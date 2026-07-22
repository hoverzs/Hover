"""Homiletikai diagnosztikai dashboard — könnyű, függőségmentes SVG-vizualizáció.

A modul szándékosan különálló a fő UI-tól (sermon_workshop_ui), és nem használ
külső chart-könyvtárat: a score ring és a lefedettség gyűrű SVG-kör, a
homiletikai profil pedig könnyű, reszponzív SVG-sokszög (radar jellegű).

Elvek:
- Csak a ténylegesen rendelkezésre álló adatot vizualizáljuk.
- A hiányzó értéket sosem rajzoljuk nullának — semleges „nincs adat” állapot.
- Minden grafikus érték szövegesen is elérhető (aria + látható címke).
- Finom animáció (500–700 ms), a prefers-reduced-motion tiszteletben tartásával.
"""

from __future__ import annotations

import html
import math
from typing import Any, Sequence

import streamlit as st

_DASH_STYLE_FLAG = "_tx_diag_dash_styles"

# Visszafogott, arculatba illő színek.
_C_BLUE = "#5a7aa8"
_C_GREEN = "#4a7c74"
_C_AMBER = "#c4923a"
_C_GREY = "#9a938a"
_C_TRACK = "rgba(160,140,115,0.20)"
_C_GRID = "rgba(120,104,84,0.28)"
_C_INK = "#1f334d"
_C_MUTED = "#6b5a48"


