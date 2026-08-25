"""Phase 5H-C: historical_context source selection + grounding policy."""

from __future__ import annotations

from textus_kb.context_builder import ContextItem, build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL, ContextProfile
from textus_kb.context_selection import (
    MAX_HISTORICAL_DICTIONARY_CHUNKS_PER_ARTICLE,
    select_context_items,
)
from textus_kb.evidence import (
    RELATION_DICTIONARY_BACKGROUND,
    RELATION_LEXICAL_HIGHLIGHT,
    RELATION_PASSAGE_PLACE,
    RELATION_PLACE_ENRICHMENT,
    EvidenceItem,
    EvidencePacket,
)
from textus_kb.retrieval import retrieve


def _packet_with_mixed_historical_candidates() -> EvidencePacket:
    evidence_items = [
        EvidenceItem(
            evidence_id="EV-PASS-1",
            source_id="stepbible_tagnt",
            source_type="morphology",
            language="grc",
            relation_type="direct_passage_match",
            passage="John.4.1-42",
            content="passage",
            metadata={},
            relevance_score=100,
        ),
        EvidenceItem(
            evidence_id="EV-LING-1",
            source_id="stepbible_tagnt",
            source_type="morphology",
            language="grc",
            relation_type=RELATION_LEXICAL_HIGHLIGHT,
            passage="John.4.1-42",
            content="Generic linguistic filler about Greek morphology that should not dominate historical context.",
            metadata={"strong_id": "G5204", "verse": 7},
            relevance_score=90,
        ),
        EvidenceItem(
            evidence_id="EV-ENR-1",
            source_id="place_enrichments_overlay",
            source_type="json",
            language="hu",
            relation_type=RELATION_PLACE_ENRICHMENT,
            passage="John.4.1-42",
            content="Sychar historical enrichment: Samaria route context and first-century village setting.",
            metadata={"place_id": "sychar", "section_key": "historical_context", "confidence": 0.8},
            relevance_score=90,
        ),
        EvidenceItem(
            evidence_id="EV-PLACE-1",
            source_id="biblical_places_passage_links",
            source_type="json",
            language="hu",
            relation_type=RELATION_PASSAGE_PLACE,
            passage="Jn 4,5",
            content="Sikár (sychar) linked to passage via Jn 4,5.",
            metadata={"place_id": "sychar"},
            relevance_score=95,
        ),
        EvidenceItem(
            evidence_id="EV-DICT-1",
            source_id="aquifer_open_bible_dictionary",
            source_type="bible_dictionary",
            language="en",
            relation_type=RELATION_DICTIONARY_BACKGROUND,
            passage="John.4.5",
            content="Sychar dictionary article content for historical background.",
            metadata={
                "article_id": "8676",
                "chunk_id": "8676-c001",
                "chunk_index": 1,
                "title": "Sychar",
                "selection_reason": "direct_passage_association",
                "passage_associations": [
                    {"start_ref": "43004005", "end_ref": "43004005"}
                ],
                "overlapping_passage_associations": [
                    {"start_ref": "43004005", "end_ref": "43004005"}
                ],
                "source_scope": "John.4.5",
                "request_scope": "John.4.1-42",
                "passage_linked": True,
            },
            relevance_score=88,
        ),
        EvidenceItem(
            evidence_id="EV-DICT-2",
            source_id="aquifer_open_bible_dictionary",
            source_type="bible_dictionary",
            language="en",
            relation_type=RELATION_DICTIONARY_BACKGROUND,
            passage="John.4.5",
            content="Sychar second chunk — redundant same-article padding.",
            metadata={
                "article_id": "8676",
                "chunk_id": "8676-c002",
                "chunk_index": 2,
                "title": "Sychar",
                "selection_reason": "direct_passage_association",
                "passage_associations": [
                    {"start_ref": "43004005", "end_ref": "43004005"}
                ],
                "overlapping_passage_associations": [
                    {"start_ref": "43004005", "end_ref": "43004005"}
                ],
                "source_scope": "John.4.5",
                "request_scope": "John.4.1-42",
                "passage_linked": True,
            },
            relevance_score=88,
        ),
    ]
    return EvidencePacket(
        passage_canonical="John.4.1-42",
        passage_display="John.4.1-42",
        build_id="phase5h-c-test",
        manifest_version="test",
        entities=[
            {
                "entity_id": "acai-deity-Lord",
                "canonical_name": "LORD",
                "entity_type": "deity",
                "external_ids": {"acai": "deity:Lord"},
                "passage_relations": [{"ref": "John.4.1"}],
                "dictionary_relations": [],
            },
            {
                "entity_id": "acai-keyterm-Always",
                "canonical_name": "Always",
                "entity_type": "keyterm",
                "external_ids": {"acai": "keyterm:Always"},
                "passage_relations": [{"ref": "John.4.1"}],
                "dictionary_relations": [],
            },
            {
                "entity_id": "acai-group-Samaritans",
                "canonical_name": "Samaritans",
                "entity_type": "group",
                "external_ids": {"acai": "group:Samaritans"},
                "passage_relations": [{"ref": "John.4.9"}],
                "dictionary_relations": [],
            },
        ],
        places=[],
        linguistic_evidence={},
        historical_evidence=[],
        sources=[],
        evidence_items=evidence_items,
        warnings=[],
        token_budget=8000,
    )


