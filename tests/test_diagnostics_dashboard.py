"""M8 diagnosztika dashboard — UI-szerkezet és státusz-összesítés regresszió."""

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
    diagnostic_status_label,
    normalize_diagnostic_status,
)
from sermon_workshop_ui import (
    _DIAG_MAP_GROUPS,
    _diag_areas_index,
    _diag_collect_priorities,
    _diag_shorten,
    _diag_status_chip_html,
    _diag_worst_status,
    _render_diagnostics_results,
)
from workspace_data import build_project_data, sanitize_project_data


def _area(key: str, status: str, **extra) -> dict:
    return {
        "key": key,
        "label": key,
        "status": status,
        "summary": extra.get("summary", f"{key} összefoglaló"),
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


def _prio_card_count(calls: list[str]) -> int:
    return sum(
        1
        for c in calls
        if 'class="sw-diag-prio-card' in c or 'class="sw-diag-prio-card ' in c
    )


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


def test_dashboard_section_order_in_source():
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    start = src.find("def _render_diagnostics_results")
    end = src.find("\ndef render_diagnostics_section", start)
    body = src[start:end]
    markers = [
        "_render_diag_overview(",
        "_render_diag_priorities(",
        "_render_diag_map(",
        "Fő erősségek",
        "Konzisztencia-figyelmeztetések",
        "Pásztori figyelmeztetések",
        "Saját hang és eredetiség",
        "Minden diagnosztikai részlet",
        "Továbbhaladási megjegyzés",
    ]
    positions = [body.find(m) for m in markers]
    assert all(p >= 0 for p in positions), list(zip(markers, positions))
    assert positions == sorted(positions)
    assert "Gyors áttekintés" in src
    assert "Most erre érdemes figyelni" in src
    assert "Diagnosztikai térkép" in src


def test_four_thematic_groups_cover_all_keys():
    grouped = [k for g in _DIAG_MAP_GROUPS for k in g["keys"]]
    assert len(_DIAG_MAP_GROUPS) == 4
    assert set(grouped) == set(DIAGNOSTIC_AREA_KEYS)
    assert len(grouped) == len(set(grouped))


def test_status_chip_has_label_and_no_score():
    chip = _diag_status_chip_html("needs_attention")
    assert "Figyelmet igényel" in chip
    assert "%" not in chip
    assert "pontszám" not in chip.casefold()
    for status in (
        "strong",
        "stable",
        "needs_attention",
        "critical_gap",
        "not_enough_information",
    ):
        html_chip = _diag_status_chip_html(status)
        assert diagnostic_status_label(status) in html_chip
        assert "sw-diag-chip" in html_chip


def test_worst_status_and_priority_cards():
    assert _diag_worst_status(["stable", "strong"]) == "stable"
    assert _diag_worst_status(["stable", "critical_gap"]) == "critical_gap"
    assert _diag_worst_status(["needs_attention", "not_enough_information"]) == (
        "needs_attention"
    )
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


def test_render_all_status_types_without_empty_critical(session, monkeypatch):
    """A–B: minden státusz + nincs critical_gap üres szakasz nélkül."""
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
                    "affected_sections": ["Hallgatói kérdés"],
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
    content = _content_calls(calls)
    assert "Gyors áttekintés" in content
    assert "Most erre érdemes figyelni" in content
    assert "Diagnosztikai térkép" in content
    assert "Hallgatói feszültség tisztázása" in content
    assert "Pásztori figyelmeztetések" not in content
    assert "pontszám" not in content.casefold()
    assert "87%" not in content
    assert _prio_card_count(calls) == 1


def test_multiple_critical_gaps_and_partial(session, monkeypatch):
    """C–D: több hiány + részleges adat."""
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
            "overall_summary": "Több lényeges hiány.",
            "overall_coherence": "Gyenge.",
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
            ],
            "pastoral_warnings": ["Óvatosan a bűntudattal."],
            "ready_for_next_stage": False,
            "readiness_note": "Előbb a hiányok.",
            "ok": True,
        },
    )
    _render_diagnostics_results()
    content = _content_calls(calls)
    assert "Lényeges hiány" in content or "critical_gap" in content
    assert "Nincs elég adat" in content
    assert "Pásztori figyelmeztetések" in content
    assert _prio_card_count(calls) == 2
    assert "Bibliai és teológiai alap" in content


def test_legacy_saved_diagnostics_roundtrip(session):
    """G: régi mentett diagnosztika változtatás nélkül megjeleníthető."""
    payload = {
        "overall_summary": "Régi összefoglaló.",
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
    assert result["overall_summary"] == "Régi összefoglaló."
    indexed = _diag_areas_index(result["diagnostic_areas"])
    assert normalize_diagnostic_status(indexed["closing"]["status"]) == (
        "needs_attention"
    )
    assert len(_diag_collect_priorities(reloaded["diagnostics"], result)) == 1


def test_shorten_and_mobile_css_present():
    assert _diag_shorten("egy két három", limit=7).endswith("…")
    css_src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in css_src
    assert "@media (max-width: 520px)" in css_src
    assert "grid-template-columns: 1fr" in css_src
    assert "plotly" not in css_src.casefold()
    assert "radar" not in css_src.casefold()
