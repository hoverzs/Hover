"""Read/write repository API for `illustration_units` (schema v3,
Phase 3A) — the layer a future controlled enrichment pilot (and,
eventually, `app.py`-side retrieval — NOT wired up here) is meant to
call, instead of every caller hand-rolling its own SQL against
`illustration_sqlite.py`'s low-level primitives.

Nothing here calls an LLM, generates Hungarian text, or writes to any
`stories` provenance field — this module only moves already-produced
enrichment field values into/through the schema v3 gates. Every
transition function relies on the two independent DB-layer gates
(content-completeness CHECK + license trigger for `published`, the
human-review-protection trigger for content updates) to actually be
fail-closed; the Python-side checks here exist for clearer error
messages and cheaper pre-flight validation, not as the sole guarantee.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from illustration_engine.illustration_sqlite import (
    insert_illustration_unit,
    update_illustration_unit_fields,
)


@dataclass(frozen=True)
class IllustrationUnitView:
    id: int
    story_id: int
    unit_index: int
    derivation_type: str
    source_span_start: int | None
    source_span_end: int | None
    title_hu: str | None
    modern_hu_text: str | None
    summary_hu: str | None
    moral_hu: str | None
    narrative_status: str | None
    narrative_status_confidence: str | None
    status: str
    enrichment_model: str | None
    enrichment_prompt_version: str | None
    enrichment_generated_at: str | None
    human_reviewed_at: str | None
    created_at: str
    updated_at: str


_UNIT_COLUMNS = (
    "id",
    "story_id",
    "unit_index",
    "derivation_type",
    "source_span_start",
    "source_span_end",
    "title_hu",
    "modern_hu_text",
    "summary_hu",
    "moral_hu",
    "narrative_status",
    "narrative_status_confidence",
    "status",
    "enrichment_model",
    "enrichment_prompt_version",
    "enrichment_generated_at",
    "human_reviewed_at",
    "created_at",
    "updated_at",
)


def _row_to_view(row: tuple) -> IllustrationUnitView:
    return IllustrationUnitView(**dict(zip(_UNIT_COLUMNS, row)))


def create_draft_unit(
    connection: sqlite3.Connection,
    *,
    story_id: int,
    unit_index: int,
    derivation_type: str,
    source_span_start: int | None = None,
    source_span_end: int | None = None,
) -> int:
    """Creates an empty draft unit — a placeholder the enrichment
    pipeline then fills in via `update_draft_unit`. Never sets any
    content field itself (no field defaults to anything but NULL)."""
    return insert_illustration_unit(
        connection,
        story_id=story_id,
        unit_index=unit_index,
        derivation_type=derivation_type,
        source_span_start=source_span_start,
        source_span_end=source_span_end,
        status="draft",
    )


def update_draft_unit(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    title_hu: str | None = None,
    modern_hu_text: str | None = None,
    summary_hu: str | None = None,
    moral_hu: str | None = None,
    narrative_status: str | None = None,
    narrative_status_confidence: str | None = None,
    enrichment_model: str | None = None,
    enrichment_prompt_version: str | None = None,
    enrichment_generated_at: str | None = None,
    allow_overwrite_reviewed: bool = False,
) -> None:
    """Writes enrichment output onto an existing unit. Refuses (via
    `update_illustration_unit_fields`'s guard) to silently overwrite a
    unit that already has `human_reviewed_at` set, unless
    `allow_overwrite_reviewed=True` — this is the enforcement point an
    AI re-run pipeline must go through; it cannot accidentally clobber
    approved content by simply calling this function again. Passing
    `allow_overwrite_reviewed=True` on an already-reviewed unit demotes
    it: `human_reviewed_at` is cleared and `status` is forced back to
    `needs_review` in the same write, so it immediately drops out of
    `published_illustration_units`/`search_units()` results — a fresh
    `approve_unit()`/`publish_unit()` pass is required to make it
    retrieval-ready again."""
    fields = {
        name: value
        for name, value in (
            ("title_hu", title_hu),
            ("modern_hu_text", modern_hu_text),
            ("summary_hu", summary_hu),
            ("moral_hu", moral_hu),
            ("narrative_status", narrative_status),
            ("narrative_status_confidence", narrative_status_confidence),
            ("enrichment_model", enrichment_model),
            ("enrichment_prompt_version", enrichment_prompt_version),
            ("enrichment_generated_at", enrichment_generated_at),
        )
        if value is not None
    }
    if not fields:
        return
    update_illustration_unit_fields(
        connection,
        unit_id=unit_id,
        allow_overwrite_reviewed=allow_overwrite_reviewed,
        **fields,
    )


def list_units_for_story(connection: sqlite3.Connection, story_id: int) -> list[IllustrationUnitView]:
    rows = connection.execute(
        f"SELECT {', '.join(_UNIT_COLUMNS)} FROM illustration_units "
        "WHERE story_id = ? ORDER BY unit_index",
        (story_id,),
    ).fetchall()
    return [_row_to_view(row) for row in rows]


def get_unit(connection: sqlite3.Connection, unit_id: int) -> IllustrationUnitView | None:
    row = connection.execute(
        f"SELECT {', '.join(_UNIT_COLUMNS)} FROM illustration_units WHERE id = ?",
        (unit_id,),
    ).fetchone()
    return _row_to_view(row) if row else None


def mark_needs_review(connection: sqlite3.Connection, unit_id: int) -> None:
    update_illustration_unit_fields(connection, unit_id=unit_id, status="needs_review")


def approve_unit(
    connection: sqlite3.Connection, unit_id: int, *, human_reviewed_at: str | None = None
) -> None:
    """Moves a unit to `approved` and stamps `human_reviewed_at` (the
    Phase 3A brief's review-provenance signal — distinct from the
    workflow `status`). `approved` does NOT require content-
    completeness by itself (same precedent as `stories`: only
    `published` is gated on it) — but stamping the review timestamp
    here is what makes the human-review-protection trigger start
    guarding this unit's content from here on."""
    update_illustration_unit_fields(
        connection,
        unit_id=unit_id,
        status="approved",
        human_reviewed_at=human_reviewed_at or datetime.now(UTC).isoformat(),
    )


def validate_publish_ready(connection: sqlite3.Connection, unit_id: int) -> tuple[bool, list[str]]:
    """Pure pre-check (no mutation) mirroring the DB-level publish
    gates, for pilot/UI tooling that wants a reason list before
    attempting the real transition (which the DB enforces regardless)."""
    unit = get_unit(connection, unit_id)
    if unit is None:
        return False, [f"illustration unit not found: id={unit_id}"]

    reasons: list[str] = []
    if unit.title_hu is None:
        reasons.append("title_hu is missing")
    if unit.modern_hu_text is None:
        reasons.append("modern_hu_text is missing")
    if unit.summary_hu is None:
        reasons.append("summary_hu is missing")
    if unit.human_reviewed_at is None:
        reasons.append("human_reviewed_at is missing (no human review recorded)")

    license_row = connection.execute(
        """
        SELECT s.license_status FROM stories st JOIN sources s ON s.id = st.source_id
        WHERE st.id = ?
        """,
        (unit.story_id,),
    ).fetchone()
    if license_row is None or license_row[0] not in ("public_domain_confirmed", "permission_granted"):
        reasons.append(
            f"source license_status {license_row[0] if license_row else None!r} does not "
            "permit publishing"
        )

    return (not reasons), reasons


def publish_unit(connection: sqlite3.Connection, unit_id: int) -> None:
    """Transitions a unit to `published`. Relies on the DB-level
    content-completeness CHECK and `trg_units_publish_requires_license_*`
    trigger as the actual fail-closed gate — this call raises
    `sqlite3.IntegrityError` (not a custom exception) if either is
    violated, exactly like every other publish-gated write in this
    schema. Call `validate_publish_ready` first for a friendlier reason
    list."""
    update_illustration_unit_fields(connection, unit_id=unit_id, status="published")


def get_or_create_tag(
    connection: sqlite3.Connection, *, category: str, slug: str, label_hu: str
) -> int:
    row = connection.execute(
        "SELECT id FROM tags WHERE category = ? AND slug = ?", (category, slug)
    ).fetchone()
    if row is not None:
        return int(row[0])
    cursor = connection.execute(
        "INSERT INTO tags(category, slug, label_hu) VALUES (?, ?, ?)",
        (category, slug, label_hu),
    )
    return int(cursor.lastrowid)


def attach_tag_to_unit(connection: sqlite3.Connection, *, unit_id: int, tag_id: int) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO illustration_unit_tags(unit_id, tag_id) VALUES (?, ?)",
        (unit_id, tag_id),
    )


