"""Shared Bible passage reference normalization and overlap helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sys
from types import SimpleNamespace

if "requests" not in sys.modules:
    try:
        import requests as _requests  # noqa: F401
    except ImportError:  # pragma: no cover - local test environment only
        sys.modules["requests"] = SimpleNamespace(
            ConnectionError=ConnectionError,
            Timeout=TimeoutError,
            get=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("requests is not installed")
            ),
        )

from ruf_bible_service import ParsedReference, parse_bible_reference


@dataclass(frozen=True)
class PassageSpan:
    book_code: str
    start_chapter: int
    start_verse: int
    end_chapter: int
    end_verse: int


def is_valid_cross_chapter_reference(reference: str) -> bool:
    match = re.fullmatch(r"\s*(.+?)\s+(\d+),(\d+)-(\d+),(\d+)\s*", reference)
    if not match:
        return False
    book, start_chapter, start_verse, end_chapter, end_verse = match.groups()
    if int(end_chapter) < int(start_chapter):
        return False
    try:
        start = parse_bible_reference(f"{book} {start_chapter},{start_verse}")
        end = parse_bible_reference(f"{book} {end_chapter},{end_verse}")
    except ValueError:
        return False
    return start.book.code == end.book.code


def passage_span(reference: str | None) -> PassageSpan | None:
    raw = str(reference or "").strip()
    if not raw:
        return None
    cross_chapter = re.fullmatch(r"\s*(.+?)\s+(\d+),(\d+)-(\d+),(\d+)\s*", raw)
    if cross_chapter:
        book, start_chapter, start_verse, end_chapter, end_verse = cross_chapter.groups()
        start = parse_bible_reference(f"{book} {start_chapter},{start_verse}")
        end = parse_bible_reference(f"{book} {end_chapter},{end_verse}")
        if start.book.code != end.book.code:
            return None
        return PassageSpan(
            book_code=start.book.code,
            start_chapter=int(start_chapter),
            start_verse=int(start_verse),
            end_chapter=int(end_chapter),
            end_verse=int(end_verse),
        )
    try:
        parsed = parse_bible_reference(raw)
    except ValueError:
        return None
    start_verse = parsed.verse_start or 1
    end_verse = parsed.verse_end or parsed.verse_start or 999
    return PassageSpan(
        book_code=parsed.book.code,
        start_chapter=parsed.chapter,
        start_verse=start_verse,
        end_chapter=parsed.chapter,
        end_verse=end_verse,
    )


def passage_refs_overlap(left: str | None, right: str | None) -> bool:
    left_span = passage_span(left)
    right_span = passage_span(right)
    if left_span is None or right_span is None:
        return False
    if left_span.book_code != right_span.book_code:
        return False
    left_start = (left_span.start_chapter, left_span.start_verse)
    left_end = (left_span.end_chapter, left_span.end_verse)
    right_start = (right_span.start_chapter, right_span.start_verse)
    right_end = (right_span.end_chapter, right_span.end_verse)
    return left_start <= right_end and right_start <= left_end


__all__ = [
    "ParsedReference",
    "PassageSpan",
    "is_valid_cross_chapter_reference",
    "parse_bible_reference",
    "passage_refs_overlap",
    "passage_span",
]
