"""Commentary "Kommentárok" tab tests -- helper/smoke pattern.

``commentary_ui.py`` is a Streamlit UI module; per this repo's established
testing style (ld. ``tests/test_workshop_nav_ui.py``,
``tests/test_quick_tools_grid.py``, ``tests/test_textus_workshop_outline_
card_removed.py``) it is tested through its pure, no-``st.*`` helper
functions rather than a full Streamlit render -- ``render_commentary_
panel()`` itself is exercised implicitly by the session-wide AppTest-
sandboxed ``import app`` in ``tests/conftest.py`` (it would raise loudly on
any wiring/crash regression).

The fixture store below is a small, synthetic 3-source (Calvin-like/JFB-
like/Henry-like) Commentary DB built directly through the real, generic
``commentary_sqlite.import_commentary_sqlite`` -- not the production
store -- so these tests are fast, deterministic, and independent of
whether the real corpora have been fetched/built locally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import commentary_ui as cu
from textus_kb import commentary_runtime
from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
from textus_kb.repositories.commentary_repository import (
    CommentaryRepository,
    CommentarySectionResult,
)


def _edition(edition_id: str, work_id: str, corpus: str) -> dict:
    return {
        "edition_id": edition_id,
        "work_id": work_id,
        "edition_label": "Test edition",
        "publication_year": 1900,
        "publisher": "Textus Test",
        "language": "en",
        "license": "CC-BY-4.0",
        "rights_status": "public-domain",
        "rights_note": f"Synthetic {corpus} fixture; not a real commentary source.",
        "source_url": f"https://example.test/{corpus}",
        "corpus": corpus,
        "external_id": f"test/{corpus}",
    }


def _synthetic_document() -> dict:
    """Three synthetic sources on John 3 modeling the exact scenarios this
    round's requirements name: an exact-verse hit (JFB-like), a native
    multi-verse range hit (Henry-like), and a Harmony-style parallel-only
    hit (Calvin-like) -- so that John.3.16 has all three, John.3.20 has
    only two (no Calvin), John.3.18 has only the range source, and
    Genesis.1.1 has none."""
    return {
        "contributors": [
            {"contributor_id": "test.calvin", "canonical_name": "Test Calvin", "birth_year": 1509, "death_year": 1564},
            {"contributor_id": "test.jfb", "canonical_name": "Test JFB", "birth_year": 1800, "death_year": 1880},
            {"contributor_id": "test.henry", "canonical_name": "Test Henry", "birth_year": 1662, "death_year": 1714},
        ],
        "works": [
            {"work_id": "test.work.calvin", "title": "Test Calvin Commentary on John", "original_title": None, "original_language": "la", "work_type": "commentary"},
            {"work_id": "test.work.jfb", "title": "Test JFB Commentary on John", "original_title": None, "original_language": "en", "work_type": "commentary"},
            {"work_id": "test.work.henry", "title": "Test Henry Commentary on John", "original_title": None, "original_language": "en", "work_type": "commentary"},
        ],
        "work_contributors": [
            {"work_id": "test.work.calvin", "contributor_id": "test.calvin", "role": "author"},
            {"work_id": "test.work.jfb", "contributor_id": "test.jfb", "role": "author"},
            {"work_id": "test.work.henry", "contributor_id": "test.henry", "role": "author"},
        ],
        "editions": [
            _edition("test.edition.calvin", "test.work.calvin", "test-calvin"),
            _edition("test.edition.jfb", "test.work.jfb", "test-jfb"),
            _edition("test.edition.henry", "test.work.henry", "test-henry"),
        ],
        "source_files": [
            {"source_file_id": "test.sf.calvin", "edition_id": "test.edition.calvin", "file_name": "calvin.xml", "raw_sha256": "a" * 64, "byte_size": 10, "retrieved_at": "2026-08-01T00:00:00Z"},
            {"source_file_id": "test.sf.jfb", "edition_id": "test.edition.jfb", "file_name": "jfb.xml", "raw_sha256": "b" * 64, "byte_size": 10, "retrieved_at": "2026-08-01T00:00:00Z"},
            {"source_file_id": "test.sf.henry", "edition_id": "test.edition.henry", "file_name": "henry.xml", "raw_sha256": "c" * 64, "byte_size": 10, "retrieved_at": "2026-08-01T00:00:00Z"},
        ],
        "import_batches": [
            {"batch_id": "test.batch.calvin", "source_file_id": "test.sf.calvin", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-08-01T00:05:00Z", "report": {}},
            {"batch_id": "test.batch.jfb", "source_file_id": "test.sf.jfb", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-08-01T00:05:00Z", "report": {}},
            {"batch_id": "test.batch.henry", "source_file_id": "test.sf.henry", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-08-01T00:05:00Z", "report": {}},
        ],
        "sections": [
            {"section_id": "test.calvin.harmony", "edition_id": "test.edition.calvin", "parent_section_id": None, "section_type": "section", "heading": "Calvin Harmony note (synthetic)", "sequence": 1, "passage_links": [{"raw_citation": "John 3:16", "relation_type": "parallel"}]},
            {"section_id": "test.jfb.exact", "edition_id": "test.edition.jfb", "parent_section_id": None, "section_type": "section", "heading": "JFB on John 3:16 (synthetic)", "sequence": 1, "passage_links": [{"raw_citation": "John 3:16", "relation_type": "primary"}]},
            {"section_id": "test.jfb.exact20", "edition_id": "test.edition.jfb", "parent_section_id": None, "section_type": "section", "heading": "JFB on John 3:20 (synthetic)", "sequence": 2, "passage_links": [{"raw_citation": "John 3:20", "relation_type": "primary"}]},
            {"section_id": "test.henry.range", "edition_id": "test.edition.henry", "parent_section_id": None, "section_type": "range_commentary", "heading": "Henry on John 3:16-21 (synthetic)", "sequence": 1, "passage_links": [{"raw_citation": "John 3:16-21", "relation_type": "primary"}]},
        ],
        "chunks": [
            {"chunk_id": "test.chunk.calvin.harmony", "section_id": "test.calvin.harmony", "sequence": 1, "text": "SYNTH CALVIN HARMONY MARKER", "plain_text": "SYNTH CALVIN HARMONY MARKER", "source_locator": "fixture://calvin/1"},
            {"chunk_id": "test.chunk.jfb.exact", "section_id": "test.jfb.exact", "sequence": 1, "text": "SYNTH JFB EXACT MARKER", "plain_text": "SYNTH JFB EXACT MARKER", "source_locator": "fixture://jfb/1"},
            {"chunk_id": "test.chunk.jfb.exact20", "section_id": "test.jfb.exact20", "sequence": 1, "text": "SYNTH JFB V20 MARKER", "plain_text": "SYNTH JFB V20 MARKER", "source_locator": "fixture://jfb/2"},
            {"chunk_id": "test.chunk.henry.range.1", "section_id": "test.henry.range", "sequence": 1, "text": "SYNTH HENRY RANGE MARKER PART ONE", "plain_text": "SYNTH HENRY RANGE MARKER PART ONE", "source_locator": "fixture://henry/1"},
            {"chunk_id": "test.chunk.henry.range.2", "section_id": "test.henry.range", "sequence": 2, "text": "SYNTH HENRY RANGE MARKER PART TWO", "plain_text": "SYNTH HENRY RANGE MARKER PART TWO", "source_locator": "fixture://henry/2"},
        ],
    }


@pytest.fixture(scope="module")
def synthetic_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("commentary_ui_synth") / "commentary.sqlite3"
    import_commentary_sqlite(document=_synthetic_document(), database_path=database)
    return database


@pytest.fixture()
def patched_repo(synthetic_db: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect commentary_ui's repository seam at the synthetic store."""
    monkeypatch.setattr(cu, "_get_repository", lambda: CommentaryRepository(synthetic_db))
    return synthetic_db


