"""Matthew Henry Commentary ThML/XML parser and importer.

Builds normalized Commentary documents (see
``textus_kb.importers.commentary_sqlite``) from the real CCEL Matthew
Henry "Commentary on the Whole Bible" — 6 separate volume files, each
covering several consecutive Bible books (unlike JFB's single file and
unlike Calvin's one-file-per-book).

Confirmed real-file structure (CCEL ``ccel/henry/mhc1.xml``..``mhc6.xml``,
verified by direct inspection across all 6 volumes — zero structural
anomalies found in any of them):

- Each volume file's ``ThML.body`` has one ``div1`` per canonical Bible
  book (title text matches the English book name exactly), plus
  front/back matter div1s ("Title Page", a "Preface: ..." div1, an
  "Indexes" div1) that are never traversed. A ``div1`` id is only
  unique *within* its own volume (e.g. "Ez" is Ezra in volume 2 but
  Ezekiel in volume 4) — always resolved together with the volume
  number, never alone.
- Within a book, ``div2`` children are chapters (title "Chapter N") or
  a bare "Introduction" (no ``<scripCom>`` at all, same as JFB).
- Within a chapter, content is a *flat* sequence of direct-sibling
  elements — confirmed with zero exceptions across all 6 volumes: a
  leading ``<scripCom osisRef="Book.N" />`` (chapter-only, no verse —
  the chapter's own opening marker, never wrapped in a div) followed by
  leading overview prose (an analytical summary of the whole chapter,
  itself containing only inline ``<scripRef>`` cross-references, never
  section-defining), then zero or more
  ``<scripCom osisRef="..."/><div class="Commentary" id="...">...</div>``
  *sibling pairs* — each pair is one commentary unit, and its own
  ``osisRef`` is very often a genuine multi-verse *range*
  (``Gen.1.1-Gen.1.2`` etc.) natively, not a single verse — Henry's
  commentary is written a "section" (several verses) at a time, and
  this is preserved as one section per range, never split per verse.
  Unlike JFB, the *next* section's marker is never nested inside the
  *previous* section's div — the two are always plain siblings, so a
  simple linear scan of direct children (no document-order recursive
  cutter) is sufficient and correct here.
- Each ``<div class="Commentary">`` opens with an ``<h4>`` heading
  (confirmed to repeat the same chapter-level label across every range
  in that chapter — not a distinct per-range title) and then a
  ``<p class="passage">`` paragraph quoting the full verse text being
  commented on (confirmed present on every single commentary div, zero
  exceptions) — that quoted-scripture paragraph is Henry's *lemma*, not
  his prose, and is excluded from chunk content exactly like Calvin's
  quoted-table text. The real commentary prose follows in further
  ``<p>`` elements, and may itself contain inline ``<scripRef>``
  cross-references (never section-defining, same policy as Calvin/JFB).
- Zero ``<note>`` elements exist anywhere in the commentary body of any
  of the 6 volumes (verified) — no footnote-catena leakage risk.

Real per-book authorship (see ``henry_commentary_source_manifest.json``
for the sourced detail): Matthew Henry personally wrote Genesis through
Acts (44 books). He died in 1714; Romans through Revelation (22 books)
was completed posthumously by named continuing ministers — the volume's
own preface ("Preface: Acts to Revelation") and its own table of
contributors name a specific author per book (e.g. "Mr. John Evans" for
Romans), never Matthew Henry. This importer trusts only that per-book
name (cross-checked against the manifest, exactly like JFB), and never
defaults every section to Henry's own authorship.

Fail-loudly policy: a scripCom that classifies to more than one
passage, a commentary div missing its expected ``<p class="passage">``
quoted-text paragraph, or a chapter with no content at all, raises
``HenryCommentaryImportError`` — never guessed or dropped silently.

No network. No schema change. No Henry-specific field in the shared
Commentary schema — everything Henry-specific lives in this module.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.importers.ccel_thml_core import (
    CcelThmlCoreError,
    ScriptureRefStats,
    dc_text,
    element_plain_text,
    find_child,
    local_tag,
    parse_thml_file,
    scripture_candidates,
)
from textus_kb.importers.henry_source_fetch import HenryBookEntry, HenryVolumeFile

IMPORT_MODE_HENRY_COMMENTARY_THML = "henry_commentary_thml"
IMPORTER_NAME = "textus_kb.importers.henry_commentary_thml"
IMPORTER_VERSION = "0.1.0"

# Matthew Henry's own well-documented dates. Continuators named in the
# Volume VI preface table have no birth/death year recorded here — never
# guessed (mirrors Calvin's own precedent for translators of unknown dates).
_HENRY_BIRTH_YEAR = 1662
_HENRY_DEATH_YEAR = 1714


class HenryCommentaryImportError(CcelThmlCoreError):
    """Raised when a Matthew Henry commentary ThML file cannot be parsed/imported."""


@dataclass
class HenryBookParseReport:
    div1_id: str
    volume: int
    work_id: str
    edition_id: str
    chapter_section_count: int = 0
    range_section_count: int = 0
    passage_link_count: int = 0
    chunk_count: int = 0
    known_empty_divs: list[dict[str, str]] = field(default_factory=list)
    scripture: ScriptureRefStats = field(default_factory=ScriptureRefStats)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scripture"] = self.scripture.to_dict()
        return payload


def parse_henry_commentary_thml(
    xml_path: str | Path,
    book_entries: list[HenryBookEntry],
) -> list[tuple[dict[str, Any], HenryBookParseReport]]:
    """Parse one Henry volume file once and return one normalized
    Commentary document + report per requested book entry (all entries
    must belong to the same volume as ``xml_path``)."""
    root = parse_thml_file(xml_path)
    if local_tag(root.tag) != "ThML":
        raise HenryCommentaryImportError(f"Expected ThML root, got {local_tag(root.tag)!r}.")
    head = find_child(root, "ThML.head")
    body = find_child(root, "ThML.body")
    if body is None:
        raise HenryCommentaryImportError("ThML.body is missing.")

    results: list[tuple[dict[str, Any], HenryBookParseReport]] = []
    for entry in book_entries:
        div1 = _find_child_by_id(body, "div1", entry.div1_id)
        if div1 is None:
            raise HenryCommentaryImportError(
                f"div1 id={entry.div1_id!r} not found in volume {entry.volume}."
            )
        document, report = _build_book_document(div1, entry, head=head)
        results.append((document, report))
    return results


def attach_henry_provenance(
    parsed: list[tuple[dict[str, Any], HenryBookParseReport]],
    book_entries: list[HenryBookEntry],
    *,
    volume: HenryVolumeFile,
    imported_at: str | None = None,
) -> tuple[list[dict[str, Any]], list[HenryBookParseReport]]:
    """Attach one ``source_files``/``import_batches`` row per book to each
    already-parsed document (every book in one volume file shares that
    file's ``file_name``/``raw_sha256``, distinct book-scoped ids)."""
    path = Path(volume.local_path)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise HenryCommentaryImportError(f"Cannot read Henry volume file: {path}") from exc
    raw_sha256 = _sha256_bytes(raw_bytes)
    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    documents: list[dict[str, Any]] = []
    reports: list[HenryBookParseReport] = []
    for (document, report), entry in zip(parsed, book_entries, strict=True):
        slug = _slug(entry.title)
        source_file_id = f"ccel.henry.{slug}.source"
        batch_id = f"ccel.henry.{slug}.batch.1"
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
                    "div1_id": report.div1_id,
                    "volume": report.volume,
                    "chapter_section_count": report.chapter_section_count,
                    "range_section_count": report.range_section_count,
                    "passage_link_count": report.passage_link_count,
                    "chunk_count": report.chunk_count,
                    "known_unmapped_sections": [
                        {
                            "div2_id": item["div2_id"],
                            "section_id": item["commentary_div_id"],
                            "reason": item["reason"],
                            "classification": item["classification"],
                        }
                        for item in report.known_empty_divs
                    ],
                },
            }
        ]
        documents.append(document)
        reports.append(report)
    return documents, reports


