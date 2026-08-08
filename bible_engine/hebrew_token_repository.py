from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bible_engine.hebrew_morphology import HebrewMorphology, decode_hebrew_morphology
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
        self._diagnostics_cache: HebrewDatabaseDiagnostics | None = None

    def diagnostics(self) -> HebrewDatabaseDiagnostics:
        """A `PRAGMA integrity_check` egy teljes DB-vizsgálat (itt: ~2 mp
        a jelenlegi fájlméretnél) — egy repository-példány élettartamán
        belül elég egyszer lefuttatni, nem minden metódushíváskor (a
        `passage()` korábban akár 3x is lefuttatta egyetlen hívásban).
        Új `HebrewTokenRepository()` példány (pl. minden Streamlit
        rerun) friss ellenőrzést kap — ez a cache nem tartós."""
        if self._diagnostics_cache is None:
            self._diagnostics_cache = inspect_hebrew_database_path(self.database_path)
        return self._diagnostics_cache

    def passage(
        self,
        book: str,
        chapter: int,
        verse_start: int,
        verse_end: int | None = None,
    ) -> HebrewRepositoryResult:
        status = self._database_status()
        diagnostics = self.diagnostics()
        if status != "ok":
            return HebrewRepositoryResult(status=status, diagnostics=diagnostics)
        tokens = tuple(get_hebrew_passage_tokens(self.database_path, book, chapter, verse_start, verse_end))
        if not tokens:
            return HebrewRepositoryResult(status="passage_not_found", diagnostics=diagnostics)
        return HebrewRepositoryResult(status="ok", tokens=tokens, diagnostics=diagnostics)

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

    def morphology(
        self,
        token: HebrewToken,
        expansions: dict[str, str] | None = None,
    ) -> HebrewMorphology:
        return decode_hebrew_morphology(token.morphology_code, expansions or {})

    def _database_status(self) -> str:
        diagnostics = self.diagnostics()
        if not diagnostics.exists:
            return "database_missing"
        if not diagnostics.required_tables_present or diagnostics.integrity_check != "ok":
            return "database_invalid"
        return "ok"


def default_hebrew_token_repository() -> HebrewTokenRepository:
    return HebrewTokenRepository(DEFAULT_TAHOT_DATABASE_PATH)
