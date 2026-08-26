"""Phase 5F staging readiness, citation policy, and cache tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.citation import (
    build_citation_ref,
    citation_policy_document,
    citations_from_context_packet,
)
from textus_kb.compare_store import HumanReview, persist_compare_run
from textus_kb.context_builder import ContextItem, ContextSection, LLMContextPacket
from textus_kb.grounded_compare import run_grounded_compare
from textus_kb.grounded_generation import (
    PASSAGE_ALLOWLIST_FLAG,
    STAGE_ALLOWED_FLAG,
    is_grounded_injection_allowed,
    is_passage_allowlisted,
    is_stage_allowed,
    prepare_grounded_provider_prompt,
)
from textus_kb.kb_cache import (
    cache_stats,
    clear_kb_cache,
    context_cache_key,
    evidence_cache_key,
)
from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB
from textus_kb.shadow_integration import run_production_with_optional_shadow
from textus_kb.staging_readiness import (
    DEFAULT_CRITERIA,
    STATUS_INSUFFICIENT,
    STATUS_NOT_READY,
    STATUS_READY,
    StagingReadinessCriteria,
    build_review_summary,
    evaluate_staging_readiness,
)


def test_review_summary_insufficient_on_mock_only(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "mock-out"

    art = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        generate_text_fn=gen,
        provider_model="mock",
    )
    persist_compare_run(art.to_dict(), database_path=db, enabled=True)
    summary = build_review_summary(database_path=str(db))
    assert summary["totals"]["mock"] >= 1
    assert summary["totals"]["live"] == 0
    assert summary["staging_readiness"]["status"] == STATUS_INSUFFICIENT


def test_mock_excluded_from_live_readiness(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "x"

    art = run_grounded_compare(
        "Jn 4,1-42",
        module="exegesis",
        production_prompt="P",
        generate_text_fn=gen,
        provider_model="mock",
    )
    payload = art.to_dict()
    payload["review"] = HumanReview(overall_preference="B").to_dict()
    persist_compare_run(payload, database_path=db, enabled=True)
    readiness = evaluate_staging_readiness(live_artifacts=[])
    assert readiness["status"] == STATUS_INSUFFICIENT
    summary = build_review_summary(database_path=str(db), live_only=True)
    assert summary["totals"]["live_reviewed"] == 0


def test_veto_on_factual_worse(tmp_path: Path) -> None:
    live = []
    for i in range(8):
        live.append(
            {
                "passage": f"John.4.{i+1}",
                "module": "exegesis" if i % 2 == 0 else "historical_context",
                "provider_model": "live-model",
                "grounded_status": "success",
                "production_output": f"prod-{i}",
                "grounded_output": f"grounded-{i}",
                "source_ids": ["acai"],
                # Explicit mapping: A=production, B=grounded — factual A => grounded worse.
                "blind_mapping": {"A": "production", "B": "grounded"},
                "review": {
                    "overall_preference": "B",
                    "factual_accuracy_preference": "A",
                    "hallucination_risk": "neither",
                },
            }
        )
    # Ensure both modules and enough passages with both — simplify criteria
    criteria = StagingReadinessCriteria(
        min_live_ab_pairs=4,
        min_distinct_passages=4,
        min_passages_with_both_modules=0,
        max_factual_b_worse_ratio=0.1,
    )
    result = evaluate_staging_readiness(live_artifacts=live, criteria=criteria)
    assert result["status"] == STATUS_NOT_READY
    assert any("factual_grounded_worse" in v for v in result["veto_reasons"])


def test_ready_when_criteria_met() -> None:
    live = []
    passages = ["John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30"]
    for passage in passages:
        for module in ("exegesis", "historical_context"):
            live.append(
                {
                    "passage": passage,
                    "module": module,
                    "provider_model": "gemini-live",
                    "grounded_status": "success",
                    "production_output": f"prod-{passage}-{module}",
                    "grounded_output": f"grounded-{passage}-{module}",
                    "source_ids": ["acai", "aquifer_open_study_notes"],
                    "blind_mapping": {"A": "production", "B": "grounded"},
                    "review": {
                        "overall_preference": "B",
                        "factual_accuracy_preference": "equal",
                        "hallucination_risk": "neither",
                    },
                }
            )
    result = evaluate_staging_readiness(live_artifacts=live, criteria=DEFAULT_CRITERIA)
    assert result["status"] == STATUS_READY
    assert result["ready"] is True
    assert result["metrics"]["grounded_preferred_or_equal_ratio"] == 1.0


def test_citation_ref_schema_and_cc_metadata() -> None:
    ref = build_citation_ref(
        evidence_id="ev-1",
        source_id="aquifer_open_study_notes",
        source_type="exegetical_note",
        metadata={
            "license": "CC-BY-SA-4.0",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "attribution": "Aquifer",
            "article_id": "art-1",
            "canonical_scope": "John.4.1-42",
        },
    )
    assert ref.citation_ready is True
    assert ref.license.startswith("CC-BY")
    assert ref.attribution
    policy = citation_policy_document()
    assert "ruf_policy" in policy
    assert "cite_when" in policy


def test_citation_coverage_from_context() -> None:
    packet = LLMContextPacket(
        passage="John.4.1-42",
        passage_display="Jn 4,1–42",
        profile="exegesis",
        sections=[
            ContextSection(
                type="exegetical",
                items=(
                    ContextItem(
                        text="note",
                        evidence_id="ev-a",
                        source_id="aquifer_open_study_notes",
                        relevance_score=1,
                        item_type="exegetical_note",
                        metadata={
                            "license": "CC-BY-SA-4.0",
                            "attribution": "Aquifer",
                            "license_url": "https://example",
                        },
                    ),
                ),
            )
        ],
        source_ids=["aquifer_open_study_notes"],
        evidence_ids=["ev-a"],
    )
    report = citations_from_context_packet(packet)
    assert report.selected_evidence_count == 1
    assert report.citation_ready_count == 1


def test_restricted_ruf_not_mixed_in_policy() -> None:
    policy = citation_policy_document()
    assert "RÚF" in policy["ruf_policy"] or "contractual" in policy["ruf_policy"]


def test_cache_hit_and_invalidation() -> None:
    clear_kb_cache()
    prep1 = prepare_grounded_provider_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        passage="Jn 4,1-42",
        module="exegesis",
        grounded_enabled=True,
        use_cache=True,
    )
    assert prep1.grounded_used is True
    assert prep1.cache_info.get("evidence_cache_hit") is False
    prep2 = prepare_grounded_provider_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        passage="Jn 4,1-42",
        module="exegesis",
        grounded_enabled=True,
        use_cache=True,
    )
    assert prep2.cache_info.get("evidence_cache_hit") is True
    # Version change → different key → miss
    key_old = evidence_cache_key("John.4.1-42", kb_build_id="old-build")
    key_new = evidence_cache_key("John.4.1-42", kb_build_id="new-build")
    assert key_old != key_new
    ctx_a = context_cache_key("John.4.1-42", "exegesis", selection_version="1")
    ctx_b = context_cache_key("John.4.1-42", "exegesis", selection_version="2")
    assert ctx_a != ctx_b
    stats = cache_stats()
    assert stats["evidence_hits"] >= 1


def test_cache_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("cache broken")

    monkeypatch.setattr("textus_kb.kb_cache.get_cached_evidence", boom)
    prep = prepare_grounded_provider_prompt(
        production_prompt="P",
        passage="Jn 4,1-42",
        module="exegesis",
        grounded_enabled=True,
        use_cache=True,
    )
    assert prep.grounded_used is True or prep.grounded_fallback is True


def test_staging_guard_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STAGE_ALLOWED_FLAG, raising=False)
    monkeypatch.setenv("TEXTUS_KB_GROUNDED_ENABLED", "true")
    assert is_stage_allowed() is False
    assert is_grounded_injection_allowed() is False


def test_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PASSAGE_ALLOWLIST_FLAG, "John.4.1-42")
    assert is_passage_allowlisted("Jn 4,1-42") is True
    assert is_passage_allowlisted("Rom.8.28-30") is False
    prep = prepare_grounded_provider_prompt(
        production_prompt="P",
        passage="Rom.8.28-30",
        module="exegesis",
        grounded_enabled=True,
    )
    assert prep.grounded_fallback is True
    assert prep.fallback_reason == "passage_not_allowlisted"


def test_production_invariance_with_new_guards() -> None:
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
    assert calls == ["PROD"]
    assert result.provider_call_count == 1


def test_phase5d_fallback_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("fail")

    monkeypatch.setattr("textus_kb.retrieval.retrieve", boom)
    clear_kb_cache()
    calls: list[str] = []

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(prompt)
        return "OK"

    result = run_production_with_optional_shadow(
        key="exegesis",
        prompt="FALLBACK",
        tab_label="Exegézis",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=True,
        generate_text_fn=gen,
        shadow_runner_fn=lambda **k: {},
    )
    assert calls == ["FALLBACK"]
    assert result.grounded_event["grounded_fallback"] is True
