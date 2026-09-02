"""General CCEL Calvin Commentary ThML/XML parser and importer.

Builds a normalized Commentary document (see
``textus_kb.importers.commentary_sqlite``) from a real CCEL Calvin
commentary ThML/XML file. Not specific to any one biblical book/volume:
the same code parses ``Commentary on Romans`` (a single, plain
chapter-by-chapter commentary) and ``Harmony of the Evangelists``
(a Gospel harmony where one section routinely links passages from two or
three different books).

Confirmed real-file structure (CCEL Calvin commentary ThML, verified
against calcom38 "Commentary on Romans" and calcom31 "Harmony of the
Evangelists, Part 1", both fetched from ccel.org):

- ``div1[type=front]``: preface / dedication / argument / title-page
  facsimiles. No passage. Becomes a passage-less "front" section.
- ``div1[type=chapter]`` (most volumes) or a single ``div1[type=section]``
  wrapping the whole body (the Harmony volume): the commentary body.
  Becomes a structural section with no passage of its own; its
  ``div2`` children are:
    - ``div2[type=scripture]``: one or more ``<scripRef>`` elements
      *inside its own ``<table>``, and not inside a ``<note>``,* give
      the quoted passage(s) — this is the section-defining passage (a
      range, or several passages for a Harmony section: CCEL marks a
      second/third non-contiguous parallel range within the same table
      the same way, e.g. Mark 9:49-50 *and* a later Mark 4:21 caption in
      the same column). A ``<scripRef>`` that *is* inside a ``<note>``
      within the table is a translator/editor footnote — most often the
      OT catena Paul himself quotes (e.g. Romans 3:10-18's footnote
      lists Psalms/Isaiah/Proverbs as "the references given in the
      margin"), or a plain cross-reference — confirmed on both real
      files to always sit inside ``<note>``, never as a bare table
      caption. It is excluded from passage_links, never stored. The
      quoted Bible text itself (inside the table) is never imported as
      chunk content — it is not Calvin's prose.
    - a plain (non-"scripture") sibling ``div2``: continuation
      commentary anchored to the *preceding* scripture div2 (CCEL split
      an unusually long verse's commentary into its own div2 instead of
      nesting it).
  Within both of the above, the actual per-verse commentary is marked by
  a ``<p>`` containing only a ``<scripCom>`` marker, immediately
  followed by a sibling ``<div class="Commentary">`` holding that
  verse's paragraphs. Each such pair becomes a child "verse_commentary"
  section, with its passage taken from the ``scripCom``'s own
  ``osisRef`` (always a single verse, or occasionally chapter-only —
  chapter-only is kept as a passage-less section, not invented).
- Inline ``<scripRef>`` elements that appear in running commentary
  prose (cross-references Calvin mentions in passing) are never
  consulted for passage_links — only ``<scripRef>`` inside a
  ``type=scripture`` div2's own ``<table>``, and ``<scripCom>``
  markers, are section-defining.

Fail-loudly policy: a ``type=scripture`` div2 whose own table yields no
parseable passage, or a ``scripCom`` marker that is present but fails
to classify as a valid verse/chapter-only reference, raises
``CalvinCommentaryImportError`` — never guessed or dropped silently.

No network. No schema change. No Calvin-specific field in the shared
Commentary schema — everything Calvin-specific lives in this module.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.ccel_thml_core import (
    CcelThmlCoreError,
    ScriptureRefStats,
    child_text,
    dc_text,
    electronic_book_id,
    element_plain_text,
    find_child,
    local_tag,
    paragraph_plain_text,
    parse_thml_file,
    scripture_candidates,
)

IMPORT_MODE_CALVIN_COMMENTARY_THML = "calvin_commentary_thml"
IMPORTER_NAME = "textus_kb.importers.calvin_commentary_thml"
IMPORTER_VERSION = "0.1.0"

AUTHOR_CONTRIBUTOR_ID = "ccel.calvin"
AUTHOR_NAME_FALLBACK = "John Calvin"

# Closed, small, and extensible only by adding to this set (not by a
# separate mechanism) — every known_unmapped_sections entry must classify
# as one of these, so the taxonomy stays honest rather than free text.
ALLOWED_UNMAPPED_CLASSIFICATIONS = frozenset(
    {
        "transcription_error",
        "incomplete_citation",
        "disjoint_verse_list",
        "non_citation_backmatter",
    }
)


class CalvinCommentaryImportError(CcelThmlCoreError):
    """Raised when a Calvin commentary ThML file cannot be parsed/imported."""


@dataclass(frozen=True)
class KnownUnmappedSection:
    """One individually-audited, explicitly declared exception: a real
    scripture-table section whose passage cannot be resolved without
    guessing (see ``ALLOWED_UNMAPPED_CLASSIFICATIONS`` for why). Declared
    in the source manifest, never invented by the parser itself — this is
    documentation with teeth, not a silent allowlist: ``reason`` and
    ``classification`` are threaded all the way into the built
    commentary.sqlite3 (via import_batches.report) so QA can report a
    dedicated ``known_unmapped`` category instead of an unexplained gap.
    """

    div2_id: str
    reason: str
    classification: str

    def __post_init__(self) -> None:
        if self.classification not in ALLOWED_UNMAPPED_CLASSIFICATIONS:
            raise CalvinCommentaryImportError(
                f"Unsupported known_unmapped classification: {self.classification!r}. "
                f"Allowed: {sorted(ALLOWED_UNMAPPED_CLASSIFICATIONS)}"
            )
        if not self.reason.strip():
            raise CalvinCommentaryImportError(
                f"known_unmapped section {self.div2_id!r} must have a non-empty reason."
            )


@dataclass
class CalvinCommentaryParseReport:
    book_id: str
    work_id: str
    edition_id: str
    front_section_count: int = 0
    range_section_count: int = 0
    verse_section_count: int = 0
    passage_link_count: int = 0
    chunk_count: int = 0
    chapter_only_scripcom_count: int = 0
    multi_passage_range_count: int = 0
    unmapped_sections: list[dict[str, str]] = field(default_factory=list)
    scripture: ScriptureRefStats = field(default_factory=ScriptureRefStats)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scripture"] = self.scripture.to_dict()
        return payload


def parse_calvin_commentary_thml(
    xml_path: str | Path,
    *,
    work_group: str | None = None,
    work_title: str | None = None,
    translator_override: str | None = None,
    known_unmapped_sections: dict[str, KnownUnmappedSection] | None = None,
) -> tuple[dict[str, Any], CalvinCommentaryParseReport]:
    """Parse one real CCEL Calvin commentary ThML file into a normalized
    Commentary document (contributors/works/work_contributors/editions/
    sections/chunks — matching ``commentary_sqlite.normalize_commentary_document``
    input shape). ``source_files``/``import_batches`` are NOT included here;
    the caller attaches those from the raw file it actually read (this
    function only sees parsed XML, not the raw bytes/hash).

    ``work_group``/``work_title``: when a multi-volume Calvin commentary
    (e.g. Psalms across 5 CCEL files) should collapse to one logical
    ``work`` row spanning several ``editions`` (one per volume/file), pass
    the SAME ``work_group`` key (and the same ``work_title``) for every
    volume in that group — driven by the source manifest's declarative
    grouping, never hardcoded here. Each volume still gets its own
    file-derived ``edition_id`` (so sections never collide across
    volumes) and carries its own per-file title in ``edition_label``.
    Omit both to keep the previous one-file-one-work behavior.

    ``translator_override``: use this exact translator name instead of the
    file's own DC.Creator[Translator] text. CCEL's own metadata is not
    internally consistent for some translators across a work_group's
    volumes (e.g. "Charles William Bingham" in one Harmony of the Law
    volume vs. "Bingham, Charles William" in the others) — without an
    override each variant would derive a different contributor_id for the
    same real person. The source manifest is expected to supply this when
    it knows the volumes disagree; never guessed here.

    ``known_unmapped_sections``: an explicit, individually-audited map of
    this file's own div2 ``id`` -> ``KnownUnmappedSection`` (reason +
    classification) whose own quotation-table citation is confirmed
    malformed/non-citation in the source and cannot be resolved without
    guessing. Listed sections import as ONE passage-less structural
    section (their real Calvin prose is kept; only the passage_link is
    omitted) instead of raising — and their reason/classification is
    carried into the built store's import_batches.report so QA can show
    a dedicated ``known_unmapped`` category, never a silent gap. Every
    other unparseable scripture section still fails loudly — this is not
    a blanket fallback.
    """
    known_unmapped_sections = known_unmapped_sections or {}
    root = parse_thml_file(xml_path)
    if local_tag(root.tag) != "ThML":
        raise CalvinCommentaryImportError(f"Expected ThML root, got {local_tag(root.tag)!r}.")
    head = find_child(root, "ThML.head")
    body = find_child(root, "ThML.body")
    if body is None:
        raise CalvinCommentaryImportError("ThML.body is missing.")

    book_id = electronic_book_id(head)
    if not book_id:
        raise CalvinCommentaryImportError("Missing electronicEdInfo/bookID.")

    if work_group:
        work_id = f"ccel.calvin.work.{work_group}"
    else:
        work_id = f"ccel.calvin.{book_id}"
    edition_id = f"ccel.calvin.{book_id}.edition"
    section_prefix = f"ccel.calvin.{book_id}"

    contributors, work_contributors, contributor_source_names = _contributors(
        head, work_id=work_id, edition_id=edition_id, translator_override=translator_override
    )
    work = _work_record(head, work_id=work_id, title_override=work_title)
    edition = _edition_record(head, work_id=work_id, edition_id=edition_id, book_id=book_id)

    stats = ScriptureRefStats()
    report = CalvinCommentaryParseReport(
        book_id=book_id, work_id=work_id, edition_id=edition_id, scripture=stats
    )
    sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []

    div1_list = [child for child in list(body) if local_tag(child.tag) == "div1"]
    if not div1_list:
        raise CalvinCommentaryImportError("ThML.body has no div1 elements.")

    for index, div1 in enumerate(div1_list, start=1):
        div1_type = (div1.get("type") or "").strip().lower()
        div1_id = (div1.get("id") or "").strip()
        if not div1_id:
            raise CalvinCommentaryImportError("div1 is missing a stable id.")
        div1_section_id = f"{section_prefix}.{div1_id}"

        has_table_div2 = any(
            local_tag(child.tag) == "div2" and find_child(child, "table") is not None
            for child in list(div1)
        )
        if not has_table_div2:
            # Auxiliary matter: preface/dedication/argument ("front"),
            # a continuous translation appendix ("back" — e.g. Romans'
            # "Translation of Romans", div2s literally titled "Chapter 1",
            # "Chapter 2"... with NO table: a running translation, not
            # verse-by-verse commentary), an auto-generated index (no
            # type attribute at all), or any other non-commentary div1.
            # Classified structurally — by whether it actually contains a
            # scripture div2 that itself has a <table> — rather than by
            # its own `type` attribute value, because that value is NOT
            # consistent across the corpus: confirmed real values include
            # "chapter" (most books), "section" (the Harmony volume, one
            # div1 for its whole body), and "Psalm" (the Psalms
            # commentary, one div1 per psalm) — an explicit allowlist of
            # type names would silently misclassify the next volume that
            # uses yet another label. The table requirement matters
            # separately: a div1 can have `type="scripture"` div2 children
            # that are pure quoted text with no table (the "back"
            # appendix case above) — those must not count as evidence
            # this div1 is real commentary. None of these non-commentary
            # div1s follow the verse-by-verse scripCom/table convention,
            # so they are imported as one passage-less section rather
            # than forced through the strict commentary-body parser.
            sections.append(
                _section_row(
                    section_id=div1_section_id,
                    edition_id=edition_id,
                    parent_section_id=None,
                    section_type=div1_type or "auxiliary",
                    heading=_attr_or_none(div1.get("title")),
                    sequence=index,
                )
            )
            report.front_section_count += 1
            text = element_plain_text(div1, skip_notes=False)
            if text:
                chunks.append(
                    _chunk_row(
                        chunk_id=f"{div1_section_id}.chunk",
                        section_id=div1_section_id,
                        sequence=1,
                        text=text,
                        locator=f"ccel:calvin/{book_id}#{div1_id}",
                    )
                )
                report.chunk_count += 1
            continue

        # Commentary body div1 (type="chapter" for most volumes, or
        # type="section" for the Harmony volume, which wraps its entire
        # body in a single div1).
        sections.append(
            _section_row(
                section_id=div1_section_id,
                edition_id=edition_id,
                parent_section_id=None,
                section_type=div1_type or "chapter",
                heading=_attr_or_none(div1.get("title")),
                sequence=index,
            )
        )

        div1_chapter_number = _div1_chapter_number(div1)
        div2_list = [child for child in list(div1) if local_tag(child.tag) == "div2"]
        current_range_section_id: str | None = None
        for div2_index, div2 in enumerate(div2_list, start=1):
            div2_type = (div2.get("type") or "").strip().lower()
            div2_id = (div2.get("id") or "").strip()
            if not div2_id:
                raise CalvinCommentaryImportError(
                    f"div2 under {div1_id!r} is missing a stable id."
                )
            div2_section_id = f"{section_prefix}.{div2_id}"
            table = find_child(div2, "table")

            # A range-defining div2 is identified by having its own <table>
            # (the quoted-passage block), not by its `type` attribute:
            # confirmed real value is usually "scripture", but some volumes
            # (Harmony of the Law) label the identical table-bearing
            # structure "section" or "Chapter" instead — an explicit
            # allowlist of type names would misclassify those as
            # untyped-continuation divs. This mirrors the same
            # table-presence signal already used to classify div1s.
            if table is not None:
                links = _table_passage_links(table, stats, expected_chapter=div1_chapter_number)
                if not links:
                    exception = known_unmapped_sections.get(div2_id)
                    if exception is None:
                        raise CalvinCommentaryImportError(
                            f"Scripture section {div2_id!r} has no parseable passage "
                            "in its own quotation table."
                        )
                    report.unmapped_sections.append(
                        {
                            "div2_id": div2_id,
                            "section_id": div2_section_id,
                            "reason": exception.reason,
                            "classification": exception.classification,
                        }
                    )
                    sections.append(
                        _section_row(
                            section_id=div2_section_id,
                            edition_id=edition_id,
                            parent_section_id=div1_section_id,
                            section_type="commentary_passage_unmapped",
                            heading=_attr_or_none(div2.get("title")),
                            sequence=div2_index,
                        )
                    )
                    text = element_plain_text(div2, skip_notes=False)
                    if text:
                        chunks.append(
                            _chunk_row(
                                chunk_id=f"{div2_section_id}.chunk",
                                section_id=div2_section_id,
                                sequence=1,
                                text=text,
                                locator=f"ccel:calvin/{book_id}#{div2_id}",
                            )
                        )
                        report.chunk_count += 1
                    current_range_section_id = div2_section_id
                    continue
                sections.append(
                    _section_row(
                        section_id=div2_section_id,
                        edition_id=edition_id,
                        parent_section_id=div1_section_id,
                        section_type="commentary_passage",
                        heading=_attr_or_none(div2.get("title")),
                        sequence=div2_index,
                        passage_links=links,
                    )
                )
                report.range_section_count += 1
                report.passage_link_count += len(links)
                if len(links) > 1:
                    report.multi_passage_range_count += 1
                current_range_section_id = div2_section_id

                verse_sections, verse_chunks, leading_text = _extract_verse_sections(
                    container=div2,
                    exclude=table,
                    parent_section_id=div2_section_id,
                    section_prefix=f"{div2_section_id}",
                    edition_id=edition_id,
                    book_id=book_id,
                    stats=stats,
                    report=report,
                )
                sections.extend(verse_sections)
                chunks.extend(verse_chunks)
                if leading_text:
                    chunks.append(
                        _chunk_row(
                            chunk_id=f"{div2_section_id}.chunk",
                            section_id=div2_section_id,
                            sequence=1,
                            text=leading_text,
                            locator=f"ccel:calvin/{book_id}#{div2_id}",
                        )
                    )
                    report.chunk_count += 1
                continue

            # Untyped sibling div2: usually a continuation anchored to the
            # most recently seen scripture-range section (Romans-style —
            # Calvin's exposition of a range's first verse split into its
            # own div2). When NO scripture-range div2 precedes it in this
            # div1 at all — a real corpus case: Ezekiel/Daniel/Jeremiah's
            # `type="lecture"` div2 opens each chapter with introductory
            # prose before any verse-range content begins — it becomes its
            # own passage-less section under the div1 instead of being
            # forced onto a range that doesn't exist.
            standalone_intro = current_range_section_id is None
            if standalone_intro:
                sections.append(
                    _section_row(
                        section_id=div2_section_id,
                        edition_id=edition_id,
                        parent_section_id=div1_section_id,
                        section_type=div2_type or "commentary_intro",
                        heading=_attr_or_none(div2.get("title")),
                        sequence=div2_index,
                    )
                )
            anchor_section_id = div2_section_id if standalone_intro else current_range_section_id
            verse_sections, verse_chunks, leading_text = _extract_verse_sections(
                container=div2,
                exclude=None,
                parent_section_id=anchor_section_id,
                section_prefix=f"{div2_section_id}",
                edition_id=edition_id,
                book_id=book_id,
                stats=stats,
                report=report,
            )
            if verse_sections:
                sections.extend(verse_sections)
                chunks.extend(verse_chunks)
                if leading_text:
                    # Unmarked lead-in text belongs to the anchor section
                    # (an existing range it continues, or its own new
                    # standalone intro section), not a further new one.
                    chunks.append(
                        _chunk_row(
                            chunk_id=f"{div2_section_id}.lead.chunk",
                            section_id=anchor_section_id,
                            sequence=1 if standalone_intro else 99,
                            text=leading_text,
                            locator=f"ccel:calvin/{book_id}#{div2_id}",
                        )
                    )
                    report.chunk_count += 1
            elif leading_text:
                # No scripCom at all in this div2: fold its whole text into
                # the anchor section (benign layout variation, not a
                # structurally uncertain passage).
                chunks.append(
                    _chunk_row(
                        chunk_id=f"{div2_section_id}.chunk",
                        section_id=anchor_section_id,
                        sequence=1 if standalone_intro else 99,
                        text=leading_text,
                        locator=f"ccel:calvin/{book_id}#{div2_id}",
                    )
                )
                report.chunk_count += 1

    document = {
        "contributors": contributors,
        "works": [work],
        "work_contributors": work_contributors,
        "editions": [edition],
        "contributor_source_names": contributor_source_names,
        "sections": sections,
        "chunks": chunks,
    }
    report.chapter_only_scripcom_count = stats.skipped_chapter_only
    return document, report


_IDENTICAL_OK_KINDS = frozenset({"contributors", "works"})
_ID_FIELD_BY_KIND = {
    "contributors": "contributor_id",
    "works": "work_id",
    "editions": "edition_id",
    "source_files": "source_file_id",
    "import_batches": "batch_id",
    "sections": "section_id",
    "chunks": "chunk_id",
}


def build_calvin_commentary_document(
    xml_path: str | Path,
    *,
    imported_at: str | None = None,
    work_group: str | None = None,
    work_title: str | None = None,
    translator_override: str | None = None,
    known_unmapped_sections: dict[str, KnownUnmappedSection] | None = None,
) -> tuple[dict[str, Any], CalvinCommentaryParseReport]:
    """Parse one Calvin commentary ThML file and attach its own
    source_files/import_batches provenance rows (raw SHA-256 computed from
    the actual bytes on disk, not invented). See ``parse_calvin_commentary_thml``
    for ``work_group``/``work_title``/``translator_override``/
    ``known_unmapped_sections``."""
    path = Path(xml_path)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise CalvinCommentaryImportError(f"Cannot read ThML file: {path}") from exc
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    document, report = parse_calvin_commentary_thml(
        path,
        work_group=work_group,
        work_title=work_title,
        known_unmapped_sections=known_unmapped_sections,
        translator_override=translator_override,
    )
    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_file_id = f"{report.edition_id}.source"
    batch_id = f"{report.edition_id}.batch.1"
    document["source_files"] = [
        {
            "source_file_id": source_file_id,
            "edition_id": report.edition_id,
            "file_name": path.name,
            "raw_sha256": raw_sha256,
            "byte_size": len(raw_bytes),
            "retrieved_at": when,
        }
    ]
    document["import_batches"] = [
        {
            "batch_id": batch_id,
            "source_file_id": source_file_id,
            "importer_name": IMPORTER_NAME,
            "importer_version": IMPORTER_VERSION,
            "imported_at": when,
            "report": {
                "book_id": report.book_id,
                "section_count": len(document["sections"]),
                "chunk_count": len(document["chunks"]),
                "passage_link_count": report.passage_link_count,
                "multi_passage_range_count": report.multi_passage_range_count,
                "known_unmapped_sections": report.unmapped_sections,
            },
        }
    ]
    return document, report


def merge_calvin_commentary_documents(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine multiple per-file Calvin commentary documents into one.

    Cross-file duplicates are allowed only for contributors/works when the
    record is byte-identical (the same Calvin author or translator
    re-declared by every file); anything else colliding on id is a real
    error, not silently deduplicated.
    """
    if not documents:
        raise CalvinCommentaryImportError("No Calvin commentary documents to merge.")
    merged: dict[str, list[dict[str, Any]]] = {kind: [] for kind in _ID_FIELD_BY_KIND}
    merged["work_contributors"] = []
    merged["contributor_source_names"] = []
    index: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in _ID_FIELD_BY_KIND}
    seen_work_contributors: set[tuple[str, str, str]] = set()
    seen_source_names: set[tuple[str, str]] = set()

    for document in documents:
        for kind, id_field in _ID_FIELD_BY_KIND.items():
            for item in document.get(kind) or []:
                item_id = str(item.get(id_field) or "").strip()
                if not item_id:
                    raise CalvinCommentaryImportError(f"Document {kind} entry missing {id_field}.")
                existing = index[kind].get(item_id)
                if existing is None:
                    merged[kind].append(item)
                    index[kind][item_id] = item
                    continue
                if kind in _IDENTICAL_OK_KINDS and existing == item:
                    continue
                raise CalvinCommentaryImportError(
                    f"Duplicate {kind} id across combined Calvin sources: {item_id!r}."
                )
        for wc in document.get("work_contributors") or []:
            key = (
                str(wc.get("work_id") or ""),
                str(wc.get("contributor_id") or ""),
                str(wc.get("role") or ""),
            )
            if key in seen_work_contributors:
                continue
            seen_work_contributors.add(key)
            merged["work_contributors"].append(wc)
        for entry in document.get("contributor_source_names") or []:
            # (contributor_id, edition_id) is unique by construction — each
            # edition_id comes from exactly one source file — so this is
            # just a defensive dedupe, not an expected real collision.
            key = (str(entry.get("contributor_id") or ""), str(entry.get("edition_id") or ""))
            if key in seen_source_names:
                continue
            seen_source_names.add(key)
            merged["contributor_source_names"].append(entry)

    return merged