def _build_book_document(
    div1: ET.Element,
    entry: HenryBookEntry,
    *,
    head: ET.Element | None,
) -> tuple[dict[str, Any], HenryBookParseReport]:
    slug = _slug(entry.title)
    work_id = f"ccel.henry.work.{slug}"
    edition_id = f"ccel.henry.{slug}.edition"
    section_prefix = f"ccel.henry.{slug}"

    canonical_name = entry.contributor_raw_name
    is_henry = canonical_name == "Matthew Henry"
    contributor_id = f"ccel.henry.{_slug(canonical_name)}"
    contributors = [
        {
            "contributor_id": contributor_id,
            "canonical_name": canonical_name,
            "birth_year": _HENRY_BIRTH_YEAR if is_henry else None,
            "death_year": _HENRY_DEATH_YEAR if is_henry else None,
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
        "title": f"Matthew Henry's Commentary on the Whole Bible: {entry.title}",
        "original_title": None,
        "original_language": "en",
        "work_type": "commentary",
    }
    edition = _edition_record(head, work_id=work_id, edition_id=edition_id, entry=entry)

    stats = ScriptureRefStats()
    report = HenryBookParseReport(
        div1_id=entry.div1_id, volume=entry.volume, work_id=work_id, edition_id=edition_id, scripture=stats
    )
    sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []

    book_section_id = f"{section_prefix}.book"
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

    div2_children = [c for c in list(div1) if local_tag(c.tag) == "div2"]
    if not div2_children:
        raise HenryCommentaryImportError(
            f"{entry.div1_id!r} (volume {entry.volume}, {entry.title}): no div2 chapters found."
        )

    known_empty = {
        (item.div2_id, item.commentary_div_id): item
        for item in entry.known_empty_commentary_divs
    }
    for chapter_seq, div2 in enumerate(div2_children, start=1):
        _process_div2(
            div2,
            book_section_id=book_section_id,
            edition_id=edition_id,
            section_prefix=section_prefix,
            chapter_seq=chapter_seq,
            sections=sections,
            chunks=chunks,
            stats=stats,
            report=report,
            known_empty=known_empty,
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


def _process_div2(
    div2: ET.Element,
    *,
    book_section_id: str,
    edition_id: str,
    section_prefix: str,
    chapter_seq: int,
    sections: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    stats: ScriptureRefStats,
    report: HenryBookParseReport,
    known_empty: dict[tuple[str, str], Any],
) -> None:
    div2_id = div2.get("id") or f"ch{chapter_seq}"
    chapter_section_id = f"{section_prefix}.{_id_suffix(div2_id)}"
    title = (div2.get("title") or "").strip() or f"Chapter {chapter_seq}"

    children = list(div2)
    leading: list[ET.Element] = []
    range_pairs: list[tuple[ET.Element, ET.Element]] = []
    i = 0
    n = len(children)
    while i < n:
        child = children[i]
        tag = local_tag(child.tag)
        if tag == "scripCom":
            if i + 1 < n and local_tag(children[i + 1].tag) == "div" and (
                children[i + 1].get("class") or ""
            ) == "Commentary":
                commentary_div = children[i + 1]
                if len(list(commentary_div)) == 0:
                    exception = known_empty.get((div2_id, commentary_div.get("id") or ""))
                    if exception is None:
                        raise HenryCommentaryImportError(
                            f"{div2_id!r}: Commentary div {commentary_div.get('id')!r} is "
                            "completely empty and not a documented known exception; "
                            "structurally uncertain."
                        )
                    report.known_empty_divs.append(
                        {
                            "div2_id": div2_id,
                            "commentary_div_id": commentary_div.get("id") or "",
                            "reason": exception.reason,
                            "classification": exception.classification,
                        }
                    )
                    i += 2
                    continue
                range_pairs.append((child, commentary_div))
                i += 2
                continue
            # Chapter-only / standalone marker (not paired with a div):
            # never wrapped in content of its own — matches Calvin/JFB's
            # "chapter-only, passage-less" precedent. Not appended to
            # leading (it carries no visible text), just skipped.
            i += 1
            continue
        if tag == "div" and (child.get("class") or "") == "Commentary":
            raise HenryCommentaryImportError(
                f"{div2_id!r}: Commentary div {child.get('id')!r} with no preceding scripCom "
                "marker; structurally uncertain."
            )
        leading.append(child)
        i += 1

    chapter_text = "\n\n".join(
        text for el in leading if (text := element_plain_text(el, skip_notes=True))
    ).strip()
    sections.append(
        _section_row(
            section_id=chapter_section_id,
            edition_id=edition_id,
            parent_section_id=book_section_id,
            section_type="chapter",
            heading=title,
            sequence=chapter_seq,
            passage_links=[],
        )
    )
    report.chapter_section_count += 1
    if chapter_text:
        chunks.append(
            _chunk_row(
                chunk_id=f"{chapter_section_id}.chunk",
                section_id=chapter_section_id,
                sequence=1,
                text=chapter_text,
                locator=f"ccel:henry/{div2_id}",
            )
        )
        report.chunk_count += 1

    if not range_pairs and not chapter_text:
        raise HenryCommentaryImportError(f"{div2_id!r}: empty chapter (no content at all).")

    for range_seq, (marker, commentary_div) in enumerate(range_pairs, start=1):
        candidates = scripture_candidates(marker, stats)
        if len(candidates) > 1:
            raise HenryCommentaryImportError(
                f"{div2_id!r} range #{range_seq}: scripCom classified to more than one "
                "passage; structurally uncertain."
            )
        range_section_id = f"{chapter_section_id}.r{range_seq}"
        if candidates:
            links = [{**candidates[0], "relation_type": "primary"}]
            heading = candidates[0]["canonical_passage"]
        else:
            links = []
            heading = None

        quoted_paragraphs = [
            c
            for c in list(commentary_div)
            if local_tag(c.tag) == "p" and (c.get("class") or "") == "passage"
        ]
        if not quoted_paragraphs:
            raise HenryCommentaryImportError(
                f"{div2_id!r} range #{range_seq} ({commentary_div.get('id')!r}): missing the "
                "expected quoted-scripture <p class=\"passage\"> paragraph."
            )
        prose_elements = [
            c
            for c in list(commentary_div)
            if not (local_tag(c.tag) == "p" and (c.get("class") or "") == "passage")
        ]
        range_text = "\n\n".join(
            text for el in prose_elements if (text := element_plain_text(el, skip_notes=True))
        ).strip()

        sections.append(
            _section_row(
                section_id=range_section_id,
                edition_id=edition_id,
                parent_section_id=chapter_section_id,
                section_type="range_commentary",
                heading=heading,
                sequence=range_seq,
                passage_links=links,
            )
        )
        report.range_section_count += 1
        report.passage_link_count += len(links)
        if range_text:
            chunks.append(
                _chunk_row(
                    chunk_id=f"{range_section_id}.chunk",
                    section_id=range_section_id,
                    sequence=1,
                    text=range_text,
                    locator=f"ccel:henry/{marker.get('id') or range_section_id}",
                )
            )
            report.chunk_count += 1


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
    head: ET.Element | None, *, work_id: str, edition_id: str, entry: HenryBookEntry
) -> dict[str, Any]:
    language = dc_text(head, "DC.Language") or "en"
    if language.lower() in {"eng", "en"}:
        language = "en"
    rights = dc_text(head, "DC.Rights") or "Public Domain"
    rights_note = (
        "CCEL ThML DC.Rights states Public Domain. The CCEL electronic "
        "edition applies markup and light editorial modernization."
    )
    if entry.authorship_note:
        rights_note = f"{rights_note} {entry.authorship_note}"
    return {
        "edition_id": edition_id,
        "work_id": work_id,
        "edition_label": f"Matthew Henry's Commentary on the Whole Bible: {entry.title}",
        "publication_year": 1710,
        "publisher": "Grand Rapids, MI: Christian Classics Ethereal Library",
        "language": language,
        "license": rights,
        "rights_status": "public-domain",
        "rights_note": rights_note,
        "source_url": f"https://www.ccel.org/ccel/henry/mhc{entry.volume}.xml",
        "corpus": "ccel",
        "external_id": f"ccel/henry/mhc{entry.volume}#{entry.div1_id}",
    }


def build_henry_corpus_from_manifest(
    manifest: Any,
    *,
    database_path: str | Path | None = None,
    atomic: bool = True,
    imported_at: str | None = None,
) -> tuple[Any, list[HenryBookParseReport]]:
    """Parse every volume file once (one parse per volume, however many
    books it contains), attach provenance, merge, and write one
    commentary.sqlite3. ``manifest`` is a ``HenrySourceManifest``."""
    from textus_kb.importers.commentary_sqlite import (
        import_commentary_sqlite,
        merge_commentary_documents,
    )

    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_documents: list[dict[str, Any]] = []
    all_reports: list[HenryBookParseReport] = []
    for volume in manifest.volumes:
        volume_books = [b for b in manifest.books if b.volume == volume.volume]
        if not volume_books:
            continue
        parsed = parse_henry_commentary_thml(volume.local_path, volume_books)
        documents, reports = attach_henry_provenance(
            parsed, volume_books, volume=volume, imported_at=when
        )
        all_documents.extend(documents)
        all_reports.extend(reports)

    merged = merge_commentary_documents(all_documents, error_cls=HenryCommentaryImportError)
    result = import_commentary_sqlite(
        document=merged,
        database_path=database_path,
        import_mode=IMPORT_MODE_HENRY_COMMENTARY_THML,
        atomic=atomic,
    )
    return result, all_reports


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
    "IMPORT_MODE_HENRY_COMMENTARY_THML",
    "HenryBookParseReport",
    "HenryCommentaryImportError",
    "attach_henry_provenance",
    "build_henry_corpus_from_manifest",
    "parse_henry_commentary_thml",
]
