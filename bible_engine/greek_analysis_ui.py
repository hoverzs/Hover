from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

import streamlit as st

from bible_engine.lexicon_hu import (
    HungarianLexiconEntry,
    get_hungarian_lexicon_entry,
    load_hungarian_lexicon,
)
from bible_engine.greek_token_repository import load_greek_verse_tokens
from bible_engine.morphology_hu import format_morphology_hu, parse_morphology_hu
from bible_engine.tagnt_parser import GreekToken, get_verse_tokens
from components.greek_token_selector import greek_token_selector
from ruf_bible_service import parse_bible_reference


ROOT = Path(__file__).parents[1]
JHN_3_16_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"
LEXICON_HU_PATH = ROOT / "bible_engine" / "data" / "lexicon_hu_sample.json"

OLD_TESTAMENT_MESSAGE = (
    "Az ószövetségi eredeti nyelvi modul későbbi fejlesztésben lesz elérhető."
)
MISSING_GREEK_DATA_MESSAGE = (
    "Ehhez az igehelyhez a görög adat még nincs helyben betöltve."
)
GREEK_DATA_ERROR_MESSAGE = "A görög elemzés jelenleg nem tölthető be."
LEXICON_HU_ERROR_MESSAGE = "A magyar lexikai adatok jelenleg nem érhetők el."
NO_HUNGARIAN_LEXICON_ENTRY_MESSAGE = "Ehhez a szóhoz még nincs magyar lexikai adat."
LEXICAL_SCOPE_NOTE = (
    "A felsorolt jelentések lexikai lehetőségek. Az adott versben "
    "érvényes jelentést a szövegkörnyezet határozza meg."
)
MISSING_GREEK_DATABASE_MESSAGE = (
    "A görög szöveg helyi adatbázisa még nincs előkészítve."
)
TAGNT_DATABASE_BUILD_HINT = (
    "Előkészítés: python scripts/build_tagnt_john_db.py "
    "--source ... --output data/generated/tagnt_john.sqlite3"
)
MULTI_VERSE_JOHN_MESSAGE = (
    "A többverses görög szakaszok megjelenítése a következő "
    "fejlesztési lépésben lesz elérhető."
)
REVIEW_STATUS_LABELS = {
    "draft": "munkaváltozat",
    "reviewed": "ellenőrzött",
}

_NEW_TESTAMENT_CODES = frozenset(
    {
        "MAT",
        "MRK",
        "LUK",
        "JHN",
        "ACT",
        "ROM",
        "1CO",
        "2CO",
        "GAL",
        "EPH",
        "PHP",
        "COL",
        "1TH",
        "2TH",
        "1TI",
        "2TI",
        "TIT",
        "PHM",
        "HEB",
        "JAS",
        "1PE",
        "2PE",
        "1JN",
        "2JN",
        "3JN",
        "JUD",
        "REV",
    }
)

GreekReferenceStatus = Literal[
    "empty",
    "invalid",
    "old_testament",
    "multi_verse_john",
    "not_loaded",
    "loaded",
]


def render_greek_analysis_block(
    reference: str,
    key_prefix: str,
    *,
    token_loader: Callable[[], list[GreekToken]] | None = None,
    lexicon_loader: Callable[
        [], dict[str, HungarianLexiconEntry] | None
    ]
    | None = None,
) -> None:
    status = greek_reference_status(reference)
    if status in {"empty", "invalid"}:
        return
    if status == "old_testament":
        st.caption(OLD_TESTAMENT_MESSAGE)
        return
    if status == "multi_verse_john":
        st.caption(MULTI_VERSE_JOHN_MESSAGE)
        return
    if status == "not_loaded":
        st.caption(MISSING_GREEK_DATA_MESSAGE)
        return

    token_loader = token_loader or (lambda: load_greek_verse_tokens(reference))
    lexicon_loader = lexicon_loader or load_demo_hungarian_lexicon
    _ensure_greek_analysis_styles()

    try:
        tokens = token_loader()
    except FileNotFoundError:
        st.caption(MISSING_GREEK_DATABASE_MESSAGE)
        st.caption(TAGNT_DATABASE_BUILD_HINT)
        return
    except Exception:
        st.caption(GREEK_DATA_ERROR_MESSAGE)
        return

    if not tokens:
        st.caption(GREEK_DATA_ERROR_MESSAGE)
        return

    try:
        lexicon_entries = lexicon_loader()
    except Exception:
        lexicon_entries = None

    _render_loaded_greek_analysis(
        tokens,
        lexicon_entries,
        key_prefix=key_prefix,
        reference_label=_greek_reference_label(reference),
    )


