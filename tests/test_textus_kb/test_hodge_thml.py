"""Hodge Systematic Theology Volume II CCEL/ThML pilot importer tests."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from textus_kb.importers.ccel_thml_core import (
    classify_osis_token,
    parse_thml_file,
)
from textus_kb.importers.hodge_thml import (
    ALLOWED_PART_DIV1_IDS,
    CHUNK_CHAR_THRESHOLD,
    HodgeThmlImportError,
    import_hodge_systematic_theology_thml,
    join_paragraph_plain,
    pack_paragraph_groups,
    parse_hodge_systematic_theology_thml,
)
from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    hash_theology_document,
    normalize_theology_document,
    validate_theology_database,
)
from textus_kb.repositories.theology_repository import TheologyRepository

FIXTURE_PATH = Path("tests/fixtures/kb/hodge_theology2_thml_min.xml")
FIXTURE_PATH_VOL1 = Path("tests/fixtures/kb/hodge_theology1_thml_min.xml")
FIXTURE_PATH_VOL3 = Path("tests/fixtures/kb/hodge_theology3_thml_min.xml")
REAL_XML_PATH = (
    Path(os.environ.get("TEMP", os.environ.get("TMP", "")))
    / "textus-hodge-e1"
    / "theology2.xml"
)


def _import(tmp_path: Path, xml_path: Path | None = None):
    database = tmp_path / "hodge-volume2-pilot.sqlite3"
    return import_hodge_systematic_theology_thml(
        xml_path or FIXTURE_PATH,
        database_path=database,
    )


def _write_xml(tmp_path: Path, xml_text: str) -> Path:
    path = tmp_path / "hodge.xml"
    path.write_text(xml_text, encoding="utf-8")
    return path


def _fixture_text() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8-sig")


def _query_all(database: Path, sql: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(database) as connection:
        return list(connection.execute(sql, params))


def test_fixture_is_markup_derived_not_real_hodge() -> None:
    text = _fixture_text()
    assert "markup-derived minimal fixture" in text
    assert "Let us make man in our image" not in text
    assert "Heathen Doctrine of Spontaneous Generation" not in text
    assert CHUNK_CHAR_THRESHOLD == 6_000


def test_external_dtd_is_not_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def boom(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("network access attempted during ThML parse")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("socket.create_connection", boom)
    parse_thml_file(FIXTURE_PATH)
    parse_hodge_systematic_theology_thml(FIXTURE_PATH)
    assert calls == []


def test_internal_dtd_entity_is_not_resolved(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-DTD-PAYLOAD", encoding="utf-8")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ThML [
  <!ENTITY xxe SYSTEM "{secret.as_uri()}">
]>
<ThML>
  <ThML.head>
    <electronicEdInfo><bookID>theology2</bookID></electronicEdInfo>
  </ThML.head>
  <ThML.body>
    <div1 title="Part II. Anthropology" id="iii">
      <div2 title="Chapter I." id="iii.i">
        <div3 title="1. Leaked." id="iii.i.i">
          <p id="iii.i.i-p1">§ 1. Leaked &xxe; text.</p>
        </div3>
      </div2>
    </div1>
    <div1 title="Part III. Soteriology." id="iv">
      <div2 title="Chapter I." id="iv.i">
        <div3 title="1. Other." id="iv.i.i">
          <p id="iv.i.i-p1">§ 1. Book two.</p>
        </div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>
"""
    path = _write_xml(tmp_path, xml)
    with pytest.raises(HodgeThmlImportError, match="Invalid ThML XML"):
        parse_hodge_systematic_theology_thml(path)


def test_malformed_xml_raises_controlled_error(tmp_path: Path) -> None:
    path = _write_xml(tmp_path, "<ThML><ThML.body>")
    with pytest.raises(HodgeThmlImportError, match="Invalid ThML XML"):
        parse_hodge_systematic_theology_thml(path)


def test_allowlisted_parts_only_and_front_index_excluded(tmp_path: Path) -> None:
    report = _import(tmp_path)
    assert tuple(ALLOWED_PART_DIV1_IDS) == ("iii", "iv")
    assert report.parts == 2
    assert report.skipped_top_level_ids == ("i", "ii", "v")
    joined = "\n".join(
        row[0] for row in _query_all(report.database_path, "SELECT plain_text FROM chunks")
    )
    assert "SYNTHETIC TITLE PAGE" not in joined
    assert "SYNTHETIC PREFATORY" not in joined
    assert "SYNTHETIC INDEX" not in joined
    assert "Tim Perrine" not in joined
    assert "CCEL Staff Writer" not in joined


