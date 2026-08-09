"""Konkordancia — önálló, kinyitható panel az Igehely fülön.

Egy explicit kapcsoló két főmód között (NEM automatikus felismerés — egy
összetett kérdés nyelvtanilag nem különböztethető meg megbízhatóan egy
hosszabb kifejezéstől):

  A. "Pontos kifejezés" — a keresőmezőn belül továbbra is automatikus
     al-mód-felismerés:
       1. Szó szerinti RÚF-keresés (`ruf_bible_local_db.py`) —
          alapértelmezett, ha a bevitel nem Strong-kód és nem
          héber/görög írásjel.
       2. Eredeti nyelvi (héber/görög) keresés
          (`original_language_concordance.py`) — Strong-kód mintára
          (pl. "H3467", "G2316") vagy héber/görög írásjelre aktiválódik.
  B. "Kérdés/fogalom" — összetett, teológiai/fogalmi kérdésekhez
     (`concept_concordance.py`) — EGY Gemini-hívással igehelyeket,
     kulcsszavakat és eredeti nyelvi terminusokat von ki a kérdésből,
     majd a fenti 1-2. mód motorjaival egészíti ki a találatokat.

Egyik mód sem érinti a fő igehely-beviteli mezőt vagy a "Bibliai szöveg"
betöltést (mindkettő az élő Szentírás.eu API-t hívja
`ruf_bible_service.fetch_ruf_passage`-on keresztül) — a Konkordancia
kizárólag a helyi RÚF- és héber/görög szövegtárakat használja (a "Kérdés/
fogalom" mód Gemini-hívása is csak a felhasználó kérdését küldi el, a
helyi szövegtár tartalmát sosem).
"""

from __future__ import annotations

import streamlit as st

import concept_concordance as concept
import original_language_concordance as olc
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
CONCEPT_QUERY_WIDGET_KEY = "concordance_concept_query_input"
TESTAMENT_WIDGET_KEY = "concordance_testament_input"
MODE_TOGGLE_KEY = "concordance_top_mode"
_MODE_EXACT = "Pontos kifejezés"
_MODE_CONCEPT = "Kérdés/fogalom"
_COMMITTED_QUERY_KEY = "_concordance_committed_query"
_COMMITTED_TESTAMENT_KEY = "_concordance_committed_testament"
_COMMITTED_MODE_KEY = "_concordance_committed_mode"  # "literal" | "original" | "concept"
_OFFSET_KEY = "_concordance_offset"
_PREFILL_QUERY_KEY = "_concordance_prefill_query"


def request_original_language_search(query: str) -> None:
    """Az "Eredeti szöveg tanulmányozása" fülről hívható: előre kitölti
    a Konkordancia keresőmezőjét egy Strong-számmal/lemmával, és
    azonnal el is indítja a 2. módú keresést a következő rerunon."""
    st.session_state[_PREFILL_QUERY_KEY] = query


def render_concordance_expander() -> None:
    """A "Konkordancia" kinyitható panel — az "Igehely keresése" alatt."""
    prefill = st.session_state.pop(_PREFILL_QUERY_KEY, None)
    if prefill:
        st.session_state[MODE_TOGGLE_KEY] = _MODE_EXACT
        st.session_state[QUERY_WIDGET_KEY] = prefill
        st.session_state[_COMMITTED_QUERY_KEY] = prefill
        st.session_state[_COMMITTED_TESTAMENT_KEY] = "Egész Biblia"
        st.session_state[_OFFSET_KEY] = 0

    with st.expander("Konkordancia", expanded=bool(prefill)):
        if not local_db.database_exists():
            with st.spinner("Konkordancia-adatbázis előkészítése…"):
                local_db.ensure_local_database()

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

        top_mode = st.radio(
            "Konkordancia mód",
            options=[_MODE_EXACT, _MODE_CONCEPT],
            key=MODE_TOGGLE_KEY,
            horizontal=True,
            label_visibility="collapsed",
        )

        if top_mode == _MODE_CONCEPT:
            _render_concept_input()
        else:
            _render_exact_input()

        _render_results()


