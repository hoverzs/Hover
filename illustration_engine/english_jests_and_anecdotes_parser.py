"""Source-specific parser for "English Jests and Anecdotes, Collected
from Various Sources" (part of the "Nuggets for Travellers" series,
Edinburgh: William Paterson, published c. 1880), Project Gutenberg
#49370.

BIBLIOGRAPHIC FACTS (verified, not assumed):
- No individual author or compiler is named anywhere in the book or on
  its title page — PG catalogues it as "Various". The Internet Archive
  scan (archive.org/details/englishjestsanec00edin, from which this PG
  e-text derives) records the publisher as "Edinburgh: William
  Paterson" and an estimated publication year of 1880 ("1880z" — an
  approximate cataloguing date, no exact year is printed in the book
  itself). At 145+ years old and with no identifiable individual
  rights-holder, this is unambiguously public domain under any US/EU
  calculation.
- PG e-text: digitized from Internet Archive scans by Chris Curnow,
  Elisa, and the PGDP Distributed Proofreading Team — a clean,
  volunteer transcription with only minor, explicitly documented
  typo corrections (see the file's own "Transcriber's Note").

STRUCTURE CONFIRMED BY DIRECT INSPECTION:
- The story region runs from the standalone heading "ENGLISH
  ANECDOTES." to the standalone closer "THE END." (both occur exactly
  once in the body). Everything before is front matter (series
  title page, "Nuggets for Travellers" companion-volume list,
  publisher imprint); everything after is back matter (a printer's
  colophon line and a "NOTES" section of bibliographic footnotes).
- Within that region, every one of the 765 individual units follows
  the SAME two-part shape: a standalone, ALL-CAPS title line, followed
  by one block-quote-free blank line, followed by the anecdote's own
  prose (which may itself contain several blank-line-separated
  paragraphs, e.g. for anecdotes built around a longer dialogue).
  Unlike `book_of_300_anecdotes_parser.py`'s source, EVERY unit here
  has a genuine title — there are no untitled paragraphs, so no
  derived-title fallback is needed.
- 13 titles repeat (2-3 times each — e.g. "CHARLES II.", "SHERIDAN.",
  "FOOTE."): the book groups multiple, genuinely separate anecdotes
  about the same recurring person under the same heading text. This is
  expected, not a parsing bug — `canonical_key`/`external_ref` carry
  the per-story identity positionally, exactly as in
  `baldwin_parser.py` (which has the same flat, un-categorized
  structure, unlike `book_of_300_anecdotes_parser.py`'s
  category-grouped one).
- A handful of anecdotes carry a single-letter bracketed footnote
  marker (`[A]` .. `[G]`) pointing to a bibliographic annotation in the
  excluded back-matter "NOTES" section (e.g. citing the specific book
  and year a quoted phrase came from). Since that back matter is
  deliberately excluded, these markers are stripped as a dangling,
  non-content transcription artifact — the same rationale as stripping
  `[Illustration]` tags in `gutenberg_text.py`.

GENRE/STRUCTURE AUDIT — NO SAFE GENERAL RULE, MANUAL EXCLUSION LIST
USED (same pattern as `book_of_300_anecdotes_parser.py`'s
`_MANUAL_CONTINUATION_PREFIXES`, applied here to EXCLUSION rather than
merging):
Three candidate deterministic signals were tried and each rejected
before falling back to a manual list:
  1. Heading keywords ("PUN", "BON-MOT", "EPITAPH", "EPIGRAM",
     "INSCRIPTION", "VERSES") — REJECTED: the overwhelming majority of
     "PUN"/"BON-MOT"-titled units (e.g. "PUNNING FLATTERY.",
     "AGRICULTURAL PUN.") are genuine narrative anecdotes built around
     a pun — the heading names the joke's mechanism, not its genre.
  2. Absence of any curly quotation mark (no reported dialogue) — 44
     of 765 units have none, but manual reading showed the large
     majority of those are still genuine narrative (a described scene
     or habitual character trait with a witty payoff, e.g. "PENNANT'S
     ANTIPATHY TO WIGS.", "CAT O' NINE TAILS.") — REJECTED as a filter,
     though useful as a candidate-narrowing tool for manual review.
  3. Length threshold — REJECTED: confirmed non-narrative units range
     from 61 to 970 characters, overlapping heavily with the "ideal"
     200-1500 band.
Every one of the 70 units under 200 characters, and every one of the
44 units containing no curly quotation mark (lengths 61-1182 chars —
the two candidate pools most likely to contain non-narrative content),
was read in full. This is a thorough, evidence-based sample, not an
exhaustive line-by-line certification of all 765 units — a small
number of additional borderline non-narrative items may remain
unflagged in the untitled majority that had at least one signal of
narrative structure. Exactly 7 units were confirmed, on individual
reading, to have NO narrative frame at all (no specific person/type
performing or saying something on a specific occasion) — either bare
quoted verse ("EPITAPH ON PROFESSOR BARNES...", "EPIGRAM."), a
generic present-tense gnomic one-liner ("KITES.", "NATIONAL
PARADOXES."), or an argumentative/reflective essay passage with no
narrated incident at all ("CUT DOWN AND CUT UP.", "TAXES.", "SIGNS
AND TOKENS."). These are excluded via `_MANUAL_NON_NARRATIVE_TITLES`,
matched against exact heading text, with a fail-loud check (parsing
raises if any listed title is not found in the source) so the
override cannot silently rot if the source text ever changes.
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


SOURCE_CODE = "PG_ENGLISH_JESTS_AND_ANECDOTES"

_STORY_REGION_START_HEADING = "ENGLISH ANECDOTES."
_STORY_REGION_END_HEADING = "THE END."

_FOOTNOTE_MARKER_RE = re.compile(r"\[[A-Z]\]")

_HEADING_MIN_LEN = 2
_HEADING_MAX_LEN = 90


def _is_heading_block(block: str) -> bool:
    """A story title: a single line, reasonably short, where every
    alphabetic character is uppercase (covers plain ASCII titles as
    well as the 13 titles that also contain curly quotes, `?`/`!`, or
    an accented capital like Æ/É — checking case rather than
    enumerating an exact punctuation allowlist avoids the false
    negatives a fixed character class produced during development)."""
    if "\n" in block:
        return False
    if not (_HEADING_MIN_LEN <= len(block) <= _HEADING_MAX_LEN):
        return False
    letters = [c for c in block if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)

# Manually verified against this exact edition (see module docstring for
# the audit that produced this list, and why no general rule could
# safely replace it). A title not found means either the source text
# changed or the heading-detection regex broke — fail loudly rather
# than silently importing a different set of stories.
_MANUAL_NON_NARRATIVE_TITLES: tuple[str, ...] = (
    "EPITAPH ON PROFESSOR BARNES, A MAN OF WEAK JUDGMENT, BUT HAPPY MEMORY.",
    "EPIGRAM.",
    "KITES.",
    "NATIONAL PARADOXES.",
    "CUT DOWN AND CUT UP.",
    "TAXES.",
    "SIGNS AND TOKENS.",
)

_EXPECTED_TOTAL_HEADINGS = 765
_EXPECTED_NARRATIVE_STORY_COUNT = _EXPECTED_TOTAL_HEADINGS - len(_MANUAL_NON_NARRATIVE_TITLES)


@dataclass(frozen=True)
class ParsedEnglishJestsStory:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class EnglishJestsParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


def parse_english_jests_text(raw_text: str) -> tuple[ParsedEnglishJestsStory, ...]:
    """Parse the full raw PG #49370 plain-text into individual narrative
    anecdotes (the 7 confirmed non-narrative units are excluded — see
    module docstring).

    Raises `EnglishJestsParseError` if the PG markers, the story-region
    boundaries, the expected total heading count, or any manual
    exclusion title don't match — parsing never silently returns a
    partial or misaligned result.
    """
    try:
        body = extract_pg_body(raw_text, source_label=SOURCE_CODE)
    except GutenbergBoilerplateError as exc:
        raise EnglishJestsParseError(str(exc)) from exc

    body = collapse_blank_lines(body)
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]

    try:
        start_idx = blocks.index(_STORY_REGION_START_HEADING)
    except ValueError as exc:
        raise EnglishJestsParseError(
            f"{SOURCE_CODE}: could not locate the {_STORY_REGION_START_HEADING!r} heading"
        ) from exc
    try:
        end_idx = blocks.index(_STORY_REGION_END_HEADING)
    except ValueError as exc:
        raise EnglishJestsParseError(
            f"{SOURCE_CODE}: could not locate the {_STORY_REGION_END_HEADING!r} closer"
        ) from exc
    if end_idx <= start_idx:
        raise EnglishJestsParseError(
            f"{SOURCE_CODE}: {_STORY_REGION_END_HEADING!r} appears before "
            f"{_STORY_REGION_START_HEADING!r}"
        )

    region_blocks = blocks[start_idx + 1 : end_idx]
    if not region_blocks or not _is_heading_block(region_blocks[0]):
        raise EnglishJestsParseError(
            f"{SOURCE_CODE}: story region does not begin with a title heading"
        )

    raw_pairs: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_body_blocks: list[str] = []
    for block in region_blocks:
        if _is_heading_block(block):
            if current_heading is not None:
                raw_pairs.append((current_heading, "\n\n".join(current_body_blocks)))
            current_heading = block
            current_body_blocks = []
        else:
            current_body_blocks.append(block)
    if current_heading is not None:
        raw_pairs.append((current_heading, "\n\n".join(current_body_blocks)))

    if len(raw_pairs) != _EXPECTED_TOTAL_HEADINGS:
        raise EnglishJestsParseError(
            f"{SOURCE_CODE}: expected {_EXPECTED_TOTAL_HEADINGS} total headings, "
            f"found {len(raw_pairs)}"
        )

    unused_exclusions = set(_MANUAL_NON_NARRATIVE_TITLES)
    stories: list[ParsedEnglishJestsStory] = []
    for heading, raw_text_block in raw_pairs:
        if heading in unused_exclusions:
            unused_exclusions.discard(heading)
            continue

        cleaned = _FOOTNOTE_MARKER_RE.sub("", raw_text_block)
        cleaned = collapse_blank_lines(cleaned).strip()
        if not cleaned:
            raise EnglishJestsParseError(f"{SOURCE_CODE}: story {heading!r} is empty after cleaning")

        position = len(stories) + 1
        stories.append(
            ParsedEnglishJestsStory(
                canonical_key=f"{position:03d}",
                external_ref=str(position),
                title_original=heading,
                original_text=cleaned,
            )
        )

    if unused_exclusions:
        raise EnglishJestsParseError(
            f"{SOURCE_CODE}: manual non-narrative exclusion title(s) never matched: "
            f"{sorted(unused_exclusions)!r}"
        )

    if len(stories) != _EXPECTED_NARRATIVE_STORY_COUNT:
        raise EnglishJestsParseError(
            f"{SOURCE_CODE}: expected {_EXPECTED_NARRATIVE_STORY_COUNT} narrative stories "
            f"after exclusions, found {len(stories)}"
        )

    return tuple(stories)


def parse_english_jests_file(path: str | Path) -> tuple[ParsedEnglishJestsStory, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_english_jests_text(raw_text)


__all__ = [
    "SOURCE_CODE",
    "EnglishJestsParseError",
    "ParsedEnglishJestsStory",
    "parse_english_jests_file",
    "parse_english_jests_text",
]
