from __future__ import annotations

from pathlib import Path

import streamlit as st

from bible_engine.morphology_hu import format_morphology_hu, parse_morphology_hu
from bible_engine.tagnt_parser import GreekToken, get_verse_tokens
from components.greek_token_selector import greek_token_selector


FIXTURE_PATH = Path(__file__).parent / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"
SELECTED_TOKEN_KEY = "greek_text_demo_selected_word_index"
TOKEN_SELECTOR_COMPONENT_KEY = "greek_text_demo_inline_token_selector"
FALLBACK_SELECTOR_KEY = "greek_text_demo_fallback_selector"


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


def apply_token_selection(
    tokens: list[GreekToken], current: int | None, candidate: int | None
) -> int | None:
    if candidate is None:
        return selected_word_index(tokens, current)
    indexes = {token.word_index for token in tokens}
    if candidate in indexes:
        return candidate
    return selected_word_index(tokens, current)


def component_state_word_index(component_state: object, tokens: list[GreekToken]) -> int | None:
    if component_state is None:
        return None
    if isinstance(component_state, dict):
        value = component_state.get("selected_word_index")
    else:
        value = getattr(component_state, "selected_word_index", None)
    if value is None:
        return None
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        candidate = None
    return apply_token_selection(tokens, None, candidate)


def main() -> None:
    st.set_page_config(page_title="Görög szövegelemzés - prototípus")

    st.markdown(
        """
        <style>
        .token-selector-label {
            margin-top: 1rem;
            margin-bottom: 0.35rem;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Görög szövegelemzés – prototípus")
    st.caption("János 3,16")

    tokens = load_demo_tokens()

    if not tokens:
        st.warning("nincs adat")
        return

    current_index = selected_word_index(tokens, st.session_state.get(SELECTED_TOKEN_KEY))
    st.session_state[SELECTED_TOKEN_KEY] = current_index
    st.session_state[FALLBACK_SELECTOR_KEY] = current_index

    def sync_component_selection() -> None:
        selected = component_state_word_index(
            st.session_state.get(TOKEN_SELECTOR_COMPONENT_KEY), tokens
        )
        st.session_state[SELECTED_TOKEN_KEY] = apply_token_selection(
            tokens, st.session_state.get(SELECTED_TOKEN_KEY), selected
        )

    def sync_fallback_selection() -> None:
        st.session_state[SELECTED_TOKEN_KEY] = apply_token_selection(
            tokens,
            st.session_state.get(SELECTED_TOKEN_KEY),
            st.session_state.get(FALLBACK_SELECTOR_KEY),
        )

    st.markdown('<div class="token-selector-label">Válasszon egy görög szót</div>', unsafe_allow_html=True)
    component_selection = greek_token_selector(
        tokens=tokens,
        selected_word_index=current_index,
        key=TOKEN_SELECTOR_COMPONENT_KEY,
        on_selected_word_index_change=sync_component_selection,
    )
    next_index = apply_token_selection(tokens, current_index, component_selection)
    if next_index != current_index:
        st.session_state[SELECTED_TOKEN_KEY] = next_index
        st.session_state[FALLBACK_SELECTOR_KEY] = next_index
        st.rerun()

    with st.expander("Alternatív szóválasztás", expanded=False):
        st.selectbox(
            "Token",
            options=[token.word_index for token in tokens],
            key=FALLBACK_SELECTOR_KEY,
            format_func=lambda index: token_option_label(_token_by_index(tokens, index)),
            on_change=sync_fallback_selection,
        )

    current_index = selected_word_index(tokens, st.session_state.get(SELECTED_TOKEN_KEY))
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
