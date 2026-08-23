"""Context profile definitions and selection priorities."""

from __future__ import annotations

from dataclasses import dataclass

from textus_kb.evidence import (
    RELATION_DIRECT_PASSAGE,
    RELATION_EXEGETICAL_NOTE,
    RELATION_LEXICAL_HIGHLIGHT,
    RELATION_PASSAGE_PLACE,
    RELATION_PASSAGE_TOKEN,
    RELATION_PLACE_CATALOG,
    RELATION_PLACE_ENRICHMENT,
)

PROFILE_EXEGESIS = "exegesis"
PROFILE_HISTORICAL = "historical_context"
PROFILE_THEOLOGY = "theology"

SUPPORTED_PROFILES = frozenset(
    {PROFILE_EXEGESIS, PROFILE_HISTORICAL, PROFILE_THEOLOGY}
)

DEFAULT_TOKEN_BUDGETS: dict[str, int] = {
    PROFILE_EXEGESIS: 4500,
    PROFILE_HISTORICAL: 3500,
    PROFILE_THEOLOGY: 3500,
}

THEOLOGY_SOURCE_WARNING = "No dedicated theological source layer available"

# Higher number = retained first under token budget pressure.
PROFILE_PRIORITIES: dict[str, dict[str, int]] = {
    PROFILE_EXEGESIS: {
        RELATION_DIRECT_PASSAGE: 100,
        RELATION_PASSAGE_TOKEN: 95,
        RELATION_EXEGETICAL_NOTE: 93,
        RELATION_LEXICAL_HIGHLIGHT: 90,
        "compact_linguistic_line": 88,
        RELATION_PASSAGE_PLACE: 70,
        RELATION_PLACE_CATALOG: 60,
        RELATION_PLACE_ENRICHMENT: 40,
        "passage_summary": 98,
    },
    PROFILE_HISTORICAL: {
        RELATION_PASSAGE_PLACE: 100,
        RELATION_PLACE_ENRICHMENT: 90,
        RELATION_PLACE_CATALOG: 85,
        "place_geography": 80,
        "place_card_summary": 75,
        RELATION_DIRECT_PASSAGE: 50,
        RELATION_LEXICAL_HIGHLIGHT: 30,
        RELATION_PASSAGE_TOKEN: 10,
    },
    PROFILE_THEOLOGY: {
        RELATION_DIRECT_PASSAGE: 100,
        RELATION_LEXICAL_HIGHLIGHT: 85,
        RELATION_PASSAGE_PLACE: 75,
        RELATION_PLACE_CATALOG: 65,
        RELATION_PLACE_ENRICHMENT: 55,
        RELATION_PASSAGE_TOKEN: 20,
    },
}


@dataclass(frozen=True)
class ContextProfile:
    name: str
    token_budget: int
    priorities: dict[str, int]

    @classmethod
    def load(cls, name: str, *, token_budget: int | None = None) -> ContextProfile:
        if name not in SUPPORTED_PROFILES:
            raise ValueError(f"Unsupported context profile: {name!r}")
        budget = token_budget if token_budget is not None else DEFAULT_TOKEN_BUDGETS[name]
        return cls(
            name=name,
            token_budget=budget,
            priorities=dict(PROFILE_PRIORITIES[name]),
        )
