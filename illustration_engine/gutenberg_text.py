"""Shared helpers for parsing raw Project Gutenberg plain-text files.

Used by `jataka_parser.py`, `aesop_parser.py`, and `baldwin_parser.py`.
Kept intentionally minimal: only logic found byte-for-byte duplicated
across at least two real sources lives here — everything about how a
given book's individual stories are delimited (headers, numbering,
back-matter) is source-specific and stays in that book's own parser
module. The PG boilerplate boundary extraction and blank-line
normalization were duplicated between Jataka and Aesop; the
illustration-tag and trailing-PG-colophon stripping were duplicated
between Jataka and Baldwin. None of this was planned as a generic
"Gutenberg parser framework" in advance — every addition here followed a
second real source needing the exact same thing.
"""

from __future__ import annotations

import re


_PG_START_RE = re.compile(r"\*\*\*\s*START OF THE PROJECT GUTENBERG EBOOK[^\n]*\*\*\*")
_PG_END_RE = re.compile(r"\*\*\*\s*END OF THE PROJECT GUTENBERG EBOOK[^\n]*\*\*\*")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_ILLUSTRATION_RE = re.compile(r"\[Illustration[^\]]*\]")
_TRAILING_PG_COLOPHON_RE = re.compile(
    r"\n+End of (?:the )?Project Gutenberg.*\Z", re.IGNORECASE | re.DOTALL
)


class GutenbergBoilerplateError(ValueError):
    """The raw text is missing the expected PG START/END boilerplate markers."""


def normalize_line_endings(raw_text: str) -> str:
    return raw_text.replace("\r\n", "\n").replace("\r", "\n")


def extract_pg_body(raw_text: str, *, source_label: str = "source") -> str:
    """Returns the text strictly between the PG START and END markers.

    Raises `GutenbergBoilerplateError` if either marker is missing or out
    of order — callers should never fall back to parsing the full raw
    text (which would risk treating PG's own license text as content).
    """
    text = normalize_line_endings(raw_text)
    start_match = _PG_START_RE.search(text)
    end_match = _PG_END_RE.search(text)
    if not start_match or not end_match or start_match.end() >= end_match.start():
        raise GutenbergBoilerplateError(
            f"{source_label}: could not locate PG START/END boilerplate markers"
        )
    return text[start_match.end() : end_match.start()]


def collapse_blank_lines(text: str) -> str:
    return _MULTI_BLANK_RE.sub("\n\n", text)


def strip_illustration_tags(text: str) -> str:
    """Removes `[Illustration ...]` image-placeholder markers — a PG
    transcription artifact, not prose content."""
    return _ILLUSTRATION_RE.sub("", text)


def strip_trailing_pg_colophon(text: str) -> str:
    """Removes a trailing "End of Project Gutenberg's <title>, by
    <author>" colophon line some PG editions repeat right before the
    START/END markers wrap it, if it ended up inside a sliced story's
    tail."""
    return _TRAILING_PG_COLOPHON_RE.sub("", text)


__all__ = [
    "GutenbergBoilerplateError",
    "collapse_blank_lines",
    "extract_pg_body",
    "normalize_line_endings",
    "strip_illustration_tags",
    "strip_trailing_pg_colophon",
]
