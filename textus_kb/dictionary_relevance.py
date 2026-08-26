"""Passage-scoped dictionary relevance helpers (Phase 5H-B).

Dictionary evidence is eligible only when a clear relevance link exists:
  A) headword/title matches a passage entity or keyterm, or
  B) explicit canonical association overlaps the request passage
     *and* A also holds (overlap alone is not enough), or
  C) strong entity↔dictionary name match for entity-expansion candidates.

Loose ACAI scored links, same-book/chapter proximity, and request-scope
stamping without source overlap are rejected.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.pilot_registry import org_ref_bounds, org_ref_to_canonical

_PAREN_RE = re.compile(r"\([^)]*\)")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")
_WS_RE = re.compile(r"\s+")

# Scored entity↔dictionary links below this are never treated as strong (C).
MIN_SCORED_MATCH_CONFIDENCE = 0.85


def normalize_dictionary_label(value: str | None) -> str:
    text = str(value or "").lower().strip()
    if not text:
        return ""
    text = _PAREN_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def labels_match(
    left: str | None,
    right: str | None,
    *,
    allow_suffix: bool = True,
) -> bool:
    a = normalize_dictionary_label(left)
    b = normalize_dictionary_label(right)
    if not a or not b:
        return False
    if a == b:
        return True
    a_stem = a.rstrip("s")
    b_stem = b.rstrip("s")
    if a_stem and b_stem and a_stem == b_stem and min(len(a_stem), len(b_stem)) >= 3:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < 4:
        return False
    padded = f" {longer} "
    needle = f" {shorter} "
    # Allow phrase at start (and optionally end) only — avoid mid-title alias noise.
    if padded.startswith(needle):
        return True
    return bool(allow_suffix and padded.endswith(needle))


def passage_term_labels(entities: Iterable[Any]) -> set[str]:
    labels: set[str] = set()
    for entity in entities:
        if isinstance(entity, dict):
            name = entity.get("canonical_name") or entity.get("name")
        else:
            name = getattr(entity, "canonical_name", None)
        if name:
            labels.add(str(name))
            normalized = normalize_dictionary_label(str(name))
            if normalized:
                labels.add(normalized)
    return labels


def article_matches_passage_terms(
    *,
    title: str | None,
    index_reference: str | None,
    passage_terms: Iterable[str],
) -> bool:
    terms = [str(term) for term in passage_terms if str(term or "").strip()]
    if not terms:
        return False
    primary = ""
    if title:
        primary = str(title).split(",", 1)[0].strip()
    for term in terms:
        if primary and labels_match(primary, term, allow_suffix=True):
            return True
        if index_reference and labels_match(
            index_reference, term, allow_suffix=False
        ):
            return True
    return False

def associations_overlapping_request(
    associations: Iterable[dict[str, Any]] | None,
    reference: CanonicalReference,
) -> list[dict[str, str]]:
    org_lo, org_hi = org_ref_bounds(reference)
    book = org_lo[:2]
    overlapping: list[dict[str, str]] = []
    for raw in associations or ():
        if not isinstance(raw, dict):
            continue
        start_ref = str(raw.get("start_ref") or "")
        end_ref = str(raw.get("end_ref") or start_ref)
        if len(start_ref) != 8 or len(end_ref) != 8:
            continue
        if not start_ref.isdigit() or not end_ref.isdigit():
            continue
        if start_ref[:2] != book or end_ref[:2] != book:
            continue
        if start_ref <= org_hi and end_ref >= org_lo:
            overlapping.append(
                {
                    "start_ref": start_ref,
                    "end_ref": end_ref,
                    "start_ref_usfm": str(raw.get("start_ref_usfm") or ""),
                    "end_ref_usfm": str(raw.get("end_ref_usfm") or ""),
                }
            )
    return overlapping


def format_source_scope(associations: Iterable[dict[str, Any]] | None) -> str | None:
    """Compact canonical scope from association org-refs (not the request passage)."""
    spans: list[str] = []
    seen: set[str] = set()
    for raw in associations or ():
        if not isinstance(raw, dict):
            continue
        start_ref = str(raw.get("start_ref") or "")
        end_ref = str(raw.get("end_ref") or start_ref)
        start_canon = org_ref_to_canonical(start_ref)
        end_canon = org_ref_to_canonical(end_ref)
        if not start_canon:
            continue
        if end_canon and end_canon != start_canon:
            # Same chapter range → Book.C.V-V; else Book.C.V–Book.C.V
            start_parts = start_canon.split(".")
            end_parts = end_canon.split(".")
            if (
                len(start_parts) == 3
                and len(end_parts) == 3
                and start_parts[0] == end_parts[0]
                and start_parts[1] == end_parts[1]
            ):
                label = f"{start_parts[0]}.{start_parts[1]}.{start_parts[2]}-{end_parts[2]}"
            else:
                label = f"{start_canon}-{end_canon}"
        else:
            label = start_canon
        if label not in seen:
            seen.add(label)
            spans.append(label)
        if len(spans) >= 3:
            break
    if not spans:
        return None
    if len(spans) == 1:
        return spans[0]
    return "; ".join(spans)


def strong_entity_dictionary_match(
    *,
    entity_name: str | None,
    title: str | None,
    index_reference: str | None,
    match_method: str | None = None,
    match_confidence: float | None = None,
) -> bool:
    """Criterion C: documented name alignment between passage entity and dictionary headword."""
    if not article_matches_passage_terms(
        title=title,
        index_reference=index_reference,
        passage_terms=[str(entity_name or "")],
    ):
        return False
    method = str(match_method or "").strip().lower()
    if method in {"", "content_id", "exact", "verified_exact_match", "external_id", "explicit"}:
        return True
    if method == "scored":
        try:
            confidence = float(match_confidence) if match_confidence is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        return confidence >= MIN_SCORED_MATCH_CONFIDENCE
    # Unknown methods require an exact-normalized name match already satisfied above,
    # but reject low-trust scored-like aliases.
    return method not in {"fuzzy", "embedding", "heuristic"}


def is_direct_dictionary_relevant(
    *,
    reference: CanonicalReference,
    title: str | None,
    index_reference: str | None,
    passage_associations: Iterable[dict[str, Any]] | None,
    passage_terms: Iterable[str],
) -> bool:
    """Direct passage retrieval: require overlapping association (B) and term match (A)."""
    overlapping = associations_overlapping_request(passage_associations, reference)
    if not overlapping:
        return False
    return article_matches_passage_terms(
        title=title,
        index_reference=index_reference,
        passage_terms=passage_terms,
    )


def is_expanded_dictionary_relevant(
    *,
    reference: CanonicalReference,
    title: str | None,
    index_reference: str | None,
    passage_associations: Iterable[dict[str, Any]] | None,
    entity_name: str | None,
    match_method: str | None = None,
    match_confidence: float | None = None,
    passage_terms: Iterable[str] | None = None,
) -> bool:
    """Entity expansion: require strong name match (C), or B+A with the driving entity in terms."""
    if strong_entity_dictionary_match(
        entity_name=entity_name,
        title=title,
        index_reference=index_reference,
        match_method=match_method,
        match_confidence=match_confidence,
    ):
        return True
    overlapping = associations_overlapping_request(passage_associations, reference)
    if not overlapping:
        return False
    terms = list(passage_terms or [])
    if entity_name:
        terms.append(str(entity_name))
    return article_matches_passage_terms(
        title=title,
        index_reference=index_reference,
        passage_terms=terms,
    )


def dictionary_relevance_score(
    *,
    reference: CanonicalReference,
    title: str | None,
    index_reference: str | None,
    passage_associations: Iterable[dict[str, Any]] | None,
    passage_terms: Iterable[str],
    entity_expansion: dict[str, Any] | None = None,
    selection_reason: str | None = None,
) -> int:
    """Rank dictionary evidence: exact term match > canonical overlap+term > strong expansion."""
    from textus_kb.evidence import (
        RELEVANCE_DICTIONARY_BACKGROUND,
        RELEVANCE_DICTIONARY_ENTITY,
        RELEVANCE_DICTIONARY_PASSAGE,
        RELEVANCE_DICTIONARY_TOPIC,
    )

    overlapping = associations_overlapping_request(passage_associations, reference)
    term_match = article_matches_passage_terms(
        title=title,
        index_reference=index_reference,
        passage_terms=passage_terms,
    )
    expansion = entity_expansion or {}
    strong = False
    if expansion:
        strong = strong_entity_dictionary_match(
            entity_name=expansion.get("canonical_name"),
            title=title,
            index_reference=index_reference,
            match_method=expansion.get("match_method"),
            match_confidence=expansion.get("match_confidence"),
        )

    if term_match and overlapping:
        return RELEVANCE_DICTIONARY_PASSAGE
    if strong:
        return RELEVANCE_DICTIONARY_PASSAGE - 4
    if term_match:
        return RELEVANCE_DICTIONARY_ENTITY
    if overlapping:
        return RELEVANCE_DICTIONARY_TOPIC
    reason = str(selection_reason or "")
    if reason in {"pilot_place_entity_match", "direct_acai_association"}:
        return RELEVANCE_DICTIONARY_ENTITY
    if reason in {"pilot_index_reference_match", "full_corpus_index"}:
        return RELEVANCE_DICTIONARY_TOPIC
    return RELEVANCE_DICTIONARY_BACKGROUND


def annotate_dictionary_scope_metadata(
    metadata: dict[str, Any],
    *,
    reference: CanonicalReference,
    request_scope: str,
) -> dict[str, Any]:
    """Attach request vs source scope without rewriting non-overlapping links as the request."""
    associations = metadata.get("passage_associations")
    overlapping = associations_overlapping_request(associations, reference)
    source_scope = format_source_scope(overlapping) if overlapping else None
    metadata["request_scope"] = request_scope
    metadata["source_scope"] = source_scope
    metadata["overlapping_passage_associations"] = overlapping
    metadata["passage_linked"] = bool(overlapping)
    return metadata
