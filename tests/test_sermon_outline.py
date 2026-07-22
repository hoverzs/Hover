"""Igehirdetési vázlat + vázlatdiagnosztika regresszió (A–O)."""

from __future__ import annotations

import copy
import json
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_diagnostics_ai import (
    MAX_REFINEMENTS,
    MAX_STRENGTHS,
    adapt_m8_to_outline_diagnostics,
    parse_outline_diagnostics,
    run_outline_diagnostics,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    save_sermon_outline,
    save_sermon_outline_diagnostics,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import (
    MISSING_PART,
    assemble_sermon_outline,
    build_outline_from_workshop,
    outline_has_content,
    outline_part_display,
)
from sermon_workshop_ui import (
    _SW_SECTION_OPTIONS,
    _diag_view_model_simplified,
    _render_diagnostics_results,
    render_diagnostics_section,
)
from workspace_data import build_project_data, sanitize_project_data

from tests.test_jude_e2e_workflow import build_jude_state


def test_section_order_outline_then_diagnostics():
    assert _SW_SECTION_OPTIONS[-2] == "Igehirdetési vázlat"
    assert _SW_SECTION_OPTIONS[-1] == "Homiletikai diagnosztika"
    assert _SW_SECTION_OPTIONS.index("Lekciójavaslat") < _SW_SECTION_OPTIONS.index(
        "Imádsági előkészítés"
    )
    assert _SW_SECTION_OPTIONS.index("Imádsági előkészítés") < _SW_SECTION_OPTIONS.index(
        "Igehirdetési vázlat"
    )


def test_a_full_jude_outline_coherent():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    assert outline["passage_reference"]
    assert "Júd" in outline["passage_reference"] or "Jud" in outline["passage_reference"]
    assert outline["main_idea"]
    assert outline["listener_question"]
    assert outline["movements"]
    assert len(outline["movements"]) == 3
    assert outline["movements"][0]["title"] == "Emlékezzetek"
    assert outline["closing"]["final_insight"]
    assert outline["lection"]["reference"]
    assert outline["prayer_before"]["own_thoughts"]
    assert outline["prayer_after"]["own_thoughts"]


def test_b_missing_sections_show_placeholder():
    state = {"last_igehely": "Júd 17–20", SERMON_WORKSHOP_KEY: get_default_sermon_workshop()}
    ensure_sermon_workshop_state(state)
    outline = build_outline_from_workshop(state)
    assert outline_part_display(outline.get("main_idea")) == MISSING_PART
    assert outline_part_display(outline.get("opening_direction")) == MISSING_PART
    assert outline_part_display([]) == MISSING_PART
    # Ne találjon ki teológiát
    assert not outline["main_idea"]
    assert not outline["movements"]


def test_c_references_only_no_full_bible_text():
    state = build_jude_state()
    passage = state.get("passage_text") or ""
    assert len(passage) > 40
    outline = build_outline_from_workshop(state)
    blob = json.dumps(outline, ensure_ascii=False)
    # Teljes textusszöveg ne legyen a vázlatban
    assert passage[:40] not in blob
    lection_text = (state[SERMON_WORKSHOP_KEY].get("lection") or {}).get("text") or ""
    if lection_text:
        assert lection_text[:30] not in blob
    assert outline["passage_reference"]
    assert "text" not in outline.get("lection", {})


def test_d_e_prayer_retained_only_and_separated():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    before = outline["prayer_before"]
    after = outline["prayer_after"]
    assert "Adj őszinteséget" in before["own_thoughts"]
    assert "Uram, szólj hozzánk." in before["selected_opening"]
    assert "Nyisd meg a szívünket." in before["selected_lines"]
    assert "Köszönjük, Uram." in after["selected_opening"]
    assert "Köszönjük, hogy megtartasz." in after["selected_lines"]
    # Előtti / utáni ne keveredjen
    assert "Köszönjük, Uram." not in before["selected_opening"]
    assert "Uram, szólj hozzánk." not in after["selected_opening"]
    # Elutasított / nyers javaslatlista nincs
    suggestions = state[SERMON_WORKSHOP_KEY]["prayer_preparation"].get(
        "before_suggestions"
    )
    assert suggestions
    blob = json.dumps(before, ensure_ascii=False)
    assert "before_suggestions" not in blob


def test_f_movement_order_preserved():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    titles = [m["title"] for m in outline["movements"]]
    assert titles == ["Emlékezzetek", "Gúnyolódók", "Megmaradás"]


def test_g_enrichment_attached_to_movements():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    mv3 = outline["movements"][2]
    assert any("épülő ház" in x for x in mv3["images"])
    assert any("horgony" in x.lower() or "Horgony" in x for x in mv3["illustrations"])
    assert any("ima" in x.lower() for x in mv3["applications"])


def test_h_no_silent_overwrite_manual_edit():
    state = build_jude_state()
    first = assemble_sermon_outline(state, force_overwrite=True)
    assert first.ok
    save_sermon_outline(state, first.outline, mark_manual_edit=False)
    # Kézi szerkesztés jelölése
    edited = dict(first.outline)
    edited["main_idea"] = "Kézzel átírt fő gondolat"
    edited["manually_edited"] = True
    save_sermon_outline(state, edited, mark_manual_edit=True)
    blocked = assemble_sermon_outline(state, force_overwrite=False)
    assert not blocked.ok
    assert "kézzel" in blocked.error_message.casefold() or "szerkeszt" in blocked.error_message.casefold()
    assert state[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"] == "Kézzel átírt fő gondolat"
    forced = assemble_sermon_outline(state, force_overwrite=True)
    assert forced.ok
    save_sermon_outline(state, forced.outline, mark_manual_edit=False)
    assert "Kézzel átírt" not in state[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"]


def test_i_old_project_loads():
    legacy = normalize_sermon_workshop(
        {
            "sermon_main_idea": "régi",
            "sermon_main_idea_status": "approved",
            "closing": {"final_discovery": "x"},
        }
    )
    assert "sermon_outline" in legacy
    assert legacy["sermon_outline"]["main_idea"] == ""
    assert legacy["sermon_outline_status"] == "draft"
    assert legacy["sermon_outline_diagnostics"] == {} or legacy[
        "sermon_outline_diagnostics"
    ].get("overview", "") == ""
    assert legacy["sermon_main_idea"] == "régi"


def test_j_save_reload_outline():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    save_sermon_outline(state, outline)
    payload = build_project_data(state)
    clean = sanitize_project_data(payload)
    reloaded = normalize_sermon_workshop(clean[SERMON_WORKSHOP_KEY])
    assert reloaded["sermon_outline"]["main_idea"] == outline["main_idea"]
    assert len(reloaded["sermon_outline"]["movements"]) == 3
    assert reloaded["sermon_outline"]["prayer_before"]["selected_opening"]


def test_k_project_switch_no_mix():
    a = build_jude_state()
    b = build_jude_state()
    oa = build_outline_from_workshop(a)
    oa["main_idea"] = "Projekt A vázlat"
    save_sermon_outline(a, oa)
    ob = build_outline_from_workshop(b)
    ob["main_idea"] = "Projekt B vázlat"
    save_sermon_outline(b, ob)
    assert a[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"] == "Projekt A vázlat"
    assert b[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"] == "Projekt B vázlat"
    payload_a = sanitize_project_data(build_project_data(a))
    payload_b = sanitize_project_data(build_project_data(b))
    assert (
        payload_a[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"]
        != payload_b[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"]
    )


def test_l_m_diagnostics_max_three_no_fake_third():
    raw = json.dumps(
        {
            "overview": "Koherens vázlat.",
            "strengths": ["a", "b", "c", "d"],
            "refinements": [
                {"title": "Egy", "explanation": "e1", "suggested_action": "s1"},
                {"title": "Kettő", "explanation": "e2", "suggested_action": "s2"},
            ],
            "ready_to_use": True,
            "next_step": "Mehet.",
            "detailed_notes": ["n1"],
            "warnings": [],
        },
        ensure_ascii=False,
    )
    parsed = parse_outline_diagnostics(raw)
    assert len(parsed.strengths) <= MAX_STRENGTHS
    assert len(parsed.refinements) <= MAX_REFINEMENTS
    assert len(parsed.refinements) == 2  # ne gyártson harmadikat


def test_n_no_outline_gates_diagnostics():
    result = run_outline_diagnostics(sermon_outline={})
    assert result.missing_outline
    assert "vázlat" in result.error_message.casefold()


def test_diagnostics_does_not_mutate_outline():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    save_sermon_outline(state, outline)
    before = copy.deepcopy(state[SERMON_WORKSHOP_KEY]["sermon_outline"])
    before_idea = state[SERMON_WORKSHOP_KEY]["sermon_main_idea"]
    diag = run_outline_diagnostics(
        sermon_outline=before,
        sermon_main_idea=before_idea,
        generate_fn=None,
    )
    assert diag.ok
    save_sermon_outline_diagnostics(state, diag.to_dict())
    assert state[SERMON_WORKSHOP_KEY]["sermon_outline"] == before
    assert state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] == before_idea


def test_christ_connection_human_label():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    assert outline["christ_connection_type_label"] == "Közvetlen kapcsolat"
    assert outline["christ_connection_type_label"] != "direct"


def test_adapt_legacy_m8():
    adapted = adapt_m8_to_outline_diagnostics(
        {
            "overall_summary": "Összkép",
            "major_strengths": ["s1", "s2", "s3", "s4"],
            "revision_priorities": [
                {
                    "title": "t1",
                    "why_it_matters": "w",
                    "recommended_action": "a",
                    "affected_sections": ["M6"],
                }
            ]
            * 5,
            "ready_for_next_stage": False,
            "readiness_note": "Finomíts.",
        }
    )
    assert adapted.overview == "Összkép"
    assert len(adapted.strengths) == 3
    assert len(adapted.refinements) == 3


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state


def test_diagnostics_ui_gate_and_simplified_view(session, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(st, "markdown", lambda *a, **k: calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(st, "caption", lambda *a, **k: calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(st, "warning", lambda *a, **k: calls.append(f"WARN:{a[0]}" if a else "WARN"))
    monkeypatch.setattr(st, "subheader", lambda *a, **k: calls.append(f"H:{a[0]}" if a else ""))
    monkeypatch.setattr(st, "button", lambda *a, **k: False)
    monkeypatch.setattr(
        st,
        "expander",
        lambda label, expanded=False: (
            calls.append(f"EXP:{label}:{expanded}") or nullcontext()
        ),
    )
    monkeypatch.setattr(st, "columns", lambda n: [nullcontext() for _ in range(n)])
    monkeypatch.setattr(st, "info", lambda *a, **k: None)
    monkeypatch.setattr(st, "success", lambda *a, **k: None)
    monkeypatch.setattr(st, "error", lambda *a, **k: None)
    monkeypatch.setattr(st, "text_area", lambda *a, **k: "")
    monkeypatch.setattr(st, "text_input", lambda *a, **k: "")
    monkeypatch.setattr(st, "rerun", lambda: None)

    render_diagnostics_section(generate_fn=None)
    assert any("vázlatot" in c.casefold() for c in calls)

    # With outline + diagnostics
    jude = build_jude_state()
    outline = build_outline_from_workshop(jude)
    save_sermon_outline(session, outline)
    save_sermon_outline_diagnostics(
        session,
        {
            "overview": "Jó vázlat.",
            "strengths": ["Erő1", "Erő2"],
            "refinements": [
                {
                    "title": "Finom1",
                    "explanation": "Miért",
                    "suggested_action": "Tedd",
                }
            ],
            "ready_to_use": True,
            "next_step": "Mehet tovább.",
            "detailed_notes": ["Részlet"],
            "warnings": [],
        },
    )
    calls.clear()
    _render_diagnostics_results()
    joined = "\n".join(calls)
    assert "Rövid összkép" in joined
    assert "Ami már jól működik" in joined
    assert "Ezen érdemes még finomítani" in joined
    assert "Továbbhaladás" in joined
    assert any(
        "Részletesebb homiletikai megjegyzések" in c for c in calls
    )
    assert "Gyors státusz" not in joined
    assert "sw-diag-prio-card" in joined


def test_view_model_limits():
    view = _diag_view_model_simplified(
        {
            "overview": "o",
            "strengths": ["1", "2", "3", "4"],
            "refinements": [{"title": str(i)} for i in range(5)],
            "ready_to_use": False,
            "next_step": "n",
        }
    )
    assert len(view["strengths"]) <= 3
    assert len(view["refinements"]) <= 3


def test_outline_has_content_helper():
    assert not outline_has_content({})
    assert not outline_has_content({"status": "draft", "bible_translation": "RÚF"})
    assert outline_has_content({"main_idea": "Van tartalom"})
