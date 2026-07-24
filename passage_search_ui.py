"""Igehely keresése — Streamlit UI (Textusműhely igehely panel).

Önálló UI-réteg: az AI-logika a `passage_search_ai` modulban van.
Nem módosítja a felső navigációt, toolbart vagy globális CSS-t.
"""

from __future__ import annotations

from typing import Any, Callable, MutableMapping, cast

import streamlit as st

from bible_text_ui import _apply_ruf_fetch_success
from occasion_context import (
    ensure_occasion_context_state,
    field_defs_for_occasion,
    is_ceremonial_occasion,
    merge_context_for_passage_search,
    update_occasion_context_fields,
    widget_key_for_field,
)
from passage_search_ai import (
    merge_exclude_list,
    normalize_passage_reference,
    normalize_passage_search_state,
    suggest_passages_for_occasion,
)
from passage_search_config import OCCASION_OPTIONS
from passage_search_history import (
    UsedPassageHistory,
    empty_used_passage_history,
    find_previous_usage,
    get_cached_used_passage_history,
)
from ruf_bible_service import fetch_ruf_passage
from ui_components import render_info_panel

SESSION_KEY = "passage_search"
PENDING_APPLY_KEY = "_pending_passage_search_apply"
PENDING_CONFIRM_KEY = "_passage_search_overwrite_pending"
STALE_FLAG_KEY = "passage_content_stale"
STALE_FROM_REF_KEY = "passage_stale_from_reference"
FLASH_SELECT_KEY = "_passage_search_select_flash"
EXPANDER_OPEN_KEY = "_passage_search_expander_open"
WIDGET_OCCASION = "passage_search_occasion"
WIDGET_CONTEXT = "passage_search_context"
WIDGET_EXCLUDE_USED = "passage_search_exclude_used"

GenerateFn = Callable[..., str]
FetchProjectsFn = Callable[[str], list[dict[str, Any]]]

_CONFIRM_MSG = (
    "Az igehely módosítása a korábbi elemzéseket elavulttá teszi. "
    "Szeretnéd folytatni?"
)
_API_FAIL_MSG = (
    "Most nem sikerült igehelyeket keresni. "
    "A megadott adatok megmaradtak, próbáld újra."
)
_HISTORY_FETCH_FAIL_MSG = (
    "A korábban használt textusokat most nem sikerült ellenőrizni. "
    "Az ajánlás enélkül folytatódik."
)


def ensure_passage_search_state(
    session_state: MutableMapping[str, Any] | None = None,
) -> dict[str, Any]:
    ss = session_state if session_state is not None else st.session_state
    raw = ss.get(SESSION_KEY)
    normalized = normalize_passage_search_state(raw)
    ss[SESSION_KEY] = normalized
    return normalized


def _save_state(state: dict[str, Any]) -> None:
    st.session_state[SESSION_KEY] = normalize_passage_search_state(state)


def workshop_material_present(
    session_state: MutableMapping[str, Any] | None = None,
) -> bool:
    """Van-e igehelyhez kötött műhelyanyag (nem csak üres mező)."""
    ss = session_state if session_state is not None else st.session_state
    for key in (
        "overview",
        "exegesis",
        "history",
        "theology",
        "illustrations",
        "actualization",
        "outline",
        "outline_draft",
        "original_text",
        "songs",
    ):
        if str(ss.get(key) or "").strip():
            return True
    if ss.get("basket"):
        return True
    tw = ss.get("text_workshop")
    if isinstance(tw, dict):
        if str(tw.get("text_main_idea") or "").strip():
            return True
        insights = tw.get("approved_insights") or tw.get("insights") or []
        if isinstance(insights, list) and any(str(x or "").strip() for x in insights):
            return True
    sw = ss.get("sermon_workshop")
    if isinstance(sw, dict):
        for key in (
            "sermon_main_idea",
            "homiletical_claim",
            "sermon_outline",
            "sermon_outline_draft",
        ):
            if str(sw.get(key) or "").strip():
                return True
    return False


def current_igehely(session_state: MutableMapping[str, Any] | None = None) -> str:
    ss = session_state if session_state is not None else st.session_state
    return (
        str(ss.get("igehely_input") or "").strip()
        or str(ss.get("last_igehely") or "").strip()
    )