def import_calvin_commentary_sqlite(
    xml_paths: list[str | Path],
    *,
    database_path: str | Path | None = None,
    atomic: bool = True,
    imported_at: str | None = None,
):
    """Parse one or more Calvin commentary ThML files, merge them, and write
    a commentary.sqlite3 store in one atomic build. Imported here (not at
    module level) to avoid a hard import-time dependency from the shared
    Commentary schema module onto this Calvin-specific parser.

    ``imported_at`` is generated once up front (a single UTC timestamp
    shared by every file's provenance row) unless the caller pins one
    explicitly. Two builds of the same inputs are otherwise not guaranteed
    byte-identical: each file's source_files/import_batches row embeds a
    real timestamp, and a build spanning a wall-clock second boundary would
    otherwise produce a different content_hash purely from that clock
    read, not from any actual content change. Pin ``imported_at`` whenever
    a reproducible, comparable content_hash matters (tests, corpus
    rebuilds meant to be diffed against a prior run).
    """
    from textus_kb.importers.commentary_sqlite import import_commentary_sqlite

    if not xml_paths:
        raise CalvinCommentaryImportError("Provide at least one Calvin ThML source path.")
    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    documents = []
    reports = []
    for xml_path in xml_paths:
        document, report = build_calvin_commentary_document(xml_path, imported_at=when)
        documents.append(document)
        reports.append(report)
    merged = merge_calvin_commentary_documents(documents)
    result = import_commentary_sqlite(
        document=merged,
        database_path=database_path,
        import_mode=IMPORT_MODE_CALVIN_COMMENTARY_THML,
        atomic=atomic,
    )
    return result, reports


