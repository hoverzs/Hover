"""Közös workspace / project_data kulcsok és összeállítás.

Az app.py fájlmentése és a Supabase project_data ugyanebből a
kulcskészletből épül. Futásidejű / titkos / widget állapot nem kerül bele.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping

from textus_workshop_data import (
    TEXT_WORKSHOP_KEY,
    normalize_text_workshop,
)

# Meglévő workspace-export kulcsok (app.py serialize_workspace).
WORKSPACE_STR_KEYS: list[str] = [
    "last_igehely",
    "last_alkalom",
    "last_stilus",
    "last_sajat",
    "overview",
    "exegesis",
    "history",
    "theology",
    "illustrations",
    "actualization",
    "outline",
    "outline_draft",
    "outline_workshop_questions",
    "outline_workshop_answers",
    "outline_reworked_draft",
    "outline_title_suggestions",
    "original_text",
    "songs",
    "series_planner_output",
    "series_idea",
]

WORKSPACE_LIST_KEYS: list[str] = [
    "basket",
    "verse_history",
    "exegesis_chat",
    "history_chat",
    "theology_chat",
    "illustrations_chat",
    "actualization_chat",
    "outline_chat",
    "original_text_chat",
    "songs_chat",
]

WORKSPACE_KEYS: list[str] = WORKSPACE_STR_KEYS + WORKSPACE_LIST_KEYS

# Tartós projektmezők a workspace-en felül (session defaults).
PROJECT_EXTRA_STR_KEYS: list[str] = [
    "series_cadence",
]

PROJECT_EXTRA_INT_KEYS: list[str] = [
    "series_weeks",
]

# Beágyazott objektumok a tartós project_data-ban (Textus 2.0).
PROJECT_NESTED_KEYS: list[str] = [
    TEXT_WORKSHOP_KEY,
]

PROJECT_DATA_STR_KEYS: list[str] = WORKSPACE_STR_KEYS + PROJECT_EXTRA_STR_KEYS
PROJECT_DATA_INT_KEYS: list[str] = list(PROJECT_EXTRA_INT_KEYS)
PROJECT_DATA_LIST_KEYS: list[str] = list(WORKSPACE_LIST_KEYS)
PROJECT_DATA_KEYS: list[str] = (
    PROJECT_DATA_STR_KEYS
    + PROJECT_DATA_INT_KEYS
    + PROJECT_DATA_LIST_KEYS
    + PROJECT_NESTED_KEYS
)

# Szándékosan soha nem kerül a project_data / workspace JSON-ba.
EXCLUDED_SESSION_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "using_builtin_key",
        "user_model_choice",
        "model_name",
        "temperature",
        "api_key_input",
        "_call_cache",
        "_debug_log",
        "_last_api_call_ts",
        "_session_uuid",
        "enable_cache",
        "_overview_running",
        "_outline_running",
        "_outline_questions_running",
        "_outline_rework_running",
        "_outline_final_running",
        "_outline_titles_running",
        "_original_running",
        "_songs_running",
        "igehely_input",
        "alkalom_input",
        "stilus_input",
        "sajat_input",
        "_outline_draft_editor",
        "_outline_answers_editor",
        "_outline_reworked_editor",
        "_pending_outline_draft_editor",
        "_clear_outline_workshop_editors",
        "_feedback_last_sent",
        # Felületi nézetkulcsok — ne kerüljenek tartós mentésbe
        "ui_mode",
        "tw_active_section",
        "tw_main_idea_input",
        "tw_main_idea_status_radio",
        "_tw_ui_resync",
    }
)


def build_workspace_payload(
    *,
    version: str,
    state: Mapping[str, Any],
    app_name: str = "Textus",
) -> dict[str, Any]:
    """Ugyanaz a tartalom, mint az app.py `serialize_workspace()` payloadja."""
    payload: dict[str, Any] = {
        "_app": app_name,
        "_version": version,
        "_saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    for key in WORKSPACE_STR_KEYS:
        payload[key] = state.get(key, "")
    for key in WORKSPACE_LIST_KEYS:
        value = state.get(key, [])
        payload[key] = list(value) if isinstance(value, list) else []
    return payload


def build_project_data(
    state: Mapping[str, Any],
    *,
    version: str | None = None,
    app_name: str = "Textus",
) -> dict[str, Any]:
    """Tartós projekt JSON a workspace-serializáció alapján (+ sorozatmezők)."""
    payload = build_workspace_payload(
        version=version or "",
        state=state,
        app_name=app_name,
    )
    if not version:
        payload.pop("_version", None)

    for key in PROJECT_EXTRA_STR_KEYS:
        payload[key] = state.get(key, "")

    for key in PROJECT_EXTRA_INT_KEYS:
        raw = state.get(key, 4)
        try:
            payload[key] = int(raw)
        except (TypeError, ValueError):
            payload[key] = 4

    # Textus 2.0 műhelyadat — hiányzó / hibás érték esetén alapértelmezett
    payload[TEXT_WORKSHOP_KEY] = normalize_text_workshop(state.get(TEXT_WORKSHOP_KEY))

    # Biztonsági szűrés: kizárt / titkos / futásidejű kulcsok soha ne maradjanak.
    for excluded in EXCLUDED_SESSION_KEYS:
        payload.pop(excluded, None)

    return sanitize_project_data(payload)


def sanitize_project_data(project_data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Csak a engedélyezett tartós kulcsokat (+ meta) hagyja meg."""
    if not isinstance(project_data, Mapping):
        return {}
    allowed = set(PROJECT_DATA_KEYS) | {"_app", "_version", "_saved_at"}
    clean: dict[str, Any] = {}
    for key, value in project_data.items():
        if key in EXCLUDED_SESSION_KEYS:
            continue
        if key not in allowed:
            continue
        if key == TEXT_WORKSHOP_KEY:
            clean[key] = normalize_text_workshop(value)
        else:
            clean[key] = value
    return clean


def project_content_fingerprint(state: Mapping[str, Any]) -> str:
    """Tartós projektmezők ujjlenyomata (dirty-jelzéshez; meta nélkül)."""
    payload: dict[str, Any] = {}
    for key in PROJECT_DATA_STR_KEYS:
        payload[key] = state.get(key, "")
    for key in PROJECT_DATA_INT_KEYS:
        raw = state.get(key, 4)
        try:
            payload[key] = int(raw)
        except (TypeError, ValueError):
            payload[key] = 4
    for key in PROJECT_DATA_LIST_KEYS:
        value = state.get(key, [])
        payload[key] = list(value) if isinstance(value, list) else []
    payload[TEXT_WORKSHOP_KEY] = normalize_text_workshop(state.get(TEXT_WORKSHOP_KEY))
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "WORKSPACE_STR_KEYS",
    "WORKSPACE_LIST_KEYS",
    "WORKSPACE_KEYS",
    "PROJECT_DATA_KEYS",
    "PROJECT_NESTED_KEYS",
    "build_workspace_payload",
    "build_project_data",
    "sanitize_project_data",
    "project_content_fingerprint",
]
