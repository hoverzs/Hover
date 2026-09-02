"""4C — részletes vázlat → Íróasztal egyirányú handoff."""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_TESTS = ROOT / "tests"
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import sermon_workshop_ui as sw_ui  # noqa: E402
import writing_desk_ui  # noqa: E402
from sermon_workshop_data import (  # noqa: E402
    _ARC_POINT_KEYS,
    ensure_sermon_workshop_state,
    set_developed_outline_candidate,
    update_developed_outline_movement_field,
)
from test_sermon_workshop_developed_outline_ui import (  # noqa: E402
    _accept_fresh_outline,
    _click_and_settle,
    _outline_edit_widget_keys,
    _render_fresh_blueprint_then_generate_outline,
)
from workspace_data import EXCLUDED_SESSION_KEYS, project_content_fingerprint  # noqa: E402
from writing_desk_data import (  # noqa: E402
    DRAFT_HTML_ALLOWED_TAGS,
    WRITING_DESK_KEY,
    get_default_writing_desk,
    sanitize_draft_html,
    set_writing_desk_draft,
)
from writing_desk_outline_handoff import (  # noqa: E402
    OUTLINE_HANDOFF_CONFIRM_KEY,
    apply_developed_outline_handoff,
    developed_outline_to_draft_html,
    draft_html_has_forbidden_technical_tokens,
    writing_desk_draft_needs_overwrite_confirmation,
)
from writing_desk_ui import (  # noqa: E402
    WRITING_DESK_DRAFT_RESYNC_FLAG,
    WRITING_DESK_DRAFT_REVISION_KEY,
    WRITING_DESK_DRAFT_WIDGET_KEY,
    WRITING_DESK_MODE,
    commit_writing_desk_draft_from_widget,
    consume_writing_desk_draft_resync_flag,
)

_ARC_FUNCTIONS = {
    "entry": "Belépés",
    "starting_point": "Alaphelyzet",
    "first_shift": "Első fordulópont",
    "deepening": "Mélyítés és fokozás",
    "reinterpretation": "Átértelmezés",
    "second_shift": "Második fordulópont",
    "arrival": "Megérkezés",
}


def _seven_point_outline() -> dict:
    movements = []
    for key in _ARC_POINT_KEYS:
        movements.append(
            {
                "key": key,
                "title": f"{_ARC_FUNCTIONS[key]} címe",
                "function": _ARC_FUNCTIONS[key],
                "main_claim": f"{_ARC_FUNCTIONS[key]} fő állítása",
                "development": [
                    f"{_ARC_FUNCTIONS[key]} kibontás 1",
                    f"{_ARC_FUNCTIONS[key]} kibontás 2",
                ],
                "exegetical_support": [f"{_ARC_FUNCTIONS[key]} szövegi támasz"],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": f"{_ARC_FUNCTIONS[key]} átvezetés",
            }
        )
    return {
        "structure_mode": "seven_point",
        "structure_note": "Rövid szerkezeti megjegyzés a hallgató számára.",
        "movements": movements,
    }


def _html_tags(html: str) -> set[str]:
    return {tag.casefold() for tag in re.findall(r"</?([a-zA-Z]+)", html)}


def _desk_html(session) -> str:
    desk = session[WRITING_DESK_KEY]
    return str((desk.get("draft") or {}).get("content") or "")


def _seed_existing_desk_draft(app: AppTest) -> None:
    desk = get_default_writing_desk()
    desk["draft"]["content"] = "<p>Meglévő jegyzet az Íróasztalon.</p>"
    app.session_state[WRITING_DESK_KEY] = desk


def _session_ui_mode(session) -> str:
    if "ui_mode" not in session:
        return ""
    return str(session["ui_mode"] or "")


def _session_with_candidate(monkeypatch, st, *, with_draft: str = "") -> dict:
    session: dict = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "Mert úgy szerette Isten a világot.",
        "bible_translation": "RÚF 2014",
        "ui_mode": "sermon_workshop",
    }
    monkeypatch.setattr(st, "session_state", session)
    monkeypatch.setattr(writing_desk_ui.st, "session_state", session)
    ensure_sermon_workshop_state(session)
    set_developed_outline_candidate(
        session,
        outline=_seven_point_outline(),
        reference="Jn 3,16",
        context_hash="hash-4c",
    )
    if with_draft:
        set_writing_desk_draft(session, with_draft)
    return session


def test_developed_outline_converts_to_whitelist_html():
    html = developed_outline_to_draft_html(_seven_point_outline())
    assert html
    assert html == sanitize_draft_html(html)
    assert _html_tags(html) <= DRAFT_HTML_ALLOWED_TAGS
    assert not draft_html_has_forbidden_technical_tokens(html)


