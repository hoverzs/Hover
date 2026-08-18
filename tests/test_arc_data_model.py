"""Az egységesített "Az igehirdetés íve" (`arc`) adatmodell tesztjei.

Célarchitektúra-terv (TEXTUS_EGYSZERUSITETT_IGEHIRDETESI_CELARCHITEKTURA_
TERV_2026-08-13.md), 1. fázis. FONTOS: ez a modul ebben a fázisban NEM aktív
source of truth — a tesztek kizárólag az adatmodellt (séma, normalizálás,
nem destruktív migráció, `update_arc_point`) vizsgálják, UI-t és
vázlatmotort nem.
"""

from __future__ import annotations

import copy

from sermon_workshop_data import (
    _ARC_POINT_KEYS,
    accept_arc_candidate,
    arc_has_content,
    discard_arc_candidate,
    empty_arc_meta,
    empty_arc_point,
    ensure_sermon_workshop_state,
    get_default_arc,
    get_default_sermon_workshop,
    migrate_legacy_arc_fields,
    normalize_arc,
    normalize_arc_candidate,
    normalize_arc_meta,
    normalize_sermon_workshop,
    set_arc_candidate,
    store_generated_arc_result,
    update_arc_point,
)
from textus_workshop_data import (
    TEXT_WORKSHOP_KEY,
    ensure_text_workshop_state,
    get_default_text_workshop,
    update_text_main_idea,
)
from workspace_data import build_project_data


# ---------------------------------------------------------------------------
# 1-2. Séma
# ---------------------------------------------------------------------------


def test_default_arc_has_exactly_seven_points():
    arc = get_default_arc()
    assert set(arc.keys()) == {
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    }
    assert len(arc) == 7
    assert tuple(_ARC_POINT_KEYS) == (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )


def test_every_point_has_identical_normalized_schema():
    arc = get_default_arc()
    expected_keys = {"text", "ai_suggestion", "ai_suggested_at", "context_hash", "updated_at"}
    for point_key, point in arc.items():
        assert set(point.keys()) == expected_keys, point_key
        assert point["text"] == ""
        assert point["ai_suggestion"] is None
        assert point["ai_suggested_at"] == ""
        assert point["context_hash"] == ""
        assert point["updated_at"] == ""


def test_empty_arc_point_matches_default_point_schema():
    assert empty_arc_point() == get_default_arc()["entry"]


# ---------------------------------------------------------------------------
# 3. Hiányos / régi projekt normalizálása adatvesztés nélkül
# ---------------------------------------------------------------------------


def test_normalize_sermon_workshop_without_arc_key_gets_safe_default():
    """Régi projekt (nincs `arc` kulcs) normalizálásakor biztonságos
    alapérték jön létre, és a régi mezők VÁLTOZATLANUL megmaradnak."""
    old_style = get_default_sermon_workshop()
    del old_style["arc"]
    old_style["sermon_main_idea"] = "Régi fókuszmondat."
    old_style["entry_point"] = {"today_connection": "Régi belépés", "type": "", "text": ""}

    normalized = normalize_sermon_workshop(old_style)

    assert normalized["arc"] == get_default_arc()
    # Adatvesztés nélkül: a régi mezők érintetlenek.
    assert normalized["sermon_main_idea"] == "Régi fókuszmondat."
    assert normalized["entry_point"]["today_connection"] == "Régi belépés"


def test_normalize_arc_with_garbage_input_returns_default():
    assert normalize_arc(None) == get_default_arc()
    assert normalize_arc("not a dict") == get_default_arc()
    assert normalize_arc(42) == get_default_arc()
    assert normalize_arc({}) == get_default_arc()


def test_normalize_arc_drops_unknown_point_keys_without_crashing():
    raw = {"entry": {"text": "Belépés szövege"}, "unknown_point": {"text": "elveszik"}}
    normalized = normalize_arc(raw)
    assert set(normalized.keys()) == set(_ARC_POINT_KEYS)
    assert normalized["entry"]["text"] == "Belépés szövege"


# ---------------------------------------------------------------------------
# 4. Elsődleges régi mezők helyes migrációja
# ---------------------------------------------------------------------------


def _sw_with_legacy_content() -> dict:
    sw = get_default_sermon_workshop()
    sw["entry_point"] = {
        "today_connection": "Ma is küzdünk a kételyekkel.",
        "type": "kérdés",
        "text": "Mikor kételkedtél utoljára?",
    }
    sw["sermon_path"] = {
        "type": "",
        "reason": "",
        "starting_point": "A hallgatók bizonytalanok a hitükben.",
        "first_shift": "A szöveg megmutatja: Isten hűsége nem a mi hitünk erősségén múlik.",
        "deepening": "Ez mélyebb bizalmat kínál, nem felszínes megnyugvást.",
        "reinterpretation": "Amit gyengeségnek hittünk, az lehet a bizalom kezdete.",
        "destination": "",
    }
    sw["christ_centered_arc"] = {
        "divine_gracious_action": "Isten kegyelemből tartja meg népét.",
        "christ_connection": "Krisztusban lett nyilvánvalóvá ez a hűség.",
        "christ_connection_type": "explicit",
        "grace_enabled_response": "Ez szabadítja fel a hálás engedelmességet.",
    }
    sw["closing"] = {
        "type": "",
        "final_discovery": "Isten hűsége nem érdemünkön múlik.",
        "hope": "Ez a remény hordozza a holnapot is.",
        "call_or_response": "Bízd rá magad újra.",
        "image_or_line": "A horgony, ami a viharban is tart.",
        "open_question": "Mit jelentene ma erre a hűségre támaszkodni?",
        "tone": "",
    }
    return sw


