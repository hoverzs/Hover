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
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    normalize_sermon_workshop,
)

# Meglévő workspace-export kulcsok (app.py serialize_workspace).
WORKSPACE_STR_KEYS: list[str] = [
    "last_igehely",
    "last_alkalom",
    "last_stilus",
    "last_sajat",
    "bible_translation",
    "passage_text",
    "passage_text_source",
    "passage_text_source_url",
    "passage_text_fetched_at",
    "passage_text_fetched_reference",
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
    SERMON_WORKSHOP_KEY,
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
        "passage_text_input",
        "bible_translation_select",
        "bible_translation_other",
        "_bible_text_ui_resync",
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
        "_tw_main_idea_adopt_pending",
        "_main_idea_suggest_running",
        "_main_idea_assess_running",
        "sw_active_section",
        "sw_sermon_main_idea_input",
        "sw_hc_condition",
        "sw_hc_false_response",
        "sw_hc_human_need",
        "sw_hc_divine_action",
        "sw_hc_grace_response",
        "_sw_ui_resync",
        "_sw_sermon_idea_adopt_pending",
        "_sw_hc_adopt_pending",
        "_sw_m4_suggest_running",
        "_sw_m4_assess_running",
        "sw_lt_listener_question",
        "sw_lt_listener_resistance",
        "sw_lt_sermon_tension",
        "_sw_lt_adopt_pending",
        "_sw_m5_suggest_running",
        "_sw_m5_assess_running",
        "sw_ga_divine_gracious_action",
        "sw_ga_christ_connection",
        "sw_ga_christ_connection_type",
        "sw_ga_promised_resolution",
        "sw_ga_grace_enabled_response",
        "_sw_ga_adopt_pending",
        "_sw_m5_ga_suggest_running",
        "_sw_m5_ga_assess_running",
        "sw_path_type",
        "sw_path_reason",
        "sw_path_starting_point",
        "sw_path_destination",
        "_sw_path_adopt_pending",
        "_sw_movements_adopt_pending",
        "_sw_mv_delete_pending",
        "_sw_m6_suggest_running",
        "_sw_m6_assess_running",
        "_sw_en_adopt_all_pending",
        "_sw_en_adopt_images_pending",
        "_sw_en_adopt_ill_pending",
        "_sw_en_adopt_apps_pending",
        "_sw_en_img_delete_pending",
        "_sw_en_ill_delete_pending",
        "_sw_en_app_delete_pending",
        "_sw_m7_suggest_running",
        "_sw_m7_assess_running",
        "sw_cl_type",
        "sw_cl_final_discovery",
        "sw_cl_hope",
        "sw_cl_call_or_response",
        "sw_cl_image_or_line",
        "sw_cl_open_question",
        "sw_cl_tone",
        "_sw_cl_adopt_pending",
        "_sw_m7_cl_suggest_running",
        "_sw_m7_cl_assess_running",
        "sw_diag_self_strengths",
        "sw_diag_self_uncertainties",
        "sw_diag_self_priority",
        "sw_diag_self_focus",
        "sw_lection_reference",
        "sw_lection_connection_type",
        "sw_lection_function",
        "sw_lection_rationale",
        "sw_lection_text",
        "sw_lection_notes",
        "sw_lection_testament_preference",
        "sw_lection_length_preference",
        "sw_lection_user_focus",
        "_sw_lection_adopt_pending",
        "_sw_lection_ruf_pending",
        "sw_prayer_tone",
        "sw_prayer_general_focus",
        "sw_prayer_rewrite_mode",
        "sw_prayer_before_own_thoughts",
        "sw_prayer_before_purpose",
        "sw_prayer_before_movement_notes",
        "sw_prayer_before_selected_opening",
        "sw_prayer_before_selected_lines",
        "sw_prayer_before_closing_direction",
        "sw_prayer_after_own_thoughts",
        "sw_prayer_after_purpose",
        "sw_prayer_after_movement_notes",
        "sw_prayer_after_selected_opening",
        "sw_prayer_after_selected_lines",
        "sw_prayer_after_closing_direction",
        "_sw_prayer_adopt_pending",
        "sw_outline_main_idea",
        "sw_outline_main_idea_summary",
        "sw_outline_listener_question",
        "sw_outline_central_tension",
        "sw_outline_listener_resistance",
        "sw_outline_divine_action",
        "sw_outline_christ_connection",
        "sw_outline_christ_type",
        "sw_outline_gospel_resolution",
        "sw_outline_grace_response",
        "sw_outline_opening",
        "sw_outline_manual_notes",
        "sw_outline_closing_final",
        "sw_outline_closing_hope",
        "sw_outline_closing_invitation",
        "sw_outline_closing_image",
        "sw_outline_closing_question",
        "sw_outline_closing_tone",
        "sw_outline_lection_ref",
        "sw_outline_lection_function",
        "sw_outline_lection_rationale",
        "sw_outline_prayer_before_own",
        "sw_outline_prayer_before_opening",
        "sw_outline_prayer_before_lines",
        "sw_outline_prayer_before_closing",
        "sw_outline_prayer_after_own",
        "sw_outline_prayer_after_opening",
        "sw_outline_prayer_after_lines",
        "sw_outline_prayer_after_closing",
        "_sw_outline_confirm_overwrite",
        "_sw_outline_running",
        "_sw_outline_diag_running",
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
    payload[SERMON_WORKSHOP_KEY] = normalize_sermon_workshop(
        state.get(SERMON_WORKSHOP_KEY)
    )

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
        elif key == SERMON_WORKSHOP_KEY:
            clean[key] = normalize_sermon_workshop(value)
        else:
            clean[key] = value
    # Régi projektek: hiányzó új string mezők biztonságos alapértéke
    for key in (
        "bible_translation",
        "passage_text",
        "passage_text_source",
        "passage_text_source_url",
        "passage_text_fetched_at",
        "passage_text_fetched_reference",
    ):
        if key not in clean:
            clean[key] = ""
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
    payload[SERMON_WORKSHOP_KEY] = normalize_sermon_workshop(
        state.get(SERMON_WORKSHOP_KEY)
    )
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
