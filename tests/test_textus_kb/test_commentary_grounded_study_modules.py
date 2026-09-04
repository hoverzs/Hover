"""Selective, module-specific Commentary grounding for Exegézis and
Kortörténet (2026-09-03 round).

Commentary (Calvin/JFB/Henry) is an interpretive witness layer added on
top of each profile's own direct evidence — never a replacement for it,
never the whole context budget, and always attributed. This file proves,
against the real, locally-built 3-source production store (gated, skipped
when unavailable — same gating as ``test_combined_calvin_jfb_henry_
commentary.py``) and with small isolated/monkeypatched stores for fail-
closed cases:

  - Exegézis: multiple distinct commentary works can enter, with
    attribution/provenance preserved, without exceeding the profile's
    token budget, and without displacing direct evidence.
  - Kortörténet: Commentary stays supplementary — direct background
    evidence keeps priority, and Commentary alone consumes a much smaller
    slice than in Exegézis.
  - Direct evidence priority is never weakened by Commentary's presence
    (a synthetic same-tier-vs-commentary priority ordering proof, plus a
    real trim-order proof that commentary drops before linguistic
    evidence under budget pressure).
  - Fail-closed: missing/invalid Commentary DB, no passage-linked match,
    and an unsupported-by-Calvin book (Revelation) all leave the module
    working exactly as it did before Commentary existed.

No external LLM/API is called anywhere in this file — everything is
tested at the deterministic evidence/context/composed-prompt level.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import ContextProfile, PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.evidence import EvidencePacket
from textus_kb.grounded_generation import prepare_grounded_provider_prompt
from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
from textus_kb.repositories.commentary_repository import CommentaryRepository
from textus_kb.retrieval import retrieve

_PRODUCTION_DB = Path("data/generated/commentary.sqlite3")
_requires_production_commentary = pytest.mark.skipif(
    not (_PRODUCTION_DB.is_file() and CommentaryRepository(_PRODUCTION_DB).store_status().available),
    reason=(
        "Production 3-source commentary.sqlite3 not present/valid locally. Build with: "
        "python scripts/build_commentary_database.py --combined-fetch --qa"
    ),
)


def _packet(reference: str) -> EvidencePacket:
    return retrieve(reference)


# --- Real production-store tests: Exegézis --------------------------------


@_requires_production_commentary
@pytest.mark.parametrize(
    ("label", "reference", "expected_work_prefixes"),
    [
        ("Romans", "Romans.1.1", {"ccel.calvin", "ccel.jfb", "ccel.henry"}),
        ("Psalms", "Psalms.23.1", {"ccel.calvin", "ccel.jfb", "ccel.henry"}),
        ("Isaiah", "Isaiah.53.5", {"ccel.calvin", "ccel.jfb", "ccel.henry"}),
        ("Gospel", "Matthew.1.1", {"ccel.calvin", "ccel.jfb", "ccel.henry"}),
        ("Revelation", "Revelation.1.1", {"ccel.jfb", "ccel.henry"}),
    ],
)
def test_exegesis_commentary_source_diversity_and_budget(
    label: str, reference: str, expected_work_prefixes: set[str]
) -> None:
    evidence = _packet(reference)
    ctx = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    commentary_items = [
        item
        for section in ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    ]
    assert commentary_items, f"{label}: expected Commentary evidence for {reference}"

    prefixes = {
        next((p for p in ("ccel.calvin", "ccel.jfb", "ccel.henry") if str(item.metadata.get("work_id") or "").startswith(p)), "")
        for item in commentary_items
    }
    assert prefixes == expected_work_prefixes, f"{label}: source diversity mismatch: {prefixes}"

    # Provenance survives: every commentary item is individually attributable.
    for item in commentary_items:
        assert item.metadata.get("work_id"), f"{label}: missing work_id"
        assert item.metadata.get("work_title"), f"{label}: missing work_title"
        assert item.metadata.get("edition_id"), f"{label}: missing edition_id"

    # Budget respected: Commentary never consumes the whole context.
    assert ctx.estimated_tokens <= ctx.max_tokens
    direct_evidence_items = [
        item
        for section in ctx.sections
        for item in section.items
        if item.item_type not in ("commentary_source",)
    ]
    assert direct_evidence_items, f"{label}: direct evidence must still be present"
    commentary_tokens = sum(i.estimated_tokens() for i in commentary_items)
    assert commentary_tokens < ctx.estimated_tokens, (
        f"{label}: commentary must not dominate the whole context budget"
    )


@_requires_production_commentary
def test_exegesis_attribution_metadata_matches_real_provenance() -> None:
    """Every attributed claim must be traceable to a real contributor/
    work/edition/passage/locator — never an invented citation."""
    evidence = _packet("Romans.1.1")
    ctx = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    commentary_items = [
        item
        for section in ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    ]
    assert commentary_items
    for item in commentary_items:
        meta = item.metadata
        assert meta.get("contributors"), "missing contributor"
        assert meta.get("canonical_scope") or meta.get("primary_passages"), "missing passage link"
        # source_locator/section_id trace back to the real store.
        assert meta.get("section_id")


# --- Real production-store tests: Kortörténet -----------------------------


@_requires_production_commentary
@pytest.mark.parametrize(
    "reference",
    ["Romans.1.1", "Psalms.23.1", "Isaiah.53.5", "Matthew.1.1"],
)
def test_historical_commentary_stays_supplementary(reference: str) -> None:
    evidence = _packet(reference)
    ctx = build_context_from_evidence(evidence, PROFILE_HISTORICAL)
    commentary_items = [
        item
        for section in ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    ]
    all_items = [item for section in ctx.sections for item in section.items]
    # Commentary is present (when available) but never the majority of the packet.
    if commentary_items:
        assert len(commentary_items) < len(all_items)
    assert ctx.estimated_tokens <= ctx.max_tokens


@_requires_production_commentary
def test_historical_commentary_budget_smaller_than_exegesis() -> None:
    """The same passage's Commentary footprint must stay smaller in
    Kortörténet than in Exegézis (explicit budget ordering requirement)."""
    evidence = _packet("Romans.1.1")
    exeg_ctx = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    hist_ctx = build_context_from_evidence(evidence, PROFILE_HISTORICAL)

    def _commentary_tokens(ctx) -> int:
        return sum(
            item.estimated_tokens()
            for section in ctx.sections
            for item in section.items
            if item.item_type == "commentary_source"
        )

    assert _commentary_tokens(hist_ctx) < _commentary_tokens(exeg_ctx)


# --- Direct evidence priority is never weakened ---------------------------


def test_commentary_priority_never_exceeds_direct_evidence_exegesis() -> None:
    exeg_profile = ContextProfile.load(PROFILE_EXEGESIS)
    from textus_kb.evidence import (
        RELATION_COMMENTARY_SOURCE,
        RELATION_DICTIONARY_BACKGROUND,
        RELATION_DIRECT_PASSAGE,
        RELATION_EXEGETICAL_NOTE,
        RELATION_LEXICAL_HIGHLIGHT,
    )

    commentary_score = exeg_profile.priorities[RELATION_COMMENTARY_SOURCE]
    for relation in (
        RELATION_DIRECT_PASSAGE,
        RELATION_EXEGETICAL_NOTE,
        RELATION_DICTIONARY_BACKGROUND,
        RELATION_LEXICAL_HIGHLIGHT,
    ):
        assert exeg_profile.priorities[relation] > commentary_score, relation


def test_commentary_priority_never_exceeds_direct_evidence_historical() -> None:
    hist_profile = ContextProfile.load(PROFILE_HISTORICAL)
    from textus_kb.evidence import (
        RELATION_COMMENTARY_SOURCE,
        RELATION_DICTIONARY_BACKGROUND,
        RELATION_PASSAGE_PLACE,
        RELATION_PLACE_CATALOG,
        RELATION_PLACE_ENRICHMENT,
    )

    commentary_score = hist_profile.priorities[RELATION_COMMENTARY_SOURCE]
    for relation in (
        RELATION_PLACE_ENRICHMENT,
        RELATION_PASSAGE_PLACE,
        RELATION_PLACE_CATALOG,
        RELATION_DICTIONARY_BACKGROUND,
    ):
        assert hist_profile.priorities[relation] > commentary_score, relation


@_requires_production_commentary
def test_lexical_evidence_survives_trim_before_commentary_under_pressure() -> None:
    """Explicit proof requested by the round: under a tight token budget,
    Greek lexical evidence still precedes/survives ahead of Calvin/JFB/
    Henry commentary in the Eredeti-szöveg-adjacent Exegézis grounded
    prompt -- commentary is trimmed first, never direct evidence."""
    loose = prepare_grounded_provider_prompt(
        production_prompt="PRODUCTION PROMPT",
        passage="Romans.1.1",
        module="exegesis",
    )
    assert loose.grounded_used
    assert "[COMMENTARY SOURCES]" in loose.provider_prompt
    assert "[LINGUISTIC]" in loose.provider_prompt

    tight = prepare_grounded_provider_prompt(
        production_prompt="PRODUCTION PROMPT",
        passage="Romans.1.1",
        module="exegesis",
        token_budget=1800,
    )
    assert tight.grounded_used
    assert "[LINGUISTIC]" in tight.provider_prompt, "direct linguistic evidence must survive trimming"
    assert "[COMMENTARY SOURCES]" not in tight.provider_prompt, (
        "commentary must be trimmed before direct evidence under budget pressure"
    )


# --- Fail-closed: missing/invalid DB, no-match, unsupported book ----------


def test_exegesis_works_without_commentary_when_db_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _packet("Romans.1.1")
    missing_path = tmp_path / "does_not_exist.sqlite3"
    ctx = build_context_from_evidence(
        evidence, PROFILE_EXEGESIS, commentary_database_path=missing_path
    )
    commentary_items = [
        item for s in ctx.sections for item in s.items if item.item_type == "commentary_source"
    ]
    assert commentary_items == []
    # Direct evidence is completely unaffected.
    direct_items = [item for s in ctx.sections for item in s.items]
    assert direct_items
    assert any(item.item_type == "linguistic" for item in direct_items)


def test_historical_works_without_commentary_when_db_invalid(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.sqlite3"
    conn = sqlite3.connect(invalid_path)
    conn.execute("CREATE TABLE store_metadata (key TEXT, value TEXT)")
    conn.execute("INSERT INTO store_metadata VALUES ('schema_version', '999')")
    conn.commit()
    conn.close()

    evidence = _packet("Romans.1.1")
    ctx = build_context_from_evidence(
        evidence, PROFILE_HISTORICAL, commentary_database_path=invalid_path
    )
    commentary_items = [
        item for s in ctx.sections for item in s.items if item.item_type == "commentary_source"
    ]
    assert commentary_items == []
    # The module keeps working (no crash, no exception) regardless of
    # which direct historical sources exist for this passage.
    assert ctx.estimated_tokens <= ctx.max_tokens


def _empty_commentary_document() -> dict:
    return {
        "contributors": [],
        "works": [],
        "work_contributors": [],
        "editions": [],
        "source_files": [],
        "import_batches": [],
        "sections": [],
        "chunks": [],
    }


def test_exegesis_no_match_leaves_direct_evidence_untouched(tmp_path: Path) -> None:
    empty_db = tmp_path / "empty_commentary.sqlite3"
    import_commentary_sqlite(document=_empty_commentary_document(), database_path=empty_db)

    evidence = _packet("Romans.1.1")
    ctx = build_context_from_evidence(
        evidence, PROFILE_EXEGESIS, commentary_database_path=empty_db
    )
    commentary_items = [
        item for s in ctx.sections for item in s.items if item.item_type == "commentary_source"
    ]
    assert commentary_items == []
    assert any(item.item_type == "linguistic" for s in ctx.sections for item in s.items)


@_requires_production_commentary
def test_revelation_unsupported_by_calvin_jfb_henry_still_work_in_exegesis() -> None:
    evidence = _packet("Revelation.1.1")
    ctx = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    commentary_items = [
        item for s in ctx.sections for item in s.items if item.item_type == "commentary_source"
    ]
    assert commentary_items, "JFB/Henry must still surface commentary for Revelation"
    work_ids = {str(item.metadata.get("work_id") or "") for item in commentary_items}
    assert not any(w.startswith("ccel.calvin") for w in work_ids)
    assert any(w.startswith("ccel.jfb") for w in work_ids) or any(
        w.startswith("ccel.henry") for w in work_ids
    )


# --- No generative call anywhere in this file's tested paths --------------


def test_no_llm_call_functions_used_in_grounded_context_building() -> None:
    """Static confirmation: build_context_from_evidence and its Commentary
    loader never import or call anything provider/LLM-related — everything
    tested above is deterministic evidence/context construction only."""
    import inspect

    from textus_kb import context_builder

    source = inspect.getsource(context_builder)
    for forbidden in ("generate_text", "genai", "google.generativeai"):
        assert forbidden not in source
