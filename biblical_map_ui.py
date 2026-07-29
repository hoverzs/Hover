"""UI for the biblical map prototype."""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any, Mapping

from biblical_map_data import (
    BIBLICAL_MAP_PLACES,
    BiblicalMapSource,
    BiblicalPlace,
    places_by_id,
    primary_place,
    sources_by_id,
)
from biblical_map_passages import (
    MAP_SELECTION_SOURCE_AUTO,
    MAP_SELECTION_SOURCE_KEY,
    MAP_SELECTION_SOURCE_MANUAL,
    apply_passage_place_selection,
    find_place_links_for_passage,
)


SELECTED_PLACE_ID_KEY = "_biblical_map_selected_place_id"
SELECTED_PLACE_SELECTBOX_KEY = f"{SELECTED_PLACE_ID_KEY}_selectbox"
CATALOG_SEARCH_QUERY_KEY = "_biblical_map_catalog_search_query"
CATALOG_SEARCH_PICK_KEY = "_biblical_map_catalog_search_pick"
CATALOG_SEARCH_LIMIT = 20

IDENTIFICATION_STATUS_LABELS = {
    "certain": "biztos",
    "probable": "valószínű",
    "possible": "lehetséges",
    "disputed": "vitatott",
    "unknown": "ismeretlen",
}
TRANSLATION_STATUS_LABELS = {
    "not_translated": "nincs fordítva",
    "machine_draft": "gépi fordítási vázlat",
    "human_translated": "emberi fordítás",
    "not_required": "nem igényel fordítást",
}
REVIEW_STATUS_LABELS = {
    "prototype": "prototípus",
    "draft": "vázlat",
    "needs_review": "szakmai ellenőrzésre vár",
    "reviewed": "ellenőrzött",
    "approved": "jóváhagyott",
}


