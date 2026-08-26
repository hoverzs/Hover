"""Read-only Aquifer Study Notes SQLite repository."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.importers.aquifer_study_notes import (
    AQUIFER_ATTRIBUTION,
    AQUIFER_LICENSE,
    AQUIFER_LICENSE_URL,
    AQUIFER_SOURCE_ID,
)
from textus_kb.importers.aquifer_study_notes_sqlite import (
    DEFAULT_DATABASE_PATH,
    validate_study_notes_database,
)
from textus_kb.pilot_registry import org_ref_bounds, references_overlap


@dataclass(frozen=True)
class StudyNotesStoreStatus:
    available: bool
    schema_version: str
    source_version: str
    upstream_commit: str
    article_count: int
    chunk_count: int
    passage_link_count: int
    content_hash: str
    import_mode: str
    database_path: str
    license: str
    license_url: str
    attribution: str
    upstream_repository: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "schema_version": self.schema_version,
            "source_version": self.source_version,
            "upstream_commit": self.upstream_commit,
            "article_count": self.article_count,
            "chunk_count": self.chunk_count,
            "passage_link_count": self.passage_link_count,
            "content_hash": self.content_hash,
            "import_mode": self.import_mode,
            "database_path": self.database_path,
            "license": self.license,
            "license_url": self.license_url,
            "attribution": self.attribution,
            "upstream_repository": self.upstream_repository,
        }


class AquiferStudyNotesRepository:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH

    @property
    def available(self) -> bool:
        return self.database_path.is_file()

    def store_status(self) -> StudyNotesStoreStatus:
        if not self.available:
            return StudyNotesStoreStatus(
                available=False,
                schema_version="",
                source_version="",
                upstream_commit="",
                article_count=0,
                chunk_count=0,
                passage_link_count=0,
                content_hash="",
                import_mode="",
                database_path=str(self.database_path),
                license=AQUIFER_LICENSE,
                license_url=AQUIFER_LICENSE_URL,
                attribution=AQUIFER_ATTRIBUTION,
                upstream_repository="",
            )
        validation = validate_study_notes_database(self.database_path)
        meta = self._metadata()
        return StudyNotesStoreStatus(
            available=True,
            schema_version=validation.schema_version,
            source_version=validation.source_version,
            upstream_commit=validation.upstream_commit,
            article_count=validation.article_count,
            chunk_count=validation.chunk_count,
            passage_link_count=validation.passage_link_count,
            content_hash=validation.content_hash,
            import_mode=str(meta.get("import_mode") or ""),
            database_path=str(self.database_path),
            license=str(meta.get("license") or AQUIFER_LICENSE),
            license_url=str(meta.get("license_url") or AQUIFER_LICENSE_URL),
            attribution=str(meta.get("attribution") or AQUIFER_ATTRIBUTION),
            upstream_repository=str(meta.get("upstream_repository") or ""),
        )

    def metadata(self) -> dict[str, str]:
        return self._metadata()

    def article_by_id(self, article_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM study_articles WHERE article_id = ?",
            (str(article_id),),
        )
        return dict(row) if row is not None else None

    def notes_for_passage(self, reference: CanonicalReference | str) -> list[dict[str, Any]]:
        canonical = (
            reference
            if isinstance(reference, CanonicalReference)
            else CanonicalReference.parse(reference)
        )
        org_lo, org_hi = org_ref_bounds(canonical)
        book = org_lo[:2]
        rows = self._fetchall(
            """
            SELECT DISTINCT a.*
            FROM study_articles a
            JOIN study_passage_links p ON p.article_id = a.article_id
            WHERE p.start_ref <= ? AND p.end_ref >= ?
              AND substr(p.start_ref, 1, 2) = ?
              AND substr(p.end_ref, 1, 2) = ?
            ORDER BY a.canonical_reference, a.article_id
            """,
            (org_hi, org_lo, book, book),
        )
        filtered: list[dict[str, Any]] = []
        for row in rows:
            try:
                note_ref = CanonicalReference.parse(str(row["canonical_reference"]))
            except Exception:
                continue
            if references_overlap(canonical, note_ref):
                filtered.append(dict(row))
        return filtered

    def chunks_for_passage(self, reference: CanonicalReference | str) -> list[dict[str, Any]]:
        notes = self.notes_for_passage(reference)
        if not notes:
            return []
        article_ids = [row["article_id"] for row in notes]
        placeholders = ",".join("?" for _ in article_ids)
        note_map = {row["article_id"]: row for row in notes}
        rows = self._fetchall(
            f"""
            SELECT c.*, a.title, a.canonical_reference, a.upstream_reference_usfm,
                   a.license, a.license_url, a.attribution
            FROM study_chunks c
            JOIN study_articles a ON a.article_id = c.article_id
            WHERE c.article_id IN ({placeholders})
            ORDER BY a.canonical_reference, c.article_id, c.chunk_index
            """,
            tuple(article_ids),
        )
        chunks: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            note = note_map.get(item["article_id"], {})
            item["title"] = note.get("title") or item.get("title")
            chunks.append(item)
        return chunks

    def chunks_for_article(self, article_id: str) -> list[dict[str, Any]]:
        article = self.article_by_id(article_id)
        if article is None:
            return []
        rows = self._fetchall(
            """
            SELECT c.*, a.title, a.canonical_reference, a.upstream_reference_usfm,
                   a.license, a.license_url, a.attribution
            FROM study_chunks c
            JOIN study_articles a ON a.article_id = c.article_id
            WHERE c.article_id = ?
            ORDER BY c.chunk_index
            """,
            (str(article_id),),
        )
        return [dict(row) for row in rows]

    def _metadata(self) -> dict[str, str]:
        if not self.available:
            return {}
        connection = self._connect()
        try:
            rows = connection.execute("SELECT key, value FROM store_metadata").fetchall()
            return {str(key): str(value) for key, value in rows}
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        connection = self._connect()
        try:
            return list(connection.execute(query, params).fetchall())
        finally:
            connection.close()

    def _fetchone(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(query, params).fetchone()
        finally:
            connection.close()
