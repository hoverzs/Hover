"""Read-only CLI reports for KB shadow audit store (Phase 5B)."""

from __future__ import annotations

import json
import statistics
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.shadow_audit import (
    DEFAULT_AUDIT_DB_PATH,
    classify_source_mix,
    load_shadow_runs,
)


def _avg(values: list[float | int]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _minmax(values: list[float | int]) -> dict[str, float | int]:
    if not values:
        return {"min": 0, "max": 0}
    return {"min": min(values), "max": max(values)}


def build_shadow_report(
    *,
    database_path: str | None = None,
    passage: str | None = None,
    module: str | None = None,
) -> dict[str, Any]:
    canonical = None
    if passage:
        try:
            canonical = CanonicalReference.parse(passage).canonical_string()
        except CanonicalReferenceError as exc:
            raise ValueError(f"Invalid passage filter: {passage!r} ({exc})") from exc

    runs = load_shadow_runs(
        database_path=database_path or DEFAULT_AUDIT_DB_PATH,
        canonical_passage=canonical,
        module=module,
    )
    retrieval = [int(r.get("retrieval_ms") or 0) for r in runs]
    context_build = [int(r.get("context_build_ms") or 0) for r in runs]
    tokens = [int(r.get("context_tokens") or 0) for r in runs]
    evidence = [int(r.get("evidence_count") or 0) for r in runs]
    entities = [int(r.get("entity_count") or 0) for r in runs]

    by_passage: dict[str, int] = {}
    by_module: dict[str, int] = {}
    by_status: dict[str, int] = {}
    source_mix_totals = {
        "linguistic": 0,
        "study_notes": 0,
        "dictionary": 0,
        "acai": 0,
        "places_background": 0,
        "other": 0,
    }
    for run in runs:
        passage_key = str(run.get("canonical_passage") or "")
        module_key = str(run.get("module") or "")
        status_key = str(run.get("status") or "")
        by_passage[passage_key] = by_passage.get(passage_key, 0) + 1
        by_module[module_key] = by_module.get(module_key, 0) + 1
        by_status[status_key] = by_status.get(status_key, 0) + 1
        mix = classify_source_mix(list(run.get("source_ids") or []))
        for key, value in mix.items():
            source_mix_totals[key] = source_mix_totals.get(key, 0) + value

    warning_runs = sum(1 for run in runs if int(run.get("warning_count") or 0) > 0)
    error_runs = sum(1 for run in runs if str(run.get("status") or "") == "error")

    return {
        "database_path": str(database_path or DEFAULT_AUDIT_DB_PATH),
        "filters": {"passage": canonical, "module": module},
        "run_count": len(runs),
        "by_passage": dict(sorted(by_passage.items())),
        "by_module": dict(sorted(by_module.items())),
        "by_status": dict(sorted(by_status.items())),
        "retrieval_ms": {
            "avg": round(_avg(retrieval), 2),
            **_minmax(retrieval),
        },
        "context_build_ms": {
            "avg": round(_avg(context_build), 2),
            **_minmax(context_build),
        },
        "context_tokens": {
            "avg": round(_avg(tokens), 2),
            **_minmax(tokens),
        },
        "evidence_count": {
            "avg": round(_avg(evidence), 2),
            **_minmax(evidence),
        },
        "entity_count": {
            "avg": round(_avg(entities), 2),
            **_minmax(entities),
        },
        "source_mix": source_mix_totals,
        "warning_run_ratio": round(warning_runs / len(runs), 4) if runs else 0.0,
        "error_run_ratio": round(error_runs / len(runs), 4) if runs else 0.0,
    }


def build_shadow_compare(
    passage: str,
    *,
    database_path: str | None = None,
) -> dict[str, Any]:
    try:
        canonical = CanonicalReference.parse(passage).canonical_string()
    except CanonicalReferenceError as exc:
        raise ValueError(f"Invalid passage: {passage!r} ({exc})") from exc

    runs = load_shadow_runs(
        database_path=database_path or DEFAULT_AUDIT_DB_PATH,
        canonical_passage=canonical,
    )
    modules = ("exegesis", "historical_context")
    comparison: dict[str, Any] = {"passage": canonical, "modules": {}}
    for module in modules:
        module_runs = [run for run in runs if run.get("module") == module]
        if not module_runs:
            comparison["modules"][module] = {"run_count": 0}
            continue
        latest = module_runs[-1]
        comparison["modules"][module] = {
            "run_count": len(module_runs),
            "latest": {
                "status": latest.get("status"),
                "production_prompt_chars": latest.get("production_prompt_chars"),
                "production_output_chars": latest.get("production_output_chars"),
                "context_tokens": latest.get("context_tokens"),
                "source_ids": latest.get("source_ids"),
                "source_mix": classify_source_mix(list(latest.get("source_ids") or [])),
                "evidence_count": latest.get("evidence_count"),
                "entity_count": latest.get("entity_count"),
                "selected_item_count": latest.get("selected_item_count"),
                "retrieval_ms": latest.get("retrieval_ms"),
                "context_build_ms": latest.get("context_build_ms"),
                "generation_ms": latest.get("generation_ms"),
                "latency_overhead_ms": int(latest.get("retrieval_ms") or 0)
                + int(latest.get("context_build_ms") or 0),
                "warning_count": latest.get("warning_count"),
                "evidence_build_id": latest.get("evidence_build_id"),
            },
            "averages": {
                "context_tokens": round(
                    _avg([int(r.get("context_tokens") or 0) for r in module_runs]),
                    2,
                ),
                "retrieval_ms": round(
                    _avg([int(r.get("retrieval_ms") or 0) for r in module_runs]),
                    2,
                ),
                "context_build_ms": round(
                    _avg([int(r.get("context_build_ms") or 0) for r in module_runs]),
                    2,
                ),
            },
        }
    return comparison


def main_report(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    passage = None
    module = None
    database = None
    i = 0
    while i < len(args):
        if args[i] == "--passage" and i + 1 < len(args):
            passage = args[i + 1]
            i += 2
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
    try:
        report = build_shadow_report(database_path=database, passage=passage, module=module)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


def main_compare(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            'Usage: python -m textus_kb shadow-compare "<reference>" [--database PATH]',
            file=sys.stderr,
        )
        return 2
    passage = args[0]
    database = None
    i = 1
    while i < len(args):
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        i += 1
    try:
        report = build_shadow_compare(passage, database_path=database)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True))
    return 0