def apply_pending_passage_search_before_widget() -> None:
    """Igehely widget létrehozása ELŐTT — pending kiválasztás alkalmazása."""
    pending = st.session_state.pop(PENDING_APPLY_KEY, None)
    if not isinstance(pending, dict):
        return
    ref = str(pending.get("reference") or "").strip()
    if not ref:
        return
    try:
        ref = normalize_passage_reference(ref)
    except ValueError:
        st.session_state[FLASH_SELECT_KEY] = {
            "type": "error",
            "text": f"Érvénytelen igehely: {ref}",
        }
        return

    old_ref = current_igehely()
    mark_stale = bool(pending.get("mark_stale"))
    load_ruf = bool(pending.get("load_ruf", True))

    st.session_state["igehely_input"] = ref
    st.session_state["last_igehely"] = ref

    if mark_stale and old_ref and old_ref != ref:
        st.session_state[STALE_FLAG_KEY] = True
        st.session_state[STALE_FROM_REF_KEY] = old_ref

    state = ensure_passage_search_state()
    state["suggestions"] = []
    state["status"] = "idle"
    state["last_error"] = ""
    _save_state(state)
    st.session_state[EXPANDER_OPEN_KEY] = False
    st.session_state.pop(PENDING_CONFIRM_KEY, None)

    ruf_ok = False
    ruf_err = ""
    if load_ruf:
        result = fetch_ruf_passage(ref)
        if result.get("success"):
            _apply_ruf_fetch_success(result)
            ruf_ok = True
        else:
            ruf_err = str(
                result.get("error") or "A RÚF-szöveg betöltése nem sikerült."
            )

    msg = f"Az igehely kiválasztva: {ref}"
    if ruf_ok:
        msg += " A RÚF 2014 szöveg betöltődött."
    elif ruf_err:
        msg += f" A RÚF-betöltés nem sikerült: {ruf_err}"
    st.session_state[FLASH_SELECT_KEY] = {"type": "success", "text": msg}


def _queue_apply(reference: str, *, mark_stale: bool) -> None:
    st.session_state[PENDING_APPLY_KEY] = {
        "reference": reference,
        "mark_stale": mark_stale,
        "load_ruf": True,
    }
    st.rerun()


def request_select_suggestion(reference: str) -> None:
    """„Ezt választom” — megerősítés vagy azonnali apply."""
    try:
        ref = normalize_passage_reference(reference)
    except ValueError:
        st.error(f"Érvénytelen igehely: {reference}")
        return

    existing = current_igehely()
    has_material = workshop_material_present()
    if existing and has_material and existing != ref:
        st.session_state[PENDING_CONFIRM_KEY] = {"reference": ref}
        st.rerun()
        return
    _queue_apply(ref, mark_stale=False)


def _resolve_history(
    *,
    owner_sub: str | None,
    fetch_projects_fn: FetchProjectsFn | None,
) -> UsedPassageHistory:
    if not (owner_sub or "").strip():
        return empty_used_passage_history()
    return get_cached_used_passage_history(
        owner_sub=owner_sub,
        fetch_projects_fn=fetch_projects_fn,
        session_state=cast(MutableMapping[str, Any], st.session_state),
    )


def _run_search(
    *,
    occasion: str,
    context: str,
    exclude: list[str],
    history_exclude: list[str],
    generate_fn: GenerateFn,
) -> None:
    state = ensure_passage_search_state()
    state["occasion"] = occasion
    state["context"] = context
    state["status"] = "running"
    state["last_error"] = ""
    _save_state(state)

    occ_ctx = ensure_occasion_context_state(
        cast(MutableMapping[str, Any], st.session_state)
    )
    merged_context = merge_context_for_passage_search(
        context, occ_ctx, occasion=occasion
    )

    with st.spinner("Igehelyek keresése…"):
        result = suggest_passages_for_occasion(
            occasion=occasion,
            context=merged_context,
            exclude_references=exclude,
            history_exclude_references=history_exclude,
            generate_fn=generate_fn,
        )

    state = ensure_passage_search_state()
    state["occasion"] = occasion
    state["context"] = context

    if result.ok and result.suggestions:
        state["suggestions"] = [s.to_dict() for s in result.suggestions]
        state["excluded_references"] = list(result.excluded_references or exclude)
        state["generated_at"] = result.generated_at
        state["status"] = "ready"
        state["last_error"] = ""
    else:
        # Korábbi találatok megmaradnak (hiba / history-fetch nem töröl)
        state["status"] = "error"
        state["last_error"] = result.error_message or _API_FAIL_MSG
    _save_state(state)


