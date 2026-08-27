"""Read-only Theology retrieval API tests."""

from __future__ import annotations

from pathlib import Path

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.importers.theology_sqlite import (
    create_empty_theology_database,
    import_theology_sqlite,
)
from textus_kb.repositories.theology_repository import (
    MAX_SEARCH_LIMIT,
    TheologyRepository,
)

EDITION_ID = "test.edition.retrieval.en"
AUTHOR_ID = "test.author.retrieval"
WORK_ID = "test.work.retrieval"


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


def _chunk(
    chunk_id: str,
    section_id: str,
    text: str,
    locator: str,
    links: list[str],
    *,
    sequence: int = 1,
) -> dict:
    payload = {
        "chunk_id": chunk_id,
        "section_id": section_id,
        "sequence": sequence,
        "text": text,
        "plain_text": text,
        "source_locator": locator,
        "passage_links": [
            {"canonical_passage": passage, "raw_citation": passage} for passage in links
        ],
    }
    return payload


def _retrieval_document() -> dict:
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
                "title": "Institutes of the Christian Religion",
                "original_title": None,
                "tradition": "reformed",
                "original_language": "la",
            }
        ],
        "editions": [
            {
                "edition_id": EDITION_ID,
                "work_id": WORK_ID,
                "edition_label": "Retrieval fixture",
                "translator": "Henry Beveridge",
                "publication_year": 1845,
                "publisher": "Textus Test",
                "language": "en",
                "license": "Public Domain",
                "rights_status": "public-domain",
                "rights_note": "Synthetic retrieval fixture.",
                "source_url": "https://example.test/theology-retrieval",
                "corpus": "ccel",
                "external_id": "test/calvin/institutes",
            }
        ],
        "sections": [
            _section("book.i", parent=None, section_type="book", heading="BOOK FIRST.", sequence=1),
            _section(
                "book.i.ch1",
                parent="book.i",
                section_type="chapter",
                heading="CHAPTER 1.",
                sequence=1,
            ),
            _section(
                "book.i.ch1.s1",
                parent="book.i.ch1",
                section_type="section",
                heading="1.",
                sequence=1,
            ),
            _section(
                "book.i.ch1.s2",
                parent="book.i.ch1",
                section_type="section",
                heading="2.",
                sequence=2,
            ),
            _section(
                "book.i.ch1.s3",
                parent="book.i.ch1",
                section_type="section",
                heading="3.",
                sequence=3,
            ),
            _section(
                "book.i.ch2",
                parent="book.i",
                section_type="chapter",
                heading="CHAPTER 2.",
                sequence=2,
            ),
            _section(
                "book.i.ch2.s1",
                parent="book.i.ch2",
                section_type="section",
                heading="1.",
                sequence=1,
            ),
            _section(
                "book.ii",
                parent=None,
                section_type="book",
                heading="BOOK SECOND.",
                sequence=2,
            ),
            _section(
                "book.ii.ch1",
                parent="book.ii",
                section_type="chapter",
                heading="CHAPTER 1.",
                sequence=1,
            ),
            _section(
                "book.ii.ch1.s1",
                parent="book.ii.ch1",
                section_type="section",
                heading="1.",
                sequence=1,
            ),
            _section(
                "book.ii.ch1.s2",
                parent="book.ii.ch1",
                section_type="section",
                heading="2.",
                sequence=2,
            ),
        ],
        "chunks": [
            _chunk(
                "chunk.exact.dup",
                "book.i.ch1.s1",
                "SYNTHETIC. Exact John 3:16 with overlapping range and xylophone one.",
                "ccel:calvin/institutes#iii.ii-p6",
                ["John.3.16", "John.3.16-18"],
            ),
            _chunk(
                "chunk.range.wide",
                "book.i.ch1.s2",
                "SYNTHETIC. Stored range John 3:14-17 xylophone two.",
                "ccel:calvin/institutes#iii.ii-p7",
                ["John.3.14-17"],
            ),
            _chunk(
                "chunk.range.later",
                "book.i.ch1.s3",
                "SYNTHETIC. Stored range John 3:16-18 only.",
                "ccel:calvin/institutes#iii.ii-p8",
                ["John.3.16-18"],
            ),
            _chunk(
                "chunk.rom",
                "book.i.ch2.s1",
                "SYNTHETIC. Romans eight three on justification.",
                "ccel:calvin/institutes#iii.iii-p1",
                ["Rom.8.3"],
            ),
            _chunk(
                "chunk.faith",
                "book.ii.ch1.s1",
                "SYNTHETIC. Saving faith receives grace.",
                "ccel:calvin/institutes#iv.ii-p1",
                ["Eph.2.8"],
            ),
            _chunk(
                "chunk.heading",
                "book.ii.ch1.s2",
                "SYNTHETIC. Body without the heading keyword.",
                "ccel:calvin/institutes#iv.ii-p2",
                [],
            ),
        ],
    }


