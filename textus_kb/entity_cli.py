"""Entity diagnostic CLI for Knowledge Base."""

from __future__ import annotations

import json
import time
from typing import Any

from textus_kb.adapters.acai_entities import AcaiEntitiesAdapter
from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.entity_expansion import expand_dictionary_evidence
from textus_kb.adapters.aquifer_bible_dictionary import AquiferBibleDictionaryAdapter
from textus_kb.manifest import load_manifest
from textus_kb.retrieval import retrieve


def run_entity_diagnostic(reference: str) -> dict[str, Any]:
    canonical = CanonicalReference.parse(reference)
    manifest = load_manifest()
    acai_source = manifest.source_by_id("acai")
    dict_source = manifest.source_by_id("aquifer_open_bible_dictionary")

    acai_adapter = AcaiEntitiesAdapter(acai_source)
    dict_adapter = AquiferBibleDictionaryAdapter(dict_source)

    started = time.perf_counter()
    passage_entities = acai_adapter.entities_for_passage(canonical)
    lookup_ms = int((time.perf_counter() - started) * 1000)

    all_entities = acai_adapter.entities_for_evidence_packet(canonical)
    type_counts: dict[str, int] = {}
    for entity in all_entities:
        type_counts[entity.entity_type] = type_counts.get(entity.entity_type, 0) + 1

    expansion_started = time.perf_counter()
    expanded, diagnostics = expand_dictionary_evidence(
        reference=canonical,
        canonical_passage=canonical.canonical_string(),
        acai_adapter=acai_adapter,
        dictionary_adapter=dict_adapter,
        direct_evidence_items=[],
        dictionary_counter_start=1,
        dict_meta=dict_adapter.bundle_metadata(),
    )
    expansion_ms = int((time.perf_counter() - expansion_started) * 1000)

    retrieval_started = time.perf_counter()
    packet = retrieve(reference, manifest=manifest)
    retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)

    store_status = acai_adapter.store_status()
    if hasattr(store_status, "to_dict"):
        store_payload = store_status.to_dict()
    else:
        store_payload = store_status

    return {
        "reference": reference,
        "canonical": canonical.canonical_string(),
        "acai_backend": acai_adapter.backend,
        "acai_available": acai_adapter.available,
        "entity_count": len(all_entities),
        "passage_linked_entity_count": len(passage_entities),
        "entity_types": type_counts,
        "entity_ids": [entity.entity_id for entity in all_entities],
        "expansion_candidate_count": len(expanded),
        "entity_expansion": diagnostics.to_dict(),
        "retrieval_debug": packet.retrieval_debug,
        "build_id": packet.build_id,
        "timing_ms": {
            "entity_lookup": lookup_ms,
            "entity_expansion": expansion_ms,
            "full_retrieval": retrieval_ms,
        },
        "store_status": store_payload,
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print('Usage: python -m textus_kb entity "Jn 4,1–42"', file=sys.stderr)
        return 2
    reference = " ".join(args).strip()
    try:
        payload = run_entity_diagnostic(reference)
    except CanonicalReferenceError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
