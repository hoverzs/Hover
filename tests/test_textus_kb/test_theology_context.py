"""Phase D2: PROFILE_THEOLOGY context integration tests."""

from __future__ import annotations

from pathlib import Path

from textus_kb.adapters.theology import THEOLOGY_SOURCE_ID
from textus_kb.citation import (
    build_citation_ref,
    citations_from_context_packet,
    format_theology_citation,
)
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import (
    PROFILE_EXEGESIS,
    PROFILE_HISTORICAL,
    PROFILE_THEOLOGY,
    TIER_PRIMARY,
    THEOLOGY_EVIDENCE_LIMIT,
    THEOLOGY_NO_MATCH_WARNING,
    THEOLOGY_SOURCE_WARNING,
    ContextProfile,
)
from textus_kb.context_selection import budget_type_for_item
from textus_kb.evidence import (
    RELATION_THEOLOGICAL_SOURCE,
    EvidencePacket,
)
from textus_kb.importers.acai_entities import ACAI_SOURCE_ID
from textus_kb.importers.theology_sqlite import (
    create_empty_theology_database,
    import_theology_sqlite,
)
from textus_kb.repositories.theology_repository import TheologyRepository
from textus_kb.retrieval import retrieve

EDITION_ID = "test.edition.d2"
AUTHOR_ID = "test.author.d2"
WORK_ID = "test.work.d2"
SOURCE_URL = "https://example.test/theology-d2"


def _packet(canonical: str = "John.3.16", display: str = "Jn 3,16") -> EvidencePacket:
    return EvidencePacket(
        passage_canonical=canonical,
        passage_display=display,
        build_id="test-d2",
        manifest_version="test",
    )


def _section(
    section_id: str,
    *,
    parent: str | None,
    section_type: str,
    heading: str,
    sequence: int,
) -> dict:
    return {
        "section_id": section_id,
        "edition_id": EDITION_ID,
        "parent_section_id": parent,
        "section_type": section_type,
        "heading": heading,
        "sequence": sequence,
    }


def _store_document(*, john316_count: int = 3) -> dict:
    sections = [
        _section("book.i", parent=None, section_type="book", heading="BOOK FIRST.", sequence=1),
        _section(
            "book.i.ch1",
            parent="book.i",
            section_type="chapter",
            heading="CHAPTER 1.",
            sequence=1,
        ),
    ]
    chunks = []
    words = (
        "alpha",
        "bravo",
        "charlie",
        "delta",
        "echo",
        "foxtrot",
        "golf",
        "hotel",
        "india",
        "juliet",
    )
    for index in range(john316_count):
        section_id = f"book.i.ch1.s{index + 1}"
        sections.append(
            _section(
                section_id,
                parent="book.i.ch1",
                section_type="section",
                heading=f"{index + 1}.",
                sequence=index + 1,
            )
        )
        word = words[index]
        links = [{"canonical_passage": "John.3.16", "raw_citation": "John.3.16"}]
        if index == 0:
            links.append(
                {"canonical_passage": "John.3.16-18", "raw_citation": "John.3.16-18"}
            )
        chunks.append(
            {
                "chunk_id": f"chunk.john316.{index + 1:02d}",
                "section_id": section_id,
                "sequence": 1,
                "text": f"SYNTHETIC theology {word} body.",
                "plain_text": f"SYNTHETIC theology {word} body.",
                "source_locator": f"ccel:calvin/institutes#iii.i-p{index + 1}",
                "passage_links": links,
            }
        )

    sections.append(
        _section(
            "book.i.ch1.rom",
            parent="book.i.ch1",
            section_type="section",
            heading="9.",
            sequence=90,
        )
    )
    chunks.append(
        {
            "chunk_id": "chunk.rom83.only",
            "section_id": "book.i.ch1.rom",
            "sequence": 1,
            "text": "SYNTHETIC Romans-only theology body.",
            "plain_text": "SYNTHETIC Romans-only theology body.",
            "source_locator": "ccel:calvin/institutes#iii.i-p90",
            "passage_links": [
                {"canonical_passage": "Rom.8.3", "raw_citation": "Rom.8.3"}
            ],
        }
    )
    sections.append(
        _section(
            "book.i.ch1.john4",
            parent="book.i.ch1",
            section_type="section",
            heading="10.",
            sequence=91,
        )
    )
    chunks.append(
        {
            "chunk_id": "chunk.john4.only",
            "section_id": "book.i.ch1.john4",
            "sequence": 1,
            "text": "SYNTHETIC John 4 theology body.",
            "plain_text": "SYNTHETIC John 4 theology body.",
            "source_locator": "ccel:calvin/institutes#iii.i-p91",
            "passage_links": [
                {"canonical_passage": "John.4.1-42", "raw_citation": "John.4.1-42"}
            ],
        }
    )

    return {
        "authors": [
            {
                "author_id": AUTHOR_ID,
                "canonical_name": "John Calvin",
                "tradition": "reformed",
                "birth_year": 1509,
                "death_year": 1564,
            }
        ],
        "works": [
            {
                "work_id": WORK_ID,
                "author_id": AUTHOR_ID,
                "title": "The Institutes of the Christian Religion",
                "original_title": None,
                "tradition": "reformed",
                "original_language": "la",
            }
        ],
        "editions": [
            {
                "edition_id": EDITION_ID,
                "work_id": WORK_ID,
                "edition_label": "D2 fixture",
                "translator": "Henry Beveridge",
                "publication_year": 1845,
                "publisher": "Textus Test",
                "language": "en",
                "license": "Public Domain",
                "rights_status": "public-domain",
                "rights_note": "Synthetic D2 fixture.",
                "source_url": SOURCE_URL,
                "corpus": "ccel",
                "external_id": "test/calvin/institutes",
            }
        ],
        "sections": sections,
        "chunks": chunks,
    }


