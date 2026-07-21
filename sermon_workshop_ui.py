"""Textus 2.0 Igehirdetési műhely — UI (M4: kézi fő gondolat + emberi helyzet).

Gemini nélkül. Nem importál az app.py-ból.
"""

from __future__ import annotations

import streamlit as st

from sermon_workshop_data import (
    add_approved_sermon_decision,
    ensure_sermon_workshop_state,
    remove_approved_sermon_decision,
    update_sermon_workshop_section,
)
from textus_workshop_data import ensure_text_workshop_state

_SW_SECTION_OPTIONS = [
    "Az igehirdetés fő gondolata",
    "Emberi helyzet és kegyelmi válasz",
    "Hallgatói kérdés és feszültség",
    "Krisztus-központú és evangéliumi ív",
    "A prédikáció útja",
    "Prédikációs mozgások",
    "Képek, illusztrációk és alkalmazás",
    "Lezárás",
    "Homiletikai diagnosztika",
]

_SW_SECTION_PLACEHOLDERS: dict[str, dict[str, str]] = {
    "Hallgatói kérdés és feszültség": {
        "goal": (
            "Megfogalmazni a hallgató valódi kérdését és a prédikációt "
            "mozgató feszültséget."
        ),
        "later": (
            "Itt döntöd el, mi tartja fenn a figyelmet — anélkül, "
            "hogy többet ígérnél, mint amit a textus kínál."
        ),
    },
    "Krisztus-központú és evangéliumi ív": {
        "goal": (
            "Meghatározni, hogyan kapcsolódik a textus Krisztushoz "
            "és az evangéliumhoz — erőltetés nélkül."
        ),
        "later": (
            "Itt jelölöd a kapcsolattípust, a kegyelem elsőbbségét, "
            "és a bizonytalanságot, ha a kapcsolat közvetett."
        ),
    },
    "A prédikáció útja": {
        "goal": (
            "Kiválasztani, hogyan haladjon a prédikáció "
            "(például elöl kimondott állítás, közös felfedezés, történet)."
        ),
        "later": (
            "Itt a forma természetes nyelven jelenik meg — nem "
            "szakzsargon-fülekben."
        ),
    },
    "Prédikációs mozgások": {
        "goal": (
            "3–5 felismerési mozgásban megtervezni, mit lát meg a "
            "hallgató szakaszról szakaszra."
        ),
        "later": (
            "Itt nem pontlistát, hanem indulást, felismerést és "
            "továbbhaladást szerkesztesz."
        ),
    },
    "Képek, illusztrációk és alkalmazás": {
        "goal": (
            "Válogatni textusból eredő képeket, illusztrációkat és "
            "konkrét alkalmazásokat."
        ),
        "later": (
            "Itt a meglévő illusztráció / aktualizálás anyagából is "
            "átvehetsz elemeket — a régi promptok változatlanok maradnak."
        ),
    },
    "Lezárás": {
        "goal": (
            "Meghatározni, hová érkezik a hallgató, milyen reménységet "
            "visz, és mi maradjon nyitott."
        ),
        "later": (
            "Itt a lezárás nem puszta összefoglaló, és nem érzelmi "
            "manipuláció."
        ),
    },
    "Homiletikai diagnosztika": {
        "goal": (
            "Rövid, szöveges tükrözést kapni textushűségről, egységről, "
            "kegyelemről és hallhatóságról."
        ),
        "later": (
            "Itt legfeljebb három javítási prioritás jelenik meg — "
            "pontszám és automatikus átírás nélkül."
        ),
    },
}

_SW_NEXT_HINTS: dict[str, str] = {
    "Az igehirdetés fő gondolata": (
        "Következő ajánlott lépés: Emberi helyzet és kegyelmi válasz"
    ),
    "Emberi helyzet és kegyelmi válasz": (
        "Következő ajánlott lépés: Hallgatói kérdés és feszültség"
    ),
    "Hallgatói kérdés és feszültség": (
        "Következő ajánlott lépés: Krisztus-központú és evangéliumi ív"
    ),
    "Krisztus-központú és evangéliumi ív": (
        "Következő ajánlott lépés: A prédikáció útja"
    ),
    "A prédikáció útja": "Következő ajánlott lépés: Prédikációs mozgások",
    "Prédikációs mozgások": (
        "Következő ajánlott lépés: Képek, illusztrációk és alkalmazás"
    ),
    "Képek, illusztrációk és alkalmazás": "Következő ajánlott lépés: Lezárás",
    "Lezárás": "Következő ajánlott lépés: Homiletikai diagnosztika",
}

_STATUS_LABELS = {
    "draft": "Vázlat",
    "approved": "Jóváhagyva",
}

