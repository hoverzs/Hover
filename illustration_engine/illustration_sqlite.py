"""Build-time SQLite layer for the illustration/story database.

Mirrors `bible_engine/hymn_sqlite.py`: this module owns schema creation
and *writes*; a later, separate read-only repository module will own
*reads*. Nothing here is imported by `app.py` or by any existing
`bible_engine`/hymn module, and nothing here imports them except the
stable, read-only `illustration_engine.paths` constants.

FAIL-CLOSED LICENSE GATE (defense in depth, two independent layers):

1. Python layer — `insert_story(..., status="published")` looks up the
   story's source `license_status` in the SAME transaction and refuses
   (raises `IllustrationLicenseGateError`) unless it is in
   `PUBLISHABLE_LICENSE_STATUSES`. This is the layer normal callers hit.
2. SQL layer — `trg_stories_publish_requires_license_*` triggers enforce
   the identical rule directly in SQLite via `RAISE(ABORT, ...)`, on both
   INSERT and UPDATE. This protects against any future caller that writes
   raw SQL and bypasses the Python helper entirely. The trigger body is
   generated from `PUBLISHABLE_LICENSE_STATUSES` (see `_publishable_sql_list`)
   so the two layers cannot silently drift apart.

A third, read-side layer (the `published_stories` VIEW) additionally
guarantees that even a row that somehow ends up with `status='published'`
against a non-publishable source is never returned by anything reading
through the view.

ILLUSTRATION UNITS (schema v3, Phase 3A; v4, Phase 3C-c): `stories` stays the immutable,
verbatim, forráshű provenance layer — enrichment NEVER writes to
`original_text`, `title_original`, `original_text_checksum`, or
`source_reference`. `illustration_units` is the new primary retrieval
object: 1 story -> 0..N units (a Phase 2O finding — a 200-1500-char
story is typically one unit, a 3000+-char story may yield several short
extracted-scene units, and most stories yield none until enrichment
actually runs). The exact same two independent gates that protect
`stories.status='published'` are mirrored here:
1. Content-completeness (same-row CHECK): `title_hu`, `modern_hu_text`,
   `summary_hu` must be non-NULL before `status='published'`.
2. License (trigger, via `story_id` -> `stories.source_id` ->
   `sources.license_status`): identical two-layer (Python +
   `trg_units_publish_requires_license_*` trigger) pattern as `stories`.
A THIRD gate is new here: `trg_units_protect_human_reviewed_content`
stops any UPDATE from silently changing a unit's content fields
(`title_hu`, `modern_hu_text`, `summary_hu`, `moral_hu`,
`narrative_status`) once `human_reviewed_at` is set, UNLESS that same
UPDATE both clears `human_reviewed_at` to NULL AND resets `status` to
'needs_review' — clearing the timestamp alone is deliberately not
enough, since a row that stayed `approved`/`published` while losing its
review stamp would be worse than not protecting it at all. This is what
makes "an AI re-run can never silently overwrite human-approved
content, nor leave a demoted unit looking still-approved" an enforced
DB guarantee, not just an API convention. A FOURTH condition —
`human_reviewed_at IS NOT NULL` — was added to the `published`
content-completeness CHECK itself, so `status='published'` is
impossible (INSERT or UPDATE, Python helper or raw SQL) without an
actual human review having happened.

Schema v4 adds `enrichment_warnings_json` (nullable TEXT, a JSON string
array) — non-fatal hallucination-guard findings from the enrichment
pipeline's two-tier guard (see `illustration_engine.enrichment_pipeline`'s
module docstring), kept alongside `enrichment_model`/
`enrichment_prompt_version`/`enrichment_generated_at` as pure audit/
provenance data. Not reviewable "content" a human directly edits, but
still PROTECTED (along with the other three enrichment_* columns) by
`trg_units_protect_human_reviewed_content`'s WHEN clause below and by
`_UNIT_CONTENT_FIELDS` — a human who reviewed a unit reviewed it as
attributed to one specific enrichment run, so silently rewriting which
run (or its warnings) produced already-approved content would corrupt
that provenance just as surely as silently rewriting title_hu.
`approve_unit()`/`publish_unit()` never reference these columns, so
normal review/publish leaves them untouched regardless.

CONTENT-COMPLETENESS GATE (schema v2, independent of the license gate):

`title_hu`, `modern_hu_text`, and `summary_hu` are the Hungarian layer,
authored in a later, separate AI-enrichment phase — a source-language
import (e.g. an English Jataka tale) legitimately has none of them yet.
They are therefore nullable, but a table-level CHECK constraint enforces
that a story can only become `status='published'` once all three are
filled in: `status = 'published'` requires `title_hu`, `modern_hu_text`,
and `summary_hu` to be non-NULL. Intermediate editorial workflow states
(`needs_review`, `approved`) are deliberately NOT gated on this — the DB
guarantees fail-closed *publishability*, not a fully-populated editorial
workflow at every intermediate step. This is a same-row CHECK (no
cross-table trigger needed) and applies to every writer, Python or raw
SQL alike. `title_original` (the source-language title, always known at
import time) and `original_text` remain the only required content
fields for a freshly-imported, still-`draft` story.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from illustration_engine.paths import GENERATED_DATA_DIR
from illustration_engine.source_registry import PUBLISHABLE_LICENSE_STATUSES


DATABASE_NAME = "illustrations.sqlite3"
DEFAULT_DATABASE_PATH = GENERATED_DATA_DIR / DATABASE_NAME
SCHEMA_VERSION = 6

ALLOWED_STORY_STATUSES = frozenset({"draft", "needs_review", "approved", "published"})
ALLOWED_ADAPTATION_STATUSES = frozenset(
    {"verbatim_transcription", "modernized_spelling", "editorial_paraphrase"}
)

# Phase 3A: illustration_units share the stories workflow vocabulary
# (draft -> needs_review -> approved -> published) — a separate, equal-by-
# value constant because the two tables are conceptually distinct, not
# because the allowed values differ.
ALLOWED_UNIT_STATUSES = frozenset({"draft", "needs_review", "approved", "published"})

# How a unit's text relates to its parent story's original_text — decides
# whether source_span_start/end are expected (see the CHECK constraint on
# illustration_units below).
ALLOWED_DERIVATION_TYPES = frozenset(
    {"full_story_translation", "condensed_story", "extracted_scene"}
)

# Controlled vocabulary from the Phase 2O enrichment-readiness audit —
# deliberately does NOT assert historical accuracy just because a real
# person is named (the Phase 2H Baldwin finding this vocabulary exists to
# capture).
ALLOWED_NARRATIVE_STATUSES = frozenset(
    {
        "documented_historical_event",
        "legend_about_historical_figure",
        "traditional_anecdote",
        "fable",
        "folktale",
        "rabbinic_aggadic_tale",
        "didactic_tale",
    }
)
ALLOWED_NARRATIVE_STATUS_CONFIDENCE = frozenset({"low", "medium", "high"})

# Phase 3H: machine QA verdict states, per-unit. Deliberately separate
# from ALLOWED_UNIT_STATUSES/human review lifecycle -- see
# update_unit_machine_qa()'s docstring for why these two state machines
# must never be conflated. 'pending' means "no machine QA run has
# recorded a verdict yet" -- both a fresh row (qa_status IS NULL) and an
# explicit 'pending' value read as "not yet checked" to callers.
ALLOWED_QA_STATUSES = frozenset({"pending", "passed", "needs_attention", "failed"})

REQUIRED_TABLES = frozenset(
    {
        "sources",
        "stories",
        "tags",
        "story_tags",
        "illustration_units",
        "illustration_unit_tags",
        "import_meta",
        "enrichment_runs",
        "enrichment_run_items",
        "qa_repairs",
    }
)
REQUIRED_VIEWS = frozenset({"published_stories", "published_illustration_units"})

# Phase 3F: production batch control plane -- pure run-audit ledger,
# never a duplicate of illustration_units' content/provenance. See
# create_schema()'s enrichment_runs/enrichment_run_items block and
# illustration_engine/enrichment_batch.py (the orchestration layer that
# actually reads/writes these tables; this module only owns their schema
# and raw CRUD, same split as every other table here).
ALLOWED_RUN_STATUSES = frozenset(
    {"created", "running", "completed", "completed_with_errors", "interrupted"}
)
ALLOWED_RUN_ITEM_STATUSES = frozenset(
    {"pending", "running", "success", "warning", "rejected", "proposal_ready", "failed"}
)
ALLOWED_STRATEGY_BANDS = frozenset({"A", "B", "C"})

# Phase 3B pilot taxonomy (user-approved, 2026-08-26; relocated here in
# Phase 3G-A). Small and closed on purpose — a caller selects FROM
# these, it never invents a new slug. category -> slug maps directly
# onto the existing tags.category CHECK ('topic', 'tone', 'function')
# above. Lives here, not in enrichment_pipeline.py, specifically so
# BOTH enrichment_pipeline.py (LLM-side tag selection) AND
# illustration_unit_repository.py (human-reviewer tag replacement, see
# replace_review_tags) can import the SAME controlled vocabulary without
# either module importing the other — enrichment_pipeline.py already
# imports repository functions, so the reverse direction would be a
# circular import. enrichment_pipeline.py re-exports these three names
# from here for backward compatibility with existing callers/tests.
PILOT_TOPICS: frozenset[str] = frozenset(
    {
        "alazat",
        "buszkeseg",
        "becsuletesseg",
        "bolcsesseg",
        "eszesseg",
        "igazsagossag",
        "irgalom",
        "kapzsisag",
        "turelem",
        "tekintely_es_hatalom",
    }
)
PILOT_TONES: frozenset[str] = frozenset(
    {"humoros", "ironikus", "komoly", "megindito", "elgondolkodtato"}
)
PILOT_HOMILETIC_FUNCTIONS: frozenset[str] = frozenset(
    {
        "bevezeto_illusztracio",
        "szemlelteto_pelda",
        "ellenpelda",
        "alkalmazasi_pelda",
        "lezaro_illusztracio",
    }
)

_publishable_sql_list = ", ".join(f"'{s}'" for s in sorted(PUBLISHABLE_LICENSE_STATUSES))
_license_status_sql_list = ", ".join(
    f"'{s}'"
    for s in sorted(
        {
            "public_domain_confirmed",
            "public_domain_assumed_by_age",
            "permission_granted",
            "unknown",
            "restricted",
        }
    )
)


class IllustrationLicenseGateError(ValueError):
    """A story nem kaphat 'published' állapotot a forrása jogállása miatt."""


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    return Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            author TEXT,
            orig_language TEXT NOT NULL,
            publication_year INTEGER,
            edition_reference TEXT,
            license_status TEXT NOT NULL CHECK (
                license_status IN ({_license_status_sql_list})
            ),
            license_basis_hu TEXT NOT NULL,
            rights_holder TEXT,
            source_url TEXT,
            retrieved_at TEXT,
            reliability_tier TEXT NOT NULL,
            notes_hu TEXT,
            tradition TEXT,
            registered_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES sources(id),
            external_ref TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            title_original TEXT NOT NULL,
            title_hu TEXT,
            original_text TEXT,
            original_text_checksum TEXT,
            source_reference TEXT,
            adaptation_status TEXT NOT NULL CHECK (
                adaptation_status IN (
                    'verbatim_transcription', 'modernized_spelling', 'editorial_paraphrase'
                )
            ),
            modern_hu_text TEXT,
            summary_hu TEXT,
            moral_hu TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'needs_review', 'approved', 'published')
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, canonical_key),
            CHECK (
                status != 'published'
                OR (title_hu IS NOT NULL AND modern_hu_text IS NOT NULL AND summary_hu IS NOT NULL)
            )
        );

        -- Phase 3A: the primary user-facing retrieval object. 1 story ->
        -- 0..N units (see module docstring). NEVER writes back to its
        -- parent story's provenance fields.
        CREATE TABLE IF NOT EXISTS illustration_units (
            id INTEGER PRIMARY KEY,
            story_id INTEGER NOT NULL REFERENCES stories(id),
            unit_index INTEGER NOT NULL,
            derivation_type TEXT NOT NULL CHECK (
                derivation_type IN ('full_story_translation', 'condensed_story', 'extracted_scene')
            ),
            source_span_start INTEGER,
            source_span_end INTEGER,
            title_hu TEXT,
            modern_hu_text TEXT,
            summary_hu TEXT,
            moral_hu TEXT,
            narrative_status TEXT CHECK (
                narrative_status IS NULL OR narrative_status IN (
                    'documented_historical_event', 'legend_about_historical_figure',
                    'traditional_anecdote', 'fable', 'folktale', 'rabbinic_aggadic_tale',
                    'didactic_tale'
                )
            ),
            narrative_status_confidence TEXT CHECK (
                narrative_status_confidence IS NULL
                OR narrative_status_confidence IN ('low', 'medium', 'high')
            ),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'needs_review', 'approved', 'published')
            ),
            enrichment_model TEXT,
            enrichment_prompt_version TEXT,
            enrichment_generated_at TEXT,
            -- Schema v4: deterministically JSON-serialized string array
            -- (e.g. '["capitalized word(s) with no matching source
            -- token...: Isten"]') of non-fatal hallucination-guard
            -- findings from the LAST enrichment run — NULL means that
            -- run produced none. Pure enrichment audit/provenance data,
            -- same class as enrichment_model/_prompt_version/
            -- _generated_at above: not an FTS field, not a controlled
            -- taxonomy, not a human-editable content field, and
            -- deliberately NOT listed in _UNIT_CONTENT_FIELDS or the
            -- trg_units_protect_human_reviewed_content trigger below —
            -- approve_unit()/publish_unit() never touch this column, so
            -- review/publish naturally never clears it either.
            enrichment_warnings_json TEXT,
            -- Phase 3H: machine QA verdict, a THIRD provenance layer next
            -- to enrichment_*/human_reviewed_at -- never conflated with
            -- either. No DB-level CHECK on qa_status (SQLite cannot add a
            -- CHECK via ALTER TABLE ADD COLUMN on an existing database, and
            -- this column set must have an IDENTICAL definition whether it
            -- was created fresh here or added by migrate_schema() to a
            -- pre-existing file -- see migrate_schema()'s own comment).
            -- ALLOWED_QA_STATUSES is enforced in Python by
            -- update_unit_machine_qa(), the sole write path. Deliberately
            -- NOT listed in _UNIT_CONTENT_FIELDS or the human-review
            -- protection trigger below -- machine QA must be re-runnable
            -- on an approved/published unit without disturbing its
            -- reviewed content or demoting it.
            qa_status TEXT,
            qa_model TEXT,
            qa_prompt_version TEXT,
            qa_checked_at TEXT,
            qa_confidence REAL,
            qa_issues_json TEXT,
            human_reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(story_id, unit_index),
            -- Phase 3A follow-up: publishing an illustration unit requires
            -- an actual human review, not just complete content — a
            -- fail-closed requirement this CHECK enforces on every INSERT
            -- and UPDATE regardless of caller (Python helper or raw SQL).
            CHECK (
                status != 'published'
                OR (
                    title_hu IS NOT NULL AND modern_hu_text IS NOT NULL AND summary_hu IS NOT NULL
                    AND human_reviewed_at IS NOT NULL
                )
            ),
            CHECK ((source_span_start IS NULL) = (source_span_end IS NULL)),
            CHECK (source_span_end IS NULL OR source_span_end > source_span_start),
            CHECK (
                derivation_type != 'extracted_scene'
                OR (source_span_start IS NOT NULL AND source_span_end IS NOT NULL)
            ),
            CHECK ((narrative_status IS NULL) = (narrative_status_confidence IS NULL))
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL CHECK (category IN ('topic', 'tone', 'function')),
            slug TEXT NOT NULL,
            label_hu TEXT NOT NULL,
            UNIQUE(category, slug)
        );

        CREATE TABLE IF NOT EXISTS story_tags (
            story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            PRIMARY KEY (story_id, tag_id)
        );

        -- Phase 3A: tags attach to illustration_units, not stories — a
        -- single long story can yield several units with DIFFERENT topics/
        -- tone/function (Phase 3A brief's own stated principle). story_tags
        -- is left in place, defined but intentionally unpopulated for now;
        -- nothing currently writes to it.
        CREATE TABLE IF NOT EXISTS illustration_unit_tags (
            unit_id INTEGER NOT NULL REFERENCES illustration_units(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            PRIMARY KEY (unit_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS import_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stories_source ON stories(source_id);
        CREATE INDEX IF NOT EXISTS idx_story_tags_story ON story_tags(story_id);
        CREATE INDEX IF NOT EXISTS idx_story_tags_tag ON story_tags(tag_id);
        CREATE INDEX IF NOT EXISTS idx_illustration_units_story ON illustration_units(story_id);
        CREATE INDEX IF NOT EXISTS idx_illustration_units_status ON illustration_units(status);
        CREATE INDEX IF NOT EXISTS idx_illustration_unit_tags_unit ON illustration_unit_tags(unit_id);
        CREATE INDEX IF NOT EXISTS idx_illustration_unit_tags_tag ON illustration_unit_tags(tag_id);

        -- Read-side fail-closed gate: only sources with a confirmed/granted
        -- license AND stories explicitly marked 'published' are exposed here.
        -- Every future public repository read must query THIS view, never
        -- the raw `stories`/`sources` tables directly.
        CREATE VIEW IF NOT EXISTS published_stories AS
        SELECT
            st.id,
            st.source_id,
            st.external_ref,
            st.canonical_key,
            st.title_original,
            st.title_hu,
            st.original_text,
            st.original_text_checksum,
            st.adaptation_status,
            st.modern_hu_text,
            st.summary_hu,
            st.moral_hu,
            st.status,
            st.created_at,
            st.updated_at,
            s.code AS source_code,
            s.license_status AS source_license_status,
            s.reliability_tier AS source_reliability_tier
        FROM stories st
        JOIN sources s ON s.id = st.source_id
        WHERE st.status = 'published'
          AND s.license_status IN ({_publishable_sql_list});

        -- SQL-layer fail-closed gate (see module docstring): mirrors the
        -- Python-layer check in insert_story() so raw-SQL writers cannot
        -- bypass it.
        CREATE TRIGGER IF NOT EXISTS trg_stories_publish_requires_license_insert
        BEFORE INSERT ON stories
        WHEN NEW.status = 'published'
        BEGIN
            SELECT RAISE(ABORT, 'license_gate: source license_status does not permit published status')
            WHERE (SELECT license_status FROM sources WHERE id = NEW.source_id)
                  NOT IN ({_publishable_sql_list});
        END;

        CREATE TRIGGER IF NOT EXISTS trg_stories_publish_requires_license_update
        BEFORE UPDATE OF status, source_id ON stories
        WHEN NEW.status = 'published'
        BEGIN
            SELECT RAISE(ABORT, 'license_gate: source license_status does not permit published status')
            WHERE (SELECT license_status FROM sources WHERE id = NEW.source_id)
                  NOT IN ({_publishable_sql_list});
        END;

        -- Phase 3A: read-side fail-closed gate for the new retrieval
        -- object, exactly mirroring published_stories above (same two
        -- conditions: unit itself published, AND its story's source
        -- license publishable). Every future search/retrieval read must
        -- query THIS view (or the FTS index joined back to it), never
        -- raw illustration_units directly.
        CREATE VIEW IF NOT EXISTS published_illustration_units AS
        SELECT
            u.id,
            u.story_id,
            u.unit_index,
            u.derivation_type,
            u.source_span_start,
            u.source_span_end,
            u.title_hu,
            u.modern_hu_text,
            u.summary_hu,
            u.moral_hu,
            u.narrative_status,
            u.narrative_status_confidence,
            u.status,
            u.created_at,
            u.updated_at,
            st.id AS story_id_check,
            st.external_ref AS story_external_ref,
            st.title_original AS story_title_original,
            s.code AS source_code,
            s.license_status AS source_license_status,
            s.reliability_tier AS source_reliability_tier,
            s.tradition AS source_tradition
        FROM illustration_units u
        JOIN stories st ON st.id = u.story_id
        JOIN sources s ON s.id = st.source_id
        WHERE u.status = 'published'
          AND s.license_status IN ({_publishable_sql_list});

        -- SQL-layer license gate for illustration_units — identical
        -- two-layer (Python + trigger) pattern as stories, just one hop
        -- further through story_id -> stories.source_id -> sources.
        CREATE TRIGGER IF NOT EXISTS trg_units_publish_requires_license_insert
        BEFORE INSERT ON illustration_units
        WHEN NEW.status = 'published'
        BEGIN
            SELECT RAISE(ABORT, 'license_gate: source license_status does not permit published status')
            WHERE (
                SELECT s.license_status
                FROM stories st JOIN sources s ON s.id = st.source_id
                WHERE st.id = NEW.story_id
            ) NOT IN ({_publishable_sql_list});
        END;

        CREATE TRIGGER IF NOT EXISTS trg_units_publish_requires_license_update
        BEFORE UPDATE OF status, story_id ON illustration_units
        WHEN NEW.status = 'published'
        BEGIN
            SELECT RAISE(ABORT, 'license_gate: source license_status does not permit published status')
            WHERE (
                SELECT s.license_status
                FROM stories st JOIN sources s ON s.id = st.source_id
                WHERE st.id = NEW.story_id
            ) NOT IN ({_publishable_sql_list});
        END;

        -- Human-review protection gate (Phase 3A brief, tightened per
        -- the follow-up review: "reviewed-content overwrite must
        -- actually demote the unit, not just clear the timestamp";
        -- tightened AGAIN in schema v4/Phase 3C-c to also cover
        -- enrichment PROVENANCE fields, not just visible content — see
        -- below).
        -- Once human_reviewed_at is set, ANY UPDATE that changes a
        -- content field is rejected UNLESS that same UPDATE both (a)
        -- clears human_reviewed_at to NULL AND (b) resets status to
        -- 'needs_review'. Clearing human_reviewed_at alone is NOT
        -- sufficient — a row that stayed 'approved'/'published' while
        -- silently losing its review timestamp would be worse than the
        -- original problem (unreviewed content still marked as ready).
        -- There is no "re-stamp with a new timestamp directly" shortcut
        -- any more: editing reviewed content always drops the unit back
        -- to needs_review, requiring a fresh approve_unit()/publish_unit()
        -- pass through the normal lifecycle.
        --
        -- Schema v4 addition: `enrichment_model`, `enrichment_prompt_
        -- version`, `enrichment_generated_at`, `enrichment_warnings_json`
        -- are also guarded here now — even though they are audit/
        -- provenance data, not human-editable content, a human who
        -- reviewed a unit reviewed it AS ATTRIBUTED TO A SPECIFIC
        -- enrichment run; silently rewriting which run (or its warnings)
        -- produced already-approved content, without demoting the unit
        -- back through review, would corrupt that provenance record just
        -- as surely as silently rewriting title_hu would. This closes a
        -- real gap: before this change, a raw SQL UPDATE that touched
        -- ONLY these columns bypassed the trigger entirely (it only
        -- looked at title_hu/modern_hu_text/summary_hu/moral_hu/
        -- narrative_status), even though update_illustration_unit_fields'
        -- Python-side check (_UNIT_CONTENT_FIELDS) has the SAME gap —
        -- see that function for the matching fix. approve_unit()/
        -- publish_unit() never reference these columns, so normal
        -- review/publish is completely unaffected by this.
        CREATE TRIGGER IF NOT EXISTS trg_units_protect_human_reviewed_content
        BEFORE UPDATE ON illustration_units
        WHEN OLD.human_reviewed_at IS NOT NULL
             AND (
                 NEW.title_hu IS NOT OLD.title_hu
                 OR NEW.modern_hu_text IS NOT OLD.modern_hu_text
                 OR NEW.summary_hu IS NOT OLD.summary_hu
                 OR NEW.moral_hu IS NOT OLD.moral_hu
                 OR NEW.narrative_status IS NOT OLD.narrative_status
                 OR NEW.enrichment_model IS NOT OLD.enrichment_model
                 OR NEW.enrichment_prompt_version IS NOT OLD.enrichment_prompt_version
                 OR NEW.enrichment_generated_at IS NOT OLD.enrichment_generated_at
                 OR NEW.enrichment_warnings_json IS NOT OLD.enrichment_warnings_json
             )
             AND NOT (NEW.human_reviewed_at IS NULL AND NEW.status = 'needs_review')
        BEGIN
            SELECT RAISE(ABORT, 'review_gate: reviewed content/provenance can only change together with human_reviewed_at cleared AND status reset to needs_review');
        END;

        -- Phase 3A FTS5 index over the three retrieval-relevant text
        -- fields, requested by the brief. External-content table: indexes
        -- ALL units regardless of status (simpler, always-in-sync
        -- triggers) — filtering to retrieval-ready (published + license-
        -- publishable) rows happens at query time by joining back to
        -- published_illustration_units, not by excluding rows from the
        -- index itself (a unit's/source's status can change after the
        -- fact; the index must not need to "know" about that).
        CREATE VIRTUAL TABLE IF NOT EXISTS illustration_units_fts USING fts5(
            title_hu, summary_hu, modern_hu_text,
            content='illustration_units', content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS trg_illustration_units_fts_insert
        AFTER INSERT ON illustration_units
        BEGIN
            INSERT INTO illustration_units_fts(rowid, title_hu, summary_hu, modern_hu_text)
            VALUES (new.id, new.title_hu, new.summary_hu, new.modern_hu_text);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_illustration_units_fts_delete
        AFTER DELETE ON illustration_units
        BEGIN
            INSERT INTO illustration_units_fts(illustration_units_fts, rowid, title_hu, summary_hu, modern_hu_text)
            VALUES ('delete', old.id, old.title_hu, old.summary_hu, old.modern_hu_text);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_illustration_units_fts_update
        AFTER UPDATE ON illustration_units
        BEGIN
            INSERT INTO illustration_units_fts(illustration_units_fts, rowid, title_hu, summary_hu, modern_hu_text)
            VALUES ('delete', old.id, old.title_hu, old.summary_hu, old.modern_hu_text);
            INSERT INTO illustration_units_fts(rowid, title_hu, summary_hu, modern_hu_text)
            VALUES (new.id, new.title_hu, new.summary_hu, new.modern_hu_text);
        END;

        -- Phase 3F (schema v5): production batch control plane. Pure run-
        -- audit data -- deliberately does NOT duplicate illustration_units'
        -- content/provenance columns, only references a resulting unit by
        -- id when a direct_unit write actually happened. A run's item list
        -- is fixed at selection time (see enrichment_batch.py) and never
        -- re-queried on resume, so it is the single reproducible record of
        -- "which story_ids this run covers."
        CREATE TABLE IF NOT EXISTS enrichment_runs (
            id INTEGER PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            model_identifier TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            source_code TEXT,
            strategy_band TEXT CHECK (strategy_band IS NULL OR strategy_band IN ('A', 'B', 'C')),
            requested_limit INTEGER,
            overall_status TEXT NOT NULL DEFAULT 'created' CHECK (
                overall_status IN ('created', 'running', 'completed', 'completed_with_errors', 'interrupted')
            ),
            selection_metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS enrichment_run_items (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES enrichment_runs(id),
            story_id INTEGER NOT NULL REFERENCES stories(id),
            expected_mode TEXT NOT NULL CHECK (expected_mode IN ('direct_unit', 'unit_proposal')),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'running', 'success', 'warning', 'rejected', 'proposal_ready', 'failed')
            ),
            illustration_unit_id INTEGER REFERENCES illustration_units(id),
            error_message TEXT,
            warnings_json TEXT,
            started_at TEXT,
            finished_at TEXT,
            UNIQUE(run_id, story_id)
        );

        CREATE INDEX IF NOT EXISTS idx_enrichment_run_items_run ON enrichment_run_items(run_id);
        CREATE INDEX IF NOT EXISTS idx_enrichment_run_items_run_status ON enrichment_run_items(run_id, status);

        -- Phase 3H: auto-repair audit trail. A repair is a bounded,
        -- content-fields-only edit (title_hu/modern_hu_text/summary_hu/
        -- moral_hu) applied by the machine QA/repair orchestrator when a
        -- QA verdict flagged safely-fixable issues -- NEVER original_text,
        -- NEVER source/provenance, NEVER derivation_type. This table is
        -- the "what changed and why" record; illustration_units.qa_* only
        -- holds the LATEST verdict, not history.
        CREATE TABLE IF NOT EXISTS qa_repairs (
            id INTEGER PRIMARY KEY,
            unit_id INTEGER NOT NULL REFERENCES illustration_units(id),
            repaired_at TEXT NOT NULL,
            qa_model TEXT NOT NULL,
            qa_prompt_version TEXT NOT NULL,
            issues_before_json TEXT NOT NULL,
            fields_changed_json TEXT NOT NULL,
            before_values_json TEXT NOT NULL,
            after_values_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_qa_repairs_unit ON qa_repairs(unit_id);
        """
    )
    connection.commit()


