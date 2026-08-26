"""Idempotent import glue: source_registry + jataka_parser -> illustration_sqlite.

Deterministic and safely re-runnable: re-running against the same
database neither duplicates rows nor errors — an existing `sources` row
(matched by `code`) or `stories` row (matched by `source_id` +
`canonical_key`) is left untouched and simply skipped.

Every imported story stays in `status="draft"` with `title_hu` /
`modern_hu_text` / `summary_hu` left NULL — the Hungarian layer is a
later, separate AI-enrichment phase (see module docstrings in
`illustration_sqlite.py`). Only the source-language title, the
unmodified source text, and solid bibliographic metadata are written
here.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from illustration_engine.illustration_sqlite import insert_source, insert_story, set_import_meta
from illustration_engine.jataka_parser import JatakaBookSpec, parse_jataka_file
from illustration_engine.source_registry import SourceRecord, load_source_registry


@dataclass(frozen=True)
class JatakaImportReport:
    source_code: str
    source_id: int
    parsed_count: int
    inserted_count: int
    skipped_existing_count: int
    raw_file_sha256: str


def import_jataka_book(
    connection: sqlite3.Connection,
    *,
    spec: JatakaBookSpec,
    raw_text_path: str | Path,
    registry_path: str | Path | None = None,
) -> JatakaImportReport:
    """Import one Jataka book (source row + its stories) idempotently.

    `spec.source_code` must match a `code` in the source registry
    (`sources.json`); that record's license/bibliographic metadata is used
    verbatim to create the `sources` row (fail-closed: an unpublishable
    `license_status` there would already have blocked any later
    `status="published"` transition — see `insert_story`'s license gate —
    but this importer never sets a non-draft status in the first place).
    """
    record = _find_source_record(spec.source_code, registry_path)
    source_id = _ensure_source(connection, record)

    raw_text_path = Path(raw_text_path)
    raw_bytes = raw_text_path.read_bytes()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    parsed_stories = parse_jataka_file(raw_text_path, spec)

    inserted = 0
    skipped = 0
    for story in parsed_stories:
        if _story_exists(connection, source_id, story.canonical_key):
            skipped += 1
            continue
        insert_story(
            connection,
            source_id=source_id,
            external_ref=story.external_ref,
            canonical_key=story.canonical_key,
            title_original=story.title_original,
            adaptation_status="verbatim_transcription",
            status="draft",
            original_text=story.original_text,
            original_text_checksum=hashlib.sha256(story.original_text.encode("utf-8")).hexdigest(),
        )
        inserted += 1

    imported_at = datetime.now(UTC).isoformat()
    set_import_meta(
        connection,
        {
            f"{spec.source_code}.raw_file_sha256": raw_sha256,
            f"{spec.source_code}.raw_file_name": raw_text_path.name,
            f"{spec.source_code}.parsed_story_count": str(len(parsed_stories)),
            f"{spec.source_code}.imported_at": imported_at,
        },
    )

    return JatakaImportReport(
        source_code=spec.source_code,
        source_id=source_id,
        parsed_count=len(parsed_stories),
        inserted_count=inserted,
        skipped_existing_count=skipped,
        raw_file_sha256=raw_sha256,
    )


def _find_source_record(code: str, registry_path: str | Path | None) -> SourceRecord:
    records = load_source_registry(registry_path)
    for record in records:
        if record.code == code:
            return record
    raise ValueError(f"No source registry entry found for code={code!r}")


def _ensure_source(connection: sqlite3.Connection, record: SourceRecord) -> int:
    row = connection.execute(
        "SELECT id FROM sources WHERE code = ?", (record.code,)
    ).fetchone()
    if row is not None:
        return int(row[0])
    return insert_source(
        connection,
        code=record.code,
        title=record.title,
        author=record.author,
        orig_language=record.orig_language,
        publication_year=record.publication_year,
        edition_reference=record.edition_reference,
        license_status=record.license_status,
        license_basis_hu=record.license_basis_hu,
        rights_holder=record.rights_holder,
        source_url=record.source_url,
        retrieved_at=record.retrieved_at,
        reliability_tier=record.reliability_tier,
        notes_hu=record.notes_hu,
    )


def _story_exists(connection: sqlite3.Connection, source_id: int, canonical_key: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM stories WHERE source_id = ? AND canonical_key = ?",
        (source_id, canonical_key),
    ).fetchone()
    return row is not None


__all__ = ["JatakaImportReport", "import_jataka_book"]
