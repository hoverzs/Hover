from __future__ import annotations

import sqlite3

import pytest

from illustration_engine.illustration_sqlite import (
    ALLOWED_DERIVATION_TYPES,
    ALLOWED_NARRATIVE_STATUSES,
    ALLOWED_QA_STATUSES,
    REQUIRED_TABLES,
    REQUIRED_VIEWS,
    SCHEMA_VERSION,
    IllustrationLicenseGateError,
    check_integrity,
    count_qa_repairs_for_unit,
    create_schema,
    insert_illustration_unit,
    insert_qa_repair,
    insert_source,
    insert_story,
    migrate_schema,
    update_illustration_unit_fields,
    update_unit_machine_qa,
)


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _make_source(conn: sqlite3.Connection, *, license_status: str = "public_domain_confirmed", code: str = "SRC") -> int:
    return insert_source(
        conn,
        code=code,
        title="Test Source",
        orig_language="en",
        license_status=license_status,
        license_basis_hu="test basis",
        reliability_tier="high",
        tradition="test tradition",
    )


def _make_story(conn: sqlite3.Connection, source_id: int, *, original_text: str = "Verbatim source text.") -> int:
    return insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="001",
        title_original="Original Title",
        adaptation_status="verbatim_transcription",
        original_text=original_text,
        source_reference="Shabbat 82a",
    )


def test_schema_version_is_6() -> None:
    """Phase 3H bumped 5->6: qa_* columns on illustration_units + the new
    qa_repairs table."""
    assert SCHEMA_VERSION == 6


def test_required_tables_and_views_present() -> None:
    conn = _fresh_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    views = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
    conn.close()
    assert REQUIRED_TABLES <= tables
    assert REQUIRED_VIEWS <= views
    assert "illustration_units_fts" in tables | {
        r for r in tables
    }  # virtual table also shows as 'table' in sqlite_master


def test_integrity_check_ok_on_fresh_schema() -> None:
    conn = _fresh_connection()
    assert check_integrity(conn) == "ok"
    conn.close()


def test_one_story_can_have_multiple_units() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    unit1 = insert_illustration_unit(
        conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation"
    )
    unit2 = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=2,
        derivation_type="extracted_scene",
        source_span_start=0,
        source_span_end=10,
    )
    conn.commit()

    rows = conn.execute(
        "SELECT id FROM illustration_units WHERE story_id = ? ORDER BY unit_index", (story_id,)
    ).fetchall()
    conn.close()
    assert [r[0] for r in rows] == [unit1, unit2]


def test_foreign_key_violation_rejected() -> None:
    conn = _fresh_connection()
    with pytest.raises(sqlite3.IntegrityError):
        insert_illustration_unit(
            conn, story_id=999999, unit_index=1, derivation_type="full_story_translation"
        )
    conn.close()


def test_duplicate_unit_index_for_same_story_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    insert_illustration_unit(conn, story_id=story_id, unit_index=1, derivation_type="condensed_story")
    with pytest.raises(sqlite3.IntegrityError):
        insert_illustration_unit(conn, story_id=story_id, unit_index=1, derivation_type="condensed_story")
    conn.close()


