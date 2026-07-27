from pathlib import Path

from streamlit.testing.v1 import AppTest

from greek_text_demo import (
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


def test_streamlit_demo_renders_initial_view() -> None:
    app_path = Path(__file__).parents[1] / "greek_text_demo.py"
    app = AppTest.from_file(str(app_path)).run()

    assert not app.exception
    assert app.title[0].value == "Görög szövegelemzés – prototípus"
    assert any("János 3,16" in caption.value for caption in app.caption)

    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("οὕτως γὰρ ἠγάπησεν" in value for value in markdown_values)
    assert any("αἰώνιον." in value for value in markdown_values)
    assert any("Válasszon egy görög szót" in value for value in markdown_values)
    assert not any("analysis-panel" in value for value in markdown_values)

    assert len(app.button) == 26
    assert app.button[0].label == "οὕτως"
    assert app.button[1].label == "γὰρ"
    assert app.button[2].label == "ἠγάπησεν"

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


def test_streamlit_demo_button_selects_another_token() -> None:
    app_path = Path(__file__).parents[1] / "greek_text_demo.py"
    app = AppTest.from_file(str(app_path)).run()

    app.button[2].click()
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ἠγάπησεν"
    assert any("Szótári alak / alakok:** ἀγαπάω" in value for value in markdown_values)
    assert any(
        "Magyar morfológia:** ige, aorisztosz, aktív, kijelentő, harmadik személy, egyes szám"
        in value
        for value in markdown_values
    )


def test_streamlit_demo_fallback_selectbox_updates_same_selection() -> None:
    app_path = Path(__file__).parents[1] / "greek_text_demo.py"
    app = AppTest.from_file(str(app_path)).run()

    app.selectbox[0].set_value(3)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ἠγάπησεν"
    assert any("Szótári alak / alakok:** ἀγαπάω" in value for value in markdown_values)
