from __future__ import annotations

import hashlib
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


DOCX_XML_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
RE21_EXPECTED_SHA256 = "c5075014a35aa843707c4a196409f46bfcf86ab950928724d5e36a43cecdbb51"

_HEADER_PREFIX_RE = re.compile(r"^(?P<number>\d{1,3})(?P<body>.+)$")
_STANZA_RE = re.compile(r"^(?P<number>\d{1,2})[\.\s](?P<text>.+)$")
_BIBLICAL_REF_RE = re.compile(
    r"^(?P<ref>(?:[1-4]\s*)?[A-ZÁÉÍÓÖŐÚÜŰ][A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]+"
    r"\s*\d+(?:[,\.]\d+(?:[–-]\d+)?)?)\s*(?P<rest>.*)$"
)
_PSALM_REF_RE = re.compile(r"^(?P<ref>Zsolt\s*\d+)\s*(?P<rest>.*)$")

_NOTE_PREFIXES = (
    "Ajánlott ",
    "Az előző ",
    "Az egyes ",
    "A napi ",
    "A további",
    "E zsoltárt",
    "Énekelhető",
    "Kegyességed",
    "Kiemelt ",
    "Meghallgatható",
    "Többször ",
)

_KNOWN_LEVEL2_SECTIONS = {
    "Istentisztelet",
    "Hitünk alapjai",
    "Az egyházi év",
    "Isten dicsérete",
    "Krisztus követése",
    "Keresztyén élet",
    "Reggeli és esti énekek",
    "Temetés",
    "Esküvő",
    "Keresztelő",
    "Konfirmáció",
    "BIBLIAKÖRI ÉNEKEK",
}


@dataclass(frozen=True)
class DocxParagraph:
    index: int
    text: str
    style: str = ""
    italic: bool = False
    bold: bool = False
    superscript: bool = False


@dataclass(frozen=True)
class DocxSourceReference:
    start_paragraph: int
    end_paragraph: int
    header_paragraph: int


@dataclass(frozen=True)
class DocxWarning:
    paragraph_index: int
    message: str
    text: str = ""


@dataclass(frozen=True)
class DocxHymnalMetadata:
    code: str
    title: str
    source_format: str
    source_checksum: str


@dataclass(frozen=True)
class DocxSection:
    title: str
    ordinal: int
    paragraph_index: int
    parent_ordinal: int | None = None


@dataclass(frozen=True)
class DocxStanza:
    number: int
    text: str
    first_line: str
    paragraph_index: int


@dataclass(frozen=True)
class DocxHymnSourceMetadata:
    text_author: str = ""
    translator: str = ""
    tune: str = ""
    biblical_reference: str = ""
    other: tuple[str, ...] = ()
    raw: str = ""


@dataclass(frozen=True)
class DocxHymn:
    number: int
    variant: str
    canonical_key: str
    first_line: str
    title: str
    title_source: str
    section: DocxSection | None
    stanzas: tuple[DocxStanza, ...]
    source_metadata: DocxHymnSourceMetadata
    raw_source: DocxSourceReference


@dataclass(frozen=True)
class DocxHymnalDocument:
    metadata: DocxHymnalMetadata
    sections: tuple[DocxSection, ...]
    hymns: tuple[DocxHymn, ...]
    paragraphs: tuple[DocxParagraph, ...]
    warnings: tuple[DocxWarning, ...] = ()


@dataclass(frozen=True)
class DocxFormatAudit:
    paragraph_count: int
    nonempty_paragraph_count: int
    paragraph_styles: dict[str, int]
    italic_run_paragraphs: int
    bold_run_paragraphs: int
    superscript_run_paragraphs: int
    hymn_header_candidates: int
    section_candidates: tuple[str, ...]
    irregular_header_examples: tuple[str, ...]


@dataclass(frozen=True)
class DocxValidationReport:
    hymn_count: int
    unique_number_count: int
    number_min: int | None
    number_max: int | None
    number_ranges: tuple[str, ...]
    variant_numbers: dict[int, tuple[str, ...]]
    section_count: int
    stanza_count: int
    duplicate_keys: tuple[str, ...]
    hymns_without_stanzas: tuple[str, ...]
    empty_stanzas: tuple[str, ...]
    missing_first_lines: tuple[str, ...]
    metadata_first_line_errors: tuple[str, ...]
    parser_warning_count: int


