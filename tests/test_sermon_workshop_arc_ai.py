"""RESET 2C — a hétpontos igehirdetési vázlat candidate-alapú MI-generálása.

Két rétegben tesztel:
  - a `sermon_workshop_arc_ai` modul tiszta motorlogikáját, hálózatmentes,
    mockolt `generate_fn`-nel (nincs valódi API-hívás, nincs API-kulcs);
  - a `sermon_workshop_ui` gomb-/panel-bekötését valódi Streamlit-
    renderelésen keresztül (`streamlit.testing.v1.AppTest`), szintén
    mindig mockolt `generate_fn`-nel.

A RESET 2A-ban elkészült, itt VÁLTOZATLANUL újrafelhasznált adatmodell-
függvények (`store_generated_arc_result`, `accept_arc_candidate`,
`discard_arc_candidate`, `arc_has_content`) saját, kimerítő tesztjei a
`tests/test_arc_data_model.py`-ban vannak — ez a fájl kifejezetten az ÚJ,
RESET 2C-s réteget (kontextus-összeállítás, prompt/séma, validálás,
orchestráció, UI-bekötés) fedi le, a 18 pontos célzott lista szerint.
"""

from __future__ import annotations

import copy
import inspect
import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_arc_ai as arc_ai  # noqa: E402
import sermon_workshop_ui as sw_ui  # noqa: E402
from sermon_workshop_data import (  # noqa: E402
    _ARC_POINT_KEYS,
    accept_arc_candidate,
    discard_arc_candidate,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    update_arc_point,
)
from textus_workshop_data import ensure_text_workshop_state  # noqa: E402
from workspace_data import build_project_data  # noqa: E402

VALID_POINTS: dict[str, str] = {
    "entry": "Belépés szöveg.",
    "starting_point": "Alaphelyzet szöveg.",
    "first_shift": "Első fordulópont szöveg.",
    "deepening": "Mélyítés szöveg.",
    "reinterpretation": "Átértelmezés szöveg.",
    "second_shift": "Második fordulópont szöveg.",
    "arrival": "Megérkezés szöveg.",
}


def _valid_response_json() -> str:
    return json.dumps(VALID_POINTS, ensure_ascii=False)


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
        self.response = response or _valid_response_json()
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


# =============================================================================
# 1. A generálási bemenet nem használ legacy outline/basket adatot.
# =============================================================================


def test_context_ignores_legacy_sermon_outline_and_basket_content():
    state = _base_state()
    state["sermon_workshop"]["sermon_outline"]["content"] = "LEGACY_OUTLINE_SENTINEL"
    state["outline_basket"] = ["BASKET_SENTINEL"]

    context = arc_ai.build_arc_generation_context(state)
    assert "sermon_outline" not in {f.name for f in context.__dataclass_fields__.values()}
    prompt = arc_ai.build_arc_generation_prompt(context)
    assert "LEGACY_OUTLINE_SENTINEL" not in prompt
    assert "BASKET_SENTINEL" not in prompt


# =============================================================================
# 2. Hiányzó referencia/szöveg/hash esetén nincs AI-hívás és nincs mutáció.
# =============================================================================


def test_missing_reference_blocks_generation_with_zero_ai_calls_and_zero_mutation():
    state = _base_state()
    state["last_igehely"] = ""
    state["igehely_input"] = ""
    gen = _CountingGenerator()
    before = copy.deepcopy(state["sermon_workshop"]["arc"])

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert outcome.status == "error"
    assert gen.calls == []
    assert state["sermon_workshop"]["arc"] == before
    assert state["sermon_workshop"]["arc_candidate"] is None


def test_missing_passage_text_blocks_generation_with_zero_ai_calls_and_zero_mutation():
    state = _base_state()
    state["passage_text"] = ""
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert gen.calls == []
    assert state["sermon_workshop"]["arc_candidate"] is None


def test_missing_everything_reports_clear_error_with_zero_ai_calls():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert gen.calls == []
    assert outcome.error_message  # rövid, világos hibaüzenet


# =============================================================================
# 3. A generáló prompt/séma kizárólag a hét engedélyezett kulcsot kéri.
# =============================================================================