@pytest.fixture()
def patched_available_status(patched_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cu, "_get_status", lambda: commentary_runtime.get_status(patched_repo))


# --- valid store / three-source + range/harmony retrieval ---------------


def test_valid_store_returns_all_three_sources_for_exact_hit(patched_repo: Path) -> None:
    results = cu._fetch_results("John.3.16")
    work_ids = {r.work_id for r in results}
    assert work_ids == {"test.work.calvin", "test.work.jfb", "test.work.henry"}


def test_range_result_is_containing_section_tier_with_native_range_passage(
    patched_repo: Path,
) -> None:
    results = cu._fetch_results("John.3.16")
    henry = next(r for r in results if r.work_id == "test.work.henry")
    assert henry.relation_type == "containing_section"
    assert henry.primary_passages == ("John.3.16-21",)


def test_harmony_style_primary_vs_parallel_relation_key(patched_repo: Path) -> None:
    results = cu._fetch_results("John.3.16")
    by_work = {r.work_id: r for r in results}
    query_canonical = cu._query_canonical("John.3.16")
    assert cu._passage_relation_key(by_work["test.work.jfb"], query_canonical) == "primary"
    assert cu._passage_relation_key(by_work["test.work.calvin"], query_canonical) == "parallel"
    assert cu._passage_relation_key(by_work["test.work.henry"], query_canonical) == "primary"
    # Human-facing labels are explicitly non-ranking wording (2026-09-03
    # UI polish round: capitalized as standalone UI copy, ld. task item 6).
    assert cu._PASSAGE_RELATION_LABELS_HU["primary"] == "Fő kommentált hely"
    assert cu._PASSAGE_RELATION_LABELS_HU["parallel"] == "Párhuzamos evangéliumi hely"


