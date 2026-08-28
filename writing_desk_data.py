"""Íróasztal munkakivonatok — AI-tól független projektadat.

Csak a beágyazott `writing_desk` session/project struktúrát kezeli.
Nem hív LLM-et, nem írja a teljes `original_text` / `history` / `theology`
forrásmezőket, és nem renderel Streamlit-widgetet.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, MutableMapping

WRITING_DESK_KEY = "writing_desk"

WRITING_DESK_EXTRACT_KEYS: tuple[str, ...] = (
    "original_text",
    "history",
    "theology",
)


def empty_writing_desk_extract() -> dict[str, str]:
    return {"content": "", "source_fingerprint": ""}


def get_default_writing_desk() -> dict[str, Any]:
    """Üres Íróasztal-adat (új session / régi projekt hiányzó mező)."""
    return {
        "extracts": {
            key: empty_writing_desk_extract() for key in WRITING_DESK_EXTRACT_KEYS
        }
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


def _normalize_extract(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return empty_writing_desk_extract()
    return {
        "content": _as_str(raw.get("content")),
        "source_fingerprint": _as_str(raw.get("source_fingerprint")),
    }


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
    return {"extracts": extracts}


def writing_desk_has_content(data: Any) -> bool:
    """Van-e nem üres munkakivonat (dirty-jelzéshez)."""
    desk = normalize_writing_desk(data)
    return any(
        (desk["extracts"][key].get("content") or "").strip()
        for key in WRITING_DESK_EXTRACT_KEYS
    )


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


__all__ = [
    "WRITING_DESK_EXTRACT_KEYS",
    "WRITING_DESK_KEY",
    "empty_writing_desk_extract",
    "ensure_writing_desk_state",
    "fingerprint_source_text",
    "get_default_writing_desk",
    "normalize_writing_desk",
    "set_writing_desk_extract",
    "writing_desk_has_content",
]
