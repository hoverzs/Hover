"""Canonical scripture reference parsing and serialization."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from textus_kb.books import (
    BOOKS,
    ENGLISH_OSIS_ALIASES,
    OSIS_BY_ID,
    RUF_TO_OSIS,
    BookRecord,
)


class CanonicalReferenceError(ValueError):
    """Raised when a reference string cannot be parsed or validated."""


@dataclass(frozen=True)
class CanonicalReference:
    """Immutable passage span keyed by stable OSIS-like book id.

    Future versification mappings (ENG/ORG/RUF) attach externally via
    ``versification_scheme`` metadata — not embedded in this phase.
    """

    book_id: str
    start_chapter: int
    start_verse: int
    end_chapter: int
    end_verse: int
    versification_scheme: str | None = None

    @property
    def book(self) -> BookRecord:
        record = OSIS_BY_ID.get(self.book_id)
        if record is None:
            raise CanonicalReferenceError(f"Unknown canonical book id: {self.book_id!r}")
        return record

    @property
    def is_single_verse(self) -> bool:
        return (
            self.start_chapter == self.end_chapter
            and self.start_verse == self.end_verse
        )

    @property
    def ruf_book_code(self) -> str:
        return self.book.ruf_code

    def canonical_string(self) -> str:
        """Deterministic internal serialization, e.g. ``John.4.1-42``."""
        if self.is_single_verse:
            return f"{self.book_id}.{self.start_chapter}.{self.start_verse}"
        if self.start_chapter == self.end_chapter:
            return (
                f"{self.book_id}.{self.start_chapter}."
                f"{self.start_verse}-{self.end_verse}"
            )
        return (
            f"{self.book_id}.{self.start_chapter}.{self.start_verse}-"
            f"{self.end_chapter}.{self.end_verse}"
        )

    def __str__(self) -> str:
        return self.canonical_string()

    @classmethod
    def parse(cls, text: str) -> CanonicalReference:
        raw = (text or "").strip()
        if not raw:
            raise CanonicalReferenceError("Empty reference string.")
        normalized = _normalize_dashes(raw)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        last_error: CanonicalReferenceError | None = None
        for parser in (
            _parse_osis_dotted,
            _parse_spaced_reference,
        ):
            try:
                return parser(normalized)
            except CanonicalReferenceError as exc:
                message = str(exc)
                if message.startswith("Not OSIS dotted form.") or message.startswith(
                    "Cannot parse reference span:"
                ):
                    last_error = exc
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise CanonicalReferenceError(f"Unrecognized reference format: {text!r}")

    @classmethod
    def from_ruf_parsed(
        cls,
        *,
        ruf_book_code: str,
        chapter: int,
        verse_start: int | None,
        verse_end: int | None,
        versification_scheme: str | None = None,
    ) -> CanonicalReference:
        book_id = RUF_TO_OSIS.get((ruf_book_code or "").upper())
        if book_id is None:
            raise CanonicalReferenceError(f"Unknown RUF book code: {ruf_book_code!r}")
        record = OSIS_BY_ID[book_id]
        if verse_start is None:
            raise CanonicalReferenceError(
                f"Verse number required for canonical reference ({ruf_book_code})."
            )
        start_chapter = 1 if record.single_chapter else chapter
        end_chapter = start_chapter if record.single_chapter else chapter
        end_verse = verse_end if verse_end is not None else verse_start
        return _build(
            book_id,
            start_chapter,
            verse_start,
            end_chapter,
            end_verse,
            versification_scheme=versification_scheme,
        )


def _normalize_dashes(text: str) -> str:
    return (
        text.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
    )


def _fold_token(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_ish = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return re.sub(r"[\s._]+", "", ascii_ish.casefold())


def _resolve_book_token(token: str) -> str:
    cleaned = (token or "").strip().rstrip(".")
    if not cleaned:
        raise CanonicalReferenceError("Missing book name or code.")

    upper = cleaned.upper()
    if upper in RUF_TO_OSIS:
        return RUF_TO_OSIS[upper]

    folded = _fold_token(cleaned)
    if not folded:
        raise CanonicalReferenceError(f"Unknown book: {token!r}")

    for book in BOOKS:
        candidates = (
            book.osis_id,
            book.ruf_code,
            book.osis_id.lower(),
        )
        for candidate in candidates:
            if _fold_token(candidate) == folded:
                return book.osis_id

    for alias, osis_id in ENGLISH_OSIS_ALIASES.items():
        if _fold_token(alias) == folded:
            return osis_id

    try:
        from ruf_bible_service import BOOK_LOOKUP

        info = BOOK_LOOKUP.get(_fold_token(cleaned))
        if info is not None:
            mapped = RUF_TO_OSIS.get(info.code)
            if mapped:
                return mapped
    except ImportError:
        pass

    raise CanonicalReferenceError(f"Unknown book: {token!r}")


def _validate_span(
    *,
    book_id: str,
    start_chapter: int,
    start_verse: int,
    end_chapter: int,
    end_verse: int,
) -> None:
    record = OSIS_BY_ID.get(book_id)
    if record is None:
        raise CanonicalReferenceError(f"Unknown book id: {book_id!r}")
    if start_chapter < 1 or end_chapter < 1:
        raise CanonicalReferenceError("Chapter number must be >= 1.")
    if start_verse < 1 or end_verse < 1:
        raise CanonicalReferenceError("Verse number must be >= 1.")
    if (end_chapter, end_verse) < (start_chapter, start_verse):
        raise CanonicalReferenceError("Reversed reference range.")
    if record.single_chapter and start_chapter != 1:
        raise CanonicalReferenceError(
            f"{book_id} is a single-chapter book; chapter must be 1."
        )


def _build(
    book_id: str,
    start_chapter: int,
    start_verse: int,
    end_chapter: int,
    end_verse: int,
    *,
    versification_scheme: str | None = None,
) -> CanonicalReference:
    _validate_span(
        book_id=book_id,
        start_chapter=start_chapter,
        start_verse=start_verse,
        end_chapter=end_chapter,
        end_verse=end_verse,
    )
    return CanonicalReference(
        book_id=book_id,
        start_chapter=start_chapter,
        start_verse=start_verse,
        end_chapter=end_chapter,
        end_verse=end_verse,
        versification_scheme=versification_scheme,
    )


def _parse_int(value: str, *, field: str) -> int:
    if not value.isdigit():
        raise CanonicalReferenceError(f"Invalid {field}: {value!r}")
    return int(value)


def _parse_osis_dotted(text: str) -> CanonicalReference:
    # John.4.1-42 or John.4.1-John.4.42 or John.4.16
    match = re.fullmatch(
        r"(?P<book>[A-Za-z0-9]+)\."
        r"(?P<chapter>\d+)\."
        r"(?P<start>\d+)"
        r"(?:-(?:(?P<end_book>[A-Za-z0-9]+)\.)?(?P<end_chapter>\d+)\.(?P<end_verse>\d+)|-(?P<end_same>\d+))?",
        text,
    )
    if not match:
        raise CanonicalReferenceError("Not OSIS dotted form.")

    book_token = match.group("book")
    book_id = _resolve_book_token(book_token)
    chapter = _parse_int(match.group("chapter"), field="chapter")
    start_verse = _parse_int(match.group("start"), field="verse")

    if match.group("end_same") is not None:
        end_verse = _parse_int(match.group("end_same"), field="verse")
        return _build(book_id, chapter, start_verse, chapter, end_verse)

    if match.group("end_chapter") is not None:
        end_book_token = match.group("end_book") or book_token
        end_book_id = _resolve_book_token(end_book_token)
        if end_book_id != book_id:
            raise CanonicalReferenceError("Cross-book ranges are not supported.")
        end_chapter = _parse_int(match.group("end_chapter"), field="chapter")
        end_verse = _parse_int(match.group("end_verse"), field="verse")
        return _build(book_id, chapter, start_verse, end_chapter, end_verse)

    return _build(book_id, chapter, start_verse, chapter, start_verse)


def _parse_spaced_reference(text: str) -> CanonicalReference:
    # Delegate Hungarian / mixed references to RUF parser when possible.
    try:
        from ruf_bible_service import parse_bible_reference

        parsed = parse_bible_reference(text.replace(":", ","))
        return CanonicalReference.from_ruf_parsed(
            ruf_book_code=parsed.book.code,
            chapter=parsed.chapter,
            verse_start=parsed.verse_start,
            verse_end=parsed.verse_end,
        )
    except ValueError as exc:
        message = str(exc)
        if "Fordított" in message or "fordított" in message.lower():
            raise CanonicalReferenceError("Reversed reference range.") from exc

    # Manual parse: BOOK rest (JHN 4:1-42, John 4:1-42)
    match = re.match(
        r"^(?P<book>.+?)\s+"
        r"(?P<rest>\d.+)$",
        text,
    )
    if not match:
        raise CanonicalReferenceError(f"Cannot parse reference span: {text!r}")

    book_id = _resolve_book_token(match.group("book").strip())
    rest = match.group("rest").replace(":", ",")
    rest = re.sub(r"\s+", "", rest)

    cross = re.fullmatch(
        r"(?P<sc>\d+),(?P<sv>\d+)-(?P<ec>\d+),(?P<ev>\d+)",
        rest,
    )
    if cross:
        return _build(
            book_id,
            _parse_int(cross.group("sc"), field="chapter"),
            _parse_int(cross.group("sv"), field="verse"),
            _parse_int(cross.group("ec"), field="chapter"),
            _parse_int(cross.group("ev"), field="verse"),
        )

    range_match = re.fullmatch(
        r"(?P<chapter>\d+),(?P<start>\d+)-(?P<end>\d+)",
        rest,
    )
    if range_match:
        chapter = _parse_int(range_match.group("chapter"), field="chapter")
        return _build(
            book_id,
            chapter,
            _parse_int(range_match.group("start"), field="verse"),
            chapter,
            _parse_int(range_match.group("end"), field="verse"),
        )

    single = re.fullmatch(r"(?P<chapter>\d+),(?P<verse>\d+)", rest)
    if single:
        chapter = _parse_int(single.group("chapter"), field="chapter")
        verse = _parse_int(single.group("verse"), field="verse")
        return _build(book_id, chapter, verse, chapter, verse)

    raise CanonicalReferenceError(f"Cannot parse reference span: {text!r}")
