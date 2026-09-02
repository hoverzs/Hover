from __future__ import annotations

from pathlib import Path

import pytest

from illustration_engine.aesop_parser import (
    AesopParseError,
    parse_aesop_file,
    parse_aesop_text,
)
from illustration_engine.paths import RAW_DATA_DIR


AESOP_SOURCE = RAW_DATA_DIR / "pg21_aesops_fables.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Aesop source not present locally: {path}")
    return path


def test_fable_count_matches_contents_listing() -> None:
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    assert len(fables) == 313


def test_first_and_last_fable() -> None:
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    assert fables[0].external_ref == "1"
    assert fables[0].title_original == "The Lion And The Mouse"
    assert fables[-1].external_ref == "313"
    assert fables[-1].title_original == "The Brazier and His Dog"


def test_fable_text_segmentation_does_not_bleed_across_boundary() -> None:
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    first_text = fables[0].original_text
    assert "A LION was awakened from sleep by a Mouse" in first_text
    assert "The Wolf And The Lamb" not in first_text
    assert "WOLF, meeting with a Lamb astray" not in first_text

    second_text = fables[1].original_text
    assert "WOLF, meeting with a Lamb astray" in second_text
    assert "The Lion And The Mouse" not in second_text


def test_fable_text_excludes_gutenberg_boilerplate() -> None:
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    joined = "\n".join(fable.original_text for fable in fables)
    forbidden = (
        "PROJECT GUTENBERG",
        "This eBook is for the use of anyone",
        "TRANSLATOR",
        "GEORGE ROUTLEDGE",
    )
    for marker in forbidden:
        assert marker.upper() not in joined.upper(), f"leaked boilerplate marker: {marker!r}"


def test_fable_text_excludes_front_and_back_matter() -> None:
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    joined = "\n".join(fable.original_text for fable in fables)
    assert "The Tale, the Parable, and the Fable are all common" not in joined  # PREFACE
    assert "was prefixed to all the early editions" not in joined  # LIFE OF AESOP
    assert "(return)" not in joined  # FOOTNOTES back matter


def test_fable_titles_are_derived_from_contents_not_hardcoded() -> None:
    """Sanity check that titles came from the CONTENTS block itself: the
    derived list must have no leading/trailing whitespace and must not
    include the front-/back-matter section headers."""
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    titles = [fable.title_original for fable in fables]
    for non_fable_marker in ("PREFACE", "LIFE OF AESOP", "AESOP’S FABLES", "FOOTNOTES", "INDEX"):
        assert non_fable_marker not in titles
    assert all(title == title.strip() for title in titles)


def test_duplicate_titles_are_kept_as_distinct_fables_with_unique_keys() -> None:
    """This edition genuinely has multiple distinct fables sharing the
    same title (e.g. two different "The Wolf and the Lion" fables) — the
    parser must keep both, distinguished by canonical_key, not collapse
    or misorder them."""
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    titles = [fable.title_original for fable in fables]
    assert titles.count("The Wolf and the Lion") == 2

    keys = [fable.canonical_key for fable in fables]
    assert len(keys) == len(set(keys))


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    fables = parse_aesop_file(_require(AESOP_SOURCE))
    keys = [fable.canonical_key for fable in fables]
    assert keys == [f"{i:03d}" for i in range(1, len(fables) + 1)]
    assert [fable.external_ref for fable in fables] == [str(i) for i in range(1, len(fables) + 1)]


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(AESOP_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_aesop_text(raw_text)
    second_pass = parse_aesop_text(raw_text)
    assert first_pass == second_pass


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(AesopParseError):
        parse_aesop_text("no PG markers in this text at all")


def test_parse_raises_on_missing_contents_heading() -> None:
    raw_text = _require(AESOP_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("CONTENTS", "TABLE OF CONTENTS")
    with pytest.raises(AesopParseError):
        parse_aesop_text(mutilated)


def test_parse_raises_on_missing_expected_fable_title() -> None:
    raw_text = _require(AESOP_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace(
        "The Lion And The Mouse", "Something Else Entirely", 1
    )
    with pytest.raises(AesopParseError):
        parse_aesop_text(mutilated)
