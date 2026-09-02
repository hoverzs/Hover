"""Íróasztal munkakivonatok és jegyzet-vázlat — AI-tól független projektadat.

Csak a beágyazott `writing_desk` session/project struktúrát kezeli.
Nem hív LLM-et, nem írja a teljes `original_text` / `history` / `theology`
forrásmezőket, és nem renderel Streamlit-widgetet.
"""

from __future__ import annotations

import hashlib
import re
from html import escape, unescape
from html.parser import HTMLParser
from typing import Any, Mapping, MutableMapping

WRITING_DESK_KEY = "writing_desk"

DRAFT_HTML_ALLOWED_TAGS: frozenset[str] = frozenset(
    {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li"}
)
_DRAFT_ALIGN_VALUES: frozenset[str] = frozenset({"left", "center", "right", "justify"})
_DRAFT_TEXT_ALIGN_RE = re.compile(
    r"text-align\s*:\s*(left|center|right|justify)\b",
    re.IGNORECASE,
)
_DRAFT_HTML_VOID_TAGS: frozenset[str] = frozenset({"br"})
_DRAFT_HTML_MARK_RE = re.compile(
    r"<(p|br|strong|b|em|i|u|ul|ol|li)(\s|/?>)",
    re.IGNORECASE,
)
_ANY_HTML_TAG_RE = re.compile(r"</?[a-zA-Z!]")
_DRAFT_HTML_SKIP_CONTENT_TAGS: frozenset[str] = frozenset(
    {"script", "style", "noscript"}
)

WRITING_DESK_EXTRACT_KEYS: tuple[str, ...] = (
    "original_text",
    "history",
    "theology",
)


def empty_writing_desk_extract() -> dict[str, str]:
    return {"content": "", "source_fingerprint": ""}


def empty_writing_desk_draft() -> dict[str, str]:
    return {"content": ""}


def get_default_writing_desk() -> dict[str, Any]:
    """Üres Íróasztal-adat (új session / régi projekt hiányzó mező)."""
    return {
        "extracts": {
            key: empty_writing_desk_extract() for key in WRITING_DESK_EXTRACT_KEYS
        },
        "draft": empty_writing_desk_draft(),
    }


def fingerprint_source_text(text: str) -> str:
    """Determinisztikus ujjlenyomat a teljes forrásanyagról.

    Üres vagy csak whitespace forrás → üres string (nincs kivonat-forrás).
    """
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def looks_like_draft_html(text: str) -> bool:
    """Van-e a 4B whitelist szerinti HTML jel a stringben."""
    return bool(_DRAFT_HTML_MARK_RE.search(text or ""))


def _looks_like_any_html(text: str) -> bool:
    """Van-e bármilyen HTML-szerű tag — sanitize vs. 4A plain text."""
    return bool(_ANY_HTML_TAG_RE.search(text or ""))


def _draft_text_align(attrs: list[tuple[str, str | None]]) -> str | None:
    """Csak p/li text-align — minden más stílus kiesik."""
    for raw_name, raw_value in attrs:
        name = (raw_name or "").lower()
        value = str(raw_value or "").strip()
        if name == "align":
            align = value.lower()
            if align in _DRAFT_ALIGN_VALUES:
                return align
        elif name == "style" and value:
            match = _DRAFT_TEXT_ALIGN_RE.search(value)
            if match:
                return match.group(1).lower()
    return None


def _draft_open_tag(name: str, attrs: list[tuple[str, str | None]]) -> str:
    if name not in {"p", "li"}:
        return f"<{name}>"
    align = _draft_text_align(attrs)
    if align and align != "left":
        return f'<{name} style="text-align: {align}">'
    return f"<{name}>"


class _DraftHtmlSanitizer(HTMLParser):
    """Whitelist-szűrő: engedélyezett tagek, p/li text-align kivételével attribútum nélkül."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._stack: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in _DRAFT_HTML_SKIP_CONTENT_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if name == "div":
            align = _draft_text_align(attrs)
            if align and align != "left":
                self._stack.append("p")
                self._parts.append(_draft_open_tag("p", [("style", f"text-align: {align}")]))
            return
        if name not in DRAFT_HTML_ALLOWED_TAGS:
            return
        if name in _DRAFT_HTML_VOID_TAGS:
            self._parts.append(f"<{name}>")
            return
        self._stack.append(name)
        self._parts.append(_draft_open_tag(name, attrs))

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _DRAFT_HTML_SKIP_CONTENT_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if name == "div":
            name = "p"
        if name not in DRAFT_HTML_ALLOWED_TAGS or name in _DRAFT_HTML_VOID_TAGS:
            return
        if name not in self._stack:
            return
        while self._stack:
            top = self._stack.pop()
            self._parts.append(f"</{top}>")
            if top == name:
                break

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if self._skip_depth or name in _DRAFT_HTML_SKIP_CONTENT_TAGS:
            return
        if name in _DRAFT_HTML_VOID_TAGS:
            self._parts.append(f"<{name}>")

    def handle_data(self, data: str) -> None:
        if data and not self._skip_depth:
            self._parts.append(escape(data, quote=False))

    def get_html(self) -> str:
        while self._stack:
            top = self._stack.pop()
            self._parts.append(f"</{top}>")
        return "".join(self._parts)


class _DraftVisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self._parts.append("\n")
        elif tag.lower() in {"p", "li"} and self._parts and not self._parts[-1].endswith("\n"):
            self._parts.append("\n")

    def get_text(self) -> str:
        return "".join(self._parts)


def sanitize_draft_html(raw: Any) -> str:
    """Szűkített HTML, vagy 4A plain text változatlanul (tagek nélkül).

    Tiltott tagek/attribútumok kiesnek; a látható szöveg megmarad.
    """
    text = _as_str(raw).replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return ""
    if not _looks_like_any_html(text):
        return text
    parser = _DraftHtmlSanitizer()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return unescape(re.sub(r"<[^>]+>", "", text))
    return parser.get_html()


def draft_visible_text(raw: Any) -> str:
    """A jegyzet látható szövege — HTML tagek nélkül, dirty/autosave-hez."""
    text = _as_str(raw).replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return ""
    if not _looks_like_any_html(text):
        return text.replace("\xa0", " ")
    extractor = _DraftVisibleTextExtractor()
    try:
        extractor.feed(text)
        extractor.close()
    except Exception:
        return unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return extractor.get_text().replace("\xa0", " ")


def draft_has_visible_content(raw: Any) -> bool:
    return bool(draft_visible_text(raw).strip())


def plain_text_to_draft_html(text: str) -> str:
    """4A plain-text draft → editor-safe HTML. Üres bemenet → üres string."""
    raw = _as_str(text).replace("\r\n", "\n").replace("\r", "\n")
    if not raw:
        return ""
    paragraphs = re.split(r"\n{2,}", raw)
    blocks: list[str] = []
    for paragraph in paragraphs:
        lines = paragraph.split("\n")
        inner = "<br>".join(escape(line, quote=False) for line in lines)
        blocks.append(f"<p>{inner}</p>")
    return "".join(blocks)


def draft_html_for_editor(raw: Any) -> str:
    """Durable content → contenteditable HTML (plain text wrap + sanitize)."""
    sanitized = sanitize_draft_html(raw)
    if not sanitized:
        return ""
    if looks_like_draft_html(sanitized):
        return sanitized
    return plain_text_to_draft_html(sanitized)


def _normalized_draft_content(raw: Any) -> str:
    sanitized = sanitize_draft_html(raw)
    if not draft_has_visible_content(sanitized):
        return ""
    return sanitized


def writing_desk_draft_widget_html(raw: Any) -> str:
    """CCv2 dict / 4A string widgetállapot → HTML vagy plain tartalom."""
    if isinstance(raw, Mapping):
        return _as_str(raw.get("html") if raw.get("html") is not None else raw.get("value"))
    return _as_str(raw)


def writing_desk_draft_widget_state(content: Any) -> dict[str, str]:
    """Durable/plain tartalom → CCv2 widget dict."""
    return {"html": draft_html_for_editor(content)}


def draft_content_from_widget(raw_widget: Any, current_durable: Any) -> str:
    """Widget dict/string → tartós draft.content, 4A wrap-echo nélkül.

    A CCv2 `{"html": ...}` állapot szűkített HTML-t tárol. Ha a tartós
    érték még 4A plain text, és a widget HTML csak ennek megjelenítési
    wrapje, a durable plain marad (nincs csendes migráció).
    """
    incoming = writing_desk_draft_widget_html(raw_widget)
    if isinstance(raw_widget, str):
        return _normalized_draft_content(incoming)
    current = _as_str(current_durable)
    sanitized = sanitize_draft_html(incoming)
    if not looks_like_draft_html(current):
        wrapped = sanitize_draft_html(draft_html_for_editor(current))
        if sanitize_draft_html(sanitized) == wrapped:
            return _normalized_draft_content(current)
    return _normalized_draft_content(sanitized)


def _normalize_extract(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return empty_writing_desk_extract()
    return {
        "content": _as_str(raw.get("content")),
        "source_fingerprint": _as_str(raw.get("source_fingerprint")),
    }


def _normalize_draft(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return empty_writing_desk_draft()
    return {"content": _normalized_draft_content(raw.get("content"))}


def normalize_writing_desk(data: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `writing_desk` struktúrát ad vissza."""
    base = get_default_writing_desk()
    if not isinstance(data, Mapping):
        return base
    raw_extracts = data.get("extracts")
    if not isinstance(raw_extracts, Mapping):
        raw_extracts = {}
    extracts = {
        key: _normalize_extract(raw_extracts.get(key))
        for key in WRITING_DESK_EXTRACT_KEYS
    }
    return {
        "extracts": extracts,
        "draft": _normalize_draft(data.get("draft")),
    }


def writing_desk_draft_content(data: Any) -> str:
    """Jegyzet/vázlat plain-text tartalma. Hiányzó draft → üres string."""
    desk = normalize_writing_desk(data)
    return _as_str((desk.get("draft") or {}).get("content"))


def writing_desk_has_content(data: Any) -> bool:
    """Van-e nem üres munkakivonat vagy jegyzet (dirty-jelzéshez)."""
    desk = normalize_writing_desk(data)
    if any(
        (desk["extracts"][key].get("content") or "").strip()
        for key in WRITING_DESK_EXTRACT_KEYS
    ):
        return True
    return draft_has_visible_content((desk.get("draft") or {}).get("content"))


def ensure_writing_desk_state(session_state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Biztosítja, hogy a session tartalmazzon érvényes `writing_desk` adatot."""
    normalized = normalize_writing_desk(session_state.get(WRITING_DESK_KEY))
    session_state[WRITING_DESK_KEY] = normalized
    return normalized


def set_writing_desk_extract(
    session_state: MutableMapping[str, Any],
    extract_key: str,
    *,
    content: str,
    source_fingerprint: str = "",
) -> dict[str, Any]:
    """Egy munkakivonat tartalmának beállítása. Nem nyúl a teljes forrásmezőkhöz."""
    if extract_key not in WRITING_DESK_EXTRACT_KEYS:
        raise ValueError(f"Ismeretlen Íróasztal-kivonat: {extract_key}")
    desk = ensure_writing_desk_state(session_state)
    desk["extracts"][extract_key] = {
        "content": _as_str(content),
        "source_fingerprint": _as_str(source_fingerprint),
    }
    return desk


def set_writing_desk_draft(
    session_state: MutableMapping[str, Any],
    content: str,
) -> dict[str, Any]:
    """A jegyzet/vázlat tartalmának beállítása. Nem nyúl a kivonatokhoz.

    4A plain text és 4B szűkített HTML egyaránt string a `draft.content`-ben.
    Vizuálisan üres HTML (`<p><br></p>`) üres stringként tárolódik.
    """
    desk = ensure_writing_desk_state(session_state)
    desk["draft"] = {"content": _normalized_draft_content(content)}
    return desk


__all__ = [
    "DRAFT_HTML_ALLOWED_TAGS",
    "WRITING_DESK_EXTRACT_KEYS",
    "WRITING_DESK_KEY",
    "draft_content_from_widget",
    "draft_has_visible_content",
    "draft_html_for_editor",
    "draft_visible_text",
    "empty_writing_desk_draft",
    "empty_writing_desk_extract",
    "ensure_writing_desk_state",
    "fingerprint_source_text",
    "get_default_writing_desk",
    "looks_like_draft_html",
    "normalize_writing_desk",
    "plain_text_to_draft_html",
    "sanitize_draft_html",
    "set_writing_desk_draft",
    "set_writing_desk_extract",
    "writing_desk_draft_content",
    "writing_desk_draft_widget_html",
    "writing_desk_draft_widget_state",
    "writing_desk_has_content",
]
