"""Theology DB v1 SQLite schema, fixture import, and validation.

Isolated store. No network, no vector index, no concept taxonomy.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.paths import PROJECT_ROOT

SCHEMA_VERSION = "1"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "generated" / "theology.sqlite3"
DEFAULT_FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "kb" / "theology_v1_sample.json"
)

IMPORT_MODE_EMPTY = "empty"
IMPORT_MODE_FIXTURE = "fixture"

REQUIRED_EDITION_FIELDS = (
    "rights_status",
    "license",
    "source_url",
    "corpus",
    "external_id",
)

REQUIRED_TABLES = frozenset(
    {
        "store_metadata",
        "authors",
        "works",
        "editions",
        "sections",
        "chunks",
        "passage_links",
        "chunks_fts",
    }
)


class TheologyImportError(ValueError):
    """Raised when a theology fixture cannot be imported."""


@dataclass
class TheologyImportReport:
    database_path: Path
    schema_version: str
    import_mode: str
    content_hash: str
    generated_at: str
    author_count: int
    work_count: int
    edition_count: int
    section_count: int
    chunk_count: int
    passage_link_count: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        return payload


@dataclass
class TheologyStoreValidation:
    schema_version: str
    content_hash: str
    import_mode: str
    generated_at: str
    author_count: int
    work_count: int
    edition_count: int
    section_count: int
    chunk_count: int
    passage_link_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS authors (
            author_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            tradition TEXT,
            birth_year INTEGER,
            death_year INTEGER
        );

        CREATE TABLE IF NOT EXISTS works (
            work_id TEXT PRIMARY KEY,
            author_id TEXT NOT NULL,
            title TEXT NOT NULL,
            original_title TEXT,
            tradition TEXT NOT NULL,
            original_language TEXT,
            FOREIGN KEY(author_id) REFERENCES authors(author_id)
        );

        CREATE TABLE IF NOT EXISTS editions (
            edition_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            edition_label TEXT,
            translator TEXT,
            publication_year INTEGER,
            publisher TEXT,
            language TEXT NOT NULL,
            license TEXT NOT NULL,
            rights_status TEXT NOT NULL,
            rights_note TEXT,
            source_url TEXT NOT NULL,
            corpus TEXT NOT NULL,
            external_id TEXT NOT NULL,
            FOREIGN KEY(work_id) REFERENCES works(work_id)
        );

        CREATE TABLE IF NOT EXISTS sections (
            section_id TEXT PRIMARY KEY,
            edition_id TEXT NOT NULL,
            parent_section_id TEXT,
            section_type TEXT,
            heading TEXT,
            sequence INTEGER NOT NULL,
            FOREIGN KEY(edition_id) REFERENCES editions(edition_id),
            FOREIGN KEY(parent_section_id) REFERENCES sections(section_id)
        );

        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            section_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            text TEXT NOT NULL,
            plain_text TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            source_locator TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES sections(section_id)
        );

        CREATE TABLE IF NOT EXISTS passage_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            book_id TEXT NOT NULL,
            start_chapter INTEGER NOT NULL,
            start_verse INTEGER NOT NULL,
            end_chapter INTEGER NOT NULL,
            end_verse INTEGER NOT NULL,
            canonical_passage TEXT NOT NULL,
            raw_citation TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
        );

        CREATE INDEX IF NOT EXISTS idx_works_author
            ON works(author_id);
        CREATE INDEX IF NOT EXISTS idx_editions_work
            ON editions(work_id);
        CREATE INDEX IF NOT EXISTS idx_sections_edition
            ON sections(edition_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_chunks_section
            ON chunks(section_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_passage_links_chunk
            ON passage_links(chunk_id);
        CREATE INDEX IF NOT EXISTS idx_passage_links_canonical
            ON passage_links(canonical_passage);
        CREATE INDEX IF NOT EXISTS idx_passage_links_book
            ON passage_links(book_id, start_chapter, start_verse);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            heading,
            plain_text,
            tokenize='unicode61'
        );
        """
    )


