"""Isolated Calvin + JFB + Henry combined Commentary store builder.

Source-level merge into one schema-v2 document, then a single SQLite
write — proves the Commentary Knowledge Base is genuinely multi-source,
source-independent architecture (mirrors ``combined_theology.py``'s
Calvin+Hodge precedent for the Theology store). Refuses the production
commentary.sqlite3 path. No network, no schema change: this module is
pure orchestration over the three existing per-source importers and the
shared, generic ``commentary_sqlite.merge_commentary_documents`` — each
source is entirely optional, so this same function combines any subset
(two sources, as proven in the JFB round, or all three).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from textus_kb.importers.calvin_commentary_thml import build_calvin_commentary_document
from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    CommentaryImportError,
    import_commentary_sqlite,
    merge_commentary_documents,
)
from textus_kb.importers.henry_commentary_thml import attach_henry_provenance, parse_henry_commentary_thml
from textus_kb.importers.jfb_commentary_thml import attach_jfb_provenance, parse_jfb_commentary_thml

IMPORT_MODE_COMBINED_COMMENTARY = "combined_commentary_thml"
# Retained for exact backward compatibility with the prior (Calvin+JFB
# only) round's import_mode value.
IMPORT_MODE_COMBINED_CALVIN_JFB = "combined_calvin_jfb_commentary_thml"


class CombinedCommentaryImportError(CommentaryImportError):
    """Raised when the combined commentary store cannot be built."""


@dataclass
class CombinedCommentaryImportReport:
    database_path: Path
    schema_version: str
    import_mode: str
    content_hash: str
    generated_at: str
    contributor_count: int
    work_count: int
    edition_count: int
    section_count: int
    chunk_count: int
    passage_link_count: int
    calvin_work_count: int = 0
    calvin_section_count: int = 0
    calvin_chunk_count: int = 0
    calvin_passage_link_count: int = 0
    jfb_work_count: int = 0
    jfb_section_count: int = 0
    jfb_chunk_count: int = 0
    jfb_passage_link_count: int = 0
    henry_work_count: int = 0
    henry_section_count: int = 0
    henry_chunk_count: int = 0
    henry_passage_link_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        return payload


def build_combined_commentary_document(
    *,
    calvin_entries: list[Any] | None = None,
    jfb_xml_path: str | Path | None = None,
    jfb_book_entries: list[Any] | None = None,
    henry_manifest: Any | None = None,
    imported_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse whichever of the three Commentary sources are provided (each
    entirely optional) and merge them with the shared, generic merge
    function — proving no source-specific merge logic is needed to
    combine any subset of independently-built Commentary sources into
    one document."""
    from datetime import UTC, datetime

    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    calvin_docs: list[dict[str, Any]] = []
    for entry in calvin_entries or []:
        known_unmapped = {
            item.div2_id: item for item in getattr(entry, "known_unmapped_sections", ())
        }
        document, _report = build_calvin_commentary_document(
            entry.local_path,
            imported_at=when,
            work_group=(entry.work_group or None),
            work_title=(entry.work_title or None),
            translator_override=(entry.translator or None),
            known_unmapped_sections=known_unmapped,
        )
        calvin_docs.append(document)

    jfb_docs: list[dict[str, Any]] = []
    if jfb_xml_path is not None and jfb_book_entries:
        jfb_parsed = parse_jfb_commentary_thml(jfb_xml_path, jfb_book_entries)
        jfb_docs, _jfb_reports = attach_jfb_provenance(
            jfb_parsed, jfb_book_entries, xml_path=jfb_xml_path, imported_at=when
        )

    henry_docs: list[dict[str, Any]] = []
    if henry_manifest is not None:
        for volume in henry_manifest.volumes:
            volume_books = [b for b in henry_manifest.books if b.volume == volume.volume]
            if not volume_books:
                continue
            parsed = parse_henry_commentary_thml(volume.local_path, volume_books)
            documents, _reports = attach_henry_provenance(
                parsed, volume_books, volume=volume, imported_at=when
            )
            henry_docs.extend(documents)

    merged = merge_commentary_documents(
        [*calvin_docs, *jfb_docs, *henry_docs], error_cls=CombinedCommentaryImportError
    )
    extras = {
        "calvin_work_count": len({d["works"][0]["work_id"] for d in calvin_docs}),
        "calvin_section_count": sum(len(d["sections"]) for d in calvin_docs),
        "calvin_chunk_count": sum(len(d["chunks"]) for d in calvin_docs),
        "calvin_passage_link_count": sum(_link_count(d) for d in calvin_docs),
        "jfb_work_count": len(jfb_docs),
        "jfb_section_count": sum(len(d["sections"]) for d in jfb_docs),
        "jfb_chunk_count": sum(len(d["chunks"]) for d in jfb_docs),
        "jfb_passage_link_count": sum(_link_count(d) for d in jfb_docs),
        "henry_work_count": len(henry_docs),
        "henry_section_count": sum(len(d["sections"]) for d in henry_docs),
        "henry_chunk_count": sum(len(d["chunks"]) for d in henry_docs),
        "henry_passage_link_count": sum(_link_count(d) for d in henry_docs),
    }
    return merged, extras


