from __future__ import annotations

from pathlib import Path

import streamlit as st

from bible_engine.morphology_hu import format_morphology_hu, parse_morphology_hu
from bible_engine.tagnt_parser import GreekToken, get_verse_tokens, render_greek_text


FIXTURE_PATH = Path(__file__).parent / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"
SELECTED_TOKEN_KEY = "greek_text_demo_selected_word_index"
TOKENS_PER_ROW = 6


def load_demo_tokens() -> list[GreekToken]:
    return get_verse_tokens(FIXTURE_PATH, book="Jhn", chapter=3, verse=16)


def token_option_label(token: GreekToken) -> str:
    return f"{token.word_index}. {token.greek_form or 'nincs adat'}"


def token_analysis(token: GreekToken) -> dict[str, str]:
    morphology = parse_morphology_hu(token.morph_code or "")
    return {
        "Szótári alak / alakok": _present(token.lemma),
        "Strong/STEP": _present(token.strong_id),
        "Morfológiai kód": _present(token.morph_code),
        "Magyar morfológia": _present(format_morphology_hu(morphology)),
        "Kiadásjelölés": _present(token.edition_flags),
    }


def selected_word_index(tokens: list[GreekToken], current: int | None) -> int | None:
    indexes = {token.word_index for token in tokens}
    if current in indexes:
        return current
    return tokens[0].word_index if tokens else None


def main() -> None:
    st.set_page_config(page_title="Görög szövegelemzés - prototípus")

    st.markdown(
        """
        <style>
        .greek-verse {
            font-size: 1.65rem;
            line-height: 1.75;
            margin: 1rem 0 1.25rem;
        }
        .token-grid-note {
            margin-top: 0.5rem;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Görög szövegelemzés – prototípus")
    st.caption("János 3,16")

    tokens = load_demo_tokens()
    greek_text = render_greek_text(tokens)
    st.markdown(f'<div class="greek-verse">{_present(greek_text)}</div>', unsafe_allow_html=True)

    if not tokens:
        st.warning("nincs adat")
        return

    if SELECTED_TOKEN_KEY not in st.session_state:
        st.session_state[SELECTED_TOKEN_KEY] = tokens[0].word_index

    current_index = selected_word_index(tokens, st.session_state.get(SELECTED_TOKEN_KEY))
    st.session_state[SELECTED_TOKEN_KEY] = current_index

    st.markdown('<div class="token-grid-note">Válasszon egy görög szót</div>', unsafe_allow_html=True)
    for row_start in range(0, len(tokens), TOKENS_PER_ROW):
        columns = st.columns(TOKENS_PER_ROW)
        for column, token in zip(columns, tokens[row_start : row_start + TOKENS_PER_ROW]):
            button_type = "primary" if token.word_index == current_index else "secondary"
            if column.button(
                token.greek_form or "nincs adat",
                key=f"greek_token_{token.word_index}",
                type=button_type,
            ):
                st.session_state[SELECTED_TOKEN_KEY] = token.word_index
                current_index = token.word_index

    with st.expander("Alternatív szóválasztás", expanded=False):
        fallback_index = st.selectbox(
            "Token",
            options=[token.word_index for token in tokens],
            index=[token.word_index for token in tokens].index(current_index),
            format_func=lambda index: token_option_label(_token_by_index(tokens, index)),
        )
        if fallback_index != current_index:
            st.session_state[SELECTED_TOKEN_KEY] = fallback_index
            current_index = fallback_index

    selected_index = current_index if current_index is not None else tokens[0].word_index
    selected = _token_by_index(tokens, selected_index)

    with st.container(border=True):
        st.subheader(_present(selected.greek_form))
        left, right = st.columns(2)
        analysis_items = list(token_analysis(selected).items())
        for label, value in analysis_items[:3]:
            left.markdown(f"**{label}:** {value}")
        for label, value in analysis_items[3:]:
            right.markdown(f"**{label}:** {value}")


def _token_by_index(tokens: list[GreekToken], word_index: int) -> GreekToken:
    return next(token for token in tokens if token.word_index == word_index)


def _present(value: str | None) -> str:
    return value if value else "nincs adat"


if __name__ == "__main__":
    main()
