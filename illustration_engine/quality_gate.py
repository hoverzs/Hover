"""Phase 3H.1: batch quality-gate evaluation.

The denominator for PASS/FAIL rate is the ORIGINAL SELECTED COHORT SIZE
(frozen at `create_run()` time), never just "however many units ended up
getting created." A deterministic enrichment rejection or a provider/
processing failure is still an outcome for that selected story -- it
must be counted in the gate's denominator, never silently excluded
because no `illustration_units` row exists for it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CohortGateResult:
    selected_count: int
    pass_count: int
    needs_attention_count: int
    fail_count: int
    enrichment_rejected_count: int
    processing_failed_count: int
    pass_rate: float
    fail_or_error_rate: float
    gate_passed: bool
    reasons: tuple[str, ...]


def evaluate_cohort_quality_gate(
    *,
    selected_count: int,
    pass_count: int,
    needs_attention_count: int,
    fail_count: int,
    enrichment_rejected_count: int,
    processing_failed_count: int,
    checksum_mismatch_count: int,
    auto_approved_count: int,
    published_count: int,
    min_pass_rate: float = 0.90,
    max_fail_or_error_rate: float = 0.02,
) -> CohortGateResult:
    """`selected_count` is the frozen cohort size -- EVERY selected story
    must land in exactly one of the five outcome buckets
    (pass/needs_attention/fail/enrichment_rejected/processing_failed);
    if the buckets don't sum to `selected_count`, that itself is a gate
    failure (something vanished from the accounting), not a silently
    ignored discrepancy."""
    if selected_count <= 0:
        raise ValueError(f"selected_count must be positive, got {selected_count!r}")

    accounted = pass_count + needs_attention_count + fail_count + enrichment_rejected_count + processing_failed_count
    reasons: list[str] = []
    if accounted != selected_count:
        reasons.append(
            f"cohort accounting mismatch: {accounted} accounted for vs {selected_count} selected "
            "-- every selected story must land in exactly one outcome bucket"
        )

    pass_rate = pass_count / selected_count
    fail_or_error_count = fail_count + enrichment_rejected_count + processing_failed_count
    fail_or_error_rate = fail_or_error_count / selected_count

    if pass_rate < min_pass_rate:
        reasons.append(f"PASS rate {pass_rate:.1%} ({pass_count}/{selected_count}) < required {min_pass_rate:.0%}")
    if fail_or_error_rate > max_fail_or_error_rate:
        reasons.append(
            f"FAIL/error rate {fail_or_error_rate:.1%} ({fail_or_error_count}/{selected_count}) "
            f"> allowed {max_fail_or_error_rate:.0%}"
        )
    if checksum_mismatch_count:
        reasons.append(f"{checksum_mismatch_count} checksum mismatch(es) -- provenance breach")
    if auto_approved_count:
        reasons.append(f"{auto_approved_count} unit(s) auto-approved -- must be zero")
    if published_count:
        reasons.append(f"{published_count} unit(s) published -- must be zero")

    return CohortGateResult(
        selected_count=selected_count,
        pass_count=pass_count,
        needs_attention_count=needs_attention_count,
        fail_count=fail_count,
        enrichment_rejected_count=enrichment_rejected_count,
        processing_failed_count=processing_failed_count,
        pass_rate=pass_rate,
        fail_or_error_rate=fail_or_error_rate,
        gate_passed=not reasons,
        reasons=tuple(reasons),
    )


__all__ = ["CohortGateResult", "evaluate_cohort_quality_gate"]
