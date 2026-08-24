"""Phase 4E: full ACAI SQLite runtime tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from textus_kb.adapters.acai_entities import AcaiEntitiesAdapter
from textus_kb.canonical_reference import CanonicalReference
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.evidence import PILOT_BUILD_ID_PHASE4E
from textus_kb.health import run_health_check
from textus_kb.importers.acai_entities import (
    ACAI_SOURCE_ID,
    UNRESOLVED_CROSSWALK_PLACE_IDS,
    _collect_org_refs,
    _load_acai_record,
    load_pilot_bundle,
    resolve_upstream_path,
    textus_entity_id_from_acai,
)
from textus_kb.importers.acai_sqlite import DEFAULT_DATABASE_PATH, validate_acai_database
from textus_kb.manifest import load_manifest
from textus_kb.pilot_registry import JOHN_4_PILOT, LUKE_10_PILOT, find_pilot, org_ref_bounds
from textus_kb.repositories.acai_entity_repository import AcaiEntityRepository
from textus_kb.retrieval import retrieve

JOHN_JSON = Path("data/kb/acai/john_4_1_42_entities.json")
PILOT_JSON = JOHN_JSON
LUKE_JSON = Path("data/kb/acai/luke_10_25_37_entities.json")
ACTS_PASSAGE = "Acts.2.1-13"
FOURTH_PASSAGE = "Rom.8.28-30"
OT_ACAI_PASSAGE = "Gen.1.1-5"


def test_full_acai_store_is_runtime_primary() -> None:
    assert DEFAULT_DATABASE_PATH.is_file()
    validation = validate_acai_database(DEFAULT_DATABASE_PATH)
    meta = {
        row[0]: row[1]
        for row in __import__("sqlite3")
        .connect(DEFAULT_DATABASE_PATH)
        .execute("SELECT key, value FROM store_metadata")
    }
    assert meta.get("import_mode") == "full"
    assert validation.entity_count > 5000


def test_manifest_acai_points_to_full_store() -> None:
    source = load_manifest().source_by_id("acai")
    assert source is not None
    assert source.resolved_path == DEFAULT_DATABASE_PATH.resolve()


def test_adapter_uses_full_sqlite_runtime() -> None:
    adapter = AcaiEntitiesAdapter(load_manifest().source_by_id("acai"))
    assert adapter.backend == "sqlite"
    assert adapter.uses_full_sqlite_runtime is True


def test_john4_org_ref_pilot_entities_present_in_full_store() -> None:
    bundle = load_pilot_bundle(JOHN_JSON)
    repo = AcaiEntityRepository(DEFAULT_DATABASE_PATH)
    lo, hi = org_ref_bounds(JOHN_4_PILOT.reference())
    root = resolve_upstream_path()
    expected_ids: set[str] = set()
    for item in bundle["entities"]:
        ext = item["external_ids"]["acai"]
        record = _load_acai_record(root, ext)
        refs = _collect_org_refs(record or {})
        if any(lo <= ref <= hi for ref in refs):
            expected_ids.add(item["entity_id"])
    sqlite_ids = {e.entity_id for e in repo.entities_for_passage(JOHN_4_PILOT.canonical)}
    assert expected_ids.issubset(sqlite_ids)


def test_luke10_org_ref_pilot_entities_present_in_full_store() -> None:
    bundle = load_pilot_bundle(LUKE_JSON)
    repo = AcaiEntityRepository(DEFAULT_DATABASE_PATH)
    lo, hi = org_ref_bounds(LUKE_10_PILOT.reference())
    root = resolve_upstream_path()
    expected_ids: set[str] = set()
    for item in bundle["entities"]:
        ext = item["external_ids"]["acai"]
        record = _load_acai_record(root, ext)
        refs = _collect_org_refs(record or {})
        if any(lo <= ref <= hi for ref in refs):
            expected_ids.add(item["entity_id"])
    sqlite_ids = {e.entity_id for e in repo.entities_for_passage(LUKE_10_PILOT.canonical)}
    assert expected_ids.issubset(sqlite_ids)


def test_stable_entity_ids_match_pilot_fixture() -> None:
    bundle = load_pilot_bundle(JOHN_JSON)
    for item in bundle["entities"]:
        ext = item["external_ids"]["acai"]
        assert item["entity_id"] == textus_entity_id_from_acai(ext)


def test_acts2_without_pilot_registry() -> None:
    assert find_pilot(ACTS_PASSAGE) is None
    packet = retrieve(ACTS_PASSAGE)
    assert packet.build_id == PILOT_BUILD_ID_PHASE4E
    assert len(packet.entities) > 0
    debug = packet.retrieval_debug
    assert debug["passage_entity_count"] > 0
    assert debug["entity_types"]


def test_fourth_passage_without_registry() -> None:
    assert find_pilot(FOURTH_PASSAGE) is None
    packet = retrieve(FOURTH_PASSAGE)
    assert packet.build_id == PILOT_BUILD_ID_PHASE4E
    assert len(packet.entities) >= 1
    assert all(entity.get("passage_relations") for entity in packet.entities)


def test_ot_acai_passage_lookup_via_repository() -> None:
    assert find_pilot(OT_ACAI_PASSAGE) is None
    repo = AcaiEntityRepository(DEFAULT_DATABASE_PATH)
    entities = repo.entities_for_passage(OT_ACAI_PASSAGE)
    assert len(entities) >= 1
    assert all(entity.passage_relations for entity in entities)


def test_full_runtime_prefers_sqlite_over_pilot_json() -> None:
    manifest = load_manifest()
    adapter = AcaiEntitiesAdapter(manifest.source_by_id(ACAI_SOURCE_ID))
    assert adapter.uses_full_sqlite_runtime
    assert PILOT_JSON.is_file()
    ref = CanonicalReference.parse("John.4.1-42")
    pilot_count = len(load_pilot_bundle(PILOT_JSON)["entities"])
    runtime_count = len(adapter.entities_for_evidence_packet(ref))
    assert runtime_count != pilot_count


def test_unresolved_crosswalk_not_auto_linked() -> None:
    from textus_kb.adapters.acai_entities import entity_to_packet_dict

    adapter = AcaiEntitiesAdapter(load_manifest().source_by_id("acai"))
    linked = {
        str(entity.get("place_crosswalk", {}).get("textus_place_id"))
        for entity in map(
            entity_to_packet_dict,
            adapter.entities_for_passage(JOHN_4_PILOT.reference()),
        )
        if entity.get("place_crosswalk")
    }
    for place_id in UNRESOLVED_CROSSWALK_PLACE_IDS:
        assert place_id not in linked


def test_entity_context_budget() -> None:
    packet = retrieve("Jn 4,1-42")
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert exegesis.estimated_tokens <= 4500
    assert historical.estimated_tokens <= 3500
    entity_sections = [
        item
        for section in exegesis.sections
        if section.type == "entities"
        for item in section.items
    ]
    assert entity_sections
    assert all("explicitly referenced" in item.text or "dictionary-linked" in item.text for item in entity_sections[:3])


def test_health_full_acai_store() -> None:
    report = run_health_check()
    assert report.acai_store is not None
    assert report.acai_store.store_available is True
    assert report.acai_store.import_mode == "full"
    assert report.acai_store.entity_count > 5000
    assert report.acai_store.external_id_count > 0
    assert report.acai_store.database_path_bytes > 0


def test_passage_lookup_performance_smoke() -> None:
    repo = AcaiEntityRepository(DEFAULT_DATABASE_PATH)
    for ref in (JOHN_4_PILOT.canonical, LUKE_10_PILOT.canonical, ACTS_PASSAGE, FOURTH_PASSAGE):
        t0 = time.perf_counter()
        repo.entities_for_passage(ref)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        assert elapsed_ms < 3000
