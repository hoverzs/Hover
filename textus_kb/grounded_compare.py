"""Dev-only A/B compare: production prompt vs KB-grounded prompt.

Default mode uses a mock generate function (no API cost).
Pass ``--live`` only when an explicit live provider callback is wired by the caller.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from textus_kb.grounded_generation import prepare_grounded_provider_prompt
from textus_kb.paths import GENERATED_DATA_DIR
from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB
from textus_kb.shadow import MODULE_TO_PROFILE

DEFAULT_COMPARE_DIR = GENERATED_DATA_DIR / "kb_grounded_compare"


@dataclass
class GroundedCompareArtifact:
    passage: str
    module: str
    production_output: str
    grounded_output: str
    production_prompt_chars: int
    grounded_prompt_chars: int
    production_prompt_estimated_tokens: int
    grounded_prompt_estimated_tokens: int
    kb_context_estimated_tokens: int
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    grounded_used: bool = False
    grounded_fallback: bool = False
    fallback_reason: str = ""
    production_latency_ms: int = 0
    grounded_prep_ms: int = 0
    grounded_latency_ms: int = 0
    provider_call_count: int = 2
    composition_version: str = ""
    prompt_hash: str = ""
    model_note: str = "mock"
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_grounded_compare(
    passage: str,
    *,
    module: str,
    production_prompt: str,
    generate_text_fn: Callable[..., str],
    use_search: bool = False,
    tab_label: str = "grounded-compare",
) -> GroundedCompareArtifact:
    """Run two explicit provider calls: A=production, B=grounded (or fallback prompt)."""
    if module not in MODULE_TO_PROFILE and module != "history":
        raise ValueError(f"Unsupported module for grounded-compare: {module!r}")
    module_key = "historical_context" if module == "history" else module

    t0 = time.perf_counter()
    production_output = generate_text_fn(
        production_prompt,
        enable_google_search=use_search,
        tab_label=f"{tab_label}:A",
    )
    production_ms = int((time.perf_counter() - t0) * 1000)

    t1 = time.perf_counter()
    prep = prepare_grounded_provider_prompt(
        production_prompt=production_prompt,
        passage=passage,
        module=module_key,
        grounded_enabled=True,
    )
    prep_ms = int((time.perf_counter() - t1) * 1000)

    t2 = time.perf_counter()
    grounded_output = generate_text_fn(
        prep.provider_prompt,
        enable_google_search=use_search,
        tab_label=f"{tab_label}:B",
    )
    grounded_ms = int((time.perf_counter() - t2) * 1000)

    return GroundedCompareArtifact(
        passage=prep.canonical_passage or passage,
        module=module_key,
        production_output=production_output,
        grounded_output=grounded_output,
        production_prompt_chars=len(production_prompt),
        grounded_prompt_chars=len(prep.provider_prompt),
        production_prompt_estimated_tokens=prep.original_prompt_estimated_tokens
        or max(1, len(production_prompt) // 4),
        grounded_prompt_estimated_tokens=prep.composed_prompt_estimated_tokens
        if prep.grounded_used
        else prep.original_prompt_estimated_tokens,
        kb_context_estimated_tokens=prep.kb_context_estimated_tokens,
        source_ids=list(prep.source_ids),
        evidence_ids=list(prep.evidence_ids),
        grounded_used=prep.grounded_used,
        grounded_fallback=prep.grounded_fallback,
        fallback_reason=prep.fallback_reason,
        production_latency_ms=production_ms,
        grounded_prep_ms=prep_ms,
        grounded_latency_ms=grounded_ms,
        provider_call_count=2,
        composition_version=prep.composition_version,
        prompt_hash=prep.prompt_hash,
        model_note="caller_generate_fn",
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _mock_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
    kind = "grounded" if "BEGIN_KB_DATA" in prompt or "<<<BEGIN_KB_DATA>>>" in prompt else "production"
    return f"[mock:{kind}:{tab_label}] chars={len(prompt)} search={enable_google_search}"


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            'Usage: python -m textus_kb grounded-compare "<reference>" '
            "--module exegesis|historical_context [--live] [--prompt-file PATH] [--out DIR]",
            file=sys.stderr,
        )
        return 2

    passage = args[0]
    module = "exegesis"
    live = False
    prompt_file = None
    out_dir = DEFAULT_COMPARE_DIR
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
        if args[i] == "--prompt-file" and i + 1 < len(args):
            prompt_file = args[i + 1]
            i += 2
            continue
        if args[i] == "--out" and i + 1 < len(args):
            out_dir = Path(args[i + 1])
            i += 2
            continue
        i += 1

    if prompt_file:
        production_prompt = Path(prompt_file).read_text(encoding="utf-8")
    else:
        production_prompt = DRY_RUN_PRODUCTION_STUB

    if live:
        print(
            "ERROR: --live requires an external provider wire-up; "
            "default CLI uses mock generate. Use run_grounded_compare() from a "
            "dev script with generate_text_fn=your_provider.",
            file=sys.stderr,
        )
        return 2

    artifact = run_grounded_compare(
        passage,
        module=module,
        production_prompt=production_prompt,
        generate_text_fn=_mock_generate,
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_passage = artifact.passage.replace(".", "_")
    out_path = out_dir / f"compare_{safe_passage}_{module}.json"
    # Dev-only fixture may include outputs; directory is under data/generated (gitignored sqlite pattern
    # — JSON compare files should also stay local; parent data/generated is partially tracked).
    payload = artifact.to_dict()
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    # Print summary without dumping full long outputs by default
    summary = {
        "passage": artifact.passage,
        "module": artifact.module,
        "grounded_used": artifact.grounded_used,
        "grounded_fallback": artifact.grounded_fallback,
        "fallback_reason": artifact.fallback_reason,
        "production_prompt_chars": artifact.production_prompt_chars,
        "grounded_prompt_chars": artifact.grounded_prompt_chars,
        "kb_context_estimated_tokens": artifact.kb_context_estimated_tokens,
        "source_ids": artifact.source_ids,
        "provider_call_count": artifact.provider_call_count,
        "grounded_prep_ms": artifact.grounded_prep_ms,
        "out_path": str(out_path),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_COMPARE_DIR",
    "GroundedCompareArtifact",
    "main",
    "run_grounded_compare",
]
