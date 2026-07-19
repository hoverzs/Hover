"""Supabase kliens — URL és kulcs a `.streamlit/secrets.toml` `[supabase]` blokkjából."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from supabase import Client, create_client


def _load_supabase_secrets() -> tuple[str, str]:
    """Beolvassa a `[supabase].url` és `[supabase].key` értékeket a secrets.toml-ból."""
    secrets_path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not secrets_path.is_file():
        raise FileNotFoundError(f"Hiányzik a secrets fájl: {secrets_path}")

    try:
        import tomllib
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("A tomllib modul szükséges a secrets.toml olvasásához.") from exc

    with secrets_path.open("rb") as f:
        data = tomllib.load(f)

    supabase_cfg = data.get("supabase") or {}
    url = str(supabase_cfg.get("url") or "").strip()
    key = str(supabase_cfg.get("key") or "").strip()

    if not url or not key:
        raise ValueError(
            "A `.streamlit/secrets.toml` `[supabase]` blokkjában meg kell adni "
            "az `url` és `key` mezőket."
        )
    return url, key


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
