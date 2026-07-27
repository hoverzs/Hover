from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from bible_engine.greek_analysis_ui import (
    GREEK_DATA_ERROR_MESSAGE,
    LEXICAL_SCOPE_NOTE,
    MISSING_GREEK_DATA_MESSAGE,
    OLD_TESTAMENT_MESSAGE,
    greek_reference_status,
    render_greek_analysis_block,
)


ROOT = Path(__file__).parents[1]


def _render_john_3_16_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Jn 3,16", key_prefix="test_greek")


def _render_other_new_testament_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Róm 8,1", key_prefix="test_greek")


def _render_old_testament_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Zsolt 23,1", key_prefix="test_greek")


def _render_invalid_reference_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="nem igehely", key_prefix="test_greek")


def _render_token_load_failure_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    def fail_tokens():
        raise OSError("missing fixture")

    render_greek_analysis_block(
        reference="Jn 3,16",
        key_prefix="test_greek",
        token_loader=fail_tokens,
    )


def _render_bible_text_editor_with_john_text() -> None:
    import streamlit as st
    from bible_text_ui import render_bible_text_editor

    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["passage_text"] = (
        "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta."
    )
    st.session_state["passage_text_source"] = "szentiras.hu"
    st.session_state["passage_text_source_url"] = "https://szentiras.hu/biblia/ruf/JHN/3"
    render_bible_text_editor()


def test_reference_status_distinguishes_supported_and_unsupported_references() -> None:
    assert greek_reference_status("Jn 3,16") == "loaded"
    assert greek_reference_status("János 3,16") == "loaded"
    assert greek_reference_status("Róm 8,1") == "not_loaded"
    assert greek_reference_status("Zsolt 23,1") == "old_testament"
    assert greek_reference_status("") == "empty"
    assert greek_reference_status("nem igehely") == "invalid"


def test_john_3_16_renders_greek_block_and_analysis_panel() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    assert not app.exception
    markdown_values = [markdown.value for markdown in app.markdown]
    caption_values = [caption.value for caption in app.caption]

    assert any("Görög eredeti szöveg" in value for value in markdown_values)
    assert any("Válasszon egy görög szót" in value for value in markdown_values)
    assert app.selectbox[0].value == 1
    assert app.subheader[0].value == "οὕτως"
    assert any("Szótári alak / alakok:** οὕτω, οὕτως" in value for value in markdown_values)
    assert any("Magyar morfológia:** határozószó" in value for value in markdown_values)
    assert any("Alapjelentés:** így" in value for value in markdown_values)
    assert any(LEXICAL_SCOPE_NOTE in value for value in caption_values)


def test_selected_word_analysis_updates_through_fallback_selectbox() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    app.selectbox[0].set_value(3)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ἠγάπησεν"
    assert any("Strong/STEP:** G0025" in value for value in markdown_values)
    assert any("Alapjelentés:** szeret" in value for value in markdown_values)
    assert any("- megbecsül" in value for value in markdown_values)

    app.selectbox[0].set_value(7)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "κόσμον,"
    assert any("Strong/STEP:** G2889" in value for value in markdown_values)
    assert any("Alapjelentés:** világ" in value for value in markdown_values)


def test_other_new_testament_reference_shows_missing_local_data_message() -> None:
    app = AppTest.from_function(_render_other_new_testament_block).run()

    assert not app.exception
    assert any(MISSING_GREEK_DATA_MESSAGE in caption.value for caption in app.caption)
    assert len(app.selectbox) == 0


def test_old_testament_reference_shows_future_module_message() -> None:
    app = AppTest.from_function(_render_old_testament_block).run()

    assert not app.exception
    assert any(OLD_TESTAMENT_MESSAGE in caption.value for caption in app.caption)
    assert len(app.selectbox) == 0


def test_invalid_reference_renders_no_greek_block() -> None:
    app = AppTest.from_function(_render_invalid_reference_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Görög eredeti szöveg" not in page_text
    assert MISSING_GREEK_DATA_MESSAGE not in page_text
    assert OLD_TESTAMENT_MESSAGE not in page_text


def test_key_prefix_separates_session_state_keys() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    assert app.session_state["test_greek_selected_word_index"] == 1
    assert app.session_state["test_greek_fallback_selector"] == 1
    assert "greek_demo_selected_word_index" not in app.session_state
    assert "bible_text_ui_selected_word_index" not in app.session_state


def test_token_loading_failure_is_contained() -> None:
    app = AppTest.from_function(_render_token_load_failure_block).run()

    assert not app.exception
    assert any(GREEK_DATA_ERROR_MESSAGE in caption.value for caption in app.caption)


def test_bible_text_editor_renders_greek_block_after_hungarian_text() -> None:
    app = AppTest.from_function(_render_bible_text_editor_with_john_text).run()

    assert not app.exception
    markdown_values = [markdown.value for markdown in app.markdown]
    bible_reader_index = next(
        index for index, value in enumerate(markdown_values) if "bible-reader" in value
    )
    greek_heading_index = next(
        index
        for index, value in enumerate(markdown_values)
        if "Görög eredeti szöveg" in value
    )

    assert bible_reader_index < greek_heading_index
    assert app.subheader[0].value == "οὕτως"
    assert app.session_state["bible_text_ui_selected_word_index"] == 1
    assert "greek_demo_selected_word_index" not in app.session_state


def test_demo_and_bible_text_ui_use_shared_renderer() -> None:
    demo_source = (ROOT / "greek_text_demo.py").read_text(encoding="utf-8")
    bible_text_source = (ROOT / "bible_text_ui.py").read_text(encoding="utf-8")

    assert "render_greek_analysis_block" in demo_source
    assert "render_greek_analysis_block" in bible_text_source
    assert "from bible_engine.greek_analysis_ui import" in demo_source
    assert "from bible_engine.greek_analysis_ui import render_greek_analysis_block" in bible_text_source