def test_only_jfb_and_henry_when_calvin_has_no_link(patched_repo: Path) -> None:
    """Requirement: "csak JFB + Henry találat, ahol Calvin nincs"."""
    results = cu._fetch_results("John.3.20")
    work_ids = {r.work_id for r in results}
    assert work_ids == {"test.work.jfb", "test.work.henry"}
    assert "test.work.calvin" not in work_ids


def test_range_only_match_without_any_exact_source(patched_repo: Path) -> None:
    results = cu._fetch_results("John.3.18")
    assert len(results) == 1
    assert results[0].work_id == "test.work.henry"
    assert results[0].relation_type == "containing_section"


def test_no_match_returns_empty_list_not_fts_or_semantic_fallback(patched_repo: Path) -> None:
    results = cu._fetch_results("Genesis.1.1")
    assert results == []


# --- unavailable store / no passage --------------------------------------


def test_unavailable_store_status(tmp_path: Path) -> None:
    status = commentary_runtime.get_status(tmp_path / "does_not_exist.sqlite3")
    assert status.available is False
    assert status.reason == "database_missing"


def test_render_commentary_panel_checks_status_before_passage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The panel must fail closed on a missing/invalid DB even before
    looking at the passage -- proven by asserting the documented order of
    checks in render_commentary_panel's own source (status first)."""
    import inspect

    source = inspect.getsource(cu.render_commentary_panel)
    status_pos = source.index("_get_status()")
    passage_pos = source.index('session_state.get("last_igehely"')
    assert status_pos < passage_pos


# --- source filtering ------------------------------------------------


def test_sources_present_is_derived_not_hardcoded(patched_repo: Path) -> None:
    results = cu._fetch_results("John.3.16")
    sources = cu._sources_present(results)
    assert set(sources) == {"Test Calvin", "Test JFB", "Test Henry"}


def test_apply_source_filter_narrows_results(patched_repo: Path) -> None:
    results = cu._fetch_results("John.3.16")
    filtered = cu._apply_source_filter(results, {"Test JFB"})
    assert {r.work_id for r in filtered} == {"test.work.jfb"}


def test_apply_source_filter_all_disabled_yields_empty(patched_repo: Path) -> None:
    results = cu._fetch_results("John.3.16")
    filtered = cu._apply_source_filter(results, set())
    assert filtered == []


def test_primary_contributor_strips_role_suffix() -> None:
    assert cu._primary_contributor(("Mr. John Evans (author)",)) == "Mr. John Evans"
    assert cu._primary_contributor(()) == "Ismeretlen szerző"


# --- caching / passage change / manual refresh ---------------------------


def test_ensure_results_caches_per_passage_and_recomputes_on_change(
    patched_repo: Path,
) -> None:
    session: dict = {}
    first = cu._ensure_results("John.3.16", session=session)
    again = cu._ensure_results("John.3.16", session=session)
    assert again is first  # cached, no recompute

    changed = cu._ensure_results("John.3.20", session=session)
    assert changed is not first
    assert {r.work_id for r in changed} == {"test.work.jfb", "test.work.henry"}


