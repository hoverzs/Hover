"""Thin, Merényi László-specific wrapper around the shared
`pg_story_import` import glue (see that module's docstring, and
`jataka_importer.py`/`aesop_importer.py`/`arany_laszlo_importer.py` for
the sibling wrappers).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from illustration_engine.merenyi_laszlo_parser import MerenyiBookSpec, parse_merenyi_laszlo_file
from illustration_engine.pg_story_import import PgImportReport, import_pg_book


MerenyiLaszloImportReport = PgImportReport


def import_merenyi_laszlo_book(
    connection: sqlite3.Connection,
    *,
    spec: MerenyiBookSpec,
    raw_text_path: str | Path,
    registry_path: str | Path | None = None,
) -> PgImportReport:
    return import_pg_book(
        connection,
        source_code=spec.source_code,
        raw_text_path=raw_text_path,
        parse_fn=lambda path: parse_merenyi_laszlo_file(path, spec),
        registry_path=registry_path,
    )


__all__ = ["MerenyiLaszloImportReport", "import_merenyi_laszlo_book"]
