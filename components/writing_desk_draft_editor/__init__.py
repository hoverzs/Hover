"""Íróasztal jegyzet/vázlat — minimalista CCv2 rich-text editor."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import streamlit as st


_COMPONENT_DIR = Path(__file__).parent
_FRONTEND_DIR = _COMPONENT_DIR / "frontend"
_COMPONENT_NAME = "writing_desk_draft_editor"
_HTML = (_FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
_CSS = (_FRONTEND_DIR / "style.css").read_text(encoding="utf-8")
_JS = (_FRONTEND_DIR / "main.js").read_text(encoding="utf-8")


def _noop() -> None:
    return None


def _component():
    """A CCv2 definíciót az aktív Streamlit runtime registryjébe teszi.

    A HTML/CSS/JS modulszinten egyszer töltődik. A `component()` hívás a
    mountkor történik, mert az AppTest saját registryt használ, és az
    import idején (vagy egy előző AppTestben) regisztrált callable ott
    nem látszik.
    """
    return st.components.v2.component(
        _COMPONENT_NAME,
        html=_HTML,
        css=_CSS,
        js=_JS,
    )


def writing_desk_draft_editor(
    *,
    html: str,
    revision: int,
    key: str,
    on_html_change: Callable[[], None] | None = None,
    height: int = 400,
):
    """Jegyzetmező: contenteditable + szűkített HTML state (`html`)."""
    return _component()(
        data={"html": html or "", "revision": int(revision or 0)},
        default={"html": html or ""},
        key=key,
        height=height,
        width="stretch",
        on_html_change=on_html_change or _noop,
    )


__all__ = ["writing_desk_draft_editor"]
