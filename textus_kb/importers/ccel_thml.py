"""Calvin Institutes CCEL/ThML pilot importer (Phase B2).

Pilot-only: John Calvin, Institutes of the Christian Religion.
No network, no DTD fetch, no schema change, no general CCEL framework.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

from textus_kb.books import ENGLISH_OSIS_ALIASES, OSIS_BY_ID
from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    TheologyImportError,
    TheologyImportReport,
    import_theology_sqlite,
)

IMPORT_MODE_CCEL_THML = "ccel_thml"

# Explicit Book I–IV allowlist from the CCEL Institutes ThML audit.
ALLOWED_BOOK_DIV1_IDS: tuple[str, ...] = ("iii", "iv", "v", "vi")

AUTHOR_ID = "ccel.calvin"
WORK_ID = "ccel.calvin.institutes"
EDITION_ID = "ccel.calvin.institutes.beveridge.1845"
SOURCE_URL = "https://www.ccel.org/ccel/calvin/institutes.xml"
EXTERNAL_ID = "ccel/calvin/institutes"
LOCATOR_PREFIX = "ccel:calvin/institutes"

RIGHTS_NOTE = (
    "CCEL ThML DC.Rights states Public Domain. "
    "The CCEL electronic edition applies markup and light editorial modernization. "
    "This pilot imports only Books I–IV and excludes prefatory, introductory, "
    "and CCEL-generated blocks whose rights status is not unambiguous."
)

_DOCTYPE_RE = re.compile(r"<!DOCTYPE\b", re.IGNORECASE)
_NUMBERED_SECTION_RE = re.compile(r"^(\d+)\.\s+\S")
_CHAPTER_ONLY_OSIS_RE = re.compile(r"^[A-Za-z0-9]+\.\d+$")
_EP_REF_RE = re.compile(r"^Ep\.?\s*\d+", re.IGNORECASE)
_NONCANONICAL_BOOKS = frozenset(
    {
        "1Macc",
        "2Macc",
        "3Macc",
        "4Macc",
        "Tob",
        "Jdt",
        "Wis",
        "Sir",
        "Bar",
        "PrAzar",
        "Sus",
        "Bel",
        "1Esd",
        "2Esd",
        "Man",
        "AddEsth",
        "EpJer",
        "1Maccabees",
        "2Maccabees",
        "Tobit",
        "Judith",
        "Wisdom",
        "Sirach",
        "Baruch",
        "Ecclus",
        "Wisd",
    }
)


class CcelThmlImportError(TheologyImportError):
    """Raised when the Calvin Institutes ThML cannot be imported."""


@dataclass
class ScriptureRefStats:
    seen: int = 0
    imported: int = 0
    skipped_chapter_only: int = 0
    skipped_noncanonical: int = 0
    skipped_nonbiblical: int = 0
    skipped_unparseable: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "scripture_refs_seen": self.seen,
            "scripture_refs_imported": self.imported,
            "scripture_refs_skipped_chapter_only": self.skipped_chapter_only,
            "scripture_refs_skipped_noncanonical": self.skipped_noncanonical,
            "scripture_refs_skipped_nonbiblical": self.skipped_nonbiblical,
            "scripture_refs_skipped_unparseable": self.skipped_unparseable,
        }


@dataclass
class CcelThmlImportReport:
    database_path: Path
    schema_version: str
    import_mode: str
    content_hash: str
    generated_at: str
    author_count: int
    work_count: int
    edition_count: int
    section_count: int
    chunk_count: int
    passage_link_count: int
    books_imported: int
    chapters_imported: int
    numbered_sections_imported: int
    skipped_top_level_ids: tuple[str, ...] = ()
    scripture_refs_seen: int = 0
    scripture_refs_imported: int = 0
    scripture_refs_skipped_chapter_only: int = 0
    scripture_refs_skipped_noncanonical: int = 0
    scripture_refs_skipped_nonbiblical: int = 0
    scripture_refs_skipped_unparseable: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        payload["skipped_top_level_ids"] = list(self.skipped_top_level_ids)
        payload["warnings"] = list(self.warnings)
        return payload


def import_ccel_institutes_thml(
    xml_path: str | Path,
    *,
    database_path: str | Path | None = None,
    atomic: bool = True,
) -> CcelThmlImportReport:
    document, extras = parse_ccel_institutes_thml(xml_path)
    theology = import_theology_sqlite(
        document=document,
        database_path=database_path if database_path is not None else DEFAULT_DATABASE_PATH,
        import_mode=IMPORT_MODE_CCEL_THML,
        atomic=atomic,
    )
    return _combine_report(theology, extras)


def parse_ccel_institutes_thml(
    xml_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(xml_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CcelThmlImportError(f"Cannot read ThML file: {path}") from exc
    root = _parse_thml_bytes(raw)
    if _local(root.tag) != "ThML":
        raise CcelThmlImportError(f"Expected ThML root, got {_local(root.tag)!r}.")

    head = _find_child(root, "ThML.head")
    body = _find_child(root, "ThML.body")
    if body is None:
        raise CcelThmlImportError("ThML.body is missing.")

    book_divs, skipped_ids = _select_allowed_books(body)
    stats = ScriptureRefStats()
    sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    chapters_imported = 0
    numbered_sections = 0

    for book_index, book_div in enumerate(book_divs, start=1):
        book_xml_id = book_div.get("id") or ""
        book_section_id = _stable_id(book_xml_id)
        sections.append(
            {
                "section_id": book_section_id,
                "edition_id": EDITION_ID,
                "parent_section_id": None,
                "section_type": "book",
                "heading": _attr_or_none(book_div.get("title")),
                "sequence": book_index,
            }
        )
        chapter_divs = [child for child in list(book_div) if _local(child.tag) == "div2"]
        for chapter_index, chapter_div in enumerate(chapter_divs, start=1):
            chapters_imported += 1
            chapter_xml_id = chapter_div.get("id") or ""
            chapter_section_id = _stable_id(chapter_xml_id)
            sections.append(
                {
                    "section_id": chapter_section_id,
                    "edition_id": EDITION_ID,
                    "parent_section_id": book_section_id,
                    "section_type": "chapter",
                    "heading": _attr_or_none(chapter_div.get("title")),
                    "sequence": chapter_index,
                }
            )
            for inst_section in _numbered_sections_from_chapter(chapter_div):
                numbered_sections += 1
                first_p_id = inst_section["first_p_id"]
                section_id = _stable_id(first_p_id)
                chunk_id = f"{section_id}.chunk"
                locator = f"{LOCATOR_PREFIX}#{first_p_id}"
                links = _passage_links_for_elements(
                    inst_section["elements"],
                    stats,
                )
                plain = inst_section["plain_text"]
                sections.append(
                    {
                        "section_id": section_id,
                        "edition_id": EDITION_ID,
                        "parent_section_id": chapter_section_id,
                        "section_type": "section",
                        "heading": inst_section["heading"],
                        "sequence": inst_section["number"],
                    }
                )
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "section_id": section_id,
                        "sequence": 1,
                        "text": plain,
                        "plain_text": plain,
                        "source_locator": locator,
                        "passage_links": links,
                    }
                )

    document = {
        "authors": [_author_record(head)],
        "works": [_work_record(head)],
        "editions": [_edition_record(head)],
        "sections": sections,
        "chunks": chunks,
    }
    extras = {
        "books_imported": len(book_divs),
        "chapters_imported": chapters_imported,
        "numbered_sections_imported": numbered_sections,
        "skipped_top_level_ids": tuple(skipped_ids),
        "scripture": stats,
        "warnings": (),
    }
    return document, extras


def _parse_thml_bytes(raw: bytes) -> ET.Element:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CcelThmlImportError("ThML input is not valid UTF-8.") from exc
    sanitized = _strip_doctype(text)
    parser = _secure_parser()
    try:
        return ET.fromstring(sanitized.encode("utf-8"), parser=parser)
    except ParseError as exc:
        raise CcelThmlImportError(f"Invalid ThML XML: {exc}") from exc


def _strip_doctype(text: str) -> str:
    match = _DOCTYPE_RE.search(text)
    if match is None:
        return text
    start = match.start()
    index = match.end()
    depth = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            continue
        if char == "[":
            depth += 1
            index += 1
            continue
        if char == "]":
            depth = max(0, depth - 1)
            index += 1
            continue
        if char == ">" and depth == 0:
            return text[:start] + text[index + 1 :]
        index += 1
    raise CcelThmlImportError("Unterminated DOCTYPE declaration.")


def _secure_parser() -> ET.XMLParser:
    parser = ET.XMLParser(encoding="utf-8")
    expat_parser = getattr(parser, "parser", None)
    if expat_parser is not None:
        if hasattr(expat_parser, "UseForeignDTD"):
            expat_parser.UseForeignDTD(False)
        if hasattr(expat_parser, "SetParamEntityParsing"):
            expat_parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        if hasattr(expat_parser, "ExternalEntityRefHandler"):
            expat_parser.ExternalEntityRefHandler = _reject_external_entity
    return parser


def _reject_external_entity(*_args: object) -> bool:
    raise CcelThmlImportError("External entity/DTD resolution is disabled.")


def _select_allowed_books(body: ET.Element) -> tuple[list[ET.Element], list[str]]:
    top_divs = [child for child in list(body) if _local(child.tag) == "div1"]
    skipped: list[str] = []
    by_id: dict[str, ET.Element] = {}
    for div in top_divs:
        div_id = (div.get("id") or "").strip()
        if div_id in ALLOWED_BOOK_DIV1_IDS:
            if div_id in by_id:
                raise CcelThmlImportError(f"Duplicate allowlisted book id: {div_id!r}")
            by_id[div_id] = div
        else:
            skipped.append(div_id or "<missing-id>")
    missing = [book_id for book_id in ALLOWED_BOOK_DIV1_IDS if book_id not in by_id]
    if missing:
        raise CcelThmlImportError(
            "Institutes Book I–IV allowlist mismatch; missing div1 id(s): "
            + ", ".join(missing)
        )
    ordered = [by_id[book_id] for book_id in ALLOWED_BOOK_DIV1_IDS]
    return ordered, skipped


def _numbered_sections_from_chapter(chapter_div: ET.Element) -> list[dict[str, Any]]:
    current: dict[str, Any] | None = None
    sections: list[dict[str, Any]] = []
    for child in list(chapter_div):
        tag = _local(child.tag)
        if tag == "p":
            css_class = (child.get("class") or "").strip()
            if css_class in {"intro", "introHead"}:
                continue
            plain = _element_plain_text(child, skip_notes=True)
            number = _numbered_section_start(plain)
            if number is not None:
                if current is not None:
                    sections.append(_finalize_inst_section(current))
                first_p_id = (child.get("id") or "").strip()
                if not first_p_id:
                    raise CcelThmlImportError(
                        "Numbered Institutes section is missing a stable paragraph id."
                    )
                current = {
                    "number": number,
                    "heading": f"{number}.",
                    "first_p_id": first_p_id,
                    "elements": [child],
                    "paragraphs": [plain],
                }
            elif current is not None:
                current["elements"].append(child)
                if plain:
                    current["paragraphs"].append(plain)
            continue
        if current is not None and tag == "note":
            current["elements"].append(child)
    if current is not None:
        sections.append(_finalize_inst_section(current))
    return sections


def _finalize_inst_section(current: dict[str, Any]) -> dict[str, Any]:
    paragraphs = list(current["paragraphs"])
    notes = _collect_notes(current["elements"])
    if notes:
        paragraphs.extend(notes)
    plain = "\n\n".join(part for part in paragraphs if part)
    current["plain_text"] = plain
    return current


def _collect_notes(elements: list[ET.Element]) -> list[str]:
    seen_ids: set[str] = set()
    notes: list[str] = []
    for element in elements:
        for note in _iter_descendants_and_self(element):
            if _local(note.tag) != "note":
                continue
            note_id = (note.get("id") or "") + "|" + (note.get("n") or "")
            if note_id in seen_ids:
                continue
            seen_ids.add(note_id)
            body = _element_plain_text(note, skip_notes=False)
            if not body:
                continue
            marker = (note.get("n") or "").strip()
            notes.append(f"[{marker}] {body}" if marker else body)
    return notes


def _passage_links_for_elements(
    elements: list[ET.Element],
    stats: ScriptureRefStats,
) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen_canonical: set[str] = set()
    for element in elements:
        for ref in _iter_descendants_and_self(element):
            if _local(ref.tag) != "scripRef":
                continue
            for candidate in _scripture_candidates(ref, stats):
                canonical = candidate["canonical_passage"]
                if canonical in seen_canonical:
                    continue
                seen_canonical.add(canonical)
                links.append(candidate)
                stats.imported += 1
    return links


def _scripture_candidates(
    ref: ET.Element,
    stats: ScriptureRefStats,
) -> list[dict[str, str]]:
    osis_raw = (ref.get("osisRef") or "").strip()
    passage = (ref.get("passage") or "").strip()
    display = _element_plain_text(ref, skip_notes=True)
    raw_citation = passage or display

    if not osis_raw:
        stats.seen += 1
        if _EP_REF_RE.match(passage or display):
            stats.skipped_nonbiblical += 1
        else:
            stats.skipped_unparseable += 1
        return []

    tokens = [token for token in osis_raw.split() if token.strip()]
    imported: list[dict[str, str]] = []
    for token in tokens:
        stats.seen += 1
        classified = _classify_osis_token(token)
        if classified[0] == "ok":
            imported.append(
                {
                    "canonical_passage": classified[1],
                    "raw_citation": raw_citation or classified[1],
                }
            )
        elif classified[0] == "chapter_only":
            stats.skipped_chapter_only += 1
        elif classified[0] == "noncanonical":
            stats.skipped_noncanonical += 1
        elif classified[0] == "nonbiblical":
            stats.skipped_nonbiblical += 1
        else:
            stats.skipped_unparseable += 1
    return imported


def _classify_osis_token(token: str) -> tuple[str, str]:
    raw = token.strip()
    if raw.lower().startswith("bible:"):
        raw = raw.split(":", 1)[1].strip()
    if _EP_REF_RE.match(raw):
        return ("nonbiblical", "")
    book_hint = raw.split(".", 1)[0]
    if _is_noncanonical_book(book_hint):
        return ("noncanonical", "")
    if _CHAPTER_ONLY_OSIS_RE.fullmatch(raw):
        if _is_known_canonical_book(book_hint):
            return ("chapter_only", "")
        return ("noncanonical", "")
    try:
        reference = CanonicalReference.parse(raw)
    except CanonicalReferenceError:
        if _CHAPTER_ONLY_OSIS_RE.fullmatch(raw) and _is_known_canonical_book(book_hint):
            return ("chapter_only", "")
        return ("unparseable", "")
    return ("ok", reference.canonical_string())


def _is_noncanonical_book(book: str) -> bool:
    folded = book.strip()
    return folded in _NONCANONICAL_BOOKS or folded.casefold() in {
        item.casefold() for item in _NONCANONICAL_BOOKS
    }


def _is_known_canonical_book(book: str) -> bool:
    if book in OSIS_BY_ID:
        return True
    if book in ENGLISH_OSIS_ALIASES:
        return True
    try:
        CanonicalReference.parse(f"{book}.1.1")
    except CanonicalReferenceError:
        return False
    return True


def _author_record(head: ET.Element | None) -> dict[str, Any]:
    name = _dc_text(head, "DC.Creator", sub="Author", scheme="short-form") or "John Calvin"
    return {
        "author_id": AUTHOR_ID,
        "canonical_name": name,
        "tradition": "reformed",
        "birth_year": 1509,
        "death_year": 1564,
    }


def _work_record(head: ET.Element | None) -> dict[str, Any]:
    title = _dc_text(head, "DC.Title") or "The Institutes of the Christian Religion"
    return {
        "work_id": WORK_ID,
        "author_id": AUTHOR_ID,
        "title": title,
        "original_title": "Institutio Christianae Religionis",
        "tradition": "reformed",
        "original_language": "la",
    }


def _edition_record(head: ET.Element | None) -> dict[str, Any]:
    language = _dc_text(head, "DC.Language") or "en"
    if language.lower() in {"eng", "en"}:
        language = "en"
    rights = _dc_text(head, "DC.Rights") or "Public Domain"
    translator = (
        _dc_text(head, "DC.Creator", sub="Translator", scheme="short-form")
        or "Henry Beveridge"
    )
    return {
        "edition_id": EDITION_ID,
        "work_id": WORK_ID,
        "edition_label": "CCEL ThML Beveridge edition",
        "translator": translator,
        "publication_year": 1845,
        "publisher": _dc_text(head, "DC.Publisher"),
        "language": language,
        "license": rights,
        "rights_status": "public-domain",
        "rights_note": RIGHTS_NOTE,
        "source_url": SOURCE_URL,
        "corpus": "ccel",
        "external_id": _electronic_id(head) or EXTERNAL_ID,
    }


def _electronic_id(head: ET.Element | None) -> str | None:
    if head is None:
        return None
    info = None
    for element in _iter_descendants_and_self(head):
        if _local(element.tag) == "electronicEdInfo":
            info = element
            break
    if info is None:
        return None
    author = _child_text(info, "authorID")
    book = _child_text(info, "bookID")
    if author and book:
        return f"ccel/{author}/{book}"
    return None


def _dc_text(
    head: ET.Element | None,
    tag: str,
    *,
    sub: str | None = None,
    scheme: str | None = None,
) -> str | None:
    if head is None:
        return None
    for element in _iter_descendants_and_self(head):
        if _local(element.tag) != tag:
            continue
        if sub is not None and (element.get("sub") or "") != sub:
            continue
        if scheme is not None and (element.get("scheme") or "") != scheme:
            continue
        text = "".join(element.itertext()).strip()
        if text:
            return text
    return None


def _child_text(parent: ET.Element, tag: str) -> str | None:
    for child in list(parent):
        if _local(child.tag) == tag:
            text = "".join(child.itertext()).strip()
            return text or None
    return None


def _find_child(parent: ET.Element, tag: str) -> ET.Element | None:
    for child in list(parent):
        if _local(child.tag) == tag:
            return child
    for child in parent.iter():
        if child is not parent and _local(child.tag) == tag:
            return child
    return None


def _element_plain_text(element: ET.Element, *, skip_notes: bool) -> str:
    parts: list[str] = []

    def walk(node: ET.Element, skipping: bool) -> None:
        tag = _local(node.tag)
        ignore = skipping or (skip_notes and tag == "note")
        if tag == "br" and not ignore:
            parts.append(" ")
        if node.text and not ignore:
            parts.append(node.text)
        for child in list(node):
            child_skip = ignore or (skip_notes and _local(child.tag) == "note")
            walk(child, child_skip)
            if child.tail and not ignore:
                parts.append(child.tail)

    walk(element, False)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _numbered_section_start(text: str) -> int | None:
    match = _NUMBERED_SECTION_RE.match(text.strip())
    if match is None:
        return None
    return int(match.group(1))


def _iter_descendants_and_self(element: ET.Element):
    yield from element.iter()


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _attr_or_none(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _stable_id(xml_id: str) -> str:
    cleaned = xml_id.strip()
    if not cleaned:
        raise CcelThmlImportError("Missing stable CCEL id.")
    return f"ccel.calvin.institutes.{cleaned}"


def _combine_report(
    theology: TheologyImportReport,
    extras: dict[str, Any],
) -> CcelThmlImportReport:
    stats: ScriptureRefStats = extras["scripture"]
    return CcelThmlImportReport(
        database_path=theology.database_path,
        schema_version=theology.schema_version,
        import_mode=theology.import_mode,
        content_hash=theology.content_hash,
        generated_at=theology.generated_at,
        author_count=theology.author_count,
        work_count=theology.work_count,
        edition_count=theology.edition_count,
        section_count=theology.section_count,
        chunk_count=theology.chunk_count,
        passage_link_count=theology.passage_link_count,
        books_imported=int(extras["books_imported"]),
        chapters_imported=int(extras["chapters_imported"]),
        numbered_sections_imported=int(extras["numbered_sections_imported"]),
        skipped_top_level_ids=tuple(extras["skipped_top_level_ids"]),
        scripture_refs_seen=stats.seen,
        scripture_refs_imported=stats.imported,
        scripture_refs_skipped_chapter_only=stats.skipped_chapter_only,
        scripture_refs_skipped_noncanonical=stats.skipped_noncanonical,
        scripture_refs_skipped_nonbiblical=stats.skipped_nonbiblical,
        scripture_refs_skipped_unparseable=stats.skipped_unparseable,
        warnings=tuple(extras.get("warnings") or ()),
    )
