"""Commentary DB v2 SQLite schema, fixture import, and validation.

Isolated store, source-independent. Not wired into the theology store, the
KB manifest, retrieval, evidence, or context builder. No network.

Architectural invariant enforced here: the *section* is the canonical
content unit and the sole owner of Bible passage links
(``section_passage_links``). Chunks are retrieval-only fragments derived
from a section's text and MUST NOT carry their own passage links — an
input chunk that declares ``passage_links`` is rejected at import time.

Schema v2 (no migration path from v1 — there is no production Commentary
DB yet, so a schema change just means "rebuild from source"):
  - ``section_passage_links.relation_type`` is now a required, explicit
    column (``primary`` or ``parallel``, extensible — see
    ``ALLOWED_PASSAGE_LINK_RELATIONS``) instead of being inferred by
    callers from row insertion order.
  - ``contributor_source_names`` is a new table recording, per edition,
    the raw contributor name string as that specific upstream source
    actually wrote it — separate from ``contributors.canonical_name``,
    which importers may normalize across editions (e.g. the same
    translator named "Bingham, Charles William" in one edition and
    "Charles William Bingham" in another) without losing the original
    per-edition wording.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.paths import PROJECT_ROOT

SCHEMA_VERSION = "2"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "generated" / "commentary.sqlite3"
DEFAULT_FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "kb" / "commentary_v1_sample.json"
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

ALLOWED_CONTRIBUTOR_ROLES = frozenset(
    {"author", "translator", "editor", "annotator", "compiler"}
)

# Deliberately small and closed for now (the two relations the corpus
# actually needs); add to this set — not a separate mechanism — if a real
# source ever needs a third relation (e.g. "commentary_on_related_passage").
ALLOWED_PASSAGE_LINK_RELATIONS = frozenset({"primary", "parallel"})

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_TABLES = frozenset(
    {
        "store_metadata",
        "contributors",
        "works",
        "work_contributors",
        "editions",
        "source_files",
        "import_batches",
        "sections",
        "section_passage_links",
        "chunks",
        "contributor_source_names",
        "sections_fts",
        "chunks_fts",
    }
)


class CommentaryImportError(ValueError):
    """Raised when a commentary fixture/document cannot be imported."""


@dataclass
class CommentaryImportReport:
    database_path: Path
    schema_version: str
    import_mode: str
    content_hash: str
    generated_at: str
    contributor_count: int
    work_count: int
    work_contributor_count: int
    edition_count: int
    source_file_count: int
    import_batch_count: int
    section_count: int
    passage_link_count: int
    chunk_count: int
    contributor_source_name_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        return payload


@dataclass
class CommentaryStoreValidation:
    schema_version: str
    content_hash: str
    import_mode: str
    generated_at: str
    contributor_count: int
    work_count: int
    work_contributor_count: int
    edition_count: int
    source_file_count: int
    import_batch_count: int
    section_count: int
    passage_link_count: int
    chunk_count: int
    contributor_source_name_count: int = 0

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

        CREATE TABLE IF NOT EXISTS contributors (
            contributor_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            birth_year INTEGER,
            death_year INTEGER
        );

        CREATE TABLE IF NOT EXISTS works (
            work_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            original_title TEXT,
            original_language TEXT,
            work_type TEXT
        );

        CREATE TABLE IF NOT EXISTS work_contributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT NOT NULL,
            contributor_id TEXT NOT NULL,
            role TEXT NOT NULL,
            FOREIGN KEY(work_id) REFERENCES works(work_id),
            FOREIGN KEY(contributor_id) REFERENCES contributors(contributor_id)
        );

        CREATE TABLE IF NOT EXISTS editions (
            edition_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            edition_label TEXT,
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

        CREATE TABLE IF NOT EXISTS source_files (
            source_file_id TEXT PRIMARY KEY,
            edition_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            raw_sha256 TEXT NOT NULL,
            byte_size INTEGER,
            retrieved_at TEXT,
            FOREIGN KEY(edition_id) REFERENCES editions(edition_id)
        );

        CREATE TABLE IF NOT EXISTS import_batches (
            batch_id TEXT PRIMARY KEY,
            source_file_id TEXT NOT NULL,
            importer_name TEXT NOT NULL,
            importer_version TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            import_mode TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            report TEXT,
            FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id)
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

        CREATE TABLE IF NOT EXISTS section_passage_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            book_id TEXT NOT NULL,
            start_chapter INTEGER NOT NULL,
            start_verse INTEGER NOT NULL,
            end_chapter INTEGER NOT NULL,
            end_verse INTEGER NOT NULL,
            canonical_passage TEXT NOT NULL,
            raw_citation TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES sections(section_id)
        );

        CREATE TABLE IF NOT EXISTS contributor_source_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contributor_id TEXT NOT NULL,
            edition_id TEXT NOT NULL,
            raw_name TEXT NOT NULL,
            FOREIGN KEY(contributor_id) REFERENCES contributors(contributor_id),
            FOREIGN KEY(edition_id) REFERENCES editions(edition_id)
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

        CREATE UNIQUE INDEX IF NOT EXISTS uq_work_contributors_role
            ON work_contributors(work_id, contributor_id, role);
        CREATE INDEX IF NOT EXISTS idx_work_contributors_work
            ON work_contributors(work_id);
        CREATE INDEX IF NOT EXISTS idx_work_contributors_contributor
            ON work_contributors(contributor_id);
        CREATE INDEX IF NOT EXISTS idx_editions_work
            ON editions(work_id);
        CREATE INDEX IF NOT EXISTS idx_source_files_edition
            ON source_files(edition_id);
        CREATE INDEX IF NOT EXISTS idx_import_batches_source_file
            ON import_batches(source_file_id);
        CREATE INDEX IF NOT EXISTS idx_sections_edition
            ON sections(edition_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_sections_parent
            ON sections(parent_section_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_section
            ON chunks(section_id, sequence);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_section_passage_links_canonical
            ON section_passage_links(section_id, canonical_passage);
        CREATE INDEX IF NOT EXISTS idx_section_passage_links_section
            ON section_passage_links(section_id);
        CREATE INDEX IF NOT EXISTS idx_section_passage_links_canonical
            ON section_passage_links(canonical_passage);
        CREATE INDEX IF NOT EXISTS idx_section_passage_links_book
            ON section_passage_links(book_id, start_chapter, start_verse);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_contributor_source_names
            ON contributor_source_names(contributor_id, edition_id);
        CREATE INDEX IF NOT EXISTS idx_contributor_source_names_edition
            ON contributor_source_names(edition_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
            section_id UNINDEXED,
            heading,
            plain_text,
            tokenize='unicode61'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            heading,
            plain_text,
            tokenize='unicode61'
        );
        """
    )


