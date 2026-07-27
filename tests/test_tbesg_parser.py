from __future__ import annotations

from pathlib import Path
import unicodedata

import pytest

from bible_engine.tagnt_parser import get_verse_tokens
from bible_engine.tbesg_parser import (
    GreekLexiconEntry,
    normalize_greek_strong_id,
    parse_tbesg_line,
)


ROOT = Path(__file__).parents[1]
TBESG_FIXTURE = ROOT / "tests" / "fixtures" / "tbesg_sample.tsv"
JHN_FIXTURE = ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"
EXPECTED_HEADER = (
    "eStrong",
    "dStrong",
    "uStrong",
    "Greek",
    "Transliteration",
    "Morph",
    "Gloss",
    "Abbott-Smith lexicon (AS), with gaps occationally filled from edited versions of  Middle LSJ ",
)


def test_fixture_preserves_actual_tbesg_header() -> None:
    header = TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()[0].split("\t")

    assert tuple(header) == EXPECTED_HEADER


def test_parse_g0025_agapao_entry() -> None:
    entry = _entries_by_strong()["G0025"]

    assert entry == GreekLexiconEntry(
        strong_id="G0025",
        dstrong_id="G0025 =",
        ustrong_id="G0025",
        greek=unicodedata.normalize("NFC", "ἀγαπάω"),
        transliteration="agapaō",
        morph="G:V",
        gloss="to love",
        meaning_raw=entry.meaning_raw,
    )
    assert entry.meaning_raw
    assert "<b>to love</b>" in entry.meaning_raw
    assert "<BR />" in entry.meaning_raw


def test_parse_g2889_kosmos_entry() -> None:
    entry = _entries_by_strong()["G2889"]

    assert entry.strong_id == "G2889"
    assert entry.greek == unicodedata.normalize("NFC", "κόσμος")
    assert entry.transliteration == "kosmos"
    assert entry.morph == "G:N-M"
    assert entry.gloss == "world"
    assert entry.meaning_raw
    assert "ornament, adornment" in entry.meaning_raw
    assert "human inhabitants of the world" in entry.meaning_raw


def test_parse_g3779_houtos_entry() -> None:
    entry = _entries_by_strong()["G3779"]

    assert entry.strong_id == "G3779"
    assert entry.greek == "οὕτως"
    assert entry.transliteration == "ohutō, ohutōs"
    assert entry.morph == "G:ADV"
    assert entry.gloss == "thus(-ly)"
    assert entry.meaning_raw
    assert "in this way, so, thus" in entry.meaning_raw


def test_greek_field_is_normalized_to_unicode_nfc() -> None:
    entry = parse_tbesg_line("G25\t\t\tἀγαπάω\t\t\t\t")

    assert entry.strong_id == "G0025"
    assert entry.greek == unicodedata.normalize("NFC", "ἀγαπάω")
    assert unicodedata.is_normalized("NFC", entry.greek)


def test_empty_optional_fields_are_none() -> None:
    entry = parse_tbesg_line("G25\t\t\tἀγαπάω\t\t\t\t")

    assert entry.dstrong_id is None
    assert entry.ustrong_id is None
    assert entry.transliteration is None
    assert entry.morph is None
    assert entry.gloss is None
    assert entry.meaning_raw is None


def test_meaning_raw_is_preserved_without_html_cleanup() -> None:
    entry = _entries_by_strong()["G0025"]

    assert entry.meaning_raw is not None
    assert "<ref='Jhn.3.35'>Jhn.3:35;</ref>" in entry.meaning_raw
    assert entry.meaning_raw.startswith(" <b>ἀγαπ")
    assert entry.meaning_raw.endswith("(AS)")


def test_normalize_greek_strong_id_pads_and_preserves_suffixes() -> None:
    assert normalize_greek_strong_id("G25") == "G0025"
    assert normalize_greek_strong_id("G0025") == "G0025"
    assert normalize_greek_strong_id("G2264G") == "G2264G"
    assert normalize_greek_strong_id("G10005") == "G10005"
    assert normalize_greek_strong_id("G20200") == "G20200"


def test_normalize_greek_strong_id_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Invalid Greek Strong identifier"):
        normalize_greek_strong_id("not-a-strong-id")

    with pytest.raises(ValueError, match="range"):
        normalize_greek_strong_id("G0000")


def test_normalize_greek_strong_id_rejects_hebrew_ids() -> None:
    with pytest.raises(ValueError, match="Hebrew id is not supported"):
        normalize_greek_strong_id("H0157")


def test_parse_tbesg_line_rejects_bad_or_incomplete_records() -> None:
    with pytest.raises(ValueError, match="expected 8 tab-separated fields"):
        parse_tbesg_line("G0025\tG0025")

    with pytest.raises(ValueError, match="missing eStrong"):
        parse_tbesg_line("\tG0025 =\tG0025\tἀγαπάω\tagapaō\tG:V\tto love\tmeaning")


def test_parse_tbesg_line_preserves_record_with_missing_greek_lemma() -> None:
    entry = parse_tbesg_line(
        "G2199\tG2199H =\tG2199H\t\tZebedaios\tN:N-M-P\t[wife of Zebedee]\tmeaning"
    )

    assert entry.strong_id == "G2199"
    assert entry.greek == ""
    assert entry.transliteration == "Zebedaios"


def test_john_3_16_tagnt_strong_ids_match_sample_lexicon_entries() -> None:
    token_strong_ids = {
        normalize_greek_strong_id(token.strong_id)
        for token in get_verse_tokens(JHN_FIXTURE, book="Jhn", chapter=3, verse=16)
    }
    lexicon_strong_ids = set(_entries_by_strong())

    assert {"G0025", "G2889", "G3779"} <= token_strong_ids
    assert {"G0025", "G2889", "G3779"} == lexicon_strong_ids
    assert {"G0025", "G2889", "G3779"} <= token_strong_ids & lexicon_strong_ids


def _fixture_records() -> list[str]:
    return TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()[1:]


def _entries_by_strong() -> dict[str, GreekLexiconEntry]:
    entries = [parse_tbesg_line(line) for line in _fixture_records() if line.strip()]
    return {entry.strong_id: entry for entry in entries}
