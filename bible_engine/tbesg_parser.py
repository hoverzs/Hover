from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_FIELD_COUNT = 8
_GREEK_STRONG_RE = re.compile(r"^G(?P<number>\d{1,5})(?P<suffix>[A-Z]?)$")
_MAX_GREEK_STRONG_NUMBER = 21502


@dataclass(frozen=True)
class GreekLexiconEntry:
    strong_id: str
    dstrong_id: str | None
    ustrong_id: str | None
    greek: str
    transliteration: str | None
    morph: str | None
    gloss: str | None
    meaning_raw: str | None


def parse_tbesg_line(line: str) -> GreekLexiconEntry:
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) != _FIELD_COUNT:
        raise ValueError(
            f"Invalid TBESG record: expected {_FIELD_COUNT} tab-separated fields, "
            f"got {len(fields)}."
        )

    (
        strong_id,
        dstrong_id,
        ustrong_id,
        greek,
        transliteration,
        morph,
        gloss,
        meaning_raw,
    ) = fields

    if not strong_id.strip():
        raise ValueError("Invalid TBESG record: missing eStrong value.")
    return GreekLexiconEntry(
        strong_id=normalize_greek_strong_id(strong_id),
        dstrong_id=_optional(dstrong_id),
        ustrong_id=_optional(ustrong_id),
        greek=unicodedata.normalize("NFC", greek.strip()),
        transliteration=_optional(transliteration),
        morph=_optional(morph),
        gloss=_optional(gloss),
        meaning_raw=_optional_raw(meaning_raw),
    )


def normalize_greek_strong_id(value: str) -> str:
    raw = (value or "").strip().upper()
    if raw.startswith("H"):
        raise ValueError(f"Invalid Greek Strong identifier: Hebrew id is not supported: {value!r}.")

    match = _GREEK_STRONG_RE.fullmatch(raw)
    if not match:
        raise ValueError(f"Invalid Greek Strong identifier: {value!r}.")

    number = int(match.group("number"))
    if number < 1 or number > _MAX_GREEK_STRONG_NUMBER:
        raise ValueError(f"Invalid Greek Strong identifier range: {value!r}.")

    width = 4 if number < 10000 else len(str(number))
    return f"G{number:0{width}d}{match.group('suffix')}"


def _optional(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _optional_raw(value: str) -> str | None:
    return value if value else None
