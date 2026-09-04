"""Derived, cache-only Hungarian Commentary translation store.

Completely separate from the canonical, read-only ``commentary.sqlite3``
(``textus_kb.repositories.commentary_repository``) -- this module never
opens that database and never writes to it. A translation here is always
DERIVED content, keyed to the exact original section content it was
produced from (``source_fingerprint``); it is never treated as, or
allowed to silently stand in for, the original commentary text.

Fail-closed throughout: any read/write failure against this store (file
missing, corrupt schema, locked file, disk error, Supabase network/auth
error) degrades to "no cached translation" rather than raising --
callers (``commentary_translation_service``) treat that exactly like a
cache miss. This store is never on the path of the original,
retrieval-only Commentary browsing experience.

Two backends, selected by ``TEXTUS_COMMENTARY_TRANSLATION_BACKEND``
(default ``"sqlite"``):

- ``sqlite`` (default): the original local-file store below. A typical
  deployment's local filesystem is ephemeral/per-instance (container
  redeploys and restarts get a fresh disk, and a multi-instance
  deployment doesn't share one instance's disk with another) -- so this
  backend is a genuinely durable, cross-user cache ONLY when the process
  keeps one persistent disk across restarts and users. Treat it as a
  dev/test backend unless that is independently confirmed for the actual
  deploy target.
- ``supabase``: a shared Postgres table (``commentary_translations``,
  ld. ``scripts/setup_commentary_translation_table.py`` for the DDL),
  keyed by the exact same ``(section_id, source_fingerprint, language,
  policy_version)`` composite used as the SQLite ``UNIQUE`` constraint --
  now the Postgres ``PRIMARY KEY`` / upsert-conflict-target, so two users
  translating the same section concurrently safely converge on one row
  (last-write-wins) instead of racing on two different local disks.

Callers that pass an EXPLICIT ``database_path`` (every test in this
repo, via ``commentary_ui._translation_database_path`` /
``commentary_translation_service``'s own ``database_path`` kwarg) always
get the plain local-SQLite-at-that-path behavior, regardless of the
configured backend -- backend selection only ever applies to the
production default path (``database_path=None``), so no existing
dev/test caller changes behavior.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from textus_kb.paths import GENERATED_DATA_DIR

DEFAULT_TRANSLATION_DB_PATH = GENERATED_DATA_DIR / "commentary_translations.sqlite3"
STORE_SCHEMA_VERSION = "1"

TRANSLATION_BACKEND_ENV_VAR = "TEXTUS_COMMENTARY_TRANSLATION_BACKEND"
TRANSLATION_SUPABASE_TABLE_ENV_VAR = "TEXTUS_COMMENTARY_TRANSLATION_TABLE"
DEFAULT_TRANSLATION_SUPABASE_TABLE = "commentary_translations"


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
    schema, locked file, Supabase network/auth error) returns None --
    exactly like a cache miss, never an exception; the caller regenerates
    instead of crashing.

    An explicit ``database_path`` always uses the local SQLite file at
    that path (test/dev isolation, unaffected by backend config). Only
    the production default (``database_path=None``) is eligible for the
    ``supabase`` backend when configured."""
    if database_path is None and _configured_backend() == "supabase":
        return _supabase_get_translation(
            section_id, source_fingerprint, language=language, policy_version=policy_version
        )
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
    when ``translated_text`` is blank (never cache an empty/failed result).

    Same backend-selection rule as ``get_translation``: an explicit
    ``database_path`` always writes to that local SQLite file; only the
    production default routes to the configured ``supabase`` backend."""
    text = (translated_text or "").strip()
    if not text:
        return None
    if database_path is None and _configured_backend() == "supabase":
        return _supabase_save_translation(
            section_id=section_id,
            source_fingerprint=source_fingerprint,
            language=language,
            policy_version=policy_version,
            translated_text=text,
            provider_model=provider_model,
        )
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


def _configured_backend() -> str:
    env_value = os.environ.get(TRANSLATION_BACKEND_ENV_VAR, "").strip().lower()
    if env_value:
        return env_value
    secret_value = _translation_secret_value("backend").strip().lower()
    if secret_value:
        return secret_value
    return "sqlite"


def _configured_supabase_table() -> str:
    env_value = os.environ.get(TRANSLATION_SUPABASE_TABLE_ENV_VAR, "").strip()
    if env_value:
        return env_value
    secret_value = _translation_secret_value("table").strip()
    if secret_value:
        return secret_value
    return DEFAULT_TRANSLATION_SUPABASE_TABLE


def _translation_secret_value(key: str) -> str:
    try:
        import streamlit as st

        cfg = st.secrets.get("commentary_translation", {})
        if isinstance(cfg, dict):
            value = cfg.get(key)
        else:
            value = getattr(cfg, key, "")
        return str(value or "").strip()
    except Exception:
        return ""


def _supabase_get_translation(
    section_id: str,
    source_fingerprint: str,
    *,
    language: str,
    policy_version: str,
) -> TranslationRecord | None:
    """Fail-closed read from the shared Postgres translation cache -- any
    network/auth/query error degrades to a plain cache miss, exactly like
    the SQLite backend's own fail-closed contract."""
    try:
        from supabase_client import get_supabase_client

        client = get_supabase_client()
        response = (
            client.table(_configured_supabase_table())
            .select("section_id, source_fingerprint, language, policy_version, "
                     "translated_text, provider_model, created_at")
            .eq("section_id", section_id)
            .eq("source_fingerprint", source_fingerprint)
            .eq("language", language)
            .eq("policy_version", policy_version)
            .limit(1)
            .execute()
        )
        rows = response.data or []
    except Exception:  # noqa: BLE001 - fail-closed, same as sqlite3.Error above
        return None
    if not rows:
        return None
    row = rows[0]
    return TranslationRecord(
        section_id=str(row["section_id"]),
        source_fingerprint=str(row["source_fingerprint"]),
        language=str(row["language"]),
        policy_version=str(row["policy_version"]),
        translated_text=str(row["translated_text"]),
        provider_model=str(row.get("provider_model") or ""),
        created_at=str(row["created_at"]),
    )


