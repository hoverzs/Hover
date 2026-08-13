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
    empty_arc_point,
    ensure_sermon_workshop_state,
    get_default_arc,
    get_default_sermon_workshop,
    migrate_legacy_arc_fields,
    normalize_arc,
    normalize_sermon_workshop,
    update_arc_point,
)


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
    assert state["sermon_workshop"]["arc"]["entry"]["text"] == "Új arc.entry szöveg."
