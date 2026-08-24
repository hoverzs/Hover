"""Phase 5E human A/B compare review workflow tests."""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

import pytest

from textus_kb.compare_store import (
    COMPARE_STORE_FLAG,
    HumanReview,
    is_compare_store_enabled,
    list_compare_runs,
    load_compare_run,
    persist_compare_run,
    update_compare_review,
)
from textus_kb.grounded_compare import (
    format_compare_report,
    main as compare_main,
    main_review_list,
    main_review_rate,
    main_review_show,
    run_grounded_compare,
    save_compare_export,
)
from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB
from textus_kb.shadow_audit import DEFAULT_AUDIT_DB_PATH, persist_shadow_audit
from textus_kb.shadow_integration import run_production_with_optional_shadow


def test_compare_store_flag_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(COMPARE_STORE_FLAG, raising=False)
    assert is_compare_store_enabled() is False


def test_compare_only_on_explicit_call() -> None:
    calls: list[str] = []

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(tab_label)
        return "x"

    # Normal production path must remain 1 call.
    prod_calls: list[str] = []

    def prod_gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        prod_calls.append(prompt)
        return "PROD"

    result = run_production_with_optional_shadow(
        key="exegesis",
        prompt="P",
        tab_label="Exegézis",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=False,
        generate_text_fn=prod_gen,
        shadow_runner_fn=lambda **kwargs: {},
    )
    assert result.provider_call_count == 1
    assert len(prod_calls) == 1

    artifact = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        generate_text_fn=gen,
    )
    assert artifact.provider_call_count == 2
    assert len(calls) == 2
    assert calls[0].endswith(":A")
    assert calls[1].endswith(":B")


def test_a_is_production_b_is_grounded_when_not_blind() -> None:
    prompts: list[str] = []

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        prompts.append(prompt)
        return f"out-{len(prompts)}"

    artifact = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        generate_text_fn=gen,
        blind=False,
    )
    assert prompts[0] == DRY_RUN_PRODUCTION_STUB
    assert "<<<BEGIN_KB_DATA>>>" in prompts[1]
    assert artifact.blind_mapping == {"A": "production", "B": "grounded"}
    assert artifact.prompt_hash_a
    assert artifact.prompt_hash_b


def test_blind_mode_hides_mapping_in_report() -> None:
    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        kind = "G" if "<<<BEGIN_KB_DATA>>>" in prompt else "P"
        return f"RESPONSE-{kind}"

    artifact = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        generate_text_fn=gen,
        blind=True,
        rng=random.Random(1),
    )
    report = format_compare_report(artifact, reveal_mapping=False)
    assert "RESPONSE A" in report
    assert "RESPONSE B" in report
    assert "blind_mapping" not in report.lower() or "withheld" in report.lower()
    assert "production" not in report.split("RESPONSE A")[1].split("RESPONSE B")[0].lower()
    # Mapping exists only in metadata
    assert artifact.blind_mapping["A"] in {"production", "grounded"}
    assert set(artifact.blind_mapping.values()) == {"production", "grounded"}
    revealed = format_compare_report(artifact, reveal_mapping=True)
    assert "blind_mapping" in revealed


def test_compare_store_persist_and_review(tmp_path: Path) -> None:
    db = tmp_path / "compare.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "text"

    artifact = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        generate_text_fn=gen,
    )
    run_id = persist_compare_run(artifact.to_dict(), database_path=db, enabled=True)
    assert run_id == artifact.run_id
    loaded = load_compare_run(run_id, database_path=db)
    assert loaded is not None
    assert loaded["production_output"] == "text"
    assert loaded["source_trace"]["selected_evidence_count"] >= 0

    updated = update_compare_review(
        run_id,
        HumanReview(
            overall_preference="B",
            factual_accuracy_preference="equal",
            hallucination_risk="neither",
            reviewer_notes="looks fine",
        ),
        database_path=db,
    )
    assert updated is not None
    assert updated["review"]["overall_preference"] == "B"
    rows = list_compare_runs(database_path=db)
    assert rows[0]["has_review"] is True


def test_review_schema_rejects_invalid(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "x"

    artifact = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="P",
        generate_text_fn=gen,
    )
    persist_compare_run(artifact.to_dict(), database_path=db, enabled=True)
    with pytest.raises(ValueError):
        update_compare_review(
            artifact.run_id,
            {"overall_preference": "YES"},
            database_path=db,
        )


