from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from illustration_engine.hebrew_tales_parser import (
    HebrewTalesParseError,
    parse_hebrew_tales_file,
    parse_hebrew_tales_text,
)
from illustration_engine.paths import RAW_DATA_DIR


HEBREW_TALES_SOURCE = RAW_DATA_DIR / "wikisource_hebrew_tales_hurwitz_kohut1917.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Hebrew Tales source not present locally: {path}")
    return path


def test_story_count() -> None:
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    assert len(stories) == 65


def test_tale_and_facetiae_split() -> None:
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    tales = [s for s in stories if s.external_ref.startswith("TALE/")]
    facetiae = [s for s in stories if s.external_ref.startswith("FACETIAE/")]
    assert len(tales) == 55
    assert len(facetiae) == 10
    # tales must all precede facetiae positionally
    assert [s.canonical_key for s in tales] == [f"{i:03d}" for i in range(1, 56)]
    assert [s.canonical_key for s in facetiae] == [f"{i:03d}" for i in range(56, 66)]


def test_first_and_last_story() -> None:
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    assert stories[0].canonical_key == "001"
    assert stories[0].external_ref == "TALE/01"
    assert stories[0].title_original == "Moses and the Lamb"
    assert stories[0].original_text.startswith("Moses and the Lamb")
    assert "Psalm cxlv. 9" in stories[0].original_text
    assert stories[0].original_text.rstrip().endswith("Exodus Rabba, § II.")

    assert stories[-1].canonical_key == "065"
    assert stories[-1].external_ref == "FACETIAE/10"
    assert stories[-1].title_original == "No Rule Without Exception"
    assert stories[-1].original_text.rstrip().endswith("Pesahim, 86b.")


def test_body_heading_used_not_shorter_toc_title() -> None:
    """Kohut's own preface discloses he abbreviated some chapter-
    headings for the reprint — `title_original` must come from the
    fuller, actual body heading, not the shorter TOC wording."""
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    ambition = next(s for s in stories if s.title_original.startswith("Ambition Humbled"))
    assert ambition.title_original == "Ambition Humbled and Reproved or Alexander and the Human Skull"

    wit_like_salt = next(s for s in stories if s.title_original.startswith("Wit Like Salt"))
    assert wit_like_salt.title_original == "Wit Like Salt: A Little Goes a Great Way"


def test_toc_duplicate_seed_resolves_to_distinct_body_titles() -> None:
    """The TOC's shortened form 'Scrupulous Honesty' names two
    different tales — since `title_original` is taken from the fuller
    body heading, both resolve to distinct, unique titles."""
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    honesty_titles = [s.title_original for s in stories if s.title_original.startswith("Scrupulous Honesty")]
    assert len(honesty_titles) == 2
    assert len(set(honesty_titles)) == 2
    assert all("Exemplified" in t for t in honesty_titles)


def test_hadrian_pair_distinct_despite_similar_toc_entries() -> None:
    """TOC entries 'The Sufferings of the Jews under Hadrian, I.' and
    'Sufferings of the Jews under Hadrian, II' inconsistently include a
    leading 'The' that the body heading may or may not have either way
    — the article-stripping fallback in `_locate_heading` must still
    resolve both to their own, non-overlapping segments."""
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    hadrian = [s for s in stories if "Sufferings of the Jews" in s.title_original]
    assert len(hadrian) == 2
    assert hadrian[0].original_text.rstrip().endswith("Ekah Rabbati, ch. I, to Lamentations I, 16.")
    assert hadrian[1].original_text.rstrip().endswith("Ekah Rabbati, ch. III, to Lamentations III, 59.")
    assert "As a further specimen" not in hadrian[0].original_text
    assert "of all the tyrants" not in hadrian[1].original_text


def test_all_title_originals_are_unique() -> None:
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    titles = [s.title_original for s in stories]
    assert len(set(titles)) == len(titles)


def test_talmudic_midrashic_citations_preserved() -> None:
    """Source citations are valuable provenance data (Phase 2N brief)
    and must be kept verbatim as the trailing content of
    `original_text`, not stripped as boilerplate."""
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    citation_samples = {
        "Moses and the Lamb": "Exodus Rabba, § II.",
        "The Seven Ages": "Ecclesiastes Rabba I, 2",
    }
    for title, expected_citation_fragment in citation_samples.items():
        story = next(s for s in stories if s.title_original == title)
        assert expected_citation_fragment in story.original_text


def test_footnotes_reattached_verbatim_with_marker_stripped() -> None:
    """Kohut's numbered footnotes are kept (not deleted) as a trailing,
    numbered paragraph on their owning story, but the inline `[N]`
    marker itself is removed from the narrative sentence."""
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    wit_like_salt = next(s for s in stories if s.title_original.startswith("Wit Like Salt"))
    assert "[14] A small coin, of less value than a farthing." in wit_like_salt.original_text
    assert "Pruta[14]" not in wit_like_salt.original_text
    assert "Pruta bring me something" in wit_like_salt.original_text

    seven_ages = next(s for s in stories if s.title_original == "The Seven Ages")
    assert "[4] Eccles. i. 2. The word occurs twice" in seven_ages.original_text


def test_section_header_footnote_not_attached_to_any_story() -> None:
    """Footnote 13 belongs to the 'FACETIÆ[13]' section-divider text,
    not to any individual tale — it must not leak into any story, and
    the divider text itself must not survive into any story's text."""
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "Athenians in Talmud and Midrash" not in joined
    assert "FACETI" not in joined


def test_front_and_editorial_matter_excluded() -> None:
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    joined = "\n".join(s.original_text for s in stories)
    assert "CONTENTS" not in joined
    assert "BLOCH" not in joined.upper()
    assert "GEORGE ALEXANDER KOHUT" not in joined.upper()
    assert "Nuggets" not in joined


def test_zero_width_space_transclusion_artifact_stripped() -> None:
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    assert all("​" not in s.original_text for s in stories)
    assert all("​" not in s.title_original for s in stories)


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    keys = [s.canonical_key for s in stories]
    assert keys == [f"{i:03d}" for i in range(1, len(stories) + 1)]
    assert len(set(s.external_ref for s in stories)) == len(stories)


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(HEBREW_TALES_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_hebrew_tales_text(raw_text)
    second_pass = parse_hebrew_tales_text(raw_text)
    assert first_pass == second_pass


def test_parse_raises_on_missing_body_start_anchor() -> None:
    with pytest.raises(HebrewTalesParseError):
        parse_hebrew_tales_text("no recognizable structure in this text at all")


def test_parse_raises_on_missing_footnote_section() -> None:
    raw_text = _require(HEBREW_TALES_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("↑", "^", 1000)
    with pytest.raises(HebrewTalesParseError):
        parse_hebrew_tales_text(mutilated)


def test_length_statistics_consistency() -> None:
    """Corpus-quality metric required by Phase 2N: this source skews
    notably longer than prior sources (per the Phase 2M audit) — the
    3000+ band is expected to be substantial and is deliberately NOT
    trimmed in this phase."""
    stories = parse_hebrew_tales_file(_require(HEBREW_TALES_SOURCE))
    lens = [len(s.original_text) for s in stories]

    too_short = sum(1 for l in lens if l < 200)
    ideal = sum(1 for l in lens if 200 <= l <= 1500)
    usable = sum(1 for l in lens if 1501 <= l <= 3000)
    too_long = sum(1 for l in lens if l > 3000)
    assert too_short + ideal + usable + too_long == len(stories)

    assert too_short == 0
    assert ideal == 21
    assert usable == 29
    assert too_long == 15
    assert statistics.median(lens) < 2500