def test_missing_allowlisted_part_is_import_error(tmp_path: Path) -> None:
    xml = _fixture_text().replace(
        'id="iv"',
        'id="zz"',
        1,
    )
    path = _write_xml(tmp_path, xml)
    with pytest.raises(HodgeThmlImportError, match="missing div1 id\\(s\\): iv"):
        parse_hodge_systematic_theology_thml(path)


def test_duplicate_allowlisted_part_is_import_error(tmp_path: Path) -> None:
    xml = _fixture_text().replace('id="iv"', 'id="iii"', 1)
    path = _write_xml(tmp_path, xml)
    with pytest.raises(HodgeThmlImportError, match="Duplicate allowlisted Volume II"):
        parse_hodge_systematic_theology_thml(path)


def test_wrong_volume_book_id_is_import_error(tmp_path: Path) -> None:
    xml = _fixture_text().replace("<bookID>theology2</bookID>", "<bookID>theology1</bookID>")
    path = _write_xml(tmp_path, xml)
    with pytest.raises(HodgeThmlImportError, match="expected bookID 'theology2'"):
        parse_hodge_systematic_theology_thml(path, volume=2)


def test_section_hierarchy_volume_part_chapter_subsection(tmp_path: Path) -> None:
    report = _import(tmp_path)
    rows = _query_all(
        report.database_path,
        """
        SELECT section_id, parent_section_id, section_type, heading, sequence
        FROM sections
        """,
    )
    by_id = {row[0]: row for row in rows}
    volume_id = "ccel.hodge.systematic_theology.vol2"
    assert by_id[volume_id][2] == "volume"
    assert by_id[volume_id][3] == "Vol. II"
    part_iii = "ccel.hodge.systematic_theology.vol2.iii"
    part_iv = "ccel.hodge.systematic_theology.vol2.iv"
    assert by_id[part_iii][1] == volume_id
    assert by_id[part_iii][2] == "part"
    assert by_id[part_iii][3] == "Part II"
    assert by_id[part_iv][3] == "Part III"
    chapter = "ccel.hodge.systematic_theology.vol2.iv.v"
    assert by_id[chapter][1] == part_iv
    assert by_id[chapter][2] == "chapter"
    assert by_id[chapter][4] == 5
    subsection = "ccel.hodge.systematic_theology.vol2.iv.v.ii"
    assert by_id[subsection][1] == chapter
    assert by_id[subsection][2] == "subsection"
    assert by_id[subsection][3] == "§2"
    assert by_id[subsection][4] == 2
    assert report.chapters == 6
    assert report.sections == 7


def test_short_div3_is_one_chunk(tmp_path: Path) -> None:
    report = _import(tmp_path)
    rows = _query_all(
        report.database_path,
        """
        SELECT chunk_id, sequence, source_locator, char_count
        FROM chunks
        WHERE section_id = ?
        """,
        ("ccel.hodge.systematic_theology.vol2.iii.i.i",),
    )
    assert len(rows) == 1
    assert rows[0][1] == 1
    assert rows[0][2] == "ccel:hodge/theology2#iii.i.i-p1"
    assert rows[0][3] < CHUNK_CHAR_THRESHOLD
    assert rows[0][0].endswith(".chunk")
    assert not rows[0][0].endswith(".chunk.1")


def test_oversize_div3_splits_on_paragraph_boundaries(tmp_path: Path) -> None:
    report = _import(tmp_path)
    rows = _query_all(
        report.database_path,
        """
        SELECT chunk_id, sequence, source_locator, plain_text, char_count
        FROM chunks
        WHERE section_id = ?
        ORDER BY sequence
        """,
        ("ccel.hodge.systematic_theology.vol2.iii.i.ii",),
    )
    assert len(rows) >= 2
    assert report.split_sections == 1
    assert report.split_chunks == len(rows)
    plains = [row[3] for row in rows]
    assert "§ 2." in plains[0]
    assert all("§ 2." not in chunk for chunk in plains[1:])
    assert "Rom. 8:3" in plains[0]
    assert "Phil. 2:6-8" in plains[-1]
    assert "Rom. 8:3" not in plains[-1]
    assert "Phil. 2:6-8" not in plains[0]
    reconstructed = join_paragraph_plain(plains)
    assert reconstructed == "\n\n".join(plains)
    assert reconstructed.count("Rom. 8:3") >= 1
    assert reconstructed.count("Phil. 2:6-8") == 1
    assert rows[0][2] == "ccel:hodge/theology2#iii.i.ii-p1"
    assert rows[-1][2] == "ccel:hodge/theology2#iii.i.ii-p3"
    assert rows[0][0].endswith(".chunk.1")
    assert rows[1][0].endswith(".chunk.2")


