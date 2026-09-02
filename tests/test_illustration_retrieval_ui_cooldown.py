"""PHASE 3I.3 (2026-08-28): root-caused a live-vs-diagnostic-script
discrepancy -- the deployed "Illusztrációk keresése" action returned 0
results for EVERY tested passage, while a standalone read-only
diagnostic script (Phase 3I.2's audit) found real matches on the same
corpus.

Root cause: `retrieve_illustrations` makes TWO sequential logical
Gemini calls per search (Stage 0 planner, then Stage B ranker) via
`app.py`'s `generate_text`. `generate_text` enforces an 8-second GLOBAL
cooldown between ANY two logical calls and, when a call lands inside
that window, returns a Hungarian "please wait" warning STRING instead
of raising or waiting -- indistinguishable, to `parse_ranking_response`,
from any other unparseable non-JSON response, so it correctly failed
closed to an empty result. Since a single Gemini call rarely takes 8+
seconds, the SECOND call (the ranker) landed inside the cooldown window
on (almost) every search -- deterministically, regardless of passage.

Fix: pass `bypass_cooldown=True` on the injected `_llm` callback in
`illustration_retrieval_ui.py`, mirroring `generate_text`'s own
documented convention for multiple logical calls within one click
("ugyanazon gombnyomás fill/repair hívásai").

Source-level regression check (the `illustration_retrieval_ui.py`
convention already established by `tests/test_illustration_legacy_
generation_removed.py` -- `_llm` is a closure inside `render_
illustration_search_action`, not callable in isolation without a full
Streamlit session context, so a source-string assertion is the
project's established, pragmatic way to pin this down for a
Streamlit-UI-adjacent module)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_UI_SRC = (ROOT / "illustration_retrieval_ui.py").read_text(encoding="utf-8")


def test_llm_callback_bypasses_cooldown():
    start = RETRIEVAL_UI_SRC.index("def _llm(prompt: str) -> str:")
    end = RETRIEVAL_UI_SRC.index("\n\n", start)
    body = RETRIEVAL_UI_SRC[start:end]
    assert "bypass_cooldown=True" in body


def test_llm_callback_still_disables_cache():
    """The cooldown fix must not accidentally also start caching
    results across different passages/searches."""
    start = RETRIEVAL_UI_SRC.index("def _llm(prompt: str) -> str:")
    end = RETRIEVAL_UI_SRC.index("\n\n", start)
    body = RETRIEVAL_UI_SRC[start:end]
    assert "use_cache=False" in body


def test_retrieval_call_uses_diagnostics_variant():
    """Phase 3I.3 point 4: the UI must call the diagnostics-returning
    entry point (not the plain one) so a dev-mode reason code is always
    available -- without changing what a production end user sees."""
    assert "retrieve_illustrations_with_diagnostics(" in RETRIEVAL_UI_SRC
    assert "from illustration_engine.retrieval import (" in RETRIEVAL_UI_SRC


def test_dev_diagnostics_only_rendered_in_development_mode():
    start = RETRIEVAL_UI_SRC.index("if st.session_state.get(_SEARCHED_KEY):")
    end = RETRIEVAL_UI_SRC.index("\n        else:", start)
    body = RETRIEVAL_UI_SRC[start:end]
    assert 'mode == "development"' in body
    assert "_render_dev_diagnostics(" in body


def test_dev_diagnostics_renderer_never_calls_generate_fn_or_prints_raw_llm_text():
    """The diagnostics panel must stay structured/content-free -- no
    raw prompt/response text, no re-invocation of the LLM."""
    start = RETRIEVAL_UI_SRC.index("def _render_dev_diagnostics(")
    end = RETRIEVAL_UI_SRC.index("\n\n\n", start)
    body = RETRIEVAL_UI_SRC[start:end]
    assert "generate_fn(" not in body
    assert "llm_generate(" not in body
