"""Íróasztal fő munkafelület — RÚF / eredeti nyelvi olvasóblokk + munkakivonatok.

A jobb oldali jegyzetszerkesztő továbbra is helyőrző.
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
from writing_desk_data import WRITING_DESK_EXTRACT_KEYS, ensure_writing_desk_state
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
WORK_MATERIAL_SECTIONS: tuple[str, ...] = tuple(
    EXTRACT_LABELS[key] for key in WRITING_DESK_EXTRACT_KEYS
)

GenerateFn = Callable[..., str]


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
        with work_surface("writing_desk_notes_placeholder"):
            render_info_panel(
                title="Szerkesztő helye",
                body="A jegyzet- és vázlatszerkesztő a következő fázisban kerül ide.",
                tone="neutral",
            )


__all__ = [
    "WORK_MATERIAL_SECTIONS",
    "WRITING_DESK_BIBLE_VIEW_KEY",
    "WRITING_DESK_LABEL",
    "WRITING_DESK_MODE",
    "WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX",
    "render_writing_desk_shell",
]
