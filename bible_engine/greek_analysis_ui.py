from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import streamlit as st

from bible_engine.greek_token_repository import (
    GreekVerseTokens,
    load_greek_passage_tokens,
)
from bible_engine.greek_lexicon_repository import (
    TBESGDatabaseUnavailableError,
    get_tbesg_lexicon_entry,
)
from bible_engine.tagnt_books import NEW_TESTAMENT_RUF_CODES
from bible_engine.tagnt_books import parse_tagnt_bible_reference
from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry
from bible_engine.lexicon_hu import (
    HungarianLexiconEntry,
    get_hungarian_lexicon_entry,
    load_hungarian_lexicon,
)
from bible_engine.morphology_hu import format_morphology_hu, parse_morphology_hu
from bible_engine.tagnt_parser import GreekToken, get_verse_tokens
from components.greek_token_selector import (
    greek_token_selector,
    greek_token_selector_value,
)


ROOT = Path(__file__).parents[1]
JHN_3_16_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"
LEXICON_HU_PATH = ROOT / "bible_engine" / "data" / "lexicon_hu_sample.json"

OLD_TESTAMENT_MESSAGE = (
    "Az ószövetségi eredeti nyelvi modul későbbi fejlesztésben lesz elérhető."
)
MISSING_GREEK_DATA_MESSAGE = (
    "Ehhez az igehelyhez nem található görög szöveg a helyi adatbázisban."
)
GREEK_DATA_ERROR_MESSAGE = "A görög elemzés jelenleg nem tölthető be."
LEXICON_HU_ERROR_MESSAGE = "A magyar lexikai adatok jelenleg nem érhetők el."
NO_HUNGARIAN_LEXICON_ENTRY_MESSAGE = "Ehhez a szóhoz még nincs magyar lexikai adat."
NO_LEXICON_ENTRY_MESSAGE = "Ehhez a szóhoz még nincs lexikai adat."
TBESG_DATABASE_MISSING_MESSAGE = "Az angol lexikai adatbázis még nincs előkészítve."
TBESG_SCOPE_NOTE = (
    "Ehhez a szóhoz még nincs ellenőrzött magyar lexikai adat. "
    "Az alábbi angol szócikk a STEPBible TBESG lexikonból származik."
)
TBESG_SOURCE_NOTE = "Lexikai adat: STEPBible TBESG, CC BY 4.0."
LEXICAL_SCOPE_NOTE = (
    "A felsorolt jelentések lexikai lehetőségek. Az adott versben "
    "érvényes jelentést a szövegkörnyezet határozza meg."
)
MISSING_GREEK_DATABASE_MESSAGE = (
    "A teljes görög Újszövetség helyi adatbázisa még nincs előkészítve."
)
TAGNT_DATABASE_BUILD_HINT = (
    "Előkészítés: python scripts/build_tagnt_nt_db.py "
    "--mat-jhn-source ... --act-rev-source ... "
    "--output data/generated/tagnt_nt.sqlite3"
)
CROSS_CHAPTER_GREEK_MESSAGE = (
    "A fejezeten átívelő görög szakaszok támogatása későbbi "
    "fejlesztésben lesz elérhető."
)
REVIEW_STATUS_LABELS = {
    "draft": "munkaváltozat",
    "reviewed": "ellenőrzött",
}

GreekReferenceStatus = Literal[
    "empty",
    "invalid",
    "old_testament",
    "cross_chapter",
    "loaded",
]


@dataclass(frozen=True)
class TokenSelection:
    book: str
    chapter: int
    verse: int
    word_index: int

    @property
    def key(self) -> str:
        return f"{self.book}:{self.chapter}:{self.verse}:{self.word_index}"


