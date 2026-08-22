from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bible_engine.hymn_sqlite import (
    HymnalSourceConfig,
    create_schema,
    get_hymn_by_number,
    get_hymnal_summary,
    import_dtx_hymnal_database,
    import_hymnals_database,
    search_fts,
)


ROOT = Path(__file__).resolve().parents[1]
ERE_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"
RE21_SOURCE = ROOT / "data" / "raw" / "hymnals" / "RE21_master.docx"
RE48_SOURCE = ROOT / "data" / "raw" / "hymnals" / "REF48_reformatus.dtx"


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


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_combined_ere_re21_import_counts_and_summaries(tmp_path: Path) -> None:
    database = _build_ere_re21(tmp_path)

    ere = get_hymnal_summary(database, hymnal_code="ERE")
    re21 = get_hymnal_summary(database, hymnal_code="RE21")

    assert ere is not None
    assert ere.hymn_count == 513
    assert ere.base_number_count == 504
    assert ere.section_count == 44
    assert ere.stanza_count == 2697
    assert ere.parser_warning_count == 0

    assert re21 is not None
    assert re21.code == "RE21"
    assert re21.title == "Református Énekeskönyv 2021"
    assert re21.source_format == "docx"
    assert re21.source_checksum == "c5075014a35aa843707c4a196409f46bfcf86ab950928724d5e36a43cecdbb51"
    assert re21.hymn_count == 667
    assert re21.base_number_count == 667
    assert re21.section_count == 39
    assert re21.stanza_count == 3783
    assert re21.parser_warning_count == 0


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_combined_import_keeps_canonical_keys_unique_per_hymnal(tmp_path: Path) -> None:
    database = _build_ere_re21(tmp_path)

    with sqlite3.connect(database) as connection:
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
        shared_number_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM hymns ere
            JOIN hymnals ere_hy ON ere_hy.id = ere.hymnal_id
            JOIN hymns re21 ON re21.number = ere.number
            JOIN hymnals re21_hy ON re21_hy.id = re21.hymnal_id
            WHERE ere_hy.code = 'ERE' AND re21_hy.code = 'RE21'
            """
        ).fetchone()[0]

    assert duplicate_count == 0
    assert shared_number_count > 0


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_re21_representative_lookups(tmp_path: Path) -> None:
    database = _build_ere_re21(tmp_path)

    hymn_1 = get_hymn_by_number(database, "RE21", 1)
    hymn_167 = get_hymn_by_number(database, "RE21", 167)
    hymn_360 = get_hymn_by_number(database, "RE21", 360)
    hymn_487 = get_hymn_by_number(database, "RE21", 487)
    hymn_626 = get_hymn_by_number(database, "RE21", 626)
    hymn_846 = get_hymn_by_number(database, "RE21", 846)

    assert hymn_1 is not None
    assert hymn_1.canonical_key == "1"
    assert hymn_1.first_line.startswith("Aki nem jár hitlenek tanácsán")
    assert hymn_1.section_title == "Genfi zsoltárok"

    assert hymn_167 is not None
    assert hymn_167.first_line.startswith("Siess, nagy Úr Isten")
    assert hymn_167.section_title == "Zsoltárdicséretek"

    assert hymn_360 is not None
    assert hymn_360.first_line == "Jer, lássuk az Úr keresztjét,"
    assert hymn_360.section_title == "Úrvacsora"

    assert hymn_487 is not None
    assert hymn_487.first_line == "Ha a keresztre néz szemem,"
    assert hymn_487.section_title == "Nagyhét – Jézus Krisztus kínszenvedése és halála"

    assert hymn_626 is not None
    assert hymn_626.first_line.startswith("Fenn a mennyben az Úr minden győztesnek ád")
    assert hymn_626.section_title == "Keresztyén reménység – Jézus Krisztus visszajövetele"

    assert hymn_846 is not None
    assert hymn_846.first_line.startswith("Áldjon meg téged, áldjon az Úr")
    assert hymn_846.section_title == "Áldás"


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_combined_import_preserves_ere_lookups(tmp_path: Path) -> None:
    database = _build_ere_re21(tmp_path)

    hymn_1 = get_hymn_by_number(database, "ERE", 1)
    hymn_254a = get_hymn_by_number(database, "ERE", 254, "a")
    hymn_504 = get_hymn_by_number(database, "ERE", 504)

    assert hymn_1 is not None
    assert hymn_1.first_line == "Aki nem jár hitlenek tanácsán,"
    assert hymn_254a is not None
    assert hymn_254a.first_line == "Erős vár a mi Istenünk,"
    assert hymn_504 is not None
    assert hymn_504.first_line == "Áldjon meg téged, áldjon az Úr,"


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_re21_fts_search_is_hymnal_filtered(tmp_path: Path) -> None:
    database = _build_ere_re21(tmp_path)

    passion_hits = search_fts(database, "kereszt", hymnal_code="RE21")
    communion_hits = search_fts(database, "úrvacsora", hymnal_code="RE21")
    providence_hits = search_fts(database, "bizalom", hymnal_code="RE21")
    penitence_hits = search_fts(database, "bűnbánat", hymnal_code="RE21")
    ere_only_hits = search_fts(database, "úrvacsora", hymnal_code="ERE")

    assert passion_hits
    assert all(hit.hymnal_code == "RE21" for hit in passion_hits)
    assert communion_hits
    assert all(hit.hymnal_code == "RE21" for hit in communion_hits)
    assert providence_hits
    assert all(hit.hymnal_code == "RE21" for hit in providence_hits)
    assert penitence_hits
    assert all(hit.hymnal_code == "RE21" for hit in penitence_hits)
    assert all(hit.hymnal_code == "ERE" for hit in ere_only_hits)


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_re21_section_parent_child_relationship_uses_foreign_key(tmp_path: Path) -> None:
    database = _build_ere_re21(tmp_path)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT child.title AS child_title, parent.title AS parent_title
            FROM sections child
            JOIN sections parent ON parent.id = child.parent_id
            JOIN hymnals hy ON hy.id = child.hymnal_id
            WHERE hy.code = ? AND child.title = ?
            """,
            ("RE21", "Genfi zsoltárok"),
        ).fetchone()

    assert row is not None
    assert row["child_title"] == "Genfi zsoltárok"
    assert row["parent_title"] == "ZSOLTÁROK"


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_combined_rebuild_is_idempotent_without_duplication(tmp_path: Path) -> None:
    database = tmp_path / "hymns.sqlite3"
    first = _import_ere_re21(database)
    second = _import_ere_re21(database)

    assert [report.hymn_count for report in first] == [513, 667]
    assert [report.hymn_count for report in second] == [513, 667]

    with sqlite3.connect(database) as connection:
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("hymnals", "sections", "hymns", "stanzas")
        }

    assert counts == {"hymnals": 2, "sections": 83, "hymns": 1180, "stanzas": 6480}


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists() and RE48_SOURCE.exists()),
    reason="Full ERE.dtx, RÉ21 DOCX, and RÉ48 DTX are local raw data",
)
def test_triple_ere_re21_re48_import_counts_and_summaries(tmp_path: Path) -> None:
    database = _build_ere_re21_re48(tmp_path)

    ere = get_hymnal_summary(database, hymnal_code="ERE")
    re21 = get_hymnal_summary(database, hymnal_code="RE21")
    re48 = get_hymnal_summary(database, hymnal_code="RE48")

    assert ere is not None
    assert (ere.hymn_count, ere.base_number_count, ere.section_count, ere.stanza_count) == (
        513,
        504,
        44,
        2697,
    )
    assert re21 is not None
    assert (re21.hymn_count, re21.base_number_count, re21.section_count, re21.stanza_count) == (
        667,
        667,
        39,
        3783,
    )
    assert re48 is not None
    assert re48.code == "RE48"
    assert re48.title == "Református Énekeskönyv (1948)"
    assert re48.source_format == "DiaTar DTX"
    assert re48.source_checksum == "3f6ebf59731263db17b7366ac4bde1f4a8515db01d5859f6c8fbbfbfb725d677"
    assert (re48.hymn_count, re48.base_number_count, re48.section_count, re48.stanza_count) == (
        512,
        512,
        0,
        3259,
    )
    assert re48.parser_warning_count == 0

    with sqlite3.connect(database) as connection:
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("sections", "hymns", "stanzas")
        }
    assert counts == {"sections": 83, "hymns": 1692, "stanzas": 9739}


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists() and RE48_SOURCE.exists()),
    reason="Full ERE.dtx, RÉ21 DOCX, and RÉ48 DTX are local raw data",
)
def test_re48_data_quality_in_combined_import(tmp_path: Path) -> None:
    database = _build_ere_re21_re48(tmp_path)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
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
        re48_variant_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM hymns h
            JOIN hymnals hy ON hy.id = h.hymnal_id
            WHERE hy.code = 'RE48' AND COALESCE(h.variant, '') <> ''
            """
        ).fetchone()[0]
        re48_without_stanzas = connection.execute(
            """
            SELECT COUNT(*)
            FROM hymns h
            JOIN hymnals hy ON hy.id = h.hymnal_id
            LEFT JOIN stanzas st ON st.hymn_id = h.id
            WHERE hy.code = 'RE48'
            GROUP BY h.id
            HAVING COUNT(st.id) = 0
            """
        ).fetchall()
        empty_stanza_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM stanzas st
            JOIN hymns h ON h.id = st.hymn_id
            JOIN hymnals hy ON hy.id = h.hymnal_id
            WHERE hy.code = 'RE48' AND TRIM(st.text) = ''
            """
        ).fetchone()[0]
        first_line_mismatch = connection.execute(
            """
            SELECT COUNT(*)
            FROM hymns h
            JOIN hymnals hy ON hy.id = h.hymnal_id
            JOIN stanzas st ON st.hymn_id = h.id
            WHERE hy.code = 'RE48'
              AND st.id = (SELECT MIN(st2.id) FROM stanzas st2 WHERE st2.hymn_id = h.id)
              AND h.first_line <> st.first_line
            """
        ).fetchone()[0]
        shared_number_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM hymns ere
            JOIN hymnals ere_hy ON ere_hy.id = ere.hymnal_id
            JOIN hymns re48 ON re48.number = ere.number
            JOIN hymnals re48_hy ON re48_hy.id = re48.hymnal_id
            WHERE ere_hy.code = 'ERE' AND re48_hy.code = 'RE48'
            """
        ).fetchone()[0]

    assert duplicate_count == 0
    assert re48_variant_count == 0
    assert re48_without_stanzas == []
    assert empty_stanza_count == 0
    assert first_line_mismatch == 0
    assert shared_number_count > 0


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists() and RE48_SOURCE.exists()),
    reason="Full ERE.dtx, RÉ21 DOCX, and RÉ48 DTX are local raw data",
)
def test_re48_representative_lookups_use_first_line_as_display_source(tmp_path: Path) -> None:
    database = _build_ere_re21_re48(tmp_path)

    expected = {
        1: "Aki nem jár hitlenek tanácsán,",
        23: "Az Úr énnékem őriző pásztorom,",
        42: "Mint a szép, híves patakra",
        90: "Tebenned bíztunk eleitől fogva,",
        150: "Dicsérjétek az Urat!",
        220: "Bocsásd meg, Úr Isten, ifjúságomnak vétkét,",
        341: "Ó, Krisztusfő, te zúzott,",
        397: "Ó, Sion, ébredj, töltsd be küldetésed,",
        431: "Úr Isten, kérünk tégedet:",
        512: "„Szólj, szólj hozzám, Uram, mert szolgád hallja szódat!”",
    }

    for number, first_line in expected.items():
        hymn = get_hymn_by_number(database, "RE48", number)
        assert hymn is not None
        assert hymn.canonical_key == str(number)
        assert hymn.first_line == first_line
        assert hymn.section_title == ""


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists() and RE48_SOURCE.exists()),
    reason="Full ERE.dtx, RÉ21 DOCX, and RÉ48 DTX are local raw data",
)
def test_re48_fts_search_is_hymnal_filtered_without_section_data(tmp_path: Path) -> None:
    database = _build_ere_re21_re48(tmp_path)

    pastor_hits = search_fts(database, "pásztor", hymnal_code="RE48")
    penitence_hits = search_fts(database, "bűn", hymnal_code="RE48")
    cross_hits = search_fts(database, "kereszt", hymnal_code="RE48")
    communion_hits = search_fts(database, "vacsora", hymnal_code="RE48")
    hope_hits = search_fts(database, "reménység", hymnal_code="RE48")

    for hits in (pastor_hits, penitence_hits, cross_hits, communion_hits, hope_hits):
        assert hits
        assert all(hit.hymnal_code == "RE48" for hit in hits)
        assert all(hit.section_title == "" for hit in hits)

    assert pastor_hits[0].canonical_key == "23"
    assert cross_hits[0].canonical_key in {"230", "338", "341", "344", "345", "496"}


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists() and RE48_SOURCE.exists()),
    reason="Full ERE.dtx, RÉ21 DOCX, and RÉ48 DTX are local raw data",
)
def test_triple_import_preserves_ere_and_re21_lookups(tmp_path: Path) -> None:
    database = _build_ere_re21_re48(tmp_path)

    ere = get_hymn_by_number(database, "ERE", 254, "a")
    re21 = get_hymn_by_number(database, "RE21", 360)

    assert ere is not None
    assert ere.first_line == "Erős vár a mi Istenünk,"
    assert ere.section_title == "Reformáció"
    assert re21 is not None
    assert re21.first_line == "Jer, lássuk az Úr keresztjét,"
    assert re21.section_title == "Úrvacsora"


def _build_ere(tmp_path: Path) -> Path:
    database = tmp_path / "hymns.sqlite3"
    report = import_dtx_hymnal_database(ERE_SOURCE, database, hymnal_code="ERE")
    assert report.hymn_count == 513
    assert report.section_count == 44
    assert report.stanza_count == 2697
    return database


def _build_ere_re21(tmp_path: Path) -> Path:
    database = tmp_path / "hymns.sqlite3"
    reports = _import_ere_re21(database)
    assert [report.hymn_count for report in reports] == [513, 667]
    assert [report.section_count for report in reports] == [44, 39]
    assert [report.stanza_count for report in reports] == [2697, 3783]
    return database


def _import_ere_re21(database: Path):
    return import_hymnals_database(
        (
            HymnalSourceConfig(code="ERE", source_path=ERE_SOURCE, source_format="dtx"),
            HymnalSourceConfig(
                code="RE21",
                source_path=RE21_SOURCE,
                source_format="docx",
                title="Református Énekeskönyv 2021",
            ),
        ),
        database,
    )


def _build_ere_re21_re48(tmp_path: Path) -> Path:
    database = tmp_path / "hymns.sqlite3"
    reports = _import_ere_re21_re48(database)
    assert [report.hymn_count for report in reports] == [513, 667, 512]
    assert [report.section_count for report in reports] == [44, 39, 0]
    assert [report.stanza_count for report in reports] == [2697, 3783, 3259]
    return database


def _import_ere_re21_re48(database: Path):
    return import_hymnals_database(
        (
            HymnalSourceConfig(code="ERE", source_path=ERE_SOURCE, source_format="dtx"),
            HymnalSourceConfig(
                code="RE21",
                source_path=RE21_SOURCE,
                source_format="docx",
                title="Református Énekeskönyv 2021",
            ),
            HymnalSourceConfig(
                code="RE48",
                source_path=RE48_SOURCE,
                source_format="dtx",
                title="Református Énekeskönyv (1948)",
            ),
        ),
        database,
    )


def _sqlite_names(connection: sqlite3.Connection, type_name: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (type_name,),
    ).fetchall()
    return {row[0] for row in rows}
