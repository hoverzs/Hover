from __future__ import annotations

import json
import sqlite3

import pytest

from illustration_engine.enrichment_pipeline import enrich_story
from illustration_engine.illustration_sqlite import create_schema, insert_source, insert_story
from illustration_engine.illustration_unit_repository import approve_unit, get_unit, list_units_for_story


ORIGINAL_TEXT = (
    "A friend told Sheridan that Lord Kenyon had fallen asleep during the "
    "play. Sheridan said: Ah, poor man, let him sleep, he thinks he is on "
    "the bench."
)

_VALID_SUMMARY = " ".join(["szo"] * 45)


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
        tradition="angol anekdota/humor",
    )


def _make_story(conn: sqlite3.Connection, source_id: int, *, original_text: str = ORIGINAL_TEXT) -> int:
    return insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="001",
        title_original="Lord Kenyon",
        adaptation_status="verbatim_transcription",
        original_text=original_text,
        source_reference="never touched by enrichment",
    )


def _valid_direct_unit_payload(**overrides) -> dict:
    unit = {
        "derivation_type": "full_story_translation",
        "title_hu": "Lord Kenyon a színházban",
        "modern_hu_text": (
            "Egy barátja elmesélte Sheridannek, hogy Lord Kenyon elaludt az "
            "előadáson. Sheridan csak ennyit mondott: hadd aludjon szegény, "
            "azt hiszi, a bírói székben van."
        ),
        "summary_hu": _VALID_SUMMARY,
        "moral_hu": "A megszokás erősebb, mint a helyzet váratlansága.",
        "topics": ["eszesseg"],
        "tone": "humoros",
        "homiletic_functions": ["szemlelteto_pelda"],
        "narrative_status": "traditional_anecdote",
        "narrative_status_confidence": "medium",
    }
    unit.update(overrides)
    return {"mode": "direct_unit", "unit": unit}


def _llm(payload: dict | str):
    if isinstance(payload, str):
        return lambda prompt: payload
    return lambda prompt: json.dumps(payload)


def test_valid_enrichment_creates_needs_review_unit() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(_valid_direct_unit_payload()), model_identifier="mock-1", expected_mode="direct_unit"
    )
    conn.commit()

    assert result.status == "unit_created"
    unit = get_unit(conn, result.unit_id)
    assert unit.status == "needs_review"
    assert unit.human_reviewed_at is None
    assert unit.enrichment_model == "mock-1"
    assert unit.title_hu == "Lord Kenyon a színházban"
    conn.close()


def test_tags_correctly_attached() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(
        topics=["eszesseg", "buszkeseg"],
        tone="ironikus",
        homiletic_functions=["szemlelteto_pelda", "lezaro_illusztracio"],
    )
    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.commit()

    rows = conn.execute(
        "SELECT t.category, t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
        "WHERE ut.unit_id = ? ORDER BY t.category, t.slug",
        (result.unit_id,),
    ).fetchall()
    conn.close()
    assert set(rows) == {
        ("topic", "eszesseg"),
        ("topic", "buszkeseg"),
        ("tone", "ironikus"),
        ("function", "szemlelteto_pelda"),
        ("function", "lezaro_illusztracio"),
    }


def test_invalid_json_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    result = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm("this is not json at all"),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.close()
    assert result.status == "rejected"
    assert "JSON" in result.errors[0]


