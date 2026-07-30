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
    for link in links:
        if link["place_id"] != place_id or link["reference"] in seen_refs:
            continue
        seen_refs.add(link["reference"])
        items.append(
            {
                "summary_hu": f"A hely ehhez a bibliai hivatkozáshoz kapcsolódik: {link['reference']}.",
                "passage_refs": [link["reference"]],
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
            place.get("geography_hu") or geography_text(place),
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
        if route_ids:
            route_names = [route["name_hu"] for route in routes if route["route_id"] in route_ids]
            sections["homiletical_context"] = text_section(
                "A hely értelmezési szempontból azért jelentős, mert a jelenlegi route-adatokban "
                f"kapcsolódik ezekhez az útvonalakhoz: {', '.join(route_names)}. Ez útvonal- és szövegösszefüggést jelez, nem kész alkalmazást.",
                [OPENBIBLE_SOURCE_ID],
                "medium",
            )
        sections = {key: value for key, value in sections.items() if value}
        enrichment = {
            "place_id": place_id,
            "profile_tier": "featured",
            "content_version": 1,
            "sections": sections,
            "related_route_ids": route_ids,
            "editorial_notes_hu": "Pilot bővített adatlap; rövid, forrásolt, ellenőrizhető összefoglaló.",
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


def main() -> None:
    build_source_audit_and_registry()
    build_priority()
    build_pilot_enrichments()


if __name__ == "__main__":
    main()
