"""OpenBible Bible Geocoding Data helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class OpenBibleAncientPlace:
    openbible_id: str
    friendly_id: str
    types: tuple[str, ...]
    lon: float | None
    lat: float | None
    modern_id: str | None
    modern_name: str | None
    pleiades_id: str | None
    wikidata_id: str | None
    identification_score: int | None
    raw: dict[str, Any]


def _parse_lonlat(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if not text or "," not in text:
        return None, None
    left, right = text.split(",", 1)
    try:
        return float(left.strip()), float(right.strip())
    except ValueError:
        return None, None


def _score_value(score: Any) -> int:
    if isinstance(score, int | float):
        return int(score)
    if isinstance(score, dict):
        for key in ("vote_total", "time_total", "vote_average"):
            if isinstance(score.get(key), int | float):
                return int(score[key])
    return 0


def _best_identification(obj: dict[str, Any]) -> dict[str, Any] | None:
    ids = obj.get("identifications")
    if not isinstance(ids, list) or not ids:
        return None
    return max(ids, key=_score_value)


def _extract_pleiades_id(linked_data: dict[str, Any]) -> str | None:
    for value in linked_data.values():
        if not isinstance(value, dict):
            continue
        for key in ("url", "data_url"):
            url = str(value.get(key) or "")
            if "pleiades.stoa.org/places/" not in url:
                continue
            parts = [part for part in url.rstrip("/").split("/") if part]
            for part in reversed(parts):
                if part.isdigit():
                    return part
    return None


def _extract_wikidata_id(linked_data: dict[str, Any]) -> str | None:
    for value in linked_data.values():
        if not isinstance(value, dict):
            continue
        wid = str(value.get("id") or "").strip()
        if wid.startswith("Q") and wid[1:].isdigit():
            return wid
    return None


def load_openbible_ancient(
    path: Path,
    ids: Iterable[str] | None = None,
) -> dict[str, OpenBibleAncientPlace]:
    wanted = set(ids or ())
    found: dict[str, OpenBibleAncientPlace] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            obj = json.loads(line)
            oid = str(obj.get("id") or "").strip()
            if wanted and oid not in wanted:
                continue
            best = _best_identification(obj)
            lon = lat = None
            modern_id = None
            modern_name = None
            score = None
            if best:
                score = _score_value(best.get("score"))
                modern_id = str(best.get("id") or "").strip() or None
                resolutions = best.get("resolutions") or []
                if resolutions:
                    lon, lat = _parse_lonlat(resolutions[0].get("lonlat"))
                    modern_id = (
                        str(resolutions[0].get("modern_basis_id") or modern_id or "").strip()
                        or None
                    )
            associations = obj.get("modern_associations") or {}
            if isinstance(associations, dict) and modern_id and modern_id in associations:
                modern_name = str(associations[modern_id].get("name") or "").strip() or None
            linked = obj.get("linked_data") or {}
            found[oid] = OpenBibleAncientPlace(
                openbible_id=oid,
                friendly_id=str(obj.get("friendly_id") or oid),
                types=tuple(obj.get("types") or ()),
                lon=lon,
                lat=lat,
                modern_id=modern_id,
                modern_name=modern_name,
                pleiades_id=_extract_pleiades_id(linked if isinstance(linked, dict) else {}),
                wikidata_id=_extract_wikidata_id(linked if isinstance(linked, dict) else {}),
                identification_score=score,
                raw=obj,
            )
            if wanted and len(found) == len(wanted):
                break
    return found


def identification_status_from_score(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 800:
        return "certain"
    if score >= 400:
        return "probable"
    if score >= 100:
        return "possible"
    return "disputed"