def _render_exact_input() -> None:
    st.caption(
        "Keress rá egy szóra/kifejezésre a RÚF szövegében, vagy adj meg "
        "egy Strong-számot (pl. H3467, G2316) / héber-görög szót az "
        "eredeti nyelvi előfordulásokhoz."
    )

    live_query = str(st.session_state.get(QUERY_WIDGET_KEY) or "")
    is_original_mode = olc.is_original_language_query(live_query)

    if is_original_mode:
        col_query, col_btn = st.columns([5, 1])
    else:
        col_query, col_filter, col_btn = st.columns([3, 2, 1])
    with col_query:
        st.text_input(
            "Keresett szó, kifejezés vagy Strong-szám",
            key=QUERY_WIDGET_KEY,
            placeholder=(
                "Írj be egy magyar szót, görög/héber kifejezést vagy "
                "Strong-számot (pl. »kegyelem«, »ἀγάπη«, »sha'ah«, vagy »G26«)"
            ),
            label_visibility="collapsed",
        )
    if not is_original_mode:
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

    if is_original_mode:
        st.caption("Eredeti nyelvi mód — a testamentum-szűrő nem releváns.")

    if search_clicked:
        query = (st.session_state.get(QUERY_WIDGET_KEY) or "").strip()
        st.session_state[_COMMITTED_QUERY_KEY] = query
        st.session_state[_COMMITTED_MODE_KEY] = (
            "original" if olc.is_original_language_query(query) else "literal"
        )
        st.session_state[_COMMITTED_TESTAMENT_KEY] = st.session_state.get(
            TESTAMENT_WIDGET_KEY, "Egész Biblia"
        )
        st.session_state[_OFFSET_KEY] = 0


def _render_concept_input() -> None:
    st.caption(
        "Tegyél fel egy összetett, teológiai/fogalmi kérdést — a rendszer "
        "nemcsak szó szerinti egyezéseket keres, hanem valódi fogalmi "
        "kapcsolódásokat és narratív példákat is."
    )
    col_query, col_btn = st.columns([5, 1])
    with col_query:
        st.text_input(
            "Kérdés/fogalom",
            key=CONCEPT_QUERY_WIDGET_KEY,
            placeholder=(
                "Pl.: hol beszél a Biblia arról, hogy a megbocsátás nem "
                "mindig automatikus, hanem feltételekhez kötött?"
            ),
            label_visibility="collapsed",
        )
    with col_btn:
        search_clicked = st.button(
            "Keresés",
            key="concordance_concept_search_btn",
            type="primary",
            use_container_width=True,
        )

    if search_clicked:
        query = (st.session_state.get(CONCEPT_QUERY_WIDGET_KEY) or "").strip()
        st.session_state[_COMMITTED_QUERY_KEY] = query
        st.session_state[_COMMITTED_MODE_KEY] = "concept"
        st.session_state[_OFFSET_KEY] = 0


def _render_results() -> None:
    committed_query = str(st.session_state.get(_COMMITTED_QUERY_KEY) or "").strip()
    if not committed_query:
        st.caption(
            "Még nincs keresés. Írj be egy szót, kifejezést vagy Strong-számot, "
            "és kattints a Keresésre."
        )
        return

    mode = st.session_state.get(_COMMITTED_MODE_KEY, "literal")
    if mode == "concept":
        _render_concept_results(committed_query)
    elif mode == "original":
        _render_original_results(committed_query)
    else:
        _render_literal_results(committed_query)


def _render_literal_results(committed_query: str) -> None:
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

    _render_pagination(offset, total)


