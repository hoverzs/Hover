from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bible_engine.hebrew_parser import HebrewToken
from bible_engine.hebrew_sqlite import (
    DEFAULT_TAHOT_DATABASE_PATH,
    HebrewDatabaseDiagnostics,
    find_hebrew_tokens_by_lemma,
    find_hebrew_tokens_by_strong_id,
    get_hebrew_books,
    get_hebrew_passage_tokens,
    get_hebrew_token,
    inspect_hebrew_database_path,
    resolve_tahot_database_path,
)


@dataclass(frozen=True)
class HebrewRepositoryResult:
    status: str
    tokens: tuple[HebrewToken, ...] = ()
    diagnostics: HebrewDatabaseDiagnostics | None = None


class HebrewTokenRepository:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = resolve_tahot_database_path(database_path)

    def diagnostics(self) -> HebrewDatabaseDiagnostics:
        return inspect_hebrew_database_path(self.database_path)

    def passage(
        self,
        book: str,
        chapter: int,
        verse_start: int,
        verse_end: int | None = None,
    ) -> HebrewRepositoryResult:
        status = self._database_status()
        if status != "ok":
            return HebrewRepositoryResult(status=status, diagnostics=self.diagnostics())
        tokens = tuple(get_hebrew_passage_tokens(self.database_path, book, chapter, verse_start, verse_end))
        if not tokens:
            return HebrewRepositoryResult(status="passage_not_found", diagnostics=self.diagnostics())
        return HebrewRepositoryResult(status="ok", tokens=tokens, diagnostics=self.diagnostics())

    def token(self, stable_token_key: str) -> HebrewToken | None:
        if self._database_status() != "ok":
            return None
        return get_hebrew_token(self.database_path, stable_token_key)

    def by_lemma(self, lemma: str) -> tuple[HebrewToken, ...]:
        if self._database_status() != "ok":
            return ()
        return tuple(find_hebrew_tokens_by_lemma(self.database_path, lemma))

    def by_strong_id(self, strong_id: str) -> tuple[HebrewToken, ...]:
        if self._database_status() != "ok":
            return ()
        return tuple(find_hebrew_tokens_by_strong_id(self.database_path, strong_id))

    def books(self) -> list[tuple[str, int, int, int]]:
        if self._database_status() != "ok":
            return []
        return get_hebrew_books(self.database_path)

    def _database_status(self) -> str:
        diagnostics = self.diagnostics()
        if not diagnostics.exists:
            return "database_missing"
        if not diagnostics.required_tables_present or diagnostics.integrity_check != "ok":
            return "database_invalid"
        return "ok"


def default_hebrew_token_repository() -> HebrewTokenRepository:
    return HebrewTokenRepository(DEFAULT_TAHOT_DATABASE_PATH)
