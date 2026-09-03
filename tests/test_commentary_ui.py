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
from textus_kb.repositories.commentary_repository import CommentaryRepository


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
    # Human-facing labels are explicitly non-ranking wording.
    assert cu._PASSAGE_RELATION_LABELS_HU["primary"] == "fő kommentált hely"
    assert cu._PASSAGE_RELATION_LABELS_HU["parallel"] == "párhuzamos evangéliumi hely"


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
    assert "render_commentary_panel(generate_fn=generate_text)" in app_src
