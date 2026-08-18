# ruff: noqa: E402
"""Fázis 2D.1 (célarchitektúra-terv, adatfolyam-javítás, 2026-08-14):
a Bibliai áttekintés és a részletes kutatási anyagok tényleges eljutása
a vázlatmotor promptjáig.

A korábbi, ideiglenes `scratchpad/dataflow_probe.py` szkript sentinel-
logikáját tartós regressziós tesztekké alakítja. Bizonyított hibák,
amiket ez a fájl őriz:

1. `st.session_state["overview"]` (Bibliai áttekintés) mentés/projekt-
   újratöltés után megmaradt, DE `collect_outline_context_bundle()`
   sosem olvasta — ezért a vázlatmotor promptjáig sem jutott el.
2. Ha `text_workshop.text_summary` bármely mezője nem üres (akár csak
   az automatikusan átmásolt `main_idea`), a collector korábbi
   `if summary_fields: ... else: ...` kizárólagos elágazása TELJESEN
   KIHAGYTA a nyers exegesis/theology/history/original_text mezőket —
   függetlenül azok jóváhagyott/friss állapotától.

Mindkettő javítva: az `overview` külön, approval nélküli bundle-kulcs;
a `text_summary` additív forrás, sosem helyettesíti a részletes
kutatási anyagot.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import (
    build_outline_user_prompt,
    compute_passage_context_hash,
    extract_outline_background_material,
)
from sermon_workshop_data import ensure_sermon_workshop_state, update_sermon_workshop_section
from sermon_workshop_outline_ai import (
    MAX_OVERVIEW_CHARS,
    collect_outline_context_bundle,
)
from textus_workshop_data import ensure_text_workshop_state, update_text_summary_fields
from workspace_data import build_project_data

OVERVIEW_SENTINEL = "OVERVIEW_SENTINEL_marker"
EXEGESIS_SENTINEL = "EXEGESIS_SENTINEL_marker"
ORIGINAL_LANGUAGE_SENTINEL = "ORIGINAL_LANGUAGE_SENTINEL_marker"
HISTORY_SENTINEL = "HISTORY_SENTINEL_marker"
THEOLOGY_SENTINEL = "THEOLOGY_SENTINEL_marker"
TEXT_SUMMARY_SENTINEL = "TEXT_SUMMARY_SENTINEL_marker"

_SENTINEL_SOURCE_KEYS = ("overview", "exegesis", "original_text", "history", "theology")
_SENTINELS = {
    "overview": OVERVIEW_SENTINEL,
    "exegesis": EXEGESIS_SENTINEL,
    "original_text": ORIGINAL_LANGUAGE_SENTINEL,
    "history": HISTORY_SENTINEL,
    "theology": THEOLOGY_SENTINEL,
}


def _full_sentinel_state(**extra) -> dict:
    state = {
        "last_igehely": "Lk 14,1-6",
        "igehely_input": "Lk 14,1-6",
        "passage_text": (
            "1 Amikor egyszer szombaton az egyik farizeus vezető házába ment "
            "étkezni, azok szemmel tartották őt. "
            "6 És nem tudtak erre felelni."
        ),
        "bible_translation": "RÚF 2014",
        "overview": OVERVIEW_SENTINEL,
        "exegesis": EXEGESIS_SENTINEL,
        "exegesis_status": "approved",
        "original_text": ORIGINAL_LANGUAGE_SENTINEL,
        "original_text_status": "approved",
        "history": HISTORY_SENTINEL,
        "history_status": "approved",
        "theology": THEOLOGY_SENTINEL,
        "theology_status": "approved",
    }
    state.update(extra)
    ensure_text_workshop_state(state)
    ensure_sermon_workshop_state(state)
    return state


# ---------------------------------------------------------------------------
# a) + b) mentés / normalizálás / projekt-újratöltés
# ---------------------------------------------------------------------------


def test_all_sentinels_survive_build_project_data():
    state = _full_sentinel_state()
    project = build_project_data(state)
    for key, sentinel in _SENTINELS.items():
        assert project.get(key) == sentinel, key


def test_all_sentinels_survive_reload_simulation():
    """Projekt-visszatöltés szimulációja: a mentett payload lesz az ÚJ
    session_state — ugyanazon a módon, ahogy a valódi projektbetöltés a
    payloadot közvetlenül a session_state-be írja vissza."""
    state = _full_sentinel_state()
    project = build_project_data(state)
    reloaded = dict(project)
    ensure_text_workshop_state(reloaded)
    ensure_sermon_workshop_state(reloaded)
    for key, sentinel in _SENTINELS.items():
        assert reloaded.get(key) == sentinel, key


# ---------------------------------------------------------------------------
# c) + d) + e) bundle → háttéranyag-kivonat → tényleges AI-prompt
# ---------------------------------------------------------------------------


def test_all_sentinels_reach_canonical_bundle():
    state = _full_sentinel_state()
    bundle = collect_outline_context_bundle(state)
    for key, sentinel in _SENTINELS.items():
        assert bundle.get(key) == sentinel, key


def test_all_sentinels_reach_background_material_extract():
    state = _full_sentinel_state()
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    for key, sentinel in _SENTINELS.items():
        assert background.get(key) == sentinel, key


def test_all_sentinels_reach_actual_ai_prompt_text():
    """Nem elég, hogy a bundle/background tartalmazza — a tényleges,
    `generate_fn`-nek átadandó promptban is meg kell jelennie."""
    state = _full_sentinel_state()
    bundle = collect_outline_context_bundle(state)
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    for key, sentinel in _SENTINELS.items():
        assert sentinel in prompt, key


def test_overview_label_appears_in_background_prompt_heading():
    state = _full_sentinel_state()
    bundle = collect_outline_context_bundle(state)
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    assert "Bibliai áttekintés" in prompt


# ---------------------------------------------------------------------------
# f) + g) text_summary jelenléte nem rejti el a részletes forrásokat
# ---------------------------------------------------------------------------


def test_full_text_summary_does_not_hide_detailed_research_sources():
    state = _full_sentinel_state()
    update_text_summary_fields(
        state,
        {
            "main_idea": "",
            "base_tension": TEXT_SUMMARY_SENTINEL,
            "key_exegetical_findings": "",
            "theological_emphases": "",
            "genre_structure_notes": "",
        },
        status="approved",
    )
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("text_summary", {}).get("base_tension") == TEXT_SUMMARY_SENTINEL
    for key in ("exegesis", "original_text", "history", "theology"):
        assert bundle.get(key) == _SENTINELS[key], key
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    for key in ("exegesis", "original_text", "history", "theology"):
        assert _SENTINELS[key] in prompt, key


def test_text_summary_with_only_copied_main_idea_does_not_hide_sources():
    """A konkrét, korábban bizonyított hiba: a Textusösszegzés panelen a
    `main_idea` a jóváhagyott `text_main_idea`-ból automatikusan
    átmásolódik MENTÉSKOR (`textus_workshop_ui._save_summary`) — ez
    ÖNMAGÁBAN, minden más mező üresen hagyása mellett is elég volt
    korábban ahhoz, hogy a teljes exegesis/theology/history/
    original_text eltűnjön a vázlatmotor elől."""
    state = _full_sentinel_state()
    tw = ensure_text_workshop_state(state)
    tw["text_main_idea"] = "Textus fő gondolat SENTINEL"
    tw["text_main_idea_status"] = "approved"
    update_text_summary_fields(
        state,
        {
            "main_idea": tw.get("text_main_idea") or "",
            "base_tension": "",
            "key_exegetical_findings": "",
            "theological_emphases": "",
            "genre_structure_notes": "",
        },
        status="draft",
    )
    bundle = collect_outline_context_bundle(state)
    assert "text_summary" in bundle
    for key in ("exegesis", "original_text", "history", "theology"):
        assert bundle.get(key) == _SENTINELS[key], key


# ---------------------------------------------------------------------------
# h) + i) + j) overview külön, approval nélküli, üres-eset viselkedés
# ---------------------------------------------------------------------------


def test_overview_reaches_bundle_without_text_summary():
    state = _full_sentinel_state()
    # nincs text_summary — az overview-nak enélkül is jelen kell lennie
    bundle = collect_outline_context_bundle(state)
    assert "text_summary" not in bundle
    assert bundle.get("overview") == OVERVIEW_SENTINEL


def test_overview_requires_no_approved_status():
    """Nincs `overview_status` mező sehol a felületen — az overview
    kizárólag a tartalom meglététől függ, jóváhagyástól nem."""
    state = _full_sentinel_state()
    assert "overview_status" not in state
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("overview") == OVERVIEW_SENTINEL
    background = extract_outline_background_material(bundle)
    assert background.get("overview") == OVERVIEW_SENTINEL


def test_empty_overview_produces_no_bundle_key_and_no_noisy_prompt_section():
    state = _full_sentinel_state(overview="")
    bundle = collect_outline_context_bundle(state)
    assert "overview" not in bundle
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    assert '"overview"' not in prompt


# ---------------------------------------------------------------------------
# k) más igehelyhez tartozó, stale részletes anyag nem szivárog át
# ---------------------------------------------------------------------------


def test_stale_detailed_source_still_excluded_from_background_after_fix():
    """A frissességi (context-hash) szabály VÁLTOZATLAN maradt — csak az
    `if/else` kizárólagosság és az `overview` hiánya szűnt meg. Egy más
    igehelyhez jóváhagyott exegézis továbbra sem jut el a háttéranyagba."""
    state = _full_sentinel_state()
    # Jóváhagyáskori ujjlenyomat egy MÁSIK igehelyhez/szöveghez.
    stale_bundle = {
        "passage_reference": "Jn 1,1",
        "bible_translation": "RÚF 2014",
        "passage_text": "Kezdetben vala az Ige...",
    }
    state["exegesis_approved_context_hash"] = compute_passage_context_hash(stale_bundle)
    bundle = collect_outline_context_bundle(state)
    # A nyers bundle-ben még benne van (a hívó dolga a stale-szűrés)...
    assert bundle.get("exegesis") == EXEGESIS_SENTINEL
    # ...de a háttéranyag-kivonatból, ami ténylegesen promptba kerül, kimarad.
    background = extract_outline_background_material(bundle)
    assert "exegesis" not in background
    # A többi, nem-stale forrás changetlenül átmegy.
    assert background.get("theology") == THEOLOGY_SENTINEL
    assert background.get("overview") == OVERVIEW_SENTINEL


# ---------------------------------------------------------------------------
# l) Vázlatkosár leválasztva, homiletikai döntések collector-viselkedése
#    változatlan
# ---------------------------------------------------------------------------


def test_basket_disconnected_and_homiletical_decisions_collector_behavior_unchanged():
    """RESET 1A-DATA (2026-08-18): megfordított elvárás a korábbi
    `test_basket_and_homiletical_decisions_collector_behavior_unchanged`
    tesztre — a Vázlatkosár tartalma többé NEM kerül a bundle-be, a
    homiletikai döntések (itt: human_condition) approval+frissesség
    kapuja viszont változatlan."""
    state = _full_sentinel_state()
    state["basket"] = [["Exegézis", "Megtartandó idézet SENTINEL"]]
    update_sermon_workshop_section(
        state, "human_condition", {"condition": "Emberi helyzet SENTINEL"}
    )
    update_sermon_workshop_section(state, "human_condition_status", "approved")

    bundle = collect_outline_context_bundle(state)
    assert "outline_basket" not in bundle
    assert bundle.get("human_condition", {}).get("condition") == "Emberi helyzet SENTINEL"
    assert bundle.get("human_condition_status") == "approved"


# ---------------------------------------------------------------------------
# 5. Tokenhatás — méret és csonkolási sorrend
# ---------------------------------------------------------------------------


def test_max_overview_chars_truncates_oversized_overview():
    long_overview = "Á" * (MAX_OVERVIEW_CHARS + 500)
    state = _full_sentinel_state(overview=long_overview)
    bundle = collect_outline_context_bundle(state)
    assert len(bundle["overview"]) <= MAX_OVERVIEW_CHARS


def test_background_bundle_size_with_all_sources_present_is_bounded():
    """Az összes forrás egyidejű jelenléte mellett is a dokumentált
    per-forrás karakterkorlátok (`MAX_OVERVIEW_CHARS`/`MAX_EXEGESIS_CHARS`/
    stb.) érvényesülnek — nincs új, korlátlan összegző blokk bevezetve."""
    from sermon_workshop_outline_ai import (
        MAX_EXEGESIS_CHARS,
        MAX_HISTORY_CHARS,
        MAX_THEOLOGY_CHARS,
    )

    state = _full_sentinel_state(
        overview="Á" * (MAX_OVERVIEW_CHARS + 200),
        exegesis="É" * (MAX_EXEGESIS_CHARS + 200),
        theology="Ő" * (MAX_THEOLOGY_CHARS + 200),
        history="Ú" * (MAX_HISTORY_CHARS + 200),
        original_text="Ű" * (MAX_EXEGESIS_CHARS + 200),
    )
    bundle = collect_outline_context_bundle(state)
    assert len(bundle["overview"]) <= MAX_OVERVIEW_CHARS
    assert len(bundle["exegesis"]) <= MAX_EXEGESIS_CHARS
    assert len(bundle["theology"]) <= MAX_THEOLOGY_CHARS
    assert len(bundle["history"]) <= MAX_HISTORY_CHARS
    assert len(bundle["original_text"]) <= MAX_EXEGESIS_CHARS
    # Nincs bevezetve új, összevont/duplikált mező a méretkorlátozás megkerülésére.
    assert "overview_full" not in bundle
    assert "background_summary" not in bundle
