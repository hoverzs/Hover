"""Igehirdetési műhely 11->5 fázis migráció + Textusösszegzés-additivitás tesztek.

Nem Streamlit UI — a régi szakaszfelirat->új fázis megfeleltetést és az
Igehirdetési műhely vázlat-kontextusának Textusösszegzés-kezelését
vizsgálja (két-műhely refaktor, Fázis 2; 2D.1 adatfolyam-javítás óta a
Textusösszegzés additív forrás, nem helyettesíti a nyers exegesis/
theology/history/original_text mezőket)."""

from __future__ import annotations

from sermon_outline_engine import extract_outline_background_material
from sermon_workshop_data import (
    add_engagement_element,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    remove_engagement_element,
    update_engagement_element,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import collect_outline_context_bundle
from sermon_workshop_ui import _SW_LEGACY_SECTION_TO_PHASE, _SW_SECTION_OPTIONS
from workshop_nav_ui import SERMON_PHASE_OPTIONS


def test_legacy_section_labels_all_map_to_a_valid_phase():
    """Minden régi (11 szakaszos) felirat egy érvényes új fázisnévre képződik."""
    for legacy_label in _SW_SECTION_OPTIONS:
        assert legacy_label in _SW_LEGACY_SECTION_TO_PHASE, (
            f"Hiányzó migráció: {legacy_label!r}"
        )
        assert _SW_LEGACY_SECTION_TO_PHASE[legacy_label] in SERMON_PHASE_OPTIONS

    # Régebbi, már korábban is átnevezett feliratok (projektmentésben előfordulhatnak).
    for extra_legacy in (
        "A prédikáció útja",
        "Prédikációs mozgások",
        "Lezárás",
        "Képek, illusztrációk és alkalmazás",
    ):
        assert extra_legacy in _SW_LEGACY_SECTION_TO_PHASE
        assert _SW_LEGACY_SECTION_TO_PHASE[extra_legacy] in SERMON_PHASE_OPTIONS


def test_outline_context_bundle_falls_back_to_raw_fields_when_summary_empty():
    """Üres (tartalom nélküli) Textusösszegzés esetén a nyers mezők maradnak a forrás.

    Korrekciós fázis 3.1 óta a Textusösszegzés bekerülése a TARTALOM
    meglétén múlik, nem a jóváhagyáson (ld. TEXTUS_IGEHIRDETESI_MUHELY_
    ADATFOLYAM_AUDIT.md) — ezért ez a teszt most az ÜRES összegzés esetét
    fedi le, nem a "nincs jóváhagyva" esetet (azt ld. lentebb, draft-tal is
    tartalmat hordozó összegzésnél)."""
    state = {
        "last_igehely": "Jn 3,16",
        "exegesis": "Exegetikai anyag.",
        "theology": "Teológiai anyag.",
        "text_workshop": {
            "text_summary": {"base_tension": "", "status": "draft"},
        },
    }
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("exegesis") == "Exegetikai anyag."
    assert bundle.get("theology") == "Teológiai anyag."
    assert "text_summary" not in bundle
    assert "text_summary" not in bundle["source_keys"]


def test_outline_context_bundle_adds_draft_summary_alongside_raw_fields():
    """2D.1 (adatfolyam-audit, bizonyított hiba javítva): a Textusösszegzés
    — DRAFT állapotban is, ha van tartalma — TOVÁBBRA IS bekerül a
    bundle-be, de többé NEM helyettesíti/nyomja el a nyers exegesis/
    theology mezőket — mindkettő együtt, additívan jelenik meg. A korábbi
    kizárólagos viselkedés (`if summary_fields: ... else: ...`) néma
    adatvesztést okozott: egyetlen kitöltött összegzés-mező is
    eltüntette a jóváhagyott, részletes kutatási anyagot a vázlatmotor
    elől."""
    state = {
        "last_igehely": "Jn 3,16",
        "exegesis": "Nyers exegézis, most már bekerül.",
        "theology": "Nyers teológia, most már bekerül.",
        "text_workshop": {
            "text_summary": {
                "base_tension": "Vázlat, de van tartalma.",
                "status": "draft",
            },
        },
    }
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("exegesis") == "Nyers exegézis, most már bekerül."
    assert bundle.get("theology") == "Nyers teológia, most már bekerül."
    assert bundle["text_summary"]["base_tension"] == "Vázlat, de van tartalma."
    assert bundle["text_summary_status"] == "draft"
    assert "text_summary" in bundle["source_keys"]
    assert "exegesis" in bundle["source_keys"]
    assert "theology" in bundle["source_keys"]


def test_outline_context_bundle_adds_approved_summary_alongside_raw_fields():
    """2D.1: jóváhagyott Textusösszegzés esetén is megmarad a nyers
    exegesis/theology/history/original_text — additív forrás, nem
    kizárólagos."""
    state = {
        "last_igehely": "Jn 3,16",
        "exegesis": "Nyers exegézis, most már bekerül.",
        "theology": "Nyers teológia, most már bekerül.",
        "history": "Nyers kortörténet, most már bekerül.",
        "original_text": "Nyers eredeti szöveg elemzés, most már bekerül.",
        "text_workshop": {
            "text_summary": {
                "main_idea": "A textus fő gondolata.",
                "base_tension": "A textus alapfeszültsége.",
                "key_exegetical_findings": "Legfontosabb exegetikai felismerések.",
                "theological_emphases": "Teológiai hangsúlyok.",
                "genre_structure_notes": "Műfaj és szerkezet.",
                "status": "approved",
                "approved_context_hash": "abc123",
            },
        },
    }
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("exegesis") == "Nyers exegézis, most már bekerül."
    assert bundle.get("theology") == "Nyers teológia, most már bekerül."
    assert bundle.get("history") == "Nyers kortörténet, most már bekerül."
    assert bundle.get("original_text") == "Nyers eredeti szöveg elemzés, most már bekerül."
    assert bundle["text_summary"]["base_tension"] == "A textus alapfeszültsége."
    assert bundle["text_summary_status"] == "approved"
    assert bundle["text_summary_approved_context_hash"] == "abc123"
    assert "text_summary" in bundle["source_keys"]
    for key in ("exegesis", "theology", "history", "original_text"):
        assert key in bundle["source_keys"]


# ---------------------------------------------------------------------------
# Korrekciós fázis 2A — Homiletikai belépési pont + A prédikáció íve
# ---------------------------------------------------------------------------


def test_entry_point_and_arc_fields_default_empty():
    sw = get_default_sermon_workshop()
    assert sw["entry_point"] == {"today_connection": "", "type": "", "text": ""}
    assert sw["entry_point_status"] == "draft"
    assert sw["sermon_path"]["first_shift"] == ""
    assert sw["sermon_path"]["deepening"] == ""


def test_old_project_without_entry_point_or_arc_fields_normalizes_safely():
    """Régi (2A előtti) projekt: nincs entry_point, a sermon_path-nak nincs
    first_shift/deepening mezője — a normalizálás ne dobjon hibát, és a
    régi sermon_movements adatok maradjanak meg."""
    legacy = {
        "sermon_path": {
            "type": "text_following",
            "reason": "Régi indoklás",
            "starting_point": "Régi kiindulópont",
            "destination": "Régi megérkezési pont",
        },
        "sermon_path_status": "approved",
        "sermon_movements": [
            {"id": "m1", "role": "tension", "title": "Régi mozgás", "core_content": "Régi tartalom"},
        ],
    }
    normalized = normalize_sermon_workshop(legacy)
    assert normalized["entry_point"] == {"today_connection": "", "type": "", "text": ""}
    assert normalized["entry_point_status"] == "draft"
    assert normalized["sermon_path"]["starting_point"] == "Régi kiindulópont"
    assert normalized["sermon_path"]["first_shift"] == ""
    assert normalized["sermon_path"]["deepening"] == ""
    # A régi mozgás nem veszett el.
    assert len(normalized["sermon_movements"]) == 1
    assert normalized["sermon_movements"][0]["core_content"] == "Régi tartalom"


def test_entry_point_status_update_stamps_approved_hash():
    session = {}
    update_sermon_workshop_section(
        session, "entry_point", {"today_connection": "x", "type": "question", "text": "y"}
    )
    update_sermon_workshop_section(session, "entry_point_status", "approved")
    sw = session["sermon_workshop"]
    assert sw["entry_point_status"] == "approved"
    assert sw["entry_point_approved_context_hash"]


def test_sermon_path_new_fields_are_approval_gated():
    """Piszkozat sermon_path (first_shift/deepening-gel együtt) ne kerüljön
    be a vázlat háttéranyagába jóváhagyás nélkül; jóváhagyás után igen."""
    state = {
        "last_igehely": "Jn 3,16",
        "sermon_workshop": {
            "sermon_path": {
                "starting_point": "sp",
                "first_shift": "első látásváltás szövege",
                "deepening": "mélyítés szövege",
            },
            "sermon_path_status": "draft",
        },
    }
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "sermon_path" not in background

    state["sermon_workshop"]["sermon_path_status"] = "approved"
    bundle2 = collect_outline_context_bundle(state)
    background2 = extract_outline_background_material(bundle2)
    assert "sermon_path" in background2
    assert background2["sermon_path"]["first_shift"] == "első látásváltás szövege"
    assert background2["sermon_path"]["deepening"] == "mélyítés szövege"


def test_sermon_movements_share_sermon_path_approval_gate():
    """A mozgáslista (sermon_movements) ne kerülhessen be a vázlatba a
    sermon_path jóváhagyása nélkül — ugyanazon a felületen, ugyanazzal a
    gombbal hagyja jóvá a felhasználó mindkettőt."""
    state = {
        "last_igehely": "Jn 3,16",
        "sermon_workshop": {
            "sermon_path": {"starting_point": "sp"},
            "sermon_path_status": "draft",
            "sermon_movements": [
                {"id": "m1", "role": "tension", "core_content": "mozgás tartalma"},
            ],
        },
    }
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "sermon_movements" not in background

    state["sermon_workshop"]["sermon_path_status"] = "approved"
    bundle2 = collect_outline_context_bundle(state)
    background2 = extract_outline_background_material(bundle2)
    assert "sermon_movements" in background2


def test_entry_point_is_approval_gated_in_outline_background():
    state = {
        "last_igehely": "Jn 3,16",
        "sermon_workshop": {
            "entry_point": {"today_connection": "tc", "type": "question", "text": "q"},
            "entry_point_status": "draft",
        },
    }
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert "entry_point" not in background

    state["sermon_workshop"]["entry_point_status"] = "approved"
    bundle2 = collect_outline_context_bundle(state)
    background2 = extract_outline_background_material(bundle2)
    assert "entry_point" in background2
    assert background2["entry_point"]["text"] == "q"


# ---------------------------------------------------------------------------
# Korrekciós fázis 2B — Megszólítás és bevonás
# ---------------------------------------------------------------------------


def test_engagement_elements_default_empty():
    sw = get_default_sermon_workshop()
    assert sw["engagement_elements"] == []
    assert sw["engagement_suggestions"] is None


def test_old_project_without_engagement_elements_normalizes_safely():
    """Régi (2B előtti) projekt: nincs engagement_elements, de VAN régi
    illusztráció/aktualizálás — egyik se vesszen el, és a normalizálás ne
    dobjon hibát."""
    legacy = {
        "illustrations": [{"id": "old1", "idea": "Régi illusztráció"}],
        "applications": [{"id": "old2", "application": "Régi alkalmazás"}],
        "enrichment_status": "approved",
    }
    normalized = normalize_sermon_workshop(legacy)
    assert normalized["engagement_elements"] == []
    assert len(normalized["illustrations"]) == 1
    assert normalized["illustrations"][0]["idea"] == "Régi illusztráció"
    assert len(normalized["applications"]) == 1
    assert normalized["enrichment_status"] == "approved"


def test_engagement_element_add_edit_approve_delete_individually():
    session = {}
    el = add_engagement_element(session, type="question", text="Eredeti szöveg?", source="ai")
    eid = el["id"]
    assert el["status"] == "draft"

    # Szerkesztés — nem jóváhagyott, státusz marad draft.
    edited = update_engagement_element(session, eid, text="Szerkesztett szöveg?")
    assert edited["text"] == "Szerkesztett szöveg?"
    assert edited["status"] == "draft"

    # Jóváhagyás — egyedi, a többi elemet nem érinti.
    other = add_engagement_element(session, type="image_metaphor", text="Egy kép.", source="own")
    approved = update_engagement_element(session, eid, status="approved")
    assert approved["status"] == "approved"
    still_draft = next(
        e
        for e in session["sermon_workshop"]["engagement_elements"]
        if e["id"] == other["id"]
    )
    assert still_draft["status"] == "draft"

    # Törlés — csak a célzott elem tűnik el.
    remove_engagement_element(session, eid)
    remaining = session["sermon_workshop"]["engagement_elements"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == other["id"]


def test_only_approved_engagement_elements_reach_outline_context():
    """Jóváhagyatlan (draft) megszólító elem ne kerülhessen a végső vázlat
    kontextusába; jóváhagyás után igen, és csak az adott elem."""
    session = {"last_igehely": "Jn 3,16"}
    add_engagement_element(session, type="question", text="Draft kérdés?", source="ai")
    approved_el = add_engagement_element(
        session, type="presence_sentence", text="Jóváhagyott mondat.", source="own"
    )
    update_engagement_element(session, approved_el["id"], status="approved")

    bundle = collect_outline_context_bundle(session)
    background = extract_outline_background_material(bundle)
    assert "engagement_elements" in background
    texts = [item["text"] for item in background["engagement_elements"]]
    assert texts == ["Jóváhagyott mondat."]
    assert "Draft kérdés?" not in texts


def test_engagement_section_fully_skippable_does_not_block_outline_readiness():
    """Üres engagement_elements esetén is fusson az outline-readiness ellenőrzés
    (a szakasz opcionális, kihagyása nem hibát okoz)."""
    from sermon_workshop_outline_ai import assess_outline_readiness

    session = {
        "last_igehely": "Jn 3,16",
        "passage_text": "Mert úgy szerette Isten a világot" * 3,
        "sermon_workshop": {"engagement_elements": []},
    }
    # Nem szabad kivételt dobnia amiatt, hogy engagement_elements üres.
    readiness = assess_outline_readiness(session)
    assert readiness is not None


def test_unapproved_old_illustrations_do_not_reach_outline_context():
    """A régi, nem jóváhagyott illusztrációs/aktualizálási tartalom ne
    kerüljön automatikusan a vázlat kontextusába."""
    session = {
        "last_igehely": "Jn 3,16",
        "sermon_workshop": {
            "illustrations": [{"id": "i1", "idea": "Nem jóváhagyott illusztráció"}],
            "enrichment_status": "draft",
        },
    }
    bundle = collect_outline_context_bundle(session)
    background = extract_outline_background_material(bundle)
    assert "illustrations" not in background
    assert "illustrations" not in bundle

    session["sermon_workshop"]["enrichment_status"] = "approved"
    bundle2 = collect_outline_context_bundle(session)
    assert "illustrations" in bundle2