def ensure_dashboard_styles() -> None:
    """A dashboard-specifikus CSS egyszeri beszúrása (session-flaggel)."""
    if st.session_state.get(_DASH_STYLE_FLAG):
        return
    st.session_state[_DASH_STYLE_FLAG] = True
    st.markdown(
        """
<style>
.tx-dgrid {
  display: grid;
  grid-template-columns: minmax(150px, 0.85fr) minmax(150px, 0.85fr) minmax(220px, 1.3fr);
  gap: 1.1rem;
  align-items: center;
}
.tx-dcell { min-width: 0; text-align: center; }
.tx-dcell.-profile { text-align: left; }
.tx-dcell-title {
  font-family: "Inter","Segoe UI",sans-serif;
  font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em;
  text-transform: uppercase; color: #8a6a3f; margin-bottom: 0.5rem;
}
.tx-ring-wrap { display: inline-flex; flex-direction: column; align-items: center; }
.tx-ring-svg .tx-ring-arc {
  transition: stroke-dashoffset 650ms cubic-bezier(0.22, 0.61, 0.36, 1);
}
.tx-ring-center { font-family: "Inter","Segoe UI",sans-serif; }
.tx-ring-big { font-size: 2.1rem; font-weight: 700; fill: #1f334d; }
.tx-ring-sub { font-size: 0.72rem; fill: #6b5a48; }
.tx-ring-qual {
  margin-top: 0.35rem; font-family: "Inter","Segoe UI",sans-serif;
  font-size: 0.9rem; font-weight: 650;
}
.tx-ring-note {
  margin-top: 0.15rem; font-family: "Inter","Segoe UI",sans-serif;
  font-size: 0.78rem; color: #6b5a48; line-height: 1.35; max-width: 22ch;
}
.tx-cov-missing {
  margin-top: 0.35rem; font-size: 0.76rem; color: #6b5a48;
  line-height: 1.35; max-width: 26ch;
}
.tx-profile-poly { transition: opacity 650ms ease; }
.tx-profile-note { font-size: 0.76rem; color: #6b5a48; margin-top: 0.2rem; }
@media (max-width: 820px) {
  .tx-dgrid { grid-template-columns: 1fr; gap: 1.4rem; }
  .tx-dcell, .tx-dcell.-profile { text-align: center; }
  .tx-dcell.-profile .tx-dcell-title { text-align: center; }
}
@media (prefers-reduced-motion: reduce) {
  .tx-ring-svg .tx-ring-arc { transition: none !important; }
  .tx-profile-poly { transition: none !important; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _qual_color(qualifier_key: str) -> str:
    return {
        "strong": _C_GREEN,
        "good": _C_BLUE,
        "improve": _C_AMBER,
        "none": _C_GREY,
    }.get(qualifier_key, _C_GREY)


def render_score_ring(
    *,
    score: int | None,
    qualifier: str,
    qualifier_key: str,
    summary: str,
    sufficient: bool,
) -> None:
    """Kör alakú összesített állapot (score ring), SVG-vel.

    Ha nincs elegendő értékelt terület, a gyűrű semleges szürke, szaggatott,
    közepén „—” és „Nincs elég adat” felirattal.
    """
    size = 150
    stroke = 12
    r = (size - stroke) / 2
    cx = cy = size / 2
    circ = 2 * math.pi * r
    color = _qual_color(qualifier_key)

    if not sufficient or score is None:
        track = (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{_C_TRACK}" stroke-width="{stroke}" '
            f'stroke-dasharray="4 6" />'
        )
        center = (
            f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" '
            f'dominant-baseline="middle" class="tx-ring-big" '
            f'style="fill:{_C_GREY};">—</text>'
            f'<text x="{cx}" y="{cy + 22}" text-anchor="middle" '
            f'class="tx-ring-sub">nincs elég adat</text>'
        )
        aria = "Általános állapot: nincs elég adat az összesített értékhez."
        svg = (
            f'<svg class="tx-ring-svg" width="{size}" height="{size}" '
            f'viewBox="0 0 {size} {size}" role="img" aria-label="{html.escape(aria)}">'
            f"{track}{center}</svg>"
        )
        st.markdown(
            '<div class="tx-ring-wrap">'
            f"{svg}"
            '<div class="tx-ring-qual" style="color:%s;">Nincs elég adat</div>' % _C_GREY
            + (
                f'<div class="tx-ring-note">{html.escape(summary)}</div>'
                if summary
                else ""
            )
            + "</div>",
            unsafe_allow_html=True,
        )
        return

    pct = max(0.0, min(1.0, score / 100.0))
    filled = circ * pct
    offset = circ - filled
    track = (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
        f'stroke="{_C_TRACK}" stroke-width="{stroke}" />'
    )
    arc = (
        f'<circle class="tx-ring-arc" cx="{cx}" cy="{cy}" r="{r}" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-dasharray="{circ:.2f}" stroke-dashoffset="{offset:.2f}" '
        f'transform="rotate(-90 {cx} {cy})" />'
    )
    center = (
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
        f'dominant-baseline="middle" class="tx-ring-big">{score}</text>'
        f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" '
        f'class="tx-ring-sub">100-ból</text>'
    )
    aria = f"Általános állapot: {score} a 100-ból, minősítés: {qualifier}."
    svg = (
        f'<svg class="tx-ring-svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" role="img" aria-label="{html.escape(aria)}">'
        f"{track}{arc}{center}</svg>"
    )
    st.markdown(
        '<div class="tx-ring-wrap">'
        f"{svg}"
        f'<div class="tx-ring-qual" style="color:{color};">{html.escape(qualifier)}</div>'
        + (f'<div class="tx-ring-note">{html.escape(summary)}</div>' if summary else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def render_coverage_ring(
    *,
    evaluated: int,
    total: int,
    missing_labels: Sequence[str],
) -> None:
    """Kisebb kör alakú lefedettségi gyűrű: kiértékelt területek aránya."""
    size = 118
    stroke = 10
    r = (size - stroke) / 2
    cx = cy = size / 2
    circ = 2 * math.pi * r
    frac = (evaluated / total) if total else 0.0
    frac = max(0.0, min(1.0, frac))
    offset = circ - circ * frac

    track = (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
        f'stroke="{_C_TRACK}" stroke-width="{stroke}" />'
    )
    arc = ""
    if evaluated > 0:
        arc = (
            f'<circle class="tx-ring-arc" cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{_C_BLUE}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-dasharray="{circ:.2f}" stroke-dashoffset="{offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" />'
        )
    center = (
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" '
        f'dominant-baseline="middle" class="tx-ring-big" '
        f'style="font-size:1.5rem;">{evaluated}/{total}</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" '
        f'class="tx-ring-sub">terület</text>'
    )
    aria = f"Lefedettség: {evaluated} a {total} területből kiértékelve."
    svg = (
        f'<svg class="tx-ring-svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" role="img" aria-label="{html.escape(aria)}">'
        f"{track}{arc}{center}</svg>"
    )
    if missing_labels:
        shown = ", ".join(html.escape(m) for m in list(missing_labels)[:4])
        extra = "" if len(missing_labels) <= 4 else " …"
        missing_html = (
            f'<div class="tx-cov-missing">Még hiányzik: {shown}{extra}</div>'
        )
    else:
        missing_html = (
            '<div class="tx-cov-missing">Minden terület kiértékelve.</div>'
            if evaluated
            else '<div class="tx-cov-missing">Még egy terület sincs kiértékelve.</div>'
        )
    st.markdown(
        f'<div class="tx-ring-wrap">{svg}{missing_html}</div>',
        unsafe_allow_html=True,
    )


def render_profile_diagram(rows: list[dict[str, Any]]) -> None:
    """Homiletikai profil — könnyű, reszponzív SVG-sokszög (radar jellegű).

    A hiányzó tengelyek nem nullaként jelennek meg: semleges „nincs adat”
    jelzést kapnak, és a diagram jelzi, ha csak részleges profil látható.
    """
    n = len(rows)
    if n == 0:
        st.markdown(
            '<div class="tx-profile-note">Nincs adat a profilhoz.</div>',
            unsafe_allow_html=True,
        )
        return

    size = 260
    cx = cy = size / 2
    max_r = size / 2 - 42  # hely a címkéknek

    def _pt(i: int, radius: float) -> tuple[float, float]:
        ang = -math.pi / 2 + (2 * math.pi * i / n)
        return cx + radius * math.cos(ang), cy + radius * math.sin(ang)

    parts: list[str] = []

    # Koncentrikus rácsgyűrűk (4 szint).
    for level in range(1, 5):
        rr = max_r * level / 4
        ring_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (_pt(i, rr) for i in range(n)))
        parts.append(
            f'<polygon points="{ring_pts}" fill="none" '
            f'stroke="{_C_GRID}" stroke-width="1" opacity="0.6" />'
        )

    # Küllők + címkék.
    for i, row in enumerate(rows):
        ex, ey = _pt(i, max_r)
        parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" '
            f'stroke="{_C_GRID}" stroke-width="1" opacity="0.5" />'
        )
        lx, ly = _pt(i, max_r + 14)
        anchor = "middle"
        if lx > cx + 4:
            anchor = "start"
        elif lx < cx - 4:
            anchor = "end"
        has_val = isinstance(row.get("value"), int)
        fill = _C_INK if has_val else _C_GREY
        label = html.escape(str(row.get("label", "")))
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="middle" style="font-size:9.5px;fill:{fill};'
            f'font-family:Inter,Segoe UI,sans-serif;">{label}</text>'
        )

    evaluated_idx = [i for i, r in enumerate(rows) if isinstance(r.get("value"), int)]

    # Kitöltött sokszög csak akkor, ha minden tengely értékelt.
    if len(evaluated_idx) == n and n >= 3:
        poly_pts = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (
                _pt(i, max_r * (rows[i]["value"] / 4)) for i in range(n)
            )
        )
        parts.append(
            f'<polygon class="tx-profile-poly" points="{poly_pts}" '
            f'fill="rgba(90,122,168,0.20)" stroke="{_C_BLUE}" stroke-width="2" />'
        )
    elif len(evaluated_idx) >= 2:
        # Részleges profil: nyílt vonal csak a szomszédos értékelt tengelyek közt.
        for a, b in zip(evaluated_idx, evaluated_idx[1:]):
            if b - a == 1:
                x1, y1 = _pt(a, max_r * (rows[a]["value"] / 4))
                x2, y2 = _pt(b, max_r * (rows[b]["value"] / 4))
                parts.append(
                    f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                    f'stroke="{_C_BLUE}" stroke-width="2" opacity="0.75" />'
                )

    # Pontok az értékelt tengelyeken.
    for i in evaluated_idx:
        px, py = _pt(i, max_r * (rows[i]["value"] / 4))
        color = str(rows[i].get("color") or _C_BLUE)
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{color}" '
            f'stroke="#fffdf9" stroke-width="1" />'
        )

    aria = "Homiletikai profil, " + "; ".join(
        f"{r.get('label','')}: {r.get('status_label','')}" for r in rows
    )
    svg = (
        f'<svg width="100%" height="{size}" viewBox="0 0 {size} {size}" '
        f'role="img" preserveAspectRatio="xMidYMid meet" '
        f'aria-label="{html.escape(aria)}">' + "".join(parts) + "</svg>"
    )
    st.markdown(svg, unsafe_allow_html=True)

    evaluated = len(evaluated_idx)
    if evaluated == 0:
        note = "Nincs elég adat a homiletikai profilhoz."
    elif evaluated < n:
        note = f"Részleges profil — {evaluated} / {n} terület értékelve."
    else:
        note = f"Teljes profil — mind a(z) {n} terület értékelve."
    st.markdown(
        f'<div class="tx-profile-note">{html.escape(note)}</div>',
        unsafe_allow_html=True,
    )
