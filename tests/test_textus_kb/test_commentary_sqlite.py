"""Isolated Commentary DB v1 SQLite store tests."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.importers.commentary_sqlite import (
    DEFAULT_FIXTURE_PATH,
    SCHEMA_VERSION,
    CommentaryImportError,
    create_empty_commentary_database,
    create_schema,
    hash_commentary_document,
    import_commentary_sqlite,
    load_fixture_document,
    normalize_commentary_document,
    sha256_bytes,
    sha256_file,
    validate_commentary_database,
)
from textus_kb.repositories.commentary_repository import CommentaryRepository

FIXTURE_PATH = Path("tests/fixtures/kb/commentary_v1_sample.json")
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
    database = tmp_path / "commentary.sqlite3"
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        tables = _sqlite_names(connection, "table")
        indexes = _sqlite_names(connection, "index")
        sections_fts_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'sections_fts'"
        ).fetchone()[0]
        chunks_fts_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'"
        ).fetchone()[0]

    assert {
        "store_metadata",
        "contributors",
        "works",
        "work_contributors",
        "editions",
        "source_files",
        "import_batches",
        "sections",
        "section_passage_links",
        "chunks",
        "sections_fts",
        "chunks_fts",
    } <= tables
    assert "idx_chunks_section" in indexes
    assert "idx_section_passage_links_canonical" in indexes
    assert "idx_section_passage_links_book" in indexes
    assert "fts5" in sections_fts_sql.lower()
    assert "fts5" in chunks_fts_sql.lower()
    assert "unicode61" in sections_fts_sql


def test_chunks_table_has_no_passage_columns(tmp_path: Path) -> None:
    """Regression guard: passage truth lives on sections, never on chunks."""
    database = tmp_path / "commentary.sqlite3"
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(chunks)").fetchall()
        }
    passage_like = {
        col
        for col in columns
        if "passage" in col or "book_id" in col or "chapter" in col or "verse" in col
    }
    assert passage_like == set()


def test_schema_version_is_two_for_empty_and_fixture_stores(tmp_path: Path) -> None:
    empty = create_empty_commentary_database(tmp_path / "empty.sqlite3")
    imported = import_commentary_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "fixture.sqlite3",
    )
    assert empty.schema_version == SCHEMA_VERSION == "2"
    assert imported.schema_version == "2"
    assert validate_commentary_database(tmp_path / "empty.sqlite3").schema_version == "2"
    assert (
        CommentaryRepository(tmp_path / "fixture.sqlite3").store_status().schema_version == "2"
    )


def test_fixture_import_writes_expected_records(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    report = import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    assert report.contributor_count == 3
    assert report.work_count == 1
    assert report.work_contributor_count == 3
    assert report.edition_count == 1
    assert report.source_file_count == 1
    assert report.import_batch_count == 1
    assert report.section_count == 6
    assert report.chunk_count == 8
    assert report.passage_link_count == 6
    assert report.import_mode == "fixture"
    assert database.is_file()


def test_fixture_provenance_chain(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                c.chunk_id,
                s.section_id,
                e.edition_id,
                e.license,
                e.rights_status,
                w.work_id,
                w.title
            FROM chunks c
            JOIN sections s ON s.section_id = c.section_id
            JOIN editions e ON e.edition_id = s.edition_id
            JOIN works w ON w.work_id = e.work_id
            WHERE c.chunk_id = 'test.chunk.john316_exact'
            """
        ).fetchone()

    assert row is not None
    assert row["section_id"] == "test.section.john316_exact"
    assert row["edition_id"] == "test.edition.synthetic_commentary.en"
    assert row["work_id"] == "test.work.synthetic_commentary"
    assert row["title"] == "Synthetic Commentary on John"
    assert row["license"] == "CC-BY-4.0"
    assert row["rights_status"] == "public-domain"


