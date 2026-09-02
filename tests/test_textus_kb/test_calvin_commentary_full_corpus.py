"""Full 45-volume Calvin commentary corpus: manifest-driven, multi-work build.

Gated on ALL 45 raw XML files being present locally (``data/raw/`` is
gitignored — fetch with
``python scripts/build_commentary_database.py --calvin-fetch``). Complements
``test_calvin_commentary_pilot.py`` (which only exercises Romans + Harmony
directly) by proving the *manifest-driven*, multi-volume-work-grouped
orchestration (``import_calvin_corpus_from_manifest``) holds up across the
complete real corpus: 45 files, 23 logical works, ~14,000 sections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.calvin_source_fetch import load_source_manifest
from textus_kb.importers.calvin_commentary_thml import import_calvin_corpus_from_manifest
from textus_kb.qa.commentary_corpus_qa import generate_commentary_corpus_qa
from textus_kb.repositories.commentary_repository import CommentaryRepository

_RAW_DIR = Path("data/raw/calvin")
_ALL_MANIFEST_ENTRIES = load_source_manifest()
_ALL_RAW_PRESENT = all(entry.local_path.is_file() for entry in _ALL_MANIFEST_ENTRIES)

pytestmark = pytest.mark.skipif(
    not _ALL_RAW_PRESENT,
    reason=(
        "Not all 45 real Calvin ThML sources are present locally. Fetch with: "
        "python scripts/build_commentary_database.py --calvin-fetch"
    ),
)


@pytest.fixture(scope="module")
def full_corpus_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("calvin_full_corpus") / "commentary.sqlite3"
    import_calvin_corpus_from_manifest(_ALL_MANIFEST_ENTRIES, database_path=database)
    return database


@pytest.fixture(scope="module")
def full_corpus_repo(full_corpus_db: Path) -> CommentaryRepository:
    return CommentaryRepository(full_corpus_db)


def test_full_corpus_scale(full_corpus_repo: CommentaryRepository) -> None:
    status = full_corpus_repo.store_status()
    assert status.available is True
    assert status.work_count == 23
    assert status.edition_count == 45
    assert status.source_file_count == 45
    assert status.import_batch_count == 45
    assert status.section_count > 14000
    assert status.chunk_count > 11000
    assert status.passage_link_count > 14000


def test_full_corpus_manifest_known_unmapped_sections_are_all_flagged(
    full_corpus_db: Path,
) -> None:
    """Every source with an explicit known_unmapped_div2_ids entry in the
    manifest actually produced that many passage-less flagged sections —
    proving the exception mechanism fired for exactly the audited cases,
    not silently more or fewer. (A manifest entry that stops firing because
    a later parser fix now resolves it cleanly should be removed from the
    manifest, not left as stale/unused — see calcom11's removed entry.)"""
    total_expected = sum(
        len(entry.known_unmapped_div2_ids) for entry in _ALL_MANIFEST_ENTRIES
    )
    report = generate_commentary_corpus_qa(full_corpus_db)
    unmapped_count = report.passageless_sections_by_type.get(
        "commentary_passage_unmapped", 0
    )
    assert unmapped_count == total_expected > 0


def test_full_corpus_qa_is_clean(full_corpus_db: Path) -> None:
    report = generate_commentary_corpus_qa(full_corpus_db)
    assert report.available is True
    assert report.orphan_sections == []
    assert report.invalid_references == []
    assert report.duplicate_section_ids == []
    assert report.duplicate_chunk_ids == []
    assert report.duplicate_passage_links == []
    assert report.cross_edition_hierarchy_issues == []
    assert report.hierarchy_cycle_sections == []
    assert report.cross_reference_count_stored == 0


def test_full_corpus_multi_volume_work_is_unified(
    full_corpus_repo: CommentaryRepository,
) -> None:
    """Psalms (5 volumes/editions) is one work; a query lands in the
    correct volume and the work_id filter finds it regardless of which
    edition holds the section."""
    hits = full_corpus_repo.sections_for_passage(
        "Psalms.119.105", work_id="ccel.calvin.work.psalms"
    )
    assert hits, "Psalm 119 must be reachable through the shared psalms work_id"
    assert all(h.work_title == "Commentary on the Book of Psalms" for h in hits)


# --- Retrieval smoke: one example per requested biblical category --------


@pytest.mark.parametrize(
    ("label", "reference", "expect_book_prefix"),
    [
        ("Pentateuch exact", "Genesis.1.1", "Gen."),
        ("Pentateuch range (Harmony of the Law)", "Deuteronomy.6.4-9", "Deut."),
        ("Psalms exact", "Psalms.23.1", "Ps."),
        ("Prophets range (Isaiah)", "Isaiah.53.4-6", "Isa."),
        ("Prophets exact (Jeremiah)", "Jeremiah.31.31", "Jer."),
        ("Acts exact", "Acts.2.1", "Acts."),
        ("Pauline range (Romans)", "Romans.8.28-30", "Rom."),
        ("Catholic epistles (James)", "James.1.1", "Jas."),
        ("Catholic epistles (1 John)", "1John.1.1", "1John."),
    ],
)
def test_full_corpus_retrieval_smoke(
    full_corpus_repo: CommentaryRepository, label: str, reference: str, expect_book_prefix: str
) -> None:
    hits = full_corpus_repo.sections_for_passage(reference)
    assert hits, f"{label}: expected at least one hit for {reference}"
    assert all(
        p.startswith(expect_book_prefix) for h in hits for p in h.canonical_passages
    ), f"{label}: cross-book leak in results for {reference}"


def test_full_corpus_harmony_multi_passage_reachable_both_ways(
    full_corpus_repo: CommentaryRepository,
) -> None:
    via_matthew = {h.section_id for h in full_corpus_repo.sections_for_passage("Matthew.1.1-17")}
    via_luke = {h.section_id for h in full_corpus_repo.sections_for_passage("Luke.3.23-38")}
    shared = via_matthew & via_luke
    assert shared, "the same Harmony section must be reachable via either passage"


@pytest.mark.parametrize("reference", ["Judges.1.1", "Esther.1.1", "Ruth.1.1"])
def test_full_corpus_negative_no_commentary_for_book(
    full_corpus_repo: CommentaryRepository, reference: str
) -> None:
    """Calvin wrote no commentary on Judges/Esther/Ruth; the corpus must
    not fabricate a hit for them."""
    assert full_corpus_repo.sections_for_passage(reference) == []