def test_primary_legacy_fields_migrate_to_correct_arc_points():
    sw = _sw_with_legacy_content()
    result = migrate_legacy_arc_fields(sw)
    arc = result["arc"]

    assert "Ma is küzdünk a kételyekkel." in arc["entry"]["text"]
    assert "Mikor kételkedtél utoljára?" in arc["entry"]["text"]

    assert arc["starting_point"]["text"] == "A hallgatók bizonytalanok a hitükben."
    assert arc["first_shift"]["text"].startswith("A szöveg megmutatja")
    assert arc["deepening"]["text"].startswith("Ez mélyebb bizalmat")
    assert arc["reinterpretation"]["text"].startswith("Amit gyengeségnek")

    assert "Isten kegyelemből tartja meg népét." in arc["second_shift"]["text"]
    assert "Krisztusban lett nyilvánvalóvá" in arc["second_shift"]["text"]
    assert "szabadítja fel" in arc["second_shift"]["text"]

    assert "Isten hűsége nem érdemünkön múlik." in arc["arrival"]["text"]
    assert "horgony" in arc["arrival"]["text"]
    assert "Mit jelentene ma" in arc["arrival"]["text"]


# ---------------------------------------------------------------------------
# 5. Másodlagos (human_condition / listener_tension) csak üres célpontot tölt
# ---------------------------------------------------------------------------


def test_secondary_legacy_fields_only_fill_empty_targets():
    sw = get_default_sermon_workshop()
    # Elsődleges (sermon_path.starting_point) ÜRES marad.
    sw["human_condition"] = {
        "condition": "A hallgatók elfáradtak a várakozásban.",
        "false_response": "",
        "human_need": "",
        "divine_action": "",
        "grace_response": "",
    }
    sw["listener_tension"] = {
        "listener_question": "Meddig kell még várni?",
        "listener_resistance": "",
        "sermon_tension": "",
        "promised_resolution": "",
    }

    result = migrate_legacy_arc_fields(sw)
    arc = result["arc"]
    assert "elfáradtak a várakozásban" in arc["starting_point"]["text"]
    assert "Meddig kell még várni?" in arc["first_shift"]["text"]


def test_secondary_legacy_fields_do_not_fill_when_primary_already_present():
    sw = get_default_sermon_workshop()
    sw["sermon_path"] = dict(sw["sermon_path"])
    sw["sermon_path"]["starting_point"] = "Elsődleges forrás szövege."
    sw["human_condition"] = {
        "condition": "Ezt a másodlagos szöveget NEM szabad felhasználni.",
        "false_response": "",
        "human_need": "",
        "divine_action": "",
        "grace_response": "",
    }

    result = migrate_legacy_arc_fields(sw)
    assert result["arc"]["starting_point"]["text"] == "Elsődleges forrás szövege."
    assert "NEM szabad" not in result["arc"]["starting_point"]["text"]


# ---------------------------------------------------------------------------
# 6. Nem üres arc mezőt semmilyen migráció nem ír felül
# ---------------------------------------------------------------------------


def test_migration_never_overwrites_nonempty_arc_text():
    sw = _sw_with_legacy_content()
    existing_arc = get_default_arc()
    existing_arc = copy.deepcopy(existing_arc)
    existing_arc["starting_point"]["text"] = "Felhasználó saját, kézzel írt szövege."

    result = migrate_legacy_arc_fields(sw, existing_arc=existing_arc)

    assert result["arc"]["starting_point"]["text"] == "Felhasználó saját, kézzel írt szövege."
    # A többi, korábban üres pont viszont migrálódik.
    assert result["arc"]["entry"]["text"] != ""


def test_migration_does_not_mutate_input_sermon_workshop():
    sw = _sw_with_legacy_content()
    before = copy.deepcopy(sw)
    migrate_legacy_arc_fields(sw)
    assert sw == before


# ---------------------------------------------------------------------------
# 7. Idempotencia
# ---------------------------------------------------------------------------


def test_migration_is_idempotent():
    sw = _sw_with_legacy_content()

    first = migrate_legacy_arc_fields(sw)
    second = migrate_legacy_arc_fields(sw, existing_arc=first["arc"])

    assert second["arc"] == first["arc"]

    third = migrate_legacy_arc_fields(sw, existing_arc=second["arc"])
    assert third["arc"] == first["arc"]


# ---------------------------------------------------------------------------
# 8-9. Engagement -> Vázlatkosár migráció
# ---------------------------------------------------------------------------


def _sw_with_engagement(*, approved_text: str, draft_text: str) -> dict:
    sw = get_default_sermon_workshop()
    sw["engagement_elements"] = [
        {
            "id": "e1",
            "type": "kérdés",
            "text": approved_text,
            "status": "approved",
            "source": "own",
            "created_at": "",
        },
        {
            "id": "e2",
            "type": "történet",
            "text": draft_text,
            "status": "draft",
            "source": "ai",
            "created_at": "",
        },
    ]
    return sw


def test_approved_engagement_element_reaches_basket_once():
    sw = _sw_with_engagement(
        approved_text="Jóváhagyott megszólító elem.",
        draft_text="Draft elem — nem kellene bekerülnie.",
    )

    first = migrate_legacy_arc_fields(sw)
    assert first["basket_items"] == [("Megszólítás (migrált)", "Jóváhagyott megszólító elem.")]

    # Ha a kosár már tartalmazza (mert az első futás eredményét már betették),
    # a második futás nem ad vissza duplikátumot.
    existing_basket = [("Megszólítás (migrált)", "Jóváhagyott megszólító elem.")]
    second = migrate_legacy_arc_fields(sw, existing_basket=existing_basket)
    assert second["basket_items"] == []


def test_draft_engagement_element_never_reaches_basket():
    sw = _sw_with_engagement(
        approved_text="Jóváhagyott.",
        draft_text="Draft — soha nem kerülhet a kosárba.",
    )
    result = migrate_legacy_arc_fields(sw)
    texts = [text for _source, text in result["basket_items"]]
    assert "Draft — soha nem kerülhet a kosárba." not in texts


# ---------------------------------------------------------------------------
# 10-11. update_arc_point()
# ---------------------------------------------------------------------------


def test_update_arc_point_only_modifies_target_point():
    state: dict = {}
    ensure_sermon_workshop_state(state)

    update_arc_point(state, "first_shift", "Első fordulópont szövege.")

    arc = state["sermon_workshop"]["arc"]
    assert arc["first_shift"]["text"] == "Első fordulópont szövege."
    for key in _ARC_POINT_KEYS:
        if key == "first_shift":
            continue
        assert arc[key] == empty_arc_point(), key