def import_combined_commentary_corpus(
    *,
    calvin_entries: list[Any] | None = None,
    jfb_xml_path: str | Path | None = None,
    jfb_book_entries: list[Any] | None = None,
    henry_manifest: Any | None = None,
    database_path: str | Path,
    atomic: bool = True,
    imported_at: str | None = None,
    import_mode: str = IMPORT_MODE_COMBINED_COMMENTARY,
) -> CombinedCommentaryImportReport:
    """Build an isolated combined store from any subset of the three
    Commentary sources. ``database_path`` is required."""
    target = Path(database_path)
    _reject_production_database(target)
    document, extras = build_combined_commentary_document(
        calvin_entries=calvin_entries,
        jfb_xml_path=jfb_xml_path,
        jfb_book_entries=jfb_book_entries,
        henry_manifest=henry_manifest,
        imported_at=imported_at,
    )
    result = import_commentary_sqlite(
        document=document,
        database_path=target,
        import_mode=import_mode,
        atomic=atomic,
    )
    return CombinedCommentaryImportReport(
        database_path=result.database_path,
        schema_version=result.schema_version,
        import_mode=result.import_mode,
        content_hash=result.content_hash,
        generated_at=result.generated_at,
        contributor_count=result.contributor_count,
        work_count=result.work_count,
        edition_count=result.edition_count,
        section_count=result.section_count,
        chunk_count=result.chunk_count,
        passage_link_count=result.passage_link_count,
        calvin_work_count=int(extras["calvin_work_count"]),
        calvin_section_count=int(extras["calvin_section_count"]),
        calvin_chunk_count=int(extras["calvin_chunk_count"]),
        calvin_passage_link_count=int(extras["calvin_passage_link_count"]),
        jfb_work_count=int(extras["jfb_work_count"]),
        jfb_section_count=int(extras["jfb_section_count"]),
        jfb_chunk_count=int(extras["jfb_chunk_count"]),
        jfb_passage_link_count=int(extras["jfb_passage_link_count"]),
        henry_work_count=int(extras["henry_work_count"]),
        henry_section_count=int(extras["henry_section_count"]),
        henry_chunk_count=int(extras["henry_chunk_count"]),
        henry_passage_link_count=int(extras["henry_passage_link_count"]),
    )


def build_combined_calvin_jfb_document(
    *,
    calvin_entries: list[Any],
    jfb_xml_path: str | Path,
    jfb_book_entries: list[Any],
    imported_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Backward-compatible two-source (Calvin+JFB) wrapper around
    ``build_combined_commentary_document``."""
    return build_combined_commentary_document(
        calvin_entries=calvin_entries,
        jfb_xml_path=jfb_xml_path,
        jfb_book_entries=jfb_book_entries,
        imported_at=imported_at,
    )


def import_combined_calvin_jfb_commentary(
    *,
    calvin_entries: list[Any],
    jfb_xml_path: str | Path,
    jfb_book_entries: list[Any],
    database_path: str | Path,
    atomic: bool = True,
    imported_at: str | None = None,
) -> CombinedCommentaryImportReport:
    """Backward-compatible two-source (Calvin+JFB) wrapper around
    ``import_combined_commentary_corpus``, preserving the prior round's
    own ``import_mode`` value."""
    return import_combined_commentary_corpus(
        calvin_entries=calvin_entries,
        jfb_xml_path=jfb_xml_path,
        jfb_book_entries=jfb_book_entries,
        database_path=database_path,
        atomic=atomic,
        imported_at=imported_at,
        import_mode=IMPORT_MODE_COMBINED_CALVIN_JFB,
    )


def _link_count(document: dict[str, Any]) -> int:
    return sum(len(section.get("passage_links") or []) for section in document.get("sections") or [])


def _reject_production_database(path: Path) -> None:
    try:
        resolved = path.resolve()
        production = DEFAULT_DATABASE_PATH.resolve()
    except OSError:
        resolved = path
        production = DEFAULT_DATABASE_PATH
    if resolved == production:
        raise CombinedCommentaryImportError(
            "Refusing to write the production commentary.sqlite3 path."
        )


__all__ = [
    "IMPORT_MODE_COMBINED_CALVIN_JFB",
    "IMPORT_MODE_COMBINED_COMMENTARY",
    "CombinedCommentaryImportError",
    "CombinedCommentaryImportReport",
    "build_combined_calvin_jfb_document",
    "build_combined_commentary_document",
    "import_combined_calvin_jfb_commentary",
    "import_combined_commentary_corpus",
]
