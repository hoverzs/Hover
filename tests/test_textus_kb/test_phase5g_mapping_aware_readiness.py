"""Mapping-aware staging readiness + blind report guarantees (Phase 5G fix)."""

from __future__ import annotations

from textus_kb.grounded_compare import format_compare_report
from textus_kb.staging_readiness import (
    DEFAULT_CRITERIA,
    STATUS_NOT_READY,
    StagingReadinessCriteria,
    evaluate_staging_readiness,
    is_grounded_hallucination_elevated,
    map_ab_preference_to_system,
    map_hallucination_risk_to_system,
    resolve_blind_mapping,
)


def test_resolve_blind_mapping_valid_and_fail_closed() -> None:
    ok, err = resolve_blind_mapping({"blind_mapping": {"A": "grounded", "B": "production"}})
    assert err is None
    assert ok == {"A": "grounded", "B": "production"}

    missing, reason = resolve_blind_mapping({})
    assert missing is None
    assert reason == "missing_blind_mapping"

    amb, reason2 = resolve_blind_mapping({"blind_mapping": {"A": "grounded", "B": "grounded"}})
    assert amb is None
    assert reason2 == "ambiguous_blind_mapping"


def test_map_preference_grounded_and_production_wins() -> None:
    a_grounded = {"A": "grounded", "B": "production"}
    b_grounded = {"A": "production", "B": "grounded"}

    # A=grounded, reviewer A -> grounded win
    assert map_ab_preference_to_system("A", a_grounded) == "grounded"
    # B=grounded, reviewer B -> grounded win
    assert map_ab_preference_to_system("B", b_grounded) == "grounded"
    # A=grounded, reviewer B -> production win
    assert map_ab_preference_to_system("B", a_grounded) == "production"
    # B=grounded, reviewer A -> production win
    assert map_ab_preference_to_system("A", b_grounded) == "production"
    # equal under both mappings
    assert map_ab_preference_to_system("equal", a_grounded) == "equal"
    assert map_ab_preference_to_system("equal", b_grounded) == "equal"


def test_map_hallucination_risk_mapping_aware() -> None:
    a_grounded = {"A": "grounded", "B": "production"}
    b_grounded = {"A": "production", "B": "grounded"}

    assert map_hallucination_risk_to_system("A", a_grounded) == "grounded_only"
    assert map_hallucination_risk_to_system("B", a_grounded) == "production_only"
    assert map_hallucination_risk_to_system("A", b_grounded) == "production_only"
    assert map_hallucination_risk_to_system("B", b_grounded) == "grounded_only"
    assert map_hallucination_risk_to_system("both", a_grounded) == "both"
    assert map_hallucination_risk_to_system("neither", a_grounded) == "neither"
    assert map_hallucination_risk_to_system("unclear", a_grounded) == "unclear"

    assert is_grounded_hallucination_elevated("grounded_only") is True
    assert is_grounded_hallucination_elevated("both") is True
    assert is_grounded_hallucination_elevated("production_only") is False
    assert is_grounded_hallucination_elevated("neither") is False
    assert is_grounded_hallucination_elevated("unclear") is False


def _pair(
    *,
    passage: str,
    module: str,
    mapping: dict[str, str],
    overall: str,
    factual: str = "equal",
    hallucination: str = "neither",
) -> dict:
    return {
        "passage": passage,
        "module": module,
        "provider_model": "gemini-live",
        "grounded_status": "success",
        "production_output": "prod",
        "grounded_output": "grounded",
        "source_ids": ["acai"],
        "blind_mapping": mapping,
        "review": {
            "overall_preference": overall,
            "factual_accuracy_preference": factual,
            "hallucination_risk": hallucination,
        },
    }


def test_readiness_a_grounded_reviewer_a_is_grounded_win() -> None:
    mapping = {"A": "grounded", "B": "production"}
    live = [
        _pair(
            passage=p,
            module=m,
            mapping=mapping,
            overall="A",
            factual="equal",
            hallucination="neither",
        )
        for p in ("John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30")
        for m in ("exegesis", "historical_context")
    ]
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["grounded_preferred_or_equal_ratio"] == 1.0
    assert result["status"] == "ready_for_limited_staging"