def detach_tag_from_unit(connection: sqlite3.Connection, *, unit_id: int, tag_id: int) -> None:
    """Symmetric counterpart to `attach_tag_to_unit` — used by callers
    (e.g. the enrichment pipeline's tag-sync step) that need to REPLACE
    a unit's tag set rather than only ever add to it."""
    connection.execute(
        "DELETE FROM illustration_unit_tags WHERE unit_id = ? AND tag_id = ?",
        (unit_id, tag_id),
    )


def search_units(
    connection: sqlite3.Connection, query_text: str, *, limit: int = 20
) -> list[IllustrationUnitView]:
    """Full-text search restricted to retrieval-ready units: published
    AND the parent story's source license publishable — enforced by
    joining the FTS5 match back to `published_illustration_units`, not
    by trusting the FTS index's own contents (which includes drafts —
    see the schema module docstring for why)."""
    rows = connection.execute(
        f"""
        SELECT {', '.join('u.' + c for c in _UNIT_COLUMNS)}
        FROM illustration_units_fts fts
        JOIN illustration_units u ON u.id = fts.rowid
        JOIN published_illustration_units p ON p.id = u.id
        WHERE illustration_units_fts MATCH ?
        ORDER BY bm25(illustration_units_fts)
        LIMIT ?
        """,
        (query_text, limit),
    ).fetchall()
    return [_row_to_view(row) for row in rows]


__all__ = [
    "IllustrationUnitView",
    "approve_unit",
    "attach_tag_to_unit",
    "create_draft_unit",
    "detach_tag_from_unit",
    "get_or_create_tag",
    "get_unit",
    "list_units_for_story",
    "mark_needs_review",
    "publish_unit",
    "search_units",
    "update_draft_unit",
    "validate_publish_ready",
]
