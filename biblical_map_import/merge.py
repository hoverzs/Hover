"""Deterministic merge rules for biblical place imports."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from biblical_map_import.pilot_catalog import (
    MANUAL_LOCKED_PLACE_IDS,
    PROTECTED_CONTENT_FIELDS,
    PilotPlaceSpec,
)


REVIEW_RANK = {
    "prototype": 0,
    "draft": 1,
    "needs_review": 2,
    "reviewed": 3,
    "approved": 4,
}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict, tuple)) and len(value) == 0:
        return True
    return False


def _merge_unique_str_list(*groups: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        if not group:
            continue
        items = group if isinstance(group, (list, tuple)) else [group]
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
    return out


def clamp_review_status(existing: str | None, incoming: str | None) -> str:
    """Never auto-promote to reviewed/approved."""
    candidate = (incoming or existing or "needs_review").strip() or "needs_review"
    if candidate in {"reviewed", "approved"}:
        # Keep existing if it was already that high; otherwise cap at needs_review.
        existing_clean = (existing or "").strip()
        if existing_clean in {"reviewed", "approved"}:
            return existing_clean
        return "needs_review"
    return candidate


def merge_place_records(
    existing: dict[str, Any] | None,
    imported: dict[str, Any],
    *,
    locked: bool,
) -> dict[str, Any]:
    """Merge imported fields into an existing record without unsafe overwrites."""
    if existing is None:
        result = deepcopy(imported)
        result["review_status"] = clamp_review_status(None, result.get("review_status"))
        return result

    result = deepcopy(existing)
    for key, incoming in imported.items():
        if key == "place_id":
            continue
        if key == "source_ids":
            result[key] = _merge_unique_str_list(result.get(key), incoming)
            continue
        if key == "review_status":
            result[key] = clamp_review_status(result.get(key), incoming)
            continue
        if locked and key in PROTECTED_CONTENT_FIELDS and not _is_empty(result.get(key)):
            continue
        if _is_empty(result.get(key)) and not _is_empty(incoming):
            result[key] = deepcopy(incoming)
            continue
        if locked:
            continue
        # Non-locked sparse demo records may receive refreshed identity fields.
        if key in {
            "openbible_id",
            "pleiades_id",
            "wikidata_id",
            "step_id",
            "latitude",
            "longitude",
            "coordinate_source_id",
            "modern_name",
            "ancient_names",
            "original_names",
            "transliterations",
            "identification_status",
            "confidence_note_hu",
            "card_summary_hu",
            "region_hu",
            "ancient_region",
            "place_type",
            "modern_country",
            "name_en",
        }:
            if not _is_empty(incoming):
                result[key] = deepcopy(incoming)
    result["curation_lock"] = bool(locked or result.get("curation_lock"))
    result["source_ids"] = _merge_unique_str_list(result.get("source_ids"), imported.get("source_ids"))
    result["review_status"] = clamp_review_status(result.get("review_status"), imported.get("review_status"))
    return result


def empty_detail_fields() -> dict[str, Any]:
    return {
        "geography_hu": None,
        "history_hu": None,
        "political_context_hu": None,
        "economic_context_hu": None,
        "social_context_hu": None,
        "religious_context_hu": None,
        "archaeology_hu": None,
        "biblical_significance_hu": None,
        "modern_context_hu": None,
        "exegetical_notes": [],
        "card_summary_en": None,
        "translation_method": None,
        "translation_model": None,
        "translated_at": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "step_id": None,
    }


def build_imported_skeleton(
    spec: PilotPlaceSpec,
    *,
    latitude: float,
    longitude: float,
    ancient_names: list[str],
    original_names: list[str],
    transliterations: list[str],
    openbible_id: str | None,
    pleiades_id: str | None,
    wikidata_id: str | None,
    identification_status: str,
    confidence_note_hu: str,
    coordinate_source_id: str,
    source_ids: list[str],
    modern_name: str | None,
) -> dict[str, Any]:
    record = {
        "place_id": spec.place_id,
        "name_hu": spec.name_hu,
        "name_en": spec.name_en,
        "ancient_names": ancient_names,
        "original_names": original_names,
        "transliterations": transliterations,
        "modern_name": modern_name or spec.modern_name,
        "modern_country": spec.modern_country,
        "place_type": spec.place_type,
        "identification_status": identification_status,
        "confidence_note_hu": confidence_note_hu,
        "latitude": latitude,
        "longitude": longitude,
        "region_hu": spec.region_hu,
        "ancient_region": spec.ancient_region,
        "geometry_type": "point",
        "coordinate_source_id": coordinate_source_id,
        "card_summary_hu": spec.card_summary_hu,
        "is_primary_demo_place": spec.is_primary_demo_place,
        "source_ids": source_ids,
        "translation_status": "not_required",
        "review_status": "needs_review",
        "openbible_id": openbible_id,
        "pleiades_id": pleiades_id,
        "wikidata_id": wikidata_id,
        "curation_lock": spec.place_id in MANUAL_LOCKED_PLACE_IDS,
        "antioch_kind": spec.antioch_kind,
    }
    record.update(empty_detail_fields())
    return record
