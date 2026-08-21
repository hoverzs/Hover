"""RESET 3B-6 — determinisztikus, non-blocking post-hoc grounding cross-
check az eredeti nyelvi (görög/héber) AI-kimenetekhez.

A cél KIZÁRÓLAG a durva grounding-sértések felismerése — nem nyelvészeti
parser, nem filológiai helyesség-ellenőrzés. A generált szövegből
kigyűjtött görög/héber szóalakokat, lemmákat és Strong-azonosítókat
összeveti a HELYI token/lexikon infrastruktúrával (a MEGLÉVŐ
`greek_token_repository` / `hebrew_token_repository` / `tagnt_sqlite` /
`hebrew_sqlite` / `*_lexicon_repository` helperekkel — nem olvas nyers
fájlt, nem épít új adatbázist).

Streamlit-független modul — közvetlenül, subprocess-izoláció NÉLKÜL
unit-tesztelhető (ld. `bible_engine/*_token_repository.py`, amelyek maguk
is Streamlit-függetlenek).

Döntési kategóriák (ld. RESET 3B-5 audit):
  - PASSAGE_MATCH — a jelenlegi passzus tokenjei között megtalálható,
    NEM kerül a visszaadott figyelmeztetés-listába.
  - GLOBAL_OTHER_PASSAGE — a jelenlegi passzusban nincs, de a globális
    token/lexikon infrastruktúrában valódi adatként azonosítható. Erős
    jelzés, de NEM automatikusan hibás — lehet tudatos párhuzam.
  - UNKNOWN — sem a passzusban, sem a globális adatbázisokban nem
    azonosítható. Óvatos jelzés — NEM nevezzük hallucinációnak (lehet
    kiadás-eltérés, transzliterációs variáns, vagy a helyi adatbázis
    lefedettségi határa: TAGNT csak ÚSZ-t, TAHOT csak ÓSZ-t fed le).
  - INVALID_STRONG_ID — a meglévő Strong-normalizáló (`normalize_greek_
    strong_id` / `normalize_hebrew_strong_id`) formátumhibát jelez.

A visszaadott figyelmeztetés-lista SOSEM blokkol semmit — a hívó felelt-
őssége, hogy csak megjelenítse (`st.warning`-hoz hasonlóan), sosem
akasztja meg a generálást/mentést/elfogadást."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from bible_engine.greek_lexicon_repository import (
    TBESGDatabaseUnavailableError,
    get_tbesg_lexicon_entry,
)
from bible_engine.greek_token_repository import (
    load_greek_passage_tokens,
    resolve_tagnt_database_path,
)
from bible_engine.hebrew_books import HebrewReferenceError, parse_hebrew_reference
from bible_engine.hebrew_lexicon_repository import (
    HebrewLexiconRepository,
    normalize_hebrew_strong_id,
)
from bible_engine.hebrew_parser import strip_hebrew_accents
from bible_engine.hebrew_sqlite import (
    find_hebrew_tokens_by_strong_id,
    resolve_tahot_database_path,
)
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.tagnt_sqlite import find_greek_tokens_by_lemma
from bible_engine.tbesg_parser import normalize_greek_strong_id


class GroundingCategory(str, Enum):
    PASSAGE_MATCH = "passage_match"
    GLOBAL_OTHER_PASSAGE = "global_other_passage"
    UNKNOWN = "unknown"
    INVALID_STRONG_ID = "invalid_strong_id"


@dataclass(frozen=True)
class GroundingWarning:
    category: GroundingCategory
    kind: str  # "greek_word" | "hebrew_word" | "greek_strong" | "hebrew_strong"
    value: str
    message: str


@dataclass(frozen=True)
class PassageVocabulary:
    greek_surface_forms: frozenset[str]
    greek_surface_forms_stripped: frozenset[str]
    greek_lemmas: frozenset[str]
    greek_lemmas_stripped: frozenset[str]
    greek_strong_ids: frozenset[str]
    hebrew_surface_forms_stripped: frozenset[str]
    hebrew_lemmas_stripped: frozenset[str]
    hebrew_strong_ids: frozenset[str]


_EMPTY_VOCABULARY = PassageVocabulary(
    greek_surface_forms=frozenset(),
    greek_surface_forms_stripped=frozenset(),
    greek_lemmas=frozenset(),
    greek_lemmas_stripped=frozenset(),
    greek_strong_ids=frozenset(),
    hebrew_surface_forms_stripped=frozenset(),
    hebrew_lemmas_stripped=frozenset(),
    hebrew_strong_ids=frozenset(),
)

# Görög: alap blokk (Ͱ-Ͽ) + kiterjesztett/politonikus blokk (ἀ-῿) — UGYANEZ
# a tartomány, mint az `app.py::_EXEGESIS_SUPPORT_PATTERN`-ben, csak itt
# `+` kvantorral, összefüggő szó-futamok kinyeréséhez.
_GREEK_RUN_RE = re.compile(r"[Ͱ-Ͽἀ-῿]+")
# Héber blokk (nikud/kantilláció + betűk együtt, ugyanabban a futamban).
_HEBREW_RUN_RE = re.compile(r"[֐-׿]+")
_GREEK_STRONG_RE = re.compile(r"\bG\d{1,5}[A-Z]?\b", re.IGNORECASE)
_HEBREW_STRONG_RE = re.compile(r"\bH\d{1,4}[A-Z]?\b", re.IGNORECASE)

# A `greek_analysis_ui.py::_looks_like_cross_chapter_reference`-szal
# SZÁNDÉKOSAN azonos, ide másolt minta — azt a modult NEM importáljuk,
# mert `streamlit`-et importál a tetején, ez a modul viszont
# Streamlit-független kell maradjon.
_CROSS_CHAPTER_REFERENCE_RE = re.compile(
    r"^(?:\d\s*)?[^\d,.:]+\s+\d+\s*[,.:]\s*\d+\s*-\s*\d+\s*[,.:]\s*\d+\s*$",
    re.IGNORECASE,
)


def _looks_like_cross_chapter_reference(reference: str) -> bool:
    cleaned = (reference or "").strip().replace("–", "-").replace("—", "-")
    return bool(_CROSS_CHAPTER_REFERENCE_RE.match(cleaned))


def _strip_combining_marks(value: str) -> str:
    """Görög accent/breathing-stripping összehasonlító kulcs — NFD, majd a
    kombinálójelek eltávolítása. Az EREDETI szöveget sosem módosítja a
    hívó oldalon, ez csak egy belső, másodlagos összevetési kulcs."""
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def build_passage_vocabulary(igehely: str) -> PassageVocabulary:
    """A jelenlegi passzushoz tartozó görög/héber szóalak/lemma/Strong-
    halmaz — a MEGLÉVŐ `load_greek_passage_tokens()` / `HebrewTokenRepository.
    passage()` hívásokból építve (ugyanaz a forrás, mint `app.py::
    build_original_language_token_block`). Hiányzó/érvénytelen/cross-
    chapter hivatkozás esetén üres szótárat ad vissza — sosem dob kivételt."""
    reference = (igehely or "").strip()
    if not reference:
        return _EMPTY_VOCABULARY

    greek_surface: set[str] = set()
    greek_surface_stripped: set[str] = set()
    greek_lemma: set[str] = set()
    greek_lemma_stripped: set[str] = set()
    greek_strong: set[str] = set()

    if not _looks_like_cross_chapter_reference(reference):
        try:
            verse_groups = load_greek_passage_tokens(reference)
        except (FileNotFoundError, ValueError):
            verse_groups = []
        for group in verse_groups:
            for token in group.tokens:
                form_nfc = unicodedata.normalize("NFC", token.greek_form)
                lemma_nfc = unicodedata.normalize("NFC", token.lemma)
                if form_nfc:
                    greek_surface.add(form_nfc)
                    greek_surface_stripped.add(_strip_combining_marks(form_nfc))
                if lemma_nfc:
                    greek_lemma.add(lemma_nfc)
                    greek_lemma_stripped.add(_strip_combining_marks(lemma_nfc))
                if token.strong_id:
                    greek_strong.add(token.strong_id.strip().upper())

    hebrew_surface_stripped: set[str] = set()
    hebrew_lemma_stripped: set[str] = set()
    hebrew_strong: set[str] = set()

    try:
        book, chapter, verse_start, verse_end = parse_hebrew_reference(reference)
    except HebrewReferenceError:
        book = None

    if book is not None:
        repository = HebrewTokenRepository()
        result = repository.passage(book, chapter, verse_start, verse_end)
        if result.status == "ok":
            for token in result.tokens:
                if token.surface_without_accents:
                    hebrew_surface_stripped.add(token.surface_without_accents)
                if token.lemma:
                    hebrew_lemma_stripped.add(strip_hebrew_accents(token.lemma))
                for strong_id in token.strong_ids:
                    if strong_id:
                        hebrew_strong.add(strong_id.strip().upper())

    return PassageVocabulary(
        greek_surface_forms=frozenset(greek_surface),
        greek_surface_forms_stripped=frozenset(greek_surface_stripped),
        greek_lemmas=frozenset(greek_lemma),
        greek_lemmas_stripped=frozenset(greek_lemma_stripped),
        greek_strong_ids=frozenset(greek_strong),
        hebrew_surface_forms_stripped=frozenset(hebrew_surface_stripped),
        hebrew_lemmas_stripped=frozenset(hebrew_lemma_stripped),
        hebrew_strong_ids=frozenset(hebrew_strong),
    )


def _greek_word_exists_globally(value: str) -> bool:
    if not value:
        return False
    path = resolve_tagnt_database_path()
    if path is None or not path.exists():
        return False
    try:
        return bool(find_greek_tokens_by_lemma(path, value))
    except (FileNotFoundError, ValueError):
        return False


def _hebrew_word_exists_globally(value: str) -> bool:
    if not value:
        return False
    try:
        return bool(HebrewTokenRepository().by_lemma(value))
    except Exception:
        return False


def _classify_greek_word(value: str, vocabulary: PassageVocabulary) -> GroundingCategory:
    nfc = unicodedata.normalize("NFC", value)
    stripped = _strip_combining_marks(nfc)
    if nfc in vocabulary.greek_surface_forms or nfc in vocabulary.greek_lemmas:
        return GroundingCategory.PASSAGE_MATCH
    if (
        stripped in vocabulary.greek_surface_forms_stripped
        or stripped in vocabulary.greek_lemmas_stripped
    ):
        return GroundingCategory.PASSAGE_MATCH
    if _greek_word_exists_globally(nfc) or _greek_word_exists_globally(stripped):
        return GroundingCategory.GLOBAL_OTHER_PASSAGE
    return GroundingCategory.UNKNOWN


def _classify_hebrew_word(value: str, vocabulary: PassageVocabulary) -> GroundingCategory:
    nfc = unicodedata.normalize("NFC", value)
    stripped = strip_hebrew_accents(nfc)
    if stripped in vocabulary.hebrew_surface_forms_stripped or stripped in vocabulary.hebrew_lemmas_stripped:
        return GroundingCategory.PASSAGE_MATCH
    if _hebrew_word_exists_globally(nfc) or _hebrew_word_exists_globally(stripped):
        return GroundingCategory.GLOBAL_OTHER_PASSAGE
    return GroundingCategory.UNKNOWN


def _greek_strong_exists_globally(normalized: str) -> bool:
    try:
        entry = get_tbesg_lexicon_entry(normalized)
    except TBESGDatabaseUnavailableError:
        return False
    return entry is not None


def _hebrew_strong_exists_globally(normalized: str, lexicon: HebrewLexiconRepository) -> bool:
    try:
        lookup = lexicon.lookup(normalized)
        if lookup.status in ("direct", "alias"):
            return True
    except Exception:
        pass
    try:
        path = resolve_tahot_database_path()
        return bool(find_hebrew_tokens_by_strong_id(path, normalized))
    except Exception:
        return False


def _classify_strong_id(
    raw_value: str,
    vocabulary: PassageVocabulary,
    hebrew_lexicon: HebrewLexiconRepository,
) -> tuple[str, GroundingCategory]:
    """(nyelv, kategória) — nyelv: "greek" vagy "hebrew", a prefixum alapján."""
    upper = raw_value.strip().upper()
    if upper.startswith("G"):
        try:
            normalized = normalize_greek_strong_id(upper)
        except ValueError:
            return "greek", GroundingCategory.INVALID_STRONG_ID
        if normalized in vocabulary.greek_strong_ids:
            return "greek", GroundingCategory.PASSAGE_MATCH
        if _greek_strong_exists_globally(normalized):
            return "greek", GroundingCategory.GLOBAL_OTHER_PASSAGE
        return "greek", GroundingCategory.UNKNOWN
    try:
        normalized = normalize_hebrew_strong_id(upper)
    except ValueError:
        return "hebrew", GroundingCategory.INVALID_STRONG_ID
    if normalized in vocabulary.hebrew_strong_ids:
        return "hebrew", GroundingCategory.PASSAGE_MATCH
    if _hebrew_strong_exists_globally(normalized, hebrew_lexicon):
        return "hebrew", GroundingCategory.GLOBAL_OTHER_PASSAGE
    return "hebrew", GroundingCategory.UNKNOWN


_CATEGORY_MESSAGES = {
    GroundingCategory.GLOBAL_OTHER_PASSAGE: (
        "Ez a nyelvi adat létezik, de nem a jelenlegi szakasz tokenjei "
        "között található."
    ),
    GroundingCategory.UNKNOWN: (
        "Ez a nyelvi adat nem azonosítható a helyi adatbázisok alapján; "
        "ellenőrzést igényel."
    ),
    GroundingCategory.INVALID_STRONG_ID: "Érvénytelen Strong-azonosító formátum.",
}


def _build_warning(category: GroundingCategory, kind: str, value: str) -> GroundingWarning:
    return GroundingWarning(
        category=category,
        kind=kind,
        value=value,
        message=f"„{value}” — {_CATEGORY_MESSAGES[category]}",
    )


def check_original_language_grounding(text: str, igehely: str) -> list[GroundingWarning]:
    """A fő belépési pont — VALAMENNYI görög/héber szóalakot, lemmát és
    Strong-azonosítót kigyűjt a megadott szövegből, és a jelenlegi
    passzus + a globális token/lexikon infrastruktúra alapján osztályozza
    őket. Csak a NEM `PASSAGE_MATCH` eseteket adja vissza — ezek mindig
    csak FIGYELMEZTETÉSEK, sosem blokkolják a hívót."""
    if not text or not text.strip():
        return []

    vocabulary = build_passage_vocabulary(igehely)
    hebrew_lexicon = HebrewLexiconRepository()

    warnings: list[GroundingWarning] = []
    seen: set[tuple[str, str]] = set()

    for raw in _GREEK_RUN_RE.findall(text):
        nfc = unicodedata.normalize("NFC", raw)
        key = ("greek_word", nfc)
        if key in seen:
            continue
        seen.add(key)
        category = _classify_greek_word(nfc, vocabulary)
        if category is not GroundingCategory.PASSAGE_MATCH:
            warnings.append(_build_warning(category, "greek_word", nfc))

    for raw in _HEBREW_RUN_RE.findall(text):
        nfc = unicodedata.normalize("NFC", raw)
        key = ("hebrew_word", nfc)
        if key in seen:
            continue
        seen.add(key)
        category = _classify_hebrew_word(nfc, vocabulary)
        if category is not GroundingCategory.PASSAGE_MATCH:
            warnings.append(_build_warning(category, "hebrew_word", nfc))

    for raw in _GREEK_STRONG_RE.findall(text):
        key = ("greek_strong", raw.upper())
        if key in seen:
            continue
        seen.add(key)
        language, category = _classify_strong_id(raw, vocabulary, hebrew_lexicon)
        if category is not GroundingCategory.PASSAGE_MATCH:
            warnings.append(_build_warning(category, f"{language}_strong", raw.upper()))

    for raw in _HEBREW_STRONG_RE.findall(text):
        key = ("hebrew_strong", raw.upper())
        if key in seen:
            continue
        seen.add(key)
        language, category = _classify_strong_id(raw, vocabulary, hebrew_lexicon)
        if category is not GroundingCategory.PASSAGE_MATCH:
            warnings.append(_build_warning(category, f"{language}_strong", raw.upper()))

    return warnings


__all__ = [
    "GroundingCategory",
    "GroundingWarning",
    "PassageVocabulary",
    "build_passage_vocabulary",
    "check_original_language_grounding",
]
