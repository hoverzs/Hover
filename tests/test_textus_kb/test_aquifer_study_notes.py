"""Tests for Aquifer Open Study Notes Phase 3A pilot integration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from textus_kb.adapters.aquifer_study_notes import AquiferStudyNotesAdapter
from textus_kb.canonical_reference import CanonicalReference
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS
from textus_kb.importers.aquifer_study_notes import (
    AQUIFER_LICENSE,
    AQUIFER_SOURCE_ID,
    import_john_4_pilot,
    index_reference_to_canonical,
    load_pilot_bundle,
)
from textus_kb.manifest import load_manifest
from textus_kb.retrieval import retrieve, retrieve_to_json

PILOT_BUNDLE = Path("data/kb/aquifer/john_4_1_42_study_notes.json")
PACKET_WITH_AQUIFER = Path("tests/fixtures/kb/john_4_1_42_packet_with_aquifer.json")
EXEGESIS_PHASE3A = Path("tests/fixtures/kb/john_4_1_42_exegesis_context_phase3a.json")


def test_aquifer_manifest_source_valid() -> None:
    manifest = load_manifest()
    source = manifest.source_by_id(AQUIFER_SOURCE_ID)
    assert source is not None
    assert source.license == "CC-BY-SA-4.0"
    assert source.source_type == "exegetical_notes"
    assert source.language == "en"
    assert source.enabled is True
    assert source.required is False


def test_pilot_bundle_preserves_license_and_provenance() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    assert bundle["license"] == AQUIFER_LICENSE
    assert bundle["source_id"] == AQUIFER_SOURCE_ID
    assert bundle["upstream_commit"]
    assert bundle["attribution"]
    note = bundle["notes"][0]
    assert note["content_html"]
    assert note["license"] == AQUIFER_LICENSE
    assert note["attribution"]


def test_john_4_notes_imported() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    assert bundle["pilot_scope"] == "John.4.1-42"
    assert len(bundle["notes"]) == 24


def test_non_john4_note_excluded_from_pilot_bundle() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    for note in bundle["notes"]:
        canonical = note["canonical_reference"]
        ref = CanonicalReference.parse(canonical)
        assert ref.book_id == "John"
        assert ref.start_chapter == 4
        assert not (
            ref.end_chapter < 4
            or ref.start_chapter > 4
            or ref.end_verse < 1
            or ref.start_verse > 42
        )


def test_canonical_mapping_from_index_reference() -> None:
    assert index_reference_to_canonical("43004010") == "John.4.10"
    assert index_reference_to_canonical("43004001-43004042") == "John.4.1-42"


def test_invalid_mapping_skipped_during_import(tmp_path: Path) -> None:
    result = import_john_4_pilot(
        upstream_root=Path("_upstream_audit/AquiferOpenStudyNotes"),
        output_path=tmp_path / "out.json",
    )
    assert result.note_count == 24
    assert not any(issue.level == "error" for issue in result.issues)


def test_original_english_content_unchanged() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    adapter_source = load_manifest().source_by_id(AQUIFER_SOURCE_ID)
    adapter = AquiferStudyNotesAdapter(adapter_source)
    chunks = adapter.load_chunks_for_passage(CanonicalReference.parse("John.4.10"))
    note = next(item for item in bundle["notes"] if item["article_id"] == "19124")
    chunk = next(item for item in chunks if item.article_id == "19124")
    assert note["content_html"] in chunk.content_html or chunk.content_html in note["content_html"]
    assert "gift" in chunk.content_plain.lower() or "living water" in chunk.content_plain.lower() or len(chunk.content_plain) > 20


def test_retrieval_includes_aquifer_evidence_deterministically() -> None:
    first = json.loads(retrieve_to_json("Jn 4,1-42"))
    second = json.loads(retrieve_to_json("Jn 4,1-42"))
    assert first == second
    aquifer_items = [
        item
        for item in first["evidence_items"]
        if item["relation_type"] == "exegetical_note"
    ]
    assert len(aquifer_items) == 24
    assert first["build"]["build_id"] == "kb-phase4b-john4-pilot-v1"


def test_evidence_ids_unique_and_stable() -> None:
    packet = retrieve("Jn 4,1-42")
    ids = [item.evidence_id for item in packet.evidence_items if item.relation_type == "exegetical_note"]
    assert len(ids) == len(set(ids))
    assert ids[0].startswith("EV-AQUIFER-")


def test_disabled_aquifer_source_graceful(phase2a_manifest) -> None:
    packet = retrieve("Jn 4,1-42", manifest=phase2a_manifest)
    assert not any(item.relation_type == "exegetical_note" for item in packet.evidence_items)
    assert any("aquifer_open_study_notes is disabled" in w for w in packet.warnings)
    assert packet.build_id == "kb-phase2a-john4-pilot-v1"


def test_missing_pilot_bundle_graceful(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    payload = deepcopy(base)
    for source in payload["sources"]:
        if source["id"] == AQUIFER_SOURCE_ID:
            source["local_path"] = "data/kb/aquifer/missing_bundle.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    packet = retrieve("Jn 4,1-42", manifest=manifest)
    assert not any(item.relation_type == "exegetical_note" for item in packet.evidence_items)
    assert any("pilot bundle missing" in w for w in packet.warnings)


def test_exegesis_context_includes_provenance() -> None:
    packet = retrieve("Jn 4,1-42")
    context = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    exegetical = [
        item
        for section in context.sections
        if section.type == "exegetical"
        for item in section.items
    ]
    assert exegetical
    assert all(item.source_id == AQUIFER_SOURCE_ID for item in exegetical)
    assert all(item.evidence_id.startswith("EV-AQUIFER-") for item in exegetical)
    evidence_ids = {item.evidence_id for item in packet.evidence_items}
    for item in exegetical:
        assert item.evidence_id in evidence_ids


def test_exegesis_context_token_budget() -> None:
    packet = retrieve("Jn 4,1-42")
    context = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    assert context.estimated_tokens <= context.token_budget


def test_matches_phase3a_golden_fixtures() -> None:
    """Study Notes evidence count remains Phase 3A; build id bumps when dictionary is enabled."""
    if not PACKET_WITH_AQUIFER.exists():
        pytest.skip("Phase 3A golden fixtures not generated yet.")
    golden_packet = json.loads(PACKET_WITH_AQUIFER.read_text(encoding="utf-8"))
    packet = json.loads(retrieve_to_json("Jn 4,1-42"))
    aquifer_count = sum(
        1 for item in packet["evidence_items"] if item["relation_type"] == "exegetical_note"
    )
    assert aquifer_count == golden_packet["aquifer_evidence_count"]

    context = build_context_from_evidence(retrieve("Jn 4,1-42"), PROFILE_EXEGESIS).to_dict()
    assert "exegetical" in {section["type"] for section in context["sections"]}
    assert context["schema_version"] == "2"
    assert context["selection_stats"]["study_notes_selected"] < aquifer_count
    assert context["estimated_tokens"] <= context["max_tokens"]
