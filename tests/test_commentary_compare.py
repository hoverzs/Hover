"""Grounded, source-restricted Commentary comparison
("Kommentárok összehasonlítása") tests -- helper/smoke pattern, matching
``tests/test_commentary_ui.py``'s established style for this feature area.

Two data sources:
  - The small synthetic 3-source document already built in ``tests/
    test_commentary_ui.py`` (Calvin-like Harmony parallel-only hit, JFB-
    like exact hit, Henry-like native range hit on John 3) -- reused here
    unchanged, since it already models exactly the primary/parallel and
    source-no-match scenarios this round needs precise control over.
  - The real, locally-built 3-source production store (gated, skipped
    when unavailable) for genuine Calvin/JFB/Henry corpus checks,
    including the real Revelation-has-no-Calvin case.

No external LLM/API is called anywhere in this file -- ``generate_fn`` is
always a local fake that records what it was called with.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import commentary_compare as cc
from tests.test_commentary_ui import _synthetic_document
from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
from textus_kb.repositories.commentary_repository import CommentaryRepository

_PRODUCTION_DB = Path("data/generated/commentary.sqlite3")
_requires_production_commentary = pytest.mark.skipif(
    not (_PRODUCTION_DB.is_file() and CommentaryRepository(_PRODUCTION_DB).store_status().available),
    reason=(
        "Production 3-source commentary.sqlite3 not present/valid locally. Build with: "
        "python scripts/build_commentary_database.py --combined-fetch --qa"
    ),
)


@pytest.fixture(scope="module")
def synthetic_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("commentary_compare_synth") / "commentary.sqlite3"
    import_commentary_sqlite(document=_synthetic_document(), database_path=database)
    return database


@pytest.fixture()
def synthetic_repo(synthetic_db: Path) -> CommentaryRepository:
    return CommentaryRepository(synthetic_db)


class _FakeGenerate:
    """Records every call; never a real provider — proves the "no LLM
    call in fail-closed paths" and "no automatic invocation" claims."""

    def __init__(self, response: str = "FAKE COMPARE OUTPUT") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.response = response

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append((prompt, kwargs))
        return self.response


# --- Pure eligibility logic -------------------------------------------


def test_readiness_needs_at_least_two_sources() -> None:
    r = cc.evaluate_compare_readiness(["A"], {"A": [object()]})
    assert r.eligible is False
    assert "legalább 2" in r.message.lower() or "2" in r.message


def test_readiness_rejects_more_than_three_sources() -> None:
    r = cc.evaluate_compare_readiness(["A", "B", "C", "D"], {})
    assert r.eligible is False
    assert "legfeljebb 3" in r.message.lower() or "3" in r.message


def test_readiness_deduplicates_source_names() -> None:
    r = cc.evaluate_compare_readiness(["A", "A", "B"], {"A": [object()], "B": [object()]})
    assert r.eligible is True
    assert r.sources_to_compare == ("A", "B")


def test_readiness_reports_source_without_hits_explicitly() -> None:
    r = cc.evaluate_compare_readiness(["A", "B", "C"], {"A": [object()], "B": [object()]})
    assert r.eligible is True
    assert r.sources_to_compare == ("A", "B")
    assert r.sources_without_hits == ("C",)


def test_readiness_ineligible_when_fewer_than_two_have_hits() -> None:
    r = cc.evaluate_compare_readiness(["A", "B"], {"A": [object()]})
    assert r.eligible is False
    assert "B" in r.message


# --- Real evidence grouping (synthetic store) --------------------------


def test_group_evidence_calvin_jfb_henry_all_three(synthetic_repo: CommentaryRepository) -> None:
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test JFB", "Test Henry"], repository=synthetic_repo
    )
    assert set(grouped) == {"Test Calvin", "Test JFB", "Test Henry"}
    for items in grouped.values():
        assert items


def test_group_evidence_calvin_jfb_only(synthetic_repo: CommentaryRepository) -> None:
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test JFB"], repository=synthetic_repo
    )
    assert set(grouped) == {"Test Calvin", "Test JFB"}


