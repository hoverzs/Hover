"""Full-corpus Aquifer Study Notes SQLite import and validation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.aquifer_study_notes import (
    AQUIFER_ATTRIBUTION,
    AQUIFER_LICENSE,
    AQUIFER_LICENSE_URL,
    AQUIFER_SOURCE_ID,
    AQUIFER_UPSTREAM_REPO,
    StudyNoteRecord,
    _chunk_html_content,
    _first_passage_usfm,
    index_reference_to_canonical,
    read_upstream_commit,
    resolve_upstream_path,
)
from textus_kb.pilot_registry import org_ref_to_canonical
from textus_kb.paths import PROJECT_ROOT

SCHEMA_VERSION = "1"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "generated" / "aquifer_study_notes.sqlite3"


@dataclass
class StudyNotesSqliteImportReport:
    database_path: Path
    article_count: int
    chunk_count: int
    passage_link_count: int
    upstream_commit: str
    source_version: str
    content_hash: str
    elapsed_ms: int
    import_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": str(self.database_path),
            "article_count": self.article_count,
            "chunk_count": self.chunk_count,
            "passage_link_count": self.passage_link_count,
            "upstream_commit": self.upstream_commit,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
            "elapsed_ms": self.elapsed_ms,
            "import_mode": self.import_mode,
        }


@dataclass
class StudyNotesStoreValidation:
    schema_version: str
    article_count: int
    chunk_count: int
    passage_link_count: int
    source_version: str
    upstream_commit: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS study_articles (
            article_id TEXT PRIMARY KEY,
            content_id TEXT NOT NULL,
            reference_id INTEGER,
            title TEXT NOT NULL,
            index_reference TEXT NOT NULL,
            canonical_reference TEXT NOT NULL,
            usfm_book_num INTEGER NOT NULL,
            start_chapter INTEGER NOT NULL,
            start_verse INTEGER NOT NULL,
            end_chapter INTEGER NOT NULL,
            end_verse INTEGER NOT NULL,
            upstream_reference_usfm TEXT,
            language TEXT NOT NULL,
            content_html TEXT NOT NULL,
            license TEXT NOT NULL,
            license_url TEXT NOT NULL,
            attribution TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS study_passage_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            start_ref TEXT NOT NULL,
            end_ref TEXT NOT NULL,
            start_ref_usfm TEXT,
            end_ref_usfm TEXT,
            canonical_passage TEXT
        );

        CREATE TABLE IF NOT EXISTS study_chunks (
            chunk_id TEXT PRIMARY KEY,
            article_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content_html TEXT NOT NULL,
            content_plain TEXT NOT NULL,
            plain_char_count INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_study_articles_canonical
            ON study_articles(canonical_reference);
        CREATE INDEX IF NOT EXISTS idx_study_articles_book_chapter
            ON study_articles(usfm_book_num, start_chapter, start_verse);
        CREATE INDEX IF NOT EXISTS idx_study_passage_start
            ON study_passage_links(start_ref);
        CREATE INDEX IF NOT EXISTS idx_study_passage_end
            ON study_passage_links(end_ref);
        CREATE INDEX IF NOT EXISTS idx_study_passage_article
            ON study_passage_links(article_id);
        CREATE INDEX IF NOT EXISTS idx_study_chunks_article
            ON study_chunks(article_id, chunk_index);
        """
    )


