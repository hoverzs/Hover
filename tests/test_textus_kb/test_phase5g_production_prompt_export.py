"""Tests for production prompt export (Phase 5G benchmark helper)."""

from __future__ import annotations

from textus_kb.production_prompt_export import (
    MODULE_TO_SECTION,
    build_production_section_prompt,
    display_reference_hu,
)
from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB


def test_display_reference_hu_benchmark_passages() -> None:
    assert display_reference_hu("John.4.1-42").startswith("Jn ")
    assert "4,1-42" in display_reference_hu("John.4.1-42")
    assert "10,25-37" in display_reference_hu("Luke.10.25-37")


def test_build_production_prompt_matches_section_keys() -> None:
    # Avoid network: pass empty passage text explicitly.
    exe = build_production_section_prompt(
        "John.4.1-42",
        module="exegesis",
        passage_text="1. Teszt vers",
    )
    assert exe.section_key == "exegesis"
    assert exe.tab_label == "Exegézis"
    assert exe.include_original_language_tokens is True
    assert "Exegézis" in exe.production_prompt or "Szövegelemzés" in exe.production_prompt
    assert exe.production_prompt.strip() != DRY_RUN_PRODUCTION_STUB.strip()
    assert "Teszt vers" in exe.production_prompt

    hist = build_production_section_prompt(
        "John.4.1-42",
        module="historical_context",
        passage_text="1. Teszt vers",
    )
    assert hist.section_key == MODULE_TO_SECTION["historical_context"] == "history"
    assert hist.tab_label == "Kortörténet"
    assert hist.include_biblical_place_context is True
    assert hist.include_original_language_tokens is False


def test_large_production_prompt_uses_adaptive_budget_without_truncation() -> None:
    from textus_kb.grounded_generation import prepare_grounded_provider_prompt
    from textus_kb.prompt_composer import (
        DEFAULT_KB_CONTEXT_MAX_TOKENS,
        DEFAULT_TOTAL_GROUNDED_MAX_TOKENS,
        grounded_kb_context_max_tokens,
        grounded_total_max_tokens,
    )

    assert grounded_kb_context_max_tokens() == DEFAULT_KB_CONTEXT_MAX_TOKENS
    assert grounded_total_max_tokens() == DEFAULT_TOTAL_GROUNDED_MAX_TOKENS
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
    assert prep.original_prompt_estimated_tokens > 8000
    assert prep.budget_diagnostics.get("budget_ok") is True


def test_live_cli_accepts_from_production_flag_without_file() -> None:
    from textus_kb.grounded_compare import main as compare_main

    # Missing --blind still fails even with --from-production.
    code = compare_main(
        ["John.4.1-42", "--module", "exegesis", "--live", "--from-production"]
    )
    assert code == 2
