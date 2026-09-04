"""Generic CCEL ThML helpers shared by source-specific importers.

No network, no DTD fetch, no schema change. Source allowlists and chunking
policies live in the caller (Calvin Institutes vs Hodge Systematic Theology).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree.ElementTree import ParseError

from textus_kb.books import ENGLISH_OSIS_ALIASES, OSIS_BY_ID
from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.theology_sqlite import TheologyImportError

_DOCTYPE_RE = re.compile(r"<!DOCTYPE\b", re.IGNORECASE)
_CHAPTER_ONLY_OSIS_RE = re.compile(r"^[A-Za-z0-9]+\.\d+$")
_EP_REF_RE = re.compile(r"^Ep\.?\s*\d+", re.IGNORECASE)
_ALT_SCHEME_RE = re.compile(r"(?i)^Bible\.[A-Za-z][A-Za-z0-9]*:")
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


class CcelThmlCoreError(TheologyImportError):
    """Raised when generic CCEL ThML parsing or scripture policy fails."""


@dataclass
class ScriptureRefStats:
    seen: int = 0
    imported: int = 0
    skipped_chapter_only: int = 0
    skipped_noncanonical: int = 0
    skipped_nonbiblical: int = 0
    skipped_unparseable: int = 0
    skipped_no_osis: int = 0
    skipped_malformed: int = 0
    duplicate_links: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def parse_thml_file(path: str | Path) -> ET.Element:
    file_path = Path(path)
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        raise CcelThmlCoreError(f"Cannot read ThML file: {file_path}") from exc
    return parse_thml_bytes(raw)


def parse_thml_bytes(raw: bytes) -> ET.Element:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CcelThmlCoreError("ThML input is not valid UTF-8.") from exc
    sanitized = strip_doctype(text)
    parser = secure_parser()
    try:
        return ET.fromstring(sanitized.encode("utf-8"), parser=parser)
    except ParseError as exc:
        raise CcelThmlCoreError(f"Invalid ThML XML: {exc}") from exc


def strip_doctype(text: str) -> str:
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
    raise CcelThmlCoreError("Unterminated DOCTYPE declaration.")


def secure_parser() -> ET.XMLParser:
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
    raise CcelThmlCoreError("External entity/DTD resolution is disabled.")


def local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def find_child(parent: ET.Element, tag: str) -> ET.Element | None:
    for child in list(parent):
        if local_tag(child.tag) == tag:
            return child
    for child in parent.iter():
        if child is not parent and local_tag(child.tag) == tag:
            return child
    return None


def iter_descendants_and_self(element: ET.Element):
    yield from element.iter()


def element_plain_text(element: ET.Element, *, skip_notes: bool) -> str:
    parts: list[str] = []

    def walk(node: ET.Element, skipping: bool) -> None:
        tag = local_tag(node.tag)
        ignore = skipping or (skip_notes and tag == "note")
        if tag == "br" and not ignore:
            parts.append(" ")
        if node.text and not ignore:
            parts.append(node.text)
        for child in list(node):
            child_skip = ignore or (skip_notes and local_tag(child.tag) == "note")
            walk(child, child_skip)
            if child.tail and not ignore:
                parts.append(child.tail)

    walk(element, False)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def collect_notes(elements: list[ET.Element]) -> list[str]:
    seen_ids: set[str] = set()
    notes: list[str] = []
    for element in elements:
        for note in iter_descendants_and_self(element):
            if local_tag(note.tag) != "note":
                continue
            note_id = (note.get("id") or "") + "|" + (note.get("n") or "")
            if note_id in seen_ids:
                continue
            seen_ids.add(note_id)
            body = element_plain_text(note, skip_notes=False)
            if not body:
                continue
            marker = (note.get("n") or "").strip()
            notes.append(f"[{marker}] {body}" if marker else body)
    return notes


def paragraph_plain_text(element: ET.Element) -> str:
    body = element_plain_text(element, skip_notes=True)
    notes = collect_notes([element])
    parts = [part for part in [body, *notes] if part]
    return "\n\n".join(parts)


def select_allowlisted_div1(
    body: ET.Element,
    allowed_ids: tuple[str, ...],
    *,
    duplicate_template: str = "Duplicate allowlisted div1 id: {div_id}",
    missing_template: str = "Allowlist mismatch; missing div1 id(s): {ids}",
) -> tuple[list[ET.Element], list[str]]:
    top_divs = [child for child in list(body) if local_tag(child.tag) == "div1"]
    skipped: list[str] = []
    by_id: dict[str, ET.Element] = {}
    for div in top_divs:
        div_id = (div.get("id") or "").strip()
        if div_id in allowed_ids:
            if div_id in by_id:
                raise CcelThmlCoreError(duplicate_template.format(div_id=repr(div_id)))
            by_id[div_id] = div
        else:
            skipped.append(div_id or "<missing-id>")
    missing = [item for item in allowed_ids if item not in by_id]
    if missing:
        raise CcelThmlCoreError(missing_template.format(ids=", ".join(missing)))
    ordered = [by_id[item] for item in allowed_ids]
    return ordered, skipped


def dc_text(
    head: ET.Element | None,
    tag: str,
    *,
    sub: str | None = None,
    scheme: str | None = None,
) -> str | None:
    if head is None:
        return None
    for element in iter_descendants_and_self(head):
        if local_tag(element.tag) != tag:
            continue
        if sub is not None and (element.get("sub") or "") != sub:
            continue
        if scheme is not None and (element.get("scheme") or "") != scheme:
            continue
        text = "".join(element.itertext()).strip()
        if text:
            return text
    return None


def dc_text_all(
    head: ET.Element | None,
    tag: str,
    *,
    sub: str | None = None,
    scheme: str | None = None,
) -> list[str]:
    """Like ``dc_text`` but returns every matching element's text, in
    document order — needed for sources with more than one contributor of
    the same role (e.g. JFB's three co-authors), where ``dc_text`` (first
    match only) would silently drop the rest."""
    if head is None:
        return []
    found: list[str] = []
    for element in iter_descendants_and_self(head):
        if local_tag(element.tag) != tag:
            continue
        if sub is not None and (element.get("sub") or "") != sub:
            continue
        if scheme is not None and (element.get("scheme") or "") != scheme:
            continue
        text = "".join(element.itertext()).strip()
        if text:
            found.append(text)
    return found


def child_text(parent: ET.Element, tag: str) -> str | None:
    for child in list(parent):
        if local_tag(child.tag) == tag:
            text = "".join(child.itertext()).strip()
            return text or None
    return None


def electronic_id(head: ET.Element | None) -> str | None:
    if head is None:
        return None
    info = None
    for element in iter_descendants_and_self(head):
        if local_tag(element.tag) == "electronicEdInfo":
            info = element
            break
    if info is None:
        return None
    author = child_text(info, "authorID")
    book = child_text(info, "bookID")
    if author and book:
        return f"ccel/{author}/{book}"
    return None


def electronic_book_id(head: ET.Element | None) -> str | None:
    if head is None:
        return None
    for element in iter_descendants_and_self(head):
        if local_tag(element.tag) == "electronicEdInfo":
            return child_text(element, "bookID")
    return None


def passage_links_for_elements(
    elements: list[ET.Element],
    stats: ScriptureRefStats,
) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen_canonical: set[str] = set()
    for element in elements:
        for ref in iter_descendants_and_self(element):
            if local_tag(ref.tag) != "scripRef":
                continue
            for candidate in scripture_candidates(ref, stats):
                canonical = candidate["canonical_passage"]
                if canonical in seen_canonical:
                    stats.duplicate_links += 1
                    continue
                seen_canonical.add(canonical)
                links.append(candidate)
                stats.imported += 1
    return links


def scripture_candidates(
    ref: ET.Element,
    stats: ScriptureRefStats,
) -> list[dict[str, str]]:
    osis_raw = (ref.get("osisRef") or "").strip()
    passage = (ref.get("passage") or "").strip()
    display = element_plain_text(ref, skip_notes=True)
    raw_citation = passage or display

    if not osis_raw:
        stats.seen += 1
        if _EP_REF_RE.match(passage or display):
            stats.skipped_nonbiblical += 1
        else:
            stats.skipped_no_osis += 1
        return []

    tokens = [token for token in osis_raw.split() if token.strip()]
    imported: list[dict[str, str]] = []
    for token in tokens:
        stats.seen += 1
        kind, canonical = classify_osis_token(token)
        if kind == "ok":
            imported.append(
                {
                    "canonical_passage": canonical,
                    "raw_citation": raw_citation or canonical,
                }
            )
        elif kind == "chapter_only":
            stats.skipped_chapter_only += 1
        elif kind == "noncanonical":
            stats.skipped_noncanonical += 1
        elif kind == "nonbiblical":
            stats.skipped_nonbiblical += 1
        elif kind == "malformed":
            stats.skipped_malformed += 1
        else:
            stats.skipped_unparseable += 1
    return imported


def classify_osis_token(token: str) -> tuple[str, str]:
    raw = token.strip()
    if not raw:
        return ("unparseable", "")
    if _ALT_SCHEME_RE.match(raw):
        return ("malformed", "")
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
    except CanonicalReferenceError as exc:
        message = str(exc)
        if "Reversed" in message:
            return ("malformed", "")
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
