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

import html
import re
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
STYLES_FLAG = "_bible_text_styles_injected"

SOURCE_CAPTION = (
    f"Forrás: {SOURCE_NAME} — Revideált új fordítás, {COPYRIGHT_NOTICE}."
)

# „17 Ti…”, „17. Ti…”, „17  Ti…” — versszám a sor elején
_VERSE_LINE_RE = re.compile(r"^(\d+)\.?\s+(.*)$")

# A RÚF betöltő gomb saját, kék primary stílusa (ne örökölje a Streamlit
# alapértelmezett piros primary színét; ne érintse a többi gombot).
_BIBLE_TEXT_CSS = """
<style>
.bible-ruf-load-marker {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* Csak a marker utáni gomb — Textus primary kék */
.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"] {
  position: relative !important;
  background:
    linear-gradient(
      155deg,
      #e8eef8 0%,
      #d4e0f2 22%,
      #c5d6ea 48%,
      #b8c9e2 72%,
      #a8bad8 100%
    ) !important;
  color: #1a2838 !important;
  border: 1px solid rgba(122, 145, 176, 0.55) !important;
  border-radius: 14px !important;
  font-family: "Inter", "Segoe UI", sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: 0.01em !important;
  text-transform: none !important;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.85) !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.92) inset,
    0 0 0 1px rgba(255, 255, 255, 0.35) inset,
    0 2px 6px rgba(52, 68, 92, 0.12),
    0 10px 22px rgba(52, 68, 92, 0.16) !important;
}

.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button:hover,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"]:hover {
  background:
    linear-gradient(
      155deg,
      #eef3fb 0%,
      #dde9f6 24%,
      #ccdff0 50%,
      #bcd2e8 74%,
      #aec6df 100%
    ) !important;
  color: #13202e !important;
  border-color: rgba(100, 130, 168, 0.62) !important;
  transform: translateY(-3px) !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.95) inset,
    0 4px 10px rgba(52, 72, 98, 0.14),
    0 14px 28px rgba(52, 72, 98, 0.20),
    0 0 28px rgba(122, 155, 198, 0.22) !important;
}

.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button:active,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"]:active {
  transform: translateY(-1px) !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.75) inset,
    0 2px 5px rgba(52, 68, 92, 0.14),
    0 8px 18px rgba(52, 68, 92, 0.16) !important;
}

.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button > div > p,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"] > div > p {
  color: #1a2838 !important;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.85) !important;
}

.bible-reader {
  margin: 0.35rem 0 0.75rem 0;
  padding: 0.85rem 1rem 0.95rem 1rem;
  max-width: 100%;
  max-height: min(58vh, 520px);
  overflow-y: auto;
  border-radius: 14px;
  border: 1px solid rgba(160, 145, 120, 0.35);
  background:
    linear-gradient(
      165deg,
      rgba(255, 252, 246, 0.92),
      rgba(246, 240, 228, 0.72)
    );
  box-sizing: border-box;
}

.bible-verse {
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
  margin: 0 0 0.72rem 0;
  line-height: 1.68;
}

.bible-verse:last-child,
.bible-para:last-child {
  margin-bottom: 0;
}

.bible-verse-num {
  flex: 0 0 auto;
  min-width: 1.55em;
  font-size: 0.8em;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: #8a7a68;
  line-height: 1.68;
  padding-top: 0.08em;
  user-select: none;
}

.bible-verse-text {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 1.05rem;
  font-weight: 500;
  color: #2a241c;
  line-height: 1.68;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.bible-para {
  margin: 0 0 0.72rem 0;
  font-size: 1.05rem;
  font-weight: 500;
  color: #2a241c;
  line-height: 1.68;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.bible-source-note {
  margin: 0.15rem 0 0.85rem 0;
  font-size: 0.78rem;
  line-height: 1.45;
  color: #7a6c5c;
}

.bible-source-note a {
  color: #4a6a8c;
  text-decoration: underline;
  text-underline-offset: 2px;
}

@media (max-width: 640px) {
  .bible-reader {
    padding: 0.75rem 0.8rem;
    max-height: min(52vh, 440px);
  }
  .bible-verse {
    gap: 0.55rem;
    margin-bottom: 0.65rem;
  }
  .bible-verse-text,
  .bible-para {
    font-size: 1rem;
  }
}
</style>
"""


