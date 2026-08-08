"""Konkordancia — önálló, kinyitható panel az Igehely fülön.

Kizárólag a helyi, teljes Biblia szintű RÚF-szövegtárat
(`ruf_bible_local_db.py`) használja szó szerinti kereséshez — a fő
igehely-beviteli mezőt és a "Bibliai szöveg" betöltést (mindkettő az
élő Szentírás.eu API-t hívja `ruf_bible_service.fetch_ruf_passage`-on
keresztül) ez a modul nem érinti.
"""

from __future__ import annotations

import streamlit as st

import ruf_bible_local_db as local_db
from passage_search_ui import request_select_suggestion
from ruf_bible_service import CANONICAL_BOOKS
from ui_components import render_info_panel


PAGE_SIZE = 20
_MANY_RESULTS_THRESHOLD = 200

# Az első 39 könyv az ÓSZ, a maradék 27 az ÚSZ — a CANONICAL_BOOKS
# kanonikus, 1Móz..Jel sorrendben tárolja őket.
_OT_CODES: tuple[str, ...] = tuple(b.code for b in CANONICAL_BOOKS[:39])
_NT_CODES: tuple[str, ...] = tuple(b.code for b in CANONICAL_BOOKS[39:])
_OT_CODE_SET = set(_OT_CODES)

TESTAMENT_BOOK_CODES: dict[str, list[str] | None] = {
    "Egész Biblia": None,
    "Ószövetség": list(_OT_CODES),
    "Újszövetség": list(_NT_CODES),
}

QUERY_WIDGET_KEY = "concordance_query_input"
TESTAMENT_WIDGET_KEY = "concordance_testament_input"
_COMMITTED_QUERY_KEY = "_concordance_committed_query"
_COMMITTED_TESTAMENT_KEY = "_concordance_committed_testament"
_OFFSET_KEY = "_concordance_offset"


def render_concordance_expander() -> None:
    """A "Konkordancia" kinyitható panel — az "Igehely keresése" alatt."""
    with st.expander("Konkordancia", expanded=False):
        st.caption(
            "Keress rá egy szóra vagy kifejezésre a teljes RÚF 2014 szövegében."
        )

        if not local_db.database_exists():
            render_info_panel(
                title="A konkordancia-kereső még nem elérhető",
                body=(
                    "A helyi, teljes Biblia szintű RÚF-szövegtár nincs "
                    "importálva ezen a példányon."
                ),
                tone="neutral",
            )
            return

        col_query, col_filter, col_btn = st.columns([3, 2, 1])
        with col_query:
            st.text_input(
                "Keresett szó vagy kifejezés",
                key=QUERY_WIDGET_KEY,
                placeholder="Pl. szeretet, örök élet",
                label_visibility="collapsed",
            )
        with col_filter:
            st.selectbox(
                "Szűrés",
                options=list(TESTAMENT_BOOK_CODES.keys()),
                key=TESTAMENT_WIDGET_KEY,
                label_visibility="collapsed",
            )
        with col_btn:
            search_clicked = st.button(
                "Keresés",
                key="concordance_search_btn",
                type="primary",
                use_container_width=True,
            )

        if search_clicked:
            st.session_state[_COMMITTED_QUERY_KEY] = (
                st.session_state.get(QUERY_WIDGET_KEY) or ""
            ).strip()
            st.session_state[_COMMITTED_TESTAMENT_KEY] = st.session_state.get(
                TESTAMENT_WIDGET_KEY, "Egész Biblia"
            )
            st.session_state[_OFFSET_KEY] = 0

        _render_results()


def _render_results() -> None:
    committed_query = str(st.session_state.get(_COMMITTED_QUERY_KEY) or "").strip()
    if not committed_query:
        st.caption(
            "Még nincs keresés. Írj be egy szót vagy kifejezést, és kattints "
            "a Keresésre."
        )
        return

    testament_label = str(
        st.session_state.get(_COMMITTED_TESTAMENT_KEY) or "Egész Biblia"
    )
    book_codes = TESTAMENT_BOOK_CODES.get(testament_label)
    offset = max(0, int(st.session_state.get(_OFFSET_KEY, 0)))

    total = local_db.count_literal(committed_query, book_codes=book_codes)
    if total == 0:
        st.info(f"Nincs találat erre: „{committed_query}”.")
        return

    hits = local_db.search_literal(
        committed_query, book_codes=book_codes, limit=PAGE_SIZE, offset=offset
    )
    if not hits:
        # Az offset túlfutott a találatokon (pl. új, szűkebb keresés után).
        st.session_state[_OFFSET_KEY] = 0
        st.rerun()
        return

    page_start = offset + 1
    page_end = offset + len(hits)
    st.caption(
        f"{total} találat erre: „{committed_query}” ({page_start}–{page_end} megjelenítve)"
    )
    if total > _MANY_RESULTS_THRESHOLD:
        st.caption(
            "Sok találat — szűkítsd Ószövetségre/Újszövetségre a jobb "
            "áttekinthetőségért."
        )

    current_group: str | None = None
    for hit in hits:
        group = "ÓSZÖVETSÉG" if hit.book_code in _OT_CODE_SET else "ÚJSZÖVETSÉG"
        if group != current_group:
            st.markdown(f"**{group}**")
            current_group = group
        reference = f"{hit.book_abbr} {hit.chapter},{hit.verse}"
        col_text, col_jump = st.columns([5, 1])
        with col_text:
            st.markdown(f"`{reference}` — {hit.snippet}")
        with col_jump:
            if st.button(
                "Ugrás",
                key=f"concordance_jump_{hit.book_code}_{hit.chapter}_{hit.verse}_{offset}",
            ):
                request_select_suggestion(reference)

    nav_prev, _nav_mid, nav_next = st.columns([1, 2, 1])
    with nav_prev:
        if offset > 0 and st.button("← Előző 20", key="concordance_prev_btn"):
            st.session_state[_OFFSET_KEY] = max(0, offset - PAGE_SIZE)
            st.rerun()
    with nav_next:
        if offset + PAGE_SIZE < total and st.button(
            "Következő 20 →", key="concordance_next_btn"
        ):
            st.session_state[_OFFSET_KEY] = offset + PAGE_SIZE
            st.rerun()


__all__ = [
    "render_concordance_expander",
    "TESTAMENT_BOOK_CODES",
    "PAGE_SIZE",
]
