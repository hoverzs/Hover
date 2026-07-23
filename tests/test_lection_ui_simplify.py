"""M9 Lekciójavaslat — egyszerűsített UI és munkafolyamat regresszió."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    update_sermon_workshop_section,
)
from sermon_workshop_m9_lection_ai import (
    LectionAssessmentResult,
    assess_lection,
    suggest_lections,
)
from sermon_workshop_ui import (
    _KEY_LECTION,
    _apply_lection_assessment_to_fields,
    _read_lection_from_widgets,
    flush_sermon_workshop_from_widgets,
)
from workspace_data import build_project_data, sanitize_project_data


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state


def stub_json(payload: dict):
    raw = json.dumps(payload, ensure_ascii=False)

    def _fn(*_a, **_k):
        return raw

    return _fn


def _lection_suggest_payload() -> dict:
    return {
        "recommended_lection": {
            "reference": "Jn 15,1–11",
            "connection_type": "gospel_complement",
            "rationale": "A szőlőtő képe a megtartó kegyelmet hordozza.",
            "liturgical_function": "Előkészíti a hitben való megmaradás témáját.",
            "estimated_length": "standard",
            "warnings": [],
        },
        "alternative_lections": [],
        "overall_reasoning": "A munkafolyamat alapján.",
        "basis": ["sermon_main_idea"],
        "no_separate_lection_needed": False,
        "no_lection_reason": "",
        "warnings": [],
        "missing_information": [],
    }


def test_ui_order_and_simplified_labels():
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    start = src.find("def render_lection_section")
    end = src.find("\ndef ", start + 1)
    section = src[start:end]

    assert "Milyen lekciót keresel?" in section
    assert "További beállítások" in section
    assert "Már van saját lekcióötletem" in section
    assert "Kiválasztott lekció" in src
    assert "A lekció kapcsolódásának részletei" in src
    assert "Lekciók javaslata" in section
    assert "_render_lection_connection_details_editor()" in section
    assert "_render_lection_selected_summary()" in section
    assert "_render_lection_textus_link_card(" in section

    assert "**Lekcióbeállítások**" not in section
    assert "**Saját lekció**" not in section
    assert "**MI-segéd**" not in section

    idx_focus = section.find("Milyen lekciót keresel?")
    idx_settings = section.find("További beállítások")
    idx_suggest = section.find("Lekciók javaslata")
    idx_own = section.find("Már van saját lekcióötletem")
    idx_summary = section.find("_render_lection_selected_summary()")
    idx_link = section.find("_render_lection_textus_link_card(")
    idx_details = section.find("_render_lection_connection_details_editor()")
    assert idx_focus < idx_settings < idx_suggest < idx_own
    assert idx_own < idx_summary < idx_link < idx_details


def test_suggest_from_free_text_focus_only(session):
    """A: csak szabad szöveges kívánság → javaslat."""
    focus = "Evangéliumi szakaszt szeretnék a megtartó kegyelemről."
    session[_KEY_LECTION["user_focus"]] = focus
    update_sermon_workshop_section(
        session,
        "lection",
        {
            **get_default_sermon_workshop()["lection"],
            "user_focus": focus,
        },
    )
    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_main_idea="Isten megtartja népét.",
        sermon_main_idea_status="approved",
        text_main_idea="Őrizzétek magatokat Isten szeretetében.",
        text_main_idea_status="approved",
        lection=session[SERMON_WORKSHOP_KEY]["lection"],
        lection_user_focus=focus,
        generate_fn=stub_json(_lection_suggest_payload()),
    )
    assert result.ok
    assert result.recommended_lection.reference == "Jn 15,1–11"
    assert result.recommended_lection.connection_type == "gospel_complement"
    assert result.recommended_lection.liturgical_function


def test_suggest_with_empty_focus_uses_workflow(session):
    """B: üres kívánság → teljes munkafolyamat alapján."""
    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_main_idea="Isten megtartja népét.",
        sermon_main_idea_status="approved",
        text_main_idea="Őrizzétek magatokat Isten szeretetében.",
        text_main_idea_status="approved",
        lection_user_focus="",
        generate_fn=stub_json(_lection_suggest_payload()),
    )
    assert result.ok
    assert result.recommended_lection.reference
    assert not result.missing_information or "passage" not in str(
        result.missing_information
    ).casefold()


def test_assess_from_reference_only(session):
    """C: csak saját igehely → értékelés működik."""
    session[_KEY_LECTION["reference"]] = "Fil 2,1–16"
    payload = {
        "overall_assessment": "Illeszkedik.",
        "strengths": ["Erős keresztény himnusz."],
        "improvements": [],
        "connection_type_assessment": "thematic illeszkedés",
        "length_assessment": "standard, felolvasható",
        "liturgical_fit_assessment": "Előkészíti a megalázkodás–felmagasztalás ívét.",
        "suggested_reference": "",
        "suggested_connection_type": "thematic",
        "revised_rationale": "Krisztus útja előkészíti a megtartás üzenetét.",
        "warnings": [],
    }
    result = assess_lection(
        passage="Júd 17–20",
        lection={"reference": "Fil 2,1–16"},
        generate_fn=stub_json(payload),
    )
    assert result.ok
    assert result.suggested_connection_type == "thematic"
    assert result.revised_rationale
    assert result.liturgical_fit_assessment

    _apply_lection_assessment_to_fields(result)
    lection = session[SERMON_WORKSHOP_KEY]["lection"]
    assert lection["connection_type"] == "thematic"
    assert lection["rationale"] == "Krisztus útja előkészíti a megtartás üzenetét."
    assert "megalázkodás" in lection["function"]


def test_assess_requires_reference(session):
    result = assess_lection(
        passage="Júd 17–20",
        lection={"reference": ""},
        generate_fn=stub_json({}),
    )
    assert not result.ok


def test_legacy_details_preserved_without_widgets(session):
    """D: régi projekt részletes adatai megmaradnak widget nélkül is."""
    update_sermon_workshop_section(
        session,
        "lection",
        {
            "reference": "Jn 15,1–11",
            "connection_type": "gospel_complement",
            "function": "Régi liturgiai funkció",
            "rationale": "Régi indoklás",
            "notes": "",
            "text": "",
            "testament_preference": "gospel",
            "length_preference": "standard",
            "user_focus": "",
        },
    )
    # Csak a fő mezők a sessionben — részletes widgetek nincsenek
    session[_KEY_LECTION["user_focus"]] = "új kívánság"
    session[_KEY_LECTION["reference"]] = "Jn 15,1–11"
    # connection / function / rationale widget kulcsok szándékosan hiányoznak
    for field in ("connection_type", "function", "rationale"):
        session.pop(_KEY_LECTION[field], None)

    block = _read_lection_from_widgets()
    assert block["connection_type"] == "gospel_complement"
    assert block["function"] == "Régi liturgiai funkció"
    assert block["rationale"] == "Régi indoklás"
    assert block["user_focus"] == "új kívánság"


def test_mi_adopt_fills_detail_fields(session):
    """E: MI-javaslat átvétele → háttér mezők."""
    pending = {
        "reference": "Jn 15,1–11",
        "connection_type": "gospel_complement",
        "function": "Előkészíti a témát.",
        "rationale": "A szőlőtő képe illik.",
    }
    for field, value in pending.items():
        session[_KEY_LECTION[field]] = value
    flush_sermon_workshop_from_widgets()
    lection = session[SERMON_WORKSHOP_KEY]["lection"]
    assert lection["reference"] == "Jn 15,1–11"
    assert lection["connection_type"] == "gospel_complement"
    assert lection["function"] == "Előkészíti a témát."
    assert lection["rationale"] == "A szőlőtő képe illik."


def test_save_reload_and_project_switch(session):
    """F+G: mentés / visszatöltés / projektváltás."""
    update_sermon_workshop_section(
        session,
        "lection",
        {
            "reference": "Jn 15,1–11",
            "connection_type": "gospel_complement",
            "function": "Funkció",
            "rationale": "Indoklás",
            "notes": "Megjegyzés",
            "text": "1 Én vagyok…",
            "testament_preference": "gospel",
            "length_preference": "short",
            "user_focus": "Evangéliumi megtartás",
        },
    )
    update_sermon_workshop_section(session, "lection_status", "approved")
    session["last_igehely"] = "Júd 17–20"
    session["passage_text"] = "17 Ti pedig…"

    payload = build_project_data(session, version="2.0-test", app_name="Textus")
    lection = payload[SERMON_WORKSHOP_KEY]["lection"]
    assert lection["user_focus"] == "Evangéliumi megtartás"
    assert lection["connection_type"] == "gospel_complement"
    assert lection["function"] == "Funkció"
    assert lection["rationale"] == "Indoklás"
    assert "sw_lection_user_focus" not in payload

    cleaned = sanitize_project_data(payload)
    reloaded = normalize_sermon_workshop(cleaned[SERMON_WORKSHOP_KEY])
    assert reloaded["lection"]["reference"] == "Jn 15,1–11"
    assert reloaded["lection"]["connection_type"] == "gospel_complement"
    assert reloaded["lection_status"] == "approved"

    other = get_default_sermon_workshop()
    assert other["lection"]["reference"] == ""
    assert other["lection"]["connection_type"] == ""
    assert other["lection"]["user_focus"] == ""


def test_suggest_generate_fn_matches_app_signature(session):
    """generate_text nem fogad system_instruction-t — a hívás kompatibilis legyen."""
    seen: dict[str, Any] = {}

    def fake_generate(
        prompt,
        enable_google_search: bool = False,
        *,
        tab_label: str = "unknown",
        use_cache: bool = True,
        system_bundle: str | None = None,
        include_brevity_directive: bool = True,
        truncation_message: str | None = None,
        truncation_notice_mode: str = "always",
        incomplete_response_message: str | None = None,
    ):
        # Nincs **kwargs: system_instruction → TypeError (mint app.generate_text).
        seen.setdefault("calls", []).append(
            {
                "tab_label": tab_label,
                "enable_google_search": enable_google_search,
                "use_cache": use_cache,
                "include_brevity_directive": include_brevity_directive,
                "system_bundle": system_bundle,
            }
        )
        seen["prompt"] = prompt
        return json.dumps(_lection_suggest_payload(), ensure_ascii=False)

    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_main_idea="Isten megtartja népét.",
        sermon_main_idea_status="approved",
        text_main_idea="Őrizzétek magatokat Isten szeretetében.",
        text_main_idea_status="approved",
        lection_user_focus="",
        generate_fn=fake_generate,
    )
    assert result.ok
    assert seen.get("calls")
    assert seen["calls"][0]["tab_label"] == "Lekciójavaslat"
    assert seen["calls"][0]["enable_google_search"] is False
    assert seen["calls"][0]["use_cache"] is False
    assert seen["calls"][0]["include_brevity_directive"] is False
    assert result.recommended_lection.reference == "Jn 15,1–11"
    assert "szőlőtő" in result.recommended_lection.rationale

    assess_seen: dict[str, Any] = {}

    def fake_assess(
        prompt,
        enable_google_search: bool = False,
        *,
        tab_label: str = "unknown",
        use_cache: bool = True,
        system_bundle: str | None = None,
        include_brevity_directive: bool = True,
        truncation_message: str | None = None,
        truncation_notice_mode: str = "always",
        incomplete_response_message: str | None = None,
    ):
        assess_seen["tab_label"] = tab_label
        assess_seen["prompt"] = prompt
        return json.dumps(
            {
                "overall_assessment": "Illeszkedik.",
                "strengths": ["Tematikus kapcsolat"],
                "improvements": [],
                "connection_type_assessment": "thematic",
                "length_assessment": "standard",
                "liturgical_fit_assessment": "jó",
                "suggested_reference": "",
                "suggested_connection_type": "thematic",
                "revised_rationale": "",
                "warnings": [],
            },
            ensure_ascii=False,
        )

    assessed = assess_lection(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_main_idea="Isten megtartja népét.",
        sermon_main_idea_status="approved",
        text_main_idea="Őrizzétek magatokat.",
        text_main_idea_status="approved",
        lection={
            "reference": "Jn 15,1–11",
            "connection_type": "gospel_complement",
            "rationale": "próba",
        },
        generate_fn=fake_assess,
    )
    assert assessed.ok
    assert assess_seen.get("tab_label") == "Lekciójavaslat"
    assert "Illeszkedik" in assessed.overall_assessment


def test_suggest_rejects_system_instruction_like_app(session):
    """Ha a wrapper TypeError-t dob system_instruction-re, a publikus API elnyeli."""

    def strict_generate(
        prompt,
        enable_google_search: bool = False,
        *,
        tab_label: str = "unknown",
        use_cache: bool = True,
        system_bundle: str | None = None,
        include_brevity_directive: bool = True,
        truncation_message: str | None = None,
        truncation_notice_mode: str = "always",
        incomplete_response_message: str | None = None,
    ):
        return json.dumps(_lection_suggest_payload(), ensure_ascii=False)

    # Közvetlen hívás a belső helperen: ha mégis system_instruction menne, TypeError.
    from sermon_workshop_m9_lection_ai import _call_lection_generate

    try:
        _call_lection_generate(
            strict_generate,
            "prompt",
            tab_label="Lekciójavaslat",
        )
    except TypeError as exc:
        pytest.fail(f"compatible call raised TypeError: {exc}")

    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_main_idea="Isten megtartja népét.",
        sermon_main_idea_status="approved",
        text_main_idea="Őrizzétek magatokat.",
        text_main_idea_status="approved",
        generate_fn=strict_generate,
    )
    assert result.ok
    assert "unexpected keyword" not in (result.error_message or "").casefold()


def test_suggest_returns_alternatives(session):
    payload = _lection_suggest_payload()
    payload["alternative_lections"] = [
        {
            "reference": "Fil 2,1–11",
            "connection_type": "thematic",
            "rationale": "a",
            "liturgical_function": "b",
            "estimated_length": "standard",
            "warnings": [],
        },
        {
            "reference": "Zsolt 23",
            "connection_type": "liturgical_echo",
            "rationale": "c",
            "liturgical_function": "d",
            "estimated_length": "short",
            "warnings": [],
        },
        {
            "reference": "Ézs 40,1–11",
            "connection_type": "preparatory",
            "rationale": "e",
            "liturgical_function": "f",
            "estimated_length": "standard",
            "warnings": [],
        },
    ]
    result = suggest_lections(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_main_idea="Isten megtartja népét.",
        sermon_main_idea_status="approved",
        text_main_idea="Őrizzétek magatokat.",
        text_main_idea_status="approved",
        lection_user_focus="",
        generate_fn=stub_json(payload),
    )
    assert result.ok
    assert len(result.alternative_lections) == 3
    assert "2–3" in (ROOT / "sermon_workshop_m9_lection_ai.py").read_text(
        encoding="utf-8"
    )
    ui = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    assert 'expanded=True' in ui[
        ui.find("További javaslatok") : ui.find("További javaslatok") + 200
    ]


def test_old_project_normalize_keeps_lection_fields():
    legacy = normalize_sermon_workshop(
        {
            "lection": {
                "reference": "Ézs 40,1–11",
                "connection_type": "preparatory",
                "function": "Vigasztalás",
                "rationale": "Régi indok",
                "testament_preference": "old_testament",
                "length_preference": "extended",
                "user_focus": "prófétai hang",
            },
            "lection_status": "draft",
        }
    )
    assert legacy["lection"]["connection_type"] == "preparatory"
    assert legacy["lection"]["function"] == "Vigasztalás"
    assert legacy["lection"]["rationale"] == "Régi indok"
    assert legacy["lection"]["user_focus"] == "prófétai hang"
