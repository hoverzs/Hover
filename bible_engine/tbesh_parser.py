from __future__ import annotations

import csv
import re
from dataclasses import dataclass


_HEBREW_STRONG_RE = re.compile(r"H\d{4}[A-Z]?", re.IGNORECASE)

TBESH_HEADERS = (
    "eStrong#",
    "dStrong",
    "uStrong",
    "Hebrew",
    "Transliteration",
    "Morph",
    "Gloss",
    "Meaning",
)


@dataclass(frozen=True)
class HebrewLexiconEntry:
    estrong: str
    dstrong: str
    ustrong: str
    hebrew: str
    transliteration: str
    morph: str
    gloss: str
    meaning: str
    source_name: str = "STEPBible TBESH"

    @property
    def strong_ids(self) -> tuple[str, ...]:
        strong_ids: list[str] = []
        for item in (self.estrong, self.dstrong, self.ustrong):
            strong_ids.extend(match.group(0).upper() for match in _HEBREW_STRONG_RE.finditer(item or ""))
        return tuple(dict.fromkeys(strong_ids))


def parse_tbesh_row(row: str) -> HebrewLexiconEntry:
    fields = next(csv.reader([row.rstrip("\n")], delimiter="\t"))
    if len(fields) < len(TBESH_HEADERS):
        raise ValueError(f"Invalid TBESH row: expected {len(TBESH_HEADERS)} columns")
    return HebrewLexiconEntry(
        estrong=fields[0].strip(),
        dstrong=fields[1].strip(),
        ustrong=fields[2].strip(),
        hebrew=fields[3].strip(),
        transliteration=fields[4].strip(),
        morph=fields[5].strip(),
        gloss=fields[6].strip(),
        meaning=fields[7].strip(),
    )


def parse_tbesh_rows(text: str) -> list[HebrewLexiconEntry]:
    entries: list[HebrewLexiconEntry] = []
    data_started = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("eStrong#"):
            data_started = True
            continue
        if not data_started:
            continue
        if line.startswith("$") or line.startswith("="):
            continue
        try:
            entries.append(parse_tbesh_row(line))
        except ValueError:
            continue
    return entries
