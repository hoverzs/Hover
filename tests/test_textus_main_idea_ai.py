"""LOCAL QA FINAL FUNCTIONAL POLISH (2026-08-21) — a "Textus fő gondolata"
JSON-hiba javítása: `response_schema` bevezetése, dedikált, valós méréssel
alátámasztott token-budget, és legfeljebb 1 kontrollált retry KIZÁRÓLAG
JSON-kinyerési hibánál (nem szemantikai/séma hibánál).

Invariant tesztek — nem egyetlen bibliai történetre drótozva.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import textus_main_idea_ai as mi_ai  # noqa: E402


def _valid_suggest_json(recommended: str = "A textus fő gondolata.") -> str:
    return json.dumps(
        {
            "recommended": recommended,
            "expanded_summary": "Egy. Kettő. Három.",
            "alternatives": [],
            "reasoning_summary": "Ok.",
            "textual_basis": ["Exegézis — x"],
            "warnings": [],
            "missing_information": [],
        },
        ensure_ascii=False,
    )


def _valid_assess_json() -> str:
    return json.dumps(
        {
            "assessment": {
                "text_fidelity": "Megfelelő — hű.",
                "clarity": "Megfelelő — világos.",
                "unity": "Megfelelő — egy állítás.",
                "theological_accuracy": "Megfelelő — pontos.",
                "scope": "Megfelelő — arányos.",
                "statement_quality": "Megfelelő — állítás.",
                "application_confusion": "Megfelelő — nem kever.",
            },
            "strengths": ["s1"],
            "revision_priorities": [],
            "revised_version": "Átdolgozott mondat.",
            "warnings": [],
        },
        ensure_ascii=False,
    )


class _CountingGenerator:
    """Hívásszámláló mock `generate_fn` — sosem hív hálózatot."""

    def __init__(self, response: str = "") -> None:
        self.response = response or _valid_suggest_json()
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


class _SequenceGenerator:
    """Hívásonként MÁS választ adó mock — a kontrollált retry teszteléséhez."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


_SUGGEST_KWARGS = dict(
    passage="1Móz 32,23-32",
    exegesis="A szakasz a küzdelemről és a névváltoztatásról szól, valódi értelmezésbeli feszültséggel.",
)


# =============================================================================
# Token-budget — valós méréssel alátámasztva, nem találgatás
# =============================================================================


def test_suggest_tab_has_a_dedicated_evidence_based_token_budget():
    import app

    assert "Textus fő gondolat — javaslat" in app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB
    budget = app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB["Textus fő gondolat — javaslat"]
    observed_max = 4001  # 3 valós Gemini-mérés (1Móz 32,23-32): 2740-4001
    assert budget >= observed_max * 1.5
    assert budget <= observed_max * 3
    assert app._default_max_output_tokens("Textus fő gondolat — javaslat") == budget


def test_assess_tab_has_a_dedicated_evidence_based_token_budget():
    import app

    assert "Textus fő gondolat — értékelés" in app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB
    budget = app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB["Textus fő gondolat — értékelés"]
    observed_max = 3476  # valós Gemini-mérés (1Móz 32,23-32)
    assert budget >= observed_max * 1.5
    assert budget <= observed_max * 3


def test_generic_4096_fallback_no_longer_applies_to_main_idea_tabs():
    import app

    assert app._default_max_output_tokens("Textus fő gondolat — javaslat") != 4096
    assert app._default_max_output_tokens("Textus fő gondolat — értékelés") != 4096


# =============================================================================
# response_schema + truncation-safe hívás
# =============================================================================


def test_suggest_call_uses_json_mode_and_response_schema():
    gen = _CountingGenerator()
    mi_ai.suggest_text_main_idea(**_SUGGEST_KWARGS, generate_fn=gen)
    assert len(gen.calls) == 1
    kwargs = gen.calls[0]["kwargs"]
    assert kwargs.get("response_mime_type") == "application/json"
    assert kwargs.get("response_schema") == mi_ai.MAIN_IDEA_SUGGEST_RESPONSE_SCHEMA
    assert kwargs.get("truncation_notice_mode") == "never"


def test_assess_call_uses_json_mode_and_response_schema():
    gen = _CountingGenerator(_valid_assess_json())
    mi_ai.assess_user_main_idea(
        passage="1Móz 32,23-32",
        user_main_idea="Jákób Istennel küzd a Jabbóknál.",
        generate_fn=gen,
    )
    assert len(gen.calls) == 1
    kwargs = gen.calls[0]["kwargs"]
    assert kwargs.get("response_mime_type") == "application/json"
    assert kwargs.get("response_schema") == mi_ai.MAIN_IDEA_ASSESS_RESPONSE_SCHEMA
    assert kwargs.get("truncation_notice_mode") == "never"


