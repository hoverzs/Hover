from __future__ import annotations

import json
import sqlite3

import pytest

from illustration_engine.enrichment_pipeline import (
    build_enrichment_prompt,
    derive_enrichment_strategy,
    enrich_story,
)
from illustration_engine.illustration_sqlite import create_schema, insert_source, insert_story
from illustration_engine.illustration_unit_repository import (
    approve_unit,
    get_unit,
    list_units_for_story,
    publish_unit,
)


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
    """title_hu remains a genuinely required field -- unlike moral_hu
    (Phase 3G-B3, see the moral_hu-specific tests below), omitting it
    must still be rejected."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload()
    del payload["unit"]["title_hu"]

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("title_hu" in e for e in result.errors)


# --- Phase 3G-B3: moral_hu is optional ---------------------------------


def test_moral_hu_null_is_valid() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(moral_hu=None)

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.commit()
    assert result.status == "unit_created"
    unit = get_unit(conn, result.unit_id)
    conn.close()
    assert unit.moral_hu is None


def test_moral_hu_empty_string_is_valid() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(moral_hu="")

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.commit()
    assert result.status == "unit_created"
    unit = get_unit(conn, result.unit_id)
    conn.close()
    assert unit.moral_hu == ""


def test_moral_hu_key_entirely_absent_is_valid() -> None:
    """The model may omit the moral_hu key outright, not just send null --
    the old direct-index unit_payload["moral_hu"] access would have raised
    KeyError for this shape."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload()
    del payload["unit"]["moral_hu"]

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.commit()
    assert result.status == "unit_created"
    unit = get_unit(conn, result.unit_id)
    conn.close()
    assert unit.moral_hu is None


def test_humorous_anecdote_with_empty_moral_is_valid() -> None:
    """The concrete policy motivation: a humoros/ironikus anecdote with no
    natural lesson must not be forced to invent one."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(tone="humoros", moral_hu=None)

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "unit_created"


def test_existing_moral_hu_still_persists_when_provided() -> None:
    """The optional policy must not regress the case where a story DOES
    have a natural moral -- providing one still works exactly as before."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(moral_hu="A megszokás erősebb, mint a helyzet váratlansága.")

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.commit()
    assert result.status == "unit_created"
    unit = get_unit(conn, result.unit_id)
    conn.close()
    assert unit.moral_hu == "A megszokás erősebb, mint a helyzet váratlansága."


def test_moral_hu_wrong_type_is_rejected() -> None:
    """Only a genuinely wrong TYPE (not null/empty/absent) is an error."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(moral_hu=["not", "a", "string"])

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "rejected"
    assert any("moral_hu" in e for e in result.errors)


def test_other_required_fields_still_reject_when_missing() -> None:
    """modern_hu_text and summary_hu remain required -- only moral_hu's
    requirement was lifted."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    payload_no_modern = _valid_direct_unit_payload()
    del payload_no_modern["unit"]["modern_hu_text"]
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload_no_modern), model_identifier="m", expected_mode="direct_unit"
    )
    assert result.status == "rejected"
    assert any("modern_hu_text" in e for e in result.errors)

    payload_no_summary = _valid_direct_unit_payload()
    del payload_no_summary["unit"]["summary_hu"]
    result2 = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload_no_summary), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result2.status == "rejected"
    assert any("summary_hu" in e for e in result2.errors)


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


