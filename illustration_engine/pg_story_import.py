"""Backward-compatible re-export shim.

This module's actual logic moved to `story_import.py` in Phase 2N,
once a genuinely non-PG source (Hebrew Tales, from Wikisource) needed
the exact same idempotent-insert glue and calling it "PG import" would
have been a mislabeling. Every existing `*_importer.py` module for a
real Project-Gutenberg-sourced book still imports `PgImportReport`/
`import_pg_book` from here — that keeps working unchanged. New,
non-PG-sourced importers should import `StoryImportReport`/
`import_story_collection` from `story_import` directly instead of
through this PG-named alias.
"""

from __future__ import annotations

from illustration_engine.story_import import (
    ParsedStoryLike,
    StoryImportReport as PgImportReport,
    import_story_collection as import_pg_book,
)


__all__ = ["ParsedStoryLike", "PgImportReport", "import_pg_book"]