def test_update_arc_point_rejects_unknown_point_key():
    state: dict = {}
    try:
        update_arc_point(state, "not_a_real_point", "x")
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError-t kellett volna dobnia")


def test_update_arc_point_stamps_updated_at_and_context_hash_for_nonempty_text():
    state: dict = {"last_igehely": "Jn 3,16", "passage_text": "Mert úgy szerette Isten..."}
    ensure_sermon_workshop_state(state)

    point = update_arc_point(state, "arrival", "Megérkezés szövege.")

    assert point["updated_at"] != ""
    # A hash-számítás lusta importtal történik; hiba esetén is csak üres
    # marad, sosem dob kivételt — itt érvényes passage-kontextussal fut.
    assert isinstance(point["context_hash"], str)


def test_update_arc_point_does_not_erase_existing_ai_suggestion():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    state["sermon_workshop"]["arc"]["deepening"]["ai_suggestion"] = "Korábbi MI-javaslat."
    state["sermon_workshop"]["arc"]["deepening"]["ai_suggested_at"] = "2026-08-13T10:00:00"

    update_arc_point(state, "deepening", "Felhasználó saját szövege.")

    point = state["sermon_workshop"]["arc"]["deepening"]
    assert point["text"] == "Felhasználó saját szövege."
    assert point["ai_suggestion"] == "Korábbi MI-javaslat."
    assert point["ai_suggested_at"] == "2026-08-13T10:00:00"


def test_update_arc_point_does_not_touch_legacy_fields():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    state["sermon_workshop"]["entry_point"] = {
        "today_connection": "Régi mező, érintetlen kell maradjon.",
        "type": "",
        "text": "",
    }

    update_arc_point(state, "entry", "Új arc.entry szöveg.")

    assert (
        state["sermon_workshop"]["entry_point"]["today_connection"]
        == "Régi mező, érintetlen kell maradjon."
    )


# ---------------------------------------------------------------------------
# 12. RESET 2A: `arc_candidate` — teljes, metaadattal ellátott szerkezet
#     (`points`/`reference`/`context_hash`/`generated_at`), NEM puszta
#     hétpontos dict. Adatmodell-szint, még nincs UI/motor.
# ---------------------------------------------------------------------------


def _full_candidate_payload(point_key: str, text: str, **meta) -> dict:
    payload = {
        "points": {point_key: {"text": text}},
        "reference": meta.get("reference", "Jn 3,16"),
        "context_hash": meta.get("context_hash", "HASH-1"),
        "generated_at": meta.get("generated_at", "2026-08-18T10:00:00"),
    }
    return payload


def test_arc_candidate_defaults_to_none():
    sw = get_default_sermon_workshop()
    assert sw["arc_candidate"] is None


def test_normalize_arc_candidate_shapes_valid_full_candidate():
    candidate = normalize_arc_candidate(
        _full_candidate_payload("entry", "Javasolt belépés.")
    )
    assert set(candidate.keys()) == {"points", "reference", "context_hash", "generated_at"}
    assert set(candidate["points"].keys()) == set(_ARC_POINT_KEYS)
    assert candidate["points"]["entry"]["text"] == "Javasolt belépés."
    assert candidate["points"]["arrival"]["text"] == ""
    assert candidate["reference"] == "Jn 3,16"
    assert candidate["context_hash"] == "HASH-1"
    assert candidate["generated_at"] == "2026-08-18T10:00:00"


def test_normalize_arc_candidate_missing_metadata_defaults_to_empty_string():
    """Hiányos (de szerkezetileg ép — van `points`) bemenet nem sérült,
    csak a hiányzó metaadat lesz üres string."""
    candidate = normalize_arc_candidate({"points": {"arrival": {"text": "Megérkezés."}}})
    assert candidate is not None
    assert candidate["reference"] == ""
    assert candidate["context_hash"] == ""
    assert candidate["generated_at"] == ""
    assert candidate["points"]["arrival"]["text"] == "Megérkezés."


def test_normalize_arc_candidate_garbage_or_missing_returns_none():
    assert normalize_arc_candidate("nem dict") is None
    assert normalize_arc_candidate(None) is None
    assert normalize_arc_candidate(42) is None


def test_normalize_arc_candidate_without_points_key_is_corrupted_returns_none():
    """Hiányzó vagy rossz típusú `points` kulcs — szerkezetileg NEM
    candidate, függetlenül attól, hogy a metaadat mezők érvényesek."""
    assert normalize_arc_candidate({"reference": "Jn 3,16", "context_hash": "H"}) is None
    assert normalize_arc_candidate({"points": "nem dict", "reference": "x"}) is None
    assert normalize_arc_candidate({"points": ["nem", "dict"]}) is None


def test_normalize_arc_candidate_is_idempotent():
    once = normalize_arc_candidate(_full_candidate_payload("entry", "Szöveg."))
    twice = normalize_arc_candidate(once)
    assert once == twice


def test_arc_candidate_survives_normalize_and_ensure_state_round_trip():
    state = {
        "sermon_workshop": {
            "arc_candidate": _full_candidate_payload(
                "deepening", "Mélyítés-javaslat SENTINEL."
            )
        }
    }
    sw = ensure_sermon_workshop_state(state)
    assert sw["arc_candidate"]["points"]["deepening"]["text"] == "Mélyítés-javaslat SENTINEL."
    assert sw["arc_candidate"]["reference"] == "Jn 3,16"

    # Második normalizálási kör (pl. következő rerun) sem veszíti el.
    sw2 = normalize_sermon_workshop(sw)
    assert sw2["arc_candidate"]["points"]["deepening"]["text"] == "Mélyítés-javaslat SENTINEL."


