from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from illustration_engine.illustration_sqlite import create_schema, insert_source, insert_story
from illustration_engine.illustration_unit_repository import create_draft_unit, get_unit, update_draft_unit
from illustration_engine.qa_orchestrator import run_machine_qa_for_unit

_VALID_SUMMARY = " ".join(["szo"] * 45)


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _make_source(conn: sqlite3.Connection) -> int:
    return insert_source(
        conn, code="SRC", title="Test Source", orig_language="en",
        license_status="public_domain_confirmed", license_basis_hu="x", reliability_tier="high",
    )


def _make_story(conn: sqlite3.Connection, source_id: int, *, original_text: str) -> int:
    return insert_story(
        conn, source_id=source_id, external_ref="1", canonical_key="001",
        title_original="Original Title", adaptation_status="verbatim_transcription",
        original_text=original_text,
    )


def _make_unit(conn: sqlite3.Connection, story_id: int, *, moral_hu: str | None = "Erőltetett tanulság.") -> int:
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu=_VALID_SUMMARY,
        moral_hu=moral_hu,
    )
    return unit_id


def _qa_response(status: str, issues: list[dict] | None = None, confidence: float = 0.8) -> str:
    return json.dumps({"status": status, "confidence": confidence, "issues": issues or [], "rationale": "r"})


def _repair_response(*, title_hu="Javított cím", modern_hu_text="Javított szöveg", summary_hu=None, moral_hu=None) -> str:
    return json.dumps(
        {
            "title_hu": title_hu,
            "modern_hu_text": modern_hu_text,
            "summary_hu": summary_hu or _VALID_SUMMARY,
            "moral_hu": moral_hu,
        }
    )


def _is_repair_prompt(prompt: str) -> bool:
    return "JAVÍTÓ" in prompt or "TALÁLT PROBLÉMÁK" in prompt


def test_pass_on_first_try_no_repair_attempted() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id)
    conn.commit()

    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        return _qa_response("PASS")

    outcome = run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=llm, model_identifier="m")
    conn.commit()

    assert outcome.initial_verdict.status == "PASS"
    assert outcome.repair_attempted is False
    assert outcome.repair_applied is False
    assert outcome.qa_status_written == "passed"
    assert len(calls) == 1  # only the initial QA call, no repair, no final QA

    unit = get_unit(conn, unit_id)
    conn.close()
    assert unit.title_hu == "Cím"  # unchanged, no repair applied


def test_needs_attention_then_repair_then_final_pass() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id, moral_hu="Erőltetett tanulság.")
    conn.commit()

    call_count = {"qa": 0, "repair": 0}

    def llm(prompt: str) -> str:
        if _is_repair_prompt(prompt):
            call_count["repair"] += 1
            return _repair_response(moral_hu=None)  # clears the forced moral
        call_count["qa"] += 1
        if call_count["qa"] == 1:
            return _qa_response("NEEDS_ATTENTION", [{"code": "FORCED_MORAL", "detail": "x"}])
        return _qa_response("PASS")  # final QA after repair

    outcome = run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=llm, model_identifier="m")
    conn.commit()

    assert outcome.initial_verdict.status == "NEEDS_ATTENTION"
    assert outcome.repair_attempted is True
    assert outcome.repair_applied is True
    assert outcome.final_verdict.status == "PASS"
    assert outcome.qa_status_written == "passed"
    assert call_count["qa"] == 2  # initial + final
    assert call_count["repair"] == 1  # exactly once -- max 1 repair

    unit = get_unit(conn, unit_id)
    conn.close()
    assert unit.title_hu == "Javított cím"
    assert unit.moral_hu is None  # forced moral actually cleared to NULL


def test_max_one_repair_even_if_final_qa_still_not_pass() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id)
    conn.commit()

    call_count = {"qa": 0, "repair": 0}

    def llm(prompt: str) -> str:
        if _is_repair_prompt(prompt):
            call_count["repair"] += 1
            return _repair_response()
        call_count["qa"] += 1
        return _qa_response("FAIL", [{"code": "MEANING_SHIFT", "detail": "x"}])

    outcome = run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=llm, model_identifier="m")
    conn.commit()

    assert outcome.repair_attempted is True
    assert outcome.repair_applied is True
    assert outcome.final_verdict.status == "FAIL"
    assert outcome.qa_status_written == "failed"
    assert call_count["repair"] == 1  # never retried a second time
    assert call_count["qa"] == 2  # initial + final, no third attempt
    conn.close()


