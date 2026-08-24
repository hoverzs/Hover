"""Phase 5A shadow integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.shadow import build_shadow_benchmark_report, run_kb_shadow_for_module


def test_shadow_artifact_exegesis() -> None:
    artifact = run_kb_shadow_for_module("Jn 4,1-42", module="exegesis")
    assert artifact.success is True
    assert artifact.status in {"success", "degraded"}
    assert artifact.profile == "exegesis"
    assert artifact.passage_canonical == "John.4.1-42"
    assert artifact.token_estimate > 0
    assert artifact.evidence_item_count > 0
    assert artifact.context_packet.get("profile") == "exegesis"


def test_shadow_artifact_historical() -> None:
    artifact = run_kb_shadow_for_module("Lk 10,25-37", module="historical_context")
    assert artifact.success is True
    assert artifact.status in {"success", "degraded"}
    assert artifact.profile == "historical_context"
    assert artifact.passage_canonical == "Luke.10.25-37"
    assert artifact.context_packet.get("profile") == "historical_context"


def test_shadow_failure_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    import textus_kb.shadow as shadow

    def _boom(_: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(shadow, "retrieve", _boom)
    artifact = run_kb_shadow_for_module("Jn 4,1-42", module="exegesis")
    assert artifact.success is False
    assert artifact.status == "error"
    assert "RuntimeError" in artifact.error


def test_shadow_benchmark_report_four_passages() -> None:
    report = build_shadow_benchmark_report(
        ["John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30"],
        modules=["exegesis", "historical_context"],
    )
    assert len(report["artifacts"]) == 8
    assert all("retrieval_duration_ms" in item for item in report["artifacts"])


def test_app_shadow_flag_default_false_and_hooked() -> None:
    app_src = Path("app.py").read_text(encoding="utf-8")
    assert 'KB_SHADOW_FLAG = "TEXTUS_KB_SHADOW_ENABLED"' in app_src
    assert 'os.getenv(KB_SHADOW_FLAG, "false")' in app_src
    assert "run_production_with_optional_shadow(" in app_src
    assert "shadow_enabled=_is_kb_shadow_enabled()" in app_src
    assert "st.session_state[key] = run.production_output" in app_src