def test_wholly_invented_two_word_name_warns_not_rejects() -> None:
    """Phase 3C-c two-tier guard: a wholly invented two-word name (neither
    word matches any source word) has no MATCHED neighbor to trigger a
    hard reject -- it is structurally indistinguishable, without a
    translation dictionary the brief explicitly forbids building, from a
    standalone correct exonym like 'Anglia'. Per the brief, an
    undecidable case must degrade to a warning rather than risk a false
    hard reject; a human reviewer sees it via EnrichmentResult.warnings."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(
        modern_hu_text="Sheridan azt mondta Zoltanovics Bélának, hogy aludjon tovább."
    )

    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit")
    conn.close()
    assert result.status == "unit_created"
    assert any("Zoltanovics" in w or "Bélának" in w for w in result.warnings)


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
    story_id = _make_story(conn, source_id, original_text=_LONG_SOURCE_TEXT)
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
    story_id = _make_story(conn, source_id, original_text=_LONG_SOURCE_TEXT)
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


_LONG_SOURCE_TEXT = "A" * 3500  # > 3000 so derive_enrichment_strategy() actually resolves to unit_proposal


def test_condensed_story_proposal_does_not_require_span() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_LONG_SOURCE_TEXT)
    payload = {
        "mode": "unit_proposal",
        "proposed_units": [
            {
                "derivation_type": "condensed_story",
                "source_span_start": None,
                "source_span_end": None,
                "title_hu": "Tömörített",
                "summary_hu": _VALID_SUMMARY,
                "topics": ["eszesseg"],
                "tone": "humoros",
                "homiletic_functions": ["szemlelteto_pelda"],
                "narrative_status": "traditional_anecdote",
                "narrative_status_confidence": "medium",
                "rationale": None,
                "standalone_reason": None,
                "target_length_chars": 500,
            }
        ],
    }
    result = enrich_story(conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal")
    conn.close()
    assert result.status == "proposal_ready"
    assert result.proposed_units[0].modern_hu_text is None
    assert result.proposed_units[0].moral_hu is None
    assert result.proposed_units[0].target_length_chars == 500


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
    """Regression for a real false-negative found during audit: the OLD
    bidirectional prefix match let a short hallucinated candidate slip
    through completely UNFLAGGED just because it happened to be a prefix
    of some longer, completely UNRELATED capitalized source word (e.g.
    'Ede' vs. a real but unrelated source word 'Edenville'). The
    tightened single-direction match (candidate must start with a real
    source word, never the reverse) still flags it -- but Phase 3D.1
    downgraded ALL proper-name guard findings to warnings (see
    _hallucination_guard's docstring: the adjacency shape this exhibits
    -- 'Ede' right next to the matched real name 'Sheridan' -- turned out
    to also fire on genuinely correct translations in the untouched
    pilot, so it can no longer block persistence by itself). 'Ede' is
    still surfaced, now as a SUSPICIOUS NAME EXPANSION warning, and the
    unit still reaches needs_review for a human to actually judge it."""
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
    assert result.status == "unit_created"
    assert not result.errors
    assert any("SUSPICIOUS NAME EXPANSION" in w and "Ede" in w for w in result.warnings)


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


# ---------------------------------------------------------------------------
# Fixes applied after the Phase 3C live smoke pilot: sentence-boundary
# false positive, explicit name-completion prohibition, and explicit
# narrative_status provenance discipline in the prompt.
# ---------------------------------------------------------------------------


def test_sentence_boundary_period_then_closing_quote_then_capital_word_accepted() -> None:
    """Regression for the exact real-world false positive found on the
    live pilot run: '...canals.” Egy ismerőse...' — a closing curly
    quote sits between the period and the whitespace, which used to
    defeat the sentence-boundary check and cause the Hungarian article
    'Egy' to be wrongly treated as mid-sentence (and then flagged as a
    hallucinated proper noun, since it obviously matches no source
    word)."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn,
        source_id,
        original_text=(
            'A lady wrote: "His Lordship could not weep; sorrow had frozen '
            'his lachrymal canals." A friend who borrowed the book returned '
            "it with a witty pencil note about the canals."
        ),
    )
    payload = _valid_direct_unit_payload(
        title_hu="Befagyott könnycsatornák",
        modern_hu_text=(
            "Egy hölgy ezt írta a könyvében: „Nem tudott sírni; a bánat jégbe "
            "fagyasztotta könnycsatornáit.” Egy ismerőse, aki kölcsönkérte a "
            "könyvet, egy szellemes ceruzajegyzettel küldte vissza a "
            "csatornákról."
        ),
        moral_hu="A dagályos fogalmazás könnyen nevetségessé válhat.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"


def test_sentence_boundary_question_mark_then_closing_quote_then_capital_word_accepted() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn,
        source_id,
        original_text=(
            "Sheridan asked, \"Are you quite well?\" Later he told Lord Kenyon "
            "the whole story again."
        ),
    )
    payload = _valid_direct_unit_payload(
        modern_hu_text=(
            "Sheridan megkérdezte: „Jól vagy?” Utána még egyszer elmesélte az "
            "egész történetet Lord Kenyonnak."
        )
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"


def test_sentence_boundary_normal_case_without_quote_still_works() -> None:
    """The sentence-boundary fix must not weaken the guard for the
    ordinary, no-quote boundary case: a word right after a plain '. '
    boundary must still be evaluated as sentence-INITIAL (i.e. NOT
    flagged/reported), same as the quote-preceded case. 'Zoltanovics
    Béla' (both unmatched, no matched neighbor) still surfaces as a
    warning per the two-tier guard, confirming the guard is still
    actively scanning this sentence rather than silently skipping it."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload(
        modern_hu_text="Sheridan elmondta a történetet. Zoltanovics Béla csak nevetett rajta."
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert any("Béla" in w for w in result.warnings)


def test_sentence_initial_hungarian_article_never_flagged_as_proper_noun() -> None:
    """'Egy' (the Hungarian indefinite article) must never itself be
    treated as a candidate proper noun once it is correctly recognized
    as sentence-initial — the exact failure from the live pilot."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn,
        source_id,
        original_text='He said: "Nothing more to add." A friend nodded in agreement.',
    )
    payload = _valid_direct_unit_payload(
        title_hu="Egyetértő bólintás",
        modern_hu_text='Azt mondta: „Nincs mit hozzátenni.” Egy barátja egyetértően bólintott.',
        moral_hu="Néha a hallgatás is válasz.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"


def test_prompt_explicitly_forbids_name_completion() -> None:
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1,
        source_id=1,
        title_original="Test",
        original_text="Pope said something witty.",
        source_code="TEST",
        tradition="test tradition",
    )
    prompt = build_enrichment_prompt(story, expected_mode="direct_unit")
    assert "NÉV-KIEGÉSZÍTÉS TILALMA" in prompt
    assert "Alexander Pope" in prompt  # the concrete example must be present
    assert "title_hu" in prompt.split("NÉV-KIEGÉSZÍTÉS TILALMA")[1][:200]


