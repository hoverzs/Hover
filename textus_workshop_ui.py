"""Textus 2.0 Textusműhely — kézi UI (AI-hívás nélkül).

A textus fő gondolata és a továbbvihető felismerések felülete.
Csak a `text_workshop` adatot és a `textus_workshop_data` segédfüggvényeit
használja. Nem importál az app.py-ból.
"""

from __future__ import annotations

import streamlit as st

from textus_workshop_data import (
    add_approved_insight,
    ensure_text_workshop_state,
    remove_approved_insight,
    update_text_main_idea,
)

_STATUS_OPTIONS = ["draft", "approved"]
_STATUS_LABELS = {
    "draft": "Vázlat",
    "approved": "Jóváhagyva",
}

_INSIGHT_SOURCES = [
    "Saját megfigyelés",
    "Áttekintés",
    "Eredeti szöveg",
    "Exegézis",
    "Kortörténet",
    "Teológia",
]

_INSIGHT_CATEGORIES = [
    "Fő gondolat",
    "Szerkezet",
    "Kulcsszó vagy kifejezés",
    "Teológiai hangsúly",
    "Emberi helyzet",
    "Isten cselekvése és kegyelme",
    "Krisztus-kapcsolat",
    "Kép vagy kontraszt",
    "Nyitott kérdés",
    "Egyéb",
]

_SOURCE_REVIEW = [
    ("overview", "Áttekintés"),
    ("original_text", "Eredeti szöveg"),
    ("exegesis", "Exegézis"),
    ("history", "Kortörténet"),
    ("theology", "Teológia"),
]

_MAIN_IDEA_SOURCE = "A textus fő gondolata"
_MAIN_IDEA_CATEGORY = "Fő gondolat"

# Widgetkulcsok — csak session UI, nem project_data
_KEY_IDEA_INPUT = "tw_main_idea_input"
_KEY_IDEA_STATUS = "tw_main_idea_status_radio"
_RESYNC_FLAG = "_tw_ui_resync"


def _apply_tw_ui_resync_if_needed() -> None:
    """Widgetkulcsok szinkronja a tartós text_workshop adatokkal (widget előtt)."""
    tw = ensure_text_workshop_state(st.session_state)
    force = bool(st.session_state.pop(_RESYNC_FLAG, False))

    status = tw.get("text_main_idea_status") or "draft"
    if status not in _STATUS_OPTIONS:
        status = "draft"
    idea = tw.get("text_main_idea") or ""

    if force or _KEY_IDEA_INPUT not in st.session_state:
        st.session_state[_KEY_IDEA_INPUT] = idea
    if force or _KEY_IDEA_STATUS not in st.session_state:
        st.session_state[_KEY_IDEA_STATUS] = status


def _render_source_materials_expander() -> None:
    """Csak olvasható áttekintés a már elkészült műhelyanyagokról."""
    with st.expander("Korábbi műhelyanyagok áttekintése", expanded=False):
        any_content = False
        for key, label in _SOURCE_REVIEW:
            text = (st.session_state.get(key) or "").strip()
            if not text:
                continue
            any_content = True
            with st.expander(label, expanded=False):
                st.markdown(text)

        if not any_content:
            st.info(
                "Még nincs áttekinthető műhelyanyag. "
                "Ha az előző szakaszokban generálsz tartalmat, itt fog megjelenni."
            )


def render_text_main_idea_section() -> None:
    """Kézi szerkesztő: a textus fő gondolata (Gemini nélkül)."""
    _apply_tw_ui_resync_if_needed()
    ensure_text_workshop_state(st.session_state)

    st.header("A textus fő gondolata")
    st.markdown(
        "Fogalmazd meg egyetlen világos mondatban, mit állít ez az "
        "igeszakasz. Ne még a prédikáció témáját, hanem magának a "
        "textusnak a központi állítását keresd."
    )

    st.text_area(
        "A textus fő gondolata",
        key=_KEY_IDEA_INPUT,
        height=120,
        label_visibility="collapsed",
        placeholder="Egyetlen, világos mondat…",
    )

    st.radio(
        "Állapot",
        options=_STATUS_OPTIONS,
        format_func=lambda s: _STATUS_LABELS.get(s, s),
        horizontal=True,
        key=_KEY_IDEA_STATUS,
    )

    if st.button("Fő gondolat mentése", type="primary", key="tw_main_idea_save_btn"):
        content = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()
        status = st.session_state.get(_KEY_IDEA_STATUS) or "draft"
        if status not in _STATUS_OPTIONS:
            status = "draft"
        update_text_main_idea(st.session_state, content, status)
        st.success("A fő gondolat elmentve.")

    tw = ensure_text_workshop_state(st.session_state)
    saved = (tw.get("text_main_idea") or "").strip()
    saved_status = tw.get("text_main_idea_status") or ""
    if saved:
        label = _STATUS_LABELS.get(saved_status, saved_status or "—")
        st.caption(f"Elmentett állapot: **{label}**")

    _render_source_materials_expander()


