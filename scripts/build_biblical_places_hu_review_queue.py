from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "biblical_places"
CATALOG_PATH = DATA_DIR / "biblical_places_catalog.json"
PILOT_PATH = DATA_DIR / "pilot_places.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
AUDIT_REPORT_PATH = DATA_DIR / "audit_report.json"
QUEUE_PATH = DATA_DIR / "hungarian_review_queue.json"
BATCH_001_PATH = DATA_DIR / "hungarian_review_batch_001.json"
BATCH_002_PATH = DATA_DIR / "hungarian_review_batch_002.json"
DOC_PATH = ROOT / "docs" / "biblical_places_hungarian_review.md"

BATCH_SIZE = 100
HIGH_CONFIDENCE_STATUSES = {"certain", "probable"}
LOW_CONFIDENCE_STATUSES = {"possible", "disputed", "unknown"}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def passage_stats(links: list[dict[str, Any]]) -> tuple[Counter[str], dict[str, list[str]]]:
    counts: Counter[str] = Counter()
    references: dict[str, list[str]] = defaultdict(list)
    for link in links:
        place_id = str(link.get("place_id") or "").strip()
        reference = str(link.get("reference") or "").strip()
        if not place_id or not reference:
            continue
        counts[place_id] += 1
        if len(references[place_id]) < 5:
            references[place_id].append(reference)
    return counts, {place_id: stable_unique(items)[:5] for place_id, items in references.items()}