_SOURCE_SERMON_MAIN = "Az igehirdetés fő gondolata"
_SOURCE_HUMAN = "Emberi helyzet és kegyelmi válasz"
_CAT_MAIN_IDEA = "Fő gondolat"

_HC_FIELDS = [
    ("condition", "Milyen emberi helyzetet tár fel a textus?", "Emberi helyzet", False),
    (
        "false_response",
        "Milyen téves vagy elégtelen emberi válasz jelenik meg? (opcionális)",
        "Téves emberi válasz",
        True,
    ),
    ("human_need", "Mire van valójában szüksége az embernek?", "Emberi szükség", False),
    ("divine_action", "Mit cselekszik Isten ebben a helyzetben?", "Isten cselekvése", False),
    (
        "grace_response",
        "Milyen választ tesz lehetővé Isten kegyelme?",
        "Kegyelmi válasz",
        False,
    ),
]

# Widget / technikai kulcsok — nem project_data
_KEY_ACTIVE_SECTION = "sw_active_section"
_KEY_SERMON_IDEA = "sw_sermon_main_idea_input"
_KEY_HC = {
    "condition": "sw_hc_condition",
    "false_response": "sw_hc_false_response",
    "human_need": "sw_hc_human_need",
    "divine_action": "sw_hc_divine_action",
    "grace_response": "sw_hc_grace_response",
}
_RESYNC_FLAG = "_sw_ui_resync"


def _session_str(*keys: str) -> str:
    for key in keys:
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _apply_sw_ui_resync_if_needed() -> None:
    """Widgetkulcsok szinkronja a tartós sermon_workshop adatokkal (widget előtt)."""
    sw = ensure_sermon_workshop_state(st.session_state)
    force = bool(st.session_state.pop(_RESYNC_FLAG, False))

    idea = sw.get("sermon_main_idea") or ""
    if force or _KEY_SERMON_IDEA not in st.session_state:
        st.session_state[_KEY_SERMON_IDEA] = idea

    hc = sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    for field, wkey in _KEY_HC.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(hc.get(field) or "")


def _render_shell_input_summary() -> None:
    """Rövid bemeneti összegzés a shell tetején."""
    tw = ensure_text_workshop_state(st.session_state)
    passage = _session_str("last_igehely", "igehely_input") or "—"
    idea = (tw.get("text_main_idea") or "").strip()
    status = (tw.get("text_main_idea_status") or "").strip()
    insights = tw.get("approved_insights") or []
    insight_count = len(insights) if isinstance(insights, list) else 0
    project_title = (
        _session_str("current_project_title")
        or _session_str("project_title_input")
        or ""
    )

    if status == "approved" and idea:
        idea_line = idea
    elif idea:
        idea_line = f"{idea} *(még nem jóváhagyva)*"
    else:
        idea_line = "—"

    st.markdown(
        f"**Igehely:** {passage}  \n"
        f"**A textus fő gondolata:** {idea_line}  \n"
        f"**Jóváhagyott felismerések:** {insight_count}"
        + (f"  \n**Projekt:** {project_title}" if project_title else "")
    )

    if status != "approved" or not idea:
        st.info(
            "A műhely használható, de a homiletikai munka biztosabb alapokon "
            "áll, ha előbb jóváhagyod a textus fő gondolatát."
        )


def _render_textus_basis_expander() -> None:
    """Csak olvasható Textusműhely-alapok — alapból összecsukva."""
    tw = ensure_text_workshop_state(st.session_state)
    with st.expander("Textusműhelyi alapok", expanded=False):
        idea = (tw.get("text_main_idea") or "").strip()
        status = (tw.get("text_main_idea_status") or "").strip()
        st.markdown("**A textus fő gondolata**")
        if idea:
            label = _STATUS_LABELS.get(status, status or "—")
            st.markdown(idea)
            st.caption(f"Státusz: {label}")
        else:
            st.caption("Még nincs megfogalmazva.")

        insights = tw.get("approved_insights") or []
        st.markdown("**Jóváhagyott felismerések**")
        if isinstance(insights, list) and insights:
            for item in insights:
                if not isinstance(item, dict):
                    continue
                content = (item.get("content") or "").strip()
                if not content:
                    continue
                cat = (item.get("category") or "").strip()
                src = (item.get("source") or "").strip()
                prefix = f"**{cat}** — " if cat else ""
                suffix = f" *(forrás: {src})*" if src else ""
                st.markdown(f"- {prefix}{content}{suffix}")
        else:
            st.caption("Még nincs jóváhagyott felismerés.")

        for key, label in (("exegesis", "Exegézis"), ("theology", "Teológia")):
            text = (st.session_state.get(key) or "").strip()
            if not text:
                continue
            with st.expander(label, expanded=False):
                st.markdown(text)


