"""Context profile definitions, budgets, and selection priorities."""

from __future__ import annotations

from dataclasses import dataclass, field

from textus_kb.evidence import (
    RELATION_COMMENTARY_SOURCE,
    RELATION_DIRECT_PASSAGE,
    RELATION_DICTIONARY_BACKGROUND,
    RELATION_EXEGETICAL_NOTE,
    RELATION_LEXICAL_HIGHLIGHT,
    RELATION_PASSAGE_PLACE,
    RELATION_PASSAGE_TOKEN,
    RELATION_PLACE_CATALOG,
    RELATION_PLACE_ENRICHMENT,
    RELATION_THEOLOGICAL_SOURCE,
)

PROFILE_EXEGESIS = "exegesis"
PROFILE_HISTORICAL = "historical_context"
PROFILE_THEOLOGY = "theology"
PROFILE_COMMENTARY = "commentary"

SUPPORTED_PROFILES = frozenset(
    {PROFILE_EXEGESIS, PROFILE_HISTORICAL, PROFILE_THEOLOGY, PROFILE_COMMENTARY}
)

TIER_CORE = "core"
TIER_PRIMARY = "primary"
TIER_SUPPORTING = "supporting"
TIER_OPTIONAL = "optional"

TIER_RANK = {
    TIER_CORE: 0,
    TIER_PRIMARY: 1,
    TIER_SUPPORTING: 2,
    TIER_OPTIONAL: 3,
}

BUDGET_LINGUISTIC = "linguistic"
BUDGET_EXEGETICAL = "exegetical"
BUDGET_DICTIONARY = "dictionary"
BUDGET_ENTITY = "entity"
BUDGET_BACKGROUND = "background"
BUDGET_PASSAGE = "passage"
BUDGET_THEOLOGY = "theology"
BUDGET_COMMENTARY = "commentary"

THEOLOGY_SOURCE_WARNING = "No dedicated theological source layer available"
THEOLOGY_NO_MATCH_WARNING = (
    "Theological source store is available, but no passage-linked "
    "theological evidence was found for this reference."
)
THEOLOGY_EVIDENCE_LIMIT = 6

COMMENTARY_SOURCE_WARNING = "No dedicated commentary source layer available"
COMMENTARY_NO_MATCH_WARNING = (
    "Commentary source store is available, but no passage-linked "
    "commentary evidence was found for this reference."
)
COMMENTARY_EVIDENCE_LIMIT = 6

# Soft target (prefer stop) vs hard max (never exceed).
# Goal: minimize provider token usage — do not pad to the hard max.
# Exegesis target ~2200–2800; historical ~1800–2500.
DEFAULT_TARGET_TOKENS: dict[str, int] = {
    PROFILE_EXEGESIS: 2500,
    PROFILE_HISTORICAL: 2200,
    PROFILE_THEOLOGY: 3500,
    PROFILE_COMMENTARY: 3000,
}

DEFAULT_MAX_TOKENS: dict[str, int] = {
    PROFILE_EXEGESIS: 4500,
    PROFILE_HISTORICAL: 3500,
    PROFILE_THEOLOGY: 3500,
    PROFILE_COMMENTARY: 3500,
}

# Backward-compatible alias used by older callers.
DEFAULT_TOKEN_BUDGETS = DEFAULT_MAX_TOKENS

# Per-type soft caps within the overall budget (aligned to target, not hard max).
DEFAULT_TYPE_BUDGETS: dict[str, dict[str, int]] = {
    PROFILE_EXEGESIS: {
        BUDGET_PASSAGE: 120,
        BUDGET_LINGUISTIC: 700,
        BUDGET_EXEGETICAL: 1200,
        BUDGET_DICTIONARY: 350,
        BUDGET_ENTITY: 200,
        BUDGET_BACKGROUND: 250,
    },
    PROFILE_HISTORICAL: {
        BUDGET_PASSAGE: 120,
        BUDGET_LINGUISTIC: 150,
        BUDGET_EXEGETICAL: 0,
        # Prefer place/enrichment background over dictionary padding.
        BUDGET_DICTIONARY: 700,
        BUDGET_ENTITY: 200,
        BUDGET_BACKGROUND: 900,
    },
    PROFILE_THEOLOGY: {
        BUDGET_PASSAGE: 150,
        BUDGET_LINGUISTIC: 800,
        BUDGET_EXEGETICAL: 500,
        BUDGET_DICTIONARY: 250,
        BUDGET_BACKGROUND: 350,
        BUDGET_THEOLOGY: 3500,
    },
    PROFILE_COMMENTARY: {
        BUDGET_PASSAGE: 150,
        BUDGET_LINGUISTIC: 500,
        BUDGET_BACKGROUND: 250,
        BUDGET_COMMENTARY: 3000,
    },
}

# Minimum diversity: reserve slots for these budget types when candidates exist.
DEFAULT_DIVERSITY_TYPES: dict[str, tuple[str, ...]] = {
    PROFILE_EXEGESIS: (BUDGET_LINGUISTIC, BUDGET_EXEGETICAL, BUDGET_DICTIONARY, BUDGET_ENTITY),
    # Background first so place/enrichment is reserved before dictionary/entities.
    PROFILE_HISTORICAL: (BUDGET_BACKGROUND, BUDGET_DICTIONARY, BUDGET_ENTITY),
    PROFILE_THEOLOGY: (BUDGET_THEOLOGY, BUDGET_LINGUISTIC, BUDGET_BACKGROUND),
    PROFILE_COMMENTARY: (BUDGET_COMMENTARY,),
}

