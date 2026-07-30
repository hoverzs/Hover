from __future__ import annotations

import csv
import json
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_place_enrichment_batch import (
    ACCEPTED_SOURCE_CATEGORIES,
    ALLOWED_SECTIONS,
    build_batch,
)

BATCH_DIR = ROOT / "data" / "biblical_places" / "enrichment_batches"
MANIFEST_PATH = BATCH_DIR / "place_enrichment_batch_001.json"
RESEARCH_PATH = BATCH_DIR / "place_enrichment_batch_001_research_queue.json"
BLOCKED_PATH = BATCH_DIR / "place_enrichment_batch_001_blocked.json"
CSV_PATH = BATCH_DIR / "place_enrichment_batch_001.csv"
REPORT_PATH = BATCH_DIR / "place_enrichment_batch_001_report.json"
CATALOG_PATH = ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
ENRICHMENTS_PATH = ROOT / "data" / "biblical_places" / "place_enrichments.json"
PROFILE_GROUPS_PATH = ROOT / "data" / "biblical_places" / "place_profile_groups.json"
SOURCES_PATH = ROOT / "data" / "biblical_places" / "place_enrichment_sources.json"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_batch_manifest_has_exactly_fifty_unique_active_places() -> None:
    manifest = _read(MANIFEST_PATH)
    catalog_ids = {item["place_id"] for item in _read(CATALOG_PATH)}
    place_ids = [item["place_id"] for item in manifest]

    assert len(manifest) == 50
    assert len(place_ids) == len(set(place_ids))
    assert set(place_ids).issubset(catalog_ids)
    assert [item["batch_position"] for item in manifest] == list(range(1, 51))


def test_batch_excludes_existing_pilot_and_blocked_resolution_places() -> None:
    manifest_ids = {item["place_id"] for item in _read(MANIFEST_PATH)}
    pilot_ids = {item["place_id"] for item in _read(ENRICHMENTS_PATH)}
    blocked_ids = {item["place_id"] for item in _read(BLOCKED_PATH)}

    assert manifest_ids.isdisjoint(pilot_ids)
    assert {"mount_sinai", "antioch_syria", "caesarea"}.issubset(blocked_ids)
    assert manifest_ids.isdisjoint({"mount_sinai", "antioch_syria", "caesarea"})


def test_batch_excludes_non_primary_profile_group_members() -> None:
    manifest_ids = {item["place_id"] for item in _read(MANIFEST_PATH)}
    blocked_ids = {item["place_id"] for item in _read(BLOCKED_PATH)}
    groups = _read(PROFILE_GROUPS_PATH)
    non_primary = {
        place_id
        for group in groups
        for place_id in group["member_place_ids"]
        if place_id != group["primary_place_id"]
    }

    assert manifest_ids.isdisjoint(non_primary)
    assert non_primary.issubset(blocked_ids)


def test_batch_required_sections_and_source_categories_are_valid() -> None:
    for row in _read(MANIFEST_PATH):
        assert set(row["required_sections"]).issubset(ALLOWED_SECTIONS)
        assert set(row["optional_sections"]).issubset(ALLOWED_SECTIONS)
        assert set(row["required_source_types"]).issubset(ACCEPTED_SOURCE_CATEGORIES)
        assert "homiletical_context" not in row["required_sections"]


def test_research_queue_matches_manifest_and_has_no_urls() -> None:
    manifest_ids = {item["place_id"] for item in _read(MANIFEST_PATH)}
    tasks = _read(RESEARCH_PATH)

    assert tasks
    assert {task["place_id"] for task in tasks}.issubset(manifest_ids)
    assert all(task["status"] == "pending" for task in tasks)
    assert all(task["section_name"] in ALLOWED_SECTIONS for task in tasks)
    assert all(set(task["accepted_source_categories"]).issubset(ACCEPTED_SOURCE_CATEGORIES) for task in tasks)
    assert all("http" not in json.dumps(task, ensure_ascii=False).casefold() for task in tasks)


def test_existing_source_ids_resolve_to_enrichment_source_registry() -> None:
    registry_ids = {item["source_id"] for item in _read(SOURCES_PATH)}
    for row in _read(MANIFEST_PATH):
        assert set(row["existing_source_ids"]).issubset(registry_ids)


def test_csv_export_matches_manifest_rows() -> None:
    manifest = _read(MANIFEST_PATH)
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert len(csv_rows) == len(manifest)
    assert [int(row["batch_position"]) for row in csv_rows] == [
        item["batch_position"] for item in manifest
    ]
    assert [row["place_id"] for row in csv_rows] == [item["place_id"] for item in manifest]


def test_report_matches_manifest_and_blocked_lists() -> None:
    report = _read(REPORT_PATH)
    manifest = _read(MANIFEST_PATH)
    blocked = _read(BLOCKED_PATH)

    assert report["batch_size_requested"] == 50
    assert report["batch_size_created"] == len(manifest)
    assert report["blocked_count"] == len(blocked)
    assert report["research_task_count"] == len(_read(RESEARCH_PATH))
    assert report["idempotency_result"] == "deterministic_builder_rewrite_expected_identical"


def test_batch_builder_is_deterministic() -> None:
    with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
        args_one = Namespace(batch_size=50, batch_number=1, output_dir=first_dir)
        args_two = Namespace(batch_size=50, batch_number=1, output_dir=second_dir)
        build_batch(args_one)
        build_batch(args_two)
        first = Path(first_dir)
        second = Path(second_dir)
        names = [
            "place_enrichment_batch_001.json",
            "place_enrichment_batch_001_research_queue.json",
            "place_enrichment_batch_001_blocked.json",
            "place_enrichment_batch_001.csv",
            "place_enrichment_batch_001_report.json",
        ]
        for name in names:
            assert (first / name).read_text(encoding="utf-8") == (second / name).read_text(encoding="utf-8")
