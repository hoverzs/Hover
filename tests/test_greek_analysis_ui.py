from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from bible_engine.greek_analysis_ui import (
    CROSS_CHAPTER_GREEK_MESSAGE,
    GREEK_DATA_ERROR_MESSAGE,
    LEXICAL_SCOPE_NOTE,
    MISSING_GREEK_DATA_MESSAGE,
    MISSING_GREEK_DATABASE_MESSAGE,
    NO_LEXICON_ENTRY_MESSAGE,
    OLD_TESTAMENT_MESSAGE,
    TAGNT_DATABASE_BUILD_HINT,
    TBESG_DATABASE_MISSING_MESSAGE,
    TBESG_SCOPE_NOTE,
    TBESG_SOURCE_NOTE,
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
        tbesg_lexicon_loader=lambda _strong_id: None,
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
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_cross_chapter_john_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Jn 3,16-4,2", key_prefix="test_greek")


def _render_other_new_testament_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    def token(
        book: str,
        chapter: int,
        verse: int,
        word_index: int,
        greek_form: str,
        lemma: str,
        morph_code: str,
        strong_id: str,
    ) -> GreekToken:
        return GreekToken(
            book=book,
            chapter=chapter,
            verse=verse,
            word_index=word_index,
            greek_form=greek_form,
            lemma=lemma,
            morph_code=morph_code,
            strong_id=strong_id,
            edition_flags="NKO",
        )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(
                book="Rom",
                chapter=8,
                verse=1,
                tokens=(token("Rom", 8, 1, 1, "Οὐδὲν", "οὐδείς", "A-NSN", "G3762"),),
            )
        ],
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


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
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_reference_switch_block() -> None:
    import streamlit as st
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    reference = st.session_state.get("active_reference", "Jn 3,16")

    def token(
        book: str,
        chapter: int,
        verse: int,
        word_index: int,
        greek_form: str,
        lemma: str,
        morph_code: str,
        strong_id: str,
    ) -> GreekToken:
        return GreekToken(
            book=book,
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
        if reference.startswith("Róm"):
            return [
                GreekVerseTokens(
                    book="Rom",
                    chapter=8,
                    verse=1,
                    tokens=(
                        token("Rom", 8, 1, 1, "Οὐδὲν", "οὐδείς", "A-NSN", "G3762"),
                        token("Rom", 8, 1, 2, "ἄρα", "ἄρα", "PRT", "G0686"),
                    ),
                )
            ]
        return [
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=16,
                tokens=(
                    token("Jhn", 3, 16, 1, "οὕτως", "οὕτω, οὕτως", "ADV", "G3779"),
                    token("Jhn", 3, 16, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
                ),
            )
        ]

    render_greek_analysis_block(
        reference=reference,
        key_prefix="test_greek",
        token_loader=passage_tokens,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_english_tbesg_fallback_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken
    from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )
    entry = SQLiteGreekLexiconEntry(
        strong_id="G3762",
        dstrong_id="G3762 =",
        ustrong_id="G3762",
        lemma="οὐδείς",
        transliteration="oudeis",
        morph="G:A",
        gloss="no one, nothing",
        meaning_raw="<b>οὐδείς</b>, no one, nothing",
        meaning_plain="οὐδείς, no one, none, nothing; used as a negative substantive.",
        meaning_paragraphs=("οὐδείς, no one, none, nothing; used as a negative substantive.",),
        references=("Rom.8.1",),
        source_name="STEPBible TBESG",
        source_version="test",
    )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: entry,
    )


def _render_missing_tbesg_database_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_lexicon_repository import TBESGDatabaseUnavailableError
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )

    def missing(_strong_id: str):
        raise TBESGDatabaseUnavailableError("missing test DB")

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=missing,
    )


def _render_no_lexicon_data_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_long_tbesg_meaning_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken
    from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )
    long_meaning = " ".join(
        [
            "A long English lexicon article about the term, preserving readable detail."
            for _ in range(25)
        ]
    )
    entry = SQLiteGreekLexiconEntry(
        strong_id="G3762",
        dstrong_id=None,
        ustrong_id="G3762",
        lemma="οὐδείς",
        transliteration="oudeis",
        morph="G:A",
        gloss="no one, nothing",
        meaning_raw=long_meaning,
        meaning_plain=long_meaning,
        meaning_paragraphs=(long_meaning,),
        references=("Rom.8.1",),
        source_name="STEPBible TBESG",
        source_version="test",
    )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: entry,
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
    assert greek_reference_status("Jn 3,16-4,2") == "cross_chapter"
    assert greek_reference_status("János 3,16") == "loaded"
    assert greek_reference_status("Róm 8,1") == "loaded"
    assert greek_reference_status("Mt 5,1-3") == "loaded"
    assert greek_reference_status("Júd 20-21") == "loaded"
    assert greek_reference_status("Zsolt 23,1") == "old_testament"
    assert greek_reference_status("") == "empty"
    assert greek_reference_status("Jn 3") == "invalid"
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


def test_hungarian_lexicon_has_priority_over_english_tbesg_fallback() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    app.selectbox[0].set_value(3)
    app.run()

    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Magyar lexikai jelentések" in page_text
    assert "Alapjelentés:** szeret" in page_text
    assert "Angol lexikai alapadat" not in page_text
    assert TBESG_SCOPE_NOTE not in page_text


