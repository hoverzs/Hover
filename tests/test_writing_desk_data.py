"""Íróasztal munkakivonatok — projektadat mentés/betöltés, LLM nélkül."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
)
from textus_workshop_data import (
    TEXT_WORKSHOP_KEY,
    ensure_text_workshop_state,
)
from workspace_data import (
    PROJECT_DATA_KEYS,
    PROJECT_NESTED_KEYS,
    build_project_data,
    project_content_fingerprint,
    sanitize_project_data,
    sanitize_project_data_report,
)
from writing_desk_data import (
    WRITING_DESK_EXTRACT_KEYS,
    WRITING_DESK_KEY,
    ensure_writing_desk_state,
    fingerprint_source_text,
    get_default_writing_desk,
    normalize_writing_desk,
    set_writing_desk_extract,
    writing_desk_has_content,
)


ROOT = Path(__file__).resolve().parents[1]


def _filled_extracts() -> dict[str, Any]:
    return {
        "extracts": {
            "original_text": {
                "content": "Rövid eredeti-szöveg kivonat",
                "source_fingerprint": fingerprint_source_text("TELJES eredeti"),
            },
            "history": {
                "content": "Rövid kortörténeti kivonat",
                "source_fingerprint": fingerprint_source_text("TELJES kortörténet"),
            },
            "theology": {
                "content": "Rövid teológiai kivonat",
                "source_fingerprint": fingerprint_source_text("TELJES teológia"),
            },
        }
    }


def _apply_writing_desk_like_app(
    session: dict[str, Any], project_data: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Ugyanaz a lépés, mint app._apply_project_data_to_session writing_desk ága."""
    raw = None
    if isinstance(project_data, Mapping):
        raw = project_data.get(WRITING_DESK_KEY)
    session[WRITING_DESK_KEY] = normalize_writing_desk(raw)
    return ensure_writing_desk_state(session)


def _stub_app_session(monkeypatch, session: dict[str, Any]):
    import app as app_mod

    monkeypatch.setattr(app_mod.st, "session_state", session)
    monkeypatch.setattr(app_mod, "_reset_language_grounding_warnings", lambda: None)
    monkeypatch.setattr(app_mod, "_queue_project_widget_sync_from_state", lambda: None)
    return app_mod


def test_data_module_has_no_llm_or_ui_imports():
    src = (ROOT / "writing_desk_data.py").read_text(encoding="utf-8")
    assert "streamlit" not in src
    assert "google" not in src.casefold()
    assert "gemini" not in src.casefold()
    assert "supabase" not in src.casefold()
    assert "generate_text" not in src
    assert "docx" not in src.casefold()


def test_new_project_gets_empty_writing_desk_extracts():
    session: dict[str, Any] = {}
    desk = ensure_writing_desk_state(session)
    assert session[WRITING_DESK_KEY] is desk
    assert set(desk["extracts"]) == set(WRITING_DESK_EXTRACT_KEYS)
    for key in WRITING_DESK_EXTRACT_KEYS:
        assert desk["extracts"][key] == {"content": "", "source_fingerprint": ""}
    assert not writing_desk_has_content(desk)

    payload = build_project_data(session)
    assert payload[WRITING_DESK_KEY] == get_default_writing_desk()


def test_legacy_project_without_writing_desk_normalizes():
    assert normalize_writing_desk(None) == get_default_writing_desk()
    assert normalize_writing_desk("rossz") == get_default_writing_desk()
    assert normalize_writing_desk({"extracts": None}) == get_default_writing_desk()

    old = sanitize_project_data({"last_igehely": "Jn 3,16"})
    assert WRITING_DESK_KEY in old
    assert old[WRITING_DESK_KEY] == get_default_writing_desk()
    assert old["last_igehely"] == "Jn 3,16"

    session: dict[str, Any] = {"last_igehely": "Jn 3,16"}
    _apply_writing_desk_like_app(session, {"last_igehely": "Jn 3,16"})
    assert session[WRITING_DESK_KEY] == get_default_writing_desk()


def test_malformed_extracts_are_normalized_without_error():
    raw = {
        "extracts": {
            "original_text": "sima szöveg",
            "history": {"content": 12, "source_fingerprint": None, "extra": True},
            "unknown_section": {"content": "eldobandó"},
        },
        "extra_top": True,
    }
    desk = normalize_writing_desk(raw)
    assert set(desk.keys()) == {"extracts"}
    assert set(desk["extracts"]) == set(WRITING_DESK_EXTRACT_KEYS)
    assert desk["extracts"]["original_text"] == {
        "content": "",
        "source_fingerprint": "",
    }
    assert desk["extracts"]["history"]["content"] == "12"
    assert desk["extracts"]["history"]["source_fingerprint"] == ""
    assert "extra" not in desk["extracts"]["history"]
    assert "unknown_section" not in desk["extracts"]
    assert desk["extracts"]["theology"] == {
        "content": "",
        "source_fingerprint": "",
    }


