"""Read-only Commentary repository tests: ranking, provenance, fail-closed."""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
from textus_kb.repositories.commentary_repository import (
    RELATION_BROADER_CONTEXT,
    RELATION_CONTAINING_SECTION,
    RELATION_EXACT_PASSAGE,
    RELATION_PARTIAL_OVERLAP,
    CommentaryChunkResult,
    CommentaryRepository,
)

FIXTURE_PATH = Path("tests/fixtures/kb/commentary_v1_sample.json")


@pytest.fixture()
def repo(tmp_path: Path) -> CommentaryRepository:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    return CommentaryRepository(database)


def _by_section(results):
    return {r.section_id: r for r in results}


def test_store_status_available(repo: CommentaryRepository) -> None:
    status = repo.store_status()
    assert status.available is True
    assert status.section_count == 6
    assert status.chunk_count == 8


# --- Exact / range-overlap ranking ----------------------------------------


def test_exact_verse_retrieval(repo: CommentaryRepository) -> None:
    results = repo.sections_for_passage("John.3.16")
    by_id = _by_section(results)

    assert by_id["test.section.john316_exact"].relation_type == RELATION_EXACT_PASSAGE
    assert by_id["test.section.multi_passage"].relation_type == RELATION_EXACT_PASSAGE
    assert by_id["test.section.john316_21_range"].relation_type == RELATION_CONTAINING_SECTION
    assert by_id["test.section.chapter3"].relation_type == RELATION_CONTAINING_SECTION
    assert "test.section.crossing" not in by_id
    assert "test.section.book" not in by_id


def test_deterministic_ranking_order(repo: CommentaryRepository) -> None:
    """Exact tier first, then containing tier by narrowest span, ties broken by document order."""
    results = repo.sections_for_passage("John.3.16")
    ordered_ids = [r.section_id for r in results]
    assert ordered_ids == [
        "test.section.john316_exact",
        "test.section.multi_passage",
        "test.section.john316_21_range",
        "test.section.chapter3",
    ]
    # Repeated calls must produce the identical order (no hidden nondeterminism).
    again = [r.section_id for r in repo.sections_for_passage("John.3.16")]
    assert again == ordered_ids


def test_multi_verse_range_retrieval(repo: CommentaryRepository) -> None:
    """A verse inside a range section, with no exact link, ranks by narrowest containing span."""
    results = repo.sections_for_passage("John.3.18")
    ordered_ids = [r.section_id for r in results]
    assert ordered_ids == [
        "test.section.john316_21_range",
        "test.section.chapter3",
    ]
    for result in results:
        assert result.relation_type == RELATION_CONTAINING_SECTION


def test_partial_overlap_relation(repo: CommentaryRepository) -> None:
    results = repo.sections_for_passage("John 3:35-4:5")
    by_id = _by_section(results)
    assert by_id["test.section.crossing"].relation_type == RELATION_PARTIAL_OVERLAP
    assert all(r.relation_type != RELATION_EXACT_PASSAGE for r in results)


def test_multi_passage_section_reports_only_overlapping_links(
    repo: CommentaryRepository,
) -> None:
    results = repo.sections_for_passage("John.4.1-6")
    by_id = _by_section(results)
    hit = by_id["test.section.multi_passage"]
    assert hit.relation_type == RELATION_EXACT_PASSAGE
    assert hit.canonical_passages == ("John.4.1-6",)


def test_no_hits_for_unrelated_passage(repo: CommentaryRepository) -> None:
    assert repo.sections_for_passage("Genesis.1.1") == []


def test_work_id_filter(repo: CommentaryRepository) -> None:
    hits = repo.sections_for_passage(
        "John.3.16", work_id="test.work.synthetic_commentary"
    )
    assert len(hits) == 4

    none_hits = repo.sections_for_passage("John.3.16", work_id="unknown.work")
    assert none_hits == []


def test_section_result_carries_contributors_and_rights(
    repo: CommentaryRepository,
) -> None:
    results = repo.sections_for_passage("John.3.16")
    hit = _by_section(results)["test.section.john316_exact"]
    assert hit.work_title == "Synthetic Commentary on John"
    assert "Synthetic Commentary Author (author)" in hit.contributors
    assert "Synthetic Commentary Translator (translator)" in hit.contributors
    assert hit.license == "CC-BY-4.0"
    assert hit.rights_status == "public-domain"
    assert hit.chunk_count == 1


# --- section_detail ---------------------------------------------------


def test_section_detail_returns_ordered_chunks(repo: CommentaryRepository) -> None:
    detail = repo.section_detail("test.section.chapter3")
    assert detail is not None
    assert [c.chunk_id for c in detail.chunks] == [
        "test.chunk.chapter3_part1",
        "test.chunk.chapter3_part2",
        "test.chunk.chapter3_part3",
    ]
    assert "GAMMA MARKER PART ONE" in detail.chunks[0].plain_text
    assert detail.canonical_passages == ("John.3.1-36",)
    assert detail.parent_chain == (("test.section.book", "Commentary on the Gospel of John (synthetic)"),)


