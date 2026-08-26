"""Calvin Institutes CCEL/ThML pilot importer tests."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from textus_kb.importers.ccel_thml import (
    ALLOWED_BOOK_DIV1_IDS,
    CcelThmlImportError,
    import_ccel_institutes_thml,
    parse_ccel_institutes_thml,
)
from textus_kb.importers.theology_sqlite import hash_theology_document
from textus_kb.repositories.theology_repository import TheologyRepository

FIXTURE_PATH = Path("tests/fixtures/kb/ccel_institutes_thml_min.xml")
REAL_XML_PATH = (
    Path(os.environ.get("TEMP", os.environ.get("TMP", "")))
    / "textus-theology-ccel-audit"
    / "www.ccel.org_ccel_calvin_institutes.xml.bin"
)


def _import(tmp_path: Path, xml_path: Path | None = None):
    database = tmp_path / "theology.sqlite3"
    return import_ccel_institutes_thml(
        xml_path or FIXTURE_PATH,
        database_path=database,
    )


def _write_xml(tmp_path: Path, xml_text: str) -> Path:
    path = tmp_path / "institutes.xml"
    path.write_text(xml_text, encoding="utf-8")
    return path


def _fixture_text() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _query_all(database: Path, sql: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(database) as connection:
        return list(connection.execute(sql, params))


def test_fixture_is_markup_derived_and_small() -> None:
    text = _fixture_text()
    assert "CCEL Calvin Institutes markup-derived minimal fixture" in text
    assert len(text.encode("utf-8")) < 12_000
    assert "Our wisdom, in so far as it ought to be deemed true" not in text


def test_external_dtd_is_not_fetched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[object] = []

    def boom(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("network access attempted during ThML parse")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("socket.create_connection", boom)
    document, extras = parse_ccel_institutes_thml(FIXTURE_PATH)
    assert calls == []
    assert extras["books_imported"] == 4
    assert document["editions"][0]["corpus"] == "ccel"


def test_internal_dtd_entity_is_not_resolved(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-DTD-PAYLOAD", encoding="utf-8")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ThML [
  <!ENTITY xxe SYSTEM "{secret.as_uri()}">
]>
<ThML>
  <ThML.body>
    <div1 title="BOOK FIRST." id="iii"><div2 title="CHAPTER 1." id="iii.ii">
      <p id="iii.ii-p1">1. Leaked &xxe; text.</p>
    </div2></div1>
    <div1 title="BOOK SECOND." id="iv"><div2 title="CHAPTER 1." id="iv.i">
      <p id="iv.i-p1">1. Book two.</p>
    </div2></div1>
    <div1 title="BOOK THIRD." id="v"><div2 title="CHAPTER 1." id="v.i">
      <p id="v.i-p1">1. Book three.</p>
    </div2></div1>
    <div1 title="BOOK FOURTH." id="vi"><div2 title="CHAPTER 1." id="vi.i">
      <p id="vi.i-p1">1. Book four.</p>
    </div2></div1>
  </ThML.body>
</ThML>
"""
    path = _write_xml(tmp_path, xml)
    with pytest.raises(CcelThmlImportError, match="Invalid ThML XML"):
        parse_ccel_institutes_thml(path)


def test_malformed_xml_raises_controlled_error(tmp_path: Path) -> None:
    path = _write_xml(tmp_path, "<ThML><ThML.body>")
    with pytest.raises(CcelThmlImportError, match="Invalid ThML XML"):
        parse_ccel_institutes_thml(path)


def test_allowlisted_books_only_and_forbidden_blocks_skipped(tmp_path: Path) -> None:
    report = _import(tmp_path)
    assert report.books_imported == 4
    assert tuple(ALLOWED_BOOK_DIV1_IDS) == ("iii", "iv", "v", "vi")
    assert report.skipped_top_level_ids == ("i", "ii", "vii", "viii")

    book_ids = {
        row[0]
        for row in _query_all(
            report.database_path,
            "SELECT section_id FROM sections WHERE section_type = 'book'",
        )
    }
    assert book_ids == {
        "ccel.calvin.institutes.iii",
        "ccel.calvin.institutes.iv",
        "ccel.calvin.institutes.v",
        "ccel.calvin.institutes.vi",
    }

    locators = [
        row[0]
        for row in _query_all(report.database_path, "SELECT source_locator FROM chunks")
    ]
    joined = "\n".join(
        row[0] for row in _query_all(report.database_path, "SELECT plain_text FROM chunks")
    )
    assert all(locator.startswith("ccel:calvin/institutes#iii.") or
               locator.startswith("ccel:calvin/institutes#v.") or
               locator.startswith("ccel:calvin/institutes#vi.")
               for locator in locators)
    assert "SYNTHETIC TITLE PAGE" not in joined
    assert "John Murray" not in joined
    assert "Synthetic aphorism" not in joined
    assert "Genesis" not in joined
    argument_chunks = _query_all(
        report.database_path,
        "SELECT source_locator FROM chunks WHERE source_locator LIKE ?",
        ("ccel:calvin/institutes#iv.%",),
    )
    assert argument_chunks == []


