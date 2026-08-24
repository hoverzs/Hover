"""Dry-run budget check for the 8 Phase 5G benchmark pairs (no provider calls)."""

from __future__ import annotations

import json
from pathlib import Path

from textus_kb.production_prompt_export import build_production_section_prompt
from textus_kb.prompt_composer import compose_grounded_prompt
from textus_kb.review_campaign import required_campaign_pairs
from textus_kb.shadow import MODULE_TO_PROFILE

# If actual KB is this close to the hard max, selection is spending ceiling
# instead of stopping at coverage — do not start live until fixed.
HARD_MAX_ALERT_RATIO = 0.80

COLUMNS = (
    "passage",
    "module",
    "production_prompt_tokens",
    "candidate_evidence_count",
    "selected_evidence_count",
    "target_kb_context_tokens",
    "actual_kb_context_tokens",
    "max_kb_context_tokens",
    "unused_target_kb_tokens",
    "unused_max_kb_tokens",
    "grounded_instruction_overhead",
    "total_grounded_tokens",
    "kb_percentage_of_total",
    "budget_status",
)


def main() -> int:
    from textus_kb.context_builder import build_context_from_evidence
    from textus_kb.retrieval import retrieve

    rows: list[dict] = []
    all_ok = True
    near_max_alerts: list[str] = []
    print(" | ".join(COLUMNS))
    print("-" * 160)
    for passage, module in required_campaign_pairs():
        export = build_production_section_prompt(passage, module=module)
        evidence = retrieve(export.passage_canonical)
        profile = MODULE_TO_PROFILE[export.module]
        context = build_context_from_evidence(evidence, profile)
        preview = compose_grounded_prompt(
            production_prompt=export.production_prompt,
            canonical_passage=export.passage_canonical,
            module=export.module,
            context_packet=context,
        )
        diag = preview.budget_diagnostics()
        status = preview.budget_status if preview.budget_ok else "exceeded"
        if not preview.budget_ok:
            all_ok = False
        sel = diag.get("selection_diagnostics") or {}
        actual_kb = int(diag.get("actual_kb_context_tokens") or preview.kb_context_estimated_tokens)
        max_kb = int(diag.get("max_kb_context_tokens") or preview.kb_context_max_tokens)
        near_hard_max = bool(max_kb and actual_kb >= int(max_kb * HARD_MAX_ALERT_RATIO))
        if near_hard_max:
            all_ok = False
            near_max_alerts.append(f"{export.passage_canonical}/{export.module}")
        row = {
            "passage": export.passage_canonical,
            "module": export.module,
            "production_prompt_tokens": preview.original_prompt_estimated_tokens,
            "candidate_evidence_count": sel.get("candidate_evidence_count")
            or sel.get("candidates"),
            "selected_evidence_count": sel.get("selected_evidence_count")
            or sel.get("selected"),
            "target_kb_context_tokens": preview.kb_context_target_tokens,
            "actual_kb_context_tokens": actual_kb,
            "max_kb_context_tokens": max_kb,
            "unused_target_kb_tokens": diag.get("unused_target_kb_tokens"),
            "unused_max_kb_tokens": diag.get("unused_max_kb_tokens"),
            "grounded_instruction_overhead": preview.composition_overhead_estimated_tokens,
            "total_grounded_tokens": preview.composed_prompt_estimated_tokens,
            "kb_percentage_of_total": diag.get("kb_percentage_of_total"),
            "budget_status": status,
            "budget_ok": preview.budget_ok,
            "production_intact": export.production_prompt in (preview.composed_prompt or ""),
            "near_hard_max": near_hard_max,
            "dropped_by_target": sel.get("dropped_by_target", sel.get("dropped_target")),
            "dropped_by_source_budget": sel.get("dropped_by_source_budget"),
            "source_diversity": sel.get("source_diversity"),
            "kb_target_utilization_percent": diag.get("kb_target_utilization_percent"),
            "kb_max_utilization_percent": diag.get("kb_max_utilization_percent"),
        }
        rows.append(row)
        print(
            f"{row['passage']} | {row['module']} | {row['production_prompt_tokens']} | "
            f"{row['candidate_evidence_count']} | {row['selected_evidence_count']} | "
            f"{row['target_kb_context_tokens']} | {row['actual_kb_context_tokens']} | "
            f"{row['max_kb_context_tokens']} | {row['unused_target_kb_tokens']} | "
            f"{row['unused_max_kb_tokens']} | {row['grounded_instruction_overhead']} | "
            f"{row['total_grounded_tokens']} | {row['kb_percentage_of_total']}% | "
            f"{row['budget_status']}"
        )

    out = Path("data/generated/kb_grounded_compare/phase5g_budget_dry_run.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "all_ok": all_ok,
        "near_hard_max_pairs": near_max_alerts,
        "hard_max_alert_ratio": HARD_MAX_ALERT_RATIO,
        "live_benchmark_allowed": all_ok and not near_max_alerts,
        "rows": rows,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nall_ok={all_ok} live_benchmark_allowed={payload['live_benchmark_allowed']}")
    if near_max_alerts:
        print(
            "NEAR HARD MAX — do not start live benchmark; fix selection first: "
            + ", ".join(near_max_alerts)
        )
    print(f"wrote {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