def test_missing_mode_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    result = enrich_story(conn, story_id=story_id, llm_generate=_llm({"unit": {}}), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert "mode" in result.errors[0]


def test_missing_required_field_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload()
    del payload["unit"]["moral_hu"]

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("moral_hu" in e for e in result.errors)


def test_forbidden_topic_enum_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(topics=["nem_letezo_cimke"])

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("topics" in e for e in result.errors)


def test_forbidden_narrative_status_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(narrative_status="definitely_true_history")

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("narrative_status" in e for e in result.errors)


def test_tone_must_be_exactly_one_controlled_value() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(tone="dühös")

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("tone" in e for e in result.errors)


def test_summary_too_short_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(summary_hu="Túl rövid összefoglaló.")

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("summary_hu" in e for e in result.errors)


def test_summary_too_long_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(summary_hu=" ".join(["szo"] * 150))

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("summary_hu" in e for e in result.errors)


def test_empty_title_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(title_hu="   ")

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("title_hu" in e for e in result.errors)


def test_empty_modern_hu_text_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(modern_hu_text="")

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("modern_hu_text" in e for e in result.errors)


def test_hallucinated_proper_noun_guard_rejects() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(
        modern_hu_text="Sheridan azt mondta Zoltanovics Bélának, hogy aludjon tovább."
    )

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("hallucinated" in e for e in result.errors)


def test_hallucination_guard_accepts_inflected_hungarian_forms_of_real_names() -> None:
    """Regression guard for a real bug found during implementation: a
    naive exact-match check flagged EVERY inflected Hungarian form of a
    real source name (Hungarian glues case suffixes directly onto
    proper nouns) as a false positive. Prefix-matching against source
    words must accept these."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(
        modern_hu_text=(
            "Sheridannek elmondták, hogy Lord Kenyonnak elaludt a szeme. "
            "Sheridan Kenyonhoz fordult tréfásan."
        )
    )

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "unit_created"


def test_raw_story_unchanged_after_enrichment() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    before = conn.execute(
        "SELECT title_original, original_text, original_text_checksum, source_reference "
        "FROM stories WHERE id = ?",
        (story_id,),
    ).fetchone()

    enrich_story(conn, story_id=story_id, llm_generate=_llm(_valid_direct_unit_payload()), model_identifier="m", expected_mode="direct_unit")
    conn.commit()

    after = conn.execute(
        "SELECT title_original, original_text, original_text_checksum, source_reference "
        "FROM stories WHERE id = ?",
        (story_id,),
    ).fetchone()
    conn.close()
    assert before == after


def test_human_reviewed_unit_overwrite_blocked() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    result = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload()),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()
    approve_unit(conn, result.unit_id)
    conn.commit()

    second = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(title_hu="AI re-run overwrite attempt")),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.close()
    assert second.status == "rejected"
    assert any("human-reviewed" in e for e in second.errors)


def test_idempotent_rerun_updates_draft_unit_in_place() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    first = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(title_hu="Első cím")),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()
    second = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(title_hu="Frissített cím")),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    assert first.unit_id == second.unit_id
    total_units = conn.execute("SELECT COUNT(*) FROM illustration_units WHERE story_id = ?", (story_id,)).fetchone()[0]
    conn.close()
    assert total_units == 1
    assert second.status == "unit_created"


def test_long_story_unit_proposal_not_persisted() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    long_text = ORIGINAL_TEXT + " " + ("Filler sentence about the story continuing. " * 100)
    story_id = _make_story(conn, source_id, original_text=long_text)

    payload = {
        "mode": "unit_proposal",
        "proposed_units": [
            {
                "derivation_type": "extracted_scene",
                "source_span_start": 0,
                "source_span_end": 120,
                "title_hu": "Első jelenet",
                "modern_hu_text": "Sheridan és Kenyon jelenete.",
                "summary_hu": _VALID_SUMMARY,
                "moral_hu": "tanulság",
                "topics": ["eszesseg"],
                "tone": "humoros",
                "homiletic_functions": ["szemlelteto_pelda"],
                "narrative_status": "traditional_anecdote",
                "narrative_status_confidence": "medium",
                "rationale": "Ez a bekezdés önmagában lezárt csattanóval rendelkezik.",
                "standalone_reason": "Nem igényli a folytatás ismeretét.",
            }
        ],
    }
    before_count = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal")
    after_count = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    conn.close()

    assert result.status == "proposal_ready"
    assert len(result.proposed_units) == 1
    assert result.proposed_units[0].rationale == "Ez a bekezdés önmagában lezárt csattanóval rendelkezik."
    assert before_count == after_count == 0


def test_unit_proposal_with_invalid_span_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = {
        "mode": "unit_proposal",
        "proposed_units": [
            {
                "derivation_type": "extracted_scene",
                "source_span_start": 500,
                "source_span_end": 10,  # end before start
                "title_hu": "Cím",
                "modern_hu_text": "Szöveg.",
                "summary_hu": _VALID_SUMMARY,
                "moral_hu": "tanulság",
                "topics": ["eszesseg"],
                "tone": "humoros",
                "homiletic_functions": ["szemlelteto_pelda"],
                "narrative_status": "traditional_anecdote",
                "narrative_status_confidence": "medium",
                "rationale": "x",
                "standalone_reason": "x",
            }
        ],
    }
    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal")
    conn.close()
    assert result.status == "rejected"
    assert any("span" in e for e in result.errors)


def test_extracted_scene_without_rationale_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = {
        "mode": "unit_proposal",
        "proposed_units": [
            {
                "derivation_type": "extracted_scene",
                "source_span_start": 0,
                "source_span_end": 20,
                "title_hu": "Cím",
                "modern_hu_text": "Sheridan es Kenyon.",
                "summary_hu": _VALID_SUMMARY,
                "moral_hu": "tanulság",
                "topics": ["eszesseg"],
                "tone": "humoros",
                "homiletic_functions": ["szemlelteto_pelda"],
                "narrative_status": "traditional_anecdote",
                "narrative_status_confidence": "medium",
                "rationale": "",
                "standalone_reason": "",
            }
        ],
    }
    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal")
    conn.close()
    assert result.status == "rejected"
    assert any("rationale" in e for e in result.errors)


def test_condensed_story_proposal_does_not_require_span() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = {
        "mode": "unit_proposal",
        "proposed_units": [
            {
                "derivation_type": "condensed_story",
                "source_span_start": None,
                "source_span_end": None,
                "title_hu": "Tömörített",
                "modern_hu_text": "Sheridan es Kenyon tortenete tomoritve.",
                "summary_hu": _VALID_SUMMARY,
                "moral_hu": "tanulság",
                "topics": ["eszesseg"],
                "tone": "humoros",
                "homiletic_functions": ["szemlelteto_pelda"],
                "narrative_status": "traditional_anecdote",
                "narrative_status_confidence": "medium",
                "rationale": None,
                "standalone_reason": None,
            }
        ],
    }
    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal")
    conn.close()
    assert result.status == "proposal_ready"


def test_story_not_found_rejected() -> None:
    conn = _fresh_connection()
    result = enrich_story(conn, story_id=999999, llm_generate=_llm(_valid_direct_unit_payload()), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"


def test_direct_unit_cannot_carry_source_span() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(source_span_start=0, source_span_end=10)

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"


# ---------------------------------------------------------------------------
# Post-review hardening: expected_mode enforcement, tag sync (not
# accumulation), atomic direct-unit persistence, and a tightened
# hallucination guard. See enrichment_pipeline.py's module docstring
# "FOLLOW-UP HARDENING" section for the design rationale behind each.
# ---------------------------------------------------------------------------


def test_long_story_expected_unit_proposal_but_model_returns_direct_unit_is_rejected() -> None:
    """The persistence decision must never be left to the model: if the
    caller declares expected_mode='unit_proposal' (the long-story
    stress case) but the model answers with 'direct_unit' anyway, the
    result must be rejected BEFORE either handler runs — so literally
    zero illustration_units may exist afterward, not even a partial
    write."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    long_text = ORIGINAL_TEXT + " " + ("Filler sentence about the story continuing. " * 100)
    story_id = _make_story(conn, source_id, original_text=long_text)

    # The model answers with a well-formed, otherwise entirely VALID
    # direct_unit payload — proving the rejection is purely about the
    # mode mismatch, not about content validity.
    result = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload()),
        model_identifier="m",
        expected_mode="unit_proposal",
    )

    unit_count = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    conn.close()
    assert result.status == "rejected"
    assert any("expected_mode" in e for e in result.errors)
    assert unit_count == 0


