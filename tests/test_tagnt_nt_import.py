from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from bible_engine.tagnt_sqlite import (
    TAGNT_NEW_TESTAMENT_BOOKS,
    BookImportCount,
    DatabaseValidationReport,
    FullImportReport,
    get_sqlite_verse_tokens,
    import_tagnt_new_testament,
    validate_tagnt_nt_database,
)


ROOT = Path(__file__).parents[1]
FIXTURE_DIR = Path(__file__).parent / "fixtures"
MAT_JHN_FIXTURE = FIXTURE_DIR / "tagnt_nt_mat_jhn_sample.tsv"
ACT_REV_FIXTURE = FIXTURE_DIR / "tagnt_nt_act_rev_sample.tsv"


def test_import_two_source_files_into_one_database(tmp_path: Path) -> None:
    database = tmp_path / "tagnt_nt.sqlite3"

    report = import_tagnt_new_testament(MAT_JHN_FIXTURE, ACT_REV_FIXTURE, database)

    assert isinstance(report, FullImportReport)
    assert report.rows_read == 8
    assert report.rows_imported == 8
    assert report.rows_skipped == 0
    assert report.parse_errors == 0
    assert report.duplicate_rows == 0
    assert report.books_imported == ("Mat", "Jhn", "Act", "Rom", "Jud", "Rev")
    assert database.exists()


def test_import_reports_per_book_counts(tmp_path: Path) -> None:
    database = _import_fixture_database(tmp_path)
    report = import_tagnt_new_testament(MAT_JHN_FIXTURE, ACT_REV_FIXTURE, database)

    counts = {count.book: count for count in report.per_book_rows}

    assert isinstance(counts["Mat"], BookImportCount)
    assert counts["Mat"].rows_imported == 2
    assert counts["Jhn"].rows_imported == 2
    assert counts["Act"].rows_imported == 1
    assert counts["Rom"].rows_imported == 1
    assert counts["Jud"].chapters == 1
    assert counts["Rev"].verses == 1


def test_validate_reports_missing_books_for_partial_fixture(tmp_path: Path) -> None:
    database = _import_fixture_database(tmp_path)

    report = validate_tagnt_nt_database(database)

    assert isinstance(report, DatabaseValidationReport)
    assert report.book_count == 6
    assert report.token_count == 8
    assert "Mrk" in report.missing_books
    assert "Missing TAGNT NT books" in report.warnings[0]


def test_validate_accepts_simulated_all_27_books(tmp_path: Path) -> None:
    mat_jhn = tmp_path / "all_mat_jhn.tsv"
    act_rev = tmp_path / "all_act_rev.tsv"
    database = tmp_path / "tagnt_nt.sqlite3"
    mat_jhn.write_text(_source_for_books(TAGNT_NEW_TESTAMENT_BOOKS[:4]), encoding="utf-8")
    act_rev.write_text(_source_for_books(TAGNT_NEW_TESTAMENT_BOOKS[4:]), encoding="utf-8")

    import_tagnt_new_testament(mat_jhn, act_rev, database)
    report = validate_tagnt_nt_database(database)

    assert report.book_count == 27
    assert report.token_count == 27
    assert report.chapter_count == 27
    assert report.verse_count == 27
    assert report.missing_books == ()
    assert report.warnings == ()
    assert report.per_book_counts[0].book == "Mat"
    assert report.per_book_counts[-1].book == "Rev"


def test_repeated_full_import_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "tagnt_nt.sqlite3"

    first = import_tagnt_new_testament(MAT_JHN_FIXTURE, ACT_REV_FIXTURE, database)
    second = import_tagnt_new_testament(MAT_JHN_FIXTURE, ACT_REV_FIXTURE, database)

    assert first.rows_imported == 8
    assert second.rows_imported == 0
    assert second.duplicate_rows == 8
    assert validate_tagnt_nt_database(database).token_count == 8


def test_unicode_and_core_fields_are_preserved(tmp_path: Path) -> None:
    database = _import_fixture_database(tmp_path)

    token = get_sqlite_verse_tokens(database, "Jhn", 3, 16)[0]

    assert token.greek_form == "οὕτως"
    assert token.lemma == "οὕτω, οὕτως"
    assert token.morph_code == "ADV"
    assert token.strong_id == "G3779"


def test_indexes_exist_after_full_import(tmp_path: Path) -> None:
    database = _import_fixture_database(tmp_path)

    with sqlite3.connect(database) as connection:
        indexes = _sqlite_names(connection, "index")

    assert "idx_greek_tokens_reference" in indexes
    assert "idx_greek_tokens_lemma" in indexes
    assert "idx_greek_tokens_strong_id" in indexes


