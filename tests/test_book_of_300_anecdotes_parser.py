from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from illustration_engine.book_of_300_anecdotes_parser import (
    BookOf300AnecdotesParseError,
    parse_book_of_300_anecdotes_file,
    parse_book_of_300_anecdotes_text,
)
from illustration_engine.paths import RAW_DATA_DIR


ANECDOTES_SOURCE = RAW_DATA_DIR / "pg15413_book_of_300_anecdotes.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Book of 300 Anecdotes source not present locally: {path}")
    return path


def test_anecdote_count() -> None:
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    assert len(anecdotes) == 345


def test_first_and_last_anecdote() -> None:
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    assert anecdotes[0].external_ref == "AFFECTION/1"
    assert anecdotes[0].title_original == "General St. Amour"
    assert anecdotes[0].title_is_derived is False
    assert anecdotes[-1].external_ref == "MISCELLANEOUS/37"
    assert anecdotes[-1].title_original == "Tyrolese peasant"


def test_anecdote_text_segmentation_does_not_bleed_across_boundary() -> None:
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    first_text = anecdotes[0].original_text
    assert "distinguished himself in the Imperial" in first_text
    assert "Deaf and Dumb Mother" not in first_text


def test_untitled_paragraphs_get_a_deterministic_derived_title() -> None:
    """~42% of anecdotes have no 'Name.--' label in the source — their
    title_original must still be non-empty and derived from the
    paragraph's own opening words (never invented / never AI text)."""
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    derived = [a for a in anecdotes if a.title_is_derived]
    assert len(derived) > 100
    for anecdote in derived[:5]:
        assert anecdote.title_original
        assert anecdote.original_text.startswith(anecdote.title_original.split()[0])


def test_indented_verse_fragment_merged_into_preceding_anecdote() -> None:
    """A quoted, indented couplet inside the Walter-Scott-innkeeper story
    must stay part of THAT anecdote's text, not become its own
    fragment — this was an actual bug found and fixed during
    implementation."""
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    scott_story = next(a for a in anecdotes if "Scotch Innkeeper" in a.original_text)
    assert "Drink, weary traveller--drink and pray" in scott_story.original_text
    assert "Drink, weary traveller--drink and pay" in scott_story.original_text
    # and it must NOT have become a separate, tiny standalone record
    fragment_titles = [a.title_original for a in anecdotes if "Drink, weary" in a.original_text]
    assert len(fragment_titles) == 1


def test_demonstrative_continuation_merged_into_preceding_anecdote() -> None:
    """A trailing editorial remark ('This incident has been admirably
    worked up in a German ballad...') opens with a bare demonstrative
    that requires an antecedent — it must be merged into the preceding
    'Italian Peasant' anecdote, not become its own record. This was a
    real bug found in the Phase 2J audit and fixed via a general,
    corpus-verified rule (exactly one such paragraph exists in the
    whole 345-anecdote book)."""
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    italian_peasant = next(a for a in anecdotes if a.title_original == "Italian Peasant")
    assert "admirably worked up in a German ballad" in italian_peasant.original_text
    standalone_remarks = [
        a for a in anecdotes if a.original_text.startswith("This incident has been")
    ]
    assert standalone_remarks == []


def test_manual_override_merges_sheridan_punchline_into_preceding_anecdote() -> None:
    """SCHOOLS: 'Sheridan instantly dropped the rod...' is the punchline
    of the immediately preceding Dr. Sheridan schoolroom anecdote, not
    an independent story — no general rule could safely catch this (see
    module docstring), so it is handled by the explicit, source-specific
    `_MANUAL_CONTINUATION_PREFIXES` override. It must NOT appear as its
    own record, and its text must be part of the Sheridan anecdote."""
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))

    standalone = [a for a in anecdotes if a.original_text.startswith("Sheridan instantly dropped")]
    assert standalone == []

    sheridan_anecdote = next(
        a for a in anecdotes if "Dr. Sheridan had a custom of ringing" in a.original_text
    )
    assert sheridan_anecdote.external_ref == "SCHOOLS/1"
    assert "gave\nhim half-a-crown." in sheridan_anecdote.original_text or (
        "half-a-crown" in sheridan_anecdote.original_text
    )


