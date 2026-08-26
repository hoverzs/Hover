"""Live human A/B review campaign tracking (Phase 5G).

Required first campaign: 4 passages × 2 modules = 8 live A/B pairs.
Mock runs never count toward campaign completion or staging readiness evidence.
"""

from __future__ import annotations

import json
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.compare_store import DEFAULT_COMPARE_DB_PATH
from textus_kb.grounded_compare import BENCHMARK_MODULES, BENCHMARK_PASSAGES
from textus_kb.staging_readiness import (
    DEFAULT_CRITERIA,
    build_review_summary,
    evaluate_staging_readiness,
    has_human_overall_review,
    is_live_compare_artifact,
    _load_all_artifacts,
)

REQUIRED_PAIR_COUNT = 8

PAIR_STATUS_MISSING = "MISSING"
PAIR_STATUS_MOCK = "MOCK_ONLY"
PAIR_STATUS_FAILED = "FAILED"
PAIR_STATUS_GENERATED_UNREVIEWED = "GENERATED / UNREVIEWED"
PAIR_STATUS_REVIEWED = "REVIEWED"


def _canonical_passage(passage: str) -> str:
    try:
        return CanonicalReference.parse(passage).canonical_string()
    except CanonicalReferenceError:
        return str(passage or "").strip()


def required_campaign_pairs() -> list[tuple[str, str]]:
    return [(p, m) for p in BENCHMARK_PASSAGES for m in BENCHMARK_MODULES]


def classify_run_completeness(artifact: dict[str, Any]) -> str:
    """Return completeness class for a single compare artifact."""
    if not is_live_compare_artifact(artifact):
        return "mock"
    status = str(artifact.get("grounded_status") or "")
    prod_ok = bool(str(artifact.get("production_output") or "").strip())
    if not prod_ok or status == "error":
        return "failed_generation"
    if not has_human_overall_review(artifact):
        return "live_generated_unreviewed"
    return "live_reviewed"


def is_readiness_evidence(artifact: dict[str, Any]) -> bool:
    """Only live + successfully generated + human reviewed counts for readiness."""
    return classify_run_completeness(artifact) == "live_reviewed"


def _artifact_sort_key(artifact: dict[str, Any]) -> str:
    return str(artifact.get("timestamp") or "") + "|" + str(artifact.get("run_id") or "")


def latest_artifacts_by_pair(
    artifacts: list[dict[str, Any]],
    *,
    live_only: bool = True,
) -> dict[tuple[str, str], dict[str, Any]]:
    """One artifact per (passage, module) — latest timestamp wins (no double-count)."""
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for art in artifacts:
        if live_only and not is_live_compare_artifact(art):
            continue
        passage = _canonical_passage(str(art.get("passage") or ""))
        module = str(art.get("module") or "")
        if not passage or not module:
            continue
        key = (passage, module)
        prev = best.get(key)
        if prev is None or _artifact_sort_key(art) >= _artifact_sort_key(prev):
            best[key] = art
    return best


