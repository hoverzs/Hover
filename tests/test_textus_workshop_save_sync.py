"""Textusműhely: globális Mentés widget-flush regresszió.

Szimulálja: gépelés → nincs blur / szakaszmentés → Mentés → tartós project_data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_text_ui import save_bible_text_from_widgets
from textus_workshop_data import (
    TEXT_WORKSHOP_KEY,
    ensure_text_workshop_state,
    get_default_text_workshop,
    normalize_text_workshop,
)
from textus_workshop_ui import flush_textus_workshop_from_widgets
from workspace_data import (
    EXCLUDED_SESSION_KEYS,
    build_project_data,
    sanitize_project_data,
)


@pytest.fixture
def session(monkeypatch):
    """Könnyű session_state stub a Streamlit widget flushhez."""
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    return state


def _sync_inputs_like_app(state: dict) -> None:
    """Az app._sync_inputs_to_last lényegi része (Streamlit nélkül)."""
    igehely = (state.get("igehely_input") or "").strip()
    alkalom = state.get("alkalom_input") or ""
    stilus = state.get("stilus_input") or ""
    sajat = state.get("sajat_input") or ""

    if igehely:
        state["last_igehely"] = igehely
    if alkalom:
        state["last_alkalom"] = alkalom
    if stilus:
        state["last_stilus"] = stilus
    state["last_sajat"] = sajat

    if "passage_text_input" in state:
        save_bible_text_from_widgets(state)

    flush_textus_workshop_from_widgets()


def test_flush_textarea_main_idea_without_section_save(session):
    """Textarea: gépelés → Mentés → text_workshop.text_main_idea."""
    ensure_text_workshop_state(session)
    session[TEXT_WORKSHOP_KEY]["text_main_idea"] = "régi mondat"
    session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] = "draft"
    session["tw_main_idea_input"] = "  Új fő gondolat a Mentés előtt  "

    flush_textus_workshop_from_widgets()

    tw = session[TEXT_WORKSHOP_KEY]
    assert tw["text_main_idea"] == "Új fő gondolat a Mentés előtt"
    assert tw["text_main_idea_status"] == "draft"


def test_flush_preserves_approved_status(session):
    ensure_text_workshop_state(session)
    session[TEXT_WORKSHOP_KEY]["text_main_idea"] = "jóváhagyott"
    session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] = "approved"
    session["tw_main_idea_input"] = "finomított megfogalmazás"

    flush_textus_workshop_from_widgets()

    tw = session[TEXT_WORKSHOP_KEY]
    assert tw["text_main_idea"] == "finomított megfogalmazás"
    assert tw["text_main_idea_status"] == "approved"


def test_flush_skips_when_widget_absent(session):
    ensure_text_workshop_state(session)
    session[TEXT_WORKSHOP_KEY]["text_main_idea"] = "megmarad"
    session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] = "approved"

    flush_textus_workshop_from_widgets()

    assert session[TEXT_WORKSHOP_KEY]["text_main_idea"] == "megmarad"
    assert session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] == "approved"


def test_project_switch_resync_blocks_stale_widget_overwrite(session):
    """Régi projekt widgetje ne írja felül az új projekt tartós adatát."""
    ensure_text_workshop_state(session)
    session[TEXT_WORKSHOP_KEY]["text_main_idea"] = "új projekt fő gondolata"
    session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] = "approved"
    session["tw_main_idea_input"] = "előző projekt stale widget"
    session["_tw_ui_resync"] = True

    flush_textus_workshop_from_widgets()

    tw = session[TEXT_WORKSHOP_KEY]
    assert tw["text_main_idea"] == "új projekt fő gondolata"
    assert session["tw_main_idea_input"] == "új projekt fő gondolata"
    assert tw["text_main_idea_status"] == "approved"
    assert "_tw_ui_resync" not in session or not session.get("_tw_ui_resync")


def test_text_input_selectbox_passage_sync_and_reload(session):
    """Igehely (text), alkalom (select), passage_text, fő gondolat → reload."""
    ensure_text_workshop_state(session)
    session[TEXT_WORKSHOP_KEY]["text_main_idea"] = ""
    session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] = ""
    session[TEXT_WORKSHOP_KEY]["approved_insights"] = [
        {
            "id": "ins-1",
            "source": "Saját megfigyelés",
            "category": "Teológia",
            "content": "Megőrzött felismerés",
            "created_at": "2026-07-22T12:00:00",
        }
    ]

    session["igehely_input"] = "Júd 17–20"
    session["alkalom_input"] = "vasárnapi gyülekezeti igehirdetés"
    session["stilus_input"] = "klasszikus református"
    session["sajat_input"] = "Hitben megmaradás"
    session["passage_text_input"] = "17 Ti pedig, szeretteim…"
    session["tw_main_idea_input"] = "Őrizzétek meg magatokat Isten szeretetében."
    session["exegesis"] = "Exegetikai háttér tartalom"
    session["history"] = "Kortörténeti háttér"
    session["theology"] = "Teológiai hangsúly"
    session["original_text"] = "Eredeti szöveg tanulmány"

    _sync_inputs_like_app(session)

    assert session["last_igehely"] == "Júd 17–20"
    assert session["last_alkalom"] == "vasárnapi gyülekezeti igehirdetés"
    assert session["last_stilus"] == "klasszikus református"
    assert session["last_sajat"] == "Hitben megmaradás"
    assert session["passage_text"].startswith("17. ")
    assert session["bible_translation"] == "RÚF 2014"
    assert (
        session[TEXT_WORKSHOP_KEY]["text_main_idea"]
        == "Őrizzétek meg magatokat Isten szeretetében."
    )

    payload = build_project_data(session, version="2.0-test", app_name="Textus")
    assert "tw_main_idea_input" not in payload
    assert "igehely_input" not in payload
    for excluded in ("tw_main_idea_input", "passage_text_input", "igehely_input"):
        assert excluded in EXCLUDED_SESSION_KEYS
        assert excluded not in payload

    assert payload["last_igehely"] == "Júd 17–20"
    assert payload["passage_text"].startswith("17. ")
    assert (
        payload[TEXT_WORKSHOP_KEY]["text_main_idea"]
        == "Őrizzétek meg magatokat Isten szeretetében."
    )
    assert payload["exegesis"] == "Exegetikai háttér tartalom"
    assert payload["history"] == "Kortörténeti háttér"
    assert payload["theology"] == "Teológiai hangsúly"
    assert payload["original_text"] == "Eredeti szöveg tanulmány"
    assert len(payload[TEXT_WORKSHOP_KEY]["approved_insights"]) == 1

    cleaned = sanitize_project_data(payload)
    reloaded_tw = normalize_text_workshop(cleaned[TEXT_WORKSHOP_KEY])
    assert (
        reloaded_tw["text_main_idea"]
        == "Őrizzétek meg magatokat Isten szeretetében."
    )
    assert reloaded_tw["approved_insights"][0]["content"] == "Megőrzött felismerés"
    assert cleaned["last_igehely"] == "Júd 17–20"
    assert cleaned["passage_text"].startswith("17. ")


def test_project_b_switch_then_back(session):
    """Projekt A mentés → B → A visszatöltés: fő gondolat és státusz."""
    ensure_text_workshop_state(session)
    session["igehely_input"] = "Júd 17–20"
    session["passage_text_input"] = "17 Ti pedig…"
    session["tw_main_idea_input"] = "A projekt fő gondolata"
    session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] = "approved"
    session[TEXT_WORKSHOP_KEY]["approved_insights"] = [
        {
            "id": "a1",
            "source": "Exegézis",
            "category": "Felismerés",
            "content": "A felismerés",
            "created_at": "2026-07-22T12:00:00",
        }
    ]
    _sync_inputs_like_app(session)
    project_a = build_project_data(session, version="2.0-test", app_name="Textus")

    # Váltás B-re (stale widget + resync, mint _apply_project_data_to_session)
    session[TEXT_WORKSHOP_KEY] = get_default_text_workshop()
    session["last_igehely"] = "Jn 3,16"
    session["passage_text"] = "16 Mert úgy szeretett…"
    session["tw_main_idea_input"] = "A projekt fő gondolata"  # stale
    session["_tw_ui_resync"] = True
    flush_textus_workshop_from_widgets()
    assert session[TEXT_WORKSHOP_KEY]["text_main_idea"] == ""
    assert session["tw_main_idea_input"] == ""

    # Vissza A-ra
    session[TEXT_WORKSHOP_KEY] = normalize_text_workshop(
        project_a[TEXT_WORKSHOP_KEY]
    )
    session["last_igehely"] = project_a["last_igehely"]
    session["passage_text"] = project_a["passage_text"]
    session["_tw_ui_resync"] = True
    flush_textus_workshop_from_widgets()
    assert (
        session[TEXT_WORKSHOP_KEY]["text_main_idea"]
        == "A projekt fő gondolata"
    )
    assert session[TEXT_WORKSHOP_KEY]["text_main_idea_status"] == "approved"
    assert len(session[TEXT_WORKSHOP_KEY]["approved_insights"]) == 1


def test_old_project_without_text_workshop_normalizes():
    empty = normalize_text_workshop(None)
    assert empty["text_main_idea"] == ""
    assert empty["text_main_idea_status"] == ""
    assert empty["approved_insights"] == []

    legacy = normalize_text_workshop(
        {
            "text_big_idea": "régi kulcs",
            "text_big_idea_status": "draft",
        }
    )
    assert legacy["text_main_idea"] == "régi kulcs"
    assert legacy["text_main_idea_status"] == "draft"


def test_flush_wired_in_app_sync():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    ui = (ROOT / "textus_workshop_ui.py").read_text(encoding="utf-8")
    assert "def flush_textus_workshop_from_widgets" in ui
    assert "flush_textus_workshop_from_widgets" in app
    idx_sync = app.find("def _sync_inputs_to_last")
    idx_flush = app.find("flush_textus_workshop_from_widgets()", idx_sync)
    idx_next = app.find("\ndef ", idx_sync + 1)
    assert idx_flush != -1 and idx_flush < idx_next
    assert "tw_main_idea_input" in app  # projektváltás pending sync
