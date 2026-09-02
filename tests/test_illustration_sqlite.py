from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from illustration_engine.illustration_sqlite import (
    ALLOWED_ADAPTATION_STATUSES,
    ALLOWED_STORY_STATUSES,
    REQUIRED_TABLES,
    REQUIRED_VIEWS,
    SCHEMA_VERSION,
    IllustrationLicenseGateError,
    check_integrity,
    create_schema,
    initialize_empty_database,
    insert_source,
    insert_story,
    set_import_meta,
)
from illustration_engine.source_registry import PUBLISHABLE_LICENSE_STATUSES, load_source_registry


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_source(
    connection: sqlite3.Connection,
    *,
    code: str = "TEST_SRC",
    license_status: str = "public_domain_confirmed",
) -> int:
    return insert_source(
        connection,
        code=code,
        title="Teszt forrás",
        orig_language="hu",
        license_status=license_status,
        license_basis_hu="Teszt indoklás.",
        reliability_tier="high",
    )


def test_create_schema_creates_required_tables_and_view(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    views = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'view'"
        ).fetchall()
    }
    conn.close()

    assert REQUIRED_TABLES.issubset(tables)
    assert REQUIRED_VIEWS.issubset(views)


def test_integrity_check_passes_on_fresh_schema(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)

    assert check_integrity(conn) == "ok"
    conn.close()


def test_insert_source_and_draft_story_succeeds(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)

    source_id = _insert_source(conn, license_status="unknown")
    story_id = insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="story-1",
        title_original="Test Title",
        title_hu="Teszt cím",
        modern_hu_text="Mai magyar szöveg.",
        summary_hu="Rövid összefoglaló.",
        adaptation_status="editorial_paraphrase",
        status="draft",
    )
    conn.commit()

    row = conn.execute("SELECT status FROM stories WHERE id = ?", (story_id,)).fetchone()
    conn.close()
    assert row[0] == "draft"


def test_insert_story_draft_without_hungarian_layer_succeeds(tmp_path: Path) -> None:
    """A source-language import (no title_hu/modern_hu_text/summary_hu yet)
    must stay valid as long as status stays 'draft' — this is exactly the
    Jataka import shape before the AI-enrichment phase runs."""
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="unknown")

    story_id = insert_story(
        conn,
        source_id=source_id,
        external_ref="I",
        canonical_key="01",
        title_original="The Monkey and the Crocodile",
        adaptation_status="verbatim_transcription",
        status="draft",
    )
    conn.commit()

    row = conn.execute(
        "SELECT title_hu, modern_hu_text, summary_hu FROM stories WHERE id = ?", (story_id,)
    ).fetchone()
    conn.close()
    assert row == (None, None, None)


@pytest.mark.parametrize("status", ["needs_review", "approved"])
def test_insert_story_intermediate_workflow_status_without_hungarian_layer_succeeds(
    tmp_path: Path, status: str
) -> None:
    """Intermediate editorial workflow states must tolerate a partially
    enriched (or not-yet-enriched) Hungarian layer — only 'published' is
    fail-closed gated. This lets needs_review/approved represent an
    in-progress enrichment step, not a fully-populated end state."""
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="public_domain_confirmed")

    story_id = insert_story(
        conn,
        source_id=source_id,
        external_ref="I",
        canonical_key="01",
        title_original="The Monkey and the Crocodile",
        adaptation_status="verbatim_transcription",
        status=status,
    )
    conn.commit()

    row = conn.execute(
        "SELECT status, title_hu, modern_hu_text, summary_hu FROM stories WHERE id = ?",
        (story_id,),
    ).fetchone()
    conn.close()
    assert row == (status, None, None, None)


def test_insert_story_published_without_hungarian_layer_rejected(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="public_domain_confirmed")

    with pytest.raises(ValueError, match="content-completeness gate"):
        insert_story(
            conn,
            source_id=source_id,
            external_ref="I",
            canonical_key="01",
            title_original="The Monkey and the Crocodile",
            adaptation_status="verbatim_transcription",
            status="published",
        )
    conn.close()


