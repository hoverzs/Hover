# ruff: noqa: E402
"""Homiletikai diagnózis — kritikus funkcionális regressziók."""

from __future__ import annotations

import copy
import re
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_diagnostics_ai import run_outline_diagnostics
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    normalize_sermon_workshop,
    save_sermon_outline,
    save_sermon_outline_diagnostics,
    set_sermon_outline_diagnostics_status,
    _diagnostics_has_result,
)
from sermon_workshop_outline_ai import (
    assemble_sermon_outline,
    build_outline_from_workshop,
    outline_has_content,
    sync_outline_content,
)
from sermon_workshop_ui import (
    _diag_active_source,
    _diag_is_stale,
    _run_outline_homiletical_diagnostics,
    render_diagnostics_section,
)
from tests.test_jude_e2e_workflow import build_jude_state
from workspace_data import build_project_data, sanitize_project_data


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state


def _contentful_draft_outline(state: dict) -> dict:
    jude = build_jude_state()
    state.clear()
    state.update(jude)
    ensure_sermon_workshop_state(state)
    outline = build_outline_from_workshop(state)
    outline = sync_outline_content(outline, force=True)
    if not outline_has_content(outline):
        # Biztos tartalom a kanonikus mezőben
        outline["content"] = (
            "Cím: Maradjatok a hitben\n"
            "Textus: Júdás 17–20\n"
            "Fókuszmondat: Az apostoli emlékeztetés őriz meg a szakadás ellen.\n"
            "Bevezetés: A közösség feszültségében megszólal az emlékeztetés.\n"
            "1. Mozgás: Emlékezzetek az apostoli szóra.\n"
            "Megérkezés: Épüljetek a legszentebb hiten."
        )
        outline["main_idea"] = (
            "Az apostoli emlékeztetés őriz meg a szakadás ellen."
        )
    outline["status"] = "draft"
    assert outline_has_content(outline)
    save_sermon_outline(state, outline, mark_manual_edit=False)
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea_status"] = "draft"
    return outline


