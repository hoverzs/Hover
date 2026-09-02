"""Calvin Commentary ThML importer tests, against real (trimmed) CCEL XML.

Fixtures are exact, unedited slices of the real files fetched from
ccel.org (Romans = calcom38, Harmony of the Evangelists = calcom31); only
whole <div1>/<div2> elements were removed to keep the fixtures small. No
hand-authored or synthetic XML is used here — every structural case below
(range section, the untyped "anomaly" verse-1 continuation, nested
per-verse <div class="Commentary"> blocks, a two-passage Harmony section,
an inline cross-reference) is real Calvin commentary markup.
"""

from __future__ import annotations

import copy
import re
import sqlite3
from pathlib import Path

import pytest

from textus_kb.importers.calvin_commentary_thml import (
    AUTHOR_CONTRIBUTOR_ID,
    IMPORT_MODE_CALVIN_COMMENTARY_THML,
    CalvinCommentaryImportError,
    build_calvin_commentary_document,
    import_calvin_commentary_sqlite,
    merge_calvin_commentary_documents,
    parse_calvin_commentary_thml,
)
from textus_kb.importers.commentary_sqlite import (
    CommentaryImportError,
    import_commentary_sqlite,
)
from textus_kb.repositories.commentary_repository import (
    RELATION_CONTAINING_SECTION,
    RELATION_EXACT_PASSAGE,
    CommentaryRepository,
)

ROMANS_FIXTURE = Path("tests/fixtures/kb/calvin_calcom38_romans_ch1_min.xml")
HARMONY_FIXTURE = Path("tests/fixtures/kb/calvin_calcom31_harmony_min.xml")


# --- Parsing structure ------------------------------------------------


def test_romans_range_section_gets_range_passage_from_table() -> None:
    document, report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    range_section = by_id["ccel.calvin.calcom38.v.i"]
    assert [l["canonical_passage"] for l in range_section["passage_links"]] == ["Rom.1.1-7"]
    assert report.range_section_count == 2


def test_romans_untyped_anomaly_div_becomes_children_of_preceding_range() -> None:
    """The real 'v.ii' div2 (no type=scripture) holds Calvin's exposition of
    verse 1 as its own top-level div2 instead of a nested Commentary div —
    a real CCEL editorial quirk. It must still be anchored under v.i."""
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    child = by_id["ccel.calvin.calcom38.v.ii.v1"]
    assert child["parent_section_id"] == "ccel.calvin.calcom38.v.i"
    assert [l["canonical_passage"] for l in child["passage_links"]] == ["Rom.1.1"]


def test_romans_nested_commentary_divs_become_verse_children() -> None:
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    parent = by_id["ccel.calvin.calcom38.v.iii"]
    assert [l["canonical_passage"] for l in parent["passage_links"]] == ["Rom.1.8-12"]
    for n, verse in enumerate(["Rom.1.8", "Rom.1.9", "Rom.1.10", "Rom.1.11", "Rom.1.12"], start=1):
        child = by_id[f"ccel.calvin.calcom38.v.iii.v{n}"]
        assert child["parent_section_id"] == "ccel.calvin.calcom38.v.iii"
        assert [l["canonical_passage"] for l in child["passage_links"]] == [verse]


def test_romans_quoted_bible_text_is_not_chunk_content() -> None:
    """The scripture div2's own chunk (if any) must never be the quoted
    verse-text table; that is not Calvin's prose."""
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    chunks_by_section = {c["section_id"]: c for c in document["chunks"]}
    range_chunk = chunks_by_section.get("ccel.calvin.calcom38.v.i.chunk")
    if range_chunk is not None:
        assert "servus Iesu Christi" not in range_chunk["plain_text"]


def test_inline_cross_reference_is_not_a_passage_link() -> None:
    """Calvin's exposition of Romans 1:1 cites Acts 23:26 in a footnote as a
    cross-reference. That must never become a section_passage_links row —
    only the scripCom-defined Romans 1:1 passage may."""
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    section = by_id["ccel.calvin.calcom38.v.ii.v1"]
    assert [l["canonical_passage"] for l in section["passage_links"]] == ["Rom.1.1"]
    chunk = next(
        c for c in _chunks(document) if c["section_id"] == "ccel.calvin.calcom38.v.ii.v1"
    )
    assert "Acts" in chunk["plain_text"]  # the cross-reference is in the prose...
    assert "Acts.23" not in [
        l["canonical_passage"] for l in section["passage_links"]
    ]  # ...but never became a passage_link


