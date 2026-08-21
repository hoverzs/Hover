"""RESET 2E-3 — a részletes prédikációs munkavázlat MI-rétegének tesztjei.

A kétlépcsős vázlatmotor MÁSODIK lépcsője: (RESET 2E-2) blueprint ->
részletes vázlat. Ebben a fázisban nincs UI, nincs automatikus láncolás,
és a blueprint AI döntési logikáját nem módosítjuk.

FONTOS: a modul neve TUDATOSAN `sermon_workshop_developed_outline_ai`, NEM
`sermon_workshop_outline_ai` — az utóbbi már létező, aktív, régi
vázlatmotor (M10), amit nem érintünk.

Minden teszt hálózatmentes, mockolt `generate_fn`-nel dolgozik — valódi
API-kulcs vagy Gemini-hívás egyikben sincs. A "friss blueprint" állapotot
a TÉNYLEGES `sermon_workshop_blueprint_ai.generate_sermon_blueprint`
pipeline-on keresztül állítjuk elő (mockolt generátorral), nem kézzel
összerakott state-tel — így a frissesség-ellenőrzés a valódi
kontextus-szerződést teszteli, nem egy párhuzamos tesztfixture-logikát.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_blueprint_ai as bp_ai  # noqa: E402
import sermon_workshop_developed_outline_ai as ol_ai  # noqa: E402
from sermon_workshop_data import (  # noqa: E402
    _ARC_POINT_KEYS,
    _DEVELOPED_MOVEMENT_LIST_FIELDS,
    _DEVELOPED_MOVEMENT_TEXT_FIELDS,
    accept_developed_outline_candidate,
    ensure_sermon_workshop_state,
    set_arc_candidate,
    set_developed_outline_candidate,
    set_field_refinement_suggestion,
    store_generated_blueprint_result,
    update_arc_point,
)
from textus_workshop_data import ensure_text_workshop_state  # noqa: E402

PASSAGE = "Mert kegyelemből van üdvösségetek hit által."
REFERENCE = "Ef 2,4-10"


# =============================================================================
# Segédek
# =============================================================================


class _CountingGenerator:
    """Hívásszámláló mock `generate_fn` — sosem hív hálózatot."""

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


def _base_state() -> dict:
    state: dict = {}
    ensure_sermon_workshop_state(state)
    ensure_text_workshop_state(state)
    state["last_igehely"] = REFERENCE
    state["igehely_input"] = REFERENCE
    state["passage_text"] = PASSAGE
    state["bible_translation"] = "RÚF 2014"
    return state


def _movement(key: str, grounded=()) -> dict:
    return {
        "key": key,
        "function": f"{key} funkció",
        "core_idea": f"{key} mag",
        "grounded_in": list(grounded),
    }


def _blueprint_payload(*, mode="seven_point", verdict="strong_fit", movements=None) -> dict:
    if movements is None:
        movements = [_movement(k) for k in _ARC_POINT_KEYS]
    return {
        "central_claim": "Isten kegyelemből, nem teljesítményből tart meg.",
        "textual_center": "A »De Isten« fordulat a szakasz szíve.",
        "listener_tension": "Muszáj-e kiérdemelnem az elfogadást?",
        "theological_turn": "A kegyelem megelőzi az embert.",
        "desired_listener_movement": "A teljesítménykényszertől a hálás szabadságig.",
        "arc_fit": {"verdict": verdict, "reason": "A szakasz érvelése ezt hordozza."},
        "recommended_structure": {"mode": mode, "movements": movements},
        "key_support": {
            "exegetical": ["A 4. vers fordulata."],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "Teljesítménykényszer a hétköznapokban.",
        "application_direction": "Hálából fakadó cselekvés.",
        "warnings": [],
    }


def _install_fresh_blueprint(state: dict, **kwargs) -> dict:
    """A VALÓDI blueprint-pipeline-on keresztül állít be egy friss,
    konzisztens blueprintet + blueprint_meta-t (mockolt generátorral) —
    nem kézzel összerakott, esetleg inkonzisztens state-tel."""
    payload = _blueprint_payload(**kwargs)
    outcome = bp_ai.generate_sermon_blueprint(
        state,
        generate_fn=lambda prompt, **kw: json.dumps(payload, ensure_ascii=False),
    )
    assert outcome.ok is True, outcome.error_message
    return payload


def _outline_movement(key: str) -> dict:
    return {
        "key": key,
        "title": f"{key} cím",
        "function": f"{key} funkció",
        "main_claim": f"{key} fő állítása egy tömör mondatban.",
        "development": [f"{key} kibontás 1.", f"{key} kibontás 2."],
        "exegetical_support": [],
        "original_language_support": [],
        "historical_theological_support": [],
        "illustration_direction": "",
        "application_direction": "",
        "transition_to_next": "",
    }


def _valid_outline_payload(keys: list[str], *, mode="seven_point") -> dict:
    return {
        "structure_mode": mode,
        "structure_note": "",
        "movements": [_outline_movement(k) for k in keys],
    }


def _valid_outline_json(keys: list[str], **kwargs) -> str:
    return json.dumps(_valid_outline_payload(keys, **kwargs), ensure_ascii=False)


def _context(state: dict) -> ol_ai.OutlineContext:
    return ol_ai.build_developed_outline_context(state)


# =============================================================================
# A-B. Blueprint jelenlét / frissesség — blokkoló kapu
# =============================================================================


def test_a_missing_blueprint_blocks_with_zero_ai_calls():
    state = _base_state()
    gen = _CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    outcome = ol_ai.generate_developed_outline(state, generate_fn=gen)
    assert outcome.ok is False
    assert outcome.status == "blocked"
    assert outcome.reason == "missing_blueprint"
    assert len(gen.calls) == 0
    assert state["sermon_workshop"]["developed_outline_candidate"] is None


def test_b_stale_blueprint_blocks_with_zero_ai_calls():
    state = _base_state()
    _install_fresh_blueprint(state)
    assert ol_ai.is_blueprint_fresh(state) is True

    # A blueprint elkészülte UTÁN megváltozik egy kanonikus bemenet, amit
    # a blueprint context builder olvas — de a blueprintet nem
    # generáljuk újra.
    update_arc_point(state, "entry", "NEW_ARC_TEXT_AFTER_BLUEPRINT")
    assert ol_ai.is_blueprint_fresh(state) is False

    gen = _CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    outcome = ol_ai.generate_developed_outline(state, generate_fn=gen)
    assert outcome.ok is False
    assert outcome.status == "blocked"
    assert outcome.reason == "blueprint_stale"
    assert len(gen.calls) == 0
    assert state["sermon_workshop"]["developed_outline_candidate"] is None


def test_missing_reference_and_passage_text_block_before_freshness():
    for missing_key in ("last_igehely", "passage_text"):
        state = _base_state()
        _install_fresh_blueprint(state)
        state[missing_key] = ""
        if missing_key == "last_igehely":
            state["igehely_input"] = ""
        else:
            state["passage_text_input"] = ""
        gen = _CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
        outcome = ol_ai.generate_developed_outline(state, generate_fn=gen)
        assert outcome.ok is False
        assert outcome.status == "blocked"
        assert outcome.reason in ("missing_reference", "missing_passage_text")
        assert len(gen.calls) == 0


# =============================================================================
# C. Friss blueprint -> AI-hívás megtörténik
# =============================================================================


def test_c_fresh_blueprint_triggers_ai_call():
    state = _base_state()
    _install_fresh_blueprint(state)
    gen = _CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    outcome = ol_ai.generate_developed_outline(state, generate_fn=gen)
    assert outcome.ok is True
    assert len(gen.calls) == 1


def test_generation_uses_structured_json_schema_and_own_system_prompt():
    state = _base_state()
    _install_fresh_blueprint(state)
    gen = _CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    ol_ai.generate_developed_outline(state, generate_fn=gen)

    kwargs = gen.calls[0]["kwargs"]
    assert kwargs["response_mime_type"] == "application/json"
    assert kwargs["response_schema"] is ol_ai.DEVELOPED_OUTLINE_RESPONSE_SCHEMA
    assert kwargs["system_bundle"] is ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert kwargs["include_brevity_directive"] is False
    assert kwargs["use_cache"] is False


# =============================================================================
# D. Bemeneti izoláció — nyers state SOHA nem kerül a promptba
# =============================================================================


def test_d_prompt_never_leaks_raw_state_only_blueprint_content():
    state = _base_state()
    _install_fresh_blueprint(state)

    state["overview"] = "RAW_OVERVIEW_SENTINEL"
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["history"] = "RAW_HISTORY_SENTINEL"
    state["theology"] = "RAW_THEOLOGY_SENTINEL"
    state["original_text"] = "RAW_ORIGINAL_SENTINEL"
    state["text_workshop"]["text_summary"]["main_idea"] = "TEXT_SUMMARY_SENTINEL"
    state["text_workshop"]["text_summary"]["status"] = "approved"
    state["text_workshop"]["text_main_idea"] = "TEXT_MAIN_IDEA_SENTINEL"
    state["sermon_workshop"]["sermon_main_idea"] = "SERMON_MAIN_IDEA_SENTINEL"
    update_arc_point(state, "starting_point", "ARC_TEXT_SENTINEL")
    set_arc_candidate(
        state,
        points={k: {"text": f"ARC_CAND_{k}"} for k in _ARC_POINT_KEYS},
        reference=REFERENCE,
        context_hash="H1",
    )
    set_field_refinement_suggestion(
        state, "starting_point", text="FIELD_REF_SENTINEL", reference=REFERENCE, context_hash="H1"
    )
    set_developed_outline_candidate(
        state,
        outline={"movements": [{"key": "entry", "main_claim": "DEV_CAND_SENTINEL"}]},
        reference=REFERENCE,
        context_hash="H1",
    )

    # A kontextust és a promptot a MÁR TÁROLT blueprintből építjük — ami az
    # `_install_fresh_blueprint` hívás idején keletkezett, a fenti
    # mutációk előtt.
    context = _context(state)
    prompt = ol_ai.build_developed_outline_prompt(context)
    for sentinel in (
        "RAW_OVERVIEW_SENTINEL",
        "RAW_EXEGESIS_SENTINEL",
        "RAW_HISTORY_SENTINEL",
        "RAW_THEOLOGY_SENTINEL",
        "RAW_ORIGINAL_SENTINEL",
        "TEXT_SUMMARY_SENTINEL",
        "TEXT_MAIN_IDEA_SENTINEL",
        "SERMON_MAIN_IDEA_SENTINEL",
        "ARC_TEXT_SENTINEL",
        "ARC_CAND_entry",
        "FIELD_REF_SENTINEL",
        "DEV_CAND_SENTINEL",
    ):
        assert sentinel not in prompt, sentinel


# =============================================================================
# E. Passage grounding
# =============================================================================


def test_e_reference_and_passage_text_enter_context_and_prompt():
    state = _base_state()
    _install_fresh_blueprint(state)
    context = _context(state)
    assert context.reference == REFERENCE
    assert context.passage_text == PASSAGE

    prompt = ol_ai.build_developed_outline_prompt(context)
    assert REFERENCE in prompt
    assert PASSAGE in prompt


# =============================================================================
# F-H. Outline context hash
# =============================================================================


def test_f_identical_input_produces_identical_hash():
    a = _base_state()
    _install_fresh_blueprint(a)
    b = _base_state()
    _install_fresh_blueprint(b)
    ha = _context(a).context_hash
    hb = _context(b).context_hash
    assert ha == hb
    assert ha != ""


def test_g_blueprint_content_change_changes_hash_even_with_identical_upstream_hash():
    """Két blueprint UGYANAZZAL az upstream `blueprint_meta.context_hash`
    értékkel (mintha ugyanabból a bemenetből, de eltérő tartalommal
    generálódott volna újra), de eltérő tényleges tartalommal -> az
    outline-context-hash-nek EL KELL térnie."""
    a = _base_state()
    b = _base_state()
    payload_a = _blueprint_payload()
    payload_b = _blueprint_payload()
    payload_b["central_claim"] = "MÁS KÖZPONTI ÁLLÍTÁS."
    store_generated_blueprint_result(a, blueprint=payload_a, context_hash="SAME_UPSTREAM_HASH")
    store_generated_blueprint_result(b, blueprint=payload_b, context_hash="SAME_UPSTREAM_HASH")

    ctx_a = _context(a)
    ctx_b = _context(b)
    assert ctx_a.blueprint_context_hash == ctx_b.blueprint_context_hash == "SAME_UPSTREAM_HASH"
    assert ctx_a.context_hash != ctx_b.context_hash
    assert ctx_a.context_hash != "" and ctx_b.context_hash != ""


def test_h_irrelevant_state_does_not_change_hash():
    state = _base_state()
    _install_fresh_blueprint(state)
    baseline = _context(state).context_hash

    set_arc_candidate(
        state, points={k: {"text": "X"} for k in _ARC_POINT_KEYS}, reference=REFERENCE, context_hash="H1"
    )
    set_field_refinement_suggestion(state, "entry", text="Y", reference=REFERENCE, context_hash="H1")
    set_developed_outline_candidate(
        state, outline={"movements": [{"key": "entry"}]}, reference=REFERENCE, context_hash="H1"
    )
    state["_sw_ui_resync"] = True
    state["ui_mode"] = "workshop"
    state["quick_tools_active_tab"] = 3
    state["sermon_workshop"]["blueprint_meta"]["generated_at"] = "MÁS_IDŐBÉLYEG"

    assert _context(state).context_hash == baseline


# =============================================================================
# I-K. Érvényes válaszok: seven-point / merged / custom
# =============================================================================


def test_i_seven_point_valid_response_is_accepted():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point", verdict="strong_fit")
    gen = _CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS), mode="seven_point"))
    outcome = ol_ai.generate_developed_outline(state, generate_fn=gen)
    assert outcome.ok is True
    assert outcome.status == "candidate"
    assert [m["key"] for m in outcome.outline["movements"]] == list(_ARC_POINT_KEYS)
    assert outcome.outline["structure_mode"] == "seven_point"


def test_j_merged_valid_response_is_accepted():
    for keys in (
        ["entry", "starting_point", "deepening", "second_shift", "arrival"],
        ["entry", "starting_point", "first_shift", "deepening", "reinterpretation", "arrival"],
    ):
        state = _base_state()
        _install_fresh_blueprint(
            state, mode="merged", verdict="partial_fit", movements=[_movement(k) for k in keys]
        )
        gen = _CountingGenerator(_valid_outline_json(keys, mode="merged"))
        outcome = ol_ai.generate_developed_outline(state, generate_fn=gen)
        assert outcome.ok is True, keys
        assert [m["key"] for m in outcome.outline["movements"]] == keys


def test_k_custom_valid_response_is_accepted():
    for count in (3, 4, 5):
        keys = [f"custom_{i}" for i in range(1, count + 1)]
        state = _base_state()
        _install_fresh_blueprint(
            state, mode="custom", verdict="weak_fit", movements=[_movement(k) for k in keys]
        )
        gen = _CountingGenerator(_valid_outline_json(keys, mode="custom"))
        outcome = ol_ai.generate_developed_outline(state, generate_fn=gen)
        assert outcome.ok is True, count
        assert [m["key"] for m in outcome.outline["movements"]] == keys


# =============================================================================
# L-Q. Elutasítási szabályok
# =============================================================================


def test_l_structure_mode_mismatch_is_rejected():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point")
    bad = _valid_outline_json(list(_ARC_POINT_KEYS), mode="merged")
    result = ol_ai.validate_developed_outline_response(
        bad, blueprint=state["sermon_workshop"]["blueprint"]
    )
    assert result.ok is False
    assert result.reason == "structure_mode_mismatch"


def test_m_movement_count_mismatch_is_rejected():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point")
    bad = _valid_outline_json(list(_ARC_POINT_KEYS)[:6], mode="seven_point")
    result = ol_ai.validate_developed_outline_response(
        bad, blueprint=state["sermon_workshop"]["blueprint"]
    )
    assert result.ok is False
    assert result.reason == "movement_count_mismatch"


def test_n_movement_key_mismatch_is_rejected():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point")
    keys = list(_ARC_POINT_KEYS)[:6] + ["kitalalt_kulcs"]
    bad = _valid_outline_json(keys, mode="seven_point")
    result = ol_ai.validate_developed_outline_response(
        bad, blueprint=state["sermon_workshop"]["blueprint"]
    )
    assert result.ok is False
    assert result.reason == "movement_key_mismatch"


def test_o_movement_order_mismatch_is_rejected():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point")
    shuffled = list(_ARC_POINT_KEYS)
    shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    bad = _valid_outline_json(shuffled, mode="seven_point")
    result = ol_ai.validate_developed_outline_response(
        bad, blueprint=state["sermon_workshop"]["blueprint"]
    )
    assert result.ok is False
    assert result.reason == "movement_order_mismatch"


def test_p_empty_required_movement_fields_are_rejected():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point")
    for field, reason in (
        ("title", "empty_title"),
        ("function", "empty_function"),
        ("main_claim", "empty_main_claim"),
    ):
        payload = _valid_outline_payload(list(_ARC_POINT_KEYS), mode="seven_point")
        payload["movements"][0][field] = "   "
        result = ol_ai.validate_developed_outline_response(
            json.dumps(payload, ensure_ascii=False),
            blueprint=state["sermon_workshop"]["blueprint"],
        )
        assert result.ok is False, field
        assert result.reason == reason, field


def test_q_empty_development_is_rejected():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point")

    payload = _valid_outline_payload(list(_ARC_POINT_KEYS), mode="seven_point")
    payload["movements"][0]["development"] = []
    result = ol_ai.validate_developed_outline_response(
        json.dumps(payload, ensure_ascii=False), blueprint=state["sermon_workshop"]["blueprint"]
    )
    assert result.ok is False
    assert result.reason == "empty_development"

    payload2 = _valid_outline_payload(list(_ARC_POINT_KEYS), mode="seven_point")
    payload2["movements"][0]["development"] = ["   ", 42, None]
    result2 = ol_ai.validate_developed_outline_response(
        json.dumps(payload2, ensure_ascii=False), blueprint=state["sermon_workshop"]["blueprint"]
    )
    assert result2.ok is False
    assert result2.reason == "empty_development"


def test_movement_list_bounds_and_entry_shape_are_enforced():
    state = _base_state()
    _install_fresh_blueprint(state, mode="seven_point")
    blueprint = state["sermon_workshop"]["blueprint"]

    empty = _valid_outline_json([], mode="seven_point")
    assert ol_ai.validate_developed_outline_response(empty, blueprint=blueprint).reason == "empty_movements"

    not_list = json.dumps({"structure_mode": "seven_point", "structure_note": "", "movements": "x"})
    assert (
        ol_ai.validate_developed_outline_response(not_list, blueprint=blueprint).reason
        == "invalid_movements"
    )

    payload = _valid_outline_payload(list(_ARC_POINT_KEYS), mode="seven_point")
    payload["movements"][0] = "nem dict"
    result = ol_ai.validate_developed_outline_response(
        json.dumps(payload, ensure_ascii=False), blueprint=blueprint
    )
    assert result.reason == "invalid_movement_entry"

    for bad in (None, "", "   ", "nem json", "[]"):
        assert ol_ai.validate_developed_outline_response(bad, blueprint=blueprint).reason == "not_json"


# =============================================================================
# R-V. State-write lifecycle — candidate-only
# =============================================================================


def test_r_invalid_response_preserves_canonical_outline():
    state = _base_state()
    _install_fresh_blueprint(state)
    before = copy.deepcopy(state["sermon_workshop"]["developed_outline"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["developed_outline_meta"])

    outcome = ol_ai.generate_developed_outline(state, generate_fn=_CountingGenerator("nem json"))
    assert outcome.ok is False
    assert state["sermon_workshop"]["developed_outline"] == before
    assert state["sermon_workshop"]["developed_outline_meta"] == before_meta


def test_s_invalid_response_preserves_existing_candidate():
    state = _base_state()
    _install_fresh_blueprint(state)
    gen_good = _CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    outcome_good = ol_ai.generate_developed_outline(state, generate_fn=gen_good)
    assert outcome_good.ok is True
    before_candidate = copy.deepcopy(state["sermon_workshop"]["developed_outline_candidate"])

    outcome_bad = ol_ai.generate_developed_outline(state, generate_fn=_CountingGenerator("nem json"))
    assert outcome_bad.ok is False
    assert state["sermon_workshop"]["developed_outline_candidate"] == before_candidate


def test_t_valid_generation_creates_candidate_only_canonical_untouched():
    state = _base_state()
    _install_fresh_blueprint(state)
    before_outline = copy.deepcopy(state["sermon_workshop"]["developed_outline"])

    outcome = ol_ai.generate_developed_outline(
        state, generate_fn=_CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    )
    assert outcome.ok is True
    assert outcome.status == "candidate"
    assert state["sermon_workshop"]["developed_outline"] == before_outline
    candidate = state["sermon_workshop"]["developed_outline_candidate"]
    assert candidate is not None
    assert candidate["outline"]["movements"][0]["key"] == "entry"
    assert candidate["reference"] == REFERENCE
    assert candidate["context_hash"] == outcome.context_hash


def test_u_first_ever_generation_is_also_candidate_only():
    """RESET 2E-1A szabályának regressziós zárja: az ELSŐ generálás is
    candidate, sosem alkalmazódik automatikusan."""
    state = _base_state()
    _install_fresh_blueprint(state)
    assert state["sermon_workshop"]["developed_outline_candidate"] is None
    assert state["sermon_workshop"]["developed_outline"]["movements"] == []

    outcome = ol_ai.generate_developed_outline(
        state, generate_fn=_CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    )
    assert outcome.ok is True
    assert state["sermon_workshop"]["developed_outline"]["movements"] == []
    assert state["sermon_workshop"]["developed_outline_candidate"] is not None


def test_v_regeneration_never_overwrites_canonical_even_after_accept():
    state = _base_state()
    _install_fresh_blueprint(state)

    outcome1 = ol_ai.generate_developed_outline(
        state, generate_fn=_CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    )
    assert outcome1.ok is True
    accepted = accept_developed_outline_candidate(
        state, reference=REFERENCE, context_hash=outcome1.context_hash
    )
    assert accepted["accepted"] is True
    canonical_after_accept = copy.deepcopy(state["sermon_workshop"]["developed_outline"])
    assert canonical_after_accept["movements"] != []

    outcome2 = ol_ai.generate_developed_outline(
        state, generate_fn=_CountingGenerator(_valid_outline_json(list(_ARC_POINT_KEYS)))
    )
    assert outcome2.ok is True
    assert state["sermon_workshop"]["developed_outline"] == canonical_after_accept
    assert state["sermon_workshop"]["developed_outline_candidate"] is not None


def test_api_error_and_exception_cause_zero_mutation():
    state = _base_state()
    _install_fresh_blueprint(state)

    for response in ("⚠️ Hiba történt a generálás közben.", "⏳ Túl sok kérés."):
        outcome = ol_ai.generate_developed_outline(state, generate_fn=_CountingGenerator(response))
        assert outcome.ok is False
        assert outcome.reason == "api_error"
        assert state["sermon_workshop"]["developed_outline_candidate"] is None

    def raising(prompt, **kwargs):
        raise RuntimeError("hálózati hiba")

    outcome = ol_ai.generate_developed_outline(state, generate_fn=raising)
    assert outcome.ok is False
    assert outcome.reason == "generate_failed"
    assert state["sermon_workshop"]["developed_outline_candidate"] is None


# =============================================================================
# W. Response schema shape
# =============================================================================


def test_w_response_schema_matches_v1_developed_outline_model():
    props = ol_ai.DEVELOPED_OUTLINE_RESPONSE_SCHEMA["properties"]
    assert set(props.keys()) == {"structure_mode", "structure_note", "movements"}

    movement_props = props["movements"]["items"]["properties"]
    expected_fields = set(_DEVELOPED_MOVEMENT_TEXT_FIELDS) | set(_DEVELOPED_MOVEMENT_LIST_FIELDS)
    assert set(movement_props.keys()) == expected_fields


# =============================================================================
# X-Y. Rendszerprompt invariánsok
# =============================================================================


def test_x_no_full_sermon_instruction():
    assert "részletes munkavázlatot" in ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "NEM kész, felolvasható prédikációt" in ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert (
        "NEM írsz előbb hosszú, kész prédikációs prózát"
        in ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    )


def test_y_prompt_and_system_prompt_forbid_movement_redesign():
    state = _base_state()
    _install_fresh_blueprint(state)
    prompt = ol_ai.build_developed_outline_prompt(_context(state))

    assert "Új mozgást NEM adhatsz hozzá" in prompt
    assert "NEM rendezheted át" in prompt
    assert "sem nevezheted át" in prompt
    assert "nem változtatod meg a `structure_mode`-ot" in ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "pontosan a blueprint mozgásait bontod ki" in ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT


# =============================================================================
# Modul-izoláció
# =============================================================================


def test_outline_module_forbidden_dependencies_and_sanctioned_exception():
    """A modul FÜGGETLEN a régi section-szintű MI-segédektől és az
    app/streamlit rétegtől. Az EGYETLEN szándékos, dokumentált kivétel a
    `sermon_workshop_blueprint_ai` — kizárólag a determinisztikus
    kontextus-hash szerződés (freshness-check) újrafelhasználásához."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ol_ai))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {
        "sermon_workshop_arc_ai",
        "sermon_workshop_refinement_ai",
        "textus_summary_ai",
        "sermon_outline_engine",
        "sermon_workshop_outline_ai",
        "app",
        "streamlit",
    }
    assert not (imported & forbidden), imported & forbidden
    assert "sermon_workshop_data" in imported
    assert "sermon_workshop_blueprint_ai" in imported