def test_english_tbesg_fallback_renders_when_hungarian_entry_is_missing() -> None:
    app = AppTest.from_function(_render_english_tbesg_fallback_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Angol lexikai alapadat" in page_text
    assert "**Alapjelentés:** no one, nothing" in page_text
    assert "**Szótári alak:** οὐδείς" in page_text
    assert "**Szófaji jelölés:** G:A" in page_text
    assert "Részletes leírás" in page_text
    assert TBESG_SCOPE_NOTE in page_text
    assert TBESG_SOURCE_NOTE in page_text
    assert "Magyar lexikai jelentések" not in page_text


def test_missing_english_tbesg_database_is_controlled() -> None:
    app = AppTest.from_function(_render_missing_tbesg_database_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert TBESG_DATABASE_MISSING_MESSAGE in page_text
    assert "Traceback" not in page_text
    assert app.subheader[0].value == "Οὐδὲν"


def test_no_lexicon_data_message_when_no_hungarian_or_tbesg_entry_exists() -> None:
    app = AppTest.from_function(_render_no_lexicon_data_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    assert NO_LEXICON_ENTRY_MESSAGE in page_text


def test_long_tbesg_meaning_is_collapsed_behind_expander() -> None:
    app = AppTest.from_function(_render_long_tbesg_meaning_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    assert "Részletes leírás" in page_text
    assert len(app.expander) >= 2
    assert any(expander.label == "Részletes angol szócikk" for expander in app.expander)


def test_greek_analysis_ui_text_has_no_mojibake_markers() -> None:
    source = (ROOT / "bible_engine" / "greek_analysis_ui.py").read_text(encoding="utf-8")

    assert "Ã" not in source
    assert "Å" not in source
    assert "Â" not in source


def test_other_new_testament_reference_renders_greek_analysis() -> None:
    app = AppTest.from_function(_render_other_new_testament_block).run()

    assert not app.exception
    assert app.subheader[0].value == "Οὐδὲν"
    assert app.session_state["test_greek_selected_token_key"] == "Rom:8:1:1"
    assert app.selectbox[0].value == 1


def test_multi_verse_john_reference_renders_verse_rows_and_shared_panel() -> None:
    app = AppTest.from_function(_render_multi_verse_john_block).run()

    assert not app.exception
    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("textus-greek-verse-marker\">16" in value for value in markdown_values)
    assert any("textus-greek-verse-marker\">17" in value for value in markdown_values)
    assert any("textus-greek-verse-marker\">18" in value for value in markdown_values)
    assert app.subheader[0].value == "οὕτως"
    assert app.session_state["test_greek_selected_token_key"] == "Jhn:3:16:1"
    assert app.session_state["test_greek_selected_word_index"] == 1
    assert app.selectbox[0].value == "Jhn:3:16:1"

    app.selectbox[0].set_value("Jhn:3:17:1")
    app.run()

    assert app.subheader[0].value == "οὐ"
    assert app.session_state["test_greek_selected_token_key"] == "Jhn:3:17:1"
    assert app.session_state["test_greek_selected_word_index"] == 1


def test_cross_chapter_john_reference_shows_controlled_message() -> None:
    app = AppTest.from_function(_render_cross_chapter_john_block).run()

    assert not app.exception
    assert any(CROSS_CHAPTER_GREEK_MESSAGE in caption.value for caption in app.caption)
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
    assert "A teljes görög Újszövetség helyi adatbázisa még nincs előkészítve." in page_text
    assert (
        "Előkészítés: python scripts/build_tagnt_nt_db.py "
        "--mat-jhn-source ... --act-rev-source ... "
        "--output data/generated/tagnt_nt.sqlite3"
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


def test_book_switch_resets_selected_token_key() -> None:
    app = AppTest.from_function(_render_reference_switch_block)
    app.session_state["active_reference"] = "Jn 3,16"
    app.run()

    assert not app.exception
    app.selectbox[0].set_value(2)
    app.run()
    assert app.session_state["test_greek_selected_token_key"] == "Jhn:3:16:2"

    app.session_state["active_reference"] = "Róm 8,1"
    app.run()

    assert not app.exception
    assert app.session_state["test_greek_selected_token_key"] == "Rom:8:1:1"
    assert app.subheader[0].value == "Οὐδὲν"


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
                greek_token("Jhn", 3, 16, 1, "οὕτως", "οὕτω, οὕτως", "ADV", "G3779"),
                greek_token("Jhn", 3, 16, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
            ),
        ),
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=17,
            tokens=(
                greek_token("Jhn", 3, 17, 1, "οὐ", "οὐ", "PRT-N", "G3756"),
                greek_token("Jhn", 3, 17, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
            ),
        ),
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=18,
            tokens=(greek_token("Jhn", 3, 18, 1, "ὁ", "ὁ", "T-NSM", "G3588"),),
        ),
    ]


def greek_token(
    book: str,
    chapter: int,
    verse: int,
    word_index: int,
    greek_form: str,
    lemma: str,
    morph_code: str,
    strong_id: str,
) -> GreekToken:
    return GreekToken(
        book=book,
        chapter=chapter,
        verse=verse,
        word_index=word_index,
        greek_form=greek_form,
        lemma=lemma,
        morph_code=morph_code,
        strong_id=strong_id,
        edition_flags="NKO",
    )
