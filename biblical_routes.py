from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from biblical_map_data import BIBLICAL_PLACES_CATALOG_PATH, DATA_DIR, SOURCES_PATH
from biblical_passage_refs import (
    is_valid_chapter_range_reference,
    is_valid_cross_chapter_reference,
    parse_bible_reference,
    passage_refs_overlap,
    passage_span,
)


ROUTES_DIR = DATA_DIR.parent / "biblical_routes"
BIBLICAL_ROUTES_PATH = ROUTES_DIR / "biblical_routes.json"

ALLOWED_ROUTE_CATEGORIES = {
    "missionary_journey",
    "patriarchal_journey",
    "exodus",
    "wilderness_journey",
    "royal_campaign",
    "prophetic_journey",
    "deportation",
    "return_from_exile",
    "ministry_journey",
    "other",
}
ALLOWED_CERTAINTIES = {"certain", "probable", "possible", "disputed", "unknown", "mixed"}
ALLOWED_GEOMETRY_STATUSES = {
    "schematic",
    "reconstructed",
    "approximate",
    "exact",
    "unavailable",
}
ALLOWED_REVIEW_STATUSES = {"prototype", "draft", "needs_review", "reviewed", "approved"}
ALLOWED_STOP_TYPES = {
    "explicit_place",
    "inferred_stop",
    "embarkation",
    "disembarkation",
    "transit",
    "destination",
    "return_stop",
    "region",
    "uncertain_place",
}
ALLOWED_SEGMENT_TYPES = {"land", "sea", "river", "mixed", "schematic", "unknown"}
ALLOWED_MAPPING_STATUSES = {"mapped", "approximate", "textual_only"}
ALLOWED_SEQUENCE_STATUSES = {"explicit", "reconstructed_order", "uncertain_order"}
ROUTE_USER_TEXT_FIELDS = (
    "name_hu",
    "short_description_hu",
    "chronology_label_hu",
    "review_notes_hu",
)
STOP_USER_TEXT_FIELDS = (
    "place_name_override_hu",
    "event_summary_hu",
    "journey_phase",
    "mapping_notes_hu",
    "source_notes_hu",
)
SEGMENT_USER_TEXT_FIELDS = ("source_notes_hu",)
MOJIBAKE_MARKERS = ("\ufffd", "Ă", "Â", "ďż˝", "â€", "Å")
CORRUPTED_QUESTION_MARK_RE = re.compile(
    r"(?:(?<=[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])\?(?=[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])|"
    r"(?:^|[\s(])\?(?=[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]))"
)


class BiblicalRouteDataError(ValueError):
    pass


@dataclass(frozen=True)
class BiblicalRouteStop:
    order: int
    stop_id: str
    place_id: str | None
    place_name_override_hu: str | None
    passage_refs: tuple[str, ...]
    event_summary_hu: str
    certainty: str
    stop_type: str
    source_notes_hu: str | None
    mapping_status: str
    display_on_map: bool
    mapping_notes_hu: str | None
    sequence_status: str
    journey_phase: str | None = None


@dataclass(frozen=True)
class BiblicalRouteSegment:
    from_stop_id: str
    to_stop_id: str
    certainty: str
    segment_type: str
    geometry_status: str
    source_notes_hu: str | None
    waypoints: tuple[str, ...]
    geometry: Any | None


@dataclass(frozen=True)
class BiblicalRoute:
    route_id: str
    name_hu: str
    name_en: str | None
    short_description_hu: str
    route_category: str
    primary_passage_refs: tuple[str, ...]
    chronology_label_hu: str | None
    chronology_sort_key: int | float | str
    certainty: str
    geometry_status: str
    source_ids: tuple[str, ...]
    review_status: str
    review_notes_hu: str | None
    stops: tuple[BiblicalRouteStop, ...]
    segments: tuple[BiblicalRouteSegment, ...]
    evidence_model: dict[str, Any]
    route_family_id: str | None = None
    family_name_hu: str | None = None
    route_sequence_order: int | None = None
    previous_route_id: str | None = None
    next_route_id: str | None = None


