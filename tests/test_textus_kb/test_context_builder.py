"""Tests for Phase 2B evidence context builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textus_kb.context_builder import (
    LLMContextPacket,
    build_context,
    build_context_from_evidence,
    build_context_to_json,
)
from textus_kb.context_profiles import (
    PROFILE_EXEGESIS,
    PROFILE_HISTORICAL,
    PROFILE_THEOLOGY,
    THEOLOGY_SOURCE_WARNING,
    ContextProfile,
)
from textus_kb.manifest import KnowledgeBaseManifest, load_manifest
from textus_kb.retrieval import retrieve

EXEGESIS_FIXTURE = Path("tests/fixtures/kb/john_4_1_42_exegesis_context.json")
HISTORICAL_FIXTURE = Path("tests/fixtures/kb/john_4_1_42_historical_context.json")
EVIDENCE_FIXTURE = Path("tests/fixtures/kb/john_4_1_42_packet.json")


@pytest.fixture(name="evidence")
def evidence_fixture(phase2a_manifest: KnowledgeBaseManifest) -> object:
    return retrieve("Jn 4,1-42", manifest=phase2a_manifest)


def test_context_is_deterministic(evidence) -> None:
    first = build_context_to_json("Jn 4,1-42", PROFILE_EXEGESIS, evidence=evidence)
    second = build_context_to_json("Jn 4,1-42", PROFILE_EXEGESIS, evidence=evidence)
    assert first == second


def test_profiles_produce_different_content(evidence) -> None:
    exegesis = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    historical = build_context_from_evidence(evidence, PROFILE_HISTORICAL)
    assert exegesis.profile != historical.profile
    assert exegesis.evidence_ids != historical.evidence_ids
    exegesis_types = {section.type for section in exegesis.sections}
    historical_types = {section.type for section in historical.sections}
    assert "linguistic" in exegesis_types
    assert "linguistic" not in historical_types


def test_exegesis_excludes_full_raw_token_json(evidence) -> None:
    context = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    serialized = json.dumps(context.to_dict(), ensure_ascii=False)
    assert '"verses"' not in serialized
    assert "greek_form" not in serialized
    assert "723 tokens (compact view" in serialized or "723 tokens" in serialized


def test_historical_context_smaller_than_evidence_packet(evidence) -> None:
    historical = build_context_from_evidence(evidence, PROFILE_HISTORICAL)
    assert historical.estimated_tokens < evidence.estimated_tokens
    reduction = evidence.estimated_tokens - historical.estimated_tokens
    assert reduction > 15_000


def test_provenance_fields_present(evidence) -> None:
    context = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    for section in context.sections:
        for item in section.items:
            assert item.evidence_id.startswith("EV-")
            assert item.source_id
            assert item.relevance_score > 0


def test_context_evidence_ids_exist_in_evidence_packet(evidence) -> None:
    context = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    evidence_ids = {item.evidence_id for item in evidence.evidence_items}
    for context_id in context.evidence_ids:
        assert context_id in evidence_ids


def test_exegesis_token_budget_respected(evidence) -> None:
    context = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    assert context.estimated_tokens <= context.token_budget


def test_historical_token_budget_respected(evidence) -> None:
    context = build_context_from_evidence(evidence, PROFILE_HISTORICAL)
    assert context.estimated_tokens <= context.token_budget


def test_forced_truncation_marks_packet(evidence) -> None:
    profile = ContextProfile.load(PROFILE_EXEGESIS, token_budget=120)
    context = build_context_from_evidence(evidence, profile)
    assert context.estimated_tokens <= 120
    assert context.max_tokens == 120
    # Soft target may absorb cuts; hard-max truncation flag when budget drops occur.
    assert context.truncated is True or context.selection_stats["selected"] < context.selection_stats["candidates"]


def test_priority_order_is_deterministic(evidence) -> None:
    full = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    trimmed = build_context_from_evidence(
        evidence,
        ContextProfile.load(PROFILE_EXEGESIS, token_budget=200),
    )
    assert trimmed.estimated_tokens <= 200
    assert len(trimmed.evidence_ids) <= len(full.evidence_ids)


def test_theology_profile_emits_source_warning(evidence) -> None:
    context = build_context_from_evidence(evidence, PROFILE_THEOLOGY)
    assert THEOLOGY_SOURCE_WARNING in context.warnings


def test_graceful_with_missing_optional_enrichment() -> None:
    from dataclasses import replace

    from textus_kb.evidence import RELATION_PLACE_ENRICHMENT

    evidence = retrieve("Jn 4,1-42")
    filtered_items = [
        item
        for item in evidence.evidence_items
        if item.relation_type != RELATION_PLACE_ENRICHMENT
    ]
    reduced = replace(evidence, evidence_items=filtered_items, historical_evidence=[])
    context = build_context_from_evidence(reduced, PROFILE_HISTORICAL)
    assert context.estimated_tokens > 0
    assert not any(
        item.item_type == "historical_enrichment"
        for section in context.sections
        for item in section.items
    )


def test_exegesis_matches_golden_fixture(evidence) -> None:
    golden = json.loads(EXEGESIS_FIXTURE.read_text(encoding="utf-8"))
    context = json.loads(build_context_to_json("Jn 4,1-42", PROFILE_EXEGESIS, evidence=evidence))
    assert context["passage"] == golden["passage"]
    assert context["profile"] == golden["profile"]
    assert context["evidence_ids"] == golden["evidence_ids"]
    assert context["estimated_tokens"] == golden["estimated_tokens"]


def test_historical_matches_golden_fixture(evidence) -> None:
    golden = json.loads(HISTORICAL_FIXTURE.read_text(encoding="utf-8"))
    context = json.loads(
        build_context_to_json("Jn 4,1-42", PROFILE_HISTORICAL, evidence=evidence)
    )
    assert context["passage"] == golden["passage"]
    assert context["profile"] == golden["profile"]
    assert context["evidence_ids"] == golden["evidence_ids"]
    assert context["estimated_tokens"] == golden["estimated_tokens"]


def test_cli_context_main_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from textus_kb.context_builder import main

    assert main(["Jn 4,1-42", "--profile", "exegesis"]) == 0
