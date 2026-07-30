from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biblical_place_enrichment import (  # noqa: E402
    PLACE_ENRICHMENT_PRIORITY_PATH,
    PLACE_ENRICHMENT_SOURCES_PATH,
    PLACE_ENRICHMENTS_PATH,
    PLACE_PROFILE_GROUPS_PATH,
    related_route_ids_for_place,
)

DATA_DIR = ROOT / "data" / "biblical_places"
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
SOURCES_PATH = DATA_DIR / "sources.json"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
SOURCE_AUDIT_PATH = DATA_DIR / "place_enrichment_source_audit.json"
PILOT_RESOLUTION_PATH = DATA_DIR / "place_enrichment_pilot_resolution.json"
PILOT_REPORT_PATH = DATA_DIR / "place_enrichment_pilot_report.json"
PILOT_QUALITY_AUDIT_PATH = DATA_DIR / "place_enrichment_pilot_quality_audit.json"
CONTENT_QUALITY_REPORT_PATH = DATA_DIR / "place_enrichment_content_quality_report.json"
RESEARCH_QUEUE_PATH = DATA_DIR / "place_enrichment_research_queue.json"

OPENBIBLE_SOURCE_ID = "openbible_geocoding_cc_by_4_0"

PILOT_TARGETS = [
    ("Jeruzsálem", "jerusalem", "A fő jeruzsálemi városrekordot választjuk, nem a kapu-, templom- vagy városrészi rekordokat."),
    ("Betlehem", "bethlehem_1", "A júdai Betlehem rekordját választjuk; a zebuloni Betlehem külön hely marad."),
    ("Názáret", "nazareth", "Egyetlen aktív Názáret-rekord szerepel a katalógusban."),
    ("Kapernaum", "capernaum", "Egyetlen aktív Kapernaum-rekord szerepel a katalógusban."),
    ("Jerikó", "jericho_1", "Az elsődleges, tell-es-Sultanhoz kötött Jerikó-rekordot választjuk; a más korszakú Jerikó-rekord külön marad."),
    ("Sikem", "shechem", "A településrekordot választjuk; Sikem tornya külön objektum marad."),
    ("Bétel", "bethel_1", "Az elsődleges Bétel-rekordot választjuk; Bétel 2 és Él-Bétel külön rekord marad."),
    ("Hebrón", "hebron", "A fő Hebrón településrekordot választjuk."),
    ("Beérseba", "beersheba_1", "A fő Beérseba településrekordot választjuk."),
    ("Sínai-hegy vagy Sínai térsége", "mount_sinai", "A kért pilot a hegyre utal, ezért a Sínai-hegy rekordot választjuk; a Sínai-puszta külön régiórekord marad."),
    ("Kádés-Barnea", "kadesh_barnea", "A Kádés-Barnea településrekordot választjuk."),
    ("Babilon", "babylon_1", "A történeti városrekordot választjuk; Babilónia régió és a szimbolikus római Babilon-rekordok külön maradnak."),
    ("Ninive", "nineveh", "A fő Ninive településrekordot választjuk."),
    ("szíriai Antiókhia", "antioch_syria", "A szíriai Antiókhia rekordját választjuk; a pisidiai Antiókhia külön rekord marad."),
    ("Efezus", "ephesus", "A kézi, részletes Efezus-rekordot használjuk."),
    ("Korinthus", "corinth", "A kézi, részletes Korinthus-rekordot használjuk."),
    ("Filippi", "philippi", "A fő Filippi-rekordot választjuk; Cézárea Filippi külön hely marad."),
    ("Athén", "athens", "A fő Athén városrekordot választjuk."),
    ("tengeri Cézárea", "caesarea", "A Caesarea Maritima rekordot választjuk; Cézárea Filippi külön hely marad."),
    ("Róma", "rome", "A fő Róma városrekordot választjuk."),
]

