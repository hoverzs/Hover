"""Fázis 1 non-regressziós tesztek: az új, additív `arc` adatmodell
JELENLÉTE nem változtathatja meg a jelenlegi vázlatmotor forráscsomagját,
a navigáció/progressz-számítást, sem a projektmentés/-betöltés más mezőit.

Célarchitektúra-terv (TEXTUS_EGYSZERUSITETT_IGEHIRDETESI_CELARCHITEKTURA_
TERV_2026-08-13.md), 1. fázis — a fázishatárok explicit tiltják az `arc`
aktiválását, ezért ezek a tesztek kifejezetten azt bizonyítják, hogy a
jelenlegi (öt munkafázisos) rendszer viselkedése bit-pontosan változatlan.
"""

from __future__ import annotations

import copy

from sermon_outline_engine import collect_canonical_source_material
from sermon_workshop_data import get_default_arc, get_default_sermon_workshop
from sermon_workshop_outline_ai import collect_outline_context_bundle
from workshop_nav_ui import sermon_phase_completed, sermon_phase_statuses, sermon_section_statuses
from workspace_data import build_project_data


def _base_state() -> dict:
    return {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "bible_translation": "RÚF 2014",
        "passage_text": "Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta...",
        "exegesis": "Exegetikai anyag.",
        "exegesis_status": "approved",
        "theology": "Teológiai anyag.",
        "theology_status": "approved",
        "sermon_workshop": get_default_sermon_workshop(),
    }


def _state_with_populated_arc() -> dict:
    state = _base_state()
    sw = state["sermon_workshop"]
    arc = get_default_arc()
    for point in arc.values():
        point["text"] = "Kitöltött, de a jelen fázisban figyelmen kívül hagyandó szöveg."
    sw["arc"] = arc
    return state


# ---------------------------------------------------------------------------
# 12. Az arc jelenléte nem változtatja meg a vázlatmotor forráscsomagját.
# ---------------------------------------------------------------------------


def _drop_internal_keys(bundle: dict) -> dict:
    """A `_`-prefixű bundle-kulcsok (pl. `_sw`) belső, nyers passthrough
    adatok — nem a vázlatmotor által ténylegesen FELHASZNÁLT kanonikus
    forráskészlet része. Ugyanezt a szűrést alkalmazza a meglévő
    `tests/test_partial_outline_workflow.py::test_context_bundle_token_
    efficient_no_aliases` is a bundle "tényleges tartalmának" ellenőrzésekor."""
    return {k: v for k, v in bundle.items() if not str(k).startswith("_")}


def test_outline_context_bundle_identical_with_and_without_populated_arc():
    without_arc = _base_state()
    with_arc = _state_with_populated_arc()

    bundle_without = collect_outline_context_bundle(without_arc)
    bundle_with = collect_outline_context_bundle(with_arc)

    assert _drop_internal_keys(bundle_without) == _drop_internal_keys(bundle_with)
    # A `_sw` belső mezőn kívül semmi más nem térhet el.
    diff_keys = {
        k
        for k in set(bundle_without) | set(bundle_with)
        if bundle_without.get(k) != bundle_with.get(k)
    }
    assert diff_keys <= {"_sw"}


def test_canonical_source_material_identical_with_and_without_populated_arc():
    without_arc = _base_state()
    with_arc = _state_with_populated_arc()

    bundle_without = collect_outline_context_bundle(without_arc)
    bundle_with = collect_outline_context_bundle(with_arc)

    canonical_without = collect_canonical_source_material(bundle_without)
    canonical_with = collect_canonical_source_material(bundle_with)

    assert canonical_without == canonical_with
    # Explicit ellenőrzés: az `arc.*` kulcsok NEM jelennek meg a `sources`-ban.
    assert not any(str(k).startswith("arc.") for k in canonical_with.get("sources", {}))


# ---------------------------------------------------------------------------
# 13. Régi projekt az öt munkafázisos UI navigációjában/progresszében
#     változatlanul jelenik meg.
# ---------------------------------------------------------------------------


def test_nav_section_and_phase_statuses_unaffected_by_populated_arc():
    without_arc = _base_state()
    without_arc["sermon_workshop"]["sermon_main_idea"] = "Fókuszmondat."
    without_arc["sermon_workshop"]["sermon_main_idea_status"] = "approved"

    with_arc = copy.deepcopy(without_arc)
    arc = get_default_arc()
    for point in arc.values():
        point["text"] = "Ez a mező ma még nem befolyásolhatja a navigációt."
    with_arc["sermon_workshop"]["arc"] = arc

    statuses_without = sermon_section_statuses(without_arc)
    statuses_with = sermon_section_statuses(with_arc)
    assert statuses_without == statuses_with

    phase_statuses_without = sermon_phase_statuses(without_arc)
    phase_statuses_with = sermon_phase_statuses(with_arc)
    assert phase_statuses_without == phase_statuses_with

    completed_without = sermon_phase_completed(without_arc)
    completed_with = sermon_phase_completed(with_arc)
    assert completed_without == completed_with


# ---------------------------------------------------------------------------
# 14. Az `arc` mező projektmentés/-betöltés után is megmarad (a meglévő
#     `sermon_workshop` -> normalize_sermon_workshop wholesale-allowlist út
#     automatikusan hordozza, nincs szükség külön allowlist-bővítésre).
# ---------------------------------------------------------------------------


def test_arc_field_survives_project_data_build_roundtrip():
    state = _state_with_populated_arc()

    project_data = build_project_data(state)

    assert "sermon_workshop" in project_data
    saved_arc = project_data["sermon_workshop"]["arc"]
    assert saved_arc == state["sermon_workshop"]["arc"]


def test_project_data_build_unaffected_by_arc_for_other_keys():
    """A mentett projekt egyéb (nem `arc`) mezői bit-pontosan azonosak
    legyenek attól függetlenül, hogy az `arc` ki van-e töltve."""
    without_arc = _base_state()
    with_arc = _state_with_populated_arc()

    project_without = build_project_data(without_arc)
    project_with = build_project_data(with_arc)

    project_without["sermon_workshop"] = dict(project_without["sermon_workshop"])
    project_with["sermon_workshop"] = dict(project_with["sermon_workshop"])
    del project_without["sermon_workshop"]["arc"]
    del project_with["sermon_workshop"]["arc"]

    assert project_without == project_with
