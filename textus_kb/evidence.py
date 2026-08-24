"""Evidence item and packet models for Knowledge Base retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

PILOT_BUILD_ID = "kb-phase2a-john4-pilot-v1"
PILOT_BUILD_ID_WITH_AQUIFER = "kb-phase3a-john4-pilot-v1"
PILOT_BUILD_ID_WITH_DICTIONARY = "kb-phase3c-john4-pilot-v1"
PILOT_BUILD_ID_WITH_ACAI = "kb-phase4a-john4-pilot-v1"
PILOT_BUILD_ID_WITH_ACAI_SQLITE = "kb-phase4b-john4-pilot-v1"
PILOT_BUILD_ID_PHASE4C = "kb-phase4c-multipilot-v1"
PILOT_BUILD_ID_PHASE4D = "kb-phase4d-aquifer-sqlite-v1"
PILOT_BUILD_ID_PHASE4E = "kb-phase4e-acai-full-runtime-v1"

# Deterministic relevance tiers (higher = retained first under token budget).
RELEVANCE_DIRECT_PASSAGE = 100
RELEVANCE_PASSAGE_PLACE = 85
RELEVANCE_EXEGETICAL_NOTE = 82
RELEVANCE_DICTIONARY_PASSAGE = 88
RELEVANCE_DICTIONARY_ENTITY = 80
RELEVANCE_DICTIONARY_TOPIC = 72
RELEVANCE_DICTIONARY_BACKGROUND = 65
RELEVANCE_PLACE_CATALOG = 75
RELEVANCE_LEXICAL_HIGHLIGHT = 70
RELEVANCE_PLACE_ENRICHMENT = 45

RELATION_DIRECT_PASSAGE = "direct_passage_match"
RELATION_PASSAGE_TOKEN = "passage_token"
RELATION_LEXICAL_HIGHLIGHT = "lexical_highlight"
RELATION_PASSAGE_PLACE = "passage_place_link"
RELATION_PLACE_CATALOG = "place_catalog"
RELATION_PLACE_ENRICHMENT = "place_enrichment"
RELATION_EXEGETICAL_NOTE = "exegetical_note"
RELATION_DICTIONARY_BACKGROUND = "dictionary_background"


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    source_id: str
    source_type: str
    language: str
    relation_type: str
    passage: str | None
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    relevance_score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "language": self.language,
            "relation_type": self.relation_type,
            "passage": self.passage,
            "content": self.content,
            "metadata": dict(self.metadata),
            "relevance_score": self.relevance_score,
        }

    def estimated_tokens(self) -> int:
        return estimate_text_tokens(self.content) + estimate_text_tokens(
            str(self.metadata)
        )


@dataclass(frozen=True)
class PlaceRecord:
    place_id: str
    name_hu: str
    name_en: str | None
    latitude: float
    longitude: float
    passage_links: tuple[str, ...]
    source_id: str
    identification_status: str
    card_summary_hu: str | None = None
    enrichment_excerpt_hu: str | None = None
    enrichment_confidence: str | None = None
    enrichment_source_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "place_id": self.place_id,
            "name_hu": self.name_hu,
            "name_en": self.name_en,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "passage_links": list(self.passage_links),
            "source_id": self.source_id,
            "identification_status": self.identification_status,
        }
        if self.card_summary_hu:
            payload["card_summary_hu"] = self.card_summary_hu
        if self.enrichment_excerpt_hu:
            payload["enrichment_excerpt_hu"] = self.enrichment_excerpt_hu
            payload["enrichment_confidence"] = self.enrichment_confidence
            payload["enrichment_source_ids"] = list(self.enrichment_source_ids)
        return payload


@dataclass(frozen=True)
class PassageTokenSummary:
    verse: int
    token_count: int
    tokens: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verse": self.verse,
            "token_count": self.token_count,
            "tokens": list(self.tokens),
        }


@dataclass(frozen=True)
class LexicalHighlight:
    strong_id: str
    lemma: str
    token_count_in_passage: int
    gloss_en: str | None
    gloss_hu: str | None
    source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strong_id": self.strong_id,
            "lemma": self.lemma,
            "token_count_in_passage": self.token_count_in_passage,
            "gloss_en": self.gloss_en,
            "gloss_hu": self.gloss_hu,
            "source_ids": list(self.source_ids),
        }


@dataclass
class EvidencePacket:
    passage_canonical: str
    passage_display: str
    build_id: str
    manifest_version: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    places: list[PlaceRecord] = field(default_factory=list)
    linguistic_evidence: dict[str, Any] = field(default_factory=dict)
    historical_evidence: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    supplemental_tokens: int = 0
    token_budget: int = 4500
    token_budget_applied: bool = False
    retrieval_debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "passage": {
                "canonical": self.passage_canonical,
                "display": self.passage_display,
            },
            "build": {
                "build_id": self.build_id,
                "manifest_version": self.manifest_version,
            },
            "entities": list(self.entities),
            "places": [place.to_dict() for place in self.places],
            "linguistic_evidence": dict(self.linguistic_evidence),
            "historical_evidence": list(self.historical_evidence),
            "sources": list(self.sources),
            "evidence_items": [item.to_dict() for item in self.evidence_items],
            "warnings": list(self.warnings),
            "estimated_tokens": self.estimated_tokens,
            "supplemental_tokens": self.supplemental_tokens,
            "token_budget": self.token_budget,
            "token_budget_applied": self.token_budget_applied,
        }
        if self.retrieval_debug:
            payload["retrieval_debug"] = dict(self.retrieval_debug)
        return payload


def estimate_text_tokens(text: str) -> int:
    """Documented approximation: max(word_count, char_count // 4)."""
    if not text:
        return 0
    stripped = text.strip()
    if not stripped:
        return 0
    word_count = len(stripped.split())
    char_estimate = len(stripped) // 4
    return max(word_count, char_estimate, 1)


def estimate_packet_tokens(
    packet: EvidencePacket,
    *,
    include_passage_token_set: bool = True,
) -> int:
    total = 0
    for item in packet.evidence_items:
        total += item.estimated_tokens()
    for place in packet.places:
        total += estimate_text_tokens(place.card_summary_hu or "")
        total += estimate_text_tokens(place.enrichment_excerpt_hu or "")
    linguistic = packet.linguistic_evidence
    if linguistic:
        if include_passage_token_set:
            token_set = linguistic.get("passage_token_set")
            if isinstance(token_set, dict):
                total += estimate_text_tokens(json.dumps(token_set, ensure_ascii=False))
        for highlight in linguistic.get("lexical_highlights", []):
            total += estimate_text_tokens(str(highlight))
    for entry in packet.historical_evidence:
        total += estimate_text_tokens(str(entry))
    return total


def estimate_supplemental_tokens(packet: EvidencePacket) -> int:
    """Token estimate excluding the full passage Greek token set."""
    return estimate_packet_tokens(packet, include_passage_token_set=False)


def estimate_trimmable_supplemental_tokens(packet: EvidencePacket) -> int:
    """Supplemental estimate excluding passage tokens, Aquifer notes, and dictionary evidence."""
    total = 0
    for item in packet.evidence_items:
        if item.relation_type in {RELATION_EXEGETICAL_NOTE, RELATION_DICTIONARY_BACKGROUND}:
            continue
        total += item.estimated_tokens()
    for place in packet.places:
        total += estimate_text_tokens(place.card_summary_hu or "")
        total += estimate_text_tokens(place.enrichment_excerpt_hu or "")
    linguistic = packet.linguistic_evidence
    if linguistic:
        for highlight in linguistic.get("lexical_highlights", []):
            total += estimate_text_tokens(str(highlight))
    for entry in packet.historical_evidence:
        total += estimate_text_tokens(str(entry))
    return total
