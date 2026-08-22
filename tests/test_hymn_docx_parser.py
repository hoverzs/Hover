from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from bible_engine.hymn_docx_parser import (
    RE21_EXPECTED_SHA256,
    audit_docx_file,
    parse_docx_file,
    sha256_file,
    validate_docx_document,
)


ROOT = Path(__file__).resolve().parents[1]
RE21_SOURCE = ROOT / "data" / "raw" / "hymnals" / "RE21_master.docx"


def test_docx_parser_handles_re21_edge_header_forms(tmp_path: Path) -> None:
    fixture = tmp_path / "re21_edge_cases.docx"
    docx = Document()
    for paragraph in (
        "ZSOLTÁROK",
        "Genfi zsoltárok",
        "1szöveg: C. Marot | fordítás: Szenci Molnár A. | dallam: Genf, 1542",
        "1.Aki nem jár hitlenek tanácsán, / És meg nem áll a bűnösök útján.",
        "Zsoltárdicséretek",
        "151Zsolt 6szöveg: Debrecen, 1560 | dallam: Kolozsvár, 1744",
        "1.Hatalmas Isten, nagy haragodban ne feddj meg engemet",
        "DICSÉRETEK",
        "Úrvacsora",
        "360Losontzi Hányoki I., 1754 | L. Bourgeois, Genf, 1551 (42. zsoltár)",
        "1.Jer, lássuk az Úr keresztjét, / Melyet felvett érettünk",
        "Keresztyén reménység – Jézus Krisztus visszajövetele",
        "626fordítás: Túrmezei E.",
        "Az előző dallamra éneklendő.",
        "1.Fenn a mennyben az Úr minden győztesnek ád",
        "Áldás",
        "8464Móz 6,22–27 | szöveg és dallam: Draskóczy L.",
        "Áldjon meg téged, áldjon az Úr",
    ):
        docx.add_paragraph(paragraph)
    docx.save(fixture)

    document = parse_docx_file(fixture, code="RE21")

    assert [hymn.canonical_key for hymn in document.hymns] == ["1", "151", "360", "626", "846"]
    assert document.hymns[0].first_line == "Aki nem jár hitlenek tanácsán,"
    assert document.hymns[1].source_metadata.biblical_reference == "Zsolt 6"
    assert document.hymns[2].source_metadata.text_author == "Losontzi Hányoki I., 1754"
    assert document.hymns[2].source_metadata.tune == "L. Bourgeois, Genf, 1551 (42. zsoltár)"
    assert document.hymns[3].source_metadata.translator == "Túrmezei E."
    assert document.hymns[4].source_metadata.biblical_reference == "4Móz 6,22–27"
    assert document.hymns[4].first_line == "Áldjon meg téged, áldjon az Úr"


@pytest.mark.skipif(not RE21_SOURCE.exists(), reason="Full RÉ21 DOCX is local raw data")
def test_full_re21_docx_checksum_matches_expected() -> None:
    assert sha256_file(RE21_SOURCE) == RE21_EXPECTED_SHA256


@pytest.mark.skipif(not RE21_SOURCE.exists(), reason="Full RÉ21 DOCX is local raw data")
def test_full_re21_docx_format_audit() -> None:
    audit = audit_docx_file(RE21_SOURCE)

    assert audit.nonempty_paragraph_count == 4615
    assert audit.paragraph_styles == {"": 4615}
    assert audit.italic_run_paragraphs == 338
    assert audit.bold_run_paragraphs == 0
    assert audit.superscript_run_paragraphs == 0
    assert audit.hymn_header_candidates == 667
    assert "ZSOLTÁROK" in audit.section_candidates
    assert "DICSÉRETEK" in audit.section_candidates
    assert "BIBLIAKÖRI ÉNEKEK" in audit.section_candidates
    assert any(example.startswith("151Zsolt 6") for example in audit.irregular_header_examples)


@pytest.mark.skipif(not RE21_SOURCE.exists(), reason="Full RÉ21 DOCX is local raw data")
def test_full_re21_docx_validation_counts() -> None:
    document = parse_docx_file(RE21_SOURCE)
    report = validate_docx_document(document)

    assert report.hymn_count == 667
    assert report.unique_number_count == 667
    assert report.number_min == 1
    assert report.number_max == 846
    assert report.number_ranges == (
        "1-197",
        "201-214",
        "221-252",
        "261-269",
        "281-302",
        "311-315",
        "321-327",
        "331-334",
        "341-347",
        "351-364",
        "371-395",
        "401-423",
        "431-456",
        "461-477",
        "481-498",
        "501-521",
        "531-536",
        "541-554",
        "561-570",
        "581-591",
        "601-630",
        "641-644",
        "651-668",
        "671-677",
        "681-705",
        "711-731",
        "741-780",
        "791-810",
        "821-834",
        "841-846",
    )
    assert report.section_count == 39
    assert report.stanza_count == 3783
    assert report.variant_numbers == {}
    assert report.duplicate_keys == ()
    assert report.hymns_without_stanzas == ()
    assert report.empty_stanzas == ()
    assert report.missing_first_lines == ()
    assert report.metadata_first_line_errors == ()
    assert report.parser_warning_count == 0


@pytest.mark.skipif(not RE21_SOURCE.exists(), reason="Full RÉ21 DOCX is local raw data")
def test_full_re21_docx_representative_records() -> None:
    document = parse_docx_file(RE21_SOURCE)
    by_number = {hymn.number: hymn for hymn in document.hymns}

    assert by_number[1].first_line.startswith("Aki nem jár hitlenek tanácsán")
    assert by_number[1].source_metadata.text_author == "C. Marot"
    assert by_number[119].first_line.startswith("Az oly emberek nyilván boldogok")
    assert by_number[119].stanzas[0].number == 1
    assert by_number[267].first_line.startswith("Urunk, irgalmazz nékünk")
    assert by_number[299].source_metadata.biblical_reference == "2Kor 13,13"
    assert by_number[360].source_metadata.text_author == "Losontzi Hányoki I., 1754"
    assert by_number[360].section and by_number[360].section.title == "Úrvacsora"
    assert by_number[626].source_metadata.translator == "Túrmezei E."
    assert by_number[846].source_metadata.biblical_reference == "4Móz 6,22–27"
    assert by_number[846].first_line.startswith("Áldjon meg téged")


@pytest.mark.skipif(not RE21_SOURCE.exists(), reason="Full RÉ21 DOCX is local raw data")
def test_full_re21_section_hierarchy() -> None:
    document = parse_docx_file(RE21_SOURCE)
    sections = {section.title: section for section in document.sections}

    assert sections["Genfi zsoltárok"].parent_ordinal == sections["ZSOLTÁROK"].ordinal
    assert sections["Kezdőénekek"].parent_ordinal == sections["Istentisztelet"].ordinal
    assert sections["Úrvacsora"].parent_ordinal == sections["Hitünk alapjai"].ordinal
    assert (
        sections["Nagyhét – Jézus Krisztus kínszenvedése és halála"].parent_ordinal
        == sections["Az egyházi év"].ordinal
    )
    assert sections["Áldás"].parent_ordinal == sections["Keresztyén élet"].ordinal
