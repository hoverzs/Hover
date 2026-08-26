"""Phase 5M: historical-context overclaim calibration (policy + prompt)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.prompt_composer import (
    DRY_RUN_PRODUCTION_STUB,
    compose_grounded_prompt,
)
from textus_kb.retrieval import retrieve

ROOT = Path(__file__).resolve().parents[1]

_WORKER = """
import json, sys
sys.path.insert(0, {root!r})
from app import SECTION_PROMPTS
with open({out!r}, "w", encoding="utf-8") as f:
    json.dump({{"history": SECTION_PROMPTS["history"]}}, f)
"""


def _load_history_prompt() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        proc = subprocess.run(
            [sys.executable, "-c", _WORKER.format(root=str(ROOT), out=str(out))],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(out.read_text(encoding="utf-8"))["history"]


_HISTORY = _load_history_prompt()

WATCHLIST_PASSAGES = (
    ("John.4.1-42", "historical_context"),
    ("Luke.10.25-37", "historical_context"),
    ("Acts.2.1-13", "historical_context"),
    ("Rom.8.28-30", "historical_context"),
)


def _compose(passage: str, module: str):
    profile = PROFILE_HISTORICAL if module == "historical_context" else PROFILE_EXEGESIS
    packet = retrieve(passage)
    context = build_context_from_evidence(packet, profile)
    preview = compose_grounded_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        canonical_passage=packet.passage_canonical,
        module=module,
        context_packet=context,
    )
    return packet, context, preview


_CONFIDENT_OVERCLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "procurator_office",
        re.compile(r"(?i)\b(procurator|prokurátor)\w*\b"),
    ),
    (
        "blood_road_nickname",
        re.compile(r"(?i)\b(blood\s*road|vérút)\b"),
    ),
    (
        "modern_medical_framing",
        re.compile(r"(?i)\b(antiseptic|disinfectant|fertőtlenítő|antiseptikus)\b"),
    ),
    (
        "religio_licita_as_status",
        re.compile(r"(?i)religio\s+licita"),
    ),
)


def flag_confident_historical_overclaims(text: str) -> list[str]:
    """Heuristic watchlist flags for regression fixtures (not a full validator)."""
    hits: list[str] = []
    body = text or ""
    for name, pattern in _CONFIDENT_OVERCLAIM_PATTERNS:
        if pattern.search(body):
            hits.append(name)
    if re.search(
        r"(?i)(tilos|forbidden|nem volt szabad).{0,40}(samarit|szamarit)",
        body,
    ) and not re.search(
        r"(?i)(egyes|feltételez|lehet|vitatott|nem mindig)",
        body,
    ):
        hits.append("categorical_samaritan_prohibition")
    if re.search(
        r"(?i)(délben|noon).{0,80}(marginal|kirekeszt|szégyen)",
        body,
    ) and not re.search(
        r"(?i)(egyes kutatók|feltételez|lehet|utalhat)",
        body,
    ):
        hits.append("noon_as_established_marginalization")
    return hits


def test_production_history_has_calibration_block() -> None:
    assert "KONKRÉT TÖRTÉNETI ÁLLÍTÁSOK KALIBRÁLÁSA (KÖTELEZŐ)" in _HISTORY
    assert "szövegben adott tényt a történeti rekonstrukciótól" in _HISTORY
    assert "modern orvosi terminológiát" in _HISTORY
    assert "kalibrált" in _HISTORY


def test_production_history_watchlist_examples_present() -> None:
    assert "prokurátor" in _HISTORY and "prefektus" in _HISTORY
    assert "Vérút" in _HISTORY and "Blood Road" in _HISTORY
    assert "fertőtlenítő" in _HISTORY
    assert "religio licita" in _HISTORY
    assert "Tóra-adás" in _HISTORY


def test_grounded_historical_prompts_include_calibration() -> None:
    for passage, module in WATCHLIST_PASSAGES:
        _packet, context, preview = _compose(passage, module)
        prompt = preview.composed_prompt
        assert "=== HISTORICAL CLAIM CALIBRATION ===" in prompt, passage
        assert "need direct evidence support" in prompt
        assert "disinfectant/antiseptic" in prompt
        assert preview.success
        assert preview.budget_ok
        assert context.profile == "historical_context"


def test_rom8_still_gets_limited_coverage_guard() -> None:
    _packet, context, preview = _compose("Rom.8.28-30", "historical_context")
    assert context.selection_stats.get("historical_coverage_status") == "limited"
    assert "=== LIMITED HISTORICAL COVERAGE ===" in preview.composed_prompt
    assert "=== HISTORICAL CLAIM CALIBRATION ===" in preview.composed_prompt


def test_exegesis_does_not_get_historical_calibration() -> None:
    _packet, _context, preview = _compose("John.4.1-42", "exegesis")
    assert "=== HISTORICAL CLAIM CALIBRATION ===" not in preview.composed_prompt


def test_heuristic_flags_known_before_examples() -> None:
    before_samples = {
        "john_procurator": "Júdeát procuratorok (helytartók) révén kormányozták.",
        "luke_medical": (
            "az olaj nyugtató és fertőtlenítő, a bor pedig fertőtlenítő hatása miatt."
        ),
        "luke_blood_road": "A Jeruzsálem–Jerikó út a Vérút néven volt ismert.",
        "rom_religio": "A zsidóság religio licita státuszt élvezett.",
    }
    for label, text in before_samples.items():
        assert flag_confident_historical_overclaims(text), label


def test_heuristic_allows_calibrated_after_examples() -> None:
    after_samples = (
        "Júdeát római helytartók igazgatták; a pontos korabeli hivatali "
        "megnevezés szakmailag vitatott.",
        "Olajat és bort használtak sebek ápolására; ezt ne írd át modern "
        "orvosi kategóriákba.",
        "A Jeruzsálem–Jerikó út veszélyes lehetett a korabeli utazók számára; "
        "népszerű későbbi beceneveket ne állíts történeti tényként.",
        "A keresztény közösség jogi helyzete Rómában bizonytalan volt; "
        "formális jogi státuszkategóriát ne feltételezz alátámasztás nélkül.",
        "Egyes kutatók szerint a délben történő vízmerítés társadalmi "
        "marginalizációra utalhat, de ez nem a szöveg explicit állítása.",
        "Zsidók és samaritánusok között feszültség volt; a kapcsolat nem "
        "volt minden körülmény között egyértelműen tiltott.",
    )
    for text in after_samples:
        assert flag_confident_historical_overclaims(text) == [], text