def test_expected_direct_unit_but_model_returns_unit_proposal_is_rejected() -> None:
    """Symmetric case: a normal 1:1 story called with
    expected_mode='direct_unit' must also reject a 'unit_proposal'
    response instead of silently accepting a read-only proposal result
    for a story the caller never authorized splitting for."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = {
        "mode": "unit_proposal",
        "proposed_units": [
            {
                "derivation_type": "condensed_story",
                "source_span_start": None,
                "source_span_end": None,
                "title_hu": "Cím",
                "modern_hu_text": "Szöveg.",
                "summary_hu": _VALID_SUMMARY,
                "moral_hu": "tanulság",
                "topics": ["eszesseg"],
                "tone": "humoros",
                "homiletic_functions": ["szemlelteto_pelda"],
                "narrative_status": "traditional_anecdote",
                "narrative_status_confidence": "medium",
                "rationale": None,
                "standalone_reason": None,
            }
        ],
    }
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "rejected"
    assert any("expected_mode" in e for e in result.errors)


def test_tag_rerun_replaces_not_accumulates() -> None:
    """First run: topics=[alazat, bolcsesseg]. Second run: topics=
    [becsuletesseg]. After the second run, exactly becsuletesseg must
    remain in the topic category for this unit — no stale accumulation
    of the first run's topics."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    first = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(topics=["alazat", "bolcsesseg"])),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    second = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(topics=["becsuletesseg"])),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    assert first.unit_id == second.unit_id
    topic_slugs = {
        row[0]
        for row in conn.execute(
            "SELECT t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
            "WHERE ut.unit_id = ? AND t.category = 'topic'",
            (second.unit_id,),
        ).fetchall()
    }
    conn.close()
    assert topic_slugs == {"becsuletesseg"}


def test_tag_rerun_replaces_tone_and_functions_too() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(
            _valid_direct_unit_payload(
                tone="komoly", homiletic_functions=["bevezeto_illusztracio", "ellenpelda"]
            )
        ),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()
    result = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(tone="ironikus", homiletic_functions=["lezaro_illusztracio"])),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    tone_slugs = {
        row[0]
        for row in conn.execute(
            "SELECT t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
            "WHERE ut.unit_id = ? AND t.category = 'tone'",
            (result.unit_id,),
        ).fetchall()
    }
    function_slugs = {
        row[0]
        for row in conn.execute(
            "SELECT t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
            "WHERE ut.unit_id = ? AND t.category = 'function'",
            (result.unit_id,),
        ).fetchall()
    }
    conn.close()
    assert tone_slugs == {"ironikus"}
    assert function_slugs == {"lezaro_illusztracio"}


