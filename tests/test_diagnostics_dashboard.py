# ruff: noqa: E402
"""M8 diagnosztika — egyszerűsített pastor-facing UI regresszió."""

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
)
from sermon_workshop_m8_ai import (
    DIAGNOSTIC_AREA_KEYS,
    normalize_diagnostic_status,
)
from sermon_workshop_ui import (
    _DIAG_DETAIL_GROUPS,
    _DIAG_MAP_GROUPS,
    _SW_SECTION_OPTIONS,
    _diag_areas_index,
    _diag_collect_priorities,
    _diag_shorten,
    _diag_soften_text,
    _diag_status_chip_html,
    _diag_status_soft_label,
    _diag_view_model,
    _render_diagnostics_results,
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


def _content_calls(calls: list[str]) -> str:
    return "\n".join(c for c in calls if not c.lstrip().startswith("<style"))


def _main_content(calls: list[str]) -> str:
    """Main surface only — stop before the closed details expander."""
    parts: list[str] = []
    for c in calls:
        if c.startswith("EXP:Részletesebb homiletikai megjegyzések") or c.startswith(
            "EXP:Részletes diagnosztika"
        ):
            break
        if c.lstrip().startswith("<style"):
            continue
        parts.append(c)
    return "\n".join(parts)


def _prio_card_count(calls: list[str]) -> int:
    return sum(1 for c in calls if 'class="sw-diag-prio-card' in c)


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
    monkeypatch.setattr(
        st,
        "expander",
        lambda label, expanded=False: (
            calls.append(f"EXP:{label}:{expanded}") or nullcontext()
        ),
    )
    monkeypatch.setattr(st, "columns", lambda n: [nullcontext() for _ in range(n)])
    monkeypatch.setattr(st, "container", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "button", lambda *a, **k: False)


def test_main_view_three_parts_in_source():
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    start = src.find("def _render_diagnostics_results")
    end = src.find("\ndef render_diagnostics_section", start)
    body = src[start:end]
    assert "Rövid összkép" in body
    assert "Ami már jól működik" in body
    assert "Amin most érdemes dolgozni" in body
    assert "_render_diag_overview_card(" in body
    assert "_render_diag_profile_list(" in body
    assert "Részletesebb homiletikai megjegyzések" in body
    assert "Általános állapot" in src
    assert "Homiletikai diagnózis" in src
    assert "Fő gondolat kidolgozása" in src
    # Régi státuszszámlálók / 12 kategória ne legyen a fő nézetben
    assert "_render_diag_status_cards(" not in body
    assert "Gyors státusz" not in body
    assert "Diagnosztikai térkép" not in src
    assert "_render_diag_map(" not in src
    assert "A vázlat homiletikai ellenőrzése" in src
    assert _SW_SECTION_OPTIONS[-1] == "Homiletikai diagnosztika"
    assert _SW_SECTION_OPTIONS[-2] == "Igehirdetési vázlat"


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
    assert "Figyelmet igényel" in chip
    assert "%" not in chip
    assert "pontszám" not in chip.casefold()
    assert _diag_status_soft_label("critical_gap") == "Javítandó"
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


def test_render_simple_main_view(session, monkeypatch):
    """Main surface: összkép + erősségek + max 3 finomítás + továbbhaladás."""
    calls: list[str] = []
    _stub_streamlit(monkeypatch, calls)

    areas = _full_areas(
        {
            "text_fidelity": "strong",
            "theological_accuracy": "stable",
            "christ_centeredness": "needs_attention",
            "unity_and_focus": "stable",
            "listener_tension": "not_enough_information",
            "sermon_path": "stable",
            "closing": "stable",
            "hearability": "stable",
            "images_and_illustrations": "stable",
            "application": "stable",
            "pastoral_responsibility": "stable",
            "voice_and_originality": "stable",
        }
    )
    save_homiletical_diagnostics(
        session,
        {
            "overall_summary": "Összességében stabil terv, egy finomítandó ponttal.",
            "overall_coherence": "A fő gondolat és a lezárás összhangban van.",
            "diagnostic_areas": areas,
            "major_strengths": ["Erős textushűség"],
            "revision_priorities": [
                {
                    "priority": 1,
                    "title": "Hallgatói feszültség tisztázása",
                    "problem": "Hiányzik",
                    "why_it_matters": "Nélküle gyenge a hallhatóság.",
                    "recommended_action": "Fogalmazd meg a feszültséget.",
                    "affected_sections": ["Hallgatói kérdés", "unity_and_focus"],
                }
            ],
            "consistency_warnings": [],
            "pastoral_warnings": [],
            "voice_and_originality_note": "Saját hang érződik.",
            "ready_for_next_stage": True,
            "readiness_note": "Mehet a lekciómodul.",
            "warnings": [],
            "missing_information": [],
            "ok": True,
        },
    )

    _render_diagnostics_results()
    main = _main_content(calls)
    content = _content_calls(calls)

    assert "Rövid összkép" in main
    assert "Ami már jól működik" in main
    assert "Amin most érdemes dolgozni" in main
    assert "Hallgatói feszültség tisztázása" in main
    assert "Erős textushűség" in main
    assert "Gyors státusz" not in main
    assert "Diagnosztikai térkép" not in main
    assert "unity_and_focus" not in main
    assert "pontszám" not in content.casefold()
    assert "87%" not in content
    assert _prio_card_count(calls) == 1
    assert any(
        c.startswith("EXP:Részletesebb homiletikai megjegyzések:False") for c in calls
    )


def test_multiple_gaps_details_not_main_warnings(session, monkeypatch):
    """Max 3 refinement cards; long notes only in closed details."""
    calls: list[str] = []
    _stub_streamlit(monkeypatch, calls)

    areas = _full_areas(
        {
            "text_fidelity": "critical_gap",
            "theological_accuracy": "critical_gap",
            "christ_centeredness": "needs_attention",
            "listener_tension": "not_enough_information",
            "images_and_illustrations": "not_enough_information",
        }
    )
    save_homiletical_diagnostics(
        session,
        {
            "overall_summary": "Több javítandó pont van a tervben.",
            "overall_coherence": "Még gyenge az összhang.",
            "diagnostic_areas": areas,
            "major_strengths": [],
            "revision_priorities": [
                {
                    "priority": 1,
                    "title": "Textushűség",
                    "why_it_matters": "Alap",
                    "recommended_action": "Vissza a textushoz",
                    "affected_sections": ["Textusműhely"],
                },
                {
                    "priority": 2,
                    "title": "Teológia",
                    "why_it_matters": "Pontosság",
                    "recommended_action": "Pontosíts",
                    "affected_sections": ["Teológia"],
                },
                {
                    "priority": 3,
                    "title": "Krisztus-központúság",
                    "why_it_matters": "Evangélium",
                    "recommended_action": "Emeld ki",
                    "affected_sections": [],
                },
                {
                    "priority": 4,
                    "title": "Ne jelenjen meg",
                    "why_it_matters": "Negyedik",
                    "recommended_action": "Skip",
                    "affected_sections": [],
                },
            ],
            "pastoral_warnings": ["Óvatosan a bűntudattal."],
            "ready_for_next_stage": False,
            "readiness_note": "Előbb a hiányok.",
            "ok": True,
        },
    )
    _render_diagnostics_results()
    main = _main_content(calls)
    content = _content_calls(calls)

    assert _prio_card_count(calls) == 3
    assert "Ne jelenjen meg" not in main
    assert "Óvatosan a bűntudattal." not in main
    assert "Óvatosan a bűntudattal." in content
    assert "text_fidelity" not in main
    assert "Gyors státusz" not in main
    assert "Javítandó pontok" not in main


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
    assert "@media (max-width: 900px)" in css_src
    assert "@media (max-width: 520px)" in css_src
    assert "grid-template-columns: 1fr" in css_src
    assert "plotly" not in css_src.casefold()
    assert "radar" not in css_src.casefold()
