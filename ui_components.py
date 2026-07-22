"""Közös, újrahasználható UI-komponensek a Premium UX 2.0-hoz."""

from __future__ import annotations

from html import escape

import streamlit as st


def render_page_intro(
    *,
    title: str,
    body: str = "",
    eyebrow: str = "",
) -> None:
    """Egységes oldalbevezető: eyebrow + cím + rövid leírás."""
    eb = escape((eyebrow or "").strip())
    ttl = escape((title or "").strip())
    txt = escape((body or "").strip())
    if not ttl and not txt:
        return
    eyebrow_html = f'<div class="tx-intro-eyebrow">{eb}</div>' if eb else ""
    body_html = f'<div class="tx-intro-body">{txt}</div>' if txt else ""
    st.markdown(
        (
            '<section class="tx-page-intro">'
            f"{eyebrow_html}"
            f'<h1 class="tx-intro-title">{ttl}</h1>'
            f"{body_html}"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_status_badge(label: str, tone: str = "neutral") -> None:
    """Rövid státuszbadge (neutral/success/warning/danger/info)."""
    safe_label = escape((label or "").strip())
    if not safe_label:
        return
    safe_tone = tone if tone in {"neutral", "success", "warning", "danger", "info"} else "neutral"
    st.markdown(
        f'<span class="tx-status-badge tx-status-{safe_tone}">{safe_label}</span>',
        unsafe_allow_html=True,
    )


def render_info_panel(
    *,
    title: str,
    body: str = "",
    tone: str = "info",
) -> None:
    """Egységes info/warn/success/error panel cím+törzs formában."""
    safe_tone = tone if tone in {"info", "success", "warning", "danger", "neutral"} else "info"
    ttl = escape((title or "").strip())
    txt = escape((body or "").strip())
    if not ttl and not txt:
        return
    ttl_html = f'<div class="tx-panel-title">{ttl}</div>' if ttl else ""
    body_html = f'<div class="tx-panel-body">{txt}</div>' if txt else ""
    st.markdown(
        (
            f'<section class="tx-panel tx-panel-{safe_tone}">'
            f"{ttl_html}"
            f"{body_html}"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_empty_state(
    *,
    title: str,
    body: str = "",
) -> None:
    """Rövid, emberi üres állapot."""
    render_info_panel(title=title, body=body, tone="neutral")

