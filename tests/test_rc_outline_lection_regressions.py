# ruff: noqa: E402
"""RC regresszió: vázlat üres-widget törlés + lekció hamis siker."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    save_sermon_outline,
)
from sermon_workshop_m9_lection_ai import suggest_lections
from sermon_workshop_outline_ai import assemble_sermon_outline, outline_has_content
from sermon_workshop_ui import (
    _KEY_OUTLINE,
    _KEY_OUTLINE_CLOSING,
    _OUTLINE_MV_PREFIX,
    _persist_outline_from_widgets,
    _read_outline_from_widgets,
)
from tests.test_jude_e2e_workflow import build_jude_state
from workshop_nav_ui import sermon_completed_sections


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    return state


def _stub_json(payload: dict):
    raw = json.dumps(payload, ensure_ascii=False)

    def _fn(*_a, **_k):
        return raw

    return _fn


def test_stale_empty_widgets_do_not_wipe_outline_on_flush(session):
    state = build_jude_state()
    result = assemble_sermon_outline(state, synthesize=False, polish=False)
    assert result.ok
    save_sermon_outline(state, result.outline, mark_manual_edit=False)
    before_idea = str(state[SERMON_WORKSHOP_KEY]["sermon_outline"].get("main_idea") or "")
    assert before_idea.strip()

    st.session_state.clear()
    st.session_state.update(state)
    for _field, wkey in _KEY_OUTLINE.items():
        st.session_state[wkey] = ""
    for _field, wkey in _KEY_OUTLINE_CLOSING.items():
        st.session_state[wkey] = ""
    for mv in state[SERMON_WORKSHOP_KEY]["sermon_outline"].get("movements") or []:
        mid = str(mv.get("id") or "")
        for field in (
            "title",
            "core_content",
            "textual_basis",
            "listener_discovery",
            "transition",
            "role_label",
            "images",
            "illustrations",
            "applications",
        ):
            st.session_state[f"{_OUTLINE_MV_PREFIX}{mid}_{field}"] = ""

    _persist_outline_from_widgets(mark_manual_edit=None)
    after = st.session_state[SERMON_WORKSHOP_KEY]["sermon_outline"]
    assert outline_has_content(after)
    assert str(after.get("main_idea") or "").strip() == before_idea.strip()


def test_approve_rejects_empty_shell_and_keeps_content(session):
    state = build_jude_state()
    result = assemble_sermon_outline(state, synthesize=False, polish=False)
    save_sermon_outline(state, result.outline, mark_manual_edit=False)
    st.session_state.clear()
    st.session_state.update(state)

    for _field, wkey in _KEY_OUTLINE.items():
        st.session_state[wkey] = ""
    merged = _read_outline_from_widgets(protect_nonempty=True)
    assert outline_has_content(merged)

    # Héj: csak igehely + üres mozgások / tone → ne számítson tartalomnak
    shell = {
        "passage_reference": "Júd 17–20",
        "movements": [
            {
                "id": "mv-a",
                "title": "",
                "role": "opening",
                "role_label": "",
                "textual_basis": "",
                "core_content": "",
                "listener_discovery": "",
                "transition": "",
                "images": [],
                "illustrations": [],
                "applications": [],
            }
        ],
        "closing": {
            "final_insight": "",
            "gospel_assurance": "",
            "invitation": "",
            "image_or_line": "",
            "open_question": "",
            "tone": "hopeful",
            "tone_label": "",
        },
        "status": "approved",
    }
    assert not outline_has_content(shell)
    completed = sermon_completed_sections(
        {SERMON_WORKSHOP_KEY: {"sermon_outline": shell, "sermon_outline_status": "approved"}}
    )
    assert "Igehirdetési vázlat" not in completed


def test_lection_insufficient_is_not_false_success():
    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="",
        sermon_main_idea="",
        text_main_idea="",
        lection_user_focus="",
        generate_fn=_stub_json({"recommended_lection": {"reference": "Jn 1,1"}}),
        skip_api_if_insufficient=True,
    )
    assert result.ok is False
    assert not (result.recommended_lection and result.recommended_lection.reference)
    assert result.error_message


def test_lection_draft_main_idea_and_passage_text_is_sufficient():
    payload = {
        "recommended_lection": {
            "reference": "Jn 15,1–11",
            "connection_type": "gospel_complement",
            "rationale": "A szőlőtő képe a megtartó kegyelmet hordozza.",
            "liturgical_function": "Előkészíti a hitben való megmaradást.",
            "estimated_length": "standard",
            "warnings": [],
        },
        "alternative_lections": [],
        "overall_reasoning": "Részleges anyag alapján.",
        "basis": ["sermon_main_idea"],
        "no_separate_lection_needed": False,
        "no_lection_reason": "",
        "warnings": [],
        "missing_information": [],
    }
    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="17 Ti pedig, szeretteim…",
        sermon_main_idea="Isten megtartja népét a gúnyolódók között is.",
        sermon_main_idea_status="draft",
        text_main_idea="",
        text_main_idea_status="draft",
        lection_user_focus="",
        generate_fn=_stub_json(payload),
        skip_api_if_insufficient=True,
    )
    assert result.ok
    assert result.recommended_lection.reference == "Jn 15,1–11"


def test_lection_uses_outline_in_context():
    outline = {
        "main_idea": "Maradjatok meg Isten szeretetében.",
        "opening_direction": "A gyülekezet feszültsége a gúnyolódással.",
        "movements": [
            {"id": "1", "title": "Emlékezzetek", "core_content": "Az apostolok szavára."}
        ],
        "closing": {"final_insight": "A Szentlélek megtart."},
    }
    captured: dict = {}

    def _capture(prompt: str, **_k):
        captured["prompt"] = prompt
        return json.dumps(
            {
                "recommended_lection": {
                    "reference": "Zsolt 23",
                    "connection_type": "liturgical_echo",
                    "rationale": "A pásztor képe.",
                    "liturgical_function": "Megnyugvás",
                    "estimated_length": "short",
                    "warnings": [],
                },
                "alternative_lections": [],
                "overall_reasoning": "Vázlat alapján.",
                "basis": ["sermon_outline"],
                "no_separate_lection_needed": False,
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_outline=outline,
        lection_user_focus="",
        generate_fn=_capture,
        skip_api_if_insufficient=True,
    )
    assert result.ok
    assert "Maradjatok meg Isten szeretetében" in captured.get("prompt", "")
    assert "Elkészült igehirdetési vázlat" in captured.get("prompt", "")


def test_manual_edit_save_can_clear_field(session):
    """Kézi mentésnél az üres mező szándékos törlés maradhat."""
    ensure_sermon_workshop_state(st.session_state)
    save_sermon_outline(
        st.session_state,
        {
            "main_idea": "Eredeti fő gondolat",
            "opening_direction": "Bevezetés",
            "movements": [],
            "closing": {"final_insight": "Zárás"},
        },
        mark_manual_edit=False,
    )
    st.session_state[_KEY_OUTLINE["main_idea"]] = ""
    st.session_state[_KEY_OUTLINE["opening_direction"]] = "Bevezetés"
    _persist_outline_from_widgets(mark_manual_edit=True)
    outline = st.session_state[SERMON_WORKSHOP_KEY]["sermon_outline"]
    assert str(outline.get("main_idea") or "") == ""
    assert str(outline.get("opening_direction") or "") == "Bevezetés"
