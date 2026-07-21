"""Központi Bibliai szöveg — UI és session-szinkron.

Tartós kulcsok (project_data / workspace):
- `last_igehely`  → igehely (`passage` szerep)
- `bible_translation` → fordítás megnevezése (RÚF 2014 az automatikus betöltésnél)
- `passage_text` → teljes bibliai szöveg
- `passage_text_source` / `passage_text_source_url` / `passage_text_fetched_at`
  / `passage_text_fetched_reference` → forrásmeta (nem a szöveg része)

Widgetkulcsok nem mennek mentésbe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, MutableMapping

import streamlit as st

from ruf_bible_service import (
    COPYRIGHT_NOTICE,
    SOURCE_NAME,
    TRANSLATION_NAME,
    fetch_ruf_passage,
    parse_bible_reference,
)

# Durable session / project keys
DURABLE_PASSAGE_TEXT = "passage_text"
DURABLE_TRANSLATION = "bible_translation"
DURABLE_PASSAGE = "last_igehely"  # meglévő igehely-kulcs
DURABLE_SOURCE = "passage_text_source"
DURABLE_SOURCE_URL = "passage_text_source_url"
DURABLE_FETCHED_AT = "passage_text_fetched_at"
DURABLE_FETCHED_REF = "passage_text_fetched_reference"

# Widget-only
KEY_PASSAGE_TEXT_INPUT = "passage_text_input"
# Legacy widget keys (régi projektek / session; nem rendereljük)
KEY_TRANSLATION_SELECT = "bible_translation_select"
KEY_TRANSLATION_OTHER = "bible_translation_other"
RESYNC_FLAG = "_bible_text_ui_resync"
FLASH_KEY = "_bible_text_flash"

SOURCE_CAPTION = (
    f"Forrás: {SOURCE_NAME} — Revideált új fordítás, {COPYRIGHT_NOTICE}."
)


def normalize_passage_text(value: Any) -> str:
    """Sortörések megőrzése; csak CRLF → LF."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text


def apply_bible_text_resync_if_needed(session_state: MutableMapping[str, Any]) -> None:
    """Widgetkulcsok szinkronja a tartós mezőkkel (widget létrehozása előtt)."""
    force = bool(session_state.pop(RESYNC_FLAG, False))
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))

    if force or KEY_PASSAGE_TEXT_INPUT not in session_state:
        session_state[KEY_PASSAGE_TEXT_INPUT] = text


def queue_bible_widget_sync_values(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    """Pending project widget sync dict-be tehető értékek."""
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))
    return {KEY_PASSAGE_TEXT_INPUT: text}


def save_bible_text_from_widgets(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    """Widgetek → tartós passage_text / bible_translation (és last_igehely szinkron)."""
    ige = str(session_state.get("igehely_input") or "").strip()
    if ige:
        session_state[DURABLE_PASSAGE] = ige

    text = normalize_passage_text(session_state.get(KEY_PASSAGE_TEXT_INPUT))
    session_state[DURABLE_PASSAGE_TEXT] = text

    # A központi blokk RÚF 2014-re van szabva (automatikus + kézi).
    translation = TRANSLATION_NAME
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
        "bible_translation": str(
            session_state.get(DURABLE_TRANSLATION) or TRANSLATION_NAME
        ).strip()
        or TRANSLATION_NAME,
        "passage_text": normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT)),
        "passage_text_source": str(session_state.get(DURABLE_SOURCE) or "").strip(),
        "passage_text_source_url": str(session_state.get(DURABLE_SOURCE_URL) or "").strip(),
        "passage_text_fetched_at": str(session_state.get(DURABLE_FETCHED_AT) or "").strip(),
        "passage_text_fetched_reference": str(
            session_state.get(DURABLE_FETCHED_REF) or ""
        ).strip(),
    }


def _current_reference(session_state: MutableMapping[str, Any]) -> str:
    return (
        str(session_state.get("igehely_input") or "").strip()
        or str(session_state.get(DURABLE_PASSAGE) or "").strip()
    )


def _refs_equivalent(a: str, b: str) -> bool:
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return (
            parse_bible_reference(a).normalized_reference
            == parse_bible_reference(b).normalized_reference
        )
    except ValueError:
        return a.casefold() == b.casefold()


def _set_flash(kind: str, text: str) -> None:
    st.session_state[FLASH_KEY] = {"type": kind, "text": text}


def _render_flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if not isinstance(flash, dict):
        return
    text = str(flash.get("text") or "").strip()
    if not text:
        return
    kind = flash.get("type") or "info"
    if kind == "error":
        st.error(text)
    elif kind == "warning":
        st.warning(text)
    elif kind == "success":
        st.success(text)
    else:
        st.info(text)


def _apply_ruf_fetch_success(result: dict[str, Any]) -> None:
    text = normalize_passage_text(result.get("text"))
    st.session_state[DURABLE_PASSAGE_TEXT] = text
    st.session_state[DURABLE_TRANSLATION] = TRANSLATION_NAME
    st.session_state[DURABLE_SOURCE] = SOURCE_NAME
    st.session_state[DURABLE_SOURCE_URL] = str(result.get("source_url") or "")
    st.session_state[DURABLE_FETCHED_AT] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    st.session_state[DURABLE_FETCHED_REF] = str(
        result.get("normalized_reference") or result.get("requested_reference") or ""
    )
    # Igehely tartósítás, ha van bemenet
    ige = _current_reference(st.session_state)
    if ige:
        st.session_state[DURABLE_PASSAGE] = ige
    st.session_state[RESYNC_FLAG] = True
    _set_flash(
        "success",
        "A RÚF 2014 szövege betöltődött. Mentés előtt ellenőrizd az igehelyet és a szöveget.",
    )