def _decision_is_duplicate(
    *,
    source_section: str,
    category: str,
    content: str,
) -> bool:
    sw = ensure_sermon_workshop_state(st.session_state)
    needle = (content or "").strip()
    for item in sw.get("approved_sermon_decisions") or []:
        if not isinstance(item, dict):
            continue
        if (
            (item.get("source_section") or "") == source_section
            and (item.get("category") or "") == category
            and (item.get("content") or "").strip() == needle
        ):
            return True
    return False


def _render_decisions_for_section(source_section: str) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    items = [
        item
        for item in (sw.get("approved_sermon_decisions") or [])
        if isinstance(item, dict)
        and (item.get("source_section") or "") == source_section
    ]
    with st.expander("Jóváhagyott homiletikai döntések", expanded=False):
        if not items:
            st.caption("Ebben a szakaszban még nincs jóváhagyott döntés.")
            return
        for item in items:
            did = str(item.get("id") or "")
            if not did:
                continue
            category = item.get("category") or "—"
            content = item.get("content") or ""
            created = item.get("created_at") or ""
            with st.container(border=True):
                st.markdown(f"**{category}**")
                if created:
                    st.caption(f"Létrehozva: {created}")
                st.markdown(content)
                confirm_key = f"sw_decision_del_confirm_{did}"
                if st.session_state.get(confirm_key):
                    st.warning("Biztosan eltávolítod ezt a döntést?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "Igen, törlés",
                            key=f"sw_decision_del_yes_{did}",
                            type="primary",
                        ):
                            remove_approved_sermon_decision(st.session_state, did)
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                    with c2:
                        if st.button("Mégse", key=f"sw_decision_del_no_{did}"):
                            st.session_state[confirm_key] = False
                            st.rerun()
                else:
                    if st.button(
                        "Döntés eltávolítása",
                        key=f"sw_decision_del_{did}",
                    ):
                        st.session_state[confirm_key] = True
                        st.rerun()


def render_sermon_main_idea_section() -> None:
    """Az igehirdetés fő gondolata — kézi szerkesztő (Gemini nélkül)."""
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    tw = ensure_text_workshop_state(st.session_state)

    st.subheader("Az igehirdetés fő gondolata")
    st.markdown(
        "Fogalmazd meg egyetlen világos mondatban, mit szeretnél, hogy a "
        "hallgató a textus alapján felismerjen. Ez még nem cím és nem "
        "vázlat, hanem az egész igehirdetést összetartó állítás."
    )

    passage = _session_str("last_igehely", "igehely_input") or "—"
    text_idea = (tw.get("text_main_idea") or "").strip()
    text_status = (tw.get("text_main_idea_status") or "").strip()
    insights = tw.get("approved_insights") or []
    insight_count = len(insights) if isinstance(insights, list) else 0

    st.markdown(
        f"**Igehely:** {passage}  \n"
        f"**A textus fő gondolata:** {text_idea or '—'}  \n"
        f"**Jóváhagyott felismerések:** {insight_count}"
    )
    if text_status != "approved" or not text_idea:
        st.info(
            "A textus fő gondolata még nincs jóváhagyva. A szakasz használható, "
            "de a homiletikai munka biztosabb alapokon áll, ha előbb a "
            "Textusműhelyben jóváhagyod."
        )

    st.text_area(
        "Az igehirdetés fő gondolata",
        key=_KEY_SERMON_IDEA,
        height=120,
        label_visibility="collapsed",
        placeholder="Egyetlen, hallható állítás…",
    )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_sermon_idea_save_draft"):
            content = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
            if not content:
                st.warning("Üres fő gondolatot nem lehet menteni. Írj egy mondatot.")
            else:
                update_sermon_workshop_section(
                    st.session_state,
                    "sermon_main_idea",
                    {
                        "sermon_main_idea": content,
                        "sermon_main_idea_status": "draft",
                    },
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_sermon_idea_approve",
        ):
            content = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
            if not content:
                st.warning(
                    "Üres fő gondolatot nem lehet jóváhagyni. Írj egy mondatot."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state,
                    "sermon_main_idea",
                    {
                        "sermon_main_idea": content,
                        "sermon_main_idea_status": "approved",
                    },
                )
                if _decision_is_duplicate(
                    source_section=_SOURCE_SERMON_MAIN,
                    category=_CAT_MAIN_IDEA,
                    content=content,
                ):
                    st.success(
                        "Jóváhagyva. Ez a fő gondolat már szerepel a "
                        "homiletikai döntések között."
                    )
                else:
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_SERMON_MAIN,
                        _CAT_MAIN_IDEA,
                        content,
                    )
                    st.success("Jóváhagyva és továbbvíve a homiletikai döntésekhez.")

    sw = ensure_sermon_workshop_state(st.session_state)
    saved = (sw.get("sermon_main_idea") or "").strip()
    saved_status = sw.get("sermon_main_idea_status") or ""
    if saved or saved_status:
        label = _STATUS_LABELS.get(saved_status, saved_status or "—")
        st.caption(f"Elmentett állapot: **{label}**")

    _render_textus_basis_expander()
    _render_decisions_for_section(_SOURCE_SERMON_MAIN)


