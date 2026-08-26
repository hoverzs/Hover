"""Stable Knowledge Base entity identity models (Phase 4A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAPPING_EXPLICIT = "explicit"
MAPPING_EXTERNAL_ID = "external_id"
MAPPING_VERIFIED_EXACT_MATCH = "verified_exact_match"
MAPPING_UNRESOLVED = "unresolved"

RELATION_PASSAGE_MENTION = "passage_mention"
RELATION_DICTIONARY_ASSOCIATION = "dictionary_association"


@dataclass(frozen=True)
class EntityAlias:
    label: str
    language: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "language": self.language, "source": self.source}


@dataclass(frozen=True)
class EntityPassageRelation:
    canonical_passage: str
    relation_type: str
    source_id: str
    upstream_refs: tuple[str, ...] = ()
    mapping_method: str = MAPPING_EXPLICIT
    confidence: str = MAPPING_EXPLICIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_passage": self.canonical_passage,
            "relation_type": self.relation_type,
            "source_id": self.source_id,
            "upstream_refs": list(self.upstream_refs),
            "mapping_method": self.mapping_method,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class EntityDictionaryRelation:
    dictionary_article_id: str
    dictionary_title: str
    acai_id: str
    match_method: str
    match_confidence: float | None
    source_id: str
    mapping_method: str = MAPPING_EXPLICIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "dictionary_article_id": self.dictionary_article_id,
            "dictionary_title": self.dictionary_title,
            "acai_id": self.acai_id,
            "match_method": self.match_method,
            "match_confidence": self.match_confidence,
            "source_id": self.source_id,
            "mapping_method": self.mapping_method,
        }


@dataclass(frozen=True)
class PlaceCrosswalk:
    textus_place_id: str
    acai_entity_id: str
    openbible_id: str | None
    pleiades_id: str | None
    canonical_name: str
    mapping_method: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "textus_place_id": self.textus_place_id,
            "acai_entity_id": self.acai_entity_id,
            "openbible_id": self.openbible_id,
            "pleiades_id": self.pleiades_id,
            "canonical_name": self.canonical_name,
            "mapping_method": self.mapping_method,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class KBEntity:
    entity_id: str
    entity_type: str
    canonical_name: str
    source_id: str
    external_id: str
    aliases: tuple[EntityAlias, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    passage_relations: tuple[EntityPassageRelation, ...] = ()
    dictionary_relations: tuple[EntityDictionaryRelation, ...] = ()
    place_crosswalk: PlaceCrosswalk | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "source_id": self.source_id,
            "external_ids": {"acai": self.external_id},
            "aliases": [alias.to_dict() for alias in self.aliases],
            "metadata": dict(self.metadata),
            "provenance": dict(self.provenance),
            "passage_relations": [rel.to_dict() for rel in self.passage_relations],
            "dictionary_relations": [rel.to_dict() for rel in self.dictionary_relations],
        }
        if self.place_crosswalk is not None:
            payload["place_crosswalk"] = self.place_crosswalk.to_dict()
        return payload


def textus_entity_id_from_acai(acai_id: str) -> str:
    """Deterministic Textus ID: acai type prefix + slug, e.g. acai-place-Sychar."""
    if ":" not in acai_id:
        return f"acai-unknown-{acai_id}"
    entity_type, slug = acai_id.split(":", 1)
    return f"acai-{entity_type}-{slug}"
