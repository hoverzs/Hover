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

2026-09-03 reader redesign: the "source-family reader" section further
down ALSO includes a handful of real, ``AppTest``-driven end-to-end
round trips (mirroring ``tests/test_sermon_workshop_developed_outline_
ui.py``'s established convention) -- the reader's family-switch/
language-toggle/translate-action interplay is genuinely stateful UI
behavior that the pure-helper style alone can't fully exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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
    # 2026-09-03 reader redesign (task item 10): the reading flow no
    # longer decorates every section with a relation caption -- only a
    # SUBTLE badge for the genuinely notable cases (parallel, or a
    # section wider than the query). Primary+exact/partial gets none.
    calvin = by_work["test.work.calvin"]
    jfb = by_work["test.work.jfb"]
    assert cu._reader_badge_text(calvin, "parallel") == "Párhuzamos hely"
    assert cu._reader_badge_text(jfb, "primary") is None


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


# NOTE (2026-09-03 reader redesign): the old `_apply_source_filter`
# (narrowing the flat card list by enabled book-level names) was removed
# -- the reader no longer shows a multi-family flat list to narrow; it
# shows exactly one selected family's sections at a time (ld.
# `_select_reader_family` / `_render_family_reader`). The compare
# feature's own multi-select still returns book-level names unchanged
# (ld. `test_source_filter_state_stays_book_level_compatible_with_compare`
# below), it just no longer feeds a `_apply_source_filter` call.


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
    """Task item 8/11: the source-selection state feeding into the
    compare feature must stay BOOK-LEVEL contributor names, unaffected by
    the family-grouped reader above it -- ld. `_group_book_sources_by_
    family`, which the compare filter (`_render_source_filter`) uses."""
    results = cu._fetch_results("Matt.5.1-12")
    sources = cu._sources_present(results)
    assert set(sources) == {"John Calvin", "David Brown", "Matthew Henry", "Charles Spurgeon"}
    compare_groups = cu._group_book_sources_by_family(results)
    all_book_names = {name for _key, _display, names in compare_groups for name in names}
    assert all_book_names == set(sources)
    jfb_group = next(g for g in compare_groups if g[0] == "ccel.jfb")
    assert jfb_group[2] == ["David Brown"]


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


# --- reader redesign: pure helpers (2026-09-03) ---------------------------


def test_select_reader_family_keeps_valid_requested() -> None:
    assert cu._select_reader_family(["a", "b", "c"], "b") == "b"


def test_select_reader_family_falls_back_to_first_when_invalid_or_missing() -> None:
    assert cu._select_reader_family(["a", "b"], "zzz") == "a"
    assert cu._select_reader_family(["a", "b"], None) == "a"


def test_select_reader_family_empty_list_returns_empty_string() -> None:
    assert cu._select_reader_family([], "a") == ""


def test_sort_sections_for_reading_orders_by_chapter_and_verse() -> None:
    s3 = _make_result("w", "s3", (), primary_passages=("John.3.18",))
    s1 = _make_result("w", "s1", (), primary_passages=("John.3.1",))
    s2 = _make_result("w", "s2", (), primary_passages=("John.3.2",))
    ordered = cu._sort_sections_for_reading([s3, s1, s2])
    assert [s.section_id for s in ordered] == ["s1", "s2", "s3"]


def test_sort_sections_for_reading_is_stable_for_ties() -> None:
    """Task item 16: "passage sorrend stabil" -- two sections that both
    have the EXACT SAME passage span must keep their ORIGINAL relative
    order, never reshuffle by coincidence."""
    a = _make_result("w", "a", (), primary_passages=("John.3.16",))
    b = _make_result("w", "b", (), primary_passages=("John.3.16",))
    ordered = cu._sort_sections_for_reading([a, b])
    assert [s.section_id for s in ordered] == ["a", "b"]
    # A whole-range hit sorts by its OWN start/end -- a wider span
    # starting at the same verse is a real, meaningful ordering
    # difference, not a tie (sorts after the narrower single-verse hit
    # that ends sooner).
    wide = _make_result("w", "wide", (), primary_passages=("John.3.16-21",))
    narrow = _make_result("w", "narrow", (), primary_passages=("John.3.16",))
    ordered2 = cu._sort_sections_for_reading([wide, narrow])
    assert [s.section_id for s in ordered2] == ["narrow", "wide"]


def test_sort_sections_for_reading_unparseable_passage_goes_last() -> None:
    good = _make_result("w", "good", (), primary_passages=("John.3.1",))
    bad = _make_result("w", "bad", (), primary_passages=())
    ordered = cu._sort_sections_for_reading([bad, good])
    assert [s.section_id for s in ordered] == ["good", "bad"]


def test_sections_with_text_drops_zero_chunk_structural_sections() -> None:
    """Real production data (ld. Róm 8,1-4 smoke): a chapter-level
    "exact_passage" section can be a zero-chunk structural container
    whose actual text lives entirely in per-verse child sections --
    nothing to read there, so the reader must skip it."""
    empty = CommentarySectionResult(
        section_id="empty", edition_id="e", work_id="w", work_title="W",
        section_type="section", heading="", sequence=1, parent_section_id=None,
        relation_type="exact_passage", canonical_passages=(), chunk_count=0,
    )
    full = _make_result("w", "full", (), primary_passages=("John.3.1",))
    kept = cu._sections_with_text([empty, full])
    assert [s.section_id for s in kept] == ["full"]


def test_group_family_sections_by_book_groups_by_work_id_preserving_order() -> None:
    a1 = _make_result("w1", "a1", (), work_title="Work One")
    b1 = _make_result("w2", "b1", (), work_title="Work Two")
    a2 = _make_result("w1", "a2", (), work_title="Work One")
    groups = cu._group_family_sections_by_book([a1, b1, a2])
    assert [g[0] for g in groups] == ["w1", "w2"]
    assert groups[0][1] == "Work One"
    assert [s.section_id for s in groups[0][2]] == ["a1", "a2"]


def test_book_display_name_hu_derives_from_passage() -> None:
    s = _make_result("w", "s", (), primary_passages=("Rom.8.1",), work_title="Fallback Title")
    assert cu._book_display_name_hu([s]) == "Rómaiakhoz írt levél"


def test_book_display_name_hu_falls_back_to_work_title_when_unparseable() -> None:
    s = _make_result("w", "s", (), primary_passages=(), work_title="Fallback Title")
    assert cu._book_display_name_hu([s]) == "Fallback Title"


def test_book_display_name_hu_empty_list_returns_empty_string() -> None:
    assert cu._book_display_name_hu([]) == ""


def test_book_contributor_note_omitted_when_contributor_matches_family() -> None:
    """Task item 8: Calvin must never show "John Calvin / John Calvin"."""
    assert (
        cu._book_contributor_note("Rómaiakhoz írt levél", "John Calvin", "John Calvin")
        is None
    )


def test_book_contributor_note_shown_when_contributor_differs() -> None:
    """Task item 8's own Henry-family example, verbatim."""
    note = cu._book_contributor_note(
        "Rómaiakhoz írt levél", "Matthew Henry", "Mr. John Evans"
    )
    assert note == "A Rómaiakhoz írt levél kommentárjának szerzője: Mr. John Evans"


def test_book_contributor_note_none_when_missing_inputs() -> None:
    assert cu._book_contributor_note("", "Matthew Henry", "Mr. John Evans") is None
    assert cu._book_contributor_note("Rómaiakhoz írt levél", "Matthew Henry", "") is None


def test_split_for_progressive_disclosure_short_text_stays_whole() -> None:
    """Task item 4: a short section may show in full, untruncated."""
    visible, rest = cu._split_for_progressive_disclosure("Short text.", 1200)
    assert visible == "Short text."
    assert rest == ""


def test_split_for_progressive_disclosure_splits_at_paragraph_boundary() -> None:
    text = ("A" * 50) + "\n\n" + ("B" * 50)
    visible, rest = cu._split_for_progressive_disclosure(text, 60)
    assert visible == "A" * 50
    assert rest == "B" * 50


def test_split_for_progressive_disclosure_never_cuts_mid_word() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    visible, rest = cu._split_for_progressive_disclosure(text, 20)
    assert visible
    assert all(word in text.split() for word in visible.split())
    assert all(word in text.split() for word in rest.split())


def test_reader_badge_text_none_for_the_common_case() -> None:
    """Task item 10: exact/partial-overlap + primary relation is the
    expected, boring case -- no badge, no interruption to the flow."""
    r = _make_result("w", "s", (), relation_type="exact_passage")
    assert cu._reader_badge_text(r, "primary") is None


def test_reader_badge_text_for_wider_containing_section() -> None:
    r = _make_result("w", "s", (), relation_type="containing_section")
    assert cu._reader_badge_text(r, "primary") == "Tágabb kommentált szakasz"


def test_reader_badge_text_parallel_overrides_tier() -> None:
    r = _make_result("w", "s", (), relation_type="exact_passage")
    assert cu._reader_badge_text(r, "parallel") == "Párhuzamos hely"


# --- reader redesign: translation orchestration (family-level action) -----


def test_translate_missing_sections_only_calls_provider_for_uncached(
    patched_grouped_repo: Path, tmp_path: Path
) -> None:
    """Task item 5/16: "ha három sectionből kettő már cache-elt, csak a
    hiányzót fordítsa" -- and a second pass over the SAME sections (all
    now cached) must make zero further provider calls."""
    repo = cu._get_repository()
    translation_db = tmp_path / "commentary_translations.sqlite3"
    results = cu._fetch_results("Matt.5.1-12")
    calvin_section = next(r for r in results if r.section_id == "grp.calvin.s1")
    jfb_sections = [r for r in results if r.work_id == "ccel.jfb.work.matthew"]
    targets = [calvin_section, *jfb_sections]

    calls: list[str] = []

    def fake_gen(prompt: str, **kwargs) -> str:
        calls.append(prompt)
        return "FAKE HU TEXT"

    succeeded, failed = cu._translate_missing_sections(
        targets,
        generate_fn=fake_gen,
        provider_model="test-model",
        repository=repo,
        database_path=translation_db,
    )
    assert succeeded == len(targets)
    assert failed == 0
    assert len(calls) == len(targets)

    calls.clear()
    succeeded2, failed2 = cu._translate_missing_sections(
        targets,
        generate_fn=fake_gen,
        provider_model="test-model",
        repository=repo,
        database_path=translation_db,
    )
    assert succeeded2 == 0
    assert failed2 == 0
    assert calls == []  # cache-hit sections are never re-requested


def test_translate_missing_sections_bypasses_cooldown_after_the_first_call(
    patched_grouped_repo: Path, tmp_path: Path
) -> None:
    """Real bug found via manual smoke test (2026-09-03, Róm 8,1-4, 4
    missing sections translated in one click): every call after the
    first failed with a false "provider unavailable" because
    generate_text (app.py) enforces a cooldown between calls unless told
    otherwise. The FIRST call in a batch still respects the real
    cooldown; every call AFTER it must explicitly bypass it (matches
    generate_text's own documented "same button press" convention)."""
    repo = cu._get_repository()
    translation_db = tmp_path / "commentary_translations.sqlite3"
    results = cu._fetch_results("Matt.5.1-12")
    calvin_section = next(r for r in results if r.section_id == "grp.calvin.s1")
    jfb_sections = [r for r in results if r.work_id == "ccel.jfb.work.matthew"]
    targets = [calvin_section, *jfb_sections]
    assert len(targets) >= 2  # otherwise this test wouldn't exercise the bug at all

    seen_bypass: list[bool] = []

    def fake_gen(prompt: str, **kwargs) -> str:
        seen_bypass.append(kwargs.get("bypass_cooldown"))
        return "FAKE HU TEXT"

    cu._translate_missing_sections(
        targets,
        generate_fn=fake_gen,
        provider_model="test-model",
        repository=repo,
        database_path=translation_db,
    )
    assert seen_bypass[0] is False
    assert all(v is True for v in seen_bypass[1:])


def test_translate_missing_sections_counts_failures_without_crashing(
    patched_grouped_repo: Path, tmp_path: Path
) -> None:
    """Task item 16: a provider failure must be reported, never crash the
    orchestration or silently cache a warning string as a translation."""
    repo = cu._get_repository()
    translation_db = tmp_path / "commentary_translations.sqlite3"
    results = cu._fetch_results("Matt.5.1-12")
    calvin_section = next(r for r in results if r.section_id == "grp.calvin.s1")

    def failing_gen(prompt: str, **kwargs) -> str:
        return "⚠️ Hiányzó API kulcs."

    succeeded, failed = cu._translate_missing_sections(
        [calvin_section],
        generate_fn=failing_gen,
        provider_model="",
        repository=repo,
        database_path=translation_db,
    )
    assert succeeded == 0
    assert failed == 1

    from textus_kb import commentary_translation_policy as policy
    from textus_kb import commentary_translation_store as store

    detail = repo.section_detail(calvin_section.section_id)
    fingerprint = store.compute_source_fingerprint([c.plain_text for c in detail.chunks])
    assert (
        store.get_translation(
            calvin_section.section_id,
            fingerprint,
            language="hu",
            policy_version=policy.TRANSLATION_POLICY_VERSION,
            database_path=translation_db,
        )
        is None
    )


# --- reader redesign: full end-to-end round trips (AppTest) ---------------


def _reader_flow_document() -> dict:
    """Three curated-family sources (Calvin/JFB/Henry) on the same
    Matthew 5:1-2 range, with Henry's book-level contributor deliberately
    DIFFERENT from the family's own display name (a real continuator
    scenario, ld. task item 8's own example) -- Calvin's own contributor
    matches the family name exactly, so it must NOT show a redundant
    note. Real-style ``<namespace>.<family>.work.<book>`` ids throughout,
    so the curated ``_SOURCE_FAMILY_DISPLAY_NAMES_HU`` names apply."""

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

    return {
        "contributors": [
            {"contributor_id": "rd.calvin.john-calvin", "canonical_name": "John Calvin", "birth_year": 1509, "death_year": 1564},
            {"contributor_id": "rd.jfb.david-brown", "canonical_name": "David Brown", "birth_year": 1803, "death_year": 1897},
            {"contributor_id": "rd.henry.john-evans", "canonical_name": "Mr. John Evans", "birth_year": 1680, "death_year": 1730},
        ],
        "works": [
            {"work_id": "ccel.calvin.work.matthew", "title": "Commentary on Matthew", "original_title": None, "original_language": "la", "work_type": "commentary"},
            {"work_id": "ccel.jfb.work.matthew", "title": "Commentary Critical and Explanatory: Matthew", "original_title": None, "original_language": "en", "work_type": "commentary"},
            {"work_id": "ccel.henry.work.matthew", "title": "Matthew Henry's Commentary on the Whole Bible: Matthew", "original_title": None, "original_language": "en", "work_type": "commentary"},
        ],
        "work_contributors": [
            {"work_id": "ccel.calvin.work.matthew", "contributor_id": "rd.calvin.john-calvin", "role": "author"},
            {"work_id": "ccel.jfb.work.matthew", "contributor_id": "rd.jfb.david-brown", "role": "author"},
            {"work_id": "ccel.henry.work.matthew", "contributor_id": "rd.henry.john-evans", "role": "author"},
        ],
        "editions": [
            _edition("ccel.calvin.matthew.edition", "ccel.calvin.work.matthew", "ccel-calvin"),
            _edition("ccel.jfb.matthew.edition", "ccel.jfb.work.matthew", "ccel-jfb"),
            _edition("ccel.henry.matthew.edition", "ccel.henry.work.matthew", "ccel-henry"),
        ],
        "source_files": [
            {"source_file_id": "rd.sf.calvin", "edition_id": "ccel.calvin.matthew.edition", "file_name": "c.xml", "raw_sha256": "1" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
            {"source_file_id": "rd.sf.jfb", "edition_id": "ccel.jfb.matthew.edition", "file_name": "j.xml", "raw_sha256": "2" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
            {"source_file_id": "rd.sf.henry", "edition_id": "ccel.henry.matthew.edition", "file_name": "h.xml", "raw_sha256": "3" * 64, "byte_size": 10, "retrieved_at": "2026-09-03T00:00:00Z"},
        ],
        "import_batches": [
            {"batch_id": "rd.batch.calvin", "source_file_id": "rd.sf.calvin", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
            {"batch_id": "rd.batch.jfb", "source_file_id": "rd.sf.jfb", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
            {"batch_id": "rd.batch.henry", "source_file_id": "rd.sf.henry", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-09-03T00:05:00Z", "report": {}},
        ],
        "sections": [
            {"section_id": "rd.calvin.v1", "edition_id": "ccel.calvin.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "Calvin v1", "sequence": 1, "passage_links": [{"raw_citation": "Matthew 5:1", "relation_type": "primary"}]},
            {"section_id": "rd.calvin.v2", "edition_id": "ccel.calvin.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "Calvin v2", "sequence": 2, "passage_links": [{"raw_citation": "Matthew 5:2", "relation_type": "primary"}]},
            {"section_id": "rd.jfb.v1", "edition_id": "ccel.jfb.matthew.edition", "parent_section_id": None, "section_type": "section", "heading": "JFB v1", "sequence": 1, "passage_links": [{"raw_citation": "Matthew 5:1", "relation_type": "primary"}]},
            {"section_id": "rd.henry.range", "edition_id": "ccel.henry.matthew.edition", "parent_section_id": None, "section_type": "range_commentary", "heading": "Henry range", "sequence": 1, "passage_links": [{"raw_citation": "Matthew 5:1-2", "relation_type": "primary"}]},
        ],
        "chunks": [
            {"chunk_id": "rd.calvin.c1", "section_id": "rd.calvin.v1", "sequence": 1, "text": "CALVIN VERSE ONE TEXT", "plain_text": "CALVIN VERSE ONE TEXT", "source_locator": "fixture://rd/calvin/1"},
            {"chunk_id": "rd.calvin.c2", "section_id": "rd.calvin.v2", "sequence": 1, "text": "CALVIN VERSE TWO TEXT", "plain_text": "CALVIN VERSE TWO TEXT", "source_locator": "fixture://rd/calvin/2"},
            {"chunk_id": "rd.jfb.c1", "section_id": "rd.jfb.v1", "sequence": 1, "text": "JFB VERSE ONE TEXT", "plain_text": "JFB VERSE ONE TEXT", "source_locator": "fixture://rd/jfb/1"},
            {"chunk_id": "rd.henry.c1", "section_id": "rd.henry.range", "sequence": 1, "text": "HENRY RANGE TEXT", "plain_text": "HENRY RANGE TEXT", "source_locator": "fixture://rd/henry/1"},
        ],
    }


def _render_commentary_reader_flow() -> None:
    """Self-contained AppTest render helper (own imports/inline data, per
    this repo's established ``AppTest.from_function`` convention -- ld.
    tests/test_sermon_workshop_developed_outline_ui.py). Builds an
    isolated synthetic Commentary + translation SQLite store under the
    system temp dir (never the real production DBs) and drives the real
    ``render_commentary_panel()`` end to end with a fake, call-counting
    ``generate_fn``."""
    import tempfile
    from pathlib import Path as _Path

    import streamlit as st

    import commentary_ui as cu
    from tests.test_commentary_ui import _reader_flow_document
    from textus_kb import commentary_runtime
    from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
    from textus_kb.repositories.commentary_repository import CommentaryRepository

    tmp_root = _Path(tempfile.gettempdir()) / "textus_test_commentary_reader_ui"
    tmp_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_root / "commentary.sqlite3"
    translation_db_path = tmp_root / "commentary_translations.sqlite3"
    import_commentary_sqlite(document=_reader_flow_document(), database_path=db_path)

    cu._get_repository = lambda: CommentaryRepository(db_path)  # type: ignore[assignment]
    cu._get_status = lambda: commentary_runtime.get_status(db_path)  # type: ignore[assignment]
    cu._translation_database_path = lambda: translation_db_path  # type: ignore[assignment]

    if "_test_call_count" not in st.session_state:
        st.session_state["_test_call_count"] = 0
    if "_test_prompts" not in st.session_state:
        st.session_state["_test_prompts"] = []

    def fake_gen(prompt: str, **kwargs) -> str:
        st.session_state["_test_call_count"] += 1
        st.session_state["_test_prompts"].append(prompt)
        return "FAKE HU TRANSLATION"

    st.session_state["last_igehely"] = "Matt.5.1-2"
    cu.render_commentary_panel(generate_fn=fake_gen, resolve_model_fn=lambda label: "test-model")


def _render_commentary_reader_flow_failing_provider() -> None:
    """Same fixture/wiring as ``_render_commentary_reader_flow``, but with
    a FAILING ``generate_fn`` -- proves the English reader stays fully
    usable even when translation generation fails (task item 16/17)."""
    import tempfile
    from pathlib import Path as _Path

    import streamlit as st

    import commentary_ui as cu
    from tests.test_commentary_ui import _reader_flow_document
    from textus_kb import commentary_runtime
    from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
    from textus_kb.repositories.commentary_repository import CommentaryRepository

    tmp_root = _Path(tempfile.gettempdir()) / "textus_test_commentary_reader_ui_failing"
    tmp_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_root / "commentary.sqlite3"
    translation_db_path = tmp_root / "commentary_translations.sqlite3"
    if translation_db_path.is_file():
        translation_db_path.unlink()
    import_commentary_sqlite(document=_reader_flow_document(), database_path=db_path)

    cu._get_repository = lambda: CommentaryRepository(db_path)  # type: ignore[assignment]
    cu._get_status = lambda: commentary_runtime.get_status(db_path)  # type: ignore[assignment]
    cu._translation_database_path = lambda: translation_db_path  # type: ignore[assignment]

    def failing_gen(prompt: str, **kwargs) -> str:
        return "⚠️ Hiányzó API kulcs."

    st.session_state["last_igehely"] = "Matt.5.1-2"
    cu.render_commentary_panel(generate_fn=failing_gen, resolve_model_fn=lambda label: "test-model")


@pytest.fixture()
def clean_reader_ui_translation_cache():
    """Resets the isolated reader-flow translation store before a test
    that needs to start from a genuine cache miss."""
    import tempfile
    from pathlib import Path as _p

    path = _p(tempfile.gettempdir()) / "textus_test_commentary_reader_ui" / "commentary_translations.sqlite3"
    if path.is_file():
        path.unlink()
    yield


def _render_commentary_reader_flow_heading_echo() -> None:
    """Same fixture/wiring as ``_render_commentary_reader_flow``, but the
    fake ``generate_fn`` mimics the REAL, observed bug (task item 5): a
    provider response that starts with a redundant markdown heading
    echoing the passage (e.g. "## Mt 5:1") despite the prompt forbidding
    it -- verifies the reader's OWN passage heading is never followed by
    a visually duplicated second one. Own isolated tmp dir so this
    doesn't interfere with the other reader-flow tests' cache state."""
    import re
    import tempfile
    from pathlib import Path as _Path

    import streamlit as st

    import commentary_ui as cu
    from tests.test_commentary_ui import _reader_flow_document
    from textus_kb import commentary_runtime
    from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
    from textus_kb.repositories.commentary_repository import CommentaryRepository

    tmp_root = _Path(tempfile.gettempdir()) / "textus_test_commentary_reader_ui_heading_echo"
    tmp_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_root / "commentary.sqlite3"
    translation_db_path = tmp_root / "commentary_translations.sqlite3"
    if translation_db_path.is_file():
        translation_db_path.unlink()
    import_commentary_sqlite(document=_reader_flow_document(), database_path=db_path)

    cu._get_repository = lambda: CommentaryRepository(db_path)  # type: ignore[assignment]
    cu._get_status = lambda: commentary_runtime.get_status(db_path)  # type: ignore[assignment]
    cu._translation_database_path = lambda: translation_db_path  # type: ignore[assignment]

    def heading_echo_gen(prompt: str, **kwargs) -> str:
        # Mimics the REAL observed provider behavior: echoes back
        # whichever passage THIS specific call's prompt is actually
        # about (never a fixed string), exactly like a real model
        # response would vary per section/batch.
        match = re.search(r"Kapcsolódó igehely: (.+)", prompt)
        passage = match.group(1).strip() if match else "?"
        heading = passage.replace(",", ":")
        return f"## {heading}\n\nEz a lefordított tartalom valódi szövege."

    st.session_state["last_igehely"] = "Matt.5.1-2"
    cu.render_commentary_panel(
        generate_fn=heading_echo_gen, resolve_model_fn=lambda label: "test-model"
    )


def test_reader_shows_exactly_one_family_selector_and_three_options(
    clean_reader_ui_translation_cache,
) -> None:
    """Task item 2: a compact single-select family control, all three
    metadata-derived families available at once. ``ButtonGroup.options``
    reports the FORMATTED (display) labels, not the raw family keys."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    controls = at.segmented_control
    assert len(controls) == 1
    assert set(controls[0].options) == {
        "John Calvin",
        "Jamieson–Fausset–Brown",
        "Matthew Henry",
    }


def test_reader_defaults_to_first_family_showing_one_reader_at_a_time(
    clean_reader_ui_translation_cache,
) -> None:
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    markdown_values = [md.value for md in at.markdown]
    headers = {"### John Calvin", "### Jamieson–Fausset–Brown", "### Matthew Henry"}
    shown = [v for v in markdown_values if v in headers]
    # Exactly one reader (family header) is open at a time.
    assert len(shown) == 1


def test_reader_switching_family_shows_only_that_familys_sections(
    clean_reader_ui_translation_cache,
) -> None:
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.henry").run(timeout=60)
    markdown_values = [md.value for md in at.markdown]
    captions = [c.value for c in at.caption]
    assert "### Matthew Henry" in markdown_values
    assert "### John Calvin" not in markdown_values
    assert "### Jamieson–Fausset–Brown" not in markdown_values
    assert any("Matthew Henry's Commentary" in c for c in captions)
    assert not any(c == "Commentary on Matthew" for c in captions)


def test_reader_language_radio_and_caption_share_one_row(
    clean_reader_ui_translation_cache,
) -> None:
    """2026-09-04 UX tweak: the "Nyelv" radio and its explanatory caption
    ("AI által készített magyar fordítás...") sit in two sibling
    ``st.columns`` -- the radio's own column, and a caption in the very
    next column -- instead of stacking on separate lines. In "Eredeti
    angol" mode the caption is simply absent (unchanged existing
    behaviour), so only the radio's own column is populated."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    columns = at.columns
    radio_col_index = next(i for i, col in enumerate(columns) if len(col.radio) == 1)
    caption_col_index = next(
        i
        for i, col in enumerate(columns)
        if any("gépi fordítása, nem összefoglalás" in c.value for c in col.caption)
    )
    assert caption_col_index == radio_col_index + 1
    assert len(columns[caption_col_index].radio) == 0
    assert len(columns[radio_col_index].caption) == 0

    radios = at.radio
    at = radios[0].set_value("Eredeti angol").run(timeout=60)
    all_captions = [c.value for c in at.caption]
    assert not any("gépi fordítása, nem összefoglalás" in c for c in all_captions)


def test_reader_multiple_sections_render_in_one_reader_in_passage_order(
    clean_reader_ui_translation_cache,
) -> None:
    """Task item 3/16: Calvin has TWO sections (v1, v2) -- both appear
    together in one reader, in passage order, without becoming two giant
    separate source cards. Switches to "Eredeti angol" so the real
    (untranslated) section text is deterministically visible regardless
    of translation-cache state."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    radios = at.radio
    at = radios[0].set_value("Eredeti angol").run(timeout=60)
    body = "\n".join(md.value for md in at.markdown)
    assert "CALVIN VERSE ONE TEXT" in body
    assert "CALVIN VERSE TWO TEXT" in body
    assert body.index("CALVIN VERSE ONE TEXT") < body.index("CALVIN VERSE TWO TEXT")
    # No per-section bordered "card" container -- the whole reader is a
    # single flow, so the work title caption appears only once, at the
    # book-group level, never repeated per verse.
    captions = [c.value for c in at.caption]
    assert captions.count("Commentary on Matthew") == 1


def test_reader_calvin_does_not_duplicate_the_same_author_name(
    clean_reader_ui_translation_cache,
) -> None:
    """Task item 8: Calvin's family name and book contributor are
    identical -- must show ONLY ONCE, never as a redundant note."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    captions = [c.value for c in at.caption]
    assert not any("kommentárjának szerzője" in c for c in captions)


def test_reader_henry_family_shows_the_real_continuator_contributor(
    clean_reader_ui_translation_cache,
) -> None:
    """Task item 8/17: family header "Matthew Henry", but the concrete
    book contributor note names "Mr. John Evans" -- a real continuator
    scenario mirroring the production Róm 8,1-4 case."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.henry").run(timeout=60)
    markdown_values = [md.value for md in at.markdown]
    assert any(v == "### Matthew Henry" for v in markdown_values)
    captions = [c.value for c in at.caption]
    assert any(
        "kommentárjának szerzője: Mr. John Evans" in c for c in captions
    )


def test_reader_jfb_family_shows_david_brown_contributor(
    clean_reader_ui_translation_cache,
) -> None:
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.jfb").run(timeout=60)
    markdown_values = [md.value for md in at.markdown]
    assert any(v == "### Jamieson–Fausset–Brown" for v in markdown_values)
    captions = [c.value for c in at.caption]
    assert any("kommentárjának szerzője: David Brown" in c for c in captions)


def test_reader_hungarian_mode_untranslated_section_does_not_call_provider(
    clean_reader_ui_translation_cache,
) -> None:
    """Task item 5/16: opening a reader with NO cached translation must
    never trigger an automatic provider call, even though Hungarian is
    the default language mode."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    assert at.session_state["_test_call_count"] == 0
    captions = [c.value for c in at.caption]
    assert any("még nincs magyar fordítás" in c for c in captions)


def test_reader_translate_action_only_translates_missing_sections(
    clean_reader_ui_translation_cache,
) -> None:
    """Task item 5/16: the family-level action translates ONLY the
    sections that lack a cached translation; a second, separate AppTest
    run then hits the cache with zero further provider calls."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    translate_btn = next(
        b for b in at.button if "lefordítása magyarra" in b.label or b.label == "Magyar fordítás elkészítése"
    )
    at = translate_btn.click().run(timeout=60)
    assert at.session_state["_test_call_count"] == 2  # Calvin has 2 sections
    body = "\n".join(md.value for md in at.markdown)
    assert "FAKE HU TRANSLATION" in body

    # Cache-hit: a brand-new AppTest run (fresh session_state counter)
    # must find both Calvin sections already cached -- zero new calls.
    at2 = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at2 = at2.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    assert at2.session_state["_test_call_count"] == 0
    body2 = "\n".join(md.value for md in at2.markdown)
    assert "FAKE HU TRANSLATION" in body2


def test_render_family_reader_is_fragment_isolated() -> None:
    """Structural guard (source-level, mirrors this repo's established
    ``inspect.getsource``-based wiring checks, ld. ``test_app_py_imports_
    and_calls_render_commentary_panel``): ``@st.fragment`` must stay
    immediately above ``_render_family_reader`` -- if it's ever removed
    (e.g. during a future refactor), the translate/language-toggle
    widgets inside it would silently go back to triggering a full
    app.py rerun, reintroducing the whole-page dim/stale-frame bug this
    round fixed.

    Note on why this is a source check rather than an ``AppTest``
    behavioral one: ``AppTest.from_function(...).run()`` always fully
    re-executes the given function for every interaction it simulates --
    verified directly against Streamlit 1.58's own ``ScriptRunner``
    (``streamlit/runtime/scriptrunner/script_runner.py``): a REAL
    fragment-scoped rerun request (``rerun_data.fragment_id_queue`` set)
    looks up and calls only the previously-registered fragment closure
    from ``self._fragment_storage`` -- it deliberately skips the normal
    ``exec(code, module.__dict__)`` path that runs the surrounding
    script. ``AppTest``'s public API (``AppTest.run()``, ``Button.
    click()``) exposes no fragment-scoped rerun option at all, so it
    cannot observe this specific optimization -- only the real
    ``ScriptRunner`` a running app actually uses does."""
    import inspect

    source = inspect.getsource(cu)
    fn_index = source.index("def _render_family_reader(")
    preceding = source[:fn_index]
    decorator_line = preceding.rstrip().splitlines()[-1].strip()
    assert decorator_line == "@st.fragment"


def test_reader_english_mode_never_calls_provider(
    clean_reader_ui_translation_cache,
) -> None:
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    radios = at.radio
    at = radios[0].set_value("Eredeti angol").run(timeout=60)
    assert at.session_state["_test_call_count"] == 0
    body = "\n".join(md.value for md in at.markdown)
    assert "CALVIN VERSE ONE TEXT" in body


def test_reader_provider_failure_leaves_english_reader_usable() -> None:
    """Task item 16/17: a failing provider must never break the English
    reading mode -- switching language mode away from Hungarian always
    works, with zero dependency on translation success."""
    at = AppTest.from_function(_render_commentary_reader_flow_failing_provider).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    radios = at.radio
    at = radios[0].set_value("Eredeti angol").run(timeout=60)
    body = "\n".join(md.value for md in at.markdown)
    assert "CALVIN VERSE ONE TEXT" in body
    assert not at.exception


def test_reader_provenance_traceable_to_each_section(
    clean_reader_ui_translation_cache,
) -> None:
    """Task item 9: nothing lost -- edition id, section id, source
    locator, upstream URL, rights and relation type all remain reachable
    per section inside the single "Forrásadatok" expander."""
    at = AppTest.from_function(_render_commentary_reader_flow).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    expander_labels = [e.label for e in at.expander]
    assert "Forrásadatok" in expander_labels
    page_text = "\n".join(md.value for md in at.markdown) + "\n".join(
        c.value for c in at.caption
    )
    assert "ccel.calvin.matthew.edition" in page_text
    assert "rd.calvin.v1" in page_text
    assert "fixture://rd/calvin/1" in page_text
    assert "https://example.test/ccel-calvin" in page_text


def test_reader_no_match_and_unavailable_states_unchanged() -> None:
    """Task item 16/18: the missing-DB and no-passage/no-match states
    stay exactly the pure functions they were -- untouched by the reader
    redesign (ld. the "unavailable store / no passage" section above for
    the equivalent pure-helper tests already covering these)."""
    import inspect

    source = inspect.getsource(cu.render_commentary_panel)
    assert "_render_missing_db(status)" in source
    assert "_render_no_passage()" in source
    assert "_render_no_match(passage)" in source


# --- Final hardening round (2026-09-03): UI label + duplicate heading ----


def test_full_section_expander_uses_the_renamed_unambiguous_label() -> None:
    """Task item 4: "Tovább olvasom" read as misleadingly casual for what
    can open a very long, complete canonical section -- renamed, not
    removed, not shortened, not summarized."""
    src = Path("commentary_ui.py").read_text(encoding="utf-8")
    assert 'st.expander("Teljes kommentárszakasz megnyitása")' in src
    assert "Tovább olvasom" not in src


def test_reader_hungarian_text_never_shows_a_duplicated_passage_heading(
) -> None:
    """Task item 5: real bug -- a provider response starting with a
    redundant markdown heading (e.g. "## Mt 5:1") rendered as a SECOND,
    visually duplicated heading right under the reader's own "Mt 5,1".
    The fix lives in commentary_translation_service (stripped once,
    before caching) -- this is the end-to-end proof the reader itself
    never shows the duplicate, regardless of where the fix lives.
    Both of Calvin's sections translate in this one click (v1 -> "## Mt
    5:1", v2 -> "## Mt 5:2", ld. the fake generate_fn), so this also
    proves the fix isn't accidentally specific to one hardcoded passage."""
    at = AppTest.from_function(_render_commentary_reader_flow_heading_echo).run(timeout=60)
    at = at.segmented_control[0].set_value("ccel.calvin").run(timeout=60)
    translate_btn = next(
        b for b in at.button if "lefordítása magyarra" in b.label or b.label == "Magyar fordítás elkészítése"
    )
    at = translate_btn.click().run(timeout=60)

    markdown_values = [md.value for md in at.markdown]
    body = "\n".join(markdown_values)
    assert body.count("Ez a lefordított tartalom valódi szövege.") == 2  # both v1 and v2
    # The model's echoed heading must never survive into the rendered
    # translated text, for EITHER section.
    assert "## Mt 5:1" not in body
    assert "## Mt 5:2" not in body
    # The translated CONTENT block itself (as opposed to the reader's own
    # "**Mt 5,1**" heading, or the unrelated "Forrásadatok" provenance
    # block that legitimately also mentions the passage) never starts
    # with a markdown heading marker.
    content_values = [v for v in markdown_values if "Ez a lefordított tartalom" in v]
    assert len(content_values) == 2
    assert all(not v.startswith("#") for v in content_values)


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
