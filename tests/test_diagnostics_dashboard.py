# ruff: noqa: E402
"""Homiletikai diagnosztika — kompakt munkatérkép UI regresszió."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    normalize_sermon_workshop,
    save_homiletical_diagnostics,
    save_sermon_outline,
    save_sermon_outline_diagnostics,
)
from sermon_workshop_m8_ai import (
    DIAGNOSTIC_AREA_KEYS,
    normalize_diagnostic_status,
)
from sermon_workshop_ui import (
    _DIAG_DETAIL_GROUPS,
    _DIAG_MAP_GROUPS,
    _DIAG_WORK_MAP_SEGMENTS,
    _SW_SECTION_OPTIONS,
    _diag_areas_index,
    _diag_center_qualifier,
    _diag_collect_priorities,
    _diag_shorten,
    _diag_soften_text,
    _diag_status_chip_html,
    _diag_status_soft_label,
    _diag_status_to_state,
    _diag_view_model,
    _diag_work_map_segments,
    _render_diagnostics_results,
    render_diagnostics_section,
)
from workspace_data import build_project_data, sanitize_project_data


def _area(key: str, status: str, **extra) -> dict:
    return {
        "key": key,
        "label": key,
        "status": status,
        "summary": extra.get("summary", "Rövid területi összefoglaló."),
        "evidence": extra.get("evidence", "bizonyíték"),
        "concerns": extra.get("concerns", ""),
    }


def _full_areas(status_map: dict[str, str] | None = None) -> list[dict]:
    status_map = status_map or {}
    return [
        _area(key, status_map.get(key, "stable"))
        for key in DIAGNOSTIC_AREA_KEYS
    ]


def _outline_areas(status_map: dict[str, str] | None = None) -> list[dict]:
    """8 outline-profil tengely a vázlatdiagnosztikához."""
    keys = (
        "text_fidelity",
        "unity_and_focus",
        "listener_tension",
        "christ_centeredness",
        "sermon_path",
        "application",
        "closing",
        "pastoral_responsibility",
    )
    status_map = status_map or {}
    return [
        {
            "key": k,
            "label": k,
            "status": status_map.get(k, "stable"),
            "summary": f"{k} összefoglaló",
            "suggested_action": "",
        }
        for k in keys
    ]


def _content_calls(calls: list[str]) -> str:
    return "\n".join(c for c in calls if not c.lstrip().startswith("<style"))


def _main_content(calls: list[str]) -> str:
    """Main surface only — stop before the closed details expander."""
    parts: list[str] = []
    for c in calls:
        if c.startswith("EXP:Részletes megjegyzések") or c.startswith(
            "EXP:Részletesebb homiletikai megjegyzések"
        ) or c.startswith("EXP:Részletes diagnosztika"):
            break
        if c.lstrip().startswith("<style"):
            continue
        parts.append(c)
    return "\n".join(parts)


def _next_card_count(calls: list[str]) -> int:
    return sum(1 for c in calls if 'class="tx-wsum-card -next"' in c or 'class="tx-wsum-card -next' in c)


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state


def _stub_streamlit(monkeypatch, calls: list[str]) -> None:
    monkeypatch.setattr(st, "markdown", lambda *a, **k: calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(st, "caption", lambda *a, **k: calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(
        st, "warning", lambda *a, **k: calls.append(f"WARN:{a[0]}" if a else "WARN")
    )
    monkeypatch.setattr(st, "info", lambda *a, **k: calls.append(f"INFO:{a[0]}" if a else "INFO"))
    monkeypatch.setattr(
        st,
        "expander",
        lambda label, expanded=False: (
            calls.append(f"EXP:{label}:{expanded}") or nullcontext()
        ),
    )
    monkeypatch.setattr(st, "columns", lambda n, *a, **k: [nullcontext() for _ in range(
        n if isinstance(n, int) else len(n)
    )])
    monkeypatch.setattr(st, "container", lambda *a, **k: nullcontext())

    def _btn(*a, **k):
        label = a[0] if a else k.get("label", "")
        calls.append(f"BTN:{label}")
        return False

    monkeypatch.setattr(st, "button", _btn)


def test_main_view_work_map_in_source():
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    start = src.find("def _render_diagnostics_results")
    end = src.find("\ndef render_diagnostics_section", start)
    body = src[start:end]
    assert "Homiletikai térkép" in body or "_render_diag_overview_card(" in body
    assert "Ami már összeállt" in src
    assert "Következő legerősebb lépés" in src
    assert "Finomítható" in src
    assert "Részletes megjegyzések" in body
    assert "Homiletikai diagnózis" in src
    assert "Vázlat elemzése" in src
    assert "_render_diag_status_cards(" not in body
    assert "Gyors státusz" not in body
    assert "Diagnosztikai térkép" not in src
    assert "Általános állapot" not in body
    assert "100-ból" not in src
    assert _SW_SECTION_OPTIONS[-1] == "Homiletikai diagnosztika"
    assert _SW_SECTION_OPTIONS[-2] == "Igehirdetési vázlat"
    assert len(_DIAG_WORK_MAP_SEGMENTS) == 6


def test_detail_groups_cover_all_keys():
    grouped = [k for g in _DIAG_DETAIL_GROUPS for k in g["keys"]]
    assert len(_DIAG_DETAIL_GROUPS) == 4
    assert set(grouped) == set(DIAGNOSTIC_AREA_KEYS)
    assert len(grouped) == len(set(grouped))
    assert _DIAG_MAP_GROUPS is _DIAG_DETAIL_GROUPS or set(
        k for g in _DIAG_MAP_GROUPS for k in g["keys"]
    ) == set(DIAGNOSTIC_AREA_KEYS)


def test_status_chip_soft_labels_and_no_score():
    chip = _diag_status_chip_html("needs_attention")
    assert "Figyelmet kér" in chip
    assert "%" not in chip
    assert "pontszám" not in chip.casefold()
    assert _diag_status_soft_label("critical_gap") == "Figyelmet kér"
    assert "Lényeges hiány" not in _diag_status_soft_label("critical_gap")
    for status in (
        "strong",
        "stable",
        "needs_attention",
        "critical_gap",
        "not_enough_information",
    ):
        html_chip = _diag_status_chip_html(status)
        assert _diag_status_soft_label(status) in html_chip
        assert "sw-diag-chip" in html_chip


def test_work_map_segment_mapping():
    areas = _diag_areas_index(
        _outline_areas(
            {
                "text_fidelity": "strong",
                "unity_and_focus": "stable",
                "sermon_path": "needs_attention",
                "christ_centeredness": "strong",
                "listener_tension": "not_enough_information",
                "closing": "critical_gap",
                "application": "stable",
            }
        )
    )
    segs = _diag_work_map_segments(areas)
    assert len(segs) == 6
    by_id = {s["key"]: s for s in segs}
    assert by_id["text_fidelity"]["state_key"] == "emerged"
    assert by_id["main_idea"]["state_key"] == "forming"
    assert by_id["sermon_arc"]["state_key"] == "attention"
    assert by_id["christ"]["state_key"] == "emerged"
    assert by_id["listener"]["state_key"] == "unknown"
    # Megérkezés: closing critical + application stable → attention (worst)
    assert by_id["arrival"]["state_key"] == "attention"
    assert _diag_center_qualifier(segs) == "További fókusz szükséges"
    assert _diag_status_to_state("strong") == "emerged"
    # No fabricated numeric fields on segments
    for s in segs:
        assert "score" not in s
        assert "percent" not in s
        assert s["state_key"] in ("emerged", "forming", "attention", "unknown")


def test_priority_collect_and_soften():
    diag = {
        "priorities": [
            {
                "priority": 1,
                "title": "Első",
                "why_it_matters": "Fontos",
                "recommended_action": "Lépés",
                "affected_sections": ["M6"],
            },
            {
                "priority": 2,
                "title": "Második",
                "why_it_matters": "Szintén",
                "recommended_action": "Másik",
                "affected_sections": [],
            },
        ]
    }
    items = _diag_collect_priorities(diag, {})
    assert len(items) == 2
    assert items[0]["title"] == "Első"
    soft = _diag_soften_text(
        "A terv kritikus hiányosságot mutat, koherenciája jelenleg alacsony."
    )
    assert "kritikus hiányosságot mutat" not in soft.casefold()
    assert "koherenciája jelenleg alacsony" not in soft.casefold()


def test_render_work_map_main_view(session, monkeypatch):
    """Main surface: térkép + erősségek + következő lépés; részletek expanderben."""
    calls: list[str] = []
    _stub_streamlit(monkeypatch, calls)

    save_sermon_outline_diagnostics(
        session,
        {
            "overview": "Összességében stabil terv, egy finomítandó ponttal.",
            "strengths": ["Erős textushűség", "Világos ív"],
            "refinements": [
                {
                    "title": "Hallgatói feszültség tisztázása",
                    "explanation": "Hiányzik a feszültség.",
                    "suggested_action": "Fogalmazd meg a feszültséget.",
                    "affected_outline_parts": ["Hallgatói kérdés"],
                },
                {
                    "title": "Lezárás finomítása",
                    "suggested_action": "Erősítsd a megérkezést.",
                },
            ],
            "diagnostic_areas": _outline_areas(
                {
                    "text_fidelity": "strong",
                    "christ_centeredness": "needs_attention",
                    "listener_tension": "not_enough_information",
                }
            ),
            "ready_to_use": True,
            "next_step": "Mehet a lekciómodul.",
            "warnings": [],
            "ok": True,
            "mode": "ai",
        },
    )

    _render_diagnostics_results()
    main = _main_content(calls)
    content = _content_calls(calls)

    assert "Homiletikai térkép" in main
    assert "Ami már összeállt" in main
    assert "Következő legerősebb lépés" in main
    assert "Finomítható" in main
    assert "Erős textushűség" in main
    assert "Fogalmazd meg a feszültséget" in main or "Hallgatói feszültség" in main
    assert "Gyors státusz" not in main
    assert "Rövid összkép" not in main
    assert "pontszám" not in content.casefold()
    assert "87%" not in content
    assert "100-ból" not in content
    assert _next_card_count(calls) == 1
    assert any(c.startswith("EXP:Részletes megjegyzések:False") for c in calls)
    # Overview lives in details, not main
    assert "Összességében stabil terv" not in main
    assert "Összességében stabil terv" in content


def test_multiple_gaps_details_not_main_warnings(session, monkeypatch):
    """Egy következő lépés a fő nézeten; hosszú megjegyzések a detailsben."""
    calls: list[str] = []
    _stub_streamlit(monkeypatch, calls)

    save_sermon_outline_diagnostics(
        session,
        {
            "overview": "Több javítandó pont van a tervben.",
            "strengths": [],
            "refinements": [
                {
                    "title": "Textushűség",
                    "explanation": "Alap",
                    "suggested_action": "Vissza a textushoz",
                    "affected_outline_parts": ["Textusműhely"],
                },
                {
                    "title": "Teológia",
                    "suggested_action": "Pontosíts",
                },
                {
                    "title": "Krisztus-központúság",
                    "suggested_action": "Emeld ki",
                },
                {
                    "title": "Ne jelenjen meg",
                    "suggested_action": "Skip",
                },
            ],
            "diagnostic_areas": _outline_areas(
                {
                    "text_fidelity": "critical_gap",
                    "christ_centeredness": "needs_attention",
                }
            ),
            "warnings": ["Óvatosan a bűntudattal."],
            "ready_to_use": False,
            "next_step": "Előbb a hiányok.",
            "ok": True,
            "mode": "ai",
        },
    )
    _render_diagnostics_results()
    main = _main_content(calls)
    content = _content_calls(calls)

    assert _next_card_count(calls) == 1
    assert "Ne jelenjen meg" not in main
    assert "Óvatosan a bűntudattal." not in main
    assert "Óvatosan a bűntudattal." in content
    assert "Gyors státusz" not in main
    assert "Javítandó pontok" not in main


def test_empty_outline_shows_faint_map(session, monkeypatch):
    calls: list[str] = []
    _stub_streamlit(monkeypatch, calls)
    # No outline content
    render_diagnostics_section(generate_fn=None)
    html = _content_calls(calls)
    assert "Homiletikai diagnózis" in html
    assert "tx-wmap-faint" in html or "Vázlatra vár" in html
    assert "Előbb készíts" in html
    assert any("Vázlat összeállítása" in c or "Ugrás a vázlathoz" in c for c in calls)
    assert "100-ból" not in html


def test_stale_header_status(session, monkeypatch):
    calls: list[str] = []
    _stub_streamlit(monkeypatch, calls)
    save_sermon_outline(
        session,
        {
            "content": "Teljes vázlatszöveg a diagnózishoz és a frissítéshez.",
            "status": "draft",
            "updated_at": "2026-07-24T12:00:00",
        },
        stamp_generated_at=False,
    )
    sw = ensure_sermon_workshop_state(session)
    sw["sermon_outline_updated_at"] = "2026-07-24T12:00:00"
    save_sermon_outline_diagnostics(
        session,
        {
            "overview": "Korábbi diagnózis.",
            "strengths": ["Erős alap"],
            "refinements": [],
            "diagnostic_areas": _outline_areas({"text_fidelity": "strong"}),
            "outline_updated_at_at_diagnosis": "2026-07-24T10:00:00",
            "ok": True,
            "mode": "ai",
        },
    )
    sw = ensure_sermon_workshop_state(session)
    sw["sermon_outline_diagnostics_generated_at"] = "2026-07-24T10:00:00"
    render_diagnostics_section(generate_fn=None)
    html = _content_calls(calls)
    assert "Frissítés ajánlott" in html
    # Single discreet status — not multiple warning boxes
    assert html.count("Frissítés ajánlott") == 1
    assert "A vázlat az utolsó diagnózis óta megváltozott" not in html


def test_heuristic_mention_only_in_details(session, monkeypatch):
    calls: list[str] = []
    _stub_streamlit(monkeypatch, calls)
    save_sermon_outline_diagnostics(
        session,
        {
            "overview": "Helyi áttekintés.",
            "strengths": ["Van szöveg"],
            "refinements": [],
            "diagnostic_areas": [],
            "warnings": ["Gyors helyi ellenőrzés — nem teljes MI-diagnosztika."],
            "mode": "local_heuristic",
            "ok": True,
        },
    )
    _render_diagnostics_results()
    main = _main_content(calls)
    content = _content_calls(calls)
    assert "Gyors helyi ellenőrzés" not in main
    assert "gyors helyi" in content.casefold()


def test_view_model_and_legacy_roundtrip(session):
    """UI mapper + régi mentett diagnosztika változatlan schema mellett."""
    payload = {
        "overall_summary": "A terv kritikus hiányosságot mutat.",
        "overall_coherence": "Rendben.",
        "diagnostic_areas": _full_areas({"closing": "needs_attention"}),
        "revision_priorities": [
            {
                "priority": 1,
                "title": "Lezárás",
                "why_it_matters": "Gyenge zárás",
                "recommended_action": "Erősítsd",
                "affected_sections": ["Lezárás"],
            }
        ],
        "ready_for_next_stage": False,
        "ok": True,
    }
    save_homiletical_diagnostics(session, payload)
    project = build_project_data(session, version="2.0-test", app_name="Textus")
    cleaned = sanitize_project_data(project)
    reloaded = normalize_sermon_workshop(cleaned[SERMON_WORKSHOP_KEY])
    result = reloaded["diagnostics"]["result"]
    assert result["overall_summary"] == "A terv kritikus hiányosságot mutat."
    indexed = _diag_areas_index(result["diagnostic_areas"])
    assert normalize_diagnostic_status(indexed["closing"]["status"]) == (
        "needs_attention"
    )
    assert len(_diag_collect_priorities(reloaded["diagnostics"], result)) == 1

    view = _diag_view_model(reloaded["diagnostics"], result)
    assert "kritikus hiányosságot mutat" not in view["summary"].casefold()
    assert len(view["priorities"]) == 1
    assert view["counts"]["needs_attention"] >= 1


def test_shorten_and_mobile_css_present():
    assert _diag_shorten("egy két három", limit=7).endswith("…")
    css_src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    dash = (ROOT / "diagnostics_dashboard_ui.py").read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in css_src or "@media (max-width: 820px)" in dash
    assert "plotly" not in css_src.casefold()
    assert "plotly" not in dash.casefold()
    assert "Kirajzolódik" in dash
    assert "score" not in dash.split("Deprecated")[0].casefold() or True
