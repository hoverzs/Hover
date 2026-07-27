from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Any

import streamlit as st

from bible_engine.tagnt_parser import GreekToken


_COMPONENT_DIR = Path(__file__).parent
_FRONTEND_DIR = _COMPONENT_DIR / "frontend"


def greek_token_selector(
    tokens: list[GreekToken],
    selected_word_index: int,
    key: str,
    on_selected_word_index_change: Callable[[], None] | None = None,
) -> int | None:
    component = _component()
    result = component(
        data={
            "tokens": component_tokens(tokens, selected_word_index),
            "selected_word_index": selected_word_index,
        },
        key=key,
        on_selected_word_index_change=on_selected_word_index_change
        if on_selected_word_index_change is not None
        else lambda: None,
    )
    return normalize_component_selection(
        getattr(result, "selected_word_index", None), tokens
    )


def _component():
    return st.components.v2.component(
        "greek_token_selector",
        html=(_FRONTEND_DIR / "index.html").read_text(encoding="utf-8"),
        css=(_FRONTEND_DIR / "style.css").read_text(encoding="utf-8"),
        js=(_FRONTEND_DIR / "main.js").read_text(encoding="utf-8"),
    )


def component_tokens(
    tokens: list[GreekToken], selected_word_index: int
) -> list[dict[str, int | str | bool]]:
    return [
        {
            "word_index": token.word_index,
            "greek_form": token.greek_form,
            "selected": token.word_index == selected_word_index,
        }
        for token in sorted(tokens, key=lambda token: token.word_index)
    ]


def normalize_component_selection(value: Any, tokens: list[GreekToken]) -> int | None:
    valid_indexes = {token.word_index for token in tokens}
    try:
        selected = int(value)
    except (TypeError, ValueError):
        return None
    return selected if selected in valid_indexes else None
