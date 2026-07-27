from pathlib import Path

from streamlit.testing.v1 import AppTest

from components.greek_token_selector import component_tokens, normalize_component_selection
from greek_text_demo import (
    apply_token_selection,
    component_state_word_index,
    load_demo_tokens,
    selected_word_index,
    token_analysis,
    token_option_label,
)


def test_demo_helpers_load_john_3_16_tokens() -> None:
    tokens = load_demo_tokens()

    assert len(tokens) == 26
    assert token_option_label(tokens[0]) == "1. οὕτως"
    assert token_option_label(tokens[2]) == "3. ἠγάπησεν"


def test_demo_token_analysis_uses_hungarian_morphology() -> None:
    token = load_demo_tokens()[2]
    analysis = token_analysis(token)

    assert analysis["Szótári alak / alakok"] == "ἀγαπάω"
    assert analysis["Strong/STEP"] == "G0025"
    assert analysis["Morfológiai kód"] == "V-AAI-3S"
    assert analysis["Magyar morfológia"] == (
        "ige, aorisztosz, aktív, kijelentő, harmadik személy, egyes szám"
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
        "word_index": 1,
        "greek_form": "οὕτως",
        "selected": False,
    }
    assert payload[2] == {
        "word_index": 3,
        "greek_form": "ἠγάπησεν",
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
    app_path = Path(__file__).parents[1] / "greek_text_demo.py"
    app = AppTest.from_file(str(app_path)).run()

    assert not app.exception
    assert app.title[0].value == "Görög szövegelemzés – prototípus"
    assert any("János 3,16" in caption.value for caption in app.caption)

    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("Válasszon egy görög szót" in value for value in markdown_values)
    assert not any("greek-verse" in value for value in markdown_values)
    assert not any("οὕτως γὰρ ἠγάπησεν" in value for value in markdown_values)
    assert not any("analysis-panel" in value for value in markdown_values)

    assert len(app.button) == 0

    selectbox = app.selectbox[0]
    assert len(selectbox.options) == 26
    assert selectbox.value == 1
    assert selectbox.options[0] == "1. οὕτως"
    assert app.subheader[0].value == "οὕτως"
    assert any("Szótári alak / alakok:** οὕτω, οὕτως" in value for value in markdown_values)
    assert any("Magyar morfológia:** határozószó" in value for value in markdown_values)
    assert any("Strong/STEP:** G3779" in value for value in markdown_values)
    assert any("Morfológiai kód:** ADV" in value for value in markdown_values)
    assert any("Kiadásjelölés:** NKO" in value for value in markdown_values)


def test_streamlit_demo_fallback_selectbox_updates_same_selection() -> None:
    app_path = Path(__file__).parents[1] / "greek_text_demo.py"
    app = AppTest.from_file(str(app_path)).run()

    app.selectbox[0].set_value(3)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ἠγάπησεν"
    assert app.selectbox[0].value == 3
    assert any("Szótári alak / alakok:** ἀγαπάω" in value for value in markdown_values)