def _render_occasion_background_card(occasion: str) -> None:
    """Kompakt, opcionális háttérmezők ceremoniális alkalmakhoz."""
    if not is_ceremonial_occasion(occasion):
        return

    occ_ctx = ensure_occasion_context_state(
        cast(MutableMapping[str, Any], st.session_state)
    )
    fields = occ_ctx.get("fields") if isinstance(occ_ctx.get("fields"), dict) else {}

    with st.container(key="passage_search_occasion_context", border=True):
        st.markdown("**Az alkalom háttere (opcionális)**")
        st.caption(
            "Néhány személyes vagy helyzeti adat segíthet az igehely és a "
            "megszólalás hangjának megválasztásában. Csak azt írd be, amit "
            "valóban fel szeretnél használni."
        )
        collected: dict[str, str] = {}
        for field_key, label, placeholder in field_defs_for_occasion(occasion):
            wkey = widget_key_for_field(field_key)
            if wkey not in st.session_state:
                st.session_state[wkey] = str(fields.get(field_key) or "")
            # Temetés/virrasztó: age rövid; többi text_area
            if field_key == "age":
                value = st.text_input(
                    label,
                    key=wkey,
                    placeholder=placeholder,
                )
            elif field_key in (
                "deceased_name",
                "child_name",
                "couple_names",
            ):
                value = st.text_input(
                    label,
                    key=wkey,
                    placeholder=placeholder,
                )
            else:
                value = st.text_area(
                    label,
                    key=wkey,
                    placeholder=placeholder,
                    height=68,
                )
            collected[field_key] = str(value or "").strip()

        update_occasion_context_fields(
            cast(MutableMapping[str, Any], st.session_state),
            occasion_type=occasion,
            fields=collected,
        )


def _render_history_controls(
    *,
    owner_sub: str | None,
    history: UsedPassageHistory,
) -> tuple[bool, list[str]]:
    """Toggle / feliratok. Vissza: (exclude_enabled, history_refs_for_ai)."""
    logged_in = bool((owner_sub or "").strip())
    if not logged_in:
        st.caption(
            "Bejelentkezve a mentett projektjeid textusait is figyelembe tudjuk venni."
        )
        return False, []

    if history.fetch_failed:
        st.warning(history.error_message or _HISTORY_FETCH_FAIL_MSG)
        return False, []

    if history.count <= 0:
        st.caption(
            "Még nincs olyan mentett projekted, amelyből korábbi textusokat "
            "tudnánk figyelembe venni."
        )
        return False, []

    if WIDGET_EXCLUDE_USED not in st.session_state:
        st.session_state[WIDGET_EXCLUDE_USED] = True

    exclude_on = st.toggle(
        "Korábban használt textusok kihagyása",
        key=WIDGET_EXCLUDE_USED,
    )
    st.caption(
        "A mentett projektjeid alapján. "
        f"Jelenleg {history.count} korábban használt igeszakaszt veszünk figyelembe."
    )
    if exclude_on:
        return True, list(history.normalized_references)
    return False, []


