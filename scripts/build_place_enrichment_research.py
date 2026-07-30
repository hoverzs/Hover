from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "biblical_places"
BATCH_DIR = DATA_DIR / "enrichment_batches"
RESEARCH_DIR = DATA_DIR / "enrichment_research"
CACHE_DIR = RESEARCH_DIR / "cache"

BATCH_PATH = BATCH_DIR / "place_enrichment_batch_001.json"
BATCH_RESEARCH_QUEUE_PATH = BATCH_DIR / "place_enrichment_batch_001_research_queue.json"
BATCH_BLOCKED_PATH = BATCH_DIR / "place_enrichment_batch_001_blocked.json"
SOURCES_PATH = DATA_DIR / "place_enrichment_sources.json"
PROFILE_GROUPS_PATH = DATA_DIR / "place_profile_groups.json"
PRIORITY_PATH = DATA_DIR / "place_enrichment_priority.json"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"

SOURCE_CANDIDATES_PATH = RESEARCH_DIR / "batch_001_source_candidates.json"
EVIDENCE_PACKETS_PATH = RESEARCH_DIR / "batch_001_evidence_packets.json"
COVERAGE_REPORT_PATH = RESEARCH_DIR / "batch_001_coverage_report.json"
READY_FOR_DRAFTING_PATH = RESEARCH_DIR / "batch_001_ready_for_drafting.json"
RESEARCH_BLOCKED_PATH = RESEARCH_DIR / "batch_001_research_blocked.json"

ALL_SECTIONS = (
    "biblical_significance",
    "key_events",
    "ancient_geography",
    "historical_context",
    "archaeology",
    "modern_context",
    "identification_notes",
    "homiletical_context",
)

ACCEPTED_SOURCE_CATEGORIES = {
    "official_archaeological_site",
    "university_project",
    "academic_gazetteer",
    "museum",
    "heritage_authority",
    "excavation_project",
    "peer_reviewed_publication",
    "official_geographical_source",
    "biblical_text_dataset",
}

