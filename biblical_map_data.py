"""Data loading and validation for the biblical map prototype."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data" / "biblical_places"
PILOT_PLACES_PATH = DATA_DIR / "pilot_places.json"
BIBLICAL_PLACES_CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
SOURCES_PATH = DATA_DIR / "sources.json"

ALLOWED_IDENTIFICATION_STATUSES = {
    "certain",
    "probable",
    "possible",
    "disputed",
    "unknown",
}
ALLOWED_GEOMETRY_TYPES = {"point"}
ALLOWED_TRANSLATION_STATUSES = {
    "not_translated",
    "machine_draft",
    "human_translated",
    "not_required",
}
ALLOWED_REVIEW_STATUSES = {
    "prototype",
    "draft",
    "needs_review",
    "reviewed",
    "approved",
}


@dataclass(frozen=True)
class BiblicalMapSource:
    source_id: str
    provider: str
    title: str
    original_language: str | None
    source_url: str | None
    license: str
    attribution: str | None
    retrieved_at: str | None
    source_type: str
    reliability_tier: str
    notes_hu: str | None


@dataclass(frozen=True)
class BiblicalExegeticalNote:
    passage_reference: str
    title_hu: str
    note_hu: str
    limitations_hu: str | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class BiblicalPlace:
    place_id: str
    name_hu: str
    name_en: str | None
    ancient_names: tuple[str, ...]
    original_names: tuple[str, ...]
    transliterations: tuple[str, ...]
    modern_name: str | None
    modern_country: str
    place_type: str
    identification_status: str
    confidence_note_hu: str | None
    latitude: float
    longitude: float
    region_hu: str | None
    ancient_region: str | None
    geometry_type: str
    coordinate_source_id: str
    card_summary_hu: str | None
    card_summary_en: str | None
    is_primary_demo_place: bool
    geography_hu: str | None
    history_hu: str | None
    political_context_hu: str | None
    economic_context_hu: str | None
    social_context_hu: str | None
    religious_context_hu: str | None
    archaeology_hu: str | None
    biblical_significance_hu: str | None
    modern_context_hu: str | None
    exegetical_notes: tuple[BiblicalExegeticalNote, ...]
    source_ids: tuple[str, ...]
    translation_status: str
    translation_method: str | None
    translation_model: str | None
    translated_at: str | None
    review_status: str
    reviewed_by: str | None
    reviewed_at: str | None
    openbible_id: str | None
    pleiades_id: str | None
    step_id: str | None
    wikidata_id: str | None

    @property
    def ancient_name(self) -> str:
        return " / ".join(self.ancient_names)

    @property
    def description(self) -> str:
        return self.card_summary_hu or ""

    @property
    def is_primary(self) -> bool:
        return self.is_primary_demo_place

    @property
    def source_note(self) -> str:
        return "demonstrációs adat"


class BiblicalMapDataError(ValueError):
    pass


def _as_str(value: Any, field_name: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise BiblicalMapDataError(f"Missing required field: {field_name}")
        return None
    if not isinstance(value, str):
        raise BiblicalMapDataError(f"Field {field_name} must be a string.")
    text = value.strip()
    if required and not text:
        raise BiblicalMapDataError(f"Field {field_name} must not be empty.")
    return text or None


def _as_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BiblicalMapDataError(f"Field {field_name} must be a list.")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise BiblicalMapDataError(f"Field {field_name} must contain strings only.")
        text = item.strip()
        if text:
            items.append(text)
    return tuple(items)


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BiblicalMapDataError(f"Field {field_name} must be a number.")
    return float(value)


def _as_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise BiblicalMapDataError(f"Field {field_name} must be a boolean.")
    return value


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BiblicalMapDataError(f"Biblical map data file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BiblicalMapDataError(f"Invalid JSON in biblical map data file: {path}") from exc


def _source_from_raw(raw: dict[str, Any]) -> BiblicalMapSource:
    return BiblicalMapSource(
        source_id=_as_str(raw.get("source_id"), "source_id", required=True) or "",
        provider=_as_str(raw.get("provider"), "provider", required=True) or "",
        title=_as_str(raw.get("title"), "title", required=True) or "",
        original_language=_as_str(raw.get("original_language"), "original_language"),
        source_url=_as_str(raw.get("source_url"), "source_url"),
        license=_as_str(raw.get("license"), "license", required=True) or "",
        attribution=_as_str(raw.get("attribution"), "attribution"),
        retrieved_at=_as_str(raw.get("retrieved_at"), "retrieved_at"),
        source_type=_as_str(raw.get("source_type"), "source_type", required=True) or "",
        reliability_tier=_as_str(raw.get("reliability_tier"), "reliability_tier", required=True) or "",
        notes_hu=_as_str(raw.get("notes_hu"), "notes_hu"),
    )


def _exegetical_note_from_raw(raw: Any) -> BiblicalExegeticalNote:
    if not isinstance(raw, dict):
        raise BiblicalMapDataError("Exegetical notes must be objects.")
    return BiblicalExegeticalNote(
        passage_reference=_as_str(raw.get("passage_reference"), "passage_reference", required=True) or "",
        title_hu=_as_str(raw.get("title_hu"), "title_hu", required=True) or "",
        note_hu=_as_str(raw.get("note_hu"), "note_hu", required=True) or "",
        limitations_hu=_as_str(raw.get("limitations_hu"), "limitations_hu"),
        source_ids=_as_str_tuple(raw.get("source_ids"), "source_ids"),
    )


def _place_from_raw(raw: Any) -> BiblicalPlace:
    if not isinstance(raw, dict):
        raise BiblicalMapDataError("Biblical place records must be objects.")
    name_en = _as_str(raw.get("name_en"), "name_en")
    name_hu = _as_str(raw.get("name_hu"), "name_hu") or name_en
    if not name_hu:
        name_hu = _as_str(raw.get("place_id"), "place_id", required=True)
    return BiblicalPlace(
        place_id=_as_str(raw.get("place_id"), "place_id", required=True) or "",
        name_hu=name_hu or "",
        name_en=name_en,
        ancient_names=_as_str_tuple(raw.get("ancient_names"), "ancient_names"),
        original_names=_as_str_tuple(raw.get("original_names"), "original_names"),
        transliterations=_as_str_tuple(raw.get("transliterations"), "transliterations"),
        modern_name=_as_str(raw.get("modern_name"), "modern_name"),
        modern_country=_as_str(raw.get("modern_country"), "modern_country") or "",
        place_type=_as_str(raw.get("place_type"), "place_type") or "",
        identification_status=_as_str(
            raw.get("identification_status"),
            "identification_status",
            required=True,
        )
        or "",
        confidence_note_hu=_as_str(raw.get("confidence_note_hu"), "confidence_note_hu"),
        latitude=_as_float(raw.get("latitude"), "latitude"),
        longitude=_as_float(raw.get("longitude"), "longitude"),
        region_hu=_as_str(raw.get("region_hu"), "region_hu"),
        ancient_region=_as_str(raw.get("ancient_region"), "ancient_region"),
        geometry_type=_as_str(raw.get("geometry_type"), "geometry_type", required=True) or "",
        coordinate_source_id=_as_str(raw.get("coordinate_source_id"), "coordinate_source_id", required=True)
        or "",
        card_summary_hu=_as_str(raw.get("card_summary_hu"), "card_summary_hu"),
        card_summary_en=_as_str(raw.get("card_summary_en"), "card_summary_en"),
        is_primary_demo_place=_as_bool(raw.get("is_primary_demo_place"), "is_primary_demo_place"),
        geography_hu=_as_str(raw.get("geography_hu"), "geography_hu"),
        history_hu=_as_str(raw.get("history_hu"), "history_hu"),
        political_context_hu=_as_str(raw.get("political_context_hu"), "political_context_hu"),
        economic_context_hu=_as_str(raw.get("economic_context_hu"), "economic_context_hu"),
        social_context_hu=_as_str(raw.get("social_context_hu"), "social_context_hu"),
        religious_context_hu=_as_str(raw.get("religious_context_hu"), "religious_context_hu"),
        archaeology_hu=_as_str(raw.get("archaeology_hu"), "archaeology_hu"),
        biblical_significance_hu=_as_str(raw.get("biblical_significance_hu"), "biblical_significance_hu"),
        modern_context_hu=_as_str(raw.get("modern_context_hu"), "modern_context_hu"),
        exegetical_notes=tuple(
            _exegetical_note_from_raw(item) for item in raw.get("exegetical_notes") or []
        ),
        source_ids=_as_str_tuple(raw.get("source_ids"), "source_ids"),
        translation_status=_as_str(raw.get("translation_status"), "translation_status", required=True)
        or "",
        translation_method=_as_str(raw.get("translation_method"), "translation_method"),
        translation_model=_as_str(raw.get("translation_model"), "translation_model"),
        translated_at=_as_str(raw.get("translated_at"), "translated_at"),
        review_status=_as_str(raw.get("review_status"), "review_status", required=True) or "",
        reviewed_by=_as_str(raw.get("reviewed_by"), "reviewed_by"),
        reviewed_at=_as_str(raw.get("reviewed_at"), "reviewed_at"),
        openbible_id=_as_str(raw.get("openbible_id"), "openbible_id"),
        pleiades_id=_as_str(raw.get("pleiades_id"), "pleiades_id"),
        step_id=_as_str(raw.get("step_id"), "step_id"),
        wikidata_id=_as_str(raw.get("wikidata_id"), "wikidata_id"),
    )


@lru_cache(maxsize=1)
def load_biblical_sources(path: Path = SOURCES_PATH) -> tuple[BiblicalMapSource, ...]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise BiblicalMapDataError("Biblical map sources JSON must contain a list.")
    sources = tuple(_source_from_raw(item) for item in raw)
    ids = [source.source_id for source in sources]
    if len(ids) != len(set(ids)):
        raise BiblicalMapDataError("Duplicate biblical map source_id found.")
    return sources


def source_ids(sources: tuple[BiblicalMapSource, ...] | None = None) -> set[str]:
    return {source.source_id for source in (sources or load_biblical_sources())}


def sources_by_id(
    sources: tuple[BiblicalMapSource, ...] | None = None,
) -> dict[str, BiblicalMapSource]:
    return {source.source_id: source for source in (sources or load_biblical_sources())}


def get_biblical_source(source_id: str) -> BiblicalMapSource | None:
    return sources_by_id().get(source_id)


def validate_biblical_places(
    places: tuple[BiblicalPlace, ...],
    sources: tuple[BiblicalMapSource, ...] | None = None,
) -> tuple[BiblicalPlace, ...]:
    if not places:
        raise BiblicalMapDataError("At least one biblical map place is required.")
    ids = [place.place_id for place in places]
    if len(ids) != len(set(ids)):
        raise BiblicalMapDataError("Duplicate biblical map place_id found.")
    source_id_set = source_ids(sources)
    primary_count = 0
    for place in places:
        if not place.place_id.strip():
            raise BiblicalMapDataError("Every biblical map place_id must be non-empty.")
        if not place.name_hu.strip():
            raise BiblicalMapDataError(f"Place {place.place_id} must have name_hu.")
        if not validate_place_record(place):
            raise BiblicalMapDataError(f"Place {place.place_id} has invalid coordinates.")
        if place.identification_status not in ALLOWED_IDENTIFICATION_STATUSES:
            raise BiblicalMapDataError(
                f"Place {place.place_id} has invalid identification_status: "
                f"{place.identification_status}"
            )
        if place.geometry_type not in ALLOWED_GEOMETRY_TYPES:
            raise BiblicalMapDataError(
                f"Place {place.place_id} has invalid geometry_type: {place.geometry_type}"
            )
        if place.translation_status not in ALLOWED_TRANSLATION_STATUSES:
            raise BiblicalMapDataError(
                f"Place {place.place_id} has invalid translation_status: "
                f"{place.translation_status}"
            )
        if place.review_status not in ALLOWED_REVIEW_STATUSES:
            raise BiblicalMapDataError(
                f"Place {place.place_id} has invalid review_status: {place.review_status}"
            )
        referenced_source_ids = set(place.source_ids)
        if place.coordinate_source_id:
            referenced_source_ids.add(place.coordinate_source_id)
        for note in place.exegetical_notes:
            referenced_source_ids.update(note.source_ids)
        missing = sorted(source_id for source_id in referenced_source_ids if source_id not in source_id_set)
        if missing:
            raise BiblicalMapDataError(
                f"Place {place.place_id} references unknown source_id(s): {', '.join(missing)}"
            )
        if place.is_primary_demo_place:
            primary_count += 1
    if primary_count != 1:
        raise BiblicalMapDataError("Exactly one primary demo biblical map place is required.")
    return places


def load_biblical_places(
    places_path: Path = BIBLICAL_PLACES_CATALOG_PATH,
    sources_path: Path = SOURCES_PATH,
) -> tuple[BiblicalPlace, ...]:
    raw = _load_json(places_path)
    if not isinstance(raw, list):
        raise BiblicalMapDataError("Biblical map places JSON must contain a list.")
    places = tuple(_place_from_raw(item) for item in raw)
    sources = load_biblical_sources(sources_path)
    return validate_biblical_places(places, sources)


def load_pilot_biblical_places(
    places_path: Path = PILOT_PLACES_PATH,
    sources_path: Path = SOURCES_PATH,
) -> tuple[BiblicalPlace, ...]:
    return load_biblical_places(places_path=places_path, sources_path=sources_path)


@lru_cache(maxsize=1)
def get_all_biblical_places() -> tuple[BiblicalPlace, ...]:
    return load_biblical_places()


def place_ids(places: tuple[BiblicalPlace, ...] | None = None) -> tuple[str, ...]:
    return tuple(place.place_id for place in (places or get_all_biblical_places()))


def places_by_id(
    places: tuple[BiblicalPlace, ...] | None = None,
) -> dict[str, BiblicalPlace]:
    return {place.place_id: place for place in (places or get_all_biblical_places())}


def get_biblical_place(place_id: str) -> BiblicalPlace | None:
    return places_by_id().get(place_id)


def get_primary_demo_place(
    places: tuple[BiblicalPlace, ...] | None = None,
) -> BiblicalPlace:
    return primary_place(places or get_all_biblical_places())


def primary_place(
    places: tuple[BiblicalPlace, ...] | None = None,
) -> BiblicalPlace:
    resolved = places or get_all_biblical_places()
    for place in resolved:
        if place.is_primary_demo_place:
            return place
    if not resolved:
        raise BiblicalMapDataError("At least one biblical map place is required.")
    return resolved[0]


def validate_place_record(place: BiblicalPlace) -> bool:
    if not place.place_id.strip() or not place.name_hu.strip():
        return False
    return -90 <= place.latitude <= 90 and -180 <= place.longitude <= 180


BIBLICAL_MAP_PLACES = get_all_biblical_places()


__all__ = [
    "ALLOWED_GEOMETRY_TYPES",
    "ALLOWED_IDENTIFICATION_STATUSES",
    "ALLOWED_REVIEW_STATUSES",
    "ALLOWED_TRANSLATION_STATUSES",
    "BIBLICAL_MAP_PLACES",
    "BIBLICAL_PLACES_CATALOG_PATH",
    "BiblicalExegeticalNote",
    "BiblicalMapDataError",
    "BiblicalMapSource",
    "BiblicalPlace",
    "DATA_DIR",
    "PILOT_PLACES_PATH",
    "SOURCES_PATH",
    "get_all_biblical_places",
    "get_biblical_place",
    "get_biblical_source",
    "get_primary_demo_place",
    "load_biblical_places",
    "load_pilot_biblical_places",
    "load_biblical_sources",
    "place_ids",
    "places_by_id",
    "primary_place",
    "source_ids",
    "sources_by_id",
    "validate_biblical_places",
    "validate_place_record",
]
