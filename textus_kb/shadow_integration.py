"""Production-safe shadow hook orchestration for section generation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SectionRunResult:
    production_output: str
    generation_duration_ms: int
    shadow_event: dict[str, Any] | None


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
) -> SectionRunResult:
    """Run production generation first, then optional shadow hook.

    This function guarantees production invariance:
    - same prompt/params regardless of shadow flag;
    - exactly one production model call per invocation;
    - shadow failures are isolated into shadow_event and never raised.
    """
    started = time.perf_counter()
    output = generate_text_fn(
        prompt,
        enable_google_search=use_search,
        tab_label=tab_label,
    )
    generation_ms = int((time.perf_counter() - started) * 1000)

    if not shadow_enabled:
        return SectionRunResult(
            production_output=output,
            generation_duration_ms=generation_ms,
            shadow_event=None,
        )

    module = "exegesis" if key == "exegesis" else "historical_context" if key == "history" else None
    if module is None or not str(passage).strip():
        return SectionRunResult(
            production_output=output,
            generation_duration_ms=generation_ms,
            shadow_event=None,
        )

    try:
        artifact = shadow_runner_fn(
            passage=passage,
            module=module,
            production_prompt=prompt,
            production_output=output,
            generation_duration_ms=generation_ms,
        )
        return SectionRunResult(
            production_output=output,
            generation_duration_ms=generation_ms,
            shadow_event=artifact,
        )
    except Exception as exc:  # pragma: no cover
        return SectionRunResult(
            production_output=output,
            generation_duration_ms=generation_ms,
            shadow_event={
                "status": "error",
                "success": False,
                "module": module,
                "passage_input": passage,
                "error": f"{type(exc).__name__}: {exc}",
                "generation_duration_ms": generation_ms,
            },
        )

