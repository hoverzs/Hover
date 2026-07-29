from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_biblical_places_hu_review_queue import BATCH_SIZE, build_queue


QUEUE_PATH = ROOT / "data" / "biblical_places" / "hungarian_review_queue.json"
BATCH_PATH = ROOT / "data" / "biblical_places" / "hungarian_review_batch_001.json"
CATALOG_PATH = ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_hungarian_review_queue_covers_full_catalog_once() -> None:
    queue = read_json(QUEUE_PATH)
    catalog = read_json(CATALOG_PATH)
    queue_ids = [item["place_id"] for item in queue]

    assert len(catalog) == 1309
    assert len(queue) == len(catalog)
    assert len(queue_ids) == len(set(queue_ids))
    assert {item["place_id"] for item in queue} == {item["place_id"] for item in catalog}


def test_hungarian_review_queue_is_deterministic() -> None:
    queue = read_json(QUEUE_PATH)
    rebuilt_queue, rebuilt_batch = build_queue()

    assert rebuilt_queue == queue
    assert rebuilt_batch == read_json(BATCH_PATH)
    assert queue == sorted(queue, key=lambda item: queue.index(item))


def test_first_hungarian_review_batch_shape_and_empty_proposals() -> None:
    batch = read_json(BATCH_PATH)

    assert 0 < len(batch) <= BATCH_SIZE <= 100
    assert batch == read_json(QUEUE_PATH)[: len(batch)]
    for item in batch:
        assert item["review_status"] == "pending"
        assert item["proposed_name_hu"] is None
        assert item["proposed_card_summary_hu"] is None
        assert len(item["representative_passages"]) <= 5


def test_corinth_and_ephesus_manual_content_is_only_carried_into_queue() -> None:
    catalog = {item["place_id"]: item for item in read_json(CATALOG_PATH)}
    queue = {item["place_id"]: item for item in read_json(QUEUE_PATH)}

    for place_id in ("corinth", "ephesus"):
        assert queue[place_id]["current_name_hu"] == catalog[place_id]["name_hu"]
        assert queue[place_id]["current_card_summary_hu"] == catalog[place_id]["card_summary_hu"]
        assert queue[place_id]["proposed_name_hu"] is None
        assert queue[place_id]["proposed_card_summary_hu"] is None
        assert "Meglévő pilot/kézi magyar tartalom" in queue[place_id]["review_notes_hu"]


def test_uncertain_or_duplicate_records_keep_review_warning() -> None:
    queue = read_json(QUEUE_PATH)

    assert any(
        item["identification_status"] in {"possible", "disputed", "unknown"}
        and item["review_notes_hu"]
        for item in queue
    )
    assert any(
        item["review_notes_hu"]
        and "Valószínű duplikátumként jelölte az audit" in item["review_notes_hu"]
        for item in queue
    )
