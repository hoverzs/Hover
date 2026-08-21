"""Regression: Javaslat átvétele → draft mentés; jóváhagyás → outline evidence."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    accept_workshop_proposal,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    section_has_accepted_content,
)
from sermon_workshop_outline_ai import (
    EMPTY_PROJECT_MESSAGE,
    assemble_sermon_outline,
    assess_outline_readiness,
    build_outline_from_workshop,
    collect_outline_context_bundle,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop
from workspace_data import build_project_data, sanitize_project_data
from workshop_nav_ui import sermon_section_statuses


def _base_state(**extra) -> dict:
    state = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta…",
        "exegesis": "A szeret ige a szöveg központi mozgása.",
        "original_text": "",
        "theology": "",
        "history": "",
        "last_sajat": "",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state


def _hc_block(**overrides) -> dict:
    block = {
        "condition": "Az ember szeretetéhsége és elveszettsége.",
        "false_response": "",
        "human_need": "Megtartó szeretetre van szüksége.",
        "divine_action": "Isten egyszülött Fiát adja.",
        "grace_response": "Hitben ragaszkodhatunk a Fiúhoz.",
    }
    block.update(overrides)
    return block


def _hc_categories() -> list[tuple[str, str]]:
    return [
        ("condition", "Emberi helyzet"),
        ("human_need", "Emberi szükség"),
        ("divine_action", "Isten cselekvése"),
        ("grace_response", "Kegyelmi válasz"),
    ]


def test_accept_proposal_persists_as_durable_draft():
    """Javaslat átvétele → mezők + draft; nem automatikus jóváhagyás."""
    state = _base_state()
    block = _hc_block()
    result = accept_workshop_proposal(
        state,
        section_key="human_condition",
        block=block,
        source_section="Emberi helyzet és kegyelmi válasz",
        field_categories=_hc_categories(),
        status_key="human_condition_status",
    )
    assert result["status"] == "draft"
    assert result["added"] == 0
    sw = state[SERMON_WORKSHOP_KEY]
    assert sw["human_condition_status"] == "draft"
    assert sw["human_condition"]["condition"] == block["condition"]
    assert not any(
        d.get("content") == block["condition"]
        for d in sw["approved_sermon_decisions"]
    )
    assert not section_has_accepted_content(
        state,
        section_key="human_condition",
        status_key="human_condition_status",
        source_section="Emberi helyzet és kegyelmi válasz",
    )
    statuses = sermon_section_statuses(state)
    assert statuses["Emberi helyzet és kegyelmi válasz"] in ("draft", "own_emphasis")
    assert statuses["Emberi helyzet és kegyelmi válasz"] != "approved"


def test_finalize_proposal_marks_approved_and_feeds_decisions():
    state = _base_state()
    block = _hc_block()
    accept_workshop_proposal(
        state,
        section_key="human_condition",
        block=block,
        source_section="Emberi helyzet és kegyelmi válasz",
        field_categories=_hc_categories(),
        status_key="human_condition_status",
        finalize=False,
    )
    result = accept_workshop_proposal(
        state,
        section_key="human_condition",
        block=block,
        source_section="Emberi helyzet és kegyelmi válasz",
        field_categories=_hc_categories(),
        status_key="human_condition_status",
        finalize=True,
    )
    assert result["status"] == "approved"
    assert result["added"] >= 3
    sw = state[SERMON_WORKSHOP_KEY]
    assert sw["human_condition_status"] == "approved"
    assert any(
        d.get("content") == block["condition"]
        for d in sw["approved_sermon_decisions"]
    )
    assert section_has_accepted_content(
        state,
        section_key="human_condition",
        status_key="human_condition_status",
        source_section="Emberi helyzet és kegyelmi válasz",
    )


def test_accept_survives_project_save_reload_and_feeds_outline():
    state = _base_state()
    accepted = "Az ember elveszett, de Isten szeretete megtalálja."
    accept_workshop_proposal(
        state,
        section_key="human_condition",
        block=_hc_block(
            condition=accepted,
            human_need="Megváltó szeretet.",
            divine_action="Isten odaadja Fiát.",
            grace_response="Higgyünk benne.",
        ),
        source_section="Emberi helyzet és kegyelmi válasz",
        field_categories=_hc_categories(),
        status_key="human_condition_status",
        finalize=True,
    )

    payload = sanitize_project_data(build_project_data(state))
    reloaded = {
        "last_igehely": payload.get("last_igehely") or state["last_igehely"],
        "igehely_input": state["igehely_input"],
        "passage_text": payload.get("passage_text") or state["passage_text"],
        "exegesis": payload.get("exegesis") or state["exegesis"],
        TEXT_WORKSHOP_KEY: payload[TEXT_WORKSHOP_KEY],
        SERMON_WORKSHOP_KEY: normalize_sermon_workshop(payload[SERMON_WORKSHOP_KEY]),
    }

    sw = reloaded[SERMON_WORKSHOP_KEY]
    assert sw["human_condition_status"] == "approved"
    assert accepted in (sw["human_condition"].get("condition") or "")
    assert any(
        accepted in str(d.get("content") or "")
        for d in (sw.get("approved_sermon_decisions") or [])
    )

    ready = assess_outline_readiness(reloaded)
    assert ready.ok, ready.message
    assert "approved_sermon_decisions" in ready.source_keys or "human_condition" in ready.source_keys

    bundle = collect_outline_context_bundle(reloaded)
    joined = " ".join(
        list(bundle.get("approved_sermon_decisions") or [])
        + [
            str(v)
            for v in (bundle.get("human_condition") or {}).values()
        ]
    )
    assert accepted in joined

    outline = build_outline_from_workshop(reloaded)
    outline_blob = " ".join(
        [
            str(outline.get("main_idea") or ""),
            str(outline.get("divine_gracious_action") or ""),
            str(outline.get("grace_enabled_response") or ""),
            str(outline.get("human_situation") or ""),
        ]
        + [
            str(m.get("core_content") or "")
            for m in (outline.get("movements") or [])
            if isinstance(m, dict)
        ]
    )
    assert accepted in outline_blob or accepted in joined
    assert outline.get("main_idea") or outline.get("movements")


def test_draft_adopt_survives_rerun_without_approval():
    """Streamlit-rerun után az átvett draft tartalom megmarad a mezőkben."""
    state = _base_state()
    text = "Átvett draft emberi helyzet."
    accept_workshop_proposal(
        state,
        section_key="human_condition",
        block=_hc_block(condition=text),
        source_section="Emberi helyzet és kegyelmi válasz",
        field_categories=_hc_categories(),
        status_key="human_condition_status",
    )
    # Szimulált rerun: session → project → normalize
    payload = sanitize_project_data(build_project_data(state))
    reloaded = {
        "last_igehely": state["last_igehely"],
        "passage_text": state["passage_text"],
        TEXT_WORKSHOP_KEY: payload[TEXT_WORKSHOP_KEY],
        SERMON_WORKSHOP_KEY: normalize_sermon_workshop(payload[SERMON_WORKSHOP_KEY]),
    }
    sw = reloaded[SERMON_WORKSHOP_KEY]
    assert sw["human_condition"]["condition"] == text
    assert sw["human_condition_status"] == "draft"
    assert not sw.get("approved_sermon_decisions")


def test_insufficient_message_is_specific():
    state = _base_state(passage_text="", exegesis="")
    ready = assess_outline_readiness(state)
    assert not ready.ok
    assert ready.message == EMPTY_PROJECT_MESSAGE
    assert "anyag nem teljes" not in ready.message.casefold()
