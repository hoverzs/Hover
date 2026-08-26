"""Phase 5J-B: reliability severity separate from comparative hallucination risk."""

from __future__ import annotations

from textus_kb.compare_store import (
    HumanReview,
    RELIABILITY_ISSUE_CHOICES,
    _validate_review_payload,
)
from textus_kb.grounded_compare import format_compare_report
from textus_kb.staging_readiness import (
    DEFAULT_CRITERIA,
    STATUS_NOT_READY,
    STATUS_READY,
    StagingReadinessCriteria,
    classify_grounded_blocking_reliability,
    evaluate_staging_readiness,
    is_grounded_hallucination_elevated,
    map_hallucination_risk_to_system,
)


def test_classify_grounded_blocking_matrix() -> None:
    assert (
        classify_grounded_blocking_reliability(
            hallucination_system="grounded_only",
            reliability_issue="blocking_reliability",
        )
        == "blocking"
    )
    assert (
        classify_grounded_blocking_reliability(
            hallucination_system="production_only",
            reliability_issue="blocking_reliability",
        )
        == "not_blocking"
    )
    assert (
        classify_grounded_blocking_reliability(
            hallucination_system="both",
            reliability_issue="non_blocking_overclaim",
        )
        == "not_blocking"
    )
    assert (
        classify_grounded_blocking_reliability(
            hallucination_system="both",
            reliability_issue="blocking_reliability",
        )
        == "blocking"
    )
    assert (
        classify_grounded_blocking_reliability(
            hallucination_system="neither",
            reliability_issue="",
        )
        == "not_blocking"
    )
    assert (
        classify_grounded_blocking_reliability(
            hallucination_system="both",
            reliability_issue="",
        )
        == "unknown"
    )
    assert (
        classify_grounded_blocking_reliability(
            hallucination_system="grounded_only",
            reliability_issue="unclear",
        )
        == "unknown"
    )


def test_legacy_elevated_helper_unchanged() -> None:
    assert is_grounded_hallucination_elevated("grounded_only") is True
    assert is_grounded_hallucination_elevated("both") is True
    assert is_grounded_hallucination_elevated("production_only") is False


def _pair(
    *,
    passage: str,
    module: str,
    mapping: dict[str, str],
    overall: str = "equal",
    factual: str = "equal",
    hallucination: str = "neither",
    reliability_issue: str = "",
    reliability_category: str = "",
) -> dict:
    review = {
        "overall_preference": overall,
        "factual_accuracy_preference": factual,
        "hallucination_risk": hallucination,
    }
    if reliability_issue:
        review["reliability_issue"] = reliability_issue
    if reliability_category:
        review["reliability_category"] = reliability_category
    return {
        "passage": passage,
        "module": module,
        "provider_model": "gemini-live",
        "grounded_status": "success",
        "production_output": "prod",
        "grounded_output": "grounded",
        "source_ids": ["acai"],
        "blind_mapping": mapping,
        "review": review,
    }


def _campaign(
    *,
    hallucination: str,
    reliability_issue: str = "",
    mapping: dict[str, str] | None = None,
    overall: str = "B",
) -> list[dict]:
    mapping = mapping or {"A": "production", "B": "grounded"}
    return [
        _pair(
            passage=p,
            module=m,
            mapping=mapping,
            overall=overall,
            hallucination=hallucination,
            reliability_issue=reliability_issue,
        )
        for p in ("John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30")
        for m in ("exegesis", "historical_context")
    ]


def test_grounded_only_blocking_counted() -> None:
    live = _campaign(hallucination="B", reliability_issue="blocking_reliability")
    # B=grounded => grounded_only
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["hallucination_grounded_elevated_ratio"] == 1.0
    assert result["metrics"]["grounded_blocking_reliability_ratio"] == 1.0
    assert any("grounded_blocking_reliability_ratio" in v for v in result["veto_reasons"])
    assert not any("hallucination_grounded_elevated" in v for v in result["veto_reasons"])
    assert result["status"] == STATUS_NOT_READY


