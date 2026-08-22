from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bible_engine.hymn_sqlite import (
    create_schema,
    get_hymn_by_number,
    get_hymnal_summary,
    import_dtx_hymnal_database,
    search_fts,
)


ROOT = Path(__file__).resolve().parents[1]
ERE_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"


def test_create_schema_creates_tables_indexes_and_fts(tmp_path: Path) -> None:
    database = tmp_path / "hymns.sqlite3"
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        tables = _sqlite_names(connection, "table")
        indexes = _sqlite_names(connection, "index")

    assert {"hymnals", "sections", "hymns", "stanzas", "import_meta", "hymns_fts"} <= tables
    assert "idx_hymns_hymnal_number" in indexes
    assert "idx_stanzas_hymn" in indexes


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    database = tmp_path / "hymns.sqlite3"
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO sections(hymnal_id, title, ordinal) VALUES (?, ?, ?)",
                (999, "Missing hymnal", 1),
            )


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_full_ere_import_counts_and_summary(tmp_path: Path) -> None:
    database = _build_ere(tmp_path)

    summary = get_hymnal_summary(database, hymnal_code="ERE")

    assert summary is not None
    assert summary.code == "ERE"
    assert summary.title == "Erdélyi Református Énekeskönyv"
    assert summary.dtx_code == "E.Ref"
    assert summary.source_format == "DiaTar DTX"
    assert summary.hymn_count == 513
    assert summary.base_number_count == 504
    assert summary.section_count == 44
    assert summary.stanza_count == 2697
    assert summary.parser_warning_count == 0
    assert len(summary.source_checksum) == 64


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_variants_are_separate_unique_records(tmp_path: Path) -> None:
    database = _build_ere(tmp_path)

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT canonical_key, number, COALESCE(variant, '') AS variant
            FROM hymns
            WHERE number IN (152, 181, 211, 254, 309, 330, 391, 400)
            ORDER BY number_sort, canonical_key
            """
        ).fetchall()
        duplicate_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT hymnal_id, canonical_key, COUNT(*) AS total
                FROM hymns
                GROUP BY hymnal_id, canonical_key
                HAVING total > 1
            )
            """
        ).fetchone()[0]

    assert [row[0] for row in rows] == [
        "152a",
        "181a",
        "181b",
        "211a",
        "211b",
        "211c",
        "254a",
        "254b",
        "309a",
        "309b",
        "330a",
        "330b",
        "391a",
        "391b",
        "400a",
        "400b",
    ]
    assert duplicate_count == 0


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_representative_hymn_lookups(tmp_path: Path) -> None:
    database = _build_ere(tmp_path)

    hymn_1 = get_hymn_by_number(database, "ERE", 1)
    hymn_119 = get_hymn_by_number(database, "ERE", 119)
    hymn_254a = get_hymn_by_number(database, "ERE", 254, "a")
    hymn_254b = get_hymn_by_number(database, "ERE", 254, "b")
    hymn_504 = get_hymn_by_number(database, "ERE", 504)

    assert hymn_1 is not None
    assert hymn_1.canonical_key == "1"
    assert hymn_1.title == "Kétféle életút"
    assert hymn_1.first_line == "Aki nem jár hitlenek tanácsán,"
    assert hymn_1.stanza_count == 4

    assert hymn_119 is not None
    assert hymn_119.title == "Az Úr Igéjének és törvényének dicsősége"
    assert hymn_119.stanza_count == 88

    assert hymn_254a is not None
    assert hymn_254a.canonical_key == "254a"
    assert hymn_254a.section_title == "Reformáció"
    assert hymn_254a.first_line == "Erős vár a mi Istenünk,"

    assert hymn_254b is not None
    assert hymn_254b.canonical_key == "254b"
    assert hymn_254b.first_line == "Erős várunk nékünk az Isten,"

    assert hymn_504 is not None
    assert hymn_504.canonical_key == "504"
    assert hymn_504.section_title == "Kánonok"
    assert hymn_504.first_line == "Áldjon meg téged, áldjon az Úr,"


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_section_parent_child_relationship_uses_foreign_key(tmp_path: Path) -> None:
    database = _build_ere(tmp_path)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT child.title AS child_title, parent.title AS parent_title
            FROM sections child
            JOIN sections parent ON parent.id = child.parent_id
            WHERE child.title = ? AND child.ordinal = 33
            """,
            ("Karácsony",),
        ).fetchone()

    assert row is not None
    assert row["child_title"] == "Karácsony"
    assert row["parent_title"] == "Énekek bibliaórákra, vasárnapi iskolai és családi alkalmakra"


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_fts_first_line_and_stanza_text_search(tmp_path: Path) -> None:
    database = _build_ere(tmp_path)

    first_line_hits = search_fts(database, "Erős vár a mi Istenünk", hymnal_code="ERE")
    stanza_hits = search_fts(database, "gyönyörködik az Úr törvényében", hymnal_code="ERE")

    assert first_line_hits
    assert first_line_hits[0].canonical_key == "254a"
    assert first_line_hits[0].first_line == "Erős vár a mi Istenünk,"

    assert stanza_hits
    assert stanza_hits[0].canonical_key == "1"


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_technical_hashes_are_not_indexed_in_fts(tmp_path: Path) -> None:
    database = _build_ere(tmp_path)

    assert search_fts(database, "E46D75E8", hymnal_code="ERE") == []


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_rebuild_is_idempotent_without_duplication(tmp_path: Path) -> None:
    database = tmp_path / "hymns.sqlite3"
    first = import_dtx_hymnal_database(ERE_SOURCE, database, hymnal_code="ERE")
    second = import_dtx_hymnal_database(ERE_SOURCE, database, hymnal_code="ERE")

    assert first.hymn_count == second.hymn_count == 513
    assert first.section_count == second.section_count == 44
    assert first.stanza_count == second.stanza_count == 2697

    with sqlite3.connect(database) as connection:
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("hymnals", "sections", "hymns", "stanzas")
        }

    assert counts == {"hymnals": 1, "sections": 44, "hymns": 513, "stanzas": 2697}


def _build_ere(tmp_path: Path) -> Path:
    database = tmp_path / "hymns.sqlite3"
    report = import_dtx_hymnal_database(ERE_SOURCE, database, hymnal_code="ERE")
    assert report.hymn_count == 513
    assert report.section_count == 44
    assert report.stanza_count == 2697
    return database


def _sqlite_names(connection: sqlite3.Connection, type_name: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (type_name,),
    ).fetchall()
    return {row[0] for row in rows}