def _render_original_results(committed_query: str) -> None:
    offset = max(0, int(st.session_state.get(_OFFSET_KEY, 0)))
    # Kontextus nélkül olcsó a teljes listát lekérni (csak token-lekérdezés);
    # a RÚF magyar kontextust csak a ténylegesen látható oldalhoz kérjük le
    # utólag, hogy nagy találatszámnál (gyakori Strong-szám) ne fussunk le
    # feleslegesen sok helyi DB-lookupot.
    all_hits = olc.search_original(committed_query, with_hungarian_context=False)
    total = len(all_hits)
    if total == 0:
        st.info(f"Nincs találat erre: „{committed_query}”.")
        return

    hits = [
        olc.attach_hungarian_context(hit)
        for hit in all_hits[offset : offset + PAGE_SIZE]
    ]
    if not hits:
        st.session_state[_OFFSET_KEY] = 0
        st.rerun()
        return

    language_label = hits[0].language.upper()
    page_start = offset + 1
    page_end = offset + len(hits)
    st.caption(
        f"{total} {language_label} találat erre: „{committed_query}” "
        f"({page_start}–{page_end} megjelenítve)"
    )
    if total > _MANY_RESULTS_THRESHOLD:
        st.caption("Sok találat — nagyon gyakori szó/Strong-szám lehet.")

    for position, hit in enumerate(hits):
        reference = f"{hit.book_abbr} {hit.chapter},{hit.verse}"
        col_text, col_jump = st.columns([5, 1])
        with col_text:
            context = f" — {hit.hungarian_context}" if hit.hungarian_context else ""
            st.markdown(
                f"`{reference}` **{hit.surface}** _{hit.lemma}_ "
                f"({hit.strong_id}){context}"
            )
        with col_jump:
            # `position` (nem csak könyv/fejezet/vers) is a kulcs része,
            # mert ugyanaz a szó/Strong-szám jogosan előfordulhat kétszer
            # egy versben — ilyenkor a hivatkozás önmagában nem egyedi.
            if st.button(
                "Ugrás",
                key=f"concordance_jump_orig_{offset}_{position}",
            ):
                request_select_suggestion(reference)

    _render_pagination(offset, total)


def _render_concept_results(committed_query: str) -> None:
    with st.spinner("Fogalmi keresés — a Gemini konkrét igehelyeket keres…"):
        result = concept.search_concept(committed_query)

    if result.error:
        st.warning(result.error)
        return

    if not result.references and not result.keyword_hits and not result.original_language_hits:
        st.info(
            f"Nem sikerült releváns, ellenőrizhető igehelyet találni erre: "
            f"„{committed_query}”."
        )
        return

    if result.references:
        st.caption(f"{len(result.references)} igehely erre: „{committed_query}”")
        for position, ref in enumerate(result.references):
            reference = f"{ref.book_abbr} {ref.chapter}"
            if ref.verse_start:
                reference += f",{ref.verse_start}"
                if ref.verse_end and ref.verse_end != ref.verse_start:
                    reference += f"-{ref.verse_end}"
            col_text, col_jump = st.columns([5, 1])
            with col_text:
                st.markdown(f"`{reference}` — {ref.context_text}")
                st.caption(f"_{ref.relation_label}_ — {ref.reasoning}")
            with col_jump:
                if st.button(
                    "Ugrás",
                    key=f"concordance_jump_concept_{position}",
                ):
                    request_select_suggestion(reference)
    else:
        st.info("A Gemini nem javasolt ellenőrizhető igehelyet erre a kérdésre.")

    extra_hits = len(result.keyword_hits) + len(result.original_language_hits)
    if extra_hits:
        with st.expander(f"További kapcsolódó találatok ({extra_hits})"):
            for position, hit in enumerate(result.keyword_hits):
                reference = f"{hit.book_abbr} {hit.chapter},{hit.verse}"
                col_text, col_jump = st.columns([5, 1])
                with col_text:
                    st.markdown(f"`{reference}` — {hit.snippet}")
                with col_jump:
                    if st.button(
                        "Ugrás",
                        key=f"concordance_jump_concept_kw_{position}",
                    ):
                        request_select_suggestion(reference)
            for position, hit in enumerate(result.original_language_hits):
                reference = f"{hit.book_abbr} {hit.chapter},{hit.verse}"
                col_text, col_jump = st.columns([5, 1])
                with col_text:
                    context = f" — {hit.hungarian_context}" if hit.hungarian_context else ""
                    st.markdown(
                        f"`{reference}` **{hit.surface}** _{hit.lemma}_ "
                        f"({hit.strong_id}){context}"
                    )
                with col_jump:
                    if st.button(
                        "Ugrás",
                        key=f"concordance_jump_concept_ol_{position}",
                    ):
                        request_select_suggestion(reference)


def _render_pagination(offset: int, total: int) -> None:
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
    "request_original_language_search",
    "TESTAMENT_BOOK_CODES",
    "PAGE_SIZE",
]
