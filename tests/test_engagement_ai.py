"""Megszólítás és bevonás — MI háttérréteg tesztek (Korrekciós fázis 2B)."""

from __future__ import annotations

import json

from sermon_workshop_engagement_ai import (
    ENGAGEMENT_TYPE_KEYS,
    MAX_SUGGESTION_OPTIONS,
    engagement_type_label,
    has_sufficient_engagement_material,
    normalize_engagement_type,
    parse_engagement_suggestion,
    suggest_engagement_elements,
)


def test_engagement_types_five_options():
    assert len(ENGAGEMENT_TYPE_KEYS) == 5
    assert set(ENGAGEMENT_TYPE_KEYS) == {
        "question",
        "direct_address",
        "image_metaphor",
        "life_situation",
        "presence_sentence",
    }


def test_normalize_engagement_type():
    assert normalize_engagement_type("question") == "question"
    assert normalize_engagement_type("nonsense") == ""
    assert normalize_engagement_type(None) == ""
    assert engagement_type_label("image_metaphor") == "Vizuális kép vagy metafora"


def test_insufficient_approved_material_skips_api_call():
    """Jóváhagyott anyag nélkül (minden None/üres) ne induljon API-hívás."""
    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    result = suggest_engagement_elements(passage="Jn 3,16", generate_fn=_should_not_run)
    assert called["n"] == 0
    assert result.ok is True
    assert result.options == []
    assert result.missing_information


def test_missing_passage_blocks_without_api_call():
    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    result = suggest_engagement_elements(passage="", generate_fn=_should_not_run)
    assert called["n"] == 0
    assert result.ok is False


def test_structured_2_to_4_response_parses_with_distinct_types():
    called = {"n": 0}

    def _gen(*_a, **_k):
        called["n"] += 1
        return json.dumps(
            {
                "options": [
                    {"type": "question", "text": "Mikor érezted magad egyedül?"},
                    {"type": "image_metaphor", "text": "Vihar és kikötő."},
                    {"type": "presence_sentence", "text": "Isten ma is itt van."},
                ],
                "reasoning_summary": "A megérkezés és a fókuszmondat alapján.",
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    result = suggest_engagement_elements(
        passage="Júd 17-20",
        sermon_main_idea="Isten megtartja népét a szétszóratásban is.",
        closing={"final_discovery": "Isten hűsége nem függ tőlünk."},
        generate_fn=_gen,
    )
    assert called["n"] == 1
    assert result.ok is True
    assert 2 <= len(result.options) <= MAX_SUGGESTION_OPTIONS
    types = [o.type for o in result.options]
    assert len(types) == len(set(types)), "no duplicate types expected"


def test_options_capped_at_four_and_deduplicated_by_type():
    raw = json.dumps(
        {
            "options": [
                {"type": t, "text": f"Szöveg {i}"}
                for i, t in enumerate(
                    ["question", "question", "direct_address", "image_metaphor", "life_situation", "presence_sentence"]
                )
            ],
            "reasoning_summary": "Ok.",
            "warnings": [],
            "missing_information": [],
        }
    )
    result = parse_engagement_suggestion(raw)
    assert len(result.options) == MAX_SUGGESTION_OPTIONS
    types = [o.type for o in result.options]
    assert len(types) == len(set(types))


def test_bad_json_falls_back_safely():
    result = parse_engagement_suggestion("nem json ez")
    assert result.ok is False
    assert result.options == []


def test_has_sufficient_material_requires_passage_and_approved_source():
    from sermon_workshop_engagement_ai import build_engagement_context

    ctx_no_passage = build_engagement_context(passage="", sermon_main_idea="x")
    assert has_sufficient_engagement_material(ctx_no_passage) is False

    ctx_no_source = build_engagement_context(passage="Jn 3,16")
    assert has_sufficient_engagement_material(ctx_no_source) is False

    ctx_ok = build_engagement_context(passage="Jn 3,16", sermon_main_idea="Fókuszmondat.")
    assert has_sufficient_engagement_material(ctx_ok) is True
