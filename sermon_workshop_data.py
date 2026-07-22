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
        "m9_lection_last_generated_at": _as_str(
            data.get("m9_lection_last_generated_at")
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
        else:
            sw[key] = _normalize_generic_list(data)
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
    "save_prayer_before_suggestions",
    "save_prayer_after_suggestions",
    "save_prayer_assessment",
]
