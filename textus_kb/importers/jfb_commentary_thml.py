"""JFB (Jamieson, Fausset & Brown) Commentary ThML/XML parser and importer.

Builds normalized Commentary documents (see
``textus_kb.importers.commentary_sqlite``) from the real CCEL JFB
commentary ThML/XML file — a single 35MB file covering the whole Bible
(unlike Calvin's 45 separate per-volume files).

Confirmed real-file structure (CCEL ``ccel/jamieson/jfb.xml``, verified
by direct inspection, not assumed from Calvin's structure):

- ``ThML.body`` has exactly two book-container ``div1``s of interest:
  id ``"x"`` ("The Old Testament") and id ``"xi"`` ("The New Testament");
  their ``div2`` children are the 66 canonical Bible books (title text
  matches the English book name exactly, e.g. "Genesis", "First
  Corinthians"). Other top-level ``div1``s (title page, cross-book
  introductions, chronological tables, acknowledgements, indexes) are
  never traversed — they are not passage-linked, per-book commentary.
- Every one of the 66 book ``div2``s opens with a short, uniform intro
  paragraph naming its own author: ``<i>Commentary by</i>
  <span class="sc">NAME</span>``. This is real per-book attribution
  authored by CCEL/the source itself (JFB divided the whole Bible by
  book among its three authors), not inferred — see
  ``_RAW_NAME_ALIASES`` for the one confirmed raw-text-vs-DC.Creator
  spelling mismatch ("A. R. Faussett" in-book vs "A. R. Fausset" in
  ``DC.Creator``).
- Within a book, ``div3`` children are chapters (title "Chapter N"),
  chapter-range overview units (title "Chapter 5-8", confirmed exactly
  once in the whole file: Matthew's Sermon-on-the-Mount overview), or
  bare "Introduction" units (confirmed on 49 of the 66 books) with no
  ``<scripCom>`` at all.
- Passage markers are ``<scripCom type="Commentary" osisRef="..." />``
  self-closing elements — never a scripture-quotation ``<table>`` the
  way Calvin's caption-scripRef mechanism works. Each verse's own
  content is a sibling ``<div class="Commentary">``. Confirmed real
  layout quirk: the marker for the *next* verse is usually nested as
  the div's own trailing content (almost always its direct last child;
  occasionally one level deeper, as the last child of a trailing
  ``<p>``) — but is also confirmed to sometimes open *inside* the
  verse's own first paragraph instead (e.g. Matthew 9:32's marker sits
  inside its own caption paragraph, not trailing 9:31's div). See
  ``_cut_into_segments``, which cuts a document-order text stream at
  every ``<scripCom>`` regardless of nesting depth or which of these
  shapes applies, rather than assuming one fixed structural position.
- Inline ``<scripRef>`` elements inside running prose (cross-references
  JFB mentions in passing) are cross-references, never passage-defining
  — only ``<scripCom>`` markers are section-defining, mirroring the same
  policy already established for Calvin's inline ``<scripRef>``. There
  are zero ``<note>`` elements anywhere in this source (verified) — no
  footnote-catena leakage risk exists here at all.
- A chapter/intro/range unit whose own leading ``<scripCom>`` classifies
  as chapter-only (no verse — true for every normal "Chapter N" opener,
  and for the one "Chapter 5-8" range case) never gets its own
  passage_link; its real prose (if any — the Sermon-on-the-Mount
  overview has substantial prose; a bare "CHAPTER 1" heading does not)
  is still kept as that section's own chunk, exactly like Calvin's
  passage-less structural containers.

Fail-loudly policy: a scripCom that classifies to more than one passage,
a book whose in-text "Commentary by ..." attribution does not match the
manifest's own ``contributor_raw_name`` (or matches nothing in the file's
own ``DC.Creator`` list), or a div3 with no content at all, raises
``JfbCommentaryImportError`` — never guessed or dropped silently.

No network. No schema change. No JFB-specific field in the shared
Commentary schema — everything JFB-specific lives in this module.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.importers.ccel_thml_core import (
    CcelThmlCoreError,
    ScriptureRefStats,
    dc_text,
    dc_text_all,
    element_plain_text,
    find_child,
    local_tag,
    parse_thml_file,
    scripture_candidates,
)
from textus_kb.importers.jfb_source_fetch import JfbBookEntry

IMPORT_MODE_JFB_COMMENTARY_THML = "jfb_commentary_thml"
IMPORTER_NAME = "textus_kb.importers.jfb_commentary_thml"
IMPORTER_VERSION = "0.1.0"

# Real, documented historical figures — used identically across all 66
# per-book documents so the generic cross-document merge's
# byte-identical-contributor rule accepts the repeated declaration.
_AUTHOR_BIO = {
    "Robert Jamieson": (1802, 1880),
    "A. R. Fausset": (1821, 1910),
    "David Brown": (1803, 1897),
}

# The one confirmed raw-text-vs-DC.Creator spelling mismatch (in-book
# "Commentary by A. R. Faussett" vs DC.Creator's "A. R. Fausset") — not a
# guess, both spellings are literal text found in the real source.
_RAW_NAME_ALIASES = {"A. R. Faussett": "A. R. Fausset"}

_BOOK_DIV1_IDS = {"OT": "x", "NT": "xi"}


class JfbCommentaryImportError(CcelThmlCoreError):
    """Raised when the JFB commentary ThML file cannot be parsed/imported."""


@dataclass
class JfbBookParseReport:
    div2_id: str
    work_id: str
    edition_id: str
    chapter_section_count: int = 0
    verse_section_count: int = 0
    passage_link_count: int = 0
    chunk_count: int = 0
    scripture: ScriptureRefStats = field(default_factory=ScriptureRefStats)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scripture"] = self.scripture.to_dict()
        return payload


def parse_jfb_commentary_thml(
    xml_path: str | Path,
    book_entries: list[JfbBookEntry],
) -> list[tuple[dict[str, Any], JfbBookParseReport]]:
    """Parse the single JFB source file once and return one normalized
    Commentary document + report per requested book entry."""
    root = parse_thml_file(xml_path)
    if local_tag(root.tag) != "ThML":
        raise JfbCommentaryImportError(f"Expected ThML root, got {local_tag(root.tag)!r}.")
    head = find_child(root, "ThML.head")
    body = find_child(root, "ThML.body")
    if body is None:
        raise JfbCommentaryImportError("ThML.body is missing.")

    author_names = dc_text_all(head, "DC.Creator", sub="Author", scheme="short-form")
    if not author_names:
        raise JfbCommentaryImportError("No DC.Creator[Author] entries found.")

    needed_testaments = {entry.testament for entry in book_entries}
    testament_divs: dict[str, ET.Element] = {}
    for testament in needed_testaments:
        div1_id = _BOOK_DIV1_IDS.get(testament)
        if div1_id is None:
            raise JfbCommentaryImportError(f"Unknown testament {testament!r}.")
        div1 = _find_child_by_id(body, "div1", div1_id)
        if div1 is None:
            raise JfbCommentaryImportError(f"Missing expected div1 id={div1_id!r} ({testament}).")
        testament_divs[testament] = div1

    results: list[tuple[dict[str, Any], JfbBookParseReport]] = []
    for entry in book_entries:
        container = testament_divs.get(entry.testament)
        if container is None:
            raise JfbCommentaryImportError(f"Unknown testament {entry.testament!r} for {entry.div2_id!r}.")
        div2 = _find_child_by_id(container, "div2", entry.div2_id)
        if div2 is None:
            raise JfbCommentaryImportError(f"div2 id={entry.div2_id!r} not found under {entry.testament}.")
        document, report = _build_book_document(div2, entry, head=head, author_names=author_names)
        results.append((document, report))
    return results


def attach_jfb_provenance(
    parsed: list[tuple[dict[str, Any], JfbBookParseReport]],
    book_entries: list[JfbBookEntry],
    *,
    xml_path: str | Path,
    imported_at: str | None = None,
) -> tuple[list[dict[str, Any]], list[JfbBookParseReport]]:
    """Attach one ``source_files``/``import_batches`` row per book to each
    already-parsed document (all 66 books physically share one file, so
    every row shares the same ``file_name``/``raw_sha256`` and gets a
    distinct, book-scoped id — see the module docstring). Shared by both
    the JFB-only corpus build and the combined Calvin+JFB build so this
    provenance logic exists in exactly one place."""
    path = Path(xml_path)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise JfbCommentaryImportError(f"Cannot read JFB source file: {path}") from exc
    raw_sha256 = _sha256_bytes(raw_bytes)
    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    documents: list[dict[str, Any]] = []
    reports: list[JfbBookParseReport] = []
    for (document, report), entry in zip(parsed, book_entries, strict=True):
        slug = _slug(entry.title)
        source_file_id = f"ccel.jfb.{slug}.source"
        batch_id = f"ccel.jfb.{slug}.batch.1"
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
                    "div2_id": report.div2_id,
                    "chapter_section_count": report.chapter_section_count,
                    "verse_section_count": report.verse_section_count,
                    "passage_link_count": report.passage_link_count,
                    "chunk_count": report.chunk_count,
                },
            }
        ]
        documents.append(document)
        reports.append(report)
    return documents, reports


def _extract_in_book_attribution(lead_elements: list[ET.Element]) -> str | None:
    """Find the real, literal ``<i>Commentary by</i> <span class="sc">NAME</span>``
    text CCEL prints at the start of every one of the 66 books' own
    commentary (confirmed present on all 66 by direct inspection) —
    never trusts the manifest's own copy of this text without checking
    it against the actual source bytes being parsed right now."""
    for element in lead_elements:
        for p in element.iter():
            if local_tag(p.tag) != "p":
                continue
            children = list(p)
            for i, child in enumerate(children):
                if local_tag(child.tag) != "i":
                    continue
                if (child.text or "").strip() != "Commentary by":
                    continue
                if i + 1 < len(children) and local_tag(children[i + 1].tag) == "span":
                    return "".join(children[i + 1].itertext()).strip()
    return None


def _build_book_document(
    div2: ET.Element,
    entry: JfbBookEntry,
    *,
    head: ET.Element | None,
    author_names: list[str],
) -> tuple[dict[str, Any], JfbBookParseReport]:
    slug = _slug(entry.title)
    work_id = f"ccel.jfb.work.{slug}"
    edition_id = f"ccel.jfb.{slug}.edition"
    section_prefix = f"ccel.jfb.{slug}"

    div3_children = [c for c in list(div2) if local_tag(c.tag) == "div3"]
    lead_elements: list[ET.Element] = []
    for child in list(div2):
        if local_tag(child.tag) == "div3":
            break
        lead_elements.append(child)

    in_book_attribution = _extract_in_book_attribution(lead_elements)
    if in_book_attribution is None:
        raise JfbCommentaryImportError(
            f"{entry.div2_id!r}: no 'Commentary by ...' attribution found in the book's "
            "own leading content; cannot verify author against the manifest without guessing."
        )
    if in_book_attribution != entry.contributor_raw_name:
        raise JfbCommentaryImportError(
            f"{entry.div2_id!r}: manifest contributor_raw_name {entry.contributor_raw_name!r} "
            f"does not match the book's own in-text attribution {in_book_attribution!r}; "
            "refusing to guess which is correct."
        )
    canonical_name = _RAW_NAME_ALIASES.get(entry.contributor_raw_name, entry.contributor_raw_name)
    if canonical_name not in author_names:
        raise JfbCommentaryImportError(
            f"{entry.div2_id!r}: in-book attribution {entry.contributor_raw_name!r} "
            f"(normalized {canonical_name!r}) does not match any DC.Creator[Author]: {author_names!r}."
        )
    contributor_id = f"ccel.jfb.{_slug(canonical_name)}"
    birth_year, death_year = _AUTHOR_BIO[canonical_name]
    contributors = [
        {
            "contributor_id": contributor_id,
            "canonical_name": canonical_name,
            "birth_year": birth_year,
            "death_year": death_year,
        }
    ]
    work_contributors = [{"work_id": work_id, "contributor_id": contributor_id, "role": "author"}]
    contributor_source_names = [
        {
            "contributor_id": contributor_id,
            "edition_id": edition_id,
            "raw_name": entry.contributor_raw_name,
        }
    ]

    work = {
        "work_id": work_id,
        "title": f"Commentary Critical and Explanatory: {entry.title}",
        "original_title": None,
        "original_language": "en",
        "work_type": "commentary",
    }
    edition = _edition_record(head, work_id=work_id, edition_id=edition_id, entry=entry)

    stats = ScriptureRefStats()
    report = JfbBookParseReport(div2_id=entry.div2_id, work_id=work_id, edition_id=edition_id, scripture=stats)
    sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []

    book_section_id = f"{section_prefix}.book"
    book_text = "\n\n".join(
        text for el in lead_elements if (text := element_plain_text(el, skip_notes=True))
    ).strip()
    sections.append(
        _section_row(
            section_id=book_section_id,
            edition_id=edition_id,
            parent_section_id=None,
            section_type="book",
            heading=entry.title,
            sequence=1,
            passage_links=[],
        )
    )
    if book_text:
        chunks.append(
            _chunk_row(
                chunk_id=f"{book_section_id}.chunk",
                section_id=book_section_id,
                sequence=1,
                text=book_text,
                locator=f"ccel:jamieson/jfb#{entry.div2_id}",
            )
        )
        report.chunk_count += 1

    if not div3_children:
        raise JfbCommentaryImportError(f"{entry.div2_id!r} ({entry.title}): no div3 chapters found.")

    for chapter_seq, div3 in enumerate(div3_children, start=1):
        _process_div3(
            div3,
            book_section_id=book_section_id,
            edition_id=edition_id,
            section_prefix=section_prefix,
            chapter_seq=chapter_seq,
            sections=sections,
            chunks=chunks,
            stats=stats,
            report=report,
            entry=entry,
        )

    document = {
        "contributors": contributors,
        "works": [work],
        "work_contributors": work_contributors,
        "editions": [edition],
        "contributor_source_names": contributor_source_names,
        "sections": sections,
        "chunks": chunks,
    }
    return document, report


def _process_div3(
    div3: ET.Element,
    *,
    book_section_id: str,
    edition_id: str,
    section_prefix: str,
    chapter_seq: int,
    sections: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    stats: ScriptureRefStats,
    report: JfbBookParseReport,
    entry: JfbBookEntry,
) -> None:
    div3_id = div3.get("id") or f"ch{chapter_seq}"
    chapter_section_id = f"{section_prefix}.{_id_suffix(div3_id)}"
    title = (div3.get("title") or "").strip() or f"Chapter {chapter_seq}"

    segments = _cut_into_segments(div3)
    if not segments:
        raise JfbCommentaryImportError(f"{div3_id!r}: empty div3 (no content at all).")

    chapter_marker, chapter_text = segments[0]
    chapter_heading = title
    chapter_links: list[dict[str, str]] = []
    if chapter_marker is not None:
        candidates = scripture_candidates(chapter_marker, stats)
        if len(candidates) > 1:
            raise JfbCommentaryImportError(
                f"{div3_id!r}: chapter-level scripCom classified to more than one passage; "
                "structurally uncertain."
            )
        if candidates:
            chapter_links = [{**candidates[0], "relation_type": "primary"}]

    sections.append(
        _section_row(
            section_id=chapter_section_id,
            edition_id=edition_id,
            parent_section_id=book_section_id,
            section_type="chapter",
            heading=chapter_heading,
            sequence=chapter_seq,
            passage_links=chapter_links,
        )
    )
    report.chapter_section_count += 1
    report.passage_link_count += len(chapter_links)
    if chapter_text:
        chunks.append(
            _chunk_row(
                chunk_id=f"{chapter_section_id}.chunk",
                section_id=chapter_section_id,
                sequence=1,
                text=chapter_text,
                locator=f"ccel:jamieson/jfb#{div3_id}",
            )
        )
        report.chunk_count += 1

    for verse_seq, (marker, verse_text) in enumerate(segments[1:], start=1):
        if marker is None:
            raise JfbCommentaryImportError(
                f"{div3_id!r}: verse segment #{verse_seq} has no scripCom marker; "
                "structurally uncertain."
            )
        candidates = scripture_candidates(marker, stats)
        if len(candidates) > 1:
            raise JfbCommentaryImportError(
                f"{div3_id!r} verse #{verse_seq}: scripCom classified to more than one "
                "passage; structurally uncertain."
            )
        verse_section_id = f"{chapter_section_id}.v{verse_seq}"
        if candidates:
            links = [{**candidates[0], "relation_type": "primary"}]
            heading = candidates[0]["canonical_passage"]
        else:
            links = []
            heading = None
        sections.append(
            _section_row(
                section_id=verse_section_id,
                edition_id=edition_id,
                parent_section_id=chapter_section_id,
                section_type="verse_commentary",
                heading=heading,
                sequence=verse_seq,
                passage_links=links,
            )
        )
        report.verse_section_count += 1
        report.passage_link_count += len(links)
        if verse_text:
            chunks.append(
                _chunk_row(
                    chunk_id=f"{verse_section_id}.chunk",
                    section_id=verse_section_id,
                    sequence=1,
                    text=verse_text,
                    locator=f"ccel:jamieson/jfb#{marker.get('id') or verse_section_id}",
                )
            )
            report.chunk_count += 1


_JFB_BLOCK_TAGS = frozenset({"p", "div"})


def _cut_into_segments(div3: ET.Element) -> list[tuple[ET.Element | None, str]]:
    """Walk div3's subtree in document order, cutting a new segment at
    every ``<scripCom>`` encountered — regardless of nesting depth.

    Confirmed real layout is NOT uniform enough to assume a scripCom
    marker always trails the *previous* verse's div (as Calvin's markers
    do): it usually does, but it is also confirmed to sometimes open
    *inside* the very first paragraph of the verse div it belongs to
    (e.g. Matthew 9:32's own marker sits inside its own caption
    paragraph, not at the end of 9:31's div). A pure document-order cut,
    independent of which element happens to structurally contain the
    marker, is the only approach that is correct for both confirmed
    shapes without guessing which one applies where.

    Returns (marker, text) pairs; the first pair's marker is the div3's
    own opening scripCom (or None for a div3 with no scripCom at all,
    e.g. a bare "Introduction"). Every later pair is one verse.
    """
    segments: list[tuple[ET.Element | None, str]] = []
    current_marker: ET.Element | None = None
    current_parts: list[str] = []

    def flush() -> None:
        if current_marker is None and not current_parts:
            return
        text = re.sub(r"[ \t]+", " ", "".join(current_parts))
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        segments.append((current_marker, text))
        current_parts.clear()

    def walk(node: ET.Element, *, top_level: bool) -> None:
        nonlocal current_marker
        for child in list(node):
            tag = local_tag(child.tag)
            if tag == "scripCom":
                flush()
                current_marker = child
            elif tag == "note":
                pass
            else:
                if top_level and tag in _JFB_BLOCK_TAGS and current_parts:
                    current_parts.append("\n\n")
                if child.text:
                    current_parts.append(child.text)
                walk(child, top_level=top_level and tag != "p")
            if child.tail:
                current_parts.append(child.tail)

    walk(div3, top_level=True)
    flush()
    return segments


def _find_child_by_id(parent: ET.Element, tag: str, element_id: str) -> ET.Element | None:
    for child in list(parent):
        if local_tag(child.tag) == tag and child.get("id") == element_id:
            return child
    return None


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


def _chunk_row(*, chunk_id: str, section_id: str, sequence: int, text: str, locator: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "section_id": section_id,
        "sequence": sequence,
        "text": text,
        "plain_text": text,
        "source_locator": locator,
    }


def _edition_record(
    head: ET.Element | None, *, work_id: str, edition_id: str, entry: JfbBookEntry
) -> dict[str, Any]:
    language = dc_text(head, "DC.Language") or "en"
    if language.lower() in {"eng", "en"}:
        language = "en"
    rights = dc_text(head, "DC.Rights") or "Public Domain"
    file_title = dc_text(head, "DC.Title", sub="Main") or dc_text(head, "DC.Title") or "JFB Commentary"
    return {
        "edition_id": edition_id,
        "work_id": work_id,
        "edition_label": f"{file_title}: {entry.title}",
        "publication_year": 1871,
        "publisher": "Grand Rapids: Christian Classics Ethereal Library",
        "language": language,
        "license": rights,
        "rights_status": "public-domain",
        "rights_note": (
            "CCEL ThML DC.Rights states Public Domain. The CCEL electronic "
            "edition applies markup and light editorial modernization."
        ),
        "source_url": "https://www.ccel.org/ccel/jamieson/jfb.xml",
        "corpus": "ccel",
        "external_id": f"ccel/jamieson/jfb#{entry.div2_id}",
    }


def build_jfb_corpus_from_manifest(
    xml_path: str | Path,
    book_entries: list[JfbBookEntry],
    *,
    database_path: str | Path | None = None,
    atomic: bool = True,
    imported_at: str | None = None,
) -> tuple[Any, list[JfbBookParseReport]]:
    """Parse the single JFB source file once, attach provenance rows per
    book (one ``source_files``/``import_batches`` row per book — all
    sharing the same physical file/sha256, distinct ids — see module
    docstring), merge, and write one commentary.sqlite3."""
    from textus_kb.importers.commentary_sqlite import (
        import_commentary_sqlite,
        merge_commentary_documents,
    )

    path = Path(xml_path)
    parsed = parse_jfb_commentary_thml(path, book_entries)
    documents, reports = attach_jfb_provenance(parsed, book_entries, xml_path=path, imported_at=imported_at)

    merged = merge_commentary_documents(documents, error_cls=JfbCommentaryImportError)
    result = import_commentary_sqlite(
        document=merged,
        database_path=database_path,
        import_mode=IMPORT_MODE_JFB_COMMENTARY_THML,
        atomic=atomic,
    )
    return result, reports


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "unknown"


def _id_suffix(div_id: str) -> str:
    return div_id.replace(".", "_")


__all__ = [
    "IMPORTER_NAME",
    "IMPORTER_VERSION",
    "IMPORT_MODE_JFB_COMMENTARY_THML",
    "JfbBookParseReport",
    "JfbCommentaryImportError",
    "attach_jfb_provenance",
    "build_jfb_corpus_from_manifest",
    "parse_jfb_commentary_thml",
]