def test_arc_candidate_is_sibling_of_arc_not_nested_inside_it():
    sw = get_default_sermon_workshop()
    assert "arc_candidate" not in sw["arc"]
    assert "arc" not in (sw["arc_candidate"] or {})
    assert "arc_meta" not in sw["arc"]
    assert "arc_meta" not in (sw["arc_candidate"] or {})


# ---------------------------------------------------------------------------
# 13. RESET 2A: bizonyíték, hogy a `text_main_idea` (Textusműhely) és a
#     `sermon_main_idea` (Igehirdetési műhely — "fókuszmondat") teljesen
#     változatlan marad az `arc`/`arc_candidate` bővítése és normalizálása
#     során. Ezek NEM arc-pontok, hanem a hét pontot összetartó központi
#     irányok — ebben a fázisban a UI-juk/MI-funkciójuk nem módosul.
# ---------------------------------------------------------------------------

SERMON_MAIN_IDEA_SENTINEL = "SERMON_MAIN_IDEA_RESET2A_SENTINEL"
TEXT_MAIN_IDEA_SENTINEL = "TEXT_MAIN_IDEA_RESET2A_SENTINEL"


def test_sermon_main_idea_default_and_normalize_unaffected_by_arc_fields():
    sw = get_default_sermon_workshop()
    assert sw["sermon_main_idea"] == ""
    assert sw["sermon_main_idea_status"] == "draft"
    assert "sermon_main_idea" not in sw["arc"]
    assert "sermon_main_idea" not in (sw["arc_candidate"] or {})


def test_sermon_main_idea_survives_arc_and_arc_candidate_population():
    """A `sermon_main_idea` normalizálása teljesen független attól, hogy az
    `arc`/`arc_candidate` üres vagy kitöltött — a két mező nem hat egymásra
    egyik irányban sem."""
    raw = {
        "sermon_main_idea": SERMON_MAIN_IDEA_SENTINEL,
        "sermon_main_idea_status": "approved",
        "arc": {"entry": {"text": "Egy arc-pont szövege."}},
        "arc_candidate": _full_candidate_payload("arrival", "Egy candidate-pont szövege."),
    }
    normalized = normalize_sermon_workshop(raw)
    assert normalized["sermon_main_idea"] == SERMON_MAIN_IDEA_SENTINEL
    assert normalized["sermon_main_idea_status"] == "approved"
    # ... és fordítva: a sermon_main_idea kitöltése nem szivárog az arc-ba.
    assert normalized["arc"]["entry"]["text"] == "Egy arc-pont szövege."
    assert (
        normalized["arc_candidate"]["points"]["arrival"]["text"]
        == "Egy candidate-pont szövege."
    )
    for key in _ARC_POINT_KEYS:
        if key == "entry":
            continue
        assert normalized["arc"][key]["text"] == ""


def test_update_arc_point_does_not_touch_sermon_main_idea():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    state["sermon_workshop"]["sermon_main_idea"] = SERMON_MAIN_IDEA_SENTINEL
    state["sermon_workshop"]["sermon_main_idea_status"] = "approved"

    update_arc_point(state, "reinterpretation", "Átértelmezés szövege.")

    sw = state["sermon_workshop"]
    assert sw["sermon_main_idea"] == SERMON_MAIN_IDEA_SENTINEL
    assert sw["sermon_main_idea_status"] == "approved"


def test_text_main_idea_lives_in_separate_module_and_state_key_from_arc():
    """A `text_main_idea` (Textusműhely, exegetikai állítás) fogalmilag és
    adatszerkezetileg is teljesen elkülönül a `sermon_workshop.arc`-tól —
    más top-level session-kulcs (`text_workshop` vs. `sermon_workshop`),
    más modul (`textus_workshop_data.py` vs. `sermon_workshop_data.py`)."""
    state: dict = {}
    update_text_main_idea(state, TEXT_MAIN_IDEA_SENTINEL, "draft")
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "starting_point", "Alaphelyzet szövege.")

    tw = state[TEXT_WORKSHOP_KEY]
    sw = state["sermon_workshop"]
    assert tw["text_main_idea"] == TEXT_MAIN_IDEA_SENTINEL
    assert sw["arc"]["starting_point"]["text"] == "Alaphelyzet szövege."
    # Nincs kereszteződés: a text_main_idea nem jelenik meg az arc-ban, és
    # fordítva, az arc pontjai nem szivárognak a text_workshop-ba.
    assert "text_main_idea" not in sw["arc"]["starting_point"]
    assert "arc" not in tw


def test_full_project_round_trip_preserves_both_main_idea_fields_and_arc_candidate():
    """Teljes `build_project_data()` mentési kör — mind a két "központi
    irány" mező, mind az új `arc_candidate` sértetlenül túléli, egymástól
    függetlenül."""
    state: dict = {
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        "sermon_workshop": get_default_sermon_workshop(),
    }
    update_text_main_idea(state, TEXT_MAIN_IDEA_SENTINEL, "approved")
    state["sermon_workshop"]["sermon_main_idea"] = SERMON_MAIN_IDEA_SENTINEL
    state["sermon_workshop"]["sermon_main_idea_status"] = "approved"
    state["sermon_workshop"]["arc_candidate"] = _full_candidate_payload(
        "second_shift", "Második fordulópont-javaslat SENTINEL."
    )

    project = build_project_data(state)

    assert project[TEXT_WORKSHOP_KEY]["text_main_idea"] == TEXT_MAIN_IDEA_SENTINEL
    assert project["sermon_workshop"]["sermon_main_idea"] == SERMON_MAIN_IDEA_SENTINEL
    assert project["sermon_workshop"]["sermon_main_idea_status"] == "approved"
    assert (
        project["sermon_workshop"]["arc_candidate"]["points"]["second_shift"]["text"]
        == "Második fordulópont-javaslat SENTINEL."
    )

    reloaded = dict(project)
    ensure_text_workshop_state(reloaded)
    ensure_sermon_workshop_state(reloaded)
    assert reloaded[TEXT_WORKSHOP_KEY]["text_main_idea"] == TEXT_MAIN_IDEA_SENTINEL
    assert reloaded["sermon_workshop"]["sermon_main_idea"] == SERMON_MAIN_IDEA_SENTINEL
    assert (
        reloaded["sermon_workshop"]["arc_candidate"]["points"]["second_shift"]["text"]
        == "Második fordulópont-javaslat SENTINEL."
    )


