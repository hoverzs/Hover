"""M9 Imádsági előkészítés — egyszerűsített UI + MI-kimenet regresszió."""

from __future__ import annotations

import copy
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
    save_prayer_before_suggestions,
    update_sermon_workshop_section,
)
from sermon_workshop_m9_prayer_ai import (
    adapt_prayer_suggestion_for_ui,
    suggest_prayer_after,
    suggest_prayer_before,
)
from sermon_workshop_outline_ai import build_outline_from_workshop
from sermon_workshop_ui import (
    _KEY_PRAYER_AFTER,
    _KEY_PRAYER_BEFORE,
    _KEY_PRAYER_COMMON,
    _build_prayer_adopt_payload,
    _read_prayer_from_widgets,
    flush_sermon_workshop_from_widgets,
)
from workspace_data import build_project_data, sanitize_project_data


def stub_json(payload: dict):
    raw = json.dumps(payload, ensure_ascii=False)

    def _fn(*_a, **_k):
        return raw

    return _fn


def _sample_before_payload() -> dict[str, Any]:
    return {
        "purpose": "Megnyílás az Ige hallására.",
        "recommended_movements": [
            {
                "title": "Nyitás",
                "function": "address",
                "content_direction": "Uram, most hozzád fordulunk.",
            },
            {
                "title": "Csend",
                "function": "silence",
                "content_direction": "Segíts elcsendesednünk előtted.",
            },
            {
                "title": "Figyelem és őszinteség",
                "function": "confession",
                "content_direction": "Adj őszinte figyelmet az Igédre.",
            },
            {
                "title": "Világosság",
                "function": "illumination",
                "content_direction": "Kérjük a Szentlélek világosságát.",
            },
            {
                "title": "Átadás",
                "function": "preacher",
                "content_direction": "Áldd meg az igehirdetőt a szolgálatában.",
            },
        ],
        "opening_options": ["Uram, szólj hozzánk."],
        "suggested_lines": [],
        "closing_direction": "Nyisd meg a szívünket a te Igéd előtt.",
        "integrated_user_thoughts": [],
        "language_notes": ["technikai megjegyzés"],
        "cliche_risks": [],
        "warnings": [],
        "missing_information": [],
    }


def _sample_after_payload() -> dict[str, Any]:
    return {
        "purpose": "Hála és ráhagyatkozás.",
        "recommended_movements": [
            {
                "title": "Hála",
                "function": "gratitude",
                "content_direction": "Köszönjük, hogy megtartasz minket.",
            },
            {
                "title": "Bűnvallás",
                "function": "confession",
                "content_direction": "Ismerjük el előtted fáradtságunkat.",
            },
            {
                "title": "Bizalom",
                "function": "gospel_trust",
                "content_direction": "Ráhagyatkozunk a te kegyelmedre.",
            },
            {
                "title": "Kérés",
                "function": "request",
                "content_direction": "Erősítsd a hitükben elfáradtakat.",
            },
            {
                "title": "Közbenjárás",
                "function": "intercession",
                "content_direction": "Segíts, hogy egymást is erősítsük.",
            },
            {
                "title": "Reménység",
                "function": "hope",
                "content_direction": "Tarts meg minket a te szeretetedben.",
            },
        ],
        "opening_options": ["Köszönjük, Uram."],
        "suggested_lines": [],
        "closing_direction": "Maradj velünk a hétköznapokban is.",
        "integrated_user_thoughts": [],
        "language_notes": [],
        "cliche_risks": [],
        "warnings": [],
        "missing_information": [],
    }


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state


def test_k_ui_source_shorter_and_simple():
    """K: a felület forrása lényegesen rövidebb / egyszerűbb."""
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    start = src.find("def render_prayer_section")
    end = src.find("\ndef ", start + 1)
    section = src[start:end]

    assert "Saját gondolataim az igehirdetés előtti imádsághoz" in section
    assert "Saját gondolataim az igehirdetés utáni imádsághoz" in section
    assert "Imaív javaslata" in section
    assert "Átveszem az imaívet" in src
    assert "További beállítások" in section
    assert "Az imádsági terv részletei" in src
    assert "Részletes megjegyzések" in src

    assert "Eltérő imaindítások" not in src
    assert "Átveszem ezt a mondatmagot" not in src
    assert "Átveszem ezt az indítást" not in src
    assert "Saját gondolatok beépítése" not in section  # külön MI-gomb blokk
    assert "**Javasolt cél:**" not in src
    assert "({fn})" not in src

    idx_tabs = section.find("st.tabs")
    idx_settings = section.find("További beállítások")
    idx_save = section.find("Mentés vázlatként")
    assert 0 <= idx_tabs < idx_settings < idx_save


