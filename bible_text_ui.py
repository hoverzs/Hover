"""Központi Bibliai szöveg — UI és session-szinkron.

Tartós kulcsok (project_data / workspace):
- `last_igehely`  → igehely (`passage` szerep)
- `bible_translation` → fordítás megnevezése (felhasználói jelölés)
- `passage_text` → teljes bibliai szöveg (kézi beillesztés)

Widgetkulcsok nem mennek mentésbe.
"""

from __future__ import annotations

from typing import Any, MutableMapping

import streamlit as st

# Durable session / project keys
DURABLE_PASSAGE_TEXT = "passage_text"
DURABLE_TRANSLATION = "bible_translation"
DURABLE_PASSAGE = "last_igehely"  # meglévő igehely-kulcs

# Widget-only
KEY_PASSAGE_TEXT_INPUT = "passage_text_input"
KEY_TRANSLATION_SELECT = "bible_translation_select"
KEY_TRANSLATION_OTHER = "bible_translation_other"
RESYNC_FLAG = "_bible_text_ui_resync"

TRANSLATION_NONE = "(nincs megadva)"
TRANSLATION_OTHER = "Egyéb"
TRANSLATION_OPTIONS = [
    TRANSLATION_NONE,
    "RÚF 2014",
    "Károli",
    "Új fordítás 1990",
    "EFO",
    "SZIT",
    TRANSLATION_OTHER,
]

KNOWN_NAMED = [o for o in TRANSLATION_OPTIONS if o not in (TRANSLATION_NONE, TRANSLATION_OTHER)]


