"""Commentary runtime ensure/provisioning tests (production storage round).

Mirrors ``test_theology_runtime.py``'s conventions (fake Supabase storage,
``_pin_to_database``-style monkeypatching, ``_clear_storage_config``
isolation) with one deliberate asymmetry: ``get_status``/``_validate_
database`` stay LENIENT (schema-version-only, unchanged from before this
round) so the large pre-existing Commentary test suite -- which asserts
``status.available is True`` against small synthetic DBs with no
invariant monkeypatching -- keeps passing unmodified. The STRICT
production-pin check (schema + exact section/chunk/passage_link counts +
content_hash) only ever runs inside ``ensure_commentary_database``'s own
post-download validation.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from textus_kb.importers.commentary_sqlite import (
    import_commentary_sqlite,
    validate_commentary_database,
)
from textus_kb.commentary_runtime import (
    COMMENTARY_DATABASE_PATH_ENV_VAR,
    COMMENTARY_DATABASE_SHA256_ENV_VAR,
    COMMENTARY_STORAGE_BUCKET_ENV_VAR,
    COMMENTARY_STORAGE_OBJECT_ENV_VAR,
    EXPECTED_CHUNK_COUNT,
    EXPECTED_CONTENT_HASH,
    EXPECTED_CONTRIBUTOR_COUNT,
    EXPECTED_EDITION_COUNT,
    EXPECTED_IMPORT_MODE,
    EXPECTED_PASSAGE_LINK_COUNT,
    EXPECTED_SECTION_COUNT,
    EXPECTED_WORK_COUNT,
    ensure_commentary_database,
    get_status,
)

FIXTURE_PATH = Path("tests/fixtures/kb/commentary_v1_sample.json")


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
    database = tmp_path / "commentary.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    import_commentary_sqlite(fixture_path=FIXTURE_PATH, database_path=database)
    return database


def _pin_to_database(monkeypatch: pytest.MonkeyPatch, database: Path) -> None:
    import textus_kb.commentary_runtime as runtime

    validation = validate_commentary_database(database)
    monkeypatch.setattr(runtime, "EXPECTED_IMPORT_MODE", validation.import_mode)
    monkeypatch.setattr(runtime, "EXPECTED_CONTENT_HASH", validation.content_hash)
    monkeypatch.setattr(runtime, "EXPECTED_CONTRIBUTOR_COUNT", validation.contributor_count)
    monkeypatch.setattr(runtime, "EXPECTED_WORK_COUNT", validation.work_count)
    monkeypatch.setattr(runtime, "EXPECTED_EDITION_COUNT", validation.edition_count)
    monkeypatch.setattr(runtime, "EXPECTED_SECTION_COUNT", validation.section_count)
    monkeypatch.setattr(runtime, "EXPECTED_CHUNK_COUNT", validation.chunk_count)
    monkeypatch.setattr(runtime, "EXPECTED_PASSAGE_LINK_COUNT", validation.passage_link_count)


def _clear_storage_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import textus_kb.commentary_runtime as runtime

    monkeypatch.delenv(COMMENTARY_STORAGE_BUCKET_ENV_VAR, raising=False)
    monkeypatch.delenv(COMMENTARY_STORAGE_OBJECT_ENV_VAR, raising=False)
    monkeypatch.delenv(COMMENTARY_DATABASE_SHA256_ENV_VAR, raising=False)
    monkeypatch.delenv(COMMENTARY_DATABASE_PATH_ENV_VAR, raising=False)
    monkeypatch.setattr(runtime, "_commentary_secret_value", lambda key: "")
    monkeypatch.setattr(runtime, "_configured_database_sha256", lambda: "")


@pytest.fixture(autouse=True)
def _isolate_storage_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runtime tests hermetic from local env / [commentary_database] secrets."""
    _clear_storage_config(monkeypatch)


# --- get_status stays lenient (unchanged, pre-existing contract) ----------


def test_get_status_accepts_small_synthetic_db_without_invariant_check(
    tmp_path: Path,
) -> None:
    """The large pre-existing Commentary test suite relies on this: a tiny
    fixture-built DB, nowhere near production section/chunk counts, must
    still report ``available=True`` from the plain ``get_status`` -- this
    round must not tighten that contract."""
    database = _import_sample(tmp_path)
    status = get_status(database)
    assert status.available is True
    assert status.reason == "ok"


def test_get_status_missing_db() -> None:
    status = get_status(Path("does/not/exist/commentary.sqlite3"))
    assert status.available is False
    assert status.reason == "database_missing"


# --- ensure_commentary_database: network-safety guard ---------------------