def test_group_evidence_calvin_henry_only(synthetic_repo: CommentaryRepository) -> None:
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test Henry"], repository=synthetic_repo
    )
    assert set(grouped) == {"Test Calvin", "Test Henry"}


def test_group_evidence_source_no_match(synthetic_repo: CommentaryRepository) -> None:
    """John.3.20 has JFB + Henry hits but no Calvin (ld. the synthetic
    document's own design) -- Calvin must be silently absent from the
    grouping (never substituted), and readiness must report it."""
    grouped = cc.group_evidence_by_source(
        "John.3.20", ["Test Calvin", "Test JFB", "Test Henry"], repository=synthetic_repo
    )
    assert "Test Calvin" not in grouped
    assert set(grouped) == {"Test JFB", "Test Henry"}
    readiness = cc.evaluate_compare_readiness(
        ["Test Calvin", "Test JFB", "Test Henry"], grouped
    )
    assert readiness.eligible is True
    assert readiness.sources_without_hits == ("Test Calvin",)
    assert readiness.sources_to_compare == ("Test JFB", "Test Henry")


def test_group_evidence_harmony_primary_and_parallel(synthetic_repo: CommentaryRepository) -> None:
    """John.3.16: the synthetic Calvin-like hit is parallel-only, JFB and
    Henry are primary -- proves the raw relation metadata for each
    grouped item is preserved (used later by build_compare_prompt's
    reused citation renderer)."""
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test JFB", "Test Henry"], repository=synthetic_repo
    )
    calvin_item = grouped["Test Calvin"][0]
    jfb_item = grouped["Test JFB"][0]
    assert calvin_item.metadata.get("parallel_passages") == ["John.3.16"]
    assert calvin_item.metadata.get("primary_passages") in ([], None)
    assert jfb_item.metadata.get("primary_passages") == ["John.3.16"]


def test_group_evidence_unavailable_db_returns_empty(tmp_path: Path) -> None:
    repo = CommentaryRepository(tmp_path / "does_not_exist.sqlite3")
    grouped = cc.group_evidence_by_source("John.3.16", ["Test Calvin", "Test JFB"], repository=repo)
    assert grouped == {}


def test_group_evidence_no_sources_requested_returns_empty(
    synthetic_repo: CommentaryRepository,
) -> None:
    assert cc.group_evidence_by_source("John.3.16", [], repository=synthetic_repo) == {}


# --- Prompt/citation structure ------------------------------------------


def test_compare_prompt_has_required_structure_headings(
    synthetic_repo: CommentaryRepository,
) -> None:
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test JFB", "Test Henry"], repository=synthetic_repo
    )
    payload = cc.build_compare_prompt("John 3:16", "John.3.16", grouped)
    for heading in (
        "## Közös hangsúlyok",
        "## Eltérő értelmezések vagy hangsúlyok",
        "## Az egyes kommentárok sajátos hozzájárulása",
        "## Mai exegetikai megjegyzés",
    ):
        assert heading in payload.prompt


def test_compare_prompt_forbids_verdicts_and_fabrication_in_rules() -> None:
    assert "TILOS kitalálni" in cc._COMPARE_RULES
    assert "megbízhatósági pontszámot" in cc._COMPARE_RULES
    assert "helyesnek" in cc._COMPARE_RULES and "hibásnak" in cc._COMPARE_RULES


def test_compare_prompt_carries_full_citation_provenance(
    synthetic_repo: CommentaryRepository,
) -> None:
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test JFB", "Test Henry"], repository=synthetic_repo
    )
    payload = cc.build_compare_prompt("John 3:16", "John.3.16", grouped)
    for required in (
        "Citation:",
        "work_title=",
        "edition_id=",
        "section_id=",
        "canonical_scope=",
    ):
        assert required in payload.prompt
    assert "Test Calvin" in payload.prompt
    assert "Test JFB" in payload.prompt
    assert "Test Henry" in payload.prompt


def test_compare_prompt_source_ids_and_evidence_ids_nonempty(
    synthetic_repo: CommentaryRepository,
) -> None:
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test JFB"], repository=synthetic_repo
    )
    payload = cc.build_compare_prompt("John 3:16", "John.3.16", grouped)
    assert payload.source_ids
    assert payload.evidence_ids
    assert payload.source_names == ("Test Calvin", "Test JFB")


