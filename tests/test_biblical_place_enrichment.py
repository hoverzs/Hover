from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biblical_place_enrichment import (
    ALLOWED_PROFILE_TIERS,
    PLACE_ENRICHMENT_PRIORITY_PATH,
    PLACE_ENRICHMENT_SOURCES_PATH,
    PLACE_ENRICHMENTS_PATH,
    PLACE_PROFILE_GROUPS_PATH,
    PlaceEnrichmentDataError,
    enrichment_profile_status,
    get_place_enrichment,
    load_place_enrichment_sources,
    load_place_enrichments,
    load_place_profile_groups,
    place_profile_group_for_place,
    related_route_ids_for_place,
)

SOURCE_AUDIT_PATH = ROOT / "data" / "biblical_places" / "place_enrichment_source_audit.json"
PILOT_RESOLUTION_PATH = ROOT / "data" / "biblical_places" / "place_enrichment_pilot_resolution.json"
PILOT_REPORT_PATH = ROOT / "data" / "biblical_places" / "place_enrichment_pilot_report.json"
PILOT_QUALITY_AUDIT_PATH = ROOT / "data" / "biblical_places" / "place_enrichment_pilot_quality_audit.json"
CONTENT_QUALITY_REPORT_PATH = ROOT / "data" / "biblical_places" / "place_enrichment_content_quality_report.json"
RESEARCH_QUEUE_PATH = ROOT / "data" / "biblical_places" / "place_enrichment_research_queue.json"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_enrichment_source_registry_loads_and_has_license_fields() -> None:
    sources = load_place_enrichment_sources()
    assert len(sources) >= 3
    for source in sources:
        assert source.source_id
        assert source.license
        assert source.attribution
        assert source.allowed_use
        assert source.reliability_scope


def test_source_audit_separates_demo_source_from_pilot_sources() -> None:
    audit = _read(SOURCE_AUDIT_PATH)
    accepted_ids = {item["source_id"] for item in audit["accepted_sources"]}
    limited_ids = {item["source_id"] for item in audit["rejected_or_limited_sources"]}
    assert "openbible_geocoding_cc_by_4_0" in accepted_ids
    assert "manual_demo_v1" in limited_ids
    assert "manual_demo_v1" not in accepted_ids


def test_place_enrichments_load_and_cover_twenty_pilots() -> None:
    enrichments = load_place_enrichments()
    assert len(enrichments) == 20
    assert {item.place_id for item in enrichments} == {
        "jerusalem",
        "bethlehem_1",
        "nazareth",
        "capernaum",
        "jericho_1",
        "shechem",
        "bethel_1",
        "hebron",
        "beersheba_1",
        "mount_sinai",
        "kadesh_barnea",
        "babylon_1",
        "nineveh",
        "antioch_syria",
        "ephesus",
        "corinth",
        "philippi",
        "athens",
        "caesarea",
        "rome",
    }


def test_each_nonempty_enrichment_section_has_valid_sources() -> None:
    source_ids = {source.source_id for source in load_place_enrichment_sources()}
    for enrichment in _read(PLACE_ENRICHMENTS_PATH):
        assert enrichment["profile_tier"] in ALLOWED_PROFILE_TIERS
        for section_key, section in enrichment["sections"].items():
            if section_key == "key_events":
                assert section["items"]
                for item in section["items"]:
                    assert item["summary_hu"].strip()
                    assert item["passage_refs"]
                    assert set(item["source_ids"]).issubset(source_ids)
            else:
                assert section["text_hu"].strip()
                assert set(section["source_ids"]).issubset(source_ids)


def test_enrichment_loader_rejects_unknown_place_id() -> None:
    raw = _read(PLACE_ENRICHMENTS_PATH)
    raw[0]["place_id"] = "unknown_place_for_test"
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "place_enrichments.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        try:
            load_place_enrichments(path)
        except PlaceEnrichmentDataError as exc:
            assert "unknown place_id" in str(exc)
        else:
            raise AssertionError("unknown place_id was accepted")


def test_enrichment_loader_rejects_unknown_source_id() -> None:
    raw = _read(PLACE_ENRICHMENTS_PATH)
    raw[0]["sections"]["biblical_significance"]["source_ids"] = ["unknown_source_for_test"]
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "place_enrichments.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        try:
            load_place_enrichments(path)
        except PlaceEnrichmentDataError as exc:
            assert "Unknown source_id" in str(exc)
        else:
            raise AssertionError("unknown source_id was accepted")


def test_enrichment_loader_rejects_mojibake_text() -> None:
    raw = _read(PLACE_ENRICHMENTS_PATH)
    raw[0]["sections"]["biblical_significance"]["text_hu"] = "HibĂˇs szĂ¶veg"
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "place_enrichments.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        try:
            load_place_enrichments(path)
        except PlaceEnrichmentDataError as exc:
            assert "Corrupted user-facing enrichment text" in str(exc)
        else:
            raise AssertionError("mojibake text was accepted")


