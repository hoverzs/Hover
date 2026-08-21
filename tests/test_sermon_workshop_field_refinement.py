"""RESET 2D-B1 — célzott, elfogadásos MI-pontosítás kilenc egymástól
teljesen független célmezőhöz (két főgondolat + hét arc-pont).

Két rétegben tesztel:
  - a `sermon_workshop_refinement_ai` modul tiszta motorlogikáját és a
    `sermon_workshop_data.py` új `field_refinements` adatmodell-
    függvényeit, hálózatmentes, mockolt `generate_fn`-nel;
  - a `sermon_workshop_ui` gomb-/panel-bekötését valódi Streamlit-
    renderelésen keresztül (`streamlit.testing.v1.AppTest`), szintén
    mindig mockolt `generate_fn`-nel.

Nincs valódi API-kulcs vagy külső hálózat egyik tesztben sem.
"""

from __future__ import annotations

import copy
import inspect
import sys
from pathlib import Path

import pytest
from streamlit.commands.execution_control import rerun as _real_st_rerun
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _restore_streamlit_rerun():
    """Védekező helyreállítás: legalább egy meglévő, ehhez a fázishoz nem
    kapcsolódó tesztfájl (`tests/test_passage_search.py`) a `streamlit.
    rerun`-t közvetlen attribútum-hozzárendeléssel (nem `monkeypatch`-
    csel) írja felül, és a `finally`-ágában elfelejti visszaállítani —
    ez a folyamat hátralévő részére egy no-op `rerun`-re cseréli a
    VALÓDI függvényt, ami ennek a fájlnak az `st.rerun()`-re támaszkodó
    AppTest-tesztjeit (a „MI-vel pontosítom” panel automatikus
    megnyitását) hamisan buktatja el, ha a pytest-futás sorrendje úgy
    hozza. Ez a fixture minden itteni teszt előtt biztosítja a valódi
    `st.rerun`-t — magát a másik fájl hibáját NEM javítja (ez a fázis
    hatóköre kizárólag `sermon_workshop_ui.py` és az ide tartozó
    UI-tesztfájlok)."""
    import streamlit as st

    st.rerun = _real_st_rerun
    yield

import sermon_workshop_refinement_ai as refine_ai  # noqa: E402
import sermon_workshop_ui as sw_ui  # noqa: E402
from sermon_workshop_data import (  # noqa: E402
    _ARC_POINT_KEYS,
    _REFINEMENT_FIELD_KEYS,
    discard_field_refinement_suggestion,
    ensure_sermon_workshop_state,
    set_field_refinement_suggestion,
    update_arc_point,
    update_sermon_workshop_section,
    validate_field_refinement_acceptance,
)
from textus_workshop_data import ensure_text_workshop_state, update_text_main_idea  # noqa: E402
from workspace_data import build_project_data  # noqa: E402

SUGGESTION_TEXT = "Ez egy pontosított javaslat szöveg."


def _base_state() -> dict:
    state: dict = {}
    ensure_sermon_workshop_state(state)
    ensure_text_workshop_state(state)
    state["last_igehely"] = "Jn 3,16"
    state["igehely_input"] = "Jn 3,16"
    state["passage_text"] = "Mert úgy szerette Isten a világot."
    state["bible_translation"] = "RÚF 2014"
    return state


class _CountingGenerator:
    """Hívásszámláló mock `generate_fn` — sosem hív hálózatot."""

    def __init__(self, response: str = "") -> None:
        self.response = response or SUGGESTION_TEXT
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


# =============================================================================
# 1. Mind a kilenc célmező saját, független MI-segédet kap.
# =============================================================================


def test_all_nine_field_keys_are_recognized_and_independent():
    assert tuple(_REFINEMENT_FIELD_KEYS) == (
        "text_main_idea",
        "sermon_main_idea",
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    assert len(_REFINEMENT_FIELD_KEYS) == 9


def test_generating_for_one_field_never_touches_the_other_eight():
    state = _base_state()
    for field_key in _REFINEMENT_FIELD_KEYS:
        gen = _CountingGenerator(response=f"Javaslat a(z) {field_key} mezőhöz.")
        outcome = refine_ai.generate_field_refinement(
            state, field_key=field_key, current_text="", instruction="", generate_fn=gen
        )
        assert outcome.ok is True
        for other_key in _REFINEMENT_FIELD_KEYS:
            entry = state["sermon_workshop"]["field_refinements"][other_key]
            if other_key == field_key:
                assert entry is not None
                assert entry["text"] == f"Javaslat a(z) {field_key} mezőhöz."
            else:
                assert entry is None, f"{field_key} generálása módosította {other_key}-t"
        discard_field_refinement_suggestion(state, field_key)


# =============================================================================
# 2. Üres és nem üres mezőnél is működik a javaslatkérés.
# =============================================================================


def test_refinement_request_works_on_empty_field():
    state = _base_state()
    gen = _CountingGenerator()
    outcome = refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="", instruction="", generate_fn=gen
    )
    assert outcome.ok is True
    assert len(gen.calls) == 1
    assert "még üres" in gen.calls[0]["prompt"]


