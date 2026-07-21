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
)

_SECTION_LIST_KEYS = (
    "sermon_movements",
    "selected_images",
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
            "connection_type": "",
            "connection": "",
            "gospel_indicative": "",
            "grace_before_demand": "",
            "uncertainty_note": "",
        },
        "sermon_path": {
            "type": "",
            "reason": "",
        },
        "sermon_movements": [],
        "selected_images": [],
        "applications": [],
        "closing": {
            "final_discovery": "",
            "hope": "",
            "call_or_response": "",
            "open_question": "",
        },
        "diagnostics": {
            "result": {},
            "priorities": [],
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
    }


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
    base = {"result": {}, "priorities": []}
    if not isinstance(raw, dict):
        return base
    result = raw.get("result")
    priorities = raw.get("priorities")
    return {
        "result": dict(result) if isinstance(result, dict) else {},
        "priorities": (
            [_as_str(x) for x in priorities if _as_str(x)]
            if isinstance(priorities, list)
            else []
        ),
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
        "sermon_movements": _normalize_generic_list(data.get("sermon_movements")),
        "selected_images": _normalize_generic_list(data.get("selected_images")),
        "applications": _normalize_generic_list(data.get("applications")),
        "closing": _normalize_str_dict(data.get("closing"), base["closing"]),
        "diagnostics": _normalize_diagnostics(data.get("diagnostics")),
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

    if key in _SECTION_DICT_KEYS:
        template = get_default_sermon_workshop()[key]
        if key == "diagnostics":
            sw[key] = _normalize_diagnostics(data)
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


__all__ = [
    "SERMON_WORKSHOP_KEY",
    "get_default_sermon_workshop",
    "normalize_sermon_workshop",
    "ensure_sermon_workshop_state",
    "update_sermon_workshop_section",
    "add_approved_sermon_decision",
    "remove_approved_sermon_decision",
    "deepcopy_sermon_workshop",
    "save_sermon_main_idea_suggestions",
    "save_sermon_main_idea_assessment",
    "save_human_condition_suggestion",
    "save_human_condition_assessment",
    "save_listener_tension_suggestions",
    "save_listener_tension_assessment",
]
