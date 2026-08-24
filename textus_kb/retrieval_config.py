"""Retrieval candidate limits for full-corpus Aquifer SQLite (Phase 4D)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AquiferRetrievalLimits:
    study_notes_candidate_limit: int = 24
    dictionary_candidate_limit: int = 48
    entity_dictionary_candidate_limit: int = 24


DEFAULT_AQUIFER_LIMITS = AquiferRetrievalLimits()


@dataclass(frozen=True)
class AcaiRetrievalLimits:
    evidence_entity_limit: int = 40
    context_entity_limit: int = 8


DEFAULT_ACAI_LIMITS = AcaiRetrievalLimits()
