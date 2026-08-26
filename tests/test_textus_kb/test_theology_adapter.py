"""Theology adapter and citation-ready Evidence mapping tests."""

from __future__ import annotations

from pathlib import Path

from textus_kb.adapters.theology import (
    THEOLOGY_SOURCE_ID,
    TheologyAdapter,
    theology_chunk_to_evidence,
)
from textus_kb.citation import build_citation_ref, format_theology_citation
from textus_kb.evidence import RELATION_THEOLOGICAL_SOURCE, EvidenceItem
from textus_kb.importers.theology_sqlite import (
    create_empty_theology_database,
    import_theology_sqlite,
)
from textus_kb.repositories.theology_repository import (
    TheologyChunkResult,
    TheologyRepository,
)
from textus_kb.retrieval import retrieve, retrieve_theology_evidence


def _chunk(**overrides: object) -> TheologyChunkResult:
    payload = {
        "chunk_id": "ccel.calvin.institutes.iv.xiii-p15.chunk",
        "plain_text": "SYNTHETIC theology body text.",
        "heading": "4.",
        "section_type": "section",
        "source_locator": "ccel:calvin/institutes#iv.xiii-p15",
        "human_readable_locator": (
            "John Calvin, The Institutes of the Christian Religion, "
            "Book II, Chapter 12, Section 4"
        ),
        "author_name": "John Calvin",
        "work_title": "The Institutes of the Christian Religion",
        "tradition": "reformed",
        "translator": "Henry Beveridge",
        "publication_year": 1845,
        "language": "en",
        "rights_status": "public-domain",
        "license": "Public Domain",
        "rights_note": "CCEL ThML DC.Rights states Public Domain.",
        "source_url": "https://www.ccel.org/ccel/calvin/institutes.xml",
        "corpus": "ccel",
        "external_id": "ccel/calvin/institutes",
        "canonical_passages": ("John.3.16", "John.3.16-18"),
        "snippet": "",
    }
    payload.update(overrides)
    return TheologyChunkResult(**payload)  # type: ignore[arg-type]


def _minimal_store_document() -> dict:
    edition_id = "test.edition.d1"
    return {
        "authors": [
            {
                "author_id": "test.author.d1",
                "canonical_name": "John Calvin",
                "tradition": "reformed",
                "birth_year": 1509,
                "death_year": 1564,
            }
        ],
        "works": [
            {
                "work_id": "test.work.d1",
                "author_id": "test.author.d1",
                "title": "The Institutes of the Christian Religion",
                "original_title": None,
                "tradition": "reformed",
                "original_language": "la",
            }
        ],
        "editions": [
            {
                "edition_id": edition_id,
                "work_id": "test.work.d1",
                "edition_label": "D1 fixture",
                "translator": "Henry Beveridge",
                "publication_year": 1845,
                "publisher": "Textus Test",
                "language": "en",
                "license": "Public Domain",
                "rights_status": "public-domain",
                "rights_note": "Synthetic D1 fixture.",
                "source_url": "https://example.test/theology-d1",
                "corpus": "ccel",
                "external_id": "test/calvin/institutes",
            }
        ],
        "sections": [
            {
                "section_id": "book.i",
                "edition_id": edition_id,
                "parent_section_id": None,
                "section_type": "book",
                "heading": "BOOK FIRST.",
                "sequence": 1,
            },
            {
                "section_id": "book.i.ch1",
                "edition_id": edition_id,
                "parent_section_id": "book.i",
                "section_type": "chapter",
                "heading": "CHAPTER 1.",
                "sequence": 1,
            },
            {
                "section_id": "book.i.ch1.s1",
                "edition_id": edition_id,
                "parent_section_id": "book.i.ch1",
                "section_type": "section",
                "heading": "1.",
                "sequence": 1,
            },
            {
                "section_id": "book.i.ch1.s2",
                "edition_id": edition_id,
                "parent_section_id": "book.i.ch1",
                "section_type": "section",
                "heading": "2.",
                "sequence": 2,
            },
        ],
        "chunks": [
            {
                "chunk_id": "chunk.first",
                "section_id": "book.i.ch1.s1",
                "sequence": 1,
                "text": "SYNTHETIC first chunk.",
                "plain_text": "SYNTHETIC first chunk.",
                "source_locator": "ccel:calvin/institutes#iii.ii-p6",
                "passage_links": [
                    {"canonical_passage": "John.3.16", "raw_citation": "John.3.16"}
                ],
            },
            {
                "chunk_id": "chunk.second",
                "section_id": "book.i.ch1.s2",
                "sequence": 1,
                "text": "SYNTHETIC second chunk.",
                "plain_text": "SYNTHETIC second chunk.",
                "source_locator": "ccel:calvin/institutes#iii.ii-p7",
                "passage_links": [
                    {
                        "canonical_passage": "John.3.16-18",
                        "raw_citation": "John.3.16-18",
                    }
                ],
            },
        ],
    }


