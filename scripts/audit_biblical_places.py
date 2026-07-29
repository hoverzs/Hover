from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "biblical_places"
PLACES_PATH = DATA_DIR / "pilot_places.json"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
SOURCES_PATH = DATA_DIR / "sources.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
PASSAGE_CATALOG_PATH = DATA_DIR / "passage_place_catalog.json"
MANUAL_LOCKS_PATH = DATA_DIR / "manual_locks.json"
IMPORT_REPORT_PATH = DATA_DIR / "full_catalog_import_report.json"
REPORT_JSON_PATH = DATA_DIR / "audit_report.json"
REPORT_MD_PATH = ROOT / "docs" / "biblical_places_audit.md"

MANUAL_SOURCE_ID = "manual_demo_v1"
MANUAL_LOCKED_PLACE_IDS = {"corinth", "ephesus"}
TECHNICAL_SUMMARY_PATTERNS = (
    "demonstrációs adat",
    "prototype",
    "prototípus",
    "openbible azonosítás",
)
MOJIBAKE_PATTERNS = ("Ã", "Å", "Ä", "Õ", "õ", "�")

COUNTRY_BOUNDS = {
    "Görögország": (34.0, 42.5, 19.0, 30.5),
    "Törökország": (35.0, 42.5, 25.0, 45.0),
    "Izrael": (29.0, 34.0, 34.0, 36.0),
    "Olaszország": (35.0, 48.0, 6.0, 19.0),
    "Szíria": (32.0, 38.0, 35.0, 43.0),
}

EXPECTED_LOCK_FINGERPRINT_FIELDS = (
    "card_summary_hu",
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
)


@dataclass(frozen=True)
class Finding:
    category: str
    severity: str
    object_type: str
    object_id: str
    message: str
    auto_fixable: bool = False


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def compact_json_hash(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str | None:
    text = value.strip()
    return text or None


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_json_value(item) for key, item in value.items()}
    return value


def dedupe_preserve_order(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def sort_key_for_record(record: dict[str, Any], primary_key: str) -> str:
    return str(record.get(primary_key) or "").casefold()


def normalize_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_json_value(place) for place in places]
    for place in normalized:
        if isinstance(place, dict):
            for list_key in ("source_ids", "ancient_names", "original_names", "transliterations"):
                if isinstance(place.get(list_key), list):
                    place[list_key] = dedupe_preserve_order(
                        [item for item in place[list_key] if item is not None]
                    )
            notes = place.get("exegetical_notes")
            if isinstance(notes, list):
                for note in notes:
                    if isinstance(note, dict) and isinstance(note.get("source_ids"), list):
                        note["source_ids"] = dedupe_preserve_order(
                            [item for item in note["source_ids"] if item is not None]
                        )
    return sorted(
        [place for place in normalized if isinstance(place, dict)],
        key=lambda place: sort_key_for_record(place, "place_id"),
    )


def normalize_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_json_value(source) for source in sources]
    by_id: dict[str, dict[str, Any]] = {}
    for source in normalized:
        if isinstance(source, dict):
            source_id = str(source.get("source_id") or "")
            if source_id and source_id not in by_id:
                by_id[source_id] = source
    return sorted(by_id.values(), key=lambda source: sort_key_for_record(source, "source_id"))


def normalize_passage_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_json_value(link) for link in links]
    result = [link for link in normalized if isinstance(link, dict)]
    def sort_key(link: dict[str, Any]) -> tuple[int, str, str]:
        source_note = str(link.get("source_note") or "")
        manual_priority = 0 if source_note == "pilot passage index" else 1
        return manual_priority, str(link.get("reference") or ""), str(link.get("place_id") or "")

    return sorted(
        dedupe_preserve_order(result),
        key=sort_key,
    )


def normalized_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def sentence_count(value: str | None) -> int:
    text = value or ""
    return len([part for part in re.split(r"[.!?]+", text) if part.strip()])