def parse_docx_file(
    path: str | Path,
    *,
    code: str = "RE21",
    title: str = "Református Énekeskönyv (2021)",
) -> DocxHymnalDocument:
    source = Path(path)
    checksum = sha256_file(source)
    paragraphs = read_docx_paragraphs(source)
    return parse_docx_paragraphs(
        paragraphs,
        code=code,
        title=title,
        source_checksum=checksum,
    )


def read_docx_paragraphs(path: str | Path) -> tuple[DocxParagraph, ...]:
    with zipfile.ZipFile(Path(path)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs: list[DocxParagraph] = []
    for index, paragraph in enumerate(root.findall(".//w:p", DOCX_XML_NS), start=1):
        text_parts: list[str] = []
        italic = False
        bold = False
        superscript = False
        for run in paragraph.findall("w:r", DOCX_XML_NS):
            text_parts.extend(node.text or "" for node in run.findall("w:t", DOCX_XML_NS))
            run_props = run.find("w:rPr", DOCX_XML_NS)
            if run_props is None:
                continue
            italic = italic or run_props.find("w:i", DOCX_XML_NS) is not None
            bold = bold or run_props.find("w:b", DOCX_XML_NS) is not None
            vertical = run_props.find("w:vertAlign", DOCX_XML_NS)
            if vertical is not None:
                superscript = superscript or vertical.attrib.get(_w_attr("val")) == "superscript"
        text = _clean_text("".join(text_parts))
        if not text:
            continue
        paragraphs.append(
            DocxParagraph(
                index=index,
                text=text,
                style=_paragraph_style(paragraph),
                italic=italic,
                bold=bold,
                superscript=superscript,
            )
        )
    return tuple(paragraphs)


def parse_docx_paragraphs(
    paragraphs: tuple[DocxParagraph, ...],
    *,
    code: str = "RE21",
    title: str = "Református Énekeskönyv (2021)",
    source_checksum: str = "",
) -> DocxHymnalDocument:
    warnings: list[DocxWarning] = []
    header_indexes = _find_hymn_headers(paragraphs, warnings)
    header_index_set = set(header_indexes)
    sections: list[DocxSection] = []
    hymns: list[DocxHymn] = []
    current_major: DocxSection | None = None
    current_level2: DocxSection | None = None
    current_section: DocxSection | None = None
    last_scan_start = 0

    for position, header_pos in enumerate(header_indexes):
        new_sections = _section_candidates(paragraphs[last_scan_start:header_pos])
        for paragraph in new_sections:
            section, current_major, current_level2 = _make_section(
                paragraph,
                len(sections) + 1,
                current_major,
                current_level2,
            )
            sections.append(section)
            current_section = section

        next_header_pos = header_indexes[position + 1] if position + 1 < len(header_indexes) else len(paragraphs)
        hymn = _parse_hymn(
            paragraphs,
            header_pos,
            next_header_pos,
            current_section,
            warnings,
        )
        hymns.append(hymn)
        last_scan_start = header_pos + 1

    return DocxHymnalDocument(
        metadata=DocxHymnalMetadata(
            code=code,
            title=title,
            source_format="docx",
            source_checksum=source_checksum,
        ),
        sections=tuple(sections),
        hymns=tuple(hymns),
        paragraphs=paragraphs,
        warnings=tuple(warnings),
    )


def audit_docx_file(path: str | Path) -> DocxFormatAudit:
    paragraphs = read_docx_paragraphs(path)
    warnings: list[DocxWarning] = []
    header_indexes = _find_hymn_headers(paragraphs, warnings)
    style_counts = Counter(paragraph.style for paragraph in paragraphs)
    sections = tuple(paragraph.text for paragraph in _section_candidates(paragraphs))
    irregular = tuple(
        paragraphs[index].text
        for index in header_indexes
        if not re.match(r"^\d+\s*szöveg", paragraphs[index].text)
    )
    return DocxFormatAudit(
        paragraph_count=len(paragraphs),
        nonempty_paragraph_count=len(paragraphs),
        paragraph_styles=dict(style_counts),
        italic_run_paragraphs=sum(1 for paragraph in paragraphs if paragraph.italic),
        bold_run_paragraphs=sum(1 for paragraph in paragraphs if paragraph.bold),
        superscript_run_paragraphs=sum(1 for paragraph in paragraphs if paragraph.superscript),
        hymn_header_candidates=len(header_indexes),
        section_candidates=sections,
        irregular_header_examples=irregular[:40],
    )


def validate_docx_document(document: DocxHymnalDocument) -> DocxValidationReport:
    keys = [hymn.canonical_key for hymn in document.hymns]
    duplicate_keys = tuple(sorted(key for key, count in Counter(keys).items() if count > 1))
    numbers = [hymn.number for hymn in document.hymns]
    variant_numbers: dict[int, tuple[str, ...]] = {}
    for hymn in document.hymns:
        if hymn.variant:
            variant_numbers.setdefault(hymn.number, tuple())
            variant_numbers[hymn.number] = tuple(sorted((*variant_numbers[hymn.number], hymn.variant)))
    hymns_without_stanzas = tuple(hymn.canonical_key for hymn in document.hymns if not hymn.stanzas)
    empty_stanzas = tuple(
        f"{hymn.canonical_key}:{stanza.number}"
        for hymn in document.hymns
        for stanza in hymn.stanzas
        if not stanza.text.strip()
    )
    missing_first_lines = tuple(hymn.canonical_key for hymn in document.hymns if not hymn.first_line.strip())
    metadata_first_line_errors = tuple(
        hymn.canonical_key
        for hymn in document.hymns
        if _looks_like_metadata(hymn.first_line)
    )
    return DocxValidationReport(
        hymn_count=len(document.hymns),
        unique_number_count=len(set(numbers)),
        number_min=min(numbers) if numbers else None,
        number_max=max(numbers) if numbers else None,
        number_ranges=_number_ranges(sorted(set(numbers))),
        variant_numbers=variant_numbers,
        section_count=len(document.sections),
        stanza_count=sum(len(hymn.stanzas) for hymn in document.hymns),
        duplicate_keys=duplicate_keys,
        hymns_without_stanzas=hymns_without_stanzas,
        empty_stanzas=empty_stanzas,
        missing_first_lines=missing_first_lines,
        metadata_first_line_errors=metadata_first_line_errors,
        parser_warning_count=len(document.warnings),
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_hymn_headers(
    paragraphs: tuple[DocxParagraph, ...],
    warnings: list[DocxWarning],
) -> list[int]:
    headers: list[int] = []
    last_number = 0
    for index, paragraph in enumerate(paragraphs):
        number = _header_number(paragraph.text)
        if number is None:
            continue
        if number <= last_number:
            continue
        if not _is_probable_header_body(paragraph.text):
            continue
        if index + 1 >= len(paragraphs):
            continue
        headers.append(index)
        last_number = number
    if headers:
        return headers
    warnings.append(DocxWarning(0, "no_hymn_headers_detected"))
    return headers


def _parse_hymn(
    paragraphs: tuple[DocxParagraph, ...],
    header_pos: int,
    next_header_pos: int,
    section: DocxSection | None,
    warnings: list[DocxWarning],
) -> DocxHymn:
    header = paragraphs[header_pos]
    number, metadata = _parse_header(header.text)
    content = list(paragraphs[header_pos + 1 : next_header_pos])
    content = _trim_trailing_section_material(content)
    extra_metadata: list[str] = []
    stanzas: list[DocxStanza] = []
    auto_stanza_number = 1
    for paragraph in content:
        if _is_stanza_heading(paragraph.text):
            extra_metadata.append(paragraph.text)
            continue
        if _looks_like_metadata(paragraph.text):
            extra_metadata.append(paragraph.text)
            continue
        stanza_match = _STANZA_RE.match(paragraph.text)
        if stanza_match:
            stanza_number = int(stanza_match.group("number"))
            stanza_text = stanza_match.group("text").strip()
        else:
            stanza_number = auto_stanza_number
            stanza_text = paragraph.text
        first_line = _first_line(stanza_text)
        stanzas.append(
            DocxStanza(
                number=stanza_number,
                text=stanza_text,
                first_line=first_line,
                paragraph_index=paragraph.index,
            )
        )
        auto_stanza_number = max(auto_stanza_number + 1, stanza_number + 1)
    if not stanzas:
        warnings.append(DocxWarning(header.index, "hymn_without_stanzas", header.text))
    first_line = _first_line(stanzas[0].text) if stanzas else ""
    return DocxHymn(
        number=number,
        variant="",
        canonical_key=str(number),
        first_line=first_line,
        title=first_line,
        title_source="first_line" if first_line else "",
        section=section,
        stanzas=tuple(stanzas),
        source_metadata=_merge_metadata(metadata, tuple(extra_metadata)),
        raw_source=DocxSourceReference(
            start_paragraph=header.index,
            end_paragraph=(content[-1].index if content else header.index),
            header_paragraph=header.index,
        ),
    )


def _parse_header(text: str) -> tuple[int, DocxHymnSourceMetadata]:
    match = _HEADER_PREFIX_RE.match(text)
    if not match:
        raise ValueError(f"Invalid hymn header: {text!r}")
    number = int(match.group("number"))
    body = match.group("body").strip()
    biblical_reference = ""
    psalm_match = _PSALM_REF_RE.match(body)
    if psalm_match:
        biblical_reference = _clean_text(psalm_match.group("ref"))
        body = psalm_match.group("rest").strip()
    elif "szöveg" in body:
        biblical_match = _BIBLICAL_REF_RE.match(body)
        if biblical_match and not biblical_match.group("rest").lstrip().startswith(("és", ":")):
            biblical_reference = _clean_text(biblical_match.group("ref"))
            body = biblical_match.group("rest").strip()
    body = body.lstrip("| ").strip()
    metadata = _parse_metadata_body(body)
    return number, DocxHymnSourceMetadata(
        text_author=metadata.text_author,
        translator=metadata.translator,
        tune=metadata.tune,
        biblical_reference=biblical_reference,
        other=metadata.other,
        raw=text,
    )


def _parse_metadata_body(body: str) -> DocxHymnSourceMetadata:
    text_author = ""
    translator = ""
    tune = ""
    other: list[str] = []
    for part in [segment.strip() for segment in body.split("|") if segment.strip()]:
        lowered = part.casefold()
        if lowered.startswith("szöveg és dallam"):
            value = _after_label(part, "szöveg és dallam")
            text_author = text_author or value
            tune = tune or value
        elif lowered.startswith("szöveg, dallam"):
            value = _after_label(part, "szöveg, dallam")
            text_author = text_author or value
            tune = tune or value
        elif lowered.startswith("szöveg"):
            text_author = text_author or _after_label(part, "szöveg")
        elif lowered.startswith("fordítás"):
            translator = translator or _after_label(part, "fordítás")
        elif "dallam:" in lowered or lowered.startswith("dallam"):
            tune = tune or _after_label(part, "dallam")
        elif not text_author:
            text_author = part
        elif not tune:
            tune = part
        else:
            other.append(part)
    return DocxHymnSourceMetadata(
        text_author=text_author,
        translator=translator,
        tune=tune,
        other=tuple(other),
        raw=body,
    )


def _merge_metadata(
    header_metadata: DocxHymnSourceMetadata,
    extra: tuple[str, ...],
) -> DocxHymnSourceMetadata:
    return DocxHymnSourceMetadata(
        text_author=header_metadata.text_author,
        translator=header_metadata.translator,
        tune=header_metadata.tune,
        biblical_reference=header_metadata.biblical_reference,
        other=tuple((*header_metadata.other, *extra)),
        raw=header_metadata.raw,
    )


def _section_candidates(paragraphs: tuple[DocxParagraph, ...] | list[DocxParagraph]) -> tuple[DocxParagraph, ...]:
    return tuple(paragraph for paragraph in paragraphs if _is_section_candidate_text(paragraph.text))


def _make_section(
    paragraph: DocxParagraph,
    ordinal: int,
    current_major: DocxSection | None,
    current_level2: DocxSection | None,
) -> tuple[DocxSection, DocxSection | None, DocxSection | None]:
    title = paragraph.text
    if _is_major_section(title):
        section = DocxSection(title=title, ordinal=ordinal, paragraph_index=paragraph.index)
        return section, section, None
    if title in _KNOWN_LEVEL2_SECTIONS or current_major is None:
        parent = current_major.ordinal if current_major else None
        section = DocxSection(
            title=title,
            ordinal=ordinal,
            paragraph_index=paragraph.index,
            parent_ordinal=parent,
        )
        return section, current_major, section
    parent = current_level2.ordinal if current_level2 else current_major.ordinal if current_major else None
    section = DocxSection(
        title=title,
        ordinal=ordinal,
        paragraph_index=paragraph.index,
        parent_ordinal=parent,
    )
    return section, current_major, current_level2


def _trim_trailing_section_material(content: list[DocxParagraph]) -> list[DocxParagraph]:
    first_section_index = None
    for index, paragraph in enumerate(content):
        if _is_section_candidate_text(paragraph.text):
            first_section_index = index
            break
    if first_section_index == 0:
        return content
    return content[:first_section_index] if first_section_index is not None else content


def _header_number(text: str) -> int | None:
    if _STANZA_RE.match(text):
        return None
    match = _HEADER_PREFIX_RE.match(text)
    if not match:
        return None
    number = int(match.group("number"))
    return number if 1 <= number <= 999 else None


def _is_probable_header_body(text: str) -> bool:
    match = _HEADER_PREFIX_RE.match(text)
    if not match:
        return False
    body = match.group("body").strip()
    if not body:
        return False
    return (
        "szöveg" in body
        or "fordítás" in body
        or "dallam" in body
        or "|" in body
        or bool(_PSALM_REF_RE.match(body))
        or bool(_BIBLICAL_REF_RE.match(body))
    )


def _is_section_candidate_text(text: str) -> bool:
    text = _clean_text(text)
    if not text or len(text) > 90 or len(text) == 1:
        return False
    if _HEADER_PREFIX_RE.match(text) or _STANZA_RE.match(text):
        return False
    if any(text.startswith(prefix) for prefix in _NOTE_PREFIXES):
        return False
    if "|" in text or ":" in text:
        return False
    if text.endswith((".", "!", "?")):
        return False
    if _is_major_section(text):
        return True
    return bool(re.search(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]", text)) and len(text.split()) <= 8


def _is_stanza_heading(text: str) -> bool:
    return bool(re.fullmatch(r"[A-ZÁÉÍÓÖŐÚÜŰ]", _clean_text(text)))


def _looks_like_metadata(text: str) -> bool:
    return text.startswith("Kiemelt versek") or any(text.startswith(prefix) for prefix in _NOTE_PREFIXES)


def _is_major_section(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and all(char.upper() == char for char in letters)


def _paragraph_style(paragraph: ET.Element) -> str:
    properties = paragraph.find("w:pPr", DOCX_XML_NS)
    if properties is None:
        return ""
    style = properties.find("w:pStyle", DOCX_XML_NS)
    if style is None:
        return ""
    return style.attrib.get(_w_attr("val"), "")


def _w_attr(name: str) -> str:
    return f"{{{DOCX_XML_NS['w']}}}{name}"


def _after_label(text: str, label: str) -> str:
    value = re.sub(rf"^{re.escape(label)}\s*:?", "", text, flags=re.IGNORECASE)
    return value.strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _first_line(text: str) -> str:
    value = _clean_text(text)
    first = re.split(r"\s*/\s*|\n", value, maxsplit=1)[0]
    return first.strip()


def _number_ranges(numbers: list[int]) -> tuple[str, ...]:
    if not numbers:
        return ()
    ranges: list[str] = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append(f"{start}" if start == previous else f"{start}-{previous}")
        start = previous = number
    ranges.append(f"{start}" if start == previous else f"{start}-{previous}")
    return tuple(ranges)


__all__ = [
    "DocxFormatAudit",
    "DocxHymn",
    "DocxHymnSourceMetadata",
    "DocxHymnalDocument",
    "DocxHymnalMetadata",
    "DocxParagraph",
    "DocxSection",
    "DocxSourceReference",
    "DocxStanza",
    "DocxValidationReport",
    "DocxWarning",
    "RE21_EXPECTED_SHA256",
    "audit_docx_file",
    "parse_docx_file",
    "parse_docx_paragraphs",
    "read_docx_paragraphs",
    "sha256_file",
    "validate_docx_document",
]
