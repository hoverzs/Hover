"""Közös, újrahasználható UI-komponensek a Premium UX 2.0-hoz."""

from __future__ import annotations

from html import escape

import streamlit as st


def render_page_intro(
    *,
    title: str,
    body: str = "",
    eyebrow: str = "",
    workspace_scope: bool = False,
) -> None:
    """Egységes oldalbevezető: opcionális eyebrow + cím + rövid leírás.

    Ha `workspace_scope=True`, a tartalom a `workspace_intro` kulcsú
    konténerbe kerül (kompakt tipográfia CSS-sel).
    """
    eb = escape((eyebrow or "").strip())
    ttl = escape((title or "").strip())
    txt = escape((body or "").strip())
    if not ttl and not txt:
        return
    # Workspace intros omit eyebrows even if a caller passes one.
    if workspace_scope:
        eb = ""
    eyebrow_html = f'<div class="tx-intro-eyebrow">{eb}</div>' if eb else ""
    body_html = f'<div class="tx-intro-body">{txt}</div>' if txt else ""
    markup = (
        '<section class="tx-page-intro">'
        f"{eyebrow_html}"
        f'<h1 class="tx-intro-title">{ttl}</h1>'
        f"{body_html}"
        "</section>"
    )
    if workspace_scope:
        with st.container(key="workspace_intro"):
            st.markdown(markup, unsafe_allow_html=True)
    else:
        st.markdown(markup, unsafe_allow_html=True)


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


def render_context_summary(items: list[tuple[str, str]]) -> None:
    """Kompakt kontextussor: címke–érték párok egyetlen rendezett blokkban.

    Nem három különálló, félkövér szövegsor, hanem egy visszafogott
    ContextSummary sáv (pl. Igehely · Fő gondolat · Jóváhagyott felismerések).
    """
    rows = [
        (escape(str(k).strip()), escape(str(v).strip()))
        for k, v in items
        if str(k).strip()
    ]
    if not rows:
        return
    inner = "".join(
        f'<span class="tx-context-item"><span class="k">{k}:</span>'
        f'<span class="v">{v or "—"}</span></span>'
        for k, v in rows
    )
    st.markdown(f'<div class="tx-context">{inner}</div>', unsafe_allow_html=True)


def render_empty_state(
    *,
    title: str,
    body: str = "",
) -> None:
    """Rövid, emberi üres állapot."""
    render_info_panel(title=title, body=body, tone="neutral")

