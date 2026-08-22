from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bible_engine.hymn_repository import (
    EXPECTED_ERE_SOURCE_CHECKSUM,
    EXPECTED_RE21_SOURCE_CHECKSUM,
    ensure_hymn_database,
    get_hymn_by_id,
    get_hymn_by_number,
    get_hymn_candidates,
    get_status,
    list_hymnals,
    search_hymns,
    validate_hymn_ids,
)
from bible_engine.hymn_sqlite import (
    HymnalSourceConfig,
    create_schema,
    import_dtx_hymnal_database,
    import_hymnals_database,
)


ROOT = Path(__file__).resolve().parents[1]
ERE_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"
RE21_SOURCE = ROOT / "data" / "raw" / "hymnals" / "RE21_master.docx"


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


@pytest.fixture(scope="module")
def ere_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not ERE_SOURCE.exists():
        pytest.skip("Full ERE.dtx is local raw data")
    database = tmp_path_factory.mktemp("hymn_repository") / "hymns.sqlite3"
    import_dtx_hymnal_database(ERE_SOURCE, database, hymnal_code="ERE")
    return database


def test_status_available_for_valid_database(ere_database: Path) -> None:
    status = get_status(ere_database)

    assert status.available is True
    assert status.reason == "ok"


def test_status_missing_database(tmp_path: Path) -> None:
    status = get_status(tmp_path / "missing.sqlite3")

    assert status.available is False
    assert status.reason == "database_missing"


def test_status_rejects_corrupt_database(tmp_path: Path) -> None:
    database = tmp_path / "hymns.sqlite3"
    database.write_bytes(b"not sqlite")

    status = get_status(database)

    assert status.available is False
    assert status.reason in {"database_unopenable", "database_invalid"}


def test_status_rejects_schema_with_wrong_metadata(tmp_path: Path) -> None:
    database = tmp_path / "hymns.sqlite3"
    with sqlite3.connect(database) as connection:
        create_schema(connection)
        connection.execute(
            """
            INSERT INTO hymnals(code, title, dtx_code, source_format, source_version, source_checksum, imported_at)
            VALUES ('ERE', 'Bad', 'E.Ref', 'DiaTar DTX', '', 'bad', 'now')
            """
        )
        connection.execute("INSERT INTO import_meta(key, value) VALUES ('schema_version', '1')")
        connection.execute("INSERT INTO import_meta(key, value) VALUES ('parser_warning_count', '0')")
        connection.commit()

    status = get_status(database)

    assert status.available is False
    assert status.reason == "metadata_validation_failed"


def test_list_hymnals_returns_ere_metadata(ere_database: Path) -> None:
    hymnals = list_hymnals(ere_database)

    assert [h.code for h in hymnals] == ["ERE"]
    assert hymnals[0].title == "Erdélyi Református Énekeskönyv"
    assert hymnals[0].source_checksum == EXPECTED_ERE_SOURCE_CHECKSUM


@pytest.mark.skipif(
    not (ERE_SOURCE.exists() and RE21_SOURCE.exists()),
    reason="Full ERE.dtx and RÉ21 DOCX are local raw data",
)
def test_status_and_repository_reads_combined_ere_re21_database(tmp_path: Path) -> None:
    database = tmp_path / "hymns.sqlite3"
    import_hymnals_database(
        (
            HymnalSourceConfig(code="ERE", source_path=ERE_SOURCE, source_format="dtx"),
            HymnalSourceConfig(
                code="RE21",
                source_path=RE21_SOURCE,
                source_format="docx",
                title="Református Énekeskönyv 2021",
            ),
        ),
        database,
    )

    status = get_status(database)
    hymnals = list_hymnals(database)
    re21_hymn = get_hymn_by_number("RE21", 360, database_path=database)
    valid = validate_hymn_ids(["RE21:360", "RE21:9999"], database_path=database)
    hits = search_hymns("úrvacsora", hymnal_codes=["RE21"], database_path=database)

    assert status.available is True
    assert status.reason == "ok"
    assert [h.code for h in hymnals] == ["ERE", "RE21"]
    assert hymnals[1].source_checksum == EXPECTED_RE21_SOURCE_CHECKSUM
    assert re21_hymn is not None
    assert re21_hymn.hymn_id == "RE21:360"
    assert re21_hymn.first_line == "Jer, lássuk az Úr keresztjét,"
    assert set(valid) == {"RE21:360"}
    assert hits
    assert all(hit.hymn.hymnal_code == "RE21" for hit in hits)


