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
        status = preview.budget_status if preview.budget_ok else "exceeded"
        if not preview.budget_ok:
            all_ok = False
        rows.append(
            {
                "passage": export.passage_canonical,
                "module": export.module,
                "production_tok": preview.original_prompt_estimated_tokens,
                "kb_tok": preview.kb_context_estimated_tokens,
                "overhead_tok": preview.composition_overhead_estimated_tokens,
                "total_grounded_tok": preview.composed_prompt_estimated_tokens,
                "kb_max": preview.kb_context_max_tokens,
                "total_max": preview.total_grounded_max_tokens,
                "kb_trim_applied": preview.kb_trim_applied,
                "budget_status": status,
                "budget_ok": preview.budget_ok,
                "production_intact": export.production_prompt in (preview.composed_prompt or ""),
            }
        )

    print("passage | module | production tok | KB tok | total grounded tok | budget status")
    print("-" * 90)
    for r in rows:
        print(
            f"{r['passage']} | {r['module']} | {r['production_tok']} | "
            f"{r['kb_tok']} | {r['total_grounded_tok']} | {r['budget_status']}"
        )
    out = Path("data/generated/kb_grounded_compare/phase5g_budget_dry_run.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"all_ok": all_ok, "rows": rows}, indent=2), encoding="utf-8")
    print(f"\nall_ok={all_ok} wrote {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
