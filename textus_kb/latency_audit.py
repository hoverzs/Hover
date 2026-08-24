"""Latency audit for grounded preparation (Phase 5F)."""

from __future__ import annotations

import json
import time
from typing import Any

from textus_kb.kb_cache import cache_stats, clear_kb_cache, composition_cache_note
from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB
from textus_kb.shadow import MODULE_TO_PROFILE

BENCHMARK_PASSAGES = (
    "John.4.1-42",
    "Luke.10.25-37",
    "Acts.2.1-13",
    "Rom.8.28-30",
)


def measure_grounded_prep_latency(
    passage: str,
    module: str,
    *,
    use_cache: bool = True,
    production_prompt: str = DRY_RUN_PRODUCTION_STUB,
) -> dict[str, Any]:
    from textus_kb.grounded_generation import prepare_grounded_provider_prompt

    t0 = time.perf_counter()
    prep = prepare_grounded_provider_prompt(
        production_prompt=production_prompt,
        passage=passage,
        module=module,
        grounded_enabled=True,
        use_cache=use_cache,
    )
    wall = int((time.perf_counter() - t0) * 1000)
    return {
        "passage": prep.canonical_passage or passage,
        "module": module,
        "status": prep.status,
        "wall_ms": wall,
        "retrieval_ms": prep.retrieval_ms,
        "context_build_ms": prep.context_build_ms,
        "composition_ms": prep.composition_ms,
        "cache": dict(getattr(prep, "cache_info", {}) or {}),
        "breakdown_note": (
            "Study Notes / Dictionary / ACAI / entity expansion timings are inside "
            "retrieval_ms (single retrieve() call). Separate adapter timers are a "
            "future instrumentation option; not required for Phase 5F mitigation."
        ),
    }


def run_latency_benchmark(
    *,
    passages: tuple[str, ...] = BENCHMARK_PASSAGES,
    modules: tuple[str, ...] = ("exegesis", "historical_context"),
) -> dict[str, Any]:
    clear_kb_cache()
    cold: list[dict[str, Any]] = []
    for passage in passages:
        for module in modules:
            if module not in MODULE_TO_PROFILE:
                continue
            cold.append(measure_grounded_prep_latency(passage, module, use_cache=True))

    warm: list[dict[str, Any]] = []
    for passage in passages:
        for module in modules:
            warm.append(measure_grounded_prep_latency(passage, module, use_cache=True))

    def _avg(rows: list[dict[str, Any]], key: str) -> float:
        vals = [float(r.get(key) or 0) for r in rows]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "cold": {
            "rows": cold,
            "avg_wall_ms": _avg(cold, "wall_ms"),
            "avg_retrieval_ms": _avg(cold, "retrieval_ms"),
            "avg_context_build_ms": _avg(cold, "context_build_ms"),
            "avg_composition_ms": _avg(cold, "composition_ms"),
        },
        "warm_cached": {
            "rows": warm,
            "avg_wall_ms": _avg(warm, "wall_ms"),
            "avg_retrieval_ms": _avg(warm, "retrieval_ms"),
            "avg_context_build_ms": _avg(warm, "context_build_ms"),
            "avg_composition_ms": _avg(warm, "composition_ms"),
        },
        "cache_stats": cache_stats(),
        "composition_cache_note": composition_cache_note(),
        "async_decision": (
            "Async/background grounded prep deferred: in-process cache is the first "
            "mitigation. Revisit async only if warm-path still exceeds product SLA."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    # Optional single passage/module
    passage = None
    module = "exegesis"
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
        i += 1
    if passage:
        clear_kb_cache()
        cold = measure_grounded_prep_latency(passage, module, use_cache=True)
        warm = measure_grounded_prep_latency(passage, module, use_cache=True)
        print(json.dumps({"cold": cold, "warm": warm, "cache_stats": cache_stats()}, indent=2))
        return 0
    report = run_latency_benchmark()
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


__all__ = [
    "BENCHMARK_PASSAGES",
    "main",
    "measure_grounded_prep_latency",
    "run_latency_benchmark",
]
