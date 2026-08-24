"""Staging readiness criteria and human-review summary (Phase 5F/5G).

Deterministic rules over live A/B human reviews only. No LLM-as-judge.
Readiness is a report — it never flips runtime grounded flags.

Preference thresholds are mapping-aware: human A/B labels are translated via
persisted ``blind_mapping`` to production/grounded before ratios are computed.
Blind reviewer-facing reports remain mapping-free unless explicitly revealed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from textus_kb.compare_store import DEFAULT_COMPARE_DB_PATH, list_compare_runs, load_compare_run

STATUS_INSUFFICIENT = "insufficient_human_review_data"
STATUS_NEEDS_MORE = "needs_more_review"
STATUS_NOT_READY = "not_ready"
STATUS_READY = "ready_for_limited_staging"

_VALID_MAPPING_SIDES = frozenset({"production", "grounded"})


@dataclass(frozen=True)
class StagingReadinessCriteria:
    """Initial staging thresholds — not a scientific quality benchmark."""

    min_live_ab_pairs: int = 8
    min_distinct_passages: int = 4
    require_exegesis: bool = True
    require_historical_context: bool = True
    require_overall_review: bool = True
    min_passages_with_both_modules: int = 2
    # Overall: grounded preferred or equal (mapping-aware). Field name kept for compat.
    min_overall_b_or_equal_ratio: float = 0.75
    # Factual: share where grounded is strictly worse than production (mapping-aware).
    max_factual_b_worse_ratio: float = 0.25
    # Hallucination: share where grounded risk is elevated (grounded_only or both).
    max_hallucination_b_elevated_ratio: float = 0.20
    max_grounded_error_rate: float = 0.25


DEFAULT_CRITERIA = StagingReadinessCriteria()


def resolve_blind_mapping(
    artifact: dict[str, Any],
) -> tuple[dict[str, str] | None, str | None]:
    """Return ({A,B}->production|grounded, None) or (None, reason) if unusable.

    Fail closed: never invent B=grounded when mapping is missing/ambiguous.
    """
    raw = artifact.get("blind_mapping")
    if not isinstance(raw, dict) or not raw:
        return None, "missing_blind_mapping"
    side_a = str(raw.get("A") or "").strip()
    side_b = str(raw.get("B") or "").strip()
    if side_a not in _VALID_MAPPING_SIDES or side_b not in _VALID_MAPPING_SIDES:
        return None, "ambiguous_blind_mapping"
    if side_a == side_b or {side_a, side_b} != _VALID_MAPPING_SIDES:
        return None, "ambiguous_blind_mapping"
    return {"A": side_a, "B": side_b}, None


def map_ab_preference_to_system(
    preference: str,
    mapping: dict[str, str],
) -> str:
    """Translate human A/B/equal/unclear into grounded|production|equal|unclear|other."""
    pref = str(preference or "").strip()
    if pref == "equal":
        return "equal"
    if pref == "unclear":
        return "unclear"
    if pref in ("A", "B"):
        return mapping[pref]
    return "other"


def map_hallucination_risk_to_system(
    risk: str,
    mapping: dict[str, str],
) -> str:
    """Translate hallucination A/B/both/neither/unclear via mapping.

    Returns: grounded_only | production_only | both | neither | unclear | other
    """
    value = str(risk or "").strip()
    if value == "both":
        return "both"
    if value == "neither":
        return "neither"
    if value == "unclear":
        return "unclear"
    if value in ("A", "B"):
        side = mapping[value]
        return f"{side}_only"
    return "other"


def is_grounded_hallucination_elevated(system_risk: str) -> bool:
    """Grounded elevated = grounded_only or both. unclear is not elevated (legacy)."""
    return system_risk in {"grounded_only", "both"}


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
            "Readiness never enables TEXTUS_KB_GROUNDED_ENABLED. "
            "Preference thresholds are mapping-aware via persisted blind_mapping."
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

    mapping_aware_metrics: dict[str, float] = {}

    # Preference ratios on live reviewed successful pairs only (mapping-aware).
    if live_reviewed_count:
        mapping_errors: list[str] = []
        overall_system: list[str] = []
        factual_system: list[str] = []
        hallu_system: list[str] = []

        for art in live_reviewed:
            mapping, map_err = resolve_blind_mapping(art)
            if mapping is None:
                mapping_errors.append(map_err or "ambiguous_blind_mapping")
                continue
            review = art.get("review") if isinstance(art.get("review"), dict) else {}
            overall_system.append(
                map_ab_preference_to_system(
                    str(review.get("overall_preference") or ""), mapping
                )
            )
            factual_raw = str(review.get("factual_accuracy_preference") or "").strip()
            if factual_raw:
                factual_system.append(map_ab_preference_to_system(factual_raw, mapping))
            hallu_raw = str(review.get("hallucination_risk") or "").strip()
            if hallu_raw:
                hallu_system.append(
                    map_hallucination_risk_to_system(hallu_raw, mapping)
                )

        if mapping_errors:
            # Fail closed: never invent B=grounded for missing/ambiguous mapping.
            vetoes.append(
                f"missing_or_ambiguous_blind_mapping:{len(mapping_errors)}"
            )
        else:
            grounded_or_equal = sum(
                1 for v in overall_system if v in {"grounded", "equal"}
            )
            overall_ratio = grounded_or_equal / live_reviewed_count
            mapping_aware_metrics["grounded_preferred_or_equal_ratio"] = round(
                overall_ratio, 3
            )
            if overall_ratio < criteria.min_overall_b_or_equal_ratio:
                unmet.append(
                    f"grounded_preferred_or_equal_ratio {overall_ratio:.3f} < "
                    f"{criteria.min_overall_b_or_equal_ratio}"
                )

            if factual_system:
                # Human preferred production => grounded is strictly worse.
                grounded_worse = sum(1 for v in factual_system if v == "production")
                factual_worse_ratio = grounded_worse / len(factual_system)
                mapping_aware_metrics["factual_grounded_worse_ratio"] = round(
                    factual_worse_ratio, 3
                )
                if factual_worse_ratio > criteria.max_factual_b_worse_ratio:
                    vetoes.append(
                        f"factual_grounded_worse_ratio {factual_worse_ratio:.3f} > "
                        f"{criteria.max_factual_b_worse_ratio}"
                    )

            if hallu_system:
                elevated = sum(
                    1 for v in hallu_system if is_grounded_hallucination_elevated(v)
                )
                elevated_ratio = elevated / len(hallu_system)
                mapping_aware_metrics["hallucination_grounded_elevated_ratio"] = round(
                    elevated_ratio, 3
                )
                if elevated_ratio > criteria.max_hallucination_b_elevated_ratio:
                    vetoes.append(
                        f"hallucination_grounded_elevated_ratio {elevated_ratio:.3f} > "
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
    missing_sources = [a for a in live_success if not (a.get("source_ids") or [])]
    if missing_sources:
        vetoes.append(f"missing_source_ids_on_success:{len(missing_sources)}")

    metrics: dict[str, Any] = {
        "live_pair_count": live_pair_count,
        "live_success_count": live_success_count,
        "live_reviewed_count": live_reviewed_count,
        "distinct_passages": len(passages),
        "modules": sorted(modules),
        "passages_with_both_modules": both_module_passages,
    }
    metrics.update(mapping_aware_metrics)

    if live_reviewed_count == 0:
        status = STATUS_INSUFFICIENT
    elif vetoes:
        status = STATUS_NOT_READY
    elif unmet:
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
    "is_grounded_hallucination_elevated",
    "is_live_compare_artifact",
    "main_review_summary",
    "map_ab_preference_to_system",
    "map_hallucination_risk_to_system",
    "resolve_blind_mapping",
    "_load_all_artifacts",
]
