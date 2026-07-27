from __future__ import annotations

from collections.abc import Callable
from html import escape

import streamlit as st

from bible_engine.greek_analysis_ui import (
    LEXICAL_SCOPE_NOTE,
    LEXICON_HU_ERROR_MESSAGE,
    apply_token_selection,
    component_state_word_index,
    load_demo_hungarian_lexicon,
    load_john_3_16_tokens as load_demo_tokens,
    render_greek_analysis_block,
    selected_word_index,
    token_analysis,
    token_option_label,
)
from ruf_bible_service import fetch_ruf_passage


RUF_REFERENCE = "Jn 3,16"
RUF_ERROR_MESSAGE = (
    "A magyar bibliai szöveg jelenleg nem tölthető be. "
    "A görög szövegelemzés továbbra is használható."
)


@st.cache_data(show_spinner=False)
def load_ruf_demo_text() -> str | None:
    try:
        result = fetch_ruf_passage(RUF_REFERENCE)
    except Exception:
        return None

    if not result.get("success"):
        return None

    text = str(result.get("text") or "").strip()
    return text or None


def main() -> None:
    render_demo()


def render_demo(
    ruf_text_loader: Callable[[], str | None] = load_ruf_demo_text,
    lexicon_loader: Callable[[], object] | None = None,
) -> None:
    st.set_page_config(page_title="Görög szövegelemzés - prototípus")

    st.markdown(
        """
        <style>
        .ruf-text {
            margin: 0.25rem 0 1.1rem;
            padding: 0.85rem 1rem;
            border-left: 3px solid #8b7355;
            background: rgba(139, 115, 85, 0.08);
            line-height: 1.65;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Görög szövegelemzés – prototípus")
    st.caption("János 3,16")
    render_ruf_text_block(ruf_text_loader)
    render_greek_analysis_block(
        reference=RUF_REFERENCE,
        key_prefix="greek_demo",
        token_loader=load_demo_tokens,
        lexicon_loader=lexicon_loader or load_demo_hungarian_lexicon,
    )


def render_ruf_text_block(ruf_text_loader: Callable[[], str | None]) -> None:
    st.markdown("### RÚF 2014")
    try:
        ruf_text = ruf_text_loader()
    except Exception:
        ruf_text = None

    if ruf_text:
        st.markdown(
            f'<div class="ruf-text">{escape(ruf_text)}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(RUF_ERROR_MESSAGE)


if __name__ == "__main__":
    main()
