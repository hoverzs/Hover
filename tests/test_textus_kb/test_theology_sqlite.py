"""Isolated Theology DB v1 SQLite store tests."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.importers.theology_sqlite import (
    DEFAULT_FIXTURE_PATH,
    SCHEMA_VERSION,
    TheologyImportError,
    create_empty_theology_database,
    create_schema,
    hash_theology_document,
    import_theology_sqlite,
    load_fixture_document,
    normalize_theology_document,
    validate_theology_database,
)
from textus_kb.repositories.theology_repository import TheologyRepository

FIXTURE_PATH = Path("tests/fixtures/kb/theology_v1_sample.json")
REQUIRED_EDITION_FIELDS = (
    "rights_status",
    "license",
    "source_url",
    "corpus",
    "external_id",
)


def _sqlite_names(connection: sqlite3.Connection, kind: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (kind,),
    ).fetchall()
    return {row[0] for row in rows}


def _load_document() -> dict:
    return load_fixture_document(FIXTURE_PATH)


def test_default_fixture_path_matches_repo_fixture() -> None:
    assert DEFAULT_FIXTURE_PATH.resolve() == FIXTURE_PATH.resolve()


def test_create_schema_creates_tables_indexes_and_fts(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        tables = _sqlite_names(connection, "table")
        indexes = _sqlite_names(connection, "index")
        fts_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'"
        ).fetchone()[0]

    assert {
        "store_metadata",
        "authors",
        "works",
        "editions",
        "sections",
        "chunks",
        "passage_links",
        "chunks_fts",
    } <= tables
    assert "idx_chunks_section" in indexes
    assert "idx_passage_links_canonical" in indexes
    assert "fts5" in fts_sql.lower()
    assert "unicode61" in fts_sql


def test_schema_version_is_one_for_empty_and_fixture_stores(tmp_path: Path) -> None:
    empty = create_empty_theology_database(tmp_path / "empty.sqlite3")
    imported = import_theology_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "fixture.sqlite3",
    )
    assert empty.schema_version == SCHEMA_VERSION == "1"
    assert imported.schema_version == "1"
    assert validate_theology_database(tmp_path / "empty.sqlite3").schema_version == "1"
    assert TheologyRepository(tmp_path / "fixture.sqlite3").store_status().schema_version == "1"


def test_fixture_import_writes_expected_records(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    report = import_theology_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    assert report.author_count == 1
    assert report.work_count == 1
    assert report.edition_count == 1
    assert report.section_count == 2
    assert report.chunk_count == 2
    assert report.passage_link_count == 1
    assert report.import_mode == "fixture"
    assert database.is_file()


def test_fixture_provenance_chain(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    import_theology_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                c.chunk_id,
                c.source_locator,
                s.section_id,
                s.heading,
                e.edition_id,
                e.license,
                e.rights_status,
                e.source_url,
                e.corpus,
                e.external_id,
                w.work_id,
                w.title,
                a.author_id,
                a.canonical_name
            FROM chunks c
            JOIN sections s ON s.section_id = c.section_id
            JOIN editions e ON e.edition_id = s.edition_id
            JOIN works w ON w.work_id = e.work_id
            JOIN authors a ON a.author_id = w.author_id
            WHERE c.chunk_id = 'test.chunk.alpha'
            """
        ).fetchone()

    assert row is not None
    assert row["section_id"] == "test.section.alpha"
    assert row["edition_id"] == "test.edition.synthetic_notes.en"
    assert row["work_id"] == "test.work.synthetic_notes"
    assert row["author_id"] == "test.author.synthetic"
    assert row["canonical_name"] == "Synthetic Test Author"
    assert row["license"] == "CC-BY-4.0"
    assert row["rights_status"] == "public-domain"
    assert row["source_url"] == "https://example.test/theology-v1-fixture"
    assert row["corpus"] == "test-fixture"
    assert row["external_id"] == "textus-theology-v1-sample"
    assert row["source_locator"] == "fixture://theology-v1/section-alpha#1"


@pytest.mark.parametrize("field", REQUIRED_EDITION_FIELDS)
def test_import_rejects_missing_edition_rights_metadata(
    tmp_path: Path,
    field: str,
) -> None:
    document = _load_document()
    document["editions"][0][field] = ""
    with pytest.raises(TheologyImportError, match="missing required field"):
        import_theology_sqlite(
            document=document,
            database_path=tmp_path / "theology.sqlite3",
        )


def test_import_rejects_absent_edition_license(tmp_path: Path) -> None:
    document = _load_document()
    del document["editions"][0]["license"]
    with pytest.raises(TheologyImportError, match="license"):
        import_theology_sqlite(
            document=document,
            database_path=tmp_path / "theology.sqlite3",
        )


