"""Full-corpus Aquifer Bible Dictionary SQLite import and validation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.importers.aquifer_bible_dictionary import (
    AQUIFER_ATTRIBUTION,
    AQUIFER_DICTIONARY_SOURCE_ID,
    AQUIFER_LICENSE,
    AQUIFER_LICENSE_URL,
    AQUIFER_UPSTREAM_REPO,
    DictionaryChunk,
    DictionaryRecord,
    _chunk_html_content,
    _load_articles_by_index,
    _pick_best_duplicate,
    html_to_plain,
    read_upstream_commit,
    resolve_upstream_path,
)
from textus_kb.pilot_registry import org_ref_to_canonical
from textus_kb.paths import PROJECT_ROOT

SCHEMA_VERSION = "1"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "generated" / "aquifer_bible_dictionary.sqlite3"


@dataclass
class DictionarySqliteImportReport:
    database_path: Path
    article_count: int
    chunk_count: int
    passage_link_count: int
    acai_link_count: int
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
            "acai_link_count": self.acai_link_count,
            "upstream_commit": self.upstream_commit,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
            "elapsed_ms": self.elapsed_ms,
            "import_mode": self.import_mode,
        }


@dataclass
class DictionaryStoreValidation:
    schema_version: str
    article_count: int
    chunk_count: int
    passage_link_count: int
    acai_link_count: int
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

        CREATE TABLE IF NOT EXISTS dictionary_articles (
            article_id TEXT PRIMARY KEY,
            content_id TEXT NOT NULL,
            reference_id INTEGER,
            title TEXT NOT NULL,
            index_reference TEXT NOT NULL,
            index_reference_normalized TEXT NOT NULL,
            language TEXT NOT NULL,
            content_html TEXT NOT NULL,
            selection_reason TEXT NOT NULL,
            license TEXT NOT NULL,
            license_url TEXT NOT NULL,
            attribution TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dictionary_chunks (
            chunk_id TEXT PRIMARY KEY,
            article_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            heading TEXT,
            content_html TEXT NOT NULL,
            content_plain TEXT NOT NULL,
            plain_char_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dictionary_passage_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            start_ref TEXT NOT NULL,
            end_ref TEXT NOT NULL,
            start_ref_usfm TEXT,
            end_ref_usfm TEXT,
            canonical_passage TEXT
        );

        CREATE TABLE IF NOT EXISTS dictionary_acai_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            acai_entity_id TEXT NOT NULL,
            match_method TEXT,
            match_confidence REAL,
            upstream_method TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_dictionary_articles_index
            ON dictionary_articles(index_reference_normalized);
        CREATE INDEX IF NOT EXISTS idx_dictionary_chunks_article
            ON dictionary_chunks(article_id, chunk_index);
        CREATE INDEX IF NOT EXISTS idx_dictionary_passage_start
            ON dictionary_passage_links(start_ref);
        CREATE INDEX IF NOT EXISTS idx_dictionary_passage_end
            ON dictionary_passage_links(end_ref);
        CREATE INDEX IF NOT EXISTS idx_dictionary_passage_article
            ON dictionary_passage_links(article_id);
        CREATE INDEX IF NOT EXISTS idx_dictionary_acai_entity
            ON dictionary_acai_links(acai_entity_id);
        CREATE INDEX IF NOT EXISTS idx_dictionary_acai_article
            ON dictionary_acai_links(article_id);
        """
    )