def test_split_has_no_text_loss_or_overlap() -> None:
    units = [
        {"plain": "AAA " * 20, "xml_id": "a", "element": None},
        {"plain": "BBB " * 20, "xml_id": "b", "element": None},
        {"plain": "CCC " * 20, "xml_id": "c", "element": None},
    ]
    original = join_paragraph_plain([unit["plain"] for unit in units])
    groups = pack_paragraph_groups(units, threshold=80)
    assert len(groups) > 1
    rebuilt = join_paragraph_plain(
        [join_paragraph_plain([unit["plain"] for unit in group]) for group in groups]
    )
    assert rebuilt == original
    seen: list[str] = []
    for group in groups:
        for unit in group:
            assert unit["xml_id"] not in seen
            seen.append(unit["xml_id"])
    assert seen == ["a", "b", "c"]


def test_human_readable_locator_and_source_locator(tmp_path: Path) -> None:
    report = _import(tmp_path)
    hits = TheologyRepository(report.database_path).chunks_for_passage("Eph.2.8-9")
    assert hits
    assert hits[0].human_readable_locator == (
        "Charles Hodge, Systematic Theology, Vol. II, Part III, Chapter 5, §2"
    )
    assert "fragment" not in hits[0].human_readable_locator
    assert hits[0].source_locator == "ccel:hodge/theology2#iv.v.ii-p1"
    assert "Page_" not in hits[0].source_locator


def test_scripture_links_and_skip_counts(tmp_path: Path) -> None:
    report = _import(tmp_path)
    links = {
        row[0]
        for row in _query_all(
            report.database_path,
            "SELECT canonical_passage FROM passage_links",
        )
    }
    assert links == {"Eph.2.8-9", "Gen.1.26-27", "Phil.2.6-8", "Rom.8.3"}
    assert report.scripture_refs_seen == 11
    assert report.passage_links_imported == 4
    assert report.skipped_chapter_only == 2
    assert report.skipped_noncanonical == 1
    assert report.skipped_no_osis == 1
    assert report.skipped_unparseable == 0
    assert report.skipped_malformed == 2
    assert report.duplicate_links == 1
    assert report.passage_link_count == 4


def test_classify_osis_token_policy() -> None:
    assert classify_osis_token("Bible:Rom.8.3") == ("ok", "Rom.8.3")
    assert classify_osis_token("Bible:Gen.1")[0] == "chapter_only"
    assert classify_osis_token("Bible:Wis.2.24")[0] == "noncanonical"
    assert classify_osis_token("Bible.vul:John.3.16")[0] == "malformed"
    assert classify_osis_token("Bible:Eph.1.17-Eph.1.10")[0] == "malformed"
    assert classify_osis_token("Bible:Col.1871")[0] == "chapter_only"


def test_provenance_and_rights_metadata(tmp_path: Path) -> None:
    report = _import(tmp_path)
    author = _query_all(
        report.database_path,
        "SELECT canonical_name, tradition, birth_year, death_year FROM authors",
    )[0]
    work = _query_all(
        report.database_path,
        "SELECT title, tradition, original_language FROM works",
    )[0]
    edition = _query_all(
        report.database_path,
        """
        SELECT edition_label, publication_year, language, rights_status, license,
               rights_note, source_url, corpus, external_id, translator
        FROM editions
        """,
    )[0]
    assert author == ("Charles Hodge", "reformed", 1797, 1878)
    assert work == ("Systematic Theology", "reformed", "en")
    assert edition[0] == "Volume II (CCEL ThML)"
    assert edition[1] == 1871
    assert edition[2] == "en"
    assert edition[3] == "needs-review"
    assert edition[4] == "unspecified"
    assert "DC.Rights is empty" in edition[5]
    assert "1878" in edition[5]
    assert "2005" in edition[5]
    assert "excluded" in edition[5]
    assert edition[6] == "https://www.ccel.org/ccel/hodge/theology2.xml"
    assert edition[7] == "ccel"
    assert edition[8] == "ccel/hodge/theology2"
    assert edition[9] is None
    assert report.import_mode == "hodge_thml"
    assert "public-domain" not in edition[3]