def test_manual_override_merges_dieppe_pilot_reward_letter() -> None:
    """HEROISM: 'Mons. de Crosne, the Intendant of Rouen...' is the
    reward-letter epilogue of the immediately preceding 'A Dieppe Pilot'
    rescue anecdote, not an independent story — handled by the same
    explicit override mechanism as the Sheridan case. It must NOT appear
    as its own record, and its text must be part of 'A Dieppe Pilot'."""
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))

    standalone = [a for a in anecdotes if a.original_text.startswith("Mons. de Crosne")]
    assert standalone == []

    dieppe_pilot = next(a for a in anecdotes if a.title_original == "A Dieppe Pilot")
    assert dieppe_pilot.external_ref == "HEROISM/1"
    assert "Mons. de Crosne, the Intendant of Rouen" in dieppe_pilot.original_text
    assert "Boussard" in dieppe_pilot.original_text


def test_manual_override_still_leaves_genuinely_separate_same_person_anecdotes_intact() -> None:
    """The reason a general name-repetition merge rule was rejected in
    favour of the explicit override list: this book has categories built
    around one recurring person (e.g. FONTENELLE), where multiple
    genuinely SEPARATE anecdotes legitimately open with the same name.
    The manual override must not have collapsed any of these."""
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    fontenelle_anecdotes = [a for a in anecdotes if a.category == "FONTENELLE"]
    assert len(fontenelle_anecdotes) >= 3


def test_parse_raises_if_a_manual_override_prefix_stops_matching() -> None:
    """If the source text underlying a `_MANUAL_CONTINUATION_PREFIXES`
    entry ever changes (e.g. a different PG re-transcription), the
    override must fail loudly rather than silently stop firing."""
    raw_text = _require(ANECDOTES_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace(
        "Sheridan instantly dropped the rod,",
        "Sheridan promptly dropped the rod,",
        1,
    )
    with pytest.raises(BookOf300AnecdotesParseError, match="never matched"):
        parse_book_of_300_anecdotes_text(mutilated)


def test_category_index_front_matter_excluded() -> None:
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    joined = "\n".join(a.original_text for a in anecdotes)
    assert "Abernethy, 26" not in joined
    assert "ACTORS, 27-33" not in joined


def test_gutenberg_boilerplate_and_the_end_excluded() -> None:
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    joined = "\n".join(a.original_text for a in anecdotes)
    assert "PROJECT GUTENBERG" not in joined.upper()
    assert "THE END." not in joined


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    keys = [a.canonical_key for a in anecdotes]
    assert keys == [f"{i:03d}" for i in range(1, len(anecdotes) + 1)]
    assert len(set(a.external_ref for a in anecdotes)) == len(anecdotes)


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(ANECDOTES_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_book_of_300_anecdotes_text(raw_text)
    second_pass = parse_book_of_300_anecdotes_text(raw_text)
    assert first_pass == second_pass


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(BookOf300AnecdotesParseError):
        parse_book_of_300_anecdotes_text("no PG markers in this text at all")


def test_parse_raises_on_missing_content_start_marker() -> None:
    raw_text = _require(ANECDOTES_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("\nANECDOTES.\n", "\nSTORIES.\n", 1)
    with pytest.raises(BookOf300AnecdotesParseError):
        parse_book_of_300_anecdotes_text(mutilated)


def test_length_statistics_consistency() -> None:
    """Corpus-quality metric required by Phase 2J: report the length
    distribution against the project's stated ideal band and assert it
    stays internally consistent (bucket counts sum to the total)."""
    anecdotes = parse_book_of_300_anecdotes_file(_require(ANECDOTES_SOURCE))
    lens = [len(a.original_text) for a in anecdotes]

    ideal = sum(1 for l in lens if 200 <= l <= 1500)
    usable = sum(1 for l in lens if 1501 <= l <= 3000)
    too_short = sum(1 for l in lens if l < 200)
    too_long = sum(1 for l in lens if l > 3000)
    assert ideal + usable + too_short + too_long == len(anecdotes)

    # This corpus was specifically chosen to skew toward the ideal band —
    # assert that it actually does, so a future re-parse regresses loudly.
    assert ideal / len(anecdotes) > 0.85
    # Exactly one record (the merged "A Dieppe Pilot" + reward-letter
    # epilogue, via the manual override) legitimately crosses 3000 chars
    # once correctly segmented — a correct merge outgrowing the ideal
    # band is expected and fine; a second one would signal a regression.
    assert too_long == 1
    assert min(lens) >= 150
    assert statistics.median(lens) < 1500
