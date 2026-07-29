from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_biblical_places_duplicate_review import (
    DEFAULT_BATCH_PATH,
    EXPECTED_GROUPS_BY_BATCH,
    apply_reviews,
    validate_batch,
)


DATA_DIR = ROOT / "data" / "biblical_places"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
DUPLICATE_QUEUE_PATH = DATA_DIR / "duplicate_review_queue.json"
BATCH_002_REVIEWED_PATH = DATA_DIR / "duplicate_review_batch_002_reviewed.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_reviewed_duplicate_batch_is_valid() -> None:
    catalog = read_json(CATALOG_PATH)
    batch = validate_batch(DEFAULT_BATCH_PATH, catalog)
    merge_groups = {group["group_id"] for group in batch if group["final_action"] == "merge"}
    keep_groups = {group["group_id"] for group in batch if group["final_action"] == "keep_separate"}

    assert len(batch) == 10
    assert merge_groups == EXPECTED_GROUPS_BY_BATCH[DEFAULT_BATCH_PATH.name]["merge"]
    assert keep_groups == EXPECTED_GROUPS_BY_BATCH[DEFAULT_BATCH_PATH.name]["keep_separate"]


def test_duplicate_review_apply_dry_run_is_safe() -> None:
    report = apply_reviews(DEFAULT_BATCH_PATH, write=False)

    assert report["valid_groups"] == 10
    assert report["merge_decision_count"] == 7
    assert report["keep_separate_count"] == 3
    assert report["catalog_count_after"] in {1302, report["catalog_count_before"]}
    assert report["lost_passage_link_count"] == 0
    assert report["bad_passage_reference_count"] == 0
    assert not report["protected_missing_place_ids"]


def test_reviewed_duplicate_merges_are_applied_to_catalog_and_links() -> None:
    catalog = read_json(CATALOG_PATH)
    ids = {record["place_id"] for record in catalog}
    removed_ids = {"ham_2", "ebron", "ai_3", "ayyah", "aphik", "arad_2", "aroer_4"}
    canonical_ids = {"egypt", "abdon", "ai_1", "aija", "aphek_1", "arad_1", "aroer_3"}
    links = read_json(PASSAGE_LINKS_PATH)
    queue = {group["group_id"]: group for group in read_json(DUPLICATE_QUEUE_PATH)}

    assert len(catalog) <= 1302
    assert removed_ids.isdisjoint(ids)
    assert canonical_ids.issubset(ids)
    assert all(link["place_id"] not in removed_ids for link in links)
    assert len({(link["reference"], link["place_id"]) for link in links}) == len(links)
    expected = EXPECTED_GROUPS_BY_BATCH[DEFAULT_BATCH_PATH.name]
    for group_id in expected["merge"] | expected["keep_separate"]:
        assert queue[group_id]["review_status"] == "reviewed"
    for group_id in expected["merge"]:
        assert queue[group_id]["final_action"] == "merge"
    for group_id in expected["keep_separate"]:
        assert queue[group_id]["final_action"] == "keep_separate"


def test_second_reviewed_duplicate_batch_is_valid_when_present() -> None:
    if not BATCH_002_REVIEWED_PATH.exists():
        return
    catalog = read_json(CATALOG_PATH)
    batch = validate_batch(BATCH_002_REVIEWED_PATH, catalog)
    expected = EXPECTED_GROUPS_BY_BATCH[BATCH_002_REVIEWED_PATH.name]

    assert len(batch) == 10
    assert {group["group_id"] for group in batch if group["final_action"] == "merge"} == expected["merge"]
    assert {group["group_id"] for group in batch if group["final_action"] == "keep_separate"} == expected["keep_separate"]


def test_second_reviewed_duplicate_merges_are_applied_when_present() -> None:
    if not BATCH_002_REVIEWED_PATH.exists():
        return
    catalog = read_json(CATALOG_PATH)
    ids = {record["place_id"] for record in catalog}
    removed_ids = {
        "beersheba_2",
        "sheba_2",
        "eden_2",
        "bethlehem_3",
        "bethsaida_2",
        "leb_kamai",
        "city_of_palms_2",
    }
    canonical_ids = {
        "beersheba_1",
        "beth_eden",
        "bethlehem_2",
        "bethsaida_1",
        "chaldea",
        "city_of_palms_1",
    }
    keep_separate_ids = {
        "babylon_2",
        "babylon_3",
        "bealoth_1",
        "bealoth_2",
        "bezek_1",
        "bezek_2",
        "cush_1",
        "ethiopia",
    }
    links = read_json(PASSAGE_LINKS_PATH)
    queue = {group["group_id"]: group for group in read_json(DUPLICATE_QUEUE_PATH)}
    expected = EXPECTED_GROUPS_BY_BATCH[BATCH_002_REVIEWED_PATH.name]

    assert len(catalog) == 1295
    assert removed_ids.isdisjoint(ids)
    assert canonical_ids.issubset(ids)
    assert keep_separate_ids.issubset(ids)
    assert all(link["place_id"] not in removed_ids for link in links)
    for group_id in expected["merge"] | expected["keep_separate"]:
        assert queue[group_id]["review_status"] == "reviewed"
    for group_id in expected["merge"]:
        assert queue[group_id]["final_action"] == "merge"
    for group_id in expected["keep_separate"]:
        assert queue[group_id]["final_action"] == "keep_separate"
        assert queue[group_id]["recommended_action"] != "merge_probable"


def test_special_alias_risks_are_not_promoted_globally() -> None:
    catalog = {record["place_id"]: record for record in read_json(CATALOG_PATH)}

    assert "Ham" not in catalog["egypt"].get("ancient_names", [])
    assert "Hám" not in catalog["egypt"].get("ancient_names", [])
    assert "Hebron" not in catalog["abdon"].get("ancient_names", [])
    assert "Gaza" not in catalog["aija"].get("ancient_names", [])
    assert {"ham_2"} <= set(catalog["egypt"].get("legacy_place_ids") or [])
    assert {"ebron"} <= set(catalog["abdon"].get("legacy_place_ids") or [])
    assert {"ayyah"} <= set(catalog["aija"].get("legacy_place_ids") or [])
