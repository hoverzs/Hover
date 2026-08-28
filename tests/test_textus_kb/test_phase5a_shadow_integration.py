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
    assert "TEXTUS_KB_GROUNDED_STAGE_ALLOWED" not in app_src


def test_shadow_explicit_true_still_produces_artifact() -> None:
    from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB
    from textus_kb.shadow_integration import run_production_with_optional_shadow

    calls: list[dict] = []

    def fake_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append({"prompt": prompt})
        return "OUT"

    def counting_shadow(**kwargs):
        return {"status": "success", "success": True, "module": kwargs.get("module")}

    result = run_production_with_optional_shadow(
        key="exegesis",
        prompt=DRY_RUN_PRODUCTION_STUB,
        tab_label="Exegézis",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=True,
        grounded_enabled=False,
        generate_text_fn=fake_generate,
        shadow_runner_fn=counting_shadow,
    )
    assert len(calls) == 1
    assert result.shadow_event is not None
    assert result.shadow_event.get("success") is True

