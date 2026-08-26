from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from illustration_engine.gulistan_importer import import_gulistan_book
from illustration_engine.illustration_sqlite import create_schema, insert_story
from illustration_engine.paths import RAW_DATA_DIR


GULISTAN_SOURCE = RAW_DATA_DIR / "pg13060_persian_literature_vol2_gulistan.txt"
GULISTAN_SOURCE_CODE = "PG_GULISTAN_SADI_ROSS"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Gulistan source not present locally: {path}")
    return path


def _fresh_connection(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "illustrations.sqlite3")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def test_import_inserts_all_parsed_stories_as_draft(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_gulistan_book(conn, raw_text_path=_require(GULISTAN_SOURCE))
    conn.commit()

    assert report.source_code == GULISTAN_SOURCE_CODE
    assert report.parsed_count == 147
    assert report.inserted_count == 147
    assert report.skipped_existing_count == 0

    rows = conn.execute(
        "SELECT status, title_hu, modern_hu_text, summary_hu FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 147
    assert all(row == ("draft", None, None, None) for row in rows)


def test_import_is_idempotent_no_duplicates_on_rerun(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(GULISTAN_SOURCE)

    first = import_gulistan_book(conn, raw_text_path=source_path)
    conn.commit()
    second = import_gulistan_book(conn, raw_text_path=source_path)
    conn.commit()

    assert first.inserted_count == 147
    assert second.inserted_count == 0
    assert second.skipped_existing_count == 147
    assert first.source_id == second.source_id

    count = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE source_id = ?", (first.source_id,)
    ).fetchone()[0]
    source_count = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE code = ?", (GULISTAN_SOURCE_CODE,)
    ).fetchone()[0]
    conn.close()
    assert count == 147
    assert source_count == 1


def test_import_records_original_text_checksum(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_gulistan_book(conn, raw_text_path=_require(GULISTAN_SOURCE))
    conn.commit()

    rows = conn.execute(
        "SELECT original_text, original_text_checksum FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 147
    for original_text, checksum in rows:
        assert checksum == hashlib.sha256(original_text.encode("utf-8")).hexdigest()


def test_import_records_raw_file_checksum_in_import_meta(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(GULISTAN_SOURCE)
    report = import_gulistan_book(conn, raw_text_path=source_path)
    conn.commit()

    expected_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stored = conn.execute(
        "SELECT value FROM import_meta WHERE key = ?",
        (f"{GULISTAN_SOURCE_CODE}.raw_file_sha256",),
    ).fetchone()[0]
    conn.close()
    assert report.raw_file_sha256 == expected_sha256
    assert stored == expected_sha256


def test_source_registry_entry_is_publishable_license(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_gulistan_book(conn, raw_text_path=_require(GULISTAN_SOURCE))
    conn.commit()

    row = conn.execute(
        "SELECT license_status, orig_language FROM sources WHERE id = ?", (report.source_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "public_domain_confirmed"
    assert row[1] == "en"


def test_published_without_hungarian_layer_still_rejected(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_gulistan_book(conn, raw_text_path=_require(GULISTAN_SOURCE))
    conn.commit()

    with pytest.raises(ValueError, match="content-completeness gate"):
        insert_story(
            conn,
            source_id=report.source_id,
            external_ref="VII/XCIX",
            canonical_key="999",
            title_original="Of the Impressions of Education",
            adaptation_status="verbatim_transcription",
            status="published",
        )
    conn.close()


def test_published_stories_view_stays_empty_for_freshly_imported_stories(
    tmp_path: Path,
) -> None:
    conn = _fresh_connection(tmp_path)
    import_gulistan_book(conn, raw_text_path=_require(GULISTAN_SOURCE))
    conn.commit()

    rows = conn.execute("SELECT COUNT(*) FROM published_stories").fetchone()[0]
    conn.close()
    assert rows == 0


def test_gulistan_and_other_sources_coexist_without_key_collisions(tmp_path: Path) -> None:
    from illustration_engine.baldwin_importer import import_baldwin_book
    from illustration_engine.book_of_300_anecdotes_importer import import_book_of_300_anecdotes

    baldwin_source = RAW_DATA_DIR / "pg18442_baldwin_fifty_famous_stories_retold.txt"
    anecdotes_source = RAW_DATA_DIR / "pg15413_book_of_300_anecdotes.txt"
    if not baldwin_source.exists() or not anecdotes_source.exists():
        pytest.skip("Not all sibling raw sources present locally")

    conn = _fresh_connection(tmp_path)
    gulistan = import_gulistan_book(conn, raw_text_path=_require(GULISTAN_SOURCE))
    baldwin = import_baldwin_book(conn, raw_text_path=baldwin_source)
    anecdotes = import_book_of_300_anecdotes(conn, raw_text_path=anecdotes_source)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    conn.close()
    assert len({gulistan.source_id, baldwin.source_id, anecdotes.source_id}) == 3
    assert total == 147 + 50 + 345
