"""Pleiades JSON helpers for optional enrichment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PleiadesPlace:
    pleiades_id: str
    title: str
    lon: float | None
    lat: float | None
    names: tuple[str, ...]
    attested_names: tuple[str, ...]
    raw: dict[str, Any]


def load_pleiades_place(path: Path) -> PleiadesPlace | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    pid = str(raw.get("id") or path.stem)
    repr_point = raw.get("reprPoint")
    lon = lat = None
    if isinstance(repr_point, list) and len(repr_point) >= 2:
        try:
            lon = float(repr_point[0])
            lat = float(repr_point[1])
        except (TypeError, ValueError):
            lon = lat = None
    names: list[str] = []
    attested: list[str] = []
    for item in raw.get("names") or []:
        if not isinstance(item, dict):
            continue
        romanized = str(item.get("romanized") or "").strip()
        attested_name = str(item.get("attested") or "").strip()
        if romanized:
            names.append(romanized)
        if attested_name:
            attested.append(attested_name)
    # stable unique order
    def _uniq(values: list[str]) -> tuple[str, ...]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return tuple(out)

    return PleiadesPlace(
        pleiades_id=pid,
        title=str(raw.get("title") or pid),
        lon=lon,
        lat=lat,
        names=_uniq(names),
        attested_names=_uniq(attested),
        raw=raw,
    )


def load_pleiades_dir(directory: Path) -> dict[str, PleiadesPlace]:
    found: dict[str, PleiadesPlace] = {}
    if not directory.exists():
        return found
    for path in sorted(directory.glob("*.json")):
        if path.name == "openbible_to_pleiades.json":
            continue
        place = load_pleiades_place(path)
        if place is not None:
            found[place.pleiades_id] = place
    return found