def test_chunk_maps_to_evidence_without_text_loss() -> None:
    chunk = _chunk()
    item = TheologyAdapter().to_evidence_item(chunk)
    assert isinstance(item, EvidenceItem)
    assert item.content == "SYNTHETIC theology body text."
    assert item.content == chunk.plain_text
    assert item.source_id == THEOLOGY_SOURCE_ID
    assert item.relation_type == RELATION_THEOLOGICAL_SOURCE
    assert item.passage == "John.3.16"
    assert item.evidence_id == "EV-THEO-ccel.calvin.institutes.iv.xiii-p15.chunk"


def test_provenance_fields_are_preserved() -> None:
    item = theology_chunk_to_evidence(_chunk())
    meta = item.metadata
    assert meta["author_name"] == "John Calvin"
    assert meta["work_title"] == "The Institutes of the Christian Religion"
    assert meta["human_readable_locator"] == (
        "John Calvin, The Institutes of the Christian Religion, "
        "Book II, Chapter 12, Section 4"
    )
    assert meta["source_locator"] == "ccel:calvin/institutes#iv.xiii-p15"
    assert meta["translator"] == "Henry Beveridge"
    assert meta["publication_year"] == 1845
    assert meta["tradition"] == "reformed"
    assert meta["rights_status"] == "public-domain"
    assert meta["license"] == "Public Domain"
    assert meta["source_url"] == "https://www.ccel.org/ccel/calvin/institutes.xml"
    assert meta["corpus"] == "ccel"
    assert meta["external_id"] == "ccel/calvin/institutes"
    assert meta["canonical_passages"] == ["John.3.16", "John.3.16-18"]
    assert item.language == "en"


def test_citation_is_built_from_metadata_only() -> None:
    item = theology_chunk_to_evidence(_chunk())
    citation = format_theology_citation(item)
    assert citation == (
        "John Calvin, The Institutes of the Christian Religion, "
        "Book II, Chapter 12, Section 4, trans. Henry Beveridge, 1845."
    )
    assert "iv.xiii-p15" not in citation
    ref = build_citation_ref(
        evidence_id=item.evidence_id,
        source_id=item.source_id,
        source_type=item.source_type,
        metadata=item.metadata,
        relation_type=item.relation_type,
    )
    assert ref.citation_ready is True
    assert ref.license == "Public Domain"
    assert ref.upstream_url == item.metadata["source_url"]
    assert ref.article_or_chunk_id == item.metadata["chunk_id"]
    assert "John.3.16" in ref.canonical_scope


def test_missing_optional_metadata_is_not_invented() -> None:
    chunk = _chunk(translator="", publication_year=None, rights_note="")
    item = theology_chunk_to_evidence(chunk)
    assert "translator" not in item.metadata
    assert "publication_year" not in item.metadata
    citation = format_theology_citation(item)
    assert "trans." not in citation
    assert "1845" not in citation
    assert "Beveridge" not in citation
    assert citation.endswith(".")


def test_repository_order_is_preserved(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    import_theology_sqlite(document=_minimal_store_document(), database_path=database)
    repo = TheologyRepository(database)
    chunks = repo.chunks_for_passage("John.3.16")
    items = TheologyAdapter().to_evidence_items(chunks)
    assert [chunk.chunk_id for chunk in chunks] == [item.metadata["chunk_id"] for item in items]
    assert [item.metadata["chunk_id"] for item in items] == ["chunk.first", "chunk.second"]


def test_retrieve_theology_evidence_fail_closed(tmp_path: Path) -> None:
    missing = retrieve_theology_evidence(
        "John.3.16",
        database_path=tmp_path / "missing.sqlite3",
    )
    assert missing == []

    broken = tmp_path / "broken.sqlite3"
    broken.write_text("not a sqlite database", encoding="utf-8")
    assert retrieve_theology_evidence("John.3.16", database_path=broken) == []

    empty = tmp_path / "empty.sqlite3"
    create_empty_theology_database(empty)
    assert retrieve_theology_evidence("John.3.16", database_path=empty) == []

    database = tmp_path / "theology.sqlite3"
    import_theology_sqlite(document=_minimal_store_document(), database_path=database)
    assert retrieve_theology_evidence("Gen.1.1", database_path=database) == []
    hits = retrieve_theology_evidence("John.3.16", database_path=database)
    assert [item.metadata["chunk_id"] for item in hits] == ["chunk.first", "chunk.second"]


def test_retrieve_does_not_inject_theology_evidence(phase2a_manifest) -> None:
    packet = retrieve("Jn 4,1-42", manifest=phase2a_manifest)
    assert all(item.source_id != THEOLOGY_SOURCE_ID for item in packet.evidence_items)
    assert THEOLOGY_SOURCE_ID not in {
        str(source.get("source_id") or source.get("id") or "")
        for source in packet.sources
    }
