from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from bible_engine.tagnt_books import parse_tagnt_bible_reference
from bible_engine.tagnt_books import tagnt_book_code_from_ruf_code
from bible_engine.tagnt_parser import GreekToken
from bible_engine.tagnt_sqlite import get_sqlite_verse_tokens


ROOT = Path(__file__).parents[1]
DEFAULT_TAGNT_DATABASE_PATH = ROOT / "data" / "generated" / "tagnt_nt.sqlite3"
TAGNT_DATABASE_ENV_VAR = "TEXTUS_TAGNT_DB_PATH"


@dataclass(frozen=True)
class GreekVerseTokens:
    book: str
    chapter: int
    verse: int
    tokens: tuple[GreekToken, ...]


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
    verses = load_greek_passage_tokens(reference, database_path=database_path)
    if len(verses) != 1:
        raise ValueError(f"Only single verse references are supported: {reference!r}")
    return list(verses[0].tokens)


def load_greek_passage_tokens(
    reference: str,
    database_path: str | Path | None = None,
) -> list[GreekVerseTokens]:
    parsed = parse_tagnt_bible_reference(reference)
    tagnt_book = tagnt_book_code_from_ruf_code(parsed.book.code)
    if tagnt_book is None:
        raise ValueError(
            f"Only New Testament books are available in the local TAGNT database: {reference!r}"
        )
    if parsed.verse_start is None:
        raise ValueError(f"Only verse references are supported: {reference!r}")

    path = Path(database_path) if database_path is not None else resolve_tagnt_database_path()
    if path is None:
        raise FileNotFoundError("TAGNT SQLite database path is not configured.")

    verse_end = parsed.verse_end or parsed.verse_start
    verses: list[GreekVerseTokens] = []
    for verse in range(parsed.verse_start, verse_end + 1):
        tokens = get_sqlite_verse_tokens(path, tagnt_book, parsed.chapter, verse)
        if not tokens:
            continue
        verses.append(
            GreekVerseTokens(
                book=tagnt_book,
                chapter=parsed.chapter,
                verse=verse,
                tokens=tuple(sorted(tokens, key=lambda token: token.word_index)),
            )
        )
    return sorted(verses, key=lambda item: item.verse)


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
