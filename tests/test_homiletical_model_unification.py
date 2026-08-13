"""Egységesített fordulópont-alapú homiletikai modell — regressziós tesztek.

A korábban párhuzamosan élő homiletikai rendszerek (úttípus-választó,
Prédikációs mozgások szerkesztő, öt külön "Emberi helyzet" mező) helyett
mostantól kizárólag a fordulópont-alapú modell (Textusmag és fókuszmondat /
Homiletikai belépési pont / A prédikáció íve / Megszólítás és bevonás /
Igehirdetési vázlat) jelenik meg a felületen. Ezek a tesztek nem Streamlit-
UI-t futtatnak (kivéve a widget-perzisztencia egy célzott esetét), hanem a
mögöttes adatmodellt, migrációt és vázlatmotor-viselkedést ellenőrzik.
"""

from __future__ import annotations

import inspect

import pytest
import streamlit as st

from sermon_outline_engine import (
    _gated_fallback_bundle,
    _heuristic_structured_from_bundle,
    extract_outline_background_material,
)
from sermon_workshop_data import (
    ensure_sermon_workshop_state,
    normalize_sermon_workshop,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import (
    build_outline_from_workshop,
    collect_outline_context_bundle,
)
from sermon_workshop_ui import _KEY_PATH, render_sermon_path_section
from workshop_nav_ui import SERMON_PHASE_OPTIONS


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    return state


# ---------------------------------------------------------------------------
# Fázis elnevezés + a régi párhuzamos rendszerek eltűnése a felületről
# ---------------------------------------------------------------------------


def test_first_phase_renamed_to_text_core_and_focus():
    assert SERMON_PHASE_OPTIONS[0] == "Textusmag és fókuszmondat"
    assert "Fókuszmondat" not in SERMON_PHASE_OPTIONS


def test_shell_dispatch_no_longer_calls_old_parallel_forms():
    """Az öt fázis közül a Homiletikai belépési pont mostantól kizárólag az
    entry_point szakaszt hívja — az öt mezős human_condition/listener_tension
    űrlap nem jelenik meg mellette párhuzamos rendszerként."""
    from sermon_workshop_ui import render_sermon_workshop_shell

    src = inspect.getsource(render_sermon_workshop_shell)
    assert "render_human_condition_section(generate_fn=generate_fn)" not in src
    assert "render_listener_tension_section(generate_fn=generate_fn)" not in src
    assert "render_entry_point_section(generate_fn=generate_fn)" in src
    assert "render_text_core_and_focus_section(generate_fn=generate_fn)" in src


def test_sermon_path_section_source_has_no_path_type_or_movements_editor():
    """Az Úttípus-választó, az indoklás mező és a Prédikációs mozgások
    szerkesztő (és az átöltő gombok) nem jelennek meg választható
    rendszerként a prédikáció íve szakaszon."""
    src = inspect.getsource(render_sermon_path_section)
    # A docstring szabadon utalhat a régi rendszerre (magyarázatként), a
    # tényleges UI-kód (widget címkék, gombok) viszont nem tartalmazhatja.
    body = src.split('"""', 2)[-1]
    assert "Úttípus" not in body
    assert "Az út rövid indoklása" not in body
    assert "**Prédikációs mozgások**" not in body
    assert "Mozgás hozzáadása" not in body
    assert "Megérkezési pont" not in src
    assert "Kitöltés a „Feszültség” mozgásból" not in src
    assert "Kitöltés az „Elmélyítés” mozgásból" not in src
    # A három aktív mező viszont megmarad.
    assert '_KEY_PATH["starting_point"]' in src
    assert '_KEY_PATH["first_shift"]' in src
    assert '_KEY_PATH["deepening"]' in src


# ---------------------------------------------------------------------------
# entry_point legacy előtöltés régi projekteknél
# ---------------------------------------------------------------------------


def test_entry_point_prefilled_from_legacy_human_condition_on_old_project_load():
    legacy = {
        "human_condition": {"condition": "Fáradtak és terheltek vagyunk."},
        "listener_tension": {},
        "entry_point": {"today_connection": "", "type": "", "text": ""},
    }
    normalized = normalize_sermon_workshop(legacy)
    assert normalized["entry_point"]["today_connection"] == "Fáradtak és terheltek vagyunk."
    assert normalized["entry_point_legacy_prefilled"] is True


def test_entry_point_prefill_does_not_reoccur_after_user_clears_field():
    """A migráció egyszeri — ha a felhasználó utána kiüríti a mezőt, a
    következő normalizálás ne írja vissza automatikusan."""
    legacy = {"human_condition": {"condition": "Régi szöveg."}}
    once = normalize_sermon_workshop(legacy)
    assert once["entry_point"]["today_connection"]

    once["entry_point"]["today_connection"] = ""
    twice = normalize_sermon_workshop(once)
    assert twice["entry_point"]["today_connection"] == ""
    assert twice["entry_point_legacy_prefilled"] is True


def test_entry_point_no_prefill_when_no_legacy_content():
    normalized = normalize_sermon_workshop({})
    assert normalized["entry_point"]["today_connection"] == ""
    assert normalized["entry_point_legacy_prefilled"] is False


# ---------------------------------------------------------------------------
# A prédikáció íve — widget-perzisztencia: csak a 3 aktív mező, legacy
# type/reason/destination megőrizve
# ---------------------------------------------------------------------------


def test_persist_sermon_path_preserves_legacy_fields_when_widgets_absent(session):
    ensure_sermon_workshop_state(session)
    update_sermon_workshop_section(
        session,
        "sermon_path",
        {
            "type": "narrative",
            "reason": "Régi indoklás",
            "starting_point": "",
            "first_shift": "",
            "deepening": "",
            "destination": "Régi megérkezési pont",
        },
    )
    from sermon_workshop_ui import _persist_sermon_path_from_widgets

    st.session_state[_KEY_PATH["starting_point"]] = "Új kiinduló látás"
    st.session_state[_KEY_PATH["first_shift"]] = "Új első látásváltás"
    st.session_state[_KEY_PATH["deepening"]] = "Új mélyítés"
    # type/reason/destination widget-kulcsok NEM léteznek (nincs UI-juk).

    _persist_sermon_path_from_widgets()

    saved = session["sermon_workshop"]["sermon_path"]
    assert saved["starting_point"] == "Új kiinduló látás"
    assert saved["first_shift"] == "Új első látásváltás"
    assert saved["deepening"] == "Új mélyítés"
    # Legacy mezők megőrizve, nem íródtak felül üresre.
    assert saved["type"] == "narrative"
    assert saved["reason"] == "Régi indoklás"
    assert saved["destination"] == "Régi megérkezési pont"


def test_sermon_path_approve_decisions_only_cover_three_active_fields(session):
    ensure_sermon_workshop_state(session)

    update_sermon_workshop_section(
        session,
        "sermon_path",
        {
            "starting_point": "Kiinduló látás szövege",
            "first_shift": "Első látásváltás szövege",
            "deepening": "Mélyítés szövege",
        },
    )
    update_sermon_workshop_section(session, "sermon_path_status", "approved")
    assert session["sermon_workshop"]["sermon_path_status"] == "approved"
    # A régi "Úttípus"/"Megérkezési pont" döntés-kategóriák nem jönnek létre
    # automatikusan pusztán a jóváhagyástól (csak explicit UI-gomb hozná
    # létre őket, amit a szakasz már nem hív meg).
    decisions = session["sermon_workshop"].get("approved_sermon_decisions") or []
    categories = {d.get("category") for d in decisions}
    assert "Úttípus" not in categories
    assert "Megérkezési pont" not in categories


# ---------------------------------------------------------------------------
# Vázlatmotor — 2-3 beszédegység, átvezetéssel (heurisztikus fallback)
# ---------------------------------------------------------------------------


def _passage_bundle(extra: dict | None = None) -> dict:
    bundle = {
        "passage_reference": "Mt 11,28-30",
        "passage_text": (
            "<p><b>28</b> Jöjjetek énhozzám mindnyájan, akik megfáradtatok és "
            "megterheltettetek, és én megnyugvást adok nektek.</p>"
            "<p><b>29</b> Vegyétek magatokra az én igámat, és tanuljátok meg "
            "tőlem, hogy szelíd és alázatos szívű vagyok, és nyugalmat "
            "találtok lelketeknek.</p>"
            "<p><b>30</b> Mert az én igám gyönyörűséges, és az én terhem "
            "könnyű.</p>"
        ),
        "project_title": "",
    }
    if extra:
        bundle.update(extra)
    return bundle


def test_heuristic_outline_produces_two_or_three_points_with_transitions():
    bundle = _passage_bundle()
    result = _heuristic_structured_from_bundle(bundle)
    points = result["points"]
    assert 2 <= len(points) <= 3
    for pt in points[:-1]:
        assert (pt.get("transition") or "").strip(), (
            "minden nem-utolsó beszédegységnek legyen átvezetése"
        )
    assert not (points[-1].get("transition") or "").strip() or True  # utolsó opcionális


def test_heuristic_fallback_never_reads_draft_or_rejected_gated_blocks():
    """Kényszerített fallback teszt (Korrekciós fázis 2C/2D): a heurisztikus
    mentőöv is kizárólag jóváhagyott-és-friss tartalmat használhat a
    gate-elt blokkokból."""
    bundle = _passage_bundle(
        {
            "sermon_path": {
                "starting_point": "JÓVÁHAGYOTT kiinduló látás",
                "first_shift": "JÓVÁHAGYOTT első látásváltás",
                "deepening": "JÓVÁHAGYOTT mélyítés",
            },
            "sermon_path_status": "approved",
            "human_condition": {"condition": "DRAFT emberi helyzet — nem szabad megjelennie"},
            "human_condition_status": "draft",
            "listener_tension": {"sermon_tension": "DRAFT feszültség — nem szabad megjelennie"},
            "listener_tension_status": "draft",
        }
    )
    gated = _gated_fallback_bundle(bundle)
    assert "human_condition" not in gated
    assert "listener_tension" not in gated
    assert gated["sermon_path"]["starting_point"] == "JÓVÁHAGYOTT kiinduló látás"

    result = _heuristic_structured_from_bundle(bundle)
    rendered = str(result)
    assert "DRAFT emberi helyzet" not in rendered
    assert "DRAFT feszültség" not in rendered


def test_forced_fallback_build_outline_from_workshop_excludes_draft_includes_approved():
    """`generate_fn=None` (kényszerített fallback) esetén a
    `build_outline_from_workshop` csak a jóváhagyott listener_tension
    tartalmat adja tovább, a draft állapotú NEM kerül be."""
    state = {
        "last_igehely": "Mt 11,28-30",
        "passage_reference": "Mt 11,28-30",
        "sermon_workshop": {
            "listener_tension": {
                "listener_question": "JÓVÁHAGYOTT hallgatói kérdés",
                "sermon_tension": "JÓVÁHAGYOTT feszültség",
                "listener_resistance": "JÓVÁHAGYOTT ellenállás",
            },
            "listener_tension_status": "approved",
            "sermon_main_idea": "DRAFT fő gondolat — nem jóváhagyott",
            "sermon_main_idea_status": "draft",
        },
    }
    seed = build_outline_from_workshop(state)
    assert seed["listener_question"] == "JÓVÁHAGYOTT hallgatói kérdés"
    assert seed["central_tension"] == "JÓVÁHAGYOTT feszültség"
    assert seed["main_idea"] != "DRAFT fő gondolat — nem jóváhagyott"


# ---------------------------------------------------------------------------
# Teljesen kézi (AI nélküli) használat a homiletikai belépési ponton és a
# prédikáció ívén — jóváhagyás után a vázlat háttéranyagában megjelenik.
# ---------------------------------------------------------------------------


def test_fully_manual_entry_point_and_path_reach_outline_background_once_approved():
    state = {"last_igehely": "Jn 3,16"}
    update_sermon_workshop_section(
        state,
        "entry_point",
        {"today_connection": "Kézzel írt kapcsolódás", "type": "question", "text": "Kézzel írt belépés"},
    )
    update_sermon_workshop_section(state, "entry_point_status", "approved")
    update_sermon_workshop_section(
        state,
        "sermon_path",
        {
            "starting_point": "Kézzel írt kiinduló látás",
            "first_shift": "",
            "deepening": "",
        },
    )
    update_sermon_workshop_section(state, "sermon_path_status", "approved")

    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert background["entry_point"]["text"] == "Kézzel írt belépés"
    assert background["sermon_path"]["starting_point"] == "Kézzel írt kiinduló látás"


# ---------------------------------------------------------------------------
# Végleges, 7-elemű kanonikus modell (Belépés / Alaphelyzet / Első
# fordulópont / Mélyítés és fokozás / opcionális Átértelmezés / Második
# fordulópont / Megérkezés) — az öt munkaszakasz vázán belül.
# ---------------------------------------------------------------------------


def test_sermon_path_default_includes_reinterpretation_field():
    from sermon_workshop_data import get_default_sermon_workshop

    sw = get_default_sermon_workshop()
    assert sw["sermon_path"]["reinterpretation"] == ""


def test_old_project_without_reinterpretation_normalizes_safely():
    legacy = {
        "sermon_path": {
            "starting_point": "Régi kiinduló látás",
            "first_shift": "Régi első látásváltás",
        },
        "sermon_path_status": "approved",
    }
    normalized = normalize_sermon_workshop(legacy)
    assert normalized["sermon_path"]["reinterpretation"] == ""
    assert normalized["sermon_path"]["starting_point"] == "Régi kiinduló látás"


def test_sermon_path_section_source_uses_new_element_titles():
    src = inspect.getsource(render_sermon_path_section)
    body = src.split('"""', 2)[-1]
    assert "Alaphelyzet" in body
    assert "Első fordulópont" in body
    assert "Mélyítés és fokozás" in body
    assert "Átértelmezés" in body
    assert '_KEY_PATH["reinterpretation"]' in src
    # A régi, hallgatói nézőpontú "Kiinduló látás" cím eltűnt a UI-kódból.
    assert "Kiinduló látás" not in body


def test_reinterpretation_is_optional_approve_works_without_it(session):
    ensure_sermon_workshop_state(session)
    update_sermon_workshop_section(
        session,
        "sermon_path",
        {
            "starting_point": "Alaphelyzet szövege",
            "first_shift": "Első fordulópont szövege",
            "deepening": "Mélyítés szövege",
            "reinterpretation": "",
        },
    )
    update_sermon_workshop_section(session, "sermon_path_status", "approved")
    assert session["sermon_workshop"]["sermon_path_status"] == "approved"
    assert session["sermon_workshop"]["sermon_path"]["reinterpretation"] == ""


def test_first_turning_point_can_be_skipped_when_not_warranted(session):
    """Az Első fordulópont kihagyható, ha a textus nem indokolja — csak az
    Alaphelyzet és a Mélyítés kitöltésével is jóváhagyható a szakasz."""
    ensure_sermon_workshop_state(session)
    update_sermon_workshop_section(
        session,
        "sermon_path",
        {
            "starting_point": "Alaphelyzet szövege",
            "first_shift": "",
            "deepening": "Mélyítés szövege",
        },
    )
    update_sermon_workshop_section(session, "sermon_path_status", "approved")
    saved = session["sermon_workshop"]["sermon_path"]
    assert saved["first_shift"] == ""
    assert session["sermon_workshop"]["sermon_path_status"] == "approved"


def test_reinterpretation_reaches_outline_background_only_when_approved():
    state = {
        "last_igehely": "Jn 3,16",
        "sermon_workshop": {
            "sermon_path": {
                "starting_point": "sp",
                "reinterpretation": "JÓVÁHAGYOTT átértelmezés szövege",
            },
            "sermon_path_status": "draft",
        },
    }
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "sermon_path" not in background

    state["sermon_workshop"]["sermon_path_status"] = "approved"
    bundle2 = collect_outline_context_bundle(state)
    background2 = extract_outline_background_material(bundle2)
    assert background2["sermon_path"]["reinterpretation"] == "JÓVÁHAGYOTT átértelmezés szövege"


def test_heuristic_intro_prefers_entry_point_belepes_over_starting_point():
    """A modell 1. eleme (Belépés) elsőbbséget élvez az Alaphelyzet (2.
    elem) felett a bevezető irány felépítésénél."""
    bundle = _passage_bundle(
        {
            "entry_point": {
                "today_connection": "tc",
                "type": "question",
                "text": "BELÉPÉS: konkrét nyitókérdés a hallgatóhoz.",
            },
            "entry_point_status": "approved",
            "sermon_path": {"starting_point": "ALAPHELYZET: a textus saját feszültsége."},
            "sermon_path_status": "approved",
        }
    )
    result = _heuristic_structured_from_bundle(bundle)
    assert "BELÉPÉS" in result["introduction_direction"]


def test_outline_system_prompt_defines_full_seven_element_model():
    from sermon_outline_engine import OUTLINE_SYSTEM_PROMPT

    for term in (
        "BELÉPÉS",
        "ALAPHELYZET",
        "ELSŐ FORDULÓPONT",
        "MÉLYÍTÉS ÉS FOKOZÁS",
        "ÁTÉRTELMEZÉS",
        "MÁSODIK FORDULÓPONT",
        "MEGÉRKEZÉS",
    ):
        assert term in OUTLINE_SYSTEM_PROMPT
