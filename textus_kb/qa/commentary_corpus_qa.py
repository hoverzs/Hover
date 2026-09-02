"""Read-only Commentary corpus QA report: machine JSON + human summary.

Every check here is defensive re-verification of invariants the importer
and the DB schema (FK + UNIQUE constraints) already enforce at write time.
A non-empty finding in this report therefore means either the store was
built outside the normal importer path, or a real bug — it is not
expected to ever find anything on a store built by
``textus_kb.importers.commentary_sqlite``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.commentary_sqlite import DEFAULT_DATABASE_PATH


@dataclass
class CommentaryCorpusQAReport:
    available: bool
    database_path: str
    schema_version: str = ""
    content_hash: str = ""
    generated_at: str = ""
    works: list[dict[str, Any]] = field(default_factory=list)
    editions: list[dict[str, Any]] = field(default_factory=list)
    source_files: list[dict[str, Any]] = field(default_factory=list)
    section_count: int = 0
    chunk_count: int = 0
    passage_link_count: int = 0
    exact_verse_link_count: int = 0
    range_link_count: int = 0
    multi_passage_sections: list[dict[str, Any]] = field(default_factory=list)
    orphan_sections: list[dict[str, Any]] = field(default_factory=list)
    passageless_sections_by_type: dict[str, int] = field(default_factory=dict)
    invalid_references: list[dict[str, Any]] = field(default_factory=list)
    duplicate_section_ids: list[str] = field(default_factory=list)
    duplicate_chunk_ids: list[str] = field(default_factory=list)
    duplicate_passage_links: list[dict[str, Any]] = field(default_factory=list)
    cross_edition_hierarchy_issues: list[dict[str, Any]] = field(default_factory=list)
    coverage_by_book: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)


def generate_commentary_corpus_qa(
    database_path: str | Path | None = None,
) -> CommentaryCorpusQAReport:
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if not db_path.is_file():
        return CommentaryCorpusQAReport(available=False, database_path=str(db_path))

    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return _build_report(connection, db_path)
    finally:
        connection.close()


def _build_report(connection: sqlite3.Connection, db_path: Path) -> CommentaryCorpusQAReport:
    meta = {
        row["key"]: row["value"]
        for row in connection.execute("SELECT key, value FROM store_metadata")
    }
    report = CommentaryCorpusQAReport(
        available=True,
        database_path=str(db_path),
        schema_version=meta.get("schema_version", ""),
        content_hash=meta.get("content_hash", ""),
        generated_at=meta.get("generated_at", ""),
    )

    report.works = [
        {
            "work_id": row["work_id"],
            "title": row["title"],
            "work_type": row["work_type"],
            "edition_count": row["edition_count"],
        }
        for row in connection.execute(
            """
            SELECT w.work_id AS work_id, w.title AS title, w.work_type AS work_type,
                   COUNT(e.edition_id) AS edition_count
            FROM works w
            LEFT JOIN editions e ON e.work_id = w.work_id
            GROUP BY w.work_id
            ORDER BY w.work_id
            """
        )
    ]
    report.editions = [
        {
            "edition_id": row["edition_id"],
            "work_id": row["work_id"],
            "language": row["language"],
            "source_url": row["source_url"],
            "section_count": row["section_count"],
        }
        for row in connection.execute(
            """
            SELECT e.edition_id AS edition_id, e.work_id AS work_id, e.language AS language,
                   e.source_url AS source_url, COUNT(s.section_id) AS section_count
            FROM editions e
            LEFT JOIN sections s ON s.edition_id = e.edition_id
            GROUP BY e.edition_id
            ORDER BY e.edition_id
            """
        )
    ]
    report.source_files = [
        {
            "source_file_id": row["source_file_id"],
            "edition_id": row["edition_id"],
            "file_name": row["file_name"],
            "raw_sha256": row["raw_sha256"],
            "byte_size": row["byte_size"],
        }
        for row in connection.execute(
            "SELECT source_file_id, edition_id, file_name, raw_sha256, byte_size FROM source_files "
            "ORDER BY source_file_id"
        )
    ]

    report.section_count = _scalar(connection, "SELECT COUNT(*) FROM sections")
    report.chunk_count = _scalar(connection, "SELECT COUNT(*) FROM chunks")
    report.passage_link_count = _scalar(connection, "SELECT COUNT(*) FROM section_passage_links")
    report.exact_verse_link_count = _scalar(
        connection,
        "SELECT COUNT(*) FROM section_passage_links "
        "WHERE start_chapter = end_chapter AND start_verse = end_verse",
    )
    report.range_link_count = report.passage_link_count - report.exact_verse_link_count

    report.multi_passage_sections = [
        {"section_id": row["section_id"], "heading": row["heading"], "passage_count": row["cnt"]}
        for row in connection.execute(
            """
            SELECT s.section_id AS section_id, s.heading AS heading, COUNT(*) AS cnt
            FROM section_passage_links p
            JOIN sections s ON s.section_id = p.section_id
            GROUP BY p.section_id
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, s.section_id
            """
        )
    ]

    report.orphan_sections = [
        {"section_id": row["section_id"], "parent_section_id": row["parent_section_id"]}
        for row in connection.execute(
            """
            SELECT s.section_id AS section_id, s.parent_section_id AS parent_section_id
            FROM sections s
            WHERE s.parent_section_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM sections p WHERE p.section_id = s.parent_section_id
              )
            """
        )
    ]

    passageless = connection.execute(
        """
        SELECT COALESCE(s.section_type, '<none>') AS section_type, COUNT(*) AS cnt
        FROM sections s
        WHERE NOT EXISTS (
            SELECT 1 FROM section_passage_links p WHERE p.section_id = s.section_id
        )
        GROUP BY COALESCE(s.section_type, '<none>')
        ORDER BY cnt DESC
        """
    ).fetchall()
    report.passageless_sections_by_type = {row["section_type"]: row["cnt"] for row in passageless}

    invalid: list[dict[str, Any]] = []
    for row in connection.execute(
        "SELECT id, section_id, canonical_passage FROM section_passage_links"
    ):
        try:
            reference = CanonicalReference.parse(row["canonical_passage"])
        except CanonicalReferenceError as exc:
            invalid.append(
                {
                    "id": row["id"],
                    "section_id": row["section_id"],
                    "canonical_passage": row["canonical_passage"],
                    "error": str(exc),
                }
            )
            continue
        if reference.canonical_string() != row["canonical_passage"]:
            invalid.append(
                {
                    "id": row["id"],
                    "section_id": row["section_id"],
                    "canonical_passage": row["canonical_passage"],
                    "error": "round-trip mismatch",
                }
            )
    report.invalid_references = invalid

    report.duplicate_section_ids = [
        row["section_id"]
        for row in connection.execute(
            "SELECT section_id, COUNT(*) AS cnt FROM sections "
            "GROUP BY section_id HAVING COUNT(*) > 1"
        )
    ]
    report.duplicate_chunk_ids = [
        row["chunk_id"]
        for row in connection.execute(
            "SELECT chunk_id, COUNT(*) AS cnt FROM chunks GROUP BY chunk_id HAVING COUNT(*) > 1"
        )
    ]
    report.duplicate_passage_links = [
        {"section_id": row["section_id"], "canonical_passage": row["canonical_passage"], "count": row["cnt"]}
        for row in connection.execute(
            """
            SELECT section_id, canonical_passage, COUNT(*) AS cnt
            FROM section_passage_links
            GROUP BY section_id, canonical_passage
            HAVING COUNT(*) > 1
            """
        )
    ]

    report.cross_edition_hierarchy_issues = [
        {
            "section_id": row["section_id"],
            "edition_id": row["edition_id"],
            "parent_section_id": row["parent_section_id"],
            "parent_edition_id": row["parent_edition_id"],
        }
        for row in connection.execute(
            """
            SELECT s.section_id AS section_id, s.edition_id AS edition_id,
                   s.parent_section_id AS parent_section_id, p.edition_id AS parent_edition_id
            FROM sections s
            JOIN sections p ON p.section_id = s.parent_section_id
            WHERE s.edition_id != p.edition_id
            """
        )
    ]

    report.coverage_by_book = {
        row["book_id"]: row["cnt"]
        for row in connection.execute(
            """
            SELECT book_id, COUNT(DISTINCT canonical_passage) AS cnt
            FROM section_passage_links
            GROUP BY book_id
            ORDER BY cnt DESC
            """
        )
    }

    warnings: list[str] = []
    if report.orphan_sections:
        warnings.append(f"{len(report.orphan_sections)} orphan section(s) found.")
    if report.invalid_references:
        warnings.append(f"{len(report.invalid_references)} invalid passage reference(s) found.")
    if report.duplicate_section_ids or report.duplicate_chunk_ids:
        warnings.append("Duplicate primary key(s) found (should be impossible under the schema).")
    if report.duplicate_passage_links:
        warnings.append("Duplicate section passage link(s) found (UNIQUE constraint bypassed?).")
    if report.cross_edition_hierarchy_issues:
        warnings.append("Cross-edition parent/child section(s) found.")
    report.warnings = warnings

    return report


def format_qa_report_human(report: CommentaryCorpusQAReport) -> str:
    if not report.available:
        return f"Commentary store not available: {report.database_path}"

    lines = [
        f"Commentary corpus QA — {report.database_path}",
        f"  schema_version={report.schema_version}  content_hash={report.content_hash[:12]}…",
        "",
        f"Works ({len(report.works)}):",
    ]
    for work in report.works:
        lines.append(f"  - {work['work_id']}: {work['title']!r} ({work['edition_count']} edition(s))")
    lines.append("")
    lines.append(f"Source files ({len(report.source_files)}):")
    for src in report.source_files:
        lines.append(f"  - {src['file_name']}  sha256={src['raw_sha256'][:16]}…  {src['byte_size']} bytes")
    lines.append("")
    lines.append(
        f"Sections: {report.section_count}   Chunks: {report.chunk_count}   "
        f"Passage links: {report.passage_link_count} "
        f"(exact-verse: {report.exact_verse_link_count}, range: {report.range_link_count})"
    )
    lines.append(f"Multi-passage sections: {len(report.multi_passage_sections)}")
    lines.append("Passage-less sections by type:")
    for section_type, count in sorted(report.passageless_sections_by_type.items()):
        lines.append(f"  - {section_type}: {count}")
    lines.append("")
    lines.append("Coverage by book (distinct passages linked):")
    for book_id, count in sorted(report.coverage_by_book.items(), key=lambda kv: -kv[1]):
        lines.append(f"  - {book_id}: {count}")
    lines.append("")
    if report.warnings:
        lines.append("WARNINGS:")
        for warning in report.warnings:
            lines.append(f"  ! {warning}")
    else:
        lines.append("No integrity issues found (orphans, invalid refs, duplicates, cross-edition hierarchy).")
    return "\n".join(lines)


def _scalar(connection: sqlite3.Connection, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    return int(row[0]) if row else 0


__all__ = [
    "CommentaryCorpusQAReport",
    "format_qa_report_human",
    "generate_commentary_corpus_qa",
]
