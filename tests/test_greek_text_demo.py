from pathlib import Path

from streamlit.testing.v1 import AppTest

from greek_text_demo import load_demo_tokens, token_analysis, token_option_label


def test_demo_helpers_load_john_3_16_tokens() -> None:
    tokens = load_demo_tokens()

    assert len(tokens) == 26
    assert token_option_label(tokens[0]) == "1. οὕτως"
    assert token_option_label(tokens[2]) == "3. ἠγάπησεν"


def test_demo_token_analysis_uses_hungarian_morphology() -> None:
    token = load_demo_tokens()[2]
    analysis = token_analysis(token)

    assert analysis["Görög szó"] == "ἠγάπησεν"
    assert analysis["Lemma"] == "ἀγαπάω"
    assert analysis["Strong/STEP"] == "G0025"
    assert analysis["Morfológiai kód"] == "V-AAI-3S"
    assert analysis["Magyar morfológia"] == (
        "ige, aorisztosz, aktív, kijelentő, harmadik személy, egyes szám"
    )
    assert analysis["Kiadásjelölés"] == "NKO"


def test_streamlit_demo_renders_initial_view() -> None:
    app_path = Path(__file__).parents[1] / "greek_text_demo.py"
    app = AppTest.from_file(str(app_path)).run()

    assert not app.exception
    assert app.title[0].value == "Görög szövegelemzés – prototípus"
    assert any("János 3,16" in caption.value for caption in app.caption)

    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("οὕτως γὰρ ἠγάπησεν" in value for value in markdown_values)
    assert any("αἰώνιον." in value for value in markdown_values)

    selectbox = app.selectbox[0]
    assert len(selectbox.options) == 26
    assert selectbox.value == 1
    assert selectbox.options[0] == "1. οὕτως"
    assert any("Lemma:** οὕτω, οὕτως" in value for value in markdown_values)
    assert any("Magyar morfológia:** határozószó" in value for value in markdown_values)


def test_streamlit_demo_selects_another_token() -> None:
    app_path = Path(__file__).parents[1] / "greek_text_demo.py"
    app = AppTest.from_file(str(app_path)).run()

    app.selectbox[0].set_value(3)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("Görög szó:** ἠγάπησεν" in value for value in markdown_values)
    assert any("Lemma:** ἀγαπάω" in value for value in markdown_values)
    assert any(
        "Magyar morfológia:** ige, aorisztosz, aktív, kijelentő, harmadik személy, egyes szám"
        in value
        for value in markdown_values
    )
