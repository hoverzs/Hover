from __future__ import annotations

import json
import sqlite3

import pytest

from illustration_engine.enrichment_batch import (
    BatchRunSummary,
    EnrichmentRunAlreadyRunningError,
    RunItemView,
    RunView,
    create_run,
    get_run,
    list_run_items,
    mark_run_interrupted,
    run_batch,
)
from illustration_engine.illustration_sqlite import (
    create_schema,
    insert_source,
    insert_story,
    update_enrichment_run as raw_update_run,
    update_enrichment_run_item as raw_update_run_item,
)
from illustration_engine.illustration_unit_repository import approve_unit, get_unit


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _make_source(conn: sqlite3.Connection, *, code: str = "SRC") -> int:
    return insert_source(
        conn,
        code=code,
        title="Test Source",
        orig_language="en",
        license_status="public_domain_confirmed",
        license_basis_hu="test basis",
        reliability_tier="high",
        tradition="test tradition",
    )


def _make_story(
    conn: sqlite3.Connection, source_id: int, *, external_ref: str, original_text: str
) -> int:
    return insert_story(
        conn,
        source_id=source_id,
        external_ref=external_ref,
        canonical_key=f"key-{external_ref}",
        title_original=f"Title {external_ref}",
        adaptation_status="verbatim_transcription",
        original_text=original_text,
    )


_VALID_SUMMARY = " ".join(["szo"] * 45)


def _direct_unit_payload(**overrides) -> dict:
    unit = {
        "derivation_type": "full_story_translation",
        "title_hu": "Cím",
        "modern_hu_text": "Ez egy rövid magyar szöveg.",
        "summary_hu": _VALID_SUMMARY,
        "moral_hu": "Tanulság.",
        "topics": ["eszesseg"],
        "tone": "humoros",
        "homiletic_functions": ["szemlelteto_pelda"],
        "narrative_status": "traditional_anecdote",
        "narrative_status_confidence": "medium",
    }
    unit.update(overrides)
    return {"mode": "direct_unit", "unit": unit}


def _proposal_payload(**overrides) -> dict:
    unit = {
        "derivation_type": "condensed_story",
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
    unit.update(overrides)
    return {"mode": "unit_proposal", "proposed_units": [unit]}


def _fixed_llm(payload: dict):
    return lambda prompt: json.dumps(payload)


def _seed_short_stories(conn: sqlite3.Connection, source_id: int, count: int, *, code_prefix: str = "s") -> list[int]:
    """Band-A stories (well under 1500 chars), Sheridan/London themed to
    stay guard-safe with the default payload."""
    story_ids = []
    for i in range(count):
        story_ids.append(
            _make_story(
                conn,
                source_id,
                external_ref=f"{code_prefix}{i}",
                original_text=f"Sheridan told a short story number {i} about London.",
            )
        )
    return story_ids


# ---------------------------------------------------------------------------
# create_run: run + item ledger creation, deterministic selection
# ---------------------------------------------------------------------------


def test_create_run_creates_run_and_pending_items() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_ids = _seed_short_stories(conn, source_id, 3)
    conn.commit()

    run_id = create_run(
        conn, model_identifier="mock-model", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10
    )
    run = get_run(conn, run_id)
    items = list_run_items(conn, run_id)
    conn.close()

    assert isinstance(run, RunView)
    assert run.overall_status == "created"
    assert run.model_identifier == "mock-model"
    assert run.prompt_version == "v1"
    assert run.source_code == "SRC"
    assert run.strategy_band == "A"
    assert run.requested_limit == 10
    assert len(items) == 3
    assert all(isinstance(item, RunItemView) for item in items)
    assert all(item.status == "pending" for item in items)
    assert all(item.expected_mode == "direct_unit" for item in items)
    assert [item.story_id for item in items] == story_ids


def test_create_run_selection_is_deterministic_by_story_id_ascending_and_band() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    # Mix of bands: two band-A (short), one band-C (long), inserted out of
    # story_id-relevant order to confirm the query itself sorts, not
    # insertion order.
    short_a = _make_story(conn, source_id, external_ref="a", original_text="Short story about Sheridan.")
    long_c = _make_story(conn, source_id, external_ref="b", original_text="X" * 3500)
    short_b = _make_story(conn, source_id, external_ref="c", original_text="Another short Sheridan story.")
    conn.commit()

    run_id = create_run(
        conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10
    )
    items = list_run_items(conn, run_id)
    conn.close()

    assert [item.story_id for item in items] == sorted([short_a, short_b])
    assert long_c not in [item.story_id for item in items]


def test_create_run_respects_limit() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 5)
    conn.commit()

    run_id = create_run(
        conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=2
    )
    items = list_run_items(conn, run_id)
    conn.close()

    assert len(items) == 2