def render_passage_search_expander(
    *,
    generate_fn: GenerateFn,
    owner_sub: str | None = None,
    fetch_projects_fn: FetchProjectsFn | None = None,
) -> None:
    """Expander a „Melyik igeszakaszt elemezzük?” mező alatt."""
    state = ensure_passage_search_state()
    history = _resolve_history(
        owner_sub=owner_sub,
        fetch_projects_fn=fetch_projects_fn,
    )

    flash = st.session_state.pop(FLASH_SELECT_KEY, None)
    if isinstance(flash, dict) and flash.get("text"):
        kind = str(flash.get("type") or "success")
        if kind == "error":
            st.error(flash["text"])
        else:
            st.success(flash["text"])

    if st.session_state.get(STALE_FLAG_KEY):
        from_ref = str(st.session_state.get(STALE_FROM_REF_KEY) or "").strip()
        stale_note = (
            "A korábbi műhelyanyagok elavultnak vannak jelölve az igehelyváltás miatt"
            + (f" (korábbi: {from_ref})" if from_ref else "")
            + ". Nem töröltük őket — újraépítéshez indítsd újra a megfelelő generálást."
        )
        render_info_panel(title="Elavult anyagok", body=stale_note, tone="warning")

    pending_confirm = st.session_state.get(PENDING_CONFIRM_KEY)
    if isinstance(pending_confirm, dict) and pending_confirm.get("reference"):
        render_info_panel(title="Megerősítés szükséges", body=_CONFIRM_MSG, tone="warning")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Igen, módosítom az igehelyet",
                key="passage_search_confirm_yes",
                type="primary",
                use_container_width=True,
            ):
                ref = str(pending_confirm.get("reference") or "")
                st.session_state.pop(PENDING_CONFIRM_KEY, None)
                _queue_apply(ref, mark_stale=True)
        with c2:
            if st.button(
                "Mégse",
                key="passage_search_confirm_no",
                use_container_width=True,
            ):
                st.session_state.pop(PENDING_CONFIRM_KEY, None)
                st.rerun()

    if WIDGET_OCCASION not in st.session_state:
        st.session_state[WIDGET_OCCASION] = state.get("occasion") or OCCASION_OPTIONS[0]
    if WIDGET_CONTEXT not in st.session_state:
        st.session_state[WIDGET_CONTEXT] = state.get("context") or ""

    expanded = bool(st.session_state.get(EXPANDER_OPEN_KEY, False))
    with st.expander("Igehely keresése", expanded=expanded):
        st.caption(
            "Ha még nincs konkrét textusod, az alkalom és néhány opcionális "
            "szempont alapján kereshetsz prédikálható igeszakaszokat."
        )

        with st.container(key="passage_search_occasion_field"):
            occasion = st.selectbox(
                "Alkalom kiválasztása",
                list(OCCASION_OPTIONS),
                key=WIDGET_OCCASION,
            )
            st.caption("Az ajánlás ehhez igazodik.")

        # Ceremoniális alkalmak: opcionális strukturált háttér (adat megmarad, ha váltasz)
        _render_occasion_background_card(str(occasion or ""))
        update_occasion_context_fields(
            cast(MutableMapping[str, Any], st.session_state),
            occasion_type=str(occasion or ""),
        )

        context = st.text_area(
            "Az alkalom vagy a helyzet rövid leírása – opcionális",
            placeholder=(
                "Például: idős ember temetése; fiatalon és váratlanul elhunyt; "
                "hosszú házasság után; a gyülekezetben kialakult feszültség; "
                "hálaadás egy nehéz időszak után…"
            ),
            key=WIDGET_CONTEXT,
            height=90,
        )
        st.caption(
            "Ha üresen hagyod, az alkalmazás kizárólag az alkalom típusa alapján "
            "ajánl textusokat."
        )

        _, history_refs = _render_history_controls(
            owner_sub=owner_sub,
            history=history,
        )

        state["occasion"] = occasion
        state["context"] = str(context or "").strip()
        _save_state(state)

        btn_col, _ = st.columns([1, 2])
        with btn_col:
            search_clicked = st.button(
                "Igehelyek ajánlása",
                key="passage_search_run_btn",
                type="primary",
                use_container_width=True,
            )

        if search_clicked:
            st.session_state[EXPANDER_OPEN_KEY] = True
            _run_search(
                occasion=occasion,
                context=str(context or "").strip(),
                exclude=[],
                history_exclude=history_refs,
                generate_fn=generate_fn,
            )
            st.rerun()

        state = ensure_passage_search_state()
        if state.get("status") == "error" and state.get("last_error"):
            st.error(state["last_error"])

        suggestions = state.get("suggestions") or []
        show_used_badge = bool((owner_sub or "").strip()) and history.count > 0
        # Badge akkor is, ha a toggle ki van (ajánlás megjelenhet korábbi textussal)
        badge_history = history if show_used_badge else empty_used_passage_history()

        if suggestions:
            st.markdown("**Ajánlott igeszakaszok**")
            for idx, item in enumerate(suggestions):
                if not isinstance(item, dict):
                    continue
                ref = str(item.get("reference") or "").strip()
                title = str(item.get("title") or "").strip()
                reason = str(item.get("reason") or "").strip()
                direction = str(item.get("homiletical_direction") or "").strip()
                used, used_month = find_previous_usage(ref, badge_history)
                with st.container(border=True):
                    st.markdown(f"**{ref}**")
                    if used:
                        badge = "Korábban már használt textus"
                        if used_month:
                            badge += f" · Korábban használva: {used_month}"
                        st.caption(badge)
                    if title:
                        st.markdown(f"**{title}**")
                    if reason:
                        st.markdown(reason)
                    if direction:
                        st.caption(f"Homiletikai irány: {direction}")
                    if st.button(
                        "Ezt választom",
                        key=f"passage_search_pick_{idx}",
                        use_container_width=True,
                    ):
                        st.session_state[EXPANDER_OPEN_KEY] = True
                        request_select_suggestion(ref)

            if st.button(
                "Más igeszakaszokat kérek",
                key="passage_search_more_btn",
                use_container_width=True,
            ):
                st.session_state[EXPANDER_OPEN_KEY] = True
                exclude = merge_exclude_list(
                    suggestions,
                    state.get("excluded_references") or [],
                )
                state["excluded_references"] = exclude
                _save_state(state)
                # Session-exclude (előző kör) + opcionális history-exclude (toggle)
                hist_refs_now = list(history_refs)
                _run_search(
                    occasion=occasion,
                    context=str(context or "").strip(),
                    exclude=exclude,
                    history_exclude=hist_refs_now,
                    generate_fn=generate_fn,
                )
                st.rerun()


__all__ = [
    "SESSION_KEY",
    "PENDING_APPLY_KEY",
    "WIDGET_EXCLUDE_USED",
    "ensure_passage_search_state",
    "apply_pending_passage_search_before_widget",
    "workshop_material_present",
    "request_select_suggestion",
    "render_passage_search_expander",
]