def render_greek_analysis_block(
    reference: str,
    key_prefix: str,
    *,
    token_loader: Callable[[], list[GreekToken]] | None = None,
    lexicon_loader: Callable[
        [], dict[str, HungarianLexiconEntry] | None
    ]
    | None = None,
    tbesg_lexicon_loader: Callable[[str], SQLiteGreekLexiconEntry | None]
    | None = None,
) -> None:
    status = greek_reference_status(reference)
    if status in {"empty", "invalid"}:
        return
    if status == "old_testament":
        st.caption(OLD_TESTAMENT_MESSAGE)
        return
    if status == "cross_chapter":
        st.caption(CROSS_CHAPTER_GREEK_MESSAGE)
        return

    passage_loader = token_loader or (lambda: load_greek_passage_tokens(reference))
    lexicon_loader = lexicon_loader or load_demo_hungarian_lexicon
    tbesg_lexicon_loader = tbesg_lexicon_loader or load_tbesg_lexicon_entry
    _ensure_greek_analysis_styles()

    try:
        loaded = passage_loader()
    except FileNotFoundError:
        st.caption(MISSING_GREEK_DATABASE_MESSAGE)
        st.caption(TAGNT_DATABASE_BUILD_HINT)
        return
    except Exception:
        st.caption(GREEK_DATA_ERROR_MESSAGE)
        return

    verse_groups = _coerce_verse_groups(loaded)
    if not verse_groups:
        st.caption(MISSING_GREEK_DATA_MESSAGE)
        return

    try:
        lexicon_entries = lexicon_loader()
    except Exception:
        lexicon_entries = None

    _render_loaded_greek_passage_analysis(
        verse_groups,
        lexicon_entries,
        tbesg_lexicon_loader,
        key_prefix=key_prefix,
        reference_label=_greek_reference_label(reference),
    )


def greek_reference_status(reference: str) -> GreekReferenceStatus:
    raw = (reference or "").strip()
    if not raw:
        return "empty"
    if _looks_like_cross_chapter_reference(raw):
        return "cross_chapter"

    try:
        parsed = parse_tagnt_bible_reference(raw)
    except ValueError:
        return "invalid"

    if parsed.book.code not in NEW_TESTAMENT_RUF_CODES:
        return "old_testament"
    if parsed.verse_start is None:
        return "invalid"

    return "loaded"


@st.cache_data(show_spinner=False)
def load_john_3_16_tokens() -> list[GreekToken]:
    return get_verse_tokens(JHN_3_16_FIXTURE_PATH, book="Jhn", chapter=3, verse=16)


@st.cache_data(show_spinner=False)
def load_demo_hungarian_lexicon() -> dict[str, HungarianLexiconEntry] | None:
    try:
        return load_hungarian_lexicon(LEXICON_HU_PATH)
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_tbesg_lexicon_entry(strong_id: str) -> SQLiteGreekLexiconEntry | None:
    return get_tbesg_lexicon_entry(strong_id)


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


