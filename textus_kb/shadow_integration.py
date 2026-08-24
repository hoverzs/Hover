"""Production-safe section generation with optional grounded prompt + shadow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from textus_kb.grounded_generation import (
    STATUS_DISABLED,
    STATUS_UNSUPPORTED,
    build_shadow_artifact_from_preparation,
    prepare_grounded_provider_prompt,
    resolve_grounded_module,
)


@dataclass(frozen=True)
class SectionRunResult:
    production_output: str
    generation_duration_ms: int
    shadow_event: dict[str, Any] | None
    grounded_event: dict[str, Any] | None = None
    provider_call_count: int = 1
    provider_prompt_kind: str = "production"  # production | grounded


def run_production_with_optional_shadow(
    *,
    key: str,
    prompt: str,
    tab_label: str,
    use_search: bool,
    passage: str,
    shadow_enabled: bool,
    generate_text_fn: Callable[..., str],
    shadow_runner_fn: Callable[..., dict[str, Any]],
    grounded_enabled: bool = False,
) -> SectionRunResult:
    """Run section generation with optional grounded injection and shadow.

    Guarantees:
    - exactly one production model call per invocation (no grounded-then-retry
      double call on prep failure);
    - when ``grounded_enabled`` is False, provider receives ``prompt`` unchanged
      (Phase 5A/5C production invariance);
    - grounded/shadow failures never raise to the caller.
    """
    module = resolve_grounded_module(key)
    prep = None
    provider_prompt = prompt
    provider_prompt_kind = "production"
    grounded_event: dict[str, Any] | None = None

    if grounded_enabled:
        if module is None:
            from textus_kb.grounded_generation import _unsupported_module

            prep = _unsupported_module(prompt, key=key, passage=passage)
            grounded_event = prep.to_audit_dict()
            grounded_event["provider_call_count"] = 1
        else:
            try:
                prep = prepare_grounded_provider_prompt(
                    production_prompt=prompt,
                    passage=passage,
                    module=module,
                    grounded_enabled=True,
                )
            except Exception as exc:  # pragma: no cover - defensive
                from textus_kb.grounded_generation import _fallback, REASON_COMPOSITION_ERROR

                prep = _fallback(
                    prompt,
                    reason=REASON_COMPOSITION_ERROR,
                    module=module or "",
                    passage=passage,
                    error=f"{type(exc).__name__}",
                )
            provider_prompt = prep.provider_prompt
            provider_prompt_kind = "grounded" if prep.grounded_used else "production"
            grounded_event = prep.to_audit_dict()
            grounded_event["provider_call_count"] = 1
    else:
        grounded_event = {
            "grounded_status": STATUS_DISABLED,
            "grounded_flag_enabled": False,
            "grounded_used": False,
            "grounded_fallback": False,
            "grounded_disabled": True,
            "provider_call_count": 1,
        }

    started = time.perf_counter()
    output = generate_text_fn(
        provider_prompt,
        enable_google_search=use_search,
        tab_label=tab_label,
    )
    generation_ms = int((time.perf_counter() - started) * 1000)

    if grounded_event is not None:
        grounded_event["generation_duration_ms"] = generation_ms
        grounded_event["production_output_chars"] = len(output)
        comparison = grounded_event.get("comparison")
        if isinstance(comparison, dict):
            comparison["production_output_chars"] = len(output)
        # Optional audit persistence for grounded runs (store flag gated).
        try:
            from textus_kb.shadow_audit import is_shadow_store_enabled, persist_shadow_audit

            if is_shadow_store_enabled() and prep is not None and not prep.grounded_disabled and not shadow_enabled:
                persist_shadow_audit(
                    {
                        **grounded_event,
                        "generation_duration_ms": generation_ms,
                    }
                )
        except Exception:
            grounded_event["audit_persist_error"] = "persist_failed"

    shadow_event: dict[str, Any] | None = None
    if shadow_enabled:
        shadow_module = module
        if shadow_module is None or not str(passage).strip():
            shadow_event = None
        else:
            try:
                # Reuse grounded prep when we already retrieved/context-built.
                if (
                    prep is not None
                    and prep.context_packet
                    and prep.canonical_passage
                    and prep.status
                    not in {STATUS_DISABLED, STATUS_UNSUPPORTED}
                ):
                    shadow_event = build_shadow_artifact_from_preparation(
                        prep,
                        production_output=output,
                        generation_duration_ms=generation_ms,
                    )
                    try:
                        from textus_kb.prompt_composer import attach_grounded_preview_metrics

                        attach_grounded_preview_metrics(
                            shadow_event, production_prompt=prompt
                        )
                    except Exception as exc:
                        shadow_event["grounded_preview_error"] = f"{type(exc).__name__}: {exc}"
                    try:
                        from textus_kb.shadow_audit import persist_shadow_audit

                        persist_shadow_audit(shadow_event)
                    except Exception as exc:
                        shadow_event["audit_persist_error"] = f"{type(exc).__name__}: {exc}"
                else:
                    shadow_event = shadow_runner_fn(
                        passage=passage,
                        module=shadow_module,
                        production_prompt=prompt,
                        production_output=output,
                        generation_duration_ms=generation_ms,
                    )
            except Exception as exc:  # pragma: no cover
                shadow_event = {
                    "status": "error",
                    "success": False,
                    "module": shadow_module,
                    "passage_input": passage,
                    "error": f"{type(exc).__name__}: {exc}",
                    "generation_duration_ms": generation_ms,
                }

    # When grounded is off, omit grounded_event from result for 5A contract
    # callers that only care about shadow — still expose disabled status for 5D.
    return SectionRunResult(
        production_output=output,
        generation_duration_ms=generation_ms,
        shadow_event=shadow_event,
        grounded_event=grounded_event,
        provider_call_count=1,
        provider_prompt_kind=provider_prompt_kind,
    )
