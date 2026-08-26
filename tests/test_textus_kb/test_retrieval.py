"""Tests for Phase 2A John 4 retrieval pilot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.evidence import estimate_supplemental_tokens
from textus_kb.manifest import KnowledgeBaseManifest, load_manifest
from textus_kb.retrieval import RetrievalError, retrieve, retrieve_to_json

FIXTURE_PATH = Path("tests/fixtures/kb/john_4_1_42_packet.json")
GOLDEN = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_jn_4_canonical_normalization() -> None:
    ref = CanonicalReference.parse("Jn 4,1–42")
    assert ref.canonical_string() == "John.4.1-42"


def test_retrieval_is_deterministic(phase2a_manifest: KnowledgeBaseManifest) -> None:
    first = retrieve_to_json("Jn 4,1-42", manifest=phase2a_manifest)
    second = retrieve_to_json("Jn 4,1-42", manifest=phase2a_manifest)
    assert first == second


def test_retrieval_matches_golden_fixture_keys(phase2a_manifest: KnowledgeBaseManifest) -> None:
    packet = json.loads(retrieve_to_json("Jn 4,1-42", manifest=phase2a_manifest))
    assert packet["passage"]["canonical"] == GOLDEN["passage"]["canonical"]
    assert packet["passage"]["display"] == GOLDEN["passage"]["display"]
    assert packet["build"]["build_id"] == GOLDEN["build"]["build_id"]
    assert len(packet["places"]) == len(GOLDEN["places"])
    assert {place["place_id"] for place in packet["places"]} == {
        place["place_id"] for place in GOLDEN["places"]
    }


def test_tagnt_evidence_covers_passage() -> None:
    packet = retrieve("Jn 4,1-42")
    token_set = packet.linguistic_evidence["passage_token_set"]
    assert token_set["verse_count"] == 42
    assert token_set["token_count"] == GOLDEN["linguistic_evidence"]["passage_token_set"]["token_count"]
    tagnt_items = [
        item for item in packet.evidence_items if item.source_id == "stepbible_tagnt"
    ]
    assert len(tagnt_items) >= 2
    assert any(item.relation_type == "passage_token" for item in tagnt_items)


def test_passage_place_links_present() -> None:
    packet = retrieve("Jn 4,1-42")
    place_ids = {place.place_id for place in packet.places}
    assert "sychar" in place_ids
    assert "samaria_2" in place_ids
    assert len(place_ids) == 6
    link_items = [
        item
        for item in packet.evidence_items
        if item.relation_type == "passage_place_link"
    ]
    assert len(link_items) == 6


def test_every_evidence_source_in_manifest() -> None:
    manifest = load_manifest()
    manifest_ids = {source.id for source in manifest.sources}
    packet = retrieve("Jn 4,1-42")
    for item in packet.evidence_items:
        assert item.source_id in manifest_ids
    for source in packet.sources:
        assert source["source_id"] in manifest_ids


def test_evidence_ids_are_unique() -> None:
    packet = retrieve("Jn 4,1-42")
    ids = [item.evidence_id for item in packet.evidence_items]
    assert len(ids) == len(set(ids))


def test_disabled_source_excluded_from_packet() -> None:
    manifest = load_manifest()
    disabled_ids = {source.id for source in manifest.sources if not source.enabled}
    packet = retrieve("Jn 4,1-42")
    used_ids = {item.source_id for item in packet.evidence_items}
    assert disabled_ids.isdisjoint(used_ids)
    assert "ruf_2014_local" not in used_ids


def test_token_budget_trims_supplemental_content_when_forced(phase2a_manifest: KnowledgeBaseManifest) -> None:
    from textus_kb.evidence import estimate_trimmable_supplemental_tokens

    full = retrieve("Jn 4,1-42", manifest=phase2a_manifest, max_evidence_tokens=4500)
    trimmed = retrieve("Jn 4,1-42", manifest=phase2a_manifest, max_evidence_tokens=1500)
    assert trimmed.token_budget_applied is True
    assert estimate_trimmable_supplemental_tokens(trimmed) <= 1500
    assert estimate_trimmable_supplemental_tokens(trimmed) < estimate_trimmable_supplemental_tokens(full)
    assert trimmed.linguistic_evidence["passage_token_set"]["token_count"] > 0
    assert any(item.relation_type == "passage_place_link" for item in trimmed.evidence_items)


def test_extreme_token_budget_keeps_passage_and_links() -> None:
    packet = retrieve("Jn 4,1-42", max_evidence_tokens=200)
    assert packet.token_budget_applied is True
    assert packet.linguistic_evidence["passage_token_set"]["token_count"] > 0
    assert any(item.relation_type == "passage_place_link" for item in packet.evidence_items)


def test_provenance_fields_present() -> None:
    packet = retrieve("Jn 4,1-42")
    for item in packet.evidence_items:
        assert item.evidence_id.startswith("EV-")
        assert item.source_id
        assert item.source_type
        assert item.relation_type
        assert item.relevance_score > 0


def test_json_serialization_stable() -> None:
    payload = json.loads(retrieve_to_json("Jn 4,1-42"))
    again = json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    assert payload == again


def test_optional_source_missing_emits_warning(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    for source in base["sources"]:
        if source["id"] == "stepbible_tbesg":
            source["local_path"] = "data/generated/missing_tbesg.sqlite3"
    manifest_path.write_text(json.dumps(base), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    packet = retrieve("Jn 4,1-42", manifest=manifest)
    assert any("stepbible_tbesg" in warning for warning in packet.warnings)
    assert packet.linguistic_evidence["passage_token_set"]["token_count"] > 0


def test_required_source_missing_raises(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    for source in base["sources"]:
        if source["id"] == "stepbible_tagnt":
            source["local_path"] = "data/generated/missing_tagnt.sqlite3"
    manifest_path.write_text(json.dumps(base), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    with pytest.raises(RetrievalError, match="stepbible_tagnt"):
        retrieve("Jn 4,1-42", manifest=manifest)


def test_lexical_highlights_are_limited_not_full_lexicon() -> None:
    packet = retrieve("Jn 4,1-42")
    highlights = packet.linguistic_evidence["lexical_highlights"]
    token_count = packet.linguistic_evidence["passage_token_set"]["token_count"]
    assert len(highlights) <= 12
    assert len(highlights) < token_count


def test_golden_fixture_has_no_ruf_text() -> None:
    serialized = FIXTURE_PATH.read_text(encoding="utf-8").lower()
    assert "ruf_2014" not in serialized
    assert "karoli" not in serialized


def test_cli_retrieve_main_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from textus_kb.retrieval import main

    monkeypatch.setattr("sys.argv", ["retrieve", "Jn 4,1-42"])
    assert main(["Jn 4,1-42"]) == 0
