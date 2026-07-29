from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "biblical_places"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
QUEUE_PATH = DATA_DIR / "hungarian_review_queue.json"
BATCH_PATH = DATA_DIR / "hungarian_review_batch_001.json"
DEFAULT_DRAFT_PATH = DATA_DIR / "hungarian_review_batch_001_hu_draft.json"
BATCH_SIZE = 100


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_nonempty_text(item: dict[str, Any], key: str) -> str:
    text = str(item.get(key) or "").strip()
    if not text:
        raise ValueError(f"{item.get('place_id')}: {key} must be non-empty.")
    return text


def validate_draft(
    draft: Any,
    *,
    catalog: list[dict[str, Any]],
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(draft, list):
        raise ValueError("Draft review file must contain a JSON list.")
    if len(draft) != BATCH_SIZE:
        raise ValueError(f"Draft review file must contain exactly {BATCH_SIZE} records.")
    catalog_ids = {str(item.get("place_id") or "") for item in catalog}
    batch_ids = [str(item.get("place_id") or "") for item in batch]
    draft_ids = [str(item.get("place_id") or "") for item in draft]
    if len(set(draft_ids)) != len(draft_ids):
        raise ValueError("Draft review file contains duplicate place_id values.")
    if set(draft_ids) != set(batch_ids):
        raise ValueError("Draft review place_id set must match the selected batch file.")
    missing = sorted(place_id for place_id in draft_ids if place_id not in catalog_ids)
    if missing:
        raise ValueError(f"Draft review references unknown place_id values: {', '.join(missing[:10])}")
    for item in draft:
        if not isinstance(item, dict):
            raise ValueError("Every draft review record must be an object.")
        require_nonempty_text(item, "place_id")
        require_nonempty_text(item, "proposed_name_hu")
        require_nonempty_text(item, "proposed_card_summary_hu")
    return draft


def apply_to_catalog(
    catalog: list[dict[str, Any]],
    draft: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    draft_by_id = {str(item["place_id"]): item for item in draft}
    changed = 0
    unchanged = 0
    result: list[dict[str, Any]] = []
    for record in catalog:
        place_id = str(record.get("place_id") or "")
        draft_item = draft_by_id.get(place_id)
        if draft_item is None:
            result.append(record)
            unchanged += 1
            continue
        updated = deepcopy(record)
        updated["name_hu"] = require_nonempty_text(draft_item, "proposed_name_hu")
        updated["card_summary_hu"] = require_nonempty_text(draft_item, "proposed_card_summary_hu")
        updated["review_status"] = "draft"
        if updated != record:
            changed += 1
        else:
            unchanged += 1
        result.append(updated)
    return result, changed, unchanged


def apply_to_review_items(
    items: list[dict[str, Any]],
    draft: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    draft_by_id = {str(item["place_id"]): item for item in draft}
    result: list[dict[str, Any]] = []
    for item in items:
        place_id = str(item.get("place_id") or "")
        draft_item = draft_by_id.get(place_id)
        if draft_item is None:
            result.append(item)
            continue
        updated = deepcopy(item)
        updated["current_name_hu"] = require_nonempty_text(draft_item, "proposed_name_hu")
        updated["current_card_summary_hu"] = require_nonempty_text(
            draft_item,
            "proposed_card_summary_hu",
        )
        updated["proposed_name_hu"] = require_nonempty_text(draft_item, "proposed_name_hu")
        updated["proposed_card_summary_hu"] = require_nonempty_text(
            draft_item,
            "proposed_card_summary_hu",
        )
        updated["review_status"] = "draft"
        updated["review_notes_hu"] = draft_item.get(
            "review_notes_hu",
            item.get("review_notes_hu"),
        )
        result.append(updated)
    return result


def apply_review(draft_path: Path, *, batch_path: Path, dry_run: bool) -> dict[str, Any]:
    catalog = read_json(CATALOG_PATH)
    queue = read_json(QUEUE_PATH)
    batch = read_json(batch_path)
    draft = validate_draft(read_json(draft_path), catalog=catalog, batch=batch)

    updated_catalog, changed, unchanged = apply_to_catalog(catalog, draft)
    updated_queue = apply_to_review_items(queue, draft)
    updated_batch = apply_to_review_items(batch, draft)

    if not dry_run:
        write_json(CATALOG_PATH, updated_catalog)
        write_json(QUEUE_PATH, updated_queue)
        write_json(batch_path, updated_batch)

    return {
        "draft_path": str(draft_path),
        "batch_path": str(batch_path),
        "validated_records": len(draft),
        "catalog_records_changed": changed,
        "catalog_records_unchanged": unchanged,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a Hungarian biblical place review batch.")
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT_PATH)
    parser.add_argument("--batch", type=Path, default=BATCH_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = apply_review(args.draft, batch_path=args.batch, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
