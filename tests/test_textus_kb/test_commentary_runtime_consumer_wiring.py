"""Runtime-ensure wiring across ALL real Commentary-evidence consumers
(production storage round, follow-up: UI-independent ensure).

``textus_kb.commentary_runtime.ensure_status`` is the single choke point
every real consumer now calls (ld. its own module docstring). These
tests drive the ACTUAL consumer entry points end to end -- never
monkeypatching ``commentary_runtime.get_status``/``ensure_status``
themselves -- with a mocked Supabase Storage client standing in for the
network, proving:

- whichever module the user reaches FIRST (Exegézis, Eredeti szöveg, or
  the Commentary reader tab) triggers provisioning on its own, with no
  dependency on the reader tab having been opened first;
- a valid local DB short-circuits every consumer with zero network calls;
- a remote failure still leaves every consumer in its existing
  fail-closed shape (never a crash, never partial/fabricated evidence);
- multiple consumers used within one process only ever download once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bible_engine.original_language_analysis import build_original_text_commentary_block
from textus_kb.grounded_generation import (
    REASON_SOURCE_UNAVAILABLE,
    STATUS_FALLBACK,
    prepare_grounded_provider_prompt,
)
from textus_kb.importers.commentary_sqlite import (
    import_commentary_sqlite,
    validate_commentary_database,
)

import commentary_ui as cu

FIXTURE_PATH = Path("tests/fixtures/kb/commentary_v1_sample.json")
PASSAGE_DOTTED = "John.3.16"
PASSAGE_HUMAN = "John 3:16"

TEST_BUCKET_ENV = "TEXTUS_COMMENTARY_DB_STORAGE_BUCKET"
TEST_OBJECT_ENV = "TEXTUS_COMMENTARY_DB_STORAGE_OBJECT"


class _FakeBucket:
    def __init__(self, payload: bytes = b"", error: BaseException | None = None) -> None:
        self.payload = payload
        self.error = error
        self.download_calls = 0

    def download(self, _object_path: str) -> bytes:
        self.download_calls += 1
        if self.error:
            raise self.error
        return self.payload


class _FakeStorage:
    def __init__(self, bucket: _FakeBucket) -> None:
        self.bucket = bucket

    def from_(self, _bucket_id: str) -> _FakeBucket:
        return self.bucket


class _FakeSupabaseClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self.storage = _FakeStorage(bucket)


def _source_db(tmp_path: Path) -> Path:
    database = tmp_path / "src" / "commentary.sqlite3"
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


@pytest.fixture()
def _isolated_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirects the module-level production default path -- imported by
    both ``commentary_runtime`` and ``commentary_repository`` from the
    same ``textus_kb.importers.commentary_sqlite`` constant -- to an
    empty tmp location, so these tests never touch (or get contaminated
    by) the real ``data/generated/commentary.sqlite3``."""
    import textus_kb.commentary_runtime as runtime
    import textus_kb.repositories.commentary_repository as repo_module

    target = tmp_path / "dst" / "commentary.sqlite3"
    monkeypatch.setattr(runtime, "DEFAULT_DATABASE_PATH", target)
    monkeypatch.setattr(repo_module, "DEFAULT_DATABASE_PATH", target)
    return target


@pytest.fixture()
def _configured_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[_FakeBucket, Path]:
    """A working, pinned, mocked remote store -- storage env vars set (as
    a real deployment's secrets would be), Supabase client mocked to
    serve the fixture DB's bytes. Returns the fake bucket (to assert
    download call counts) and the payload's source path."""
    source = _source_db(tmp_path)
    _pin_to_database(monkeypatch, source)
    monkeypatch.setenv(TEST_BUCKET_ENV, "test-commentary-private")
    monkeypatch.setenv(TEST_OBJECT_ENV, "commentary.sqlite3")
    bucket = _FakeBucket(payload=source.read_bytes())
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )
    return bucket, source


# --- "first Commentary need" from each consumer, no prior reader-tab open --


def test_exegesis_opened_first_triggers_ensure(
    _isolated_default_path: Path,
    _configured_download: tuple[_FakeBucket, Path],
) -> None:
    bucket, _source = _configured_download
    assert not _isolated_default_path.exists()

    prep = prepare_grounded_provider_prompt(
        production_prompt="PROD",
        passage=PASSAGE_DOTTED,
        module="exegesis",
        grounded_enabled=True,
        use_cache=False,
    )
    assert bucket.download_calls == 1
    assert _isolated_default_path.is_file()
    assert "[COMMENTARY SOURCES]" in prep.provider_prompt