def test_prompt_explicitly_states_narrative_status_provenance_discipline() -> None:
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1,
        source_id=1,
        title_original="Test",
        original_text="Voltaire said something witty.",
        source_code="TEST",
        tradition="test tradition",
    )
    prompt = build_enrichment_prompt(story, expected_mode="direct_unit")
    assert "NARRATIVE_STATUS FORRÁS-FEGYELEM" in prompt
    assert "Rohan" in prompt  # the concrete Voltaire/Rohan cautionary example
    assert "KIZÁRÓLAG" in prompt.split("NARRATIVE_STATUS FORRÁS-FEGYELEM")[1][:300]


def test_prompt_name_completion_rule_applies_to_all_four_text_fields() -> None:
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1, source_id=1, title_original="Test", original_text="X.", source_code="TEST", tradition=None
    )
    prompt = build_enrichment_prompt(story, expected_mode="direct_unit")
    rule_section = prompt.split("NÉV-KIEGÉSZÍTÉS TILALMA")[1][:200]
    for field_name in ("title_hu", "modern_hu_text", "summary_hu", "moral_hu"):
        assert field_name in rule_section


def test_prompt_states_moral_hu_is_optional() -> None:
    """Phase 3G-B3: the prompt must explicitly tell the model not to
    fabricate a moral for a story that has no natural one."""
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1, source_id=1, title_original="Test", original_text="X.", source_code="TEST", tradition=None
    )
    prompt = build_enrichment_prompt(story, expected_mode="direct_unit")
    assert "OPCIONÁLIS" in prompt
    assert "moral_hu" in prompt
    moral_section = prompt.split("MORAL_HU SZABÁLYOK")[1][:600]
    assert "Ne gyárts erkölcsi tanulságot" in moral_section
    assert "null" in moral_section


# ---------------------------------------------------------------------------
# Conservative narrative_status classification (post Phase 3C-b review):
# "real historical person + old anecdote + punchline + unverifiable" must
# NOT by itself justify legend_about_historical_figure — the pipeline
# cannot verify a semantic classification judgment in code, so what IS
# testable and enforced here is that the prompt itself states the rule,
# the English-Jests-specific conservative default, and the Baldwin
# caution explicitly.
# ---------------------------------------------------------------------------


def test_prompt_requires_explicit_evidence_for_legend_classification() -> None:
    """The exact scenario from the Phase 3C-b review: PG_ENGLISH_JESTS_AND_ANECDOTES
    + a real historical figure + a punchline-driven, unverifiable anecdote
    must NOT default to legend_about_historical_figure absent explicit
    source/provenance evidence of legendary status — the prompt must state
    this, and must name traditional_anecdote as the conservative fallback."""
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1,
        source_id=1,
        title_original="Justice",
        original_text=(
            "A French nobleman, who had been satirized by Voltaire, meeting "
            "the poet soon after, gave him a hearty drubbing."
        ),
        source_code="PG_ENGLISH_JESTS_AND_ANECDOTES",
        tradition="angol anekdota/humor",
    )
    prompt = build_enrichment_prompt(story, expected_mode="direct_unit")

    legend_rule = prompt.split("legend_about_historical_figure ÉRTÉK HASZNÁLATÁNAK FELTÉTELE")[1][:900]
    assert "legendary" in legend_rule or "legend" in legend_rule
    assert "valós történelmi személy" in legend_rule
    assert "csattanója" in legend_rule
    assert "NEM legendát" in legend_rule

    assert "PG_ENGLISH_JESTS_AND_ANECDOTES" in prompt
    fallback_defaults = prompt.split("NARRATIVE_STATUS FORRÁS-TUDATOS ALAPÉRTELMEZÉSEK")[1][:600]
    assert "traditional_anecdote" in fallback_defaults


def test_prompt_baldwin_caution_present_and_not_automatic_legend() -> None:
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1,
        source_id=1,
        title_original="King Alfred and the Cakes",
        original_text="There was once a king named Alfred.",
        source_code="PG_BALDWIN_FIFTY_FAMOUS_STORIES_RETOLD",
        tradition="nyugati történelmi/legendás elbeszélés",
    )
    prompt = build_enrichment_prompt(story, expected_mode="direct_unit")
    start = prompt.find("James Baldwin")
    baldwin_section = " ".join(prompt[start : start + 900].split())
    assert "NEM jelenti azt, hogy MINDEN" in baldwin_section
    assert "low" in baldwin_section and "medium" in baldwin_section


def test_conservative_fallback_no_longer_lists_legend_as_default_option() -> None:
    """The old provenance-discipline text offered 'traditional_anecdote
    VAGY legend_about_historical_figure' as the two acceptable
    conservative fallbacks when evidence is insufficient — legend must
    no longer be presented as an acceptable no-evidence fallback."""
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1, source_id=1, title_original="T", original_text="X.", source_code="TEST", tradition=None
    )
    prompt = build_enrichment_prompt(story, expected_mode="direct_unit")
    fegyelem_section = prompt.split("NARRATIVE_STATUS FORRÁS-FEGYELEM")[1]
    fallback_line = fegyelem_section.split("KONZERVATÍV alapértelmezés")[1][:300]
    assert "traditional_anecdote" in fallback_line
    assert "hacsak a fenti explicit provenance-feltétel nem teljesül" in fallback_line


