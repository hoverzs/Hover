from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bible_engine.greek_lexicon_repository import resolve_tbesg_database_path
from bible_engine.greek_token_repository import resolve_tagnt_database_path
from bible_engine.lexicon_hu import load_hungarian_lexicon
from bible_engine.tbesg_parser import normalize_greek_strong_id
from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry, get_sqlite_lexicon_entry


ROOT = Path(__file__).parents[1]
LEXICON_HU_SAMPLE_PATH = ROOT / "bible_engine" / "data" / "lexicon_hu_sample.json"
DEFAULT_LEXICON_HU_PATH = ROOT / "bible_engine" / "data" / "lexicon_hu.json"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "STEPBible TBESG"
DEFAULT_TRANSLATION_METHOD = "ai_assisted"
DEFAULT_REVIEW_STATUS = "draft"
ALLOWED_REVIEW_STATUSES = frozenset({"draft", "reviewed"})
ALLOWED_TRANSLATION_METHODS = frozenset({"ai_assisted", "human"})
EXPORT_RECORD_FIELDS = frozenset(
    {
        "strong_id",
        "lemma",
        "transliteration",
        "morph",
        "gloss_en",
        "meaning_plain_en",
        "nt_frequency",
        "primary_gloss_hu",
        "senses_hu",
        "note_hu",
        "review_status",
        "translation_method",
        "source_name",
        "source_version",
    }
)
PLACEHOLDER_RE = re.compile(r"\b(?:TODO|TBD|fordítandó|forditando)\b", re.IGNORECASE)


@dataclass(frozen=True)
class LexiconExportReport:
    output_path: str
    records_exported: int
    limit: int
    offset: int
    order_by: str
    warnings: tuple[str, ...]
    first_strong_id: str | None
    last_strong_id: str | None


