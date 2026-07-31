"""Közös, újrahasználható UI-komponensek a Premium UX 2.0-hoz."""

from __future__ import annotations

from contextlib import contextmanager
from html import escape
from typing import Iterator

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


def render_work_section(
    *,
    title: str,
    body: str = "",
    context: str = "",
    show_rule: bool = False,
) -> None:
    """Munkaszakasz fejléc: kis kontextuscímke, kompakt cím + magyarázat egy sorban.

    Nem teljes kártya — csak hierarchikus nyitóblokk a feladat előtt.
    A cím és a rövid leírás egy lead-sorban ül (szűk képernyőn tördelve).
    """
    ctx = escape((context or "").strip())
    ttl = escape((title or "").strip())
    txt = escape((body or "").strip())
    if not ttl and not txt:
        return
    ctx_html = f'<div class="tx-work-section-context">{ctx}</div>' if ctx else ""
    title_html = (
        f'<div class="tx-work-section-title" role="heading" aria-level="2">{ttl}</div>'
        if ttl
        else ""
    )
    body_html = f'<p class="tx-work-section-body">{txt}</p>' if txt else ""
    lead_html = (
        f'<div class="tx-work-section-lead">{title_html}{body_html}</div>'
        if title_html or body_html
        else ""
    )
    rule_html = '<hr class="tx-work-section-rule" />' if show_rule else ""
    st.markdown(
        (
            '<section class="tx-work-section">'
            f"{ctx_html}"
            f"{lead_html}"
            f"{rule_html}"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


@contextmanager
def work_surface(key: str) -> Iterator[None]:
    """Egy feladat = egy emelt munkafelület (keyed CSS panel)."""
    safe = (key or "main").strip().replace(" ", "_")
    with st.container(key=f"tx_work_surface_{safe}"):
        yield


@contextmanager
def action_row(key: str) -> Iterator[None]:
    """Elsődleges / másodlagos gombok a munkafelület alján."""
    safe = (key or "actions").strip().replace(" ", "_")
    with st.container(key=f"tx_action_row_{safe}"):
        yield


@contextmanager
def mi_helper_zone(
    key: str,
    *,
    title: str = "MI-segéd",
    body: str = "",
) -> Iterator[None]:
    """Halk MI/helper zóna: rövid cím + leírás, alatta műveletek."""
    safe = (key or "mi").strip().replace(" ", "_")
    ttl = escape((title or "").strip())
    txt = escape((body or "").strip())
    with st.container(key=f"tx_mi_helper_{safe}"):
        if ttl:
            st.markdown(f'<div class="tx-mi-title">{ttl}</div>', unsafe_allow_html=True)
        if txt:
            st.markdown(f'<div class="tx-mi-body">{txt}</div>', unsafe_allow_html=True)
        yield


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
    """Egységes helper/státusz sáv: bal hangsúlycsík, rövid cím + max 2–3 sor."""
    safe_tone = tone if tone in {"info", "success", "warning", "danger", "neutral"} else "info"
    ttl = escape((title or "").strip())
    txt = escape((body or "").strip())
    if not ttl and not txt:
        return
    ttl_html = f'<div class="tx-panel-title">{ttl}</div>' if ttl else ""
    body_html = f'<div class="tx-panel-body">{txt}</div>' if txt else ""
    st.markdown(
        (
            f'<section class="tx-panel tx-helper tx-panel-{safe_tone} tx-helper-{safe_tone}">'
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


__all__ = [
    "action_row",
    "mi_helper_zone",
    "render_context_summary",
    "render_empty_state",
    "render_info_panel",
    "render_page_intro",
    "render_status_badge",
    "render_work_section",
    "work_surface",
]
