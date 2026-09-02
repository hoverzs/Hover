"""Thin, Aesop-specific wrapper around the shared `pg_story_import`
import glue (see that module's docstring, and `jataka_importer.py` for
the sibling wrapper).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from illustration_engine.aesop_parser import SOURCE_CODE, parse_aesop_file
from illustration_engine.pg_story_import import PgImportReport, import_pg_book


AesopImportReport = PgImportReport


def import_aesop_book(
    connection: sqlite3.Connection,
    *,
    raw_text_path: str | Path,
    registry_path: str | Path | None = None,
) -> PgImportReport:
    return import_pg_book(
        connection,
        source_code=SOURCE_CODE,
        raw_text_path=raw_text_path,
        parse_fn=parse_aesop_file,
        registry_path=registry_path,
    )


__all__ = ["AesopImportReport", "import_aesop_book"]
