"""Részleges munkafolyamat — vázlat + diagnosztika (A–O)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_diagnostics_ai import (
    fallback_outline_diagnostics,
    run_outline_diagnostics,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    save_sermon_outline,
)
from sermon_workshop_outline_ai import (
    PROVISIONAL_NOTICE,
    assemble_sermon_outline,
    assess_outline_readiness,
    build_outline_from_workshop,
    collect_outline_context_bundle,
    outline_has_provisional_bridges,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop
from tests.test_jude_e2e_workflow import build_jude_state
from workspace_data import build_project_data, sanitize_project_data


def _base_state(**extra) -> dict:
    state = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "",
        "exegesis": "",
        "theology": "",
        "history": "",
        "last_sajat": "",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state


def test_a_full_workflow_uses_approved():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    assert outline["main_idea"]
    assert len(outline["movements"]) == 3
    assert outline["movements"][0]["title"] == "Emlékezzetek"
    assert "sermon_movements" not in (outline.get("provisional_sections") or [])
    assert "sermon_movements" in (outline.get("source_sections") or [])


def test_b_textus_only_builds_outline():
    state = _base_state(
        passage_text="16 Mert úgy szerette Isten a világot…",
        exegesis="A szeret ige a szöveg központi mozgása.",
        theology="Isten szabadító szeretete.",
    )
    state[TEXT_WORKSHOP_KEY]["text_main_idea"] = "Isten szeretete megváltást hoz."
    state[TEXT_WORKSHOP_KEY]["text_main_idea_status"] = "approved"
    ready = assess_outline_readiness(state)
    assert ready.ok
    result = assemble_sermon_outline(state, generate_fn=None, synthesize=True)
    assert result.ok
    assert result.outline["main_idea"]
    assert result.outline["movements"]
    assert 2 <= len(result.outline["movements"]) <= 5
    assert outline_has_provisional_bridges(result.outline)
    assert PROVISIONAL_NOTICE in result.warnings
    assert not state[SERMON_WORKSHOP_KEY].get("sermon_movements")


def test_c_textus_plus_sermon_main_idea_no_m5_m9():
    state = _base_state(
        passage_text="16 Mert úgy szerette Isten a világot…",
        exegesis="Exegézis röviden.",
    )
    state[TEXT_WORKSHOP_KEY]["text_main_idea"] = "Textus fő gondolat"
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Igehirdetési fő gondolat"
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea_status"] = "draft"
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    assert result.outline["main_idea"] == "Igehirdetési fő gondolat"
    assert result.outline["movements"]
    assert not result.outline.get("lection", {}).get("reference")
    assert not result.outline.get("listener_question")


def test_d_own_idea_and_notes():
    state = _base_state(
        passage_text="Rövid bibliai szöveg a keresztről.",
        last_sajat="A kereszt a szeretet jele a gyülekezetnek.",
    )
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Saját fő gondolat a keresztről"
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    assert "Saját fő gondolat" in result.outline["main_idea"]
    assert result.outline["movements"]


def test_e_no_m6_creates_provisional_movements():
    state = _base_state(passage_text="Rövid textus.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Fő gondolat M6 nélkül"
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    assert 2 <= len(result.outline["movements"]) <= 5
    assert "sermon_movements" in (result.outline.get("provisional_sections") or [])
    assert state[SERMON_WORKSHOP_KEY]["sermon_movements"] == []


def test_f_existing_m6_preserved_exactly():
    state = build_jude_state()
    before = [dict(m) for m in state[SERMON_WORKSHOP_KEY]["sermon_movements"]]
    outline = build_outline_from_workshop(state)
    titles = [m["title"] for m in outline["movements"]]
    assert titles == ["Emlékezzetek", "Gúnyolódók", "Megmaradás"]
    assert "sermon_movements" not in (outline.get("provisional_sections") or [])
    assert state[SERMON_WORKSHOP_KEY]["sermon_movements"] == before


def test_g_no_m7_not_diagnostic_error():
    state = _base_state(passage_text="Textus.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Fő gondolat"
    result = assemble_sermon_outline(state, generate_fn=None)
    save_sermon_outline(state, result.outline)
    diag = run_outline_diagnostics(
        sermon_outline=result.outline, generate_fn=None
    )
    assert diag.ok
    assert not any(
        "illusztr" in (r.title or "").casefold() for r in diag.refinements
    )


def test_h_no_lection_or_prayer_hidden():
    state = _base_state(passage_text="Textus.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Fő gondolat"
    outline = build_outline_from_workshop(state)
    assert not outline.get("lection", {}).get("reference")
    assert not outline.get("prayer_before", {}).get("own_thoughts")
    assert not outline.get("prayer_after", {}).get("selected_opening")


def test_i_no_closing_module_gets_provisional():
    state = _base_state(passage_text="Textus.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Fő gondolat lezárás nélkül"
    outline = build_outline_from_workshop(state)
    assert outline["closing"]["final_insight"]
    assert "closing" in (outline.get("provisional_sections") or [])


def test_j_partial_outline_diagnostics_no_module_list():
    state = _base_state(passage_text="Textus.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Részleges fő gondolat"
    outline = assemble_sermon_outline(state, generate_fn=None).outline
    diag = fallback_outline_diagnostics(outline=outline)
    assert diag.ok
    assert diag.overview
    assert len(diag.strengths) <= 3
    assert len(diag.refinements) <= 3
    joined = " ".join(
        [diag.overview]
        + diag.strengths
        + [r.title + r.explanation for r in diag.refinements]
        + diag.warnings
    ).casefold()
    assert "m4" not in joined
    assert "m5" not in joined
    assert "m6" not in joined
    assert "m7" not in joined
    assert "m9" not in joined
    assert "az ellenőrzés a jelenlegi vázlat alapján készült" in joined


def test_k_sparse_but_usable_short_outline():
    state = _base_state(passage_text="Rövid.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Egy mondatos fő gondolat"
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    assert 2 <= len(result.outline["movements"]) <= 5
    titles = [m["title"] for m in result.outline["movements"]]
    assert len(titles) == len(set(titles))


def test_l_empty_project_blocks_template_sermon(monkeypatch):
    """Nincs szöveg + sikertelen RÚF → ne készüljön sablonprédikáció."""

    def _ruf_fail(_ref: str):
        return {"success": False, "error": "not found"}

    monkeypatch.setattr(
        "ruf_bible_service.fetch_ruf_passage",
        _ruf_fail,
        raising=False,
    )
    # Invalid ref so even a live RÚF path cannot silently fill the gap.
    state = _base_state(
        passage_text="",
        last_igehely="Xyzzy 99,1",
        igehely_input="Xyzzy 99,1",
    )
    ready = assess_outline_readiness(state)
    assert not ready.ok
    result = assemble_sermon_outline(state, generate_fn=None)
    assert not result.ok
    assert (
        "bibliai szöveg" in result.error_message.casefold()
        or "rúf" in result.error_message.casefold()
        or "igehely" in result.error_message.casefold()
    )


def test_m_save_reload_partial_outline():
    state = _base_state(passage_text="Textus mentéshez.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Mentendő fő gondolat"
    result = assemble_sermon_outline(state, generate_fn=None)
    save_sermon_outline(state, result.outline)
    payload = sanitize_project_data(build_project_data(state))
    reloaded = normalize_sermon_workshop(payload[SERMON_WORKSHOP_KEY])
    assert reloaded["sermon_outline"]["main_idea"] == result.outline["main_idea"]
    assert reloaded["sermon_outline"].get("source_sections")
    assert reloaded["sermon_outline"].get("provisional_sections")


def test_n_project_switch_isolation():
    a = _base_state(passage_text="A", last_igehely="Jn 1,1")
    b = _base_state(passage_text="B", last_igehely="Jn 2,1")
    a[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Projekt A"
    b[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Projekt B"
    oa = assemble_sermon_outline(a, generate_fn=None).outline
    ob = assemble_sermon_outline(b, generate_fn=None).outline
    save_sermon_outline(a, oa)
    save_sermon_outline(b, ob)
    assert a[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"] == "Projekt A"
    assert b[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"] == "Projekt B"


def test_o_old_project_without_meta():
    legacy = normalize_sermon_workshop(
        {
            "sermon_main_idea": "régi",
            "sermon_outline": {
                "main_idea": "Régi vázlat",
                "movements": [{"title": "Egy", "core_content": "Tartalom"}],
            },
        }
    )
    outline = legacy["sermon_outline"]
    assert outline["main_idea"] == "Régi vázlat"
    assert outline.get("source_sections") == []
    assert outline.get("provisional_sections") == []
    diag = run_outline_diagnostics(sermon_outline=outline, generate_fn=None)
    assert diag.ok
    assert not diag.missing_outline


def test_context_bundle_token_efficient_no_aliases():
    state = build_jude_state()
    bundle = collect_outline_context_bundle(state)
    assert "passage_text" in bundle
    assert "igehely_input" not in bundle
    assert "last_igehely" not in bundle
    raw = json.dumps(
        {k: v for k, v in bundle.items() if not str(k).startswith("_")},
        ensure_ascii=False,
    )
    assert "sermon_main_idea_suggestions" not in raw
    assert "before_suggestions" not in raw
    assert "diagnostics" not in raw


def test_assemble_does_not_write_back_workshop_fields():
    state = _base_state(passage_text="Textus.")
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea"] = "Fő"
    before = copy.deepcopy(state[SERMON_WORKSHOP_KEY])
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    sw = state[SERMON_WORKSHOP_KEY]
    assert sw["sermon_movements"] == before["sermon_movements"]
    assert sw["closing"] == before["closing"]
    assert sw["listener_tension"] == before["listener_tension"]
    assert sw["human_condition"] == before["human_condition"]