WEB_DISCOVERED_CANDIDATES = [
    {
        "candidate_id": "web_unesco_ancient_thebes_87",
        "place_ids": ["egypt"],
        "section_names": ["historical_context", "archaeology"],
        "title": "Ancient Thebes with its Necropolis",
        "institution_or_author": "UNESCO World Heritage Centre",
        "source_type": "heritage_authority",
        "url_or_identifier": "https://whc.unesco.org/en/list/87",
        "publication_date": "1979",
        "access_date": "2026-07-30",
        "language": "en",
        "license": "citation_only_review_required",
        "attribution": "UNESCO World Heritage Centre",
        "reuse_status": "citation_only",
        "reliability_status": "high",
        "relevance_status": "contextual",
        "supported_topics": ["Ancient Egypt heritage context", "Thebes and Nile Valley setting"],
        "limitations_hu": "Egyiptom egészére csak kontextuális forrás; nem minden egyiptomi bibliai helyre közvetlen.",
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
    },
    {
        "candidate_id": "web_pleiades_ancient_places",
        "place_ids": ["multiple"],
        "section_names": ["ancient_geography", "identification_notes"],
        "title": "Ancient Places in Pleiades",
        "institution_or_author": "Pleiades contributors",
        "source_type": "academic_gazetteer",
        "url_or_identifier": "https://pleiades.stoa.org/places",
        "publication_date": "2024-07-11",
        "access_date": "2026-07-30",
        "language": "en",
        "license": "CC-BY-3.0",
        "attribution": "Pleiades contributors; Ancient World Mapping Center and Institute for the Study of the Ancient World",
        "reuse_status": "approved",
        "reliability_status": "high",
        "relevance_status": "contextual",
        "supported_topics": ["Ancient gazetteer methodology", "Place identity and names"],
        "limitations_hu": "A batchben csak azoknál a helyeknél közvetlen, ahol konkrét Pleiades rekord is fel van oldva.",
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
    },
    {
        "candidate_id": "web_cogat_archaeology_unit",
        "place_ids": ["samaria_1", "judea_1"],
        "section_names": ["archaeology", "historical_context"],
        "title": "Archaeology Unit",
        "institution_or_author": "Coordination of Government Activities in the Territories",
        "source_type": "official_archaeological_site",
        "url_or_identifier": "https://www.gov.il/en/departments/units/archeology_unit",
        "publication_date": None,
        "access_date": "2026-07-30",
        "language": "en",
        "license": "citation_only_review_required",
        "attribution": "Coordination of Government Activities in the Territories",
        "reuse_status": "citation_only",
        "reliability_status": "medium",
        "relevance_status": "contextual",
        "supported_topics": ["Archaeological responsibility in Judea and Samaria", "Site preservation context"],
        "limitations_hu": "Intézményi, de nem minden konkrét bibliai helyhez közvetlen lelőhelylap.",
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
    },
]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def compact_ref_key(reference: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", reference).strip("_").lower()[:40]


def build_route_index(routes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_place: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in routes:
        for stop in route.get("stops") or []:
            place_id = stop.get("place_id")
            if not place_id:
                continue
            by_place[place_id].append(
                {
                    "route_id": route["route_id"],
                    "route_name_hu": route["name_hu"],
                    "stop_id": stop.get("stop_id"),
                    "passage_refs": stop.get("passage_refs") or [],
                    "event_summary_hu": stop.get("event_summary_hu"),
                }
            )
    return by_place


def build_passage_index(links: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_place: dict[str, list[str]] = defaultdict(list)
    for link in links:
        ref = link.get("reference")
        if ref and ref not in by_place[link["place_id"]]:
            by_place[link["place_id"]].append(ref)
    return {place_id: refs for place_id, refs in by_place.items()}


def source_candidate_from_registry(source: dict[str, Any], used_by: dict[str, set[str]]) -> dict[str, Any]:
    source_type = source.get("source_type") or "academic_gazetteer"
    candidate_type = source_type_category(source_type)
    return {
        "candidate_id": f"existing_{source['source_id']}",
        "place_id": "multiple",
        "place_ids": sorted(used_by.get(source["source_id"], [])) or ["multiple"],
        "name_hu": "több hely",
        "section_names": sections_for_source_type(source_type),
        "title": source.get("title"),
        "institution_or_author": source.get("institution"),
        "source_type": candidate_type,
        "url_or_identifier": source.get("identifier"),
        "publication_date": None,
        "access_date": "2026-07-30",
        "language": "en",
        "license": source.get("license"),
        "attribution": source.get("attribution"),
        "reuse_status": "approved" if str(source.get("license") or "").startswith("CC") else "citation_only",
        "reliability_status": "high" if source.get("reliability_scope") in {"official_institutional", "scholarly_curated", "institutional_scholarly"} else "medium",
        "relevance_status": "direct" if used_by.get(source["source_id"]) else "contextual",
        "supported_topics": [source.get("allowed_use") or ""],
        "limitations_hu": source.get("notes_hu"),
        "discovery_method": "existing_registry",
        "duplicate_of_candidate_id": None,
        "review_status": "accepted_existing_source",
    }


def source_type_category(source_type: str) -> str:
    if "archaeological" in source_type:
        return "official_archaeological_site" if "official" in source_type else "excavation_project"
    if "heritage" in source_type:
        return "heritage_authority"
    if "gazetteer" in source_type:
        return "academic_gazetteer"
    if "geocoding" in source_type:
        return "biblical_text_dataset"
    return "academic_gazetteer"


def sections_for_source_type(source_type: str) -> list[str]:
    if "archaeological" in source_type or "heritage" in source_type:
        return ["historical_context", "archaeology", "modern_context"]
    if "gazetteer" in source_type:
        return ["ancient_geography", "identification_notes", "modern_context"]
    if "geocoding" in source_type:
        return ["biblical_significance", "key_events", "modern_context", "identification_notes"]
    return ["identification_notes"]


def evidence_item(
    *,
    place_id: str,
    section: str,
    source_ref: str,
    claim_hu: str,
    evidence_type: str,
    confidence: str,
    passage_refs: list[str] | None = None,
    chronology: str | None = None,
    geographical_scope: str | None = None,
    record_specific: bool = True,
    shared_profile_evidence: bool = False,
    limitations_hu: str | None = None,
    usable_for_drafting: bool = True,
) -> dict[str, Any]:
    return {
        "evidence_id": stable_id("ev", place_id, section, source_ref, claim_hu),
        "candidate_id": source_ref if source_ref.startswith("web_") or source_ref.startswith("existing_") else None,
        "approved_source_id": None if source_ref.startswith("web_") or source_ref.startswith("existing_") else source_ref,
        "claim_hu": claim_hu,
        "evidence_type": evidence_type,
        "confidence": confidence,
        "passage_refs": passage_refs or [],
        "chronology": chronology,
        "geographical_scope": geographical_scope,
        "record_specific": record_specific,
        "shared_profile_evidence": shared_profile_evidence,
        "limitations_hu": limitations_hu,
        "usable_for_drafting": usable_for_drafting,
    }


def build_packets() -> dict[str, Any]:
    manifest = read_json(BATCH_PATH)
    batch_queue = read_json(BATCH_RESEARCH_QUEUE_PATH)
    batch_blocked = read_json(BATCH_BLOCKED_PATH)
    registry = read_json(SOURCES_PATH)
    profile_groups = read_json(PROFILE_GROUPS_PATH, [])
    catalog = read_json(CATALOG_PATH)
    links = read_json(PASSAGE_LINKS_PATH)
    routes = read_json(ROUTES_PATH)

    places_by_id = {place["place_id"]: place for place in catalog}
    groups_by_place = {
        place_id: group
        for group in profile_groups
        for place_id in group.get("member_place_ids", [])
    }
    passage_refs_by_place = build_passage_index(links)
    route_stops_by_place = build_route_index(routes)
    used_sources: dict[str, set[str]] = defaultdict(set)
    for row in manifest:
        for source_id in row.get("existing_source_ids") or []:
            used_sources[source_id].add(row["place_id"])

    candidates = [
        source_candidate_from_registry(source, used_sources)
        for source in registry
        if source.get("source_id") in used_sources or source.get("source_id") == "openbible_geocoding_cc_by_4_0"
    ]
    candidates.extend(WEB_DISCOVERED_CANDIDATES)
    candidates = dedupe_candidates(candidates)
    candidate_ids = {candidate["candidate_id"] for candidate in candidates}
    approved_source_ids = {source["source_id"] for source in registry}

    packets = []
    coverage_rows = []
    blocked_rows = []
    for row in manifest:
        place = places_by_id[row["place_id"]]
        group = groups_by_place.get(row["place_id"])
        section_evidence = {section: [] for section in ALL_SECTIONS}
        source_ids: set[str] = set(row.get("existing_source_ids") or [])
        passage_refs = passage_refs_by_place.get(row["place_id"], [])
        route_stops = route_stops_by_place.get(row["place_id"], [])

        add_biblical_evidence(section_evidence, row, passage_refs, route_stops)
        add_structured_place_evidence(section_evidence, row, place)
        add_source_candidate_evidence(section_evidence, row, candidates)

        for source_id in source_ids:
            if source_id not in approved_source_ids:
                blocked_rows.append(blocked_item(row, "all", "unknown_source_id", [source_id], "review_source_registry", True, True))

        coverage = coverage_for_packet(row, section_evidence, source_ids, candidates, group)
        coverage_rows.append(coverage)
        if not coverage["ready_for_drafting"]:
            for section in row["required_sections"]:
                if not section_evidence[section]:
                    blocked_rows.append(
                        blocked_item(
                            row,
                            section,
                            "no_safe_evidence_available",
                            [],
                            "research_approved_source",
                            section in {"biblical_significance", "key_events", "identification_notes"},
                            section in {"historical_context", "archaeology"},
                        )
                    )

        packets.append(
            {
                "place_id": row["place_id"],
                "name_hu": row["name_hu"],
                "record_context": {
                    "place_type": row.get("place_type"),
                    "identification_status": row.get("identification_status"),
                    "profile_group_id": row.get("profile_group_id"),
                    "related_place_ids": related_place_ids(group, row["place_id"]),
                    "passage_refs": passage_refs[:20],
                    "related_route_ids": row.get("related_route_ids") or [],
                },
                "section_evidence": section_evidence,
                "source_ids": sorted(source_ids),
                "coverage_status": coverage["coverage_status"],
                "research_gaps": coverage["remaining_source_gaps"],
                "record_resolution_notes_hu": group.get("notes_hu") if group else "",
                "ready_for_drafting": coverage["ready_for_drafting"],
            }
        )

    ready_rows = ready_for_drafting_rows(coverage_rows, packets)
    research_blocked_rows = sorted_blocked(blocked_rows, batch_blocked)
    report = {
        "summary": coverage_summary(coverage_rows, candidates, research_blocked_rows),
        "places": coverage_rows,
    }
    cache = {
        "cache_version": 1,
        "generated_from": [
            str(BATCH_PATH.as_posix()),
            str(BATCH_RESEARCH_QUEUE_PATH.as_posix()),
            str(SOURCES_PATH.as_posix()),
        ],
        "candidate_hash": hashlib.sha1(json.dumps(candidates, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "packet_hash": hashlib.sha1(json.dumps(packets, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "status": "metadata_only_cache",
    }

    write_json(SOURCE_CANDIDATES_PATH, candidates)
    write_json(EVIDENCE_PACKETS_PATH, packets)
    write_json(COVERAGE_REPORT_PATH, report)
    write_json(READY_FOR_DRAFTING_PATH, ready_rows)
    write_json(RESEARCH_BLOCKED_PATH, research_blocked_rows)
    write_json(CACHE_DIR / "batch_001_research_cache.json", cache)
    return {
        "candidates": candidates,
        "packets": packets,
        "coverage": report,
        "ready": ready_rows,
        "blocked": research_blocked_rows,
    }


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        url = str(candidate.get("url_or_identifier") or candidate["candidate_id"]).split("?", 1)[0].rstrip("/")
        if url in by_url:
            candidate["duplicate_of_candidate_id"] = by_url[url]["candidate_id"]
            continue
        by_url[url] = candidate
    return sorted(by_url.values(), key=lambda item: item["candidate_id"])


def add_biblical_evidence(section_evidence: dict[str, list[dict[str, Any]]], row: dict[str, Any], passage_refs: list[str], route_stops: list[dict[str, Any]]) -> None:
    place_id = row["place_id"]
    if passage_refs:
        section_evidence["biblical_significance"].append(
            evidence_item(
                place_id=place_id,
                section="biblical_significance",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu=f"A batchadat szerint a hely {row['passage_count']} passage-place kapcsolattal szerepel.",
                evidence_type="biblical_text_link",
                confidence="medium",
                passage_refs=passage_refs[:12],
                limitations_hu="Ez előfordulási és kapcsolatadat, nem önmagában kész bibliai jelentőség-leírás.",
            )
        )
    event_refs = []
    seen_keys: set[str] = set()
    for stop in route_stops:
        key = "|".join(stop.get("passage_refs") or [])
        if key and key not in seen_keys:
            seen_keys.add(key)
            event_refs.append((stop.get("passage_refs") or [], stop.get("event_summary_hu") or "Route-stop esemény."))
        if len(event_refs) >= 6:
            break
    if not event_refs:
        for ref in passage_refs[:6]:
            key = compact_ref_key(ref)
            if key not in seen_keys:
                seen_keys.add(key)
                event_refs.append(([ref], "Passage-place kapcsolat további eseménycsoportosítást igényel."))
    for refs, summary in event_refs:
        section_evidence["key_events"].append(
            evidence_item(
                place_id=place_id,
                section="key_events",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu=summary,
                evidence_type="biblical_text_link",
                confidence="medium",
                passage_refs=refs,
                limitations_hu="A végleges key event szerkesztéshez emberi/forráskritikai csoportosítás szükséges.",
            )
        )


def add_structured_place_evidence(section_evidence: dict[str, list[dict[str, Any]]], row: dict[str, Any], place: dict[str, Any]) -> None:
    place_id = row["place_id"]
    if place.get("modern_name") or place.get("modern_country"):
        section_evidence["modern_context"].append(
            evidence_item(
                place_id=place_id,
                section="modern_context",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu="A canonical rekord modern azonosítási mezőket tartalmaz.",
                evidence_type="structured_metadata",
                confidence="medium",
                geographical_scope=", ".join(part for part in [place.get("modern_name"), place.get("modern_country")] if part),
                limitations_hu="A modern mező külön intézményi ellenőrzést igényelhet.",
            )
        )
    section_evidence["identification_notes"].append(
        evidence_item(
            place_id=place_id,
            section="identification_notes",
            source_ref="openbible_geocoding_cc_by_4_0",
            claim_hu=f"A canonical rekord azonosítási státusza: {place.get('identification_status')}.",
            evidence_type="structured_metadata",
            confidence="medium" if place.get("identification_status") in {"certain", "probable"} else "low",
            limitations_hu=place.get("confidence_note_hu"),
        )
    )
    if place.get("ancient_region") or place.get("region_hu") or place.get("place_type"):
        section_evidence["ancient_geography"].append(
            evidence_item(
                place_id=place_id,
                section="ancient_geography",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu="A canonical rekord ókori régióra, helytípusra vagy térségi besorolásra vonatkozó strukturált mezőket tartalmaz.",
                evidence_type="structured_metadata",
                confidence="medium",
                geographical_scope=place.get("ancient_region") or place.get("region_hu") or place.get("place_type"),
                limitations_hu="Ez nem helyettesít szakmai ókori földrajzi háttérforrást.",
            )
        )


def add_source_candidate_evidence(section_evidence: dict[str, list[dict[str, Any]]], row: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    place_id = row["place_id"]
    for candidate in candidates:
        place_ids = set(candidate.get("place_ids") or [])
        if place_id not in place_ids:
            continue
        for section in candidate.get("section_names") or []:
            if section not in section_evidence:
                continue
            section_evidence[section].append(
                evidence_item(
                    place_id=place_id,
                    section=section,
                    source_ref=candidate["candidate_id"],
                    claim_hu=f"A source candidate közvetlen vagy kontextuális forrásként jelölt ehhez a szakaszhoz: {candidate['title']}.",
                    evidence_type="direct_statement" if candidate["relevance_status"] == "direct" else "scholarly_inference",
                    confidence=candidate["reliability_status"],
                    limitations_hu=candidate.get("limitations_hu"),
                    usable_for_drafting=candidate["reuse_status"] in {"approved", "citation_only"},
                )
            )


def related_place_ids(group: dict[str, Any] | None, place_id: str) -> list[str]:
    if not group:
        return []
    return [item for item in group.get("member_place_ids", []) if item != place_id]


def coverage_for_packet(
    row: dict[str, Any],
    section_evidence: dict[str, list[dict[str, Any]]],
    source_ids: set[str],
    candidates: list[dict[str, Any]],
    group: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    usable_sections = [
        section for section, items in section_evidence.items() if any(item["usable_for_drafting"] for item in items)
    ]
    evidence_items = [item for items in section_evidence.values() for item in items]
    candidate_ids = {item["candidate_id"] for item in evidence_items if item.get("candidate_id")}
    approved_candidate_count = sum(
        1 for candidate_id in candidate_ids if candidate_by_id.get(candidate_id, {}).get("reuse_status") == "approved"
    )
    institutional_source_count = sum(
        1
        for candidate_id in candidate_ids
        if candidate_by_id.get(candidate_id, {}).get("source_type")
        in {"official_archaeological_site", "university_project", "museum", "heritage_authority", "excavation_project", "peer_reviewed_publication"}
    )
    confidence_counts = Counter(item["confidence"] for item in evidence_items)
    remaining_gaps = [
        section
        for section in row.get("required_sections", [])
        if not section_evidence.get(section)
    ]
    ready_for_drafting = not group or group.get("review_status") != "needs_review"
    ready_for_drafting = ready_for_drafting and len(usable_sections) >= 2 and len(evidence_items) >= 2
    ready_for_source_backed = (
        ready_for_drafting
        and len(usable_sections) >= 3
        and (len(source_ids) + approved_candidate_count) >= 2
        and ("key_events" in usable_sections or "biblical_significance" in usable_sections)
        and not any(section in remaining_gaps for section in ("biblical_significance", "key_events", "identification_notes"))
    )
    possible_featured = (
        ready_for_source_backed
        and len(usable_sections) >= 4
        and institutional_source_count >= 2
        and ("archaeology" in usable_sections or "historical_context" in usable_sections)
        and not remaining_gaps
    )
    return {
        "place_id": row["place_id"],
        "name_hu": row["name_hu"],
        "candidate_source_count": len(candidate_ids),
        "approved_source_count": len(source_ids) + approved_candidate_count,
        "institutional_source_count": institutional_source_count,
        "section_coverage": {section: bool(items) for section, items in section_evidence.items()},
        "evidence_item_count": len(evidence_items),
        "confidence_distribution": dict(confidence_counts),
        "archaeology_coverage": bool(section_evidence["archaeology"]),
        "historical_context_coverage": bool(section_evidence["historical_context"]),
        "identification_coverage": bool(section_evidence["identification_notes"]),
        "remaining_source_gaps": remaining_gaps,
        "ready_for_drafting": ready_for_drafting,
        "ready_for_source_backed": ready_for_source_backed,
        "possible_featured_candidate": possible_featured,
        "blocking_issues": row.get("blocking_issues", []) + (["profile_group_needs_review"] if group and group.get("review_status") == "needs_review" else []),
        "coverage_status": "featured_candidate" if possible_featured else "source_backed_candidate" if ready_for_source_backed else "draftable" if ready_for_drafting else "blocked",
    }


def blocked_item(row: dict[str, Any], section: str, reason: str, attempted: list[str], next_action: str, blocks_drafting: bool, blocks_source_backed: bool) -> dict[str, Any]:
    return {
        "place_id": row["place_id"],
        "section_name": section,
        "blocking_reason": reason,
        "attempted_sources": attempted,
        "required_source_type": " or ".join(source_types_for_section(section)),
        "next_action": next_action,
        "blocks_drafting": blocks_drafting,
        "blocks_source_backed": blocks_source_backed,
        "notes_hu": "A kutatási fázis nem tölt ki hiányzó szakmai állítást forrás nélkül.",
    }


def source_types_for_section(section: str) -> list[str]:
    mapping = {
        "biblical_significance": ["biblical_text_dataset", "academic_gazetteer"],
        "key_events": ["biblical_text_dataset"],
        "ancient_geography": ["academic_gazetteer", "official_geographical_source"],
        "historical_context": ["university_project", "museum", "peer_reviewed_publication"],
        "archaeology": ["official_archaeological_site", "excavation_project", "heritage_authority", "museum"],
        "modern_context": ["official_geographical_source", "academic_gazetteer"],
        "identification_notes": ["academic_gazetteer", "official_geographical_source"],
        "homiletical_context": ["biblical_text_dataset", "academic_gazetteer", "peer_reviewed_publication"],
    }
    return mapping.get(section, [])


def sorted_blocked(blocked_rows: list[dict[str, Any]], batch_blocked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(blocked_rows)
    for blocked in batch_blocked:
        rows.append(
            {
                "place_id": blocked["place_id"],
                "section_name": "record_resolution",
                "blocking_reason": blocked["blocking_reason"],
                "attempted_sources": [],
                "required_source_type": "",
                "next_action": blocked.get("recommended_next_action"),
                "blocks_drafting": True,
                "blocks_source_backed": True,
                "notes_hu": blocked.get("required_resolution"),
            }
        )
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for row in sorted(rows, key=lambda item: (item["place_id"], item["section_name"], item["blocking_reason"])):
        key = (row["place_id"], row["section_name"], row["blocking_reason"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def ready_for_drafting_rows(coverage_rows: list[dict[str, Any]], packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packets_by_id = {packet["place_id"]: packet for packet in packets}
    rows = []
    for coverage in coverage_rows:
        if not coverage["ready_for_drafting"]:
            continue
        packet = packets_by_id[coverage["place_id"]]
        available_sections = [
            section for section, covered in coverage["section_coverage"].items() if covered
        ]
        source_ids = packet["source_ids"]
        target = (
            "featured_candidate"
            if coverage["possible_featured_candidate"]
            else "source_backed"
            if coverage["ready_for_source_backed"]
            else "partial"
        )
        rows.append(
            {
                "place_id": coverage["place_id"],
                "name_hu": coverage["name_hu"],
                "available_sections": available_sections,
                "evidence_count": coverage["evidence_item_count"],
                "approved_source_ids": source_ids,
                "institutional_source_count": coverage["institutional_source_count"],
                "unresolved_gaps": coverage["remaining_source_gaps"],
                "drafting_priority": coverage["evidence_item_count"] * 10 + coverage["institutional_source_count"] * 25,
                "recommended_profile_target": target,
                "drafting_notes_hu": "Draft csak az evidence packet alapján készülhet; ez még nem végleges enrichment szöveg.",
            }
        )
    rows.sort(key=lambda item: (-item["drafting_priority"], item["place_id"]))
    return rows[:20]


def coverage_summary(coverage_rows: list[dict[str, Any]], candidates: list[dict[str, Any]], blocked_rows: list[dict[str, Any]]) -> dict[str, Any]:
    section_counts = Counter()
    confidence_counts = Counter()
    for row in coverage_rows:
        for section, covered in row["section_coverage"].items():
            if covered:
                section_counts[section] += 1
        confidence_counts.update(row["confidence_distribution"])
    return {
        "internet_research_status": "limited_web_discovery_plus_existing_registry",
        "place_count": len(coverage_rows),
        "source_candidate_count": len(candidates),
        "approved_registry_source_promotions": 0,
        "institutional_or_scholarly_candidate_count": sum(
            1
            for candidate in candidates
            if candidate["source_type"]
            in {"official_archaeological_site", "university_project", "academic_gazetteer", "museum", "heritage_authority", "excavation_project", "peer_reviewed_publication"}
        ),
        "evidence_item_count": sum(row["evidence_item_count"] for row in coverage_rows),
        "section_coverage": dict(section_counts),
        "confidence_distribution": dict(confidence_counts),
        "ready_for_drafting_count": sum(1 for row in coverage_rows if row["ready_for_drafting"]),
        "ready_for_source_backed_count": sum(1 for row in coverage_rows if row["ready_for_source_backed"]),
        "featured_candidate_count": sum(1 for row in coverage_rows if row["possible_featured_candidate"]),
        "research_blocked_count": len(blocked_rows),
        "largest_source_gaps": dict(Counter(gap for row in coverage_rows for gap in row["remaining_source_gaps"]).most_common(8)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build source candidates and evidence packets for batch 001.")
    parser.add_argument("--batch-number", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_number != 1:
        raise SystemExit("Only batch 001 is currently supported by this research builder.")
    build_packets()


if __name__ == "__main__":
    main()
