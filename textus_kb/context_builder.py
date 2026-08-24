"""Build module-specific LLM context packets from Evidence Packets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from textus_kb.context_profiles import (
    PROFILE_EXEGESIS,
    PROFILE_HISTORICAL,
    PROFILE_THEOLOGY,
    SUPPORTED_PROFILES,
    THEOLOGY_SOURCE_WARNING,
    ContextProfile,
)
from textus_kb.context_selection import SelectionStats, select_context_items
from textus_kb.evidence import (
    RELATION_DIRECT_PASSAGE,
    RELATION_DICTIONARY_BACKGROUND,
    RELATION_EXEGETICAL_NOTE,
    RELATION_LEXICAL_HIGHLIGHT,
    RELATION_PASSAGE_PLACE,
    RELATION_PASSAGE_TOKEN,
    RELATION_PLACE_CATALOG,
    RELATION_PLACE_ENRICHMENT,
    EvidenceItem,
    EvidencePacket,
    estimate_text_tokens,
)
from textus_kb.importers.acai_entities import ACAI_SOURCE_ID, GENERIC_ACAI_IDS
from textus_kb.retrieval import retrieve

SCHEMA_VERSION = "2"


@dataclass(frozen=True)
class ContextItem:
    text: str
    evidence_id: str
    source_id: str
    relevance_score: int
    item_type: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "relevance_score": self.relevance_score,
            "item_type": self.item_type,
            "metadata": dict(self.metadata),
        }

    def estimated_tokens(self) -> int:
        return estimate_text_tokens(self.text) + estimate_text_tokens(str(self.metadata))


@dataclass(frozen=True)
class ContextSection:
    type: str
    items: tuple[ContextItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class LLMContextPacket:
    passage: str
    passage_display: str
    profile: str
    sections: list[ContextSection] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    target_tokens: int = 3200
    token_budget: int = 4500
    max_tokens: int = 4500
    truncated: bool = False
    schema_version: str = SCHEMA_VERSION
    evidence_packet_build_id: str = ""
    selection_stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "passage": self.passage,
            "passage_display": self.passage_display,
            "profile": self.profile,
            "sections": [section.to_dict() for section in self.sections],
            "source_ids": list(self.source_ids),
            "evidence_ids": list(self.evidence_ids),
            "warnings": list(self.warnings),
            "estimated_tokens": self.estimated_tokens,
            "target_tokens": self.target_tokens,
            "token_budget": self.token_budget,
            "max_tokens": self.max_tokens,
            "truncated": self.truncated,
            "evidence_packet_build_id": self.evidence_packet_build_id,
            "selection_stats": dict(self.selection_stats),
        }


def build_context(
    reference: str,
    profile: str,
    *,
    token_budget: int | None = None,
    evidence: EvidencePacket | None = None,
) -> LLMContextPacket:
    packet = evidence if evidence is not None else retrieve(reference)
    profile_obj = ContextProfile.load(profile, token_budget=token_budget)
    return build_context_from_evidence(packet, profile_obj)


def build_context_from_evidence(
    evidence: EvidencePacket,
    profile: ContextProfile | str,
) -> LLMContextPacket:
    if isinstance(profile, str):
        profile = ContextProfile.load(profile)

    builders = {
        PROFILE_EXEGESIS: _build_exegesis_context,
        PROFILE_HISTORICAL: _build_historical_context,
        PROFILE_THEOLOGY: _build_theology_context,
    }
    builder = builders[profile.name]
    candidates = builder(evidence, profile)
    return _finalize_context_packet(evidence, profile, candidates)


def build_context_to_json(
    reference: str,
    profile: str,
    *,
    token_budget: int | None = None,
    evidence: EvidencePacket | None = None,
    indent: int | None = 2,
) -> str:
    packet = build_context(reference, profile, token_budget=token_budget, evidence=evidence)
    return json.dumps(packet.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)


def _dictionary_context_metadata(item: EvidenceItem, canonical_scope: str) -> dict[str, Any]:
    """Compact dictionary metadata for context selection (avoid large audit lists)."""
    passage_associations = item.metadata.get("passage_associations")
    entity_topics = item.metadata.get("entity_topics")
    return {
        "article_id": item.metadata.get("article_id"),
        "chunk_id": item.metadata.get("chunk_id"),
        "heading": item.metadata.get("heading"),
        "index_reference": item.metadata.get("index_reference"),
        "selection_reason": item.metadata.get("selection_reason"),
        "passage_linked": bool(passage_associations),
        "entity_topic_count": len(entity_topics) if isinstance(entity_topics, (list, tuple)) else 0,
        "entity_expansion": item.metadata.get("entity_expansion"),
        "license": item.metadata.get("license"),
        "license_url": item.metadata.get("license_url"),
        "attribution": item.metadata.get("attribution"),
        "upstream_commit": item.metadata.get("upstream_commit"),
        "upstream_resource_version": item.metadata.get("upstream_resource_version"),
        "canonical_scope": canonical_scope,
    }


def _build_exegesis_context(
    evidence: EvidencePacket,
    profile: ContextProfile,
) -> list[ContextItem]:
    items: list[ContextItem] = []
    by_relation = _index_evidence(evidence)

    for item in by_relation.get(RELATION_DIRECT_PASSAGE, []):
        items.append(
            ContextItem(
                text=f"Canonical passage: {evidence.passage_canonical} ({evidence.passage_display})",
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_DIRECT_PASSAGE],
                item_type="passage",
                metadata={"canonical_scope": evidence.passage_canonical},
            )
        )

    token_set = evidence.linguistic_evidence.get("passage_token_set", {})
    summary = (
        f"Greek NT coverage: {token_set.get('verse_count', 0)} verses, "
        f"{token_set.get('token_count', 0)} tokens (compact view; full set in Evidence Packet)."
    )
    for item in by_relation.get(RELATION_PASSAGE_TOKEN, []):
        items.append(
            ContextItem(
                text=summary,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities["passage_summary"],
                item_type="passage_summary",
                metadata={
                    "verse_count": token_set.get("verse_count"),
                    "token_count": token_set.get("token_count"),
                    "canonical_scope": evidence.passage_canonical,
                },
            )
        )

    highlight_evidence = {
        str(item.metadata.get("strong_id")): item
        for item in by_relation.get(RELATION_LEXICAL_HIGHLIGHT, [])
        if item.metadata.get("strong_id")
    }
    for highlight in evidence.linguistic_evidence.get("lexical_highlights", []):
        strong_id = str(highlight.get("strong_id") or "")
        linked = highlight_evidence.get(strong_id)
        if linked is None:
            continue
        verse_ref, token = _first_token_occurrence(token_set, strong_id)
        line = _format_compact_lexical_line(
            evidence.passage_display,
            verse_ref,
            highlight,
            token,
        )
        scope = (
            f"{evidence.passage_canonical.split('.')[0]}.{evidence.passage_canonical.split('.')[1]}.{verse_ref}"
            if verse_ref
            else evidence.passage_canonical
        )
        items.append(
            ContextItem(
                text=line,
                evidence_id=linked.evidence_id,
                source_id=linked.source_id,
                relevance_score=profile.priorities["compact_linguistic_line"],
                item_type="linguistic",
                metadata={
                    "strong_id": strong_id,
                    "verse": verse_ref,
                    "lemma": highlight.get("lemma"),
                    "canonical_scope": scope,
                },
            )
        )

    for item in sorted(
        by_relation.get(RELATION_EXEGETICAL_NOTE, []),
        key=lambda entry: (
            -entry.relevance_score,
            str(entry.metadata.get("article_id") or ""),
            int(entry.metadata.get("chunk_index") or 0),
        ),
    ):
        title = str(item.metadata.get("title") or item.passage or "Study Note")
        license_label = str(item.metadata.get("license") or "CC-BY-SA-4.0")
        text = (
            f"{title} [{item.passage}] — {item.content} "
            f"(Source: Aquifer Open Study Notes, {license_label})"
        )
        items.append(
            ContextItem(
                text=text,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_EXEGETICAL_NOTE],
                item_type="exegetical_note",
                metadata={
                    "article_id": item.metadata.get("article_id"),
                    "chunk_id": item.metadata.get("chunk_id"),
                    "license": item.metadata.get("license"),
                    "license_url": item.metadata.get("license_url"),
                    "attribution": item.metadata.get("attribution"),
                    "canonical_scope": item.passage,
                    "passage": item.passage,
                },
            )
        )

    for item in sorted(
        by_relation.get(RELATION_DICTIONARY_BACKGROUND, []),
        key=lambda entry: (
            -entry.relevance_score,
            str(entry.metadata.get("article_id") or ""),
            int(entry.metadata.get("chunk_index") or 0),
        ),
    ):
        title = str(item.metadata.get("title") or "Dictionary")
        heading = item.metadata.get("heading")
        heading_label = f" — {heading}" if heading else ""
        license_label = str(item.metadata.get("license") or "CC-BY-SA-4.0")
        text = (
            f"{title}{heading_label}: {item.content} "
            f"(Source: Aquifer Open Bible Dictionary, {license_label})"
        )
        items.append(
            ContextItem(
                text=text,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_DICTIONARY_BACKGROUND],
                item_type="dictionary_background",
                metadata=_dictionary_context_metadata(item, evidence.passage_canonical),
            )
        )

    for item in by_relation.get(RELATION_PASSAGE_PLACE, []):
        items.append(
            ContextItem(
                text=item.content,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PASSAGE_PLACE],
                item_type="place_link",
                metadata={
                    "place_id": item.metadata.get("place_id"),
                    "passage": item.passage,
                    "canonical_scope": item.passage,
                },
            )
        )

    for item in by_relation.get(RELATION_PLACE_CATALOG, []):
        items.append(
            ContextItem(
                text=item.content,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PLACE_CATALOG],
                item_type="place_catalog",
                metadata={"place_id": item.metadata.get("place_id")},
            )
        )

    for item in by_relation.get(RELATION_PLACE_ENRICHMENT, []):
        items.append(
            ContextItem(
                text=item.content,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PLACE_ENRICHMENT],
                item_type="enrichment",
                metadata={
                    "place_id": item.metadata.get("place_id"),
                    "section_key": item.metadata.get("section_key"),
                },
            )
        )

    items.extend(_entity_summary_items(evidence, profile))
    return items


def _build_historical_context(
    evidence: EvidencePacket,
    profile: ContextProfile,
) -> list[ContextItem]:
    items: list[ContextItem] = []
    by_relation = _index_evidence(evidence)

    items.append(
        ContextItem(
            text=f"Historical context scope: {evidence.passage_display} ({evidence.passage_canonical})",
            evidence_id=_first_evidence_id(by_relation, RELATION_DIRECT_PASSAGE),
            source_id=_first_source_id(by_relation, RELATION_DIRECT_PASSAGE) or "stepbible_tagnt",
            relevance_score=profile.priorities[RELATION_DIRECT_PASSAGE],
            item_type="passage_scope",
            metadata={"canonical_scope": evidence.passage_canonical},
        )
    )

    for item in by_relation.get(RELATION_PASSAGE_PLACE, []):
        place_id = str(item.metadata.get("place_id") or "")
        place = _find_place(evidence, place_id)
        coords = ""
        if place is not None:
            coords = f" ({place.latitude:.5f}, {place.longitude:.5f})"
        items.append(
            ContextItem(
                text=f"{item.content}{coords}",
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PASSAGE_PLACE],
                item_type="passage_place_link",
                metadata={
                    "place_id": place_id,
                    "passage": item.passage,
                    "canonical_scope": item.passage,
                },
            )
        )

    for item in sorted(
        by_relation.get(RELATION_DICTIONARY_BACKGROUND, []),
        key=lambda entry: (
            -entry.relevance_score,
            str(entry.metadata.get("article_id") or ""),
            int(entry.metadata.get("chunk_index") or 0),
        ),
    ):
        title = str(item.metadata.get("title") or "Dictionary")
        heading = item.metadata.get("heading")
        heading_label = f" — {heading}" if heading else ""
        license_label = str(item.metadata.get("license") or "CC-BY-SA-4.0")
        text = (
            f"{title}{heading_label}: {item.content} "
            f"(Source: Aquifer Open Bible Dictionary, {license_label})"
        )
        items.append(
            ContextItem(
                text=text,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_DICTIONARY_BACKGROUND],
                item_type="dictionary_background",
                metadata=_dictionary_context_metadata(item, evidence.passage_canonical),
            )
        )

    for item in by_relation.get(RELATION_PLACE_ENRICHMENT, []):
        items.append(
            ContextItem(
                text=item.content,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PLACE_ENRICHMENT],
                item_type="historical_enrichment",
                metadata={
                    "place_id": item.metadata.get("place_id"),
                    "section_key": item.metadata.get("section_key"),
                    "confidence": item.metadata.get("confidence"),
                },
            )
        )

    for item in by_relation.get(RELATION_PLACE_CATALOG, []):
        place_id = str(item.metadata.get("place_id") or "")
        place = _find_place(evidence, place_id)
        geography_bits = []
        if place is not None:
            geography_bits.append(
                f"Coordinates: {place.latitude:.5f}, {place.longitude:.5f}"
            )
            geography_bits.append(
                f"Identification status: {place.identification_status}"
            )
        geography = " | ".join(geography_bits)
        items.append(
            ContextItem(
                text=f"{item.content}" + (f" | {geography}" if geography else ""),
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PLACE_CATALOG],
                item_type="place_catalog",
                metadata={"place_id": place_id},
            )
        )
        if geography:
            items.append(
                ContextItem(
                    text=geography,
                    evidence_id=item.evidence_id,
                    source_id=item.source_id,
                    relevance_score=profile.priorities["place_geography"],
                    item_type="geography",
                    metadata={"place_id": place_id},
                )
            )

    items.extend(_entity_summary_items(evidence, profile))
    return items


def _entity_summary_items(
    evidence: EvidencePacket,
    profile: ContextProfile,
) -> list[ContextItem]:
    summaries: list[ContextItem] = []
    entities = [
        entity
        for entity in evidence.entities
        if isinstance(entity, dict)
        and str((entity.get("external_ids") or {}).get("acai") or "") not in GENERIC_ACAI_IDS
    ]
    entities.sort(
        key=lambda entity: (
            0 if entity.get("passage_relations") else 1,
            0 if entity.get("dictionary_relations") else 1,
            str(entity.get("entity_type") or ""),
            str(entity.get("canonical_name") or ""),
            str(entity.get("entity_id") or ""),
        )
    )
    passage_label = evidence.passage_display or evidence.passage_canonical
    for entity in entities[:8]:
        entity_id = str(entity.get("entity_id") or "")
        entity_type = str(entity.get("entity_type") or "entity")
        name = str(entity.get("canonical_name") or entity_id)
        if entity.get("passage_relations"):
            link_label = f"explicitly referenced in {passage_label}"
        elif entity.get("dictionary_relations"):
            link_label = f"dictionary-linked for {passage_label}"
        elif entity.get("place_crosswalk"):
            link_label = f"place crosswalk ({entity['place_crosswalk'].get('textus_place_id')})"
        else:
            link_label = f"ACAI entity for {passage_label}"
        text = f"{name} — {entity_type} — {link_label}"
        summaries.append(
            ContextItem(
                text=text,
                evidence_id=f"ENT-{entity_id}",
                source_id=ACAI_SOURCE_ID,
                relevance_score=profile.priorities.get(RELATION_PASSAGE_PLACE, 70),
                item_type="entity_summary",
                metadata={
                    "entity_id": entity_id,
                    "external_id": (entity.get("external_ids") or {}).get("acai"),
                    "entity_type": entity_type,
                    "budget_type": "entity",
                    "canonical_scope": evidence.passage_canonical,
                },
            )
        )
    return summaries


def _build_theology_context(
    evidence: EvidencePacket,
    profile: ContextProfile,
) -> list[ContextItem]:
    items: list[ContextItem] = []
    by_relation = _index_evidence(evidence)

    items.append(
        ContextItem(
            text=f"Theological reading scope: {evidence.passage_display} ({evidence.passage_canonical})",
            evidence_id=_first_evidence_id(by_relation, RELATION_DIRECT_PASSAGE),
            source_id=_first_source_id(by_relation, RELATION_DIRECT_PASSAGE) or "stepbible_tagnt",
            relevance_score=profile.priorities[RELATION_DIRECT_PASSAGE],
            item_type="passage",
            metadata={"canonical_scope": evidence.passage_canonical},
        )
    )

    highlight_evidence = {
        str(item.metadata.get("strong_id")): item
        for item in by_relation.get(RELATION_LEXICAL_HIGHLIGHT, [])
        if item.metadata.get("strong_id")
    }
    for highlight in evidence.linguistic_evidence.get("lexical_highlights", []):
        strong_id = str(highlight.get("strong_id") or "")
        linked = highlight_evidence.get(strong_id)
        if linked is None:
            continue
        gloss_en = highlight.get("gloss_en") or ""
        gloss_hu = highlight.get("gloss_hu") or ""
        gloss = " / ".join(part for part in (gloss_en, gloss_hu) if part)
        items.append(
            ContextItem(
                text=f"{highlight.get('lemma')} ({strong_id}): {gloss}".strip(),
                evidence_id=linked.evidence_id,
                source_id=linked.source_id,
                relevance_score=profile.priorities[RELATION_LEXICAL_HIGHLIGHT],
                item_type="lexical",
                metadata={"strong_id": strong_id},
            )
        )

    for item in by_relation.get(RELATION_PASSAGE_PLACE, []):
        items.append(
            ContextItem(
                text=item.content,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PASSAGE_PLACE],
                item_type="place_link",
                metadata={"place_id": item.metadata.get("place_id")},
            )
        )

    for item in by_relation.get(RELATION_PLACE_CATALOG, []):
        items.append(
            ContextItem(
                text=item.content,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                relevance_score=profile.priorities[RELATION_PLACE_CATALOG],
                item_type="place_catalog",
                metadata={"place_id": item.metadata.get("place_id")},
            )
        )

    return items


def _finalize_context_packet(
    evidence: EvidencePacket,
    profile: ContextProfile,
    candidates: list[ContextItem],
) -> LLMContextPacket:
    warnings = list(evidence.warnings)
    if profile.name == PROFILE_THEOLOGY:
        warnings.append(THEOLOGY_SOURCE_WARNING)

    kept, stats = select_context_items(
        candidates,
        profile,
        passage_canonical=evidence.passage_canonical,
    )
    sections = _group_sections(kept, profile.name)

    source_ids = sorted({item.source_id for item in kept})
    evidence_ids = [item.evidence_id for item in kept]

    packet = LLMContextPacket(
        passage=evidence.passage_canonical,
        passage_display=evidence.passage_display,
        profile=profile.name,
        sections=sections,
        source_ids=source_ids,
        evidence_ids=evidence_ids,
        warnings=warnings,
        target_tokens=profile.target_tokens,
        token_budget=profile.max_tokens,
        max_tokens=profile.max_tokens,
        truncated=stats.dropped_budget > 0,
        evidence_packet_build_id=evidence.build_id,
        selection_stats=stats.to_dict(),
    )
    packet.estimated_tokens = _estimate_context_tokens(packet)

    if stats.dropped_budget > 0:
        packet.warnings.append(
            f"Context hard-max pressure: dropped {stats.dropped_budget} item(s) "
            f"to stay within max_tokens={profile.max_tokens}."
        )
    if stats.study_notes_candidates and stats.study_notes_selected < stats.study_notes_candidates:
        packet.warnings.append(
            f"Aquifer notes selected {stats.study_notes_selected}/{stats.study_notes_candidates} "
            f"(source-aware selection; full set remains in Evidence Packet)."
        )
    if stats.dictionary_candidates and stats.dictionary_selected < stats.dictionary_candidates:
        packet.warnings.append(
            f"Dictionary chunks selected {stats.dictionary_selected}/{stats.dictionary_candidates} "
            f"(source-aware selection; full set remains in Evidence Packet)."
        )
    return packet


def _group_sections(items: list[ContextItem], profile: str) -> list[ContextSection]:
    section_order = _section_order(profile)
    buckets: dict[str, list[ContextItem]] = {key: [] for key in section_order}
    for item in items:
        section_type = _item_section_type(item.item_type)
        buckets.setdefault(section_type, []).append(item)

    sections: list[ContextSection] = []
    seen: set[str] = set()
    for section_type in section_order:
        if section_type in seen:
            continue
        bucket = buckets.get(section_type, [])
        if bucket:
            sections.append(ContextSection(type=section_type, items=tuple(bucket)))
            seen.add(section_type)
    for section_type, bucket in buckets.items():
        if section_type not in seen and bucket:
            sections.append(ContextSection(type=section_type, items=tuple(bucket)))
    return sections


def _section_order(profile: str) -> tuple[str, ...]:
    if profile == PROFILE_EXEGESIS:
        return ("passage", "linguistic", "exegetical", "dictionary", "entities", "places", "background")
    if profile == PROFILE_HISTORICAL:
        return ("passage", "dictionary", "entities", "places", "historical", "geography")
    return ("passage", "lexical", "places", "background")


def _item_section_type(item_type: str) -> str:
    mapping = {
        "passage": "passage",
        "passage_summary": "passage",
        "passage_scope": "passage",
        "linguistic": "linguistic",
        "exegetical_note": "exegetical",
        "dictionary_background": "dictionary",
        "entity_summary": "entities",
        "lexical": "lexical",
        "place_link": "places",
        "passage_place_link": "places",
        "place_catalog": "places",
        "enrichment": "background",
        "historical_enrichment": "historical",
        "geography": "geography",
    }
    return mapping.get(item_type, "background")


def _estimate_context_tokens(packet: LLMContextPacket) -> int:
    total = 0
    for section in packet.sections:
        for item in section.items:
            total += item.estimated_tokens()
    return total


def _index_evidence(evidence: EvidencePacket) -> dict[str, list[EvidenceItem]]:
    buckets: dict[str, list[EvidenceItem]] = {}
    for item in evidence.evidence_items:
        buckets.setdefault(item.relation_type, []).append(item)
    for relation_items in buckets.values():
        relation_items.sort(key=lambda entry: entry.evidence_id)
    return buckets


def _first_evidence_id(
    by_relation: dict[str, list[EvidenceItem]],
    relation_type: str,
) -> str:
    items = by_relation.get(relation_type, [])
    return items[0].evidence_id if items else "EV-UNKNOWN-0000"


def _first_source_id(
    by_relation: dict[str, list[EvidenceItem]],
    relation_type: str,
) -> str | None:
    items = by_relation.get(relation_type, [])
    return items[0].source_id if items else None


def _find_place(evidence: EvidencePacket, place_id: str):
    for place in evidence.places:
        if place.place_id == place_id:
            return place
    return None


def _first_token_occurrence(
    token_set: dict[str, Any],
    strong_id: str,
) -> tuple[int | None, dict[str, Any] | None]:
    for verse in token_set.get("verses", []):
        for token in verse.get("tokens", []):
            if str(token.get("strong_id") or "").upper() == strong_id.upper():
                return int(verse.get("verse", 0)), token
    return None, None


def _format_compact_lexical_line(
    passage_display: str,
    verse: int | None,
    highlight: dict[str, Any],
    token: dict[str, Any] | None,
) -> str:
    book_chapter = _passage_prefix(passage_display)
    verse_ref = f"{book_chapter}{verse}" if verse else book_chapter.rstrip()
    lemma = highlight.get("lemma") or (token or {}).get("lemma") or ""
    strong_id = highlight.get("strong_id") or (token or {}).get("strong_id") or ""
    morph = _describe_morph((token or {}).get("morph_code"))
    gloss_en = highlight.get("gloss_en") or ""
    gloss_hu = highlight.get("gloss_hu") or ""
    gloss = " / ".join(
        part
        for part in (
            f'"{gloss_en}"' if gloss_en else "",
            f'"{gloss_hu}"' if gloss_hu else "",
        )
        if part
    )
    greek_form = (token or {}).get("greek_form") or lemma
    parts = [f"{verse_ref} — {greek_form} ({strong_id})"]
    if morph:
        parts.append(morph)
    if gloss:
        parts.append(gloss)
    return ", ".join(parts)


def _passage_prefix(passage_display: str) -> str:
    match = re.match(r"^(.+?\s+\d+),", passage_display.replace(":", ","))
    if match:
        return f"{match.group(1)},"
    return passage_display.split("-")[0].strip() + ","


def _describe_morph(morph_code: str | None) -> str:
    if not morph_code:
        return ""
    code = str(morph_code)
    if code.startswith("N"):
        return "noun"
    if code.startswith("V"):
        return "verb"
    if code.startswith("A"):
        return "adjective"
    if code.startswith("C"):
        return "conjunction"
    if code.startswith("P"):
        return "pronoun"
    if code.startswith("D"):
        return "adverb"
    if code.startswith("RA"):
        return "article"
    return f"morph={code}"


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            'Usage: python -m textus_kb context "<reference>" --profile exegesis',
            file=sys.stderr,
        )
        return 2

    reference_parts: list[str] = []
    profile = PROFILE_EXEGESIS
    token_budget: int | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--profile" and i + 1 < len(args):
            profile = args[i + 1]
            i += 2
            continue
        if arg == "--token-budget" and i + 1 < len(args):
            token_budget = int(args[i + 1])
            i += 2
            continue
        reference_parts.append(arg)
        i += 1

    if profile not in SUPPORTED_PROFILES:
        print(json.dumps({"error": f"Unsupported profile: {profile!r}"}), file=sys.stderr)
        return 2

    reference = " ".join(reference_parts).strip()
    if not reference:
        print(json.dumps({"error": "Missing reference."}), file=sys.stderr)
        return 2

    try:
        output = build_context_to_json(reference, profile, token_budget=token_budget)
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    _print_json(output)
    return 0


def _print_json(text: str) -> None:
    import sys

    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.write(b"\n")
        return
    print(text)


__all__ = [
    "LLMContextPacket",
    "ContextItem",
    "ContextSection",
    "build_context",
    "build_context_from_evidence",
    "build_context_to_json",
    "main",
]