def _render_source_caption(session_state: MutableMapping[str, Any]) -> None:
    snap = get_bible_text_snapshot(session_state)
    if snap["passage_text_source"] != SOURCE_NAME and not snap["passage_text_source_url"]:
        return
    url = snap["passage_text_source_url"]
    if url:
        st.caption(f"{SOURCE_CAPTION}  \n[Megnyitás a forrásoldalon]({url})")
    else:
        st.caption(SOURCE_CAPTION)


def _render_reference_mismatch_warning(session_state: MutableMapping[str, Any]) -> None:
    fetched = str(session_state.get(DURABLE_FETCHED_REF) or "").strip()
    current = _current_reference(session_state)
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))
    if not fetched or not current or not text.strip():
        return
    if _refs_equivalent(fetched, current):
        return
    st.warning(
        f"Az igehely ({current}) különbözik a szöveg utolsó RÚF-betöltésekor "
        f"használt helytől ({fetched}). A mentett szöveg nem törlődött — "
        "szükség esetén töltsd be újra vagy szerkeszd kézzel."
    )


def render_bible_text_editor() -> None:
    """Szerkeszthető Bibliai szöveg blokk (Textusműhely / Igehely szakasz)."""
    apply_bible_text_resync_if_needed(st.session_state)

    st.markdown("### Bibliai szöveg")
    st.caption(
        "Az igehely megadása után töltsd be a RÚF 2014 szöveget, "
        "vagy illeszd be kézzel. Ellenőrizd, hogy a szöveg megfelel-e "
        "a megadott igehelynek."
    )
    st.markdown(f"**Fordítás:** {TRANSLATION_NAME}")

    _render_flash()
    _render_reference_mismatch_warning(st.session_state)

    if st.button(
        "RÚF-szöveg betöltése",
        key="bible_text_ruf_load_btn",
        type="primary",
        use_container_width=True,
        help="A megadott igehely RÚF 2014 szövegét a szentiras.hu-ról tölti be.",
    ):
        ref = _current_reference(st.session_state)
        if not ref:
            st.error("Előbb add meg az igehelyet (pl. Júd 17–20).")
        else:
            with st.spinner("RÚF szöveg betöltése a szentiras.hu-ról…"):
                result = fetch_ruf_passage(ref)
            if result.get("success"):
                _apply_ruf_fetch_success(result)
                st.rerun()
            else:
                err = str(result.get("error") or "A RÚF-szöveg betöltése nem sikerült.")
                st.error(err)
                st.info("A kézi beillesztés továbbra is elérhető.")

    st.text_area(
        "Teljes bibliai szöveg",
        key=KEY_PASSAGE_TEXT_INPUT,
        height=220,
        placeholder="Töltsd be a RÚF szöveget, vagy illeszd be ide kézzel…",
    )

    _render_source_caption(st.session_state)

    if st.button(
        "Bibliai szöveg mentése",
        key="bible_text_save_btn",
        use_container_width=True,
    ):
        saved = save_bible_text_from_widgets(st.session_state)
        n = len((saved["passage_text"] or "").strip())
        if n:
            st.success(
                f"Bibliai szöveg elmentve ({saved['bible_translation']}) — {n} karakter."
            )
        else:
            st.success("Bibliai szöveg mező elmentve (üres).")


def render_bible_text_preview(*, expanded: bool = False) -> None:
    """Csak olvasható előnézet (Igehirdetési műhely)."""
    snap = get_bible_text_snapshot(st.session_state)
    passage = snap["passage"] or "—"
    translation = snap["bible_translation"] or TRANSLATION_NAME
    text = snap["passage_text"]

    with st.expander("Bibliai szöveg", expanded=expanded):
        st.markdown(f"**Igehely:** {passage}")
        st.markdown(f"**Fordítás:** {translation}")
        if text.strip():
            preview = text if len(text) <= 2500 else text[:2499].rstrip() + "…"
            st.text(preview)
            if len(text) > 2500:
                st.caption("A teljes szöveg hosszabb — a Textusműhelyben szerkeszthető.")
            _render_source_caption(st.session_state)
        else:
            st.caption(
                "Még nincs bibliai szöveg. "
                "Töltsd be vagy add meg a Textusműhelyben."
            )


__all__ = [
    "DURABLE_PASSAGE_TEXT",
    "DURABLE_TRANSLATION",
    "DURABLE_PASSAGE",
    "DURABLE_SOURCE",
    "DURABLE_SOURCE_URL",
    "DURABLE_FETCHED_AT",
    "DURABLE_FETCHED_REF",
    "KEY_PASSAGE_TEXT_INPUT",
    "KEY_TRANSLATION_SELECT",
    "KEY_TRANSLATION_OTHER",
    "RESYNC_FLAG",
    "TRANSLATION_NAME",
    "normalize_passage_text",
    "apply_bible_text_resync_if_needed",
    "queue_bible_widget_sync_values",
    "save_bible_text_from_widgets",
    "get_bible_text_snapshot",
    "render_bible_text_editor",
    "render_bible_text_preview",
]
