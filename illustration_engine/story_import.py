"""Generic idempotent import glue, shared by every source-specific
book parser regardless of where the raw text originally came from.

This was `pg_story_import.py` until Phase 2N (Hebrew Tales) needed the
exact same idempotent-insert/checksum/import_meta logic for a
Wikisource-sourced book. Inspecting that module's actual body showed it
never touched PG boilerplate at all — it only orchestrates
`(canonical_key, external_ref, title_original, original_text)` tuples
produced by a caller-supplied `parse_fn` — so calling it "PG import"
for a non-PG source would have been a real mislabeling, not just a
cosmetic one. The logic is proven identical across 6 real PG sources
AND the new Wikisource source, which is the concrete-duplication bar
this project requires before generalizing.

`pg_story_import.py` now re-exports `StoryImportReport`/
`import_story_collection` under its original PG-era names
(`PgImportReport`/`import_pg_book`) so none of the existing PG
importers needed to change; new non-PG importers (e.g.
`hebrew_tales_importer.py`) should import from THIS module instead,
under the correctly-named symbols.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable, Protocol

from illustration_engine.illustration_sqlite import insert_source, insert_story, set_import_meta
from illustration_engine.source_registry import SourceRecord, load_source_registry


class ParsedStoryLike(Protocol):
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


@dataclass(frozen=True)
class StoryImportReport:
    source_code: str
    source_id: int
    parsed_count: int
    inserted_count: int
    skipped_existing_count: int
    raw_file_sha256: str


def import_story_collection(
    connection: sqlite3.Connection,
    *,
    source_code: str,
    raw_text_path: str | Path,
    parse_fn: Callable[[Path], Iterable[ParsedStoryLike]],
    registry_path: str | Path | None = None,
) -> StoryImportReport:
    """Import one source's row and its stories idempotently.

    `source_code` must match a `code` in the source registry
    (`sources.json`); that record's license/bibliographic metadata is
    used verbatim to create the `sources` row. Every story is inserted
    as `status="draft"` with no Hungarian layer — that is a later,
    separate AI-enrichment phase's job, not this importer's. Format-
    agnostic: `raw_text_path` may be a Project Gutenberg plain-text
    file, a Wikisource-derived plain-text file, or any future raw
    source — this function never inspects the raw text itself, only
    `parse_fn`'s output.
    """
    record = _find_source_record(source_code, registry_path)
    source_id = _ensure_source(connection, record)

    raw_text_path = Path(raw_text_path)
    raw_sha256 = hashlib.sha256(raw_text_path.read_bytes()).hexdigest()

    parsed_stories = list(parse_fn(raw_text_path))

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
            f"{source_code}.raw_file_sha256": raw_sha256,
            f"{source_code}.raw_file_name": raw_text_path.name,
            f"{source_code}.parsed_story_count": str(len(parsed_stories)),
            f"{source_code}.imported_at": imported_at,
        },
    )

    return StoryImportReport(
        source_code=source_code,
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
        tradition=record.tradition,
    )


def _story_exists(connection: sqlite3.Connection, source_id: int, canonical_key: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM stories WHERE source_id = ? AND canonical_key = ?",
        (source_id, canonical_key),
    ).fetchone()
    return row is not None


__all__ = ["ParsedStoryLike", "StoryImportReport", "import_story_collection"]
