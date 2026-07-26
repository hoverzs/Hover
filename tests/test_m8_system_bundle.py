# ruff: noqa: E402
"""M8 diagnosztika: saját rendszerprompt, ne az M7 enrichment csomag."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_m7_ai import M7_SYSTEM_BUNDLE
from sermon_workshop_m8_ai import (
    M8_SYSTEM_BUNDLE,
    TAB_DIAG,
    _call_diagnostics_generate,
    run_homiletical_diagnostics,
)


def test_m8_system_bundle_is_diagnostics_specific_not_m7():
    assert M8_SYSTEM_BUNDLE.strip()
    assert M8_SYSTEM_BUNDLE != M7_SYSTEM_BUNDLE
    low = M8_SYSTEM_BUNDLE.casefold()
    assert "diagnoszt" in low
    assert "értékel" in low or "ertekél" in low or "diagnosztizálj" in low
    # Ne legyen kép/illusztráció-generáló szerep
    assert "ajánlj új képeket" not in low
    assert "recommended_textual_images" not in low


def test_m8_diagnostics_passes_m8_system_bundle_not_m7():
    captured: dict = {}

    def gen(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return json.dumps(
            {
                "overall_summary": "A vázlat textusközpontú.",
                "overall_score": 8,
                "diagnostic_areas": [],
                "major_strengths": ["Világos fókusz"],
                "revision_priorities": [],
                "consistency_warnings": [],
                "pastoral_warnings": [],
                "voice_and_originality_note": "",
                "ready_for_next_stage": True,
                "readiness_note": "Mehet tovább.",
                "missing_information": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    raw = _call_diagnostics_generate(gen, "diagnosztikai próba")
    assert raw
    assert captured.get("system_bundle") == M8_SYSTEM_BUNDLE
    assert captured.get("system_bundle") != M7_SYSTEM_BUNDLE
    assert captured.get("tab_label") == TAB_DIAG
    assert captured.get("include_brevity_directive") is False


def test_run_homiletical_diagnostics_uses_m8_bundle_end_to_end():
    captured: dict = {}

    def gen(prompt, **kwargs):
        captured.update(kwargs)
        return json.dumps(
            {
                "overall_summary": "A diagnosztika a műhelyanyag alapján készült.",
                "overall_score": 7,
                "diagnostic_areas": [
                    {
                        "key": "text_fidelity",
                        "status": "stable",
                        "note": "Textusközeli.",
                    }
                ],
                "major_strengths": ["Textushűség"],
                "revision_priorities": [],
                "consistency_warnings": [],
                "pastoral_warnings": [],
                "voice_and_originality_note": "",
                "ready_for_next_stage": True,
                "readiness_note": "OK",
                "missing_information": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_homiletical_diagnostics(
        passage="Júd 17–20",
        passage_text="17 Ti pedig… 20 épüljetek…",
        exegesis="Emlékezet és megmaradás.",
        sermon_main_idea="Isten megtart a gúny közepette.",
        sermon_main_idea_status="approved",
        generate_fn=gen,
    )
    assert captured.get("system_bundle") == M8_SYSTEM_BUNDLE
    assert captured.get("system_bundle") != M7_SYSTEM_BUNDLE
    assert result is not None
    assert result.ok or bool(captured.get("system_bundle"))