def test_passage_link_is_normalized_with_canonical_reference(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    import_theology_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    expected = CanonicalReference.parse("John.3.16")

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT chunk_id, book_id, start_chapter, start_verse,
                   end_chapter, end_verse, canonical_passage, raw_citation
            FROM passage_links
            """
        ).fetchone()

    assert row is not None
    assert row["chunk_id"] == "test.chunk.alpha"
    assert row["book_id"] == expected.book_id == "John"
    assert row["start_chapter"] == expected.start_chapter == 3
    assert row["start_verse"] == expected.start_verse == 16
    assert row["end_chapter"] == expected.end_chapter == 3
    assert row["end_verse"] == expected.end_verse == 16
    assert row["canonical_passage"] == expected.canonical_string() == "John.3.16"
    assert row["raw_citation"] == "John.3.16"


def test_fts5_search_matches_plain_text_and_heading(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    import_theology_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    repo = TheologyRepository(database)

    text_hits = repo.search_plain_text("Alpha marker phrase")
    assert len(text_hits) == 1
    assert text_hits[0].chunk_id == "test.chunk.alpha"
    assert "Alpha marker" in text_hits[0].plain_text
    assert "**" in text_hits[0].snippet

    heading_hits = repo.search_plain_text("Synthetic Beta Heading")
    assert len(heading_hits) == 1
    assert heading_hits[0].chunk_id == "test.chunk.beta"
    assert heading_hits[0].heading == "Synthetic Beta Heading"


def test_fts_special_characters_do_not_raise(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    import_theology_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    repo = TheologyRepository(database)

    assert repo.search_plain_text('"fura- lekérdezés:1') == []
    assert repo.search_plain_text("alpha AND missing") == []


def test_store_status_counts_match_fixture(tmp_path: Path) -> None:
    database = tmp_path / "theology.sqlite3"
    report = import_theology_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    status = TheologyRepository(database).store_status()

    assert status.available is True
    assert status.schema_version == "1"
    assert status.author_count == report.author_count == 1
    assert status.work_count == report.work_count == 1
    assert status.edition_count == report.edition_count == 1
    assert status.section_count == report.section_count == 2
    assert status.chunk_count == report.chunk_count == 2
    assert status.passage_link_count == report.passage_link_count == 1
    assert status.content_hash == report.content_hash
    assert status.import_mode == "fixture"


def test_missing_database_is_fail_closed(tmp_path: Path) -> None:
    repo = TheologyRepository(tmp_path / "missing.sqlite3")
    status = repo.store_status()

    assert repo.available is False
    assert status.available is False
    assert status.schema_version == ""
    assert status.author_count == 0
    assert status.work_count == 0
    assert status.edition_count == 0
    assert status.section_count == 0
    assert status.chunk_count == 0
    assert status.passage_link_count == 0
    assert repo.search_plain_text("Alpha marker") == []


def test_invalid_database_is_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "broken.sqlite3"
    path.write_text("not a sqlite database", encoding="utf-8")
    status = TheologyRepository(path).store_status()
    assert status.available is False
    assert TheologyRepository(path).search_plain_text("Alpha") == []


def test_empty_database_store_status_is_available_with_zero_counts(tmp_path: Path) -> None:
    database = tmp_path / "empty.sqlite3"
    create_empty_theology_database(database)
    status = TheologyRepository(database).store_status()
    assert status.available is True
    assert status.schema_version == "1"
    assert status.import_mode == "empty"
    assert status.chunk_count == 0
    assert status.passage_link_count == 0


def test_content_hash_is_deterministic_for_identical_input(tmp_path: Path) -> None:
    first = import_theology_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "a.sqlite3",
    )
    second = import_theology_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "b.sqlite3",
    )
    document = normalize_theology_document(_load_document())
    expected = hash_theology_document(document)

    assert first.content_hash == second.content_hash == expected
    assert len(first.content_hash) == 64
    assert first.content_hash != second.generated_at


def test_content_hash_changes_when_fixture_changes(tmp_path: Path) -> None:
    original = import_theology_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "a.sqlite3",
    )
    mutated = copy.deepcopy(_load_document())
    mutated["chunks"][1]["plain_text"] = "SYNTHETIC TEST ONLY. Changed beta phrase."
    changed = import_theology_sqlite(
        document=mutated,
        database_path=tmp_path / "b.sqlite3",
    )
    assert original.content_hash != changed.content_hash


def test_build_script_empty_and_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.build_theology_database import main as build_main

    empty_path = tmp_path / "empty.sqlite3"
    fixture_path = tmp_path / "fixture.sqlite3"

    assert build_main(["--empty", "--output", str(empty_path)]) == 0
    empty_payload = json.loads(capsys.readouterr().out)
    assert empty_payload["import_mode"] == "empty"
    assert empty_payload["schema_version"] == "1"
    assert empty_payload["chunk_count"] == 0

    assert build_main(
        ["--fixture", str(FIXTURE_PATH), "--output", str(fixture_path)]
    ) == 0
    fixture_payload = json.loads(capsys.readouterr().out)
    assert fixture_payload["import_mode"] == "fixture"
    assert fixture_payload["chunk_count"] == 2
    assert TheologyRepository(fixture_path).store_status().available is True