def test_import_does_not_perform_network_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise AssertionError("Commentary runtime import must not open Supabase.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)
    import textus_kb.commentary_runtime as runtime

    assert callable(runtime.ensure_commentary_database)
    assert runtime.ensure_commentary_database is ensure_commentary_database


def test_explicit_path_does_not_download_even_if_env_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.sqlite3"
    monkeypatch.setenv(COMMENTARY_STORAGE_BUCKET_ENV_VAR, "should-not-use")
    monkeypatch.setenv(COMMENTARY_STORAGE_OBJECT_ENV_VAR, "commentary.sqlite3")

    def boom() -> None:
        raise AssertionError("Explicit tmp path must not start a runtime download.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    status = ensure_commentary_database(missing)
    assert status.available is False
    assert status.reason == "database_missing"


def test_env_path_does_not_download_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-commentary.sqlite3"
    monkeypatch.setenv(COMMENTARY_DATABASE_PATH_ENV_VAR, str(missing))

    def boom() -> None:
        raise AssertionError("Env path override must not start a runtime download.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)
    status = ensure_commentary_database()
    assert status.available is False
    assert status.reason == "database_missing"
    assert Path(status.database_path) == missing


# --- ensure_commentary_database: cache short-circuit (item 5: no redundant download) --


def test_valid_cached_database_matching_pin_short_circuits_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_sample(tmp_path)
    _pin_to_database(monkeypatch, database)
    _clear_storage_config(monkeypatch)

    def boom() -> None:
        raise AssertionError("Supabase should not be called for a strictly valid local DB.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    status = ensure_commentary_database(database)
    assert status.available is True
    assert status.reason == "ok"


def test_valid_but_unpinned_cached_database_triggers_download_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A local DB at the DEFAULT path that is schema-valid (passes
    ``get_status``) but does NOT match the pinned production invariants
    (e.g. a stale/partial build) must NOT be silently treated as good
    enough by ``ensure_commentary_database`` -- it should attempt to
    fetch the real pinned artifact instead, exactly like a missing file
    would (here: falling through to ``storage_not_configured`` since no
    storage is configured in this test)."""
    import textus_kb.commentary_runtime as runtime

    database = _import_sample(tmp_path)
    monkeypatch.setattr(runtime, "DEFAULT_DATABASE_PATH", database)
    # Deliberately do NOT pin EXPECTED_* to this database, no explicit
    # database_path (so the "explicit path never downloads" guard does
    # not apply), and storage left unconfigured -- ensure_commentary_
    # database must reject the local file's invariants and fall through
    # to storage_not_configured (not silently return available=True for
    # the wrong DB).
    status = ensure_commentary_database()
    assert status.available is False
    assert status.reason == "storage_not_configured"


def test_missing_db_without_storage_config_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import textus_kb.commentary_runtime as runtime

    monkeypatch.setattr(runtime, "DEFAULT_DATABASE_PATH", tmp_path / "commentary.sqlite3")
    status = ensure_commentary_database()
    assert status.available is False
    assert status.reason == "storage_not_configured"


# --- ensure_commentary_database: download + atomic install ----------------


def test_successful_mocked_private_storage_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    target = tmp_path / "dst" / "commentary.sqlite3"
    payload = source.read_bytes()
    bucket = _FakeBucket(payload=payload)
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
        expected_database_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert status.available is True
    assert status.reason == "ok"
    assert target.is_file()
    assert target.read_bytes() == payload
    assert bucket.requested_paths == ["commentary.sqlite3"]
    assert client.storage.requested_buckets == ["test-commentary-private"]
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_blob_sha256_mismatch_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    target = tmp_path / "commentary.sqlite3"
    bucket = _FakeBucket(payload=source.read_bytes())
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
        expected_database_sha256="0" * 64,
    )
    assert status.available is False
    assert status.reason == "database_checksum_mismatch"
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_downloaded_wrong_invariants_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema-valid but wrong-content download (e.g. wrong corpus
    version) must never become the active database, even without a
    configured SHA256 pin -- caught by the post-download invariant
    check (section/chunk/passage_link counts + content_hash)."""
    wrong = _import_sample(tmp_path / "src")
    target = tmp_path / "commentary.sqlite3"
    bucket = _FakeBucket(payload=wrong.read_bytes())
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
    )
    assert status.available is False
    assert status.reason == "metadata_validation_failed"
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_download_error_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "commentary.sqlite3"
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
    )
    assert status.available is False
    assert status.reason == "download_failed"
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_download_empty_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "commentary.sqlite3"
    bucket = _FakeBucket(payload=b"")
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
    )
    assert status.available is False
    assert status.reason == "download_empty"


def test_part_file_is_cleaned_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    target = tmp_path / "commentary.sqlite3"
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
    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
        expected_database_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert status.available is False
    assert status.reason == "write_failed"
    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_atomic_replace_overwrites_invalid_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    target = tmp_path / "commentary.sqlite3"
    target.write_bytes(b"corrupt-local")
    payload = source.read_bytes()
    bucket = _FakeBucket(payload=payload)
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
        expected_database_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert status.available is True
    assert target.read_bytes() == payload
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_invalid_local_is_not_replaced_by_failed_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "commentary.sqlite3"
    target.write_bytes(b"corrupt-local")
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    status = ensure_commentary_database(
        target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
    )
    assert status.available is False
    assert status.reason == "download_failed"
    assert target.read_bytes() == b"corrupt-local"


# --- production pin sanity -------------------------------------------------


def test_production_pin_matches_current_final_build() -> None:
    assert EXPECTED_IMPORT_MODE == "combined_commentary_thml"
    assert EXPECTED_CONTRIBUTOR_COUNT == 27
    assert EXPECTED_WORK_COUNT == 155
    assert EXPECTED_EDITION_COUNT == 177
    assert EXPECTED_SECTION_COUNT == 57331
    assert EXPECTED_CHUNK_COUNT == 41955
    assert EXPECTED_PASSAGE_LINK_COUNT == 54162
    assert len(EXPECTED_CONTENT_HASH) == 64


def test_local_production_artifact_matches_pin_if_present() -> None:
    """If the locally rebuilt production DB happens to be present in this
    checkout, it must satisfy the exact strict pin used in production --
    this is the direct, repo-local check that the pinned constants in
    ``commentary_runtime.py`` are not stale relative to the real build."""
    candidate = Path("data/generated/commentary.sqlite3")
    if not candidate.is_file():
        pytest.skip("local Commentary production artifact not present")
    status = ensure_commentary_database(candidate)
    assert status.available is True
    assert status.reason == "ok"
