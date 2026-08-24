"""In-process KB cache for grounded preparation (Phase 5F).

Caches Evidence Packet and Context Packet only — never provider outputs.
Cache layer errors fall through to normal retrieval; retrieve/build errors
propagate unchanged. Default enabled for prep path when called.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.context_builder import SCHEMA_VERSION as CONTEXT_SCHEMA_VERSION
from textus_kb.evidence import PILOT_BUILD_ID_PHASE4E
from textus_kb.prompt_composer import COMPOSITION_VERSION

RETRIEVAL_CACHE_VERSION = "1"
CONTEXT_CACHE_VERSION = "1"

_T = TypeVar("_T")
_lock = threading.RLock()
_evidence_cache: dict[str, Any] = {}
_context_cache: dict[str, Any] = {}
_stats = {"evidence_hits": 0, "evidence_misses": 0, "context_hits": 0, "context_misses": 0}


def clear_kb_cache() -> None:
    with _lock:
        _evidence_cache.clear()
        _context_cache.clear()
        for key in _stats:
            _stats[key] = 0


def cache_stats() -> dict[str, int]:
    with _lock:
        return dict(_stats)


def _canonical(passage: str) -> str:
    try:
        return CanonicalReference.parse(passage).canonical_string()
    except CanonicalReferenceError:
        return str(passage or "").strip()


def evidence_cache_key(
    passage: str,
    *,
    kb_build_id: str = PILOT_BUILD_ID_PHASE4E,
    retrieval_version: str = RETRIEVAL_CACHE_VERSION,
) -> str:
    return "|".join(
        [
            "evidence",
            _canonical(passage),
            kb_build_id,
            retrieval_version,
        ]
    )


def context_cache_key(
    passage: str,
    profile: str,
    *,
    kb_build_id: str = PILOT_BUILD_ID_PHASE4E,
    context_schema_version: str = CONTEXT_SCHEMA_VERSION,
    selection_version: str = CONTEXT_CACHE_VERSION,
) -> str:
    return "|".join(
        [
            "context",
            _canonical(passage),
            profile,
            kb_build_id,
            context_schema_version,
            selection_version,
        ]
    )


def get_cached_evidence(key: str) -> Any | None:
    with _lock:
        if key in _evidence_cache:
            _stats["evidence_hits"] += 1
            return _evidence_cache[key]
        _stats["evidence_misses"] += 1
        return None


def set_cached_evidence(key: str, value: Any) -> None:
    with _lock:
        _evidence_cache[key] = value


def get_cached_context(key: str) -> Any | None:
    with _lock:
        if key in _context_cache:
            _stats["context_hits"] += 1
            return _context_cache[key]
        _stats["context_misses"] += 1
        return None


def set_cached_context(key: str, value: Any) -> None:
    with _lock:
        _context_cache[key] = value


def cached_retrieve(
    passage: str,
    retrieve_fn: Callable[[str], _T],
    *,
    kb_build_id: str = PILOT_BUILD_ID_PHASE4E,
    use_cache: bool = True,
) -> tuple[_T, bool]:
    """Return (packet, cache_hit). Retrieve errors propagate; cache I/O errors are ignored."""
    if not use_cache:
        return retrieve_fn(passage), False

    key = evidence_cache_key(passage, kb_build_id=kb_build_id)
    try:
        hit = get_cached_evidence(key)
    except Exception:
        hit = None
    if hit is not None:
        return hit, True

    value = retrieve_fn(passage)
    try:
        build_id = getattr(value, "build_id", None) or kb_build_id
        key = evidence_cache_key(passage, kb_build_id=str(build_id))
        set_cached_evidence(key, value)
    except Exception:
        pass
    return value, False


def cached_build_context(
    passage: str,
    profile: str,
    evidence: Any,
    build_fn: Callable[..., _T],
    *,
    use_cache: bool = True,
) -> tuple[_T, bool]:
    if not use_cache:
        return build_fn(evidence, profile), False

    build_id = str(getattr(evidence, "build_id", "") or PILOT_BUILD_ID_PHASE4E)
    key = context_cache_key(passage, profile, kb_build_id=build_id)
    try:
        hit = get_cached_context(key)
    except Exception:
        hit = None
    if hit is not None:
        return hit, True

    value = build_fn(evidence, profile)
    try:
        set_cached_context(key, value)
    except Exception:
        pass
    return value, False


def composition_cache_note() -> str:
    return (
        f"Composed prompts are not cached in Phase 5F "
        f"(composition_version={COMPOSITION_VERSION}); "
        "production prompt hash would be required and provider output is never cached."
    )


__all__ = [
    "CONTEXT_CACHE_VERSION",
    "RETRIEVAL_CACHE_VERSION",
    "cache_stats",
    "cached_build_context",
    "cached_retrieve",
    "clear_kb_cache",
    "composition_cache_note",
    "context_cache_key",
    "evidence_cache_key",
    "get_cached_context",
    "get_cached_evidence",
    "set_cached_context",
    "set_cached_evidence",
]
