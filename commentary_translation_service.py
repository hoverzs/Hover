"""Narrow service API over the derived, cache-only Hungarian Commentary
translation layer -- ``get_translation`` (cache-only) and
``get_or_create_translation`` (cache-or-generate), sitting on top of
``textus_kb.commentary_translation_store`` (SQLite cache) and
``textus_kb.commentary_translation_policy`` (prompt + glossary).

No Streamlit dependency here, mirroring ``commentary_compare.py``'s own
split between orchestration and UI -- the UI layer (the "Eredeti" /
"Magyar fordítás" toggle in ``commentary_ui.py``) is a thin caller on
top of this module, and receives ``generate_fn`` from ``app.py`` exactly
like the compare feature does.

Fail-closed throughout: any failure here (missing/corrupt translation
DB, missing/failing provider, missing section) degrades to "no Hungarian
translation available right now" -- it NEVER touches or blocks the
original, read-only Commentary browsing
(``textus_kb.repositories.commentary_repository``, ``commentary.sqlite3``).
A translation is always DERIVED content: its provenance is traceable
through ``section_id`` back to the exact original section (work/edition/
contributors/upstream source), the same metadata the retrieval-only
cards already display -- never treated as, or displayed as, an original
quotation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from textus_kb.commentary_translation_policy import (
    TRANSLATION_POLICY_VERSION,
    build_translation_prompt,
)
from textus_kb.commentary_translation_store import (
    TranslationRecord,
    compute_source_fingerprint,
    get_translation as _store_get_translation,
    save_translation as _store_save_translation,
)
from textus_kb.repositories.commentary_repository import CommentaryRepository

DEFAULT_LANGUAGE = "hu"
TRANSLATION_TAB_LABEL = "Kommentár fordítás (HU)"


@dataclass(frozen=True)
class TranslationOutcome:
    # "cached" | "missing" | "generated" | "unavailable"
    # | "provider_error" | "no_generate_fn"
    status: str
    message: str = ""
    text: str = ""
    provider_model: str = ""
    created_at: str = ""


def _looks_like_provider_failure(text: str) -> bool:
    """Same warning-string convention guarded against elsewhere (ld.
    ``commentary_compare._looks_like_provider_failure``) -- ``generate_
    text`` (app.py) returns a warning STRING rather than raising on a
    blocking condition (missing API key, cooldown, etc.). Without this
    check a "⚠️ Hiányzó API kulcs…" string would be cached and displayed
    as if it were a genuine translation."""
    raw = (text or "").strip()
    if not raw:
        return True
    return raw.startswith(("⚠️", "⏳"))


def _record_to_outcome(record: TranslationRecord) -> TranslationOutcome:
    return TranslationOutcome(
        status="cached",
        text=record.translated_text,
        provider_model=record.provider_model,
        created_at=record.created_at,
    )


def get_translation(
    section_id: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    repository: CommentaryRepository | None = None,
    database_path: str | Path | None = None,
) -> TranslationOutcome:
    """Cache-only lookup -- never calls a provider. Fail-closed: a
    missing section, a missing translation DB, or a corrupt translation
    DB all resolve to a plain "missing"/"unavailable" outcome, never an
    exception."""
    repo = repository if repository is not None else CommentaryRepository()
    detail = repo.section_detail(section_id)
    if detail is None:
        return TranslationOutcome(status="unavailable", message="A szakasz nem érhető el.")
    fingerprint = compute_source_fingerprint([c.plain_text for c in detail.chunks])
    record = _store_get_translation(
        section_id,
        fingerprint,
        language=language,
        policy_version=TRANSLATION_POLICY_VERSION,
        database_path=database_path,
    )
    if record is None:
        return TranslationOutcome(status="missing")
    return _record_to_outcome(record)


def get_or_create_translation(
    section_id: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    generate_fn: Callable[..., str] | None,
    provider_model: str = "",
    repository: CommentaryRepository | None = None,
    database_path: str | Path | None = None,
    bypass_cooldown: bool = False,
) -> TranslationOutcome:
    """Cache-hit -> immediate return, zero provider calls. Cache-miss ->
    translates the FULL canonical section (every chunk, in order -- never
    just a UI preview), then persists on success. Provider unavailability
    or failure never stores anything (fail-closed) and never blocks the
    original English Commentary, which this function never touches.

    ``bypass_cooldown`` forwards straight to ``generate_fn`` (matches
    ``generate_text``'s own "same button press" convention for multiple
    calls back-to-back, ld. its docstring in app.py) -- callers that
    translate SEVERAL sections from one user action (ld. commentary_ui.
    _translate_missing_sections) must set this for every call after the
    first, or app.py's own inter-call cooldown makes every call but the
    first fail as a false "provider unavailable"."""
    repo = repository if repository is not None else CommentaryRepository()
    detail = repo.section_detail(section_id)
    if detail is None:
        return TranslationOutcome(status="unavailable", message="A szakasz nem érhető el.")

    chunk_texts = [c.plain_text for c in detail.chunks]
    fingerprint = compute_source_fingerprint(chunk_texts)
    cached = _store_get_translation(
        section_id,
        fingerprint,
        language=language,
        policy_version=TRANSLATION_POLICY_VERSION,
        database_path=database_path,
    )
    if cached is not None:
        return _record_to_outcome(cached)

    if not chunk_texts:
        return TranslationOutcome(
            status="unavailable", message="Ehhez a szakaszhoz nem tartozik önálló szöveg."
        )
    if generate_fn is None:
        return TranslationOutcome(
            status="no_generate_fn", message="Nincs elérhető AI-hívás a fordításhoz."
        )

    source_text = "\n\n".join(chunk_texts)
    prompt = build_translation_prompt(
        section_text=source_text,
        work_title=detail.work_title,
        contributors=", ".join(detail.contributors) or "—",
        passage_display=", ".join(detail.primary_passages or detail.canonical_passages) or "—",
    )
    raw = generate_fn(
        prompt,
        enable_google_search=False,
        tab_label=TRANSLATION_TAB_LABEL,
        use_cache=False,
        include_brevity_directive=False,
        bypass_cooldown=bypass_cooldown,
    )
    text = str(raw or "")
    if _looks_like_provider_failure(text):
        return TranslationOutcome(status="provider_error", message=text)

    saved = _store_save_translation(
        section_id=section_id,
        source_fingerprint=fingerprint,
        language=language,
        policy_version=TRANSLATION_POLICY_VERSION,
        translated_text=text,
        provider_model=provider_model,
        database_path=database_path,
    )
    if saved is not None:
        return TranslationOutcome(
            status="generated",
            text=saved.translated_text,
            provider_model=saved.provider_model,
            created_at=saved.created_at,
        )
    # Store write failed (e.g. translation DB unavailable/corrupt) -- the
    # text itself is still a valid, real translation and safe to show
    # once; it just won't be cached this time (next open re-generates).
    return TranslationOutcome(status="generated", text=text, provider_model=provider_model)


__all__ = [
    "DEFAULT_LANGUAGE",
    "TRANSLATION_TAB_LABEL",
    "TranslationOutcome",
    "get_or_create_translation",
    "get_translation",
]
