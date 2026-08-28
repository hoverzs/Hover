"""Íróasztal fő munkafelület — v1 shell + RÚF / eredeti nyelvi olvasóblokk.

A kétoszlopos munkaterület továbbra is helyőrző. A tetején a meglévő
Textus RÚF- és eredetinyelv-renderelőket használjuk újra.
"""

from __future__ import annotations

import streamlit as st

from bible_text_ui import render_bible_text_reading_block
from ui_components import (
    render_info_panel,
    render_page_intro,
    render_work_section,
    work_surface,
)


WRITING_DESK_MODE = "writing_desk"
WRITING_DESK_LABEL = "Íróasztal"
WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX = "writing_desk_original_language"
WRITING_DESK_BIBLE_VIEW_KEY = "writing_desk_bible_text_view_mode"
WORK_MATERIAL_SECTIONS: tuple[str, ...] = (
    "Eredeti szöveg",
    "Kortörténet",
    "Teológia",
)


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


def render_writing_desk_shell() -> None:
    """Rendereli az Íróasztal munkafelületét."""
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
            body="Rövid kivonatok helye.",
            context=WRITING_DESK_LABEL,
        )
        with work_surface("writing_desk_work_material"):
            for section in WORK_MATERIAL_SECTIONS:
                st.markdown(f"**{section}**")

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
