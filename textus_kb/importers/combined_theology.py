"""Isolated Calvin + Hodge combined theology store builder.

Source-level merge into one schema-v1 document, then a single SQLite write.
Refuses the production theology.sqlite3 path. No network, no schema change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from textus_kb.importers.ccel_thml import parse_ccel_institutes_thml
from textus_kb.importers.hodge_thml import parse_hodge_systematic_theology_thml
from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    TheologyImportError,
    TheologyImportReport,
    hash_theology_document,
    import_theology_sqlite,
    normalize_theology_document,
)

IMPORT_MODE_COMBINED_CALVIN_HODGE = "combined_calvin_hodge_thml"

_ID_FIELDS = {
    "authors": "author_id",
    "works": "work_id",
    "editions": "edition_id",
    "sections": "section_id",
    "chunks": "chunk_id",
}
_IDENTICAL_OK = frozenset({"authors", "works"})


class CombinedTheologyImportError(TheologyImportError):
    """Raised when the combined Calvin+Hodge store cannot be built."""


@dataclass
class CombinedTheologyImportReport:
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
    calvin_section_count: int = 0
    calvin_chunk_count: int = 0
    calvin_passage_link_count: int = 0
    hodge_section_count: int = 0
    hodge_chunk_count: int = 0
    hodge_passage_link_count: int = 0
    hodge_volume_chunk_counts: tuple[int, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        payload["hodge_volume_chunk_counts"] = list(self.hodge_volume_chunk_counts)
        payload["warnings"] = list(self.warnings)
        return payload


def import_combined_calvin_hodge_thml(
    *,
    calvin_xml_path: str | Path,
    hodge_volume1_xml_path: str | Path,
    hodge_volume2_xml_path: str | Path,
    hodge_volume3_xml_path: str | Path,
    database_path: str | Path,
    atomic: bool = True,
) -> CombinedTheologyImportReport:
    """Build an isolated combined store. ``database_path`` is required."""
    target = Path(database_path)
    _reject_production_database(target)
    document, extras = build_combined_calvin_hodge_document(
        calvin_xml_path=calvin_xml_path,
        hodge_volume1_xml_path=hodge_volume1_xml_path,
        hodge_volume2_xml_path=hodge_volume2_xml_path,
        hodge_volume3_xml_path=hodge_volume3_xml_path,
    )
    theology = import_theology_sqlite(
        document=document,
        database_path=target,
        import_mode=IMPORT_MODE_COMBINED_CALVIN_HODGE,
        atomic=atomic,
    )
    return _combine_report(theology, extras)


def build_combined_calvin_hodge_document(
    *,
    calvin_xml_path: str | Path,
    hodge_volume1_xml_path: str | Path,
    hodge_volume2_xml_path: str | Path,
    hodge_volume3_xml_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    calvin_doc, _calvin_extras = parse_ccel_institutes_thml(calvin_xml_path)
    hodge_docs: list[dict[str, Any]] = []
    hodge_volume_chunk_counts: list[int] = []
    for volume, xml_path in (
        (1, hodge_volume1_xml_path),
        (2, hodge_volume2_xml_path),
        (3, hodge_volume3_xml_path),
    ):
        document, _extras = parse_hodge_systematic_theology_thml(xml_path, volume=volume)
        hodge_docs.append(document)
        hodge_volume_chunk_counts.append(len(document["chunks"]))

    merged = merge_theology_documents([calvin_doc, *hodge_docs])
    extras = {
        "calvin_section_count": len(calvin_doc["sections"]),
        "calvin_chunk_count": len(calvin_doc["chunks"]),
        "calvin_passage_link_count": _link_count(calvin_doc),
        "hodge_section_count": sum(len(doc["sections"]) for doc in hodge_docs),
        "hodge_chunk_count": sum(len(doc["chunks"]) for doc in hodge_docs),
        "hodge_passage_link_count": sum(_link_count(doc) for doc in hodge_docs),
        "hodge_volume_chunk_counts": tuple(hodge_volume_chunk_counts),
        "warnings": (),
    }
    return merged, extras


def merge_theology_documents(documents: list[dict[str, Any]]) -> dict[str, Any]:
    if not documents:
        raise CombinedTheologyImportError("No theology documents to merge.")
    merged: dict[str, list[dict[str, Any]]] = {
        "authors": [],
        "works": [],
        "editions": [],
        "sections": [],
        "chunks": [],
    }
    index: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in _ID_FIELDS}
    for document in documents:
        if not isinstance(document, dict):
            raise CombinedTheologyImportError("Each theology document must be an object.")
        for kind, id_field in _ID_FIELDS.items():
            items = document.get(kind) or []
            if not isinstance(items, list):
                raise CombinedTheologyImportError(f"Document {kind} must be an array.")
            for item in items:
                if not isinstance(item, dict):
                    raise CombinedTheologyImportError(f"Document {kind} entries must be objects.")
                item_id = str(item.get(id_field) or "").strip()
                if not item_id:
                    raise CombinedTheologyImportError(f"Missing {id_field}.")
                existing = index[kind].get(item_id)
                if existing is None:
                    merged[kind].append(item)
                    index[kind][item_id] = item
                    continue
                if kind in _IDENTICAL_OK and existing == item:
                    continue
                raise CombinedTheologyImportError(
                    f"Duplicate {kind[:-1]} id across combined sources: {item_id!r}."
                )
    _assert_passage_link_identity(merged["chunks"])
    return merged


def _assert_passage_link_identity(chunks: list[dict[str, Any]]) -> None:
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        for link in chunk.get("passage_links") or []:
            if not isinstance(link, dict):
                continue
            passage = str(link.get("canonical_passage") or "").strip()
            if not passage:
                continue
            key = (chunk_id, passage)
            if key in seen:
                raise CombinedTheologyImportError(
                    f"Duplicate passage_link identity: {key!r}."
                )
            seen.add(key)


def _link_count(document: dict[str, Any]) -> int:
    return sum(len(chunk.get("passage_links") or []) for chunk in document.get("chunks") or [])


def _reject_production_database(path: Path) -> None:
    try:
        resolved = path.resolve()
        production = DEFAULT_DATABASE_PATH.resolve()
    except OSError:
        resolved = path
        production = DEFAULT_DATABASE_PATH
    if resolved == production:
        raise CombinedTheologyImportError(
            "Refusing to write the production theology.sqlite3 path."
        )


def _combine_report(
    theology: TheologyImportReport,
    extras: dict[str, Any],
) -> CombinedTheologyImportReport:
    return CombinedTheologyImportReport(
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
        calvin_section_count=int(extras["calvin_section_count"]),
        calvin_chunk_count=int(extras["calvin_chunk_count"]),
        calvin_passage_link_count=int(extras["calvin_passage_link_count"]),
        hodge_section_count=int(extras["hodge_section_count"]),
        hodge_chunk_count=int(extras["hodge_chunk_count"]),
        hodge_passage_link_count=int(extras["hodge_passage_link_count"]),
        hodge_volume_chunk_counts=tuple(extras["hodge_volume_chunk_counts"]),
        warnings=tuple(extras.get("warnings") or ()),
    )


def combined_document_hash(
    *,
    calvin_xml_path: str | Path,
    hodge_volume1_xml_path: str | Path,
    hodge_volume2_xml_path: str | Path,
    hodge_volume3_xml_path: str | Path,
) -> str:
    document, _extras = build_combined_calvin_hodge_document(
        calvin_xml_path=calvin_xml_path,
        hodge_volume1_xml_path=hodge_volume1_xml_path,
        hodge_volume2_xml_path=hodge_volume2_xml_path,
        hodge_volume3_xml_path=hodge_volume3_xml_path,
    )
    return hash_theology_document(normalize_theology_document(document))