def test_sqlite_validation_and_deterministic_ids(tmp_path: Path) -> None:
    first_doc, _extras = parse_hodge_systematic_theology_thml(FIXTURE_PATH)
    second_doc, _ = parse_hodge_systematic_theology_thml(FIXTURE_PATH)
    assert first_doc == second_doc
    first = import_hodge_systematic_theology_thml(
        FIXTURE_PATH,
        database_path=tmp_path / "a.sqlite3",
    )
    second = import_hodge_systematic_theology_thml(
        FIXTURE_PATH,
        database_path=tmp_path / "b.sqlite3",
    )
    assert first.content_hash == second.content_hash
    assert first.content_hash == hash_theology_document(
        normalize_theology_document(first_doc)
    )
    validation = validate_theology_database(first.database_path)
    assert validation.schema_version == "1"
    assert validation.import_mode == "hodge_thml"
    assert validation.chunk_count == first.chunk_count
    assert TheologyRepository(first.database_path).store_status().available is True
    del tmp_path
    with pytest.raises(HodgeThmlImportError, match="production theology.sqlite3"):
        import_hodge_systematic_theology_thml(
            FIXTURE_PATH,
            database_path=DEFAULT_DATABASE_PATH,
        )


def test_chunk_order_is_document_order(tmp_path: Path) -> None:
    report = _import(tmp_path)
    locators = [
        row[0]
        for row in _query_all(
            report.database_path,
            """
            SELECT chunks.source_locator
            FROM chunks
            JOIN sections ON sections.section_id = chunks.section_id
            ORDER BY sections.section_id, chunks.sequence
            """,
        )
    ]
    assert locators[0] == "ccel:hodge/theology2#iii.i.i-p1"
    assert "ccel:hodge/theology2#iv.v.ii-p1" in locators
    assert locators == sorted(locators, key=locators.index)


@pytest.mark.skipif(not REAL_XML_PATH.is_file(), reason="real Hodge Volume II XML not in temp")
def test_real_volume_two_xml_pilot_parse(tmp_path: Path) -> None:
    report = import_hodge_systematic_theology_thml(
        REAL_XML_PATH,
        database_path=tmp_path / "hodge-volume2-pilot.sqlite3",
    )
    assert report.parts == 2
    assert report.skipped_top_level_ids == ("i", "ii", "v")
    assert report.chapters == 23
    assert report.sections == 116
    assert report.chunk_count >= report.sections
    assert report.split_sections > 0
    assert report.passage_link_count > 0
    assert report.import_mode == "hodge_thml"
    locators = [
        row[0]
        for row in _query_all(
            report.database_path,
            "SELECT source_locator FROM chunks ORDER BY source_locator LIMIT 5",
        )
    ]
    assert any(item.startswith("ccel:hodge/theology2#iii.") for item in locators)
    assert report.volume == 2


def test_volume_one_allowlist_and_introduction_locator(tmp_path: Path) -> None:
    report = import_hodge_systematic_theology_thml(
        FIXTURE_PATH_VOL1,
        database_path=tmp_path / "hodge-volume1-pilot.sqlite3",
    )
    assert report.volume == 1
    assert report.parts == 2
    assert report.skipped_top_level_ids == ("i", "ii", "v")
    joined = "\n".join(
        row[0] for row in _query_all(report.database_path, "SELECT plain_text FROM chunks")
    )
    assert "SYNTHETIC TITLE PAGE" not in joined
    assert "SYNTHETIC INDEX" not in joined
    hits = TheologyRepository(report.database_path).chunks_for_passage("John.3.16")
    assert hits
    assert hits[0].human_readable_locator == (
        "Charles Hodge, Systematic Theology, Vol. I, Introduction, Chapter 1, §1"
    )
    assert "fragment" not in hits[0].human_readable_locator
    assert hits[0].source_locator == "ccel:hodge/theology1#iii.i.i-p1"
    proper = TheologyRepository(report.database_path).chunks_for_passage("Eph.2.8-9")
    assert proper
    assert proper[0].human_readable_locator == (
        "Charles Hodge, Systematic Theology, Vol. I, Part I, Chapter 3, §2"
    )
    edition = _query_all(
        report.database_path,
        "SELECT edition_label, source_url, external_id, rights_status FROM editions",
    )[0]
    assert edition == (
        "Volume I (CCEL ThML)",
        "https://www.ccel.org/ccel/hodge/theology1.xml",
        "ccel/hodge/theology1",
        "needs-review",
    )


