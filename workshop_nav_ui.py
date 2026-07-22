"""Közös műhely-navigáció (Textusműhely / Igehirdetési műhely).

Streamlit widgetek + CSS stepper / elsődleges nézetváltó.
A session kulcsok és a navigációs logika változatlan.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from html import escape
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

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


# Státuszikonok a lépéslistához (glyph-alapú, nem csak szín → hozzáférhető).
_STEP_STATE_ICON: dict[str, str] = {
    "active": ":material/radio_button_checked:",
    "done": ":material/check_circle:",
    "pending": ":material/radio_button_unchecked:",
}
_STEP_STATE_LABEL: dict[str, str] = {
    "active": "Munkában",
    "done": "Elkészült",
    "pending": "Nincs elkezdve",
}


def render_step_selector(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    key_prefix: str | None = None,
) -> str:
    """Központi lépésválasztó — egyetlen „i / N · Cím” vezérlő, lenyíló listával.

    Nincs Előző/Következő navigáció: a felhasználó szabadon választ a lépések
    közül. A lenyíló panel a triggerhez igazodik (st.popover), Escape és külső
    kattintás bezárja, billentyűzettel használható. A `key` marad a szakasz
    forrása; gombok állítják (tisztán felületi állapot).
    """
    opts = [str(o) for o in options if str(o).strip()]
    if not opts:
        return ""

    done = {str(x) for x in (completed or ()) if str(x).strip()}
    current = str(st.session_state.get(key) or "")
    if current not in opts:
        st.session_state[key] = opts[0]
        current = opts[0]

    idx = opts.index(current)
    total = len(opts)
    prefix = key_prefix or key
    done_count = sum(1 for o in opts if o in done)
    pct = int(round((done_count / total) * 100)) if total else 0

    def _state_of(opt: str) -> str:
        if opt == current:
            return "active"
        if opt in done:
            return "done"
        return "pending"

    # Idővonal-csomópontok és összekötő vonal színe lépésenként (st-key osztályok).
    node_rules: list[str] = []
    for i, opt in enumerate(opts):
        state = _state_of(opt)
        cls = f"st-key-{prefix}_step_{i}"
        if state == "done":
            icon_c, line_c = "#5a7aa8", "#5a7aa8"
        elif state == "active":
            icon_c, line_c = "#3f6699", "rgba(160, 150, 135, 0.45)"
        else:
            icon_c, line_c = "#9c9384", "rgba(160, 150, 135, 0.45)"
        node_rules.append(
            f'.{cls} button [data-testid="stIconMaterial"]{{color:{icon_c} !important;}}'
            f".{cls} button::before{{background:{line_c} !important;}}"
        )
        if i == 0:
            node_rules.append(f".{cls} button::before{{top:50% !important;}}")
        if i == total - 1:
            node_rules.append(f".{cls} button::before{{bottom:50% !important;}}")
    if total == 1:
        node_rules.append(f".st-key-{prefix}_step_0 button::before{{display:none !important;}}")

    # Horgony + a bal oldali körgyűrű haladási aránya + a lépésenkénti csomópontok.
    st.markdown(
        '<div class="tx-stepselect-anchor" aria-hidden="true"></div>'
        "<style>.element-container:has(.tx-stepselect-anchor) "
        '+ [data-testid="stLayoutWrapper"] [data-testid="stPopover"] button'
        f"{{--tx-step-pct:{pct};}}"
        + "".join(node_rules)
        + "</style>",
        unsafe_allow_html=True,
    )

    # Zárt vezérlő: bal oldalon „{szám}. {név}”, jobb oldalon a visszafogott
    # elkészültségi számláló; egyetlen chevron a jobb szélen (CSS).
    trigger_label = f"{idx + 1}. {current} :gray[{done_count} / {total} elkészült]"
    with st.popover(trigger_label, use_container_width=True, icon=":material/expand_more:"):
        st.markdown(
            (
                '<div class="tx-stepmenu-head">'
                '<div class="tx-stepmenu-title">Munkafolyamat</div>'
                f'<div class="tx-stepmenu-sub">{done_count} / {total} lépés elkészült</div>'
                '<div class="tx-wf-progress" role="presentation">'
                f'<div class="tx-wf-progress-fill" style="width:{pct}%"></div>'
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        for i, opt in enumerate(opts):
            state = _state_of(opt)
            # A szám + név balra; az állapot visszafogott, jobbra igazított
            # szövegként (a névhez NEM fűzve) — a szétválasztást CSS végzi.
            label = f"{i + 1}. {opt} :gray[{_STEP_STATE_LABEL[state]}]"
            if st.button(
                label,
                key=f"{prefix}_step_{i}",
                icon=_STEP_STATE_ICON[state],
                type="primary" if state == "active" else "secondary",
                use_container_width=True,
            ):
                if opt != current:
                    st.session_state[key] = opt
                    st.rerun()
        # Nyitáskor az aktív lépéshez görgetés (mozgáscsökkentést tisztelve).
        components.html(
            """
