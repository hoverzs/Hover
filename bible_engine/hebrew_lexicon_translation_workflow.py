from __future__ import annotations

import html
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from bible_engine.hebrew_lexicon_hu import (
    DEFAULT_HEBREW_LEXICON_HU_PATH,
    load_hebrew_hungarian_lexicon,
)
from bible_engine.hebrew_lexicon_repository import normalize_hebrew_strong_id
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH, DEFAULT_TBESH_DATABASE_PATH
from bible_engine.paths import DATA_DIR, GENERATED_DATA_DIR


SCHEMA_VERSION = "1.0"
SOURCE_NAME = "STEPBible TBESH"
DEFAULT_BATCH_DIR = DATA_DIR / "hebrew_translation_batches"
DEFAULT_PILOT_BATCH_PATH = DEFAULT_BATCH_DIR / "hebrew_lexicon_batch_0001.json"
DEFAULT_LANGUAGE_AUDIT_PATH = GENERATED_DATA_DIR / "tbesh_language_normalization_audit.json"
DEFAULT_BATCH_AUDIT_PATH = GENERATED_DATA_DIR / "hebrew_lexicon_batch_0001_audit.json"
THEOLOGICAL_TERMS = {
    "H0306",
    "H0410",
    "H0430",
    "H3068",
    "H3068G",
    "H7307",
    "H1285",
    "H2617",
    "H6666",
    "H7965",
}
ENGLISH_SENTENCE_RE = re.compile(r"\b(?:the|and|of|to|with|from|for|that|which|this|be|is|are)\b", re.IGNORECASE)
HTML_RE = re.compile(r"<[^>]+>")
MARKDOWN_RE = re.compile(r"[*_`#\[\]]")
HUNGARIAN_ACCENT_RE = re.compile(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")
WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]+")
ENGLISH_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "been",
    "being",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "may",
    "not",
    "of",
    "on",
    "or",
    "that",
    "the",
    "these",
    "this",
    "those",
    "to",
    "was",
    "were",
    "which",
    "with",
}
HUNGARIAN_FUNCTION_WORDS = {
    "a",
    "az",
    "és",
    "vagy",
    "hogy",
    "is",
    "nem",
    "de",
    "mint",
    "mely",
    "amely",
    "valamely",
    "való",
    "valamint",
    "túl",
    "kívül",
    "alapján",
    "gyakran",
    "jelöl",
    "jelölhet",
    "kifejez",
    "kifejezhet",
    "használatos",
    "értelemben",
}
TECHNICAL_TERMS = {
    "qal",
    "piel",
    "nifal",
    "niphal",
    "hifil",
    "hiphil",
    "hitpael",
    "strong",
    "step",
    "lemma",
    "qere",
    "ketiv",
}


@dataclass(frozen=True)
class HebrewLexiconBatchReport:
    output_path: str
    records_exported: int
    limit: int
    offset: int
    first_strong_id: str | None
    last_strong_id: str | None


@dataclass(frozen=True)
class HebrewLexiconImportReport:
    input_path: str
    output_path: str
    records_read: int
    records_imported: int
    records_skipped: int
    errors: tuple[str, ...]


def audit_tbesh_database(database_path: str | Path = DEFAULT_TBESH_DATABASE_PATH) -> dict[str, object]:
    with sqlite3.connect(database_path) as connection:
        total = int(connection.execute("SELECT COUNT(*) FROM lexicon_entries").fetchone()[0])
        languages = {
            (row[0] or "unspecified"): int(row[1])
            for row in connection.execute("SELECT language, COUNT(*) FROM lexicon_entries GROUP BY language")
        }
        duplicate_strongs = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT strong_id FROM lexicon_entries GROUP BY strong_id HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
        )
        extended = int(
            connection.execute(
                "SELECT COUNT(*) FROM lexicon_entries WHERE strong_id GLOB 'H[0-9][0-9][0-9][0-9][A-Z]'"
            ).fetchone()[0]
        )
    return {
        "total_records": total,
        "language_counts": languages,
        "duplicate_strong_records": duplicate_strongs,
        "extended_strong_records": extended,
        "translation_fields": ["hebrew", "transliteration", "morph", "gloss", "meaning"],
        "short_gloss_fields": ["gloss"],
        "long_guidance_fields": ["meaning"],
        "technical_fields": ["estrong", "dstrong", "ustrong", "morph", "raw_fields_json"],
    }