def test_refinement_request_works_on_non_empty_field():
    state = _base_state()
    gen = _CountingGenerator()
    outcome = refine_ai.generate_field_refinement(
        state,
        field_key="entry",
        current_text="Már van kézzel írt tartalom.",
        instruction="Legyen rövidebb.",
        generate_fn=gen,
    )
    assert outcome.ok is True
    assert "Már van kézzel írt tartalom." in gen.calls[0]["prompt"]
    assert "Legyen rövidebb." in gen.calls[0]["prompt"]


def test_instruction_is_optional_and_generation_still_works():
    state = _base_state()
    gen = _CountingGenerator()
    outcome = refine_ai.generate_field_refinement(
        state, field_key="sermon_main_idea", current_text="Valami.", instruction="", generate_fn=gen
    )
    assert outcome.ok is True
    assert "Nincs külön felhasználói utasítás" in gen.calls[0]["prompt"]


# =============================================================================
# 3. Csak az adott mező kontextusa kerül az MI-hívásba.
# =============================================================================


def test_prompt_contains_only_the_target_field_content_not_other_fields():
    state = _base_state()
    state["sermon_workshop"]["arc"]["starting_point"]["text"] = "ALAPHELYZET_SENTINEL_MASIK_MEZO"
    state["sermon_workshop"]["sermon_main_idea"] = "FOKUSZMONDAT_SENTINEL_MASIK_MEZO"
    state["text_workshop"]["text_main_idea"] = "FOGONDOLAT_SENTINEL_MASIK_MEZO"
    state["overview"] = "ATTEKINTES_SENTINEL_HATTERANYAG"
    state["exegesis"] = "EXEGEZIS_SENTINEL_HATTERANYAG"

    gen = _CountingGenerator()
    refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="Belépés saját tartalma.", instruction="", generate_fn=gen
    )
    prompt = gen.calls[0]["prompt"]
    assert "Belépés saját tartalma." in prompt
    for sentinel in (
        "ALAPHELYZET_SENTINEL_MASIK_MEZO",
        "FOKUSZMONDAT_SENTINEL_MASIK_MEZO",
        "FOGONDOLAT_SENTINEL_MASIK_MEZO",
        "ATTEKINTES_SENTINEL_HATTERANYAG",
        "EXEGEZIS_SENTINEL_HATTERANYAG",
    ):
        assert sentinel not in prompt


def test_context_builder_reads_no_other_field_keys():
    state = _base_state()
    context = refine_ai.build_refinement_context(
        state, field_key="entry", current_text="x", instruction="y"
    )
    field_names = {f.name for f in context.__dataclass_fields__.values()}
    assert "arc" not in field_names
    assert "sermon_main_idea" not in field_names
    assert "overview" not in field_names


# =============================================================================
# 4. Az MI-válasz nem ír automatikusan kanonikus adatot.
# =============================================================================


def test_generation_never_writes_canonical_fields_only_the_suggestion_store():
    state = _base_state()
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_sermon_idea = state["sermon_workshop"]["sermon_main_idea"]
    before_text_idea = state["text_workshop"]["text_main_idea"]

    gen = _CountingGenerator()
    outcome = refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="", instruction="", generate_fn=gen
    )

    assert outcome.ok is True
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["sermon_main_idea"] == before_sermon_idea
    assert state["text_workshop"]["text_main_idea"] == before_text_idea
    assert state["sermon_workshop"]["field_refinements"]["entry"]["text"] == SUGGESTION_TEXT


# =============================================================================
# 5. Átvétel kizárólag a célmezőt módosítja.
# =============================================================================


def test_accepting_one_field_suggestion_does_not_touch_other_canonical_fields():
    state = _base_state()
    for key in _ARC_POINT_KEYS:
        update_arc_point(state, key, f"Kézi {key} szöveg.")
    before_other_points = {
        key: copy.deepcopy(state["sermon_workshop"]["arc"][key])
        for key in _ARC_POINT_KEYS
        if key != "entry"
    }
    before_sermon_idea = state["sermon_workshop"]["sermon_main_idea"]
    before_text_idea = state["text_workshop"]["text_main_idea"]

    gen = _CountingGenerator(response="Pontosított belépés.")
    refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="Kézi entry szöveg.", instruction="", generate_fn=gen
    )
    context = refine_ai.build_refinement_context(
        state, field_key="entry", current_text="Kézi entry szöveg."
    )
    result = validate_field_refinement_acceptance(
        state, "entry", reference=context.reference, context_hash=context.context_hash
    )
    assert result["valid"] is True
    update_arc_point(state, "entry", result["text"], context_hash=context.context_hash)

    assert state["sermon_workshop"]["arc"]["entry"]["text"] == "Pontosított belépés."
    for key, before in before_other_points.items():
        assert state["sermon_workshop"]["arc"][key] == before
    assert state["sermon_workshop"]["sermon_main_idea"] == before_sermon_idea
    assert state["text_workshop"]["text_main_idea"] == before_text_idea


