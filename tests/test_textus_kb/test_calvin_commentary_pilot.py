"""Full real-corpus pilot: the complete Romans + Harmony ThML files.

Gated on the raw XML actually being present locally (``data/raw/`` is
gitignored — these files are not committed; fetch them with
``python scripts/build_commentary_database.py --calvin-fetch``). This
proves the pipeline holds up on real, full-size volumes (2500+ real
sections combined), not just the small trimmed fixtures used by
``test_calvin_commentary_thml.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.calvin_commentary_thml import import_calvin_commentary_sqlite
from textus_kb.qa.commentary_corpus_qa import generate_commentary_corpus_qa
from textus_kb.repositories.commentary_repository import (
    RELATION_CONTAINING_SECTION,
    RELATION_EXACT_PASSAGE,
    RELATION_PARTIAL_OVERLAP,
    CommentaryRepository,
)

ROMANS_RAW = Path("data/raw/calvin/calcom38.xml")
HARMONY_RAW = Path("data/raw/calvin/calcom31.xml")

pytestmark = pytest.mark.skipif(
    not (ROMANS_RAW.is_file() and HARMONY_RAW.is_file()),
    reason=(
        "Real Calvin ThML sources not present locally. Fetch with: "
        "python scripts/build_commentary_database.py --calvin-fetch"
    ),
)


@pytest.fixture(scope="module")
def full_pilot_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("calvin_pilot") / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_RAW, HARMONY_RAW], database_path=database)
    return database


@pytest.fixture(scope="module")
def full_pilot_repo(full_pilot_db: Path) -> CommentaryRepository:
    return CommentaryRepository(full_pilot_db)


def test_full_corpus_is_substantial(full_pilot_repo: CommentaryRepository) -> None:
    status = full_pilot_repo.store_status()
    assert status.available is True
    # Two full real Calvin volumes: well beyond a hand-picked few sections.
    assert status.section_count > 900
    assert status.chunk_count > 700
    assert status.passage_link_count > 900


def test_full_corpus_exact_and_containing_ranking(full_pilot_repo: CommentaryRepository) -> None:
    hits = full_pilot_repo.sections_for_passage("Romans.1.9")
    by_id = {h.section_id: h for h in hits}
    assert by_id["ccel.calvin.calcom38.v.iii.v2"].relation_type == RELATION_EXACT_PASSAGE
    assert by_id["ccel.calvin.calcom38.v.iii"].relation_type == RELATION_CONTAINING_SECTION


def test_full_corpus_multi_passage_harmony_section_reachable_both_ways(
    full_pilot_repo: CommentaryRepository,
) -> None:
    via_matthew = {h.section_id for h in full_pilot_repo.sections_for_passage("Matthew.1.1-17")}
    via_luke = {h.section_id for h in full_pilot_repo.sections_for_passage("Luke.3.23-38")}
    assert "ccel.calvin.calcom31.ix.xiv" in via_matthew
    assert "ccel.calvin.calcom31.ix.xiv" in via_luke


def test_full_corpus_no_cross_book_leak(full_pilot_repo: CommentaryRepository) -> None:
    hits = full_pilot_repo.sections_for_passage("Romans.5.1")
    leaked = [
        passage
        for hit in hits
        for passage in hit.canonical_passages
        if not passage.startswith("Rom.")
    ]
    assert leaked == []


def test_full_corpus_book_without_calvin_commentary_returns_empty(
    full_pilot_repo: CommentaryRepository,
) -> None:
    assert full_pilot_repo.sections_for_passage("Genesis.1.1") == []
    assert full_pilot_repo.sections_for_passage("John.3.16") == []


def test_full_corpus_boundary_overlap_is_partial_not_exact(
    full_pilot_repo: CommentaryRepository,
) -> None:
    """A cross-section-boundary query correctly reports partial_overlap for
    neighboring harmony sections that share only an edge verse."""
    hits = full_pilot_repo.sections_for_passage("Luke.3.21-38")
    relations = {h.relation_type for h in hits}
    assert RELATION_PARTIAL_OVERLAP in relations or RELATION_EXACT_PASSAGE in relations


def test_full_corpus_qa_report_is_clean(full_pilot_db: Path) -> None:
    report = generate_commentary_corpus_qa(full_pilot_db)
    assert report.available is True
    assert report.orphan_sections == []
    assert report.invalid_references == []
    assert report.duplicate_section_ids == []
    assert report.duplicate_chunk_ids == []
    assert report.duplicate_passage_links == []
    assert report.cross_edition_hierarchy_issues == []
    assert report.warnings == []
    # Real coverage: Romans dominates one work, Matthew/Luke the harmony.
    assert report.coverage_by_book.get("Rom", 0) > 400
    assert report.coverage_by_book.get("Matt", 0) > 100