def test_three_extracts_save_and_reload():
    session: dict[str, Any] = {
        "original_text": "TELJES eredeti",
        "history": "TELJES kortörténet",
        "theology": "TELJES teológia",
        WRITING_DESK_KEY: _filled_extracts(),
    }
    payload = build_project_data(session, version="2.0-test")
    extracts = payload[WRITING_DESK_KEY]["extracts"]
    assert extracts["original_text"]["content"] == "Rövid eredeti-szöveg kivonat"
    assert extracts["history"]["content"] == "Rövid kortörténeti kivonat"
    assert extracts["theology"]["content"] == "Rövid teológiai kivonat"

    cleaned = sanitize_project_data(payload)
    reloaded: dict[str, Any] = {}
    _apply_writing_desk_like_app(reloaded, cleaned)
    roundtrip = reloaded[WRITING_DESK_KEY]["extracts"]
    assert roundtrip["original_text"]["content"] == "Rövid eredeti-szöveg kivonat"
    assert roundtrip["history"]["content"] == "Rövid kortörténeti kivonat"
    assert roundtrip["theology"]["content"] == "Rövid teológiai kivonat"


def test_source_fingerprint_survives_save_and_reload():
    source = "TELJES kortörténet\r\nmásodik sor"
    fp = fingerprint_source_text(source)
    assert fp == hashlib.sha256("TELJES kortörténet\nmásodik sor".encode("utf-8")).hexdigest()
    assert fingerprint_source_text("TELJES kortörténet\nmásodik sor") == fp
    assert fingerprint_source_text("   ") == ""
    assert fingerprint_source_text("") == ""

    session: dict[str, Any] = {}
    set_writing_desk_extract(
        session,
        "history",
        content="rövid",
        source_fingerprint=fp,
    )
    payload = build_project_data(session)
    cleaned = sanitize_project_data(payload)
    assert (
        cleaned[WRITING_DESK_KEY]["extracts"]["history"]["source_fingerprint"] == fp
    )

    reloaded: dict[str, Any] = {}
    _apply_writing_desk_like_app(reloaded, cleaned)
    assert (
        reloaded[WRITING_DESK_KEY]["extracts"]["history"]["source_fingerprint"] == fp
    )


def test_save_as_inherits_writing_desk_from_current_session():
    session: dict[str, Any] = {
        "last_igehely": "Jn 3,16",
        "current_project_id": "old-id",
        WRITING_DESK_KEY: _filled_extracts(),
    }
    # Mentés újként: create_project(owner, title, passage, build_project_data_from_state)
    new_payload = build_project_data(session, version="2.0-test")
    assert new_payload[WRITING_DESK_KEY]["extracts"]["theology"]["content"] == (
        "Rövid teológiai kivonat"
    )
    assert new_payload[WRITING_DESK_KEY]["extracts"]["history"][
        "source_fingerprint"
    ] == fingerprint_source_text("TELJES kortörténet")

    opened: dict[str, Any] = {"current_project_id": "new-id"}
    _apply_writing_desk_like_app(opened, new_payload)
    assert opened[WRITING_DESK_KEY]["extracts"]["original_text"]["content"] == (
        "Rövid eredeti-szöveg kivonat"
    )


def test_project_switch_does_not_leak_extracts(monkeypatch):
    session: dict[str, Any] = {
        "last_igehely": "Jn 3,16",
        WRITING_DESK_KEY: _filled_extracts(),
    }
    project_a = build_project_data(session)

    app_mod = _stub_app_session(monkeypatch, session)
    app_mod._apply_project_data_to_session({"last_igehely": "Zsolt 23,1"})
    assert session["last_igehely"] == "Zsolt 23,1"
    for key in WRITING_DESK_EXTRACT_KEYS:
        assert session[WRITING_DESK_KEY]["extracts"][key]["content"] == ""
        assert session[WRITING_DESK_KEY]["extracts"][key]["source_fingerprint"] == ""

    app_mod._apply_project_data_to_session(project_a)
    assert (
        session[WRITING_DESK_KEY]["extracts"]["history"]["content"]
        == "Rövid kortörténeti kivonat"
    )


def test_clear_workspace_resets_writing_desk(monkeypatch):
    session: dict[str, Any] = {WRITING_DESK_KEY: _filled_extracts()}
    app_mod = _stub_app_session(monkeypatch, session)
    app_mod._clear_workspace_content()
    assert session[WRITING_DESK_KEY] == get_default_writing_desk()


