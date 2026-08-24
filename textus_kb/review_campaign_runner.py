"""Phase 5G live benchmark runner + human review pack builder (dev-only).

Explicit developer invocation only — never called from production UI.
Does not write review-rate preferences (human review stays pending).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from textus_kb.compare_store import DEFAULT_COMPARE_DB_PATH, persist_compare_run
from textus_kb.grounded_compare import (
    DEFAULT_COMPARE_DIR,
    _responses_for_display,
    format_source_trace_report,
    run_grounded_compare,
)
from textus_kb.production_prompt_export import build_production_section_prompt
from textus_kb.review_campaign import required_campaign_pairs

PROVIDER_ERROR_MARKERS = (
    "⚠️ **Hiányzó API kulcs",
    "⚠️ **API hiba",
    "várakozás van",
    "Globális cooldown",
)


def _looks_like_provider_failure(text: str) -> bool:
    raw = str(text or "")
    if not raw.strip():
        return True
    return any(marker in raw for marker in PROVIDER_ERROR_MARKERS)


def run_single_live_pair(
    passage: str,
    module: str,
    *,
    database_path: str | Path | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one live blind A/B pair using the real production section prompt."""
    os.environ["TEXTUS_KB_COMPARE_STORE_ENABLED"] = "true"
    export = build_production_section_prompt(passage, module=module)
    generate_fn, model_note = _import_live_generate()

    artifact = run_grounded_compare(
        export.passage_canonical,
        module=export.module,
        production_prompt=export.production_prompt,
        generate_text_fn=generate_fn,
        blind=True,
        provider_model=model_note,
        tab_label=export.tab_label,
    )
    payload = artifact.to_dict()
    payload["benchmark_prompt_export"] = export.to_dict()

    # Detect soft provider failures that still return a string.
    soft_fail = False
    soft_reason = ""
    if _looks_like_provider_failure(artifact.production_output):
        soft_fail = True
        soft_reason = "production_output_looks_like_provider_error"
        payload["grounded_status"] = "error"
        payload["grounded_error"] = soft_reason
    elif artifact.grounded_status == "success" and _looks_like_provider_failure(
        artifact.grounded_output
    ):
        soft_fail = True
        soft_reason = "grounded_output_looks_like_provider_error"
        payload["grounded_status"] = "error"
        payload["grounded_error"] = soft_reason

    store_id = persist_compare_run(
        payload,
        database_path=database_path,
        enabled=True,
    )

    out = Path(out_dir or DEFAULT_COMPARE_DIR)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"compare_{export.passage_canonical.replace('.', '_')}_{export.module}_{artifact.run_id[:8]}.json"
    # Blind export for humans — mapping withheld.
    blind_copy = dict(payload)
    blind_copy.pop("blind_mapping", None)
    json_path.write_text(json.dumps(blind_copy, indent=2, ensure_ascii=True), encoding="utf-8")
    # Mapping kept only in sidecar for technical recovery (not in review MD).
    map_path = out / f"mapping_{artifact.run_id[:8]}.json"
    map_path.write_text(
        json.dumps(
            {
                "run_id": artifact.run_id,
                "blind_mapping": payload.get("blind_mapping"),
                "note": "Technical only — do not open before human review.",
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    return {
        "run_id": artifact.run_id,
        "store_id": store_id,
        "passage": export.passage_canonical,
        "module": export.module,
        "tab_label": export.tab_label,
        "grounded_status": payload.get("grounded_status"),
        "grounded_error": payload.get("grounded_error") or soft_reason,
        "provider_call_count": artifact.provider_call_count,
        "production_output_chars": artifact.production_output_chars,
        "grounded_output_chars": artifact.grounded_output_chars,
        "json_path": str(json_path),
        "soft_fail": soft_fail,
        "artifact": payload,
        "export_meta": export.to_dict(),
    }


def _import_live_generate():
    from textus_kb.grounded_compare import _resolve_live_generate

    return _resolve_live_generate()


def verify_pair_result(result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    art = result.get("artifact") or {}
    if result.get("soft_fail"):
        issues.append(str(result.get("grounded_error") or "soft_fail"))
    if str(art.get("grounded_status")) != "success":
        issues.append(f"grounded_status={art.get('grounded_status')}")
    if not str(art.get("production_output") or "").strip():
        issues.append("missing_production_output")
    if not str(art.get("grounded_output") or "").strip():
        issues.append("missing_grounded_output")
    if int(art.get("provider_call_count") or 0) != 2:
        issues.append(f"provider_call_count={art.get('provider_call_count')}")
    if not art.get("prompt_hash_a") or not art.get("prompt_hash_b"):
        issues.append("missing_prompt_hashes")
    if bool(art.get("grounded_fallback")):
        issues.append("grounded_fallback")
    budget_status = str(
        (art.get("metrics") or {}).get("budget_status")
        or art.get("budget_status")
        or ""
    ).lower()
    if budget_status and budget_status not in {"ok", "trimmed"}:
        issues.append(f"budget_status={budget_status}")
    elif not budget_status:
        # Prefer metrics; fall back to budget_diagnostics when present.
        diag = (art.get("metrics") or {}).get("budget_diagnostics") or art.get(
            "budget_diagnostics"
        ) or {}
        budget_status = str(diag.get("budget_status") or "").lower()
        if budget_status and budget_status not in {"ok", "trimmed"}:
            issues.append(f"budget_status={budget_status}")
    trace = art.get("source_trace") if isinstance(art.get("source_trace"), dict) else {}
    if int(trace.get("selected_evidence_count") or 0) <= 0:
        issues.append("empty_source_trace")
    if int(trace.get("citation_ready_count") or 0) <= 0:
        issues.append("no_citation_ready")
    if not result.get("store_id"):
        issues.append("compare_store_persist_failed")
    if str(art.get("provider_model") or "").startswith("mock"):
        issues.append("mock_provider")
    return issues


def run_full_campaign(
    *,
    database_path: str | Path | None = None,
    out_dir: Path | None = None,
    max_retries: int = 1,
) -> dict[str, Any]:
    """Run all 8 required live pairs sequentially. Never auto review-rate."""
    os.environ["TEXTUS_KB_COMPARE_STORE_ENABLED"] = "true"
    out = Path(out_dir or DEFAULT_COMPARE_DIR)
    out.mkdir(parents=True, exist_ok=True)
    db = database_path or DEFAULT_COMPARE_DB_PATH

    results: list[dict[str, Any]] = []
    for passage, module in required_campaign_pairs():
        attempt = 0
        while True:
            attempt += 1
            print(f"=== LIVE PAIR {passage} / {module} (attempt {attempt}) ===", flush=True)
            result = run_single_live_pair(
                passage,
                module,
                database_path=db,
                out_dir=out,
            )
            issues = verify_pair_result(result)
            result["verification_issues"] = issues
            if not issues:
                results.append(result)
                break
            transient = any(
                x in " ".join(issues).lower()
                for x in ("timeout", "429", "5xx", "connection", "provider_error", "soft_fail")
            )
            if attempt <= max_retries and transient:
                print(f"RETRY after issues: {issues}", flush=True)
                time.sleep(12)
                continue
            results.append(result)
            # Structural failures stop the campaign.
            if any(
                s in " ".join(issues)
                for s in (
                    "grounded_fallback",
                    "empty_source_trace",
                    "missing_prompt_hashes",
                    "compare_store_persist_failed",
                    "budget_status=",
                    "no_citation_ready",
                    "mock_provider",
                )
            ):
                return {
                    "ok": False,
                    "stopped_early": True,
                    "results": results,
                    "error": f"Structural failure on {passage}/{module}: {issues}",
                }
            break

    return {"ok": all(not r.get("verification_issues") for r in results), "results": results}


def build_review_pack(
    results: list[dict[str, Any]],
    *,
    out_dir: Path | None = None,
) -> dict[str, str]:
    """Write human review MD + guide + index. Does not reveal A/B mapping."""
    out = Path(out_dir or DEFAULT_COMPARE_DIR)
    out.mkdir(parents=True, exist_ok=True)

    title_map = {
        ("John.4.1-42", "exegesis"): "1. John 4 — Exegesis",
        ("John.4.1-42", "historical_context"): "2. John 4 — Historical context",
        ("Luke.10.25-37", "exegesis"): "3. Luke 10 — Exegesis",
        ("Luke.10.25-37", "historical_context"): "4. Luke 10 — Historical context",
        ("Acts.2.1-13", "exegesis"): "5. Acts 2 — Exegesis",
        ("Acts.2.1-13", "historical_context"): "6. Acts 2 — Historical context",
        ("Rom.8.28-30", "exegesis"): "7. Romans 8 — Exegesis",
        ("Rom.8.28-30", "historical_context"): "8. Romans 8 — Historical context",
    }

    lines = [
        "# Phase 5G Human Review",
        "",
        "Blind A/B review package. Mapping (production vs grounded) is withheld.",
        "Fill the Human review checkboxes after reading both responses.",
        "Do **not** open mapping sidecars before rating.",
        "",
    ]
    index_rows: list[dict[str, Any]] = []

    for result in results:
        art = result.get("artifact") or {}
        passage = str(art.get("passage") or result.get("passage") or "")
        module = str(art.get("module") or result.get("module") or "")
        heading = title_map.get((passage, module), f"{passage} — {module}")
        responses = _responses_for_display(art)
        trace = art.get("source_trace") if isinstance(art.get("source_trace"), dict) else {}
        metrics = art.get("metrics") if isinstance(art.get("metrics"), dict) else {}
        diag = metrics.get("budget_diagnostics") or {}
        selection = (
            metrics.get("selection_diagnostics")
            or diag.get("selection_diagnostics")
            or {}
        )
        budget_status = str(
            metrics.get("budget_status") or diag.get("budget_status") or "unknown"
        )
        kb_pct = metrics.get("kb_percentage_of_total")
        if kb_pct is None:
            kb_pct = metrics.get("kb_share_of_grounded_percent")
        candidate_n = selection.get("candidate_evidence_count") or selection.get(
            "candidates"
        )
        selected_n = selection.get("selected_evidence_count") or selection.get(
            "selected"
        ) or len(art.get("evidence_ids") or [])

        lines.extend(
            [
                f"## {heading}",
                "",
                f"**run_id:** `{art.get('run_id')}`",
                f"**status:** {art.get('grounded_status')}",
                "",
                "### Response A",
                "",
                str(responses.get("A") or "").strip() or "_(empty)_",
                "",
                "### Response B",
                "",
                str(responses.get("B") or "").strip() or "_(empty)_",
                "",
                "### Technical metadata",
                "",
                f"- production prompt tokens: {art.get('production_prompt_estimated_tokens')}",
                f"- grounded prompt tokens: {art.get('grounded_prompt_estimated_tokens')}",
                f"- KB context tokens: {art.get('kb_context_estimated_tokens')}",
                f"- KB percentage: {kb_pct}%",
                f"- production generation latency (ms): {art.get('production_latency_ms')}",
                f"- grounded prep latency (ms): {art.get('grounded_prep_ms')}",
                f"- grounded generation latency (ms): {art.get('grounded_latency_ms')}",
                f"- candidate evidence: {candidate_n}",
                f"- selected evidence: {selected_n}",
                f"- target KB tokens: {metrics.get('target_kb_context_tokens') or diag.get('target_kb_context_tokens')}",
                f"- max KB tokens: {metrics.get('max_kb_context_tokens') or metrics.get('kb_context_max_tokens') or diag.get('max_kb_context_tokens')}",
                f"- grounded instruction overhead: {metrics.get('composition_overhead_estimated_tokens') or diag.get('grounded_instruction_overhead')}",
                f"- total grounded tokens: {metrics.get('total_grounded_estimated_tokens') or diag.get('total_grounded_tokens')}",
                f"- budget status: {budget_status}",
                f"- provider call count: {art.get('provider_call_count')}",
                "",
                "### Grounded source trace",
                "",
                f"- Study Notes: {trace.get('study_notes_count', 0)}",
                f"- Dictionary: {trace.get('dictionary_count', 0)}",
                f"- Linguistic: {trace.get('linguistic_evidence_count', 0)}",
                f"- ACAI: {trace.get('acai_entity_source_count', 0)}",
                f"- Places/background: {trace.get('places_background_count', 0)}",
                f"- Citation-ready: {trace.get('citation_ready_count', 0)}",
                f"- selected evidence count: {trace.get('selected_evidence_count', 0)}",
                f"- source IDs: {', '.join(art.get('source_ids') or []) or '(none)'}",
                "",
                "Full citation detail:",
                "",
                "```",
                format_source_trace_report(art).rstrip(),
                "```",
                "",
                "### Human review",
                "",
                "Factual accuracy:",
                "[ ] A",
                "[ ] B",
                "[ ] Equal",
                "[ ] Unclear",
                "",
                "Exegetical usefulness:",
                "[ ] A",
                "[ ] B",
                "[ ] Equal",
                "[ ] Unclear",
                "",
                "Historical grounding:",
                "[ ] A",
                "[ ] B",
                "[ ] Equal",
                "[ ] Unclear",
                "",
                "Clarity/style:",
                "[ ] A",
                "[ ] B",
                "[ ] Equal",
                "[ ] Unclear",
                "",
                "Hallucination risk:",
                "[ ] A",
                "[ ] B",
                "[ ] Both",
                "[ ] Neither",
                "[ ] Unclear",
                "",
                "Overall:",
                "[ ] A",
                "[ ] B",
                "[ ] Equal",
                "[ ] Unclear",
                "",
                "Notes:",
                "",
                "---",
                "",
            ]
        )

        provider_model = str(art.get("provider_model") or art.get("model_note") or "")
        live_flag = "live" if not provider_model.startswith("mock") else "mock"
        index_rows.append(
            {
                "run_id": art.get("run_id"),
                "passage": passage,
                "module": module,
                "reviewer_response_a": "A",
                "reviewer_response_b": "B",
                "generation_status": art.get("grounded_status"),
                "live_or_mock": live_flag,
                "provider": "Gemini",
                "model": provider_model,
                "provider_call_count": art.get("provider_call_count"),
                "source_trace_status": (
                    "ok"
                    if int(trace.get("selected_evidence_count") or 0) > 0
                    else "empty"
                ),
                "budget_status": budget_status,
                "production_prompt_tokens": art.get("production_prompt_estimated_tokens"),
                "grounded_prompt_tokens": art.get("grounded_prompt_estimated_tokens"),
                "kb_context_tokens": art.get("kb_context_estimated_tokens"),
                "kb_percentage_of_total": kb_pct,
                "candidate_evidence_count": candidate_n,
                "selected_evidence_count": selected_n,
                "prompt_hash_a": art.get("prompt_hash_a"),
                "prompt_hash_b": art.get("prompt_hash_b"),
                "latency": {
                    "production_ms": art.get("production_latency_ms"),
                    "grounded_prep_ms": art.get("grounded_prep_ms"),
                    "grounded_ms": art.get("grounded_latency_ms"),
                },
                "human_review_status": "pending",
                # Internal metadata only — not shown in human review MD.
                "internal_blind_mapping": art.get("blind_mapping"),
                "verification_issues": result.get("verification_issues") or [],
            }
        )

    review_md = out / "PHASE5G_HUMAN_REVIEW.md"
    guide_md = out / "PHASE5G_REVIEW_GUIDE.md"
    index_json = out / "phase5g_review_index.json"

    review_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    guide_md.write_text(
        "\n".join(
            [
                "# Phase 5G Review Guide",
                "",
                "Short checklist while reading Response A and Response B.",
                "Do not decide before reading both fully. Mapping is blind on purpose.",
                "Do **not** open mapping sidecars before rating.",
                "",
                "## Exegesis",
                "",
                "- Greek linguistic accuracy (when claimed)",
                "- Lexical claims tied to the passage",
                "- Literary / textual context",
                "- Real exegetical added value",
                "- Suspicious or unsourced claims",
                "- Natural Hungarian",
                "- Excessive technical / data-dump style",
                "",
                "## Historical context",
                "",
                "- Historical concreteness",
                "- Cultural background",
                "- Accuracy of people / places / groups",
                "- Anachronism",
                "- Overstated or uncertain claims",
                "- Usability for pastoral prep",
                "- Natural Hungarian",
                "",
                "## General questions",
                "",
                "- Which gives more actually usable information?",
                "- Which asserts fewer unverifiable specifics?",
                "- Which reads more naturally?",
                "- Which would I rather use for preparation?",
                "",
                "## After reading",
                "",
                "1. Fill the Human review section in `PHASE5G_HUMAN_REVIEW.md`",
                "2. Persist with `python -m textus_kb review-rate <run_id> ...`",
                "3. Only then `python -m textus_kb review-show <run_id> --reveal`",
                "4. Final: `python -m textus_kb review-campaign-status`",
                "5. Final: `python -m textus_kb review-summary --live-only`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    index_json.write_text(
        json.dumps(
            {
                "campaign": "phase5g",
                "human_review_status": "pending",
                "pair_count": len(index_rows),
                "pairs": index_rows,
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    return {
        "review_md": str(review_md),
        "guide_md": str(guide_md),
        "index_json": str(index_json),
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(
            "Usage: python -m textus_kb.review_campaign_runner [--run] [--pack-only]",
            file=sys.stderr,
        )
        return 2

    # Cost visibility before live work.
    print(
        "COST ESTIMATE\n"
        "- pairs: 8\n"
        "- provider calls: 16 (2 per pair)\n"
        "- model/provider: Gemini 2.5 Flash via app.generate_text\n"
        "- known cost risk: real paid/shared Gemini usage; long NT passages\n"
        "  (esp. John 4 / Acts 2) + Greek token blocks => larger prompts\n"
        "- no monetary estimate (no reliable runtime pricing data)\n",
        flush=True,
    )

    if "--pack-only" in args:
        print("pack-only requires prior results; use --run", file=sys.stderr)
        return 2

    if "--run" not in args:
        print("Refusing to start live calls without explicit --run", file=sys.stderr)
        return 2

    campaign = run_full_campaign()
    pack = build_review_pack(campaign.get("results") or [])
    summary = {
        "ok": campaign.get("ok"),
        "stopped_early": campaign.get("stopped_early", False),
        "error": campaign.get("error"),
        "pair_count": len(campaign.get("results") or []),
        "provider_calls": sum(
            int((r.get("artifact") or {}).get("provider_call_count") or 0)
            for r in (campaign.get("results") or [])
        ),
        "pack": pack,
        "pairs": [
            {
                "passage": r.get("passage"),
                "module": r.get("module"),
                "run_id": r.get("run_id"),
                "issues": r.get("verification_issues"),
                "status": (r.get("artifact") or {}).get("grounded_status"),
            }
            for r in (campaign.get("results") or [])
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if campaign.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
