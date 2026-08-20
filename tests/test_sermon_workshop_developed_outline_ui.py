"""RESET 2E-4 — a kétlépcsős vázlatmotor (blueprint + részletes vázlat)
UI-bekötésének tesztjei.

Valódi Streamlit-renderelésen keresztül (`streamlit.testing.v1.AppTest`)
bizonyítja a working — mindig mockolt `generate_fn`-nel, nincs valódi
API-kulcs vagy hálózati hívás. Az `AppTest.from_function` miatt minden
render-segédfüggvény TELJESEN önálló (saját importok, saját inline
adatok) — ez a meglévő `test_sermon_workshop_arc_ai.py`/`test_sermon_
workshop_flat_ui.py` bevett mintája.

A blueprintnek NINCS candidate-lifecycle-ja (RESET 2E-1/2E-2 szerződés,
ITT VÁLTOZATLAN) — sikeres generálás közvetlenül a kanonikus mezőt írja.
A részletes vázlat KÖTELEZŐEN candidate-only (RESET 2E-1A/2E-3) — ez a
fájl elsősorban ezt a lifecycle-t (generate -> candidate -> explicit
accept/discard -> kanonikus) ellenőrzi a UI-n keresztül.
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