def audit_duplicate_place_ids(audit_report: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for finding in audit_report.get("findings") or []:
        if finding.get("category") != "probable_duplicate_place":
            continue
        object_id = str(finding.get("object_id") or "")
        for place_id in object_id.split("/"):
            cleaned = place_id.strip()
            if cleaned:
                result.add(cleaned)
    return result


def review_notes_for(place: dict[str, Any], *, pilot_ids: set[str], probable_duplicates: set[str]) -> str | None:
    notes: list[str] = []
    place_id = str(place.get("place_id") or "")
    status = str(place.get("identification_status") or "")
    if place_id in pilot_ids and (place.get("name_hu") or place.get("card_summary_hu")):
        notes.append("Meglévő pilot/kézi magyar tartalom; csak ellenőrzés után módosítsd.")
    if status in LOW_CONFIDENCE_STATUSES:
        notes.append("Bizonytalan vagy vitatott azonosítás; a magyar név és leírás szakmai ellenőrzést igényel.")
    if place_id in probable_duplicates:
        notes.append("Valószínű duplikátumként jelölte az audit; összevonás előtt ellenőrizd az azonosítást.")
    return " ".join(notes) or None


def existing_draft_reviews() -> dict[str, dict[str, Any]]:
    existing_queue = read_json(QUEUE_PATH, [])
    if not isinstance(existing_queue, list):
        return {}
    return {
        str(item.get("place_id") or ""): item
        for item in existing_queue
        if isinstance(item, dict)
        and item.get("review_status") == "draft"
        and str(item.get("proposed_name_hu") or "").strip()
        and str(item.get("proposed_card_summary_hu") or "").strip()
    }


def priority_key(item: dict[str, Any], *, pilot_order: dict[str, int]) -> tuple[Any, ...]:
    place_id = str(item.get("place_id") or "")
    status = str(item.get("identification_status") or "")
    has_modern = bool(item.get("modern_name"))
    return (
        -int(item.get("passage_count") or 0),
        0 if place_id in pilot_order else 1,
        pilot_order.get(place_id, 999_999),
        0 if status == "certain" else 1 if status == "probable" else 2,
        0 if has_modern else 1,
        str(item.get("name_hu") or item.get("name_en") or "").casefold(),
        place_id,
    )


def build_queue() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    catalog = read_json(CATALOG_PATH, [])
    pilot_places = read_json(PILOT_PATH, [])
    links = read_json(PASSAGE_LINKS_PATH, [])
    audit_report = read_json(AUDIT_REPORT_PATH, {})

    pilot_ids = {str(place.get("place_id") or "") for place in pilot_places if place.get("place_id")}
    pilot_order = {
        str(place.get("place_id") or ""): index
        for index, place in enumerate(pilot_places)
        if place.get("place_id")
    }
    counts, representative_refs = passage_stats(links)
    probable_duplicates = audit_duplicate_place_ids(audit_report)
    draft_reviews = existing_draft_reviews()

    by_place_id: dict[str, dict[str, Any]] = {}
    for place in catalog:
        place_id = str(place.get("place_id") or "").strip()
        if not place_id or place_id in by_place_id:
            continue
        item = {
            "place_id": place_id,
            "name_en": place.get("name_en"),
            "ancient_names": place.get("ancient_names") or [],
            "original_names": place.get("original_names") or [],
            "transliterations": place.get("transliterations") or [],
            "modern_name": place.get("modern_name"),
            "modern_country": place.get("modern_country"),
            "region_hu": place.get("region_hu"),
            "ancient_region": place.get("ancient_region"),
            "identification_status": place.get("identification_status"),
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "passage_count": counts.get(place_id, 0),
            "representative_passages": representative_refs.get(place_id, []),
            "source_ids": place.get("source_ids") or [],
            "current_name_hu": place.get("name_hu"),
            "current_card_summary_hu": place.get("card_summary_hu"),
            "proposed_name_hu": None,
            "proposed_card_summary_hu": None,
            "review_status": "pending",
            "review_notes_hu": review_notes_for(
                place,
                pilot_ids=pilot_ids,
                probable_duplicates=probable_duplicates,
            ),
        }
        draft_review = draft_reviews.get(place_id)
        if draft_review is not None:
            item["proposed_name_hu"] = str(draft_review["proposed_name_hu"]).strip()
            item["proposed_card_summary_hu"] = str(
                draft_review["proposed_card_summary_hu"]
            ).strip()
            item["review_status"] = "draft"
            item["review_notes_hu"] = draft_review.get("review_notes_hu")
        by_place_id[place_id] = item

    queue = sorted(by_place_id.values(), key=lambda item: priority_key(item, pilot_order=pilot_order))
    return queue, queue[:BATCH_SIZE]


def build_batch_002(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return queue[BATCH_SIZE : BATCH_SIZE * 2]


def write_documentation(queue_count: int, batch_count: int) -> None:
    DOC_PATH.write_text(
        "\n".join(
            [
                "# Bibliai helyek magyarítási munkalistája",
                "",
                f"- Teljes munkalista: `{QUEUE_PATH.relative_to(ROOT)}` ({queue_count} rekord)",
                f"- Első feldolgozási köteg: `{BATCH_001_PATH.relative_to(ROOT)}` ({batch_count} rekord)",
                "",
                "## Prioritási szabály",
                "",
                "A rendezés determinisztikus. Elöl állnak a legtöbb bibliai hivatkozással rendelkező helyek, ezen belül a pilotban szereplő rekordok, majd a biztosabb azonosítású és mai helyhez kapcsolható rekordok. A bizonytalan, vitatott vagy audit által valószínű duplikátumnak jelölt rekordok nem vesznek el, de `review_notes_hu` figyelmeztetést kapnak.",
                "",
                "## Későbbi magyar kártyaleírás szabálya",
                "",
                "- Legfeljebb 1-2 rövid mondat legyen.",
                "- Elsősorban az ókori hely szerepét és a mai azonosítást tartalmazza.",
                "- Ne legyen esszészerű.",
                "- Ne ismételje fölöslegesen a nevet, országot és koordinátát.",
                "- Bizonytalan azonosítást ne állítson biztos tényként.",
                "- Csak ellenőrzött strukturált adatra és forrásokra támaszkodjon.",
                "",
                "A script nem ír vissza a teljes katalógusba, és nem tölti ki automatikusan a javasolt magyar mezőket.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Hungarian review queue for biblical places.")
    parser.add_argument("--check", action="store_true", help="Fail if generated files would change.")
    args = parser.parse_args()

    queue, batch = build_queue()
    batch_002 = build_batch_002(queue)
    outputs = {
        QUEUE_PATH: queue,
        BATCH_001_PATH: batch,
        BATCH_002_PATH: batch_002,
    }
    if args.check:
        changed = [
            str(path)
            for path, payload in outputs.items()
            if not path.exists()
            or path.read_text(encoding="utf-8")
            != json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ]
        expected_doc = DOC_PATH.exists()
        if changed or not expected_doc:
            print(json.dumps({"changed": changed, "documentation_exists": expected_doc}, ensure_ascii=False, indent=2))
            return 2
        print("Hungarian review queue idempotency check passed.")
        return 0

    for path, payload in outputs.items():
        write_json(path, payload)
    write_documentation(len(queue), len(batch))
    print(
        json.dumps(
            {
                "queue_count": len(queue),
                "batch_001_count": len(batch),
                "batch_002_count": len(batch_002),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
