"""Shared accent-/case-fold matching helpers for 19th-century Hungarian
Project Gutenberg folktale collections (currently: `arany_laszlo_parser.py`,
`merenyi_laszlo_parser.py`).

Extracted after the SECOND such source (Merényi László) confirmed the
same concrete need already found in the first (Arany László): these
editions' ALL-CAPS body headings carry period-typesetting/OCR
irregularities — dropped accents on capital letters, occasional
sentence-case instead of true caps, and (in Merényi's case) a trailing
footnote-reference bracket fused onto the heading — that a verbatim or
merely whitespace-tolerant match (as used for the English-language
Jataka/Aesop sources) would miss. Rather than hand-tolerating each
irregularity per book, every title (and the whole book body, once) is
run through `fold_preserving_length`, then matched with
`heading_pattern`. This is NOT a general "Hungarian text" or "folktale
framework" — it is exactly the one proven technique, shared because two
real sources needed it identically; each book's own parser module still
owns 100% of its title list, section boundaries, and back-matter rules.
"""

from __future__ import annotations

import re
import unicodedata


def fold_preserving_length(text: str) -> str:
    """Accent- and case-folds `text` one character at a time so the
    result has the exact same length (and therefore the same offsets)
    as the input — Hungarian precomposed accented letters always
    NFKD-decompose into exactly one base letter plus one combining mark,
    so stripping the combining mark yields exactly one folded character
    per input character. This lets a match found in the folded text be
    used directly as an offset into the original, unfolded text."""
    return "".join(_fold_char(ch) for ch in text)


def heading_pattern(title: str) -> re.Pattern[str]:
    """A standalone-heading regex for `title`, tolerant of (a) accent-
    dropping and case irregularities (via `fold_preserving_length` — the
    caller must fold the text being searched the same way), (b) the
    title wrapping across a line break at any word boundary, (c) an
    optional trailing `.`/`?`/`!`, and (d) an optional trailing
    footnote-reference bracket like `[101]` fused onto the heading."""
    words = fold_preserving_length(title).split()
    body_pattern = r"\s+".join(re.escape(word) for word in words)
    return re.compile(rf"^[ \t]*{body_pattern}[?.!]?(?:\[[0-9]+\])?[ \t]*$", re.MULTILINE)


def _fold_char(ch: str) -> str:
    decomposed = unicodedata.normalize("NFKD", ch)
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    folded = (base or ch).casefold()
    return folded if len(folded) == 1 else ch.casefold()[:1]


__all__ = ["fold_preserving_length", "heading_pattern"]
