"""Korábban használt textusok — mentett projektekből, átfedés-szűréssel.

Nincs külön history-tábla: a felhasználó mentett projektjei az egyetlen
tartós forrás. Az AI-nak csak normalizált referencia-stringek mennek.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from ruf_bible_service import ParsedReference, parse_bible_reference

CACHE_KEY = "_passage_used_history_cache"
_MAX_VERSE = 200

_HU_MONTHS = (
    "",
    "január",
    "február",
    "március",
    "április",
    "május",
    "június",
    "július",
    "augusztus",
    "szeptember",
    "október",
    "november",
    "december",
)

FetchProjectsFn = Callable[[str], list[dict[str, Any]]]


@dataclass(frozen=True)
class NormalizedPassageSpan:
    """Összehasonlítható igehely-tartomány (könyv + fejezet/vers határok)."""

    book_code: str
    start_chapter: int
    start_verse: int
    end_chapter: int
    end_verse: int
    normalized_reference: str

    def start_key(self) -> tuple[int, int]:
        return (self.start_chapter, self.start_verse)

    def end_key(self) -> tuple[int, int]:
        return (self.end_chapter, self.end_verse)


@dataclass
class UsedPassageHistory:
    """Összegyűjtött, deduplikált korábbi textusok (csak refs + meta dátum)."""

    normalized_references: list[str] = field(default_factory=list)
    spans: list[NormalizedPassageSpan] = field(default_factory=list)
    last_used_at_by_ref: dict[str, str] = field(default_factory=dict)
    ok: bool = True
    error_message: str = ""
    fetch_failed: bool = False

    @property
    def count(self) -> int:
        return len(self.normalized_references)

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "normalized_references": list(self.normalized_references),
            "last_used_at_by_ref": dict(self.last_used_at_by_ref),
            "ok": self.ok,
            "error_message": self.error_message,
            "fetch_failed": self.fetch_failed,
        }


def _s(value: Any) -> str:
    return str(value or "").strip()


def span_from_parsed(parsed: ParsedReference) -> NormalizedPassageSpan:
    """ParsedReference → összehasonlítható tartomány."""
    chapter = int(parsed.chapter)
    if parsed.verse_start is None:
        return NormalizedPassageSpan(
            book_code=parsed.book.code,
            start_chapter=chapter,
            start_verse=1,
            end_chapter=chapter,
            end_verse=_MAX_VERSE,
            normalized_reference=parsed.normalized_reference,
        )
    v0 = int(parsed.verse_start)
    v1 = int(parsed.verse_end) if parsed.verse_end is not None else v0
    return NormalizedPassageSpan(
        book_code=parsed.book.code,
        start_chapter=chapter,
        start_verse=min(v0, v1),
        end_chapter=chapter,
        end_verse=max(v0, v1),
        normalized_reference=parsed.normalized_reference,
    )


def parse_passage_span(reference: str) -> NormalizedPassageSpan:
    """Referencia → NormalizedPassageSpan. ValueError érvénytelen esetén."""
    return span_from_parsed(parse_bible_reference(reference))


def try_parse_passage_span(reference: str) -> NormalizedPassageSpan | None:
    try:
        return parse_passage_span(reference)
    except (ValueError, TypeError, AttributeError):
        return None


def references_overlap(reference_a: Any, reference_b: Any) -> bool:
    """Ugyanazon könyvön belüli átfedő tartományok → True.

    Szomszédos, nem átfedő tartományok (pl. 16–18 és 19–21) → False.
    Más könyv azonos fejezet/vers mellett is → False.
    """
    span_a = _coerce_span(reference_a)
    span_b = _coerce_span(reference_b)
    if span_a is None or span_b is None:
        return False
    if span_a.book_code != span_b.book_code:
        return False
    # Átfedés: nem (A vége < B eleje vagy B vége < A eleje)
    if span_a.end_key() < span_b.start_key():
        return False
    if span_b.end_key() < span_a.start_key():
        return False
    return True


def _coerce_span(value: Any) -> NormalizedPassageSpan | None:
    if isinstance(value, NormalizedPassageSpan):
        return value
    if isinstance(value, ParsedReference):
        return span_from_parsed(value)
    if isinstance(value, str):
        return try_parse_passage_span(value)
    return None


def _extract_passage_raw(project: Mapping[str, Any]) -> str:
    """Kanonikus igehely a projektből — csak passage / last_igehely."""
    top = _s(project.get("passage"))
    if top:
        return top
    pdata = project.get("project_data")
    if isinstance(pdata, Mapping):
        return _s(pdata.get("last_igehely"))
    return ""


def _parse_when(raw: Any) -> datetime | None:
    text = _s(raw)
    if not text:
        return None
    # Supabase ISO: 2026-07-22T10:00:00+00:00 / ...Z
    cleaned = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        pass
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return datetime(int(text[0:4]), int(text[5:7]), int(text[8:10]))
        except ValueError:
            return None
    return None


def format_used_month_hu(iso_or_date: str) -> str:
    """ISO / dátum → „YYYY. hónap” (magyar). Üres ha nem értelmezhető."""
    dt = _parse_when(iso_or_date)
    if dt is None:
        return ""
    month = _HU_MONTHS[dt.month] if 1 <= dt.month <= 12 else ""
    if not month:
        return ""
    return f"{dt.year}. {month}"


def collect_used_passage_references(
    saved_projects: Sequence[Mapping[str, Any]] | None,
) -> UsedPassageHistory:
    """Mentett projektek kanonikus igehelyeiből normalizált, deduplikált lista.

    A hívó már a saját felhasználó projektjeit adja át.
    Csak passage / last_igehely — semmi cím, jegyzet, outline.
    """
    best: dict[str, tuple[NormalizedPassageSpan, datetime | None, str]] = {}
    for project in saved_projects or []:
        if not isinstance(project, Mapping):
            continue
        raw = _extract_passage_raw(project)
        if not raw:
            continue
        span = try_parse_passage_span(raw)
        if span is None:
            continue
        key = span.normalized_reference
        when = _parse_when(project.get("updated_at")) or _parse_when(
            project.get("created_at")
        )
        when_raw = _s(project.get("updated_at")) or _s(project.get("created_at"))
        prev = best.get(key)
        if prev is None:
            best[key] = (span, when, when_raw)
            continue
        prev_when = prev[1]
        if when is not None and (prev_when is None or when > prev_when):
            best[key] = (span, when, when_raw)

    # Stabil sorrend: normalizált referencia ABC
    keys = sorted(best.keys(), key=lambda r: r.casefold())
    refs: list[str] = []
    spans: list[NormalizedPassageSpan] = []
    dates: dict[str, str] = {}
    for key in keys:
        span, _when, when_raw = best[key]
        refs.append(span.normalized_reference)
        spans.append(span)
        if when_raw:
            dates[span.normalized_reference] = when_raw
    return UsedPassageHistory(
        normalized_references=refs,
        spans=spans,
        last_used_at_by_ref=dates,
        ok=True,
    )


def reference_overlaps_any(
    reference: str,
    excluded: Sequence[Any],
) -> bool:
    """True, ha a referencia átfed bármely kizárt tartománnyal."""
    span = try_parse_passage_span(reference)
    if span is None:
        return False
    for item in excluded or []:
        if references_overlap(span, item):
            return True
    return False


def empty_used_passage_history() -> UsedPassageHistory:
    return UsedPassageHistory()


def invalidate_used_passage_cache(
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Cache törlése mentés / törlés / login / logout után."""
    if session_state is None:
        try:
            import streamlit as st

            session_state = st.session_state
        except Exception:
            return
    session_state.pop(CACHE_KEY, None)


