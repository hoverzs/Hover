"""Illusztrációk és aktualizálás — egyszerűsített M7 regresszió."""

from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_events_search_service import NO_SEARCH_MESSAGE, search_current_events
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    save_sermon_outline,
    update_sermon_workshop_section,
)
from sermon_workshop_m7_simple_ai import (
    assess_enrichment_readiness,
    build_simple_enrichment_context,
    illustration_card_to_legacy,
    suggest_actualizations,
    suggest_illustrations,
)
from sermon_workshop_outline_ai import build_outline_from_workshop
from sermon_workshop_ui import _SW_SECTION_OPTIONS, render_enrichment_section
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop


def _state(**extra):
    state = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot…",
        "exegesis": "",
        "theology": "",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state


def test_section_renamed():
    assert "Illusztrációk és aktualizálás" in _SW_SECTION_OPTIONS
    assert "Képek, illusztrációk és alkalmazás" not in _SW_SECTION_OPTIONS


def test_a_textus_only_readiness():
    state = _state()
    assert assess_enrichment_readiness(state).ok


def test_b_partial_no_m6_gate():
    state = _state()
    # Nincs M6, nincs gospel, nincs approved main idea
    ready = assess_enrichment_readiness(state)
    assert ready.ok
    ctx = build_simple_enrichment_context(state)
    assert "passage" in ctx
    assert "passage_text" in ctx
    assert "sermon_movements" not in ctx


def test_c_empty_direction_context():
    state = _state()
    ctx = build_simple_enrichment_context(state, user_direction="")
    assert "user_direction" not in ctx


def test_d_e_illustration_suggest_parses(monkeypatch):
    state = _state()

    def gen(prompt, **kwargs):
        assert kwargs.get("enable_google_search") is False
        return json.dumps(
            {
                "note": "A textus saját képe is elég lehet.",
                "suggestions": [
                    {
                        "title": "Hétköznapi példa",
                        "type": "everyday",
                        "idea": "Egy család megosztja a kenyerét.",
                        "connection_to_text": "A szeretet gyakorlati formája.",
                        "usage_note": "",
                        "source_verification_required": False,
                    },
                    {
                        "title": "Haszid gondolat",
                        "type": "spiritual_story",
                        "idea": "Rövid összefoglaló egy haszid tanításról.",
                        "connection_to_text": "Isten közelsége.",
                        "usage_note": "A pontos forrás ellenőrzendő.",
                        "source_name": "haszid hagyomány",
                        "source_verification_required": True,
                    },
                ],
            },
            ensure_ascii=False,
        )

    result = suggest_illustrations(state, user_direction="", generate_fn=gen)
    assert result.ok
    assert 1 <= len(result.suggestions) <= 4
    assert result.suggestions[1]["source_verification_required"] is True
    assert "ellenőrzendő" in result.suggestions[1]["usage_note"].casefold()


def test_f_textual_image_preferred_note():
    state = _state()

    def gen(prompt, **kwargs):
        return json.dumps(
            {
                "note": (
                    "Ehhez a textushoz a bibliai szöveg saját képe erősebb lehet, "
                    "mint egy külső illusztráció."
                ),
                "suggestions": [
                    {
                        "title": "Textusbeli kép",
                        "type": "textual_image",
                        "idea": "A világ szeretete mint horizont.",
                        "connection_to_text": "Közvetlenül a textusból.",
                    }
                ],
            },
            ensure_ascii=False,
        )

    result = suggest_illustrations(state, generate_fn=gen)
    assert "saját képe" in result.note.casefold() or "textus" in result.note.casefold()