def _format_matrix(pairs: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    matrix: dict[str, dict[str, str]] = {}
    for item in pairs:
        passage = str(item["passage"])
        module = str(item["module"])
        matrix.setdefault(passage, {})[module] = str(item["status"])
    return matrix


def build_campaign_status(*, database_path: str | None = None) -> dict[str, Any]:
    artifacts = _load_all_artifacts(database_path=database_path)
    by_completeness: dict[str, int] = {
        "mock": 0,
        "failed_generation": 0,
        "live_generated_unreviewed": 0,
        "live_reviewed": 0,
    }
    for art in artifacts:
        key = classify_run_completeness(art)
        by_completeness[key] = by_completeness.get(key, 0) + 1

    live_artifacts = [a for a in artifacts if is_live_compare_artifact(a)]
    latest_live = latest_artifacts_by_pair(live_artifacts, live_only=True)
    latest_all = latest_artifacts_by_pair(artifacts, live_only=False)

    pairs: list[dict[str, Any]] = []
    generated_live = 0
    reviewed_live = 0
    failed_pairs = 0
    missing_pairs: list[str] = []
    provider_calls_live = 0

    for passage, module in required_campaign_pairs():
        art = latest_live.get((passage, module))
        if art is None:
            mock_candidate = latest_all.get((passage, module))
            if mock_candidate and not is_live_compare_artifact(mock_candidate):
                status = PAIR_STATUS_MOCK
                run_id = str(mock_candidate.get("run_id") or "")
            else:
                status = PAIR_STATUS_MISSING
                run_id = ""
                missing_pairs.append(f"{passage}/{module}")
        else:
            completeness = classify_run_completeness(art)
            run_id = str(art.get("run_id") or "")
            provider_calls_live += int(art.get("provider_call_count") or 0)
            if completeness == "failed_generation":
                status = PAIR_STATUS_FAILED
                failed_pairs += 1
            elif completeness == "live_reviewed":
                status = PAIR_STATUS_REVIEWED
                generated_live += 1
                reviewed_live += 1
            else:
                status = PAIR_STATUS_GENERATED_UNREVIEWED
                generated_live += 1
        pairs.append(
            {
                "passage": passage,
                "module": module,
                "status": status,
                "run_id": run_id,
            }
        )

    readiness = evaluate_staging_readiness(
        live_artifacts=list(latest_live.values()),
        criteria=DEFAULT_CRITERIA,
    )
    summary = build_review_summary(database_path=database_path, live_only=True)

    return {
        "required_pairs": REQUIRED_PAIR_COUNT,
        "generated_live_pairs": generated_live,
        "reviewed_live_pairs": reviewed_live,
        "failed_pairs": failed_pairs,
        "missing_pairs": missing_pairs,
        "mock_run_count": by_completeness.get("mock", 0),
        "completeness_counts": by_completeness,
        "live_provider_call_count": provider_calls_live,
        "estimated_calls_per_successful_pair": 2,
        "pairs": pairs,
        "matrix": _format_matrix(pairs),
        "staging_readiness": readiness,
        "live_preference_snapshot": summary.get("preferences"),
        "database_path": str(database_path or DEFAULT_COMPARE_DB_PATH),
        "note": (
            "Only live + successfully generated + human-reviewed pairs count as "
            "staging readiness evidence. Mock runs never count. "
            "Readiness never enables grounded flags."
        ),
    }


def format_campaign_status_text(report: dict[str, Any]) -> str:
    lines = [
        "================================",
        "LIVE REVIEW CAMPAIGN STATUS",
        "================================",
        f"required_pairs: {report.get('required_pairs')}",
        f"generated_live_pairs: {report.get('generated_live_pairs')}",
        f"reviewed_live_pairs: {report.get('reviewed_live_pairs')}",
        f"failed_pairs: {report.get('failed_pairs')}",
        f"mock_run_count: {report.get('mock_run_count')}",
        f"live_provider_call_count: {report.get('live_provider_call_count')}",
        f"readiness: {(report.get('staging_readiness') or {}).get('status')}",
        "",
    ]
    matrix = report.get("matrix") or {}
    for passage in BENCHMARK_PASSAGES:
        lines.append(passage)
        mods = matrix.get(passage) or {}
        for module in BENCHMARK_MODULES:
            status = mods.get(module, PAIR_STATUS_MISSING)
            lines.append(f"  {module:<22} {status}")
        lines.append("")
    missing = report.get("missing_pairs") or []
    if missing:
        lines.append("missing:")
        for item in missing:
            lines.append(f"  - {item}")
        lines.append("")
    readiness = report.get("staging_readiness") or {}
    unmet = readiness.get("unmet_criteria") or []
    vetoes = readiness.get("veto_reasons") or []
    if unmet:
        lines.append("unmet_criteria:")
        for item in unmet:
            lines.append(f"  - {item}")
    if vetoes:
        lines.append("veto_reasons:")
        for item in vetoes:
            lines.append(f"  - {item}")
    lines.append("")
    lines.append(str(report.get("note") or ""))
    return "\n".join(lines).rstrip() + "\n"


def campaign_manual_commands(*, prompt_file: str | None = None) -> list[str]:
    """Reproducible live commands — print only; never auto-execute."""
    cmds: list[str] = []
    for passage, module in required_campaign_pairs():
        if prompt_file:
            cmds.append(
                "python -m textus_kb grounded-compare "
                f'"{passage}" --module {module} --live --blind '
                f'--prompt-file "{prompt_file}"'
            )
        else:
            cmds.append(
                "python -m textus_kb grounded-compare "
                f'"{passage}" --module {module} --live --blind --from-production'
            )
    return cmds


def main_campaign_status(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    database = None
    as_json = False
    i = 0
    while i < len(args):
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        if args[i] == "--json":
            as_json = True
            i += 1
            continue
        i += 1
    report = build_campaign_status(database_path=database)
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True))
    else:
        print(format_campaign_status_text(report))
    return 0


def main_campaign_commands(argv: list[str] | None = None) -> int:
    """Print reproducible live commands without executing provider calls."""
    args = argv if argv is not None else []
    prompt_file = None
    i = 0
    while i < len(args):
        if args[i] == "--prompt-file" and i + 1 < len(args):
            prompt_file = args[i + 1]
            i += 2
            continue
        i += 1
    print("# Phase 5G live review campaign — run ONE pair at a time (manual).")
    print("# Prefer --from-production (real SECTION_PROMPTS) over hand-exported files.")
    print("# Do NOT batch-automate these if you want cost control.")
    print("set TEXTUS_KB_COMPARE_STORE_ENABLED=true")
    print()
    for cmd in campaign_manual_commands(prompt_file=prompt_file):
        print(cmd)
    print()
    print("# After each generation:")
    print("#   python -m textus_kb review-show <run_id>")
    print("#   python -m textus_kb review-rate <run_id> --overall ... --factual ...")
    print("#   python -m textus_kb review-sources <run_id>")
    print("#   python -m textus_kb review-show <run_id> --reveal")
    print("# Final:")
    print("#   python -m textus_kb review-campaign-status")
    print("#   python -m textus_kb review-summary --live-only")
    return 0


__all__ = [
    "PAIR_STATUS_FAILED",
    "PAIR_STATUS_GENERATED_UNREVIEWED",
    "PAIR_STATUS_MISSING",
    "PAIR_STATUS_MOCK",
    "PAIR_STATUS_REVIEWED",
    "REQUIRED_PAIR_COUNT",
    "build_campaign_status",
    "campaign_manual_commands",
    "classify_run_completeness",
    "format_campaign_status_text",
    "is_readiness_evidence",
    "latest_artifacts_by_pair",
    "main_campaign_commands",
    "main_campaign_status",
    "required_campaign_pairs",
]