def import_calvin_corpus_from_manifest(
    entries: list[Any],
    *,
    database_path: str | Path | None = None,
    atomic: bool = True,
    imported_at: str | None = None,
):
    """Build one commentary.sqlite3 from a list of
    ``textus_kb.importers.calvin_source_fetch.CalvinSourceEntry`` (already
    fetched — ``entry.local_path`` must exist and match its pinned
    ``raw_sha256``; this function does not fetch). Entries sharing the same
    ``work_group`` collapse into one logical ``work`` spanning several
    ``editions`` (one per volume); an entry with no ``work_group`` is its
    own single-volume work — driven entirely by the manifest, nothing
    Calvin-specific hardcoded here about which books group together.
    """
    from textus_kb.importers.commentary_sqlite import import_commentary_sqlite

    if not entries:
        raise CalvinCommentaryImportError("Provide at least one manifest entry.")
    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    documents = []
    reports = []
    for entry in entries:
        known_unmapped = {
            item.div2_id: item
            for item in getattr(entry, "known_unmapped_sections", ())
        }
        document, report = build_calvin_commentary_document(
            entry.local_path,
            imported_at=when,
            work_group=(entry.work_group or None),
            work_title=(entry.work_title or None),
            translator_override=(entry.translator or None),
            known_unmapped_sections=known_unmapped,
        )
        documents.append(document)
        reports.append(report)
    merged = merge_calvin_commentary_documents(documents)
    result = import_commentary_sqlite(
        document=merged,
        database_path=database_path,
        import_mode=IMPORT_MODE_CALVIN_COMMENTARY_THML,
        atomic=atomic,
    )
    return result, reports


