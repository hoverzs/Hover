from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bible_engine.greek_lexicon_repository import resolve_tbesg_database_path
from bible_engine.greek_token_repository import resolve_tagnt_database_path
from bible_engine.lexicon_hu import (
    DEFAULT_HUNGARIAN_LEXICON_PATH,
    DEFAULT_STRONG_ALIASES_PATH,
    load_hungarian_lexicon,
    load_strong_aliases,
    resolve_hungarian_lexicon_entry,
)
from bible_engine.lexicon_translation_workflow import (
    SCHEMA_VERSION,
    _export_record,
)
from bible_engine.tbesg_parser import normalize_greek_strong_id
from bible_engine.tbesg_sqlite import get_sqlite_lexicon_entry


ROOT = Path(__file__).parents[1]
DEFAULT_COVERAGE_REPORT_PATH = ROOT / "data" / "generated" / "nt_lexicon_coverage_report.json"
NT_COVERAGE_SOURCE_NAME = "STEPBible TBESG + TAGNT coverage"
NT_FREQUENCY_ORDER = "tagnt_token_frequency"
_GREEK_STRONG_FRAGMENT_RE = re.compile(r"G\d{1,5}[A-Z]?", re.IGNORECASE)


@dataclass(frozen=True)
class StrongFrequencyReport:
    token_count: int
    missing_strong_token_count: int
    frequencies: dict[str, int]
    token_strong_ids: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class CoverageAuditReport:
    output_path: str
    summary: dict[str, int | float]
    missing_hungarian_strong_ids: tuple[str, ...]
    missing_tbesg_strong_ids: tuple[str, ...]


@dataclass(frozen=True)
class NTMissingExportReport:
    output_path: str
    records_exported: int
    limit: int
    offset: int
    total_missing_nt_records: int
    warnings: tuple[str, ...]
    first_strong_id: str | None
    last_strong_id: str | None


def normalize_tagnt_strong_ids(value: object) -> tuple[str, ...]:
    text = "" if value is None else str(value).strip()
    if not text:
        return ()

    normalized: list[str] = []
    for raw_id in _GREEK_STRONG_FRAGMENT_RE.findall(text):
        try:
            strong_id = normalize_greek_strong_id(raw_id)
        except ValueError:
            continue
        if strong_id not in normalized:
            normalized.append(strong_id)
    return tuple(normalized)


def collect_tagnt_strong_frequencies(
    database_path: str | Path | None = None,
) -> StrongFrequencyReport:
    database = Path(database_path) if database_path is not None else resolve_tagnt_database_path()
    if database is None or not database.exists():
        raise FileNotFoundError(f"TAGNT SQLite database not found: {database}")

    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT strong_id FROM greek_tokens").fetchall()

    frequencies: dict[str, int] = {}
    token_strong_ids: list[tuple[str, ...]] = []
    missing_strong_token_count = 0
    for (raw_strong_id,) in rows:
        strong_ids = normalize_tagnt_strong_ids(raw_strong_id)
        token_strong_ids.append(strong_ids)
        if not strong_ids:
            missing_strong_token_count += 1
            continue
        for strong_id in strong_ids:
            frequencies[strong_id] = frequencies.get(strong_id, 0) + 1

    return StrongFrequencyReport(
        token_count=len(rows),
        missing_strong_token_count=missing_strong_token_count,
        frequencies=frequencies,
        token_strong_ids=tuple(token_strong_ids),
    )