def test_harmony_section_links_multiple_passages() -> None:
    document, report = parse_calvin_commentary_thml(HARMONY_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    section = by_id["ccel.calvin.calcom31.ix.xiv"]
    passages = {l["canonical_passage"] for l in section["passage_links"]}
    assert passages == {"Matt.1.1-17", "Luke.3.23-38"}
    assert report.multi_passage_range_count == 1


def test_harmony_verse_children_keep_their_own_single_book() -> None:
    """Children of a multi-passage Harmony section resolve their own passage
    independently (Matthew verses here), not the parent's combined range."""
    document, _report = parse_calvin_commentary_thml(HARMONY_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    child = by_id["ccel.calvin.calcom31.ix.xiv.v1"]
    assert [l["canonical_passage"] for l in child["passage_links"]] == ["Matt.1.1"]


def test_contributors_have_author_and_translator_roles() -> None:
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    roles = {(wc["contributor_id"], wc["role"]) for wc in document["work_contributors"]}
    assert (AUTHOR_CONTRIBUTOR_ID, "author") in roles
    names = {c["contributor_id"]: c["canonical_name"] for c in document["contributors"]}
    assert names[AUTHOR_CONTRIBUTOR_ID] == "John Calvin"
    translator_ids = [cid for cid, role in roles if role == "translator"]
    assert len(translator_ids) == 1
    assert "Owen" in names[translator_ids[0]]


def test_edition_metadata_is_real_not_invented() -> None:
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    edition = document["editions"][0]
    assert edition["license"] == "Public Domain"
    assert edition["rights_status"] == "public-domain"
    assert edition["language"] == "en"
    assert edition["source_url"] == "https://www.ccel.org/ccel/calvin/calcom38.xml"
    assert edition["external_id"] == "ccel/calvin/calcom38"


# --- Fail-loudly on structurally uncertain passage mapping ---------------


def test_scripture_section_without_parseable_table_fails_loudly(tmp_path: Path) -> None:
    text = ROMANS_FIXTURE.read_text(encoding="utf-8")
    # Break every scripRef's osisRef inside the FIRST scripture div2's table
    # so no passage can be recovered from it.
    mutated = re.sub(r'osisRef="Bible:Rom\.1\.1-Rom\.1\.7"', 'osisRef=""', text, count=1)
    assert mutated != text
    broken = tmp_path / "broken_romans.xml"
    broken.write_text(mutated, encoding="utf-8")
    with pytest.raises(CalvinCommentaryImportError, match="no parseable passage"):
        parse_calvin_commentary_thml(broken)


def test_dangling_scripcom_marker_fails_loudly(tmp_path: Path) -> None:
    text = ROMANS_FIXTURE.read_text(encoding="utf-8")
    # Remove the FIRST <div class="Commentary" ...> opening tag's class
    # attribute so the scripCom marker before it can no longer find its
    # paired content block by the expected structural signal.
    mutated = text.replace('<div class="Commentary" id="Bible:Rom.1.8">', "<div>", 1)
    assert mutated != text
    broken = tmp_path / "broken_marker.xml"
    broken.write_text(mutated, encoding="utf-8")
    with pytest.raises(CalvinCommentaryImportError):
        parse_calvin_commentary_thml(broken)


# --- Provenance / SHA-256 -------------------------------------------------


def test_build_document_attaches_real_raw_sha256() -> None:
    import hashlib

    document, report = build_calvin_commentary_document(ROMANS_FIXTURE)
    expected = hashlib.sha256(ROMANS_FIXTURE.read_bytes()).hexdigest()
    source_file = document["source_files"][0]
    assert source_file["raw_sha256"] == expected
    assert source_file["file_name"] == ROMANS_FIXTURE.name
    batch = document["import_batches"][0]
    assert batch["source_file_id"] == source_file["source_file_id"]
    assert batch["importer_name"] == "textus_kb.importers.calvin_commentary_thml"
    assert batch["report"]["book_id"] == report.book_id


# --- Multi-file combined import; no duplicate author/translator ----------


def test_merge_two_calvin_documents_dedupes_shared_author() -> None:
    romans_doc, _ = build_calvin_commentary_document(ROMANS_FIXTURE)
    harmony_doc, _ = build_calvin_commentary_document(HARMONY_FIXTURE)
    merged = merge_calvin_commentary_documents([romans_doc, harmony_doc])

    author_rows = [c for c in merged["contributors"] if c["contributor_id"] == AUTHOR_CONTRIBUTOR_ID]
    assert len(author_rows) == 1  # Calvin declared by both files, not duplicated

    translator_ids = {c["contributor_id"] for c in merged["contributors"]} - {AUTHOR_CONTRIBUTOR_ID}
    assert len(translator_ids) == 2  # Owen (Romans) and Pringle (Harmony) are distinct people

    assert len(merged["works"]) == 2
    assert len(merged["editions"]) == 2
    assert len(merged["source_files"]) == 2


def test_import_calvin_commentary_sqlite_combines_both_fixtures(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    report, parse_reports = import_calvin_commentary_sqlite(
        [ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=database
    )
    assert report.import_mode == IMPORT_MODE_CALVIN_COMMENTARY_THML
    assert report.work_count == 2
    assert report.source_file_count == 2
    assert report.import_batch_count == 2
    assert len(parse_reports) == 2

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        contributors = connection.execute(
            "SELECT contributor_id, canonical_name FROM contributors"
        ).fetchall()
    assert len(contributors) == 3  # Calvin + Owen + Pringle, no duplicate Calvin row


# --- Deterministic build ---------------------------------------------------


def test_deterministic_build_same_content_hash(tmp_path: Path) -> None:
    first, _ = import_calvin_commentary_sqlite(
        [ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=tmp_path / "a.sqlite3"
    )
    second, _ = import_calvin_commentary_sqlite(
        [ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=tmp_path / "b.sqlite3"
    )
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64


# --- Repository retrieval on real (trimmed) Calvin data -------------------


@pytest.fixture()
def calvin_repo(tmp_path: Path) -> CommentaryRepository:
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=database)
    return CommentaryRepository(database)


def test_exact_verse_retrieval_real_data(calvin_repo: CommentaryRepository) -> None:
    hits = calvin_repo.sections_for_passage("Rom.1.1")
    by_id = {h.section_id: h for h in hits}
    assert by_id["ccel.calvin.calcom38.v.ii.v1"].relation_type == RELATION_EXACT_PASSAGE
    assert by_id["ccel.calvin.calcom38.v.i"].relation_type == RELATION_CONTAINING_SECTION


def test_range_retrieval_real_data(calvin_repo: CommentaryRepository) -> None:
    hits = calvin_repo.sections_for_passage("Rom.1.9")
    by_id = {h.section_id: h for h in hits}
    assert by_id["ccel.calvin.calcom38.v.iii.v2"].relation_type == RELATION_EXACT_PASSAGE
    assert by_id["ccel.calvin.calcom38.v.iii"].relation_type == RELATION_CONTAINING_SECTION


def test_multi_passage_retrieval_real_data(calvin_repo: CommentaryRepository) -> None:
    via_matthew = calvin_repo.sections_for_passage("Matt.1.1-17")
    via_luke = calvin_repo.sections_for_passage("Luke.3.23-38")
    assert any(h.section_id == "ccel.calvin.calcom31.ix.xiv" for h in via_matthew)
    assert any(h.section_id == "ccel.calvin.calcom31.ix.xiv" for h in via_luke)


def test_no_cross_book_leak_real_data(calvin_repo: CommentaryRepository) -> None:
    hits = calvin_repo.sections_for_passage("Rom.1.9")
    assert all(
        passage.startswith("Rom.") for h in hits for passage in h.canonical_passages
    )


def test_book_without_calvin_commentary_returns_empty(calvin_repo: CommentaryRepository) -> None:
    assert calvin_repo.sections_for_passage("Genesis.1.1") == []
    assert calvin_repo.sections_for_passage("John.3.16") == []


def _chunks(document: dict) -> list[dict]:
    return document["chunks"]