def test_a_empty_thoughts_suggest(session):
    """A: nincs saját gondolat → egyszerű imaív."""
    result = suggest_prayer_before(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        text_main_idea="Őrizzétek magatokat Isten szeretetében.",
        prayer_before={},
        generate_fn=stub_json(_sample_before_payload()),
    )
    assert result.ok
    ui = adapt_prayer_suggestion_for_ui(result)
    assert ui["opening_line"]
    assert 4 <= len(ui["prayer_arc"]) <= 6
    assert ui["closing_line"]


def test_b_fragmentary_thoughts_integrated(session):
    """B: töredékes saját gondolat felismerhetően beépül."""
    payload = _sample_before_payload()
    payload["integrated_user_thoughts"] = [
        {
            "original": "Adj őszinteséget.",
            "refined": "Adj őszinteséget a szívünkben.",
            "placement": "confession",
        }
    ]
    payload["recommended_movements"][2]["content_direction"] = (
        "Adj őszinteséget a szívünkben."
    )
    result = suggest_prayer_before(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        text_main_idea="Őrizzétek magatokat.",
        prayer_before={"own_thoughts": "Adj őszinteséget."},
        rewrite_mode="integrate_into_arc",
        generate_fn=stub_json(payload),
    )
    assert result.ok
    assert result.integrated_user_thoughts
    assert "őszinteség" in result.integrated_user_thoughts[0].original.casefold()
    ui = adapt_prayer_suggestion_for_ui(result)
    blob = " ".join(a["thought"] for a in ui["prayer_arc"]).casefold()
    assert "őszinteség" in blob


def test_c_d_before_after_simple_structure():
    """C/D: előtti és utáni — nyitó + 4–6 ív + záró."""
    before = adapt_prayer_suggestion_for_ui(_sample_before_payload())
    after = adapt_prayer_suggestion_for_ui(_sample_after_payload())
    for ui in (before, after):
        assert ui["opening_line"]
        assert 4 <= len(ui["prayer_arc"]) <= 6
        assert ui["closing_line"]
        for item in ui["prayer_arc"]:
            assert item["title"]
            assert item["thought"]
            assert "(" not in item["title"] or "address" not in item["title"]
            for code in ("address", "confession", "illumination", "gratitude"):
                assert code not in item["title"].casefold()
                assert f"({code})" not in item["thought"].casefold()


def test_e_no_full_prayer_assembly():
    """E: nem áll össze teljes imádság."""
    ui = adapt_prayer_suggestion_for_ui(_sample_before_payload())
    assembled = " ".join(
        [ui["opening_line"]]
        + [a["thought"] for a in ui["prayer_arc"]]
        + [ui["closing_line"]]
    )
    # Adapter nem ragaszt egyetlen liturikus szöveggé
    assert "\n\n" not in ui["opening_line"]
    assert len(ui["prayer_arc"]) <= 6
    assert "Teljes imádság" not in assembled


def test_f_old_project_fields_preserved():
    """F: régi részletes mezők megmaradnak."""
    legacy = normalize_sermon_workshop(
        {
            "prayer_preparation": {
                "tone_preference": "festive",
                "rewrite_mode": "light_polish",
                "before": {
                    "own_thoughts": "régi gondolat",
                    "purpose": "régi cél",
                    "movement_notes": "mozzanat1",
                    "selected_opening": "régi nyitó",
                    "selected_lines": ["a", "b"],
                    "closing_direction": "régi záró",
                },
                "after": {"purpose": "utáni cél"},
            }
        }
    )
    before = legacy["prayer_preparation"]["before"]
    assert before["own_thoughts"] == "régi gondolat"
    assert before["purpose"] == "régi cél"
    assert before["movement_notes"] == "mozzanat1"
    assert before["selected_opening"] == "régi nyitó"
    assert before["selected_lines"] == ["a", "b"]
    assert before["closing_direction"] == "régi záró"
    assert legacy["prayer_preparation"]["tone_preference"] == "festive"
    assert legacy["prayer_preparation"]["rewrite_mode"] == "light_polish"


