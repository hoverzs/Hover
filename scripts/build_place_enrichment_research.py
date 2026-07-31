from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"

SOURCE_CANDIDATES_PATH = RESEARCH_DIR / "batch_001_source_candidates.json"
EVIDENCE_PACKETS_PATH = RESEARCH_DIR / "batch_001_evidence_packets.json"
COVERAGE_REPORT_PATH = RESEARCH_DIR / "batch_001_coverage_report.json"
READY_FOR_DRAFTING_PATH = RESEARCH_DIR / "batch_001_ready_for_drafting.json"
RESEARCH_BLOCKED_PATH = RESEARCH_DIR / "batch_001_research_blocked.json"
INTEGRITY_AUDIT_PATH = RESEARCH_DIR / "batch_001_evidence_integrity_audit.json"
SOURCE_VALIDATION_PATH = RESEARCH_DIR / "batch_001_source_validation_report.json"
ACQUISITION_QUEUE_PATH = RESEARCH_DIR / "batch_001_source_acquisition_queue.json"
STRICT_COVERAGE_PATH = RESEARCH_DIR / "batch_001_strict_coverage_report.json"
BIBLICAL_DRAFT_READY_PATH = RESEARCH_DIR / "batch_001_biblical_draft_ready.json"
PARTIAL_PROFILE_READY_PATH = RESEARCH_DIR / "batch_001_partial_profile_ready.json"
SOURCE_BACKED_READY_PATH = RESEARCH_DIR / "batch_001_source_backed_ready.json"
FEATURED_CANDIDATES_PATH = RESEARCH_DIR / "batch_001_featured_candidates.json"

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

