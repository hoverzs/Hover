"""Gyorseszközök „Vázlat" gomb — kurátori-kapu (`require_curation`)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
)
from sermon_workshop_outline_ai import assess_outline_readiness
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop


def _base_state(**extra) -> dict:
    state = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot…",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state


def test_default_behavior_unchanged_no_curation_required():
    state = _base_state()
    ready = assess_outline_readiness(state)
    assert ready.ok


def test_require_curation_blocks_raw_passage_only():
    state = _base_state()
    ready = assess_outline_readiness(state, require_curation=True)
    assert not ready.ok
    assert "saját döntés" in ready.message


def test_require_curation_passes_with_basket_item():
    state = _base_state(basket=[{"source": "Exegézis", "content": "Megtartandó gondolat."}])
    ready = assess_outline_readiness(state, require_curation=True)
    assert ready.ok


def test_require_curation_passes_with_text_main_idea():
    state = _base_state()
    state[TEXT_WORKSHOP_KEY]["text_main_idea"] = "Isten szeretete megváltást hoz."
    ready = assess_outline_readiness(state, require_curation=True)
    assert ready.ok


def test_require_curation_passes_with_approved_insight():
    state = _base_state()
    state[TEXT_WORKSHOP_KEY]["approved_insights"] = [
        {"content": "A szeretet ige a szöveg központi mozgása.", "approved": True}
    ]
    ready = assess_outline_readiness(state, require_curation=True)
    assert ready.ok


def test_require_curation_passes_with_sermon_main_idea():
    state = _base_state()
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Isten szabadító szeretete."
    ready = assess_outline_readiness(state, require_curation=True)
    assert ready.ok


def test_require_curation_ignores_non_persistent_approval_flags():
    """A `{key}_ever_approved` session-flagek (nem perzisztensek) NEM elegendők."""
    state = _base_state(exegesis_ever_approved=True, exegesis_status="approved")
    ready = assess_outline_readiness(state, require_curation=True)
    assert not ready.ok
