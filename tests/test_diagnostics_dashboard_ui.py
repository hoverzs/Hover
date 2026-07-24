# ruff: noqa: E402
"""SVG homiletikai munkatérkép — üres / részleges / teljes állapot."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diagnostics_dashboard_ui import (
    build_work_map_svg,
    ensure_dashboard_styles,
    render_coverage_ring,
    render_profile_diagram,
    render_score_ring,
    render_work_map,
    segment_state_label,
)


@pytest.fixture
def calls(monkeypatch):
    out: list[str] = []
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(
        st, "markdown", lambda *a, **k: out.append(str(a[0]) if a else "")
    )
    monkeypatch.setattr(
        st, "caption", lambda *a, **k: out.append(str(a[0]) if a else "")
    )
    return out


def _six_segments(state: str = "unknown") -> list[dict]:
    labels = (
        "Textushűség",
        "Fő gondolat",
        "Igehirdetési ív",
        "Krisztus-központúság",
        "Hallgatói megszólítás",
        "Megérkezés",
    )
    return [
        {
            "key": f"s{i}",
            "label": lbl,
            "state_key": state,
            "tooltip": f"{lbl}: {segment_state_label(state)}",
        }
        for i, lbl in enumerate(labels)
    ]


def test_work_map_empty_is_faint_neutral(calls):
    ensure_dashboard_styles()
    render_work_map(
        _six_segments("unknown"),
        center_title="Aktuális vázlat",
        center_qualifier="Még alakuló kép",
        faint=True,
    )
    html = "\n".join(calls)
    assert "tx-wmap" in html
    assert "Még alakuló kép" in html
    assert "Aktuális vázlat" in html
    assert "tx-wmap-faint" in html
    assert "Kirajzolódik" in html  # legend
    assert "%" not in html or "100%" in html  # width=100% ok; no score %
    assert ">72<" not in html
    assert "100-ból" not in html
    assert "pontszám" not in html.casefold()


def test_work_map_partial_and_full_qualitative(calls):
    segs = _six_segments("unknown")
    segs[0]["state_key"] = "emerged"
    segs[1]["state_key"] = "forming"
    segs[2]["state_key"] = "attention"
    render_work_map(
        segs,
        center_qualifier="További fókusz szükséges",
        faint=False,
    )
    html = "\n".join(calls)
    assert "Textushűség" in html
    assert "További fókusz szükséges" in html
    assert "#5a7aa8" in html  # emerged blue
    assert "#c4a06a" in html  # forming gold
    assert "#b87a52" in html  # attention terracotta
    assert "title>" in html.casefold() or "<title>" in html
    assert "100-ból" not in html
    assert "/10" not in html


def test_build_work_map_svg_has_six_paths():
    svg = build_work_map_svg(_six_segments("forming"), center_qualifier="Kibontakozó ív")
    assert svg.count('class="tx-wmap-seg"') == 6
    assert "Kibontakozó ív" in svg
    assert "%" not in svg.replace('width="100%"', "")


def test_legacy_score_ring_hides_numbers(calls):
    """Deprecated score ring must not display numeric scores."""
    ensure_dashboard_styles()
    render_score_ring(
        score=None,
        qualifier="Nincs elég adat",
        qualifier_key="none",
        summary="Még nincs elég terület.",
        sufficient=False,
    )
    html = "\n".join(calls)
    assert "nincs elég adat" in html.casefold() or "Még alakuló" in html or "Nincs elég" in html
    assert ">72<" not in html
    assert "100-ból" not in html

    calls.clear()
    render_score_ring(
        score=72,
        qualifier="Jó alap",
        qualifier_key="good",
        summary="A vázlat jó alap.",
        sufficient=True,
    )
    html2 = "\n".join(calls)
    assert ">72<" not in html2
    assert "100-ból" not in html2
    assert "Aktuális vázlat" in html2


def test_coverage_ring_qualitative_note(calls):
    render_coverage_ring(
        evaluated=5,
        total=8,
        missing_labels=["Alkalmazás", "Lezárás", "Pásztori hang"],
    )
    html = "\n".join(calls)
    assert "Részleges" in html or "hiányzik" in html.casefold() or "alakul" in html.casefold()
    assert "5/8" not in html  # no ratio-as-grade


def test_profile_partial_forwards_to_work_map(calls):
    rows = [
        {
            "label": "Textushűség",
            "value": 3,
            "status": "stable",
            "status_label": "Alakul",
            "color": "#5a7aa8",
        },
        {
            "label": "Alkalmazás",
            "value": None,
            "status": "not_enough_information",
            "status_label": "Még nincs elég adat",
            "color": "#9a938a",
        },
        {
            "label": "Lezárás",
            "value": 2,
            "status": "needs_attention",
            "status_label": "Figyelmet kér",
            "color": "#c4923a",
        },
    ]
    render_profile_diagram(rows)
    html = "\n".join(calls)
    assert "Textushűség" in html
    assert "tx-wmap" in html
    assert "100-ból" not in html
