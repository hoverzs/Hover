"""Homiletikai belépési pont — MI háttérréteg tesztek (Korrekciós fázis 2A)."""

from __future__ import annotations

import json

from sermon_workshop_entry_point_ai import (
    ENTRY_POINT_TYPE_KEYS,
    NO_ENTRY_POINT_TYPE,
    entry_point_type_label,
    has_sufficient_entry_point_material,
    normalize_entry_point_type,
    parse_entry_point_suggestion,
    suggest_entry_point,
)


def test_entry_point_types_five_options():
    assert len(ENTRY_POINT_TYPE_KEYS) == 5
    assert "question" in ENTRY_POINT_TYPE_KEYS
    assert "event" in ENTRY_POINT_TYPE_KEYS
    assert "everyday_experience" in ENTRY_POINT_TYPE_KEYS
    assert "image_contrast" in ENTRY_POINT_TYPE_KEYS
    assert "text_direct" in ENTRY_POINT_TYPE_KEYS


def test_normalize_entry_point_type_allows_none():
    assert normalize_entry_point_type("question") == "question"
    assert normalize_entry_point_type("nonsense") == NO_ENTRY_POINT_TYPE
    assert normalize_entry_point_type(None) == NO_ENTRY_POINT_TYPE
    assert normalize_entry_point_type("") == NO_ENTRY_POINT_TYPE
    assert entry_point_type_label("") == "Nincs külön belépési pont"
    assert entry_point_type_label("event") == "Megtörtént eset"


def test_insufficient_material_skips_api_call():
    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    result = suggest_entry_point(passage="Jn 3,16", generate_fn=_should_not_run)
    assert called["n"] == 0
    assert result.ok is True
    assert result.today_connection == ""
    assert result.options == []
    assert result.missing_information


def test_missing_passage_blocks_without_api_call():
    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    result = suggest_entry_point(passage="", generate_fn=_should_not_run)
    assert called["n"] == 0
    assert result.ok is False


def test_sufficient_material_calls_api_and_parses_options():
    called = {"n": 0}

    def _gen(*_a, **_k):
        called["n"] += 1
        return json.dumps(
            {
                "today_connection": "A mai hallgató is küzd az elszigeteltséggel.",
                "options": [
                    {"type": "question", "text": "Mikor érezted magad egyedül?"},
                    {"type": "image_contrast", "text": "Vihar és kikötő ellentéte."},
                ],
                "reasoning_summary": "Az emberi helyzet alapján.",
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    result = suggest_entry_point(
        passage="Júd 17-20",
        human_condition={"condition": "Megosztottság fenyegeti a közösséget."},
        listener_tension={"listener_question": "Hogyan maradjak hű?"},
        generate_fn=_gen,
    )
    assert called["n"] == 1
    assert result.ok is True
    assert result.today_connection
    assert len(result.options) == 2
    assert {o.type for o in result.options} == {"question", "image_contrast"}


def test_options_capped_and_deduplicated_by_type():
    raw = json.dumps(
        {
            "today_connection": "TC",
            "options": [
                {"type": "question", "text": "Q1"},
                {"type": "question", "text": "Q2 duplicate type"},
                {"type": "event", "text": "E1"},
                {"type": "everyday_experience", "text": "EE1"},
                {"type": "image_contrast", "text": "IC1"},
            ],
            "reasoning_summary": "Ok.",
            "warnings": [],
            "missing_information": [],
        }
    )
    result = parse_entry_point_suggestion(raw)
    assert len(result.options) == 3
    types = [o.type for o in result.options]
    assert len(types) == len(set(types))


def test_bad_json_falls_back_safely():
    result = parse_entry_point_suggestion("nem json ez")
    assert result.ok is False
    assert result.today_connection == ""
    assert result.options == []


def test_has_sufficient_material_requires_passage_and_source():
    from sermon_workshop_entry_point_ai import build_entry_point_context

    ctx_no_passage = build_entry_point_context(passage="", human_condition={"condition": "x"})
    assert has_sufficient_entry_point_material(ctx_no_passage) is False

    ctx_no_source = build_entry_point_context(passage="Jn 3,16")
    assert has_sufficient_entry_point_material(ctx_no_source) is False

    ctx_ok = build_entry_point_context(
        passage="Jn 3,16", text_summary_base_tension="A textus alapfeszültsége."
    )
    assert has_sufficient_entry_point_material(ctx_ok) is True
