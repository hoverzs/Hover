"""Konkordancia — 2. mód: eredeti nyelvi (héber/görög) keresés.

Adott Strong-szám vagy lemma (héber/görög szótő) összes előfordulását
adja vissza a teljes Bibliában (héber ÓSZ + görög ÚSZ), a RÚF magyar
kontextussal együtt. A bemenetet automatikusan felismeri: Strong-kód
minta (pl. "H3467", "G2316") vagy héber/görög írásjelekből álló szöveg
esetén ez a modul illetékes, egyébként (magyar/latin szöveg) az 1. mód
(`ruf_bible_local_db.search_literal`) marad az irányadó.

A magyar kontextus-sor a helyi RÚF-szövegtárból (`ruf_bible_local_db`)
jön — ugyanaz a forrás, mint az 1. módnál —, NEM a fő igehely-mezőnél
használt élő API-ból; a konkordancia-panel egyik módja sem érinti a fő
igehely-beviteli mezőt vagy annak élő API-útvonalát.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bible_engine.hebrew_books import OT_BOOKS
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.tagnt_books import RUF_TO_TAGNT_BOOK_CODES
from bible_engine.tagnt_sqlite import (
    find_greek_tokens_by_lemma,
    find_greek_tokens_by_strong_id,
)
from bible_engine.greek_token_repository import resolve_tagnt_database_path
import ruf_bible_local_db as local_db
from ruf_bible_service import CANONICAL_BOOKS


_HEBREW_STRONG_RE = re.compile(r"^H\d{3,4}[A-Z]?$", re.IGNORECASE)
_GREEK_STRONG_RE = re.compile(r"^G\d{3,4}$", re.IGNORECASE)
_HEBREW_SCRIPT_RE = re.compile(r"[֐-׿]")
_GREEK_SCRIPT_RE = re.compile(r"[Ͱ-Ͽἀ-῿]")

# tahot/tagnt könyvkód -> RÚF 3-betűs könyvkód, a magyar rövidítéshez
# (ruf_bible_service.CANONICAL_BOOKS) és a helyi RÚF-DB-hez.
_TAHOT_TO_RUF: dict[str, str] = {b.tahot_code: b.ruf_code for b in OT_BOOKS}
_TAGNT_TO_RUF: dict[str, str] = {v: k for k, v in RUF_TO_TAGNT_BOOK_CODES.items()}
_RUF_CODE_TO_BOOK = {b.code: b for b in CANONICAL_BOOKS}


QueryKind = str  # "strong_hebrew" | "strong_greek" | "hebrew_lemma" | "greek_lemma" | "unknown"


def detect_query_kind(query: str) -> QueryKind:
    q = (query or "").strip()
    if not q:
        return "unknown"
    if _HEBREW_STRONG_RE.match(q):
        return "strong_hebrew"
    if _GREEK_STRONG_RE.match(q):
        return "strong_greek"
    if _HEBREW_SCRIPT_RE.search(q):
        return "hebrew_lemma"
    if _GREEK_SCRIPT_RE.search(q):
        return "greek_lemma"
    return "unknown"


def is_original_language_query(query: str) -> bool:
    """True, ha a bevitel Strong-kód mintát követ, vagy héber/görög
    írásjeleket tartalmaz — ilyenkor a Konkordancia panel automatikusan
    a 2. módba (ez a modul) vált az 1. mód (szó szerinti RÚF-keresés)
    helyett."""
    return detect_query_kind(query) != "unknown"


@dataclass(frozen=True)
class OriginalLanguageHit:
    language: str  # "héber" | "görög"
    book_abbr: str
    ordinal: int
    chapter: int
    verse: int
    surface: str
    lemma: str
    strong_id: str
    hungarian_context: str = ""


def search_original(
    query: str, *, with_hungarian_context: bool = True
) -> list[OriginalLanguageHit]:
    """A `query` alapján (Strong-kód vagy lemma) megkeresi az összes
    előfordulást. Ismeretlen/üres bevitelnél üres listát ad — a hívó
    felelőssége eldönteni, hogy egyáltalán ezt a modult hívja-e
    (lásd `is_original_language_query`)."""
    kind = detect_query_kind(query)
    q = (query or "").strip()
    if kind == "unknown":
        return []

    hits: list[OriginalLanguageHit] = []
    if kind == "strong_hebrew":
        hits.extend(_search_hebrew(q.upper(), by_strong=True))
    elif kind == "hebrew_lemma":
        hits.extend(_search_hebrew(q, by_strong=False))
    elif kind == "strong_greek":
        hits.extend(_search_greek(q.upper(), by_strong=True))
    elif kind == "greek_lemma":
        hits.extend(_search_greek(q, by_strong=False))

    if with_hungarian_context:
        hits = [_attach_context(hit) for hit in hits]
    return hits


def _search_hebrew(value: str, *, by_strong: bool) -> list[OriginalLanguageHit]:
    repo = HebrewTokenRepository()
    tokens = repo.by_strong_id(value) if by_strong else repo.by_lemma(value)
    seen: set[str] = set()
    hits: list[OriginalLanguageHit] = []
    for token in tokens:
        # A `by_strong_id`/`by_lemma` a komponens- ÉS a flat 'token'-
        # szerepű token_strong_ids sor miatt duplikálhatja ugyanazt a
        # tokent — itt a stable_key alapján szűrjük az egyedi találatokra.
        if token.stable_key in seen:
            continue
        seen.add(token.stable_key)
        ruf_code = _TAHOT_TO_RUF.get(token.book)
        book_info = _RUF_CODE_TO_BOOK.get(ruf_code) if ruf_code else None
        if book_info is None:
            continue
        hits.append(
            OriginalLanguageHit(
                language="héber",
                book_abbr=book_info.abbr,
                ordinal=_ordinal_of(book_info.code),
                chapter=token.chapter,
                verse=token.verse,
                surface=token.surface,
                lemma=token.lemma,
                strong_id=value if by_strong else (token.strong_ids[0] if token.strong_ids else ""),
                hungarian_context="",
            )
        )
    hits.sort(key=lambda h: (h.ordinal, h.chapter, h.verse))
    return hits


def _search_greek(value: str, *, by_strong: bool) -> list[OriginalLanguageHit]:
    database_path = resolve_tagnt_database_path()
    if database_path is None:
        return []
    tokens = (
        find_greek_tokens_by_strong_id(database_path, value)
        if by_strong
        else find_greek_tokens_by_lemma(database_path, value)
    )
    hits: list[OriginalLanguageHit] = []
    for token in tokens:
        ruf_code = _TAGNT_TO_RUF.get(token.book)
        book_info = _RUF_CODE_TO_BOOK.get(ruf_code) if ruf_code else None
        if book_info is None:
            continue
        hits.append(
            OriginalLanguageHit(
                language="görög",
                book_abbr=book_info.abbr,
                ordinal=_ordinal_of(book_info.code),
                chapter=token.chapter,
                verse=token.verse,
                surface=token.greek_form,
                lemma=token.lemma,
                strong_id=token.strong_id,
                hungarian_context="",
            )
        )
    hits.sort(key=lambda h: (h.ordinal, h.chapter, h.verse))
    return hits


def _ordinal_of(ruf_code: str) -> int:
    for index, book in enumerate(CANONICAL_BOOKS, start=1):
        if book.code == ruf_code:
            return index
    return 999


def attach_hungarian_context(hit: OriginalLanguageHit) -> OriginalLanguageHit:
    """Egyetlen találathoz utólag hozzáfűzi a RÚF magyar kontextus-sort.

    Nagy találatszámú keresésnél (pl. gyakori Strong-szám) hívd ezt
    csak a ténylegesen megjelenített (laponkénti) találatokra —
    `search_original(..., with_hungarian_context=False)` a teljes
    listát kontextus nélkül, olcsón adja vissza."""
    return _attach_context(hit)


def _attach_context(hit: OriginalLanguageHit) -> OriginalLanguageHit:
    ruf_code = next(
        (book.code for book in CANONICAL_BOOKS if book.abbr == hit.book_abbr),
        None,
    )
    if ruf_code is None:
        return hit
    verses = local_db.lookup_local(ruf_code, hit.chapter, hit.verse, hit.verse)
    context = verses[0]["text"] if verses else ""
    return OriginalLanguageHit(
        language=hit.language,
        book_abbr=hit.book_abbr,
        ordinal=hit.ordinal,
        chapter=hit.chapter,
        verse=hit.verse,
        surface=hit.surface,
        lemma=hit.lemma,
        strong_id=hit.strong_id,
        hungarian_context=context,
    )


__all__ = [
    "OriginalLanguageHit",
    "detect_query_kind",
    "is_original_language_query",
    "search_original",
    "attach_hungarian_context",
]
