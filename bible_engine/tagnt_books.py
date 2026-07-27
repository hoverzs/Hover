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


def _normalize_reference_alias(reference: str) -> str:
    text = (reference or "").strip()
    for alias, replacement in _REFERENCE_ALIASES.items():
        if re.match(rf"^{re.escape(alias)}\b", text, flags=re.IGNORECASE):
            return replacement + text[len(alias) :]
    return reference
