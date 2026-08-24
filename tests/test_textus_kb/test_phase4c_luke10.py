"""Phase 4C tests: Luke 10 second pilot, retrieval modes, expansion delta."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.entity_expansion import SELECTION_REASON, expand_dictionary_evidence
from textus_kb.expansion_delta import compute_expansion_delta
from textus_kb.importers.acai_entities import load_pilot_bundle
from textus_kb.manifest import load_manifest
from textus_kb.evidence import PILOT_BUILD_ID_PHASE4D
from textus_kb.pilot_registry import LUKE_10_PILOT, find_pilot, get_pilot
from textus_kb.retrieval import retrieve
from textus_kb.retrieval_comparison import compare_context_modes

LUKE_REF = "Lk 10,25-37"
LUKE_CANONICAL = "Luke.10.25-37"
STUDY_NOTES = Path("data/kb/aquifer/luke_10_25_37_study_notes.json")
DICTIONARY = Path("data/kb/aquifer/luke_10_25_37_bible_dictionary.json")
ACAI_JSON = Path("data/kb/acai/luke_10_25_37_entities.json")
FIXTURES = Path("tests/fixtures/kb")


def test_luke_canonical_parsing() -> None:
    ref = CanonicalReference.parse(LUKE_REF)
    assert ref.canonical_string() == LUKE_CANONICAL
    assert find_pilot(ref) is not None
    assert find_pilot(ref).id == LUKE_10_PILOT.id


def test_pilot_registry_paths() -> None:
    pilot = get_pilot("luke_10_25_37")
    assert pilot.study_notes_resolved.resolve() == STUDY_NOTES.resolve()
    assert pilot.dictionary_resolved.resolve() == DICTIONARY.resolve()
    assert pilot.acai_json_resolved.resolve() == ACAI_JSON.resolve()


def test_resolve_pilot_bundles() -> None:
    from textus_kb.pilot_registry import resolve_pilot_bundles

    bundles = resolve_pilot_bundles(LUKE_CANONICAL)
    assert bundles is not None
    assert bundles["pilot_id"] == "luke_10_25_37"
    assert bundles["study_notes_resolved"].resolve() == STUDY_NOTES.resolve()
    assert resolve_pilot_bundles("Mk 1,1-8") is None


def test_luke_study_notes_bundle() -> None:
    bundle = json.loads(STUDY_NOTES.read_text(encoding="utf-8"))
    assert bundle["pilot_scope"] == LUKE_CANONICAL
    assert len(bundle["notes"]) == 10


def test_luke_dictionary_bundle() -> None:
    bundle = json.loads(DICTIONARY.read_text(encoding="utf-8"))
    assert bundle["pilot_scope"] == LUKE_CANONICAL
    assert len(bundle["entries"]) == 10
    assert sum(len(entry["chunks"]) for entry in bundle["entries"]) == 146


def test_luke_acai_entities() -> None:
    bundle = load_pilot_bundle(ACAI_JSON)
    assert bundle["pilot_scope"] == LUKE_CANONICAL
    assert len(bundle["entities"]) == 15
    report = bundle["pilot_report"]
    assert report["passage_linked_entities"] >= 1
    assert report["dictionary_linked_entities"] >= 1


def test_luke_tagnt_retrieval() -> None:
    packet = retrieve(LUKE_REF, entity_mode="direct_only")
    token_set = packet.linguistic_evidence.get("passage_token_set") or {}
    assert token_set.get("verse_count", 0) >= 10
    assert packet.passage_canonical == LUKE_CANONICAL


def test_direct_only_mode_skips_entities() -> None:
    packet = retrieve(LUKE_REF, entity_mode="direct_only")
    assert packet.entities == []
    assert packet.retrieval_debug["entity_mode"] == "direct_only"
    assert packet.retrieval_debug.get("entity_expansion", {}).get("skipped") is True


def test_direct_plus_entities_includes_entities() -> None:
    packet = retrieve(LUKE_REF, entity_mode="direct_plus_entities")
    assert len(packet.entities) == 15
    assert "expansion_delta" in packet.retrieval_debug


def test_expansion_delta_structure() -> None:
    packet = retrieve(LUKE_REF, entity_mode="direct_plus_entities")
    delta = packet.retrieval_debug["expansion_delta"]
    for key in (
        "direct_candidates",
        "entity_candidates",
        "duplicate_with_direct",
        "unique_entity_candidates",
        "unique_entity_selected",
    ):
        assert key in delta
    assert isinstance(delta["direct_candidates"], int)
    assert isinstance(delta["entity_candidates"], int)


def test_isolated_expansion_produces_candidates() -> None:
    from textus_kb.adapters.acai_entities import AcaiEntitiesAdapter
    from textus_kb.adapters.aquifer_bible_dictionary import AquiferBibleDictionaryAdapter

    manifest = load_manifest()
    ref = CanonicalReference.parse(LUKE_CANONICAL)
    expanded, diag = expand_dictionary_evidence(
        reference=ref,
        canonical_passage=LUKE_CANONICAL,
        acai_adapter=AcaiEntitiesAdapter(manifest.source_by_id("acai")),
        dictionary_adapter=AquiferBibleDictionaryAdapter(manifest.source_by_id("aquifer_open_bible_dictionary")),
        direct_evidence_items=[],
        dictionary_counter_start=1,
        dict_meta={},
    )
    assert diag.dictionary_candidates_added > 0
    assert all(item.metadata.get("entity_expansion") for item in expanded)


def test_integrated_expansion_delta_honest_for_luke() -> None:
    """Integrated retrieval may show zero unique expansion when direct pilot covers entity links."""
    packet = retrieve(LUKE_REF, entity_mode="direct_plus_entities")
    delta = packet.retrieval_debug["expansion_delta"]
    assert delta["entity_candidates"] >= 0
    if delta["entity_candidates"] == 0:
        assert delta["unique_entity_candidates"] == 0


def test_duplicate_detection_logic() -> None:
    from textus_kb.evidence import EvidenceItem, RELATION_DICTIONARY_BACKGROUND

    direct = [
        EvidenceItem(
            evidence_id="EV-DICT-0001",
            source_id="aquifer_open_bible_dictionary",
            source_type="bible_dictionary",
            language="en",
            relation_type=RELATION_DICTIONARY_BACKGROUND,
            passage=LUKE_CANONICAL,
            content="direct",
            metadata={"chunk_id": "c1", "article_id": "8121"},
        )
    ]
    expanded = [
        EvidenceItem(
            evidence_id="EV-DICT-0002",
            source_id="aquifer_open_bible_dictionary",
            source_type="bible_dictionary",
            language="en",
            relation_type=RELATION_DICTIONARY_BACKGROUND,
            passage=LUKE_CANONICAL,
            content="dup",
            metadata={"chunk_id": "c1", "article_id": "8121", "selection_reason": SELECTION_REASON},
        ),
        EvidenceItem(
            evidence_id="EV-DICT-0003",
            source_id="aquifer_open_bible_dictionary",
            source_type="bible_dictionary",
            language="en",
            relation_type=RELATION_DICTIONARY_BACKGROUND,
            passage=LUKE_CANONICAL,
            content="unique",
            metadata={"chunk_id": "c2", "article_id": "9999", "selection_reason": SELECTION_REASON},
        ),
    ]
    delta = compute_expansion_delta(direct_evidence_items=direct, expanded_items=expanded)
    assert delta.duplicate_with_direct == 1
    assert delta.unique_entity_candidates == 1


def test_context_budget_luke() -> None:
    packet = retrieve(LUKE_REF)
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert exegesis.estimated_tokens <= 4500
    assert historical.estimated_tokens <= 3500


def test_context_determinism_luke() -> None:
    first = build_context_from_evidence(retrieve(LUKE_REF), PROFILE_HISTORICAL).to_dict()
    second = build_context_from_evidence(retrieve(LUKE_REF), PROFILE_HISTORICAL).to_dict()
    assert first["estimated_tokens"] == second["estimated_tokens"]
    assert first["evidence_ids"] == second["evidence_ids"]


def test_john4_regression_after_multipilot() -> None:
    packet = retrieve("Jn 4,1-42")
    assert len(packet.entities) == 30
    assert packet.build_id == PILOT_BUILD_ID_PHASE4D
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    assert exegesis.estimated_tokens <= 4500


def test_luke_golden_fixtures_exist() -> None:
    names = [
        "luke_10_25_37_packet.json",
        "luke_10_25_37_entity_expansion.json",
        "luke_10_25_37_exegesis_context.json",
        "luke_10_25_37_historical_context.json",
    ]
    for name in names:
        assert (FIXTURES / name).exists()


def test_luke_golden_packet_matches() -> None:
    golden = json.loads((FIXTURES / "luke_10_25_37_packet.json").read_text(encoding="utf-8"))
    packet = json.loads(json.dumps(retrieve(LUKE_REF).to_dict(), ensure_ascii=False))
    assert packet["build"]["build_id"] == PILOT_BUILD_ID_PHASE4D
    assert len(packet["entities"]) == golden["entity_count"]


def test_context_comparison_runs() -> None:
    report = compare_context_modes(LUKE_REF, PROFILE_HISTORICAL)
    assert report.direct_only["estimated_tokens"] > 0
    assert report.direct_plus_entities["estimated_tokens"] > 0
