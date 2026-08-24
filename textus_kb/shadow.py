"""KB shadow-mode retrieval/context artifacts for production-safe integration."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.retrieval import retrieve

MODULE_TO_PROFILE = {
    "exegesis": PROFILE_EXEGESIS,
    "history": PROFILE_HISTORICAL,
    "historical_context": PROFILE_HISTORICAL,
}


@dataclass(frozen=True)
class KBShadowArtifact:
    success: bool
    module: str
    profile: str
    passage_input: str
    passage_canonical: str
    evidence_packet_build_id: str
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    context_packet: dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0
    retrieval_warnings: list[str] = field(default_factory=list)
    retrieval_duration_ms: int = 0
    context_build_duration_ms: int = 0
    evidence_item_count: int = 0
    entity_count: int = 0
    study_notes_count: int = 0
    dictionary_count: int = 0
    selected_context_count: int = 0
    source_count: int = 0
    comparison: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_kb_shadow_for_module(
    passage: str,
    *,
    module: str,
    production_prompt: str = "",
    production_output: str = "",
) -> KBShadowArtifact:
    profile = MODULE_TO_PROFILE.get(module)
    if profile is None:
        return KBShadowArtifact(
            success=False,
            module=module,
            profile="",
            passage_input=passage,
            passage_canonical="",
            evidence_packet_build_id="",
            error=f"Unsupported module for KB shadow: {module!r}",
        )

    try:
        t0 = time.perf_counter()
        evidence = retrieve(passage)
        retrieval_ms = int((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        context = build_context_from_evidence(evidence, profile)
        context_ms = int((time.perf_counter() - t1) * 1000)

        evidence_items = evidence.evidence_items
        study_notes_count = sum(1 for item in evidence_items if item.relation_type == "exegetical_note")
        dictionary_count = sum(
            1 for item in evidence_items if item.relation_type == "dictionary_background"
        )
        selected_context_count = sum(len(section.items) for section in context.sections)
        context_dict = context.to_dict()
        comparison = {
            "production_prompt_chars": len(production_prompt),
            "kb_context_tokens": context.estimated_tokens,
            "production_output_chars": len(production_output),
            "shadow_evidence_coverage": {
                "evidence_item_count": len(evidence_items),
                "study_notes_count": study_notes_count,
                "dictionary_count": dictionary_count,
                "entity_count": len(evidence.entities),
            },
            "source_count": len(context.source_ids),
            "warnings": list(evidence.warnings),
        }
        return KBShadowArtifact(
            success=True,
            module=module,
            profile=profile,
            passage_input=passage,
            passage_canonical=evidence.passage_canonical,
            evidence_packet_build_id=evidence.build_id,
            source_ids=list(context.source_ids),
            evidence_ids=list(context.evidence_ids),
            context_packet=context_dict,
            token_estimate=context.estimated_tokens,
            retrieval_warnings=list(evidence.warnings),
            retrieval_duration_ms=retrieval_ms,
            context_build_duration_ms=context_ms,
            evidence_item_count=len(evidence_items),
            entity_count=len(evidence.entities),
            study_notes_count=study_notes_count,
            dictionary_count=dictionary_count,
            selected_context_count=selected_context_count,
            source_count=len(context.source_ids),
            comparison=comparison,
        )
    except Exception as exc:  # pragma: no cover - exercised through integration tests
        return KBShadowArtifact(
            success=False,
            module=module,
            profile=profile,
            passage_input=passage,
            passage_canonical="",
            evidence_packet_build_id="",
            error=f"{type(exc).__name__}: {exc}",
        )


def build_shadow_benchmark_report(passages: list[str], *, modules: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for passage in passages:
        for module in modules:
            artifact = run_kb_shadow_for_module(passage, module=module)
            rows.append(artifact.to_dict())
    return {"passages": passages, "modules": modules, "artifacts": rows}


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            'Usage: python -m textus_kb shadow "<reference>" --module exegesis|historical_context',
            file=sys.stderr,
        )
        return 2
    passage = args[0]
    module = "exegesis"
    benchmark = False
    i = 1
    while i < len(args):
        if args[i] == "--module" and i + 1 < len(args):
            module = args[i + 1]
            i += 2
            continue
        if args[i] == "--benchmark":
            benchmark = True
            i += 1
            continue
        i += 1

    if benchmark:
        report = build_shadow_benchmark_report(
            ["John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30"],
            modules=["exegesis", "historical_context"],
        )
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0

    artifact = run_kb_shadow_for_module(passage, module=module)
    print(json.dumps(artifact.to_dict(), indent=2, ensure_ascii=True))
    return 0 if artifact.success else 1