def test_compare_prompt_caps_items_per_source(synthetic_repo: CommentaryRepository) -> None:
    grouped = cc.group_evidence_by_source(
        "John.3.16", ["Test Calvin", "Test JFB", "Test Henry"], repository=synthetic_repo
    )
    for items in grouped.values():
        assert len(items) <= cc.MAX_ITEMS_PER_SOURCE


# --- Orchestration (run_commentary_compare) ------------------------------


def test_run_compare_ok_calls_generate_fn_once(synthetic_repo: CommentaryRepository) -> None:
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "John.3.16",
        "John 3:16",
        ["Test Calvin", "Test JFB", "Test Henry"],
        generate_fn=fake,
        repository=synthetic_repo,
    )
    assert result.status == "ok"
    assert result.text == "FAKE COMPARE OUTPUT"
    assert len(fake.calls) == 1
    prompt, kwargs = fake.calls[0]
    assert "John 3:16" in prompt
    assert kwargs.get("use_cache") is False
    assert kwargs.get("enable_google_search") is False


def test_run_compare_max_three_sources_ok(synthetic_repo: CommentaryRepository) -> None:
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "John.3.16",
        "John 3:16",
        ["Test Calvin", "Test JFB", "Test Henry"],
        generate_fn=fake,
        repository=synthetic_repo,
    )
    assert result.status == "ok"
    assert result.payload is not None
    assert len(result.payload.source_names) == 3


@pytest.mark.parametrize(
    ("sources", "expected_status"),
    [
        ([], "ineligible"),
        (["Test Calvin"], "ineligible"),
        (["Test Calvin", "Test JFB", "Test Henry", "Extra"], "ineligible"),
    ],
)
def test_run_compare_ineligible_never_calls_generate_fn(
    synthetic_repo: CommentaryRepository, sources: list[str], expected_status: str
) -> None:
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "John.3.16", "John 3:16", sources, generate_fn=fake, repository=synthetic_repo
    )
    assert result.status == expected_status
    assert fake.calls == []


def test_run_compare_provider_failure_string_not_treated_as_ok(
    synthetic_repo: CommentaryRepository,
) -> None:
    """Real bug found via browser smoke test (2026-09-03): generate_text
    (app.py) returns a warning STRING like "⚠️ Hiányzó API kulcs…" rather
    than raising when blocked -- without detecting this, that string would
    be stored/displayed as if it were a genuine grounded comparison."""
    fake = _FakeGenerate(response="⚠️ **Hiányzó API kulcs.** Add meg a Beállítások fülön...")
    result = cc.run_commentary_compare(
        "John.3.16",
        "John 3:16",
        ["Test Calvin", "Test JFB"],
        generate_fn=fake,
        repository=synthetic_repo,
    )
    assert result.status == "provider_error"
    assert result.text == ""
    assert "Hiányzó API kulcs" in result.message
    assert len(fake.calls) == 1  # the call did happen -- this is a post-hoc detection


def test_run_compare_empty_provider_response_is_provider_failure(
    synthetic_repo: CommentaryRepository,
) -> None:
    fake = _FakeGenerate(response="")
    result = cc.run_commentary_compare(
        "John.3.16",
        "John 3:16",
        ["Test Calvin", "Test JFB"],
        generate_fn=fake,
        repository=synthetic_repo,
    )
    assert result.status == "provider_error"


def test_run_compare_unavailable_db_never_calls_generate_fn(tmp_path: Path) -> None:
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "John.3.16",
        "John 3:16",
        ["Test Calvin", "Test JFB"],
        generate_fn=fake,
        database_path=tmp_path / "does_not_exist.sqlite3",
    )
    assert result.status == "unavailable"
    assert fake.calls == []


def test_run_compare_invalid_db_never_calls_generate_fn(tmp_path: Path) -> None:
    import sqlite3

    bad_db = tmp_path / "invalid.sqlite3"
    conn = sqlite3.connect(bad_db)
    conn.execute("CREATE TABLE store_metadata (key TEXT, value TEXT)")
    conn.execute("INSERT INTO store_metadata VALUES ('schema_version', '999')")
    conn.commit()
    conn.close()
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "John.3.16", "John 3:16", ["Test Calvin", "Test JFB"], generate_fn=fake, database_path=bad_db
    )
    assert result.status == "unavailable"
    assert fake.calls == []


