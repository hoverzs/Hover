"""Derived, cache-only Hungarian Commentary translation store.

Completely separate from the canonical, read-only ``commentary.sqlite3``
(``textus_kb.repositories.commentary_repository``) -- this module never
opens that database and never writes to it. A translation here is always
DERIVED content, keyed to the exact original section content it was
produced from (``source_fingerprint``); it is never treated as, or
allowed to silently stand in for, the original commentary text.

Fail-closed throughout: any read/write failure against this store (file
missing, corrupt schema, locked file, disk error) degrades to "no cached
translation" rather than raising -- callers (``commentary_translation_
service``) treat that exactly like a cache miss. This store is never on
the path of the original, retrieval-only Commentary browsing experience.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from textus_kb.paths import GENERATED_DATA_DIR

DEFAULT_TRANSLATION_DB_PATH = GENERATED_DATA_DIR / "commentary_translations.sqlite3"
STORE_SCHEMA_VERSION = "1"


def compute_source_fingerprint(chunk_texts: Sequence[str]) -> str:
    """Deterministic fingerprint of a section's full, ordered chunk text.

    Any change to the canonical section's own content (a corpus rebuild,
    a chunk edit/re-import) changes this fingerprint, which automatically
    makes every previously cached translation for that section ineligible
    for a cache hit -- without ever deleting or touching the old row."""
    joined = "\n\n".join(chunk_texts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TranslationRecord:
    section_id: str
    source_fingerprint: str
    language: str
    policy_version: str
    translated_text: str
    provider_model: str
    created_at: str


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL,
            language TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            provider_model TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(section_id, source_fingerprint, language, policy_version)
        );

        CREATE INDEX IF NOT EXISTS idx_translations_lookup
            ON translations(section_id, language, policy_version);
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO store_metadata(key, value) VALUES (?, ?)",
        ("schema_version", STORE_SCHEMA_VERSION),
    )


def get_translation(
    section_id: str,
    source_fingerprint: str,
    *,
    language: str,
    policy_version: str,
    database_path: str | Path | None = None,
) -> TranslationRecord | None:
    """Fail-closed cache lookup. Any DB error (missing file, corrupt
    schema, locked file) returns None -- exactly like a cache miss, never
    an exception; the caller regenerates instead of crashing."""
    path = Path(database_path) if database_path is not None else DEFAULT_TRANSLATION_DB_PATH
    if not path.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT section_id, source_fingerprint, language, policy_version,
                       translated_text, provider_model, created_at
                FROM translations
                WHERE section_id = ? AND source_fingerprint = ?
                  AND language = ? AND policy_version = ?
                """,
                (section_id, source_fingerprint, language, policy_version),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return TranslationRecord(
        section_id=str(row["section_id"]),
        source_fingerprint=str(row["source_fingerprint"]),
        language=str(row["language"]),
        policy_version=str(row["policy_version"]),
        translated_text=str(row["translated_text"]),
        provider_model=str(row["provider_model"] or ""),
        created_at=str(row["created_at"]),
    )


def save_translation(
    *,
    section_id: str,
    source_fingerprint: str,
    language: str,
    policy_version: str,
    translated_text: str,
    provider_model: str = "",
    database_path: str | Path | None = None,
) -> TranslationRecord | None:
    """Persist one successful translation. Never raises: caching is a pure
    optimization layered on top of a real generation result, so a storage
    failure here must never take down the caller that already has valid
    translated text in hand. Returns None (not stored) on any failure, or
    when ``translated_text`` is blank (never cache an empty/failed result)."""
    text = (translated_text or "").strip()
    if not text:
        return None
    path = Path(database_path) if database_path is not None else DEFAULT_TRANSLATION_DB_PATH
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            _create_schema(connection)
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO translations (
                        section_id, source_fingerprint, language, policy_version,
                        translated_text, provider_model, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section_id,
                        source_fingerprint,
                        language,
                        policy_version,
                        text,
                        provider_model,
                        created_at,
                    ),
                )
        finally:
            connection.close()
    except (sqlite3.Error, OSError):
        return None
    return TranslationRecord(
        section_id=section_id,
        source_fingerprint=source_fingerprint,
        language=language,
        policy_version=policy_version,
        translated_text=text,
        provider_model=provider_model,
        created_at=created_at,
    )


__all__ = [
    "DEFAULT_TRANSLATION_DB_PATH",
    "STORE_SCHEMA_VERSION",
    "TranslationRecord",
    "compute_source_fingerprint",
    "get_translation",
    "save_translation",
]
