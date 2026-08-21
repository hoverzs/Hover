"""TEXTUS — központi Google Analytics 4 (GA4) integráció.

Célok:
- gtag a szülő dokumentumba (Streamlit iframe mellett is működik);
- send_page_view kikapcsolva a confignál — page_view csak kontrolláltan;
- Streamlit-rerun nem duplikál page_view / eseményt;
- soha ne essen szét az app GA / adblocker / hálózati hiba miatt;
- tilos PII, igehely, prédikáció, prompt, AI-válasz küldése.

Publikus API:
  init_analytics()
  track_page_view(page_name, page_path)
  track_event(event_name, parameters=None)
  track_app_navigation()  # ui_mode / panel / szakasz → page_view (+ module_open)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Mapping
from urllib.parse import quote

logger = logging.getLogger(__name__)

DEFAULT_GA_MEASUREMENT_ID = "G-WD39Q5K1MM"
SECRET_KEY = "TEXTUS_GA_MEASUREMENT_ID"

# Session kulcsok
_SS_BOOTSTRAPPED = "_textus_ga_bootstrapped"
_SS_LAST_PAGE = "_textus_ga_last_page"
_SS_LAST_MODULE = "_textus_ga_last_module"
_SS_RUN_EMITTED = "_textus_ga_run_emitted"
_SS_RUN_COUNTER = "_textus_ga_run_counter"

_ALLOWED_PARAM_KEYS = frozenset(
    {
        "module_name",
        "feature_name",
        "method",
        "status",
        "file_format",
        "error_code",
        "page_title",
        "page_location",
        "page_path",
    }
)

_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9ÁÉÍÓÖŐÚÜŰáéíóöőúüű ._/\-]{1,80}$")
_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_MEASUREMENT_ID_RE = re.compile(r"^G-[A-Z0-9]+$", re.IGNORECASE)

_UI_MODE_LABELS = {
    "workshop": "Textusműhely",
    "sermon_workshop": "Igehirdetési műhely",
    "settings": "Beállítások",
}


def _safe_call(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("analytics_swallowed err=%s", type(exc).__name__)
        return None


def get_measurement_id() -> str:
    """TEXTUS_GA_MEASUREMENT_ID env → secrets → alapértelmezés."""
    env_val = (os.environ.get(SECRET_KEY) or "").strip()
    if env_val and _MEASUREMENT_ID_RE.match(env_val):
        return env_val

    try:
        import streamlit as st

        raw = st.secrets.get(SECRET_KEY)  # type: ignore[attr-defined]
        if raw is not None:
            sid = str(raw).strip()
            if sid and _MEASUREMENT_ID_RE.match(sid):
                return sid
    except Exception:  # noqa: BLE001
        pass

    return DEFAULT_GA_MEASUREMENT_ID


def _session() -> Any | None:
    try:
        import streamlit as st

        return st.session_state
    except Exception:  # noqa: BLE001
        return None


def _slug(value: str, *, fallback: str = "page") -> str:
    text = (value or "").strip().casefold()
    if not text:
        return fallback
    repl = str.maketrans(
        {
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ö": "o",
            "ő": "o",
            "ú": "u",
            "ü": "u",
            "ű": "u",
        }
    )
    text = text.translate(repl)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:64] or fallback)


def _sanitize_param_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if abs(float(value)) > 1_000_000:
            return None
        return str(value)
    text = str(value).strip()
    if not text or len(text) > 80:
        return None
    if _EMAIL_RE.search(text):
        return None
    low = text.casefold()
    banned_bits = (
        "password",
        "token",
        "secret",
        "api_key",
        "bearer",
        "@",
    )
    if any(b in low for b in banned_bits):
        return None
    if not _SAFE_VALUE_RE.match(text):
        slug = _slug(text, fallback="")
        return slug or None
    return text


def sanitize_event_params(parameters: Mapping[str, Any] | None) -> dict[str, str]:
    """Csak engedélyezett, biztonságos kulcs/érték párok."""
    out: dict[str, str] = {}
    if not isinstance(parameters, Mapping):
        return out
    for key, raw in parameters.items():
        k = str(key or "").strip()
        if k not in _ALLOWED_PARAM_KEYS:
            continue
        cleaned = _sanitize_param_value(raw)
        if cleaned is None:
            continue
        out[k] = cleaned
    return out


def _json_for_js(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _inject_js(script_body: str, *, element_id: str) -> None:
    """Nulla magas iframe → szülő window gtag hívás."""
    try:
        import streamlit.components.v1 as components
    except Exception:  # noqa: BLE001
        return

    safe_body = script_body.replace("</", "<\\/")
    html = (
        f'<div id="{element_id}" style="display:none"></div>'
        f"<script>(function(){{try{{{safe_body}}}catch(_e){{}}}})();</script>"
    )
    _safe_call(components.html, html, height=0, width=0)


def _bootstrap_script(measurement_id: str) -> str:
    mid = json.dumps(measurement_id)
    return f"""
