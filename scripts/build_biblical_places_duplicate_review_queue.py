from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "biblical_places"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
AUDIT_REPORT_PATH = DATA_DIR / "audit_report.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
HU_REVIEW_QUEUE_PATH = DATA_DIR / "hungarian_review_queue.json"
OUTPUT_PATH = DATA_DIR / "duplicate_review_queue.json"
DOC_PATH = ROOT / "docs" / "biblical_places_duplicate_review.md"

ALLOWED_RECOMMENDED_ACTIONS = {
    "merge_probable",
    "keep_separate_probable",
    "needs_expert_review",
    "same_place_different_record_type",
    "insufficient_evidence",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

REGION_TYPES = {"region", "province", "country", "territory", "wilderness", "island"}
POINT_TYPES = {"settlement", "city", "town", "village", "site", "fortress"}
FEATURE_TYPES = {"river", "mountain", "valley", "body of water", "sea", "lake", "spring"}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def base_place_id(place_id: str) -> str:
    return re.sub(r"_\d+$", "", place_id)


def stable_unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def duplicate_findings(audit_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in audit_report.get("findings") or []
        if finding.get("category") == "probable_duplicate_place"
    ]


def finding_pair(finding: dict[str, Any]) -> tuple[str, str] | None:
    parts = [part.strip() for part in str(finding.get("object_id") or "").split("/")]
    parts = [part for part in parts if part]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def build_components(pairs: list[tuple[str, str]]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for left, right in pairs:
        graph[left].add(right)
        graph[right].add(left)

    components: list[list[str]] = []
    visited: set[str] = set()
    for start in sorted(graph):
        if start in visited:
            continue
        queue = deque([start])
        visited.add(start)
        component: list[str] = []
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbor in sorted(graph[node]):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        components.append(sorted(component))
    return components


def haversine_km(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    lat1 = left.get("latitude")
    lon1 = left.get("longitude")
    lat2 = right.get("latitude")
    lon2 = right.get("longitude")
    if not all(isinstance(value, (int, float)) for value in (lat1, lon1, lat2, lon2)):
        return None
    radius_km = 6371.0088
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return round(radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 3)


def pairwise_distances(records: list[dict[str, Any]]) -> list[float]:
    distances: list[float] = []
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            distance = haversine_km(left, right)
            if distance is not None:
                distances.append(distance)
    return distances


def name_tokens(place: dict[str, Any]) -> set[str]:
    values = [
        place.get("place_id"),
        base_place_id(str(place.get("place_id") or "")),
        place.get("name_en"),
        place.get("name_hu"),
        place.get("modern_name"),
        *(place.get("ancient_names") or []),
        *(place.get("transliterations") or []),
        *(place.get("original_names") or []),
    ]
    return {normalized for value in values if (normalized := normalize_text(value))}


def shared_name_tokens(records: list[dict[str, Any]]) -> set[str]:
    if not records:
        return set()
    shared = name_tokens(records[0])
    for record in records[1:]:
        shared &= name_tokens(record)
    return shared


def place_kind(place_type: Any) -> str:
    normalized = normalize_text(place_type)
    if normalized in REGION_TYPES:
        return "region"
    if normalized in POINT_TYPES:
        return "point"
    if normalized in FEATURE_TYPES:
        return "feature"
    return normalized or "unknown"


def classify_group(
    records: list[dict[str, Any]],
    *,
    shared_passages: list[str],
    distances: list[float],
    match_reasons: list[str],
) -> tuple[str, str]:
    kinds = {place_kind(record.get("place_type")) for record in records}
    bases = {base_place_id(str(record.get("place_id") or "")) for record in records}
    shared_names = shared_name_tokens(records)
    min_distance = min(distances) if distances else None
    exact_or_close = min_distance is not None and min_distance <= 0.25
    close = min_distance is not None and min_distance <= 2.0
    same_base = len(bases) == 1
    mixed_record_type = len(kinds) > 1

    if exact_or_close and (same_base or shared_names) and not mixed_record_type:
        return "merge_probable", "high"
    if exact_or_close and mixed_record_type:
        return "same_place_different_record_type", "medium"
    if close and (same_base or shared_names) and shared_passages:
        return "merge_probable", "medium"
    if mixed_record_type and (close or shared_names):
        return "same_place_different_record_type", "medium"
    if shared_passages and not close:
        return "needs_expert_review", "medium"
    if same_base or shared_names:
        return "needs_expert_review", "medium"
    if any("very close coordinates" in reason for reason in match_reasons):
        return "insufficient_evidence", "low"
    return "needs_expert_review", "low"


def group_priority(group: dict[str, Any]) -> tuple[Any, ...]:
    action_rank = {
        "merge_probable": 0,
        "same_place_different_record_type": 1,
        "needs_expert_review": 2,
        "keep_separate_probable": 3,
        "insufficient_evidence": 4,
    }
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    distance = group.get("coordinate_distance_km")
    return (
        action_rank.get(group["recommended_action"], 99),
        confidence_rank.get(group["confidence"], 99),
        999999 if distance is None else float(distance),
        -len(group.get("shared_passages") or []),
        group["group_id"],
    )


def build_passage_maps(links: list[dict[str, Any]]) -> tuple[dict[str, list[str]], Counter[str]]:
    passages_by_place: dict[str, list[str]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for link in links:
        place_id = str(link.get("place_id") or "").strip()
        reference = str(link.get("reference") or "").strip()
        if not place_id or not reference:
            continue
        counts[place_id] += 1
        passages_by_place[place_id].append(reference)
    return {
        place_id: stable_unique(references)
        for place_id, references in passages_by_place.items()
    }, counts


def build_queue() -> list[dict[str, Any]]:
    catalog = read_json(CATALOG_PATH, [])
    audit_report = read_json(AUDIT_REPORT_PATH, {})
    links = read_json(PASSAGE_LINKS_PATH, [])
    hu_queue = read_json(HU_REVIEW_QUEUE_PATH, [])
    catalog_by_id = {str(place.get("place_id") or ""): place for place in catalog}
    review_notes_by_id = {
        str(item.get("place_id") or ""): item.get("review_notes_hu")
        for item in hu_queue
        if isinstance(item, dict)
    }
    passages_by_place, passage_counts = build_passage_maps(links)

    findings = duplicate_findings(audit_report)
    pairs = [pair for finding in findings if (pair := finding_pair(finding))]
    pair_messages: dict[tuple[str, str], list[str]] = defaultdict(list)
    for finding in findings:
        pair = finding_pair(finding)
        if not pair:
            continue
        pair_messages[tuple(sorted(pair))].append(str(finding.get("message") or "Audit duplicate finding."))

    groups: list[dict[str, Any]] = []
    for component in build_components(pairs):
        records = [catalog_by_id[place_id] for place_id in component if place_id in catalog_by_id]
        if len(records) < 2:
            continue
        candidate_ids = [str(record["place_id"]) for record in records]
        passage_sets = [set(passages_by_place.get(place_id, [])) for place_id in candidate_ids]
        shared_passages = sorted(set.intersection(*passage_sets)) if passage_sets else []
        union_passages = sorted(set.union(*passage_sets)) if passage_sets else []
        distinct_passages = {
            place_id: sorted(set(passages_by_place.get(place_id, [])) - set(shared_passages))[:10]
            for place_id in candidate_ids
        }
        distances = pairwise_distances(records)
        match_reasons = stable_unique(
            [
                reason
                for index, left in enumerate(candidate_ids)
                for right in candidate_ids[index + 1 :]
                for reason in pair_messages.get(tuple(sorted((left, right))), [])
            ]
        )
        if len({record.get("modern_name") for record in records if record.get("modern_name")}) == 1:
            match_reasons.append("Records share the same modern_name.")
        if shared_name_tokens(records):
            match_reasons.append("Records share at least one normalized name variant.")
        if any(base_place_id(place_id) == base_place_id(other) for place_id in candidate_ids for other in candidate_ids if place_id != other):
            match_reasons.append("Records appear to be numbered variants of the same base place_id.")
        match_reasons = stable_unique(match_reasons)
        recommended_action, confidence = classify_group(
            records,
            shared_passages=shared_passages,
            distances=distances,
            match_reasons=match_reasons,
        )
        group = {
            "group_id": "dup_" + "__".join(candidate_ids),
            "candidate_place_ids": candidate_ids,
            "candidate_names_en": {record["place_id"]: record.get("name_en") for record in records},
            "candidate_names_hu": {record["place_id"]: record.get("name_hu") for record in records},
            "ancient_names": {record["place_id"]: record.get("ancient_names") or [] for record in records},
            "modern_names": {record["place_id"]: record.get("modern_name") for record in records},
            "coordinates": {
                record["place_id"]: {
                    "latitude": record.get("latitude"),
                    "longitude": record.get("longitude"),
                }
                for record in records
            },
            "identification_statuses": {
                record["place_id"]: record.get("identification_status") for record in records
            },
            "representative_passages": union_passages[:10],
            "passage_counts": {place_id: int(passage_counts.get(place_id, 0)) for place_id in candidate_ids},
            "source_ids": {record["place_id"]: record.get("source_ids") or [] for record in records},
            "current_review_notes_hu": {
                place_id: review_notes_by_id.get(place_id) for place_id in candidate_ids
            },
            "match_reasons": match_reasons,
            "coordinate_distance_km": max(distances) if distances else None,
            "shared_passages": shared_passages[:10],
            "distinct_passages": distinct_passages,
            "recommended_action": recommended_action,
            "confidence": confidence,
            "reviewer_notes_hu": None,
            "review_status": "pending",
        }
        groups.append(group)

    return sorted(groups, key=group_priority)


def write_documentation(queue: list[dict[str, Any]]) -> None:
    action_counts = Counter(group["recommended_action"] for group in queue)
    confidence_counts = Counter(group["confidence"] for group in queue)
    duplicate_record_ids = {
        place_id
        for group in queue
        for place_id in group.get("candidate_place_ids", [])
    }
    lines = [
        "# Bibliai helyek duplikációgyanú review queue",
        "",
        f"- Duplikációgyanús rekordok száma: {len(duplicate_record_ids)}",
        f"- Review csoportok száma: {len(queue)}",
        f"- `merge_probable`: {action_counts.get('merge_probable', 0)}",
        f"- `keep_separate_probable`: {action_counts.get('keep_separate_probable', 0)}",
        f"- `same_place_different_record_type`: {action_counts.get('same_place_different_record_type', 0)}",
        f"- `needs_expert_review`: {action_counts.get('needs_expert_review', 0)}",
        f"- `insufficient_evidence`: {action_counts.get('insufficient_evidence', 0)}",
        f"- `high` confidence: {confidence_counts.get('high', 0)}",
        f"- `medium` confidence: {confidence_counts.get('medium', 0)}",
        f"- `low` confidence: {confidence_counts.get('low', 0)}",
        "",
        "## Top 20 prioritású csoport",
        "",
        "| group_id | action | confidence | rekordok | távolság km |",
        "|---|---|---|---|---|",
    ]
    for group in queue[:20]:
        distance = group.get("coordinate_distance_km")
        distance_text = "" if distance is None else str(distance)
        lines.append(
            "| {group_id} | {action} | {confidence} | {records} | {distance} |".format(
                group_id=group["group_id"],
                action=group["recommended_action"],
                confidence=group["confidence"],
                records=", ".join(group["candidate_place_ids"]),
                distance=distance_text,
            )
        )
    lines.append("")
    lines.append("A queue csak szakmai ellenőrzési munkalista; nem hajt végre merge-et, törlést vagy place_id módosítást.")
    DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build duplicate review queue for biblical places.")
    parser.add_argument("--check", action="store_true", help="Fail if generated outputs would change.")
    args = parser.parse_args()

    queue = build_queue()
    expected_json = json.dumps(queue, ensure_ascii=False, indent=2) + "\n"
    action_counts = Counter(group["recommended_action"] for group in queue)
    confidence_counts = Counter(group["confidence"] for group in queue)

    if args.check:
        changed = []
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != expected_json:
            changed.append(str(OUTPUT_PATH))
        old_doc = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else None
        write_documentation(queue)
        new_doc = DOC_PATH.read_text(encoding="utf-8")
        if old_doc != new_doc:
            changed.append(str(DOC_PATH))
            if old_doc is not None:
                DOC_PATH.write_text(old_doc, encoding="utf-8")
        if changed:
            print(json.dumps({"changed": changed}, ensure_ascii=False, indent=2))
            return 2
        print("Duplicate review queue idempotency check passed.")
        return 0

    write_json(OUTPUT_PATH, queue)
    write_documentation(queue)
    print(
        json.dumps(
            {
                "groups": len(queue),
                "recommended_action_counts": dict(sorted(action_counts.items())),
                "confidence_counts": dict(sorted(confidence_counts.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