def resolve_selected_place_id(
    session_state: Mapping[str, Any],
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> str | None:
    """Return a valid selected place id, or None when nothing was chosen yet."""
    if not places:
        raise ValueError("At least one biblical map place is required.")
    selected = str(session_state.get(SELECTED_PLACE_ID_KEY) or "").strip()
    valid_ids = {place.place_id for place in places}
    if selected in valid_ids:
        return selected
    return None


def selected_place_for_session(
    session_state: Mapping[str, Any],
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> BiblicalPlace:
    selected_id = resolve_selected_place_id(session_state, places)
    if selected_id:
        return places_by_id(places).get(selected_id) or primary_place(places)
    return primary_place(places)


def place_option_labels(
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> dict[str, str]:
    return {
        place.place_id: (
            f"{display_place_name(place)} – elsődleges helyszín"
            if place.is_primary
            else display_place_name(place)
        )
        for place in places
    }


def place_selectbox_options(
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
    prioritized_place_id: str | None = None,
) -> list[str]:
    """Return deterministic place id options with an optional first item."""
    by_id: dict[str, BiblicalPlace] = {}
    for place in places:
        by_id.setdefault(place.place_id, place)

    sorted_places = sorted(
        by_id.values(),
        key=lambda place: (display_place_name(place).casefold(), place.place_id),
    )
    options = [place.place_id for place in sorted_places]
    priority = str(prioritized_place_id or "").strip()
    if priority in by_id:
        return [priority] + [place_id for place_id in options if place_id != priority]
    return options


def passage_linked_places(
    reference: str | None,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> tuple[BiblicalPlace, ...]:
    """Places linked to the current passage only (never the full catalog)."""
    by_id = places_by_id(places)
    linked: list[BiblicalPlace] = []
    for link in find_place_links_for_passage(reference):
        place = by_id.get(link.place_id)
        if place is not None:
            linked.append(place)
    return tuple(linked)


def normalize_place_search_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _place_search_haystacks(place: BiblicalPlace) -> tuple[str, ...]:
    values = [
        place.name_hu,
        place.name_en,
        place.modern_name,
        place.modern_country,
        place.ancient_name,
        *place.ancient_names,
        *place.original_names,
        *place.transliterations,
        place.place_id,
    ]
    return tuple(normalize_place_search_text(value) for value in values if value)


def display_place_name(place: BiblicalPlace) -> str:
    for value in (
        place.name_hu,
        place.name_en,
        place.ancient_name,
        place.modern_name,
        *place.ancient_names,
        *place.transliterations,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "Névtelen bibliai hely"


def fallback_place_description(place: BiblicalPlace) -> str:
    if place.card_summary_hu:
        return place.card_summary_hu
    if not place.modern_name:
        return ""
    location_parts = [
        value
        for value in (place.ancient_region, place.region_hu, place.modern_country)
        if value
    ]
    if not location_parts:
        status_prefix = (
            "Bizonytalan azonosítású bibliai helyszín"
            if place.identification_status in {"possible", "disputed", "unknown"}
            else "Bibliai helyszín"
        )
        return f"{status_prefix}; mai azonosítása: {place.modern_name}."
    status_prefix = (
        "Bizonytalan azonosítású bibliai helyszín"
        if place.identification_status in {"possible", "disputed", "unknown"}
        else "Bibliai helyszín"
    )
    return (
        f"{status_prefix} az ókori {location_parts[0]} területén; "
        f"mai azonosítása: {place.modern_name}."
    )


def search_biblical_places(
    query: str | None,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
    *,
    limit: int = CATALOG_SEARCH_LIMIT,
) -> list[BiblicalPlace]:
    """Accent/case-insensitive ranked catalog search, capped to `limit` hits."""
    needle = normalize_place_search_text(query)
    if not needle or limit <= 0:
        return []

    ranked: list[tuple[int, str, BiblicalPlace]] = []
    for place in places:
        haystacks = _place_search_haystacks(place)
        if not haystacks:
            continue
        score = 0
        if any(item == needle for item in haystacks):
            score = 300
        elif any(item.startswith(needle) for item in haystacks):
            score = 200
        elif any(needle in item for item in haystacks):
            score = 100
        if score:
            ranked.append((score, display_place_name(place).casefold(), place))

    ranked.sort(key=lambda item: (-item[0], item[1], item[2].place_id))
    return [place for _, _, place in ranked[:limit]]


def map_rows(
    selected_place_id: str,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> list[dict[str, Any]]:
    """Rows for Streamlit's built-in map widget."""
    rows: list[dict[str, Any]] = []
    for place in places:
        is_selected = place.place_id == selected_place_id
        rows.append(
            {
                "lat": place.latitude,
                "lon": place.longitude,
                "name": display_place_name(place),
                "place_id": place.place_id,
                "size": 520 if place.is_primary or is_selected else 240,
                "color": "#5a7aa8" if place.is_primary or is_selected else "#8a6a3f",
            }
        )
    return rows


def _streamlit():
    try:
        import streamlit as st  # type: ignore
    except ImportError as exc:  # pragma: no cover - app runtime dependency
        raise RuntimeError("Streamlit is required to render the biblical map prototype.") from exc
    return st


def _render_styles(st: Any) -> None:
    st.markdown(
        """
<style>
.textus-biblical-map-note {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.84rem;
  line-height: 1.45;
  margin: 0.2rem 0 0.75rem;
}
.textus-biblical-map-card {
  border-left: 3px solid var(--tx-primary, #5a7aa8);
  background: rgba(236, 242, 248, 0.55);
  padding: 0.75rem 0.85rem;
  border-radius: 0 8px 8px 0;
  margin-top: 0.25rem;
}
.textus-biblical-map-card h4 {
  margin: 0 0 0.35rem;
  font-size: 1rem;
}
.textus-biblical-map-meta {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.84rem;
  line-height: 1.45;
}
.textus-biblical-map-sources {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.78rem;
  line-height: 1.3;
  margin: 0.3rem 0 0;
}
.textus-biblical-map-sources a {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
  word-break: break-word;
}
.textus-biblical-map-quality {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.78rem;
  line-height: 1.3;
  margin: 0.45rem 0 0;
}
@media (max-width: 768px) {
  .textus-biblical-map-card {
    margin-top: 0.75rem;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )


def _display_status(value: str | None, labels: Mapping[str, str]) -> str:
    return labels.get(str(value or "").strip(), str(value or "").strip() or "—")


def _source_index() -> dict[str, BiblicalMapSource]:
    try:
        return sources_by_id()
    except Exception:
        return {}


def dedupe_sources(sources: list[BiblicalMapSource]) -> list[BiblicalMapSource]:
    """Drop duplicate source_id / provider entries while preserving order."""
    unique: list[BiblicalMapSource] = []
    seen_ids: set[str] = set()
    seen_providers: set[str] = set()
    for source in sources:
        source_id = _usable_text(source.source_id)
        provider = normalize_place_search_text(
            _usable_text(source.provider) or _usable_text(source.title)
        )
        if source_id and source_id in seen_ids:
            continue
        if provider and provider in seen_providers:
            continue
        if source_id:
            seen_ids.add(source_id)
        if provider:
            seen_providers.add(provider)
        unique.append(source)
    return unique


def _resolve_sources(place: BiblicalPlace) -> list[BiblicalMapSource]:
    by_id = _source_index()
    resolved = [source for source_id in place.source_ids if (source := by_id.get(source_id))]
    return dedupe_sources(resolved)


def _uses_only_manual_demo_source(place: BiblicalPlace) -> bool:
    source_ids = tuple(source_id for source_id in place.source_ids if source_id)
    return source_ids == ("manual_demo_v1",)


def _usable_text(value: str | None) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _compact_source_markdown_item(source: BiblicalMapSource) -> str:
    provider = _usable_text(source.provider) or _usable_text(source.title) or "Forrás"
    url = _usable_text(source.source_url)
    if url:
        return f"[{provider}]({url})"
    return provider


def _compact_source_html_item(source: BiblicalMapSource) -> str:
    provider = html.escape(
        _usable_text(source.provider) or _usable_text(source.title) or "Forrás"
    )
    url = _usable_text(source.source_url)
    if url:
        return (
            f'<a href="{html.escape(url, quote=True)}" '
            f'target="_blank" rel="noopener">{provider}</a>'
        )
    return provider


def compact_sources_markdown(sources: list[BiblicalMapSource]) -> str:
    """Return a single compact inline sources line, or empty string."""
    items = [
        item
        for source in dedupe_sources(sources)
        if (item := _compact_source_markdown_item(source))
    ]
    if not items:
        return ""
    return "**Források:** " + " · ".join(items)


def compact_sources_html(sources: list[BiblicalMapSource]) -> str:
    """Return compact inline HTML for sources, or empty string."""
    items = [
        item
        for source in dedupe_sources(sources)
        if (item := _compact_source_html_item(source))
    ]
    if not items:
        return ""
    return (
        '<div class="textus-biblical-map-sources">'
        "<strong>Források:</strong> "
        + " · ".join(items)
        + "</div>"
    )


def _render_short_sources(st: Any, sources: list[BiblicalMapSource]) -> None:
    html_block = compact_sources_html(sources)
    if not html_block:
        return
    st.markdown(html_block, unsafe_allow_html=True)


def _render_detail_expanders(st: Any, place: BiblicalPlace) -> None:
    sources = _resolve_sources(place)

    background_fields = [
        ("Földrajzi háttér", place.geography_hu),
        ("Történeti háttér", place.history_hu),
        ("Politikai-közigazgatási háttér", place.political_context_hu),
        ("Gazdasági háttér", place.economic_context_hu),
        ("Társadalmi háttér", place.social_context_hu),
        ("Vallási háttér", place.religious_context_hu),
        ("Régészeti háttér", place.archaeology_hu),
        ("Bibliai jelentőség", place.biblical_significance_hu),
        ("Mai kontextus", place.modern_context_hu),
    ]
    if any(value for _, value in background_fields):
        with st.expander("Részletes háttér", expanded=False):
            for label, value in background_fields:
                if value:
                    st.markdown(f"**{label}.** {value}")
            quality_parts = []
            if place.identification_status:
                identification_label = _display_status(
                    place.identification_status,
                    IDENTIFICATION_STATUS_LABELS,
                )
                if identification_label and identification_label != "—":
                    quality_parts.append(f"{identification_label} helyazonosítás")
            if place.review_status:
                review_label = _display_status(place.review_status, REVIEW_STATUS_LABELS)
                if review_label and review_label != "—":
                    quality_parts.append(review_label)
            quality_text = " · ".join(part for part in quality_parts if part and part != "—")
            if quality_text:
                st.markdown(
                    f'<div class="textus-biblical-map-quality">'
                    f"Adatminőség: {html.escape(quality_text)}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            _render_short_sources(st, sources)

    if place.exegetical_notes:
        with st.expander("Exegetikai megjegyzések", expanded=False):
            for note in place.exegetical_notes:
                st.markdown(f"**{note.passage_reference} – {note.title_hu}**")
                st.markdown(note.note_hu)
                if note.limitations_hu:
                    st.caption(f"Korlátok: {note.limitations_hu}")
                source_lookup = _source_index()
                resolved = dedupe_sources(
                    [
                        source
                        for source_id in note.source_ids
                        if (source := source_lookup.get(source_id))
                    ]
                )
                _render_short_sources(st, resolved)


def _render_place_card(st: Any, place: BiblicalPlace, passage_reference: str) -> None:
    current_ref = passage_reference.strip()
    primary_badge = " · elsődleges helyszín" if place.is_primary else ""
    display_name = display_place_name(place)
    ancient_name = place.ancient_name or "—"
    name_en = place.name_en or "—"
    modern_country = place.modern_country or "—"
    place_type = place.place_type or "—"
    description = fallback_place_description(place)
    passage_line = (
        f"<div><strong>Aktuális igerész:</strong> {html.escape(current_ref)}</div>"
        if current_ref
        else "<div><strong>Aktuális igerész:</strong> még nincs megadva.</div>"
    )
    sources = _resolve_sources(place)
    show_card_sources = sources and any(
        source.source_id != "manual_demo_v1" for source in sources
    )
    source_line = compact_sources_html(sources) if show_card_sources else ""
    demo_source_line = (
        f'<div class="textus-biblical-map-meta"><strong>Forrás:</strong> '
        f"{html.escape(place.source_note)}</div>"
        if _uses_only_manual_demo_source(place)
        else ""
    )
    st.markdown(
        f"""
<div class="textus-biblical-map-card">
  <h4>{html.escape(display_name)}{primary_badge}</h4>
  <div class="textus-biblical-map-meta">
    <div><strong>Ókori / alternatív név:</strong> {html.escape(ancient_name)}</div>
    <div><strong>Angol név:</strong> {html.escape(name_en)}</div>
    <div><strong>Mai ország:</strong> {html.escape(modern_country)}</div>
    <div><strong>Helytípus:</strong> {html.escape(place_type)}</div>
    <div><strong>Azonosítás:</strong> {_display_status(place.identification_status, IDENTIFICATION_STATUS_LABELS)}</div>
    <div><strong>Koordináta:</strong> {place.latitude:.4f}, {place.longitude:.4f}</div>
    {passage_line}
    {source_line}
  </div>
  {f"<p>{html.escape(description)}</p>" if description else ""}
  {demo_source_line}
</div>
""",
        unsafe_allow_html=True,
    )
    _render_detail_expanders(st, place)


def _render_passage_place_selector(
    st: Any,
    *,
    linked_places: tuple[BiblicalPlace, ...],
    selected_id: str | None,
    auto_place_id: str | None,
) -> str | None:
    """Render passage-only place controls; never the full catalog."""
    labels = place_option_labels(linked_places)
    linked_ids = [place.place_id for place in linked_places]
    selection_source = str(st.session_state.get(MAP_SELECTION_SOURCE_KEY) or "")

    if not linked_ids:
        return selected_id

    if len(linked_ids) == 1:
        only_id = linked_ids[0]
        st.caption(f"Aktuális igerész helyszíne: {labels.get(only_id, only_id)}")
        if selection_source == MAP_SELECTION_SOURCE_MANUAL and selected_id and selected_id != only_id:
            # Catalog pick stays until the user changes it.
            return selected_id
        st.session_state[SELECTED_PLACE_ID_KEY] = only_id
        return only_id

    options = place_selectbox_options(linked_places, auto_place_id or selected_id)
    if selected_id not in options:
        preferred = auto_place_id if auto_place_id in options else options[0]
        st.session_state[SELECTED_PLACE_SELECTBOX_KEY] = preferred
        selected_id = preferred
        st.session_state[SELECTED_PLACE_ID_KEY] = preferred
    elif (
        selection_source == MAP_SELECTION_SOURCE_AUTO
        or st.session_state.get(SELECTED_PLACE_SELECTBOX_KEY) not in options
    ):
        st.session_state[SELECTED_PLACE_SELECTBOX_KEY] = selected_id

    current_index = options.index(selected_id) if selected_id in options else 0
    chosen_id = st.selectbox(
        "Aktuális igerész helyszínei",
        options,
        index=current_index,
        format_func=lambda place_id: labels.get(place_id, place_id),
        key=SELECTED_PLACE_SELECTBOX_KEY,
    )
    if chosen_id != selected_id:
        st.session_state[SELECTED_PLACE_ID_KEY] = chosen_id
        st.session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_MANUAL
        return chosen_id
    return selected_id


def _render_catalog_search(
    st: Any,
    *,
    places: tuple[BiblicalPlace, ...],
    selected_id: str | None,
) -> str | None:
    """Separate full-catalog search; picking a hit updates map/card."""
    st.text_input(
        "Másik bibliai hely keresése",
        key=CATALOG_SEARCH_QUERY_KEY,
        placeholder="pl. korinthus, athens, antiochia…",
        help="Magyar, angol, ókori, mai és alternatív nevek; ékezetfüggetlen.",
    )
    query = str(st.session_state.get(CATALOG_SEARCH_QUERY_KEY) or "").strip()
    if not query:
        if CATALOG_SEARCH_PICK_KEY in st.session_state:
            del st.session_state[CATALOG_SEARCH_PICK_KEY]
        return selected_id

    hits = search_biblical_places(query, places, limit=CATALOG_SEARCH_LIMIT)
    if not hits:
        st.caption("Nincs találat a katalógusban.")
        return selected_id

    labels = place_option_labels(hits)
    options = [place.place_id for place in hits]
    placeholder = "— válassz a találatok közül —"
    select_options = [placeholder, *options]
    current_pick = str(st.session_state.get(CATALOG_SEARCH_PICK_KEY) or "").strip()
    if current_pick not in select_options:
        st.session_state[CATALOG_SEARCH_PICK_KEY] = placeholder
    chosen = st.selectbox(
        "Keresési találatok",
        select_options,
        format_func=lambda place_id: (
            placeholder if place_id == placeholder else labels.get(place_id, place_id)
        ),
        key=CATALOG_SEARCH_PICK_KEY,
    )
    if chosen != placeholder and chosen != selected_id:
        st.session_state[SELECTED_PLACE_ID_KEY] = chosen
        st.session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_MANUAL
        return chosen
    return selected_id


def render_biblical_map_prototype(
    passage_reference: str | None = None,
    *,
    st_module: Any | None = None,
) -> None:
    """Render the isolated biblical map prototype in the Textus workshop."""
    st = st_module or _streamlit()
    places = BIBLICAL_MAP_PLACES

    _render_styles(st)
    with st.expander("Bibliai térkép – prototípus", expanded=False):
        current_ref = (passage_reference or "").strip()
        if current_ref:
            st.caption(f"Aktuális igerész: {current_ref}")
        else:
            st.caption("Aktuális igerész még nincs megadva.")
        if not places:
            st.warning("A bibliai térkép prototípus helyadatai nem érhetőek el.")
            return

        auto_link = apply_passage_place_selection(
            st.session_state,
            current_ref,
            selected_place_key=SELECTED_PLACE_ID_KEY,
        )
        linked_places = passage_linked_places(current_ref, places)
        selected_id = resolve_selected_place_id(st.session_state, places)
        by_id = places_by_id(places)

        st.markdown(
            '<div class="textus-biblical-map-note">'
            "A térkép az aktuális igerészhez kapcsolódó bibliai helyszíneket jeleníti meg."
            "</div>",
            unsafe_allow_html=True,
        )

        left, right = st.columns([1.18, 0.82], gap="medium")
        with left:
            map_focus_id = selected_id or (
                auto_link.place_id if auto_link is not None else primary_place(places).place_id
            )
            map_places = linked_places or (
                (by_id[map_focus_id],) if map_focus_id in by_id else ()
            )
            try:
                st.map(
                    map_rows(map_focus_id, map_places),
                    latitude="lat",
                    longitude="lon",
                    size="size",
                    color="color",
                    zoom=4,
                    use_container_width=True,
                )
            except Exception as exc:  # pragma: no cover - depends on Streamlit runtime
                st.warning(
                    "A térképi nézet nem érhető el, de a helyválasztó és az adatlap használható."
                )
                with st.expander("Technikai részletek", expanded=False):
                    st.caption(type(exc).__name__)

            selected_id = _render_passage_place_selector(
                st,
                linked_places=linked_places,
                selected_id=selected_id,
                auto_place_id=auto_link.place_id if auto_link is not None else None,
            )
            selected_id = _render_catalog_search(
                st,
                places=places,
                selected_id=selected_id,
            )

        selection_source = str(st.session_state.get(MAP_SELECTION_SOURCE_KEY) or "")
        if selected_id:
            st.session_state[SELECTED_PLACE_ID_KEY] = selected_id

        selected_place = by_id.get(selected_id) if selected_id else None
        if selected_place is None and auto_link is not None:
            selected_place = by_id.get(auto_link.place_id)
        if selected_place is None and linked_places:
            selected_place = linked_places[0]

        if current_ref and selection_source == MAP_SELECTION_SOURCE_AUTO and auto_link is not None:
            display_name = (
                display_place_name(selected_place)
                if selected_place is not None
                else display_place_name(by_id.get(auto_link.place_id))
                if by_id.get(auto_link.place_id) is not None
                else auto_link.place_id
            )
            st.info(
                "A helyszín a megadott igerész alapján automatikusan lett "
                f"kiválasztva: {display_name}."
            )
        elif current_ref and selection_source == MAP_SELECTION_SOURCE_MANUAL and selected_place:
            st.caption("A jelenlegi helyszínt kézzel választottad ki.")
        elif current_ref and not linked_places:
            st.caption(
                "Ehhez az igerészhez a prototípus még nem tartalmaz automatikus helykapcsolatot."
            )

        with right:
            if selected_place is not None:
                _render_place_card(st, selected_place, passage_reference or "")
            else:
                st.caption(
                    "Válassz helyszínt a keresőből, vagy adj meg olyan igerészt, "
                    "amelyhez van helykapcsolat."
                )


__all__ = [
    "CATALOG_SEARCH_LIMIT",
    "CATALOG_SEARCH_PICK_KEY",
    "CATALOG_SEARCH_QUERY_KEY",
    "SELECTED_PLACE_ID_KEY",
    "SELECTED_PLACE_SELECTBOX_KEY",
    "compact_sources_html",
    "compact_sources_markdown",
    "dedupe_sources",
    "map_rows",
    "normalize_place_search_text",
    "passage_linked_places",
    "place_option_labels",
    "place_selectbox_options",
    "render_biblical_map_prototype",
    "resolve_selected_place_id",
    "search_biblical_places",
    "selected_place_for_session",
]
