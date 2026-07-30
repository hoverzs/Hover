from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "biblical_places"
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
PRIORITY_PATH = DATA_DIR / "place_enrichment_priority.json"
PILOT_AUDIT_PATH = DATA_DIR / "place_enrichment_pilot_quality_audit.json"
CONTENT_QUALITY_PATH = DATA_DIR / "place_enrichment_content_quality_report.json"
PROFILE_GROUPS_PATH = DATA_DIR / "place_profile_groups.json"
ENRICHMENTS_PATH = DATA_DIR / "place_enrichments.json"
SOURCES_PATH = DATA_DIR / "place_enrichment_sources.json"
GLOBAL_RESEARCH_QUEUE_PATH = DATA_DIR / "place_enrichment_research_queue.json"
DEFAULT_OUTPUT_DIR = DATA_DIR / "enrichment_batches"

ALLOWED_SECTIONS = {
    "biblical_significance",
    "key_events",
    "ancient_geography",
    "historical_context",
    "archaeology",
    "modern_context",
    "identification_notes",
    "homiletical_context",
}

ACCEPTED_SOURCE_CATEGORIES = {
    "official_archaeological_site",
    "university_project",
    "academic_gazetteer",
    "museum",
    "heritage_authority",
    "excavation_project",
    "peer_reviewed_publication",
    "official_geographical_source",
    "biblical_text_dataset",
}

SECTION_SOURCE_TYPES = {
    "biblical_significance": ("biblical_text_dataset", "academic_gazetteer"),
    "key_events": ("biblical_text_dataset",),
    "ancient_geography": ("academic_gazetteer", "official_geographical_source"),
    "historical_context": ("university_project", "museum", "peer_reviewed_publication"),
    "archaeology": ("official_archaeological_site", "excavation_project", "heritage_authority", "museum"),
    "modern_context": ("official_geographical_source", "academic_gazetteer"),
    "identification_notes": ("academic_gazetteer", "official_geographical_source"),
    "homiletical_context": ("biblical_text_dataset", "academic_gazetteer", "peer_reviewed_publication"),
}

OT_BOOKS = {
    "GEN",
    "EXO",
    "LEV",
    "NUM",
    "DEU",
    "JOS",
    "JDG",
    "RUT",
    "1SA",
    "2SA",
    "1KI",
    "2KI",
    "1CH",
    "2CH",
    "EZR",
    "NEH",
    "EST",
    "JOB",
    "PSA",
    "PRO",
    "ECC",
    "SNG",
    "ISA",
    "JER",
    "LAM",
    "EZK",
    "DAN",
    "HOS",
    "JOL",
    "AMO",
    "OBA",
    "JON",
    "MIC",
    "NAM",
    "HAB",
    "ZEP",
    "HAG",
    "ZEC",
    "MAL",
    "MT",
    "Mk",
}
NT_BOOKS = {
    "MAT",
    "MRK",
    "LUK",
    "JHN",
    "ACT",
    "ROM",
    "1CO",
    "2CO",
    "GAL",
    "EPH",
    "PHP",
    "COL",
    "1TH",
    "2TH",
    "1TI",
    "2TI",
    "TIT",
    "PHM",
    "HEB",
    "JAS",
    "1PE",
    "2PE",
    "1JN",
    "2JN",
    "3JN",
    "JUD",
    "REV",
    "ApCsel",
    "Mt",
    "Mk",
    "Lk",
    "Jn",
}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def book_from_reference(reference: str) -> str:
    return str(reference or "").strip().split(" ", 1)[0]


def testament_for_book(book: str) -> str:
    if book in OT_BOOKS:
        return "old_testament"
    if book in NT_BOOKS:
        return "new_testament"
    return "unknown"


