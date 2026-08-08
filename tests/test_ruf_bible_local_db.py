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
