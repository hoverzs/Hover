"""Dev-only A/B compare + human review workflow (Phase 5E).

Explicit CLI/API only — never invoked from production ``generate_section()``.
Compare outputs may be stored in a separate gitignored SQLite DB when
``TEXTUS_KB_COMPARE_STORE_ENABLED=true`` (not the Phase 5B shadow audit store).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from textus_kb.compare_store import (
    COMPARE_STORE_FLAG,
    DEFAULT_COMPARE_DB_PATH,
    HumanReview,
    is_compare_store_enabled,
    persist_compare_run,
)
from textus_kb.evidence import estimate_text_tokens
from textus_kb.grounded_generation import prepare_grounded_provider_prompt
from textus_kb.paths import GENERATED_DATA_DIR
from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB
from textus_kb.shadow import MODULE_TO_PROFILE
from textus_kb.shadow_audit import classify_source_mix

DEFAULT_COMPARE_DIR = GENERATED_DATA_DIR / "kb_grounded_compare"
BENCHMARK_PASSAGES = (
    "John.4.1-42",
    "Luke.10.25-37",
    "Acts.2.1-13",
    "Rom.8.28-30",
)
BENCHMARK_MODULES = ("exegesis", "historical_context")


@dataclass
class GroundedCompareArtifact:
    run_id: str
    timestamp: str
    passage: str
    module: str
    production_output: str
    grounded_output: str
    production_prompt_chars: int
    grounded_prompt_chars: int
    production_prompt_estimated_tokens: int
    grounded_prompt_estimated_tokens: int
    kb_context_estimated_tokens: int
    production_output_chars: int = 0
    grounded_output_chars: int = 0
    production_output_estimated_tokens: int = 0
    grounded_output_estimated_tokens: int = 0
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    source_trace: dict[str, Any] = field(default_factory=dict)
    grounded_used: bool = False
    grounded_fallback: bool = False
    grounded_status: str = "success"  # success | error
    grounded_error: str = ""
    fallback_reason: str = ""
    production_latency_ms: int = 0
    grounded_prep_ms: int = 0
    grounded_latency_ms: int = 0
    provider_call_count: int = 0
    composition_version: str = ""
    prompt_hash_a: str = ""
    prompt_hash_b: str = ""
    evidence_build_id: str = ""
    provider_model: str = "mock"
    model_note: str = "mock"
    blind: bool = False
    blind_mapping: dict[str, str] = field(default_factory=dict)
    review: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_source_trace(
    *,
    source_ids: list[str],
    evidence_ids: list[str],
    context_packet: dict[str, Any] | None = None,
    entity_count: int = 0,
    selected_item_count: int = 0,
) -> dict[str, Any]:
    mix = classify_source_mix(list(source_ids))
    citation_ready_count = 0
    citation_incomplete_count = 0
    citations: list[dict[str, Any]] = []
    if context_packet:
        try:
            from textus_kb.citation import citations_from_context_packet

            coverage = citations_from_context_packet(context_packet)
            citation_ready_count = coverage.citation_ready_count
            citation_incomplete_count = coverage.incomplete_count
            citations = [
                {
                    "title": c.title,
                    "source_id": c.source_id,
                    "evidence_id": c.evidence_id,
                    "source_type": c.source_type,
                    "article_or_chunk_id": c.article_or_chunk_id,
                    "canonical_scope": c.canonical_scope,
                    "license": c.license,
                    "attribution": c.attribution,
                    "citation_ready": c.citation_ready,
                }
                for c in coverage.citations
            ]
        except Exception:
            pass
    return {
        "source_ids": list(source_ids),
        "selected_evidence_count": len(evidence_ids),
        "selected_item_count": int(selected_item_count),
        "study_notes_count": int(mix.get("study_notes") or 0),
        "dictionary_count": int(mix.get("dictionary") or 0),
        "acai_entity_source_count": int(mix.get("acai") or 0),
        "linguistic_evidence_count": int(mix.get("linguistic") or 0),
        "places_background_count": int(mix.get("places_background") or 0),
        "entity_count": int(entity_count),
        "source_mix": mix,
        "context_section_count": len((context_packet or {}).get("sections") or []),
        "citation_ready_count": citation_ready_count,
        "citation_incomplete_count": citation_incomplete_count,
        "citations": citations,
    }


def run_grounded_compare(
    passage: str,
    *,
    module: str,
    production_prompt: str,
    generate_text_fn: Callable[..., str],
    use_search: bool = False,
    tab_label: str = "grounded-compare",
    blind: bool = False,
    provider_model: str = "caller_generate_fn",
    rng: random.Random | None = None,
) -> GroundedCompareArtifact:
    """Run explicit A/B provider calls for human review.

    Compare mode does **not** substitute the production prompt for B on grounded
    failure — B is recorded as ``error`` while A is preserved.
    """
    if module not in MODULE_TO_PROFILE and module != "history":
        raise ValueError(f"Unsupported module for grounded-compare: {module!r}")
    module_key = "historical_context" if module == "history" else module
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    prompt_hash_a = _sha256_text(production_prompt)

    # Same tab_label for A and B → same model / max_output_tokens / config.
    provider_tab = tab_label

    # --- A: production ---
    t0 = time.perf_counter()
    production_output = generate_text_fn(
        production_prompt,
        enable_google_search=use_search,
        tab_label=provider_tab,
    )
    production_ms = int((time.perf_counter() - t0) * 1000)
    provider_calls = 1

    # --- B: grounded prep (no production-prompt substitution on failure) ---
    t1 = time.perf_counter()
    prep = prepare_grounded_provider_prompt(
        production_prompt=production_prompt,
        passage=passage,
        module=module_key,
        grounded_enabled=True,
    )
    prep_ms = int((time.perf_counter() - t1) * 1000)

    grounded_output = ""
    grounded_latency_ms = 0
    grounded_status = "success"
    grounded_error = ""
    prompt_hash_b = ""
    grounded_prompt_chars = 0
    grounded_prompt_tokens = 0

    if prep.grounded_used and prep.provider_prompt and prep.provider_prompt != production_prompt:
        prompt_hash_b = _sha256_text(prep.provider_prompt)
        grounded_prompt_chars = len(prep.provider_prompt)
        grounded_prompt_tokens = prep.composed_prompt_estimated_tokens
        t2 = time.perf_counter()
        try:
            grounded_output = generate_text_fn(
                prep.provider_prompt,
                enable_google_search=use_search,
                tab_label=provider_tab,
            )
            grounded_latency_ms = int((time.perf_counter() - t2) * 1000)
            provider_calls += 1
        except Exception as exc:
            grounded_status = "error"
            grounded_error = f"{type(exc).__name__}"
            grounded_latency_ms = int((time.perf_counter() - t2) * 1000)
    else:
        grounded_status = "error"
        grounded_error = (
            prep.error
            or prep.fallback_reason
            or ("grounded_fallback" if prep.grounded_fallback else "grounded_prep_failed")
        )
        grounded_prompt_chars = 0
        grounded_prompt_tokens = 0
        prompt_hash_b = ""

    source_trace = build_source_trace(
        source_ids=list(prep.source_ids),
        evidence_ids=list(prep.evidence_ids),
        context_packet=prep.context_packet,
        entity_count=prep.entity_count,
        selected_item_count=prep.selected_item_count,
    )

    # Blind mapping: display labels A/B hide which is production vs grounded.
    if blind:
        coin = (rng or random.Random()).choice(("AB", "BA"))
        if coin == "AB":
            blind_mapping = {"A": "production", "B": "grounded"}
        else:
            blind_mapping = {"A": "grounded", "B": "production"}
    else:
        blind_mapping = {"A": "production", "B": "grounded"}

    metrics = {
        "provider_call_count": provider_calls,
        "production_prompt_chars": len(production_prompt),
        "production_prompt_estimated_tokens": prep.original_prompt_estimated_tokens
        or estimate_text_tokens(production_prompt),
        "grounded_prompt_chars": grounded_prompt_chars,
        "grounded_prompt_estimated_tokens": grounded_prompt_tokens,
        "kb_context_estimated_tokens": prep.kb_context_estimated_tokens,
        "composition_overhead_estimated_tokens": int(
            (prep.budget_diagnostics or {}).get("composition_overhead_estimated_tokens") or 0
        ),
        "total_grounded_estimated_tokens": int(
            (prep.budget_diagnostics or {}).get("total_grounded_estimated_tokens")
            or grounded_prompt_tokens
            or 0
        ),
        "kb_share_of_grounded_percent": float(
            (prep.budget_diagnostics or {}).get("kb_share_of_grounded_percent") or 0.0
        ),
        "target_kb_context_tokens": int(
            (prep.budget_diagnostics or {}).get("target_kb_context_tokens")
            or (prep.budget_diagnostics or {}).get("kb_context_target_tokens")
            or 0
        ),
        "kb_context_max_tokens": int(
            (prep.budget_diagnostics or {}).get("kb_context_max_tokens")
            or (prep.budget_diagnostics or {}).get("max_kb_context_tokens")
            or 0
        ),
        "total_grounded_max_tokens": int(
            (prep.budget_diagnostics or {}).get("total_grounded_max_tokens") or 0
        ),
        "kb_trim_applied": bool((prep.budget_diagnostics or {}).get("kb_trim_applied")),
        "budget_status": str(
            (prep.budget_diagnostics or {}).get("budget_status")
            or ("exceeded" if grounded_status != "success" and prep.grounded_fallback else "ok")
        ),
        "selection_diagnostics": dict(
            (prep.budget_diagnostics or {}).get("selection_diagnostics") or {}
        ),
        "production_output_chars": len(production_output or ""),
        "grounded_output_chars": len(grounded_output or ""),
        "production_output_estimated_tokens": estimate_text_tokens(production_output or ""),
        "grounded_output_estimated_tokens": estimate_text_tokens(grounded_output or "")
        if grounded_output
        else 0,
        "production_latency_ms": production_ms,
        "grounded_prep_ms": prep_ms,
        "grounded_latency_ms": grounded_latency_ms,
        "budget_diagnostics": dict(prep.budget_diagnostics or {}),
    }

    return GroundedCompareArtifact(
        run_id=run_id,
        timestamp=timestamp,
        passage=prep.canonical_passage or passage,
        module=module_key,
        production_output=production_output or "",
        grounded_output=grounded_output or "",
        production_prompt_chars=len(production_prompt),
        grounded_prompt_chars=grounded_prompt_chars,
        production_prompt_estimated_tokens=metrics["production_prompt_estimated_tokens"],
        grounded_prompt_estimated_tokens=grounded_prompt_tokens,
        kb_context_estimated_tokens=prep.kb_context_estimated_tokens,
        production_output_chars=metrics["production_output_chars"],
        grounded_output_chars=metrics["grounded_output_chars"],
        production_output_estimated_tokens=metrics["production_output_estimated_tokens"],
        grounded_output_estimated_tokens=metrics["grounded_output_estimated_tokens"],
        source_ids=list(prep.source_ids),
        evidence_ids=list(prep.evidence_ids),
        source_trace=source_trace,
        grounded_used=bool(prep.grounded_used and grounded_status == "success"),
        grounded_fallback=prep.grounded_fallback,
        grounded_status=grounded_status,
        grounded_error=grounded_error,
        fallback_reason=prep.fallback_reason,
        production_latency_ms=production_ms,
        grounded_prep_ms=prep_ms,
        grounded_latency_ms=grounded_latency_ms,
        provider_call_count=provider_calls,
        composition_version=prep.composition_version,
        prompt_hash_a=prompt_hash_a,
        prompt_hash_b=prompt_hash_b,
        evidence_build_id=prep.evidence_build_id,
        provider_model=provider_model,
        model_note=provider_model,
        blind=blind,
        blind_mapping=blind_mapping,
        review=HumanReview().to_dict(),
        metrics=metrics,
    )


def _responses_for_display(artifact: GroundedCompareArtifact | dict[str, Any]) -> dict[str, str]:
    data = artifact.to_dict() if isinstance(artifact, GroundedCompareArtifact) else dict(artifact)
    mapping = data.get("blind_mapping") or {"A": "production", "B": "grounded"}
    prod = str(data.get("production_output") or "")
    grounded = str(data.get("grounded_output") or "")
    if data.get("grounded_status") == "error" and not grounded:
        grounded = f"[ERROR] {data.get('grounded_error') or 'grounded generation failed'}"
    out: dict[str, str] = {}
    for label in ("A", "B"):
        kind = mapping.get(label, "production" if label == "A" else "grounded")
        out[label] = prod if kind == "production" else grounded
    return out


def format_compare_report(
    artifact: GroundedCompareArtifact | dict[str, Any],
    *,
    reveal_mapping: bool = False,
) -> str:
    """Human-readable report. Blind mode hides production/grounded labels unless revealed."""
    data = artifact.to_dict() if isinstance(artifact, GroundedCompareArtifact) else dict(artifact)
    responses = _responses_for_display(data)
    review = data.get("review") if isinstance(data.get("review"), dict) else {}
    trace = data.get("source_trace") if isinstance(data.get("source_trace"), dict) else {}
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    lines = [
        "--------------------------------",
        f"PASSAGE: {data.get('passage')}",
        f"MODULE: {data.get('module')}",
        f"RUN_ID: {data.get('run_id')}",
        f"TIMESTAMP: {data.get('timestamp')}",
        "--------------------------------",
        "",
        "RESPONSE A",
        responses.get("A", ""),
        "",
        "RESPONSE B",
        responses.get("B", ""),
        "",
        "KB SOURCES",
    ]
    if data.get("blind") and not reveal_mapping:
        lines.append("(hidden in blind mode — see metadata after review)")
    else:
        lines.append(f"source_ids: {', '.join(data.get('source_ids') or []) or '(none)'}")
        lines.append(f"selected_evidence_count: {trace.get('selected_evidence_count', 0)}")
        lines.append(f"study_notes_count: {trace.get('study_notes_count', 0)}")
        lines.append(f"dictionary_count: {trace.get('dictionary_count', 0)}")
        lines.append(f"acai_entity_source_count: {trace.get('acai_entity_source_count', 0)}")
        lines.append(f"linguistic_evidence_count: {trace.get('linguistic_evidence_count', 0)}")
        lines.append(f"places_background_count: {trace.get('places_background_count', 0)}")
        lines.append(f"entity_count: {trace.get('entity_count', 0)}")
        lines.append(f"citation_ready_count: {trace.get('citation_ready_count', 0)}")
        lines.append(f"grounded_status: {data.get('grounded_status')}")
        if data.get("grounded_error"):
            lines.append(f"grounded_error: {data.get('grounded_error')}")
        lines.append("(full citation list: python -m textus_kb review-sources <run_id>)")
    lines.extend(
        [
            "",
            "METRICS",
            f"provider_call_count: {data.get('provider_call_count') or metrics.get('provider_call_count')}",
            f"production_prompt_estimated_tokens: {data.get('production_prompt_estimated_tokens')}",
            f"grounded_prompt_estimated_tokens: {data.get('grounded_prompt_estimated_tokens')}",
            f"kb_context_estimated_tokens: {data.get('kb_context_estimated_tokens')}",
            f"production_output_chars: {data.get('production_output_chars')}",
            f"grounded_output_chars: {data.get('grounded_output_chars')}",
            f"production_latency_ms: {data.get('production_latency_ms')}",
            f"grounded_prep_ms: {data.get('grounded_prep_ms')}",
            f"grounded_latency_ms: {data.get('grounded_latency_ms')}",
            f"provider_model: {data.get('provider_model') or data.get('model_note')}",
            f"composition_version: {data.get('composition_version')}",
            f"prompt_hash_a: {data.get('prompt_hash_a')}",
            f"prompt_hash_b: {data.get('prompt_hash_b')}",
            f"evidence_build_id: {data.get('evidence_build_id')}",
            "",
            "REVIEW",
        ]
    )
    if any(str(v).strip() for v in review.values()):
        for key in (
            "factual_accuracy_preference",
            "exegetical_usefulness_preference",
            "historical_grounding_preference",
            "clarity_style_preference",
            "hallucination_risk",
            "overall_preference",
            "reviewer_notes",
        ):
            lines.append(f"{key}: {review.get(key) or ''}")
    else:
        lines.append("(empty — use review-rate to record human preferences)")
    if reveal_mapping or not data.get("blind"):
        lines.extend(
            [
                "",
                "MAPPING",
                f"blind: {bool(data.get('blind'))}",
                f"blind_mapping: {json.dumps(data.get('blind_mapping') or {}, ensure_ascii=True)}",
            ]
        )
    else:
        lines.extend(["", "MAPPING", "blind: true (mapping withheld from reviewer-facing text)"])
    return "\n".join(lines).rstrip() + "\n"


def format_source_trace_report(artifact: dict[str, Any]) -> str:
    """Human-readable citation/source trace (not mixed into Response A/B)."""
    from textus_kb.citation import display_name_for_source

    trace = artifact.get("source_trace") if isinstance(artifact.get("source_trace"), dict) else {}
    lines = [
        "--------------------------------",
        "SOURCE / CITATION TRACE",
        f"PASSAGE: {artifact.get('passage')}",
        f"MODULE: {artifact.get('module')}",
        f"RUN_ID: {artifact.get('run_id')}",
        "--------------------------------",
        f"selected_evidence_count: {trace.get('selected_evidence_count', 0)}",
        f"study_notes_count: {trace.get('study_notes_count', 0)}",
        f"dictionary_count: {trace.get('dictionary_count', 0)}",
        f"linguistic_evidence_count: {trace.get('linguistic_evidence_count', 0)}",
        f"acai_entity_source_count: {trace.get('acai_entity_source_count', 0)}",
        f"places_background_count: {trace.get('places_background_count', 0)}",
        f"entity_count: {trace.get('entity_count', 0)}",
        f"citation_ready_count: {trace.get('citation_ready_count', 0)}",
        f"citation_incomplete_count: {trace.get('citation_incomplete_count', 0)}",
        "",
        "SOURCES",
    ]
    source_ids = list(artifact.get("source_ids") or trace.get("source_ids") or [])
    if not source_ids:
        lines.append("(none)")
    else:
        for sid in source_ids:
            lines.append(f"- {display_name_for_source(str(sid))} ({sid})")
    lines.append("")
    lines.append("CITATIONS")
    citations = list(trace.get("citations") or [])
    if not citations:
        lines.append("(none stored — regenerate compare to attach citation metadata)")
    else:
        for idx, cite in enumerate(citations, start=1):
            title = str(cite.get("title") or display_name_for_source(str(cite.get("source_id") or "")))
            lines.append(f"{idx}. {title}")
            lines.append(f"   type: {cite.get('source_type') or ''}")
            if cite.get("article_or_chunk_id"):
                lines.append(f"   article/chunk: {cite.get('article_or_chunk_id')}")
            if cite.get("canonical_scope"):
                lines.append(f"   scope: {cite.get('canonical_scope')}")
            lines.append(f"   license: {cite.get('license') or '(missing)'}")
            if cite.get("attribution"):
                lines.append(f"   attribution: {cite.get('attribution')}")
            lines.append(f"   citation_ready: {bool(cite.get('citation_ready'))}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_compare_export(
    artifact: GroundedCompareArtifact | dict[str, Any],
    output_path: str | Path,
    *,
    reveal_mapping: bool = False,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = artifact.to_dict() if isinstance(artifact, GroundedCompareArtifact) else dict(artifact)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
    else:
        path.write_text(
            format_compare_report(data, reveal_mapping=reveal_mapping),
            encoding="utf-8",
        )
    return path


def _mock_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
    kind = (
        "grounded"
        if "<<<BEGIN_KB_DATA>>>" in prompt or "BEGIN_KB_DATA" in prompt
        else "production"
    )
    return f"[mock:{kind}:{tab_label}] chars={len(prompt)} search={enable_google_search}"


def _resolve_live_generate() -> tuple[Callable[..., str], str]:
    """Best-effort reuse of production generate_text (dev/staging only).

    Wraps production ``generate_text`` so compare calls:
    - disable provider-output cache (A/B must both hit the provider);
    - wait out the global Gemini cooldown instead of returning a block message;
    - keep model/config parity via the caller's ``tab_label`` (section label).
    """
    try:
        from app import (  # type: ignore
            GEMINI_COOLDOWN_S,
            _cooldown_remaining,
            generate_text,
            resolve_gemini_model_for_tab,
        )
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Could not import app.generate_text for --live. "
            "Wire generate_text_fn via run_grounded_compare() instead."
        ) from exc

    def _live_generate(
        prompt: str,
        *,
        enable_google_search: bool = False,
        tab_label: str = "unknown",
    ) -> str:
        remaining = float(_cooldown_remaining() or 0.0)
        if remaining > 0:
            time.sleep(remaining + 0.05)
        return generate_text(
            prompt,
            enable_google_search=enable_google_search,
            tab_label=tab_label,
            use_cache=False,
            bypass_cooldown=False,
        )

    model_note = f"app.generate_text:{resolve_gemini_model_for_tab('Exegézis')}"
    _ = GEMINI_COOLDOWN_S  # documented parity constraint
    return _live_generate, model_note


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            'Usage: python -m textus_kb grounded-compare "<reference>" '
            "--module exegesis|historical_context "
            "[--blind] [--live --from-production | --live --prompt-file PATH] "
            "[--output PATH] [--database PATH] [--out DIR]",
            file=sys.stderr,
        )
        return 2

    passage = args[0]
    module = "exegesis"
    live = False
    blind = False
    from_production = False
    prompt_file = None
    output_path = None
    out_dir = DEFAULT_COMPARE_DIR
    database = None
    i = 1
    while i < len(args):
        if args[i] == "--module" and i + 1 < len(args):
            module = args[i + 1]
            i += 2
            continue
        if args[i] == "--live":
            live = True
            i += 1
            continue
        if args[i] == "--blind":
            blind = True
            i += 1
            continue
        if args[i] == "--from-production":
            from_production = True
            i += 1
            continue
        if args[i] == "--prompt-file" and i + 1 < len(args):
            prompt_file = args[i + 1]
            i += 2
            continue
        if args[i] == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
            continue
        if args[i] == "--out" and i + 1 < len(args):
            out_dir = Path(args[i + 1])
            i += 2
            continue
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        i += 1

    tab_label = "grounded-compare"
    if live:
        if not prompt_file and not from_production:
            print(
                "ERROR: --live requires --from-production or --prompt-file "
                "with the real production prompt. Do not use the dry-run stub.",
                file=sys.stderr,
            )
            return 2
        if not blind:
            print(
                "ERROR: --live requires --blind for unbiased human review. "
                "Reveal mapping only after review-rate via review-show --reveal.",
                file=sys.stderr,
            )
            return 2
        if from_production:
            from textus_kb.production_prompt_export import build_production_section_prompt

            export = build_production_section_prompt(passage, module=module)
            production_prompt = export.production_prompt
            tab_label = export.tab_label
            passage = export.passage_canonical
        else:
            production_prompt = Path(prompt_file).read_text(encoding="utf-8")
        if not production_prompt.strip():
            print("ERROR: production prompt is empty.", file=sys.stderr)
            return 2
        if production_prompt.strip() == DRY_RUN_PRODUCTION_STUB.strip():
            print(
                "ERROR: --live refuses the dry-run stub prompt. "
                "Use --from-production or export the real SECTION_PROMPTS prompt.",
                file=sys.stderr,
            )
            return 2
        generate_fn, model_note = _resolve_live_generate()
    else:
        if prompt_file:
            production_prompt = Path(prompt_file).read_text(encoding="utf-8")
        else:
            production_prompt = DRY_RUN_PRODUCTION_STUB
        generate_fn, model_note = _mock_generate, "mock"

    artifact = run_grounded_compare(
        passage,
        module=module,
        production_prompt=production_prompt,
        generate_text_fn=generate_fn,
        blind=blind,
        provider_model=model_note,
        tab_label=tab_label,
    )

    # Optional compare-store persistence (isolated; never touches shadow audit).
    store_run_id = None
    store_error = None
    try:
        store_run_id = persist_compare_run(
            artifact.to_dict(),
            database_path=database,
            enabled=True if database else None,
        )
    except Exception as exc:
        store_error = f"{type(exc).__name__}"

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_passage = str(artifact.passage).replace(".", "_")
    json_path = out_dir / f"compare_{safe_passage}_{module}_{artifact.run_id[:8]}.json"
    json_path.write_text(
        json.dumps(artifact.to_dict(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    export_path = None
    if output_path:
        export_path = save_compare_export(
            artifact,
            output_path,
            reveal_mapping=not blind,
        )

    summary = {
        "run_id": artifact.run_id,
        "passage": artifact.passage,
        "module": artifact.module,
        "blind": artifact.blind,
        "live": live,
        "grounded_status": artifact.grounded_status,
        "grounded_error": artifact.grounded_error,
        "grounded_used": artifact.grounded_used,
        "provider_call_count": artifact.provider_call_count,
        "production_prompt_estimated_tokens": artifact.production_prompt_estimated_tokens,
        "grounded_prompt_estimated_tokens": artifact.grounded_prompt_estimated_tokens,
        "kb_context_estimated_tokens": artifact.kb_context_estimated_tokens,
        "production_latency_ms": artifact.production_latency_ms,
        "grounded_prep_ms": artifact.grounded_prep_ms,
        "grounded_latency_ms": artifact.grounded_latency_ms,
        "source_trace": {
            k: v
            for k, v in (artifact.source_trace or {}).items()
            if k != "citations"
        },
        "citation_ready_count": (artifact.source_trace or {}).get("citation_ready_count", 0),
        "json_path": str(json_path),
        "export_path": str(export_path) if export_path else None,
        "compare_store_enabled": is_compare_store_enabled() or bool(database),
        "compare_store_run_id": store_run_id,
        "compare_store_error": store_error,
        "compare_store_flag": COMPARE_STORE_FLAG,
        "next_steps": [
            f"python -m textus_kb review-show {artifact.run_id}",
            f"python -m textus_kb review-sources {artifact.run_id}",
            f"python -m textus_kb review-rate {artifact.run_id} --overall ...",
            f"python -m textus_kb review-show {artifact.run_id} --reveal",
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True, sort_keys=True))
    print()
    print(format_compare_report(artifact, reveal_mapping=not blind))
    return 0 if artifact.production_output else 1


def main_review_list(argv: list[str] | None = None) -> int:
    import sys

    from textus_kb.compare_store import list_compare_runs

    args = argv if argv is not None else sys.argv[1:]
    database = None
    limit = 50
    i = 0
    while i < len(args):
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
            continue
        i += 1
    rows = list_compare_runs(database_path=database, limit=limit)
    print(json.dumps(rows, indent=2, ensure_ascii=True))
    return 0


def main_review_show(argv: list[str] | None = None) -> int:
    import sys

    from textus_kb.compare_store import load_compare_run

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m textus_kb review-show <run_id> [--reveal] [--database PATH]", file=sys.stderr)
        return 2
    run_id = args[0]
    reveal = False
    database = None
    i = 1
    while i < len(args):
        if args[i] == "--reveal":
            reveal = True
            i += 1
            continue
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        i += 1
    artifact = load_compare_run(run_id, database_path=database)
    if artifact is None:
        print(f"Run not found: {run_id}", file=sys.stderr)
        return 1
    print(format_compare_report(artifact, reveal_mapping=reveal or not artifact.get("blind")))
    return 0


def main_review_rate(argv: list[str] | None = None) -> int:
    import sys

    from textus_kb.compare_store import load_compare_run, update_compare_review

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            "Usage: python -m textus_kb review-rate <run_id> "
            "[--overall A|B|equal|unclear] "
            "[--factual ...] [--exegetical ...] [--historical ...] [--clarity ...] "
            "[--hallucination A|B|both|neither|unclear] [--notes TEXT] [--database PATH]",
            file=sys.stderr,
        )
        return 2
    run_id = args[0]
    database = None
    fields: dict[str, str] = {}
    i = 1
    while i < len(args):
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        if args[i] == "--overall" and i + 1 < len(args):
            fields["overall_preference"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--factual" and i + 1 < len(args):
            fields["factual_accuracy_preference"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--exegetical" and i + 1 < len(args):
            fields["exegetical_usefulness_preference"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--historical" and i + 1 < len(args):
            fields["historical_grounding_preference"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--clarity" and i + 1 < len(args):
            fields["clarity_style_preference"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--hallucination" and i + 1 < len(args):
            fields["hallucination_risk"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--notes" and i + 1 < len(args):
            fields["reviewer_notes"] = args[i + 1]
            i += 2
            continue
        i += 1

    existing = load_compare_run(run_id, database_path=database)
    if existing is None:
        print(f"Run not found: {run_id}", file=sys.stderr)
        return 1
    review = HumanReview.from_dict(existing.get("review"))
    merged = {**review.to_dict(), **fields}
    merged["review_updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        updated = update_compare_review(run_id, merged, database_path=database)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(updated.get("review") if updated else merged, indent=2, ensure_ascii=True))
    return 0


def main_review_sources(argv: list[str] | None = None) -> int:
    import sys

    from textus_kb.compare_store import load_compare_run

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            "Usage: python -m textus_kb review-sources <run_id> [--database PATH]",
            file=sys.stderr,
        )
        return 2
    run_id = args[0]
    database = None
    i = 1
    while i < len(args):
        if args[i] == "--database" and i + 1 < len(args):
            database = args[i + 1]
            i += 2
            continue
        i += 1
    artifact = load_compare_run(run_id, database_path=database)
    if artifact is None:
        print(f"Run not found: {run_id}", file=sys.stderr)
        return 1
    print(format_source_trace_report(artifact))
    return 0


__all__ = [
    "BENCHMARK_MODULES",
    "BENCHMARK_PASSAGES",
    "DEFAULT_COMPARE_DIR",
    "GroundedCompareArtifact",
    "build_source_trace",
    "format_compare_report",
    "format_source_trace_report",
    "main",
    "main_review_list",
    "main_review_rate",
    "main_review_show",
    "main_review_sources",
    "run_grounded_compare",
    "save_compare_export",
]
