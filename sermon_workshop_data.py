"""Textus 2.0 Igehirdetési műhely — AI-tól független adatstruktúra.

Csak a `sermon_workshop` session/project adatot kezeli. Nem hív Geminit,
Supabase-t, és nem renderel Streamlit-widgetet. A `text_workshop` és a
meglévő elemzési kulcsokhoz nem nyúl.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any, MutableMapping

SERMON_WORKSHOP_KEY = "sermon_workshop"

_SECTION_DICT_KEYS = (
    "human_condition",
    "listener_tension",
    "christ_centered_arc",
    "sermon_path",
    "closing",
    "diagnostics",
    "lection",
    "prayer_preparation",
)

_SECTION_LIST_KEYS = (
    "sermon_movements",
    "selected_images",
    "illustrations",
    "applications",
    "approved_sermon_decisions",
    "illustration_suggestions",
    "actualization_suggestions",
    "retained_illustration_cards",
    "actualization_connections",
)

_SECTION_STR_KEYS = (
    "illustration_user_direction",
    "actualization_user_direction",
    "illustration_suggest_note",
    "actualization_suggest_note",
)


def get_default_sermon_workshop() -> dict[str, Any]:
    """Üres Igehirdetési műhely-adat (új session / régi projekt hiányzó mező)."""
    return {
        "sermon_main_idea": "",
        "sermon_main_idea_status": "draft",
        "human_condition": {
            "condition": "",
            "false_response": "",
            "human_need": "",
            "divine_action": "",
            "grace_response": "",
        },
        "listener_tension": {
            "listener_question": "",
            "listener_resistance": "",
            "sermon_tension": "",
            "promised_resolution": "",
        },
        "christ_centered_arc": {
            "divine_gracious_action": "",
            "christ_connection": "",
            "christ_connection_type": "",
            "grace_enabled_response": "",
        },
        "sermon_path": {
            "type": "",
            "reason": "",
            "starting_point": "",
            "destination": "",
        },
        "sermon_movements": [],
        "selected_images": [],
        "illustrations": [],
        "applications": [],
        "enrichment_status": "draft",
        "illustration_user_direction": "",
        "actualization_user_direction": "",
        "illustration_suggestions": [],
        "actualization_suggestions": [],
        "retained_illustration_cards": [],
        "actualization_connections": [],
        "illustration_suggest_note": "",
        "actualization_suggest_note": "",
        "closing": {
            "type": "",
            "final_discovery": "",
            "hope": "",
            "call_or_response": "",
            "image_or_line": "",
            "open_question": "",
            "tone": "",
        },
        "closing_status": "draft",
        "diagnostics": {
            "result": {},
            "priorities": [],
        },
        "self_review_strengths": "",
        "self_review_uncertainties": "",
        "self_review_priority": "",
        "self_review_focus": "",
        "m8_last_generated_at": "",
        "lection": {
            "reference": "",
            "connection_type": "",
            "function": "",
            "rationale": "",
            "text": "",
            "notes": "",
            "testament_preference": "any",
            "length_preference": "standard",
            "user_focus": "",
            "text_source": "",
            "text_source_url": "",
            "text_fetched_at": "",
            "text_fetched_reference": "",
        },
        "lection_status": "draft",
        "lection_suggestions": None,
        "lection_assessment": None,
        "lection_connection_analysis": None,
        "m9_lection_last_generated_at": "",
        "prayer_preparation": {
            "tone_preference": "mixed",
            "general_focus": "",
            "rewrite_mode": "integrate_into_arc",
            "before": {
                "own_thoughts": "",
                "purpose": "",
                "movement_notes": "",
                "selected_opening": "",
                "selected_lines": [],
                "closing_direction": "",
                "status": "draft",
            },
            "after": {
                "own_thoughts": "",
                "purpose": "",
                "movement_notes": "",
                "selected_opening": "",
                "selected_lines": [],
                "closing_direction": "",
                "status": "draft",
            },
            "before_suggestions": None,
            "after_suggestions": None,
            "assessment": None,
            "status": "draft",
            "last_generated_at": "",
        },
        "approved_sermon_decisions": [],
        "sermon_main_idea_suggestions": None,
        "sermon_main_idea_assessment": None,
        "human_condition_suggestion": None,
        "human_condition_assessment": None,
        "m4_last_generated_at": "",
        "listener_tension_suggestions": None,
        "listener_tension_assessment": None,
        "m5_last_generated_at": "",
        "gospel_arc_suggestions": None,
        "gospel_arc_assessment": None,
        "m5_gospel_arc_last_generated_at": "",
        "sermon_path_suggestions": None,
        "sermon_path_assessment": None,
        "m6_last_generated_at": "",
        "sermon_enrichment_suggestions": None,
        "sermon_enrichment_assessment": None,
        "m7_last_generated_at": "",
        "closing_suggestions": None,
        "closing_assessment": None,
        "m7_closing_last_generated_at": "",
        "sermon_outline": empty_sermon_outline(),
        "sermon_outline_status": "draft",
        "sermon_outline_generated_at": "",
        "sermon_outline_updated_at": "",
        "sermon_outline_diagnostics": {},
        "sermon_outline_diagnostics_generated_at": "",
        # idle | running | ready | error — normalize megőrzi (ne vesszen el rerun-kor)
        "sermon_outline_diagnostics_status": "idle",
        "sermon_outline_diagnostics_error": "",
    }


_MOVEMENT_FIELD_KEYS = (
    "id",
    "title",
    "role",
    "core_content",
    "textual_basis",
    "listener_discovery",
    "transition_to_next",
)


def empty_sermon_movement(*, role: str = "") -> dict[str, str]:
    """Üres prédikációs mozgás (új elem / biztonságos alapérték)."""
    return {
        "id": str(uuid.uuid4()),
        "title": "",
        "role": _as_str(role),
        "core_content": "",
        "textual_basis": "",
        "listener_discovery": "",
        "transition_to_next": "",
    }


def empty_outline_movement() -> dict[str, Any]:
    return {
        "id": "",
        "title": "",
        "role": "",
        "role_label": "",
        "textual_basis": "",
        "textual_anchor": "",
        "core_content": "",
        "exegetical_core": "",
        "theological_claim": "",
        "listener_discovery": "",
        "grace_application": "",
        "transition": "",
        # Kibontott prédikációs bulletök (homiletikai vázlat főnézet).
        "development": [],
        "images": [],
        "illustrations": [],
        "applications": [],
    }


def empty_sermon_outline() -> dict[str, Any]:
    """Üres igehirdetési vázlat — régi projektek biztonságos alapértéke."""
    return {
        "status": "draft",
        "generated_at": "",
        "updated_at": "",
        "project_title": "",
        "passage_reference": "",
        "bible_translation": "",
        "lection_reference": "",
        "lection_translation": "",
        "sermon_title": "",
        "title_suggestions": [],
        "main_idea": "",
        "main_idea_summary": "",
        "homiletical_aim": "",
        "human_situation": "",
        "listener_question": "",
        "central_tension": "",
        "listener_resistance": "",
        "divine_gracious_action": "",
        "christ_connection": "",
        "christ_connection_type_label": "",
        "gospel_resolution": "",
        "grace_enabled_response": "",
        "opening_direction": "",
        # Munkavázlat bevezetés / megérkezés (főnézet).
        "introduction": {
            "development": "",
            "transition": "",
        },
        "conclusion": {
            "development": "",
            "final_sentence": "",
        },
        # Nem blokkoló textushatár-megjegyzés (pl. gondolati ív a következő versben).
        "text_boundary_note": "",
        "suggested_text_boundary": "",
        # Kanonikus, olvasható vázlatszöveg — előnézet / szerkesztés / diagnosztika.
        "content": "",
        "movements": [],
        "extra_enrichment": {
            "images": [],
            "illustrations": [],
            "applications": [],
        },
        "closing": {
            "final_insight": "",
            "gospel_assurance": "",
            "invitation": "",
            "image_or_line": "",
            "open_question": "",
            "tone": "",
            "tone_label": "",
        },
        "lection": {
            "reference": "",
            "function": "",
            "rationale": "",
        },
        "prayer_before": {
            "movements": [],
            "own_thoughts": "",
            "selected_opening": "",
            "selected_lines": [],
            "closing_direction": "",
        },
        "prayer_after": {
            "movements": [],
            "own_thoughts": "",
            "selected_opening": "",
            "selected_lines": [],
            "closing_direction": "",
        },
        "manual_notes": "",
        "editorial_tips": [],
        "manually_edited": False,
        # Hibás (approved + üres) állapot javítása után UI-üzenethez.
        "needs_rebuild": False,
        # Meta — fejlesztői / diagnosztikai; a fő UI nem listázza nyersen
        "source_sections": [],
        "provisional_sections": [],
        "source_fingerprint": "",
        "source_completeness": "",
        "actualization_connections": [],
    }


def _normalize_str_list(raw: Any, *, max_items: int = 20) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = _as_str(item)
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def _normalize_outline_prayer(raw: Any) -> dict[str, Any]:
    template = empty_sermon_outline()["prayer_before"]
    if not isinstance(raw, dict):
        return dict(template)
    return {
        "movements": _normalize_str_list(raw.get("movements")),
        "own_thoughts": _as_str(raw.get("own_thoughts")),
        "selected_opening": _as_str(raw.get("selected_opening")),
        "selected_lines": _normalize_str_list(raw.get("selected_lines")),
        "closing_direction": _as_str(raw.get("closing_direction")),
    }


def _normalize_outline_movement(raw: Any) -> dict[str, Any]:
    base = empty_outline_movement()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "id",
        "title",
        "role",
        "role_label",
        "textual_basis",
        "textual_anchor",
        "core_content",
        "exegetical_core",
        "theological_claim",
        "listener_discovery",
        "grace_application",
        "transition",
    ):
        if key in raw:
            out[key] = _as_str(raw.get(key))
    # Címek ne tartalmazzanak saját számozást (a render adja: „1. …”)
    if out["title"]:
        import re

        out["title"] = re.sub(r"^\s*\d+[.)]\s*", "", out["title"]).strip()
    if not out["textual_anchor"] and out["textual_basis"]:
        out["textual_anchor"] = out["textual_basis"]
    out["development"] = _normalize_str_list(raw.get("development"), max_items=8)
    for list_key in ("images", "illustrations", "applications"):
        out[list_key] = _normalize_str_list(raw.get(list_key))
    return out


def normalize_sermon_outline(raw: Any) -> dict[str, Any]:
    """Vázlat normalizálása; hiányzó mezők biztonságos alapértékkel."""
    base = empty_sermon_outline()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "generated_at",
        "updated_at",
        "project_title",
        "passage_reference",
        "bible_translation",
        "lection_reference",
        "lection_translation",
        "sermon_title",
        "main_idea",
        "main_idea_summary",
        "homiletical_aim",
        "human_situation",
        "listener_question",
        "central_tension",
        "listener_resistance",
        "divine_gracious_action",
        "christ_connection",
        "christ_connection_type_label",
        "gospel_resolution",
        "grace_enabled_response",
        "opening_direction",
        "content",
        "manual_notes",
        "text_boundary_note",
        "suggested_text_boundary",
    ):
        if key in raw:
            out[key] = _as_str(raw.get(key))
    # Új munkavázlat aliasok
    if not out["main_idea"] and raw.get("focus_sentence"):
        out["main_idea"] = _as_str(raw.get("focus_sentence"))
    if not out["sermon_title"] and raw.get("title"):
        out["sermon_title"] = _as_str(raw.get("title"))
    if not out["passage_reference"] and raw.get("text_reference"):
        out["passage_reference"] = _as_str(raw.get("text_reference"))
    out["title_suggestions"] = _normalize_str_list(
        raw.get("title_suggestions"), max_items=5
    )
    out["editorial_tips"] = _normalize_str_list(
        raw.get("editorial_tips"), max_items=2
    )
    # Új séma alias: refinement_suggestions → editorial_tips
    if not out["editorial_tips"]:
        out["editorial_tips"] = _normalize_str_list(
            raw.get("refinement_suggestions"), max_items=2
        )
    status = _as_str(raw.get("status")) or "draft"
    if status not in ("draft", "approved", "empty", ""):
        status = "draft"
    out["status"] = status or "draft"
    out["manually_edited"] = bool(raw.get("manually_edited"))
    out["needs_rebuild"] = bool(raw.get("needs_rebuild"))
    movements_raw = raw.get("movements")
    movements: list[dict[str, Any]] = []
    if isinstance(movements_raw, list):
        for item in movements_raw[:8]:
            if isinstance(item, dict):
                movements.append(_normalize_outline_movement(item))
    out["movements"] = movements
    intro_raw = (
        raw.get("introduction") if isinstance(raw.get("introduction"), dict) else {}
    )
    introduction = dict(base["introduction"])
    for key in introduction:
        if key in intro_raw:
            introduction[key] = _as_str(intro_raw.get(key))
    # Legacy: opening_direction → introduction.development
    if not introduction["development"] and out.get("opening_direction"):
        introduction["development"] = _as_str(out.get("opening_direction"))
    out["introduction"] = introduction
    if introduction["development"] and not out.get("opening_direction"):
        out["opening_direction"] = introduction["development"]
    conc_raw = raw.get("conclusion") if isinstance(raw.get("conclusion"), dict) else {}
    conclusion = dict(base["conclusion"])
    for key in conclusion:
        if key in conc_raw:
            conclusion[key] = _as_str(conc_raw.get(key))
    out["conclusion"] = conclusion
    closing_raw = raw.get("closing") if isinstance(raw.get("closing"), dict) else {}
    closing = dict(base["closing"])
    for key in closing:
        if key in closing_raw:
            closing[key] = _as_str(closing_raw.get(key))
    # Sync conclusion ↔ closing
    if not conclusion["development"] and closing.get("final_insight"):
        conclusion["development"] = _as_str(closing.get("final_insight"))
    if not conclusion["final_sentence"] and closing.get("image_or_line"):
        conclusion["final_sentence"] = _as_str(closing.get("image_or_line"))
    if conclusion["development"] and not closing.get("final_insight"):
        closing["final_insight"] = conclusion["development"]
    if conclusion["final_sentence"] and not closing.get("image_or_line"):
        closing["image_or_line"] = conclusion["final_sentence"]
    out["conclusion"] = conclusion
    out["closing"] = closing
    lection_raw = raw.get("lection") if isinstance(raw.get("lection"), dict) else {}
    lection = dict(base["lection"])
    for key in lection:
        if key in lection_raw:
            lection[key] = _as_str(lection_raw.get(key))
    out["lection"] = lection
    extra_raw = (
        raw.get("extra_enrichment")
        if isinstance(raw.get("extra_enrichment"), dict)
        else {}
    )
    out["extra_enrichment"] = {
        "images": _normalize_str_list(extra_raw.get("images")),
        "illustrations": _normalize_str_list(extra_raw.get("illustrations")),
        "applications": _normalize_str_list(extra_raw.get("applications")),
    }
    out["prayer_before"] = _normalize_outline_prayer(raw.get("prayer_before"))
    out["prayer_after"] = _normalize_outline_prayer(raw.get("prayer_after"))
    out["source_sections"] = _normalize_str_list(
        raw.get("source_sections"), max_items=40
    )
    out["provisional_sections"] = _normalize_str_list(
        raw.get("provisional_sections"), max_items=20
    )
    out["source_fingerprint"] = _as_str(raw.get("source_fingerprint"))
    completeness = _as_str(raw.get("source_completeness"))
    if completeness not in ("full", "partial", "minimal", ""):
        completeness = "partial" if out["source_sections"] else ""
    out["source_completeness"] = completeness
    out["actualization_connections"] = _normalize_simple_card_list(
        raw.get("actualization_connections"), max_items=8
    )
    return out


def _normalize_diag_status(raw: Any) -> str:
    status = _as_str(raw).casefold() or "idle"
    if status not in ("idle", "running", "ready", "error"):
        return "idle"
    return status


def _diagnostics_has_result(payload: Any) -> bool:
    """Van-e megjeleníthető diagnosztikai eredmény (üres skeleton nem számít)."""
    if not isinstance(payload, dict) or not payload:
        return False
    if _as_str(payload.get("overview")):
        return True
    if _normalize_str_list(payload.get("strengths"), max_items=3):
        return True
    if isinstance(payload.get("refinements"), list) and any(
        isinstance(x, dict) and _as_str(x.get("title")) for x in payload["refinements"]
    ):
        return True
    if isinstance(payload.get("diagnostic_areas"), list) and any(
        isinstance(x, dict) and _as_str(x.get("key")) for x in payload["diagnostic_areas"]
    ):
        return True
    return False


def normalize_sermon_outline_diagnostics(raw: Any) -> dict[str, Any]:
    """Egyszerűsített vázlatdiagnosztika — max 3 erősség / finomítás."""
    if not isinstance(raw, dict):
        return {}
    strengths = _normalize_str_list(raw.get("strengths"), max_items=3)
    refinements: list[dict[str, Any]] = []
    for item in raw.get("refinements") or []:
        if not isinstance(item, dict):
            continue
        title = _as_str(item.get("title"))
        if not title:
            continue
        refinements.append(
            {
                "title": title,
                "explanation": _as_str(
                    item.get("explanation")
                    or item.get("why_it_matters")
                    or item.get("problem")
                ),
                "suggested_action": _as_str(
                    item.get("suggested_action") or item.get("recommended_action")
                ),
                "affected_outline_parts": _normalize_str_list(
                    item.get("affected_outline_parts")
                    or item.get("affected_sections")
                ),
            }
        )
        if len(refinements) >= 3:
            break
    return {
        "overview": _as_str(raw.get("overview") or raw.get("overall_summary")),
        "strengths": strengths,
        "refinements": refinements,
        "ready_to_use": bool(
            raw.get("ready_to_use")
            if "ready_to_use" in raw
            else raw.get("ready_for_next_stage")
        ),
        "next_step": _as_str(raw.get("next_step") or raw.get("readiness_note")),
        "detailed_notes": _normalize_str_list(raw.get("detailed_notes"), max_items=30),
        "warnings": _normalize_str_list(raw.get("warnings"), max_items=20),
        "diagnostic_areas": _normalize_outline_diag_areas(raw.get("diagnostic_areas")),
        "mode": _as_str(raw.get("mode")) or "ai",
        "ok": bool(raw.get("ok", True)),
        "error_message": _as_str(raw.get("error_message")),
        "missing_outline": bool(raw.get("missing_outline")),
        "outline_updated_at_at_diagnosis": _as_str(
            raw.get("outline_updated_at_at_diagnosis")
        ),
    }


def _normalize_outline_diag_areas(raw: Any) -> list[dict[str, Any]]:
    """Vázlatdiagnosztika 8 tengelye — hiányzó score soha ne legyen 0."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = _as_str(item.get("key"))
        if not key:
            continue
        status = _as_str(item.get("status")) or "not_enough_information"
        score_raw = item.get("score")
        score: int | None
        if status == "not_enough_information" or score_raw in (None, "", 0, "0"):
            score = None
        else:
            try:
                score = int(score_raw)
            except (TypeError, ValueError):
                score = None
            if score is not None and score <= 0:
                score = None
            elif score is not None:
                score = max(1, min(4, score))
        out.append(
            {
                "key": key,
                "label": _as_str(item.get("label")) or key,
                "status": status,
                "score": score,
                "summary": _as_str(item.get("summary")),
                "suggested_action": _as_str(item.get("suggested_action")),
            }
        )
    return out