def test_response_schema_requires_exactly_the_seven_allowed_keys_in_order():
    assert tuple(arc_ai.ARC_RESPONSE_SCHEMA["required"]) == tuple(_ARC_POINT_KEYS)
    assert set(arc_ai.ARC_RESPONSE_SCHEMA["properties"].keys()) == set(_ARC_POINT_KEYS)


def test_generate_fn_invoked_with_structured_json_schema_and_single_call():
    state = _base_state()
    gen = _CountingGenerator()
    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert outcome.ok is True
    assert len(gen.calls) == 1
    kwargs = gen.calls[0]["kwargs"]
    assert kwargs["response_mime_type"] == "application/json"
    assert kwargs["response_schema"] is arc_ai.ARC_RESPONSE_SCHEMA


# =============================================================================
# 4. Helyes strukturált eredmény érvényesen normalizálódik.
# =============================================================================


def test_valid_json_response_normalizes_to_exact_seven_points():
    points = arc_ai.validate_and_normalize_arc_response(_valid_response_json())
    assert points == VALID_POINTS


def test_valid_response_wrapped_in_markdown_fence_still_normalizes():
    fenced = "```json\n" + _valid_response_json() + "\n```"
    points = arc_ai.validate_and_normalize_arc_response(fenced)
    assert points == VALID_POINTS


# =============================================================================
# 5. Hibás/hiányos MI-kimenet: nulla kanonikus és candidate mutáció.
# =============================================================================


def test_missing_key_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    del broken["arrival"]
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_extra_unknown_key_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    broken["extra_unexpected_key"] = "x"
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_empty_string_value_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    broken["entry"] = "   "
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_non_string_value_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    broken["entry"] = 123
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_malformed_json_is_rejected():
    assert arc_ai.validate_and_normalize_arc_response("nem JSON szöveg {{{") is None


def test_invalid_response_causes_zero_mutation_end_to_end():
    state = _base_state()
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    gen = _CountingGenerator(response="nem JSON szöveg {{{")

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert len(gen.calls) == 1  # a hívás megtörtént, de az eredmény nem hasznosult
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] is None


def test_api_error_string_response_causes_zero_mutation():
    state = _base_state()
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    gen = _CountingGenerator(response="⚠️ Hiba történt a generálás közben.")

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] is None


# =============================================================================
# 6-7. Üres arc -> applied (közvetlen írás); nem üres arc -> csak candidate.
# =============================================================================


def test_empty_arc_successful_generation_applies_directly():
    state = _base_state()
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is True
    assert outcome.status == "applied"
    arc = state["sermon_workshop"]["arc"]
    for key, text in VALID_POINTS.items():
        assert arc[key]["text"] == text
    assert state["sermon_workshop"]["arc_candidate"] is None
    assert state["sermon_workshop"]["arc_meta"]["reference"] == "Jn 3,16"
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""


def test_non_empty_arc_successful_generation_creates_candidate_only():
    state = _base_state()
    update_arc_point(state, "entry", "Már van kézzel írt tartalom.")
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is True
    assert outcome.status == "candidate"
    assert state["sermon_workshop"]["arc"]["entry"]["text"] == "Már van kézzel írt tartalom."
    candidate = state["sermon_workshop"]["arc_candidate"]
    assert candidate is not None
    assert candidate["points"]["entry"]["text"] == VALID_POINTS["entry"]


# =============================================================================
# 8. A candidate létrehozása a régi hét pontot bit-pontosan érintetlenül
#    hagyja.
# =============================================================================


def test_candidate_creation_leaves_existing_arc_bit_for_bit_unchanged():
    state = _base_state()
    for key in _ARC_POINT_KEYS:
        update_arc_point(state, key, f"Kézi {key} szöveg.")
    before = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.status == "candidate"
    assert state["sermon_workshop"]["arc"] == before
    assert state["sermon_workshop"]["arc_meta"] == before_meta


# =============================================================================
# 9-13. Candidate elfogadása/elvetése — a RESET 2A-s tiszta függvényeken
#       keresztül, a RESET 2C-s bemenettel/kontextussal összekötve.
# =============================================================================


def test_accepting_candidate_triggers_zero_ai_calls():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert len(gen.calls) == 1

    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is True
    assert len(gen.calls) == 1  # elfogadás nem indított új hívást


