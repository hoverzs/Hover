"""End-to-end biblical place import pipeline."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from biblical_map_import.download import (
    download_openbible,
    download_pleiades_ids,
    write_download_manifest,
)
from biblical_map_import.merge import build_imported_skeleton, merge_place_records
from biblical_map_import.openbible_loader import (
    identification_status_from_score,
    load_openbible_ancient,
)
from biblical_map_import.pilot_catalog import (
    MANUAL_LOCKED_PLACE_IDS,
    included_pilot_specs,
    pilot_specs_by_id,
)
from biblical_map_import.pleiades_loader import load_pleiades_dir


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "biblical_places"
RAW_DIR = DATA_DIR / "raw"
PILOT_PATH = DATA_DIR / "pilot_places.json"
SOURCES_PATH = DATA_DIR / "sources.json"
PASSAGE_LINKS_PATH = DATA_DIR / "passage_place_links.json"
MANUAL_LOCKS_PATH = DATA_DIR / "manual_locks.json"
REPORT_PATH = DATA_DIR / "import_report.json"

OPENBIBLE_SOURCE_ID = "openbible_geocoding_cc_by_4_0"
PLEIADES_SOURCE_ID_PREFIX = "pleiades_place_"

TODAY = date.today().isoformat()


@dataclass
class ImportReport:
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    imported_place_ids: list[str] = field(default_factory=list)
    preserved_locked_ids: list[str] = field(default_factory=list)
    download: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "warnings": self.warnings,
            "errors": self.errors,
            "imported_place_ids": self.imported_place_ids,
            "preserved_locked_ids": self.preserved_locked_ids,
            "download": self.download,
        }


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected list JSON: {path}")
    return [item for item in raw if isinstance(item, dict)]


def _dump_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _canonical_places_json(places: list[dict[str, Any]]) -> str:
    ordered = sorted(places, key=lambda item: str(item.get("place_id") or ""))
    # Keep primary Jerusalem first for human readability of the pilot file.
    primary = [item for item in ordered if item.get("is_primary_demo_place")]
    rest = [item for item in ordered if not item.get("is_primary_demo_place")]
    stable = primary + rest
    return json.dumps(stable, indent=2, ensure_ascii=False) + "\n"


def ensure_base_sources(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item.get("source_id")): item for item in existing}
    openbible = {
        "source_id": OPENBIBLE_SOURCE_ID,
        "provider": "OpenBible.info Bible Geocoding Data",
        "title": "Bible Geocoding Data (ancient/modern place catalog)",
        "original_language": "en",
        "source_url": "https://github.com/openbibleinfo/Bible-Geocoding-Data",
        "license": "CC-BY-4.0",
        "attribution": "Stephen Smith / OpenBible.info Bible Geocoding Data",
        "retrieved_at": TODAY,
        "source_type": "open_geocoding_dataset",
        "reliability_tier": "aggregated_open_scholarship",
        "notes_hu": (
            "Nyílt CC-BY-4.0 adat. Koordináták és azonosítók forrása; hosszú "
            "forrásszöveget nem másolunk át."
        ),
    }
    by_id[OPENBIBLE_SOURCE_ID] = openbible
    return list(by_id.values())


def ensure_pleiades_source(existing: list[dict[str, Any]], pleiades_id: str) -> list[dict[str, Any]]:
    source_id = f"{PLEIADES_SOURCE_ID_PREFIX}{pleiades_id}"
    by_id = {str(item.get("source_id")): item for item in existing}
    if source_id not in by_id:
        by_id[source_id] = {
            "source_id": source_id,
            "provider": "Pleiades",
            "title": f"Pleiades place {pleiades_id}",
            "original_language": "en",
            "source_url": f"https://pleiades.stoa.org/places/{pleiades_id}",
            "license": "CC-BY-3.0",
            "attribution": (
                "Pleiades contributors; Ancient World Mapping Center and "
                "Institute for the Study of the Ancient World"
            ),
            "retrieved_at": TODAY,
            "source_type": "scholarly_gazetteer",
            "reliability_tier": "scholarly_curated",
            "notes_hu": "Ókori helyazonosítás és névváltozatok kiegészítő forrása.",
        }
    return list(by_id.values())


def default_passage_links() -> list[dict[str, Any]]:
    return [
        {
            "reference": "ApCsel 18,1-18",
            "place_id": "corinth",
            "reason_hu": "Pál korinthusi szolgálatának pilot szakasza.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "ApCsel 19,1-41",
            "place_id": "ephesus",
            "reason_hu": "Pál efezusi szolgálatának pilot helykapcsolata.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "Ef 1,1-14",
            "place_id": "ephesus",
            "reason_hu": "Az efezusi levél címzett gyülekezetéhez kapcsolt hely.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "Mt 2,23",
            "place_id": "nazareth",
            "reason_hu": "Jézus názáreti letelepedésére utaló szakasz.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "Mk 1,21-28",
            "place_id": "capernaum",
            "reason_hu": "A kapernaumi zsinagógai jelenet helykapcsolata.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "ApCsel 2,1-13",
            "place_id": "jerusalem",
            "reason_hu": "A pünkösdi jeruzsálemi esemény helykapcsolata.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "ApCsel 17,16-34",
            "place_id": "athens",
            "reason_hu": "Pál athéni Areopágosz-beszédének helykapcsolata.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "ApCsel 16,11-40",
            "place_id": "philippi",
            "reason_hu": "Pál filippi szolgálatának helykapcsolata.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "ApCsel 17,1-9",
            "place_id": "thessalonica",
            "reason_hu": "Pál thesszalonikai szolgálatának helykapcsolata.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "ApCsel 11,19-30",
            "place_id": "antioch_syria",
            "reason_hu": "A szíriai Antiókhia missziói központjának helykapcsolata.",
            "source_note": "pilot passage index",
        },
        {
            "reference": "ApCsel 28,11-31",
            "place_id": "rome",
            "reason_hu": "Pál római házi őrizetének helykapcsolata.",
            "source_note": "pilot passage index",
        },
    ]


def write_manual_locks() -> None:
    payload = {
        "locked_place_ids": sorted(MANUAL_LOCKED_PLACE_IDS),
        "policy": (
            "Bulk import may fill null fields and union source_ids, but must not "
            "overwrite non-empty protected content fields. review_status must not "
            "be auto-promoted to reviewed/approved."
        ),
    }
    _dump_json(MANUAL_LOCKS_PATH, payload)


def build_place_from_sources(
    spec,
    openbible,
    pleiades_by_id,
    report: ImportReport,
) -> dict[str, Any] | None:
    ob = openbible.get(spec.openbible_id)
    if ob is None:
        report.errors.append(f"Missing OpenBible record for {spec.place_id} ({spec.openbible_id})")
        return None

    pleiades_id = spec.pleiades_id or ob.pleiades_id
    pleiades = pleiades_by_id.get(pleiades_id) if pleiades_id else None

    lat = ob.lat
    lon = ob.lon
    coordinate_source_id = OPENBIBLE_SOURCE_ID
    if (lat is None or lon is None) and pleiades is not None:
        lat = pleiades.lat
        lon = pleiades.lon
        if lat is not None and lon is not None and pleiades_id:
            coordinate_source_id = f"{PLEIADES_SOURCE_ID_PREFIX}{pleiades_id}"

    if lat is None or lon is None:
        report.errors.append(f"No coordinates for {spec.place_id}")
        return None

    ancient_names = [ob.friendly_id]
    if ob.modern_name and ob.modern_name not in ancient_names:
        ancient_names.append(ob.modern_name)
    if pleiades is not None:
        for name in pleiades.names:
            if name not in ancient_names:
                ancient_names.append(name)

    original_names: list[str] = []
    transliterations: list[str] = []
    if pleiades is not None:
        for name in pleiades.attested_names:
            # Keep non-Latin attested forms as original script candidates.
            if any(ord(ch) > 127 for ch in name):
                original_names.append(name)
            else:
                transliterations.append(name)
        for name in pleiades.names:
            if name not in transliterations and name not in ancient_names:
                transliterations.append(name)

    status = identification_status_from_score(ob.identification_score)
    confidence = (
        f"OpenBible azonosítás (score={ob.identification_score}). "
        "Az importált rekord szakmai ellenőrzésre vár; részletes háttérszöveg nincs generálva."
    )
    if spec.antioch_kind == "syria":
        confidence += " Ez a szíriai (Orontész menti) Antiókhia, nem a pisidiai."
    elif spec.antioch_kind == "pisidia":
        confidence += " Ez a pisidiai Antiókhia, nem a szíriai."

    source_ids = [OPENBIBLE_SOURCE_ID]
    if pleiades_id:
        source_ids.append(f"{PLEIADES_SOURCE_ID_PREFIX}{pleiades_id}")

    return build_imported_skeleton(
        spec,
        latitude=float(lat),
        longitude=float(lon),
        ancient_names=ancient_names,
        original_names=original_names,
        transliterations=transliterations,
        openbible_id=ob.openbible_id,
        pleiades_id=pleiades_id,
        wikidata_id=ob.wikidata_id,
        identification_status=status,
        confidence_note_hu=confidence,
        coordinate_source_id=coordinate_source_id,
        source_ids=source_ids,
        modern_name=ob.modern_name or spec.modern_name,
    )


def run_import(
    *,
    dry_run: bool = False,
    download: bool = True,
    force_download: bool = False,
) -> ImportReport:
    report = ImportReport()
    specs = included_pilot_specs()
    openbible_ids = [spec.openbible_id for spec in specs]
    pleiades_ids = [spec.pleiades_id for spec in specs if spec.pleiades_id]

    if download:
        ob_report = download_openbible(RAW_DIR, force=force_download)
        # Seed known pleiades ids even before parsing openbible links.
        pl_report = download_pleiades_ids(RAW_DIR, [pid for pid in pleiades_ids if pid], force=force_download)
        report.download = {
            "openbible": ob_report.as_dict(),
            "pleiades": pl_report.as_dict(),
        }
        write_download_manifest(RAW_DIR / "download_manifest.json", {
            "openbible": ob_report,
            "pleiades": pl_report,
        })
        if ob_report.failed:
            report.warnings.extend(ob_report.failed)
        if pl_report.failed:
            report.warnings.extend(pl_report.failed)

    ancient_path = RAW_DIR / "openbible" / "ancient.jsonl"
    if not ancient_path.exists():
        report.errors.append(f"Missing OpenBible ancient file: {ancient_path}")
        if not dry_run:
            _dump_json(REPORT_PATH, report.as_dict())
        return report

    openbible = load_openbible_ancient(ancient_path, openbible_ids)
    pleiades_by_id = load_pleiades_dir(RAW_DIR / "pleiades")

    existing_places = _load_json_list(PILOT_PATH)
    existing_by_id = {str(item.get("place_id")): item for item in existing_places}
    sources = ensure_base_sources(_load_json_list(SOURCES_PATH))

    # Snapshot locked content for invariance checks.
    locked_before = {
        place_id: deepcopy(existing_by_id[place_id])
        for place_id in MANUAL_LOCKED_PLACE_IDS
        if place_id in existing_by_id
    }

    merged_places: list[dict[str, Any]] = []
    for spec in specs:
        imported = build_place_from_sources(spec, openbible, pleiades_by_id, report)
        if imported is None:
            continue
        if imported.get("pleiades_id"):
            sources = ensure_pleiades_source(sources, str(imported["pleiades_id"]))
        locked = spec.place_id in MANUAL_LOCKED_PLACE_IDS or bool(
            (existing_by_id.get(spec.place_id) or {}).get("curation_lock")
        )
        merged = merge_place_records(existing_by_id.get(spec.place_id), imported, locked=locked)
        # Preserve dense locked content checksum fields.
        if locked and spec.place_id in locked_before:
            before = locked_before[spec.place_id]
            for key in (
                "geography_hu",
                "history_hu",
                "exegetical_notes",
                "card_summary_hu",
                "latitude",
                "longitude",
            ):
                if before.get(key) not in (None, [], ""):
                    merged[key] = deepcopy(before[key])
            report.preserved_locked_ids.append(spec.place_id)
        merged_places.append(merged)
        report.imported_place_ids.append(spec.place_id)

    # Keep any unexpected existing non-pilot records? Pilot should be exactly 10.
    merged_ids = {item["place_id"] for item in merged_places}
    for place_id, record in existing_by_id.items():
        if place_id not in merged_ids and place_id in MANUAL_LOCKED_PLACE_IDS:
            merged_places.append(deepcopy(record))

    if len(merged_places) != 10:
        report.errors.append(f"Expected 10 pilot places, got {len(merged_places)}")

    # Validate locked invariance for detailed prose.
    for place_id, before in locked_before.items():
        after = next((item for item in merged_places if item.get("place_id") == place_id), None)
        if after is None:
            report.errors.append(f"Locked place missing after import: {place_id}")
            continue
        for key in ("geography_hu", "history_hu", "exegetical_notes", "card_summary_hu"):
            if before.get(key) != after.get(key):
                report.errors.append(f"Locked field changed for {place_id}.{key}")

    write_manual_locks()
    passage_links = default_passage_links()
    # Ensure passage targets exist.
    for link in passage_links:
        if link["place_id"] not in {item["place_id"] for item in merged_places}:
            report.errors.append(f"Passage link target missing: {link['place_id']}")

    report.messages.append(f"Prepared {len(merged_places)} pilot places.")
    if dry_run:
        report.messages.append("Dry-run only; JSON outputs were not written.")
        _dump_json(REPORT_PATH, report.as_dict())
        return report

    # Deterministic write
    PILOT_PATH.write_text(_canonical_places_json(merged_places), encoding="utf-8")
    # Keep sources sorted by source_id for idempotency.
    sources_sorted = sorted(sources, key=lambda item: str(item.get("source_id") or ""))
    _dump_json(SOURCES_PATH, sources_sorted)
    _dump_json(PASSAGE_LINKS_PATH, passage_links)
    _dump_json(REPORT_PATH, report.as_dict())
    report.messages.append(f"Wrote {PILOT_PATH}")
    report.messages.append(f"Wrote {SOURCES_PATH}")
    report.messages.append(f"Wrote {PASSAGE_LINKS_PATH}")
    return report


def places_file_fingerprint(path: Path = PILOT_PATH) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
