"""Source-specific parser for Merényi László's "Eredeti népmesék", 1–2.
rész (Pest: Heckenast Gusztáv, 1861), Project Gutenberg #39419 (1. rész)
and #39386 (2. rész).

Combines two already-proven patterns rather than inventing a new one:

- The (book spec + one shared parse function for N sibling books)
  structure from `jataka_parser.py` — this book, like the Jataka pair,
  comes as two separate PG editions of the same collection.
- The accent-/case-fold heading matching from `hungarian_folktale_text`
  (shared with `arany_laszlo_parser.py`) — this edition (produced by the
  same "Albert László" PG transcription project, same era) has the same
  kind of ALL-CAPS-heading irregularities.

ONE NEW IRREGULARITY, not seen in Arany's book, forced a small addition
to the SHARED `hungarian_folktale_text.heading_pattern` (not a local
hack): "1. rész"'s seventh tale heading is fused to a footnote-reference
bracket — "A SZEGÉNY EMBER ÉS A KOMÁJA.[101]" — where "[101]" points to
a translator's note about the tale's relation to another named folklore
collection (a genuine period editorial aside, not a modern annotation —
left in place in `original_text`, same treatment as Arany's inline
glossary footnote). A first, footnote-blind pass over the raw text
under-counted this book's tales by one; the fix was cross-checking
every book's own back-of-book "TARTALOM."/"Néptalányok." listing count,
which is why `MERENYI_1_RESZ`/`MERENYI_2_RESZ` below carry that exact,
manually verified count as their source of truth, not a first-pass
heading scan.

STRUCTURAL DIFFERENCE BETWEEN THE TWO VOLUMES: "2. rész" (13 tales) has
no riddle section at all — its back matter is a "TARTALOM." listing
straight after the last tale. "1. rész" (10 tales) has a "Néptalányok."
(folk riddles) section — structurally the same kind of untitled,
2-5-line numbered-verse content as Arany's "Találós mesék"/"Csali-mesék"
— followed by a "Felóldás." (answer key) and only then its own
"TARTALOM.". Both volumes are therefore given their own
`back_matter_marker` (the marker that immediately follows the LAST real
tale) rather than assuming one fixed section name — "TARTALOM." for
2. rész, "Néptalányok." for 1. rész — excluded for the identical
structural reason as Arany's riddle sections and Aesop's FOOTNOTES/INDEX:
no title + narrative-paragraph shape, not a judgment of literary worth.
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


# Both volumes carry the printer's own colophon line ("Wigand K. F.
# könyvnyomdája Pozsonyban.", italicized with PG's `_..._` convention)
# immediately before their final "TARTALOM."/"Néptalányok." back matter.
# In "1. rész" that already falls inside the excluded back-matter region
# (the "Néptalányok" riddle section comes first); in "2. rész" — which
# has no riddle section — it lands right after the last tale's narrative
# text instead, so it must be stripped explicitly. It is not narrative
# content in either case (a printing-house imprint, not the collector's
# or the tale's own words), so stripping it is a structural exclusion,
# consistent with dropping PG's own boilerplate.
_TRAILING_PRINTER_COLOPHON_RE = re.compile(
    r"\n+_Wigand K\. F\. könyvnyomdája Pozsonyban\.?_\s*\Z"
)


@dataclass(frozen=True)
class MerenyiBookSpec:
    source_code: str
    book_title: str
    tale_titles: tuple[str, ...]
    back_matter_marker: str


@dataclass(frozen=True)
class ParsedMerenyiTale:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class MerenyiLaszloParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


MERENYI_1_RESZ = MerenyiBookSpec(
    source_code="PG_MERENYI_LASZLO_EREDETI_NEPMESEK_1",
    book_title="Eredeti népmesék (1. rész)",
    tale_titles=(
        "A kigyóbőr",
        "A szárdiniai király fia",
        "Vízi Péter és Vízi Pál",
        "Kilinkó",
        "A kerek kő",
        "A farkas és a róka komasága",
        "A szegény ember és a komája",
        "A vén király",
        "A medve és a farkas",
        "Bolond Jankó",
    ),
    back_matter_marker="Néptalányok",
)

MERENYI_2_RESZ = MerenyiBookSpec(
    source_code="PG_MERENYI_LASZLO_EREDETI_NEPMESEK_2",
    book_title="Eredeti népmesék (2. rész)",
    tale_titles=(
        "A hamupipőke",
        "A nádszál kisasszony",
        "Az aranyhajú kertészbojtár",
        "A csodaszörny",
        "A lidércz",
        "Prücsök János",
        "Patkós Körmöndiné",
        "A mostoha leány s az édes leány",
        "A szegény ember és az obsitos",
        "A terhes asszony",
        "A vén leány",
        "A boszorkány",
        "Bolond Jankó",
    ),
    back_matter_marker="TARTALOM",
)


def parse_merenyi_laszlo_text(
    raw_text: str, spec: MerenyiBookSpec
) -> tuple[ParsedMerenyiTale, ...]:
    """Parse the full raw PG plain-text of one Merényi László volume into
    tales. Raises `MerenyiLaszloParseError` if the PG markers or any
    title in `spec.tale_titles` cannot be found, in order, as a
    standalone body heading — parsing never silently returns a
    partial/misaligned result."""
    try:
        body = extract_pg_body(raw_text, source_label=spec.source_code)
    except GutenbergBoilerplateError as exc:
        raise MerenyiLaszloParseError(str(exc)) from exc

    folded_body = fold_preserving_length(body)

    header_matches: list[re.Match[str]] = []
    search_from = 0
    for title in spec.tale_titles:
        pattern = heading_pattern(title)
        match = pattern.search(folded_body, search_from)
        if match is None:
            raise MerenyiLaszloParseError(
                f"{spec.source_code}: expected tale heading not found in order: "
                f"{title!r} (searching from offset {search_from})"
            )
        header_matches.append(match)
        search_from = match.end()

    back_matter_pattern = heading_pattern(spec.back_matter_marker)
    back_matter_match = back_matter_pattern.search(folded_body, header_matches[-1].end())
    if back_matter_match is None:
        raise MerenyiLaszloParseError(
            f"{spec.source_code}: expected back-matter marker "
            f"{spec.back_matter_marker!r} not found after the last tale"
        )

    tales: list[ParsedMerenyiTale] = []
    for index, (title, header_match) in enumerate(zip(spec.tale_titles, header_matches)):
        text_start = header_match.end()
        text_end = (
            header_matches[index + 1].start()
            if index + 1 < len(header_matches)
            else back_matter_match.start()
        )
        raw_tale_text = _TRAILING_PRINTER_COLOPHON_RE.sub("", body[text_start:text_end])
        cleaned = collapse_blank_lines(raw_tale_text).strip()
        if not cleaned:
            raise MerenyiLaszloParseError(
                f"{spec.source_code}: tale {title!r} is empty after cleaning"
            )
        position = index + 1
        tales.append(
            ParsedMerenyiTale(
                canonical_key=f"{position:02d}",
                external_ref=str(position),
                title_original=title,
                original_text=cleaned,
            )
        )

    return tuple(tales)


def parse_merenyi_laszlo_file(
    path: str | Path, spec: MerenyiBookSpec
) -> tuple[ParsedMerenyiTale, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_merenyi_laszlo_text(raw_text, spec)


__all__ = [
    "MERENYI_1_RESZ",
    "MERENYI_2_RESZ",
    "MerenyiBookSpec",
    "MerenyiLaszloParseError",
    "ParsedMerenyiTale",
    "parse_merenyi_laszlo_file",
    "parse_merenyi_laszlo_text",
]