def test_tag_sync_does_not_touch_non_pilot_controlled_tag() -> None:
    """A tag this pipeline does not own (different category, or a
    category it owns but a slug outside its controlled vocabulary —
    representing some future, non-pilot metadata source) must survive
    a re-run untouched."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    result = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(topics=["alazat"])),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    # Simulate a tag attached by some other, non-pilot mechanism: same
    # 'topic' category, but a slug outside PILOT_TOPICS.
    foreign_tag_id = conn.execute(
        "INSERT INTO tags(category, slug, label_hu) VALUES ('topic', 'kulso_cimke', 'külső címke') RETURNING id"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO illustration_unit_tags(unit_id, tag_id) VALUES (?, ?)", (result.unit_id, foreign_tag_id)
    )
    conn.commit()

    enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(topics=["becsuletesseg"])),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    remaining_slugs = {
        row[0]
        for row in conn.execute(
            "SELECT t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
            "WHERE ut.unit_id = ? AND t.category = 'topic'",
            (result.unit_id,),
        ).fetchall()
    }
    conn.close()
    assert remaining_slugs == {"becsuletesseg", "kulso_cimke"}


def test_atomic_rollback_on_mid_sequence_failure_leaves_no_partial_unit(monkeypatch) -> None:
    """Deliberately induced failure at the tag-sync step (via
    monkeypatch) — the previous DB state must be fully preserved: no
    illustration_unit row, no tags, nothing partially written."""
    import illustration_engine.enrichment_pipeline as pipeline_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    def failing_get_or_create_tag(*args, **kwargs):
        raise RuntimeError("simulated tag-sync failure")

    monkeypatch.setattr(pipeline_module, "get_or_create_tag", failing_get_or_create_tag)

    before_units = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    before_tags = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    result = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload()),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    after_units = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    after_tags = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    assert result.status == "rejected"
    assert any("persistence failed" in e for e in result.errors)
    assert after_units == before_units == 0
    assert after_tags == before_tags


def test_atomic_rollback_preserves_prior_content_on_idempotent_rerun_failure(monkeypatch) -> None:
    """A more thorough atomicity check: the unit already exists (from a
    successful first run) with specific content; a second run fails
    mid-sequence (simulated at mark_needs_review) — the unit's content
    must revert to / remain exactly the first run's values, not a
    half-applied mix of old and new."""
    import illustration_engine.enrichment_pipeline as pipeline_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    first = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(title_hu="Eredeti, sikeres cím")),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()
    before = get_unit(conn, first.unit_id)

    def failing_mark_needs_review(*args, **kwargs):
        raise RuntimeError("simulated failure after content update")

    monkeypatch.setattr(pipeline_module, "mark_needs_review", failing_mark_needs_review)

    second = enrich_story(
        conn,
        story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(title_hu="Félbeszakadt frissítés")),
        model_identifier="m",
        expected_mode="direct_unit",
    )
    conn.commit()

    after = get_unit(conn, first.unit_id)
    conn.close()

    assert second.status == "rejected"
    assert before.title_hu == "Eredeti, sikeres cím"
    assert after.title_hu == "Eredeti, sikeres cím"  # unchanged, NOT "Félbeszakadt frissítés"
    assert after == before


def test_hallucination_guard_short_candidate_prefix_of_unrelated_source_word_still_flagged() -> None:
    """Regression for a real false-negative found during audit: the
    OLD bidirectional prefix match let a short hallucinated candidate
    slip through un-flagged just because it happened to be a prefix of
    some longer, completely UNRELATED capitalized source word (e.g.
    'Ede' vs. a real but unrelated source word 'Edenville'). The
    tightened single-direction match (candidate must start with a real
    source word, never the reverse) correctly rejects it."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn,
        source_id,
        original_text=(
            "Sheridan lived near Edenville, a quiet market town, "
            "before he moved to London for the season."
        ),
    )
    payload = _valid_direct_unit_payload(
        modern_hu_text="Sheridan Ede birtokán élt, mielőtt Londonba költözött a szezonra."
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "rejected"
    assert any("hallucinated" in e and "Ede" in e for e in result.errors)


def test_hallucination_guard_still_accepts_inflected_real_name_after_tightening() -> None:
    """Companion regression to the guard above: tightening the match
    direction/source pool must not reintroduce the original false-
    positive bug (rejecting real, correctly-inflected Hungarian forms
    of genuine source names)."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(
        modern_hu_text=(
            "Sheridannek elmondták, hogy Lord Kenyonnak elaludt a szeme a "
            "színházban. Sheridan Kenyonhoz fordult tréfásan, és mindketten "
            "nevettek a helyzeten."
        )
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
