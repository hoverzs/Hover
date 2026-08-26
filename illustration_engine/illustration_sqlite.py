"""Build-time SQLite layer for the illustration/story database.

Mirrors `bible_engine/hymn_sqlite.py`: this module owns schema creation
and *writes*; a later, separate read-only repository module will own
*reads*. Nothing here is imported by `app.py` or by any existing
`bible_engine`/hymn module, and nothing here imports them except the
stable, read-only `illustration_engine.paths` constants.

FAIL-CLOSED LICENSE GATE (defense in depth, two independent layers):

1. Python layer — `insert_story(..., status="published")` looks up the
   story's source `license_status` in the SAME transaction and refuses
   (raises `IllustrationLicenseGateError`) unless it is in
   `PUBLISHABLE_LICENSE_STATUSES`. This is the layer normal callers hit.
2. SQL layer — `trg_stories_publish_requires_license_*` triggers enforce
   the identical rule directly in SQLite via `RAISE(ABORT, ...)`, on both
   INSERT and UPDATE. This protects against any future caller that writes
   raw SQL and bypasses the Python helper entirely. The trigger body is
   generated from `PUBLISHABLE_LICENSE_STATUSES` (see `_publishable_sql_list`)
   so the two layers cannot silently drift apart.

A third, read-side layer (the `published_stories` VIEW) additionally
guarantees that even a row that somehow ends up with `status='published'`
against a non-publishable source is never returned by anything reading
through the view.

CONTENT-COMPLETENESS GATE (schema v2, independent of the license gate):

`title_hu`, `modern_hu_text`, and `summary_hu` are the Hungarian layer,
authored in a later, separate AI-enrichment phase — a source-language
import (e.g. an English Jataka tale) legitimately has none of them yet.
They are therefore nullable, but a table-level CHECK constraint enforces
that a story can only become `status='published'` once all three are
filled in: `status = 'published'` requires `title_hu`, `modern_hu_text`,
and `summary_hu` to be non-NULL. Intermediate editorial workflow states
(`needs_review`, `approved`) are deliberately NOT gated on this — the DB
guarantees fail-closed *publishability*, not a fully-populated editorial
workflow at every intermediate step. This is a same-row CHECK (no
cross-table trigger needed) and applies to every writer, Python or raw
SQL alike. `title_original` (the source-language title, always known at
import time) and `original_text` remain the only required content
fields for a freshly-imported, still-`draft` story.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from illustration_engine.paths import GENERATED_DATA_DIR
from illustration_engine.source_registry import PUBLISHABLE_LICENSE_STATUSES


DATABASE_NAME = "illustrations.sqlite3"
DEFAULT_DATABASE_PATH = GENERATED_DATA_DIR / DATABASE_NAME
SCHEMA_VERSION = 2

ALLOWED_STORY_STATUSES = frozenset({"draft", "needs_review", "approved", "published"})
ALLOWED_ADAPTATION_STATUSES = frozenset(
    {"verbatim_transcription", "modernized_spelling", "editorial_paraphrase"}
)

REQUIRED_TABLES = frozenset({"sources", "stories", "tags", "story_tags", "import_meta"})
REQUIRED_VIEWS = frozenset({"published_stories"})

_publishable_sql_list = ", ".join(f"'{s}'" for s in sorted(PUBLISHABLE_LICENSE_STATUSES))
_license_status_sql_list = ", ".join(
    f"'{s}'"
    for s in sorted(
        {
            "public_domain_confirmed",
            "public_domain_assumed_by_age",
            "permission_granted",
            "unknown",
            "restricted",
        }
    )
)


class IllustrationLicenseGateError(ValueError):
    """A story nem kaphat 'published' állapotot a forrása jogállása miatt."""


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    return Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            author TEXT,
            orig_language TEXT NOT NULL,
            publication_year INTEGER,
            edition_reference TEXT,
            license_status TEXT NOT NULL CHECK (
                license_status IN ({_license_status_sql_list})
            ),
            license_basis_hu TEXT NOT NULL,
            rights_holder TEXT,
            source_url TEXT,
            retrieved_at TEXT,
            reliability_tier TEXT NOT NULL,
            notes_hu TEXT,
            registered_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES sources(id),
            external_ref TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            title_original TEXT NOT NULL,
            title_hu TEXT,
            original_text TEXT,
            original_text_checksum TEXT,
            adaptation_status TEXT NOT NULL CHECK (
                adaptation_status IN (
                    'verbatim_transcription', 'modernized_spelling', 'editorial_paraphrase'
                )
            ),
            modern_hu_text TEXT,
            summary_hu TEXT,
            moral_hu TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'needs_review', 'approved', 'published')
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, canonical_key),
            CHECK (
                status != 'published'
                OR (title_hu IS NOT NULL AND modern_hu_text IS NOT NULL AND summary_hu IS NOT NULL)
            )
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL CHECK (category IN ('topic', 'tone', 'function')),
            slug TEXT NOT NULL,
            label_hu TEXT NOT NULL,
            UNIQUE(category, slug)
        );

        CREATE TABLE IF NOT EXISTS story_tags (
            story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            PRIMARY KEY (story_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS import_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stories_source ON stories(source_id);
        CREATE INDEX IF NOT EXISTS idx_story_tags_story ON story_tags(story_id);
        CREATE INDEX IF NOT EXISTS idx_story_tags_tag ON story_tags(tag_id);

        -- Read-side fail-closed gate: only sources with a confirmed/granted
        -- license AND stories explicitly marked 'published' are exposed here.
        -- Every future public repository read must query THIS view, never
        -- the raw `stories`/`sources` tables directly.
        CREATE VIEW IF NOT EXISTS published_stories AS
        SELECT
            st.id,
            st.source_id,
            st.external_ref,
            st.canonical_key,
            st.title_original,
            st.title_hu,
            st.original_text,
            st.original_text_checksum,
            st.adaptation_status,
            st.modern_hu_text,
            st.summary_hu,
            st.moral_hu,
            st.status,
            st.created_at,
            st.updated_at,
            s.code AS source_code,
            s.license_status AS source_license_status,
            s.reliability_tier AS source_reliability_tier
        FROM stories st
        JOIN sources s ON s.id = st.source_id
        WHERE st.status = 'published'
          AND s.license_status IN ({_publishable_sql_list});

        -- SQL-layer fail-closed gate (see module docstring): mirrors the
        -- Python-layer check in insert_story() so raw-SQL writers cannot
        -- bypass it.
        CREATE TRIGGER IF NOT EXISTS trg_stories_publish_requires_license_insert
        BEFORE INSERT ON stories
        WHEN NEW.status = 'published'
        BEGIN
            SELECT RAISE(ABORT, 'license_gate: source license_status does not permit published status')
            WHERE (SELECT license_status FROM sources WHERE id = NEW.source_id)
                  NOT IN ({_publishable_sql_list});
        END;

        CREATE TRIGGER IF NOT EXISTS trg_stories_publish_requires_license_update
        BEFORE UPDATE OF status, source_id ON stories
        WHEN NEW.status = 'published'
        BEGIN
            SELECT RAISE(ABORT, 'license_gate: source license_status does not permit published status')
            WHERE (SELECT license_status FROM sources WHERE id = NEW.source_id)
                  NOT IN ({_publishable_sql_list});
        END;
        """
    )
    connection.commit()


