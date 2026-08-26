"""Source-specific parser for Ellen C. Babbitt's Project Gutenberg Jataka
Tales editions (PG #62514 "Jataka Tales", 1912; PG #7518 "More Jataka
Tales", 1922).

This module only turns a raw PG plain-text file into structured, in-memory
story objects — it never touches SQLite (see `jataka_importer.py` for
that). It deliberately does NOT do free-form structural guessing: each
book's exact (roman numeral, title) sequence is hardcoded from the book's
own "CONTENTS" listing, and parsing fails loudly if the text does not
contain every expected header in order. This mirrors the
`bible_engine/hymn_*` philosophy of never trusting silent/partial
extraction over a known-good expected shape.

Excluded from every parsed story (never reaches the database as story
content): the PG legal header/footer, the transcriber's note, the title
page, the dedication, the foreword (Felix Adler's foreword in book 1;
book 2's own foreword referencing it), and the CONTENTS listing itself.
`[Illustration ...]` caption markers embedded inside a story's body are
also stripped, since they are a PG transcription artifact (an image
placeholder), not prose content — everything else in `original_text` is
preserved unchanged from the source.
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


_ILLUSTRATION_RE = re.compile(r"\[Illustration[^\]]*\]")
_TRAILING_THE_END_RE = re.compile(r"\n+THE END\s*\Z")
_TRAILING_PG_COLOPHON_RE = re.compile(
    r"\n+End of (?:the )?Project Gutenberg.*\Z", re.IGNORECASE | re.DOTALL
)


@dataclass(frozen=True)
class JatakaBookSpec:
    source_code: str
    book_title: str
    stories: tuple[tuple[str, str], ...]  # (roman numeral, title), in order


@dataclass(frozen=True)
class ParsedJatakaStory:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class JatakaParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


JATAKA_TALES_1912 = JatakaBookSpec(
    source_code="PG_JATAKA_TALES_BABBITT_1912",
    book_title="Jataka Tales",
    stories=(
        ("I", "THE MONKEY AND THE CROCODILE"),
        ("II", "HOW THE TURTLE SAVED HIS OWN LIFE"),
        ("III", "THE MERCHANT OF SERI"),
        ("IV", "THE TURTLE WHO COULDN'T STOP TALKING"),
        ("V", "THE OX WHO WON THE FORFEIT"),
        ("VI", "THE SANDY ROAD"),
        ("VII", "THE QUARREL OF THE QUAILS"),
        ("VIII", "THE MEASURE OF RICE"),
        ("IX", "THE FOOLISH, TIMID RABBIT"),
        ("X", "THE WISE AND THE FOOLISH MERCHANT"),
        ("XI", "THE ELEPHANT GIRLY-FACE"),
        ("XII", "THE BANYAN DEER"),
        ("XIII", "THE PRINCES AND THE WATER-SPRITE"),
        ("XIV", "THE KING'S WHITE ELEPHANT"),
        ("XV", "THE OX WHO ENVIED THE PIG"),
        ("XVI", "GRANNY'S BLACKIE"),
        ("XVII", "THE CRAB AND THE CRANE"),
        ("XVIII", "WHY THE OWL IS NOT KING OF THE BIRDS"),
    ),
)

MORE_JATAKA_TALES_1922 = JatakaBookSpec(
    source_code="PG_MORE_JATAKA_TALES_BABBITT_1922",
    book_title="More Jataka Tales",
    stories=(
        ("I", "THE GIRL MONKEY AND THE STRING OF PEARLS"),
        ("II", "THE THREE FISHES"),
        ("III", "THE TRICKY WOLF AND THE RATS"),
        ("IV", "THE WOODPECKER, TURTLE, AND DEER"),
        ("V", "THE GOLDEN GOOSE"),
        ("VI", "THE STUPID MONKEYS"),
        ("VII", "THE CUNNING WOLF"),
        ("VIII", "THE PENNY-WISE MONKEY"),
        ("IX", "THE RED-BUD TREE"),
        ("X", "THE WOODPECKER AND THE LION"),
        ("XI", "THE OTTERS AND THE WOLF"),
        ("XII", "HOW THE MONKEY SAVED HIS TROOP"),
        ("XIII", "THE HAWKS AND THEIR FRIENDS"),
        ("XIV", "THE BRAVE LITTLE BOWMAN"),
        ("XV", "THE FOOLHARDY WOLF"),
        ("XVI", "THE STOLEN PLOW"),
        ("XVII", "THE LION IN BAD COMPANY"),
        ("XVIII", "THE WISE GOAT AND THE WOLF"),
        ("XIX", "PRINCE WICKED AND THE GRATEFUL ANIMALS"),
        ("XX", "BEAUTY AND BROWNIE"),
        ("XXI", "THE ELEPHANT AND THE DOG"),
    ),
)


def parse_jataka_text(raw_text: str, spec: JatakaBookSpec) -> tuple[ParsedJatakaStory, ...]:
    """Parse the full raw PG plain-text of one Jataka book into stories.

    Raises `JatakaParseError` if the PG start/end markers or any expected
    (roman numeral, title) header is missing, out of order, or duplicated —
    parsing never silently returns a partial or misaligned result.
    """
    try:
        body = extract_pg_body(raw_text, source_label=spec.source_code)
    except GutenbergBoilerplateError as exc:
        raise JatakaParseError(str(exc)) from exc

    header_matches: list[re.Match[str]] = []
    search_from = 0
    for roman, title in spec.stories:
        pattern = re.compile(
            rf"^[ \t]*{re.escape(roman)}\.?[ \t]*$\n+^[ \t]*{re.escape(title)}[ \t]*$\n",
            re.MULTILINE,
        )
        match = pattern.search(body, search_from)
        if match is None:
            raise JatakaParseError(
                f"{spec.source_code}: expected header not found in order: "
                f"{roman!r} / {title!r} (searching from offset {search_from})"
            )
        header_matches.append(match)
        search_from = match.end()

    stories: list[ParsedJatakaStory] = []
    for index, ((roman, title), header_match) in enumerate(zip(spec.stories, header_matches)):
        text_start = header_match.end()
        text_end = header_matches[index + 1].start() if index + 1 < len(header_matches) else len(body)
        raw_story_text = body[text_start:text_end]
        cleaned = _clean_story_text(raw_story_text)
        if not cleaned:
            raise JatakaParseError(f"{spec.source_code}: story {roman!r} ({title!r}) is empty after cleaning")
        stories.append(
            ParsedJatakaStory(
                canonical_key=f"{index + 1:02d}",
                external_ref=roman,
                title_original=title.title(),
                original_text=cleaned,
            )
        )

    return tuple(stories)


def parse_jataka_file(path: str | Path, spec: JatakaBookSpec) -> tuple[ParsedJatakaStory, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_jataka_text(raw_text, spec)


def _clean_story_text(raw_text: str) -> str:
    text = _ILLUSTRATION_RE.sub("", raw_text)
    text = _TRAILING_THE_END_RE.sub("", text)
    text = _TRAILING_PG_COLOPHON_RE.sub("", text)
    text = collapse_blank_lines(text)
    return text.strip()


__all__ = [
    "JATAKA_TALES_1912",
    "MORE_JATAKA_TALES_1922",
    "JatakaBookSpec",
    "JatakaParseError",
    "ParsedJatakaStory",
    "parse_jataka_file",
    "parse_jataka_text",
]
