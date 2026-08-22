from __future__ import annotations

from hymn_ui_state import (
    HYMN_PASSAGE_MANUAL_OVERRIDE_KEY,
    HYMN_PASSAGE_SYNCED_SOURCE_KEY,
    HYMN_PASSAGE_WIDGET_KEY,
    mark_hymn_passage_manual_override,
    sync_hymn_passage_from_main_state,
)


def test_main_passage_autofills_hymn_passage() -> None:
    state: dict[str, object] = {"last_igehely": "Zsolt 23"}

    result = sync_hymn_passage_from_main_state(state)

    assert result == "Zsolt 23"
    assert state[HYMN_PASSAGE_WIDGET_KEY] == "Zsolt 23"
    assert state[HYMN_PASSAGE_SYNCED_SOURCE_KEY] == "Zsolt 23"
    assert state[HYMN_PASSAGE_MANUAL_OVERRIDE_KEY] is False


def test_main_passage_change_updates_hymn_passage_without_manual_override() -> None:
    state: dict[str, object] = {"last_igehely": "Zsolt 23"}
    sync_hymn_passage_from_main_state(state)
    state["last_igehely"] = "Ézs 53,3-7"

    result = sync_hymn_passage_from_main_state(state)

    assert result == "Ézs 53,3-7"
    assert state[HYMN_PASSAGE_WIDGET_KEY] == "Ézs 53,3-7"
    assert state[HYMN_PASSAGE_SYNCED_SOURCE_KEY] == "Ézs 53,3-7"


def test_manual_override_is_preserved_when_main_passage_changes() -> None:
    state: dict[str, object] = {"last_igehely": "Zsolt 23"}
    sync_hymn_passage_from_main_state(state)
    state[HYMN_PASSAGE_WIDGET_KEY] = "Jn 10,11-16"
    mark_hymn_passage_manual_override(state)
    state["last_igehely"] = "Ézs 53,3-7"

    result = sync_hymn_passage_from_main_state(state)

    assert result == "Jn 10,11-16"
    assert state[HYMN_PASSAGE_WIDGET_KEY] == "Jn 10,11-16"
    assert state[HYMN_PASSAGE_MANUAL_OVERRIDE_KEY] is True


def test_empty_main_passage_does_not_error() -> None:
    state: dict[str, object] = {}

    result = sync_hymn_passage_from_main_state(state)

    assert result == ""
    assert state[HYMN_PASSAGE_WIDGET_KEY] == ""
