from __future__ import annotations

import json

from illustration_engine.qa_agent import (
    QAIssue,
    QAVerdict,
    build_qa_prompt,
    build_repair_prompt,
    reconcile_deterministic_strategy_issue,
    run_content_qa,
    run_repair,
)


def _kwargs(**overrides) -> dict:
    base = dict(
        source_code="SRC",
        title_original="Original Title",
        original_text="Once upon a time, something funny happened.",
        title_hu="Cím",
        modern_hu_text="Egyszer volt, hol nem volt, valami vicces történt.",
        summary_hu="Összefoglaló.",
        moral_hu=None,
        tone="humoros",
        derivation_type="full_story_translation",
        current_expected_mode="direct_unit",
        current_expected_derivation_type="full_story_translation",
    )
    base.update(overrides)
    return base


def _llm(response) -> callable:
    if isinstance(response, dict):
        return lambda prompt: json.dumps(response)
    return lambda prompt: response


def test_pass_verdict_parsed_correctly() -> None:
    verdict = run_content_qa(
        **_kwargs(),
        llm_generate=_llm({"status": "PASS", "confidence": 0.95, "issues": [], "rationale": "OK"}),
    )
    assert verdict.status == "PASS"
    assert verdict.confidence == 0.95
    assert verdict.issues == ()


def test_needs_attention_verdict_with_issues_parsed() -> None:
    verdict = run_content_qa(
        **_kwargs(),
        llm_generate=_llm(
            {
                "status": "NEEDS_ATTENTION",
                "confidence": 0.6,
                "issues": [{"code": "poor_hungarian", "detail": "furcsa mondat"}],
                "rationale": "Van egy apró probléma.",
            }
        ),
    )
    assert verdict.status == "NEEDS_ATTENTION"
    assert verdict.issues == (QAIssue(code="POOR_HUNGARIAN", detail="furcsa mondat"),)


def test_fail_verdict_parsed() -> None:
    verdict = run_content_qa(
        **_kwargs(),
        llm_generate=_llm(
            {
                "status": "FAIL",
                "confidence": 0.9,
                "issues": [{"code": "HALLUCINATED_DETAIL", "detail": "kitalált szereplő"}],
                "rationale": "Súlyos hűségi hiba.",
            }
        ),
    )
    assert verdict.status == "FAIL"


def test_confidence_clamped_to_0_1_range() -> None:
    verdict = run_content_qa(**_kwargs(), llm_generate=_llm({"status": "PASS", "confidence": 5.0, "issues": []}))
    assert verdict.confidence == 1.0

    verdict2 = run_content_qa(**_kwargs(), llm_generate=_llm({"status": "PASS", "confidence": -3.0, "issues": []}))
    assert verdict2.confidence == 0.0


def test_malformed_json_fails_closed() -> None:
    verdict = run_content_qa(**_kwargs(), llm_generate=_llm("this is not json at all"))
    assert verdict.status == "FAIL"
    assert verdict.confidence == 0.0
    assert any(i.code == "QA_PARSE_ERROR" for i in verdict.issues)


def test_missing_status_fails_closed() -> None:
    verdict = run_content_qa(**_kwargs(), llm_generate=_llm({"confidence": 0.9, "issues": []}))
    assert verdict.status == "FAIL"
    assert any(i.code == "QA_PARSE_ERROR" for i in verdict.issues)


def test_invalid_status_value_fails_closed() -> None:
    verdict = run_content_qa(**_kwargs(), llm_generate=_llm({"status": "MAYBE", "confidence": 0.9, "issues": []}))
    assert verdict.status == "FAIL"


def test_markdown_fenced_json_response_parsed() -> None:
    raw = '```json\n{"status": "PASS", "confidence": 0.8, "issues": []}\n```'
    verdict = run_content_qa(**_kwargs(), llm_generate=_llm(raw))
    assert verdict.status == "PASS"


def test_trailing_comma_tolerated() -> None:
    raw = '{"status": "PASS", "confidence": 0.8, "issues": [],}'
    verdict = run_content_qa(**_kwargs(), llm_generate=_llm(raw))
    assert verdict.status == "PASS"


def test_unknown_issue_code_still_captured() -> None:
    verdict = run_content_qa(
        **_kwargs(),
        llm_generate=_llm(
            {"status": "NEEDS_ATTENTION", "confidence": 0.5, "issues": [{"code": "SOMETHING_NEW", "detail": "x"}]}
        ),
    )
    assert verdict.issues[0].code == "SOMETHING_NEW"


def test_prompt_states_moral_hu_optional_note_when_empty() -> None:
    prompt = build_qa_prompt(**_kwargs(moral_hu=None))
    assert "opcionális" in prompt
    assert "NEM hiba" in prompt