def normalize_passage_text(value: Any) -> str:
    """Sortörések megőrzése; csak CRLF → LF."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text


def parse_passage_text_blocks(passage_text: str) -> list[tuple[str | None, str]]:
    """passage_text sorok → (verszám|None, szöveg) listája.

    Felismeri: ``17 Ti…``, ``17. Ti…``, ``17  Ti…``.
    Versszám nélküli sor → (None, teljes sor).
    """
    text = normalize_passage_text(passage_text)
    blocks: list[tuple[str | None, str]] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = _VERSE_LINE_RE.match(line)
        if m:
            blocks.append((m.group(1), m.group(2).strip()))
        else:
            blocks.append((None, line))
    return blocks


def build_formatted_bible_text_html(passage_text: str) -> str:
    """Biztonságos HTML a formázott olvasónézethez (escape-elt tartalom)."""
    blocks = parse_passage_text_blocks(passage_text)
    if not blocks:
        return ""
    parts: list[str] = ['<div class="bible-reader">']
    for num, body in blocks:
        safe_body = html.escape(body, quote=True)
        if num is None:
            parts.append(f'<p class="bible-para">{safe_body}</p>')
        else:
            safe_num = html.escape(num, quote=True)
            parts.append(
                '<div class="bible-verse">'
                f'<span class="bible-verse-num">{safe_num}</span>'
                f'<span class="bible-verse-text">{safe_body}</span>'
                "</div>"
            )
    parts.append("</div>")
    return "\n".join(parts)


def render_formatted_bible_text(passage_text: str) -> None:
    """Formázott, csak olvasható Bibliai szöveg előnézet."""
    markup = build_formatted_bible_text_html(passage_text)
    if not markup:
        return
    st.markdown(markup, unsafe_allow_html=True)


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


def _ensure_bible_text_styles() -> None:
    if st.session_state.get(STYLES_FLAG):
        return
    st.session_state[STYLES_FLAG] = True
    st.markdown(_BIBLE_TEXT_CSS, unsafe_allow_html=True)


def _current_reference(session_state: MutableMapping[str, Any]) -> str:
    return (
        str(session_state.get("igehely_input") or "").strip()
        or str(session_state.get(DURABLE_PASSAGE) or "").strip()
    )


def _display_passage_text(session_state: MutableMapping[str, Any]) -> str:
    """Olvasónézet forrása: widget (ha van), különben tartós mező."""
    if KEY_PASSAGE_TEXT_INPUT in session_state:
        widget_text = normalize_passage_text(session_state.get(KEY_PASSAGE_TEXT_INPUT))
        if widget_text.strip():
            return widget_text
    return normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))


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
    caption = html.escape(SOURCE_CAPTION, quote=True)
    if url:
        safe_url = html.escape(url, quote=True)
        st.markdown(
            f'<p class="bible-source-note">{caption}<br/>'
            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">'
            "Megnyitás a forrásoldalon</a></p>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<p class="bible-source-note">{caption}</p>',
            unsafe_allow_html=True,
        )


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


def _render_ruf_load_button() -> None:
    st.markdown('<div class="bible-ruf-load-marker"></div>', unsafe_allow_html=True)
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


def _render_editor_fields(*, save_label: str = "Bibliai szöveg mentése") -> None:
    st.text_area(
        "Teljes bibliai szöveg",
        key=KEY_PASSAGE_TEXT_INPUT,
        height=220,
        placeholder="Töltsd be a RÚF szöveget, vagy illeszd be ide kézzel…",
    )
    if st.button(save_label, key="bible_text_save_btn", use_container_width=True):
        saved = save_bible_text_from_widgets(st.session_state)
        n = len((saved["passage_text"] or "").strip())
        if n:
            st.success(
                f"Bibliai szöveg elmentve ({saved['bible_translation']}) — {n} karakter."
            )
        else:
            st.success("Bibliai szöveg mező elmentve (üres).")


def render_bible_text_editor() -> None:
    """Szerkeszthető Bibliai szöveg blokk (Textusműhely / Igehely szakasz)."""
    _ensure_bible_text_styles()
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
    _render_ruf_load_button()

    display_text = _display_passage_text(st.session_state)
    # Az olvasónézet csak tartós / betöltött szövegnél jelenjen meg —
    # gépelés közben ne csukódjon össze a szerkesztő.
    has_text = bool(
        normalize_passage_text(st.session_state.get(DURABLE_PASSAGE_TEXT)).strip()
    )

    if has_text:
        render_formatted_bible_text(display_text)
        _render_source_caption(st.session_state)
        with st.expander("Bibliai szöveg szerkesztése", expanded=False):
            _render_editor_fields()
    else:
        _render_editor_fields()
        _render_source_caption(st.session_state)


def render_bible_text_preview(*, expanded: bool = False) -> None:
    """Csak olvasható előnézet (Igehirdetési műhely)."""
    _ensure_bible_text_styles()
    snap = get_bible_text_snapshot(st.session_state)
    passage = snap["passage"] or "—"
    translation = snap["bible_translation"] or TRANSLATION_NAME
    text = snap["passage_text"]

    with st.expander("Bibliai szöveg", expanded=expanded):
        st.markdown(f"**Igehely:** {passage}")
        st.markdown(f"**Fordítás:** {translation}")
        if text.strip():
            render_formatted_bible_text(text)
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
    "parse_passage_text_blocks",
    "build_formatted_bible_text_html",
    "render_formatted_bible_text",
    "apply_bible_text_resync_if_needed",
    "queue_bible_widget_sync_values",
    "save_bible_text_from_widgets",
    "get_bible_text_snapshot",
    "render_bible_text_editor",
    "render_bible_text_preview",
]