# ---------------------------------------------------------------------------
# Phase 3C-c: two-tier proper-noun guard (HARD REJECT vs WARNING)
# ---------------------------------------------------------------------------

_POPE_SWIFT_SOURCE_TEXT = (
    "Swift once wrote a letter of recommendation to Pope on behalf of a "
    "gentleman of excellent character."
)


def test_name_completion_pope_to_alexander_pope_is_suspicious_warning_not_reject() -> None:
    """Source only ever writes the bare surname 'Pope' -- an output that
    completes it with an invented given name is the canonical
    name-completion hallucination shape. Phase 3D.1: the untouched
    25-story pilot found this SAME adjacency shape also fires on
    genuinely correct translations ('Ádámnak Lumley', 'North
    Írországgal'), so it can no longer hard-reject by itself -- it now
    surfaces as a high-priority SUSPICIOUS NAME EXPANSION warning
    (silent pass is explicitly NOT acceptable either), and the unit still
    reaches needs_review for a human to make the actual call."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_POPE_SWIFT_SOURCE_TEXT)
    payload = _valid_direct_unit_payload(
        modern_hu_text="Swift ajánlólevelet írt Alexander Pope-nak egy kiváló jellemű úriemberről."
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert not result.errors
    assert any("SUSPICIOUS NAME EXPANSION" in w and "Alexander" in w for w in result.warnings)


def test_name_completion_swift_to_jonathan_swift_is_suspicious_warning_not_reject() -> None:
    """Same pattern, reversed roles: 'Swift' kept bare in source, output
    completes it to 'Jonathan Swift'. Deliberately phrased so 'Jonathan'
    is NOT sentence-initial (a separate, documented, accepted guard
    limitation — see _hallucination_guard's docstring — not what this
    test is checking). Same Phase 3D.1 downgrade as the Pope test above:
    warning, not rejection."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_POPE_SWIFT_SOURCE_TEXT)
    payload = _valid_direct_unit_payload(
        modern_hu_text="Egyszer Jonathan Swift ajánlólevelet írt Pope-nak egy kiváló jellemű úriemberről."
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert not result.errors
    assert any("SUSPICIOUS NAME EXPANSION" in w and "Jonathan" in w for w in result.warnings)


@pytest.mark.parametrize(
    ("source_text", "hungarian_word"),
    [
        ("A person announced to Nushirowan the Just, saying that God had removed his enemy.", "Isten"),
        ("May the Lord take the Bishop, and the Devil have his Due.", "Ördög"),
        ("There lived in England a wise and good king named Alfred.", "Anglia"),
        ("James came from Scotland to England to become king.", "Skócia"),
    ],
)
def test_translated_exonym_is_warning_not_hard_reject(source_text: str, hungarian_word: str) -> None:
    """A correct Hungarian translation of a source concept (God->Isten,
    Devil->Ördög, England->Anglia, Scotland->Skócia) has no source token
    it could prefix-match (different word entirely, not a transliteration)
    and stands alone (no adjacent matched candidate) -- per the Phase
    3C-c brief, this must warn, not hard-reject, and must not block
    persistence."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=source_text)
    # title_hu/moral_hu deliberately overridden away from
    # _valid_direct_unit_payload's defaults ("Lord Kenyon a színházban" /
    # a "Sheridan/Lord Kenyon" moral) -- those defaults contain their OWN
    # capitalized words ("Lord") that would coincidentally source-match
    # against some of this test's custom source_text values and produce
    # an unrelated, confusing adjacency finding that has nothing to do
    # with what this test checks. Same class of test-authoring mistake
    # documented earlier in this file's history — avoided here up front.
    payload = _valid_direct_unit_payload(
        title_hu="Rövid tanmese",
        modern_hu_text=f"Ez a történet {hungarian_word} szerepét emeli ki egy rövid tanmesében.",
        moral_hu="A tanmese egyszerű, alázatos tanulságot hordoz.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert any(hungarian_word in w for w in result.warnings)
    assert not result.errors


def test_enrichment_result_warnings_default_to_empty_tuple() -> None:
    """A clean enrichment with no guard findings at all must still expose
    an (empty) warnings tuple, not None or a missing attribute -- callers
    should be able to always iterate result.warnings unconditionally."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    payload = _valid_direct_unit_payload()
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert result.warnings == ()


# ---------------------------------------------------------------------------
# Schema v4: enrichment_warnings_json persistence (Phase 3C-c follow-up)
# ---------------------------------------------------------------------------

_NUSHIROWAN_SOURCE_TEXT = (
    "A person announced to Nushirowan the Just, saying that God had removed his enemy."
)


def test_warning_persists_to_db_after_direct_unit_enrichment() -> None:
    """The God->Isten warning must not be just a return-value artifact --
    a human reviewer looking at this unit LATER (a fresh get_unit() call,
    no access to the original EnrichmentResult) must still be able to see
    it."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_NUSHIROWAN_SOURCE_TEXT)
    payload = _valid_direct_unit_payload(
        title_hu="Rövid tanmese",
        modern_hu_text="Ez a történet Isten szerepét emeli ki egy rövid tanmesében.",
        moral_hu="A tanmese egyszerű, alázatos tanulságot hordoz.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.commit()
    unit = get_unit(conn, result.unit_id)
    conn.close()

    assert result.status == "unit_created"
    assert unit.status == "needs_review"
    assert any("Isten" in w for w in unit.enrichment_warnings)
    assert unit.enrichment_warnings == result.warnings


def test_no_warning_enrichment_writes_null_column() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(_valid_direct_unit_payload()),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    raw_column = conn.execute(
        "SELECT enrichment_warnings_json FROM illustration_units WHERE id = ?", (result.unit_id,)
    ).fetchone()[0]
    unit = get_unit(conn, result.unit_id)
    conn.close()

    assert result.status == "unit_created"
    assert raw_column is None
    assert unit.enrichment_warnings == ()


def test_rerun_replaces_warnings_does_not_accumulate() -> None:
    """First run warns about 'Isten'; second run (same unit_index, so an
    idempotent rerun of the SAME unit) warns about a DIFFERENT, unrelated
    invented name and never mentions 'Isten' at all. The final state must
    contain ONLY the second run's warning -- if the two were being
    accumulated instead of replaced, 'Isten' would still be present."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_NUSHIROWAN_SOURCE_TEXT)

    first = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Első cím",
            modern_hu_text="Ez a történet Isten szerepét emeli ki.",
            moral_hu="Első tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    first_unit = get_unit(conn, first.unit_id)
    assert any("Isten" in w for w in first_unit.enrichment_warnings)

    second = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Második cím",
            modern_hu_text="Ez a történet Zoltanovics Bélának a bölcsességéről szól.",
            moral_hu="Második tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    second_unit = get_unit(conn, second.unit_id)
    conn.close()

    assert second.status == "unit_created"
    assert second.unit_id == first.unit_id  # same unit (unit_index defaults to 1 both times)
    assert not any("Isten" in w for w in second_unit.enrichment_warnings)
    assert any("Zoltanovics" in w or "Bélának" in w for w in second_unit.enrichment_warnings)


def test_warned_rerun_then_clean_rerun_clears_warning_to_null() -> None:
    """First run warns about 'Isten'; second run's Hungarian text has no
    guard findings at all -- the column must become NULL again, not keep
    showing the stale warning from the first run."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_NUSHIROWAN_SOURCE_TEXT)

    first = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Első cím",
            modern_hu_text="Ez a történet Isten szerepét emeli ki.",
            moral_hu="Első tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    assert any("Isten" in w for w in get_unit(conn, first.unit_id).enrichment_warnings)

    second = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Tiszta cím",
            modern_hu_text="Nushirowannak elmondták, hogy elhunyt egyik ellenfele.",
            moral_hu="Tiszta tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    raw_column = conn.execute(
        "SELECT enrichment_warnings_json FROM illustration_units WHERE id = ?", (second.unit_id,)
    ).fetchone()[0]
    second_unit = get_unit(conn, second.unit_id)
    conn.close()

    assert second.status == "unit_created"
    assert raw_column is None
    assert second_unit.enrichment_warnings == ()


def test_atomic_rollback_preserves_prior_warnings_on_rerun_failure(monkeypatch) -> None:
    """Same atomicity guarantee as
    test_atomic_rollback_preserves_prior_content_on_idempotent_rerun_failure,
    explicitly checked for enrichment_warnings: a second run that would
    have introduced a DIFFERENT set of findings, but fails mid-sequence,
    must leave the first run's warning state completely untouched --
    neither wiped to NULL nor partially applied."""
    import illustration_engine.enrichment_pipeline as pipeline_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_NUSHIROWAN_SOURCE_TEXT)

    first = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Eredeti cím",
            modern_hu_text="Ez a történet Isten szerepét emeli ki.",
            moral_hu="Eredeti tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    before = get_unit(conn, first.unit_id)
    assert any("Isten" in w for w in before.enrichment_warnings)

    def failing_mark_needs_review(*args, **kwargs):
        raise RuntimeError("simulated failure after content+warning update")

    monkeypatch.setattr(pipeline_module, "mark_needs_review", failing_mark_needs_review)

    second = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Félbeszakadt frissítés",
            modern_hu_text="Nushirowannak elmondták, hogy elhunyt egyik ellenfele.",
            moral_hu="Új tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    after = get_unit(conn, first.unit_id)
    conn.close()

    assert second.status == "rejected"
    assert after == before
    assert after.enrichment_warnings == before.enrichment_warnings
    assert any("Isten" in w for w in after.enrichment_warnings)  # still the FIRST run's warning


def test_human_reviewed_protection_blocks_rerun_even_with_new_warnings() -> None:
    """The existing Phase 3A/3B human-review protection must keep working
    unchanged: an approved unit's content (and, by extension, its
    warnings -- they always travel together in the same update_draft_unit
    call) cannot be silently overwritten by a rerun, even one that would
    introduce a brand-new warning."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_NUSHIROWAN_SOURCE_TEXT)

    first = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Jóváhagyott cím",
            modern_hu_text="Nushirowannak elmondták, hogy elhunyt egyik ellenfele.",
            moral_hu="Jóváhagyott tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    approve_unit(conn, first.unit_id)
    conn.commit()
    before = get_unit(conn, first.unit_id)
    assert before.enrichment_warnings == ()  # the approved run itself had no warnings

    second = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Új próbálkozás",
            modern_hu_text="Ez a történet Isten szerepét emeli ki.",
            moral_hu="Új tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    after = get_unit(conn, first.unit_id)
    conn.close()

    assert second.status == "rejected"
    assert any("human-reviewed" in e for e in second.errors)
    assert after == before
    assert after.enrichment_warnings == ()  # NOT overwritten with the rejected run's "Isten" warning


