"""UI for the biblical map prototype."""

from __future__ import annotations

import html
import math
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
from biblical_routes import (
    BiblicalRoute,
    BiblicalRouteDataError,
    BiblicalRouteStop,
    find_route_stop_matches_for_passage,
    load_biblical_routes,
    route_options,
)


SELECTED_PLACE_ID_KEY = "_biblical_map_selected_place_id"
SELECTED_PLACE_SELECTBOX_KEY = f"{SELECTED_PLACE_ID_KEY}_selectbox"
CATALOG_SEARCH_QUERY_KEY = "_biblical_map_catalog_search_query"
CATALOG_SEARCH_PICK_KEY = "_biblical_map_catalog_search_pick"
CATALOG_SEARCH_LIMIT = 20
ACTIVE_MAP_VIEW_KEY = "_biblical_map_active_view"
MAP_VIEW_PLACES = "Helyszínek"
MAP_VIEW_ROUTES = "Bibliai útvonalak"
SELECTED_ROUTE_ID_KEY = "_biblical_map_selected_route_id"
SELECTED_ROUTE_STOP_ID_KEY = "_biblical_map_selected_route_stop_id"
HIGHLIGHTED_ROUTE_STOP_IDS_KEY = "_biblical_map_highlighted_route_stop_ids"
ROUTE_VIEW_WARNING_HU = (
    "Az útvonal a bibliai szövegben megnevezett állomások sorrendjét mutatja. "
    "A vonalak sematikusak, nem a pontos ókori nyomvonalat jelölik."
)

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
CERTAINTY_LABELS = {
    "certain": "biztos",
    "probable": "valószínű",
    "possible": "lehetséges",
    "disputed": "vitatott",
    "unknown": "ismeretlen",
    "mixed": "vegyes",
}
GEOMETRY_STATUS_LABELS = {
    "schematic": "sematikus",
    "reconstructed": "rekonstruált",
    "approximate": "hozzávetőleges",
    "exact": "pontos",
    "unavailable": "nem áll rendelkezésre",
}
STOP_TYPE_LABELS = {
    "embarkation": "behajózás",
    "disembarkation": "partraszállás",
    "transit": "áthaladás",
    "destination": "célállomás",
    "return_stop": "visszaúti állomás",
    "explicit_place": "a szövegben megnevezett hely",
    "inferred_stop": "kikövetkeztetett állomás",
    "region": "régió",
    "uncertain_place": "bizonytalan hely",
}
SEGMENT_TYPE_LABELS = {
    "land": "szárazföldi",
    "sea": "tengeri",
    "river": "folyami",
    "mixed": "vegyes",
    "schematic": "sematikus",
    "unknown": "ismeretlen",
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


def route_stop_display_name(stop: BiblicalRouteStop, place: BiblicalPlace | None) -> str:
    override = str(stop.place_name_override_hu or "").strip()
    if override:
        return override
    if place is not None:
        return display_place_name(place)
    return stop.place_id


def route_direction_label(stop: BiblicalRouteStop) -> str:
    if stop.stop_type == "return_stop" or stop.stop_id.endswith("_return"):
        return "visszaút"
    return "odaút"


def route_stop_rows(
    route: BiblicalRoute,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
    *,
    selected_stop_id: str | None = None,
    highlighted_stop_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    by_id = places_by_id(places)
    highlighted = set(highlighted_stop_ids)
    rows: list[dict[str, Any]] = []
    for stop in route.stops:
        place = by_id.get(stop.place_id)
        if place is None:
            continue
        is_selected = stop.stop_id == selected_stop_id
        is_highlighted = stop.stop_id in highlighted
        rows.append(
            {
                "lat": place.latitude,
                "lon": place.longitude,
                "display_lat": place.latitude,
                "display_lon": place.longitude,
                "name": route_stop_display_name(stop, place),
                "place_id": place.place_id,
                "stop_id": stop.stop_id,
                "order": stop.order,
                "label": str(stop.order),
                "stop_type": stop.stop_type,
                "stop_type_label": _display_status(stop.stop_type, STOP_TYPE_LABELS),
                "certainty": stop.certainty,
                "certainty_label": _display_status(stop.certainty, CERTAINTY_LABELS),
                "direction": route_direction_label(stop),
                "passage_refs": ", ".join(stop.passage_refs),
                "size": 680 if is_selected else 560 if is_highlighted else 420,
                "color": "#2f6f8f" if is_selected or is_highlighted else "#6f6a5f",
            }
        )
    coordinate_groups: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for row in rows:
        key = (round(float(row["lat"]), 6), round(float(row["lon"]), 6))
        coordinate_groups.setdefault(key, []).append(row)
    for group in coordinate_groups.values():
        if len(group) < 2:
            continue
        radius = 0.035
        for index, row in enumerate(sorted(group, key=lambda item: int(item["order"]))):
            angle = (2 * math.pi * index) / len(group)
            row["display_lat"] = float(row["lat"]) + math.sin(angle) * radius
            row["display_lon"] = float(row["lon"]) + math.cos(angle) * radius
    return rows


def route_segment_rows(
    route: BiblicalRoute,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> list[dict[str, Any]]:
    by_place_id = places_by_id(places)
    stop_by_id = {stop.stop_id: stop for stop in route.stops}
    rows: list[dict[str, Any]] = []
    for segment in route.segments:
        from_stop = stop_by_id.get(segment.from_stop_id)
        to_stop = stop_by_id.get(segment.to_stop_id)
        if from_stop is None or to_stop is None:
            continue
        from_place = by_place_id.get(from_stop.place_id)
        to_place = by_place_id.get(to_stop.place_id)
        if from_place is None or to_place is None:
            continue
        direction = (
            "return"
            if (
                from_stop.stop_type == "return_stop"
                or to_stop.stop_type == "return_stop"
                or from_stop.stop_id.endswith("_return")
                or to_stop.stop_id.endswith("_return")
            )
            else "outbound"
        )
        rows.append(
            {
                "from_stop_id": segment.from_stop_id,
                "to_stop_id": segment.to_stop_id,
                "segment_type": segment.segment_type,
                "segment_type_label": _display_status(segment.segment_type, SEGMENT_TYPE_LABELS),
                "certainty": segment.certainty,
                "certainty_label": _display_status(segment.certainty, CERTAINTY_LABELS),
                "geometry_status": segment.geometry_status,
                "geometry_status_label": _display_status(segment.geometry_status, GEOMETRY_STATUS_LABELS),
                "direction": direction,
                "line_style": "dashed" if direction == "return" else "solid",
                "path": [
                    [from_place.longitude, from_place.latitude],
                    [to_place.longitude, to_place.latitude],
                ],
                "color": (
                    [53, 101, 132, 190]
                    if segment.segment_type == "sea"
                    else [132, 101, 61, 190]
                )
                if direction == "outbound"
                else (
                    [53, 101, 132, 125]
                    if segment.segment_type == "sea"
                    else [132, 101, 61, 125]
                ),
                "width": 4 if segment.segment_type == "sea" else 3,
            }
        )
    return rows


def route_viewport(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {"latitude": 0.0, "longitude": 0.0, "zoom": 1.0}
    latitudes = [float(row["lat"]) for row in rows]
    longitudes = [float(row["lon"]) for row in rows]
    lat_span = max(latitudes) - min(latitudes)
    lon_span = max(longitudes) - min(longitudes)
    span = max(lat_span, lon_span)
    zoom = 6.0 if span < 2 else 5.0 if span < 6 else 4.0 if span < 14 else 3.0
    return {
        "latitude": sum(latitudes) / len(latitudes),
        "longitude": sum(longitudes) / len(longitudes),
        "zoom": zoom,
    }


def route_matches_for_passage(
    reference: str | None,
) -> dict[str, list[BiblicalRouteStop]]:
    grouped: dict[str, list[BiblicalRouteStop]] = {}
    for match in find_route_stop_matches_for_passage(reference):
        grouped.setdefault(match.route.route_id, []).append(match.stop)
    return grouped


def switch_to_route_view_for_passage(
    session_state: Any,
    route_id: str,
    stop_ids: list[str] | tuple[str, ...],
) -> None:
    unique_stop_ids = list(dict.fromkeys(str(stop_id) for stop_id in stop_ids if stop_id))
    session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    session_state[SELECTED_ROUTE_ID_KEY] = route_id
    session_state[HIGHLIGHTED_ROUTE_STOP_IDS_KEY] = unique_stop_ids
    if unique_stop_ids:
        session_state[SELECTED_ROUTE_STOP_ID_KEY] = unique_stop_ids[0]


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
    raw = str(value or "").strip()
    if not raw:
        return "—"
    return labels.get(raw, raw.replace("_", " "))


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


def _render_passage_route_prompt(st: Any, current_ref: str) -> None:
    matches_by_route = route_matches_for_passage(current_ref)
    if not matches_by_route:
        return
    try:
        routes = {route.route_id: route for route in load_biblical_routes()}
    except BiblicalRouteDataError:
        return
    for route_id, stops in matches_by_route.items():
        route = routes.get(route_id)
        if route is None:
            continue
        stop_names = [
            route_stop_display_name(stop, places_by_id(BIBLICAL_MAP_PLACES).get(stop.place_id))
            for stop in stops
        ]
        st.info(
            "Ez a szakasz egy nagyobb bibliai útvonal része.\n\n"
            f"Kapcsolódó útvonal: {route.name_hu}\n\n"
            f"Érintett állomások: {', '.join(stop_names)}"
        )
        if st.button(
            "A teljes útvonal megtekintése",
            key=f"_biblical_map_open_route_{route_id}",
        ):
            switch_to_route_view_for_passage(
                st.session_state,
                route_id,
                [stop.stop_id for stop in stops],
            )
            if hasattr(st, "rerun"):
                st.rerun()


def _route_labels(routes: tuple[BiblicalRoute, ...]) -> dict[str, str]:
    return {route.route_id: route.name_hu for route in routes}


def compact_ancient_name_options(place: BiblicalPlace, *, limit: int = 6) -> tuple[str, ...]:
    values = [
        *place.ancient_names,
        *place.original_names,
        *place.transliterations,
    ]
    compact: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _usable_text(value)
        if not text:
            continue
        if re.search(r"\s+\d+$", text):
            continue
        normalized = normalize_place_search_text(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        compact.append(text)
        if len(compact) >= limit:
            break
    return tuple(compact)


def _all_route_place_name_options(place: BiblicalPlace) -> tuple[str, ...]:
    values = [
        *place.ancient_names,
        *place.original_names,
        *place.transliterations,
    ]
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _usable_text(value)
        normalized = normalize_place_search_text(text)
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        names.append(text)
    return tuple(names)


def _render_compact_route_place_card(
    st: Any,
    place: BiblicalPlace,
    passage_reference: str,
) -> None:
    display_name = display_place_name(place)
    ancient_names = compact_ancient_name_options(place)
    all_names = _all_route_place_name_options(place)
    modern_location = " · ".join(
        part for part in (place.modern_name, place.modern_country) if _usable_text(part)
    ) or "—"
    description = fallback_place_description(place)
    st.markdown(
        f"""
<div class="textus-biblical-map-card">
  <h4>{html.escape(display_name)}</h4>
  <div class="textus-biblical-map-meta">
    <div><strong>Ókori / alternatív név:</strong> {html.escape(", ".join(ancient_names) if ancient_names else "—")}</div>
    <div><strong>Angol név:</strong> {html.escape(place.name_en or "—")}</div>
    <div><strong>Mai hely:</strong> {html.escape(modern_location)}</div>
    <div><strong>Helytípus:</strong> {html.escape(place.place_type or "—")}</div>
    <div><strong>Bizonyosság:</strong> {html.escape(_display_status(place.identification_status, IDENTIFICATION_STATUS_LABELS))}</div>
    <div><strong>Kapcsolódó igehely:</strong> {html.escape(passage_reference or "—")}</div>
  </div>
  {f"<p>{html.escape(description)}</p>" if description else ""}
</div>
""",
        unsafe_allow_html=True,
    )
    if len(all_names) > len(ancient_names):
        hidden_names = [name for name in all_names if name not in ancient_names]
        with st.expander("További névváltozatok", expanded=False):
            st.markdown(", ".join(html.escape(name) for name in hidden_names))


def _render_route_legend(st: Any, segment_rows: list[dict[str, Any]]) -> None:
    items = ["szárazföldi út", "tengeri út", "visszaút"]
    if any(row.get("certainty") in {"possible", "disputed", "unknown"} for row in segment_rows):
        items.append("bizonytalan szakasz")
    st.caption("Jelmagyarázat: " + " · ".join(items))


def _render_route_map(
    st: Any,
    route: BiblicalRoute,
    stop_rows: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
) -> None:
    if not stop_rows:
        st.warning("Ehhez az útvonalhoz nincs megjeleníthető állomás.")
        return
    viewport = route_viewport(stop_rows)
    _render_route_legend(st, segment_rows)
    try:
        import pydeck as pdk  # type: ignore

        layers = []
        if segment_rows:
            layers.append(
                pdk.Layer(
                    "PathLayer",
                    data=segment_rows,
                    get_path="path",
                    get_color="color",
                    get_width="width",
                    width_min_pixels=2,
                    pickable=True,
                )
            )
        layers.extend(
            [
                pdk.Layer(
                    "ScatterplotLayer",
                    data=stop_rows,
                    get_position="[display_lon, display_lat]",
                    get_radius="size",
                    get_fill_color="[245, 239, 224, 230]",
                    get_line_color="[45, 55, 65, 220]",
                    line_width_min_pixels=2,
                    pickable=True,
                ),
                pdk.Layer(
                    "TextLayer",
                    data=stop_rows,
                    get_position="[display_lon, display_lat]",
                    get_text="label",
                    get_size=14,
                    get_color="[30, 42, 56, 255]",
                    get_alignment_baseline="'center'",
                    pickable=False,
                ),
            ]
        )
        st.pydeck_chart(
            pdk.Deck(
                map_style=None,
                initial_view_state=pdk.ViewState(
                    latitude=viewport["latitude"],
                    longitude=viewport["longitude"],
                    zoom=viewport["zoom"],
                ),
                layers=layers,
                tooltip={
                    "text": "{order}. {name}\n{direction} · {passage_refs}\n{stop_type_label} · {certainty_label}"
                },
            ),
            use_container_width=True,
            height=520,
        )
    except Exception:
        st.warning(
            "Az útvonalas térképi nézet nem érhető el; az állomásmarkerek egyszerű térképen jelennek meg."
        )
        try:
            st.map(
                stop_rows,
                latitude="display_lat",
                longitude="display_lon",
                size="size",
                color="color",
                zoom=int(viewport["zoom"]),
                use_container_width=True,
            )
        except Exception:
            st.warning("Az útvonal térképi megjelenítése most nem érhető el.")


def _render_route_view(st: Any) -> None:
    st.markdown("### Bibliai útvonalak")
    try:
        routes = load_biblical_routes()
    except BiblicalRouteDataError:
        st.warning("A bibliai útvonalak adatai most nem érhetők el.")
        return
    if not routes:
        st.caption("Még nincs betölthető bibliai útvonal.")
        return

    options = route_options(routes)
    labels = _route_labels(routes)
    selected_route_id = str(st.session_state.get(SELECTED_ROUTE_ID_KEY) or "")
    if selected_route_id not in options:
        selected_route_id = options[0]
        st.session_state[SELECTED_ROUTE_ID_KEY] = selected_route_id
    selected_route_id = st.selectbox(
        "Útvonal kiválasztása",
        options,
        index=options.index(selected_route_id),
        format_func=lambda route_id: labels.get(route_id, route_id),
        key=SELECTED_ROUTE_ID_KEY,
    )
    route = next(route for route in routes if route.route_id == selected_route_id)
    highlighted_stop_ids = tuple(st.session_state.get(HIGHLIGHTED_ROUTE_STOP_IDS_KEY) or ())
    selected_stop_id = str(st.session_state.get(SELECTED_ROUTE_STOP_ID_KEY) or "")
    valid_stop_ids = [stop.stop_id for stop in route.stops]
    if selected_stop_id not in valid_stop_ids:
        selected_stop_id = highlighted_stop_ids[0] if highlighted_stop_ids else valid_stop_ids[0]
        st.session_state[SELECTED_ROUTE_STOP_ID_KEY] = selected_stop_id

    st.markdown(f"**{route.name_hu}**")
    st.caption(
        "Elsődleges szakasz: "
        + ", ".join(route.primary_passage_refs)
        + (f" · {route.chronology_label_hu}" if route.chronology_label_hu else "")
    )
    st.caption(
        f"Bizonyosság: {_display_status(route.certainty, CERTAINTY_LABELS)} · "
        f"Geometria: {_display_status(route.geometry_status, GEOMETRY_STATUS_LABELS)}"
    )
    st.warning(ROUTE_VIEW_WARNING_HU)

    stop_rows = route_stop_rows(
        route,
        selected_stop_id=selected_stop_id,
        highlighted_stop_ids=highlighted_stop_ids,
    )
    segment_rows = route_segment_rows(route)
    _render_route_map(st, route, stop_rows, segment_rows)

    stop_labels = {
        stop.stop_id: (
            f"{stop.order}. "
            f"{route_stop_display_name(stop, places_by_id(BIBLICAL_MAP_PLACES).get(stop.place_id))} "
            f"– {route_direction_label(stop)}"
        )
        for stop in route.stops
    }
    selector_col, detail_col = st.columns([0.36, 0.64], gap="medium")
    with selector_col:
        chosen_stop_id = st.selectbox(
            "Állomás kiválasztása",
            valid_stop_ids,
            index=valid_stop_ids.index(selected_stop_id),
            format_func=lambda stop_id: stop_labels.get(stop_id, stop_id),
            key=SELECTED_ROUTE_STOP_ID_KEY,
        )
    with detail_col:
        selected_stop = next(stop for stop in route.stops if stop.stop_id == chosen_stop_id)
        selected_place = places_by_id(BIBLICAL_MAP_PLACES).get(selected_stop.place_id)
        st.markdown(
            f"**{selected_stop.order}. {route_stop_display_name(selected_stop, selected_place)} – "
            f"{route_direction_label(selected_stop)}**"
        )
        st.caption(
            f"Igehely: {', '.join(selected_stop.passage_refs)} · "
            f"{_display_status(selected_stop.stop_type, STOP_TYPE_LABELS)} · "
            f"{_display_status(selected_stop.certainty, CERTAINTY_LABELS)}"
        )
        st.markdown(selected_stop.event_summary_hu)
        if selected_place is not None:
            _render_compact_route_place_card(
                st,
                selected_place,
                ", ".join(selected_stop.passage_refs),
            )

    st.markdown("#### Állomások")
    for stop in route.stops:
        place = places_by_id(BIBLICAL_MAP_PLACES).get(stop.place_id)
        emphasis = "**" if stop.stop_id in highlighted_stop_ids else ""
        st.markdown(
            f"{emphasis}{stop.order}. {route_stop_display_name(stop, place)} – "
            f"{route_direction_label(stop)}{emphasis}  \n"
            f"{stop.event_summary_hu}  \n"
            f"`{', '.join(stop.passage_refs)}` · "
            f"{_display_status(stop.stop_type, STOP_TYPE_LABELS)} · "
            f"{_display_status(stop.certainty, CERTAINTY_LABELS)}"
        )


def _render_places_view(
    st: Any,
    *,
    passage_reference: str | None,
    places: tuple[BiblicalPlace, ...],
) -> None:
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
    if current_ref:
        _render_passage_route_prompt(st, current_ref)

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


def render_biblical_map_prototype(
    passage_reference: str | None = None,
    *,
    st_module: Any | None = None,
) -> None:
    """Render the biblical map prototype in the Textus workshop."""
    st = st_module or _streamlit()
    places = BIBLICAL_MAP_PLACES

    _render_styles(st)
    with st.expander("Bibliai térkép", expanded=False):
        view_options = [MAP_VIEW_PLACES, MAP_VIEW_ROUTES]
        current_view = str(st.session_state.get(ACTIVE_MAP_VIEW_KEY) or MAP_VIEW_PLACES)
        if current_view not in view_options:
            current_view = MAP_VIEW_PLACES
        active_view = st.radio(
            "Térkép nézet",
            view_options,
            index=view_options.index(current_view),
            horizontal=True,
            key=ACTIVE_MAP_VIEW_KEY,
        )
        if active_view == MAP_VIEW_ROUTES:
            _render_route_view(st)
        else:
            _render_places_view(st, passage_reference=passage_reference, places=places)


__all__ = [
    "ACTIVE_MAP_VIEW_KEY",
    "CATALOG_SEARCH_LIMIT",
    "CATALOG_SEARCH_PICK_KEY",
    "CATALOG_SEARCH_QUERY_KEY",
    "CERTAINTY_LABELS",
    "GEOMETRY_STATUS_LABELS",
    "HIGHLIGHTED_ROUTE_STOP_IDS_KEY",
    "MAP_VIEW_PLACES",
    "MAP_VIEW_ROUTES",
    "SELECTED_PLACE_ID_KEY",
    "SELECTED_PLACE_SELECTBOX_KEY",
    "SELECTED_ROUTE_ID_KEY",
    "SELECTED_ROUTE_STOP_ID_KEY",
    "ROUTE_VIEW_WARNING_HU",
    "SEGMENT_TYPE_LABELS",
    "STOP_TYPE_LABELS",
    "compact_ancient_name_options",
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
    "route_matches_for_passage",
    "route_segment_rows",
    "route_stop_display_name",
    "route_stop_rows",
    "route_viewport",
    "search_biblical_places",
    "selected_place_for_session",
    "switch_to_route_view_for_passage",
]