def test_ensure_results_force_recomputes(patched_repo: Path) -> None:
    session: dict = {}
    first = cu._ensure_results("John.3.16", session=session)
    forced = cu._ensure_results("John.3.16", session=session, force=True)
    assert forced is not first
    assert {r.work_id for r in forced} == {r.work_id for r in first}


# --- full section detail data path (expand) -------------------------------


def test_section_detail_preserves_original_chunk_order(patched_repo: Path) -> None:
    repo = cu._get_repository()
    detail = repo.section_detail("test.henry.range")
    assert detail is not None
    assert [c.sequence for c in detail.chunks] == [1, 2]
    assert detail.chunks[0].plain_text == "SYNTH HENRY RANGE MARKER PART ONE"
    assert detail.chunks[1].plain_text == "SYNTH HENRY RANGE MARKER PART TWO"


def test_section_detail_shows_which_passage_it_covers(patched_repo: Path) -> None:
    repo = cu._get_repository()
    detail = repo.section_detail("test.henry.range")
    assert detail is not None
    assert detail.primary_passages == ("John.3.16-21",)


def test_section_detail_missing_id_returns_none(patched_repo: Path) -> None:
    repo = cu._get_repository()
    assert repo.section_detail("does.not.exist") is None


def test_chunk_previews_do_not_load_full_multi_chunk_section(patched_repo: Path) -> None:
    """The card preview must come from a lightweight first-chunk query,
    never the full (multi-chunk) section_detail() text."""
    repo = cu._get_repository()
    previews = repo.chunk_previews(["test.henry.range"])
    assert previews["test.henry.range"] == "SYNTH HENRY RANGE MARKER PART ONE"
    assert "PART TWO" not in previews["test.henry.range"]


# --- source-family grouping (2026-09-03 UI polish round) -----------------
#
# Pure-function tests below build CommentarySectionResult objects by hand
# (no DB needed) to exercise the grouping ALGORITHM directly. The DB-backed
# tests further down use a SEPARATE, dedicated fixture
# (_grouped_synthetic_document) that follows the REAL corpus's
# `<namespace>.<family>.work.<book>` work_id convention (verified against
# the production commentary.sqlite3) -- deliberately NOT the existing
# `_synthetic_document()` above, whose flatter `test.work.<family>` ids
# predate this grouping requirement and would collapse all three of its
# sources into one family under a namespace-prefix key. Reusing it here
# would either silently produce a wrong result or require special-casing
# the algorithm around a test-only convention -- a new, realistic fixture
# is safer and exercises the real behavior faithfully.


def _make_result(
    work_id: str,
    section_id: str,
    contributors: tuple[str, ...],
    *,
    work_title: str = "Work",
    relation_type: str = "exact_passage",
    primary_passages: tuple[str, ...] = (),
) -> CommentarySectionResult:
    return CommentarySectionResult(
        section_id=section_id,
        edition_id=f"{work_id}.edition",
        work_id=work_id,
        work_title=work_title,
        section_type="section",
        heading="",
        sequence=1,
        parent_section_id=None,
        relation_type=relation_type,
        canonical_passages=primary_passages,
        chunk_count=1,
        primary_passages=primary_passages,
        contributors=contributors,
    )


def test_source_family_key_derived_from_work_id_namespace() -> None:
    assert cu._source_family_key("ccel.calvin.work.matthew") == "ccel.calvin"
    assert cu._source_family_key("ccel.jfb.work.matthew") == "ccel.jfb"
    assert cu._source_family_key("ccel.henry.work.matthew") == "ccel.henry"
    # Different books, same family -> same key (this is the whole point).
    assert cu._source_family_key("ccel.jfb.work.matthew") == cu._source_family_key(
        "ccel.jfb.work.james"
    )


def test_source_family_display_name_uses_curated_names_for_known_families() -> None:
    assert cu._source_family_display_name("ccel.calvin", ["John Calvin"]) == "John Calvin"
    assert (
        cu._source_family_display_name("ccel.jfb", ["David Brown"])
        == "Jamieson–Fausset–Brown"
    )
    assert cu._source_family_display_name("ccel.henry", ["Matthew Henry"]) == "Matthew Henry"


