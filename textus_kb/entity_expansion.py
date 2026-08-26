"""Deterministic entity-driven dictionary retrieval expansion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from textus_kb.adapters.acai_entities import AcaiEntitiesAdapter, AcaiEntityView
from textus_kb.adapters.aquifer_bible_dictionary import AquiferBibleDictionaryAdapter
from textus_kb.canonical_reference import CanonicalReference
from textus_kb.dictionary_relevance import (
    annotate_dictionary_scope_metadata,
    dictionary_relevance_score,
    is_expanded_dictionary_relevant,
    passage_term_labels,
)
from textus_kb.evidence import (
    EvidenceItem,
    RELATION_DICTIONARY_BACKGROUND,
)
from textus_kb.importers.aquifer_bible_dictionary import AQUIFER_DICTIONARY_SOURCE_ID

MAX_ENTITY_EXPANSION = 12
MAX_DICTIONARY_CANDIDATES_PER_ENTITY = 3
MAX_TOTAL_EXPANSION_CANDIDATES = 40

PRIORITY_PASSAGE_ENTITY = 0
PRIORITY_PASSAGE_AND_DICTIONARY = 1
PRIORITY_VERIFIED_CROSSWALK = 2
PRIORITY_INDIRECT = 3

SELECTION_REASON = "entity_acai_dictionary_link"


@dataclass
class EntityExpansionDiagnostics:
    entities_considered: int = 0
    entities_used: int = 0
    dictionary_candidates_added: int = 0
    dropped_by_limit: int = 0
    dropped_by_relevance: int = 0
    direct_dictionary_candidates: int = 0
    entity_ids_used: list[str] = field(default_factory=list)
    article_ids_added: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities_considered": self.entities_considered,
            "entities_used": self.entities_used,
            "dictionary_candidates_added": self.dictionary_candidates_added,
            "dropped_by_limit": self.dropped_by_limit,
            "dropped_by_relevance": self.dropped_by_relevance,
            "direct_dictionary_candidates": self.direct_dictionary_candidates,
            "entity_ids_used": list(self.entity_ids_used),
            "article_ids_added": list(self.article_ids_added),
        }


def expand_dictionary_evidence(
    *,
    reference: CanonicalReference,
    canonical_passage: str,
    acai_adapter: AcaiEntitiesAdapter,
    dictionary_adapter: AquiferBibleDictionaryAdapter,
    direct_evidence_items: list[EvidenceItem],
    dictionary_counter_start: int,
    dict_meta: dict[str, Any],
) -> tuple[list[EvidenceItem], EntityExpansionDiagnostics]:
    """Add dictionary chunks linked via ACAI entities (explicit associations only)."""
    diagnostics = EntityExpansionDiagnostics()
    if not acai_adapter.available or not dictionary_adapter.available:
        return [], diagnostics

    direct_article_ids = {
        str(item.metadata.get("article_id") or "")
        for item in direct_evidence_items
        if item.relation_type == RELATION_DICTIONARY_BACKGROUND and item.metadata.get("article_id")
    }
    diagnostics.direct_dictionary_candidates = len(direct_article_ids)

    passage_entities = acai_adapter.entities_for_passage(reference)
    passage_terms = passage_term_labels(passage_entities)
    all_entities = acai_adapter.entities_for_evidence_packet(reference)
    considered = _dedupe_views(passage_entities + [e for e in all_entities if e not in passage_entities])
    diagnostics.entities_considered = len(considered)

    ranked = sorted(considered, key=_entity_priority_key)
    expanded_items: list[EvidenceItem] = []
    counter = dictionary_counter_start
    seen_article_entity: set[tuple[str, str]] = set()

    for entity in ranked:
        if diagnostics.entities_used >= MAX_ENTITY_EXPANSION:
            diagnostics.dropped_by_limit += 1
            continue
        if diagnostics.dictionary_candidates_added >= MAX_TOTAL_EXPANSION_CANDIDATES:
            diagnostics.dropped_by_limit += 1
            continue

        articles = _dictionary_articles_for_entity(entity, acai_adapter)
        if not articles:
            continue

        entity_used = False
        per_entity_added = 0
        for article in articles:
            if per_entity_added >= MAX_DICTIONARY_CANDIDATES_PER_ENTITY:
                diagnostics.dropped_by_limit += 1
                break
            if diagnostics.dictionary_candidates_added >= MAX_TOTAL_EXPANSION_CANDIDATES:
                diagnostics.dropped_by_limit += 1
                break

            article_id = str(article["dictionary_article_id"])
            dedupe_key = (article_id, entity.entity_id)
            if dedupe_key in seen_article_entity:
                continue
            if article_id in direct_article_ids:
                continue

            chunks = dictionary_adapter.load_chunks_for_article(article_id)
            if not chunks:
                continue

            sample = chunks[0]
            if not is_expanded_dictionary_relevant(
                reference=reference,
                title=sample.title or str(article.get("dictionary_title") or ""),
                index_reference=sample.index_reference,
                passage_associations=sample.passage_associations,
                entity_name=entity.canonical_name,
                match_method=str(article.get("match_method") or ""),
                match_confidence=_as_float(article.get("match_confidence")),
                passage_terms=passage_terms,
            ):
                diagnostics.dropped_by_relevance += 1
                continue

            seen_article_entity.add(dedupe_key)
            entity_used = True
            per_entity_added += 1
            for chunk in chunks[:MAX_DICTIONARY_CANDIDATES_PER_ENTITY]:
                if diagnostics.dictionary_candidates_added >= MAX_TOTAL_EXPANSION_CANDIDATES:
                    diagnostics.dropped_by_limit += 1
                    break

                expansion_meta = {
                    "passage": canonical_passage,
                    "entity_id": entity.entity_id,
                    "acai_id": entity.external_id,
                    "entity_type": entity.entity_type,
                    "canonical_name": entity.canonical_name,
                    "dictionary_article_id": article_id,
                    "dictionary_title": article.get("dictionary_title"),
                    "match_method": article.get("match_method"),
                    "match_confidence": article.get("match_confidence"),
                    "mapping_method": article.get("mapping_method"),
                    "priority_tier": _priority_tier(entity),
                    "relevance_reason": "strong_entity_dictionary_match",
                }
                metadata = {
                    "article_id": chunk.article_id,
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "title": chunk.title,
                    "heading": chunk.heading,
                    "index_reference": chunk.index_reference,
                    "content_html": chunk.content_html,
                    "selection_reason": SELECTION_REASON,
                    "passage_associations": list(chunk.passage_associations),
                    "entity_topics": [
                        {
                            "entity_id": entity.entity_id,
                            "acai_id": entity.external_id,
                            "canonical_name": entity.canonical_name,
                            "entity_type": entity.entity_type,
                        }
                    ],
                    "entity_expansion": expansion_meta,
                    "license": chunk.license,
                    "license_url": chunk.license_url,
                    "attribution": chunk.attribution,
                    "upstream_commit": dict_meta.get("upstream_commit"),
                    "upstream_resource_version": dict_meta.get("upstream_resource_version"),
                    "relevance_reason": "strong_entity_dictionary_match",
                }
                annotate_dictionary_scope_metadata(
                    metadata,
                    reference=reference,
                    request_scope=canonical_passage,
                )
                relevance = dictionary_relevance_score(
                    reference=reference,
                    title=chunk.title,
                    index_reference=chunk.index_reference,
                    passage_associations=chunk.passage_associations,
                    passage_terms=passage_terms,
                    entity_expansion=expansion_meta,
                    selection_reason=SELECTION_REASON,
                )
                stable_id = (
                    f"EV-DICT-{chunk.chunk_id}"
                    if dictionary_adapter.backend == "sqlite" and chunk.chunk_id
                    else f"EV-DICT-{counter:04d}"
                )
                expanded_items.append(
                    EvidenceItem(
                        evidence_id=stable_id,
                        source_id=AQUIFER_DICTIONARY_SOURCE_ID,
                        source_type="bible_dictionary",
                        language="en",
                        relation_type=RELATION_DICTIONARY_BACKGROUND,
                        passage=metadata.get("source_scope"),
                        content=chunk.content_plain,
                        metadata=metadata,
                        relevance_score=relevance,
                    )
                )
                counter += 1
                diagnostics.dictionary_candidates_added += 1
                if article_id not in diagnostics.article_ids_added:
                    diagnostics.article_ids_added.append(article_id)

        if entity_used:
            diagnostics.entities_used += 1
            diagnostics.entity_ids_used.append(entity.entity_id)

    return expanded_items, diagnostics


def _dictionary_articles_for_entity(
    entity: AcaiEntityView,
    adapter: AcaiEntitiesAdapter,
) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel in entity.dictionary_relations:
        article_id = str(rel.get("dictionary_article_id") or "")
        if not article_id or article_id in seen:
            continue
        seen.add(article_id)
        articles.append(
            {
                "dictionary_article_id": article_id,
                "dictionary_title": rel.get("dictionary_title"),
                "match_method": rel.get("match_method"),
                "match_confidence": rel.get("match_confidence"),
                "mapping_method": rel.get("mapping_method"),
            }
        )
    if adapter.repository is not None:
        for item in adapter.repository.dictionary_articles_for_entity(entity.entity_id):
            article_id = str(item.get("dictionary_article_id") or "")
            if not article_id or article_id in seen:
                continue
            seen.add(article_id)
            articles.append(item)
    return articles


def _entity_priority_key(entity: AcaiEntityView) -> tuple[int, str, str, str]:
    return (_priority_tier(entity), entity.entity_type, entity.canonical_name, entity.entity_id)


def _priority_tier(entity: AcaiEntityView) -> int:
    if entity.passage_relations and entity.dictionary_relations:
        return PRIORITY_PASSAGE_AND_DICTIONARY
    if entity.passage_relations:
        return PRIORITY_PASSAGE_ENTITY
    if entity.place_crosswalk and entity.place_crosswalk.get("mapping_method") in {
        "external_id",
        "verified_exact_match",
    }:
        return PRIORITY_VERIFIED_CROSSWALK
    return PRIORITY_INDIRECT


def _dedupe_views(views: list[AcaiEntityView]) -> list[AcaiEntityView]:
    seen: set[str] = set()
    ordered: list[AcaiEntityView] = []
    for view in views:
        if view.entity_id in seen:
            continue
        seen.add(view.entity_id)
        ordered.append(view)
    return ordered


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
