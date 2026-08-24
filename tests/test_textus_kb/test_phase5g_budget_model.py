"""Adaptive grounded prompt budget model tests (Phase 5G fix)."""

from __future__ import annotations

from textus_kb.context_builder import ContextItem, ContextSection, LLMContextPacket
from textus_kb.evidence import estimate_text_tokens
from textus_kb.grounded_compare import run_grounded_compare
from textus_kb.grounded_generation import prepare_grounded_provider_prompt
from textus_kb.production_prompt_export import build_production_section_prompt
from textus_kb.prompt_composer import (
    BUDGET_STATUS_EXCEEDED,
    BUDGET_STATUS_OK,
    DEFAULT_KB_CONTEXT_MAX_TOKENS,
    DEFAULT_TOTAL_GROUNDED_MAX_TOKENS,
    compose_grounded_prompt,
    grounded_kb_context_max_tokens,
    grounded_total_max_tokens,
)


def _kb_packet(text: str, *, n: int = 8) -> LLMContextPacket:
    items = tuple(
        ContextItem(
            text=f"{text} block-{i} " + ("word " * 40),
            evidence_id=f"ev-{i}",
            source_id="aquifer_open_study_notes",
            relevance_score=10 - (i % 5),
            item_type="exegetical_note",
            metadata={"canonical_scope": "John.4.1-42", "license": "CC-BY-SA-4.0"},
        )
        for i in range(n)
    )
    return LLMContextPacket(
        passage="John.4.1-42",
        passage_display="Jn 4,1–42",
        profile="exegesis",
        sections=[ContextSection(type="exegetical", items=items)],
        source_ids=["aquifer_open_study_notes"],
        evidence_ids=[f"ev-{i}" for i in range(n)],
        schema_version="2",
        evidence_packet_build_id="budget-test",
    )


def test_defaults_kb_allowance_and_total_cap() -> None:
    assert grounded_kb_context_max_tokens() == DEFAULT_KB_CONTEXT_MAX_TOKENS == 4500
    assert grounded_total_max_tokens() == DEFAULT_TOTAL_GROUNDED_MAX_TOKENS == 28000
    from textus_kb.prompt_composer import (
        grounded_kb_context_target_tokens,
        resolve_grounded_budget_limits,
    )

    assert grounded_kb_context_target_tokens(module="exegesis") == 2500
    assert grounded_kb_context_max_tokens(module="exegesis") == 4500
    assert grounded_kb_context_target_tokens(module="historical_context") == 2200
    assert grounded_kb_context_max_tokens(module="historical_context") == 3500
    t, m, total = resolve_grounded_budget_limits(module="exegesis")
    assert (t, m, total) == (2500, 4500, 28000)


def test_16k_production_plus_kb_succeeds_under_total_cap() -> None:
    # ~16k estimated tokens without needing live export.
    production = ("PROD_LINE_WITH_CONTENT " * 800)  # rough ~16k tokens depending on estimator
    # Pad until >= 16000 estimated.
    while estimate_text_tokens(production) < 16000:
        production += " MORE_TOKEN_CONTENT_BLOCK"
    packet = _kb_packet("KB note", n=6)
    preview = compose_grounded_prompt(
        production_prompt=production,
        canonical_passage="John.4.1-42",
        module="exegesis",
        context_packet=packet,
        # Leave headroom for ~3k KB under default-like total.
        token_budget=22000,
        kb_context_max_tokens=3000,
    )
    assert preview.original_prompt_estimated_tokens >= 16000
    assert preview.budget_ok is True
    assert preview.budget_status in {BUDGET_STATUS_OK, "trimmed"}
    assert production in preview.composed_prompt
    assert preview.kb_context_estimated_tokens <= 3000
    assert preview.composed_prompt_estimated_tokens <= 22000
    diag = preview.budget_diagnostics()
    assert diag["production_prompt_estimated_tokens"] == preview.original_prompt_estimated_tokens
    assert diag["total_grounded_estimated_tokens"] == preview.composed_prompt_estimated_tokens
    assert "composition_overhead_estimated_tokens" in diag