def test_outline_module_never_calls_generate_text_directly():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ol_ai))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "generate_text" not in called_names


def test_outline_system_prompt_is_standalone_and_not_shared_with_blueprint():
    assert ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT != bp_ai.BLUEPRINT_SYSTEM_PROMPT
    assert ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT.startswith("SZEREP:")
    assert "BASE_SYSTEM_PROMPT" not in ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT


def test_developed_outline_tab_has_a_dedicated_evidence_based_token_budget():
    """LOCAL MANUAL QA FIX: a budget NEM találgatás -- 2 valódi Gemini-
    hívás `usageMetadata`-ja (thoughtsTokenCount + candidatesTokenCount)
    6345-9087 közé esett egy teljes, blueprintből kibontott munkavázlatnál
    (1Móz 32,23-32 kontextussal) -- a 16000-es érték ésszerű tartalékot ad
    a MEGFIGYELT maximum fölé, NEM egy vakon nagyra állított plafon."""
    import app

    assert "Részletes prédikációs munkavázlat" in app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB
    budget = app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB["Részletes prédikációs munkavázlat"]
    observed_max = 9087
    assert budget >= observed_max * 1.5
    assert budget <= observed_max * 2.5


# =============================================================================
# LOCAL QA FINAL FUNCTIONAL POLISH (2026-08-21) — redundancia-csökkentés
# és upstream bizonytalanság megőrzése. Invariant tesztek a promptra, nem
# egyetlen bibliai történetre drótozva.
# =============================================================================


