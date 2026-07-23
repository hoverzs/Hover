# ruff: noqa: E402
"""Vázlat kanonikus content + állapot / jóváhagyás regresszió."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_diagnostics_ai import _outline_context_block, run_outline_diagnostics
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    normalize_sermon_outline,
    save_sermon_outline,
)
from sermon_workshop_outline_ai import (
    assemble_sermon_outline,
    outline_canonical_text,
    outline_has_content,
    repair_outline_integrity,
    sync_outline_content,
)
from sermon_workshop_ui import (
    _KEY_OUTLINE,
    _assemble_and_save_outline,
    _persist_outline_from_widgets,
)
from workshop_nav_ui import sermon_completed_sections


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    return state


def _partial_workshop(state: dict) -> None:
    ensure_sermon_workshop_state(state)
    sw = state[SERMON_WORKSHOP_KEY]
    sw["sermon_main_idea"] = "Isten kegyelme megújítja a fáradt szívet."
    sw["sermon_main_idea_status"] = "draft"
    sw["listener_tension"] = {
        "listener_question": "Miért nem elég a saját erőnk?",
        "sermon_tension": "A fáradtság és a kegyelem feszültsége",
        "listener_resistance": "Mégis magunkat erőltetjük",
        "promised_resolution": "Krisztus pihenést ad",
    }
    sw["christ_centered_arc"] = {
        "divine_gracious_action": "Isten eljön a fáradthoz",
        "christ_connection": "Mt 11,28",
        "christ_connection_type": "direct",
        "grace_enabled_response": "Elfogadni a pihenést",
    }
    state["last_igehely"] = "Mt 11,28–30"
    state["passage_reference"] = "Mt 11,28–30"
    state["passage_text"] = "Jöjjetek énhozzám mindnyájan..."


def test_partial_workshop_builds_nonempty_outline(session):
    _partial_workshop(session)
    result = assemble_sermon_outline(session, synthesize=False, polish=False)
    assert result.ok
    assert outline_has_content(result.outline)
    text = outline_canonical_text(result.outline)
    assert "fókuszmondat" in text.lower() or "Fókuszmondat" in text
    assert "Isten kegyelme" in text
    assert result.outline.get("content", "").strip()
    assert "Saját megjegyzés" not in text


def test_notes_alone_are_not_outline_content():
    shell = normalize_sermon_outline(
        {
            "status": "approved",
            "manual_notes": "csak jegyzet",
            "updated_at": "2026-01-01T00:00:00",
            "passage_reference": "Mt 11",
            "lection_reference": "Zsolt 23",
        }
    )
    assert not outline_has_content(shell)
    repaired, changed = repair_outline_integrity(shell)
    assert changed
    assert repaired["status"] != "approved"
    assert repaired.get("needs_rebuild") is True


def test_approved_empty_is_invalid_state():
    raw = {
        "status": "approved",
        "content": "",
        "manual_notes": "x",
        "updated_at": "2026-07-01T12:00:00",
    }
    repaired, changed = repair_outline_integrity(raw)
    assert changed
    assert not outline_has_content(repaired)
    assert repaired["status"] in {"draft", "empty"}


def test_generated_outline_appears_immediately(session, monkeypatch):
    _partial_workshop(session)
    messages: list[str] = []

    def _md(text, *a, **k):
        messages.append(str(text))

    monkeypatch.setattr(st, "markdown", _md)
    monkeypatch.setattr(st, "info", lambda *a, **k: None)
    monkeypatch.setattr(st, "success", lambda *a, **k: None)
    monkeypatch.setattr(st, "warning", lambda *a, **k: None)
    monkeypatch.setattr(st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(st, "button", lambda *a, **k: False)
    monkeypatch.setattr(st, "columns", lambda *a, **k: [nullctx(), nullctx()])
    monkeypatch.setattr(st, "expander", lambda *a, **k: nullctx())
    monkeypatch.setattr(st, "container", lambda *a, **k: nullctx())
    monkeypatch.setattr(st, "text_area", lambda *a, **k: "")
    monkeypatch.setattr(st, "spinner", lambda *a, **k: nullctx())
    monkeypatch.setattr(st, "rerun", lambda: None)

    result = assemble_sermon_outline(session, synthesize=False, polish=False)
    save_sermon_outline(session, result.outline, mark_manual_edit=False)
    from sermon_workshop_outline_ai import render_compact_sermon_outline

    render_compact_sermon_outline(result.outline)
    blob = "\n".join(messages)
    assert "Isten kegyelme" in blob
    assert "Vázlat előnézete" not in blob  # preview title is outside compact render


class nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return lambda *a, **k: None


def test_outline_editable_and_persists(session):
    _partial_workshop(session)
    result = assemble_sermon_outline(session, synthesize=False, polish=False)
    save_sermon_outline(session, result.outline, mark_manual_edit=False)
    st.session_state.clear()
    st.session_state.update(session)
    edited = (result.outline.get("content") or "") + "\n\nKézi kiegészítés."
    st.session_state[_KEY_OUTLINE["content"]] = edited
    st.session_state[_KEY_OUTLINE["manual_notes"]] = "csak jegyzet"
    _persist_outline_from_widgets(mark_manual_edit=True)
    saved = normalize_sermon_outline(session[SERMON_WORKSHOP_KEY]["sermon_outline"])
    assert "Kézi kiegészítés" in (saved.get("content") or "")
    assert saved.get("manual_notes") == "csak jegyzet"
    # újratöltés szimuláció
    reloaded = normalize_sermon_outline(
        dict(session[SERMON_WORKSHOP_KEY]["sermon_outline"])
    )
    assert "Kézi kiegészítés" in (reloaded.get("content") or "")
    assert outline_has_content(reloaded)


def test_empty_outline_cannot_be_approved(session):
    ensure_sermon_workshop_state(session)
    empty = normalize_sermon_outline(
        {"status": "approved", "manual_notes": "jegyzet", "content": ""}
    )
    save_sermon_outline(session, empty, mark_manual_edit=False)
    saved = normalize_sermon_outline(session[SERMON_WORKSHOP_KEY]["sermon_outline"])
    assert saved.get("status") != "approved"
    assert not outline_has_content(saved)
    assert "Igehirdetési vázlat" not in sermon_completed_sections(session)


def test_notes_do_not_substitute_outline():
    assert not outline_has_content({"manual_notes": "Ez nem vázlat, csak jegyzet."})
    assert outline_has_content({"main_idea": "Valódi fő gondolat a textusból."})


def test_diagnostics_receives_canonical_outline_text(session):
    _partial_workshop(session)
    result = assemble_sermon_outline(session, synthesize=False, polish=False)
    save_sermon_outline(session, result.outline, mark_manual_edit=False)
    block = _outline_context_block(result.outline)
    assert "Isten kegyelme" in block
    assert "content" in block
    assert "csak jegyzet" not in block
    diag = run_outline_diagnostics(
        sermon_outline=result.outline,
        generate_fn=None,
        prefer_local_heuristic=True,
    )
    assert diag.ok
    assert not diag.missing_outline


def test_diagnostics_refuses_empty_outline():
    diag = run_outline_diagnostics(
        sermon_outline={"manual_notes": "jegyzet", "status": "approved"},
        generate_fn=None,
    )
    assert diag.missing_outline
    assert not diag.ok


def test_ai_failure_no_false_success(session, monkeypatch):
    _partial_workshop(session)
    warnings: list[str] = []
    errors: list[str] = []
    successes: list[str] = []

    def _boom(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr(st, "spinner", lambda *a, **k: nullctx())
    monkeypatch.setattr(st, "warning", lambda m, *a, **k: warnings.append(str(m)))
    monkeypatch.setattr(st, "error", lambda m, *a, **k: errors.append(str(m)))
    monkeypatch.setattr(st, "success", lambda m, *a, **k: successes.append(str(m)))
    monkeypatch.setattr(st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(st, "rerun", lambda: None)

    # synthesize=True with failing generate_fn still keeps local outline → success OK
    # False success path: assemble returns ok=False
    from sermon_workshop_outline_ai import OutlineAssemblyResult

    monkeypatch.setattr(
        "sermon_workshop_ui.assemble_sermon_outline",
        lambda *a, **k: OutlineAssemblyResult(
            ok=False, error_message="Generálási hiba: network"
        ),
    )
    _assemble_and_save_outline(generate_fn=_boom, force_overwrite=True)
    assert successes == []
    assert any("nem sikerült" in w.lower() or "hiba" in w.lower() for w in warnings)


def test_approved_outline_still_visible(session):
    _partial_workshop(session)
    result = assemble_sermon_outline(session, synthesize=False, polish=False)
    outline = sync_outline_content(result.outline, force=True)
    outline["status"] = "approved"
    save_sermon_outline(session, outline, mark_manual_edit=False)
    session[SERMON_WORKSHOP_KEY]["sermon_outline_status"] = "approved"
    saved = normalize_sermon_outline(session[SERMON_WORKSHOP_KEY]["sermon_outline"])
    assert outline_has_content(saved)
    assert outline_canonical_text(saved)
    assert "Igehirdetési vázlat" in sermon_completed_sections(session)
