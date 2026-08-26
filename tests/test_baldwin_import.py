from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from illustration_engine.baldwin_importer import import_baldwin_book
from illustration_engine.illustration_sqlite import create_schema, insert_story
from illustration_engine.paths import RAW_DATA_DIR


BALDWIN_SOURCE = RAW_DATA_DIR / "pg18442_baldwin_fifty_famous_stories_retold.txt"
BALDWIN_SOURCE_CODE = "PG_BALDWIN_FIFTY_FAMOUS_STORIES_RETOLD"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Baldwin source not present locally: {path}")
    return path


def _fresh_connection(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "illustrations.sqlite3")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def test_import_inserts_all_parsed_stories_as_draft(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_baldwin_book(conn, raw_text_path=_require(BALDWIN_SOURCE))
    conn.commit()

    assert report.source_code == BALDWIN_SOURCE_CODE
    assert report.parsed_count == 50
    assert report.inserted_count == 50
    assert report.skipped_existing_count == 0

    rows = conn.execute(
        "SELECT status, title_hu, modern_hu_text, summary_hu FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 50
    assert all(row == ("draft", None, None, None) for row in rows)


def test_import_is_idempotent_no_duplicates_on_rerun(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(BALDWIN_SOURCE)

    first = import_baldwin_book(conn, raw_text_path=source_path)
    conn.commit()
    second = import_baldwin_book(conn, raw_text_path=source_path)
    conn.commit()

    assert first.inserted_count == 50
    assert second.inserted_count == 0
    assert second.skipped_existing_count == 50
    assert first.source_id == second.source_id

    count = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE source_id = ?", (first.source_id,)
    ).fetchone()[0]
    source_count = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE code = ?", (BALDWIN_SOURCE_CODE,)
    ).fetchone()[0]
    conn.close()
    assert count == 50
    assert source_count == 1


def test_import_records_original_text_checksum(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_baldwin_book(conn, raw_text_path=_require(BALDWIN_SOURCE))
    conn.commit()

    rows = conn.execute(
        "SELECT original_text, original_text_checksum FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 50
    for original_text, checksum in rows:
        assert checksum == hashlib.sha256(original_text.encode("utf-8")).hexdigest()


def test_import_records_raw_file_checksum_in_import_meta(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(BALDWIN_SOURCE)
    report = import_baldwin_book(conn, raw_text_path=source_path)
    conn.commit()

    expected_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stored = conn.execute(
        "SELECT value FROM import_meta WHERE key = ?",
        (f"{BALDWIN_SOURCE_CODE}.raw_file_sha256",),
    ).fetchone()[0]
    conn.close()
    assert report.raw_file_sha256 == expected_sha256
    assert stored == expected_sha256


def test_source_registry_entry_is_publishable_license(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_baldwin_book(conn, raw_text_path=_require(BALDWIN_SOURCE))
    conn.commit()

    row = conn.execute(
        "SELECT license_status, orig_language FROM sources WHERE id = ?", (report.source_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "public_domain_confirmed"
    assert row[1] == "en"


def test_published_without_hungarian_layer_still_rejected(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_baldwin_book(conn, raw_text_path=_require(BALDWIN_SOURCE))
    conn.commit()

    with pytest.raises(ValueError, match="content-completeness gate"):
        insert_story(
            conn,
            source_id=report.source_id,
            external_ref="99",
            canonical_key="99",
            title_original="Some Other Story",
            adaptation_status="verbatim_transcription",
            status="published",
        )
    conn.close()


def test_published_stories_view_stays_empty_for_freshly_imported_baldwin(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    import_baldwin_book(conn, raw_text_path=_require(BALDWIN_SOURCE))
    conn.commit()

    rows = conn.execute("SELECT COUNT(*) FROM published_stories").fetchone()[0]
    conn.close()
    assert rows == 0


def test_baldwin_jataka_aesop_arany_merenyi_coexist_without_key_collisions(
    tmp_path: Path,
) -> None:
    from illustration_engine.aesop_importer import import_aesop_book
    from illustration_engine.arany_laszlo_importer import import_arany_laszlo_book
    from illustration_engine.jataka_importer import import_jataka_book
    from illustration_engine.jataka_parser import JATAKA_TALES_1912
    from illustration_engine.merenyi_laszlo_importer import import_merenyi_laszlo_book
    from illustration_engine.merenyi_laszlo_parser import MERENYI_1_RESZ

    other_sources = {
        "jataka": RAW_DATA_DIR / "pg62514_jataka_tales.txt",
        "aesop": RAW_DATA_DIR / "pg21_aesops_fables.txt",
        "arany": RAW_DATA_DIR / "pg38852_arany_laszlo_eredeti_nepmesek.txt",
        "merenyi": RAW_DATA_DIR / "pg39419_merenyi_laszlo_eredeti_nepmesek_1resz.txt",
    }
    if not all(p.exists() for p in other_sources.values()):
        pytest.skip("Not all sibling raw sources present locally")

    conn = _fresh_connection(tmp_path)
    baldwin = import_baldwin_book(conn, raw_text_path=_require(BALDWIN_SOURCE))
    jataka = import_jataka_book(
        conn, spec=JATAKA_TALES_1912, raw_text_path=other_sources["jataka"]
    )
    aesop = import_aesop_book(conn, raw_text_path=other_sources["aesop"])
    arany = import_arany_laszlo_book(conn, raw_text_path=other_sources["arany"])
    merenyi = import_merenyi_laszlo_book(
        conn, spec=MERENYI_1_RESZ, raw_text_path=other_sources["merenyi"]
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    conn.close()
    ids = {baldwin.source_id, jataka.source_id, aesop.source_id, arany.source_id, merenyi.source_id}
    assert len(ids) == 5
    assert total == 50 + 18 + 313 + 31 + 10
