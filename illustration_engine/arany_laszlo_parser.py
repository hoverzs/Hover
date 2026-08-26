"""Source-specific parser for Arany László's "Eredeti népmesék" (Pest:
Heckenast Gusztáv, 1862), Project Gutenberg #38852.

Structurally distinct from both prior Gutenberg sources handled by this
engine (see `jataka_parser.py`, `aesop_parser.py`), so only the genuinely
identical PG-boilerplate extraction is reused
(`gutenberg_text.extract_pg_body`):

TITLE LIST — hardcoded, not derived from CONTENTS (unlike Aesop). With
only 31 real tales (much closer to Jataka's 18/21 than to Aesop's 313),
hand-listing them is manageable — and necessary here, because this
book's "TARTALOM." listing line-wraps its longest entry across two
physical lines with a page number tacked on, which makes robust
programmatic derivation more complex than just reading the 31 titles
off the book's own table of contents once, by hand.

MATCHING IS ACCENT- AND CASE-FOLDED, NOT VERBATIM. This edition's
ALL-CAPS body headings have two confirmed, source-specific
irregularities that verbatim/whitespace-tolerant matching (Jataka's or
Aesop's approach) would each individually miss:
  - one heading keeps sentence case ("Az ARANYHAJÚ HERCZEGKISASSZONY.")
    instead of true ALL-CAPS;
  - one heading (also folk humoristic style Hungarian typesetting) drops
    the accent on a capitalized "É" ("A TÜNDERKISASSZONY..." for
    "tündér"), so a simple `.upper()` on the table-of-contents title
    would not exactly match it.
Rather than hand-tolerating each irregularity, every title (and the
whole book body, once) is passed through the shared
`hungarian_folktale_text.fold_preserving_length` (see that module for
why it's shared — a second source, Merényi László, confirmed the same
concrete need), which NFKD-decomposes each character, drops any
combining accent mark, and casefolds — deliberately LENGTH-PRESERVING
(1 codepoint in, 1 codepoint out) so that a match found in the folded
body maps directly back to the same offsets in the real, unfolded body
text used for `original_text`. `original_text` itself is always sliced
from the unfolded body, so folding never touches what is actually
stored.

The book's last tale title ("Mért haragszik a disznó a kutyára...")
also wraps across two physical body lines — handled generically by
joining each title's words with a flexible whitespace separator instead
of assuming a single line, rather than special-casing that one title.

EXCLUDED SECTIONS (structural, not taste-based — see the audit for the
reasoning): after the 31 numbered/titled narrative tales, the book has
a "Találós mesék" section (54 numbered items, each a 2-5 line riddle
verse with NO title of its own) and a "Csali-mesék" section (5 numbered
items, each a very short trick/nonsense verse, also untitled), followed
by a "Megfejtések" answer key for the riddles. None of these have the
(title + narrative paragraph) shape the rest of this engine's `stories`
table models, so none of them are imported — this mirrors excluding
Aesop's FOOTNOTES/INDEX and Jataka's Foreword as structurally distinct
back matter, not a judgment about their literary worth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from illustration_engine.gutenberg_text import (
    GutenbergBoilerplateError,
    collapse_blank_lines,
    extract_pg_body,
)
from illustration_engine.hungarian_folktale_text import fold_preserving_length, heading_pattern


SOURCE_CODE = "PG_ARANY_LASZLO_EREDETI_NEPMESEK"

# Order and wording taken verbatim from this edition's own "TARTALOM."
# listing (proper case, as printed there — NOT the shouty body heading
# case, which is normalized away by folding anyway).
TALE_TITLES: tuple[str, ...] = (
    "A vak király",
    "A boltos három lyánya",
    "A czigány fiú",
    "Ráadó és Anyicska",
    "Az aranyhajú herczegkisasszony",
    "Az őzike",
    "A veres tehén",
    "A tündérkisasszony és a czigánylyány",
    "Az ördög-szerető",
    "Jankó és a három elátkozott királykisasszony",
    "Az ördög és a két lyány",
    "A kis malacz és a farkasok",
    "Zsuzska és az ördög",
    "Fehérlófia",
    "A nyelves királykisasszony",
    "Gagyi gazda",
    "Babszem Jankó",
    "Dongó meg Mohácsi",
    "A szomorú királykisasszony",
    "A macska és az egér",
    "A farkas-tanya",
    "Panczimanczi",
    "A hólyag, szalmaszál és a tüzes üszök",
    "A kis gömböcz",
    "Farkas-barkas",
    "A kakaska és a jérczike",
    "A két koszorú",
    "A kóró és a kis madár",
    "A kis ködmön",
    "Iczinke-piczinke",
    "Mért haragszik a disznó a kutyára, a kutya a macskára, a macska az egérre",
)

# Marks the end of the last real tale — everything from here to the PG
# end marker (Találós mesék / Csali-mesék / Megfejtések) is excluded.
BACK_MATTER_MARKER = "Találós mesék"


@dataclass(frozen=True)
class ParsedAranyTale:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class AranyLaszloParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


def parse_arany_laszlo_text(raw_text: str) -> tuple[ParsedAranyTale, ...]:
    """Parse the full raw PG #38852 plain-text into individual tales.

    Raises `AranyLaszloParseError` if the PG markers or any title in
    `TALE_TITLES` cannot be found, in order, as a standalone body
    heading — parsing never silently returns a partial/misaligned result.
    """
    try:
        body = extract_pg_body(raw_text, source_label=SOURCE_CODE)
    except GutenbergBoilerplateError as exc:
        raise AranyLaszloParseError(str(exc)) from exc

    folded_body = fold_preserving_length(body)

    header_matches: list[re.Match[str]] = []
    search_from = 0
    for title in TALE_TITLES:
        pattern = heading_pattern(title)
        match = pattern.search(folded_body, search_from)
        if match is None:
            raise AranyLaszloParseError(
                f"{SOURCE_CODE}: expected tale heading not found in order: "
                f"{title!r} (searching from offset {search_from})"
            )
        header_matches.append(match)
        search_from = match.end()

    back_matter_pattern = heading_pattern(BACK_MATTER_MARKER)
    back_matter_match = back_matter_pattern.search(folded_body, header_matches[-1].end())
    if back_matter_match is None:
        raise AranyLaszloParseError(
            f"{SOURCE_CODE}: expected back-matter marker {BACK_MATTER_MARKER!r} "
            "not found after the last tale"
        )

    tales: list[ParsedAranyTale] = []
    for index, (title, header_match) in enumerate(zip(TALE_TITLES, header_matches)):
        text_start = header_match.end()
        text_end = (
            header_matches[index + 1].start()
            if index + 1 < len(header_matches)
            else back_matter_match.start()
        )
        cleaned = collapse_blank_lines(body[text_start:text_end]).strip()
        if not cleaned:
            raise AranyLaszloParseError(f"{SOURCE_CODE}: tale {title!r} is empty after cleaning")
        position = index + 1
        tales.append(
            ParsedAranyTale(
                canonical_key=f"{position:02d}",
                external_ref=str(position),
                title_original=title,
                original_text=cleaned,
            )
        )

    return tuple(tales)


def parse_arany_laszlo_file(path: str | Path) -> tuple[ParsedAranyTale, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_arany_laszlo_text(raw_text)


__all__ = [
    "BACK_MATTER_MARKER",
    "SOURCE_CODE",
    "TALE_TITLES",
    "AranyLaszloParseError",
    "ParsedAranyTale",
    "parse_arany_laszlo_file",
    "parse_arany_laszlo_text",
]