def normalize_passage_text(value: Any) -> str:
    """Sortörések megőrzése; csak CRLF → LF."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text


def translation_to_widgets(stored: str) -> tuple[str, str]:
    """Tartós fordításnév → (select érték, egyéb mező)."""
    name = (stored or "").strip()
    if not name:
        return TRANSLATION_NONE, ""
    if name in KNOWN_NAMED:
        return name, ""
    return TRANSLATION_OTHER, name


def widgets_to_translation(select_value: str, other_value: str) -> str:
    sel = (select_value or "").strip()
    if not sel or sel == TRANSLATION_NONE:
        return ""
    if sel == TRANSLATION_OTHER:
        return (other_value or "").strip()
    return sel


def apply_bible_text_resync_if_needed(session_state: MutableMapping[str, Any]) -> None:
    """Widgetkulcsok szinkronja a tartós mezőkkel (widget létrehozása előtt)."""
    force = bool(session_state.pop(RESYNC_FLAG, False))
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))
    stored_tr = str(session_state.get(DURABLE_TRANSLATION) or "")
    select_val, other_val = translation_to_widgets(stored_tr)

    if force or KEY_PASSAGE_TEXT_INPUT not in session_state:
        session_state[KEY_PASSAGE_TEXT_INPUT] = text
    if force or KEY_TRANSLATION_SELECT not in session_state:
        session_state[KEY_TRANSLATION_SELECT] = select_val
    if force or KEY_TRANSLATION_OTHER not in session_state:
        session_state[KEY_TRANSLATION_OTHER] = other_val


def queue_bible_widget_sync_values(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    """Pending project widget sync dict-be tehető értékek."""
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))
    select_val, other_val = translation_to_widgets(
        str(session_state.get(DURABLE_TRANSLATION) or "")
    )
    return {
        KEY_PASSAGE_TEXT_INPUT: text,
        KEY_TRANSLATION_SELECT: select_val,
        KEY_TRANSLATION_OTHER: other_val,
    }


def save_bible_text_from_widgets(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    """Widgetek → tartós passage_text / bible_translation (és last_igehely szinkron)."""
    ige = str(session_state.get("igehely_input") or "").strip()
    if ige:
        session_state[DURABLE_PASSAGE] = ige

    text = normalize_passage_text(session_state.get(KEY_PASSAGE_TEXT_INPUT))
    session_state[DURABLE_PASSAGE_TEXT] = text

    translation = widgets_to_translation(
        str(session_state.get(KEY_TRANSLATION_SELECT) or ""),
        str(session_state.get(KEY_TRANSLATION_OTHER) or ""),
    )
    session_state[DURABLE_TRANSLATION] = translation
    return {
        "passage": str(session_state.get(DURABLE_PASSAGE) or ""),
        "bible_translation": translation,
        "passage_text": text,
    }


def get_bible_text_snapshot(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    return {
        "passage": (
            str(session_state.get(DURABLE_PASSAGE) or "").strip()
            or str(session_state.get("igehely_input") or "").strip()
        ),
        "bible_translation": str(session_state.get(DURABLE_TRANSLATION) or "").strip(),
        "passage_text": normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT)),
    }


def render_bible_text_editor() -> None:
    """Szerkeszthető Bibliai szöveg blokk (Textusműhely / Igehely szakasz)."""
    apply_bible_text_resync_if_needed(st.session_state)

    st.markdown("### Bibliai szöveg")
    st.caption(
        "Illeszd be ide az igeszakasz teljes szövegét. "
        "Ellenőrizd, hogy a bemásolt szöveg megfelel-e a megadott igehelynek "
        "és bibliafordításnak."
    )

    st.selectbox(
        "Bibliafordítás",
        options=TRANSLATION_OPTIONS,
        key=KEY_TRANSLATION_SELECT,
        help="Felhasználói jelölés — a rendszer nem ellenőrzi a fordítás azonosságát.",
    )
    if st.session_state.get(KEY_TRANSLATION_SELECT) == TRANSLATION_OTHER:
        st.text_input(
            "Fordítás neve (egyéb)",
            key=KEY_TRANSLATION_OTHER,
            placeholder="Pl. saját megnevezés…",
        )

    st.text_area(
        "Teljes bibliai szöveg",
        key=KEY_PASSAGE_TEXT_INPUT,
        height=220,
        placeholder="Illeszd be ide az igeszakasz szövegét…",
    )

    if st.button("Bibliai szöveg mentése", key="bible_text_save_btn", type="primary"):
        saved = save_bible_text_from_widgets(st.session_state)
        n = len((saved["passage_text"] or "").strip())
        if n:
            st.success(
                f"Bibliai szöveg elmentve"
                + (f" ({saved['bible_translation']})" if saved["bible_translation"] else "")
                + f" — {n} karakter."
            )
        else:
            st.success("Bibliai szöveg mező elmentve (üres).")


def render_bible_text_preview(*, expanded: bool = False) -> None:
    """Csak olvasható előnézet (Igehirdetési műhely)."""
    snap = get_bible_text_snapshot(st.session_state)
    passage = snap["passage"] or "—"
    translation = snap["bible_translation"] or "—"
    text = snap["passage_text"]

    with st.expander("Bibliai szöveg", expanded=expanded):
        st.markdown(f"**Igehely:** {passage}")
        st.markdown(f"**Fordítás:** {translation}")
        if text.strip():
            # Ésszerű magasság: hosszú szöveg scrollolható markdown / text
            preview = text if len(text) <= 2500 else text[:2499].rstrip() + "…"
            st.text(preview)
            if len(text) > 2500:
                st.caption("A teljes szöveg hosszabb — a Textusműhelyben szerkeszthető.")
        else:
            st.caption(
                "Még nincs bemásolt bibliai szöveg. "
                "Add meg a Textusműhely „Igehely, alkalom és szövegkörnyezet” szakaszában."
            )


__all__ = [
    "DURABLE_PASSAGE_TEXT",
    "DURABLE_TRANSLATION",
    "DURABLE_PASSAGE",
    "KEY_PASSAGE_TEXT_INPUT",
    "KEY_TRANSLATION_SELECT",
    "KEY_TRANSLATION_OTHER",
    "RESYNC_FLAG",
    "normalize_passage_text",
    "apply_bible_text_resync_if_needed",
    "queue_bible_widget_sync_values",
    "save_bible_text_from_widgets",
    "get_bible_text_snapshot",
    "render_bible_text_editor",
    "render_bible_text_preview",
]
