from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from bible_engine.greek_analysis_ui import (
    CROSS_CHAPTER_JOHN_MESSAGE,
    GREEK_DATA_ERROR_MESSAGE,
    LEXICAL_SCOPE_NOTE,
    MISSING_GREEK_DATA_MESSAGE,
    MISSING_GREEK_DATABASE_MESSAGE,
    MULTI_VERSE_JOHN_MESSAGE,
    OLD_TESTAMENT_MESSAGE,
    TAGNT_DATABASE_BUILD_HINT,
    greek_reference_status,
    render_greek_analysis_block,
)
from bible_engine.greek_token_repository import GreekVerseTokens
from bible_engine.greek_token_repository import TAGNT_DATABASE_ENV_VAR
from bible_engine.tagnt_parser import GreekToken
from bible_engine.tagnt_sqlite import import_tagnt_book


ROOT = Path(__file__).parents[1]


def _render_john_3_16_block() -> None:
    from bible_engine.greek_analysis_ui import load_john_3_16_tokens, render_greek_analysis_block

    render_greek_analysis_block(
        reference="Jn 3,16",
        key_prefix="test_greek",
        token_loader=load_john_3_16_tokens,
    )


def _render_john_3_16_default_loader_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Jn 3,16", key_prefix="test_greek")


def _render_multi_verse_john_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    def token(
        chapter: int,
        verse: int,
        word_index: int,
        greek_form: str,
        lemma: str,
        morph_code: str,
        strong_id: str,
    ) -> GreekToken:
        return GreekToken(
            book="Jhn",
            chapter=chapter,
            verse=verse,
            word_index=word_index,
            greek_form=greek_form,
            lemma=lemma,
            morph_code=morph_code,
            strong_id=strong_id,
            edition_flags="NKO",
        )

    def passage_tokens() -> list[GreekVerseTokens]:
        return [
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=16,
                tokens=(
                    token(3, 16, 1, "οὕτως", "οὕτω, οὕτως", "ADV", "G3779"),
                    token(3, 16, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
                ),
            ),
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=17,
                tokens=(
                    token(3, 17, 1, "οὐ", "οὐ", "PRT-N", "G3756"),
                    token(3, 17, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
                ),
            ),
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=18,
                tokens=(token(3, 18, 1, "ὁ", "ὁ", "T-NSM", "G3588"),),
            ),
        ]

    render_greek_analysis_block(
        reference="Jn 3,16-18",
        key_prefix="test_greek",
        token_loader=passage_tokens,
    )


def _render_cross_chapter_john_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Jn 3,16-4,2", key_prefix="test_greek")


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
    assert greek_reference_status("Jn 1,1") == "loaded"
    assert greek_reference_status("Jn 14,6") == "loaded"
    assert greek_reference_status("Jn 3,16-18") == "loaded"
    assert greek_reference_status("Jn 3,16-4,2") == "cross_chapter_john"
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
    assert any("<strong>Szótári alak / alakok:</strong> οὕτω, οὕτως" in value for value in markdown_values)
    assert any("<strong>Magyar morfológia:</strong> határozószó" in value for value in markdown_values)
    assert any("Alapjelentés:** így" in value for value in markdown_values)
    assert any(LEXICAL_SCOPE_NOTE in value for value in caption_values)


def test_selected_word_analysis_updates_through_fallback_selectbox() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    app.selectbox[0].set_value(3)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ἠγάπησεν"
    assert any("<strong>Strong/STEP:</strong> G0025" in value for value in markdown_values)
    assert any("Alapjelentés:** szeret" in value for value in markdown_values)
    assert any("szeret · megbecsül" in value for value in markdown_values)

    app.selectbox[0].set_value(7)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "κόσμον,"
    assert any("<strong>Strong/STEP:</strong> G2889" in value for value in markdown_values)
    assert any("Alapjelentés:** világ" in value for value in markdown_values)


