"""Phase 3F: production batch control plane for the illustration
enrichment pipeline (`illustration_engine.enrichment_pipeline`).

This module owns EVERYTHING about running `enrich_story()` over many
stories: deterministic selection, the persistent run/item ledger
(`enrichment_runs`/`enrichment_run_items`, schema v5 — raw CRUD lives in
`illustration_sqlite.py`, same split as every other table), resume/retry
policy, and story-level fault isolation. None of this logic lives in
`enrichment_pipeline.py` (which stays a single-story, ledger-unaware
function), in `illustration_sqlite.py` (schema + raw CRUD only, no
selection/resume/retry policy), or in `app.py` (no Streamlit/UI
dependency here at all — this module is provider-agnostic and UI-free,
matching `illustration_engine`'s established self-containment rule).

DETERMINISTIC SELECTION — `create_run()` is the ONLY place a batch's
story list is decided. It queries `source_code`'s stories ordered by
`story_id ASC`, classifies each by `derive_enrichment_strategy()`
(mapped to a single letter: 'A' = direct_unit/full_story_translation,
'B' = direct_unit/condensed_story, 'C' = unit_proposal), keeps the first
`limit` stories matching the requested `strategy_band`, and freezes that
exact list into `enrichment_run_items` rows (`status='pending'`) in the
SAME call. This is what makes a run's item list the reproducible
definition of the batch — `run_batch()` NEVER re-runs the selection
query; every subsequent call (including a resume after an interrupted
process) only re-reads the frozen item rows already in the ledger.

CONCURRENCY MODEL — SINGLE RUNNER PER RUN, enforced, not just assumed.
There is no multi-worker processing of one run, no lease, no heartbeat,
and no automatic/time-based staleness detection anywhere in this module.
`run_batch()` refuses to start at all — raising
`EnrichmentRunAlreadyRunningError`, calling `llm_generate` zero times —
if the target run's `overall_status` is already `'running'`: that status
is the ENTIRE concurrency guard, checked once at the top of the
function, before anything else happens. A second, concurrent
`run_batch()` call on the same `run_id` can therefore never process the
same story twice. Recovering a run whose process genuinely crashed (so
nothing ever transitioned it out of `'running'`) requires an EXPLICIT,
human-authorized action — `mark_run_interrupted(connection, run_id)` —
which asserts "the previous process is confirmed gone" and moves
`overall_status` from `'running'` to `'interrupted'`. Only THEN does
`run_batch()` accept the run again. This is the deliberate scope
boundary: enough to make a single operator's restart-after-crash safe
and explicit, not a distributed-worker coordination system.

RESUME/RETRY POLICY — `run_batch()` is itself the resume mechanism: a
fresh run and a resumed run go through the exact same code path (after
the concurrency guard above has already passed), because every item's
current `status` already tells the function what to do with it:
- `pending` -> always (re)run.
- `running` -> (re)run ONLY when the run's `overall_status` was
  `'interrupted'` at the start of this call — see CRASH / STALE-RUNNING
  RESUME SEMANTICS below. In every other reachable case (a run that
  isn't `'running'` and isn't `'interrupted'` — i.e. `'created'`,
  `'completed'`, or `'completed_with_errors'`) no item can legitimately
  be `'running'` at all, because the concurrency guard above already
  refuses to let two `run_batch()` calls overlap on the same run.
- `failed` -> always (re)run, regardless of the run's overall_status
  (including a plain `completed_with_errors` resume, no special flag
  needed) — an unexpected exception, safe to retry automatically.
- `rejected` -> skipped UNLESS the caller passes `retry_rejected=True` —
  a deterministic contract-violation rejection (bad JSON, wrong
  derivation_type, guard-adjacent findings that are warnings now, an
  expected_mode/strategy mismatch, human-review protection, etc.) is
  usually not something blindly retrying fixes, so it needs an explicit
  opt-in.
- `success` / `warning` / `proposal_ready` -> always skipped. A
  `unit_proposal` result is NEVER retried automatically even though
  nothing was persisted for it — re-proposing is a deliberate human
  decision (Phase 3C-c PROPOSAL CONTRACT), not something a batch resume
  should do on its own. A run where EVERY item is already at one of
  these three statuses (`overall_status='completed'`) triggers zero
  eligible items and therefore zero `llm_generate` calls on a repeat
  `run_batch()` call.

CRASH / STALE-RUNNING RESUME SEMANTICS — a caught Python exception
(handled by FAULT ISOLATION below) is the easy case; a real production
crash (process killed, machine loses power) can interrupt a story
mid-`enrich_story()` call with NO exception ever raised or caught, AND
can leave the RUN's own `overall_status` stuck at `'running'` forever
(the process never got to run `run_batch()`'s own completion/interrupt
handling either). To make the item-level state visible once recovery
happens, `_process_one_item` writes `status='running'` (clearing any
stale error_message/warnings_json from an earlier attempt) and COMMITS
it BEFORE calling `enrich_story()` at all — not inside the same
SAVEPOINT as the actual attempt, specifically so it survives a crash
that happens after this write but before the attempt finishes. A
`running` item therefore always means "a previous attempt started and
never reached its own final status update" — but that fact ALONE does
not make it safe to retry automatically: without the run-level
`'interrupted'` gate above, a second, still-legitimately-running process
could observe another worker's in-flight `running` item and reprocess
the same story concurrently. The gate is what removes that ambiguity —
`running` items are only ever retried as part of an EXPLICITLY recovered
(`mark_run_interrupted`) resume, never a plain, unguarded re-call.

FAULT ISOLATION — each item is processed inside its own SQL SAVEPOINT.
On success, the SAVEPOINT is released and the connection is committed
immediately (so a later item's failure can never roll back an earlier
item's already-recorded outcome). On an exception (from `enrich_story`
itself, or from writing the ledger row), the SAVEPOINT is rolled back —
undoing BOTH any partial illustration_unit write AND any partial ledger
write from this one item, so the item's enrichment result and its ledger
record can never disagree — and the item is marked `failed` in a fresh,
separate write. The loop always continues to the next item; a single bad
story never stops the batch. NEVER a blanket `connection.rollback()` —
that would also discard the previous, already-committed items' work.

HUMAN-REVIEW PROTECTION — `run_batch()` always calls `enrich_story()`
with `allow_overwrite_reviewed=False` and does not expose any way to
override that. A rejected item hitting the review-protection gate
(`IllustrationUnitReviewProtectionError`, surfaced by `enrich_story` as
`status="rejected"`) is recorded exactly like any other rejection —
there is no batch-level mechanism, resume or otherwise, that can bypass
it; the ONLY sanctioned override
(`update_draft_unit(..., allow_overwrite_reviewed=True)`) remains a
single-unit, explicit, out-of-band call this module never makes.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from illustration_engine.enrichment_pipeline import EnrichmentResult, derive_enrichment_strategy, enrich_story
from illustration_engine.illustration_sqlite import (
    insert_enrichment_run,
    insert_enrichment_run_item,
    update_enrichment_run,
    update_enrichment_run_item,
)

ALLOWED_STRATEGY_BANDS: frozenset[str] = frozenset({"A", "B", "C"})


class EnrichmentRunAlreadyRunningError(ValueError):
    """Raised by `run_batch()` when the target run's `overall_status` is
    already `'running'` — see the module docstring's CONCURRENCY MODEL
    section. Subclasses `ValueError`, matching
    `IllustrationLicenseGateError`/`IllustrationUnitReviewProtectionError`
    in `illustration_sqlite.py`."""


@dataclass(frozen=True)
class RunView:
    id: int
    started_at: str
    finished_at: str | None
    model_identifier: str
    prompt_version: str
    source_code: str | None
    strategy_band: str | None
    requested_limit: int | None
    overall_status: str
    selection_metadata_json: str | None


@dataclass(frozen=True)
class RunItemView:
    id: int
    run_id: int
    story_id: int
    expected_mode: str
    status: str
    illustration_unit_id: int | None
    error_message: str | None
    # Parsed from warnings_json so no caller ever hand-parses raw JSON --
    # same convention as IllustrationUnitView.enrichment_warnings.
    warnings: tuple[str, ...]
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class BatchRunSummary:
    run_id: int
    overall_status: str
    processed_count: int
    success_count: int
    warning_count: int
    rejected_count: int
    proposal_ready_count: int
    failed_count: int
    skipped_count: int


def _band_letter_for_length(length: int) -> str:
    strategy = derive_enrichment_strategy(length)
    if strategy.expected_mode == "unit_proposal":
        return "C"
    return "A" if strategy.expected_derivation_type == "full_story_translation" else "B"


def _row_to_run_view(row: tuple) -> RunView:
    return RunView(*row)


_RUN_COLUMNS = (
    "id",
    "started_at",
    "finished_at",
    "model_identifier",
    "prompt_version",
    "source_code",
    "strategy_band",
    "requested_limit",
    "overall_status",
    "selection_metadata_json",
)

_RUN_ITEM_COLUMNS = (
    "id",
    "run_id",
    "story_id",
    "expected_mode",
    "status",
    "illustration_unit_id",
    "error_message",
    "warnings_json",
    "started_at",
    "finished_at",
)


def _row_to_run_item_view(row: tuple) -> RunItemView:
    values = dict(zip(_RUN_ITEM_COLUMNS, row))
    raw_warnings_json = values.pop("warnings_json")
    values["warnings"] = tuple(json.loads(raw_warnings_json)) if raw_warnings_json else ()
    return RunItemView(**values)


def get_run(connection: sqlite3.Connection, run_id: int) -> RunView | None:
    row = connection.execute(
        f"SELECT {', '.join(_RUN_COLUMNS)} FROM enrichment_runs WHERE id = ?", (run_id,)
    ).fetchone()
    return _row_to_run_view(row) if row else None


def mark_run_interrupted(connection: sqlite3.Connection, run_id: int) -> None:
    """Explicit, operator/recovery-script-only action: asserts that the
    process which set this run to `'running'` is no longer actually
    running (a hard crash, a killed process, a dead machine — something
    that never got the chance to call `run_batch()`'s own normal
    completion/exception handling) and transitions it to `'interrupted'`,
    committing immediately.

    This is the ONLY way a `'running'` run becomes resumable again — see
    the module docstring CONCURRENCY MODEL section. There is deliberately
    no automatic/time-based staleness detection here: nothing in this
    module ever decides on its own that a run "looks old enough" to be
    dead. A human (or an explicit recovery script acting on a human's
    behalf) must make this exact call, asserting they have verified the
    previous process is actually gone.

    Raises `ValueError` if the run does not exist, or if it is not
    currently `'running'` — marking a run interrupted only makes sense
    while it looks actively in-progress; calling this on an already-
    terminal run (or one that's already `'interrupted'`) is a caller
    mistake, not a normal recovery action."""
    run = get_run(connection, run_id)
    if run is None:
        raise ValueError(f"enrichment run not found: id={run_id}")
    if run.overall_status != "running":
        raise ValueError(
            f"cannot mark run id={run_id} interrupted: overall_status is {run.overall_status!r}, "
            "not 'running'"
        )
    update_enrichment_run(
        connection, run_id=run_id, overall_status="interrupted", finished_at=datetime.now(UTC).isoformat()
    )
    connection.commit()


def list_run_items(connection: sqlite3.Connection, run_id: int) -> list[RunItemView]:
    rows = connection.execute(
        f"SELECT {', '.join(_RUN_ITEM_COLUMNS)} FROM enrichment_run_items WHERE run_id = ? ORDER BY id ASC",
        (run_id,),
    ).fetchall()
    return [_row_to_run_item_view(row) for row in rows]


def create_run(
    connection: sqlite3.Connection,
    *,
    model_identifier: str,
    prompt_version: str,
    source_code: str,
    strategy_band: str,
    limit: int,
) -> int:
    """Deterministically selects up to `limit` stories from `source_code`
    whose `derive_enrichment_strategy()` band matches `strategy_band`
    ('A'/'B'/'C'), ordered by `story_id ASC`, and freezes that exact
    selection into `enrichment_run_items` (all `status='pending'`) in the
    same call. See the module docstring's DETERMINISTIC SELECTION
    section — this is the ONLY place the batch's story list is decided;
    `run_batch()` never re-queries it."""
    if strategy_band not in ALLOWED_STRATEGY_BANDS:
        raise ValueError(f"strategy_band must be one of {sorted(ALLOWED_STRATEGY_BANDS)}, got {strategy_band!r}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit!r}")

    rows = connection.execute(
        """
        SELECT st.id, LENGTH(st.original_text)
        FROM stories st JOIN sources s ON s.id = st.source_id
        WHERE s.code = ?
        ORDER BY st.id ASC
        """,
        (source_code,),
    ).fetchall()

    selected: list[tuple[int, str]] = []  # (story_id, expected_mode)
    for story_id, length in rows:
        if _band_letter_for_length(length) != strategy_band:
            continue
        strategy = derive_enrichment_strategy(length)
        selected.append((story_id, strategy.expected_mode))
        if len(selected) >= limit:
            break

    now = datetime.now(UTC).isoformat()
    connection.execute("SAVEPOINT create_enrichment_run")
    try:
        run_id = insert_enrichment_run(
            connection,
            model_identifier=model_identifier,
            prompt_version=prompt_version,
            source_code=source_code,
            strategy_band=strategy_band,
            requested_limit=limit,
            overall_status="created",
            selection_metadata_json=json.dumps({"story_ids": [sid for sid, _ in selected]}),
            started_at=now,
        )
        for story_id, expected_mode in selected:
            insert_enrichment_run_item(
                connection, run_id=run_id, story_id=story_id, expected_mode=expected_mode, status="pending"
            )
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT create_enrichment_run")
        connection.execute("RELEASE SAVEPOINT create_enrichment_run")
        raise
    else:
        connection.execute("RELEASE SAVEPOINT create_enrichment_run")
    connection.commit()
    return run_id


def _map_result_to_item_status(result: EnrichmentResult) -> str:
    if result.status == "unit_created":
        return "warning" if result.warnings else "success"
    if result.status in ("proposal_ready", "rejected"):
        return result.status
    raise ValueError(f"unexpected EnrichmentResult.status: {result.status!r}")


def _process_one_item(
    connection: sqlite3.Connection, *, item: RunItemView, run: RunView, llm_generate: Callable[[str], str]
) -> str:
    started_at = datetime.now(UTC).isoformat()
    # Marked 'running' and committed BEFORE enrich_story() is even
    # called -- see module docstring CRASH / STALE-RUNNING RESUME
    # SEMANTICS. If the process is killed while enrich_story() is
    # executing (a real crash, not a caught Python exception), this is
    # the durable record a later resume finds: the item is neither
    # untouched ('pending') nor cleanly finished, so it must be retried,
    # exactly like a 'failed' item.
    update_enrichment_run_item(
        connection,
        item_id=item.id,
        status="running",
        illustration_unit_id=None,
        error_message=None,
        warnings_json=None,
        started_at=started_at,
    )
    connection.commit()

    connection.execute("SAVEPOINT batch_item")
    try:
        result = enrich_story(
            connection,
            story_id=item.story_id,
            llm_generate=llm_generate,
            model_identifier=run.model_identifier,
            prompt_version=run.prompt_version,
            expected_mode=item.expected_mode,
            # Never overridable from a batch -- see module docstring's
            # HUMAN-REVIEW PROTECTION section.
            allow_overwrite_reviewed=False,
        )
        item_status = _map_result_to_item_status(result)
        update_enrichment_run_item(
            connection,
            item_id=item.id,
            status=item_status,
            illustration_unit_id=result.unit_id,
            error_message="; ".join(result.errors) if result.errors else None,
            warnings_json=json.dumps(list(result.warnings)) if result.warnings else None,
            started_at=started_at,
            finished_at=datetime.now(UTC).isoformat(),
        )
    except Exception as exc:  # noqa: BLE001 - story-level isolation: one bad story must not stop the batch
        connection.execute("ROLLBACK TO SAVEPOINT batch_item")
        connection.execute("RELEASE SAVEPOINT batch_item")
        update_enrichment_run_item(
            connection,
            item_id=item.id,
            status="failed",
            illustration_unit_id=None,
            error_message=str(exc),
            warnings_json=None,
            started_at=started_at,
            finished_at=datetime.now(UTC).isoformat(),
        )
        connection.commit()
        return "failed"
    else:
        connection.execute("RELEASE SAVEPOINT batch_item")
        connection.commit()
        return item_status


def run_batch(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    llm_generate: Callable[[str], str],
    retry_rejected: bool = False,
) -> BatchRunSummary:
    """Processes every eligible item of an existing run — this is BOTH
    the initial execution path AND the resume path (see module docstring
    RESUME/RETRY POLICY section): calling this again on a `completed`,
    `completed_with_errors`, or `interrupted` run (with `retry_rejected=
    True` to also retry rejections) is the entire resume mechanism, with
    no separate function or state to manage. It is NOT the way to resume
    a run whose `overall_status` is still `running` — see the module
    docstring's CONCURRENCY MODEL section and
    `EnrichmentRunAlreadyRunningError`.

    A story-level exception is always isolated (see FAULT ISOLATION) —
    it can never stop the batch or corrupt an earlier item's already-
    committed result. `allow_overwrite_reviewed` is never exposed here;
    the human-review gate cannot be bypassed from a batch, ever."""
    run = get_run(connection, run_id)
    if run is None:
        raise ValueError(f"enrichment run not found: id={run_id}")

    if run.overall_status == "running":
        raise EnrichmentRunAlreadyRunningError(
            f"enrichment run id={run_id} is already 'running' — a second, concurrent run_batch() "
            "call on the same run is not allowed (single-runner-per-run contract, see module "
            "docstring). If the process that started it has actually crashed, call "
            "mark_run_interrupted(connection, run_id) first to explicitly recover it, then call "
            "run_batch() again."
        )

    # 'running' items are ONLY eligible when resuming a run explicitly
    # recovered via mark_run_interrupted() — see module docstring
    # CONCURRENCY MODEL. A 'created'/'completed'/'completed_with_errors'
    # run should never legitimately have any 'running' items (the guard
    # above already refuses to let two run_batch() calls overlap on the
    # same run), so this stays narrowly scoped to the one case it exists
    # for: genuine post-crash recovery.
    was_interrupted = run.overall_status == "interrupted"

    items = list_run_items(connection, run_id)
    eligible_statuses = {"pending", "failed"} | ({"rejected"} if retry_rejected else set())
    if was_interrupted:
        eligible_statuses.add("running")
    to_process = [item for item in items if item.status in eligible_statuses]
    skipped_count = len(items) - len(to_process)

    update_enrichment_run(connection, run_id=run_id, overall_status="running")
    connection.commit()

    counts = {"success": 0, "warning": 0, "rejected": 0, "proposal_ready": 0, "failed": 0}
    try:
        for item in to_process:
            outcome_status = _process_one_item(connection, item=item, run=run, llm_generate=llm_generate)
            counts[outcome_status] += 1
    except BaseException:
        # Should not normally happen -- _process_one_item isolates every
        # per-item exception already -- but if something still escapes
        # (e.g. a bug in this loop itself, or a KeyboardInterrupt), the
        # run must not be left stuck at "running" forever with no record
        # of what happened; mark it interrupted and let the exception
        # continue to propagate to the caller.
        update_enrichment_run(
            connection, run_id=run_id, overall_status="interrupted", finished_at=datetime.now(UTC).isoformat()
        )
        connection.commit()
        raise

    overall_status = (
        "completed" if counts["rejected"] == 0 and counts["failed"] == 0 else "completed_with_errors"
    )
    update_enrichment_run(
        connection, run_id=run_id, overall_status=overall_status, finished_at=datetime.now(UTC).isoformat()
    )
    connection.commit()

    return BatchRunSummary(
        run_id=run_id,
        overall_status=overall_status,
        processed_count=sum(counts.values()),
        success_count=counts["success"],
        warning_count=counts["warning"],
        rejected_count=counts["rejected"],
        proposal_ready_count=counts["proposal_ready"],
        failed_count=counts["failed"],
        skipped_count=skipped_count,
    )


__all__ = [
    "ALLOWED_STRATEGY_BANDS",
    "BatchRunSummary",
    "EnrichmentRunAlreadyRunningError",
    "RunItemView",
    "RunView",
    "create_run",
    "get_run",
    "list_run_items",
    "mark_run_interrupted",
    "run_batch",
]