def test_missing_allowlisted_book_is_import_error(tmp_path: Path) -> None:
    xml = _fixture_text().replace(
        """    <div1 title="BOOK FOURTH." n="iv" id="vi">
      <div2 title="CHAPTER 1." n="ii" id="vi.ii">
        <p id="vi.ii-p1">1. Synthetic book four section.</p>
      </div2>
    </div1>""",
        "",
    )
    path = _write_xml(tmp_path, xml)
    with pytest.raises(CcelThmlImportError, match="missing div1 id\\(s\\): vi"):
        parse_ccel_institutes_thml(path)


def test_duplicate_allowlisted_book_is_import_error(tmp_path: Path) -> None:
    xml = _fixture_text().replace(
        'id="iv"',
        'id="iii"',
        1,
    )
    path = _write_xml(tmp_path, xml)
    with pytest.raises(CcelThmlImportError, match="Duplicate allowlisted book id"):
        parse_ccel_institutes_thml(path)


def test_chapter_hierarchy_and_section_boundaries(tmp_path: Path) -> None:
    report = _import(tmp_path)
    rows = _query_all(
        report.database_path,
        """
        SELECT section_id, parent_section_id, section_type, heading, sequence
        FROM sections
        ORDER BY section_id
        """,
    )
    by_id = {row[0]: row for row in rows}
    assert by_id["ccel.calvin.institutes.iii.ii"][1] == "ccel.calvin.institutes.iii"
    assert by_id["ccel.calvin.institutes.iii.ii"][2] == "chapter"
    assert by_id["ccel.calvin.institutes.iii.ii-p6"][1] == "ccel.calvin.institutes.iii.ii"
    assert by_id["ccel.calvin.institutes.iii.ii-p6"][2] == "section"
    assert by_id["ccel.calvin.institutes.iii.ii-p6"][4] == 1
    assert by_id["ccel.calvin.institutes.iii.ii-p8"][4] == 2
    assert report.chapters_imported == 4
    assert report.numbered_sections_imported == 4
    assert report.chunk_count == 4


def test_intro_paragraphs_are_not_chunks(tmp_path: Path) -> None:
    report = _import(tmp_path)
    texts = [
        row[0]
        for row in _query_all(report.database_path, "SELECT plain_text FROM chunks")
    ]
    blob = "\n".join(texts)
    assert "Synthetic TOC line one" not in blob
    assert "Synthetic TOC line two" not in blob
    assert "SYNTHETIC CHAPTER TITLE" not in blob
    assert "Sections." not in blob


def test_one_institutes_section_is_one_chunk_with_continuations(tmp_path: Path) -> None:
    report = _import(tmp_path)
    first = _query_all(
        report.database_path,
        "SELECT plain_text, source_locator FROM chunks WHERE source_locator = ?",
        ("ccel:calvin/institutes#iii.ii-p6",),
    )
    assert len(first) == 1
    plain, locator = first[0]
    assert locator == "ccel:calvin/institutes#iii.ii-p6"
    assert "1. Synthetic body" in plain
    assert "Continuation of section one after the page break." in plain
    assert "2. Synthetic body beta" not in plain
    chunk_ids = _query_all(
        report.database_path,
        "SELECT chunk_id FROM chunks WHERE section_id = ?",
        ("ccel.calvin.institutes.iii.ii-p6",),
    )
    assert len(chunk_ids) == 1


def test_locator_is_stable_ccel_id(tmp_path: Path) -> None:
    report = _import(tmp_path)
    locators = {
        row[0]
        for row in _query_all(report.database_path, "SELECT source_locator FROM chunks")
    }
    assert locators == {
        "ccel:calvin/institutes#iii.ii-p6",
        "ccel:calvin/institutes#iii.ii-p8",
        "ccel:calvin/institutes#v.ii-p2",
        "ccel:calvin/institutes#vi.ii-p1",
    }


def test_inline_markup_kept_and_note_not_duplicated(tmp_path: Path) -> None:
    report = _import(tmp_path)
    plain = _query_all(
        report.database_path,
        "SELECT plain_text FROM chunks WHERE source_locator = ?",
        ("ccel:calvin/institutes#iii.ii-p6",),
    )[0][0]
    assert "alpha" in plain
    assert "smallcaps" in plain
    assert "John 3:16" in plain
    assert plain.count("Synthetic footnote with italic clause.") == 1
    assert "[1] Synthetic footnote with italic clause." in plain


