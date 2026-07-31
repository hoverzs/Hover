from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biblical_map_import.merge import clamp_review_status, merge_place_records
from biblical_map_import.openbible_loader import load_openbible_ancient
from biblical_map_import.pilot_catalog import (
    MANUAL_LOCKED_PLACE_IDS,
    included_pilot_specs,
    resolve_places_by_hungarian_name,
)
from biblical_map_import.pipeline import (
    PILOT_PATH,
    places_file_fingerprint,
    run_import,
)


def test_pilot_catalog_has_ten_included_places() -> None:
    specs = included_pilot_specs()
    assert len(specs) == 10
    assert {spec.place_id for spec in specs} == {
        "jerusalem",
        "nazareth",
        "capernaum",
        "corinth",
        "ephesus",
        "athens",
        "philippi",
        "thessalonica",
        "antioch_syria",
        "rome",
    }


def test_antioch_hungarian_name_is_ambiguous() -> None:
    matches = resolve_places_by_hungarian_name("Antiókhia")
    kinds = {spec.antioch_kind for spec in matches}
    assert kinds == {"syria", "pisidia"}


def test_merge_preserves_locked_nonempty_fields() -> None:
    existing = {
        "place_id": "corinth",
        "card_summary_hu": "KEZI",
        "geography_hu": "KEZI GEO",
        "source_ids": ["pleiades_corinth_570182"],
        "review_status": "needs_review",
        "openbible_id": None,
    }
    imported = {
        "place_id": "corinth",
        "card_summary_hu": "IMPORT",
        "geography_hu": "IMPORT GEO",
        "source_ids": ["openbible_geocoding_cc_by_4_0"],
        "review_status": "approved",
        "openbible_id": "a6f437a",
    }
    merged = merge_place_records(existing, imported, locked=True)
    assert merged["card_summary_hu"] == "KEZI"
    assert merged["geography_hu"] == "KEZI GEO"
    assert merged["openbible_id"] == "a6f437a"
    assert set(merged["source_ids"]) == {
        "pleiades_corinth_570182",
        "openbible_geocoding_cc_by_4_0",
    }
    assert merged["review_status"] == "needs_review"


def test_review_status_is_not_auto_promoted() -> None:
    assert clamp_review_status("prototype", "approved") == "needs_review"
    assert clamp_review_status("reviewed", "approved") == "reviewed"


def test_openbible_loader_reads_pilot_ids() -> None:
    path = ROOT / "data" / "biblical_places" / "raw" / "openbible" / "ancient.jsonl"
    if not path.exists():
        return
    found = load_openbible_ancient(path, ["a1fe6e7", "ae41ab4", "a6c704a"])
    assert found["a1fe6e7"].friendly_id == "Athens"
    assert found["ae41ab4"].friendly_id == "Antioch 1"
    assert found["a6c704a"].friendly_id == "Antioch 2"
    assert found["a1fe6e7"].lat is not None
    assert found["a1fe6e7"].lon is not None


def test_import_dry_run_and_locked_invariance(tmp_path: Path, monkeypatch) -> None:
    # Use real data dir files; ensure locked snapshots remain stable conceptually.
    before = None
    if PILOT_PATH.exists():
        places = json.loads(PILOT_PATH.read_text(encoding="utf-8"))
        before = {
            item["place_id"]: deepcopy(item)
            for item in places
            if item.get("place_id") in MANUAL_LOCKED_PLACE_IDS
        }
    report = run_import(dry_run=True, download=False)
    assert not report.errors or "Missing OpenBible" in " ".join(report.errors)
    if before and not report.errors:
        # Dry-run does not write; locked snapshot unchanged on disk.
        after_places = json.loads(PILOT_PATH.read_text(encoding="utf-8"))
        after = {
            item["place_id"]: item
            for item in after_places
            if item.get("place_id") in MANUAL_LOCKED_PLACE_IDS
        }
        for place_id, record in before.items():
            assert after[place_id]["card_summary_hu"] == record["card_summary_hu"]
            assert after[place_id]["geography_hu"] == record["geography_hu"]
