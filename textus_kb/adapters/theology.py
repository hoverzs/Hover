"""Map TheologyChunkResult records to citation-ready EvidenceItem objects.

Mapping only: no SQL, no search, no network, no LLM.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from textus_kb.evidence import (
    RELATION_THEOLOGICAL_SOURCE,
    RELEVANCE_THEOLOGICAL_SOURCE,
    EvidenceItem,
)
from textus_kb.repositories.theology_repository import TheologyChunkResult

THEOLOGY_SOURCE_ID = "theology_sqlite"
THEOLOGY_SOURCE_TYPE = "sqlite"


class TheologyAdapter:
    """Pure mapper from repository hits to EvidenceItem records."""

    SOURCE_ID = THEOLOGY_SOURCE_ID

    def to_evidence_item(self, chunk: TheologyChunkResult) -> EvidenceItem:
        return theology_chunk_to_evidence(chunk)

    def to_evidence_items(
        self,
        chunks: Sequence[TheologyChunkResult],
    ) -> list[EvidenceItem]:
        return [self.to_evidence_item(chunk) for chunk in chunks]


def theology_chunk_to_evidence(chunk: TheologyChunkResult) -> EvidenceItem:
    passages = tuple(chunk.canonical_passages)
    metadata = _evidence_metadata(chunk, passages)
    passage = passages[0] if passages else None
    return EvidenceItem(
        evidence_id=_evidence_id(chunk.chunk_id),
        source_id=THEOLOGY_SOURCE_ID,
        source_type=THEOLOGY_SOURCE_TYPE,
        language=str(chunk.language or ""),
        relation_type=RELATION_THEOLOGICAL_SOURCE,
        passage=passage,
        content=chunk.plain_text,
        metadata=metadata,
        relevance_score=RELEVANCE_THEOLOGICAL_SOURCE,
    )


def _evidence_id(chunk_id: str) -> str:
    token = str(chunk_id or "").strip().replace(" ", "-")
    return f"EV-THEO-{token}" if token else "EV-THEO-UNKNOWN"


def _evidence_metadata(
    chunk: TheologyChunkResult,
    passages: tuple[str, ...],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "canonical_passages": list(passages),
    }
    optional: dict[str, Any] = {
        "author_name": chunk.author_name,
        "work_title": chunk.work_title,
        "human_readable_locator": chunk.human_readable_locator,
        "source_locator": chunk.source_locator,
        "heading": chunk.human_readable_locator or chunk.heading,
        "section_type": chunk.section_type,
        "translator": chunk.translator,
        "publication_year": chunk.publication_year,
        "language": chunk.language,
        "tradition": chunk.tradition,
        "rights_status": chunk.rights_status,
        "license": chunk.license,
        "rights_note": chunk.rights_note,
        "source_url": chunk.source_url,
        "corpus": chunk.corpus,
        "external_id": chunk.external_id,
        "canonical_scope": "; ".join(passages),
    }
    for key, value in optional.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        metadata[key] = value
    return metadata
