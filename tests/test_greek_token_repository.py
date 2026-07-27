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
    assert DEFAULT_TAGNT_DATABASE_PATH == ROOT / "data" / "generated" / "tagnt_john.sqlite3"


def test_generated_database_and_raw_paths_are_gitignored() -> None:
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "data/generated/tagnt_john.sqlite3",
            "_qa_shell/TAGNT_Mat-Jhn_raw.txt",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "data/generated/tagnt_john.sqlite3" in result.stdout
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


def test_non_john_or_multi_verse_references_are_rejected(tmp_path: Path) -> None:
    database = build_sample_database(tmp_path)

    with pytest.raises(ValueError, match="Only John"):
        load_greek_verse_tokens("Róm 8,1", database_path=database)
    with pytest.raises(ValueError, match="Only single John verses"):
        load_greek_verse_tokens("Jn 3,16-18", database_path=database)
    with pytest.raises(ValueError, match="Only single John verses"):
        load_greek_verse_tokens("Jn 3", database_path=database)


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