def _repo(tmp_path: Path) -> TheologyRepository:
    database = tmp_path / "theology.sqlite3"
    document = _retrieval_document()
    # Heading-only FTS match: section heading, not chunk body.
    document["sections"][-1]["heading"] = "Predestination heading marker"
    import_theology_sqlite(document=document, database_path=database)
    return TheologyRepository(database)


def test_exact_verse_match_and_range_overlap(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    hits = repo.chunks_for_passage(CanonicalReference.parse("John.3.16"))
    ids = [hit.chunk_id for hit in hits]
    assert ids[0] == "chunk.exact.dup"
    assert "chunk.range.wide" in ids
    assert "chunk.range.later" in ids
    assert "chunk.rom" not in ids
    assert ids.index("chunk.range.later") < ids.index("chunk.range.wide")


def test_query_range_finds_stored_single_verse(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    hits = repo.chunks_for_passage("John.3.14-17")
    ids = {hit.chunk_id for hit in hits}
    assert "chunk.exact.dup" in ids
    assert "chunk.range.wide" in ids
    assert hits[0].chunk_id == "chunk.range.wide"


def test_stored_range_matches_query_single_verse(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    hits = repo.chunks_for_passage("John.3.16")
    later = next(hit for hit in hits if hit.chunk_id == "chunk.range.later")
    assert later.canonical_passages == ("John.3.16-18",)


def test_duplicate_overlapping_links_yield_one_chunk(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    hits = repo.chunks_for_passage("John.3.16")
    assert [hit.chunk_id for hit in hits].count("chunk.exact.dup") == 1
    exact = next(hit for hit in hits if hit.chunk_id == "chunk.exact.dup")
    assert exact.canonical_passages == ("John.3.16", "John.3.16-18")


def test_unknown_passage_returns_empty(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.chunks_for_passage("Gen.1.1") == []


def test_invalid_passage_input_is_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.chunks_for_passage("") == []
    assert repo.chunks_for_passage("not-a-verse") == []
    assert repo.chunks_for_passage("Bible:NotABook.1.1") == []


def test_fts_simple_and_multiword(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    simple = repo.search_text("justification")
    assert [hit.chunk_id for hit in simple] == ["chunk.rom"]
    multi = repo.search_text("Saving faith")
    assert [hit.chunk_id for hit in multi] == ["chunk.faith"]


def test_fts_heading_match(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    hits = repo.search_text("Predestination heading marker")
    assert [hit.chunk_id for hit in hits] == ["chunk.heading"]
    assert hits[0].heading == "Predestination heading marker"


def test_fts_special_characters_empty_and_no_hit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.search_text('"fura- lekérdezés:1') == []
    assert repo.search_text("alpha AND missing") == []
    assert repo.search_text("") == []
    assert repo.search_text("   ") == []
    assert repo.search_text("xyzzy-no-such-token") == []


def test_fts_limit_and_stable_ordering(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = [hit.chunk_id for hit in repo.search_text("xylophone")]
    second = [hit.chunk_id for hit in repo.search_text("xylophone")]
    assert first == second
    assert set(first) == {"chunk.exact.dup", "chunk.range.wide"}
    limited = repo.search_text("xylophone", limit=1)
    assert len(limited) == 1
    assert limited[0].chunk_id == first[0]
    capped = repo.search_text("xylophone", limit=10_000)
    assert len(capped) == 2
    assert len(capped) <= MAX_SEARCH_LIMIT


def test_provenance_and_human_readable_locator(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    hit = repo.chunks_for_passage("John.3.16")[0]
    assert hit.author_name == "John Calvin"
    assert hit.work_title == "Institutes of the Christian Religion"
    assert hit.tradition == "reformed"
    assert hit.translator == "Henry Beveridge"
    assert hit.publication_year == 1845
    assert hit.language == "en"
    assert hit.rights_status == "public-domain"
    assert hit.license == "Public Domain"
    assert hit.rights_note == "Synthetic retrieval fixture."
    assert hit.source_url == "https://example.test/theology-retrieval"
    assert hit.corpus == "ccel"
    assert hit.external_id == "test/calvin/institutes"
    assert hit.source_locator == "ccel:calvin/institutes#iii.ii-p6"
    assert hit.heading == "1."
    assert hit.section_type == "section"
    assert hit.human_readable_locator == (
        "John Calvin, Institutes of the Christian Religion, Book I, Chapter 1, Section 1"
    )
    assert "fragment" not in hit.human_readable_locator


def test_split_section_appends_fragment_suffix(tmp_path: Path) -> None:
    document = _retrieval_document()
    document["chunks"].append(
        _chunk(
            "chunk.exact.dup.2",
            "book.i.ch1.s1",
            "SYNTHETIC. Second fragment of the same section.",
            "ccel:calvin/institutes#iii.ii-p6b",
            ["John.3.16"],
            sequence=2,
        )
    )
    database = tmp_path / "split-locator.sqlite3"
    import_theology_sqlite(document=document, database_path=database)
    hits = [
        hit
        for hit in TheologyRepository(database).chunks_for_passage("John.3.16")
        if hit.chunk_id.startswith("chunk.exact.dup")
    ]
    locators = {hit.chunk_id: hit.human_readable_locator for hit in hits}
    assert locators["chunk.exact.dup"] == (
        "John Calvin, Institutes of the Christian Religion, Book I, Chapter 1, "
        "Section 1, fragment 1"
    )
    assert locators["chunk.exact.dup.2"] == (
        "John Calvin, Institutes of the Christian Religion, Book I, Chapter 1, "
        "Section 1, fragment 2"
    )


def test_argument_chapter_uses_heading_not_sequence(tmp_path: Path) -> None:
    document = _retrieval_document()
    document["sections"].append(
        _section(
            "book.i.arg",
            parent="book.i",
            section_type="chapter",
            heading="ARGUMENT.",
            sequence=99,
        )
    )
    document["sections"].append(
        _section(
            "book.i.arg.s1",
            parent="book.i.arg",
            section_type="section",
            heading="1.",
            sequence=1,
        )
    )
    document["chunks"].append(
        _chunk(
            "chunk.argument",
            "book.i.arg.s1",
            "SYNTHETIC. Argument chapter body.",
            "ccel:calvin/institutes#iii.i-p1",
            ["Ps.23.1"],
        )
    )
    database = tmp_path / "arg.sqlite3"
    import_theology_sqlite(document=document, database_path=database)
    hit = TheologyRepository(database).chunks_for_passage("Ps.23.1")[0]
    assert "Argument" in hit.human_readable_locator
    assert "Chapter 99" not in hit.human_readable_locator


def test_missing_and_invalid_database_are_fail_closed(tmp_path: Path) -> None:
    missing = TheologyRepository(tmp_path / "missing.sqlite3")
    assert missing.chunks_for_passage("John.3.16") == []
    assert missing.search_text("justification") == []

    broken = tmp_path / "broken.sqlite3"
    broken.write_text("not a sqlite database", encoding="utf-8")
    invalid = TheologyRepository(broken)
    assert invalid.store_status().available is False
    assert invalid.chunks_for_passage("John.3.16") == []
    assert invalid.search_text("justification") == []

    empty = tmp_path / "empty.sqlite3"
    create_empty_theology_database(empty)
    empty_repo = TheologyRepository(empty)
    assert empty_repo.store_status().available is True
    assert empty_repo.chunks_for_passage("John.3.16") == []
    assert empty_repo.search_text("justification") == []