def import_study_notes_sqlite(
    *,
    upstream_root: str | Path | None = None,
    database_path: str | Path | None = None,
    language: str = "eng",
    mode: str = "full",
) -> StudyNotesSqliteImportReport:
    started = time.perf_counter()
    root = resolve_upstream_path(upstream_root)
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_path = root / language / "metadata.json"
    json_dir = root / language / "json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Aquifer study notes metadata missing: {metadata_path}")
    if not json_dir.is_dir():
        raise FileNotFoundError(f"Aquifer study notes JSON dir missing: {json_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    resource_version = str(metadata.get("resource_metadata", {}).get("version", "unknown"))
    upstream_commit = read_upstream_commit(root)

    records: list[StudyNoteRecord] = []
    for path in sorted(json_dir.glob("*.content.json")):
        articles = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(articles, list):
            continue
        for article in articles:
            if not isinstance(article, dict):
                continue
            record = _normalize_full_article(article)
            if record is not None:
                records.append(record)

    records.sort(key=lambda item: (item.index_reference, item.article_id))
    content_hash = _hash_records(records)

    connection = sqlite3.connect(db_path)
    try:
        create_schema(connection)
        connection.execute("DELETE FROM study_passage_links")
        connection.execute("DELETE FROM study_chunks")
        connection.execute("DELETE FROM study_articles")
        connection.execute("DELETE FROM store_metadata")

        passage_total = 0
        chunk_total = 0
        for record in records:
            _insert_record(connection, record)
            passage_total += len(_passage_links_for_article(record))
            chunk_total += len(record.chunks)

        _write_metadata(
            connection,
            resource_version=resource_version,
            upstream_commit=upstream_commit,
            content_hash=content_hash,
            article_count=len(records),
            chunk_count=chunk_total,
            passage_link_count=passage_total,
            import_mode=mode,
        )
        connection.commit()
    finally:
        connection.close()

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return StudyNotesSqliteImportReport(
        database_path=db_path,
        article_count=len(records),
        chunk_count=chunk_total,
        passage_link_count=passage_total,
        upstream_commit=upstream_commit,
        source_version=resource_version,
        content_hash=content_hash,
        elapsed_ms=elapsed_ms,
        import_mode=mode,
    )


def validate_study_notes_database(database_path: str | Path | None = None) -> StudyNotesStoreValidation:
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if not db_path.is_file():
        raise FileNotFoundError(f"Study Notes SQLite store missing: {db_path}")
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        meta = _read_metadata(connection)
        article_count = connection.execute("SELECT COUNT(*) FROM study_articles").fetchone()[0]
        chunk_count = connection.execute("SELECT COUNT(*) FROM study_chunks").fetchone()[0]
        passage_link_count = connection.execute("SELECT COUNT(*) FROM study_passage_links").fetchone()[0]
    finally:
        connection.close()
    return StudyNotesStoreValidation(
        schema_version=str(meta.get("schema_version") or ""),
        article_count=int(article_count),
        chunk_count=int(chunk_count),
        passage_link_count=int(passage_link_count),
        source_version=str(meta.get("source_version") or ""),
        upstream_commit=str(meta.get("upstream_commit") or ""),
        content_hash=str(meta.get("content_hash") or ""),
    )


def _normalize_full_article(article: dict[str, Any]) -> StudyNoteRecord | None:
    article_id = str(article.get("content_id") or "").strip()
    title = str(article.get("title") or "").strip()
    index_reference = str(article.get("index_reference") or "").strip()
    content_html = str(article.get("content") or "")
    if not article_id or not index_reference or not content_html:
        return None
    try:
        canonical = index_reference_to_canonical(index_reference)
    except CanonicalReferenceError:
        return None

    upstream_usfm = _first_passage_usfm(article)
    chunks = _chunk_html_content(article_id, content_html)
    return StudyNoteRecord(
        article_id=article_id,
        content_id=article_id,
        reference_id=_safe_int(article.get("reference_id")),
        title=title,
        index_reference=index_reference,
        canonical_reference=canonical,
        upstream_reference_usfm=upstream_usfm,
        language=str(article.get("language") or "eng"),
        content_html=content_html,
        chunks=chunks,
    )


def _passage_links_for_article(record: StudyNoteRecord) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    index_reference = record.index_reference
    parts = index_reference.split("-")
    start = parts[0]
    end = parts[1] if len(parts) > 1 else start
    if len(start) == 8 and start.isdigit() and len(end) == 8 and end.isdigit():
        links.append(
            {
                "start_ref": start,
                "end_ref": end,
                "start_ref_usfm": record.upstream_reference_usfm or "",
                "end_ref_usfm": record.upstream_reference_usfm or "",
            }
        )
    return links


def _insert_record(connection: sqlite3.Connection, record: StudyNoteRecord) -> None:
    parsed = CanonicalReference.parse(record.canonical_reference)
    connection.execute(
        """
        INSERT INTO study_articles (
            article_id, content_id, reference_id, title, index_reference,
            canonical_reference, usfm_book_num, start_chapter, start_verse,
            end_chapter, end_verse, upstream_reference_usfm, language,
            content_html, license, license_url, attribution
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.article_id,
            record.content_id,
            record.reference_id,
            record.title,
            record.index_reference,
            record.canonical_reference,
            int(record.index_reference[:2]),
            parsed.start_chapter,
            parsed.start_verse,
            parsed.end_chapter,
            parsed.end_verse,
            record.upstream_reference_usfm,
            record.language,
            record.content_html,
            record.license,
            record.license_url,
            record.attribution,
        ),
    )
    for chunk in record.chunks:
        connection.execute(
            """
            INSERT INTO study_chunks (
                chunk_id, article_id, chunk_index, content_html, content_plain, plain_char_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.chunk_id,
                record.article_id,
                chunk.chunk_index,
                chunk.content_html,
                chunk.content_plain,
                len(chunk.content_plain),
            ),
        )
    for passage in _passage_links_for_article(record):
        connection.execute(
            """
            INSERT INTO study_passage_links (
                article_id, start_ref, end_ref, start_ref_usfm, end_ref_usfm, canonical_passage
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.article_id,
                passage["start_ref"],
                passage["end_ref"],
                passage.get("start_ref_usfm"),
                passage.get("end_ref_usfm"),
                record.canonical_reference,
            ),
        )


def _write_metadata(
    connection: sqlite3.Connection,
    *,
    resource_version: str,
    upstream_commit: str,
    content_hash: str,
    article_count: int,
    chunk_count: int,
    passage_link_count: int,
    import_mode: str,
) -> None:
    rows = {
        "schema_version": SCHEMA_VERSION,
        "source_id": AQUIFER_SOURCE_ID,
        "source_version": resource_version,
        "upstream_commit": upstream_commit,
        "upstream_repository": AQUIFER_UPSTREAM_REPO,
        "license": AQUIFER_LICENSE,
        "license_url": AQUIFER_LICENSE_URL,
        "attribution": AQUIFER_ATTRIBUTION,
        "content_hash": content_hash,
        "article_count": str(article_count),
        "chunk_count": str(chunk_count),
        "passage_link_count": str(passage_link_count),
        "import_mode": import_mode,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    for key, value in rows.items():
        connection.execute(
            "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
            (key, value),
        )


def _read_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM store_metadata").fetchall()
    return {str(key): str(value) for key, value in rows}


def _hash_records(records: list[StudyNoteRecord]) -> str:
    payload = json.dumps([record.to_dict() for record in records], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    upstream = None
    output = None
    i = 0
    while i < len(args):
        if args[i] == "--upstream" and i + 1 < len(args):
            upstream = args[i + 1]
            i += 2
            continue
        if args[i] == "--output" and i + 1 < len(args):
            output = args[i + 1]
            i += 2
            continue
        i += 1

    report = import_study_notes_sqlite(upstream_root=upstream, database_path=output)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
