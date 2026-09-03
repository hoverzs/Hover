""""Kommentárok" fül -- közvetlen, retrieval-only nézet a Commentary
Knowledge Base fölött (jelenleg Calvin + JFB + Matthew Henry, de a UI
semmit nem tételez fel a forrásszámról vagy -nevekről -- ld. lentebb).

A kártyalista maga NEM generatív: minden kártya szó szerint a helyi
``commentary.sqlite3``-ból származik (``CommentaryRepository``). A meglévő
``render_section_tab()`` "Generálás gomb -> egy hosszú AI-szöveg" mintáját
szándékosan NEM használja ez a modul -- a Commentary UI/workflow audit
(2026-09-03) explicit döntése szerint ez retrieval-only forrásnézet, nem
generált tartalom, és a passage-retrieval mindig exact/range-overlap marad
(nincs FTS/semantic fallback -- ld. ``CommentaryRepository.
sections_for_passage`` saját dokumentációját).

Egy kibontott szakaszon belül -- opcionálisan, explicit felhasználói
kattintásra -- elérhető egy "Eredeti" / "Magyar fordítás" nézetváltó is
(ld. ``_render_translation_toggle``, ``commentary_translation_service``).
Ez az EGYETLEN generatív AI-hívási pont ezen a fülön; a fordítás mindig
származtatott, cache-elt réteg a ``commentary_translations.sqlite3``-ban,
sosem módosítja vagy helyettesíti az itt megjelenő eredeti angol szöveget,
és az eredeti mindig egy kattintással ("Eredeti") visszaérhető marad.

Forrás-generikusság: a forrás-szűrő checkboxok és a kártya-badge-ek NEM egy
hardcode-olt 3-elemű listából épülnek, hanem minden alkalommal a ténylegesen
visszakapott találatok ``contributors`` metaadatából származnak (ld.
``_primary_contributor``) -- egy jövőbeli negyedik korpusz importálásakor
ez a modul módosítás nélkül megjeleníti majd az új forrást is.
"""

from __future__ import annotations

from typing import Any, Callable, MutableMapping

import streamlit as st

import commentary_translation_service
from commentary_compare import render_commentary_compare_section
from textus_kb import commentary_runtime
from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.repositories.commentary_repository import (
    CommentaryRepository,
    CommentarySectionResult,
    primary_contributor_name,
)
from ui_components import (
    action_row,
    render_context_summary,
    render_info_panel,
    render_status_badge,
    render_work_section,
    work_surface,
)

_RELATION_TIER_LABELS_HU: dict[str, str] = {
    "exact_passage": "pontos találat",
    "containing_section": "tágabb szakasz tartalmazza",
    "partial_overlap": "részleges átfedés",
    "broader_context": "tágabb kontextus",
}

_PASSAGE_RELATION_LABELS_HU: dict[str, str] = {
    "primary": "fő kommentált hely",
    "parallel": "párhuzamos evangéliumi hely",
}

_PASSAGE_RELATION_LEGEND_HU = (
    "ℹ️ „Fő kommentált hely”: a szakasz elsődlegesen erről a helyről szól. "
    "„Párhuzamos evangéliumi hely”: a szerző (pl. Kálvin evangélium-"
    "harmóniája) egy másik evangéliumi párhuzam-vers kommentárjaként "
    "tárgyalja ezt a helyet is — ez a kapcsolat TÍPUSA, nem fontossági "
    "sorrend."
)

_SOURCE_BADGE_TONES: tuple[str, ...] = ("info", "success", "warning", "neutral")

_STATUS_REASON_LABELS_HU: dict[str, str] = {
    "database_missing": "A Commentary adatbázis (commentary.sqlite3) még nincs legenerálva.",
    "database_unopenable": "A Commentary adatbázis nem nyitható meg.",
    "schema_incompatible": "A Commentary adatbázis sémája nem kompatibilis a jelenlegi verzióval.",
}

_BUILD_HINT = (
    "Build parancs: `python scripts/build_commentary_database.py "
    "--combined-fetch --qa` (vagy `--combined`, ha a nyers forrásfájlok "
    "már helyben vannak a `data/raw/` alatt)."
)

_CACHE_PASSAGE_KEY = "_commentary_ui_cached_passage"
_CACHE_RESULTS_KEY = "_commentary_ui_cached_results"
_FILTER_STATE_KEY = "_commentary_ui_source_filter"
_PREVIEW_MAX_CHARS = 220
_MAX_DISPLAYED_CARDS = 12