def test_approve_and_publish_do_not_clear_warning_provenance() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)  # default license_status is publishable
    story_id = _make_story(conn, source_id, original_text=_NUSHIROWAN_SOURCE_TEXT)

    result = enrich_story(
        conn, story_id=story_id,
        llm_generate=_llm(_valid_direct_unit_payload(
            title_hu="Rövid tanmese",
            modern_hu_text="Ez a történet Isten szerepét emeli ki.",
            moral_hu="Alázatos tanulság.",
        )),
        model_identifier="m", expected_mode="direct_unit",
    )
    conn.commit()
    before_review = get_unit(conn, result.unit_id)
    assert any("Isten" in w for w in before_review.enrichment_warnings)

    approve_unit(conn, result.unit_id)
    conn.commit()
    after_approve = get_unit(conn, result.unit_id)
    assert after_approve.status == "approved"
    assert after_approve.enrichment_warnings == before_review.enrichment_warnings

    publish_unit(conn, result.unit_id)
    conn.commit()
    after_publish = get_unit(conn, result.unit_id)
    conn.close()

    assert after_publish.status == "published"
    assert after_publish.enrichment_warnings == before_review.enrichment_warnings


# ---------------------------------------------------------------------------
# Phase 3C-c: unit_proposal contract no longer generates modern_hu_text
# ---------------------------------------------------------------------------