def test_accept_requires_exact_nonempty_reference_and_context_hash_match():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    # A bibliai szöveg megváltozik a generálás óta -> más context_hash.
    state["passage_text"] = "Egy teljesen más bibliai szöveg."
    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is False
    assert result["reason"] == "context_hash_mismatch"


def test_context_mismatch_leaves_candidate_and_canonical_arc_unchanged():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_candidate = copy.deepcopy(state["sermon_workshop"]["arc_candidate"])

    result = accept_arc_candidate(state, reference="Róm 8,28", context_hash="STALE-HASH")

    assert result["accepted"] is False
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] == before_candidate


def test_discard_only_clears_candidate_arc_and_meta_untouched():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    discard_arc_candidate(state)

    assert state["sermon_workshop"]["arc_candidate"] is None
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta


def test_manually_updated_at_resets_to_empty_after_accepting_candidate():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""

    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is True
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""


# =============================================================================
# 14-16. A candidate panel csak valós candidate esetén jelenik meg; applied
#        után nincs panel; candidate esetén readonly előnézet + pontosan
#        két gomb.
# =============================================================================


def _render_no_candidate() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    def fake_gen(prompt, **kwargs):
        return "{}"  # sosem hívjuk meg ebben a tesztben

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def test_no_candidate_panel_when_no_candidate_present():
    app = AppTest.from_function(_render_no_candidate).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body
    labels = [b.label for b in app.button]
    assert "Javaslat átvétele" not in labels
    assert "Javaslat elvetése" not in labels


