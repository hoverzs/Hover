from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "biblical_places"
RAW_OPENBIBLE_ANCIENT_PATH = DATA_DIR / "raw" / "openbible" / "ancient.jsonl"
PILOT_PATH = DATA_DIR / "pilot_places.json"
SOURCES_PATH = DATA_DIR / "sources.json"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PASSAGE_CATALOG_PATH = DATA_DIR / "passage_place_catalog.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
IMPORT_REPORT_PATH = DATA_DIR / "full_catalog_import_report.json"
HU_REVIEW_QUEUE_PATH = DATA_DIR / "hungarian_review_queue.json"
DUPLICATE_PLACE_MERGES_PATH = DATA_DIR / "duplicate_place_merges.json"

OPENBIBLE_SOURCE_ID = "openbible_geocoding_cc_by_4_0"
MANUAL_LOCKED_PLACE_IDS = {"corinth", "ephesus"}

REQUIRED_PLACE_KEYS = [
    "place_id",
    "name_hu",
    "name_en",
    "ancient_names",
    "original_names",
    "transliterations",
    "modern_name",
    "modern_country",
    "place_type",
    "identification_status",
    "confidence_note_hu",
    "latitude",
    "longitude",
    "region_hu",
    "ancient_region",
    "geometry_type",
    "coordinate_source_id",
    "card_summary_hu",
    "card_summary_en",
    "is_primary_demo_place",
    "geography_hu",
    "history_hu",
    "political_context_hu",
    "economic_context_hu",
    "social_context_hu",
    "religious_context_hu",
    "archaeology_hu",
    "biblical_significance_hu",
    "modern_context_hu",
    "exegetical_notes",
    "source_ids",
    "translation_status",
    "translation_method",
    "translation_model",
    "translated_at",
    "review_status",
    "reviewed_by",
    "reviewed_at",
    "openbible_id",
    "pleiades_id",
    "step_id",
    "wikidata_id",
    "legacy_place_ids",
    "merge_review_notes_hu",
    "rejected_aliases_hu",
]

