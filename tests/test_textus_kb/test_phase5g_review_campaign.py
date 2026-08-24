"""Phase 5G live review campaign workflow tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.compare_store import HumanReview, persist_compare_run, update_compare_review
from textus_kb.grounded_compare import (
    format_compare_report,
    format_source_trace_report,
    main as compare_main,
    main_review_sources,
    run_grounded_compare,
)
from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB as STUB
from textus_kb.review_campaign import (
    REQUIRED_PAIR_COUNT,
    build_campaign_status,
    campaign_manual_commands,
    classify_run_completeness,
    is_readiness_evidence,
    latest_artifacts_by_pair,
    required_campaign_pairs,
)
from textus_kb.shadow_integration import run_production_with_optional_shadow
from textus_kb.staging_readiness import STATUS_INSUFFICIENT, evaluate_staging_readiness


def test_required_campaign_pairs_are_eight() -> None:
    pairs = required_campaign_pairs()
    assert len(pairs) == REQUIRED_PAIR_COUNT == 8
    assert ("John.4.1-42", "exegesis") in pairs
    assert ("Rom.8.28-30", "historical_context") in pairs


def test_live_requires_prompt_file_and_blind(tmp_path: Path) -> None:
    code = compare_main(["Jn 4,1-42", "--module", "exegesis", "--live"])
    assert code == 2
    prompt = tmp_path / "p.txt"
    prompt.write_text("REAL PRODUCTION PROMPT BODY FOR REVIEW", encoding="utf-8")
    code2 = compare_main(
        ["Jn 4,1-42", "--module", "exegesis", "--live", "--prompt-file", str(prompt)]
    )
    assert code2 == 2  # missing --blind


def test_live_rejects_stub_prompt(tmp_path: Path) -> None:
    prompt = tmp_path / "stub.txt"
    prompt.write_text(STUB, encoding="utf-8")
    code = compare_main(
        [
            "Jn 4,1-42",
            "--module",
            "exegesis",
            "--live",
            "--blind",
            "--prompt-file",
            str(prompt),
        ]
    )
    assert code == 2


def test_mock_default_does_not_call_live_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom():
        raise AssertionError("live resolver must not run without --live")

    monkeypatch.setattr("textus_kb.grounded_compare._resolve_live_generate", boom)
    code = compare_main(["Jn 4,1-42", "--module", "exegesis", "--out", str(Path("data/generated/kb_grounded_compare"))])
    assert code == 0


def test_mock_not_campaign_completion(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "mock"

    art = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt=STUB,
        generate_text_fn=gen,
        provider_model="mock",
    )
    persist_compare_run(art.to_dict(), database_path=db, enabled=True)
    status = build_campaign_status(database_path=str(db))
    assert status["reviewed_live_pairs"] == 0
    assert status["generated_live_pairs"] == 0
    assert status["mock_run_count"] >= 1
    assert status["staging_readiness"]["status"] == STATUS_INSUFFICIENT


def test_unreviewed_live_not_counted_as_reviewed(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "live-out"

    art = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="REAL PROMPT",
        generate_text_fn=gen,
        provider_model="app.generate_text",
    )
    assert art.grounded_status == "success"
    persist_compare_run(art.to_dict(), database_path=db, enabled=True)
    status = build_campaign_status(database_path=str(db))
    assert status["generated_live_pairs"] == 1
    assert status["reviewed_live_pairs"] == 0
    assert any(p["status"] == "GENERATED / UNREVIEWED" for p in status["pairs"] if p["passage"] == "John.4.1-42")


def test_reviewed_live_counts_once(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "out"

    art = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="REAL",
        generate_text_fn=gen,
        provider_model="gemini-live",
    )
    persist_compare_run(art.to_dict(), database_path=db, enabled=True)
    # Rate twice — still one reviewed pair
    update_compare_review(
        art.run_id,
        HumanReview(overall_preference="B", factual_accuracy_preference="equal"),
        database_path=db,
    )
    update_compare_review(
        art.run_id,
        HumanReview(overall_preference="equal", factual_accuracy_preference="B"),
        database_path=db,
    )
    status = build_campaign_status(database_path=str(db))
    assert status["reviewed_live_pairs"] == 1
    # Duplicate artifact same pair should not inflate after latest-by-pair
    art2 = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="REAL",
        generate_text_fn=gen,
        provider_model="gemini-live",
    )
    persist_compare_run(art2.to_dict(), database_path=db, enabled=True)
    status2 = build_campaign_status(database_path=str(db))
    # Latest unreviewed replaces reviewed for that pair in campaign matrix
    assert status2["reviewed_live_pairs"] in {0, 1}


def test_campaign_missing_pair_list(tmp_path: Path) -> None:
    status = build_campaign_status(database_path=str(tmp_path / "empty.sqlite3"))
    assert len(status["missing_pairs"]) == 8


def test_blind_mapping_hidden_until_reveal() -> None:
    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "BODY"

    art = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="P",
        generate_text_fn=gen,
        blind=True,
        provider_model="mock",
    )
    hidden = format_compare_report(art, reveal_mapping=False)
    assert "blind_mapping" not in hidden or "withheld" in hidden
    assert "production" not in hidden.split("RESPONSE A")[1].split("RESPONSE B")[0].lower()
    revealed = format_compare_report(art, reveal_mapping=True)
    assert "blind_mapping" in revealed


def test_source_trace_cli(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "x"

    art = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt=STUB,
        generate_text_fn=gen,
    )
    persist_compare_run(art.to_dict(), database_path=db, enabled=True)
    assert "citation_ready_count" in (art.source_trace or {})
    report = format_source_trace_report(art.to_dict())
    assert "SOURCE / CITATION TRACE" in report
    assert main_review_sources([art.run_id, "--database", str(db)]) == 0


def test_manual_commands_do_not_execute_provider() -> None:
    cmds = campaign_manual_commands()
    assert len(cmds) == 8
    assert all("--live" in c and "--blind" in c and "--from-production" in c for c in cmds)
    cmds_file = campaign_manual_commands(prompt_file="prod.txt")
    assert all("--prompt-file" in c for c in cmds_file)


def test_classify_and_readiness_evidence() -> None:
    mock = {"provider_model": "mock", "grounded_status": "success", "production_output": "a"}
    assert classify_run_completeness(mock) == "mock"
    assert is_readiness_evidence(mock) is False
    live_unrev = {
        "provider_model": "app.generate_text",
        "grounded_status": "success",
        "production_output": "a",
        "review": {},
    }
    assert classify_run_completeness(live_unrev) == "live_generated_unreviewed"
    assert is_readiness_evidence(live_unrev) is False
    live_rev = {
        **live_unrev,
        "review": {"overall_preference": "B"},
    }
    assert classify_run_completeness(live_rev) == "live_reviewed"
    assert is_readiness_evidence(live_rev) is True


def test_failed_generation_not_readiness_evidence() -> None:
    failed = {
        "provider_model": "live",
        "grounded_status": "error",
        "production_output": "A ok",
        "review": {"overall_preference": "A"},
    }
    assert classify_run_completeness(failed) == "failed_generation"
    assert is_readiness_evidence(failed) is False
    result = evaluate_staging_readiness(live_artifacts=[failed])
    assert result["metrics"]["live_reviewed_count"] == 0


def test_production_call_count_still_one() -> None:
    calls: list[str] = []

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(prompt)
        return "OUT"

    result = run_production_with_optional_shadow(
        key="exegesis",
        prompt="PROD",
        tab_label="Exegézis",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=False,
        generate_text_fn=gen,
        shadow_runner_fn=lambda **k: {},
    )
    assert result.provider_call_count == 1
    assert calls == ["PROD"]


def test_latest_by_pair_dedupes() -> None:
    arts = [
        {
            "passage": "John.4.1-42",
            "module": "exegesis",
            "provider_model": "live",
            "timestamp": "2026-01-01T00:00:00Z",
            "run_id": "a",
            "grounded_status": "success",
            "production_output": "1",
        },
        {
            "passage": "John.4.1-42",
            "module": "exegesis",
            "provider_model": "live",
            "timestamp": "2026-01-02T00:00:00Z",
            "run_id": "b",
            "grounded_status": "success",
            "production_output": "2",
        },
    ]
    latest = latest_artifacts_by_pair(arts)
    assert latest[("John.4.1-42", "exegesis")]["run_id"] == "b"
