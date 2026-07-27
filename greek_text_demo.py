from __future__ import annotations

from pathlib import Path

import streamlit as st

from bible_engine.morphology_hu import format_morphology_hu, parse_morphology_hu
from bible_engine.tagnt_parser import GreekToken, get_verse_tokens, render_greek_text


FIXTURE_PATH = Path(__file__).parent / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"


def load_demo_tokens() -> list[GreekToken]:
    return get_verse_tokens(FIXTURE_PATH, book="Jhn", chapter=3, verse=16)


def token_option_label(token: GreekToken) -> str:
    return f"{token.word_index}. {token.greek_form or 'nincs adat'}"


def token_analysis(token: GreekToken) -> dict[str, str]:
    morphology = parse_morphology_hu(token.morph_code or "")
    return {
        "Görög szó": _present(token.greek_form),
        "Lemma": _present(token.lemma),
        "Strong/STEP": _present(token.strong_id),
        "Morfológiai kód": _present(token.morph_code),
        "Magyar morfológia": _present(format_morphology_hu(morphology)),
        "Kiadásjelölés": _present(token.edition_flags),
    }


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
        .analysis-panel {
            border: 1px solid rgba(49, 51, 63, 0.18);
            border-radius: 8px;
            padding: 1rem;
            margin-top: 1rem;
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

    selected_index = st.selectbox(
        "Token",
        options=[token.word_index for token in tokens],
        format_func=lambda index: token_option_label(_token_by_index(tokens, index)),
    )
    selected = _token_by_index(tokens, selected_index)

    st.markdown('<div class="analysis-panel">', unsafe_allow_html=True)
    for label, value in token_analysis(selected).items():
        st.markdown(f"**{label}:** {value}")
    st.markdown("</div>", unsafe_allow_html=True)


def _token_by_index(tokens: list[GreekToken], word_index: int) -> GreekToken:
    return next(token for token in tokens if token.word_index == word_index)


def _present(value: str | None) -> str:
    return value if value else "nincs adat"


if __name__ == "__main__":
    main()
