# ruff: noqa: E402
"""Regresszió: mentés, műhelyváltás, lépésválasztó, vázlat, diagnosztika, imaív.

Ellenőrzi, hogy a közelmúltbeli UI / adatfolyam-módosítások nem rontják
egymást, és a kulcsfolyamatok együtt is működnek.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_diagnostics_ai import run_outline_diagnostics
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    save_prayer_after_suggestions,
    save_prayer_before_suggestions,
    save_sermon_outline,
    update_sermon_workshop_section,
)
from sermon_workshop_m9_prayer_ai import (
    build_prayer_source_caption,
    suggest_prayer_after,
    suggest_prayer_before,
)
from sermon_workshop_outline_ai import (
    assemble_sermon_outline,
    build_outline_from_workshop,
    collect_available_sermon_material,
    outline_has_content,
)
from sermon_workshop_ui import (
    _KEY_PRAYER_BEFORE,
    _collect_prayer_kwargs,
    _prayer_plan_fingerprint,
    _prayer_plan_is_edited,
    _prayer_baseline_key,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, ensure_text_workshop_state
from ui_theme import premium_overlay_css, premium_tokens_css
from workshop_nav_ui import (
    completed_step_indices,
    sermon_completed_sections,
    textus_completed_sections,
)
from workspace_data import build_project_data, sanitize_project_data


def _stub_json(payload: dict[str, Any]):
    raw = json.dumps(payload, ensure_ascii=False)

    def _fn(*_a, **_k):
        return raw

    return _fn


def _before_payload() -> dict[str, Any]:
    return {
        "purpose": "Megnyílás",
        "recommended_movements": [
            {"title": "Nyitás", "function": "address", "content_direction": "Uram."},
            {"title": "Csend", "function": "silence", "content_direction": "Csend."},
            {
                "title": "Világosság",
                "function": "illumination",
                "content_direction": "Adj világosságot.",
            },
            {
                "title": "Átadás",
                "function": "preacher",
                "content_direction": "Áldd a szolgálatot.",
            },
        ],
        "opening_options": ["Uram, szólj."],
        "suggested_lines": [],
        "closing_direction": "Nyisd meg a szívünket.",
        "integrated_user_thoughts": [],
        "language_notes": [],
        "cliche_risks": [],
        "warnings": [],
        "missing_information": [],
    }


def _after_payload() -> dict[str, Any]:
    return {
        "purpose": "Válasz",
        "recommended_movements": [
            {"title": "Hála", "function": "gratitude", "content_direction": "Köszönjük."},
            {
                "title": "Bizalom",
                "function": "gospel_trust",
                "content_direction": "Ráhagyatkozunk.",
            },
            {"title": "Kérés", "function": "request", "content_direction": "Erősíts."},
            {
                "title": "Reménység",
                "function": "hope",
                "content_direction": "Tarts meg.",
            },
        ],
        "opening_options": ["Köszönjük."],
        "suggested_lines": [],
        "closing_direction": "Maradj velünk.",
        "integrated_user_thoughts": [],
        "language_notes": [],
        "cliche_risks": [],
        "warnings": [],
        "missing_information": [],
    }


@pytest.fixture
def session(monkeypatch):
    state: dict = {
        "last_igehely": "Júd 17–20",
        "passage_text": "17 Ti pedig…",
        "bible_translation": "RÚF 2014",
        "ui_mode": "sermon_workshop",
        TEXT_WORKSHOP_KEY: {
            "text_main_idea": "Őrizzétek magatokat Isten szeretetében.",
            "text_main_idea_status": "approved",
            "approved_insights": [{"content": "Megtartó szeretet"}],
        },
        "exegesis": "Apostoli figyelmeztetés.",
        "theology": "Isten megtart.",
    }
    monkeypatch.setattr(st, "session_state", state)
    ensure_text_workshop_state(state)
    ensure_sermon_workshop_state(state)
    update_sermon_workshop_section(
        state,
        "sermon_main_idea",
        {
            "sermon_main_idea": "Isten megtartja népét.",
            "sermon_main_idea_status": "approved",
        },
    )
    update_sermon_workshop_section(
        state,
        "christ_centered_arc",
        {"divine_gracious_action": "Megtart Krisztusban."},
    )
    update_sermon_workshop_section(
        state,
        "listener_tension",
        {"promised_resolution": "Ő megőriz."},
    )
    return state


def test_css_mainnav_and_prayer_not_conflicting():
    """Főmenü és imádság CSS együtt él a design tokenekkel."""
    tokens = premium_tokens_css()
    overlay = premium_overlay_css()
    assert "--tx-primary:" in tokens
    assert ".st-key-workspace_switcher" in overlay
    assert ".st-key-workspace_intro" in overlay
    assert ".st-key-textus_app_toolbar" in overlay
    assert ".st-key-project_picker_content" in overlay or "project_picker_content" in overlay
    assert 'key="bar_projects_open"' in (
        (ROOT / "workshop_nav_ui.py").read_text(encoding="utf-8")
    )
    assert "_PROJECTS_POPOVER_DISMISS_JS" not in (
        (ROOT / "workshop_nav_ui.py").read_text(encoding="utf-8")
    )
    assert ".st-key-quick_tools_grid" in overlay
    assert ".tx-quick-tools" in overlay or ".st-key-quick_tools_grid" in overlay
    # Gyorseszköz kártyákon ne legyen CSS ::before tartalomikon
    assert 'content: "\\f518"' not in overlay
    assert ".tx-prayer-quick" in overlay
    assert "repeat(3, minmax(0, 1fr))" in overlay
    assert "stColumn" in overlay or "flex: 1 1 0" in overlay
    # Ne legyen erős gradient a főmenü gombokon
    assert "linear-gradient(120deg" not in overlay.split(".tx-prayer-quick")[0]
    # Mobil: felirat ne törjön a toolbar-on / switcher címke nowrap
    assert "white-space: nowrap" in overlay
    # Kompakt switcher magasság
    assert "min-height: 46px" in overlay
    # Projektek min. szélesség
    assert "min-width: 112px" in overlay
    # Ceruzaikon a11y címke
    assert "bar_title_edit" in overlay or "Projekt nevének szerkesztése" in (
        __import__("pathlib").Path("workshop_nav_ui.py").read_text(encoding="utf-8")
    )
    # Gyorseszközök: 4 oszlopos grid keyed konténerrel
    assert "repeat(4, minmax(0, 1fr))" in overlay

def test_project_save_preserves_outline_diag_prayer(session):
    """Mentés: vázlat + diagnosztika + mindkét imaív megmarad.

    2026-08-13, Fázis 2B: `synthesize=False` megszűnt — a nem-mechanikus
    SEED-építőt (`build_outline_from_workshop`) közvetlenül használjuk."""
    outline = build_outline_from_workshop(session)
    save_sermon_outline(session, outline, mark_manual_edit=False)
    assert outline_has_content(outline)

    diag = run_outline_diagnostics(
        sermon_outline=outline,
        passage="Júd 17–20",
        sermon_main_idea="Isten megtartja népét.",
        generate_fn=lambda *_a, **_k: json.dumps(
            {
                "overview": "Rendben.",
                "diagnostic_areas": [
                    {"key": "text_fidelity", "score": 4, "note": "ok"},
                    {"key": "unity_and_focus", "score": 4, "note": "ok"},
                    {"key": "listener_tension", "score": 3, "note": "ok"},
                    {"key": "christ_centeredness", "score": 4, "note": "ok"},
                    {"key": "sermon_path", "score": 3, "note": "ok"},
                    {"key": "application", "score": None, "note": "hiány"},
                    {"key": "closing", "score": 3, "note": "ok"},
                    {"key": "pastoral_responsibility", "score": 4, "note": "ok"},
                ],
                "strengths": ["Textushűség"],
                "refinements": ["Alkalmazás"],
            },
            ensure_ascii=False,
        ),
    )
    assert diag.ok is True
    assert diag.mode == "ai"

    save_prayer_before_suggestions(session, {**_before_payload(), "ok": True})
    save_prayer_after_suggestions(session, {**_after_payload(), "ok": True})

    payload = sanitize_project_data(build_project_data(session))
    sw = payload[SERMON_WORKSHOP_KEY]
    assert outline_has_content(sw.get("sermon_outline"))
    assert sw["prayer_preparation"]["before_suggestions"]["opening_options"]
    assert sw["prayer_preparation"]["after_suggestions"]["opening_options"]
    assert (
        sw["prayer_preparation"]["before_suggestions"]["opening_options"]
        != sw["prayer_preparation"]["after_suggestions"]["opening_options"]
    )


def test_workshop_mode_switch_and_step_helpers(session):
    """Műhelyváltás state + lépésválasztó completed indexek."""
    assert session["ui_mode"] == "sermon_workshop"
    session["ui_mode"] = "workshop"
    assert session["ui_mode"] == "workshop"
    session["ui_mode"] = "sermon_workshop"

    text_done = textus_completed_sections(session)
    assert "Igehely, alkalom és szövegkörnyezet" in text_done
    assert "A textus fő gondolata" in text_done

    sermon_done = sermon_completed_sections(session)
    assert "Az igehirdetés fő gondolata" in sermon_done

    opts = ["A", "B", "C"]
    assert completed_step_indices(opts, {"B"}) == [1]


def test_outline_material_feeds_prayer_and_diagnostics(session):
    """Közös anyaggyűjtő: vázlat + imaív + diagnosztika ugyanazt a forrást látja."""
    bundle = collect_available_sermon_material(session)
    assert "passage_reference" in bundle.get("source_keys", []) or bundle.get(
        "passage_reference"
    )
    assert bundle.get("text_main_idea") or bundle.get("sermon_main_idea")

    outline = build_outline_from_workshop(session)
    save_sermon_outline(session, outline, mark_manual_edit=False)

    kwargs = _collect_prayer_kwargs()
    assert kwargs.get("passage")
    assert kwargs.get("source_keys")
    assert outline_has_content(kwargs.get("sermon_outline")) or kwargs.get(
        "sermon_main_idea"
    )

    prayer_kwargs = {
        k: v for k, v in kwargs.items() if not str(k).startswith("_")
    }
    before = suggest_prayer_before(
        **prayer_kwargs,
        generate_fn=_stub_json(_before_payload()),
    )
    assert before.ok
    assert before.source_caption

    after = suggest_prayer_after(
        **prayer_kwargs,
        generate_fn=_stub_json(_after_payload()),
    )
    assert after.ok

    save_prayer_before_suggestions(session, before.to_dict())
    save_prayer_after_suggestions(session, after.to_dict())
    prep = session[SERMON_WORKSHOP_KEY]["prayer_preparation"]
    assert prep["before_suggestions"]["opening_options"]
    assert prep["after_suggestions"]["opening_options"]
    assert (
        prep["after_suggestions"]["opening_options"]
        != prep["before_suggestions"]["opening_options"]
    )


def test_prayer_modes_quick_and_criteria_and_edit_guard(session):
    """Mindkét imamód + szerkesztésvédelmi fingerprint."""
    quick = suggest_prayer_before(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        text_main_idea="Őrizzétek magatokat.",
        prayer_before={},
        source_keys=["passage_reference", "passage_text", "text_main_idea", "exegesis"],
        generate_fn=_stub_json(_before_payload()),
    )
    assert quick.ok

    criteria = suggest_prayer_before(
        passage="Júd 17–20",
        passage_text="17 Ti pedig…",
        text_main_idea="Őrizzétek magatokat.",
        prayer_before={"own_thoughts": "Kérjük a Szentlélek világosságát."},
        generate_fn=_stub_json(_before_payload()),
    )
    assert criteria.ok

    after = suggest_prayer_after(
        passage="Júd 17–20",
        sermon_outline={
            "main_idea": "Megtartás",
            "movements": [{"core_content": "Őriz"}],
        },
        prayer_after={},
        source_keys=["passage_reference", "sermon_outline", "text_main_idea"],
        generate_fn=_stub_json(_after_payload()),
    )
    assert after.ok
    assert "vázlat" in (after.source_caption or "").casefold()

    session[_KEY_PRAYER_BEFORE["selected_opening"]] = "Uram, szólj."
    session[_KEY_PRAYER_BEFORE["selected_lines"]] = "Pont1\nPont2"
    session[_KEY_PRAYER_BEFORE["closing_direction"]] = "Záró"
    session[_KEY_PRAYER_BEFORE["movement_notes"]] = ""
    session[_KEY_PRAYER_BEFORE["purpose"]] = ""
    session[_KEY_PRAYER_BEFORE["own_thoughts"]] = ""
    from sermon_workshop_ui import _read_prayer_side_from_widgets

    live = _read_prayer_side_from_widgets(_KEY_PRAYER_BEFORE)
    session[_prayer_baseline_key("before")] = _prayer_plan_fingerprint(live)
    assert not _prayer_plan_is_edited("before")
    session[_KEY_PRAYER_BEFORE["selected_opening"]] = "Módosítva"
    assert _prayer_plan_is_edited("before")

    cap, sparse = build_prayer_source_caption(
        source_keys=["passage_reference"], has_outline=False
    )
    assert sparse
    assert "általánosabb" in cap.casefold()


def test_diagnostics_api_failure_no_fake_success(session):
    """Diagnosztika hálózati hibánál ne adjon hamis sikert."""
    outline = build_outline_from_workshop(session)
    save_sermon_outline(session, outline, mark_manual_edit=False)

    def boom(*_a, **_k):
        raise ConnectionError("offline")

    result = run_outline_diagnostics(
        sermon_outline=outline,
        passage="Júd 17–20",
        generate_fn=boom,
    )
    assert result.ok is False
    assert result.mode in ("api_error", "parse_error") or bool(result.error_message)


def test_project_isolation_after_switch(session):
    """Projektváltás: A/B imaív és vázlat nem keveredik."""
    save_prayer_before_suggestions(
        session, {**_before_payload(), "opening_options": ["A nyitó"], "ok": True}
    )
    payload_a = sanitize_project_data(build_project_data(copy.deepcopy(session)))

    other: dict = {"last_igehely": "Jn 3,16", "passage_text": "Mert úgy…"}
    ensure_sermon_workshop_state(other)
    save_prayer_before_suggestions(
        other, {**_before_payload(), "opening_options": ["B nyitó"], "ok": True}
    )
    payload_b = sanitize_project_data(build_project_data(other))

    assert (
        payload_a[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before_suggestions"][
            "opening_options"
        ]
        != payload_b[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before_suggestions"][
            "opening_options"
        ]
    )


def test_mobile_css_touch_targets_present():
    """Mobil media query: kompakt switcher, olvasható címkék."""
    overlay = premium_overlay_css()
    assert "@media (max-width: 768px)" in overlay
    assert "@media (max-width: 390px)" in overlay
    assert "repeat(3, minmax(0, 1fr))" in overlay
    assert "stColumn" in overlay or "flex: 1 1 0" in overlay
    assert ".st-key-workspace_switcher" in overlay
    assert "min-height: 46px" in overlay
    assert ".st-key-workspace_intro" in overlay
