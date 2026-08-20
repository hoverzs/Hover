"""RESET 2E-4/2E-5 — a kétlépcsős vázlatmotor (blueprint + részletes
vázlat) UI-bekötésének és a kanonikus vázlat kézi szerkesztésének
tesztjei.

Valódi Streamlit-renderelésen keresztül (`streamlit.testing.v1.AppTest`)
bizonyítja a working — mindig mockolt `generate_fn`-nel, nincs valódi
API-kulcs vagy hálózati hívás. Az `AppTest.from_function` miatt minden
render-segédfüggvény TELJESEN önálló (saját importok, saját inline
adatok) — ez a meglévő `test_sermon_workshop_arc_ai.py`/`test_sermon_
workshop_flat_ui.py` bevett mintája.

A blueprintnek NINCS candidate-lifecycle-ja (RESET 2E-1/2E-2 szerződés,
ITT VÁLTOZATLAN) — sikeres generálás közvetlenül a kanonikus mezőt írja.
A részletes vázlat KÖTELEZŐEN candidate-only (RESET 2E-1A/2E-3) — a
2E-4-es teszt-blokk ezt a lifecycle-t (generate -> candidate -> explicit
accept/discard -> kanonikus) ellenőrzi.

A 2E-5-ös teszt-blokk a MÁR ELFOGADOTT, kanonikus `developed_outline`
kézi szerkesztését ellenőrzi: a candidate-előnézet marad read-only, a
kanonikus movementek tartalmi mezői (title/function/main_claim/
development/*_support/illustration_direction/application_direction/
transition_to_next) szerkeszthetők, de a `key`/`structure_mode`/
mozgás-sorrend/mozgás-darabszám nem.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_ui as sw_ui  # noqa: E402
from sermon_workshop_data import _DEVELOPED_MOVEMENT_LIST_FIELDS  # noqa: E402

REFERENCE = "Jn 3,16"
PASSAGE = "Mert úgy szerette Isten a világot."

ARC_KEYS = (
    "entry",
    "starting_point",
    "first_shift",
    "deepening",
    "reinterpretation",
    "second_shift",
    "arrival",
)


# =============================================================================
# Önálló render-segédfüggvények (AppTest.from_function miatt teljesen
# saját importokkal/adatokkal)
# =============================================================================


def _render_missing_blueprint() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    def fake_gen(prompt, **kwargs):
        raise AssertionError("Hiányzó blueprint mellett nem szabadna AI-hívásnak történnie.")

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_stale_blueprint() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import store_generated_blueprint_result

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint = {
        "central_claim": "X",
        "textual_center": "Y",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "Z",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": ["WARNING_SENTINEL_ÜTKÖZÉS"],
    }
    # SZÁNDÉKOSAN eltérő context_hash az aktuális kanonikus bemenettől
    # számolt hash-től -> a blueprint garantáltan stale lesz.
    store_generated_blueprint_result(
        st.session_state, blueprint=blueprint, context_hash="DELIBERATELY_MISMATCHED_HASH"
    )

    def fake_gen(prompt, **kwargs):
        raise AssertionError("Elavult blueprint mellett nem szabadna AI-hívásnak történnie.")

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_shell_no_generate_fn() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"
    sw_ui.render_sermon_workshop_shell()


def _render_blueprint_invalid_response() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    def fake_gen(prompt, **kwargs):
        return "nem json"

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_fresh_blueprint_with_warnings_no_click() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_blueprint_ai import build_blueprint_generation_context
    from sermon_workshop_data import store_generated_blueprint_result

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": ["WARNING_SENTINEL_FRESH"],
    }
    ctx_hash = build_blueprint_generation_context(st.session_state).context_hash
    store_generated_blueprint_result(st.session_state, blueprint=blueprint, context_hash=ctx_hash)

    def fake_gen(prompt, **kwargs):
        raise AssertionError("Ebben a tesztben nem kattintunk gombra.")

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_fresh_blueprint_then_generate_outline() -> None:
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint_payload = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }
    outline_payload = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": k,
                "title": f"{k} cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["pont 1", "pont 2"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
            for k in arc_keys
        ],
    }
    if "_bp_call_count" not in st.session_state:
        st.session_state["_bp_call_count"] = 0
    if "_outline_call_count" not in st.session_state:
        st.session_state["_outline_call_count"] = 0

    def fake_gen(prompt, **kwargs):
        if kwargs.get("tab_label") == "Homiletikai blueprint":
            st.session_state["_bp_call_count"] += 1
            return json.dumps(blueprint_payload, ensure_ascii=False)
        st.session_state["_outline_call_count"] += 1
        return json.dumps(outline_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


# =============================================================================
# A. Hiányzó blueprint -> nulla AI-hívás, letiltott gomb, blokkoló üzenet
# =============================================================================


def test_a_missing_blueprint_disables_outline_button_with_message():
    app = AppTest.from_function(_render_missing_blueprint).run(timeout=60)
    assert not app.exception

    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert outline_btn.disabled is True
    captions = [c.value for c in app.caption]
    assert any("Előbb készítsd el a homiletikai blueprintet." in c for c in captions)


# =============================================================================
# B. Elavult blueprint -> nulla AI-hívás, letiltott gomb, blokkoló üzenet
# =============================================================================


def test_b_stale_blueprint_disables_outline_button_with_message():
    app = AppTest.from_function(_render_stale_blueprint).run(timeout=60)
    assert not app.exception

    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert outline_btn.disabled is True
    captions = [c.value for c in app.caption]
    assert any("elavult" in c for c in captions)


def test_b_blueprint_warnings_are_always_visible_and_not_resolvable():
    app = AppTest.from_function(_render_stale_blueprint).run(timeout=60)
    warning_values = [w.value for w in app.warning]
    assert any("WARNING_SENTINEL_ÜTKÖZÉS" in w for w in warning_values)
    # Nincs "feloldás"/"megoldás" gomb a warninghoz.
    labels = [b.label for b in app.button]
    assert not any("felold" in label.lower() or "megold" in label.lower() for label in labels)


# =============================================================================
# C. Friss blueprint -> a részletes vázlat generálása lehetséges
# =============================================================================


def test_c_fresh_blueprint_enables_outline_button_and_shows_warnings():
    app = AppTest.from_function(_render_fresh_blueprint_with_warnings_no_click).run(timeout=60)
    assert not app.exception

    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert outline_btn.disabled is False
    warning_values = [w.value for w in app.warning]
    assert any("WARNING_SENTINEL_FRESH" in w for w in warning_values)
    labels = [b.label for b in app.button]
    assert "Blueprint újragenerálása" in labels


# =============================================================================
# D-E. Sikeres generálás -> KIZÁRÓLAG candidate, kanonikus változatlan
# =============================================================================


def test_d_successful_generation_creates_candidate_only():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Blueprint készítése")
    app.button[bp_idx].click().run()
    # `st.rerun()`-t indító kattintás után egy további `.run()` szükséges
    # a letisztult gomb-fához (ld. `test_h`/`test_i` bővebb magyarázatát).
    app.run(timeout=60)
    assert not app.exception
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []

    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    assert app.button[outline_idx].disabled is False
    app.button[outline_idx].click().run()
    assert not app.exception

    assert app.session_state["_outline_call_count"] == 1
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []
    candidate = app.session_state["sermon_workshop"]["developed_outline_candidate"]
    assert candidate is not None
    assert candidate["outline"]["movements"][0]["key"] == "entry"

    body = "\n".join(md.value for md in app.markdown)
    assert "Új részletes vázlatjavaslat" in body


def test_no_automatic_chaining_from_blueprint_to_outline():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Blueprint készítése")
    app.button[bp_idx].click().run()
    assert not app.exception
    # `_outline_call_count`-ot a render-függvény minden futáson MINDIG
    # inicializálja 0-ra, ha még nincs jelen — így közvetlenül olvasható.
    assert app.session_state["_outline_call_count"] == 0
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []


# =============================================================================
# F. Elfogadás -> kanonikus frissül, candidate törlődik
# =============================================================================


def test_f_accept_writes_canonical_and_clears_candidate():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Blueprint készítése")
    app.button[bp_idx].click().run()
    app.run(timeout=60)
    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    app.button[outline_idx].click().run()
    app.run(timeout=60)

    accept_idx = next(i for i, b in enumerate(app.button) if b.label == "Vázlat átvétele")
    app.button[accept_idx].click().run()
    app.run(timeout=60)
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    movements = app.session_state["sermon_workshop"]["developed_outline"]["movements"]
    assert movements != []
    assert movements[0]["key"] == "entry"

    body = "\n".join(md.value for md in app.markdown)
    assert "Részletes prédikációs munkavázlat" in body


# =============================================================================
# G. Elvetés -> kanonikus NEM változik
# =============================================================================


def test_g_discard_clears_candidate_and_leaves_canonical_untouched():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Blueprint készítése")
    app.button[bp_idx].click().run()
    app.run(timeout=60)
    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    app.button[outline_idx].click().run()
    app.run(timeout=60)

    discard_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Vázlat elvetése"
    )
    app.button[discard_idx].click().run()
    app.run(timeout=60)
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []


# =============================================================================
# H. Regenerálás elfogadás UTÁN -> kanonikus VÁLTOZATLAN
# =============================================================================


def test_h_regeneration_after_accept_never_overwrites_canonical():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Blueprint készítése")
    app.button[bp_idx].click().run()
    app.run(timeout=60)
    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    app.button[outline_idx].click().run()
    app.run(timeout=60)
    accept_idx = next(i for i, b in enumerate(app.button) if b.label == "Vázlat átvétele")
    app.button[accept_idx].click().run()
    # Az elfogadás `st.rerun()`-t indít (`_toast_and_rerun`) — egy
    # további, kattintás nélküli `.run()` szükséges, hogy a gomb-fa
    # ténylegesen a rerun UTÁNI, letisztult állapotot tükrözze (a
    # `sermon_workshop.developed_outline_candidate` session_state-értéke
    # már itt is helyes, de a widget-fa csak az extra run után az).
    app.run(timeout=60)

    canonical_before = app.session_state["sermon_workshop"]["developed_outline"]
    assert canonical_before["movements"] != []

    regen_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat újragenerálása"
    )
    app.button[regen_idx].click().run()
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == canonical_before
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None
    assert app.session_state["_outline_call_count"] == 2


# =============================================================================
# I. Blueprint generálható és újragenerálható; érvénytelen válasz esetén
#    a kanonikus blueprint változatlan és hibaüzenet jelenik meg.
# =============================================================================


def test_i_blueprint_can_be_generated_and_regenerated():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Blueprint készítése")
    app.button[bp_idx].click().run()
    # A sikeres generálás `st.rerun()`-t indít (`_toast_and_rerun`) — egy
    # további, kattintás nélküli `.run()` szükséges, hogy a gomb-fa (és
    # ezzel a "Blueprint készítése" -> "Blueprint újragenerálása" felirat-
    # váltás) ténylegesen a rerun UTÁNI állapotot tükrözze.
    app.run(timeout=60)
    assert not app.exception
    assert app.session_state["sermon_workshop"]["blueprint"]["central_claim"] == (
        "Isten kezdeményez."
    )
    assert app.session_state["_bp_call_count"] == 1

    regen_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Blueprint újragenerálása"
    )
    app.button[regen_idx].click().run()
    assert not app.exception
    assert app.session_state["_bp_call_count"] == 2


def test_i_invalid_blueprint_response_shows_error_and_preserves_canonical():
    app = AppTest.from_function(_render_blueprint_invalid_response).run(timeout=60)
    idx = next(i for i, b in enumerate(app.button) if b.label == "Blueprint készítése")
    app.button[idx].click().run()
    assert not app.exception

    assert app.session_state["sermon_workshop"]["blueprint"]["central_claim"] == ""
    error_values = [e.value for e in app.error]
    assert error_values


# =============================================================================
# J. `generate_fn=None` -> crash-mentes, gombok helyesen letiltva
# =============================================================================


def test_j_generate_fn_none_is_crash_free_and_disables_buttons():
    app = AppTest.from_function(_render_shell_no_generate_fn).run(timeout=60)
    assert not app.exception

    bp_btn = next(b for b in app.button if b.label == "Blueprint készítése")
    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert bp_btn.disabled is True
    assert outline_btn.disabled is True


# =============================================================================
# RESET 2E-5 — a MÁR ELFOGADOTT, kanonikus `developed_outline` kézi
# szerkesztésének tesztjei.
# =============================================================================


def _click_and_settle(app: AppTest, label: str) -> AppTest:
    """Kattintás egy gombra + egy TOVÁBBI, kattintás nélküli `.run()` —
    a `_toast_and_rerun()` által indított `st.rerun()` néha csak egy
    extra `.run()` után tükröződik teljesen a gomb-/widget-fában (ld. a
    2E-4-es blokk hasonló megjegyzéseit). A `session_state` ilyenkor is
    már helyes az első `.run()` után, de a KÖVETKEZŐ gomb/widget
    kereséséhez a letisztult fa kell."""
    idx = next(i for i, b in enumerate(app.button) if b.label == label)
    app.button[idx].click().run()
    app.run(timeout=60)
    return app


def _accept_fresh_outline(app: AppTest) -> AppTest:
    """Blueprint generálás -> részletes vázlat generálás -> elfogadás —
    a `_render_fresh_blueprint_then_generate_outline` render-függvényre
    épülő AppTest-példányon. A végén a kanonikus `developed_outline`
    tartalmazza mind a hét, `entry`...`arrival` kulcsú mozgást."""
    _click_and_settle(app, "Blueprint készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    _click_and_settle(app, "Vázlat átvétele")
    return app


def _text_input_by_key(app: AppTest, key: str):
    return next(ti for ti in app.text_input if ti.key == key)


def _text_input_index_by_key(app: AppTest, key: str) -> int:
    return next(i for i, ti in enumerate(app.text_input) if ti.key == key)


def _text_area_index_by_key(app: AppTest, key: str) -> int:
    return next(i for i, ta in enumerate(app.text_area) if ta.key == key)


# =============================================================================
# 1. Candidate továbbra is read-only
# =============================================================================


def test_candidate_panel_has_no_editable_widgets():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _click_and_settle(app, "Blueprint készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    assert not app.exception

    body = "\n".join(md.value for md in app.markdown)
    assert "Új részletes vázlatjavaslat" in body
    # A kanonikus vázlat még üres -> a szerkesztő szekció nem is renderel
    # semmilyen `sw_flat_outline_edit_*` widgetet.
    outline_widget_keys = [
        ti.key for ti in app.text_input if str(ti.key or "").startswith("sw_flat_outline_edit_")
    ] + [
        ta.key for ta in app.text_area if str(ta.key or "").startswith("sw_flat_outline_edit_")
    ]
    assert outline_widget_keys == []


# =============================================================================
# 2. Kanonikus outline szerkeszthető
# =============================================================================


def test_canonical_outline_is_editable_after_accept():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)
    assert not app.exception

    title_widget = _text_input_by_key(app, "sw_flat_outline_edit_entry_title")
    assert title_widget.value == "entry cím"


# =============================================================================
# 3-4. Egy mező módosítása KIZÁRÓLAG azt a mezőt változtatja; minden más
#      (a mozgás többi mezője, a többi mozgás, structure_mode/note)
#      bit-pontosan változatlan.
# =============================================================================


def test_editing_one_field_changes_only_that_field():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)
    before = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("ÚJ CÍM").run()
    assert not app.exception

    after = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])
    assert after["movements"][0]["title"] == "ÚJ CÍM"
    assert after["movements"][0]["key"] == "entry"

    # Minden más mező/mozgás/szerkezeti adat bit-pontosan változatlan —
    # ha visszaállítjuk a title-t, a két struktúrának egyeznie kell.
    reverted = copy.deepcopy(after)
    reverted["movements"][0]["title"] = before["movements"][0]["title"]
    assert reverted == before


# =============================================================================
# 5. `movement.key` NINCS szerkeszthető widgethez kötve, és a UI sosem
#    hívja a mutátort `field="key"`-jel.
# =============================================================================


def test_movement_key_has_no_editable_widget():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    key_field_widgets = [
        ti.key for ti in app.text_input if str(ti.key or "").endswith("_key")
    ] + [ta.key for ta in app.text_area if str(ta.key or "").endswith("_key")]
    assert key_field_widgets == []


def test_field_widget_sets_never_include_movement_key():
    """Forráskód-szintű garancia: a szerkeszthető mezőkészletek (rövid
    szöveg / textarea / lista) egyike sem tartalmazza a `key`-t — ez
    zárja ki, hogy bármelyik UI-hurok valaha is `field="key"`-jel hívja
    az `update_developed_outline_movement_field`-et."""
    all_editable_fields = (
        set(sw_ui._OUTLINE_SHORT_TEXT_FIELDS)
        | set(sw_ui._OUTLINE_TEXTAREA_FIELDS)
        | set(_DEVELOPED_MOVEMENT_LIST_FIELDS)
    )
    assert "key" not in all_editable_fields


# =============================================================================
# 6. Structure mode/count/order nem módosítható UI-ból
# =============================================================================


def test_no_ui_controls_for_structure_mode_count_or_order():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    labels = [b.label for b in app.button]
    for forbidden in (
        "Mozgás hozzáadása",
        "Mozgás törlése",
        "Mozgás áthelyezése",
        "Szerkezet módosítása",
        "Structure mode módosítása",
    ):
        assert forbidden not in labels

    structure_widget_keys = [
        ti.key for ti in app.text_input if "structure_mode" in str(ti.key or "")
    ] + [ta.key for ta in app.text_area if "structure_mode" in str(ta.key or "")]
    assert structure_widget_keys == []


# =============================================================================
# 7. Rerun után a kézi módosítás megmarad
# =============================================================================


def test_manual_edit_survives_rerun():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("MEGŐRZÖTT CÍM").run()
    assert not app.exception

    app.run(timeout=60)  # kattintás nélküli, tiszta rerun
    idx2 = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    assert app.text_input[idx2].value == "MEGŐRZÖTT CÍM"
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "MEGŐRZÖTT CÍM"
    )


# =============================================================================
# 8-9. Lista-mező többsoros szövege listává alakul, üres sorok kimaradnak
# =============================================================================


def test_list_field_multiline_text_becomes_list_and_drops_empty_lines():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    idx = _text_area_index_by_key(app, "sw_flat_outline_edit_entry_development")
    app.text_area[idx].input("Első gondolat.\n\n  Második gondolat.  \n\n").run()
    assert not app.exception

    development = app.session_state["sermon_workshop"]["developed_outline"]["movements"][0][
        "development"
    ]
    assert development == ["Első gondolat.", "Második gondolat."]


# =============================================================================
# 10. Új AI candidate generálása kézi szerkesztés után NEM módosítja a
#     kanonikus outline-t
# =============================================================================


def test_new_candidate_generation_after_manual_edit_does_not_touch_canonical():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("KÉZI SZERKESZTÉS").run()
    app.run(timeout=60)
    canonical_before = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == canonical_before
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None


# =============================================================================
# 11. Candidate discard után a kézzel szerkesztett kanonikus változat
#     megmarad
# =============================================================================


def test_discard_after_manual_edit_preserves_canonical():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("KÉZI SZERKESZTÉS 2").run()
    app.run(timeout=60)
    canonical_before = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    _click_and_settle(app, "Vázlat elvetése")
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == canonical_before
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None


# =============================================================================
# 12-13. Candidate accept lecseréli a kézzel szerkesztett kanonikus
#        változatot; utána `manually_updated_at` újra üres
# =============================================================================


def test_accept_after_manual_edit_replaces_canonical_and_resets_manually_updated_at():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("KÉZI SZERKESZTÉS 3").run()
    app.run(timeout=60)
    assert (
        app.session_state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"]
        != ""
    )

    _click_and_settle(app, "Részletes vázlat újragenerálása")

    # A candidate-panelen figyelmeztetés jelenik meg, mert a kanonikus
    # kézzel módosítva volt.
    warning_values = [w.value for w in app.warning]
    assert any("Az elfogadás lecseréli" in w for w in warning_values)

    _click_and_settle(app, "Vázlat átvétele")
    assert not app.exception

    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "entry cím"
    )
    assert (
        app.session_state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"]
        == ""
    )


# =============================================================================
# 14. Accept után a régi editor widget-kulcsok törlődnek, és az ÚJ
#     kanonikus értékek jelennek meg (nincs "ragadt" régi szöveg)
# =============================================================================


def test_accept_clears_stale_widget_state_and_shows_new_canonical_value():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("RÉGI SZERKESZTETT SZÖVEG").run()
    app.run(timeout=60)

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    _click_and_settle(app, "Vázlat átvétele")
    assert not app.exception

    idx2 = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    assert app.text_input[idx2].value == "entry cím"
    assert "RÉGI SZERKESZTETT SZÖVEG" not in [ti.value for ti in app.text_input]


# =============================================================================
# 15. `index_out_of_range` nem okoz UI-crasht
# =============================================================================


def _render_index_out_of_range_scenario() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["developed_outline"] = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": "entry",
                "title": "Cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["a"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
        ],
    }
    # Szimulálja azt a legitim futásidejű esetet, amikor egy elavult
    # widget-callback egy MÁR NEM létező indexre hivatkozna (a vázlat
    # időközben megrövidült) — közvetlenül hívja a mentő-callbacket egy
    # a jelenlegi listánál (1 elem) nagyobb indexszel.
    st.session_state["_developed_outline_ioor_probe"] = "not_run"
    try:
        sw_ui._flat_save_developed_outline_movement_field(5, "entry", "title")
        st.session_state["_developed_outline_ioor_probe"] = "no_crash"
    except Exception as exc:  # pragma: no cover — a teszt épp azt bizonyítja, hogy ez nem fut le
        st.session_state["_developed_outline_ioor_probe"] = f"crashed: {exc}"

    sw_ui.render_sermon_workshop_shell()


def test_index_out_of_range_does_not_crash():
    app = AppTest.from_function(_render_index_out_of_range_scenario).run(timeout=60)
    assert not app.exception
    assert app.session_state["_developed_outline_ioor_probe"] == "no_crash"
    # A meglévő, 1 elemű kanonikus vázlat érintetlen maradt.
    assert len(app.session_state["sermon_workshop"]["developed_outline"]["movements"]) == 1
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "Cím"
    )


# =============================================================================
# RESET 2E-6a — state-integritási hardening: a kanonikus `developed_
# outline` upstream frissessége, és a legacy panel egyidejű
# megjelenésének megszüntetése.
# =============================================================================


def _render_blueprint_regenerates_with_different_content() -> None:
    """Az `_render_fresh_blueprint_then_generate_outline`-tól eltérően a
    blueprint-generátor a MÁSODIK hívásra MÁS `central_claim`-mel
    válaszol — ez teszi lehetővé a "friss blueprint, de más tartalom"
    forgatókönyv (RESET 2E-6a, 3. pont) explicit tesztelését."""
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )

    def blueprint_payload(claim: str) -> dict:
        return {
            "central_claim": claim,
            "textual_center": "Úgy szerette Isten...",
            "listener_tension": "",
            "theological_turn": "",
            "desired_listener_movement": "A kételytől a bizalomig.",
            "arc_fit": {"verdict": "strong_fit", "reason": "r"},
            "recommended_structure": {
                "mode": "seven_point",
                "movements": [
                    {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                    for k in arc_keys
                ],
            },
            "key_support": {
                "exegetical": [],
                "original_language": [],
                "historical_theological": [],
            },
            "illustration_direction": "",
            "application_direction": "",
            "warnings": [],
        }

    outline_payload = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": k,
                "title": f"{k} cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["pont 1", "pont 2"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
            for k in arc_keys
        ],
    }

    if "_bp_gen_count" not in st.session_state:
        st.session_state["_bp_gen_count"] = 0

    def fake_gen(prompt, **kwargs):
        if kwargs.get("tab_label") == "Homiletikai blueprint":
            st.session_state["_bp_gen_count"] += 1
            claim = (
                "ELSŐ ÁLLÍTÁS"
                if st.session_state["_bp_gen_count"] == 1
                else "MÁSODIK, MÁS ÁLLÍTÁS"
            )
            return json.dumps(blueprint_payload(claim), ensure_ascii=False)
        return json.dumps(outline_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


# -----------------------------------------------------------------------
# 1. Friss canonical developed outline -> nincs stale warning
# -----------------------------------------------------------------------


def test_fresh_canonical_outline_has_no_stale_warning():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert not any("KORÁBBI blueprintből" in w for w in warning_values)
    assert not any("igehelyhez készült" in w for w in warning_values)


# -----------------------------------------------------------------------
# 2. Blueprint input megváltozik -> canonical outline stale warningot kap
#    (+ 6/7: nem törlődik, továbbra is szerkeszthető)
# -----------------------------------------------------------------------


def test_blueprint_input_change_triggers_stale_warning_but_keeps_content_editable():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["sermon_workshop"]["arc"]["entry"]["text"] = "MEGVÁLTOZOTT_ARC_SZÖVEG"
    app.run(timeout=60)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI blueprintből" in w for w in warning_values)

    # A tartalom NEM törlődött, és továbbra is szerkeszthető.
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] != []
    title_widget = _text_input_by_key(app, "sw_flat_outline_edit_entry_title")
    assert title_widget.disabled is False

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("STALE ÁLLAPOTBAN SZERKESZTETT CÍM").run()
    assert not app.exception
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "STALE ÁLLAPOTBAN SZERKESZTETT CÍM"
    )


# -----------------------------------------------------------------------
# 3. Blueprint újragenerálás (más tartalommal) -> régi canonical outline
#    stale warningot kap, függetlenül attól, hogy kézzel módosítva volt-e
# -----------------------------------------------------------------------


def test_blueprint_regeneration_with_different_content_triggers_stale_warning():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)
    assert app.session_state["sermon_workshop"]["blueprint"]["central_claim"] == "ELSŐ ÁLLÍTÁS"
    old_canonical = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Blueprint újragenerálása")
    assert not app.exception
    assert (
        app.session_state["sermon_workshop"]["blueprint"]["central_claim"]
        == "MÁSODIK, MÁS ÁLLÍTÁS"
    )

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI blueprintből" in w for w in warning_values)
    # A régi canonical outline MEGMARADT, változatlanul.
    assert app.session_state["sermon_workshop"]["developed_outline"] == old_canonical


def test_stale_warning_appears_regardless_of_manual_edit_state():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)

    idx = _text_input_index_by_key(app, "sw_flat_outline_edit_entry_title")
    app.text_input[idx].input("KÉZILEG SZERKESZTETT CÍM").run()
    app.run(timeout=60)

    _click_and_settle(app, "Blueprint újragenerálása")
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI blueprintből" in w for w in warning_values)
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "KÉZILEG SZERKESZTETT CÍM"
    )


# -----------------------------------------------------------------------
# 4. Reference változás -> különösen egyértelmű stale warning
# -----------------------------------------------------------------------


def _render_fresh_blueprint_then_generate_outline_reusable_inputs() -> None:
    """A megosztott `_render_fresh_blueprint_then_generate_outline`
    UNCONDITIONÁLISAN, minden egyes scriptfuttatáson újraírja a
    `last_igehely`/`igehely_input`/`passage_text` mezőket a hardcode-olt
    kezdőértékre — ez elfedné egy, a teszt OLDALÁRÓL (a `.run()` HÍVÁS
    ELŐTT) `app.session_state`-en keresztül végzett külső módosítást,
    mert a scriptfuttatás a saját elején rögtön felülírná.

    Ez a változat `st.session_state.setdefault(...)`-ot használ — csak
    AKKOR ír kezdőértéket, ha a kulcs MÉG NINCS jelen —, így egy a teszt
    által a `.run()` hívás előtt beállított ÚJ érték a következő
    scriptfuttatáson TÉNYLEGESEN érvényesül, ahogy egy valódi
    felhasználói szerkesztés is tenné."""
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state.setdefault("last_igehely", "Jn 3,16")
    st.session_state.setdefault("igehely_input", "Jn 3,16")
    st.session_state.setdefault("passage_text", "Mert úgy szerette Isten a világot.")
    st.session_state.setdefault("bible_translation", "RÚF 2014")

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint_payload = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }
    outline_payload = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": k,
                "title": f"{k} cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["pont 1", "pont 2"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
            for k in arc_keys
        ],
    }

    def fake_gen(prompt, **kwargs):
        if kwargs.get("tab_label") == "Homiletikai blueprint":
            return json.dumps(blueprint_payload, ensure_ascii=False)
        return json.dumps(outline_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def test_reference_change_triggers_reference_changed_warning():
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline_reusable_inputs
    ).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["last_igehely"] = "Róm 8,28"
    app.session_state["igehely_input"] = "Róm 8,28"
    app.run(timeout=60)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any(
        ("igehelyhez készült" in w) and (REFERENCE in w) and ("Róm 8,28" in w)
        for w in warning_values
    )


# -----------------------------------------------------------------------
# 5. Passage text változás -> stale warning
# -----------------------------------------------------------------------


def test_passage_text_change_triggers_stale_warning():
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline_reusable_inputs
    ).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["passage_text"] = "Egy teljesen más bibliai szöveg."
    app.run(timeout=60)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI blueprintből" in w for w in warning_values)


# -----------------------------------------------------------------------
# 8. Új developed-outline candidate generálása (friss blueprintből, a
#    RÉGI canonical mögötti blueprinthez képest) NEM törli a régi
#    canonical outline-t
# -----------------------------------------------------------------------


def test_new_candidate_after_blueprint_regeneration_does_not_touch_old_canonical():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)
    old_canonical = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Blueprint újragenerálása")
    _click_and_settle(app, "Részletes vázlat újragenerálása")
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == old_canonical
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None


# -----------------------------------------------------------------------
# 9. Új candidate accept után a friss canonical context hash friss,
#    a stale warning eltűnik
# -----------------------------------------------------------------------


def test_accept_after_blueprint_regeneration_clears_stale_warning():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)

    _click_and_settle(app, "Blueprint újragenerálása")
    warning_values_before = [w.value for w in app.warning]
    assert any("KORÁBBI blueprintből" in w for w in warning_values_before)

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    _click_and_settle(app, "Vázlat átvétele")
    assert not app.exception

    warning_values_after = [w.value for w in app.warning]
    assert not any("KORÁBBI blueprintből" in w for w in warning_values_after)
    assert not any("igehelyhez készült" in w for w in warning_values_after)


# -----------------------------------------------------------------------
# 10-13. Legacy panel láthatósága érdemi új workflow-állapot mellett
# -----------------------------------------------------------------------

_LEGACY_OUTLINE_CONTENT = {
    "content": (
        "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi ötlépéses "
        "munkafolyamatból, kellően hosszú tartalommal."
    )
}


def _render_legacy_only() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_visible_when_no_new_workflow_state():
    app = AppTest.from_function(_render_legacy_only).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" in body


def _render_legacy_with_blueprint() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state, store_generated_blueprint_result

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint = {
        "central_claim": "X",
        "textual_center": "Y",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "Z",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {"exegetical": [], "original_language": [], "historical_theological": []},
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }
    store_generated_blueprint_result(st.session_state, blueprint=blueprint, context_hash="H1")

    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_hidden_when_blueprint_exists():
    app = AppTest.from_function(_render_legacy_with_blueprint).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" not in body


def _render_legacy_with_outline_candidate() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state, set_developed_outline_candidate

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    set_developed_outline_candidate(
        st.session_state,
        outline={
            "structure_mode": "seven_point",
            "structure_note": "",
            "movements": [
                {
                    "key": "entry",
                    "title": "T",
                    "function": "f",
                    "main_claim": "m",
                    "development": ["d"],
                    "exegetical_support": [],
                    "original_language_support": [],
                    "historical_theological_support": [],
                    "illustration_direction": "",
                    "application_direction": "",
                    "transition_to_next": "",
                }
            ],
        },
        reference="Jn 3,16",
        context_hash="H1",
    )
    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_hidden_when_outline_candidate_exists():
    app = AppTest.from_function(_render_legacy_with_outline_candidate).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" not in body


def _render_legacy_with_canonical_outline() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    sw["developed_outline"] = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": "entry",
                "title": "T",
                "function": "f",
                "main_claim": "m",
                "development": ["d"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
        ],
    }
    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_hidden_when_canonical_outline_exists():
    app = AppTest.from_function(_render_legacy_with_canonical_outline).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" not in body


# -----------------------------------------------------------------------
# 14. Projektváltási widget-state célzott teszt
# -----------------------------------------------------------------------


def _render_project_switch_scenario() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    if not st.session_state.get("_switched_to_project_b"):
        sw["developed_outline"] = {
            "structure_mode": "seven_point",
            "structure_note": "",
            "movements": [
                {
                    "key": "entry",
                    "title": "PROJEKT_A_CIM",
                    "function": "f",
                    "main_claim": "A",
                    "development": ["a"],
                    "exegetical_support": [],
                    "original_language_support": [],
                    "historical_theological_support": [],
                    "illustration_direction": "",
                    "application_direction": "",
                    "transition_to_next": "",
                }
            ],
        }
        sw["developed_outline_meta"] = {
            "reference": "Jn 3,16",
            "context_hash": "A",
            "generated_at": "t",
            "manually_updated_at": "",
        }

    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_project_switch_purges_stale_outline_editor_widgets():
    """RESET 2E-6a: a `_apply_sw_ui_resync_if_needed()`-ba épített
    `_clear_developed_outline_edit_widgets()` hívás ELLENŐRZÉSE — a
    `_sw_ui_resync` jelző UGYANAZ, amit `app.py` projektnyitáskor is
    beállít (`_apply_project_data_to_session`)."""
    app = AppTest.from_function(_render_project_switch_scenario).run(timeout=60)
    title_widget = _text_input_by_key(app, "sw_flat_outline_edit_entry_title")
    assert title_widget.value == "PROJEKT_A_CIM"

    app.session_state["_switched_to_project_b"] = True
    app.session_state["sermon_workshop"]["developed_outline"] = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": "entry",
                "title": "PROJEKT_B_CIM",
                "function": "f",
                "main_claim": "B",
                "development": ["b"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
        ],
    }
    app.session_state["sermon_workshop"]["developed_outline_meta"] = {
        "reference": "Jn 3,16",
        "context_hash": "B",
        "generated_at": "t2",
        "manually_updated_at": "",
    }
    # Ugyanaz a jelző, mint amit `app.py` `_apply_project_data_to_session`-je
    # állít be projekt megnyitásakor.
    app.session_state["_sw_ui_resync"] = True
    app.run(timeout=60)
    assert not app.exception

    title_widget2 = _text_input_by_key(app, "sw_flat_outline_edit_entry_title")
    assert title_widget2.value == "PROJEKT_B_CIM"
