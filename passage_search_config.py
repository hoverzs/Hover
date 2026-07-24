"""Igehely-keresés — alkalmi gyakorisági / „elcsépelt” textusok konfigurációja.

Súlycsökkentő lista, nem tiltólista. Egy klasszikus textus megjelenhet,
ha jól illik, de az öt ajánlásból legfeljebb egy lehet ilyen.
"""

from __future__ import annotations

from typing import Any

# UI selectbox opciók — sorrend a felületen.
OCCASION_OPTIONS: tuple[str, ...] = (
    "Vasárnapi istentisztelet",
    "Bűnbánati istentisztelet",
    "Virrasztó",
    "Temetés",
    "Esketés",
    "Keresztelés",
    "Úrvacsorai alkalom",
    "Hálaadó istentisztelet",
    "Konfirmáció",
    "Egyéb alkalom",
)

# Alkalom → gyakran automatikusan felmerülő (elcsépelt) referenciák.
# Normalizált / közeli alakok; az egyezés parse_bible_reference után történik.
COMMON_REFERENCES_BY_OCCASION: dict[str, tuple[str, ...]] = {
    "Virrasztó": (
        "Zsolt 23",
        "Zsolt 23,1–6",
        "Jn 14,1–6",
        "Jn 11,25–26",
        "Róm 8,38–39",
        "2Kor 1,3–7",
    ),
    "Temetés": (
        "Zsolt 23",
        "Zsolt 23,1–6",
        "Jn 11,25–26",
        "Jn 14,1–6",
        "Róm 8,38–39",
        "1Thess 4,13–18",
    ),
    "Esketés": (
        "1Kor 13,1–13",
        "1Kor 13",
    ),
    "Keresztelés": (
        "Mk 10,13–16",
        "Mt 28,18–20",
        "Mt 3,13–17",
        "ApCsel 2,38–39",
    ),
    "Bűnbánati istentisztelet": (
        "Zsolt 51",
        "Zsolt 51,1–19",
        "Lk 15,11–32",
        "1Jn 1,8–10",
    ),
    "Vasárnapi istentisztelet": (
        "Jn 3,16–21",
        "Róm 8,28–39",
        "Mt 5,1–12",
    ),
    "Úrvacsorai alkalom": (
        "1Kor 11,23–26",
        "Lk 22,14–20",
        "Jn 6,35–40",
    ),
    "Hálaadó istentisztelet": (
        "Zsolt 103",
        "Zsolt 100",
        "1Thess 5,16–18",
    ),
    "Konfirmáció": (
        "Józs 1,9",
        "2Tim 1,7",
        "Mt 28,18–20",
    ),
    "Egyéb alkalom": (),
}

MAX_COMMON_IN_BATCH = 1


def common_references_for(occasion: str) -> tuple[str, ...]:
    key = (occasion or "").strip()
    return COMMON_REFERENCES_BY_OCCASION.get(key, ())


def get_passage_search_config() -> dict[str, Any]:
    """Szerkeszthető pillanatkép tesztekhez / későbbi bővítéshez."""
    return {
        "occasion_options": list(OCCASION_OPTIONS),
        "common_references_by_occasion": {
            k: list(v) for k, v in COMMON_REFERENCES_BY_OCCASION.items()
        },
        "max_common_in_batch": MAX_COMMON_IN_BATCH,
    }


__all__ = [
    "OCCASION_OPTIONS",
    "COMMON_REFERENCES_BY_OCCASION",
    "MAX_COMMON_IN_BATCH",
    "common_references_for",
    "get_passage_search_config",
]
