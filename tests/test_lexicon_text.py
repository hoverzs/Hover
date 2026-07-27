from __future__ import annotations

from pathlib import Path
import re

from bible_engine.lexicon_text import (
    LexiconMeaning,
    get_plain_lexicon_meaning,
    parse_lexicon_meaning,
)
from bible_engine.tbesg_parser import GreekLexiconEntry, parse_tbesg_line


ROOT = Path(__file__).parents[1]
TBESG_FIXTURE = ROOT / "tests" / "fixtures" / "tbesg_sample.tsv"
HTML_TAG_RE = re.compile(r"<[^>]+>")


def test_g0025_meaning_raw_is_cleaned_to_readable_text() -> None:
    entry = _entries_by_strong()["G0025"]
    meaning = parse_lexicon_meaning(entry.meaning_raw)

    assert meaning.raw == entry.meaning_raw
    assert "ἀγαπάω, -ῶ," in meaning.plain_text
    assert "to love, to feel and exhibit esteem" in meaning.plain_text
    assert "Of human affection, to men" in meaning.plain_text
    assert "God's love" in meaning.plain_text
    assert "φιλέω" in meaning.plain_text
    assert not HTML_TAG_RE.search(meaning.plain_text)


def test_g2889_meaning_raw_is_cleaned_to_readable_text() -> None:
    meaning = parse_lexicon_meaning(_entries_by_strong()["G2889"].meaning_raw)

    assert "κόσμος, -ου, ὁ" in meaning.plain_text
    assert "order (Hom., Plat., al.)." in meaning.plain_text
    assert "ornament, adornment" in meaning.plain_text
    assert "the human inhabitants of the world" in meaning.plain_text
    assert not HTML_TAG_RE.search(meaning.plain_text)


def test_g3779_meaning_raw_is_cleaned_to_readable_text() -> None:
    meaning = parse_lexicon_meaning(_entries_by_strong()["G3779"].meaning_raw)

    assert "οὕτως, rarely" in meaning.plain_text
    assert "in this way, so, thus" in meaning.plain_text
    assert "referring to what precedes" in meaning.plain_text
    assert "Referring to what follows" in meaning.plain_text
    assert not HTML_TAG_RE.search(meaning.plain_text)


def test_formatting_tags_are_removed_without_losing_content() -> None:
    meaning = parse_lexicon_meaning("<b>bold</b> and <i>italic</i> <re>synonym</re>")

    assert meaning.plain_text == "bold and italic synonym"
    assert "<b>" not in meaning.plain_text
    assert "<i>" not in meaning.plain_text
    assert "<re>" not in meaning.plain_text


def test_br_tags_create_separate_paragraphs() -> None:
    meaning = parse_lexicon_meaning("first<BR />second<br>third")

    assert meaning.paragraphs == ("first", "second", "third")
    assert meaning.plain_text == "first\nsecond\nthird"


def test_html_entities_are_decoded() -> None:
    meaning = parse_lexicon_meaning("love &amp; esteem &lt;not-a-tag&gt;")

    assert meaning.plain_text == "love & esteem <not-a-tag>"


def test_empty_and_none_inputs_are_safe_empty_objects() -> None:
    assert parse_lexicon_meaning("") == LexiconMeaning(
        raw="",
        plain_text="",
        paragraphs=(),
        references=(),
        warnings=(),
    )
    assert parse_lexicon_meaning(None) == LexiconMeaning(
        raw="",
        plain_text="",
        paragraphs=(),
        references=(),
        warnings=(),
    )


def test_unknown_tag_is_safe_and_reported() -> None:
    meaning = parse_lexicon_meaning("alpha <step-special code='x'>beta</step-special>")

    assert meaning.plain_text == "alpha beta"
    assert meaning.warnings == (
        "Unknown TBESG tag preserved as text content: step-special",
    )


def test_raw_value_is_preserved_exactly() -> None:
    raw = "  <b>alpha</b><BR /> beta  "
    meaning = parse_lexicon_meaning(raw)

    assert meaning.raw == raw
    assert meaning.plain_text == "alpha\nbeta"


def test_references_are_collected_from_tbesg_ref_attributes() -> None:
    meaning = parse_lexicon_meaning("see <ref='Jhn.3.16'>Jhn.3:16</ref>")

    assert meaning.references == ("Jhn.3.16",)
    assert meaning.plain_text == "see Jhn.3:16"


def test_get_plain_lexicon_meaning_returns_plain_text_for_entry() -> None:
    entry = _entries_by_strong()["G0025"]

    assert get_plain_lexicon_meaning(entry) == parse_lexicon_meaning(
        entry.meaning_raw
    ).plain_text


def test_all_fixture_meanings_can_be_cleaned() -> None:
    entries = _entries_by_strong()

    assert set(entries) == {"G0025", "G2889", "G3779"}
    for entry in entries.values():
        meaning = parse_lexicon_meaning(entry.meaning_raw)

        assert meaning.plain_text
        assert meaning.paragraphs
        assert not HTML_TAG_RE.search(meaning.plain_text)
        assert not meaning.warnings


def test_essential_words_are_not_lost_from_fixture_records() -> None:
    entries = _entries_by_strong()
    expected_words = {
        "G0025": ("love", "esteem", "goodwill"),
        "G2889": ("order", "ornament", "world"),
        "G3779": ("way", "so", "thus"),
    }

    for strong_id, words in expected_words.items():
        plain_text = parse_lexicon_meaning(entries[strong_id].meaning_raw).plain_text
        assert all(word in plain_text for word in words)


def _entries_by_strong() -> dict[str, GreekLexiconEntry]:
    lines = TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()[1:]
    entries = [parse_tbesg_line(line) for line in lines if line.strip()]
    return {entry.strong_id: entry for entry in entries}