def greek_reference_status(reference: str) -> GreekReferenceStatus:
    raw = (reference or "").strip()
    if not raw:
        return "empty"

    try:
        parsed = parse_bible_reference(raw)
    except ValueError:
        return "invalid"

    if parsed.book.code not in _NEW_TESTAMENT_CODES:
        return "old_testament"

    if parsed.book.code == "JHN":
        if parsed.verse_start is None:
            return "multi_verse_john"
        if parsed.verse_end is not None and parsed.verse_end != parsed.verse_start:
            return "multi_verse_john"
        return "loaded"

    return "not_loaded"


@st.cache_data(show_spinner=False)
def load_john_3_16_tokens() -> list[GreekToken]:
    return get_verse_tokens(JHN_3_16_FIXTURE_PATH, book="Jhn", chapter=3, verse=16)


@st.cache_data(show_spinner=False)
def load_demo_hungarian_lexicon() -> dict[str, HungarianLexiconEntry] | None:
    try:
        return load_hungarian_lexicon(LEXICON_HU_PATH)
    except Exception:
        return None


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


def _render_loaded_greek_analysis(
    tokens: list[GreekToken],
    lexicon_entries: dict[str, HungarianLexiconEntry] | None,
    *,
    key_prefix: str,
    reference_label: str | None = None,
) -> None:
    selected_key = _key(key_prefix, "selected_word_index")
    component_key = _key(key_prefix, "inline_token_selector")
    fallback_key = _key(key_prefix, "fallback_selector")

    current_index = selected_word_index(tokens, st.session_state.get(selected_key))
    st.session_state[selected_key] = current_index
    st.session_state[fallback_key] = current_index

    def sync_component_selection() -> None:
        selected = component_state_word_index(st.session_state.get(component_key), tokens)
        st.session_state[selected_key] = apply_token_selection(
            tokens, st.session_state.get(selected_key), selected
        )

    def sync_fallback_selection() -> None:
        st.session_state[selected_key] = apply_token_selection(
            tokens,
            st.session_state.get(selected_key),
            st.session_state.get(fallback_key),
        )

    st.markdown(
        '<h3 class="textus-greek-analysis-title">Görög eredeti szöveg</h3>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="textus-greek-analysis-label">Válasszon egy görög szót</div>',
        unsafe_allow_html=True,
    )
    if reference_label:
        st.caption(reference_label)
    component_selection = greek_token_selector(
        tokens=tokens,
        selected_word_index=current_index,
        key=component_key,
        on_selected_word_index_change=sync_component_selection,
    )
    next_index = apply_token_selection(tokens, current_index, component_selection)
    if next_index != current_index:
        st.session_state[selected_key] = next_index
        st.session_state[fallback_key] = next_index
        st.rerun()

    st.markdown('<div class="textus-greek-fallback-marker"></div>', unsafe_allow_html=True)
    with st.expander("Alternatív szóválasztás", expanded=False):
        st.selectbox(
            "Token",
            options=[token.word_index for token in tokens],
            key=fallback_key,
            format_func=lambda index: token_option_label(_token_by_index(tokens, index)),
            on_change=sync_fallback_selection,
        )

    current_index = selected_word_index(tokens, st.session_state.get(selected_key))
    selected_index = current_index if current_index is not None else tokens[0].word_index
    selected = _token_by_index(tokens, selected_index)
    _render_analysis_panel(selected, lexicon_entries)