def test_representative_lookups_return_database_records(ere_database: Path) -> None:
    hymn_1 = get_hymn_by_number("ERE", 1, database_path=ere_database)
    hymn_119 = get_hymn_by_number("ERE", 119, database_path=ere_database)
    hymn_254a = get_hymn_by_number("ERE", 254, "a", database_path=ere_database)
    hymn_254b = get_hymn_by_number("ERE", 254, "b", database_path=ere_database)
    hymn_504 = get_hymn_by_number("ERE", 504, database_path=ere_database)

    assert hymn_1 is not None
    assert hymn_1.hymn_id == "ERE:1"
    assert hymn_1.display_number == "1"
    assert hymn_1.first_line == "Aki nem jár hitlenek tanácsán,"
    assert hymn_1.section == ""

    assert hymn_119 is not None
    assert hymn_119.hymn_id == "ERE:119"
    assert hymn_119.title == "Az Úr Igéjének és törvényének dicsősége"

    assert hymn_254a is not None
    assert hymn_254a.hymn_id == "ERE:254a"
    assert hymn_254a.display_number == "254a"
    assert hymn_254a.first_line == "Erős vár a mi Istenünk,"

    assert hymn_254b is not None
    assert hymn_254b.hymn_id == "ERE:254b"
    assert hymn_254b.display_number == "254b"
    assert hymn_254b.first_line == "Erős várunk nékünk az Isten,"

    assert hymn_504 is not None
    assert hymn_504.hymn_id == "ERE:504"
    assert hymn_504.section == "Kánonok"
    assert hymn_504.parent_section == "Énekek bibliaórákra, vasárnapi iskolai és családi alkalmakra"
    assert hymn_504.first_line == "Áldjon meg téged, áldjon az Úr,"


def test_missing_hymn_number_returns_none(ere_database: Path) -> None:
    assert get_hymn_by_number("ERE", 999, database_path=ere_database) is None


def test_hymnal_filtered_fts(ere_database: Path) -> None:
    hits = search_hymns("Erős vár a mi Istenünk", hymnal_codes=["ERE"], database_path=ere_database)
    no_hits = search_hymns("Erős vár a mi Istenünk", hymnal_codes=["RÉ21"], database_path=ere_database)

    assert hits
    assert hits[0].hymn.hymn_id == "ERE:254a"
    assert no_hits == []


def test_get_hymn_candidates_returns_records_without_stanza_text(ere_database: Path) -> None:
    candidates = get_hymn_candidates("gyönyörködik az Úr törvényében", ["ERE"], database_path=ere_database)

    assert candidates
    assert candidates[0].hymn_id == "ERE:1"
    assert not hasattr(candidates[0], "text")
    assert not hasattr(candidates[0], "stanzas")


def test_hymn_id_validation_accepts_only_database_ids(ere_database: Path) -> None:
    valid = validate_hymn_ids(
        ["ERE:1", "ERE:254a", "ERE:does-not-exist", "bad-format", "RÉ21:1"],
        database_path=ere_database,
    )

    assert set(valid) == {"ERE:1", "ERE:254a"}
    assert valid["ERE:254a"].first_line == "Erős vár a mi Istenünk,"


def test_get_hymn_by_id_rejects_false_id(ere_database: Path) -> None:
    assert get_hymn_by_id("ERE:254a", ere_database) is not None
    assert get_hymn_by_id("ERE:999", ere_database) is None
    assert get_hymn_by_id("not-a-real-id", ere_database) is None


def test_unavailable_database_does_not_generate_fallback(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"

    assert get_status(missing).available is False
    assert get_hymn_by_number("ERE", 1, database_path=missing) is None
    assert search_hymns("Erős vár", hymnal_codes=["ERE"], database_path=missing) == []
    assert validate_hymn_ids(["ERE:1"], database_path=missing) == {}


def test_ensure_short_circuits_when_valid_database_exists(
    ere_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom():
        raise AssertionError("Supabase should not be called for a valid local DB.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    status = ensure_hymn_database(ere_database)

    assert status.available is True
    assert status.reason == "ok"


def test_ensure_downloads_and_validates_missing_database(
    tmp_path: Path, ere_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "hymns.sqlite3"
    bucket = _FakeBucket(payload=ere_database.read_bytes())
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)
    monkeypatch.setattr("bible_engine.hymn_repository._configured_database_sha256", lambda: "")

    status = ensure_hymn_database(
        target,
        storage_bucket_id="test-hymns-private",
        storage_object_path="hymns.sqlite3",
    )

    assert status.available is True
    assert status.reason == "ok"
    assert target.is_file()
    assert bucket.requested_paths == ["hymns.sqlite3"]
    assert client.storage.requested_buckets == ["test-hymns-private"]
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_ensure_rejects_download_checksum_mismatch(
    tmp_path: Path, ere_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "hymns.sqlite3"
    bucket = _FakeBucket(payload=ere_database.read_bytes())
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    status = ensure_hymn_database(
        target,
        storage_bucket_id="test-hymns-private",
        storage_object_path="hymns.sqlite3",
        expected_database_sha256="0" * 64,
    )

    assert status.available is False
    assert status.reason == "database_checksum_mismatch"
    assert not target.exists()


def test_ensure_returns_unavailable_on_download_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "hymns.sqlite3"
    bucket = _FakeBucket(error=ConnectionError("network down"))
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)
    monkeypatch.setattr("bible_engine.hymn_repository._configured_database_sha256", lambda: "")

    status = ensure_hymn_database(
        target,
        storage_bucket_id="test-hymns-private",
        storage_object_path="hymns.sqlite3",
    )

    assert status.available is False
    assert status.reason == "download_failed"
    assert not target.exists()


def test_ensure_requires_storage_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEXTUS_HYMN_DB_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("TEXTUS_HYMN_DB_STORAGE_OBJECT", raising=False)
    monkeypatch.setattr("bible_engine.hymn_repository._hymn_secret_value", lambda key: "")

    status = ensure_hymn_database(tmp_path / "hymns.sqlite3")

    assert status.available is False
    assert status.reason == "storage_not_configured"
