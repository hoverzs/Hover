"""Calvin Commentary ThML importer tests, against real (trimmed) CCEL XML.

Fixtures are exact, unedited slices of the real files fetched from
ccel.org (Romans = calcom38, Harmony of the Evangelists = calcom31); only
whole <div1>/<div2> elements were removed to keep the fixtures small. No
hand-authored or synthetic XML is used here — every structural case below
(range section, the untyped "anomaly" verse-1 continuation, nested
per-verse <div class="Commentary"> blocks, a two-passage Harmony section,
an inline cross-reference) is real Calvin commentary markup.
"""

from __future__ import annotations

import copy
import re
import sqlite3
from pathlib import Path

import pytest

from textus_kb.importers.calvin_commentary_thml import (
    AUTHOR_CONTRIBUTOR_ID,
    IMPORT_MODE_CALVIN_COMMENTARY_THML,
    CalvinCommentaryImportError,
    KnownUnmappedSection,
    build_calvin_commentary_document,
    import_calvin_commentary_sqlite,
    merge_calvin_commentary_documents,
    parse_calvin_commentary_thml,
)
from textus_kb.importers.commentary_sqlite import (
    CommentaryImportError,
    import_commentary_sqlite,
)
from textus_kb.repositories.commentary_repository import (
    RELATION_CONTAINING_SECTION,
    RELATION_EXACT_PASSAGE,
    CommentaryRepository,
)

ROMANS_FIXTURE = Path("tests/fixtures/kb/calvin_calcom38_romans_ch1_min.xml")
HARMONY_FIXTURE = Path("tests/fixtures/kb/calvin_calcom31_harmony_min.xml")
ROMANS_FOOTNOTE_CATENA_FIXTURE = Path(
    "tests/fixtures/kb/calvin_calcom38_romans_footnote_catena_min.xml"
)
HARMONY_CONTINUATION_FIXTURE = Path(
    "tests/fixtures/kb/calvin_calcom31_harmony_continuation_min.xml"
)
ISAIAH_NO_WRAPPER_FIXTURE = Path(
    "tests/fixtures/kb/calvin_calcom13_isaiah_no_wrapper_min.xml"
)
HARMONY_LAW_PLAIN_CAPTION_FIXTURE = Path(
    "tests/fixtures/kb/calvin_calcom03_harmony_law_plain_caption_min.xml"
)


# --- Parsing structure ------------------------------------------------


def test_romans_range_section_gets_range_passage_from_table() -> None:
    document, report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    range_section = by_id["ccel.calvin.calcom38.v.i"]
    assert [l["canonical_passage"] for l in range_section["passage_links"]] == ["Rom.1.1-7"]
    assert report.range_section_count == 2


def test_romans_untyped_anomaly_div_becomes_children_of_preceding_range() -> None:
    """The real 'v.ii' div2 (no type=scripture) holds Calvin's exposition of
    verse 1 as its own top-level div2 instead of a nested Commentary div —
    a real CCEL editorial quirk. It must still be anchored under v.i."""
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    child = by_id["ccel.calvin.calcom38.v.ii.v1"]
    assert child["parent_section_id"] == "ccel.calvin.calcom38.v.i"
    assert [l["canonical_passage"] for l in child["passage_links"]] == ["Rom.1.1"]


def test_romans_nested_commentary_divs_become_verse_children() -> None:
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    parent = by_id["ccel.calvin.calcom38.v.iii"]
    assert [l["canonical_passage"] for l in parent["passage_links"]] == ["Rom.1.8-12"]
    for n, verse in enumerate(["Rom.1.8", "Rom.1.9", "Rom.1.10", "Rom.1.11", "Rom.1.12"], start=1):
        child = by_id[f"ccel.calvin.calcom38.v.iii.v{n}"]
        assert child["parent_section_id"] == "ccel.calvin.calcom38.v.iii"
        assert [l["canonical_passage"] for l in child["passage_links"]] == [verse]