def migrate_schema(connection: sqlite3.Connection) -> None:
    """Idempotent, additive-only migration for an EXISTING database file
    (Phase 3H). Safe to call on every startup/batch run:

    1. `create_schema()` first -- adds any missing table/view/trigger/
       index (a no-op for ones that already exist, proven safe/additive
       for the real pilot DB during the Phase 3G-B audit).
    2. Then adds any missing individual COLUMNS on `illustration_units`
       that `CREATE TABLE IF NOT EXISTS` cannot retrofit onto an already-
       existing table (SQLite has no `ALTER TABLE ... ADD COLUMN IF NOT
       EXISTS`, so this checks `PRAGMA table_info` itself and only adds
       what is actually missing).

    NEVER drops, renames, or ALTERs an existing column; NEVER touches
    existing row data. The added column list/types are IDENTICAL to the
    ones in `create_schema()`'s own `illustration_units` definition --
    keep both in sync by hand if either changes."""
    create_schema(connection)
    existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(illustration_units)")}
    qa_columns: dict[str, str] = {
        "qa_status": "TEXT",
        "qa_model": "TEXT",
        "qa_prompt_version": "TEXT",
        "qa_checked_at": "TEXT",
        "qa_confidence": "REAL",
        "qa_issues_json": "TEXT",
    }
    for column_name, sql_type in qa_columns.items():
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE illustration_units ADD COLUMN {column_name} {sql_type}")
    connection.commit()