def test_create_run_selection_metadata_reproducible() -> None:
    """The exact story_id list is frozen into selection_metadata_json at
    creation time -- a caller (or auditor) can read back precisely what
    this run covers without re-running the selection query."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_ids = _seed_short_stories(conn, source_id, 3)
    conn.commit()

    run_id = create_run(
        conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10
    )
    run = get_run(conn, run_id)
    conn.close()

    metadata = json.loads(run.selection_metadata_json)
    assert metadata["story_ids"] == story_ids


def test_create_run_rejects_invalid_band() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="Z", limit=10)
    conn.close()


def test_create_run_rejects_non_positive_limit() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=0)
    conn.close()


# ---------------------------------------------------------------------------
# run_batch: outcome mapping (success / warning / rejected / proposal_ready)
# ---------------------------------------------------------------------------


def test_run_batch_success_item() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    items = list_run_items(conn, run_id)
    conn.close()

    assert summary.success_count == 1
    assert summary.overall_status == "completed"
    assert items[0].status == "success"
    assert items[0].illustration_unit_id is not None
    assert items[0].warnings == ()
    assert items[0].error_message is None


def test_run_batch_warning_item() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn, source_id, external_ref="w", original_text="A person announced that God had blessed the land."
    )
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    payload = _direct_unit_payload(modern_hu_text="Valaki azt mondta, hogy Isten megáldotta a földet.")
    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(payload))
    items = list_run_items(conn, run_id)
    conn.close()

    assert summary.warning_count == 1
    assert summary.overall_status == "completed"  # warnings alone do not count as errors
    assert items[0].status == "warning"
    assert items[0].illustration_unit_id is not None
    assert any("Isten" in w for w in items[0].warnings)


def test_run_batch_rejected_item_creates_zero_units() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    # Wrong derivation_type for a band-A story -> deterministic contract rejection.
    payload = _direct_unit_payload(derivation_type="condensed_story")
    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(payload))
    items = list_run_items(conn, run_id)
    unit_count = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    conn.close()

    assert summary.rejected_count == 1
    assert summary.overall_status == "completed_with_errors"
    assert items[0].status == "rejected"
    assert items[0].illustration_unit_id is None
    assert items[0].error_message is not None
    assert unit_count == 0


def test_run_batch_proposal_ready_persists_zero_units() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, external_ref="long", original_text="X" * 3500)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="C", limit=10)

    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_proposal_payload()))
    items = list_run_items(conn, run_id)
    unit_count = conn.execute("SELECT COUNT(*) FROM illustration_units WHERE story_id = ?", (story_id,)).fetchone()[0]
    conn.close()

    assert summary.proposal_ready_count == 1
    assert summary.overall_status == "completed"
    assert items[0].status == "proposal_ready"
    assert items[0].illustration_unit_id is None
    assert unit_count == 0


# ---------------------------------------------------------------------------
# Fault isolation: exception -> failed, batch continues
# ---------------------------------------------------------------------------


def test_exception_marks_item_failed_and_batch_continues(monkeypatch) -> None:
    import illustration_engine.enrichment_batch as batch_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_ids = _seed_short_stories(conn, source_id, 3)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    call_count = {"n": 0}
    real_enrich_story = batch_module.enrich_story

    def flaky_enrich_story(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:  # fail exactly the second item
            raise RuntimeError("simulated provider crash")
        return real_enrich_story(*args, **kwargs)

    monkeypatch.setattr(batch_module, "enrich_story", flaky_enrich_story)

    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    items = list_run_items(conn, run_id)
    conn.close()

    assert summary.failed_count == 1
    assert summary.success_count == 2
    assert summary.overall_status == "completed_with_errors"
    assert call_count["n"] == 3  # all three items were attempted despite the middle failure
    statuses = {item.story_id: item.status for item in items}
    assert statuses[story_ids[1]] == "failed"
    assert statuses[story_ids[0]] == "success"
    assert statuses[story_ids[2]] == "success"
    failed_item = next(item for item in items if item.status == "failed")
    assert "simulated provider crash" in failed_item.error_message


def test_failed_item_leaves_no_partial_illustration_unit(monkeypatch) -> None:
    import illustration_engine.enrichment_batch as batch_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    def raising_enrich_story(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(batch_module, "enrich_story", raising_enrich_story)

    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    unit_count = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    conn.close()

    assert unit_count == 0


# ---------------------------------------------------------------------------
# Resume / retry semantics
# ---------------------------------------------------------------------------


def test_resume_skips_success_warning_and_proposal_items() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 2)
    long_id = _make_story(conn, source_id, external_ref="long", original_text="X" * 3500)
    conn.commit()

    run_a = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    run_batch(conn, run_id=run_a, llm_generate=_fixed_llm(_direct_unit_payload()))

    run_c = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="C", limit=10)
    run_batch(conn, run_id=run_c, llm_generate=_fixed_llm(_proposal_payload()))

    call_count = {"n": 0}
    real_llm = _fixed_llm(_direct_unit_payload())

    def counting_llm(prompt):
        call_count["n"] += 1
        return real_llm(prompt)

    # Second run_batch call on ALREADY-COMPLETED runs = a resume with
    # nothing eligible (all items success/proposal_ready) -- must call
    # the LLM zero times.
    summary_a = run_batch(conn, run_id=run_a, llm_generate=counting_llm)
    summary_c = run_batch(conn, run_id=run_c, llm_generate=counting_llm)
    conn.close()

    assert call_count["n"] == 0
    assert summary_a.processed_count == 0
    assert summary_a.skipped_count == 2
    assert summary_c.processed_count == 0
    assert summary_c.skipped_count == 1


def test_rejected_skipped_by_default_on_resume() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    bad_payload = _direct_unit_payload(derivation_type="condensed_story")
    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(bad_payload))

    call_count = {"n": 0}

    def counting_llm(prompt):
        call_count["n"] += 1
        return json.dumps(bad_payload)

    summary = run_batch(conn, run_id=run_id, llm_generate=counting_llm)
    conn.close()

    assert call_count["n"] == 0
    assert summary.skipped_count == 1
    assert summary.processed_count == 0


def test_retry_rejected_true_reprocesses_rejected_items() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    bad_payload = _direct_unit_payload(derivation_type="condensed_story")
    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(bad_payload))

    # Fix the payload for the retry -- this time it should succeed.
    good_payload = _direct_unit_payload()
    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(good_payload), retry_rejected=True)
    items = list_run_items(conn, run_id)
    conn.close()

    assert summary.processed_count == 1
    assert summary.success_count == 1
    assert items[0].status == "success"
    assert items[0].error_message is None  # stale rejection message cleared, not left stale


def test_retry_rejected_leaves_already_successful_items_completely_untouched() -> None:
    """Phase 3H.1 cohort-recovery scenario: a frozen run with a MIX of
    already-successful and rejected items -- retrying the rejected ones
    must not re-process, re-call the LLM for, or in any way alter the
    already-successful ones' unit content or ledger row."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 3)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    call_count = {"n": 0}

    def first_story_bad_llm(prompt: str) -> str:
        call_count["n"] += 1
        # First call (story 1, id ASC) gets an invalid derivation_type ->
        # rejected; the rest succeed normally.
        if call_count["n"] == 1:
            return json.dumps(_direct_unit_payload(derivation_type="condensed_story"))
        return json.dumps(_direct_unit_payload(title_hu=f"Cím {call_count['n']}"))

    run_batch(conn, run_id=run_id, llm_generate=first_story_bad_llm)
    items_before = list_run_items(conn, run_id)
    assert [i.status for i in items_before] == ["rejected", "success", "success"]
    successful_unit_ids = [i.illustration_unit_id for i in items_before if i.status == "success"]
    successful_titles_before = [get_unit(conn, uid).title_hu for uid in successful_unit_ids]

    calls_before_retry = call_count["n"]
    summary = run_batch(
        conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload(title_hu="Retried")), retry_rejected=True
    )
    items_after = list_run_items(conn, run_id)
    successful_titles_after = [get_unit(conn, uid).title_hu for uid in successful_unit_ids]
    conn.close()

    # Only the ONE rejected item was reprocessed -- exactly one more LLM call.
    assert summary.processed_count == 1
    assert call_count["n"] == calls_before_retry  # the mixed-llm was not called again (fixed llm used instead)
    assert [i.status for i in items_after] == ["success", "success", "success"]
    assert successful_titles_after == successful_titles_before  # completely unchanged