def test_raw_story_untouched_by_unit_creation_and_enrichment() -> None:
    """Creating/enriching illustration units must never mutate the
    parent story's provenance fields."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    original_text = "Verbatim source text, must never change."
    story_id = _make_story(conn, source_id, original_text=original_text)

    before = conn.execute(
        "SELECT title_original, original_text, original_text_checksum, source_reference "
        "FROM stories WHERE id = ?",
        (story_id,),
    ).fetchone()

    unit_id = insert_illustration_unit(
        conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation"
    )
    update_illustration_unit_fields(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()

    after = conn.execute(
        "SELECT title_original, original_text, original_text_checksum, source_reference "
        "FROM stories WHERE id = ?",
        (story_id,),
    ).fetchone()
    conn.close()
    assert before == after
    assert after[1] == original_text


def test_extracted_scene_requires_source_span() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    with pytest.raises(ValueError, match="source span"):
        insert_illustration_unit(
            conn, story_id=story_id, unit_index=1, derivation_type="extracted_scene"
        )
    conn.close()


def test_source_span_end_must_exceed_start() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    with pytest.raises(ValueError):
        insert_illustration_unit(
            conn,
            story_id=story_id,
            unit_index=1,
            derivation_type="extracted_scene",
            source_span_start=50,
            source_span_end=10,
        )
    conn.close()


def test_incomplete_unit_cannot_be_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    with pytest.raises(ValueError, match="content-completeness"):
        insert_illustration_unit(
            conn,
            story_id=story_id,
            unit_index=1,
            derivation_type="full_story_translation",
            status="published",
            title_hu="Cím",
            modern_hu_text="Szöveg",
            human_reviewed_at="2026-01-01T00:00:00+00:00",
            # summary_hu missing
        )
    conn.close()


def test_unit_without_human_review_cannot_be_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    with pytest.raises(ValueError, match="human_reviewed_at"):
        insert_illustration_unit(
            conn,
            story_id=story_id,
            unit_index=1,
            derivation_type="full_story_translation",
            status="published",
            title_hu="Cím",
            modern_hu_text="Szöveg",
            summary_hu="Összefoglaló",
            # human_reviewed_at intentionally omitted
        )
    conn.close()


def test_complete_unit_on_non_publishable_source_cannot_be_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="unknown")
    story_id = _make_story(conn, source_id)
    with pytest.raises(IllustrationLicenseGateError):
        insert_illustration_unit(
            conn,
            story_id=story_id,
            unit_index=1,
            derivation_type="full_story_translation",
            status="published",
            title_hu="Cím",
            modern_hu_text="Szöveg",
            summary_hu="Összefoglaló",
            human_reviewed_at="2026-01-01T00:00:00+00:00",
        )
    conn.close()


def test_sql_layer_license_gate_on_update_even_bypassing_python_helper() -> None:
    """Raw SQL UPDATE must also be blocked — the SQL trigger is the
    fail-closed backstop, not just the Python precheck."""
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="restricted")
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="license_gate"):
        conn.execute(
            "UPDATE illustration_units SET status = 'published', updated_at = '' WHERE id = ?",
            (unit_id,),
        )
    conn.close()


def test_approved_status_does_not_require_completeness() -> None:
    """Mirrors the stories precedent: only 'published' is gated on
    content-completeness, intermediate workflow states are not."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn, story_id=story_id, unit_index=1, derivation_type="condensed_story", status="approved"
    )
    conn.close()
    assert unit_id > 0


def test_human_reviewed_content_protected_from_silent_overwrite_via_sql_trigger() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Eredeti cím",
        modern_hu_text="Eredeti szöveg",
        summary_hu="Eredeti összefoglaló",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="review_gate"):
        conn.execute(
            "UPDATE illustration_units SET title_hu = 'Csendes felülírás' WHERE id = ?",
            (unit_id,),
        )
    conn.close()