def build_tbesh_language_normalization_audit(
    output_path: str | Path = DEFAULT_LANGUAGE_AUDIT_PATH,
    *,
    tahot_database_path: str | Path = DEFAULT_TAHOT_DATABASE_PATH,
    tbesh_database_path: str | Path = DEFAULT_TBESH_DATABASE_PATH,
) -> dict[str, object]:
    entries = _raw_tbesh_entries(tbesh_database_path)
    language_counts = _core_language_counts(tahot_database_path)
    records = [
        _resolve_language_record(entry, language_counts.get(strong_id, {"hebrew": 0, "aramaic": 0}))
        for strong_id, entry in entries.items()
    ]
    summary = {
        "total_records": len(records),
        "original_language_counts": dict(Counter(record["original_language"] for record in records)),
        "resolved_language_counts": dict(Counter(record["resolved_language"] for record in records)),
        "resolved_from_tahot_occurrences": sum(
            1 for record in records if record["evidence"] == "tahot_core_token_language"
        ),
        "still_unspecified": sum(1 for record in records if record["resolved_language"] == "unspecified"),
        "mixed_records": sum(1 for record in records if record["resolved_language"] == "mixed"),
    }
    data = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "priority_order": [
            "explicit TBESH language",
            "actual TAHOT core-token occurrence language",
            "documented Strong/STEP metadata",
            "unspecified",
        ],
        "summary": summary,
        "records": records,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def build_hebrew_lexicon_priority_audit(
    output_path: str | Path = GENERATED_DATA_DIR / "hebrew_lexicon_translation_priority.json",
    *,
    tahot_database_path: str | Path = DEFAULT_TAHOT_DATABASE_PATH,
    tbesh_database_path: str | Path = DEFAULT_TBESH_DATABASE_PATH,
    hungarian_lexicon_path: str | Path = DEFAULT_HEBREW_LEXICON_HU_PATH,
) -> dict[str, object]:
    output = Path(output_path)
    language_audit = build_tbesh_language_normalization_audit(
        output_path=output.parent / DEFAULT_LANGUAGE_AUDIT_PATH.name,
        tahot_database_path=tahot_database_path,
        tbesh_database_path=tbesh_database_path,
    )
    language_by_strong = {
        str(record["strong_id"]): record
        for record in language_audit["records"]
        if isinstance(record, dict)
    }
    entries = _tbesh_entries(tbesh_database_path, language_by_strong=language_by_strong)
    frequencies = _core_frequencies(tahot_database_path)
    hu_entries = load_hebrew_hungarian_lexicon(hungarian_lexicon_path)
    records = []
    for strong_id, entry in entries.items():
        freq = frequencies.get(strong_id, {})
        token_frequency = int(freq.get("token_frequency", 0))
        verse_frequency = int(freq.get("verse_frequency", 0))
        book_frequency = int(freq.get("book_frequency", 0))
        part_of_speech = _part_of_speech(entry)
        theological = _theological_flag(strong_id, entry)
        proper_name = _proper_name_flag(entry)
        ambiguity = _ambiguity_flag(entry)
        extended = _extended_strong_flag(strong_id)
        usable_source = _usable_source_flag(entry)
        technical = _technical_record_flag(entry, part_of_speech)
        simple = _simple_lexical_flag(entry, part_of_speech, proper_name, ambiguity, usable_source)
        score = _priority_score(
            token_frequency=token_frequency,
            verse_frequency=verse_frequency,
            book_frequency=book_frequency,
            language=entry["language"],
            theological=theological,
            proper_name=proper_name,
            ambiguity=ambiguity,
            extended=extended,
            technical=technical,
            usable_source=usable_source,
            in_demo=_in_demo_sample(freq.get("sample_references", [])),
        )
        records.append(
            {
                "strong_id": strong_id,
                "lemma": entry["hebrew"],
                "language": entry["language"],
                "original_language": entry.get("original_language", ""),
                "language_evidence": entry.get("language_evidence", ""),
                "hebrew_token_count": int(freq.get("hebrew_token_count", 0)),
                "aramaic_token_count": int(freq.get("aramaic_token_count", 0)),
                "part_of_speech": part_of_speech,
                "token_frequency": token_frequency,
                "verse_frequency": verse_frequency,
                "book_frequency": book_frequency,
                "tbesh_record_exists": True,
                "current_hu_record_exists": strong_id in hu_entries,
                "priority_score": score,
                "priority_reason": _priority_reason(token_frequency, theological, proper_name, ambiguity, simple),
                "sample_references": freq.get("sample_references", []),
                "proper_name_flag": proper_name,
                "theological_term_flag": theological,
                "ambiguity_flag": ambiguity,
                "extended_strong_flag": extended,
                "technical_record_flag": technical,
                "usable_source_flag": usable_source,
                "simple_lexical_flag": simple,
            }
        )
    records.sort(key=lambda item: (-int(item["priority_score"]), item["strong_id"]))
    data = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "score_formula": (
            "TAHOT core token frequency first; demo and theological terms get small bonuses; "
            "proper names, ambiguity/guidance, non-Hebrew languages, extended IDs, and missing source text are penalized."
        ),
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def export_hebrew_lexicon_batch(
    output_path: str | Path = DEFAULT_PILOT_BATCH_PATH,
    *,
    limit: int = 100,
    offset: int = 0,
    tahot_database_path: str | Path = DEFAULT_TAHOT_DATABASE_PATH,
    tbesh_database_path: str | Path = DEFAULT_TBESH_DATABASE_PATH,
    hungarian_lexicon_path: str | Path = DEFAULT_HEBREW_LEXICON_HU_PATH,
) -> HebrewLexiconBatchReport:
    output = Path(output_path)
    default_output = output.resolve() == DEFAULT_PILOT_BATCH_PATH.resolve()
    production_batch_output = output.parent.resolve() == DEFAULT_BATCH_DIR.resolve()
    priority_output = (
        GENERATED_DATA_DIR / "hebrew_lexicon_translation_priority.json"
        if default_output
        else output.parent / "hebrew_lexicon_translation_priority.json"
    )
    language_output = DEFAULT_LANGUAGE_AUDIT_PATH if default_output else output.parent / DEFAULT_LANGUAGE_AUDIT_PATH.name
    batch_audit_output = (
        DEFAULT_BATCH_AUDIT_PATH
        if default_output
        else GENERATED_DATA_DIR / f"{output.stem}_audit.json"
        if production_batch_output
        else output.with_name(f"{output.stem}_audit.json")
    )
    audit = build_hebrew_lexicon_priority_audit(
        output_path=priority_output,
        tahot_database_path=tahot_database_path,
        tbesh_database_path=tbesh_database_path,
        hungarian_lexicon_path=hungarian_lexicon_path,
    )
    language_by_strong = {
        str(record["strong_id"]): record
        for record in build_tbesh_language_normalization_audit(
            output_path=language_output,
            tahot_database_path=tahot_database_path,
            tbesh_database_path=tbesh_database_path,
        )["records"]
        if isinstance(record, dict)
    }
    entries = _tbesh_entries(tbesh_database_path, language_by_strong=language_by_strong)
    candidates = []
    excluded_preaudit = []
    for item in audit["records"]:
        if item["current_hu_record_exists"] or not item["tbesh_record_exists"]:
            continue
        if item["token_frequency"] <= 0:
            continue
        if item.get("technical_record_flag"):
            excluded_preaudit.append({**item, "preaudit_class": "technical_risk", "exclusion_reason": "technical parser or annotation risk"})
            continue
        if not item.get("usable_source_flag"):
            excluded_preaudit.append({**item, "preaudit_class": "insufficient_source", "exclusion_reason": "missing usable gloss and source note"})
            continue
        entry = entries[item["strong_id"]]
        record = _batch_record(item, entry)
        if record["preaudit_class"] in {"technical_risk", "insufficient_source"}:
            excluded_preaudit.append({**record, "exclusion_reason": record["review_reason"]})
            continue
        candidates.append(record)
    ordered = _select_pilot_records(candidates, limit=limit + offset)
    selected = _sort_export_records(ordered[offset : offset + limit])
    data = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source": SOURCE_NAME,
        "batch": {"limit": limit, "offset": offset, "order_by": "priority_score"},
        "translation_guidelines": _translation_guidelines(),
        "records": selected,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_batch_quality_audit(batch_audit_output, selected, candidates, excluded_preaudit=excluded_preaudit)
    _write_review_candidate_batch(output, data, selected)
    return HebrewLexiconBatchReport(
        output_path=str(output),
        records_exported=len(selected),
        limit=limit,
        offset=offset,
        first_strong_id=selected[0]["strong_id"] if selected else None,
        last_strong_id=selected[-1]["strong_id"] if selected else None,
    )


