from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


_HYMN_HEADER_RE = re.compile(
    r"^(?P<number>\d+)(?P<variant>[a-z])?(?:\.\s*(?P<title>.*))?$"
)
_STANZA_RE = re.compile(r"^/(?P<number>\d+)$")
_HASH_RE = re.compile(r"^#[0-9A-Fa-f]{8}$")


@dataclass(frozen=True)
class SourceReference:
    start_line: int
    end_line: int
    header_line: int


@dataclass(frozen=True)
class DtxWarning:
    line_number: int
    message: str
    line: str = ""


@dataclass(frozen=True)
class HymnalMetadata:
    code: str
    title: str = ""
    dtx_code: str = ""
    category: str = ""
    header_comments: tuple[str, ...] = ()


@dataclass(frozen=True)
class Section:
    title: str
    ordinal: int
    line_number: int
    parent_ordinal: int | None = None


@dataclass(frozen=True)
class Stanza:
    number: int
    text: str
    first_line: str
    line_number: int
    technical_hash: str = ""
    heading: str = ""
    metadata_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class Hymn:
    number: int
    variant: str
    first_line: str
    title: str
    title_source: str
    section: Section | None
    stanzas: tuple[Stanza, ...]
    source_metadata: tuple[str, ...]
    raw_source: SourceReference

    @property
    def key(self) -> str:
        return f"{self.number}{self.variant}"


@dataclass(frozen=True)
class HymnalDocument:
    metadata: HymnalMetadata
    sections: tuple[Section, ...]
    hymns: tuple[Hymn, ...]
    warnings: tuple[DtxWarning, ...] = ()


@dataclass(frozen=True)
class HymnalValidationReport:
    hymn_count: int
    base_number_count: int
    number_min: int | None
    number_max: int | None
    variant_numbers: dict[int, tuple[str, ...]]
    duplicate_keys: tuple[str, ...]
    hymns_without_stanzas: tuple[str, ...]
    empty_stanzas: tuple[str, ...]
    technical_hash_lines_in_text: tuple[str, ...]
    section_titles_as_hymns: tuple[str, ...]
    first_line_source_errors: tuple[str, ...]
    last_hymn_key: str
    parser_warning_count: int


@dataclass(frozen=True)
class DtxFormatAudit:
    line_count: int
    header_comments: tuple[str, ...]
    metadata_title: str
    metadata_dtx_code: str
    metadata_category: str
    numbered_hymn_records: int
    section_records: int
    stanza_markers: int
    technical_hash_lines: int
    semicolon_lines: int
    empty_lines: int
    variant_numbers: dict[int, tuple[str, ...]]
    max_stanza_number: int
    nonstandard_lines: tuple[tuple[int, str], ...]
    parser_warnings: tuple[DtxWarning, ...]


@dataclass
class _PendingComments:
    lines: list[str] = field(default_factory=list)
    start_line: int | None = None

    def add(self, line_number: int, text: str) -> None:
        if self.start_line is None:
            self.start_line = line_number
        self.lines.append(text)

    def take(self) -> tuple[tuple[str, ...], int | None]:
        value = tuple(self.lines)
        start = self.start_line
        self.lines.clear()
        self.start_line = None
        return value, start

    def clear(self) -> None:
        self.lines.clear()
        self.start_line = None


@dataclass
class _OpenStanza:
    number: int
    line_number: int
    heading_lines: tuple[str, ...] = ()
    hash_value: str = ""
    text_lines: list[str] = field(default_factory=list)


@dataclass
class _OpenHymn:
    number: int
    variant: str
    header_title: str
    header_line: int
    metadata: tuple[str, ...]
    metadata_start_line: int | None
    section: Section | None
    stanzas: list[Stanza] = field(default_factory=list)
    stanza: _OpenStanza | None = None
    last_content_line: int = 0


def parse_dtx_file(path: str | Path, *, code: str | None = None) -> HymnalDocument:
    source = Path(path)
    text = source.read_text(encoding="utf-8-sig")
    return parse_dtx_text(text, code=code or source.stem)


