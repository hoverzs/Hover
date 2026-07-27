from __future__ import annotations

import sqlite3
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bible_engine.tagnt_parser import GreekToken, parse_tagnt_row


_TAGNT_RECORD_RE = re.compile(r"^[1-3]?[A-Za-z]{3}\.\d+\.\d+(?:[\[\(\{][^#]+[\]\)\}])?#")
_TAGNT_BOOK_RE = re.compile(r"^(?P<book>[1-3]?[A-Za-z]{3})\.")


@dataclass(frozen=True)
class ImportReport:
    source_path: str
    database_path: str
    book: str
    rows_read: int
    rows_imported: int
    rows_skipped: int
    parse_errors: int
    duplicate_rows: int


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS greek_tokens (
            id INTEGER PRIMARY KEY,
            book TEXT NOT NULL,
            chapter INTEGER NOT NULL,
            verse INTEGER NOT NULL,
            word_index INTEGER NOT NULL,
            greek_form TEXT NOT NULL,
            lemma TEXT,
            morph_code TEXT,
            strong_id TEXT,
            edition_flags TEXT,
            source_name TEXT NOT NULL,
            source_version TEXT,
            imported_at TEXT NOT NULL,
            UNIQUE(book, chapter, verse, word_index, edition_flags)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_greek_tokens_reference
        ON greek_tokens(book, chapter, verse)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_greek_tokens_lemma
        ON greek_tokens(lemma)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_greek_tokens_strong_id
        ON greek_tokens(strong_id)
        """
    )


def import_tagnt_book(
    source_path: str | Path,
    database_path: str | Path,
    book: str,
    source_name: str,
    source_version: str | None = None,
) -> ImportReport:
    source = Path(source_path)
    database = Path(database_path)
    if not source.exists():
        raise FileNotFoundError(f"TAGNT source file not found: {source}")

    rows_read = 0
    rows_imported = 0
    rows_skipped = 0
    parse_errors = 0
    duplicate_rows = 0
    imported_at = datetime.now(UTC).isoformat()

    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        data_section_started = False
        with source.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if _is_ignored_source_line(line):
                    if line.startswith("Word & Type"):
                        data_section_started = True
                    continue
                if not data_section_started and not _looks_like_tagnt_record(line):
                    continue
                if _looks_like_tagnt_record(line):
                    data_section_started = True

                rows_read += 1
                record_book = _record_book(line)
                if record_book and record_book != book:
                    rows_skipped += 1
                    continue

                try:
                    token = parse_tagnt_row(line)
                except ValueError:
                    parse_errors += 1
                    continue

                if token.book != book:
                    rows_skipped += 1
                    continue

                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO greek_tokens (
                        book,
                        chapter,
                        verse,
                        word_index,
                        greek_form,
                        lemma,
                        morph_code,
                        strong_id,
                        edition_flags,
                        source_name,
                        source_version,
                        imported_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        token.book,
                        token.chapter,
                        token.verse,
                        token.word_index,
                        token.greek_form,
                        token.lemma or None,
                        token.morph_code or None,
                        token.strong_id or None,
                        token.edition_flags,
                        source_name,
                        source_version,
                        imported_at,
                    ),
                )
                if cursor.rowcount:
                    rows_imported += 1
                else:
                    duplicate_rows += 1

    return ImportReport(
        source_path=str(source),
        database_path=str(database),
        book=book,
        rows_read=rows_read,
        rows_imported=rows_imported,
        rows_skipped=rows_skipped,
        parse_errors=parse_errors,
        duplicate_rows=duplicate_rows,
    )


def get_sqlite_verse_tokens(
    database_path: str | Path,
    book: str,
    chapter: int,
    verse: int,
) -> list[GreekToken]:
    database = Path(database_path)
    if not database.exists():
        raise FileNotFoundError(f"TAGNT SQLite database not found: {database}")

    try:
        with sqlite3.connect(database) as connection:
            rows = connection.execute(
                """
                SELECT
                    book,
                    chapter,
                    verse,
                    word_index,
                    greek_form,
                    lemma,
                    morph_code,
                    strong_id,
                    edition_flags
                FROM greek_tokens
                WHERE book = ? AND chapter = ? AND verse = ?
                ORDER BY word_index
                """,
                (book, chapter, verse),
            ).fetchall()
    except sqlite3.Error as error:
        raise ValueError(f"Invalid TAGNT SQLite database schema: {error}") from error

    return [
        GreekToken(
            book=row[0],
            chapter=row[1],
            verse=row[2],
            word_index=row[3],
            greek_form=row[4],
            lemma=row[5] or "",
            morph_code=row[6] or "",
            strong_id=row[7] or "",
            edition_flags=row[8] or "",
        )
        for row in rows
    ]


def _is_ignored_source_line(line: str) -> bool:
    return not line or line.startswith("#") or line.startswith("Word & Type")


def _looks_like_tagnt_record(line: str) -> bool:
    return bool(_TAGNT_RECORD_RE.match(line))


def _record_book(line: str) -> str | None:
    match = _TAGNT_BOOK_RE.match(line)
    if not match:
        return None
    return match.group("book")
