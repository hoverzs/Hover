"""Commentary corpus QA report tests (small trimmed real Calvin fixtures)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from textus_kb.importers.calvin_commentary_thml import import_calvin_commentary_sqlite
from textus_kb.qa.commentary_corpus_qa import (
    format_qa_report_human,
    generate_commentary_corpus_qa,
)

ROMANS_FIXTURE = Path("tests/fixtures/kb/calvin_calcom38_romans_ch1_min.xml")
HARMONY_FIXTURE = Path("tests/fixtures/kb/calvin_calcom31_harmony_min.xml")


def test_qa_report_missing_database_is_unavailable(tmp_path: Path) -> None:
    report = generate_commentary_corpus_qa(tmp_path / "missing.sqlite3")
    assert report.available is False
    assert "not available" in format_qa_report_human(report)


def test_qa_report_on_clean_calvin_import(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=database)
    report = generate_commentary_corpus_qa(database)

    assert report.available is True
    assert len(report.works) == 2
    assert len(report.source_files) == 2
    assert report.section_count > 0
    assert report.chunk_count > 0
    assert report.passage_link_count > 0
    assert report.exact_verse_link_count > 0
    assert report.range_link_count > 0
    assert any(s["passage_count"] > 1 for s in report.multi_passage_sections)

    # All invariants enforced at import/DB level should read back clean.
    assert report.orphan_sections == []
    assert report.invalid_references == []
    assert report.duplicate_section_ids == []
    assert report.duplicate_chunk_ids == []
    assert report.duplicate_passage_links == []
    assert report.cross_edition_hierarchy_issues == []
    assert report.warnings == []

    assert "Rom" in report.coverage_by_book_primary
    assert "Matt" in report.coverage_by_book_primary
    assert report.cross_reference_count_stored == 0
    assert report.primary_passage_link_count > 0


def test_qa_report_passageless_sections_are_categorized_not_flagged(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE], database_path=database)
    report = generate_commentary_corpus_qa(database)
    # The chapter-level structural section (div1) has no passage of its
    # own — that is expected, not an integrity problem.
    assert sum(report.passageless_sections_by_type.values()) > 0
    assert report.warnings == []


def test_qa_report_detects_orphan_section_when_fk_bypassed(tmp_path: Path) -> None:
    """Defensive check: if a store were ever built outside the normal importer
    (bypassing FK enforcement), the QA report must still catch it."""
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE], database_path=database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "UPDATE sections SET parent_section_id = 'does.not.exist' "
            "WHERE section_id = 'ccel.calvin.calcom38.v.i'"
        )
        connection.commit()
    report = generate_commentary_corpus_qa(database)
    assert len(report.orphan_sections) == 1
    assert report.orphan_sections[0]["section_id"] == "ccel.calvin.calcom38.v.i"
    assert report.warnings


def test_human_readable_report_mentions_works_and_coverage(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=database)
    report = generate_commentary_corpus_qa(database)
    text = format_qa_report_human(report)
    assert "Commentary on Romans" in text
    assert "Sections:" in text
    assert "Coverage by book" in text