def test_volume_three_part_continued_and_eschatology_locator(tmp_path: Path) -> None:
    report = import_hodge_systematic_theology_thml(
        FIXTURE_PATH_VOL3,
        database_path=tmp_path / "hodge-volume3-pilot.sqlite3",
    )
    assert report.volume == 3
    assert report.skipped_top_level_ids == ("i", "ii", "v")
    rows = {
        row[0]: row
        for row in _query_all(
            report.database_path,
            "SELECT section_id, section_type, heading FROM sections",
        )
    }
    assert rows["ccel.hodge.systematic_theology.vol3.iii"][1:] == ("part", "Part III")
    assert rows["ccel.hodge.systematic_theology.vol3.iv"][1:] == ("part", "Part IV")
    soteriology = TheologyRepository(report.database_path).chunks_for_passage("Eph.2.8-9")
    assert soteriology
    assert soteriology[0].human_readable_locator == (
        "Charles Hodge, Systematic Theology, Vol. III, Part III, Chapter 1, §1"
    )
    assert "fragment" not in soteriology[0].human_readable_locator
    assert soteriology[0].source_locator.startswith("ccel:hodge/theology3#")
    eschatology = TheologyRepository(report.database_path).chunks_for_passage("1Cor.15.20")
    assert eschatology
    assert eschatology[0].human_readable_locator == (
        "Charles Hodge, Systematic Theology, Vol. III, Part IV, Chapter 5, §3"
    )
    assert "fragment" not in eschatology[0].human_readable_locator
    edition = _query_all(
        report.database_path,
        "SELECT edition_label, source_url FROM editions",
    )[0]
    assert edition == (
        "Volume III (CCEL ThML)",
        "https://www.ccel.org/ccel/hodge/theology3.xml",
    )


def test_invalid_volume_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(HodgeThmlImportError, match="Unsupported Hodge volume"):
        parse_hodge_systematic_theology_thml(FIXTURE_PATH, volume=4)


def test_volume_one_missing_expected_div1_is_import_error(tmp_path: Path) -> None:
    xml = FIXTURE_PATH_VOL1.read_text(encoding="utf-8").replace('id="iv"', 'id="zz"', 1)
    path = _write_xml(tmp_path, xml)
    with pytest.raises(HodgeThmlImportError, match="missing div1 id\\(s\\): iv"):
        parse_hodge_systematic_theology_thml(path, volume=1)


def test_volume_two_fixture_hash_is_stable(tmp_path: Path) -> None:
    first = import_hodge_systematic_theology_thml(
        FIXTURE_PATH,
        database_path=tmp_path / "vol2-a.sqlite3",
        volume=2,
    )
    second = import_hodge_systematic_theology_thml(
        FIXTURE_PATH,
        database_path=tmp_path / "vol2-b.sqlite3",
    )
    assert first.volume == 2
    assert first.content_hash == second.content_hash
    assert first.chunk_count == second.chunk_count


def test_split_section_locator_uses_fragment_suffix(tmp_path: Path) -> None:
    report = _import(tmp_path)
    repo = TheologyRepository(report.database_path)
    rom = [
        hit
        for hit in repo.chunks_for_passage("Rom.8.3")
        if hit.source_locator.startswith("ccel:hodge/theology2#iii.i.ii")
    ]
    phil = [
        hit
        for hit in repo.chunks_for_passage("Phil.2.6-8")
        if hit.source_locator.startswith("ccel:hodge/theology2#iii.i.ii")
    ]
    assert rom
    assert phil
    assert rom[0].human_readable_locator == (
        "Charles Hodge, Systematic Theology, Vol. II, Part II, Chapter 1, §2, fragment 1"
    )
    assert phil[0].human_readable_locator == (
        "Charles Hodge, Systematic Theology, Vol. II, Part II, Chapter 1, §2, fragment 2"
    )
    rows = _query_all(
        report.database_path,
        """
        SELECT sequence FROM chunks
        WHERE chunk_id = ?
        """,
        (phil[0].chunk_id,),
    )
    assert rows[0][0] == 2