var w = window.parent || window;
var mid = {mid};
if (!w.__textusGa) {{
  w.__textusGa = {{ mid: mid, ready: false }};
  w.dataLayer = w.dataLayer || [];
  w.gtag = w.gtag || function(){{ w.dataLayer.push(arguments); }};
  var s = w.document.createElement('script');
  s.async = true;
  s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(mid);
  s.onload = function(){{ w.__textusGa.ready = true; }};
  (w.document.head || w.document.documentElement).appendChild(s);
  w.gtag('js', new Date());
  w.gtag('config', mid, {{
    send_page_view: false,
    anonymize_ip: true
  }});
}}
"""


def init_analytics() -> None:
    """Egyszer / session: GA szkript a szülő dokumentumba (send_page_view: false)."""
    ss = _session()
    if ss is not None and ss.get(_SS_BOOTSTRAPPED):
        return
    mid = get_measurement_id()
    if not mid:
        return
    _inject_js(_bootstrap_script(mid), element_id="textus-ga-boot")
    if ss is not None:
        ss[_SS_BOOTSTRAPPED] = True


def track_page_view(page_name: str, page_path: str) -> None:
    """Page view — csak ha a path/név változott a sessionben."""
    try:
        name = str(page_name or "page").strip()[:80] or "page"
        if _EMAIL_RE.search(name):
            name = "page"
        path = str(page_path or "").strip() or "/"
        if not path.startswith("/"):
            path = "/" + path
        path = path[:120]

        ss = _session()
        marker = f"{name}|{path}"
        if ss is not None and ss.get(_SS_LAST_PAGE) == marker:
            return
        if ss is not None:
            ss[_SS_LAST_PAGE] = marker

        init_analytics()
        mid = get_measurement_id()
        payload = {
            "page_title": name,
            "page_path": path,
            "page_location": path,
        }
        body = f"""
var w = window.parent || window;
if (typeof w.gtag === 'function') {{
  w.gtag('event', 'page_view', {_json_for_js(payload)});
  w.gtag('config', {json.dumps(mid)}, {{
    send_page_view: false,
    page_path: {json.dumps(path)},
    page_title: {json.dumps(name)}
  }});
}}
"""
        eid = "textus-ga-pv-" + quote(path, safe="")[:40]
        _inject_js(body, element_id=eid)
    except Exception as exc:  # noqa: BLE001
        logger.debug("track_page_view_failed err=%s", type(exc).__name__)


def _run_emitted_set() -> set[str]:
    """Aktuális script-run emit-halmaza (rerun = új számláló → üres halmaz)."""
    ss = _session()
    if ss is None:
        return set()
    # Streamlit minden script futáskor újra lefuttatja az app entrypontot.
    # A modulállapot megmarad, ezért a futást session számlálóval jelezzük:
    # az entrypoint init_analytics / track_app_navigation elején növeljük.
    counter = int(ss.get(_SS_RUN_COUNTER) or 0)
    bag = ss.get(_SS_RUN_EMITTED)
    if not isinstance(bag, dict) or bag.get("run") != counter:
        bag = {"run": counter, "keys": set()}
        ss[_SS_RUN_EMITTED] = bag
    keys = bag.get("keys")
    if not isinstance(keys, set):
        keys = set()
        bag["keys"] = keys
    return keys


def begin_analytics_run() -> None:
    """Hívd az app belépési pontján minden Streamlit-futás elején."""
    ss = _session()
    if ss is None:
        return
    ss[_SS_RUN_COUNTER] = int(ss.get(_SS_RUN_COUNTER) or 0) + 1
    ss[_SS_RUN_EMITTED] = {"run": ss[_SS_RUN_COUNTER], "keys": set()}


def track_event(event_name: str, parameters: dict | None = None) -> None:
    """Egyedi esemény; azonos esemény+param ugyanabban a script-runban nem ismétlődik."""
    try:
        name = str(event_name or "").strip()
        if not name or not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,39}$", name):
            return
        params = sanitize_event_params(parameters)

        guard_key = name + "|" + json.dumps(params, sort_keys=True, ensure_ascii=True)
        emitted = _run_emitted_set()
        if guard_key in emitted:
            return
        emitted.add(guard_key)

        init_analytics()
        body = f"""
