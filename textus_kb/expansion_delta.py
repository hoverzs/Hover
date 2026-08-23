"""Expansion delta metrics for direct vs entity-expanded retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from textus_kb.entity_expansion import SELECTION_REASON
from textus_kb.evidence import (
    RELATION_DICTIONARY_BACKGROUND,
    RELATION_EXEGETICAL_NOTE,
    RELATION_LEXICAL_HIGHLIGHT,
    RELATION_PASSAGE_PLACE,
    EvidenceItem,
)


@dataclass
class ExpansionDelta:
    direct_candidates: int = 0
    entity_candidates: int = 0
    duplicate_with_direct: int = 0
    unique_entity_candidates: int = 0
    unique_entity_selected: int = 0
    direct_evidence_ids: list[str] = field(default_factory=list)
    unique_entity_evidence_ids: list[str] = field(default_factory=list)
    selected_entity_evidence_ids: list[str] = field(default_factory=list)
    entity_provenance: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "direct_candidates": self.direct_candidates,
            "entity_candidates": self.entity_candidates,
            "duplicate_with_direct": self.duplicate_with_direct,
            "unique_entity_candidates": self.unique_entity_candidates,
            "unique_entity_selected": self.unique_entity_selected,
            "direct_evidence_ids": list(self.direct_evidence_ids),
            "unique_entity_evidence_ids": list(self.unique_entity_evidence_ids),
            "selected_entity_evidence_ids": list(self.selected_entity_evidence_ids),
            "entity_provenance": list(self.entity_provenance),
        }


def count_direct_candidates(evidence_items: list[EvidenceItem]) -> int:
    """Count non-entity-expanded supplemental evidence items."""
    return sum(
        1
        for item in evidence_items
        if item.metadata.get("selection_reason") != SELECTION_REASON
        and item.relation_type
        in {
            RELATION_DICTIONARY_BACKGROUND,
            RELATION_EXEGETICAL_NOTE,
            RELATION_LEXICAL_HIGHLIGHT,
            RELATION_PASSAGE_PLACE,
        }
    )


def compute_expansion_delta(
    *,
    direct_evidence_items: list[EvidenceItem],
    expanded_items: list[EvidenceItem],
) -> ExpansionDelta:
    direct_chunk_ids = {
        str(item.metadata.get("chunk_id") or "")
        for item in direct_evidence_items
        if item.relation_type == RELATION_DICTIONARY_BACKGROUND and item.metadata.get("chunk_id")
    }
    direct_article_ids = {
        str(item.metadata.get("article_id") or "")
        for item in direct_evidence_items
        if item.relation_type == RELATION_DICTIONARY_BACKGROUND and item.metadata.get("article_id")
    }

    entity_items = [
        item
        for item in expanded_items
        if item.metadata.get("selection_reason") == SELECTION_REASON
    ]
    duplicates = 0
    unique_items: list[EvidenceItem] = []
    for item in entity_items:
        chunk_id = str(item.metadata.get("chunk_id") or "")
        article_id = str(item.metadata.get("article_id") or "")
        if chunk_id and chunk_id in direct_chunk_ids:
            duplicates += 1
            continue
        if article_id and article_id in direct_article_ids:
            duplicates += 1
            continue
        unique_items.append(item)

    provenance = []
    for item in unique_items:
        expansion = item.metadata.get("entity_expansion")
        if isinstance(expansion, dict):
            provenance.append(dict(expansion))

    return ExpansionDelta(
        direct_candidates=count_direct_candidates(direct_evidence_items),
        entity_candidates=len(entity_items),
        duplicate_with_direct=duplicates,
        unique_entity_candidates=len(unique_items),
        direct_evidence_ids=[
            item.evidence_id
            for item in direct_evidence_items
            if item.relation_type == RELATION_DICTIONARY_BACKGROUND
        ],
        unique_entity_evidence_ids=[item.evidence_id for item in unique_items],
        entity_provenance=provenance,
    )


def apply_selected_entity_evidence(
    delta: ExpansionDelta,
    selected_evidence_ids: set[str],
) -> ExpansionDelta:
    selected = [eid for eid in delta.unique_entity_evidence_ids if eid in selected_evidence_ids]
    return ExpansionDelta(
        direct_candidates=delta.direct_candidates,
        entity_candidates=delta.entity_candidates,
        duplicate_with_direct=delta.duplicate_with_direct,
        unique_entity_candidates=delta.unique_entity_candidates,
        unique_entity_selected=len(selected),
        direct_evidence_ids=list(delta.direct_evidence_ids),
        unique_entity_evidence_ids=list(delta.unique_entity_evidence_ids),
        selected_entity_evidence_ids=selected,
        entity_provenance=list(delta.entity_provenance),
    )
