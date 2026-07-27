from __future__ import annotations

import os
from pathlib import Path

from bible_engine.tbesg_parser import normalize_greek_strong_id
from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry, get_sqlite_lexicon_entry


ROOT = Path(__file__).parents[1]
DEFAULT_TBESG_DATABASE_PATH = ROOT / "data" / "generated" / "tbesg_lexicon.sqlite3"
TBESG_DATABASE_ENV_VAR = "TEXTUS_TBESG_DB_PATH"


class TBESGDatabaseUnavailableError(FileNotFoundError):
    pass


def resolve_tbesg_database_path() -> Path:
    env_value = os.environ.get(TBESG_DATABASE_ENV_VAR)
    if env_value and env_value.strip():
        return Path(env_value).expanduser()

    secret_value = _tbesg_database_path_from_streamlit_secrets()
    if secret_value:
        return Path(secret_value).expanduser()

    return DEFAULT_TBESG_DATABASE_PATH


def get_tbesg_lexicon_entry(
    strong_id: str,
    database_path: str | Path | None = None,
) -> SQLiteGreekLexiconEntry | None:
    normalized = normalize_greek_strong_id(strong_id)
    path = Path(database_path) if database_path is not None else resolve_tbesg_database_path()
    if not path.exists():
        raise TBESGDatabaseUnavailableError(f"TBESG SQLite database not found: {path}")
    return get_sqlite_lexicon_entry(path, normalized)


def _tbesg_database_path_from_streamlit_secrets() -> str | None:
    try:
        import streamlit as st

        tbesg_database = st.secrets.get("tbesg_database", {})
    except Exception:
        return None

    if isinstance(tbesg_database, dict):
        value = tbesg_database.get("path")
        if value:
            return str(value)
    return None
