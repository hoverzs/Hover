"""Read-only Theology DB v1 SQLite repository."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    SCHEMA_VERSION,
    TheologyImportError,
    validate_theology_database,
)


@dataclass(frozen=True)
class TheologyStoreStatus:
    available: bool
    schema_version: str
    author_count: int
    work_count: int
    edition_count: int
    section_count: int
    chunk_count: int
    passage_link_count: int
    content_hash: str = ""
    import_mode: str = ""
    generated_at: str = ""
    database_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "schema_version": self.schema_version,
            "author_count": self.author_count,
            "work_count": self.work_count,
            "edition_count": self.edition_count,
            "section_count": self.section_count,
            "chunk_count": self.chunk_count,
            "passage_link_count": self.passage_link_count,
            "content_hash": self.content_hash,
            "import_mode": self.import_mode,
            "generated_at": self.generated_at,
            "database_path": self.database_path,
        }


@dataclass(frozen=True)
class TheologySearchHit:
    chunk_id: str
    heading: str
    plain_text: str
    snippet: str


class TheologyRepository:
    """Read-only repository over the isolated theology SQLite store."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = (
            Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
        )

    @property
    def available(self) -> bool:
        return self.database_path.is_file()

    def store_status(self) -> TheologyStoreStatus:
        if not self.available:
            return self._unavailable()
        try:
            validation = validate_theology_database(self.database_path)
        except (OSError, sqlite3.Error, TheologyImportError, FileNotFoundError):
            return self._unavailable()
        if validation.schema_version != SCHEMA_VERSION:
            return self._unavailable(schema_version=validation.schema_version)
        return TheologyStoreStatus(
            available=True,
            schema_version=validation.schema_version,
            author_count=validation.author_count,
            work_count=validation.work_count,
            edition_count=validation.edition_count,
            section_count=validation.section_count,
            chunk_count=validation.chunk_count,
            passage_link_count=validation.passage_link_count,
            content_hash=validation.content_hash,
            import_mode=validation.import_mode,
            generated_at=validation.generated_at,
            database_path=str(self.database_path),
        )

    def search_plain_text(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[TheologySearchHit]:
        """Minimal FTS helper for isolated store tests. Not a retrieval API."""
        q = (query or "").strip()
        if not q:
            return []
        connection = self._connect()
        if connection is None:
            return []
        try:
            rows = connection.execute(
                """
                SELECT
                    f.chunk_id AS chunk_id,
                    f.heading AS heading,
                    f.plain_text AS plain_text,
                    snippet(chunks_fts, 2, '**', '**', '…', 32) AS snippet
                FROM chunks_fts f
                WHERE chunks_fts MATCH ?
                LIMIT ?
                """,
                (_fts_phrase_query(q), int(limit)),
            ).fetchall()
            return [
                TheologySearchHit(
                    chunk_id=str(row["chunk_id"]),
                    heading=str(row["heading"] or ""),
                    plain_text=str(row["plain_text"] or ""),
                    snippet=str(row["snippet"] or row["plain_text"] or ""),
                )
                for row in rows
            ]
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    def _unavailable(self, *, schema_version: str = "") -> TheologyStoreStatus:
        return TheologyStoreStatus(
            available=False,
            schema_version=schema_version,
            author_count=0,
            work_count=0,
            edition_count=0,
            section_count=0,
            chunk_count=0,
            passage_link_count=0,
            database_path=str(self.database_path),
        )

    def _connect(self) -> sqlite3.Connection | None:
        if not self.database_path.is_file():
            return None
        try:
            connection = sqlite3.connect(
                f"file:{self.database_path.as_posix()}?mode=ro",
                uri=True,
            )
            connection.row_factory = sqlite3.Row
            return connection
        except sqlite3.Error:
            return None


def _fts_phrase_query(query: str) -> str:
    escaped = query.replace('"', '""')
    return f'"{escaped}"'
