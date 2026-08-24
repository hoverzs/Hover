"""Dev-only A/B compare store (Phase 5E). Separate from privacy-limited shadow audit."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.paths import GENERATED_DATA_DIR

COMPARE_STORE_FLAG = "TEXTUS_KB_COMPARE_STORE_ENABLED"
COMPARE_SCHEMA_VERSION = "1"
DEFAULT_COMPARE_DB_PATH = GENERATED_DATA_DIR / "kb_grounded_compare.sqlite3"

REVIEW_CHOICES = frozenset({"A", "B", "equal", "unclear"})
HALLUCINATION_CHOICES = frozenset({"A", "B", "both", "neither", "unclear"})


@dataclass
class HumanReview:
    factual_accuracy_preference: str = ""
    exegetical_usefulness_preference: str = ""
    historical_grounding_preference: str = ""
    clarity_style_preference: str = ""
    hallucination_risk: str = ""
    overall_preference: str = ""
    reviewer_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> HumanReview:
        if not isinstance(payload, dict):
            return cls()
        return cls(
            factual_accuracy_preference=str(payload.get("factual_accuracy_preference") or ""),
            exegetical_usefulness_preference=str(
                payload.get("exegetical_usefulness_preference") or ""
            ),
            historical_grounding_preference=str(
                payload.get("historical_grounding_preference") or ""
            ),
            clarity_style_preference=str(payload.get("clarity_style_preference") or ""),
            hallucination_risk=str(payload.get("hallucination_risk") or ""),
            overall_preference=str(payload.get("overall_preference") or ""),
            reviewer_notes=str(payload.get("reviewer_notes") or ""),
        )


def is_compare_store_enabled() -> bool:
    raw = (os.getenv(COMPARE_STORE_FLAG, "false") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def create_compare_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compare_runs (
            run_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            passage TEXT NOT NULL,
            module TEXT NOT NULL,
            provider_model TEXT NOT NULL DEFAULT '',
            production_prompt_estimated_tokens INTEGER NOT NULL DEFAULT 0,
            grounded_prompt_estimated_tokens INTEGER NOT NULL DEFAULT 0,
            kb_context_estimated_tokens INTEGER NOT NULL DEFAULT 0,
            production_latency_ms INTEGER NOT NULL DEFAULT 0,
            grounded_prep_ms INTEGER NOT NULL DEFAULT 0,
            grounded_latency_ms INTEGER NOT NULL DEFAULT 0,
            provider_call_count INTEGER NOT NULL DEFAULT 0,
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            source_trace_json TEXT NOT NULL DEFAULT '{}',
            production_output TEXT NOT NULL DEFAULT '',
            grounded_output TEXT NOT NULL DEFAULT '',
            grounded_status TEXT NOT NULL DEFAULT '',
            grounded_error TEXT NOT NULL DEFAULT '',
            prompt_hash_a TEXT NOT NULL DEFAULT '',
            prompt_hash_b TEXT NOT NULL DEFAULT '',
            composition_version TEXT NOT NULL DEFAULT '',
            evidence_build_id TEXT NOT NULL DEFAULT '',
            blind INTEGER NOT NULL DEFAULT 0,
            blind_mapping_json TEXT NOT NULL DEFAULT '{}',
            review_json TEXT NOT NULL DEFAULT '{}',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            artifact_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_compare_runs_passage
            ON compare_runs(passage);
        CREATE INDEX IF NOT EXISTS idx_compare_runs_module
            ON compare_runs(module);
        CREATE INDEX IF NOT EXISTS idx_compare_runs_timestamp
            ON compare_runs(timestamp);
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO store_metadata(key, value) VALUES (?, ?)",
        ("schema_version", COMPARE_SCHEMA_VERSION),
    )


def persist_compare_run(
    artifact: dict[str, Any],
    *,
    database_path: str | Path | None = None,
    enabled: bool | None = None,
) -> str | None:
    """Persist a compare artifact when the compare-store flag is enabled.

    Returns run_id or None when disabled. Raises on hard write failures
    (callers should isolate). Never writes to the Phase 5B shadow audit DB.
    """
    if enabled is None:
        enabled = is_compare_store_enabled()
    if not enabled:
        return None

    run_id = str(artifact.get("run_id") or uuid.uuid4())
    path = Path(database_path) if database_path is not None else DEFAULT_COMPARE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    review = artifact.get("review") if isinstance(artifact.get("review"), dict) else {}
    with sqlite3.connect(path) as connection:
        create_compare_schema(connection)
        with connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO compare_runs (
                    run_id, schema_version, timestamp, passage, module, provider_model,
                    production_prompt_estimated_tokens, grounded_prompt_estimated_tokens,
                    kb_context_estimated_tokens, production_latency_ms, grounded_prep_ms,
                    grounded_latency_ms, provider_call_count, source_ids_json,
                    evidence_ids_json, source_trace_json, production_output, grounded_output,
                    grounded_status, grounded_error, prompt_hash_a, prompt_hash_b,
                    composition_version, evidence_build_id, blind, blind_mapping_json,
                    review_json, metrics_json, artifact_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    COMPARE_SCHEMA_VERSION,
                    str(artifact.get("timestamp") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
                    str(artifact.get("passage") or ""),
                    str(artifact.get("module") or ""),
                    str(artifact.get("provider_model") or artifact.get("model_note") or ""),
                    int(artifact.get("production_prompt_estimated_tokens") or 0),
                    int(artifact.get("grounded_prompt_estimated_tokens") or 0),
                    int(artifact.get("kb_context_estimated_tokens") or 0),
                    int(artifact.get("production_latency_ms") or 0),
                    int(artifact.get("grounded_prep_ms") or 0),
                    int(artifact.get("grounded_latency_ms") or 0),
                    int(artifact.get("provider_call_count") or 0),
                    json.dumps(artifact.get("source_ids") or [], ensure_ascii=True),
                    json.dumps(artifact.get("evidence_ids") or [], ensure_ascii=True),
                    json.dumps(artifact.get("source_trace") or {}, ensure_ascii=True),
                    str(artifact.get("production_output") or ""),
                    str(artifact.get("grounded_output") or ""),
                    str(artifact.get("grounded_status") or ""),
                    str(artifact.get("grounded_error") or ""),
                    str(artifact.get("prompt_hash_a") or ""),
                    str(artifact.get("prompt_hash_b") or ""),
                    str(artifact.get("composition_version") or ""),
                    str(artifact.get("evidence_build_id") or ""),
                    1 if artifact.get("blind") else 0,
                    json.dumps(artifact.get("blind_mapping") or {}, ensure_ascii=True),
                    json.dumps(review, ensure_ascii=True),
                    json.dumps(artifact.get("metrics") or {}, ensure_ascii=True),
                    json.dumps(artifact, ensure_ascii=True),
                ),
            )
    return run_id


def load_compare_run(
    run_id: str,
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    path = Path(database_path) if database_path is not None else DEFAULT_COMPARE_DB_PATH
    if not path.is_file():
        return None
    with sqlite3.connect(path) as connection:
        create_compare_schema(connection)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM compare_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_artifact(dict(row))


def list_compare_runs(
    *,
    database_path: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = Path(database_path) if database_path is not None else DEFAULT_COMPARE_DB_PATH
    if not path.is_file():
        return []
    with sqlite3.connect(path) as connection:
        create_compare_schema(connection)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT run_id, timestamp, passage, module, grounded_status,
                   provider_call_count, review_json, blind
            FROM compare_runs
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        review = json.loads(item.pop("review_json") or "{}")
        item["has_review"] = bool(any(str(v).strip() for v in review.values()))
        item["overall_preference"] = str(review.get("overall_preference") or "")
        results.append(item)
    return results


def update_compare_review(
    run_id: str,
    review: HumanReview | dict[str, Any],
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    path = Path(database_path) if database_path is not None else DEFAULT_COMPARE_DB_PATH
    if not path.is_file():
        return None
    payload = review.to_dict() if isinstance(review, HumanReview) else dict(review)
    _validate_review_payload(payload)
    with sqlite3.connect(path) as connection:
        create_compare_schema(connection)
        with connection:
            cur = connection.execute(
                "UPDATE compare_runs SET review_json = ? WHERE run_id = ?",
                (json.dumps(payload, ensure_ascii=True), run_id),
            )
            if cur.rowcount == 0:
                return None
            # Keep artifact_json in sync when present.
            row = connection.execute(
                "SELECT artifact_json FROM compare_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row and row[0]:
                artifact = json.loads(row[0])
                artifact["review"] = payload
                connection.execute(
                    "UPDATE compare_runs SET artifact_json = ? WHERE run_id = ?",
                    (json.dumps(artifact, ensure_ascii=True), run_id),
                )
    return load_compare_run(run_id, database_path=path)


def _validate_review_payload(payload: dict[str, Any]) -> None:
    for key in (
        "factual_accuracy_preference",
        "exegetical_usefulness_preference",
        "historical_grounding_preference",
        "clarity_style_preference",
        "overall_preference",
    ):
        value = str(payload.get(key) or "").strip()
        if value and value not in REVIEW_CHOICES:
            raise ValueError(f"Invalid {key}: {value!r}; expected one of {sorted(REVIEW_CHOICES)}")
    risk = str(payload.get("hallucination_risk") or "").strip()
    if risk and risk not in HALLUCINATION_CHOICES:
        raise ValueError(
            f"Invalid hallucination_risk: {risk!r}; expected one of {sorted(HALLUCINATION_CHOICES)}"
        )
    # review_updated_at and reviewer_notes are free-form / optional metadata.


def _row_to_artifact(row: dict[str, Any]) -> dict[str, Any]:
    artifact = json.loads(row.get("artifact_json") or "{}")
    if not artifact:
        artifact = {
            "run_id": row.get("run_id"),
            "schema_version": row.get("schema_version"),
            "timestamp": row.get("timestamp"),
            "passage": row.get("passage"),
            "module": row.get("module"),
            "provider_model": row.get("provider_model"),
            "production_prompt_estimated_tokens": row.get("production_prompt_estimated_tokens"),
            "grounded_prompt_estimated_tokens": row.get("grounded_prompt_estimated_tokens"),
            "kb_context_estimated_tokens": row.get("kb_context_estimated_tokens"),
            "production_latency_ms": row.get("production_latency_ms"),
            "grounded_prep_ms": row.get("grounded_prep_ms"),
            "grounded_latency_ms": row.get("grounded_latency_ms"),
            "provider_call_count": row.get("provider_call_count"),
            "source_ids": json.loads(row.get("source_ids_json") or "[]"),
            "evidence_ids": json.loads(row.get("evidence_ids_json") or "[]"),
            "source_trace": json.loads(row.get("source_trace_json") or "{}"),
            "production_output": row.get("production_output"),
            "grounded_output": row.get("grounded_output"),
            "grounded_status": row.get("grounded_status"),
            "grounded_error": row.get("grounded_error"),
            "prompt_hash_a": row.get("prompt_hash_a"),
            "prompt_hash_b": row.get("prompt_hash_b"),
            "composition_version": row.get("composition_version"),
            "evidence_build_id": row.get("evidence_build_id"),
            "blind": bool(row.get("blind")),
            "blind_mapping": json.loads(row.get("blind_mapping_json") or "{}"),
            "metrics": json.loads(row.get("metrics_json") or "{}"),
        }
    artifact["review"] = json.loads(row.get("review_json") or "{}")
    artifact["run_id"] = row.get("run_id")
    return artifact


__all__ = [
    "COMPARE_SCHEMA_VERSION",
    "COMPARE_STORE_FLAG",
    "DEFAULT_COMPARE_DB_PATH",
    "HALLUCINATION_CHOICES",
    "HumanReview",
    "REVIEW_CHOICES",
    "create_compare_schema",
    "is_compare_store_enabled",
    "list_compare_runs",
    "load_compare_run",
    "persist_compare_run",
    "update_compare_review",
]
