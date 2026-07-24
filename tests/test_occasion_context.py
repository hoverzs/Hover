"""Alkalmi háttér (occasion_context) — regressziós tesztek."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from occasion_context import (
    BAPTISM_FIELD_KEYS,
    CEREMONIAL_OCCASIONS,
    FUNERAL_FIELD_KEYS,
    OCCASION_CONTEXT_KEY,
    WEDDING_FIELD_KEYS,
    empty_occasion_context,
    ensure_occasion_context_state,
    field_defs_for_occasion,
    field_keys_for_occasion,
    format_occasion_context_for_prompt,
    is_ceremonial_occasion,
    merge_context_for_passage_search,
    normalize_occasion_context,
    occasion_context_has_content,
    update_occasion_context_fields,
)
from passage_search_ai import suggest_passages_for_occasion
from passage_search_config import OCCASION_OPTIONS
from sermon_workshop_outline_ai import collect_outline_context_bundle
from sermon_workshop_outline_synth_ai import _occasion_block_for_prompt
from workspace_data import build_project_data, sanitize_project_data


def _funeral_ctx(**overrides: str) -> dict[str, Any]:
    ctx = empty_occasion_context(occasion_type="Temetés")
    ctx["fields"].update(
        {
            "deceased_name": "Kovács János",
            "age": "78",
            "life_path": "Tanár, három gyermek",
            "specific_situation": "Hosszú betegség után",
            "pastoral_note": "Család a reménységet kéri",
        }
    )
    ctx["fields"].update(overrides)
    return ctx


def _sug(reference: str) -> dict[str, Any]:
    return {
        "reference": reference,
        "title": "Rovid cim",
        "reason": "Illik az alkalomhoz, biblikusan megalapozott.",
        "homiletical_direction": "A remenyseg Isten igeretere tekint.",
        "familiarity": "less_common",
    }


def _payload(occasion: str, suggestions: list[dict[str, Any]], context: str = "") -> str:
    return json.dumps(
        {
            "occasion": occasion,
            "context_summary": context or occasion,
            "suggestions": suggestions,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Config / UI field schemas
# ---------------------------------------------------------------------------


def test_ceremonial_occasions_and_field_schemas():
    assert CEREMONIAL_OCCASIONS == {
        "Virrasztó",
        "Temetés",
        "Keresztelés",
        "Esketés",
    }
    for occ in CEREMONIAL_OCCASIONS:
        assert occ in OCCASION_OPTIONS
        assert is_ceremonial_occasion(occ)
    assert not is_ceremonial_occasion("Vasárnapi istentisztelet")
    assert not is_ceremonial_occasion("Egyéb alkalom")

    assert field_keys_for_occasion("Temetés") == FUNERAL_FIELD_KEYS
    assert field_keys_for_occasion("Virrasztó") == FUNERAL_FIELD_KEYS
    assert field_keys_for_occasion("Keresztelés") == BAPTISM_FIELD_KEYS
    assert field_keys_for_occasion("Esketés") == WEDDING_FIELD_KEYS
    assert field_keys_for_occasion("Vasárnapi istentisztelet") == ()

    baptism_labels = [lab for _, lab, _ in field_defs_for_occasion("Keresztelés")]
    assert any("gyermek" in lab.casefold() for lab in baptism_labels)
    wedding_labels = [lab for _, lab, _ in field_defs_for_occasion("Esketés")]
    assert any("házas" in lab.casefold() for lab in wedding_labels)
    funeral_labels = [lab for _, lab, _ in field_defs_for_occasion("Temetés")]
    assert any("elhunyt" in lab.casefold() for lab in funeral_labels)


def test_normalize_empty_and_legacy_roundtrip():
    empty = normalize_occasion_context(None)
    assert empty["occasion_type"] == ""
    assert empty["fields"]["deceased_name"] == ""
    assert empty["note"] == ""
    assert not occasion_context_has_content(empty)

    legacy = {
        "occasion_type": "Temetés",
        "deceased_name": "Anna",
        "age": "90",
    }
    norm = normalize_occasion_context(legacy)
    assert norm["occasion_type"] == "Temetés"
    assert norm["fields"]["deceased_name"] == "Anna"
    assert norm["fields"]["age"] == "90"
    assert occasion_context_has_content(norm)

    # Ismeretlen alkalom → üres type, mezők megmaradnak
    weird = normalize_occasion_context({"occasion_type": "XYZ", "fields": {"age": "1"}})
    assert weird["occasion_type"] == ""
    assert weird["fields"]["age"] == "1"


def test_format_prompt_empty_vs_funeral():
    assert format_occasion_context_for_prompt(None) == ""
    assert format_occasion_context_for_prompt(empty_occasion_context()) == ""

    block = format_occasion_context_for_prompt(_funeral_ctx(), occasion="Temetés")
    assert "pásztori alkalmazási kontextus" in block
    assert "Kovács János" in block
    assert "78" in block
    assert "Ne találj ki" in block or "Ne állíts" in block
    assert "üdvösség" in block.casefold()


def test_merge_context_for_passage_search():
    merged = merge_context_for_passage_search(
        "hirtelen veszteség",
        _funeral_ctx(),
        occasion="Virrasztó",
    )
    assert "hirtelen veszteség" in merged
    assert "Strukturált alkalmi háttér" in merged
    assert "Kovács" in merged

    only_free = merge_context_for_passage_search("csak ez", None, occasion="Temetés")
    assert only_free == "csak ez"


# ---------------------------------------------------------------------------
# Persistence — guest session vs logged-in project
# ---------------------------------------------------------------------------


def test_project_data_persists_occasion_context_logged_in_shape():
    state = {
        "last_igehely": "Jn 11,25–26",
        "last_alkalom": "temetés",
        OCCASION_CONTEXT_KEY: _funeral_ctx(),
    }
    payload = build_project_data(state, version="2.0-test")
    assert OCCASION_CONTEXT_KEY in payload
    assert payload[OCCASION_CONTEXT_KEY]["fields"]["deceased_name"] == "Kovács János"

    cleaned = sanitize_project_data(payload)
    assert cleaned[OCCASION_CONTEXT_KEY]["occasion_type"] == "Temetés"
    assert cleaned[OCCASION_CONTEXT_KEY]["fields"]["age"] == "78"

    # Régi projekt: hiányzó kulcs → üres alap
    old = sanitize_project_data({"last_igehely": "Jn 3,16"})
    assert OCCASION_CONTEXT_KEY in old
    assert old[OCCASION_CONTEXT_KEY]["fields"]["deceased_name"] == ""


def test_guest_session_roundtrip_without_cloud():
    """Vendég: session-ben él; nem kerül history / más projektbe."""
    ss: dict[str, Any] = {}
    ensure_occasion_context_state(ss)
    update_occasion_context_fields(
        ss,
        occasion_type="Keresztelés",
        fields={
            "child_name": "Anna",
            "parents_request": "szövetség hangsúlya",
            "pastoral_note": "csendes hálaadás",
        },
    )
    assert ss[OCCASION_CONTEXT_KEY]["fields"]["child_name"] == "Anna"

    # Más „projekt” session — nincs automatikus átvitel
    other: dict[str, Any] = {}
    ensure_occasion_context_state(other)
    assert other[OCCASION_CONTEXT_KEY]["fields"]["child_name"] == ""

    # History extract csak passage-t néz — PII nem szivárog ref-listába
    from passage_search_history import collect_used_passage_references

    projects = [
        {
            "passage": "Jn 3,16",
            "project_data": {
                "last_igehely": "Jn 3,16",
                OCCASION_CONTEXT_KEY: _funeral_ctx(),
            },
        }
    ]
    hist = collect_used_passage_references(projects)
    blob = " ".join(hist.normalized_references)
    assert "Kovács" not in blob
    assert "Jn 3,16" in blob or "Jn" in blob


def test_type_switch_keeps_fields_silently():
    ss: dict[str, Any] = {}
    update_occasion_context_fields(
        ss,
        occasion_type="Temetés",
        fields={"deceased_name": "Péter", "age": "60"},
    )
    update_occasion_context_fields(ss, occasion_type="Vasárnapi istentisztelet")
    assert ss[OCCASION_CONTEXT_KEY]["occasion_type"] == "Vasárnapi istentisztelet"
    # Mezők megmaradnak (UI elrejti, adat nem vész el)
    assert ss[OCCASION_CONTEXT_KEY]["fields"]["deceased_name"] == "Péter"


# ---------------------------------------------------------------------------
# AI prompt wiring
# ---------------------------------------------------------------------------


def test_passage_recommend_includes_occasion_context_no_passage():
    """Nincs konkrét textus + virrasztó háttér → 4–5 javaslat, kontextus a promptban."""
    seen: dict[str, str] = {}

    def gen(prompt: str, **_kwargs: Any) -> str:
        seen["prompt"] = prompt
        return _payload(
            "Virrasztó",
            [
                _sug("Job 19,23-27"),
                _sug("Zsolt 90,1-12"),
                _sug("Ezs 25,6-9"),
                _sug("2Kor 4,16-18"),
                _sug("1Pt 1,3-9"),
            ],
            context="virrasztó",
        )

    ctx = empty_occasion_context(occasion_type="Virrasztó")
    ctx["fields"]["deceased_name"] = "Mária néni"
    ctx["fields"]["specific_situation"] = "hálás emlékezés"
    merged = merge_context_for_passage_search("", ctx, occasion="Virrasztó")

    result = suggest_passages_for_occasion(
        occasion="Virrasztó",
        context=merged,
        generate_fn=gen,
    )
    assert result.ok
    assert MIN_OK <= len(result.suggestions) <= 5
    assert "Mária" in seen["prompt"] or "hálás" in seen["prompt"]
    assert "Virrasztó" in seen["prompt"]


MIN_OK = 4


def test_concrete_passage_empty_background_unchanged_alap():
    """Üres háttér → build_alap pastoral blokk nélkül (régi viselkedés)."""
    import app as app_mod

    class _SS(dict):
        pass

    ss = _SS()
    ss.update(
        {
            "last_igehely": "Jn 11,25–26",
            "last_alkalom": "temetés",
            "last_stilus": "pasztorális",
            "last_sajat": "",
            "bible_translation": "RÚF 2014",
            "passage_text": "Én vagyok a feltámadás és az élet.",
            OCCASION_CONTEXT_KEY: empty_occasion_context(occasion_type="Temetés"),
        }
    )
    with patch.object(app_mod, "st") as st_mock:
        st_mock.session_state = ss
        plain = app_mod.build_alap_from_state(include_pastoral_context=True)
        assert "pásztori alkalmazási kontextus" not in plain
        assert "Jn 11,25–26" in plain


def test_concrete_passage_funeral_background_in_overview_not_exegesis():
    """Konkrét textus + temetési háttér: overview kapja, exegézis nem."""
    import app as app_mod

    class _SS(dict):
        pass

    ss = _SS()
    ss.update(
        {
            "last_igehely": "Jn 11,25–26",
            "last_alkalom": "temetés",
            "last_stilus": "pasztorális",
            "last_sajat": "",
            "bible_translation": "RÚF 2014",
            "passage_text": "Én vagyok a feltámadás és az élet.",
            "passage_search": {"occasion": "Temetés"},
            OCCASION_CONTEXT_KEY: _funeral_ctx(),
        }
    )
    with patch.object(app_mod, "st") as st_mock:
        st_mock.session_state = ss
        overview_alap = app_mod.build_alap_from_state(include_pastoral_context=True)
        exegesis_alap = app_mod.build_alap_from_state(include_pastoral_context=False)

    assert "pásztori alkalmazási kontextus" in overview_alap
    assert "Kovács János" in overview_alap
    assert "Jn 11,25–26" in overview_alap
    # Exegézis: szöveghű, nincs életrajz
    assert "pásztori alkalmazási kontextus" not in exegesis_alap
    assert "Kovács János" not in exegesis_alap
    assert "Én vagyok a feltámadás" in exegesis_alap


def test_outline_bundle_and_synth_prompt_get_occasion_context():
    state = {
        "last_igehely": "Jn 14,1–6",
        "last_alkalom": "temetés",
        "passage_text": "Ne nyugtalankodjék a ti szívetek.",
        "passage_search": {"occasion": "Temetés"},
        OCCASION_CONTEXT_KEY: _funeral_ctx(),
        "text_workshop": {"text_main_idea": "", "approved_insights": []},
        "sermon_workshop": {},
    }
    bundle = collect_outline_context_bundle(state)
    assert "occasion_context" in bundle
    assert bundle["occasion_context"]["fields"]["deceased_name"] == "Kovács János"
    assert bundle.get("passage_search_occasion") == "Temetés"

    block = _occasion_block_for_prompt(bundle)
    assert "pásztori alkalmazási kontextus" in block or "ALKALMI KONTEXTUS" in block
    assert "Kovács" in block or "Temetés" in block


def test_virraszto_still_in_options_regression():
    assert "Virrasztó" in OCCASION_OPTIONS
    assert OCCASION_OPTIONS.index("Virrasztó") + 1 == OCCASION_OPTIONS.index("Temetés")
    assert is_ceremonial_occasion("Virrasztó")
    defs = field_defs_for_occasion("Virrasztó")
    assert len(defs) == len(FUNERAL_FIELD_KEYS)