def test_repair_not_applied_when_unparseable_keeps_initial_verdict() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id)
    conn.commit()

    def llm(prompt: str) -> str:
        if _is_repair_prompt(prompt):
            return "not valid json"
        return _qa_response("NEEDS_ATTENTION", [{"code": "POOR_HUNGARIAN", "detail": "x"}])

    outcome = run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=llm, model_identifier="m")
    conn.commit()

    assert outcome.repair_attempted is True
    assert outcome.repair_applied is False
    assert outcome.final_verdict == outcome.initial_verdict
    assert outcome.qa_status_written == "needs_attention"

    unit = get_unit(conn, unit_id)
    conn.close()
    assert unit.title_hu == "Cím"  # untouched


def test_allow_repair_false_skips_repair_entirely() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id)
    conn.commit()

    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        return _qa_response("FAIL", [{"code": "MEANING_SHIFT", "detail": "x"}])

    outcome = run_machine_qa_for_unit(
        conn, unit_id=unit_id, llm_generate=llm, model_identifier="m", allow_repair=False
    )
    conn.commit()

    assert outcome.repair_attempted is False
    assert outcome.qa_status_written == "failed"
    assert len(calls) == 1
    conn.close()


def test_qa_repair_audit_row_created_with_before_after() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id, moral_hu="Erőltetett tanulság.")
    conn.commit()

    def llm(prompt: str) -> str:
        if _is_repair_prompt(prompt):
            return _repair_response(moral_hu=None)
        return _qa_response("NEEDS_ATTENTION", [{"code": "FORCED_MORAL", "detail": "x"}]) \
            if "Javított" not in prompt else _qa_response("PASS")

    run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=llm, model_identifier="m")
    conn.commit()

    row = conn.execute(
        "SELECT unit_id, issues_before_json, fields_changed_json, before_values_json, after_values_json "
        "FROM qa_repairs WHERE unit_id = ?",
        (unit_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == unit_id
    assert "FORCED_MORAL" in row[1]
    changed = json.loads(row[2])
    assert "moral_hu" in changed
    before = json.loads(row[3])
    after = json.loads(row[4])
    assert before["moral_hu"] == "Erőltetett tanulság."
    assert after["moral_hu"] is None


def test_human_reviewed_at_and_status_never_touched_by_qa() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id)
    conn.commit()

    before = conn.execute("SELECT status, human_reviewed_at FROM illustration_units WHERE id=?", (unit_id,)).fetchone()

    def llm(prompt: str) -> str:
        if _is_repair_prompt(prompt):
            return _repair_response()
        return _qa_response("NEEDS_ATTENTION", [{"code": "POOR_HUNGARIAN", "detail": "x"}])

    run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=llm, model_identifier="m")
    conn.commit()

    after = conn.execute("SELECT status, human_reviewed_at FROM illustration_units WHERE id=?", (unit_id,)).fetchone()
    conn.close()
    assert before == after
    assert after[1] is None


def test_original_text_and_checksum_untouched_across_qa_and_repair() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story that must never change.")
    unit_id = _make_unit(conn, story_id)
    conn.commit()

    before = conn.execute(
        "SELECT original_text, original_text_checksum, title_original FROM stories WHERE id=?", (story_id,)
    ).fetchone()

    def llm(prompt: str) -> str:
        if _is_repair_prompt(prompt):
            return _repair_response()
        return _qa_response("NEEDS_ATTENTION", [{"code": "POOR_HUNGARIAN", "detail": "x"}])

    run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=llm, model_identifier="m")
    conn.commit()

    after = conn.execute(
        "SELECT original_text, original_text_checksum, title_original FROM stories WHERE id=?", (story_id,)
    ).fetchone()
    conn.close()
    assert before == after


def test_provider_failure_propagates_and_is_not_silently_swallowed() -> None:
    """The orchestrator itself does not catch provider exceptions --
    per-story isolation is the BATCH script's responsibility (matching
    enrichment_batch.py's own _process_one_item pattern), so a raised
    exception here must propagate cleanly, not be silently absorbed."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="Short story.")
    unit_id = _make_unit(conn, story_id)
    conn.commit()

    def broken_llm(prompt: str) -> str:
        raise ConnectionError("simulated provider failure")

    with pytest.raises(ConnectionError):
        run_machine_qa_for_unit(conn, unit_id=unit_id, llm_generate=broken_llm, model_identifier="m")

    # nothing partially written
    row = conn.execute("SELECT qa_status FROM illustration_units WHERE id=?", (unit_id,)).fetchone()
    conn.close()
    assert row[0] is None


def test_moral_hu_null_from_the_start_is_not_flagged_as_content_missing() -> None:
    """A unit that already correctly has moral_hu=None (per the Phase
    3G-B3 optional policy) must be QA-able without any special casing."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="A joke with no moral.")
    unit_id = _make_unit(conn, story_id, moral_hu=None)
    conn.commit()

    outcome = run_machine_qa_for_unit(
        conn, unit_id=unit_id, llm_generate=lambda p: _qa_response("PASS"), model_identifier="m"
    )
    conn.close()
    assert outcome.qa_status_written == "passed"