def create_empty_commentary_database(
    database_path: str | Path | None = None,
    *,
    atomic: bool = True,
) -> CommentaryImportReport:
    return _write_document(
        _empty_document(),
        database_path=database_path,
        import_mode=IMPORT_MODE_EMPTY,
        atomic=atomic,
    )


def import_commentary_sqlite(
    *,
    fixture_path: str | Path | None = None,
    document: dict[str, Any] | None = None,
    database_path: str | Path | None = None,
    import_mode: str = IMPORT_MODE_FIXTURE,
    atomic: bool = True,
) -> CommentaryImportReport:
    if document is None and fixture_path is None:
        raise CommentaryImportError("Provide fixture_path or document.")
    if document is None:
        document = load_fixture_document(fixture_path)
    normalized = normalize_commentary_document(document)
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
        raise CommentaryImportError(f"Cannot read commentary fixture: {fixture}") from exc
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CommentaryImportError(f"Invalid commentary fixture JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CommentaryImportError("Commentary fixture root must be a JSON object.")
    return payload


def normalize_commentary_document(document: dict[str, Any]) -> dict[str, Any]:
    contributors = [
        _normalize_contributor(item) for item in _as_object_list(document, "contributors")
    ]
    contributor_ids = _unique_ids(
        [item["contributor_id"] for item in contributors], kind="contributor"
    )

    works = [_normalize_work(item) for item in _as_object_list(document, "works")]
    work_ids = _unique_ids([item["work_id"] for item in works], kind="work")

    work_contributors = [
        _normalize_work_contributor(item, work_ids, contributor_ids)
        for item in _as_object_list(document, "work_contributors")
    ]
    _reject_duplicate_work_contributors(work_contributors)

    editions = [
        _normalize_edition(item, work_ids)
        for item in _as_object_list(document, "editions")
    ]
    edition_ids = _unique_ids([item["edition_id"] for item in editions], kind="edition")

    contributor_source_names = [
        _normalize_contributor_source_name(item, contributor_ids, edition_ids)
        for item in _as_object_list(document, "contributor_source_names")
    ]
    _reject_duplicate_contributor_source_names(contributor_source_names)

    source_files = [
        _normalize_source_file(item, edition_ids)
        for item in _as_object_list(document, "source_files")
    ]
    source_file_ids = _unique_ids(
        [item["source_file_id"] for item in source_files], kind="source_file"
    )

    import_batches = [
        _normalize_import_batch(item, source_file_ids)
        for item in _as_object_list(document, "import_batches")
    ]
    _unique_ids([item["batch_id"] for item in import_batches], kind="import_batch")

    sections_raw = _as_object_list(document, "sections")
    section_ids_preview = _unique_ids(
        [_require_text(item.get("section_id"), "section_id") for item in sections_raw],
        kind="section",
    )
    section_edition_preview = {
        _require_text(item.get("section_id"), "section_id"): _require_text(
            item.get("edition_id"), "edition_id"
        )
        for item in sections_raw
    }
    sections = [
        _normalize_section(item, edition_ids, section_ids_preview, section_edition_preview)
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
        "contributors": contributors,
        "works": works,
        "work_contributors": work_contributors,
        "editions": editions,
        "contributor_source_names": contributor_source_names,
        "source_files": source_files,
        "import_batches": import_batches,
        "sections": sections,
        "chunks": chunks,
    }


def hash_commentary_document(document: dict[str, Any]) -> str:
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_commentary_database(
    database_path: str | Path | None = None,
) -> CommentaryStoreValidation:
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if not db_path.is_file():
        raise FileNotFoundError(f"Commentary SQLite store missing: {db_path}")
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
            raise CommentaryImportError(f"Commentary store schema incompatible: {missing}")
        meta = _read_metadata(connection)
        return CommentaryStoreValidation(
            schema_version=str(meta.get("schema_version") or ""),
            content_hash=str(meta.get("content_hash") or ""),
            import_mode=str(meta.get("import_mode") or ""),
            generated_at=str(meta.get("generated_at") or ""),
            contributor_count=_count(connection, "contributors"),
            work_count=_count(connection, "works"),
            work_contributor_count=_count(connection, "work_contributors"),
            edition_count=_count(connection, "editions"),
            source_file_count=_count(connection, "source_files"),
            import_batch_count=_count(connection, "import_batches"),
            section_count=_count(connection, "sections"),
            passage_link_count=_count(connection, "section_passage_links"),
            chunk_count=_count(connection, "chunks"),
            contributor_source_name_count=_count(connection, "contributor_source_names"),
        )
    finally:
        connection.close()


def _write_document(
    document: dict[str, Any],
    *,
    database_path: str | Path | None,
    import_mode: str,
    atomic: bool,
) -> CommentaryImportReport:
    database = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    database.parent.mkdir(parents=True, exist_ok=True)
    content_hash = hash_commentary_document(document)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    passage_link_count = sum(len(section["passage_links"]) for section in document["sections"])

    target = _temporary_database_path(database) if atomic else database
    if target.exists():
        target.unlink()

    connection = sqlite3.connect(target)
    try:
        create_schema(connection)
        _insert_document(connection, document, content_hash=content_hash, import_mode=import_mode)
        _rebuild_fts(connection)
        _write_metadata(
            connection,
            content_hash=content_hash,
            import_mode=import_mode,
            generated_at=generated_at,
            contributor_count=len(document["contributors"]),
            work_count=len(document["works"]),
            work_contributor_count=len(document["work_contributors"]),
            edition_count=len(document["editions"]),
            source_file_count=len(document["source_files"]),
            import_batch_count=len(document["import_batches"]),
            section_count=len(document["sections"]),
            passage_link_count=passage_link_count,
            chunk_count=len(document["chunks"]),
            contributor_source_name_count=len(document["contributor_source_names"]),
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise CommentaryImportError(f"Invalid commentary SQLite integrity_check: {integrity}")
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

    return CommentaryImportReport(
        database_path=database,
        schema_version=SCHEMA_VERSION,
        import_mode=import_mode,
        content_hash=content_hash,
        generated_at=generated_at,
        contributor_count=len(document["contributors"]),
        work_count=len(document["works"]),
        work_contributor_count=len(document["work_contributors"]),
        edition_count=len(document["editions"]),
        source_file_count=len(document["source_files"]),
        import_batch_count=len(document["import_batches"]),
        section_count=len(document["sections"]),
        passage_link_count=passage_link_count,
        chunk_count=len(document["chunks"]),
        contributor_source_name_count=len(document["contributor_source_names"]),
    )


def _insert_document(
    connection: sqlite3.Connection,
    document: dict[str, Any],
    *,
    content_hash: str,
    import_mode: str,
) -> None:
    for contributor in document["contributors"]:
        connection.execute(
            """
            INSERT INTO contributors (
                contributor_id, canonical_name, birth_year, death_year
            ) VALUES (?, ?, ?, ?)
            """,
            (
                contributor["contributor_id"],
                contributor["canonical_name"],
                contributor["birth_year"],
                contributor["death_year"],
            ),
        )
    for work in document["works"]:
        connection.execute(
            """
            INSERT INTO works (
                work_id, title, original_title, original_language, work_type
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                work["work_id"],
                work["title"],
                work["original_title"],
                work["original_language"],
                work["work_type"],
            ),
        )
    for wc in document["work_contributors"]:
        connection.execute(
            """
            INSERT INTO work_contributors (
                work_id, contributor_id, role
            ) VALUES (?, ?, ?)
            """,
            (wc["work_id"], wc["contributor_id"], wc["role"]),
        )
    for edition in document["editions"]:
        connection.execute(
            """
            INSERT INTO editions (
                edition_id, work_id, edition_label, publication_year,
                publisher, language, license, rights_status, rights_note,
                source_url, corpus, external_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edition["edition_id"],
                edition["work_id"],
                edition["edition_label"],
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
    for entry in document["contributor_source_names"]:
        connection.execute(
            """
            INSERT INTO contributor_source_names (
                contributor_id, edition_id, raw_name
            ) VALUES (?, ?, ?)
            """,
            (entry["contributor_id"], entry["edition_id"], entry["raw_name"]),
        )
    for source_file in document["source_files"]:
        connection.execute(
            """
            INSERT INTO source_files (
                source_file_id, edition_id, file_name, raw_sha256, byte_size, retrieved_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_file["source_file_id"],
                source_file["edition_id"],
                source_file["file_name"],
                source_file["raw_sha256"],
                source_file["byte_size"],
                source_file["retrieved_at"],
            ),
        )
    for batch in document["import_batches"]:
        connection.execute(
            """
            INSERT INTO import_batches (
                batch_id, source_file_id, importer_name, importer_version,
                imported_at, import_mode, content_hash, report
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch["batch_id"],
                batch["source_file_id"],
                batch["importer_name"],
                batch["importer_version"],
                batch["imported_at"],
                batch["import_mode"] or import_mode,
                content_hash,
                json.dumps(batch["report"], ensure_ascii=False, sort_keys=True)
                if batch["report"] is not None
                else None,
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
        for link in section["passage_links"]:
            connection.execute(
                """
                INSERT INTO section_passage_links (
                    section_id, book_id, start_chapter, start_verse,
                    end_chapter, end_verse, canonical_passage, raw_citation,
                    relation_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    section["section_id"],
                    link["book_id"],
                    link["start_chapter"],
                    link["start_verse"],
                    link["end_chapter"],
                    link["end_verse"],
                    link["canonical_passage"],
                    link["raw_citation"],
                    link["relation_type"],
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

    connection.execute("DELETE FROM sections_fts")
    section_rows = connection.execute(
        "SELECT section_id, heading, sequence FROM sections ORDER BY sequence, section_id"
    ).fetchall()
    chunk_rows = connection.execute(
        "SELECT section_id, plain_text FROM chunks ORDER BY section_id, sequence"
    ).fetchall()
    plain_text_by_section: dict[str, list[str]] = {}
    for section_id, plain_text in chunk_rows:
        plain_text_by_section.setdefault(str(section_id), []).append(str(plain_text or ""))
    for section_id, heading, _sequence in section_rows:
        aggregated = " ".join(plain_text_by_section.get(str(section_id), []))
        connection.execute(
            "INSERT INTO sections_fts(section_id, heading, plain_text) VALUES (?, ?, ?)",
            (str(section_id), str(heading or ""), aggregated),
        )


def _write_metadata(
    connection: sqlite3.Connection,
    *,
    content_hash: str,
    import_mode: str,
    generated_at: str,
    contributor_count: int,
    work_count: int,
    work_contributor_count: int,
    edition_count: int,
    source_file_count: int,
    import_batch_count: int,
    section_count: int,
    passage_link_count: int,
    chunk_count: int,
    contributor_source_name_count: int,
) -> None:
    rows = {
        "schema_version": SCHEMA_VERSION,
        "content_hash": content_hash,
        "import_mode": import_mode,
        "generated_at": generated_at,
        "contributor_count": str(contributor_count),
        "work_count": str(work_count),
        "work_contributor_count": str(work_contributor_count),
        "edition_count": str(edition_count),
        "source_file_count": str(source_file_count),
        "import_batch_count": str(import_batch_count),
        "section_count": str(section_count),
        "passage_link_count": str(passage_link_count),
        "chunk_count": str(chunk_count),
        "contributor_source_name_count": str(contributor_source_name_count),
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
        "contributors": [],
        "works": [],
        "work_contributors": [],
        "editions": [],
        "contributor_source_names": [],
        "source_files": [],
        "import_batches": [],
        "sections": [],
        "chunks": [],
    }


def _as_object_list(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise CommentaryImportError(f"Fixture field {key!r} must be an array.")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise CommentaryImportError(f"Fixture field {key}[{index}] must be an object.")
        items.append(item)
    return items


def _unique_ids(ids: list[str], *, kind: str) -> set[str]:
    seen: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            raise CommentaryImportError(f"Duplicate {kind} id: {item_id!r}")
        seen.add(item_id)
    return seen


def _normalize_contributor(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "contributor_id": _require_text(item.get("contributor_id"), "contributor_id"),
        "canonical_name": _require_text(item.get("canonical_name"), "canonical_name"),
        "birth_year": _optional_int(item.get("birth_year"), "birth_year"),
        "death_year": _optional_int(item.get("death_year"), "death_year"),
    }


def _normalize_work(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "work_id": _require_text(item.get("work_id"), "work_id"),
        "title": _require_text(item.get("title"), "title"),
        "original_title": _optional_text(item.get("original_title")),
        "original_language": _optional_text(item.get("original_language")),
        "work_type": _optional_text(item.get("work_type")),
    }


def _normalize_work_contributor(
    item: dict[str, Any],
    work_ids: set[str],
    contributor_ids: set[str],
) -> dict[str, Any]:
    work_id = _require_text(item.get("work_id"), "work_id")
    if work_id not in work_ids:
        raise CommentaryImportError(f"work_contributors references unknown work_id: {work_id!r}")
    contributor_id = _require_text(item.get("contributor_id"), "contributor_id")
    if contributor_id not in contributor_ids:
        raise CommentaryImportError(
            f"work_contributors references unknown contributor_id: {contributor_id!r}"
        )
    role = _require_text(item.get("role"), "role").strip().lower()
    if role not in ALLOWED_CONTRIBUTOR_ROLES:
        raise CommentaryImportError(
            f"Unsupported work_contributors role: {role!r}. "
            f"Allowed: {sorted(ALLOWED_CONTRIBUTOR_ROLES)}"
        )
    return {"work_id": work_id, "contributor_id": contributor_id, "role": role}


def _reject_duplicate_work_contributors(work_contributors: list[dict[str, Any]]) -> None:
    seen: set[tuple[str, str, str]] = set()
    for item in work_contributors:
        key = (item["work_id"], item["contributor_id"], item["role"])
        if key in seen:
            raise CommentaryImportError(
                "Duplicate work_contributors entry: "
                f"work_id={item['work_id']!r}, contributor_id={item['contributor_id']!r}, "
                f"role={item['role']!r}"
            )
        seen.add(key)


def _normalize_contributor_source_name(
    item: dict[str, Any],
    contributor_ids: set[str],
    edition_ids: set[str],
) -> dict[str, Any]:
    contributor_id = _require_text(item.get("contributor_id"), "contributor_id")
    if contributor_id not in contributor_ids:
        raise CommentaryImportError(
            f"contributor_source_names references unknown contributor_id: {contributor_id!r}"
        )
    edition_id = _require_text(item.get("edition_id"), "edition_id")
    if edition_id not in edition_ids:
        raise CommentaryImportError(
            f"contributor_source_names references unknown edition_id: {edition_id!r}"
        )
    return {
        "contributor_id": contributor_id,
        "edition_id": edition_id,
        "raw_name": _require_text(item.get("raw_name"), "raw_name"),
    }


def _reject_duplicate_contributor_source_names(
    entries: list[dict[str, Any]]
) -> None:
    seen: set[tuple[str, str]] = set()
    for item in entries:
        key = (item["contributor_id"], item["edition_id"])
        if key in seen:
            raise CommentaryImportError(
                "Duplicate contributor_source_names entry: "
                f"contributor_id={item['contributor_id']!r}, edition_id={item['edition_id']!r}"
            )
        seen.add(key)


def _normalize_edition(item: dict[str, Any], work_ids: set[str]) -> dict[str, Any]:
    work_id = _require_text(item.get("work_id"), "work_id")
    if work_id not in work_ids:
        raise CommentaryImportError(f"Edition references unknown work_id: {work_id!r}")
    missing = [
        field
        for field in REQUIRED_EDITION_FIELDS
        if not _optional_text(item.get(field))
    ]
    if missing:
        edition_id = _optional_text(item.get("edition_id")) or "<unknown>"
        raise CommentaryImportError(
            f"Edition {edition_id!r} missing required field(s): {', '.join(missing)}"
        )
    return {
        "edition_id": _require_text(item.get("edition_id"), "edition_id"),
        "work_id": work_id,
        "edition_label": _optional_text(item.get("edition_label")),
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


def _normalize_source_file(item: dict[str, Any], edition_ids: set[str]) -> dict[str, Any]:
    edition_id = _require_text(item.get("edition_id"), "edition_id")
    if edition_id not in edition_ids:
        raise CommentaryImportError(f"source_files references unknown edition_id: {edition_id!r}")
    raw_sha256 = _require_text(item.get("raw_sha256"), "raw_sha256").strip().lower()
    if not _SHA256_HEX_RE.match(raw_sha256):
        raise CommentaryImportError(
            f"source_files.raw_sha256 must be 64 lowercase hex chars: {raw_sha256!r}"
        )
    return {
        "source_file_id": _require_text(item.get("source_file_id"), "source_file_id"),
        "edition_id": edition_id,
        "file_name": _require_text(item.get("file_name"), "file_name"),
        "raw_sha256": raw_sha256,
        "byte_size": _optional_int(item.get("byte_size"), "byte_size"),
        "retrieved_at": _optional_text(item.get("retrieved_at")),
    }


def _normalize_import_batch(item: dict[str, Any], source_file_ids: set[str]) -> dict[str, Any]:
    source_file_id = _require_text(item.get("source_file_id"), "source_file_id")
    if source_file_id not in source_file_ids:
        raise CommentaryImportError(
            f"import_batches references unknown source_file_id: {source_file_id!r}"
        )
    report = item.get("report")
    if report is not None and not isinstance(report, dict):
        raise CommentaryImportError("import_batches.report must be an object or null.")
    return {
        "batch_id": _require_text(item.get("batch_id"), "batch_id"),
        "source_file_id": source_file_id,
        "importer_name": _require_text(item.get("importer_name"), "importer_name"),
        "importer_version": _require_text(item.get("importer_version"), "importer_version"),
        "imported_at": _require_text(item.get("imported_at"), "imported_at"),
        "import_mode": _optional_text(item.get("import_mode")),
        "report": report,
    }


def _normalize_section(
    item: dict[str, Any],
    edition_ids: set[str],
    section_ids: set[str],
    section_edition_preview: dict[str, str],
) -> dict[str, Any]:
    section_id = _require_text(item.get("section_id"), "section_id")
    edition_id = _require_text(item.get("edition_id"), "edition_id")
    if edition_id not in edition_ids:
        raise CommentaryImportError(f"Section references unknown edition_id: {edition_id!r}")
    parent_section_id = _optional_text(item.get("parent_section_id"))
    if parent_section_id is not None:
        if parent_section_id not in section_ids:
            raise CommentaryImportError(
                f"Section references unknown parent_section_id: {parent_section_id!r}"
            )
        parent_edition_id = section_edition_preview.get(parent_section_id)
        if parent_edition_id != edition_id:
            raise CommentaryImportError(
                f"Section {section_id!r} parent_section_id {parent_section_id!r} belongs to "
                f"a different edition ({parent_edition_id!r} != {edition_id!r}); "
                "a section's parent must be in the same edition."
            )
    links_raw = item.get("passage_links") or []
    if not isinstance(links_raw, list):
        raise CommentaryImportError("Section passage_links must be an array.")
    passage_links = [_normalize_passage_link(link) for link in links_raw]
    _reject_duplicate_passage_links(passage_links, section_id=section_id)
    return {
        "section_id": section_id,
        "edition_id": edition_id,
        "parent_section_id": parent_section_id,
        "section_type": _optional_text(item.get("section_type")),
        "heading": _optional_text(item.get("heading")),
        "sequence": _require_int(item.get("sequence"), "sequence"),
        "passage_links": passage_links,
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
            raise CommentaryImportError("Section parent cycle or unresolved parent_section_id.")
        remaining = next_remaining
    return ordered


def _normalize_chunk(item: dict[str, Any], section_ids: set[str]) -> dict[str, Any]:
    if item.get("passage_links"):
        raise CommentaryImportError(
            "Chunk must not declare passage_links; passage links belong to the section "
            f"(chunk_id={item.get('chunk_id')!r})."
        )
    section_id = _require_text(item.get("section_id"), "section_id")
    if section_id not in section_ids:
        raise CommentaryImportError(f"Chunk references unknown section_id: {section_id!r}")
    text = _require_text(item.get("text"), "text")
    plain_text = _optional_text(item.get("plain_text")) or text
    return {
        "chunk_id": _require_text(item.get("chunk_id"), "chunk_id"),
        "section_id": section_id,
        "sequence": _require_int(item.get("sequence"), "sequence"),
        "text": text,
        "plain_text": plain_text,
        "char_count": len(plain_text),
        "source_locator": _require_text(item.get("source_locator"), "source_locator"),
    }


def _reject_duplicate_passage_links(
    passage_links: list[dict[str, Any]], *, section_id: str
) -> None:
    seen: set[str] = set()
    for link in passage_links:
        canonical = link["canonical_passage"]
        if canonical in seen:
            raise CommentaryImportError(
                f"Duplicate passage_link canonical_passage {canonical!r} "
                f"in section {section_id!r}."
            )
        seen.add(canonical)


def _normalize_passage_link(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise CommentaryImportError("Passage link must be an object.")
    raw_citation = _optional_text(item.get("raw_citation"))
    canonical_text = _optional_text(item.get("canonical_passage")) or raw_citation
    if not canonical_text:
        raise CommentaryImportError("Passage link missing canonical_passage/raw_citation.")
    try:
        reference = CanonicalReference.parse(canonical_text)
    except CanonicalReferenceError as exc:
        raise CommentaryImportError(
            f"Unparseable passage citation: {canonical_text!r}"
        ) from exc
    relation_type = _require_text(item.get("relation_type"), "relation_type").strip().lower()
    if relation_type not in ALLOWED_PASSAGE_LINK_RELATIONS:
        raise CommentaryImportError(
            f"Unsupported passage_link relation_type: {relation_type!r}. "
            f"Allowed: {sorted(ALLOWED_PASSAGE_LINK_RELATIONS)}"
        )
    return {
        "book_id": reference.book_id,
        "start_chapter": reference.start_chapter,
        "start_verse": reference.start_verse,
        "end_chapter": reference.end_chapter,
        "end_verse": reference.end_verse,
        "canonical_passage": reference.canonical_string(),
        "raw_citation": raw_citation or reference.canonical_string(),
        "relation_type": relation_type,
    }


def _require_text(value: Any, field: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise CommentaryImportError(f"Missing required field: {field}")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_int(value: Any, field: str) -> int:
    number = _optional_int(value, field)
    if number is None:
        raise CommentaryImportError(f"Missing required field: {field}")
    return number


def _optional_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CommentaryImportError(f"Invalid integer for {field}: {value!r}") from exc


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