def test_pending_items_run_on_resume() -> None:
    """Simulates an interrupted process: create_run() ran, but run_batch()
    never got called (or crashed before touching any item) -- all items
    are still 'pending'. A fresh run_batch() call must process them."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 2)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    items_before = list_run_items(conn, run_id)
    assert all(item.status == "pending" for item in items_before)

    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    conn.close()

    assert summary.processed_count == 2
    assert summary.success_count == 2


def test_interrupted_batch_resume_processes_only_remaining_items(monkeypatch) -> None:
    """A more realistic interruption: the FIRST run_batch() call fails
    partway through (item 2 of 3 raises), leaving item 3 still 'pending'
    (never attempted) and item 2 'failed'. A resume call must pick up
    both, and must NOT reprocess the already-successful item 1."""
    import illustration_engine.enrichment_batch as batch_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_ids = _seed_short_stories(conn, source_id, 3)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    call_count = {"n": 0}
    real_enrich_story = batch_module.enrich_story

    def flaky_enrich_story(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated crash mid-batch")
        return real_enrich_story(*args, **kwargs)

    monkeypatch.setattr(batch_module, "enrich_story", flaky_enrich_story)
    first_summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    assert first_summary.success_count == 2  # item 1 and item 3 succeeded, item 2 failed
    assert first_summary.failed_count == 1

    monkeypatch.setattr(batch_module, "enrich_story", real_enrich_story)  # remove the flakiness

    call_ids_before_resume = call_count["n"]

    resume_summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    items = list_run_items(conn, run_id)
    conn.close()

    assert resume_summary.processed_count == 1  # only the previously-failed item
    assert resume_summary.success_count == 1
    assert resume_summary.skipped_count == 2  # the two already-successful items
    assert all(item.status == "success" for item in items)


# ---------------------------------------------------------------------------
# Human-review protection is never bypassable from a batch
# ---------------------------------------------------------------------------


def test_already_enriched_story_excluded_from_a_later_run_selection() -> None:
    """Phase 3H hardening: create_run() must never re-select a story that
    already has an illustration_unit -- regardless of that unit's status
    (needs_review/approved/both exercised below) -- since a second
    selection would otherwise let enrich_story() silently UPDATE the
    existing unit in place via its get-or-create semantics. This is the
    FIRST line of defense; the human-review-protection guard inside
    enrich_story()/update_draft_unit() (covered elsewhere, e.g.
    test_enrichment_pipeline.py) is the second, independent one."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, external_ref="r", original_text="Sheridan told a short story.")
    conn.commit()

    run_1 = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    run_batch(conn, run_id=run_1, llm_generate=_fixed_llm(_direct_unit_payload(title_hu="Jóváhagyott cím")))
    items = list_run_items(conn, run_1)
    unit_id = items[0].illustration_unit_id
    approve_unit(conn, unit_id)
    conn.commit()
    before = get_unit(conn, unit_id)

    run_2 = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    summary = run_batch(conn, run_id=run_2, llm_generate=_fixed_llm(_direct_unit_payload(title_hu="Csendes felülírás")))
    items_2 = list_run_items(conn, run_2)
    after = get_unit(conn, unit_id)
    conn.close()

    # The already-enriched story is excluded at selection time -- run_2
    # has NOTHING to process, not even a rejected item.
    assert items_2 == []
    assert summary.processed_count == 0
    assert after == before
    assert after.title_hu == "Jóváhagyott cím"


