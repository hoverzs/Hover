"""Theology runtime ensure/provisioning tests (Phase D3B)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from textus_kb.importers.theology_sqlite import (
    create_empty_theology_database,
    import_theology_sqlite,
    validate_theology_database,
)
from textus_kb.theology_runtime import (
    THEOLOGY_DATABASE_SHA256_ENV_VAR,
    THEOLOGY_STORAGE_BUCKET_ENV_VAR,
    THEOLOGY_STORAGE_OBJECT_ENV_VAR,
    ensure_theology_database,
    get_status,
)

FIXTURE_PATH = Path("tests/fixtures/kb/theology_v1_sample.json")


class _FakeBucket:
    def __init__(self, payload: bytes = b"", error: BaseException | None = None) -> None:
        self.payload = payload
        self.error = error
        self.requested_paths: list[str] = []

    def download(self, object_path: str) -> bytes:
        self.requested_paths.append(object_path)
        if self.error:
            raise self.error
        return self.payload


class _FakeStorage:
    def __init__(self, bucket: _FakeBucket) -> None:
        self.bucket = bucket
        self.requested_buckets: list[str] = []

    def from_(self, bucket_id: str) -> _FakeBucket:
        self.requested_buckets.append(bucket_id)
        return self.bucket


class _FakeSupabaseClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self.storage = _FakeStorage(bucket)


def _import_sample(tmp_path: Path) -> Path:
    database = tmp_path / "theology.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    import_theology_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    return database


def _pin_to_database(monkeypatch: pytest.MonkeyPatch, database: Path) -> None:
    import textus_kb.theology_runtime as runtime

    validation = validate_theology_database(database)
    monkeypatch.setattr(runtime, "EXPECTED_SCHEMA_VERSION", validation.schema_version)
    monkeypatch.setattr(runtime, "EXPECTED_IMPORT_MODE", validation.import_mode)
    monkeypatch.setattr(runtime, "EXPECTED_CONTENT_HASH", validation.content_hash)
    monkeypatch.setattr(runtime, "EXPECTED_AUTHOR_COUNT", validation.author_count)
    monkeypatch.setattr(runtime, "EXPECTED_WORK_COUNT", validation.work_count)
    monkeypatch.setattr(runtime, "EXPECTED_EDITION_COUNT", validation.edition_count)
    monkeypatch.setattr(runtime, "EXPECTED_SECTION_COUNT", validation.section_count)
    monkeypatch.setattr(runtime, "EXPECTED_CHUNK_COUNT", validation.chunk_count)
    monkeypatch.setattr(runtime, "EXPECTED_PASSAGE_LINK_COUNT", validation.passage_link_count)


def _clear_storage_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import textus_kb.theology_runtime as runtime

    monkeypatch.delenv(THEOLOGY_STORAGE_BUCKET_ENV_VAR, raising=False)
    monkeypatch.delenv(THEOLOGY_STORAGE_OBJECT_ENV_VAR, raising=False)
    monkeypatch.delenv(THEOLOGY_DATABASE_SHA256_ENV_VAR, raising=False)
    monkeypatch.setattr(runtime, "_theology_secret_value", lambda key: "")
    monkeypatch.setattr(runtime, "_configured_database_sha256", lambda: "")


def test_import_does_not_perform_network_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise AssertionError("Theology runtime import must not open Supabase.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)
    import textus_kb.theology_runtime as runtime

    assert callable(runtime.ensure_theology_database)
    assert runtime.ensure_theology_database is ensure_theology_database


def test_valid_cached_database_short_circuits_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_sample(tmp_path)
    _pin_to_database(monkeypatch, database)
    _clear_storage_config(monkeypatch)

    def boom() -> None:
        raise AssertionError("Supabase should not be called for a valid local DB.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    status = ensure_theology_database(database)
    assert status.available is True
    assert status.reason == "ok"


def test_explicit_path_does_not_download_even_if_env_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.sqlite3"
    monkeypatch.setenv(THEOLOGY_STORAGE_BUCKET_ENV_VAR, "should-not-use")
    monkeypatch.setenv(THEOLOGY_STORAGE_OBJECT_ENV_VAR, "theology.sqlite3")

    def boom() -> None:
        raise AssertionError("Explicit tmp path must not start a runtime download.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    status = ensure_theology_database(missing)
    assert status.available is False
    assert status.reason == "database_missing"


def test_missing_db_without_storage_config_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_config(monkeypatch)
    import textus_kb.theology_runtime as runtime

    monkeypatch.setattr(runtime, "DEFAULT_DATABASE_PATH", tmp_path / "theology.sqlite3")
    status = ensure_theology_database()
    assert status.available is False
    assert status.reason == "storage_not_configured"


def test_successful_mocked_private_storage_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    _clear_storage_config(monkeypatch)
    target = tmp_path / "dst" / "theology.sqlite3"
    payload = source.read_bytes()
    bucket = _FakeBucket(payload=payload)
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    status = ensure_theology_database(
        target,
        storage_bucket_id="test-theology-private",
        storage_object_path="theology.sqlite3",
        expected_database_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert status.available is True
    assert status.reason == "ok"
    assert target.is_file()
    assert target.read_bytes() == payload
    assert bucket.requested_paths == ["theology.sqlite3"]
    assert client.storage.requested_buckets == ["test-theology-private"]
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_blob_sha256_mismatch_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    _clear_storage_config(monkeypatch)
    target = tmp_path / "theology.sqlite3"
    bucket = _FakeBucket(payload=source.read_bytes())
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    status = ensure_theology_database(
        target,
        storage_bucket_id="test-theology-private",
        storage_object_path="theology.sqlite3",
        expected_database_sha256="0" * 64,
    )
    assert status.available is False
    assert status.reason == "database_checksum_mismatch"
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_invalid_sqlite_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_config(monkeypatch)
    broken = tmp_path / "theology.sqlite3"
    broken.write_text("not a sqlite database", encoding="utf-8")
    status = get_status(broken)
    assert status.available is False
    assert status.reason in {"database_unopenable", "schema_incompatible"}


def test_wrong_schema_version_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_sample(tmp_path)
    _pin_to_database(monkeypatch, database)
    _clear_storage_config(monkeypatch)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE store_metadata SET value = '99' WHERE key = 'schema_version'"
        )
        connection.commit()
    status = get_status(database)
    assert status.available is False
    assert status.reason == "schema_incompatible"


def test_wrong_content_hash_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_config(monkeypatch)
    database = _import_sample(tmp_path)
    status = get_status(database)
    assert status.available is False
    assert status.reason == "metadata_validation_failed"
    assert "content_hash" in status.detail


def test_wrong_author_work_edition_counts_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_config(monkeypatch)
    empty = tmp_path / "empty.sqlite3"
    create_empty_theology_database(empty)
    status = get_status(empty)
    assert status.available is False
    assert status.reason == "metadata_validation_failed"
    assert "author_count" in status.detail
    assert "work_count" in status.detail
    assert "edition_count" in status.detail


def test_wrong_section_chunk_passage_counts_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_config(monkeypatch)
    database = _import_sample(tmp_path)
    status = get_status(database)
    assert status.available is False
    assert status.reason == "metadata_validation_failed"
    assert "section_count" in status.detail
    assert "chunk_count" in status.detail
    assert "passage_link_count" in status.detail


def test_invalid_import_mode_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_config(monkeypatch)
    empty = tmp_path / "empty.sqlite3"
    create_empty_theology_database(empty)
    status = get_status(empty)
    assert status.available is False
    assert "import_mode" in status.detail


def test_download_error_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_config(monkeypatch)
    target = tmp_path / "theology.sqlite3"
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    status = ensure_theology_database(
        target,
        storage_bucket_id="test-theology-private",
        storage_object_path="theology.sqlite3",
    )
    assert status.available is False
    assert status.reason == "download_failed"
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_part_file_is_cleaned_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    _clear_storage_config(monkeypatch)
    target = tmp_path / "theology.sqlite3"
    payload = source.read_bytes()
    bucket = _FakeBucket(payload=payload)
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    original_replace = Path.replace

    def fail_replace(self: Path, target_path: Path) -> Path:  # type: ignore[override]
        if str(self).endswith(".part"):
            raise OSError("disk full")
        return original_replace(self, target_path)

    monkeypatch.setattr(Path, "replace", fail_replace)
    status = ensure_theology_database(
        target,
        storage_bucket_id="test-theology-private",
        storage_object_path="theology.sqlite3",
        expected_database_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert status.available is False
    assert status.reason == "write_failed"
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_valid_existing_database_survives_failed_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_sample(tmp_path)
    _pin_to_database(monkeypatch, database)
    original = database.read_bytes()

    def boom() -> None:
        raise AssertionError("Valid cached DB must not download.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)
    status = ensure_theology_database(
        database,
        storage_bucket_id="test-theology-private",
        storage_object_path="theology.sqlite3",
    )
    assert status.available is True
    assert database.read_bytes() == original


def test_invalid_local_is_not_replaced_by_failed_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "theology.sqlite3"
    target.write_bytes(b"corrupt-local")
    _clear_storage_config(monkeypatch)
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    status = ensure_theology_database(
        target,
        storage_bucket_id="test-theology-private",
        storage_object_path="theology.sqlite3",
    )
    assert status.available is False
    assert status.reason == "download_failed"
    assert target.read_bytes() == b"corrupt-local"


def test_atomic_replace_overwrites_invalid_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    _clear_storage_config(monkeypatch)
    target = tmp_path / "theology.sqlite3"
    target.write_bytes(b"corrupt-local")
    payload = source.read_bytes()
    bucket = _FakeBucket(payload=payload)
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    status = ensure_theology_database(
        target,
        storage_bucket_id="test-theology-private",
        storage_object_path="theology.sqlite3",
        expected_database_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert status.available is True
    assert target.read_bytes() == payload
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_local_blob_hash_mismatch_is_not_usable_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_sample(tmp_path)
    _pin_to_database(monkeypatch, database)
    _clear_storage_config(monkeypatch)

    def boom() -> None:
        raise AssertionError("Hash-mismatch cache must not download without storage kwargs.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)
    status = ensure_theology_database(
        database,
        expected_database_sha256="0" * 64,
    )
    assert status.available is False
    assert status.reason == "database_checksum_mismatch"
