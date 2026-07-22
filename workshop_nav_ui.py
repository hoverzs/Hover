"""Közös műhely-szakasz navigáció (Textusműhely / Igehirdetési műhely).

Streamlit radio + CSS stepper stílus. Ugyanazok a session kulcsok
maradnak, a funkcionalitás változatlan.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

import streamlit as st


def render_section_stepper(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    label: str = "Szakaszok",
) -> str:
    """Vizuális lépésnavigáció — aktív / kész / várakozó állapotokkal."""
    opts = [str(o) for o in options if str(o).strip()]
    if not opts:
        return ""

    done = {str(x) for x in (completed or ()) if str(x).strip()}
    current = str(st.session_state.get(key) or "")
    if current not in opts:
        st.session_state[key] = opts[0]
        current = opts[0]

    def _format(opt: str) -> str:
        if opt in done and opt != current:
            return f"✓  {opt}"
        return opt

    st.markdown(
        '<div class="ws-stepper-anchor" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    st.radio(
        label,
        options=opts,
        key=key,
        format_func=_format,
        label_visibility="collapsed",
    )
    return str(st.session_state.get(key) or opts[0])


def textus_completed_sections(state: Any) -> set[str]:
    """Textusműhely: tartalom alapján késznek jelölt szakaszok."""
    get = state.get if hasattr(state, "get") else (lambda *_: None)
    done: set[str] = set()
    if str(get("last_igehely") or get("igehely_input") or "").strip() or str(
        get("passage_text") or ""
    ).strip():
        done.add("Igehely, alkalom és szövegkörnyezet")
    if str(get("original_text") or "").strip():
        done.add("Eredeti szöveg és kulcsszavak")
    if str(get("exegesis") or "").strip():
        done.add("Exegézis, műfaj és szerkezet")
    if str(get("history") or "").strip():
        done.add("Kortörténeti háttér")
    if str(get("theology") or "").strip():
        done.add("Teológiai hangsúlyok")
    tw = get("text_workshop") if isinstance(get("text_workshop"), dict) else {}
    if not isinstance(tw, dict):
        tw = {}
    if str(tw.get("text_main_idea") or "").strip() or str(
        tw.get("text_main_idea_status") or ""
    ).strip() in ("draft", "approved"):
        done.add("A textus fő gondolata")
    insights = tw.get("approved_insights")
    if isinstance(insights, list) and any(
        isinstance(x, dict) and str(x.get("content") or "").strip() for x in insights
    ):
        done.add("Mit viszünk tovább?")
    return done


def sermon_completed_sections(
    state: Any,
    *,
    status_of: Callable[[str], str] | None = None,
) -> set[str]:
    """Igehirdetési műhely: jóváhagyott / érdemi tartalmú szakaszok."""
    get = state.get if hasattr(state, "get") else (lambda *_: None)
    sw = get("sermon_workshop") if isinstance(get("sermon_workshop"), dict) else {}
    if not isinstance(sw, dict):
        sw = {}

    def _status(key: str) -> str:
        if status_of is not None:
            return str(status_of(key) or "").strip()
        return str(sw.get(key) or "").strip()

    def _has_text(*keys: str) -> bool:
        for k in keys:
            val = sw.get(k)
            if isinstance(val, str) and val.strip():
                return True
            if isinstance(val, dict) and any(
                str(v).strip() for v in val.values() if not isinstance(v, (list, dict))
            ):
                return True
            if isinstance(val, list) and val:
                return True
        return False

    done: set[str] = set()
    if _status("sermon_main_idea_status") == "approved" or _has_text(
        "sermon_main_idea"
    ):
        done.add("Az igehirdetés fő gondolata")
    if _status("human_condition_status") == "approved" or _has_text("human_condition"):
        done.add("Emberi helyzet és kegyelmi válasz")
    if _status("listener_tension_status") == "approved" or _has_text(
        "listener_tension"
    ):
        done.add("Hallgatói kérdés és feszültség")
    if _status("christ_centered_arc_status") == "approved" or _has_text(
        "christ_centered_arc"
    ):
        done.add("Krisztus-központú és evangéliumi ív")
    if _status("sermon_path_status") == "approved" or _has_text(
        "sermon_path", "sermon_movements"
    ):
        done.add("Az igehirdetés útja és mozgásai")
    if _status("enrichment_status") == "approved" or _has_text(
        "selected_images", "illustrations", "applications"
    ):
        done.add("Képek, illusztrációk és alkalmazás")
    if _status("closing_status") == "approved" or _has_text("closing"):
        done.add("Lezárás és megérkezés")
    if _status("lection_status") == "approved" or (
        isinstance(sw.get("lection"), dict)
        and str(sw["lection"].get("reference") or "").strip()
    ):
        done.add("Lekciójavaslat")
    if _status("prayer_status") == "approved" or _has_text("prayer_preparation"):
        done.add("Imádsági előkészítés")
    if _status("sermon_outline_status") == "approved" or _has_text("sermon_outline"):
        done.add("Igehirdetési vázlat")
    diag = sw.get("diagnostics") if isinstance(sw.get("diagnostics"), dict) else {}
    result = diag.get("result") if isinstance(diag.get("result"), dict) else {}
    outline_diag = sw.get("sermon_outline_diagnostics")
    if (isinstance(result, dict) and result) or (
        isinstance(outline_diag, dict) and outline_diag
    ):
        done.add("Homiletikai diagnosztika")
    return done


__all__ = [
    "render_section_stepper",
    "textus_completed_sections",
    "sermon_completed_sections",
]