def get_cached_used_passage_history(
    *,
    owner_sub: str | None,
    fetch_projects_fn: FetchProjectsFn | None,
    session_state: MutableMapping[str, Any] | None = None,
    force_refresh: bool = False,
) -> UsedPassageHistory:
    """Session-cache-elt korábbi textusok. Vendégnél üres, fetch nélkül."""
    if session_state is None:
        try:
            import streamlit as st

            session_state = st.session_state
        except Exception:
            session_state = {}

    owner = _s(owner_sub)
    if not owner:
        return empty_used_passage_history()

    if not force_refresh:
        cached = session_state.get(CACHE_KEY)
        if isinstance(cached, dict) and _s(cached.get("owner_sub")) == owner:
            return UsedPassageHistory(
                normalized_references=list(cached.get("normalized_references") or []),
                spans=[
                    s
                    for s in (
                        try_parse_passage_span(r)
                        for r in (cached.get("normalized_references") or [])
                    )
                    if s is not None
                ],
                last_used_at_by_ref=dict(cached.get("last_used_at_by_ref") or {}),
                ok=bool(cached.get("ok", True)),
                error_message=_s(cached.get("error_message")),
                fetch_failed=bool(cached.get("fetch_failed")),
            )

    if fetch_projects_fn is None:
        return UsedPassageHistory(
            ok=False,
            fetch_failed=True,
            error_message=(
                "A korábban használt textusokat most nem sikerült ellenőrizni. "
                "Az ajánlás enélkül folytatódik."
            ),
        )

    try:
        projects = fetch_projects_fn(owner)
        history = collect_used_passage_references(projects)
    except Exception:
        history = UsedPassageHistory(
            ok=False,
            fetch_failed=True,
            error_message=(
                "A korábban használt textusokat most nem sikerült ellenőrizni. "
                "Az ajánlás enélkül folytatódik."
            ),
        )

    session_state[CACHE_KEY] = {
        "owner_sub": owner,
        **history.to_cache_dict(),
    }
    return history


def find_previous_usage(
    reference: str,
    history: UsedPassageHistory | None,
) -> tuple[bool, str]:
    """(used, formatted_month) — badge-hez; cím nélkül."""
    if history is None or not history.normalized_references:
        return False, ""
    span = try_parse_passage_span(reference)
    if span is None:
        return False, ""
    for used_ref in history.normalized_references:
        if references_overlap(span, used_ref):
            raw_date = history.last_used_at_by_ref.get(used_ref, "")
            return True, format_used_month_hu(raw_date)
    return False, ""


__all__ = [
    "CACHE_KEY",
    "NormalizedPassageSpan",
    "UsedPassageHistory",
    "collect_used_passage_references",
    "parse_passage_span",
    "try_parse_passage_span",
    "span_from_parsed",
    "references_overlap",
    "reference_overlaps_any",
    "format_used_month_hu",
    "empty_used_passage_history",
    "invalidate_used_passage_cache",
    "get_cached_used_passage_history",
    "find_previous_usage",
]