def test_romans_quoted_bible_text_is_not_chunk_content() -> None:
    """The scripture div2's own chunk (if any) must never be the quoted
    verse-text table; that is not Calvin's prose."""
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    chunks_by_section = {c["section_id"]: c for c in document["chunks"]}
    range_chunk = chunks_by_section.get("ccel.calvin.calcom38.v.i.chunk")
    if range_chunk is not None:
        assert "servus Iesu Christi" not in range_chunk["plain_text"]


def test_inline_cross_reference_is_not_a_passage_link() -> None:
    """Calvin's exposition of Romans 1:1 cites Acts 23:26 in a footnote as a
    cross-reference. That must never become a section_passage_links row —
    only the scripCom-defined Romans 1:1 passage may."""
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    section = by_id["ccel.calvin.calcom38.v.ii.v1"]
    assert [l["canonical_passage"] for l in section["passage_links"]] == ["Rom.1.1"]
    chunk = next(
        c for c in _chunks(document) if c["section_id"] == "ccel.calvin.calcom38.v.ii.v1"
    )
    assert "Acts" in chunk["plain_text"]  # the cross-reference is in the prose...
    assert "Acts.23" not in [
        l["canonical_passage"] for l in section["passage_links"]
    ]  # ...but never became a passage_link


def test_harmony_section_links_multiple_passages() -> None:
    document, report = parse_calvin_commentary_thml(HARMONY_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    section = by_id["ccel.calvin.calcom31.ix.xiv"]
    passages = {l["canonical_passage"] for l in section["passage_links"]}
    assert passages == {"Matt.1.1-17", "Luke.3.23-38"}
    assert report.multi_passage_range_count == 1


def test_harmony_verse_children_keep_their_own_single_book() -> None:
    """Children of a multi-passage Harmony section resolve their own passage
    independently (Matthew verses here), not the parent's combined range."""
    document, _report = parse_calvin_commentary_thml(HARMONY_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    child = by_id["ccel.calvin.calcom31.ix.xiv.v1"]
    assert [l["canonical_passage"] for l in child["passage_links"]] == ["Matt.1.1"]


def test_contributors_have_author_and_translator_roles() -> None:
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    roles = {(wc["contributor_id"], wc["role"]) for wc in document["work_contributors"]}
    assert (AUTHOR_CONTRIBUTOR_ID, "author") in roles
    names = {c["contributor_id"]: c["canonical_name"] for c in document["contributors"]}
    assert names[AUTHOR_CONTRIBUTOR_ID] == "John Calvin"
    translator_ids = [cid for cid, role in roles if role == "translator"]
    assert len(translator_ids) == 1
    assert "Owen" in names[translator_ids[0]]


def test_edition_metadata_is_real_not_invented() -> None:
    document, _report = parse_calvin_commentary_thml(ROMANS_FIXTURE)
    edition = document["editions"][0]
    assert edition["license"] == "Public Domain"
    assert edition["rights_status"] == "public-domain"
    assert edition["language"] == "en"
    assert edition["source_url"] == "https://www.ccel.org/ccel/calvin/calcom38.xml"
    assert edition["external_id"] == "ccel/calvin/calcom38"


# --- Footnote-embedded OT catena / bibliographic cross-references --------
#
# Real bug found via corpus QA: Romans 3:10-18 is itself a chain of OT
# quotations (Ps 14:1-3, 53:3, 5:9, 14:3, 9:7; Isaiah 56:7; Proverbs 1:16;
# Psalm 36:1) and CCEL's translator footnote lists them as "the references
# given in the margin" — an 8-token osisRef inside a <note> in the SAME
# <table> as the real "Romans 3:10-18" caption. Before the fix, every one
# of those 8 tokens leaked into section_passage_links.


def test_ot_catena_footnote_is_not_a_passage_link() -> None:
    document, _report = parse_calvin_commentary_thml(ROMANS_FOOTNOTE_CATENA_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    section = by_id["ccel.calvin.calcom38.vii.v"]
    passages = [l["canonical_passage"] for l in section["passage_links"]]
    assert passages == ["Rom.3.10-18"]
    leaked_books = {p.split(".", 1)[0] for p in passages} - {"Rom"}
    assert leaked_books == set()


def test_footnote_catena_note_lives_in_the_excluded_quote_table() -> None:
    """The catena footnote is attached to verse 18's Latin quote text inside
    the table, so — consistent with the table never becoming chunk content
    — neither its citations nor its own text appear in any chunk."""
    document, _report = parse_calvin_commentary_thml(ROMANS_FOOTNOTE_CATENA_FIXTURE)
    all_text = " ".join(c["plain_text"] for c in document["chunks"])
    assert "references given in the margin" not in all_text


def test_secondary_table_caption_is_kept_as_parallel_passage() -> None:
    """A real three-column Harmony table (Matthew/Mark/Luke) where the Mark
    column carries a SECOND, non-contiguous caption (Mark 4:21, marked with
    a different CSS class than the primary captions) must keep all six
    legitimate passages — only the genuine footnote cross-reference
    (Leviticus 2:13, inside a <note>) must be excluded."""
    document, _report = parse_calvin_commentary_thml(HARMONY_CONTINUATION_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    section = by_id["ccel.calvin.calcom31.ix.xlii"]
    passages = {l["canonical_passage"] for l in section["passage_links"]}
    assert passages == {
        "Matt.5.13-16",
        "Mark.9.49-50",
        "Luke.14.34-35",
        "Mark.4.21",
        "Luke.8.16",
        "Luke.11.33",
    }
    assert "Lev.2.13" not in passages


# --- Fail-loudly on structurally uncertain passage mapping ---------------


def test_scripture_section_without_parseable_table_fails_loudly(tmp_path: Path) -> None:
    text = ROMANS_FIXTURE.read_text(encoding="utf-8")
    # Break the FIRST scripture div2's table caption so no passage can be
    # recovered from it either structurally (osisRef) or via the
    # plain-text-caption fallback (the visible citation text itself).
    mutated = re.sub(r'osisRef="Bible:Rom\.1\.1-Rom\.1\.7"', 'osisRef=""', text, count=1)
    mutated = mutated.replace(
        '<scripRef passage="Romans 1:1-7" id="v.i-p1.1" parsed="|Rom|1|1|1|7" '
        'osisRef="">Romans 1:1-7</scripRef>',
        '<scripRef passage="" id="v.i-p1.1" parsed="" osisRef="">not a reference</scripRef>',
    )
    assert mutated != text
    broken = tmp_path / "broken_romans.xml"
    broken.write_text(mutated, encoding="utf-8")
    with pytest.raises(CalvinCommentaryImportError, match="no parseable passage"):
        parse_calvin_commentary_thml(broken)


def test_verse_content_without_commentary_div_wrapper_is_still_collected() -> None:
    """Real corpus case (Isaiah): scripCom markers are sometimes followed by
    plain sibling <p> elements with no wrapping <div class="Commentary"> at
    all. Content between one scripCom and the next belongs to that verse
    regardless of whether a wrapper tag is present — verified against the
    real, unedited Isaiah 17 fixture below."""
    document, _report = parse_calvin_commentary_thml(ISAIAH_NO_WRAPPER_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    chunks_by_section = {c["section_id"]: c for c in document["chunks"]}
    verse_section = next(
        s for s in document["sections"] if s["section_type"] == "verse_commentary"
    )
    chunk = chunks_by_section.get(verse_section["section_id"])
    assert chunk is not None and chunk["plain_text"]


# --- Provenance / SHA-256 -------------------------------------------------


def test_build_document_attaches_real_raw_sha256() -> None:
    import hashlib

    document, report = build_calvin_commentary_document(ROMANS_FIXTURE)
    expected = hashlib.sha256(ROMANS_FIXTURE.read_bytes()).hexdigest()
    source_file = document["source_files"][0]
    assert source_file["raw_sha256"] == expected
    assert source_file["file_name"] == ROMANS_FIXTURE.name
    batch = document["import_batches"][0]
    assert batch["source_file_id"] == source_file["source_file_id"]
    assert batch["importer_name"] == "textus_kb.importers.calvin_commentary_thml"
    assert batch["report"]["book_id"] == report.book_id


# --- Multi-file combined import; no duplicate author/translator ----------


def test_merge_two_calvin_documents_dedupes_shared_author() -> None:
    romans_doc, _ = build_calvin_commentary_document(ROMANS_FIXTURE)
    harmony_doc, _ = build_calvin_commentary_document(HARMONY_FIXTURE)
    merged = merge_calvin_commentary_documents([romans_doc, harmony_doc])

    author_rows = [c for c in merged["contributors"] if c["contributor_id"] == AUTHOR_CONTRIBUTOR_ID]
    assert len(author_rows) == 1  # Calvin declared by both files, not duplicated

    translator_ids = {c["contributor_id"] for c in merged["contributors"]} - {AUTHOR_CONTRIBUTOR_ID}
    assert len(translator_ids) == 2  # Owen (Romans) and Pringle (Harmony) are distinct people

    assert len(merged["works"]) == 2
    assert len(merged["editions"]) == 2
    assert len(merged["source_files"]) == 2


# --- Multi-volume work grouping (manifest-declared, not hardcoded) -------


def test_work_group_collapses_two_volumes_into_one_work(tmp_path: Path) -> None:
    """Two files sharing a manifest-declared work_group merge into one
    `work` row spanning two `editions` (one per volume/file); section ids
    stay collision-free because they are still derived from each file's
    own book_id, not from the shared work_group."""
    fixed = "2026-01-01T00:00:00Z"
    volume_a, _ = build_calvin_commentary_document(
        ROMANS_FIXTURE,
        imported_at=fixed,
        work_group="test_multivolume",
        work_title="Test Multi-Volume Work",
    )
    volume_b, _ = build_calvin_commentary_document(
        HARMONY_FIXTURE,
        imported_at=fixed,
        work_group="test_multivolume",
        work_title="Test Multi-Volume Work",
    )
    merged = merge_calvin_commentary_documents([volume_a, volume_b])

    assert len(merged["works"]) == 1
    assert merged["works"][0]["work_id"] == "ccel.calvin.work.test_multivolume"
    assert merged["works"][0]["title"] == "Test Multi-Volume Work"
    assert len(merged["editions"]) == 2
    edition_ids = {e["edition_id"] for e in merged["editions"]}
    assert len(edition_ids) == 2  # no collision even though work_id is shared

    section_ids = [s["section_id"] for s in merged["sections"]]
    assert len(section_ids) == len(set(section_ids))  # no cross-volume collisions

    database = tmp_path / "commentary.sqlite3"
    import_commentary_sqlite(document=merged, database_path=database)
    repo = CommentaryRepository(database)
    hits = repo.sections_for_passage("Rom.1.1", work_id="ccel.calvin.work.test_multivolume")
    assert any(h.section_id == "ccel.calvin.calcom38.v.ii.v1" for h in hits)
    # Retrieval is unified at the work level: filtering by the shared
    # work_id still finds a section that lives in the OTHER volume's edition.
    harmony_hits = repo.sections_for_passage(
        "Matt.1.1-17", work_id="ccel.calvin.work.test_multivolume"
    )
    assert any(h.section_id == "ccel.calvin.calcom31.ix.xiv" for h in harmony_hits)


def test_group_entries_by_work_orders_by_volume() -> None:
    from textus_kb.importers.calvin_source_fetch import CalvinSourceEntry, group_entries_by_work

    entries = [
        CalvinSourceEntry(
            id="calcom10", title="t", url="u", local_path=Path("x"), raw_sha256="0" * 64,
            work_group="psalms", volume=3,
        ),
        CalvinSourceEntry(
            id="calcom08", title="t", url="u", local_path=Path("x"), raw_sha256="0" * 64,
            work_group="psalms", volume=1,
        ),
        CalvinSourceEntry(
            id="calcom38", title="t", url="u", local_path=Path("x"), raw_sha256="0" * 64,
        ),
    ]
    groups = group_entries_by_work(entries)
    assert set(groups.keys()) == {"psalms", "calcom38"}
    assert [e.id for e in groups["psalms"]] == ["calcom08", "calcom10"]
    assert [e.id for e in groups["calcom38"]] == ["calcom38"]


def test_import_calvin_commentary_sqlite_combines_both_fixtures(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    report, parse_reports = import_calvin_commentary_sqlite(
        [ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=database
    )
    assert report.import_mode == IMPORT_MODE_CALVIN_COMMENTARY_THML
    assert report.work_count == 2
    assert report.source_file_count == 2
    assert report.import_batch_count == 2
    assert len(parse_reports) == 2

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        contributors = connection.execute(
            "SELECT contributor_id, canonical_name FROM contributors"
        ).fetchall()
    assert len(contributors) == 3  # Calvin + Owen + Pringle, no duplicate Calvin row


# --- Deterministic build ---------------------------------------------------


def test_deterministic_build_same_content_hash(tmp_path: Path) -> None:
    """Two builds are byte-identical only when imported_at is pinned: each
    file's provenance row embeds a real timestamp, so an unpinned build
    spanning a wall-clock second boundary would otherwise (correctly)
    produce a different content_hash from that clock read alone."""
    fixed_timestamp = "2026-01-01T00:00:00Z"
    first, _ = import_calvin_commentary_sqlite(
        [ROMANS_FIXTURE, HARMONY_FIXTURE],
        database_path=tmp_path / "a.sqlite3",
        imported_at=fixed_timestamp,
    )
    second, _ = import_calvin_commentary_sqlite(
        [ROMANS_FIXTURE, HARMONY_FIXTURE],
        database_path=tmp_path / "b.sqlite3",
        imported_at=fixed_timestamp,
    )
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64


# --- Repository retrieval on real (trimmed) Calvin data -------------------


@pytest.fixture()
def calvin_repo(tmp_path: Path) -> CommentaryRepository:
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE, HARMONY_FIXTURE], database_path=database)
    return CommentaryRepository(database)


def test_exact_verse_retrieval_real_data(calvin_repo: CommentaryRepository) -> None:
    hits = calvin_repo.sections_for_passage("Rom.1.1")
    by_id = {h.section_id: h for h in hits}
    assert by_id["ccel.calvin.calcom38.v.ii.v1"].relation_type == RELATION_EXACT_PASSAGE
    assert by_id["ccel.calvin.calcom38.v.i"].relation_type == RELATION_CONTAINING_SECTION


def test_range_retrieval_real_data(calvin_repo: CommentaryRepository) -> None:
    hits = calvin_repo.sections_for_passage("Rom.1.9")
    by_id = {h.section_id: h for h in hits}
    assert by_id["ccel.calvin.calcom38.v.iii.v2"].relation_type == RELATION_EXACT_PASSAGE
    assert by_id["ccel.calvin.calcom38.v.iii"].relation_type == RELATION_CONTAINING_SECTION


def test_multi_passage_retrieval_real_data(calvin_repo: CommentaryRepository) -> None:
    via_matthew = calvin_repo.sections_for_passage("Matt.1.1-17")
    via_luke = calvin_repo.sections_for_passage("Luke.3.23-38")
    assert any(h.section_id == "ccel.calvin.calcom31.ix.xiv" for h in via_matthew)
    assert any(h.section_id == "ccel.calvin.calcom31.ix.xiv" for h in via_luke)


def test_no_cross_book_leak_real_data(calvin_repo: CommentaryRepository) -> None:
    hits = calvin_repo.sections_for_passage("Rom.1.9")
    assert all(
        passage.startswith("Rom.") for h in hits for passage in h.canonical_passages
    )


def test_book_without_calvin_commentary_returns_empty(calvin_repo: CommentaryRepository) -> None:
    assert calvin_repo.sections_for_passage("Genesis.1.1") == []
    assert calvin_repo.sections_for_passage("John.3.16") == []


def _chunks(document: dict) -> list[dict]:
    return document["chunks"]


# --- Plain-text captions and connector-word normalization ----------------
#
# Real bugs found via a full 45-volume corpus scan: some CCEL volumes omit
# <scripRef> markup from a table caption entirely (Harmony of the Law:
# bare "deuteronomy 6:20-25" text), and some insert a decorative English
# word between the book name and the numbers (Isaiah: "Isaiah Chapter
# 1:1-31"). Both are recovered by parsing the caption's own visible text
# with the same general-purpose CanonicalReference.parse already trusted
# for raw_citation elsewhere — never invented, always the literal text
# present in the document.


def test_plain_text_caption_without_scripref_is_recovered() -> None:
    document, report = parse_calvin_commentary_thml(HARMONY_LAW_PLAIN_CAPTION_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    section = by_id["ccel.calvin.calcom03.v.xiii"]
    assert [l["canonical_passage"] for l in section["passage_links"]] == ["Deut.6.20-25"]
    assert report.unmapped_sections == []


def test_connector_word_is_stripped_before_parsing() -> None:
    """"Isaiah Chapter 1:1-31" (real caption text, no scripRef at all)
    resolves correctly only because "Chapter" is stripped before parsing —
    this is exercised end-to-end by the no-wrapper fixture's own range
    section, which would otherwise fail to import at all."""
    document, _report = parse_calvin_commentary_thml(ISAIAH_NO_WRAPPER_FIXTURE)
    by_id = {s["section_id"]: s for s in document["sections"]}
    range_section = by_id["ccel.calvin.calcom13.viii.i"]
    assert [l["canonical_passage"] for l in range_section["passage_links"]] == ["Isa.1.1-31"]


def test_non_citation_caption_text_is_not_guessed(tmp_path: Path) -> None:
    """Real corpus case: a "Tables and Indices" back-matter table in the
    Psalms commentary has a caption reading "Major subjects addressed in
    each Psalm" — table-formatted like a real scripture caption, but not a
    Bible citation at all. The plain-text fallback must refuse it (fail
    loudly, or via an explicit known_unmapped_sections exception) rather
    than inventing a passage from unrelated text."""
    text = HARMONY_LAW_PLAIN_CAPTION_FIXTURE.read_text(encoding="utf-8")
    mutated = text.replace(
        "deuteronomy 6:20-25", "Major subjects addressed in each Psalm"
    )
    assert mutated != text
    broken = tmp_path / "not_a_reference.xml"
    broken.write_text(mutated, encoding="utf-8")
    with pytest.raises(CalvinCommentaryImportError, match="no parseable passage"):
        parse_calvin_commentary_thml(broken)
    # The manifest's explicit exception mechanism handles exactly this case.
    exception = KnownUnmappedSection(
        div2_id="v.xiii",
        reason="Synthetic mutation of the plain-text caption fixture for this test.",
        classification="non_citation_backmatter",
    )
    document, report = parse_calvin_commentary_thml(
        broken, known_unmapped_sections={"v.xiii": exception}
    )
    assert [item["div2_id"] for item in report.unmapped_sections] == ["v.xiii"]
    by_id = {s["section_id"]: s for s in document["sections"]}
    assert by_id["ccel.calvin.calcom03.v.xiii"]["passage_links"] == []


# --- Full manifest-driven, multi-volume corpus build ----------------------


def test_manifest_known_unmapped_exceptions_are_threaded_through(tmp_path: Path) -> None:
    """The manifest's per-source known_unmapped_sections reaches the parser
    via import_calvin_corpus_from_manifest, not just the lower-level
    build_calvin_commentary_document/parse_calvin_commentary_thml calls."""
    from textus_kb.importers.calvin_commentary_thml import import_calvin_corpus_from_manifest
    from textus_kb.importers.calvin_source_fetch import CalvinSourceEntry

    text = HARMONY_LAW_PLAIN_CAPTION_FIXTURE.read_text(encoding="utf-8")
    mutated = text.replace(
        "deuteronomy 6:20-25", "Major subjects addressed in each Psalm"
    )
    broken = tmp_path / "not_a_reference.xml"
    broken.write_text(mutated, encoding="utf-8")

    entry = CalvinSourceEntry(
        id="test",
        title="Test",
        url="https://example.invalid/test.xml",
        local_path=broken,
        raw_sha256="0" * 64,
        known_unmapped_sections=(
            KnownUnmappedSection(
                div2_id="v.xiii",
                reason="Synthetic mutation of the plain-text caption fixture for this test.",
                classification="non_citation_backmatter",
            ),
        ),
    )
    report, parse_reports = import_calvin_corpus_from_manifest(
        [entry], database_path=tmp_path / "commentary.sqlite3"
    )
    assert report.section_count > 0
    assert [item["div2_id"] for item in parse_reports[0].unmapped_sections] == ["v.xiii"]