def _import_store(tmp_path: Path, *, john316_count: int = 3) -> Path:
    database = tmp_path / "theology.sqlite3"
    import_theology_sqlite(document=_store_document(john316_count=john316_count), database_path=database)
    return database


def _theology_items(packet) -> list:
    return [
        item
        for section in packet.sections
        for item in section.items
        if item.item_type == "theological_source"
    ]


def test_theology_profile_accepts_theological_source() -> None:
    profile = ContextProfile.load(PROFILE_THEOLOGY)
    assert RELATION_THEOLOGICAL_SOURCE in profile.priorities
    assert profile.item_tiers["theological_source"] == TIER_PRIMARY
    assert budget_type_for_item("theological_source") == "theology"


def test_other_profiles_do_not_accept_theological_source() -> None:
    exegesis = ContextProfile.load(PROFILE_EXEGESIS)
    historical = ContextProfile.load(PROFILE_HISTORICAL)
    assert RELATION_THEOLOGICAL_SOURCE not in exegesis.priorities
    assert RELATION_THEOLOGICAL_SOURCE not in historical.priorities
    assert "theological_source" not in exegesis.item_tiers
    assert "theological_source" not in historical.item_tiers
    assert "theological_source" not in exegesis.type_budgets
    assert "theological_source" not in historical.type_budgets
    assert "theology" not in exegesis.type_budgets
    assert "theology" not in historical.type_budgets


def test_theology_evidence_enters_context_with_citation_metadata(tmp_path: Path) -> None:
    database = _import_store(tmp_path)
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=database,
    )
    items = _theology_items(context)
    assert items
    assert "theological" in {section.type for section in context.sections}
    first = items[0]
    assert first.source_id == THEOLOGY_SOURCE_ID
    meta = first.metadata
    assert meta["author_name"] == "John Calvin"
    assert meta["work_title"] == "The Institutes of the Christian Religion"
    assert meta["human_readable_locator"]
    assert meta["source_locator"] == "ccel:calvin/institutes#iii.i-p1"
    assert meta["source_url"] == SOURCE_URL
    assert meta["translator"] == "Henry Beveridge"
    assert meta["publication_year"] == 1845
    assert "John.3.16" in meta["canonical_passages"]
    assert meta["canonical_scope"]
    citation = format_theology_citation(meta)
    assert "John Calvin" in citation
    assert "Beveridge" in citation
    assert "1845" in citation
    assert "p. " not in citation
    ref = build_citation_ref(
        evidence_id=first.evidence_id,
        source_id=first.source_id,
        source_type="sqlite",
        metadata=meta,
        relation_type=RELATION_THEOLOGICAL_SOURCE,
    )
    assert ref.citation_ready is True
    assert ref.upstream_url == SOURCE_URL
    coverage = citations_from_context_packet(context)
    theology_refs = [item for item in coverage.citations if item.source_id == THEOLOGY_SOURCE_ID]
    assert theology_refs
    assert all(item.citation_ready for item in theology_refs)
    assert THEOLOGY_SOURCE_WARNING not in context.warnings
    assert THEOLOGY_NO_MATCH_WARNING not in context.warnings


def test_theology_evidence_order_is_repository_order(tmp_path: Path) -> None:
    database = _import_store(tmp_path, john316_count=4)
    repo_ids = [
        chunk.chunk_id
        for chunk in TheologyRepository(database).chunks_for_passage("John.3.16")
    ]
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=database,
    )
    context_ids = [item.metadata["chunk_id"] for item in _theology_items(context)]
    assert context_ids == repo_ids[: len(context_ids)]
    assert context_ids == sorted(context_ids, key=lambda chunk_id: repo_ids.index(chunk_id))


