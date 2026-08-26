"""Phase 5K-B — local staging integration fixes.

Covers:
1) Primary passage-scope constraints in production (+ grounded) prompts
2) NT book resolver path for Lk / ApCsel (and aliases) vs OT/Hebrew
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


_PROMPT_WORKER = """
import json
import sys

sys.path.insert(0, {root!r})

from app import SECTION_PROMPTS
from textus_kb.prompt_composer import _grounded_rules_block

result = {{
    "exegesis": SECTION_PROMPTS["exegesis"],
    "history": SECTION_PROMPTS["history"],
    "grounded_rules": _grounded_rules_block(module="exegesis"),
}}

with open({out_path!r}, "w", encoding="utf-8") as f:
    json.dump(result, f)
"""


def _load_prompts() -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "prompts.json"
        script = _PROMPT_WORKER.format(root=str(ROOT), out_path=str(out_path))
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(out_path.read_text(encoding="utf-8"))


def test_exegesis_prompt_keeps_primary_scope_for_john_4_and_rom_8() -> None:
    prompts = _load_prompts()
    exegesis = prompts["exegesis"]
    assert "ELSŐDLEGES ELEMZÉSI HATÓKÖR" in exegesis
    assert "PRIMÉR" in exegesis
    # Explicit anti-leakage examples for the reported blockers.
    assert "43–54" in exegesis or "43-54" in exegesis
    assert "Róm 8,28–30" in exegesis or "Róm 8,28-30" in exegesis
    assert "teljes 8. fejezetet" in exegesis
    # Contextual references remain allowed.
    assert "KONTEXTUSKÉNT" in exegesis or "kontextus" in exegesis.casefold()


def test_history_prompt_keeps_primary_scope_and_allows_context() -> None:
    prompts = _load_prompts()
    history = prompts["history"]
    assert "ELSŐDLEGES ELEMZÉSI HATÓKÖR" in history
    assert "PRIMÉR" in history
    assert "kontextus" in history.casefold()
    assert "Lk 10" in history


def test_grounded_rules_reinforce_primary_passage_scope() -> None:
    prompts = _load_prompts()
    rules = prompts["grounded_rules"]
    assert "PRIMARY PASSAGE SCOPE" in rules
    assert "context only" in rules.casefold()


@pytest.mark.parametrize(
    ("reference", "expected_status"),
    [
        ("Lk 10,25-37", "loaded"),
        ("Lk 10.25-37", "loaded"),
        ("Luke.10.25-37", "loaded"),
        ("Luke 10,25-37", "loaded"),
        ("ApCsel 2,1-13", "loaded"),
        ("ApCsel 2.1-13", "loaded"),
        ("Acts.2.1-13", "loaded"),
        ("Acts 2,1-13", "loaded"),
        ("Jn 4,1-42", "loaded"),
        ("Mt 5,1-3", "loaded"),
        ("Mk 1,1-8", "loaded"),
        ("Róm 8,28-30", "loaded"),
        ("1Kor 13,1-13", "loaded"),
        ("Lk 10", "needs_verses"),
        ("ApCsel 2", "needs_verses"),
        ("1Móz 1,1", "old_testament"),
        ("Zsolt 23,1", "old_testament"),
    ],
)
def test_nt_ot_resolver_status_matrix(
    reference: str, expected_status: str
) -> None:
    from bible_engine.greek_analysis_ui import greek_reference_status

    assert greek_reference_status(reference) == expected_status


def test_nt_chapter_only_does_not_use_ot_error_message() -> None:
    from streamlit.testing.v1 import AppTest

    from bible_engine.greek_analysis_ui import NT_NEEDS_VERSES_MESSAGE

    def _render() -> None:
        from bible_engine.greek_analysis_ui import render_greek_analysis_block

        render_greek_analysis_block(reference="Lk 10", key_prefix="phase5kb_lk")

    app = AppTest.from_function(_render).run()
    assert not app.exception
    warnings = [w.value for w in app.warning]
    assert any(NT_NEEDS_VERSES_MESSAGE in value for value in warnings)
    assert not any("ószövetségi" in value.casefold() for value in warnings)


def test_apcsel_chapter_only_does_not_use_ot_error_message() -> None:
    from streamlit.testing.v1 import AppTest

    from bible_engine.greek_analysis_ui import NT_NEEDS_VERSES_MESSAGE

    def _render() -> None:
        from bible_engine.greek_analysis_ui import render_greek_analysis_block

        render_greek_analysis_block(reference="ApCsel 2", key_prefix="phase5kb_act")

    app = AppTest.from_function(_render).run()
    assert not app.exception
    warnings = [w.value for w in app.warning]
    assert any(NT_NEEDS_VERSES_MESSAGE in value for value in warnings)
    assert not any("ószövetségi" in value.casefold() for value in warnings)


def test_token_block_routes_nt_and_ot_aliases() -> None:
    """Token-block builder must not send NT abbrs down the Hebrew error path."""
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "tokens.json"
        worker = f"""
import json
import sys
sys.path.insert(0, {str(ROOT)!r})
from app import build_original_language_token_block
result = {{
    "lk": build_original_language_token_block("Lk 10"),
    "apcsel": build_original_language_token_block("ApCsel 2"),
    "gen": build_original_language_token_block("1Móz 1,1"),
    "psa": build_original_language_token_block("Zsolt 23,1"),
}}
with open({str(out_path)!r}, "w", encoding="utf-8") as f:
    json.dump(result, f)
"""
        proc = subprocess.run(
            [sys.executable, "-c", worker],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(out_path.read_text(encoding="utf-8"))

    assert "ószövetségi könyv rövidítése nem azonosítható: Lk" not in result["lk"]
    assert "ószövetségi könyv rövidítése nem azonosítható: ApCsel" not in result["apcsel"]
    assert "verszámot" in result["lk"].casefold() or "görög" in result["lk"].casefold()
    # OT aliases still attempt Hebrew path (not Greek NT messages).
    assert "görög elemzéshez" not in result["gen"].casefold()
    assert "görög elemzéshez" not in result["psa"].casefold()