def test_already_enriched_needs_review_story_also_excluded() -> None:
    """The exclusion must apply regardless of the existing unit's status
    -- not just approved/published ones."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, external_ref="r2", original_text="A second short story.")
    conn.commit()

    run_1 = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    run_batch(conn, run_id=run_1, llm_generate=_fixed_llm(_direct_unit_payload(title_hu="Első cím")))
    conn.commit()
    unit_id = list_run_items(conn, run_1)[0].illustration_unit_id
    before = get_unit(conn, unit_id)
    assert before.status == "needs_review"  # never approved -- still excluded

    run_2 = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    summary = run_batch(conn, run_id=run_2, llm_generate=_fixed_llm(_direct_unit_payload(title_hu="Második cím")))
    after = get_unit(conn, unit_id)
    conn.close()

    assert summary.processed_count == 0
    assert after == before
    assert after.title_hu == "Első cím"


# ---------------------------------------------------------------------------
# Ledger JSON/string roundtrip
# ---------------------------------------------------------------------------


def test_ledger_warnings_json_roundtrip() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(
        conn, source_id, external_ref="w", original_text="A person announced that God had blessed the land."
    )
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    payload = _direct_unit_payload(modern_hu_text="Valaki azt mondta, hogy Isten megáldotta a földet.")
    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(payload))

    raw_json = conn.execute(
        "SELECT warnings_json FROM enrichment_run_items WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    items = list_run_items(conn, run_id)
    conn.close()

    assert raw_json is not None
    parsed_raw = json.loads(raw_json)
    assert isinstance(parsed_raw, list)
    assert items[0].warnings == tuple(parsed_raw)


def test_ledger_error_message_roundtrip() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    bad_payload = _direct_unit_payload(derivation_type="condensed_story")
    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(bad_payload))

    raw_error = conn.execute(
        "SELECT error_message FROM enrichment_run_items WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    items = list_run_items(conn, run_id)
    conn.close()

    assert raw_error is not None
    assert items[0].error_message == raw_error


def test_no_warning_item_has_null_warnings_json() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))

    raw_json = conn.execute(
        "SELECT warnings_json FROM enrichment_run_items WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    conn.close()

    assert raw_json is None


# ---------------------------------------------------------------------------
# Run completion status
# ---------------------------------------------------------------------------


def test_run_completion_status_completed_when_all_clean() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 2)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    run = get_run(conn, run_id)
    conn.close()

    assert summary.overall_status == "completed"
    assert run.overall_status == "completed"
    assert run.finished_at is not None


def test_run_completion_status_completed_with_errors_when_any_rejected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 2)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    bad_payload = _direct_unit_payload(derivation_type="condensed_story")
    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(bad_payload))
    run = get_run(conn, run_id)
    conn.close()

    assert summary.overall_status == "completed_with_errors"
    assert run.overall_status == "completed_with_errors"


def test_run_not_found_raises() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        run_batch(conn, run_id=999999, llm_generate=_fixed_llm(_direct_unit_payload()))
    conn.close()


# ---------------------------------------------------------------------------
# Story/item transaction atomicity (explicit proof, per follow-up audit)
# ---------------------------------------------------------------------------


def test_ledger_write_failure_after_successful_enrich_story_rolls_back_unit(monkeypatch) -> None:
    """(A) enrich_story() succeeds and would normally persist an
    illustration_unit, but the SECOND ledger write for this item (the one
    recording the final outcome -- the FIRST already succeeded, marking
    'running') is made to fail. The whole per-item SAVEPOINT must roll
    back TOGETHER: the illustration_unit write is undone, and the item
    ends up 'failed', never a false 'success' with no matching unit."""
    import illustration_engine.enrichment_batch as batch_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    real_update_item = batch_module.update_enrichment_run_item
    call_count = {"n": 0}

    def flaky_update_item(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:  # 1st call = mark 'running' (must succeed); 2nd = final outcome (fails here)
            raise RuntimeError("simulated ledger write failure")
        return real_update_item(*args, **kwargs)

    monkeypatch.setattr(batch_module, "update_enrichment_run_item", flaky_update_item)

    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    unit_count = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    items = list_run_items(conn, run_id)
    conn.close()

    assert unit_count == 0  # the successful enrich_story() write was rolled back with the failed ledger write
    assert items[0].status == "failed"
    assert items[0].illustration_unit_id is None
    assert summary.failed_count == 1
    assert summary.success_count == 0


def test_previous_successful_item_survives_next_items_failed_transaction(monkeypatch) -> None:
    """(B) A two-item batch: item 1 succeeds and its own SAVEPOINT is
    released and committed; item 2's attempt then fails. Item 1's
    illustration_unit and ledger record must be completely unaffected --
    no blanket batch-wide rollback undoes already-committed work."""
    import illustration_engine.enrichment_batch as batch_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_ids = _seed_short_stories(conn, source_id, 2)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    real_enrich_story = batch_module.enrich_story
    call_count = {"n": 0}

    def flaky_enrich_story(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated failure on the second item")
        return real_enrich_story(*args, **kwargs)

    monkeypatch.setattr(batch_module, "enrich_story", flaky_enrich_story)
    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))

    items = list_run_items(conn, run_id)
    unit_count = conn.execute("SELECT COUNT(*) FROM illustration_units").fetchone()[0]
    conn.close()

    first_item = next(item for item in items if item.story_id == story_ids[0])
    second_item = next(item for item in items if item.story_id == story_ids[1])
    assert first_item.status == "success"
    assert first_item.illustration_unit_id is not None
    assert second_item.status == "failed"
    assert unit_count == 1  # only item 1's unit exists -- item 2's failure created nothing


# ---------------------------------------------------------------------------
# Crash / stale-running resume semantics
# ---------------------------------------------------------------------------


def test_item_marked_running_before_enrich_story_is_called(monkeypatch) -> None:
    """Direct proof of the intermediate write: mid-_process_one_item (a
    real crash would stop the process here), the item must already show
    'running' with started_at set, durably committed -- not still
    'pending', and not yet at any terminal status."""
    import illustration_engine.enrichment_batch as batch_module

    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    observed = {}

    def spying_enrich_story(*args, **kwargs):
        # At this exact point, the 'running' write must already be
        # committed to the connection -- proof that a real crash here
        # would leave exactly this row durable on disk for a file-backed DB.
        row = conn.execute(
            "SELECT status, started_at FROM enrichment_run_items WHERE run_id = ?", (run_id,)
        ).fetchone()
        observed["status"], observed["started_at"] = row
        raise RuntimeError("simulated crash mid-item")

    monkeypatch.setattr(batch_module, "enrich_story", spying_enrich_story)
    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    conn.close()

    assert observed["status"] == "running"
    assert observed["started_at"] is not None


def test_stale_running_item_retried_only_after_explicit_mark_run_interrupted() -> None:
    """Simulates a REAL crash directly at the DB level (not via a caught
    Python exception): both the run and one of its items are left exactly
    at status='running' the way a genuine process crash would leave them
    (the process died before its own completion/interrupt handling ever
    ran). A plain run_batch() call must NOT silently retry that item --
    it must refuse to start at all (EnrichmentRunAlreadyRunningError,
    zero LLM calls), because nothing has confirmed the previous process
    is actually gone. Only AFTER the explicit mark_run_interrupted()
    recovery call does a fresh run_batch() retry the stale item to a real
    terminal status."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    item_id = list_run_items(conn, run_id)[0].id

    # Simulate the crash: run AND item both stuck at 'running', as a real
    # process death mid-_process_one_item would leave them.
    raw_update_run(conn, run_id=run_id, overall_status="running")
    raw_update_run_item(conn, item_id=item_id, status="running", started_at="2026-01-01T00:00:00+00:00")
    conn.commit()
    assert get_run(conn, run_id).overall_status == "running"
    assert list_run_items(conn, run_id)[0].status == "running"

    call_count = {"n": 0}

    def counting_llm(prompt):
        call_count["n"] += 1
        return json.dumps(_direct_unit_payload())

    with pytest.raises(EnrichmentRunAlreadyRunningError):
        run_batch(conn, run_id=run_id, llm_generate=counting_llm)
    assert call_count["n"] == 0
    assert list_run_items(conn, run_id)[0].status == "running"  # untouched by the refused call

    mark_run_interrupted(conn, run_id)
    assert get_run(conn, run_id).overall_status == "interrupted"

    summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    items_after = list_run_items(conn, run_id)
    conn.close()

    assert summary.processed_count == 1
    assert summary.success_count == 1
    assert items_after[0].status == "success"