def check_integrity(connection: sqlite3.Connection) -> str:
    return connection.execute("PRAGMA integrity_check").fetchone()[0]


def insert_source(
    connection: sqlite3.Connection,
    *,
    code: str,
    title: str,
    orig_language: str,
    license_status: str,
    license_basis_hu: str,
    reliability_tier: str,
    author: str | None = None,
    publication_year: int | None = None,
    edition_reference: str | None = None,
    rights_holder: str | None = None,
    source_url: str | None = None,
    retrieved_at: str | None = None,
    notes_hu: str | None = None,
    tradition: str | None = None,
    registered_at: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO sources(
            code, title, author, orig_language, publication_year, edition_reference,
            license_status, license_basis_hu, rights_holder, source_url, retrieved_at,
            reliability_tier, notes_hu, tradition, registered_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            code,
            title,
            author,
            orig_language,
            publication_year,
            edition_reference,
            license_status,
            license_basis_hu,
            rights_holder,
            source_url,
            retrieved_at,
            reliability_tier,
            notes_hu,
            tradition,
            registered_at or datetime.now(UTC).isoformat(),
        ),
    )
    return int(cursor.lastrowid)


def insert_story(
    connection: sqlite3.Connection,
    *,
    source_id: int,
    external_ref: str,
    canonical_key: str,
    title_original: str,
    adaptation_status: str,
    status: str = "draft",
    title_hu: str | None = None,
    modern_hu_text: str | None = None,
    summary_hu: str | None = None,
    original_text: str | None = None,
    original_text_checksum: str | None = None,
    source_reference: str | None = None,
    moral_hu: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> int:
    if adaptation_status not in ALLOWED_ADAPTATION_STATUSES:
        raise ValueError(f"Invalid adaptation_status: {adaptation_status!r}")
    if status not in ALLOWED_STORY_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    for field_name, value in (
        ("external_ref", external_ref),
        ("canonical_key", canonical_key),
        ("title_original", title_original),
    ):
        if not (value or "").strip():
            raise ValueError(f"{field_name} must be non-empty")
    for field_name, value in (
        ("title_hu", title_hu),
        ("modern_hu_text", modern_hu_text),
        ("summary_hu", summary_hu),
    ):
        if value is not None and not value.strip():
            raise ValueError(f"{field_name} must be non-empty when provided")

    if status == "published" and (title_hu is None or modern_hu_text is None or summary_hu is None):
        missing = [
            name
            for name, value in (
                ("title_hu", title_hu),
                ("modern_hu_text", modern_hu_text),
                ("summary_hu", summary_hu),
            )
            if value is None
        ]
        raise ValueError(
            f"status={status!r} requires title_hu, modern_hu_text, and summary_hu "
            f"to be filled in (content-completeness gate) — missing: {missing}"
        )
    if status == "published":
        _assert_source_is_publishable(connection, source_id)

    now = datetime.now(UTC).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO stories(
            source_id, external_ref, canonical_key, title_original, title_hu,
            original_text, original_text_checksum, source_reference, adaptation_status,
            modern_hu_text, summary_hu, moral_hu, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            external_ref,
            canonical_key,
            title_original,
            title_hu,
            original_text,
            original_text_checksum,
            source_reference,
            adaptation_status,
            modern_hu_text,
            summary_hu,
            moral_hu,
            status,
            created_at or now,
            updated_at or now,
        ),
    )
    return int(cursor.lastrowid)


