"""LEGACY PRESET CLEANUP + BIBLIAI HÁTTÉR ÖSSZEGZÉS PROFESSZIONALIZÁLÁSA —
a `SECTION_PROMPTS["overview"]` (Bibliai háttér összegzés) átdolgozott
promptjának invariant tesztjei.

Ugyanaz a tesztinfrastruktúra-korlátozás áll fenn, mint
`test_history_prompt_hardening.py`-ban: `app.py` puszta importálása a fő
pytest-folyamatban korrumpálja a Streamlit globális DeltaGenerator-
állapotát, ezért a `SECTION_PROMPTS` szótárat egy elkülönített
alfolyamatban töltjük be.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_WORKER_TEMPLATE = """
import json
import sys

sys.path.insert(0, {root!r})

from app import SECTION_PROMPTS, SECTIONS_WITH_GOOGLE_SEARCH

result = {{
    "overview": SECTION_PROMPTS["overview"],
    "sections_with_google_search": sorted(SECTIONS_WITH_GOOGLE_SEARCH),
}}

with open({out_path!r}, "w", encoding="utf-8") as f:
    json.dump(result, f)
"""


def _load_prompts() -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        script = _WORKER_TEMPLATE.format(root=str(ROOT), out_path=str(out_path))
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"worker alfolyamat-hiba:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
        return json.loads(out_path.read_text(encoding="utf-8"))


_PROMPTS = _load_prompts()


def test_overview_does_not_require_other_workshop_modules_first():
    """A standalone működés: a prompt ne írja elő más modul előzetes elkészültét."""
    overview = _PROMPTS["overview"]
    assert "nem akarnak minden részletes műhelymodulon" in overview
    assert "elsősorban azoknak" in overview


def test_overview_forbids_becoming_mini_commentary():
    overview = _PROMPTS["overview"]
    assert "NE készíts mini-kommentárt, teljes exegézist, teljes teológiai" in overview


def test_overview_uses_the_five_requested_sections_in_order():
    overview = _PROMPTS["overview"]
    headings = ["Fő üzenet", "Kontextus és szerkezet", "Teológiai hangsúlyok", "Lehetséges prédikációs irányok", "Mire figyeljünk?"]
    positions = [overview.index(f"## {h}") for h in headings]
    assert positions == sorted(positions)
    # A régi, most eltávolított 6-szakaszos szerkezet fejlécei ne maradjanak bent.
    assert "## Közvetlen bibliai kontextus" not in overview
    assert "## Irodalmi és teológiai architektúra" not in overview
    assert "## Teológiai hangsúly\n" not in overview
    assert "## Prédikációs irányok" not in overview
    assert "## Figyelmeztetések" not in overview


def test_overview_forbids_categorical_certainty_qualifiers():
    overview = _PROMPTS["overview"]
    assert '"egyértelműen"' in overview
    assert '"biztosan", "kétségtelenül", "nyilvánvalóan"' in overview
    assert "NE fogalmazz kategorikus bizonyossággal" in overview


def test_overview_requires_consistency_across_all_sections_not_just_warnings():
    overview = _PROMPTS["overview"]
    assert "MINDEN szakaszára egyformán vonatkozik" in overview
    assert "legyél\n  következetes a válasz egészében" in overview


def test_overview_forbids_attributing_disputed_agency_to_god_as_subject():
    overview = _PROMPTS["overview"]
    assert "NE fogalmazz úgy sem, hogy Istent teszed meg egy vitatott" in overview
    assert '"A küzdő fél maga Isten."' in overview


def test_overview_forbids_fabricating_confession_references():
    overview = _PROMPTS["overview"]
    assert "NE találj ki konkrét hitvallási hivatkozást" in overview
    assert "Heidelbergi Káté" in overview
    assert "a református hitvallási hagyomány" in overview


def test_overview_requires_hedging_disputed_historical_claims():
    overview = _PROMPTS["overview"]
    assert "ne\n  mutasd be konszenzusként, ha nem az" in overview


def test_overview_forbids_redundancy_across_sections():
    overview = _PROMPTS["overview"]
    assert "REDUNDANCIA TILALOM" in overview
    assert "TELJES KIFEJTÉSSEL csak" in overview


def test_overview_specifies_length_reduction_without_impoverishing_content():
    overview = _PROMPTS["overview"]
    assert "25–30%-kal tömörebb" in overview
    assert "ne legyen sekélyes vagy\nsablonos" in overview


def test_overview_is_not_registered_for_google_search():
    """A standalone gyors-áttekintés maradjon a jelenlegi, nem-kereséses architektúrában."""
    assert "overview" not in _PROMPTS["sections_with_google_search"]
