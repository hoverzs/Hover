"""Közös műhely-navigáció (Textusműhely / Igehirdetési műhely).

Streamlit widgetek + CSS stepper / elsődleges nézetváltó.
A session kulcsok és a navigációs logika változatlan.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from html import escape
from typing import Any

import streamlit as st

_DEFAULT_UI_MODE_LABELS: dict[str, str] = {
    "quick": "Gyorseszközök",
    "workshop": "Textusműhely",
    "sermon_workshop": "Igehirdetési műhely",
}

# Optional Material icons (Streamlit markdown) — clean, not emoji.
_DEFAULT_UI_MODE_ICONS: dict[str, str] = {
    "quick": ":material/bolt:",
    "workshop": ":material/menu_book:",
    "sermon_workshop": ":material/auto_stories:",
}


def completed_step_indices(
    options: Sequence[str],
    completed: Iterable[str] | None,
) -> list[int]:
    """0-based indices of completed (not necessarily active) steps."""
    done = {str(x) for x in (completed or ()) if str(x).strip()}
    return [i for i, opt in enumerate(options) if opt in done]


def _render_stepper(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None,
    label: str,
    anchor_base: str,
) -> str:
    """Közös lépésnavigáció-mag — a megjelenést az anchor osztály vezérli.

    A címben nincs ✓; a kész állapotot CSS jelöli (ws-done-N osztályok).
    A session kulcs és a navigációs logika minden variánsnál azonos.
    """
    opts = [str(o) for o in options if str(o).strip()]
    if not opts:
        return ""

    done = {str(x) for x in (completed or ()) if str(x).strip()}
    current = str(st.session_state.get(key) or "")
    if current not in opts:
        st.session_state[key] = opts[0]
        current = opts[0]

    done_classes = " ".join(f"ws-done-{i}" for i in completed_step_indices(opts, done))
    anchor_cls = f"{anchor_base} {done_classes}".strip()
    st.markdown(
        f'<div class="{anchor_cls}" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    # format_func: plain labels only (no checkmark in text)
    st.radio(
        label,
        options=opts,
        key=key,
        format_func=lambda opt: str(opt),
        label_visibility="collapsed",
    )
    return str(st.session_state.get(key) or opts[0])


def render_workshop_stepper(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    label: str = "Szakaszok",
) -> str:
    """Függőleges lépésnavigáció (visszafelé kompatibilis változat)."""
    return _render_stepper(
        options,
        key=key,
        completed=completed,
        label=label,
        anchor_base="ws-stepper-anchor",
    )


def render_workshop_step_grid(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    label: str = "Munkafolyamat",
) -> str:
    """Felső, több sorba törhető lépésrács — aktív / kész / várakozó.

    Ugyanaz a widget és session kulcs, mint a függőleges stepperé; csak a
    megjelenés más (grid). Mindkét műhely ezt használja.
    """
    return _render_stepper(
        options,
        key=key,
        completed=completed,
        label=label,
        anchor_base="ws-step-grid-anchor",
    )


# Backward-compatible aliasok
render_section_stepper = render_workshop_stepper


def render_primary_view_switcher(
    options: Sequence[str] | None = None,
    *,
    labels: Mapping[str, str] | None = None,
    icons: Mapping[str, str] | None = None,
    key: str = "ui_mode",
) -> str:
    """Háromelemű elsődleges nézetváltó (segmented control)."""
    opts = [str(o) for o in (options or ("quick", "workshop", "sermon_workshop"))]
    label_map = dict(_DEFAULT_UI_MODE_LABELS)
    if labels:
        label_map.update({str(k): str(v) for k, v in labels.items()})
    icon_map = dict(_DEFAULT_UI_MODE_ICONS)
    if icons:
        icon_map.update({str(k): str(v) for k, v in icons.items()})

    if st.session_state.get(key) not in opts:
        st.session_state[key] = opts[0]

    def _format(mode: str) -> str:
        text = label_map.get(mode, mode)
        icon = (icon_map.get(mode) or "").strip()
        return f"{icon} {text}".strip() if icon else text

    st.markdown(
        '<div class="ws-primary-nav-anchor" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )

    if hasattr(st, "segmented_control"):
        st.segmented_control(
            "Nézet",
            options=opts,
            format_func=_format,
            key=key,
            required=True,
            label_visibility="collapsed",
            width="stretch",
        )
    else:
        st.radio(
            "Nézet",
            options=opts,
            format_func=_format,
            horizontal=True,
            key=key,
            label_visibility="collapsed",
        )

    return str(st.session_state.get(key) or opts[0])


def render_project_toolbar_anchor() -> None:
    """CSS horog a projektgombok tömör eszköztárához."""
    st.markdown(
        '<div class="ws-project-toolbar-anchor" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )


# Alias — a gombok és mentési logika az app projekt-sávjában marad.
render_project_toolbar = render_project_toolbar_anchor


def render_info_panel(title: str, body: str = "") -> None:
    """Cím + törzs hierarchia info-panelekhez (sentence case)."""
    t = escape((title or "").strip())
    b = escape((body or "").strip())
    if not t and not b:
        return
    title_html = f'<div class="ws-info-title">{t}</div>' if t else ""
    body_html = f'<div class="ws-info-body">{b}</div>' if b else ""
    st.markdown(
        f'<div class="ws-info-panel">{title_html}{body_html}</div>',
        unsafe_allow_html=True,
    )


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
        "selected_images",
        "illustrations",
        "applications",
        "retained_illustration_cards",
        "actualization_connections",
    ):
        done.add("Illusztrációk és aktualizálás")
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
    "completed_step_indices",
    "render_workshop_stepper",
    "render_section_stepper",
    "render_primary_view_switcher",
    "render_project_toolbar_anchor",
    "render_project_toolbar",
    "render_info_panel",
    "textus_completed_sections",
    "sermon_completed_sections",
]
