"""Deterministic, source-aware selection of context items for LLM packets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.context_profiles import (
    BUDGET_BACKGROUND,
    BUDGET_DICTIONARY,
    BUDGET_ENTITY,
    BUDGET_EXEGETICAL,
    BUDGET_LINGUISTIC,
    BUDGET_PASSAGE,
    TIER_CORE,
    TIER_OPTIONAL,
    TIER_PRIMARY,
    TIER_RANK,
    TIER_SUPPORTING,
    ContextProfile,
)

# Prevent one dictionary article from consuming the entire dictionary budget.
MAX_DICTIONARY_CHUNKS_PER_ARTICLE = 2

# Jaccard threshold for near-duplicate plain text.
REDUNDANCY_JACCARD_THRESHOLD = 0.85

# Coverage segments for Jn 4-style single-chapter ranges (verse buckets).
DEFAULT_COVERAGE_SEGMENT_SIZE = 10


@dataclass
class SelectionCandidate:
    """Wrapper around a ContextItem with selection metadata."""

    item: Any  # ContextItem (avoid circular import at type level)
    tier: str
    budget_type: str
    specificity: int = 0
    verse_start: int | None = None
    verse_end: int | None = None
    selection_score: int = 0
    normalized_text: str = ""
    tokens: frozenset[str] = field(default_factory=frozenset)

    @property
    def estimated_tokens(self) -> int:
        return self.item.estimated_tokens()


@dataclass
class SelectionStats:
    candidates: int = 0
    selected: int = 0
    dropped_budget: int = 0
    dropped_redundant: int = 0
    dropped_type_budget: int = 0
    dropped_target: int = 0
    tokens_by_type: dict[str, int] = field(default_factory=dict)
    selected_by_tier: dict[str, int] = field(default_factory=dict)
    coverage_segments: list[dict[str, Any]] = field(default_factory=list)
    study_notes_candidates: int = 0
    study_notes_selected: int = 0
    dictionary_candidates: int = 0
    dictionary_selected: int = 0
    linguistic_selected: int = 0
    places_background_selected: int = 0
    aquifer_candidates: int = 0
    aquifer_selected: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "selected": self.selected,
            "dropped_budget": self.dropped_budget,
            "dropped_redundant": self.dropped_redundant,
            "dropped_type_budget": self.dropped_type_budget,
            "dropped_target": self.dropped_target,
            "tokens_by_type": dict(self.tokens_by_type),
            "selected_by_tier": dict(self.selected_by_tier),
            "coverage_segments": list(self.coverage_segments),
            "study_notes_candidates": self.study_notes_candidates,
            "study_notes_selected": self.study_notes_selected,
            "dictionary_candidates": self.dictionary_candidates,
            "dictionary_selected": self.dictionary_selected,
            "linguistic_selected": self.linguistic_selected,
            "places_background_selected": self.places_background_selected,
            "aquifer_candidates": self.aquifer_candidates,
            "aquifer_selected": self.aquifer_selected,
        }


def classify_item_type(item_type: str, profile: ContextProfile) -> str:
    return profile.item_tiers.get(item_type, TIER_OPTIONAL)


def budget_type_for_item(item_type: str) -> str:
    if item_type in {"passage", "passage_summary", "passage_scope"}:
        return BUDGET_PASSAGE
    if item_type in {"linguistic", "lexical"}:
        return BUDGET_LINGUISTIC
    if item_type == "exegetical_note":
        return BUDGET_EXEGETICAL
    if item_type == "dictionary_background":
        return BUDGET_DICTIONARY
    if item_type == "entity_summary":
        return BUDGET_ENTITY
    return BUDGET_BACKGROUND


def normalize_plain_text(text: str) -> str:
    lowered = text.casefold()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^\w\s]", "", lowered, flags=re.UNICODE)
    return lowered.strip()


def text_token_set(text: str) -> frozenset[str]:
    return frozenset(normalize_plain_text(text).split())


def jaccard_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0


def parse_canonical_verse_span(
    passage: str | None,
) -> tuple[int | None, int | None]:
    """Return (start_verse, end_verse) for a same-chapter canonical string."""
    if not passage:
        return None, None
    try:
        ref = CanonicalReference.parse(passage)
    except CanonicalReferenceError:
        return None, None
    if ref.start_chapter != ref.end_chapter:
        return ref.start_verse, ref.end_verse
    return ref.start_verse, ref.end_verse


def specificity_score(
    verse_start: int | None,
    verse_end: int | None,
    *,
    passage_start: int,
    passage_end: int,
) -> int:
    """Higher = more specific to a verse or short range within the passage."""
    if verse_start is None or verse_end is None:
        return 40
    span = max(0, verse_end - verse_start)
    covers_full = verse_start <= passage_start and verse_end >= passage_end
    if covers_full and span >= (passage_end - passage_start):
        return 20  # whole-chapter / full-passage overview
    if span == 0:
        return 100  # single verse
    if span <= 2:
        return 90
    if span <= 5:
        return 75
    if span <= 10:
        return 55
    return 35


def coverage_segment_index(verse: int, passage_start: int, segment_size: int) -> int:
    return max(0, (verse - passage_start) // segment_size)


def build_coverage_segments(
    passage_start: int,
    passage_end: int,
    *,
    segment_size: int = DEFAULT_COVERAGE_SEGMENT_SIZE,
) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    cursor = passage_start
    while cursor <= passage_end:
        end = min(cursor + segment_size - 1, passage_end)
        segments.append((cursor, end))
        cursor = end + 1
    return segments


def prepare_candidates(
    items: list[Any],
    profile: ContextProfile,
    *,
    passage_canonical: str,
) -> list[SelectionCandidate]:
    try:
        passage_ref = CanonicalReference.parse(passage_canonical)
        p_start, p_end = passage_ref.start_verse, passage_ref.end_verse
    except CanonicalReferenceError:
        p_start, p_end = 1, 42

    prepared: list[SelectionCandidate] = []
    for item in items:
        verse_start, verse_end = parse_canonical_verse_span(
            item.metadata.get("canonical_scope") or item.metadata.get("passage")
            if isinstance(item.metadata, dict)
            else None
        )
        # Fall back: exegetical notes store passage on the item itself via builder.
        if verse_start is None and hasattr(item, "metadata"):
            # Try to recover from text title pattern "John 4:10" is not needed;
            # builder should set metadata.canonical_scope — see context_builder.
            scope = item.metadata.get("canonical_scope")
            if scope:
                verse_start, verse_end = parse_canonical_verse_span(str(scope))

        specificity = 50
        if item.item_type == "exegetical_note":
            specificity = specificity_score(
                verse_start,
                verse_end,
                passage_start=p_start,
                passage_end=p_end,
            )
        elif item.item_type in {"linguistic", "lexical"}:
            verse = item.metadata.get("verse")
            if isinstance(verse, int):
                verse_start = verse_end = verse
                specificity = 95
        elif item.item_type == "dictionary_background":
            if item.metadata.get("passage_associations"):
                specificity = 95
            elif item.metadata.get("entity_expansion"):
                if profile.name == "historical_context":
                    specificity = 88
                else:
                    specificity = 55
            elif item.metadata.get("entity_topics"):
                specificity = 85
            else:
                specificity = 65

        tier = classify_item_type(item.item_type, profile)
        # Whole-passage Aquifer overview is optional; verse-specific notes stay primary.
        if item.item_type == "exegetical_note":
            if specificity <= 25:
                tier = TIER_OPTIONAL
            elif specificity >= 75:
                tier = TIER_PRIMARY
            else:
                tier = TIER_SUPPORTING

        norm = normalize_plain_text(item.text)
        tokens = text_token_set(item.text)
        selection_score = (
            item.relevance_score * 10
            + specificity
            + (100 - TIER_RANK.get(tier, 3) * 20)
        )
        prepared.append(
            SelectionCandidate(
                item=item,
                tier=tier,
                budget_type=budget_type_for_item(item.item_type),
                specificity=specificity,
                verse_start=verse_start,
                verse_end=verse_end,
                selection_score=selection_score,
                normalized_text=norm,
                tokens=tokens,
            )
        )
    return prepared


def select_context_items(
    items: list[Any],
    profile: ContextProfile,
    *,
    passage_canonical: str,
) -> tuple[list[Any], SelectionStats]:
    """Select a diverse, non-redundant subset of context items under budgets."""
    stats = SelectionStats(candidates=len(items))
    if not items:
        return [], stats

    try:
        passage_ref = CanonicalReference.parse(passage_canonical)
        p_start, p_end = passage_ref.start_verse, passage_ref.end_verse
    except CanonicalReferenceError:
        p_start, p_end = 1, 42

    candidates = prepare_candidates(items, profile, passage_canonical=passage_canonical)
    stats.study_notes_candidates = sum(
        1 for c in candidates if c.item.item_type == "exegetical_note"
    )
    stats.dictionary_candidates = sum(
        1 for c in candidates if c.item.item_type == "dictionary_background"
    )
    stats.aquifer_candidates = stats.study_notes_candidates

    # --- Redundancy pass (deterministic order) ---
    candidates.sort(
        key=lambda c: (
            TIER_RANK.get(c.tier, 9),
            -c.selection_score,
            c.item.item_type,
            c.item.evidence_id,
        )
    )
    kept_after_dedup: list[SelectionCandidate] = []
    seen_keys: set[str] = set()
    seen_norms: list[tuple[str, frozenset[str]]] = []

    for cand in candidates:
        dedup_key = _dedup_key(cand)
        if dedup_key in seen_keys:
            stats.dropped_redundant += 1
            continue
        redundant = False
        for prev_norm, prev_tokens in seen_norms:
            if cand.normalized_text and cand.normalized_text == prev_norm:
                redundant = True
                break
            if (
                cand.tokens
                and prev_tokens
                and jaccard_similarity(cand.tokens, prev_tokens)
                >= REDUNDANCY_JACCARD_THRESHOLD
            ):
                redundant = True
                break
        if redundant:
            stats.dropped_redundant += 1
            continue
        seen_keys.add(dedup_key)
        seen_norms.append((cand.normalized_text, cand.tokens))
        kept_after_dedup.append(cand)

    # --- Coverage-aware exegetical reservation ---
    segments = build_coverage_segments(p_start, p_end)
    segment_hits: dict[int, list[SelectionCandidate]] = {i: [] for i in range(len(segments))}
    exegetical = [
        c for c in kept_after_dedup if c.item.item_type == "exegetical_note"
    ]
    for cand in exegetical:
        for idx, (seg_start, seg_end) in enumerate(segments):
            if cand.verse_start is None or cand.verse_end is None:
                continue
            if cand.verse_end < seg_start or cand.verse_start > seg_end:
                continue
            # Prefer notes that don't span the entire passage for coverage.
            if cand.specificity <= 25:
                continue
            segment_hits[idx].append(cand)

    coverage_picks: list[SelectionCandidate] = []
    coverage_seen: set[str] = set()
    for idx, hits in segment_hits.items():
        if not hits:
            continue
        hits_sorted = sorted(
            hits,
            key=lambda c: (-c.specificity, -c.selection_score, c.item.evidence_id),
        )
        pick = hits_sorted[0]
        if pick.item.evidence_id not in coverage_seen:
            coverage_picks.append(pick)
            coverage_seen.add(pick.item.evidence_id)

    # --- Main selection with type budgets, diversity, target ---
    type_caps = dict(profile.type_budgets)
    type_used: dict[str, int] = {key: 0 for key in type_caps}
    total_tokens = 0
    selected: list[SelectionCandidate] = []
    selected_ids: set[str] = set()

    def try_add(cand: SelectionCandidate, *, force_diversity: bool = False) -> bool:
        nonlocal total_tokens
        if cand.item.evidence_id in selected_ids:
            return False
        cost = cand.estimated_tokens
        budget_type = cand.budget_type
        type_cap = type_caps.get(budget_type, profile.max_tokens)
        if type_used.get(budget_type, 0) + cost > type_cap and not force_diversity:
            return False
        # Soft target: do not add non-core once the next item would exceed target.
        if (
            selected
            and cand.tier != TIER_CORE
            and not force_diversity
            and total_tokens + cost > profile.target_tokens
        ):
            return False
        if total_tokens + cost > profile.max_tokens:
            return False
        selected.append(cand)
        selected_ids.add(cand.item.evidence_id)
        total_tokens += cost
        type_used[budget_type] = type_used.get(budget_type, 0) + cost
        return True

    # 1) Always take core first.
    for cand in kept_after_dedup:
        if cand.tier == TIER_CORE:
            if not try_add(cand):
                if total_tokens + cand.estimated_tokens > profile.max_tokens:
                    stats.dropped_budget += 1
                elif type_used.get(cand.budget_type, 0) + cand.estimated_tokens > type_caps.get(
                    cand.budget_type, profile.max_tokens
                ):
                    stats.dropped_type_budget += 1
                else:
                    stats.dropped_target += 1

    # 2) Coverage picks for exegetical notes (one per segment, within type budget).
    for cand in coverage_picks:
        if not try_add(cand):
            cost = cand.estimated_tokens
            # Allow one coverage note even if type budget is tight, never past hard max.
            type_cap = type_caps.get(cand.budget_type, profile.max_tokens)
            over_type = type_used.get(cand.budget_type, 0) + cost > type_cap
            if (
                cand.item.evidence_id not in selected_ids
                and total_tokens + cost <= profile.max_tokens
                and total_tokens + cost <= profile.target_tokens
                and (not over_type or type_used.get(cand.budget_type, 0) < type_cap * 0.5)
            ):
                selected.append(cand)
                selected_ids.add(cand.item.evidence_id)
                total_tokens += cost
                type_used[cand.budget_type] = type_used.get(cand.budget_type, 0) + cost
            else:
                stats.dropped_type_budget += 1

    # 3) Diversity reservation: ensure at least one item per required type if available.
    for budget_type in profile.diversity_types:
        if any(c.budget_type == budget_type for c in selected):
            continue
        pool = [
            c
            for c in kept_after_dedup
            if c.budget_type == budget_type and c.item.evidence_id not in selected_ids
        ]
        if not pool:
            continue
        pool.sort(key=lambda c: (-c.selection_score, c.item.evidence_id))
        try_add(pool[0], force_diversity=True)

    # 4) Fill remaining by tier then score until target.
    remaining = [
        c for c in kept_after_dedup if c.item.evidence_id not in selected_ids
    ]
    dictionary_article_counts: dict[str, int] = {}
    for cand in selected:
        if cand.item.item_type == "dictionary_background":
            article_id = str(cand.item.metadata.get("article_id") or "")
            if article_id:
                dictionary_article_counts[article_id] = dictionary_article_counts.get(article_id, 0) + 1

    remaining.sort(
        key=lambda c: (
            TIER_RANK.get(c.tier, 9),
            -c.specificity if c.item.item_type == "exegetical_note" else 0,
            -c.specificity if c.item.item_type == "dictionary_background" else 0,
            -c.selection_score,
            c.item.evidence_id,
        )
    )
    for cand in remaining:
        if cand.item.item_type == "dictionary_background":
            article_id = str(cand.item.metadata.get("article_id") or "")
            if article_id and dictionary_article_counts.get(article_id, 0) >= MAX_DICTIONARY_CHUNKS_PER_ARTICLE:
                stats.dropped_type_budget += 1
                continue
        if total_tokens >= profile.target_tokens:
            # After target, only add core-equivalent leftovers that fit hard max.
            if cand.tier != TIER_CORE:
                stats.dropped_target += 1
                continue
        if try_add(cand):
            if cand.item.item_type == "dictionary_background":
                article_id = str(cand.item.metadata.get("article_id") or "")
                if article_id:
                    dictionary_article_counts[article_id] = dictionary_article_counts.get(article_id, 0) + 1
            continue
        cost = cand.estimated_tokens
        if total_tokens + cost > profile.max_tokens:
            stats.dropped_budget += 1
        elif type_used.get(cand.budget_type, 0) + cost > type_caps.get(
            cand.budget_type, profile.max_tokens
        ):
            stats.dropped_type_budget += 1
        else:
            stats.dropped_target += 1

    # Stable output order: score then evidence id (sections regroup later).
    selected.sort(
        key=lambda c: (-c.selection_score, c.item.item_type, c.item.evidence_id)
    )

    # Attach classification onto selected items via metadata copy.
    # Re-estimate after enrichment; drop trailing items if hard max exceeded.
    from textus_kb.context_builder import ContextItem

    result_items: list[Any] = []
    running = 0
    for cand in selected:
        meta = dict(cand.item.metadata)
        meta["selection_tier"] = cand.tier
        meta["selection_specificity"] = cand.specificity
        meta["budget_type"] = cand.budget_type
        if cand.verse_start is not None:
            meta["canonical_scope"] = meta.get("canonical_scope") or (
                f"v{cand.verse_start}"
                if cand.verse_end == cand.verse_start
                else f"v{cand.verse_start}-{cand.verse_end}"
            )
        enriched = ContextItem(
            text=cand.item.text,
            evidence_id=cand.item.evidence_id,
            source_id=cand.item.source_id,
            relevance_score=cand.item.relevance_score,
            item_type=cand.item.item_type,
            metadata=meta,
        )
        cost = enriched.estimated_tokens()
        if result_items and running + cost > profile.max_tokens:
            stats.dropped_budget += 1
            continue
        # Soft target applies after metadata enrichment for non-core items.
        if (
            result_items
            and cand.tier != TIER_CORE
            and running + cost > profile.target_tokens
        ):
            stats.dropped_target += 1
            continue
        if not result_items and cost > profile.max_tokens:
            # Keep a truncated core slice so tiny budgets still produce output.
            char_limit = max(40, profile.max_tokens * 4)
            text = enriched.text
            if len(text) > char_limit:
                text = text[:char_limit].rstrip() + "…"
            enriched = ContextItem(
                text=text,
                evidence_id=enriched.evidence_id,
                source_id=enriched.source_id,
                relevance_score=enriched.relevance_score,
                item_type=enriched.item_type,
                metadata=dict(enriched.metadata),
            )
            cost = enriched.estimated_tokens()
            stats.dropped_budget += 1
        result_items.append(enriched)
        running += cost

    stats.selected = len(result_items)
    stats.study_notes_selected = sum(
        1 for item in result_items if item.item_type == "exegetical_note"
    )
    stats.dictionary_selected = sum(
        1 for item in result_items if item.item_type == "dictionary_background"
    )
    stats.linguistic_selected = sum(
        1 for item in result_items if item.item_type in {"linguistic", "lexical"}
    )
    stats.places_background_selected = sum(
        1
        for item in result_items
        if item.item_type
        in {
            "place_link",
            "passage_place_link",
            "place_catalog",
            "geography",
            "enrichment",
            "historical_enrichment",
        }
    )
    stats.aquifer_selected = stats.study_notes_selected
    stats.tokens_by_type = {}
    stats.selected_by_tier = {}
    for item in result_items:
        bt = str(item.metadata.get("budget_type") or budget_type_for_item(item.item_type))
        stats.tokens_by_type[bt] = stats.tokens_by_type.get(bt, 0) + item.estimated_tokens()
        tier = str(item.metadata.get("selection_tier") or TIER_OPTIONAL)
        stats.selected_by_tier[tier] = stats.selected_by_tier.get(tier, 0) + 1

    # Refresh coverage against final selection.
    stats.coverage_segments = []
    selected_exegetical = [
        item for item in result_items if item.item_type == "exegetical_note"
    ]
    for seg_start, seg_end in segments:
        note_count = 0
        covered = False
        for item in selected_exegetical:
            scope = str(item.metadata.get("canonical_scope") or "")
            v_start, v_end = parse_canonical_verse_span(scope)
            if v_start is None:
                continue
            if v_end is None:
                v_end = v_start
            if v_end < seg_start or v_start > seg_end:
                continue
            note_count += 1
            specificity = int(item.metadata.get("selection_specificity") or 0)
            if specificity > 25:
                covered = True
        stats.coverage_segments.append(
            {
                "segment": f"{seg_start}-{seg_end}",
                "covered": covered,
                "note_count": note_count,
            }
        )

    return result_items, stats


def _dedup_key(cand: SelectionCandidate) -> str:
    meta = cand.item.metadata or {}
    article_id = meta.get("article_id")
    chunk_id = meta.get("chunk_id")
    if article_id and chunk_id:
        prefix = "dict" if cand.item.item_type == "dictionary_background" else "aquifer"
        return f"{prefix}:{article_id}:{chunk_id}"
    if article_id:
        return f"aquifer:{article_id}"
    place_id = meta.get("place_id")
    if place_id and cand.item.item_type in {"place_link", "passage_place_link", "geography"}:
        return f"place:{cand.item.item_type}:{place_id}"
    return f"id:{cand.item.evidence_id}"
