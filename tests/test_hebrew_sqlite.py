from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from bible_engine.hebrew_sqlite import (
    _strip_hebrew_cantillation,
    find_hebrew_tokens_by_lemma,
    find_hebrew_tokens_by_strong_id,
    get_hebrew_books,
    get_hebrew_lexicon_entry,
    get_hebrew_passage_tokens,
    get_hebrew_token,
    inspect_hebrew_database_path,
    import_hebrew_fixture_database,
)
from bible_engine.tbesh_parser import parse_tbesh_rows


FIXTURES = Path(__file__).parent / "fixtures"
TAHOT = FIXTURES / "tahot_ruth_psa_sample.tsv"
TBESH = FIXTURES / "tbesh_ruth_psa_sample.tsv"


def test_sqlite_round_trip_and_indexes(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"

    report = import_hebrew_fixture_database(TAHOT, TBESH, database)
    tokens = get_hebrew_passage_tokens(database, "Rut", 1, 1, 5)

    assert report.tokens_imported == len(TAHOT.read_text(encoding="utf-8").splitlines())
    assert report.books == ("Rut", "Psa")
    assert tokens[0].stable_key == "Rut:1:1:1"
    assert tokens[-1].verse == 5
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            "metadata",
            "books",
            "tokens",
            "token_components",
            "token_strong_ids",
            "ketiv_qere",
            "lexicon_entries",
        }.issubset(tables)
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_different_current_working_directory_still_reads_database(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        tokens = get_hebrew_passage_tokens(database.resolve(), "Psa", 23, 1, 4)
    finally:
        os.chdir(old_cwd)

    assert tokens[0].book == "Psa"
    assert tokens[-1].verse == 4


def test_tbesh_lexicon_linking_and_unknown_strong(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)

    entry = get_hebrew_lexicon_entry(database, "H1961")
    missing = get_hebrew_lexicon_entry(database, "H9999Z")

    assert entry is not None
    assert entry.gloss or entry.meaning
    assert missing is None


def test_repository_queries_and_diagnostics(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)

    diagnostics = inspect_hebrew_database_path(database)
    books = get_hebrew_books(database)
    token = get_hebrew_token(database, "Rut:1:1:1")
    lemma_tokens = find_hebrew_tokens_by_lemma(database, "הָיָה")
    strong_tokens = find_hebrew_tokens_by_strong_id(database, "H1961")

    assert diagnostics.exists
    assert diagnostics.required_tables_present
    assert books[0][0] == "Rut"
    assert token is not None
    assert token.stable_key == "Rut:1:1:1"
    assert any(item.stable_key == "Rut:1:1:1" for item in lemma_tokens)
    assert any(item.stable_key == "Rut:1:1:1" for item in strong_tokens)


def test_tbesh_parser_reads_fixture_records() -> None:
    entries = parse_tbesh_rows(TBESH.read_text(encoding="utf-8"))

    assert entries
    assert any("H1961" in entry.strong_ids for entry in entries)


def test_tbesh_parser_extracts_ids_from_annotated_fields() -> None:
    record = (
        "H6635B = a Name of\tH6635B = a Name of\tH6635B\t"
        "צָבָא\ttsa.va'\tN:N-M-T\tHosts\tname guidance"
    )

    entry = parse_tbesh_rows("eStrong#\tdStrong\tuStrong\tHebrew\tTransliteration\tMorph\tGloss\tMeaning\n" + record)[0]

    assert entry.strong_ids == ("H6635B",)


def test_strip_hebrew_cantillation_removes_accent_marks() -> None:
    """A TAHOT lemma-mező gyakran tartalmaz kantillációs (te'amim)
    jeleket (pl. "חֶ֫סֶד"), amit egy felhasználó normál begépeléssel
    szinte sosem ír be — a lemma-keresésnek ezért ezen jelek nélkül
    kell egyeznie."""
    with_accent = "חֶ֫סֶד"
    without_accent = "חֶסֶד"
    assert _strip_hebrew_cantillation(with_accent) == without_accent
    assert _strip_hebrew_cantillation(without_accent) == without_accent


def test_strip_hebrew_cantillation_handles_empty_and_none() -> None:
    assert _strip_hebrew_cantillation("") == ""
    assert _strip_hebrew_cantillation(None) == ""


def test_find_hebrew_tokens_by_strong_id_bare_number_matches_lettered_variant(tmp_path: Path) -> None:
    """Ha egy Strong-szám a TAHOT-ban kizárólag betű-suffixummal
    ellátott változatként létezik (pl. "H1961A"), a suffixum nélküli
    ("H1961") keresésnek is meg kell találnia — a felhasználók a
    szokásos, suffixum nélküli formát írják be."""
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE token_strong_ids SET strong_id = 'H1961A' WHERE strong_id = 'H1961'"
        )
        connection.commit()

    tokens = find_hebrew_tokens_by_strong_id(database, "H1961")

    assert len(tokens) > 0
