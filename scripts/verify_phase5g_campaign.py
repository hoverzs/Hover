"""One-off Phase 5G post-campaign technical verification (dev)."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("TEXTUS_KB_COMPARE_STORE_ENABLED", "true")

from textus_kb.compare_store import load_compare_run
from textus_kb.review_campaign import build_campaign_status, classify_run_completeness

ROOT = Path("data/generated/kb_grounded_compare")
idx = json.loads((ROOT / "phase5g_review_index.json").read_text(encoding="utf-8"))
md = (ROOT / "PHASE5G_HUMAN_REVIEW.md").read_text(encoding="utf-8")
guide = (ROOT / "PHASE5G_REVIEW_GUIDE.md").read_text(encoding="utf-8")

issues: list[str] = []
run_ids: set[str] = set()
total_calls = 0

for p in idx["pairs"]:
    rid = str(p["run_id"])
    if rid in run_ids:
        issues.append(f"duplicate_run_id:{rid}")
    run_ids.add(rid)
    art = load_compare_run(rid)
    if art is None:
        issues.append(f"missing_store:{rid}")
        continue
    cls = classify_run_completeness(art)
    if cls != "live_generated_unreviewed":
        issues.append(f"{rid}:class={cls}")
    if art.get("grounded_status") != "success":
        issues.append(f"{rid}:status={art.get('grounded_status')}")
    if art.get("grounded_fallback"):
        issues.append(f"{rid}:fallback")
    calls = int(art.get("provider_call_count") or 0)
    if calls != 2:
        issues.append(f"{rid}:calls={calls}")
    total_calls += calls
    trace = art.get("source_trace") if isinstance(art.get("source_trace"), dict) else {}
    if int(trace.get("selected_evidence_count") or 0) <= 0:
        issues.append(f"{rid}:empty_trace")
    if int(trace.get("citation_ready_count") or 0) <= 0:
        issues.append(f"{rid}:citation_ready=0")
    if not art.get("prompt_hash_a") or not art.get("prompt_hash_b"):
        issues.append(f"{rid}:missing_hashes")
    if not art.get("blind_mapping"):
        issues.append(f"{rid}:missing_mapping")
    if p.get("human_review_status") != "pending":
        issues.append(f"{rid}:review_not_pending")

# Blind integrity: human MD must not reveal which response is production/grounded.
for needle in (
    "blind_mapping",
    "\nMAPPING\n",
    "### Production response",
    "### Grounded response",
    "A = production",
    "B = grounded",
    "A: production",
    "B: grounded",
):
    if needle in md:
        issues.append(f"md_leak:{needle.strip()}")

st = build_campaign_status()
report = {
    "index_pairs": idx["pair_count"],
    "unique_run_ids": len(run_ids),
    "provider_calls_on_index_runs": total_calls,
    "campaign_generated_live": st["generated_live_pairs"],
    "campaign_reviewed_live": st["reviewed_live_pairs"],
    "campaign_missing": st["missing_pairs"],
    "readiness": st["staging_readiness"]["status"],
    "live_provider_call_count": st["live_provider_call_count"],
    "review_md_chars": len(md),
    "guide_md_chars": len(guide),
    "issues": issues,
    "ok": not issues
    and idx["pair_count"] == 8
    and total_calls == 16
    and st["generated_live_pairs"] == 8
    and st["reviewed_live_pairs"] == 0,
}
print(json.dumps(report, indent=2, ensure_ascii=True))
raise SystemExit(0 if report["ok"] else 1)