def _render_and_generate_twice() -> None:
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    valid_points = {
        "entry": "Belépés szöveg.",
        "starting_point": "Alaphelyzet szöveg.",
        "first_shift": "Első fordulópont szöveg.",
        "deepening": "Mélyítés szöveg.",
        "reinterpretation": "Átértelmezés szöveg.",
        "second_shift": "Második fordulópont szöveg.",
        "arrival": "Megérkezés szöveg.",
    }

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"
    if "_arc_ai_call_count" not in st.session_state:
        # Csak az ELSŐ (script-indító) futáson nullázunk — a script minden
        # rerunon újrafut a tetejétől, egy feltétlen nullázás elveszítené a
        # korábbi futások számlálóját.
        st.session_state["_arc_ai_call_count"] = 0

    def fake_gen(prompt, **kwargs):
        st.session_state["_arc_ai_call_count"] += 1
        return json.dumps(valid_points, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def test_applied_result_shows_no_candidate_panel():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()  # üres arc -> applied
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body


def test_candidate_shows_readonly_preview_and_exactly_two_action_buttons():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()  # 1. hívás -> applied (üres arc)
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()  # 2. hívás -> candidate (már nem üres arc)
    assert not app.exception

    labels = [b.label for b in app.button]
    assert labels.count("Javaslat átvétele") == 1
    assert labels.count("Javaslat elvetése") == 1
    # 9 kanonikus tartalommező + 9 RESET 2D-B1 pontosítási instrukciós mező —
    # a readonly candidate-előnézet önmagában nem ad hozzá text_area-t.
    assert len(app.text_area) == 18

    body = "\n".join(md.value for md in app.markdown)
    for text in VALID_POINTS.values():
        assert text in body


def test_accepting_candidate_via_ui_does_not_trigger_extra_ai_call():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()
    assert app.session_state["_arc_ai_call_count"] == 2

    accept_idx = next(i for i, b in enumerate(app.button) if b.label == "Javaslat átvétele")
    app.button[accept_idx].click().run()
    assert not app.exception
    assert app.session_state["_arc_ai_call_count"] == 2  # elfogadás nem hívott generálást
    assert app.session_state["sermon_workshop"]["arc_candidate"] is None

    # A gombkezelő `st.rerun()`-t hív — az AppTest a lezajlott mutációt
    # azonnal a session_state-ben tükrözi, de a renderelt fát csak egy
    # további `.run()` rendezi a végleges (candidate nélküli) állapotra.
    app.run()
    labels = [b.label for b in app.button]
    assert "Javaslat átvétele" not in labels
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body


def test_discarding_candidate_via_ui_leaves_arc_untouched_and_removes_panel():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()
    values_before = sorted(ta.value for ta in app.text_area)

    discard_idx = next(i for i, b in enumerate(app.button) if b.label == "Javaslat elvetése")
    app.button[discard_idx].click().run()
    assert not app.exception
    assert app.session_state["sermon_workshop"]["arc_candidate"] is None

    values_after = sorted(ta.value for ta in app.text_area)
    assert values_after == values_before

    # Lásd a fenti megjegyzést: a `st.rerun()`-t hívó gombkezelő után egy
    # további `.run()` szükséges a végleges, candidate nélküli fa
    # ellenőrzéséhez.
    app.run()
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body
    labels = [b.label for b in app.button]
    assert "Javaslat elvetése" not in labels


# =============================================================================
# 17. Nincs régi outline-generálás, export vagy section-szintű MI-gomb ezen
#     az útvonalon; az arc_ai modul nem függ a régi motortól/segédektől.
# =============================================================================


def test_arc_ai_module_does_not_import_old_engine_prompt_or_section_helpers():
    src = inspect.getsource(arc_ai)
    for forbidden in (
        "sermon_workshop_outline_ai",
        "sermon_workshop_m4_ai",
        "sermon_workshop_entry_point_ai",
        "sermon_workshop_engagement_ai",
        "import extract_json_object",  # a régi M4 segéd — ez a modul saját, önálló másolatot ír
        "from sermon_workshop_m4_ai",
    ):
        assert forbidden not in src, forbidden
    # Saját, önálló JSON-kinyerő van definiálva, nem importálva a régi modulból.
    assert "def _extract_json_object(" in src
    # Szűk szemantikai korrekció (2026-08-19): a `context_hash` mostantól
    # ennek a modulnak saját, teljes-kontextus hash-függvényéből származik
    # — a korábbi, kizárólag olvasó `sermon_outline_engine` kapcsolat
    # (`compute_current_passage_context_hash`) megszűnt, a modul funkcionális
    # kódja innentől SEMMIT nem importál a régi motorból.
    assert "from sermon_outline_engine import" not in src
    assert "import sermon_outline_engine" not in src
    assert "def compute_arc_generation_context_hash(" in src


def test_generated_route_has_no_legacy_or_export_buttons():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()
    labels = {b.label for b in app.button}
    for forbidden in (
        "Hétpontos vázlat generálása",
        "Word-export",
        "Vázlat exportálása",
        "Letöltés Word (.docx)",
        "Átveszem",
        "MI-javaslat",
    ):
        assert forbidden not in labels, forbidden


# =============================================================================
# 18. Projektmentési körben az arc, arc_meta és arc_candidate helyesen
#     megmarad (a RESET 2C motor által ténylegesen előállított alakban).
# =============================================================================


def test_project_round_trip_preserves_arc_arc_meta_and_arc_candidate_from_engine():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom, ami candidate-et vált ki.")
    gen = _CountingGenerator()
    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert outcome.status == "candidate"

    project = build_project_data(state)
    reloaded: dict = dict(project)
    ensure_sermon_workshop_state(reloaded)

    assert reloaded["sermon_workshop"]["arc"]["entry"]["text"] == (
        "Kézi tartalom, ami candidate-et vált ki."
    )
    candidate = reloaded["sermon_workshop"]["arc_candidate"]
    assert candidate is not None
    for key, text in VALID_POINTS.items():
        assert candidate["points"][key]["text"] == text
    assert candidate["reference"] == "Jn 3,16"
    assert reloaded["sermon_workshop"]["arc_meta"]["reference"] == ""  # nem íródott felül


# =============================================================================
# SZŰK SZEMANTIKAI KORREKCIÓ (2026-08-19): a candidate `context_hash`-e a
# TELJES, ténylegesen felhasznált generálási bemenet azonosítója legyen,
# ne csak a szűk igehely/szöveg/fordítás hármas. Az alábbi 12 teszt a
# felhasználói korrekciós kérés kötelező listáját fedi le pontról pontra.
# =============================================================================


def _set_text_main_idea(state: dict, value: str) -> None:
    state["text_workshop"]["text_main_idea"] = value


def _set_sermon_main_idea(state: dict, value: str) -> None:
    state["sermon_workshop"]["sermon_main_idea"] = value


# 1. Azonos teljes kontextus -> azonos hash.


def test_identical_full_context_produces_identical_hash():
    state = _base_state()
    ctx1 = arc_ai.build_arc_generation_context(state)
    ctx2 = arc_ai.build_arc_generation_context(state)
    assert ctx1.context_hash == ctx2.context_hash
    assert ctx1.context_hash != ""


# 2-6. Az egyes generálási bemenetek megváltozása eltérő hash-t eredményez.


def test_reference_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["last_igehely"] = "Róm 8,28"
    state["igehely_input"] = "Róm 8,28"
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_passage_text_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["passage_text"] = "Egy teljesen más bibliai szöveg."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_bible_translation_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["bible_translation"] = "KAR"
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_text_main_idea_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    _set_text_main_idea(state, "A textus fő gondolata SENTINEL.")
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_sermon_main_idea_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    _set_sermon_main_idea(state, "Fókuszmondat SENTINEL.")
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


# 7. overview / exegesis / original_text / history / theology egyenként.


def test_overview_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["overview"] = "Bibliai áttekintés SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_exegesis_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["exegesis"] = "Exegézis SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_original_text_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["original_text"] = "Eredeti nyelvi anyag SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_history_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["history"] = "Kortörténet SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_theology_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["theology"] = "Teológia SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


# 8. Nem generálási adat (generated_at, candidate tartalma) nem befolyásolja
#    a hash-t.


def test_generated_at_and_candidate_content_do_not_affect_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash

    state["sermon_workshop"]["arc_candidate"] = {
        "points": {"entry": {"text": "Valami candidate tartalom."}},
        "reference": "Más igehely",
        "context_hash": "MASIK-HASH",
        "generated_at": "2000-01-01T00:00:00",
    }
    state["sermon_workshop"]["arc_meta"]["generated_at"] = "2000-01-01T00:00:00"
    state["sermon_workshop"]["arc"]["entry"]["text"] = "Kanonikus arc tartalom."

    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after == before


# 9. Candidate generálása után MINDEN felsorolt kontextusváltozás blokkolja
#    az átvételt, nulla kanonikus mutációval.


def _generate_candidate(state: dict) -> None:
    """Kézi tartalommal tölti fel az arcot, majd egy sikeres generálással
    candidate-et hoz létre — innen tesztelhető minden context-mutáció."""
    update_arc_point(state, "entry", "Már van kézzel írt tartalom.")
    gen = _CountingGenerator()
    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert outcome.status == "candidate"


def _assert_accept_blocked_with_zero_mutation(
    state: dict, *, expected_reason: str = "context_hash_mismatch"
) -> None:
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_candidate = copy.deepcopy(state["sermon_workshop"]["arc_candidate"])

    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is False
    assert result["reason"] == expected_reason
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] == before_candidate