def test_priority_file_is_sorted_and_contains_required_fields() -> None:
    rows = _read(PLACE_ENRICHMENT_PRIORITY_PATH)
    assert len(rows) > 1000
    assert rows == sorted(rows, key=lambda item: (-item["total_score"], item["place_id"]))
    for row in rows[:20]:
        assert row["place_id"]
        assert row["priority_tier"] in {"featured", "high", "medium", "basic"}
        assert isinstance(row["total_score"], int)


def test_pilot_resolution_report_has_no_skipped_pilots() -> None:
    report = _read(PILOT_RESOLUTION_PATH)
    assert report["requested_count"] == 20
    assert report["resolved_count"] == 20
    assert report["skipped_count"] == 0


def test_pilot_report_has_expected_archaeology_and_route_counts() -> None:
    report = _read(PILOT_REPORT_PATH)
    assert report["requested_pilot_place_count"] == 20
    assert report["resolved_place_count"] == 20
    assert report["sections_without_sources"] == []
    assert report["archaeology_section_count"] >= 2
    assert report["route_link_count_by_place"]["corinth"] >= 1


def test_related_route_ids_are_computed_from_route_stops() -> None:
    assert "paul_second_missionary_journey" in related_route_ids_for_place("corinth")
    enrichment = get_place_enrichment("corinth")
    assert enrichment is not None
    assert enrichment.related_route_ids == related_route_ids_for_place("corinth")


def test_profile_groups_load_and_keep_distinct_records() -> None:
    groups = load_place_profile_groups()
    assert len(groups) == 2
    jericho = place_profile_group_for_place("jericho_2")
    assert jericho is not None
    assert jericho.profile_id == "jericho_site"
    assert jericho.primary_place_id == "jericho_1"
    assert "jericho_1" in jericho.member_place_ids
    assert "jericho_2" in jericho.member_place_ids
    assert place_profile_group_for_place("antioch_2") is None
    assert place_profile_group_for_place("caesarea_philippi") is None


def test_enrichment_profile_status_is_computed_from_quality() -> None:
    assert enrichment_profile_status(get_place_enrichment("corinth")) == "featured"
    assert enrichment_profile_status(get_place_enrichment("ephesus")) == "featured"
    assert enrichment_profile_status(get_place_enrichment("jericho_1")) == "source_backed"
    assert enrichment_profile_status(get_place_enrichment("abana")) == "basic"


def test_generic_passage_link_events_were_removed() -> None:
    for enrichment in _read(PLACE_ENRICHMENTS_PATH):
        key_events = enrichment["sections"].get("key_events")
        if not key_events:
            continue
        for item in key_events["items"]:
            assert "A hely ehhez a bibliai hivatkozáshoz kapcsolódik" not in item["summary_hu"]


def test_generic_geography_and_route_list_homiletics_were_removed() -> None:
    for enrichment in _read(PLACE_ENRICHMENTS_PATH):
        sections = enrichment["sections"]
        if "ancient_geography" in sections:
            assert "A rekord szerint a hely típusa" not in sections["ancient_geography"]["text_hu"]
        assert "homiletical_context" not in sections


def test_quality_audit_covers_twenty_pilot_places() -> None:
    rows = _read(PILOT_QUALITY_AUDIT_PATH)
    assert len(rows) == 20
    statuses = {row["profile_status"] for row in rows}
    assert "featured" in statuses
    assert "source_backed" in statuses
    assert any(row["resolved_place_id"] == "jericho_1" and row["same_physical_site"] for row in rows)


def test_content_quality_report_has_no_remaining_generic_rendered_sections() -> None:
    rows = _read(CONTENT_QUALITY_REPORT_PATH)
    assert len(rows) == 20 * 8
    rendered_generic = [
        row
        for row in rows
        if row["quality_status"] == "generic" and row["recommended_action"] != "remove_or_rewrite_with_sources"
    ]
    assert rendered_generic == []


def test_research_queue_tracks_source_gaps_without_urls() -> None:
    rows = _read(RESEARCH_QUEUE_PATH)
    assert rows
    assert any(row["place_id"] == "jerusalem" and row["missing_section"] == "archaeology" for row in rows)
    assert any(row["place_id"] == "jericho_1" for row in rows)
    assert all("http" not in json.dumps(row, ensure_ascii=False).casefold() for row in rows)


def test_priority_file_includes_quality_and_research_fields() -> None:
    row = next(item for item in _read(PLACE_ENRICHMENT_PRIORITY_PATH) if item["place_id"] == "corinth")
    assert row["enrichment_status"] == "featured"
    assert "content_quality_score" in row
    assert "source_gap_count" in row
    assert "record_resolution_needed" in row
    assert "research_priority" in row
    assert "next_action" in row