def import_hebrew_lexicon_batch(
    input_path: str | Path,
    *,
    output_path: str | Path = DEFAULT_HEBREW_LEXICON_HU_PATH,
    tbesh_database_path: str | Path = DEFAULT_TBESH_DATABASE_PATH,
) -> HebrewLexiconImportReport:
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {data.get('schema_version')!r}")
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    existing = {
        strong_id: _entry_to_json(entry)
        for strong_id, entry in load_hebrew_hungarian_lexicon(output_path).items()
    }
    tbesh_entries = _tbesh_entries(tbesh_database_path)
    seen: set[str] = set()
    errors: list[str] = []
    imported = 0
    skipped = 0
    for index, raw in enumerate(records, start=1):
        try:
            record = _validated_import_record(raw, index, tbesh_entries)
            if record["strong_id"] in seen:
                raise ValueError(f"duplicate strong_id in batch: {record['strong_id']}")
            seen.add(record["strong_id"])
        except ValueError as exc:
            errors.append(f"record #{index}: {exc}")
            skipped += 1
            continue
        existing[record["strong_id"]] = _production_record(record, tbesh_entries[record["strong_id"]])
        imported += 1
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(sorted(existing.values(), key=lambda item: item["strong_id"]), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return HebrewLexiconImportReport(str(input_path), str(output), len(records), imported, skipped, tuple(errors))


def audit_hebrew_lexicon_hu(path: str | Path = DEFAULT_HEBREW_LEXICON_HU_PATH) -> dict[str, object]:
    entries = load_hebrew_hungarian_lexicon(path)
    return {
        "records": len(entries),
        "review_status_counts": {
            status: sum(1 for entry in entries.values() if entry.review_status == status)
            for status in sorted({"draft", "reviewed"})
        },
        "languages": {
            language: sum(1 for entry in entries.values() if entry.language == language)
            for language in sorted({entry.language for entry in entries.values()})
        },
    }


def _raw_tbesh_entries(database_path: str | Path) -> dict[str, dict[str, str]]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT strong_id, estrong, dstrong, ustrong, hebrew, transliteration, morph, gloss, meaning, language, source_name
            FROM lexicon_entries
            ORDER BY strong_id
            """
        ).fetchall()
    return {
        row[0]: {
            "strong_id": row[0] or "",
            "estrong": row[1] or "",
            "dstrong": row[2] or "",
            "ustrong": row[3] or "",
            "hebrew": row[4] or "",
            "transliteration": row[5] or "",
            "morph": row[6] or "",
            "gloss": row[7] or "",
            "meaning": row[8] or "",
            "language": (row[9] or "").strip(),
            "source_name": row[10] or SOURCE_NAME,
        }
        for row in rows
    }


def _tbesh_entries(
    database_path: str | Path,
    *,
    language_by_strong: dict[str, dict[str, object]] | None = None,
) -> dict[str, dict[str, str]]:
    raw_entries = _raw_tbesh_entries(database_path)
    if language_by_strong is None:
        language_by_strong = {}
    entries: dict[str, dict[str, str]] = {}
    for strong_id, entry in raw_entries.items():
        language_record = language_by_strong.get(strong_id, {})
        resolved = str(language_record.get("resolved_language") or entry["language"] or _language_from_morph(entry["morph"]))
        if resolved == "unspecified":
            resolved = ""
        entries[strong_id] = {
            **entry,
            "language": resolved,
            "original_language": entry["language"],
            "language_evidence": str(language_record.get("evidence") or ""),
        }
    return entries


def _core_frequencies(database_path: str | Path) -> dict[str, dict[str, object]]:
    with sqlite3.connect(database_path) as connection:
        join_column = _token_strong_join_column(connection)
        if _table_exists(connection, "token_strong_ids"):
            rows = connection.execute(
                f"""
                SELECT s.strong_id, t.book, t.chapter, t.verse, t.language
                FROM token_strong_ids s
                JOIN tokens t ON t.{join_column} = s.{join_column}
                WHERE s.role = 'core' AND COALESCE(s.strong_id, '') <> ''
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT c.strong_id, t.book, t.chapter, t.verse, t.language
                FROM token_components c
                JOIN tokens t ON t.stable_token_key = c.stable_token_key
                WHERE c.role = 'core' AND COALESCE(c.strong_id, '') <> ''
                """
            ).fetchall()
    grouped: dict[str, dict[str, object]] = {}
    for strong_id, book, chapter, verse, language in rows:
        try:
            normalized = normalize_hebrew_strong_id(str(strong_id))
        except ValueError:
            continue
        item = grouped.setdefault(
            normalized,
            {
                "token_frequency": 0,
                "refs": set(),
                "books": set(),
                "sample_references": [],
                "hebrew_token_count": 0,
                "aramaic_token_count": 0,
            },
        )
        item["token_frequency"] = int(item["token_frequency"]) + 1
        if language == "hebrew":
            item["hebrew_token_count"] = int(item["hebrew_token_count"]) + 1
        elif language == "aramaic":
            item["aramaic_token_count"] = int(item["aramaic_token_count"]) + 1
        ref = f"{book} {chapter},{verse}"
        item["refs"].add(ref)  # type: ignore[union-attr]
        item["books"].add(book)  # type: ignore[union-attr]
        samples = item["sample_references"]
        if isinstance(samples, list) and len(samples) < 5 and ref not in samples:
            samples.append(ref)
    for item in grouped.values():
        item["verse_frequency"] = len(item.pop("refs"))
        item["book_frequency"] = len(item.pop("books"))
    return grouped


def _core_language_counts(database_path: str | Path) -> dict[str, dict[str, int]]:
    with sqlite3.connect(database_path) as connection:
        join_column = _token_strong_join_column(connection)
        if _table_exists(connection, "token_strong_ids"):
            rows = connection.execute(
                f"""
                SELECT s.strong_id, t.language, COUNT(*)
                FROM token_strong_ids s
                JOIN tokens t ON t.{join_column} = s.{join_column}
                WHERE s.role = 'core' AND COALESCE(s.strong_id, '') <> ''
                GROUP BY s.strong_id, t.language
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT c.strong_id, t.language, COUNT(*)
                FROM token_components c
                JOIN tokens t ON t.stable_token_key = c.stable_token_key
                WHERE c.role = 'core' AND COALESCE(c.strong_id, '') <> ''
                GROUP BY c.strong_id, t.language
                """
            ).fetchall()
    counts: dict[str, dict[str, int]] = {}
    for strong_id, language, count in rows:
        try:
            normalized = normalize_hebrew_strong_id(str(strong_id))
        except ValueError:
            continue
        item = counts.setdefault(normalized, {"hebrew": 0, "aramaic": 0})
        if language == "hebrew":
            item["hebrew"] += int(count)
        elif language == "aramaic":
            item["aramaic"] += int(count)
    return counts


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _token_strong_join_column(connection: sqlite3.Connection) -> str:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(token_strong_ids)")}
    return "token_id" if "token_id" in columns else "stable_token_key"


def _resolve_language_record(entry: dict[str, str], counts: dict[str, int]) -> dict[str, object]:
    original = (entry["language"] or "").strip() or "unspecified"
    hebrew_count = int(counts.get("hebrew", 0))
    aramaic_count = int(counts.get("aramaic", 0))
    warning = ""
    if original in {"hebrew", "aramaic"}:
        resolved = original
        evidence = "explicit_tbesh_language"
        confidence = "high"
        if (resolved == "hebrew" and aramaic_count) or (resolved == "aramaic" and hebrew_count):
            warning = "TAHOT core-token language differs from explicit TBESH language"
    elif hebrew_count and aramaic_count:
        resolved = "mixed"
        evidence = "tahot_core_token_language"
        confidence = "high"
        warning = "occurs in Hebrew and Aramaic core-token contexts"
    elif hebrew_count:
        resolved = "hebrew"
        evidence = "tahot_core_token_language"
        confidence = "high"
    elif aramaic_count:
        resolved = "aramaic"
        evidence = "tahot_core_token_language"
        confidence = "high"
    else:
        morph_language = _language_from_morph(entry["morph"])
        relation_language = _language_from_relation(entry)
        if morph_language:
            resolved = morph_language
            evidence = "tbesh_morph_prefix"
            confidence = "medium"
        elif relation_language:
            resolved = relation_language
            evidence = "tbesh_relation_metadata"
            confidence = "medium"
        else:
            resolved = "unspecified"
            evidence = "none"
            confidence = "low"
            warning = "no explicit language, no TAHOT core occurrence, and no documented H/A metadata"
    return {
        "strong_id": entry["strong_id"],
        "lemma": entry["hebrew"],
        "original_language": original,
        "resolved_language": resolved,
        "evidence": evidence,
        "hebrew_token_count": hebrew_count,
        "aramaic_token_count": aramaic_count,
        "confidence": confidence,
        "warning": warning,
    }


def _priority_score(
    *,
    token_frequency: int,
    verse_frequency: int,
    book_frequency: int,
    language: str,
    theological: bool,
    proper_name: bool,
    ambiguity: bool,
    extended: bool,
    technical: bool,
    usable_source: bool,
    in_demo: bool,
) -> int:
    return (
        token_frequency * 100
        + verse_frequency * 10
        + book_frequency * 25
        + (3000 if theological else 0)
        + (2500 if in_demo else 0)
        + (1000 if language == "hebrew" else 0)
        - (6000 if language == "aramaic" else 0)
        - (9000 if language in {"mixed", ""} else 0)
        - (25000 if proper_name and not theological else 0)
        - (2500 if ambiguity else 0)
        - (1500 if extended else 0)
        - (50000 if technical else 0)
        - (50000 if not usable_source else 0)
    )


def _batch_record(priority: dict[str, object], entry: dict[str, str]) -> dict[str, object]:
    preaudit = _translation_preaudit(priority, entry)
    return {
        "strong_id": priority["strong_id"],
        "lemma": entry["hebrew"],
        "transliteration": entry["transliteration"],
        "language": entry["language"],
        "part_of_speech": priority.get("part_of_speech", ""),
        "source_gloss_en": entry["gloss"],
        "source_note_en": _plain_source_note(entry["meaning"]),
        "token_frequency": priority["token_frequency"],
        "verse_frequency": priority.get("verse_frequency", 0),
        "book_frequency": priority.get("book_frequency", 0),
        "priority_score": priority.get("priority_score", 0),
        "sample_references": priority["sample_references"],
        "proper_name_flag": priority["proper_name_flag"],
        "ambiguity_flag": priority["ambiguity_flag"],
        "simple_lexical_flag": priority.get("simple_lexical_flag", False),
        "technical_record_flag": priority.get("technical_record_flag", False),
        **preaudit,
        "selection_reason": priority.get("priority_reason", ""),
        "requested_fields": ["base_meaning_hu", "possible_meanings_hu", "lexical_note_hu"],
        "translator_notes": "",
        "base_meaning_hu": "",
        "possible_meanings_hu": [],
        "lexical_note_hu": "",
        "translation_method": "ai_assisted",
        "review_status": "draft",
    }


def _validated_import_record(raw: Any, index: int, tbesh_entries: dict[str, dict[str, str]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("record must be an object")
    strong_id = normalize_hebrew_strong_id(str(raw.get("strong_id", "")))
    if strong_id not in tbesh_entries:
        raise ValueError(f"TBESH source record not found: {strong_id}")
    if str(raw.get("lemma", "")).strip() != tbesh_entries[strong_id]["hebrew"]:
        raise ValueError(f"lemma mismatch for {strong_id}")
    base = _required_hu(raw.get("base_meaning_hu"), "base_meaning_hu")
    possible = raw.get("possible_meanings_hu")
    if not isinstance(possible, list) or not possible:
        raise ValueError("possible_meanings_hu must contain at least one value")
    possible_hu = [_required_hu(item, "possible_meanings_hu") for item in possible]
    note = _required_hu(raw.get("lexical_note_hu"), "lexical_note_hu")
    warnings = raw.get("warnings", [])
    if not isinstance(warnings, list):
        raise ValueError("warnings must be a list")
    for field_name, value in (("base_meaning_hu", base), ("lexical_note_hu", note), *[("possible_meanings_hu", item) for item in possible_hu]):
        _reject_bad_hu_text(value, field_name)
    if raw.get("review_status") not in {"draft", "reviewed"}:
        raise ValueError("review_status must be 'draft' or 'reviewed'")
    if raw.get("translation_method") not in {"ai_assisted", "human"}:
        raise ValueError("translation_method must be 'ai_assisted' or 'human'")
    return {**raw, "strong_id": strong_id, "base_meaning_hu": base, "possible_meanings_hu": possible_hu, "lexical_note_hu": note}


def _production_record(record: dict[str, Any], source: dict[str, str]) -> dict[str, object]:
    return {
        "strong_id": record["strong_id"],
        "lemma": source["hebrew"],
        "transliteration": source["transliteration"],
        "language": record.get("language") or source["language"],
        "base_meaning_hu": record["base_meaning_hu"],
        "possible_meanings_hu": record["possible_meanings_hu"],
        "lexical_note_hu": record["lexical_note_hu"],
        "source_gloss_en": source["gloss"],
        "source_note_en": _plain_source_note(source["meaning"]),
        "translation_method": record["translation_method"],
        "review_status": record["review_status"],
        "source": "STEPBible TBESH alapján készített magyar munkaváltozat",
        "source_record_id": record["strong_id"],
        "aliases": [],
        "warnings": list(record.get("warnings", [])),
    }


def _entry_to_json(entry: Any) -> dict[str, object]:
    return {
        "strong_id": entry.strong_id,
        "lemma": entry.lemma,
        "transliteration": entry.transliteration,
        "language": entry.language,
        "base_meaning_hu": entry.base_meaning_hu,
        "possible_meanings_hu": list(entry.possible_meanings_hu),
        "lexical_note_hu": entry.lexical_note_hu,
        "source_gloss_en": entry.source_gloss_en,
        "source_note_en": entry.source_note_en,
        "translation_method": entry.translation_method,
        "review_status": entry.review_status,
        "source": entry.source,
        "source_record_id": entry.source_record_id,
        "aliases": list(entry.aliases),
        "warnings": list(entry.warnings),
    }


def _required_hu(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if len(value.strip()) > 500:
        raise ValueError(f"{field_name} is too long")
    return value.strip()


def _reject_bad_hu_text(value: str, field_name: str) -> None:
    if not value:
        return
    if HTML_RE.search(value):
        raise ValueError(f"{field_name} must not contain HTML")
    if MARKDOWN_RE.search(value):
        raise ValueError(f"{field_name} must not contain raw markdown")
    if _appears_to_be_english_sentence(value, field_name):
        raise ValueError(f"{field_name} appears to contain an English sentence")


def _appears_to_be_english_sentence(value: str, field_name: str = "") -> bool:
    words = [word.casefold() for word in WORD_RE.findall(value)]
    if not words:
        return False
    technical_words = {word for word in words if word in TECHNICAL_TERMS or re.fullmatch(r"h\d{4}[a-z]?", word)}
    lexical_words = [word for word in words if word not in technical_words]
    if not lexical_words:
        return False
    english_hits = sum(1 for word in lexical_words if word in ENGLISH_FUNCTION_WORDS)
    hungarian_hits = sum(1 for word in words if word in HUNGARIAN_FUNCTION_WORDS)
    has_hungarian_accents = bool(HUNGARIAN_ACCENT_RE.search(value))
    has_sentence_punctuation = bool(re.search(r"[.!?;]", value))
    if has_hungarian_accents:
        hungarian_hits += 2
    if field_name == "possible_meanings_hu":
        return english_hits >= 2 and hungarian_hits == 0
    if not has_hungarian_accents and english_hits >= 4 and has_sentence_punctuation:
        return True
    if hungarian_hits >= 2:
        return False
    if english_hits >= 4 and has_sentence_punctuation:
        return True
    if "the" in lexical_words and english_hits >= 2 and not has_hungarian_accents:
        return True
    if english_hits >= 3 and has_sentence_punctuation:
        return True
    return english_hits >= 2 and hungarian_hits == 0 and len(lexical_words) >= 2


def _plain_source_note(value: str, limit: int = 2000) -> str:
    text = html.unescape(HTML_RE.sub(" ", value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip()


def _language_from_morph(morph: str) -> str:
    if morph.startswith("A"):
        return "aramaic"
    if morph.startswith("H"):
        return "hebrew"
    return ""


def _proper_name_flag(entry: dict[str, str]) -> bool:
    return entry["morph"].endswith("-P") or " = \"" in entry["meaning"] or " only mentioned at " in entry["meaning"]


def _theological_flag(strong_id: str, entry: dict[str, str]) -> bool:
    haystack = f"{entry['hebrew']} {entry['gloss']} {entry['meaning']}".lower()
    return strong_id in THEOLOGICAL_TERMS or any(term in haystack for term in ("god", "lord", "spirit", "covenant", "sin", "righteous", "holy"))


def _ambiguity_flag(entry: dict[str, str]) -> bool:
    return any(marker in entry["meaning"] for marker in ("<BR>", ";", "1)", "2)", "»")) or "," in entry["gloss"]


def _in_demo_sample(samples: object) -> bool:
    if not isinstance(samples, list):
        return False
    demo_books = {"Rut", "Psa", "Dan", "Gen", "Isa"}
    return any(str(sample).split(" ", 1)[0] in demo_books for sample in samples)


def _priority_reason(token_frequency: int, theological: bool, proper_name: bool, ambiguity: bool) -> str:
    reasons = []
    if token_frequency:
        reasons.append("előfordul a TAHOT core tokenekben")
    if theological:
        reasons.append("teológiailag/exegétikailag fontos lexéma")
    if proper_name:
        reasons.append("névanyagként külön ellenőrizendő")
    if ambiguity:
        reasons.append("többjelentésű vagy guidance-ot tartalmaz")
    return "; ".join(reasons) or "TBESH rekord"


def _language_from_relation(entry: dict[str, str]) -> str:
    text = f"{entry['estrong']} {entry['meaning']}".lower()
    if " in aramaic of " in text or text.startswith("aramaic of ") or "<br>aramaic of " in text:
        return "aramaic"
    if " in hebrew of " in text or text.startswith("hebrew of ") or "<br>hebrew of " in text:
        return "hebrew"
    return ""


def _part_of_speech(entry: dict[str, str]) -> str:
    morph = entry["morph"]
    if ":V" in morph:
        return "verb"
    if ":N" in morph:
        return "noun"
    if ":A" in morph:
        return "adjective"
    if ":Part" in morph or morph.endswith("Part"):
        return "particle"
    if ":Adv" in morph:
        return "adverb"
    if ":Pron" in morph:
        return "pronoun"
    return "other"


def _extended_strong_flag(strong_id: str) -> bool:
    return bool(re.fullmatch(r"H\d{4}[A-Z]", strong_id))


def _technical_record_flag(entry: dict[str, str], part_of_speech: str) -> bool:
    lemma = entry["hebrew"].strip()
    gloss = entry["gloss"].strip()
    meaning = _plain_source_note(entry["meaning"]).lower()
    if "[" in lemma or "]" in lemma:
        return True
    if part_of_speech == "other" and not gloss:
        return True
    return "parser" in meaning and "technical" in meaning


def _usable_source_flag(entry: dict[str, str]) -> bool:
    return bool(entry["gloss"].strip() or _plain_source_note(entry["meaning"]).strip())


def _translation_preaudit(priority: dict[str, object], entry: dict[str, str]) -> dict[str, object]:
    if priority.get("technical_record_flag"):
        preaudit_class = "technical_risk"
        difficulty = "high"
        risk = "technical"
        review_required = True
        review_reason = "Technikai vagy annotációs jellegű rekord, nem elsődleges lexikai szócikk."
    elif not priority.get("usable_source_flag"):
        preaudit_class = "insufficient_source"
        difficulty = "high"
        risk = "source_missing"
        review_required = True
        review_reason = "Nincs használható gloss vagy source note."
    elif priority.get("proper_name_flag"):
        preaudit_class = "proper_name"
        difficulty = "medium"
        risk = "proper_name"
        review_required = True
        review_reason = "Tulajdonnév vagy névanyag; magyar névalak ellenőrzése szükséges."
    elif priority.get("ambiguity_flag"):
        preaudit_class = "ambiguous"
        difficulty = "high"
        risk = "polysemy"
        review_required = True
        review_reason = "Többértelmű vagy guidance-ot tartalmazó forrásrekord."
    elif priority.get("simple_lexical_flag"):
        preaudit_class = "straightforward"
        difficulty = "low"
        risk = "low"
        review_required = False
        review_reason = ""
    else:
        preaudit_class = "contextual"
        difficulty = "medium"
        risk = "contextual"
        review_required = True
        review_reason = "Kontextusfüggő vagy közepesen összetett lexikai rekord."
    warnings = []
    if preaudit_class == "proper_name":
        warnings.append("proper_name_review")
    if preaudit_class == "ambiguous":
        warnings.append("ambiguity_review")
    if preaudit_class == "contextual":
        warnings.append("contextual_review")
    return {
        "preaudit_class": preaudit_class,
        "translation_difficulty": difficulty,
        "translation_risk": risk,
        "suggested_hu_headword": "",
        "review_required": review_required,
        "review_reason": review_reason,
        "warnings": warnings,
    }


def _proper_name_flag(entry: dict[str, str]) -> bool:
    meaning = entry["meaning"].lower()
    gloss = entry["gloss"].strip()
    return (
        entry["morph"].endswith("-P")
        or " = \"" in entry["meaning"]
        or " only mentioned at " in meaning
        or "first mentioned at " in meaning
        or "son of:" in meaning
        or "daughter of:" in meaning
        or "father of:" in meaning
        or "mother of:" in meaning
        or gloss in {"LORD", "Yahweh"}
    )


def _ambiguity_flag(entry: dict[str, str]) -> bool:
    meaning = html.unescape(entry["meaning"])
    gloss = entry["gloss"]
    numbered_senses = bool(re.search(r"\b1\)", meaning) and re.search(r"\b2\)", meaning))
    guidance_relation = any(
        marker.lower() in meaning.lower()
        for marker in (
            "Another name of",
            "Another spelling of",
            "Combined with",
            "Aramaic of",
            "Hebrew of",
            "Spelling of",
            "Part of",
        )
    )
    return numbered_senses or guidance_relation or "»" in meaning or "," in gloss or ";" in gloss


def _simple_lexical_flag(
    entry: dict[str, str],
    part_of_speech: str,
    proper_name: bool,
    ambiguity: bool,
    usable_source: bool,
) -> bool:
    return (
        entry["language"] == "hebrew"
        and part_of_speech in {"noun", "verb", "adjective"}
        and not proper_name
        and not ambiguity
        and usable_source
    )


def _priority_reason(token_frequency: int, theological: bool, proper_name: bool, ambiguity: bool, simple: bool) -> str:
    reasons = []
    if token_frequency:
        reasons.append("előfordul a TAHOT core tokenekben")
    if simple:
        reasons.append("egyszerű, jól dokumentált héber lexikai rekord")
    if theological:
        reasons.append("teológiailag/exegetikailag fontos lexéma")
    if proper_name:
        reasons.append("névanyagként külön ellenőrizendő")
    if ambiguity:
        reasons.append("többjelentésű vagy guidance-ot tartalmaz")
    return "; ".join(reasons) or "TBESH rekord"


def _select_pilot_records(records: list[dict[str, object]], *, limit: int) -> list[dict[str, object]]:
    if limit <= 0:
        return []
    quotas = _selection_quotas(limit)
    ordered = sorted(records, key=lambda item: (-int(item["token_frequency"]), -_record_priority(item), str(item["strong_id"])))
    selected: list[dict[str, object]] = []
    selected_ids: set[str] = set()

    def can_add(record: dict[str, object], *, strict_hebrew: bool = False) -> bool:
        if str(record["strong_id"]) in selected_ids:
            return False
        if strict_hebrew and record.get("language") != "hebrew":
            return False
        projected = selected + [record]
        if _count_language(projected, "aramaic") > quotas["max_aramaic"]:
            return False
        if _count_unresolved(projected) > quotas["max_unresolved"]:
            return False
        if sum(1 for item in projected if item.get("proper_name_flag")) > quotas["max_proper"]:
            return False
        if sum(1 for item in projected if item.get("ambiguity_flag")) > quotas["max_ambiguity"]:
            return False
        return True

    def add_from(predicate: Any, *, max_items: int | None = None, strict_hebrew: bool = False) -> None:
        added = 0
        for record in ordered:
            if len(selected) >= limit:
                return
            if max_items is not None and added >= max_items:
                return
            if not predicate(record):
                continue
            if not can_add(record, strict_hebrew=strict_hebrew):
                continue
            selected.append(record)
            selected_ids.add(str(record["strong_id"]))
            added += 1

    add_from(lambda item: item.get("simple_lexical_flag"), max_items=min(quotas["target_simple"], limit), strict_hebrew=True)
    add_from(lambda item: item.get("language") == "hebrew" and item.get("theological_term_flag"), max_items=quotas["theological_slots"])
    add_from(
        lambda item: item.get("language") == "hebrew"
        and not item.get("proper_name_flag")
        and item.get("part_of_speech") in {"noun", "verb", "adjective", "particle", "adverb"},
        max_items=max(0, quotas["target_hebrew"] - len(selected)),
    )
    add_from(lambda item: item.get("language") == "aramaic" and not item.get("proper_name_flag"), max_items=quotas["max_aramaic"])
    add_from(lambda item: item.get("language") in {"mixed", "", "unspecified"}, max_items=quotas["max_unresolved"])
    add_from(lambda item: item.get("language") == "hebrew", max_items=max(0, limit - len(selected)))
    add_from(lambda item: True, max_items=max(0, limit - len(selected)))
    return selected[:limit]


def _selection_quotas(limit: int) -> dict[str, int]:
    if limit >= 1000:
        return {
            "target_hebrew": 850,
            "max_aramaic": 100,
            "max_unresolved": 50,
            "max_proper": 40,
            "target_simple": 700,
            "max_ambiguity": 250,
            "theological_slots": 50,
        }
    if limit >= 500:
        return {
            "target_hebrew": 420,
            "max_aramaic": 50,
            "max_unresolved": 30,
            "max_proper": 20,
            "target_simple": 300,
            "max_ambiguity": 150,
            "theological_slots": 30,
        }
    return {
        "target_hebrew": min(90, limit),
        "max_aramaic": min(10, max(0, limit // 10)),
        "max_unresolved": 5,
        "max_proper": 5,
        "target_simple": min(70, limit),
        "max_ambiguity": 25,
        "theological_slots": 10,
    }


def _record_priority(record: dict[str, object]) -> int:
    score = int(record.get("token_frequency", 0)) * 100
    if record.get("simple_lexical_flag"):
        score += 3000
    if record.get("theological_term_flag"):
        score += 2000
    if record.get("language") == "hebrew":
        score += 1000
    return score


def _sort_export_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        records,
        key=lambda record: (
            -int(record.get("token_frequency", 0)),
            -int(record.get("verse_frequency", 0)),
            -int(record.get("book_frequency", 0)),
            -int(record.get("priority_score", 0)),
            str(record.get("strong_id", "")),
        ),
    )


def _count_language(records: list[dict[str, object]], language: str) -> int:
    return sum(1 for record in records if record.get("language") == language)


def _count_unresolved(records: list[dict[str, object]]) -> int:
    return sum(1 for record in records if record.get("language") in {"mixed", "", "unspecified"})


def _write_batch_quality_audit(
    output_path: str | Path,
    selected: list[dict[str, object]],
    candidates: list[dict[str, object]],
    *,
    excluded_preaudit: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    frequencies = [int(record["token_frequency"]) for record in selected]
    selected_ids = {str(record["strong_id"]) for record in selected}
    excluded_preaudit = excluded_preaudit or []
    excluded = [
        {
            "strong_id": record["strong_id"],
            "lemma": record["lemma"],
            "token_frequency": record["token_frequency"],
            "language": record.get("language", ""),
            "reason": _exclusion_reason(record, selected),
        }
        for record in candidates
        if str(record["strong_id"]) not in selected_ids
    ][:50]
    data = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "record_count": len(selected),
        "language_distribution": dict(Counter(str(record.get("language") or "unspecified") for record in selected)),
        "part_of_speech_distribution": dict(Counter(str(record.get("part_of_speech") or "other") for record in selected)),
        "proper_name_count": sum(1 for record in selected if record.get("proper_name_flag")),
        "ambiguity_flag_count": sum(1 for record in selected if record.get("ambiguity_flag")),
        "simple_record_count": sum(1 for record in selected if record.get("simple_lexical_flag")),
        "guidance_record_count": sum(1 for record in selected if record.get("ambiguity_flag")),
        "preaudit_class_distribution": dict(Counter(str(record.get("preaudit_class") or "") for record in selected)),
        "straightforward_record_count": sum(1 for record in selected if record.get("preaudit_class") == "straightforward"),
        "contextual_record_count": sum(1 for record in selected if record.get("preaudit_class") == "contextual"),
        "review_candidate_count": sum(1 for record in selected if record.get("review_required")),
        "technical_risk_excluded_count": sum(1 for record in excluded_preaudit if record.get("preaudit_class") == "technical_risk"),
        "insufficient_source_excluded_count": sum(1 for record in excluded_preaudit if record.get("preaudit_class") == "insufficient_source"),
        "simple_to_guidance_ratio": _safe_ratio(
            sum(1 for record in selected if record.get("simple_lexical_flag")),
            sum(1 for record in selected if record.get("ambiguity_flag")),
        ),
        "token_frequency": {
            "minimum": min(frequencies) if frequencies else 0,
            "median": median(frequencies) if frequencies else 0,
            "maximum": max(frequencies) if frequencies else 0,
        },
        "top_20_records": [
            {
                "strong_id": record["strong_id"],
                "lemma": record["lemma"],
                "language": record.get("language", ""),
                "part_of_speech": record.get("part_of_speech", ""),
                "token_frequency": record["token_frequency"],
                "selection_reason": record.get("selection_reason", ""),
            }
            for record in selected[:20]
        ],
        "top_30_records": [
            {
                "strong_id": record["strong_id"],
                "lemma": record["lemma"],
                "language": record.get("language", ""),
                "part_of_speech": record.get("part_of_speech", ""),
                "token_frequency": record["token_frequency"],
                "selection_reason": record.get("selection_reason", ""),
            }
            for record in selected[:30]
        ],
        "top_40_records": [
            {
                "strong_id": record["strong_id"],
                "lemma": record["lemma"],
                "language": record.get("language", ""),
                "part_of_speech": record.get("part_of_speech", ""),
                "token_frequency": record["token_frequency"],
                "selection_reason": record.get("selection_reason", ""),
            }
            for record in selected[:40]
        ],
        "lowest_priority_20_records": [
            {
                "strong_id": record["strong_id"],
                "lemma": record["lemma"],
                "language": record.get("language", ""),
                "part_of_speech": record.get("part_of_speech", ""),
                "token_frequency": record["token_frequency"],
                "selection_reason": record.get("selection_reason", ""),
            }
            for record in selected[-20:]
        ],
        "lowest_priority_30_records": [
            {
                "strong_id": record["strong_id"],
                "lemma": record["lemma"],
                "language": record.get("language", ""),
                "part_of_speech": record.get("part_of_speech", ""),
                "token_frequency": record["token_frequency"],
                "selection_reason": record.get("selection_reason", ""),
            }
            for record in selected[-30:]
        ],
        "records": [
            {
                "strong_id": record["strong_id"],
                "lemma": record["lemma"],
                "language": record.get("language", ""),
                "part_of_speech": record.get("part_of_speech", ""),
                "token_frequency": record["token_frequency"],
                "selection_reason": record.get("selection_reason", ""),
            }
            for record in selected
        ],
        "excluded_high_priority_records": excluded,
        "excluded_preaudit_records": [
            {
                "strong_id": record.get("strong_id"),
                "lemma": record.get("lemma"),
                "language": record.get("language", ""),
                "token_frequency": record.get("token_frequency", 0),
                "preaudit_class": record.get("preaudit_class", ""),
                "reason": record.get("exclusion_reason", ""),
            }
            for record in excluded_preaudit[:100]
        ],
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def _write_review_candidate_batch(output_path: Path, batch_data: dict[str, object], selected: list[dict[str, object]]) -> None:
    if output_path.parent.resolve() != DEFAULT_BATCH_DIR.resolve():
        return
    review_records = [record for record in selected if record.get("review_required")]
    if not review_records:
        return
    review_path = output_path.with_name(f"{output_path.stem}_review_candidates.json")
    review_data = {
        **{key: value for key, value in batch_data.items() if key != "records"},
        "review_candidate_source": str(output_path),
        "records": review_records,
    }
    review_path.write_text(json.dumps(review_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_ratio(left: int, right: int) -> float | None:
    if right == 0:
        return None
    return round(left / right, 2)


def _exclusion_reason(record: dict[str, object], selected: list[dict[str, object]]) -> str:
    if record.get("language") == "aramaic" and _count_language(selected, "aramaic") >= 10:
        return "aramaic pilot cap reached"
    if record.get("language") in {"mixed", "", "unspecified"}:
        return "unresolved/mixed language reserved for later batch"
    if record.get("proper_name_flag"):
        return "proper-name cap or later-name workflow"
    if record.get("ambiguity_flag"):
        return "guidance/ambiguity cap reached"
    if record.get("extended_strong_flag"):
        return "extended Strong variant deprioritized"
    return "lower priority after composition quotas"


def _translation_guidelines() -> dict[str, object]:
    return {
        "style": "Rövid, lexikai, kontextustól független magyar szótári lehetőségek.",
        "avoid": ["angol mondat", "HTML", "nyers markdown", "hosszú teológiai magyarázat", "kitalált etimológia"],
        "special_cases": ["tulajdonnevek", "földrajzi nevek", "népnevek", "isteni nevek és címek", "hapaxok", "héber-arámi homográfok"],
    }