# ---------------------------------------------------------------------------
# Frozen run selection (explicit proof, per follow-up audit)
# ---------------------------------------------------------------------------


def test_resume_does_not_pick_up_newly_eligible_stories() -> None:
    """create_run() freezes the exact story list into enrichment_run_items
    at creation time. Adding a NEW, equally-eligible story to the corpus
    AFTER the run was created, then calling run_batch() again (a resume),
    must NOT cause the new story to appear in this run -- the run's item
    list is the reproducible definition of the batch, and resume never
    re-runs the selection query."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 2)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    items_at_creation = list_run_items(conn, run_id)
    assert len(items_at_creation) == 2

    new_story_id = _make_story(
        conn, source_id, external_ref="new-after-creation", original_text="Sheridan told a brand new short story."
    )
    conn.commit()

    run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    items_after_resume = list_run_items(conn, run_id)
    conn.close()

    assert len(items_after_resume) == 2
    assert new_story_id not in [item.story_id for item in items_after_resume]


# ---------------------------------------------------------------------------
# Run-level concurrency guard (single-runner-per-run contract)
# ---------------------------------------------------------------------------


def test_A_second_run_batch_on_already_running_run_raises_and_calls_llm_zero_times() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    raw_update_run(conn, run_id=run_id, overall_status="running")
    conn.commit()

    call_count = {"n": 0}

    def counting_llm(prompt):
        call_count["n"] += 1
        return json.dumps(_direct_unit_payload())

    with pytest.raises(EnrichmentRunAlreadyRunningError):
        run_batch(conn, run_id=run_id, llm_generate=counting_llm)
    conn.close()

    assert call_count["n"] == 0


def test_B_running_run_with_running_item_not_retried_by_normal_call() -> None:
    """A more specific variant of A: the run AND one of its items are
    both 'running' (the realistic crash state) -- a normal run_batch()
    call must refuse to start, leaving the item exactly as it was, not
    silently reprocess it."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    item_id = list_run_items(conn, run_id)[0].id

    raw_update_run(conn, run_id=run_id, overall_status="running")
    raw_update_run_item(conn, item_id=item_id, status="running", started_at="2026-01-01T00:00:00+00:00")
    conn.commit()

    with pytest.raises(EnrichmentRunAlreadyRunningError):
        run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    item_after = list_run_items(conn, run_id)[0]
    conn.close()

    assert item_after.status == "running"  # completely untouched by the refused call