<script>
(function () {
  try {
    var pdoc = window.parent.document;
    var mq = window.parent.matchMedia
      && window.parent.matchMedia('(prefers-reduced-motion: reduce)');
    var reduce = !!(mq && mq.matches);
    function scrollActive() {
      var body = pdoc.querySelector('[data-testid="stPopoverBody"]');
      if (!body) return;
      var act = body.querySelector('.stButton > button[kind="primary"]');
      if (act) act.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' });
    }
    setTimeout(scrollActive, 60);
    var obs = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var added = muts[i].addedNodes || [];
        for (var j = 0; j < added.length; j++) {
          var n = added[j];
          if (n.nodeType === 1 && n.querySelector &&
              (n.matches && n.matches('[data-testid="stPopoverBody"]')
               || n.querySelector('[data-testid="stPopoverBody"]'))) {
            setTimeout(scrollActive, 50);
          }
        }
      }
    });
    obs.observe(pdoc.body, { childList: true, subtree: true });
  } catch (e) {}
})();
</script>
""",
            height=0,
        )

    return str(st.session_state.get(key) or opts[0])


def render_progress_summary(
    options: Sequence[str],
    *,
    completed: Iterable[str] | None = None,
) -> None:
    """Kompakt haladási információ + vékony progress bar a lépésválasztó alatt."""
    opts = [str(o) for o in options if str(o).strip()]
    if not opts:
        return
    done = {str(x) for x in (completed or ()) if str(x).strip()}
    total = len(opts)
    done_count = sum(1 for o in opts if o in done)
    pct = int(round((done_count / total) * 100)) if total else 0
    st.markdown(
        (
            '<div class="tx-progress-wrap">'
            '<div class="tx-progress-info">'
            f'<span>{done_count} / {total} szakaszban van megtartott anyag</span>'
            "<span>A lépések rugalmasan használhatók; nem kötelező mindet kitölteni.</span>"
            "</div>"
            '<div class="tx-wf-progress" role="presentation">'
            f'<div class="tx-wf-progress-fill" style="width:{pct}%"></div>'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_workshop_workflow_nav(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    key_prefix: str | None = None,
) -> str:
    """Közös munkafolyamat-navigáció: központi lépésválasztó + haladásösszegzés."""
    active = render_step_selector(
        options, key=key, completed=completed, key_prefix=key_prefix
    )
    render_progress_summary(options, completed=completed)
    return active


# Backward-compatible aliasok
render_section_stepper = render_workshop_stepper


# Rövid, opcionális alcímek a fő nézetekhez (prémium főmenü).
_DEFAULT_UI_MODE_SUBTITLES: dict[str, str] = {
    "quick": "Gyors elemzés és segédeszközök",
    "workshop": "A bibliai szöveg feltárása",
    "sermon_workshop": "Az igehirdetés felépítése",
}


def render_primary_view_switcher(
    options: Sequence[str] | None = None,
    *,
    labels: Mapping[str, str] | None = None,
    icons: Mapping[str, str] | None = None,
    subtitles: Mapping[str, str] | None = None,
    key: str = "ui_mode",
) -> str:
    """Háromelemű, prémium elsődleges főmenü — nagy, teljesen kattintható kártyák.

    A nézetváltási state és logika változatlan: a `key` (alapból `ui_mode`)
    értéke marad a nézet forrása. A gombok közvetlenül állítják be, mivel ez
    tisztán felületi állapot (nincs widget-tulajdonlás, nem kerül mentésbe).
    """
    opts = [str(o) for o in (options or ("quick", "workshop", "sermon_workshop"))]
    label_map = dict(_DEFAULT_UI_MODE_LABELS)
    if labels:
        label_map.update({str(k): str(v) for k, v in labels.items()})
    icon_map = dict(_DEFAULT_UI_MODE_ICONS)
    if icons:
        icon_map.update({str(k): str(v) for k, v in icons.items()})
    subtitle_map = dict(_DEFAULT_UI_MODE_SUBTITLES)
    if subtitles:
        subtitle_map.update({str(k): str(v) for k, v in subtitles.items()})

    if st.session_state.get(key) not in opts:
        st.session_state[key] = opts[0]
    current = str(st.session_state.get(key) or opts[0])

    st.markdown(
        '<div class="tx-mainnav-anchor" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(opts), gap="small")
    for col, mode in zip(cols, opts):
        is_active = mode == current
        title = label_map.get(mode, mode)
        with col:
            clicked = st.button(
                title,
                key=f"tx_mainnav_{mode}",
                icon=(icon_map.get(mode) or None),
                type="primary" if is_active else "secondary",
                use_container_width=True,
            )
        if clicked and not is_active:
            st.session_state[key] = mode
            st.rerun()

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
