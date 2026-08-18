"""Igehirdetési műhely — UI- és állapotszinkronizációs regressziós tesztek.

A kézi próba során jelentkezett négy tünet (lebegő/overlay panel nem tűnik
el szabályosan; ugyanaz a szakaszfejléc néha kétszer jelenik meg;
jóváhagyás után nem frissül következetesen minden állapot; a progressz és
a ténylegesen jóváhagyott tartalom időnként nem egyezik) közös gyökéroka:
a "Jóváhagyom és átadom" / "Mentés vázlatként" gombok korábban NEM hívtak
`st.rerun()`-t a mentés után, miközben a navigáció/progresszsáv a szakasz
tartalma ELŐTT renderel a shell-ben (`render_sermon_workshop_shell`) —
így egyetlen futtatáson belül keveredett a jóváhagyás előtti (nav) és
utáni (szakasz-UI) állapot, ami a Streamlit-oldali portál-elemek
(st.popover) számára inkonzisztens widget-fát eredményezett.

A javítás: egységes `sermon_workshop_ui._toast_and_rerun()` minden
mentés/jóváhagyás sikeres ágán — ATOMI minta (tartalom mentése → státusz
állítása → toast → azonnali, kontrollált rerun).
"""

from __future__ import annotations

import inspect

import pytest
import streamlit as st