def import_dictionary_sqlite(
    *,
    upstream_root: str | Path | None = None,
    database_path: str | Path | None = None,
    language: str = "eng",
    mode: str = "full",
) -> DictionarySqliteImportReport:
    started = time.perf_counter()
    root = resolve_upstream_path(upstream_root)
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_path = root / language / "metadata.json"
    json_dir = root / language / "json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Aquifer dictionary metadata missing: {metadata_path}")
    if not json_dir.is_dir():
        raise FileNotFoundError(f"Aquifer dictionary JSON dir missing: {json_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    resource_version = str(metadata.get("resource_metadata", {}).get("version", "unknown"))
    upstream_commit = read_upstream_commit(root)

    articles_by_index = _load_articles_by_index(json_dir)
    selected: dict[str, dict[str, Any]] = {}
    for index_reference, candidates in articles_by_index.items():
        selected[index_reference] = _pick_best_duplicate(candidates)

    records: list[DictionaryRecord] = []
    for index_reference in sorted(selected.keys()):
        record = _normalize_full_article(selected[index_reference], index_reference)
        if record is not None:
            records.append(record)

    content_hash = _hash_records(records)
    connection = sqlite3.connect(db_path)
    try:
        create_schema(connection)
        connection.execute("DELETE FROM dictionary_acai_links")
        connection.execute("DELETE FROM dictionary_passage_links")
        connection.execute("DELETE FROM dictionary_chunks")
        connection.execute("DELETE FROM dictionary_articles")
        connection.execute("DELETE FROM store_metadata")

        passage_total = 0
        acai_total = 0
        chunk_total = 0
        for record in records:
            _insert_record(connection, record)
            passage_total += len(record.passage_associations)
            acai_topics = _extract_acai_links_from_record(record)
            acai_total += len(acai_topics)
            chunk_total += len(record.chunks)

        _write_metadata(
            connection,
            resource_version=resource_version,
            upstream_commit=upstream_commit,
            content_hash=content_hash,
            article_count=len(records),
            chunk_count=chunk_total,
            passage_link_count=passage_total,
            acai_link_count=acai_total,
            import_mode=mode,
        )
        connection.commit()
    finally:
        connection.close()

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return DictionarySqliteImportReport(
        database_path=db_path,
        article_count=len(records),
        chunk_count=chunk_total,
        passage_link_count=passage_total,
        acai_link_count=acai_total,
        upstream_commit=upstream_commit,
        source_version=resource_version,
        content_hash=content_hash,
        elapsed_ms=elapsed_ms,
        import_mode=mode,
    )


def validate_dictionary_database(database_path: str | Path | None = None) -> DictionaryStoreValidation:
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if not db_path.is_file():
        raise FileNotFoundError(f"Dictionary SQLite store missing: {db_path}")
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        meta = _read_metadata(connection)
        article_count = connection.execute("SELECT COUNT(*) FROM dictionary_articles").fetchone()[0]
        chunk_count = connection.execute("SELECT COUNT(*) FROM dictionary_chunks").fetchone()[0]
        passage_link_count = connection.execute("SELECT COUNT(*) FROM dictionary_passage_links").fetchone()[0]
        acai_link_count = connection.execute("SELECT COUNT(*) FROM dictionary_acai_links").fetchone()[0]
    finally:
        connection.close()
    return DictionaryStoreValidation(
        schema_version=str(meta.get("schema_version") or ""),
        article_count=int(article_count),
        chunk_count=int(chunk_count),
        passage_link_count=int(passage_link_count),
        acai_link_count=int(acai_link_count),
        source_version=str(meta.get("source_version") or ""),
        upstream_commit=str(meta.get("upstream_commit") or ""),
        content_hash=str(meta.get("content_hash") or ""),
    )


def _normalize_full_article(
    article: dict[str, Any],
    index_reference: str,
) -> DictionaryRecord | None:
    article_id = str(article.get("content_id") or "").strip()
    title = str(article.get("title") or "").strip()
    content_html = str(article.get("content") or "")
    if not article_id or not title or not content_html:
        return None

    passage_associations = _extract_all_passage_associations(article)
    acai_links = _extract_upstream_acai_links(article)
    selection_reason = _full_selection_reason(passage_associations, acai_links)
    chunks = _chunk_html_content(article_id, content_html)
    entity_topics = [
        {
            "entity_id": link["acai_entity_id"],
            "entity_type": "acai",
            "source": "upstream_acai_association",
        }
        for link in acai_links
    ]

    return DictionaryRecord(
        article_id=article_id,
        content_id=article_id,
        reference_id=_safe_int(article.get("reference_id")),
        title=title,
        index_reference=index_reference,
        language=str(article.get("language") or "eng"),
        content_html=content_html,
        chunks=chunks,
        passage_associations=passage_associations,
        entity_topics=entity_topics,
        selection_reason=selection_reason,
    )


def _extract_all_passage_associations(article: dict[str, Any]) -> list[dict[str, str]]:
    associations: list[dict[str, str]] = []
    for passage in article.get("associations", {}).get("passage", []):
        start_ref = str(passage.get("start_ref") or "")
        end_ref = str(passage.get("end_ref") or start_ref)
        if not start_ref.isdigit() or not end_ref.isdigit():
            continue
        associations.append(
            {
                "start_ref": start_ref,
                "end_ref": end_ref,
                "start_ref_usfm": str(passage.get("start_ref_usfm") or ""),
                "end_ref_usfm": str(passage.get("end_ref_usfm") or ""),
            }
        )
    associations.sort(key=lambda item: (item["start_ref"], item["end_ref"]))
    return associations


def _extract_upstream_acai_links(article: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for item in article.get("associations", {}).get("acai", []):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("id") or item.get("entity_id") or "").strip()
        if not entity_id:
            continue
        links.append(
            {
                "acai_entity_id": entity_id,
                "match_method": str(item.get("method") or item.get("match_method") or "upstream"),
                "match_confidence": _safe_float(item.get("confidence") or item.get("match_confidence")),
                "upstream_method": str(item.get("method") or ""),
            }
        )
    links.sort(key=lambda item: item["acai_entity_id"])
    return links


def _extract_acai_links_from_record(record: DictionaryRecord) -> list[dict[str, Any]]:
    seen: set[str] = set()
    links: list[dict[str, Any]] = []
    for topic in record.entity_topics:
        entity_id = str(topic.get("entity_id") or "")
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        links.append(
            {
                "acai_entity_id": entity_id,
                "match_method": "upstream_acai_association",
                "match_confidence": None,
                "upstream_method": "upstream_acai_association",
            }
        )
    return links


def _full_selection_reason(
    passage_associations: list[dict[str, str]],
    acai_links: list[dict[str, Any]],
) -> str:
    if passage_associations:
        return "direct_passage_association"
    if acai_links:
        return "direct_acai_association"
    return "full_corpus_index"


def _insert_record(connection: sqlite3.Connection, record: DictionaryRecord) -> None:
    connection.execute(
        """
        INSERT INTO dictionary_articles (
            article_id, content_id, reference_id, title, index_reference,
            index_reference_normalized, language, content_html, selection_reason,
            license, license_url, attribution
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.article_id,
            record.content_id,
            record.reference_id,
            record.title,
            record.index_reference,
            record.index_reference.lower().strip(),
            record.language,
            record.content_html,
            record.selection_reason,
            record.license,
            record.license_url,
            record.attribution,
        ),
    )
    for chunk in record.chunks:
        connection.execute(
            """
            INSERT INTO dictionary_chunks (
                chunk_id, article_id, chunk_index, heading, content_html,
                content_plain, plain_char_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.chunk_id,
                record.article_id,
                chunk.chunk_index,
                chunk.heading,
                chunk.content_html,
                chunk.content_plain,
                len(chunk.content_plain),
            ),
        )
    for passage in record.passage_associations:
        canonical = org_ref_to_canonical(passage["start_ref"])
        if passage["start_ref"] != passage["end_ref"]:
            end_canonical = org_ref_to_canonical(passage["end_ref"])
            if canonical and end_canonical:
                canonical = f"{canonical.split('.')[0]}.{canonical.split('.')[1]}.{canonical.split('.')[2]}-{end_canonical.split('.')[2]}"
        connection.execute(
            """
            INSERT INTO dictionary_passage_links (
                article_id, start_ref, end_ref, start_ref_usfm, end_ref_usfm, canonical_passage
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.article_id,
                passage["start_ref"],
                passage["end_ref"],
                passage.get("start_ref_usfm"),
                passage.get("end_ref_usfm"),
                canonical,
            ),
        )
    for link in _extract_acai_links_from_record(record):
        connection.execute(
            """
            INSERT INTO dictionary_acai_links (
                article_id, acai_entity_id, match_method, match_confidence, upstream_method
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.article_id,
                link["acai_entity_id"],
                link["match_method"],
                link["match_confidence"],
                link["upstream_method"],
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
    acai_link_count: int,
    import_mode: str,
) -> None:
    rows = {
        "schema_version": SCHEMA_VERSION,
        "source_id": AQUIFER_DICTIONARY_SOURCE_ID,
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
        "acai_link_count": str(acai_link_count),
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


def _hash_records(records: list[DictionaryRecord]) -> str:
    payload = json.dumps([record.to_dict() for record in records], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
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

    report = import_dictionary_sqlite(upstream_root=upstream, database_path=output)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
