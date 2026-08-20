"""RESET 3B-4a — a kortörténet (`history`) prompt kockázatcsökkentő
hardeningje.

A `history` modulhoz JELENLEG nincs külső, ellenőrzött történeti
adatforrás (ld. RESET 3B-4 stratégiai audit) — ez a fázis EZT nem
változtatja meg, kizárólag a promptot szigorítja: a modell ne érezze
kötelességének, hogy minden alcímhez konkrét, de ellenőrizetlen
évszámot/uralkodónevet/régészeti leletet gyártson.

FONTOS TESZTINFRASTRUKTÚRA-MEGJEGYZÉS — ugyanaz a korlátozás, mint
`tests/test_original_language_token_block.py`-ban és `tests/test_
exegesis_original_language_grounding.py`-ban dokumentálva: `app.py` egy
tiszta Streamlit-szkript, aminek puszta importálása (`from app import
...`) a FŐ pytest-folyamatban korrumpálja a Streamlit globális
DeltaGenerator-állapotát. Itt nincs szükség `st.session_state`-re (csak a
statikus `SECTION_PROMPTS` szótár TARTALMÁT vizsgáljuk), ezért elég a
`test_original_language_token_block.py` EGYSZERŰBB, bare `python -c`
alfolyamat-mintája — AppTest nem kell.
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
    "history": SECTION_PROMPTS["history"],
    "exegesis": SECTION_PROMPTS["exegesis"],
    "theology": SECTION_PROMPTS["theology"],
    "overview": SECTION_PROMPTS["overview"],
    "sections_with_google_search": sorted(SECTIONS_WITH_GOOGLE_SEARCH),
}}

with open({out_path!r}, "w", encoding="utf-8") as f:
    json.dump(result, f)
"""


def _load_prompts() -> dict:
    """`SECTION_PROMPTS`/`SECTIONS_WITH_GOOGLE_SEARCH` beolvasása egy
    elkülönített alfolyamatban (ld. modul docstring)."""
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


# A modul szintjén egyszer töltjük be -- minden teszt ugyanazt a
# beolvasott promptkészletet használja, nem indítunk felesleges
# alfolyamatokat tesztenként.
_PROMPTS = _load_prompts()


# =============================================================================
# 1-4. Új bizonytalanság-fegyelmi szabályok jelen vannak
# =============================================================================


def test_1_history_prompt_forbids_inventing_uncertain_specifics():
    history = _PROMPTS["history"]
    assert (
        "NE találj ki helyette hihetően hangzó, de ellenőrizetlen\n"
        "részletet" in history
    )
    assert "A hiányzó részlet MINDIG jobb" in history


def test_2_history_prompt_explicitly_allows_more_general_phrasing():
    history = _PROMPTS["history"]
    assert "fogalmazz ÁLTALÁNOSABBAN" in history
    assert (
        '(pl. "a korszakra jellemző\npolitikai instabilitás" egy konkrét, '
        "bizonytalan uralkodó-név helyett)" in history
    )


def test_3_history_prompt_explicitly_allows_omitting_a_detail():
    history = _PROMPTS["history"]
    assert "egyszerűen HAGYD KI azt a konkrétumot" in history


def test_4_history_prompt_does_not_force_manufactured_archaeological_interest():
    history = _PROMPTS["history"]
    assert 'NE gyárts mesterséges régészeti "érdekességet"' in history
    assert "Egyetlen alcím sem kötelezően" in history
    assert "lehet RÖVID, akár\n1-2 mondatos is" in history


def test_uncertainty_disclosure_is_framed_as_required_discipline_not_weakness():
    history = _PROMPTS["history"]
    assert (
        "A BIZONYTALANSÁG JELZÉSE NEM GYENGESÉG, HANEM KÖTELEZŐ SZAKMAI "
        "FEGYELEM" in history
    )


def test_biztos_valoszinu_vitatott_labeling_is_not_mandatory_everywhere():
    history = _PROMPTS["history"]
    assert (
        "ez NEM azt jelenti, hogy minden bekezdést vagy mondatot\n"
        "külön címkével kellene ellátnod" in history
    )
    assert "egyszerűen állítsd, címkézés nélkül" in history


def test_strong_certainty_language_is_restricted_to_textbook_level_facts():
    history = _PROMPTS["history"]
    assert (
        'NE HASZNÁLJ olyan erős, tényként ható megfogalmazást ("dokumentált",\n'
        '"biztosan", "a régészet bizonyítja"' in history
    )
    assert "alaptankönyvi szinten, vitán felül ismert" in history


# =============================================================================
# 5-7. A meglévő szerkezet/tiltások változatlanok
# =============================================================================


def test_5_all_six_existing_subheadings_are_unchanged():
    history = _PROMPTS["history"]
    for heading in (
        "## Történelmi háttér",
        "## Politikai és vallási környezet",
        "## Társadalmi és gazdasági viszonyok",
        "## Földrajzi és régészeti háttér",
        "## Korabeli szokások",
        "## Korabeli élethelyzet",
    ):
        assert heading in history, heading
    # Pontosan hat -- nincs új, hetedik alcím.
    assert history.count("\n## ") == 6


def test_6_greek_hebrew_prohibition_still_present():
    history = _PROMPTS["history"]
    assert "görög vagy héber szó, kifejezés idézése vagy elemzése" in history


def test_7_homiletical_application_prohibition_still_present():
    history = _PROMPTS["history"]
    assert (
        "homiletikai, alkalmazási vagy \"kövessük Krisztus példáját\" jellegű"
        in history
    )
    assert "Ne vonj le következtetést arról, mire használható ez a prédikációban" in history


# =============================================================================
# 8. History továbbra sem kap Google Search-et
# =============================================================================


def test_8_history_still_has_no_google_search():
    assert "history" not in _PROMPTS["sections_with_google_search"]
    assert _PROMPTS["sections_with_google_search"] == ["actualization"]


# =============================================================================
# 9. Más szekció promptjai változatlanok
# =============================================================================


def test_9_exegesis_prompt_unchanged_by_this_phase():
    exegesis = _PROMPTS["exegesis"]
    # A RESET 3B-3-ban bevezetett grounding-szöveg megvan, de a history
    # hardening ehhez a modulhoz NEM adott hozzá semmit.
    assert "GÖRÖG/HÉBER HIVATKOZÁS SZIGORÚ HATÁRA" in exegesis
    assert "BIZONYTALANSÁG-FEGYELEM (KÖTELEZŐ, RÉSZLETES SZABÁLY" not in exegesis


def test_9_theology_and_overview_prompts_have_no_history_hardening_text():
    for key in ("theology", "overview"):
        prompt = _PROMPTS[key]
        assert "BIZONYTALANSÁG-FEGYELEM (KÖTELEZŐ, RÉSZLETES SZABÁLY" not in prompt
        assert 'NE gyárts mesterséges régészeti "érdekességet"' not in prompt