def test_other_new_testament_reference_shows_missing_local_data_message() -> None:
    app = AppTest.from_function(_render_other_new_testament_block).run()

    assert not app.exception
    assert any(MISSING_GREEK_DATA_MESSAGE in caption.value for caption in app.caption)
    assert len(app.selectbox) == 0


def test_multi_verse_john_reference_renders_verse_rows_and_shared_panel() -> None:
    app = AppTest.from_function(_render_multi_verse_john_block).run()

    assert not app.exception
    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("textus-greek-verse-marker\">16" in value for value in markdown_values)
    assert any("textus-greek-verse-marker\">17" in value for value in markdown_values)
    assert any("textus-greek-verse-marker\">18" in value for value in markdown_values)
    assert app.subheader[0].value == "οὕτως"
    assert app.session_state["test_greek_selected_token_key"] == "3:16:1"
    assert app.session_state["test_greek_selected_word_index"] == 1
    assert app.selectbox[0].value == "3:16:1"

    app.selectbox[0].set_value("3:17:1")
    app.run()

    assert app.subheader[0].value == "οὐ"
    assert app.session_state["test_greek_selected_token_key"] == "3:17:1"
    assert app.session_state["test_greek_selected_word_index"] == 1


def test_cross_chapter_john_reference_shows_controlled_message() -> None:
    app = AppTest.from_function(_render_cross_chapter_john_block).run()

    assert not app.exception
    assert any(CROSS_CHAPTER_JOHN_MESSAGE in caption.value for caption in app.caption)
    assert len(app.selectbox) == 0


def test_default_renderer_does_not_use_fixture_fallback_for_missing_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    missing_database = tmp_path / "missing.sqlite3"
    monkeypatch.setenv(TAGNT_DATABASE_ENV_VAR, str(missing_database))

    app = AppTest.from_function(_render_john_3_16_default_loader_block).run()

    assert not app.exception
    caption_values = [caption.value for caption in app.caption]
    assert any(MISSING_GREEK_DATABASE_MESSAGE in value for value in caption_values)
    assert any(TAGNT_DATABASE_BUILD_HINT in value for value in caption_values)
    page_text = "\n".join(caption_values)
    assert "A görög szöveg helyi adatbázisa még nincs előkészítve." in page_text
    assert (
        "Előkészítés: python scripts/build_tagnt_john_db.py "
        "--source ... --output data/generated/tagnt_john.sqlite3"
    ) in page_text
    assert "Ã" not in page_text
    assert "Å" not in page_text
    assert "Â" not in page_text
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


def test_bible_text_editor_renders_greek_block_after_hungarian_text(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(TAGNT_DATABASE_ENV_VAR, str(_build_john_3_16_database(tmp_path)))

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


def _build_john_3_16_database(tmp_path: Path) -> Path:
    database = tmp_path / "tagnt_john.sqlite3"
    import_tagnt_book(
        ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv",
        database,
        "Jhn",
        "fixture",
        "test",
    )
    return database


def sample_passage_tokens() -> list[GreekVerseTokens]:
    return [
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=16,
            tokens=(
                greek_token(3, 16, 1, "οὕτως", "οὕτω, οὕτως", "ADV", "G3779"),
                greek_token(3, 16, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
            ),
        ),
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=17,
            tokens=(
                greek_token(3, 17, 1, "οὐ", "οὐ", "PRT-N", "G3756"),
                greek_token(3, 17, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
            ),
        ),
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=18,
            tokens=(greek_token(3, 18, 1, "ὁ", "ὁ", "T-NSM", "G3588"),),
        ),
    ]


def greek_token(
    chapter: int,
    verse: int,
    word_index: int,
    greek_form: str,
    lemma: str,
    morph_code: str,
    strong_id: str,
) -> GreekToken:
    return GreekToken(
        book="Jhn",
        chapter=chapter,
        verse=verse,
        word_index=word_index,
        greek_form=greek_form,
        lemma=lemma,
        morph_code=morph_code,
        strong_id=strong_id,
        edition_flags="NKO",
    )
