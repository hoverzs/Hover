"""Phase 3I / 3I.1: user-facing illustration retrieval UI.

Lives OUTSIDE `illustration_review_ui.py` -- that module is the
internal reviewer/QA tool (gated to the owner email or localhost);
THIS module is the normal, public "Illusztrációk" tab's SOLE content.

Phase 3I.1: the tab previously also ran a free-form LLM story-generation
block (SECTION_PROMPTS["illustrations"] in app.py -- "Klasszikus
tanmesék" / "Valós anekdoták és esetek" / "Mai, hétköznapi történet" /
"Bevezető illusztráció") that produced source-less, fabricated stories.
That block has been REMOVED from app.py entirely (the prompt no longer
exists, the tab no longer calls it) because it violated the Phase 3I
"NO GENERATED FAKE STORIES" principle. This module's retrieval action
is now the ONLY illustration content the "Illusztrációk" tab renders --
every story a user sees here is read verbatim from `illustration_units`
in the DB; the LLM only ranks/explains, never authors story content.

Its own access boundary is not about WHO the user is --
it is entirely about which retrieval MODE applies:

- non-loopback host (production/Cloud): `mode="production"` --
  `illustration_engine.retrieval.find_candidates` restricts to
  `published_illustration_units` only.
- strict loopback host (localhost/127.0.0.1/::1, reusing
  `illustration_review_ui.is_local_loopback_request` -- the SAME
  narrow check the reviewer panel uses, not a new heuristic):
  `mode="development"` -- unpublished but `qa_status='passed'` units
  become visible too, for internal QA testing. A discreet banner makes
  this explicit whenever it is active (see `_DEV_MODE_BANNER`).

Same dependency-injection pattern as `textus_workshop_ui.py`/
`sermon_workshop_ui.py`: `app.py` supplies `generate_fn=generate_text`;
this module never touches Gemini/HTTP itself.

NEVER shown to the end user: the ranking prompt, raw JSON, qa_status/
qa_issues internals, or any other reviewer-facing technical detail --
see `_render_result_card`.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

import streamlit as st

from illustration_engine.illustration_sqlite import DEFAULT_DATABASE_PATH, migrate_schema
from illustration_engine.retrieval import IllustrationRetrievalResult, retrieve_illustrations
from illustration_review_ui import is_local_loopback_request
from ui_components import action_row, render_info_panel, render_work_section, work_surface

_RESULTS_KEY = "ill_retrieval_results"
_MODE_KEY = "ill_retrieval_mode"
_SEARCHED_KEY = "ill_retrieval_searched"

_DEV_MODE_BANNER = "⚠️ Belső QA corpus — még nem publikált tételek."
_EMPTY_RESULT_MESSAGE = "A tudástárban most nem találtam megfelelő, ellenőrzött illusztrációt."


@st.cache_resource(show_spinner=False)
def _get_connection() -> sqlite3.Connection:
    """Deliberately a SEPARATE connection/cache from
    `illustration_review_ui._get_connection()` -- two independent UI
    surfaces (internal reviewer tool vs. public retrieval feature) with
    no reason to share private internals, even though both point at the
    same physical DB file (SQLite supports multiple connections to one
    file). `migrate_schema()` is idempotent/additive-only (Phase 3H) --
    self-healing here too, same reasoning as the reviewer panel."""
    connection = sqlite3.connect(str(DEFAULT_DATABASE_PATH), check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")
    migrate_schema(connection)
    return connection


def _current_mode() -> str:
    return "development" if is_local_loopback_request() else "production"


def _render_result_card(item: IllustrationRetrievalResult) -> None:
    with st.container(border=True):
        st.markdown(f"**{item.title_hu}**")
        st.write(item.summary_hu)
        with st.expander("Teljes történet elolvasása"):
            st.write(item.modern_hu_text)
            if item.moral_hu:
                st.caption(f"Tanulság: {item.moral_hu}")
        caption_parts = [f"Forrás: {item.source_attribution}"]
        if item.homiletic_functions:
            caption_parts.append(f"Homiletikai irány: {', '.join(item.homiletic_functions)}")
        st.caption(" · ".join(caption_parts))


def render_illustration_search_action(*, generate_fn: Callable[..., str] | None = None) -> None:
    """Renders the "Illusztrációk" tab's entire content.

    Phase 3I.1: this is no longer a supplementary action bolted onto a
    free-form generative block -- it IS the tab. Call this once, directly
    inside `with tabs[5]:` in `app.py`, with nothing else alongside it."""
    render_work_section(
        title="Illusztrációk",
        body=(
            "A meglévő textus alapján keres a Textus saját, ember és gép "
            "által ellenőrzött illusztráció-adatbázisában. A történet "
            "mindig az adatbázisból származik -- az AI csak rangsorol és "
            "magyarázza a kapcsolódást, sosem talál ki új történetet."
        ),
        context="Textusműhely",
    )

    mode = _current_mode()
    if mode == "development":
        st.info(_DEV_MODE_BANNER)

    passage = (st.session_state.get("last_igehely") or "").strip()

    with work_surface("illustration_retrieval"):
        with action_row("illustration_retrieval_search"):
            if st.button("Illusztrációk keresése", key="ill_retrieval_search_btn", type="primary"):
                if not passage:
                    st.warning("Add meg az igeszakaszt az „Igehely” fülön, mielőtt keresel.")
                elif generate_fn is None:
                    st.warning("Nincs elérhető AI-hívás ehhez a funkcióhoz.")
                else:
                    with st.spinner("Illusztrációk keresése…"):
                        connection = _get_connection()
                        passage_text = str(st.session_state.get("passage_text") or "")
                        occasion = str(st.session_state.get("occasion_label") or "").strip()

                        def _llm(prompt: str) -> str:
                            return generate_fn(
                                prompt,
                                enable_google_search=False,
                                tab_label="Illusztrációk",
                                use_cache=False,
                                include_brevity_directive=False,
                            )

                        results = retrieve_illustrations(
                            connection,
                            mode=mode,
                            passage_reference=passage,
                            passage_text=passage_text,
                            theme="",
                            occasion=occasion,
                            llm_generate=_llm,
                        )
                        st.session_state[_RESULTS_KEY] = results
                        st.session_state[_MODE_KEY] = mode
                        st.session_state[_SEARCHED_KEY] = True

        if st.session_state.get(_SEARCHED_KEY):
            results: list[IllustrationRetrievalResult] = st.session_state.get(_RESULTS_KEY) or []
            if not results:
                render_info_panel(
                    title="Nincs megfelelő találat",
                    body=_EMPTY_RESULT_MESSAGE,
                    tone="neutral",
                )
            else:
                for item in results:
                    _render_result_card(item)
        else:
            render_info_panel(
                title="Még nincs keresés",
                body="Kattints az „Illusztrációk keresése” gombra az igeszakaszhoz illő, ellenőrzött történetekért.",
                tone="neutral",
            )


__all__ = ["render_illustration_search_action"]