def test_workspace_import_without_writing_desk_does_not_keep_previous_extracts(
    monkeypatch,
):
    session: dict[str, Any] = {WRITING_DESK_KEY: _filled_extracts()}
    app_mod = _stub_app_session(monkeypatch, session)
    raw = json.dumps(
        {"_app": "Textus", "last_igehely": "Róm 8,1"},
        ensure_ascii=False,
    ).encode("utf-8")
    ok, _info = app_mod.deserialize_workspace(raw)
    assert ok is True
    assert session[WRITING_DESK_KEY] == get_default_writing_desk()
    assert session["last_igehely"] == "Róm 8,1"


def test_text_workshop_and_sermon_workshop_and_source_fields_unchanged():
    session: dict[str, Any] = {
        "original_text": "TELJES eredeti forrás",
        "history": "TELJES kortörténeti forrás",
        "theology": "TELJES teológiai forrás",
        "last_igehely": "Jn 3,16",
    }
    ensure_text_workshop_state(session)
    ensure_sermon_workshop_state(session)
    session[TEXT_WORKSHOP_KEY]["text_main_idea"] = "A textus fő gondolata"
    session[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Az igehirdetés fő gondolata"
    set_writing_desk_extract(
        session,
        "original_text",
        content="rövid kivonat",
        source_fingerprint=fingerprint_source_text(session["original_text"]),
    )

    assert session["original_text"] == "TELJES eredeti forrás"
    assert session["history"] == "TELJES kortörténeti forrás"
    assert session["theology"] == "TELJES teológiai forrás"

    payload = build_project_data(session)
    cleaned = sanitize_project_data(payload)

    assert cleaned["original_text"] == "TELJES eredeti forrás"
    assert cleaned["history"] == "TELJES kortörténeti forrás"
    assert cleaned["theology"] == "TELJES teológiai forrás"
    assert cleaned[TEXT_WORKSHOP_KEY]["text_main_idea"] == "A textus fő gondolata"
    assert (
        cleaned[SERMON_WORKSHOP_KEY]["sermon_main_idea"]
        == "Az igehirdetés fő gondolata"
    )
    assert (
        cleaned[WRITING_DESK_KEY]["extracts"]["original_text"]["content"]
        == "rövid kivonat"
    )
    assert cleaned[WRITING_DESK_KEY]["extracts"]["original_text"]["content"] != (
        cleaned["original_text"]
    )


def test_sanitize_and_fingerprint_keep_writing_desk():
    assert WRITING_DESK_KEY in PROJECT_NESTED_KEYS
    assert WRITING_DESK_KEY in PROJECT_DATA_KEYS

    filled = _filled_extracts()
    report = sanitize_project_data_report(
        {
            "_app": "Textus",
            "last_igehely": "Jn 3,16",
            "api_key": "AIzaLEAK",
            "bogus": {"nested": True},
            WRITING_DESK_KEY: filled,
        }
    )
    assert "api_key" not in report.data
    assert "bogus" in report.dropped_keys
    assert WRITING_DESK_KEY in report.data
    assert (
        report.data[WRITING_DESK_KEY]["extracts"]["theology"]["content"]
        == "Rövid teológiai kivonat"
    )
    assert report.data[WRITING_DESK_KEY]["extracts"]["theology"][
        "source_fingerprint"
    ] == fingerprint_source_text("TELJES teológia")

    empty_fp = project_content_fingerprint({})
    with_extracts_fp = project_content_fingerprint({WRITING_DESK_KEY: filled})
    assert empty_fp != with_extracts_fp
    assert project_content_fingerprint({WRITING_DESK_KEY: filled}) == with_extracts_fp


def test_app_wires_writing_desk_into_save_load_and_clear_paths():
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    workspace_src = (ROOT / "workspace_data.py").read_text(encoding="utf-8")
    ui_src = (ROOT / "writing_desk_ui.py").read_text(encoding="utf-8")

    assert "ensure_writing_desk_state(st.session_state)" in app_src
    assert "normalize_writing_desk(" in app_src
    assert "get_default_writing_desk()" in app_src
    assert "WRITING_DESK_KEY" in app_src
    assert "payload[WRITING_DESK_KEY] = normalize_writing_desk" in workspace_src
    assert "clean[key_s] = normalize_writing_desk(nested)" in workspace_src

    assert "generate_text" not in ui_src
    assert "render_bible_text_editor" not in ui_src
    assert "autosave" not in ui_src.casefold()
    assert "docx" not in ui_src.casefold()
    assert "chat" not in ui_src.casefold()
    data_src = (ROOT / "writing_desk_data.py").read_text(encoding="utf-8")
    assert "generate_text" not in data_src
    assert "chat" not in data_src.casefold()
