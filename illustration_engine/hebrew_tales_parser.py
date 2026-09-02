"""Source-specific parser for Hyman Hurwitz's "Hebrew Tales: Selected
and Translated from the Writings of the Ancient Hebrew Sages" (London,
1826), as revised and re-edited by George Alexander Kohut in the
"Second Edition" (New York: Bloch Publishing Co., 1917/1911).

NOT A PROJECT GUTENBERG SOURCE. The raw text
(`data/raw/illustrations/wikisource_hebrew_tales_hurwitz_kohut1917.txt`)
is extracted from the English Wikisource "Validated" (community
double-proofread) transcription of the 1917 edition — see the Phase 2M
audit for why this specific digital edition was chosen over the raw,
uncorrected-OCR scans of the true 1826 first edition on archive.org.
Consequently this parser does NOT use `gutenberg_text.extract_pg_body`
(there are no PG START/END boilerplate markers here) and its importer
does NOT go through `pg_story_import.py` (see `hebrew_tales_importer.py`
— it uses the renamed, format-agnostic `story_import.py` instead). It
DOES reuse `gutenberg_text.normalize_line_endings`/`collapse_blank_lines`
— those two helpers are genuinely format-agnostic whitespace
normalization with no PG-specific behavior, unlike `extract_pg_body`.

PROVENANCE (see `sources.json` for the full legal audit):
- Hurwitz translated/selected the tales from Talmudic and Midrashic
  sources for the 1826 first edition (Morrison and Watt, London).
- Kohut, editing the 1917 "Second Edition", explicitly disclosed (in
  his own Editor's Preface, reproduced in this same raw source) that he
  (a) omitted Hurwitz's original prefatory Essay, (b) omitted the
  original edition's separate "Aphorisms and Apophthegms" section and
  "a number of items which can not properly be classified as 'tales'"
  — i.e. Kohut ALREADY did our project's own narrative-only filtering
  for us, which is why this source needed no manual non-narrative
  exclusion list (contrast `english_jests_and_anecdotes_parser.py`'s
  7-item list) — (c) modernized the spelling of proper names, and (d)
  "abbreviate[d] the chapter-headings and the introductions to some of
  the stories." Point (d) is why `title_original` is taken from the
  actual BODY heading (the fuller, sometimes-longer wording Kohut kept
  in the running text) rather than the shorter Table-of-Contents
  wording — the TOC titles are used ONLY as search seeds to locate each
  body heading, never stored as `title_original` themselves.
- Three tales (the 2nd, 3rd, and 4th in the volume — "The Value of a
  Good Wife", "The Lord Helpeth Man and Beast", "Conversation of a
  Philosopher with a Rabbi") were, per Kohut's preface, actually
  translated by Samuel Taylor Coleridge, not Hurwitz. This is recorded
  in `sources.json`'s `notes_hu` (no schema field was added for
  per-story translator attribution — the model has nowhere to hang a
  third per-story attribution axis without speculative schema growth,
  and it is source-level provenance information, not something that
  varies in a way any current field could misrepresent).

STRUCTURE: 65 titled units between the body heading "HEBREW TALES" and
the reference-notes section — 55 main tales (pp. 15-111) + 10
"Facetiae" (witty anecdotes, pp. 115-128), per the work's own Table of
Contents. Every unit has a genuine title (unlike
`book_of_300_anecdotes_parser.py`'s source) — no derived-title fallback
is needed. Each unit is: a title line, a blank line, the narrative
prose (itself possibly several blank-line-separated paragraphs), and
then a Talmudic/Midrashic source citation (e.g. "Exodus Rabba, § II.",
"Shabbat, 82a.") as its own final paragraph.

TOC-VS-BODY HEADING MATCHING: the Table of Contents' wording sometimes
differs from the actual body heading (case differences, an inserted
"of"/dropped "The", or the body heading continuing with a longer
subtitle after the TOC's shorter form, e.g. TOC "Ambition Humbled and
Reproved" vs. body "Ambition Humbled and Reproved or Alexander and the
Human Skull"). `_locate_heading` handles this with two general,
title-agnostic rules — no per-title hardcoded overrides were needed for
any of the 65 titles: (1) match on the title's first 5 words with a
FLEXIBLE separator between them (arbitrary whitespace/quote characters,
not a literal single space) — this alone resolves cases like TOC
`Milton's "Dark from Excess of Light"` vs. body `Milton's "Dark from
Excess of Light."` where a straight quote sits directly between two
words with no space; (2) if that fails, retry after stripping a
leading "The "/"A "/"An " article from the title — this resolves the
two "Sufferings of the Jews under Hadrian" tales, whose TOC entries
inconsistently include/omit a leading "The" that the body heading never
has either way. The TOC itself has one duplicate SEARCH SEED
("Scrupulous Honesty" is the shortened TOC form of two different
tales) — but since `title_original` is taken from the fuller body
heading (point (d) above), the two resolve to distinct, unique titles
on their own ("Scrupulous Honesty. Exemplified in the Hospitable Rabbi
Phinehas" / "...Exemplified in the Conduct of Rabbi Saphra"); all 65
final `title_original` values are unique. Even so, matching never
relies on title uniqueness to begin with — each TOC search always
starts from just past the previously-found heading, so sequential
title order (not text uniqueness) is what actually resolves any
duplicate seed, and `canonical_key`/`external_ref` carry the per-story
identity positionally regardless.

SOURCE CITATIONS ARE KEPT, NOT STRIPPED. Per the Phase 2N brief, the
trailing Talmudic/Midrashic citation on every tale (e.g. "Yerushalmi
Horayot, III, 48a.") is genuine, valuable provenance data — the current
`stories` schema has no dedicated `source_reference` column (audited:
`illustration_sqlite.py`'s `stories` table has no such field, and
`moral_hu` is a Hungarian-labeled AI-enrichment target, not a place to
smuggle English source-citation data into). No speculative schema
change was made. Instead the citation is deliberately left as the LAST
paragraph of `original_text`, before any reattached footnote block (see
below) — exactly matching its position on the actual printed page, so
`original_text` stays genuinely verbatim/source-faithful. A future
migration can deterministically extract it: it is always the paragraph
immediately after the narrative body and immediately before a
reattached footnote block (if any), and it never itself contains a
"\n\n" internally in the 65 units checked in this phase.

FOOTNOTE MARKERS ([1], [2], ...): Kohut's edition has 15 numbered
footnotes, collected in a references list at the very end of the page,
each referenced by an inline `[N]` marker within some tale's text. Per
the Phase 2N brief, these are NOT blindly deleted. Reading all 15
showed a genuine mix — short glosses of a Hebrew/Aramaic/Greek term
central to the story ("A small coin, of less value than a farthing." —
explaining "Pruta" in "Wit Like Salt"), a historical aside that itself
contains a second embedded anecdote (footnote 9, about Rabbi Akiba and
Pappos), and a couple of pure bibliographic cross-references ("See
Numbers v. 23."). Rather than build a fuzzy, subjective "is this one
necessary" classifier (exactly the kind of ad hoc judgment call this
project's structural/deterministic philosophy avoids elsewhere), every
footnote whose marker survives into a story's cleaned text is kept in
full and reattached verbatim to that story, in marker order, as its own
trailing paragraph(s) after the citation — the inline `[N]` marker
itself is stripped from the narrative sentence (a dangling reference to
a page-bottom list has no meaning once the tale is extracted on its
own) but the footnote's actual text is preserved, never discarded.
ONE footnote (marker 13, "For the entire contents of this section, see
the article 'Athenians in Talmud and Midrash'...") is attached not to
any individual tale but to the "FACETIÆ" section-divider heading itself
(it literally reads "FACETIÆ[13]" on the page, between the last main
tale and the first Facetiae item) — this is stripped as front-matter-
within-body (see `_FACETIAE_SECTION_HEADER_RE`) along with its marker,
and footnote 13's text is preserved instead in `sources.json`'s
`notes_hu` (documented there, not attached to any single story, since
it genuinely is not about any one story).

Wikisource's page-transclusion mechanism inserts an invisible U+200B
zero-width space at scanned-page boundaries within the running text —
a purely typographic transclusion artifact (113 occurrences across 60
of the 65 stories), never rendered or meaningful as content. It is
stripped, the same way `[Illustration]` tags are stripped from PG
sources.

EXCLUDED: the title page, "Nuggets"-style front matter, Kohut's
Editor's Preface (a 1917 composition, not part of any tale), the Table
of Contents itself, and the "FACETIÆ" section-divider heading (see
above). None of these contain narrative content of the kind this
engine's `stories` table models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from illustration_engine.gutenberg_text import collapse_blank_lines, normalize_line_endings


SOURCE_CODE = "HEBREW_TALES_HURWITZ_KOHUT1917"

_MAIN_TALE_TITLES: tuple[str, ...] = (
    "Moses and the Lamb",
    "The Value of a Good Wife",
    "The Lord Helpeth Man and Beast",
    "Conversation of a Philosopher with a Rabbi",
    "The Princess and Rabbi Joshua",
    "Mercy in Judgment",
    "Blessings in Disguise",
    "Intended Divorce and Reconciliation",
    "The Heavenly Lamp",
    "True Charity Knows no Law",
    "Scripture Impartiality",
    "The Honor Due to Whatever is Truly Useful",
    "To Insult Poverty or Natural Defect, no Venial Crime",
    "Liberality Grounded on Religion not to be Conquered by Reverse Fortune",
    "On Pretended Majorities",
    "On the Mood of Mind that will Render the Consequences of Improper Actions "
    "the Atonement for Them",
    "The Seven Ages",
    "Incorruptible Treasures",
    "Table Talk of the Sages of Israel",
    "Destruction of Wickedness",
    "The Meek and the Haughty",
    "The Heathen and the Hebrew Sages",
    "The Conquest of Meekness",
    "True Charity",
    "Filial Reverence",
    "The Double Moral and Twofold Tale",
    "Compassion Toward the Unhappy",
    "The Legacy of Rabbi Johanan to his Disciples",
    'Milton\'s "Dark from Excess of Light"',
    "The Wilful Drunkard",
    "Do not Provoke those who Throw off Appearances of Justice",
    "The Traveller and the Date-tree of the Oasis",
    "The Aged Planter and Hadrian",
    "The Same Things no Longer the Same under Altered Circumstances",
    "The Preposterous Snake",
    "The Doctrine of Resurrection Supported by that of Creation",
    "The Sufferings of the Jews under Hadrian, I.",
    "Sufferings of the Jews under Hadrian, II",
    "On Vows in Cases Previously Binding on the Conscience",
    "Poverty no Proof of Divine Disfavor",
    "Scrupulous Honesty",
    "The Fox and the Fish",
    "The Climax of Benevolence",
    "Rabbi Simeon and the Jewels",
    "He who Wrongs the Dishonest under the Pretence of their Dishonesty Renders "
    "Himself an Accomplice",
    "Scrupulous Honesty",
    "Reverence for Truth and Simplicity not to be Sacrificed to the Forms of Courtesy",
    "The Twofold Charity of the Benevolent Physician",
    "Folly of Idolatry",
    "Abraham's Deliverance from the Fiery Furnace",
    "No Loss of Dignity from any Innocent Means of Promoting Peace and Harmony",
    "The Lawful Heir",
    "The Fox and the Rift in the Garden-Wall",
    "Alexander and the Female Chief",
    "Ambition Humbled and Reproved",
)

_FACETIAE_TITLES: tuple[str, ...] = (
    "Wit Like Salt",
    'The Word "Us"',
    "The Tailor and the Broken Mortar",
    "Witty Retort of a Hebrew Child",
    "The Inhospitable Jester Taken in his Own Snare",
    "The Enigma that Cost the Athenian his Mantle",
    "The Quadruple Tale",
    "The Athenian and his One-Eyed Slave",
    "The Scientific Carver",
    "No Rule Without Exception",
)

assert len(_MAIN_TALE_TITLES) == 55
assert len(_FACETIAE_TITLES) == 10

_BODY_START_ANCHOR = "HEBREW TALES\n\nMoses and the Lamb"
_FOOTNOTE_SECTION_MARK = "↑"
_FACETIAE_SECTION_HEADER_RE = re.compile(r"FACETIÆ(?:\[\d+\])?\s*")
_INLINE_FOOTNOTE_MARKER_RE = re.compile(r"\[(\d+)\]")
_ZERO_WIDTH_SPACE = "​"

# Verified against this exact edition (see module docstring): footnote 13
# belongs to the "FACETIÆ[13]" section-divider text, not to any single
# tale — it is stripped along with that divider and never reattached to
# a story. A count mismatch anywhere below means the source text changed
# or the parsing logic broke; this parser fails loudly rather than
# silently importing a different set of stories or dropping a footnote.
_SECTION_HEADER_FOOTNOTE_NUMBER = 13
_EXPECTED_FOOTNOTE_COUNT = 15
_EXPECTED_TOTAL_STORIES = 65

_ARTICLES = ("The ", "A ", "An ")
_HEADING_SEARCH_PREFIX_WORDS = 5
_FLEXIBLE_WORD_SEPARATOR = r"""[\s'"‘’“”]*"""


@dataclass(frozen=True)
class ParsedHebrewTale:
    canonical_key: str
    external_ref: str
    title_original: str
    original_text: str


class HebrewTalesParseError(ValueError):
    """The raw text did not match the expected structure for this book."""


def parse_hebrew_tales_text(raw_text: str) -> tuple[ParsedHebrewTale, ...]:
    """Parse the full raw Wikisource plain-text into the 65 narrative
    units (55 tales + 10 Facetiae).

    Raises `HebrewTalesParseError` if the body/footnote-section
    boundaries, any of the 65 expected headings, or the expected
    footnote count/attribution don't match — parsing never silently
    returns a partial or misaligned result.
    """
    text = normalize_line_endings(raw_text)

    body_start = text.find(_BODY_START_ANCHOR)
    if body_start == -1:
        raise HebrewTalesParseError(
            f"{SOURCE_CODE}: could not locate the {_BODY_START_ANCHOR!r} body-start anchor"
        )
    footnote_start = text.find(_FOOTNOTE_SECTION_MARK)
    if footnote_start == -1 or footnote_start <= body_start:
        raise HebrewTalesParseError(
            f"{SOURCE_CODE}: could not locate the footnote-section start marker "
            f"after the story body"
        )

    all_titles: list[tuple[str, str]] = [(t, "TALE") for t in _MAIN_TALE_TITLES] + [
        (t, "FACETIAE") for t in _FACETIAE_TITLES
    ]

    search_from = body_start
    positions: list[int] = []
    for title, kind in all_titles:
        pos = _locate_heading(text, title, search_from)
        if pos is None:
            raise HebrewTalesParseError(
                f"{SOURCE_CODE}: could not locate body heading for {kind} {title!r}"
            )
        positions.append(pos)
        search_from = pos + _HEADING_SEARCH_PREFIX_WORDS * 2

    footnotes_by_number = _parse_footnotes(text, footnote_start)
    if len(footnotes_by_number) != _EXPECTED_FOOTNOTE_COUNT:
        raise HebrewTalesParseError(
            f"{SOURCE_CODE}: expected {_EXPECTED_FOOTNOTE_COUNT} footnotes, "
            f"found {len(footnotes_by_number)}"
        )

    stories: list[ParsedHebrewTale] = []
    consumed_footnote_numbers: set[int] = set()
    tale_index = 0
    facetiae_index = 0

    for index, (title, kind) in enumerate(all_titles):
        pos = positions[index]
        next_pos = positions[index + 1] if index + 1 < len(positions) else footnote_start
        raw_segment = text[pos:next_pos]
        raw_segment = _FACETIAE_SECTION_HEADER_RE.sub("", raw_segment)

        heading_end = raw_segment.find("\n\n")
        if heading_end == -1:
            raise HebrewTalesParseError(
                f"{SOURCE_CODE}: {kind} {title!r} heading has no following blank line"
            )
        heading_text = raw_segment[:heading_end].replace(_ZERO_WIDTH_SPACE, "").strip()
        body_text = raw_segment[heading_end:]

        markers_found = [int(m.group(1)) for m in _INLINE_FOOTNOTE_MARKER_RE.finditer(body_text)]
        body_text = _INLINE_FOOTNOTE_MARKER_RE.sub("", body_text)
        body_text = body_text.replace(_ZERO_WIDTH_SPACE, "")
        body_text = collapse_blank_lines(body_text).strip()
        if not body_text:
            raise HebrewTalesParseError(f"{SOURCE_CODE}: {kind} {title!r} is empty after cleaning")

        footnote_paragraphs = []
        for number in markers_found:
            if number not in footnotes_by_number:
                raise HebrewTalesParseError(
                    f"{SOURCE_CODE}: {kind} {title!r} references unknown footnote [{number}]"
                )
            footnote_paragraphs.append(f"[{number}] {footnotes_by_number[number]}")
            consumed_footnote_numbers.add(number)

        full_text = "\n\n".join([heading_text, body_text, *footnote_paragraphs])

        if kind == "TALE":
            tale_index += 1
            external_ref = f"TALE/{tale_index:02d}"
        else:
            facetiae_index += 1
            external_ref = f"FACETIAE/{facetiae_index:02d}"

        position = index + 1
        stories.append(
            ParsedHebrewTale(
                canonical_key=f"{position:03d}",
                external_ref=external_ref,
                title_original=heading_text,
                original_text=full_text,
            )
        )

    unaccounted = (
        set(footnotes_by_number) - consumed_footnote_numbers - {_SECTION_HEADER_FOOTNOTE_NUMBER}
    )
    if unaccounted:
        raise HebrewTalesParseError(
            f"{SOURCE_CODE}: footnote(s) never matched to any story: {sorted(unaccounted)}"
        )
    if _SECTION_HEADER_FOOTNOTE_NUMBER in consumed_footnote_numbers:
        raise HebrewTalesParseError(
            f"{SOURCE_CODE}: section-header footnote "
            f"[{_SECTION_HEADER_FOOTNOTE_NUMBER}] unexpectedly attached to a story "
            "— the FACETIÆ-header-stripping regex may have stopped matching"
        )

    if len(stories) != _EXPECTED_TOTAL_STORIES:
        raise HebrewTalesParseError(
            f"{SOURCE_CODE}: expected {_EXPECTED_TOTAL_STORIES} stories, found {len(stories)}"
        )

    return tuple(stories)


def parse_hebrew_tales_file(path: str | Path) -> tuple[ParsedHebrewTale, ...]:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_hebrew_tales_text(raw_text)


def _locate_heading(text: str, title: str, search_from: int) -> int | None:
    for candidate in (title, _strip_leading_article(title)):
        words = candidate.split()[:_HEADING_SEARCH_PREFIX_WORDS]
        if not words:
            continue
        pattern = re.compile(
            _FLEXIBLE_WORD_SEPARATOR.join(re.escape(w) for w in words), re.IGNORECASE
        )
        match = pattern.search(text, search_from)
        if match:
            return match.start()
    return None


def _strip_leading_article(title: str) -> str:
    for article in _ARTICLES:
        if title.startswith(article):
            return title[len(article) :]
    return title


def _parse_footnotes(text: str, footnote_start: int) -> dict[int, str]:
    footnote_block = text[footnote_start:]
    end = footnote_block.find("This work is a translation")
    if end != -1:
        footnote_block = footnote_block[:end]
    pieces = [p.strip() for p in footnote_block.split(_FOOTNOTE_SECTION_MARK) if p.strip()]
    return {
        number: collapse_blank_lines(piece.replace(_ZERO_WIDTH_SPACE, "")).strip()
        for number, piece in enumerate(pieces, start=1)
    }


__all__ = [
    "SOURCE_CODE",
    "HebrewTalesParseError",
    "ParsedHebrewTale",
    "parse_hebrew_tales_file",
    "parse_hebrew_tales_text",
]