def test_readiness_b_grounded_reviewer_b_is_grounded_win() -> None:
    mapping = {"A": "production", "B": "grounded"}
    live = [
        _pair(
            passage=p,
            module=m,
            mapping=mapping,
            overall="B",
            factual="equal",
            hallucination="neither",
        )
        for p in ("John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30")
        for m in ("exegesis", "historical_context")
    ]
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["grounded_preferred_or_equal_ratio"] == 1.0
    assert result["ready"] is True


def test_readiness_swapped_mapping_does_not_treat_label_b_as_grounded() -> None:
    """If A=grounded and reviewer picks B, that is a production win — not grounded."""
    mapping = {"A": "grounded", "B": "production"}
    live = [
        _pair(
            passage=p,
            module=m,
            mapping=mapping,
            overall="B",  # production preferred
            factual="B",  # production preferred => grounded worse
            hallucination="B",  # production_only — not grounded elevated
        )
        for p in ("John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30")
        for m in ("exegesis", "historical_context")
    ]
    criteria = StagingReadinessCriteria(
        min_live_ab_pairs=8,
        min_distinct_passages=4,
        min_passages_with_both_modules=2,
        min_overall_b_or_equal_ratio=0.75,
        max_factual_b_worse_ratio=0.25,
        max_hallucination_b_elevated_ratio=0.20,
    )
    result = evaluate_staging_readiness(live_artifacts=live, criteria=criteria)
    assert result["metrics"]["grounded_preferred_or_equal_ratio"] == 0.0
    assert result["metrics"]["factual_grounded_worse_ratio"] == 1.0
    assert result["metrics"]["hallucination_grounded_elevated_ratio"] == 0.0
    assert any("grounded_preferred_or_equal_ratio" in u for u in result["unmet_criteria"])
    assert any("factual_grounded_worse_ratio" in v for v in result["veto_reasons"])
    assert not any("hallucination_grounded_elevated" in v for v in result["veto_reasons"])
    assert result["status"] == STATUS_NOT_READY


def test_missing_mapping_fail_closed() -> None:
    live = [
        {
            "passage": "John.4.1-42",
            "module": "exegesis",
            "provider_model": "live",
            "grounded_status": "success",
            "production_output": "p",
            "grounded_output": "g",
            "source_ids": ["acai"],
            # no blind_mapping
            "review": {"overall_preference": "B", "hallucination_risk": "neither"},
        }
    ]
    result = evaluate_staging_readiness(
        live_artifacts=live,
        criteria=StagingReadinessCriteria(
            min_live_ab_pairs=1,
            min_distinct_passages=1,
            min_passages_with_both_modules=0,
            require_historical_context=False,
        ),
    )
    assert result["status"] == STATUS_NOT_READY
    assert any("missing_or_ambiguous_blind_mapping" in v for v in result["veto_reasons"])


def test_blind_report_hides_mapping_reveal_shows_it() -> None:
    artifact = {
        "run_id": "r1",
        "passage": "John.4.1-42",
        "module": "exegesis",
        "timestamp": "2026-01-01T00:00:00Z",
        "blind": True,
        "blind_mapping": {"A": "grounded", "B": "production"},
        "production_output": "PROD_TEXT",
        "grounded_output": "GROUNDED_TEXT",
        "grounded_status": "success",
        "source_ids": ["acai"],
        "source_trace": {},
        "metrics": {},
        "review": {"overall_preference": "A"},
        "provider_call_count": 2,
        "production_prompt_estimated_tokens": 1,
        "grounded_prompt_estimated_tokens": 1,
        "kb_context_estimated_tokens": 1,
    }
    blind = format_compare_report(artifact, reveal_mapping=False)
    assert "blind: true (mapping withheld from reviewer-facing text)" in blind
    assert "blind_mapping:" not in blind
    assert '"A": "grounded"' not in blind

    revealed = format_compare_report(artifact, reveal_mapping=True)
    assert "blind_mapping:" in revealed
    assert "grounded" in revealed
    assert "production" in revealed
