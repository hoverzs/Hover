"""Versioned Hungarian Commentary translation policy: the strict
professional-translator prompt template plus a partial theological
glossary for consistent terminology.

``TRANSLATION_POLICY_VERSION`` is part of the translation cache key
(``textus_kb.commentary_translation_store``) -- bump it whenever a change
here (rule wording, glossary entries) could change translation output,
so every previously cached translation is treated as stale and
regenerated rather than silently served under the old wording.
"""

from __future__ import annotations

TRANSLATION_POLICY_VERSION = "v1"

# Partial glossary -- common Reformed/classical theological terms only.
# Per this round's scope: NOT a full theological lexicon. Safe to extend
# with more terms in a future round WITHOUT a version bump only as long
# as it never changes how an already-covered term is translated; changing
# an existing mapping always requires bumping TRANSLATION_POLICY_VERSION.
HU_THEOLOGICAL_GLOSSARY: dict[str, str] = {
    "atonement": "engesztelés",
    "covenant": "szövetség",
    "election": "kiválasztás",
    "faith": "hit",
    "grace": "kegyelem",
    "imputation": "beszámítás",
    "justification": "megigazulás",
    "reconciliation": "megbékélés",
    "redemption": "megváltás",
    "regeneration": "újjászületés",
    "repentance": "megtérés",
    "righteousness": "igazság / megigazultság",
    "salvation": "üdvösség",
    "sanctification": "megszentelődés",
    "propitiation": "engesztelő áldozat",
}

_TRANSLATOR_RULES = """=== FORDÍTÁSI SZABÁLYOK -- SZIGORÚ SZAKFORDÍTÓI MÓD ===
Ez egy klasszikus keresztény kommentár-szakasz teljes, szó szerinti fordítása angolról \
magyarra. Kizárólag fordíts -- ne végezz semmilyen szerkesztést, értelmezést vagy tartalmi \
változtatást.

KÖTELEZŐ SZABÁLYOK:
- Ne foglald össze a szöveget -- a TELJES tartalmat fordítsd le, semmit ne hagyj ki.
- Ne magyarázz hozzá semmit, amit az eredeti szerző nem írt le.
- Ne javítsd ki, ne finomítsd és ne "korrigáld" teológiailag a szerző álláspontját, még akkor \
sem, ha vitatható vagy elavultnak tűnik.
- Ne modernizáld önkényesen a gondolatmenetet, a stílust vagy a szóhasználatot.
- Ne változtasd meg az eredeti érvelés hangsúlyait, sorrendjét vagy bekezdésszerkezetét.
- Görög, héber és latin kifejezéseket -- ha az eredeti szövegben szerepelnek -- őrizd meg \
eredeti alakjukban (az eredetiben szereplő zárójeles magyarázattal együtt, ha az eredeti is \
így teszi; saját magyarázatot ne adj hozzá).
- Bibliai hivatkozásokat felismerhető formában add vissza -- ne told el, ne cseréld le más \
hivatkozásra.
- Bizonytalan jelentésű szó vagy kifejezés esetén NE találj ki jelentést -- fordítsd a \
legszorosabb, legszó szerintibb magyar megfelelővel, saját feltételezés hozzáadása nélkül.
- Az idézetek (más bibliai versek, latin mondások, stb.) logikai helye maradjon pontosan ott, \
ahol az eredetiben van.

TERMINOLÓGIA -- ezeket a fogalmakat KÖVETKEZETESEN, mindig ugyanúgy fordítsd, valahányszor \
előfordulnak:
{glossary}

A kimenet KIZÁRÓLAG a lefordított magyar szöveg legyen -- ne fűzz hozzá saját bevezetőt, \
összefoglalót, megjegyzést vagy magyarázatot a fordításhoz."""


def _glossary_block() -> str:
    return "\n".join(
        f"- {en} → {hu}" for en, hu in sorted(HU_THEOLOGICAL_GLOSSARY.items())
    )


def build_translation_prompt(
    *,
    section_text: str,
    work_title: str,
    contributors: str,
    passage_display: str,
) -> str:
    """Full translation prompt for one canonical Commentary section.
    ``section_text`` must already be the FULL ordered chunk text (never a
    UI preview) -- enforced by the caller
    (``commentary_translation_service.get_or_create_translation``)."""
    rules = _TRANSLATOR_RULES.format(glossary=_glossary_block())
    header = (
        "=== FORDÍTANDÓ KOMMENTÁR-SZAKASZ ===\n"
        f"Mű: {work_title}\n"
        f"Szerző/közreműködő: {contributors}\n"
        f"Kapcsolódó igehely: {passage_display}"
    )
    return "\n\n".join(
        [
            rules,
            header,
            "<<<BEGIN_SOURCE_TEXT>>>",
            section_text,
            "<<<END_SOURCE_TEXT>>>",
        ]
    )


__all__ = [
    "HU_THEOLOGICAL_GLOSSARY",
    "TRANSLATION_POLICY_VERSION",
    "build_translation_prompt",
]