def test_scripture_links_and_skip_counts(tmp_path: Path) -> None:
    report = _import(tmp_path)
    links = _query_all(
        report.database_path,
        """
        SELECT chunks.source_locator, passage_links.canonical_passage
        FROM passage_links
        JOIN chunks ON chunks.chunk_id = passage_links.chunk_id
        ORDER BY chunks.source_locator, passage_links.canonical_passage
        """,
    )
    first = [canonical for locator, canonical in links if locator.endswith("#iii.ii-p6")]
    second = [canonical for locator, canonical in links if locator.endswith("#iii.ii-p8")]
    assert first == ["John.3.16", "Rom.8.28-30"]
    assert second == ["1Cor.3.21-23", "John.3.16", "Rom.8.32"]
    assert report.scripture_refs_seen == 11
    assert report.scripture_refs_imported == 5
    assert report.scripture_refs_skipped_chapter_only == 2
    assert report.scripture_refs_skipped_noncanonical == 1
    assert report.scripture_refs_skipped_nonbiblical == 1
    assert report.scripture_refs_skipped_unparseable == 1
    assert report.passage_link_count == 5


def test_duplicate_ref_in_same_chunk_is_deduped(tmp_path: Path) -> None:
    report = _import(tmp_path)
    rows = _query_all(
        report.database_path,
        """
        SELECT canonical_passage, COUNT(*)
        FROM passage_links
        WHERE chunk_id = ?
        GROUP BY canonical_passage
        """,
        ("ccel.calvin.institutes.iii.ii-p6.chunk",),
    )
    counts = {canonical: count for canonical, count in rows}
    assert counts["John.3.16"] == 1


def test_metadata_uses_header_and_pilot_constants(tmp_path: Path) -> None:
    report = _import(tmp_path)
    author = _query_all(
        report.database_path,
        "SELECT canonical_name, tradition FROM authors",
    )[0]
    edition = _query_all(
        report.database_path,
        """
        SELECT translator, publication_year, language, rights_status,
               corpus, external_id, rights_note, license
        FROM editions
        """,
    )[0]
    assert author == ("John Calvin", "reformed")
    assert edition[0] == "Henry Beveridge"
    assert edition[1] == 1845
    assert edition[2] == "en"
    assert edition[3] == "public-domain"
    assert edition[4] == "ccel"
    assert edition[5] == "ccel/calvin/institutes"
    note = edition[6]
    assert "Public Domain" in note
    assert "markup" in note.lower()
    assert "excludes" in note.lower()
    assert edition[7] == "Public Domain"
    assert report.import_mode == "ccel_thml"


def test_import_is_deterministic(tmp_path: Path) -> None:
    from textus_kb.importers.theology_sqlite import normalize_theology_document

    first_doc, first_extras = parse_ccel_institutes_thml(FIXTURE_PATH)
    second_doc, second_extras = parse_ccel_institutes_thml(FIXTURE_PATH)
    assert first_doc == second_doc
    assert first_extras["skipped_top_level_ids"] == second_extras["skipped_top_level_ids"]
    first = import_ccel_institutes_thml(FIXTURE_PATH, database_path=tmp_path / "a.sqlite3")
    second = import_ccel_institutes_thml(FIXTURE_PATH, database_path=tmp_path / "b.sqlite3")
    assert first.content_hash == second.content_hash
    assert first.content_hash == hash_theology_document(
        normalize_theology_document(first_doc)
    )


def test_build_script_ccel_thml_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.build_theology_database import main as build_main

    output = tmp_path / "from-cli.sqlite3"
    assert build_main(["--ccel-thml", str(FIXTURE_PATH), "--output", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["import_mode"] == "ccel_thml"
    assert payload["books_imported"] == 4
    assert payload["scripture_refs_imported"] == 5
    assert TheologyRepository(output).store_status().available is True


@pytest.mark.skipif(not REAL_XML_PATH.is_file(), reason="real CCEL Institutes XML not in temp")
def test_real_institutes_xml_pilot_parse(tmp_path: Path) -> None:
    report = import_ccel_institutes_thml(
        REAL_XML_PATH,
        database_path=tmp_path / "real-institutes.sqlite3",
    )
    assert report.books_imported == 4
    assert report.skipped_top_level_ids == ("i", "ii", "vii", "viii")
    assert report.chunk_count == report.numbered_sections_imported
    assert report.chapters_imported > 0
    locators = [
        row[0]
        for row in _query_all(
            report.database_path,
            "SELECT source_locator FROM chunks ORDER BY source_locator LIMIT 5",
        )
    ]
    assert "ccel:calvin/institutes#iii.ii-p6" in locators or any(
        locator.startswith("ccel:calvin/institutes#iii.") for locator in locators
    )
    links = _query_all(
        report.database_path,
        "SELECT canonical_passage FROM passage_links LIMIT 3",
    )
    assert len(links) >= 3
