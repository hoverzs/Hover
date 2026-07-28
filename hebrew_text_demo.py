from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from bible_engine.hebrew_lexicon_repository import HebrewLexiconRepository
from bible_engine.hebrew_morphology import decode_hebrew_morphology, load_tehmc_expansions
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH, DEFAULT_TBESH_DATABASE_PATH
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from components.hebrew_token_selector import hebrew_token_selector


TEHMC_SOURCE = Path(os.environ.get("TEMP", "")) / "TEHMC.txt"
PASSAGES = {
    "Ruth 1,1-5": ("Rut", 1, 1, 5),
    "Ruth 4,13-17": ("Rut", 4, 13, 17),
    "Zsolt 23,1-4": ("Psa", 23, 1, 4),
    "1Moz 1,1-5": ("Gen", 1, 1, 5),
    "Ezs 53,1-5": ("Isa", 53, 1, 5),
    "Daniel arami minta": ("Dan", 2, 4, 6),
    "Ketiv-qere minta": ("Rut", 3, 14, 14),
}


def render_hebrew_demo(database_path: Path = DEFAULT_TAHOT_DATABASE_PATH) -> None:
    st.title("Heber Oszovetseg prototipus")
    st.caption("Fejlesztoi TAHOT/TBESH prototipus. Forras: STEP Bible, CC BY 4.0.")

    token_repository = HebrewTokenRepository(database_path)
    diagnostics = token_repository.diagnostics()
    if not diagnostics.exists:
        st.warning(
            "A heber prototipus adatbazis meg nincs elkeszitve. "
            "Futtasd: .venv\\Scripts\\python.exe scripts\\build_hebrew_prototype_db.py"
        )
        st.code(str(database_path))
        return
    if diagnostics.integrity_check != "ok" or not diagnostics.required_tables_present:
        st.error("A heber adatbazis letezik, de nem ervenyes vagy nem teljes.")
        st.json(diagnostics.__dict__)
        return

    label = st.selectbox("Szakasz", tuple(PASSAGES))
    book, chapter, start, end = PASSAGES[label]
    result = token_repository.passage(book, chapter, start, end)
    if result.status != "ok":
        st.warning(f"A szakasz nem talalhato: {result.status}")
        return
    tokens = list(result.tokens)
    if not tokens:
        return

    current_key = st.session_state.get("hebrew_demo_selected_key") or tokens[0].stable_key
    selected = hebrew_token_selector(
        tokens,
        current_key,
        key=f"hebrew-selector-{book}-{chapter}-{start}-{end}",
    )
    selected_key = selected or current_key
    st.session_state["hebrew_demo_selected_key"] = selected_key
    selected_token = next((token for token in tokens if token.stable_key == selected_key), tokens[0])

    with st.expander("Alternativ szovalasztas", expanded=False):
        st.selectbox(
            "Token",
            [token.stable_key for token in tokens],
            index=[token.stable_key for token in tokens].index(selected_token.stable_key),
            key="hebrew_demo_selected_key",
        )

    lexicon = HebrewLexiconRepository(DEFAULT_TBESH_DATABASE_PATH)
    expansions = load_tehmc_expansions(TEHMC_SOURCE) if TEHMC_SOURCE.exists() else {}
    morphology = decode_hebrew_morphology(selected_token.morphology_code, expansions)
    lookup = lexicon.lookup_token(selected_token)

    st.subheader("Kattintott szo")
    left, right = st.columns([1, 2])
    with left:
        st.markdown(f"**Felszini alak:** {selected_token.surface}")
        st.markdown(f"**Kantillacio nelkul:** {selected_token.surface_without_accents}")
        st.markdown(f"**Lemma:** {selected_token.lemma or 'nincs adat'}")
        st.markdown(f"**Strong/STEP:** {', '.join(selected_token.strong_ids) or 'nincs adat'}")
        st.markdown(f"**Nyelv:** {'arami' if selected_token.language == 'aramaic' else 'heber'}")
    with right:
        st.markdown(f"**Morfologiai kod:** `{selected_token.morphology_code or 'nincs adat'}`")
        st.json(morphology.__dict__)

    st.markdown("**Prefix/core/suffix bontas**")
    rows = []
    for component in selected_token.prefix_components:
        rows.append({"szerep": "prefix", **component.__dict__})
    if selected_token.core_component:
        rows.append({"szerep": "core", **selected_token.core_component.__dict__})
    for component in selected_token.suffix_components:
        rows.append({"szerep": "suffix", **component.__dict__})
    st.dataframe(rows, hide_index=True)

    if selected_token.ketiv or selected_token.qere:
        st.info(f"Ketiv: {selected_token.ketiv or 'nincs'}; qere: {selected_token.qere or 'nincs'}")

    st.markdown("**TBESH lexikai fallback**")
    if lookup.core.entry:
        entry = lookup.core.entry
        source_note = (
            f"{lookup.core.source_strong_id} -> {lookup.core.alias_target}"
            if lookup.core.via_alias
            else lookup.core.matched_strong_id
        )
        st.markdown(f"`{source_note}` · {entry.hebrew} · {entry.transliteration}")
        st.markdown(f"**Gloss:** {entry.gloss}")
        st.markdown(entry.meaning or "Nincs hosszabb TBESH megjegyzes.")
    else:
        st.warning(f"Nincs kozvetlen TBESH talalat: {lookup.core.status}")

    st.caption("Forras es licenc: STEP Bible / STEPBible-Data, CC BY 4.0, www.STEPBible.org.")


render_hebrew_demo()
