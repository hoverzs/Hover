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

_INSIGHT_KEYS = ("id", "source", "category", "content", "approved", "created_at")


def get_default_text_workshop() -> dict[str, Any]:
    """Üres Textusműhely-adat (új session / régi projekt hiányzó mező)."""
    return {
        "text_big_idea": "",
        "text_big_idea_status": "",
        "approved_insights": [],
    }


def normalize_text_workshop(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `text_workshop` struktúrát ad vissza."""
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
        "text_big_idea": str(raw.get("text_big_idea") or ""),
        "text_big_idea_status": str(raw.get("text_big_idea_status") or ""),
        "approved_insights": insights_out,
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


def update_text_big_idea(
    session_state: MutableMapping[str, Any],
    content: str,
    status: str,
) -> dict[str, Any]:
    """A textus nagy gondolatának tartalma / státusza (UI nélkül)."""
    tw = ensure_text_workshop_state(session_state)
    tw["text_big_idea"] = str(content or "")
    tw["text_big_idea_status"] = str(status or "")
    return tw


__all__ = [
    "TEXT_WORKSHOP_KEY",
    "get_default_text_workshop",
    "normalize_text_workshop",
    "ensure_text_workshop_state",
    "add_approved_insight",
    "remove_approved_insight",
    "update_text_big_idea",
]
