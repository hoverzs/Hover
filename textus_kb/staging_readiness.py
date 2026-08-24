"""Staging readiness criteria and human-review summary (Phase 5F).

Deterministic rules over live A/B human reviews only. No LLM-as-judge.
Readiness is a report — it never flips runtime grounded flags.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from textus_kb.compare_store import DEFAULT_COMPARE_DB_PATH, list_compare_runs, load_compare_run

STATUS_INSUFFICIENT = "insufficient_human_review_data"
STATUS_NEEDS_MORE = "needs_more_review"
STATUS_NOT_READY = "not_ready"
STATUS_READY = "ready_for_limited_staging"


@dataclass(frozen=True)
class StagingReadinessCriteria:
    """Initial staging thresholds — not a scientific quality benchmark."""

    min_live_ab_pairs: int = 8
    min_distinct_passages: int = 4
    require_exegesis: bool = True
    require_historical_context: bool = True
    require_overall_review: bool = True
    min_passages_with_both_modules: int = 2
    # Overall: grounded (B) preferred or equal in at least this share of reviewed live pairs.
    min_overall_b_or_equal_ratio: float = 0.75
    # Factual: share where B is strictly worse than A must stay below this.
    max_factual_b_worse_ratio: float = 0.25
    # Hallucination: share where B (or both) is worse risk must stay below this.
    max_hallucination_b_elevated_ratio: float = 0.20
    max_grounded_error_rate: float = 0.25


DEFAULT_CRITERIA = StagingReadinessCriteria()


def is_live_compare_artifact(artifact: dict[str, Any]) -> bool:
    model = str(artifact.get("provider_model") or artifact.get("model_note") or "").lower()
    if not model or "mock" in model:
        return False
    return True


def has_human_overall_review(artifact: dict[str, Any]) -> bool:
    review = artifact.get("review") if isinstance(artifact.get("review"), dict) else {}
    return bool(str(review.get("overall_preference") or "").strip())


def _preference_counts(values: list[str]) -> dict[str, int]:
    counts = {"A": 0, "B": 0, "equal": 0, "unclear": 0, "other": 0}
    for raw in values:
        key = str(raw or "").strip()
        if key in counts:
            counts[key] += 1
        elif key:
            counts["other"] += 1
    return counts


def _load_all_artifacts(
    *,
    database_path: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    rows = list_compare_runs(database_path=database_path, limit=limit)
    artifacts: list[dict[str, Any]] = []
    for row in rows:
        art = load_compare_run(str(row["run_id"]), database_path=database_path)
        if art:
            artifacts.append(art)
    return artifacts


def build_review_summary(
    *,
    database_path: str | None = None,
    live_only: bool = False,
    module: str | None = None,
    criteria: StagingReadinessCriteria = DEFAULT_CRITERIA,
) -> dict[str, Any]:
    artifacts = _load_all_artifacts(database_path=database_path)
    if module:
        artifacts = [a for a in artifacts if a.get("module") == module]

    live = [a for a in artifacts if is_live_compare_artifact(a)]
    mock = [a for a in artifacts if not is_live_compare_artifact(a)]
    pool = live if live_only else artifacts

    reviewed = [a for a in pool if has_human_overall_review(a)]
    unreviewed = [a for a in pool if not has_human_overall_review(a)]
    live_reviewed = [
        a
        for a in live
        if has_human_overall_review(a)
        and str(a.get("grounded_status") or "") == "success"
        and bool(str(a.get("production_output") or "").strip())
    ]

    def _field_counts(field: str, items: list[dict[str, Any]]) -> dict[str, int]:
        return _preference_counts(
            [
                str((a.get("review") or {}).get(field) or "")
                for a in items
                if isinstance(a.get("review"), dict)
            ]
        )

    coverage_pairs = sorted(
        {
            (str(a.get("passage") or ""), str(a.get("module") or ""))
            for a in (live_reviewed if live_only else live)
        }
    )
    readiness = evaluate_staging_readiness(
        live_artifacts=live,
        criteria=criteria,
    )

    return {
        "database_path": str(database_path or DEFAULT_COMPARE_DB_PATH),
        "filters": {"live_only": live_only, "module": module},
        "totals": {
            "all": len(artifacts),
            "live": len(live),
            "mock": len(mock),
            "reviewed_in_filter": len(reviewed),
            "unreviewed_in_filter": len(unreviewed),
            "live_reviewed": len(live_reviewed),
        },
        "coverage": {
            "live_pairs": coverage_pairs,
            "live_passages": sorted({p for p, _ in coverage_pairs}),
            "live_modules": sorted({m for _, m in coverage_pairs}),
        },
        "preferences": {
            "overall": _field_counts("overall_preference", live_reviewed),
            "factual_accuracy": _field_counts("factual_accuracy_preference", live_reviewed),
            "exegetical_usefulness": _field_counts(
                "exegetical_usefulness_preference", live_reviewed
            ),
            "historical_grounding": _field_counts(
                "historical_grounding_preference", live_reviewed
            ),
            "clarity_style": _field_counts("clarity_style_preference", live_reviewed),
            "hallucination_risk": _field_counts("hallucination_risk", live_reviewed),
        },
        "grounded_status_live": _preference_counts(
            [str(a.get("grounded_status") or "") for a in live]
        ),
        "staging_readiness": readiness,
        "criteria": asdict(criteria),
        "note": (
            "Mock runs are excluded from staging readiness evidence. "
            "Readiness never enables TEXTUS_KB_GROUNDED_ENABLED."
        ),
    }


def evaluate_staging_readiness(
    *,
    live_artifacts: list[dict[str, Any]],
    criteria: StagingReadinessCriteria = DEFAULT_CRITERIA,
) -> dict[str, Any]:
    # Evidence for preference thresholds: live + successful generation + reviewed.
    live_success = [
        a
        for a in live_artifacts
        if str(a.get("grounded_status") or "") == "success"
        and bool(str(a.get("production_output") or "").strip())
    ]
    live_reviewed = [a for a in live_success if has_human_overall_review(a)]
    unmet: list[str] = []
    vetoes: list[str] = []

    live_pair_count = len(live_artifacts)
    live_success_count = len(live_success)
    live_reviewed_count = len(live_reviewed)
    passages = {str(a.get("passage") or "") for a in live_reviewed if a.get("passage")}
    modules = {str(a.get("module") or "") for a in live_reviewed if a.get("module")}

    by_passage: dict[str, set[str]] = {}
    for art in live_reviewed:
        by_passage.setdefault(str(art.get("passage") or ""), set()).add(
            str(art.get("module") or "")
        )
    both_module_passages = sum(
        1
        for mods in by_passage.values()
        if "exegesis" in mods and "historical_context" in mods
    )

    if live_reviewed_count < criteria.min_live_ab_pairs:
        unmet.append(
            f"live_reviewed_pairs {live_reviewed_count} < min {criteria.min_live_ab_pairs}"
        )
    if len(passages) < criteria.min_distinct_passages:
        unmet.append(
            f"distinct_passages {len(passages)} < min {criteria.min_distinct_passages}"
        )
    if criteria.require_exegesis and "exegesis" not in modules:
        unmet.append("missing_module:exegesis")
    if criteria.require_historical_context and "historical_context" not in modules:
        unmet.append("missing_module:historical_context")
    if both_module_passages < criteria.min_passages_with_both_modules:
        unmet.append(
            f"passages_with_both_modules {both_module_passages} < min "
            f"{criteria.min_passages_with_both_modules}"
        )

    # Preference ratios on live reviewed successful pairs only.
    overall_vals = [
        str((a.get("review") or {}).get("overall_preference") or "") for a in live_reviewed
    ]
    if live_reviewed_count:
        b_or_equal = sum(1 for v in overall_vals if v in {"B", "equal"})
        ratio = b_or_equal / live_reviewed_count
        if ratio < criteria.min_overall_b_or_equal_ratio:
            unmet.append(
                f"overall_b_or_equal_ratio {ratio:.3f} < {criteria.min_overall_b_or_equal_ratio}"
            )

        factual = [
            str((a.get("review") or {}).get("factual_accuracy_preference") or "")
            for a in live_reviewed
        ]
        factual_filled = [v for v in factual if v]
        if factual_filled:
            worse = sum(1 for v in factual_filled if v == "A")  # A preferred => B worse
            worse_ratio = worse / len(factual_filled)
            if worse_ratio > criteria.max_factual_b_worse_ratio:
                vetoes.append(
                    f"factual_b_worse_ratio {worse_ratio:.3f} > "
                    f"{criteria.max_factual_b_worse_ratio}"
                )

        hallu = [
            str((a.get("review") or {}).get("hallucination_risk") or "")
            for a in live_reviewed
        ]
        hallu_filled = [v for v in hallu if v]
        if hallu_filled:
            elevated = sum(1 for v in hallu_filled if v in {"B", "both"})
            elevated_ratio = elevated / len(hallu_filled)
            if elevated_ratio > criteria.max_hallucination_b_elevated_ratio:
                vetoes.append(
                    f"hallucination_b_elevated_ratio {elevated_ratio:.3f} > "
                    f"{criteria.max_hallucination_b_elevated_ratio}"
                )

        # Citation readiness veto when stored on successful reviewed runs.
        low_cite = [
            a
            for a in live_reviewed
            if isinstance(a.get("source_trace"), dict)
            and int((a.get("source_trace") or {}).get("selected_evidence_count") or 0) > 0
            and int((a.get("source_trace") or {}).get("citation_ready_count") or 0) == 0
        ]
        if low_cite:
            vetoes.append(f"citation_ready_missing_on_reviewed:{len(low_cite)}")

    if live_pair_count:
        errors = sum(1 for a in live_artifacts if str(a.get("grounded_status")) == "error")
        err_rate = errors / live_pair_count
        if err_rate > criteria.max_grounded_error_rate:
            vetoes.append(
                f"grounded_error_rate {err_rate:.3f} > {criteria.max_grounded_error_rate}"
            )

    # Provenance veto: live success runs must carry source_ids.
    missing_sources = [
        a
        for a in live_success
        if not (a.get("source_ids") or [])
    ]
    if missing_sources:
        vetoes.append(f"missing_source_ids_on_success:{len(missing_sources)}")

    metrics = {
        "live_pair_count": live_pair_count,
        "live_success_count": live_success_count,
        "live_reviewed_count": live_reviewed_count,
        "distinct_passages": len(passages),
        "modules": sorted(modules),
        "passages_with_both_modules": both_module_passages,
    }

    if live_reviewed_count == 0:
        status = STATUS_INSUFFICIENT
    elif vetoes:
        status = STATUS_NOT_READY
    elif unmet:
        # Distinguish sparse data vs partial progress.
        if live_reviewed_count < max(2, criteria.min_live_ab_pairs // 2):
            status = STATUS_INSUFFICIENT
        else:
            status = STATUS_NEEDS_MORE
    else:
        status = STATUS_READY

    return {
        "status": status,
        "unmet_criteria": unmet,
        "veto_reasons": vetoes,
        "metrics": metrics,
        "ready": status == STATUS_READY,
    }


def main_review_summary(argv: list[str] | None = None) -> int:
    import json
    import sys

    args = argv if argv is not None else sys.argv[1:]
    live_only = False
    module = None
    database = None
    i = 0
    while i < len(args):
        if args[i] == "--live-only":
            live_only = True
            i += 1
            continue
        if args[i] == "--module" and i + 1 < len(args):
            module = args[i + 1]
            i += 2
            continue
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        i += 1
    report = build_review_summary(
        database_path=database,
        live_only=live_only,
        module=module,
    )
    print(json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_CRITERIA",
    "STATUS_INSUFFICIENT",
    "STATUS_NEEDS_MORE",
    "STATUS_NOT_READY",
    "STATUS_READY",
    "StagingReadinessCriteria",
    "build_review_summary",
    "evaluate_staging_readiness",
    "has_human_overall_review",
    "is_live_compare_artifact",
    "main_review_summary",
    "_load_all_artifacts",
]
