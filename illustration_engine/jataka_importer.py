"""Thin, Jataka-specific wrapper around the shared `pg_story_import`
import glue (see that module's docstring for why it's shared).

Kept as its own module — rather than callers using `pg_story_import`
directly — so `import_jataka_book(connection, spec=..., raw_text_path=...)`
stays the stable, source-specific entry point `scripts/build_illustration_
database.py` and the test suite already depend on.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from illustration_engine.jataka_parser import JatakaBookSpec, parse_jataka_file
from illustration_engine.pg_story_import import PgImportReport, import_pg_book


JatakaImportReport = PgImportReport


def import_jataka_book(
    connection: sqlite3.Connection,
    *,
    spec: JatakaBookSpec,
    raw_text_path: str | Path,
    registry_path: str | Path | None = None,
) -> PgImportReport:
    return import_pg_book(
        connection,
        source_code=spec.source_code,
        raw_text_path=raw_text_path,
        parse_fn=lambda path: parse_jataka_file(path, spec),
        registry_path=registry_path,
    )


__all__ = ["JatakaImportReport", "import_jataka_book"]
