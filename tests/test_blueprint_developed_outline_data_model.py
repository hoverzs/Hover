"""RESET 2E-1 — a kétlépcsős vázlatmotor ADATMODELLJÉNEK tesztjei.

A RESET 2E-0 architekturális audit elfogadott iránya:
`kanonikus bemenet → belső homiletikai blueprint → részletes vázlat`

Ez a fázis KIZÁRÓLAG adatmodell: nincs Gemini-hívás, nincs prompt, nincs
UI, és a meglévő `arc` generálás változatlan. Ezek a tesztek ennek
megfelelően kizárólag a sémát, a normalizálást, a visszafelé
kompatibilitást, a candidate-életciklust és a kézi szerkesztést
vizsgálják — semmilyen AI- vagy UI-viselkedést nem.

A `sermon_workshop_data.py` meglévő filozófiáját követik: a normalize
legyen védekező, de NE agresszív (a részleges tartalmat sosem dobja el
csak azért, mert egy opcionális mező hiányzik).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (  # noqa: E402
    accept_developed_outline_candidate,
    developed_outline_has_content,
    discard_developed_outline_candidate,
    empty_blueprint,
    empty_blueprint_meta,
    empty_developed_outline,
    empty_developed_outline_meta,
    empty_developed_outline_movement,
    empty_sermon_outline,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_blueprint,
    normalize_blueprint_meta,
    normalize_developed_outline,
    normalize_developed_outline_candidate,
    normalize_developed_outline_meta,
    normalize_developed_outline_movement,
    normalize_sermon_workshop,
    set_developed_outline_candidate,
    store_generated_developed_outline_result,
    update_developed_outline_movement_field,
)
from workspace_data import build_project_data  # noqa: E402

NEW_KEYS = (
    "blueprint",
    "blueprint_meta",
    "developed_outline",
    "developed_outline_meta",
    "developed_outline_candidate",
)


def _movement(key: str, **overrides) -> dict:
    base = {
        "key": key,
        "title": f"{key} cím",
        "function": f"{key} funkció",
        "main_claim": f"{key} fő állítás",
        "development": [f"{key} kibontás 1.", f"{key} kibontás 2."],
        "exegetical_support": [f"{key} exegetikai megfigyelés"],
        "original_language_support": [],
        "historical_theological_support": [],
        "illustration_direction": "",
        "application_direction": "",
        "transition_to_next": f"{key} átvezetés",
    }
    base.update(overrides)
    return base


def _outline(*keys: str) -> dict:
    return {
        "structure_mode": "seven_point",
        "structure_note": "Teljes hétpontos ív.",
        "movements": [_movement(k) for k in keys],
    }


def _base_state() -> dict:
    state: dict = {}
    ensure_sermon_workshop_state(state)
    return state


def _seed_canonical_outline(
    state: dict,
    *keys: str,
    reference: str = "Ef 2,4-10",
    context_hash: str = "H1",
) -> None:
    """Kanonikus vázlat előállítása a VALÓDI, teljes életcikluson át:
    generálás -> candidate -> explicit elfogadás.

    RESET 2E-1A óta a generálás SOSEM ír közvetlenül a kanonikus mezőbe
    (az első alkalommal sem), ezért a tesztek sem használhatják a
    generálást rövidítésként kanonikus tartalom beállítására — az egyetlen
    út az explicit `accept`."""
    store_generated_developed_outline_result(
        state, outline=_outline(*keys), reference=reference, context_hash=context_hash
    )
    result = accept_developed_outline_candidate(
        state, reference=reference, context_hash=context_hash
    )
    assert result["accepted"] is True, "a teszt-előkészítésnek sikerülnie kell"


# =============================================================================
# A. Default state
# =============================================================================


def test_a_default_state_contains_all_new_structures():
    sw = get_default_sermon_workshop()
    for key in NEW_KEYS:
        assert key in sw, key

    assert sw["blueprint"] == empty_blueprint()
    assert sw["blueprint_meta"] == empty_blueprint_meta()
    assert sw["developed_outline"] == empty_developed_outline()
    assert sw["developed_outline_meta"] == empty_developed_outline_meta()
    # A hiány maga `None` — nincs külön szentinel-dict (arc_candidate minta).
    assert sw["developed_outline_candidate"] is None


def test_a_default_blueprint_shape_is_type_stable():
    bp = empty_blueprint()
    for key in (
        "central_claim",
        "textual_center",
        "listener_tension",
        "theological_turn",
        "desired_listener_movement",
        "illustration_direction",
        "application_direction",
    ):
        assert bp[key] == ""
    assert bp["arc_fit"] == {"verdict": "", "reason": ""}
    assert bp["recommended_structure"] == {"mode": "", "movements": []}
    assert bp["key_support"] == {
        "exegetical": [],
        "original_language": [],
        "historical_theological": [],
    }
    assert bp["warnings"] == []


def test_a_default_developed_outline_movement_is_type_stable():
    mv = empty_developed_outline_movement()
    for key in (
        "key",
        "title",
        "function",
        "main_claim",
        "illustration_direction",
        "application_direction",
        "transition_to_next",
    ):
        assert mv[key] == ""
    # A kibontás és a támogató mezők LISTÁK — hogy 2-4 külön gondolat
    # önálló elemként legyen kezelhető, ne egy összefolyó szövegblokk.
    for key in (
        "development",
        "exegetical_support",
        "original_language_support",
        "historical_theological_support",
    ):
        assert mv[key] == []


def test_a_no_blueprint_candidate_key_exists():
    """A blueprint BELSŐ artefaktum — a felhasználó sosem szerkeszti,
    ezért nincs mit védeni néma felülírástól, és nincs `blueprint_
    candidate` sem (ld. a modul RESET 2E-1 blokkjának indoklását)."""
    assert "blueprint_candidate" not in get_default_sermon_workshop()


# =============================================================================
# B. Backward compatibility — régi projekt, új kulcsok nélkül
# =============================================================================


def test_b_legacy_state_without_new_keys_gets_safe_defaults():
    legacy = {
        "sermon_main_idea": "Régi fókuszmondat.",
        "arc": {"entry": {"text": "Régi belépés."}},
    }
    for key in NEW_KEYS:
        assert key not in legacy

    sw = normalize_sermon_workshop(legacy)

    assert sw["blueprint"] == empty_blueprint()
    assert sw["blueprint_meta"] == empty_blueprint_meta()
    assert sw["developed_outline"] == empty_developed_outline()
    assert sw["developed_outline_meta"] == empty_developed_outline_meta()
    assert sw["developed_outline_candidate"] is None


def test_b_legacy_state_loses_no_existing_data():
    legacy = {
        "sermon_main_idea": "Régi fókuszmondat.",
        "sermon_main_idea_status": "approved",
        "arc": {"entry": {"text": "Régi belépés."}},
        "human_condition": {"condition": "Régi emberi helyzet."},
        "sermon_outline": {"content": "Régi, legacy vázlatszöveg."},
    }
    sw = normalize_sermon_workshop(legacy)

    assert sw["sermon_main_idea"] == "Régi fókuszmondat."
    assert sw["sermon_main_idea_status"] == "approved"
    assert sw["arc"]["entry"]["text"] == "Régi belépés."
    assert sw["human_condition"]["condition"] == "Régi emberi helyzet."
    assert sw["sermon_outline"]["content"] == "Régi, legacy vázlatszöveg."


def test_b_new_structures_survive_project_round_trip():
    state = _base_state()
    sw = state["sermon_workshop"]
    sw["blueprint"] = normalize_blueprint(
        {"central_claim": "Isten kegyelemből tart meg.", "warnings": ["Ellenőrizendő."]}
    )
    sw["blueprint_meta"] = normalize_blueprint_meta(
        {"context_hash": "HASH-BP", "generated_at": "2026-08-20T10:00:00"}
    )
    sw["developed_outline"] = normalize_developed_outline(_outline("entry", "arrival"))
    sw["developed_outline_meta"] = normalize_developed_outline_meta(
        {"reference": "Ef 2,4-10", "context_hash": "HASH-DO"}
    )

    project = build_project_data(state)
    reloaded: dict = dict(project)
    ensure_sermon_workshop_state(reloaded)
    out = reloaded["sermon_workshop"]

    assert out["blueprint"]["central_claim"] == "Isten kegyelemből tart meg."
    assert out["blueprint"]["warnings"] == ["Ellenőrizendő."]
    assert out["blueprint_meta"]["context_hash"] == "HASH-BP"
    assert len(out["developed_outline"]["movements"]) == 2
    assert out["developed_outline"]["movements"][0]["key"] == "entry"
    assert out["developed_outline_meta"]["reference"] == "Ef 2,4-10"


# =============================================================================
# C. Blueprint normalization — részleges / hibás bemenet
# =============================================================================


def test_c_blueprint_normalizes_from_garbage_inputs():
    for garbage in (None, "szöveg", 42, [], True):
        assert normalize_blueprint(garbage) == empty_blueprint()


def test_c_partial_blueprint_keeps_present_data_and_fills_the_rest():
    partial = {
        "central_claim": "A kegyelem megelőz minden emberi teljesítményt.",
        "arc_fit": {"verdict": "partial_fit"},  # `reason` hiányzik
        "key_support": {"exegetical": ["»De Isten…« — a fordulat a 4. versben."]},
        # `recommended_structure`, `warnings`, a többi szöveges mező hiányzik
    }
    bp = normalize_blueprint(partial)

    assert bp["central_claim"] == "A kegyelem megelőz minden emberi teljesítményt."
    assert bp["arc_fit"] == {"verdict": "partial_fit", "reason": ""}
    assert bp["key_support"]["exegetical"] == ["»De Isten…« — a fordulat a 4. versben."]
    assert bp["key_support"]["original_language"] == []
    assert bp["recommended_structure"] == {"mode": "", "movements": []}
    assert bp["warnings"] == []
    assert bp["textual_center"] == ""


def test_c_blueprint_wrong_types_fall_back_without_raising():
    broken = {
        "central_claim": None,
        "arc_fit": "nem dict",
        "recommended_structure": ["nem dict"],
        "key_support": 5,
        "warnings": "nem lista",
    }
    bp = normalize_blueprint(broken)
    assert bp["central_claim"] == ""
    assert bp["arc_fit"] == {"verdict": "", "reason": ""}
    assert bp["recommended_structure"] == {"mode": "", "movements": []}
    assert bp["key_support"]["exegetical"] == []
    assert bp["warnings"] == []


def test_c_blueprint_ignores_unknown_extra_keys():
    bp = normalize_blueprint({"central_claim": "X.", "ismeretlen_extra": "dobandó"})
    assert bp["central_claim"] == "X."
    assert "ismeretlen_extra" not in bp
    assert set(bp.keys()) == set(empty_blueprint().keys())


def test_c_blueprint_normalization_is_idempotent():
    raw = {
        "central_claim": "X.",
        "arc_fit": {"verdict": "strong_fit", "reason": "Narratív textus."},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [{"key": "entry", "core_idea": "Y.", "grounded_in": ["arc.entry"]}],
        },
        "key_support": {"exegetical": ["Z."]},
        "warnings": ["W."],
    }
    once = normalize_blueprint(raw)
    assert normalize_blueprint(once) == once


def test_c_arc_fit_verdict_is_stored_verbatim_without_decision_logic():
    """Ebben a fázisban NINCS strong/partial/weak döntési logika — az
    adatmodell bármilyen későbbi verdiktet biztonságosan eltárol."""
    for verdict in ("strong_fit", "partial_fit", "weak_fit", "", "bármi_más"):
        bp = normalize_blueprint({"arc_fit": {"verdict": verdict, "reason": "r"}})
        assert bp["arc_fit"]["verdict"] == verdict


# =============================================================================
# D. Adaptive movements — 7 / 5 / 3 custom mozgás adatvesztés nélkül
# =============================================================================


def _structure(keys):
    return {
        "recommended_structure": {
            "mode": "adaptive",
            "movements": [
                {
                    "key": k,
                    "function": f"{k} funkció",
                    "core_idea": f"{k} mag",
                    "grounded_in": [f"arc.{k}"],
                }
                for k in keys
            ],
        }
    }


def test_d_seven_movements_normalize_without_loss():
    keys = [
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    ]
    bp = normalize_blueprint(_structure(keys))
    movements = bp["recommended_structure"]["movements"]
    assert [m["key"] for m in movements] == keys
    assert movements[0]["grounded_in"] == ["arc.entry"]


def test_d_five_movements_normalize_without_loss():
    keys = ["entry", "starting_point", "deepening", "second_shift", "arrival"]
    bp = normalize_blueprint(_structure(keys))
    assert [m["key"] for m in bp["recommended_structure"]["movements"]] == keys


def test_d_three_custom_movements_normalize_without_loss():
    keys = ["custom_1", "custom_2", "custom_3"]
    bp = normalize_blueprint(_structure(keys))
    movements = bp["recommended_structure"]["movements"]
    assert [m["key"] for m in movements] == keys
    assert movements[1]["core_idea"] == "custom_2 mag"


def test_d_partial_movement_is_kept_not_dropped():
    bp = normalize_blueprint(
        {"recommended_structure": {"movements": [{"key": "entry"}, {"core_idea": "csak mag"}]}}
    )
    movements = bp["recommended_structure"]["movements"]
    assert len(movements) == 2
    assert movements[0] == {"key": "entry", "function": "", "core_idea": "", "grounded_in": []}
    assert movements[1]["core_idea"] == "csak mag"
    assert movements[1]["key"] == ""


def test_d_non_dict_movement_entries_are_skipped_others_kept():
    bp = normalize_blueprint(
        {"recommended_structure": {"movements": [{"key": "entry"}, "szemét", None, {"key": "arrival"}]}}
    )
    movements = bp["recommended_structure"]["movements"]
    assert [m["key"] for m in movements] == ["entry", "arrival"]


# =============================================================================
# E. Developed outline normalization
# =============================================================================


def test_e_developed_outline_normalizes_from_garbage_inputs():
    for garbage in (None, "szöveg", 7, [], True):
        assert normalize_developed_outline(garbage) == empty_developed_outline()


def test_e_partial_outline_and_partial_movement_normalize_safely():
    partial = {
        "structure_mode": "merged",
        # `structure_note` hiányzik
        "movements": [
            {"key": "entry", "main_claim": "Csak a fő állítás van meg."},
            "nem dict",
            {"development": ["egy gondolat"]},
        ],
    }
    outline = normalize_developed_outline(partial)

    assert outline["structure_mode"] == "merged"
    assert outline["structure_note"] == ""
    assert len(outline["movements"]) == 2

    first = outline["movements"][0]
    assert first["key"] == "entry"
    assert first["main_claim"] == "Csak a fő állítás van meg."
    assert first["development"] == []
    assert first["title"] == ""

    second = outline["movements"][1]
    assert second["development"] == ["egy gondolat"]
    assert second["key"] == ""


def test_e_movement_list_fields_survive_wrong_types():
    mv = normalize_developed_outline_movement(
        {"key": "entry", "development": "nem lista", "exegetical_support": None}
    )
    assert mv["key"] == "entry"
    assert mv["development"] == []
    assert mv["exegetical_support"] == []


def test_e_developed_outline_normalization_is_idempotent():
    once = normalize_developed_outline(_outline("entry", "deepening", "arrival"))
    assert normalize_developed_outline(once) == once


def test_e_developed_outline_has_content_detects_empty_and_filled():
    assert developed_outline_has_content(empty_developed_outline()) is False
    assert developed_outline_has_content({"movements": [empty_developed_outline_movement()]}) is False
    assert developed_outline_has_content(_outline("entry")) is True
    # A tartalom lehet KIZÁRÓLAG listamezőben is.
    only_list = {"movements": [{"development": ["egy gondolat"]}]}
    assert developed_outline_has_content(only_list) is True


# =============================================================================
# F. Candidate lifecycle — set / accept / discard
# =============================================================================


def test_f_set_candidate_leaves_canonical_outline_untouched():
    state = _base_state()
    state["sermon_workshop"]["developed_outline"] = normalize_developed_outline(
        _outline("entry")
    )
    before = copy.deepcopy(state["sermon_workshop"]["developed_outline"])

    set_developed_outline_candidate(
        state,
        outline=_outline("arrival"),
        reference="Ef 2,4-10",
        context_hash="H1",
    )

    assert state["sermon_workshop"]["developed_outline"] == before
    candidate = state["sermon_workshop"]["developed_outline_candidate"]
    assert candidate["outline"]["movements"][0]["key"] == "arrival"
    assert candidate["reference"] == "Ef 2,4-10"
    assert candidate["generated_at"]  # automatikus időbélyeg


def test_f_first_generation_creates_candidate_only_and_never_applies():
    """RESET 2E-1A, 1-2. követelmény: az ELSŐ generálás sem alkalmazódik
    automatikusan — a kanonikus vázlat üres marad, az eredmény
    candidate-be kerül."""
    state = _base_state()
    assert state["sermon_workshop"]["developed_outline"] == empty_developed_outline()

    result = store_generated_developed_outline_result(
        state, outline=_outline("entry", "arrival"), reference="Ef 2,4-10", context_hash="H1"
    )

    assert result["status"] == "candidate"
    sw = state["sermon_workshop"]
    # 1. A kanonikus vázlat VÁLTOZATLAN/üres marad.
    assert sw["developed_outline"] == empty_developed_outline()
    assert developed_outline_has_content(sw["developed_outline"]) is False
    # A kanonikus meta sem íródik meg — még nincs elfogadott tartalom.
    assert sw["developed_outline_meta"] == empty_developed_outline_meta()
    # 2. Az eredmény a candidate-ben van.
    candidate = sw["developed_outline_candidate"]
    assert candidate is not None
    assert [m["key"] for m in candidate["outline"]["movements"]] == ["entry", "arrival"]
    assert candidate["reference"] == "Ef 2,4-10"
    assert candidate["context_hash"] == "H1"
    assert candidate["generated_at"]


def test_f_generation_never_writes_canonical_outline_on_any_call():
    """A generáló függvény SOHA nem ír a kanonikus mezőbe — sem az első,
    sem a további hívásokon (RESET 2E-1A alapszabály)."""
    state = _base_state()
    for _ in range(3):
        store_generated_developed_outline_result(
            state, outline=_outline("entry"), reference="Ef 2,4-10", context_hash="H1"
        )
        assert state["sermon_workshop"]["developed_outline"] == empty_developed_outline()
        assert state["sermon_workshop"]["developed_outline_meta"] == (
            empty_developed_outline_meta()
        )


def test_f_regenerated_result_is_also_candidate_only():
    """RESET 2E-1A, 5. követelmény: a második/regenerált eredmény is
    kizárólag candidate — az elfogadott kanonikus vázlat érintetlen."""
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    before = copy.deepcopy(state["sermon_workshop"]["developed_outline"])

    result = store_generated_developed_outline_result(
        state, outline=_outline("arrival"), reference="Ef 2,4-10", context_hash="H1"
    )

    assert result["status"] == "candidate"
    assert state["sermon_workshop"]["developed_outline"] == before
    candidate = state["sermon_workshop"]["developed_outline_candidate"]
    assert [m["key"] for m in candidate["outline"]["movements"]] == ["arrival"]


def test_f_generation_never_overwrites_manually_edited_canonical_outline():
    """RESET 2E-1A, 6. követelmény: kézzel szerkesztett kanonikus vázlatot
    a generálás sosem ír felül."""
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    update_developed_outline_movement_field(
        state, index=0, field="main_claim", value="KÉZZEL írt fő állítás."
    )
    before_outline = copy.deepcopy(state["sermon_workshop"]["developed_outline"])
    before_manual = state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"]
    assert before_manual != ""

    store_generated_developed_outline_result(
        state, outline=_outline("arrival"), reference="Ef 2,4-10", context_hash="H1"
    )

    sw = state["sermon_workshop"]
    assert sw["developed_outline"] == before_outline
    assert sw["developed_outline"]["movements"][0]["main_claim"] == "KÉZZEL írt fő állítás."
    # A kézi szerkesztés nyoma is megmarad — a generálás nem hamisítja meg.
    assert sw["developed_outline_meta"]["manually_updated_at"] == before_manual


def test_f_accept_makes_exactly_the_candidate_canonical():
    """RESET 2E-1A, 3. követelmény."""
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    set_developed_outline_candidate(
        state, outline=_outline("arrival"), reference="Ef 2,4-10", context_hash="H1"
    )

    result = accept_developed_outline_candidate(
        state, reference="Ef 2,4-10", context_hash="H1"
    )

    assert result["accepted"] is True
    sw = state["sermon_workshop"]
    assert [m["key"] for m in sw["developed_outline"]["movements"]] == ["arrival"]
    assert sw["developed_outline_candidate"] is None
    assert sw["developed_outline_meta"]["context_hash"] == "H1"
    # Az elfogadott tartalom a candidate-ből származik, nem kézi szerkesztésből.
    assert sw["developed_outline_meta"]["manually_updated_at"] == ""


def test_f_accept_is_the_only_path_that_creates_canonical_outline():
    """A teljes életciklus egy menetben: generálás -> candidate ->
    elfogadás. A kanonikus vázlat KIZÁRÓLAG az elfogadás hatására jön
    létre."""
    state = _base_state()
    store_generated_developed_outline_result(
        state, outline=_outline("entry", "arrival"), reference="Ef 2,4-10", context_hash="H1"
    )
    assert developed_outline_has_content(state["sermon_workshop"]["developed_outline"]) is False

    accept_developed_outline_candidate(state, reference="Ef 2,4-10", context_hash="H1")

    sw = state["sermon_workshop"]
    assert developed_outline_has_content(sw["developed_outline"]) is True
    assert [m["key"] for m in sw["developed_outline"]["movements"]] == ["entry", "arrival"]
    assert sw["developed_outline_meta"]["context_hash"] == "H1"
    assert sw["developed_outline_candidate"] is None


def test_f_discard_keeps_canonical_outline_and_clears_only_candidate():
    """RESET 2E-1A, 4. követelmény."""
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    before_outline = copy.deepcopy(state["sermon_workshop"]["developed_outline"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["developed_outline_meta"])
    set_developed_outline_candidate(
        state, outline=_outline("arrival"), reference="Ef 2,4-10", context_hash="H1"
    )

    discard_developed_outline_candidate(state)

    sw = state["sermon_workshop"]
    assert sw["developed_outline_candidate"] is None
    assert sw["developed_outline"] == before_outline
    assert sw["developed_outline_meta"] == before_meta


def test_f_discard_of_first_generation_leaves_outline_empty():
    """Ha a felhasználó az ELSŐ javaslatot elveti, nem marad utána
    kanonikus tartalom — mert soha nem is jött létre."""
    state = _base_state()
    store_generated_developed_outline_result(
        state, outline=_outline("entry"), reference="Ef 2,4-10", context_hash="H1"
    )

    discard_developed_outline_candidate(state)

    sw = state["sermon_workshop"]
    assert sw["developed_outline_candidate"] is None
    assert sw["developed_outline"] == empty_developed_outline()
    assert sw["developed_outline_meta"] == empty_developed_outline_meta()


def test_f_accept_rejects_mismatched_or_missing_context():
    cases = [
        ({"reference": "Ef 2,4-10", "context_hash": "MÁS"}, "context_hash_mismatch"),
        ({"reference": "MÁS", "context_hash": "H1"}, "reference_mismatch"),
        ({"reference": "", "context_hash": "H1"}, "missing_context_identity"),
        ({"reference": "Ef 2,4-10", "context_hash": ""}, "missing_context_identity"),
    ]
    for kwargs, expected_reason in cases:
        state = _base_state()
        _seed_canonical_outline(state, "entry")
        set_developed_outline_candidate(
            state, outline=_outline("arrival"), reference="Ef 2,4-10", context_hash="H1"
        )
        before = copy.deepcopy(state["sermon_workshop"]["developed_outline"])

        result = accept_developed_outline_candidate(state, **kwargs)

        assert result["accepted"] is False
        assert result["reason"] == expected_reason
        assert state["sermon_workshop"]["developed_outline"] == before
        assert state["sermon_workshop"]["developed_outline_candidate"] is not None


def test_f_accept_without_candidate_reports_no_candidate():
    state = _base_state()
    result = accept_developed_outline_candidate(state, reference="Ef 2,4-10", context_hash="H1")
    assert result == {"accepted": False, "reason": "no_candidate"}


def test_f_structurally_broken_candidate_never_counts_as_valid():
    # Hiányzó `outline` mező -> szerkezetileg nem candidate.
    assert normalize_developed_outline_candidate({"reference": "Ef 2,4-10"}) is None
    assert normalize_developed_outline_candidate(None) is None
    assert normalize_developed_outline_candidate("szemét") is None

    state = _base_state()
    state["sermon_workshop"]["developed_outline_candidate"] = {"reference": "Ef 2,4-10"}
    result = accept_developed_outline_candidate(state, reference="Ef 2,4-10", context_hash="H1")
    # A LÉNYEG a biztonságos elutasítás. A konkrét ok azért lehet kétféle,
    # mert az `ensure_sermon_workshop_state()` a beolvasás ELŐTT `None`-ra
    # normalizálja a sérült candidate-et (ilyenkor `no_candidate`), míg a
    # normalizálást megkerülő úton `invalid_candidate` jön — pontosan
    # ugyanez a helyzet az `accept_arc_candidate`-nél is (ld.
    # `tests/test_arc_data_model.py` azonos elfogadó asszertálását).
    assert result["accepted"] is False
    assert result["reason"] in ("no_candidate", "invalid_candidate")
    assert state["sermon_workshop"]["developed_outline"] == empty_developed_outline()


# =============================================================================
# G. Manual update
# =============================================================================


def test_g_manual_update_changes_only_the_targeted_field():
    state = _base_state()
    _seed_canonical_outline(state, "entry", "arrival")
    before = copy.deepcopy(state["sermon_workshop"]["developed_outline"])

    result = update_developed_outline_movement_field(
        state, index=0, field="main_claim", value="Kézzel átírt fő állítás."
    )

    assert result["updated"] is True
    movements = state["sermon_workshop"]["developed_outline"]["movements"]
    assert movements[0]["main_claim"] == "Kézzel átírt fő állítás."
    # Ugyanannak a mozgásnak a többi mezője változatlan.
    assert movements[0]["title"] == before["movements"][0]["title"]
    assert movements[0]["development"] == before["movements"][0]["development"]
    # A MÁSIK mozgás bit-pontosan változatlan.
    assert movements[1] == before["movements"][1]
    # A szerkezeti metaadat változatlan.
    assert state["sermon_workshop"]["developed_outline"]["structure_mode"] == (
        before["structure_mode"]
    )


def test_g_manual_update_refreshes_manual_timestamp():
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    assert state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"] == ""

    update_developed_outline_movement_field(
        state, index=0, field="title", value="Új cím."
    )

    meta = state["sermon_workshop"]["developed_outline_meta"]
    assert meta["manually_updated_at"] != ""
    # Az eredet-metaadat NEM íródik át kézi szerkesztéskor.
    assert meta["context_hash"] == "H1"
    assert meta["reference"] == "Ef 2,4-10"


def test_g_manual_update_supports_list_fields():
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    result = update_developed_outline_movement_field(
        state, index=0, field="development", value=["Első gondolat.", "Második gondolat."]
    )
    assert result["updated"] is True
    assert state["sermon_workshop"]["developed_outline"]["movements"][0]["development"] == [
        "Első gondolat.",
        "Második gondolat.",
    ]


def test_g_manual_update_rejects_out_of_range_index_safely():
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    before = copy.deepcopy(state["sermon_workshop"]["developed_outline"])

    for bad_index in (1, 99, -1, "0", None):
        result = update_developed_outline_movement_field(
            state, index=bad_index, field="title", value="Nem szabad kiírni."
        )
        assert result["updated"] is False
        assert result["reason"] == "index_out_of_range"

    assert state["sermon_workshop"]["developed_outline"] == before
    # Sikertelen kísérlet NEM hamisítja meg a kézi időbélyeget.
    assert state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"] == ""


def test_g_manual_update_raises_on_unknown_field():
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    try:
        update_developed_outline_movement_field(
            state, index=0, field="nincs_ilyen_mezo", value="x"
        )
    except ValueError as exc:
        assert "nincs_ilyen_mezo" in str(exc)
    else:  # pragma: no cover - a teszt lényege, hogy ide ne jussunk
        raise AssertionError("ValueError-t vártunk ismeretlen mezőnévre.")


def test_g_manual_update_does_not_touch_candidate():
    state = _base_state()
    _seed_canonical_outline(state, "entry")
    set_developed_outline_candidate(
        state, outline=_outline("arrival"), reference="Ef 2,4-10", context_hash="H1"
    )
    before_candidate = copy.deepcopy(state["sermon_workshop"]["developed_outline_candidate"])

    update_developed_outline_movement_field(
        state, index=0, field="title", value="Kézi cím."
    )

    assert state["sermon_workshop"]["developed_outline_candidate"] == before_candidate


# =============================================================================
# H. Legacy isolation — a régi `sermon_outline` és az új
#    `developed_outline` SOSEM keveredik, egyik irányban sem.
# =============================================================================


def test_h_legacy_sermon_outline_is_not_migrated_into_developed_outline():
    legacy = {
        "sermon_outline": {
            "content": "Régi, legacy vázlatszöveg — NEM migrálandó.",
            "status": "approved",
        }
    }
    sw = normalize_sermon_workshop(legacy)

    assert sw["sermon_outline"]["content"] == "Régi, legacy vázlatszöveg — NEM migrálandó."
    # Az új vázlat ettől függetlenül ÜRES marad.
    assert sw["developed_outline"] == empty_developed_outline()
    assert developed_outline_has_content(sw["developed_outline"]) is False


def test_h_developed_outline_does_not_leak_into_legacy_sermon_outline():
    state = _base_state()
    _seed_canonical_outline(state, "entry", "arrival")
    sw = state["sermon_workshop"]

    assert developed_outline_has_content(sw["developed_outline"]) is True
    # A legacy mező bit-pontosan az üres alapértéken marad.
    assert sw["sermon_outline"] == empty_sermon_outline()


def test_h_both_systems_can_hold_content_side_by_side_independently():
    state = _base_state()
    state["sermon_workshop"]["sermon_outline"]["content"] = "Régi rendszer tartalma."
    _seed_canonical_outline(state, "entry")

    sw = normalize_sermon_workshop(state["sermon_workshop"])
    assert sw["sermon_outline"]["content"] == "Régi rendszer tartalma."
    assert sw["developed_outline"]["movements"][0]["key"] == "entry"


def test_h_accepting_developed_candidate_never_writes_legacy_outline():
    state = _base_state()
    state["sermon_workshop"]["sermon_outline"]["content"] = "Régi tartalom."
    _seed_canonical_outline(state, "entry")
    set_developed_outline_candidate(
        state, outline=_outline("arrival"), reference="Ef 2,4-10", context_hash="H1"
    )

    accept_developed_outline_candidate(state, reference="Ef 2,4-10", context_hash="H1")

    assert state["sermon_workshop"]["sermon_outline"]["content"] == "Régi tartalom."


# =============================================================================
# Kereszt-izoláció: az új mezők nem érintik az `arc` rendszert.
# =============================================================================


def test_new_structures_do_not_disturb_arc_system():
    state = _base_state()
    state["sermon_workshop"]["arc"]["entry"]["text"] = "Arc belépés."
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_arc_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    _seed_canonical_outline(state, "entry")
    update_developed_outline_movement_field(state, index=0, field="title", value="Cím.")

    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_arc_meta
    assert state["sermon_workshop"]["arc_candidate"] is None