def test_source_family_display_name_falls_back_generically_for_unknown_family() -> None:
    """Task requirement: "ugyanez a modell legyen általános más
    több-szerzős kommentárokra is" -- a family with NO curated entry must
    still get a sensible, data-derived name, never crash or show a raw
    internal key."""
    assert cu._source_family_display_name("ccel.spurgeon", ["Charles Spurgeon"]) == (
        "Charles Spurgeon"
    )
    assert cu._source_family_display_name("ccel.mystery", ["A Person", "B Person"]) == (
        "A Person – B Person"
    )
    assert cu._source_family_display_name("ccel.mystery", []) == "Ismeretlen forrás"


def test_group_results_by_family_groups_three_sources_and_preserves_order() -> None:
    results = [
        _make_result("ccel.calvin.work.matthew", "s1", ("John Calvin (author)",)),
        _make_result("ccel.jfb.work.matthew", "s2", ("David Brown (author)",)),
        _make_result("ccel.henry.work.matthew", "s3", ("Matthew Henry (author)",)),
    ]
    groups = cu._group_results_by_family(results)
    assert [g[1] for g in groups] == [
        "John Calvin",
        "Jamieson–Fausset–Brown",
        "Matthew Henry",
    ]
    assert [g[2][0].section_id for g in groups] == ["s1", "s2", "s3"]


def test_group_results_by_family_keeps_multiple_sections_under_one_source_together() -> None:
    results = [
        _make_result("ccel.jfb.work.matthew", "s1", ("David Brown (author)",)),
        _make_result("ccel.henry.work.matthew", "s2", ("Matthew Henry (author)",)),
        _make_result("ccel.jfb.work.matthew", "s3", ("David Brown (author)",)),
    ]
    groups = cu._group_results_by_family(results)
    assert len(groups) == 2  # JFB + Henry, not 3 -- the two JFB hits share one group
    jfb_key, jfb_display, jfb_sections = next(g for g in groups if g[0] == "ccel.jfb")
    assert jfb_display == "Jamieson–Fausset–Brown"
    assert [s.section_id for s in jfb_sections] == ["s1", "s3"]


def test_group_book_sources_by_family_lists_multiple_book_contributors() -> None:
    """A wide query can hit two different JFB-family books (different
    named contributors) at once -- the filter must still show ONE family
    group, listing both book-level names as detail."""
    results = [
        _make_result("ccel.jfb.work.matthew", "s1", ("David Brown (author)",)),
        _make_result("ccel.jfb.work.james", "s2", ("A. R. Fausset (author)",)),
    ]
    groups = cu._group_book_sources_by_family(results)
    assert len(groups) == 1
    family_key, display, book_names = groups[0]
    assert family_key == "ccel.jfb"
    assert display == "Jamieson–Fausset–Brown"
    assert book_names == ["David Brown", "A. R. Fausset"]


# --- human-friendly Hungarian passage display -----------------------------


def test_format_passage_hu_single_verse() -> None:
    assert cu._format_passage_hu("John.3.16") == "Jn 3,16"


def test_format_passage_hu_same_chapter_range() -> None:
    assert cu._format_passage_hu("Matt.5.1-12") == "Mt 5,1–12"


def test_format_passage_hu_cross_chapter_range() -> None:
    assert cu._format_passage_hu("Rom.8.1-4") == "Róm 8,1–4"


def test_format_passage_hu_unmapped_book_falls_back_to_raw_canonical() -> None:
    """Display-only fallback -- never hides data for an unrecognized book
    id, just shows it less prettily."""
    fake = "NotABook.1.1"
    assert cu._format_passage_hu(fake) == fake


def test_format_passage_hu_covers_every_registered_osis_book() -> None:
    from textus_kb.books import BOOKS

    missing = [b.osis_id for b in BOOKS if b.osis_id not in cu._OSIS_TO_RUF_ABBR_HU]
    assert missing == []


def test_format_passage_list_hu_joins_multiple_and_handles_empty() -> None:
    assert cu._format_passage_list_hu(["John.3.16", "Matt.5.1-12"]) == "Jn 3,16, Mt 5,1–12"
    assert cu._format_passage_list_hu([]) == "—"


# --- DB-backed grouping integration (realistic <family>.work.<book> ids) --


