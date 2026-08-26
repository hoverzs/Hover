"""Deterministic ACAI entity selection for evidence packets and context."""

from __future__ import annotations

from typing import Any, Protocol

from textus_kb.importers.acai_entities import GENERIC_ACAI_IDS, PASSAGE_ENTITY_TYPES

PRIMARY_ENTITY_TYPES = PASSAGE_ENTITY_TYPES
SUPPORTING_ENTITY_TYPES = frozenset({"deity", "realia", "fauna", "flora", "keyterm"})


class EntityViewLike(Protocol):
    entity_id: str
    entity_type: str
    canonical_name: str
    external_id: str
    passage_relations: tuple[Any, ...]
    dictionary_relations: tuple[Any, ...]


def entity_selection_score(
    view: EntityViewLike,
    *,
    dictionary_article_ids: frozenset[str] | None = None,
) -> tuple[int, int, int, str, str]:
    """Higher tuple values sort first (deterministic tie-break on name/id)."""
    score = 0
    if view.passage_relations:
        score += 1000
    if dictionary_article_ids and any(
        str(rel.get("dictionary_article_id") or "") in dictionary_article_ids
        for rel in view.dictionary_relations
    ):
        score += 500
    elif view.dictionary_relations:
        score += 200
    if view.entity_type in PRIMARY_ENTITY_TYPES:
        score += 100
    elif view.entity_type in SUPPORTING_ENTITY_TYPES:
        score += 40
    generic_penalty = 1 if view.external_id in GENERIC_ACAI_IDS else 0
    return (
        -generic_penalty,
        score,
        -len(view.passage_relations),
        view.canonical_name.casefold(),
        view.entity_id,
    )


def select_entities_for_evidence(
    views: list[EntityViewLike],
    *,
    limit: int,
    dictionary_article_ids: frozenset[str] | None = None,
) -> list[EntityViewLike]:
    if not views:
        return []
    ranked = sorted(
        views,
        key=lambda view: entity_selection_score(
            view,
            dictionary_article_ids=dictionary_article_ids,
        ),
    )
    selected: list[EntityViewLike] = []
    seen: set[str] = set()
    for view in ranked:
        if view.entity_id in seen:
            continue
        seen.add(view.entity_id)
        selected.append(view)
        if len(selected) >= limit:
            break
    return selected


def entity_type_counts(entities: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in entities:
        entity_type = str(entity.get("entity_type") or "unknown")
        counts[entity_type] = counts.get(entity_type, 0) + 1
    return dict(sorted(counts.items()))