def _insight_is_duplicate_main_idea(content: str) -> bool:
    tw = ensure_text_workshop_state(st.session_state)
    needle = (content or "").strip()
    for item in tw.get("approved_insights") or []:
        if not isinstance(item, dict):
            continue
        if (
            (item.get("source") or "") == _MAIN_IDEA_SOURCE
            and (item.get("category") or "") == _MAIN_IDEA_CATEGORY
            and (item.get("content") or "").strip() == needle
        ):
            return True
    return False


def _render_forward_main_idea_button() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    idea = (tw.get("text_main_idea") or "").strip()
    status = tw.get("text_main_idea_status") or ""
    if not idea or status != "approved":
        return

    if st.button(
        "Fő gondolat hozzáadása a továbbvihető felismerésekhez",
        key="tw_forward_main_idea_btn",
    ):
        if _insight_is_duplicate_main_idea(idea):
            st.info(
                "Ez a fő gondolat változatlan tartalommal már szerepel "
                "a továbbvihető felismerések között."
            )
        else:
            add_approved_insight(
                st.session_state,
                _MAIN_IDEA_SOURCE,
                _MAIN_IDEA_CATEGORY,
                idea,
            )
            st.success("A fő gondolat hozzáadva a továbbvihető felismerésekhez.")
            st.rerun()


def _render_insight_cards() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    insights = list(tw.get("approved_insights") or [])
    if not insights:
        st.info(
            "Még nincs jóváhagyott felismerés. "
            "Add hozzá az elsőt a fenti űrlapon, vagy továbbítsd a jóváhagyott fő gondolatot."
        )
        return

    for item in insights:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id") or "")
        if not iid:
            continue
        source = item.get("source") or "—"
        category = item.get("category") or "—"
        content = item.get("content") or ""
        created = item.get("created_at") or ""

        with st.container(border=True):
            st.markdown(f"**Forrás:** {source}  \n**Kategória:** {category}")
            if created:
                st.caption(f"Létrehozva: {created}")
            st.markdown(content)

            confirm_key = f"tw_insight_del_confirm_{iid}"
            if st.session_state.get(confirm_key):
                st.warning("Biztosan törölni szeretnéd ezt a felismerést?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        "Igen, törlés",
                        key=f"tw_insight_del_yes_{iid}",
                        type="primary",
                    ):
                        remove_approved_insight(st.session_state, iid)
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                with c2:
                    if st.button("Mégse", key=f"tw_insight_del_no_{iid}"):
                        st.session_state[confirm_key] = False
                        st.rerun()
            else:
                if st.button(
                    "Felismerés eltávolítása",
                    key=f"tw_insight_del_{iid}",
                ):
                    st.session_state[confirm_key] = True
                    st.rerun()


def render_approved_insights_section() -> None:
    """Jóváhagyott, továbbvihető felismerések gyűjtése (Gemini nélkül)."""
    ensure_text_workshop_state(st.session_state)

    st.header("Mit viszünk tovább?")
    st.markdown(
        "Itt gyűjtheted össze azokat a felismeréseket, amelyekre az "
        "igehirdetés felépítésekor valóban támaszkodni szeretnél."
    )

    _render_forward_main_idea_button()

    with st.form("tw_add_insight_form", clear_on_submit=True):
        source = st.selectbox("Forrás", options=_INSIGHT_SOURCES)
        category = st.selectbox("Kategória", options=_INSIGHT_CATEGORIES)
        content = st.text_area(
            "Tartalom",
            placeholder="Fogalmazd meg röviden a továbbvihető felismerést…",
            height=100,
        )
        submitted = st.form_submit_button(
            "Jóváhagyott felismerés hozzáadása",
            type="primary",
        )

    if submitted:
        text = (content or "").strip()
        if not text:
            st.warning("Üres felismerést nem lehet hozzáadni.")
        else:
            add_approved_insight(st.session_state, source, category, text)
            st.success("Felismerés hozzáadva.")
            st.rerun()

    st.subheader("Jóváhagyott felismerések")
    _render_insight_cards()


__all__ = [
    "render_text_main_idea_section",
    "render_approved_insights_section",
]