def _render_loaded_greek_passage_analysis(
    verse_groups: list[GreekVerseTokens],
    lexicon_entries: dict[str, HungarianLexiconEntry] | None,
    tbesg_lexicon_loader: Callable[[str], SQLiteGreekLexiconEntry | None],
    *,
    key_prefix: str,
    reference_label: str | None = None,
) -> None:
    all_tokens = _flatten_tokens(verse_groups)
    selected_word_key = _key(key_prefix, "selected_word_index")
    selected_token_key = _key(key_prefix, "selected_token_key")
    reference_state_key = _key(key_prefix, "reference_key")
    fallback_key = _key(key_prefix, "fallback_selector")
    current_reference_key = _verse_groups_key(verse_groups)

    current_selection = _selected_token_key(
        all_tokens,
        st.session_state.get(selected_token_key),
    )
    if st.session_state.get(reference_state_key) != current_reference_key:
        current_selection = _first_token_key(all_tokens)
        st.session_state[reference_state_key] = current_reference_key

    st.session_state[selected_token_key] = current_selection
    st.session_state[selected_word_key] = _word_index_from_token_key(current_selection)
    st.session_state[fallback_key] = _fallback_value(verse_groups, current_selection)

    def sync_component_selection(component_key: str) -> None:
        selected = component_state_token_key(st.session_state.get(component_key), all_tokens)
        st.session_state[selected_token_key] = _apply_token_key_selection(
            all_tokens,
            st.session_state.get(selected_token_key),
            selected,
        )
        st.session_state[selected_word_key] = _word_index_from_token_key(
            st.session_state.get(selected_token_key)
        )

    def sync_fallback_selection() -> None:
        st.session_state[selected_token_key] = _selection_key_from_fallback_value(
            verse_groups,
            st.session_state.get(fallback_key),
        )
        st.session_state[selected_word_key] = _word_index_from_token_key(
            st.session_state.get(selected_token_key)
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

    for verse_group in verse_groups:
        component_key = _key(
            key_prefix,
            f"inline_token_selector_{verse_group.chapter}_{verse_group.verse}",
        )
        st.markdown(
            f'<div class="textus-greek-verse-marker">{verse_group.verse}</div>',
            unsafe_allow_html=True,
        )
        verse_selection = current_selection if _selection_belongs_to_verse(
            current_selection,
            verse_group,
        ) else None
        component_selection = greek_token_selector_value(
            tokens=list(verse_group.tokens),
            selected_token_key=verse_selection,
            key=component_key,
            on_selected_token_key_change=lambda component_key=component_key: sync_component_selection(
                component_key
            ),
        )
        next_selection = _apply_token_key_selection(
            all_tokens,
            current_selection,
            component_selection,
        )
        if next_selection != current_selection:
            st.session_state[selected_token_key] = next_selection
            st.session_state[selected_word_key] = _word_index_from_token_key(next_selection)
            st.session_state[fallback_key] = _fallback_value(verse_groups, next_selection)
            st.rerun()

    st.markdown('<div class="textus-greek-fallback-marker"></div>', unsafe_allow_html=True)
    with st.expander("Alternatív szóválasztás", expanded=False):
        st.selectbox(
            "Token",
            options=_fallback_options(verse_groups),
            key=fallback_key,
            format_func=lambda value: _fallback_label(verse_groups, value),
            on_change=sync_fallback_selection,
        )

    current_selection = _selected_token_key(all_tokens, st.session_state.get(selected_token_key))
    selected = _token_by_selection_key(all_tokens, current_selection)
    _render_analysis_panel(selected, lexicon_entries, tbesg_lexicon_loader)


def _render_loaded_greek_analysis(
    tokens: list[GreekToken],
    lexicon_entries: dict[str, HungarianLexiconEntry] | None,
    tbesg_lexicon_loader: Callable[[str], SQLiteGreekLexiconEntry | None],
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
    _render_analysis_panel(selected, lexicon_entries, tbesg_lexicon_loader)


def _render_analysis_panel(
    selected: GreekToken,
    lexicon_entries: dict[str, HungarianLexiconEntry] | None,
    tbesg_lexicon_loader: Callable[[str], SQLiteGreekLexiconEntry | None],
) -> None:
    st.markdown('<div class="textus-greek-analysis-card-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader(_present(selected.greek_form))
        left, right = st.columns(2, gap="small")
        analysis_items = list(token_analysis(selected).items())
        left.markdown(_compact_field_markup(analysis_items[:3]), unsafe_allow_html=True)
        right.markdown(_compact_field_markup(analysis_items[3:]), unsafe_allow_html=True)
        _render_lexicon_section(selected, lexicon_entries, tbesg_lexicon_loader)


def _render_lexicon_section(
    token: GreekToken,
    entries: dict[str, HungarianLexiconEntry] | None,
    tbesg_lexicon_loader: Callable[[str], SQLiteGreekLexiconEntry | None],
) -> None:
    st.divider()

    if entries is not None:
        entry = _hungarian_lexicon_entry_for_token(entries, token)
        if entry is not None:
            _render_hungarian_lexicon_section(entry)
            return
    else:
        st.markdown(LEXICON_HU_ERROR_MESSAGE)

    tbesg_entry = _tbesg_lexicon_entry_for_token(tbesg_lexicon_loader, token)
    if isinstance(tbesg_entry, TBESGDatabaseUnavailableError):
        st.markdown(TBESG_DATABASE_MISSING_MESSAGE)
        return
    if tbesg_entry is not None:
        _render_tbesg_lexicon_section(tbesg_entry)
        return

    st.markdown(NO_LEXICON_ENTRY_MESSAGE)


def _render_hungarian_lexicon_section(entry: HungarianLexiconEntry) -> None:
    st.markdown("#### Magyar lexikai jelentések")
    st.caption(LEXICAL_SCOPE_NOTE)
    st.markdown(f"**Alapjelentés:** {entry.primary_gloss}")
    st.markdown(f"**Lehetséges jelentések:** {' · '.join(entry.senses)}")

    if entry.note:
        st.markdown(f"**Lexikai megjegyzés:** {entry.note}")

    review_status = REVIEW_STATUS_LABELS.get(entry.review_status, entry.review_status)
    st.markdown(f"**Ellenőrzési állapot:** {review_status}")
    st.caption(f"Forrás: {entry.source}")


def _render_tbesg_lexicon_section(entry: SQLiteGreekLexiconEntry) -> None:
    st.markdown("#### Angol lexikai alapadat")
    st.caption(TBESG_SCOPE_NOTE)
    st.markdown(f"**Alapjelentés:** {_present(entry.gloss)}")

    if entry.lemma:
        st.markdown(f"**Szótári alak:** {entry.lemma}")
    if entry.morph:
        st.markdown(f"**Szófaji jelölés:** {entry.morph}")
    if entry.meaning_plain:
        preview, has_more = _short_lexicon_preview(entry.meaning_plain)
        st.markdown(f"**Részletes leírás:** {preview}")
        if has_more:
            with st.expander("Részletes angol szócikk", expanded=False):
                st.markdown(entry.meaning_plain)
    if entry.references:
        with st.expander("Hivatkozások", expanded=False):
            st.markdown(", ".join(entry.references[:60]))

    st.caption(TBESG_SOURCE_NOTE)


def _compact_field_markup(items: list[tuple[str, str]]) -> str:
    rows = "\n".join(
        f'<div class="textus-greek-field"><strong>{html.escape(label)}:</strong> '
        f"{html.escape(value)}</div>"
        for label, value in items
    )
    return f'<div class="textus-greek-field-list">{rows}</div>'


def _hungarian_lexicon_entry_for_token(
    entries: dict[str, HungarianLexiconEntry],
    token: GreekToken,
) -> HungarianLexiconEntry | None:
    try:
        return get_hungarian_lexicon_entry(entries, token.strong_id)
    except ValueError:
        return None


def _tbesg_lexicon_entry_for_token(
    loader: Callable[[str], SQLiteGreekLexiconEntry | None],
    token: GreekToken,
) -> SQLiteGreekLexiconEntry | TBESGDatabaseUnavailableError | None:
    try:
        return loader(token.strong_id)
    except TBESGDatabaseUnavailableError as error:
        return error
    except (ValueError, FileNotFoundError):
        return None


def _short_lexicon_preview(text: str, limit: int = 700) -> tuple[str, bool]:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact, False

    truncated = compact[:limit].rstrip()
    last_sentence = max(truncated.rfind("."), truncated.rfind(";"), truncated.rfind(":"))
    if last_sentence >= 240:
        truncated = truncated[: last_sentence + 1]
    else:
        truncated = truncated.rstrip(" ,;:")
    return f"{truncated}...", True


def _ensure_greek_analysis_styles() -> None:
    st.markdown(
        """
        <style>
        .textus-greek-analysis-title {
            margin: 0.06rem 0 0;
            font-size: 0.98rem;
            line-height: 1.1;
            font-weight: 700;
        }
        .element-container:has(.textus-greek-analysis-title) {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .textus-greek-analysis-label {
            margin: 0;
            font-size: 0.86rem;
            font-weight: 600;
            line-height: 1.08;
        }
        .element-container:has(.textus-greek-analysis-label) {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .greek-token-selector {
            font-size: 1.12rem;
            line-height: 1.3;
            margin: 0 0 0.02rem;
        }
        .textus-greek-verse-marker {
            float: left;
            min-width: 1.35rem;
            margin: 0.01rem 0.28rem 0 0;
            color: #7a6c5c;
            font-size: 0.7rem;
            font-weight: 700;
            line-height: 1.28;
            text-align: right;
            user-select: none;
        }
        .element-container:has(.textus-greek-verse-marker) {
            margin: 0 !important;
            padding: 0 !important;
            height: 0 !important;
        }
        .greek-token-selector .greek-token {
            margin: 0 0.08rem 0.02rem 0;
            padding: 0 0.06rem;
            line-height: 1.08;
            vertical-align: baseline;
        }
        .greek-token-selector .greek-token[aria-pressed="true"] {
            box-shadow: inset 0 -0.08em 0 var(--st-primary-color, #ff4b4b);
            outline: 1px solid rgba(115, 92, 62, 0.22);
            outline-offset: 0;
        }
        .element-container:has(.textus-greek-analysis-label) + .element-container [data-testid="stCaptionContainer"] {
            margin-top: 0 !important;
            margin-bottom: 0.08rem !important;
            font-size: 0.78rem !important;
            line-height: 1.08 !important;
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
            margin-bottom: 0.03rem !important;
        }
        .element-container:has(.textus-greek-fallback-marker) + .element-container details {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .element-container:has(.textus-greek-fallback-marker) + .element-container summary {
            padding-top: 0.04rem !important;
            padding-bottom: 0.04rem !important;
            min-height: 0 !important;
            line-height: 1.08 !important;
            font-size: 0.84rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) {
            margin: 0 !important;
            padding: 0 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.28rem 0.42rem 0.32rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stVerticalBlock"] {
            gap: 0.03rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container h3 {
            margin: 0 0 0.04rem !important;
            padding: 0 !important;
            line-height: 1.05 !important;
            font-size: 1rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container h4 {
            margin: 0.02rem 0 0.02rem !important;
            padding: 0 !important;
            line-height: 1.08 !important;
            font-size: 0.94rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container .textus-greek-field-list {
            margin: 0 !important;
            line-height: 1.16 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container .textus-greek-field {
            margin: 0 0 0.025rem !important;
            line-height: 1.16 !important;
            font-size: 0.9rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.035rem !important;
            line-height: 1.16 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stMarkdownContainer"] ul {
            margin-top: 0 !important;
            margin-bottom: 0.04rem !important;
            padding-left: 0.85rem !important;
            line-height: 1.12 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stMarkdownContainer"] li {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            line-height: 1.12 !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stDivider"] {
            margin-top: 0.06rem !important;
            margin-bottom: 0.04rem !important;
        }
        .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stCaptionContainer"] {
            margin-bottom: 0.035rem !important;
            line-height: 1.08 !important;
            font-size: 0.78rem !important;
        }
        @media (max-width: 640px) {
            .greek-token-selector {
                font-size: 1.06rem;
                line-height: 1.28;
            }
            .textus-greek-verse-marker {
                min-width: 1.18rem;
                margin-right: 0.22rem;
                font-size: 0.66rem;
            }
            .element-container:has(.textus-greek-analysis-card-marker) + .element-container [data-testid="stVerticalBlockBorderWrapper"] {
                padding: 0.55rem 0.65rem !important;
            }
            .element-container:has(.textus-greek-analysis-card-marker) + .element-container .textus-greek-field {
                font-size: 0.88rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _coerce_verse_groups(
    loaded: list[GreekToken] | list[GreekVerseTokens],
) -> list[GreekVerseTokens]:
    if not loaded:
        return []
    first = loaded[0]
    if isinstance(first, GreekVerseTokens):
        return sorted(loaded, key=lambda item: (item.chapter, item.verse))  # type: ignore[arg-type]

    grouped: dict[tuple[str, int, int], list[GreekToken]] = {}
    for token in loaded:  # type: ignore[assignment]
        grouped.setdefault((token.book, token.chapter, token.verse), []).append(token)
    return [
        GreekVerseTokens(
            book=book,
            chapter=chapter,
            verse=verse,
            tokens=tuple(sorted(tokens, key=lambda token: token.word_index)),
        )
        for (book, chapter, verse), tokens in sorted(grouped.items())
    ]


def _flatten_tokens(verse_groups: list[GreekVerseTokens]) -> list[GreekToken]:
    tokens: list[GreekToken] = []
    for verse_group in verse_groups:
        tokens.extend(verse_group.tokens)
    return tokens


def _token_selection(token: GreekToken) -> TokenSelection:
    return TokenSelection(
        book=token.book,
        chapter=token.chapter,
        verse=token.verse,
        word_index=token.word_index,
    )


def _token_key(token: GreekToken) -> str:
    return _token_selection(token).key


def _first_token_key(tokens: list[GreekToken]) -> str | None:
    return _token_key(tokens[0]) if tokens else None


def _selected_token_key(tokens: list[GreekToken], current: object) -> str | None:
    valid_keys = {_token_key(token) for token in tokens}
    if current is not None and str(current) in valid_keys:
        return str(current)
    return _first_token_key(tokens)


def _apply_token_key_selection(
    tokens: list[GreekToken],
    current: object,
    candidate: object,
) -> str | None:
    if candidate is None:
        return _selected_token_key(tokens, current)
    valid_keys = {_token_key(token) for token in tokens}
    if str(candidate) in valid_keys:
        return str(candidate)
    return _selected_token_key(tokens, current)


def component_state_token_key(component_state: object, tokens: list[GreekToken]) -> str | None:
    if component_state is None:
        return None
    if isinstance(component_state, dict):
        value = component_state.get("selected_token_key")
    else:
        value = getattr(component_state, "selected_token_key", None)
    return _apply_token_key_selection(tokens, None, value)


def _word_index_from_token_key(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).split(":")[-1])
    except ValueError:
        return None


def _selection_belongs_to_verse(
    selection_key: str | None,
    verse_group: GreekVerseTokens,
) -> bool:
    if selection_key is None:
        return False
    return selection_key.startswith(
        f"{verse_group.book}:{verse_group.chapter}:{verse_group.verse}:"
    )


def _verse_groups_key(verse_groups: list[GreekVerseTokens]) -> str:
    return "|".join(
        f"{verse_group.book}:{verse_group.chapter}:{verse_group.verse}:{len(verse_group.tokens)}"
        for verse_group in verse_groups
    )


def _fallback_options(verse_groups: list[GreekVerseTokens]) -> list[int | str]:
    if len(verse_groups) == 1:
        return [token.word_index for token in verse_groups[0].tokens]
    return [_token_key(token) for token in _flatten_tokens(verse_groups)]


def _fallback_value(
    verse_groups: list[GreekVerseTokens],
    selection_key: str | None,
) -> int | str | None:
    if selection_key is None:
        return None
    if len(verse_groups) == 1:
        return _word_index_from_token_key(selection_key)
    return selection_key


def _selection_key_from_fallback_value(
    verse_groups: list[GreekVerseTokens],
    value: object,
) -> str | None:
    if value is None:
        return _first_token_key(_flatten_tokens(verse_groups))
    if len(verse_groups) == 1:
        verse_group = verse_groups[0]
        try:
            word_index = int(value)
        except (TypeError, ValueError):
            return _first_token_key(list(verse_group.tokens))
        for token in verse_group.tokens:
            if token.word_index == word_index:
                return _token_key(token)
        return _first_token_key(list(verse_group.tokens))
    return _selected_token_key(_flatten_tokens(verse_groups), value)


def _fallback_label(verse_groups: list[GreekVerseTokens], value: int | str) -> str:
    selection_key = _selection_key_from_fallback_value(verse_groups, value)
    token = _token_by_selection_key(_flatten_tokens(verse_groups), selection_key)
    if len(verse_groups) == 1:
        return token_option_label(token)
    return f"{token.chapter},{token.verse} / {token.word_index}. {token.greek_form or 'nincs adat'}"


def _token_by_selection_key(
    tokens: list[GreekToken],
    selection_key: str | None,
) -> GreekToken:
    resolved = _selected_token_key(tokens, selection_key)
    for token in tokens:
        if _token_key(token) == resolved:
            return token
    return tokens[0]


def _looks_like_cross_chapter_reference(reference: str) -> bool:
    cleaned = (reference or "").strip().replace("–", "-").replace("—", "-")
    return bool(
        re.match(
            r"^(?:\d\s*)?[^\d,.:]+\s+\d+\s*[,.:]\s*\d+\s*-\s*\d+\s*[,.:]\s*\d+\s*$",
            cleaned,
            flags=re.IGNORECASE,
        )
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
        parsed = parse_tagnt_bible_reference(reference)
    except ValueError:
        return ""
    if parsed.book.code in NEW_TESTAMENT_RUF_CODES and parsed.verse_start is not None:
        if parsed.verse_end is not None and parsed.verse_end != parsed.verse_start:
            return parsed.normalized_reference
        return parsed.normalized_reference
    return parsed.normalized_reference