_VERSE_TAIL_RE = re.compile(r"^\s*[:.\-]\s*(\d+(?:\s*[-,]\s*\d+)*)\s*$")
_CHAPTER_ONLY_OSIS_RE = re.compile(r"^([A-Za-z0-9]+)\.(\d+)$")
_TRAILING_NUMBER_RE = re.compile(r"(\d+)\s*$")
_CAPTION_CONNECTOR_WORD_RE = re.compile(r"\b(?:Chapters?|Verses?)\b", re.IGNORECASE)


def _div1_chapter_number(div1: ET.Element) -> int | None:
    """The chapter/psalm number this div1 itself declares (from its own
    title, e.g. "Chapter 2" -> 2, "Psalm 34" -> 34), used only to verify a
    chapter-only caption reconstruction (see
    ``_reconstruct_chapter_only_caption``) — never to invent a passage on
    its own."""
    match = _TRAILING_NUMBER_RE.search((div1.get("title") or "").strip())
    return int(match.group(1)) if match else None


def _table_passage_links(
    table: ET.Element, stats: ScriptureRefStats, *, expected_chapter: int | None
) -> list[dict[str, str]]:
    scrip_refs = _collect_caption_scriprefs(table)
    links: list[dict[str, str]] = []
    seen_canonical: set[str] = set()
    for ref in scrip_refs:
        reconstructed = _reconstruct_chapter_only_caption(ref, expected_chapter=expected_chapter)
        candidates = [reconstructed] if reconstructed else scripture_candidates(ref, stats)
        if reconstructed:
            stats.seen += 1
            stats.imported += 1
        for candidate in candidates:
            canonical = candidate["canonical_passage"]
            if canonical in seen_canonical:
                stats.duplicate_links += 1
                continue
            seen_canonical.add(canonical)
            links.append(candidate)
    if not links:
        fallback = _plain_text_caption_fallback(table)
        if fallback is not None:
            stats.seen += 1
            stats.imported += 1
            links.append(fallback)
    # The first accepted caption in document order is the section's
    # primary commented passage; any further one (a Harmony section's
    # second/third parallel-gospel column, or a continuation caption like
    # Mark 4:21 later in the same column) is explicitly "parallel" — never
    # inferred later from row insertion order.
    for index, link in enumerate(links):
        link["relation_type"] = "primary" if index == 0 else "parallel"
    return links