def _supabase_save_translation(
    *,
    section_id: str,
    source_fingerprint: str,
    language: str,
    policy_version: str,
    translated_text: str,
    provider_model: str,
) -> TranslationRecord | None:
    """Fail-closed upsert into the shared Postgres translation cache, on
    the same ``(section_id, source_fingerprint, language, policy_version)``
    conflict target as the table's own primary key -- two users
    translating the same section concurrently safely converge on one row
    (last-write-wins) instead of racing. Never raises: a write failure
    here must never take down a caller that already has valid translated
    text in hand (ld. ``save_translation``'s own docstring)."""
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        from supabase_client import get_supabase_client

        client = get_supabase_client()
        client.table(_configured_supabase_table()).upsert(
            {
                "section_id": section_id,
                "source_fingerprint": source_fingerprint,
                "language": language,
                "policy_version": policy_version,
                "translated_text": translated_text,
                "provider_model": provider_model,
                "created_at": created_at,
            },
            on_conflict="section_id,source_fingerprint,language,policy_version",
        ).execute()
    except Exception:  # noqa: BLE001 - fail-closed, same as (sqlite3.Error, OSError) above
        return None
    return TranslationRecord(
        section_id=section_id,
        source_fingerprint=source_fingerprint,
        language=language,
        policy_version=policy_version,
        translated_text=translated_text,
        provider_model=provider_model,
        created_at=created_at,
    )


__all__ = [
    "DEFAULT_TRANSLATION_DB_PATH",
    "DEFAULT_TRANSLATION_SUPABASE_TABLE",
    "STORE_SCHEMA_VERSION",
    "TRANSLATION_BACKEND_ENV_VAR",
    "TRANSLATION_SUPABASE_TABLE_ENV_VAR",
    "TranslationRecord",
    "compute_source_fingerprint",
    "get_translation",
    "save_translation",
]