def _valid_proposal_unit(**overrides) -> dict:
    unit = {
        "derivation_type": "extracted_scene",
        "source_span_start": 0,
        "source_span_end": 10,
        "title_hu": "Egy jelenet",
        "summary_hu": _VALID_SUMMARY,
        "topics": ["eszesseg"],
        "tone": "humoros",
        "homiletic_functions": ["szemlelteto_pelda"],
        "narrative_status": "traditional_anecdote",
        "narrative_status_confidence": "medium",
        "rationale": "Önmagában érthető jelenet.",
        "standalone_reason": "Nem igényli a többi rész ismeretét.",
    }
    unit.update(overrides)
    return unit


def test_proposal_does_not_require_modern_hu_text_or_moral_hu() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_LONG_SOURCE_TEXT)
    payload = {"mode": "unit_proposal", "proposed_units": [_valid_proposal_unit()]}
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal"
    )
    conn.close()
    assert result.status == "proposal_ready"
    assert result.proposed_units[0].modern_hu_text is None
    assert result.proposed_units[0].moral_hu is None


def test_proposal_still_requires_title_and_summary() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_LONG_SOURCE_TEXT)
    payload = {
        "mode": "unit_proposal",
        "proposed_units": [_valid_proposal_unit(summary_hu="")],
    }
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal"
    )
    conn.close()
    assert result.status == "rejected"
    assert any("summary_hu" in e for e in result.errors)


def _condensed_story_payload(target_length_chars) -> dict:
    return {
        "mode": "unit_proposal",
        "proposed_units": [
            _valid_proposal_unit(
                derivation_type="condensed_story",
                source_span_start=None,
                source_span_end=None,
                rationale=None,
                standalone_reason=None,
                target_length_chars=target_length_chars,
            )
        ],
    }