PROTECTED_PILOT_FIELDS = {
    "name_hu",
    "name_en",
    "ancient_names",
    "original_names",
    "transliterations",
    "modern_name",
    "modern_country",
    "place_type",
    "identification_status",
    "confidence_note_hu",
    "latitude",
    "longitude",
    "region_hu",
    "ancient_region",
    "coordinate_source_id",
    "card_summary_hu",
    "is_primary_demo_place",
    "geography_hu",
    "history_hu",
    "political_context_hu",
    "economic_context_hu",
    "social_context_hu",
    "religious_context_hu",
    "archaeology_hu",
    "biblical_significance_hu",
    "modern_context_hu",
    "exegetical_notes",
    "translation_status",
    "translation_method",
    "translation_model",
    "translated_at",
    "review_status",
    "reviewed_by",
    "reviewed_at",
    "openbible_id",
    "pleiades_id",
    "step_id",
    "wikidata_id",
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    text = value.casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "place"


def parse_lonlat(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if "," not in text:
        return None, None
    lon_s, lat_s = text.split(",", 1)
    try:
        lon = float(lon_s.strip())
        lat = float(lat_s.strip())
    except ValueError:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lon, lat


def score_value(score: Any) -> int | None:
    if isinstance(score, int | float):
        return int(score)
    if isinstance(score, dict):
        values = [
            value
            for key in ("time_total", "vote_total", "vote_average")
            if isinstance((value := score.get(key)), int | float)
        ]
        if values:
            return int(max(values))
    return None


def identification_status(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 800:
        return "certain"
    if score >= 400:
        return "probable"
    if score >= 100:
        return "possible"
    return "disputed"


def first_best_identification(raw: dict[str, Any]) -> dict[str, Any] | None:
    identifications = raw.get("identifications")
    if not isinstance(identifications, list) or not identifications:
        return None
    return max(identifications, key=lambda item: score_value(item.get("score")) or -1)


def first_resolution(identification: dict[str, Any] | None) -> dict[str, Any] | None:
    if not identification:
        return None
    resolutions = identification.get("resolutions")
    if not isinstance(resolutions, list):
        return None
    for resolution in resolutions:
        if isinstance(resolution, dict) and parse_lonlat(resolution.get("lonlat")) != (None, None):
            return resolution
    return None


def linked_id(raw: dict[str, Any], predicate) -> str | None:
    linked = raw.get("linked_data")
    if not isinstance(linked, dict):
        return None
    for value in linked.values():
        if not isinstance(value, dict):
            continue
        found = predicate(value)
        if found:
            return found
    return None


def pleiades_id(raw: dict[str, Any]) -> str | None:
    def find(value: dict[str, Any]) -> str | None:
        for key in ("url", "data_url"):
            url = str(value.get(key) or "")
            if "pleiades.stoa.org/places/" in url:
                candidate = url.rstrip("/").split("/")[-1]
                if candidate.isdigit():
                    return candidate
        return None

    return linked_id(raw, find)


def wikidata_id(raw: dict[str, Any]) -> str | None:
    return linked_id(
        raw,
        lambda value: candidate
        if (candidate := str(value.get("id") or "")).startswith("Q")
        and candidate[1:].isdigit()
        else None,
    )


def clean_list(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def modern_name(raw: dict[str, Any], resolution: dict[str, Any] | None) -> str | None:
    modern_id = str((resolution or {}).get("modern_basis_id") or "").strip()
    associations = raw.get("modern_associations")
    if modern_id and isinstance(associations, dict):
        value = associations.get(modern_id)
        if isinstance(value, dict) and value.get("name"):
            return str(value["name"]).strip()
    identification = first_best_identification(raw)
    description = str((identification or {}).get("description") or "")
    match = re.search(r">([^<>]+)</modern>", description)
    return match.group(1).strip() if match else None


def build_summary(raw: dict[str, Any], modern: str | None, status: str) -> str | None:
    if status in {"unknown", "disputed"}:
        return None
    ancient = str(raw.get("friendly_id") or "").strip()
    types = clean_list(list(raw.get("types") or []))
    type_text = ", ".join(types[:2]) if types else "biblical place"
    if ancient and modern and ancient != modern:
        return f"{ancient} is an ancient {type_text}; OpenBible identifies it with {modern}."
    if ancient:
        return f"{ancient} is an ancient {type_text} in the OpenBible geocoding dataset."
    return None


def empty_place_record() -> dict[str, Any]:
    return {
        "place_id": "",
        "name_hu": None,
        "name_en": None,
        "ancient_names": [],
        "original_names": [],
        "transliterations": [],
        "modern_name": None,
        "modern_country": None,
        "place_type": None,
        "identification_status": "unknown",
        "confidence_note_hu": None,
        "latitude": None,
        "longitude": None,
        "region_hu": None,
        "ancient_region": None,
        "geometry_type": "point",
        "coordinate_source_id": OPENBIBLE_SOURCE_ID,
        "card_summary_hu": None,
        "card_summary_en": None,
        "is_primary_demo_place": False,
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
        "source_ids": [OPENBIBLE_SOURCE_ID],
        "translation_status": "not_translated",
        "translation_method": None,
        "translation_model": None,
        "translated_at": None,
        "review_status": "needs_review",
        "reviewed_by": None,
        "reviewed_at": None,
        "openbible_id": None,
        "pleiades_id": None,
        "step_id": None,
        "wikidata_id": None,
        "legacy_place_ids": [],
        "merge_review_notes_hu": None,
        "rejected_aliases_hu": [],
    }


def ensure_shape(record: dict[str, Any]) -> dict[str, Any]:
    shaped = empty_place_record()
    shaped.update(record)
    return {key: shaped.get(key) for key in REQUIRED_PLACE_KEYS}


def build_raw_place(raw: dict[str, Any], place_id: str) -> tuple[dict[str, Any] | None, str | None]:
    identification = first_best_identification(raw)
    resolution = first_resolution(identification)
    lon, lat = parse_lonlat((resolution or {}).get("lonlat"))
    if lat is None or lon is None:
        return None, "missing_or_invalid_coordinates"
    score = score_value((identification or {}).get("score"))
    status = identification_status(score)
    friendly = str(raw.get("friendly_id") or raw.get("id") or "").strip()
    modern = modern_name(raw, resolution)
    types = clean_list(list(raw.get("types") or []) + list((identification or {}).get("types") or []))
    record = empty_place_record()
    record.update(
        {
            "place_id": place_id,
            "name_hu": None,
            "name_en": friendly or place_id,
            "ancient_names": clean_list([friendly, *list((raw.get("translation_name_counts") or {}).keys())]),
            "original_names": [],
            "transliterations": [],
            "modern_name": modern,
            "modern_country": None,
            "place_type": ", ".join(types) if types else None,
            "identification_status": status,
            "confidence_note_hu": (
                f"OpenBible azonosítás (score={score}). "
                "Importált rekord; magyar név és részletes háttér szakmai ellenőrzésre vár."
                if score is not None
                else "OpenBible rekord; azonosítási pontszám nem áll rendelkezésre."
            ),
            "latitude": lat,
            "longitude": lon,
            "card_summary_hu": None,
            "card_summary_en": build_summary(raw, modern, status),
            "openbible_id": str(raw.get("id") or "").strip() or None,
            "pleiades_id": pleiades_id(raw),
            "wikidata_id": wikidata_id(raw),
        }
    )
    return ensure_shape(record), None


def non_empty(value: Any) -> bool:
    return value not in (None, "", [], {})


def merge_pilot(base: dict[str, Any], pilot: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    merged["place_id"] = pilot.get("place_id") or base.get("place_id")
    for key, value in pilot.items():
        if key == "source_ids":
            merged[key] = clean_list([*(base.get(key) or []), *(value or [])])
        elif key == "is_primary_demo_place":
            merged[key] = bool(value)
        elif key in PROTECTED_PILOT_FIELDS and non_empty(value):
            merged[key] = deepcopy(value)
        elif key not in merged or not non_empty(merged.get(key)):
            merged[key] = deepcopy(value)
    return ensure_shape(merged)


def remove_mixed_manual_demo_source(record: dict[str, Any]) -> dict[str, Any]:
    source_ids = record.get("source_ids")
    if not isinstance(source_ids, list):
        return record
    manual_source_id = "manual_demo_v1"
    real_sources = [source_id for source_id in source_ids if source_id != manual_source_id]
    if real_sources and len(real_sources) != len(source_ids):
        record = deepcopy(record)
        record["source_ids"] = real_sources
        if record.get("coordinate_source_id") == manual_source_id:
            record["coordinate_source_id"] = real_sources[0]
    return record


def apply_hungarian_review_overrides(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_queue = read_json(HU_REVIEW_QUEUE_PATH, [])
    if not isinstance(review_queue, list):
        return catalog
    review_by_id = {
        str(item.get("place_id") or ""): item
        for item in review_queue
        if isinstance(item, dict)
        and item.get("review_status") == "draft"
        and str(item.get("proposed_name_hu") or "").strip()
        and str(item.get("proposed_card_summary_hu") or "").strip()
    }
    if not review_by_id:
        return catalog
    merged: list[dict[str, Any]] = []
    for record in catalog:
        place_id = str(record.get("place_id") or "")
        review_item = review_by_id.get(place_id)
        if review_item is None:
            merged.append(record)
            continue
        updated = deepcopy(record)
        updated["name_hu"] = str(review_item["proposed_name_hu"]).strip()
        updated["card_summary_hu"] = str(review_item["proposed_card_summary_hu"]).strip()
        updated["review_status"] = "draft"
        merged.append(updated)
    return merged


def stable_unique_json(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


IDENTIFICATION_STATUS_RANK = {
    "unknown": 0,
    "disputed": 1,
    "possible": 2,
    "probable": 3,
    "certain": 4,
}


def least_certain_status(values: list[Any]) -> str:
    statuses = [str(value or "unknown") for value in values]
    return min(statuses, key=lambda item: IDENTIFICATION_STATUS_RANK.get(item, 0)) if statuses else "unknown"


def alias_filter(group_id: str, value: Any) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return False
    if group_id == "dup_egypt__ham_2" and text in {"ham", "hám", "ham 2"}:
        return False
    if group_id == "dup_abdon__ebron" and text == "hebron":
        return False
    if group_id == "dup_aija__ayyah" and text == "gaza":
        return False
    if group_id == "dup_judea_1__judea_2" and text in {"galilee", "galilean", "galileans"}:
        return False
    return True


def apply_duplicate_place_merges_to_catalog(
    catalog: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_id = {str(record.get("place_id") or ""): deepcopy(record) for record in catalog}
    redirects: dict[str, str] = {}
    for decision in decisions:
        if decision.get("final_action") != "merge":
            continue
        group_id = str(decision.get("group_id") or "")
        canonical_id = str(decision.get("canonical_place_id") or decision.get("proposed_canonical_place_id") or "")
        removed_ids = [
            str(place_id)
            for place_id in decision.get("removed_place_ids", [])
            if str(place_id) and str(place_id) != canonical_id
        ]
        if not canonical_id or canonical_id not in by_id:
            continue
        candidates = [by_id[canonical_id], *[by_id[place_id] for place_id in removed_ids if place_id in by_id]]
        if len(candidates) < 2:
            for removed_id in removed_ids:
                redirects[removed_id] = canonical_id
            continue

        canonical = by_id[canonical_id]
        canonical["name_hu"] = str(decision.get("proposed_merged_name_hu") or canonical.get("name_hu") or "").strip()
        canonical["card_summary_hu"] = str(
            decision.get("proposed_merged_summary_hu") or canonical.get("card_summary_hu") or ""
        ).strip()
        canonical["review_status"] = "reviewed"
        canonical["identification_status"] = least_certain_status(
            [record.get("identification_status") for record in candidates]
        )
        for key in ("ancient_names", "original_names", "transliterations", "source_ids", "exegetical_notes"):
            values: list[Any] = []
            for record in candidates:
                record_values = record.get(key) or []
                if key in {"ancient_names", "original_names", "transliterations"}:
                    values.extend(value for value in record_values if alias_filter(group_id, value))
                else:
                    values.extend(record_values)
            canonical[key] = stable_unique_json(values)

        legacy_ids: list[str] = []
        rejected_aliases: list[str] = []
        for record in candidates:
            place_id = str(record.get("place_id") or "")
            if place_id != canonical_id:
                legacy_ids.append(place_id)
            legacy_ids.extend(str(value) for value in record.get("legacy_place_ids") or [] if str(value))
        if group_id == "dup_egypt__ham_2":
            rejected_aliases.extend(["Ham", "Hám"])
        if group_id == "dup_abdon__ebron":
            rejected_aliases.append("Hebron")
        if group_id == "dup_aija__ayyah":
            rejected_aliases.append("Gaza")
        if group_id == "dup_judea_1__judea_2":
            rejected_aliases.append("Galilee")
        canonical["legacy_place_ids"] = stable_unique_json([*(canonical.get("legacy_place_ids") or []), *legacy_ids])
        canonical["rejected_aliases_hu"] = stable_unique_json(
            [*(canonical.get("rejected_aliases_hu") or []), *rejected_aliases]
        )
        note = (
            f"Duplikációs review alapján összevont rekord ({group_id}); "
            f"korábbi place_id-k: {', '.join(removed_ids)}."
        )
        existing_note = str(canonical.get("merge_review_notes_hu") or "").strip()
        canonical["merge_review_notes_hu"] = existing_note if note in existing_note else (existing_note + "\n" + note).strip()
        by_id[canonical_id] = ensure_shape(canonical)
        for removed_id in removed_ids:
            redirects[removed_id] = canonical_id
            by_id.pop(removed_id, None)
    return sorted(by_id.values(), key=lambda item: str(item.get("place_id") or "")), redirects


def apply_duplicate_place_merges_to_links(
    links: list[dict[str, Any]],
    redirects: dict[str, str],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        updated = deepcopy(link)
        place_id = str(updated.get("place_id") or "")
        updated["place_id"] = redirects.get(place_id, place_id)
        key = (str(updated.get("reference") or ""), str(updated.get("place_id") or ""))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        merged.append(updated)
    return sorted(merged, key=passage_link_sort_key)


def load_openbible_raw() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with RAW_OPENBIBLE_ANCIENT_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            records.append(json.loads(line))
    return records


def build_place_id_maps(raw_records: list[dict[str, Any]], pilot_places: list[dict[str, Any]]) -> dict[str, str]:
    pilot_by_openbible = {
        str(place.get("openbible_id")): str(place.get("place_id"))
        for place in pilot_places
        if place.get("openbible_id") and place.get("place_id")
    }
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for raw in raw_records:
        openbible_id = str(raw.get("id") or "")
        base = pilot_by_openbible.get(openbible_id) or slugify(str(raw.get("url_slug") or raw.get("friendly_id") or openbible_id))
        place_id = base
        if place_id in used:
            place_id = f"{base}_{openbible_id}"
        used.add(place_id)
        mapping[openbible_id] = place_id
    return mapping


def reference_from_verse(verse: dict[str, Any]) -> str | None:
    usx = str(verse.get("usx") or "").strip()
    match = re.fullmatch(r"([1-3]?[A-Z]{2,3})\s+(\d+):(\d+)", usx)
    if not match:
        return None
    book, chapter, verse_no = match.groups()
    return f"{book} {chapter},{verse_no}"


def build_passage_catalog(raw_records: list[dict[str, Any]], place_id_by_openbible: dict[str, str], importable_ids: set[str]) -> tuple[list[dict[str, Any]], Counter[str]]:
    skipped = Counter()
    links_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in raw_records:
        openbible_id = str(raw.get("id") or "")
        if openbible_id not in importable_ids:
            continue
        place_id = place_id_by_openbible[openbible_id]
        verses = raw.get("verses")
        if not isinstance(verses, list) or not verses:
            skipped["missing_verses"] += 1
            continue
        for verse in verses:
            if not isinstance(verse, dict):
                skipped["invalid_verse_object"] += 1
                continue
            reference = reference_from_verse(verse)
            if not reference:
                skipped["unparseable_usx"] += 1
                continue
            key = (reference, place_id)
            links_by_key[key] = {
                "reference": reference,
                "place_id": place_id,
                "reason_hu": "OpenBible vers-hivatkozásból generált helykapcsolat.",
                "source_note": "OpenBible Bible Geocoding Data verses",
                "openbible_id": openbible_id,
                "osis": verse.get("osis"),
            }
    return sorted(links_by_key.values(), key=lambda item: (item["reference"], item["place_id"])), skipped


def passage_link_sort_key(link: dict[str, Any]) -> tuple[int, str, str]:
    source_note = str(link.get("source_note") or "")
    manual_priority = 0 if source_note == "pilot passage index" else 1
    return manual_priority, str(link.get("reference") or ""), str(link.get("place_id") or "")


def source_ids(sources: list[dict[str, Any]]) -> set[str]:
    return {str(source.get("source_id") or "") for source in sources}


def ensure_openbible_source(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(source.get("source_id") or ""): source for source in sources}
    by_id[OPENBIBLE_SOURCE_ID] = {
        "source_id": OPENBIBLE_SOURCE_ID,
        "provider": "OpenBible.info Bible Geocoding Data",
        "title": "Bible Geocoding Data (ancient/modern place catalog)",
        "original_language": "en",
        "source_url": "https://github.com/openbibleinfo/Bible-Geocoding-Data",
        "license": "CC-BY-4.0",
        "attribution": "Stephen Smith / OpenBible.info Bible Geocoding Data",
        "retrieved_at": "2026-07-29",
        "source_type": "open_geocoding_dataset",
        "reliability_tier": "aggregated_open_scholarship",
        "notes_hu": "Helynevek, koordináták és bibliai vershivatkozások forrása. A Textus nem másol át hosszú forrásszöveget.",
    }
    return sorted(by_id.values(), key=lambda item: str(item.get("source_id") or ""))


def build_catalog() -> dict[str, Any]:
    raw_records = load_openbible_raw()
    pilot_places = read_json(PILOT_PATH, [])
    place_id_by_openbible = build_place_id_maps(raw_records, pilot_places)
    catalog_by_openbible: dict[str, dict[str, Any]] = {}
    skipped = Counter()
    for raw in raw_records:
        openbible_id = str(raw.get("id") or "")
        record, reason = build_raw_place(raw, place_id_by_openbible[openbible_id])
        if record is None:
            skipped[reason or "unknown"] += 1
            continue
        catalog_by_openbible[openbible_id] = record

    by_place_id = {record["place_id"]: record for record in catalog_by_openbible.values()}
    manual_overrides = 0
    for pilot in pilot_places:
        pilot_id = str(pilot.get("place_id") or "")
        openbible_id = str(pilot.get("openbible_id") or "")
        base = catalog_by_openbible.get(openbible_id) if openbible_id else None
        if base is None:
            base = by_place_id.get(pilot_id) or empty_place_record()
            base["place_id"] = pilot_id
        old_id = str(base.get("place_id") or "")
        merged = merge_pilot(base, pilot)
        if old_id and old_id != merged["place_id"]:
            by_place_id.pop(old_id, None)
        by_place_id[merged["place_id"]] = remove_mixed_manual_demo_source(merged)
        manual_overrides += 1

    catalog = sorted(by_place_id.values(), key=lambda item: str(item.get("place_id") or ""))
    catalog = apply_hungarian_review_overrides(catalog)
    duplicate_merge_decisions = read_json(DUPLICATE_PLACE_MERGES_PATH, [])
    catalog, duplicate_redirects = apply_duplicate_place_merges_to_catalog(catalog, duplicate_merge_decisions)
    importable_openbible_ids = set(catalog_by_openbible)
    passage_catalog, passage_skipped = build_passage_catalog(raw_records, place_id_by_openbible, importable_openbible_ids)
    manual_links = read_json(PASSAGE_LINKS_PATH, [])
    merged_links: list[dict[str, Any]] = []
    seen_links: set[tuple[str, str]] = set()
    for link in [*manual_links, *passage_catalog]:
        key = (str(link.get("reference") or ""), str(link.get("place_id") or ""))
        if not key[0] or not key[1] or key in seen_links:
            continue
        seen_links.add(key)
        merged_links.append(link)
    merged_links = apply_duplicate_place_merges_to_links(merged_links, duplicate_redirects)

    sources = ensure_openbible_source(read_json(SOURCES_PATH, []))
    return {
        "raw_place_count": len(raw_records),
        "imported_place_count": len(catalog_by_openbible),
        "skipped_place_count": sum(skipped.values()),
        "skipped_places_by_reason": dict(sorted(skipped.items())),
        "manual_override_count": manual_overrides,
        "duplicate_merge_count": len(
            [decision for decision in duplicate_merge_decisions if decision.get("final_action") == "merge"]
        ),
        "duplicate_redirect_count": len(duplicate_redirects),
        "merged_catalog_count": len(catalog),
        "passage_catalog_count": len(passage_catalog),
        "merged_passage_link_count": len(merged_links),
        "passage_skipped_by_reason": dict(sorted(passage_skipped.items())),
        "catalog": catalog,
        "passage_catalog": passage_catalog,
        "merged_passage_links": sorted(merged_links, key=passage_link_sort_key),
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the full biblical places catalog from local OpenBible raw data.")
    parser.add_argument("--check", action="store_true", help="Build and compare without writing.")
    args = parser.parse_args()
    result = build_catalog()
    if result["imported_place_count"] <= 100:
        print("ERROR: OpenBible raw data did not produce more than 100 importable places.")
        return 1
    outputs = {
        CATALOG_PATH: result["catalog"],
        PASSAGE_CATALOG_PATH: result["passage_catalog"],
        PASSAGE_LINKS_PATH: result["merged_passage_links"],
        SOURCES_PATH: result["sources"],
        IMPORT_REPORT_PATH: {
            key: value
            for key, value in result.items()
            if key not in {"catalog", "passage_catalog", "merged_passage_links", "sources"}
        },
    }
    if args.check:
        changed = [
            str(path)
            for path, payload in outputs.items()
            if path.exists()
            and path.read_text(encoding="utf-8")
            != json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ]
        missing = [str(path) for path in outputs if not path.exists()]
        if changed or missing:
            print(json.dumps({"changed": changed, "missing": missing}, ensure_ascii=False, indent=2))
            return 2
        print("Full catalog import idempotency check passed.")
        return 0
    for path, payload in outputs.items():
        write_json(path, payload)
    print(
        json.dumps(
            {
                "raw_place_count": result["raw_place_count"],
                "imported_place_count": result["imported_place_count"],
                "skipped_place_count": result["skipped_place_count"],
                "manual_override_count": result["manual_override_count"],
                "merged_catalog_count": result["merged_catalog_count"],
                "passage_catalog_count": result["passage_catalog_count"],
                "merged_passage_link_count": result["merged_passage_link_count"],
                "skipped_places_by_reason": result["skipped_places_by_reason"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
