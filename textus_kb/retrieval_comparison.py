"""Compare direct-only vs entity-expanded context packets for a pilot passage."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.expansion_delta import ExpansionDelta, apply_selected_entity_evidence
from textus_kb.retrieval import retrieve


@dataclass
class ContextComparisonReport:
    reference: str
    canonical: str
    profile: str
    direct_only: dict[str, Any] = field(default_factory=dict)
    direct_plus_entities: dict[str, Any] = field(default_factory=dict)
    delta: dict[str, Any] = field(default_factory=dict)
    timing_ms: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "canonical": self.canonical,
            "profile": self.profile,
            "direct_only": dict(self.direct_only),
            "direct_plus_entities": dict(self.direct_plus_entities),
            "delta": dict(self.delta),
            "timing_ms": dict(self.timing_ms),
        }


def compare_context_modes(reference: str, profile: str) -> ContextComparisonReport:
    started = time.perf_counter()
    direct_packet = retrieve(reference, entity_mode="direct_only")
    direct_retrieval_ms = int((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    expanded_packet = retrieve(reference, entity_mode="direct_plus_entities")
    expanded_retrieval_ms = int((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    direct_context = build_context_from_evidence(direct_packet, profile)
    direct_context_ms = int((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    expanded_context = build_context_from_evidence(expanded_packet, profile)
    expanded_context_ms = int((time.perf_counter() - started) * 1000)

    canonical = direct_packet.passage_canonical
    direct_ids = set(direct_context.evidence_ids)
    expanded_ids = set(expanded_context.evidence_ids)
    unique_added = sorted(expanded_ids - direct_ids)

    expansion_delta_raw = dict(expanded_packet.retrieval_debug.get("expansion_delta") or {})
    unique_entity_ids = set(expansion_delta_raw.get("unique_entity_evidence_ids") or [])
    entity_selected = [eid for eid in expanded_context.evidence_ids if eid in unique_entity_ids]

    if expansion_delta_raw:
        delta_obj = ExpansionDelta(
            direct_candidates=int(expansion_delta_raw.get("direct_candidates") or 0),
            entity_candidates=int(expansion_delta_raw.get("entity_candidates") or 0),
            duplicate_with_direct=int(expansion_delta_raw.get("duplicate_with_direct") or 0),
            unique_entity_candidates=int(expansion_delta_raw.get("unique_entity_candidates") or 0),
            direct_evidence_ids=list(expansion_delta_raw.get("direct_evidence_ids") or []),
            unique_entity_evidence_ids=list(expansion_delta_raw.get("unique_entity_evidence_ids") or []),
            entity_provenance=list(expansion_delta_raw.get("entity_provenance") or []),
        )
        expansion_delta = apply_selected_entity_evidence(delta_obj, set(entity_selected)).to_dict()
    else:
        expansion_delta = expansion_delta_raw

    provenance_selected = [
        item
        for item in (expansion_delta.get("entity_provenance") or [])
        if any(eid in unique_added for eid in entity_selected)
    ]

    return ContextComparisonReport(
        reference=reference,
        canonical=canonical,
        profile=profile,
        direct_only={
            "evidence_item_count": len(direct_packet.evidence_items),
            "estimated_tokens": direct_context.estimated_tokens,
            "source_ids": direct_context.source_ids,
            "evidence_ids": direct_context.evidence_ids,
        },
        direct_plus_entities={
            "evidence_item_count": len(expanded_packet.evidence_items),
            "estimated_tokens": expanded_context.estimated_tokens,
            "source_ids": expanded_context.source_ids,
            "evidence_ids": expanded_context.evidence_ids,
            "expansion_delta": expansion_delta,
        },
        delta={
            "unique_added_evidence_ids": unique_added,
            "token_delta": expanded_context.estimated_tokens - direct_context.estimated_tokens,
            "entity_selected_in_context": entity_selected,
            "entity_provenance_selected": provenance_selected,
        },
        timing_ms={
            "direct_retrieval": direct_retrieval_ms,
            "expanded_retrieval": expanded_retrieval_ms,
            "direct_context_build": direct_context_ms,
            "expanded_context_build": expanded_context_ms,
        },
    )


def compare_profiles(reference: str) -> dict[str, Any]:
    return {
        "exegesis": compare_context_modes(reference, PROFILE_EXEGESIS).to_dict(),
        "historical_context": compare_context_modes(reference, PROFILE_HISTORICAL).to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print('Usage: python -m textus_kb.retrieval_comparison "Lk 10,25-37"', file=sys.stderr)
        return 2
    reference = " ".join(args).strip()
    print(json.dumps(compare_profiles(reference), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
