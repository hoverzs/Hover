"""Thin, Gulistan-specific wrapper around the shared `pg_story_import`
import glue (see that module's docstring, and the other `*_importer.py`
modules for the sibling wrappers).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from illustration_engine.gulistan_parser import SOURCE_CODE, parse_gulistan_file
from illustration_engine.pg_story_import import PgImportReport, import_pg_book


GulistanImportReport = PgImportReport


def import_gulistan_book(
    connection: sqlite3.Connection,
    *,
    raw_text_path: str | Path,
    registry_path: str | Path | None = None,
) -> PgImportReport:
    return import_pg_book(
        connection,
        source_code=SOURCE_CODE,
        raw_text_path=raw_text_path,
        parse_fn=parse_gulistan_file,
        registry_path=registry_path,
    )


__all__ = ["GulistanImportReport", "import_gulistan_book"]