def test_seven_movements_keep_order_and_cultured_fields():
    html = developed_outline_to_draft_html(_seven_point_outline())
    positions = [html.find(f"{index}. {_ARC_FUNCTIONS[key]}") for index, key in enumerate(_ARC_POINT_KEYS, start=1)]
    assert all(pos >= 0 for pos in positions)
    assert positions == sorted(positions)
    assert "Belépés címe" in html
    assert "Belépés fő állítása" in html
    assert "Belépés kibontás 1" in html
    assert "Átvezetés: Belépés átvezetés" in html
    assert "Szövegi kapaszkodó:" in html
    assert "Háttéranyagok" in html
    assert "<ul>" in html
    assert "<li>" in html
    assert "<strong>" in html


def test_handoff_html_has_no_json_field_names():
    html = developed_outline_to_draft_html(_seven_point_outline())
    for token in (
        "developed_outline",
        "expansion_items",
        "main_claim",
        "transition_to_next",
        "structure_mode",
        "exegetical_support",
        "illustration_direction",
    ):
        assert token not in html


def test_empty_draft_handoff_is_direct(monkeypatch):
    import streamlit as st

    session = _session_with_candidate(monkeypatch, st)
    assert writing_desk_draft_needs_overwrite_confirmation(session) is False
    revision_before = int(session.get(WRITING_DESK_DRAFT_REVISION_KEY) or 0)
    result = apply_developed_outline_handoff(
        session, reference="Jn 3,16", context_hash="hash-4c"
    )
    assert result["accepted"] is True
    assert result["transferred"] is True
    assert session["ui_mode"] == WRITING_DESK_MODE
    assert session["sermon_workshop"]["developed_outline_candidate"] is None
    html = _desk_html(session)
    assert "Belépés címe" in html
    assert session.get(WRITING_DESK_DRAFT_RESYNC_FLAG) is True
    assert int(session.get(WRITING_DESK_DRAFT_REVISION_KEY) or 0) == revision_before
    writing_desk_ui.apply_writing_desk_draft_resync_if_needed()
    assert int(session[WRITING_DESK_DRAFT_REVISION_KEY]) == revision_before + 1
    widget = session[WRITING_DESK_DRAFT_WIDGET_KEY]
    assert "Belépés címe" in str(widget)


def test_substantive_draft_needs_confirmation_unit(monkeypatch):
    import streamlit as st

    session = _session_with_candidate(
        monkeypatch, st, with_draft="<p>Meglévő íróasztal jegyzet.</p>"
    )
    assert writing_desk_draft_needs_overwrite_confirmation(session) is True
    before = _desk_html(session)
    assert apply_developed_outline_handoff is not None
    assert before == "<p>Meglévő íróasztal jegyzet.</p>" or "Meglévő íróasztal jegyzet." in before


