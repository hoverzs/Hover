"""Íróasztal fő munkafelület — v1 shell.

Ez a modul egyelőre csak a harmadik fő nézet üres, stabil vázát rendereli.
Nem olvas/ír projektadatot, nem indít AI-hívást, és nem valósít meg editort.
"""

from __future__ import annotations

import streamlit as st

from ui_components import (
    render_info_panel,
    render_page_intro,
    render_work_section,
    work_surface,
)


WRITING_DESK_MODE = "writing_desk"
WRITING_DESK_LABEL = "Íróasztal"
WORK_MATERIAL_SECTIONS: tuple[str, ...] = (
    "Eredeti szöveg",
    "Kortörténet",
    "Teológia",
)


def render_writing_desk_shell() -> None:
    """Rendereli az Íróasztal üres, később bővíthető munkafelületét."""
    render_page_intro(
        title=WRITING_DESK_LABEL,
        body="Jegyzetelés és vázlatkészítés az aktuális projekthez.",
        workspace_scope=True,
    )

    render_work_section(
        title="Bibliai szöveg és eredeti nyelv",
        body="A RÚF szöveg és az eredeti nyelvi blokk későbbi fázisban kerül ide.",
        context=WRITING_DESK_LABEL,
    )
    with work_surface("writing_desk_scripture_placeholder"):
        render_info_panel(
            title="Szövegterület előkészítve",
            body="Itt jelenik majd meg a RÚF bibliai szöveg és az eredeti szöveg rövid elemzése.",
            tone="neutral",
        )

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
    "WRITING_DESK_LABEL",
    "WRITING_DESK_MODE",
    "render_writing_desk_shell",
]
