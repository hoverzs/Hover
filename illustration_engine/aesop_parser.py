"""Source-specific parser for George Fyler Townsend's translation of
Aesop's Fables, Project Gutenberg #21 ("Three hundred Aesop's fables").

Structurally different from the Jataka books (see `jataka_parser.py`),
so it is NOT built on top of that module beyond the genuinely identical
PG-boilerplate extraction (`gutenberg_text.extract_pg_body`):

- There is no numbering at all (no roman numerals, no "I"/"II" headers) —
  each fable is delimited purely by its Title Case title line.
- With 313 fables, hand-typing an expected-title constant (the approach
  used for Jataka's 18/21 titles) would be unwieldy and error-prone.
  Instead this parser derives the authoritative, ordered title list from
  the book's OWN "CONTENTS" listing at parse time, then requires every
  one of those titles to reappear, in the same order, as an exact
  standalone body heading — this keeps the "never guess structure, always
  validate against a known-good expected shape" principle from the
  Jataka parser, just sourced from the file itself instead of a hardcoded
  constant (deriving the model of the book from the actual book being
  parsed, in one pass).
- The CONTENTS listing and the real body headings are reliably told apart
  by a single, consistent typographic detail in this edition: every
  CONTENTS entry is prefixed with exactly one leading space
  ("` The Lion And The Mouse`"), while the real body headings have none
  ("`The Lion And The Mouse`"). Matching titles with a strict `^title$`
  (no leading whitespace tolerance) therefore only ever matches the real
  body heading, never the CONTENTS entry — this is a deliberate,
  source-specific choice, NOT reused from Jataka's (whitespace-tolerant)
  header regex, because Jataka's CONTENTS lines always carry extra text
  (a page number) that already rules out an accidental exact-line match.
- The book also has real back matter after the last fable (`FOOTNOTES`,
  then `INDEX`) before the PG end marker, which must be excluded from
  the last fable's text — Jataka never needed this.
- Some titles are legitimately duplicated (distinct fables sharing the
  same title, e.g. two different "The Wolf and the Lion" fables). The
  strictly sequential, forward-only search (each title search starts
  right after the previous match) handles this correctly without special
  casing, as long as the body repeats them in the same order as CONTENTS.
- Unlike the Jataka books, this edition has no `[Illustration ...]`
  markers and no trailing "THE END"/colophon line inside fable bodies,
  so no such stripping is needed here.
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


SOURCE_CODE = "PG_AESOPS_FABLES_TOWNSEND"

_CONTENTS_HEADING_RE = re.compile(r"^CONTENTS$", re.MULTILINE)
_FABLES_SECTION_MARKER = "AESOP’S FABLES"
_BACK_MATTER_MARKER = "FOOTNOTES"


@dataclass(frozen=True)
class ParsedAesopFable:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class AesopParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


def parse_aesop_text(raw_text: str) -> tuple[ParsedAesopFable, ...]:
    """Parse the full raw PG #21 plain-text into individual fables.

    Raises `AesopParseError` if the PG markers, the CONTENTS listing, or
    any title derived from it cannot be found in order in the body —
    parsing never silently returns a partial or misaligned result.
    """
    try:
        body = extract_pg_body(raw_text, source_label=SOURCE_CODE)
    except GutenbergBoilerplateError as exc:
        raise AesopParseError(str(exc)) from exc

    titles = _derive_fable_titles_from_contents(body)

    header_matches: list[re.Match[str]] = []
    search_from = 0
    for title in titles:
        pattern = re.compile(rf"^{re.escape(title)}$\n", re.MULTILINE)
        match = pattern.search(body, search_from)
        if match is None:
            raise AesopParseError(
                f"{SOURCE_CODE}: expected fable heading not found in order: "
                f"{title!r} (searching from offset {search_from})"
            )
        header_matches.append(match)
        search_from = match.end()

    back_matter_match = re.search(rf"^{_BACK_MATTER_MARKER}$", body, re.MULTILINE)
    if back_matter_match is None or back_matter_match.start() < header_matches[-1].end():
        raise AesopParseError(
            f"{SOURCE_CODE}: expected back-matter marker {_BACK_MATTER_MARKER!r} "
            "not found after the last fable"
        )

    fables: list[ParsedAesopFable] = []
    for index, (title, header_match) in enumerate(zip(titles, header_matches)):
        text_start = header_match.end()
        text_end = (
            header_matches[index + 1].start()
            if index + 1 < len(header_matches)
            else back_matter_match.start()
        )
        cleaned = collapse_blank_lines(body[text_start:text_end]).strip()
        if not cleaned:
            raise AesopParseError(f"{SOURCE_CODE}: fable {title!r} is empty after cleaning")
        position = index + 1
        fables.append(
            ParsedAesopFable(
                canonical_key=f"{position:03d}",
                external_ref=str(position),
                title_original=title,
                original_text=cleaned,
            )
        )

    return tuple(fables)


def parse_aesop_file(path: str | Path) -> tuple[ParsedAesopFable, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_aesop_text(raw_text)


def _derive_fable_titles_from_contents(body: str) -> list[str]:
    """Extracts the ordered fable-title list from the book's own CONTENTS
    section, excluding the surrounding front-matter ("PREFACE", "LIFE OF
    AESOP") and back-matter ("FOOTNOTES", "INDEX") entries."""
    heading_match = _CONTENTS_HEADING_RE.search(body)
    if heading_match is None:
        raise AesopParseError(f"{SOURCE_CODE}: could not locate a 'CONTENTS' heading")

    entries: list[str] = []
    for line in body[heading_match.end() :].splitlines():
        if line == "":
            continue
        if line.startswith(" "):
            entries.append(line.strip())
            continue
        break  # first non-indented, non-blank line ends the CONTENTS block

    try:
        start_index = entries.index(_FABLES_SECTION_MARKER) + 1
        end_index = entries.index(_BACK_MATTER_MARKER, start_index)
    except ValueError as exc:
        raise AesopParseError(
            f"{SOURCE_CODE}: CONTENTS listing is missing the expected "
            f"{_FABLES_SECTION_MARKER!r}/{_BACK_MATTER_MARKER!r} boundary markers"
        ) from exc

    titles = entries[start_index:end_index]
    if not titles:
        raise AesopParseError(f"{SOURCE_CODE}: no fable titles found in CONTENTS")
    return titles


__all__ = [
    "SOURCE_CODE",
    "AesopParseError",
    "ParsedAesopFable",
    "parse_aesop_file",
    "parse_aesop_text",
]
