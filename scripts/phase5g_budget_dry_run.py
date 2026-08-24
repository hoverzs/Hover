"""Dry-run budget check for the 8 Phase 5G benchmark pairs (no provider calls)."""

from __future__ import annotations

import json
from pathlib import Path

from textus_kb.production_prompt_export import build_production_section_prompt
from textus_kb.prompt_composer import compose_grounded_prompt
from textus_kb.review_campaign import required_campaign_pairs
from textus_kb.shadow import MODULE_TO_PROFILE


def main() -> int:
    from textus_kb.context_builder import build_context_from_evidence
    from textus_kb.retrieval import retrieve

    rows: list[dict] = []
    all_ok = True
    print(
        "passage | module | prod tok | KB tok | overhead | total | KB% | "
        "target | max | status"
    )
    print("-" * 110)
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
        row = {
            "passage": export.passage_canonical,
            "module": export.module,
            "production_tok": preview.original_prompt_estimated_tokens,
            "kb_tok": preview.kb_context_estimated_tokens,
            "overhead_tok": preview.composition_overhead_estimated_tokens,
            "total_grounded_tok": preview.composed_prompt_estimated_tokens,
            "kb_share_percent": diag.get("kb_share_of_grounded_percent"),
            "target_kb": preview.kb_context_target_tokens,
            "max_kb": preview.kb_context_max_tokens,
            "total_max": preview.total_grounded_max_tokens,
            "kb_trim_applied": preview.kb_trim_applied,
            "budget_status": status,
            "budget_ok": preview.budget_ok,
            "production_intact": export.production_prompt in (preview.composed_prompt or ""),
            "candidate_evidence_count": sel.get("candidate_evidence_count"),
            "selected_evidence_count": sel.get("selected_evidence_count"),
            "dropped_by_target": sel.get("dropped_by_target", sel.get("dropped_target")),
            "dropped_by_source_budget": sel.get("dropped_by_source_budget"),
            "source_diversity": sel.get("source_diversity"),
        }
        rows.append(row)
        print(
            f"{row['passage']} | {row['module']} | {row['production_tok']} | "
            f"{row['kb_tok']} | {row['overhead_tok']} | {row['total_grounded_tok']} | "
            f"{row['kb_share_percent']}% | {row['target_kb']} | {row['max_kb']} | "
            f"{row['budget_status']}"
        )

    out = Path("data/generated/kb_grounded_compare/phase5g_budget_dry_run.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"all_ok": all_ok, "rows": rows}, indent=2), encoding="utf-8")
    print(f"\nall_ok={all_ok} wrote {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
