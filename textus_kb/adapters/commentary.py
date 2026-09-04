"""Map CommentaryRepository hits to citation-ready EvidenceItem objects.

Mapping only: no SQL, no search, no network, no LLM. A commentary section
is the canonical citable unit (never a bare chunk) — see
``textus_kb.repositories.commentary_repository``. When a section's own
prose is longer than ``COMMENTARY_EXCERPT_CHAR_LIMIT``, only as many of its
chunks as fit are included in ``EvidenceItem.content`` (a section currently
always has exactly one chunk in the Calvin corpus, so this degrades to a
single-chunk excerpt today, but the logic is chunk-count-agnostic for
future multi-chunk sections); the item's metadata still identifies the
full, un-truncated section so a citation always resolves back to the real
work/edition/section record, never to a synthetic fragment.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from textus_kb.evidence import (
    RELATION_COMMENTARY_SOURCE,
    RELEVANCE_COMMENTARY_SOURCE,
    EvidenceItem,
)
from textus_kb.repositories.commentary_repository import (
    CommentarySectionDetail,
    CommentarySectionResult,
)

COMMENTARY_SOURCE_ID = "commentary_sqlite"
COMMENTARY_SOURCE_TYPE = "sqlite"

# Per-item excerpt cap (characters). Bounds how much of one long Calvin
# section's prose enters a single EvidenceItem, so one oversized section
# cannot alone consume (or blow past) the whole Commentary context budget
# and get dropped entirely by the generic token-budget selector.
COMMENTARY_EXCERPT_CHAR_LIMIT = 2000


class CommentaryAdapter:
    """Pure mapper from repository hits to EvidenceItem records."""

    SOURCE_ID = COMMENTARY_SOURCE_ID

    def to_evidence_item(
        self,
        hit: CommentarySectionResult,
        detail: CommentarySectionDetail,
    ) -> EvidenceItem:
        return commentary_section_to_evidence(hit, detail)

    def to_evidence_items(
        self,
        pairs: Sequence[tuple[CommentarySectionResult, CommentarySectionDetail]],
    ) -> list[EvidenceItem]:
        return [self.to_evidence_item(hit, detail) for hit, detail in pairs]


def commentary_section_to_evidence(
    hit: CommentarySectionResult,
    detail: CommentarySectionDetail,
) -> EvidenceItem:
    content, excerpt_meta = _excerpt_content(detail)
    # ``hit`` (from sections_for_passage) is query-scoped: its
    # primary/parallel lists only ever contain links that actually overlap
    # this query. ``detail``'s lists are the section's full, unscoped set —
    # using those here would always report the section's overall primary
    # passage even when this specific query matched only a parallel one
    # (e.g. a Harmony section reached via its Luke parallel link would
    # wrongly report Matthew, its primary, as the matched passage).
    passage = (
        hit.primary_passages[0]
        if hit.primary_passages
        else hit.parallel_passages[0]
        if hit.parallel_passages
        else (hit.canonical_passages[0] if hit.canonical_passages else None)
    )
    metadata = _evidence_metadata(hit, detail, excerpt_meta)
    return EvidenceItem(
        evidence_id=_evidence_id(detail.section_id),
        source_id=COMMENTARY_SOURCE_ID,
        source_type=COMMENTARY_SOURCE_TYPE,
        language=str(hit.language or ""),
        relation_type=RELATION_COMMENTARY_SOURCE,
        passage=passage,
        content=content,
        metadata=metadata,
        relevance_score=RELEVANCE_COMMENTARY_SOURCE,
    )


def _excerpt_content(detail: CommentarySectionDetail) -> tuple[str, dict[str, Any]]:
    """Concatenate ``detail.chunks`` (sequence order) up to the excerpt
    cap. Whole chunks are preferred; only the chunk that would cross the
    cap is itself truncated (word boundary, trailing ellipsis) — never a
    later chunk left partially included while an earlier one is skipped.
    """
    chunk_ids = [chunk.chunk_id for chunk in detail.chunks]
    parts: list[str] = []
    included_chunk_ids: list[str] = []
    total_len = 0
    truncated = False
    for chunk in detail.chunks:
        text = chunk.plain_text or ""
        if not text:
            continue
        remaining = COMMENTARY_EXCERPT_CHAR_LIMIT - total_len
        if remaining <= 0:
            truncated = True
            break
        if len(text) <= remaining:
            parts.append(text)
            included_chunk_ids.append(chunk.chunk_id)
            total_len += len(text)
            continue
        # This chunk alone crosses the cap: include a truncated prefix
        # (word boundary where possible) and stop — never skip straight
        # to a later chunk once one has been partially included.
        excerpt = text[:remaining].rstrip()
        last_space = excerpt.rfind(" ")
        if last_space > 0:
            excerpt = excerpt[:last_space]
        parts.append(excerpt.rstrip() + "…")
        included_chunk_ids.append(chunk.chunk_id)
        truncated = True
        break

    content = "\n\n".join(parts)
    excerpt_meta = {
        "chunk_ids": chunk_ids,
        "chunk_count": len(chunk_ids),
        "included_chunk_ids": included_chunk_ids,
        "included_chunk_count": len(included_chunk_ids),
        "excerpt_truncated": truncated,
    }
    return content, excerpt_meta


def _evidence_id(section_id: str) -> str:
    token = str(section_id or "").strip().replace(" ", "-")
    return f"EV-COMM-{token}" if token else "EV-COMM-UNKNOWN"


def _evidence_metadata(
    hit: CommentarySectionResult,
    detail: CommentarySectionDetail,
    excerpt_meta: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "section_id": detail.section_id,
        "edition_id": detail.edition_id,
        "work_id": detail.work_id,
        "canonical_passages": list(detail.canonical_passages),
        "primary_passages": list(detail.primary_passages),
        "parallel_passages": list(detail.parallel_passages),
        # The query-relative match tier (exact/containing/partial overlap —
        # see RELATION_EXACT_PASSAGE etc.), distinct from EvidenceItem's own
        # RELATION_COMMENTARY_SOURCE relation_type and from the passage-link-
        # level primary/parallel split above.
        "query_relation_type": hit.relation_type,
        "canonical_scope": "; ".join(detail.canonical_passages),
        **excerpt_meta,
    }
    optional: dict[str, Any] = {
        "work_title": hit.work_title,
        "section_type": hit.section_type,
        "heading": hit.heading,
        "parent_section_id": hit.parent_section_id,
        "contributors": list(hit.contributors) if hit.contributors else None,
        "language": hit.language,
        "rights_status": hit.rights_status,
        "license": hit.license,
        "rights_note": hit.rights_note,
        "source_url": hit.source_url,
        "corpus": hit.corpus,
        "external_id": hit.external_id,
        "source_locator": detail.chunks[0].source_locator if detail.chunks else None,
        "human_readable_locator": _human_readable_locator(hit, detail),
    }
    for key, value in optional.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        metadata[key] = value
    return metadata


def _human_readable_locator(
    hit: CommentarySectionResult,
    detail: CommentarySectionDetail,
) -> str:
    author = next(
        (c for c in hit.contributors if "(author)" in c), hit.contributors[0] if hit.contributors else ""
    )
    parts = [author, hit.work_title]
    parts.extend(node[1] for node in detail.parent_chain if node[1])
    if hit.heading:
        parts.append(hit.heading)
    return ", ".join(part.strip() for part in parts if part and part.strip())


__all__ = [
    "COMMENTARY_EXCERPT_CHAR_LIMIT",
    "COMMENTARY_SOURCE_ID",
    "COMMENTARY_SOURCE_TYPE",
    "CommentaryAdapter",
    "commentary_section_to_evidence",
]