def test_multiple_contributors_with_roles(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT c.canonical_name, wc.role
            FROM work_contributors wc
            JOIN contributors c ON c.contributor_id = wc.contributor_id
            ORDER BY wc.role
            """
        ).fetchall()

    roles = {row["role"] for row in rows}
    assert roles == {"author", "translator", "editor"}
    assert len(rows) == 3


# --- Provenance -------------------------------------------------------


def test_raw_sha256_provenance_recorded(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        source_file = connection.execute(
            "SELECT * FROM source_files WHERE source_file_id = 'test.source_file.john_commentary_raw'"
        ).fetchone()
        batch = connection.execute(
            "SELECT * FROM import_batches WHERE source_file_id = 'test.source_file.john_commentary_raw'"
        ).fetchone()

    assert source_file is not None
    assert source_file["raw_sha256"] == "f321dc42db147968ce079f72b078a40d2e8243c8fdf62cdc9e127e08de485e56"
    assert len(source_file["raw_sha256"]) == 64
    assert source_file["edition_id"] == "test.edition.synthetic_commentary.en"
    assert source_file["file_name"] == "synthetic_john_commentary.xml"

    assert batch is not None
    assert batch["importer_name"] == "textus_kb.importers.commentary_sqlite"
    assert batch["importer_version"] == "0.1.0"
    assert batch["imported_at"] == "2026-08-01T00:05:00Z"
    assert json.loads(batch["report"]) == {"note": "synthetic fixture batch"}


def test_raw_fingerprint_and_normalized_content_hash_are_distinct(tmp_path: Path) -> None:
    """Raw source SHA-256 and the normalized-document content hash are two different concepts."""
    database = tmp_path / "commentary.sqlite3"
    report = import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        source_file = connection.execute("SELECT raw_sha256 FROM source_files").fetchone()
        batch = connection.execute("SELECT content_hash FROM import_batches").fetchone()

    assert source_file["raw_sha256"] != batch["content_hash"]
    assert batch["content_hash"] == report.content_hash
    # Mutating raw bytes (a re-download of the same logical file) must not be
    # required to change when only downstream normalized content changes, and
    # vice versa: the two hashes are computed over different inputs.
    assert sha256_bytes(b"synthetic-commentary-fixture-source-v1") == source_file["raw_sha256"]


def test_sha256_file_matches_sha256_bytes(tmp_path: Path) -> None:
    payload = b"raw commentary source fixture bytes"
    path = tmp_path / "raw.xml"
    path.write_bytes(payload)
    assert sha256_file(path) == sha256_bytes(payload) == hashlib.sha256(payload).hexdigest()


def test_import_rejects_invalid_raw_sha256(tmp_path: Path) -> None:
    document = _load_document()
    document["source_files"][0]["raw_sha256"] = "not-a-valid-hash"
    with pytest.raises(CommentaryImportError, match="raw_sha256"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_import_rejects_source_file_unknown_edition(tmp_path: Path) -> None:
    document = _load_document()
    document["source_files"][0]["edition_id"] = "unknown.edition"
    with pytest.raises(CommentaryImportError, match="unknown edition_id"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_import_rejects_batch_unknown_source_file(tmp_path: Path) -> None:
    document = _load_document()
    document["import_batches"][0]["source_file_id"] = "unknown.source_file"
    with pytest.raises(CommentaryImportError, match="unknown source_file_id"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


# --- Field validation ---------------------------------------------------


@pytest.mark.parametrize("field", REQUIRED_EDITION_FIELDS)
def test_import_rejects_missing_edition_rights_metadata(
    tmp_path: Path,
    field: str,
) -> None:
    document = _load_document()
    document["editions"][0][field] = ""
    with pytest.raises(CommentaryImportError, match="missing required field"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_import_rejects_unknown_contributor_role(tmp_path: Path) -> None:
    document = _load_document()
    document["work_contributors"][0]["role"] = "ghostwriter"
    with pytest.raises(CommentaryImportError, match="Unsupported work_contributors role"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_import_rejects_work_contributor_unknown_ids(tmp_path: Path) -> None:
    document = _load_document()
    document["work_contributors"][0]["contributor_id"] = "unknown.contributor"
    with pytest.raises(CommentaryImportError, match="unknown contributor_id"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


# --- Data-quality invariants: fail loudly, never silently dedupe --------


def test_import_rejects_duplicate_work_contributor(tmp_path: Path) -> None:
    """(work_id, contributor_id, role) must be unique; a repeated declaration
    (e.g. from combining multiple per-book source files that each redeclare
    the same author) is a data-quality error, not something to silently drop."""
    document = _load_document()
    document["work_contributors"].append(dict(document["work_contributors"][0]))
    with pytest.raises(CommentaryImportError, match="Duplicate work_contributors entry"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_work_contributors_unique_index_is_defense_in_depth(tmp_path: Path) -> None:
    """DB-level UNIQUE constraint rejects a duplicate even if inserted directly,
    bypassing normalize_commentary_document."""
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        row = connection.execute(
            "SELECT work_id, contributor_id, role FROM work_contributors LIMIT 1"
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO work_contributors (work_id, contributor_id, role) VALUES (?, ?, ?)",
                row,
            )


def test_import_rejects_cross_edition_parent_section(tmp_path: Path) -> None:
    """A section's parent_section_id must belong to the same edition_id."""
    document = _load_document()
    document["editions"].append(
        {
            "edition_id": "test.edition.other",
            "work_id": "test.work.synthetic_commentary",
            "edition_label": "Other edition",
            "publication_year": 1901,
            "publisher": "Textus Test Fixture",
            "language": "en",
            "license": "CC-BY-4.0",
            "rights_status": "public-domain",
            "rights_note": "synthetic",
            "source_url": "https://example.test/other-edition",
            "corpus": "test-fixture",
            "external_id": "other-edition",
        }
    )
    document["sections"].append(
        {
            "section_id": "test.section.cross_edition_leak",
            "edition_id": "test.edition.other",
            "parent_section_id": "test.section.chapter3",
            "section_type": "section",
            "heading": "Leaked cross-edition child",
            "sequence": 1,
            "passage_links": [],
        }
    )
    with pytest.raises(CommentaryImportError, match="different edition"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_import_rejects_duplicate_passage_link_in_section(tmp_path: Path) -> None:
    """The same canonical passage must not be linked twice on one section."""
    document = _load_document()
    exact_section = next(
        s for s in document["sections"] if s["section_id"] == "test.section.john316_exact"
    )
    exact_section["passage_links"].append(dict(exact_section["passage_links"][0]))
    with pytest.raises(CommentaryImportError, match="Duplicate passage_link"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_section_passage_links_unique_index_is_defense_in_depth(tmp_path: Path) -> None:
    """DB-level UNIQUE(section_id, canonical_passage) rejects a duplicate even
    if inserted directly, bypassing normalize_commentary_document."""
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        row = connection.execute(
            """
            SELECT section_id, book_id, start_chapter, start_verse,
                   end_chapter, end_verse, canonical_passage, raw_citation, relation_type
            FROM section_passage_links LIMIT 1
            """
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO section_passage_links (
                    section_id, book_id, start_chapter, start_verse,
                    end_chapter, end_verse, canonical_passage, raw_citation, relation_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )


# --- Architectural invariant: section owns passage truth, not chunk -----


def test_chunk_with_passage_links_is_rejected(tmp_path: Path) -> None:
    """Explicit regression: passage truth is section_passage_links, never the chunk."""
    document = _load_document()
    document["chunks"][0]["passage_links"] = [{"raw_citation": "John 1:1"}]
    with pytest.raises(CommentaryImportError, match="must not declare passage_links"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


def test_multi_passage_section_stores_all_links(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT canonical_passage FROM section_passage_links
            WHERE section_id = 'test.section.multi_passage'
            ORDER BY canonical_passage
            """
        ).fetchall()

    passages = {row["canonical_passage"] for row in rows}
    assert passages == {"John.4.1-6", "John.3.16"}


def test_parent_child_section_hierarchy(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT parent_section_id FROM sections WHERE section_id = 'test.section.john316_exact'"
        ).fetchone()
        root = connection.execute(
            "SELECT parent_section_id FROM sections WHERE section_id = 'test.section.book'"
        ).fetchone()

    assert row["parent_section_id"] == "test.section.chapter3"
    assert root["parent_section_id"] is None


def test_import_rejects_unresolved_parent_section(tmp_path: Path) -> None:
    document = _load_document()
    document["sections"][1]["parent_section_id"] = "unknown.section"
    with pytest.raises(CommentaryImportError, match="unknown parent_section_id"):
        import_commentary_sqlite(
            document=document,
            database_path=tmp_path / "commentary.sqlite3",
        )


# --- Passage link normalization ------------------------------------------


def test_range_passage_link_is_normalized_with_canonical_reference(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    expected = CanonicalReference.parse("John 3:16-21")

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT section_id, book_id, start_chapter, start_verse,
                   end_chapter, end_verse, canonical_passage, raw_citation
            FROM section_passage_links
            WHERE section_id = 'test.section.john316_21_range'
            """
        ).fetchone()

    assert row is not None
    assert row["book_id"] == expected.book_id == "John"
    assert row["start_chapter"] == expected.start_chapter == 3
    assert row["start_verse"] == expected.start_verse == 16
    assert row["end_chapter"] == expected.end_chapter == 3
    assert row["end_verse"] == expected.end_verse == 21
    assert row["canonical_passage"] == expected.canonical_string() == "John.3.16-21"


# --- FTS ------------------------------------------------------------------


def test_sections_fts_aggregates_multiple_chunks(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT plain_text FROM sections_fts WHERE section_id = 'test.section.chapter3'"
        ).fetchone()

    assert "GAMMA MARKER PART ONE" in row["plain_text"]
    assert "GAMMA MARKER PART TWO" in row["plain_text"]
    assert "GAMMA MARKER PART THREE" in row["plain_text"]


def test_fts_special_characters_do_not_raise(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    from textus_kb.repositories.commentary_repository import CommentaryRepository as Repo

    repo = Repo(database)
    assert repo.search_text('"fura- lekérdezés:1') == []
    assert repo.search_text("gamma AND missing") == []


# --- Store status / fail-closed -------------------------------------------


def test_store_status_counts_match_fixture(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    report = import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    status = CommentaryRepository(database).store_status()

    assert status.available is True
    assert status.schema_version == "2"
    assert status.contributor_count == report.contributor_count == 3
    assert status.work_count == report.work_count == 1
    assert status.edition_count == report.edition_count == 1
    assert status.source_file_count == report.source_file_count == 1
    assert status.import_batch_count == report.import_batch_count == 1
    assert status.section_count == report.section_count == 6
    assert status.chunk_count == report.chunk_count == 8
    assert status.passage_link_count == report.passage_link_count == 6
    assert status.content_hash == report.content_hash
    assert status.import_mode == "fixture"


def test_missing_database_is_fail_closed(tmp_path: Path) -> None:
    repo = CommentaryRepository(tmp_path / "missing.sqlite3")
    status = repo.store_status()

    assert repo.available is False
    assert status.available is False
    assert status.schema_version == ""
    assert status.section_count == 0
    assert status.chunk_count == 0
    assert status.passage_link_count == 0
    assert repo.sections_for_passage("John.3.16") == []
    assert repo.search_text("gamma") == []
    assert repo.section_detail("test.section.book") is None
    assert repo.broader_context("test.section.book") == []


def test_invalid_database_is_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "broken.sqlite3"
    path.write_text("not a sqlite database", encoding="utf-8")
    status = CommentaryRepository(path).store_status()
    assert status.available is False
    assert CommentaryRepository(path).sections_for_passage("John.3.16") == []


def test_empty_database_store_status_is_available_with_zero_counts(tmp_path: Path) -> None:
    database = tmp_path / "empty.sqlite3"
    create_empty_commentary_database(database)
    status = CommentaryRepository(database).store_status()
    assert status.available is True
    assert status.schema_version == "2"
    assert status.import_mode == "empty"
    assert status.chunk_count == 0
    assert status.passage_link_count == 0


def test_wrong_schema_version_is_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE store_metadata SET value = '999' WHERE key = 'schema_version'"
        )
        connection.commit()
    status = CommentaryRepository(database).store_status()
    assert status.available is False
    assert status.schema_version == "999"


def test_missing_required_table_is_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE chunks")
        connection.commit()
    with pytest.raises(CommentaryImportError, match="schema incompatible"):
        validate_commentary_database(database)


# --- Content hash determinism ---------------------------------------------


def test_content_hash_is_deterministic_for_identical_input(tmp_path: Path) -> None:
    first = import_commentary_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "a.sqlite3",
    )
    second = import_commentary_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "b.sqlite3",
    )
    document = normalize_commentary_document(_load_document())
    expected = hash_commentary_document(document)

    assert first.content_hash == second.content_hash == expected
    assert len(first.content_hash) == 64
    assert first.content_hash != second.generated_at


def test_content_hash_changes_when_fixture_changes(tmp_path: Path) -> None:
    original = import_commentary_sqlite(
        fixture_path=FIXTURE_PATH,
        database_path=tmp_path / "a.sqlite3",
    )
    mutated = copy.deepcopy(_load_document())
    mutated["chunks"][1]["plain_text"] = "SYNTHETIC TEST ONLY. Changed gamma phrase."
    changed = import_commentary_sqlite(
        document=mutated,
        database_path=tmp_path / "b.sqlite3",
    )
    assert original.content_hash != changed.content_hash


def test_atomic_build_leaves_no_temp_file_on_success(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    leftovers = list(tmp_path.glob(".*tmp.sqlite3"))
    assert leftovers == []
    assert database.is_file()


def test_atomic_build_does_not_clobber_existing_db_on_failure(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    before = database.read_bytes()

    broken = _load_document()
    broken["editions"][0]["license"] = ""
    with pytest.raises(CommentaryImportError):
        import_commentary_sqlite(document=broken, database_path=database)

    assert database.read_bytes() == before
    leftovers = list(tmp_path.glob(".*tmp.sqlite3"))
    assert leftovers == []


def test_build_script_empty_and_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.build_commentary_database import main as build_main

    empty_path = tmp_path / "empty.sqlite3"
    fixture_path = tmp_path / "fixture.sqlite3"

    assert build_main(["--empty", "--output", str(empty_path)]) == 0
    empty_payload = json.loads(capsys.readouterr().out)
    assert empty_payload["import_mode"] == "empty"
    assert empty_payload["schema_version"] == "2"
    assert empty_payload["chunk_count"] == 0

    assert build_main(
        ["--fixture", str(FIXTURE_PATH), "--output", str(fixture_path)]
    ) == 0
    fixture_payload = json.loads(capsys.readouterr().out)
    assert fixture_payload["import_mode"] == "fixture"
    assert fixture_payload["chunk_count"] == 8
    assert CommentaryRepository(fixture_path).store_status().available is True