# ---------------------------------------------------------------------------
# 14. RESET 2A (folytatás): `arc_meta` — a kanonikus `arc`-ra EGYÜTTESEN
#     vonatkozó frissesség-/eredet-metaadat (NEM egy pont belseje).
# ---------------------------------------------------------------------------


def test_arc_meta_default_is_all_empty_strings():
    meta = empty_arc_meta()
    assert meta == {
        "reference": "",
        "context_hash": "",
        "generated_at": "",
        "manually_updated_at": "",
    }


def test_get_default_sermon_workshop_includes_empty_arc_meta():
    sw = get_default_sermon_workshop()
    assert sw["arc_meta"] == empty_arc_meta()


def test_normalize_sermon_workshop_without_arc_meta_key_gets_safe_default():
    """Régi projektben nincs `arc_meta` mező — a hiánya nem hibázik."""
    normalized = normalize_sermon_workshop({"sermon_main_idea": "x"})
    assert normalized["arc_meta"] == empty_arc_meta()


def test_normalize_arc_meta_shapes_valid_input():
    meta = normalize_arc_meta(
        {
            "reference": "Jn 3,16",
            "context_hash": "HASH-1",
            "generated_at": "2026-08-18T10:00:00",
            "manually_updated_at": "2026-08-18T11:00:00",
        }
    )
    assert meta == {
        "reference": "Jn 3,16",
        "context_hash": "HASH-1",
        "generated_at": "2026-08-18T10:00:00",
        "manually_updated_at": "2026-08-18T11:00:00",
    }


def test_normalize_arc_meta_is_idempotent():
    once = normalize_arc_meta({"reference": "Jn 3,16", "context_hash": "H"})
    twice = normalize_arc_meta(once)
    assert once == twice == normalize_arc_meta(twice)


def test_normalize_arc_meta_corrupted_or_partial_input_handled_safely():
    """Hibás típus (nem dict) -> biztonságos alapérték; részleges dict ->
    a hiányzó mezők üres stringre esnek, nincs kivétel."""
    assert normalize_arc_meta("nem dict") == empty_arc_meta()
    assert normalize_arc_meta(None) == empty_arc_meta()
    assert normalize_arc_meta(["lista"]) == empty_arc_meta()
    partial = normalize_arc_meta({"reference": "Jn 3,16"})
    assert partial["reference"] == "Jn 3,16"
    assert partial["context_hash"] == ""
    assert partial["generated_at"] == ""
    assert partial["manually_updated_at"] == ""
    # Ismeretlen extra kulcsok nem szivárognak be.
    extra = normalize_arc_meta({"reference": "x", "unknown_field": "y"})
    assert "unknown_field" not in extra


def test_arc_meta_not_placed_inside_any_arc_point_context_hash():
    """Explicit tiltás: az `arc_meta` mezői NEM kerülhetnek bele egyik
    arc-pont `context_hash` mezőjébe sem."""
    sw = get_default_sermon_workshop()
    for point in sw["arc"].values():
        assert point["context_hash"] == ""
    assert "arc_meta" not in sw["arc"]


# ---------------------------------------------------------------------------
# 15. RESET 2A: `store_generated_arc_result()` — első generálás vs.
#     újragenerálás döntési szabálya.
# ---------------------------------------------------------------------------

GENERATED_POINTS = {
    "entry": {"text": "Belépés SENTINEL."},
    "starting_point": {"text": "Alaphelyzet SENTINEL."},
    "first_shift": {"text": "Első fordulópont SENTINEL."},
    "deepening": {"text": "Mélyítés SENTINEL."},
    "reinterpretation": {"text": "Átértelmezés SENTINEL."},
    "second_shift": {"text": "Második fordulópont SENTINEL."},
    "arrival": {"text": "Megérkezés SENTINEL."},
}


def test_store_generated_arc_result_applies_directly_when_arc_is_empty():
    state: dict = {}
    ensure_sermon_workshop_state(state)

    result = store_generated_arc_result(
        state,
        points=GENERATED_POINTS,
        reference="Jn 3,16",
        context_hash="HASH-A",
        generated_at="2026-08-18T10:00:00",
    )

    assert result["status"] == "applied"
    sw = state["sermon_workshop"]
    assert sw["arc"]["entry"]["text"] == "Belépés SENTINEL."
    assert sw["arc"]["arrival"]["text"] == "Megérkezés SENTINEL."
    assert sw["arc_meta"]["reference"] == "Jn 3,16"
    assert sw["arc_meta"]["context_hash"] == "HASH-A"
    assert sw["arc_meta"]["generated_at"] == "2026-08-18T10:00:00"
    assert sw["arc_candidate"] is None


def test_store_generated_arc_result_becomes_candidate_when_arc_has_content():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "entry", "Kézzel írt belépés — MEGŐRZENDŐ.")

    result = store_generated_arc_result(
        state,
        points=GENERATED_POINTS,
        reference="Jn 3,16",
        context_hash="HASH-B",
        generated_at="2026-08-18T12:00:00",
    )

    assert result["status"] == "candidate"
    sw = state["sermon_workshop"]
    # A kanonikus arc EGYETLEN pontja sem változott.
    assert sw["arc"]["entry"]["text"] == "Kézzel írt belépés — MEGŐRZENDŐ."
    for key in _ARC_POINT_KEYS:
        if key == "entry":
            continue
        assert sw["arc"][key]["text"] == "", key
    # A candidate-ág nem érinti az arc_meta generálási mezőit — csak a
    # korábbi `update_arc_point()` hívás állította be a
    # `manually_updated_at`-ot, a reference/context_hash/generated_at
    # változatlanul üres marad (nem "applied" ág).
    assert sw["arc_meta"]["reference"] == ""
    assert sw["arc_meta"]["context_hash"] == ""
    assert sw["arc_meta"]["generated_at"] == ""
    # A candidate tartalmazza a teljes eredményt + metaadatot.
    candidate = sw["arc_candidate"]
    assert candidate["points"]["arrival"]["text"] == "Megérkezés SENTINEL."
    assert candidate["reference"] == "Jn 3,16"
    assert candidate["context_hash"] == "HASH-B"
    assert candidate["generated_at"] == "2026-08-18T12:00:00"