@pytest.mark.parametrize(
    ("target_length_chars", "expected_status"),
    [
        (199, "rejected"),   # one under the floor
        (200, "proposal_ready"),  # exactly the floor
        (1500, "proposal_ready"),  # exactly the ceiling
        (1501, "rejected"),  # one over the ceiling
    ],
)
def test_condensed_story_target_length_chars_range_boundaries(
    target_length_chars: int, expected_status: str
) -> None:
    """A retrieval-ready illustration unit is meant to be short and
    directly tellable -- 'shorter than the source' alone let a 6000-char
    source pair with a 5800-char 'condensed' proposal, effectively no
    condensing at all. target_length_chars must additionally sit in
    [200, 1500], on top of (unconditionally) being shorter than the
    source. _LONG_SOURCE_TEXT (3500 chars) is long enough that every
    value tested here is already 'shorter than source' -- this test is
    isolating the range check alone, not the shorter-than-source check
    (see test_condensed_story_proposal_target_length_must_be_shorter_than_source
    for that one)."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_LONG_SOURCE_TEXT)
    payload = _condensed_story_payload(target_length_chars)
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal"
    )
    conn.close()
    assert result.status == expected_status
    if expected_status == "rejected":
        assert any("target_length_chars" in e for e in result.errors)


def test_condensed_story_proposal_target_length_must_be_shorter_than_source() -> None:
    """target_length_chars=250 is comfortably inside [200, 1500], so this
    isolates the SEPARATE 'must actually be shorter than the source'
    check. Phase 3D.1 note: since derive_enrichment_strategy() only ever
    routes a story to unit_proposal once its source exceeds 3000 chars,
    and target_length_chars is capped at 1500, this specific combination
    (target_length_chars >= source length) can no longer occur through
    the normal enrich_story() entry point -- it is exercised here by
    calling the internal _handle_unit_proposal() handler directly against
    a short, hand-built _LoadedStory, bypassing the length-strategy gate,
    so the underlying validation logic itself still has real coverage."""
    from illustration_engine.enrichment_pipeline import _handle_unit_proposal, _LoadedStory

    story = _LoadedStory(
        id=1, source_id=1, title_original="T", original_text="A" * 148,
        source_code="TEST", tradition=None,
    )
    raw_response = _llm(_condensed_story_payload(250))("prompt")
    payload = json.loads(raw_response)
    result = _handle_unit_proposal(story=story, payload=payload, raw_response=raw_response)
    assert result.status == "rejected"
    assert any("target_length_chars" in e and "shorter" in e for e in result.errors)


def test_extracted_scene_proposal_must_not_set_target_length_chars() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_LONG_SOURCE_TEXT)
    payload = {
        "mode": "unit_proposal",
        "proposed_units": [_valid_proposal_unit(target_length_chars=50)],
    }
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal"
    )
    conn.close()
    assert result.status == "rejected"
    assert any("target_length_chars" in e for e in result.errors)


def test_proposal_prompt_no_longer_requests_modern_hu_text_or_moral_hu() -> None:
    from illustration_engine.enrichment_pipeline import _LoadedStory

    story = _LoadedStory(
        id=1, source_id=1, title_original="T",
        original_text="A" * 5000, source_code="TEST", tradition=None,
    )
    prompt = build_enrichment_prompt(story, expected_mode="unit_proposal")
    # Colon-anchored: matches only an actual JSON key ('"modern_hu_text":'),
    # not the prose reminder further down that legitimately names the
    # field while explaining it must be absent (Hungarian suffix attaches
    # directly to the closing quote there, never followed by a colon).
    assert '"modern_hu_text":' not in prompt
    assert '"moral_hu":' not in prompt
    assert "target_length_chars" in prompt


# ---------------------------------------------------------------------------
# Phase 3D.1: deterministic length strategy + warning-only proper-name guard
# ---------------------------------------------------------------------------


def test_derive_enrichment_strategy_boundaries() -> None:
    strategy_1400 = derive_enrichment_strategy(1400)
    assert strategy_1400.expected_mode == "direct_unit"
    assert strategy_1400.expected_derivation_type == "full_story_translation"

    strategy_1500 = derive_enrichment_strategy(1500)
    assert strategy_1500.expected_derivation_type == "full_story_translation"

    strategy_1501 = derive_enrichment_strategy(1501)
    assert strategy_1501.expected_mode == "direct_unit"
    assert strategy_1501.expected_derivation_type == "condensed_story"

    strategy_2000 = derive_enrichment_strategy(2000)
    assert strategy_2000.expected_mode == "direct_unit"
    assert strategy_2000.expected_derivation_type == "condensed_story"

    strategy_3000 = derive_enrichment_strategy(3000)
    assert strategy_3000.expected_derivation_type == "condensed_story"

    strategy_3001 = derive_enrichment_strategy(3001)
    assert strategy_3001.expected_mode == "unit_proposal"
    assert strategy_3001.expected_derivation_type is None

    strategy_3500 = derive_enrichment_strategy(3500)
    assert strategy_3500.expected_mode == "unit_proposal"


_CONDENSED_BAND_SOURCE_TEXT = (
    "Sheridan told a long and detailed story about London for many hours. " * 30
)[:2000]


def _padded_hungarian_text(char_count: int) -> str:
    filler = "Ez egy hosszú, tömörített illusztráció szövege. "
    return (filler * (char_count // len(filler) + 1))[:char_count]


def test_condensed_band_modern_hu_text_over_1500_chars_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_CONDENSED_BAND_SOURCE_TEXT)
    payload = _valid_direct_unit_payload(
        derivation_type="condensed_story", modern_hu_text=_padded_hungarian_text(1700)
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "rejected"
    assert any("condensed_story modern_hu_text must be" in e for e in result.errors)


def test_condensed_band_modern_hu_text_within_range_accepted() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text=_CONDENSED_BAND_SOURCE_TEXT)
    payload = _valid_direct_unit_payload(
        derivation_type="condensed_story", modern_hu_text=_padded_hungarian_text(1000)
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"


def test_3500_char_source_accepts_unit_proposal() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="A" * 3500)
    payload = _condensed_story_payload(500)
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="unit_proposal"
    )
    conn.close()
    assert result.status == "proposal_ready"


def test_derivation_type_mismatch_rejected_with_zero_db_write() -> None:
    """The LLM no longer freely picks between the two direct_unit
    derivation types -- for a short (band-A) story, ONLY
    full_story_translation is valid; sending condensed_story instead is a
    contract violation, same severity as an expected_mode mismatch."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)  # default ORIGINAL_TEXT, 148 chars -> band A
    payload = _valid_direct_unit_payload(derivation_type="condensed_story")
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    units = conn.execute("SELECT COUNT(*) FROM illustration_units WHERE story_id = ?", (story_id,)).fetchone()[0]
    conn.close()
    assert result.status == "rejected"
    assert any("derivation_type must be" in e for e in result.errors)
    assert units == 0


