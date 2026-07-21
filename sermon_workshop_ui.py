"""Textus 2.0 Igehirdetési műhely — UI-keret (M3: MI nélkül).

Helyőrző szakaszok + bemeneti összegzés a Textusműhely adataiból.
Nem importál az app.py-ból, nem hív Geminit.
"""

from __future__ import annotations

import streamlit as st

from sermon_workshop_data import ensure_sermon_workshop_state
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
    "Az igehirdetés fő gondolata": {
        "goal": (
            "Egyetlen, hallható és textushű mondatban megfogalmazni, "
            "mit szeretnél, hogy a hallgató hazavigyen."
        ),
        "later": (
            "Itt döntöd el az igehirdetés fő gondolatát — ez nem azonos "
            "a textus fő gondolatával, és nem prédikációs cím."
        ),
    },
    "Emberi helyzet és kegyelmi válasz": {
        "goal": (
            "Megnevezni a textus és a hallgató közös emberi helyzetét, "
            "valamint Isten kegyelmi válaszát."
        ),
        "later": (
            "Itt választod szét a törést / szükségét és a kegyelmet — "
            "sablonos bűnprobléma nélkül."
        ),
    },
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

_KEY_ACTIVE_SECTION = "sw_active_section"


def _session_str(*keys: str) -> str:
    for key in keys:
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _render_input_summary() -> None:
    """Rövid bemeneti összegzés a Textusműhely / projekt adataiból."""
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
    """Igehirdetési műhely keret — M3 helyőrzők, Gemini nélkül."""
    ensure_sermon_workshop_state(st.session_state)
    ensure_text_workshop_state(st.session_state)

    st.header("Igehirdetési műhely")
    st.caption(
        "A textus megértésétől a hallható, textushű és kegyelemközpontú "
        "igehirdetés felépítéséig."
    )

    _render_input_summary()

    if st.session_state.get(_KEY_ACTIVE_SECTION) not in _SW_SECTION_OPTIONS:
        st.session_state[_KEY_ACTIVE_SECTION] = _SW_SECTION_OPTIONS[0]

    st.radio(
        "Aktív szakasz",
        options=_SW_SECTION_OPTIONS,
        key=_KEY_ACTIVE_SECTION,
    )

    active = st.session_state.get(_KEY_ACTIVE_SECTION) or _SW_SECTION_OPTIONS[0]
    _render_section_placeholder(active)

    next_hint = _SW_NEXT_HINTS.get(active)
    if next_hint:
        st.caption(next_hint)


__all__ = [
    "render_sermon_workshop_shell",
]