def test_arc_has_content_true_for_any_single_nonempty_point():
    empty = get_default_arc()
    assert arc_has_content(empty) is False
    one_filled = get_default_arc()
    one_filled["deepening"]["text"] = "Csak ez a pont van kitöltve."
    assert arc_has_content(one_filled) is True


def test_arc_has_content_handles_garbage_input_safely():
    assert arc_has_content(None) is False
    assert arc_has_content("nem dict") is False
    assert arc_has_content({}) is False


# ---------------------------------------------------------------------------
# 16. RESET 2A: `accept_arc_candidate()` — kontextusvédelem.
# ---------------------------------------------------------------------------


def _state_with_candidate(*, reference="Jn 3,16", context_hash="HASH-B") -> dict:
    state: dict = {}
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "entry", "Kézzel írt belépés — MEGŐRZENDŐ.")
    store_generated_arc_result(
        state,
        points=GENERATED_POINTS,
        reference=reference,
        context_hash=context_hash,
        generated_at="2026-08-18T12:00:00",
    )
    return state


def test_accept_arc_candidate_succeeds_on_matching_reference_and_context_hash():
    state = _state_with_candidate()

    result = accept_arc_candidate(state, reference="Jn 3,16", context_hash="HASH-B")

    assert result["accepted"] is True
    assert result["reason"] == ""
    sw = state["sermon_workshop"]
    assert sw["arc"]["arrival"]["text"] == "Megérkezés SENTINEL."
    assert sw["arc"]["entry"]["text"] == "Belépés SENTINEL."  # a candidate felülírta
    assert sw["arc_meta"]["reference"] == "Jn 3,16"
    assert sw["arc_meta"]["context_hash"] == "HASH-B"
    assert sw["arc_meta"]["generated_at"] == "2026-08-18T12:00:00"
    assert sw["arc_candidate"] is None


def test_accept_arc_candidate_rejects_mismatched_reference_with_zero_mutation():
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    result = accept_arc_candidate(state, reference="Róm 8,28", context_hash="HASH-B")

    assert result["accepted"] is False
    assert result["reason"] == "reference_mismatch"
    sw = state["sermon_workshop"]
    assert sw["arc"] == before_arc
    assert sw["arc_meta"] == before_meta
    assert sw["arc_candidate"] is not None  # a candidate megmarad, nem veszett el


def test_accept_arc_candidate_rejects_mismatched_context_hash_with_zero_mutation():
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    result = accept_arc_candidate(state, reference="Jn 3,16", context_hash="STALE-HASH")

    assert result["accepted"] is False
    assert result["reason"] == "context_hash_mismatch"
    sw = state["sermon_workshop"]
    assert sw["arc"] == before_arc
    assert sw["arc_meta"] == before_meta
    assert sw["arc_candidate"] is not None


def test_accept_arc_candidate_rejects_corrupted_candidate_with_zero_mutation():
    """Sérült candidate (nincs érvényes `points` szerkezete) — az
    elfogadás elutasított, a kanonikus arc/arc_meta bit-pontosan
    változatlan marad, függetlenül attól, hogy a reference/context_hash
    egyezne-e."""
    state: dict = {}
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "entry", "Meglévő tartalom — MEGŐRZENDŐ.")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])
    # Közvetlen, "kézzel tákolt" sérült candidate — nincs benne `points`.
    state["sermon_workshop"]["arc_candidate"] = {
        "reference": "Jn 3,16",
        "context_hash": "HASH-C",
    }

    result = accept_arc_candidate(state, reference="Jn 3,16", context_hash="HASH-C")

    assert result["accepted"] is False
    assert result["reason"] in ("no_candidate", "invalid_candidate")
    sw = state["sermon_workshop"]
    assert sw["arc"] == before_arc
    assert sw["arc_meta"] == before_meta


def test_accept_arc_candidate_no_candidate_present_is_rejected():
    state: dict = {}
    ensure_sermon_workshop_state(state)

    result = accept_arc_candidate(state, reference="Jn 3,16", context_hash="H")

    assert result["accepted"] is False
    assert result["reason"] == "no_candidate"


def test_accept_arc_candidate_never_triggers_ai_or_network_call():
    """Forráskód-szintű bizonyíték: sem az elfogadás, sem a candidate-
    beállítás/elvetés nem hivatkozik AI- vagy külső API-hívásra."""
    import inspect

    for fn in (
        accept_arc_candidate,
        set_arc_candidate,
        discard_arc_candidate,
        store_generated_arc_result,
        arc_has_content,
        normalize_arc_candidate,
        normalize_arc_meta,
    ):
        src = inspect.getsource(fn)
        for forbidden in (
            "generate_text(",
            "genai.",
            "requests.",
            "google.generativeai",
            "GenerateFn",
            "_call_generate",
        ):
            assert forbidden not in src, f"{fn.__name__} hivatkozik: {forbidden}"


# ---------------------------------------------------------------------------
# 17. RESET 2A: `discard_arc_candidate()` — mutációmentes elvetés.
# ---------------------------------------------------------------------------


def test_discard_arc_candidate_clears_only_the_candidate():
    state = _state_with_candidate()
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    discard_arc_candidate(state)

    sw = state["sermon_workshop"]
    assert sw["arc_candidate"] is None
    assert sw["arc"] == before_arc
    assert sw["arc_meta"] == before_meta


def test_discard_arc_candidate_on_already_empty_candidate_is_a_safe_no_op():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    discard_arc_candidate(state)  # nem dobhat kivételt akkor sem, ha nincs mit törölni
    assert state["sermon_workshop"]["arc_candidate"] is None


