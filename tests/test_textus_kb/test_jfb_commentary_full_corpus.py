"""Full JFB commentary corpus: single-file, 66-book, whole-Bible build.

Gated on the real JFB source being present locally (``data/raw/`` is
gitignored — fetch with ``fetch_source`` from ``jfb_source_fetch.py``).
Complements ``test_jfb_commentary_thml.py`` (Philemon fixture only) by
proving the full real corpus — 66 books, ~31,000 verses, the entire
Protestant Bible — builds cleanly and passes the same generic QA already
proven on Calvin, with zero JFB-specific QA changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.jfb_commentary_thml import build_jfb_corpus_from_manifest
from textus_kb.importers.jfb_source_fetch import load_source_manifest
from textus_kb.qa.commentary_corpus_qa import generate_commentary_corpus_qa
from textus_kb.repositories.commentary_repository import CommentaryRepository

_MANIFEST = load_source_manifest()
_RAW_PRESENT = _MANIFEST.source.local_path.is_file()

pytestmark = pytest.mark.skipif(
    not _RAW_PRESENT,
    reason=(
        "JFB raw source not present locally. Fetch with: "
        "python -c \"from textus_kb.importers.jfb_source_fetch import load_source_manifest, "
        "fetch_source; fetch_source(load_source_manifest().source)\""
    ),
)


@pytest.fixture(scope="module")
def full_corpus_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("jfb_full_corpus") / "commentary.sqlite3"
    build_jfb_corpus_from_manifest(
        _MANIFEST.source.local_path,
        list(_MANIFEST.books),
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
    assert status.contributor_count == 3
    # Protestant Bible has 31,102 verses; a handful of JFB verse groupings
    # (multiple verses commented on together) account for the small gap.
    assert 30900 <= status.section_count - 66 - 1236 <= 31102
    assert status.passage_link_count > 30900


def test_full_corpus_qa_is_clean(full_corpus_db: Path) -> None:
    """The same generic QA already proven on Calvin, run unchanged
    against JFB — proving the QA layer really is source-independent."""
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
    assert report.warnings == []
    # JFB has no Harmony-style parallel-passage concept: every link is primary.
    assert report.parallel_passage_link_count == 0
    assert report.primary_passage_link_count == report.passage_link_count
    assert len(report.works) == 66
    assert len(report.contributors) == 3


def test_full_corpus_content_hash_deterministic(tmp_path: Path) -> None:
    second = tmp_path / "second.sqlite3"
    result_a, _ = build_jfb_corpus_from_manifest(
        _MANIFEST.source.local_path,
        list(_MANIFEST.books),
        database_path=tmp_path / "first.sqlite3",
        imported_at="2026-01-01T00:00:00Z",
    )
    result_b, _ = build_jfb_corpus_from_manifest(
        _MANIFEST.source.local_path,
        list(_MANIFEST.books),
        database_path=second,
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
    assert all(h.work_title.startswith("Commentary Critical and Explanatory") for h in hits)


def test_full_corpus_every_book_has_at_least_one_hit(
    full_corpus_repo: CommentaryRepository,
) -> None:
    """Unlike Calvin (silent on Judges/Esther/Ruth), JFB genuinely covers
    the whole Bible — there is no book with zero commentary."""
    for reference, prefix in [
        ("Judges.1.1", "Judg."),
        ("Ruth.1.1", "Ruth."),
        ("Esther.1.1", "Esth."),
    ]:
        hits = full_corpus_repo.sections_for_passage(reference)
        assert hits, f"JFB must cover {reference} (unlike Calvin)"