def test_outputs_not_in_shadow_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compare_db = tmp_path / "compare.sqlite3"
    audit_db = tmp_path / "audit.sqlite3"
    monkeypatch.setattr("textus_kb.shadow_audit.DEFAULT_AUDIT_DB_PATH", audit_db)

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "FULL_MODEL_OUTPUT_SECRET"

    artifact = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="PROMPT",
        generate_text_fn=gen,
    )
    persist_compare_run(artifact.to_dict(), database_path=compare_db, enabled=True)
    # Shadow audit should not receive full outputs even if someone maps metrics.
    written = persist_shadow_audit(
        {
            "status": "success",
            "module": "exegesis",
            "profile": "exegesis",
            "passage_canonical": artifact.passage,
            "evidence_packet_build_id": artifact.evidence_build_id,
            "source_ids": artifact.source_ids,
            "evidence_item_count": 1,
            "entity_count": 0,
            "selected_context_count": 1,
            "token_estimate": 10,
            "retrieval_duration_ms": 1,
            "context_build_duration_ms": 1,
            "retrieval_warnings": [],
            "comparison": {"production_prompt_chars": 6, "production_output_chars": 10},
            "production_output": "FULL_MODEL_OUTPUT_SECRET",
            "composed_prompt": "FULL_MODEL_OUTPUT_SECRET",
        },
        database_path=audit_db,
        enabled=True,
    )
    assert written is not None
    with sqlite3.connect(audit_db) as connection:
        dumped = " ".join(
            str(cell) for row in connection.execute("SELECT * FROM shadow_runs") for cell in row
        )
    assert "FULL_MODEL_OUTPUT_SECRET" not in dumped
    with sqlite3.connect(compare_db) as connection:
        compare_dump = " ".join(
            str(cell) for row in connection.execute("SELECT * FROM compare_runs") for cell in row
        )
    assert "FULL_MODEL_OUTPUT_SECRET" in compare_dump


def test_grounded_b_failure_keeps_a(monkeypatch: pytest.MonkeyPatch) -> None:
    from textus_kb.grounded_generation import GroundedPreparationResult, STATUS_FALLBACK

    def fake_prep(**kwargs):
        return GroundedPreparationResult(
            status=STATUS_FALLBACK,
            provider_prompt=kwargs["production_prompt"],
            production_prompt=kwargs["production_prompt"],
            grounded_fallback=True,
            fallback_reason="retrieval_error",
            error="RuntimeError",
        )

    monkeypatch.setattr(
        "textus_kb.grounded_compare.prepare_grounded_provider_prompt",
        fake_prep,
    )
    calls: list[str] = []

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(prompt)
        return "A-OUTPUT"

    artifact = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="PROD",
        generate_text_fn=gen,
    )
    assert artifact.production_output == "A-OUTPUT"
    assert artifact.grounded_status == "error"
    assert artifact.grounded_output == ""
    assert artifact.provider_call_count == 1
    assert len(calls) == 1
    assert calls[0] == "PROD"
    report = format_compare_report(artifact)
    assert "A-OUTPUT" in report
    assert "[ERROR]" in report


def test_store_failure_isolated_from_compare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("textus_kb.grounded_compare.persist_compare_run", boom)
    code = compare_main(["Jn 4,1-42", "--module", "exegesis", "--out", str(tmp_path)])
    assert code == 0


def test_cli_review_commands(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "body"

    artifact = run_grounded_compare(
        "Rom.8.28-30",
        module="historical_context",
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        generate_text_fn=gen,
    )
    persist_compare_run(artifact.to_dict(), database_path=db, enabled=True)
    assert main_review_list(["--database", str(db)]) == 0
    assert main_review_show([artifact.run_id, "--database", str(db)]) == 0
    assert (
        main_review_rate(
            [
                artifact.run_id,
                "--database",
                str(db),
                "--overall",
                "equal",
                "--notes",
                "ok",
            ]
        )
        == 0
    )


def test_markdown_export(tmp_path: Path) -> None:
    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "out"

    artifact = run_grounded_compare(
        "Acts.2.1-13",
        module="exegesis",
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        generate_text_fn=gen,
    )
    path = save_compare_export(artifact, tmp_path / "compare.md")
    text = path.read_text(encoding="utf-8")
    assert "PASSAGE:" in text
    assert "RESPONSE A" in text
    assert "METRICS" in text