def _grouped_synthetic_document() -> dict:
    """Four synthetic sources (Calvin-like, JFB-like with TWO books/
    contributors, Henry-like, and an uncurated 4th "Spurgeon-like" family)
    on Matthew 5:1-12, all sharing the REAL `<namespace>.<family>.work.
    <book>` work_id convention -- ld. the module-level comment above for
    why this is a separate fixture from `_synthetic_document()`."""
    return {
        "contributors": [
            {"contributor_id": "grp.calvin.john-calvin", "canonical_name": "John Calvin", "birth_year": 1509, "death_year": 1564},
            {"contributor_id": "grp.jfb.david-brown", "canonical_name": "David Brown", "birth_year": 1803, "death_year": 1897},
            {"contributor_id": "grp.jfb.a-r-fausset", "canonical_name": "A. R. Fausset", "birth_year": 1821, "death_year": 1910},
            {"contributor_id": "grp.henry.matthew-henry", "canonical_name": "Matthew Henry", "birth_year": 1662, "death_year": 1714},
            {"contributor_id": "grp.spurgeon.charles-spurgeon", "canonical_name": "Charles Spurgeon", "birth_year": 1834, "death_year": 1892},
        ],
        "works": [
            {"work_id": "ccel.calvin.work.matthew", "title": "Commentary on Matthew", "original_title": None, "original_language": "la", "work_type": "commentary"},
            {"work_id": "ccel.jfb.work.matthew", "title": "Commentary Critical and Explanatory: Matthew", "original_title": None, "original_language": "en", "work_type": "commentary"},
            {"work_id": "ccel.jfb.work.james", "title": "Commentary Critical and Explanatory: James", "original_title": None, "original_language": "en", "work_type": "commentary"},
            {"work_id": "ccel.henry.work.matthew", "title": "Matthew Henry's Commentary on the Whole Bible: Matthew", "original_title": None, "original_language": "en", "work_type": "commentary"},
            {"work_id": "ccel.spurgeon.work.matthew", "title": "Spurgeon's Notes on Matthew", "original_title": None, "original_language": "en", "work_type": "commentary"},
        ],
        "work_contributors": [
            {"work_id": "ccel.calvin.work.matthew", "contributor_id": "grp.calvin.john-calvin", "role": "author"},
            {"work_id": "ccel.jfb.work.matthew", "contributor_id": "grp.jfb.david-brown", "role": "author"},
            {"work_id": "ccel.jfb.work.james", "contributor_id": "grp.jfb.a-r-fausset", "role": "author"},
            {"work_id": "ccel.henry.work.matthew", "contributor_id": "grp.henry.matthew-henry", "role": "author"},
            {"work_id": "ccel.spurgeon.work.matthew", "contributor_id": "grp.spurgeon.charles-spurgeon", "role": "author"},
        ],
        "editions": [
            _edition("ccel.calvin.matthew.edition", "ccel.calvin.work.matthew", "ccel-calvin"),
            _edition("ccel.jfb.matthew.edition", "ccel.jfb.work.matthew", "ccel-jfb"),
            _edition("ccel.jfb.james.edition", "ccel.jfb.work.james", "ccel-jfb"),
            _edition("ccel.henry.matthew.edition", "ccel.henry.work.matthew", "ccel-henry"),
            _edition("ccel.spurgeon.matthew.edition", "ccel.spurgeon.work.matthew", "ccel-spurgeon"),
        ],
        "source_files": [
            {"source_file_id": "grp.sf.calvin", "edition_id": "ccel.calvin.matthew.edition", "file_name": "calvin.xml", "raw_sha256": "1" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
            {"source_file_id": "grp.sf.jfb.matthew", "edition_id": "ccel.jfb.matthew.edition", "file_name": "jfb_matt.xml", "raw_sha256": "2" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
            {"source_file_id": "grp.sf.jfb.james", "edition_id": "ccel.jfb.james.edition", "file_name": "jfb_jas.xml", "raw_sha256": "3" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
            {"source_file_id": "grp.sf.henry", "edition_id": "ccel.henry.matthew.edition", "file_name": "henry.xml", "raw_sha256": "4" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
            {"source_file_id": "grp.sf.spurgeon", "edition_id": "ccel.spurgeon.matthew.edition", "file_name": "spurgeon.xml", "raw_sha256": "5" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
        ],
        "import_batches": [
            {"batch_id": "grp.batch.calvin", "source_file_id": "grp.sf.calvin", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
            {"batch_id": "grp.batch.jfb.matthew", "source_file_id": "grp.sf.jfb.matthew", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
            {"batch_id": "grp.batch.jfb.james", "source_file_id": "grp.sf.jfb.james", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
            {"batch_id": "grp.batch.henry", "source_file_id": "grp.sf.henry", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
            {"batch_id": "grp.batch.spurgeon", "source_file_id": "grp.sf.spurgeon", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
        ],
        "sections": [
            {"section_id": "grp.calvin.s1", "edition_id": "ccel.calvin.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "Calvin on Matt 5:1-12", "sequence": 1, "passage_links": [{"raw_citation": "Matthew 5:1-12", "relation_type": "primary"}]},
            {"section_id": "grp.jfb.s1", "edition_id": "ccel.jfb.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "JFB on Matt 5:1-12 (range)", "sequence": 1, "passage_links": [{"raw_citation": "Matthew 5:1-12", "relation_type": "primary"}]},
            {"section_id": "grp.jfb.s2", "edition_id": "ccel.jfb.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "JFB on Matt 5:3 (verse note)", "sequence": 2, "passage_links": [{"raw_citation": "Matthew 5:3", "relation_type": "primary"}]},
            {"section_id": "grp.henry.s1", "edition_id": "ccel.henry.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "Henry on Matt 5:1-12", "sequence": 1, "passage_links": [{"raw_citation": "Matthew 5:1-12", "relation_type": "primary"}]},
            {"section_id": "grp.spurgeon.s1", "edition_id": "ccel.spurgeon.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "Spurgeon on Matt 5:1-12", "sequence": 1, "passage_links": [{"raw_citation": "Matthew 5:1-12", "relation_type": "primary"}]},
        ],
        "chunks": [
            {"chunk_id": "grp.calvin.c1", "section_id": "grp.calvin.s1", "sequence": 1, "text": "GRP CALVIN MARKER", "plain_text": "GRP CALVIN MARKER", "source_locator": "fixture://grp/calvin/1"},
            {"chunk_id": "grp.jfb.c1", "section_id": "grp.jfb.s1", "sequence": 1, "text": "GRP JFB RANGE MARKER", "plain_text": "GRP JFB RANGE MARKER", "source_locator": "fixture://grp/jfb/1"},
            {"chunk_id": "grp.jfb.c2", "section_id": "grp.jfb.s2", "sequence": 1, "text": "GRP JFB VERSE MARKER", "plain_text": "GRP JFB VERSE MARKER", "source_locator": "fixture://grp/jfb/2"},
            {"chunk_id": "grp.henry.c1", "section_id": "grp.henry.s1", "sequence": 1, "text": "GRP HENRY MARKER", "plain_text": "GRP HENRY MARKER", "source_locator": "fixture://grp/henry/1"},
            {"chunk_id": "grp.spurgeon.c1", "section_id": "grp.spurgeon.s1", "sequence": 1, "text": "GRP SPURGEON MARKER", "plain_text": "GRP SPURGEON MARKER", "source_locator": "fixture://grp/spurgeon/1"},
        ],
    }


@pytest.fixture(scope="module")
def grouped_synthetic_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("commentary_ui_grouped") / "commentary.sqlite3"
    import_commentary_sqlite(document=_grouped_synthetic_document(), database_path=database)
    return database


@pytest.fixture()
def patched_grouped_repo(
    grouped_synthetic_db: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(cu, "_get_repository", lambda: CommentaryRepository(grouped_synthetic_db))
    return grouped_synthetic_db


def test_real_retrieval_groups_into_four_families_incl_unmapped_fallback(
    patched_grouped_repo: Path,
) -> None:
    results = cu._fetch_results("Matt.5.1-12")
    groups = cu._group_results_by_family(results)
    displays = [g[1] for g in groups]
    assert "John Calvin" in displays
    assert "Jamieson–Fausset–Brown" in displays
    assert "Matthew Henry" in displays
    assert "Charles Spurgeon" in displays  # uncurated family, generic fallback


def test_jfb_family_groups_two_sections_with_book_level_attribution_preserved(
    patched_grouped_repo: Path,
) -> None:
    results = cu._fetch_results("Matt.5.1-12")
    groups = cu._group_results_by_family(results)
    _key, display, sections = next(g for g in groups if g[0] == "ccel.jfb")
    assert display == "Jamieson–Fausset–Brown"
    assert len(sections) == 2
    assert all(cu._primary_contributor(s.contributors) == "David Brown" for s in sections)


def test_source_filter_state_stays_book_level_compatible_with_compare(
    patched_grouped_repo: Path,
) -> None:
    """Task item 8: the source-selection state feeding into the compare
    feature must stay BOOK-LEVEL contributor names, unaffected by the
    family-grouped filter/card presentation above it."""
    results = cu._fetch_results("Matt.5.1-12")
    sources = cu._sources_present(results)
    assert set(sources) == {"John Calvin", "David Brown", "Matthew Henry", "Charles Spurgeon"}
    filtered = cu._apply_source_filter(results, {"David Brown", "Matthew Henry"})
    assert {cu._primary_contributor(r.contributors) for r in filtered} == {
        "David Brown",
        "Matthew Henry",
    }


def test_provenance_fields_remain_fully_available_after_grouping(
    patched_grouped_repo: Path,
) -> None:
    """Task item 7: grouping/compacting the card list must never lose
    provenance data, only demote its visual prominence."""
    repo = cu._get_repository()
    detail = repo.section_detail("grp.jfb.s1")
    assert detail is not None
    assert detail.edition_id == "ccel.jfb.matthew.edition"
    assert detail.contributors

    results = cu._fetch_results("Matt.5.1-12")
    jfb_card = next(r for r in results if r.section_id == "grp.jfb.s1")
    assert jfb_card.source_url
    assert jfb_card.external_id
    assert jfb_card.rights_status


def test_human_friendly_passage_display_from_real_retrieval(
    patched_grouped_repo: Path,
) -> None:
    results = cu._fetch_results("Matt.5.1-12")
    card = next(r for r in results if r.section_id == "grp.calvin.s1")
    passages = card.primary_passages or card.canonical_passages
    assert cu._format_passage_list_hu(passages) == "Mt 5,1–12"


def test_no_match_state_unchanged_with_grouped_store(patched_grouped_repo: Path) -> None:
    assert cu._fetch_results("Gen.1.1") == []


# --- no generative call in this module ------------------------------------


def test_commentary_ui_card_list_makes_no_direct_llm_call() -> None:
    """Static proof the retrieval-only card list itself never calls a
    provider directly (mirrors tests/test_illustration_legacy_generation_
    removed.py) -- the module DOES now thread an injected ``generate_fn``
    through to commentary_compare.py's explicit-action compare section
    (2026-09-03 grounded-compare round), but never names a concrete
    provider (generate_text/genai/Gemini) or calls generate_fn itself."""
    source = Path(cu.__file__).read_text(encoding="utf-8")
    for forbidden in ("generate_text(", "genai", "Gemini", "gemini", "GEMINI"):
        assert forbidden not in source, forbidden
    # generate_fn is only ever passed through, never invoked in this module.
    assert "generate_fn(" not in source


# --- tab wiring smoke (index + import name) -------------------------------


def test_app_py_wires_commentary_tab_between_original_text_and_exegesis() -> None:
    from workshop_nav_ui import QUICK_TOOLS_TAB_LABELS

    labels = [label.split(": ", 1)[-1] for label in QUICK_TOOLS_TAB_LABELS]
    assert labels.index("Eredeti szöveg tanulmányozása") == labels.index("Kommentárok") - 1
    assert labels.index("Kommentárok") == labels.index("Exegézis") - 1


def test_app_py_imports_and_calls_render_commentary_panel() -> None:
    app_src = Path("app.py").read_text(encoding="utf-8")
    assert "from commentary_ui import render_commentary_panel" in app_src
    # 2026-09-03 (HU translation infra round): now also passes
    # resolve_model_fn, for the translation-provenance model/provider name.
    assert (
        "render_commentary_panel(generate_fn=generate_text, "
        "resolve_model_fn=resolve_gemini_model_for_tab)" in app_src
    )
