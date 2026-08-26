"""Shared helpers for parsing raw Project Gutenberg plain-text files.

Used by both `jataka_parser.py` and `aesop_parser.py`. Kept intentionally
minimal: only the PG boilerplate boundary extraction and blank-line
normalization are byte-for-byte identical logic across both sources —
everything about how a given book's individual stories are delimited
(headers, numbering, back-matter) is source-specific and stays in that
book's own parser module. This module exists because the PG start/end
marker extraction was found duplicated verbatim between the Jataka and
Aesop parsers while implementing the latter, not because a generic
"Gutenberg parser framework" was planned in advance.
"""

from __future__ import annotations

import re


_PG_START_RE = re.compile(r"\*\*\*\s*START OF THE PROJECT GUTENBERG EBOOK[^\n]*\*\*\*")
_PG_END_RE = re.compile(r"\*\*\*\s*END OF THE PROJECT GUTENBERG EBOOK[^\n]*\*\*\*")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


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


__all__ = [
    "GutenbergBoilerplateError",
    "collapse_blank_lines",
    "extract_pg_body",
    "normalize_line_endings",
]
