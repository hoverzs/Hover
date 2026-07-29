from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_biblical_places_duplicate_review_queue import (
    ALLOWED_CONFIDENCE,
    ALLOWED_RECOMMENDED_ACTIONS,
    build_queue,
)


DATA_DIR = ROOT / "data" / "biblical_places"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
OUTPUT_PATH = DATA_DIR / "duplicate_review_queue.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_duplicate_review_queue_shape_and_references() -> None:
    queue = read_json(OUTPUT_PATH)
    catalog_ids = {item["place_id"] for item in read_json(CATALOG_PATH)}
    group_ids = [group["group_id"] for group in queue]

    assert queue
    assert len(group_ids) == len(set(group_ids))
    for group in queue:
        candidate_ids = group["candidate_place_ids"]
        assert len(candidate_ids) >= 2
        assert len(candidate_ids) == len(set(candidate_ids))
        assert set(candidate_ids).issubset(catalog_ids)
        assert group["recommended_action"] in ALLOWED_RECOMMENDED_ACTIONS
        assert group["confidence"] in ALLOWED_CONFIDENCE
        assert group["review_status"] == "pending"
        assert group["reviewer_notes_hu"] is None
        assert isinstance(group["match_reasons"], list)
        assert isinstance(group["shared_passages"], list)
        assert isinstance(group["distinct_passages"], dict)
        assert set(group["distinct_passages"]).issubset(candidate_ids)


def test_duplicate_review_queue_is_deterministic() -> None:
    assert build_queue() == read_json(OUTPUT_PATH)


def test_duplicate_review_queue_contains_audit_groups_only_once() -> None:
    queue = read_json(OUTPUT_PATH)
    seen: set[str] = set()
    for group in queue:
        marker = json.dumps(sorted(group["candidate_place_ids"]), sort_keys=True)
        assert marker not in seen
        seen.add(marker)
