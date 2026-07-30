from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_place_enrichment_research import (  # noqa: E402
    ALL_SECTIONS,
    ACCEPTED_SOURCE_CATEGORIES,
    build_packets,
)

DATA_DIR = ROOT / "data" / "biblical_places"
BATCH_DIR = DATA_DIR / "enrichment_batches"
RESEARCH_DIR = DATA_DIR / "enrichment_research"

MANIFEST_PATH = BATCH_DIR / "place_enrichment_batch_001.json"
BLOCKED_PATH = BATCH_DIR / "place_enrichment_batch_001_blocked.json"
SOURCE_REGISTRY_PATH = DATA_DIR / "place_enrichment_sources.json"
SOURCE_CANDIDATES_PATH = RESEARCH_DIR / "batch_001_source_candidates.json"
EVIDENCE_PACKETS_PATH = RESEARCH_DIR / "batch_001_evidence_packets.json"
COVERAGE_REPORT_PATH = RESEARCH_DIR / "batch_001_coverage_report.json"
READY_FOR_DRAFTING_PATH = RESEARCH_DIR / "batch_001_ready_for_drafting.json"
RESEARCH_BLOCKED_PATH = RESEARCH_DIR / "batch_001_research_blocked.json"
CACHE_PATH = RESEARCH_DIR / "cache" / "batch_001_research_cache.json"

REUSE_STATUSES = {"approved", "citation_only", "blocked"}
RELIABILITY_STATUSES = {"high", "medium", "low", "unknown"}
RELEVANCE_STATUSES = {"direct", "contextual", "uncertain"}
EVIDENCE_TYPES = {
    "direct_statement",
    "biblical_text_link",
    "scholarly_inference",
    "structured_metadata",
}
CONFIDENCE_VALUES = {"high", "medium", "low"}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_research_outputs_match_first_batch_manifest() -> None:
    manifest = _read(MANIFEST_PATH)
    packets = _read(EVIDENCE_PACKETS_PATH)
    report = _read(COVERAGE_REPORT_PATH)
    ready = _read(READY_FOR_DRAFTING_PATH)

    manifest_ids = [row["place_id"] for row in manifest]
    packet_ids = [packet["place_id"] for packet in packets]

    assert len(manifest) == 50
    assert len(packets) == 50
    assert packet_ids == manifest_ids
    assert report["summary"]["place_count"] == 50
    assert report["summary"]["ready_for_drafting_count"] == 50
    assert len(ready) <= 20


def test_source_candidates_are_unique_reviewable_sources() -> None:
    candidates = _read(SOURCE_CANDIDATES_PATH)

    candidate_ids = [candidate["candidate_id"] for candidate in candidates]
    normalized_urls = [
        str(candidate.get("url_or_identifier") or candidate["candidate_id"]).split("?", 1)[0].rstrip("/")
        for candidate in candidates
    ]

    assert candidates
    assert len(candidate_ids) == len(set(candidate_ids))
    assert len(normalized_urls) == len(set(normalized_urls))
    for candidate in candidates:
        assert set(candidate["section_names"]).issubset(set(ALL_SECTIONS))
        assert candidate["source_type"] in ACCEPTED_SOURCE_CATEGORIES
        assert candidate["reuse_status"] in REUSE_STATUSES
        assert candidate["reliability_status"] in RELIABILITY_STATUSES
        assert candidate["relevance_status"] in RELEVANCE_STATUSES
        assert candidate["review_status"] in {"accepted_existing_source", "candidate_only"}
        if candidate.get("url_or_identifier"):
            assert candidate["url_or_identifier"].startswith("https://")


def test_evidence_packets_have_valid_references_and_no_final_enrichment_text() -> None:
    candidates = _read(SOURCE_CANDIDATES_PATH)
    packets = _read(EVIDENCE_PACKETS_PATH)
    registry = _read(SOURCE_REGISTRY_PATH)
    candidate_ids = {candidate["candidate_id"] for candidate in candidates}
    approved_source_ids = {source["source_id"] for source in registry}

    for packet in packets:
        assert set(packet["section_evidence"]) == set(ALL_SECTIONS)
        assert packet["ready_for_drafting"] is True
        assert "profile_group_id" in packet["record_context"]
        for section_items in packet["section_evidence"].values():
            for item in section_items:
                assert item["evidence_type"] in EVIDENCE_TYPES
                assert item["confidence"] in CONFIDENCE_VALUES
                assert isinstance(item["usable_for_drafting"], bool)
                assert item["candidate_id"] is None or item["candidate_id"] in candidate_ids
                assert item["approved_source_id"] is None or item["approved_source_id"] in approved_source_ids
                assert item["candidate_id"] or item["approved_source_id"]
                assert item["claim_hu"]
                assert "kész adatlap" not in item["claim_hu"].casefold()


def test_coverage_ready_and_blocked_reports_are_consistent() -> None:
    report = _read(COVERAGE_REPORT_PATH)
    ready = _read(READY_FOR_DRAFTING_PATH)
    blocked = _read(RESEARCH_BLOCKED_PATH)
    batch_blocked = _read(BLOCKED_PATH)

    coverage_by_id = {row["place_id"]: row for row in report["places"]}
    ready_ids = {row["place_id"] for row in ready}
    blocked_ids = {row["place_id"] for row in blocked}
    batch_blocked_ids = {row["place_id"] for row in batch_blocked}

    assert ready_ids.issubset(coverage_by_id)
    assert all(coverage_by_id[place_id]["ready_for_drafting"] for place_id in ready_ids)
    assert batch_blocked_ids.issubset(blocked_ids)
    assert report["summary"]["research_blocked_count"] == len(blocked)
    assert report["summary"]["approved_registry_source_promotions"] == 0
    assert report["summary"]["internet_research_status"] == "limited_web_discovery_plus_existing_registry"
    assert report["summary"]["largest_source_gaps"]["historical_context"] > 0
    assert report["summary"]["largest_source_gaps"]["archaeology"] > 0


def test_research_cache_matches_generated_outputs() -> None:
    cache = _read(CACHE_PATH)

    assert cache["cache_version"] == 1
    assert len(cache["candidate_hash"]) == 40
    assert len(cache["packet_hash"]) == 40
    assert cache["status"] == "metadata_only_cache"


def test_research_builder_rewrites_outputs_idempotently() -> None:
    paths = [
        SOURCE_CANDIDATES_PATH,
        EVIDENCE_PACKETS_PATH,
        COVERAGE_REPORT_PATH,
        READY_FOR_DRAFTING_PATH,
        RESEARCH_BLOCKED_PATH,
        CACHE_PATH,
    ]
    before = {path: path.read_text(encoding="utf-8") for path in paths}
    build_packets()
    after = {path: path.read_text(encoding="utf-8") for path in paths}

    assert after == before


if __name__ == "__main__":
    current_module = sys.modules[__name__]
    for name in sorted(dir(current_module)):
        if name.startswith("test_"):
            getattr(current_module, name)()
