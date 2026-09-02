from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from illustration_engine.gulistan_parser import (
    GulistanParseError,
    parse_gulistan_file,
    parse_gulistan_text,
)
from illustration_engine.paths import RAW_DATA_DIR


GULISTAN_SOURCE = RAW_DATA_DIR / "pg13060_persian_literature_vol2_gulistan.txt"

_EXPECTED_CHAPTER_COUNTS = {
    "I": 35,
    "II": 38,
    "III": 24,
    "IV": 12,
    "V": 15,
    "VI": 6,
    "VII": 17,
}


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Gulistan source not present locally: {path}")
    return path


def test_story_count() -> None:
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    assert len(stories) == 147


def test_per_chapter_story_counts() -> None:
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    counts: dict[str, int] = {}
    for story in stories:
        chapter = story.external_ref.split("/")[0]
        counts[chapter] = counts.get(chapter, 0) + 1
    assert counts == _EXPECTED_CHAPTER_COUNTS


def test_first_and_last_story() -> None:
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    assert stories[0].canonical_key == "001"
    assert stories[0].external_ref == "I/I"
    assert stories[0].title_original == "Of the Customs of Kings"
    assert stories[0].original_text.startswith("I have heard of a king who made the sign")

    assert stories[-1].canonical_key == "147"
    assert stories[-1].external_ref == "VII/XXI"
    assert stories[-1].title_original == "Of the Impressions of Education"
    assert stories[-1].original_text.endswith('enjoy this world and the next."')


def test_story_boundaries_do_not_bleed() -> None:
    """The first story (I/I) must not swallow the opening of the second
    (I/II) — each numbered unit's text must stop exactly at the next
    bare-numeral heading."""
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    first = next(s for s in stories if s.external_ref == "I/I")
    second = next(s for s in stories if s.external_ref == "I/II")
    assert second.original_text.split("\n", 1)[0] not in first.original_text


def test_title_original_is_the_shared_chapter_subtitle_not_invented_per_story() -> None:
    """No per-story titles exist in this source (see module docstring) —
    `title_original` must be the genuine chapter subtitle, identical for
    every story within the same chapter."""
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    chapter_ii_titles = {s.title_original for s in stories if s.external_ref.startswith("II/")}
    assert chapter_ii_titles == {"Of the Morals of Dervishes"}


def test_missing_section_asterisk_markers_stripped() -> None:
    """Chapter V genuinely skips from numeral I to III (Ross's own
    translator's note explains a section was left untranslated, marked
    in the source by a row of asterisks) — that row must not leak into
    any story's `original_text`."""
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "*       *       *       *       *" not in joined
    chapter_v_numerals = [
        s.external_ref.split("/")[1] for s in stories if s.external_ref.startswith("V/")
    ]
    assert chapter_v_numerals[0] == "I"
    assert chapter_v_numerals[1] == "III"


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    keys = [s.canonical_key for s in stories]
    assert keys == [f"{i:03d}" for i in range(1, len(stories) + 1)]
    assert len(set(s.external_ref for s in stories)) == len(stories)


def test_chapter_viii_aphorisms_excluded() -> None:
    """Chapter VIII ('Of the Duties of Society') is a structural
    exclusion — its units are overwhelmingly bare gnomic maxims, not
    narrative anecdotes (see module docstring). None of its content may
    appear in the parsed corpus."""
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "Riches are intended for the comfort of life" not in joined
    assert not any(s.title_original == "Of the Duties of Society" for s in stories)


def test_contents_listing_and_gottheil_introduction_excluded() -> None:
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "disjointed paragraphs, generally beginning with" not in joined
    assert " III.  On the Preciousness of Contentment" not in joined


def test_gutenberg_boilerplate_excluded() -> None:
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "PROJECT GUTENBERG" not in joined.upper()


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(GULISTAN_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_gulistan_text(raw_text)
    second_pass = parse_gulistan_text(raw_text)
    assert first_pass == second_pass


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(GulistanParseError):
        parse_gulistan_text("no PG markers in this text at all")


def test_parse_raises_on_missing_chapter_heading() -> None:
    raw_text = _require(GULISTAN_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("CHAPTER IV", "CHAPTER FOUR", 1)
    with pytest.raises(GulistanParseError, match="CHAPTER IV"):
        parse_gulistan_text(mutilated)


def test_parse_raises_on_story_count_mismatch() -> None:
    raw_text = _require(GULISTAN_SOURCE).read_text(encoding="utf-8")
    # Delete chapter VI's first story-numeral heading (the bare "I" line
    # immediately after "Of Imbecility and Old Age"), dropping its count
    # from the expected 6 to 5.
    marker = "Of Imbecility and Old Age\n\n\nI\n\nIn the metropolitan mosque"
    assert raw_text.count(marker) == 1
    mutilated = raw_text.replace(
        marker, "Of Imbecility and Old Age\n\nIn the metropolitan mosque", 1
    )
    assert mutilated != raw_text
    with pytest.raises(GulistanParseError, match="expected 6"):
        parse_gulistan_text(mutilated)


def test_parse_raises_on_non_increasing_numerals() -> None:
    raw_text = _require(GULISTAN_SOURCE).read_text(encoding="utf-8")
    # Chapter V genuinely jumps I -> III (a translator's-note-documented
    # omission); corrupt that III into a I so the sequence becomes
    # I, I, IV... (not strictly increasing) within chapter V only (the
    # bare "III" heading also occurs, unrelatedly, elsewhere in the
    # book, so the substitution is scoped to chapter V's own region).
    chapter_v_start = raw_text.find("CHAPTER V\n\nOn Love and Youth")
    chapter_vi_start = raw_text.find("CHAPTER VI\n")
    assert 0 < chapter_v_start < chapter_vi_start
    region = raw_text[chapter_v_start:chapter_vi_start]
    corrupted_region = region.replace("\n\nIII\n\n", "\n\nI\n\n", 1)
    assert corrupted_region != region
    mutilated = raw_text[:chapter_v_start] + corrupted_region + raw_text[chapter_vi_start:]
    with pytest.raises(GulistanParseError, match="strictly increasing"):
        parse_gulistan_text(mutilated)


def test_length_statistics_consistency() -> None:
    """Corpus-quality metric required by Phase 2K: report the length
    distribution against the project's stated ideal band and assert it
    stays internally consistent (bucket counts sum to the total)."""
    stories = parse_gulistan_file(_require(GULISTAN_SOURCE))
    lens = [len(s.original_text) for s in stories]

    too_short = sum(1 for l in lens if l < 200)
    ideal = sum(1 for l in lens if 200 <= l <= 1500)
    usable = sum(1 for l in lens if 1501 <= l <= 3000)
    too_long = sum(1 for l in lens if l > 3000)
    assert too_short + ideal + usable + too_long == len(stories)

    assert too_short == 1
    assert ideal == 109
    assert usable == 27
    assert too_long == 10
    assert min(lens) == 175
    assert max(lens) == 16838
    assert statistics.median(lens) == 975
