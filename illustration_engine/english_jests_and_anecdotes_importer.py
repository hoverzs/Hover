"""Thin, English-Jests-and-Anecdotes-specific wrapper around the shared
`pg_story_import` import glue (see that module's docstring, and the
other `*_importer.py` modules for the sibling wrappers).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from illustration_engine.english_jests_and_anecdotes_parser import (
    SOURCE_CODE,
    parse_english_jests_file,
)
from illustration_engine.pg_story_import import PgImportReport, import_pg_book


EnglishJestsImportReport = PgImportReport


def import_english_jests_book(
    connection: sqlite3.Connection,
    *,
    raw_text_path: str | Path,
    registry_path: str | Path | None = None,
) -> PgImportReport:
    return import_pg_book(
        connection,
        source_code=SOURCE_CODE,
        raw_text_path=raw_text_path,
        parse_fn=parse_english_jests_file,
        registry_path=registry_path,
    )


__all__ = ["EnglishJestsImportReport", "import_english_jests_book"]