def test_reference_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["last_igehely"] = "Róm 8,28"
    state["igehely_input"] = "Róm 8,28"
    # A referencia-eltérést `accept_arc_candidate` a hash-egyeztetés előtt
    # ellenőrzi (RESET 2A, változatlan sorrend) — a reason itt
    # "reference_mismatch", nem "context_hash_mismatch". A candidate
    # identitásának VÉDELME (nulla mutáció) ettől függetlenül azonos.
    _assert_accept_blocked_with_zero_mutation(state, expected_reason="reference_mismatch")


def test_passage_text_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["passage_text"] = "Egy teljesen más bibliai szöveg."
    _assert_accept_blocked_with_zero_mutation(state)


def test_bible_translation_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["bible_translation"] = "KAR"
    _assert_accept_blocked_with_zero_mutation(state)


def test_text_main_idea_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    _set_text_main_idea(state, "A textus fő gondolata SENTINEL.")
    _assert_accept_blocked_with_zero_mutation(state)


def test_sermon_main_idea_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    _set_sermon_main_idea(state, "Fókuszmondat SENTINEL.")
    _assert_accept_blocked_with_zero_mutation(state)


def test_overview_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["overview"] = "Bibliai áttekintés SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_exegesis_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["exegesis"] = "Exegézis SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_original_text_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["original_text"] = "Eredeti nyelvi anyag SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_history_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["history"] = "Kortörténet SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_theology_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["theology"] = "Teológia SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_accept_after_candidate_blocked_by_mutation_triggers_zero_ai_calls():
    state = _base_state()
    _generate_candidate(state)
    state["overview"] = "Bibliai áttekintés SENTINEL."
    context = arc_ai.build_arc_generation_context(state)
    accept_arc_candidate(state, reference=context.reference, context_hash=context.context_hash)
    # Az elutasított átvétel sem hívhat AI-t — a candidate generálásához
    # használt `gen`-en kívül nincs újabb hívás (itt csak a mutáció-mentes
    # elutasítást ellenőrizzük, AI-hívás nélkül, ami már a fenti helper
    # `accept_arc_candidate` szignatúrájából is következik: nincs
    # `generate_fn` paramétere).
    assert "generate_fn" not in inspect.signature(accept_arc_candidate).parameters


