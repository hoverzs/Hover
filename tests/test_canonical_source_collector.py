"""Korrekciós fázis 3.1 — automatikus/kanonikus forrás-hozzáférés.

A Textusműhely háttérforrásai (exegézis, eredeti szöveg, kortörténet,
teológia, aktualizálás, textusösszegzés, a textus fő gondolata) mostantól
approval nélkül is automatikusan elérhetők az Igehirdetési műhely és a
vázlatmotor számára — csak a tartalom megléte és az AKTUÁLIS igehelyhez
tartozó frissesség számít. A hét homiletikai modellmező (fókuszmondat,
belépési pont, prédikáció íve, evangéliumi fordulat, megérkezés stb.)
jóváhagyási mechanizmusa VÁLTOZATLAN — ezt a fázis nem érinti.

Ld. TEXTUS_IGEHIRDETESI_MUHELY_ADATFOLYAM_AUDIT.md — ez a fájl az ott
javasolt tesztlista mind a 10 pontját lefedi.
"""

from __future__ import annotations

from sermon_outline_engine import (
    collect_canonical_source_material,
    compute_current_passage_context_hash,
    extract_outline_background_material,
    _gated_fallback_bundle,
)
from sermon_workshop_data import (
    ensure_sermon_workshop_state,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import collect_outline_context_bundle
from textus_workshop_data import (
    TEXT_WORKSHOP_KEY,
    ensure_text_workshop_state,
    update_text_main_idea,
    update_text_summary_fields,
)


def _state_with_passage(**extra) -> dict:
    state: dict = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta.",
        "bible_translation": "RÚF 2014",
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    ensure_text_workshop_state(state)
    return state


# ---------------------------------------------------------------------------
# 1-2. Elkészült exegézis / eredeti szöveg / kortörténet — külön jóváhagyás
# nélkül bekerül a forráscsomagba.
# ---------------------------------------------------------------------------


def test_unapproved_exegesis_original_text_history_reach_background_material():
    state = _state_with_passage(
        exegesis="Exegetikai megállapítás a szeretet igéjéről.",
        original_text="Az agapaó ige jelentése önfeláldozó szeretet.",
        history="Első századi zsidó-hellén kontextus.",
        exegesis_status="draft",
        original_text_status="draft",
        history_status="draft",
    )
    # Generáláskor bélyegzett ujjlenyomat (ld. app.py::render_section_tab) —
    # itt kézzel szimulálva, hogy a friss-ellenőrzés át tudjon menni.
    fresh_hash = compute_current_passage_context_hash(state)
    state["exegesis_approved_context_hash"] = fresh_hash
    state["original_text_approved_context_hash"] = fresh_hash
    state["history_approved_context_hash"] = fresh_hash

    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert background.get("exegesis") == "Exegetikai megállapítás a szeretet igéjéről."
    assert background.get("original_text") == "Az agapaó ige jelentése önfeláldozó szeretet."
    assert background.get("history") == "Első századi zsidó-hellén kontextus."


# ---------------------------------------------------------------------------
# 3. A felhasználó által szerkesztett tartalom elsőbbséget élvez.
# ---------------------------------------------------------------------------


def test_user_edited_content_is_what_reaches_background_not_stale_ai_leftover():
    """A tényleges session-tartalom (amit a felhasználó utoljára mentett/
    szerkesztett) jut el a háttéranyagba — nincs rejtett, felülíró
    AI-verzió; a bundle mindig a JELENLEGI session_state-et tükrözi."""
    state = _state_with_passage(
        exegesis="Első, AI által javasolt megfogalmazás.",
        exegesis_status="draft",
    )
    state["exegesis_approved_context_hash"] = compute_current_passage_context_hash(state)

    # A felhasználó felülírja saját szövegével (új generálás/szerkesztés) —
    # ugyanaz a minta, mint app.py::render_section_tab generáláskor.
    state["exegesis"] = "Felhasználó által átírt, végleges megfogalmazás."
    state["exegesis_approved_context_hash"] = compute_current_passage_context_hash(state)

    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert background.get("exegesis") == "Felhasználó által átírt, végleges megfogalmazás."


# ---------------------------------------------------------------------------
# 4. Üres anyag nem kerül be.
# ---------------------------------------------------------------------------


def test_empty_source_does_not_reach_background_material():
    state = _state_with_passage(exegesis="", theology="   ", history=None)
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "exegesis" not in background
    assert "theology" not in background
    assert "history" not in background


# ---------------------------------------------------------------------------
# 5. Másik textushoz tartozó stale anyag nem kerül be automatikusan.
# ---------------------------------------------------------------------------


def test_stale_source_from_different_passage_excluded():
    other_passage_state = {"passage_reference": "Róm 8,28", "passage_text": "Más textus."}
    stale_hash = compute_current_passage_context_hash(other_passage_state)
    state = _state_with_passage(
        exegesis="Ez a szöveg egy MÁSIK igehelyhez készült.",
        exegesis_status="draft",
        exegesis_approved_context_hash=stale_hash,
    )
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "exegesis" not in background

    gated = _gated_fallback_bundle(bundle)
    assert "exegesis" not in gated


def test_source_without_saved_hash_treated_as_fresh_backward_compat():
    """Régi projekt: nincs mentett ujjlenyomat (a mechanizmus bevezetése
    előtti mentés) — ez NEM tekinthető stale-nek, visszafelé-kompatibilitás."""
    state = _state_with_passage(exegesis="Régi projektből származó exegézis.")
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert background.get("exegesis") == "Régi projektből származó exegézis."


# ---------------------------------------------------------------------------
# 6. Régi projekt tartalma adatvesztés nélkül betöltődik.
# ---------------------------------------------------------------------------


def test_old_project_all_seven_sources_survive_and_reach_context():
    """Egy 3.1 előtti mentés (nincs *_approved_context_hash, csak *_status
    draft/approved keverve) minden mezője megmarad és eljut a
    háttéranyagig — semmi nem vész el a migráció során. (Textusösszegzés
    tartalma nélkül, hogy a meglévő exkluzivitás-szabály — összegzés
    tartalom esetén a nyers mezők helyébe lép — ne fedje el ezt a tesztet;
    azt a szabályt a test_sermon_workshop_phase_migration.py külön fedi.)"""
    state = _state_with_passage(
        exegesis="Régi exegézis.",
        theology="Régi teológia.",
        history="Régi kortörténet.",
        original_text="Régi eredeti nyelvi elemzés.",
        actualization="Régi aktualizálás.",
    )
    state[TEXT_WORKSHOP_KEY]["text_main_idea"] = "Régi textus fő gondolat."

    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert background.get("exegesis") == "Régi exegézis."
    assert background.get("theology") == "Régi teológia."
    assert background.get("history") == "Régi kortörténet."
    assert background.get("original_text") == "Régi eredeti nyelvi elemzés."
    assert background.get("actualization") == "Régi aktualizálás."
    assert background.get("text_main_idea") == "Régi textus fő gondolat."


# ---------------------------------------------------------------------------
# 7. A homiletikai AI és a vázlatmotor azonos forráscsomagot kap.
# ---------------------------------------------------------------------------


def test_ai_path_and_fallback_path_see_identical_canonical_sources():
    state = _state_with_passage(
        exegesis="Közös exegézis mindkét útvonalnak.",
        theology="Közös teológia mindkét útvonalnak.",
    )
    bundle = collect_outline_context_bundle(state)
    ai_background = extract_outline_background_material(bundle)
    fallback_bundle = _gated_fallback_bundle(bundle)

    for key in ("exegesis", "theology"):
        assert ai_background.get(key) == fallback_bundle.get(key)
        assert ai_background.get(key) is not None


def test_canonical_source_material_matches_gated_outputs():
    """A `collect_canonical_source_material` structured kimenete pontosan
    azt a forráskészletet jelzi "current_passage"-ként, ami ténylegesen
    átjut mindkét gate-elt útvonalon."""
    state = _state_with_passage(exegesis="Exegézis a struktúrateszthez.")
    bundle = collect_outline_context_bundle(state)
    canonical = collect_canonical_source_material(bundle)
    assert canonical["sources"]["exegesis"]["current_passage"] is True
    assert canonical["sources"]["exegesis"]["origin"] == "textusműhely"
    assert canonical["sources"]["exegesis"]["editable_by_user"] is True

    background = extract_outline_background_material(bundle)
    assert "exegesis" in background


# ---------------------------------------------------------------------------
# 8. Pusztán a bibliai szöveggel sem jelenik meg blokkoló háttéranyaghiba.
# ---------------------------------------------------------------------------


def test_bible_text_alone_produces_no_blocking_missing_background_state():
    from sermon_outline_engine import extract_outline_excluded_draft_blocks

    state = _state_with_passage()
    bundle = collect_outline_context_bundle(state)
    excluded = extract_outline_excluded_draft_blocks(bundle)
    # Nincs kitöltött (de nem jóváhagyott) homiletikai döntés, tehát nincs
    # "kimaradt, nem jóváhagyott" figyelmeztetés sem — a bibliai szöveg
    # önmagában elegendő induló állapot.
    assert excluded == []


# ---------------------------------------------------------------------------
# 9. Homiletikai döntések jóváhagyási mechanizmusa VÁLTOZATLAN.
# ---------------------------------------------------------------------------


def test_homiletical_decision_keys_still_require_approval():
    """A 7 modellmező (itt: sermon_path) NEM válik automatikusan elérhetővé
    — a jóváhagyás továbbra is feltétel, ahogy a 3.1 előtt is."""
    state = _state_with_passage()
    update_sermon_workshop_section(
        state, "sermon_path", {"starting_point": "Draft alaphelyzet, nincs jóváhagyva."}
    )
    update_sermon_workshop_section(state, "sermon_path_status", "draft")

    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "sermon_path" not in background

    update_sermon_workshop_section(state, "sermon_path_status", "approved")
    bundle2 = collect_outline_context_bundle(state)
    background2 = extract_outline_background_material(bundle2)
    assert "sermon_path" in background2


# ---------------------------------------------------------------------------
# 10. A Textusműhely jelenlegi felülete változatlan marad (nincs UI-hívás
# eltávolítva/átnevezve — csak forráskód-szintű ellenőrzés, hogy a
# render_section_tab approvable=True gombjai megmaradtak).
# ---------------------------------------------------------------------------


def test_textus_workshop_ui_unchanged_render_section_tab_signature():
    import inspect

    import app

    src = inspect.getsource(app.render_section_tab)
    # A gombpár és az approvable-ág megmaradt — csak a generáláskori
    # hash-bélyegzés adódott hozzá.
    assert '"Mentés vázlatként"' in src
    assert '"Jóváhagyom és átadom"' in src
    assert "approvable and has_result" in src


def test_update_text_main_idea_and_summary_still_support_manual_status_flow():
    """A textus fő gondolata / Textusösszegzés draft→approved mentési
    útvonala (UI-gombok mögötti függvények) nem változott meg
    funkcionálisan — csak a hash-bélyegzés vált gyakoribbá."""
    state = _state_with_passage()
    update_text_main_idea(state, "Kézzel írt textus fő gondolat.", "draft")
    tw = state[TEXT_WORKSHOP_KEY]
    assert tw["text_main_idea"] == "Kézzel írt textus fő gondolat."
    assert tw["text_main_idea_status"] == "draft"
    assert tw["text_main_idea_approved_context_hash"]

    update_text_summary_fields(
        state, {"base_tension": "Kézzel írt alapfeszültség."}, status="draft"
    )
    assert state[TEXT_WORKSHOP_KEY]["text_summary"]["base_tension"] == "Kézzel írt alapfeszültség."
    assert state[TEXT_WORKSHOP_KEY]["text_summary"]["approved_context_hash"]


# ---------------------------------------------------------------------------
# Explicit, kért végpróba: exegézis + eredeti szöveg + kortörténet, jóváhagyás
# nélkül, mindhárom eljut a vázlatmotor BEMENETÉIG (normál ÉS fallback).
# ---------------------------------------------------------------------------


def test_e2e_three_unapproved_sources_reach_outline_engine_input_both_paths():
    state = _state_with_passage(
        exegesis="E2E: exegetikai felismerés a szeretet fogalmáról.",
        original_text="E2E: az agapaó ige eredeti jelentése.",
        history="E2E: első századi kortörténeti háttér.",
        exegesis_status="draft",
        original_text_status="draft",
        history_status="draft",
    )
    # Generáláskori hash-bélyegzés szimulálása (app.py::render_section_tab mintája).
    for key in ("exegesis", "original_text", "history"):
        state[f"{key}_approved_context_hash"] = compute_current_passage_context_hash(state)

    bundle = collect_outline_context_bundle(state)

    # Normál (AI-prompt) útvonal bemenete.
    ai_input = extract_outline_background_material(bundle)
    assert ai_input.get("exegesis") == "E2E: exegetikai felismerés a szeretet fogalmáról."
    assert ai_input.get("original_text") == "E2E: az agapaó ige eredeti jelentése."
    assert ai_input.get("history") == "E2E: első századi kortörténeti háttér."

    # Fallback (heurisztikus) útvonal bemenete — ugyanaz a forráskészlet.
    fallback_input = _gated_fallback_bundle(bundle)
    assert fallback_input.get("exegesis") == "E2E: exegetikai felismerés a szeretet fogalmáról."
    assert fallback_input.get("original_text") == "E2E: az agapaó ige eredeti jelentése."
    assert fallback_input.get("history") == "E2E: első századi kortörténeti háttér."

    # Egyik forrás sem "jóváhagyva" — a bekerülés kizárólag a tartalom és a
    # frissesség alapján történt, nem az approval miatt.
    assert bundle.get("exegesis_status") == "draft"
    assert bundle.get("original_text_status") == "draft"
    assert bundle.get("history_status") == "draft"