def test_run_compare_no_generate_fn_never_crashes(synthetic_repo: CommentaryRepository) -> None:
    result = cc.run_commentary_compare(
        "John.3.16",
        "John 3:16",
        ["Test Calvin", "Test JFB"],
        generate_fn=None,
        repository=synthetic_repo,
    )
    assert result.status == "no_generate_fn"


def test_run_compare_source_no_match_excludes_it_from_prompt(
    synthetic_repo: CommentaryRepository,
) -> None:
    """John.3.20 has no Calvin -- compare must proceed with JFB+Henry
    only, never fabricate a Calvin excerpt, never substitute another
    passage or an FTS hit."""
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "John.3.20",
        "John 3:20",
        ["Test Calvin", "Test JFB", "Test Henry"],
        generate_fn=fake,
        repository=synthetic_repo,
    )
    assert result.status == "ok"
    assert result.payload is not None
    assert "Test Calvin" not in result.payload.source_names
    assert set(result.payload.source_names) == {"Test JFB", "Test Henry"}
    assert "Test Calvin" not in fake.calls[0][0]


# --- Real production-store checks ---------------------------------------


@_requires_production_commentary
@pytest.mark.parametrize(
    ("label", "reference", "sources"),
    [
        ("Calvin+JFB", "Isaiah.53.5", ["John Calvin", "David Brown"]),
        ("Calvin+Henry", "Psalms.23.1", ["John Calvin", "Mr. William Tong"]),
    ],
)
def test_real_two_source_compare_smoke(label: str, reference: str, sources: list[str]) -> None:
    # Resolve to the real contributor names actually present for this
    # passage (Psalms is by Matthew Henry himself in the real corpus --
    # verified once via retrieve_commentary_evidence in this round's own
    # audit; other books route to a named continuator instead).
    from textus_kb.retrieval import retrieve_commentary_evidence
    from textus_kb.repositories.commentary_repository import primary_contributor_name

    real_items = retrieve_commentary_evidence(reference)
    present = [primary_contributor_name(item.metadata.get("contributors")) for item in real_items]
    chosen = present[:2] if len(present) >= 2 else present
    assert len(chosen) >= 2, f"{label}: expected at least 2 real sources for {reference}"

    fake = _FakeGenerate()
    result = cc.run_commentary_compare(reference, reference, chosen, generate_fn=fake)
    assert result.status == "ok", f"{label}: {result.message}"
    assert len(fake.calls) == 1


@_requires_production_commentary
def test_real_three_source_compare_romans() -> None:
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "Romans.1.1",
        "Romans 1:1",
        ["John Calvin", "David Brown", "Mr. John Evans"],
        generate_fn=fake,
    )
    assert result.status == "ok"
    assert result.payload is not None
    assert set(result.payload.source_names) == {"John Calvin", "David Brown", "Mr. John Evans"}


@_requires_production_commentary
def test_real_revelation_jfb_henry_calvin_missing() -> None:
    fake = _FakeGenerate()
    result = cc.run_commentary_compare(
        "Revelation.1.1",
        "Revelation 1:1",
        ["A. R. Fausset", "Mr. William Tong", "John Calvin"],
        generate_fn=fake,
    )
    assert result.status == "ok"
    assert result.payload is not None
    assert "John Calvin" not in result.payload.source_names
    assert set(result.payload.source_names) == {"A. R. Fausset", "Mr. William Tong"}


@_requires_production_commentary
def test_real_harmony_primary_parallel_citation_present() -> None:
    grouped = cc.group_evidence_by_source(
        "Luke.3.23-38", ["John Calvin", "David Brown", "Matthew Henry"]
    )
    assert "John Calvin" in grouped
    payload = cc.build_compare_prompt("Luke 3:23-38", "Luke.3.23-38", grouped)
    assert "parallel_passages=" in payload.prompt or "primary_passages=" in payload.prompt
    assert "Luke.3.23-38" in payload.prompt or "Matt.1.1-17" in payload.prompt


