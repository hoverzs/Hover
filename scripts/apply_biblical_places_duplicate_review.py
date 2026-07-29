from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "biblical_places"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
DUPLICATE_QUEUE_PATH = DATA_DIR / "duplicate_review_queue.json"
MERGE_DECISIONS_PATH = DATA_DIR / "duplicate_place_merges.json"
DEFAULT_BATCH_PATH = DATA_DIR / "duplicate_review_batch_001_reviewed.json"
DEFAULT_REPORT_PATH = DATA_DIR / "duplicate_review_apply_report.json"

EXPECTED_GROUPS_BY_BATCH = {
    "duplicate_review_batch_001_reviewed.json": {
        "merge": {
            "dup_egypt__ham_2",
            "dup_abdon__ebron",
            "dup_ai_1__ai_3",
            "dup_aija__ayyah",
            "dup_aphek_1__aphik",
            "dup_arad_1__arad_2",
            "dup_aroer_3__aroer_4",
        },
        "keep_separate": {
            "dup_kadesh_barnea__meribah_1",
            "dup_aram_naharaim__mesopotamia",
            "dup_arnon__valley_of_the_arnon",
        },
    },
    "duplicate_review_batch_002_reviewed.json": {
        "merge": {
            "dup_beersheba_1__beersheba_2__sheba_2",
            "dup_beth_eden__eden_2",
            "dup_bethlehem_2__bethlehem_3",
            "dup_bethsaida_1__bethsaida_2",
            "dup_chaldea__leb_kamai",
            "dup_city_of_palms_1__city_of_palms_2",
        },
        "keep_separate": {
            "dup_babylon_2__babylon_3",
            "dup_bealoth_1__bealoth_2",
            "dup_bezek_1__bezek_2",
            "dup_cush_1__ethiopia",
        },
    },
    "duplicate_review_batch_003_reviewed.json": {
        "count": 45,
        "merge_count": 22,
        "keep_separate_count": 23,
    },
}
REQUIRED_STRATEGY_FIELDS = {
    "proposed_passage_strategy",
    "proposed_coordinate_strategy",
    "proposed_alias_strategy",
    "proposed_record_type",
}
PROTECTED_PLACE_IDS = {"corinth", "ephesus", "jerusalem", "nazareth", "thessalonica"}
IDENTIFICATION_STATUS_RANK = {
    "unknown": 0,
    "disputed": 1,
    "possible": 2,
    "probable": 3,
    "certain": 4,
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text(value: Any) -> str:
    return str(value or "").strip()


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


def has_text(value: Any) -> bool:
    return bool(text(value))


def validate_batch(batch_path: Path, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    batch = read_json(batch_path, None)
    if not isinstance(batch, list):
        raise ValueError("The reviewed duplicate batch must be a JSON list.")
    expected = EXPECTED_GROUPS_BY_BATCH.get(batch_path.name)
    expected_count = int((expected or {}).get("count", 10))
    if len(batch) != expected_count:
        raise ValueError(f"Expected exactly {expected_count} groups, got {len(batch)}.")

    catalog_ids = {text(place.get("place_id")) for place in catalog}
    catalog_by_id = {text(place.get("place_id")): place for place in catalog}
    group_ids = [text(group.get("group_id")) for group in batch]
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("Duplicate group_id found in reviewed duplicate batch.")

    merge_groups = {text(group.get("group_id")) for group in batch if group.get("final_action") == "merge"}
    keep_groups = {text(group.get("group_id")) for group in batch if group.get("final_action") == "keep_separate"}
    if expected is not None:
        if "merge" in expected and merge_groups != expected["merge"]:
            raise ValueError(f"Merge group mismatch: {sorted(merge_groups)}")
        if "keep_separate" in expected and keep_groups != expected["keep_separate"]:
            raise ValueError(f"Keep-separate group mismatch: {sorted(keep_groups)}")
        if "merge_count" in expected and len(merge_groups) != expected["merge_count"]:
            raise ValueError(f"Expected {expected['merge_count']} merge groups, got {len(merge_groups)}.")
        if "keep_separate_count" in expected and len(keep_groups) != expected["keep_separate_count"]:
            raise ValueError(
                f"Expected {expected['keep_separate_count']} keep-separate groups, got {len(keep_groups)}."
            )

    for group in batch:
        group_id = text(group.get("group_id"))
        candidate_ids = [text(place_id) for place_id in group.get("candidate_place_ids") or []]
        if len(candidate_ids) < 2 or len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError(f"{group_id}: invalid candidate_place_ids.")
        if group.get("review_status") != "reviewed":
            raise ValueError(f"{group_id}: review_status must be reviewed.")
        if group.get("final_action") not in {"merge", "keep_separate"}:
            raise ValueError(f"{group_id}: final_action must be merge or keep_separate.")
        for field in REQUIRED_STRATEGY_FIELDS:
            if not has_text(group.get(field)):
                raise ValueError(f"{group_id}: missing {field}.")
        if group.get("final_action") == "keep_separate" and not has_text(group.get("expert_decision_hu")):
            raise ValueError(f"{group_id}: expert_decision_hu is required for keep_separate.")
        if group.get("final_action") == "merge":
            canonical_id = text(group.get("proposed_canonical_place_id"))
            if canonical_id not in candidate_ids:
                raise ValueError(f"{group_id}: proposed_canonical_place_id is not a candidate.")
            missing = sorted(place_id for place_id in candidate_ids if place_id not in catalog_ids)
            canonical_legacy_ids = set(catalog_by_id.get(canonical_id, {}).get("legacy_place_ids") or [])
            if missing and not set(missing).issubset(canonical_legacy_ids):
                raise ValueError(f"{group_id}: unknown candidate place_id values: {missing}")
            if not has_text(group.get("proposed_merged_name_hu")):
                raise ValueError(f"{group_id}: proposed_merged_name_hu is required.")
            if not has_text(group.get("proposed_merged_summary_hu")):
                raise ValueError(f"{group_id}: proposed_merged_summary_hu is required.")
        else:
            missing = sorted(place_id for place_id in candidate_ids if place_id not in catalog_ids)
            if missing:
                raise ValueError(f"{group_id}: unknown candidate place_id values: {missing}")
    return batch


def validate_hungarian_text(batch: list[dict[str, Any]]) -> None:
    suspicious = re.compile(r"\?|�|Ă|Ĺ|Ĺ|Ĺ")
    for group in batch:
        group_id = text(group.get("group_id"))
        for key, value in group.items():
            if isinstance(value, str) and suspicious.search(value):
                raise ValueError(f"{group_id}: suspicious text encoding marker in {key}.")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and suspicious.search(item):
                        raise ValueError(f"{group_id}: suspicious text encoding marker in {key}.")


def alias_allowed(group_id: str, value: Any) -> bool:
    normalized = text(value).casefold()
    if not normalized:
        return False
    if group_id == "dup_egypt__ham_2" and normalized in {"ham", "hám", "ham 2"}:
        return False
    if group_id == "dup_abdon__ebron" and normalized == "hebron":
        return False
    if group_id == "dup_aija__ayyah" and normalized == "gaza":
        return False
    if group_id == "dup_judea_1__judea_2" and normalized in {"galilee", "galilean", "galileans"}:
        return False
    return True


def rejected_aliases_for(group_id: str) -> list[str]:
    if group_id == "dup_egypt__ham_2":
        return ["Ham", "Hám"]
    if group_id == "dup_abdon__ebron":
        return ["Hebron"]
    if group_id == "dup_aija__ayyah":
        return ["Gaza"]
    if group_id == "dup_judea_1__judea_2":
        return ["Galilee"]
    return []


def least_certain_status(records: list[dict[str, Any]]) -> str:
    statuses = [text(record.get("identification_status")) or "unknown" for record in records]
    return min(statuses, key=lambda item: IDENTIFICATION_STATUS_RANK.get(item, 0))


def merge_record(canonical: dict[str, Any], removed_records: list[dict[str, Any]], group: dict[str, Any]) -> dict[str, Any]:
    group_id = text(group.get("group_id"))
    candidates = [canonical, *removed_records]
    updated = deepcopy(canonical)
    updated["name_hu"] = text(group.get("proposed_merged_name_hu")) or updated.get("name_hu")
    updated["card_summary_hu"] = text(group.get("proposed_merged_summary_hu")) or updated.get("card_summary_hu")
    updated["review_status"] = "reviewed"
    updated["identification_status"] = least_certain_status(candidates)
    for key in ("ancient_names", "original_names", "transliterations"):
        values = [
            value
            for record in candidates
            for value in (record.get(key) or [])
            if alias_allowed(group_id, value)
        ]
        updated[key] = stable_unique(values)
    for key in ("source_ids", "exegetical_notes"):
        updated[key] = stable_unique([value for record in candidates for value in (record.get(key) or [])])

    legacy_ids = [
        place_id
        for record in removed_records
        if (place_id := text(record.get("place_id")))
    ]
    legacy_ids.extend(
        text(value)
        for record in candidates
        for value in (record.get("legacy_place_ids") or [])
        if text(value)
    )
    updated["legacy_place_ids"] = stable_unique([*(updated.get("legacy_place_ids") or []), *legacy_ids])
    updated["rejected_aliases_hu"] = stable_unique(
        [*(updated.get("rejected_aliases_hu") or []), *rejected_aliases_for(group_id)]
    )
    note = (
        f"Duplikációs review alapján összevont rekord ({group_id}); "
        f"korábbi place_id-k: {', '.join(legacy_ids[: len(removed_records)])}."
    )
    decision_note = text(group.get("expert_decision_hu"))
    risk_values = [text(value) for value in group.get("merge_risks_hu") or [] if text(value)]
    if decision_note:
        note += f" Szakmai döntés: {decision_note}"
    if risk_values:
        note += " Kockázatok: " + " ".join(risk_values)
    existing_note = text(updated.get("merge_review_notes_hu"))
    updated["merge_review_notes_hu"] = existing_note if note in existing_note else (existing_note + "\n" + note).strip()

    for key in (
        "geography_hu",
        "history_hu",
        "political_context_hu",
        "economic_context_hu",
        "social_context_hu",
        "religious_context_hu",
        "archaeology_hu",
        "biblical_significance_hu",
        "modern_context_hu",
    ):
        if has_text(updated.get(key)):
            continue
        for record in removed_records:
            if has_text(record.get(key)):
                updated[key] = record[key]
                break
    return updated


def redirect_links(links: list[dict[str, Any]], redirects: dict[str, str]) -> tuple[list[dict[str, Any]], int, int, int]:
    pre_canonicalized = {
        (text(link.get("reference")), redirects.get(text(link.get("place_id")), text(link.get("place_id"))))
        for link in links
        if text(link.get("reference")) and text(link.get("place_id"))
    }
    redirected = 0
    deduped = 0
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for link in links:
        old_place_id = text(link.get("place_id"))
        new_place_id = redirects.get(old_place_id, old_place_id)
        updated = deepcopy(link)
        if new_place_id != old_place_id:
            redirected += 1
            updated["place_id"] = new_place_id
        key = (text(updated.get("reference")), text(updated.get("place_id")))
        if not key[0] or not key[1]:
            continue
        if key in seen:
            deduped += 1
            continue
        seen.add(key)
        result.append(updated)
    post = {(text(link.get("reference")), text(link.get("place_id"))) for link in result}
    lost = len(pre_canonicalized - post)
    result.sort(key=lambda link: (0 if text(link.get("source_note")) == "pilot passage index" else 1, text(link.get("reference")), text(link.get("place_id"))))
    return result, redirected, deduped, lost


def update_duplicate_queue(queue: list[dict[str, Any]], batch: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    reviewed_by_id = {text(group.get("group_id")): group for group in batch}
    changed = 0
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in queue:
        group_id = text(group.get("group_id"))
        reviewed = reviewed_by_id.get(group_id)
        if reviewed is None:
            result.append(group)
            continue
        updated = deepcopy(group)
        for key, value in reviewed.items():
            if key in {
                "proposed_canonical_place_id",
                "proposed_merged_name_hu",
                "proposed_merged_summary_hu",
                "proposed_passage_strategy",
                "proposed_coordinate_strategy",
                "proposed_alias_strategy",
                "proposed_record_type",
                "merge_risks_hu",
                "expert_decision_hu",
                "final_action",
                "review_status",
                "reviewer_notes_hu",
            }:
                updated[key] = deepcopy(value)
        if reviewed.get("final_action") == "keep_separate":
            updated["reviewer_notes_hu"] = deepcopy(reviewed.get("expert_decision_hu"))
            record_type = text(reviewed.get("proposed_record_type"))
            if record_type == "same_place_different_record_type":
                updated["recommended_action"] = "same_place_different_record_type"
            elif record_type in {"keep_separate_probable", "possibly_distinct_settlements"}:
                updated["recommended_action"] = "keep_separate_probable"
            elif record_type == "insufficient_evidence":
                updated["recommended_action"] = "insufficient_evidence"
            else:
                updated["recommended_action"] = "needs_expert_review"
        result.append(updated)
        seen.add(group_id)
        if updated != group:
            changed += 1
    for group_id, reviewed in reviewed_by_id.items():
        if group_id not in seen:
            result.append(deepcopy(reviewed))
            changed += 1
    return result, changed


def apply_reviews(batch_path: Path, *, write: bool) -> dict[str, Any]:
    catalog = read_json(CATALOG_PATH, [])
    links = read_json(PASSAGE_LINKS_PATH, [])
    queue = read_json(DUPLICATE_QUEUE_PATH, [])
    existing_decisions = read_json(MERGE_DECISIONS_PATH, [])
    batch = validate_batch(batch_path, catalog)
    validate_hungarian_text(batch)

    catalog_before = len(catalog)
    by_id = {text(record.get("place_id")): deepcopy(record) for record in catalog}
    redirects: dict[str, str] = {}
    removed_place_ids: list[str] = []
    canonical_place_ids: list[str] = []
    decisions_by_group = {text(decision.get("group_id")): decision for decision in existing_decisions if isinstance(decision, dict)}

    for group in batch:
        if group.get("final_action") != "merge":
            continue
        canonical_id = text(group.get("proposed_canonical_place_id"))
        candidate_ids = [text(place_id) for place_id in group.get("candidate_place_ids") or []]
        removed_ids = [place_id for place_id in candidate_ids if place_id != canonical_id]
        canonical_place_ids.append(canonical_id)
        if canonical_id not in by_id:
            for removed_id in removed_ids:
                redirects[removed_id] = canonical_id
            continue
        removed_records = [by_id[place_id] for place_id in removed_ids if place_id in by_id]
        if removed_records:
            by_id[canonical_id] = merge_record(by_id[canonical_id], removed_records, group)
            for removed_id in removed_ids:
                redirects[removed_id] = canonical_id
                if removed_id in by_id:
                    by_id.pop(removed_id)
                    removed_place_ids.append(removed_id)
        decisions_by_group[text(group.get("group_id"))] = {
            "group_id": text(group.get("group_id")),
            "final_action": "merge",
            "canonical_place_id": canonical_id,
            "removed_place_ids": removed_ids,
            "candidate_place_ids": candidate_ids,
            "proposed_merged_name_hu": group.get("proposed_merged_name_hu"),
            "proposed_merged_summary_hu": group.get("proposed_merged_summary_hu"),
            "proposed_passage_strategy": group.get("proposed_passage_strategy"),
            "proposed_coordinate_strategy": group.get("proposed_coordinate_strategy"),
            "proposed_alias_strategy": group.get("proposed_alias_strategy"),
            "proposed_record_type": group.get("proposed_record_type"),
            "expert_decision_hu": group.get("expert_decision_hu"),
            "merge_risks_hu": group.get("merge_risks_hu") or [],
        }

    merged_catalog = sorted(by_id.values(), key=lambda record: text(record.get("place_id")))
    merged_links, redirected_link_count, deduped_link_count, lost_link_count = redirect_links(links, redirects)
    updated_queue, queue_changed_count = update_duplicate_queue(queue, batch)
    decisions = sorted(decisions_by_group.values(), key=lambda item: text(item.get("group_id")))
    bad_refs = [
        {"reference": link.get("reference"), "place_id": link.get("place_id")}
        for link in merged_links
        if text(link.get("place_id")) not in by_id
    ]
    protected_missing = sorted(place_id for place_id in PROTECTED_PLACE_IDS if place_id not in by_id)
    report = {
        "valid_groups": len(batch),
        "merge_decision_count": len([group for group in batch if group.get("final_action") == "merge"]),
        "keep_separate_count": len([group for group in batch if group.get("final_action") == "keep_separate"]),
        "catalog_count_before": catalog_before,
        "catalog_count_after": len(merged_catalog),
        "removed_place_ids": sorted(removed_place_ids),
        "canonical_place_ids": sorted(set(canonical_place_ids)),
        "redirected_passage_link_count": redirected_link_count,
        "deduped_passage_link_count": deduped_link_count,
        "lost_passage_link_count": lost_link_count,
        "bad_passage_reference_count": len(bad_refs),
        "bad_passage_references": bad_refs[:20],
        "duplicate_queue_changed_groups": queue_changed_count,
        "protected_missing_place_ids": protected_missing,
        "would_write": write,
    }
    if bad_refs:
        raise ValueError(f"Passage-place integrity failed: {bad_refs[:5]}")
    if protected_missing:
        raise ValueError(f"Protected records missing after merge: {protected_missing}")
    if lost_link_count != 0:
        raise ValueError(f"Lost passage links after redirect: {lost_link_count}")

    if write:
        write_json(CATALOG_PATH, merged_catalog)
        write_json(PASSAGE_LINKS_PATH, merged_links)
        write_json(DUPLICATE_QUEUE_PATH, updated_queue)
        write_json(MERGE_DECISIONS_PATH, decisions)
        report_to_write = report
        previous_report = read_json(DEFAULT_REPORT_PATH, {})
        if (
            isinstance(previous_report, dict)
            and previous_report.get("removed_place_ids")
            and not report.get("removed_place_ids")
        ):
            report_to_write = deepcopy(previous_report)
            report_to_write["idempotency_check_report"] = report
        write_json(DEFAULT_REPORT_PATH, report_to_write)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply reviewed biblical place duplicate merge decisions.")
    parser.add_argument("batch_path", nargs="?", type=Path, default=DEFAULT_BATCH_PATH)
    parser.add_argument("--apply", action="store_true", help="Write catalog, passage links, queue and merge decision log.")
    args = parser.parse_args(argv)
    try:
        report = apply_reviews(args.batch_path, write=args.apply)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
