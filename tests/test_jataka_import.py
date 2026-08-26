from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from illustration_engine.illustration_sqlite import create_schema, insert_story
from illustration_engine.jataka_importer import import_jataka_book
from illustration_engine.jataka_parser import JATAKA_TALES_1912, MORE_JATAKA_TALES_1922
from illustration_engine.paths import RAW_DATA_DIR


JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg62514_jataka_tales.txt"
MORE_JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg7518_more_jataka_tales.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Jataka source not present locally: {path}")
    return path


def _fresh_connection(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "illustrations.sqlite3")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def test_import_inserts_all_parsed_stories_as_draft(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_jataka_book(
        conn, spec=JATAKA_TALES_1912, raw_text_path=_require(JATAKA_TALES_SOURCE)
    )
    conn.commit()

    assert report.parsed_count == 18
    assert report.inserted_count == 18
    assert report.skipped_existing_count == 0

    rows = conn.execute(
        "SELECT status, title_hu, modern_hu_text, summary_hu FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 18
    assert all(row == ("draft", None, None, None) for row in rows)


def test_import_is_idempotent_no_duplicates_on_rerun(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(JATAKA_TALES_SOURCE)

    first = import_jataka_book(conn, spec=JATAKA_TALES_1912, raw_text_path=source_path)
    conn.commit()
    second = import_jataka_book(conn, spec=JATAKA_TALES_1912, raw_text_path=source_path)
    conn.commit()

    assert first.inserted_count == 18
    assert second.inserted_count == 0
    assert second.skipped_existing_count == 18

    count = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE source_id = ?", (first.source_id,)
    ).fetchone()[0]
    conn.close()
    assert count == 18


def test_import_reuses_existing_source_row_across_runs(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(JATAKA_TALES_SOURCE)

    first = import_jataka_book(conn, spec=JATAKA_TALES_1912, raw_text_path=source_path)
    conn.commit()
    second = import_jataka_book(conn, spec=JATAKA_TALES_1912, raw_text_path=source_path)
    conn.commit()

    source_count = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE code = ?", (JATAKA_TALES_1912.source_code,)
    ).fetchone()[0]
    conn.close()
    assert first.source_id == second.source_id
    assert source_count == 1


def test_import_records_original_text_checksum(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    report = import_jataka_book(
        conn, spec=JATAKA_TALES_1912, raw_text_path=_require(JATAKA_TALES_SOURCE)
    )
    conn.commit()

    rows = conn.execute(
        "SELECT original_text, original_text_checksum FROM stories WHERE source_id = ?",
        (report.source_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 18
    for original_text, checksum in rows:
        assert checksum == hashlib.sha256(original_text.encode("utf-8")).hexdigest()


def test_import_records_raw_file_checksum_in_import_meta(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    source_path = _require(JATAKA_TALES_SOURCE)
    report = import_jataka_book(conn, spec=JATAKA_TALES_1912, raw_text_path=source_path)
    conn.commit()

    expected_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stored = conn.execute(
        "SELECT value FROM import_meta WHERE key = ?",
        (f"{JATAKA_TALES_1912.source_code}.raw_file_sha256",),
    ).fetchone()[0]
    conn.close()
    assert report.raw_file_sha256 == expected_sha256
    assert stored == expected_sha256


def test_import_both_books_coexist_without_key_collisions(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    r1 = import_jataka_book(
        conn, spec=JATAKA_TALES_1912, raw_text_path=_require(JATAKA_TALES_SOURCE)
    )
    r2 = import_jataka_book(
        conn, spec=MORE_JATAKA_TALES_1922, raw_text_path=_require(MORE_JATAKA_TALES_SOURCE)
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    conn.close()
    assert r1.source_id != r2.source_id
    assert total == 18 + 21


def test_imported_jataka_source_is_publishable_by_license_but_blocked_by_completeness_gate(
    tmp_path: Path,
) -> None:
    """The Jataka sources are public_domain_confirmed (license gate would
    allow 'published'), but every imported story still lacks the Hungarian
    layer — so the content-completeness gate must block publishing until
    a later AI-enrichment phase fills it in."""
    conn = _fresh_connection(tmp_path)
    report = import_jataka_book(
        conn, spec=JATAKA_TALES_1912, raw_text_path=_require(JATAKA_TALES_SOURCE)
    )
    conn.commit()

    with pytest.raises(ValueError, match="content-completeness gate"):
        insert_story(
            conn,
            source_id=report.source_id,
            external_ref="I",
            canonical_key="99",
            title_original="Some Other Story",
            adaptation_status="verbatim_transcription",
            status="published",
        )
    conn.close()


def test_direct_sql_publish_bypass_still_blocked_for_imported_jataka_stories(
    tmp_path: Path,
) -> None:
    """Defense-in-depth: flipping an already-imported Jataka story straight
    to 'published' via raw SQL (skipping insert_story entirely) must still
    be rejected by the content-completeness CHECK constraint, even though
    the source's license IS publishable."""
    conn = _fresh_connection(tmp_path)
    report = import_jataka_book(
        conn, spec=JATAKA_TALES_1912, raw_text_path=_require(JATAKA_TALES_SOURCE)
    )
    conn.commit()

    story_id = conn.execute(
        "SELECT id FROM stories WHERE source_id = ? AND canonical_key = '01'",
        (report.source_id,),
    ).fetchone()[0]

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE stories SET status = 'published' WHERE id = ?", (story_id,))
    conn.close()


def test_published_stories_view_stays_empty_for_freshly_imported_jataka(tmp_path: Path) -> None:
    conn = _fresh_connection(tmp_path)
    import_jataka_book(
        conn, spec=JATAKA_TALES_1912, raw_text_path=_require(JATAKA_TALES_SOURCE)
    )
    conn.commit()

    rows = conn.execute("SELECT COUNT(*) FROM published_stories").fetchone()[0]
    conn.close()
    assert rows == 0
