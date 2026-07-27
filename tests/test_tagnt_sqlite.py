from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bible_engine.tagnt_parser import get_verse_tokens
from bible_engine.tagnt_sqlite import (
    create_schema,
    get_sqlite_verse_tokens,
    import_tagnt_book,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"
JHN_FIXTURE = FIXTURE_DIR / "tagnt_jhn_3_16_sample.tsv"


def test_create_schema_creates_table_and_indexes(tmp_path: Path) -> None:
    database = tmp_path / "tagnt.sqlite"
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        table_names = _sqlite_names(connection, "table")
        index_names = _sqlite_names(connection, "index")

    assert "greek_tokens" in table_names
    assert "idx_greek_tokens_reference" in index_names
    assert "idx_greek_tokens_lemma" in index_names
    assert "idx_greek_tokens_strong_id" in index_names


def test_import_small_fixture_and_get_john_3_16(tmp_path: Path) -> None:
    database = tmp_path / "tagnt.sqlite"

    report = import_tagnt_book(
        JHN_FIXTURE,
        database,
        book="Jhn",
        source_name="fixture",
        source_version="test",
    )
    tokens = get_sqlite_verse_tokens(database, "Jhn", 3, 16)

    assert report.rows_read == 26
    assert report.rows_imported == 26
    assert report.rows_skipped == 0
    assert report.parse_errors == 0
    assert report.duplicate_rows == 0
    assert len(tokens) == 26
    assert [token.word_index for token in tokens] == list(range(1, 27))


def test_import_only_requested_book(tmp_path: Path) -> None:
    mixed_source = tmp_path / "mixed.tsv"
    mixed_source.write_text(
        JHN_FIXTURE.read_text(encoding="utf-8")
        + "\n"
        + JHN_FIXTURE.read_text(encoding="utf-8").replace("Jhn.", "Mat."),
        encoding="utf-8",
    )
    database = tmp_path / "tagnt.sqlite"

    report = import_tagnt_book(
        mixed_source,
        database,
        book="Jhn",
        source_name="fixture",
    )

    assert report.rows_read == 52
    assert report.rows_imported == 26
    assert report.rows_skipped == 26
    assert len(get_sqlite_verse_tokens(database, "Jhn", 3, 16)) == 26
    assert get_sqlite_verse_tokens(database, "Mat", 3, 16) == []


def test_sqlite_tokens_match_fixture_order_and_core_fields(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)
    sqlite_tokens = get_sqlite_verse_tokens(database, "Jhn", 3, 16)
    fixture_tokens = get_verse_tokens(JHN_FIXTURE, book="Jhn", chapter=3, verse=16)

    assert sqlite_tokens == fixture_tokens
    assert sqlite_tokens[0] == fixture_tokens[0]
    assert sqlite_tokens[-1] == fixture_tokens[-1]
    assert sqlite_tokens[0].lemma == fixture_tokens[0].lemma
    assert sqlite_tokens[0].morph_code == fixture_tokens[0].morph_code
    assert sqlite_tokens[0].strong_id == fixture_tokens[0].strong_id
    assert sqlite_tokens[10].edition_flags == fixture_tokens[10].edition_flags


def test_repeated_import_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "tagnt.sqlite"

    first = import_tagnt_book(JHN_FIXTURE, database, "Jhn", "fixture")
    second = import_tagnt_book(JHN_FIXTURE, database, "Jhn", "fixture")

    assert first.rows_imported == 26
    assert second.rows_imported == 0
    assert second.duplicate_rows == 26
    assert len(get_sqlite_verse_tokens(database, "Jhn", 3, 16)) == 26


def test_missing_verse_returns_empty_list(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)

    assert get_sqlite_verse_tokens(database, "Jhn", 3, 999) == []


def test_missing_database_has_clear_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(FileNotFoundError, match="TAGNT SQLite database not found"):
        get_sqlite_verse_tokens(missing, "Jhn", 3, 16)


def test_invalid_schema_has_clear_error(tmp_path: Path) -> None:
    database = tmp_path / "invalid.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY)")

    with pytest.raises(ValueError, match="Invalid TAGNT SQLite database schema"):
        get_sqlite_verse_tokens(database, "Jhn", 3, 16)


def test_unicode_is_preserved(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)
    token = get_sqlite_verse_tokens(database, "Jhn", 3, 16)[2]

    assert token.greek_form == get_verse_tokens(JHN_FIXTURE, "Jhn", 3, 16)[2].greek_form


def test_parse_errors_are_reported_without_crashing(tmp_path: Path) -> None:
    source = tmp_path / "bad_rows.tsv"
    source.write_text(
        JHN_FIXTURE.read_text(encoding="utf-8")
        + "\n"
        + "not a valid TAGNT row\n",
        encoding="utf-8",
    )
    database = tmp_path / "tagnt.sqlite"

    report = import_tagnt_book(source, database, "Jhn", "fixture")

    assert report.rows_read == 27
    assert report.rows_imported == 26
    assert report.parse_errors == 1
    assert len(get_sqlite_verse_tokens(database, "Jhn", 3, 16)) == 26


def test_john_alternate_verse_numbering_rows_are_imported(tmp_path: Path) -> None:
    source = tmp_path / "john_alternate_numbering.tsv"
    source.write_text(
        "Jhn.7.53{8.1}#01=KO\t[[Καὶ (Kai)\t{8.1} And\tG2532=CONJ\t"
        "καί=and\tNA28+NA27+Tyn+WH+TR+Byz\t\t\t[[Y\tand\t#01\tG2532\t\t^\n",
        encoding="utf-8",
    )
    database = tmp_path / "tagnt.sqlite"

    report = import_tagnt_book(source, database, "Jhn", "fixture")
    tokens = get_sqlite_verse_tokens(database, "Jhn", 7, 53)

    assert report.rows_imported == 1
    assert report.parse_errors == 0
    assert tokens[0].book == "Jhn"
    assert tokens[0].chapter == 7
    assert tokens[0].verse == 53
    assert tokens[0].word_index == 1
    assert tokens[0].greek_form == "[[Καὶ"


def _import_fixture(tmp_path: Path) -> Path:
    database = tmp_path / "tagnt.sqlite"
    import_tagnt_book(JHN_FIXTURE, database, "Jhn", "fixture", "test")
    return database


def _sqlite_names(connection: sqlite3.Connection, type_name: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (type_name,),
    ).fetchall()
    return {row[0] for row in rows}
