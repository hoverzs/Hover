from __future__ import annotations

from pathlib import Path

import pytest

from illustration_engine.baldwin_parser import (
    BaldwinParseError,
    parse_baldwin_file,
    parse_baldwin_text,
)
from illustration_engine.paths import RAW_DATA_DIR


BALDWIN_SOURCE = RAW_DATA_DIR / "pg18442_baldwin_fifty_famous_stories_retold.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Baldwin source not present locally: {path}")
    return path


def test_story_count_matches_contents_listing() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    assert len(stories) == 50


def test_first_and_last_story() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    assert stories[0].external_ref == "1"
    assert stories[0].title_original == "King Alfred and the Cakes"
    assert stories[-1].external_ref == "50"
    assert stories[-1].title_original == "Mignon"


def test_story_text_segmentation_does_not_bleed_across_boundary() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    first_text = stories[0].original_text
    assert "wise and good king whose name" in first_text
    assert "KING ALFRED AND THE BEGGAR" not in first_text.upper()

    second_text = stories[1].original_text
    assert "KING ALFRED AND THE CAKES" not in second_text.upper()


def test_multi_part_story_kept_as_one_record_with_internal_subheadings() -> None:
    """'King John and the Abbot' is told across two internal, non-CONTENTS
    sub-headings ('I. The Three Questions.' / 'II. The Three Answers.') —
    these must stay inside ONE story record, matching the book's own
    CONTENTS (which lists it as a single entry), not be split or lost."""
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    tale = next(s for s in stories if s.title_original == "King John and the Abbot")
    assert "THE THREE QUESTIONS" in tale.original_text.upper()
    assert "THE THREE ANSWERS" in tale.original_text.upper()


def test_unlisted_second_heading_stays_inside_its_parent_story() -> None:
    """'The White Ship' is followed by an unlisted heading ('He Never
    Smiled Again') that is really its second scene, not a separate
    CONTENTS entry — it must remain part of 'The White Ship'."""
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    tale = next(s for s in stories if s.title_original == "The White Ship")
    assert "HE NEVER SMILED AGAIN" in tale.original_text.upper()


def test_five_part_story_kept_intact() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    tale = next(s for s in stories if s.title_original == "Whittington and his Cat")
    for marker in ("THE CITY", "THE KITCHEN", "THE VENTURE", "THE CAT", "THE FORTUNE"):
        assert marker in tale.original_text.upper()


def test_story_text_excludes_gutenberg_boilerplate() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    joined = "\n".join(story.original_text for story in stories)
    forbidden = (
        "PROJECT GUTENBERG",
        "This eBook is for the use of anyone",
        "AMERICAN BOOK COMPANY",
    )
    for marker in forbidden:
        assert marker.upper() not in joined.upper(), f"leaked boilerplate marker: {marker!r}"


def test_story_text_excludes_contents_and_preface() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    joined = "\n".join(story.original_text for story in stories)
    assert "CONCERNING THESE STORIES" not in joined.upper()
    assert "half-legendary" not in joined.lower()


def test_story_text_excludes_illustration_captions() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    joined = "\n".join(story.original_text for story in stories)
    assert "[Illustration" not in joined


def test_last_story_excludes_trailing_scene_break_and_pg_colophon() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    last = stories[-1].original_text
    assert not last.rstrip().endswith("*")
    assert "end of project gutenberg" not in last.lower()


def test_internal_mid_story_scene_break_is_preserved() -> None:
    """A scene-break ornament ('*   *   *   *   *') appears in the MIDDLE
    of 'Casabianca' (separating the prose retelling from a poem
    quotation) — that is original 1896 typography, not a PG artifact,
    and must be preserved, unlike the trailing one at the very end of
    the book."""
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    tale = next(s for s in stories if s.title_original == "Casabianca")
    assert "*" in tale.original_text


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    stories = parse_baldwin_file(_require(BALDWIN_SOURCE))
    keys = [story.canonical_key for story in stories]
    assert keys == [f"{i:02d}" for i in range(1, 51)]
    assert [story.external_ref for story in stories] == [str(i) for i in range(1, 51)]


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(BALDWIN_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_baldwin_text(raw_text)
    second_pass = parse_baldwin_text(raw_text)
    assert first_pass == second_pass


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(BaldwinParseError):
        parse_baldwin_text("no PG markers in this text at all")


def test_parse_raises_on_missing_expected_story_title() -> None:
    raw_text = _require(BALDWIN_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace(
        "KING ALFRED AND THE CAKES.", "SOMETHING ELSE ENTIRELY.", 1
    )
    with pytest.raises(BaldwinParseError):
        parse_baldwin_text(mutilated)
