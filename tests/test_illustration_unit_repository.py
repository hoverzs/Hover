from __future__ import annotations

import sqlite3

import pytest

from illustration_engine.illustration_sqlite import (
    IllustrationUnitReviewProtectionError,
    create_schema,
    insert_source,
    insert_story,
)
from illustration_engine.illustration_unit_repository import (
    approve_unit,
    attach_tag_to_unit,
    create_draft_unit,
    get_or_create_tag,
    get_unit,
    list_units_for_story,
    mark_needs_review,
    publish_unit,
    search_units,
    update_draft_unit,
    validate_publish_ready,
)


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _make_source(conn: sqlite3.Connection, *, license_status: str = "public_domain_confirmed") -> int:
    return insert_source(
        conn,
        code="SRC",
        title="Test Source",
        orig_language="en",
        license_status=license_status,
        license_basis_hu="test basis",
        reliability_tier="high",
    )


def _make_story(conn: sqlite3.Connection, source_id: int) -> int:
    return insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="001",
        title_original="Original Title",
        adaptation_status="verbatim_transcription",
        original_text="Once upon a time, a wise man taught his students a lesson about patience.",
    )


def test_full_lifecycle_draft_to_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    conn.commit()
    unit = get_unit(conn, unit_id)
    assert unit.status == "draft"
    assert unit.title_hu is None

    ready, reasons = validate_publish_ready(conn, unit_id)
    assert ready is False
    assert "title_hu is missing" in reasons

    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="A türelmes tanító",
        modern_hu_text="Egyszer egy bölcs ember türelemre tanította tanítványait.",
        summary_hu="Rövid tanmese a türelemről.",
        enrichment_model="test-model-v1",
        enrichment_prompt_version="hu_enrichment_v1",
    )
    conn.commit()

    mark_needs_review(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "needs_review"

    approve_unit(conn, unit_id)
    conn.commit()
    approved = get_unit(conn, unit_id)
    assert approved.status == "approved"
    assert approved.human_reviewed_at is not None

    ready, reasons = validate_publish_ready(conn, unit_id)
    assert ready is True
    assert reasons == []

    publish_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "published"


def test_list_units_for_story_ordered_by_unit_index() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    third = create_draft_unit(conn, story_id=story_id, unit_index=3, derivation_type="condensed_story")
    first = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="condensed_story")
    second = create_draft_unit(conn, story_id=story_id, unit_index=2, derivation_type="condensed_story")
    conn.commit()

    units = list_units_for_story(conn, story_id)
    conn.close()
    assert [u.id for u in units] == [first, second, third]
    assert [u.unit_index for u in units] == [1, 2, 3]


def test_get_unit_returns_none_for_missing_id() -> None:
    conn = _fresh_connection()
    result = get_unit(conn, 999999)
    conn.close()
    assert result is None


def test_update_draft_unit_refuses_silent_overwrite_of_reviewed_content() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()

    with pytest.raises(IllustrationUnitReviewProtectionError):
        update_draft_unit(conn, unit_id=unit_id, title_hu="AI re-run overwrite attempt")
    conn.close()


def test_approved_unit_explicit_overwrite_demotes_to_needs_review() -> None:
    """An explicit override on an APPROVED (not yet published) unit
    succeeds, but must actually demote it: human_reviewed_at cleared
    AND status forced back to needs_review — not left at 'approved'."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Eredeti", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    before = get_unit(conn, unit_id)
    assert before.status == "approved"
    assert before.human_reviewed_at is not None

    update_draft_unit(conn, unit_id=unit_id, title_hu="Explicit felülírás", allow_overwrite_reviewed=True)
    conn.commit()
    updated = get_unit(conn, unit_id)
    assert updated.title_hu == "Explicit felülírás"
    assert updated.human_reviewed_at is None
    assert updated.status == "needs_review"
    conn.close()


def test_published_unit_explicit_overwrite_demotes_to_needs_review() -> None:
    """Same guarantee, but starting from an actually PUBLISHED unit —
    the overwrite must demote it out of 'published' entirely."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Eredeti", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "published"

    update_draft_unit(
        conn, unit_id=unit_id, modern_hu_text="Felülírt szöveg", allow_overwrite_reviewed=True
    )
    conn.commit()
    updated = get_unit(conn, unit_id)
    assert updated.modern_hu_text == "Felülírt szöveg"
    assert updated.human_reviewed_at is None
    assert updated.status == "needs_review"
    conn.close()


