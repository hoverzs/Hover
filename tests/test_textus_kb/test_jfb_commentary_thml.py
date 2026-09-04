"""JFB Commentary ThML importer tests, against a real (trimmed) CCEL XML fixture.

The fixture is an exact, unedited slice of the real ``jfb.xml`` fetched
from ccel.org (Philemon's own ``div2``, whole and unedited — Philemon is
short enough to keep entire, so this fixture also doubles as a full,
real "Introduction with no scripCom at all" + "chapter whose own opening
marker is verse 1 itself" case). No hand-authored or synthetic XML is
used here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.jfb_commentary_thml import (
    JfbCommentaryImportError,
    parse_jfb_commentary_thml,
)
from textus_kb.importers.jfb_source_fetch import JfbBookEntry

PHILEMON_FIXTURE = Path("tests/fixtures/kb/jfb_philemon_min.xml")

PHILEMON_ENTRY = JfbBookEntry(
    order=1,
    div2_id="xi.xviii",
    title="Philemon",
    testament="NT",
    contributor_raw_name="A. R. Faussett",
    coverage="Philemon",
)


def _parse(entry: JfbBookEntry = PHILEMON_ENTRY, path: Path = PHILEMON_FIXTURE):
    results = parse_jfb_commentary_thml(path, [entry])
    return results[0]


def test_book_section_is_passage_less_structural() -> None:
    document, _report = _parse()
    by_id = {s["section_id"]: s for s in document["sections"]}
    book = by_id["ccel.jfb.philemon.book"]
    assert book["section_type"] == "book"
    assert book["parent_section_id"] is None
    assert book["passage_links"] == []


def test_introduction_div3_has_no_scripcom_and_no_passage() -> None:
    """Real corpus case (confirmed on 49/66 books): a bare "Introduction"
    div3 with zero <scripCom> markers becomes one passage-less structural
    section holding all its own prose, not an error."""
    document, _report = _parse()
    by_id = {s["section_id"]: s for s in document["sections"]}
    intro = by_id["ccel.jfb.philemon.xi_xviii_i"]
    assert intro["section_type"] == "chapter"
    assert intro["heading"] == "Introduction"
    assert intro["passage_links"] == []
    chunks_by_section = {c["section_id"]: c for c in document["chunks"]}
    assert "Origen" in chunks_by_section[intro["section_id"]]["plain_text"]


def test_chapter_opening_marker_can_itself_be_verse_one() -> None:
    """Real corpus quirk: Philemon's "Chapter 1" div3 has no separate
    chapter-only heading marker of its own — its opening <scripCom> is
    verse 1's own marker, so the div3-level "chapter" section legitimately
    carries a real passage_link (not always passage-less)."""
    document, _report = _parse()
    by_id = {s["section_id"]: s for s in document["sections"]}
    chapter = by_id["ccel.jfb.philemon.xi_xviii_ii"]
    assert [l["canonical_passage"] for l in chapter["passage_links"]] == ["Phlm.1.1"]


def test_all_25_verses_present_with_sequential_passages() -> None:
    document, _report = _parse()
    verse_sections = [
        s for s in document["sections"] if s["section_type"] == "verse_commentary"
    ]
    assert len(verse_sections) == 24  # verse 1 lives on the chapter section itself
    passages = [s["passage_links"][0]["canonical_passage"] for s in verse_sections]
    assert passages == [f"Phlm.1.{n}" for n in range(2, 26)]


def test_relation_type_is_always_primary() -> None:
    document, _report = _parse()
    all_links = [link for s in document["sections"] for link in s["passage_links"]]
    assert all_links
    assert all(link["relation_type"] == "primary" for link in all_links)


def test_inline_scripref_is_not_a_passage_link() -> None:
    """Philemon 1:1's own commentary cites Ac 16:14 / Col 4:9 inline
    (cross-references); those must never appear as passage_links on that
    verse's own section."""
    document, _report = _parse()
    by_id = {s["section_id"]: s for s in document["sections"]}
    chapter = by_id["ccel.jfb.philemon.xi_xviii_ii"]
    assert [l["canonical_passage"] for l in chapter["passage_links"]] == ["Phlm.1.1"]
    chunk = next(c for c in document["chunks"] if c["section_id"] == chapter["section_id"])
    assert "Col" in chunk["plain_text"] or "Coloss" in chunk["plain_text"]


def test_contributor_raw_name_typo_preserved_distinct_from_canonical() -> None:
    """Real corpus finding: the in-book attribution text spells Fausset's
    name with a doubled 't' ("Faussett"); DC.Creator spells it correctly
    ("Fausset"). Both must be preserved — canonical_name normalized,
    raw_name exactly as printed — never silently coerced to one spelling."""
    document, _report = _parse()
    assert document["contributors"][0]["canonical_name"] == "A. R. Fausset"
    assert document["contributor_source_names"][0]["raw_name"] == "A. R. Faussett"