def test_historical_prioritizes_enrichment_over_generic_linguistic() -> None:
    packet = _packet_with_mixed_historical_candidates()
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    selected_types = {
        item.item_type
        for section in historical.sections
        for item in section.items
    }
    assert "historical_enrichment" in selected_types
    assert "linguistic" not in selected_types
    assert "lexical" not in selected_types
    assert historical.selection_stats["linguistic_selected"] == 0


def test_place_background_not_crowded_out_by_generic_dictionary() -> None:
    packet = _packet_with_mixed_historical_candidates()
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert historical.selection_stats["historical_background_selected"] >= 1
    assert historical.selection_stats["historical_coverage_status"] == "ok"
    selected_types = {
        item.item_type
        for section in historical.sections
        for item in section.items
    }
    assert "passage_place_link" in selected_types or "historical_enrichment" in selected_types


def test_generic_acai_deity_keyterm_not_historical_grounding() -> None:
    packet = _packet_with_mixed_historical_candidates()
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    entity_texts = [
        item.text
        for section in historical.sections
        for item in section.items
        if item.item_type == "entity_summary"
    ]
    assert all("LORD" not in text for text in entity_texts)
    assert all("Always" not in text for text in entity_texts)
    assert any("Samaritans" in text for text in entity_texts)


def test_historical_coverage_limited_when_no_background_available() -> None:
    packet = retrieve("Rom.8.28-30")
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert historical.selection_stats["historical_background_candidates"] == 0
    assert historical.selection_stats["historical_coverage_status"] == "limited"
    assert any("Historical coverage limited" in warning for warning in historical.warnings)
    # Fail-safe: do not invent place/enrichment rows.
    selected_types = {
        item.item_type
        for section in historical.sections
        for item in section.items
    }
    assert "historical_enrichment" not in selected_types
    assert "passage_place_link" not in selected_types


def test_available_historical_evidence_meets_coverage_requirement() -> None:
    packet = retrieve("John.4.1-42")
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert historical.selection_stats["historical_background_candidates"] > 0
    assert historical.selection_stats["historical_background_selected"] >= 1
    assert historical.selection_stats["historical_coverage_status"] == "ok"


def test_redundant_same_article_dictionary_dedup_in_historical() -> None:
    packet = _packet_with_mixed_historical_candidates()
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    article_ids = [
        item.metadata.get("article_id")
        for section in historical.sections
        for item in section.items
        if item.item_type == "dictionary_background"
    ]
    assert article_ids.count("8676") <= MAX_HISTORICAL_DICTIONARY_CHUNKS_PER_ARTICLE
    # Live Phase 5G-style check: no Baptism×2.
    live = build_context_from_evidence(retrieve("John.4.1-42"), PROFILE_HISTORICAL)
    live_articles = [
        item.metadata.get("article_id")
        for section in live.sections
        for item in section.items
        if item.item_type == "dictionary_background" and item.metadata.get("article_id")
    ]
    assert all(live_articles.count(article_id) <= 1 for article_id in set(live_articles))


def test_duplicate_place_enrichment_dedup() -> None:
    items = [
        ContextItem(
            text="Jerusalem enrichment duplicate A",
            evidence_id="EV-ENR-A",
            source_id="place_enrichments_overlay",
            relevance_score=100,
            item_type="historical_enrichment",
            metadata={"place_id": "jerusalem", "section_key": "biblical_significance"},
        ),
        ContextItem(
            text="Jerusalem enrichment duplicate B same section",
            evidence_id="EV-ENR-B",
            source_id="place_enrichments_overlay",
            relevance_score=99,
            item_type="historical_enrichment",
            metadata={"place_id": "jerusalem", "section_key": "biblical_significance"},
        ),
        ContextItem(
            text="Jerusalem enrichment different section kept",
            evidence_id="EV-ENR-C",
            source_id="place_enrichments_overlay",
            relevance_score=98,
            item_type="historical_enrichment",
            metadata={"place_id": "jerusalem", "section_key": "key_events"},
        ),
    ]
    profile = ContextProfile.load(PROFILE_HISTORICAL)
    selected, stats = select_context_items(
        items, profile, passage_canonical="Luke.10.25-37"
    )
    section_keys = [
        (item.metadata.get("place_id"), item.metadata.get("section_key"))
        for item in selected
        if item.item_type == "historical_enrichment"
    ]
    assert ("jerusalem", "biblical_significance") in section_keys
    assert ("jerusalem", "key_events") in section_keys
    assert section_keys.count(("jerusalem", "biblical_significance")) == 1
    assert stats.dropped_redundant >= 1


def test_exegesis_selection_unchanged_shape() -> None:
    packet = retrieve("John.4.1-42")
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    section_types = {section.type for section in exegesis.sections}
    assert "linguistic" in section_types or "exegetical" in section_types
    assert exegesis.estimated_tokens <= 4500
    # Historical-only coverage fields should not force exegesis behavior.
    assert exegesis.selection_stats.get("historical_coverage_status") in {"", None}


def test_phase5h_b_dictionary_relevance_not_regressed() -> None:
    packet = retrieve("John.4.1-42")
    titles = {
        str(item.metadata.get("title") or "")
        for item in packet.evidence_items
        if item.source_type == "bible_dictionary"
    }
    assert "Abba" not in titles
    assert "Aegean Sea" not in titles
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    selected_blob = " ".join(
        item.text for section in historical.sections for item in section.items
    )
    assert "Abba" not in selected_blob
    assert "Aegean Sea" not in selected_blob


def test_historical_token_max_still_respected() -> None:
    packet = retrieve("Acts.2.1-13")
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert historical.estimated_tokens <= 3500
    assert historical.max_tokens == 3500
