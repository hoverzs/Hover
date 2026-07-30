"""Source-backed enrichment overlay for biblical map places."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from biblical_map_data import DATA_DIR, place_ids, places_by_id
from biblical_routes import load_biblical_routes


PLACE_ENRICHMENT_SOURCES_PATH = DATA_DIR / "place_enrichment_sources.json"
PLACE_ENRICHMENTS_PATH = DATA_DIR / "place_enrichments.json"
PLACE_ENRICHMENT_PRIORITY_PATH = DATA_DIR / "place_enrichment_priority.json"

ALLOWED_CONFIDENCE_VALUES = {"high", "medium", "low"}
ALLOWED_SECTION_REVIEW_STATUSES = {"source_backed", "needs_review"}
ALLOWED_OVERALL_REVIEW_STATUSES = {"source_backed", "needs_review"}
ALLOWED_PROFILE_TIERS = {"featured", "high", "medium", "basic"}

TEXT_SECTION_KEYS = (
    "biblical_significance",
    "ancient_geography",
    "historical_context",
    "archaeology",
    "modern_context",
    "identification_notes",
    "homiletical_context",
)

SECTION_LABELS_HU = {
    "biblical_significance": "Bibliai jelentőség",
    "key_events": "Fontos bibliai események",
    "ancient_geography": "Ókori földrajzi háttér",
    "historical_context": "Történeti háttér",
    "archaeology": "Régészet",
    "modern_context": "Mai helyzet",
    "identification_notes": "Azonosítás és bizonyosság",
    "homiletical_context": "Igehirdetési és tanulmányozási összefüggések",
}

CONFIDENCE_LABELS_HU = {
    "high": "magas bizonyosság",
    "medium": "közepes bizonyosság",
    "low": "alacsony bizonyosság",
}

SECTION_REVIEW_LABELS_HU = {
    "source_backed": "forrásolt",
    "needs_review": "szakmai ellenőrzésre vár",
}

MOJIBAKE_MARKERS = ("Ă", "Ĺ", "Ĺ‘", "Ĺ±", "â€", "Â", "\ufffd")
CORRUPTED_QUESTION_MARK_RE = re.compile(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{2,}\?[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{2,}")


class PlaceEnrichmentDataError(ValueError):
    """Raised when place enrichment overlay data is invalid."""


@dataclass(frozen=True)
class PlaceEnrichmentSource:
    source_id: str
    title: str
    institution: str
    source_type: str
    identifier: str | None
    license: str
    attribution: str
    allowed_use: str
    reliability_scope: str
    notes_hu: str | None


@dataclass(frozen=True)
class EnrichmentTextSection:
    text_hu: str
    source_ids: tuple[str, ...]
    confidence: str
    review_status: str


@dataclass(frozen=True)
class EnrichmentKeyEvent:
    summary_hu: str
    passage_refs: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class EnrichmentKeyEventsSection:
    items: tuple[EnrichmentKeyEvent, ...]
    confidence: str
    review_status: str


@dataclass(frozen=True)
class PlaceEnrichment:
    place_id: str
    profile_tier: str
    content_version: int
    sections: dict[str, EnrichmentTextSection | EnrichmentKeyEventsSection]
    related_route_ids: tuple[str, ...]
    editorial_notes_hu: str | None
    overall_review_status: str


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlaceEnrichmentDataError(f"Invalid JSON in {path}") from exc


def _as_str(
    value: Any,
    field_name: str,
    *,
    required: bool = False,
    validate_text: bool = True,
) -> str | None:
    if value is None:
        if required:
            raise PlaceEnrichmentDataError(f"Missing required field: {field_name}")
        return None
    if not isinstance(value, str):
        raise PlaceEnrichmentDataError(f"Field {field_name} must be a string.")
    text = value.strip()
    if required and not text:
        raise PlaceEnrichmentDataError(f"Field {field_name} must not be empty.")
    if validate_text:
        _validate_user_text(text, field_name)
    return text or None


def _as_str_tuple(value: Any, field_name: str, *, required: bool = False) -> tuple[str, ...]:
    if value is None:
        if required:
            raise PlaceEnrichmentDataError(f"Missing required field: {field_name}")
        return ()
    if not isinstance(value, list):
        raise PlaceEnrichmentDataError(f"Field {field_name} must be a list.")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _as_str(item, field_name, required=True) or ""
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    if required and not result:
        raise PlaceEnrichmentDataError(f"Field {field_name} must not be empty.")
    return tuple(result)


def _validate_user_text(value: str | None, field_name: str) -> None:
    if not value:
        return
    if any(marker in value for marker in MOJIBAKE_MARKERS) or CORRUPTED_QUESTION_MARK_RE.search(value):
        raise PlaceEnrichmentDataError(f"Corrupted user-facing enrichment text in {field_name}: {value!r}")


def _enum(value: Any, field_name: str, allowed: set[str]) -> str:
    text = _as_str(value, field_name, required=True) or ""
    if text not in allowed:
        raise PlaceEnrichmentDataError(f"Invalid {field_name}: {text}")
    return text


def _legacy_place_ids_by_canonical() -> dict[str, set[str]]:
    return {
        place.place_id: set(place.legacy_place_ids)
        for place in places_by_id().values()
        if getattr(place, "legacy_place_ids", ())
    }


def _all_legacy_place_ids() -> set[str]:
    legacy_ids: set[str] = set()
    for ids in _legacy_place_ids_by_canonical().values():
        legacy_ids.update(ids)
    return legacy_ids


def _source_from_raw(raw: Any) -> PlaceEnrichmentSource:
    if not isinstance(raw, dict):
        raise PlaceEnrichmentDataError("Enrichment source records must be objects.")
    return PlaceEnrichmentSource(
        source_id=_as_str(raw.get("source_id"), "source_id", required=True) or "",
        title=_as_str(raw.get("title"), "title", required=True) or "",
        institution=_as_str(raw.get("institution"), "institution", required=True) or "",
        source_type=_as_str(raw.get("source_type"), "source_type", required=True) or "",
        identifier=_as_str(raw.get("identifier"), "identifier", validate_text=False),
        license=_as_str(raw.get("license"), "license", required=True) or "",
        attribution=_as_str(raw.get("attribution"), "attribution", required=True) or "",
        allowed_use=_as_str(raw.get("allowed_use"), "allowed_use", required=True) or "",
        reliability_scope=_as_str(raw.get("reliability_scope"), "reliability_scope", required=True) or "",
        notes_hu=_as_str(raw.get("notes_hu"), "notes_hu"),
    )


@lru_cache(maxsize=1)
def load_place_enrichment_sources(
    path: Path = PLACE_ENRICHMENT_SOURCES_PATH,
) -> tuple[PlaceEnrichmentSource, ...]:
    raw = _load_json(path, [])
    if not isinstance(raw, list):
        raise PlaceEnrichmentDataError("Place enrichment sources JSON must contain a list.")
    sources = tuple(_source_from_raw(item) for item in raw)
    ids = [source.source_id for source in sources]
    if len(ids) != len(set(ids)):
        raise PlaceEnrichmentDataError("Duplicate enrichment source_id found.")
    return sources


def place_enrichment_sources_by_id(
    sources: tuple[PlaceEnrichmentSource, ...] | None = None,
) -> dict[str, PlaceEnrichmentSource]:
    return {source.source_id: source for source in (sources or load_place_enrichment_sources())}


def _validate_source_ids(source_ids: tuple[str, ...], field_name: str, known: set[str]) -> None:
    if not source_ids:
        raise PlaceEnrichmentDataError(f"Field {field_name} must contain at least one source_id.")
    missing = [source_id for source_id in source_ids if source_id not in known]
    if missing:
        raise PlaceEnrichmentDataError(f"Unknown source_id in {field_name}: {', '.join(missing)}")


def _text_section_from_raw(
    key: str,
    raw: Any,
    known_source_ids: set[str],
) -> EnrichmentTextSection | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PlaceEnrichmentDataError(f"Section {key} must be an object or null.")
    text_hu = _as_str(raw.get("text_hu"), f"{key}.text_hu", required=True) or ""
    source_ids = _as_str_tuple(raw.get("source_ids"), f"{key}.source_ids", required=True)
    _validate_source_ids(source_ids, f"{key}.source_ids", known_source_ids)
    return EnrichmentTextSection(
        text_hu=text_hu,
        source_ids=source_ids,
        confidence=_enum(raw.get("confidence"), f"{key}.confidence", ALLOWED_CONFIDENCE_VALUES),
        review_status=_enum(
            raw.get("review_status"),
            f"{key}.review_status",
            ALLOWED_SECTION_REVIEW_STATUSES,
        ),
    )


def _key_events_section_from_raw(
    raw: Any,
    known_source_ids: set[str],
) -> EnrichmentKeyEventsSection | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PlaceEnrichmentDataError("Section key_events must be an object or null.")
    items_raw = raw.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise PlaceEnrichmentDataError("key_events.items must contain at least one event.")
    items: list[EnrichmentKeyEvent] = []
    for index, item_raw in enumerate(items_raw, start=1):
        if not isinstance(item_raw, dict):
            raise PlaceEnrichmentDataError("key_events.items entries must be objects.")
        source_ids = _as_str_tuple(
            item_raw.get("source_ids"),
            f"key_events.items[{index}].source_ids",
            required=True,
        )
        _validate_source_ids(source_ids, f"key_events.items[{index}].source_ids", known_source_ids)
        items.append(
            EnrichmentKeyEvent(
                summary_hu=_as_str(
                    item_raw.get("summary_hu"),
                    f"key_events.items[{index}].summary_hu",
                    required=True,
                )
                or "",
                passage_refs=_as_str_tuple(
                    item_raw.get("passage_refs"),
                    f"key_events.items[{index}].passage_refs",
                    required=True,
                ),
                source_ids=source_ids,
            )
        )
    return EnrichmentKeyEventsSection(
        items=tuple(items),
        confidence=_enum(raw.get("confidence"), "key_events.confidence", ALLOWED_CONFIDENCE_VALUES),
        review_status=_enum(
            raw.get("review_status"),
            "key_events.review_status",
            ALLOWED_SECTION_REVIEW_STATUSES,
        ),
    )


def _enrichment_from_raw(raw: Any, known_source_ids: set[str]) -> PlaceEnrichment:
    if not isinstance(raw, dict):
        raise PlaceEnrichmentDataError("Enrichment records must be objects.")
    place_id = _as_str(raw.get("place_id"), "place_id", required=True) or ""
    canonical_ids = set(place_ids())
    if place_id not in canonical_ids:
        if place_id in _all_legacy_place_ids():
            raise PlaceEnrichmentDataError(f"Enrichment uses legacy place_id: {place_id}")
        raise PlaceEnrichmentDataError(f"Enrichment references unknown place_id: {place_id}")

    sections_raw = raw.get("sections")
    if not isinstance(sections_raw, dict):
        raise PlaceEnrichmentDataError(f"Enrichment {place_id} must define sections.")
    sections: dict[str, EnrichmentTextSection | EnrichmentKeyEventsSection] = {}
    for key in TEXT_SECTION_KEYS:
        section = _text_section_from_raw(key, sections_raw.get(key), known_source_ids)
        if section is not None:
            sections[key] = section
    key_events = _key_events_section_from_raw(sections_raw.get("key_events"), known_source_ids)
    if key_events is not None:
        sections["key_events"] = key_events
    if not sections:
        raise PlaceEnrichmentDataError(f"Enrichment {place_id} must contain at least one section.")

    related_route_ids = _as_str_tuple(raw.get("related_route_ids"), "related_route_ids")
    known_route_ids = {route.route_id for route in load_biblical_routes()}
    unknown_route_ids = [route_id for route_id in related_route_ids if route_id not in known_route_ids]
    if unknown_route_ids:
        raise PlaceEnrichmentDataError(
            f"Enrichment {place_id} references unknown route_id(s): {', '.join(unknown_route_ids)}"
        )
    return PlaceEnrichment(
        place_id=place_id,
        profile_tier=_enum(raw.get("profile_tier"), "profile_tier", ALLOWED_PROFILE_TIERS),
        content_version=int(raw.get("content_version") or 1),
        sections=sections,
        related_route_ids=related_route_ids,
        editorial_notes_hu=_as_str(raw.get("editorial_notes_hu"), "editorial_notes_hu"),
        overall_review_status=_enum(
            raw.get("overall_review_status"),
            "overall_review_status",
            ALLOWED_OVERALL_REVIEW_STATUSES,
        ),
    )


@lru_cache(maxsize=1)
def load_place_enrichments(path: Path = PLACE_ENRICHMENTS_PATH) -> tuple[PlaceEnrichment, ...]:
    raw = _load_json(path, [])
    if not isinstance(raw, list):
        raise PlaceEnrichmentDataError("Place enrichments JSON must contain a list.")
    known_source_ids = set(place_enrichment_sources_by_id())
    enrichments = tuple(_enrichment_from_raw(item, known_source_ids) for item in raw)
    ids = [item.place_id for item in enrichments]
    if len(ids) != len(set(ids)):
        raise PlaceEnrichmentDataError("Duplicate enrichment place_id found.")
    return enrichments


def place_enrichments_by_id(
    enrichments: tuple[PlaceEnrichment, ...] | None = None,
) -> dict[str, PlaceEnrichment]:
    return {item.place_id: item for item in (enrichments or load_place_enrichments())}


def get_place_enrichment(place_id: str) -> PlaceEnrichment | None:
    return place_enrichments_by_id().get(place_id)


def related_route_ids_for_place(place_id: str) -> tuple[str, ...]:
    route_ids: list[str] = []
    for route in load_biblical_routes():
        if any(stop.place_id == place_id for stop in route.stops):
            route_ids.append(route.route_id)
    return tuple(route_ids)


__all__ = [
    "ALLOWED_CONFIDENCE_VALUES",
    "ALLOWED_OVERALL_REVIEW_STATUSES",
    "ALLOWED_PROFILE_TIERS",
    "ALLOWED_SECTION_REVIEW_STATUSES",
    "CONFIDENCE_LABELS_HU",
    "EnrichmentKeyEvent",
    "EnrichmentKeyEventsSection",
    "EnrichmentTextSection",
    "PLACE_ENRICHMENT_PRIORITY_PATH",
    "PLACE_ENRICHMENT_SOURCES_PATH",
    "PLACE_ENRICHMENTS_PATH",
    "PlaceEnrichment",
    "PlaceEnrichmentDataError",
    "PlaceEnrichmentSource",
    "SECTION_LABELS_HU",
    "SECTION_REVIEW_LABELS_HU",
    "TEXT_SECTION_KEYS",
    "get_place_enrichment",
    "load_place_enrichment_sources",
    "load_place_enrichments",
    "place_enrichment_sources_by_id",
    "place_enrichments_by_id",
    "related_route_ids_for_place",
]