def test_production_over_legacy_8k_does_not_fail_only_for_that() -> None:
    production = "X" * 40000  # well over 8k estimated
    assert estimate_text_tokens(production) > 8000
    preview = compose_grounded_prompt(
        production_prompt=production,
        canonical_passage="John.4.1-42",
        module="exegesis",
        context_packet=_kb_packet("note", n=2),
    )
    assert preview.budget_ok is True
    assert production in preview.composed_prompt
    assert preview.total_grounded_max_tokens == DEFAULT_TOTAL_GROUNDED_MAX_TOKENS


def test_kb_max_enforced_and_trim_preserves_production() -> None:
    production = "KEEP_PRODUCTION_VERBATIM"
    packet = _kb_packet("large kb", n=20)
    preview = compose_grounded_prompt(
        production_prompt=production,
        canonical_passage="John.4.1-42",
        module="exegesis",
        context_packet=packet,
        kb_context_max_tokens=200,
        token_budget=8000,
    )
    assert production in preview.composed_prompt
    assert preview.kb_context_estimated_tokens <= 200
    assert preview.budget_ok is True
    assert preview.kb_trim_applied is True
    # After aggressive KB-max trim, items may be fully removed; production stays intact.
    assert preview.budget_diagnostics()["kb_context_max_tokens"] == 200


def test_total_hard_cap_structured_exceeded() -> None:
    production = "P" * 5000
    preview = compose_grounded_prompt(
        production_prompt=production,
        canonical_passage="John.4.1-42",
        module="exegesis",
        context_packet=_kb_packet("kb", n=10),
        token_budget=50,  # smaller than production+overhead
        kb_context_max_tokens=4500,
    )
    assert preview.budget_ok is False
    assert preview.budget_status == BUDGET_STATUS_EXCEEDED
    # Production must still be intact when a composed string exists; if early-fail, empty.
    if preview.composed_prompt:
        assert production in preview.composed_prompt


def test_real_export_prep_succeeds_and_records_diagnostics() -> None:
    export = build_production_section_prompt(
        "John.4.1-42",
        module="exegesis",
        passage_text="1. Teszt",
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=export.production_prompt,
        passage=export.passage_canonical,
        module=export.module,
        grounded_enabled=True,
    )
    assert prep.grounded_used is True
    assert prep.grounded_fallback is False
    assert export.production_prompt in (prep.provider_prompt or "")
    assert prep.budget_diagnostics.get("budget_ok") is True
    assert prep.budget_diagnostics.get("kb_context_max_tokens") == 4500
    assert prep.budget_diagnostics.get("kb_context_target_tokens") == 2500
    assert prep.budget_diagnostics.get("total_grounded_max_tokens") == 28000
    assert prep.kb_context_estimated_tokens <= 2500 or prep.budget_diagnostics.get(
        "kb_trim_applied"
    )
    assert "kb_share_of_grounded_percent" in prep.budget_diagnostics


def test_compare_success_provider_calls_two_and_budget_metrics() -> None:
    calls: list[str] = []

    def gen(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(tab_label)
        return f"out-{len(calls)}"

    export = build_production_section_prompt(
        "Rom.8.28-30",
        module="exegesis",
        passage_text="28. Teszt",
    )
    art = run_grounded_compare(
        export.passage_canonical,
        module=export.module,
        production_prompt=export.production_prompt,
        generate_text_fn=gen,
        blind=True,
        provider_model="mock-test",
    )
    assert art.provider_call_count == 2
    assert len(calls) == 2
    assert art.grounded_status == "success"
    assert art.metrics.get("budget_status") in {"ok", "trimmed"}
    assert "composition_overhead_estimated_tokens" in art.metrics


def test_prep_budget_failure_does_not_fake_grounded_success() -> None:
    production = "TINY"
    # Force impossible total cap via env override on compose path using token_budget.
    preview = compose_grounded_prompt(
        production_prompt=production + ("Z" * 2000),
        canonical_passage="John.4.1-42",
        module="exegesis",
        context_packet=_kb_packet("x", n=3),
        token_budget=10,
    )
    assert preview.budget_ok is False
    prep = prepare_grounded_provider_prompt(
        production_prompt=production + ("Z" * 2000),
        passage="John.4.1-42",
        module="exegesis",
        grounded_enabled=True,
        token_budget=10,
    )
    assert prep.grounded_used is False
    assert prep.grounded_fallback is True
    assert prep.fallback_reason == "budget_exceeded"
    # Provider prompt falls back to production for app path, but compare treats as B error.
    assert prep.provider_prompt == production + ("Z" * 2000)