def test_caller_expected_mode_mismatch_does_not_call_llm() -> None:
    """A caller-supplied expected_mode that disagrees with what
    derive_enrichment_strategy() computes from the story's length is a
    configuration error caught BEFORE llm_generate is invoked at all --
    no tokens spent, no raw_response, no DB write."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)  # 148 chars -> band A -> direct_unit

    calls: list[str] = []

    def spy_llm(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps(_valid_direct_unit_payload())

    result = enrich_story(
        conn, story_id=story_id, llm_generate=spy_llm, model_identifier="m", expected_mode="unit_proposal"
    )
    units = conn.execute("SELECT COUNT(*) FROM illustration_units WHERE story_id = ?", (story_id,)).fetchone()[0]
    conn.close()
    assert result.status == "rejected"
    assert calls == []
    assert result.unit_id is None
    assert units == 0
    assert any("does not match the length-derived strategy" in e for e in result.errors)


def test_caller_expected_mode_mismatch_other_direction_does_not_call_llm() -> None:
    """Same check, opposite direction: a long (unit_proposal-band) story
    called with expected_mode="direct_unit" must also be rejected before
    the LLM is called."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="A" * 3500)  # unit_proposal band

    calls: list[str] = []

    def spy_llm(prompt: str) -> str:
        calls.append(prompt)
        return "{}"

    result = enrich_story(
        conn, story_id=story_id, llm_generate=spy_llm, model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "rejected"
    assert calls == []


def test_diacritic_folding_adam_to_adam_accented_no_warning() -> None:
    """Phase 3D.1: 'Ádám' (correct Hungarian) must no longer warn purely
    because of the accent difference from the ASCII source word 'Adam'."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn, source_id, original_text="A person announced that Adam was the first man created."
    )
    payload = _valid_direct_unit_payload(
        title_hu="Cím",
        modern_hu_text="A történet Ádámról szól, az első teremtett emberről.",
        moral_hu="Tanulság.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert not any("dám" in w for w in result.warnings)


def test_diacritic_folding_orleans_to_orleans_accented_no_warning() -> None:
    """Phase 3D.1: 'Orléans' (correct Hungarian spelling) must no longer
    warn purely because of the accent difference from the ASCII source
    word 'Orleans' -- this is the exact case that produced the only
    warning in the Phase 3D untouched 5-story smoke pilot."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn, source_id, original_text="The Duke of Orleans received the poet warmly."
    )
    payload = _valid_direct_unit_payload(
        title_hu="Cím",
        modern_hu_text="Az Orléans-i herceg szívélyesen fogadta a költőt.",
        moral_hu="Tanulság.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert not any("rléans" in w for w in result.warnings)


def test_diacritic_folding_does_not_suppress_genuine_semantic_translation_warnings() -> None:
    """Guard rail for the folding fix itself: János/Anglia/Isten share no
    letters with john/england/god even after diacritic folding, so they
    must keep warning exactly as before -- folding is normalization, not
    a translation dictionary."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn, source_id, original_text="A person announced to the king that God had blessed England."
    )
    payload = _valid_direct_unit_payload(
        title_hu="Cím",
        modern_hu_text="Egy ember azt mondta a királynak, hogy Isten megáldotta Angliát.",
        moral_hu="Tanulság.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert any("Isten" in w for w in result.warnings)
    assert any("Angli" in w for w in result.warnings)


def test_987_style_adamnak_lumley_not_hard_reject() -> None:
    """Reproduces the exact Phase 3D untouched-pilot false-reject shape:
    a correct biblical-name translation ('Ádámnak') sitting, by ordinary
    sentence word order, right next to a real matched source surname
    ('Lumley') -- must no longer block persistence."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn,
        source_id,
        original_text="The king visited Lumley Castle and admired the portraits of the family.",
    )
    payload = _valid_direct_unit_payload(
        title_hu="Családfa",
        modern_hu_text=(
            "A király meglátogatta Lumley kastélyát, és azt mondta, hogy eddig nem "
            "tudta, hogy Ádámnak Lumley volt a vezetékneve."
        ),
        moral_hu="Tanulság.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert not result.errors


def test_1575_style_north_irorszaggal_not_hard_reject() -> None:
    """Reproduces the second Phase 3D untouched-pilot false-reject shape:
    a correct place-name translation ('Írországgal') sitting right after
    a real matched source surname ('North') -- must no longer block
    persistence, but should still surface as a suspicious-adjacency
    warning for a human to look at first."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn, source_id, original_text="Lord North brought forward new measures relating to Ireland."
    )
    payload = _valid_direct_unit_payload(
        title_hu="Cím",
        modern_hu_text="Lord North Írországgal kapcsolatos javaslatokat terjesztett elő.",
        moral_hu="Tanulság.",
    )
    result = enrich_story(
        conn, story_id=story_id, llm_generate=_llm(payload), model_identifier="m", expected_mode="direct_unit"
    )
    conn.close()
    assert result.status == "unit_created"
    assert not result.errors
    assert any("SUSPICIOUS NAME EXPANSION" in w for w in result.warnings)
