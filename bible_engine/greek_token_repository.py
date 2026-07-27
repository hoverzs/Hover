from __future__ import annotations

import os
from pathlib import Path

from bible_engine.tagnt_parser import GreekToken
from bible_engine.tagnt_sqlite import get_sqlite_verse_tokens
from ruf_bible_service import parse_bible_reference


ROOT = Path(__file__).parents[1]
DEFAULT_TAGNT_DATABASE_PATH = ROOT / "data" / "generated" / "tagnt_john.sqlite3"
TAGNT_DATABASE_ENV_VAR = "TEXTUS_TAGNT_DB_PATH"


def resolve_tagnt_database_path() -> Path | None:
    env_value = os.environ.get(TAGNT_DATABASE_ENV_VAR)
    if env_value and env_value.strip():
        return Path(env_value).expanduser()

    secret_value = _tagnt_database_path_from_streamlit_secrets()
    if secret_value:
        return Path(secret_value).expanduser()

    return DEFAULT_TAGNT_DATABASE_PATH


def load_greek_verse_tokens(
    reference: str,
    database_path: str | Path | None = None,
) -> list[GreekToken]:
    parsed = parse_bible_reference(reference)
    if parsed.book.code != "JHN":
        raise ValueError(f"Only John is available in the local TAGNT database: {reference!r}")
    if parsed.verse_start is None:
        raise ValueError(f"Only single John verses are supported: {reference!r}")
    if parsed.verse_end is not None and parsed.verse_end != parsed.verse_start:
        raise ValueError(f"Only single John verses are supported: {reference!r}")

    path = Path(database_path) if database_path is not None else resolve_tagnt_database_path()
    if path is None:
        raise FileNotFoundError("TAGNT SQLite database path is not configured.")

    return get_sqlite_verse_tokens(path, "Jhn", parsed.chapter, parsed.verse_start)


def _tagnt_database_path_from_streamlit_secrets() -> str | None:
    try:
        import streamlit as st

        tagnt_database = st.secrets.get("tagnt_database", {})
    except Exception:
        return None

    if isinstance(tagnt_database, dict):
        value = tagnt_database.get("path")
    else:
        value = getattr(tagnt_database, "path", None)

    if value is None:
        return None
    text = str(value).strip()
    return text or None