# ---------------------------------------------------------------------------
# 18. RESET 2A: `update_arc_point()` kiegészítése — `arc_meta.
#     manually_updated_at` frissítése, a többi `arc_meta` mező érintetlen.
# ---------------------------------------------------------------------------


def test_update_arc_point_stamps_arc_meta_manually_updated_at():
    state: dict = {}
    ensure_sermon_workshop_state(state)

    update_arc_point(state, "entry", "Kézzel írt szöveg.")

    meta = state["sermon_workshop"]["arc_meta"]
    assert meta["manually_updated_at"] != ""


def test_update_arc_point_does_not_touch_other_arc_meta_fields():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    store_generated_arc_result(
        state,
        points=GENERATED_POINTS,
        reference="Jn 3,16",
        context_hash="HASH-A",
        generated_at="2026-08-18T10:00:00",
    )

    update_arc_point(state, "arrival", "Kézzel finomított megérkezés.")

    meta = state["sermon_workshop"]["arc_meta"]
    assert meta["reference"] == "Jn 3,16"
    assert meta["context_hash"] == "HASH-A"
    assert meta["generated_at"] == "2026-08-18T10:00:00"
    assert meta["manually_updated_at"] != ""


# ---------------------------------------------------------------------------
# 19. RESET 2A: teljes projektmentés/visszatöltés — arc, arc_meta,
#     arc_candidate EGYÜTT, a legacy pontmezőkkel, sermon_outline-nal és
#     basket-tel együtt, egymást nem érintve.
# ---------------------------------------------------------------------------


def test_full_arc_stack_and_legacy_fields_survive_project_round_trip():
    state: dict = {
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        "sermon_workshop": get_default_sermon_workshop(),
        "basket": [["Exegézis", "Régi kosár-tartalom SENTINEL."]],
    }
    ensure_sermon_workshop_state(state)
    sw = state["sermon_workshop"]
    sw["entry_point"]["today_connection"] = "Legacy belépés SENTINEL."
    sw["sermon_path"]["type"] = "Legacy sermon_path SENTINEL."
    sw["christ_centered_arc"]["christ_connection"] = "Legacy christ_centered_arc SENTINEL."
    sw["closing"]["final_discovery"] = "Legacy closing SENTINEL."
    sw["engagement_elements"] = [
        {
            "id": "e1",
            "type": "kérdés",
            "text": "Legacy engagement SENTINEL.",
            "status": "draft",
            "source": "own",
            "created_at": "",
        }
    ]
    sw["sermon_outline"]["content"] = "Régi, mentett vázlatszöveg SENTINEL."

    store_generated_arc_result(
        state,
        points=GENERATED_POINTS,
        reference="Jn 3,16",
        context_hash="HASH-A",
        generated_at="2026-08-18T10:00:00",
    )
    update_arc_point(state, "entry", "Kézzel felülírt belépés SENTINEL.")
    store_generated_arc_result(
        state,
        points=GENERATED_POINTS,
        reference="Jn 3,16",
        context_hash="HASH-B",
        generated_at="2026-08-18T11:00:00",
    )  # ez most candidate lesz, mert az arc már nem üres

    project = build_project_data(state)
    reloaded = dict(project)
    ensure_text_workshop_state(reloaded)
    ensure_sermon_workshop_state(reloaded)
    rsw = reloaded["sermon_workshop"]

    # Arc-verem: arc (kézzel felülírt) + arc_meta (az ELSŐ generálásból,
    # update_arc_point csak a manually_updated_at-ot frissíti) + candidate.
    assert rsw["arc"]["entry"]["text"] == "Kézzel felülírt belépés SENTINEL."
    assert rsw["arc"]["arrival"]["text"] == "Megérkezés SENTINEL."
    assert rsw["arc_meta"]["reference"] == "Jn 3,16"
    assert rsw["arc_meta"]["context_hash"] == "HASH-A"
    assert rsw["arc_meta"]["manually_updated_at"] != ""
    assert rsw["arc_candidate"]["context_hash"] == "HASH-B"

    # Legacy mezők bit-pontosan megmaradnak.
    assert rsw["entry_point"]["today_connection"] == "Legacy belépés SENTINEL."
    assert rsw["sermon_path"]["type"] == "Legacy sermon_path SENTINEL."
    assert (
        rsw["christ_centered_arc"]["christ_connection"]
        == "Legacy christ_centered_arc SENTINEL."
    )
    assert rsw["closing"]["final_discovery"] == "Legacy closing SENTINEL."
    assert rsw["engagement_elements"][0]["text"] == "Legacy engagement SENTINEL."
    assert rsw["sermon_outline"]["content"] == "Régi, mentett vázlatszöveg SENTINEL."
    assert reloaded["basket"] == [["Exegézis", "Régi kosár-tartalom SENTINEL."]]


def test_migrate_legacy_arc_fields_is_never_called_automatically():
    """Forráskód-szintű bizonyíték: sem a `normalize_sermon_workshop`, sem
    az `ensure_sermon_workshop_state`, sem egyetlen új arc-segédfüggvény
    sem hívja a `migrate_legacy_arc_fields`-et — az kizárólag explicit,
    tesztből induló hívással érhető el (változatlan a RESET 2A előtti
    állapothoz képest)."""
    import inspect

    for fn in (
        normalize_sermon_workshop,
        ensure_sermon_workshop_state,
        store_generated_arc_result,
        set_arc_candidate,
        discard_arc_candidate,
        accept_arc_candidate,
        update_arc_point,
        normalize_arc_candidate,
        normalize_arc_meta,
        arc_has_content,
    ):
        src = inspect.getsource(fn)
        assert "migrate_legacy_arc_fields" not in src, fn.__name__


# ---------------------------------------------------------------------------
# 20. Szűk szemantikai korrekció (2026-08-18): `arc_meta.manually_updated_at`
#     KIZÁRÓLAG a JELENLEGI kanonikus arc utolsó kézi szerkesztésére
#     vonatkozhat — egy teljes tartalomcsere (közvetlen alkalmazás vagy
#     candidate-elfogadás) SOSEM örökölheti át egy korábbi, már lecserélt
#     arc kézi-szerkesztési időpontját.
# ---------------------------------------------------------------------------