def normalize_sermon_movement(raw: Any) -> dict[str, str]:
    """Egy mozgás normalizálása; hiányzó mezők üres stringgel."""
    base = empty_sermon_movement()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in _MOVEMENT_FIELD_KEYS:
        if key in raw:
            out[key] = _as_str(raw.get(key))
    if not out["id"]:
        out["id"] = str(uuid.uuid4())
    return out


def normalize_sermon_movements(raw: Any, *, max_items: int = 5) -> list[dict[str, str]]:
    """Mozgáslista normalizálása; max 5 elem, érvénytelen elemek kihagyva."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_sermon_movement(item))
        if len(out) >= max_items:
            break
    return out


_TEXTUAL_IMAGE_FIELDS = (
    "id",
    "image",
    "textual_basis",
    "homiletical_function",
    "placement",
    "movement_id",
    "development_notes",
    "source_ref",
)

_ILLUSTRATION_FIELDS = (
    "id",
    "idea",
    "source",
    "function",
    "placement",
    "movement_id",
    "connection_to_text",
    "risk_or_limit",
    "source_ref",
)

_APPLICATION_FIELDS = (
    "id",
    "application",
    "scope",
    "gospel_basis",
    "concreteness",
    "placement",
    "movement_id",
    "pastoral_caution",
    "source_ref",
)


def empty_textual_image() -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "image": "",
        "textual_basis": "",
        "homiletical_function": "",
        "placement": "general",
        "movement_id": "",
        "development_notes": "",
        "source_ref": "",
    }


def empty_illustration() -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "idea": "",
        "source": "needs_verification",
        "function": "",
        "placement": "general",
        "movement_id": "",
        "connection_to_text": "",
        "risk_or_limit": "",
        "source_ref": "",
    }


def empty_application() -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "application": "",
        "scope": "personal",
        "gospel_basis": "",
        "concreteness": "",
        "placement": "general",
        "movement_id": "",
        "pastoral_caution": "",
        "source_ref": "",
    }


def _normalize_enrichment_item(
    raw: Any,
    *,
    fields: tuple[str, ...],
    empty_fn,
) -> dict[str, str]:
    base = empty_fn()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in fields:
        if key in raw:
            out[key] = _as_str(raw.get(key))
    if not out["id"]:
        out["id"] = str(uuid.uuid4())
    return out


def normalize_textual_image(raw: Any) -> dict[str, str]:
    return _normalize_enrichment_item(
        raw, fields=_TEXTUAL_IMAGE_FIELDS, empty_fn=empty_textual_image
    )


def normalize_illustration(raw: Any) -> dict[str, str]:
    return _normalize_enrichment_item(
        raw, fields=_ILLUSTRATION_FIELDS, empty_fn=empty_illustration
    )


def normalize_application(raw: Any) -> dict[str, str]:
    return _normalize_enrichment_item(
        raw, fields=_APPLICATION_FIELDS, empty_fn=empty_application
    )


def normalize_textual_images(raw: Any, *, max_items: int = 3) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_textual_image(item))
        if len(out) >= max_items:
            break
    return out


def _normalize_simple_card_list(raw: Any, *, max_items: int = 12) -> list[dict[str, Any]]:
    """UI-kártyák laza normalizálása — régi projektek biztonsága."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cleaned: dict[str, Any] = {}
        for key, val in item.items():
            if isinstance(val, bool):
                cleaned[str(key)] = val
            elif isinstance(val, (int, float)):
                cleaned[str(key)] = val
            else:
                cleaned[str(key)] = _as_str(val)
        if not cleaned.get("id"):
            cleaned["id"] = str(uuid.uuid4())
        out.append(cleaned)
        if len(out) >= max_items:
            break
    return out