def _primary_contributor(contributors: tuple[str, ...]) -> str:
    """UI-facing wrapper around ``commentary_repository.
    primary_contributor_name`` (shared with ``commentary_compare.py``, so
    the compare source-selection groups results the exact same way these
    cards do) — adds this module's own "unknown author" fallback label."""
    return primary_contributor_name(contributors) or "Ismeretlen szerző"


def _source_badge_tone(source_name: str) -> str:
    """Deterministic, generic tone assignment -- stable across reruns,
    scales to any number of distinct sources (cycles the palette)."""
    idx = sum(ord(ch) for ch in source_name) % len(_SOURCE_BADGE_TONES)
    return _SOURCE_BADGE_TONES[idx]


def _query_canonical(passage: str) -> str | None:
    try:
        return CanonicalReference.parse(passage).canonical_string()
    except CanonicalReferenceError:
        return None


def _passage_relation_key(
    result: CommentarySectionResult, query_canonical: str | None
) -> str | None:
    """Which relation label applies to THIS query passage specifically --
    a section can carry both primary and parallel links, so this is
    resolved per query, never as a blanket "this section is primary"."""
    if query_canonical and query_canonical in result.primary_passages:
        return "primary"
    if query_canonical and query_canonical in result.parallel_passages:
        return "parallel"
    if result.primary_passages and not result.parallel_passages:
        return "primary"
    if result.parallel_passages and not result.primary_passages:
        return "parallel"
    return None


def interleave_by_source(
    results: list[CommentarySectionResult],
) -> list[CommentarySectionResult]:
    """Diversity pass on top of the repository's already tier/primary-
    sorted list.

    ``CommentaryRepository.sections_for_passage`` already returns results
    ordered by (relevance tier, span, primary-before-parallel, document
    order) -- that ordering is fully preserved here. Within each tier this
    additionally round-robins across distinct sources so one commentator
    with many overlapping same-tier hits (e.g. JFB's per-verse partial-
    overlap sections across a wide range query) never crowds the others
    out of view. Structurally mirrors ``context_builder.
    _interleave_commentary_by_work`` / ``_round_robin_by_work``'s two-level
    (tier, then per-tier round-robin) approach, applied here to display
    cards instead of AI evidence items -- a UI-local helper, not a reuse
    of that private, differently-shaped function.
    """
    tier_order: list[str] = []
    tiers: dict[str, list[CommentarySectionResult]] = {}
    for item in results:
        tier = item.relation_type
        if tier not in tiers:
            tiers[tier] = []
            tier_order.append(tier)
        tiers[tier].append(item)

    interleaved: list[CommentarySectionResult] = []
    for tier in tier_order:
        source_order: list[str] = []
        by_source: dict[str, list[CommentarySectionResult]] = {}
        for item in tiers[tier]:
            source = _primary_contributor(item.contributors)
            if source not in by_source:
                by_source[source] = []
                source_order.append(source)
            by_source[source].append(item)
        while any(by_source[s] for s in source_order):
            for source in source_order:
                bucket = by_source[source]
                if bucket:
                    interleaved.append(bucket.pop(0))
    return interleaved


def _get_repository() -> CommentaryRepository:
    """Single, monkeypatchable seam for DB access -- production always uses
    the default (production) path; tests point this at an isolated store."""
    return CommentaryRepository()


def _translation_database_path() -> str | None:
    """Single, monkeypatchable seam mirroring ``_get_repository`` for the
    (separate, derived) translation cache -- ``None`` means "use
    ``commentary_translation_service``'s own default production path";
    tests point this at an isolated store so they never touch the real
    ``data/generated/commentary_translations.sqlite3``."""
    return None


def _get_status() -> commentary_runtime.CommentaryRuntimeStatus:
    """Single, monkeypatchable seam mirroring ``_get_repository`` for the
    runtime availability check."""
    return commentary_runtime.get_status()


def _fetch_results(passage: str) -> list[CommentarySectionResult]:
    repo = _get_repository()
    return interleave_by_source(repo.sections_for_passage(passage))