def _plain_text_caption_fallback(table: ET.Element) -> dict[str, str] | None:
    """Some CCEL volumes (confirmed: Harmony of the Law) render a table's
    caption as bare text with no <scripRef> markup at all, e.g.
    ``<p class="TableCaption16">deuteronomy 6:20-25</p>``. When a table has
    NO scripRef caption whatsoever, parse the first row's first cell's own
    paragraph text with the same general-purpose reference parser already
    trusted for raw_citation fallback elsewhere in this codebase
    (``CanonicalReference.parse``) — not a heuristic invented for Calvin,
    just applying the existing strict parser to explicit, human-readable
    citation text that is present in the document. Returns None (no
    guessing) if the row structure is unexpected or the text does not
    parse as a clean single reference.
    """
    first_row = find_child(table, "tr")
    if first_row is None:
        return None
    first_cell = find_child(first_row, "td")
    if first_cell is None:
        return None
    caption_p = find_child(first_cell, "p")
    if caption_p is None:
        return None
    text = element_plain_text(caption_p, skip_notes=True)
    if not text:
        return None
    # Strip purely decorative connector words some volumes insert between
    # the book name and the chapter:verse numbers (confirmed real
    # captions: "Isaiah Chapter 1:1-31", "Philemon Verses 8-14") — the
    # word carries no information the numbers don't already give, and
    # CanonicalReference.parse does not otherwise accept it.
    normalized = _CAPTION_CONNECTOR_WORD_RE.sub(" ", text).strip()
    try:
        reference = CanonicalReference.parse(normalized)
    except CanonicalReferenceError:
        return None
    return {"canonical_passage": reference.canonical_string(), "raw_citation": text}


