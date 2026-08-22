"""Read-only repository and runtime bootstrap for local hymn data.

The repository is the application-facing boundary for hymn data. It never
generates hymn numbers, first lines, or titles; those values must come from
the validated SQLite database.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from bible_engine.hymn_sqlite import DEFAULT_DATABASE_PATH, resolve_database_path


EXPECTED_ERE_SOURCE_CHECKSUM = (
    "f2afd902096e11899e650e5e77fe1b5829e25ee0a31420405f4181534f8719bb"
)
EXPECTED_ERE_HYMN_COUNT = 513
EXPECTED_ERE_BASE_NUMBER_COUNT = 504
EXPECTED_ERE_SECTION_COUNT = 44
EXPECTED_ERE_STANZA_COUNT = 2697
EXPECTED_ERE_PARSER_WARNING_COUNT = 0
EXPECTED_RE21_SOURCE_CHECKSUM = (
    "c5075014a35aa843707c4a196409f46bfcf86ab950928724d5e36a43cecdbb51"
)
EXPECTED_RE21_HYMN_COUNT = 667
EXPECTED_RE21_BASE_NUMBER_COUNT = 667
EXPECTED_RE21_SECTION_COUNT = 39
EXPECTED_RE21_STANZA_COUNT = 3783
EXPECTED_RE21_PARSER_WARNING_COUNT = 0
EXPECTED_RE48_SOURCE_CHECKSUM = (
    "3f6ebf59731263db17b7366ac4bde1f4a8515db01d5859f6c8fbbfbfb725d677"
)
EXPECTED_RE48_HYMN_COUNT = 512
EXPECTED_RE48_BASE_NUMBER_COUNT = 512
EXPECTED_RE48_SECTION_COUNT = 0
EXPECTED_RE48_STANZA_COUNT = 3259
EXPECTED_RE48_PARSER_WARNING_COUNT = 0
EXPECTED_SCHEMA_VERSION = "1"

HYMN_STORAGE_BUCKET_ENV_VAR = "TEXTUS_HYMN_DB_STORAGE_BUCKET"
HYMN_STORAGE_OBJECT_ENV_VAR = "TEXTUS_HYMN_DB_STORAGE_OBJECT"
HYMN_DATABASE_SHA256_ENV_VAR = "TEXTUS_HYMN_DB_SHA256"

REQUIRED_TABLES = frozenset(
    {"hymnals", "sections", "hymns", "stanzas", "import_meta", "hymns_fts"}
)


@dataclass(frozen=True)
class HymnRepositoryStatus:
    available: bool
    reason: str
    database_path: str
    detail: str = ""


@dataclass(frozen=True)
class HymnalInfo:
    code: str
    title: str
    source_format: str
    source_version: str
    source_checksum: str
    imported_at: str


@dataclass(frozen=True)
class HymnRecord:
    hymn_id: str
    hymnal_code: str
    number: int
    variant: str
    display_number: str
    first_line: str
    title: str
    section: str
    parent_section: str


@dataclass(frozen=True)
class HymnSearchResult:
    hymn: HymnRecord
    match_text: str = ""


def get_status(database_path: str | Path | None = None) -> HymnRepositoryStatus:
    path = resolve_database_path(database_path)
    return _validate_database(path)


def ensure_hymn_database(
    database_path: str | Path | None = None,
    *,
    storage_bucket_id: str | None = None,
    storage_object_path: str | None = None,
    expected_database_sha256: str | None = None,
) -> HymnRepositoryStatus:
    """Ensure a valid local hymn SQLite file, downloading a prebuilt DB if needed.

    The download path mirrors `ruf_bible_local_db.ensure_local_database`: it uses
    the existing Supabase credentials loader and writes a temporary `.part` file
    before replacing the target. The production artifact is the SQLite DB, not
    the DTX source.
    """
    path = resolve_database_path(database_path)
    status = _validate_database(path)
    if status.available:
        return status

    bucket_id = storage_bucket_id or _configured_storage_bucket_id()
    object_path = storage_object_path or _configured_storage_object_path()
    if not bucket_id or not object_path:
        return HymnRepositoryStatus(
            available=False,
            reason="storage_not_configured",
            database_path=str(path),
            detail=status.reason,
        )

    try:
        from supabase_client import get_supabase_client

        client = get_supabase_client()
        data = client.storage.from_(bucket_id).download(object_path)
    except Exception as exc:  # noqa: BLE001 - runtime bootstrap must fail closed
        return HymnRepositoryStatus(
            available=False,
            reason="download_failed",
            database_path=str(path),
            detail=str(exc),
        )
    if not data:
        return HymnRepositoryStatus(
            available=False,
            reason="download_empty",
            database_path=str(path),
        )

    expected_db_hash = expected_database_sha256 or _configured_database_sha256()
    if expected_db_hash and _sha256_bytes(data) != expected_db_hash:
        return HymnRepositoryStatus(
            available=False,
            reason="database_checksum_mismatch",
            database_path=str(path),
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    try:
        tmp_path.write_bytes(data)
        downloaded_status = _validate_database(tmp_path)
        if not downloaded_status.available:
            return HymnRepositoryStatus(
                available=False,
                reason=downloaded_status.reason,
                database_path=str(path),
                detail=downloaded_status.detail,
            )
        tmp_path.replace(path)
    except OSError as exc:
        return HymnRepositoryStatus(
            available=False,
            reason="write_failed",
            database_path=str(path),
            detail=str(exc),
        )
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return _validate_database(path)


def list_hymnals(database_path: str | Path | None = None) -> list[HymnalInfo]:
    conn = _open_available_database(database_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT code, title, source_format, COALESCE(source_version, '') AS source_version,
                   source_checksum, imported_at
            FROM hymnals
            ORDER BY code
            """
        ).fetchall()
        return [
            HymnalInfo(
                code=row["code"],
                title=row["title"],
                source_format=row["source_format"],
                source_version=row["source_version"],
                source_checksum=row["source_checksum"],
                imported_at=row["imported_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()


def get_hymn_by_id(
    hymn_id: str,
    database_path: str | Path | None = None,
) -> HymnRecord | None:
    parsed = _parse_hymn_id(hymn_id)
    if parsed is None:
        return None
    hymnal_code, canonical_key = parsed
    conn = _open_available_database(database_path)
    if conn is None:
        return None
    try:
        row = conn.execute(_HYMN_SELECT_SQL + " WHERE hy.code = ? AND h.canonical_key = ?",
                           (hymnal_code, canonical_key)).fetchone()
        return _hymn_from_row(row) if row else None
    finally:
        conn.close()


def get_hymn_by_number(
    hymnal_code: str,
    number: int,
    variant: str | None = None,
    database_path: str | Path | None = None,
) -> HymnRecord | None:
    conn = _open_available_database(database_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            _HYMN_SELECT_SQL
            + """
              WHERE hy.code = ? AND h.number = ? AND COALESCE(h.variant, '') = ?
            """,
            (hymnal_code, int(number), _normalize_variant(variant)),
        ).fetchone()
        return _hymn_from_row(row) if row else None
    finally:
        conn.close()


def search_hymns(
    query: str,
    hymnal_codes: Iterable[str] | None = None,
    *,
    limit: int = 20,
    database_path: str | Path | None = None,
) -> list[HymnSearchResult]:
    q = (query or "").strip()
    if not q:
        return []
    conn = _open_available_database(database_path)
    if conn is None:
        return []
    try:
        codes = _normalize_hymnal_codes(hymnal_codes)
        code_sql = ""
        params: list[object] = [_fts_phrase_query(q)]
        if codes:
            placeholders = ",".join("?" for _ in codes)
            code_sql = f" AND f.hymnal_code IN ({placeholders})"
            params.extend(codes)
        exact = f"%{q}%"
        params.extend([exact, exact, int(limit)])
        rows = conn.execute(
            """
            SELECT
                h.id AS sqlite_hymn_id,
                hy.code AS hymnal_code,
                h.canonical_key,
                h.number,
                COALESCE(h.variant, '') AS variant,
                h.first_line,
                h.title,
                COALESCE(s.title, '') AS section_title,
                COALESCE(ps.title, '') AS parent_section_title,
                snippet(hymns_fts, 4, '**', '**', '...', 16) AS match_text
            FROM hymns_fts f
            JOIN hymnals hy ON hy.code = f.hymnal_code
            JOIN hymns h ON h.hymnal_id = hy.id AND h.canonical_key = f.canonical_key
            LEFT JOIN sections s ON s.id = h.section_id
            LEFT JOIN sections ps ON ps.id = s.parent_id
            WHERE f.hymns_fts MATCH ?
            """
            + code_sql
            + """
            ORDER BY
                CASE
                    WHEN h.first_line LIKE ? THEN 0
                    WHEN h.title LIKE ? THEN 1
                    ELSE 2
                END,
                h.number_sort,
                h.canonical_key
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            HymnSearchResult(hymn=_hymn_from_row(row), match_text=row["match_text"] or "")
            for row in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_hymn_candidates(
    query: str,
    hymnal_codes: Iterable[str] | None = None,
    *,
    limit: int = 20,
    database_path: str | Path | None = None,
) -> list[HymnRecord]:
    return [
        result.hymn
        for result in search_hymns(
            query,
            hymnal_codes=hymnal_codes,
            limit=limit,
            database_path=database_path,
        )
    ]


def validate_hymn_ids(
    hymn_ids: Iterable[str],
    database_path: str | Path | None = None,
) -> dict[str, HymnRecord]:
    ids = list(dict.fromkeys(str(hymn_id).strip() for hymn_id in hymn_ids if str(hymn_id).strip()))
    if not ids:
        return {}
    conn = _open_available_database(database_path)
    if conn is None:
        return {}
    valid: dict[str, HymnRecord] = {}
    try:
        for hymn_id in ids:
            parsed = _parse_hymn_id(hymn_id)
            if parsed is None:
                continue
            hymnal_code, canonical_key = parsed
            row = conn.execute(
                _HYMN_SELECT_SQL + " WHERE hy.code = ? AND h.canonical_key = ?",
                (hymnal_code, canonical_key),
            ).fetchone()
            if row:
                valid[hymn_id] = _hymn_from_row(row)
        return valid
    finally:
        conn.close()


def database_exists(database_path: str | Path | None = None) -> bool:
    return resolve_database_path(database_path).is_file()


_HYMN_SELECT_SQL = """
    SELECT
        h.id AS sqlite_hymn_id,
        hy.code AS hymnal_code,
        h.canonical_key,
        h.number,
        COALESCE(h.variant, '') AS variant,
        h.first_line,
        h.title,
        COALESCE(s.title, '') AS section_title,
        COALESCE(ps.title, '') AS parent_section_title
    FROM hymns h
    JOIN hymnals hy ON hy.id = h.hymnal_id
    LEFT JOIN sections s ON s.id = h.section_id
    LEFT JOIN sections ps ON ps.id = s.parent_id
"""


def _validate_database(path: Path) -> HymnRepositoryStatus:
    if not path.is_file():
        return HymnRepositoryStatus(False, "database_missing", str(path))
    conn = _open_readonly(path)
    if conn is None:
        return HymnRepositoryStatus(False, "database_unopenable", str(path))
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            return HymnRepositoryStatus(False, "database_corrupt", str(path), str(integrity))
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        }
        if not REQUIRED_TABLES.issubset(tables):
            missing = ", ".join(sorted(REQUIRED_TABLES - tables))
            return HymnRepositoryStatus(False, "schema_incompatible", str(path), missing)
        schema_version = _meta(conn, "schema_version")
        if schema_version != EXPECTED_SCHEMA_VERSION:
            return HymnRepositoryStatus(
                False,
                "schema_incompatible",
                str(path),
                f"schema_version={schema_version or '<missing>'}",
            )
        ere_summary = _summary_counts(conn, "ERE")
        if ere_summary is None:
            return HymnRepositoryStatus(False, "hymnal_missing", str(path), "ERE")
        mismatches = _hymnal_mismatches(
            "ERE",
            ere_summary,
            expected_source_checksum=EXPECTED_ERE_SOURCE_CHECKSUM,
            expected_hymn_count=EXPECTED_ERE_HYMN_COUNT,
            expected_base_number_count=EXPECTED_ERE_BASE_NUMBER_COUNT,
            expected_section_count=EXPECTED_ERE_SECTION_COUNT,
            expected_stanza_count=EXPECTED_ERE_STANZA_COUNT,
            expected_parser_warning_count=EXPECTED_ERE_PARSER_WARNING_COUNT,
        )
        re21_summary = _summary_counts(conn, "RE21")
        if re21_summary is not None:
            mismatches.extend(
                _hymnal_mismatches(
                    "RE21",
                    re21_summary,
                    expected_source_checksum=EXPECTED_RE21_SOURCE_CHECKSUM,
                    expected_hymn_count=EXPECTED_RE21_HYMN_COUNT,
                    expected_base_number_count=EXPECTED_RE21_BASE_NUMBER_COUNT,
                    expected_section_count=EXPECTED_RE21_SECTION_COUNT,
                    expected_stanza_count=EXPECTED_RE21_STANZA_COUNT,
                    expected_parser_warning_count=EXPECTED_RE21_PARSER_WARNING_COUNT,
                )
            )
        re48_summary = _summary_counts(conn, "RE48")
        if re48_summary is not None:
            mismatches.extend(
                _hymnal_mismatches(
                    "RE48",
                    re48_summary,
                    expected_source_checksum=EXPECTED_RE48_SOURCE_CHECKSUM,
                    expected_hymn_count=EXPECTED_RE48_HYMN_COUNT,
                    expected_base_number_count=EXPECTED_RE48_BASE_NUMBER_COUNT,
                    expected_section_count=EXPECTED_RE48_SECTION_COUNT,
                    expected_stanza_count=EXPECTED_RE48_STANZA_COUNT,
                    expected_parser_warning_count=EXPECTED_RE48_PARSER_WARNING_COUNT,
                )
            )
        if mismatches:
            return HymnRepositoryStatus(
                False,
                "metadata_validation_failed",
                str(path),
                "; ".join(mismatches),
            )
        return HymnRepositoryStatus(True, "ok", str(path))
    except sqlite3.Error as exc:
        return HymnRepositoryStatus(False, "database_invalid", str(path), str(exc))
    finally:
        conn.close()


def _hymnal_mismatches(
    hymnal_code: str,
    summary: tuple[str, int, int, int, int, int],
    *,
    expected_source_checksum: str,
    expected_hymn_count: int,
    expected_base_number_count: int,
    expected_section_count: int,
    expected_stanza_count: int,
    expected_parser_warning_count: int,
) -> list[str]:
    source_checksum, hymn_count, base_count, section_count, stanza_count, warning_count = summary
    expected = {
        "source_checksum": (source_checksum, expected_source_checksum),
        "hymn_count": (hymn_count, expected_hymn_count),
        "base_number_count": (base_count, expected_base_number_count),
        "section_count": (section_count, expected_section_count),
        "stanza_count": (stanza_count, expected_stanza_count),
        "parser_warning_count": (warning_count, expected_parser_warning_count),
    }
    return [
        f"{hymnal_code}.{name}={actual} expected={want}"
        for name, (actual, want) in expected.items()
        if actual != want
    ]


def _summary_counts(conn: sqlite3.Connection, hymnal_code: str) -> tuple[str, int, int, int, int, int] | None:
    row = conn.execute(
        """
        SELECT
            hy.source_checksum,
            (SELECT COUNT(*) FROM hymns h WHERE h.hymnal_id = hy.id) AS hymn_count,
            (SELECT COUNT(DISTINCT h.number) FROM hymns h WHERE h.hymnal_id = hy.id) AS base_number_count,
            (SELECT COUNT(*) FROM sections s WHERE s.hymnal_id = hy.id) AS section_count,
            (
                SELECT COUNT(*)
                FROM stanzas st
                JOIN hymns h ON h.id = st.hymn_id
                WHERE h.hymnal_id = hy.id
            ) AS stanza_count,
            COALESCE(
                (SELECT value FROM import_meta WHERE key = hy.code || '.parser_warning_count'),
                (SELECT value FROM import_meta WHERE key = 'parser_warning_count'),
                '0'
            )
                AS parser_warning_count
        FROM hymnals hy
        WHERE hy.code = ?
        """,
        (hymnal_code,),
    ).fetchone()
    if row is None:
        return None
    return (
        row["source_checksum"],
        int(row["hymn_count"]),
        int(row["base_number_count"]),
        int(row["section_count"]),
        int(row["stanza_count"]),
        int(row["parser_warning_count"]),
    )


def _open_available_database(database_path: str | Path | None) -> sqlite3.Connection | None:
    path = resolve_database_path(database_path)
    if not _validate_database(path).available:
        return None
    return _open_readonly(path)


def _open_readonly(path: Path) -> sqlite3.Connection | None:
    try:
        if not path.is_file():
            return None
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _hymn_from_row(row: sqlite3.Row) -> HymnRecord:
    variant = row["variant"] or ""
    canonical_key = row["canonical_key"]
    hymnal_code = row["hymnal_code"]
    return HymnRecord(
        hymn_id=f"{hymnal_code}:{canonical_key}",
        hymnal_code=hymnal_code,
        number=int(row["number"]),
        variant=variant,
        display_number=f"{int(row['number'])}{variant}",
        first_line=row["first_line"],
        title=row["title"],
        section=row["section_title"],
        parent_section=row["parent_section_title"],
    )


def _parse_hymn_id(hymn_id: str) -> tuple[str, str] | None:
    text = (hymn_id or "").strip()
    if ":" not in text:
        return None
    code, key = text.split(":", 1)
    code = code.strip()
    key = key.strip()
    if not code or not key:
        return None
    return code, key


def _normalize_variant(variant: str | None) -> str:
    return (variant or "").strip().lower()


def _normalize_hymnal_codes(hymnal_codes: Iterable[str] | None) -> list[str]:
    if hymnal_codes is None:
        return []
    return [str(code).strip() for code in hymnal_codes if str(code).strip()]


def _fts_phrase_query(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def _meta(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM import_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def _configured_storage_bucket_id() -> str:
    env_value = os.environ.get(HYMN_STORAGE_BUCKET_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return _hymn_secret_value("storage_bucket")


def _configured_storage_object_path() -> str:
    env_value = os.environ.get(HYMN_STORAGE_OBJECT_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return _hymn_secret_value("storage_object")


def _configured_database_sha256() -> str:
    env_value = os.environ.get(HYMN_DATABASE_SHA256_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return _hymn_secret_value("database_sha256")


def _hymn_secret_value(key: str) -> str:
    try:
        import streamlit as st

        cfg = st.secrets.get("hymn_database", {})
        if isinstance(cfg, dict):
            value = cfg.get(key)
        else:
            value = getattr(cfg, key, "")
        return str(value or "").strip()
    except Exception:
        return ""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "EXPECTED_ERE_SOURCE_CHECKSUM",
    "EXPECTED_RE21_SOURCE_CHECKSUM",
    "EXPECTED_RE48_SOURCE_CHECKSUM",
    "HYMN_DATABASE_SHA256_ENV_VAR",
    "HYMN_STORAGE_BUCKET_ENV_VAR",
    "HYMN_STORAGE_OBJECT_ENV_VAR",
    "HymnRecord",
    "HymnRepositoryStatus",
    "HymnSearchResult",
    "HymnalInfo",
    "database_exists",
    "ensure_hymn_database",
    "get_hymn_by_id",
    "get_hymn_by_number",
    "get_hymn_candidates",
    "get_status",
    "list_hymnals",
    "search_hymns",
    "validate_hymn_ids",
]