# 10. Az eredeti teljes kontextus visszaállítása után a candidate átvehető.


def test_restoring_original_context_makes_candidate_acceptable_again():
    state = _base_state()
    _generate_candidate(state)

    state["overview"] = "Ideiglenes módosítás."
    context = arc_ai.build_arc_generation_context(state)
    blocked = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )
    assert blocked["accepted"] is False

    state["overview"] = ""  # vissza az eredeti (üres) állapotra
    context2 = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context2.reference, context_hash=context2.context_hash
    )
    assert result["accepted"] is True
    assert state["sermon_workshop"]["arc_candidate"] is None
    for key, text in VALID_POINTS.items():
        assert state["sermon_workshop"]["arc"][key]["text"] == text


# 11. Kézi arc-szerkesztés a lapos UI-n az aktuális teljes context_hash-t
#     írja az `arc_meta` mezőbe.


def test_manual_edit_via_flat_ui_writes_full_context_hash_into_arc_meta(monkeypatch):
    import streamlit as st

    state = _base_state()
    monkeypatch.setattr(st, "session_state", state)

    expected_hash = arc_ai.build_arc_generation_context(state).context_hash
    assert expected_hash != ""

    state[sw_ui._KEY_FLAT_ARC["arrival"]] = "Megérkezés élő szerkesztés."
    sw_ui._flat_save_arc_point("arrival")

    assert state["sermon_workshop"]["arc_meta"]["context_hash"] == expected_hash
    assert state["sermon_workshop"]["arc"]["arrival"]["context_hash"] == expected_hash


def test_manual_edit_via_flat_ui_arc_meta_hash_changes_when_context_changes(monkeypatch):
    import streamlit as st

    state = _base_state()
    monkeypatch.setattr(st, "session_state", state)

    state[sw_ui._KEY_FLAT_ARC["entry"]] = "Belépés első verzió."
    sw_ui._flat_save_arc_point("entry")
    first_hash = state["sermon_workshop"]["arc_meta"]["context_hash"]

    state["passage_text"] = "Megváltozott bibliai szöveg."
    state[sw_ui._KEY_FLAT_ARC["entry"]] = "Belépés második verzió."
    sw_ui._flat_save_arc_point("entry")
    second_hash = state["sermon_workshop"]["arc_meta"]["context_hash"]

    assert second_hash != first_hash


# 12. A régi, nem hétpontos hívók (közvetlen `update_arc_point()` hívás
#     `context_hash` nélkül) visszafelé kompatibilisek maradnak.


def test_update_arc_point_without_context_hash_param_is_fully_backward_compatible():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    assert state["sermon_workshop"]["arc_meta"]["context_hash"] == ""

    point = update_arc_point(state, "deepening", "Régi hívó, nincs context_hash átadva.")

    # A pont saját mezője a régi, szűk (lusta importos) hash-elvet kapja,
    # az `arc_meta.context_hash` pedig — pontosan mint a korrekció előtt —
    # ÉRINTETLEN marad, mert a hívó nem adott át semmit.
    assert point["text"] == "Régi hívó, nincs context_hash átadva."
    assert state["sermon_workshop"]["arc_meta"]["context_hash"] == ""
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""


def test_update_arc_point_signature_gained_only_an_optional_keyword_param():
    sig = inspect.signature(update_arc_point)
    params = sig.parameters
    assert "context_hash" in params
    assert params["context_hash"].default is None
    assert params["context_hash"].kind == inspect.Parameter.KEYWORD_ONLY
    # A pozicionális paraméterek sorrendje/száma változatlan.
    positional = [
        name
        for name, p in params.items()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    assert positional == ["session_state", "point_key", "text"]
