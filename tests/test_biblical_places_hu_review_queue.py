from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_biblical_places_hu_review_queue import (
    BATCH_SIZE,
    build_batch_002,
    build_queue,
    build_unprocessed_batch,
)


DATA_DIR = ROOT / "data" / "biblical_places"
QUEUE_PATH = DATA_DIR / "hungarian_review_queue.json"
BATCH_PATH = DATA_DIR / "hungarian_review_batch_001.json"
BATCH_002_PATH = DATA_DIR / "hungarian_review_batch_002.json"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
DRAFT_PATH = DATA_DIR / "hungarian_review_batch_001_hu_draft.json"
DRAFT_002_PATH = DATA_DIR / "hungarian_review_batch_002_hu_draft.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_hungarian_review_queue_covers_full_catalog_once() -> None:
    queue = read_json(QUEUE_PATH)
    catalog = read_json(CATALOG_PATH)
    queue_ids = [item["place_id"] for item in queue]

    assert len(catalog) == 1267
    assert len(queue) == len(catalog)
    assert len(queue_ids) == len(set(queue_ids))
    assert {item["place_id"] for item in queue} == {item["place_id"] for item in catalog}


def test_hungarian_review_queue_is_deterministic() -> None:
    queue = read_json(QUEUE_PATH)
    rebuilt_queue, rebuilt_batch = build_queue()
    rebuilt_batch_002 = build_batch_002(rebuilt_queue)

    assert rebuilt_queue == queue
    assert rebuilt_batch == read_json(BATCH_PATH)
    assert rebuilt_batch_002 == read_json(BATCH_002_PATH)


def test_first_hungarian_review_batch_shape_and_applied_proposals() -> None:
    batch = read_json(BATCH_PATH)
    draft = read_json(DRAFT_PATH)
    catalog = {item["place_id"]: item for item in read_json(CATALOG_PATH)}
    draft_by_id = {item["place_id"]: item for item in draft}

    assert len(batch) == BATCH_SIZE == 100
    assert len(draft) == BATCH_SIZE
    assert len({item["place_id"] for item in draft}) == BATCH_SIZE
    assert batch == read_json(QUEUE_PATH)[: len(batch)]
    for item in batch:
        place_id = item["place_id"]
        if place_id in draft_by_id and catalog[place_id]["review_status"] == "draft":
            draft_item = draft_by_id[place_id]
            assert item["review_status"] == "draft"
            assert item["proposed_name_hu"] == draft_item["proposed_name_hu"]
            assert item["proposed_card_summary_hu"] == draft_item["proposed_card_summary_hu"]
            assert catalog[place_id]["name_hu"] == draft_item["proposed_name_hu"]
            assert catalog[place_id]["card_summary_hu"] == draft_item["proposed_card_summary_hu"]
        else:
            assert item["current_name_hu"] == catalog[place_id]["name_hu"]
            assert item["current_card_summary_hu"] == catalog[place_id]["card_summary_hu"]
        assert len(item["representative_passages"]) <= 5


def test_corinth_and_ephesus_manual_content_is_carried_into_queue() -> None:
    catalog = {item["place_id"]: item for item in read_json(CATALOG_PATH)}
    queue = {item["place_id"]: item for item in read_json(QUEUE_PATH)}

    for place_id in ("corinth", "ephesus"):
        assert queue[place_id]["current_name_hu"] == catalog[place_id]["name_hu"]
        assert queue[place_id]["current_card_summary_hu"] == catalog[place_id]["card_summary_hu"]
        assert "pilot" in (queue[place_id]["review_notes_hu"] or "")


def test_second_hungarian_review_batch_shape_and_applied_proposals() -> None:
    queue = read_json(QUEUE_PATH)
    batch_001 = read_json(BATCH_PATH)
    batch_002 = read_json(BATCH_002_PATH)
    draft = read_json(DRAFT_002_PATH)
    catalog = {item["place_id"]: item for item in read_json(CATALOG_PATH)}
    draft_by_id = {item["place_id"]: item for item in draft}
    batch_001_ids = {item["place_id"] for item in batch_001}
    batch_002_ids = [item["place_id"] for item in batch_002]

    assert len(batch_002) == BATCH_SIZE == 100
    assert len(draft) == BATCH_SIZE
    assert len({item["place_id"] for item in draft}) == BATCH_SIZE
    assert batch_002 == queue[BATCH_SIZE : BATCH_SIZE * 2]
    assert len(batch_002_ids) == len(set(batch_002_ids))
    assert not batch_001_ids.intersection(batch_002_ids)
    for item in batch_002:
        place_id = item["place_id"]
        if place_id in draft_by_id and catalog[place_id]["review_status"] == "draft":
            draft_item = draft_by_id[place_id]
            assert item["review_status"] == "draft"
            assert item["proposed_name_hu"] == draft_item["proposed_name_hu"]
            assert item["proposed_card_summary_hu"] == draft_item["proposed_card_summary_hu"]
            assert catalog[place_id]["name_hu"] == draft_item["proposed_name_hu"]
            assert catalog[place_id]["card_summary_hu"] == draft_item["proposed_card_summary_hu"]
        else:
            assert item["current_name_hu"] == catalog[place_id]["name_hu"]
            assert item["current_card_summary_hu"] == catalog[place_id]["card_summary_hu"]


def test_unprocessed_batch_uses_current_catalog_state() -> None:
    queue = read_json(QUEUE_PATH)
    catalog = {item["place_id"]: item for item in read_json(CATALOG_PATH)}
    batch = build_unprocessed_batch(queue, limit=25)
    expected = [
        item
        for item in queue
        if not (item.get("current_name_hu") and item.get("current_card_summary_hu"))
    ][:25]
    batch_ids = [item["place_id"] for item in batch]

    assert batch == expected
    assert len(batch) == min(25, len(expected))
    assert len(batch_ids) == len(set(batch_ids))
    for item in batch:
        place = catalog[item["place_id"]]
        assert not (place.get("name_hu") and place.get("card_summary_hu"))
        assert item["review_status"] == "pending"
        assert item["proposed_name_hu"] is None
        assert item["proposed_card_summary_hu"] is None


def test_uncertain_or_duplicate_records_keep_review_warning() -> None:
    queue = read_json(QUEUE_PATH)

    assert any(
        item["identification_status"] in {"possible", "disputed", "unknown"}
        and item["review_notes_hu"]
        for item in queue
    )
    assert any(
        item["review_notes_hu"]
        and "duplik" in item["review_notes_hu"].casefold()
        for item in queue
    )
