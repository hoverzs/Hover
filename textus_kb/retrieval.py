"""Deterministic passage retrieval for the Knowledge Base pilot."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

from textus_kb.adapters.acai_entities import AcaiEntitiesAdapter, entity_to_packet_dict
from textus_kb.adapters.aquifer_bible_dictionary import AquiferBibleDictionaryAdapter
from textus_kb.adapters.aquifer_study_notes import AquiferStudyNotesAdapter
from textus_kb.adapters.lexicon import LexiconAdapter
from textus_kb.adapters.places import PlacesAdapter
from textus_kb.adapters.tagnt import TagntAdapter
from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.dictionary_relevance import (
    annotate_dictionary_scope_metadata,
    dictionary_relevance_score,
    is_direct_dictionary_relevant,
    passage_term_labels,
)
from textus_kb.entity_expansion import expand_dictionary_evidence
from textus_kb.entity_selection import entity_type_counts
from textus_kb.expansion_delta import ExpansionDelta, compute_expansion_delta
from textus_kb.evidence import (
    PILOT_BUILD_ID,
    PILOT_BUILD_ID_WITH_AQUIFER,
    PILOT_BUILD_ID_WITH_DICTIONARY,
    PILOT_BUILD_ID_WITH_ACAI,
    PILOT_BUILD_ID_WITH_ACAI_SQLITE,
    PILOT_BUILD_ID_PHASE4C,
    PILOT_BUILD_ID_PHASE4D,
    PILOT_BUILD_ID_PHASE4E,
    RELATION_DIRECT_PASSAGE,
    RELATION_DICTIONARY_BACKGROUND,
    RELATION_EXEGETICAL_NOTE,
    RELATION_LEXICAL_HIGHLIGHT,
    RELATION_PASSAGE_PLACE,
    RELATION_PASSAGE_TOKEN,
    RELATION_PLACE_CATALOG,
    RELATION_PLACE_ENRICHMENT,
    RELEVANCE_DIRECT_PASSAGE,
    RELEVANCE_EXEGETICAL_NOTE,
    RELEVANCE_LEXICAL_HIGHLIGHT,
    RELEVANCE_PASSAGE_PLACE,
    RELEVANCE_PLACE_CATALOG,
    RELEVANCE_PLACE_ENRICHMENT,
    EvidenceItem,
    EvidencePacket,
    LexicalHighlight,
    PassageTokenSummary,
    PlaceRecord,
    estimate_packet_tokens,
    estimate_supplemental_tokens,
    estimate_trimmable_supplemental_tokens,
)
from textus_kb.manifest import KnowledgeBaseManifest, ManifestSource, load_manifest
from textus_kb.pilot_registry import find_pilot

DEFAULT_MAX_EVIDENCE_TOKENS = 4500
DEFAULT_LEXICAL_HIGHLIGHT_LIMIT = 12

EntityRetrievalMode = Literal["direct_only", "direct_plus_entities"]

# Backward-compatible alias retained for tests referencing John 4 seed directly.
JOHN_4_LEXICAL_SEED = __import__(
    "textus_kb.pilot_registry", fromlist=["JOHN_4_PILOT"]
).JOHN_4_PILOT.lexical_seed


class RetrievalError(RuntimeError):
    """Raised when retrieval cannot complete for a required source."""


def retrieve(
    reference: str | CanonicalReference,
    *,
    manifest: KnowledgeBaseManifest | None = None,
    max_evidence_tokens: int = DEFAULT_MAX_EVIDENCE_TOKENS,
    lexical_highlight_limit: int = DEFAULT_LEXICAL_HIGHLIGHT_LIMIT,
    display_reference: str | None = None,
    entity_mode: EntityRetrievalMode = "direct_plus_entities",
) -> EvidencePacket:
    """Build a deterministic Evidence Packet from local Textus sources."""
    if isinstance(reference, CanonicalReference):
        canonical = reference
        display = display_reference or canonical.canonical_string()
    else:
        canonical = CanonicalReference.parse(reference)
        display = display_reference or reference.strip()

    manifest_obj = manifest or load_manifest()
    enabled_sources = {
        source.id: source
        for source in manifest_obj.sources
        if source.enabled
    }

    warnings: list[str] = []
    evidence_items: list[EvidenceItem] = []
    sources_used: dict[str, dict[str, str]] = {}
    places: list[PlaceRecord] = []
    historical_evidence: list[dict[str, Any]] = []
    linguistic_evidence: dict[str, Any] = {}

    canonical_passage = canonical.canonical_string()
    pilot = find_pilot(canonical)
    if pilot is None:
        warnings.append(
            "Passage is outside registered KB pilots; "
            "Study Notes, Dictionary, and ACAI pilot bundles will be skipped."
        )
        lexical_seed: tuple[str, ...] = ()
    else:
        lexical_seed = pilot.lexical_seed

    _add_source_record(sources_used, enabled_sources, "stepbible_tagnt")
    tagnt = _require_source(enabled_sources, "stepbible_tagnt")
    tagnt_adapter = TagntAdapter(tagnt)
    verse_tokens = tagnt_adapter.load_passage_tokens(canonical)
    token_count = sum(len(row.tokens) for row in verse_tokens)
    verse_summaries = tuple(
        PassageTokenSummary(
            verse=row.verse,
            token_count=len(row.tokens),
            tokens=row.tokens,
        ).to_dict()
        for row in verse_tokens
    )

    linguistic_evidence["passage_token_set"] = {
        "verse_count": len(verse_summaries),
        "token_count": token_count,
        "verses": list(verse_summaries),
    }
    linguistic_evidence["lexical_highlights"] = []

    evidence_items.append(
        EvidenceItem(
            evidence_id=_next_id("TAGNT", 1),
            source_id="stepbible_tagnt",
            source_type="sqlite",
            language="grc",
            relation_type=RELATION_PASSAGE_TOKEN,
            passage=canonical_passage,
            content=(
                f"Greek NT token set for {display}: "
                f"{len(verse_summaries)} verses, {token_count} tokens."
            ),
            metadata={
                "verse_count": len(verse_summaries),
                "token_count": token_count,
            },
            relevance_score=RELEVANCE_DIRECT_PASSAGE,
        )
    )
    evidence_items.append(
        EvidenceItem(
            evidence_id=_next_id("TAGNT", 2),
            source_id="stepbible_tagnt",
            source_type="sqlite",
            language="grc",
            relation_type=RELATION_DIRECT_PASSAGE,
            passage=canonical_passage,
            content=f"Direct passage match: {canonical_passage}",
            metadata={"display_reference": display},
            relevance_score=RELEVANCE_DIRECT_PASSAGE,
        )
    )

    tbesg_source = enabled_sources.get("stepbible_tbesg")
    hu_source = enabled_sources.get("lexicon_hu_overlay")
    if tbesg_source is None or not tbesg_source.enabled:
        warnings.append("Optional source stepbible_tbesg is disabled; English glosses omitted.")
    elif not tbesg_source.resolved_path.is_file():
        warnings.append("Optional source stepbible_tbesg file missing; English glosses omitted.")
    else:
        _add_source_record(sources_used, enabled_sources, "stepbible_tbesg")

    if hu_source is None or not hu_source.enabled:
        warnings.append("Optional source lexicon_hu_overlay is disabled; Hungarian glosses omitted.")
    elif not hu_source.resolved_path.is_file():
        warnings.append("Optional source lexicon_hu_overlay file missing; Hungarian glosses omitted.")
    else:
        _add_source_record(sources_used, enabled_sources, "lexicon_hu_overlay")

    lexicon_adapter = LexiconAdapter(
        tbesg_source=tbesg_source,
        hu_source=hu_source,
    )
    strong_counter = Counter(
        token["strong_id"]
        for row in verse_tokens
        for token in row.tokens
        if token.get("strong_id")
    )
    highlight_ids = _select_lexical_highlights(
        strong_counter,
        limit=lexical_highlight_limit,
        lexical_seed=lexical_seed,
    )
    lex_counter = 3
    for strong_id in highlight_ids:
        lookup = lexicon_adapter.lookup(strong_id)
        if lookup is None:
            continue
        for src in lookup.source_ids:
            _add_source_record(sources_used, enabled_sources, src)
        highlight = LexicalHighlight(
            strong_id=lookup.strong_id,
            lemma=lookup.lemma,
            token_count_in_passage=strong_counter.get(strong_id, 0),
            gloss_en=lookup.gloss_en,
            gloss_hu=lookup.gloss_hu,
            source_ids=lookup.source_ids,
        )
        linguistic_evidence["lexical_highlights"].append(highlight.to_dict())
        gloss_parts = []
        if lookup.gloss_en:
            gloss_parts.append(f"EN: {lookup.gloss_en}")
        if lookup.gloss_hu:
            gloss_parts.append(f"HU: {lookup.gloss_hu}")
        evidence_items.append(
            EvidenceItem(
                evidence_id=_next_id("LEX", lex_counter),
                source_id=lookup.source_ids[0],
                source_type=_source_type_for(manifest_obj, lookup.source_ids[0]),
                language="grc",
                relation_type=RELATION_LEXICAL_HIGHLIGHT,
                passage=canonical_passage,
                content=(
                    f"{lookup.lemma} ({lookup.strong_id}) — "
                    + ("; ".join(gloss_parts) if gloss_parts else "lexicon entry")
                ),
                metadata={
                    "strong_id": lookup.strong_id,
                    "token_count_in_passage": strong_counter.get(strong_id, 0),
                    "lexicon_source_ids": list(lookup.source_ids),
                },
                relevance_score=RELEVANCE_LEXICAL_HIGHLIGHT,
            )
        )
        lex_counter += 1

    catalog_source = enabled_sources.get("biblical_places_catalog")
    links_source = enabled_sources.get("biblical_places_passage_links")
    enrichment_source = enabled_sources.get("place_enrichments_overlay")

    if catalog_source is None or not catalog_source.enabled:
        warnings.append("Optional source biblical_places_catalog is disabled.")
    elif not catalog_source.resolved_path.is_file():
        warnings.append("Optional source biblical_places_catalog file missing.")
    else:
        _add_source_record(sources_used, enabled_sources, "biblical_places_catalog")

    if links_source is None or not links_source.enabled:
        warnings.append("Optional source biblical_places_passage_links is disabled.")
    elif not links_source.resolved_path.is_file():
        warnings.append("Optional source biblical_places_passage_links file missing.")
    else:
        _add_source_record(sources_used, enabled_sources, "biblical_places_passage_links")

    if enrichment_source is None or not enrichment_source.enabled:
        warnings.append("Optional source place_enrichments_overlay is disabled.")
    elif not enrichment_source.resolved_path.is_file():
        warnings.append("Optional source place_enrichments_overlay file missing.")
    else:
        _add_source_record(sources_used, enabled_sources, "place_enrichments_overlay")

    places_adapter = PlacesAdapter(
        catalog_source=catalog_source,
        links_source=links_source,
        enrichment_source=enrichment_source,
    )
    passage_links = places_adapter.find_passage_links(canonical)
    place_counter = 1
    for link in sorted(passage_links, key=lambda item: item.place_id):
        catalog = places_adapter.get_catalog_entry(link.place_id)
        if catalog is None:
            warnings.append(f"Passage link references unknown place_id: {link.place_id}")
            continue

        enrichment_excerpts = places_adapter.get_enrichment_excerpts(link.place_id)
        enrichment_text = None
        enrichment_confidence = None
        enrichment_source_ids: tuple[str, ...] = ()
        if enrichment_excerpts:
            enrichment_text = " ".join(
                excerpt.text_hu for excerpt in enrichment_excerpts[:2]
            )[:1200]
            enrichment_confidence = enrichment_excerpts[0].confidence
            enrichment_source_ids = enrichment_excerpts[0].source_ids

        place_record = PlaceRecord(
            place_id=catalog.place_id,
            name_hu=catalog.name_hu,
            name_en=catalog.name_en,
            latitude=catalog.latitude,
            longitude=catalog.longitude,
            passage_links=(link.normalized_reference,),
            source_id=PlacesAdapter.CATALOG_SOURCE_ID,
            identification_status=catalog.identification_status,
            card_summary_hu=catalog.card_summary_hu,
            enrichment_excerpt_hu=enrichment_text,
            enrichment_confidence=enrichment_confidence,
            enrichment_source_ids=enrichment_source_ids,
        )
        places.append(place_record)

        evidence_items.append(
            EvidenceItem(
                evidence_id=_next_id("PLACE", place_counter),
                source_id=PlacesAdapter.LINKS_SOURCE_ID,
                source_type="json",
                language="hu",
                relation_type=RELATION_PASSAGE_PLACE,
                passage=link.normalized_reference,
                content=(
                    f"{catalog.name_hu} ({catalog.place_id}) linked to passage "
                    f"via {link.normalized_reference}: {link.reason_hu}"
                ),
                metadata={
                    "place_id": catalog.place_id,
                    "source_note": link.source_note,
                    "latitude": catalog.latitude,
                    "longitude": catalog.longitude,
                },
                relevance_score=RELEVANCE_PASSAGE_PLACE,
            )
        )
        place_counter += 1

        if catalog.card_summary_hu:
            evidence_items.append(
                EvidenceItem(
                    evidence_id=_next_id("PLACE", place_counter),
                    source_id=PlacesAdapter.CATALOG_SOURCE_ID,
                    source_type="json",
                    language="hu",
                    relation_type=RELATION_PLACE_CATALOG,
                    passage=link.normalized_reference,
                    content=catalog.card_summary_hu,
                    metadata={
                        "place_id": catalog.place_id,
                        "identification_status": catalog.identification_status,
                    },
                    relevance_score=RELEVANCE_PLACE_CATALOG,
                )
            )
            place_counter += 1

        for excerpt in enrichment_excerpts:
            evidence_items.append(
                EvidenceItem(
                    evidence_id=_next_id("PLACE", place_counter),
                    source_id=PlacesAdapter.ENRICHMENT_SOURCE_ID,
                    source_type="json",
                    language="hu",
                    relation_type=RELATION_PLACE_ENRICHMENT,
                    passage=link.normalized_reference,
                    content=excerpt.text_hu,
                    metadata={
                        "place_id": catalog.place_id,
                        "section_key": excerpt.section_key,
                        "confidence": excerpt.confidence,
                        "review_status": excerpt.review_status,
                        "enrichment_source_ids": list(excerpt.source_ids),
                    },
                    relevance_score=RELEVANCE_PLACE_ENRICHMENT,
                )
            )
            place_counter += 1
            historical_evidence.append(
                {
                    "place_id": catalog.place_id,
                    "section_key": excerpt.section_key,
                    "text_hu": excerpt.text_hu,
                    "confidence": excerpt.confidence,
                    "source_id": PlacesAdapter.ENRICHMENT_SOURCE_ID,
                }
            )

    disabled_in_manifest = [
        source.id
        for source in manifest_obj.sources
        if not source.enabled and source.id == "ruf_2014_local"
    ]
    if disabled_in_manifest:
        warnings.append(
            "RUF local text source is disabled by manifest policy; packet excludes RUF prose."
        )

    aquifer_source = enabled_sources.get("aquifer_open_study_notes")
    aquifer_adapter = AquiferStudyNotesAdapter(aquifer_source)
    aquifer_counter = 1
    if aquifer_source is None or not aquifer_source.enabled:
        warnings.append("Optional source aquifer_open_study_notes is disabled.")
    elif not aquifer_adapter.store_available():
        warnings.append("Optional source aquifer_open_study_notes store missing.")
    elif not aquifer_adapter.passage_has_data(canonical):
        warnings.append("Optional source aquifer_open_study_notes: no data for this passage.")
    else:
        _add_source_record(sources_used, enabled_sources, "aquifer_open_study_notes")
        meta = aquifer_adapter.bundle_metadata(canonical)
        use_stable_ids = aquifer_adapter.backend == "sqlite"
        for chunk in aquifer_adapter.load_chunks_for_passage(canonical):
            content_plain = chunk.content_plain
            evidence_items.append(
                EvidenceItem(
                    evidence_id=_chunk_evidence_id(
                        "AQUIFER", chunk.chunk_id, fallback_index=aquifer_counter
                    )
                    if use_stable_ids
                    else _next_id("AQUIFER", aquifer_counter),
                    source_id=AquiferStudyNotesAdapter.SOURCE_ID,
                    source_type="exegetical_note",
                    language="en",
                    relation_type=RELATION_EXEGETICAL_NOTE,
                    passage=chunk.canonical_reference,
                    content=content_plain,
                    metadata={
                        "article_id": chunk.article_id,
                        "chunk_id": chunk.chunk_id,
                        "chunk_index": chunk.chunk_index,
                        "title": chunk.title,
                        "content_html": chunk.content_html,
                        "upstream_reference_usfm": chunk.upstream_reference_usfm,
                        "license": chunk.license,
                        "license_url": chunk.license_url,
                        "attribution": chunk.attribution,
                        "upstream_commit": meta.get("upstream_commit"),
                        "upstream_resource_version": meta.get("upstream_resource_version"),
                    },
                    relevance_score=_aquifer_relevance(
                        chunk.canonical_reference,
                        pilot_canonical=pilot.canonical if pilot is not None else None,
                    ),
                )
            )
            aquifer_counter += 1

    acai_source = enabled_sources.get("acai")
    acai_adapter = AcaiEntitiesAdapter(acai_source)
    passage_entity_views_early = (
        acai_adapter.entities_for_passage(canonical) if acai_adapter.available else []
    )
    passage_terms = passage_term_labels(passage_entity_views_early)
    if not passage_terms and pilot is not None:
        passage_terms = set(pilot.dictionary_index_refs) | {
            str(place_id).replace("_", " ") for place_id in pilot.dictionary_place_ids
        }

    dictionary_source = enabled_sources.get("aquifer_open_bible_dictionary")
    dictionary_adapter = AquiferBibleDictionaryAdapter(dictionary_source)
    dictionary_counter = 1
    direct_dictionary_count = 0
    direct_dictionary_dropped = 0
    dict_meta = dictionary_adapter.bundle_metadata(canonical)
    if dictionary_source is None or not dictionary_source.enabled:
        warnings.append("Optional source aquifer_open_bible_dictionary is disabled.")
    elif not dictionary_adapter.store_available():
        warnings.append("Optional source aquifer_open_bible_dictionary store missing.")
    elif not dictionary_adapter.passage_has_data(canonical):
        warnings.append("Optional source aquifer_open_bible_dictionary: no data for this passage.")
    else:
        _add_source_record(sources_used, enabled_sources, "aquifer_open_bible_dictionary")
        use_stable_dict_ids = dictionary_adapter.backend == "sqlite"
        for chunk in dictionary_adapter.load_chunks_for_passage(
            canonical,
            passage_terms=passage_terms,
        ):
            if not is_direct_dictionary_relevant(
                reference=canonical,
                title=chunk.title,
                index_reference=chunk.index_reference,
                passage_associations=chunk.passage_associations,
                passage_terms=passage_terms,
            ):
                direct_dictionary_dropped += 1
                continue
            metadata = {
                "article_id": chunk.article_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "title": chunk.title,
                "heading": chunk.heading,
                "index_reference": chunk.index_reference,
                "content_html": chunk.content_html,
                "selection_reason": chunk.selection_reason,
                "passage_associations": list(chunk.passage_associations),
                "entity_topics": list(chunk.entity_topics),
                "license": chunk.license,
                "license_url": chunk.license_url,
                "attribution": chunk.attribution,
                "upstream_commit": dict_meta.get("upstream_commit"),
                "upstream_resource_version": dict_meta.get("upstream_resource_version"),
                "relevance_reason": "passage_overlap_and_term_match",
            }
            annotate_dictionary_scope_metadata(
                metadata,
                reference=canonical,
                request_scope=canonical_passage,
            )
            evidence_items.append(
                EvidenceItem(
                    evidence_id=_chunk_evidence_id(
                        "DICT", chunk.chunk_id, fallback_index=dictionary_counter
                    )
                    if use_stable_dict_ids
                    else _next_id("DICT", dictionary_counter),
                    source_id=AquiferBibleDictionaryAdapter.SOURCE_ID,
                    source_type="bible_dictionary",
                    language="en",
                    relation_type=RELATION_DICTIONARY_BACKGROUND,
                    passage=metadata.get("source_scope"),
                    content=chunk.content_plain,
                    metadata=metadata,
                    relevance_score=dictionary_relevance_score(
                        reference=canonical,
                        title=chunk.title,
                        index_reference=chunk.index_reference,
                        passage_associations=chunk.passage_associations,
                        passage_terms=passage_terms,
                        selection_reason=chunk.selection_reason,
                    ),
                )
            )
            dictionary_counter += 1
            direct_dictionary_count += 1

    entity_records: list[dict[str, Any]] = []
    entity_expansion_debug: dict[str, Any] = {
        "entity_mode": entity_mode,
        "pilot_id": pilot.id if pilot is not None else None,
        "direct_dictionary_dropped_by_relevance": direct_dictionary_dropped,
    }
    expansion_delta = ExpansionDelta()
    if acai_source is None or not acai_source.enabled:
        warnings.append("Optional source acai is disabled.")
    elif not acai_adapter.available:
        warnings.append("Optional source acai entity store missing.")
    elif entity_mode == "direct_only":
        entity_expansion_debug["entity_expansion"] = {"skipped": True, "reason": "direct_only_mode"}
        expansion_delta = compute_expansion_delta(
            direct_evidence_items=evidence_items,
            expanded_items=[],
        )
    else:
        _add_source_record(sources_used, enabled_sources, "acai")
        dict_article_ids = frozenset(
            str(item.metadata.get("article_id") or "")
            for item in evidence_items
            if item.relation_type == RELATION_DICTIONARY_BACKGROUND and item.metadata.get("article_id")
        )
        passage_entity_views = passage_entity_views_early or acai_adapter.entities_for_passage(
            canonical
        )
        entity_views = acai_adapter.entities_for_evidence_packet(
            canonical,
            dictionary_article_ids=dict_article_ids,
        )
        entity_records = [entity_to_packet_dict(view) for view in entity_views]
        expanded_items: list[EvidenceItem] = []
        expansion_diag = None
        direct_items_before_expansion = list(evidence_items)
        if dictionary_adapter.available and acai_adapter.available:
            expanded_items, expansion_diag = expand_dictionary_evidence(
                reference=canonical,
                canonical_passage=canonical_passage,
                acai_adapter=acai_adapter,
                dictionary_adapter=dictionary_adapter,
                direct_evidence_items=evidence_items,
                dictionary_counter_start=dictionary_counter,
                dict_meta=dict_meta,
            )
            existing_chunk_ids = {
                str(item.metadata.get("chunk_id") or "")
                for item in evidence_items
                if item.metadata.get("chunk_id")
            }
            for item in expanded_items:
                chunk_id = str(item.metadata.get("chunk_id") or "")
                if chunk_id and chunk_id in existing_chunk_ids:
                    if expansion_diag is not None:
                        expansion_diag.dropped_by_limit += 1
                    continue
                evidence_items.append(item)
                if chunk_id:
                    existing_chunk_ids.add(chunk_id)
                dictionary_counter += 1
        expansion_delta = compute_expansion_delta(
            direct_evidence_items=direct_items_before_expansion,
            expanded_items=expanded_items,
        )
        entity_expansion_debug.update(
            {
                "entity_expansion": expansion_diag.to_dict() if expansion_diag is not None else {},
                "direct_dictionary_candidates": direct_dictionary_count,
                "acai_backend": acai_adapter.backend,
                "acai_import_mode": acai_adapter.import_mode,
                "passage_entity_count": len(passage_entity_views),
                "entity_types": entity_type_counts(entity_records),
                "entities_selected_for_packet": len(entity_records),
                "expansion_delta": expansion_delta.to_dict(),
            }
        )

    if entity_mode == "direct_only" and not entity_expansion_debug.get("expansion_delta"):
        entity_expansion_debug["expansion_delta"] = expansion_delta.to_dict()

    build_id = _resolve_build_id(
        aquifer_counter,
        dictionary_counter,
        len(entity_records),
        acai_backend=acai_adapter.backend if acai_adapter.available else "none",
        acai_import_mode=acai_adapter.import_mode if acai_adapter.available else "",
        aquifer_backend=aquifer_adapter.backend if aquifer_adapter.available else "none",
        dictionary_backend=dictionary_adapter.backend if dictionary_adapter.available else "none",
        pilot_id=pilot.id if pilot is not None else None,
        entity_mode=entity_mode,
    )

    packet = EvidencePacket(
        passage_canonical=canonical_passage,
        passage_display=display,
        build_id=build_id,
        manifest_version=manifest_obj.manifest_version,
        entities=entity_records,
        places=places,
        linguistic_evidence=linguistic_evidence,
        historical_evidence=historical_evidence,
        sources=sorted(sources_used.values(), key=lambda item: item["source_id"]),
        evidence_items=_sort_evidence_items(evidence_items),
        warnings=warnings,
        token_budget=max_evidence_tokens,
        retrieval_debug=entity_expansion_debug,
    )
    packet.estimated_tokens = estimate_packet_tokens(packet)
    packet.supplemental_tokens = estimate_supplemental_tokens(packet)
    packet = _apply_token_budget(
        packet,
        max_evidence_tokens,
        lexical_highlight_limit=lexical_highlight_limit,
    )
    packet.retrieval_debug = entity_expansion_debug
    return packet


def retrieve_to_json(
    reference: str | CanonicalReference,
    *,
    indent: int | None = 2,
    **kwargs: Any,
) -> str:
    packet = retrieve(reference, **kwargs)
    return json.dumps(packet.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)


def _require_source(sources: dict[str, ManifestSource], source_id: str) -> ManifestSource:
    source = sources.get(source_id)
    if source is None or not source.enabled:
        raise RetrievalError(f"Required source {source_id!r} is disabled or missing from manifest.")
    if not source.resolved_path.is_file():
        raise RetrievalError(
            f"Required source {source_id!r} file missing: {source.resolved_path}"
        )
    return source


def _add_source_record(
    bucket: dict[str, dict[str, str]],
    enabled_sources: dict[str, ManifestSource],
    source_id: str,
) -> None:
    source = enabled_sources.get(source_id)
    if source is None:
        return
    bucket[source_id] = {
        "source_id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "language": source.language,
        "version": source.version,
        "license": source.license,
        "local_path": source.local_path,
    }


def _source_type_for(manifest: KnowledgeBaseManifest, source_id: str) -> str:
    source = manifest.source_by_id(source_id)
    return source.source_type if source is not None else "unknown"


def _next_id(prefix: str, index: int) -> str:
    return f"EV-{prefix}-{index:04d}"


def _chunk_evidence_id(prefix: str, chunk_id: str, *, fallback_index: int) -> str:
    token = str(chunk_id or "").strip().replace(" ", "-")
    if token:
        return f"EV-{prefix}-{token}"
    return _next_id(prefix, fallback_index)


def _aquifer_relevance(canonical_reference: str, *, pilot_canonical: str | None = None) -> int:
    if pilot_canonical and canonical_reference == pilot_canonical:
        return RELEVANCE_EXEGETICAL_NOTE - 2
    if canonical_reference == "John.4.1-42":
        return RELEVANCE_EXEGETICAL_NOTE - 2
    if "-" not in canonical_reference:
        return RELEVANCE_EXEGETICAL_NOTE
    return RELEVANCE_EXEGETICAL_NOTE - 1


def _resolve_build_id(
    aquifer_counter: int,
    dictionary_counter: int,
    entity_count: int,
    *,
    acai_backend: str = "none",
    acai_import_mode: str = "",
    aquifer_backend: str = "none",
    dictionary_backend: str = "none",
    pilot_id: str | None = None,
    entity_mode: EntityRetrievalMode = "direct_plus_entities",
) -> str:
    if acai_backend == "sqlite" and acai_import_mode == "full":
        return PILOT_BUILD_ID_PHASE4E
    if aquifer_backend == "sqlite" or dictionary_backend == "sqlite":
        return PILOT_BUILD_ID_PHASE4D
    if pilot_id == "luke_10_25_37":
        return PILOT_BUILD_ID_PHASE4C
    if entity_count > 0 and acai_backend == "sqlite":
        return PILOT_BUILD_ID_WITH_ACAI_SQLITE
    if entity_count > 0:
        return PILOT_BUILD_ID_WITH_ACAI
    if dictionary_counter > 1:
        return PILOT_BUILD_ID_WITH_DICTIONARY
    if aquifer_counter > 1:
        return PILOT_BUILD_ID_WITH_AQUIFER
    return PILOT_BUILD_ID


def _sort_evidence_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return sorted(
        items,
        key=lambda item: (
            -item.relevance_score,
            item.relation_type,
            item.evidence_id,
        ),
    )


def _select_lexical_highlights(
    strong_counter: Counter[str],
    *,
    limit: int,
    lexical_seed: tuple[str, ...] = JOHN_4_LEXICAL_SEED,
) -> tuple[str, ...]:
    """Deterministic highlight selection: frequency, seed priority, then Strong ID."""
    if not strong_counter:
        return ()

    seed_rank = {strong_id: index for index, strong_id in enumerate(lexical_seed)}

    def sort_key(strong_id: str) -> tuple[int, int, str]:
        seed_priority = seed_rank.get(strong_id, len(lexical_seed) + 1)
        return (-strong_counter[strong_id], seed_priority, strong_id)

    ordered = sorted(strong_counter.keys(), key=sort_key)
    return tuple(ordered[:limit])


def _apply_token_budget(
    packet: EvidencePacket,
    max_tokens: int,
    *,
    lexical_highlight_limit: int,
) -> EvidencePacket:
    """Trim supplemental enrichment/highlights; never drop passage tokens, links, or Aquifer notes."""
    supplemental = estimate_supplemental_tokens(packet)
    trimmable = estimate_trimmable_supplemental_tokens(packet)
    if trimmable <= max_tokens:
        if supplemental > max_tokens and any(
            item.relation_type in {RELATION_EXEGETICAL_NOTE, RELATION_DICTIONARY_BACKGROUND}
            for item in packet.evidence_items
        ):
            warned = EvidencePacket(
                passage_canonical=packet.passage_canonical,
                passage_display=packet.passage_display,
                build_id=packet.build_id,
                manifest_version=packet.manifest_version,
                entities=list(packet.entities),
                places=list(packet.places),
                linguistic_evidence=dict(packet.linguistic_evidence),
                historical_evidence=list(packet.historical_evidence),
                sources=list(packet.sources),
                evidence_items=list(packet.evidence_items),
                warnings=list(packet.warnings),
                estimated_tokens=packet.estimated_tokens,
                supplemental_tokens=supplemental,
                token_budget=packet.token_budget,
            )
            warned.warnings.append(
                f"Supplemental token estimate ({supplemental}) exceeds budget ({max_tokens}); "
                "Aquifer exegetical notes and dictionary evidence retained for audit."
            )
            warned.token_budget_applied = True
            return warned
        return packet

    from dataclasses import replace

    warnings = list(packet.warnings)
    evidence_items = list(packet.evidence_items)
    places = list(packet.places)
    historical = list(packet.historical_evidence)
    linguistic = dict(packet.linguistic_evidence)

    enrichment_before = sum(
        1 for item in evidence_items if item.relation_type == RELATION_PLACE_ENRICHMENT
    )
    evidence_items = [
        item for item in evidence_items if item.relation_type != RELATION_PLACE_ENRICHMENT
    ]
    historical = []
    places = [
        replace(
            place,
            enrichment_excerpt_hu=None,
            enrichment_confidence=None,
            enrichment_source_ids=(),
        )
        for place in places
    ]

    trimmed = EvidencePacket(
        passage_canonical=packet.passage_canonical,
        passage_display=packet.passage_display,
        build_id=packet.build_id,
        manifest_version=packet.manifest_version,
        entities=list(packet.entities),
        places=places,
        linguistic_evidence=linguistic,
        historical_evidence=historical,
        sources=list(packet.sources),
        evidence_items=_sort_evidence_items(evidence_items),
        warnings=warnings,
        token_budget=packet.token_budget,
    )
    trimmed.estimated_tokens = estimate_packet_tokens(trimmed)

    highlight_limits = [
        limit
        for limit in (
            lexical_highlight_limit,
            max(lexical_highlight_limit // 2, 6),
            max(lexical_highlight_limit // 3, 4),
            0,
        )
        if limit <= lexical_highlight_limit
    ]
    seen_limits: list[int] = []
    for limit in highlight_limits:
        if limit in seen_limits:
            continue
        seen_limits.append(limit)
        candidate = _trim_lexical_highlights(trimmed, limit)
        if estimate_trimmable_supplemental_tokens(candidate) <= max_tokens:
            return _finalize_budget_trim(
                candidate,
                supplemental=supplemental,
                max_tokens=max_tokens,
                enrichment_before=enrichment_before,
                lexical_highlight_limit=lexical_highlight_limit,
                highlight_limit=limit,
            )

    catalog_trimmed = _trim_place_catalog_evidence(trimmed)
    if estimate_trimmable_supplemental_tokens(catalog_trimmed) <= max_tokens:
        return _finalize_budget_trim(
            catalog_trimmed,
            supplemental=supplemental,
            max_tokens=max_tokens,
            enrichment_before=enrichment_before,
            lexical_highlight_limit=lexical_highlight_limit,
            highlight_limit=0,
            dropped_catalog=True,
        )

    link_only = _trim_place_catalog_evidence(_trim_lexical_highlights(trimmed, 0))
    link_only = EvidencePacket(
        passage_canonical=link_only.passage_canonical,
        passage_display=link_only.passage_display,
        build_id=link_only.build_id,
        manifest_version=link_only.manifest_version,
        entities=list(link_only.entities),
        places=[
            replace(place, card_summary_hu=None)
            for place in link_only.places
        ],
        linguistic_evidence=dict(link_only.linguistic_evidence),
        historical_evidence=[],
        sources=list(link_only.sources),
        evidence_items=[
            item
            for item in link_only.evidence_items
            if item.relation_type
            in {
                RELATION_DIRECT_PASSAGE,
                RELATION_PASSAGE_TOKEN,
                RELATION_PASSAGE_PLACE,
                RELATION_EXEGETICAL_NOTE,
                RELATION_DICTIONARY_BACKGROUND,
            }
        ],
        warnings=list(link_only.warnings),
        token_budget=link_only.token_budget,
    )
    link_only.supplemental_tokens = estimate_supplemental_tokens(link_only)
    if link_only.supplemental_tokens > max_tokens:
        link_only = _truncate_supplemental_evidence_content(link_only, max_tokens)
    link_only.estimated_tokens = estimate_packet_tokens(link_only)
    link_only.token_budget_applied = True
    link_only.warnings.append(
        f"Supplemental token budget ({max_tokens}) exceeded at {supplemental}; "
        "kept passage tokens and minimal place links only."
    )
    return link_only


def _truncate_supplemental_evidence_content(
    packet: EvidencePacket,
    max_tokens: int,
) -> EvidencePacket:
    """Deterministically shorten supplemental evidence text until under budget."""
    char_limit = 240
    candidate = packet
    while char_limit >= 10:
        trimmed_items = []
        for item in candidate.evidence_items:
            if item.relation_type in {
                RELATION_DIRECT_PASSAGE,
                RELATION_PASSAGE_TOKEN,
            }:
                trimmed_items.append(item)
                continue
            content = item.content
            if len(content) > char_limit:
                content = content[:char_limit].rstrip() + "…"
            trimmed_items.append(
                EvidenceItem(
                    evidence_id=item.evidence_id,
                    source_id=item.source_id,
                    source_type=item.source_type,
                    language=item.language,
                    relation_type=item.relation_type,
                    passage=item.passage,
                    content=content,
                    metadata=dict(item.metadata),
                    relevance_score=item.relevance_score,
                )
            )
        candidate = EvidencePacket(
            passage_canonical=packet.passage_canonical,
            passage_display=packet.passage_display,
            build_id=packet.build_id,
            manifest_version=packet.manifest_version,
            entities=list(packet.entities),
            places=list(packet.places),
            linguistic_evidence=dict(packet.linguistic_evidence),
            historical_evidence=list(packet.historical_evidence),
            sources=list(packet.sources),
            evidence_items=_sort_evidence_items(trimmed_items),
            warnings=list(packet.warnings),
            token_budget=packet.token_budget,
        )
        candidate.supplemental_tokens = estimate_supplemental_tokens(candidate)
        if candidate.supplemental_tokens <= max_tokens:
            return candidate
        char_limit //= 2
    return candidate


def _finalize_budget_trim(
    packet: EvidencePacket,
    *,
    supplemental: int,
    max_tokens: int,
    enrichment_before: int,
    lexical_highlight_limit: int,
    highlight_limit: int,
    dropped_catalog: bool = False,
) -> EvidencePacket:
    packet.token_budget_applied = True
    packet.supplemental_tokens = estimate_supplemental_tokens(packet)
    packet.estimated_tokens = estimate_packet_tokens(packet)
    dropped_enrichment = enrichment_before
    dropped_highlights = max(0, lexical_highlight_limit - highlight_limit)
    parts = []
    if dropped_enrichment:
        parts.append(f"{dropped_enrichment} enrichment item(s)")
    if dropped_highlights > 0:
        parts.append(f"{dropped_highlights} lexical highlight(s)")
    if dropped_catalog:
        parts.append("place catalog summaries")
    detail = " and ".join(parts) if parts else "supplemental content"
    packet.warnings.append(
        f"Supplemental token budget ({max_tokens}) exceeded at {supplemental}; "
        f"trimmed {detail}. Passage Greek tokens are exempt from budget."
    )
    return packet


def _trim_place_catalog_evidence(packet: EvidencePacket) -> EvidencePacket:
    from dataclasses import replace

    evidence_items = [
        item
        for item in packet.evidence_items
        if item.relation_type != RELATION_PLACE_CATALOG
    ]
    places = [replace(place, card_summary_hu=None) for place in packet.places]
    return EvidencePacket(
        passage_canonical=packet.passage_canonical,
        passage_display=packet.passage_display,
        build_id=packet.build_id,
        manifest_version=packet.manifest_version,
        entities=list(packet.entities),
        places=places,
        linguistic_evidence=dict(packet.linguistic_evidence),
        historical_evidence=list(packet.historical_evidence),
        sources=list(packet.sources),
        evidence_items=_sort_evidence_items(evidence_items),
        warnings=list(packet.warnings),
        estimated_tokens=packet.estimated_tokens,
        supplemental_tokens=packet.supplemental_tokens,
        token_budget=packet.token_budget,
        token_budget_applied=packet.token_budget_applied,
    )


def _trim_lexical_highlights(packet: EvidencePacket, limit: int) -> EvidencePacket:
    linguistic = dict(packet.linguistic_evidence)
    highlights = list(linguistic.get("lexical_highlights", []))
    linguistic["lexical_highlights"] = highlights[:limit]

    kept_strong_ids = {
        str(item.get("strong_id"))
        for item in linguistic["lexical_highlights"]
        if item.get("strong_id")
    }
    evidence_items = [
        item
        for item in packet.evidence_items
        if item.relation_type != RELATION_LEXICAL_HIGHLIGHT
        or str(item.metadata.get("strong_id")) in kept_strong_ids
    ]
    return EvidencePacket(
        passage_canonical=packet.passage_canonical,
        passage_display=packet.passage_display,
        build_id=packet.build_id,
        manifest_version=packet.manifest_version,
        entities=list(packet.entities),
        places=list(packet.places),
        linguistic_evidence=linguistic,
        historical_evidence=list(packet.historical_evidence),
        sources=list(packet.sources),
        evidence_items=_sort_evidence_items(evidence_items),
        warnings=list(packet.warnings),
        estimated_tokens=packet.estimated_tokens,
        token_budget=packet.token_budget,
        token_budget_applied=packet.token_budget_applied,
    )


def _print_json(text: str) -> None:
    import sys

    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.write(b"\n")
        return
    print(text)


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m textus_kb retrieve <reference>", file=sys.stderr)
        return 2

    reference = " ".join(args).strip()
    try:
        output = retrieve_to_json(reference)
    except (CanonicalReferenceError, RetrievalError, FileNotFoundError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    _print_json(output)
    return 0


__all__ = [
    "DEFAULT_MAX_EVIDENCE_TOKENS",
    "RetrievalError",
    "main",
    "retrieve",
    "retrieve_to_json",
]