def _reconstruct_chapter_only_caption(
    ref: ET.Element, *, expected_chapter: int | None
) -> dict[str, str] | None:
    """Recover a verse range CCEL split across a scripRef/tail boundary.

    Only when SAFE: the scripRef's own osisRef must be exactly
    "Book.N" (chapter-only, no verse) AND N must match the enclosing
    div1's own declared chapter/psalm number (``expected_chapter``) —
    confirming N really is the chapter, not a mis-encoded verse number.
    Real corpus counter-example that this guard exists for: Psalm 34's
    "Psalm 15-17" caption has osisRef "Ps.15" with tail "-17" — but "15"
    here is NOT chapter 15, it is verse 15 *of the enclosing Psalm 34*
    (a CCEL transcription slip). Since 15 != expected_chapter (34), this
    function correctly refuses to reconstruct it — that case is instead
    an explicit, individually-audited known_unmapped_sections exception.
    Confirmed-safe real case: Acts 2's "Acts 2: 5-12" caption has osisRef
    "Acts.2" with tail ": 5-12"; div1 is "Chapter 2", so 2 == 2 and the
    reconstruction to Acts.2.5-12 is correct.

    Also requires the tail text (immediately after the closing tag,
    within the same table cell) to be nothing but a clean verse or
    verse-range preceded by ':', '.', or '-' — any other shape (or no
    tail at all) returns None rather than guessing.
    """
    if expected_chapter is None:
        return None
    osis_raw = (ref.get("osisRef") or "").strip()
    if osis_raw.lower().startswith("bible:"):
        osis_raw = osis_raw.split(":", 1)[1].strip()
    if " " in osis_raw:
        return None  # multi-token osisRef: not the single chapter-only case
    match = _CHAPTER_ONLY_OSIS_RE.fullmatch(osis_raw)
    if not match:
        return None
    book_token, chapter_str = match.group(1), match.group(2)
    if int(chapter_str) != expected_chapter:
        return None
    tail_match = _VERSE_TAIL_RE.match(ref.tail or "")
    if not tail_match:
        return None
    verse_numbers = [int(v) for v in re.findall(r"\d+", tail_match.group(1))]
    if not verse_numbers:
        return None
    start_verse, end_verse = verse_numbers[0], verse_numbers[-1]
    if end_verse < start_verse:
        return None
    synthetic = (
        f"{book_token}.{expected_chapter}.{start_verse}"
        if start_verse == end_verse
        else f"{book_token}.{expected_chapter}.{start_verse}-{end_verse}"
    )
    try:
        reference = CanonicalReference.parse(synthetic)
    except CanonicalReferenceError:
        return None
    display = (ref.get("passage") or "").strip()
    tail_text = (ref.tail or "").strip()
    raw_citation = f"{display}{tail_text}" if display else reference.canonical_string()
    return {"canonical_passage": reference.canonical_string(), "raw_citation": raw_citation}


