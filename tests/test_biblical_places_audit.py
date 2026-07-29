from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_biblical_places import (
    EXPECTED_LOCK_FINGERPRINT_FIELDS,
    MANUAL_LOCKED_PLACE_IDS,
    audit_catalog,
    read_json,
)
from scripts.build_biblical_places_catalog import build_catalog


def test_full_catalog_import_report_matches_outputs() -> None:
    report = read_json(ROOT / "data" / "biblical_places" / "full_catalog_import_report.json")
    catalog = read_json(ROOT / "data" / "biblical_places" / "biblical_places_catalog.json")
    passage_catalog = read_json(ROOT / "data" / "biblical_places" / "passage_place_catalog.json")

    assert report["raw_place_count"] == 1342
    assert report["imported_place_count"] == len(catalog) > 100
    assert report["skipped_place_count"] == 33
    assert report["skipped_places_by_reason"] == {"missing_or_invalid_coordinates": 33}
    assert report["manual_override_count"] == 10
    assert len(passage_catalog) > 11


def test_full_catalog_builder_is_idempotent_in_memory() -> None:
    rebuilt = build_catalog()
    catalog = read_json(ROOT / "data" / "biblical_places" / "biblical_places_catalog.json")
    passage_catalog = read_json(ROOT / "data" / "biblical_places" / "passage_place_catalog.json")

    assert rebuilt["catalog"] == catalog
    assert rebuilt["passage_catalog"] == passage_catalog


def test_audit_report_files_have_expected_shape() -> None:
    report_path = ROOT / "data" / "biblical_places" / "audit_report.json"
    markdown_path = ROOT / "docs" / "biblical_places_audit.md"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "data" / "biblical_places" / "biblical_places_catalog.json").read_text(encoding="utf-8"))

    assert markdown_path.exists()
    assert report["catalog_record_count"] == len(catalog) > 100
    assert report["merged_catalog_count"] == len(catalog)
    assert report["openbible_raw_place_count"] == 1342
    assert report["successfully_imported_place_count"] > 100
    assert report["skipped_place_count"] == 33
    assert report["manual_override_count"] == 10
    assert report["passage_place_link_count"] > 11
    assert report["large_place_list_for_passage_count"] == 118
    assert report["definite_duplicate_merge_count"] == 0
    assert report["uncertain_duplicate_count"] == 201
    assert report["invalid_external_id_count"] == 0
    assert report["invalid_external_ids_fixed"] is True
    assert report["mixed_manual_demo_source_count"] == 0
    assert report["mixed_manual_demo_source_resolved"] is True
    assert report["ui_fallback_name_count"] == 1299
    assert report["safe_fallback_description_count"] > 100
    assert "summary" in report
    assert "auto_fixed_items" in report
    assert "top_findings" in report
    assert "hungarian_name_review" in report
    assert "disputed_or_multiple_identification_review" in report


def test_audit_catalog_flags_review_items_without_missing_references() -> None:
    places = read_json(ROOT / "data" / "biblical_places" / "biblical_places_catalog.json")
    sources = read_json(ROOT / "data" / "biblical_places" / "sources.json")
    links = read_json(ROOT / "data" / "biblical_places" / "passage_place_links.json")

    findings = audit_catalog(places, sources, links)
    categories = {finding.category for finding in findings}

    assert "missing_hungarian_name" in categories
    assert "summary_repeats_name" in categories
    assert "mixed_manual_demo_source" not in categories
    assert "invalid_external_id" not in categories
    assert "missing_source_id" not in categories
    assert "missing_coordinate_source_id" not in categories
    assert "passage_link_unknown_place" not in categories


def test_manual_lock_records_keep_protected_content() -> None:
    places = {
        place["place_id"]: place
        for place in read_json(ROOT / "data" / "biblical_places" / "pilot_places.json")
    }
    locks = read_json(ROOT / "data" / "biblical_places" / "manual_locks.json")

    assert set(locks["locked_place_ids"]) == MANUAL_LOCKED_PLACE_IDS
    for place_id in MANUAL_LOCKED_PLACE_IDS:
        record = places[place_id]
        for field_name in EXPECTED_LOCK_FINGERPRINT_FIELDS:
            assert field_name in record
        assert record["review_status"] == "needs_review"
