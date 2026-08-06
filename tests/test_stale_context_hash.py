from __future__ import annotations

from sermon_outline_engine import (
    compute_current_passage_context_hash,
    compute_passage_context_hash,
    extract_outline_background_material,
    extract_stale_approved_blocks,
    generate_sermon_outline,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import collect_outline_context_bundle
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop


def _base_state() -> dict:
    return {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta…",
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
    }


def test_approved_context_hash_survives_ensure_sermon_workshop_state_rebuild():
    """A 4a) pont explicit kérése: ne csak feltételezzük, bizonyítsuk, hogy
    az _approved_context_hash mező túléli az ensure_sermon_workshop_state()
    (azaz normalize_sermon_workshop()) allowlist-alapú újraépítését."""
    state = _base_state()

    update_sermon_workshop_section(
        state, "human_condition", {"condition": "Az ember magára maradottsága."}
    )
    update_sermon_workshop_section(state, "human_condition_status", "approved")

    sw = state[SERMON_WORKSHOP_KEY]
    saved_hash = sw.get("human_condition_approved_context_hash")
    assert saved_hash, "A jóváhagyás nem mentette el a hash-t."

    # Szimuláljuk a következő Streamlit rerunt: a session_state[SERMON_WORKSHOP_KEY]
    # ugyanaz a dict marad, de minden render elején ez fut le.
    rebuilt = ensure_sermon_workshop_state(state)

    assert rebuilt.get("human_condition_approved_context_hash") == saved_hash, (
        "Az _approved_context_hash elveszett az ensure_sermon_workshop_state() "
        "(normalize_sermon_workshop) allowlist-újraépítésekor."
    )

    # Egy MÁSODIK, független rebuild (pl. egy újabb rerun) is meg kell hogy őrizze.
    state[SERMON_WORKSHOP_KEY] = dict(rebuilt)
    rebuilt_again = ensure_sermon_workshop_state(state)
    assert (
        rebuilt_again.get("human_condition_approved_context_hash") == saved_hash
    )


def test_old_approved_block_without_hash_is_not_falsely_stale():
    """A d) pont explicit kérése: egy RÉGI, hash nélküli "approved" blokk
    (a mechanizmus bevezetése előtti jóváhagyás) NE váljon hamisan STALE-lé."""
    state = _base_state()
    sw = state[SERMON_WORKSHOP_KEY]

    # Régi adat szimulálása: approved státusz, de SOSEM mentett hash.
    sw["human_condition"] = {"condition": "Régi, migráció előtti jóváhagyott tartalom."}
    sw["human_condition_status"] = "approved"
    assert "human_condition_approved_context_hash" not in sw or not sw.get(
        "human_condition_approved_context_hash"
    )

    bundle = collect_outline_context_bundle(state)
    assert bundle.get("human_condition_approved_context_hash") == ""

    stale = extract_stale_approved_blocks(bundle)
    assert stale == [], (
        "Egy hash nélküli, régi 'approved' blokkot hamisan STALE-nek jelölt."
    )

    background = extract_outline_background_material(bundle)
    assert "human_condition" in background, (
        "Egy hash nélküli, régi 'approved' blokk tartalmának be kellene "
        "kerülnie a háttéranyagba (visszafelé-kompatibilitás)."
    )


def test_fresh_approval_then_unchanged_passage_is_not_stale_then_passage_change_makes_it_stale():
    """3. pont: izolált, kód-szintű funkcionális teszt a teljes körre —
    friss jóváhagyás → hash mentése → igehely/szöveg változatlan → nem STALE;
    majd igehely/szöveg változik → a blokk STALE-lé válik → kimarad a
    vázlatból, megfelelő figyelmeztetéssel."""
    state = _base_state()

    update_sermon_workshop_section(
        state, "human_condition", {"condition": "Friss, jóváhagyott elemzés."}
    )
    update_sermon_workshop_section(state, "human_condition_status", "approved")

    # --- 1) Igehely/szöveg változatlan: nem STALE, bekerül a háttéranyagba ---
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("human_condition_status") == "approved"
    assert bundle.get("human_condition_approved_context_hash") == (
        compute_passage_context_hash(bundle)
    )
    assert extract_stale_approved_blocks(bundle) == []
    background = extract_outline_background_material(bundle)
    assert "human_condition" in background

    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert not any(
        "megváltozott" in w and "human_condition" not in w for w in result.warnings
    )
    assert not any("Emberi állapot / helyzet" in w for w in result.warnings), (
        result.warnings
    )

    # --- 2) A bibliai szöveg megváltozik (ugyanaz az igehely, más szövegváltozat) ---
    state["passage_text"] = (
        "16 Mert úgy szerette Isten a világot — MEGVÁLTOZOTT szövegváltozat."
    )

    bundle2 = collect_outline_context_bundle(state)
    current_hash = compute_passage_context_hash(bundle2)
    assert bundle2.get("human_condition_approved_context_hash") != current_hash

    stale = extract_stale_approved_blocks(bundle2)
    assert stale == ["Emberi állapot / helyzet"]

    background2 = extract_outline_background_material(bundle2)
    assert "human_condition" not in background2, (
        "A STALE blokknak ki kellene maradnia a háttéranyagból."
    )

    result2 = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    stale_warning = [
        w
        for w in result2.warnings
        if "megváltozott" in w and "Emberi állapot / helyzet" in w
    ]
    assert stale_warning, result2.warnings


def test_compute_current_passage_context_hash_matches_bundle_level_hash():
    """A kényelmi wrapper (session_state-ből számol) ugyanazt adja, mint a
    bundle-alapú compute_passage_context_hash — nincs eltérés a két útvonal közt."""
    state = _base_state()
    bundle = collect_outline_context_bundle(state)
    assert compute_current_passage_context_hash(state) == compute_passage_context_hash(
        bundle
    )
