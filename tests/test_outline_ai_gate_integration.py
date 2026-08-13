# ruff: noqa: E402
"""Fázis 2B utólagos audit (2026-08-13): bizonyítás, hogy a `sermon_workshop_
outline_ai.build_outline_from_workshop()` (és a mögötte álló `sermon_outline_
engine._gated_fallback_bundle()`) SEMMILYEN produkciós útvonalon nem válhat
a felhasználó felé megjelenő, jóváhagyható vagy exportálható VÉGLEGES
prédikációvázlattá — kizárólag a `sermon_outline_engine.generate_sermon_
outline()` sikeres AI-szintézise vagy egy korábban ténylegesen mentett,
érvényes vázlat lehet a `sermon_workshop.sermon_outline` forrása.

Ez a fájl a valódi produkciós UI-belépési pontokat hívja közvetlenül
(`sermon_workshop_ui._assemble_and_save_outline`, a "Vázlat összeállítása/
frissítése a meglévő anyagból" gomb tényleges kódja) — NEM újraírt/
egyszerűsített tesztlogikát —, `st.session_state`-et monkeypatch-elve,
ugyanazzal a mintával, mint `tests/test_outline_canonical_content.py` és
`tests/test_diagnostics_critical_flow.py`. Teljes Streamlit AppTest helyett
(ld. `tests/test_textus_workshop_outline_card_removed.py` docstringje: az
app.py mérete miatt ez a bevett, gyors, stabil ellenőrzési mód ebben a
projektben) — de a hívott függvény maga a produkciós kód, nem mock.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
import streamlit as st

from sermon_outline_engine import AI_UNAVAILABLE_MESSAGE
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    normalize_sermon_outline,
    save_sermon_outline,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import (
    build_outline_from_workshop,
    outline_canonical_text,
    outline_has_content,
)
from sermon_workshop_ui import (
    _CONFIRM_OUTLINE_OVERWRITE,
    _OUTLINE_ASSEMBLY_FLASH_SUCCESS,
    _OUTLINE_ASSEMBLY_FLASH_WARNINGS,
    _assemble_and_save_outline,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop
from tests.test_jude_e2e_workflow import build_jude_state
from tests.test_outline_engine import _ok_gen, _valid_structured


class nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    monkeypatch.setattr(st, "spinner", lambda *a, **k: nullctx())
    monkeypatch.setattr(st, "warning", lambda *a, **k: None)
    monkeypatch.setattr(st, "error", lambda *a, **k: None)
    monkeypatch.setattr(st, "success", lambda *a, **k: None)
    monkeypatch.setattr(st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(st, "rerun", lambda: None)
    return state


def _rich_workshop_state() -> dict:
    """Teljes, jóváhagyott Júdás-műhely — a build_outline_from_workshop()
    ebből MÁR ÖNMAGÁBAN is tartalmas, nem-üres seedet tudna építeni."""
    state = build_jude_state()
    ensure_sermon_workshop_state(state)
    return state


def _empty_new_project_state() -> dict:
    state = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta…",
        "exegesis": "",
        "theology": "",
        "history": "",
        "last_sajat": "",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
    }
    ensure_sermon_workshop_state(state)
    return state


# ---------------------------------------------------------------------------
# 1. generate_fn=None esetén a felhasználó nem kap új kész vázlatot
# ---------------------------------------------------------------------------


def test_missing_generate_fn_gives_user_no_new_outline(session):
    session.update(_rich_workshop_state())
    warnings: list[str] = []
    st.warning = lambda m, *a, **k: warnings.append(str(m))

    _assemble_and_save_outline(generate_fn=None, force_overwrite=False)

    sw = ensure_sermon_workshop_state(session)
    assert not outline_has_content(sw.get("sermon_outline"))
    assert any(AI_UNAVAILABLE_MESSAGE in w for w in warnings)
    # A gomb megnyomása után sem status, sem tartalom nem lett "kész".
    assert str(sw.get("sermon_outline_status") or "draft") != "approved"


# ---------------------------------------------------------------------------
# 2. AI-hiba esetén nem jelenik meg seed/workshop-bundle kész vázlatként
# ---------------------------------------------------------------------------


def test_ai_error_does_not_surface_seed_as_finished_outline(session):
    state = _rich_workshop_state()
    session.update(state)

    # Bizonyítás: a build_outline_from_workshop() ÖNMAGÁBAN nem üres —
    # lenne mit "átcsempészni", ha a motor visszaesne rá.
    seed = build_outline_from_workshop(state)
    assert outline_has_content(seed)
    assert seed.get("movements")

    def boom(*_a, **_k):
        raise RuntimeError("AI szolgáltatás nem elérhető")

    _assemble_and_save_outline(generate_fn=boom, force_overwrite=False)

    sw = ensure_sermon_workshop_state(session)
    assert not outline_has_content(sw.get("sermon_outline"))
    # A mentett (üres) vázlat NEM egyezik a seed tartalmával — nincs
    # észrevétlen "átcsempészés".
    stored = normalize_sermon_outline(sw.get("sermon_outline"))
    assert stored.get("main_idea") != seed.get("main_idea") or not stored.get(
        "main_idea"
    )
    assert not stored.get("movements")


# ---------------------------------------------------------------------------
# 3. AI-hiba után a Word-export nem exportál AI nélkül összeállított vázlatot
# ---------------------------------------------------------------------------


def test_ai_error_leaves_nothing_exportable_via_word(session):
    state = _rich_workshop_state()
    session.update(state)

    def boom(*_a, **_k):
        raise RuntimeError("offline")

    _assemble_and_save_outline(generate_fn=boom, force_overwrite=False)

    sw = ensure_sermon_workshop_state(session)
    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    # A Word-export (sermon_workshop_ui.py render_outline_section,
    # ~3795. sor) pontosan ezt a függvényt hívja a session["outline"]
    # feltöltéséhez — ha ez üres, nincs mit exportálni.
    export_body = outline_canonical_text(outline)
    assert export_body == ""


# ---------------------------------------------------------------------------
# 4. Meglévő approved vázlat továbbra is megjelenik és exportálható
# ---------------------------------------------------------------------------


def test_existing_approved_outline_survives_and_stays_exportable(session):
    state = _rich_workshop_state()
    session.update(state)

    _assemble_and_save_outline(generate_fn=_ok_gen, force_overwrite=False)
    sw = ensure_sermon_workshop_state(session)
    assert outline_has_content(sw.get("sermon_outline"))
    update_sermon_workshop_section(session, "sermon_outline_status", "approved")
    # A `sermon_outline.status` beágyazott mező csak a következő
    # ensure_sermon_workshop_state/normalize hívásnál szinkronizálódik a
    # sermon_outline_status-hoz — ez a szinkron maga NEM tartalommódosítás,
    # csak itt vesszük fel az összehasonlítási alapot UTÁNA, hogy a
    # második (sikertelen) próba tényleg semmit ne változtasson.
    sw = ensure_sermon_workshop_state(session)
    approved_snapshot = json.dumps(sw["sermon_outline"], sort_keys=True)
    approved_main_idea = sw["sermon_outline"].get("main_idea")
    approved_export_body = outline_canonical_text(
        normalize_sermon_outline(sw["sermon_outline"])
    )
    assert approved_export_body.strip()

    def boom(*_a, **_k):
        raise RuntimeError("offline")

    _assemble_and_save_outline(generate_fn=boom, force_overwrite=True)

    sw = ensure_sermon_workshop_state(session)
    assert json.dumps(sw["sermon_outline"], sort_keys=True) == approved_snapshot
    assert sw["sermon_outline"].get("main_idea") == approved_main_idea
    assert sw.get("sermon_outline_status") == "approved"
    still_exportable = outline_canonical_text(
        normalize_sermon_outline(sw["sermon_outline"])
    )
    assert still_exportable == approved_export_body

    # Végponti bizonyíték: a jóváhagyott tartalomból ténylegesen épül
    # érvényes .docx.
    import io

    from docx import Document

    from outline_word_export import build_outline_docx

    session["outline"] = still_exportable
    session["last_igehely"] = "Júd 17–20"
    docx_bytes = build_outline_docx()
    assert docx_bytes[:2] == b"PK"
    doc = Document(io.BytesIO(docx_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert approved_main_idea in full_text


# ---------------------------------------------------------------------------
# 5. Új projektben, meglévő vázlat nélkül, AI-hiba után nincs menthető/
#    jóváhagyható kész vázlat
# ---------------------------------------------------------------------------


def test_new_project_ai_failure_leaves_nothing_approvable(session):
    state = _empty_new_project_state()
    session.update(state)

    def boom(*_a, **_k):
        raise RuntimeError("offline")

    _assemble_and_save_outline(generate_fn=boom, force_overwrite=False)

    sw = ensure_sermon_workshop_state(session)
    before = normalize_sermon_outline(sw.get("sermon_outline"))
    # Ez pontosan a "Vázlat jóváhagyása" gomb saját őrfeltétele
    # (sermon_workshop_ui.py ~3865. sor): ha ez False, a UI blokkolja a
    # jóváhagyást, és figyelmeztetést ad "üres vagy csak whitespace-t
    # tartalmazó vázlat nem hagyható jóvá" szöveggel.
    assert not outline_has_content(before)


# ---------------------------------------------------------------------------
# 6. build_outline_from_workshop() eredménye nem kerülhet észrevétlenül
#    végleges vázlatstátuszba
# ---------------------------------------------------------------------------


def test_build_outline_from_workshop_has_no_production_ui_call_site():
    """Regressziós őr: ha egy jövőbeli módosítás közvetlenül a UI-ból
    hívná a `build_outline_from_workshop()`-ot (megkerülve az AI-
    generálási szerződést), ez a teszt azonnal elbukik."""
    ui_src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "build_outline_from_workshop(" not in ui_src
    assert "build_outline_from_workshop(" not in app_src
    assert "_gated_fallback_bundle(" not in ui_src
    assert "_gated_fallback_bundle(" not in app_src

    # Az egyetlen engedélyezett produkciós hívó: a motor belső seedje
    # (kizárólag metaadat-egyesítésre, sosem végleges tartalomként —
    # ld. structured_to_sermon_outline()).
    engine_src = (ROOT / "sermon_outline_engine.py").read_text(encoding="utf-8")
    occurrences = engine_src.count("build_outline_from_workshop(")
    assert occurrences == 1


def test_build_outline_from_workshop_result_is_always_draft_status():
    """Még ha valaki közvetlenül elmentené is a seedet, az sosem
    'approved' — a jóváhagyás mindig külön, explicit felhasználói
    lépés (update_sermon_workshop_section(..., "approved"))."""
    state = _rich_workshop_state()
    seed = build_outline_from_workshop(state)
    assert seed.get("status") != "approved"


def test_ai_content_wins_over_rich_seed_when_generation_succeeds(session):
    """Erős bizonyíték az A/B/C szétválasztásra: még ha a műhely-seed
    (build_outline_from_workshop) tartalmas és eltérő témájú, sikeres
    AI-generálás esetén a VÉGSŐ vázlat tartalma (main_idea, movements)
    kizárólag az AI válaszából származik, nem a seedből."""
    state = _rich_workshop_state()
    session.update(state)

    seed = build_outline_from_workshop(state)
    seed_main_idea = seed.get("main_idea")
    assert seed_main_idea  # a Júdás-műhely eleve tartalmas

    def gen_divergent(*_a, **_k):
        return json.dumps(
            _valid_structured(
                title="Teljesen más témájú, MI-generált cím",
                focus_sentence=(
                    "Ez a fókuszmondat szándékosan nem egyezik a műhely "
                    "jóváhagyott fő gondolatával, hogy bizonyítsa: a "
                    "végső tartalom az AI válaszából, nem a seedből ered."
                ),
            ),
            ensure_ascii=False,
        )

    _assemble_and_save_outline(generate_fn=gen_divergent, force_overwrite=False)
    sw = ensure_sermon_workshop_state(session)
    assert outline_has_content(sw.get("sermon_outline"))
    final_main_idea = sw["sermon_outline"].get("main_idea")
    assert final_main_idea != seed_main_idea
    assert "szándékosan nem egyezik" in final_main_idea
