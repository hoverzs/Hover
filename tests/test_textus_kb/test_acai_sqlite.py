"""Tests for ACAI SQLite store, repository, and entity expansion (Phase 4B)."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from textus_kb.adapters.acai_entities import AcaiEntitiesAdapter, entity_to_packet_dict
from textus_kb.canonical_reference import CanonicalReference
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.entity_expansion import (
    MAX_ENTITY_EXPANSION,
    MAX_TOTAL_EXPANSION_CANDIDATES,
    expand_dictionary_evidence,
)
from textus_kb.importers.acai_entities import ACAI_SOURCE_ID, load_pilot_bundle
from textus_kb.importers.acai_sqlite import (
    DEFAULT_DATABASE_PATH,
    create_schema,
    import_acai_sqlite,
    validate_acai_database,
)
from textus_kb.manifest import load_manifest
from textus_kb.repositories.acai_entity_repository import AcaiEntityRepository
from textus_kb.retrieval import retrieve, retrieve_to_json

PILOT_JSON = Path("data/kb/acai/john_4_1_42_entities.json")
PILOT_SQLITE = Path("data/generated/acai_entities.sqlite3")
FULL_SQLITE = Path("data/generated/acai_entities_full.sqlite3")


@pytest.fixture(scope="module")
def pilot_sqlite(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if PILOT_SQLITE.is_file():
        return PILOT_SQLITE
    output = tmp_path_factory.mktemp("acai") / "pilot.sqlite3"
    import_acai_sqlite(database_path=output, mode="pilot")
    return output


def test_sqlite_schema_tables_exist(pilot_sqlite: Path) -> None:
    with sqlite3.connect(pilot_sqlite) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "entities",
        "entity_aliases",
        "entity_passage_links",
        "entity_external_ids",
        "entity_dictionary_links",
        "store_metadata",
    }.issubset(tables)


def test_importer_idempotent(pilot_sqlite: Path, tmp_path: Path) -> None:
    target = tmp_path / "acai.sqlite3"
    first = import_acai_sqlite(database_path=target, mode="pilot")
    second = import_acai_sqlite(database_path=target, mode="pilot")
    assert first.entity_count == second.entity_count
    assert first.content_hash == second.content_hash
    assert first.passage_link_count == second.passage_link_count


def test_pilot_entity_counts(pilot_sqlite: Path) -> None:
    validation = validate_acai_database(pilot_sqlite)
    bundle = load_pilot_bundle(PILOT_JSON)
    assert validation.entity_count == len(bundle["entities"])
    assert validation.entity_count >= 20
    assert validation.passage_link_count > 0
    assert validation.dictionary_link_count > 0
    assert validation.external_id_count > 0


def test_unique_acai_external_ids(pilot_sqlite: Path) -> None:
    with sqlite3.connect(pilot_sqlite) as connection:
        total = connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        distinct = connection.execute("SELECT COUNT(DISTINCT external_id) FROM entities").fetchone()[0]
    assert total == distinct


def test_repository_passage_lookup(pilot_sqlite: Path) -> None:
    repo = AcaiEntityRepository(pilot_sqlite)
    entities = repo.entities_for_passage(CanonicalReference.parse("John.4.1-42"))
    assert entities
    assert any(entity.external_id == "place:Sychar" for entity in entities)


def test_repository_dictionary_and_external_ids(pilot_sqlite: Path) -> None:
    repo = AcaiEntityRepository(pilot_sqlite)
    sychar = next(entity for entity in repo.all_entities() if entity.external_id == "place:Sychar")
    articles = repo.dictionary_articles_for_entity(sychar.entity_id)
    external_ids = repo.external_ids_for_entity(sychar.entity_id)
    assert articles or sychar.dictionary_relations
    assert external_ids or sychar.place_crosswalk


def test_json_sqlite_parity_entity_ids() -> None:
    manifest = load_manifest()
    source = manifest.source_by_id(ACAI_SOURCE_ID)
    adapter = AcaiEntitiesAdapter(source)
    ref = CanonicalReference.parse("John.4.1-42")
    json_ids = sorted(
        item["entity_id"] for item in load_pilot_bundle(PILOT_JSON)["entities"]
    )
    sqlite_ids = sorted(view.entity_id for view in adapter.entities_for_evidence_packet(ref))
    assert json_ids == sqlite_ids


def test_entity_driven_dictionary_expansion() -> None:
    manifest = load_manifest()
    acai = AcaiEntitiesAdapter(manifest.source_by_id(ACAI_SOURCE_ID))
    dictionary = __import__(
        "textus_kb.adapters.aquifer_bible_dictionary",
        fromlist=["AquiferBibleDictionaryAdapter"],
    ).AquiferBibleDictionaryAdapter(manifest.source_by_id("aquifer_open_bible_dictionary"))
    ref = CanonicalReference.parse("John.4.1-42")
    expanded, diagnostics = expand_dictionary_evidence(
        reference=ref,
        canonical_passage=ref.canonical_string(),
        acai_adapter=acai,
        dictionary_adapter=dictionary,
        direct_evidence_items=[],
        dictionary_counter_start=100,
        dict_meta=dictionary.bundle_metadata(),
    )
    assert diagnostics.entities_considered > 0
    assert expanded
    assert any(item.metadata.get("entity_expansion") for item in expanded)


def test_expansion_limits_respected() -> None:
    manifest = load_manifest()
    acai = AcaiEntitiesAdapter(manifest.source_by_id(ACAI_SOURCE_ID))
    dictionary = __import__(
        "textus_kb.adapters.aquifer_bible_dictionary",
        fromlist=["AquiferBibleDictionaryAdapter"],
    ).AquiferBibleDictionaryAdapter(manifest.source_by_id("aquifer_open_bible_dictionary"))
    ref = CanonicalReference.parse("John.4.1-42")
    expanded, diagnostics = expand_dictionary_evidence(
        reference=ref,
        canonical_passage=ref.canonical_string(),
        acai_adapter=acai,
        dictionary_adapter=dictionary,
        direct_evidence_items=[],
        dictionary_counter_start=1,
        dict_meta=dictionary.bundle_metadata(),
    )
    assert diagnostics.entities_used <= MAX_ENTITY_EXPANSION
    assert diagnostics.dictionary_candidates_added <= MAX_TOTAL_EXPANSION_CANDIDATES


def test_unresolved_place_not_auto_linked() -> None:
    bundle = load_pilot_bundle(PILOT_JSON)
    unresolved_ids = {item["textus_place_id"] for item in bundle["unresolved_crosswalks"]}
    linked_place_ids = {
        entity["place_crosswalk"]["textus_place_id"]
        for entity in bundle["entities"]
        if entity.get("place_crosswalk")
    }
    assert "galilee_1" in unresolved_ids
    assert "galilee_1" not in linked_place_ids


def test_provenance_chain_on_expanded_evidence() -> None:
    manifest = load_manifest()
    acai = AcaiEntitiesAdapter(manifest.source_by_id(ACAI_SOURCE_ID))
    dictionary = __import__(
        "textus_kb.adapters.aquifer_bible_dictionary",
        fromlist=["AquiferBibleDictionaryAdapter"],
    ).AquiferBibleDictionaryAdapter(manifest.source_by_id("aquifer_open_bible_dictionary"))
    ref = CanonicalReference.parse("John.4.1-42")
    expanded, _ = expand_dictionary_evidence(
        reference=ref,
        canonical_passage=ref.canonical_string(),
        acai_adapter=acai,
        dictionary_adapter=dictionary,
        direct_evidence_items=[],
        dictionary_counter_start=1,
        dict_meta=dictionary.bundle_metadata(),
    )
    assert expanded
    chain = expanded[0].metadata["entity_expansion"]
    assert chain["passage"]
    assert chain["entity_id"]
    assert chain["dictionary_article_id"]
    assert expanded[0].metadata["license"]


def test_retrieval_debug_metadata() -> None:
    packet = retrieve("Jn 4,1-42")
    assert packet.retrieval_debug
    assert "entity_expansion" in packet.retrieval_debug
    assert packet.retrieval_debug["acai_backend"] == "sqlite"


def test_disabled_acai_store_graceful(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    payload = deepcopy(base)
    for source in payload["sources"]:
        if source["id"] == ACAI_SOURCE_ID:
            source["enabled"] = False
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    packet = retrieve("Jn 4,1-42", manifest=manifest)
    assert packet.entities == []
    assert packet.retrieval_debug == {}


def test_context_budget_still_within_limits() -> None:
    packet = retrieve("Jn 4,1-42")
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert exegesis.estimated_tokens <= 4500
    assert historical.estimated_tokens <= 3500


def test_manifest_points_to_sqlite() -> None:
    source = load_manifest().source_by_id(ACAI_SOURCE_ID)
    assert source is not None
    assert source.source_type == "sqlite"
    assert source.resolved_path.suffix == ".sqlite3"


def test_health_includes_acai_store() -> None:
    from textus_kb.health import run_health_check

    report = run_health_check()
    assert report.acai_store is not None
    assert report.acai_store.store_available is True
    assert report.acai_store.entity_count > 0


def test_full_import_reasonable_when_present() -> None:
    if not FULL_SQLITE.is_file():
        pytest.skip("Full ACAI import artifact not generated in this workspace.")
    validation = validate_acai_database(FULL_SQLITE)
    assert validation.entity_count > 1000
    assert validation.dictionary_link_count > 100


def test_create_schema_on_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite3"
    with sqlite3.connect(db) as connection:
        create_schema(connection)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "entities" in tables