def test_theology_evidence_limit_is_applied(tmp_path: Path) -> None:
    database = _import_store(tmp_path, john316_count=8)
    repo_ids = [
        chunk.chunk_id
        for chunk in TheologyRepository(database).chunks_for_passage(
            "John.3.16",
            limit=THEOLOGY_EVIDENCE_LIMIT,
        )
    ]
    assert len(repo_ids) == THEOLOGY_EVIDENCE_LIMIT
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=database,
    )
    items = _theology_items(context)
    assert len(items) == THEOLOGY_EVIDENCE_LIMIT
    assert [item.metadata["chunk_id"] for item in items] == repo_ids


def test_duplicate_chunk_does_not_enter_context_twice(tmp_path: Path) -> None:
    database = _import_store(tmp_path, john316_count=2)
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=database,
    )
    ids = [item.evidence_id for item in _theology_items(context)]
    assert ids
    assert len(ids) == len(set(ids))
    chunk_ids = [item.metadata["chunk_id"] for item in _theology_items(context)]
    assert chunk_ids.count("chunk.john316.01") == 1


def test_missing_theology_db_is_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=missing,
    )
    assert _theology_items(context) == []
    assert THEOLOGY_SOURCE_WARNING in context.warnings
    assert THEOLOGY_NO_MATCH_WARNING not in context.warnings
    assert context.sections


def test_invalid_theology_db_is_fail_closed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.sqlite3"
    broken.write_text("not a sqlite database", encoding="utf-8")
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=broken,
    )
    assert _theology_items(context) == []
    assert THEOLOGY_SOURCE_WARNING in context.warnings
    assert THEOLOGY_NO_MATCH_WARNING not in context.warnings


def test_available_store_without_passage_match_uses_no_match_warning(tmp_path: Path) -> None:
    database = _import_store(tmp_path)
    context = build_context_from_evidence(
        _packet("Gen.1.1", "Gen 1,1"),
        PROFILE_THEOLOGY,
        theology_database_path=database,
    )
    assert _theology_items(context) == []
    assert THEOLOGY_NO_MATCH_WARNING in context.warnings
    assert THEOLOGY_SOURCE_WARNING not in context.warnings


def test_empty_available_store_uses_no_match_warning(tmp_path: Path) -> None:
    empty = tmp_path / "empty.sqlite3"
    create_empty_theology_database(empty)
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=empty,
    )
    assert _theology_items(context) == []
    assert THEOLOGY_NO_MATCH_WARNING in context.warnings
    assert THEOLOGY_SOURCE_WARNING not in context.warnings


def test_available_store_with_match_omits_missing_layer_warning(tmp_path: Path) -> None:
    database = _import_store(tmp_path)
    context = build_context_from_evidence(
        _packet(),
        PROFILE_THEOLOGY,
        theology_database_path=database,
    )
    assert _theology_items(context)
    assert THEOLOGY_SOURCE_WARNING not in context.warnings
    assert THEOLOGY_NO_MATCH_WARNING not in context.warnings


def test_exegesis_and_historical_ignore_theology_store(
    phase2a_manifest, tmp_path: Path
) -> None:
    evidence = retrieve("Jn 4,1-42", manifest=phase2a_manifest)
    database = _import_store(tmp_path)
    missing = tmp_path / "missing.sqlite3"
    exegesis_with = build_context_from_evidence(
        evidence,
        PROFILE_EXEGESIS,
        theology_database_path=database,
    )
    exegesis_without = build_context_from_evidence(
        evidence,
        PROFILE_EXEGESIS,
        theology_database_path=missing,
    )
    historical_with = build_context_from_evidence(
        evidence,
        PROFILE_HISTORICAL,
        theology_database_path=database,
    )
    historical_without = build_context_from_evidence(
        evidence,
        PROFILE_HISTORICAL,
        theology_database_path=missing,
    )
    assert exegesis_with.evidence_ids == exegesis_without.evidence_ids
    assert historical_with.evidence_ids == historical_without.evidence_ids
    for packet in (exegesis_with, historical_with):
        assert _theology_items(packet) == []
        assert THEOLOGY_SOURCE_ID not in packet.source_ids
        assert all(not item_id.startswith("EV-THEO-") for item_id in packet.evidence_ids)


def test_aquifer_and_acai_evidence_behavior_unchanged() -> None:
    evidence = retrieve("Jn 4,1-42")
    assert any(item.relation_type == "exegetical_note" for item in evidence.evidence_items)
    assert all(item.source_id != THEOLOGY_SOURCE_ID for item in evidence.evidence_items)
    context = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    assert context.selection_stats["aquifer_selected"] >= 1
    assert THEOLOGY_SOURCE_ID not in context.source_ids
    acai_items = [item for item in evidence.evidence_items if item.source_id == ACAI_SOURCE_ID]
    assert all(item.relation_type != RELATION_THEOLOGICAL_SOURCE for item in acai_items)
