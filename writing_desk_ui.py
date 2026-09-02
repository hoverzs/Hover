"""Íróasztal fő munkafelület — RÚF / eredeti nyelvi olvasóblokk + munkakivonatok.

A jobb oldali jegyzet/vázlat V1-ben natív plain-text mező.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from bible_text_ui import render_bible_text_reading_block
from ui_components import (
    render_info_panel,
    render_page_intro,
    render_work_section,
    work_surface,
)
from writing_desk_data import (
    WRITING_DESK_EXTRACT_KEYS,
    ensure_writing_desk_state,
    set_writing_desk_draft,
    writing_desk_draft_content,
)
from writing_desk_extracts import (
    EXTRACT_LABELS,
    STATUS_MISSING_SOURCE,
    STATUS_READY,
    STATUS_STALE,
    STATUS_VALID,
    extract_error_session_key,
    generate_writing_desk_extract,
    inspect_writing_desk_extract,
)


WRITING_DESK_MODE = "writing_desk"
WRITING_DESK_LABEL = "Íróasztal"
WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX = "writing_desk_original_language"
WRITING_DESK_BIBLE_VIEW_KEY = "writing_desk_bible_text_view_mode"
WRITING_DESK_DRAFT_WIDGET_KEY = "writing_desk_draft_input"
WRITING_DESK_DRAFT_RESYNC_FLAG = "_wd_draft_resync"
_DRAFT_TEXT_AREA_HEIGHT_PX = 400
WORK_MATERIAL_SECTIONS: tuple[str, ...] = tuple(
    EXTRACT_LABELS[key] for key in WRITING_DESK_EXTRACT_KEYS
)

GenerateFn = Callable[..., str]


def apply_writing_desk_draft_resync_if_needed() -> None:
    """Widgetkulcs szinkronja a tartós writing_desk.draft adattal (widget előtt)."""
    desk = ensure_writing_desk_state(st.session_state)
    force = bool(st.session_state.pop(WRITING_DESK_DRAFT_RESYNC_FLAG, False))
    content = writing_desk_draft_content(desk)
    if force or WRITING_DESK_DRAFT_WIDGET_KEY not in st.session_state:
        st.session_state[WRITING_DESK_DRAFT_WIDGET_KEY] = content


def _writing_desk_draft_project_sync_pending() -> bool:
    """Projektváltás / import / új munka: a durable draft a forrás, ne a widget."""
    return bool(
        st.session_state.get(WRITING_DESK_DRAFT_RESYNC_FLAG)
        or st.session_state.get("_pending_project_widget_sync")
    )


def commit_writing_desk_draft_from_widget() -> None:
    """Jegyzetmező → tartós `writing_desk.draft.content`.

    Normál szerkesztés és `on_change` út. Projektváltáskor / importnál /
    új munkánál nem ír, hogy a régi widgetérték ne írja felül az új draftot.
    """
    if _writing_desk_draft_project_sync_pending():
        return
    if WRITING_DESK_DRAFT_WIDGET_KEY not in st.session_state:
        return
    set_writing_desk_draft(
        st.session_state,
        st.session_state.get(WRITING_DESK_DRAFT_WIDGET_KEY) or "",
    )


def flush_writing_desk_draft_from_widget() -> None:
    """Élő jegyzetmező → tartós `writing_desk.draft` (ha a widget létezik).

    Mentés / dirty-check előtt hívandó, hogy a gépelés a projekt fingerprintbe
    kerüljön. Projektváltás után, ha a resync még nem futott, előbb a tartós
    adatból frissíti a widgetet, hogy régi session-érték ne írjon felül.
    """
    ensure_writing_desk_state(st.session_state)
    apply_writing_desk_draft_resync_if_needed()
    commit_writing_desk_draft_from_widget()


def _on_writing_desk_draft_change() -> None:
    """A textarea értéke a widget unmountja előtt a tartós draftba kerül.

    A főnézet-váltó gomb `st.rerun()`-t hív, mielőtt az Íróasztal shell
    újra létrehozná a mezőt. Az `on_change` a Streamlit callback-fázisában
    fut (az előző futtatás widget-metaadataiból), ezért a draft akkor is
    durable marad, ha ezen a futáson a textarea már nem mountolódik.
    """
    commit_writing_desk_draft_from_widget()


def _render_notes_editor() -> None:
    apply_writing_desk_draft_resync_if_needed()
    st.text_area(
        "Jegyzet / vázlat",
        key=WRITING_DESK_DRAFT_WIDGET_KEY,
        height=_DRAFT_TEXT_AREA_HEIGHT_PX,
        width="stretch",
        placeholder="Jegyzet, vázlat vagy szabad szöveg",
        label_visibility="collapsed",
        on_change=_on_writing_desk_draft_change,
    )
    commit_writing_desk_draft_from_widget()


def _render_scripture_block() -> None:
    """RÚF + görög/héber token UI; hiba esetén nem állítja le a shellt."""
    try:
        render_bible_text_reading_block(
            original_language_key_prefix=WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX,
            bible_view_key=WRITING_DESK_BIBLE_VIEW_KEY,
            display_mode="compact",
        )
    except Exception as exc:
        from streamlit.errors import Error as StreamlitError

        if isinstance(exc, StreamlitError):
            raise
        render_info_panel(
            title="A bibliai szöveg most nem jeleníthető meg",
            body=(
                "A jegyzetelés ettől függetlenül folytatható. "
                "A RÚF és az eredeti szöveg a Textusműhelyből tölthető be."
            ),
            tone="neutral",
        )


def _run_extract_generation(extract_key: str, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Kivonat készítése…"):
        result = generate_writing_desk_extract(
            st.session_state,
            extract_key,
            generate_fn=generate_fn,
        )
    error_key = extract_error_session_key(extract_key)
    if result.ok:
        st.session_state.pop(error_key, None)
    else:
        st.session_state[error_key] = result.error_message
    st.rerun()


def _render_extract_card(
    extract_key: str,
    *,
    generate_fn: GenerateFn | None,
) -> None:
    view = inspect_writing_desk_extract(st.session_state, extract_key)
    error_key = extract_error_session_key(extract_key)
    if view.status == STATUS_VALID:
        st.session_state.pop(error_key, None)
    error_text = str(st.session_state.get(error_key) or "").strip()
    with st.container(border=True, key=f"writing_desk_extract_card_{extract_key}"):
        st.markdown(f"**{view.label}**")
        if error_text:
            render_info_panel(
                title="A kivonat most nem készült el",
                body=error_text,
                tone="warning",
            )
        if view.status == STATUS_MISSING_SOURCE:
            st.caption(view.missing_message)
            return
        if view.status == STATUS_VALID:
            st.markdown(view.content)
            return
        if view.status == STATUS_STALE:
            st.caption("A forrásanyag megváltozott")
            if st.button(
                "Kivonat frissítése",
                key=f"writing_desk_extract_refresh_{extract_key}",
                width="stretch",
            ):
                _run_extract_generation(extract_key, generate_fn)
            return
        if view.status == STATUS_READY:
            if st.button(
                "Kivonat készítése",
                key=f"writing_desk_extract_generate_{extract_key}",
                width="stretch",
            ):
                _run_extract_generation(extract_key, generate_fn)


def render_writing_desk_shell(*, generate_fn: GenerateFn | None = None) -> None:
    """Rendereli az Íróasztal munkafelületét."""
    ensure_writing_desk_state(st.session_state)
    render_page_intro(
        title=WRITING_DESK_LABEL,
        body="Jegyzetelés és vázlatkészítés az aktuális projekthez.",
        workspace_scope=True,
    )

    render_work_section(
        title="Bibliai szöveg és eredeti nyelv",
        body="Az aktuális projekt RÚF szövege és kattintható eredeti nyelvi tokenjei.",
        context=WRITING_DESK_LABEL,
    )
    with work_surface("writing_desk_scripture"):
        _render_scripture_block()

    left_col, right_col = st.columns([1, 2.4], gap="large")

    with left_col:
        render_work_section(
            title="Munkaanyag",
            body="Rövid kivonatok a meglévő projektanyagból.",
            context=WRITING_DESK_LABEL,
        )
        with work_surface("writing_desk_work_material"):
            for extract_key in WRITING_DESK_EXTRACT_KEYS:
                _render_extract_card(extract_key, generate_fn=generate_fn)

    with right_col:
        render_work_section(
            title="Jegyzet / vázlat",
            body="A készülő jegyzet lesz az Íróasztal középpontja.",
            context=WRITING_DESK_LABEL,
        )
        with work_surface("writing_desk_notes"):
            _render_notes_editor()


__all__ = [
    "WORK_MATERIAL_SECTIONS",
    "WRITING_DESK_BIBLE_VIEW_KEY",
    "WRITING_DESK_DRAFT_RESYNC_FLAG",
    "WRITING_DESK_DRAFT_WIDGET_KEY",
    "WRITING_DESK_LABEL",
    "WRITING_DESK_MODE",
    "WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX",
    "apply_writing_desk_draft_resync_if_needed",
    "commit_writing_desk_draft_from_widget",
    "flush_writing_desk_draft_from_widget",
    "render_writing_desk_shell",
]
