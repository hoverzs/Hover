from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


TAGNT_HEADERS: tuple[str, ...] = (
    "Word & Type",
    "Greek",
    "English translation",
    "dStrongs = Grammar",
    "Dictionary form =  Gloss",
    "editions",
    "Meaning variants",
    "Spelling variants",
    "Spanish translation",
    "Sub-meaning",
    "Conjoin word",
    "sStrong+Instance",
    "Alt Strongs",
    "",
    "",
    "",
    "",
)
TAGNT_ACT_REV_HEADERS = TAGNT_HEADERS

_WORD_AND_TYPE_RE = re.compile(
    r"^(?P<book>[1-3]?[A-Za-z]{3})\."
    r"(?P<chapter>\d+)\."
    r"(?P<verse>\d+)#"
    r"(?P<word_index>\d+)="
    r"(?P<edition_flags>.+)$"
)
_TRAILING_TRANSLITERATION_RE = re.compile(r"\s+\([^)]*\)\s*$")


@dataclass(frozen=True)
class GreekToken:
    book: str
    chapter: int
    verse: int
    word_index: int
    greek_form: str
    lemma: str
    morph_code: str
    strong_id: str
    edition_flags: str


def parse_tagnt_row(
    row: str, headers: Sequence[str] = TAGNT_HEADERS
) -> GreekToken:
    fields = next(csv.reader([row], delimiter="\t"))
    columns = _indexed_headers(headers)

    word_and_type = _field(fields, columns, "Word & Type")
    reference = _parse_word_and_type(word_and_type)

    strong_and_morph = _field(fields, columns, "dStrongs = Grammar")
    strong_id, morph_code = _split_required(
        strong_and_morph, "=", "dStrongs = Grammar"
    )

    lemma_and_gloss = _field(fields, columns, "Dictionary form =  Gloss")
    lemma, _gloss = _split_required(
        lemma_and_gloss, "=", "Dictionary form =  Gloss"
    )

    return GreekToken(
        book=reference["book"],
        chapter=int(reference["chapter"]),
        verse=int(reference["verse"]),
        word_index=int(reference["word_index"]),
        greek_form=_display_greek(_field(fields, columns, "Greek")),
        lemma=unicodedata.normalize("NFC", lemma.strip()),
        morph_code=morph_code.strip(),
        strong_id=strong_id.strip(),
        edition_flags=reference["edition_flags"],
    )


def get_verse_tokens(
    source_path: str | Path,
    book: str,
    chapter: int,
    verse: int,
) -> list[GreekToken]:
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"TAGNT source file not found: {path}")

    tokens: list[GreekToken] = []
    prefix = f"{book}.{chapter}.{verse}#"

    with path.open("r", encoding="utf-8") as source:
        for raw_line in source:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("Word & Type"):
                continue
            if not line.startswith(prefix):
                continue
            tokens.append(parse_tagnt_row(line))

    return sorted(tokens, key=lambda token: token.word_index)


def _indexed_headers(headers: Sequence[str]) -> Mapping[str, int]:
    columns: dict[str, int] = {}
    for index, header in enumerate(headers):
        name = header.strip()
        if name and name not in columns:
            columns[name] = index

    required = (
        "Word & Type",
        "Greek",
        "dStrongs = Grammar",
        "Dictionary form =  Gloss",
    )
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValueError(f"Missing TAGNT header field(s): {', '.join(missing)}")
    return columns


def _field(fields: Sequence[str], columns: Mapping[str, int], name: str) -> str:
    index = columns[name]
    if index >= len(fields):
        raise ValueError(f"Missing TAGNT field: {name}")
    value = fields[index].strip()
    if not value:
        raise ValueError(f"Empty TAGNT field: {name}")
    return value


def _parse_word_and_type(value: str) -> Mapping[str, str]:
    match = _WORD_AND_TYPE_RE.match(value)
    if not match:
        raise ValueError(f"Invalid TAGNT Word & Type field: {value!r}")
    return match.groupdict()


def _split_required(value: str, separator: str, field_name: str) -> tuple[str, str]:
    left, separator_found, right = value.partition(separator)
    if not separator_found or not left.strip() or not right.strip():
        raise ValueError(f"Invalid TAGNT {field_name} field: {value!r}")
    return left, right


def _display_greek(value: str) -> str:
    greek = _TRAILING_TRANSLITERATION_RE.sub("", value).strip()
    if not greek:
        raise ValueError(f"Invalid TAGNT Greek field: {value!r}")
    return unicodedata.normalize("NFC", greek)
