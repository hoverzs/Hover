"""Phase 5H-D: critical output safety + unsupported-claim / limited-coverage guards."""

from __future__ import annotations

from textus_kb.citation import citations_from_context_packet
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.prompt_composer import (
    DRY_RUN_PRODUCTION_STUB,
    compose_grounded_prompt,
    render_kb_context,
    scrub_internal_identifiers,
)
from textus_kb.retrieval import retrieve


def _compose(passage: str, module: str):
    profile = PROFILE_HISTORICAL if module == "historical_context" else PROFILE_EXEGESIS
    packet = retrieve(passage)
    context = build_context_from_evidence(packet, profile)
    preview = compose_grounded_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        canonical_passage=packet.passage_canonical,
        module=module,
        context_packet=context,
    )
    return packet, context, preview


def test_internal_evidence_ids_not_in_llm_facing_context() -> None:
    _packet, context, preview = _compose("Rom.8.28-30", "exegesis")
    rendered, _sources, evidence_ids, _warnings = render_kb_context(context)
    assert evidence_ids
    assert "EV-" not in rendered
    assert "source_id=" not in rendered
    assert "EV-" not in preview.composed_prompt
    assert "source_id=aquifer" not in preview.composed_prompt
    dirty = "Abba (EV-DICT-EV-DICT-3268-C001) and [EV-LEX-FOO]"
    assert "EV-" not in scrub_internal_identifiers(dirty)


def test_source_trace_and_citation_metadata_still_keep_internal_ids() -> None:
    _packet, context, preview = _compose("Rom.8.28-30", "exegesis")
    assert preview.evidence_ids
    assert all(eid for eid in preview.evidence_ids)
    assert context.evidence_ids
    coverage = citations_from_context_packet(context)
    assert coverage.selected_evidence_count >= 1
    assert any(ref.evidence_id for ref in coverage.citations)


def test_limited_historical_coverage_gets_strict_guard() -> None:
    _packet, context, preview = _compose("Rom.8.28-30", "historical_context")
    assert context.selection_stats.get("historical_coverage_status") == "limited"
    assert "=== LIMITED HISTORICAL COVERAGE ===" in preview.composed_prompt
    assert "korlátozott" in preview.composed_prompt
    assert "Ne egészítsd ki konkrét történeti nevekkel" in preview.composed_prompt


def test_ok_historical_coverage_does_not_get_limited_guard() -> None:
    _packet, context, preview = _compose("John.4.1-42", "historical_context")
    assert context.selection_stats.get("historical_coverage_status") == "ok"
    assert "=== LIMITED HISTORICAL COVERAGE ===" not in preview.composed_prompt


def test_unsupported_claim_guard_in_grounded_instruction() -> None:
    _packet, _context, preview = _compose("Acts.2.1-13", "exegesis")
    prompt = preview.composed_prompt
    assert "Concrete historical, geographical, or linguistic claims" in prompt
    assert "Do not invent specific names, dates, legal statuses" in prompt
    assert "=== LIMITED HISTORICAL COVERAGE ===" not in prompt


def test_exegesis_does_not_receive_historical_limited_guard() -> None:
    _packet, context, preview = _compose("Rom.8.28-30", "exegesis")
    assert context.profile == "exegesis"
    assert "=== LIMITED HISTORICAL COVERAGE ===" not in preview.composed_prompt


def test_production_prompt_unchanged_in_composition() -> None:
    production = DRY_RUN_PRODUCTION_STUB
    _packet, _context, preview = _compose("John.4.1-42", "exegesis")
    assert production in preview.composed_prompt
    assert preview.original_prompt_chars == len(production)
    assert preview.composed_prompt.index(
        "=== TEXTUS PRODUCTION INSTRUCTIONS ==="
    ) < preview.composed_prompt.index(production)


def test_token_budget_still_ok_for_phase5h_d_dry_runs() -> None:
    for passage, module in (
        ("Rom.8.28-30", "historical_context"),
        ("Rom.8.28-30", "exegesis"),
        ("John.4.1-42", "historical_context"),
        ("Acts.2.1-13", "exegesis"),
    ):
        _packet, context, preview = _compose(passage, module)
        assert preview.success
        assert preview.budget_ok
        assert preview.kb_context_estimated_tokens <= preview.kb_context_max_tokens
        assert preview.composed_prompt_estimated_tokens <= preview.total_grounded_max_tokens
        assert context.estimated_tokens <= context.max_tokens


def test_phase5h_b_dictionary_noise_still_absent() -> None:
    packet = retrieve("John.4.1-42")
    titles = {
        str(item.metadata.get("title") or "")
        for item in packet.evidence_items
        if item.source_type == "bible_dictionary"
    }
    assert "Abba" not in titles
    assert "Aegean Sea" not in titles


def test_phase5h_c_historical_coverage_fields_still_present() -> None:
    packet = retrieve("John.4.1-42")
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert historical.selection_stats.get("historical_coverage_status") == "ok"
    assert historical.selection_stats.get("historical_background_selected", 0) >= 1