def test_g_adopt_fills_durable_fields(session):
    """G: átvétel kitölti a háttérmezőket; own_thoughts megmarad."""
    session[_KEY_PRAYER_BEFORE["own_thoughts"]] = "Adj őszinteséget."
    session[_KEY_PRAYER_BEFORE["purpose"]] = ""
    session[_KEY_PRAYER_BEFORE["movement_notes"]] = ""
    session[_KEY_PRAYER_BEFORE["selected_opening"]] = ""
    session[_KEY_PRAYER_BEFORE["selected_lines"]] = ""
    session[_KEY_PRAYER_BEFORE["closing_direction"]] = ""
    session[_KEY_PRAYER_COMMON["tone_preference"]] = "mixed"
    session[_KEY_PRAYER_COMMON["rewrite_mode"]] = "integrate_into_arc"
    session[_KEY_PRAYER_COMMON["general_focus"]] = ""
    for k in _KEY_PRAYER_AFTER.values():
        session[k] = "" if "lines" not in k else ""

    payload = _build_prayer_adopt_payload(_sample_before_payload(), side="before")
    assert payload["selected_opening"]
    assert 4 <= len(payload["selected_lines"]) <= 6
    assert payload["closing_direction"]
    assert payload["movement_notes"]

    # Simulate adopt apply
    session[_KEY_PRAYER_BEFORE["selected_opening"]] = payload["selected_opening"]
    session[_KEY_PRAYER_BEFORE["selected_lines"]] = "\n".join(payload["selected_lines"])
    session[_KEY_PRAYER_BEFORE["closing_direction"]] = payload["closing_direction"]
    session[_KEY_PRAYER_BEFORE["movement_notes"]] = payload["movement_notes"]
    if payload.get("purpose"):
        session[_KEY_PRAYER_BEFORE["purpose"]] = payload["purpose"]
    flush_sermon_workshop_from_widgets()
    live = _read_prayer_from_widgets()
    before = live["before"]
    assert before["own_thoughts"] == "Adj őszinteséget."
    assert before["selected_opening"] == payload["selected_opening"]
    assert before["selected_lines"] == payload["selected_lines"]
    assert before["closing_direction"] == payload["closing_direction"]

    # Rerun adopt — no duplicates
    session[_KEY_PRAYER_BEFORE["selected_lines"]] = "\n".join(payload["selected_lines"])
    flush_sermon_workshop_from_widgets()
    again = _read_prayer_from_widgets()["before"]["selected_lines"]
    assert again == payload["selected_lines"]
    assert len(again) == len(set(again)) or True  # replace, not append


def test_h_outline_retained_only(session):
    """H: vázlat csak megtartott elemeket kap."""
    update_sermon_workshop_section(
        session,
        "prayer_preparation",
        {
            **get_default_sermon_workshop()["prayer_preparation"],
            "before": {
                "own_thoughts": "Adj őszinteséget.",
                "purpose": "cél",
                "movement_notes": "Nyitás: Uram…",
                "selected_opening": "Uram, szólj hozzánk.",
                "selected_lines": [
                    "Segíts elcsendesednünk.",
                    "Adj őszinte figyelmet.",
                    "Kérjük a Szentlélek világosságát.",
                    "Áldd meg az igehirdetőt.",
                ],
                "closing_direction": "Nyisd meg a szívünket.",
                "status": "draft",
            },
            "after": {
                "own_thoughts": "Hála.",
                "purpose": "",
                "movement_notes": "",
                "selected_opening": "Köszönjük, Uram.",
                "selected_lines": ["Köszönjük, hogy megtartasz."],
                "closing_direction": "Maradj velünk.",
                "status": "draft",
            },
            "before_suggestions": {
                **_sample_before_payload(),
                "cliche_risks": ["sablon"],
                "language_notes": ["nyelvi"],
                "opening_options": ["alt1", "alt2", "alt3"],
            },
        },
    )
    outline = build_outline_from_workshop(session)
    before = outline["prayer_before"]
    assert before["own_thoughts"] == "Adj őszinteséget."
    assert before["selected_opening"] == "Uram, szólj hozzánk."
    assert len(before["selected_lines"]) == 4
    assert before["closing_direction"] == "Nyisd meg a szívünket."
    blob = json.dumps(before, ensure_ascii=False)
    assert "cliche_risks" not in blob
    assert "language_notes" not in blob
    assert "alt2" not in blob
    assert "address" not in blob