def audit_nt_lexicon_coverage(
    *,
    output_path: str | Path = DEFAULT_COVERAGE_REPORT_PATH,
    tagnt_database_path: str | Path | None = None,
    tbesg_database_path: str | Path | None = None,
    hungarian_lexicon_path: str | Path = DEFAULT_HUNGARIAN_LEXICON_PATH,
    strong_aliases_path: str | Path = DEFAULT_STRONG_ALIASES_PATH,
) -> CoverageAuditReport:
    tagnt = collect_tagnt_strong_frequencies(tagnt_database_path)
    tagnt_strong_ids = set(tagnt.frequencies)
    tbesg_strong_ids = _load_tbesg_strong_ids(tbesg_database_path)
    hungarian_entries = _load_hungarian_entries(hungarian_lexicon_path)
    hungarian_strong_ids = set(hungarian_entries)
    aliases = _load_strong_aliases_if_available(strong_aliases_path)
    alias_resolved_strong_ids = {
        strong_id
        for strong_id in tagnt_strong_ids - hungarian_strong_ids
        if resolve_hungarian_lexicon_entry(hungarian_entries, strong_id, aliases) is not None
    }

    missing_tbesg = sorted(tagnt_strong_ids - tbesg_strong_ids)
    missing_hungarian = sorted(tagnt_strong_ids - hungarian_strong_ids)
    hungarian_used = sorted(hungarian_strong_ids & tagnt_strong_ids)
    hungarian_not_used = sorted(hungarian_strong_ids - tagnt_strong_ids)

    covered_token_count = sum(
        1 for strong_ids in tagnt.token_strong_ids if strong_ids and any(
            strong_id in hungarian_strong_ids for strong_id in strong_ids
        )
    )
    alias_covered_token_count = sum(
        1 for strong_ids in tagnt.token_strong_ids if strong_ids
        and not any(strong_id in hungarian_strong_ids for strong_id in strong_ids)
        and any(strong_id in alias_resolved_strong_ids for strong_id in strong_ids)
    )
    uncovered_token_count = sum(
        1 for strong_ids in tagnt.token_strong_ids if strong_ids and not any(
            strong_id in hungarian_strong_ids for strong_id in strong_ids
        )
    )
    effective_uncovered_token_count = sum(
        1 for strong_ids in tagnt.token_strong_ids if strong_ids
        and not any(
            strong_id in hungarian_strong_ids or strong_id in alias_resolved_strong_ids
            for strong_id in strong_ids
        )
    )
    lexical_token_count = covered_token_count + uncovered_token_count
    effective_covered_token_count = covered_token_count + alias_covered_token_count
    unresolved_strong_ids = sorted(
        tagnt_strong_ids - hungarian_strong_ids - alias_resolved_strong_ids
    )
    coverage_percent = (
        round((covered_token_count / lexical_token_count) * 100, 2)
        if lexical_token_count
        else 0.0
    )

    summary: dict[str, int | float] = {
        "tagnt_total_tokens": tagnt.token_count,
        "tagnt_unique_strong_ids": len(tagnt_strong_ids),
        "tagnt_tokens_without_strong_id": tagnt.missing_strong_token_count,
        "tagnt_strong_ids_found_in_tbesg": len(tagnt_strong_ids & tbesg_strong_ids),
        "tagnt_strong_ids_missing_from_tbesg": len(missing_tbesg),
        "tagnt_strong_ids_found_in_hungarian": len(hungarian_used),
        "tagnt_strong_ids_missing_from_hungarian": len(missing_hungarian),
        "tagnt_tokens_with_hungarian_lexicon": covered_token_count,
        "tagnt_tokens_without_hungarian_lexicon": uncovered_token_count,
        "tagnt_token_hungarian_coverage_percent": coverage_percent,
        "tagnt_lexeme_hungarian_coverage_percent": round(
            (len(hungarian_used) / len(tagnt_strong_ids)) * 100, 2
        )
        if tagnt_strong_ids
        else 0.0,
        "hungarian_strong_ids_not_used_in_tagnt": len(hungarian_not_used),
        "direct_hungarian_token_count": covered_token_count,
        "direct_hungarian_lexeme_count": len(hungarian_used),
        "direct_hungarian_token_coverage_percent": coverage_percent,
        "direct_hungarian_lexeme_coverage_percent": round(
            (len(hungarian_used) / len(tagnt_strong_ids)) * 100, 2
        )
        if tagnt_strong_ids
        else 0.0,
        "alias_hungarian_token_count": alias_covered_token_count,
        "alias_hungarian_lexeme_count": len(alias_resolved_strong_ids),
        "alias_hungarian_token_coverage_percent": round(
            (alias_covered_token_count / lexical_token_count) * 100, 2
        )
        if lexical_token_count
        else 0.0,
        "alias_hungarian_lexeme_coverage_percent": round(
            (len(alias_resolved_strong_ids) / len(tagnt_strong_ids)) * 100, 2
        )
        if tagnt_strong_ids
        else 0.0,
        "effective_tokens_with_hungarian_lexicon": effective_covered_token_count,
        "effective_lexemes_with_hungarian_lexicon": len(hungarian_used)
        + len(alias_resolved_strong_ids),
        "effective_token_coverage": round(
            (effective_covered_token_count / lexical_token_count) * 100, 2
        )
        if lexical_token_count
        else 0.0,
        "effective_lexeme_coverage": round(
            ((len(hungarian_used) + len(alias_resolved_strong_ids)) / len(tagnt_strong_ids))
            * 100,
            2,
        )
        if tagnt_strong_ids
        else 0.0,
        "unresolved_strong_id_count": len(unresolved_strong_ids),
        "unresolved_token_count": effective_uncovered_token_count,
    }
    data = {
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "missing_hungarian_strong_ids": missing_hungarian,
        "missing_tbesg_strong_ids": missing_tbesg,
        "tagnt_strong_ids": sorted(tagnt_strong_ids),
        "hungarian_strong_ids_used_in_nt": hungarian_used,
        "hungarian_strong_ids_not_used_in_nt": hungarian_not_used,
        "direct_hungarian_coverage": {
            "strong_ids": hungarian_used,
            "token_count": covered_token_count,
            "lexeme_count": len(hungarian_used),
            "token_coverage_percent": coverage_percent,
            "lexeme_coverage_percent": summary["direct_hungarian_lexeme_coverage_percent"],
        },
        "alias_hungarian_coverage": {
            "strong_ids": sorted(alias_resolved_strong_ids),
            "token_count": alias_covered_token_count,
            "lexeme_count": len(alias_resolved_strong_ids),
            "token_coverage_percent": summary["alias_hungarian_token_coverage_percent"],
            "lexeme_coverage_percent": summary["alias_hungarian_lexeme_coverage_percent"],
        },
        "unresolved_strong_ids": unresolved_strong_ids,
        "unresolved_token_count": effective_uncovered_token_count,
        "effective_token_coverage": summary["effective_token_coverage"],
        "effective_lexeme_coverage": summary["effective_lexeme_coverage"],
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return CoverageAuditReport(
        output_path=str(output),
        summary=summary,
        missing_hungarian_strong_ids=tuple(missing_hungarian),
        missing_tbesg_strong_ids=tuple(missing_tbesg),
    )


def export_nt_missing_lexicon_batch(
    *,
    output_path: str | Path,
    limit: int = 1000,
    offset: int = 0,
    tagnt_database_path: str | Path | None = None,
    tbesg_database_path: str | Path | None = None,
    hungarian_lexicon_path: str | Path = DEFAULT_HUNGARIAN_LEXICON_PATH,
) -> NTMissingExportReport:
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    if offset < 0:
        raise ValueError("offset must not be negative.")

    tbesg_database = Path(tbesg_database_path) if tbesg_database_path is not None else resolve_tbesg_database_path()
    if not tbesg_database.exists():
        raise FileNotFoundError(f"TBESG SQLite database not found: {tbesg_database}")

    tagnt = collect_tagnt_strong_frequencies(tagnt_database_path)
    translated = _load_hungarian_strong_ids(hungarian_lexicon_path)
    missing_ids = sorted(
        (strong_id for strong_id in tagnt.frequencies if strong_id not in translated),
        key=lambda strong_id: (-tagnt.frequencies[strong_id], strong_id),
    )
    selected_ids = missing_ids[offset : offset + limit]

    records: list[dict[str, object]] = []
    warnings: list[str] = []
    for strong_id in selected_ids:
        entry = get_sqlite_lexicon_entry(tbesg_database, strong_id)
        if entry is None:
            warnings.append(f"TBESG source record not found: {strong_id}")
            continue
        records.append(_export_record(entry, tagnt.frequencies[strong_id]))

    data = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source": NT_COVERAGE_SOURCE_NAME,
        "batch": {
            "source": NT_COVERAGE_SOURCE_NAME,
            "limit": limit,
            "offset": offset,
            "order_by": NT_FREQUENCY_ORDER,
            "total_missing_nt_records": len(missing_ids),
        },
        "records": records,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return NTMissingExportReport(
        output_path=str(output),
        records_exported=len(records),
        limit=limit,
        offset=offset,
        total_missing_nt_records=len(missing_ids),
        warnings=tuple(warnings),
        first_strong_id=records[0]["strong_id"] if records else None,
        last_strong_id=records[-1]["strong_id"] if records else None,
    )


def _load_tbesg_strong_ids(database_path: str | Path | None) -> set[str]:
    database = Path(database_path) if database_path is not None else resolve_tbesg_database_path()
    if not database.exists():
        raise FileNotFoundError(f"TBESG SQLite database not found: {database}")
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT strong_id FROM greek_lexicon").fetchall()
    strong_ids: set[str] = set()
    for (raw_strong_id,) in rows:
        try:
            strong_ids.add(normalize_greek_strong_id(str(raw_strong_id)))
        except ValueError:
            continue
    return strong_ids


def _load_hungarian_strong_ids(path: str | Path) -> set[str]:
    return set(_load_hungarian_entries(path))


def _load_hungarian_entries(path: str | Path):
    source = Path(path)
    if not source.exists():
        return {}
    return load_hungarian_lexicon(source)


def _load_strong_aliases_if_available(path: str | Path):
    try:
        return load_strong_aliases(path)
    except (FileNotFoundError, ValueError):
        return {}