def has_hungarian_signal(value: str | None) -> bool:
    text = value or ""
    return any(ch in text for ch in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ")


def contains_suspicious_encoding(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern in value for pattern in MOJIBAKE_PATTERNS)
    if isinstance(value, list):
        return any(contains_suspicious_encoding(item) for item in value)
    if isinstance(value, dict):
        return any(contains_suspicious_encoding(item) for item in value.values())
    return False


def rough_distance_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    try:
        return abs(float(left["latitude"]) - float(right["latitude"])) + abs(
            float(left["longitude"]) - float(right["longitude"])
        )
    except (KeyError, TypeError, ValueError):
        return 999.0


def add_finding(
    findings: list[Finding],
    category: str,
    severity: str,
    object_type: str,
    object_id: str,
    message: str,
    *,
    auto_fixable: bool = False,
) -> None:
    findings.append(
        Finding(
            category=category,
            severity=severity,
            object_type=object_type,
            object_id=object_id,
            message=message,
            auto_fixable=auto_fixable,
        )
    )


def audit_catalog(places: list[dict[str, Any]], sources: list[dict[str, Any]], links: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    place_ids = [str(place.get("place_id") or "") for place in places]
    source_ids = [str(source.get("source_id") or "") for source in sources]
    place_id_counts = Counter(place_ids)
    source_id_counts = Counter(source_ids)
    valid_place_ids = {place_id for place_id in place_ids if place_id}
    valid_source_ids = {source_id for source_id in source_ids if source_id}

    for place_id, count in place_id_counts.items():
        if count > 1:
            add_finding(findings, "duplicate_place_id", "error", "place", place_id, f"Duplicate place_id appears {count} times.")
    for source_id, count in source_id_counts.items():
        if count > 1:
            add_finding(findings, "duplicate_source_id", "error", "source", source_id, f"Duplicate source_id appears {count} times.", auto_fixable=True)

    names: dict[str, list[str]] = defaultdict(list)
    for place in places:
        place_id = str(place.get("place_id") or "")
        name_key = normalized_name(str(place.get("name_hu") or ""))
        if name_key:
            names[name_key].append(place_id)
    for name_key, ids in names.items():
        if len(set(ids)) > 1:
            add_finding(findings, "same_hungarian_name", "review", "place", ", ".join(sorted(set(ids))), f"Same normalized Hungarian name is used by multiple records: {name_key}.")

    for index, left in enumerate(places):
        for right in places[index + 1 :]:
            shared_names = {
                normalized_name(item)
                for item in [
                    left.get("name_hu"),
                    left.get("name_en"),
                    *(left.get("ancient_names") or []),
                    *(left.get("transliterations") or []),
                ]
                if normalized_name(str(item or ""))
            } & {
                normalized_name(item)
                for item in [
                    right.get("name_hu"),
                    right.get("name_en"),
                    *(right.get("ancient_names") or []),
                    *(right.get("transliterations") or []),
                ]
                if normalized_name(str(item or ""))
            }
            if shared_names and rough_distance_score(left, right) < 0.25:
                add_finding(
                    findings,
                    "probable_duplicate_place",
                    "review",
                    "place_pair",
                    f"{left.get('place_id')} / {right.get('place_id')}",
                    "Records share a name variant and have very close coordinates.",
                )

    for place in places:
        place_id = str(place.get("place_id") or "")
        lat = place.get("latitude")
        lon = place.get("longitude")
        try:
            lat_value = float(lat)
            lon_value = float(lon)
            if not (-90 <= lat_value <= 90 and -180 <= lon_value <= 180):
                add_finding(findings, "invalid_coordinates", "error", "place", place_id, "Coordinates are outside valid latitude/longitude range.")
            if lat_value == 0 and lon_value == 0:
                add_finding(findings, "suspicious_coordinates", "review", "place", place_id, "Coordinates are exactly 0,0.")
            country = str(place.get("modern_country") or "")
            if country in COUNTRY_BOUNDS:
                min_lat, max_lat, min_lon, max_lon = COUNTRY_BOUNDS[country]
                if not (min_lat <= lat_value <= max_lat and min_lon <= lon_value <= max_lon):
                    add_finding(findings, "coordinates_outside_country_bounds", "review", "place", place_id, f"Coordinates look outside rough bounds for {country}.")
        except (TypeError, ValueError):
            add_finding(findings, "invalid_coordinates", "error", "place", place_id, "Coordinates are missing or non-numeric.")

        coordinate_source_id = str(place.get("coordinate_source_id") or "")
        if coordinate_source_id not in valid_source_ids:
            add_finding(findings, "missing_coordinate_source_id", "error", "place", place_id, f"coordinate_source_id does not resolve: {coordinate_source_id}")
        for source_id in place.get("source_ids") or []:
            if source_id not in valid_source_ids:
                add_finding(findings, "missing_source_id", "error", "place", place_id, f"source_id does not resolve: {source_id}")
        for note in place.get("exegetical_notes") or []:
            for source_id in note.get("source_ids") or []:
                if source_id not in valid_source_ids:
                    add_finding(findings, "missing_note_source_id", "error", "place", place_id, f"exegetical note source_id does not resolve: {source_id}")

        if place.get("openbible_id") and not re.fullmatch(r"a[0-9a-f]{6}", str(place["openbible_id"])):
            add_finding(findings, "invalid_external_id", "review", "place", place_id, f"Suspicious openbible_id: {place['openbible_id']}")
        if place.get("pleiades_id") and not re.fullmatch(r"\d+", str(place["pleiades_id"])):
            add_finding(findings, "invalid_external_id", "review", "place", place_id, f"Suspicious pleiades_id: {place['pleiades_id']}")
        if place.get("wikidata_id") and not re.fullmatch(r"Q\d+", str(place["wikidata_id"])):
            add_finding(findings, "invalid_external_id", "review", "place", place_id, f"Suspicious wikidata_id: {place['wikidata_id']}")

        name_hu = str(place.get("name_hu") or "")
        if not name_hu:
            add_finding(findings, "missing_hungarian_name", "review", "place", place_id, "name_hu is missing.")
        elif not has_hungarian_signal(name_hu) and name_hu == str(place.get("name_en") or ""):
            add_finding(findings, "hungarian_name_review", "review", "place", place_id, "name_hu is identical to name_en and has no Hungarian diacritic signal.")

        if contains_suspicious_encoding(place):
            add_finding(findings, "suspicious_encoding", "review", "place", place_id, "Record contains suspicious mojibake or replacement characters.")

        summary = str(place.get("card_summary_hu") or "")
        if not summary:
            add_finding(findings, "empty_card_summary_hu", "review", "place", place_id, "card_summary_hu is empty.")
        else:
            if sentence_count(summary) > 2 or len(summary) > 360:
                add_finding(findings, "long_card_summary_hu", "review", "place", place_id, "card_summary_hu is longer than the 1-2 sentence guideline.")
            if any(pattern in summary.casefold() for pattern in TECHNICAL_SUMMARY_PATTERNS):
                add_finding(findings, "technical_or_demo_summary", "review", "place", place_id, "card_summary_hu contains technical/prototype wording.")
            if name_hu and summary.casefold().startswith(name_hu.casefold()):
                add_finding(findings, "summary_repeats_name", "review", "place", place_id, "card_summary_hu starts by repeating the place name.")

        if place.get("identification_status") == "certain" and place.get("review_status") in {"prototype", "draft"}:
            add_finding(findings, "certain_status_without_review", "review", "place", place_id, "Place is marked certain while still prototype/draft.")
        if place.get("identification_status") == "certain" and "vitat" in str(place.get("confidence_note_hu") or "").casefold():
            add_finding(findings, "disputed_place_marked_certain", "review", "place", place_id, "Confidence note suggests dispute while status is certain.")

        source_list = tuple(place.get("source_ids") or ())
        if MANUAL_SOURCE_ID in source_list and source_list != (MANUAL_SOURCE_ID,):
            add_finding(findings, "mixed_manual_demo_source", "review", "place", place_id, "manual_demo_v1 is mixed with real/imported sources.")

    link_counts_by_reference = Counter(str(link.get("reference") or "") for link in links)
    reported_large_references: set[str] = set()
    for link in links:
        reference = str(link.get("reference") or "")
        place_id = str(link.get("place_id") or "")
        if place_id not in valid_place_ids:
            add_finding(findings, "passage_link_unknown_place", "error", "passage_link", reference, f"Passage link references unknown place_id: {place_id}")
        if not re.fullmatch(r"[1-3]?\s?[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]+\.?\s+\d+,\d+(?:[-–]\d+)?", reference):
            add_finding(findings, "passage_reference_parse_review", "review", "passage_link", reference, "Reference should be checked by parser/tests.")
        if link_counts_by_reference[reference] > 4 and reference not in reported_large_references:
            reported_large_references.add(reference)
            add_finding(findings, "large_place_list_for_passage", "review", "passage_link", reference, "Reference has more than four linked places.")

    locked_ids = set(read_json(MANUAL_LOCKS_PATH).get("locked_place_ids", [])) if MANUAL_LOCKS_PATH.exists() else set()
    for required in MANUAL_LOCKED_PLACE_IDS:
        if required not in locked_ids:
            add_finding(findings, "manual_lock_missing", "error", "manual_lock", required, "Required manual lock is missing.")
        elif required not in valid_place_ids:
            add_finding(findings, "manual_lock_unknown_place", "error", "manual_lock", required, "Manual lock references a missing place.")

    return findings


def summarize_findings(findings: list[Finding]) -> dict[str, Any]:
    by_category = Counter(finding.category for finding in findings)
    by_severity = Counter(finding.severity for finding in findings)
    return {
        "by_category": dict(sorted(by_category.items())),
        "by_severity": dict(sorted(by_severity.items())),
    }


def report_data(
    places: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    links: list[dict[str, Any]],
    findings: list[Finding],
    auto_fixes: list[str],
    before_hash: str,
    after_hash: str,
) -> dict[str, Any]:
    review_findings = [finding for finding in findings if finding.severity == "review"]
    hungarian_name_review = [
        asdict(finding)
        for finding in findings
        if finding.category in {"hungarian_name_review", "missing_hungarian_name", "suspicious_encoding"}
    ]
    disputed_or_multiple = [
        asdict(finding)
        for finding in findings
        if finding.category
        in {
            "same_hungarian_name",
            "probable_duplicate_place",
            "disputed_place_marked_certain",
            "certain_status_without_review",
        }
    ]
    missing_hu_count = sum(1 for place in places if not place.get("name_hu"))
    fallback_description_count = 0
    for place in places:
        if place.get("card_summary_hu"):
            continue
        if place.get("modern_name"):
            fallback_description_count += 1
    uncertain_duplicates = sum(1 for finding in findings if finding.category == "probable_duplicate_place")
    invalid_external_ids = sum(1 for finding in findings if finding.category == "invalid_external_id")
    mixed_manual = sum(1 for finding in findings if finding.category == "mixed_manual_demo_source")
    large_lists = sum(1 for finding in findings if finding.category == "large_place_list_for_passage")
    return {
        "generated_at": "2026-07-29",
        "catalog_record_count": len(places),
        "source_record_count": len(sources),
        "passage_place_link_count": len(links),
        "hash_before_fix": before_hash,
        "hash_after_fix": after_hash,
        "idempotent_after_fix": before_hash == after_hash or not auto_fixes,
        "summary": summarize_findings(findings),
        "auto_fixed_items": auto_fixes,
        "review_required_count": len(review_findings),
        "large_place_list_for_passage_count": large_lists,
        "definite_duplicate_merge_count": 0,
        "uncertain_duplicate_count": uncertain_duplicates,
        "invalid_external_id_count": invalid_external_ids,
        "invalid_external_ids_fixed": invalid_external_ids == 0,
        "mixed_manual_demo_source_count": mixed_manual,
        "mixed_manual_demo_source_resolved": mixed_manual == 0,
        "ui_fallback_name_count": missing_hu_count,
        "safe_fallback_description_count": fallback_description_count,
        "top_findings": [asdict(finding) for finding in findings[:30]],
        "hungarian_name_review": hungarian_name_review,
        "disputed_or_multiple_identification_review": disputed_or_multiple,
        "findings": [asdict(finding) for finding in findings],
    }


def markdown_report(report: dict[str, Any]) -> str:
    category_lines = [
        f"- `{category}`: {count}"
        for category, count in report["summary"]["by_category"].items()
    ] or ["- Nincs találat."]
    fixed_lines = [f"- {item}" for item in report["auto_fixed_items"]] or ["- Nem volt automatikusan javítható eltérés."]
    top_lines = [
        f"- [{finding['severity']}] `{finding['category']}` `{finding['object_id']}`: {finding['message']}"
        for finding in report["top_findings"]
    ] or ["- Nincs kiemelt probléma."]
    name_lines = [
        f"- `{finding['object_id']}`: {finding['message']}"
        for finding in report["hungarian_name_review"]
    ] or ["- Nincs magyar névellenőrzési találat."]
    disputed_lines = [
        f"- `{finding['object_id']}`: {finding['message']}"
        for finding in report["disputed_or_multiple_identification_review"]
    ] or ["- Nincs vitatott vagy többes helyazonosítási találat."]
    return "\n".join(
        [
            "# Bibliai helyszínkatalógus audit",
            "",
            f"- Auditált katalógus: `{report.get('audited_catalog_path', 'data/biblical_places/pilot_places.json')}`",
            f"- OpenBible nyers helyrekordok száma: {report.get('openbible_raw_place_count')}",
            f"- Sikeresen importált helyek száma: {report.get('successfully_imported_place_count')}",
            f"- Kihagyott helyek száma: {report.get('skipped_place_count')}",
            f"- Kihagyási okok: `{report.get('skipped_places_by_reason', {})}`",
            f"- Kézi override-ok száma: {report.get('manual_override_count')}",
            f"- Merged katalógus mérete: {report.get('merged_catalog_count', report['catalog_record_count'])}",
            f"- Katalógus rekordok száma: {report['catalog_record_count']}",
            f"- Forrásrekordok száma: {report['source_record_count']}",
            f"- Passage-place kapcsolatok száma: {report['passage_place_link_count']}",
            f"- Szakmai ellenőrzést igénylő tételek: {report['review_required_count']}",
            f"- Large passage-list találatok: {report.get('large_place_list_for_passage_count')}",
            f"- Biztosan összevont duplikátumok: {report.get('definite_duplicate_merge_count')}",
            f"- Bizonytalan duplikátumok: {report.get('uncertain_duplicate_count')}",
            f"- Invalid external ID találatok: {report.get('invalid_external_id_count')}",
            f"- Mixed manual demo source találatok: {report.get('mixed_manual_demo_source_count')}",
            f"- UI fallback nevet igénylő rekordok: {report.get('ui_fallback_name_count')}",
            f"- Biztonságos rövid fallback leírás előállítható: {report.get('safe_fallback_description_count')}",
            f"- Idempotencia státusz: {'sikeres' if report['idempotent_after_fix'] else 'ellenőrzendő'}",
            "",
            "## Hibakategóriák",
            *category_lines,
            "",
            "## Automatikusan javított tételek",
            *fixed_lines,
            "",
            "## Legfontosabb problémák",
            *top_lines,
            "",
            "## Magyar névellenőrzésre vár",
            *name_lines,
            "",
            "## Vitatott vagy többes helyazonosítás",
            *disputed_lines,
            "",
            "## Megjegyzés",
            "Az audit nem végez történeti, régészeti vagy exegetikai tartalmi döntést. A bizonytalan találatok szakmai ellenőrzésre maradnak.",
            "",
        ]
    )


def run(fix: bool) -> dict[str, Any]:
    target_places_path = CATALOG_PATH if CATALOG_PATH.exists() else PLACES_PATH
    original_places = read_json(target_places_path)
    original_sources = read_json(SOURCES_PATH)
    original_links = read_json(PASSAGE_LINKS_PATH)
    import_report = read_json(IMPORT_REPORT_PATH) if IMPORT_REPORT_PATH.exists() else {}
    before_snapshot = {
        "places": deepcopy(original_places),
        "sources": deepcopy(original_sources),
        "links": deepcopy(original_links),
    }
    before_hash = compact_json_hash(before_snapshot)

    fixed_places = normalize_places(original_places)
    fixed_sources = normalize_sources(original_sources)
    fixed_links = normalize_passage_links(original_links)
    fixed_snapshot = {
        "places": fixed_places,
        "sources": fixed_sources,
        "links": fixed_links,
    }
    after_hash = compact_json_hash(fixed_snapshot)

    auto_fixes: list[str] = []
    if fixed_places != original_places:
        auto_fixes.append("pilot_places.json whitespace/empty-string/list normalization and deterministic record order")
    if fixed_sources != original_sources:
        auto_fixes.append("sources.json duplicate source_id removal, whitespace normalization and deterministic record order")
    if fixed_links != original_links:
        auto_fixes.append("passage_place_links.json whitespace normalization and deterministic record order")

    if fix:
        if fixed_places != original_places:
            write_json(target_places_path, fixed_places)
        if fixed_sources != original_sources:
            write_json(SOURCES_PATH, fixed_sources)
        if fixed_links != original_links:
            write_json(PASSAGE_LINKS_PATH, fixed_links)
        places, sources, links = fixed_places, fixed_sources, fixed_links
    else:
        places, sources, links = original_places, original_sources, original_links

    findings = audit_catalog(places, sources, links)
    report = report_data(places, sources, links, findings, auto_fixes if fix else [], before_hash, after_hash)
    report["audited_catalog_path"] = str(target_places_path.relative_to(ROOT))
    report["openbible_raw_place_count"] = import_report.get("raw_place_count")
    report["successfully_imported_place_count"] = import_report.get("imported_place_count")
    report["skipped_place_count"] = import_report.get("skipped_place_count")
    report["skipped_places_by_reason"] = import_report.get("skipped_places_by_reason", {})
    report["manual_override_count"] = import_report.get("manual_override_count")
    report["merged_catalog_count"] = import_report.get("merged_catalog_count", len(places))
    report["generated_passage_catalog_count"] = import_report.get("passage_catalog_count")
    write_json(REPORT_JSON_PATH, report)
    REPORT_MD_PATH.write_text(markdown_report(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the biblical places catalog.")
    parser.add_argument("--fix", action="store_true", help="Apply safe deterministic technical fixes.")
    args = parser.parse_args()
    report = run(fix=args.fix)
    print(
        json.dumps(
            {
                "catalog_record_count": report["catalog_record_count"],
                "passage_place_link_count": report["passage_place_link_count"],
                "summary": report["summary"],
                "auto_fixed_items": report["auto_fixed_items"],
                "review_required_count": report["review_required_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
