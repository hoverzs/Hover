from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from illustration_engine.english_jests_and_anecdotes_parser import (
    EnglishJestsParseError,
    parse_english_jests_file,
    parse_english_jests_text,
)
from illustration_engine.paths import RAW_DATA_DIR


JESTS_SOURCE = RAW_DATA_DIR / "pg49370_english_jests_and_anecdotes.txt"

_MANUAL_NON_NARRATIVE_TITLES = (
    "EPITAPH ON PROFESSOR BARNES, A MAN OF WEAK JUDGMENT, BUT HAPPY MEMORY.",
    "EPIGRAM.",
    "KITES.",
    "NATIONAL PARADOXES.",
    "CUT DOWN AND CUT UP.",
    "TAXES.",
    "SIGNS AND TOKENS.",
)


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw English Jests and Anecdotes source not present locally: {path}")
    return path


def test_story_count() -> None:
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    assert len(stories) == 758


def test_first_and_last_story() -> None:
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    assert stories[0].canonical_key == "001"
    assert stories[0].external_ref == "1"
    assert stories[0].title_original == "LACHRYMAL CANALS."
    assert stories[0].original_text.startswith("A lady who kept a boarding-school")

    assert stories[-1].canonical_key == "758"
    assert stories[-1].external_ref == "758"
    assert stories[-1].title_original == "AN IMPOSTOR."


def test_story_boundaries_do_not_bleed() -> None:
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    first = next(s for s in stories if s.title_original == "LACHRYMAL CANALS.")
    second = next(s for s in stories if s.title_original == "THE DUCHESS OF NEWCASTLE.")
    assert "THE DUCHESS OF NEWCASTLE" not in first.original_text
    assert "This famous lady" not in first.original_text
    assert second.original_text.startswith("This famous lady")


def test_duplicate_headings_produce_distinct_stories() -> None:
    """13 titles (e.g. 'CHARLES II.') repeat across genuinely separate
    anecdotes about the same recurring person — canonical_key/
    external_ref must still keep each occurrence distinct."""
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    charles = [s for s in stories if s.title_original == "CHARLES II."]
    assert len(charles) == 3
    assert len({s.canonical_key for s in charles}) == 3
    assert len({s.external_ref for s in charles}) == 3


def test_manual_non_narrative_exclusions_are_absent() -> None:
    """The 7 confirmed non-narrative units (bare verse/epitaph, gnomic
    one-liners, argumentative essay passages with no narrated incident
    — see module docstring for the full audit) must not appear in the
    parsed corpus at all."""
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    present_titles = {s.title_original for s in stories}
    assert present_titles.isdisjoint(_MANUAL_NON_NARRATIVE_TITLES)


def test_parse_raises_if_a_manual_exclusion_title_stops_matching() -> None:
    raw_text = _require(JESTS_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("EPIGRAM.", "EPIGRAMS.", 1)
    with pytest.raises(EnglishJestsParseError, match="never matched"):
        parse_english_jests_text(mutilated)


def test_footnote_markers_stripped() -> None:
    """Single-letter bracketed footnote markers ([A]-[G]) point to
    bibliographic annotations in the deliberately-excluded back-matter
    'NOTES' section — they must not leak into any story's text."""
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    import re

    assert re.search(r"\[[A-Z]\]", joined) is None


def test_front_and_back_matter_excluded() -> None:
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "NUGGETS FOR TRAVELLERS" not in joined
    assert "WILLIAM PATERSON" not in joined.upper()
    assert "R. SYMON, PRINTER" not in joined.upper()
    assert "Burnett" not in joined  # a NOTES-section bibliographic footnote body


def test_gutenberg_boilerplate_excluded() -> None:
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "PROJECT GUTENBERG" not in joined.upper()


def test_multi_paragraph_dialogue_story_preserved_intact() -> None:
    """'SHERIDAN AND THE STRANGER.' is told across 16 blank-line
    separated dialogue turns in the source — they must all land in one
    record, not be split into fragments."""
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    story = next(s for s in stories if s.title_original == "SHERIDAN AND THE STRANGER.")
    assert "_Stranger._" in story.original_text
    assert "Piccadilly" in story.original_text
    assert "enjoying his joke." in story.original_text


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    keys = [s.canonical_key for s in stories]
    assert keys == [f"{i:03d}" for i in range(1, len(stories) + 1)]
    assert len(set(s.external_ref for s in stories)) == len(stories)


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(JESTS_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_english_jests_text(raw_text)
    second_pass = parse_english_jests_text(raw_text)
    assert first_pass == second_pass


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(EnglishJestsParseError):
        parse_english_jests_text("no PG markers in this text at all")


def test_parse_raises_on_missing_story_region_start() -> None:
    raw_text = _require(JESTS_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("ENGLISH ANECDOTES.", "ENGLISH ANECDOTES", 1)
    with pytest.raises(EnglishJestsParseError):
        parse_english_jests_text(mutilated)


def test_length_statistics_consistency() -> None:
    """Corpus-quality metric required by Phase 2L: report the length
    distribution against the project's stated ideal band and assert it
    stays internally consistent (bucket counts sum to the total)."""
    stories = parse_english_jests_file(_require(JESTS_SOURCE))
    lens = [len(s.original_text) for s in stories]

    too_short = sum(1 for l in lens if l < 200)
    ideal = sum(1 for l in lens if 200 <= l <= 1500)
    usable = sum(1 for l in lens if 1501 <= l <= 3000)
    too_long = sum(1 for l in lens if l > 3000)
    assert too_short + ideal + usable + too_long == len(stories)

    assert too_short == 66
    assert ideal == 681
    assert usable == 10
    assert too_long == 1
    assert min(lens) == 93
    assert max(lens) == 3363
    assert statistics.median(lens) == 377.5