def test_approved_unit_enrichment_warnings_raw_sql_update_blocked_without_demotion() -> None:
    """Schema v4/Phase 3C-c: enrichment_warnings_json is audit/provenance
    data, not visible content, but it must be protected the same way --
    a raw SQL UPDATE that touches ONLY this column on an approved unit,
    without demoting it, must still be rejected by the trigger."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
        status="approved",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="review_gate"):
        conn.execute(
            "UPDATE illustration_units SET enrichment_warnings_json = '[\"invented\"]' WHERE id = ?",
            (unit_id,),
        )
    conn.close()


def test_published_unit_enrichment_model_raw_sql_update_blocked_without_demotion() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
        status="published",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
        enrichment_model="claude-sonnet-5",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="review_gate"):
        conn.execute(
            "UPDATE illustration_units SET enrichment_model = 'a-different-model' WHERE id = ?",
            (unit_id,),
        )
    conn.close()


def test_prompt_version_and_generated_at_raw_sql_update_blocked_without_demotion() -> None:
    """Same protection for the remaining two enrichment-provenance
    columns -- checked together since they share the exact same
    mechanism as enrichment_model/enrichment_warnings_json above."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
        status="approved",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
        enrichment_prompt_version="hu_illustration_enrichment_pilot_v1",
        enrichment_generated_at="2026-01-01T00:00:00+00:00",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="review_gate"):
        conn.execute(
            "UPDATE illustration_units SET enrichment_prompt_version = 'v2' WHERE id = ?",
            (unit_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="review_gate"):
        conn.execute(
            "UPDATE illustration_units SET enrichment_generated_at = '2027-01-01T00:00:00+00:00' WHERE id = ?",
            (unit_id,),
        )
    conn.close()


def test_enrichment_provenance_change_allowed_with_explicit_demotion() -> None:
    """The same sanctioned path as reviewed CONTENT changes: touching an
    enrichment-provenance column succeeds when the SAME UPDATE also
    clears human_reviewed_at and resets status to needs_review."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
        status="approved",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
        enrichment_model="claude-sonnet-5",
    )
    conn.commit()
    conn.execute(
        "UPDATE illustration_units SET enrichment_model = 'a-different-model', "
        "human_reviewed_at = NULL, status = 'needs_review' WHERE id = ?",
        (unit_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT enrichment_model, human_reviewed_at, status FROM illustration_units WHERE id = ?",
        (unit_id,),
    ).fetchone()
    conn.close()
    assert row == ("a-different-model", None, "needs_review")


def test_reviewed_content_change_requires_null_timestamp_and_needs_review_status_together() -> None:
    """The only sanctioned way to touch reviewed content: the SAME
    UPDATE must both null out human_reviewed_at AND reset status to
    'needs_review'. Neither alone is sufficient (see the two tests
    below); doing both together succeeds."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Eredeti cím",
        modern_hu_text="Eredeti szöveg",
        summary_hu="Eredeti összefoglaló",
        status="approved",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
    )
    conn.commit()
    conn.execute(
        "UPDATE illustration_units SET title_hu = 'Ember által frissített cím', "
        "human_reviewed_at = NULL, status = 'needs_review' WHERE id = ?",
        (unit_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT title_hu, human_reviewed_at, status FROM illustration_units WHERE id = ?", (unit_id,)
    ).fetchone()
    conn.close()
    assert row == ("Ember által frissített cím", None, "needs_review")


def test_reviewed_content_change_rejected_if_only_timestamp_cleared_but_status_stays() -> None:
    """Clearing human_reviewed_at alone, while leaving status at
    'approved'/'published', must still be rejected — that combination
    would leave a demoted/unreviewed row looking retrieval-ready."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Eredeti cím",
        modern_hu_text="Eredeti szöveg",
        summary_hu="Eredeti összefoglaló",
        status="approved",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="review_gate"):
        conn.execute(
            "UPDATE illustration_units SET title_hu = 'Csak időbélyeg törölve', "
            "human_reviewed_at = NULL WHERE id = ?",
            (unit_id,),
        )
    conn.close()


def test_reviewed_content_change_rejected_if_only_status_reset_but_timestamp_stays() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Eredeti cím",
        modern_hu_text="Eredeti szöveg",
        summary_hu="Eredeti összefoglaló",
        status="approved",
        human_reviewed_at="2026-01-01T00:00:00+00:00",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="review_gate"):
        conn.execute(
            "UPDATE illustration_units SET title_hu = 'Csak status resetelve', "
            "status = 'needs_review' WHERE id = ?",
            (unit_id,),
        )
    conn.close()


def test_raw_sql_publish_without_human_reviewed_at_blocked() -> None:
    """Even a complete, publishable-source unit cannot be published via
    raw SQL without human_reviewed_at — the CHECK constraint fires
    regardless of caller."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=1,
        derivation_type="full_story_translation",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE illustration_units SET status = 'published' WHERE id = ?", (unit_id,))
    conn.close()


def test_illustration_unit_tags_link_to_tags_table() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = insert_illustration_unit(
        conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation"
    )
    tag_id = conn.execute(
        "INSERT INTO tags(category, slug, label_hu) VALUES ('topic', 'irgalom', 'irgalom') RETURNING id"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO illustration_unit_tags(unit_id, tag_id) VALUES (?, ?)", (unit_id, tag_id)
    )
    conn.commit()

    joined = conn.execute(
        """
        SELECT t.slug FROM illustration_unit_tags ut
        JOIN tags t ON t.id = ut.tag_id
        WHERE ut.unit_id = ?
        """,
        (unit_id,),
    ).fetchall()
    conn.close()
    assert joined == [("irgalom",)]


def test_two_units_from_same_story_can_carry_different_tags() -> None:
    """Phase 3A's own stated principle: units derived from one long
    story may have different topics/tone/function."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Long story " * 500)
    unit1 = insert_illustration_unit(
        conn, story_id=story_id, unit_index=1, derivation_type="extracted_scene",
        source_span_start=0, source_span_end=100,
    )
    unit2 = insert_illustration_unit(
        conn, story_id=story_id, unit_index=2, derivation_type="extracted_scene",
        source_span_start=200, source_span_end=300,
    )
    tag_a = conn.execute(
        "INSERT INTO tags(category, slug, label_hu) VALUES ('topic', 'turelem', 'türelem') RETURNING id"
    ).fetchone()[0]
    tag_b = conn.execute(
        "INSERT INTO tags(category, slug, label_hu) VALUES ('topic', 'buszkeseg', 'büszkeség') RETURNING id"
    ).fetchone()[0]
    conn.execute("INSERT INTO illustration_unit_tags(unit_id, tag_id) VALUES (?, ?)", (unit1, tag_a))
    conn.execute("INSERT INTO illustration_unit_tags(unit_id, tag_id) VALUES (?, ?)", (unit2, tag_b))
    conn.commit()

    tags1 = {r[0] for r in conn.execute(
        "SELECT tag_id FROM illustration_unit_tags WHERE unit_id = ?", (unit1,)
    )}
    tags2 = {r[0] for r in conn.execute(
        "SELECT tag_id FROM illustration_unit_tags WHERE unit_id = ?", (unit2,)
    )}
    conn.close()
    assert tags1 == {tag_a}
    assert tags2 == {tag_b}
    assert tags1 != tags2


def test_narrative_status_and_confidence_must_be_set_together() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    with pytest.raises(ValueError, match="narrative_status"):
        insert_illustration_unit(
            conn,
            story_id=story_id,
            unit_index=1,
            derivation_type="full_story_translation",
            narrative_status="fable",
        )
    conn.close()


def test_narrative_status_controlled_vocabulary() -> None:
    assert "documented_historical_event" in ALLOWED_NARRATIVE_STATUSES
    assert "legend_about_historical_figure" in ALLOWED_NARRATIVE_STATUSES
    assert "rabbinic_aggadic_tale" in ALLOWED_NARRATIVE_STATUSES


def test_derivation_type_controlled_vocabulary() -> None:
    assert ALLOWED_DERIVATION_TYPES == frozenset(
        {"full_story_translation", "condensed_story", "extracted_scene"}
    )


def test_sources_tradition_column_populated_via_insert_source() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    tradition = conn.execute("SELECT tradition FROM sources WHERE id = ?", (source_id,)).fetchone()[0]
    conn.close()
    assert tradition == "test tradition"


def test_stories_source_reference_column_populated() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    ref = conn.execute("SELECT source_reference FROM stories WHERE id = ?", (story_id,)).fetchone()[0]
    conn.close()
    assert ref == "Shabbat 82a"


# ---------------------------------------------------------------------------
# Phase 3H: schema migration, QA persistence, lifecycle separation
# ---------------------------------------------------------------------------


def _make_unit(conn: sqlite3.Connection, story_id: int, *, unit_index: int = 1) -> int:
    return insert_illustration_unit(
        conn,
        story_id=story_id,
        unit_index=unit_index,
        derivation_type="full_story_translation",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
    )


def test_qa_repairs_in_required_tables() -> None:
    assert "qa_repairs" in REQUIRED_TABLES


def test_migrate_schema_on_fresh_db_matches_create_schema() -> None:
    """migrate_schema() on a brand-new :memory: DB must produce the exact
    same table/column shape as create_schema() alone -- no missing or
    extra columns."""
    conn = _fresh_connection()  # already ran create_schema via the fixture
    migrate_schema(conn)  # must be a safe no-op
    cols = {row[1] for row in conn.execute("PRAGMA table_info(illustration_units)")}
    conn.close()
    for expected in ("qa_status", "qa_model", "qa_prompt_version", "qa_checked_at", "qa_confidence", "qa_issues_json"):
        assert expected in cols


def test_migrate_schema_adds_missing_qa_columns_to_pre_existing_db() -> None:
    """Simulates a pre-Phase-3H database file (schema v5 shape, no qa_*
    columns) and proves migrate_schema() retrofits them WITHOUT touching
    existing row data -- this is the real scenario for the actual
    production illustrations.sqlite3 file."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    # Minimal pre-3H illustration_units shape (no qa_* columns) plus the
    # other tables a unit insert needs -- built by hand to avoid depending
    # on create_schema()'s CURRENT (post-3H) definition for this one test.
    conn.executescript(
        """
        CREATE TABLE sources (
            id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
            orig_language TEXT NOT NULL, license_status TEXT NOT NULL,
            license_basis_hu TEXT NOT NULL, reliability_tier TEXT NOT NULL,
            registered_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE stories (
            id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
            external_ref TEXT NOT NULL, canonical_key TEXT NOT NULL,
            title_original TEXT NOT NULL, original_text TEXT,
            adaptation_status TEXT NOT NULL DEFAULT 'verbatim_transcription',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE illustration_units (
            id INTEGER PRIMARY KEY, story_id INTEGER NOT NULL REFERENCES stories(id),
            unit_index INTEGER NOT NULL, derivation_type TEXT NOT NULL,
            title_hu TEXT, modern_hu_text TEXT, summary_hu TEXT, moral_hu TEXT,
            status TEXT NOT NULL DEFAULT 'draft', human_reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.execute(
        "INSERT INTO sources(code, title, orig_language, license_status, license_basis_hu, reliability_tier) "
        "VALUES ('SRC', 'T', 'en', 'public_domain_confirmed', 'x', 'high')"
    )
    conn.execute(
        "INSERT INTO stories(source_id, external_ref, canonical_key, title_original, original_text) "
        "VALUES (1, '1', '001', 'Orig', 'Text.')"
    )
    conn.execute(
        "INSERT INTO illustration_units(story_id, unit_index, derivation_type, title_hu) "
        "VALUES (1, 1, 'full_story_translation', 'Pre-existing title')"
    )
    conn.commit()

    cols_before = {row[1] for row in conn.execute("PRAGMA table_info(illustration_units)")}
    assert "qa_status" not in cols_before  # sanity: the pre-3H shape really lacks it

    migrate_schema(conn)

    cols_after = {row[1] for row in conn.execute("PRAGMA table_info(illustration_units)")}
    for expected in ("qa_status", "qa_model", "qa_prompt_version", "qa_checked_at", "qa_confidence", "qa_issues_json"):
        assert expected in cols_after
    # existing row data untouched
    title = conn.execute("SELECT title_hu FROM illustration_units WHERE id = 1").fetchone()[0]
    assert title == "Pre-existing title"
    qa_status = conn.execute("SELECT qa_status FROM illustration_units WHERE id = 1").fetchone()[0]
    assert qa_status is None  # newly-added column, no backfill
    conn.close()


def test_migrate_schema_is_idempotent_when_run_twice() -> None:
    conn = _fresh_connection()
    migrate_schema(conn)
    migrate_schema(conn)  # must not raise "duplicate column" or similar
    conn.close()


def test_update_unit_machine_qa_persists_all_fields() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id)

    update_unit_machine_qa(
        conn, unit_id=unit_id, qa_status="passed", qa_model="qa-model-1",
        qa_prompt_version="qa_v1", qa_confidence=0.92, qa_issues_json="[]",
    )
    row = conn.execute(
        "SELECT qa_status, qa_model, qa_prompt_version, qa_confidence, qa_issues_json, qa_checked_at "
        "FROM illustration_units WHERE id = ?",
        (unit_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "passed"
    assert row[1] == "qa-model-1"
    assert row[2] == "qa_v1"
    assert row[3] == 0.92
    assert row[4] == "[]"
    assert row[5] is not None


def test_update_unit_machine_qa_rejects_invalid_status() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id)
    with pytest.raises(ValueError):
        update_unit_machine_qa(
            conn, unit_id=unit_id, qa_status="not_a_real_status", qa_model="m", qa_prompt_version="v1"
        )
    conn.close()


def test_allowed_qa_statuses_exact_set() -> None:
    assert ALLOWED_QA_STATUSES == frozenset({"pending", "passed", "needs_attention", "failed"})


def test_machine_qa_never_changes_human_reviewed_at_or_status() -> None:
    """Lifecycle separation: running machine QA (even repeatedly) on a
    needs_review/approved/published unit must never move status or set/
    clear human_reviewed_at."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id)
    update_illustration_unit_fields(conn, unit_id=unit_id, status="needs_review")

    before = conn.execute("SELECT status, human_reviewed_at FROM illustration_units WHERE id=?", (unit_id,)).fetchone()

    for qa_status in ("passed", "needs_attention", "failed", "passed"):
        update_unit_machine_qa(
            conn, unit_id=unit_id, qa_status=qa_status, qa_model="m", qa_prompt_version="v1"
        )

    after = conn.execute("SELECT status, human_reviewed_at FROM illustration_units WHERE id=?", (unit_id,)).fetchone()
    conn.close()
    assert before == after == ("needs_review", None)


def test_machine_qa_does_not_touch_raw_story_or_checksum() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id)
    before = conn.execute(
        "SELECT original_text, original_text_checksum, title_original FROM stories WHERE id=?", (story_id,)
    ).fetchone()

    update_unit_machine_qa(conn, unit_id=unit_id, qa_status="failed", qa_model="m", qa_prompt_version="v1")

    after = conn.execute(
        "SELECT original_text, original_text_checksum, title_original FROM stories WHERE id=?", (story_id,)
    ).fetchone()
    conn.close()
    assert before == after


def test_insert_qa_repair_and_count() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id)

    assert count_qa_repairs_for_unit(conn, unit_id) == 0

    insert_qa_repair(
        conn, unit_id=unit_id, qa_model="m", qa_prompt_version="v1",
        issues_before_json='[{"code":"POOR_HUNGARIAN","detail":"x"}]',
        fields_changed_json='["modern_hu_text"]',
        before_values_json='{"modern_hu_text":"old"}',
        after_values_json='{"modern_hu_text":"new"}',
    )
    conn.commit()
    assert count_qa_repairs_for_unit(conn, unit_id) == 1
    conn.close()
