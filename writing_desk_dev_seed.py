"""Íróasztal helyi smoke seed — csak fejlesztés / kézi teszt.

Production viselkedést nem változtat. Akkor tölt, ha:
  TEXTUS_DEV_SEED=writing_desk  (vagy 1/true/yes/on)
és a runtime localhost.

Nincs Streamlit-gomb, nincs Supabase, nincs új dependency.
A fixture JSON a meglévő munkamenet-import formátumát követi
(`_app: Textus`), ezért Beállításokból is betölthető.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from writing_desk_data import WRITING_DESK_KEY, normalize_writing_desk

DEV_SEED_FLAG = "TEXTUS_DEV_SEED"
DEV_SEED_VALUE = "writing_desk"
APPLIED_SESSION_KEY = "_writing_desk_dev_seed_applied"
FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "tests"
    / "fixtures"
    / "writing_desk"
    / "lk_15_11_24_workspace.json"
)

_SEED_SESSION_KEYS: tuple[str, ...] = (
    "last_igehely",
    "last_alkalom",
    "last_sajat",
    "bible_translation",
    "passage_text",
    "passage_text_source",
    "passage_text_source_url",
    "passage_text_fetched_at",
    "passage_text_fetched_reference",
    "original_text",
    "history",
    "theology",
)


def writing_desk_dev_seed_requested(
    env: Mapping[str, str] | None = None,
) -> bool:
    source = env if env is not None else os.environ
    raw = str(source.get(DEV_SEED_FLAG, "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", DEV_SEED_VALUE}


def load_writing_desk_dev_workspace() -> dict[str, Any]:
    raw = FIXTURE_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("_app") not in ("Textus", "Emmaus"):
        raise ValueError("A Writing Desk dev fixture nem TEXTUS munkamenet-fájl.")
    return payload


def apply_writing_desk_dev_seed(
    session: MutableMapping[str, Any],
    *,
    force: bool = False,
) -> bool:
    """Forrásmezők + üres kivonatok. Második hívás no-op (kivonat-cache marad)."""
    if not force and session.get(APPLIED_SESSION_KEY):
        return False
    payload = load_writing_desk_dev_workspace()
    for key in _SEED_SESSION_KEYS:
        if key in payload:
            session[key] = payload[key]
    session[WRITING_DESK_KEY] = normalize_writing_desk(payload.get(WRITING_DESK_KEY))
    session[APPLIED_SESSION_KEY] = True
    return True


def maybe_apply_writing_desk_dev_seed(
    session: MutableMapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    is_local: bool | None = None,
) -> bool:
    """Env + localhost kapu. Productionben no-op."""
    if not writing_desk_dev_seed_requested(env):
        return False
    local = is_local
    if local is None:
        try:
            from auth_config import is_local_runtime

            local = bool(is_local_runtime())
        except Exception:  # noqa: BLE001
            local = False
    if not local:
        return False
    applied = apply_writing_desk_dev_seed(session)
    if applied:
        session["ui_mode"] = "writing_desk"
        session["_bible_text_ui_resync"] = True
    return applied


__all__ = [
    "APPLIED_SESSION_KEY",
    "DEV_SEED_FLAG",
    "DEV_SEED_VALUE",
    "FIXTURE_PATH",
    "apply_writing_desk_dev_seed",
    "load_writing_desk_dev_workspace",
    "maybe_apply_writing_desk_dev_seed",
    "writing_desk_dev_seed_requested",
]
