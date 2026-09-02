"""Source-specific parser for James Baldwin's "Fifty Famous Stories
Retold" (New York: American Book Company, 1896), Project Gutenberg
#18442.

Structurally the SIMPLEST of the sources handled by this engine so far:
this edition's "CONTENTS." listing is a clean, one-title-per-line list
with no page numbers and no line-wrapping (unlike Aesop's or Arany's),
so the title list is derived from it programmatically, mirroring
`aesop_parser.py`'s approach rather than a hardcoded constant. Matching
is a plain, case-SENSITIVE search for each title's ALL-CAPS
(`.upper()`), optionally period-terminated body heading — this alone is
enough to distinguish it from the CONTENTS entry (mixed case) with no
need for Arany/Merényi's accent-fold tolerance (this is English text —
no accented capitals) or Aesop's leading-space trick (no page numbers to
create ambiguity in the first place).

EXCLUDED FRONT MATTER: the CONTENTS listing itself, and Baldwin's own
"CONCERNING THESE STORIES." preface (see the audit for why its content
matters even though it's excluded — it directly addresses the
legend-vs-documented-history question). A book-title heading
("FIFTY FAMOUS STORIES RETOLD.") is repeated a second time, right before
the first story — this is naturally skipped since it is not one of the
50 titles being searched for.

MULTI-PART STORIES ARE KEPT AS ONE RECORD, NOT SPLIT: two of the fifty
CONTENTS entries are told across internal, non-CONTENTS-listed
sub-headings — "King John and the Abbot" contains "I. THE THREE
QUESTIONS." / "II. THE THREE ANSWERS.", and "Whittington and his Cat"
contains five roman-numeral sub-parts. Because the parser only searches
for the 50 official CONTENTS titles (never the internal sub-headings),
these sub-headings are automatically swept up as part of their parent
story's continuous `original_text` — exactly matching the book's own
CONTENTS, which treats each as ONE entry. Likewise, "The White Ship" is
followed by an unlisted second heading ("He Never Smiled Again") that
is really its second scene, not a separate story — same automatic
handling, no special-casing needed.

NO SEPARATE BACK-MATTER SECTION exists after the last story (unlike
Aesop's FOOTNOTES/INDEX or the Hungarian folktale books' riddle
sections) — the last story's text runs to the PG end marker. What DOES
land in its raw tail is a decorative "*   *   *   *   *" scene-break
ornament (a period-typography convention, not narrative content) and
occasionally a "End of Project Gutenberg's ..." colophon line — both
stripped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from illustration_engine.gutenberg_text import (
    GutenbergBoilerplateError,
    collapse_blank_lines,
    extract_pg_body,
    strip_illustration_tags,
    strip_trailing_pg_colophon,
)


SOURCE_CODE = "PG_BALDWIN_FIFTY_FAMOUS_STORIES_RETOLD"

_CONTENTS_HEADING_RE = re.compile(r"^CONTENTS\.$", re.MULTILINE)
_PREFACE_HEADING = "CONCERNING THESE STORIES."
_TRAILING_SCENE_BREAK_RE = re.compile(r"\n+[ \t]*\*(?:[ \t]+\*){2,}[ \t]*\Z")


@dataclass(frozen=True)
class ParsedBaldwinStory:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class BaldwinParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


def parse_baldwin_text(raw_text: str) -> tuple[ParsedBaldwinStory, ...]:
    """Parse the full raw PG #18442 plain-text into individual stories.

    Raises `BaldwinParseError` if the PG markers, the CONTENTS listing,
    or any title derived from it cannot be found in order in the body —
    parsing never silently returns a partial or misaligned result.
    """
    try:
        body = extract_pg_body(raw_text, source_label=SOURCE_CODE)
    except GutenbergBoilerplateError as exc:
        raise BaldwinParseError(str(exc)) from exc

    titles = _derive_story_titles_from_contents(body)

    header_matches: list[re.Match[str]] = []
    search_from = 0
    for title in titles:
        pattern = re.compile(rf"^{re.escape(title.upper())}\.?$\n", re.MULTILINE)
        match = pattern.search(body, search_from)
        if match is None:
            raise BaldwinParseError(
                f"{SOURCE_CODE}: expected story heading not found in order: "
                f"{title!r} (searching from offset {search_from})"
            )
        header_matches.append(match)
        search_from = match.end()

    stories: list[ParsedBaldwinStory] = []
    for index, (title, header_match) in enumerate(zip(titles, header_matches)):
        text_start = header_match.end()
        text_end = (
            header_matches[index + 1].start() if index + 1 < len(header_matches) else len(body)
        )
        cleaned = _clean_story_text(body[text_start:text_end])
        if not cleaned:
            raise BaldwinParseError(f"{SOURCE_CODE}: story {title!r} is empty after cleaning")
        position = index + 1
        stories.append(
            ParsedBaldwinStory(
                canonical_key=f"{position:02d}",
                external_ref=str(position),
                title_original=title,
                original_text=cleaned,
            )
        )

    return tuple(stories)


def parse_baldwin_file(path: str | Path) -> tuple[ParsedBaldwinStory, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_baldwin_text(raw_text)


def _derive_story_titles_from_contents(body: str) -> list[str]:
    heading_match = _CONTENTS_HEADING_RE.search(body)
    if heading_match is None:
        raise BaldwinParseError(f"{SOURCE_CODE}: could not locate a 'CONTENTS.' heading")

    titles: list[str] = []
    for line in body[heading_match.end() :].splitlines():
        if line == "":
            continue
        if line.strip() == _PREFACE_HEADING:
            break
        titles.append(line.strip())

    if not titles:
        raise BaldwinParseError(f"{SOURCE_CODE}: no story titles found in CONTENTS")
    return titles


def _clean_story_text(raw_text: str) -> str:
    text = strip_illustration_tags(raw_text)
    text = strip_trailing_pg_colophon(text)
    text = _TRAILING_SCENE_BREAK_RE.sub("", text)
    text = collapse_blank_lines(text)
    return text.strip()


__all__ = [
    "SOURCE_CODE",
    "BaldwinParseError",
    "ParsedBaldwinStory",
    "parse_baldwin_file",
    "parse_baldwin_text",
]