# Higher number = retained first under token budget pressure.
PROFILE_PRIORITIES: dict[str, dict[str, int]] = {
    PROFILE_EXEGESIS: {
        RELATION_DIRECT_PASSAGE: 100,
        RELATION_PASSAGE_TOKEN: 95,
        RELATION_EXEGETICAL_NOTE: 93,
        RELATION_DICTIONARY_BACKGROUND: 78,
        RELATION_LEXICAL_HIGHLIGHT: 90,
        "compact_linguistic_line": 88,
        RELATION_PASSAGE_PLACE: 70,
        RELATION_PLACE_CATALOG: 60,
        RELATION_PLACE_ENRICHMENT: 40,
        "passage_summary": 98,
    },
    PROFILE_HISTORICAL: {
        # Prefer concrete historical/place grounding over generic dictionary/ACAI.
        RELATION_PLACE_ENRICHMENT: 100,
        RELATION_PASSAGE_PLACE: 96,
        RELATION_PLACE_CATALOG: 90,
        RELATION_DICTIONARY_BACKGROUND: 82,
        "place_geography": 78,
        "place_card_summary": 74,
        "historical_entity": 70,
        RELATION_DIRECT_PASSAGE: 50,
        RELATION_LEXICAL_HIGHLIGHT: 30,
        RELATION_PASSAGE_TOKEN: 10,
    },
    PROFILE_THEOLOGY: {
        RELATION_DIRECT_PASSAGE: 100,
        RELATION_THEOLOGICAL_SOURCE: 90,
        RELATION_LEXICAL_HIGHLIGHT: 85,
        RELATION_PASSAGE_PLACE: 75,
        RELATION_PLACE_CATALOG: 65,
        RELATION_PLACE_ENRICHMENT: 55,
        RELATION_PASSAGE_TOKEN: 20,
    },
    PROFILE_COMMENTARY: {
        # Direct linguistic/lexical/morphological evidence always outranks
        # classic commentary — Commentary is an interpretive witness layer,
        # never a substitute for direct evidence. No per-commentator
        # reliability score is assigned.
        RELATION_DIRECT_PASSAGE: 100,
        RELATION_COMMENTARY_SOURCE: 90,
        RELATION_LEXICAL_HIGHLIGHT: 85,
        RELATION_PASSAGE_TOKEN: 20,
    },
}

# Item-type → selection tier (profile-specific overrides applied in code).
EXEGESIS_ITEM_TIERS: dict[str, str] = {
    "passage": TIER_CORE,
    "passage_summary": TIER_CORE,
    "linguistic": TIER_PRIMARY,
    "exegetical_note": TIER_PRIMARY,
    "dictionary_background": TIER_SUPPORTING,
    "entity_summary": TIER_SUPPORTING,
    "place_link": TIER_SUPPORTING,
    "place_catalog": TIER_SUPPORTING,
    "enrichment": TIER_OPTIONAL,
}

HISTORICAL_ITEM_TIERS: dict[str, str] = {
    "passage_scope": TIER_CORE,
    "historical_enrichment": TIER_PRIMARY,
    "passage_place_link": TIER_PRIMARY,
    "place_catalog": TIER_SUPPORTING,
    # Dictionary/entities support history but must not crowd out place/enrichment.
    "dictionary_background": TIER_SUPPORTING,
    "entity_summary": TIER_SUPPORTING,
    "geography": TIER_SUPPORTING,
}

THEOLOGY_ITEM_TIERS: dict[str, str] = {
    "passage": TIER_CORE,
    "theological_source": TIER_PRIMARY,
    "lexical": TIER_PRIMARY,
    "place_link": TIER_SUPPORTING,
    "place_catalog": TIER_OPTIONAL,
}

COMMENTARY_ITEM_TIERS: dict[str, str] = {
    "passage": TIER_CORE,
    "commentary_source": TIER_PRIMARY,
    "lexical": TIER_PRIMARY,
}


@dataclass(frozen=True)
class ContextProfile:
    name: str
    token_budget: int
    priorities: dict[str, int]
    target_tokens: int = 2500
    max_tokens: int = 4500
    type_budgets: dict[str, int] = field(default_factory=dict)
    diversity_types: tuple[str, ...] = ()
    item_tiers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        name: str,
        *,
        token_budget: int | None = None,
        target_tokens: int | None = None,
    ) -> ContextProfile:
        if name not in SUPPORTED_PROFILES:
            raise ValueError(f"Unsupported context profile: {name!r}")
        max_tokens = token_budget if token_budget is not None else DEFAULT_MAX_TOKENS[name]
        target = target_tokens if target_tokens is not None else DEFAULT_TARGET_TOKENS[name]
        if target > max_tokens:
            target = max_tokens
        tiers = {
            PROFILE_EXEGESIS: EXEGESIS_ITEM_TIERS,
            PROFILE_HISTORICAL: HISTORICAL_ITEM_TIERS,
            PROFILE_THEOLOGY: THEOLOGY_ITEM_TIERS,
            PROFILE_COMMENTARY: COMMENTARY_ITEM_TIERS,
        }[name]
        return cls(
            name=name,
            token_budget=max_tokens,
            max_tokens=max_tokens,
            target_tokens=target,
            priorities=dict(PROFILE_PRIORITIES[name]),
            type_budgets=dict(DEFAULT_TYPE_BUDGETS[name]),
            diversity_types=DEFAULT_DIVERSITY_TYPES[name],
            item_tiers=dict(tiers),
        )
