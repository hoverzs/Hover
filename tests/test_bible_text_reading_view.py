"""Formázott Bibliai szöveg olvasónézet — escape és versparser tesztek."""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_text_ui import (
    build_formatted_bible_text_html,
    format_passage_text_blocks,
    normalize_verse_number_spacing,
    parse_passage_text_blocks,
    save_bible_text_from_widgets,
)

errors: list[str] = []


def ok(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def _render_empty_bible_text_editor() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["igehely_input"] = "Jn 3,16"
    bible_text_ui.render_bible_text_editor()


def _render_editor_with_greek_text() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "16. Mert úgy szerette Isten a világot."
    bible_text_ui.render_bible_text_editor()


def _render_editor_with_ruf_error() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["_bible_text_ruf_last_error"] = (
        "Külső szolgáltatási kapcsolat hibája: mock hiba."
    )
    st.session_state["_bible_text_ruf_last_error_ref"] = "Jn 3,16"
    bible_text_ui.render_bible_text_editor()


def test_ruf_button_click_does_not_refetch_on_plain_rerun() -> None:
    import bible_text_ui

    calls: list[str] = []
    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        calls.append(reference)
        return {
            "success": True,
            "requested_reference": reference,
            "normalized_reference": "Jn 3,16",
            "translation": "RÚF 2014",
            "text": "16. Mert úgy szerette Isten a világot.",
            "verses": [{"number": 16, "text": "Mert úgy szerette Isten a világot."}],
            "source_name": "szentiras.hu",
            "source_url": "https://szentiras.hu/biblia/ruf/JHN/3",
            "copyright_notice": "",
            "warnings": [],
            "error": "",
        }

    def render_editor() -> None:
        import streamlit as st

        import bible_text_ui

        st.session_state["igehely_input"] = "Jn 3,16"
        bible_text_ui.render_bible_text_editor()

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(render_editor).run()
        app.button[0].click().run()
        assert calls == ["Jn 3,16"]

        app.run()
        assert calls == ["Jn 3,16"]
        assert app.session_state["passage_text"].startswith("16. Mert úgy szerette")
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_manual_text_area_is_hidden_by_default() -> None:
    app = AppTest.from_function(_render_empty_bible_text_editor).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert all(button.label != "Bibliai szöveg mentése" for button in app.button)
    assert any(
        expander.label == "Bibliai szöveg kézi beillesztése"
        for expander in app.expander
    )


def test_manual_text_area_renders_when_expander_is_open() -> None:
    app = AppTest.from_function(_render_empty_bible_text_editor).run()

    app.session_state["_bible_text_manual_paste_expander"] = True
    app.run()

    assert len(app.text_area) == 1
    assert app.text_area[0].label == "Teljes bibliai szöveg"
    assert any(button.label == "Bibliai szöveg mentése" for button in app.button)


def test_manual_text_save_still_works_and_survives_rerun() -> None:
    state = {
        "igehely_input": "Jn 3,16",
        "passage_text_input": "16Mert úgy szerette Isten a világot.",
    }

    saved = save_bible_text_from_widgets(state)

    assert saved["passage_text"] == "16. Mert úgy szerette Isten a világot."
    assert state["passage_text"] == "16. Mert úgy szerette Isten a világot."
    assert state["passage_text_input"] == "16Mert úgy szerette Isten a világot."

    app = AppTest.from_function(_render_empty_bible_text_editor).run()
    app.session_state["_bible_text_manual_paste_expander"] = True
    app.session_state["passage_text_input"] = "16Mert úgy szerette Isten a világot."
    app.run()

    assert app.text_area[0].value == "16Mert úgy szerette Isten a világot."
    app.run()
    assert app.session_state["passage_text_input"] == "16Mert úgy szerette Isten a világot."


def test_successful_ruf_load_does_not_open_manual_section() -> None:
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        return {
            "success": True,
            "requested_reference": reference,
            "normalized_reference": "Jn 3,16",
            "translation": "RÚF 2014",
            "text": "16. Mert úgy szerette Isten a világot.",
            "verses": [{"number": 16, "text": "Mert úgy szerette Isten a világot."}],
            "source_name": "szentiras.hu",
            "source_url": "https://szentiras.hu/biblia/ruf/JHN/3",
            "copyright_notice": "",
            "warnings": [],
            "error": "",
        }

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(_render_empty_bible_text_editor).run()
        app.button[0].click().run()

        assert len(app.text_area) == 0
        assert app.session_state["passage_text"].startswith("16. Mert")
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_ruf_error_does_not_open_manual_section() -> None:
    app = AppTest.from_function(_render_editor_with_ruf_error).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert any(button.label == "Újrapróbálás" for button in app.button)
    assert any(
        expander.label == "Bibliai szöveg kézi beillesztése"
        for expander in app.expander
    )


def test_greek_text_rendering_remains_available_with_manual_section_closed() -> None:
    app = AppTest.from_function(_render_editor_with_greek_text).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert any("Görög eredeti szöveg" in value for value in [m.value for m in app.markdown])


def test_missing_space_after_verse_number_is_normalized() -> None:
    blocks = parse_passage_text_blocks("16Mert úgy szerette Isten a világot.")

    assert blocks == [("16", "Mert úgy szerette Isten a világot.")]
    assert normalize_verse_number_spacing("16Mert úgy szerette Isten a világot.") == (
        "16. Mert úgy szerette Isten a világot."
    )


def test_already_formatted_verse_text_is_preserved() -> None:
    text = "16. Mert úgy szerette Isten a világot.\n17. Mert Isten nem azért küldte."

    assert normalize_verse_number_spacing(text) == text


def test_two_and_three_digit_verse_numbers_are_formatted() -> None:
    text = "22 Így szól az, aki ezekről bizonyságot tesz.\n100Dicsérjetek az Urat!"

    assert parse_passage_text_blocks(text) == [
        ("22", "Így szól az, aki ezekről bizonyságot tesz."),
        ("100", "Dicsérjetek az Urat!"),
    ]
    assert normalize_verse_number_spacing(text).splitlines() == [
        "22. Így szól az, aki ezekről bizonyságot tesz.",
        "100. Dicsérjetek az Urat!",
    ]


def test_manual_pasted_text_formats_without_touching_unicode() -> None:
    text = "1Nincsen azért most már semmiféle kárhoztató ítélet.\n2 mert az élet Lelkének törvénye."

    normalized = normalize_verse_number_spacing(text)

    assert normalized == (
        "1. Nincsen azért most már semmiféle kárhoztató ítélet.\n"
        "2. mert az élet Lelkének törvénye."
    )
    assert "ítélet" in normalized
    assert "Lelkének" in normalized


def test_formatted_html_has_separate_verse_number_span() -> None:
    markup = build_formatted_bible_text_html("16Mert úgy szerette Isten a világot.")

    assert '<span class="bible-verse-num">16.</span>' in markup
    assert "16Mert" not in markup
    assert "Mert úgy szerette Isten" in markup


def test_continuous_and_line_views_contain_same_text() -> None:
    text = "16. Mert úgy szerette Isten a világot.\n17. Mert Isten nem azért küldte."

    line_markup = build_formatted_bible_text_html(text, view_mode="Versenkénti nézet")
    continuous_markup = build_formatted_bible_text_html(text, view_mode="Folyamatos nézet")

    for needle in (
        "16.",
        "Mert úgy szerette Isten a világot.",
        "17.",
        "Mert Isten nem azért küldte.",
    ):
        assert needle in line_markup
        assert needle in continuous_markup
    assert "bible-inline-num" in continuous_markup


def main() -> None:
    # Versszám formák
    blocks = parse_passage_text_blocks(
        "17 Ti azonban, szeretteim...\n"
        "18. Azt mondták ugyanis...\n"
        "19  Ezek szakadásokat okoznak...\n"
        "Bevezető megjegyzés sortörés nélkül\n"
        "20 Ti azonban, szeretteim..."
    )
    ok(blocks[0] == ("17", "Ti azonban, szeretteim..."), f"b0 {blocks[0]}")
    ok(blocks[1] == ("18", "Azt mondták ugyanis..."), f"b1 {blocks[1]}")
    ok(blocks[2] == ("19", "Ezek szakadásokat okoznak..."), f"b2 {blocks[2]}")
    ok(blocks[3] == (None, "Bevezető megjegyzés sortörés nélkül"), f"b3 {blocks[3]}")
    ok(blocks[4] == ("20", "Ti azonban, szeretteim..."), f"b4 {blocks[4]}")

    # HTML escape
    markup = build_formatted_bible_text_html('16 <script>alert("x")</script> & "idézet"')
    ok("<script>" not in markup, "script tag must be escaped")
    ok("&lt;script&gt;" in markup, "escaped script")
    ok("&amp;" in markup, "amp escaped")
    ok("bible-verse-num" in markup and "bible-verse-text" in markup, "structure")
    ok("alert" in markup, "text preserved escaped")

    # Üres
    ok(build_formatted_bible_text_html("   \n  ") == "", "empty")

    # Hosszú sor — struktúra megmarad
    long = "1 " + ("szó " * 80)
    m = build_formatted_bible_text_html(long)
    ok("bible-verse-text" in m, "long verse")
    ok("table" not in m.lower(), "no table")

    # Júd jellegű 4 vers
    jude = (
        "17 Ti azonban, szeretteim, emlékezzetek meg...\n"
        "18 Azt mondták ugyanis...\n"
        "19 Ezek szakadásokat okoznak...\n"
        "20 Ti azonban, szeretteim, épüljetek..."
    )
    jb = parse_passage_text_blocks(jude)
    ok(len(jb) == 4, "jude 4")
    ok([n for n, _ in jb] == ["17", "18", "19", "20"], "jude nums")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    print("OK bible reading view tests passed")


if __name__ == "__main__":
    main()