def test_contributor_work_and_edition_wiring() -> None:
    document, report = _parse()
    assert document["works"][0]["work_id"] == "ccel.jfb.work.philemon"
    assert document["editions"][0]["edition_id"] == "ccel.jfb.philemon.edition"
    assert document["work_contributors"] == [
        {
            "work_id": "ccel.jfb.work.philemon",
            "contributor_id": "ccel.jfb.a-r-fausset",
            "role": "author",
        }
    ]
    assert report.work_id == "ccel.jfb.work.philemon"


def test_book_text_attribution_mismatching_manifest_fails_loudly(tmp_path: Path) -> None:
    """The manifest's contributor_raw_name is never trusted blindly — it
    is cross-checked against the book's own actual in-text attribution on
    every parse, so a stale/wrong manifest entry fails loudly instead of
    silently mis-attributing a book to the wrong historical author."""
    text = PHILEMON_FIXTURE.read_text(encoding="utf-8")
    mutated = text.replace(
        'Commentary by</i> <span class="sc" id="xi.xviii-p1.5">A. R. Faussett</span>',
        'Commentary by</i> <span class="sc" id="xi.xviii-p1.5">Someone Else Entirely</span>',
    )
    assert mutated != text
    broken = tmp_path / "broken.xml"
    broken.write_text(mutated, encoding="utf-8")
    with pytest.raises(JfbCommentaryImportError, match="does not match the book's own in-text attribution"):
        parse_jfb_commentary_thml(broken, [PHILEMON_ENTRY])


def test_attribution_not_matching_any_dc_creator_fails_loudly(tmp_path: Path) -> None:
    """Both the manifest and the book's own in-text attribution agree on
    a name that simply is not one of the file's own DC.Creator authors —
    a different, deeper failure mode than a manifest/text mismatch."""
    text = PHILEMON_FIXTURE.read_text(encoding="utf-8")
    mutated = text.replace(
        'Commentary by</i> <span class="sc" id="xi.xviii-p1.5">A. R. Faussett</span>',
        'Commentary by</i> <span class="sc" id="xi.xviii-p1.5">Someone Else Entirely</span>',
    )
    assert mutated != text
    broken = tmp_path / "broken.xml"
    broken.write_text(mutated, encoding="utf-8")
    mismatched_entry = JfbBookEntry(
        order=1,
        div2_id="xi.xviii",
        title="Philemon",
        testament="NT",
        contributor_raw_name="Someone Else Entirely",
    )
    with pytest.raises(JfbCommentaryImportError, match="does not match any DC.Creator"):
        parse_jfb_commentary_thml(broken, [mismatched_entry])


def test_unknown_div2_id_fails_loudly() -> None:
    bad_entry = JfbBookEntry(
        order=1,
        div2_id="xi.xviii.does-not-exist",
        title="Philemon",
        testament="NT",
        contributor_raw_name="A. R. Faussett",
    )
    with pytest.raises(JfbCommentaryImportError, match="not found"):
        parse_jfb_commentary_thml(PHILEMON_FIXTURE, [bad_entry])


def test_only_requested_testament_div1_is_required(tmp_path: Path) -> None:
    """The fixture only has an NT div1 wrapper; parsing an NT-only book
    list must not require the (absent) OT div1 to exist."""
    document, _report = _parse()
    assert document["sections"]


def test_split_into_segments_cuts_at_every_scripcom_regardless_of_nesting() -> None:
    """Direct unit test of the document-order cutter against a real
    fixture: verse boundaries must be found even though CCEL's own markup
    nests the announcing scripCom at varying depths (confirmed real
    layout quirk, not assumed uniform)."""
    from textus_kb.importers.ccel_thml_core import find_child, local_tag, parse_thml_file
    from textus_kb.importers.jfb_commentary_thml import _cut_into_segments

    root = parse_thml_file(PHILEMON_FIXTURE)
    body = find_child(root, "ThML.body")
    div1 = next(c for c in list(body) if local_tag(c.tag) == "div1")
    book = next(c for c in list(div1) if local_tag(c.tag) == "div2")
    chapter = next(
        c
        for c in list(book)
        if local_tag(c.tag) == "div3" and c.get("id") == "xi.xviii.ii"
    )
    segments = _cut_into_segments(chapter)
    # 1 (chapter/verse-1 opening) + 24 further verses = 25 segments.
    assert len(segments) == 25
    assert all(marker is not None for marker, _text in segments)
