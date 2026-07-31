"""Hand-defined and data-driven passage-to-place links for the biblical map."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any, MutableMapping

from biblical_map_data import BIBLICAL_MAP_PLACES, DATA_DIR
from biblical_passage_refs import passage_refs_overlap

if "requests" not in sys.modules:
    try:
        import requests as _requests  # noqa: F401
    except ImportError:  # pragma: no cover - local test environment only
        sys.modules["requests"] = SimpleNamespace(
            ConnectionError=ConnectionError,
            Timeout=TimeoutError,
            get=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("requests is not installed")
            ),
        )

from ruf_bible_service import ParsedReference, parse_bible_reference


MAP_LAST_PROCESSED_REFERENCE_KEY = "_biblical_map_last_processed_reference"
MAP_SELECTION_SOURCE_KEY = "_biblical_map_selection_source"

MAP_SELECTION_SOURCE_AUTO = "auto"
MAP_SELECTION_SOURCE_MANUAL = "manual"
MAP_SELECTION_SOURCE_UNMATCHED = "unmatched"

PASSAGE_LINK_TYPE_PRIMARY_EVENT_LOCATION = "primary_event_location"
PASSAGE_LINK_SOURCE_NOTE = "kézzel definiált demonstrációs kapcsolat"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"


@dataclass(frozen=True)
class BiblicalPassagePlaceLink:
    normalized_reference: str
    place_id: str
    link_type: str
    reason_hu: str
    source_note: str
    parsed_reference: ParsedReference


def _build_passage_link(
    reference: str,
    place_id: str,
    reason_hu: str,
    *,
    source_note: str = PASSAGE_LINK_SOURCE_NOTE,
) -> BiblicalPassagePlaceLink:
    parsed = parse_bible_reference(reference)
    return BiblicalPassagePlaceLink(
        normalized_reference=parsed.normalized_reference,
        place_id=place_id,
        link_type=PASSAGE_LINK_TYPE_PRIMARY_EVENT_LOCATION,
        reason_hu=reason_hu,
        source_note=source_note,
        parsed_reference=parsed,
    )


# Backward-compatible seed links. Prefer data/biblical_places/passage_place_links.json.
_SEED_PASSAGE_LINKS: tuple[BiblicalPassagePlaceLink, ...] = (
    _build_passage_link(
        "ApCsel 18,1-18",
        "corinth",
        "Pál korinthusi szolgálatának demonstrációs szakasza.",
    ),
    _build_passage_link(
        "Ef 1,1-14",
        "ephesus",
        "Az efezusi levél címzett gyülekezetéhez kapcsolt demonstrációs hely.",
    ),
    _build_passage_link(
        "ApCsel 19,1-41",
        "ephesus",
        "Pál efezusi szolgálatának és az efezusi konfliktusnak a pilot helykapcsolata.",
    ),
    _build_passage_link(
        "Mt 2,23",
        "nazareth",
        "Jézus názáreti letelepedésére utaló demonstrációs szakasz.",
    ),
    _build_passage_link(
        "Mk 1,21-28",
        "capernaum",
        "A kapernaumi zsinagógai jelenet demonstrációs helykapcsolata.",
    ),
    _build_passage_link(
        "ApCsel 2,1-13",
        "jerusalem",
        "A pünkösdi jeruzsálemi esemény demonstrációs helykapcsolata.",
    ),
)


@lru_cache(maxsize=1)
def load_passage_place_links(
    path: Path | None = None,
) -> tuple[BiblicalPassagePlaceLink, ...]:
    target = path or PASSAGE_LINKS_PATH
    links: list[BiblicalPassagePlaceLink] = []
    seen: set[tuple[str, str]] = set()
    if target.exists():
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"Passage links JSON must be a list: {target}")
        for item in raw:
            if not isinstance(item, dict):
                continue
            reference = str(item.get("reference") or "").strip()
            place_id = str(item.get("place_id") or "").strip()
            reason = str(item.get("reason_hu") or "").strip() or "Pilot passage-place link."
            source_note = str(item.get("source_note") or "").strip() or "pilot passage index"
            if not reference or not place_id:
                continue
            link = _build_passage_link(
                reference,
                place_id,
                reason,
                source_note=source_note,
            )
            key = (link.normalized_reference, link.place_id)
            if key in seen:
                continue
            seen.add(key)
            links.append(link)
    if not links:
        links.extend(_SEED_PASSAGE_LINKS)
    return tuple(links)


BIBLICAL_PASSAGE_PLACE_LINKS: tuple[BiblicalPassagePlaceLink, ...] = load_passage_place_links()


def _valid_place_ids() -> set[str]:
    return {place.place_id for place in BIBLICAL_MAP_PLACES}


def _parse_reference(reference: str | None) -> ParsedReference | None:
    raw = (reference or "").strip()
    if not raw:
        return None
    try:
        return parse_bible_reference(raw)
    except ValueError:
        return None


def find_primary_place_link_for_passage(
    reference: str | None,
    links: tuple[BiblicalPassagePlaceLink, ...] | None = None,
) -> BiblicalPassagePlaceLink | None:
    matches = find_place_links_for_passage(reference, links=links)
    return matches[0] if matches else None


def find_place_links_for_passage(
    reference: str | None,
    links: tuple[BiblicalPassagePlaceLink, ...] | None = None,
) -> tuple[BiblicalPassagePlaceLink, ...]:
    """Return all overlapping passage-place links for a reference."""
    parsed = _parse_reference(reference)
    if parsed is None:
        return ()
    resolved_links = links if links is not None else load_passage_place_links()
    valid_ids = _valid_place_ids()
    matches: list[BiblicalPassagePlaceLink] = []
    seen_place_ids: set[str] = set()
    for link in resolved_links:
        if link.place_id not in valid_ids:
            continue
        if not passage_refs_overlap(parsed.normalized_reference, link.normalized_reference):
            continue
        if link.place_id in seen_place_ids:
            continue
        seen_place_ids.add(link.place_id)
        matches.append(link)
    return tuple(matches)


def find_primary_place_for_passage(reference: str | None) -> str | None:
    link = find_primary_place_link_for_passage(reference)
    return link.place_id if link else None


def validate_passage_place_links(
    links: tuple[BiblicalPassagePlaceLink, ...] | None = None,
) -> tuple[BiblicalPassagePlaceLink, ...]:
    resolved = links if links is not None else load_passage_place_links()
    valid_ids = _valid_place_ids()
    for link in resolved:
        if link.place_id not in valid_ids:
            raise ValueError(f"Passage link references unknown place_id: {link.place_id}")
    return resolved


def normalized_passage_reference(reference: str | None) -> str:
    parsed = _parse_reference(reference)
    return parsed.normalized_reference if parsed else ""


def apply_passage_place_selection(
    session_state: MutableMapping[str, Any],
    reference: str | None,
    *,
    selected_place_key: str,
) -> BiblicalPassagePlaceLink | None:
    normalized_reference = normalized_passage_reference(reference)
    last_reference = str(session_state.get(MAP_LAST_PROCESSED_REFERENCE_KEY) or "")
    link = find_primary_place_link_for_passage(reference)

    if normalized_reference and normalized_reference != last_reference:
        session_state[MAP_LAST_PROCESSED_REFERENCE_KEY] = normalized_reference
        if link is not None:
            session_state[selected_place_key] = link.place_id
            session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_AUTO
        else:
            session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_UNMATCHED
    elif not normalized_reference and last_reference:
        session_state[MAP_LAST_PROCESSED_REFERENCE_KEY] = ""
        session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_UNMATCHED
    elif link is not None and selected_place_key not in session_state:
        session_state[selected_place_key] = link.place_id
        session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_AUTO
        session_state[MAP_LAST_PROCESSED_REFERENCE_KEY] = normalized_reference

    return link


__all__ = [
    "BIBLICAL_PASSAGE_PLACE_LINKS",
    "BiblicalPassagePlaceLink",
    "MAP_LAST_PROCESSED_REFERENCE_KEY",
    "MAP_SELECTION_SOURCE_AUTO",
    "MAP_SELECTION_SOURCE_KEY",
    "MAP_SELECTION_SOURCE_MANUAL",
    "MAP_SELECTION_SOURCE_UNMATCHED",
    "PASSAGE_LINK_SOURCE_NOTE",
    "PASSAGE_LINKS_PATH",
    "apply_passage_place_selection",
    "find_place_links_for_passage",
    "find_primary_place_for_passage",
    "find_primary_place_link_for_passage",
    "load_passage_place_links",
    "normalized_passage_reference",
    "validate_passage_place_links",
]