def test_g_actualization_with_search():
    state = _state()
    calls = {"n": 0}

    def gen(prompt, **kwargs):
        calls["n"] += 1
        if kwargs.get("enable_google_search"):
            return (
                "Cím: Közösségi adománygyűjtés\n"
                "Összefoglaló: Egy erdélyi városban összefogtak.\n"
                "Forrás: Telex · 2026-07-20\n"
                "URL: https://example.com/hir"
            )
        return json.dumps(
            {
                "note": "",
                "suggestions": [
                    {
                        "title": "Közösségi adománygyűjtés",
                        "event_summary": "Egy erdélyi városban összefogtak.",
                        "connection_to_text": "Kapcsolódási pont lehet a szeretet gyakorlásához.",
                        "possible_use": "bevezető kérdés",
                        "source_name": "Telex",
                        "source_url": "https://example.com/hir",
                        "published_at": "2026-07-20",
                        "caution": "",
                    }
                ],
            },
            ensure_ascii=False,
        )

    result = suggest_actualizations(state, generate_fn=gen)
    assert result.ok
    assert result.used_web_search
    assert result.suggestions
    assert result.suggestions[0]["source_url"]
    assert result.suggestions[0]["published_at"]
    assert calls["n"] >= 2


def test_h_no_web_search_service():
    state = _state()
    result = suggest_actualizations(state, generate_fn=None)
    assert not result.ok
    assert "webes" in result.error_message.casefold() or "keresési" in result.error_message.casefold()
    search = search_current_events(query_prompt="x", generate_fn=None)
    assert not search.ok
    assert search.error_message == NO_SEARCH_MESSAGE


def test_i_no_relevant_events():
    state = _state()

    def gen(prompt, **kwargs):
        if kwargs.get("enable_google_search"):
            return "Nincs érdemi friss találat."
        return json.dumps(
            {
                "note": (
                    "A jelenlegi találatok között nincs olyan friss esemény, "
                    "amelyet érdemes lenne erőltetés nélkül ehhez a textushoz kapcsolni."
                ),
                "suggestions": [],
            },
            ensure_ascii=False,
        )

    result = suggest_actualizations(state, generate_fn=gen)
    assert result.ok
    assert result.suggestions == []
    assert "erőltetés" in result.note.casefold()


def test_j_sensitive_caution():
    state = _state()

    def gen(prompt, **kwargs):
        if kwargs.get("enable_google_search"):
            return "Tragédia: baleset történt."
        return json.dumps(
            {
                "suggestions": [
                    {
                        "title": "Közlekedési baleset",
                        "event_summary": "Súlyos baleset történt.",
                        "connection_to_text": "Óvatosan párhuzamba állítható a törékenységgel.",
                        "possible_use": "rövid háttér",
                        "source_name": "MTI",
                        "source_url": "https://example.com/a",
                        "published_at": "2026-07-21",
                        "caution": "érzékeny tragédia",
                    }
                ]
            },
            ensure_ascii=False,
        )

    result = suggest_actualizations(state, generate_fn=gen)
    assert "tragédia" in result.suggestions[0]["caution"].casefold()


def test_k_retain_no_duplicate():
    state = _state()
    card = {
        "id": "ill1",
        "title": "Példa",
        "idea": "Ötlet",
        "selected": True,
    }
    update_sermon_workshop_section(
        state, "retained_illustration_cards", [card]
    )
    update_sermon_workshop_section(
        state, "retained_illustration_cards", [card]
    )
    retained = state[SERMON_WORKSHOP_KEY]["retained_illustration_cards"]
    assert len(retained) == 1


def test_l_old_m7_project_loads():
    legacy = normalize_sermon_workshop(
        {
            "illustrations": [
                {
                    "id": "old1",
                    "idea": "Régi illusztráció",
                    "connection_to_text": "Kapcsolat",
                    "source": "everyday_observation",
                }
            ],
            "applications": [
                {"id": "a1", "application": "Régi alkalmazás", "scope": "personal"}
            ],
        }
    )
    assert legacy["illustrations"][0]["idea"] == "Régi illusztráció"
    assert legacy["applications"][0]["application"] == "Régi alkalmazás"
    assert "retained_illustration_cards" in legacy
    assert legacy["retained_illustration_cards"] == []


