"""Strukturált MI-JSON válaszok biztonságos tisztítása.

Nem cseréli le a meglévő extract_json_object / motor-validátorokat —
közös szűrőréteg: ismeretlen kulcsok, titkok, túl hosszú mezők.
"""

from __future__ import annotations

from typing import Any, Mapping

# Technikai / titkos kulcsok — soha ne kerüljenek projektadatba a modellből.
FORBIDDEN_AI_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "api-key",
        "gemini_api_key",
        "secret",
        "secrets",
        "token",
        "access_token",
        "refresh_token",
        "auth",
        "authorization",
        "password",
        "cookie_secret",
        "system_prompt",
        "developer_prompt",
        "interpreter_path",
        "pythonpath",
        "environ",
        "env",
        "session_id",
        "session_uuid",
        "_call_cache",
        "_debug_log",
    }
)

DEFAULT_MAX_STRING = 8000
DEFAULT_MAX_LIST = 40
DEFAULT_MAX_DICT_KEYS = 80
DEFAULT_MAX_DEPTH = 8


def _is_forbidden_key(key: Any) -> bool:
    k = str(key or "").strip().casefold().replace("-", "_")
    if k in FORBIDDEN_AI_KEYS:
        return True
    if k.endswith("_api_key") or k.endswith("_secret") or k.endswith("_token"):
        return True
    return False


def sanitize_ai_json(
    payload: Any,
    *,
    allowed_keys: set[str] | frozenset[str] | None = None,
    max_string: int = DEFAULT_MAX_STRING,
    max_list: int = DEFAULT_MAX_LIST,
    max_dict_keys: int = DEFAULT_MAX_DICT_KEYS,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any] | None:
    """Visszaad egy tisztított dict-et, vagy None-t ha a gyökér érvénytelen."""
    if not isinstance(payload, Mapping):
        return None

    def _walk(node: Any, depth: int) -> Any:
        if depth > max_depth:
            return None
        if isinstance(node, str):
            return node if len(node) <= max_string else node[: max_string - 1] + "…"
        if isinstance(node, bool) or node is None:
            return node
        if isinstance(node, int | float):
            return node
        if isinstance(node, list):
            out_list: list[Any] = []
            for item in node[:max_list]:
                cleaned = _walk(item, depth + 1)
                if cleaned is not None:
                    out_list.append(cleaned)
            return out_list
        if isinstance(node, Mapping):
            out: dict[str, Any] = {}
            for i, (raw_key, value) in enumerate(node.items()):
                if i >= max_dict_keys:
                    break
                key = str(raw_key)
                if _is_forbidden_key(key):
                    continue
                if allowed_keys is not None and depth == 0 and key not in allowed_keys:
                    continue
                cleaned = _walk(value, depth + 1)
                if cleaned is not None:
                    out[key] = cleaned
            return out
        # Egyéb típusok (bytes, stb.) — ne kerüljenek tovább
        return None

    cleaned = _walk(payload, 0)
    return cleaned if isinstance(cleaned, dict) else None


__all__ = [
    "FORBIDDEN_AI_KEYS",
    "sanitize_ai_json",
]