# =============================================================================
# 6. Arc-pont átvétele frissíti a megfelelő metaadatokat.
# =============================================================================


def test_accepting_arc_point_suggestion_updates_manually_updated_at_and_context_hash():
    state = _base_state()
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""

    gen = _CountingGenerator(response="Pontosított belépés.")
    refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="", instruction="", generate_fn=gen
    )
    context = refine_ai.build_refinement_context(state, field_key="entry", current_text="")
    result = validate_field_refinement_acceptance(
        state, "entry", reference=context.reference, context_hash=context.context_hash
    )
    assert result["valid"] is True

    from sermon_workshop_arc_ai import build_arc_generation_context

    full_context_hash = build_arc_generation_context(state).context_hash
    update_arc_point(state, "entry", result["text"], context_hash=full_context_hash)

    assert state["sermon_workshop"]["arc"]["entry"]["text"] == "Pontosított belépés."
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""
    assert state["sermon_workshop"]["arc_meta"]["context_hash"] == full_context_hash


# =============================================================================
# 7. Elvetés nulla kanonikus mutációt okoz.
# =============================================================================


def test_discard_causes_zero_canonical_mutation_and_clears_only_that_suggestion():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi entry szöveg.")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    gen = _CountingGenerator()
    refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="Kézi entry szöveg.", instruction="", generate_fn=gen
    )
    set_field_refinement_suggestion(
        state, "starting_point", text="Más javaslat.", reference="Jn 3,16", context_hash="H2"
    )

    discard_field_refinement_suggestion(state, "entry")

    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta
    assert state["sermon_workshop"]["field_refinements"]["entry"] is None
    # a másik mező függőben lévő javaslata érintetlen
    assert state["sermon_workshop"]["field_refinements"]["starting_point"]["text"] == "Más javaslat."


# =============================================================================
# 8. Hibás modellválasz nulla mutációt okoz.
# =============================================================================


def test_empty_model_response_causes_zero_mutation():
    state = _base_state()
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    gen = _CountingGenerator(response="   ")
    outcome = refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="", instruction="", generate_fn=gen
    )
    assert outcome.ok is False
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["field_refinements"]["entry"] is None


def test_api_error_string_response_causes_zero_mutation():
    state = _base_state()
    gen = _CountingGenerator(response="⚠️ Hiba történt a generálás közben.")
    outcome = refine_ai.generate_field_refinement(
        state, field_key="sermon_main_idea", current_text="", instruction="", generate_fn=gen
    )
    assert outcome.ok is False
    assert state["sermon_workshop"]["field_refinements"]["sermon_main_idea"] is None
    assert state["sermon_workshop"]["sermon_main_idea"] == ""


def test_generate_fn_exception_causes_zero_mutation():
    state = _base_state()

    def raising_gen(prompt, **kwargs):
        raise RuntimeError("hálózati hiba")

    outcome = refine_ai.generate_field_refinement(
        state, field_key="text_main_idea", current_text="", instruction="", generate_fn=raising_gen
    )
    assert outcome.ok is False
    assert outcome.error_message
    assert state["sermon_workshop"]["field_refinements"]["text_main_idea"] is None
    assert state["text_workshop"]["text_main_idea"] == ""


def test_missing_context_blocks_generation_with_zero_ai_calls():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    ensure_text_workshop_state(state)
    gen = _CountingGenerator()
    outcome = refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="", instruction="", generate_fn=gen
    )
    assert outcome.ok is False
    assert len(gen.calls) == 0


# =============================================================================
# 9-10. Kontextusváltozás blokkolja az átvételt; visszaállítás után az
#       átvétel ismét lehetséges.
# =============================================================================


def test_context_change_after_generation_blocks_acceptance_with_zero_mutation():
    state = _base_state()
    gen = _CountingGenerator()
    refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="", instruction="", generate_fn=gen
    )
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_suggestion = copy.deepcopy(state["sermon_workshop"]["field_refinements"]["entry"])

    # a bibliai szöveg megváltozik a generálás óta
    state["passage_text"] = "Egy teljesen más bibliai szöveg."
    context = refine_ai.build_refinement_context(state, field_key="entry", current_text="")
    result = validate_field_refinement_acceptance(
        state, "entry", reference=context.reference, context_hash=context.context_hash
    )

    assert result["valid"] is False
    assert result["reason"] == "context_hash_mismatch"
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["field_refinements"]["entry"] == before_suggestion


