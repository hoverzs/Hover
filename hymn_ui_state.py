"""Session-state helpers for the hymn recommendation UI."""

from __future__ import annotations

from collections.abc import MutableMapping


MAIN_PASSAGE_SOURCE_KEY = "last_igehely"
MAIN_PASSAGE_WIDGET_KEY = "igehely_input"
HYMN_PASSAGE_WIDGET_KEY = "songs_verse"
HYMN_PASSAGE_MANUAL_OVERRIDE_KEY = "_songs_verse_manual_override"
HYMN_PASSAGE_SYNCED_SOURCE_KEY = "_songs_verse_synced_from"


def sync_hymn_passage_from_main_state(state: MutableMapping[str, object]) -> str:
    """Sync the hymn passage widget from the central passage unless overridden."""
    source = _current_main_passage(state)
    current = _clean(state.get(HYMN_PASSAGE_WIDGET_KEY))
    synced_from = _clean(state.get(HYMN_PASSAGE_SYNCED_SOURCE_KEY))
    manual_override = bool(state.get(HYMN_PASSAGE_MANUAL_OVERRIDE_KEY))

    if HYMN_PASSAGE_WIDGET_KEY not in state:
        state[HYMN_PASSAGE_WIDGET_KEY] = ""

    if not source:
        state.setdefault(HYMN_PASSAGE_SYNCED_SOURCE_KEY, "")
        return _clean(state.get(HYMN_PASSAGE_WIDGET_KEY))

    if not manual_override or current == synced_from:
        state[HYMN_PASSAGE_WIDGET_KEY] = source
        state[HYMN_PASSAGE_SYNCED_SOURCE_KEY] = source
        state[HYMN_PASSAGE_MANUAL_OVERRIDE_KEY] = False

    return _clean(state.get(HYMN_PASSAGE_WIDGET_KEY))


def mark_hymn_passage_manual_override(state: MutableMapping[str, object]) -> None:
    """Mark whether the hymn passage widget differs from the last synced source."""
    current = _clean(state.get(HYMN_PASSAGE_WIDGET_KEY))
    synced_from = _clean(state.get(HYMN_PASSAGE_SYNCED_SOURCE_KEY))
    state[HYMN_PASSAGE_MANUAL_OVERRIDE_KEY] = current != synced_from


def _current_main_passage(state: MutableMapping[str, object]) -> str:
    return _clean(state.get(MAIN_PASSAGE_SOURCE_KEY)) or _clean(
        state.get(MAIN_PASSAGE_WIDGET_KEY)
    )


def _clean(value: object) -> str:
    return str(value or "").strip()


__all__ = [
    "HYMN_PASSAGE_MANUAL_OVERRIDE_KEY",
    "HYMN_PASSAGE_SYNCED_SOURCE_KEY",
    "HYMN_PASSAGE_WIDGET_KEY",
    "MAIN_PASSAGE_SOURCE_KEY",
    "MAIN_PASSAGE_WIDGET_KEY",
    "mark_hymn_passage_manual_override",
    "sync_hymn_passage_from_main_state",
]
