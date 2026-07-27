from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bible_engine.greek_lexicon_repository import (
    DEFAULT_TBESG_DATABASE_PATH,
    TBESG_DATABASE_ENV_VAR,
    TBESGDatabaseUnavailableError,
    get_tbesg_lexicon_entry,
    resolve_tbesg_database_path,
)
from bible_engine.tbesg_sqlite import import_tbesg_lexicon


ROOT = Path(__file__).parents[1]
TBESG_FIXTURE = ROOT / "tests" / "fixtures" / "tbesg_sample.tsv"


def test_default_tbesg_database_path_is_generated_sqlite(monkeypatch) -> None:
    monkeypatch.delenv(TBESG_DATABASE_ENV_VAR, raising=False)

    assert resolve_tbesg_database_path() == DEFAULT_TBESG_DATABASE_PATH
    assert DEFAULT_TBESG_DATABASE_PATH == ROOT / "data" / "generated" / "tbesg_lexicon.sqlite3"


def test_environment_variable_overrides_default_path(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "custom.sqlite3"
    monkeypatch.setenv(TBESG_DATABASE_ENV_VAR, str(database))

    assert resolve_tbesg_database_path() == database


def test_get_tbesg_entry_by_strong_id_and_normalized_id(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)

    direct = get_tbesg_lexicon_entry("G0025", database_path=database)
    normalized = get_tbesg_lexicon_entry("G25", database_path=database)

    assert direct == normalized
    assert direct is not None
    assert direct.strong_id == "G0025"
    assert direct.lemma == "ἀγαπάω"
    assert direct.gloss == "to love"


def test_get_tbesg_entry_returns_none_for_missing_record(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)

    assert get_tbesg_lexicon_entry("G9999", database_path=database) is None


def test_missing_database_has_controlled_domain_error(tmp_path: Path) -> None:
    with pytest.raises(TBESGDatabaseUnavailableError, match="TBESG SQLite database not found"):
        get_tbesg_lexicon_entry("G0025", database_path=tmp_path / "missing.sqlite3")


def test_invalid_strong_id_is_rejected_before_database_lookup(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid Greek Strong identifier"):
        get_tbesg_lexicon_entry("H0157", database_path=tmp_path / "missing.sqlite3")


def test_invalid_database_schema_is_reported(tmp_path: Path) -> None:
    database = tmp_path / "invalid.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE greek_lexicon (strong_id TEXT)")

    with pytest.raises(ValueError, match="Invalid TBESG SQLite database schema"):
        get_tbesg_lexicon_entry("G0025", database_path=database)


def test_repository_does_not_require_network_for_lookup(tmp_path: Path, monkeypatch) -> None:
    database = _import_fixture(tmp_path)

    def fail_network(*_args, **_kwargs):
        raise AssertionError("network access must not be used")

    monkeypatch.setattr("socket.create_connection", fail_network)

    assert get_tbesg_lexicon_entry("G2889", database_path=database).lemma == "κόσμος"


def _import_fixture(tmp_path: Path) -> Path:
    database = tmp_path / "lexicon.sqlite3"
    import_tbesg_lexicon(TBESG_FIXTURE, database)
    return database