def test_target_field_own_content_change_after_generation_blocks_acceptance():
    """Ha maga a célmező tartalma változik meg a generálás óta (pl. a
    felhasználó közben kézzel átírta), az is kontextusváltozásnak számít —
    a javaslat a RÉGI tartalomra épült."""
    state = _base_state()
    gen = _CountingGenerator()
    refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="Eredeti szöveg.", instruction="", generate_fn=gen
    )
    # a felhasználó időközben kézzel átírta a mezőt
    context = refine_ai.build_refinement_context(
        state, field_key="entry", current_text="Időközben kézzel átírt szöveg."
    )
    result = validate_field_refinement_acceptance(
        state, "entry", reference=context.reference, context_hash=context.context_hash
    )
    assert result["valid"] is False
    assert result["reason"] == "context_hash_mismatch"


def test_restoring_original_context_makes_acceptance_possible_again():
    state = _base_state()
    gen = _CountingGenerator()
    refine_ai.generate_field_refinement(
        state, field_key="entry", current_text="", instruction="", generate_fn=gen
    )

    state["passage_text"] = "Ideiglenesen más szöveg."
    context_blocked = refine_ai.build_refinement_context(state, field_key="entry", current_text="")
    blocked = validate_field_refinement_acceptance(
        state, "entry", reference=context_blocked.reference, context_hash=context_blocked.context_hash
    )
    assert blocked["valid"] is False

    state["passage_text"] = "Mert úgy szerette Isten a világot."  # eredeti visszaállítva
    context_restored = refine_ai.build_refinement_context(state, field_key="entry", current_text="")
    restored = validate_field_refinement_acceptance(
        state, "entry", reference=context_restored.reference, context_hash=context_restored.context_hash
    )
    assert restored["valid"] is True
    assert restored["text"] == SUGGESTION_TEXT


# =============================================================================
# 11. A teljes hétpontos candidate-rendszer változatlanul működik együtt
#     a mezőnkénti pontosítással (nincs kereszteződés a két rendszer közt).
# =============================================================================


def test_arc_candidate_and_field_refinement_coexist_without_cross_contamination():
    from sermon_workshop_arc_ai import generate_seven_point_arc

    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom, ami candidate-et vált ki.")

    valid_points = {
        "entry": "Belépés.",
        "starting_point": "Alaphelyzet.",
        "first_shift": "Első fordulópont.",
        "deepening": "Mélyítés.",
        "reinterpretation": "Átértelmezés.",
        "second_shift": "Második fordulópont.",
        "arrival": "Megérkezés.",
    }
    import json

    arc_gen = lambda prompt, **kwargs: json.dumps(valid_points, ensure_ascii=False)  # noqa: E731
    outcome = generate_seven_point_arc(state, generate_fn=arc_gen)
    assert outcome.status == "candidate"
    assert state["sermon_workshop"]["arc_candidate"] is not None

    refine_gen = _CountingGenerator(response="Pontosított alaphelyzet.")
    refine_outcome = refine_ai.generate_field_refinement(
        state,
        field_key="starting_point",
        current_text="",
        instruction="",
        generate_fn=refine_gen,
    )
    assert refine_outcome.ok is True

    # a candidate érintetlen, a field_refinements pedig önálló
    assert state["sermon_workshop"]["arc_candidate"]["points"]["entry"]["text"] == "Belépés."
    assert state["sermon_workshop"]["field_refinements"]["starting_point"]["text"] == "Pontosított alaphelyzet."
    assert state["sermon_workshop"]["arc"]["entry"]["text"] == "Kézi tartalom, ami candidate-et vált ki."


# =============================================================================
# 12. A függőben lévő javaslatok projektmentés után megmaradnak.
# =============================================================================


def test_pending_suggestions_survive_project_save_and_reload():
    state = _base_state()
    set_field_refinement_suggestion(
        state, "entry", text="Belépés javaslat.", reference="Jn 3,16", context_hash="HASH-A"
    )
    set_field_refinement_suggestion(
        state,
        "sermon_main_idea",
        text="Fókuszmondat javaslat.",
        instruction="Legyen tömörebb.",
        reference="Jn 3,16",
        context_hash="HASH-B",
    )

    project = build_project_data(state)
    reloaded: dict = dict(project)
    ensure_sermon_workshop_state(reloaded)

    refinements = reloaded["sermon_workshop"]["field_refinements"]
    assert refinements["entry"]["text"] == "Belépés javaslat."
    assert refinements["entry"]["context_hash"] == "HASH-A"
    assert refinements["sermon_main_idea"]["text"] == "Fókuszmondat javaslat."
    assert refinements["sermon_main_idea"]["instruction"] == "Legyen tömörebb."
    for key in _REFINEMENT_FIELD_KEYS:
        if key not in ("entry", "sermon_main_idea"):
            assert refinements[key] is None