def route_index(routes: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for route in routes:
        for stop in route.get("stops") or []:
            place_id = stop.get("place_id")
            if place_id and route["route_id"] not in result[place_id]:
                result[place_id].append(route["route_id"])
    return {place_id: sorted(route_ids) for place_id, route_ids in result.items()}


def group_indexes(groups: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_profile = {group["profile_id"]: group for group in groups}
    by_place: dict[str, dict[str, Any]] = {}
    for group in groups:
        for place_id in group.get("member_place_ids") or []:
            by_place[place_id] = group
    return by_profile, by_place


def place_testament_stats(links: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    books_by_place: dict[str, set[str]] = defaultdict(set)
    testament_by_place: dict[str, Counter[str]] = defaultdict(Counter)
    for link in links:
        book = book_from_reference(link.get("reference", ""))
        books_by_place[link["place_id"]].add(book)
        testament_by_place[link["place_id"]][testament_for_book(book)] += 1
    stats: dict[str, dict[str, Any]] = {}
    for place_id, books in books_by_place.items():
        testament_counts = testament_by_place[place_id]
        if testament_counts["old_testament"] and testament_counts["new_testament"]:
            era = "multi_period"
        elif testament_counts["new_testament"]:
            era = "new_testament"
        elif testament_counts["old_testament"]:
            era = "old_testament"
        else:
            era = "unknown"
        stats[place_id] = {
            "books": sorted(books),
            "era": era,
            "primary_book": sorted(books)[0] if books else "unknown",
        }
    return stats


def required_sections_for(row: dict[str, Any], place: dict[str, Any]) -> list[str]:
    sections = ["biblical_significance", "key_events", "identification_notes"]
    if place.get("modern_name") or place.get("modern_country"):
        sections.append("modern_context")
    if row.get("route_count", 0) or place.get("ancient_region") or place.get("region_hu"):
        sections.append("ancient_geography")
    if row.get("passage_count", 0) >= 20 or row.get("biblical_book_count", 0) >= 5 or row.get("route_count", 0):
        sections.append("historical_context")
    if row.get("passage_count", 0) >= 20 or row.get("route_count", 0) or row.get("identification_status") in {"certain", "probable"}:
        sections.append("archaeology")
    return [section for section in sections if section in ALLOWED_SECTIONS]


def optional_sections_for(row: dict[str, Any]) -> list[str]:
    optional: list[str] = []
    if row.get("route_count", 0) or row.get("route_stop_count", 0):
        optional.append("homiletical_context")
    return optional


def required_source_types_for(sections: list[str]) -> list[str]:
    values: list[str] = []
    for section in sections:
        values.extend(SECTION_SOURCE_TYPES.get(section, ()))
    return sorted(set(values))


def source_gap_count(row: dict[str, Any], sections: list[str]) -> int:
    base_gap = int(row.get("source_gap_count") or 0)
    if "archaeology" in sections and row.get("source_count", 0) <= 1:
        base_gap += 1
    if "historical_context" in sections and row.get("source_count", 0) <= 1:
        base_gap += 1
    return base_gap


def selection_score(row: dict[str, Any], group: dict[str, Any] | None) -> int:
    certainty_bonus = {
        "certain": 80,
        "probable": 50,
        "possible": 10,
        "disputed": -30,
        "unknown": -20,
    }.get(row.get("identification_status"), 0)
    readiness_bonus = max(0, int(row.get("source_count") or 0) - int(row.get("source_gap_count") or 0)) * 20
    group_penalty = 15 if group and group.get("review_status") == "needs_review" else 0
    return (
        int(row.get("total_score") or 0)
        + int(row.get("research_priority") or 0) * 8
        + int(row.get("passage_count") or 0) * 3
        + int(row.get("biblical_book_count") or 0) * 20
        + int(row.get("route_stop_count") or 0) * 40
        + int(row.get("route_count") or 0) * 60
        + int(row.get("content_quality_score") or 0)
        + readiness_bonus
        + certainty_bonus
        + int(row.get("manual_priority") or 0)
        - group_penalty
    )


def build_blocked_record(
    row: dict[str, Any],
    place: dict[str, Any] | None,
    reason: str,
    group: dict[str, Any] | None,
    related_place_ids: list[str],
) -> dict[str, Any]:
    return {
        "place_id": row["place_id"],
        "name_hu": (place or {}).get("name_hu") or row.get("name_hu"),
        "blocking_reason": reason,
        "related_place_ids": related_place_ids,
        "profile_group_id": group.get("profile_id") if group else None,
        "required_resolution": "canonical_record_review",
        "recommended_next_action": "review_before_batch_selection",
        "priority_if_resolved": row.get("total_score", 0),
    }


def build_batch(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_number = int(args.batch_number)
    batch_size = int(args.batch_size)
    suffix = f"{batch_number:03d}"

    catalog = read_json(CATALOG_PATH)
    places_by_id = {place["place_id"]: place for place in catalog}
    active_ids = set(places_by_id)
    legacy_ids = {
        legacy_id
        for place in catalog
        for legacy_id in (place.get("legacy_place_ids") or [])
    }
    priority_rows = read_json(PRIORITY_PATH)
    pilot_place_ids = {item["place_id"] for item in read_json(ENRICHMENTS_PATH, [])}
    quality_rows = read_json(PILOT_AUDIT_PATH, [])
    needs_resolution_ids = {
        item["resolved_place_id"]
        for item in quality_rows
        if item.get("profile_status") == "needs_record_resolution"
    }
    content_quality = read_json(CONTENT_QUALITY_PATH, [])
    research_queue = read_json(GLOBAL_RESEARCH_QUEUE_PATH, [])
    groups = read_json(PROFILE_GROUPS_PATH, [])
    _groups_by_id, groups_by_place = group_indexes(groups)
    routes = read_json(ROUTES_PATH)
    route_ids_by_place = route_index(routes)
    links = read_json(PASSAGE_LINKS_PATH)
    testament_stats = place_testament_stats(links)
    source_registry_ids = {source["source_id"] for source in read_json(SOURCES_PATH)}

    blocked: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    excluded_existing_pilot = 0
    excluded_legacy_ids = 0
    excluded_record_resolution = 0
    excluded_profile_group_conflicts = 0
    for row in priority_rows:
        place_id = row["place_id"]
        place = places_by_id.get(place_id)
        group = groups_by_place.get(place_id)
        if place_id in needs_resolution_ids or row.get("record_resolution_needed"):
            excluded_record_resolution += 1
            quality = next((item for item in quality_rows if item.get("resolved_place_id") == place_id), {})
            blocked.append(
                build_blocked_record(
                    row,
                    place,
                    "needs_record_resolution",
                    group,
                    quality.get("related_canonical_place_ids") or [],
                )
            )
            continue
        if place_id in pilot_place_ids:
            excluded_existing_pilot += 1
            continue
        if place_id in legacy_ids or place_id not in active_ids or place is None:
            excluded_legacy_ids += 1
            blocked.append(build_blocked_record(row, place, "legacy_or_inactive_place_id", group, []))
            continue
        if group and group.get("primary_place_id") != place_id:
            excluded_profile_group_conflicts += 1
            blocked.append(
                build_blocked_record(
                    row,
                    place,
                    "non_primary_profile_group_member",
                    group,
                    [item for item in group.get("member_place_ids", []) if item != place_id],
                )
            )
            continue
        if place.get("latitude") is None or place.get("longitude") is None:
            blocked.append(build_blocked_record(row, place, "missing_coordinates", group, []))
            continue
        sections = required_sections_for(row, place)
        optional_sections = optional_sections_for(row)
        section_source_types = required_source_types_for(sections)
        row_source_gap_count = source_gap_count(row, sections)
        route_ids = route_ids_by_place.get(place_id, [])
        stats = testament_stats.get(place_id, {"books": [], "era": "unknown", "primary_book": "unknown"})
        score = selection_score(row, group)
        candidates.append(
            {
                "row": row,
                "place": place,
                "group": group,
                "sections": sections,
                "optional_sections": optional_sections,
                "source_types": section_source_types,
                "source_gap_count": row_source_gap_count,
                "route_ids": route_ids,
                "era": stats["era"],
                "primary_book": stats["primary_book"],
                "score": score,
            }
        )

    candidates.sort(
        key=lambda item: (
            -item["score"],
            item["era"],
            item["primary_book"],
            item["row"]["place_id"],
        )
    )

    selected: list[dict[str, Any]] = []
    book_counts: Counter[str] = Counter()
    era_counts: Counter[str] = Counter()
    max_per_book = 10
    max_per_era = 35
    for candidate in candidates:
        if len(selected) >= batch_size:
            break
        if book_counts[candidate["primary_book"]] >= max_per_book:
            continue
        if candidate["era"] in {"old_testament", "new_testament"} and era_counts[candidate["era"]] >= max_per_era:
            continue
        selected.append(candidate)
        book_counts[candidate["primary_book"]] += 1
        era_counts[candidate["era"]] += 1
    if len(selected) < batch_size:
        selected_ids = {item["row"]["place_id"] for item in selected}
        for candidate in candidates:
            if len(selected) >= batch_size:
                break
            if candidate["row"]["place_id"] not in selected_ids:
                selected.append(candidate)
                selected_ids.add(candidate["row"]["place_id"])

    manifest: list[dict[str, Any]] = []
    research_tasks: list[dict[str, Any]] = []
    for index, item in enumerate(selected, start=1):
        row = item["row"]
        place = item["place"]
        group = item["group"]
        sections = item["sections"]
        optional_sections = item["optional_sections"]
        source_types = item["source_types"]
        source_gap = item["source_gap_count"]
        route_ids = item["route_ids"]
        blocking_issues = []
        if source_gap:
            blocking_issues.append("source_gap")
        if group and group.get("review_status") == "needs_review":
            blocking_issues.append("profile_group_needs_review")
        ready_for_research = True
        ready_for_content = source_gap == 0 and not blocking_issues
        manifest.append(
            {
                "batch_position": index,
                "place_id": row["place_id"],
                "name_hu": place.get("name_hu") or row.get("name_hu"),
                "name_en": place.get("name_en"),
                "place_type": place.get("place_type"),
                "modern_country": place.get("modern_country"),
                "identification_status": row.get("identification_status"),
                "profile_group_id": group.get("profile_id") if group else None,
                "current_enrichment_status": row.get("enrichment_status", "basic"),
                "passage_count": row.get("passage_count", 0),
                "biblical_book_count": row.get("biblical_book_count", 0),
                "route_stop_count": row.get("route_stop_count", 0),
                "route_count": row.get("route_count", 0),
                "related_route_ids": route_ids,
                "existing_source_ids": place.get("source_ids") or [],
                "source_count": row.get("source_count", 0),
                "source_gap_count": source_gap,
                "research_priority": row.get("research_priority", 0),
                "total_score": row.get("total_score", 0),
                "selection_reason_hu": selection_reason_hu(row, item),
                "required_sections": sections,
                "optional_sections": optional_sections,
                "required_source_types": source_types,
                "blocking_issues": blocking_issues,
                "ready_for_research": ready_for_research,
                "ready_for_content": ready_for_content,
                "notes_hu": "Automatikus előkészítő batch; új tartalmi szöveg nem készült.",
            }
        )
        for section in sections:
            required_types = SECTION_SOURCE_TYPES.get(section, ())
            research_tasks.append(
                {
                    "task_id": f"batch_{suffix}_{index:03d}_{section}",
                    "batch_number": batch_number,
                    "place_id": row["place_id"],
                    "name_hu": place.get("name_hu") or row.get("name_hu"),
                    "section_name": section,
                    "priority": research_task_priority(section, item),
                    "required_source_type": " or ".join(required_types),
                    "research_question_hu": research_question(section, place),
                    "accepted_source_categories": list(required_types),
                    "existing_source_ids": place.get("source_ids") or [],
                    "source_gap": section_source_gap(section, item),
                    "blocking_for_source_backed": section in {"biblical_significance", "key_events", "identification_notes"} and section_source_gap(section, item),
                    "blocking_for_featured": section in {"historical_context", "archaeology", "key_events"},
                    "profile_group_notes_hu": group.get("notes_hu") if group else None,
                    "status": "pending",
                }
            )

    selected_ids = {item["place_id"] for item in manifest}
    high_priority_blocked_ids = {item["place_id"] for item in blocked}
    for row in priority_rows[:200]:
        place_id = row["place_id"]
        if place_id not in selected_ids and place_id not in pilot_place_ids and place_id not in high_priority_blocked_ids:
            if row.get("record_resolution_needed"):
                place = places_by_id.get(place_id)
                group = groups_by_place.get(place_id)
                blocked.append(build_blocked_record(row, place, "record_resolution_needed", group, []))

    manifest_path = output_dir / f"place_enrichment_batch_{suffix}.json"
    research_path = output_dir / f"place_enrichment_batch_{suffix}_research_queue.json"
    blocked_path = output_dir / f"place_enrichment_batch_{suffix}_blocked.json"
    csv_path = output_dir / f"place_enrichment_batch_{suffix}.csv"
    report_path = output_dir / f"place_enrichment_batch_{suffix}_report.json"
    write_json(manifest_path, manifest)
    write_json(research_path, research_tasks)
    write_json(blocked_path, blocked)
    write_csv(csv_path, manifest)
    report = build_report(
        batch_size=batch_size,
        manifest=manifest,
        candidates=candidates,
        blocked=blocked,
        excluded_existing_pilot=excluded_existing_pilot,
        excluded_legacy_ids=excluded_legacy_ids,
        excluded_record_resolution=excluded_record_resolution,
        excluded_profile_group_conflicts=excluded_profile_group_conflicts,
        research_tasks=research_tasks,
    )
    write_json(report_path, report)
    return {
        "manifest": manifest,
        "research_tasks": research_tasks,
        "blocked": blocked,
        "report": report,
        "paths": {
            "manifest": manifest_path,
            "research": research_path,
            "blocked": blocked_path,
            "csv": csv_path,
            "report": report_path,
        },
        "source_registry_ids": source_registry_ids,
        "content_quality_count": len(content_quality),
        "global_research_queue_count": len(research_queue),
    }


def selection_reason_hu(row: dict[str, Any], item: dict[str, Any]) -> str:
    parts = [
        f"magas prioritási pontszám ({row.get('total_score', 0)})",
        f"{row.get('passage_count', 0)} passage-kapcsolat",
    ]
    if row.get("route_count", 0):
        parts.append(f"{row.get('route_count')} route-kapcsolat")
    if item["source_gap_count"]:
        parts.append("forráskutatási hiány dokumentálva")
    return "; ".join(parts) + "."


def research_task_priority(section: str, item: dict[str, Any]) -> str:
    if section in {"key_events", "biblical_significance", "identification_notes"}:
        return "high"
    if section in {"archaeology", "historical_context"} and item["row"].get("passage_count", 0) >= 20:
        return "high"
    return "medium"


def research_question(section: str, place: dict[str, Any]) -> str:
    name = place.get("name_hu") or place.get("name_en") or place["place_id"]
    questions = {
        "biblical_significance": f"Mely bibliai szakaszok támasztják alá {name} fő bibliai jelentőségét?",
        "key_events": f"Mely legfontosabb, konkrét bibliai események kapcsolódnak {name} helyéhez?",
        "ancient_geography": f"Milyen ellenőrzött ókori földrajzi háttér adható {name} helyéhez?",
        "historical_context": f"Van-e helyspecifikus történeti háttérforrás {name} rövid adatlapjához?",
        "archaeology": f"Van-e intézményi vagy szakmai régészeti forrás {name} helyéhez?",
        "modern_context": f"Milyen ellenőrzött modern azonosítási háttér rögzíthető {name} helyéhez?",
        "identification_notes": f"Milyen forrás támasztja alá {name} helyazonosításának bizonyosságát vagy bizonytalanságát?",
        "homiletical_context": f"Van-e konkrét, helyspecifikus háttér, amely {name} szövegértelmezési jelentőségét megvilágítja?",
    }
    return questions[section]


def section_source_gap(section: str, item: dict[str, Any]) -> bool:
    if section in {"archaeology", "historical_context"} and item["row"].get("source_count", 0) <= 1:
        return True
    return bool(item["source_gap_count"] and section in {"archaeology", "historical_context"})


def write_csv(path: Path, manifest: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "batch_position",
        "place_id",
        "name_hu",
        "place_type",
        "identification_status",
        "passage_count",
        "biblical_book_count",
        "route_count",
        "research_priority",
        "total_score",
        "required_sections",
        "required_source_types",
        "ready_for_research",
        "blocking_issues",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in manifest:
            writer.writerow(
                {
                    field: ";".join(str(item) for item in row[field])
                    if isinstance(row.get(field), list)
                    else row.get(field)
                    for field in fields
                }
            )


def build_report(
    *,
    batch_size: int,
    manifest: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    excluded_existing_pilot: int,
    excluded_legacy_ids: int,
    excluded_record_resolution: int,
    excluded_profile_group_conflicts: int,
    research_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    era_counts = Counter(era_for_manifest_row(row) for row in manifest)
    required_source_types = Counter(
        source_type
        for row in manifest
        for source_type in row["required_source_types"]
    )
    required_sections = Counter(
        section
        for row in manifest
        for section in row["required_sections"]
    )
    source_gaps = Counter(str(row["source_gap_count"]) for row in manifest)
    return {
        "batch_size_requested": batch_size,
        "batch_size_created": len(manifest),
        "eligible_candidates": len(candidates),
        "excluded_existing_pilot": excluded_existing_pilot,
        "excluded_legacy_ids": excluded_legacy_ids,
        "excluded_record_resolution": excluded_record_resolution,
        "excluded_profile_group_conflicts": excluded_profile_group_conflicts,
        "blocked_count": len(blocked),
        "old_testament_place_count": era_counts["old_testament"],
        "new_testament_place_count": era_counts["new_testament"],
        "multi_period_place_count": era_counts["multi_period"],
        "unknown_period_place_count": era_counts["unknown"],
        "route_linked_place_count": sum(1 for row in manifest if row["route_count"]),
        "passage_count_distribution": distribution([row["passage_count"] for row in manifest]),
        "identification_status_distribution": dict(Counter(row["identification_status"] for row in manifest)),
        "required_source_type_distribution": dict(required_source_types),
        "required_section_distribution": dict(required_sections),
        "source_gap_distribution": dict(source_gaps),
        "top_20_selection_reasons": [
            {
                "batch_position": row["batch_position"],
                "place_id": row["place_id"],
                "name_hu": row["name_hu"],
                "selection_reason_hu": row["selection_reason_hu"],
            }
            for row in manifest[:20]
        ],
        "warnings": [],
        "idempotency_result": "deterministic_builder_rewrite_expected_identical",
        "research_task_count": len(research_tasks),
    }


def era_for_manifest_row(row: dict[str, Any]) -> str:
    if any(route_id.startswith("paul_") for route_id in row.get("related_route_ids", [])):
        return "new_testament"
    if any(route_id.startswith(("joshua_", "abraham_", "jacob_", "joseph_", "exodus_", "wilderness_")) for route_id in row.get("related_route_ids", [])):
        return "old_testament"
    if row.get("biblical_book_count", 0) >= 10 and row.get("passage_count", 0) >= 30:
        return "multi_period"
    return "unknown"


def distribution(values: list[int]) -> dict[str, int]:
    buckets = {"0-9": 0, "10-49": 0, "50-99": 0, "100+": 0}
    for value in values:
        if value < 10:
            buckets["0-9"] += 1
        elif value < 50:
            buckets["10-49"] += 1
        elif value < 100:
            buckets["50-99"] += 1
        else:
            buckets["100+"] += 1
    return buckets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a deterministic place enrichment research batch.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--batch-number", type=int, default=1)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    build_batch(parse_args())


if __name__ == "__main__":
    main()
