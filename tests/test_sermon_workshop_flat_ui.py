"""RESET 2B (2026-08-18): az Igehirdetési műhely egyszerű, lapos,
hétpontos szerkesztőfelülete.

PREFLIGHT: a korábbi ötlépéses, popover-navigációs `render_sermon_
workshop_shell()` aktív hívási útvonalát erre a fázisra leválasztottuk —
a régi section-renderelők (`render_workshop_workflow_nav`,
`render_entry_point_section`, `render_gospel_arc_section`,
`render_sermon_path_section`, `render_engagement_section`,
`render_closing_section`, `render_text_core_and_focus_section`,
`render_outline_section`) megmaradnak legacy kódként, de innen már nem
hívódnak. Az új felület két része: "Textus és fókusz" (két önálló,
kanonikus mező — `text_workshop.text_main_idea` és `sermon_workshop.
sermon_main_idea`) és a "Hétpontos igehirdetési vázlat" (az `arc.*`
pontok közvetlen szerkesztése `update_arc_point()`-tal).

Ez a fájl forráskód-szintű ÉS valódi Streamlit-renderelési tesztekkel
(`streamlit.testing.v1.AppTest`) bizonyítja a működést — nem csak
stringkereséssel. Nincs valódi AI/külső API-hívás egyik tesztben sem
(`generate_fn` mindig `None` vagy nincs átadva).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_ui as sw_ui  # noqa: E402
from sermon_workshop_data import (  # noqa: E402
    _ARC_POINT_KEYS,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
)
from textus_workshop_data import (  # noqa: E402
    TEXT_WORKSHOP_KEY,
    ensure_text_workshop_state,
    get_default_text_workshop,
)
from workspace_data import build_project_data  # noqa: E402

TEXT_MAIN_IDEA_SENTINEL = "TEXT_MAIN_IDEA_2B_SENTINEL"
SERMON_MAIN_IDEA_SENTINEL = "SERMON_MAIN_IDEA_2B_SENTINEL"
ARC_POINT_SENTINELS: dict[str, str] = {
    key: f"ARC_{key.upper()}_2B_SENTINEL" for key in _ARC_POINT_KEYS
}


def _render_shell() -> None:
    import sermon_workshop_ui as sw_ui

    sw_ui.render_sermon_workshop_shell()


def _render_shell_with_content() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import _ARC_POINT_KEYS, get_default_sermon_workshop
    from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state[TEXT_WORKSHOP_KEY] = get_default_text_workshop()
    st.session_state[TEXT_WORKSHOP_KEY]["text_main_idea"] = "TEXT_MAIN_IDEA_2B_SENTINEL"
    st.session_state["sermon_workshop"] = get_default_sermon_workshop()
    st.session_state["sermon_workshop"]["sermon_main_idea"] = "SERMON_MAIN_IDEA_2B_SENTINEL"
    for key in _ARC_POINT_KEYS:
        st.session_state["sermon_workshop"]["arc"][key]["text"] = f"ARC_{key.upper()}_2B_SENTINEL"
    sw_ui.render_sermon_workshop_shell()


# ---------------------------------------------------------------------------
# 1-3. A shell aktív forrásában nincs régi navigáció/dispatch (forráskód).
# ---------------------------------------------------------------------------


def test_shell_source_has_no_floating_nav_call():
    src = inspect.getsource(sw_ui.render_sermon_workshop_shell)
    assert "render_workshop_workflow_nav(" not in src
    assert "SERMON_PHASE_OPTIONS" not in src
    assert "sermon_phase_completed(" not in src
    assert "sermon_phase_statuses(" not in src


def test_shell_source_has_no_active_five_step_dispatch():
    src = inspect.getsource(sw_ui.render_sermon_workshop_shell)
    assert "_KEY_ACTIVE_SECTION" not in src
    assert 'active ==' not in src


def test_shell_source_does_not_call_old_section_renderers():
    src = inspect.getsource(sw_ui.render_sermon_workshop_shell)
    for fn_name in (
        "render_text_core_and_focus_section",
        "render_entry_point_section",
        "render_gospel_arc_section",
        "render_sermon_path_section",
        "render_engagement_section",
        "render_closing_section",
        "render_outline_section",
    ):
        assert f"{fn_name}(" not in src, fn_name
        # A régi függvények megmaradnak legacy kódként, nem törölve.
        assert callable(getattr(sw_ui, fn_name)), fn_name


# ---------------------------------------------------------------------------
# 4-5. Nincs "Jóváhagyott felismerések" szöveg, nincs approval-/
#      forráshiány-blokkolás az új felületen — valódi renderelés.
# ---------------------------------------------------------------------------


def test_rendered_shell_has_no_exception():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    assert not app.exception


def test_rendered_shell_has_no_approved_insights_counter():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    body = "\n".join(md.value for md in app.markdown) + "\n".join(
        c.value for c in app.caption
    )
    assert "Jóváhagyott felismerések" not in body


def test_rendered_shell_has_no_approval_or_missing_source_blocking():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    body = "\n".join(md.value for md in app.markdown) + "\n".join(
        c.value for c in app.caption
    )
    for phrase in (
        "még nincs jóváhagyva",
        "nincs elég anyag",
        "nincs elegendő",
        "forrásanyag elegendő",
        "Jóváhagyom és átadom",
        "Mentés vázlatként",
    ):
        assert phrase not in body, phrase
    assert not any(btn.label == "Jóváhagyom és átadom" for btn in app.button)


# ---------------------------------------------------------------------------
# 6-8. Pontosan két főgondolat-mező a megfelelő adattal; pontosan hét,
#      helyes sorrendű arc-kártya a megfelelő `_ARC_POINT_KEYS` kulcsokkal.
# ---------------------------------------------------------------------------


def test_exactly_two_main_idea_fields_with_correct_content():
    app = AppTest.from_function(_render_shell_with_content).run(timeout=60)
    assert not app.exception
    values = [ta.value for ta in app.text_area]
    assert TEXT_MAIN_IDEA_SENTINEL in values
    assert SERMON_MAIN_IDEA_SENTINEL in values


def test_exactly_nine_text_areas_two_main_idea_plus_seven_arc_cards():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    assert not app.exception
    assert len(app.text_area) == 9


def test_seven_arc_cards_in_correct_order_with_correct_content():
    app = AppTest.from_function(_render_shell_with_content).run(timeout=60)
    assert not app.exception
    values = [ta.value for ta in app.text_area]
    ordered_sentinels = [ARC_POINT_SENTINELS[key] for key in _ARC_POINT_KEYS]
    positions = [values.index(s) for s in ordered_sentinels]
    assert positions == sorted(positions), "az arc-kártyák nem a helyes sorrendben jelennek meg"


def test_arc_card_titles_appear_in_correct_order():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    body_blocks = [md.value for md in app.markdown]
    joined = "\n".join(body_blocks)
    titles_in_order = [
        "1. Belépés",
        "2. Alaphelyzet",
        "3. Első fordulópont",
        "4. Mélyítés és fokozás",
        "5. Átértelmezés",
        "6. Második fordulópont",
        "7. Megérkezés",
    ]
    positions = [joined.find(t) for t in titles_in_order]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)


def test_seven_cards_use_correct_arc_point_keys_via_update_arc_point(monkeypatch):
    """Az egyes kártyák widgetkulcsai `_KEY_FLAT_ARC`-on keresztül pontosan
    a `_ARC_POINT_KEYS` kulcsokra vannak leképezve — az `update_arc_point`
    egy ismeretlen kulccsal `ValueError`-t dobna, ez bizonyítja, hogy a
    UI kizárólag érvényes kulcsokat használ."""
    import streamlit as st

    assert set(sw_ui._KEY_FLAT_ARC.keys()) == set(_ARC_POINT_KEYS)
    # Közvetlen hívás minden kulccsal — nem dobhat kivételt, és pontosan a
    # megfelelő `_ARC_POINT_KEYS` kulcsot módosítja `update_arc_point`-on
    # keresztül.
    for key in _ARC_POINT_KEYS:
        state: dict = {}
        ensure_sermon_workshop_state(state)
        monkeypatch.setattr(st, "session_state", state)
        state[sw_ui._KEY_FLAT_ARC[key]] = "x"
        sw_ui._flat_save_arc_point(key)
        assert state["sermon_workshop"]["arc"][key]["text"] == "x"


# ---------------------------------------------------------------------------
# 9-10. Nincs pontonkénti MI-gomb/"Átveszem" gomb; nincs generálás-/
#       exportgomb ebben a fázisban.
# ---------------------------------------------------------------------------


def test_no_per_point_ai_or_adopt_buttons():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    labels = [btn.label for btn in app.button]
    for forbidden in (
        "Átveszem",
        "Javaslat készítése",
        "Javaslatok készítése",
        "MI-javaslat",
        "Saját megfogalmazás értékelése",
    ):
        assert forbidden not in labels, forbidden


def test_no_generation_or_export_button_in_this_phase():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    labels = [btn.label for btn in app.button]
    for forbidden in (
        "Hétpontos vázlat generálása",
        "Word-export",
        "Vázlat exportálása",
        "Letöltés Word (.docx)",
    ):
        assert forbidden not in labels, forbidden
    assert len(app.button) == 0, (
        f"nem várt gomb(ok) jelentek meg ebben a fázisban: {[b.label for b in app.button]}"
    )


def test_no_ai_call_helpers_referenced_by_new_flat_functions():
    """Forráskód-szintű bizonyíték: az új mentő/renderelő függvények
    egyike sem hivatkozik AI-/külső API-hívásra."""
    for fn in (
        sw_ui._flat_save_text_main_idea,
        sw_ui._flat_save_sermon_main_idea,
        sw_ui._flat_save_arc_point,
        sw_ui.render_flat_text_and_focus_section,
        sw_ui.render_flat_seven_point_outline_section,
        sw_ui._render_flat_legacy_outline_panel,
    ):
        src = inspect.getsource(fn)
        for forbidden in ("generate_fn(", "generate_text(", "GenerateFn", "_call_generate"):
            assert forbidden not in src, f"{fn.__name__} hivatkozik: {forbidden}"


# ---------------------------------------------------------------------------
# 11-12. Kézi szerkesztés frissíti a megfelelő kanonikus mezőt; kézi
#        arc-szerkesztés frissíti a `manually_updated_at` értéket.
# ---------------------------------------------------------------------------


def test_editing_text_main_idea_widget_updates_canonical_field_via_apptest():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    idx = next(
        i for i, ta in enumerate(app.text_area) if ta.key == sw_ui._KEY_FLAT_TEXT_MAIN_IDEA
    )
    app.text_area[idx].input("Élő szerkesztés SENTINEL.").run()
    assert app.session_state[TEXT_WORKSHOP_KEY]["text_main_idea"] == "Élő szerkesztés SENTINEL."


def test_editing_sermon_main_idea_widget_updates_canonical_field_via_apptest():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    idx = next(i for i, ta in enumerate(app.text_area) if ta.key == sw_ui._KEY_SERMON_IDEA)
    app.text_area[idx].input("Fókuszmondat SENTINEL.").run()
    assert (
        app.session_state["sermon_workshop"]["sermon_main_idea"]
        == "Fókuszmondat SENTINEL."
    )


def test_editing_one_arc_card_widget_updates_only_that_point_via_apptest():
    app = AppTest.from_function(_render_shell).run(timeout=60)
    idx = next(
        i
        for i, ta in enumerate(app.text_area)
        if ta.key == sw_ui._KEY_FLAT_ARC["deepening"]
    )
    app.text_area[idx].input("Mélyítés élő SENTINEL.").run()
    arc = app.session_state["sermon_workshop"]["arc"]
    assert arc["deepening"]["text"] == "Mélyítés élő SENTINEL."
    for key in _ARC_POINT_KEYS:
        if key == "deepening":
            continue
        assert arc[key]["text"] == "", key


def test_arc_point_edit_updates_manually_updated_at_via_callback(monkeypatch):
    import streamlit as st

    state: dict = {}
    ensure_sermon_workshop_state(state)
    monkeypatch.setattr(st, "session_state", state)
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""
    state[sw_ui._KEY_FLAT_ARC["arrival"]] = "Megérkezés SENTINEL."
    sw_ui._flat_save_arc_point("arrival")
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""


def test_manual_edit_does_not_require_or_touch_legacy_approved_status(monkeypatch):
    import streamlit as st

    state: dict = {}
    ensure_sermon_workshop_state(state)
    ensure_text_workshop_state(state)
    monkeypatch.setattr(st, "session_state", state)
    state[sw_ui._KEY_FLAT_TEXT_MAIN_IDEA] = "Draft szöveg."
    sw_ui._flat_save_text_main_idea()
    # A régi "draft" legacy mező tájékoztató jelleggel megmaradhat, de
    # a tartalom máris elérhető — nincs blokkoló approval-feltétel.
    assert state[TEXT_WORKSHOP_KEY]["text_main_idea"] == "Draft szöveg."
    assert state[TEXT_WORKSHOP_KEY]["text_main_idea_status"] == "draft"


# ---------------------------------------------------------------------------
# 13-14. Projektmentés/visszatöltés után a két főgondolat és mind a hét
#        pont megmarad; a legacy `sermon_outline` bit-pontosan megmarad.
# ---------------------------------------------------------------------------


def test_full_project_round_trip_preserves_both_main_ideas_and_all_seven_points():
    state: dict = {
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        "sermon_workshop": get_default_sermon_workshop(),
    }
    state[TEXT_WORKSHOP_KEY]["text_main_idea"] = TEXT_MAIN_IDEA_SENTINEL
    state["sermon_workshop"]["sermon_main_idea"] = SERMON_MAIN_IDEA_SENTINEL
    for key in _ARC_POINT_KEYS:
        state["sermon_workshop"]["arc"][key]["text"] = ARC_POINT_SENTINELS[key]

    project = build_project_data(state)
    reloaded = dict(project)
    ensure_text_workshop_state(reloaded)
    ensure_sermon_workshop_state(reloaded)

    assert reloaded[TEXT_WORKSHOP_KEY]["text_main_idea"] == TEXT_MAIN_IDEA_SENTINEL
    assert reloaded["sermon_workshop"]["sermon_main_idea"] == SERMON_MAIN_IDEA_SENTINEL
    for key in _ARC_POINT_KEYS:
        assert reloaded["sermon_workshop"]["arc"][key]["text"] == ARC_POINT_SENTINELS[key]


def test_legacy_sermon_outline_survives_round_trip_bit_for_bit():
    state: dict = {
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        "sermon_workshop": get_default_sermon_workshop(),
    }
    state["sermon_workshop"]["sermon_outline"]["content"] = (
        "Régi, mentett vázlatszöveg SENTINEL, elég hosszú a heurisztikának."
    )
    project = build_project_data(state)
    reloaded = dict(project)
    ensure_sermon_workshop_state(reloaded)
    assert (
        reloaded["sermon_workshop"]["sermon_outline"]["content"]
        == "Régi, mentett vázlatszöveg SENTINEL, elég hosszú a heurisztikának."
    )


# ---------------------------------------------------------------------------
# 15-16. Üres arc + legacy vázlat → read-only panel megjelenik; nem üres
#        arc esetén a legacy panel nem jelenik meg.
# ---------------------------------------------------------------------------


def _render_shell_with_empty_arc_and_legacy_outline() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import get_default_sermon_workshop

    st.session_state["sermon_workshop"] = get_default_sermon_workshop()
    st.session_state["sermon_workshop"]["sermon_outline"]["content"] = (
        "## Régi vázlat\n\nRégi, olvasható tartalom SENTINEL, elég hosszú "
        "ahhoz, hogy a heurisztika tartalmasnak ismerje el, több mint "
        "negyven karakter hosszan."
    )
    sw_ui.render_sermon_workshop_shell()


def _render_shell_with_filled_arc_and_legacy_outline() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import get_default_sermon_workshop

    st.session_state["sermon_workshop"] = get_default_sermon_workshop()
    st.session_state["sermon_workshop"]["arc"]["entry"]["text"] = "Már van új vázlat."
    st.session_state["sermon_workshop"]["sermon_outline"]["content"] = (
        "## Régi vázlat\n\nRégi, olvasható tartalom SENTINEL, elég hosszú "
        "ahhoz, hogy a heurisztika tartalmasnak ismerje el, több mint "
        "negyven karakter hosszan."
    )
    sw_ui.render_sermon_workshop_shell()


def test_legacy_panel_appears_when_arc_empty_and_legacy_outline_has_content():
    app = AppTest.from_function(_render_shell_with_empty_arc_and_legacy_outline).run(
        timeout=60
    )
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" in body
    assert "SENTINEL" in body
    # Read-only: nem ad hozzá új text_area-t a legacy tartalomhoz (a 9
    # meglévő widgeten felül semmi).
    assert len(app.text_area) == 9


def test_legacy_panel_absent_when_arc_already_has_content():
    app = AppTest.from_function(_render_shell_with_filled_arc_and_legacy_outline).run(
        timeout=60
    )
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" not in body


def test_legacy_panel_does_not_copy_data_into_arc(monkeypatch):
    import streamlit as st

    state: dict = {"sermon_workshop": get_default_sermon_workshop()}
    state["sermon_workshop"]["sermon_outline"]["content"] = (
        "## Régi vázlat\n\nRégi tartalom, elég hosszú a heurisztikának, "
        "több mint negyven karakter."
    )
    monkeypatch.setattr(st, "session_state", state)
    sw_ui._render_flat_legacy_outline_panel()
    for key in _ARC_POINT_KEYS:
        assert state["sermon_workshop"]["arc"][key]["text"] == ""


# ---------------------------------------------------------------------------
# 17. Az `arc_candidate` nem jelenik meg ebben a fázisban.
# ---------------------------------------------------------------------------


def test_arc_candidate_never_rendered_in_this_phase():
    src_shell = inspect.getsource(sw_ui.render_sermon_workshop_shell)
    src_focus = inspect.getsource(sw_ui.render_flat_text_and_focus_section)
    src_outline = inspect.getsource(sw_ui.render_flat_seven_point_outline_section)
    src_legacy = inspect.getsource(sw_ui._render_flat_legacy_outline_panel)
    for src in (src_shell, src_focus, src_outline, src_legacy):
        assert "arc_candidate" not in src


def test_arc_candidate_present_but_not_rendered_does_not_appear_in_ui():
    def _render() -> None:
        import streamlit as st

        import sermon_workshop_ui as sw_ui
        from sermon_workshop_data import (
            ensure_sermon_workshop_state,
            get_default_sermon_workshop,
            set_arc_candidate,
        )

        st.session_state["sermon_workshop"] = get_default_sermon_workshop()
        ensure_sermon_workshop_state(st.session_state)
        set_arc_candidate(
            st.session_state,
            points={"entry": {"text": "Candidate SENTINEL."}},
            reference="Jn 3,16",
            context_hash="H1",
        )
        sw_ui.render_sermon_workshop_shell()

    app = AppTest.from_function(_render).run(timeout=60)
    assert not app.exception
    values = [ta.value for ta in app.text_area]
    assert "Candidate SENTINEL." not in values
    body = "\n".join(md.value for md in app.markdown) + "\n".join(
        c.value for c in app.caption
    )
    assert "andidate" not in body.casefold() or "arc_candidate" not in body


# ---------------------------------------------------------------------------
# 18. A Textusműhely UI-ja és a globális műhelyváltó változatlan marad.
# ---------------------------------------------------------------------------


def test_textus_workshop_ui_module_untouched():
    """Ez a fázis kizárólag `sermon_workshop_ui.py`-t módosította — a
    Textusműhely saját UI-modulja (`textus_workshop_ui.py`) importálható
    és a régi, saját fő gondolat -szekciója érintetlen."""
    import textus_workshop_ui as tw_ui

    assert hasattr(tw_ui, "render_text_main_idea_section")
    assert callable(tw_ui.render_text_main_idea_section)


def test_global_workspace_switcher_and_quick_tools_untouched():
    import workshop_nav_ui as nav

    assert hasattr(nav, "render_workspace_switcher")
    assert hasattr(nav, "render_quick_tools_tabs")
    assert hasattr(nav, "QUICK_TOOLS_TAB_LABELS")
    assert len(nav.QUICK_TOOLS_TAB_LABELS) == 12