def test_legacy_project_without_field_refinements_key_loads_safely():
    """Régi, `field_refinements` mező NÉLKÜLI projekt biztonságosan az
    összes célmezőre `None`-ra esik vissza — nem dob kivételt."""
    legacy_project: dict = {
        "sermon_workshop": {
            "sermon_main_idea": "Régi fókuszmondat.",
            "arc": {"entry": {"text": "Régi belépés."}},
        }
    }
    sw = ensure_sermon_workshop_state(legacy_project)
    assert sw["field_refinements"] == {key: None for key in _REFINEMENT_FIELD_KEYS}
    assert sw["sermon_main_idea"] == "Régi fókuszmondat."
    assert sw["arc"]["entry"]["text"] == "Régi belépés."


# =============================================================================
# 13. A régi Textusműhelyes refinement chat továbbra is változatlanul
#     renderel — forráskód-szintű bizonyíték, mivel app.py-t ez a fázis
#     egyáltalán nem módosította.
# =============================================================================


def test_legacy_refinement_chat_call_sites_are_unchanged():
    import app

    assert callable(app.refinement_chat)
    src_original_text_panel = inspect.getsource(app.render_original_text_panel)
    assert 'refinement_chat("Eredeti szöveg tanulmányozása", "original_text", "original_text_chat")' in (
        src_original_text_panel
    )
    src_section_tab = inspect.getsource(app.render_section_tab)
    assert "refinement_chat(chat_title or header, key, f\"{key}_chat\")" in src_section_tab


# =============================================================================
# UI RÉTEG — valódi Streamlit-renderelés AppTest-tel.
# =============================================================================


def _render_shell_with_generate() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    def fake_gen(prompt, **kwargs):
        return "Pontosított javaslat szöveg."

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def test_ui_renders_nine_independent_refinement_expanders():
    """RESET 2D-B2, 6. pont: a két főgondolat expanderének felirata
    („MI-javaslat vagy pontosítás”) egyértelműen jelzi, hogy üres mezőhöz
    is kérhető javaslat, nem csak meglévő tartalom pontosítható; a hét
    arc-pont expandere külön felirattal jelenik meg, mivel azoknál a
    kártya alatti önálló gyors gomb már fedi az egyszerű javaslatkérést."""
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    assert not app.exception
    expander_labels = [e.label for e in app.expander]
    assert expander_labels.count("MI-javaslat vagy pontosítás") == 2
    assert expander_labels.count("Pontosítási kérés (opcionális)") == 7
    request_buttons = [b for b in app.button if b.label == "Egyedi MI-javaslat kérése"]
    assert len(request_buttons) == 9
    quick_buttons = [b for b in app.button if b.label == "MI-javaslat ehhez a ponthoz"]
    assert len(quick_buttons) == 7


def test_ui_no_refinement_button_when_generate_fn_is_none():
    def _render_no_generate() -> None:
        import streamlit as st

        import sermon_workshop_ui as sw_ui

        st.session_state["last_igehely"] = "Jn 3,16"
        st.session_state["igehely_input"] = "Jn 3,16"
        st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
        sw_ui.render_sermon_workshop_shell()

    app = AppTest.from_function(_render_no_generate).run(timeout=60)
    assert not app.exception
    request_buttons = [b for b in app.button if b.label == "Egyedi MI-javaslat kérése"]
    assert len(request_buttons) == 9
    assert all(b.disabled for b in request_buttons)
    quick_buttons = [b for b in app.button if b.label == "MI-javaslat ehhez a ponthoz"]
    assert len(quick_buttons) == 7
    assert all(b.disabled for b in quick_buttons)


def test_ui_request_then_accept_updates_target_field_and_shows_no_stale_panel():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    request_buttons = [i for i, b in enumerate(app.button) if b.label == "Egyedi MI-javaslat kérése"]
    # a 3. kérés gomb (index 2) az első arc-pont ("Belépés")
    idx = request_buttons[2]
    app.button[idx].click().run()
    assert not app.exception

    labels = [b.label for b in app.button]
    accept_idx = labels.index("Javaslat átvétele")
    app.button[accept_idx].click().run()
    assert not app.exception

    assert app.session_state["sermon_workshop"]["arc"]["entry"]["text"] == (
        "Pontosított javaslat szöveg."
    )
    assert app.session_state["sermon_workshop"]["field_refinements"]["entry"] is None

    # a `st.rerun()`-t hívó gombkezelő után a renderelt fa csak egy
    # további `.run()` után rendeződik a végleges állapotra (AppTest
    # sajátosság — ld. korábbi fázisok azonos megjegyzése).
    app.run()
    labels_after = [b.label for b in app.button]
    assert "Javaslat átvétele" not in labels_after