def create_empty_theology_database(
    database_path: str | Path | None = None,
    *,
    atomic: bool = True,
) -> TheologyImportReport:
    return _write_document(
        _empty_document(),
        database_path=database_path,
        import_mode=IMPORT_MODE_EMPTY,
        atomic=atomic,
    )


def import_theology_sqlite(
    *,
    fixture_path: str | Path | None = None,
    document: dict[str, Any] | None = None,
    database_path: str | Path | None = None,
    import_mode: str = IMPORT_MODE_FIXTURE,
    atomic: bool = True,
) -> TheologyImportReport:
    if document is None and fixture_path is None:
        raise TheologyImportError("Provide fixture_path or document.")
    if document is None:
        document = load_fixture_document(fixture_path)
    normalized = normalize_theology_document(document)
    return _write_document(
        normalized,
        database_path=database_path,
        import_mode=import_mode,
        atomic=atomic,
    )


def load_fixture_document(path: str | Path | None) -> dict[str, Any]:
    fixture = Path(path) if path is not None else DEFAULT_FIXTURE_PATH
    try:
        raw_text = fixture.read_text(encoding="utf-8")
    except OSError as exc:
        raise TheologyImportError(f"Cannot read theology fixture: {fixture}") from exc
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise TheologyImportError(f"Invalid theology fixture JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise TheologyImportError("Theology fixture root must be a JSON object.")
    return payload


def normalize_theology_document(document: dict[str, Any]) -> dict[str, Any]:
    authors = [_normalize_author(item) for item in _as_object_list(document, "authors")]
    author_ids = _unique_ids([item["author_id"] for item in authors], kind="author")

    works = [_normalize_work(item, author_ids) for item in _as_object_list(document, "works")]
    work_ids = _unique_ids([item["work_id"] for item in works], kind="work")

    editions = [
        _normalize_edition(item, work_ids)
        for item in _as_object_list(document, "editions")
    ]
    edition_ids = _unique_ids([item["edition_id"] for item in editions], kind="edition")

    sections_raw = _as_object_list(document, "sections")
    section_ids_preview = _unique_ids(
        [_require_text(item.get("section_id"), "section_id") for item in sections_raw],
        kind="section",
    )
    sections = [
        _normalize_section(item, edition_ids, section_ids_preview)
        for item in sections_raw
    ]
    sections = _order_sections(sections)
    section_ids = {item["section_id"] for item in sections}

    chunks = [
        _normalize_chunk(item, section_ids)
        for item in _as_object_list(document, "chunks")
    ]
    _unique_ids([item["chunk_id"] for item in chunks], kind="chunk")

    return {
        "authors": authors,
        "works": works,
        "editions": editions,
        "sections": sections,
        "chunks": chunks,
    }


def hash_theology_document(document: dict[str, Any]) -> str:
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_theology_database(
    database_path: str | Path | None = None,
) -> TheologyStoreValidation:
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if not db_path.is_file():
        raise FileNotFoundError(f"Theology SQLite store missing: {db_path}")
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        if not REQUIRED_TABLES.issubset(tables):
            missing = ", ".join(sorted(REQUIRED_TABLES - tables))
            raise TheologyImportError(f"Theology store schema incompatible: {missing}")
        meta = _read_metadata(connection)
        return TheologyStoreValidation(
            schema_version=str(meta.get("schema_version") or ""),
            content_hash=str(meta.get("content_hash") or ""),
            import_mode=str(meta.get("import_mode") or ""),
            generated_at=str(meta.get("generated_at") or ""),
            author_count=_count(connection, "authors"),
            work_count=_count(connection, "works"),
            edition_count=_count(connection, "editions"),
            section_count=_count(connection, "sections"),
            chunk_count=_count(connection, "chunks"),
            passage_link_count=_count(connection, "passage_links"),
        )
    finally:
        connection.close()


def _write_document(
    document: dict[str, Any],
    *,
    database_path: str | Path | None,
    import_mode: str,
    atomic: bool,
) -> TheologyImportReport:
    database = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    database.parent.mkdir(parents=True, exist_ok=True)
    content_hash = hash_theology_document(document)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    passage_link_count = sum(len(chunk["passage_links"]) for chunk in document["chunks"])

    target = _temporary_database_path(database) if atomic else database
    if target.exists():
        target.unlink()

    connection = sqlite3.connect(target)
    try:
        create_schema(connection)
        _insert_document(connection, document)
        _rebuild_fts(connection)
        _write_metadata(
            connection,
            content_hash=content_hash,
            import_mode=import_mode,
            generated_at=generated_at,
            author_count=len(document["authors"]),
            work_count=len(document["works"]),
            edition_count=len(document["editions"]),
            section_count=len(document["sections"]),
            chunk_count=len(document["chunks"]),
            passage_link_count=passage_link_count,
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise TheologyImportError(f"Invalid theology SQLite integrity_check: {integrity}")
        connection.commit()
    except Exception:
        connection.close()
        if atomic and target.exists() and target != database:
            target.unlink(missing_ok=True)
        raise
    else:
        connection.close()

    if atomic:
        _replace_atomically(target, database)

    return TheologyImportReport(
        database_path=database,
        schema_version=SCHEMA_VERSION,
        import_mode=import_mode,
        content_hash=content_hash,
        generated_at=generated_at,
        author_count=len(document["authors"]),
        work_count=len(document["works"]),
        edition_count=len(document["editions"]),
        section_count=len(document["sections"]),
        chunk_count=len(document["chunks"]),
        passage_link_count=passage_link_count,
    )


def _insert_document(connection: sqlite3.Connection, document: dict[str, Any]) -> None:
    for author in document["authors"]:
        connection.execute(
            """
            INSERT INTO authors (
                author_id, canonical_name, tradition, birth_year, death_year
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                author["author_id"],
                author["canonical_name"],
                author["tradition"],
                author["birth_year"],
                author["death_year"],
            ),
        )
    for work in document["works"]:
        connection.execute(
            """
            INSERT INTO works (
                work_id, author_id, title, original_title, tradition, original_language
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                work["work_id"],
                work["author_id"],
                work["title"],
                work["original_title"],
                work["tradition"],
                work["original_language"],
            ),
        )
    for edition in document["editions"]:
        connection.execute(
            """
            INSERT INTO editions (
                edition_id, work_id, edition_label, translator, publication_year,
                publisher, language, license, rights_status, rights_note,
                source_url, corpus, external_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edition["edition_id"],
                edition["work_id"],
                edition["edition_label"],
                edition["translator"],
                edition["publication_year"],
                edition["publisher"],
                edition["language"],
                edition["license"],
                edition["rights_status"],
                edition["rights_note"],
                edition["source_url"],
                edition["corpus"],
                edition["external_id"],
            ),
        )
    for section in document["sections"]:
        connection.execute(
            """
            INSERT INTO sections (
                section_id, edition_id, parent_section_id, section_type, heading, sequence
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                section["section_id"],
                section["edition_id"],
                section["parent_section_id"],
                section["section_type"],
                section["heading"],
                section["sequence"],
            ),
        )
    for chunk in document["chunks"]:
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, section_id, sequence, text, plain_text, char_count, source_locator
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk["chunk_id"],
                chunk["section_id"],
                chunk["sequence"],
                chunk["text"],
                chunk["plain_text"],
                chunk["char_count"],
                chunk["source_locator"],
            ),
        )
        for link in chunk["passage_links"]:
            connection.execute(
                """
                INSERT INTO passage_links (
                    chunk_id, book_id, start_chapter, start_verse,
                    end_chapter, end_verse, canonical_passage, raw_citation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk["chunk_id"],
                    link["book_id"],
                    link["start_chapter"],
                    link["start_verse"],
                    link["end_chapter"],
                    link["end_verse"],
                    link["canonical_passage"],
                    link["raw_citation"],
                ),
            )


def _rebuild_fts(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM chunks_fts")
    connection.execute(
        """
        INSERT INTO chunks_fts(chunk_id, heading, plain_text)
        SELECT c.chunk_id, COALESCE(s.heading, ''), c.plain_text
        FROM chunks c
        LEFT JOIN sections s ON s.section_id = c.section_id
        ORDER BY s.sequence, c.sequence, c.chunk_id
        """
    )


def _write_metadata(
    connection: sqlite3.Connection,
    *,
    content_hash: str,
    import_mode: str,
    generated_at: str,
    author_count: int,
    work_count: int,
    edition_count: int,
    section_count: int,
    chunk_count: int,
    passage_link_count: int,
) -> None:
    rows = {
        "schema_version": SCHEMA_VERSION,
        "content_hash": content_hash,
        "import_mode": import_mode,
        "generated_at": generated_at,
        "author_count": str(author_count),
        "work_count": str(work_count),
        "edition_count": str(edition_count),
        "section_count": str(section_count),
        "chunk_count": str(chunk_count),
        "passage_link_count": str(passage_link_count),
    }
    connection.execute("DELETE FROM store_metadata")
    connection.executemany(
        "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
        sorted(rows.items()),
    )


def _read_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM store_metadata").fetchall()
    return {str(key): str(value) for key, value in rows}


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def _empty_document() -> dict[str, Any]:
    return {
        "authors": [],
        "works": [],
        "editions": [],
        "sections": [],
        "chunks": [],
    }


def _as_object_list(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise TheologyImportError(f"Fixture field {key!r} must be an array.")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TheologyImportError(f"Fixture field {key}[{index}] must be an object.")
        items.append(item)
    return items


def _unique_ids(ids: list[str], *, kind: str) -> set[str]:
    seen: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            raise TheologyImportError(f"Duplicate {kind} id: {item_id!r}")
        seen.add(item_id)
    return seen


def _normalize_author(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "author_id": _require_text(item.get("author_id"), "author_id"),
        "canonical_name": _require_text(item.get("canonical_name"), "canonical_name"),
        "tradition": _optional_text(item.get("tradition")),
        "birth_year": _optional_int(item.get("birth_year"), "birth_year"),
        "death_year": _optional_int(item.get("death_year"), "death_year"),
    }


def _normalize_work(item: dict[str, Any], author_ids: set[str]) -> dict[str, Any]:
    author_id = _require_text(item.get("author_id"), "author_id")
    if author_id not in author_ids:
        raise TheologyImportError(f"Work references unknown author_id: {author_id!r}")
    return {
        "work_id": _require_text(item.get("work_id"), "work_id"),
        "author_id": author_id,
        "title": _require_text(item.get("title"), "title"),
        "original_title": _optional_text(item.get("original_title")),
        "tradition": _require_text(item.get("tradition"), "tradition"),
        "original_language": _optional_text(item.get("original_language")),
    }


def _normalize_edition(item: dict[str, Any], work_ids: set[str]) -> dict[str, Any]:
    work_id = _require_text(item.get("work_id"), "work_id")
    if work_id not in work_ids:
        raise TheologyImportError(f"Edition references unknown work_id: {work_id!r}")
    missing = [
        field
        for field in REQUIRED_EDITION_FIELDS
        if not _optional_text(item.get(field))
    ]
    if missing:
        edition_id = _optional_text(item.get("edition_id")) or "<unknown>"
        raise TheologyImportError(
            f"Edition {edition_id!r} missing required field(s): {', '.join(missing)}"
        )
    return {
        "edition_id": _require_text(item.get("edition_id"), "edition_id"),
        "work_id": work_id,
        "edition_label": _optional_text(item.get("edition_label")),
        "translator": _optional_text(item.get("translator")),
        "publication_year": _optional_int(item.get("publication_year"), "publication_year"),
        "publisher": _optional_text(item.get("publisher")),
        "language": _require_text(item.get("language"), "language"),
        "license": _require_text(item.get("license"), "license"),
        "rights_status": _require_text(item.get("rights_status"), "rights_status"),
        "rights_note": _optional_text(item.get("rights_note")),
        "source_url": _require_text(item.get("source_url"), "source_url"),
        "corpus": _require_text(item.get("corpus"), "corpus"),
        "external_id": _require_text(item.get("external_id"), "external_id"),
    }


def _normalize_section(
    item: dict[str, Any],
    edition_ids: set[str],
    section_ids: set[str],
) -> dict[str, Any]:
    edition_id = _require_text(item.get("edition_id"), "edition_id")
    if edition_id not in edition_ids:
        raise TheologyImportError(f"Section references unknown edition_id: {edition_id!r}")
    parent_section_id = _optional_text(item.get("parent_section_id"))
    if parent_section_id is not None and parent_section_id not in section_ids:
        raise TheologyImportError(
            f"Section references unknown parent_section_id: {parent_section_id!r}"
        )
    return {
        "section_id": _require_text(item.get("section_id"), "section_id"),
        "edition_id": edition_id,
        "parent_section_id": parent_section_id,
        "section_type": _optional_text(item.get("section_type")),
        "heading": _optional_text(item.get("heading")),
        "sequence": _require_int(item.get("sequence"), "sequence"),
    }


def _order_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = list(sections)
    ordered: list[dict[str, Any]] = []
    placed: set[str] = set()
    while remaining:
        progress = False
        next_remaining: list[dict[str, Any]] = []
        for section in remaining:
            parent = section["parent_section_id"]
            if parent is None or parent in placed:
                ordered.append(section)
                placed.add(section["section_id"])
                progress = True
            else:
                next_remaining.append(section)
        if not progress:
            raise TheologyImportError("Section parent cycle or unresolved parent_section_id.")
        remaining = next_remaining
    return ordered


def _normalize_chunk(item: dict[str, Any], section_ids: set[str]) -> dict[str, Any]:
    section_id = _require_text(item.get("section_id"), "section_id")
    if section_id not in section_ids:
        raise TheologyImportError(f"Chunk references unknown section_id: {section_id!r}")
    text = _require_text(item.get("text"), "text")
    plain_text = _optional_text(item.get("plain_text")) or text
    links_raw = item.get("passage_links") or []
    if not isinstance(links_raw, list):
        raise TheologyImportError("Chunk passage_links must be an array.")
    return {
        "chunk_id": _require_text(item.get("chunk_id"), "chunk_id"),
        "section_id": section_id,
        "sequence": _require_int(item.get("sequence"), "sequence"),
        "text": text,
        "plain_text": plain_text,
        "char_count": len(plain_text),
        "source_locator": _require_text(item.get("source_locator"), "source_locator"),
        "passage_links": [_normalize_passage_link(link) for link in links_raw],
    }


def _normalize_passage_link(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise TheologyImportError("Passage link must be an object.")
    raw_citation = _optional_text(item.get("raw_citation"))
    canonical_text = _optional_text(item.get("canonical_passage")) or raw_citation
    if not canonical_text:
        raise TheologyImportError("Passage link missing canonical_passage/raw_citation.")
    try:
        reference = CanonicalReference.parse(canonical_text)
    except CanonicalReferenceError as exc:
        raise TheologyImportError(
            f"Unparseable passage citation: {canonical_text!r}"
        ) from exc
    return {
        "book_id": reference.book_id,
        "start_chapter": reference.start_chapter,
        "start_verse": reference.start_verse,
        "end_chapter": reference.end_chapter,
        "end_verse": reference.end_verse,
        "canonical_passage": reference.canonical_string(),
        "raw_citation": raw_citation or reference.canonical_string(),
    }


def _require_text(value: Any, field: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise TheologyImportError(f"Missing required field: {field}")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_int(value: Any, field: str) -> int:
    number = _optional_int(value, field)
    if number is None:
        raise TheologyImportError(f"Missing required field: {field}")
    return number


def _optional_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TheologyImportError(f"Invalid integer for {field}: {value!r}") from exc


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
            time.sleep(0.05 * (attempt + 1))
