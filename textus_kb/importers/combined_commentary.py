"""Isolated Calvin + JFB combined Commentary store builder.

Source-level merge into one schema-v2 document, then a single SQLite
write — proves the Commentary Knowledge Base is genuinely multi-source,
source-independent architecture (mirrors ``combined_theology.py``'s
Calvin+Hodge precedent for the Theology store). Refuses the production
commentary.sqlite3 path. No network, no schema change: this module is
pure orchestration over the two existing per-source importers and the
shared, generic ``commentary_sqlite.merge_commentary_documents``.
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
from textus_kb.importers.jfb_commentary_thml import attach_jfb_provenance, parse_jfb_commentary_thml

IMPORT_MODE_COMBINED_CALVIN_JFB = "combined_calvin_jfb_commentary_thml"


class CombinedCommentaryImportError(CommentaryImportError):
    """Raised when the combined Calvin+JFB commentary store cannot be built."""


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

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        return payload


def build_combined_calvin_jfb_document(
    *,
    calvin_entries: list[Any],
    jfb_xml_path: str | Path,
    jfb_book_entries: list[Any],
    imported_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse the full Calvin corpus (one document per source file, per
    ``calvin_entries``) and the full JFB corpus (one document per book,
    from a single parse of ``jfb_xml_path``), then merge them with the
    shared, generic merge function — proving no source-specific merge
    logic is needed to combine two independently-built Commentary
    sources into one document."""
    from datetime import UTC, datetime

    when = imported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    calvin_docs: list[dict[str, Any]] = []
    for entry in calvin_entries:
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

    jfb_parsed = parse_jfb_commentary_thml(jfb_xml_path, jfb_book_entries)
    jfb_docs, _jfb_reports = attach_jfb_provenance(
        jfb_parsed, jfb_book_entries, xml_path=jfb_xml_path, imported_at=when
    )

    merged = merge_commentary_documents(
        [*calvin_docs, *jfb_docs], error_cls=CombinedCommentaryImportError
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
    }
    return merged, extras


def import_combined_calvin_jfb_commentary(
    *,
    calvin_entries: list[Any],
    jfb_xml_path: str | Path,
    jfb_book_entries: list[Any],
    database_path: str | Path,
    atomic: bool = True,
    imported_at: str | None = None,
) -> CombinedCommentaryImportReport:
    """Build an isolated combined Calvin+JFB store. ``database_path`` is required."""
    target = Path(database_path)
    _reject_production_database(target)
    document, extras = build_combined_calvin_jfb_document(
        calvin_entries=calvin_entries,
        jfb_xml_path=jfb_xml_path,
        jfb_book_entries=jfb_book_entries,
        imported_at=imported_at,
    )
    result = import_commentary_sqlite(
        document=document,
        database_path=target,
        import_mode=IMPORT_MODE_COMBINED_CALVIN_JFB,
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
    "CombinedCommentaryImportError",
    "CombinedCommentaryImportReport",
    "build_combined_calvin_jfb_document",
    "import_combined_calvin_jfb_commentary",
]
