from __future__ import annotations

import sqlite3
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bible_engine.tagnt_parser import GreekToken, parse_tagnt_row


_TAGNT_RECORD_RE = re.compile(r"^[1-3]?[A-Za-z]{2,3}\.\d+\.\d+(?:[\[\(\{][^#]+[\]\)\}])?#")
_TAGNT_BOOK_RE = re.compile(r"^(?P<book>[1-3]?[A-Za-z]{2,3})\.")


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


TAGNT_NEW_TESTAMENT_BOOKS: tuple[str, ...] = (
    "Mat",
    "Mrk",
    "Luk",
    "Jhn",
    "Act",
    "Rom",
    "1Co",
    "2Co",
    "Gal",
    "Eph",
    "Php",
    "Col",
    "1Th",
    "2Th",
    "1Ti",
    "2Ti",
    "Tit",
    "Phm",
    "Heb",
    "Jas",
    "1Pe",
    "2Pe",
    "1Jn",
    "2Jn",
    "3Jn",
    "Jud",
    "Rev",
)


@dataclass(frozen=True)
class BookImportCount:
    book: str
    rows_imported: int
    chapters: int
    verses: int


@dataclass(frozen=True)
class FullImportReport:
    database_path: str
    source_files: tuple[str, ...]
    books_requested: tuple[str, ...]
    books_imported: tuple[str, ...]
    rows_read: int
    rows_imported: int
    rows_skipped: int
    parse_errors: int
    duplicate_rows: int
    per_book_rows: tuple[BookImportCount, ...]
    started_at: str
    completed_at: str


@dataclass(frozen=True)
class DatabaseValidationReport:
    book_count: int
    token_count: int
    chapter_count: int
    verse_count: int
    missing_books: tuple[str, ...]
    duplicate_key_count: int
    invalid_token_count: int
    per_book_counts: tuple[BookImportCount, ...]
    warnings: tuple[str, ...]


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