def check_integrity(connection: sqlite3.Connection) -> str:
    return connection.execute("PRAGMA integrity_check").fetchone()[0]


def insert_source(
    connection: sqlite3.Connection,
    *,
    code: str,
    title: str,
    orig_language: str,
    license_status: str,
    license_basis_hu: str,
    reliability_tier: str,
    author: str | None = None,
    publication_year: int | None = None,
    edition_reference: str | None = None,
    rights_holder: str | None = None,
    source_url: str | None = None,
    retrieved_at: str | None = None,
    notes_hu: str | None = None,
    registered_at: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO sources(
            code, title, author, orig_language, publication_year, edition_reference,
            license_status, license_basis_hu, rights_holder, source_url, retrieved_at,
            reliability_tier, notes_hu, registered_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            code,
            title,
            author,
            orig_language,
            publication_year,
            edition_reference,
            license_status,
            license_basis_hu,
            rights_holder,
            source_url,
            retrieved_at,
            reliability_tier,
            notes_hu,
            registered_at or datetime.now(UTC).isoformat(),
        ),
    )
    return int(cursor.lastrowid)


def insert_story(
    connection: sqlite3.Connection,
    *,
    source_id: int,
    external_ref: str,
    canonical_key: str,
    title_original: str,
    adaptation_status: str,
    status: str = "draft",
    title_hu: str | None = None,
    modern_hu_text: str | None = None,
    summary_hu: str | None = None,
    original_text: str | None = None,
    original_text_checksum: str | None = None,
    moral_hu: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> int:
    if adaptation_status not in ALLOWED_ADAPTATION_STATUSES:
        raise ValueError(f"Invalid adaptation_status: {adaptation_status!r}")
    if status not in ALLOWED_STORY_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    for field_name, value in (
        ("external_ref", external_ref),
        ("canonical_key", canonical_key),
        ("title_original", title_original),
    ):
        if not (value or "").strip():
            raise ValueError(f"{field_name} must be non-empty")
    for field_name, value in (
        ("title_hu", title_hu),
        ("modern_hu_text", modern_hu_text),
        ("summary_hu", summary_hu),
    ):
        if value is not None and not value.strip():
            raise ValueError(f"{field_name} must be non-empty when provided")

    if status == "published" and (title_hu is None or modern_hu_text is None or summary_hu is None):
        missing = [
            name
            for name, value in (
                ("title_hu", title_hu),
                ("modern_hu_text", modern_hu_text),
                ("summary_hu", summary_hu),
            )
            if value is None
        ]
        raise ValueError(
            f"status={status!r} requires title_hu, modern_hu_text, and summary_hu "
            f"to be filled in (content-completeness gate) — missing: {missing}"
        )
    if status == "published":
        _assert_source_is_publishable(connection, source_id)

    now = datetime.now(UTC).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO stories(
            source_id, external_ref, canonical_key, title_original, title_hu,
            original_text, original_text_checksum, adaptation_status, modern_hu_text,
            summary_hu, moral_hu, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            external_ref,
            canonical_key,
            title_original,
            title_hu,
            original_text,
            original_text_checksum,
            adaptation_status,
            modern_hu_text,
            summary_hu,
            moral_hu,
            status,
            created_at or now,
            updated_at or now,
        ),
    )
    return int(cursor.lastrowid)