def _sources_present(results: list[CommentarySectionResult]) -> list[str]:
    """Distinct source names in first-seen order -- purely data-derived,
    never a hardcoded corpus list (ld. a modul docstringjét)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for r in results:
        name = _primary_contributor(r.contributors)
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _apply_source_filter(
    results: list[CommentarySectionResult], enabled_sources: set[str]
) -> list[CommentarySectionResult]:
    return [r for r in results if _primary_contributor(r.contributors) in enabled_sources]


def _ensure_results(
    passage: str,
    *,
    session: MutableMapping[str, Any] | None = None,
    force: bool = False,
) -> list[CommentarySectionResult]:
    """Per-passage cached retrieval. ``session`` defaults to the real
    ``st.session_state`` in production; tests may inject a plain dict to
    exercise the caching logic without a live Streamlit context."""
    store: MutableMapping[str, Any] = st.session_state if session is None else session
    if (
        force
        or store.get(_CACHE_PASSAGE_KEY) != passage
        or _CACHE_RESULTS_KEY not in store
    ):
        store[_CACHE_RESULTS_KEY] = _fetch_results(passage)
        store[_CACHE_PASSAGE_KEY] = passage
    return store[_CACHE_RESULTS_KEY]


def _render_missing_db(status: commentary_runtime.CommentaryRuntimeStatus) -> None:
    reason = _STATUS_REASON_LABELS_HU.get(status.reason, status.reason)
    render_info_panel(
        title="Commentary adatbázis nem elérhető",
        body=f"{reason} {_BUILD_HINT}",
        tone="warning",
    )


def _render_no_passage() -> None:
    render_info_panel(
        title="Nincs kiválasztva igeszakasz",
        body="Add meg az igeszakaszt az „Igehely” fülön, mielőtt a kommentárokat böngészed.",
        tone="neutral",
    )


def _render_no_match(passage: str) -> None:
    render_info_panel(
        title="Nincs kommentár-találat",
        body=(
            f"A jelenleg elérhető kommentárforrások egyike sem tartalmaz közvetlen "
            f"kommentárt erre a helyre: {passage}. A rendszer nem tér át szövegkeresésre "
            "vagy AI-pótlásra — csak a valódi, hozzárendelt kommentárszakaszokat mutatja."
        ),
        tone="neutral",
    )


def _render_all_sources_disabled() -> None:
    render_info_panel(
        title="Minden forrás ki van kapcsolva",
        body="Kapcsolj vissza legalább egy forrást a szűrőben a találatok megtekintéséhez.",
        tone="neutral",
    )


def _render_source_filter(results: list[CommentarySectionResult]) -> set[str]:
    sources_present = _sources_present(results)

    filter_state: dict[str, bool] = st.session_state.setdefault(_FILTER_STATE_KEY, {})
    if sources_present:
        cols = st.columns(len(sources_present))
        for col, name in zip(cols, sources_present):
            with col:
                filter_state[name] = st.checkbox(
                    name,
                    value=filter_state.get(name, True),
                    key=f"commentary_source_filter_{name}",
                )
    return {name for name, enabled in filter_state.items() if enabled}


def _render_card(
    result: CommentarySectionResult,
    *,
    query_canonical: str | None,
    generate_fn: Callable[..., str] | None = None,
    resolve_model_fn: Callable[[str], str] | None = None,
) -> None:
    source_name = _primary_contributor(result.contributors)
    tier_label = _RELATION_TIER_LABELS_HU.get(result.relation_type, result.relation_type)
    relation_key = _passage_relation_key(result, query_canonical)
    relation_label = _PASSAGE_RELATION_LABELS_HU.get(relation_key or "", "")

    passages = result.primary_passages or result.canonical_passages
    passage_display = ", ".join(passages) if passages else "—"

    with st.container(border=True):
        badge_col, title_col = st.columns([1, 4])
        with badge_col:
            render_status_badge(source_name, tone=_source_badge_tone(source_name))
        with title_col:
            st.markdown(f"**{result.work_title}**")

        caption_bits = [passage_display, tier_label]
        if relation_label:
            caption_bits.append(relation_label)
        st.caption(" · ".join(caption_bits))

        repo = _get_repository()
        preview = repo.chunk_previews([result.section_id], max_chars=_PREVIEW_MAX_CHARS).get(
            result.section_id, ""
        )
        if preview:
            st.write(preview)

        with st.expander("Teljes szöveg és forrás megtekintése"):
            _render_detail(result, generate_fn=generate_fn, resolve_model_fn=resolve_model_fn)


_TRANSLATION_VIEW_ORIGINAL = "Eredeti"
_TRANSLATION_VIEW_HUNGARIAN = "Magyar fordítás"
_TRANSLATION_VIEW_KEY_PREFIX = "commentary_translation_view_"


def _render_translation_view_toggle(section_id: str, *, has_text: bool) -> str:
    """"Eredeti" / "Magyar fordítás" nézetváltó -- csak akkor jelenik meg,
    ha a szakaszhoz egyáltalán tartozik önálló szöveg (szerkezeti, üres
    szakaszoknál nincs mit fordítani). Alapértelmezés MINDIG "Eredeti" --
    az eredeti angol szöveg soha nem tűnik el, csak explicit váltásra."""
    if not has_text:
        return _TRANSLATION_VIEW_ORIGINAL
    return st.radio(
        "Nézet",
        options=(_TRANSLATION_VIEW_ORIGINAL, _TRANSLATION_VIEW_HUNGARIAN),
        key=f"{_TRANSLATION_VIEW_KEY_PREFIX}{section_id}",
        horizontal=True,
        label_visibility="collapsed",
    )


def _render_translation_panel(
    card: CommentarySectionResult,
    *,
    generate_fn: Callable[..., str] | None,
    resolve_model_fn: Callable[[str], str] | None,
) -> None:
    """Cache-hit -> azonnal megjelenik, új modellhívás nélkül. Cache-miss
    -> explicit "Magyar fordítás készítése" gomb; a teljes kanonikus
    szakasz fordul (nem preview). Hiba/elérhetetlen provider esetén csak
    ez a panel jelez -- az "Eredeti" nézet és a fenti kártyalista ettől
    függetlenül változatlanul működik."""
    repo = _get_repository()
    db_path = _translation_database_path()
    outcome = commentary_translation_service.get_translation(
        card.section_id, repository=repo, database_path=db_path
    )
    if outcome.status == "cached":
        _render_translated_text(outcome, card)
        return
    if outcome.status != "missing":
        st.caption("A fordítás jelenleg nem érhető el ehhez a szakaszhoz.")
        return

    if st.button(
        "Magyar fordítás készítése",
        key=f"commentary_translate_btn_{card.section_id}",
        disabled=generate_fn is None,
    ):
        provider_model = (
            resolve_model_fn(commentary_translation_service.TRANSLATION_TAB_LABEL)
            if resolve_model_fn is not None
            else ""
        )
        with st.spinner("Magyar fordítás készítése…"):
            result = commentary_translation_service.get_or_create_translation(
                card.section_id,
                generate_fn=generate_fn,
                provider_model=provider_model,
                repository=repo,
                database_path=db_path,
            )
        if result.status in ("cached", "generated"):
            _render_translated_text(result, card)
        else:
            st.warning(result.message or "A fordítás jelenleg nem készíthető el.")


def _render_translated_text(
    outcome: "commentary_translation_service.TranslationOutcome",
    card: CommentarySectionResult,
) -> None:
    st.caption("AI által készített magyar fordítás")
    st.write(outcome.text)
    st.caption(
        f"Az eredeti angol szöveg gépi fordítása (forrás: {card.work_title}). "
        "Az eredeti szöveg az „Eredeti” nézetben egy kattintással elérhető."
    )


def _render_detail(
    card: CommentarySectionResult,
    *,
    generate_fn: Callable[..., str] | None = None,
    resolve_model_fn: Callable[[str], str] | None = None,
) -> None:
    repo = _get_repository()
    detail = repo.section_detail(card.section_id)
    if detail is None:
        st.warning("A szakasz részletei jelenleg nem érhetők el.")
        return

    if detail.parent_chain:
        breadcrumb = " › ".join((heading or sid) for sid, heading in detail.parent_chain)
        current = detail.heading or detail.section_type
        st.caption(f"Szerkezet: {breadcrumb} › {current}")

    passages = detail.primary_passages or detail.canonical_passages
    if passages:
        st.caption(f"Ez a szakasz erre a helyre vonatkozik: {', '.join(passages)}")
    if detail.parallel_passages:
        st.caption(f"Párhuzamos evangéliumi hely: {', '.join(detail.parallel_passages)}")

    view = _render_translation_view_toggle(card.section_id, has_text=bool(detail.chunks))
    if view == _TRANSLATION_VIEW_HUNGARIAN and detail.chunks:
        _render_translation_panel(card, generate_fn=generate_fn, resolve_model_fn=resolve_model_fn)
    else:
        for chunk in detail.chunks:
            st.write(chunk.plain_text)
        if not detail.chunks:
            st.caption("Ehhez a szakaszhoz nem tartozik önálló szöveg (csak szerkezeti elem).")

    source_locator = detail.chunks[0].source_locator if detail.chunks else ""
    render_context_summary(
        [
            ("Szerző/közreműködő", ", ".join(detail.contributors) or "—"),
            ("Mű", card.work_title),
            ("Kiadás (edition)", detail.edition_id),
            ("Kanonikus hely", ", ".join(detail.canonical_passages) or "—"),
            ("Forrás locator", source_locator or "—"),
        ]
    )
    provenance_bits = []
    if card.source_url:
        provenance_bits.append(f"Upstream forrás: {card.source_url}")
    if card.external_id:
        provenance_bits.append(f"Azonosító: {card.external_id}")
    if card.rights_status or card.license:
        provenance_bits.append(
            f"Jogi státusz: {card.rights_status or '—'}"
            + (f" ({card.license})" if card.license else "")
        )
    if provenance_bits:
        st.caption(" · ".join(provenance_bits))
    if card.rights_note:
        st.caption(card.rights_note)


def render_commentary_panel(
    *,
    generate_fn: Callable[..., str] | None = None,
    resolve_model_fn: Callable[[str], str] | None = None,
) -> None:
    """Renders the "Kommentárok" tab's entire content.

    ``generate_fn`` powers two independent, explicit-click-only generative
    actions: the "Kommentárok összehasonlítása" section below the cards,
    and the per-card "Magyar fordítás készítése" button inside an expanded
    section's "Eredeti" / "Magyar fordítás" toggle (ld. ``_render_
    translation_panel``). The retrieval-only card list itself still makes
    zero LLM calls on its own -- and, like ``generate_fn``, never names a
    concrete provider in this module's own source. ``resolve_model_fn``
    (app.py's own tab-based model-routing lookup) is optional,
    translation-only provenance metadata -- when omitted, translations
    are still generated and cached normally, just without a recorded
    provider/model name.
    """
    render_work_section(
        title="Kommentárok",
        body=(
            "Klasszikus kommentárok az aktuális igeszakaszhoz -- közvetlenül a "
            "forrásból, AI-összefoglalás nélkül. Minden kártya szó szerinti "
            "idézet a kiválasztott műből."
        ),
        context="Textusműhely",
    )

    status = _get_status()
    if not status.available:
        with work_surface("commentary_unavailable"):
            _render_missing_db(status)
        return

    passage = (st.session_state.get("last_igehely") or "").strip()
    if not passage:
        with work_surface("commentary_no_passage"):
            _render_no_passage()
        return

    with work_surface("commentary_results"):
        with action_row("commentary_refresh"):
            if st.button("Frissítés", key="commentary_refresh_btn"):
                _ensure_results(passage, force=True)
                st.rerun()

        results = _ensure_results(passage)
        if not results:
            _render_no_match(passage)
            return

        query_canonical = _query_canonical(passage)
        enabled_sources = _render_source_filter(results)
        visible = _apply_source_filter(results, enabled_sources)
        if not visible:
            _render_all_sources_disabled()
            return

        if any(r.parallel_passages for r in visible):
            st.caption(_PASSAGE_RELATION_LEGEND_HU)

        shown, hidden = visible[:_MAX_DISPLAYED_CARDS], visible[_MAX_DISPLAYED_CARDS:]
        for result in shown:
            _render_card(
                result,
                query_canonical=query_canonical,
                generate_fn=generate_fn,
                resolve_model_fn=resolve_model_fn,
            )
        if hidden:
            st.caption(
                f"+ {len(hidden)} további, alacsonyabb relevanciájú találat nem jelenik meg."
            )

        # Only enabled-AND-currently-shown sources count -- filter_state can
        # carry stale entries from a previous passage's checkboxes that no
        # longer render this render (ld. _render_source_filter), so this
        # must be intersected with the sources actually present now, not
        # used as the raw filter_state dict.
        ordered_enabled_sources = [s for s in _sources_present(results) if s in enabled_sources]

    with work_surface("commentary_compare_section"):
        render_commentary_compare_section(
            passage=passage,
            passage_display=passage,
            enabled_sources=ordered_enabled_sources,
            generate_fn=generate_fn,
        )


__all__ = ["render_commentary_panel", "interleave_by_source"]

# NOTE: the underscored helpers below (`_get_repository`, `_get_status`,
# `_fetch_results`, `_ensure_results`, `_sources_present`,
# `_apply_source_filter`, `_primary_contributor`, `_passage_relation_key`,
# `_query_canonical`) are intentionally still module-private (no public
# API contract) but are imported directly by tests/test_commentary_ui.py
# -- consistent with this repo's existing pattern of testing Streamlit UI
# modules via their pure helper functions rather than full rendering.