def test_C_mark_run_interrupted_transitions_running_to_interrupted() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)
    raw_update_run(conn, run_id=run_id, overall_status="running")
    conn.commit()

    mark_run_interrupted(conn, run_id)
    run = get_run(conn, run_id)
    conn.close()

    assert run.overall_status == "interrupted"
    assert run.finished_at is not None


def test_mark_run_interrupted_rejects_non_running_run() -> None:
    """Marking a run interrupted only makes sense while it looks
    actively in-progress -- calling it on a freshly-created (never
    started) or already-terminal run is a caller mistake, not a normal
    recovery action."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    with pytest.raises(ValueError):
        mark_run_interrupted(conn, run_id)  # still 'created', never started
    conn.close()


def test_E_completed_with_errors_failed_item_retried_by_explicit_resume() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 1)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    bad_payload = _direct_unit_payload(derivation_type="condensed_story")
    first_summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(bad_payload))
    assert first_summary.overall_status == "completed_with_errors"
    assert first_summary.rejected_count == 1  # a deterministic contract rejection, not 'failed' -- see below

    # Force the item into 'failed' directly (simulating an exception-path
    # outcome) to test the specific 'completed_with_errors + failed item'
    # scenario the audit asked for, independent of the rejected/
    # retry_rejected path already covered elsewhere.
    item_id = list_run_items(conn, run_id)[0].id
    raw_update_run_item(conn, item_id=item_id, status="failed", error_message="simulated prior failure")
    conn.commit()
    assert get_run(conn, run_id).overall_status == "completed_with_errors"

    good_payload = _direct_unit_payload()
    resume_summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(good_payload))
    items_after = list_run_items(conn, run_id)
    conn.close()

    assert resume_summary.processed_count == 1
    assert resume_summary.success_count == 1
    assert items_after[0].status == "success"


def test_F_completed_run_second_call_makes_zero_llm_calls() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    _seed_short_stories(conn, source_id, 2)
    conn.commit()
    run_id = create_run(conn, model_identifier="m", prompt_version="v1", source_code="SRC", strategy_band="A", limit=10)

    first_summary = run_batch(conn, run_id=run_id, llm_generate=_fixed_llm(_direct_unit_payload()))
    assert first_summary.overall_status == "completed"

    call_count = {"n": 0}

    def counting_llm(prompt):
        call_count["n"] += 1
        return json.dumps(_direct_unit_payload())

    second_summary = run_batch(conn, run_id=run_id, llm_generate=counting_llm)
    conn.close()

    assert call_count["n"] == 0
    assert second_summary.processed_count == 0
    assert second_summary.skipped_count == 2