def test_section_detail_missing_returns_none(repo: CommentaryRepository) -> None:
    assert repo.section_detail("unknown.section") is None


def test_section_detail_multi_passage_section(repo: CommentaryRepository) -> None:
    detail = repo.section_detail("test.section.multi_passage")
    assert detail is not None
    assert set(detail.canonical_passages) == {"John.4.1-6", "John.3.16"}


# --- broader_context (explicit opt-in only) --------------------------------


def test_broader_context_climbs_one_level(repo: CommentaryRepository) -> None:
    results = repo.broader_context("test.section.john316_exact", levels=1)
    assert [r.section_id for r in results] == ["test.section.chapter3"]
    assert results[0].relation_type == RELATION_BROADER_CONTEXT


def test_broader_context_climbs_two_levels_root_first(repo: CommentaryRepository) -> None:
    results = repo.broader_context("test.section.john316_exact", levels=2)
    assert [r.section_id for r in results] == [
        "test.section.book",
        "test.section.chapter3",
    ]


def test_broader_context_root_section_has_no_ancestors(repo: CommentaryRepository) -> None:
    assert repo.broader_context("test.section.book", levels=5) == []


def test_broader_context_unknown_section(repo: CommentaryRepository) -> None:
    assert repo.broader_context("unknown.section") == []


def test_sections_for_passage_never_falls_back_to_broader_context(
    repo: CommentaryRepository,
) -> None:
    """A passage with zero direct/overlapping hits must return empty, not ancestors."""
    assert repo.sections_for_passage("Genesis.1.1") == []


# --- Secondary FTS ----------------------------------------------------------


def test_search_text_finds_section_by_aggregated_chunk_text(
    repo: CommentaryRepository,
) -> None:
    hits = repo.search_text("GAMMA MARKER")
    assert any(hit.section_id == "test.section.chapter3" for hit in hits)


def test_search_text_finds_single_chunk_section(repo: CommentaryRepository) -> None:
    hits = repo.search_text("DELTA MARKER")
    assert len(hits) == 1
    assert hits[0].section_id == "test.section.john316_exact"
    assert "**" in hits[0].snippet
    assert hits[0].canonical_passages == ("John.3.16",)


def test_search_text_empty_query_returns_empty(repo: CommentaryRepository) -> None:
    assert repo.search_text("") == []
    assert repo.search_text("   ") == []


def test_search_text_is_independent_of_passage_retrieval(
    repo: CommentaryRepository,
) -> None:
    """FTS and passage retrieval are separate codepaths: a phrase absent from
    every chunk finds nothing via FTS, while the dedicated passage API still
    finds John.3.16 by its structured passage link, not by text search."""
    assert repo.search_text("nonexistent xyzzy marker phrase") == []
    assert repo.sections_for_passage("John.3.16") != []


# --- Fail-closed --------------------------------------------------------


def test_missing_database_is_fail_closed(tmp_path: Path) -> None:
    repo = CommentaryRepository(tmp_path / "missing.sqlite3")
    assert repo.store_status().available is False
    assert repo.sections_for_passage("John.3.16") == []
    assert repo.section_detail("test.section.book") is None
    assert repo.broader_context("test.section.book") == []
    assert repo.search_text("gamma") == []


def test_invalid_database_is_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "broken.sqlite3"
    path.write_text("not a sqlite database", encoding="utf-8")
    repo = CommentaryRepository(path)
    assert repo.store_status().available is False
    assert repo.sections_for_passage("John.3.16") == []


def test_unparseable_reference_returns_empty(repo: CommentaryRepository) -> None:
    assert repo.sections_for_passage("Not A Real Reference") == []


# --- Regression: passage truth lives on the section, not the chunk --------


def test_chunk_result_model_has_no_passage_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(CommentaryChunkResult)}
    assert not any("passage" in name for name in field_names)
    assert not any("book_id" in name or "chapter" in name or "verse" in name for name in field_names)


def test_passage_retrieval_result_derives_from_section_links_only(
    tmp_path: Path,
) -> None:
    """Corrupting chunk text must not change which sections match a passage,
    and clearing section_passage_links must remove the section from results —
    proving section_passage_links, not chunk content, is the source of truth."""
    database = tmp_path / "corrupt_chunks.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE chunks SET plain_text = 'irrelevant corrupted text', text = 'irrelevant corrupted text'"
        )
        connection.commit()
    corrupted_repo = CommentaryRepository(database)
    corrupted_results = {r.section_id for r in corrupted_repo.sections_for_passage("John.3.16")}
    assert corrupted_results == {
        "test.section.john316_exact",
        "test.section.multi_passage",
        "test.section.john316_21_range",
        "test.section.chapter3",
    }

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM section_passage_links WHERE section_id = 'test.section.john316_exact'"
        )
        connection.commit()
    after_delete = {r.section_id for r in corrupted_repo.sections_for_passage("John.3.16")}
    assert "test.section.john316_exact" not in after_delete
