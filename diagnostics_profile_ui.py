"""Homiletikai profil megjelenítése (radar chart opcionális, natív fallback).

A modul szándékosan különálló, hogy a diagnosztikai fő UI (sermon_workshop_ui)
független maradjon az opcionális vizualizációs függőségtől. Ha a chart-könyvtár
nem elérhető vagy hibázik, elegáns vízszintes állapotsávokra esik vissza.
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st


def render_profile_bars(rows: list[dict[str, Any]]) -> None:
    """Elegáns, vízszintes állapotsávok — könyvtárfüggetlen natív megoldás.

    Minden sor tartalmazza a terület nevét, a vizuális szintet és a szöveges
    státuszt (a szín mellett mindig van szöveges címke — hozzáférhetőség).
    """
    blocks: list[str] = ['<div class="tx-profile">']
    for r in rows:
        val = r.get("value")
        pct = int((val / 4) * 100) if isinstance(val, int) else 0
        fill = (
            f'<div class="tx-profile-fill" style="width:{pct}%;'
            f'background:{r.get("color", "#8a8580")};"></div>'
            if pct
            else ""
        )
        blocks.append(
            '<div class="tx-profile-row">'
            '<div class="tx-profile-head">'
            f'<span class="tx-profile-name">{html.escape(str(r.get("label", "")))}</span>'
            f'<span class="tx-profile-status">'
            f'{html.escape(str(r.get("status_label", "")))}</span>'
            "</div>"
            f'<div class="tx-profile-track">{fill}</div>'
            "</div>"
        )
    blocks.append("</div>")
    st.markdown("".join(blocks), unsafe_allow_html=True)


def render_profile_chart(rows: list[dict[str, Any]]) -> None:
    """Radar/polar chart, ha a vizualizációs könyvtár elérhető; különben sávok."""
    try:
        import plotly.graph_objects as go  # type: ignore
    except Exception:
        render_profile_bars(rows)
        return

    try:
        labels = [str(r.get("label", "")) for r in rows]
        values = [r.get("value") if isinstance(r.get("value"), int) else 0 for r in rows]
        status_labels = [str(r.get("status_label", "")) for r in rows]
        labels_c = labels + labels[:1]
        values_c = values + values[:1]
        status_c = status_labels + status_labels[:1]

        fig = go.Figure()
        fig.add_trace(
            go.Scatterpolar(
                r=values_c,
                theta=labels_c,
                fill="toself",
                fillcolor="rgba(90, 122, 168, 0.22)",
                line=dict(color="#5a7aa8", width=2),
                marker=dict(color="#b38a4e", size=6),
                customdata=status_c,
                hovertemplate="%{theta}: %{customdata}<extra></extra>",
            )
        )
        fig.update_layout(
            polar=dict(
                bgcolor="rgba(255,252,247,0.4)",
                radialaxis=dict(
                    visible=True,
                    range=[0, 4],
                    showticklabels=False,
                    ticks="",
                    gridcolor="rgba(160,140,115,0.35)",
                ),
                angularaxis=dict(
                    tickfont=dict(size=11, color="#3d3228"),
                    gridcolor="rgba(160,140,115,0.30)",
                ),
            ),
            showlegend=False,
            margin=dict(l=40, r=40, t=30, b=30),
            height=360,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception:
        render_profile_bars(rows)