def parse_dtx_text(text: str, *, code: str = "") -> HymnalDocument:
    lines = text.splitlines()
    warnings: list[DtxWarning] = []
    header_comments: list[str] = []
    metadata_title = ""
    metadata_dtx_code = ""
    metadata_category = ""
    sections: list[Section] = []
    hymns: list[Hymn] = []
    pending = _PendingComments()
    current_hymn: _OpenHymn | None = None
    current_section: Section | None = None
    active_parent_section: Section | None = None
    hymns_since_current_section = False
    seen_record_or_section = False
    seen_header_control = False

    def warn(line_number: int, message: str, line: str = "") -> None:
        warnings.append(DtxWarning(line_number=line_number, message=message, line=line))

    def close_stanza() -> None:
        nonlocal current_hymn
        if current_hymn is None or current_hymn.stanza is None:
            return
        stanza = current_hymn.stanza
        text_lines = [line.strip() for line in stanza.text_lines if line.strip()]
        text_value = "\n".join(text_lines)
        first_line = text_lines[0] if text_lines else ""
        current_hymn.stanzas.append(
            Stanza(
                number=stanza.number,
                text=text_value,
                first_line=first_line,
                line_number=stanza.line_number,
                technical_hash=stanza.hash_value,
                heading=_first_nonempty(stanza.heading_lines),
                metadata_lines=stanza.heading_lines,
            )
        )
        current_hymn.stanza = None

    def close_hymn(end_line: int | None = None) -> None:
        nonlocal current_hymn
        if current_hymn is None:
            return
        close_stanza()
        metadata = current_hymn.metadata
        header_title = current_hymn.header_title.strip()
        title = header_title
        title_source = "header" if header_title else ""
        if not title:
            title = _first_nonempty(metadata)
            title_source = "metadata" if title else ""
        first_line = _first_stanza_line(current_hymn.stanzas)
        source_start = current_hymn.metadata_start_line or current_hymn.header_line
        source_end = end_line or current_hymn.last_content_line or current_hymn.header_line
        hymns.append(
            Hymn(
                number=current_hymn.number,
                variant=current_hymn.variant,
                first_line=first_line,
                title=title,
                title_source=title_source,
                section=current_hymn.section,
                stanzas=tuple(current_hymn.stanzas),
                source_metadata=metadata,
                raw_source=SourceReference(
                    start_line=source_start,
                    end_line=source_end,
                    header_line=current_hymn.header_line,
                ),
            )
        )
        current_hymn = None

    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        marker = line[0]

        if marker == ";":
            comment = line[1:].strip()
            if not seen_record_or_section and not seen_header_control:
                header_comments.append(comment)
            else:
                pending.add(line_number, comment)
            continue

        if marker in {"N", "R", "C"} and not seen_record_or_section:
            seen_header_control = True
            value = line[1:].strip()
            if marker == "N":
                metadata_title = value
            elif marker == "R":
                metadata_dtx_code = value
            elif marker == "C":
                metadata_category = value
            continue

        if marker == ">":
            if current_hymn is not None:
                end_line = (pending.start_line - 1) if pending.start_line else line_number - 1
                close_hymn(end_line=end_line)
            body = line[1:].strip()
            record_match = _HYMN_HEADER_RE.match(body)
            comments, comment_start = pending.take()
            seen_record_or_section = True
            if record_match:
                current_hymn = _OpenHymn(
                    number=int(record_match.group("number")),
                    variant=record_match.group("variant") or "",
                    header_title=(record_match.group("title") or "").strip(),
                    header_line=line_number,
                    metadata=comments,
                    metadata_start_line=comment_start,
                    section=current_section,
                    last_content_line=line_number,
                )
                hymns_since_current_section = True
            else:
                if comments:
                    warn(
                        comment_start or line_number,
                        "Semicolon metadata before section was not attached to a hymn.",
                        " | ".join(comments),
                    )
                if current_section is not None and not hymns_since_current_section:
                    active_parent_section = current_section
                current_section = Section(
                    title=body,
                    ordinal=len(sections) + 1,
                    line_number=line_number,
                    parent_ordinal=active_parent_section.ordinal if active_parent_section else None,
                )
                sections.append(current_section)
                hymns_since_current_section = False
            continue

        stanza_match = _STANZA_RE.match(line)
        if stanza_match:
            comments, _comment_start = pending.take()
            if current_hymn is None:
                warn(line_number, "Stanza marker outside a hymn record.", line)
                continue
            close_stanza()
            current_hymn.stanza = _OpenStanza(
                number=int(stanza_match.group("number")),
                line_number=line_number,
                heading_lines=comments,
            )
            current_hymn.last_content_line = line_number
            continue

        if marker == "#":
            if not _HASH_RE.match(line):
                warn(line_number, "Malformed technical hash line.", line)
            if current_hymn is None or current_hymn.stanza is None:
                warn(line_number, "Technical hash line outside a stanza.", line)
                continue
            if current_hymn.stanza.hash_value:
                warn(line_number, "Multiple technical hash lines for one stanza.", line)
            current_hymn.stanza.hash_value = line
            current_hymn.last_content_line = line_number
            continue

        if marker == " ":
            if pending.lines:
                warn(
                    pending.start_line or line_number,
                    "Semicolon metadata before a text line could not be attached to a stanza or hymn.",
                    " | ".join(pending.lines),
                )
                pending.clear()
            if current_hymn is None or current_hymn.stanza is None:
                warn(line_number, "Text line outside a stanza.", line)
                continue
            current_hymn.stanza.text_lines.append(line[1:].rstrip())
            current_hymn.last_content_line = line_number
            continue

        warn(line_number, "Unrecognized DTX line.", line)

    if current_hymn is not None:
        close_hymn(end_line=len(lines))
    elif pending.lines:
        warn(
            pending.start_line or len(lines),
            "Trailing semicolon metadata was not attached to a hymn.",
            " | ".join(pending.lines),
        )

    metadata = HymnalMetadata(
        code=code or metadata_dtx_code,
        title=metadata_title,
        dtx_code=metadata_dtx_code,
        category=metadata_category,
        header_comments=tuple(header_comments),
    )
    return HymnalDocument(
        metadata=metadata,
        sections=tuple(sections),
        hymns=tuple(hymns),
        warnings=tuple(warnings),
    )


