from __future__ import annotations

import pytest

from illustration_engine.quality_gate import evaluate_cohort_quality_gate


def _base(**overrides) -> dict:
    base = dict(
        selected_count=50,
        pass_count=45,
        needs_attention_count=4,
        fail_count=1,
        enrichment_rejected_count=0,
        processing_failed_count=0,
        checksum_mismatch_count=0,
        auto_approved_count=0,
        published_count=0,
    )
    base.update(overrides)
    return base


def test_gate_passes_at_exact_thresholds() -> None:
    """45/50 PASS = 90.0%, 1/50 FAIL = 2.0% -- both exactly at the
    boundary, must PASS (>=90%, <=2%)."""
    result = evaluate_cohort_quality_gate(**_base())
    assert result.gate_passed is True
    assert result.pass_rate == 0.90
    assert result.fail_or_error_rate == 0.02
    assert result.reasons == ()


def test_gate_fails_below_pass_rate() -> None:
    result = evaluate_cohort_quality_gate(**_base(pass_count=44, needs_attention_count=5))
    assert result.gate_passed is False
    assert any("PASS rate" in r for r in result.reasons)


def test_gate_fails_above_fail_rate() -> None:
    result = evaluate_cohort_quality_gate(**_base(pass_count=44, fail_count=2, needs_attention_count=4))
    assert result.gate_passed is False
    assert any("FAIL/error rate" in r for r in result.reasons)


def test_selected_cohort_is_the_denominator_not_just_enriched_count() -> None:
    """The exact bug this module fixes: 3 stories were deterministically
    rejected during enrichment (never became a unit at all) -- they must
    still count against the 50-story denominator, not vanish."""
    # 47 enriched (42 PASS + 4 NEEDS_ATTENTION + 1 FAIL) + 3 enrichment-rejected = 50 selected
    result = evaluate_cohort_quality_gate(
        **_base(pass_count=42, needs_attention_count=4, fail_count=1, enrichment_rejected_count=3)
    )
    assert result.pass_rate == 42 / 50  # NOT 42/47
    assert result.pass_rate < 0.90
    assert result.gate_passed is False


def test_enrichment_rejected_counted_toward_fail_or_error_rate() -> None:
    result = evaluate_cohort_quality_gate(
        **_base(pass_count=46, needs_attention_count=1, fail_count=0, enrichment_rejected_count=3)
    )
    # fail_or_error = 0 fail + 3 rejected = 3/50 = 6% > 2%
    assert result.fail_or_error_rate == 3 / 50
    assert result.gate_passed is False
    assert any("FAIL/error rate" in r for r in result.reasons)


def test_processing_failed_counted_toward_fail_or_error_rate() -> None:
    result = evaluate_cohort_quality_gate(
        **_base(pass_count=46, needs_attention_count=1, fail_count=0, processing_failed_count=3)
    )
    assert result.fail_or_error_rate == 3 / 50
    assert result.gate_passed is False


def test_cohort_accounting_mismatch_is_itself_a_gate_failure() -> None:
    """If the buckets don't sum to selected_count, something vanished
    from the accounting -- must fail the gate, not silently pass."""
    result = evaluate_cohort_quality_gate(
        **_base(pass_count=40, needs_attention_count=4, fail_count=1)  # sums to 45, not 50
    )
    assert result.gate_passed is False
    assert any("accounting mismatch" in r for r in result.reasons)


def test_checksum_mismatch_always_fails_gate_regardless_of_rates() -> None:
    result = evaluate_cohort_quality_gate(**_base(checksum_mismatch_count=1))
    assert result.gate_passed is False
    assert any("checksum mismatch" in r for r in result.reasons)


def test_auto_approved_always_fails_gate() -> None:
    result = evaluate_cohort_quality_gate(**_base(auto_approved_count=1))
    assert result.gate_passed is False
    assert any("auto-approved" in r for r in result.reasons)


def test_published_always_fails_gate() -> None:
    result = evaluate_cohort_quality_gate(**_base(published_count=1))
    assert result.gate_passed is False
    assert any("published" in r for r in result.reasons)


def test_zero_selected_count_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_cohort_quality_gate(**_base(selected_count=0))


def test_clean_cohort_gate_passes() -> None:
    result = evaluate_cohort_quality_gate(
        **_base(pass_count=48, needs_attention_count=2, fail_count=0)
    )
    assert result.gate_passed is True