def _stub_streamlit_run(monkeypatch, *, calls: list | None = None) -> list:
    log = calls if calls is not None else []
    monkeypatch.setattr(st, "spinner", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "warning", lambda m, *a, **k: log.append(("warn", str(m))))
    monkeypatch.setattr(st, "error", lambda m, *a, **k: log.append(("error", str(m))))
    monkeypatch.setattr(st, "success", lambda m, *a, **k: log.append(("ok", str(m))))
    monkeypatch.setattr(st, "info", lambda m, *a, **k: log.append(("info", str(m))))
    monkeypatch.setattr(st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(st, "rerun", lambda: log.append(("rerun",)))
    return log


def test_draft_outline_without_approved_focus_runs_diagnostics(session):
    outline = _contentful_draft_outline(session)
    assert session[SERMON_WORKSHOP_KEY]["sermon_main_idea_status"] != "approved"
    diag = run_outline_diagnostics(
        sermon_outline=outline,
        sermon_main_idea=outline.get("main_idea") or "",
        generate_fn=None,
    )
    assert diag.ok
    assert not diag.missing_outline


def test_approved_outline_runs_diagnostics(session):
    outline = _contentful_draft_outline(session)
    outline["status"] = "approved"
    save_sermon_outline(session, outline, mark_manual_edit=False)
    session[SERMON_WORKSHOP_KEY]["sermon_outline_status"] = "approved"
    diag = run_outline_diagnostics(sermon_outline=outline, generate_fn=None)
    assert diag.ok


def test_partial_workshop_runs_diagnostics(session):
    jude = build_jude_state()
    session.clear()
    session.update(jude)
    ensure_sermon_workshop_state(session)
    # Csak részleges műhely: töröljük a hallgatói feszültséget / lezárást.
    session[SERMON_WORKSHOP_KEY]["listener_tension"] = {}
    session[SERMON_WORKSHOP_KEY]["closing"] = {}
    session[SERMON_WORKSHOP_KEY]["sermon_main_idea_status"] = "draft"
    result = assemble_sermon_outline(session, synthesize=False, polish=False)
    if not result.ok or not outline_has_content(result.outline):
        outline = _contentful_draft_outline(session)
    else:
        outline = sync_outline_content(result.outline, force=True)
        save_sermon_outline(session, outline, mark_manual_edit=False)
    diag = run_outline_diagnostics(sermon_outline=outline, generate_fn=None)
    assert diag.ok
    assert not diag.missing_outline


def test_first_run_persists_after_ensure(session, monkeypatch):
    _contentful_draft_outline(session)
    _stub_streamlit_run(monkeypatch)
    _run_outline_homiletical_diagnostics(generate_fn=None, prefer_local_heuristic=True)
    sw = ensure_sermon_workshop_state(session)
    assert _diagnostics_has_result(sw.get("sermon_outline_diagnostics"))
    assert sw.get("sermon_outline_diagnostics_status") == "ready"
    assert sw.get("sermon_outline_diagnostics_generated_at")
    # Rerun / ensure nem törli
    sw2 = ensure_sermon_workshop_state(session)
    assert _diagnostics_has_result(sw2.get("sermon_outline_diagnostics"))
    _, _, has = _diag_active_source()
    assert has is True


def test_project_save_reload_keeps_diagnosis(session, monkeypatch):
    _contentful_draft_outline(session)
    _stub_streamlit_run(monkeypatch)
    _run_outline_homiletical_diagnostics(generate_fn=None, prefer_local_heuristic=True)
    payload = build_project_data(session)
    clean = sanitize_project_data(payload)
    restored: dict = {}
    restored[SERMON_WORKSHOP_KEY] = normalize_sermon_workshop(
        clean.get(SERMON_WORKSHOP_KEY)
    )
    assert _diagnostics_has_result(
        restored[SERMON_WORKSHOP_KEY].get("sermon_outline_diagnostics")
    )
    assert restored[SERMON_WORKSHOP_KEY].get(
        "sermon_outline_diagnostics_generated_at"
    )
    assert restored[SERMON_WORKSHOP_KEY].get("sermon_outline_diagnostics_status") in (
        "ready",
        "idle",
    )


def test_outline_edit_keeps_old_diag_marked_stale(session, monkeypatch):
    outline = _contentful_draft_outline(session)
    _stub_streamlit_run(monkeypatch)
    _run_outline_homiletical_diagnostics(generate_fn=None, prefer_local_heuristic=True)
    source, generated, has = _diag_active_source()
    assert has
    # Vázlat módosítása későbbi időbélyeggel
    outline = dict(outline)
    outline["main_idea"] = (outline.get("main_idea") or "") + " (módosítva)"
    save_sermon_outline(session, outline, mark_manual_edit=True)
    # Erősítsük a későbbi frissítést (ugyanazon másodperc elkerülése)
    session[SERMON_WORKSHOP_KEY]["sermon_outline_updated_at"] = "2099-01-01T00:00:00"
    assert _diagnostics_has_result(
        session[SERMON_WORKSHOP_KEY].get("sermon_outline_diagnostics")
    )
    assert _diag_is_stale(source, generated) is True


def test_api_error_shows_message_keeps_previous(session, monkeypatch):
    _contentful_draft_outline(session)
    log = _stub_streamlit_run(monkeypatch)
    # Először sikeres helyi diagnózis
    _run_outline_homiletical_diagnostics(generate_fn=None, prefer_local_heuristic=True)
    before = copy.deepcopy(session[SERMON_WORKSHOP_KEY]["sermon_outline_diagnostics"])
    before_at = session[SERMON_WORKSHOP_KEY]["sermon_outline_diagnostics_generated_at"]

    def boom(*_a, **_k):
        raise RuntimeError("hálózat megszakadt")

    _run_outline_homiletical_diagnostics(generate_fn=boom)
    sw = ensure_sermon_workshop_state(session)
    assert sw["sermon_outline_diagnostics"] == before
    assert sw["sermon_outline_diagnostics_generated_at"] == before_at
    assert sw["sermon_outline_diagnostics_status"] == "error"
    err = str(sw.get("sermon_outline_diagnostics_error") or "")
    assert "nem készült el" in err.casefold()
    assert "vázlat változatlanul megmaradt" in err.casefold()
    # Ne maradjon running
    assert sw["sermon_outline_diagnostics_status"] != "running"
    assert not session.get("_sw_outline_diag_running")


def test_empty_outline_no_api_call_and_guidance(session, monkeypatch):
    calls: list = []

    def should_not_run(*_a, **_k):
        calls.append("api")
        return "{}"

    log: list = []
    monkeypatch.setattr(st, "spinner", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "warning", lambda m, *a, **k: log.append(str(m)))
    monkeypatch.setattr(st, "error", lambda m, *a, **k: log.append(str(m)))
    monkeypatch.setattr(st, "success", lambda m, *a, **k: None)
    monkeypatch.setattr(st, "info", lambda m, *a, **k: None)
    monkeypatch.setattr(st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(st, "columns", lambda *a, **k: [nullcontext(), nullcontext()])
    monkeypatch.setattr(st, "button", lambda *a, **k: False)
    monkeypatch.setattr(st, "rerun", lambda: None)

    from ui_components import render_empty_state, render_page_intro

    monkeypatch.setattr(
        "sermon_workshop_ui.render_page_intro",
        lambda **k: log.append(k.get("title", "")),
    )
    monkeypatch.setattr(
        "sermon_workshop_ui.render_empty_state",
        lambda **k: log.append(k.get("title", "")),
    )

    render_diagnostics_section(generate_fn=should_not_run)
    assert calls == []
    joined = " ".join(log)
    assert "Előbb készíts igehirdetési vázlatot" in joined or any(
        "vázlat" in str(x).casefold() for x in log
    )


def test_no_duplicate_diag_widget_keys():
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    keys = re.findall(r'key\s*=\s*"(sw_diag_[^"]+)"', src)
    assert keys
    assert len(keys) == len(set(keys)), f"duplikált kulcsok: {keys}"


def test_parse_repair_retry_once(session):
    outline = _contentful_draft_outline(session)
    calls: list[str] = []

    def flaky(*_a, **_k):
        calls.append("x")
        if len(calls) == 1:
            return "ez nem json"
        return (
            '{"overview":"Jó irány.","strengths":["Van fő gondolat."],'
            '"refinements":[],"diagnostic_areas":[],"ready_to_use":true,'
            '"next_step":"Kidolgozás."}'
        )

    diag = run_outline_diagnostics(sermon_outline=outline, generate_fn=flaky)
    assert diag.ok
    assert len(calls) == 2


def test_error_survives_normalize(session):
    set_sermon_outline_diagnostics_status(
        session, "error", error_message="A diagnosztika most nem készült el: teszt."
    )
    sw = ensure_sermon_workshop_state(session)
    assert sw["sermon_outline_diagnostics_status"] == "error"
    assert "teszt" in sw["sermon_outline_diagnostics_error"]
