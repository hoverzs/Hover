from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from illustration_engine.illustration_sqlite import create_schema, insert_story
from illustration_engine.merenyi_laszlo_importer import import_merenyi_laszlo_book
from illustration_engine.merenyi_laszlo_parser import MERENYI_1_RESZ, MERENYI_2_RESZ
from illustration_engine.paths import RAW_DATA_DIR


MERENYI_1_SOURCE = RAW_DATA_DIR / "pg39419_merenyi_laszlo_eredeti_nepmesek_1resz.txt"
MERENYI_2_SOURCE = RAW_DATA_DIR / "pg39386_merenyi_laszlo_eredeti_nepmesek_2resz.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Merényi László source not present locally: {path}")
    return path


def _fresh_connection(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "illustrations.sqlite3")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def test_import_inserts_all_parsed_tales_as_draft_for_both_volumes(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    r1 = import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=_require(MERENYI_1_SOURCE)
    )
    r2 = import_merenyi_laszlo_book(
        conn, spec=MERENYI_2_RESZ, raw_text_path=_require(MERENYI_2_SOURCE)
    )
    conn.commit()

    assert r1.parsed_count == r1.inserted_count == 10
    assert r2.parsed_count == r2.inserted_count == 13
    assert r1.skipped_existing_count == r2.skipped_existing_count == 0

    total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    non_draft = conn.execute("SELECT COUNT(*) FROM stories WHERE status != 'draft'").fetchone()[0]
    hungarian_layer = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE title_hu IS NOT NULL "
        "OR modern_hu_text IS NOT NULL OR summary_hu IS NOT NULL"
    ).fetchone()[0]
    conn.close()
    assert total == 23
    assert non_draft == 0
    assert hungarian_layer == 0


def test_import_is_idempotent_no_duplicates_on_rerun(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(MERENYI_2_SOURCE)

    first = import_merenyi_laszlo_book(conn, spec=MERENYI_2_RESZ, raw_text_path=source_path)
    conn.commit()
    second = import_merenyi_laszlo_book(conn, spec=MERENYI_2_RESZ, raw_text_path=source_path)
    conn.commit()

    assert first.inserted_count == 13
    assert second.inserted_count == 0
    assert second.skipped_existing_count == 13
    assert first.source_id == second.source_id

    count = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE source_id = ?", (first.source_id,)
    ).fetchone()[0]
    source_count = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE code = ?", (MERENYI_2_RESZ.source_code,)
    ).fetchone()[0]
    conn.close()
    assert count == 13
    assert source_count == 1


def test_import_records_original_text_checksum(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=_require(MERENYI_1_SOURCE)
    )
    conn.commit()

    rows = conn.execute(
        "SELECT original_text, original_text_checksum FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 10
    for original_text, checksum in rows:
        assert checksum == hashlib.sha256(original_text.encode("utf-8")).hexdigest()


def test_import_records_raw_file_checksum_in_import_meta(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(MERENYI_2_SOURCE)
    report = import_merenyi_laszlo_book(conn, spec=MERENYI_2_RESZ, raw_text_path=source_path)
    conn.commit()

    expected_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stored = conn.execute(
        "SELECT value FROM import_meta WHERE key = ?",
        (f"{MERENYI_2_RESZ.source_code}.raw_file_sha256",),
    ).fetchone()[0]
    conn.close()
    assert report.raw_file_sha256 == expected_sha256
    assert stored == expected_sha256


def test_both_merenyi_volumes_coexist_without_key_collisions(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    r1 = import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=_require(MERENYI_1_SOURCE)
    )
    r2 = import_merenyi_laszlo_book(
        conn, spec=MERENYI_2_RESZ, raw_text_path=_require(MERENYI_2_SOURCE)
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    conn.close()
    assert r1.source_id != r2.source_id
    assert total == 10 + 13


def test_source_registry_entries_are_publishable_license(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    r1 = import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=_require(MERENYI_1_SOURCE)
    )
    conn.commit()

    row = conn.execute(
        "SELECT license_status, orig_language FROM sources WHERE id = ?", (r1.source_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "public_domain_confirmed"
    assert row[1] == "hu"


def test_published_without_hungarian_layer_still_rejected(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=_require(MERENYI_1_SOURCE)
    )
    conn.commit()

    with pytest.raises(ValueError, match="content-completeness gate"):
        insert_story(
            conn,
            source_id=report.source_id,
            external_ref="99",
            canonical_key="99",
            title_original="Some Other Tale",
            adaptation_status="verbatim_transcription",
            status="published",
        )
    conn.close()


def test_published_stories_view_stays_empty_for_freshly_imported_merenyi(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=_require(MERENYI_1_SOURCE)
    )
    conn.commit()

    rows = conn.execute("SELECT COUNT(*) FROM published_stories").fetchone()[0]
    conn.close()
    assert rows == 0


def test_merenyi_arany_and_jataka_sources_coexist_without_key_collisions(tmp_path: Path) -> None:
    from illustration_engine.arany_laszlo_importer import import_arany_laszlo_book
    from illustration_engine.jataka_importer import import_jataka_book
    from illustration_engine.jataka_parser import JATAKA_TALES_1912

    arany_source = RAW_DATA_DIR / "pg38852_arany_laszlo_eredeti_nepmesek.txt"
    jataka_source = RAW_DATA_DIR / "pg62514_jataka_tales.txt"
    if not arany_source.exists() or not jataka_source.exists():
        pytest.skip("Raw Arany/Jataka sources not present locally")

    conn = _fresh_connection(tmp_path)
    merenyi1 = import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=_require(MERENYI_1_SOURCE)
    )
    merenyi2 = import_merenyi_laszlo_book(
        conn, spec=MERENYI_2_RESZ, raw_text_path=_require(MERENYI_2_SOURCE)
    )
    arany = import_arany_laszlo_book(conn, raw_text_path=arany_source)
    jataka = import_jataka_book(conn, spec=JATAKA_TALES_1912, raw_text_path=jataka_source)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    conn.close()
    ids = {merenyi1.source_id, merenyi2.source_id, arany.source_id, jataka.source_id}
    assert len(ids) == 4
    assert total == 10 + 13 + 31 + 18
