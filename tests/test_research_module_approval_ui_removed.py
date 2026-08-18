"""Fázis 2D.3 (UI-audit, 2026-08-18): a Textusműhely kutatási moduljainál
(exegézis / eredeti nyelvi anyag / kortörténet / teológia) megmaradt, de
funkcionálisan már szükségtelen approval-UI eltávolítása.

PREFLIGHT-EREDMÉNY (ld. a fázisvégi audit is): ezekre a forrásokra a
vázlatmotor már a 2D.1/2D.2 (és az azt megelőző "Korrekciós fázis 3.1")
óta NEM approval-gated — csak a friss igehelyhez tartozást ellenőrzi
(ld. `tests/test_outline_research_source_no_approval_gate.py`,
`tests/test_outline_canonical_background_flow.py`,
`tests/test_canonical_source_collector.py`). A "Mentés vázlatként" /
"Jóváhagyom és átadom" gombpár és a "sosem lett jóváhagyva"
figyelmeztetés ezért félrevezető volt: gating-et sugalltak, ami valójában
nem létezett. Ez a fájl azt bizonyítja, hogy:

1. a gombpár ténylegesen eltűnt mindkét érintett UI-helyről (app.py
   `render_section_tab` és `render_original_text_panel`);
2. a "sosem lett jóváhagyva" figyelmeztetés-mechanizmus (dead code) is
   teljesen eltűnt;
3. a generált tartalom a gomb nélkül is végigfut a TELJES
   `generate_sermon_outline()` belépőponton (nem csak a bundle/background
   szinten, amit a 2D.1/2D.2 már bizonyított);
4. a homiletikai döntésekre (pl. `human_condition`) vonatkozó, MÉG
   AKTÍV "Kimaradt a vázlatból (nincs jóváhagyva)" figyelmeztetés
   változatlanul működik — ez a fázis NEM nyúlt hozzá.

Nincs valódi AI/külső API-hívás egyik tesztben sem (`generate_fn=None`).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import generate_sermon_outline
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    update_sermon_workshop_section,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, ensure_text_workshop_state, get_default_text_workshop

EXEGESIS_SENTINEL = "EXEGESIS_2D3_SENTINEL"
ORIGINAL_LANGUAGE_SENTINEL = "ORIGINAL_LANGUAGE_2D3_SENTINEL"
HISTORY_SENTINEL = "HISTORY_2D3_SENTINEL"
THEOLOGY_SENTINEL = "THEOLOGY_2D3_SENTINEL"


def _draft_research_state(**extra) -> dict:
    """Mind a négy kutatási forrás DRAFT állapotban, sosem jóváhagyva —
    az approve-gomb eltávolítása utáni ÚJ normál eset (korábban is ez
    volt a funkcionálisan érvényes állapot, csak a UI ezt nem tükrözte)."""
    state = {
        "last_igehely": "Lk 14,1-6",
        "igehely_input": "Lk 14,1-6",
        "passage_text": (
            "1 Amikor egyszer szombaton az egyik farizeus vezető házába ment "
            "étkezni, azok szemmel tartották őt. "
            "6 És nem tudtak erre felelni."
        ),
        "bible_translation": "RÚF 2014",
        "exegesis": EXEGESIS_SENTINEL,
        "exegesis_status": "draft",
        "original_text": ORIGINAL_LANGUAGE_SENTINEL,
        "original_text_status": "draft",
        "history": HISTORY_SENTINEL,
        "history_status": "draft",
        "theology": THEOLOGY_SENTINEL,
        "theology_status": "draft",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_text_workshop_state(state)
    ensure_sermon_workshop_state(state)
    return state


# ---------------------------------------------------------------------------
# A) a gombpár és a mögöttes UI-szöveg ténylegesen eltűnt
# ---------------------------------------------------------------------------


def test_render_section_tab_has_no_approval_button_source():
    import app

    src = inspect.getsource(app.render_section_tab)
    assert '"Mentés vázlatként"' not in src
    assert '"Jóváhagyom és átadom"' not in src
    assert "_save_draft_btn" not in src
    assert "_approve_btn" not in src
    assert "_ever_approved" not in src
    # A generáláskori hash-bélyegzés (freshness védelem) megmaradt.
    assert "compute_current_passage_context_hash" in src
    assert "approvable and has_result" in src


def test_render_original_text_panel_has_no_approval_button_source():
    import app

    src = inspect.getsource(app.render_original_text_panel)
    assert '"Mentés vázlatként"' not in src
    assert '"Jóváhagyom és átadom"' not in src
    assert "original_save_draft_btn" not in src
    assert "original_approve_btn" not in src
    assert "original_text_ever_approved" not in src
    assert "compute_current_passage_context_hash" in src


def test_no_orphaned_approvable_status_labels_constant():
    import app

    assert not hasattr(app, "_APPROVABLE_STATUS_LABELS")


# ---------------------------------------------------------------------------
# B) a "sosem lett jóváhagyva" holt figyelmeztetés-mechanizmus eltűnt
# ---------------------------------------------------------------------------


def test_never_approved_warning_mechanism_removed():
    import sermon_outline_engine as engine

    assert not hasattr(engine, "extract_never_approved_main_blocks")
    assert not hasattr(engine, "_NEVER_VS_REVOKED_TRACKED_KEYS")

    src = Path(engine.__file__).read_text(encoding="utf-8")
    assert "sosem lett jóváhagyva" not in src
    assert "extract_never_approved_main_blocks" not in src


def test_generate_sermon_outline_never_emits_never_approved_warning():
    """A négy kutatási forrás sosincs jóváhagyva ebben az állapotban —
    a régi (dead) mechanizmus ilyenkor figyelmeztetést adott volna;
    az ÚJ, gomb nélküli viselkedésben ilyen figyelmeztetés nem jelenhet
    meg, mert a mechanizmus maga tűnt el."""
    state = _draft_research_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert not any("sosem lett jóváhagyva" in w for w in result.warnings), result.warnings


# ---------------------------------------------------------------------------
# C) a generált tartalom a TELJES generate_sermon_outline() belépőponton
#    keresztül is approval nélkül elérhető marad (nem csak bundle/background
#    szinten, amit a 2D.1/2D.2 már bizonyított)
# ---------------------------------------------------------------------------


def test_generate_sermon_outline_reaches_ai_unavailable_branch_without_blocking_warning():
    """generate_fn=None esetén a függvény korán visszatér (nincs API-hívó
    funkció) — de a warnings lista MÁR ekkor is elkészül a bundle-ből, és
    NEM tartalmazhat approval-hiányra hivatkozó blokkolást a 4 kutatási
    forrásra, hiszen a bundle sikeresen tartalmazza őket draft állapotban is."""
    state = _draft_research_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert result.error_kind == "ai_unavailable"
    for w in result.warnings:
        assert "Exegézis" not in w
        assert "Kortörténet" not in w
        assert "Teológia" not in w
        assert "Eredeti nyelvi elemzés" not in w


# ---------------------------------------------------------------------------
# D) NEM ÉRINTETT: a homiletikai döntésekre (pl. human_condition) vonatkozó
#    "Kimaradt a vázlatból (nincs jóváhagyva)" figyelmeztetés VÁLTOZATLANUL
#    aktív — ez a fázis explicit módon nem nyúlt hozzá.
# ---------------------------------------------------------------------------


def test_excluded_draft_warning_for_homiletical_keys_still_fires():
    state = _draft_research_state()
    update_sermon_workshop_section(
        state, "human_condition", {"condition": "Draft emberi helyzet, nincs jóváhagyva."}
    )
    update_sermon_workshop_section(state, "human_condition_status", "draft")

    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert any(
        "Kimaradt a vázlatból (nincs jóváhagyva)" in w and "Emberi állapot" in w
        for w in result.warnings
    ), result.warnings
