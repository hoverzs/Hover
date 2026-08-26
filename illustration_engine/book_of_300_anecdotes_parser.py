"""Source-specific parser for "The Book of Three Hundred Anecdotes:
Historical, Literary, and Humorous. A New Selection." (London: Burns &
Oates / New York: Barclay Street, undated 19th-century edition),
Project Gutenberg #15413.

A THIRD, distinct structural pattern (neither Jataka/Aesop/Baldwin's
"one heading per story" nor the Hungarian folktale books' scheme):

- The book is organised into ~46 ALL-CAPS THEMATIC CATEGORIES (e.g.
  "AFFECTION.", "ARTISTS.", "HUMANITY.") — a standalone, short,
  all-caps line ending in a period, distinguishable from any anecdote
  paragraph by being the ENTIRE paragraph (an anecdote paragraph always
  contains lower-case prose after its opening words).
- WITHIN a category, individual anecdotes are blank-line-separated
  paragraphs. The clear majority open with a short name/label followed
  by ".--" ("General St. Amour.--This officer..."), which is captured
  as `title_original`. But roughly 40% of paragraphs (161 of 409 in
  this edition) have NO such label — they simply continue in plain
  prose ("Richardson, in his anecdotes of painting, says...") while
  still being a genuinely separate, self-contained anecdote (verified
  by reading a sample), not a continuation of the previous one.

Because of that ~40% figure, this parser does NOT delimit anecdotes by
searching for the ".--" pattern (that would silently swallow every
untitled paragraph into whichever titled anecdote precedes it — a
segmentation bug, not just missing metadata).

A SECOND segmentation hazard, found by inspecting the shortest parsed
results empirically (not assumed in advance): several anecdotes quote
a short indented verse/rhyme in their middle ("    'Drink, weary
traveller--drink and pray;'"), typeset with its own blank-line spacing
— a naive "blank line = new anecdote" rule fragments ONE anecdote into
2-4 pieces at these quotes. Two independent, empirically-verified
signals distinguish a genuine new anecdote from such an internal
fragment: a real anecdote's paragraph always (a) starts at column 0
(no leading whitespace on its first raw line, before stripping) and
(b) starts with an upper-case letter. Any paragraph failing either
check is appended to the PRECEDING anecdote's text instead of starting
a new record — this is why indentation must be inspected on the raw,
not yet `.strip()`-ed paragraph text.

A THIRD segmentation hazard, found during a follow-up review of the
shortest parsed results: a small number of paragraphs are actually the
TAIL of the preceding anecdote (its punchline sentence, or an
editorial aside about it), not a new anecdote — but, unlike the verse
quotes above, they are typeset completely flush-left with no
indentation, so they are structurally indistinguishable from a
genuine new untitled anecdote by formatting alone. One sub-case DOES
have a reliable, general, verified-safe marker and is handled:
paragraphs opening with a bare demonstrative ("This incident has been
admirably worked up in a German ballad...") grammatically require an
antecedent, and — checked against the full 345-anecdote corpus — this
pattern occurs exactly ONCE in the whole book, so treating it as a
continuation carries no false-positive risk elsewhere; it is merged
into the preceding anecdote the same way verse fragments are.

Two further known cases (a Sheridan schoolroom anecdote's closing
sentence, "SCHOOLS"; a Dieppe-pilot rescue's follow-up reward letter,
"HEROISM") were checked directly against their raw-text context and
are, in fact, also continuations — but NO general, low-risk rule to
catch them was found. The most obvious candidate (merge a paragraph
into the previous one if its opening proper noun already appeared
there) was tested and REJECTED: this book has categories built around
one recurring person (e.g. "BONAPARTE", "FONTENELLE"), where multiple
genuinely SEPARATE anecdotes legitimately open with the same name
("Fontenelle, being praised for..." immediately follows another
Fontenelle anecdote) — a name-repetition rule would silently merge
those together, trading a ~0.6%-of-corpus problem for a worse, harder
to detect one.

Because no safe general rule exists for these two, they are handled by
`_MANUAL_CONTINUATION_PREFIXES` below — a small, explicit, source-
specific override list (NOT a general framework: it lives only in this
module, keyed by exact verbatim opening text manually verified against
the raw PG #15413 source, and parsing fails loudly if a listed prefix
is never matched, so a future re-transcription that changes the text
cannot silently go stale).

Title extraction is a two-path, fully deterministic rule applied AFTER
segmentation:
  1. If the paragraph opens with `<label>.--`, that label is
     `title_original` (`title_is_derived=False`).
  2. Otherwise, `title_original` is synthesized from the paragraph's
     own first few words (`title_is_derived=True`) — still literally
     "from the source" (no invented wording), just not an
     author-supplied label. This distinction is surfaced on
     `ParsedAnecdote.title_is_derived` so a future metadata/quality
     pass can treat the two differently without re-parsing.

EXCLUDED: the front-of-book alphabetical "INDEX." (a page-number
subject index, not a table of contents — entries like "ACTORS, 27-33"
give page ranges, not titles, and are useless as titles anyway), the
title-page material before it, and the "THE END." + PG colophon after
the last anecdote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from illustration_engine.gutenberg_text import (
    GutenbergBoilerplateError,
    collapse_blank_lines,
    extract_pg_body,
    strip_trailing_pg_colophon,
)


SOURCE_CODE = "PG_BOOK_OF_300_ANECDOTES"

_CONTENT_START_RE = re.compile(r"^ANECDOTES\.$", re.MULTILINE)
_TRAILING_THE_END_RE = re.compile(r"\n+THE END\.\s*\Z")
_CATEGORY_HEADER_RE = re.compile(r"\A[A-Z][A-Z .,'&\-]*\.\Z")
_TITLED_ANECDOTE_RE = re.compile(r"\A([A-Z][^\n]*?)\.--")
_FALLBACK_TITLE_WORDS = 8

# A paragraph opening with a bare demonstrative ("This incident has been
# admirably worked up in a German ballad...") grammatically requires an
# antecedent — no genuine, self-contained anecdote in this book opens
# this way (verified: exactly one paragraph in the whole 345-anecdote
# corpus matches this pattern). It is therefore a reliable, general
# signal for an editorial aside/remark trailing the PRECEDING anecdote,
# not a new one — same treatment as an indented verse fragment.
_DEMONSTRATIVE_CONTINUATION_RE = re.compile(
    r"\A(?:This|That|These|Those)\s+(?:incident|anecdote|story|circumstance|"
    r"fact|case|event|occurrence)\b",
    re.IGNORECASE,
)

# MANUAL SEGMENTATION OVERRIDE — this book only.
#
# Both entries were verified by direct inspection of the raw PG #15413
# text: each is typographically a completely ordinary new paragraph
# (flush-left, capitalised first word — indistinguishable by formatting
# from a genuine untitled anecdote), but narratively each is the tail of
# the PRECEDING anecdote, not an independent one:
#
#   - "Sheridan instantly dropped the rod, and, instead of a good
#     whipping, gave him half-a-crown." (SCHOOLS category) is the
#     punchline of the immediately preceding "Dr. Sheridan had a custom
#     of ringing his scholars to prayers..." anecdote (the rat-in-the-
#     bell-rope schoolroom story) — "the rod" and "a good whipping" are
#     definite references to things only established there.
#   - "Mons. de Crosne, the Intendant of Rouen, having stated these
#     circumstances to M. Neckar..." (HEROISM category) is the reward-
#     letter epilogue of the immediately preceding "A Dieppe Pilot"
#     anecdote — "these circumstances" and "Boussard" (the letter's
#     addressee) both refer back to that story.
#
# No general typographic/grammatical rule (indentation, demonstrative
# pronouns, name-repetition — see module docstring for what was tried
# and rejected) safely catches these two without risking false merges
# elsewhere in the corpus, so they are listed here explicitly instead.
# Matched against the paragraph's own stripped, collapsed text via
# `str.startswith`, so a change to this exact wording in a future PG
# re-transcription will make the override silently stop firing — which
# is why `parse_book_of_300_anecdotes_text` verifies every entry here
# was actually used at least once and fails loudly otherwise.
_MANUAL_CONTINUATION_PREFIXES: tuple[str, ...] = (
    "Sheridan instantly dropped the rod,",
    "Mons. de Crosne, the Intendant of Rouen,",
)


@dataclass(frozen=True)
class ParsedAnecdote:
    canonical_key: str
    external_ref: str
    title_original: str
    title_is_derived: bool
    category: str
    original_text: str


class BookOf300AnecdotesParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


def parse_book_of_300_anecdotes_text(raw_text: str) -> tuple[ParsedAnecdote, ...]:
    """Parse the full raw PG #15413 plain-text into individual anecdotes.

    Raises `BookOf300AnecdotesParseError` if the PG markers or the
    "ANECDOTES." content-start marker are missing, or if an anecdote
    paragraph appears before any category header — parsing never
    silently returns a partial or misaligned result.
    """
    try:
        body = extract_pg_body(raw_text, source_label=SOURCE_CODE)
    except GutenbergBoilerplateError as exc:
        raise BookOf300AnecdotesParseError(str(exc)) from exc

    start_match = _CONTENT_START_RE.search(body)
    if start_match is None:
        raise BookOf300AnecdotesParseError(
            f"{SOURCE_CODE}: could not locate the 'ANECDOTES.' content-start marker"
        )
    content = body[start_match.end() :]
    content = _TRAILING_THE_END_RE.sub("", content)
    content = strip_trailing_pg_colophon(content)

    # Deliberately NOT stripped yet: leading whitespace on a raw paragraph's
    # first line is the signal that distinguishes an internal verse-quote
    # fragment from a genuine new anecdote (see module docstring).
    raw_paragraphs = [p for p in re.split(r"\n[ \t]*\n", content) if p.strip()]

    anecdotes: list[ParsedAnecdote] = []
    matched_manual_prefixes: set[str] = set()
    current_category: str | None = None
    position_in_category = 0
    for raw_paragraph in raw_paragraphs:
        stripped = raw_paragraph.strip()
        collapsed = collapse_blank_lines(stripped)

        if _CATEGORY_HEADER_RE.match(collapsed):
            current_category = collapsed.rstrip(".")
            position_in_category = 0
            continue

        first_line = raw_paragraph.split("\n", 1)[0]
        is_indented = first_line[:1] in (" ", "\t")
        starts_uppercase = collapsed[:1].isupper() if collapsed else False
        is_demonstrative_continuation = bool(_DEMONSTRATIVE_CONTINUATION_RE.match(collapsed))
        manual_prefix = next(
            (p for p in _MANUAL_CONTINUATION_PREFIXES if collapsed.startswith(p)), None
        )
        if manual_prefix is not None:
            matched_manual_prefixes.add(manual_prefix)

        if is_indented or not starts_uppercase or is_demonstrative_continuation or manual_prefix:
            if not anecdotes:
                raise BookOf300AnecdotesParseError(
                    f"{SOURCE_CODE}: an internal-fragment-shaped paragraph "
                    f"appeared with no preceding anecdote to attach it to: "
                    f"{collapsed[:60]!r}"
                )
            previous = anecdotes[-1]
            anecdotes[-1] = ParsedAnecdote(
                canonical_key=previous.canonical_key,
                external_ref=previous.external_ref,
                title_original=previous.title_original,
                title_is_derived=previous.title_is_derived,
                category=previous.category,
                original_text=f"{previous.original_text}\n\n{collapsed}",
            )
            continue

        if current_category is None:
            raise BookOf300AnecdotesParseError(
                f"{SOURCE_CODE}: anecdote paragraph found before any category "
                f"header: {collapsed[:60]!r}"
            )

        position_in_category += 1
        title_original, is_derived = _extract_title(collapsed)
        position = len(anecdotes) + 1
        anecdotes.append(
            ParsedAnecdote(
                canonical_key=f"{position:03d}",
                external_ref=f"{current_category}/{position_in_category}",
                title_original=title_original,
                title_is_derived=is_derived,
                category=current_category,
                original_text=collapsed,
            )
        )

    if not anecdotes:
        raise BookOf300AnecdotesParseError(f"{SOURCE_CODE}: no anecdotes were parsed")

    unused_overrides = set(_MANUAL_CONTINUATION_PREFIXES) - matched_manual_prefixes
    if unused_overrides:
        raise BookOf300AnecdotesParseError(
            f"{SOURCE_CODE}: _MANUAL_CONTINUATION_PREFIXES entry never matched the "
            f"source text (source may have changed — re-verify the override): "
            f"{sorted(unused_overrides)!r}"
        )

    return tuple(anecdotes)


def parse_book_of_300_anecdotes_file(path: str | Path) -> tuple[ParsedAnecdote, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_book_of_300_anecdotes_text(raw_text)


def _extract_title(paragraph: str) -> tuple[str, bool]:
    match = _TITLED_ANECDOTE_RE.match(paragraph)
    if match:
        return match.group(1).strip(), False
    words = paragraph.split()
    snippet = " ".join(words[:_FALLBACK_TITLE_WORDS]).rstrip(",.;:")
    return snippet, True


__all__ = [
    "SOURCE_CODE",
    "BookOf300AnecdotesParseError",
    "ParsedAnecdote",
    "parse_book_of_300_anecdotes_file",
    "parse_book_of_300_anecdotes_text",
]
