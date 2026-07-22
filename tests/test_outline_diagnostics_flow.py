"""Vázlat → diagnosztika adatfolyam: API-hiba, heurisztika, frissesség."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_diagnostics_ai import (
    fallback_outline_diagnostics,
    parse_outline_diagnostics,
    run_outline_diagnostics,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    save_sermon_outline,
    save_sermon_outline_diagnostics,
)
from sermon_workshop_outline_ai import (
    assemble_sermon_outline,
    build_outline_from_workshop,
    collect_available_sermon_material,
)
from tests.test_jude_e2e_workflow import build_jude_state


def test_api_exception_does_not_claim_success():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)

    def boom(*_a, **_k):
        raise RuntimeError("simulated network failure")

    result = run_outline_diagnostics(
        sermon_outline=outline,
        sermon_main_idea=outline.get("main_idea") or "",
        generate_fn=boom,
    )
    assert result.ok is False
    assert result.mode == "api_error"
    assert "nem sikerült" in result.error_message.casefold()
    assert result.diagnostic_areas == []
    assert any("Generálási hiba:" in w for w in result.warnings)


def test_api_error_text_does_not_fallback_as_success():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)

    def bad_api(*_a, **_k):
        return "⚠️ API hiba: rate limit"

    result = run_outline_diagnostics(
        sermon_outline=outline,
        generate_fn=bad_api,
    )
    assert result.ok is False
    assert result.mode == "api_error"
    assert result.diagnostic_areas == []


def test_local_heuristic_is_marked_and_has_no_fake_zero_areas():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    result = run_outline_diagnostics(
        sermon_outline=outline,
        generate_fn=None,
    )
    assert result.ok is True
    assert result.mode == "local_heuristic"
    assert result.diagnostic_areas == []
    assert any("helyi" in w.casefold() for w in result.warnings)


def test_ai_areas_null_score_not_zero():
    raw = """
    {
      "overview": "Részleges, de használható.",
      "strengths": ["Van fő gondolat."],
      "refinements": [],
      "diagnostic_areas": [
        {"key": "text_fidelity", "label": "Textushűség", "status": "stable", "score": 3, "summary": "ok"},
        {"key": "application", "label": "Alkalmazás", "status": "not_enough_information", "score": 0, "summary": ""}
      ],
      "ready_to_use": false,
      "next_step": "Finomítsd az alkalmazást."
    }
    """
    parsed = parse_outline_diagnostics(raw)
    assert parsed.ok
    by_key = {a["key"]: a for a in parsed.diagnostic_areas}
    assert by_key["text_fidelity"]["score"] == 3
    assert by_key["application"]["score"] is None
    assert by_key["application"]["status"] == "not_enough_information"
    # Mind a 8 tengely jelen van
    assert len(parsed.diagnostic_areas) == 8


def test_collect_available_sermon_material_ignores_empty_status():
    state = build_jude_state()
    # Státusz draft, de van tartalom
    state[SERMON_WORKSHOP_KEY]["sermon_main_idea_status"] = "draft"
    bundle = collect_available_sermon_material(state)
    assert "passage_reference" in bundle.get("source_keys", [])
    assert bundle.get("sermon_main_idea") or bundle.get("text_main_idea")


def test_partial_assemble_then_diagnose_heuristic():
    state = build_jude_state()
    # Csak részleges anyag — assemble mégis működik
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    save_sermon_outline(state, result.outline)
    diag = run_outline_diagnostics(
        sermon_outline=result.outline,
        generate_fn=None,
    )
    assert diag.ok
    assert diag.mode == "local_heuristic"
    payload = diag.to_dict()
    payload["outline_updated_at_at_diagnosis"] = state[SERMON_WORKSHOP_KEY][
        "sermon_outline_updated_at"
    ]
    save_sermon_outline_diagnostics(state, payload)
    # Elavultság: vázlat későbbi frissítése
    save_sermon_outline(state, result.outline, mark_manual_edit=True)
    outline_u = state[SERMON_WORKSHOP_KEY]["sermon_outline_updated_at"]
    diag_u = state[SERMON_WORKSHOP_KEY]["sermon_outline_diagnostics_generated_at"]
    pinned = state[SERMON_WORKSHOP_KEY]["sermon_outline_diagnostics"][
        "outline_updated_at_at_diagnosis"
    ]
    assert outline_u >= pinned
    # A diagnózis időbélyege a mentéskor keletkezett — a vázlat újraírása után elavult
    assert outline_u >= diag_u or outline_u > pinned


def test_manual_edit_does_not_block_diagnostics():
    state = build_jude_state()
    outline = build_outline_from_workshop(state)
    outline["manually_edited"] = True
    outline["main_idea"] = "Kézzel módosított fő gondolat."
    save_sermon_outline(state, outline, mark_manual_edit=True)
    before = copy.deepcopy(state[SERMON_WORKSHOP_KEY]["sermon_outline"])
    diag = run_outline_diagnostics(
        sermon_outline=before,
        generate_fn=None,
    )
    assert diag.ok
    save_sermon_outline_diagnostics(state, diag.to_dict())
    assert state[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"] == before["main_idea"]
    assert state[SERMON_WORKSHOP_KEY]["sermon_outline"]["manually_edited"] is True