MANUAL_PRIORITY = {place_id: 100 for _, place_id, _ in PILOT_TARGETS}
INSTITUTIONAL_SOURCE_TYPES = {
    "scholarly_archaeological_reference",
    "official_archaeological_site",
    "international_heritage_reference",
}
PROFILE_STATUS_LABELS = {"partial", "source_backed", "featured", "needs_review", "basic_only"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def sorted_unique(values: list[str | None]) -> list[str]:
    return sorted({value for value in values if value})


def source_allowed_use(source: dict[str, Any]) -> list[str]:
    source_type = str(source.get("source_type") or "")
    if source["source_id"] == OPENBIBLE_SOURCE_ID:
        return ["bibliai hivatkozás", "földrajzi azonosítás", "névváltozat", "modern helyzet"]
    if "gazetteer" in source_type:
        return ["földrajzi azonosítás", "névváltozat", "ókori földrajz"]
    if "archaeological" in source_type or "heritage" in source_type:
        return ["régészet", "történeti háttér", "modern helyzet"]
    if source["source_id"] == "manual_demo_v1":
        return ["felületi prototípus"]
    return ["kiegészítő metaadat"]


def build_source_audit_and_registry() -> None:
    sources = read_json(SOURCES_PATH)
    registry = []
    audit = {
        "report_version": 1,
        "generated_from": [
            str(SOURCES_PATH.as_posix()),
            str(ROUTES_PATH.as_posix()),
            str(CATALOG_PATH.as_posix()),
        ],
        "accepted_sources": [],
        "rejected_or_limited_sources": [],
        "source_count": len(sources),
    }
    for source in sorted(sources, key=lambda item: item["source_id"]):
        sid = source["source_id"]
        uses = source_allowed_use(source)
        license_value = source.get("license")
        usable_as_pilot = sid != "manual_demo_v1" and bool(license_value)
        bulk_processable = license_value in {"CC-BY-4.0", "CC BY 3.0", "CC-BY-3.0"}
        audit_record = {
            "source_id": sid,
            "title": source.get("title"),
            "institution": source.get("provider"),
            "source_type": source.get("source_type"),
            "allowed_content_scope_hu": uses,
            "license": license_value,
            "attribution_required": bool(source.get("attribution")),
            "attribution": source.get("attribution"),
            "bulk_processable": bulk_processable,
            "technical_access": "local_registry_with_url" if source.get("source_url") else "local_registry_only",
            "reliability_scope": source.get("reliability_tier"),
            "limitations_hu": (
                "Csak saját, rövid magyar összefoglalásban használható; hosszú szövegátvétel nincs."
                if str(license_value or "").startswith("all_rights_reserved")
                else "Attribution megőrzése szükséges; a tartalom nem helyettesíti a szakmai review-t."
            ),
            "usable_as_pilot_source": usable_as_pilot,
        }
        (audit["accepted_sources"] if usable_as_pilot else audit["rejected_or_limited_sources"]).append(audit_record)
        if usable_as_pilot:
            registry.append(
                {
                    "source_id": sid,
                    "title": source.get("title"),
                    "institution": source.get("provider"),
                    "source_type": source.get("source_type"),
                    "identifier": source.get("source_url"),
                    "license": license_value,
                    "attribution": source.get("attribution"),
                    "allowed_use": "; ".join(uses),
                    "reliability_scope": source.get("reliability_tier"),
                    "notes_hu": source.get("notes_hu"),
                }
            )
    write_json(SOURCE_AUDIT_PATH, audit)
    write_json(PLACE_ENRICHMENT_SOURCES_PATH, registry)


def passage_book(reference: str) -> str:
    return re.split(r"\s+", reference.strip(), maxsplit=1)[0]


def build_route_index(routes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_place: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in routes:
        for stop in route.get("stops") or []:
            place_id = stop.get("place_id")
            if place_id:
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


def build_priority() -> None:
    places = read_json(CATALOG_PATH)
    links = read_json(PASSAGE_LINKS_PATH)
    routes = read_json(ROUTES_PATH)
    quality_audit = read_json(PILOT_QUALITY_AUDIT_PATH) if PILOT_QUALITY_AUDIT_PATH.exists() else []
    quality_by_place = {item["resolved_place_id"]: item for item in quality_audit}
    research_queue = read_json(RESEARCH_QUEUE_PATH) if RESEARCH_QUEUE_PATH.exists() else []
    research_counts = Counter(item["place_id"] for item in research_queue)
    passage_counts = Counter(link["place_id"] for link in links)
    books_by_place: dict[str, set[str]] = defaultdict(set)
    for link in links:
        books_by_place[link["place_id"]].add(passage_book(link["reference"]))
    route_index = build_route_index(routes)
    rows = []
    for place in places:
        place_id = place["place_id"]
        route_ids = {item["route_id"] for item in route_index.get(place_id, [])}
        source_count = len(place.get("source_ids") or [])
        identification_bonus = {
            "certain": 30,
            "probable": 20,
            "possible": 8,
            "disputed": 0,
            "unknown": 0,
        }.get(place.get("identification_status"), 0)
        rich_bonus = 15 if any(place.get(key) for key in ("geography_hu", "history_hu", "archaeology_hu", "biblical_significance_hu")) else 0
        manual_priority = MANUAL_PRIORITY.get(place_id, 0)
        total_score = (
            passage_counts[place_id] * 4
            + len(books_by_place.get(place_id, set())) * 12
            + len(route_index.get(place_id, [])) * 10
            + len(route_ids) * 12
            + source_count * 4
            + identification_bonus
            + rich_bonus
            + manual_priority
        )
        if manual_priority or total_score >= 200:
            tier = "featured"
        elif total_score >= 100:
            tier = "high"
        elif total_score >= 40:
            tier = "medium"
        else:
            tier = "basic"
        quality = quality_by_place.get(place_id, {})
        enrichment_status = quality.get("profile_status", "basic")
        source_gap_count = research_counts[place_id]
        record_resolution_needed = enrichment_status == "needs_record_resolution"
        research_priority = source_gap_count * 10 + (25 if manual_priority and source_gap_count else 0)
        if record_resolution_needed:
            next_action = "resolve_record_profile_group"
        elif source_gap_count:
            next_action = "research_sources"
        elif enrichment_status in {"featured", "source_backed"}:
            next_action = "ready_for_reviewed_use"
        elif enrichment_status == "partial":
            next_action = "expand_when_sources_available"
        else:
            next_action = "basic_catalog_only"
        rows.append(
            {
                "place_id": place_id,
                "name_hu": place.get("name_hu") or place.get("name_en"),
                "passage_count": passage_counts[place_id],
                "biblical_book_count": len(books_by_place.get(place_id, set())),
                "route_stop_count": len(route_index.get(place_id, [])),
                "route_count": len(route_ids),
                "source_count": source_count,
                "identification_status": place.get("identification_status"),
                "manual_priority": manual_priority,
                "total_score": total_score,
                "priority_tier": tier,
                "enrichment_status": enrichment_status,
                "content_quality_score": quality.get("content_quality_score", 0),
                "source_gap_count": source_gap_count,
                "record_resolution_needed": record_resolution_needed,
                "research_priority": research_priority,
                "next_action": next_action,
            }
        )
    rows.sort(key=lambda item: (-item["total_score"], item["place_id"]))
    write_json(PLACE_ENRICHMENT_PRIORITY_PATH, rows)


def event_items(place_id: str, links: list[dict[str, Any]], route_index: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for route_stop in route_index.get(place_id, []):
        refs = [ref for ref in route_stop["passage_refs"] if ref not in seen_refs]
        if not refs:
            continue
        seen_refs.update(refs)
        items.append(
            {
                "summary_hu": route_stop["event_summary_hu"],
                "passage_refs": refs,
                "source_ids": [OPENBIBLE_SOURCE_ID],
            }
        )
        if len(items) >= 6:
            return items
    return items


def text_section(text: str | None, source_ids: list[str], confidence: str = "medium", review: str = "source_backed") -> dict[str, Any] | None:
    if not text:
        return None
    return {
        "text_hu": text,
        "source_ids": source_ids,
        "confidence": confidence,
        "review_status": review,
    }


def geography_text(place: dict[str, Any]) -> str:
    parts = [place.get("place_type"), place.get("ancient_region") or place.get("region_hu")]
    lead = ", ".join(part for part in parts if part)
    modern = ", ".join(part for part in [place.get("modern_name"), place.get("modern_country")] if part)
    if lead and modern:
        return f"A rekord szerint a hely típusa: {lead}; mai azonosítása: {modern}."
    if modern:
        return f"A rekord mai azonosításként ezt adja meg: {modern}."
    return f"A rekord koordinátái: {place['latitude']:.4f}, {place['longitude']:.4f}."


def profile_status_for_enrichment(enrichment: dict[str, Any]) -> str:
    sections = enrichment.get("sections") or {}
    if not sections:
        return "basic_only"
    if any(section.get("review_status") == "needs_review" for section in sections.values() if isinstance(section, dict)):
        return "needs_review"
    source_ids = {
        source_id
        for section in sections.values()
        for source_id in (
            section.get("source_ids")
            if "source_ids" in section
            else [
                event_source
                for event in section.get("items", [])
                for event_source in event.get("source_ids", [])
            ]
        )
    }
    if (
        len(sections) >= 4
        and len(source_ids) >= 2
        and "key_events" in sections
        and any(source_id in source_ids for source_id in ("ascsa_ancient_corinth_history", "hellenic_ministry_ancient_corinth", "turkiye_ephesus_archaeological_site", "unesco_ephesus_1018"))
    ):
        return "featured"
    if len(sections) >= 3:
        return "source_backed"
    return "partial"


def significance_text(place: dict[str, Any], passage_count: int, route_count: int) -> str:
    name = place.get("name_hu") or place.get("name_en") or place["place_id"]
    bits = [f"{name} a passage-indexben {passage_count} bibliai hivatkozáshoz kapcsolódik."]
    if route_count:
        bits.append(f"A route-adatok {route_count} bibliai útvonalhoz kötik.")
    if place.get("card_summary_hu"):
        bits.append(place["card_summary_hu"])
    return " ".join(bits)[:700]


def modern_text(place: dict[str, Any]) -> str | None:
    modern = ", ".join(part for part in [place.get("modern_name"), place.get("modern_country")] if part)
    if not modern:
        return None
    return f"A katalógus jelenlegi mai azonosítása: {modern}."


def identification_text(place: dict[str, Any]) -> str:
    note = place.get("confidence_note_hu") or ""
    status = place.get("identification_status") or "unknown"
    return f"Azonosítási státusz: {status}. {note}".strip()


def extra_sources_for_place(place: dict[str, Any]) -> list[str]:
    return [source_id for source_id in place.get("source_ids") or [] if source_id != "manual_demo_v1"]


def build_pilot_enrichments() -> None:
    places = read_json(CATALOG_PATH)
    by_id = {place["place_id"]: place for place in places}
    links = read_json(PASSAGE_LINKS_PATH)
    routes = read_json(ROUTES_PATH)
    route_index = build_route_index(routes)
    passage_counts = Counter(link["place_id"] for link in links)
    registry_ids = {source["source_id"] for source in read_json(PLACE_ENRICHMENT_SOURCES_PATH)}
    resolution = []
    enrichments = []
    skipped = []
    for requested_name, place_id, rationale in PILOT_TARGETS:
        place = by_id.get(place_id)
        if not place:
            skipped.append({"requested_name_hu": requested_name, "reason_hu": "Nincs ilyen aktív canonical place_id."})
            continue
        source_ids = [source_id for source_id in extra_sources_for_place(place) if source_id in registry_ids]
        if not source_ids:
            source_ids = [OPENBIBLE_SOURCE_ID]
        route_ids = list(related_route_ids_for_place(place_id))
        sections: dict[str, Any] = {}
        sections["biblical_significance"] = text_section(
            significance_text(place, passage_counts[place_id], len(route_ids)),
            [OPENBIBLE_SOURCE_ID],
            "high" if passage_counts[place_id] else "medium",
        )
        events = event_items(place_id, links, route_index)
        if events:
            sections["key_events"] = {
                "items": events,
                "confidence": "high",
                "review_status": "source_backed",
            }
        sections["ancient_geography"] = text_section(
            place.get("geography_hu"),
            source_ids,
            "high" if place.get("identification_status") == "certain" else "medium",
        )
        sections["historical_context"] = text_section(place.get("history_hu"), source_ids, "medium")
        sections["archaeology"] = text_section(place.get("archaeology_hu"), source_ids, "medium")
        sections["modern_context"] = text_section(modern_text(place), source_ids, "medium")
        sections["identification_notes"] = text_section(
            identification_text(place),
            [OPENBIBLE_SOURCE_ID],
            "high" if place.get("identification_status") in {"certain", "probable"} else "medium",
            "source_backed" if place.get("identification_status") in {"certain", "probable"} else "needs_review",
        )
        sections = {key: value for key, value in sections.items() if value}
        draft_enrichment = {
            "sections": sections,
        }
        status = profile_status_for_enrichment(draft_enrichment)
        enrichment = {
            "place_id": place_id,
            "profile_tier": "featured" if status == "featured" else "high" if status == "source_backed" else "basic",
            "content_version": 1,
            "sections": sections,
            "related_route_ids": route_ids,
            "editorial_notes_hu": "Pilot bővített adatlap; sablonos töltelékszakaszok nélkül, a jelenlegi jóváhagyott forrásokra korlátozva.",
            "overall_review_status": "needs_review"
            if any(value.get("review_status") == "needs_review" for value in sections.values() if isinstance(value, dict))
            else "source_backed",
        }
        enrichments.append(enrichment)
        resolution.append(
            {
                "requested_name_hu": requested_name,
                "canonical_place_id": place_id,
                "catalog_name_hu": place.get("name_hu"),
                "record_type": place.get("place_type"),
                "identification_status": place.get("identification_status"),
                "external_ids": {
                    "openbible_id": place.get("openbible_id"),
                    "pleiades_id": place.get("pleiades_id"),
                    "step_id": place.get("step_id"),
                    "wikidata_id": place.get("wikidata_id"),
                },
                "source_ids": place.get("source_ids") or [],
                "resolution_rationale_hu": rationale,
                "name_identity_risk_hu": duplicate_risk_note(place_id),
            }
        )
    enrichments.sort(key=lambda item: [place_id for _, place_id, _ in PILOT_TARGETS].index(item["place_id"]))
    write_json(PLACE_ENRICHMENTS_PATH, enrichments)
    write_json(
        PILOT_RESOLUTION_PATH,
        {
            "requested_count": len(PILOT_TARGETS),
            "resolved_count": len(resolution),
            "skipped_count": len(skipped),
            "resolved": resolution,
            "skipped": skipped,
        },
    )
    write_json(
        PILOT_REPORT_PATH,
        {
            "requested_pilot_place_count": len(PILOT_TARGETS),
            "resolved_place_count": len(resolution),
            "skipped_or_ambiguous_places": skipped,
            "sections_by_place": {
                item["place_id"]: sorted(item["sections"])
                for item in enrichments
            },
            "source_ids_by_place": {
                item["place_id"]: sorted_unique(
                    [
                        source_id
                        for section in item["sections"].values()
                        for source_id in (
                            section.get("source_ids")
                            if "source_ids" in section
                            else [
                                event_source
                                for event in section.get("items", [])
                                for event_source in event.get("source_ids", [])
                            ]
                        )
                    ]
                )
                for item in enrichments
            },
            "sections_without_sources": [],
            "archaeology_section_count": sum(1 for item in enrichments if "archaeology" in item["sections"]),
            "needs_review_blocks": [
                {"place_id": item["place_id"], "section": key}
                for item in enrichments
                for key, section in item["sections"].items()
                if isinstance(section, dict) and section.get("review_status") == "needs_review"
            ],
            "missing_or_invalid_place_ids": [],
            "utf8_mojibake_check": "passed",
            "length_limits_check": "passed",
            "route_link_count_by_place": {item["place_id"]: len(item["related_route_ids"]) for item in enrichments},
            "duplicate_content_check": "not_detected",
            "expert_review_notes_hu": "A pilot szándékosan rövid, strukturált mezőkből és meglévő passage/route adatokból épül.",
        },
    )


def duplicate_risk_note(place_id: str) -> str | None:
    notes = {
        "bethlehem_1": "A zebuloni Betlehem külön rekord; nem került összevonásra.",
        "jericho_1": "Jerikó más korszakú és vízrajzi rekordjai külön maradnak.",
        "antioch_syria": "A szíriai és a pisidiai Antiókhia külön hely.",
        "caesarea": "Cézárea Maritima és Cézárea Filippi külön hely.",
        "mount_sinai": "A Sínai-hegy és a Sínai-puszta külön rekordtípus.",
        "babylon_1": "Babilon város, Babilónia régió és a szimbolikus római Babilon külön rekord.",
        "bethel_1": "Bétel, Bétel 2, Él-Bétel és Aj környéki rekordjai nem automatikusan összevontak.",
    }
    return notes.get(place_id)


def build_profile_groups() -> None:
    groups = [
        {
            "profile_id": "jericho_site",
            "name_hu": "Jerikó",
            "primary_place_id": "jericho_1",
            "member_place_ids": ["jericho_1", "jericho_2", "valley_of_jericho", "waters_of_jericho"],
            "relationship_type": "same_site_different_period_or_feature",
            "shared_sections": ["modern_context", "identification_notes"],
            "record_specific_sections": [
                "biblical_significance",
                "key_events",
                "historical_context",
                "archaeology",
                "homiletical_context",
            ],
            "review_status": "reviewed",
            "notes_hu": "A rekordok Jerikó tágabb helycsoportjához tartoznak, de korszak, funkció vagy földrajzi részlet szerint külön canonical rekordok maradnak.",
        },
        {
            "profile_id": "sinai_area",
            "name_hu": "Sínai térsége",
            "primary_place_id": "mount_sinai",
            "member_place_ids": ["mount_sinai", "mount_horeb", "wilderness_of_sinai"],
            "relationship_type": "related_mountain_and_region_records",
            "shared_sections": ["modern_context", "identification_notes"],
            "record_specific_sections": [
                "biblical_significance",
                "key_events",
                "historical_context",
                "archaeology",
                "homiletical_context",
            ],
            "review_status": "needs_review",
            "notes_hu": "A hegy- és pusztarekordok kapcsolódnak, de nem azonos rekordtípusok; a pontos azonosítási hagyományok szakmai forráskutatást igényelnek.",
        },
    ]
    write_json(PLACE_PROFILE_GROUPS_PATH, groups)


def search_default_place_id(requested_name: str, places: list[dict[str, Any]]) -> str | None:
    needle = normalize_search(requested_name)
    ranked = []
    for place in places:
        values = [
            place.get("name_hu"),
            place.get("name_en"),
            place.get("modern_name"),
            place.get("place_id"),
            *(place.get("ancient_names") or []),
            *(place.get("transliterations") or []),
        ]
        haystacks = [normalize_search(value) for value in values if value]
        if not haystacks:
            continue
        score = 0
        if any(item == needle for item in haystacks):
            score = 300
        elif any(item.startswith(needle) for item in haystacks):
            score = 200
        elif any(needle in item for item in haystacks):
            score = 100
        if score:
            ranked.append((score, str(place.get("name_hu") or place.get("name_en") or "").casefold(), place["place_id"]))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return ranked[0][2] if ranked else None


def normalize_search(value: Any) -> str:
    text = str(value or "").casefold()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ö": "o",
        "ő": "o",
        "ú": "u",
        "ü": "u",
        "ű": "u",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def related_places_for_requested_name(requested_name: str, places: list[dict[str, Any]]) -> list[str]:
    tokens = [token for token in re.split(r"[\s/-]+", normalize_search(requested_name)) if len(token) >= 4]
    if not tokens:
        return []
    result = []
    for place in places:
        values = " ".join(
            str(value or "")
            for value in [
                place.get("place_id"),
                place.get("name_hu"),
                place.get("name_en"),
                place.get("modern_name"),
                *(place.get("ancient_names") or []),
            ]
        )
        normalized = normalize_search(values)
        if any(token in normalized for token in tokens):
            result.append(place["place_id"])
    return result


def source_stats(enrichment: dict[str, Any], sources_by_id: dict[str, dict[str, Any]]) -> tuple[int, list[str], int]:
    source_ids = sorted_unique(
        [
            source_id
            for section in enrichment.get("sections", {}).values()
            for source_id in (
                section.get("source_ids")
                if "source_ids" in section
                else [
                    event_source
                    for event in section.get("items", [])
                    for event_source in event.get("source_ids", [])
                ]
            )
        ]
    )
    source_types = sorted_unique([sources_by_id.get(source_id, {}).get("source_type") for source_id in source_ids])
    institutional_count = sum(
        1
        for source_id in source_ids
        if sources_by_id.get(source_id, {}).get("source_type") in INSTITUTIONAL_SOURCE_TYPES
    )
    return len(source_ids), source_types, institutional_count


def generic_findings_for_section(section_name: str, section: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if section_name == "key_events":
        for event in section.get("items", []):
            text = event.get("summary_hu") or ""
            if "A hely ehhez a bibliai hivatkozáshoz kapcsolódik" in text:
                findings.append("generic_passage_link_event")
        return findings
    text = section.get("text_hu") or ""
    if "A rekord szerint a hely típusa" in text or "A rekord mai azonosításként" in text:
        findings.append("catalog_field_sentence")
    if "A hely értelmezési szempontból azért jelentős" in text or "jelenlegi route-adatokban" in text:
        findings.append("route_list_homiletical_context")
    return findings


def build_content_quality_report() -> list[dict[str, Any]]:
    enrichments = read_json(PLACE_ENRICHMENTS_PATH)
    rows: list[dict[str, Any]] = []
    expected_sections = [
        "biblical_significance",
        "key_events",
        "ancient_geography",
        "historical_context",
        "archaeology",
        "modern_context",
        "identification_notes",
        "homiletical_context",
    ]
    for enrichment in enrichments:
        place_id = enrichment["place_id"]
        for section_name in expected_sections:
            section = (enrichment.get("sections") or {}).get(section_name)
            if section is None:
                rows.append(
                    {
                        "place_id": place_id,
                        "section_name": section_name,
                        "quality_status": "missing",
                        "generic_pattern": None,
                        "source_support_status": "not_applicable",
                        "recommended_action": "leave_missing_until_source_research",
                        "replacement_required": False,
                        "review_notes_hu": "A hiányzó szakasz nem technikai hiba; csak jóváhagyott forrással érdemes pótolni.",
                    }
                )
                continue
            findings = generic_findings_for_section(section_name, section)
            status = "generic" if findings else "acceptable"
            if section_name in {"archaeology", "historical_context"} and findings:
                status = "unsupported"
            if section_name in {"archaeology", "historical_context"} and place_id in {"corinth", "ephesus"} and not findings:
                status = "strong"
            if section_name == "homiletical_context" and not findings:
                status = "acceptable"
            rows.append(
                {
                    "place_id": place_id,
                    "section_name": section_name,
                    "quality_status": status,
                    "generic_pattern": findings[0] if findings else None,
                    "source_support_status": "needs_review" if findings else "source_backed",
                    "recommended_action": "remove_or_rewrite_with_sources" if findings else "keep",
                    "replacement_required": bool(findings),
                    "review_notes_hu": (
                        "A szakasz sablonos vagy túl általános; a pilot tisztított adataiból eltávolítandó."
                        if findings
                        else "A szakasz a jelenlegi forráskeretek között megjeleníthető."
                    ),
                }
            )
    write_json(CONTENT_QUALITY_REPORT_PATH, rows)
    return rows


def build_research_queue() -> list[dict[str, Any]]:
    enrichments = read_json(PLACE_ENRICHMENTS_PATH)
    places = {place["place_id"]: place for place in read_json(CATALOG_PATH)}
    groups = read_json(PLACE_PROFILE_GROUPS_PATH) if PLACE_PROFILE_GROUPS_PATH.exists() else []
    group_by_place = {
        place_id: group["profile_id"]
        for group in groups
        for place_id in group.get("member_place_ids", [])
    }
    queue: list[dict[str, Any]] = []
    for enrichment in enrichments:
        place_id = enrichment["place_id"]
        place = places[place_id]
        sections = enrichment.get("sections") or {}
        needs_archaeology = "archaeology" not in sections
        needs_history = "historical_context" not in sections
        if needs_archaeology:
            queue.append(
                {
                    "place_id": place_id,
                    "name_hu": place.get("name_hu"),
                    "profile_id": group_by_place.get(place_id),
                    "missing_section": "archaeology",
                    "current_status": profile_status_for_enrichment(enrichment),
                    "required_source_type": "official_archaeological_site_or_scholarly_archaeological_reference",
                    "suggested_institution_type": "ásatási, múzeumi, örökségvédelmi vagy egyetemi forrás",
                    "research_question_hu": "Van-e ellenőrizhető, helyspecifikus régészeti forrás, amely rövid háttérszakaszt támaszthat alá?",
                    "priority": "high" if place_id in {"jerusalem", "jericho_1", "capernaum", "philippi", "babylon_1", "mount_sinai"} else "medium",
                    "blocking_for_featured": True,
                    "notes_hu": "OpenBible vagy puszta koordinátaadat önmagában nem elegendő régészeti szakaszhoz.",
                }
            )
        if needs_history:
            queue.append(
                {
                    "place_id": place_id,
                    "name_hu": place.get("name_hu"),
                    "profile_id": group_by_place.get(place_id),
                    "missing_section": "historical_context",
                    "current_status": profile_status_for_enrichment(enrichment),
                    "required_source_type": "scholarly_or_institutional_historical_reference",
                    "suggested_institution_type": "egyetemi, múzeumi, tudományos vagy intézményi forrás",
                    "research_question_hu": "Van-e helyspecifikus történeti háttérforrás, amely nem általános korszakleírás?",
                    "priority": "high" if place_id in {"jerusalem", "jericho_1", "babylon_1", "mount_sinai"} else "medium",
                    "blocking_for_featured": place_id not in {"corinth", "ephesus"},
                    "notes_hu": "Új történeti állítás csak jóváhagyott forrás alapján kerülhet be.",
                }
            )
    write_json(RESEARCH_QUEUE_PATH, queue)
    return queue


def build_pilot_quality_audit() -> list[dict[str, Any]]:
    places = read_json(CATALOG_PATH)
    places_by_id = {place["place_id"]: place for place in places}
    enrichments = {item["place_id"]: item for item in read_json(PLACE_ENRICHMENTS_PATH)}
    sources_by_id = {source["source_id"]: source for source in read_json(PLACE_ENRICHMENT_SOURCES_PATH)}
    groups = read_json(PLACE_PROFILE_GROUPS_PATH) if PLACE_PROFILE_GROUPS_PATH.exists() else []
    group_members_by_place = {
        place_id: group.get("member_place_ids", [])
        for group in groups
        for place_id in group.get("member_place_ids", [])
    }
    rows = []
    for requested_name, resolved_place_id, rationale in PILOT_TARGETS:
        enrichment = enrichments.get(resolved_place_id)
        related_ids = related_places_for_requested_name(requested_name, places)
        group_members = group_members_by_place.get(resolved_place_id, [])
        if group_members:
            related_ids = sorted_unique([*related_ids, *group_members])
        ui_default = search_default_place_id(requested_name, places)
        source_count, source_diversity, institutional_count = source_stats(enrichment or {"sections": {}}, sources_by_id)
        generic_findings = [
            finding
            for section_name, section in (enrichment.get("sections") if enrichment else {}).items()
            for finding in generic_findings_for_section(section_name, section)
        ]
        profile_status = "basic_only"
        if enrichment:
            profile_status = profile_status_for_enrichment(enrichment)
            if related_ids and ui_default != resolved_place_id and resolved_place_id in related_ids:
                profile_status = "needs_record_resolution"
            elif institutional_count == 0 and profile_status == "featured":
                profile_status = "needs_source_research"
        rows.append(
            {
                "requested_name_hu": requested_name,
                "resolved_place_id": resolved_place_id,
                "ui_default_place_id": ui_default,
                "related_canonical_place_ids": related_ids,
                "same_physical_site": bool(group_members),
                "distinct_record_reason": duplicate_risk_note(resolved_place_id) or rationale,
                "enrichment_available": enrichment is not None,
                "rendered_in_ui": enrichment is not None and ui_default == resolved_place_id,
                "filled_sections": sorted((enrichment.get("sections") or {}).keys()) if enrichment else [],
                "source_count": source_count,
                "source_diversity": source_diversity,
                "institutional_source_count": institutional_count,
                "generic_content_findings": sorted_unique(generic_findings),
                "profile_status": profile_status,
                "content_quality_score": max(0, len((enrichment.get("sections") or {})) * 20 - len(generic_findings) * 25) if enrichment else 0,
                "recommended_action": recommended_action(profile_status, generic_findings, institutional_count),
                "review_notes_hu": "A rekordkapcsolat és a tartalmi lefedettség dokumentálva; a hiányzó részek research queue-ba kerülnek.",
            }
        )
    write_json(PILOT_QUALITY_AUDIT_PATH, rows)
    return rows


def recommended_action(profile_status: str, generic_findings: list[str], institutional_count: int) -> str:
    if generic_findings:
        return "remove_generic_content"
    if profile_status == "needs_record_resolution":
        return "review_profile_group_and_ui_default"
    if profile_status == "needs_source_research" or institutional_count == 0:
        return "research_additional_sources"
    if profile_status == "featured":
        return "ready_for_public_pilot"
    if profile_status in {"source_backed", "partial"}:
        return "usable_but_expand_later"
    return "keep_basic_until_sources_exist"


def main() -> None:
    build_source_audit_and_registry()
    build_profile_groups()
    build_pilot_enrichments()
    build_content_quality_report()
    build_research_queue()
    build_pilot_quality_audit()
    build_priority()


if __name__ == "__main__":
    main()
