"""Dev-only shadow audit store (SQLite) for Phase 5B reporting."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.paths import GENERATED_DATA_DIR

SHADOW_STORE_FLAG = "TEXTUS_KB_SHADOW_STORE_ENABLED"
SCHEMA_VERSION = "1"
DEFAULT_AUDIT_DB_PATH = GENERATED_DATA_DIR / "kb_shadow_audit.sqlite3"

# Never persist these keys if present on an artifact/event dict.
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "bearer",
        "credential",
        "password",
        "email",
        "user_id",
        "account_id",
        "session_id",
        "session_token",
        "production_prompt",
        "production_output",
        "user_prompt",
        "prompt",
        "output",
        "context_packet",
        "evidence_ids",
        "evidence_packet",
        "entities",
        "evidence_items",
    }
)


@dataclass(frozen=True)
class ShadowAuditRecord:
    schema_version: str
    run_id: str
    timestamp: str
    canonical_passage: str
    module: str
    profile: str
    evidence_build_id: str
    context_schema_version: str
    source_ids: list[str]
    evidence_count: int
    entity_count: int
    selected_item_count: int
    context_tokens: int
    retrieval_ms: int
    context_build_ms: int
    warning_count: int
    status: str
    production_prompt_chars: int
    production_output_chars: int
    generation_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_shadow_store_enabled() -> bool:
    raw = (os.getenv(SHADOW_STORE_FLAG, "false") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shadow_runs (
            run_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            canonical_passage TEXT NOT NULL,
            module TEXT NOT NULL,
            profile TEXT NOT NULL,
            evidence_build_id TEXT NOT NULL,
            context_schema_version TEXT NOT NULL,
            source_ids_json TEXT NOT NULL,
            evidence_count INTEGER NOT NULL,
            entity_count INTEGER NOT NULL,
            selected_item_count INTEGER NOT NULL,
            context_tokens INTEGER NOT NULL,
            retrieval_ms INTEGER NOT NULL,
            context_build_ms INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            production_prompt_chars INTEGER NOT NULL,
            production_output_chars INTEGER NOT NULL,
            generation_ms INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_shadow_runs_passage
            ON shadow_runs(canonical_passage);
        CREATE INDEX IF NOT EXISTS idx_shadow_runs_module_profile
            ON shadow_runs(module, profile);
        CREATE INDEX IF NOT EXISTS idx_shadow_runs_timestamp
            ON shadow_runs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_shadow_runs_status
            ON shadow_runs(status);
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO store_metadata(key, value) VALUES (?, ?)",
        ("schema_version", SCHEMA_VERSION),
    )


def artifact_to_audit_record(artifact: dict[str, Any]) -> ShadowAuditRecord:
    """Map a shadow artifact dict to a privacy-safe audit record.

    Input may contain large transient fields (`context_packet`, prompt/output
    strings used only for length metrics). Those are never persisted.
    """
    comparison = artifact.get("comparison") if isinstance(artifact.get("comparison"), dict) else {}
    context_packet = artifact.get("context_packet") if isinstance(artifact.get("context_packet"), dict) else {}
    source_ids = [str(item) for item in (artifact.get("source_ids") or [])]

    prompt_chars = int(
        comparison.get("production_prompt_chars")
        or artifact.get("production_prompt_chars")
        or 0
    )
    output_chars = int(
        comparison.get("production_output_chars")
        or artifact.get("production_output_chars")
        or 0
    )

    return ShadowAuditRecord(
        schema_version=SCHEMA_VERSION,
        run_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        canonical_passage=str(artifact.get("passage_canonical") or ""),
        module=str(artifact.get("module") or ""),
        profile=str(artifact.get("profile") or ""),
        evidence_build_id=str(artifact.get("evidence_packet_build_id") or ""),
        context_schema_version=str(context_packet.get("schema_version") or ""),
        source_ids=source_ids,
        evidence_count=int(artifact.get("evidence_item_count") or 0),
        entity_count=int(artifact.get("entity_count") or 0),
        selected_item_count=int(artifact.get("selected_context_count") or 0),
        context_tokens=int(artifact.get("token_estimate") or 0),
        retrieval_ms=int(artifact.get("retrieval_duration_ms") or 0),
        context_build_ms=int(artifact.get("context_build_duration_ms") or 0),
        warning_count=len(artifact.get("retrieval_warnings") or []),
        status=str(artifact.get("status") or ("success" if artifact.get("success") else "error")),
        production_prompt_chars=prompt_chars,
        production_output_chars=output_chars,
        generation_ms=int(artifact.get("generation_duration_ms") or 0),
    )


def assert_record_privacy_safe(record: ShadowAuditRecord | dict[str, Any]) -> None:
    payload = record.to_dict() if isinstance(record, ShadowAuditRecord) else dict(record)
    for key in FORBIDDEN_PAYLOAD_KEYS:
        assert key not in payload, f"Forbidden key present in audit record: {key}"
    # Length metrics only — never raw text.
    assert isinstance(payload.get("production_prompt_chars"), int)
    assert isinstance(payload.get("production_output_chars"), int)


def persist_shadow_audit(
    artifact: dict[str, Any],
    *,
    database_path: str | Path | None = None,
    enabled: bool | None = None,
) -> ShadowAuditRecord | None:
    """Persist a privacy-safe audit row when the store flag is enabled.

    Returns the written record, or None when persistence is disabled.
    Raises on hard write failures so callers can isolate them.
    """
    if enabled is None:
        enabled = is_shadow_store_enabled()
    if not enabled:
        return None

    record = artifact_to_audit_record(artifact)
    path = Path(database_path) if database_path is not None else DEFAULT_AUDIT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        create_schema(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO shadow_runs (
                    run_id, schema_version, timestamp, canonical_passage, module, profile,
                    evidence_build_id, context_schema_version, source_ids_json,
                    evidence_count, entity_count, selected_item_count, context_tokens,
                    retrieval_ms, context_build_ms, warning_count, status,
                    production_prompt_chars, production_output_chars, generation_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.schema_version,
                    record.timestamp,
                    record.canonical_passage,
                    record.module,
                    record.profile,
                    record.evidence_build_id,
                    record.context_schema_version,
                    json.dumps(record.source_ids, ensure_ascii=True),
                    record.evidence_count,
                    record.entity_count,
                    record.selected_item_count,
                    record.context_tokens,
                    record.retrieval_ms,
                    record.context_build_ms,
                    record.warning_count,
                    record.status,
                    record.production_prompt_chars,
                    record.production_output_chars,
                    record.generation_ms,
                ),
            )
    return record


def load_shadow_runs(
    *,
    database_path: str | Path | None = None,
    canonical_passage: str | None = None,
    module: str | None = None,
) -> list[dict[str, Any]]:
    path = Path(database_path) if database_path is not None else DEFAULT_AUDIT_DB_PATH
    if not path.is_file():
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if canonical_passage:
        clauses.append("canonical_passage = ?")
        params.append(canonical_passage)
    if module:
        clauses.append("module = ?")
        params.append(module)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT *
        FROM shadow_runs
        {where}
        ORDER BY timestamp ASC, run_id ASC
    """
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, tuple(params)).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["source_ids"] = json.loads(item.pop("source_ids_json") or "[]")
        results.append(item)
    return results


def classify_source_mix(source_ids: list[str]) -> dict[str, int]:
    buckets = {
        "linguistic": 0,
        "study_notes": 0,
        "dictionary": 0,
        "acai": 0,
        "places_background": 0,
        "other": 0,
    }
    for source_id in source_ids:
        sid = str(source_id)
        if sid in {"stepbible_tagnt", "stepbible_tahot", "stepbible_tbesg", "stepbible_tbesh", "lexicon_hu_overlay"}:
            buckets["linguistic"] += 1
        elif sid == "aquifer_open_study_notes":
            buckets["study_notes"] += 1
        elif sid == "aquifer_open_bible_dictionary":
            buckets["dictionary"] += 1
        elif sid == "acai":
            buckets["acai"] += 1
        elif "place" in sid or sid.endswith("_enrichment") or "background" in sid:
            buckets["places_background"] += 1
        else:
            buckets["other"] += 1
    return buckets
