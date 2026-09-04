"""Shared/persistent Hungarian Commentary translation cache -- Supabase
Postgres backend selection (production storage/deployment round).

Companion to ``tests/test_commentary_translation.py`` (which exercises the
unchanged, default local-SQLite behavior via explicit ``database_path``
everywhere). These tests cover ONLY the new backend-selection layer added
to ``textus_kb.commentary_translation_store``:

- an explicit ``database_path`` always uses local SQLite regardless of
  backend config (the existing dev/test contract every current caller
  relies on stays intact);
- ``database_path=None`` (the production default) routes to the
  ``supabase`` backend when ``TEXTUS_COMMENTARY_TRANSLATION_BACKEND`` is
  set to it, using the SAME cache-key fields
  (section_id, source_fingerprint, language, policy_version) as the
  composite upsert-conflict-target, for safe concurrent writes;
- any Supabase error is fail-closed (a plain cache miss / not-stored),
  exactly like the SQLite backend's own fail-closed contract.

A minimal fake Postgrest-style client stands in for the real
``supabase`` package -- no real network access anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb import commentary_translation_store as store
from textus_kb.commentary_translation_store import (
    TRANSLATION_BACKEND_ENV_VAR,
    TRANSLATION_SUPABASE_TABLE_ENV_VAR,
    TranslationRecord,
)


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeSelectQuery:
    def __init__(self, table: "_FakeTable") -> None:
        self._table = table
        self._filters: dict[str, str] = {}
        self._limit: int | None = None

    def select(self, _columns: str) -> "_FakeSelectQuery":
        return self

    def eq(self, key: str, value: str) -> "_FakeSelectQuery":
        self._filters[key] = value
        return self

    def limit(self, n: int) -> "_FakeSelectQuery":
        self._limit = n
        return self

    def execute(self) -> _FakeResponse:
        matches = [
            row
            for row in self._table.rows
            if all(row.get(k) == v for k, v in self._filters.items())
        ]
        if self._limit is not None:
            matches = matches[: self._limit]
        return _FakeResponse(matches)


class _FakeUpsertQuery:
    def __init__(self, table: "_FakeTable", payload: dict, on_conflict: str | None) -> None:
        self._table = table
        self._payload = payload
        self._on_conflict = on_conflict

    def execute(self) -> _FakeResponse:
        self._table.upsert_calls.append((dict(self._payload), self._on_conflict))
        key = (
            self._payload["section_id"],
            self._payload["source_fingerprint"],
            self._payload["language"],
            self._payload["policy_version"],
        )
        self._table.rows = [
            row
            for row in self._table.rows
            if (
                row["section_id"],
                row["source_fingerprint"],
                row["language"],
                row["policy_version"],
            )
            != key
        ]
        self._table.rows.append(dict(self._payload))
        return _FakeResponse([self._payload])


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.upsert_calls: list[tuple[dict, str | None]] = []

    def select(self, columns: str) -> _FakeSelectQuery:
        return _FakeSelectQuery(self).select(columns)

    def upsert(self, payload: dict, on_conflict: str | None = None) -> _FakeUpsertQuery:
        return _FakeUpsertQuery(self, payload, on_conflict)


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {}
        self.requested_tables: list[str] = []

    def table(self, name: str) -> _FakeTable:
        self.requested_tables.append(name)
        return self.tables.setdefault(name, _FakeTable())


class _RaisingSupabaseClient:
    def table(self, _name: str) -> "_RaisingSupabaseClient":
        return self

    def select(self, *_a, **_k):  # noqa: ANN002, ANN003
        raise ConnectionError("network down")

    def upsert(self, *_a, **_k):  # noqa: ANN002, ANN003
        raise ConnectionError("network down")


@pytest.fixture(autouse=True)
def _isolate_backend_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TRANSLATION_BACKEND_ENV_VAR, raising=False)
    monkeypatch.delenv(TRANSLATION_SUPABASE_TABLE_ENV_VAR, raising=False)
    monkeypatch.setattr(store, "_translation_secret_value", lambda key: "")


# --- default backend / explicit path are unaffected ------------------------


def test_default_backend_is_sqlite() -> None:
    assert store._configured_backend() == "sqlite"


def test_explicit_database_path_ignores_supabase_backend_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")

    def boom() -> None:
        raise AssertionError("Explicit database_path must never reach Supabase.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    db_path = tmp_path / "commentary_translations.sqlite3"
    saved = store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-1",
        language="hu",
        policy_version="v1",
        translated_text="Szöveg.",
        database_path=db_path,
    )
    assert saved is not None
    assert db_path.is_file()
    fetched = store.get_translation(
        "sec-1", "fp-1", language="hu", policy_version="v1", database_path=db_path
    )
    assert fetched is not None
    assert fetched.translated_text == "Szöveg."


# --- supabase backend: cache-miss / cache-hit -------------------------------


def test_supabase_backend_cache_miss_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    client = _FakeSupabaseClient()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    result = store.get_translation("sec-1", "fp-1", language="hu", policy_version="v1")
    assert result is None
    assert client.requested_tables == ["commentary_translations"]


def test_supabase_backend_save_then_get_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    client = _FakeSupabaseClient()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    saved = store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-1",
        language="hu",
        policy_version="v1",
        translated_text="Megosztott fordítás.",
        provider_model="gemini-test",
    )
    assert saved is not None
    assert isinstance(saved, TranslationRecord)

    fetched = store.get_translation("sec-1", "fp-1", language="hu", policy_version="v1")
    assert fetched is not None
    assert fetched.translated_text == "Megosztott fordítás."
    assert fetched.provider_model == "gemini-test"

    # A DIFFERENT user/session, same process config, sees the SAME cached
    # row -- this is exactly the cross-user sharing the SQLite backend
    # cannot guarantee on an ephemeral/per-instance filesystem.
    fetched_again = store.get_translation("sec-1", "fp-1", language="hu", policy_version="v1")
    assert fetched_again == fetched


def test_supabase_backend_upsert_uses_composite_conflict_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    client = _FakeSupabaseClient()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-1",
        language="hu",
        policy_version="v1",
        translated_text="Első verzió.",
    )
    table = client.tables["commentary_translations"]
    assert len(table.upsert_calls) == 1
    payload, on_conflict = table.upsert_calls[0]
    assert on_conflict == "section_id,source_fingerprint,language,policy_version"
    assert payload["section_id"] == "sec-1"

    # A "concurrent" second save for the SAME key overwrites in place
    # (last-write-wins), never creating a duplicate row.
    store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-1",
        language="hu",
        policy_version="v1",
        translated_text="Frissített verzió.",
    )
    assert len(table.rows) == 1
    assert table.rows[0]["translated_text"] == "Frissített verzió."


def test_supabase_backend_fingerprint_change_invalidates_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    client = _FakeSupabaseClient()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-old",
        language="hu",
        policy_version="v1",
        translated_text="Régi forrás fordítása.",
    )
    # A corpus rebuild changes the fingerprint -- the old cached row must
    # not be served for the new fingerprint (same semantics the SQLite
    # backend already guarantees via its own UNIQUE key).
    miss = store.get_translation("sec-1", "fp-new", language="hu", policy_version="v1")
    assert miss is None


def test_supabase_backend_policy_version_change_invalidates_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    client = _FakeSupabaseClient()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-1",
        language="hu",
        policy_version="v1",
        translated_text="Régi policy fordítása.",
    )
    miss = store.get_translation("sec-1", "fp-1", language="hu", policy_version="v2")
    assert miss is None


# --- fail-closed on any Supabase error ---------------------------------


def test_supabase_backend_get_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _RaisingSupabaseClient()
    )
    result = store.get_translation("sec-1", "fp-1", language="hu", policy_version="v1")
    assert result is None


def test_supabase_backend_save_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _RaisingSupabaseClient()
    )
    result = store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-1",
        language="hu",
        policy_version="v1",
        translated_text="Szöveg.",
    )
    assert result is None


def test_supabase_backend_never_caches_blank_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRANSLATION_BACKEND_ENV_VAR, "supabase")
    client = _FakeSupabaseClient()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    result = store.save_translation(
        section_id="sec-1",
        source_fingerprint="fp-1",
        language="hu",
        policy_version="v1",
        translated_text="   ",
    )
    assert result is None
    assert client.tables == {}


def test_configured_supabase_table_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRANSLATION_SUPABASE_TABLE_ENV_VAR, "custom_translations_table")
    assert store._configured_supabase_table() == "custom_translations_table"
