"""Phase 3H: bounded QA + repair orchestration for one illustration unit.

Pipeline, per unit, STRICTLY bounded (never an agent loop):
  1 initial QA -> (if not PASS and repair allowed) 1 repair -> 1 final QA.
No retries beyond this; if the final QA is not PASS, the unit's qa_status
becomes 'needs_attention' or 'failed' and a human reviews it -- this
module never approves/publishes/re-repairs.

Provenance/lifecycle guarantees (all structural, not conventions):
- reads unit/story data via illustration_unit_repository.get_review_item()
  (read-only);
- repair writes go through illustration_sqlite.update_illustration_unit_fields()
  directly (NOT the update_draft_unit() convenience wrapper -- that
  wrapper filters out None values as "leave untouched", which would
  silently refuse to CLEAR moral_hu back to NULL when a repair
  legitimately removes a forced/invented moral -- exactly the Phase
  3G-B3/3H-A scenario this whole repair path exists to fix). The
  human-review-protection guard still applies at this level exactly as
  for every other content write.
- QA-verdict writes go through illustration_sqlite.update_unit_machine_qa()
  -- the sole write path for qa_* columns, which cannot touch status/
  human_reviewed_at even by accident (see its own docstring).
- this module has NO write path to `stories` at all -- original_text/
  checksum immutability is structural, not a promise.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Callable

from illustration_engine.enrichment_pipeline import derive_enrichment_strategy
from illustration_engine.illustration_sqlite import (
    insert_qa_repair,
    update_illustration_unit_fields,
    update_unit_machine_qa,
)
from illustration_engine.illustration_unit_repository import get_review_item
from illustration_engine.qa_agent import QA_PROMPT_VERSION, QAIssue, QAVerdict, run_content_qa, run_repair

_VERDICT_TO_QA_STATUS = {"PASS": "passed", "NEEDS_ATTENTION": "needs_attention", "FAIL": "failed"}
_REPAIRABLE_FIELDS = ("title_hu", "modern_hu_text", "summary_hu", "moral_hu")


@dataclass(frozen=True)
class QAOutcome:
    unit_id: int
    initial_verdict: QAVerdict
    repair_attempted: bool
    repair_applied: bool
    final_verdict: QAVerdict
    qa_status_written: str


def _issues_to_json(issues: tuple[QAIssue, ...]) -> str:
    return json.dumps([{"code": i.code, "detail": i.detail} for i in issues], ensure_ascii=False)


def _qa_for_item(item, strategy, llm_generate: Callable[[str], str]) -> QAVerdict:
    return run_content_qa(
        source_code=item.source_code,
        title_original=item.title_original,
        original_text=item.original_text,
        title_hu=item.title_hu or "",
        modern_hu_text=item.modern_hu_text or "",
        summary_hu=item.summary_hu or "",
        moral_hu=item.moral_hu,
        tone=item.tone,
        derivation_type=item.derivation_type,
        current_expected_mode=strategy.expected_mode,
        current_expected_derivation_type=strategy.expected_derivation_type,
        llm_generate=llm_generate,
    )


def run_machine_qa_for_unit(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    llm_generate: Callable[[str], str],
    model_identifier: str,
    prompt_version: str = QA_PROMPT_VERSION,
    allow_repair: bool = True,
) -> QAOutcome:
    """Runs the bounded QA -> repair -> final-QA pipeline for one unit.

    DOES NOT COMMIT -- same convention as every other illustration_engine
    write function and as `enrichment_batch.py`'s own per-item commit
    pattern (see that module's FAULT ISOLATION docstring section). The
    CALLER owns the transaction boundary. A batch orchestrator normally
    commits after each item for fault isolation (a crash mid-run only
    loses the one in-flight item); a bare, uncommitted call followed by
    `connection.close()` performs a silent, total ROLLBACK of this
    write -- no exception, no corruption, the unit's qa_status simply
    reverts to whatever it was before this call. This is exactly the
    Phase 3J bug (a standalone batch script never called `commit()`,
    losing an entire QA pass silently) -- see `tests/test_qa_orchestrator.py`'s
    commit-persistence regression tests, and `run_machine_qa_for_unit_and_commit`
    below for a wrapper that closes this gap for simple, single-call
    scripts."""
    item = get_review_item(connection, unit_id)
    if item is None:
        raise ValueError(f"illustration unit not found: id={unit_id}")

    strategy = derive_enrichment_strategy(len(item.original_text or ""))
    initial_verdict = _qa_for_item(item, strategy, llm_generate)
    final_verdict = initial_verdict
    repair_attempted = False
    repair_applied = False

    if initial_verdict.status != "PASS" and allow_repair:
        repair_attempted = True
        repaired = run_repair(
            source_code=item.source_code,
            title_original=item.title_original,
            original_text=item.original_text,
            title_hu=item.title_hu or "",
            modern_hu_text=item.modern_hu_text or "",
            summary_hu=item.summary_hu or "",
            moral_hu=item.moral_hu,
            issues=initial_verdict.issues,
            llm_generate=llm_generate,
        )
        if repaired is not None:
            before_values = {f: getattr(item, f) for f in _REPAIRABLE_FIELDS}
            changed_fields = [f for f in _REPAIRABLE_FIELDS if repaired[f] != before_values[f]]
            if changed_fields:
                # Explicit values for ALL four fields (including a real
                # None for moral_hu when the repair clears it) -- see
                # module docstring for why update_draft_unit() is
                # deliberately NOT used here.
                update_illustration_unit_fields(
                    connection,
                    unit_id=unit_id,
                    title_hu=repaired["title_hu"],
                    modern_hu_text=repaired["modern_hu_text"],
                    summary_hu=repaired["summary_hu"],
                    moral_hu=repaired["moral_hu"],
                )
                insert_qa_repair(
                    connection,
                    unit_id=unit_id,
                    qa_model=model_identifier,
                    qa_prompt_version=prompt_version,
                    issues_before_json=_issues_to_json(initial_verdict.issues),
                    fields_changed_json=json.dumps(changed_fields),
                    before_values_json=json.dumps(before_values, ensure_ascii=False),
                    after_values_json=json.dumps(repaired, ensure_ascii=False),
                )
                repair_applied = True
                refreshed = get_review_item(connection, unit_id)
                final_verdict = _qa_for_item(refreshed, strategy, llm_generate)

    qa_status = _VERDICT_TO_QA_STATUS[final_verdict.status]
    update_unit_machine_qa(
        connection,
        unit_id=unit_id,
        qa_status=qa_status,
        qa_model=model_identifier,
        qa_prompt_version=prompt_version,
        qa_confidence=final_verdict.confidence,
        qa_issues_json=_issues_to_json(final_verdict.issues),
    )

    return QAOutcome(
        unit_id=unit_id,
        initial_verdict=initial_verdict,
        repair_attempted=repair_attempted,
        repair_applied=repair_applied,
        final_verdict=final_verdict,
        qa_status_written=qa_status,
    )


def run_machine_qa_for_unit_and_commit(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    llm_generate: Callable[[str], str],
    model_identifier: str,
    prompt_version: str = QA_PROMPT_VERSION,
    allow_repair: bool = True,
) -> QAOutcome:
    """Phase 3J.1: same pipeline as `run_machine_qa_for_unit`, but commits
    immediately after -- for standalone/one-off scripts that call this
    function directly (not through an already-committing orchestrator
    like `enrichment_batch.run_batch()`) and have no reason to batch
    multiple units into one transaction. Prefer THIS over the bare
    function for any new standalone script, unless you have a specific,
    deliberate reason to control the commit boundary yourself (and if so,
    commit after EVERY unit anyway -- see the bare function's docstring
    for why per-item commit matters even then)."""
    outcome = run_machine_qa_for_unit(
        connection, unit_id=unit_id, llm_generate=llm_generate, model_identifier=model_identifier,
        prompt_version=prompt_version, allow_repair=allow_repair,
    )
    connection.commit()
    return outcome


__all__ = ["QAOutcome", "run_machine_qa_for_unit", "run_machine_qa_for_unit_and_commit"]
