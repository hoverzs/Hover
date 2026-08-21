"""RESET 3B-6 — a `bible_engine/original_language_grounding_check.py`
determinisztikus, non-blocking post-hoc grounding cross-check tesztjei,
plusz az `original_text`/`exegesis` `app.py`-integráció.

Két rész:

  1. A `bible_engine.original_language_grounding_check` modul MAGA
     Streamlit-független (ld. a modul saját docstringjét), ezért
     KÖZVETLENÜL, subprocess-izoláció NÉLKÜL importálható és
     tesztelhető a fő pytest-folyamatban.

  2. Az `app.py`-integráció (`generate_section("exegesis")` és
     `render_original_text_panel()` bekötése) — ugyanaz a korlátozás,
     mint `tests/test_original_language_token_block.py`-ban és
     `tests/test_exegesis_original_language_grounding.py`-ban
     dokumentálva: `app.py` importálása a FŐ pytest-folyamatban
     korrumpálja a Streamlit globális állapotát, ezért ezek a tesztek
     egy VALÓDI ideiglenes .py fájlon keresztül, AppTest-alapú
     alfolyamatban futnak. A generálás API-hívását `app.generate_text`
     monkeypatch-eléssel mockoljuk — nincs valódi hálózati hívás.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import pytest

from bible_engine.original_language_grounding_check import (
    GroundingCategory,
    build_passage_vocabulary,
    check_original_language_grounding,
)

ROOT = Path(__file__).resolve().parents[1]


def _categories(text: str, igehely: str) -> list[GroundingCategory]:
    return [w.category for w in check_original_language_grounding(text, igehely)]


# =============================================================================
# 1-4. Valódi passzus-adat -> nincs warning
# =============================================================================


def test_1_real_greek_passage_surface_form_has_no_warning():
    # ἠγάπησεν (Jn 3,16, agapao) valodi szoalak.
    text = "A szoveg itt az ἠγάπησεν szot hasznalja."
    assert _categories(text, "Jn 3:16") == []


def test_2_real_hebrew_passage_surface_form_has_no_warning():
    # בראשית (1Moz 1:1) valodi szoalak (accent-mentes forma).
    text = "A kezdo szo itt בראשית, azaz kezdetben."
    assert _categories(text, "1Moz 1:1") == []


def test_3_real_lemma_citation_has_no_warning():
    # lemma (agapao), nem a ragozott szoalak.
    text = "A lemma ἀγαπάω, ami szeretetet jelent."
    assert _categories(text, "Jn 3:16") == []


def test_4_real_strong_id_citation_has_no_warning():
    text = "A Strong-szam G0025 a passzus egyik tokenjehez tartozik."
    assert _categories(text, "Jn 3:16") == []


# =============================================================================
# 5-6. Mas passzusbol valo, VALODI nyelvi adat -> GLOBAL_OTHER_PASSAGE
# =============================================================================


def test_5_greek_word_from_different_nt_passage_is_global_other_passage():
    # logos (G3056) nem szerepel Jn 3,16-ban.
    text = "Emliti a λόγος szot is, ami mas osszefuggesben all."
    categories = _categories(text, "Jn 3:16")
    assert categories == [GroundingCategory.GLOBAL_OTHER_PASSAGE]


def test_6_hebrew_word_from_different_ot_passage_is_global_other_passage():
    # Egy 1Moz 1:1-ben nem szereplo, de valodi heber szo (pl. melek - kiraly).
    text = "Emliti a מֶלֶךְ szot is."
    categories = _categories(text, "1Moz 1:1")
    assert GroundingCategory.GLOBAL_OTHER_PASSAGE in categories


# =============================================================================
# 7-8. Ismeretlen (kitalalt) token -> UNKNOWN
# =============================================================================


def test_7_unknown_greek_token_is_unknown():
    text = "A szoveg egy kitalalt szot hasznal: ξψζθφ."
    assert _categories(text, "Jn 3:16") == [GroundingCategory.UNKNOWN]


def test_8_unknown_hebrew_token_is_unknown():
    text = "A szoveg egy kitalalt heber szot hasznal: צץקרשת."
    assert _categories(text, "1Moz 1:1") == [GroundingCategory.UNKNOWN]


# =============================================================================
# 9. Ervenytelen Strong-ID -> INVALID_STRONG_ID
# =============================================================================


def test_9_invalid_strong_ids_are_flagged_separately():
    text = "Strong szamok: G30000 es H12 ervenytelen formatumuak."
    warnings = check_original_language_grounding(text, "Jn 3:16")
    by_value = {w.value: w.category for w in warnings}
    assert by_value["G30000"] == GroundingCategory.INVALID_STRONG_ID
    assert by_value["H12"] == GroundingCategory.INVALID_STRONG_ID


# =============================================================================
# 10-11. Normalizalas: ekezet/nikud-elteres NEM okoz hamis warningot
# =============================================================================


def test_10_greek_accent_difference_does_not_cause_false_warning():
    # 'theos' (G2316) ekezet NELKUL -- a stripped fallback-nek talalnia kell.
    accentless = unicodedata.normalize(
        "NFC", "".join(ch for ch in unicodedata.normalize("NFD", "θεός") if not unicodedata.combining(ch))
    )
    text = f"A szo itt {accentless}, ekezet nelkul irva."
    assert _categories(text, "Jn 3:16") == []


def test_11_hebrew_nikud_difference_does_not_cause_false_warning():
    # A passzus tokenjenek nikud NELKULI alakja is talalnia kell.
    text = "A szo itt בראשית, nikud nelkul irva."
    assert _categories(text, "1Moz 1:1") == []


# =============================================================================
# 12. Sofit-elteres NEM kerul mesterségesen normalizálásra
# =============================================================================


def test_12_sofit_variant_is_not_silently_folded():
    # Helyes: 'השמים' (vegen sofit mem ם). 1Moz 1,1 valodi tokenje.
    correct = "השמים"
    wrong = "השמימ"  # vegen KOZONSEGES mem מ, nem sofit
    assert _categories(f"Itt szerepel a {correct} szo.", "1Moz 1:1") == []
    wrong_categories = _categories(f"Itt szerepel a {wrong} szo.", "1Moz 1:1")
    assert wrong_categories != []
    assert GroundingCategory.PASSAGE_MATCH not in wrong_categories


# =============================================================================
# 13. H Strong suffix-variáns nem okoz hamis pozitívot
# =============================================================================


def test_13_bare_hebrew_strong_id_matches_lettered_only_global_entry():
    # H0122 maga sehol nincs kozvetlen lexikon-bejegyzeskent, csak
    # H0122A (2Kir 3,22) es H0122B (1Moz 25,30) letezik -- 1Moz 1,1-hez
    # kepest ez egy MASIK passzus, tehat GLOBAL_OTHER_PASSAGE varhato,
    # NEM UNKNOWN es NEM INVALID_STRONG_ID.
    text = "A szo mogott a H0122 Strong-szam all."
    warnings = check_original_language_grounding(text, "1Moz 1:1")
    assert len(warnings) == 1
    assert warnings[0].category == GroundingCategory.GLOBAL_OTHER_PASSAGE


# =============================================================================
# 14. Hianyzo token-adat -> graceful fallback (nincs kivetel)
# =============================================================================


def test_14_missing_or_unparseable_reference_gracefully_falls_back():
    # Fejezetkozi hivatkozas -- a token-blokk logika szerint sincs adat.
    text = "Itt egy λόγος szo van."
    warnings = check_original_language_grounding(text, "Jn 3,16-4,2")
    assert warnings  # nem dob kivetelt, es UNKNOWN/GLOBAL besorolast ad

    # Teljesen ertelmezhetetlen hivatkozas.
    warnings2 = check_original_language_grounding(text, "nem egy igehely !!!")
    assert isinstance(warnings2, list)

    # Ures szoveg -- ures lista, nincs kivetel.
    assert check_original_language_grounding("", "Jn 3:16") == []

    # build_passage_vocabulary onmagaban is graceful.
    vocab = build_passage_vocabulary("nem egy igehely !!!")
    assert vocab.greek_surface_forms == frozenset()
    assert vocab.hebrew_strong_ids == frozenset()


# =============================================================================
# 15-17. `app.py` integracio -- AppTest-alapu alfolyamat
# =============================================================================

_EXEGESIS_WORKER_TEMPLATE = '''
import json
import sys

sys.path.insert(0, __ROOT__)

from streamlit.testing.v1 import AppTest


def _render():
    import streamlit as st
    import app

    # `igehely_input` egy VALÓDI widget-kulcs máshol az app.py-ban (az
    # "Igehely" fülön) -- `import app` már importáláskor lerendereli, ezért
    # ide direktben NEM írhatunk bele (Streamlit tiltja). A `render_
    # original_text_panel`/`generate_section` a hiányzó `igehely_input`
    # esetén a `last_igehely`-re esik vissza -- ld. mindkét függvény
    # forráskódját -- ezért elég csak azt beállítani.
    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["bible_translation"] = ""
    st.session_state["passage_text"] = "Mert ugy szerette Isten a vilagot."
    st.session_state["api_key"] = "TEST_KEY"
    st.session_state["using_builtin_key"] = False

    def _fake_generate_text(prompt, **kwargs):
        return (
            "## Kulcsszavak es kulcskifejezesek\\n\\n"
            "A szoveg emliti a λόγος szot egy masik "
            "igehelybol, ld. 3. vers.\\n\\n"
            "## Kontextus\\n\\nEz a szakasz Jn 3,16-hoz kapcsolodik.\\n"
        )

    app.generate_text = _fake_generate_text

    returned = app.generate_section("exegesis")

    st.session_state["_worker_result"] = {
        "generate_section_returned": returned,
        "exegesis_text": st.session_state.get("exegesis"),
        "support_warnings": st.session_state.get("exegesis_support_warnings"),
        "grounding_warnings": st.session_state.get("exegesis_grounding_warnings"),
    }


app_test = AppTest.from_function(_render).run(timeout=60)
worker_result = app_test.session_state["_worker_result"]
worker_result["app_exception"] = bool(app_test.exception)

with open(__OUT_PATH__, "w", encoding="utf-8") as f:
    json.dump(worker_result, f)
'''


_ORIGINAL_TEXT_WORKER_TEMPLATE = '''
import json
import sys

sys.path.insert(0, __ROOT__)

from streamlit.testing.v1 import AppTest


def _render():
    import streamlit as st
    import app

    # `igehely_input` egy VALÓDI widget-kulcs máshol az app.py-ban -- ld.
    # a `_EXEGESIS_WORKER_TEMPLATE`-ben lévő azonos megjegyzést.
    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["bible_translation"] = ""
    st.session_state["passage_text"] = "Mert ugy szerette Isten a vilagot."
    st.session_state["api_key"] = "TEST_KEY"
    st.session_state["using_builtin_key"] = False

    def _fake_generate_text(prompt, **kwargs):
        return (
            "Az eredeti szoveg elemzese: *λόγος* [logosz] "
            "szo, ami egy masik igehelybol szarmazo pelda."
        )

    app.generate_text = _fake_generate_text

    app.render_original_text_panel()

    # A `_worker_result`-ot MINDEN render-passzon újraírjuk (az utolsó,
    # rerun-utáni passzon lesz friss) -- ugyanaz a minta, mint az
    # exegesis workerben, bracket-eléréssel olvasva ki a végén (az
    # AppTest `session_state` proxy nem támogat `.get()`-et).
    st.session_state["_worker_result"] = {
        "original_text": st.session_state.get("original_text"),
        "grounding_warnings": st.session_state.get("original_text_grounding_warnings"),
    }


app_test = AppTest.from_function(_render).run(timeout=60)
app_test.button(key="original_run").click().run(timeout=60)
# Rerun-settles (ld. korabbi RESET fazisok dokumentalt mintaja).
app_test.run(timeout=60)

result = app_test.session_state["_worker_result"]
result["app_exception"] = bool(app_test.exception)

with open(__OUT_PATH__, "w", encoding="utf-8") as f:
    json.dump(result, f)
'''


def _run_apptest_worker(template: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        worker_path = Path(tmp_dir) / "worker.py"
        script = template.replace("__ROOT__", repr(str(ROOT))).replace(
            "__OUT_PATH__", repr(str(out_path))
        )
        worker_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(worker_path)],
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


@pytest.fixture(scope="module")
def _exegesis_result() -> dict:
    return _run_apptest_worker(_EXEGESIS_WORKER_TEMPLATE)


@pytest.fixture(scope="module")
def _original_text_result() -> dict:
    return _run_apptest_worker(_ORIGINAL_TEXT_WORKER_TEMPLATE)


def test_15_original_text_grounding_warning_does_not_block_result(_original_text_result):
    assert _original_text_result["app_exception"] is False
    # Az eredmeny MENTVE/HASZNALHATO marad a figyelmeztetes ELLENERE.
    assert _original_text_result["original_text"]
    assert "λόγος" in _original_text_result["original_text"]
    # Es TENYLEGESEN van legalabb egy grounding-figyelmeztetes (mas
    # igehelybol szarmazo szo -- a mock szoveg szandekosan ilyen).
    assert _original_text_result["grounding_warnings"]


def test_16_exegesis_grounding_warning_does_not_block_result(_exegesis_result):
    assert _exegesis_result["app_exception"] is False
    assert _exegesis_result["generate_section_returned"] is True
    assert _exegesis_result["exegesis_text"]
    assert _exegesis_result["grounding_warnings"]


def test_17_existing_support_presence_check_is_unaffected(_exegesis_result):
    # A meglevo `validate_exegesis_has_support` VALTOZATLANUL fut -- a
    # mock szoveg mindket alcimehez van vers-hivatkozas VAGY gorog
    # karakter, tehat nem varunk support-warningot; a lista tipusa/
    # jelenlete bizonyitja, hogy a mechanizmus lefutott es NEM torlodott
    # ki az uj grounding-reteg altal.
    assert _exegesis_result["support_warnings"] == []


# =============================================================================
# RESET 3B-6a -- state-integrity: a grounding/support warning-listak
# ELETCIKLUSA. Mindharom kulcs (`exegesis_support_warnings`,
# `exegesis_grounding_warnings`, `original_text_grounding_warnings`) tisztan
# futasideju, SOSEM resze a mentett project_data-nak -- ezert a tartalom-
# visszaallito utvonalaknak (projektvaltas, workspace-torles, workspace-
# import) EXPLICIT modon kell nullazniuk oket, kulonben egy korabbi
# projekt/allapot figyelmeztetese szivarogna at az uj tartalom ala.
#
# MODSZERTANI MEGJEGYZES: a harom erintett fuggveny (`_apply_project_data_
# to_session`, `_clear_workspace_content`, `deserialize_workspace`) a TELJES
# workspace-t (sok mezot, tobbek kozott widget-kotesu kulcsokat, pl.
# `series_idea`) atirja. Egy AppTest-alapu `_render()`-ben az `import app`
# MAGA mar teljes egeszeben lerendereli az app.py-t (ld. a fajl elejen levo
# dokumentaciot) -- ezert e harom fuggveny FUTASIDEJU meghivasa AppTest-en
# keresztul "cannot be modified after the widget... is instantiated"
# hibaba utkozik, FUGGETLENUL a hivas sorrendjetol (mert az `import app`
# egyetlen menetben, elejetol vegig lefuttatja a teljes oldalt, nem csak a
# gombig). Ezert itt STRUKTURALIS (forraskod-alapu) ellenorzest hasznalunk
# -- ugyanazt a technikat, mint a 21. teszt -- ami bizonyitja, hogy mindharom
# fuggveny TENYLEGESEN meghivja a kozos `_reset_language_grounding_
# warnings()` helpert, es hogy az a helper valoban mindharom kulcsot ures
# listara allitja.
# =============================================================================

_SOURCE_INSPECTION_WORKER_TEMPLATE = '''
import json
import sys

sys.path.insert(0, __ROOT__)

import app

result = {
    "reset_helper_keys": list(app._LANGUAGE_GROUNDING_WARNING_KEYS),
    "apply_project_data_calls_reset": "_reset_language_grounding_warnings()" in
        __import__("inspect").getsource(app._apply_project_data_to_session),
    "clear_workspace_calls_reset": "_reset_language_grounding_warnings()" in
        __import__("inspect").getsource(app._clear_workspace_content),
    "deserialize_workspace_calls_reset": "_reset_language_grounding_warnings()" in
        __import__("inspect").getsource(app.deserialize_workspace),
}

with open(__OUT_PATH__, "w", encoding="utf-8") as f:
    json.dump(result, f)
'''


def _run_source_inspection_worker() -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        script = _SOURCE_INSPECTION_WORKER_TEMPLATE.replace(
            "__ROOT__", repr(str(ROOT))
        ).replace("__OUT_PATH__", repr(str(out_path)))
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


def test_18_all_three_content_reset_paths_clear_the_warning_keys():
    result = _run_source_inspection_worker()
    assert set(result["reset_helper_keys"]) == {
        "exegesis_support_warnings",
        "exegesis_grounding_warnings",
        "original_text_grounding_warnings",
    }
    assert result["apply_project_data_calls_reset"] is True
    assert result["clear_workspace_calls_reset"] is True
    assert result["deserialize_workspace_calls_reset"] is True


_RESET_HELPER_RUNTIME_WORKER_TEMPLATE = '''
import json
import sys

sys.path.insert(0, __ROOT__)

from streamlit.testing.v1 import AppTest


def _render():
    import streamlit as st
    import app

    # A `_reset_language_grounding_warnings` MAGA nem erint egyetlen
    # widget-kotesu kulcsot sem (a harom celkulcs sosem `key=` egyetlen
    # widgeten), ezert -- a fenti strukturalis teszttel ellentetben --
    # ez KOZVETLENUL, futasidoben is biztonsagosan tesztelheto AppTest-en
    # keresztul, meg a teljes oldal `import app`-kori lerenderelese utan is.
    st.session_state["exegesis_support_warnings"] = ["STALE_SUPPORT_WARNING"]
    st.session_state["exegesis_grounding_warnings"] = ["STALE_EXEGESIS_GROUNDING_WARNING"]
    st.session_state["original_text_grounding_warnings"] = ["STALE_ORIGINAL_TEXT_GROUNDING_WARNING"]

    app._reset_language_grounding_warnings()

    st.session_state["_worker_result"] = {
        "exegesis_support_warnings": st.session_state.get("exegesis_support_warnings"),
        "exegesis_grounding_warnings": st.session_state.get("exegesis_grounding_warnings"),
        "original_text_grounding_warnings": st.session_state.get(
            "original_text_grounding_warnings"
        ),
    }


app_test = AppTest.from_function(_render).run(timeout=60)
worker_result = app_test.session_state["_worker_result"]
worker_result["app_exception"] = bool(app_test.exception)

with open(__OUT_PATH__, "w", encoding="utf-8") as f:
    json.dump(worker_result, f)
'''


def test_18b_reset_helper_actually_clears_stale_values_at_runtime():
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        worker_path = Path(tmp_dir) / "worker.py"
        script = _RESET_HELPER_RUNTIME_WORKER_TEMPLATE.replace(
            "__ROOT__", repr(str(ROOT))
        ).replace("__OUT_PATH__", repr(str(out_path)))
        worker_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(worker_path)],
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
        result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["app_exception"] is False
    assert result["exegesis_support_warnings"] == []
    assert result["exegesis_grounding_warnings"] == []
    assert result["original_text_grounding_warnings"] == []


# =============================================================================
# RESET 3B-6a -- egymast koveto generalasi probalkozasok: sikeres, tiszta
# ujrageneralas es hibas probalkozas sem hagy hatra "aktualisnak tuno"
# regi figyelmeztetest.
# =============================================================================

_EXEGESIS_SEQUENTIAL_WORKER_TEMPLATE = '''
import json
import sys

sys.path.insert(0, __ROOT__)

from streamlit.testing.v1 import AppTest


def _render():
    import streamlit as st
    import app

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["bible_translation"] = ""
    st.session_state["passage_text"] = "Mert ugy szerette Isten a vilagot."
    st.session_state["api_key"] = "TEST_KEY"
    st.session_state["using_builtin_key"] = False

    # 1. probalkozas: figyelmezteto szoveget general (mas igehelybol
    # szarmazo valodi gorog szoval).
    def _fake_generate_text_with_warning(prompt, **kwargs):
        return (
            "## Kulcsszavak es kulcskifejezesek\\n\\n"
            "A szo λόγος (3. vers).\\n\\n"
            "## Kontextus\\n\\nJn 3,16.\\n"
        )

    app.generate_text = _fake_generate_text_with_warning
    app.generate_section("exegesis")
    after_first = {
        "text": st.session_state.get("exegesis"),
        "grounding_warnings": list(st.session_state.get("exegesis_grounding_warnings") or []),
    }

    # 2. probalkozas: TISZTA, csak a passzus sajat tokenjet hasznalo szoveg
    # -- a regi figyelmeztetesnek el kell tunnie.
    def _fake_generate_text_clean(prompt, **kwargs):
        return (
            "## Kulcsszavak es kulcskifejezesek\\n\\n"
            "A szo ἠγάπησεν (3. vers).\\n\\n"
            "## Kontextus\\n\\nJn 3,16.\\n"
        )

    app.generate_text = _fake_generate_text_clean
    app.generate_section("exegesis")
    after_clean_regen = {
        "text": st.session_state.get("exegesis"),
        "grounding_warnings": list(st.session_state.get("exegesis_grounding_warnings") or []),
    }

    # 3. probalkozas: HIBAS/felbeszakadt valasz -- a masodik korbol
    # (tiszta, warning nelkuli) allapotot folytatja, ELLENORIZZUK, hogy ha
    # elozoleg VOLT figyelmeztetes-allapot, az uj (hibas) probalkozas utan
    # nem tunik ugy, mintha az AKTUALIS probalkozashoz tartozna.
    def _fake_generate_text_error(prompt, **kwargs):
        return "⚠️ Az elemzes nem sikerult."

    app.generate_text = _fake_generate_text_error
    app.generate_section("exegesis")
    after_error_attempt = {
        "text": st.session_state.get("exegesis"),
        "grounding_warnings": list(st.session_state.get("exegesis_grounding_warnings") or []),
    }

    st.session_state["_worker_result"] = {
        "after_first": after_first,
        "after_clean_regen": after_clean_regen,
        "after_error_attempt": after_error_attempt,
    }


app_test = AppTest.from_function(_render).run(timeout=60)
worker_result = app_test.session_state["_worker_result"]
worker_result["app_exception"] = bool(app_test.exception)

with open(__OUT_PATH__, "w", encoding="utf-8") as f:
    json.dump(worker_result, f)
'''


@pytest.fixture(scope="module")
def _exegesis_sequential_result() -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        worker_path = Path(tmp_dir) / "worker.py"
        script = _EXEGESIS_SEQUENTIAL_WORKER_TEMPLATE.replace(
            "__ROOT__", repr(str(ROOT))
        ).replace("__OUT_PATH__", repr(str(out_path)))
        worker_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(worker_path)],
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


def test_19_successful_clean_regeneration_clears_previous_warning(
    _exegesis_sequential_result,
):
    assert _exegesis_sequential_result["app_exception"] is False
    assert _exegesis_sequential_result["after_first"]["grounding_warnings"]
    assert _exegesis_sequential_result["after_clean_regen"]["grounding_warnings"] == []


def test_20_failed_generation_attempt_does_not_keep_stale_warning_as_current(
    _exegesis_sequential_result,
):
    # A harmadik (hibas) probalkozas utan a szoveg maga is a HIBAuzenet --
    # a hozza tartozo grounding_warnings-nak ehhez kell igazodnia (ures),
    # NEM az elozo, sikeres probalkozas figyelmeztetesenek kell maradnia.
    after_error = _exegesis_sequential_result["after_error_attempt"]
    assert after_error["text"] == "⚠️ Az elemzes nem sikerult."
    assert after_error["grounding_warnings"] == []


def test_21_original_text_and_exegesis_use_separate_warning_state():
    # A ket kulcs nev szerint is elkulonul -- `check_original_language_
    # grounding` sosem ir egy kozos/megosztott kulcsba.
    import inspect

    from bible_engine import original_language_grounding_check as module

    source = inspect.getsource(module)
    assert "exegesis_grounding_warnings" not in source
    assert "original_text_grounding_warnings" not in source
    # A modul maga NEM ismeri a session-kulcsokat -- az app.py kotesi
    # retege felelos a kulon kulcsokert (ld. 18-20. teszt: a ket kulcs
    # fuggetlenul nullazodik/toltodik).