def test_sql_check_allows_raw_insert_needs_review_without_hungarian_layer(tmp_path: Path) -> None:
    """Mirrors the Python-layer allowance: raw SQL must also be free to
    insert a 'needs_review' row without the Hungarian layer filled in."""
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="public_domain_confirmed")

    conn.execute(
        """
        INSERT INTO stories(
            source_id, external_ref, canonical_key, title_original, adaptation_status,
            status, created_at, updated_at
        )
        VALUES (?, 'I', '01', 'The Monkey and the Crocodile', 'verbatim_transcription',
                'needs_review', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
        """,
        (source_id,),
    )
    conn.commit()

    row = conn.execute("SELECT status FROM stories WHERE source_id = ?", (source_id,)).fetchone()
    conn.close()
    assert row[0] == "needs_review"


def test_sql_check_blocks_raw_insert_published_without_hungarian_layer(tmp_path: Path) -> None:
    """Defense-in-depth for the content-completeness gate: a raw SQL INSERT
    that bypasses insert_story() must still be blocked by the table-level
    CHECK constraint when status = 'published' but the Hungarian layer is
    NULL — even though the source's license is publishable.
    """
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="public_domain_confirmed")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO stories(
                source_id, external_ref, canonical_key, title_original, adaptation_status,
                status, created_at, updated_at
            )
            VALUES (?, 'I', '01', 'The Monkey and the Crocodile', 'verbatim_transcription',
                    'published', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
            """,
            (source_id,),
        )
    conn.close()


@pytest.mark.parametrize(
    "license_status",
    ["public_domain_assumed_by_age", "unknown", "restricted"],
)
def test_insert_story_published_rejected_for_non_publishable_license(
    tmp_path: Path, license_status: str
) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status=license_status)

    with pytest.raises(IllustrationLicenseGateError):
        insert_story(
            conn,
            source_id=source_id,
            external_ref="1",
            canonical_key="story-1",
            title_original="Test Title",
            title_hu="Teszt cím",
            modern_hu_text="Mai magyar szöveg.",
            summary_hu="Rövid összefoglaló.",
            adaptation_status="editorial_paraphrase",
            status="published",
        )
    conn.close()


@pytest.mark.parametrize("license_status", sorted(PUBLISHABLE_LICENSE_STATUSES))
def test_insert_story_published_succeeds_for_publishable_license(
    tmp_path: Path, license_status: str
) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status=license_status)

    story_id = insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="story-1",
        title_original="Test Title",
        title_hu="Teszt cím",
        modern_hu_text="Mai magyar szöveg.",
        summary_hu="Rövid összefoglaló.",
        adaptation_status="editorial_paraphrase",
        status="published",
    )
    conn.commit()

    row = conn.execute("SELECT status FROM stories WHERE id = ?", (story_id,)).fetchone()
    conn.close()
    assert row[0] == "published"


def test_insert_story_invalid_adaptation_status_rejected(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn)

    with pytest.raises(ValueError, match="adaptation_status"):
        insert_story(
            conn,
            source_id=source_id,
            external_ref="1",
            canonical_key="story-1",
            title_original="Test Title",
            title_hu="Teszt cím",
            modern_hu_text="Mai magyar szöveg.",
            summary_hu="Rövid összefoglaló.",
            adaptation_status="not_a_real_status",
        )
    conn.close()


def test_sql_trigger_blocks_raw_insert_bypassing_python_gate(tmp_path: Path) -> None:
    """Defense-in-depth: even a raw SQL INSERT that skips insert_story()
    entirely must be blocked by the DB trigger for a non-publishable source.
    """
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="public_domain_assumed_by_age")

    with pytest.raises(sqlite3.IntegrityError, match="license_gate"):
        conn.execute(
            """
            INSERT INTO stories(
                source_id, external_ref, canonical_key, title_original, title_hu,
                adaptation_status, modern_hu_text, summary_hu, status, created_at, updated_at
            )
            VALUES (?, '1', 'story-1', 'Title', 'Cím', 'editorial_paraphrase', 'Szöveg',
                    'Összefoglaló', 'published', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
            """,
            (source_id,),
        )
    conn.close()


def test_sql_trigger_blocks_raw_update_to_published(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="unknown")
    story_id = insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="story-1",
        title_original="Title",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
        adaptation_status="editorial_paraphrase",
        status="draft",
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="license_gate"):
        conn.execute(
            "UPDATE stories SET status = 'published' WHERE id = ?", (story_id,)
        )
    conn.close()


def test_published_stories_view_includes_valid_published_story(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn, license_status="public_domain_confirmed")
    insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="story-1",
        title_original="Title",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
        adaptation_status="editorial_paraphrase",
        status="published",
    )
    conn.commit()

    rows = conn.execute("SELECT canonical_key FROM published_stories").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["story-1"]


def test_published_stories_view_excludes_draft_and_non_publishable_sources(
    tmp_path: Path,
) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)

    draft_source_id = _insert_source(
        conn, code="DRAFT_SRC", license_status="public_domain_confirmed"
    )
    insert_story(
        conn,
        source_id=draft_source_id,
        external_ref="1",
        canonical_key="draft-story",
        title_original="Title",
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu="Összefoglaló",
        adaptation_status="editorial_paraphrase",
        status="draft",
    )
    conn.commit()

    rows = conn.execute("SELECT canonical_key FROM published_stories").fetchall()
    conn.close()
    assert rows == []


def test_import_meta_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    set_import_meta(conn, {"schema_version": str(SCHEMA_VERSION), "source_count": "1"})
    conn.commit()

    rows = dict(conn.execute("SELECT key, value FROM import_meta").fetchall())
    conn.close()
    assert rows["schema_version"] == str(SCHEMA_VERSION)
    assert rows["source_count"] == "1"


def test_initialize_empty_database_creates_valid_file(tmp_path: Path) -> None:
    db_path = tmp_path / "illustrations.sqlite3"
    result_path = initialize_empty_database(db_path)

    assert result_path == db_path
    assert db_path.is_file()

    conn = sqlite3.connect(db_path)
    try:
        assert check_integrity(conn) == "ok"
        meta = dict(conn.execute("SELECT key, value FROM import_meta").fetchall())
        assert meta["schema_version"] == str(SCHEMA_VERSION)
        assert meta["source_count"] == "0"
        assert meta["story_count"] == "0"
    finally:
        conn.close()


def test_allowed_status_constants_match_schema_check_constraints(tmp_path: Path) -> None:
    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = _insert_source(conn)

    for status in ALLOWED_STORY_STATUSES - {"published"}:
        insert_story(
            conn,
            source_id=source_id,
            external_ref=status,
            canonical_key=f"story-{status}",
            title_original="Title",
            title_hu="Cím",
            modern_hu_text="Szöveg",
            summary_hu="Összefoglaló",
            adaptation_status=next(iter(ALLOWED_ADAPTATION_STATUSES)),
            status=status,
        )
    conn.commit()
    conn.close()


def test_seed_registry_source_cannot_publish_story(tmp_path: Path) -> None:
    """End-to-end fail-closed proof: the real sources.json seed entry for
    Pesti Gábor (public_domain_assumed_by_age) must not be usable to
    publish a story, even when loaded through the real registry loader.
    """
    records = load_source_registry()
    pesti = next(r for r in records if r.code == "PESTI_ESOPUS_1536")

    db = tmp_path / "illustrations.sqlite3"
    conn = _connect(db)
    create_schema(conn)
    source_id = insert_source(
        conn,
        code=pesti.code,
        title=pesti.title,
        author=pesti.author,
        orig_language=pesti.orig_language,
        publication_year=pesti.publication_year,
        edition_reference=pesti.edition_reference,
        license_status=pesti.license_status,
        license_basis_hu=pesti.license_basis_hu,
        rights_holder=pesti.rights_holder,
        source_url=pesti.source_url,
        retrieved_at=pesti.retrieved_at,
        reliability_tier=pesti.reliability_tier,
        notes_hu=pesti.notes_hu,
    )

    with pytest.raises(IllustrationLicenseGateError):
        insert_story(
            conn,
            source_id=source_id,
            external_ref="1",
            canonical_key="esopus-1",
            title_original="A róka és a holló",
            title_hu="A róka és a holló",
            modern_hu_text="Mai magyar átirat.",
            summary_hu="Rövid összefoglaló.",
            adaptation_status="editorial_paraphrase",
            status="published",
        )
    conn.close()