def test_ui_request_then_discard_leaves_arc_untouched():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    request_buttons = [i for i, b in enumerate(app.button) if b.label == "Egyedi MI-javaslat kérése"]
    idx = request_buttons[2]
    app.button[idx].click().run()
    values_before = sorted(ta.value for ta in app.text_area)

    labels = [b.label for b in app.button]
    discard_idx = labels.index("Javaslat elvetése")
    app.button[discard_idx].click().run()
    assert not app.exception

    values_after = sorted(ta.value for ta in app.text_area)
    assert values_after == values_before
    assert app.session_state["sermon_workshop"]["field_refinements"]["entry"] is None


# =============================================================================
# UX-KORREKCIÓ (2026-08-19): kézi teszten talált hiba — sikeres javaslat-
# kérés után a `_toast_and_rerun()` programozott `st.rerun()`-ja minden
# kulcs nélküli `st.expander`-t visszacsukott, noha a saját panelben friss,
# még át nem tekintett javaslat várt. Egy fogyó, session-state-alapú
# jelző (`_KEY_REFINE_AUTO_OPEN_FIELD`) most pontosan a célmező paneljét
# nyitja ki a következő rendereléskor, majd azonnal törlődik.
# =============================================================================


def _expander_states(app) -> list[tuple[str, bool]]:
    return [(e.label, e.proto.expanded) for e in app.expander]


def _request_button_indexes(app) -> list[int]:
    return [i for i, b in enumerate(app.button) if b.label == "Egyedi MI-javaslat kérése"]


def _quick_request_button_indexes(app) -> list[int]:
    return [i for i, b in enumerate(app.button) if b.label == "MI-javaslat ehhez a ponthoz"]


# 1-4. Javaslatkérés után PONTOSAN a célmező panelje nyílik ki; a Bibliai
#      szöveg panel és a másik nyolc refinement-panel nem.


def test_successful_request_opens_only_the_target_field_panel():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    before = _expander_states(app)
    assert all(not expanded for _, expanded in before), "kezdetben minden panel csukott"

    request_idx = _request_button_indexes(app)
    # index 2 -> a harmadik "Javaslat kérése" gomb -> az első arc-pont ("Belépés")
    idx = request_idx[2]
    app.button[idx].click().run()
    assert not app.exception

    states = _expander_states(app)
    open_indexes = [i for i, (_, expanded) in enumerate(states) if expanded]
    assert open_indexes == [3], f"pontosan egy panel nyíljon ki, nem: {open_indexes}"

    # index 0 mindig a "Bibliai szöveg" panel — sosem nyílhat ki emiatt.
    assert states[0] == ("Bibliai szöveg", False)


def test_successful_request_for_different_field_opens_only_that_fields_panel():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    request_idx = _request_button_indexes(app)
    # index 0 -> az első "Javaslat kérése" gomb -> "A textus fő gondolata"
    idx = request_idx[0]
    app.button[idx].click().run()
    assert not app.exception

    states = _expander_states(app)
    open_indexes = [i for i, (_, expanded) in enumerate(states) if expanded]
    # index 1 = "A textus fő gondolata" panelje (index 0 = Bibliai szöveg)
    assert open_indexes == [1]


def test_other_eight_panels_remain_closed_after_one_field_requests_suggestion():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    request_idx = _request_button_indexes(app)
    idx = request_idx[5]  # egy másik arc-pont
    app.button[idx].click().run()
    assert not app.exception

    states = _expander_states(app)
    refinement_states = [
        expanded
        for label, expanded in states
        if label in ("MI-javaslat vagy pontosítás", "Pontosítási kérés (opcionális)")
    ]
    assert refinement_states.count(True) == 1
    assert refinement_states.count(False) == 8


# 5. Átvétel vagy elvetés után nincs függőben lévő automatikus megnyitás.


def test_no_auto_open_pending_after_accept():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    request_idx = _request_button_indexes(app)
    app.button[request_idx[2]].click().run()

    labels = [b.label for b in app.button]
    accept_idx = labels.index("Javaslat átvétele")
    app.button[accept_idx].click().run()
    app.run()  # ld. korábbi fázisok megjegyzése az AppTest rerun-sajátosságról

    assert all(not expanded for _, expanded in _expander_states(app))


def test_no_auto_open_pending_after_discard():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    request_idx = _request_button_indexes(app)
    app.button[request_idx[2]].click().run()

    labels = [b.label for b in app.button]
    discard_idx = labels.index("Javaslat elvetése")
    app.button[discard_idx].click().run()
    app.run()

    assert all(not expanded for _, expanded in _expander_states(app))


# 6. Sikertelen generálás után nincs automatikus megnyitás.