def test_original_text_opened_first_triggers_ensure(
    _isolated_default_path: Path,
    _configured_download: tuple[_FakeBucket, Path],
) -> None:
    bucket, _source = _configured_download
    assert not _isolated_default_path.exists()

    block = build_original_text_commentary_block(PASSAGE_HUMAN)
    assert bucket.download_calls == 1
    assert _isolated_default_path.is_file()
    assert block != ""


def test_commentary_ui_opened_first_triggers_ensure(
    _isolated_default_path: Path,
    _configured_download: tuple[_FakeBucket, Path],
) -> None:
    bucket, _source = _configured_download
    assert not _isolated_default_path.exists()

    status = cu._get_status()
    assert status.available is True
    assert bucket.download_calls == 1
    assert _isolated_default_path.is_file()


# --- idempotency: valid local DB never re-downloads -------------------


def test_valid_local_db_no_remote_download_via_exegesis(
    _isolated_default_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _source_db(tmp_path)
    _isolated_default_path.parent.mkdir(parents=True, exist_ok=True)
    _isolated_default_path.write_bytes(source.read_bytes())

    def boom() -> None:
        raise AssertionError("Supabase must not be called for an already-valid local DB.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    prep = prepare_grounded_provider_prompt(
        production_prompt="PROD",
        passage=PASSAGE_DOTTED,
        module="exegesis",
        grounded_enabled=True,
        use_cache=False,
    )
    assert "[COMMENTARY SOURCES]" in prep.provider_prompt


# --- remote failure: every consumer stays fail-closed, never crashes ---


def test_remote_failure_commentary_module_is_fail_closed(
    _isolated_default_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(TEST_BUCKET_ENV, "test-commentary-private")
    monkeypatch.setenv(TEST_OBJECT_ENV, "commentary.sqlite3")
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    prep = prepare_grounded_provider_prompt(
        production_prompt="PROD",
        passage=PASSAGE_DOTTED,
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert prep.status == STATUS_FALLBACK
    assert prep.fallback_reason == REASON_SOURCE_UNAVAILABLE
    assert prep.provider_prompt == "PROD"


def test_remote_failure_exegesis_stays_ungrounded_supplement_only(
    _isolated_default_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TEST_BUCKET_ENV, "test-commentary-private")
    monkeypatch.setenv(TEST_OBJECT_ENV, "commentary.sqlite3")
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    prep = prepare_grounded_provider_prompt(
        production_prompt="PROD",
        passage=PASSAGE_DOTTED,
        module="exegesis",
        grounded_enabled=True,
        use_cache=False,
    )
    assert "[COMMENTARY SOURCES]" not in prep.provider_prompt


def test_remote_failure_original_text_block_is_fail_closed(
    _isolated_default_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TEST_BUCKET_ENV, "test-commentary-private")
    monkeypatch.setenv(TEST_OBJECT_ENV, "commentary.sqlite3")
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    assert build_original_text_commentary_block(PASSAGE_HUMAN) == ""


def test_remote_failure_commentary_ui_stays_fail_closed(
    _isolated_default_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TEST_BUCKET_ENV, "test-commentary-private")
    monkeypatch.setenv(TEST_OBJECT_ENV, "commentary.sqlite3")
    bucket = _FakeBucket(error=ConnectionError("network down"))
    monkeypatch.setattr(
        "supabase_client.get_supabase_client", lambda: _FakeSupabaseClient(bucket)
    )

    status = cu._get_status()
    assert status.available is False
    assert status.reason == "download_failed"


# --- one process, several consumers -> exactly one download -----------


def test_multiple_consumers_one_process_download_once(
    _isolated_default_path: Path,
    _configured_download: tuple[_FakeBucket, Path],
) -> None:
    bucket, _source = _configured_download

    first = prepare_grounded_provider_prompt(
        production_prompt="PROD",
        passage=PASSAGE_DOTTED,
        module="exegesis",
        grounded_enabled=True,
        use_cache=False,
    )
    assert bucket.download_calls == 1

    block = build_original_text_commentary_block(PASSAGE_HUMAN)
    assert bucket.download_calls == 1  # still just the one, from above

    status = cu._get_status()
    assert bucket.download_calls == 1  # still just the one

    assert "[COMMENTARY SOURCES]" in first.provider_prompt
    assert block != ""
    assert status.available is True
