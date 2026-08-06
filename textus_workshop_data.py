"""Textus 2.0 Textusműhely — AI-tól független adatstruktúra.

Csak a `text_workshop` session/project adatot kezeli. Nem hív Geminit,
Supabase-t, és nem renderel Streamlit-widgetet. A meglévő elemzési
kulcsokhoz (exegesis, theology, stb.) nem nyúl.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, MutableMapping

TEXT_WORKSHOP_KEY = "text_workshop"

# Régi mezőnevek → új (visszafelé kompatibilis betöltés)
_LEGACY_MAIN_IDEA = "text_big_idea"
_LEGACY_MAIN_IDEA_STATUS = "text_big_idea_status"


def get_default_text_workshop() -> dict[str, Any]:
    """Üres Textusműhely-adat (új session / régi projekt hiányzó mező)."""
    return {
        "text_main_idea": "",
        "text_main_idea_status": "",
        "text_main_idea_approved_context_hash": "",
        "approved_insights": [],
        "main_idea_suggestions": None,
        "main_idea_assessment": None,
        "main_idea_last_generated_at": "",
    }


def _migrate_main_idea_field(raw: dict[str, Any], new_key: str, legacy_key: str) -> str:
    """Új mező előnyt élvez; hiányában a régi mező értékét másolja át."""
    if new_key in raw:
        return str(raw.get(new_key) or "")
    if legacy_key in raw:
        return str(raw.get(legacy_key) or "")
    return ""


def _normalize_optional_dict(raw: Any) -> dict[str, Any] | None:
    """MI-eredmény dict vagy None; hibás típus → None (régi projektek biztonsága)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    return None


def normalize_text_workshop(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `text_workshop` struktúrát ad vissza.

    Régi `text_big_idea` / `text_big_idea_status` mezőket az új
    `text_main_idea` / `text_main_idea_status` nevekre migrálja.
    Hiányzó MI-mezők alapértéket kapnak. Az új mentések csak az új
    mezőneveket tartalmazzák.
    """
    base = get_default_text_workshop()
    if not isinstance(raw, dict):
        return base

    insights_out: list[dict[str, Any]] = []
    insights_raw = raw.get("approved_insights")
    if isinstance(insights_raw, list):
        for item in insights_raw:
            if not isinstance(item, dict):
                continue
            insights_out.append(
                {
                    "id": str(item.get("id") or ""),
                    "source": str(item.get("source") or ""),
                    "category": str(item.get("category") or ""),
                    "content": str(item.get("content") or ""),
                    "approved": bool(item.get("approved", True)),
                    "created_at": str(item.get("created_at") or ""),
                }
            )

    return {
        "text_main_idea": _migrate_main_idea_field(
            raw, "text_main_idea", _LEGACY_MAIN_IDEA
        ),
        "text_main_idea_status": _migrate_main_idea_field(
            raw, "text_main_idea_status", _LEGACY_MAIN_IDEA_STATUS
        ),
        "text_main_idea_approved_context_hash": str(
            raw.get("text_main_idea_approved_context_hash") or ""
        ),
        "approved_insights": insights_out,
        "main_idea_suggestions": _normalize_optional_dict(
            raw.get("main_idea_suggestions", base["main_idea_suggestions"])
        ),
        "main_idea_assessment": _normalize_optional_dict(
            raw.get("main_idea_assessment", base["main_idea_assessment"])
        ),
        "main_idea_last_generated_at": str(
            raw.get("main_idea_last_generated_at") or ""
        ),
    }


def ensure_text_workshop_state(session_state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Biztosítja, hogy a session tartalmazzon érvényes `text_workshop` adatot."""
    normalized = normalize_text_workshop(session_state.get(TEXT_WORKSHOP_KEY))
    session_state[TEXT_WORKSHOP_KEY] = normalized
    return normalized


def add_approved_insight(
    session_state: MutableMapping[str, Any],
    source: str,
    category: str,
    content: str,
) -> dict[str, Any]:
    """Új jóváhagyott felismerés hozzáadása. Gemini / DB nélkül."""
    tw = ensure_text_workshop_state(session_state)
    insight = {
        "id": str(uuid.uuid4()),
        "source": str(source or ""),
        "category": str(category or ""),
        "content": str(content or ""),
        "approved": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    tw["approved_insights"].append(insight)
    return insight


def remove_approved_insight(
    session_state: MutableMapping[str, Any],
    insight_id: str,
) -> dict[str, Any]:
    """Felismerés eltávolítása `id` alapján."""
    tw = ensure_text_workshop_state(session_state)
    target = str(insight_id or "")
    tw["approved_insights"] = [
        item for item in tw["approved_insights"] if str(item.get("id") or "") != target
    ]
    return tw


def update_text_main_idea(
    session_state: MutableMapping[str, Any],
    content: str,
    status: str,
) -> dict[str, Any]:
    """A textus fő gondolatának tartalma / státusza (UI nélkül).

    Jóváhagyáskor (status == "approved") elmenti a
    `text_main_idea_approved_context_hash`-t is — a vázlatmotor STALE-
    ellenőrzésének alapja (ld. sermon_outline_engine.compute_current_
    passage_context_hash). Lusta import a körkörös import elkerülésére."""
    tw = ensure_text_workshop_state(session_state)
    tw["text_main_idea"] = str(content or "")
    tw["text_main_idea_status"] = str(status or "")
    if str(status or "") == "approved":
        try:
            from sermon_outline_engine import compute_current_passage_context_hash

            tw["text_main_idea_approved_context_hash"] = (
                compute_current_passage_context_hash(session_state)
            )
        except Exception:  # noqa: BLE001
            pass
    return tw


def save_main_idea_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós javaslat-eredmény mentése a text_workshop-ba."""
    tw = ensure_text_workshop_state(session_state)
    tw["main_idea_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        tw["main_idea_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return tw


def save_main_idea_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós értékelés-eredmény mentése a text_workshop-ba."""
    tw = ensure_text_workshop_state(session_state)
    tw["main_idea_assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        tw["main_idea_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return tw


__all__ = [
    "TEXT_WORKSHOP_KEY",
    "get_default_text_workshop",
    "normalize_text_workshop",
    "ensure_text_workshop_state",
    "add_approved_insight",
    "remove_approved_insight",
    "update_text_main_idea",
    "save_main_idea_suggestions",
    "save_main_idea_assessment",
]
