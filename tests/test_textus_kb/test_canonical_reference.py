"""Tests for CanonicalReference parsing and serialization."""

from __future__ import annotations

import pytest

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Jn 4,1–42", "John.4.1-42"),
        ("Jn 4:1-42", "John.4.1-42"),
        ("JHN 4:1-42", "John.4.1-42"),
        ("John 4:1-42", "John.4.1-42"),
        ("John.4.1-42", "John.4.1-42"),
        ("Jn 4,16", "John.4.16"),
        ("JHN 4,16", "John.4.16"),
    ],
)
def test_required_input_formats_normalize(raw: str, expected: str) -> None:
    ref = CanonicalReference.parse(raw)
    assert ref.canonical_string() == expected


def test_hungarian_book_names() -> None:
    assert CanonicalReference.parse("1Móz 1,1").canonical_string() == "Gen.1.1"
    assert CanonicalReference.parse("Róm 8,28").canonical_string() == "Rom.8.28"
    assert CanonicalReference.parse("ApCsel 2,1").canonical_string() == "Acts.2.1"
    assert CanonicalReference.parse("Zsolt 23,1").canonical_string() == "Ps.23.1"


def test_english_book_names() -> None:
    assert CanonicalReference.parse("Genesis 1,1").canonical_string() == "Gen.1.1"
    assert CanonicalReference.parse("Matthew 5,3").canonical_string() == "Matt.5.3"
    assert CanonicalReference.parse("Revelation 1,1").canonical_string() == "Rev.1.1"


def test_internal_ruf_codes() -> None:
    ref = CanonicalReference.parse("1CO 13,4-7")
    assert ref.book_id == "1Cor"
    assert ref.ruf_book_code == "1CO"
    assert ref.canonical_string() == "1Cor.13.4-7"


def test_single_verse_property() -> None:
    ref = CanonicalReference.parse("Jn 3,16")
    assert ref.is_single_verse is True
    assert ref.canonical_string() == "John.3.16"


def test_verse_range_same_chapter() -> None:
    ref = CanonicalReference.parse("Jn 4,1-42")
    assert ref.start_chapter == 4
    assert ref.start_verse == 1
    assert ref.end_chapter == 4
    assert ref.end_verse == 42
    assert ref.is_single_verse is False


def test_cross_chapter_range() -> None:
    ref = CanonicalReference.parse("Jn 4,1-5,10")
    assert ref.canonical_string() == "John.4.1-5.10"


def test_whitespace_and_dash_variants() -> None:
    assert (
        CanonicalReference.parse("  Jn   4 , 1 - 42 ").canonical_string()
        == "John.4.1-42"
    )
    assert CanonicalReference.parse("Jn 4,1—42").canonical_string() == "John.4.1-42"


def test_deterministic_roundtrip() -> None:
    first = CanonicalReference.parse("Jn 4,1–42")
    second = CanonicalReference.parse(first.canonical_string())
    assert first == second
    assert first.canonical_string() == second.canonical_string()


def test_str_uses_canonical_form() -> None:
    assert str(CanonicalReference.parse("Jn 4,1-42")) == "John.4.1-42"


def test_invalid_book_raises() -> None:
    with pytest.raises(CanonicalReferenceError, match="Unknown book"):
        CanonicalReference.parse("NotABook 1,1")


def test_invalid_chapter_raises() -> None:
    with pytest.raises(CanonicalReferenceError, match="Chapter"):
        CanonicalReference.from_ruf_parsed(
            ruf_book_code="JHN",
            chapter=0,
            verse_start=1,
            verse_end=1,
        )


def test_invalid_verse_raises() -> None:
    with pytest.raises(CanonicalReferenceError, match="Verse"):
        CanonicalReference.from_ruf_parsed(
            ruf_book_code="JHN",
            chapter=1,
            verse_start=0,
            verse_end=1,
        )


def test_reversed_range_raises() -> None:
    with pytest.raises(CanonicalReferenceError, match="Reversed"):
        CanonicalReference.parse("Jn 4,10-1")


def test_unparseable_format_raises() -> None:
    with pytest.raises(CanonicalReferenceError):
        CanonicalReference.parse("???")
    with pytest.raises(CanonicalReferenceError):
        CanonicalReference.parse("")


def test_single_chapter_book() -> None:
    ref = CanonicalReference.parse("Júd 1,3")
    assert ref.book_id == "Jude"
    assert ref.canonical_string() == "Jude.1.3"


def test_versification_scheme_optional_field() -> None:
    ref = CanonicalReference.parse("Jn 4,1")
    assert ref.versification_scheme is None