def render_human_condition_section() -> None:
    """Emberi helyzet és kegyelmi válasz — kézi szerkesztő (Gemini nélkül)."""
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Emberi helyzet és kegyelmi válasz")
    st.markdown(
        "Vizsgáld meg, milyen emberi helyzetet tár fel a textus, és mit "
        "cselekszik ebben a helyzetben Isten. Ne csak problémát keress: "
        "figyelj a korlátozottságra, téves bizalomra, félelemre, vágyra, "
        "törésre és reménységre is."
    )

    for field, label, _category, _optional in _HC_FIELDS:
        st.text_area(
            label,
            key=_KEY_HC[field],
            height=80,
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_hc_save_draft"):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_HC.items()
            }
            if not (block["condition"] or block["divine_action"]):
                st.warning(
                    "A mentéshez legalább az emberi helyzet vagy Isten "
                    "cselekvése mezőt töltsd ki."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "human_condition", block
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_hc_approve",
        ):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_HC.items()
            }
            if not (block["condition"] or block["divine_action"]):
                st.warning(
                    "A jóváhagyáshoz legalább az emberi helyzet vagy Isten "
                    "cselekvése mezőt töltsd ki."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "human_condition", block
                )
                added = 0
                skipped = 0
                for field, _label, category, _optional in _HC_FIELDS:
                    content = block.get(field) or ""
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_HUMAN,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_HUMAN,
                        category,
                        content,
                    )
                    added += 1
                if added and skipped:
                    st.success(
                        f"Jóváhagyva. {added} új döntés került továbbvitelre; "
                        f"{skipped} már szerepelt."
                    )
                elif added:
                    st.success(
                        f"Jóváhagyva és továbbvíve ({added} homiletikai döntés)."
                    )
                else:
                    st.success(
                        "Jóváhagyva. A kitöltött elemek már szerepeltek a "
                        "homiletikai döntések között."
                    )

    st.caption("Következő ajánlott lépés: Hallgatói kérdés és feszültség")
    _render_decisions_for_section(_SOURCE_HUMAN)


def _render_section_placeholder(section: str) -> None:
    meta = _SW_SECTION_PLACEHOLDERS.get(section) or {
        "goal": "Ez a szakasz a későbbi mérföldkövekben válik működővé.",
        "later": "Itt később homiletikai döntést hozol.",
    }
    st.subheader(section)
    st.markdown(f"**Cél:** {meta['goal']}")
    st.markdown(meta["later"])
    st.caption("Következő fejlesztési mérföldkőben válik működővé.")


def render_sermon_workshop_shell() -> None:
    """Igehirdetési műhely keret — M4: két működő szakasz + helyőrzők."""
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    ensure_text_workshop_state(st.session_state)

    st.header("Igehirdetési műhely")
    st.caption(
        "A textus megértésétől a hallható, textushű és kegyelemközpontú "
        "igehirdetés felépítéséig."
    )

    _render_shell_input_summary()

    if st.session_state.get(_KEY_ACTIVE_SECTION) not in _SW_SECTION_OPTIONS:
        st.session_state[_KEY_ACTIVE_SECTION] = _SW_SECTION_OPTIONS[0]

    st.radio(
        "Aktív szakasz",
        options=_SW_SECTION_OPTIONS,
        key=_KEY_ACTIVE_SECTION,
    )

    active = st.session_state.get(_KEY_ACTIVE_SECTION) or _SW_SECTION_OPTIONS[0]
    if active == "Az igehirdetés fő gondolata":
        render_sermon_main_idea_section()
    elif active == "Emberi helyzet és kegyelmi válasz":
        render_human_condition_section()
    else:
        _render_section_placeholder(active)

    # A két működő szakasz saját hintet / döntéslistát kezel;
    # a helyőrzőknél a shell adja a következő lépést.
    if active not in (
        "Az igehirdetés fő gondolata",
        "Emberi helyzet és kegyelmi válasz",
    ):
        next_hint = _SW_NEXT_HINTS.get(active)
        if next_hint:
            st.caption(next_hint)
    elif active == "Az igehirdetés fő gondolata":
        st.caption(_SW_NEXT_HINTS[active])


__all__ = [
    "render_sermon_workshop_shell",
    "render_sermon_main_idea_section",
    "render_human_condition_section",
]
