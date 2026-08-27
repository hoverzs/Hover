"""RESET 3D-2 — a teológia ("theology") prompt kockázatcsökkentő
hardeningje.

A `theology` prompt grounded és ungrounded módban is igaz marad: konkrét
teológust, művet, hitvallást, kátészámot vagy bibliográfiai adatot csak
akkor nevezhet meg, ha a rendszer által adott ellenőrzött forráskontextus
ezt ténylegesen tartalmazza. A modell ne gyártson ellenőrizetlen
Heidelbergi Káté kérdésszámot, hitvallási fejezethivatkozást, szó szerinti
idézetet vagy teológus-attribúciót.

FONTOS TESZTINFRASTRUKTÚRA-MEGJEGYZÉS — ugyanaz a korlátozás, mint
`tests/test_original_language_token_block.py`-ban és `tests/test_
history_prompt_hardening.py`-ban dokumentálva: `app.py` egy tiszta
Streamlit-szkript, aminek puszta importálása (`from app import ...`) a
FŐ pytest-folyamatban korrumpálja a Streamlit globális DeltaGenerator-
állapotát. Itt nincs szükség `st.session_state`-re (csak a statikus
`SECTION_PROMPTS` szótár TARTALMÁT vizsgáljuk), ezért elég a
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
    "theology": SECTION_PROMPTS["theology"],
    "exegesis": SECTION_PROMPTS["exegesis"],
    "history": SECTION_PROMPTS["history"],
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
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=str(ROOT), timeout=120,
        )
        assert proc.returncode == 0, (
            f"worker alfolyamat-hiba:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
        return json.loads(out_path.read_text(encoding="utf-8"))


_PROMPTS = _load_prompts()


# =============================================================================
# 1-4. Az uj bizonytalansag-fegyelmi szabalyok jelen vannak
# =============================================================================


def test_1_theology_prompt_forbids_inventing_catechism_question_numbers():
    # LOCAL MANUAL QA FIX (2026-08-21): a manuális teszt (1Móz 32,23-32)
    # kimutatta, hogy a "csak ha nagy biztonsággal rendelkezel" feltételes
    # szabály NEM volt elég szigorú -- a modell tovább is konkrét HK-
    # kérdésszámot generált. A szabály mostantól ALAPÉRTELMEZETT TILTÁS,
    # nem feltételes engedély.
    theology = _PROMPTS["theology"]
    assert (
        "ALAPÉRTELMEZETTEN NE adj meg konkrét hitvallási\nhivatkozást — "
        "Heidelbergi Káté kérdésszámot, II. Helvét Hitvallás"
        in theology
    )
    assert (
        'saját emlékezetből felidézett szám ÉPP OLYAN ellenőrizetlen, '
        "mint egy\nkitalált." in theology
    )


def test_2_theology_prompt_forbids_uncertain_confession_chapter_reference():
    theology = _PROMPTS["theology"]
    assert (
        "II. Helvét Hitvallás\nfejezetszámát vagy dokumentumpontját"
        in theology
    )
    assert "ellenőrzött forráskontextusban szerepel" in theology
    assert "NINCS külső, ellenőrzött teológiai adatforrás" not in theology


def test_3_theology_prompt_forbids_fabricated_quotes():
    theology = _PROMPTS["theology"]
    assert "kvázi-szó\nszerinti idézetet" in theology
    assert "hamis idézetet a szószéken" in theology


def test_4_theology_prompt_forbids_uncertain_theologian_attribution():
    theology = _PROMPTS["theology"]
    assert (
        "Ugyanez vonatkozik konkrét teológusoknak vagy reformátoroknak "
        "(pl.\nKálvin, Luther, Barth vagy más teológus) tulajdonított "
        "állításokra: NE\nrendelj hozzájuk konkrét nézetet csak azért, "
        "hogy tekintélyt kölcsönözz\naz érvelésnek." in theology
    )
    assert "mondd el a teológiai gondolatot NÉV NÉLKÜL" in theology


# =============================================================================
# 5. Altalanosabb reformatus megfogalmazas explicit megengedett
# =============================================================================


def test_5_theology_prompt_explicitly_allows_more_general_phrasing():
    theology = _PROMPTS["theology"]
    assert (
        "Csak a REFORMÁTUS HITVALLÁSI HAGYOMÁNY TARTALMÁT/TANÍTÁSÁT\n"
        "fogalmazd meg, szám vagy idézet nélkül" in theology
    )
    assert (
        '(pl. "a református hitvallási\nhagyomány hangsúlyozza..." '
        "egy konkrét kérdésszám vagy fejezethivatkozás\nhelyett)"
        in theology
    )


# =============================================================================
# 6. Vitatott dogmatikai allaspont nem jelenhet meg egyetlen biztos
#    reformatus allaspontkent
# =============================================================================


def test_6_theology_prompt_forbids_presenting_contested_view_as_the_reformed_position():
    theology = _PROMPTS["theology"]
    assert (
        "Különböztesd meg világosan: (1) a textusból közvetlenül "
        "következő\nteológiai hangsúlyt, (2) a református hagyomány "
        "általánosan elfogadott\nértelmezését, és (3) egy lehetséges — "
        "nem egyedüli — dogmatikai olvasatot." in theology
    )
    assert (
        'mintha az volna az EGYETLEN, magától értetődő "református '
        'álláspont".' in theology
    )


# =============================================================================
# 7. Konkretum kihagyasa explicit megengedett
# =============================================================================


def test_7_theology_prompt_explicitly_allows_omitting_a_detail():
    # LOCAL MANUAL QA FIX: a szabály mostantól nem "generalizálj VAGY
    # hagyd ki" választást ad, hanem egyenesen elhagyja a konkrét
    # hivatkozást (szám/idézet) alapból -- a hiányzó konkrétum explicit
    # jobbnak van jelölve a bizonytalan adatnál.
    theology = _PROMPTS["theology"]
    assert "fogalmazd meg, szám vagy idézet nélkül" in theology
    assert "A hiányzó hivatkozás MINDIG jobb,\nmint" in theology


def test_uncertainty_disclosure_is_framed_as_required_discipline_not_weakness():
    theology = _PROMPTS["theology"]
    assert (
        "A BIZONYTALANSÁG JELZÉSE NEM GYENGESÉG, HANEM KÖTELEZŐ SZAKMAI "
        "FEGYELEM" in theology
    )


# =============================================================================
# 8. A meglevo theology szerkezet valtozatlan
# =============================================================================


def test_8_existing_theology_structure_is_unchanged():
    theology = _PROMPTS["theology"]
    assert "# TEOLÓGIA — REFORMÁTUS ÉRZÉKENYSÉGGEL" in theology
    assert "Szakmai vízió:" in theology
    assert (
        "Emeld ki a textusban TÉNYLEGESEN jelenlévő teológiai "
        "súlypontokat" in theology
    )
    assert "Kerüld a latin és szakteológiai terminusok elsődleges használatát" in theology
    for bullet in (
        "- Isten-arculat:",
        "- Emberkép:",
        "- Isten üdvözítő munkája:",
        "- Krisztusra mutatás:",
        "- Hitvallásos kapcsolódás:",
    ):
        assert bullet in theology, bullet
    # Pontosan öt szempont -- nincs uj, hatodik kategoria.
    assert theology.count("\n- ") == 5
    assert (
        "A cél a tömör teológiai tisztánlátás: 2-3 valóban kibontott "
        "szempont," in theology
    )


# =============================================================================
# 9. Exegezis / eredeti nyelvi hatar valtozatlan
# =============================================================================


def test_9_theology_prompt_still_has_no_original_language_content():
    theology = _PROMPTS["theology"]
    assert "görög" not in theology.lower()
    assert "héber" not in theology.lower()
    assert "eredeti nyelvi" not in theology.lower()


def test_9_exegesis_prompt_unaffected_by_theology_hardening():
    exegesis = _PROMPTS["exegesis"]
    assert "GÖRÖG/HÉBER HIVATKOZÁS SZIGORÚ HATÁRA" in exegesis
    assert "BIZONYTALANSÁG-FEGYELEM (KÖTELEZŐ SZABÁLY" not in exegesis


# =============================================================================
# 10. Homiletikai hatar valtozatlan (a theology promptnak sosem volt
#     kulon "SZIGORUAN TILOS" blokkja -- ez most sem valtozott)
# =============================================================================


def test_10_theology_prompt_still_has_no_homiletical_application_content():
    theology = _PROMPTS["theology"]
    assert "igehirdetésben" not in theology.lower()
    assert "prédikációban" not in theology.lower()
    assert "kövessük" not in theology.lower()


# =============================================================================
# 11. History tovabbra sem kap Google Search-et -- es theology sem
# =============================================================================


def test_11_theology_still_has_no_google_search():
    assert "theology" not in _PROMPTS["sections_with_google_search"]
    assert _PROMPTS["sections_with_google_search"] == ["actualization"]


# =============================================================================
# 12. Mas section promptok valtozatlanok
# =============================================================================


def test_12_history_and_overview_prompts_have_no_theology_hardening_text():
    for key in ("history", "overview"):
        prompt = _PROMPTS[key]
        assert "BIZONYTALANSÁG-FEGYELEM (KÖTELEZŐ SZABÁLY" not in prompt
        assert "Kálvin, Luther, Barth" not in prompt


def test_12_history_prompt_retains_its_own_reset_3b4a_hardening():
    # Nem szabad, hogy a theology-hardening veletlenul felulirja vagy
    # duplikalja a history sajat, korabbi (RESET 3B-4a) hardeningjet.
    history = _PROMPTS["history"]
    assert (
        "A BIZONYTALANSÁG JELZÉSE NEM GYENGESÉG, HANEM KÖTELEZŐ SZAKMAI "
        "FEGYELEM" in history
    )
    assert history.count("BIZONYTALANSÁG-FEGYELEM") == 1