def _render_analysis_panel(
    selected: GreekToken,
    lexicon_entries: dict[str, HungarianLexiconEntry] | None,
) -> None:
    st.markdown('<div class="textus-greek-analysis-card-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader(_present(selected.greek_form))
        left, right = st.columns(2, gap="small")
        analysis_items = list(token_analysis(selected).items())
        for label, value in analysis_items[:3]:
            left.markdown(f"**{label}:** {value}")
        for label, value in analysis_items[3:]:
            right.markdown(f"**{label}:** {value}")
        _render_hungarian_lexicon_section(selected, lexicon_entries)


def _render_hungarian_lexicon_section(
    token: GreekToken,
    entries: dict[str, HungarianLexiconEntry] | None,
) -> None:
    st.divider()
    st.markdown("#### Magyar lexikai jelentések")
    st.caption(LEXICAL_SCOPE_NOTE)

    if entries is None:
        st.markdown(LEXICON_HU_ERROR_MESSAGE)
        return

    entry = _hungarian_lexicon_entry_for_token(entries, token)
    if entry is None:
        st.markdown(NO_HUNGARIAN_LEXICON_ENTRY_MESSAGE)
        return

    st.markdown(f"**Alapjelentés:** {entry.primary_gloss}")
    st.markdown("**Lehetséges jelentések:**")
    for sense in entry.senses:
        st.markdown(f"- {sense}")

    if entry.note:
        st.markdown(f"**Lexikai megjegyzés:** {entry.note}")

    review_status = REVIEW_STATUS_LABELS.get(entry.review_status, entry.review_status)
    st.markdown(f"**Ellenőrzési állapot:** {review_status}")
    st.caption(f"Forrás: {entry.source}")


def _hungarian_lexicon_entry_for_token(
    entries: dict[str, HungarianLexiconEntry],
    token: GreekToken,
) -> HungarianLexiconEntry | None:
    try:
        return get_hungarian_lexicon_entry(entries, token.strong_id)
    except ValueError:
        return None


def _ensure_greek_analysis_styles() -> None:
    st.markdown(
        """
        <style>
        .textus-greek-analysis-title {
            margin: 0.16rem 0 0.01rem;
            font-size: 1.02rem;
            line-height: 1.18;
            font-weight: 700;
        }
        .element-container:has(.textus-greek-analysis-title) {
            margin-top: 0.05rem !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .textus-greek-analysis-label {
            margin: 0 0 0.02rem;
            font-size: 0.92rem;
            font-weight: 600;
            line-height: 1.16;
        }
        .element-container:has(.textus-greek-analysis-label) {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .greek-token-selector {
            font-size: 1.28rem;
            line-height: 1.26;
            margin: 0 0 0.04rem;
        }
        .greek-token-selector .greek-token {
            margin: 0 0.1rem 0.04rem 0;
            padding: 0 0.12rem;
            line-height: 1.05;
            vertical-align: baseline;
        }
        .greek-token-selector .greek-token[aria-pressed="true"] {
            box-shadow: inset 0 -0.1em 0 var(--st-primary-color, #ff4b4b);
            outline: 1px solid rgba(115, 92, 62, 0.22);
            outline-offset: 0;
        }
        .textus-greek-fallback-marker,
        .textus-greek-analysis-card-marker {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .element-container:has(.textus-greek-fallback-marker) {
            margin: 0 !important;
            padding: 0 !important;
        }
        .element-container:has(.textus-greek-fallback-marker) + .element-container {
            margin-top: 0 !important;
            margin-bottom: 0.08rem !important;
        }
        .element-container:has(.textus-greek-fallback-marker) + .element-container details {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .element-container:has(.textus-greek-fallback-marker) + .element-container summary {
            padding-top: 0.1rem !important;
            padding-bottom: 0.1rem !important;
            min-height: 0 !important;
            line-height: 1.2 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) {
            margin: 0 !important;
            padding: 0 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container {
            margin-top: 0.03rem !important;
            margin-bottom: 0 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.42rem 0.55rem 0.48rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stVerticalBlock"] {
            gap: 0.08rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container h3 {
            margin: 0 0 0.12rem !important;
            padding: 0 !important;
            line-height: 1.12 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container h4 {
            margin: 0.05rem 0 0.04rem !important;
            padding: 0 !important;
            line-height: 1.14 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.07rem !important;
            line-height: 1.23 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stMarkdownContainer"] ul {
            margin-top: 0 !important;
            margin-bottom: 0.1rem !important;
            padding-left: 1rem !important;
            line-height: 1.18 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stMarkdownContainer"] li {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            line-height: 1.18 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stDivider"] {
            margin-top: 0.12rem !important;
            margin-bottom: 0.08rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stCaptionContainer"] {
            margin-bottom: 0.08rem !important;
            line-height: 1.16 !important;
        }
        @media (max-width: 640px) {
            .greek-token-selector {
                font-size: 1.16rem;
                line-height: 1.24;
            }
            .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stVerticalBlockBorderWrapper"] {
                padding: 0.75rem 0.78rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _token_by_index(tokens: list[GreekToken], word_index: int) -> GreekToken:
    return next(token for token in tokens if token.word_index == word_index)


def _present(value: str | None) -> str:
    return value if value else "nincs adat"


def _key(prefix: str, suffix: str) -> str:
    clean_prefix = (prefix or "greek_analysis").strip().replace(" ", "_")
    return f"{clean_prefix}_{suffix}"


def _greek_reference_label(reference: str) -> str:
    try:
        parsed = parse_bible_reference(reference)
    except ValueError:
        return ""
    if parsed.book.code == "JHN" and parsed.verse_start is not None:
        return f"JĂˇnos {parsed.chapter},{parsed.verse_start}"
    return parsed.normalized_reference
