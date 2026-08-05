"""Supabase kliens — URL és kulcs env változóból, projekt `secrets.toml`-ból
vagy `st.secrets`-ből, ebben a sorrendben (ugyanaz a fallback-minta, mint
az `app.py`-beli Gemini API-kulcs betöltésénél)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from supabase import Client, create_client

_SECRETS_PATH = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"


def _read_supabase_secrets_from_env() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL", "") or "").strip()
    key = (os.environ.get("SUPABASE_KEY", "") or "").strip()
    return url, key


def _read_supabase_secrets_from_project_file() -> tuple[str, str]:
    """`.streamlit/secrets.toml` az app fájl melletti projektgyökérben (TOML)."""
    if not _SECRETS_PATH.is_file():
        return "", ""
    try:
        import tomllib
    except ImportError:
        return "", ""
    try:
        with _SECRETS_PATH.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return "", ""
    supabase_cfg = data.get("supabase") or {}
    url = str(supabase_cfg.get("url") or "").strip()
    key = str(supabase_cfg.get("key") or "").strip()
    return url, key


def _read_supabase_secrets_from_streamlit() -> tuple[str, str]:
    try:
        import streamlit as st

        supabase_cfg = st.secrets.get("supabase", {})
        url = str(supabase_cfg.get("url") or "").strip()
        key = str(supabase_cfg.get("key") or "").strip()
        return url, key
    except Exception:
        return "", ""


def _load_supabase_secrets() -> tuple[str, str]:
    """URL és kulcs: env (`SUPABASE_URL`/`SUPABASE_KEY`) > projekt
    `secrets.toml` > `st.secrets["supabase"]`, ebben a sorrendben. Az első
    forrás nyer, ahol MINDKÉT érték (url és key) nem üres — a két mező
    sosem keveredhet különböző forrásokból."""
    for loader in (
        _read_supabase_secrets_from_env,
        _read_supabase_secrets_from_project_file,
        _read_supabase_secrets_from_streamlit,
    ):
        url, key = loader()
        if url and key:
            return url, key

    raise RuntimeError(
        "Nincs Supabase hitelesítő adat egyik forrásban sem: "
        "SUPABASE_URL / SUPABASE_KEY env változók, "
        "`.streamlit/secrets.toml` `[supabase]` blokk, vagy `st.secrets['supabase']`."
    )


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Visszaad egy újrafelhasználható Supabase klienst."""
    url, key = _load_supabase_secrets()
    return create_client(url, key)


if __name__ == "__main__":
    client = get_supabase_client()
    response = client.table("projects").select("*").limit(1).execute()
    rows = response.data or []
    print(f"projects tábla elérhető. Mintasorok száma: {len(rows)}")
