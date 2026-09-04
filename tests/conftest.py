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


@pytest.fixture(autouse=True)
def _isolate_commentary_storage_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard against any test accidentally reaching real Supabase Storage
    through ``textus_kb.commentary_runtime.ensure_status`` (2026-09-04
    production-storage round): that function is now the SINGLE choke
    point called, with no explicit ``database_path``, by every real
    Commentary-evidence consumer (the reader UI, Exegézis, Eredeti
    szöveg, Kortörténet) -- meaning it is reachable from a much wider set
    of tests than just ``test_commentary_runtime.py``'s own dedicated
    suite (which already isolates itself further via its own autouse
    fixture). Any test whose mocked/real local status comes back
    unavailable would otherwise fall through to real storage-config
    resolution, and if THIS machine's env/secrets happen to have
    ``TEXTUS_COMMENTARY_DB_STORAGE_BUCKET`` (etc.) configured -- exactly
    as they legitimately would be post-deployment -- that fall-through
    would attempt a real network call during a unit test. Clearing these
    three env vars for every test (regardless of whether that test cares)
    keeps ``ensure_status`` degrading to the local, network-free
    ``storage_not_configured`` reason unless a test explicitly opts back
    in (ld. ``tests/test_textus_kb/test_commentary_runtime.py``'s own
    mocked-Supabase-client tests, which set these via monkeypatch/kwargs
    themselves)."""
    monkeypatch.delenv("TEXTUS_COMMENTARY_DB_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("TEXTUS_COMMENTARY_DB_STORAGE_OBJECT", raising=False)
    monkeypatch.delenv("TEXTUS_COMMENTARY_DB_SHA256", raising=False)


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