def import_tagnt_new_testament(
    mat_jhn_source_path: str | Path,
    act_rev_source_path: str | Path,
    database_path: str | Path,
    source_version: str | None = None,
) -> FullImportReport:
    sources = (Path(mat_jhn_source_path), Path(act_rev_source_path))
    missing_sources = [str(source) for source in sources if not source.exists()]
    if missing_sources:
        raise FileNotFoundError(
            f"TAGNT source file not found: {', '.join(missing_sources)}"
        )

    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    imported_at = started_at

    rows_read = 0
    rows_imported = 0
    rows_skipped = 0
    parse_errors = 0
    duplicate_rows = 0
    allowed_books = set(TAGNT_NEW_TESTAMENT_BOOKS)

    with sqlite3.connect(database) as connection:
        create_schema(connection)
        for source in sources:
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
                    if record_book not in allowed_books:
                        rows_skipped += 1
                        continue

                    try:
                        token = parse_tagnt_row(line)
                    except ValueError:
                        parse_errors += 1
                        continue

                    if token.book not in allowed_books:
                        rows_skipped += 1
                        continue

                    cursor = _insert_token(
                        connection,
                        token,
                        source_name=f"STEPBible TAGNT {source.name}",
                        source_version=source_version,
                        imported_at=imported_at,
                    )
                    if cursor.rowcount:
                        rows_imported += 1
                    else:
                        duplicate_rows += 1

    completed_at = datetime.now(UTC).isoformat()
    per_book_rows = _book_import_counts(database, TAGNT_NEW_TESTAMENT_BOOKS)
    books_imported = tuple(book.book for book in per_book_rows if book.rows_imported)

    return FullImportReport(
        database_path=str(database),
        source_files=tuple(str(source) for source in sources),
        books_requested=TAGNT_NEW_TESTAMENT_BOOKS,
        books_imported=books_imported,
        rows_read=rows_read,
        rows_imported=rows_imported,
        rows_skipped=rows_skipped,
        parse_errors=parse_errors,
        duplicate_rows=duplicate_rows,
        per_book_rows=per_book_rows,
        started_at=started_at,
        completed_at=completed_at,
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

                cursor = _insert_token(
                    connection,
                    token,
                    source_name=source_name,
                    source_version=source_version,
                    imported_at=imported_at,
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


def validate_tagnt_nt_database(
    database_path: str | Path,
) -> DatabaseValidationReport:
    database = Path(database_path)
    if not database.exists():
        raise FileNotFoundError(f"TAGNT SQLite database not found: {database}")

    try:
        with sqlite3.connect(database) as connection:
            books = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT book FROM greek_tokens ORDER BY book"
                ).fetchall()
            )
            token_count = connection.execute(
                "SELECT COUNT(*) FROM greek_tokens"
            ).fetchone()[0]
            chapter_count = connection.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT book, chapter FROM greek_tokens)"
            ).fetchone()[0]
            verse_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM (SELECT DISTINCT book, chapter, verse FROM greek_tokens)
                """
            ).fetchone()[0]
            duplicate_key_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT book, chapter, verse, word_index, edition_flags, COUNT(*) AS total
                    FROM greek_tokens
                    GROUP BY book, chapter, verse, word_index, edition_flags
                    HAVING total > 1
                )
                """
            ).fetchone()[0]
            invalid_token_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM greek_tokens
                WHERE
                    book = ''
                    OR chapter <= 0
                    OR verse <= 0
                    OR word_index <= 0
                    OR greek_form = ''
                    OR book NOT IN ({placeholders})
                """.format(
                    placeholders=", ".join("?" for _ in TAGNT_NEW_TESTAMENT_BOOKS)
                ),
                TAGNT_NEW_TESTAMENT_BOOKS,
            ).fetchone()[0]
    except sqlite3.Error as error:
        raise ValueError(f"Invalid TAGNT SQLite database schema: {error}") from error

    missing_books = tuple(
        book for book in TAGNT_NEW_TESTAMENT_BOOKS if book not in set(books)
    )
    unexpected_books = tuple(book for book in books if book not in set(TAGNT_NEW_TESTAMENT_BOOKS))
    warnings: list[str] = []
    if missing_books:
        warnings.append(f"Missing TAGNT NT books: {', '.join(missing_books)}")
    if unexpected_books:
        warnings.append(f"Unexpected book codes: {', '.join(unexpected_books)}")
    if duplicate_key_count:
        warnings.append(f"Duplicate token keys: {duplicate_key_count}")
    if invalid_token_count:
        warnings.append(f"Invalid token rows: {invalid_token_count}")

    return DatabaseValidationReport(
        book_count=len(books),
        token_count=token_count,
        chapter_count=chapter_count,
        verse_count=verse_count,
        missing_books=missing_books,
        duplicate_key_count=duplicate_key_count,
        invalid_token_count=invalid_token_count,
        per_book_counts=_book_import_counts(database, TAGNT_NEW_TESTAMENT_BOOKS),
        warnings=tuple(warnings),
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


def _insert_token(
    connection: sqlite3.Connection,
    token: GreekToken,
    *,
    source_name: str,
    source_version: str | None,
    imported_at: str,
) -> sqlite3.Cursor:
    return connection.execute(
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


def _book_import_counts(
    database_path: Path,
    books: tuple[str, ...],
) -> tuple[BookImportCount, ...]:
    with sqlite3.connect(database_path) as connection:
        counts_by_book = {
            row[0]: BookImportCount(
                book=row[0],
                rows_imported=row[1],
                chapters=row[2],
                verses=row[3],
            )
            for row in connection.execute(
                """
                SELECT
                    book,
                    COUNT(*) AS token_count,
                    COUNT(DISTINCT chapter) AS chapter_count,
                    COUNT(DISTINCT chapter || ':' || verse) AS verse_count
                FROM greek_tokens
                GROUP BY book
                """
            ).fetchall()
        }
    return tuple(
        counts_by_book.get(
            book,
            BookImportCount(book=book, rows_imported=0, chapters=0, verses=0),
        )
        for book in books
    )


def _is_ignored_source_line(line: str) -> bool:
    return not line or line.startswith("#") or line.startswith("Word & Type")


def _looks_like_tagnt_record(line: str) -> bool:
    return bool(_TAGNT_RECORD_RE.match(line))


def _record_book(line: str) -> str | None:
    match = _TAGNT_BOOK_RE.match(line)
    if not match:
        return None
    return match.group("book")
