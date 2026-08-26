"""Source-specific parser for "The Gulistan" (Rose Garden) of Sa'di,
translated by James Ross (1823), as printed in "The Persian Literature,
Comprising The Shah Nameh, The Rubaiyat, The Divan, and The Gulistan,
Volume 2" (Revised Edition, 1900), Project Gutenberg #13060.

STRUCTURE CONFIRMED BY DIRECT INSPECTION (not assumed):
- Despite the umbrella title, this specific PG volume contains ONLY the
  Gulistan — no Shah Nameh/Rubaiyat/Divan content is present in the
  file (verified: `CHAPTER I`..`CHAPTER VIII` span the entire body
  between the PG START and END markers).
- The Gulistan's 8 chapters each restart a bare Roman-numeral counter
  at "I" for their own numbered units (a standalone line containing
  ONLY the numeral — unlike the Jataka books, there is no accompanying
  title text on a second line, because these units genuinely have no
  individual titles in the source).
- Numbering is NOT always contiguous within a chapter (e.g. Chapter V
  jumps from I to III) — Ross's own translator's note (reproduced by
  PG) explains this: a handful of sections of the original Persian text
  were not translated, marked in this edition by a row of asterisks,
  and Ross evidently kept the original numbering rather than
  renumbering around the gaps. This parser does not assume a
  contiguous sequence — it just requires each chapter's found numerals
  to be strictly increasing, and lets `_EXPECTED_STORY_COUNTS` (derived
  from a full manual count of this exact edition) catch any drift.

CHAPTER VIII IS DELIBERATELY EXCLUDED — a structural finding, not a
taste judgement. A sample across chapters I-VII showed every unit
opening with a narrative scene ("I have heard of a king who...", "A
mendicant... was saying...", "They asked a scorpion..."); a sample
across chapter VIII ("Of the Duties of Society", 95 units — the
largest chapter by far) showed the opposite: the great majority are
bare gnomic maxims with no narrative frame at all ("Riches are
intended for the comfort of life, and not life for the purpose of
hoarding riches.", "Two things are repugnant to reason: ..."). This
matches Gottheil's 1900 introduction's own description of the book's
paragraphs as "generally beginning with an aphorism or an anecdote...
sometimes altogether lyrical" — chapter VIII is overwhelmingly the
"aphorism"/lyrical case, not the "anecdote" case this engine's
`stories` table models. Excluding it mirrors excluding Arany/Merényi's
riddle sections: a genre boundary drawn from the text's own content
shape, not from theological or literary taste.

NO PER-STORY TITLES EXIST IN THE SOURCE. Per the Phase 2K brief, this
parser does NOT synthesize one (e.g. from opening words, as
`book_of_300_anecdotes_parser.py` does for its untitled paragraphs —
that source at least has ordinary prose to draw a snippet from in a
way a reader would recognize as "the story's own opening", whereas a
fabricated snippet here would misleadingly look like a title where the
book presents none at all). Instead `title_original` is the chapter's
own subtitle ("Of the Customs of Kings", "Of the Morals of Dervishes",
...) — genuine source text, shared by every story in that chapter
(not unique per story, which is fine: `canonical_key`/`external_ref`
carry the per-story identity).

EXCLUDED: the title page, Gottheil's 1900 "Introduction" essay (a
modern editorial contribution, not Sa'di's or Ross's text), and the
front CONTENTS listing. The mid-text rows of asterisks marking a
skipped section (see above) are stripped as non-content, the same way
Baldwin's decorative scene-break rows are.
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


SOURCE_CODE = "PG_GULISTAN_SADI_ROSS"

_CHAPTER_HEADING_RE = re.compile(r"^CHAPTER ([IVXLC]+)$\n+^([^\n]+)$", re.MULTILINE)
_STORY_NUMERAL_RE = re.compile(r"^[ \t]*([IVXLC]+)[ \t]*$\n", re.MULTILINE)
_MISSING_SECTION_RE = re.compile(r"\n?[ \t]*\*(?:[ \t]+\*){2,}[ \t]*\n?")

# Manually verified against this exact edition (see module docstring for
# why chapter VIII is excluded). A count mismatch means either the source
# text changed or the parsing regex broke — either way, fail loudly
# rather than silently import a different set of stories.
_INCLUDED_CHAPTERS_IN_ORDER: tuple[str, ...] = ("I", "II", "III", "IV", "V", "VI", "VII")
_EXPECTED_STORY_COUNTS: dict[str, int] = {
    "I": 35,
    "II": 38,
    "III": 24,
    "IV": 12,
    "V": 15,
    "VI": 6,
    "VII": 17,
}


@dataclass(frozen=True)
class ParsedGulistanStory:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class GulistanParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


def parse_gulistan_text(raw_text: str) -> tuple[ParsedGulistanStory, ...]:
    """Parse the full raw PG #13060 plain-text into individual Gulistan
    stories from chapters I-VII (chapter VIII is deliberately excluded —
    see module docstring).

    Raises `GulistanParseError` if the PG markers, a chapter heading, or
    a chapter's expected story count don't match — parsing never
    silently returns a partial or misaligned result.
    """
    try:
        body = extract_pg_body(raw_text, source_label=SOURCE_CODE)
    except GutenbergBoilerplateError as exc:
        raise GulistanParseError(str(exc)) from exc

    chapter_matches = list(_CHAPTER_HEADING_RE.finditer(body))
    chapters_by_roman = {m.group(1): m for m in chapter_matches}
    for roman in _INCLUDED_CHAPTERS_IN_ORDER:
        if roman not in chapters_by_roman:
            raise GulistanParseError(f"{SOURCE_CODE}: could not locate 'CHAPTER {roman}' heading")

    stories: list[ParsedGulistanStory] = []
    for index, roman in enumerate(_INCLUDED_CHAPTERS_IN_ORDER):
        heading_match = chapters_by_roman[roman]
        chapter_subtitle = heading_match.group(2).strip()
        region_start = heading_match.end()
        next_match = chapter_matches[chapter_matches.index(heading_match) + 1]
        region_end = next_match.start()
        region = body[region_start:region_end]

        story_matches = list(_STORY_NUMERAL_RE.finditer(region))
        expected = _EXPECTED_STORY_COUNTS[roman]
        if len(story_matches) != expected:
            raise GulistanParseError(
                f"{SOURCE_CODE}: chapter {roman} expected {expected} numbered "
                f"stories, found {len(story_matches)}"
            )

        previous_value = 0
        for story_index, story_match in enumerate(story_matches):
            value = _roman_to_int(story_match.group(1))
            if value <= previous_value:
                raise GulistanParseError(
                    f"{SOURCE_CODE}: chapter {roman} story numerals are not "
                    f"strictly increasing at {story_match.group(1)!r}"
                )
            previous_value = value

            text_start = story_match.end()
            text_end = (
                story_matches[story_index + 1].start()
                if story_index + 1 < len(story_matches)
                else len(region)
            )
            raw_story_text = _MISSING_SECTION_RE.sub("\n", region[text_start:text_end])
            cleaned = collapse_blank_lines(raw_story_text).strip()
            if not cleaned:
                raise GulistanParseError(
                    f"{SOURCE_CODE}: chapter {roman} story {story_match.group(1)!r} "
                    "is empty after cleaning"
                )

            position = len(stories) + 1
            stories.append(
                ParsedGulistanStory(
                    canonical_key=f"{position:03d}",
                    external_ref=f"{roman}/{story_match.group(1)}",
                    title_original=chapter_subtitle,
                    original_text=cleaned,
                )
            )

    return tuple(stories)


def parse_gulistan_file(path: str | Path) -> tuple[ParsedGulistanStory, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_gulistan_text(raw_text)


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman_to_int(roman: str) -> int:
    total = 0
    previous = 0
    for char in reversed(roman):
        value = _ROMAN_VALUES[char]
        total += value if value >= previous else -value
        previous = value
    return total


__all__ = [
    "SOURCE_CODE",
    "GulistanParseError",
    "ParsedGulistanStory",
    "parse_gulistan_file",
    "parse_gulistan_text",
]