def test_prompt_gives_strategy_context_but_tells_llm_not_to_judge_it() -> None:
    """Phase 3H.1: the prompt still SHOWS the model the current expected
    strategy (context), but explicitly instructs it NOT to emit a
    STRATEGY_MISMATCH verdict -- that issue code is deterministic-only
    (see reconcile_deterministic_strategy_issue)."""
    prompt = build_qa_prompt(
        **_kwargs(derivation_type="full_story_translation", current_expected_mode="unit_proposal", current_expected_derivation_type=None)
    )
    assert "unit_proposal" in prompt
    assert "NE adj vissza" in prompt
    assert "STRATEGY_MISMATCH" in prompt  # mentioned only in the "don't use this" instruction


def test_prompt_does_not_offer_strategy_mismatch_as_a_usable_code() -> None:
    prompt = build_qa_prompt(**_kwargs())
    # The actual comma-separated code list is everything after the final
    # colon in the "Ismert issue code-ok..." sentence -- the sentence
    # ITSELF mentions STRATEGY_MISMATCH (in the "don't use it" aside),
    # but that must not appear in the offered list past the colon.
    codes_line = prompt.split("Ismert issue code-ok")[1].split(":", 1)[1].split(".")[0]
    assert "STRATEGY_MISMATCH" not in codes_line
    assert "BAD_SUMMARY" in codes_line


# --- repair --------------------------------------------------------------


def _repair_kwargs(**overrides) -> dict:
    base = dict(
        source_code="SRC",
        title_original="Original Title",
        original_text="Once upon a time, something funny happened.",
        title_hu="Rossz cím",
        modern_hu_text="Furán megfogalmazott szöveg.",
        summary_hu="Összefoglaló.",
        moral_hu="Erőltetett tanulság, amit nem kellett volna.",
        issues=(QAIssue(code="FORCED_MORAL", detail="A moral_hu ráerőltetett."),),
    )
    base.update(overrides)
    return base


def test_repair_returns_corrected_fields() -> None:
    result = run_repair(
        **_repair_kwargs(),
        llm_generate=_llm(
            {
                "title_hu": "Jó cím",
                "modern_hu_text": "Javított szöveg.",
                "summary_hu": "Javított összefoglaló.",
                "moral_hu": None,
            }
        ),
    )
    assert result == {
        "title_hu": "Jó cím",
        "modern_hu_text": "Javított szöveg.",
        "summary_hu": "Javított összefoglaló.",
        "moral_hu": None,
    }


def test_repair_clears_forced_moral_to_null() -> None:
    """The concrete FORCED_MORAL repair scenario -- the repair must be
    able to actually CLEAR moral_hu, not just replace its text."""
    result = run_repair(
        **_repair_kwargs(),
        llm_generate=_llm(
            {"title_hu": "Cím", "modern_hu_text": "Szöveg.", "summary_hu": "Összefoglaló.", "moral_hu": None}
        ),
    )
    assert result["moral_hu"] is None


def test_repair_malformed_json_returns_none() -> None:
    result = run_repair(**_repair_kwargs(), llm_generate=_llm("not json"))
    assert result is None


def test_repair_missing_required_field_returns_none() -> None:
    result = run_repair(
        **_repair_kwargs(),
        llm_generate=_llm({"title_hu": "Cím", "modern_hu_text": "Szöveg."}),  # summary_hu missing
    )
    assert result is None


def test_repair_wrong_type_for_moral_hu_returns_none() -> None:
    result = run_repair(
        **_repair_kwargs(),
        llm_generate=_llm(
            {"title_hu": "Cím", "modern_hu_text": "Szöveg.", "summary_hu": "Összefoglaló.", "moral_hu": ["not", "a", "string"]}
        ),
    )
    assert result is None


def test_repair_prompt_forbids_editing_original_text_and_strategy() -> None:
    prompt = build_repair_prompt(**_repair_kwargs())
    assert "VÁLTOZATLAN" in prompt
    assert "STRATEGY_MISMATCH" in prompt
    assert "javítható" in prompt


# ---------------------------------------------------------------------------
# Phase 3H.1: STRATEGY_MISMATCH is deterministic-only, never an LLM opinion.
# The 4 concrete regression cases from the real pilot audit.
# ---------------------------------------------------------------------------


def _run_qa_with_strategy(*, original_text_length: int, derivation_type: str, llm_response: dict):
    from illustration_engine.enrichment_pipeline import derive_enrichment_strategy

    strategy = derive_enrichment_strategy(original_text_length)
    return run_content_qa(
        **_kwargs(
            derivation_type=derivation_type,
            current_expected_mode=strategy.expected_mode,
            current_expected_derivation_type=strategy.expected_derivation_type,
        ),
        llm_generate=_llm(llm_response),
    )


