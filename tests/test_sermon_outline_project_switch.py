# -*- coding: utf-8 -*-
"""Projektváltás: stale outline widget ne írja felül az új projekt vázlatát."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_flush_sermon_resyncs_before_persist_avoids_sticky_outline(monkeypatch):
    """A Textus/Bible mintára: resync előbb, majd flush — régi sw_outline_* nem győz."""
    import streamlit as st

    from sermon_workshop_data import (
        SERMON_WORKSHOP_KEY,
        get_default_sermon_workshop,
        normalize_sermon_outline,
    )
    from sermon_workshop_ui import (
        _KEY_OUTLINE,
        _RESYNC_FLAG,
        flush_sermon_workshop_from_widgets,
    )

    # Fake session state dict
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state, raising=False)

    # Project B durable outline (üres / más ige)
    sw = get_default_sermon_workshop()
    sw["sermon_outline"] = normalize_sermon_outline(
        {
            "content": "# Új projekt – Jn 3,16\n\n**Fókuszmondat:** Isten szeret.",
            "main_idea": "Isten szeret.",
            "passage_reference": "Jn 3,16",
        }
    )
    state[SERMON_WORKSHOP_KEY] = sw
    state[_RESYNC_FLAG] = True

    # Stale widget from previous project (Préd 4)
    state[_KEY_OUTLINE["content"]] = (
        "# Beragadt vázlat – Préd 4,9–12\n\n**Fókuszmondat:** Régi tartalom."
    )

    flush_sermon_workshop_from_widgets()

    saved = normalize_sermon_outline(state[SERMON_WORKSHOP_KEY].get("sermon_outline"))
    content = str(saved.get("content") or "")
    assert "Préd 4" not in content
    assert "Jn 3,16" in content or "Isten szeret" in content
    # Widget also resynced from durable
    assert "Préd 4" not in str(state.get(_KEY_OUTLINE["content"]) or "")