# --- No LLM call for the retrieval-only tab; UI wiring smoke -------------


def test_commentary_ui_still_makes_no_llm_call_in_its_own_source() -> None:
    """The card-list module itself (commentary_ui.py) must still never
    reference generate_text/Gemini directly -- it only threads generate_fn
    through to commentary_compare's explicit-action section."""
    import commentary_ui

    source = Path(commentary_ui.__file__).read_text(encoding="utf-8")
    for forbidden in ("generate_text(", "genai", "Gemini", "gemini", "GEMINI"):
        assert forbidden not in source


def test_run_compare_only_called_inside_button_click_in_ui_source() -> None:
    """Static proof that render_commentary_compare_section never invokes
    run_commentary_compare outside the st.button(...) branch -- i.e.
    compare never auto-generates on passage/source-selection change."""
    import inspect

    source = inspect.getsource(cc.render_commentary_compare_section)
    button_idx = source.index("st.button(")
    call_idx = source.index("run_commentary_compare(")
    assert button_idx < call_idx


def test_commentary_ui_imports_compare_module() -> None:
    app_src = Path("commentary_ui.py").read_text(encoding="utf-8")
    assert "from commentary_compare import render_commentary_compare_section" in app_src
    assert "render_commentary_compare_section(" in app_src


def test_app_py_passes_generate_fn_to_commentary_panel() -> None:
    app_src = Path("app.py").read_text(encoding="utf-8")
    # 2026-09-03 (HU translation infra round): now also passes
    # resolve_model_fn, for the translation-provenance model/provider name.
    assert (
        "render_commentary_panel(generate_fn=generate_text, "
        "resolve_model_fn=resolve_gemini_model_for_tab)" in app_src
    )


def test_stale_result_never_shown_after_passage_change() -> None:
    """Real bug found via manual browser smoke test (2026-09-03): a
    compare generated for Róm 3,28, then switching passage to Róm 8,1-4,
    left the OLD compare result visible on screen, distinguished only by
    a small caption -- easy to miss while scrolling. A result must only
    ever render for the exact passage it was generated for."""
    ok_result = cc.CompareResult(status="ok", message="", text="some real comparison text")
    ctx_old_passage = {"passage": "Romans.3.28", "passage_display": "Róm 3,28", "sources": ("A", "B")}
    assert cc.is_result_current_for_passage(ok_result, ctx_old_passage, "Romans.3.28") is True
    assert cc.is_result_current_for_passage(ok_result, ctx_old_passage, "Romans.8.1-4") is False


def test_stale_result_check_handles_missing_or_failed_result() -> None:
    assert cc.is_result_current_for_passage(None, {"passage": "Romans.3.28"}, "Romans.3.28") is False
    assert cc.is_result_current_for_passage(None, None, "Romans.3.28") is False
    failed = cc.CompareResult(status="ineligible", message="not enough sources")
    assert cc.is_result_current_for_passage(failed, {"passage": "Romans.3.28"}, "Romans.3.28") is False


def test_compare_tab_has_a_dedicated_output_token_budget() -> None:
    """Real bug found via manual browser smoke test (2026-09-03, Róm 3,28,
    Calvin+JFB+Henry): without a dedicated entry, "Kommentárok
    összehasonlítása" fell back to the generic 4096-token ceiling and the
    real response was truncated mid-sentence (finishReason=MAX_TOKENS)
    before reaching the "Mai exegetikai megjegyzés" section. Mirrors the
    precedent in tests/test_textus_main_idea_ai.py's own budget tests."""
    import app

    label = "Kommentárok összehasonlítása"
    assert label in app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB
    budget = app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB[label]
    generic_fallback = 4096
    assert budget > generic_fallback * 2, "must clearly exceed the truncating generic default"
    assert app._default_max_output_tokens(label) == budget
    # Matches commentary_compare.py's own tab_label string exactly.
    compare_src = Path("commentary_compare.py").read_text(encoding="utf-8")
    assert f'tab_label="{label}"' in compare_src