def test_response_schemas_have_required_top_level_keys():
    assert set(mi_ai.MAIN_IDEA_SUGGEST_RESPONSE_SCHEMA["required"]) == {
        "recommended",
        "expanded_summary",
        "alternatives",
        "reasoning_summary",
        "textual_basis",
        "warnings",
        "missing_information",
    }
    assert set(mi_ai.MAIN_IDEA_ASSESS_RESPONSE_SCHEMA["required"]) == {
        "assessment",
        "strengths",
        "revision_priorities",
        "revised_version",
        "warnings",
    }


# =============================================================================
# Kontrollált retry — KIZÁRÓLAG JSON-kinyerési hibánál
# =============================================================================


def test_suggest_retry_recovers_from_a_truncated_first_response():
    gen = _SequenceGenerator(["{\"recommended\": \"csonka", _valid_suggest_json("Helyreállt javaslat.")])
    result = mi_ai.suggest_text_main_idea(**_SUGGEST_KWARGS, generate_fn=gen)
    assert len(gen.calls) == 2
    assert result.ok is True
    assert result.recommended == "Helyreállt javaslat."
    # A retry-prompt tartalmazza a korrekciós jelzést.
    assert "KORREKCIÓ" in gen.calls[1]["prompt"]


def test_suggest_retry_gives_up_after_second_invalid_response():
    gen = _SequenceGenerator(["nem json {{{", "still not json {{{"])
    result = mi_ai.suggest_text_main_idea(**_SUGGEST_KWARGS, generate_fn=gen)
    assert len(gen.calls) == 2
    assert result.ok is False
    assert "érvényes JSON" in result.error_message


def test_suggest_does_not_retry_on_semantically_thin_but_valid_json():
    """A parser megengedő: hiányzó/üres mezőket alapértékkel tölt ki — ez
    NEM JSON-kinyerési hiba, tehát NEM váltja ki a retryt (1 hívás elég)."""
    gen = _CountingGenerator(json.dumps({"recommended": "Csak ez van."}, ensure_ascii=False))
    result = mi_ai.suggest_text_main_idea(**_SUGGEST_KWARGS, generate_fn=gen)
    assert len(gen.calls) == 1
    assert result.ok is True
    assert result.recommended == "Csak ez van."


def test_assess_retry_recovers_from_a_truncated_first_response():
    gen = _SequenceGenerator(["{\"assessment\": {\"text_fidelity\": \"csonka", _valid_assess_json()])
    result = mi_ai.assess_user_main_idea(
        passage="1Móz 32,23-32",
        user_main_idea="Jákób Istennel küzd a Jabbóknál.",
        exegesis="A szakasz a küzdelemről és a névváltoztatásról szól.",
        generate_fn=gen,
    )
    assert len(gen.calls) == 2
    assert result.ok is True
    assert result.revised_version == "Átdolgozott mondat."


def test_assess_retry_gives_up_after_second_invalid_response():
    gen = _SequenceGenerator(["nem json {{{", "still not json {{{"])
    result = mi_ai.assess_user_main_idea(
        passage="1Móz 32,23-32",
        user_main_idea="Jákób Istennel küzd a Jabbóknál.",
        generate_fn=gen,
    )
    assert len(gen.calls) == 2
    assert result.ok is False
    assert "érvényes JSON" in result.error_message


# =============================================================================
# _diagnose_invalid_json_response — determinisztikus osztályozás
# =============================================================================


def test_diagnose_truncated_response():
    cut_off = '{"recommended": "A textus fő gondolata itt kezdődik és nem zárul le'
    assert "}" not in cut_off
    assert mi_ai._diagnose_invalid_json_response(cut_off) == "not_json:truncated_response"


def test_diagnose_prose_before_json():
    raw = 'Íme a válaszom:\n{"recommended": "x", "expanded_summary": "", "alternatives": [], "reasoning_summary": "", "textual_basis": [], "warnings": [], "missing_information": []}'
    assert mi_ai._diagnose_invalid_json_response(raw) == "not_json:prose_before_json"


def test_diagnose_no_json_object_found():
    assert mi_ai._diagnose_invalid_json_response("teljesen sima szöveg, se kapcsos zárójel") == "not_json:no_json_object_found"


def test_diagnose_empty_or_api_error():
    assert mi_ai._diagnose_invalid_json_response("") == "not_json:empty_or_api_error"
    assert mi_ai._diagnose_invalid_json_response("⚠️ Hiba történt.") == "not_json:empty_or_api_error"