def test_no_mismatch_293_chars_full_story_translation() -> None:
    """#17 regression: 293 chars + full_story_translation -> NO
    STRATEGY_MISMATCH, even though the real pilot run had the LLM
    false-positive one here."""
    verdict = _run_qa_with_strategy(
        original_text_length=293,
        derivation_type="full_story_translation",
        llm_response={
            "status": "NEEDS_ATTENTION", "confidence": 0.9,
            "issues": [{"code": "STRATEGY_MISMATCH", "detail": "llm false positive"}],
        },
    )
    assert not any(i.code == "STRATEGY_MISMATCH" for i in verdict.issues)
    assert verdict.status == "PASS"  # the false-positive was the ONLY issue -- recomputed to PASS


def test_no_mismatch_1225_chars_full_story_translation() -> None:
    """#20 regression."""
    verdict = _run_qa_with_strategy(
        original_text_length=1225, derivation_type="full_story_translation",
        llm_response={"status": "PASS", "confidence": 1.0, "issues": []},
    )
    assert verdict.status == "PASS"
    assert not any(i.code == "STRATEGY_MISMATCH" for i in verdict.issues)


def test_no_mismatch_323_chars_full_story_translation() -> None:
    """#22 regression."""
    verdict = _run_qa_with_strategy(
        original_text_length=323, derivation_type="full_story_translation",
        llm_response={"status": "PASS", "confidence": 1.0, "issues": []},
    )
    assert verdict.status == "PASS"
    assert not any(i.code == "STRATEGY_MISMATCH" for i in verdict.issues)


def test_real_mismatch_2570_chars_full_story_translation_detected() -> None:
    """#19 (Alfred) regression: 2570 chars stored as full_story_translation
    -- deterministically SHOULD be condensed_story. A real mismatch must
    ALWAYS be flagged, even if the LLM itself says PASS."""
    verdict = _run_qa_with_strategy(
        original_text_length=2570, derivation_type="full_story_translation",
        llm_response={"status": "PASS", "confidence": 1.0, "issues": []},
    )
    assert verdict.status == "NEEDS_ATTENTION"  # upgraded from the model's PASS
    mismatch_issues = [i for i in verdict.issues if i.code == "STRATEGY_MISMATCH"]
    assert len(mismatch_issues) == 1
    assert "condensed_story" in mismatch_issues[0].detail


def test_real_mismatch_never_downgraded_below_llm_fail() -> None:
    verdict = _run_qa_with_strategy(
        original_text_length=2570, derivation_type="full_story_translation",
        llm_response={"status": "FAIL", "confidence": 0.9, "issues": [{"code": "MEANING_SHIFT", "detail": "x"}]},
    )
    assert verdict.status == "FAIL"  # never downgraded
    assert any(i.code == "STRATEGY_MISMATCH" for i in verdict.issues)
    assert any(i.code == "MEANING_SHIFT" for i in verdict.issues)


def test_reconcile_llm_provided_strategy_mismatch_is_always_replaced_with_deterministic_detail() -> None:
    """Even when the LLM happens to guess correctly that there IS a
    mismatch, its own issue is still discarded and replaced with the
    deterministic one -- the LLM's STRATEGY_MISMATCH is NEVER trusted
    verbatim, correct guess or not."""
    verdict = QAVerdict(
        status="NEEDS_ATTENTION", confidence=0.5,
        issues=(QAIssue(code="STRATEGY_MISMATCH", detail="llm's own guess, must be discarded"),),
        rationale="r",
    )
    result = reconcile_deterministic_strategy_issue(
        verdict, stored_derivation_type="full_story_translation",
        current_expected_mode="direct_unit", current_expected_derivation_type="condensed_story",
    )
    assert len(result.issues) == 1
    assert result.issues[0].detail != "llm's own guess, must be discarded"
    assert "determinisztikus ellenőrzés" in result.issues[0].detail


def test_reconcile_drops_false_positive_but_keeps_other_genuine_issues() -> None:
    verdict = QAVerdict(
        status="NEEDS_ATTENTION", confidence=0.7,
        issues=(QAIssue(code="STRATEGY_MISMATCH", detail="wrong"), QAIssue(code="POOR_HUNGARIAN", detail="x")),
        rationale="r",
    )
    result = reconcile_deterministic_strategy_issue(
        verdict, stored_derivation_type="full_story_translation",
        current_expected_mode="direct_unit", current_expected_derivation_type="full_story_translation",
    )
    assert not any(i.code == "STRATEGY_MISMATCH" for i in result.issues)
    assert any(i.code == "POOR_HUNGARIAN" for i in result.issues)
    assert result.status == "NEEDS_ATTENTION"  # kept -- POOR_HUNGARIAN alone still justifies it


def test_reconcile_noop_when_llm_never_mentions_strategy_and_no_mismatch() -> None:
    verdict = QAVerdict(status="PASS", confidence=1.0, issues=(), rationale="r")
    result = reconcile_deterministic_strategy_issue(
        verdict, stored_derivation_type="full_story_translation",
        current_expected_mode="direct_unit", current_expected_derivation_type="full_story_translation",
    )
    assert result == verdict
