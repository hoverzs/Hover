# ruff: noqa: E402
"""Regresszió: vázlat előnézet minőség — Júd 17–20 minta + banlist.

Az eredeti felhasználói projektet nem módosítja; a build_jude_state()
másolatán dolgozik.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import SERMON_WORKSHOP_KEY, save_sermon_outline
from sermon_workshop_outline_ai import (
    MISSING_PART,
    OUTLINE_PLACEHOLDER_BANLIST,
    build_outline_from_workshop,
    is_banned_outline_placeholder,
    outline_to_readable_content,
    render_compact_sermon_outline,
)
from tests.test_jude_e2e_workflow import build_jude_state
from tests.test_sermon_outline import _stub_streamlit_capture


def test_banlist_detects_templates():
    assert is_banned_outline_placeholder("A textus magja elmélyül.")
    assert is_banned_outline_placeholder("Ez a rész még nincs kidolgozva.")
    assert is_banned_outline_placeholder("Nem állapítható meg felelősen")
    assert not is_banned_outline_placeholder(
        "Isten a gúnyolódók között is megtartja népét."
    )


def test_jude_outline_preview_acceptance(session, monkeypatch):
    """Júd 17–20: elfogadási feltételek a kanonikus előnézetre."""
    state = copy.deepcopy(build_jude_state())
    outline = build_outline_from_workshop(state)
    content = outline_to_readable_content(outline)

    idea = (outline.get("main_idea") or "").strip()
    assert idea
    assert idea.count(".") <= 2 or "\n" not in idea.split(".")[0]
    # Bevezetés ne ismételje szó szerint a fő gondolatot
    opening = (outline.get("opening_direction") or "").strip()
    assert opening
    assert opening != idea
    assert idea not in opening or len(opening) > len(idea) + 20

    mvs = outline.get("movements") or []
    assert 3 <= len(mvs) <= 4
    titles = [str(m.get("title") or "") for m in mvs]
    for banned in ("Nyitás", "Kibontás", "Megérkezés"):
        # Önmagában sablon címként ne szerepeljen
        assert banned not in titles

    assert outline.get("christ_connection") or outline.get("divine_gracious_action")
    assert outline.get("listener_question")
    apps = []
    extra = outline.get("extra_enrichment") or {}
    apps.extend(extra.get("applications") or [])
    for mv in mvs:
        apps.extend(mv.get("applications") or [])
    if outline.get("grace_enabled_response"):
        apps.append(outline["grace_enabled_response"])
    if outline.get("gospel_resolution"):
        apps.append(outline["gospel_resolution"])
    usable_apps = [a for a in apps if str(a or "").strip()]
    assert len(usable_apps) >= 2

    closing = (outline.get("closing") or {}).get("final_insight") or ""
    assert closing.strip()
    assert closing.strip() != idea

    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        assert banned not in content, f"banlist hit: {banned}"
    assert MISSING_PART not in content
    # Nyers mezőnevek / technikai címkék ne jelenjenek meg
    assert "gospel_resolution" not in content
    assert "core_content" not in content
    assert "Kapcsolat típusa" not in content
    assert "Hallgatói felismerés" not in content
    assert "**Központi tartalom:**" not in content
    assert "##" not in content
    # Főnézet szerkezet
    assert "Fókuszmondat" in content
    assert "Bevezetési irány" in content or "Bevezetés" in content
    assert "Megérkezés" in content

    # Truncation artifact
    assert "az útmu" not in content.casefold()

    calls = _stub_streamlit_capture(monkeypatch)
    save_sermon_outline(session, outline)
    render_compact_sermon_outline(session[SERMON_WORKSHOP_KEY]["sermon_outline"])
    joined = "\n".join(calls)
    assert "Textus: Júd 17–20" in joined or "Júd 17–20" in joined
    assert "sw-outline-card" not in joined  # orphan üres kártya nélkül
    assert MISSING_PART not in joined
    assert "Nem állapítható meg felelősen" not in joined


def test_empty_sections_omitted_from_content():
    outline = {
        "passage_reference": "Júd 17–20",
        "bible_translation": "RÚF 2014",
        "main_idea": "Egyetlen világos központi állítás.",
        "opening_direction": "",
        "movements": [
            {
                "id": "m1",
                "title": "Emlékezzetek",
                "textual_basis": "Júd 17",
                "core_content": "Apostoli szavakra emlékezés",
                "listener_discovery": "Nem vagyunk tanácstalanok",
            }
        ],
        "listener_question": "",
        "christ_connection": "",
        "divine_gracious_action": "",
        "closing": {"final_insight": "Kegyelmi megérkezés a megtartó szeretetben."},
        "extra_enrichment": {"applications": []},
    }
    content = outline_to_readable_content(outline)
    assert "Fókuszmondat" in content
    assert "Emlékezzetek" in content
    assert "Megérkezés" in content
    assert MISSING_PART not in content
    # Üres bevezetés ne jelenjen meg
    assert "**Bevezetés**" not in content
    assert "**Bevezetési irány**" not in content
    assert "##" not in content
    assert "Hallgatói felismerés" not in content
    assert "Kapcsolat típusa" not in content


def test_uncertain_christ_label_hidden():
    outline = {
        "passage_reference": "Júd 17–20",
        "main_idea": "Isten megtart.",
        "christ_connection": "Krisztusban van a megtartó szeretet.",
        "christ_connection_type_label": "Nem állapítható meg felelősen",
        "movements": [],
        "closing": {},
    }
    content = outline_to_readable_content(outline)
    assert "Nem állapítható meg felelősen" not in content
    assert "Kapcsolat típusa" not in content
    # A Krisztus-mező a háttérben marad — a főnézetben nem külön fejezet
    assert "Fókuszmondat" in content


def test_truncate_does_not_cut_mid_word():
    from sermon_workshop_outline_ai import _truncate

    long = (
        "Az útmutatás világos: a hívők a Szentlélekben imádkozva őrizzék "
        "meg magukat Isten szeretetében, miközben várják az Úr irgalmát."
    )
    cut = _truncate(long, 60)
    assert "az útmu…" not in cut.casefold()
    assert "…" not in cut or cut.endswith((".", "!", "?")) or " " in cut
    assert not cut.rstrip("…").endswith(("az útmu", "útmu"))


@pytest.fixture
def session(monkeypatch):
    import streamlit as st

    from sermon_workshop_data import ensure_sermon_workshop_state

    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state