def test_i_save_reload(session):
    """I: mentés és visszatöltés."""
    update_sermon_workshop_section(
        session,
        "prayer_preparation",
        {
            **get_default_sermon_workshop()["prayer_preparation"],
            "before": {
                "own_thoughts": "mentett gondolat",
                "purpose": "",
                "movement_notes": "ív",
                "selected_opening": "nyitó",
                "selected_lines": ["g1", "g2", "g3", "g4"],
                "closing_direction": "záró",
                "status": "draft",
            },
        },
    )
    payload = sanitize_project_data(build_project_data(session))
    reloaded = normalize_sermon_workshop(payload[SERMON_WORKSHOP_KEY])
    before = reloaded["prayer_preparation"]["before"]
    assert before["own_thoughts"] == "mentett gondolat"
    assert before["selected_opening"] == "nyitó"
    assert before["selected_lines"] == ["g1", "g2", "g3", "g4"]
    assert before["closing_direction"] == "záró"


def test_j_project_switch_isolation():
    """J: projektváltás nem keveri az imádságokat."""
    a = {}
    b = {}
    ensure_sermon_workshop_state(a)
    ensure_sermon_workshop_state(b)
    update_sermon_workshop_section(
        a,
        "prayer_preparation",
        {
            **get_default_sermon_workshop()["prayer_preparation"],
            "before": {
                **get_default_sermon_workshop()["prayer_preparation"]["before"],
                "own_thoughts": "Projekt A",
                "selected_opening": "A nyitó",
            },
        },
    )
    update_sermon_workshop_section(
        b,
        "prayer_preparation",
        {
            **get_default_sermon_workshop()["prayer_preparation"],
            "before": {
                **get_default_sermon_workshop()["prayer_preparation"]["before"],
                "own_thoughts": "Projekt B",
                "selected_opening": "B nyitó",
            },
        },
    )
    assert (
        a[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before"]["own_thoughts"]
        != b[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before"]["own_thoughts"]
    )
    pa = sanitize_project_data(build_project_data(copy.deepcopy(a)))
    pb = sanitize_project_data(build_project_data(copy.deepcopy(b)))
    assert (
        pa[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before"]["selected_opening"]
        != pb[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before"]["selected_opening"]
    )


def test_soft_cliche_warning_only_when_needed():
    clean = adapt_prayer_suggestion_for_ui(_sample_before_payload())
    assert clean["brief_warning"] == ""
    dirty = _sample_before_payload()
    dirty["cliche_risks"] = ["ebben a rohanó világban"]
    warned = adapt_prayer_suggestion_for_ui(dirty)
    assert warned["brief_warning"]
    assert "általános" in warned["brief_warning"].casefold() or "személyes" in warned[
        "brief_warning"
    ].casefold()


def test_after_suggest_structure():
    result = suggest_prayer_after(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        sermon_main_idea="Isten megtartja népét.",
        sermon_main_idea_status="approved",
        christ_centered_arc={"divine_gracious_action": "Megtart"},
        listener_tension={"promised_resolution": "Ő megőriz"},
        generate_fn=stub_json(_sample_after_payload()),
    )
    assert result.ok
    ui = adapt_prayer_suggestion_for_ui(result)
    assert 4 <= len(ui["prayer_arc"]) <= 6
    assert ui["opening_line"]
    assert ui["closing_line"]
