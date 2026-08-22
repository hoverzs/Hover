from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bible_engine.hymn_docx_parser import parse_docx_file
from bible_engine.hymn_dtx_parser import Hymn, HymnalDocument, Section, parse_dtx_file
from bible_engine.paths import GENERATED_DATA_DIR


DATABASE_NAME = "hymns.sqlite3"
DEFAULT_DATABASE_PATH = GENERATED_DATA_DIR / DATABASE_NAME
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class HymnImportReport:
    database_path: str
    hymnal_code: str
    source_path: str
    source_checksum: str
    hymn_count: int
    base_number_count: int
    section_count: int
    stanza_count: int
    parser_warning_count: int
    built_at: str


@dataclass(frozen=True)
class HymnalSourceConfig:
    code: str
    source_path: str | Path
    source_format: str
    title: str = ""
    source_version: str = ""


@dataclass(frozen=True)
class HymnalSummary:
    code: str
    title: str
    dtx_code: str
    source_format: str
    source_version: str
    source_checksum: str
    imported_at: str
    hymn_count: int
    base_number_count: int
    section_count: int
    stanza_count: int
    parser_warning_count: int


@dataclass(frozen=True)
class HymnLookup:
    hymnal_code: str
    canonical_key: str
    number: int
    variant: str
    first_line: str
    title: str
    title_source: str
    section_title: str
    parent_section_title: str
    stanza_count: int
    raw_source_reference: str