def test_single_paragraph_over_threshold_stays_one_chunk() -> None:
    oversized = {"plain": "y" * (CHUNK_CHAR_THRESHOLD + 80), "xml_id": "p1", "element": None}
    groups = pack_paragraph_groups([oversized], threshold=CHUNK_CHAR_THRESHOLD)
    assert groups == [[oversized]]


def test_passage_links_are_local_to_split_fragment(tmp_path: Path) -> None:
    padding = ("synthetic fragment-local padding sentence. " * 180).strip()
    assert len(padding) > CHUNK_CHAR_THRESHOLD
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ThML>
  <ThML.head>
    <electronicEdInfo><bookID>theology2</bookID></electronicEdInfo>
  </ThML.head>
  <ThML.body>
    <div1 title="Part II. Anthropology" id="iii">
      <div2 title="Chapter I." id="iii.i">
        <div3 title="1. Local links." id="iii.i.i">
          <p id="iii.i.i-p1">§ 1. First fragment cites
            <scripRef passage="Rom. 8:3" osisRef="Bible:Rom.8.3">Rom. 8:3</scripRef>.</p>
          <p id="iii.i.i-p2">{padding}</p>
          <p id="iii.i.i-p3">Third fragment cites
            <scripRef passage="Phil. 2:6-8" osisRef="Bible:Phil.2.6-Phil.2.8">Phil. 2:6-8</scripRef>.</p>
        </div3>
      </div2>
    </div1>
    <div1 title="Part III. Soteriology." id="iv">
      <div2 title="Chapter I." id="iv.i">
        <div3 title="1. Other." id="iv.i.i">
          <p id="iv.i.i-p1">§ 1. Book two.</p>
        </div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>
"""
    path = _write_xml(tmp_path, xml)
    report = import_hodge_systematic_theology_thml(
        path,
        database_path=tmp_path / "fragment-links.sqlite3",
        volume=2,
    )
    rows = _query_all(
        report.database_path,
        """
        SELECT chunks.sequence, chunks.source_locator, chunks.plain_text,
               GROUP_CONCAT(passage_links.canonical_passage)
        FROM chunks
        LEFT JOIN passage_links ON passage_links.chunk_id = chunks.chunk_id
        WHERE chunks.section_id = ?
        GROUP BY chunks.chunk_id
        ORDER BY chunks.sequence
        """,
        ("ccel.hodge.systematic_theology.vol2.iii.i.i",),
    )
    assert len(rows) == 3
    assert rows[0][1] == "ccel:hodge/theology2#iii.i.i-p1"
    assert rows[1][1] == "ccel:hodge/theology2#iii.i.i-p2"
    assert rows[2][1] == "ccel:hodge/theology2#iii.i.i-p3"
    assert rows[0][3] == "Rom.8.3"
    assert rows[1][3] is None
    assert rows[2][3] == "Phil.2.6-8"
    assert "Phil. 2:6-8" not in rows[0][2]
    assert "Rom. 8:3" not in rows[2][2]
    repo = TheologyRepository(report.database_path)
    rom = repo.chunks_for_passage("Rom.8.3")
    phil = repo.chunks_for_passage("Phil.2.6-8")
    assert [hit.source_locator for hit in rom] == ["ccel:hodge/theology2#iii.i.i-p1"]
    assert [hit.source_locator for hit in phil] == ["ccel:hodge/theology2#iii.i.i-p3"]
    assert rom[0].human_readable_locator.endswith(", fragment 1")
    assert phil[0].human_readable_locator.endswith(", fragment 3")
    assert rom[0].canonical_passages == ("Rom.8.3",)
    assert phil[0].canonical_passages == ("Phil.2.6-8",)
    reconstructed = join_paragraph_plain([row[2] for row in rows])
    assert reconstructed.count("Rom. 8:3") == 1
    assert reconstructed.count("Phil. 2:6-8") == 1

