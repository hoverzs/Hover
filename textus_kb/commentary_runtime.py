"""Runtime bootstrap for the gitignored Commentary SQLite artifact.

Fail-closed status resolution only. Unlike ``theology_runtime`` (which
downloads one pinned production artifact from private storage), the
Commentary store is built locally from the CCEL Calvin source manifest via
``scripts/build_commentary_database.py`` — there is no single pinned blob
to fetch here, and this module never downloads or builds anything. It
exists so callers have one place to resolve the database path (default,
env override, or explicit override) and check schema/content validity
without duplicating that logic.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    SCHEMA_VERSION,
    CommentaryImportError,
    validate_commentary_database,
)

COMMENTARY_DATABASE_PATH_ENV_VAR = "TEXTUS_COMMENTARY_DATABASE_PATH"


@dataclass(frozen=True)
class CommentaryRuntimeStatus:
    available: bool
    reason: str
    database_path: str
    detail: str = ""


def get_status(database_path: str | Path | None = None) -> CommentaryRuntimeStatus:
    """Validate a local Commentary DB without downloading or building it.

    ``database_path`` takes precedence; otherwise ``TEXTUS_COMMENTARY_DATABASE_PATH``;
    otherwise the default ``data/generated/commentary.sqlite3`` path.
    """
    path = _resolve_database_path(database_path)
    return _validate_database(path)


def _resolve_database_path(database_path: str | Path | None) -> Path:
    if database_path is not None:
        return Path(database_path)
    env_value = os.environ.get(COMMENTARY_DATABASE_PATH_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_DATABASE_PATH


def _validate_database(path: Path) -> CommentaryRuntimeStatus:
    if not path.is_file():
        return CommentaryRuntimeStatus(False, "database_missing", str(path))
    try:
        validation = validate_commentary_database(path)
    except FileNotFoundError:
        return CommentaryRuntimeStatus(False, "database_missing", str(path))
    except (OSError, sqlite3.Error) as exc:
        return CommentaryRuntimeStatus(False, "database_unopenable", str(path), str(exc))
    except CommentaryImportError as exc:
        return CommentaryRuntimeStatus(False, "schema_incompatible", str(path), str(exc))
    if validation.schema_version != SCHEMA_VERSION:
        return CommentaryRuntimeStatus(
            False,
            "schema_incompatible",
            str(path),
            f"schema_version={validation.schema_version or '<missing>'}",
        )
    return CommentaryRuntimeStatus(True, "ok", str(path))


__all__ = [
    "COMMENTARY_DATABASE_PATH_ENV_VAR",
    "CommentaryRuntimeStatus",
    "get_status",
]
