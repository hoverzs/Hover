from __future__ import annotations

from pathlib import Path

import pytest

import ruf_bible_local_db as local_db
import ruf_bible_service as ruf


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    ruf.clear_ruf_cache()


def _seed_db(path: Path) -> None:
    conn = local_db.get_connection(path)
    local_db.upsert_chapter_verses(
        conn,
        book_code="JHN",
        book_abbr="Jn",
        ordinal=43,
        chapter=3,
        verses=[
            {"verse_number": 16, "text": "Mert úgy szerette Isten a világot."},
            {"verse_number": 17, "text": "Mert nem azért küldte el Isten a Fiút."},
        ],
    )
    conn.commit()
    conn.close()


def _seed_gen(path: Path) -> None:
    conn = local_db.get_connection(path)
    local_db.upsert_chapter_verses(
        conn,
        book_code="GEN",
        book_abbr="1Móz",
        ordinal=1,
        chapter=1,
        verses=[{"verse_number": 27, "text": "Megteremtette Isten az embert a maga képére."}],
    )
    conn.commit()
    conn.close()


def test_search_literal_treats_query_as_exact_phrase(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    # "Isten szerette" fordított sorrendben NEM egyezik szó szerint, mivel
    # a keresés mindig pontos kifejezésre illeszkedik (nem AND/OR).
    assert local_db.search_literal("Isten szerette", database_path=path) == []
    assert len(local_db.search_literal("úgy szerette", database_path=path)) == 1


def test_search_literal_survives_special_characters_without_crashing(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    # FTS5-ben operátor-jelentésű karakterek (kötőjel, idézőjel, kettőspont)
    # ne dobjanak kivételt — a keresés egyszerűen 0 találatot ad.
    assert local_db.search_literal('"fura- lekérdezés:1', database_path=path) == []


def test_search_literal_returns_highlighted_snippet(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    hits = local_db.search_literal("szerette", database_path=path)
    assert len(hits) == 1
    assert "**szerette**" in hits[0].snippet


def test_search_literal_book_codes_filters_by_testament(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)
    _seed_gen(path)

    ot_hits = local_db.search_literal("Isten", book_codes=["GEN"], database_path=path)
    assert {h.book_code for h in ot_hits} == {"GEN"}

    nt_hits = local_db.search_literal("Isten", book_codes=["JHN"], database_path=path)
    assert {h.book_code for h in nt_hits} == {"JHN"}

    all_hits = local_db.search_literal("Isten", database_path=path)
    assert {h.book_code for h in all_hits} == {"GEN", "JHN"}


def test_count_literal_matches_search_literal_result_size(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)
    _seed_gen(path)

    assert local_db.count_literal("Isten", database_path=path) == 3
    assert local_db.count_literal("Isten", book_codes=["GEN"], database_path=path) == 1


def test_count_literal_empty_query_is_zero(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)
    assert local_db.count_literal("", database_path=path) == 0


class _FakeBucket:
    def __init__(self, payload: bytes | None = None, error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.requested_paths: list[str] = []

    def download(self, path: str) -> bytes:
        self.requested_paths.append(path)
        if self._error is not None:
            raise self._error
        return self._payload or b""


class _FakeStorage:
    def __init__(self, bucket: _FakeBucket) -> None:
        self._bucket = bucket
        self.requested_buckets: list[str] = []

    def from_(self, bucket_id: str) -> _FakeBucket:
        self.requested_buckets.append(bucket_id)
        return self._bucket


class _FakeSupabaseClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self.storage = _FakeStorage(bucket)


def test_ensure_local_database_short_circuits_when_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    def boom():
        raise AssertionError("Nem kellett volna Supabase-t hívnia.")

    monkeypatch.setattr("supabase_client.get_supabase_client", boom, raising=False)

    assert local_db.ensure_local_database(path) is True


def test_ensure_local_database_downloads_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ruf.sqlite3"
    assert not path.exists()

    source = tmp_path / "source.sqlite3"
    _seed_db(source)
    payload = source.read_bytes()
    bucket = _FakeBucket(payload=payload)
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    ok = local_db.ensure_local_database(path)

    assert ok is True
    assert path.is_file()
    assert path.read_bytes() == payload
    assert bucket.requested_paths == [local_db.STORAGE_OBJECT_PATH]
    # Nincs ittmaradt .part ideiglenes fájl.
    assert not path.with_suffix(path.suffix + ".part").exists()


def test_ensure_local_database_returns_false_on_download_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ruf.sqlite3"
    bucket = _FakeBucket(error=ConnectionError("network down"))
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    assert local_db.ensure_local_database(path) is False
    assert not path.exists()


def test_ensure_local_database_returns_false_on_empty_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ruf.sqlite3"
    bucket = _FakeBucket(payload=b"")
    client = _FakeSupabaseClient(bucket)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    assert local_db.ensure_local_database(path) is False
    assert not path.exists()


def test_purge_database_removes_main_and_sibling_files(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)
    assert path.is_file()
    (tmp_path / "ruf.sqlite3-journal").write_text("stale journal")
    (tmp_path / "ruf.sqlite3-wal").write_text("stale wal")

    removed = local_db.purge_database(path)

    assert not path.exists()
    assert not (tmp_path / "ruf.sqlite3-journal").exists()
    assert not (tmp_path / "ruf.sqlite3-wal").exists()
    assert len(removed) == 3


def test_purge_database_on_nonexistent_db_is_noop(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.sqlite3"
    assert local_db.purge_database(path) == []


def test_ensure_schema_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    conn1 = local_db.get_connection(path)
    conn1.close()
    conn2 = local_db.get_connection(path)
    conn2.close()


def test_lookup_local_returns_verse_range(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    result = local_db.lookup_local("JHN", 3, 16, 16, database_path=path)
    assert result == [
        {"verse_number": 16, "number": 16, "text": "Mert úgy szerette Isten a világot.", "reference": ""}
    ]


def test_lookup_local_whole_chapter_when_no_verse_given(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    result = local_db.lookup_local("JHN", 3, None, None, database_path=path)
    assert result is not None
    assert [r["verse_number"] for r in result] == [16, 17]


def test_lookup_local_returns_none_for_partial_range(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    # 18. vers nincs a DB-ben -> a tartomány nem teljes -> None (API fallback)
    result = local_db.lookup_local("JHN", 3, 16, 18, database_path=path)
    assert result is None


def test_lookup_local_returns_none_when_db_missing(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.sqlite3"
    assert local_db.lookup_local("JHN", 3, 16, 16, database_path=path) is None


def test_search_literal_finds_matching_verse(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    hits = local_db.search_literal("szerette", database_path=path)
    assert len(hits) == 1
    assert hits[0].book_code == "JHN"
    assert hits[0].verse == 16


def test_search_literal_empty_query_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)

    assert local_db.search_literal("", database_path=path) == []


def test_search_literal_missing_db_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.sqlite3"
    assert local_db.search_literal("szeretet", database_path=path) == []


def test_chapter_status_transitions(tmp_path: Path) -> None:
    path = tmp_path / "ruf.sqlite3"
    conn = local_db.get_connection(path)
    assert local_db.get_chapter_status(conn, "JHN", 3) is None
    assert local_db.chapter_already_ok(conn, "JHN", 3) is False

    local_db.record_fetch_error(conn, "JHN", 3, "boom")
    conn.commit()
    assert local_db.get_chapter_status(conn, "JHN", 3) == "error"
    assert local_db.chapter_already_ok(conn, "JHN", 3) is False

    local_db.upsert_chapter_verses(
        conn,
        book_code="JHN",
        book_abbr="Jn",
        ordinal=43,
        chapter=3,
        verses=[{"verse_number": 16, "text": "..."}],
    )
    conn.commit()
    assert local_db.get_chapter_status(conn, "JHN", 3) == "ok"
    assert local_db.chapter_already_ok(conn, "JHN", 3) is True
    conn.close()


def test_fetch_ruf_passage_never_consults_local_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fő igehely-beviteli mező szándékosan mindig az élő API-t hívja.

    A helyi RÚF-szövegtár kizárólag a Konkordancia funkcióhoz készült
    (`ruf_bible_local_db.lookup_local` / `search_literal` közvetlen
    hívásán keresztül) — a meglévő `fetch_ruf_passage` útvonalat
    szándékosan nem érinti, még akkor sem, ha a helyi DB tartalmazná a
    kért igeszakaszt. Ez a teszt regresszió-védelem erre a döntésre.
    """
    path = tmp_path / "ruf.sqlite3"
    _seed_db(path)
    called = False
    real_lookup_local = local_db.lookup_local

    def spy_lookup(*args, **kwargs):
        nonlocal called
        called = True
        return real_lookup_local(*args, **{**kwargs, "database_path": path})

    monkeypatch.setattr(local_db, "lookup_local", spy_lookup)
    monkeypatch.delenv(ruf.SZENTIRAS_EU_API_KEY_NAME, raising=False)
    monkeypatch.setattr(ruf, "_streamlit_secret", lambda _name: "")

    result = ruf.fetch_ruf_passage("Jn 3,16")

    assert called is False
    # Nincs API-kulcs a tesztkörnyezetben -> a hívás az élő útvonalon
    # (helyesen) hibával tér vissza, de sosem local_db forrásból.
    assert result["success"] is False
    assert result.get("cache_status") != "local_db"