def test_production_only_blocking_not_counted_for_grounded() -> None:
    mapping = {"A": "grounded", "B": "production"}
    # Reviewer B => production_only; severity blocking on the production side issue.
    live = _campaign(
        hallucination="B",
        reliability_issue="blocking_reliability",
        mapping=mapping,
        overall="A",  # grounded overall win
    )
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["hallucination_grounded_elevated_ratio"] == 0.0
    assert result["metrics"]["grounded_blocking_reliability_ratio"] == 0.0
    assert result["metrics"]["reliability_annotation_unknown_count"] == 0
    assert result["status"] == STATUS_READY


def test_both_non_blocking_overclaim_not_counted() -> None:
    live = _campaign(hallucination="both", reliability_issue="non_blocking_overclaim")
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["hallucination_grounded_elevated_ratio"] == 1.0
    assert result["metrics"]["grounded_blocking_reliability_ratio"] == 0.0
    assert result["status"] == STATUS_READY


def test_both_blocking_reliability_counted() -> None:
    live = _campaign(hallucination="both", reliability_issue="blocking_reliability")
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["grounded_blocking_reliability_ratio"] == 1.0
    assert result["status"] == STATUS_NOT_READY


def test_neither_not_counted() -> None:
    live = _campaign(hallucination="neither")
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["hallucination_grounded_elevated_ratio"] == 0.0
    assert result["metrics"].get("grounded_blocking_reliability_ratio") == 0.0
    assert result["status"] == STATUS_READY


def test_missing_legacy_severity_fail_closed_not_silently_safe() -> None:
    live = _campaign(hallucination="both", reliability_issue="")
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["hallucination_grounded_elevated_ratio"] == 1.0
    assert "grounded_blocking_reliability_ratio" not in result["metrics"]
    assert result["metrics"]["reliability_annotation_unknown_count"] == 8
    assert any(
        "missing_or_unclear_reliability_issue" in v for v in result["veto_reasons"]
    )
    assert result["status"] == STATUS_NOT_READY


def test_randomized_mapping_grounded_on_a() -> None:
    mapping = {"A": "grounded", "B": "production"}
    live = _campaign(
        hallucination="A",
        reliability_issue="blocking_reliability",
        mapping=mapping,
        overall="A",
    )
    assert map_hallucination_risk_to_system("A", mapping) == "grounded_only"
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["metrics"]["grounded_blocking_reliability_ratio"] == 1.0


def test_blind_report_still_hides_mapping() -> None:
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
        "review": {
            "overall_preference": "A",
            "hallucination_risk": "both",
            "reliability_issue": "non_blocking_overclaim",
        },
        "provider_call_count": 2,
        "production_prompt_estimated_tokens": 1,
        "grounded_prompt_estimated_tokens": 1,
        "kb_context_estimated_tokens": 1,
    }
    blind = format_compare_report(artifact, reveal_mapping=False)
    assert "blind_mapping:" not in blind
    assert "reliability_issue: non_blocking_overclaim" in blind
    revealed = format_compare_report(artifact, reveal_mapping=True)
    assert "blind_mapping:" in revealed


def test_human_review_accepts_reliability_fields() -> None:
    payload = {
        "overall_preference": "B",
        "hallucination_risk": "both",
        "reliability_issue": "non_blocking_overclaim",
        "reliability_category": "linguistic_overclaim",
    }
    _validate_review_payload(payload)
    review = HumanReview.from_dict(payload)
    assert review.reliability_issue in RELIABILITY_ISSUE_CHOICES
    assert review.reliability_category == "linguistic_overclaim"


def test_legacy_elevated_metric_still_computed_under_swapped_mapping() -> None:
    """Phase 5H-A: production_only must not elevate; elevated not a readiness veto."""
    mapping = {"A": "grounded", "B": "production"}
    live = [
        _pair(
            passage=p,
            module=m,
            mapping=mapping,
            overall="B",  # production preferred
            factual="B",
            hallucination="B",  # production_only
            reliability_issue="blocking_reliability",
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
        max_grounded_blocking_reliability_ratio=0.20,
    )
    result = evaluate_staging_readiness(live_artifacts=live, criteria=criteria)
    assert result["metrics"]["hallucination_grounded_elevated_ratio"] == 0.0
    assert result["metrics"]["grounded_blocking_reliability_ratio"] == 0.0
    assert not any("hallucination_grounded_elevated" in v for v in result["veto_reasons"])
    assert not any("grounded_blocking_reliability" in v for v in result["veto_reasons"])
