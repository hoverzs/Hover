"""Thin, Hebrew-Tales-specific wrapper around the shared, format-
agnostic `story_import` glue (see that module's docstring, and the
`*_importer.py` modules for the PG-sourced siblings).

Deliberately does NOT go through `pg_story_import.py` — this source is
a Wikisource transcription, not a Project Gutenberg one (see
`hebrew_tales_parser.py`'s module docstring for the full audit trail).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from illustration_engine.hebrew_tales_parser import SOURCE_CODE, parse_hebrew_tales_file
from illustration_engine.story_import import StoryImportReport, import_story_collection


HebrewTalesImportReport = StoryImportReport


def import_hebrew_tales_book(
    connection: sqlite3.Connection,
    *,
    raw_text_path: str | Path,
    registry_path: str | Path | None = None,
) -> StoryImportReport:
    return import_story_collection(
        connection,
        source_code=SOURCE_CODE,
        raw_text_path=raw_text_path,
        parse_fn=parse_hebrew_tales_file,
        registry_path=registry_path,
    )


__all__ = ["HebrewTalesImportReport", "import_hebrew_tales_book"]
