"""Guarded KB-grounded production prompt injection (Phase 5D).

Default-on for mapped modules (exegesis, historical, theology). Explicit
``TEXTUS_KB_GROUNDED_ENABLED=false`` is an emergency kill switch. On success,
the Phase 5C composed prompt is sent to the provider exactly once. On any
preparation failure, the original production prompt is used for that same
single provider call (hard fallback — no double call).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from textus_kb.prompt_composer import (
    COMPOSITION_VERSION,
    compose_grounded_prompt,
    grounded_prompt_token_budget,
)
from textus_kb.shadow import MODULE_TO_PROFILE

GROUNDED_FLAG = "TEXTUS_KB_GROUNDED_ENABLED"
PASSAGE_ALLOWLIST_FLAG = "TEXTUS_KB_GROUNDED_PASSAGE_ALLOWLIST"
_GROUNDED_DISABLED_VALUES = frozenset({"false", "0", "no", "off"})

STATUS_USED = "grounded_used"
STATUS_FALLBACK = "grounded_fallback"
STATUS_DISABLED = "grounded_disabled"
STATUS_UNSUPPORTED = "grounded_unsupported_module"

REASON_RETRIEVAL_ERROR = "retrieval_error"
REASON_CONTEXT_ERROR = "context_error"
REASON_BUDGET_EXCEEDED = "budget_exceeded"
REASON_COMPOSITION_ERROR = "composition_error"
REASON_UNSUPPORTED_PASSAGE = "unsupported_passage"
REASON_SOURCE_UNAVAILABLE = "source_unavailable"
REASON_UNSUPPORTED_MODULE = "unsupported_module"
REASON_PASSAGE_NOT_ALLOWLISTED = "passage_not_allowlisted"


def is_grounded_enabled() -> bool:
    """Optional kill switch. Unset/empty/true → on; only explicit false disables."""
    raw = os.getenv(GROUNDED_FLAG)
    if raw is None:
        return True
    return raw.strip().lower() not in _GROUNDED_DISABLED_VALUES


def is_grounded_injection_allowed() -> bool:
    """Production injection follows the grounded kill-switch policy (default on)."""
    return is_grounded_enabled()


def passage_allowlist_canonicals() -> set[str] | None:
    """Return allowlist set, or None when unrestricted."""
    raw = (os.getenv(PASSAGE_ALLOWLIST_FLAG, "") or "").strip()
    if not raw:
        return None
    from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError

    allowed: set[str] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            allowed.add(CanonicalReference.parse(token).canonical_string())
        except CanonicalReferenceError:
            allowed.add(token)
    return allowed


def is_passage_allowlisted(passage: str) -> bool:
    allowed = passage_allowlist_canonicals()
    if allowed is None:
        return True
    from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError

    try:
        canonical = CanonicalReference.parse(passage).canonical_string()
    except CanonicalReferenceError:
        canonical = str(passage or "").strip()
    return canonical in allowed


def resolve_grounded_module(section_key: str) -> str | None:
    """Map production section key → KB module, or None if unsupported."""
    if section_key == "exegesis":
        return "exegesis"
    if section_key == "history":
        return "historical_context"
    if section_key == "theology":
        return "theology"
    if section_key == "commentary":
        return "commentary"
    return None


@dataclass
class GroundedPreparationResult:
    status: str
    provider_prompt: str
    production_prompt: str
    grounded_used: bool = False
    grounded_fallback: bool = False
    grounded_disabled: bool = False
    grounded_unsupported_module: bool = False
    fallback_reason: str = ""
    module: str = ""
    profile: str = ""
    passage_input: str = ""
    canonical_passage: str = ""
    composition_version: str = ""
    prompt_hash: str = ""
    composed_prompt_chars: int = 0
    composed_prompt_estimated_tokens: int = 0
    kb_context_estimated_tokens: int = 0
    original_prompt_chars: int = 0
    original_prompt_estimated_tokens: int = 0
    kb_prompt_ratio: float = 0.0
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    evidence_count: int = 0
    entity_count: int = 0
    selected_item_count: int = 0
    source_count: int = 0
    evidence_build_id: str = ""
    context_schema_version: str = ""
    retrieval_ms: int = 0
    context_build_ms: int = 0
    composition_ms: int = 0
    warnings: list[str] = field(default_factory=list)
    context_packet: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    cache_info: dict[str, Any] = field(default_factory=dict)
    budget_diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_audit_dict(self) -> dict[str, Any]:
        """Privacy-safe grounded metadata (never includes full prompts)."""
        return {
            "grounded_status": self.status,
            "grounded_flag_enabled": not self.grounded_disabled,
            "grounded_used": self.grounded_used,
            "grounded_fallback": self.grounded_fallback,
            "grounded_disabled": self.grounded_disabled,
            "grounded_unsupported_module": self.grounded_unsupported_module,
            "fallback_reason": self.fallback_reason,
            "module": self.module,
            "profile": self.profile,
            "passage_input": self.passage_input,
            "passage_canonical": self.canonical_passage,
            "composition_version": self.composition_version or COMPOSITION_VERSION,
            "prompt_hash": self.prompt_hash,
            "composed_prompt_chars": self.composed_prompt_chars,
            "composed_prompt_estimated_tokens": self.composed_prompt_estimated_tokens,
            "kb_context_estimated_tokens": self.kb_context_estimated_tokens,
            "kb_prompt_ratio": self.kb_prompt_ratio,
            "original_prompt_chars": self.original_prompt_chars,
            "original_prompt_estimated_tokens": self.original_prompt_estimated_tokens,
            "source_ids": list(self.source_ids),
            "evidence_count": self.evidence_count,
            "entity_count": self.entity_count,
            "selected_item_count": self.selected_item_count,
            "source_count": self.source_count,
            "evidence_packet_build_id": self.evidence_build_id,
            "context_schema_version": self.context_schema_version,
            "retrieval_duration_ms": self.retrieval_ms,
            "context_build_duration_ms": self.context_build_ms,
            "composition_duration_ms": self.composition_ms,
            "warning_count": len(self.warnings),
            "retrieval_warnings": list(self.warnings),
            "error": self.error,
            "budget_diagnostics": dict(self.budget_diagnostics),
            # Flatten for shadow_audit mapper
            "status": "success" if self.grounded_used else ("degraded" if self.grounded_fallback else "success"),
            "success": True,
            "token_estimate": self.kb_context_estimated_tokens,
            "evidence_item_count": self.evidence_count,
            "selected_context_count": self.selected_item_count,
            "production_prompt_chars": self.original_prompt_chars,
            "comparison": {
                "production_prompt_chars": self.original_prompt_chars,
                "production_output_chars": 0,
            },
        }


def _disabled(production_prompt: str, *, passage: str = "") -> GroundedPreparationResult:
    return GroundedPreparationResult(
        status=STATUS_DISABLED,
        provider_prompt=production_prompt,
        production_prompt=production_prompt,
        grounded_disabled=True,
        original_prompt_chars=len(production_prompt),
        passage_input=passage,
    )


def _unsupported_module(production_prompt: str, *, key: str, passage: str) -> GroundedPreparationResult:
    return GroundedPreparationResult(
        status=STATUS_UNSUPPORTED,
        provider_prompt=production_prompt,
        production_prompt=production_prompt,
        grounded_unsupported_module=True,
        fallback_reason=REASON_UNSUPPORTED_MODULE,
        original_prompt_chars=len(production_prompt),
        passage_input=passage,
        module=key,
        error=f"Unsupported module for grounded generation: {key!r}",
    )


def _fallback(
    production_prompt: str,
    *,
    reason: str,
    module: str = "",
    profile: str = "",
    passage: str = "",
    canonical: str = "",
    error: str = "",
    retrieval_ms: int = 0,
    context_build_ms: int = 0,
    composition_ms: int = 0,
    warnings: list[str] | None = None,
    context_packet: dict[str, Any] | None = None,
    **extra: Any,
) -> GroundedPreparationResult:
    return GroundedPreparationResult(
        status=STATUS_FALLBACK,
        provider_prompt=production_prompt,
        production_prompt=production_prompt,
        grounded_fallback=True,
        fallback_reason=reason,
        module=module,
        profile=profile,
        passage_input=passage,
        canonical_passage=canonical,
        original_prompt_chars=len(production_prompt),
        retrieval_ms=retrieval_ms,
        context_build_ms=context_build_ms,
        composition_ms=composition_ms,
        warnings=list(warnings or []),
        context_packet=dict(context_packet or {}),
        error=error,
        **extra,
    )


def prepare_grounded_provider_prompt(
    *,
    production_prompt: str,
    passage: str,
    module: str,
    token_budget: int | None = None,
    grounded_enabled: bool | None = None,
    use_cache: bool = True,
) -> GroundedPreparationResult:
    """Build grounded provider prompt or hard-fallback to production prompt.

    Never calls a model provider. Never raises to callers for KB failures.

    When ``grounded_enabled`` is None, follows ``is_grounded_enabled()``
    (unset env → on; explicit false → emergency disable).
    """
    if grounded_enabled is None:
        grounded_enabled = is_grounded_enabled()
    if not grounded_enabled:
        return _disabled(production_prompt, passage=passage)

    profile = MODULE_TO_PROFILE.get(module)
    if profile is None:
        return _unsupported_module(production_prompt, key=module, passage=passage)

    if not str(passage).strip():
        return _fallback(
            production_prompt,
            reason=REASON_UNSUPPORTED_PASSAGE,
            module=module,
            profile=profile,
            passage=passage,
            error="Empty passage",
        )

    if not is_passage_allowlisted(passage):
        return _fallback(
            production_prompt,
            reason=REASON_PASSAGE_NOT_ALLOWLISTED,
            module=module,
            profile=profile,
            passage=passage,
            error="Passage not in TEXTUS_KB_GROUNDED_PASSAGE_ALLOWLIST",
        )

    theology_database_path: str | None = None
    if module == "theology":
        from textus_kb.theology_runtime import ensure_theology_database

        runtime_status = ensure_theology_database()
        if not runtime_status.available:
            return _fallback(
                production_prompt,
                reason=REASON_SOURCE_UNAVAILABLE,
                module=module,
                profile=profile,
                passage=passage,
                error=runtime_status.reason or "Theology store unavailable",
                warnings=[runtime_status.detail] if runtime_status.detail else None,
            )
        theology_database_path = runtime_status.database_path or None

    commentary_database_path: str | None = None
    if module == "commentary":
        from textus_kb.commentary_runtime import get_status as get_commentary_status

        runtime_status = get_commentary_status()
        if not runtime_status.available:
            return _fallback(
                production_prompt,
                reason=REASON_SOURCE_UNAVAILABLE,
                module=module,
                profile=profile,
                passage=passage,
                error=runtime_status.reason or "Commentary store unavailable",
                warnings=[runtime_status.detail] if runtime_status.detail else None,
            )
        commentary_database_path = runtime_status.database_path or None

    budget = int(token_budget) if token_budget is not None else None
    retrieval_ms = 0
    context_build_ms = 0
    cache_info: dict[str, Any] = {
        "evidence_cache_hit": False,
        "context_cache_hit": False,
    }

    try:
        from textus_kb.kb_cache import cached_retrieve
        from textus_kb.retrieval import retrieve

        t0 = time.perf_counter()
        evidence, evidence_hit = cached_retrieve(passage, retrieve, use_cache=use_cache)
        retrieval_ms = int((time.perf_counter() - t0) * 1000)
        cache_info["evidence_cache_hit"] = bool(evidence_hit)
    except Exception as exc:
        return _fallback(
            production_prompt,
            reason=REASON_RETRIEVAL_ERROR,
            module=module,
            profile=profile,
            passage=passage,
            error=f"{type(exc).__name__}",
            retrieval_ms=retrieval_ms,
        )

    try:
        from textus_kb.context_builder import build_context_from_evidence
        from textus_kb.kb_cache import cached_build_context

        def _build_context(evidence_packet, context_profile):
            if theology_database_path:
                return build_context_from_evidence(
                    evidence_packet,
                    context_profile,
                    theology_database_path=theology_database_path,
                )
            if commentary_database_path:
                return build_context_from_evidence(
                    evidence_packet,
                    context_profile,
                    commentary_database_path=commentary_database_path,
                )
            return build_context_from_evidence(evidence_packet, context_profile)

        t1 = time.perf_counter()
        context, context_hit = cached_build_context(
            evidence.passage_canonical or passage,
            profile,
            evidence,
            _build_context,
            use_cache=use_cache,
        )
        context_build_ms = int((time.perf_counter() - t1) * 1000)
        cache_info["context_cache_hit"] = bool(context_hit)
    except Exception as exc:
        return _fallback(
            production_prompt,
            reason=REASON_CONTEXT_ERROR,
            module=module,
            profile=profile,
            passage=passage,
            canonical=getattr(evidence, "passage_canonical", "") or "",
            error=f"{type(exc).__name__}",
            retrieval_ms=retrieval_ms,
            context_build_ms=context_build_ms,
        )

    if not context.source_ids and not any(section.items for section in context.sections):
        return _fallback(
            production_prompt,
            reason=REASON_SOURCE_UNAVAILABLE,
            module=module,
            profile=profile,
            passage=passage,
            canonical=evidence.passage_canonical,
            error="No KB sources/context items available",
            retrieval_ms=retrieval_ms,
            context_build_ms=context_build_ms,
            warnings=list(context.warnings),
            context_packet=context.to_dict(),
            evidence_build_id=evidence.build_id,
            evidence_count=len(evidence.evidence_items),
            entity_count=len(evidence.entities),
            cache_info=cache_info,
        )

    try:
        t2 = time.perf_counter()
        preview = compose_grounded_prompt(
            production_prompt=production_prompt,
            canonical_passage=evidence.passage_canonical,
            module=module,
            context_packet=context,
            token_budget=budget,
        )
        composition_ms = int((time.perf_counter() - t2) * 1000)
    except Exception as exc:
        return _fallback(
            production_prompt,
            reason=REASON_COMPOSITION_ERROR,
            module=module,
            profile=profile,
            passage=passage,
            canonical=evidence.passage_canonical,
            error=f"{type(exc).__name__}",
            retrieval_ms=retrieval_ms,
            context_build_ms=context_build_ms,
            context_packet=context.to_dict(),
            evidence_build_id=evidence.build_id,
            cache_info=cache_info,
        )

    selected = sum(len(section.items) for section in context.sections)
    base_kwargs = {
        "module": module,
        "profile": profile,
        "passage": passage,
        "canonical": evidence.passage_canonical,
        "retrieval_ms": retrieval_ms,
        "context_build_ms": context_build_ms,
        "composition_ms": composition_ms,
        "warnings": list(preview.warnings) + list(context.warnings),
        "context_packet": context.to_dict(),
        "evidence_build_id": evidence.build_id,
        "evidence_count": len(evidence.evidence_items),
        "entity_count": len(evidence.entities),
        "selected_item_count": selected,
        "source_ids": list(preview.source_ids or context.source_ids),
        "evidence_ids": list(preview.evidence_ids or context.evidence_ids),
        "source_count": len(preview.source_ids or context.source_ids),
        "composed_prompt_chars": preview.composed_prompt_chars,
        "composed_prompt_estimated_tokens": preview.composed_prompt_estimated_tokens,
        "kb_context_estimated_tokens": preview.kb_context_estimated_tokens,
        "kb_prompt_ratio": preview.kb_prompt_ratio,
        "original_prompt_estimated_tokens": preview.original_prompt_estimated_tokens,
        "composition_version": preview.composition_version,
        "prompt_hash": preview.prompt_hash,
        "context_schema_version": str(context.schema_version or ""),
        "cache_info": cache_info,
    }

    if not preview.success:
        return _fallback(
            production_prompt,
            reason=REASON_COMPOSITION_ERROR,
            error=(preview.error or "composition_failed")[:200],
            **base_kwargs,
        )

    if not preview.budget_ok or not preview.composed_prompt:
        return _fallback(
            production_prompt,
            reason=REASON_BUDGET_EXCEEDED,
            error="Grounded prompt exceeds token budget after KB trim",
            budget_diagnostics=preview.budget_diagnostics(),
            **base_kwargs,
        )

    # Success path — provider gets composed prompt exactly once.
    return GroundedPreparationResult(
        status=STATUS_USED,
        provider_prompt=preview.composed_prompt,
        production_prompt=production_prompt,
        grounded_used=True,
        module=module,
        profile=profile,
        passage_input=passage,
        canonical_passage=evidence.passage_canonical,
        composition_version=preview.composition_version,
        prompt_hash=preview.prompt_hash,
        composed_prompt_chars=preview.composed_prompt_chars,
        composed_prompt_estimated_tokens=preview.composed_prompt_estimated_tokens,
        kb_context_estimated_tokens=preview.kb_context_estimated_tokens,
        original_prompt_chars=len(production_prompt),
        original_prompt_estimated_tokens=preview.original_prompt_estimated_tokens,
        kb_prompt_ratio=preview.kb_prompt_ratio,
        source_ids=list(preview.source_ids),
        evidence_ids=list(preview.evidence_ids),
        evidence_count=len(evidence.evidence_items),
        entity_count=len(evidence.entities),
        selected_item_count=selected,
        source_count=len(preview.source_ids),
        evidence_build_id=evidence.build_id,
        context_schema_version=str(context.schema_version or ""),
        retrieval_ms=retrieval_ms,
        context_build_ms=context_build_ms,
        composition_ms=composition_ms,
        warnings=list(preview.warnings) + list(context.warnings),
        context_packet=context.to_dict(),
        cache_info=cache_info,
        budget_diagnostics=preview.budget_diagnostics(),
    )


def build_shadow_artifact_from_preparation(
    prep: GroundedPreparationResult,
    *,
    production_output: str,
    generation_duration_ms: int,
) -> dict[str, Any]:
    """Reuse grounded prep for shadow artifact when both flags are on."""
    artifact = {
        "status": "degraded" if prep.warnings else "success",
        "success": True,
        "module": prep.module,
        "profile": prep.profile,
        "passage_input": prep.passage_input,
        "passage_canonical": prep.canonical_passage,
        "evidence_packet_build_id": prep.evidence_build_id,
        "source_ids": list(prep.source_ids),
        "evidence_ids": list(prep.evidence_ids),
        "context_packet": dict(prep.context_packet),
        "token_estimate": prep.kb_context_estimated_tokens,
        "retrieval_warnings": list(prep.warnings),
        "retrieval_duration_ms": prep.retrieval_ms,
        "context_build_duration_ms": prep.context_build_ms,
        "evidence_item_count": prep.evidence_count,
        "entity_count": prep.entity_count,
        "selected_context_count": prep.selected_item_count,
        "source_count": prep.source_count,
        "generation_duration_ms": generation_duration_ms,
        "comparison": {
            "production_prompt_chars": prep.original_prompt_chars,
            "production_output_chars": len(production_output),
            "kb_context_tokens": prep.kb_context_estimated_tokens,
        },
        "composed_prompt_chars": prep.composed_prompt_chars,
        "composed_prompt_estimated_tokens": prep.composed_prompt_estimated_tokens,
        "kb_prompt_ratio": prep.kb_prompt_ratio,
        "composition_version": prep.composition_version,
        "prompt_hash": prep.prompt_hash,
        "grounded_status": prep.status,
        "grounded_used": prep.grounded_used,
        "grounded_fallback": prep.grounded_fallback,
        "fallback_reason": prep.fallback_reason,
        "reused_from_grounded_prep": True,
    }
    return artifact


__all__ = [
    "GROUNDED_FLAG",
    "PASSAGE_ALLOWLIST_FLAG",
    "GroundedPreparationResult",
    "REASON_BUDGET_EXCEEDED",
    "REASON_COMPOSITION_ERROR",
    "REASON_CONTEXT_ERROR",
    "REASON_PASSAGE_NOT_ALLOWLISTED",
    "REASON_RETRIEVAL_ERROR",
    "REASON_SOURCE_UNAVAILABLE",
    "REASON_UNSUPPORTED_MODULE",
    "REASON_UNSUPPORTED_PASSAGE",
    "STATUS_DISABLED",
    "STATUS_FALLBACK",
    "STATUS_UNSUPPORTED",
    "STATUS_USED",
    "build_shadow_artifact_from_preparation",
    "is_grounded_enabled",
    "is_grounded_injection_allowed",
    "is_passage_allowlisted",
    "passage_allowlist_canonicals",
    "prepare_grounded_provider_prompt",
    "resolve_grounded_module",
]