def test_direct_apply_on_empty_arc_resets_stale_manually_updated_at():
    """1. pont: korábban létező manually_updated_at + üres arc + közvetlen
    generált alkalmazás → az új manually_updated_at üres."""
    state: dict = {}
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "entry", "Ideiglenes kézi szöveg.")
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""
    # Az arc-ot "üresre" állítjuk vissza (pl. a felhasználó törölte) —
    # ez az egyetlen módja annak, hogy `arc_has_content` újra hamis legyen,
    # miközben a régi (stale) manually_updated_at még ott áll a meta-ban.
    state["sermon_workshop"]["arc"] = get_default_arc()

    result = store_generated_arc_result(
        state,
        points=GENERATED_POINTS,
        reference="Jn 3,16",
        context_hash="HASH-A",
        generated_at="2026-08-18T10:00:00",
    )

    assert result["status"] == "applied"
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""


def test_accept_candidate_on_manually_edited_arc_resets_manually_updated_at():
    """2. pont: kézzel szerkesztett arc + candidate elfogadása → az új
    arc_meta manually_updated_at értéke üres (a candidate tartalma nem
    kézi szerkesztés eredménye)."""
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""

    result = accept_arc_candidate(state, reference="Jn 3,16", context_hash="HASH-B")

    assert result["accepted"] is True
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""


def test_discard_candidate_leaves_previous_manually_updated_at_untouched():
    """3. pont: candidate elvetése → a korábbi manually_updated_at
    változatlan."""
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    before = state["sermon_workshop"]["arc_meta"]["manually_updated_at"]
    assert before != ""

    discard_arc_candidate(state)

    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == before


def test_mismatched_candidate_rejection_leaves_previous_manually_updated_at_untouched():
    """4. pont: candidate reference/context mismatch → a korábbi
    manually_updated_at változatlan."""
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    before = state["sermon_workshop"]["arc_meta"]["manually_updated_at"]
    assert before != ""

    result_ref = accept_arc_candidate(state, reference="Róm 8,28", context_hash="HASH-B")
    assert result_ref["accepted"] is False
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == before

    result_hash = accept_arc_candidate(state, reference="Jn 3,16", context_hash="STALE")
    assert result_hash["accepted"] is False
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == before


def test_update_arc_point_after_accept_creates_fresh_manually_updated_at():
    """5. pont: candidate elfogadása után végzett update_arc_point() → új
    manually_updated_at keletkezik."""
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    accept_arc_candidate(state, reference="Jn 3,16", context_hash="HASH-B")
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""

    update_arc_point(state, "arrival", "Elfogadás utáni kézi finomítás.")

    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""


# ---------------------------------------------------------------------------
# 21. Szűk szemantikai korrekció: üres kontextusazonosító (candidate vagy
#     aktuális oldalon) SOSEM tekinthető érvényes egyezésnek —
#     `accept_arc_candidate` `"missing_context_identity"` okkal utasítja
#     el, nulla kanonikus mutációval.
# ---------------------------------------------------------------------------


def test_accept_rejects_empty_candidate_reference_with_zero_mutation():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "entry", "Meglévő tartalom — MEGŐRZENDŐ.")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])
    set_arc_candidate(
        state, points=GENERATED_POINTS, reference="", context_hash="HASH-X"
    )

    result = accept_arc_candidate(state, reference="", context_hash="HASH-X")

    assert result["accepted"] is False
    assert result["reason"] == "missing_context_identity"
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta


def test_accept_rejects_empty_candidate_context_hash_with_zero_mutation():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "entry", "Meglévő tartalom — MEGŐRZENDŐ.")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])
    set_arc_candidate(
        state, points=GENERATED_POINTS, reference="Jn 3,16", context_hash=""
    )

    result = accept_arc_candidate(state, reference="Jn 3,16", context_hash="")

    assert result["accepted"] is False
    assert result["reason"] == "missing_context_identity"
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta


def test_accept_rejects_empty_current_reference_with_zero_mutation():
    """A candidate-nek van érvényes reference/context_hash-e, de az
    ELFOGADÁSKOR átadott aktuális reference üres — így sem fogadható el."""
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    result = accept_arc_candidate(state, reference="", context_hash="HASH-B")

    assert result["accepted"] is False
    assert result["reason"] == "missing_context_identity"
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta


def test_accept_rejects_empty_current_context_hash_with_zero_mutation():
    state = _state_with_candidate(reference="Jn 3,16", context_hash="HASH-B")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    result = accept_arc_candidate(state, reference="Jn 3,16", context_hash="")

    assert result["accepted"] is False
    assert result["reason"] == "missing_context_identity"
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta


def test_accept_rejects_when_both_candidate_and_current_context_are_empty():
    """Mindkét oldal ÜGYANÚGY üres — nem tekinthető "véletlen egyezésnek"."""
    state: dict = {}
    ensure_sermon_workshop_state(state)
    update_arc_point(state, "entry", "Meglévő tartalom — MEGŐRZENDŐ.")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])
    set_arc_candidate(state, points=GENERATED_POINTS, reference="", context_hash="")

    result = accept_arc_candidate(state, reference="", context_hash="")

    assert result["accepted"] is False
    assert result["reason"] == "missing_context_identity"
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta


def test_arc_candidate_matches_context_helper_rejects_empty_identities():
    from sermon_workshop_data import _arc_candidate_matches_context

    valid_candidate = {"reference": "Jn 3,16", "context_hash": "HASH-1"}
    assert (
        _arc_candidate_matches_context(
            valid_candidate, reference="Jn 3,16", context_hash="HASH-1"
        )
        is True
    )
    assert (
        _arc_candidate_matches_context(valid_candidate, reference="", context_hash="HASH-1")
        is False
    )
    empty_candidate = {"reference": "", "context_hash": ""}
    assert (
        _arc_candidate_matches_context(empty_candidate, reference="", context_hash="")
        is False
    )