def test_existing_draft_shows_overwrite_confirmation_in_ui():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    _click_and_settle(app, "Tervrajz készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    _seed_existing_desk_draft(app)
    app.run(timeout=60)

    _click_and_settle(app, "Szerkesztés az Íróasztalon")
    warnings = "\n".join(w.value for w in app.warning)
    assert "Az Íróasztalon már van jegyzet" in warnings
    labels = [b.label for b in app.button]
    assert "Igen, lecserélem" in labels
    assert "Mégse" in labels
    assert "Szerkesztés az Íróasztalon" not in labels
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None
    assert "Meglévő jegyzet az Íróasztalon." in _desk_html(app.session_state)
    assert _session_ui_mode(app.session_state) != WRITING_DESK_MODE


def test_overwrite_cancel_leaves_existing_draft():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    _click_and_settle(app, "Tervrajz készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    _seed_existing_desk_draft(app)
    app.run(timeout=60)
    _click_and_settle(app, "Szerkesztés az Íróasztalon")
    _click_and_settle(app, "Mégse")

    assert "Meglévő jegyzet az Íróasztalon." in _desk_html(app.session_state)
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None
    confirm = (
        app.session_state[OUTLINE_HANDOFF_CONFIRM_KEY]
        if OUTLINE_HANDOFF_CONFIRM_KEY in app.session_state
        else False
    )
    assert confirm in (False, None)
    labels = [b.label for b in app.button]
    assert "Szerkesztés az Íróasztalon" in labels
    assert _session_ui_mode(app.session_state) != WRITING_DESK_MODE


def test_overwrite_yes_replaces_draft_with_outline():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    _click_and_settle(app, "Tervrajz készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    _seed_existing_desk_draft(app)
    app.run(timeout=60)
    _click_and_settle(app, "Szerkesztés az Íróasztalon")
    _click_and_settle(app, "Igen, lecserélem")

    html = _desk_html(app.session_state)
    assert "Meglévő jegyzet az Íróasztalon." not in html
    assert "entry cím" in html
    assert app.session_state["ui_mode"] == WRITING_DESK_MODE
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert WRITING_DESK_DRAFT_RESYNC_FLAG in app.session_state
    assert app.session_state[WRITING_DESK_DRAFT_RESYNC_FLAG] is True


def test_stale_ccv2_widget_cannot_overwrite_handoff(monkeypatch):
    import streamlit as st

    session = _session_with_candidate(monkeypatch, st)
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": "<p>Régi CCv2 tartalom.</p>"
    }
    apply_developed_outline_handoff(
        session, reference="Jn 3,16", context_hash="hash-4c"
    )
    assert "Belépés címe" in _desk_html(session)
    assert "Régi CCv2 tartalom." not in str(session.get(WRITING_DESK_DRAFT_WIDGET_KEY))
    commit_writing_desk_draft_from_widget()
    assert "Belépés címe" in _desk_html(session)
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {"html": "<p>Régi CCv2 tartalom.</p>"}
    writing_desk_ui.flush_writing_desk_draft_from_widget()
    assert "Belépés címe" in _desk_html(session)
    assert "Régi CCv2 tartalom." not in _desk_html(session)


def test_writing_desk_edit_does_not_write_back_to_structured_outline(monkeypatch):
    import streamlit as st

    session = _session_with_candidate(monkeypatch, st)
    apply_developed_outline_handoff(
        session, reference="Jn 3,16", context_hash="hash-4c"
    )
    outline_before = session["sermon_workshop"]["developed_outline"]["movements"][0][
        "title"
    ]
    consume_writing_desk_draft_resync_flag()
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {"html": "<p>Szabadon átírt vázlat.</p>"}
    commit_writing_desk_draft_from_widget()
    assert _desk_html(session) == "<p>Szabadon átírt vázlat.</p>"
    assert (
        session["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == outline_before
    )


def test_failed_accept_does_not_change_draft_or_ui_mode(monkeypatch):
    import streamlit as st

    session: dict = {"ui_mode": "sermon_workshop"}
    monkeypatch.setattr(st, "session_state", session)
    monkeypatch.setattr(writing_desk_ui.st, "session_state", session)
    ensure_sermon_workshop_state(session)
    set_writing_desk_draft(session, "<p>Maradjon.</p>")
    result = apply_developed_outline_handoff(
        session, reference="Jn 3,16", context_hash="hash-4c"
    )
    assert result["accepted"] is False
    assert result["transferred"] is False
    assert _desk_html(session) == "<p>Maradjon.</p>"
    assert session["ui_mode"] == "sermon_workshop"


def test_handoff_uses_existing_project_fingerprint_path(monkeypatch):
    import streamlit as st

    session = _session_with_candidate(monkeypatch, st)
    before = project_content_fingerprint(session)
    apply_developed_outline_handoff(
        session, reference="Jn 3,16", context_hash="hash-4c"
    )
    after = project_content_fingerprint(session)
    assert before != after
    assert WRITING_DESK_KEY in session
    assert _desk_html(session)


def test_confirm_key_is_session_ephemeral():
    assert OUTLINE_HANDOFF_CONFIRM_KEY in EXCLUDED_SESSION_KEYS


def test_production_ui_drops_second_seven_field_editor():
    section = inspect.getsource(sw_ui.render_flat_developed_outline_section)
    candidate = inspect.getsource(sw_ui._render_developed_outline_candidate_panel)
    shell = inspect.getsource(sw_ui.render_sermon_workshop_shell)
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    ui_src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    assert "_render_developed_outline_canonical_readonly" in section
    assert "_render_developed_outline_movement_editable" not in section
    assert "_render_developed_outline_movement_editable" not in shell
    assert "Vázlat átvétele" not in candidate
    assert "Vázlat átvétele" not in ui_src
    assert "Vázlat átvétele" not in app_src
    assert "Szerkesztés az Íróasztalon" in candidate
    assert "Vázlat elvetése" in candidate
    assert "render_sermon_workshop_shell(generate_fn=generate_text)" in app_src
    assert ui_src.count("_render_developed_outline_movement_editable(") == 1


def test_first_seven_point_editors_remain():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    arc_keys = [
        ta.key for ta in app.text_area if str(ta.key or "").startswith("sw_flat_arc_")
    ]
    assert len(arc_keys) == 7
    labels = [b.label for b in app.button]
    assert "MI-javaslat mind a hét ponthoz" in labels
    assert labels.count("MI-javaslat ehhez a ponthoz") == 7


def test_detailed_outline_generation_and_discard_still_work():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    _click_and_settle(app, "Tervrajz készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    body = "\n".join(md.value for md in app.markdown)
    assert "Új részletes vázlatjavaslat" in body
    _click_and_settle(app, "Vázlat elvetése")
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []


def test_canonical_readonly_not_seven_field_editor_after_handoff():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    _accept_fresh_outline(app)
    assert _outline_edit_widget_keys(app) == []
    captions = "\n".join(c.value for c in app.caption)
    assert "A szabad szerkesztés az Íróasztalon történik." in captions


def test_structured_mutator_still_exists_independently(monkeypatch):
    import streamlit as st

    session = _session_with_candidate(monkeypatch, st)
    apply_developed_outline_handoff(
        session, reference="Jn 3,16", context_hash="hash-4c"
    )
    update_developed_outline_movement_field(
        session, index=0, field="title", value="Domain mutátor"
    )
    assert (
        session["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "Domain mutátor"
    )
    assert "Belépés címe" in _desk_html(session)