from sermon_outline_engine import (
    _gated_fallback_bundle,
    extract_outline_background_material,
)
from sermon_workshop_data import (
    ensure_sermon_workshop_state,
    normalize_sermon_workshop,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import collect_outline_context_bundle
import sermon_workshop_ui as sw_ui
from workshop_nav_ui import sermon_phase_statuses


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    return state


# ---------------------------------------------------------------------------
# 1. Egy szakasz egyetlen renderelése egy futtatáson belül
# ---------------------------------------------------------------------------


def test_old_section_render_functions_no_longer_dispatched_after_reset_2b():
    """RESET 2B (2026-08-18): megfordított elvárás — a korábbi
    `test_each_section_render_function_dispatched_exactly_once` azt
    védte, hogy minden régi öt-fázisos section-renderer pontosan egyszer
    hívódjon a shellből. Az egyszerű, lapos felület ezt a dispatchet
    teljesen leválasztotta — a régi függvények megmaradtak legacy
    kódként (nem törölve), de innen már NEM hívódnak."""
    src = inspect.getsource(sw_ui.render_sermon_workshop_shell)
    for fn_name in (
        "render_text_core_and_focus_section",
        "render_entry_point_section",
        "render_sermon_path_section",
        "render_gospel_arc_section",
        "render_closing_section",
        "render_engagement_section",
        "render_outline_section",
    ):
        call = f"{fn_name}(generate_fn=generate_fn)"
        assert call not in src, f"{fn_name} még mindig aktívan hívódik a shellből"
        assert callable(getattr(sw_ui, fn_name)), f"{fn_name} ne törlődjön, csak inaktiválódjon"


# ---------------------------------------------------------------------------
# 2. Overlay bezárása szakaszváltáskor / jóváhagyáskor — a mentés/jóváhagyás
# minden érintett ága a `_toast_and_rerun` (toast + azonnali rerun) atomi
# mintát hívja, nem puszta `st.success`-t.
# ---------------------------------------------------------------------------


def test_toast_and_rerun_helper_calls_toast_then_rerun(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(st, "toast", lambda msg, **k: calls.append(f"toast:{msg}"))
    monkeypatch.setattr(st, "rerun", lambda: calls.append("rerun"))
    sw_ui._toast_and_rerun("teszt üzenet")
    assert calls == ["toast:teszt üzenet", "rerun"]


@pytest.mark.parametrize(
    "fn",
    [
        sw_ui.render_sermon_main_idea_section,
        sw_ui.render_entry_point_section,
        sw_ui.render_sermon_path_section,
        sw_ui.render_gospel_arc_section,
        sw_ui.render_closing_section,
        sw_ui._render_lection_save_approve,
        sw_ui.render_enrichment_section,
    ],
)
def test_save_and_approve_branches_use_atomic_toast_and_rerun(fn):
    src = inspect.getsource(fn)
    # Legalább két hívás (Mentés vázlatként + Jóváhagyom és átadom sikeres ága).
    assert src.count("_toast_and_rerun(") >= 2, (
        f"{fn.__name__}: a mentés/jóváhagyás sikeres ága nem az atomi "
        "toast+rerun mintát használja"
    )


def test_prayer_save_and_approve_helpers_use_atomic_toast_and_rerun():
    draft_src = inspect.getsource(sw_ui._save_prayer_as_draft)
    approve_src = inspect.getsource(sw_ui._approve_prayer_and_handoff)
    assert "_toast_and_rerun(" in draft_src
    assert "_toast_and_rerun(" in approve_src


def test_engagement_item_save_and_approve_use_atomic_toast_and_rerun():
    src = inspect.getsource(sw_ui._render_engagement_element_editor)
    assert src.count("_toast_and_rerun(") >= 2


def test_nav_step_switch_triggers_rerun_on_change():
    """Szakaszváltáskor (más lépésre kattintva) is kontrollált rerun fut —
    ez már korábban is így működött, itt csak regresszióvédelemként."""
    src = inspect.getsource(__import__("workshop_nav_ui").render_step_selector)
    assert "st.rerun()" in src


# ---------------------------------------------------------------------------
# 3. draft → approved állapotátmenet
# ---------------------------------------------------------------------------


def test_entry_point_draft_to_approved_transition(session):
    ensure_sermon_workshop_state(session)
    update_sermon_workshop_section(
        session, "entry_point", {"today_connection": "tc", "type": "question", "text": "belépés"}
    )
    update_sermon_workshop_section(session, "entry_point_status", "draft")
    assert session["sermon_workshop"]["entry_point_status"] == "draft"

    update_sermon_workshop_section(session, "entry_point_status", "approved")
    sw = session["sermon_workshop"]
    assert sw["entry_point_status"] == "approved"
    assert sw["entry_point_approved_context_hash"]


# ---------------------------------------------------------------------------
# 4. Jóváhagyott adat megmaradása rerun után (a perzisztens dict-en
# szimulálva: a "rerun" csak azt jelenti, hogy a script újra beolvassa
# ugyanazt a `sermon_workshop` state-et — ez NEM veszíthet adatot).
# ---------------------------------------------------------------------------


def test_approved_data_survives_simulated_rerun(session):
    ensure_sermon_workshop_state(session)
    update_sermon_workshop_section(
        session,
        "sermon_path",
        {
            "starting_point": "Alaphelyzet szövege",
            "first_shift": "Első fordulópont szövege",
            "deepening": "Mélyítés szövege",
            "reinterpretation": "Átértelmezés szövege",
        },
    )
    update_sermon_workshop_section(session, "sermon_path_status", "approved")

    # "Rerun" szimuláció: a következő futtatás ugyanabból a perzisztens
    # dict-ből normalizál újra — semmi nem veszhet el.
    reloaded = normalize_sermon_workshop(session["sermon_workshop"])
    assert reloaded["sermon_path_status"] == "approved"
    assert reloaded["sermon_path"]["starting_point"] == "Alaphelyzet szövege"
    assert reloaded["sermon_path"]["first_shift"] == "Első fordulópont szövege"
    assert reloaded["sermon_path"]["deepening"] == "Mélyítés szövege"
    assert reloaded["sermon_path"]["reinterpretation"] == "Átértelmezés szövege"


# ---------------------------------------------------------------------------
# 5. Progressz és a ténylegesen jóváhagyott állapot egyezése
# ---------------------------------------------------------------------------


def test_progress_status_matches_actual_approved_state(session):
    ensure_sermon_workshop_state(session)
    state = {"sermon_workshop": session["sermon_workshop"]}

    before = sermon_phase_statuses(state)
    assert before["Homiletikai belépési pont"] == "ai_ready"

    update_sermon_workshop_section(
        session, "entry_point", {"today_connection": "tc", "type": "question", "text": "q"}
    )
    update_sermon_workshop_section(session, "entry_point_status", "approved")
    state = {"sermon_workshop": session["sermon_workshop"]}
    after_entry = sermon_phase_statuses(state)
    assert after_entry["Homiletikai belépési pont"] == "approved"
    # A többi fázis nem "szennyeződött" a jóváhagyástól.
    assert after_entry["A prédikáció íve"] == "ai_ready"

    update_sermon_workshop_section(
        session, "sermon_path", {"starting_point": "sp", "first_shift": "", "deepening": ""}
    )
    update_sermon_workshop_section(session, "sermon_path_status", "draft")
    state = {"sermon_workshop": session["sermon_workshop"]}
    after_path_draft = sermon_phase_statuses(state)
    assert after_path_draft["A prédikáció íve"] == "own_emphasis"

    update_sermon_workshop_section(session, "sermon_path_status", "approved")
    state = {"sermon_workshop": session["sermon_workshop"]}
    after_path_approved = sermon_phase_statuses(state)
    assert after_path_approved["A prédikáció íve"] == "approved"


# ---------------------------------------------------------------------------
# 6. Mind a hét jóváhagyott modellmező eljut a normál ÉS a fallback
# vázlatmotorhoz is — semmi nem veszik el.
# ---------------------------------------------------------------------------


def test_all_seven_approved_model_elements_reach_normal_and_fallback_engine():
    state = {
        "last_igehely": "Jn 3,16",
        "sermon_workshop": {
            "entry_point": {
                "today_connection": "BELÉPÉS-kapcsolódás",
                "type": "question",
                "text": "BELÉPÉS-szöveg",
            },
            "entry_point_status": "approved",
            "sermon_path": {
                "starting_point": "ALAPHELYZET-szöveg",
                "first_shift": "ELSŐ-FORDULÓPONT-szöveg",
                "deepening": "MÉLYÍTÉS-szöveg",
                "reinterpretation": "ÁTÉRTELMEZÉS-szöveg",
            },
            "sermon_path_status": "approved",
            "christ_centered_arc": {
                "divine_gracious_action": "MÁSODIK-FORDULÓPONT-Isten-cselekvése",
                "christ_connection": "MÁSODIK-FORDULÓPONT-Krisztus-kapcsolat",
                "grace_enabled_response": "MÁSODIK-FORDULÓPONT-válasz",
            },
            "christ_centered_arc_status": "approved",
            "closing": {
                "final_discovery": "MEGÉRKEZÉS-felismerés",
            },
            "closing_status": "approved",
        },
    }

    bundle = collect_outline_context_bundle(state)

    # Normál (AI-prompt) útvonal.
    background = extract_outline_background_material(bundle)
    assert background["entry_point"]["text"] == "BELÉPÉS-szöveg"
    assert background["sermon_path"]["starting_point"] == "ALAPHELYZET-szöveg"
    assert background["sermon_path"]["first_shift"] == "ELSŐ-FORDULÓPONT-szöveg"
    assert background["sermon_path"]["deepening"] == "MÉLYÍTÉS-szöveg"
    assert background["sermon_path"]["reinterpretation"] == "ÁTÉRTELMEZÉS-szöveg"
    assert background["christ_centered_arc"]["christ_connection"] == "MÁSODIK-FORDULÓPONT-Krisztus-kapcsolat"
    assert background["closing"]["final_discovery"] == "MEGÉRKEZÉS-felismerés"

    # Fallback (heurisztikus / AI-hívás nélküli) útvonal — ugyanaz a gate.
    gated = _gated_fallback_bundle(bundle)
    assert gated["entry_point"]["text"] == "BELÉPÉS-szöveg"
    assert gated["sermon_path"]["starting_point"] == "ALAPHELYZET-szöveg"
    assert gated["sermon_path"]["first_shift"] == "ELSŐ-FORDULÓPONT-szöveg"
    assert gated["sermon_path"]["deepening"] == "MÉLYÍTÉS-szöveg"
    assert gated["sermon_path"]["reinterpretation"] == "ÁTÉRTELMEZÉS-szöveg"
    assert gated["christ_centered_arc"]["christ_connection"] == "MÁSODIK-FORDULÓPONT-Krisztus-kapcsolat"
    assert gated["closing"]["final_discovery"] == "MEGÉRKEZÉS-felismerés"


# ---------------------------------------------------------------------------
# 7. Régi projekt betöltése adatvesztés nélkül
# ---------------------------------------------------------------------------


def test_old_project_full_legacy_state_normalizes_without_data_loss():
    legacy = {
        "sermon_main_idea": "Régi fő gondolat",
        "sermon_main_idea_status": "approved",
        "human_condition": {
            "condition": "Régi emberi helyzet",
            "false_response": "Régi téves válasz",
            "human_need": "Régi szükség",
            "divine_action": "Régi isteni cselekvés",
            "grace_response": "Régi kegyelmi válasz",
        },
        "human_condition_status": "approved",
        "listener_tension": {
            "listener_question": "Régi hallgatói kérdés",
            "listener_resistance": "Régi ellenállás",
            "sermon_tension": "Régi feszültség",
            "promised_resolution": "Régi feloldás",
        },
        "listener_tension_status": "approved",
        "sermon_path": {
            "type": "narrative",
            "reason": "Régi indoklás",
            "starting_point": "Régi kiindulópont",
            "destination": "Régi megérkezési pont",
        },
        "sermon_path_status": "approved",
        "sermon_movements": [
            {"id": "m1", "role": "tension", "title": "Régi mozgás", "core_content": "Régi mozgástartalom"},
        ],
        "illustrations": [{"id": "i1", "idea": "Régi illusztráció"}],
        "applications": [{"id": "a1", "application": "Régi alkalmazás"}],
        "enrichment_status": "approved",
    }
    normalized = normalize_sermon_workshop(legacy)

    # Semmi nem veszett el a régi mezőkből.
    assert normalized["sermon_main_idea"] == "Régi fő gondolat"
    assert normalized["human_condition"]["condition"] == "Régi emberi helyzet"
    assert normalized["human_condition_status"] == "approved"
    assert normalized["listener_tension"]["sermon_tension"] == "Régi feszültség"
    assert normalized["sermon_path"]["type"] == "narrative"
    assert normalized["sermon_path"]["starting_point"] == "Régi kiindulópont"
    assert normalized["sermon_path"]["destination"] == "Régi megérkezési pont"
    assert len(normalized["sermon_movements"]) == 1
    assert normalized["sermon_movements"][0]["core_content"] == "Régi mozgástartalom"
    assert len(normalized["illustrations"]) == 1
    assert len(normalized["applications"]) == 1
    assert normalized["enrichment_status"] == "approved"

    # Az új mezők biztonságosan, alapértelmezett (üres/draft) állapotban
    # jelennek meg — a migráció nem dob hibát, és a "Belépés" a legacy
    # emberi-helyzet tartalomból előtöltődik.
    assert normalized["sermon_path"]["reinterpretation"] == ""
    assert normalized["entry_point_status"] == "draft"
    assert normalized["entry_point"]["today_connection"] == "Régi emberi helyzet"
    assert normalized["engagement_elements"] == []