def test_overwritten_previously_published_unit_disappears_from_search() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="Cím",
        modern_hu_text="Egyedi kulcsszó: villamosfarkas.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()
    assert [r.id for r in search_units(conn, "villamosfarkas")] == [unit_id]

    update_draft_unit(
        conn,
        unit_id=unit_id,
        modern_hu_text="Még mindig villamosfarkas, de módosítva.",
        allow_overwrite_reviewed=True,
    )
    conn.commit()
    assert get_unit(conn, unit_id).status == "needs_review"
    assert search_units(conn, "villamosfarkas") == []
    conn.close()


def test_demoted_unit_searchable_again_after_fresh_review_and_republish() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="Cím",
        modern_hu_text="Egyedi kulcsszó: napórakagyló.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()

    update_draft_unit(
        conn, unit_id=unit_id, modern_hu_text="Frissített napórakagyló szöveg.", allow_overwrite_reviewed=True
    )
    conn.commit()
    assert search_units(conn, "napórakagyló") == []

    # fresh human review + re-publish
    approve_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "approved"
    publish_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "published"
    assert [r.id for r in search_units(conn, "napórakagyló")] == [unit_id]
    conn.close()


def test_publish_unit_raises_on_non_publishable_source() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="restricted")
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()

    ready, reasons = validate_publish_ready(conn, unit_id)
    assert ready is False
    assert any("license_status" in r for r in reasons)

    with pytest.raises(sqlite3.IntegrityError):
        publish_unit(conn, unit_id)
    conn.close()


def test_search_returns_only_published_and_license_publishable_units() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    published_unit = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=published_unit,
        title_hu="Türelem",
        modern_hu_text="A türelemről szóló egyedi kulcsszó: zsiráfmadár.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, published_unit)
    conn.commit()
    publish_unit(conn, published_unit)

    draft_unit = create_draft_unit(conn, story_id=story_id, unit_index=2, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=draft_unit,
        title_hu="Draft cím",
        modern_hu_text="Ugyanaz az egyedi kulcsszó: zsiráfmadár, de draft állapotban.",
        summary_hu="Draft összefoglaló.",
    )
    conn.commit()

    approved_not_published = create_draft_unit(
        conn, story_id=story_id, unit_index=3, derivation_type="full_story_translation"
    )
    update_draft_unit(
        conn,
        unit_id=approved_not_published,
        title_hu="Jóváhagyott, de nem publikált",
        modern_hu_text="Egyedi kulcsszó: zsiráfmadár, jóváhagyva, de nem publikálva.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, approved_not_published)
    conn.commit()

    results = search_units(conn, "zsiráfmadár")
    conn.close()
    assert [r.id for r in results] == [published_unit]


def test_search_excludes_published_unit_from_non_publishable_source() -> None:
    """Even a unit whose OWN status is 'published' must not surface if
    its source's license status changes after the fact — the read path
    re-checks the source, it doesn't trust the unit's own status alone."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="Cím",
        modern_hu_text="Egyedi kulcsszó: hódfarkas.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()
    assert [r.id for r in search_units(conn, "hódfarkas")] == [unit_id]

    # simulate the source's license being revoked after the fact
    conn.execute("UPDATE sources SET license_status = 'restricted' WHERE id = ?", (source_id,))
    conn.commit()
    assert search_units(conn, "hódfarkas") == []
    conn.close()


def test_get_or_create_tag_is_idempotent() -> None:
    conn = _fresh_connection()
    first = get_or_create_tag(conn, category="topic", slug="irgalom", label_hu="irgalom")
    second = get_or_create_tag(conn, category="topic", slug="irgalom", label_hu="irgalom")
    conn.close()
    assert first == second


def test_attach_tag_to_unit_and_query() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="condensed_story")
    tag_id = get_or_create_tag(conn, category="function", slug="bevezeto", label_hu="bevezető illusztráció")
    attach_tag_to_unit(conn, unit_id=unit_id, tag_id=tag_id)
    conn.commit()

    row = conn.execute(
        "SELECT COUNT(*) FROM illustration_unit_tags WHERE unit_id = ? AND tag_id = ?",
        (unit_id, tag_id),
    ).fetchone()
    conn.close()
    assert row[0] == 1