def _collect_caption_scriprefs(root: ET.Element) -> list[ET.Element]:
    """<scripRef> elements in ``root``, excluding any inside a <note>.

    Verified against both real Calvin volumes: every table-scoped
    scripRef that is NOT inside a <note> is a genuine primary/parallel
    passage caption (regardless of its CSS class — CCEL uses several
    different auto-generated class names for these), and every one that
    IS inside a <note> is a footnote-style cross-reference. There is no
    ambiguous third case in the confirmed structure.
    """
    found: list[ET.Element] = []

    def walk(node: ET.Element) -> None:
        for child in list(node):
            tag = local_tag(child.tag)
            if tag == "note":
                continue
            if tag == "scripRef":
                found.append(child)
            walk(child)

    walk(root)
    return found


def _extract_verse_sections(
    *,
    container: ET.Element,
    exclude: ET.Element | None,
    parent_section_id: str,
    section_prefix: str,
    edition_id: str,
    book_id: str,
    stats: ScriptureRefStats,
    report: CalvinCommentaryParseReport,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Split ``container``'s direct children on <p><scripCom/></p> markers.

    Everything between one marker and the next (or the end of the
    container) belongs to that marker's verse — confirmed real content
    takes two different shapes across the corpus: a single wrapping
    ``<div class="Commentary">`` (Romans/Harmony/Psalms/Acts) or a run of
    plain sibling ``<p>`` elements with no wrapper at all (Isaiah). Both
    are collected the same way here; only the boundary (the next marker)
    matters, not what tag the content between two markers happens to use.

    Returns (sections, chunks, leading_text) where leading_text is any
    content before the first scripCom marker (belongs to the caller).
    """
    sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    leading_parts: list[str] = []
    pending_marker: ET.Element | None = None
    pending_content: list[ET.Element] = []
    verse_index = 0

    def flush() -> None:
        nonlocal verse_index, pending_marker, pending_content
        if pending_marker is None:
            return
        verse_index += 1
        _finalize_verse_section(
            marker=pending_marker,
            content_elements=pending_content,
            sections=sections,
            chunks=chunks,
            parent_section_id=parent_section_id,
            section_id=f"{section_prefix}.v{verse_index}",
            edition_id=edition_id,
            book_id=book_id,
            sequence=verse_index,
            stats=stats,
            report=report,
        )
        pending_marker = None
        pending_content = []

    for child in list(container):
        if child is exclude:
            continue
        marker = _as_scripcom_marker(child)
        if marker is not None:
            flush()
            pending_marker = marker
            continue
        if pending_marker is not None:
            pending_content.append(child)
            continue
        text = paragraph_plain_text(child) if local_tag(child.tag) == "p" else ""
        if text:
            leading_parts.append(text)

    flush()

    return sections, chunks, "\n\n".join(leading_parts)


def _as_scripcom_marker(element: ET.Element) -> ET.Element | None:
    if local_tag(element.tag) != "p":
        return None
    children = list(element)
    if len(children) != 1 or local_tag(children[0].tag) != "scripCom":
        return None
    if (element.text or "").strip():
        return None
    return children[0]


def _finalize_verse_section(
    *,
    marker: ET.Element,
    content_elements: list[ET.Element],
    sections: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    parent_section_id: str,
    section_id: str,
    edition_id: str,
    book_id: str,
    sequence: int,
    stats: ScriptureRefStats,
    report: CalvinCommentaryParseReport,
) -> None:
    candidates = scripture_candidates(marker, stats)
    passage_display = (marker.get("passage") or "").strip()
    if candidates:
        links = [{**candidates[0], "relation_type": "primary"}]
        heading = candidates[0]["canonical_passage"]
    else:
        # Legitimate chapter-only / non-versed aside: no passage_link, but
        # never silently dropped from the corpus.
        links = []
        heading = passage_display or None
    if len(candidates) > 1:
        # A single scripCom marker referring to more than one verse is not
        # part of the confirmed real-file structure; treat as uncertain.
        raise CalvinCommentaryImportError(
            f"scripCom in {section_id!r} classified to more than one passage; "
            "structurally uncertain."
        )

    sections.append(
        _section_row(
            section_id=section_id,
            edition_id=edition_id,
            parent_section_id=parent_section_id,
            section_type="verse_commentary",
            heading=heading,
            sequence=sequence,
            passage_links=links,
        )
    )
    report.verse_section_count += 1
    report.passage_link_count += len(links)

    text_parts = [element_plain_text(el, skip_notes=True) for el in content_elements]
    notes = _notes_text(content_elements)
    parts = [part for part in (*text_parts, notes) if part]
    full_text = "\n\n".join(parts)
    if full_text:
        chunks.append(
            _chunk_row(
                chunk_id=f"{section_id}.chunk",
                section_id=section_id,
                sequence=1,
                text=full_text,
                locator=f"ccel:calvin/{book_id}#{marker.get('id') or section_id}",
            )
        )
        report.chunk_count += 1


def _notes_text(elements: list[ET.Element]) -> str:
    from textus_kb.importers.ccel_thml_core import collect_notes

    notes = collect_notes(elements)
    return "\n\n".join(notes)


def _section_row(
    *,
    section_id: str,
    edition_id: str,
    parent_section_id: str | None,
    section_type: str,
    heading: str | None,
    sequence: int,
    passage_links: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "edition_id": edition_id,
        "parent_section_id": parent_section_id,
        "section_type": section_type,
        "heading": heading,
        "sequence": sequence,
        "passage_links": [
            {
                "raw_citation": link["raw_citation"],
                "canonical_passage": link["canonical_passage"],
                "relation_type": link["relation_type"],
            }
            for link in (passage_links or [])
        ],
    }


def _chunk_row(
    *, chunk_id: str, section_id: str, sequence: int, text: str, locator: str
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "section_id": section_id,
        "sequence": sequence,
        "text": text,
        "plain_text": text,
        "source_locator": locator,
    }


def _contributors(
    head: ET.Element | None,
    *,
    work_id: str,
    edition_id: str,
    translator_override: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    author_raw_name = dc_text(head, "DC.Creator", sub="Author", scheme="short-form")
    author_name = author_raw_name or AUTHOR_NAME_FALLBACK
    contributors = [
        {
            "contributor_id": AUTHOR_CONTRIBUTOR_ID,
            "canonical_name": author_name,
            "birth_year": 1509,
            "death_year": 1564,
        }
    ]
    work_contributors = [
        {"work_id": work_id, "contributor_id": AUTHOR_CONTRIBUTOR_ID, "role": "author"}
    ]
    contributor_source_names: list[dict[str, Any]] = []
    if author_raw_name:
        contributor_source_names.append(
            {
                "contributor_id": AUTHOR_CONTRIBUTOR_ID,
                "edition_id": edition_id,
                "raw_name": author_raw_name,
            }
        )

    # The raw upstream name is recorded only when the edition itself states
    # one; a work_group-level translator_override is a corpus-building
    # convenience (unifying spelling across a multi-volume work) and is not,
    # by itself, evidence of what this specific edition's title page says.
    translator_source_name = dc_text(head, "DC.Creator", sub="Translator", scheme="short-form")
    translator_name = translator_override or translator_source_name
    if translator_name:
        translator_id = f"ccel.calvin.translator.{_slug(translator_name)}"
        contributors.append(
            {
                "contributor_id": translator_id,
                "canonical_name": translator_name,
                "birth_year": None,
                "death_year": None,
            }
        )
        work_contributors.append(
            {"work_id": work_id, "contributor_id": translator_id, "role": "translator"}
        )
        if translator_source_name:
            contributor_source_names.append(
                {
                    "contributor_id": translator_id,
                    "edition_id": edition_id,
                    "raw_name": translator_source_name,
                }
            )
    return contributors, work_contributors, contributor_source_names


def _work_record(
    head: ET.Element | None, *, work_id: str, title_override: str | None = None
) -> dict[str, Any]:
    title = (
        title_override
        or dc_text(head, "DC.Title", sub="Main")
        or dc_text(head, "DC.Title")
        or "Calvin Commentary"
    )
    return {
        "work_id": work_id,
        "title": title,
        "original_title": None,
        "original_language": "la",
        "work_type": "commentary",
    }


def _edition_record(
    head: ET.Element | None, *, work_id: str, edition_id: str, book_id: str
) -> dict[str, Any]:
    language = dc_text(head, "DC.Language") or "en"
    if language.lower() in {"eng", "en"}:
        language = "en"
    rights = dc_text(head, "DC.Rights") or "Public Domain"
    publisher = dc_text(head, "DC.Publisher")
    publication_year = _year_from_date(dc_text(head, "DC.Date", sub="Created"))
    file_title = dc_text(head, "DC.Title", sub="Main") or dc_text(head, "DC.Title") or book_id
    return {
        "edition_id": edition_id,
        "work_id": work_id,
        "edition_label": file_title,
        "publication_year": publication_year,
        "publisher": publisher,
        "language": language,
        "license": rights,
        "rights_status": "public-domain",
        "rights_note": (
            "CCEL ThML DC.Rights states Public Domain. The CCEL electronic "
            "edition applies markup and light editorial modernization."
        ),
        "source_url": f"https://www.ccel.org/ccel/calvin/{book_id}.xml",
        "corpus": "ccel",
        "external_id": f"ccel/calvin/{book_id}",
    }


def _year_from_date(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value[:4] if ch.isdigit())
    return int(digits) if len(digits) == 4 else None


def _attr_or_none(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "unknown"


__all__ = [
    "AUTHOR_CONTRIBUTOR_ID",
    "IMPORT_MODE_CALVIN_COMMENTARY_THML",
    "IMPORTER_NAME",
    "IMPORTER_VERSION",
    "CalvinCommentaryImportError",
    "CalvinCommentaryParseReport",
    "build_calvin_commentary_document",
    "import_calvin_commentary_sqlite",
    "import_calvin_corpus_from_manifest",
    "merge_calvin_commentary_documents",
    "parse_calvin_commentary_thml",
]
