"""Full Matthew Henry commentary corpus: 6 volumes, 66 books, whole-Bible build.

Gated on the real 6 CCEL volume files being present locally (``data/raw/``
is gitignored — fetch with ``fetch_all_volumes`` from
``henry_source_fetch.py``). Complements ``test_henry_commentary_thml.py``
(Obadiah fixture only) by proving the full real corpus builds cleanly,
passes the same generic QA already proven on Calvin and JFB with zero
Henry-specific QA changes, and that the real per-book authorship (Henry
himself vs. 14 named posthumous continuators) survives into the store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.henry_commentary_thml import build_henry_corpus_from_manifest
from textus_kb.importers.henry_source_fetch import load_source_manifest
from textus_kb.qa.commentary_corpus_qa import generate_commentary_corpus_qa
from textus_kb.repositories.commentary_repository import CommentaryRepository

_MANIFEST = load_source_manifest()
_RAW_PRESENT = all(v.local_path.is_file() for v in _MANIFEST.volumes)

pytestmark = pytest.mark.skipif(
    not _RAW_PRESENT,
    reason=(
        "Henry raw volumes not present locally. Fetch with: "
        "python -c \"from textus_kb.importers.henry_source_fetch import load_source_manifest, "
        "fetch_all_volumes; fetch_all_volumes()\""
    ),
)


@pytest.fixture(scope="module")
def full_corpus_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("henry_full_corpus") / "commentary.sqlite3"
    build_henry_corpus_from_manifest(
        _MANIFEST,
        database_path=database,
        imported_at="2026-01-01T00:00:00Z",
    )
    return database


@pytest.fixture(scope="module")
def full_corpus_repo(full_corpus_db: Path) -> CommentaryRepository:
    return CommentaryRepository(full_corpus_db)


def test_full_corpus_scale(full_corpus_repo: CommentaryRepository) -> None:
    status = full_corpus_repo.store_status()
    assert status.available is True
    assert status.work_count == 66
    assert status.edition_count == 66
    assert status.source_file_count == 66
    assert status.import_batch_count == 66
    # Matthew Henry himself + 14 named posthumous continuators.
    assert status.contributor_count == 15
    # 66 book + 1255 chapter + 4258 range sections.
    assert status.section_count == 5579
    assert status.passage_link_count == 4258
    assert status.chunk_count == 5512


def test_full_corpus_qa_is_clean(full_corpus_db: Path) -> None:
    """The same generic QA already proven on Calvin and JFB, run unchanged
    against Henry — proving the QA layer really is source-independent."""
    report = generate_commentary_corpus_qa(full_corpus_db)
    assert report.available is True
    assert report.orphan_sections == []
    assert report.invalid_references == []
    assert report.duplicate_section_ids == []
    assert report.duplicate_chunk_ids == []
    assert report.duplicate_passage_links == []
    assert report.cross_edition_hierarchy_issues == []
    assert report.hierarchy_cycle_sections == []
    assert report.invalid_relation_types == []
    assert report.cross_reference_count_stored == 0
    # Henry's 5 one-chapter books (Obadiah, Philemon, 2 John, 3 John, Jude)
    # are short enough to trip the generic "< 5 passage links per source
    # file" heuristic warning — expected given their real length, not a
    # data-quality problem. No other warnings are expected.
    assert len(report.warnings) == 1
    assert "< 5 passage link" in report.warnings[0]
    # Henry has no Harmony-style parallel-passage concept: every link is primary.
    assert report.parallel_passage_link_count == 0
    assert report.primary_passage_link_count == report.passage_link_count
    assert len(report.works) == 66
    assert len(report.contributors) == 15
    # The 5 documented one-chapter-book "duplicate empty marker" exceptions,
    # surfaced via the exact same known_unmapped_sections QA key Calvin uses.
    assert len(report.known_unmapped) == 5
    classifications = {item.get("classification") for item in report.known_unmapped}
    assert classifications == {"duplicate_empty_marker"}


def test_full_corpus_content_hash_deterministic(tmp_path: Path) -> None:
    result_a, _ = build_henry_corpus_from_manifest(
        _MANIFEST,
        database_path=tmp_path / "first.sqlite3",
        imported_at="2026-01-01T00:00:00Z",
    )
    result_b, _ = build_henry_corpus_from_manifest(
        _MANIFEST,
        database_path=tmp_path / "second.sqlite3",
        imported_at="2099-12-31T23:59:59Z",
    )
    assert result_a.content_hash == result_b.content_hash


@pytest.mark.parametrize(
    ("label", "reference", "expect_book_prefix"),
    [
        ("Pentateuch exact", "Genesis.1.1", "Gen."),
        ("Historical books", "Joshua.1.1", "Josh."),
        ("Poetical - Psalms", "Psalms.23.1", "Ps."),
        ("Prophetic - Isaiah", "Isaiah.53.5", "Isa."),
        ("Minor prophet", "Obadiah.1.1", "Obad."),
        ("Gospel - Matthew", "Matthew.1.1", "Matt."),
        ("Acts", "Acts.2.1", "Acts."),
        ("Pauline - Romans", "Romans.8.28", "Rom."),
        ("General epistle - James", "James.1.1", "Jas."),
        ("Revelation", "Revelation.1.1", "Rev."),
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
    assert all(h.work_title.startswith("Matthew Henry's Commentary") for h in hits)


def test_full_corpus_every_book_has_at_least_one_hit(
    full_corpus_repo: CommentaryRepository,
) -> None:
    for reference, prefix in [
        ("Judges.1.1", "Judg."),
        ("Ruth.1.1", "Ruth."),
        ("Esther.1.1", "Esth."),
        ("2John.1.1", "2John."),
        ("3John.1.1", "3John."),
        ("Jude.1.1", "Jude."),
        ("Philemon.1.1", "Phlm."),
    ]:
        hits = full_corpus_repo.sections_for_passage(reference)
        assert hits, f"Henry must cover {reference} (including all 5 one-chapter books)"


def test_acts_attributed_to_matthew_henry(full_corpus_repo: CommentaryRepository) -> None:
    """Real corpus finding: despite living in the mhc6.xml file alongside
    the posthumous continuators, Acts was originally part of Henry's own
    Matthew-Acts manuscript and must be attributed to him, not to a
    continuator."""
    hits = full_corpus_repo.sections_for_passage("Acts.2.1")
    assert hits
    detail = full_corpus_repo.section_detail(hits[0].section_id)
    assert detail is not None
    assert any(name.startswith("Matthew Henry") for name in detail.contributors)


@pytest.mark.parametrize(
    ("reference", "expected_contributor"),
    [
        ("Romans.1.1", "Mr. John Evans"),
        ("Hebrews.1.1", "Mr. William Tong"),
        ("Revelation.1.1", "Mr. William Tong"),
        ("1John.1.1", "Mr. John Reynolds"),
    ],
)
def test_posthumous_books_attributed_to_named_continuators(
    full_corpus_repo: CommentaryRepository, reference: str, expected_contributor: str
) -> None:
    """Real corpus finding (Volume VI's own preface table): books from
    Romans through Revelation are attributed to their real named
    continuing minister, never fabricated as Matthew Henry's own work."""
    hits = full_corpus_repo.sections_for_passage(reference)
    assert hits
    detail = full_corpus_repo.section_detail(hits[0].section_id)
    assert detail is not None
    names = set(detail.contributors)
    assert any(name.startswith(expected_contributor) for name in names)
    assert not any(name.startswith("Matthew Henry") for name in names)