def normalize_illustrations(raw: Any, *, max_items: int = 3) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_illustration(item))
        if len(out) >= max_items:
            break
    return out


def normalize_applications(raw: Any, *, max_items: int = 4) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_application(item))
        if len(out) >= max_items:
            break
    return out


def _as_str(value: Any) -> str:
    return str(value or "")


def _normalize_str_dict(raw: Any, template: dict[str, str]) -> dict[str, str]:
    out = dict(template)
    if not isinstance(raw, dict):
        return out
    for key in template:
        if key in raw:
            out[key] = _as_str(raw.get(key))
    return out


def _normalize_diagnostics(raw: Any) -> dict[str, Any]:
    """M8 diagnosztika: result = teljes MI-eredmény; priorities = max 3 elem."""
    base: dict[str, Any] = {"result": {}, "priorities": []}
    if not isinstance(raw, dict):
        return base
    result = raw.get("result")
    priorities_raw = raw.get("priorities")
    priorities: list[Any] = []
    if isinstance(priorities_raw, list):
        for item in priorities_raw:
            if isinstance(item, dict):
                priorities.append(
                    {
                        "priority": item.get("priority", len(priorities) + 1),
                        "title": _as_str(item.get("title")),
                        "problem": _as_str(item.get("problem")),
                        "why_it_matters": _as_str(item.get("why_it_matters")),
                        "recommended_action": _as_str(item.get("recommended_action")),
                        "affected_sections": (
                            [_as_str(x) for x in item.get("affected_sections", []) if _as_str(x)]
                            if isinstance(item.get("affected_sections"), list)
                            else []
                        ),
                    }
                )
            elif _as_str(item):
                # Régi string prioritások visszafelé kompatibilisen
                priorities.append(
                    {
                        "priority": len(priorities) + 1,
                        "title": _as_str(item),
                        "problem": "",
                        "why_it_matters": "",
                        "recommended_action": "",
                        "affected_sections": [],
                    }
                )
            if len(priorities) >= 3:
                break
    return {
        "result": dict(result) if isinstance(result, dict) else {},
        "priorities": priorities,
    }


