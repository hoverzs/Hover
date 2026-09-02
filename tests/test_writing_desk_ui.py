"""Íróasztal shell + RÚF / eredeti nyelvi olvasóblokk tesztek."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

from streamlit.testing.v1 import AppTest

import writing_desk_ui
from writing_desk_ui import (
    WRITING_DESK_BIBLE_VIEW_KEY,
    WRITING_DESK_DRAFT_RESYNC_FLAG,
    WRITING_DESK_DRAFT_WIDGET_KEY,
    WRITING_DESK_LABEL,
    WRITING_DESK_MODE,
    WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX,
)


def _patch_streamlit_shell(
    monkeypatch,
    st,
    session: dict | None = None,
    *,
    click_key: str | None = None,
) -> dict[str, list]:
    calls: dict[str, list] = {
        "columns": [],
        "markdown": [],
        "caption": [],
        "radio": [],
        "buttons": [],
        "rerun": [],
        "text_area": [],
    }
    monkeypatch.setattr(st, "session_state", session if session is not None else {})
    monkeypatch.setattr(st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "spinner", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        st,
        "caption",
        lambda body, *args, **kwargs: calls["caption"].append(str(body)),
    )
    monkeypatch.setattr(
        st,
        "rerun",
        lambda *args, **kwargs: calls["rerun"].append(True),
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

    def _button(label, *args, **kwargs):
        key = kwargs.get("key")
        calls["buttons"].append((str(label), key))
        return bool(click_key) and key == click_key

    def _text_area(label, *args, **kwargs):
        key = kwargs.get("key")
        value = args[0] if args else kwargs.get("value")
        if key and key in st.session_state:
            value = st.session_state[key]
        elif value is None:
            value = ""
        if key is not None:
            st.session_state[key] = value
        calls["text_area"].append(
            {
                "label": str(label),
                "key": key,
                "value": value,
                "height": kwargs.get("height"),
                "placeholder": kwargs.get("placeholder"),
                "on_change": kwargs.get("on_change"),
            }
        )
        return value

    monkeypatch.setattr(st, "columns", _columns)
    monkeypatch.setattr(st, "markdown", _markdown)
    monkeypatch.setattr(st, "radio", _radio)
    monkeypatch.setattr(st, "button", _button)
    monkeypatch.setattr(st, "text_area", _text_area)
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
    assert "A jegyzet- és vázlatszerkesztő a következő fázisban kerül ide." not in joined
    assert "Szerkesztő helye" not in joined
    assert calls["text_area"]
    assert calls["text_area"][0]["key"] == WRITING_DESK_DRAFT_WIDGET_KEY
    assert calls["text_area"][0]["height"] == 400


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


def test_writing_desk_ui_mode_is_not_a_durable_session_key():
    from workspace_data import EXCLUDED_SESSION_KEYS, PROJECT_DATA_KEYS, PROJECT_NESTED_KEYS
    from writing_desk_data import WRITING_DESK_KEY

    assert "ui_mode" in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_DRAFT_WIDGET_KEY in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_DRAFT_RESYNC_FLAG in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_KEY in PROJECT_DATA_KEYS
    assert WRITING_DESK_KEY in PROJECT_NESTED_KEYS
    assert WRITING_DESK_KEY == WRITING_DESK_MODE
    assert WRITING_DESK_LABEL == "Íróasztal"


def test_notes_text_area_loads_existing_draft(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {}
    set_writing_desk_draft(session, "Meglévő vázlat\nmásodik sor")
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()

    assert calls["text_area"][0]["key"] == WRITING_DESK_DRAFT_WIDGET_KEY
    assert calls["text_area"][0]["value"] == "Meglévő vázlat\nmásodik sor"
    assert calls["text_area"][0]["on_change"] is writing_desk_ui._on_writing_desk_draft_change
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Meglévő vázlat\nmásodik sor"
    )
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == "Meglévő vázlat\nmásodik sor"


def test_notes_edit_updates_writing_desk_draft_and_survives_rerun(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY

    session: dict = {}
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""

    session[WRITING_DESK_DRAFT_WIDGET_KEY] = "Gépelt jegyzet\núj sor"
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "Gépelt jegyzet\núj sor"

    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "Gépelt jegyzet\núj sor"
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == "Gépelt jegyzet\núj sor"


def test_notes_widget_shows_new_project_draft_after_switch(monkeypatch):
    import streamlit as st

    from writing_desk_data import (
        WRITING_DESK_KEY,
        normalize_writing_desk,
        set_writing_desk_draft,
    )

    session: dict = {}
    set_writing_desk_draft(session, "Projekt A jegyzet")
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == "Projekt A jegyzet"

    session[WRITING_DESK_KEY] = normalize_writing_desk(
        {"draft": {"content": "Projekt B jegyzet"}}
    )
    session[WRITING_DESK_DRAFT_RESYNC_FLAG] = True
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == "Projekt B jegyzet"
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "Projekt B jegyzet"
    assert WRITING_DESK_DRAFT_RESYNC_FLAG not in session


def test_on_change_commit_updates_durable_draft_before_unmount(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_extract

    session: dict = {}
    set_writing_desk_extract(
        session,
        "history",
        content="Rövid kortörténeti kivonat.",
        source_fingerprint="abc",
    )
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()

    session[WRITING_DESK_DRAFT_WIDGET_KEY] = "Íróasztal jegyzet\n\nmásodik bekezdés"
    writing_desk_ui.commit_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
    assert (
        session[WRITING_DESK_KEY]["extracts"]["history"]["content"]
        == "Rövid kortörténeti kivonat."
    )

    session.pop(WRITING_DESK_DRAFT_WIDGET_KEY, None)
    assert WRITING_DESK_DRAFT_WIDGET_KEY not in session
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )

    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
    assert (
        session[WRITING_DESK_KEY]["extracts"]["history"]["content"]
        == "Rövid kortörténeti kivonat."
    )


def test_commit_skips_stale_widget_during_project_resync(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {
        WRITING_DESK_DRAFT_WIDGET_KEY: "Projekt A stale widget",
        WRITING_DESK_DRAFT_RESYNC_FLAG: True,
        "_pending_project_widget_sync": {
            WRITING_DESK_DRAFT_WIDGET_KEY: "Projekt B jegyzet",
        },
    }
    set_writing_desk_draft(session, "Projekt B jegyzet")
    monkeypatch.setattr(st, "session_state", session)

    writing_desk_ui.commit_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "Projekt B jegyzet"
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == "Projekt A stale widget"


def test_valid_extract_is_shown_and_does_not_call_llm(monkeypatch):
    import streamlit as st

    from writing_desk_data import fingerprint_source_text, set_writing_desk_extract

    session = {"history": "TELJES kortörténeti forrásanyag a projekthez."}
    set_writing_desk_extract(
        session,
        "history",
        content="Rövid, használható kortörténeti megállapítás.",
        source_fingerprint=fingerprint_source_text(session["history"]),
    )
    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    joined = _joined_markdown(calls)
    assert "Rövid, használható kortörténeti megállapítás." in joined
    assert "Kivonat készítése" not in [label for label, _key in calls["buttons"]]
    assert llm_calls == []
    assert calls["rerun"] == []


def test_missing_source_shows_cultural_empty_state_without_llm(monkeypatch):
    import streamlit as st

    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, {})
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    captions = "\n".join(calls["caption"])
    assert "Ehhez a projekthez még nincs elkészített eredeti szöveges elemzés." in captions
    assert "Ehhez a projekthez még nincs elkészített kortörténeti elemzés." in captions
    assert "Ehhez a projekthez még nincs elkészített teológiai elemzés." in captions
    assert calls["buttons"] == []
    assert llm_calls == []


def test_stale_extract_is_refreshable_and_not_shown_as_valid(monkeypatch):
    import streamlit as st

    from writing_desk_data import fingerprint_source_text, set_writing_desk_extract
    from writing_desk_extracts import STATUS_STALE, inspect_writing_desk_extract

    session = {"theology": "ÚJ teológiai forrásanyag."}
    set_writing_desk_extract(
        session,
        "theology",
        content="Régi teológiai kivonat, ne ezt mutasd érvényesként.",
        source_fingerprint=fingerprint_source_text("régi forrás"),
    )
    assert inspect_writing_desk_extract(session, "theology").status == STATUS_STALE

    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    joined = _joined_markdown(calls)
    assert "Régi teológiai kivonat, ne ezt mutasd érvényesként." not in joined
    assert "A forrásanyag megváltozott" in calls["caption"]
    assert ("Kivonat frissítése", "writing_desk_extract_refresh_theology") in calls["buttons"]
    assert llm_calls == []


def test_page_load_does_not_generate_extracts_automatically(monkeypatch):
    import streamlit as st

    session = {
        "original_text": "Van forrás, de még nincs kivonat.",
        "history": "Van kortörténet is.",
        "theology": "Van teológia is.",
    }
    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    labels = [label for label, _key in calls["buttons"]]
    assert labels == ["Kivonat készítése", "Kivonat készítése", "Kivonat készítése"]
    assert llm_calls == []
    assert calls["rerun"] == []


def test_generate_button_calls_llm_only_for_clicked_card(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY

    session = {
        "original_text": "Eredeti forrás mondatokkal.",
        "history": "Kortörténeti forrás mondatokkal.",
        "theology": "Teológiai forrás mondatokkal.",
    }
    llm_calls: list[str] = []

    def _generate(prompt, **kwargs):
        llm_calls.append(prompt)
        return "Egy rövid, használható kivonatmondat."

    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(
        monkeypatch,
        st,
        session,
        click_key="writing_desk_extract_generate_history",
    )
    writing_desk_ui.render_writing_desk_shell(generate_fn=_generate)

    assert len(llm_calls) == 1
    assert "Kortörténet" in llm_calls[0]
    assert session[WRITING_DESK_KEY]["extracts"]["history"]["content"] == (
        "Egy rövid, használható kivonatmondat."
    )
    assert session[WRITING_DESK_KEY]["extracts"]["original_text"]["content"] == ""
    assert session[WRITING_DESK_KEY]["extracts"]["theology"]["content"] == ""
    assert calls["rerun"] == [True]


def test_output_limit_ui_does_not_show_partial_as_valid_extract(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY
    from writing_desk_extracts import (
        EXTRACT_INCOMPLETE_MESSAGE,
        extract_error_session_key,
    )

    partial = (
        "Az ἀσώτως (asótós) határozószó nem csupán a tékozló pénzszórásra utal, "
        "hanem egy olyan mértéktelen élet"
    )
    truncated = (
        f"{partial}\n\n---\n\n"
        "> ⚠️ **A válasz a modell kimeneti korlátjánál megszakadt.** "
        "Kérlek, próbáld újra vagy bontsd kisebb részekre a kérést; "
        "részletekért használd a **finomítás chatet**."
    )
    session = {
        "original_text": "Eredeti forrás mondatokkal.",
        "history": "Kortörténeti forrás mondatokkal.",
        "theology": "Teológiai forrás mondatokkal.",
    }

    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(
        monkeypatch,
        st,
        session,
        click_key="writing_desk_extract_generate_history",
    )
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: truncated
    )

    assert session[WRITING_DESK_KEY]["extracts"]["history"]["content"] == ""
    assert (
        session[extract_error_session_key("history")] == EXTRACT_INCOMPLETE_MESSAGE
    )
    assert partial not in _joined_markdown(calls)
    assert calls["rerun"] == [True]

    calls2 = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: truncated
    )
    joined = _joined_markdown(calls2)
    assert partial not in joined
    assert "A kivonat most nem készült el" in joined
    assert EXTRACT_INCOMPLETE_MESSAGE in joined
    assert (
        "Kivonat készítése",
        "writing_desk_extract_generate_history",
    ) in calls2["buttons"]


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


def _render_desk_with_main_view_switcher() -> None:
    """Íróasztal + valódi főnézet-váltó — a smoke útvonal AppTestje."""
    import streamlit as st

    import writing_desk_ui as wd
    from workshop_nav_ui import render_workspace_switcher

    original_scripture = wd._render_scripture_block
    wd._render_scripture_block = lambda: None
    try:
        st.session_state.setdefault("ui_mode", wd.WRITING_DESK_MODE)
        wd.flush_writing_desk_draft_from_widget()
        render_workspace_switcher(
            options=["workshop", "sermon_workshop", wd.WRITING_DESK_MODE],
            labels={
                "workshop": "Textusműhely",
                "sermon_workshop": "Igehirdetési műhely",
                wd.WRITING_DESK_MODE: wd.WRITING_DESK_LABEL,
            },
            key="ui_mode",
        )
        if st.session_state.get("ui_mode") == wd.WRITING_DESK_MODE:
            wd.render_writing_desk_shell()
            st.stop()
        st.markdown("Textusműhely")
    finally:
        wd._render_scripture_block = original_scripture


def _notes_area(app: AppTest):
    return next(
        ta for ta in app.text_area if ta.key == WRITING_DESK_DRAFT_WIDGET_KEY
    )


def test_draft_survives_textusmuhely_round_trip_via_switcher() -> None:
    from writing_desk_data import WRITING_DESK_KEY

    app = AppTest.from_function(_render_desk_with_main_view_switcher).run(timeout=60)
    assert not app.exception
    assert app.session_state["ui_mode"] == WRITING_DESK_MODE

    _notes_area(app).input("Íróasztal jegyzet\n\nmásodik bekezdés").run()
    assert not app.exception
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )

    app.button(key="tx_mainnav_workshop").click().run()
    assert not app.exception
    assert app.session_state["ui_mode"] == "workshop"
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
    # Az élő app a nem renderelt textarea kulcsát eldobja; az AppTest
    # megtartja. A production unmountot így szimuláljuk a visszatérés előtt.
    del app.session_state[WRITING_DESK_DRAFT_WIDGET_KEY]

    app.button(key="tx_mainnav_writing_desk").click().run()
    assert not app.exception
    assert app.session_state["ui_mode"] == WRITING_DESK_MODE
    assert _notes_area(app).value == "Íróasztal jegyzet\n\nmásodik bekezdés"
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
    assert app.session_state[WRITING_DESK_DRAFT_WIDGET_KEY] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