SOURCE_STRENGTH_CLASSES = (
    "A_biblical_primary",
    "B_structured_gazetteer",
    "C_external_institutional",
    "D_external_scholarly",
    "E_contextual_secondary",
    "F_inference",
    "G_unsupported",
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

INSTITUTIONAL_TYPES = {
    "official_archaeological_site",
    "university_project",
    "museum",
    "heritage_authority",
    "excavation_project",
}
SCHOLARLY_TYPES = {"peer_reviewed_publication"}
EXTERNAL_CDE = {
    "C_external_institutional",
    "D_external_scholarly",
    "E_contextual_secondary",
}
MEANINGFUL_SECTIONS = {
    "biblical_significance",
    "key_events",
    "ancient_geography",
    "historical_context",
    "archaeology",
    "modern_context",
    "identification_notes",
    "homiletical_context",
}
REGION_LIKE_TYPES = {"region", "territory", "country", "body of water", "river", "sea"}

# Live-validated institutional candidates (2026-07-30).
WEB_DISCOVERED_CANDIDATES = [
    {
        "candidate_id": "web_unesco_ancient_thebes_87",
        "place_ids": ["egypt"],
        "section_names": ["historical_context", "archaeology", "modern_context"],
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
        "supported_topics": [
            "Ancient Egypt heritage context",
            "Thebes and Nile Valley setting",
        ],
        "limitations_hu": (
            "Egyiptom egészére kontextuális örökségvédelmi forrás; "
            "nem minden egyiptomi bibliai helyre közvetlen lelőhelyadat."
        ),
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
        "place_specific": False,
        "claim_support_notes_hu": (
            "Az oldal megerősíti Théba / Nílus-völgyi ókori egyiptomi "
            "civilizációs és régészeti kontextusát."
        ),
    },
    {
        "candidate_id": "web_unesco_tyre_299",
        "place_ids": ["tyre"],
        "section_names": ["historical_context", "archaeology", "modern_context"],
        "title": "Tyre",
        "institution_or_author": "UNESCO World Heritage Centre",
        "source_type": "heritage_authority",
        "url_or_identifier": "https://whc.unesco.org/en/list/299",
        "publication_date": "1984",
        "access_date": "2026-07-30",
        "language": "en",
        "license": "citation_only_review_required",
        "attribution": "UNESCO World Heritage Centre",
        "reuse_status": "citation_only",
        "reliability_status": "high",
        "relevance_status": "direct",
        "supported_topics": [
            "Phoenician Tyre historical role",
            "Roman and later archaeological remains",
        ],
        "limitations_hu": "Helyspecifikus UNESCO WHC lap; citation-only szöveghasználat.",
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
        "place_specific": True,
        "claim_support_notes_hu": (
            "A lap Tírusz föníciai szerepét és főként római kori régészeti maradványait írja le."
        ),
    },
    {
        "candidate_id": "web_unesco_jerusalem_148",
        "place_ids": ["zion", "judea_1", "mount_zion"],
        "section_names": ["historical_context", "modern_context", "identification_notes"],
        "title": "Old City of Jerusalem and its Walls",
        "institution_or_author": "UNESCO World Heritage Centre",
        "source_type": "heritage_authority",
        "url_or_identifier": "https://whc.unesco.org/en/list/148",
        "publication_date": "1981",
        "access_date": "2026-07-30",
        "language": "en",
        "license": "citation_only_review_required",
        "attribution": "UNESCO World Heritage Centre",
        "reuse_status": "citation_only",
        "reliability_status": "high",
        "relevance_status": "contextual",
        "supported_topics": [
            "Jerusalem old city heritage setting",
            "Multi-religious historical significance",
        ],
        "limitations_hu": (
            "Jeruzsálem óvárosára vonatkozik; Sion / Júdea rekordoknál kontextuális, "
            "nem helyettesít külön Sion-lelőhelylapot."
        ),
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
        "place_specific": False,
        "claim_support_notes_hu": (
            "Az oldal Jeruzsálem óvárosának örökségi és történeti kontextusát dokumentálja."
        ),
    },
    {
        "candidate_id": "web_unesco_petra_326",
        "place_ids": ["edom"],
        "section_names": ["historical_context", "modern_context"],
        "title": "Petra",
        "institution_or_author": "UNESCO World Heritage Centre",
        "source_type": "heritage_authority",
        "url_or_identifier": "https://whc.unesco.org/en/list/326",
        "publication_date": "1985",
        "access_date": "2026-07-30",
        "language": "en",
        "license": "citation_only_review_required",
        "attribution": "UNESCO World Heritage Centre",
        "reuse_status": "citation_only",
        "reliability_status": "high",
        "relevance_status": "contextual",
        "supported_topics": [
            "Nabataean caravan-city context between Arabia, Egypt and Syria-Phoenicia",
        ],
        "limitations_hu": (
            "Petra lelőhelylap; Edóm egészére csak kontextuális. "
            "Nem indokol településspecifikus archaeology sectiont Edómra."
        ),
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
        "place_specific": False,
        "claim_support_notes_hu": (
            "A lap a nabateus karavánváros és a tágabb Arábia–Egyiptom–Szíria "
            "kereszteződés kontextusát írja le."
        ),
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
        "attribution": (
            "Pleiades contributors; Ancient World Mapping Center and "
            "Institute for the Study of the Ancient World"
        ),
        "reuse_status": "approved",
        "reliability_status": "high",
        "relevance_status": "contextual",
        "supported_topics": ["Ancient gazetteer methodology", "Place identity and names"],
        "limitations_hu": (
            "Módszertani gazetteer-oldal; csak akkor közvetlen, ha konkrét "
            "Pleiades rekord is fel van oldva."
        ),
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
        "place_specific": False,
        "claim_support_notes_hu": "Az oldal a Pleiades gazetteer modelljét ismerteti.",
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
        "supported_topics": [
            "Archaeological responsibility in Judea and Samaria",
            "Site preservation context",
        ],
        "limitations_hu": (
            "Intézményi oldal; a live fetch Cloudflare-blokkot kapott, "
            "ezért claim-támogatás nem ellenőrizhető."
        ),
        "discovery_method": "web_search",
        "duplicate_of_candidate_id": None,
        "review_status": "candidate_only",
        "place_specific": False,
        "claim_support_notes_hu": "URL formátum ismert; tartalom live ellenőrzése sikertelen.",
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


def is_https_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


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
    return dict(by_place)


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


def strength_for_registry_source(source: dict[str, Any], section: str) -> str:
    source_type = str(source.get("source_type") or "")
    category = source_type_category(source_type)
    if category == "biblical_text_dataset":
        if section in {"biblical_significance", "key_events"}:
            return "A_biblical_primary"
        if section in {"ancient_geography", "identification_notes", "modern_context"}:
            return "B_structured_gazetteer"
        return "E_contextual_secondary"
    if category == "academic_gazetteer":
        return "B_structured_gazetteer"
    if category in INSTITUTIONAL_TYPES or "heritage" in source_type or "official" in source_type:
        return "C_external_institutional"
    if category in SCHOLARLY_TYPES:
        return "D_external_scholarly"
    return "E_contextual_secondary"


def strength_for_candidate(candidate: dict[str, Any], section: str) -> str:
    source_type = candidate.get("source_type") or ""
    relevance = candidate.get("relevance_status") or "contextual"
    if source_type == "biblical_text_dataset":
        if section in {"biblical_significance", "key_events"}:
            return "A_biblical_primary"
        return "B_structured_gazetteer"
    if source_type == "academic_gazetteer":
        return "B_structured_gazetteer"
    if source_type in INSTITUTIONAL_TYPES:
        if relevance == "direct" and candidate.get("place_specific"):
            return "C_external_institutional"
        return "E_contextual_secondary" if section != "archaeology" else "C_external_institutional"
    if source_type in SCHOLARLY_TYPES:
        return "D_external_scholarly"
    if relevance != "direct":
        return "E_contextual_secondary"
    return "E_contextual_secondary"


def evidence_item(
    *,
    place_id: str,
    section: str,
    source_ref: str,
    claim_hu: str,
    evidence_type: str,
    confidence: str,
    source_strength_class: str,
    passage_refs: list[str] | None = None,
    chronology: str | None = None,
    geographical_scope: str | None = None,
    record_specific: bool = True,
    shared_profile_evidence: bool = False,
    limitations_hu: str | None = None,
    usable_for_drafting: bool | None = None,
    approved_source_id: str | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    if source_strength_class not in SOURCE_STRENGTH_CLASSES:
        raise ValueError(f"Invalid source_strength_class: {source_strength_class}")
    if usable_for_drafting is None:
        usable_for_drafting = source_strength_class != "G_unsupported"
    if source_strength_class == "G_unsupported":
        usable_for_drafting = False
    if candidate_id is None and (
        source_ref.startswith("web_")
        or source_ref.startswith("existing_")
        or source_ref.startswith("catalog_")
    ):
        candidate_id = source_ref
    if approved_source_id is None and candidate_id is None:
        approved_source_id = source_ref
    return {
        "evidence_id": stable_id("ev", place_id, section, source_ref, claim_hu, source_strength_class),
        "candidate_id": candidate_id,
        "approved_source_id": approved_source_id,
        "claim_hu": claim_hu,
        "evidence_type": evidence_type,
        "confidence": confidence,
        "source_strength_class": source_strength_class,
        "passage_refs": passage_refs or [],
        "chronology": chronology,
        "geographical_scope": geographical_scope,
        "record_specific": record_specific,
        "shared_profile_evidence": shared_profile_evidence,
        "limitations_hu": limitations_hu,
        "usable_for_drafting": usable_for_drafting,
    }


def dedupe_evidence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = "|".join(
            [
                item.get("source_strength_class") or "",
                item.get("evidence_type") or "",
                item.get("claim_hu") or "",
                item.get("approved_source_id") or item.get("candidate_id") or "",
            ]
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(item)
            continue
        refs = list(dict.fromkeys((existing.get("passage_refs") or []) + (item.get("passage_refs") or [])))
        existing["passage_refs"] = refs
        if item.get("usable_for_drafting") and not existing.get("usable_for_drafting"):
            existing["usable_for_drafting"] = True
        if item.get("approved_source_id") and not existing.get("approved_source_id"):
            existing["approved_source_id"] = item["approved_source_id"]
            existing["candidate_id"] = item.get("candidate_id")
    return list(merged.values())


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
        "reuse_status": "approved" if str(source.get("license") or "").upper().startswith("CC") else "citation_only",
        "reliability_status": (
            "high"
            if source.get("reliability_scope")
            in {"official_institutional", "scholarly_curated", "institutional_scholarly"}
            else "medium"
        ),
        "relevance_status": "direct" if used_by.get(source["source_id"]) else "contextual",
        "supported_topics": [source.get("allowed_use") or ""],
        "limitations_hu": source.get("notes_hu"),
        "discovery_method": "existing_registry",
        "duplicate_of_candidate_id": None,
        "review_status": "accepted_existing_source",
        "place_specific": bool(used_by.get(source["source_id"])),
    }


def catalog_pleiades_candidates(
    manifest: list[dict[str, Any]],
    places_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []
    for row in manifest:
        place = places_by_id[row["place_id"]]
        pleiades_id = place.get("pleiades_id")
        if not pleiades_id:
            continue
        candidate_id = f"catalog_pleiades_{pleiades_id}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "place_ids": [row["place_id"]],
                "section_names": ["ancient_geography", "identification_notes", "modern_context"],
                "title": f"Pleiades place {pleiades_id}",
                "institution_or_author": "Pleiades",
                "source_type": "academic_gazetteer",
                "url_or_identifier": f"https://pleiades.stoa.org/places/{pleiades_id}",
                "publication_date": None,
                "access_date": "2026-07-30",
                "language": "en",
                "license": "CC-BY-3.0",
                "attribution": (
                    "Pleiades contributors; Ancient World Mapping Center and "
                    "Institute for the Study of the Ancient World"
                ),
                "reuse_status": "approved",
                "reliability_status": "high",
                "relevance_status": "direct",
                "supported_topics": ["földrajzi azonosítás; névváltozat; ókori földrajz"],
                "limitations_hu": (
                    "A Pleiades ID a canonical katalógusból származik. "
                    "A live oldal botvédelem miatt nem volt tartalmilag ellenőrizhető."
                ),
                "discovery_method": "catalog_external_id",
                "duplicate_of_candidate_id": None,
                "review_status": "candidate_only",
                "place_specific": True,
                "claim_support_notes_hu": (
                    "Külső azonosító a helyi katalógusban; tartalmi claim live fetch nélkül."
                ),
            }
        )
    return candidates


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        url = str(candidate.get("url_or_identifier") or candidate["candidate_id"]).split("?", 1)[0].rstrip("/")
        if url in by_url:
            existing = by_url[url]
            existing_places = set(existing.get("place_ids") or [])
            existing_places.update(candidate.get("place_ids") or [])
            existing["place_ids"] = sorted(existing_places)
            continue
        by_url[url] = dict(candidate)
    return sorted(by_url.values(), key=lambda item: item["candidate_id"])


def add_biblical_evidence(
    section_evidence: dict[str, list[dict[str, Any]]],
    row: dict[str, Any],
    passage_refs: list[str],
    route_stops: list[dict[str, Any]],
) -> None:
    place_id = row["place_id"]
    if passage_refs:
        section_evidence["biblical_significance"].append(
            evidence_item(
                place_id=place_id,
                section="biblical_significance",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu=(
                    "A passage-place index konkrét bibliai szakaszokhoz köti a helyet; "
                    "ez bibliai jelentőség-vázlat alapja lehet."
                ),
                evidence_type="biblical_text_link",
                confidence="medium",
                source_strength_class="A_biblical_primary",
                passage_refs=passage_refs[:12],
                limitations_hu=(
                    "Ez szövegkapcsolat és hivatkozás-halmaz, nem önmagában kész "
                    "bibliai jelentőség-próza. Az előfordulásszám önmagában nem elég."
                ),
                approved_source_id="openbible_geocoding_cc_by_4_0",
            )
        )
        if len(passage_refs) >= 2:
            section_evidence["biblical_significance"].append(
                evidence_item(
                    place_id=place_id,
                    section="biblical_significance",
                    source_ref="openbible_geocoding_cc_by_4_0",
                    claim_hu=(
                        "Több elkülöníthető passage-place kapcsolat áll rendelkezésre "
                        "a bibliai jelentőség szakasz vázlatához."
                    ),
                    evidence_type="biblical_text_link",
                    confidence="medium",
                    source_strength_class="A_biblical_primary",
                    passage_refs=passage_refs[12:24] or passage_refs[:2],
                    limitations_hu="A szakaszok tematikus csoportosítása még szerkesztői feladat.",
                    approved_source_id="openbible_geocoding_cc_by_4_0",
                )
            )

    event_refs: list[tuple[list[str], str]] = []
    seen_keys: set[str] = set()
    for stop in route_stops:
        refs = stop.get("passage_refs") or []
        key = "|".join(refs)
        summary = (stop.get("event_summary_hu") or "").strip()
        if not refs or not summary or key in seen_keys:
            continue
        seen_keys.add(key)
        event_refs.append((refs, summary))
        if len(event_refs) >= 6:
            break
    if not event_refs:
        for ref in passage_refs[:6]:
            key = compact_ref_key(ref)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            event_refs.append(
                (
                    [ref],
                    f"A hely a következő bibliai szakaszhoz kapcsolódik: {ref}.",
                )
            )
    for refs, summary in event_refs:
        section_evidence["key_events"].append(
            evidence_item(
                place_id=place_id,
                section="key_events",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu=summary,
                evidence_type="biblical_text_link",
                confidence="medium",
                source_strength_class="A_biblical_primary",
                passage_refs=refs,
                limitations_hu=(
                    "A végleges key event szerkesztéshez forráskritikai csoportosítás szükséges."
                ),
                approved_source_id="openbible_geocoding_cc_by_4_0",
            )
        )


def add_structured_place_evidence(
    section_evidence: dict[str, list[dict[str, Any]]],
    row: dict[str, Any],
    place: dict[str, Any],
    pleiades_candidate_ids: dict[str, str] | None = None,
) -> None:
    place_id = row["place_id"]
    pleiades_candidate_ids = pleiades_candidate_ids or {}
    if place.get("modern_name") or place.get("modern_country"):
        section_evidence["modern_context"].append(
            evidence_item(
                place_id=place_id,
                section="modern_context",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu="A canonical rekord modern azonosítási mezőket tartalmaz.",
                evidence_type="structured_metadata",
                confidence="medium",
                source_strength_class="B_structured_gazetteer",
                geographical_scope=", ".join(
                    part for part in [place.get("modern_name"), place.get("modern_country")] if part
                ),
                limitations_hu="A modern mező külön intézményi ellenőrzést igényelhet.",
                approved_source_id="openbible_geocoding_cc_by_4_0",
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
            source_strength_class="B_structured_gazetteer",
            limitations_hu=place.get("confidence_note_hu"),
            approved_source_id="openbible_geocoding_cc_by_4_0",
        )
    )
    if place.get("ancient_region") or place.get("region_hu") or place.get("place_type"):
        section_evidence["ancient_geography"].append(
            evidence_item(
                place_id=place_id,
                section="ancient_geography",
                source_ref="openbible_geocoding_cc_by_4_0",
                claim_hu=(
                    "A canonical rekord ókori régióra, helytípusra vagy térségi "
                    "besorolásra vonatkozó strukturált mezőket tartalmaz."
                ),
                evidence_type="structured_metadata",
                confidence="medium",
                source_strength_class="B_structured_gazetteer",
                geographical_scope=place.get("ancient_region")
                or place.get("region_hu")
                or place.get("place_type"),
                limitations_hu=(
                    "Koordináta / place_type önmagában csak basic/partial geography; "
                    "nem source-backed részletes ókori földrajz."
                ),
                approved_source_id="openbible_geocoding_cc_by_4_0",
            )
        )
    if place.get("pleiades_id"):
        pleiades_ref = pleiades_candidate_ids.get(
            str(place["pleiades_id"]),
            f"catalog_pleiades_{place['pleiades_id']}",
        )
        section_evidence["identification_notes"].append(
            evidence_item(
                place_id=place_id,
                section="identification_notes",
                source_ref=pleiades_ref,
                claim_hu=f"A katalógus Pleiades külső azonosítót rögzít: {place['pleiades_id']}.",
                evidence_type="structured_metadata",
                confidence="medium",
                source_strength_class="B_structured_gazetteer",
                limitations_hu="A live Pleiades oldal tartalma ebben a körben nem volt ellenőrizhető.",
                candidate_id=pleiades_ref if pleiades_ref.startswith(("catalog_", "existing_")) else None,
                approved_source_id=(
                    None
                    if pleiades_ref.startswith(("catalog_", "existing_", "web_"))
                    else pleiades_ref
                ),
            )
        )
        section_evidence["ancient_geography"].append(
            evidence_item(
                place_id=place_id,
                section="ancient_geography",
                source_ref=pleiades_ref,
                claim_hu=(
                    "A helyhez Pleiades gazetteer-azonosító tartozik a canonical rekordban."
                ),
                evidence_type="structured_metadata",
                confidence="medium",
                source_strength_class="B_structured_gazetteer",
                limitations_hu="Részletes ókori földrajzi állításhoz további C/D/E forrás kell.",
                candidate_id=pleiades_ref if pleiades_ref.startswith(("catalog_", "existing_")) else None,
                approved_source_id=(
                    None
                    if pleiades_ref.startswith(("catalog_", "existing_", "web_"))
                    else pleiades_ref
                ),
            )
        )


def add_source_candidate_evidence(
    section_evidence: dict[str, list[dict[str, Any]]],
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    registry_by_id: dict[str, dict[str, Any]],
    validation_by_id: dict[str, dict[str, Any]] | None = None,
) -> None:
    place_id = row["place_id"]
    place_type = str(row.get("place_type") or "")
    validation_by_id = validation_by_id or {}
    for candidate in candidates:
        place_ids = set(candidate.get("place_ids") or [])
        if place_id not in place_ids and "multiple" not in place_ids:
            continue
        validation = validation_by_id.get(candidate["candidate_id"]) or {}
        if validation.get("validation_status") in {"unclear", "rejected", "metadata_only"}:
            continue
        # Avoid generic OpenBible candidate duplication when approved source already present.
        if candidate["candidate_id"].startswith("existing_openbible"):
            continue
        if candidate["candidate_id"] == "web_pleiades_ancient_places":
            continue
        if candidate["candidate_id"].startswith("existing_") and candidate["relevance_status"] != "direct":
            if place_id not in place_ids:
                continue
        for section in candidate.get("section_names") or []:
            if section not in section_evidence:
                continue
            if section == "archaeology" and place_type in REGION_LIKE_TYPES and not candidate.get(
                "place_specific"
            ):
                # Egypt UNESCO Thebes: allow contextual archaeology for Egypt region.
                if place_id != "egypt":
                    continue
            strength = strength_for_candidate(candidate, section)
            claim = candidate.get("claim_support_notes_hu") or (
                f"Ellenőrzött intézményi/szakmai forrás ehhez a szakaszhoz: {candidate['title']}."
            )
            section_evidence[section].append(
                evidence_item(
                    place_id=place_id,
                    section=section,
                    source_ref=candidate["candidate_id"],
                    claim_hu=claim,
                    evidence_type=(
                        "direct_statement"
                        if candidate.get("relevance_status") == "direct"
                        else "scholarly_inference"
                    ),
                    confidence=candidate.get("reliability_status") or "medium",
                    source_strength_class=strength,
                    limitations_hu=candidate.get("limitations_hu"),
                    usable_for_drafting=candidate.get("reuse_status") in {"approved", "citation_only"},
                    candidate_id=candidate["candidate_id"],
                )
            )


def related_place_ids(group: dict[str, Any] | None, place_id: str) -> list[str]:
    if not group:
        return []
    return [item for item in group.get("member_place_ids", []) if item != place_id]


def valid_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if item.get("usable_for_drafting")
        and item.get("source_strength_class") != "G_unsupported"
    ]


def strength_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item.get("source_strength_class") or "G_unsupported" for item in items)
    return {key: counts.get(key, 0) for key in SOURCE_STRENGTH_CLASSES}


def section_source_status(section: str, items: list[dict[str, Any]]) -> str:
    usable = valid_items(items)
    if not usable:
        return "unsupported"
    classes = {item["source_strength_class"] for item in usable}
    if classes <= {"A_biblical_primary"}:
        return "biblical_only"
    if classes <= {"A_biblical_primary", "B_structured_gazetteer"}:
        if "B_structured_gazetteer" in classes and "A_biblical_primary" not in classes:
            return "gazetteer_only"
        if classes == {"A_biblical_primary", "B_structured_gazetteer"}:
            return "partially_supported" if section not in {"biblical_significance", "key_events"} else "biblical_only"
        return "gazetteer_only"
    if "D_external_scholarly" in classes:
        return "scholarly_supported"
    if "C_external_institutional" in classes:
        return "institutionally_supported"
    if classes & EXTERNAL_CDE:
        return "partially_supported"
    return "partially_supported"


def section_meets_threshold(section: str, items: list[dict[str, Any]], *, detailed: bool = False) -> tuple[bool, str]:
    usable = valid_items(items)
    classes = {item["source_strength_class"] for item in usable}
    if section == "biblical_significance":
        ok = any(item["source_strength_class"] == "A_biblical_primary" and item.get("passage_refs") for item in usable)
        return ok, "biblical_primary_with_passage_refs" if ok else "missing_biblical_primary"
    if section == "key_events":
        events = [item for item in usable if item["source_strength_class"] == "A_biblical_primary" and item.get("passage_refs")]
        ok = bool(events)
        return ok, "biblical_events_present" if ok else "missing_key_events"
    if section == "ancient_geography":
        has_b = "B_structured_gazetteer" in classes
        has_extra = bool(classes & EXTERNAL_CDE)
        if has_b and has_extra:
            return True, "gazetteer_plus_external"
        if has_b:
            return (not detailed), "gazetteer_basic_only"
        return False, "missing_geography_support"
    if section == "historical_context":
        ok = bool(classes & {"C_external_institutional", "D_external_scholarly", "E_contextual_secondary"})
        return ok, "external_historical_support" if ok else "missing_historical_external"
    if section == "archaeology":
        ok = bool(classes & {"C_external_institutional", "D_external_scholarly"})
        return ok, "institutional_or_scholarly_archaeology" if ok else "missing_archaeology_cd"
    if section == "modern_context":
        ok = bool(classes & {"B_structured_gazetteer", "C_external_institutional", "D_external_scholarly", "E_contextual_secondary"})
        return ok, "modern_support_present" if ok else "missing_modern_support"
    if section == "identification_notes":
        ok = bool(classes & {"B_structured_gazetteer", "C_external_institutional", "D_external_scholarly", "E_contextual_secondary"})
        return ok, "identification_support_present" if ok else "missing_identification_support"
    if section == "homiletical_context":
        place_specific = any(
            item.get("record_specific") and item["source_strength_class"] in EXTERNAL_CDE for item in usable
        )
        return place_specific, "place_specific_homiletical" if place_specific else "missing_homiletical_support"
    return bool(usable), "generic"


def section_source_backed(section: str, items: list[dict[str, Any]]) -> bool:
    usable = valid_items(items)
    classes = {item["source_strength_class"] for item in usable}
    status = section_source_status(section, items)
    if section in {"biblical_significance", "key_events"}:
        ok, _ = section_meets_threshold(section, items)
        return ok
    if section == "ancient_geography":
        return "B_structured_gazetteer" in classes and bool(classes & EXTERNAL_CDE)
    if section == "historical_context":
        return bool(classes & {"C_external_institutional", "D_external_scholarly", "E_contextual_secondary"})
    if section == "archaeology":
        return bool(classes & {"C_external_institutional", "D_external_scholarly"})
    if section == "modern_context":
        return bool(classes & {"C_external_institutional", "D_external_scholarly", "E_contextual_secondary"}) or (
            "B_structured_gazetteer" in classes and status in {"partially_supported", "institutionally_supported", "scholarly_supported"}
        )
    if section == "identification_notes":
        return bool(classes & {"B_structured_gazetteer", "C_external_institutional", "D_external_scholarly"})
    if section == "homiletical_context":
        ok, _ = section_meets_threshold(section, items)
        return ok
    return False


def independent_external_sources(
    items: list[dict[str, Any]],
    candidates_by_id: dict[str, dict[str, Any]],
    registry_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for item in valid_items(items):
        if item["source_strength_class"] not in EXTERNAL_CDE | {"B_structured_gazetteer"}:
            if item["source_strength_class"] == "A_biblical_primary":
                continue
        key = item.get("approved_source_id") or item.get("candidate_id")
        if not key or key in seen:
            continue
        if item["source_strength_class"] == "A_biblical_primary":
            continue
        # OpenBible counts as structured/biblical layer, not independent C/D external.
        if key in {"openbible_geocoding_cc_by_4_0", "existing_openbible_geocoding_cc_by_4_0"}:
            continue
        if item["source_strength_class"] in EXTERNAL_CDE or (
            item["source_strength_class"] == "B_structured_gazetteer"
            and not str(key).startswith("openbible")
        ):
            # For source_backed independence, B gazetteer can count as one external
            # only when paired with C/D elsewhere; tracked separately.
            seen.add(key)
            found.append(key)
    return found


def evaluate_readiness(
    *,
    row: dict[str, Any],
    section_evidence: dict[str, list[dict[str, Any]]],
    group: dict[str, Any] | None,
    candidates_by_id: dict[str, dict[str, Any]],
    registry_by_id: dict[str, dict[str, Any]],
    blocked_place_ids: set[str],
) -> dict[str, Any]:
    all_items = [item for items in section_evidence.values() for item in items]
    usable_all = valid_items(all_items)
    unsupported = [item for item in all_items if item.get("source_strength_class") == "G_unsupported"]
    section_ok = {}
    valid_sections = []
    source_backed_sections = []
    for section, items in section_evidence.items():
        ok, reason = section_meets_threshold(section, items)
        section_ok[section] = {"meets_threshold": ok, "reason": reason}
        if ok and section in MEANINGFUL_SECTIONS:
            valid_sections.append(section)
        if section_source_backed(section, items):
            source_backed_sections.append(section)

    classes_present = {item["source_strength_class"] for item in usable_all}
    cde_items = [item for item in usable_all if item["source_strength_class"] in EXTERNAL_CDE]
    cd_items = [
        item
        for item in usable_all
        if item["source_strength_class"] in {"C_external_institutional", "D_external_scholarly"}
    ]
    place_specific_cd = [
        item
        for item in cd_items
        if (item.get("candidate_id") and candidates_by_id.get(item["candidate_id"], {}).get("place_specific"))
        or (
            item.get("approved_source_id")
            and registry_by_id.get(item["approved_source_id"], {}).get("source_type")
            in {
                "official_archaeological_site",
                "international_heritage_reference",
                "scholarly_archaeological_reference",
            }
        )
    ]
    a_count = sum(1 for item in usable_all if item["source_strength_class"] == "A_biblical_primary")
    independent = independent_external_sources(usable_all, candidates_by_id, registry_by_id)
    independent_cde = [
        key
        for key in independent
        if any(
            item.get("approved_source_id") == key or item.get("candidate_id") == key
            for item in cde_items
        )
    ]
    has_cd = bool(cd_items)
    record_block = row["place_id"] in blocked_place_ids or (
        group is not None and group.get("review_status") == "needs_review"
    )

    biblical_ok = (
        ("biblical_significance" in valid_sections or "key_events" in valid_sections)
        and a_count >= 2
        and not record_block
    )
    partial_ok = (
        len(valid_sections) >= 2
        and bool(cde_items)
        and not unsupported
        and not record_block
    )
    source_backed_ok = (
        len(valid_sections) >= 3
        and len(independent_cde) >= 2
        and has_cd
        and ("biblical_significance" in valid_sections or "key_events" in valid_sections)
        and not unsupported
        and not record_block
        and not any(
            section in {"biblical_significance", "key_events", "identification_notes"}
            and section not in valid_sections
            for section in row.get("required_sections", [])
        )
    )
    # A+B only cannot be source_backed.
    if classes_present <= {"A_biblical_primary", "B_structured_gazetteer"}:
        source_backed_ok = False
        partial_ok = False
    featured_ok = (
        len(valid_sections) >= 4
        and len({item.get("approved_source_id") or item.get("candidate_id") for item in place_specific_cd}) >= 2
        and ("historical_context" in source_backed_sections or "archaeology" in source_backed_sections)
        and not record_block
        and (group is None or group.get("review_status") != "needs_review")
    )
    if classes_present <= {"A_biblical_primary", "B_structured_gazetteer"}:
        featured_ok = False

    if featured_ok:
        readiness_class = "featured_candidate"
    elif source_backed_ok:
        readiness_class = "source_backed_profile_ready"
    elif partial_ok:
        readiness_class = "partial_profile_ready"
    elif biblical_ok:
        readiness_class = "biblical_draft_ready"
    else:
        readiness_class = "not_ready"

    remaining_gaps = [
        section
        for section in row.get("required_sections", [])
        if section not in valid_sections
    ]
    return {
        "valid_sections": valid_sections,
        "source_backed_sections": source_backed_sections,
        "section_ok": section_ok,
        "a_count": a_count,
        "classes_present": sorted(classes_present),
        "independent_external_source_ids": independent,
        "independent_external_cde_count": len(independent_cde),
        "unsupported_count": len(unsupported),
        "biblical_draft_ready": biblical_ok,
        "partial_profile_ready": partial_ok,
        "source_backed_profile_ready": source_backed_ok,
        "featured_candidate": featured_ok,
        "readiness_class": readiness_class,
        "remaining_source_gaps": remaining_gaps,
        "record_block": record_block,
        "ready_for_drafting": biblical_ok or partial_ok or source_backed_ok or featured_ok,
        "ready_for_source_backed": source_backed_ok or featured_ok,
    }


def coverage_for_packet(
    row: dict[str, Any],
    section_evidence: dict[str, list[dict[str, Any]]],
    source_ids: set[str],
    candidates: list[dict[str, Any]],
    group: dict[str, Any] | None,
    registry_by_id: dict[str, dict[str, Any]],
    blocked_place_ids: set[str],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    candidates_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    all_items = [item for items in section_evidence.values() for item in items]
    usable = valid_items(all_items)
    candidate_ids = {item["candidate_id"] for item in all_items if item.get("candidate_id")}
    institutional_source_count = sum(
        1
        for candidate_id in candidate_ids
        if candidates_by_id.get(candidate_id, {}).get("source_type") in INSTITUTIONAL_TYPES
    )
    confidence_counts = Counter(item["confidence"] for item in all_items)
    strength = strength_counts(all_items)
    section_statuses = {
        section: section_source_status(section, items) for section, items in section_evidence.items()
    }
    return {
        "place_id": row["place_id"],
        "name_hu": row["name_hu"],
        "candidate_source_count": len(candidate_ids),
        "approved_source_count": len(source_ids),
        "institutional_source_count": institutional_source_count,
        "section_coverage": {
            section: bool(valid_items(items)) for section, items in section_evidence.items()
        },
        "section_source_status": section_statuses,
        "evidence_item_count": len(all_items),
        "valid_evidence_item_count": len(usable),
        "evidence_count_by_strength_class": strength,
        "confidence_distribution": dict(confidence_counts),
        "archaeology_coverage": readiness["section_ok"]["archaeology"]["meets_threshold"],
        "historical_context_coverage": readiness["section_ok"]["historical_context"]["meets_threshold"],
        "identification_coverage": readiness["section_ok"]["identification_notes"]["meets_threshold"],
        "remaining_source_gaps": readiness["remaining_source_gaps"],
        "ready_for_drafting": readiness["ready_for_drafting"],
        "ready_for_source_backed": readiness["ready_for_source_backed"],
        "biblical_draft_ready": readiness["biblical_draft_ready"],
        "partial_profile_ready": readiness["partial_profile_ready"],
        "source_backed_profile_ready": readiness["source_backed_profile_ready"],
        "possible_featured_candidate": readiness["featured_candidate"],
        "readiness_class": readiness["readiness_class"],
        "blocking_issues": row.get("blocking_issues", [])
        + (["profile_group_needs_review"] if group and group.get("review_status") == "needs_review" else [])
        + (["record_resolution_blocked"] if readiness["record_block"] else []),
        "coverage_status": readiness["readiness_class"],
    }


def blocked_item(
    row: dict[str, Any],
    section: str,
    reason: str,
    attempted: list[str],
    next_action: str,
    blocks_drafting: bool,
    blocks_source_backed: bool,
) -> dict[str, Any]:
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
        "biblical_significance": ["biblical_text_dataset"],
        "key_events": ["biblical_text_dataset"],
        "ancient_geography": ["academic_gazetteer", "official_geographical_source", "heritage_authority"],
        "historical_context": [
            "university_project",
            "museum",
            "peer_reviewed_publication",
            "heritage_authority",
        ],
        "archaeology": [
            "official_archaeological_site",
            "excavation_project",
            "heritage_authority",
            "museum",
            "peer_reviewed_publication",
        ],
        "modern_context": ["official_geographical_source", "heritage_authority", "academic_gazetteer"],
        "identification_notes": ["academic_gazetteer", "official_geographical_source"],
        "homiletical_context": [
            "peer_reviewed_publication",
            "heritage_authority",
            "university_project",
        ],
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


def drafting_scope_for(readiness_class: str, valid_sections: list[str]) -> str:
    if readiness_class == "featured_candidate":
        return "teljes source-backed profil / featured candidate"
    if readiness_class == "source_backed_profile_ready":
        return "teljes source-backed profil"
    if readiness_class == "partial_profile_ready":
        return "részleges profil; történeti/régészeti szakaszok csak a támogatott körben"
    if readiness_class == "biblical_draft_ready":
        biblical = [section for section in valid_sections if section in {"biblical_significance", "key_events", "identification_notes"}]
        return "csak " + " + ".join(biblical or ["biblical_significance", "key_events"])
    return "nem draftolható biztonságosan"


def readiness_rows(
    coverage_rows: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    readiness_by_id: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    packets_by_id = {packet["place_id"]: packet for packet in packets}
    candidates_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    buckets = {
        "biblical_draft_ready": [],
        "partial_profile_ready": [],
        "source_backed_profile_ready": [],
        "featured_candidate": [],
    }
    for coverage in coverage_rows:
        readiness = readiness_by_id[coverage["place_id"]]
        packet = packets_by_id[coverage["place_id"]]
        all_items = [item for items in packet["section_evidence"].values() for item in items]
        candidate_ids = sorted(
            {
                item["candidate_id"]
                for item in all_items
                if item.get("candidate_id") and item["candidate_id"] in candidates_by_id
            }
        )
        row = {
            "place_id": coverage["place_id"],
            "name_hu": coverage["name_hu"],
            "valid_sections": readiness["valid_sections"],
            "evidence_count_by_strength": strength_counts(all_items),
            "approved_source_ids": packet["source_ids"],
            "candidate_source_ids": candidate_ids,
            "independent_external_source_count": readiness["independent_external_cde_count"],
            "readiness_class": readiness["readiness_class"],
            "unresolved_gaps": readiness["remaining_source_gaps"],
            "blocked_sections": [
                section
                for section, meta in readiness["section_ok"].items()
                if not meta["meets_threshold"]
            ],
            "drafting_scope": drafting_scope_for(readiness["readiness_class"], readiness["valid_sections"]),
            "drafting_notes_hu": (
                "Draft csak az auditált evidence packet alapján készülhet; "
                "ez még nem végleges enrichment szöveg."
            ),
        }
        if readiness["featured_candidate"]:
            buckets["featured_candidate"].append(row)
        if readiness["source_backed_profile_ready"]:
            buckets["source_backed_profile_ready"].append(row)
        if readiness["partial_profile_ready"]:
            buckets["partial_profile_ready"].append(row)
        if readiness["biblical_draft_ready"]:
            buckets["biblical_draft_ready"].append(row)
    for key, rows in buckets.items():
        rows.sort(key=lambda item: item["place_id"])
    return buckets


def legacy_ready_for_drafting_rows(
    coverage_rows: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    readiness_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    packets_by_id = {packet["place_id"]: packet for packet in packets}
    rows = []
    for coverage in coverage_rows:
        readiness = readiness_by_id[coverage["place_id"]]
        if not readiness["ready_for_drafting"]:
            continue
        packet = packets_by_id[coverage["place_id"]]
        rows.append(
            {
                "place_id": coverage["place_id"],
                "name_hu": coverage["name_hu"],
                "available_sections": readiness["valid_sections"],
                "evidence_count": coverage["valid_evidence_item_count"],
                "approved_source_ids": packet["source_ids"],
                "institutional_source_count": coverage["institutional_source_count"],
                "unresolved_gaps": coverage["remaining_source_gaps"],
                "drafting_priority": coverage["valid_evidence_item_count"] * 10
                + coverage["institutional_source_count"] * 25,
                "recommended_profile_target": readiness["readiness_class"],
                "drafting_notes_hu": (
                    "Szigorú readiness szerint; ready_for_drafting nem jelent automatikus source-backed státuszt."
                ),
            }
        )
    rows.sort(key=lambda item: (-item["drafting_priority"], item["place_id"]))
    return rows[:20]


def validate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reports = []
    known_live = {
        "web_unesco_ancient_thebes_87": {
            "validation_status": "citation_only",
            "url_status": "reachable",
            "identity_verified": True,
            "institution_verified": True,
            "relevance_verified": True,
            "claim_support_verified": True,
            "license_status": "citation_only_review_required",
            "allowed_sections": ["historical_context", "archaeology", "modern_context"],
            "rejection_reason": None,
            "notes_hu": "UNESCO WHC Théba lap élőben ellenőrizve; citation-only promócióra alkalmas.",
        },
        "web_unesco_tyre_299": {
            "validation_status": "citation_only",
            "url_status": "reachable",
            "identity_verified": True,
            "institution_verified": True,
            "relevance_verified": True,
            "claim_support_verified": True,
            "license_status": "citation_only_review_required",
            "allowed_sections": ["historical_context", "archaeology", "modern_context"],
            "rejection_reason": None,
            "notes_hu": "UNESCO WHC Tírusz lap élőben ellenőrizve; helyspecifikus citation-only forrás.",
        },
        "web_unesco_jerusalem_148": {
            "validation_status": "citation_only",
            "url_status": "reachable",
            "identity_verified": True,
            "institution_verified": True,
            "relevance_verified": True,
            "claim_support_verified": True,
            "license_status": "citation_only_review_required",
            "allowed_sections": ["historical_context", "modern_context", "identification_notes"],
            "rejection_reason": None,
            "notes_hu": "Jeruzsálem óváros WHC lap ellenőrizve; Sion/Júdea rekordoknál kontextuális.",
        },
        "web_unesco_petra_326": {
            "validation_status": "citation_only",
            "url_status": "reachable",
            "identity_verified": True,
            "institution_verified": True,
            "relevance_verified": True,
            "claim_support_verified": True,
            "license_status": "citation_only_review_required",
            "allowed_sections": ["historical_context", "modern_context"],
            "rejection_reason": None,
            "notes_hu": "Petra WHC lap ellenőrizve; Edómra csak kontextuális, archaeology nélkül.",
        },
        "web_pleiades_ancient_places": {
            "validation_status": "metadata_only",
            "url_status": "reachable",
            "identity_verified": True,
            "institution_verified": True,
            "relevance_verified": False,
            "claim_support_verified": False,
            "license_status": "CC-BY-3.0",
            "allowed_sections": [],
            "rejection_reason": "not_place_specific",
            "notes_hu": "Módszertani gazetteer-index; nem helyspecifikus registry-promóció.",
        },
        "web_cogat_archaeology_unit": {
            "validation_status": "unclear",
            "url_status": "blocked_or_unreachable",
            "identity_verified": False,
            "institution_verified": False,
            "relevance_verified": False,
            "claim_support_verified": False,
            "license_status": "unclear",
            "allowed_sections": [],
            "rejection_reason": "live_content_unavailable",
            "notes_hu": "Cloudflare-blokk miatt a claim és intézményi tartalom nem ellenőrizhető; nem promótálandó.",
        },
    }
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        url = candidate.get("url_or_identifier")
        base = {
            "candidate_id": candidate_id,
            "url_or_identifier": url,
            "url_format_ok": is_https_url(url),
        }
        if candidate_id in known_live:
            reports.append({**base, **known_live[candidate_id]})
            continue
        if candidate_id.startswith("existing_"):
            reports.append(
                {
                    **base,
                    "validation_status": "approved"
                    if str(candidate.get("license") or "").upper().startswith("CC")
                    else "citation_only",
                    "url_status": "assumed_registry_verified",
                    "identity_verified": True,
                    "institution_verified": True,
                    "relevance_verified": True,
                    "claim_support_verified": True,
                    "license_status": candidate.get("license"),
                    "allowed_sections": candidate.get("section_names") or [],
                    "rejection_reason": None,
                    "notes_hu": "Már a központi registryben lévő forrás candidate tükre.",
                }
            )
            continue
        if candidate_id.startswith("catalog_pleiades_"):
            reports.append(
                {
                    **base,
                    "validation_status": "unclear",
                    "url_status": "bot_protected_or_unverified_live",
                    "identity_verified": True,
                    "institution_verified": True,
                    "relevance_verified": True,
                    "claim_support_verified": False,
                    "license_status": "CC-BY-3.0",
                    "allowed_sections": ["ancient_geography", "identification_notes"],
                    "rejection_reason": "live_page_not_verified",
                    "notes_hu": (
                        "Pleiades ID a katalógusból ismert, de a live oldal botvédelem miatt "
                        "nem került tartalmi ellenőrzésre; nem automatikus registry-promóció."
                    ),
                }
            )
            continue
        reports.append(
            {
                **base,
                "validation_status": "rejected",
                "url_status": "unknown",
                "identity_verified": False,
                "institution_verified": False,
                "relevance_verified": False,
                "claim_support_verified": False,
                "license_status": "unclear",
                "allowed_sections": [],
                "rejection_reason": "unvalidated_candidate",
                "notes_hu": "Nincs elegendő ellenőrzés a promócióhoz.",
            }
        )
    return sorted(reports, key=lambda item: item["candidate_id"])


def promote_sources(
    registry: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    validations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {source["source_id"]: source for source in registry}
    by_url = {
        str(source.get("identifier") or "").split("?", 1)[0].rstrip("/"): source for source in registry
    }
    validation_by_id = {row["candidate_id"]: row for row in validations}
    promotions = []
    promote_map = {
        "web_unesco_ancient_thebes_87": {
            "source_id": "unesco_ancient_thebes_87",
            "title": "Ancient Thebes with its Necropolis",
            "allowed_use": "régészet; történeti háttér; modern helyzet",
            "notes_hu": (
                "Egyiptom kontextuális örökségvédelmi forrása (Théba WHC). "
                "Citation-only; nem településspecifikus minden egyiptomi helyre."
            ),
        },
        "web_unesco_tyre_299": {
            "source_id": "unesco_tyre_299",
            "title": "Tyre",
            "allowed_use": "régészet; történeti háttér; modern helyzet",
            "notes_hu": "Tírusz helyspecifikus UNESCO WHC forrása; citation-only.",
        },
        "web_unesco_jerusalem_148": {
            "source_id": "unesco_jerusalem_148",
            "title": "Old City of Jerusalem and its Walls",
            "allowed_use": "történeti háttér; modern helyzet; azonosítási kontextus",
            "notes_hu": (
                "Jeruzsálem óváros WHC lap; Sion/Júdea rekordoknál kontextuális citation-only forrás."
            ),
        },
        "web_unesco_petra_326": {
            "source_id": "unesco_petra_326",
            "title": "Petra",
            "allowed_use": "történeti háttér; modern helyzet",
            "notes_hu": (
                "Petra WHC lap; Edómra kontextuális. Nem indokol teljes Edóm archaeology sectiont."
            ),
        },
    }
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        if candidate_id not in promote_map:
            continue
        validation = validation_by_id.get(candidate_id)
        if not validation or validation["validation_status"] not in {"approved", "citation_only"}:
            continue
        meta = promote_map[candidate_id]
        url = str(candidate.get("url_or_identifier") or "").split("?", 1)[0].rstrip("/")
        if meta["source_id"] in by_id or url in by_url:
            continue
        record = {
            "source_id": meta["source_id"],
            "title": meta["title"],
            "institution": candidate.get("institution_or_author"),
            "source_type": "international_heritage_reference",
            "identifier": candidate.get("url_or_identifier"),
            "license": "all_rights_reserved_reference_only",
            "attribution": candidate.get("attribution"),
            "allowed_use": meta["allowed_use"],
            "reliability_scope": "official_institutional",
            "notes_hu": meta["notes_hu"],
        }
        registry.append(record)
        by_id[record["source_id"]] = record
        promotions.append(
            {
                "candidate_id": candidate_id,
                "source_id": record["source_id"],
                "validation_status": validation["validation_status"],
            }
        )
    registry.sort(key=lambda item: item["source_id"])
    return registry, promotions


def build_integrity_audit(
    packets: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    readiness_by_id: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
    previous_ready_ids: set[str],
) -> dict[str, Any]:
    candidates_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    section_rows = []
    unjustified = []
    biblical_or_meta_only = []
    unsupported_claims = []
    duplicate_notes = []
    generic_proliferation = []
    for packet, coverage in zip(packets, coverage_rows):
        readiness = readiness_by_id[packet["place_id"]]
        for section, items in packet["section_evidence"].items():
            usable = valid_items(items)
            unsupported = [item for item in items if item.get("source_strength_class") == "G_unsupported"]
            candidate_count = len({item.get("candidate_id") for item in items if item.get("candidate_id")})
            registry_count = len({item.get("approved_source_id") for item in items if item.get("approved_source_id")})
            independent = len(
                {
                    item.get("approved_source_id") or item.get("candidate_id")
                    for item in usable
                    if item["source_strength_class"] in EXTERNAL_CDE
                }
            )
            current_ready_sb = packet["place_id"] in previous_ready_ids
            corrected_sb = readiness["ready_for_source_backed"]
            demotion = None
            if current_ready_sb and not corrected_sb:
                demotion = (
                    "A korábbi source-backed minősítés túl optimista volt: "
                    "hiányzik a szekcióküszöböt teljesítő C/D/E támogatás vagy a független külső forrás."
                )
                unjustified.append(
                    {
                        "place_id": packet["place_id"],
                        "name_hu": packet["name_hu"],
                        "section_name": section,
                    }
                )
            status = section_source_status(section, items)
            if status in {"biblical_only", "gazetteer_only"} and section in {
                "historical_context",
                "archaeology",
                "homiletical_context",
                "ancient_geography",
            }:
                biblical_or_meta_only.append(
                    {
                        "place_id": packet["place_id"],
                        "section_name": section,
                        "section_source_status": status,
                    }
                )
            for item in unsupported:
                unsupported_claims.append(
                    {
                        "place_id": packet["place_id"],
                        "section_name": section,
                        "evidence_id": item["evidence_id"],
                        "claim_hu": item["claim_hu"],
                    }
                )
            claim_counts = Counter(item["claim_hu"] for item in items)
            for claim, count in claim_counts.items():
                if count > 1:
                    duplicate_notes.append(
                        {
                            "place_id": packet["place_id"],
                            "section_name": section,
                            "claim_hu": claim,
                            "count": count,
                        }
                    )
            generic = [
                item
                for item in items
                if "source candidate" in (item.get("claim_hu") or "").casefold()
                or "jelölt ehhez a szakaszhoz" in (item.get("claim_hu") or "")
            ]
            if len(generic) > 1:
                generic_proliferation.append(
                    {
                        "place_id": packet["place_id"],
                        "section_name": section,
                        "count": len(generic),
                    }
                )
            section_rows.append(
                {
                    "place_id": packet["place_id"],
                    "name_hu": packet["name_hu"],
                    "section_name": section,
                    "evidence_count": len(items),
                    "evidence_count_by_strength_class": strength_counts(items),
                    "valid_evidence_count": len(usable),
                    "unsupported_evidence_count": len(unsupported),
                    "candidate_source_count": candidate_count,
                    "registry_source_count": registry_count,
                    "independent_source_count": independent,
                    "section_source_status": status,
                    "current_coverage_status": "covered" if items else "missing",
                    "corrected_coverage_status": (
                        "source_backed"
                        if section_source_backed(section, items)
                        else "threshold_met"
                        if readiness["section_ok"][section]["meets_threshold"]
                        else "unsupported_or_partial"
                    ),
                    "current_ready_for_drafting": current_ready_sb or packet.get("ready_for_drafting", False),
                    "corrected_ready_for_drafting": readiness["ready_for_drafting"],
                    "current_ready_for_source_backed": current_ready_sb,
                    "corrected_ready_for_source_backed": corrected_sb,
                    "demotion_reason_hu": demotion,
                    "required_next_action": (
                        "acquire_cd_source"
                        if section in {"historical_context", "archaeology"}
                        and not section_source_backed(section, items)
                        else "keep_biblical_draft_scope"
                        if readiness["biblical_draft_ready"] and not corrected_sb
                        else "none"
                    ),
                    "notes_hu": readiness["section_ok"][section]["reason"],
                }
            )
    return {
        "summary": {
            "section_audit_rows": len(section_rows),
            "unjustified_source_backed_mentions": len(unjustified),
            "biblical_or_metadata_only_sections": len(biblical_or_meta_only),
            "unsupported_claims": len(unsupported_claims),
            "duplicate_claim_groups": len(duplicate_notes),
            "generic_proliferation_groups": len(generic_proliferation),
        },
        "sections": section_rows,
        "unjustified_source_backed_records": unjustified,
        "biblical_or_metadata_only_sections": biblical_or_meta_only,
        "unsupported_claims": unsupported_claims,
        "duplicate_evidence_notes": duplicate_notes,
        "generic_evidence_proliferation": generic_proliferation,
    }


def build_acquisition_queue(
    batch_queue: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    readiness_by_id: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates_by_place: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        for place_id in candidate.get("place_ids") or []:
            if place_id != "multiple":
                candidates_by_place[place_id].append(candidate["candidate_id"])
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for task in batch_queue:
        place_id = task["place_id"]
        section = task["section_name"]
        readiness = readiness_by_id.get(place_id)
        if readiness and readiness["section_ok"].get(section, {}).get("meets_threshold"):
            continue
        required = task.get("required_source_type") or " or ".join(source_types_for_section(section))
        missing = "C_or_D"
        if section in {"biblical_significance", "key_events"}:
            missing = "A_biblical_primary"
        elif section in {"ancient_geography", "identification_notes", "modern_context"}:
            missing = "B_plus_C_D_or_E"
        elif section == "homiletical_context":
            missing = "C_D_or_strong_E_place_specific"
        key = (place_id, section, missing)
        if key in deduped:
            continue
        priority = "high" if section in {"historical_context", "archaeology"} else task.get("priority") or "medium"
        deduped[key] = {
            "task_id": stable_id("acq", place_id, section, missing),
            "place_id": place_id,
            "name_hu": task.get("name_hu"),
            "section_name": section,
            "current_source_status": (
                readiness["section_ok"][section]["reason"]
                if readiness and section in readiness["section_ok"]
                else "unknown"
            ),
            "missing_source_strength": missing,
            "required_source_type": required,
            "suggested_institution_category": source_types_for_section(section)[0]
            if source_types_for_section(section)
            else "heritage_authority",
            "exact_research_question_hu": task.get("research_question_hu")
            or f"Milyen ellenőrzött C/D forrás támasztja alá {task.get('name_hu')} / {section} szakaszát?",
            "current_candidates": sorted(set(candidates_by_place.get(place_id, []))),
            "priority": priority,
            "blocks_partial_profile": section in {"historical_context", "archaeology", "ancient_geography"},
            "blocks_source_backed": section in {"historical_context", "archaeology", "identification_notes"},
            "blocks_featured": section in {"historical_context", "archaeology"},
            "status": "open",
        }
    # Ensure priority places missing C/D get explicit tasks even if queue filtered oddly.
    for packet in packets:
        readiness = readiness_by_id[packet["place_id"]]
        for section in ("historical_context", "archaeology"):
            if readiness["section_ok"][section]["meets_threshold"]:
                continue
            if packet["record_context"].get("place_type") in REGION_LIKE_TYPES and section == "archaeology":
                # Still record acquisition need, but lower priority for broad regions except egypt/tyre-like.
                pass
            key = (packet["place_id"], section, "C_or_D")
            if key in deduped:
                continue
            deduped[key] = {
                "task_id": stable_id("acq", packet["place_id"], section, "C_or_D"),
                "place_id": packet["place_id"],
                "name_hu": packet["name_hu"],
                "section_name": section,
                "current_source_status": readiness["section_ok"][section]["reason"],
                "missing_source_strength": "C_or_D",
                "required_source_type": " or ".join(source_types_for_section(section)),
                "suggested_institution_category": source_types_for_section(section)[0],
                "exact_research_question_hu": (
                    f"Keress helyspecifikus intézményi vagy tudományos forrást "
                    f"{packet['name_hu']} {section} szakaszához."
                ),
                "current_candidates": sorted(set(candidates_by_place.get(packet["place_id"], []))),
                "priority": "high",
                "blocks_partial_profile": True,
                "blocks_source_backed": True,
                "blocks_featured": True,
                "status": "open",
            }
    return sorted(deduped.values(), key=lambda item: (item["place_id"], item["section_name"]))


def strict_coverage_report(
    coverage_rows: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    readiness_by_id: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    acquisition_tasks: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    removed_unsupported: int,
    deduped_evidence_count: int,
) -> dict[str, Any]:
    strength_totals = Counter()
    only_a = []
    only_ab = []
    with_cd = []
    no_external = []
    unsupported_places = []
    section_strength = defaultdict(Counter)
    for packet in packets:
        readiness = readiness_by_id[packet["place_id"]]
        items = [item for section_items in packet["section_evidence"].values() for item in section_items]
        usable = valid_items(items)
        strength_totals.update(item["source_strength_class"] for item in items)
        classes = {item["source_strength_class"] for item in usable}
        if not usable:
            unsupported_places.append(packet["place_id"])
        if classes and classes <= {"A_biblical_primary"}:
            only_a.append(packet["place_id"])
        if classes and classes <= {"A_biblical_primary", "B_structured_gazetteer"}:
            only_ab.append(packet["place_id"])
        if classes & {"C_external_institutional", "D_external_scholarly"}:
            with_cd.append(packet["place_id"])
        if not (classes & EXTERNAL_CDE):
            no_external.append(packet["place_id"])
        for section, section_items in packet["section_evidence"].items():
            section_strength[section].update(
                item["source_strength_class"] for item in valid_items(section_items)
            )
    return {
        "summary": {
            "total_places": len(packets),
            "biblical_draft_ready_count": sum(
                1 for readiness in readiness_by_id.values() if readiness["biblical_draft_ready"]
            ),
            "partial_profile_ready_count": sum(
                1 for readiness in readiness_by_id.values() if readiness["partial_profile_ready"]
            ),
            "source_backed_profile_ready_count": sum(
                1 for readiness in readiness_by_id.values() if readiness["source_backed_profile_ready"]
            ),
            "featured_candidate_count": sum(
                1 for readiness in readiness_by_id.values() if readiness["featured_candidate"]
            ),
            "unsupported_places": unsupported_places,
            "places_without_external_cde": no_external,
            "places_only_a_evidence": only_a,
            "places_only_a_plus_b_evidence": only_ab,
            "places_with_c_or_d": with_cd,
            "section_coverage_by_strength": {
                section: dict(counts) for section, counts in section_strength.items()
            },
            "evidence_strength_totals": dict(strength_totals),
            "promoted_registry_sources": promotions,
            "rejected_candidates": [
                row["candidate_id"]
                for row in validations
                if row["validation_status"] == "rejected"
            ],
            "unclear_license_or_validation_candidates": [
                row["candidate_id"]
                for row in validations
                if row["validation_status"] in {"unclear", "metadata_only"}
            ],
            "deduplicated_evidence_count": deduped_evidence_count,
            "removed_or_disabled_unsupported_evidence_count": removed_unsupported,
            "remaining_source_acquisition_tasks": len(acquisition_tasks),
            "blocked_records": len(blocked_rows),
            "largest_source_gaps": dict(
                Counter(
                    gap
                    for readiness in readiness_by_id.values()
                    for gap in readiness["remaining_source_gaps"]
                ).most_common(8)
            ),
            "internet_research_status": "limited_validated_web_discovery_plus_existing_registry",
            "notes_hu": (
                "A bibliai textuskapcsolat, a koordináta-metaadat, a történeti szakirodalom "
                "és a régészeti intézményi forrás nem egyenértékű."
            ),
        },
        "places": coverage_rows,
    }


def coverage_summary(
    coverage_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
) -> dict[str, Any]:
    section_counts = Counter()
    confidence_counts = Counter()
    strength_counts_total = Counter()
    for row in coverage_rows:
        for section, covered in row["section_coverage"].items():
            if covered:
                section_counts[section] += 1
        confidence_counts.update(row["confidence_distribution"])
        strength_counts_total.update(row.get("evidence_count_by_strength_class") or {})
    return {
        "internet_research_status": "limited_validated_web_discovery_plus_existing_registry",
        "place_count": len(coverage_rows),
        "source_candidate_count": len(candidates),
        "approved_registry_source_promotions": len(promotions),
        "institutional_or_scholarly_candidate_count": sum(
            1
            for candidate in candidates
            if candidate["source_type"] in INSTITUTIONAL_TYPES | SCHOLARLY_TYPES | {"academic_gazetteer"}
        ),
        "evidence_item_count": sum(row["evidence_item_count"] for row in coverage_rows),
        "valid_evidence_item_count": sum(row["valid_evidence_item_count"] for row in coverage_rows),
        "evidence_strength_totals": dict(strength_counts_total),
        "section_coverage": dict(section_counts),
        "confidence_distribution": dict(confidence_counts),
        "ready_for_drafting_count": sum(1 for row in coverage_rows if row["ready_for_drafting"]),
        "ready_for_source_backed_count": sum(1 for row in coverage_rows if row["ready_for_source_backed"]),
        "biblical_draft_ready_count": sum(1 for row in coverage_rows if row.get("biblical_draft_ready")),
        "partial_profile_ready_count": sum(1 for row in coverage_rows if row.get("partial_profile_ready")),
        "source_backed_profile_ready_count": sum(
            1 for row in coverage_rows if row.get("source_backed_profile_ready")
        ),
        "featured_candidate_count": sum(1 for row in coverage_rows if row["possible_featured_candidate"]),
        "research_blocked_count": len(blocked_rows),
        "largest_source_gaps": dict(
            Counter(gap for row in coverage_rows for gap in row["remaining_source_gaps"]).most_common(8)
        ),
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
    previous_ready = {
        row["place_id"]
        for row in read_json(READY_FOR_DRAFTING_PATH, [])
        if row.get("recommended_profile_target") in {"source_backed", "featured_candidate", "source_backed_profile_ready"}
    }
    # Previous optimistic batch treated all 50 as source-backed in coverage report.
    previous_coverage = read_json(COVERAGE_REPORT_PATH, {"places": []})
    for row in previous_coverage.get("places") or []:
        if row.get("ready_for_source_backed"):
            previous_ready.add(row["place_id"])

    places_by_id = {place["place_id"]: place for place in catalog}
    groups_by_place = {
        place_id: group
        for group in profile_groups
        for place_id in group.get("member_place_ids", [])
    }
    passage_refs_by_place = build_passage_index(links)
    route_stops_by_place = build_route_index(routes)
    blocked_place_ids = {row["place_id"] for row in batch_blocked}
    used_sources: dict[str, set[str]] = defaultdict(set)
    for row in manifest:
        for source_id in row.get("existing_source_ids") or []:
            used_sources[source_id].add(row["place_id"])
        place = places_by_id[row["place_id"]]
        row["has_pleiades"] = bool(place.get("pleiades_id"))

    candidates = [
        source_candidate_from_registry(source, used_sources)
        for source in registry
        if source.get("source_id") in used_sources or source.get("source_id") == "openbible_geocoding_cc_by_4_0"
    ]
    candidates.extend(WEB_DISCOVERED_CANDIDATES)
    candidates.extend(catalog_pleiades_candidates(manifest, places_by_id))
    candidates = dedupe_candidates(candidates)

    pleiades_candidate_ids: dict[str, str] = {}
    for candidate in candidates:
        url = str(candidate.get("url_or_identifier") or "")
        marker = "/places/"
        if "pleiades.stoa.org" in url and marker in url:
            pleiades_id = url.rstrip("/").split(marker, 1)[-1]
            pleiades_candidate_ids[pleiades_id] = candidate["candidate_id"]

    validations = validate_candidates(candidates)
    registry, promotions = promote_sources(registry, candidates, validations)
    write_json(SOURCES_PATH, registry)
    registry_by_id = {source["source_id"]: source for source in registry}
    batch_promoted_ids = {
        "unesco_ancient_thebes_87",
        "unesco_tyre_299",
        "unesco_jerusalem_148",
        "unesco_petra_326",
    }
    promoted_in_registry = [
        {
            "candidate_id": next(
                (
                    candidate["candidate_id"]
                    for candidate in candidates
                    if str(candidate.get("url_or_identifier") or "").rstrip("/")
                    == str(source.get("identifier") or "").rstrip("/")
                ),
                source["source_id"],
            ),
            "source_id": source["source_id"],
            "validation_status": "citation_only",
        }
        for source in registry
        if source["source_id"] in batch_promoted_ids
    ]
    if not promotions:
        promotions = promoted_in_registry

    packets = []
    coverage_rows = []
    blocked_rows = []
    readiness_by_id: dict[str, dict[str, Any]] = {}
    raw_evidence_count = 0
    deduped_evidence_count = 0
    disabled_unsupported = 0

    for row in manifest:
        place = places_by_id[row["place_id"]]
        group = groups_by_place.get(row["place_id"])
        section_evidence = {section: [] for section in ALL_SECTIONS}
        source_ids: set[str] = set(row.get("existing_source_ids") or [])
        # Attach promoted UNESCO sources where relevant.
        for promotion in promotions:
            candidate = next(c for c in candidates if c["candidate_id"] == promotion["candidate_id"])
            if row["place_id"] in set(candidate.get("place_ids") or []):
                source_ids.add(promotion["source_id"])
        passage_refs = passage_refs_by_place.get(row["place_id"], [])
        route_stops = route_stops_by_place.get(row["place_id"], [])

        add_biblical_evidence(section_evidence, row, passage_refs, route_stops)
        add_structured_place_evidence(
            section_evidence,
            row,
            place,
            pleiades_candidate_ids=pleiades_candidate_ids,
        )
        add_source_candidate_evidence(
            section_evidence,
            row,
            candidates,
            registry_by_id,
            validation_by_id={row["candidate_id"]: row for row in validations},
        )

        for section, items in list(section_evidence.items()):
            raw_evidence_count += len(items)
            deduped = dedupe_evidence_items(items)
            # Disable unsupported.
            for item in deduped:
                if item.get("source_strength_class") == "G_unsupported":
                    if item.get("usable_for_drafting"):
                        disabled_unsupported += 1
                    item["usable_for_drafting"] = False
            section_evidence[section] = deduped
            deduped_evidence_count += len(deduped)

        for source_id in list(source_ids):
            if source_id not in registry_by_id:
                blocked_rows.append(
                    blocked_item(row, "all", "unknown_source_id", [source_id], "review_source_registry", True, True)
                )

        readiness = evaluate_readiness(
            row=row,
            section_evidence=section_evidence,
            group=group,
            candidates_by_id={candidate["candidate_id"]: candidate for candidate in candidates},
            registry_by_id=registry_by_id,
            blocked_place_ids=blocked_place_ids,
        )
        readiness_by_id[row["place_id"]] = readiness
        coverage = coverage_for_packet(
            row,
            section_evidence,
            source_ids,
            candidates,
            group,
            registry_by_id,
            blocked_place_ids,
            readiness,
        )
        coverage_rows.append(coverage)
        if not readiness["ready_for_drafting"]:
            for section in row["required_sections"]:
                if not valid_items(section_evidence[section]):
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
                "ready_for_drafting": readiness["ready_for_drafting"],
                "readiness_class": readiness["readiness_class"],
                "biblical_draft_ready": readiness["biblical_draft_ready"],
                "partial_profile_ready": readiness["partial_profile_ready"],
                "source_backed_profile_ready": readiness["source_backed_profile_ready"],
                "featured_candidate": readiness["featured_candidate"],
            }
        )

    ready_rows = legacy_ready_for_drafting_rows(coverage_rows, packets, readiness_by_id)
    readiness_lists = readiness_rows(coverage_rows, packets, readiness_by_id, candidates)
    research_blocked_rows = sorted_blocked(blocked_rows, batch_blocked)
    integrity = build_integrity_audit(
        packets, coverage_rows, readiness_by_id, candidates, previous_ready
    )
    acquisition = build_acquisition_queue(batch_queue, packets, readiness_by_id, candidates)
    report = {
        "summary": coverage_summary(coverage_rows, candidates, research_blocked_rows, promotions),
        "places": coverage_rows,
    }
    strict = strict_coverage_report(
        coverage_rows,
        packets,
        readiness_by_id,
        candidates,
        validations,
        promotions,
        acquisition,
        research_blocked_rows,
        disabled_unsupported,
        deduped_evidence_count,
    )
    cache = {
        "cache_version": 2,
        "generated_from": [
            str(BATCH_PATH.as_posix()),
            str(BATCH_RESEARCH_QUEUE_PATH.as_posix()),
            str(SOURCES_PATH.as_posix()),
        ],
        "candidate_hash": hashlib.sha1(
            json.dumps(candidates, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "packet_hash": hashlib.sha1(
            json.dumps(packets, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "status": "metadata_only_cache",
        "raw_evidence_count_before_dedupe": raw_evidence_count,
        "deduplicated_evidence_count": deduped_evidence_count,
    }

    write_json(SOURCE_CANDIDATES_PATH, candidates)
    write_json(EVIDENCE_PACKETS_PATH, packets)
    write_json(COVERAGE_REPORT_PATH, report)
    write_json(READY_FOR_DRAFTING_PATH, ready_rows)
    write_json(RESEARCH_BLOCKED_PATH, research_blocked_rows)
    write_json(INTEGRITY_AUDIT_PATH, integrity)
    write_json(SOURCE_VALIDATION_PATH, validations)
    write_json(ACQUISITION_QUEUE_PATH, acquisition)
    write_json(STRICT_COVERAGE_PATH, strict)
    write_json(BIBLICAL_DRAFT_READY_PATH, readiness_lists["biblical_draft_ready"])
    write_json(PARTIAL_PROFILE_READY_PATH, readiness_lists["partial_profile_ready"])
    write_json(SOURCE_BACKED_READY_PATH, readiness_lists["source_backed_profile_ready"])
    write_json(FEATURED_CANDIDATES_PATH, readiness_lists["featured_candidate"])
    write_json(CACHE_DIR / "batch_001_research_cache.json", cache)
    return {
        "candidates": candidates,
        "packets": packets,
        "coverage": report,
        "ready": ready_rows,
        "blocked": research_blocked_rows,
        "promotions": promotions,
        "validations": validations,
        "strict": strict,
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
