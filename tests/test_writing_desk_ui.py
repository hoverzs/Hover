"""Íróasztal shell + RÚF / eredeti nyelvi olvasóblokk tesztek."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

from streamlit.testing.v1 import AppTest

import writing_desk_ui
from writing_desk_ui import (
    WRITING_DESK_BIBLE_VIEW_KEY,
    WRITING_DESK_LABEL,
    WRITING_DESK_MODE,
    WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX,
)


def _patch_streamlit_shell(monkeypatch, st, session: dict | None = None) -> dict[str, list]:
    calls: dict[str, list] = {
        "columns": [],
        "markdown": [],
        "caption": [],
        "radio": [],
    }
    monkeypatch.setattr(st, "session_state", session if session is not None else {})
    monkeypatch.setattr(st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        st,
        "caption",
        lambda body, *args, **kwargs: calls["caption"].append(str(body)),
    )

    def _columns(spec, *args, **kwargs):
        calls["columns"].append((spec, kwargs.get("gap")))
        n = spec if isinstance(spec, int) else len(spec)
        return [nullcontext() for _ in range(n)]

    def _markdown(body, *args, **kwargs):
        calls["markdown"].append(str(body))

    def _radio(label, options, *args, **kwargs):
        calls["radio"].append(kwargs.get("key"))
        return options[0]

    monkeypatch.setattr(st, "columns", _columns)
    monkeypatch.setattr(st, "markdown", _markdown)
    monkeypatch.setattr(st, "radio", _radio)
    return calls


def _joined_markdown(calls: dict[str, list]) -> str:
    return "\n".join(calls["markdown"])


def test_writing_desk_shell_keeps_two_column_workspace(monkeypatch):
    import streamlit as st

    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st)

    writing_desk_ui.render_writing_desk_shell()

    joined = _joined_markdown(calls)
    assert calls["columns"] == [([1, 2.4], "large")]
    assert "Íróasztal" in joined
    assert "Munkaanyag" in joined
    assert "Jegyzet / vázlat" in joined
    assert "Eredeti szöveg" in joined
    assert "Kortörténet" in joined
    assert "Teológia" in joined
    assert "A jegyzet- és vázlatszerkesztő a következő fázisban kerül ide." in joined


def test_writing_desk_renders_ruf_reading_block(monkeypatch):
    import streamlit as st

    import bible_text_ui

    ruf_texts: list[str] = []
    ruf_view_keys: list[str | None] = []
    orig_calls: list[dict] = []

    def _capture_ruf(text, **kwargs):
        ruf_texts.append(str(text))
        ruf_view_keys.append(kwargs.get("view_key"))

    monkeypatch.setattr(
        bible_text_ui,
        "render_formatted_bible_text",
        _capture_ruf,
    )
    monkeypatch.setattr(
        bible_text_ui,
        "render_greek_analysis_block",
        lambda **kwargs: orig_calls.append(kwargs),
    )

    session = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16. Mert úgy szerette Isten a világot.",
        "bible_translation": "RÚF 2014",
    }
    calls = _patch_streamlit_shell(monkeypatch, st, session)

    writing_desk_ui.render_writing_desk_shell()

    assert ruf_texts == ["16. Mert úgy szerette Isten a világot."]
    assert ruf_view_keys == [WRITING_DESK_BIBLE_VIEW_KEY]
    assert orig_calls[0]["reference"] == "Jn 3,16"
    assert orig_calls[0]["key_prefix"] == WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    assert orig_calls[0]["display_mode"] == "compact"
    joined = _joined_markdown(calls)
    assert "Jn 3,16" in joined
    assert "RÚF 2014" in joined
    assert "Munkaanyag" in joined


def test_writing_desk_nt_routes_to_greek_not_hebrew(monkeypatch):
    import streamlit as st

    import bible_engine.greek_analysis_ui as greek_analysis_ui
    import hebrew_text_demo

    greek_refs: list[str] = []
    hebrew_calls: list[tuple] = []

    monkeypatch.setattr(
        greek_analysis_ui,
        "load_greek_passage_tokens",
        lambda reference: greek_refs.append(reference) or [],
    )
    monkeypatch.setattr(
        hebrew_text_demo,
        "render_hebrew_original_language_reference",
        lambda *args, **kwargs: hebrew_calls.append((args, kwargs)),
    )

    session = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16. Mert úgy szerette Isten a világot.",
    }
    calls = _patch_streamlit_shell(monkeypatch, st, session)

    writing_desk_ui.render_writing_desk_shell()

    assert greek_refs == ["Jn 3,16"]
    assert hebrew_calls == []
    assert WRITING_DESK_BIBLE_VIEW_KEY in calls["radio"]
    assert "Munkaanyag" in _joined_markdown(calls)


def test_writing_desk_ot_routes_to_hebrew_not_greek(monkeypatch):
    import streamlit as st

    import bible_engine.greek_analysis_ui as greek_analysis_ui
    import hebrew_text_demo

    greek_refs: list[str] = []
    hebrew_calls: list[tuple] = []

    monkeypatch.setattr(
        greek_analysis_ui,
        "load_greek_passage_tokens",
        lambda reference: greek_refs.append(reference) or [],
    )

    def _hebrew(reference, *, key_prefix, **kwargs):
        hebrew_calls.append((reference, key_prefix, kwargs.get("display_mode")))

    monkeypatch.setattr(
        hebrew_text_demo,
        "render_hebrew_original_language_reference",
        _hebrew,
    )

    session = {
        "last_igehely": "Zsolt 23,1",
        "passage_text": "1. Az Úr az én pásztorom.",
    }
    calls = _patch_streamlit_shell(monkeypatch, st, session)

    writing_desk_ui.render_writing_desk_shell()

    assert greek_refs == []
    assert hebrew_calls == [
        ("Zsolt 23,1", WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX, "compact")
    ]
    assert "Munkaanyag" in _joined_markdown(calls)
    assert "Jegyzet / vázlat" in _joined_markdown(calls)


def test_missing_ruf_with_reference_still_renders_original_language(monkeypatch):
    import streamlit as st

    import bible_text_ui

    orig_calls: list[dict] = []
    monkeypatch.setattr(
        bible_text_ui,
        "render_formatted_bible_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("empty RÚF text should not be formatted")
        ),
    )
    monkeypatch.setattr(
        bible_text_ui,
        "render_greek_analysis_block",
        lambda **kwargs: orig_calls.append(kwargs),
    )

    calls = _patch_streamlit_shell(
        monkeypatch,
        st,
        {"last_igehely": "Jn 3,16", "passage_text": ""},
    )
    writing_desk_ui.render_writing_desk_shell()

    assert orig_calls[0]["reference"] == "Jn 3,16"
    assert orig_calls[0]["key_prefix"] == WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    assert orig_calls[0]["display_mode"] == "compact"
    assert any("Még nincs RÚF szöveg" in caption for caption in calls["caption"])
    assert "Munkaanyag" in _joined_markdown(calls)
    assert "Jegyzet / vázlat" in _joined_markdown(calls)


def test_missing_ruf_or_original_language_does_not_block_shell(monkeypatch):
    import streamlit as st

    calls = _patch_streamlit_shell(monkeypatch, st, {})
    writing_desk_ui.render_writing_desk_shell()

    joined = _joined_markdown(calls)
    assert "Munkaanyag" in joined
    assert "Jegyzet / vázlat" in joined
    assert "Teológia" in joined
    assert any("Nincs megadott igehely" in caption for caption in calls["caption"])

    def _boom(*args, **kwargs):
        raise RuntimeError("scripture unavailable")

    monkeypatch.setattr(writing_desk_ui, "render_bible_text_reading_block", _boom)
    failing = _patch_streamlit_shell(
        monkeypatch,
        st,
        {"last_igehely": "Jn 3,16", "passage_text": "16. szöveg"},
    )
    writing_desk_ui.render_writing_desk_shell()
    failed_joined = _joined_markdown(failing)
    assert "Munkaanyag" in failed_joined
    assert "Jegyzet / vázlat" in failed_joined
    assert "A bibliai szöveg most nem jeleníthető meg" in failed_joined


def test_writing_desk_uses_unique_original_language_widget_keys():
    src = Path(writing_desk_ui.__file__).read_text(encoding="utf-8")
    assert WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX == "writing_desk_original_language"
    assert WRITING_DESK_BIBLE_VIEW_KEY == "writing_desk_bible_text_view_mode"
    assert "bible_text_ui" not in WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    assert "textus_original_language" not in src
    assert 'key_prefix="bible_text_ui"' not in src
    assert "render_bible_text_editor" not in src
    assert "generate_text" not in src
    assert 'display_mode="compact"' in src

    app_src = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    assert 'display_mode="compact"' not in app_src


def test_writing_desk_shell_does_not_define_project_persistence():
    from workspace_data import EXCLUDED_SESSION_KEYS, PROJECT_DATA_KEYS

    assert "ui_mode" in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_MODE not in PROJECT_DATA_KEYS
    assert "writing_desk" not in PROJECT_DATA_KEYS
    assert WRITING_DESK_LABEL == "Íróasztal"


def _render_writing_desk_john_compact() -> None:
    import streamlit as st

    from bible_engine.greek_analysis_ui import load_john_3_16_tokens
    import bible_engine.greek_analysis_ui as greek_ui

    real_panel = greek_ui._render_analysis_panel
    real_loader = greek_ui.load_greek_passage_tokens
    real_tbesg = greek_ui.load_tbesg_lexicon_entry
    real_factory = st.components.v2.component

    def spy_panel(selected, lexicon_entries, tbesg_lexicon_loader, *, key_prefix, display_mode="full"):
        st.session_state["_writing_desk_analysis_display_mode"] = display_mode
        st.session_state["_writing_desk_analysis_key_prefix"] = key_prefix
        st.session_state["_writing_desk_analysis_form"] = selected.greek_form
        return real_panel(
            selected,
            lexicon_entries,
            tbesg_lexicon_loader,
            key_prefix=key_prefix,
            display_mode=display_mode,
        )

    def spy_factory(name, **kwargs):
        renderer = real_factory(name, **kwargs)

        def mounted(*args, **mount_kwargs):
            if name == "greek_token_selector":
                st.session_state["_writing_desk_token_selector_key"] = mount_kwargs.get("key")
            return renderer(*args, **mount_kwargs)

        return mounted

    greek_ui.load_greek_passage_tokens = lambda reference: load_john_3_16_tokens()
    greek_ui.load_tbesg_lexicon_entry = lambda _strong_id: None
    greek_ui._render_analysis_panel = spy_panel
    st.components.v2.component = spy_factory
    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["passage_text"] = "16. Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"
    import writing_desk_ui
    try:
        writing_desk_ui.render_writing_desk_shell()
    finally:
        greek_ui.load_greek_passage_tokens = real_loader
        greek_ui.load_tbesg_lexicon_entry = real_tbesg
        greek_ui._render_analysis_panel = real_panel
        st.components.v2.component = real_factory


def _render_writing_desk_ot_compact() -> None:
    import streamlit as st

    real_factory = st.components.v2.component

    def spy_factory(name, **kwargs):
        renderer = real_factory(name, **kwargs)

        def mounted(*args, **mount_kwargs):
            if name == "hebrew_token_selector":
                st.session_state["_writing_desk_hebrew_token_selector_key"] = mount_kwargs.get(
                    "key"
                )
            return renderer(*args, **mount_kwargs)

        return mounted

    st.components.v2.component = spy_factory
    st.session_state["last_igehely"] = "Zsolt 23,1"
    st.session_state["passage_text"] = "1. Az Úr az én pásztorom."
    import writing_desk_ui
    try:
        writing_desk_ui.render_writing_desk_shell()
    finally:
        st.components.v2.component = real_factory


def _page_text(app: AppTest) -> str:
    text = "\n".join(markdown.value for markdown in app.markdown)
    text += "\n".join(caption.value for caption in app.caption)
    return text


def test_writing_desk_compact_reaches_real_greek_analysis_panel() -> None:
    app = AppTest.from_function(_render_writing_desk_john_compact).run()

    assert not app.exception
    assert app.session_state["_writing_desk_analysis_display_mode"] == "compact"
    assert (
        app.session_state["_writing_desk_analysis_key_prefix"]
        == WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    )
    page_text = _page_text(app)
    assert "textus-greek-compact-card-marker" in page_text
    assert "Magyar lexikai jelentések" not in page_text
    assert "Ellenőrzési állapot" not in page_text
    assert "Konkordancia" not in page_text
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)


def test_writing_desk_token_selector_uses_isolated_stable_key() -> None:
    app = AppTest.from_function(_render_writing_desk_john_compact).run()

    assert not app.exception
    assert (
        app.session_state["_writing_desk_token_selector_key"]
        == f"{WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX}_inline_token_selector"
    )
    assert "bible_text_ui" not in app.session_state["_writing_desk_token_selector_key"]
    assert "textus_original_language" not in app.session_state["_writing_desk_token_selector_key"]


def test_writing_desk_token_selection_reaches_compact_analysis_panel() -> None:
    from bible_engine.greek_analysis_ui import load_john_3_16_tokens

    app = AppTest.from_function(_render_writing_desk_john_compact).run()
    assert not app.exception
    assert "οὕτως" in (app.session_state["_writing_desk_analysis_form"] or "")

    tokens = load_john_3_16_tokens()
    chosen = next(token for token in tokens if token.word_index == 3)
    app.session_state[f"{WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX}_selected_token_key"] = (
        f"{chosen.book}:{chosen.chapter}:{chosen.verse}:{chosen.word_index}"
    )
    app.run()

    assert not app.exception
    assert app.session_state["_writing_desk_analysis_form"] == chosen.greek_form
    assert app.session_state["_writing_desk_analysis_display_mode"] == "compact"
    page_text = _page_text(app)
    assert chosen.greek_form in page_text
    assert "Magyar lexikai jelentések" not in page_text
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)


def test_writing_desk_hebrew_compact_path_keeps_isolated_key() -> None:
    app = AppTest.from_function(_render_writing_desk_ot_compact).run()

    assert not app.exception
    assert (
        app.session_state["_writing_desk_hebrew_token_selector_key"]
        == f"{WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX}_inline_token_selector"
    )
    page_text = _page_text(app)
    assert "textus-hebrew-compact-card-marker" in page_text
    assert "Technikai morfológiai részletek" not in page_text
    assert "Forrás és licenc" not in page_text
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)