var w = window.parent || window;
if (typeof w.gtag === 'function') {{
  w.gtag('event', {json.dumps(name)}, {_json_for_js(params)});
}}
"""
        eid = "textus-ga-ev-" + _slug(name) + "-" + str(abs(hash(guard_key)) % 10_000_000)
        _inject_js(body, element_id=eid)
    except Exception as exc:  # noqa: BLE001
        logger.debug("track_event_failed err=%s", type(exc).__name__)


def clear_event_guard(event_name: str | None = None) -> None:
    """Kompatibilitási no-op / run-halmaz tisztítás (ritkán kell)."""
    ss = _session()
    if ss is None:
        return
    bag = ss.get(_SS_RUN_EMITTED)
    if not isinstance(bag, dict):
        return
    keys = bag.get("keys")
    if not isinstance(keys, set):
        return
    if not event_name:
        keys.clear()
        return
    prefix = str(event_name) + "|"
    bag["keys"] = {k for k in keys if not str(k).startswith(prefix)}


def track_app_navigation() -> None:
    """Aktuális ui_mode / shell_panel / műhelyszakasz → page_view (+ module_open)."""
    try:
        import streamlit as st

        shell = str(st.session_state.get("shell_panel") or "").strip()
        mode = str(st.session_state.get("ui_mode") or "workshop").strip()
        if mode not in ("workshop", "sermon_workshop"):
            mode = "workshop"

        if shell == "settings":
            module = "settings"
            page_name = _UI_MODE_LABELS["settings"]
            page_path = "/settings"
        elif mode == "sermon_workshop":
            module = "sermon_workshop"
            section = str(st.session_state.get("sw_active_section") or "").strip()
            if section:
                page_name = f"Igehirdetési műhely · {section}"
                page_path = f"/sermon/{_slug(section)}"
            else:
                page_name = _UI_MODE_LABELS["sermon_workshop"]
                page_path = "/sermon"
        else:
            module = "workshop"
            page_name = _UI_MODE_LABELS["workshop"]
            page_path = "/workshop"

        ss = st.session_state
        prev_module = ss.get(_SS_LAST_MODULE)
        if prev_module != module:
            if prev_module is not None:
                track_event("module_open", {"module_name": module})
            ss[_SS_LAST_MODULE] = module

        track_page_view(page_name, page_path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("track_app_navigation_failed err=%s", type(exc).__name__)


def feature_name_from_label(label: Any) -> str:
    """Magyar fülcím → biztonságos feature_name."""
    text = str(label or "unknown").strip() or "unknown"
    return _slug(text, fallback="unknown")


__all__ = [
    "DEFAULT_GA_MEASUREMENT_ID",
    "SECRET_KEY",
    "begin_analytics_run",
    "clear_event_guard",
    "feature_name_from_label",
    "get_measurement_id",
    "init_analytics",
    "sanitize_event_params",
    "track_app_navigation",
    "track_event",
    "track_page_view",
]
