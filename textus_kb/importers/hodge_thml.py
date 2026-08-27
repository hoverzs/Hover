"""Charles Hodge Systematic Theology CCEL/ThML pilot importer.

Isolated Volume I–III pilot. Does not write the Calvin production theology DB,
does not download, and does not change schema.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from textus_kb.importers.ccel_thml_core import (
    CcelThmlCoreError,
    ScriptureRefStats,
    dc_text,
    electronic_book_id,
    electronic_id,
    find_child,
    local_tag,
    paragraph_plain_text,
    parse_thml_file,
    passage_links_for_elements,
    select_allowlisted_div1,
)
from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    TheologyImportReport,
    import_theology_sqlite,
)

IMPORT_MODE_HODGE_THML = "hodge_thml"
CHUNK_CHAR_THRESHOLD = 10_000

AUTHOR_ID = "ccel.hodge"
WORK_ID = "ccel.hodge.systematic_theology"

RIGHTS_STATUS = "needs-review"
LICENSE_PLACEHOLDER = "unspecified"
PUBLICATION_YEAR = 1871
RIGHTS_NOTE = (
    "Original 1871 Charles Hodge text; author died 1878. "
    "CCEL electronic markup dated 2005. DC.Rights is empty on the source ThML. "
    "Title, prefatory, indexes, and CCEL staff description are excluded. "
    "Production reuse requires explicit rights review."
)

_SECTION_NUMBER_RE = re.compile(r"^\s*(\d+)\.")
_SECTION_MARK_RE = re.compile(r"^\s*\u00a7\s*(\d+)\b")


@dataclass(frozen=True)
class HodgeDiv1Spec:
    xml_id: str
    section_type: str
    expected_title_prefix: str
    heading: str


@dataclass(frozen=True)
class HodgeVolumePolicy:
    volume: int
    roman: str
    book_id: str
    heading: str
    edition_label: str
    edition_id: str
    source_url: str
    external_id: str
    locator_prefix: str
    section_id_prefix: str
    div1s: tuple[HodgeDiv1Spec, ...]

    @property
    def allowed_div1_ids(self) -> tuple[str, ...]:
        return tuple(spec.xml_id for spec in self.div1s)


def _volume_policy(
    volume: int,
    *,
    roman: str,
    book_id: str,
    div1s: tuple[HodgeDiv1Spec, ...],
) -> HodgeVolumePolicy:
    return HodgeVolumePolicy(
        volume=volume,
        roman=roman,
        book_id=book_id,
        heading=f"Vol. {roman}",
        edition_label=f"Volume {roman} (CCEL ThML)",
        edition_id=f"ccel.hodge.systematic_theology.vol{volume}.ccel_thml",
        source_url=f"https://www.ccel.org/ccel/hodge/{book_id}.xml",
        external_id=f"ccel/hodge/{book_id}",
        locator_prefix=f"ccel:hodge/{book_id}",
        section_id_prefix=f"ccel.hodge.systematic_theology.vol{volume}",
        div1s=div1s,
    )


VOLUME_POLICIES: dict[int, HodgeVolumePolicy] = {
    1: _volume_policy(
        1,
        roman="I",
        book_id="theology1",
        div1s=(
            HodgeDiv1Spec("iii", "introduction", "Introduction", "Introduction"),
            HodgeDiv1Spec("iv", "part", "Part I. Theology Proper", "Part I"),
        ),
    ),
    2: _volume_policy(
        2,
        roman="II",
        book_id="theology2",
        div1s=(
            HodgeDiv1Spec("iii", "part", "Part II. Anthropology", "Part II"),
            HodgeDiv1Spec("iv", "part", "Part III. Soteriology", "Part III"),
        ),
    ),
    3: _volume_policy(
        3,
        roman="III",
        book_id="theology3",
        div1s=(
            HodgeDiv1Spec("iii", "part", "Part III. Continued", "Part III"),
            HodgeDiv1Spec("iv", "part", "Part IV. Eschatology", "Part IV"),
        ),
    ),
}

BOOK_ID_TO_VOLUME = {
    policy.book_id: policy.volume for policy in VOLUME_POLICIES.values()
}

# Vol. II ids kept for existing tests; I/II/III all use the same div1 ids.
ALLOWED_PART_DIV1_IDS: tuple[str, ...] = VOLUME_POLICIES[2].allowed_div1_ids
EXPECTED_BOOK_ID = VOLUME_POLICIES[2].book_id
EDITION_ID = VOLUME_POLICIES[2].edition_id
SOURCE_URL = VOLUME_POLICIES[2].source_url
EXTERNAL_ID = VOLUME_POLICIES[2].external_id
LOCATOR_PREFIX = VOLUME_POLICIES[2].locator_prefix
SECTION_ID_PREFIX = VOLUME_POLICIES[2].section_id_prefix


class HodgeThmlImportError(CcelThmlCoreError):
    """Raised when the Hodge Systematic Theology ThML cannot be imported."""


@dataclass
class HodgeThmlImportReport:
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
    volume: int = 0
    parts: int = 0
    chapters: int = 0
    sections: int = 0
    split_sections: int = 0
    split_chunks: int = 0
    skipped_top_level_ids: tuple[str, ...] = ()
    scripture_refs_seen: int = 0
    passage_links_imported: int = 0
    skipped_chapter_only: int = 0
    skipped_noncanonical: int = 0
    skipped_no_osis: int = 0
    skipped_unparseable: int = 0
    skipped_malformed: int = 0
    duplicate_links: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        payload["skipped_top_level_ids"] = list(self.skipped_top_level_ids)
        payload["warnings"] = list(self.warnings)
        return payload


def import_hodge_systematic_theology_thml(
    xml_path: str | Path,
    *,
    database_path: str | Path,
    volume: int | None = None,
    atomic: bool = True,
) -> HodgeThmlImportReport:
    target = Path(database_path)
    _reject_production_database(target)
    document, extras = parse_hodge_systematic_theology_thml(xml_path, volume=volume)
    theology = import_theology_sqlite(
        document=document,
        database_path=target,
        import_mode=IMPORT_MODE_HODGE_THML,
        atomic=atomic,
    )
    return _combine_report(theology, extras)


def parse_hodge_systematic_theology_thml(
    xml_path: str | Path,
    *,
    volume: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return _parse_hodge_systematic_theology_thml(xml_path, volume=volume)
    except CcelThmlCoreError as exc:
        if isinstance(exc, HodgeThmlImportError):
            raise
        raise HodgeThmlImportError(str(exc)) from exc


def _parse_hodge_systematic_theology_thml(
    xml_path: str | Path,
    *,
    volume: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = parse_thml_file(xml_path)
    if local_tag(root.tag) != "ThML":
        raise HodgeThmlImportError(f"Expected ThML root, got {local_tag(root.tag)!r}.")

    head = find_child(root, "ThML.head")
    body = find_child(root, "ThML.body")
    if body is None:
        raise HodgeThmlImportError("ThML.body is missing.")
    policy = _resolve_volume_policy(head, volume)

    part_divs, skipped_ids = select_allowlisted_div1(
        body,
        policy.allowed_div1_ids,
        duplicate_template=(
            f"Duplicate allowlisted Volume {policy.roman} div1 id: {{div_id}}"
        ),
        missing_template=(
            f"Volume {policy.roman} allowlist mismatch; missing div1 id(s): {{ids}}"
        ),
    )
    _assert_expected_div1_titles(part_divs, policy)

    stats = ScriptureRefStats()
    sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    chapters_imported = 0
    div3_imported = 0
    split_sections = 0
    split_chunks = 0

    volume_section_id = policy.section_id_prefix
    sections.append(
        {
            "section_id": volume_section_id,
            "edition_id": policy.edition_id,
            "parent_section_id": None,
            "section_type": "volume",
            "heading": policy.heading,
            "sequence": 1,
        }
    )

    for part_index, (part_div, spec) in enumerate(zip(part_divs, policy.div1s), start=1):
        part_xml_id = _require_xml_id(part_div, kind=spec.section_type)
        part_section_id = _stable_id(part_xml_id, policy)
        sections.append(
            {
                "section_id": part_section_id,
                "edition_id": policy.edition_id,
                "parent_section_id": volume_section_id,
                "section_type": spec.section_type,
                "heading": spec.heading,
                "sequence": part_index,
            }
        )
        chapter_divs = [
            child for child in list(part_div) if local_tag(child.tag) == "div2"
        ]
        for chapter_index, chapter_div in enumerate(chapter_divs, start=1):
            chapters_imported += 1
            chapter_xml_id = _require_xml_id(chapter_div, kind="chapter")
            chapter_section_id = _stable_id(chapter_xml_id, policy)
            sections.append(
                {
                    "section_id": chapter_section_id,
                    "edition_id": policy.edition_id,
                    "parent_section_id": part_section_id,
                    "section_type": "chapter",
                    "heading": _attr_or_none(chapter_div.get("title")),
                    "sequence": chapter_index,
                }
            )
            for subsection in _div3_sections(chapter_div):
                div3_imported += 1
                section_id = _stable_id(subsection["xml_id"], policy)
                sections.append(
                    {
                        "section_id": section_id,
                        "edition_id": policy.edition_id,
                        "parent_section_id": chapter_section_id,
                        "section_type": "subsection",
                        "heading": subsection["heading"],
                        "sequence": subsection["number"],
                    }
                )
                packed = pack_paragraph_groups(
                    subsection["units"],
                    threshold=CHUNK_CHAR_THRESHOLD,
                )
                if len(packed) > 1:
                    split_sections += 1
                    split_chunks += len(packed)
                for chunk_index, group in enumerate(packed, start=1):
                    elements = [unit["element"] for unit in group]
                    plain = join_paragraph_plain([unit["plain"] for unit in group])
                    locator = (
                        f"{policy.locator_prefix}#"
                        f"{_leading_locator_id(group, subsection['xml_id'])}"
                    )
                    chunk_id = _chunk_id(section_id, chunk_index, split=len(packed) > 1)
                    chunks.append(
                        {
                            "chunk_id": chunk_id,
                            "section_id": section_id,
                            "sequence": chunk_index,
                            "text": plain,
                            "plain_text": plain,
                            "source_locator": locator,
                            "passage_links": passage_links_for_elements(elements, stats),
                        }
                    )

    document = {
        "authors": [_author_record(head)],
        "works": [_work_record()],
        "editions": [_edition_record(head, policy)],
        "sections": sections,
        "chunks": chunks,
    }
    extras = {
        "volume": policy.volume,
        "parts": len(part_divs),
        "chapters": chapters_imported,
        "sections": div3_imported,
        "split_sections": split_sections,
        "split_chunks": split_chunks,
        "skipped_top_level_ids": tuple(skipped_ids),
        "scripture": stats,
        "warnings": (),
    }
    return document, extras


def pack_paragraph_groups(
    units: list[dict[str, Any]],
    *,
    threshold: int,
) -> list[list[dict[str, Any]]]:
    nonempty = [unit for unit in units if unit["plain"]]
    if not nonempty:
        raise HodgeThmlImportError("Hodge div3 has no importable paragraph text.")
    if len(join_paragraph_plain([unit["plain"] for unit in nonempty])) <= threshold:
        return [nonempty]

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_len = 0
    for unit in nonempty:
        add_len = len(unit["plain"])
        separator = 2 if current else 0
        if current and current_len + separator + add_len > threshold:
            groups.append(current)
            current = [unit]
            current_len = add_len
            continue
        current.append(unit)
        current_len += separator + add_len
    if current:
        groups.append(current)
    return groups


def join_paragraph_plain(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part)


def _div3_sections(chapter_div: ET.Element) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for child in list(chapter_div):
        if local_tag(child.tag) != "div3":
            continue
        xml_id = _require_xml_id(child, kind="section")
        units = _paragraph_units(child)
        title = (child.get("title") or "").strip()
        number = _section_number(title, units)
        found.append(
            {
                "xml_id": xml_id,
                "number": number,
                "heading": _subsection_heading(number, title),
                "units": units,
            }
        )
    return found


def _paragraph_units(div3: ET.Element) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for child in list(div3):
        tag = local_tag(child.tag)
        if tag == "p":
            plain = paragraph_plain_text(child)
            if not plain:
                continue
            units.append(
                {
                    "xml_id": (child.get("id") or "").strip(),
                    "plain": plain,
                    "element": child,
                }
            )
            continue
        if tag == "note":
            plain = paragraph_plain_text(child)
            if not plain:
                continue
            units.append(
                {
                    "xml_id": (child.get("id") or "").strip(),
                    "plain": plain,
                    "element": child,
                }
            )
    return units


def _section_number(title: str, units: list[dict[str, Any]]) -> int:
    match = _SECTION_NUMBER_RE.match(title)
    if match:
        return int(match.group(1))
    if units:
        marked = _SECTION_MARK_RE.match(units[0]["plain"])
        if marked:
            return int(marked.group(1))
    raise HodgeThmlImportError(
        f"Hodge div3 is missing a numbered section heading: {title!r}."
    )


def _subsection_heading(number: int, _title: str) -> str:
    return f"\u00a7{number}"


def _leading_locator_id(group: list[dict[str, Any]], div3_id: str) -> str:
    for unit in group:
        xml_id = str(unit.get("xml_id") or "").strip()
        if xml_id:
            return xml_id
    return div3_id


def _chunk_id(section_id: str, sequence: int, *, split: bool) -> str:
    if not split and sequence == 1:
        return f"{section_id}.chunk"
    return f"{section_id}.chunk.{sequence}"


def _resolve_volume_policy(
    head: ET.Element | None,
    volume: int | None,
) -> HodgeVolumePolicy:
    book_id = electronic_book_id(head)
    inferred = BOOK_ID_TO_VOLUME.get(book_id) if book_id else None
    if volume is None:
        if inferred is None:
            raise HodgeThmlImportError(
                "Cannot determine Hodge volume from bookID; pass volume=1, 2, or 3."
            )
        volume = inferred
    if volume not in VOLUME_POLICIES:
        raise HodgeThmlImportError(f"Unsupported Hodge volume: {volume!r}.")
    policy = VOLUME_POLICIES[volume]
    if book_id is not None and book_id != policy.book_id:
        raise HodgeThmlImportError(
            f"Volume {policy.roman} importer expected bookID {policy.book_id!r}, "
            f"got {book_id!r}."
        )
    return policy


def _assert_expected_div1_titles(
    part_divs: list[ET.Element],
    policy: HodgeVolumePolicy,
) -> None:
    for div, spec in zip(part_divs, policy.div1s):
        title = (div.get("title") or "").strip()
        if not title.casefold().startswith(spec.expected_title_prefix.casefold()):
            raise HodgeThmlImportError(
                f"Volume {policy.roman} div1 id={spec.xml_id!r} expected title "
                f"starting with {spec.expected_title_prefix!r}, got {title!r}."
            )


def _author_record(head: ET.Element | None) -> dict[str, Any]:
    name = dc_text(head, "DC.Creator", sub="Author", scheme="short-form") or "Charles Hodge"
    return {
        "author_id": AUTHOR_ID,
        "canonical_name": name,
        "tradition": "reformed",
        "birth_year": 1797,
        "death_year": 1878,
    }


def _work_record() -> dict[str, Any]:
    return {
        "work_id": WORK_ID,
        "author_id": AUTHOR_ID,
        "title": "Systematic Theology",
        "original_title": "Systematic Theology",
        "tradition": "reformed",
        "original_language": "en",
    }


def _edition_record(head: ET.Element | None, policy: HodgeVolumePolicy) -> dict[str, Any]:
    language = dc_text(head, "DC.Language") or "en"
    if language.lower() in {"eng", "en"}:
        language = "en"
    return {
        "edition_id": policy.edition_id,
        "work_id": WORK_ID,
        "edition_label": policy.edition_label,
        "translator": None,
        "publication_year": PUBLICATION_YEAR,
        "publisher": dc_text(head, "DC.Publisher"),
        "language": language,
        "license": LICENSE_PLACEHOLDER,
        "rights_status": RIGHTS_STATUS,
        "rights_note": RIGHTS_NOTE,
        "source_url": policy.source_url,
        "corpus": "ccel",
        "external_id": electronic_id(head) or policy.external_id,
    }


def _require_xml_id(element: ET.Element, *, kind: str) -> str:
    xml_id = (element.get("id") or "").strip()
    if not xml_id:
        raise HodgeThmlImportError(f"Hodge {kind} is missing a stable CCEL id.")
    return xml_id


def _stable_id(xml_id: str, policy: HodgeVolumePolicy) -> str:
    cleaned = xml_id.strip()
    if not cleaned:
        raise HodgeThmlImportError("Missing stable CCEL id.")
    return f"{policy.section_id_prefix}.{cleaned}"


def _attr_or_none(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _reject_production_database(path: Path) -> None:
    try:
        resolved = path.resolve()
        production = DEFAULT_DATABASE_PATH.resolve()
    except OSError:
        resolved = path
        production = DEFAULT_DATABASE_PATH
    if resolved == production:
        raise HodgeThmlImportError(
            "Refusing to write the production theology.sqlite3 path."
        )


def _combine_report(
    theology: TheologyImportReport,
    extras: dict[str, Any],
) -> HodgeThmlImportReport:
    stats: ScriptureRefStats = extras["scripture"]
    return HodgeThmlImportReport(
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
        volume=int(extras["volume"]),
        parts=int(extras["parts"]),
        chapters=int(extras["chapters"]),
        sections=int(extras["sections"]),
        split_sections=int(extras["split_sections"]),
        split_chunks=int(extras["split_chunks"]),
        skipped_top_level_ids=tuple(extras["skipped_top_level_ids"]),
        scripture_refs_seen=stats.seen,
        passage_links_imported=stats.imported,
        skipped_chapter_only=stats.skipped_chapter_only,
        skipped_noncanonical=stats.skipped_noncanonical,
        skipped_no_osis=stats.skipped_no_osis,
        skipped_unparseable=stats.skipped_unparseable,
        skipped_malformed=stats.skipped_malformed,
        duplicate_links=stats.duplicate_links,
        warnings=tuple(extras.get("warnings") or ()),
    )
