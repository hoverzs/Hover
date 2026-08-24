"""Phase 5B shadow audit store and reporting tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.shadow import run_kb_shadow_artifact_dict, run_kb_shadow_for_module
from textus_kb.shadow_audit import (
    SHADOW_STORE_FLAG,
    SCHEMA_VERSION,
    assert_record_privacy_safe,
    artifact_to_audit_record,
    is_shadow_store_enabled,
    load_shadow_runs,
    persist_shadow_audit,
)
from textus_kb.shadow_integration import run_production_with_optional_shadow
from textus_kb.shadow_report import build_shadow_compare, build_shadow_report


def test_store_flag_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SHADOW_STORE_FLAG, raising=False)
    assert is_shadow_store_enabled() is False


def test_flag_false_no_persistence_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SHADOW_STORE_FLAG, "false")
    db = tmp_path / "audit.sqlite3"
    artifact = run_kb_shadow_for_module("Jn 4,1-42", module="exegesis").to_dict()
    written = persist_shadow_audit(artifact, database_path=db, enabled=False)
    assert written is None
    assert not db.exists()


def test_flag_true_writes_audit_record(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    artifact = run_kb_shadow_for_module(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="PROMPT-TEXT",
        production_output="OUTPUT-TEXT",
    ).to_dict()
    written = persist_shadow_audit(artifact, database_path=db, enabled=True)
    assert written is not None
    assert written.schema_version == SCHEMA_VERSION
    assert written.canonical_passage == "John.4.1-42"
    assert written.module == "exegesis"
    assert written.production_prompt_chars == len("PROMPT-TEXT")
    assert written.production_output_chars == len("OUTPUT-TEXT")
    assert_record_privacy_safe(written)
    rows = load_shadow_runs(database_path=db)
    assert len(rows) == 1
    assert rows[0]["canonical_passage"] == "John.4.1-42"
    # Ensure raw text never lands in DB columns.
    with sqlite3.connect(db) as connection:
        dumped = " ".join(str(cell) for row in connection.execute("SELECT * FROM shadow_runs") for cell in row)
    assert "PROMPT-TEXT" not in dumped
    assert "OUTPUT-TEXT" not in dumped


def test_schema_indexes_exist(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    artifact = run_kb_shadow_for_module("Lk 10,25-37", module="historical_context").to_dict()
    persist_shadow_audit(artifact, database_path=db, enabled=True)
    with sqlite3.connect(db) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_shadow_runs_passage" in names
    assert "idx_shadow_runs_module_profile" in names
    assert "idx_shadow_runs_timestamp" in names
    assert "idx_shadow_runs_status" in names


def test_passage_and_module_filters(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    for passage, module in [
        ("Jn 4,1-42", "exegesis"),
        ("Jn 4,1-42", "historical_context"),
        ("Lk 10,25-37", "exegesis"),
    ]:
        persist_shadow_audit(
            run_kb_shadow_for_module(passage, module=module).to_dict(),
            database_path=db,
            enabled=True,
        )
    john = CanonicalReference.parse("Jn 4,1–42").canonical_string()
    report = build_shadow_report(database_path=str(db), passage="Jn 4,1–42")
    assert report["run_count"] == 2
    assert report["filters"]["passage"] == john
    report_ex = build_shadow_report(database_path=str(db), module="exegesis")
    assert report_ex["run_count"] == 2
    assert report_ex["by_module"] == {"exegesis": 2}


def test_report_deterministic(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    persist_shadow_audit(
        run_kb_shadow_for_module("Acts.2.1-13", module="exegesis").to_dict(),
        database_path=db,
        enabled=True,
    )
    first = json.dumps(build_shadow_report(database_path=str(db)), sort_keys=True)
    second = json.dumps(build_shadow_report(database_path=str(db)), sort_keys=True)
    assert first == second


def test_comparison_report(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    for module in ("exegesis", "historical_context"):
        persist_shadow_audit(
            run_kb_shadow_for_module(
                "Rom.8.28-30",
                module=module,
                production_prompt="x" * 10,
                production_output="y" * 20,
            ).to_dict(),
            database_path=db,
            enabled=True,
        )
    compare = build_shadow_compare("Rom.8.28-30", database_path=str(db))
    assert compare["passage"] == "Rom.8.28-30"
    assert compare["modules"]["exegesis"]["run_count"] == 1
    assert compare["modules"]["historical_context"]["run_count"] == 1
    latest = compare["modules"]["exegesis"]["latest"]
    assert latest["production_prompt_chars"] == 10
    assert latest["production_output_chars"] == 20
    assert "latency_overhead_ms" in latest


def test_persistence_failure_does_not_break_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SHADOW_STORE_FLAG, "true")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("textus_kb.shadow_audit.persist_shadow_audit", boom)

    calls: list[dict] = []

    def fake_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(
            {
                "prompt": prompt,
                "enable_google_search": enable_google_search,
                "tab_label": tab_label,
            }
        )
        return "PROD"

    result = run_production_with_optional_shadow(
        key="exegesis",
        prompt="PROMPT",
        tab_label="Exegézis",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=True,
        generate_text_fn=fake_generate,
        shadow_runner_fn=run_kb_shadow_artifact_dict,
    )
    assert result.production_output == "PROD"
    assert calls == [
        {"prompt": "PROMPT", "enable_google_search": False, "tab_label": "Exegézis"}
    ]
    assert result.shadow_event is not None
    assert "audit_persist_error" in result.shadow_event


def test_artifact_mapping_privacy() -> None:
    artifact = {
        "status": "success",
        "success": True,
        "module": "exegesis",
        "profile": "exegesis",
        "passage_canonical": "John.4.1-42",
        "evidence_packet_build_id": "kb-x",
        "source_ids": ["acai", "aquifer_open_study_notes"],
        "evidence_item_count": 3,
        "entity_count": 2,
        "selected_context_count": 1,
        "token_estimate": 100,
        "retrieval_duration_ms": 10,
        "context_build_duration_ms": 5,
        "retrieval_warnings": ["w"],
        "comparison": {
            "production_prompt_chars": 12,
            "production_output_chars": 34,
        },
        "context_packet": {"schema_version": "2", "sections": [{"secret": "no"}]},
        "production_prompt": "SHOULD-NOT-PERSIST",
        "production_output": "SHOULD-NOT-PERSIST-EITHER",
    }
    record = artifact_to_audit_record(artifact)
    assert_record_privacy_safe(record)
    dumped = json.dumps(record.to_dict())
    assert "SHOULD-NOT-PERSIST" not in dumped