def validate_hymnal(document: HymnalDocument) -> HymnalValidationReport:
    keys = [hymn.key for hymn in document.hymns]
    key_counts = Counter(keys)
    variants: dict[int, list[str]] = defaultdict(list)
    empty_stanzas: list[str] = []
    hashes_in_text: list[str] = []
    first_line_errors: list[str] = []
    section_titles = {section.title for section in document.sections}

    for hymn in document.hymns:
        if hymn.variant:
            variants[hymn.number].append(hymn.variant)
        if hymn.first_line != _first_stanza_line(hymn.stanzas):
            first_line_errors.append(hymn.key)
        for stanza in hymn.stanzas:
            if not stanza.text.strip():
                empty_stanzas.append(f"{hymn.key}/{stanza.number}")
            if any(line.startswith("#") for line in stanza.text.splitlines()):
                hashes_in_text.append(f"{hymn.key}/{stanza.number}")

    numbers = [hymn.number for hymn in document.hymns]
    return HymnalValidationReport(
        hymn_count=len(document.hymns),
        base_number_count=len(set(numbers)),
        number_min=min(numbers) if numbers else None,
        number_max=max(numbers) if numbers else None,
        variant_numbers={k: tuple(v) for k, v in sorted(variants.items())},
        duplicate_keys=tuple(key for key, count in key_counts.items() if count > 1),
        hymns_without_stanzas=tuple(hymn.key for hymn in document.hymns if not hymn.stanzas),
        empty_stanzas=tuple(empty_stanzas),
        technical_hash_lines_in_text=tuple(hashes_in_text),
        section_titles_as_hymns=tuple(
            hymn.key for hymn in document.hymns if hymn.title in section_titles
        ),
        first_line_source_errors=tuple(first_line_errors),
        last_hymn_key=document.hymns[-1].key if document.hymns else "",
        parser_warning_count=len(document.warnings),
    )


def audit_dtx_format(text: str, *, code: str = "") -> DtxFormatAudit:
    document = parse_dtx_text(text, code=code)
    lines = text.splitlines()
    variants: dict[int, list[str]] = defaultdict(list)
    max_stanza = 0
    nonstandard: list[tuple[int, str]] = []

    for hymn in document.hymns:
        if hymn.variant:
            variants[hymn.number].append(hymn.variant)
        for stanza in hymn.stanzas:
            max_stanza = max(max_stanza, stanza.number)

    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        if line[0] in {";", ">", "/", "#", " ", "N", "R", "C"}:
            continue
        nonstandard.append((line_number, line))

    return DtxFormatAudit(
        line_count=len(lines),
        header_comments=document.metadata.header_comments,
        metadata_title=document.metadata.title,
        metadata_dtx_code=document.metadata.dtx_code,
        metadata_category=document.metadata.category,
        numbered_hymn_records=len(document.hymns),
        section_records=len(document.sections),
        stanza_markers=sum(1 for line in lines if _STANZA_RE.match(line)),
        technical_hash_lines=sum(1 for line in lines if line.startswith("#")),
        semicolon_lines=sum(1 for line in lines if line.startswith(";")),
        empty_lines=sum(1 for line in lines if not line),
        variant_numbers={k: tuple(v) for k, v in sorted(variants.items())},
        max_stanza_number=max_stanza,
        nonstandard_lines=tuple(nonstandard),
        parser_warnings=document.warnings,
    )


def hymn_by_key(document: HymnalDocument, key: str) -> Hymn:
    for hymn in document.hymns:
        if hymn.key == key:
            return hymn
    raise KeyError(key)


def _first_nonempty(lines: Iterable[str]) -> str:
    return next((line.strip() for line in lines if line.strip()), "")


def _first_stanza_line(stanzas: Iterable[Stanza]) -> str:
    for stanza in stanzas:
        if stanza.first_line:
            return stanza.first_line
    return ""


__all__ = [
    "DtxFormatAudit",
    "DtxWarning",
    "Hymn",
    "HymnalDocument",
    "HymnalMetadata",
    "HymnalValidationReport",
    "Section",
    "SourceReference",
    "Stanza",
    "audit_dtx_format",
    "hymn_by_key",
    "parse_dtx_file",
    "parse_dtx_text",
    "validate_hymnal",
]
