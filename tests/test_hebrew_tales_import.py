from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from illustration_engine.hebrew_tales_importer import import_hebrew_tales_book
from illustration_engine.illustration_sqlite import create_schema, insert_story
from illustration_engine.paths import RAW_DATA_DIR


HEBREW_TALES_SOURCE = RAW_DATA_DIR / "wikisource_hebrew_tales_hurwitz_kohut1917.txt"
HEBREW_TALES_SOURCE_CODE = "HEBREW_TALES_HURWITZ_KOHUT1917"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Hebrew Tales source not present locally: {path}")
    return path


def _fresh_connection(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "illustrations.sqlite3")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def test_import_inserts_all_parsed_stories_as_draft(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_hebrew_tales_book(conn, raw_text_path=_require(HEBREW_TALES_SOURCE))
    conn.commit()

    assert report.source_code == HEBREW_TALES_SOURCE_CODE
    assert report.parsed_count == 65
    assert report.inserted_count == 65
    assert report.skipped_existing_count == 0

    rows = conn.execute(
        "SELECT status, title_hu, modern_hu_text, summary_hu FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 65
    assert all(row == ("draft", None, None, None) for row in rows)


def test_import_is_idempotent_no_duplicates_on_rerun(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(HEBREW_TALES_SOURCE)

    first = import_hebrew_tales_book(conn, raw_text_path=source_path)
    conn.commit()
    second = import_hebrew_tales_book(conn, raw_text_path=source_path)
    conn.commit()

    assert first.inserted_count == 65
    assert second.inserted_count == 0
    assert second.skipped_existing_count == 65
    assert first.source_id == second.source_id

    count = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE source_id = ?", (first.source_id,)
    ).fetchone()[0]
    source_count = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE code = ?", (HEBREW_TALES_SOURCE_CODE,)
    ).fetchone()[0]
    conn.close()
    assert count == 65
    assert source_count == 1


def test_import_records_original_text_checksum(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_hebrew_tales_book(conn, raw_text_path=_require(HEBREW_TALES_SOURCE))
    conn.commit()

    rows = conn.execute(
        "SELECT original_text, original_text_checksum FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 65
    for original_text, checksum in rows:
        assert checksum == hashlib.sha256(original_text.encode("utf-8")).hexdigest()


def test_import_records_raw_file_checksum_in_import_meta(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(HEBREW_TALES_SOURCE)
    report = import_hebrew_tales_book(conn, raw_text_path=source_path)
    conn.commit()

    expected_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stored = conn.execute(
        "SELECT value FROM import_meta WHERE key = ?",
        (f"{HEBREW_TALES_SOURCE_CODE}.raw_file_sha256",),
    ).fetchone()[0]
    conn.close()
    assert report.raw_file_sha256 == expected_sha256
    assert stored == expected_sha256


def test_source_registry_entry_is_publishable_license(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_hebrew_tales_book(conn, raw_text_path=_require(HEBREW_TALES_SOURCE))
    conn.commit()

    row = conn.execute(
        "SELECT license_status, orig_language FROM sources WHERE id = ?", (report.source_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "public_domain_confirmed"
    assert row[1] == "en"


def test_published_without_hungarian_layer_still_rejected(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_hebrew_tales_book(conn, raw_text_path=_require(HEBREW_TALES_SOURCE))
    conn.commit()

    with pytest.raises(ValueError, match="content-completeness gate"):
        insert_story(
            conn,
            source_id=report.source_id,
            external_ref="TALE/999",
            canonical_key="999",
            title_original="Some Other Tale",
            adaptation_status="verbatim_transcription",
            status="published",
        )
    conn.close()


def test_published_stories_view_stays_empty_for_freshly_imported_stories(
    tmp_path: Path,
) -> None:
    conn = _fresh_connection(tmp_path)
    import_hebrew_tales_book(conn, raw_text_path=_require(HEBREW_TALES_SOURCE))
    conn.commit()

    rows = conn.execute("SELECT COUNT(*) FROM published_stories").fetchone()[0]
    conn.close()
    assert rows == 0


def test_hebrew_tales_and_other_sources_coexist_without_key_collisions(tmp_path: Path) -> None:
    from illustration_engine.baldwin_importer import import_baldwin_book
    from illustration_engine.gulistan_importer import import_gulistan_book

    baldwin_source = RAW_DATA_DIR / "pg18442_baldwin_fifty_famous_stories_retold.txt"
    gulistan_source = RAW_DATA_DIR / "pg13060_persian_literature_vol2_gulistan.txt"
    if not baldwin_source.exists() or not gulistan_source.exists():
        pytest.skip("Not all sibling raw sources present locally")

    conn = _fresh_connection(tmp_path)
    hebrew_tales = import_hebrew_tales_book(conn, raw_text_path=_require(HEBREW_TALES_SOURCE))
    baldwin = import_baldwin_book(conn, raw_text_path=baldwin_source)
    gulistan = import_gulistan_book(conn, raw_text_path=gulistan_source)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    conn.close()
    assert len({hebrew_tales.source_id, baldwin.source_id, gulistan.source_id}) == 3
    assert total == 65 + 50 + 147
