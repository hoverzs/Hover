"""LOCAL MANUAL QA FIX, Phase D — az `original_text`/`exegesis` promptok
tartalmi minőség-finomítása, az `1Móz 32,23-32` kézi teszt konkrét
megfigyelései alapján:

  - `original_text`: ismétlődés-tilalom kiemelt szavak között, tömörségi
    elvárás (1-3 mondat/szó), és tiltás arra, hogy egyetlen szó
    jelentéséből aránytalanul nagy teológiai/exegetikai következtetést
    vonjon le a modell.
  - `exegesis`: a nyers, technikai többkomponensű Strong-kód (pl.
    "H9005+H9033") NE kerüljön a végleges szövegbe — csak egyetlen,
    olvasható azonosító; és a több legitim olvasatú azonosítási/
    teológiai kérdések (pl. egy alak isteni kiléte, névváltoztatás
    súlya, "győzelem"-értelmezés) az "Értelmezési kérdések" alcím alatt,
    LEHETSÉGES olvasatként jelenjenek meg, ne egyetlen bizonyos tényként
    valahol máshol.

FONTOS TESZTINFRASTRUKTÚRA-MEGJEGYZÉS — ugyanaz a korlátozás, mint
`tests/test_history_prompt_hardening.py`-ban dokumentálva: `app.py`
importálása a FŐ pytest-folyamatban korrumpálja a Streamlit globális
DeltaGenerator-állapotát, ezért bare `python -c` alfolyamatban futunk
(nincs szükség `st.session_state`-re, csak statikus prompt-szövegre).
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

from app import SECTION_PROMPTS, ORIGINAL_TEXT_BASE_PROMPT

result = {{
    "exegesis": SECTION_PROMPTS["exegesis"],
    "history": SECTION_PROMPTS["history"],
    "theology": SECTION_PROMPTS["theology"],
    "original_text_base": ORIGINAL_TEXT_BASE_PROMPT,
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
# original_text — ismétlődés-tilalom, tömörség, arányos következtetés
# =============================================================================


def test_original_text_forbids_repeating_the_same_point_across_words():
    prompt = _PROMPTS["original_text_base"]
    assert (
        "Kerüld, hogy UGYANAZT a gondolatot több kiemelt\nszó alatt is "
        "megismételd" in prompt
    )


def test_original_text_asks_for_concise_per_word_treatment():
    prompt = _PROMPTS["original_text_base"]
    assert (
        "Egy\nkiválasztott szóhoz ALAPÉRTELMEZETTEN LEGFELJEBB 3 rövid "
        "mondat tartozik." in prompt
    )
    assert "4. mondat KIVÉTELESEN megengedett" in prompt


def test_original_text_forbids_overreaching_conclusions_from_a_single_word():
    prompt = _PROMPTS["original_text_base"]
    assert (
        "NE tulajdoníts nagy, önálló teológiai vagy exegetikai "
        "következtetést\nPUSZTÁN egy szó jelentéséből" in prompt
    )


def test_original_text_separates_form_lemma_meaning_function_relevance():
    prompt = _PROMPTS["original_text_base"]
    assert (
        "(1) szóalak + lemma + alapjelentés EGY\nmondatban; (2) mit végez "
        "EBBEN a mondatban (funkció) EGY mondatban; (3)\nlegfeljebb EGY "
        "rövid mondat exegetikai jelentőség" in prompt
    )


def test_original_text_forbids_flat_undecided_identity_claims():
    prompt = _PROMPTS["original_text_base"]
    assert "VITATOTT IDENTITÁSI KÉRDÉS NEM DÖNTHETŐ EL NYELVI ESZKÖZZEL" in prompt
    assert '"az isteni lény", "Isten\nitt...", "mint isteni jelenlét"' in prompt
    assert "NEM teológiai identitásdöntés" in prompt


def test_original_text_forbids_over_etymologizing_from_cognate_roots():
    prompt = _PROMPTS["original_text_base"]
    assert "NE TÚLOZD EL A SZÓETIMOLÓGIÁT" in prompt
    assert "rokongyökök, hangzásbeli asszociációk" in prompt
    assert '"fejedelmi módon", "uralkodóként"' in prompt


def test_original_text_five_word_cap_and_other_rules_unchanged():
    prompt = _PROMPTS["original_text_base"]
    assert "LEGFELJEBB 5 szót vagy kifejezést emelhetsz ki." in prompt
    assert "TILOS:" in prompt
    assert "angol nyelvű jelentés-megadás vagy gloss" in prompt


# =============================================================================
# exegesis — olvasható Strong-azonosító, technikai összetett kód tiltása
# =============================================================================


def test_exegesis_forbids_raw_multi_component_strong_codes():
    prompt = _PROMPTS["exegesis"]
    assert (
        'nyers, technikai összetett kódja (pl. "H9005+H9033" vagy más '
        '"+"-szal' in prompt
    )
    assert "NE másold be őket a végleges szövegbe." in prompt


def test_exegesis_allows_a_single_readable_strong_id():
    prompt = _PROMPTS["exegesis"]
    assert (
        'egyetlen, tiszta azonosító (pl. "G0025"), SOSEM a token-lista'
        in prompt
    )


# =============================================================================
# exegesis — több legitim olvasatú kérdések az Értelmezési kérdések alá
# =============================================================================


def test_exegesis_pushes_disputed_identification_questions_into_dedicated_heading():
    prompt = _PROMPTS["exegesis"]
    assert (
        "IDE tartozik minden olyan\nazonosítási vagy teológiai kérdés, "
        "ahol a szakirodalomban több elfogadott\nolvasat létezik (pl. "
        "egy titokzatos alak isteni/angyali kiléte, egy\nnévváltoztatás "
        'pontos teológiai súlya, egy küzdelem "győzelemként" való'
        in prompt
    )


def test_exegesis_requires_presenting_as_possible_readings_not_a_single_fact():
    prompt = _PROMPTS["exegesis"]
    assert (
        "ezeket mint LEHETSÉGES olvasatokat mutasd be" in prompt
    )
    assert "NE egyetlen, magától értetődő\ntényként" in prompt


def test_exegesis_forbids_named_identity_terms_outside_dedicated_heading():
    prompt = _PROMPTS["exegesis"]
    assert (
        'az\n"angyal", "teofánia", "isteni jelenlét", "pre-inkarnációs '
        'Krisztus" (vagy\nhasonló azonosító) EGYIKE se jelenjen meg biztos, '
        "eldöntött tényként a\nMűfaj és szerkezet, a Kulcsszavak és "
        "kulcskifejezések, vagy a Nyelvtani és\nszerkezeti megfigyelések "
        "alcím alatt" in prompt
    )
    assert (
        "nem\nazt jelenti, hogy minden teológiai állítást ide kellene "
        "zárni" in prompt
    )


def test_exegesis_genre_section_avoids_asserting_disputed_reading():
    prompt = _PROMPTS["exegesis"]
    assert (
        'NE a vitatott olvasat nevét (pl. NE nevezd flatly "teofániának"'
        in prompt
    )


def test_exegesis_grammar_section_defers_identity_question():
    prompt = _PROMPTS["exegesis"]
    assert (
        'NE nevezd\n"isteni jelenlétnek", és NE beszélj "isteni '
        'szuverenitásáról" vagy hasonló' in prompt
    )
    assert (
        '"a későbbi\nversek egyértelműen isteni jelenlétre utalnak", '
        'vagy hogy egy cselekedet\n"az isteni szuverenitás megnyilvánulása"'
        in prompt
    )
    assert '— sem nyíltan, sem burkoltan.' in prompt


def test_exegesis_interpretive_questions_forbids_self_contradiction():
    prompt = _PROMPTS["exegesis"]
    assert "BELSŐ ÖNELLENTMONDÁS TILOS" in prompt
    assert (
        '"a küzdő\nfél biztosan Isten volt" (ez már értelmezési döntés '
        "— TILOS)" in prompt
    )
    assert (
        '"Jákób a találkozást Istennel való találkozásként értelmezi"'
        in prompt
    )


def test_exegesis_forbids_repeating_the_same_insight_across_headings():
    prompt = _PROMPTS["exegesis"]
    assert "ALCÍMEK KÖZÖTTI ISMÉTLÉS TILOS" in prompt
    assert (
        '"a győzelem paradox módon a sebezhetőségen és a függésen keresztül\n'
        'valósul meg"' in prompt
    )


def test_exegesis_forbids_uncertain_confession_numbering_in_preaching_value():
    prompt = _PROMPTS["exegesis"]
    assert "NE hivatkozz konkrét hitvallási" in prompt
    assert "nincs ellenőrzött\nhitvallási adatforrásod" in prompt


def test_exegesis_allows_unnumbered_confession_content_reference():
    prompt = _PROMPTS["exegesis"]
    assert "TARTALMÁRA/TANÍTÁSÁRA szám nélkül utalhatsz" in prompt


def test_exegesis_headings_and_structure_unchanged():
    prompt = _PROMPTS["exegesis"]
    for heading in (
        "## Műfaj és szerkezet",
        "## Kontextus",
        "## Kulcsszavak és kulcskifejezések",
        "## Nyelvtani és szerkezeti megfigyelések",
        "## Párhuzamos bibliai helyek",
        "## Értelmezési kérdések",
        "## Prédikációs haszon",
    ):
        assert heading in prompt, heading
    assert "GÖRÖG/HÉBER HIVATKOZÁS SZIGORÚ HATÁRA" in prompt


# =============================================================================
# Nincs átszivárgás más szekcióba
# =============================================================================


def test_no_leakage_into_history_or_theology_prompts():
    for key in ("history", "theology"):
        prompt = _PROMPTS[key]
        assert "H9005+H9033" not in prompt
        assert "IDE tartozik minden olyan" not in prompt