@dataclass(frozen=True)
class HymnSearchHit:
    hymnal_code: str
    canonical_key: str
    number: int
    variant: str
    first_line: str
    title: str
    section_title: str
    match_text: str


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    return Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS hymnals (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            dtx_code TEXT,
            source_format TEXT NOT NULL,
            source_version TEXT,
            source_checksum TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY,
            hymnal_id INTEGER NOT NULL,
            parent_id INTEGER,
            title TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            FOREIGN KEY(hymnal_id) REFERENCES hymnals(id) ON DELETE CASCADE,
            FOREIGN KEY(parent_id) REFERENCES sections(id) ON DELETE SET NULL,
            UNIQUE(hymnal_id, ordinal)
        );

        CREATE TABLE IF NOT EXISTS hymns (
            id INTEGER PRIMARY KEY,
            hymnal_id INTEGER NOT NULL,
            section_id INTEGER,
            number INTEGER NOT NULL,
            variant TEXT,
            number_sort REAL NOT NULL,
            canonical_key TEXT NOT NULL,
            first_line TEXT NOT NULL,
            title TEXT NOT NULL,
            title_source TEXT NOT NULL,
            raw_source_reference TEXT NOT NULL,
            FOREIGN KEY(hymnal_id) REFERENCES hymnals(id) ON DELETE CASCADE,
            FOREIGN KEY(section_id) REFERENCES sections(id) ON DELETE SET NULL,
            UNIQUE(hymnal_id, canonical_key)
        );

        CREATE TABLE IF NOT EXISTS stanzas (
            id INTEGER PRIMARY KEY,
            hymn_id INTEGER NOT NULL,
            stanza_no INTEGER NOT NULL,
            first_line TEXT NOT NULL,
            text TEXT NOT NULL,
            heading TEXT,
            technical_hash TEXT,
            FOREIGN KEY(hymn_id) REFERENCES hymns(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS import_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sections_hymnal_parent
            ON sections(hymnal_id, parent_id, ordinal);
        CREATE INDEX IF NOT EXISTS idx_hymns_hymnal_number
            ON hymns(hymnal_id, number, variant);
        CREATE INDEX IF NOT EXISTS idx_hymns_hymnal_canonical
            ON hymns(hymnal_id, canonical_key);
        CREATE INDEX IF NOT EXISTS idx_stanzas_hymn
            ON stanzas(hymn_id, stanza_no);

        CREATE VIRTUAL TABLE IF NOT EXISTS hymns_fts USING fts5(
            hymnal_code UNINDEXED,
            canonical_key UNINDEXED,
            hymn_first_line,
            hymn_title,
            stanza_text,
            stanza_first_line,
            section_title,
            tokenize='unicode61'
        );
        """
    )
    connection.commit()


def import_dtx_hymnal_database(
    source_path: str | Path,
    database_path: str | Path,
    *,
    hymnal_code: str,
    source_version: str = "",
    atomic: bool = True,
) -> HymnImportReport:
    reports = import_hymnals_database(
        [
            HymnalSourceConfig(
                code=hymnal_code,
                source_path=source_path,
                source_format="dtx",
                source_version=source_version,
            )
        ],
        database_path,
        atomic=atomic,
    )
    return reports[0]


def import_hymnals_database(
    sources: list[HymnalSourceConfig] | tuple[HymnalSourceConfig, ...],
    database_path: str | Path,
    *,
    atomic: bool = True,
) -> tuple[HymnImportReport, ...]:
    if not sources:
        raise ValueError("At least one hymnal source must be provided.")
    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    target = _temporary_database_path(database) if atomic else database
    if target.exists():
        target.unlink()

    built_at = datetime.now(UTC).isoformat()
    loaded = [_load_source(config) for config in sources]

    connection = sqlite3.connect(target)
    reports: list[HymnImportReport] = []
    try:
        create_schema(connection)
        metadata: dict[str, str] = {
            "schema_version": str(SCHEMA_VERSION),
            "hymnal_codes": json.dumps([item["config"].code for item in loaded], ensure_ascii=False),
            "build_timestamp": built_at,
        }
        for item in loaded:
            config = item["config"]
            document = item["document"]
            checksum = item["checksum"]
            source = item["source"]
            normalized_format = item["source_format"]
            stanza_count = sum(len(hymn.stanzas) for hymn in document.hymns)
            base_number_count = len({hymn.number for hymn in document.hymns})
            warning_count = len(document.warnings)

            _insert_document(
                connection,
                document,
                hymnal_code=config.code,
                title_override=config.title,
                source_format=normalized_format,
                source_checksum=checksum,
                source_version=config.source_version,
                imported_at=built_at,
            )
            metadata.update(
                {
                    f"{config.code}.source_path": str(source),
                    f"{config.code}.source_checksum": checksum,
                    f"{config.code}.source_format": normalized_format,
                    f"{config.code}.source_version": config.source_version,
                    f"{config.code}.hymn_count": str(len(document.hymns)),
                    f"{config.code}.base_number_count": str(base_number_count),
                    f"{config.code}.section_count": str(len(document.sections)),
                    f"{config.code}.stanza_count": str(stanza_count),
                    f"{config.code}.parser_warning_count": str(warning_count),
                }
            )
            reports.append(
                HymnImportReport(
                    database_path=str(database),
                    hymnal_code=config.code,
                    source_path=str(source),
                    source_checksum=checksum,
                    hymn_count=len(document.hymns),
                    base_number_count=base_number_count,
                    section_count=len(document.sections),
                    stanza_count=stanza_count,
                    parser_warning_count=warning_count,
                    built_at=built_at,
                )
            )

        first = reports[0]
        metadata.update(
            {
                "hymnal_code": first.hymnal_code,
                "source_path": first.source_path,
                "source_checksum": first.source_checksum,
                "source_format": loaded[0]["source_format"],
                "source_version": loaded[0]["config"].source_version,
                "hymn_count": str(first.hymn_count),
                "base_number_count": str(first.base_number_count),
                "section_count": str(first.section_count),
                "stanza_count": str(first.stanza_count),
                "parser_warning_count": str(first.parser_warning_count),
            }
        )
        _set_import_meta(connection, metadata)
        _rebuild_fts(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Invalid hymn SQLite integrity_check: {integrity}")
        connection.commit()
    finally:
        connection.close()

    if atomic:
        _replace_atomically(target, database)

    return tuple(reports)


def get_hymnal_summary(
    database_path: str | Path | None = None,
    *,
    hymnal_code: str = "ERE",
) -> HymnalSummary | None:
    path = resolve_database_path(database_path)
    conn = _open_readonly(path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            """
            SELECT
                hy.code, hy.title, hy.dtx_code, hy.source_format,
                COALESCE(hy.source_version, '') AS source_version,
                hy.source_checksum, hy.imported_at,
                (SELECT COUNT(*) FROM hymns h WHERE h.hymnal_id = hy.id)
                    AS hymn_count,
                (SELECT COUNT(DISTINCT h.number) FROM hymns h WHERE h.hymnal_id = hy.id)
                    AS base_number_count,
                (SELECT COUNT(*) FROM sections s WHERE s.hymnal_id = hy.id)
                    AS section_count,
                (
                    SELECT COUNT(*)
                    FROM stanzas st
                    JOIN hymns h ON h.id = st.hymn_id
                    WHERE h.hymnal_id = hy.id
                ) AS stanza_count,
                COALESCE(
                    MAX(CASE WHEN im.key = hy.code || '.parser_warning_count' THEN im.value END),
                    MAX(CASE WHEN im.key = 'parser_warning_count' THEN im.value END),
                    '0'
                )
                    AS parser_warning_count
            FROM hymnals hy
            LEFT JOIN import_meta im
                ON im.key IN (hy.code || '.parser_warning_count', 'parser_warning_count')
            WHERE hy.code = ?
            GROUP BY hy.id
            """,
            (hymnal_code,),
        ).fetchone()
        if row is None:
            return None
        return HymnalSummary(
            code=row["code"],
            title=row["title"],
            dtx_code=row["dtx_code"] or "",
            source_format=row["source_format"],
            source_version=row["source_version"],
            source_checksum=row["source_checksum"],
            imported_at=row["imported_at"],
            hymn_count=int(row["hymn_count"]),
            base_number_count=int(row["base_number_count"]),
            section_count=int(row["section_count"]),
            stanza_count=int(row["stanza_count"]),
            parser_warning_count=int(row["parser_warning_count"]),
        )
    finally:
        conn.close()


def get_hymn_by_number(
    database_path: str | Path | None,
    hymnal_code: str,
    number: int,
    variant: str = "",
) -> HymnLookup | None:
    path = resolve_database_path(database_path)
    conn = _open_readonly(path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            """
            SELECT
                hy.code AS hymnal_code,
                h.canonical_key,
                h.number,
                COALESCE(h.variant, '') AS variant,
                h.first_line,
                h.title,
                h.title_source,
                COALESCE(s.title, '') AS section_title,
                COALESCE(ps.title, '') AS parent_section_title,
                h.raw_source_reference,
                COUNT(st.id) AS stanza_count
            FROM hymns h
            JOIN hymnals hy ON hy.id = h.hymnal_id
            LEFT JOIN sections s ON s.id = h.section_id
            LEFT JOIN sections ps ON ps.id = s.parent_id
            LEFT JOIN stanzas st ON st.hymn_id = h.id
            WHERE hy.code = ? AND h.number = ? AND COALESCE(h.variant, '') = ?
            GROUP BY h.id
            """,
            (hymnal_code, int(number), (variant or "").strip()),
        ).fetchone()
        return _hymn_lookup_from_row(row) if row else None
    finally:
        conn.close()


def search_fts(
    database_path: str | Path | None,
    query: str,
    *,
    hymnal_code: str = "ERE",
    limit: int = 20,
) -> list[HymnSearchHit]:
    q = (query or "").strip()
    if not q:
        return []
    path = resolve_database_path(database_path)
    conn = _open_readonly(path)
    if conn is None:
        return []
    try:
        sql = """
            SELECT
                hy.code AS hymnal_code,
                h.canonical_key,
                h.number,
                COALESCE(h.variant, '') AS variant,
                h.first_line,
                h.title,
                COALESCE(s.title, '') AS section_title,
                snippet(hymns_fts, 4, '**', '**', '...', 16) AS match_text
            FROM hymns_fts f
            JOIN hymnals hy ON hy.code = f.hymnal_code
            JOIN hymns h ON h.hymnal_id = hy.id AND h.canonical_key = f.canonical_key
            LEFT JOIN sections s ON s.id = h.section_id
            WHERE f.hymns_fts MATCH ? AND f.hymnal_code = ?
            ORDER BY h.number_sort, h.canonical_key
            LIMIT ?
        """
        sql = sql.replace(
            "ORDER BY h.number_sort, h.canonical_key",
            """
            ORDER BY
                CASE
                    WHEN h.first_line LIKE ? THEN 0
                    WHEN h.title LIKE ? THEN 1
                    ELSE 2
                END,
                h.number_sort,
                h.canonical_key
            """,
        )
        exact = f"%{q}%"
        rows = conn.execute(
            sql,
            (_fts_phrase_query(q), hymnal_code, exact, exact, int(limit)),
        ).fetchall()
        return [
            HymnSearchHit(
                hymnal_code=row["hymnal_code"],
                canonical_key=row["canonical_key"],
                number=int(row["number"]),
                variant=row["variant"],
                first_line=row["first_line"],
                title=row["title"],
                section_title=row["section_title"],
                match_text=row["match_text"] or "",
            )
            for row in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _insert_document(
    connection: sqlite3.Connection,
    document: Any,
    *,
    hymnal_code: str,
    title_override: str = "",
    source_format: str,
    source_checksum: str,
    source_version: str,
    imported_at: str,
) -> None:
    cursor = connection.execute(
        """
        INSERT INTO hymnals(
            code, title, dtx_code, source_format, source_version, source_checksum, imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hymnal_code,
            title_override or document.metadata.title,
            getattr(document.metadata, "dtx_code", ""),
            source_format,
            source_version,
            source_checksum,
            imported_at,
        ),
    )
    hymnal_id = int(cursor.lastrowid)
    section_ids = _insert_sections(connection, hymnal_id, document.sections)
    for hymn in document.hymns:
        _insert_hymn(connection, hymnal_id, section_ids, hymn)


def _insert_sections(
    connection: sqlite3.Connection,
    hymnal_id: int,
    sections: tuple[Any, ...],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for section in sections:
        parent_id = ids.get(section.parent_ordinal or -1)
        cursor = connection.execute(
            """
            INSERT INTO sections(hymnal_id, parent_id, title, ordinal)
            VALUES (?, ?, ?, ?)
            """,
            (hymnal_id, parent_id, section.title, section.ordinal),
        )
        ids[section.ordinal] = int(cursor.lastrowid)
    return ids


def _insert_hymn(
    connection: sqlite3.Connection,
    hymnal_id: int,
    section_ids: dict[int, int],
    hymn: Any,
) -> None:
    section_id = section_ids.get(hymn.section.ordinal) if hymn.section else None
    cursor = connection.execute(
        """
        INSERT INTO hymns(
            hymnal_id, section_id, number, variant, number_sort, canonical_key,
            first_line, title, title_source, raw_source_reference
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hymnal_id,
            section_id,
            hymn.number,
            hymn.variant or None,
            _number_sort(hymn.number, hymn.variant),
            _canonical_key(hymn),
            hymn.first_line,
            hymn.title,
            hymn.title_source,
            _raw_source_reference(hymn),
        ),
    )
    hymn_id = int(cursor.lastrowid)
    for stanza in hymn.stanzas:
        connection.execute(
            """
            INSERT INTO stanzas(
                hymn_id, stanza_no, first_line, text, heading, technical_hash
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                hymn_id,
                stanza.number,
                stanza.first_line,
                stanza.text,
                getattr(stanza, "heading", "") or None,
                getattr(stanza, "technical_hash", "") or None,
            ),
        )


def _load_source(config: HymnalSourceConfig) -> dict[str, Any]:
    source = Path(config.source_path)
    if not source.exists():
        raise FileNotFoundError(f"Hymnal source file not found: {source}")
    source_format = _normalized_source_format(config.source_format)
    if source_format == "DiaTar DTX":
        document = parse_dtx_file(source, code=config.code)
    elif source_format == "docx":
        document = parse_docx_file(
            source,
            code=config.code,
            title=config.title or "Református Énekeskönyv 2021",
        )
    else:
        raise ValueError(f"Unsupported hymnal source_format: {config.source_format}")
    return {
        "config": config,
        "source": source,
        "source_format": source_format,
        "checksum": _sha256(source),
        "document": document,
    }


def _normalized_source_format(source_format: str) -> str:
    value = source_format.strip().lower()
    if value in {"dtx", "diatar dtx"}:
        return "DiaTar DTX"
    if value in {"docx", "word docx"}:
        return "docx"
    return source_format.strip()


def _canonical_key(hymn: Any) -> str:
    return getattr(hymn, "key", "") or getattr(hymn, "canonical_key", "")


def _raw_source_reference(hymn: Any) -> str:
    raw = hymn.raw_source
    if hasattr(raw, "start_line"):
        payload = {
            "start_line": raw.start_line,
            "end_line": raw.end_line,
            "header_line": raw.header_line,
        }
    else:
        payload = {
            "start_paragraph": raw.start_paragraph,
            "end_paragraph": raw.end_paragraph,
            "header_paragraph": raw.header_paragraph,
        }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _rebuild_fts(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM hymns_fts")
    connection.execute(
        """
        INSERT INTO hymns_fts(
            hymnal_code, canonical_key, hymn_first_line, hymn_title,
            stanza_text, stanza_first_line, section_title
        )
        SELECT
            hy.code,
            h.canonical_key,
            h.first_line,
            h.title,
            COALESCE(GROUP_CONCAT(st.text, '\n'), ''),
            COALESCE(GROUP_CONCAT(st.first_line, '\n'), ''),
            COALESCE(s.title, '')
        FROM hymns h
        JOIN hymnals hy ON hy.id = h.hymnal_id
        LEFT JOIN stanzas st ON st.hymn_id = h.id
        LEFT JOIN sections s ON s.id = h.section_id
        GROUP BY h.id
        ORDER BY h.number_sort, h.canonical_key
        """
    )


def _set_import_meta(connection: sqlite3.Connection, metadata: dict[str, str]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO import_meta(key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )


def _hymn_lookup_from_row(row: sqlite3.Row) -> HymnLookup:
    return HymnLookup(
        hymnal_code=row["hymnal_code"],
        canonical_key=row["canonical_key"],
        number=int(row["number"]),
        variant=row["variant"],
        first_line=row["first_line"],
        title=row["title"],
        title_source=row["title_source"],
        section_title=row["section_title"],
        parent_section_title=row["parent_section_title"],
        stanza_count=int(row["stanza_count"]),
        raw_source_reference=row["raw_source_reference"],
    )


def _fts_phrase_query(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def _number_sort(number: int, variant: str) -> float:
    if not variant:
        return float(number)
    suffix = ord(variant.lower()[0]) - ord("a") + 1
    return float(number) + suffix / 100.0


def _open_readonly(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temporary_database_path(database: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{database.stem}.",
        suffix=".tmp.sqlite3",
        dir=database.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _replace_atomically(source: Path, target: Path) -> None:
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


__all__ = [
    "DATABASE_NAME",
    "DEFAULT_DATABASE_PATH",
    "SCHEMA_VERSION",
    "HymnImportReport",
    "HymnalSourceConfig",
    "HymnLookup",
    "HymnSearchHit",
    "HymnalSummary",
    "create_schema",
    "get_hymn_by_number",
    "get_hymnal_summary",
    "import_dtx_hymnal_database",
    "import_hymnals_database",
    "resolve_database_path",
    "search_fts",
]