def test_duplicate_records_are_reported(tmp_path: Path) -> None:
    mat_jhn = tmp_path / "dupe_mat_jhn.tsv"
    mat_jhn.write_text(
        MAT_JHN_FIXTURE.read_text(encoding="utf-8")
        + MAT_JHN_FIXTURE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    database = tmp_path / "tagnt_nt.sqlite3"

    report = import_tagnt_new_testament(mat_jhn, ACT_REV_FIXTURE, database)

    assert report.rows_imported == 8
    assert report.duplicate_rows == 4


def test_parse_errors_are_reported_without_crashing(tmp_path: Path) -> None:
    mat_jhn = tmp_path / "bad_mat_jhn.tsv"
    mat_jhn.write_text(
        MAT_JHN_FIXTURE.read_text(encoding="utf-8") + "Mat.1.1#bad\n",
        encoding="utf-8",
    )
    database = tmp_path / "tagnt_nt.sqlite3"

    report = import_tagnt_new_testament(mat_jhn, ACT_REV_FIXTURE, database)

    assert report.parse_errors == 1
    assert report.rows_imported == 8


def test_missing_source_file_has_clear_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.tsv"

    with pytest.raises(FileNotFoundError, match="TAGNT source file not found"):
        import_tagnt_new_testament(missing, ACT_REV_FIXTURE, tmp_path / "tagnt.sqlite3")


def test_empty_sources_create_empty_database_with_validation_warnings(tmp_path: Path) -> None:
    mat_jhn = tmp_path / "empty_mat_jhn.tsv"
    act_rev = tmp_path / "empty_act_rev.tsv"
    database = tmp_path / "tagnt_nt.sqlite3"
    mat_jhn.write_text("", encoding="utf-8")
    act_rev.write_text("", encoding="utf-8")

    import_report = import_tagnt_new_testament(mat_jhn, act_rev, database)
    validation = validate_tagnt_nt_database(database)

    assert import_report.rows_read == 0
    assert import_report.rows_imported == 0
    assert validation.book_count == 0
    assert validation.token_count == 0
    assert validation.missing_books == TAGNT_NEW_TESTAMENT_BOOKS


@pytest.mark.parametrize(
    ("book", "chapter", "verse", "expected_first"),
    [
        ("Mat", 1, 1, "Βίβλος"),
        ("Act", 2, 1, "Καὶ"),
        ("Rom", 8, 1, "Οὐδὲν"),
        ("Jud", 1, 20, "Ὑμεῖς"),
        ("Rev", 22, 21, "Ἡ"),
    ],
)
def test_sample_verses_can_be_read(
    tmp_path: Path,
    book: str,
    chapter: int,
    verse: int,
    expected_first: str,
) -> None:
    database = _import_fixture_database(tmp_path)

    tokens = get_sqlite_verse_tokens(database, book, chapter, verse)

    assert tokens
    assert [token.word_index for token in tokens] == sorted(
        token.word_index for token in tokens
    )
    assert tokens[0].greek_form == expected_first
    assert tokens[0].lemma
    assert tokens[0].morph_code
    assert tokens[0].strong_id


def test_john_current_lookup_still_works(tmp_path: Path) -> None:
    database = _import_fixture_database(tmp_path)

    tokens = get_sqlite_verse_tokens(database, "Jhn", 3, 16)

    assert len(tokens) == 2
    assert tokens[0].book == "Jhn"
    assert tokens[0].chapter == 3
    assert tokens[0].verse == 16


def test_legacy_john_build_script_remains_compatible(tmp_path: Path) -> None:
    database = tmp_path / "tagnt_john.sqlite3"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_tagnt_john_db.py"),
            "--source",
            str(MAT_JHN_FIXTURE),
            "--output",
            str(database),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Import complete" in result.stdout
    assert len(get_sqlite_verse_tokens(database, "Jhn", 3, 16)) == 2


def test_generated_databases_and_raw_sources_are_gitignored() -> None:
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "data/generated/tagnt_nt.sqlite3",
            "data/generated/tagnt_john.sqlite3",
            "data/raw/TAGNT_Mat-Jhn_raw.txt",
            "data/raw/TAGNT_Act-Rev_raw.txt",
            "_qa_shell/TAGNT_Mat-Jhn_raw.txt",
            "_qa_shell/TAGNT_Act-Rev_raw.txt",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "data/generated/tagnt_nt.sqlite3" in result.stdout
    assert "data/raw/TAGNT_Act-Rev_raw.txt" in result.stdout
    assert "_qa_shell/TAGNT_Act-Rev_raw.txt" in result.stdout


def _import_fixture_database(tmp_path: Path) -> Path:
    database = tmp_path / "tagnt_nt.sqlite3"
    import_tagnt_new_testament(MAT_JHN_FIXTURE, ACT_REV_FIXTURE, database)
    return database


def _source_for_books(books: tuple[str, ...]) -> str:
    rows = [
        "Word & Type\tGreek\tEnglish translation\tdStrongs = Grammar\t"
        "Dictionary form =  Gloss\teditions"
    ]
    for book in books:
        rows.append(_row(book, 1, 1, 1, "λόγος", "G3056", "N-NSM", "λόγος"))
    return "\n".join(rows) + "\n"


def _row(
    book: str,
    chapter: int,
    verse: int,
    word_index: int,
    greek: str,
    strong_id: str,
    morph_code: str,
    lemma: str,
) -> str:
    return (
        f"{book}.{chapter}.{verse}#{word_index:02d}=NKO\t"
        f"{greek} (logos)\tword\t{strong_id}={morph_code}\t"
        f"{lemma}=word\tNA28+NA27+Tyn+SBL+WH+Treg+TR+Byz"
    )


def _sqlite_names(connection: sqlite3.Connection, type_name: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (type_name,),
    ).fetchall()
    return {row[0] for row in rows}