_LECTION_TESTAMENT_PREFS = frozenset(
    {"any", "old_testament", "psalm", "gospel", "new_testament"}
)
_LECTION_LENGTH_PREFS = frozenset({"short", "standard", "extended"})
_LECTION_CONNECTION_TYPES = frozenset(
    {
        "thematic",
        "canonical",
        "redemptive_historical",
        "preparatory",
        "contrast",
        "gospel_complement",
        "liturgical_echo",
    }
)


def normalize_lection_testament_preference(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _LECTION_TESTAMENT_PREFS else "any"


def normalize_lection_length_preference(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _LECTION_LENGTH_PREFS else "standard"


def normalize_lection_connection_type(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _LECTION_CONNECTION_TYPES else ""


def _normalize_lection(raw: Any) -> dict[str, str]:
    """M9 lekcióblokk — biztonságos alapértékek régi projektekhez."""
    template = get_default_sermon_workshop()["lection"]
    out = _normalize_str_dict(raw, template)
    out["testament_preference"] = normalize_lection_testament_preference(
        out.get("testament_preference")
    )
    out["length_preference"] = normalize_lection_length_preference(
        out.get("length_preference")
    )
    conn = normalize_lection_connection_type(out.get("connection_type"))
    out["connection_type"] = conn
    return out


_PRAYER_TONE_PREFS = frozenset(
    {
        "quiet_meditative",
        "honest_confessional",
        "hopeful",
        "assuring",
        "intercessory",
        "communal",
        "festive",
        "simple_direct",
        "biblical_imagery",
        "mixed",
    }
)
_PRAYER_REWRITE_MODES = frozenset(
    {"light_polish", "integrate_into_arc", "free_rephrase"}
)
_PRAYER_SIDE_STATUS = frozenset({"draft", "approved", ""})


def normalize_prayer_tone_preference(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _PRAYER_TONE_PREFS else "mixed"


def normalize_prayer_rewrite_mode(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _PRAYER_REWRITE_MODES else "integrate_into_arc"


def _normalize_prayer_lines(raw: Any, *, max_items: int = 24) -> list[str]:
    if isinstance(raw, list):
        out = [_as_str(x).strip() for x in raw if _as_str(x).strip()]
        return out[:max_items]
    text = _as_str(raw).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return lines[:max_items]


def empty_prayer_side() -> dict[str, Any]:
    return {
        "own_thoughts": "",
        "purpose": "",
        "movement_notes": "",
        "selected_opening": "",
        "selected_lines": [],
        "closing_direction": "",
        "status": "draft",
    }


def _normalize_prayer_side(raw: Any) -> dict[str, Any]:
    base = empty_prayer_side()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "own_thoughts",
        "purpose",
        "movement_notes",
        "selected_opening",
        "closing_direction",
    ):
        if key in raw:
            out[key] = _as_str(raw.get(key))
    if "selected_lines" in raw:
        out["selected_lines"] = _normalize_prayer_lines(raw.get("selected_lines"))
    status = _as_str(raw.get("status")) or "draft"
    if status not in _PRAYER_SIDE_STATUS:
        status = "draft"
    out["status"] = status or "draft"
    return out


def _normalize_prayer_preparation(raw: Any) -> dict[str, Any]:
    """M9 imádsági előkészítés — biztonságos alapértékek régi projektekhez."""
    base = get_default_sermon_workshop()["prayer_preparation"]
    if not isinstance(raw, dict):
        return copy.deepcopy(base)
    status = _as_str(raw.get("status")) or "draft"
    if status not in ("draft", "approved", ""):
        status = "draft"
    return {
        "tone_preference": normalize_prayer_tone_preference(
            raw.get("tone_preference", base["tone_preference"])
        ),
        "general_focus": _as_str(raw.get("general_focus")),
        "rewrite_mode": normalize_prayer_rewrite_mode(
            raw.get("rewrite_mode", base["rewrite_mode"])
        ),
        "before": _normalize_prayer_side(raw.get("before")),
        "after": _normalize_prayer_side(raw.get("after")),
        "before_suggestions": _normalize_optional_dict(
            raw.get("before_suggestions", base["before_suggestions"])
        ),
        "after_suggestions": _normalize_optional_dict(
            raw.get("after_suggestions", base["after_suggestions"])
        ),
        "assessment": _normalize_optional_dict(
            raw.get("assessment", base["assessment"])
        ),
        "status": status or "draft",
        "last_generated_at": _as_str(raw.get("last_generated_at")),
    }


def _normalize_decisions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "id": _as_str(item.get("id")),
                "source_section": _as_str(item.get("source_section")),
                "category": _as_str(item.get("category")),
                "content": _as_str(item.get("content")),
                "approved": bool(item.get("approved", True)),
                "created_at": _as_str(item.get("created_at")),
            }
        )
    return out


def _normalize_generic_list(raw: Any) -> list[Any]:
    if not isinstance(raw, list):
        return []
    return list(raw)


def _normalize_optional_dict(raw: Any) -> dict[str, Any] | None:
    """MI-eredmény dict vagy None; hibás típus → None (régi projektek biztonsága)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    return None


def normalize_sermon_workshop(data: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `sermon_workshop` struktúrát ad vissza."""
    base = get_default_sermon_workshop()
    if not isinstance(data, dict):
        return base

    status = _as_str(data.get("sermon_main_idea_status")) or "draft"
    if status not in ("draft", "approved", ""):
        status = "draft"

    enrichment_status = _as_str(data.get("enrichment_status")) or "draft"
    if enrichment_status not in ("draft", "approved", ""):
        enrichment_status = "draft"

    closing_status = _as_str(data.get("closing_status")) or "draft"
    if closing_status not in ("draft", "approved", ""):
        closing_status = "draft"

    lection_status = _as_str(data.get("lection_status")) or "draft"
    if lection_status not in ("draft", "approved", ""):
        lection_status = "draft"

    outline_status = _as_str(data.get("sermon_outline_status")) or "draft"
    if outline_status not in ("draft", "approved", "empty", ""):
        outline_status = "draft"

    return {
        "sermon_main_idea": _as_str(data.get("sermon_main_idea")),
        "sermon_main_idea_status": status or "draft",
        "human_condition": _normalize_str_dict(
            data.get("human_condition"), base["human_condition"]
        ),
        "listener_tension": _normalize_str_dict(
            data.get("listener_tension"), base["listener_tension"]
        ),
        "christ_centered_arc": _normalize_str_dict(
            data.get("christ_centered_arc"), base["christ_centered_arc"]
        ),
        "sermon_path": _normalize_str_dict(
            data.get("sermon_path"), base["sermon_path"]
        ),
        "sermon_movements": normalize_sermon_movements(data.get("sermon_movements")),
        "selected_images": normalize_textual_images(data.get("selected_images")),
        "illustrations": normalize_illustrations(data.get("illustrations")),
        "applications": normalize_applications(data.get("applications")),
        "enrichment_status": enrichment_status or "draft",
        "illustration_user_direction": _as_str(
            data.get("illustration_user_direction")
        ),
        "actualization_user_direction": _as_str(
            data.get("actualization_user_direction")
        ),
        "illustration_suggestions": _normalize_simple_card_list(
            data.get("illustration_suggestions")
        ),
        "actualization_suggestions": _normalize_simple_card_list(
            data.get("actualization_suggestions")
        ),
        "retained_illustration_cards": _normalize_simple_card_list(
            data.get("retained_illustration_cards")
        ),
        "actualization_connections": _normalize_simple_card_list(
            data.get("actualization_connections")
        ),
        "illustration_suggest_note": _as_str(data.get("illustration_suggest_note")),
        "actualization_suggest_note": _as_str(data.get("actualization_suggest_note")),
        "closing": _normalize_str_dict(data.get("closing"), base["closing"]),
        "closing_status": closing_status or "draft",
        "diagnostics": _normalize_diagnostics(data.get("diagnostics")),
        "lection": _normalize_lection(data.get("lection")),
        "lection_status": lection_status or "draft",
        "prayer_preparation": _normalize_prayer_preparation(
            data.get("prayer_preparation")
        ),
        "approved_sermon_decisions": _normalize_decisions(
            data.get("approved_sermon_decisions")
        ),
        "sermon_main_idea_suggestions": _normalize_optional_dict(
            data.get(
                "sermon_main_idea_suggestions",
                base["sermon_main_idea_suggestions"],
            )
        ),
        "sermon_main_idea_assessment": _normalize_optional_dict(
            data.get(
                "sermon_main_idea_assessment",
                base["sermon_main_idea_assessment"],
            )
        ),
        "human_condition_suggestion": _normalize_optional_dict(
            data.get(
                "human_condition_suggestion",
                base["human_condition_suggestion"],
            )
        ),
        "human_condition_assessment": _normalize_optional_dict(
            data.get(
                "human_condition_assessment",
                base["human_condition_assessment"],
            )
        ),
        "m4_last_generated_at": _as_str(data.get("m4_last_generated_at")),
        "listener_tension_suggestions": _normalize_optional_dict(
            data.get(
                "listener_tension_suggestions",
                base["listener_tension_suggestions"],
            )
        ),
        "listener_tension_assessment": _normalize_optional_dict(
            data.get(
                "listener_tension_assessment",
                base["listener_tension_assessment"],
            )
        ),
        "m5_last_generated_at": _as_str(data.get("m5_last_generated_at")),
        "gospel_arc_suggestions": _normalize_optional_dict(
            data.get(
                "gospel_arc_suggestions",
                base["gospel_arc_suggestions"],
            )
        ),
        "gospel_arc_assessment": _normalize_optional_dict(
            data.get(
                "gospel_arc_assessment",
                base["gospel_arc_assessment"],
            )
        ),
        "m5_gospel_arc_last_generated_at": _as_str(
            data.get("m5_gospel_arc_last_generated_at")
        ),
        "sermon_path_suggestions": _normalize_optional_dict(
            data.get(
                "sermon_path_suggestions",
                base["sermon_path_suggestions"],
            )
        ),
        "sermon_path_assessment": _normalize_optional_dict(
            data.get(
                "sermon_path_assessment",
                base["sermon_path_assessment"],
            )
        ),
        "m6_last_generated_at": _as_str(data.get("m6_last_generated_at")),
        "sermon_enrichment_suggestions": _normalize_optional_dict(
            data.get(
                "sermon_enrichment_suggestions",
                base["sermon_enrichment_suggestions"],
            )
        ),
        "sermon_enrichment_assessment": _normalize_optional_dict(
            data.get(
                "sermon_enrichment_assessment",
                base["sermon_enrichment_assessment"],
            )
        ),
        "m7_last_generated_at": _as_str(data.get("m7_last_generated_at")),
        "closing_suggestions": _normalize_optional_dict(
            data.get("closing_suggestions", base["closing_suggestions"])
        ),
        "closing_assessment": _normalize_optional_dict(
            data.get("closing_assessment", base["closing_assessment"])
        ),
        "m7_closing_last_generated_at": _as_str(
            data.get("m7_closing_last_generated_at")
        ),
        "self_review_strengths": _as_str(data.get("self_review_strengths")),
        "self_review_uncertainties": _as_str(data.get("self_review_uncertainties")),
        "self_review_priority": _as_str(data.get("self_review_priority")),
        "self_review_focus": _as_str(data.get("self_review_focus")),
        "m8_last_generated_at": _as_str(data.get("m8_last_generated_at")),
        "lection_suggestions": _normalize_optional_dict(
            data.get("lection_suggestions", base["lection_suggestions"])
        ),
        "lection_assessment": _normalize_optional_dict(
            data.get("lection_assessment", base["lection_assessment"])
        ),
        "lection_connection_analysis": _normalize_lection_connection_analysis_field(
            data.get(
                "lection_connection_analysis",
                base.get("lection_connection_analysis"),
            )
        ),
        "m9_lection_last_generated_at": _as_str(
            data.get("m9_lection_last_generated_at")
        ),
        "sermon_outline": normalize_sermon_outline(data.get("sermon_outline")),
        "sermon_outline_status": outline_status or "draft",
        "sermon_outline_generated_at": _as_str(
            data.get("sermon_outline_generated_at")
        ),
        "sermon_outline_updated_at": _as_str(data.get("sermon_outline_updated_at")),
        "sermon_outline_diagnostics": normalize_sermon_outline_diagnostics(
            data.get("sermon_outline_diagnostics")
        ),
        "sermon_outline_diagnostics_generated_at": _as_str(
            data.get("sermon_outline_diagnostics_generated_at")
        ),
        "sermon_outline_diagnostics_status": _normalize_diag_status(
            data.get(
                "sermon_outline_diagnostics_status",
                base.get("sermon_outline_diagnostics_status"),
            )
        ),
        "sermon_outline_diagnostics_error": _as_str(
            data.get(
                "sermon_outline_diagnostics_error",
                base.get("sermon_outline_diagnostics_error"),
            )
        ),
    }


def ensure_sermon_workshop_state(
    session_state: MutableMapping[str, Any],
) -> dict[str, Any]:
    """Biztosítja, hogy a session tartalmazzon érvényes `sermon_workshop` adatot."""
    normalized = normalize_sermon_workshop(session_state.get(SERMON_WORKSHOP_KEY))
    session_state[SERMON_WORKSHOP_KEY] = normalized
    return normalized


def update_sermon_workshop_section(
    session_state: MutableMapping[str, Any],
    section: str,
    data: Any,
) -> dict[str, Any]:
    """Egy szakasz / mezőcsoport frissítése a `sermon_workshop`-ban.

    `section` lehet pl. `human_condition`, `sermon_path`, `sermon_main_idea`,
    `sermon_movements`, stb. A `sermon_main_idea` esetén a `data` lehet string
    vagy dict (`sermon_main_idea` / `sermon_main_idea_status` kulcsokkal).
    """
    sw = ensure_sermon_workshop_state(session_state)
    key = str(section or "").strip()

    if key in ("sermon_main_idea", "main_idea"):
        if isinstance(data, dict):
            if "sermon_main_idea" in data:
                sw["sermon_main_idea"] = _as_str(data.get("sermon_main_idea"))
            if "sermon_main_idea_status" in data:
                status = _as_str(data.get("sermon_main_idea_status")) or "draft"
                if status not in ("draft", "approved", ""):
                    status = "draft"
                sw["sermon_main_idea_status"] = status or "draft"
        else:
            sw["sermon_main_idea"] = _as_str(data)
        return sw

    if key == "sermon_main_idea_status":
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", ""):
            status = "draft"
        sw["sermon_main_idea_status"] = status or "draft"
        return sw

    if key == "enrichment_status":
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", ""):
            status = "draft"
        sw["enrichment_status"] = status or "draft"
        return sw

    if key == "closing_status":
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", ""):
            status = "draft"
        sw["closing_status"] = status or "draft"
        return sw

    if key == "lection_status":
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", ""):
            status = "draft"
        sw["lection_status"] = status or "draft"
        return sw

    if key == "sermon_outline_status":
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", "empty", ""):
            status = "draft"
        sw["sermon_outline_status"] = status or "draft"
        outline = normalize_sermon_outline(sw.get("sermon_outline"))
        outline["status"] = sw["sermon_outline_status"]
        sw["sermon_outline"] = outline
        return sw

    if key in ("sermon_outline", "outline"):
        outline = normalize_sermon_outline(data)
        sw["sermon_outline"] = outline
        status = _as_str(outline.get("status")) or "draft"
        if status not in ("draft", "approved", "empty", ""):
            status = "draft"
        sw["sermon_outline_status"] = status or "draft"
        if outline.get("generated_at"):
            sw["sermon_outline_generated_at"] = _as_str(outline.get("generated_at"))
        if outline.get("updated_at"):
            sw["sermon_outline_updated_at"] = _as_str(outline.get("updated_at"))
        return sw

    if key == "sermon_outline_diagnostics":
        sw["sermon_outline_diagnostics"] = normalize_sermon_outline_diagnostics(data)
        return sw

    if key in (
        "self_review_strengths",
        "self_review_uncertainties",
        "self_review_priority",
        "self_review_focus",
    ):
        sw[key] = _as_str(data)
        return sw

    if key in _SECTION_DICT_KEYS:
        template = get_default_sermon_workshop()[key]
        if key == "diagnostics":
            sw[key] = _normalize_diagnostics(data)
        elif key == "lection":
            current = sw.get(key) if isinstance(sw.get(key), dict) else {}
            merged = dict(template)
            if isinstance(current, dict):
                merged.update({k: _as_str(current.get(k)) for k in template})
            if isinstance(data, dict):
                for field_key in template:
                    if field_key in data:
                        merged[field_key] = _as_str(data.get(field_key))
            sw[key] = _normalize_lection(merged)
        elif key == "prayer_preparation":
            current = sw.get(key) if isinstance(sw.get(key), dict) else {}
            merged = copy.deepcopy(template)
            if isinstance(current, dict):
                merged = _normalize_prayer_preparation({**merged, **current})
            if isinstance(data, dict):
                # Mély merge: top-level + before/after részleges frissítés
                for top_key, top_val in data.items():
                    if top_key in ("before", "after") and isinstance(top_val, dict):
                        side = dict(merged.get(top_key) or {})
                        side.update(top_val)
                        merged[top_key] = side
                    elif top_key in merged or top_key in (
                        "before_suggestions",
                        "after_suggestions",
                        "assessment",
                        "tone_preference",
                        "general_focus",
                        "rewrite_mode",
                        "status",
                        "last_generated_at",
                    ):
                        merged[top_key] = top_val
            sw[key] = _normalize_prayer_preparation(merged)
        else:
            # Merge: meglévő + új mezők
            current = sw.get(key) if isinstance(sw.get(key), dict) else {}
            merged = dict(template)
            if isinstance(current, dict):
                merged.update({k: _as_str(current.get(k)) for k in template})
            if isinstance(data, dict):
                for field_key in template:
                    if field_key in data:
                        merged[field_key] = _as_str(data.get(field_key))
            sw[key] = merged
        return sw

    if key in _SECTION_LIST_KEYS:
        if key == "approved_sermon_decisions":
            sw[key] = _normalize_decisions(data)
        elif key == "sermon_movements":
            sw[key] = normalize_sermon_movements(data)
        elif key == "selected_images":
            sw[key] = normalize_textual_images(data)
        elif key == "illustrations":
            sw[key] = normalize_illustrations(data)
        elif key == "applications":
            sw[key] = normalize_applications(data)
        elif key in (
            "illustration_suggestions",
            "actualization_suggestions",
            "retained_illustration_cards",
            "actualization_connections",
        ):
            sw[key] = _normalize_simple_card_list(data)
        else:
            sw[key] = _normalize_generic_list(data)
        return sw

    if key in _SECTION_STR_KEYS:
        sw[key] = _as_str(data)
        return sw

    # Ismeretlen szakasz: ne dobjon hibát; hagyja érintetlenül
    return sw


def add_approved_sermon_decision(
    session_state: MutableMapping[str, Any],
    source_section: str,
    category: str,
    content: str,
) -> dict[str, Any]:
    """Új jóváhagyott homiletikai döntés. Gemini / DB nélkül."""
    sw = ensure_sermon_workshop_state(session_state)
    decision = {
        "id": str(uuid.uuid4()),
        "source_section": _as_str(source_section),
        "category": _as_str(category),
        "content": _as_str(content),
        "approved": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    sw["approved_sermon_decisions"].append(decision)
    return decision


def remove_approved_sermon_decision(
    session_state: MutableMapping[str, Any],
    decision_id: str,
) -> dict[str, Any]:
    """Homiletikai döntés eltávolítása `id` alapján."""
    sw = ensure_sermon_workshop_state(session_state)
    target = _as_str(decision_id)
    sw["approved_sermon_decisions"] = [
        item
        for item in sw["approved_sermon_decisions"]
        if _as_str(item.get("id")) != target
    ]
    return sw


def deepcopy_sermon_workshop(data: Any) -> dict[str, Any]:
    """Normalizált másolat (tesztekhez / biztonságos átadáshoz)."""
    return copy.deepcopy(normalize_sermon_workshop(data))


def save_sermon_main_idea_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M4 főgondolat-javaslat mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_main_idea_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_main_idea_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M4 főgondolat-értékelés mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_main_idea_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_human_condition_suggestion(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós emberi helyzet javaslat mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["human_condition_suggestion"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_human_condition_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós emberi helyzet értékelés mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["human_condition_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_listener_tension_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 hallgatói feszültség-javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["listener_tension_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m5_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_listener_tension_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 hallgatói feszültség-értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["listener_tension_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m5_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_gospel_arc_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 evangéliumi ív javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["gospel_arc_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m5_gospel_arc_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_gospel_arc_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 evangéliumi ív értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["gospel_arc_assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m5_gospel_arc_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_sermon_path_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M6 igehirdetési út javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_path_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m6_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_path_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M6 igehirdetési út értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_path_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m6_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_enrichment_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 kép/illusztráció/alkalmazás javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_enrichment_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m7_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_enrichment_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 kép/illusztráció/alkalmazás értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_enrichment_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m7_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_closing_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 lezárási javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["closing_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m7_closing_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_closing_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 lezárási értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["closing_assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m7_closing_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_homiletical_diagnostics(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M8 diagnosztika mentése a meglévő `diagnostics` kulcsba.

    Nem módosítja az M4–M7 tartalmakat és a kézi önellenőrző mezőket.
    """
    sw = ensure_sermon_workshop_state(session_state)
    result = dict(payload) if isinstance(payload, dict) else {}
    priorities_raw = result.get("revision_priorities")
    priorities: list[Any] = []
    if isinstance(priorities_raw, list):
        for item in priorities_raw[:3]:
            if isinstance(item, dict):
                priorities.append(item)
            elif _as_str(item):
                priorities.append({"title": _as_str(item), "priority": len(priorities) + 1})
    sw["diagnostics"] = _normalize_diagnostics(
        {"result": result, "priorities": priorities}
    )
    if stamp_generated_at:
        sw["m8_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def _normalize_lection_connection_analysis_field(raw: Any) -> dict[str, Any] | None:
    """Lekció–textus kapcsolati elemzés tartós mezője."""
    try:
        from sermon_workshop_lection_link_ai import (
            normalize_lection_connection_analysis,
        )
    except Exception:  # pragma: no cover
        return _normalize_optional_dict(raw) if isinstance(raw, dict) else None
    return normalize_lection_connection_analysis(raw)


def save_lection_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 lekciójavaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["lection_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m9_lection_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_lection_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 lekcióértékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["lection_assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m9_lection_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_lection_connection_analysis(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any] | None,
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós lekció–textus kapcsolati elemzés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = _normalize_lection_connection_analysis_field(payload)
    sw["lection_connection_analysis"] = normalized
    if stamp_generated_at and isinstance(normalized, dict) and normalized.get("ok"):
        if not _as_str(normalized.get("generated_at")):
            normalized["generated_at"] = datetime.now().isoformat(timespec="seconds")
            sw["lection_connection_analysis"] = normalized
        sw["m9_lection_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_prayer_before_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 előtti imaív javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    prep = _normalize_prayer_preparation(sw.get("prayer_preparation"))
    prep["before_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        prep["last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    sw["prayer_preparation"] = prep
    return sw


def save_prayer_after_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 utáni imaív javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    prep = _normalize_prayer_preparation(sw.get("prayer_preparation"))
    prep["after_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        prep["last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    sw["prayer_preparation"] = prep
    return sw


def save_prayer_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 imádsági terv értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    prep = _normalize_prayer_preparation(sw.get("prayer_preparation"))
    prep["assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        prep["last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    sw["prayer_preparation"] = prep
    return sw


def save_sermon_outline(
    session_state: MutableMapping[str, Any],
    outline: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
    mark_manual_edit: bool = False,
) -> dict[str, Any]:
    """Igehirdetési vázlat tartós mentése. Nem módosítja az M4–M9 forrásmezőket."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = normalize_sermon_outline(outline)
    now = datetime.now().isoformat(timespec="seconds")
    if stamp_generated_at and not _as_str(normalized.get("generated_at")):
        normalized["generated_at"] = now
    normalized["updated_at"] = now
    if mark_manual_edit:
        normalized["manually_edited"] = True
    status = _as_str(normalized.get("status")) or "draft"
    if status not in ("draft", "approved", "empty", ""):
        status = "draft"
    # Üres tartalom soha ne maradjon approved.
    try:
        from sermon_workshop_outline_ai import outline_has_content, sync_outline_content

        # Content: csak ha üres, töltsük a struktúrából — kézi content ne vesszen el.
        if not _as_str(normalized.get("content")):
            normalized = sync_outline_content(normalized, force=True)
        if not outline_has_content(normalized):
            if status == "approved":
                status = "draft"
                normalized["needs_rebuild"] = True
        else:
            normalized["needs_rebuild"] = False
    except Exception:  # pragma: no cover
        pass
    normalized["status"] = status or "draft"
    sw["sermon_outline"] = normalized
    sw["sermon_outline_status"] = normalized["status"]
    sw["sermon_outline_generated_at"] = _as_str(normalized.get("generated_at"))
    sw["sermon_outline_updated_at"] = now
    return sw


def save_sermon_outline_diagnostics(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Vázlatdiagnosztika mentése — nem módosítja a vázlatot / műhelymezőket."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = normalize_sermon_outline_diagnostics(payload)
    # Üres payload soha ne törölje a korábbi érvényes diagnózist.
    if not _diagnostics_has_result(normalized) and _diagnostics_has_result(
        sw.get("sermon_outline_diagnostics")
    ):
        return sw
    sw["sermon_outline_diagnostics"] = normalized
    if stamp_generated_at:
        sw["sermon_outline_diagnostics_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    sw["sermon_outline_diagnostics_status"] = "ready"
    sw["sermon_outline_diagnostics_error"] = ""
    return sw


def set_sermon_outline_diagnostics_status(
    session_state: MutableMapping[str, Any],
    status: str,
    *,
    error_message: str = "",
) -> dict[str, Any]:
    """Diagnosztika futási / hibastátusz — a meglévő eredményt nem törli."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = _normalize_diag_status(status)
    sw["sermon_outline_diagnostics_status"] = normalized
    if normalized == "error":
        sw["sermon_outline_diagnostics_error"] = _as_str(error_message)
    elif normalized in ("idle", "running", "ready"):
        sw["sermon_outline_diagnostics_error"] = ""
    return sw


__all__ = [
    "SERMON_WORKSHOP_KEY",
    "get_default_sermon_workshop",
    "normalize_sermon_workshop",
    "ensure_sermon_workshop_state",
    "update_sermon_workshop_section",
    "add_approved_sermon_decision",
    "remove_approved_sermon_decision",
    "deepcopy_sermon_workshop",
    "empty_sermon_movement",
    "normalize_sermon_movement",
    "normalize_sermon_movements",
    "empty_outline_movement",
    "empty_sermon_outline",
    "normalize_sermon_outline",
    "normalize_sermon_outline_diagnostics",
    "empty_textual_image",
    "empty_illustration",
    "empty_application",
    "normalize_textual_image",
    "normalize_illustration",
    "normalize_application",
    "normalize_textual_images",
    "normalize_illustrations",
    "normalize_applications",
    "normalize_lection_testament_preference",
    "normalize_lection_length_preference",
    "normalize_lection_connection_type",
    "normalize_prayer_tone_preference",
    "normalize_prayer_rewrite_mode",
    "empty_prayer_side",
    "save_sermon_main_idea_suggestions",
    "save_sermon_main_idea_assessment",
    "save_human_condition_suggestion",
    "save_human_condition_assessment",
    "save_listener_tension_suggestions",
    "save_listener_tension_assessment",
    "save_gospel_arc_suggestions",
    "save_gospel_arc_assessment",
    "save_sermon_path_suggestions",
    "save_sermon_path_assessment",
    "save_sermon_enrichment_suggestions",
    "save_sermon_enrichment_assessment",
    "save_closing_suggestions",
    "save_closing_assessment",
    "save_homiletical_diagnostics",
    "save_lection_suggestions",
    "save_lection_assessment",
    "save_lection_connection_analysis",
    "save_prayer_before_suggestions",
    "save_prayer_after_suggestions",
    "save_prayer_assessment",
    "save_sermon_outline",
    "save_sermon_outline_diagnostics",
    "set_sermon_outline_diagnostics_status",
    "_diagnostics_has_result",
]