def test_m_outline_only_retained():
    state = _state()
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Fő gondolat"
    state[SERMON_WORKSHOP_KEY]["illustration_suggestions"] = [
        {"id": "s1", "title": "Nem megtartott", "idea": "Alternatíva"}
    ]
    state[SERMON_WORKSHOP_KEY]["retained_illustration_cards"] = [
        {
            "id": "r1",
            "title": "Megtartott",
            "idea": "Csak ez kerüljön be",
            "connection_to_text": "Kapcsolat",
            "selected": True,
        }
    ]
    state[SERMON_WORKSHOP_KEY]["actualization_connections"] = [
        {
            "id": "a1",
            "title": "Friss esemény",
            "event_summary": "Összefoglaló",
            "source_name": "Telex",
            "published_at": "2026-07-20",
        }
    ]
    outline = build_outline_from_workshop(state)
    blob = json.dumps(outline, ensure_ascii=False)
    assert "Csak ez kerüljön be" in blob
    assert "Nem megtartott" not in blob
    assert outline["actualization_connections"]
    assert outline["actualization_connections"][0]["published_at"] == "2026-07-20"


def test_n_project_switch_isolation():
    a = _state(last_igehely="Jn 1,1")
    b = _state(last_igehely="Jn 2,1")
    update_sermon_workshop_section(
        a,
        "retained_illustration_cards",
        [{"id": "1", "title": "A", "idea": "Projekt A"}],
    )
    update_sermon_workshop_section(
        b,
        "retained_illustration_cards",
        [{"id": "2", "title": "B", "idea": "Projekt B"}],
    )
    assert a[SERMON_WORKSHOP_KEY]["retained_illustration_cards"][0]["idea"] == "Projekt A"
    assert b[SERMON_WORKSHOP_KEY]["retained_illustration_cards"][0]["idea"] == "Projekt B"


def test_o_ui_no_manual_forms(session, monkeypatch):
    calls: list[str] = []

    def _cap(*a, **k):
        calls.append(str(a[0]) if a else "")

    def _md(*a, **k):
        calls.append(str(a[0]) if a else "")

    def _btn(*a, **k):
        calls.append(f"BTN:{a[0]}" if a else "BTN")
        return False

    def _ta(*a, **k):
        calls.append(f"TA:{a[0] if a else ''}")
        return ""

    monkeypatch.setattr(st, "markdown", _md)
    monkeypatch.setattr(st, "caption", _cap)
    monkeypatch.setattr(st, "info", lambda *a, **k: calls.append(f"INFO:{a[0]}" if a else ""))
    monkeypatch.setattr(st, "warning", lambda *a, **k: None)
    monkeypatch.setattr(st, "success", lambda *a, **k: None)
    monkeypatch.setattr(st, "subheader", lambda *a, **k: calls.append(f"H:{a[0]}"))
    monkeypatch.setattr(st, "button", _btn)
    monkeypatch.setattr(st, "text_area", _ta)
    monkeypatch.setattr(st, "tabs", lambda labels: [nullcontext(), nullcontext()])
    monkeypatch.setattr(st, "expander", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "columns", lambda n: [nullcontext() for _ in range(n)])
    monkeypatch.setattr(st, "container", lambda: nullcontext())
    monkeypatch.setattr(st, "write", lambda *a, **k: None)
    monkeypatch.setattr(st, "rerun", lambda: None)

    session["last_igehely"] = "Jn 3,16"
    session["passage_text"] = "Textus"
    render_enrichment_section(generate_fn=None)
    joined = "\n".join(calls)
    assert "Illusztrációk és aktualizálás" in joined
    assert "Illusztrációk javaslata" in joined
    assert "Aktuális kapcsolódások keresése" in joined
    assert "homiletikai funkció" not in joined.casefold()
    assert "movement" not in joined.casefold()
    assert "Kép hozzáadása" not in joined
    assert "Alkalmazás hozzáadása" not in joined
    assert "előbb jóvá kell hagyni" not in joined.casefold()


def test_legacy_card_roundtrip():
    card = {
        "id": "x",
        "title": "Cím",
        "idea": "Ötlet szöveg",
        "connection_to_text": "Kapcsolat",
        "usage_note": "Megjegyzés",
        "source_verification_required": True,
    }
    legacy = illustration_card_to_legacy(card)
    assert "Ötlet" in legacy["idea"]
    assert legacy["source"] == "needs_verification"


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state
