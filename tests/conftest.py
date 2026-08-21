"""Session-szintű teszt-előkészítés (tesztinfrastruktúra, NEM termékkód).

Gyökérok (bizonyítva, 2026-08-13, tesztalap-stabilizálás): `app.py` egy
tiszta Streamlit-szkript — nincs benne `if __name__ == "__main__":` őr, a
teljes modul tetőtől talpig, importáláskor lefut, beleértve a valódi
`st.form("textus_feedback_form", ...)` hívást is. Éles üzemben ez helyes és
szükséges (mindig `streamlit run app.py` futtatja, valódi Streamlit-runtime
kontextusban).

A tesztkörnyezetben viszont számos tesztfájl importálja közvetlenül az
`app` modult (pl. csak egyetlen segédfüggvényért), AppTest-sandbox NÉLKÜL —
lásd pl. `tests/test_canonical_source_collector.py`,
`tests/test_concept_concordance.py`, `tests/test_occasion_context.py`,
`tests/test_outline_engine.py`, `tests/test_p0_generate_text_tls_
temperature.py`, `tests/test_security_hygiene.py`, `tests/test_word_
export.py`. A LEGELSŐ ilyen import a pytest-folyamat főszálán, közvetlenül
(sandbox nélkül) hajtja végre az `app.py` teljes tetejét — ez szennyezi a
Streamlit globális DeltaGenerator form-/widget-nyomkövetési állapotát, és a
később (a teljes `pytest tests/` futásban, ábécésorrendben utána) végrehajtódó,
`streamlit.testing.v1.AppTest`-alapú tesztek ettől hamis,
"DeltaGeneratorSingleton instance already exists!" / "st.button() can't be
used in an st.form()" / "Within a form, callbacks can only be defined on
st.form_submit_button" hibákkal buknak — miközben külön futtatva zöldek.

Ezt minimális, determinisztikus fájlpár-reprodukcióval bizonyítottuk (pl.
`pytest tests/test_bible_text_reading_view.py
tests/test_original_language_token_block.py` — a régi, közvetlen `import
app`-ot használó verzióval, javítás előtt).

A javítás: az `app` modult a session ELSŐ lépéseként, EGYETLEN alkalommal,
`AppTest`-sandboxban importáljuk be — a Streamlit saját tesztelési
infrastruktúrája megfelelően kezeli a script-futtatási kontextust, így az
`app.py` tetején lévő kód itt biztonságosan lefuthat, DeltaGenerator-
szennyezés nélkül. Miután a modul egyszer bekerült a `sys.modules`
gyorsítótárba, Python importrendszere a FENTI tesztfájlok mindegyikében
található, későbbi `import app` / `import app as app_mod` hívásokat már csak
a gyorsítótárazott modul visszaadásaként kezeli — NEM hajtja újra végre a
tetején lévő kódot —, tehát biztonságos.

Ez KIZÁRÓLAG tesztinfrastruktúra-intézkedés: sem az `app.py`, sem a fent
felsorolt tesztfájlok `import app` hívásai nem változtak."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _preimport_app_module_inside_streamlit_sandbox() -> None:
    """Lásd a modul docstringjét — ez a session legelső, mindenki által
    (autouse) megkövetelt lépése, mielőtt bármely teszt teste lefutna.

    Szándékosan NEM nyel el semmilyen hibát: az `AppTest.run()` önmagában
    nem dob kivételt egy, a sandboxolt szkriptben történt hibára (csak az
    `.exception` listába gyűjti) — ezért itt explicit módon ellenőrizzük és
    újra felemeljük, hogy egy valódi `app.py`-import-hiba hangosan,
    azonnal buktassa a session legelső lépését, ne csendben sikkadjon el."""
    from streamlit.testing.v1 import AppTest

    def _do_import() -> None:
        import app  # noqa: F401

    result = AppTest.from_function(_do_import).run(timeout=60)
    if result.exception:
        raise RuntimeError(
            "Az 'app' modul előimportja a Streamlit-sandboxban hibázott: "
            f"{[exc.message for exc in result.exception]}"
        )