def test_no_auto_open_after_failed_generation():
    def _render_failing() -> None:
        import streamlit as st

        import sermon_workshop_ui as sw_ui

        st.session_state["last_igehely"] = "Jn 3,16"
        st.session_state["igehely_input"] = "Jn 3,16"
        st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
        st.session_state["bible_translation"] = "RÚF 2014"

        def failing_gen(prompt, **kwargs):
            return "   "  # üres/érvénytelen válasz

        sw_ui.render_sermon_workshop_shell(generate_fn=failing_gen)

    app = AppTest.from_function(_render_failing).run(timeout=60)
    request_idx = _request_button_indexes(app)
    app.button[request_idx[2]].click().run()
    assert not app.exception
    assert any(e.value for e in app.error), "hibaüzenetnek meg kell jelennie"

    assert all(not expanded for _, expanded in _expander_states(app))


# 7. A javaslat, átvétel, elvetés és kontextusvédelmi viselkedés
#    változatlan — az automatikusan kinyílt panelben a tartalom is helyes.


def test_auto_opened_panel_shows_correct_readonly_suggestion_and_both_buttons():
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    request_idx = _request_button_indexes(app)
    app.button[request_idx[2]].click().run()

    markdown_texts = "\n".join(md.value for md in app.markdown)
    assert "Pontosított javaslat szöveg." in markdown_texts
    labels = [b.label for b in app.button]
    assert "Javaslat átvétele" in labels
    assert "Javaslat elvetése" in labels
    # a kanonikus arc-pont a javaslat átvétele NÉLKÜL változatlan marad
    assert app.session_state["sermon_workshop"]["arc"]["entry"]["text"] == ""


# =============================================================================
# RESET 2D-B2: a hétpontos vázlat átnevezett gombja, az önálló kártyánkénti
# gyors javaslatgomb üres és kitöltött mezőn is, valamint annak bizonyítéka,
# hogy nincs második, párhuzamos teljes-vázlat-generáló útvonal.
# =============================================================================


def test_full_outline_button_relabeled_and_still_uses_single_generation_route():
    """2D-B2, 1. pont: a hétpontos vázlat gombja az új feliratot kapja, de
    továbbra is a meglévő, egyetlen AI-hívást használó candidate/applied
    útvonalat (`generate_seven_point_arc`) hívja."""
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    labels = [b.label for b in app.button]
    assert "MI-javaslat mind a hét ponthoz" in labels
    assert "Hétpontos vázlatjavaslat készítése" not in labels


def test_no_second_full_outline_generator_path():
    """2D-B2, 8. pont: a hétpontos szekció forráskódja pontosan egyetlen
    `generate_seven_point_arc(` hívást tartalmaz — nincs második,
    párhuzamos teljes-vázlat-generáló út."""
    src = inspect.getsource(sw_ui.render_flat_seven_point_outline_section)
    assert src.count("generate_seven_point_arc(") == 1


def test_quick_button_appears_exactly_once_per_arc_card():
    """2D-B2, 2. pont: mind a hét arc-kártyán pontosan egy külső, egyedi
    MI-javaslat gomb jelenik meg."""
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    quick_idx = _quick_request_button_indexes(app)
    assert len(quick_idx) == 7


def test_quick_button_generates_suggestion_for_empty_arc_point():
    """2D-B2, 3. pont: üres arc-pontnál a külső gomb javaslatot készít."""
    app = AppTest.from_function(_render_shell_with_generate).run(timeout=60)
    quick_idx = _quick_request_button_indexes(app)
    assert app.session_state["sermon_workshop"]["arc"]["entry"]["text"] == ""

    # a legelső gyors gomb -> az első arc-pont ("Belépés")
    app.button[quick_idx[0]].click().run()
    assert not app.exception

    assert app.session_state["sermon_workshop"]["field_refinements"]["entry"]["text"] == (
        "Pontosított javaslat szöveg."
    )
    assert app.session_state["sermon_workshop"]["arc"]["entry"]["text"] == ""

    states = _expander_states(app)
    open_indexes = [i for i, (_, expanded) in enumerate(states) if expanded]
    assert open_indexes == [3], "a gyors gomb ugyanazt a panelt nyitja ki, mint az egyedi kérés"


