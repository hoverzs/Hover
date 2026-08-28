"""Isolated Calvin + Hodge combined theology builder tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_THEOLOGY
from textus_kb.evidence import EvidencePacket
from textus_kb.importers.ccel_thml import parse_ccel_institutes_thml
from textus_kb.importers.combined_theology import (
    IMPORT_MODE_COMBINED_CALVIN_HODGE,
    CombinedTheologyImportError,
    import_combined_calvin_hodge_thml,
    merge_theology_documents,
)
from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    SCHEMA_VERSION,
    validate_theology_database,
)
from textus_kb.prompt_composer import compose_grounded_prompt
from textus_kb.repositories.theology_repository import TheologyRepository

CALVIN_FIXTURE = Path("tests/fixtures/kb/ccel_institutes_thml_min.xml")
HODGE_FIXTURES = {
    1: Path("tests/fixtures/kb/hodge_theology1_thml_min.xml"),
    2: Path("tests/fixtures/kb/hodge_theology2_thml_min.xml"),
    3: Path("tests/fixtures/kb/hodge_theology3_thml_min.xml"),
}


def _build(tmp_path: Path, *, name: str = "combined.sqlite3"):
    return import_combined_calvin_hodge_thml(
        calvin_xml_path=CALVIN_FIXTURE,
        hodge_volume1_xml_path=HODGE_FIXTURES[1],
        hodge_volume2_xml_path=HODGE_FIXTURES[2],
        hodge_volume3_xml_path=HODGE_FIXTURES[3],
        database_path=tmp_path / name,
    )


def _query(database: Path, sql: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(database) as connection:
        return list(connection.execute(sql, params))


def test_production_path_is_rejected() -> None:
    with pytest.raises(CombinedTheologyImportError, match="production theology.sqlite3"):
        import_combined_calvin_hodge_thml(
            calvin_xml_path=CALVIN_FIXTURE,
            hodge_volume1_xml_path=HODGE_FIXTURES[1],
            hodge_volume2_xml_path=HODGE_FIXTURES[2],
            hodge_volume3_xml_path=HODGE_FIXTURES[3],
            database_path=DEFAULT_DATABASE_PATH,
        )


def test_combined_fixture_shape_and_ids(tmp_path: Path) -> None:
    report = _build(tmp_path)
    assert report.schema_version == SCHEMA_VERSION
    assert report.import_mode == IMPORT_MODE_COMBINED_CALVIN_HODGE
    assert report.author_count == 2
    assert report.work_count == 2
    assert report.edition_count == 4
    authors = {
        row[0]: row[1]
        for row in _query(report.database_path, "SELECT author_id, canonical_name FROM authors")
    }
    assert authors == {
        "ccel.calvin": "John Calvin",
        "ccel.hodge": "Charles Hodge",
    }
    works = {
        row[0]: row[1]
        for row in _query(report.database_path, "SELECT work_id, author_id FROM works")
    }
    assert works == {
        "ccel.calvin.institutes": "ccel.calvin",
        "ccel.hodge.systematic_theology": "ccel.hodge",
    }
    editions = {
        row[0]: row[1]
        for row in _query(
            report.database_path,
            "SELECT edition_id, rights_status FROM editions ORDER BY edition_id",
        )
    }
    assert editions["ccel.calvin.institutes.beveridge.1845"] == "public-domain"
    assert editions["ccel.hodge.systematic_theology.vol1.ccel_thml"] == "needs-review"
    assert editions["ccel.hodge.systematic_theology.vol2.ccel_thml"] == "needs-review"
    assert editions["ccel.hodge.systematic_theology.vol3.ccel_thml"] == "needs-review"
    store_keys = {
        row[0] for row in _query(report.database_path, "SELECT key FROM store_metadata")
    }
    assert "rights_status" not in store_keys
    assert report.chunk_count == report.calvin_chunk_count + report.hodge_chunk_count
    assert (
        report.passage_link_count
        == report.calvin_passage_link_count + report.hodge_passage_link_count
    )


def test_no_id_collisions(tmp_path: Path) -> None:
    report = _build(tmp_path)
    for table, column in (
        ("authors", "author_id"),
        ("works", "work_id"),
        ("editions", "edition_id"),
        ("sections", "section_id"),
        ("chunks", "chunk_id"),
    ):
        ids = [row[0] for row in _query(report.database_path, f"SELECT {column} FROM {table}")]
        assert ids
        assert len(ids) == len(set(ids))
    links = _query(
        report.database_path,
        "SELECT chunk_id, canonical_passage FROM passage_links",
    )
    assert len(links) == len(set(links))
    section_ids = [row[0] for row in _query(report.database_path, "SELECT section_id FROM sections")]
    calvin_ids = [item for item in section_ids if "calvin" in item]
    hodge_ids = [item for item in section_ids if "hodge" in item]
    assert calvin_ids
    assert hodge_ids
    assert set(calvin_ids).isdisjoint(hodge_ids)


def test_duplicate_cross_source_id_is_hard_error() -> None:
    calvin, _extras = parse_ccel_institutes_thml(CALVIN_FIXTURE)
    cloned = {
        "authors": calvin["authors"],
        "works": calvin["works"],
        "editions": [{**calvin["editions"][0], "edition_label": "clone"}],
        "sections": calvin["sections"],
        "chunks": calvin["chunks"],
    }
    with pytest.raises(CombinedTheologyImportError, match="Duplicate edition id"):
        merge_theology_documents([calvin, cloned])


def test_fts_both_authors(tmp_path: Path) -> None:
    report = _build(tmp_path)
    repo = TheologyRepository(report.database_path)
    synthetic = repo.search_text("Synthetic")
    assert any(hit.author_id == "ccel.hodge" for hit in synthetic)
    fts_count = _query(report.database_path, "SELECT COUNT(*) FROM chunks_fts")[0][0]
    chunk_count = _query(report.database_path, "SELECT COUNT(*) FROM chunks")[0][0]
    assert fts_count == chunk_count
    orphans = _query(
        report.database_path,
        """
        SELECT COUNT(*) FROM chunks
        WHERE section_id NOT IN (SELECT section_id FROM sections)
        """,
    )[0][0]
    assert orphans == 0
    link_orphans = _query(
        report.database_path,
        """
        SELECT COUNT(*) FROM passage_links
        WHERE chunk_id NOT IN (SELECT chunk_id FROM chunks)
        """,
    )[0][0]
    assert link_orphans == 0


def test_passage_retrieval_both_authors_and_diversity(tmp_path: Path) -> None:
    report = _build(tmp_path)
    repo = TheologyRepository(report.database_path)
    hits = repo.chunks_for_passage("John.3.16", limit=6)
    authors = {hit.author_id for hit in hits}
    assert "ccel.calvin" in authors
    assert "ccel.hodge" in authors
    assert max(sum(1 for hit in hits if hit.author_id == author) for author in authors) <= 3
    rom = repo.chunks_for_passage("Rom.8.3", limit=6)
    assert rom
    assert any(hit.author_id == "ccel.hodge" for hit in rom)


def test_logical_hash_and_counts_are_deterministic(tmp_path: Path) -> None:
    first = _build(tmp_path, name="a.sqlite3")
    second = _build(tmp_path, name="b.sqlite3")
    assert first.content_hash == second.content_hash
    assert first.chunk_count == second.chunk_count
    assert first.passage_link_count == second.passage_link_count
    assert first.section_count == second.section_count
    validation = validate_theology_database(first.database_path)
    assert validation.content_hash == first.content_hash
    assert validation.import_mode == IMPORT_MODE_COMBINED_CALVIN_HODGE
    ids_a = [
        hit.chunk_id
        for hit in TheologyRepository(first.database_path).chunks_for_passage("John.3.16", limit=6)
    ]
    ids_b = [
        hit.chunk_id
        for hit in TheologyRepository(second.database_path).chunks_for_passage("John.3.16", limit=6)
    ]
    assert ids_a == ids_b


def test_hodge_rights_remain_needs_review(tmp_path: Path) -> None:
    report = _build(tmp_path)
    rows = _query(
        report.database_path,
        """
        SELECT rights_status, license FROM editions
        WHERE edition_id LIKE 'ccel.hodge%'
        """,
    )
    assert rows
    assert all(row[0] == "needs-review" and row[1] == "unspecified" for row in rows)


def test_context_and_grounded_compose_from_combined_path(tmp_path: Path) -> None:
    report = _build(tmp_path)
    packet = EvidencePacket(
        passage_canonical="John.3.16",
        passage_display="Jn 3,16",
        build_id="combined-pilot",
        manifest_version="test",
    )
    context = build_context_from_evidence(
        packet,
        PROFILE_THEOLOGY,
        theology_database_path=report.database_path,
    )
    theology_items = [
        item
        for section in context.sections
        for item in section.items
        if item.item_type == "theological_source"
    ]
    assert theology_items
    authors = {item.metadata.get("author_name") for item in theology_items}
    assert "John Calvin" in authors
    assert "Charles Hodge" in authors
    preview = compose_grounded_prompt(
        production_prompt="SYNTHETIC production theology prompt.",
        canonical_passage="John.3.16",
        module="theology",
        context_packet=context,
    )
    assert preview.success is True
    assert "[THEOLOGICAL SOURCES]" in preview.composed_prompt
    assert "Never imply that the current corpus represents all Protestant," in (
        preview.composed_prompt
    )
    assert "Do not invent page numbers." in preview.composed_prompt
    assert "Page_" not in preview.composed_prompt
    assert "needs-review" not in preview.composed_prompt
    assert "unspecified" not in preview.composed_prompt
