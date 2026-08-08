from streamlit.testing.v1 import AppTest

from components.greek_token_selector import component_tokens, normalize_component_selection
from greek_text_demo import (
    LEXICAL_SCOPE_NOTE,
    LEXICON_HU_ERROR_MESSAGE,
    NO_LEXICON_ENTRY_MESSAGE,
    RUF_ERROR_MESSAGE,
    RUF_REFERENCE,
    apply_token_selection,
    component_state_word_index,
    load_demo_hungarian_lexicon,
    load_demo_tokens,
    load_ruf_demo_text,
    selected_word_index,
    token_analysis,
    token_option_label,
)


def _demo_with_mocked_ruf_success() -> None:
    from greek_text_demo import render_demo

    def load_mock_ruf_text() -> str:
        return "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta."

    render_demo(
        ruf_text_loader=load_mock_ruf_text,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _demo_with_mocked_ruf_success_and_empty_lexicon() -> None:
    from greek_text_demo import render_demo

    def load_mock_ruf_text() -> str:
        return "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta."

    render_demo(
        ruf_text_loader=load_mock_ruf_text,
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _demo_with_mocked_ruf_failure() -> None:
    from greek_text_demo import render_demo

    def load_failing_ruf_text() -> str:
        raise TimeoutError("mock timeout")

    render_demo(
        ruf_text_loader=load_failing_ruf_text,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _demo_with_mocked_ruf_success_and_lexicon_failure() -> None:
    from greek_text_demo import render_demo

    def load_mock_ruf_text() -> str:
        return "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta."

    def load_failing_lexicon() -> None:
        raise OSError("mock lexicon failure")

    render_demo(
        ruf_text_loader=load_mock_ruf_text,
        lexicon_loader=load_failing_lexicon,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def test_demo_helpers_load_john_3_16_tokens() -> None:
    tokens = load_demo_tokens()

    assert len(tokens) == 26
    assert token_option_label(tokens[0]) == "1. οὕτως"
    assert token_option_label(tokens[2]) == "3. ἠγάπησεν"


def test_load_ruf_demo_text_uses_existing_ruf_service(monkeypatch) -> None:
    calls = []

    def fake_fetch_ruf_passage(reference: str) -> dict[str, object]:
        calls.append(reference)
        return {"success": True, "text": "16 magyar próbaszöveg"}

    monkeypatch.setattr(
        "greek_text_demo.fetch_ruf_passage",
        fake_fetch_ruf_passage,
    )
    load_ruf_demo_text.clear()

    assert load_ruf_demo_text() == "16 magyar próbaszöveg"
    assert calls == [RUF_REFERENCE]

    load_ruf_demo_text.clear()


def test_load_demo_hungarian_lexicon_loads_full_runtime_entries() -> None:
    load_demo_hungarian_lexicon.clear()
    entries = load_demo_hungarian_lexicon()

    assert entries is not None
    assert "G2316" in entries
    assert "G1063" in entries
    assert "G3779" in entries
    assert entries["G0025"].primary_gloss == "szeret"

    load_demo_hungarian_lexicon.clear()


def test_demo_token_analysis_uses_hungarian_morphology() -> None:
    token = load_demo_tokens()[2]
    analysis = token_analysis(token)

    assert analysis["Szótári alak / alakok"] == "ἀγαπάω"
    assert analysis["Strong/STEP"] == "G0025"
    assert analysis["Morfológiai kód"] == "V-AAI-3S"
    assert analysis["Nyelvtani alak"] == (
        "ige, aorisztoszi, kijelentő mód, aktív igenem, egyes szám harmadik személy"
    )
    assert analysis["Kiadásjelölés"] == "NKO"


def test_selected_word_index_defaults_and_preserves_valid_selection() -> None:
    tokens = load_demo_tokens()

    assert selected_word_index(tokens, None) == 1
    assert selected_word_index(tokens, 3) == 3
    assert selected_word_index(tokens, 999) == 1
    assert selected_word_index([], 1) is None


def test_component_payload_contains_26_inline_tokens_and_selected_state() -> None:
    tokens = load_demo_tokens()
    payload = component_tokens(tokens, selected_word_index=3)

    assert len(payload) == 26
    assert payload[0] == {
        "book": "Jhn",
        "chapter": 3,
        "verse": 16,
        "word_index": 1,
        "greek_form": "οὕτως",
        "selection_key": "Jhn:3:16:1",
        "selected": False,
    }
    assert payload[2] == {
        "book": "Jhn",
        "chapter": 3,
        "verse": 16,
        "word_index": 3,
        "greek_form": "ἠγάπησεν",
        "selection_key": "Jhn:3:16:3",
        "selected": True,
    }
    assert "lemma" not in payload[0]
    assert "strong_id" not in payload[0]
    assert "morph_code" not in payload[0]


def test_component_selection_normalization_is_safe() -> None:
    tokens = load_demo_tokens()

    assert normalize_component_selection(3, tokens) == 3
    assert normalize_component_selection("3", tokens) == 3
    assert normalize_component_selection(999, tokens) is None
    assert normalize_component_selection("bad", tokens) is None
    assert normalize_component_selection(None, tokens) is None


def test_component_state_word_index_reads_component_result_safely() -> None:
    tokens = load_demo_tokens()

    assert component_state_word_index({"selected_word_index": 3}, tokens) == 3
    assert component_state_word_index({"selected_word_index": 999}, tokens) == 1
    assert component_state_word_index({}, tokens) is None


def test_component_returned_word_index_updates_selection_safely() -> None:
    tokens = load_demo_tokens()

    assert apply_token_selection(tokens, current=1, candidate=3) == 3
    assert apply_token_selection(tokens, current=3, candidate=None) == 3
    assert apply_token_selection(tokens, current=3, candidate=999) == 3
    assert apply_token_selection(tokens, current=999, candidate=999) == 1


def test_component_next_render_payload_receives_resolved_selection() -> None:
    tokens = load_demo_tokens()
    selected = apply_token_selection(tokens, current=1, candidate=3)
    payload = component_tokens(tokens, selected_word_index=selected)

    assert selected == 3
    assert payload[2]["selected"] is True
    assert all(
        item["selected"] is False
        for item in payload
        if item["word_index"] != 3
    )


def test_streamlit_demo_renders_initial_view() -> None:
    app = AppTest.from_function(_demo_with_mocked_ruf_success).run()

    assert not app.exception
    assert app.title[0].value == "Görög szövegelemzés – prototípus"
    assert any("János 3,16" in caption.value for caption in app.caption)

    markdown_values = [markdown.value for markdown in app.markdown]
    ruf_title_index = next(
        index for index, value in enumerate(markdown_values) if "RÚF 2014" in value
    )
    ruf_text_index = next(
        index
        for index, value in enumerate(markdown_values)
        if "Mert úgy szerette Isten" in value
    )
    selector_label_index = next(
        index
        for index, value in enumerate(markdown_values)
        if "Válasszon egy görög szót" in value
    )
    assert ruf_title_index < ruf_text_index < selector_label_index
    assert any("Válasszon egy görög szót" in value for value in markdown_values)
    assert not any('class="greek-verse"' in value for value in markdown_values)
    assert not any("οὕτως γὰρ ἠγάπησεν" in value for value in markdown_values)
    assert not any("analysis-panel" in value for value in markdown_values)

    assert len(app.button) == 1
    assert app.button[0].label == "Konkordancia: mind a 215 előfordulás"

    selectbox = app.selectbox[0]
    assert len(selectbox.options) == 26
    assert selectbox.value == 1
    assert selectbox.options[0] == "1. οὕτως"
    assert app.subheader[0].value == "οὕτως"
    assert any("<strong>Szótári alak / alakok:</strong> οὕτω, οὕτως" in value for value in markdown_values)
    assert any("<strong>Nyelvtani alak:</strong> határozószó" in value for value in markdown_values)
    assert any("<strong>Strong/STEP:</strong> G3779" in value for value in markdown_values)
    assert any("<strong>Morfológiai kód:</strong> ADV" in value for value in markdown_values)
    assert any("<strong>Kiadásjelölés:</strong> NKO" in value for value in markdown_values)
    assert any("Magyar lexikai jelentések" in value for value in markdown_values)
    assert any("Alapjelentés:** így" in value for value in markdown_values)
    assert any("Ellenőrzési állapot:** munkaváltozat" in value for value in markdown_values)
    assert any(
        "STEPBible TBESG alapján készített magyar munkaváltozat" in caption.value
        for caption in app.caption
    )
    assert any(LEXICAL_SCOPE_NOTE in caption.value for caption in app.caption)


def test_streamlit_demo_fallback_selectbox_updates_same_selection() -> None:
    app = AppTest.from_function(_demo_with_mocked_ruf_success).run()

    app.selectbox[0].set_value(3)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ἠγάπησεν"
    assert app.selectbox[0].value == 3
    assert any("<strong>Szótári alak / alakok:</strong> ἀγαπάω" in value for value in markdown_values)
    assert any("Alapjelentés:** szeret" in value for value in markdown_values)
    assert any("szeret · megbecsül" in value for value in markdown_values)
    assert any(
        "jóindulattal viszonyul valakihez" in value for value in markdown_values
    )

    morphology_values = [
        value for value in markdown_values if "<strong>Nyelvtani alak:</strong>" in value
    ]
    assert morphology_values
    assert all("szeret" not in value for value in morphology_values)


def test_streamlit_demo_shows_hungarian_lexicon_for_kosmos_and_houtos() -> None:
    app = AppTest.from_function(_demo_with_mocked_ruf_success).run()

    app.selectbox[0].set_value(7)
    app.run()
    kosmos_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "κόσμον,"
    assert any("Alapjelentés:** világ" in value for value in kosmos_values)
    assert any("világegyetem" in value for value in kosmos_values)
    assert any("dísz vagy ékesség" in value for value in kosmos_values)

    app.selectbox[0].set_value(1)
    app.run()
    houtos_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "οὕτως"
    assert any("Alapjelentés:** így" in value for value in houtos_values)
    assert any("ilyen módon" in value for value in houtos_values)
    assert any("ekképpen" in value for value in houtos_values)


def test_streamlit_demo_shows_normal_empty_lexicon_state_for_unsupported_token() -> None:
    app = AppTest.from_function(_demo_with_mocked_ruf_success_and_empty_lexicon).run()

    app.selectbox[0].set_value(8)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ὥστε"
    assert any(NO_LEXICON_ENTRY_MESSAGE in value for value in markdown_values)
    assert not any(
        "Alapjelentés:**" in value
        for value in markdown_values
    )


def test_streamlit_demo_ruf_failure_keeps_greek_analysis_available() -> None:
    app = AppTest.from_function(_demo_with_mocked_ruf_failure).run()

    assert not app.exception
    assert any(RUF_ERROR_MESSAGE in warning.value for warning in app.warning)
    assert app.subheader[0].value == "οὕτως"

    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("Válasszon egy görög szót" in value for value in markdown_values)
    assert any("<strong>Szótári alak / alakok:</strong> οὕτω, οὕτως" in value for value in markdown_values)


def test_streamlit_demo_lexicon_failure_keeps_greek_analysis_available() -> None:
    app = AppTest.from_function(_demo_with_mocked_ruf_success_and_lexicon_failure).run()

    assert not app.exception
    assert app.subheader[0].value == "οὕτως"

    markdown_values = [markdown.value for markdown in app.markdown]
    assert any(LEXICON_HU_ERROR_MESSAGE in value for value in markdown_values)
    assert any("<strong>Nyelvtani alak:</strong> határozószó" in value for value in markdown_values)
    assert any("<strong>Strong/STEP:</strong> G3779" in value for value in markdown_values)


def test_streamlit_demo_does_not_show_contextual_or_exegetical_claims() -> None:
    app = AppTest.from_function(_demo_with_mocked_ruf_success).run()

    app.selectbox[0].set_value(3)
    app.run()

    page_text = "\n".join(markdown.value for markdown in app.markdown)
    assert "Ebben a versben ezt jelenti" not in page_text
    assert "Exegetikai jelentőség" not in page_text
    assert "AI magyarázat" not in page_text
    assert "angol TBESG" not in page_text