def test_quick_button_creates_candidate_for_filled_arc_point_without_overwrite():
    """2D-B2, 4. pont: kitöltött arc-pontnál a külső gomb candidate-et
    készít, automatikus felülírás nélkül."""

    def _render_with_filled_entry() -> None:
        import streamlit as st

        import sermon_workshop_ui as sw_ui
        from sermon_workshop_data import ensure_sermon_workshop_state, update_arc_point

        st.session_state["last_igehely"] = "Jn 3,16"
        st.session_state["igehely_input"] = "Jn 3,16"
        st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
        st.session_state["bible_translation"] = "RÚF 2014"
        ensure_sermon_workshop_state(st.session_state)
        update_arc_point(st.session_state, "entry", "Kézzel írt belépés.")

        def fake_gen(prompt, **kwargs):
            return "Alternatív, jobb megfogalmazás."

        sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)

    app = AppTest.from_function(_render_with_filled_entry).run(timeout=60)
    quick_idx = _quick_request_button_indexes(app)
    app.button[quick_idx[0]].click().run()
    assert not app.exception

    assert app.session_state["sermon_workshop"]["field_refinements"]["entry"]["text"] == (
        "Alternatív, jobb megfogalmazás."
    )
    # a kézzel írt tartalom NEM íródik felül automatikusan
    assert app.session_state["sermon_workshop"]["arc"]["entry"]["text"] == "Kézzel írt belépés."


# =============================================================================
# RESET 2D-F1 — a két főgondolat-mező promptszerződése: exegetikai vs.
# homiletikai szerep, rövidség, nem egymás parafrázisa. Ezek a tesztek
# KIZÁRÓLAG a promptba kerülő szöveget ellenőrzik — nem tudnak és nem is
# állítják, hogy egy valódi modellválasz minőségét bizonyítanák.
# =============================================================================


def test_text_main_idea_prompt_states_exegetical_role_and_length_cap():
    state = _base_state()
    context = refine_ai.build_refinement_context(
        state, field_key="text_main_idea", current_text=""
    )
    prompt = refine_ai.build_refinement_prompt(context)
    assert "EXEGETIKAI" in prompt
    assert "Legfeljebb 1–2 mondat" in prompt or "Legfeljebb 1-2 mondat" in prompt
    assert "ne ismételd meg a szöveget" in prompt


def test_sermon_main_idea_prompt_states_homiletical_role_and_length_cap():
    state = _base_state()
    context = refine_ai.build_refinement_context(
        state, field_key="sermon_main_idea", current_text=""
    )
    prompt = refine_ai.build_refinement_prompt(context)
    assert "HOMILETIKAI FÓKUSZMONDAT" in prompt
    assert "Legfeljebb 1–2 mondat" in prompt or "Legfeljebb 1-2 mondat" in prompt


def test_main_idea_prompts_explicitly_contrast_with_each_other():
    """A két mező promptja NEM egymás parafrázisát kéri: a `text_main_
    idea` explicit tiltja a hallgató/alkalmazás felé mutatást, a `sermon_
    main_idea` explicit tiltja a szöveg puszta tartalmi összefoglalását —
    a két utasítás egymást kizáró irányt ad."""
    state = _base_state()
    text_context = refine_ai.build_refinement_context(
        state, field_key="text_main_idea", current_text=""
    )
    sermon_context = refine_ai.build_refinement_context(
        state, field_key="sermon_main_idea", current_text=""
    )
    text_prompt = refine_ai.build_refinement_prompt(text_context)
    sermon_prompt = refine_ai.build_refinement_prompt(sermon_context)

    assert "ne az igehirdetés alkalmazása, felszólítás vagy a hallgató felé mutass" in text_prompt
    assert "ez NE a szöveg tartalmi összefoglalása legyen" in sermon_prompt
    assert text_prompt != sermon_prompt


def test_other_seven_fields_do_not_receive_main_idea_contrast_guidance():
    """A kontraszt-utasítás KIZÁRÓLAG a két főgondolat-mezőt érinti — a
    hét arc-pont promptja nem tartalmazza (azoknak nincs "egymás
    parafrázisa" kockázatuk, mindegyik saját, elkülönült szerepű)."""
    state = _base_state()
    for field_key in _ARC_POINT_KEYS:
        context = refine_ai.build_refinement_context(
            state, field_key=field_key, current_text=""
        )
        prompt = refine_ai.build_refinement_prompt(context)
        assert "EXEGETIKAI" not in prompt
        assert "HOMILETIKAI FÓKUSZMONDAT" not in prompt


def test_field_labels_and_response_validation_unchanged_by_prompt_edit():
    """RESET 2D-F1 kizárólag promptszöveget módosít — a mezőcímkék és a
    kilenc célmező kulcskészlete bit-pontosan változatlan marad."""
    assert refine_ai._FIELD_LABELS == {
        "text_main_idea": "A textus fő gondolata",
        "sermon_main_idea": "Az igehirdetés fő gondolata – fókuszmondat",
        "entry": "Belépés",
        "starting_point": "Alaphelyzet",
        "first_shift": "Első fordulópont",
        "deepening": "Mélyítés és fokozás",
        "reinterpretation": "Átértelmezés",
        "second_shift": "Második fordulópont",
        "arrival": "Megérkezés",
    }
    assert tuple(_REFINEMENT_FIELD_KEYS) == (
        "text_main_idea",
        "sermon_main_idea",
    ) + tuple(_ARC_POINT_KEYS)