def test_optional_fields_default_to_empty_not_auto_filled():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "`exegetical_support`: ÜRES LISTA az alapértelmezett" in prompt
    assert "`illustration_direction`: ÜRES STRING az alapértelmezett" in prompt
    assert "`application_direction`: ÜRES STRING az alapértelmezett" in prompt


def test_application_folds_into_last_development_bullet():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "UTOLSÓ development-pont" in prompt
    assert "application_direction` maradjon üres string" in prompt


def test_illustration_direction_forbids_generic_search_task_pattern():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "TILOS az olyan mondatszerkezet" in prompt
    assert "Egy történet/példa arról/arra, amikor valaki" in prompt
    assert "MEGNEVEZETT, behatárolt területet" in prompt


def test_illustration_direction_still_forbids_fabricated_real_events():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "Ne találj ki ellenőrizhetetlen történelmi vagy valós személyhez köthető történetet." in prompt


def test_system_prompt_requires_preserving_upstream_uncertainty():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "A KANONIKUS BLUEPRINT BIZONYTALANSÁGI SZINTJÉT ŐRZÖD MEG" in prompt
    assert '"A küzdő fél maga Isten."' in prompt


def test_system_prompt_forbids_categorical_certainty_qualifiers():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "egyértelműen" in prompt
    assert "TILOSAK egy olyan kérdésnél" in prompt
    assert "biztosan, kétségtelenül, nyilvánvalóan" in prompt