def _assert_source_is_publishable(connection: sqlite3.Connection, source_id: int) -> None:
    row = connection.execute(
        "SELECT license_status FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"source_id not found: {source_id}")
    license_status = row[0]
    if license_status not in PUBLISHABLE_LICENSE_STATUSES:
        raise IllustrationLicenseGateError(
            "Cannot mark story as 'published': source license_status "
            f"{license_status!r} is not in PUBLISHABLE_LICENSE_STATUSES "
            f"({sorted(PUBLISHABLE_LICENSE_STATUSES)})."
        )


class IllustrationUnitReviewProtectionError(ValueError):
    """A write attempted to silently change human-reviewed unit content."""


# Schema v4/Phase 3C-c: extended beyond visible content to also cover the
# enrichment provenance columns (which run/prompt-version produced this
# content, and what it warned about) — see trg_units_protect_human_
# reviewed_content's comment in create_schema() for why these need the
# same protection as title_hu etc., even though a human never edits them
# directly.
_UNIT_CONTENT_FIELDS = (
    "title_hu",
    "modern_hu_text",
    "summary_hu",
    "moral_hu",
    "narrative_status",
    "enrichment_model",
    "enrichment_prompt_version",
    "enrichment_generated_at",
    "enrichment_warnings_json",
)


def insert_illustration_unit(
    connection: sqlite3.Connection,
    *,
    story_id: int,
    unit_index: int,
    derivation_type: str,
    status: str = "draft",
    title_hu: str | None = None,
    modern_hu_text: str | None = None,
    summary_hu: str | None = None,
    moral_hu: str | None = None,
    narrative_status: str | None = None,
    narrative_status_confidence: str | None = None,
    source_span_start: int | None = None,
    source_span_end: int | None = None,
    enrichment_model: str | None = None,
    enrichment_prompt_version: str | None = None,
    enrichment_generated_at: str | None = None,
    enrichment_warnings_json: str | None = None,
    human_reviewed_at: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> int:
    if derivation_type not in ALLOWED_DERIVATION_TYPES:
        raise ValueError(f"Invalid derivation_type: {derivation_type!r}")
    if status not in ALLOWED_UNIT_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    if narrative_status is not None and narrative_status not in ALLOWED_NARRATIVE_STATUSES:
        raise ValueError(f"Invalid narrative_status: {narrative_status!r}")
    if (
        narrative_status_confidence is not None
        and narrative_status_confidence not in ALLOWED_NARRATIVE_STATUS_CONFIDENCE
    ):
        raise ValueError(f"Invalid narrative_status_confidence: {narrative_status_confidence!r}")
    if (narrative_status is None) != (narrative_status_confidence is None):
        raise ValueError(
            "narrative_status and narrative_status_confidence must be both set or both None"
        )
    if (source_span_start is None) != (source_span_end is None):
        raise ValueError("source_span_start and source_span_end must be both set or both None")
    if (
        source_span_start is not None
        and source_span_end is not None
        and source_span_end <= source_span_start
    ):
        raise ValueError("source_span_end must be greater than source_span_start")
    if derivation_type == "extracted_scene" and source_span_start is None:
        raise ValueError("derivation_type='extracted_scene' requires a source span")
    for field_name, value in (
        ("title_hu", title_hu),
        ("modern_hu_text", modern_hu_text),
        ("summary_hu", summary_hu),
    ):
        if value is not None and not value.strip():
            raise ValueError(f"{field_name} must be non-empty when provided")

    if status == "published" and (
        title_hu is None or modern_hu_text is None or summary_hu is None or human_reviewed_at is None
    ):
        missing = [
            name
            for name, value in (
                ("title_hu", title_hu),
                ("modern_hu_text", modern_hu_text),
                ("summary_hu", summary_hu),
                ("human_reviewed_at", human_reviewed_at),
            )
            if value is None
        ]
        raise ValueError(
            f"status={status!r} requires title_hu, modern_hu_text, summary_hu, and "
            f"human_reviewed_at to be filled in (content-completeness + human-review "
            f"gate) — missing: {missing}"
        )
    if status == "published":
        _assert_unit_source_is_publishable(connection, story_id)

    now = datetime.now(UTC).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO illustration_units(
            story_id, unit_index, derivation_type, source_span_start, source_span_end,
            title_hu, modern_hu_text, summary_hu, moral_hu,
            narrative_status, narrative_status_confidence, status,
            enrichment_model, enrichment_prompt_version, enrichment_generated_at,
            enrichment_warnings_json,
            human_reviewed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            story_id,
            unit_index,
            derivation_type,
            source_span_start,
            source_span_end,
            title_hu,
            modern_hu_text,
            summary_hu,
            moral_hu,
            narrative_status,
            narrative_status_confidence,
            status,
            enrichment_model,
            enrichment_prompt_version,
            enrichment_generated_at,
            enrichment_warnings_json,
            human_reviewed_at,
            created_at or now,
            updated_at or now,
        ),
    )
    return int(cursor.lastrowid)


def _assert_unit_source_is_publishable(connection: sqlite3.Connection, story_id: int) -> None:
    row = connection.execute(
        """
        SELECT s.license_status FROM stories st JOIN sources s ON s.id = st.source_id
        WHERE st.id = ?
        """,
        (story_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"story_id not found: {story_id}")
    license_status = row[0]
    if license_status not in PUBLISHABLE_LICENSE_STATUSES:
        raise IllustrationLicenseGateError(
            "Cannot mark illustration unit as 'published': parent story's source "
            f"license_status {license_status!r} is not in PUBLISHABLE_LICENSE_STATUSES "
            f"({sorted(PUBLISHABLE_LICENSE_STATUSES)})."
        )


def update_illustration_unit_fields(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    allow_overwrite_reviewed: bool = False,
    **fields: object,
) -> None:
    """Updates one or more columns on an existing illustration unit.

    Python-layer half of the human-review protection guarantee — the SQL
    trigger `trg_units_protect_human_reviewed_content` is the other,
    fail-closed half (this function existing gives a clearer Python
    exception; the trigger is what makes the guarantee hold even for a
    caller that bypasses this function entirely). Refuses to touch any
    content OR enrichment-provenance field (see `_UNIT_CONTENT_FIELDS`:
    `title_hu`, `modern_hu_text`, `summary_hu`, `moral_hu`,
    `narrative_status`, `enrichment_model`, `enrichment_prompt_version`,
    `enrichment_generated_at`, `enrichment_warnings_json`) on a unit
    whose `human_reviewed_at` is already set, unless
    `allow_overwrite_reviewed=True` is passed explicitly.

    There is no "re-stamp with content in the same call" shortcut: an
    explicit `allow_overwrite_reviewed=True` ALWAYS both clears
    `human_reviewed_at` to NULL and resets `status` to 'needs_review' as
    part of the same write, overriding whatever the caller passed for
    either — this mirrors the SQL trigger's requirement exactly (see its
    definition) and is a deliberate, fail-closed design choice: clearing
    the timestamp alone, while leaving `status='approved'`/`'published'`
    intact, would be worse than not protecting the content at all (an
    unreviewed row still marked as if it were ready). The only way back
    to `approved`/`published` after an override is a fresh
    `approve_unit()`/`publish_unit()` call.

    A `status='published'` transition here still goes through the same
    content-completeness/license/human-review CHECK+trigger gates as
    `insert_illustration_unit` — SQLite raises `IntegrityError` if those
    are violated; this function does not duplicate that pre-check for
    updates, only for inserts.
    """
    if not fields:
        return
    if "status" in fields and fields["status"] not in ALLOWED_UNIT_STATUSES:
        raise ValueError(f"Invalid status: {fields['status']!r}")

    row = connection.execute(
        "SELECT human_reviewed_at FROM illustration_units WHERE id = ?", (unit_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"illustration unit not found: id={unit_id}")
    human_reviewed_at = row[0]

    touches_content = any(name in fields for name in _UNIT_CONTENT_FIELDS)
    if human_reviewed_at is not None and touches_content:
        if not allow_overwrite_reviewed:
            raise IllustrationUnitReviewProtectionError(
                f"illustration unit id={unit_id} was human-reviewed at {human_reviewed_at!r} — "
                "refusing to silently overwrite its content. Pass allow_overwrite_reviewed=True "
                "to demote it to needs_review and proceed."
            )
        # Forcibly demote — see docstring. This overrides any status/
        # human_reviewed_at the caller may have also passed in `fields`.
        fields = {**fields, "human_reviewed_at": None, "status": "needs_review"}

    write_fields = dict(fields)
    write_fields["updated_at"] = write_fields.get("updated_at") or datetime.now(UTC).isoformat()
    set_clause = ", ".join(f"{name} = ?" for name in write_fields)
    connection.execute(
        f"UPDATE illustration_units SET {set_clause} WHERE id = ?",
        (*write_fields.values(), unit_id),
    )


def set_import_meta(connection: sqlite3.Connection, metadata: dict[str, str]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO import_meta(key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )


# ---------------------------------------------------------------------------
# Phase 3F: enrichment_runs / enrichment_run_items raw CRUD. Deliberately
# thin (no business logic, no selection algorithm, no resume/retry policy)
# -- see illustration_engine/enrichment_batch.py for all of that; this is
# only the same kind of low-level insert/update primitive every other
# table in this module already has.
# ---------------------------------------------------------------------------


def insert_enrichment_run(
    connection: sqlite3.Connection,
    *,
    model_identifier: str,
    prompt_version: str,
    source_code: str | None = None,
    strategy_band: str | None = None,
    requested_limit: int | None = None,
    selection_metadata_json: str | None = None,
    overall_status: str = "created",
    started_at: str | None = None,
) -> int:
    if strategy_band is not None and strategy_band not in ALLOWED_STRATEGY_BANDS:
        raise ValueError(f"Invalid strategy_band: {strategy_band!r}")
    if overall_status not in ALLOWED_RUN_STATUSES:
        raise ValueError(f"Invalid overall_status: {overall_status!r}")
    now = datetime.now(UTC).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO enrichment_runs(
            started_at, finished_at, model_identifier, prompt_version, source_code,
            strategy_band, requested_limit, overall_status, selection_metadata_json
        ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            started_at or now,
            model_identifier,
            prompt_version,
            source_code,
            strategy_band,
            requested_limit,
            overall_status,
            selection_metadata_json,
        ),
    )
    return int(cursor.lastrowid)


def update_enrichment_run(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    overall_status: str | None = None,
    finished_at: str | None = None,
) -> None:
    fields: dict[str, object] = {}
    if overall_status is not None:
        if overall_status not in ALLOWED_RUN_STATUSES:
            raise ValueError(f"Invalid overall_status: {overall_status!r}")
        fields["overall_status"] = overall_status
    if finished_at is not None:
        fields["finished_at"] = finished_at
    if not fields:
        return
    set_clause = ", ".join(f"{name} = ?" for name in fields)
    connection.execute(
        f"UPDATE enrichment_runs SET {set_clause} WHERE id = ?", (*fields.values(), run_id)
    )


def insert_enrichment_run_item(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    story_id: int,
    expected_mode: str,
    status: str = "pending",
) -> int:
    if expected_mode not in ("direct_unit", "unit_proposal"):
        raise ValueError(f"Invalid expected_mode: {expected_mode!r}")
    if status not in ALLOWED_RUN_ITEM_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    cursor = connection.execute(
        """
        INSERT INTO enrichment_run_items(run_id, story_id, expected_mode, status)
        VALUES (?, ?, ?, ?)
        """,
        (run_id, story_id, expected_mode, status),
    )
    return int(cursor.lastrowid)


def update_enrichment_run_item(
    connection: sqlite3.Connection,
    *,
    item_id: int,
    status: str,
    illustration_unit_id: int | None = None,
    error_message: str | None = None,
    warnings_json: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    """A run item's outcome is always recorded as ONE complete
    transition, not a partial field-by-field patch: `status` is required
    (every call represents "this item just finished being attempted, and
    here is its full outcome"), and `illustration_unit_id`/
    `error_message`/`warnings_json` are ALWAYS written exactly as given
    -- including `None`, which correctly clears a stale value from an
    earlier attempt (e.g. a retried item that failed with an error
    message and now succeeds must not keep showing the old error)."""
    if status not in ALLOWED_RUN_ITEM_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    set_parts = ["status = ?", "illustration_unit_id = ?", "error_message = ?", "warnings_json = ?"]
    values: list[object] = [status, illustration_unit_id, error_message, warnings_json]
    if started_at is not None:
        set_parts.append("started_at = ?")
        values.append(started_at)
    if finished_at is not None:
        set_parts.append("finished_at = ?")
        values.append(finished_at)
    connection.execute(
        f"UPDATE enrichment_run_items SET {', '.join(set_parts)} WHERE id = ?",
        (*values, item_id),
    )


# ---------------------------------------------------------------------------
# Phase 3H: machine QA raw CRUD. Same split as every other table here --
# no business logic (no verdict computation, no repair decision-making,
# see illustration_engine/qa_agent.py and qa_orchestrator.py for that),
# only schema-shaped reads/writes.
# ---------------------------------------------------------------------------


def update_unit_machine_qa(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    qa_status: str,
    qa_model: str,
    qa_prompt_version: str,
    qa_checked_at: str | None = None,
    qa_confidence: float | None = None,
    qa_issues_json: str | None = None,
) -> None:
    """The SOLE write path for a unit's qa_* columns. Deliberately touches
    ONLY qa_status/qa_model/qa_prompt_version/qa_checked_at/qa_confidence/
    qa_issues_json -- never status, human_reviewed_at, or any content
    field. This is what makes "machine QA never sets human_reviewed_at/
    approved/published" structurally true rather than just a convention:
    there is no code path here that could touch them even by accident."""
    if qa_status not in ALLOWED_QA_STATUSES:
        raise ValueError(f"Invalid qa_status: {qa_status!r}")
    connection.execute(
        """
        UPDATE illustration_units
        SET qa_status = ?, qa_model = ?, qa_prompt_version = ?, qa_checked_at = ?,
            qa_confidence = ?, qa_issues_json = ?
        WHERE id = ?
        """,
        (
            qa_status,
            qa_model,
            qa_prompt_version,
            qa_checked_at or datetime.now(UTC).isoformat(),
            qa_confidence,
            qa_issues_json,
            unit_id,
        ),
    )


def insert_qa_repair(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    qa_model: str,
    qa_prompt_version: str,
    issues_before_json: str,
    fields_changed_json: str,
    before_values_json: str,
    after_values_json: str,
    repaired_at: str | None = None,
) -> int:
    """Records one repair event. This call itself does NOT apply the
    repair to `illustration_units` -- the caller (qa_orchestrator) writes
    the repaired content via the existing `update_draft_unit` (so the
    human-review-protection trigger/guard still applies exactly as for
    any other content edit) and records the audit row here separately."""
    cursor = connection.execute(
        """
        INSERT INTO qa_repairs(
            unit_id, repaired_at, qa_model, qa_prompt_version,
            issues_before_json, fields_changed_json, before_values_json, after_values_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            unit_id,
            repaired_at or datetime.now(UTC).isoformat(),
            qa_model,
            qa_prompt_version,
            issues_before_json,
            fields_changed_json,
            before_values_json,
            after_values_json,
        ),
    )
    return int(cursor.lastrowid)


def count_qa_repairs_for_unit(connection: sqlite3.Connection, unit_id: int) -> int:
    return int(
        connection.execute("SELECT COUNT(*) FROM qa_repairs WHERE unit_id = ?", (unit_id,)).fetchone()[0]
    )


def initialize_empty_database(
    database_path: str | Path | None = None,
    *,
    atomic: bool = True,
) -> Path:
    """Creates a fresh, schema-only database file (no source/story data).

    Useful for tests and as the Phase-1 buildable artifact; mirrors the
    atomic temp-file-then-replace pattern used by `hymn_sqlite`.
    """
    database = resolve_database_path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    target = _temporary_database_path(database) if atomic else database
    if target.exists():
        target.unlink()

    connection = sqlite3.connect(target)
    try:
        create_schema(connection)
        set_import_meta(
            connection,
            {
                "schema_version": str(SCHEMA_VERSION),
                "build_timestamp": datetime.now(UTC).isoformat(),
                "source_count": "0",
                "story_count": "0",
            },
        )
        integrity = check_integrity(connection)
        if integrity != "ok":
            raise ValueError(f"Invalid illustration SQLite integrity_check: {integrity}")
        connection.commit()
    finally:
        connection.close()

    if atomic:
        _replace_atomically(target, database)
    return database


def _temporary_database_path(database: Path) -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile(
        prefix=f".{database.stem}.",
        suffix=".tmp.sqlite3",
        dir=database.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _replace_atomically(source: Path, target: Path) -> None:
    import os
    import time

    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


__all__ = [
    "ALLOWED_ADAPTATION_STATUSES",
    "ALLOWED_DERIVATION_TYPES",
    "ALLOWED_NARRATIVE_STATUS_CONFIDENCE",
    "ALLOWED_NARRATIVE_STATUSES",
    "ALLOWED_QA_STATUSES",
    "ALLOWED_RUN_ITEM_STATUSES",
    "ALLOWED_RUN_STATUSES",
    "ALLOWED_STORY_STATUSES",
    "ALLOWED_STRATEGY_BANDS",
    "ALLOWED_UNIT_STATUSES",
    "DATABASE_NAME",
    "DEFAULT_DATABASE_PATH",
    "PILOT_HOMILETIC_FUNCTIONS",
    "PILOT_TONES",
    "PILOT_TOPICS",
    "REQUIRED_TABLES",
    "REQUIRED_VIEWS",
    "SCHEMA_VERSION",
    "IllustrationLicenseGateError",
    "IllustrationUnitReviewProtectionError",
    "check_integrity",
    "count_qa_repairs_for_unit",
    "create_schema",
    "initialize_empty_database",
    "insert_enrichment_run",
    "insert_enrichment_run_item",
    "insert_illustration_unit",
    "insert_qa_repair",
    "insert_source",
    "insert_story",
    "migrate_schema",
    "resolve_database_path",
    "set_import_meta",
    "update_enrichment_run",
    "update_enrichment_run_item",
    "update_illustration_unit_fields",
    "update_unit_machine_qa",
]