def _assert_source_is_publishable(connection: sqlite3.Connection, source_id: int) -> None:
    row = connection.execute(
        "SELECT license_status FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"source_id not found: {source_id}")
    license_status = row[0]
    if license_status not in PUBLISHABLE_LICENSE_STATUSES:
        raise IllustrationLicenseGateError(
            "Cannot mark story as 'published': source license_status "
            f"{license_status!r} is not in PUBLISHABLE_LICENSE_STATUSES "
            f"({sorted(PUBLISHABLE_LICENSE_STATUSES)})."
        )


def set_import_meta(connection: sqlite3.Connection, metadata: dict[str, str]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO import_meta(key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )


def initialize_empty_database(
    database_path: str | Path | None = None,
    *,
    atomic: bool = True,
) -> Path:
    """Creates a fresh, schema-only database file (no source/story data).

    Useful for tests and as the Phase-1 buildable artifact; mirrors the
    atomic temp-file-then-replace pattern used by `hymn_sqlite`.
    """
    database = resolve_database_path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    target = _temporary_database_path(database) if atomic else database
    if target.exists():
        target.unlink()

    connection = sqlite3.connect(target)
    try:
        create_schema(connection)
        set_import_meta(
            connection,
            {
                "schema_version": str(SCHEMA_VERSION),
                "build_timestamp": datetime.now(UTC).isoformat(),
                "source_count": "0",
                "story_count": "0",
            },
        )
        integrity = check_integrity(connection)
        if integrity != "ok":
            raise ValueError(f"Invalid illustration SQLite integrity_check: {integrity}")
        connection.commit()
    finally:
        connection.close()

    if atomic:
        _replace_atomically(target, database)
    return database


def _temporary_database_path(database: Path) -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile(
        prefix=f".{database.stem}.",
        suffix=".tmp.sqlite3",
        dir=database.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _replace_atomically(source: Path, target: Path) -> None:
    import os
    import time

    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


__all__ = [
    "ALLOWED_ADAPTATION_STATUSES",
    "ALLOWED_STORY_STATUSES",
    "DATABASE_NAME",
    "DEFAULT_DATABASE_PATH",
    "REQUIRED_TABLES",
    "REQUIRED_VIEWS",
    "SCHEMA_VERSION",
    "IllustrationLicenseGateError",
    "check_integrity",
    "create_schema",
    "initialize_empty_database",
    "insert_source",
    "insert_story",
    "resolve_database_path",
    "set_import_meta",
]