@dataclass(frozen=True)
class BiblicalRouteStopMatch:
    route: BiblicalRoute
    stop: BiblicalRouteStop


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BiblicalRouteDataError(f"Biblical route data file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BiblicalRouteDataError(f"Invalid JSON in biblical route data file: {path}") from exc


def _as_str(value: Any, field_name: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise BiblicalRouteDataError(f"Missing required field: {field_name}")
        return None
    if not isinstance(value, str):
        raise BiblicalRouteDataError(f"Field {field_name} must be a string.")
    text = value.strip()
    if required and not text:
        raise BiblicalRouteDataError(f"Field {field_name} must not be empty.")
    return text or None


def validate_route_user_text(value: Any, field_path: str) -> None:
    if not isinstance(value, str) or not value:
        return
    if any(marker in value for marker in MOJIBAKE_MARKERS) or CORRUPTED_QUESTION_MARK_RE.search(value):
        raise BiblicalRouteDataError(f"Corrupted user-facing route text in {field_path}: {value!r}")


def _validate_user_text_fields(raw: dict[str, Any], fields: tuple[str, ...], prefix: str) -> None:
    for field in fields:
        value = raw.get(field)
        if value is not None:
            validate_route_user_text(value, f"{prefix}.{field}")


def _validate_user_text_tree(value: Any, field_path: str) -> None:
    if isinstance(value, str):
        validate_route_user_text(value, field_path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_user_text_tree(item, f"{field_path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_user_text_tree(item, f"{field_path}.{key}")


def _as_str_tuple(value: Any, field_name: str, *, required: bool = False) -> tuple[str, ...]:
    if value is None:
        if required:
            raise BiblicalRouteDataError(f"Missing required field: {field_name}")
        return ()
    if not isinstance(value, list):
        raise BiblicalRouteDataError(f"Field {field_name} must be a list.")
    items: list[str] = []
    for item in value:
        text = _as_str(item, field_name)
        if text:
            items.append(text)
    if required and not items:
        raise BiblicalRouteDataError(f"Field {field_name} must not be empty.")
    return tuple(items)


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BiblicalRouteDataError(f"Field {field_name} must be an integer.")
    return value


def _as_bool(value: Any, field_name: str, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise BiblicalRouteDataError(f"Field {field_name} must be a boolean.")
    return value


def _optional_enum(value: Any, field_name: str, allowed: set[str], *, default: str) -> str:
    if value is None:
        return default
    return _enum(value, field_name, allowed)


def _enum(value: Any, field_name: str, allowed: set[str]) -> str:
    text = _as_str(value, field_name, required=True) or ""
    if text not in allowed:
        raise BiblicalRouteDataError(f"Unknown {field_name}: {text}")
    return text


def _validate_passage_refs(refs: tuple[str, ...], field_name: str) -> None:
    if not refs:
        raise BiblicalRouteDataError(f"Field {field_name} must contain at least one reference.")
    for reference in refs:
        try:
            parse_bible_reference(reference)
        except ValueError as exc:
            if _is_valid_cross_chapter_reference(reference):
                continue
            if is_valid_chapter_range_reference(reference):
                continue
            raise BiblicalRouteDataError(f"Invalid passage reference in {field_name}: {reference}") from exc


def _is_valid_cross_chapter_reference(reference: str) -> bool:
    return is_valid_cross_chapter_reference(reference)


def _catalog_place_ids(path: Path) -> tuple[set[str], dict[str, str]]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise BiblicalRouteDataError(f"Biblical places catalog must be a list: {path}")
    active_ids: set[str] = set()
    legacy_to_canonical: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        place_id = str(item.get("place_id") or "").strip()
        if not place_id:
            continue
        active_ids.add(place_id)
        for legacy_id in item.get("legacy_place_ids") or []:
            legacy_text = str(legacy_id or "").strip()
            if not legacy_text:
                continue
            existing = legacy_to_canonical.get(legacy_text)
            if existing and existing != place_id:
                raise BiblicalRouteDataError(
                    f"Legacy place_id maps to multiple canonical records: {legacy_text}"
                )
            legacy_to_canonical[legacy_text] = place_id
    return active_ids, legacy_to_canonical


def _source_ids(path: Path) -> set[str]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise BiblicalRouteDataError(f"Biblical sources must be a list: {path}")
    return {str(item.get("source_id") or "").strip() for item in raw if isinstance(item, dict)}


def _resolve_place_id(
    place_id: str,
    *,
    active_place_ids: set[str],
    legacy_to_canonical: dict[str, str],
    allow_legacy_place_ids: bool,
) -> str:
    if place_id in active_place_ids:
        return place_id
    if place_id in legacy_to_canonical:
        if allow_legacy_place_ids:
            return legacy_to_canonical[place_id]
        raise BiblicalRouteDataError(f"Route uses legacy place_id without compatibility mode: {place_id}")
    raise BiblicalRouteDataError(f"Route references unknown place_id: {place_id}")


def _stop_from_raw(
    raw: Any,
    *,
    active_place_ids: set[str],
    legacy_to_canonical: dict[str, str],
    allow_legacy_place_ids: bool,
) -> BiblicalRouteStop:
    if not isinstance(raw, dict):
        raise BiblicalRouteDataError("Route stops must be objects.")
    _validate_user_text_fields(raw, STOP_USER_TEXT_FIELDS, "stops")
    passage_refs = _as_str_tuple(raw.get("passage_refs"), "stops.passage_refs", required=True)
    _validate_passage_refs(passage_refs, "stops.passage_refs")
    mapping_status = _optional_enum(
        raw.get("mapping_status"),
        "stops.mapping_status",
        ALLOWED_MAPPING_STATUSES,
        default="mapped",
    )
    display_on_map = _as_bool(raw.get("display_on_map"), "stops.display_on_map", default=True)
    sequence_status = _optional_enum(
        raw.get("sequence_status"),
        "stops.sequence_status",
        ALLOWED_SEQUENCE_STATUSES,
        default="explicit",
    )
    raw_place_id = _as_str(raw.get("place_id"), "stops.place_id")
    place_name_override_hu = _as_str(raw.get("place_name_override_hu"), "stops.place_name_override_hu")
    mapping_notes_hu = _as_str(raw.get("mapping_notes_hu"), "stops.mapping_notes_hu")
    if mapping_status == "textual_only":
        if raw_place_id is not None:
            raise BiblicalRouteDataError("textual_only stop must not define place_id.")
        if not place_name_override_hu:
            raise BiblicalRouteDataError("textual_only stop must define place_name_override_hu.")
        if display_on_map:
            raise BiblicalRouteDataError("textual_only stop must use display_on_map=false.")
        if not mapping_notes_hu:
            raise BiblicalRouteDataError("textual_only stop must define mapping_notes_hu.")
        place_id = None
    else:
        if raw_place_id is None:
            raise BiblicalRouteDataError(f"{mapping_status} stop must define place_id.")
        if not display_on_map:
            raise BiblicalRouteDataError(f"{mapping_status} stop must use display_on_map=true.")
        place_id = _resolve_place_id(
            raw_place_id,
            active_place_ids=active_place_ids,
            legacy_to_canonical=legacy_to_canonical,
            allow_legacy_place_ids=allow_legacy_place_ids,
        )
    return BiblicalRouteStop(
        order=_as_int(raw.get("order"), "stops.order"),
        stop_id=_as_str(raw.get("stop_id"), "stops.stop_id", required=True) or "",
        place_id=place_id,
        place_name_override_hu=place_name_override_hu,
        passage_refs=passage_refs,
        event_summary_hu=_as_str(raw.get("event_summary_hu"), "stops.event_summary_hu", required=True) or "",
        certainty=_enum(raw.get("certainty"), "stops.certainty", ALLOWED_CERTAINTIES),
        stop_type=_enum(raw.get("stop_type"), "stops.stop_type", ALLOWED_STOP_TYPES),
        source_notes_hu=_as_str(raw.get("source_notes_hu"), "stops.source_notes_hu"),
        mapping_status=mapping_status,
        display_on_map=display_on_map,
        mapping_notes_hu=mapping_notes_hu,
        sequence_status=sequence_status,
        journey_phase=_as_str(raw.get("journey_phase"), "stops.journey_phase"),
    )


def _segment_from_raw(raw: Any, stop_ids: set[str]) -> BiblicalRouteSegment:
    if not isinstance(raw, dict):
        raise BiblicalRouteDataError("Route segments must be objects.")
    _validate_user_text_fields(raw, SEGMENT_USER_TEXT_FIELDS, "segments")
    from_stop_id = _as_str(raw.get("from_stop_id"), "segments.from_stop_id", required=True) or ""
    to_stop_id = _as_str(raw.get("to_stop_id"), "segments.to_stop_id", required=True) or ""
    if from_stop_id not in stop_ids:
        raise BiblicalRouteDataError(f"Segment references unknown from_stop_id: {from_stop_id}")
    if to_stop_id not in stop_ids:
        raise BiblicalRouteDataError(f"Segment references unknown to_stop_id: {to_stop_id}")
    if from_stop_id == to_stop_id:
        raise BiblicalRouteDataError(f"Segment cannot reference the same stop twice: {from_stop_id}")
    return BiblicalRouteSegment(
        from_stop_id=from_stop_id,
        to_stop_id=to_stop_id,
        certainty=_enum(raw.get("certainty"), "segments.certainty", ALLOWED_CERTAINTIES),
        segment_type=_enum(raw.get("segment_type"), "segments.segment_type", ALLOWED_SEGMENT_TYPES),
        geometry_status=_enum(
            raw.get("geometry_status"),
            "segments.geometry_status",
            ALLOWED_GEOMETRY_STATUSES,
        ),
        source_notes_hu=_as_str(raw.get("source_notes_hu"), "segments.source_notes_hu"),
        waypoints=_as_str_tuple(raw.get("waypoints"), "segments.waypoints"),
        geometry=raw.get("geometry"),
    )


def _route_from_raw(
    raw: Any,
    *,
    active_place_ids: set[str],
    legacy_to_canonical: dict[str, str],
    known_source_ids: set[str],
    allow_legacy_place_ids: bool,
) -> BiblicalRoute:
    if not isinstance(raw, dict):
        raise BiblicalRouteDataError("Route records must be objects.")
    _validate_user_text_fields(raw, ROUTE_USER_TEXT_FIELDS, "routes")
    if isinstance(raw.get("evidence_model"), dict):
        _validate_user_text_tree(raw["evidence_model"], "routes.evidence_model")
    source_ids = _as_str_tuple(raw.get("source_ids"), "source_ids", required=True)
    missing_sources = [source_id for source_id in source_ids if source_id not in known_source_ids]
    if missing_sources:
        raise BiblicalRouteDataError(f"Route references unknown source_ids: {', '.join(missing_sources)}")
    primary_passage_refs = _as_str_tuple(
        raw.get("primary_passage_refs"),
        "primary_passage_refs",
        required=True,
    )
    _validate_passage_refs(primary_passage_refs, "primary_passage_refs")
    raw_stops = raw.get("stops")
    if not isinstance(raw_stops, list) or not raw_stops:
        raise BiblicalRouteDataError("Route must contain at least one stop.")
    stops = tuple(
        _stop_from_raw(
            item,
            active_place_ids=active_place_ids,
            legacy_to_canonical=legacy_to_canonical,
            allow_legacy_place_ids=allow_legacy_place_ids,
        )
        for item in raw_stops
    )
    stop_ids = [stop.stop_id for stop in stops]
    if len(stop_ids) != len(set(stop_ids)):
        raise BiblicalRouteDataError("Route stop_id values must be unique within a route.")
    orders = [stop.order for stop in stops]
    if len(orders) != len(set(orders)):
        raise BiblicalRouteDataError("Route stop order values must be unique within a route.")
    if orders != sorted(orders) or orders != list(range(1, len(stops) + 1)):
        raise BiblicalRouteDataError("Route stop order values must be consecutive and sorted from 1.")
    segments = tuple(_segment_from_raw(item, set(stop_ids)) for item in raw.get("segments") or [])
    return BiblicalRoute(
        route_id=_as_str(raw.get("route_id"), "route_id", required=True) or "",
        name_hu=_as_str(raw.get("name_hu"), "name_hu", required=True) or "",
        name_en=_as_str(raw.get("name_en"), "name_en"),
        short_description_hu=_as_str(
            raw.get("short_description_hu"),
            "short_description_hu",
            required=True,
        )
        or "",
        route_category=_enum(raw.get("route_category"), "route_category", ALLOWED_ROUTE_CATEGORIES),
        primary_passage_refs=primary_passage_refs,
        chronology_label_hu=_as_str(raw.get("chronology_label_hu"), "chronology_label_hu"),
        chronology_sort_key=raw.get("chronology_sort_key"),
        certainty=_enum(raw.get("certainty"), "certainty", ALLOWED_CERTAINTIES),
        geometry_status=_enum(raw.get("geometry_status"), "geometry_status", ALLOWED_GEOMETRY_STATUSES),
        source_ids=source_ids,
        review_status=_enum(raw.get("review_status"), "review_status", ALLOWED_REVIEW_STATUSES),
        review_notes_hu=_as_str(raw.get("review_notes_hu"), "review_notes_hu"),
        stops=stops,
        segments=segments,
        evidence_model=raw.get("evidence_model") if isinstance(raw.get("evidence_model"), dict) else {},
        route_family_id=_as_str(raw.get("route_family_id"), "route_family_id"),
        family_name_hu=_as_str(raw.get("family_name_hu"), "family_name_hu"),
        route_sequence_order=(
            _as_int(raw.get("route_sequence_order"), "route_sequence_order")
            if raw.get("route_sequence_order") is not None
            else None
        ),
        previous_route_id=_as_str(raw.get("previous_route_id"), "previous_route_id"),
        next_route_id=_as_str(raw.get("next_route_id"), "next_route_id"),
    )


def load_biblical_routes(
    routes_path: Path = BIBLICAL_ROUTES_PATH,
    *,
    places_path: Path = BIBLICAL_PLACES_CATALOG_PATH,
    sources_path: Path = SOURCES_PATH,
    allow_legacy_place_ids: bool = False,
) -> tuple[BiblicalRoute, ...]:
    raw = _load_json(routes_path)
    if not isinstance(raw, list):
        raise BiblicalRouteDataError(f"Biblical routes JSON must be a list: {routes_path}")
    active_place_ids, legacy_to_canonical = _catalog_place_ids(places_path)
    known_source_ids = _source_ids(sources_path)
    routes = tuple(
        _route_from_raw(
            item,
            active_place_ids=active_place_ids,
            legacy_to_canonical=legacy_to_canonical,
            known_source_ids=known_source_ids,
            allow_legacy_place_ids=allow_legacy_place_ids,
        )
        for item in raw
    )
    route_ids = [route.route_id for route in routes]
    if len(route_ids) != len(set(route_ids)):
        raise BiblicalRouteDataError("Route route_id values must be unique.")
    return routes


def get_biblical_route(route_id: str) -> BiblicalRoute | None:
    for route in load_biblical_routes():
        if route.route_id == route_id:
            return route
    return None


def find_route_stop_matches_for_passage(
    reference: str | None,
    routes: tuple[BiblicalRoute, ...] | None = None,
) -> tuple[BiblicalRouteStopMatch, ...]:
    if passage_span(reference) is None:
        return ()
    resolved_routes = routes if routes is not None else load_biblical_routes()
    matches: list[BiblicalRouteStopMatch] = []
    for route in resolved_routes:
        for stop in route.stops:
            if any(passage_refs_overlap(reference, passage_ref) for passage_ref in stop.passage_refs):
                matches.append(BiblicalRouteStopMatch(route=route, stop=stop))
    return tuple(matches)


def route_options(routes: tuple[BiblicalRoute, ...] | None = None) -> list[str]:
    resolved_routes = routes if routes is not None else load_biblical_routes()
    return [route.route_id for route in sorted(resolved_routes, key=lambda item: item.chronology_sort_key)]


__all__ = [
    "ALLOWED_CERTAINTIES",
    "ALLOWED_GEOMETRY_STATUSES",
    "ALLOWED_MAPPING_STATUSES",
    "ALLOWED_ROUTE_CATEGORIES",
    "ALLOWED_SEGMENT_TYPES",
    "ALLOWED_SEQUENCE_STATUSES",
    "ALLOWED_STOP_TYPES",
    "BIBLICAL_ROUTES_PATH",
    "BiblicalRoute",
    "BiblicalRouteDataError",
    "BiblicalRouteSegment",
    "BiblicalRouteStop",
    "BiblicalRouteStopMatch",
    "find_route_stop_matches_for_passage",
    "get_biblical_route",
    "load_biblical_routes",
    "passage_refs_overlap",
    "route_options",
    "validate_route_user_text",
]
