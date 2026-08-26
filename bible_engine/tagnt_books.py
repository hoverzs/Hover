from __future__ import annotations

import re

from ruf_bible_service import parse_bible_reference


RUF_TO_TAGNT_BOOK_CODES: dict[str, str] = {
    "MAT": "Mat",
    "MRK": "Mrk",
    "LUK": "Luk",
    "JHN": "Jhn",
    "ACT": "Act",
    "ROM": "Rom",
    "1CO": "1Co",
    "2CO": "2Co",
    "GAL": "Gal",
    "EPH": "Eph",
    "PHP": "Php",
    "COL": "Col",
    "1TH": "1Th",
    "2TH": "2Th",
    "1TI": "1Ti",
    "2TI": "2Ti",
    "TIT": "Tit",
    "PHM": "Phm",
    "HEB": "Heb",
    "JAS": "Jas",
    "1PE": "1Pe",
    "2PE": "2Pe",
    "1JN": "1Jn",
    "2JN": "2Jn",
    "3JN": "3Jn",
    "JUD": "Jud",
    "REV": "Rev",
}

TAGNT_NEW_TESTAMENT_BOOK_CODES: tuple[str, ...] = tuple(
    RUF_TO_TAGNT_BOOK_CODES.values()
)
NEW_TESTAMENT_RUF_CODES: frozenset[str] = frozenset(RUF_TO_TAGNT_BOOK_CODES)

_REFERENCE_ALIASES: dict[str, str] = {
    "1thessz": "1Thess",
    "2thessz": "2Thess",
}

# OSIS/English book id → Hungarian RUF abbreviation used by parse_bible_reference.
_CANONICAL_BOOK_TO_RUF_ABBR: dict[str, str] = {
    "Matthew": "Mt",
    "Mark": "Mk",
    "Luke": "Lk",
    "John": "Jn",
    "Acts": "ApCsel",
    "Romans": "Róm",
    "1Corinthians": "1Kor",
    "2Corinthians": "2Kor",
    "Galatians": "Gal",
    "Ephesians": "Ef",
    "Philippians": "Fil",
    "Colossians": "Kol",
    "1Thessalonians": "1Thess",
    "2Thessalonians": "2Thess",
    "1Timothy": "1Tim",
    "2Timothy": "2Tim",
    "Titus": "Tit",
    "Philemon": "Filem",
    "Hebrews": "Zsid",
    "James": "Jak",
    "1Peter": "1Pt",
    "2Peter": "2Pt",
    "1John": "1Jn",
    "2John": "2Jn",
    "3John": "3Jn",
    "Jude": "Júd",
    "Revelation": "Jel",
}


def tagnt_book_code_from_ruf_code(ruf_code: str) -> str | None:
    return RUF_TO_TAGNT_BOOK_CODES.get((ruf_code or "").upper())


def tagnt_book_code_from_reference(reference: str) -> str:
    parsed = parse_tagnt_bible_reference(reference)
    code = tagnt_book_code_from_ruf_code(parsed.book.code)
    if code is None:
        raise ValueError(f"Reference is not a TAGNT New Testament book: {reference!r}")
    return code


def parse_tagnt_bible_reference(reference: str):
    normalized = _normalize_reference_alias(reference)
    return parse_bible_reference(normalized)


def try_normalize_canonical_dotted_reference(reference: str) -> str | None:
    """Convert ``Luke.10.25-37`` / ``John.4.1-42`` into RUF-style ``Lk 10,25-37``.

    Returns None when the input is not a dotted canonical/OSIS form.
    """
    text = (reference or "").strip().replace("–", "-").replace("—", "-")
    match = re.match(
        r"^([A-Za-z][A-Za-z0-9]+)\.(\d+)\.(\d+)(?:-(\d+)(?:\.(\d+))?)?\s*$",
        text,
    )
    if not match:
        return None
    book_token, chapter_s, start_s, end_or_ch, end_vs = match.groups()
    abbr = _CANONICAL_BOOK_TO_RUF_ABBR.get(book_token) or _CANONICAL_BOOK_TO_RUF_ABBR.get(
        book_token[:1].upper() + book_token[1:]
    )
    if abbr is None:
        # Title-case lookup (john → John) via canonical map keys.
        titled = book_token[:1].upper() + book_token[1:]
        abbr = _CANONICAL_BOOK_TO_RUF_ABBR.get(titled)
    if abbr is None:
        return None
    chapter = int(chapter_s)
    start = int(start_s)
    if end_or_ch is None:
        return f"{abbr} {chapter},{start}"
    if end_vs is None:
        # Same-chapter span: Book.ch.start-end
        end = int(end_or_ch)
        if end == start:
            return f"{abbr} {chapter},{start}"
        return f"{abbr} {chapter},{start}-{end}"
    # Cross-chapter: Book.ch.vs-ch2.vs2 — greek pipeline still rejects later.
    end_chapter = int(end_or_ch)
    end_verse = int(end_vs)
    return f"{abbr} {chapter},{start}-{end_chapter},{end_verse}"


def _normalize_reference_alias(reference: str) -> str:
    text = (reference or "").strip()
    dotted = try_normalize_canonical_dotted_reference(text)
    if dotted:
        return dotted
    for alias, replacement in _REFERENCE_ALIASES.items():
        if re.match(rf"^{re.escape(alias)}\b", text, flags=re.IGNORECASE):
            return replacement + text[len(alias) :]
    return reference