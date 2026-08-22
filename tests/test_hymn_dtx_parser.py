from __future__ import annotations

from pathlib import Path

import pytest

from bible_engine.hymn_dtx_parser import (
    audit_dtx_format,
    hymn_by_key,
    parse_dtx_file,
    validate_hymnal,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "hymns" / "dtx_sample.dtx"
ERE_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"


def test_parse_metadata_sections_hymns_and_variants() -> None:
    document = parse_dtx_file(FIXTURE, code="SAMPLE")

    assert document.metadata.code == "SAMPLE"
    assert document.metadata.title == "Sample Hymnal"
    assert document.metadata.dtx_code == "SAMPLE"
    assert document.metadata.category == "Test"
    assert document.metadata.header_comments == ("Sample DiaTar hymnal", "Header note")
    assert [section.title for section in document.sections] == [
        "Section One",
        "Closing Section",
        "Parent Section",
        "Child Section",
    ]
    assert document.sections[3].parent_ordinal == document.sections[2].ordinal
    assert [hymn.key for hymn in document.hymns] == ["1", "2a", "2b", "3", "4"]


def test_metadata_title_is_used_when_header_has_only_number() -> None:
    document = parse_dtx_file(FIXTURE, code="SAMPLE")
    hymn = hymn_by_key(document, "1")

    assert hymn.title == "First title from metadata"
    assert hymn.title_source == "metadata"
    assert hymn.source_metadata == ("First title from metadata", "Tune/source line")
    assert hymn.first_line == "First line of hymn one"
    assert hymn.stanzas[0].text == "First line of hymn one\nSecond line of hymn one"
    assert hymn.stanzas[0].technical_hash == "#1234ABCD"


def test_header_title_variants_and_internal_stanza_heading() -> None:
    document = parse_dtx_file(FIXTURE, code="SAMPLE")
    hymn = hymn_by_key(document, "2b")

    assert hymn.number == 2
    assert hymn.variant == "b"
    assert hymn.title == "Variant title"
    assert hymn.title_source == "header"
    assert hymn.section is not None
    assert hymn.section.title == "Section One"
    assert hymn.stanzas[1].number == 2
    assert hymn.stanzas[1].heading == "Internal stanza heading"
    assert hymn.stanzas[1].metadata_lines == ("Internal stanza heading", "")
    assert hymn.stanzas[1].first_line == "Variant B second stanza"


def test_adjacent_sections_create_parent_child_relationship() -> None:
    document = parse_dtx_file(FIXTURE, code="SAMPLE")
    hymn = hymn_by_key(document, "4")

    assert hymn.section is not None
    assert hymn.section.title == "Child Section"
    assert hymn.section.parent_ordinal == 3


def test_validate_fixture_detects_no_structural_errors() -> None:
    document = parse_dtx_file(FIXTURE, code="SAMPLE")
    report = validate_hymnal(document)

    assert report.hymn_count == 5
    assert report.base_number_count == 4
    assert report.number_min == 1
    assert report.number_max == 4
    assert report.variant_numbers == {2: ("a", "b")}
    assert report.duplicate_keys == ()
    assert report.hymns_without_stanzas == ()
    assert report.empty_stanzas == ()
    assert report.technical_hash_lines_in_text == ()
    assert report.section_titles_as_hymns == ()
    assert report.first_line_source_errors == ()


def test_audit_counts_fixture_constructs() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    audit = audit_dtx_format(text, code="SAMPLE")

    assert audit.numbered_hymn_records == 5
    assert audit.section_records == 4
    assert audit.stanza_markers == 7
    assert audit.technical_hash_lines == 7
    assert audit.variant_numbers == {2: ("a", "b")}
    assert audit.nonstandard_lines == ()


@pytest.mark.skipif(not ERE_SOURCE.exists(), reason="Full ERE.dtx is local raw data")
def test_full_ere_dtx_import_validation() -> None:
    document = parse_dtx_file(ERE_SOURCE, code="ERE")
    report = validate_hymnal(document)

    assert document.metadata.code == "ERE"
    assert document.metadata.title == "Erdélyi Református Énekeskönyv"
    assert document.metadata.dtx_code == "E.Ref"
    assert document.metadata.category == "Egyházak"
    assert len(document.sections) == 44
    assert document.sections[31].title == "Énekek bibliaórákra, vasárnapi iskolai és családi alkalmakra"
    assert document.sections[32].title == "Karácsony"
    assert document.sections[32].parent_ordinal == document.sections[31].ordinal
    assert report.hymn_count == 513
    assert report.base_number_count == 504
    assert report.number_min == 1
    assert report.number_max == 504
    assert report.variant_numbers == {
        152: ("a",),
        181: ("a", "b"),
        201: ("a", "b"),
        211: ("a", "b", "c"),
        254: ("a", "b"),
        309: ("a", "b"),
        330: ("a", "b"),
        391: ("a", "b"),
        400: ("a", "b"),
    }
    assert report.duplicate_keys == ()
    assert report.hymns_without_stanzas == ()
    assert report.empty_stanzas == ()
    assert report.technical_hash_lines_in_text == ()
    assert report.section_titles_as_hymns == ()
    assert report.first_line_source_errors == ()
    assert report.last_hymn_key == "504"

    first = hymn_by_key(document, "1")
    assert first.title == "Kétféle életút"
    assert first.first_line == "Aki nem jár hitlenek tanácsán,"
    assert first.stanzas[0].technical_hash == "#E46D75E8"

    long_hymn = hymn_by_key(document, "119")
    assert len(long_hymn.stanzas) == 88
    assert long_hymn.stanzas[20].heading == "Foglaljam szívembe az Úr törvényét"

    last = hymn_by_key(document, "504")
    assert last.title == "Áldjon meg téged, áldjon az Úr"
    assert last.first_line == "Áldjon meg téged, áldjon az Úr,"
