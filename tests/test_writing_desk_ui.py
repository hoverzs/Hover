"""Íróasztal shell tesztek."""

from __future__ import annotations

from contextlib import nullcontext


def test_writing_desk_shell_renders_static_placeholder_layout(monkeypatch):
    import streamlit as st

    import writing_desk_ui

    calls: dict[str, list] = {
        "columns": [],
        "markdown": [],
    }

    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(
        st,
        "container",
        lambda *args, **kwargs: nullcontext(),
    )

    def _columns(spec, *args, **kwargs):
        calls["columns"].append((spec, kwargs.get("gap")))
        return [nullcontext(), nullcontext()]

    def _markdown(body, *args, **kwargs):
        calls["markdown"].append(str(body))

    monkeypatch.setattr(st, "columns", _columns)
    monkeypatch.setattr(st, "markdown", _markdown)

    writing_desk_ui.render_writing_desk_shell()

    joined = "\n".join(calls["markdown"])
    assert calls["columns"] == [([1, 2.4], "large")]
    assert "Íróasztal" in joined
    assert "Munkaanyag" in joined
    assert "Jegyzet / vázlat" in joined
    assert "Eredeti szöveg" in joined
    assert "Kortörténet" in joined
    assert "Teológia" in joined
    assert "A jegyzet- és vázlatszerkesztő a következő fázisban kerül ide." in joined


def test_writing_desk_shell_does_not_define_project_persistence():
    from workspace_data import EXCLUDED_SESSION_KEYS, PROJECT_DATA_KEYS
    from writing_desk_ui import WRITING_DESK_MODE

    assert "ui_mode" in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_MODE not in PROJECT_DATA_KEYS
    assert "writing_desk" not in PROJECT_DATA_KEYS
