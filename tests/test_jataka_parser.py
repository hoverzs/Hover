from __future__ import annotations

from pathlib import Path

import pytest

from illustration_engine.jataka_parser import (
    JATAKA_TALES_1912,
    MORE_JATAKA_TALES_1922,
    JatakaParseError,
    parse_jataka_file,
    parse_jataka_text,
)
from illustration_engine.paths import RAW_DATA_DIR


JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg62514_jataka_tales.txt"
MORE_JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg7518_more_jataka_tales.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Jataka source not present locally: {path}")
    return path


def test_jataka_tales_story_count() -> None:
    stories = parse_jataka_file(_require(JATAKA_TALES_SOURCE), JATAKA_TALES_1912)
    assert len(stories) == 18


def test_more_jataka_tales_story_count() -> None:
    stories = parse_jataka_file(_require(MORE_JATAKA_TALES_SOURCE), MORE_JATAKA_TALES_1922)
    assert len(stories) == 21


def test_jataka_tales_first_and_last_story() -> None:
    stories = parse_jataka_file(_require(JATAKA_TALES_SOURCE), JATAKA_TALES_1912)
    assert stories[0].external_ref == "I"
    assert stories[0].title_original == "The Monkey And The Crocodile"
    assert stories[-1].external_ref == "XVIII"
    assert stories[-1].title_original == "Why The Owl Is Not King Of The Birds"


def test_more_jataka_tales_first_and_last_story() -> None:
    stories = parse_jataka_file(_require(MORE_JATAKA_TALES_SOURCE), MORE_JATAKA_TALES_1922)
    assert stories[0].external_ref == "I"
    assert stories[0].title_original == "The Girl Monkey And The String Of Pearls"
    assert stories[-1].external_ref == "XXI"
    assert stories[-1].title_original == "The Elephant And The Dog"


def test_story_text_segmentation_does_not_bleed_across_boundary() -> None:
    """The first story's text must contain its own content and must NOT
    contain any trace of the second story's title or opening line."""
    stories = parse_jataka_file(_require(JATAKA_TALES_SOURCE), JATAKA_TALES_1912)
    first_text = stories[0].original_text
    assert "A monkey lived in a great tree on a river bank." in first_text
    assert "HOW THE TURTLE SAVED HIS OWN LIFE" not in first_text
    assert "A king once had a lake made" not in first_text

    second_text = stories[1].original_text
    assert "A king once had a lake made" in second_text
    assert "THE MONKEY AND THE CROCODILE" not in second_text


def test_story_text_excludes_gutenberg_boilerplate() -> None:
    stories = parse_jataka_file(_require(JATAKA_TALES_SOURCE), JATAKA_TALES_1912)
    joined = "\n".join(story.original_text for story in stories)
    forbidden = (
        "PROJECT GUTENBERG",
        "Transcriber's Notes",
        "This eBook is for the use of anyone",
        "CONTENTS",
        "FOREWORD",
        "FELIX ADLER",
    )
    for marker in forbidden:
        assert marker.upper() not in joined.upper(), f"leaked boilerplate marker: {marker!r}"


def test_story_text_excludes_illustration_captions() -> None:
    stories = parse_jataka_file(_require(MORE_JATAKA_TALES_SOURCE), MORE_JATAKA_TALES_1922)
    joined = "\n".join(story.original_text for story in stories)
    assert "[Illustration" not in joined


def test_story_text_excludes_trailing_the_end_and_pg_colophon() -> None:
    jataka = parse_jataka_file(_require(JATAKA_TALES_SOURCE), JATAKA_TALES_1912)
    assert not jataka[-1].original_text.rstrip().endswith("THE END")

    more_jataka = parse_jataka_file(_require(MORE_JATAKA_TALES_SOURCE), MORE_JATAKA_TALES_1922)
    assert "End of Project Gutenberg" not in more_jataka[-1].original_text


def test_canonical_keys_are_stable_zero_padded_and_unique() -> None:
    stories = parse_jataka_file(_require(JATAKA_TALES_SOURCE), JATAKA_TALES_1912)
    keys = [story.canonical_key for story in stories]
    assert keys == [f"{i:02d}" for i in range(1, 19)]
    assert len(set(keys)) == len(keys)


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(JATAKA_TALES_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_jataka_text(raw_text, JATAKA_TALES_1912)
    second_pass = parse_jataka_text(raw_text, JATAKA_TALES_1912)
    assert first_pass == second_pass


def test_parse_raises_on_missing_expected_header() -> None:
    raw_text = _require(JATAKA_TALES_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("THE MONKEY AND THE CROCODILE", "SOMETHING ELSE ENTIRELY")
    with pytest.raises(JatakaParseError):
        parse_jataka_text(mutilated, JATAKA_TALES_1912)


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(JatakaParseError):
        parse_jataka_text("no PG markers in this text at all", JATAKA_TALES_1912)