@dataclass(frozen=True)
class LexiconImportReport:
    input_path: str
    output_path: str
    records_read: int
    records_imported: int
    records_skipped: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def export_untranslated_lexicon_batch(
    output_path: str | Path,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "nt_frequency",
    tbesg_database_path: str | Path | None = None,
    tagnt_database_path: str | Path | None = None,
) -> LexiconExportReport:
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    if offset < 0:
        raise ValueError("offset must not be negative.")
    if order_by not in {"nt_frequency", "strong_id"}:
        raise ValueError("order_by must be 'nt_frequency' or 'strong_id'.")

    tbesg_database = (
        Path(tbesg_database_path)
        if tbesg_database_path is not None
        else resolve_tbesg_database_path()
    )
    if not tbesg_database.exists():
        raise FileNotFoundError(f"TBESG SQLite database not found: {tbesg_database}")

    warnings: list[str] = []
    frequencies: dict[str, int] = {}
    if order_by == "nt_frequency":
        tagnt_database = (
            Path(tagnt_database_path)
            if tagnt_database_path is not None
            else resolve_tagnt_database_path()
        )
        if tagnt_database is not None and tagnt_database.exists():
            frequencies = _strong_frequencies(tagnt_database)
        else:
            warnings.append(
                "TAGNT database unavailable; exported records are ordered by strong_id."
            )

    translated = _existing_hungarian_strong_ids()
    entries = [
        entry
        for entry in _all_tbesg_entries(tbesg_database)
        if entry.strong_id not in translated
    ]

    if order_by == "nt_frequency" and frequencies:
        entries.sort(key=lambda entry: (-frequencies.get(entry.strong_id, 0), entry.strong_id))
    else:
        entries.sort(key=lambda entry: entry.strong_id)

    selected = entries[offset : offset + limit]
    records = [_export_record(entry, frequencies.get(entry.strong_id, 0)) for entry in selected]
    created_at = datetime.now(UTC).isoformat()
    data = {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "source": SOURCE_NAME,
        "batch": {
            "limit": limit,
            "offset": offset,
            "order_by": order_by,
        },
        "records": records,
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return LexiconExportReport(
        output_path=str(output),
        records_exported=len(records),
        limit=limit,
        offset=offset,
        order_by=order_by,
        warnings=tuple(warnings),
        first_strong_id=records[0]["strong_id"] if records else None,
        last_strong_id=records[-1]["strong_id"] if records else None,
    )


def import_hungarian_lexicon_batch(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> LexiconImportReport:
    input_file = Path(input_path)
    output_file = Path(output_path) if output_path is not None else DEFAULT_LEXICON_HU_PATH
    data = _read_translation_batch(input_file)
    records = data["records"]
    base_entries = _load_output_entries(output_file)
    entries_by_strong = {
        normalize_greek_strong_id(str(entry["strong_id"])): dict(entry)
        for entry in base_entries
    }

    errors: list[str] = []
    warnings: list[str] = []
    records_imported = 0
    records_skipped = 0
    seen: set[str] = set()

    for index, raw_record in enumerate(records, start=1):
        try:
            record = _validated_translation_record(raw_record, index)
            strong_id = record["strong_id"]
            if strong_id in seen:
                raise ValueError(f"duplicate strong_id in batch: {strong_id}")
            seen.add(strong_id)
            _validate_against_tbesg(record, index)
        except ValueError as error:
            records_skipped += 1
            errors.append(f"record #{index}: {error}")
            continue

        existing = entries_by_strong.get(strong_id)
        if existing is not None:
            if existing.get("review_status") == "reviewed" and record["review_status"] == "draft":
                records_skipped += 1
                warnings.append(
                    f"record #{index}: reviewed entry {strong_id} was not overwritten by draft."
                )
                continue
            if _existing_entry_matches_record(existing, record):
                records_skipped += 1
                continue

        entries_by_strong[strong_id] = _hungarian_output_entry(record)
        records_imported += 1

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_entries = sorted(entries_by_strong.values(), key=lambda entry: entry["strong_id"])
    output_file.write_text(
        json.dumps(output_entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return LexiconImportReport(
        input_path=str(input_file),
        output_path=str(output_file),
        records_read=len(records),
        records_imported=records_imported,
        records_skipped=records_skipped,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _all_tbesg_entries(database_path: Path) -> list[SQLiteGreekLexiconEntry]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT strong_id
            FROM greek_lexicon
            ORDER BY strong_id
            """
        ).fetchall()
    entries = []
    for row in rows:
        entry = get_sqlite_lexicon_entry(database_path, str(row[0]))
        if entry is not None:
            entries.append(entry)
    return entries


def _strong_frequencies(database_path: Path) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT strong_id, COUNT(*) AS frequency
            FROM greek_tokens
            WHERE strong_id IS NOT NULL AND strong_id != ''
            GROUP BY strong_id
            """
        ).fetchall()

    frequencies: dict[str, int] = {}
    for strong_id, frequency in rows:
        try:
            normalized = normalize_greek_strong_id(str(strong_id))
        except ValueError:
            continue
        frequencies[normalized] = frequencies.get(normalized, 0) + int(frequency)
    return frequencies


def _existing_hungarian_strong_ids() -> set[str]:
    path = DEFAULT_LEXICON_HU_PATH if DEFAULT_LEXICON_HU_PATH.exists() else LEXICON_HU_SAMPLE_PATH
    if not path.exists():
        return set()
    return set(load_hungarian_lexicon(path))


def _export_record(entry: SQLiteGreekLexiconEntry, nt_frequency: int) -> dict[str, object]:
    return {
        "strong_id": entry.strong_id,
        "lemma": entry.lemma,
        "transliteration": entry.transliteration or "",
        "morph": entry.morph or "",
        "gloss_en": entry.gloss or "",
        "meaning_plain_en": _trim_meaning(entry.meaning_plain or ""),
        "nt_frequency": nt_frequency,
        "primary_gloss_hu": "",
        "senses_hu": [],
        "note_hu": "",
        "review_status": DEFAULT_REVIEW_STATUS,
        "translation_method": DEFAULT_TRANSLATION_METHOD,
        "source_name": SOURCE_NAME,
        "source_version": entry.source_version,
    }


def _trim_meaning(value: str, limit: int = 2500) -> str:
    compact = value.strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _read_translation_batch(input_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid translation batch JSON: {error.msg}.") from error

    if not isinstance(data, dict):
        raise ValueError("Invalid translation batch JSON: root value must be an object.")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {data.get('schema_version')!r}.")
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("Invalid translation batch JSON: records must be a list.")
    return data


def _load_output_entries(output_path: Path) -> list[dict[str, Any]]:
    source = output_path if output_path.exists() else None
    if source is None and output_path == DEFAULT_LEXICON_HU_PATH and LEXICON_HU_SAMPLE_PATH.exists():
        source = LEXICON_HU_SAMPLE_PATH
    if source is None:
        return []

    raw_entries = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw_entries, list):
        raise ValueError(f"Invalid Hungarian lexicon JSON: {source}")
    return [dict(entry) for entry in raw_entries if isinstance(entry, dict)]


def _validated_translation_record(raw_record: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw_record, dict):
        raise ValueError("record must be an object")
    unknown = set(raw_record) - EXPORT_RECORD_FIELDS
    missing = EXPORT_RECORD_FIELDS - set(raw_record)
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"missing fields: {', '.join(sorted(missing))}")

    strong_id = normalize_greek_strong_id(str(raw_record["strong_id"]))
    lemma = _required_text(raw_record["lemma"], "lemma")
    primary_gloss = _required_text(raw_record["primary_gloss_hu"], "primary_gloss_hu")
    senses = raw_record["senses_hu"]
    if not isinstance(senses, list) or not senses:
        raise ValueError("senses_hu must contain at least one value")
    senses_hu = tuple(_required_text(value, "senses_hu") for value in senses)
    _reject_placeholders(primary_gloss, "primary_gloss_hu")
    for sense in senses_hu:
        _reject_placeholders(sense, "senses_hu")
    note = str(raw_record["note_hu"]).strip()
    if note:
        _reject_placeholders(note, "note_hu")

    review_status = str(raw_record["review_status"]).strip()
    if review_status not in ALLOWED_REVIEW_STATUSES:
        raise ValueError("review_status must be 'draft' or 'reviewed'")
    translation_method = str(raw_record["translation_method"]).strip()
    if translation_method not in ALLOWED_TRANSLATION_METHODS:
        raise ValueError("translation_method must be 'ai_assisted' or 'human'")
    source_name = str(raw_record["source_name"]).strip()
    if source_name != SOURCE_NAME:
        raise ValueError("source_name must be STEPBible TBESG")

    return {
        **raw_record,
        "strong_id": strong_id,
        "lemma": unicodedata.normalize("NFC", lemma),
        "primary_gloss_hu": primary_gloss,
        "senses_hu": senses_hu,
        "note_hu": note,
        "review_status": review_status,
        "translation_method": translation_method,
        "source_name": source_name,
    }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return unicodedata.normalize("NFC", value.strip())


def _reject_placeholders(value: str, field_name: str) -> None:
    if PLACEHOLDER_RE.search(value):
        raise ValueError(f"{field_name} contains a placeholder value")


def _validate_against_tbesg(record: dict[str, Any], index: int) -> None:
    tbesg_entry = get_sqlite_lexicon_entry(resolve_tbesg_database_path(), record["strong_id"])
    if tbesg_entry is None:
        raise ValueError(f"TBESG source record not found: {record['strong_id']}")
    if unicodedata.normalize("NFC", tbesg_entry.lemma) != record["lemma"]:
        raise ValueError(
            f"lemma mismatch for {record['strong_id']}: {record['lemma']!r} != {tbesg_entry.lemma!r}"
        )


def _hungarian_output_entry(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "strong_id": record["strong_id"],
        "lemma": record["lemma"],
        "primary_gloss": record["primary_gloss_hu"],
        "senses": list(record["senses_hu"]),
        "note": record["note_hu"] or None,
        "source": f"{record['source_name']} alapján készített magyar munkaváltozat",
        "review_status": record["review_status"],
        "translation_method": record["translation_method"],
        "source_name": record["source_name"],
        "source_version": record["source_version"],
    }


def _existing_entry_matches_record(existing: dict[str, Any], record: dict[str, Any]) -> bool:
    return (
        normalize_greek_strong_id(str(existing.get("strong_id", ""))) == record["strong_id"]
        and str(existing.get("lemma", "")).strip() == record["lemma"]
        and str(existing.get("primary_gloss", "")).strip() == record["primary_gloss_hu"]
        and tuple(existing.get("senses", ())) == tuple(record["senses_hu"])
        and (existing.get("note") or "") == record["note_hu"]
        and existing.get("review_status") == record["review_status"]
    )
