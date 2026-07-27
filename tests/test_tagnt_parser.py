from pathlib import Path

import pytest

from bible_engine.tagnt_parser import GreekToken, get_verse_tokens, parse_tagnt_row


FIXTURE_DIR = Path(__file__).parent / "fixtures"
JHN_FIXTURE = FIXTURE_DIR / "tagnt_jhn_3_16_sample.tsv"
JUD_FIXTURE = FIXTURE_DIR / "tagnt_jud_1_20_sample.tsv"


def fixture_rows(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_john_3_16_fixture_parses_core_fields_and_order() -> None:
    rows = fixture_rows(JHN_FIXTURE)
    tokens = [parse_tagnt_row(row) for row in rows]
    token = tokens[0]

    assert token == GreekToken(
        book="Jhn",
        chapter=3,
        verse=16,
        word_index=1,
        greek_form="οὕτως",
        lemma="οὕτω, οὕτως",
        morph_code="ADV",
        strong_id="G3779",
        edition_flags="NKO",
    )
    assert [token.word_index for token in tokens] == list(range(1, 27))
    assert [token.greek_form for token in tokens[:3]] == [
        "οὕτως",
        "γὰρ",
        "ἠγάπησεν",
    ]
    assert all(token.book == "Jhn" for token in tokens)
    assert all(token.chapter == 3 for token in tokens)
    assert all(token.verse == 16 for token in tokens)


def test_get_verse_tokens_returns_john_3_16_in_order_from_path() -> None:
    tokens = get_verse_tokens(JHN_FIXTURE, book="Jhn", chapter=3, verse=16)

    assert len(tokens) == 26
    assert all(token.book == "Jhn" for token in tokens)
    assert all(token.chapter == 3 for token in tokens)
    assert all(token.verse == 16 for token in tokens)
    assert [token.word_index for token in tokens] == list(range(1, 27))
    assert [token.greek_form for token in tokens[:3]] == [
        "οὕτως",
        "γὰρ",
        "ἠγάπησεν",
    ]
    assert tokens[0].lemma == "οὕτω, οὕτως"
    assert tokens[0].morph_code == "ADV"
    assert tokens[0].strong_id == "G3779"
    assert tokens[10].edition_flags == "ko"


def test_get_verse_tokens_accepts_string_path_and_returns_empty_for_missing_verse() -> None:
    tokens = get_verse_tokens(str(JHN_FIXTURE), book="Jhn", chapter=3, verse=16)
    missing = get_verse_tokens(str(JHN_FIXTURE), book="Jhn", chapter=3, verse=999)

    assert len(tokens) == 26
    assert missing == []


def test_john_3_16_preserves_variant_edition_flags() -> None:
    token = parse_tagnt_row(fixture_rows(JHN_FIXTURE)[10])

    assert token.book == "Jhn"
    assert token.chapter == 3
    assert token.verse == 16
    assert token.word_index == 11
    assert token.greek_form == "αὐτοῦ"
    assert token.lemma == "αὐτός"
    assert token.morph_code == "P-GSM"
    assert token.strong_id == "G0846"
    assert token.edition_flags == "ko"


def test_jude_1_20_fixture_parses_core_fields_and_order() -> None:
    rows = fixture_rows(JUD_FIXTURE)
    tokens = [parse_tagnt_row(row) for row in rows]
    token = tokens[2]

    assert token.book == "Jud"
    assert token.chapter == 1
    assert token.verse == 20
    assert token.word_index == 3
    assert token.greek_form == "ἀγαπητοί,"
    assert token.lemma == "ἀγαπητός"
    assert token.morph_code == "A-VPM"
    assert token.strong_id == "G0027"
    assert token.edition_flags == "NKO"
    assert [token.word_index for token in tokens] == list(range(1, 14))
    assert [token.greek_form for token in tokens[:3]] == [
        "ὑμεῖς",
        "δέ,",
        "ἀγαπητοί,",
    ]
    assert all(token.book == "Jud" for token in tokens)
    assert all(token.chapter == 1 for token in tokens)
    assert all(token.verse == 20 for token in tokens)


def test_get_verse_tokens_returns_jude_1_20_regression_fixture() -> None:
    tokens = get_verse_tokens(JUD_FIXTURE, book="Jud", chapter=1, verse=20)

    assert len(tokens) == 13
    assert all(token.book == "Jud" for token in tokens)
    assert all(token.chapter == 1 for token in tokens)
    assert all(token.verse == 20 for token in tokens)
    assert [token.word_index for token in tokens] == list(range(1, 14))
    assert tokens[2].greek_form == "ἀγαπητοί,"
    assert tokens[2].lemma == "ἀγαπητός"
    assert tokens[2].morph_code == "A-VPM"
    assert tokens[2].strong_id == "G0027"
    assert tokens[2].edition_flags == "NKO"


def test_splits_lemma_and_gloss_only_at_first_separator() -> None:
    token = parse_tagnt_row(fixture_rows(JHN_FIXTURE)[0])

    assert token.lemma == "οὕτω, οὕτως"
    assert token.morph_code == "ADV"
    assert token.strong_id == "G3779"


def test_invalid_or_incomplete_row_has_clear_error() -> None:
    with pytest.raises(ValueError, match="Invalid TAGNT Word & Type field"):
        parse_tagnt_row("Jhn.3.16\tοὕτως (houtōs)\tThus\tG3779=ADV\tοὕτω, οὕτως=thus")

    with pytest.raises(ValueError, match="Missing TAGNT field: dStrongs = Grammar"):
        parse_tagnt_row("Jud.1.20#01=NKO\tὑμεῖς (humeis)")


def test_get_verse_tokens_missing_file_has_clear_error() -> None:
    missing_file = FIXTURE_DIR / "missing_tagnt.tsv"

    with pytest.raises(FileNotFoundError, match="TAGNT source file not found"):
        get_verse_tokens(missing_file, book="Jhn", chapter=3, verse=16)
