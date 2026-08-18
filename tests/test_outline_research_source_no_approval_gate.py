# ruff: noqa: E402
"""Fázis 2D.2 (célarchitektúra-terv, adatfolyam-audit, 2026-08-14):
a Textusműhely kutatási háttéranyagainak (exegézis / eredeti nyelvi
anyag / kortörténet / teológia) approval-gating egyszerűsítése.

PREFLIGHT-EREDMÉNY (ld. a fázisvégi audit is): a `collect_outline_
context_bundle()` → `extract_outline_background_material()` →
`build_outline_user_prompt()` láncban ezekre a forrásokra **jelenleg
NINCS approval-feltétel** — ezt a "Korrekciós fázis 3.1" már korábban
bevezette (ld. `sermon_outline_engine.py` `_CANONICAL_TEXTUS_SOURCE_KEYS`
dokumentációja és `tests/test_canonical_source_collector.py`, ami már
kimerítően teszteli a bundle/background szintet). Éles, produkciós
kódmódosítás ezért NEM történt ebben a fázisban.

Ez a fájl KÉT, a meglévő suite-ból hiányzó bizonyítási szintet told
hozzá, ugyanazzal a sentinel-mintával, mint a 2D.1:
1. a teljes mentés→projekt-újratöltés (`build_project_data` + reload)
   láncot, NEM csak az élő session-collector viselkedést;
2. a TÉNYLEGES AI-prompt szövegét (nem csak a bundle/background dict-et).

Emellett explicit regressziós bizonyítékot ad arra, hogy a Vázlatkosár
és a homiletikai döntések collector-viselkedése ebben a fázisban is
érintetlen maradt. (Az overview approval-mentességének non-regressziós
próbája már a 2D.1 `tests/test_outline_canonical_background_flow.py`
fájljában megvan — itt szándékosan nem ismételtük meg, hogy elkerüljük
a lényegében teljes duplikációt.)

Két, felülvizsgálat során lényegében teljesen redundánsnak bizonyult
tesztet NEM tartalmaz ez a fájl (eltávolítva, ld. commit-üzenet/audit):
egy, ami szó szerint megismételte a meglévő
`test_canonical_source_collector.py::test_source_without_saved_hash_
treated_as_fresh_backward_compat` állítását (és amit a saját, ugyanitt
maradt `test_draft_research_sources_reach_background_material_after_
reload` tesztje is mellékesen bizonyít, hiszen a `_draft_research_
state()` fixture sosem állít be hash-t), és egy, ami szó szerint
megismételte a 2D.1 `test_overview_requires_no_approved_status`
tesztjét.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import (
    build_outline_user_prompt,
    compute_current_passage_context_hash,
    compute_passage_context_hash,
    extract_outline_background_material,
)
from sermon_workshop_data import ensure_sermon_workshop_state, update_sermon_workshop_section
from sermon_workshop_outline_ai import collect_outline_context_bundle
from textus_workshop_data import ensure_text_workshop_state
from workspace_data import build_project_data

EXEGESIS_SENTINEL = "EXEGESIS_2D2_SENTINEL"
ORIGINAL_LANGUAGE_SENTINEL = "ORIGINAL_LANGUAGE_2D2_SENTINEL"
HISTORY_SENTINEL = "HISTORY_2D2_SENTINEL"
THEOLOGY_SENTINEL = "THEOLOGY_2D2_SENTINEL"

_RESEARCH_SENTINELS = {
    "exegesis": EXEGESIS_SENTINEL,
    "original_text": ORIGINAL_LANGUAGE_SENTINEL,
    "history": HISTORY_SENTINEL,
    "theology": THEOLOGY_SENTINEL,
}


def _draft_research_state(**extra) -> dict:
    """Mind a négy kutatási forrás DRAFT állapotban (sosem jóváhagyva),
    de az AKTUÁLIS igehelyhez tartozó ujjlenyomattal — ez a normál,
    "generáltam, de még nem hagytam jóvá" felhasználói eset."""
    state = {
        "last_igehely": "Lk 14,1-6",
        "igehely_input": "Lk 14,1-6",
        "passage_text": (
            "1 Amikor egyszer szombaton az egyik farizeus vezető házába ment "
            "étkezni, azok szemmel tartották őt. "
            "6 És nem tudtak erre felelni."
        ),
        "bible_translation": "RÚF 2014",
        "exegesis": EXEGESIS_SENTINEL,
        "exegesis_status": "draft",
        "original_text": ORIGINAL_LANGUAGE_SENTINEL,
        "original_text_status": "draft",
        "history": HISTORY_SENTINEL,
        "history_status": "draft",
        "theology": THEOLOGY_SENTINEL,
        "theology_status": "draft",
    }
    state.update(extra)
    ensure_text_workshop_state(state)
    ensure_sermon_workshop_state(state)
    return state


# ---------------------------------------------------------------------------
# A) approval nem feltétel — teljes mentés→visszatöltés lánc + prompt
# ---------------------------------------------------------------------------


def test_draft_research_sources_survive_build_project_data_and_reload():
    state = _draft_research_state()
    project = build_project_data(state)
    for key, sentinel in _RESEARCH_SENTINELS.items():
        assert project.get(key) == sentinel, key
        assert project.get(f"{key}_status") == "draft", key

    reloaded = dict(project)
    ensure_text_workshop_state(reloaded)
    ensure_sermon_workshop_state(reloaded)
    for key, sentinel in _RESEARCH_SENTINELS.items():
        assert reloaded.get(key) == sentinel, key


def test_draft_research_sources_reach_background_material_after_reload():
    state = _draft_research_state()
    project = build_project_data(state)
    reloaded = dict(project)
    ensure_text_workshop_state(reloaded)
    ensure_sermon_workshop_state(reloaded)

    bundle = collect_outline_context_bundle(reloaded)
    background = extract_outline_background_material(bundle)
    for key, sentinel in _RESEARCH_SENTINELS.items():
        assert background.get(key) == sentinel, key


def test_draft_research_sources_reach_actual_ai_prompt_text():
    """Nem elég, hogy a háttéranyag-kivonat tartalmazza — a ténylegesen a
    `generate_fn`-nek átadott promptban is meg kell jelenniük, jóváhagyás
    nélkül is."""
    state = _draft_research_state()
    bundle = collect_outline_context_bundle(state)
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    for key, sentinel in _RESEARCH_SENTINELS.items():
        assert sentinel in prompt, key


def test_old_never_approved_status_reaches_prompt_too():
    """Régi, sosem jóváhagyott státusszal (vagy státuszmező teljes
    hiányával) mentett tartalom is eljut a promptig."""
    state = _draft_research_state(
        exegesis_status="", original_text_status="", history_status="", theology_status=""
    )
    bundle = collect_outline_context_bundle(state)
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    for key, sentinel in _RESEARCH_SENTINELS.items():
        assert sentinel in prompt, key


# ---------------------------------------------------------------------------
# B) freshness / igehely-azonosság védelem — VÁLTOZATLANUL érvényesül
# ---------------------------------------------------------------------------


def test_empty_research_source_never_reaches_bundle_or_prompt():
    state = _draft_research_state(exegesis="", theology="   ")
    bundle = collect_outline_context_bundle(state)
    assert "exegesis" not in bundle
    assert "theology" not in bundle
    background = extract_outline_background_material(bundle)
    assert "exegesis" not in background
    assert "theology" not in background
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    assert EXEGESIS_SENTINEL not in prompt
    assert THEOLOGY_SENTINEL not in prompt


def test_different_passage_research_source_excluded_from_prompt():
    """Más igehelyhez jóváhagyott/mentett tartalom — a mentéskori
    ujjlenyomat egy MÁSIK passzushoz tartozik — nem szivárog át."""
    other_passage_bundle = {
        "passage_reference": "Róm 8,28",
        "bible_translation": "RÚF 2014",
        "passage_text": "Más igehelyhez tartozó szöveg.",
    }
    stale_hash = compute_passage_context_hash(other_passage_bundle)
    state = _draft_research_state(
        exegesis_approved_context_hash=stale_hash,
        theology_approved_context_hash=stale_hash,
    )
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "exegesis" not in background
    assert "theology" not in background
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    assert EXEGESIS_SENTINEL not in prompt
    assert THEOLOGY_SENTINEL not in prompt
    # A nem-stale forrásokat (history/original_text) ez nem érinti.
    assert HISTORY_SENTINEL in prompt
    assert ORIGINAL_LANGUAGE_SENTINEL in prompt


def test_proven_stale_same_passage_hash_mismatch_excluded():
    """Bizonyítottan stale eset: a mentéskori hash a JELENLEGI igehelyhez
    tartozna, de a bibliai szöveg időközben megváltozott — az eltérő
    hash miatt kizáródik."""
    state = _draft_research_state()
    current_fresh_hash = compute_current_passage_context_hash(state)
    state["exegesis_approved_context_hash"] = current_fresh_hash
    # A szöveg utólag megváltozik (pl. RÚF-frissítés) — a hash már nem egyezik.
    state["passage_text"] = "Egy teljesen más, később betöltött bibliai szöveg."

    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "exegesis" not in background
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    assert EXEGESIS_SENTINEL not in prompt


# ---------------------------------------------------------------------------
# C) nem érintett viselkedés — overview, kosár, homiletikai döntések,
#    végső vázlat jóváhagyása (regressziós védőháló erre a fázisra)
# ---------------------------------------------------------------------------


def test_homiletical_decision_keys_still_require_approval_after_2d2():
    """A hét modellmezőt (itt: human_condition) a 2D.2 NEM érinti — az
    approval+frissesség kettős kapu változatlan."""
    state = _draft_research_state()
    update_sermon_workshop_section(
        state, "human_condition", {"condition": "Draft emberi helyzet, nincs jóváhagyva."}
    )
    update_sermon_workshop_section(state, "human_condition_status", "draft")

    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "human_condition" not in background

    update_sermon_workshop_section(state, "human_condition_status", "approved")
    update_sermon_workshop_section(
        state,
        "human_condition_approved_context_hash",
        compute_current_passage_context_hash(state),
    )
    bundle2 = collect_outline_context_bundle(state)
    background2 = extract_outline_background_material(bundle2)
    assert "human_condition" in background2


def test_outline_basket_collector_behavior_unchanged_after_2d2():
    state = _draft_research_state()
    state["basket"] = [("Exegézis", "2D2 kosár-regresszió SENTINEL")]
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("outline_basket") == [
        {"source": "Exegézis", "content": "2D2 kosár-regresszió SENTINEL"}
    ]
