# ruff: noqa: E402
"""SVG diagnosztikai dashboard komponensek — üres / részleges / teljes állapot."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diagnostics_dashboard_ui import (
    ensure_dashboard_styles,
    render_coverage_ring,
    render_profile_diagram,
    render_score_ring,
)


@pytest.fixture
def calls(monkeypatch):
    out: list[str] = []
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(
        st, "markdown", lambda *a, **k: out.append(str(a[0]) if a else "")
    )
    return out


def test_score_ring_insufficient_is_neutral(calls):
    ensure_dashboard_styles()
    render_score_ring(
        score=None,
        qualifier="Nincs elég adat",
        qualifier_key="none",
        summary="Még nincs elég terület.",
        sufficient=False,
    )
    html = "\n".join(calls)
    assert "nincs elég adat" in html.casefold()
    assert "—" in html
    assert "stroke-dasharray=\"4 6\"" in html
    assert 'class="tx-ring-big"' in html
    assert ">72<" not in html
    assert '">100-ból</' not in html


def test_score_ring_sufficient_shows_value(calls):
    render_score_ring(
        score=72,
        qualifier="Jó alap",
        qualifier_key="good",
        summary="A vázlat jó alap.",
        sufficient=True,
    )
    html = "\n".join(calls)
    assert ">72<" in html
    assert "100-ból" in html
    assert "Jó alap" in html
    assert "aria-label=" in html


def test_coverage_ring_lists_missing(calls):
    render_coverage_ring(
        evaluated=5,
        total=8,
        missing_labels=["Alkalmazás", "Lezárás", "Pásztori hang"],
    )
    html = "\n".join(calls)
    assert "5/8" in html
    assert "Még hiányzik" in html
    assert "Alkalmazás" in html


def test_profile_partial_does_not_zero_fill(calls):
    rows = [
        {
            "label": "Textushűség",
            "value": 3,
            "status_label": "Stabil",
            "color": "#5a7aa8",
        },
        {
            "label": "Alkalmazás",
            "value": None,
            "status_label": "Nincs elég adat",
            "color": "#9a938a",
        },
        {
            "label": "Lezárás",
            "value": 2,
            "status_label": "Figyelmet igényel",
            "color": "#c4923a",
        },
    ]
    render_profile_diagram(rows)
    html = "\n".join(calls)
    assert "Részleges profil" in html
    assert "Textushűség" in html
    assert "fill=\"rgba(90,122,168,0.20)\"" not in html