def test_system_prompt_forbids_the_adjective_form_of_nyilvanvalo_too():
    """FINAL SERMON UX POLISH (2026-08-21): real-API retest 1Móz32-n
    kimutatta, hogy a modell a "nyilvánvalóan" (határozó) tiltása mellett
    a "nyilvánvaló" (melléknév) alakkal kerülte meg a szabályt, méghozzá
    UGYANABBAN a mondatban, ami korábban helyesen nyitva hagyta a küzdő
    fél kilétét ("...a küzdő fél pontos identitását a szöveg nyitva
    hagyja... de a találkozás isteni dimenziója nyilvánvaló."). A prompt
    mostantól explicit tiltja a ragozott alakokat is, és külön kimondja,
    hogy a mondat egyik fele sem zárhatja le, amit a másik nyitva hagyott."""
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "nyilvánvaló — RAGOZOTT ALAKBAN IS" in prompt
    assert "ne zárd le az imént nyitva hagyott bizonytalanságot" in prompt


def test_system_prompt_distinguishes_textual_fact_exegetical_inference_and_homiletical_application():
    """FINAL SERMON UX POLISH (2026-08-21): a downstream epistemikus
    fegyelem — a homiletikai következtetés ne jelenjen meg exegetikai
    vagy textuális tényként."""
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "HOMILETIKAI KÖVETKEZTETÉST NE FOGALMAZZ ÚGY, MINTHA MAGA A TEXTUS BIZONYÍTANÁ" in prompt
    assert "amit a textus explicit mond" in prompt
    assert "amit az exegézis valószínű vagy lehetséges értelmezésként ad" in prompt
    assert "amit a prédikáció homiletikai alkalmazásként épít tovább" in prompt


def test_system_prompt_gives_concrete_bad_good_homiletical_application_examples():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert '"A sérülés azt mutatja, hogy Isten ereje a gyengeségben teljesedik ki."' in prompt
    assert "Homiletikailag a sérülés megnyithatja a gyengeség és az Istentől való függés témáját." in prompt
    assert '"Jákób a csalóból Isten harcosává válik."' in prompt
    assert '"A küzdelem nem elkerülendő, hanem az átalakulás része."' in prompt


def test_blueprint_system_prompt_also_preserves_upstream_uncertainty():
    assert (
        "A KANONIKUS BEMENET BIZONYTALANSÁGI SZINTJÉT ŐRIZD MEG"
        in bp_ai.BLUEPRINT_SYSTEM_PROMPT
    )


def test_target_length_reduction_is_specified_without_impoverishing_content():
    prompt = ol_ai.DEVELOPED_OUTLINE_SYSTEM_PROMPT
    assert "15-25%-kal kevesebb szöveg" in prompt
    assert "Ne legyen vázlatosan szegényes" in prompt
