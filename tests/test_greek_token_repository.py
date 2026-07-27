from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from bible_engine.greek_token_repository import (
    DEFAULT_TAGNT_DATABASE_PATH,
    GreekVerseTokens,
    TAGNT_DATABASE_ENV_VAR,
    load_greek_passage_tokens,
    load_greek_verse_tokens,
    resolve_tagnt_database_path,
)
from bible_engine.tagnt_parser import GreekToken, render_greek_text
from bible_engine.tagnt_sqlite import create_schema, import_tagnt_book


FIXTURE_DIR = Path(__file__).parent / "fixtures"
JHN_3_16_FIXTURE = FIXTURE_DIR / "tagnt_jhn_3_16_sample.tsv"
ROOT = Path(__file__).parents[1]


def test_resolve_database_path_from_environment(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "john.sqlite3"

    monkeypatch.setenv(TAGNT_DATABASE_ENV_VAR, str(database))

    assert resolve_tagnt_database_path() == database


def test_resolve_database_path_uses_project_default(monkeypatch) -> None:
    monkeypatch.delenv(TAGNT_DATABASE_ENV_VAR, raising=False)
    monkeypatch.setattr(
        "bible_engine.greek_token_repository._tagnt_database_path_from_streamlit_secrets",
        lambda: None,
    )

    assert resolve_tagnt_database_path() == DEFAULT_TAGNT_DATABASE_PATH


def test_default_database_path_is_project_generated_sqlite() -> None:
    assert DEFAULT_TAGNT_DATABASE_PATH == ROOT / "data" / "generated" / "tagnt_nt.sqlite3"


def test_generated_database_and_raw_paths_are_gitignored() -> None:
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "data/generated/tagnt_nt.sqlite3",
            "data/generated/tagnt_john.sqlite3",
            "data/raw/TAGNT_Act-Rev_raw.txt",
            "_qa_shell/TAGNT_Mat-Jhn_raw.txt",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "data/generated/tagnt_nt.sqlite3" in result.stdout
    assert "data/generated/tagnt_john.sqlite3" in result.stdout
    assert "data/raw/TAGNT_Act-Rev_raw.txt" in result.stdout
    assert "_qa_shell/TAGNT_Mat-Jhn_raw.txt" in result.stdout


def test_missing_database_has_clear_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"

    with pytest.raises(FileNotFoundError, match="TAGNT SQLite database not found"):
        load_greek_verse_tokens("Jn 3,16", database_path=missing)


@pytest.mark.parametrize(
    ("reference", "expected_count", "first_form"),
    [
        ("Jn 1,1", 3, "Ἐν"),
        ("Jn 3,16", 26, "οὕτως"),
        ("Jn 10,10", 3, "ὁ"),
        ("Jn 14,6", 3, "λέγει"),
        ("Jn 21,17", 3, "λέγει"),
    ],
)
def test_load_john_verse_tokens_from_sqlite(
    tmp_path: Path,
    reference: str,
    expected_count: int,
    first_form: str,
) -> None:
    database = build_sample_database(tmp_path)

    tokens = load_greek_verse_tokens(reference, database_path=database)

    assert len(tokens) == expected_count
    assert tokens[0].greek_form == first_form
    assert [token.word_index for token in tokens] == sorted(
        token.word_index for token in tokens
    )
    assert render_greek_text(tokens)


def test_john_3_16_sqlite_tokens_match_existing_fixture(tmp_path: Path) -> None:
    database = build_sample_database(tmp_path)

    tokens = load_greek_verse_tokens("Jn 3,16", database_path=database)

    assert len(tokens) == 26
    assert tokens[0].strong_id == "G3779"
    assert tokens[2].strong_id == "G0025"
    assert tokens[6].strong_id == "G2889"


def test_load_john_3_16_21_passage_returns_six_ordered_verses(tmp_path: Path) -> None:
    database = build_sample_database(tmp_path)

    verses = load_greek_passage_tokens("Jn 3,16-21", database_path=database)

    assert [verse.verse for verse in verses] == [16, 17, 18, 19, 20, 21]
    assert len(verses[0].tokens) == 26
    assert all(isinstance(verse, GreekVerseTokens) for verse in verses)
    assert all(
        [token.word_index for token in verse.tokens]
        == sorted(token.word_index for token in verse.tokens)
        for verse in verses
    )


def test_load_john_10_7_10_and_14_1_6_passages(tmp_path: Path) -> None:
    database = build_sample_database(tmp_path)

    john_10 = load_greek_passage_tokens("Jn 10,7-10", database_path=database)
    john_14 = load_greek_passage_tokens("Jn 14,1-6", database_path=database)

    assert [verse.verse for verse in john_10] == [7, 8, 9, 10]
    assert [verse.verse for verse in john_14] == [1, 2, 3, 4, 5, 6]


def test_single_verse_api_rejects_multi_verse_and_chapter_references(tmp_path: Path) -> None:
    database = build_sample_database(tmp_path)

    assert load_greek_verse_tokens("Róm 8,1", database_path=database)[0].book == "Rom"
    with pytest.raises(ValueError, match="Only single verse references"):
        load_greek_verse_tokens("Jn 3,16-18", database_path=database)
    with pytest.raises(ValueError, match="Only verse references"):
        load_greek_verse_tokens("Jn 3", database_path=database)


@pytest.mark.parametrize(
    ("reference", "expected_book", "expected_verses"),
    [
        ("Mt 5,1-3", "Mat", [1, 2, 3]),
        ("Mk 1,1", "Mrk", [1]),
        ("Lk 15,11-13", "Luk", [11, 12, 13]),
        ("Jn 3,16-18", "Jhn", [16, 17, 18]),
        ("ApCsel 2,1-4", "Act", [1, 2, 3, 4]),
        ("Róm 8,1-4", "Rom", [1, 2, 3, 4]),
        ("1Kor 13,1-3", "1Co", [1, 2, 3]),
        ("Gal 5,22-23", "Gal", [22, 23]),
        ("Ef 2,8-10", "Eph", [8, 9, 10]),
        ("Fil 2,5-7", "Php", [5, 6, 7]),
        ("Zsid 11,1-3", "Heb", [1, 2, 3]),
        ("Jak 1,2-4", "Jas", [2, 3, 4]),
        ("1Pt 1,3-5", "1Pe", [3, 4, 5]),
        ("1Jn 4,7-10", "1Jn", [7, 8, 9, 10]),
        ("Júd 20-21", "Jud", [20, 21]),
        ("Júd 1,20-21", "Jud", [20, 21]),
        ("Jel 22,20-21", "Rev", [20, 21]),
    ],
)
def test_load_new_testament_passages_from_sqlite(
    tmp_path: Path,
    reference: str,
    expected_book: str,
    expected_verses: list[int],
) -> None:
    database = build_sample_database(tmp_path)

    verses = load_greek_passage_tokens(reference, database_path=database)

    assert [verse.book for verse in verses] == [expected_book] * len(expected_verses)
    assert [verse.verse for verse in verses] == expected_verses
    assert all(
        [token.word_index for token in verse.tokens]
        == sorted(token.word_index for token in verse.tokens)
        for verse in verses
    )
    assert all(verse.tokens[0].greek_form for verse in verses)


def build_sample_database(tmp_path: Path) -> Path:
    database = tmp_path / "tagnt_john_sample.sqlite3"
    import_tagnt_book(JHN_3_16_FIXTURE, database, "Jhn", "fixture", "test")
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        for token in [
            token_for("Jhn", 1, 1, 1, "Ἐν", "ἐν", "PREP", "G1722"),
            token_for("Jhn", 1, 1, 2, "ἀρχῇ", "ἀρχή", "N-DSF", "G0746"),
            token_for("Jhn", 1, 1, 3, "ἦν", "εἰμί", "V-IAI-3S", "G1510"),
            token_for("Jhn", 10, 10, 1, "ὁ", "ὁ", "T-NSM", "G3588"),
            token_for("Jhn", 10, 10, 2, "κλέπτης", "κλέπτης", "N-NSM", "G2812"),
            token_for("Jhn", 10, 10, 3, "ἔρχεται", "ἔρχομαι", "V-PNI-3S", "G2064"),
            token_for("Jhn", 3, 17, 1, "οὐ", "οὐ", "PRT-N", "G3756"),
            token_for("Jhn", 3, 18, 1, "ὁ", "ὁ", "T-NSM", "G3588"),
            token_for("Jhn", 3, 19, 1, "αὕτη", "οὗτος", "D-NSF", "G3778"),
            token_for("Jhn", 3, 20, 1, "πᾶς", "πᾶς", "A-NSM", "G3956"),
            token_for("Jhn", 3, 21, 1, "ὁ", "ὁ", "T-NSM", "G3588"),
            token_for("Jhn", 10, 7, 1, "εἶπεν", "λέγω", "V-2AAI-3S", "G3004G"),
            token_for("Jhn", 10, 8, 1, "πάντες", "πᾶς", "A-NPM", "G3956"),
            token_for("Jhn", 10, 9, 1, "ἐγώ", "ἐγώ", "P-1NS", "G1473"),
            token_for("Jhn", 14, 1, 1, "μὴ", "μή", "PRT-N", "G3361"),
            token_for("Jhn", 14, 2, 1, "ἐν", "ἐν", "PREP", "G1722"),
            token_for("Jhn", 14, 3, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Jhn", 14, 4, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Jhn", 14, 5, 1, "λέγει", "λέγω", "V-PAI-3S", "G3004G"),
            token_for("Jhn", 14, 6, 1, "λέγει", "λέγω", "V-PAI-3S", "G3004G"),
            token_for("Jhn", 14, 6, 2, "αὐτῷ", "αὐτός", "P-DSM", "G0846"),
            token_for("Jhn", 14, 6, 3, "Ἰησοῦς", "Ἰησοῦς", "N-NSM-P", "G2424G"),
            token_for("Jhn", 21, 17, 1, "λέγει", "λέγω", "V-PAI-3S", "G3004G"),
            token_for("Jhn", 21, 17, 2, "αὐτῷ", "αὐτός", "P-DSM", "G0846"),
            token_for("Jhn", 21, 17, 3, "τὸ", "ὁ", "T-ASN", "G3588"),
            token_for("Mat", 5, 1, 1, "Ἰδὼν", "ὁράω", "V-2AAP-NSM", "G3708"),
            token_for("Mat", 5, 2, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Mat", 5, 3, 1, "μακάριοι", "μακάριος", "A-NPM", "G3107"),
            token_for("Mrk", 1, 1, 1, "Ἀρχὴ", "ἀρχή", "N-NSF", "G0746"),
            token_for("Luk", 15, 11, 1, "Εἶπεν", "λέγω", "V-2AAI-3S", "G3004G"),
            token_for("Luk", 15, 12, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Luk", 15, 13, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Act", 2, 1, 1, "Καὶ", "καί", "CONJ", "G2532"),
            token_for("Act", 2, 2, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Act", 2, 3, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Act", 2, 4, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("Rom", 8, 1, 1, "Οὐδὲν", "οὐδείς", "A-NSN", "G3762"),
            token_for("Rom", 8, 2, 1, "ὁ", "ὁ", "T-NSM", "G3588"),
            token_for("Rom", 8, 3, 1, "τὸ", "ὁ", "T-NSN", "G3588"),
            token_for("Rom", 8, 4, 1, "ἵνα", "ἵνα", "CONJ", "G2443"),
            token_for("1Co", 13, 1, 1, "Ἐὰν", "ἐάν", "COND", "G1437"),
            token_for("1Co", 13, 2, 1, "καὶ", "καί", "CONJ", "G2532"),
            token_for("1Co", 13, 3, 1, "κἂν", "καί ἐάν", "COND", "G2579"),
            token_for("Gal", 5, 22, 1, "ὁ", "ὁ", "T-NSM", "G3588"),
            token_for("Gal", 5, 23, 1, "πραΰτης", "πραΰτης", "N-NSF", "G4236"),
            token_for("Eph", 2, 8, 1, "τῇ", "ὁ", "T-DSF", "G3588"),
            token_for("Eph", 2, 9, 1, "οὐκ", "οὐ", "PRT-N", "G3756"),
            token_for("Eph", 2, 10, 1, "αὐτοῦ", "αὐτός", "P-GSM", "G0846"),
            token_for("Php", 2, 5, 1, "τοῦτο", "οὗτος", "D-ASN", "G3778"),
            token_for("Php", 2, 6, 1, "ὃς", "ὅς", "R-NSM", "G3739"),
            token_for("Php", 2, 7, 1, "ἀλλὰ", "ἀλλά", "CONJ", "G0235"),
            token_for("Heb", 11, 1, 1, "Ἔστιν", "εἰμί", "V-PAI-3S", "G1510"),
            token_for("Heb", 11, 2, 1, "ἐν", "ἐν", "PREP", "G1722"),
            token_for("Heb", 11, 3, 1, "πίστει", "πίστις", "N-DSF", "G4102"),
            token_for("Jas", 1, 2, 1, "πᾶσαν", "πᾶς", "A-ASF", "G3956"),
            token_for("Jas", 1, 3, 1, "γινώσκοντες", "γινώσκω", "V-PAP-NPM", "G1097"),
            token_for("Jas", 1, 4, 1, "ἡ", "ὁ", "T-NSF", "G3588"),
            token_for("1Pe", 1, 3, 1, "Εὐλογητὸς", "εὐλογητός", "A-NSM", "G2128"),
            token_for("1Pe", 1, 4, 1, "εἰς", "εἰς", "PREP", "G1519"),
            token_for("1Pe", 1, 5, 1, "τοὺς", "ὁ", "T-APM", "G3588"),
            token_for("1Jn", 4, 7, 1, "Ἀγαπητοί", "ἀγαπητός", "A-VPM", "G0027"),
            token_for("1Jn", 4, 8, 1, "ὁ", "ὁ", "T-NSM", "G3588"),
            token_for("1Jn", 4, 9, 1, "ἐν", "ἐν", "PREP", "G1722"),
            token_for("1Jn", 4, 10, 1, "ἐν", "ἐν", "PREP", "G1722"),
            token_for("Jud", 1, 20, 1, "ὑμεῖς", "σύ", "P-2NP", "G4771"),
            token_for("Jud", 1, 21, 1, "ἑαυτοὺς", "ἑαυτοῦ", "F-2APM", "G1438"),
            token_for("Rev", 22, 20, 1, "Λέγει", "λέγω", "V-PAI-3S", "G3004G"),
            token_for("Rev", 22, 21, 1, "Ἡ", "ὁ", "T-NSF", "G3588"),
        ]:
            connection.execute(
                """
                INSERT OR IGNORE INTO greek_tokens (
                    book, chapter, verse, word_index, greek_form, lemma,
                    morph_code, strong_id, edition_flags, source_name,
                    source_version, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token.book,
                    token.chapter,
                    token.verse,
                    token.word_index,
                    token.greek_form,
                    token.lemma,
                    token.morph_code,
                    token.strong_id,
                    token.edition_flags,
                    "test",
                    "test",
                    "2026-07-27T00:00:00+00:00",
                ),
            )
    return database


def token_for(
    book: str,
    chapter: int,
    verse: int,
    word_index: int,
    greek_form: str,
    lemma: str,
    morph_code: str,
    strong_id: str,
) -> GreekToken:
    return GreekToken(
        book=book,
        chapter=chapter,
        verse=verse,
        word_index=word_index,
        greek_form=greek_form,
        lemma=lemma,
        morph_code=morph_code,
        strong_id=strong_id,
        edition_flags="NKO",
    )
