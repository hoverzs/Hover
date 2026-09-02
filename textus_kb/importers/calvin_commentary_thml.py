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
      *inside its own ``<table>``* give the quoted passage(s) — this is
      the section-defining passage (a range, or several passages for a
      Harmony section). The quoted Bible text itself (inside the table)
      is never imported as chunk content — it is not Calvin's prose.
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
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    passage_links_for_elements,
    scripture_candidates,
)

IMPORT_MODE_CALVIN_COMMENTARY_THML = "calvin_commentary_thml"
IMPORTER_NAME = "textus_kb.importers.calvin_commentary_thml"
IMPORTER_VERSION = "0.1.0"

AUTHOR_CONTRIBUTOR_ID = "ccel.calvin"
AUTHOR_NAME_FALLBACK = "John Calvin"


class CalvinCommentaryImportError(CcelThmlCoreError):
    """Raised when a Calvin commentary ThML file cannot be parsed/imported."""


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
    scripture: ScriptureRefStats = field(default_factory=ScriptureRefStats)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scripture"] = self.scripture.to_dict()
        return payload


def parse_calvin_commentary_thml(
    xml_path: str | Path,
) -> tuple[dict[str, Any], CalvinCommentaryParseReport]:
    """Parse one real CCEL Calvin commentary ThML file into a normalized
    Commentary document (contributors/works/work_contributors/editions/
    sections/chunks — matching ``commentary_sqlite.normalize_commentary_document``
    input shape). ``source_files``/``import_batches`` are NOT included here;
    the caller attaches those from the raw file it actually read (this
    function only sees parsed XML, not the raw bytes/hash)."""
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

    work_id = f"ccel.calvin.{book_id}"
    edition_id = f"{work_id}.edition"
    section_prefix = f"ccel.calvin.{book_id}"

    contributors, work_contributors = _contributors(head, work_id=work_id)
    work = _work_record(head, work_id=work_id)
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

        if div1_type not in {"chapter", "section"}:
            # Auxiliary matter: preface/dedication/argument ("front"),
            # a continuous translation appendix ("back"), or an
            # auto-generated index (no type attribute at all). None of
            # these follow the verse-by-verse scripCom/table convention,
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

            if div2_type == "scripture":
                table = find_child(div2, "table")
                links = _table_passage_links(table, stats) if table is not None else []
                if not links:
                    raise CalvinCommentaryImportError(
                        f"Scripture section {div2_id!r} has no parseable passage "
                        "in its own quotation table."
                    )
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

            # Untyped sibling div2: continuation commentary anchored to the
            # most recently seen scripture-range section.
            if current_range_section_id is None:
                raise CalvinCommentaryImportError(
                    f"Commentary div2 {div2_id!r} has no preceding scripture "
                    "section to anchor its passage to."
                )
            verse_sections, verse_chunks, leading_text = _extract_verse_sections(
                container=div2,
                exclude=None,
                parent_section_id=current_range_section_id,
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
                    # Unmarked lead-in text inside a continuation div2 belongs
                    # to the range section it continues, not a new section.
                    chunks.append(
                        _chunk_row(
                            chunk_id=f"{div2_section_id}.lead.chunk",
                            section_id=current_range_section_id,
                            sequence=99,
                            text=leading_text,
                            locator=f"ccel:calvin/{book_id}#{div2_id}",
                        )
                    )
                    report.chunk_count += 1
            elif leading_text:
                # No scripCom at all in this div2: fold its whole text into
                # the range section it continues (benign layout variation,
                # not a structurally uncertain passage).
                chunks.append(
                    _chunk_row(
                        chunk_id=f"{div2_section_id}.chunk",
                        section_id=current_range_section_id,
                        sequence=99,
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
) -> tuple[dict[str, Any], CalvinCommentaryParseReport]:
    """Parse one Calvin commentary ThML file and attach its own
    source_files/import_batches provenance rows (raw SHA-256 computed from
    the actual bytes on disk, not invented)."""
    path = Path(xml_path)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise CalvinCommentaryImportError(f"Cannot read ThML file: {path}") from exc
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    document, report = parse_calvin_commentary_thml(path)
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
    index: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in _ID_FIELD_BY_KIND}
    seen_work_contributors: set[tuple[str, str, str]] = set()

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

    return merged


def import_calvin_commentary_sqlite(
    xml_paths: list[str | Path],
    *,
    database_path: str | Path | None = None,
    atomic: bool = True,
):
    """Parse one or more Calvin commentary ThML files, merge them, and write
    a commentary.sqlite3 store in one atomic build. Imported here (not at
    module level) to avoid a hard import-time dependency from the shared
    Commentary schema module onto this Calvin-specific parser."""
    from textus_kb.importers.commentary_sqlite import import_commentary_sqlite

    if not xml_paths:
        raise CalvinCommentaryImportError("Provide at least one Calvin ThML source path.")
    documents = []
    reports = []
    for xml_path in xml_paths:
        document, report = build_calvin_commentary_document(xml_path)
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


def _table_passage_links(
    table: ET.Element, stats: ScriptureRefStats
) -> list[dict[str, str]]:
    scrip_refs = [el for el in table.iter() if local_tag(el.tag) == "scripRef"]
    return passage_links_for_elements(scrip_refs, stats)


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

    Returns (sections, chunks, leading_text) where leading_text is any
    content before the first scripCom marker (belongs to the caller).
    """
    sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    leading_parts: list[str] = []
    pending: ET.Element | None = None
    verse_index = 0

    for child in list(container):
        if child is exclude:
            continue
        tag = local_tag(child.tag)
        marker = _as_scripcom_marker(child)
        if marker is not None:
            pending = marker
            continue
        if pending is not None and tag == "div" and (child.get("class") or "") == "Commentary":
            verse_index += 1
            _finalize_verse_section(
                marker=pending,
                content_element=child,
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
            pending = None
            continue
        if pending is not None:
            # A scripCom marker not immediately followed by its Commentary
            # div is a structural surprise; do not guess its content.
            raise CalvinCommentaryImportError(
                "scripCom marker not followed by a <div class=\"Commentary\"> "
                f"sibling in {section_prefix!r}."
            )
        text = paragraph_plain_text(child) if tag == "p" else ""
        if text:
            leading_parts.append(text)

    if pending is not None:
        raise CalvinCommentaryImportError(
            f"Dangling scripCom marker with no content in {section_prefix!r}."
        )

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
    content_element: ET.Element,
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
        links = [candidates[0]]
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

    text = element_plain_text(content_element, skip_notes=True)
    notes = _notes_text(content_element)
    parts = [part for part in (text, notes) if part]
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


def _notes_text(element: ET.Element) -> str:
    from textus_kb.importers.ccel_thml_core import collect_notes

    notes = collect_notes([element])
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
            {"raw_citation": link["raw_citation"], "canonical_passage": link["canonical_passage"]}
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
    head: ET.Element | None, *, work_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    author_name = (
        dc_text(head, "DC.Creator", sub="Author", scheme="short-form") or AUTHOR_NAME_FALLBACK
    )
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
    translator_name = dc_text(head, "DC.Creator", sub="Translator", scheme="short-form")
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
    return contributors, work_contributors


def _work_record(head: ET.Element | None, *, work_id: str) -> dict[str, Any]:
    title = dc_text(head, "DC.Title", sub="Main") or dc_text(head, "DC.Title") or "Calvin Commentary"
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
    return {
        "edition_id": edition_id,
        "work_id": work_id,
        "edition_label": "CCEL ThML edition",
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
    "merge_calvin_commentary_documents",
    "parse_calvin_commentary_thml",
]
