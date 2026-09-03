"""Matthew Henry Commentary ThML importer tests, against a real (trimmed) CCEL XML fixture.

The fixture is an exact, unedited slice of the real ``mhc4.xml`` fetched
from ccel.org (Obadiah's own ``div1``, whole and unedited — Obadiah is
short enough to keep entire, and it is one of the 5 real corpus books
that exercises the documented "duplicate empty marker" exception). No
hand-authored or synthetic XML is used here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.henry_commentary_thml import (
    HenryCommentaryImportError,
    parse_henry_commentary_thml,
)
from textus_kb.importers.henry_source_fetch import HenryBookEntry, KnownEmptyCommentaryDiv

OBADIAH_FIXTURE = Path("tests/fixtures/kb/henry_obadiah_min.xml")

OBADIAH_KNOWN_EMPTY = KnownEmptyCommentaryDiv(
    div2_id="Obad.ii",
    commentary_div_id="Obad.ii-p1.9",
    reason="test fixture: documented upstream CCEL empty-marker artifact",
    classification="duplicate_empty_marker",
)

OBADIAH_ENTRY = HenryBookEntry(
    order=1,
    volume=4,
    div1_id="Obad",
    title="Obadiah",
    contributor_raw_name="Matthew Henry",
    known_empty_commentary_divs=(OBADIAH_KNOWN_EMPTY,),
)


def _parse(entry: HenryBookEntry = OBADIAH_ENTRY, path: Path = OBADIAH_FIXTURE):
    results = parse_henry_commentary_thml(path, [entry])
    return results[0]


def test_book_section_is_passage_less_structural() -> None:
    document, _report = _parse()
    by_id = {s["section_id"]: s for s in document["sections"]}
    book = by_id["ccel.henry.obadiah.book"]
    assert book["section_type"] == "book"
    assert book["parent_section_id"] is None
    assert book["passage_links"] == []


def test_introduction_div2_has_no_scripcom_and_no_passage() -> None:
    document, _report = _parse()
    by_id = {s["section_id"]: s for s in document["sections"]}
    intro = by_id["ccel.henry.obadiah.Obad_i"]
    assert intro["section_type"] == "chapter"
    assert intro["heading"] == "Introduction"
    assert intro["passage_links"] == []


def test_ranges_are_native_multi_verse_not_split_per_verse() -> None:
    """The core structural claim this round exists to prove: Henry's own
    multi-verse commentary sections stay one section per range — Obadiah's
    21 verses become exactly 3 range sections (1-9, 10-16, 17-21), never
    21 individually-split verse sections."""
    document, _report = _parse()
    range_sections = [s for s in document["sections"] if s["section_type"] == "range_commentary"]
    assert len(range_sections) == 3
    passages = [s["passage_links"][0]["canonical_passage"] for s in range_sections]
    assert passages == ["Obad.1.1-9", "Obad.1.10-16", "Obad.1.17-21"]


def test_relation_type_is_always_primary() -> None:
    document, _report = _parse()
    all_links = [link for s in document["sections"] for link in s["passage_links"]]
    assert all_links
    assert all(link["relation_type"] == "primary" for link in all_links)


def test_quoted_scripture_text_excluded_from_chunk_content() -> None:
    """The <p class="passage"> quoted-verse paragraph is Henry's lemma,
    not his prose, and must never appear as the section's own commentary
    text — mirrors Calvin's quoted-table-text exclusion precedent."""
    document, _report = _parse()
    range_section = next(
        s for s in document["sections"]
        if s["section_type"] == "range_commentary"
        and s["passage_links"][0]["canonical_passage"] == "Obad.1.1-9"
    )
    chunk = next(c for c in document["chunks"] if c["section_id"] == range_section["section_id"])
    # The quoted KJV verse text opens "The vision of Obadiah..." verbatim;
    # Henry's own prose commentary must be present without it being a
    # simple substring duplication of the full quoted block.
    assert "vision of Obadiah" not in chunk["plain_text"]


def test_inline_scripref_is_not_a_passage_link() -> None:
    document, _report = _parse()
    range_section = next(
        s for s in document["sections"]
        if s["section_type"] == "range_commentary"
        and s["passage_links"][0]["canonical_passage"] == "Obad.1.1-9"
    )
    assert [l["canonical_passage"] for l in range_section["passage_links"]] == ["Obad.1.1-9"]


def test_known_empty_commentary_div_is_skipped_not_a_section() -> None:
    document, report = _parse()
    assert report.known_empty_divs == [
        {
            "div2_id": "Obad.ii",
            "commentary_div_id": "Obad.ii-p1.9",
            "reason": OBADIAH_KNOWN_EMPTY.reason,
            "classification": "duplicate_empty_marker",
        }
    ]
    section_ids = {s["section_id"] for s in document["sections"]}
    assert "ccel.henry.obadiah.Obad_ii.r1" in section_ids
    # No section was fabricated for the empty marker itself.
    assert len([s for s in document["sections"] if s["section_type"] == "range_commentary"]) == 3


def test_undocumented_empty_div_fails_loudly() -> None:
    """Without the known-exception entry, the exact same empty div must
    raise rather than being silently skipped — proving this is a
    documented, audited allowlist, not a blanket tolerance."""
    entry = HenryBookEntry(
        order=1, volume=4, div1_id="Obad", title="Obadiah",
        contributor_raw_name="Matthew Henry",
        known_empty_commentary_divs=(),
    )
    with pytest.raises(HenryCommentaryImportError, match="completely empty"):
        parse_henry_commentary_thml(OBADIAH_FIXTURE, [entry])


def test_contributor_and_work_wiring() -> None:
    document, report = _parse()
    assert document["works"][0]["work_id"] == "ccel.henry.work.obadiah"
    assert document["editions"][0]["edition_id"] == "ccel.henry.obadiah.edition"
    assert document["contributors"][0]["canonical_name"] == "Matthew Henry"
    assert document["contributors"][0]["birth_year"] == 1662
    assert document["contributors"][0]["death_year"] == 1714
    assert document["work_contributors"] == [
        {
            "work_id": "ccel.henry.work.obadiah",
            "contributor_id": "ccel.henry.matthew-henry",
            "role": "author",
        }
    ]
    assert report.work_id == "ccel.henry.work.obadiah"


def test_continuator_contributor_has_no_guessed_dates() -> None:
    """A named posthumous continuator's birth/death years are never
    invented when unknown — mirrors Calvin's own precedent for
    translators of unknown dates."""
    entry = HenryBookEntry(
        order=1, volume=4, div1_id="Obad", title="Obadiah",
        contributor_raw_name="Mr. Someone Continuator",
        known_empty_commentary_divs=(OBADIAH_KNOWN_EMPTY,),
    )
    document, _report = _parse(entry=entry)
    contributor = document["contributors"][0]
    assert contributor["canonical_name"] == "Mr. Someone Continuator"
    assert contributor["birth_year"] is None
    assert contributor["death_year"] is None


def test_unknown_div1_id_fails_loudly() -> None:
    bad_entry = HenryBookEntry(
        order=1, volume=4, div1_id="DoesNotExist", title="Obadiah",
        contributor_raw_name="Matthew Henry",
    )
    with pytest.raises(HenryCommentaryImportError, match="not found"):
        parse_henry_commentary_thml(OBADIAH_FIXTURE, [bad_entry])
