"""Részletes vázlat → Íróasztal draft (egyirányú 4C handoff).

Nem hív LLM-et, nem ír sermon structured outline-t a Writing Desk
szerkesztésétől, és nem implementál merge/append/DOCX/chat útvonalat.
"""

from __future__ import annotations

from html import escape
from typing import Any, MutableMapping

from sermon_workshop_data import (
    _DEVELOPED_MOVEMENT_LIST_FIELDS,
    accept_developed_outline_candidate,
    normalize_developed_outline,
)
from writing_desk_data import (
    draft_has_visible_content,
    ensure_writing_desk_state,
    sanitize_draft_html,
    writing_desk_draft_content,
)
from writing_desk_ui import WRITING_DESK_MODE, replace_writing_desk_draft_content


OUTLINE_HANDOFF_CONFIRM_KEY = "_wd_outline_handoff_confirm"

_SUPPORT_LABELS: tuple[tuple[str, str], ...] = (
    ("Szövegi kapaszkodó", "exegetical_support"),
    ("Eredeti nyelvi támasz", "original_language_support"),
    ("Történeti/teológiai támasz", "historical_theological_support"),
    ("Illusztrációs irány", "illustration_direction"),
    ("Alkalmazási irány", "application_direction"),
)

_FORBIDDEN_TECHNICAL_TOKENS: tuple[str, ...] = (
    "developed_outline",
    "developed_outline_candidate",
    "expansion_items",
    "main_claim",
    "transition_to_next",
    "structure_mode",
    "structure_note",
    "exegetical_support",
    "original_language_support",
    "historical_theological_support",
    "illustration_direction",
    "application_direction",
    "movement",
    "movements",
)


def _esc(text: str) -> str:
    return escape(str(text), quote=False)


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _movement_heading(index: int, movement: dict[str, Any]) -> str:
    function = str(movement.get("function") or "").strip()
    title = str(movement.get("title") or "").strip()
    if function and title:
        return f"{index}. {function} / {title}"
    if function:
        return f"{index}. {function}"
    if title:
        return f"{index}. {title}"
    return f"{index}."


def _support_lines(movement: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for label, field in _SUPPORT_LABELS:
        if field in _DEVELOPED_MOVEMENT_LIST_FIELDS:
            items = _str_list(movement.get(field))
            if items:
                lines.append(f"{label}: " + "; ".join(items))
        else:
            value = str(movement.get(field) or "").strip()
            if value:
                lines.append(f"{label}: {value}")
    return lines


def developed_outline_to_draft_html(outline: Any) -> str:
    """Kanonikus/candidate `developed_outline` → 4B szűkített HTML.

    Kulturált munkadokumentum: sorszám, szerep/cím, fő állítás, kibontás,
    átvezetés. Nincs technikai JSON mezőnév.
    """
    normalized = normalize_developed_outline(outline)
    parts: list[str] = []
    note = str(normalized.get("structure_note") or "").strip()
    if note:
        parts.append(f"<p><em>{_esc(note)}</em></p>")

    for index, movement in enumerate(normalized["movements"], start=1):
        parts.append(f"<p><strong>{_esc(_movement_heading(index, movement))}</strong></p>")
        claim = str(movement.get("main_claim") or "").strip()
        if claim:
            parts.append(f"<p>{_esc(claim)}</p>")
        items = _str_list(movement.get("development"))
        if items:
            lis = "".join(f"<li>{_esc(item)}</li>" for item in items)
            parts.append(f"<ul>{lis}</ul>")
        transition = str(movement.get("transition_to_next") or "").strip()
        if transition:
            parts.append(f"<p>Átvezetés: {_esc(transition)}</p>")

    background: list[str] = []
    for index, movement in enumerate(normalized["movements"], start=1):
        lines = _support_lines(movement)
        if not lines:
            continue
        heading = _movement_heading(index, movement)
        background.append(f"<p><strong>{_esc(heading)}</strong></p>")
        for line in lines:
            background.append(f"<p>{_esc(line)}</p>")
    if background:
        parts.append("<p><strong>Háttéranyagok</strong></p>")
        parts.extend(background)

    return sanitize_draft_html("".join(parts))


def draft_html_has_forbidden_technical_tokens(html: str) -> bool:
    lowered = html.casefold()
    return any(token.casefold() in lowered for token in _FORBIDDEN_TECHNICAL_TOKENS)


def writing_desk_draft_needs_overwrite_confirmation(
    session_state: MutableMapping[str, Any],
) -> bool:
    desk = ensure_writing_desk_state(session_state)
    return draft_has_visible_content(writing_desk_draft_content(desk))


def apply_developed_outline_handoff(
    session_state: MutableMapping[str, Any],
    *,
    reference: str,
    context_hash: str,
) -> dict[str, Any]:
    """Proposal elfogadása, majd a kanonikus vázlat átadása az Íróasztalnak.

    Sikertelen accept esetén a durable draft és a `ui_mode` változatlan.
    """
    result = accept_developed_outline_candidate(
        session_state,
        reference=reference,
        context_hash=context_hash,
    )
    session_state[OUTLINE_HANDOFF_CONFIRM_KEY] = False
    if not result.get("accepted"):
        return {**result, "transferred": False}

    html = developed_outline_to_draft_html(result["developed_outline"])
    replace_writing_desk_draft_content(html)
    session_state["ui_mode"] = WRITING_DESK_MODE
    return {**result, "transferred": True, "html": html}


__all__ = [
    "OUTLINE_HANDOFF_CONFIRM_KEY",
    "apply_developed_outline_handoff",
    "developed_outline_to_draft_html",
    "draft_html_has_forbidden_technical_tokens",
    "writing_desk_draft_needs_overwrite_confirmation",
]
