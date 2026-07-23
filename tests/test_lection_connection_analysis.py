"""Lekció ↔ textus kapcsolati elemzés — regresszió és minőségi padló."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    save_lection_connection_analysis,
    save_lection_suggestions,
)
from sermon_workshop_lection_link_ai import (
    WEAK_CONNECTION_MESSAGE,
    analyze_lection_textus_link,
    build_lection_link_fingerprint,
    detect_passage_lection_overlap,
    lection_connection_analysis_is_stale,
    normalize_lection_connection_analysis,
    normalize_lection_link_type,
)
from workspace_data import build_project_data, sanitize_project_data


@pytest.fixture
def session(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    ensure_sermon_workshop_state(state)
    return state


def stub_json(payload: dict):
    raw = json.dumps(payload, ensure_ascii=False)

    def _fn(*_a, **_k):
        return raw

    return _fn


def _strong_ot_for_nt_payload() -> dict:
    return {
        "one_sentence": (
            "Ézsaiás a megtartó Úr ígéretét hangolja elő, amelyet Júdás "
            "a hitben való megmaradásra fordít."
        ),
        "connection_types": [
            {
                "type": "promise_fulfillment",
                "rationale": "Az ószövetségi megtartás-ígéret az újszövetségi buzdítást keretezi.",
            },
            {
                "type": "liturgical_preparation",
                "rationale": "A lekció a prédikáció előtt ráhangol Isten hűségére.",
            },
        ],
        "key_links": [
            {
                "verse_or_detail": "Ézs 40,11 — pásztorként terel",
                "motif": "Isten megtartó gondoskodása",
                "sermon_significance": "Előkészíti Júdás megtartásra hívó szavát.",
            },
            {
                "verse_or_detail": "Júd 21 — őrizzétek magatokat",
                "motif": "Megmaradás Isten szeretetében",
                "sermon_significance": "A hallgató válaszát a lekció reménysége tartja.",
            },
        ],
        "linguistic_insights": [],
        "historical_background": [
            {"observation": "A száműzetés utáni vigasztalás hangja Ézsaiásnál."}
        ],
        "theological_gospel_link": {
            "divine_action": "Isten maga őrzi és tereli népét.",
            "grace_arc": "Az ígéret megelőzi a buzdítást.",
            "christ_centered": "",
            "listener_response": "A gyülekezet megtartottként hallhatja a felszólítást.",
        },
        "liturgical_role": {
            "why_read": "A prédikáció előtt Isten hűségére hangol.",
            "congregation_focus": "A pásztori gondviselés képe.",
            "before_or_after": "before",
            "needs_brief_intro": True,
            "strongest_verses": "Ézs 40,10–11",
        },
        "homiletical_uses": [
            {
                "placement": "introduction",
                "suggestion": "A pásztorkép említhető a megnyitásban.",
            }
        ],
        "connection_strength": "strong",
        "weak_connection_note": "",
        "alternative_lections": [],
        "overlap_note": "",
    }


def _weak_payload() -> dict:
    return {
        "one_sentence": "Mindkét szakasz Istenről beszél, de a kapcsolat felszínes.",
        "connection_types": [
            {
                "type": "shared_motif",
                "rationale": "Csak általános „Isten”-motívum köti őket össze.",
            }
        ],
        "key_links": [
            {
                "verse_or_detail": "Ált. kulcsszó",
                "motif": "Isten",
                "sermon_significance": "Nem textusspecifikus.",
            },
            {
                "verse_or_detail": "Másik általános motívum",
                "motif": "Hit",
                "sermon_significance": "Bármely szakaszhoz illeszthető.",
            },
        ],
        "linguistic_insights": [],
        "historical_background": [],
        "theological_gospel_link": {
            "divine_action": "",
            "grace_arc": "",
            "christ_centered": "",
            "listener_response": "",
        },
        "liturgical_role": {
            "why_read": "Inkább általános felolvasás.",
            "congregation_focus": "Általános figyelem.",
            "before_or_after": "either",
            "needs_brief_intro": False,
            "strongest_verses": "",
        },
        "homiletical_uses": [],
        "connection_strength": "weak",
        "weak_connection_note": "valami más szöveg",
        "alternative_lections": [
            {
                "reference": "Jn 15,1–11",
                "rationale": "Szorosabban kapcsolódik a megmaradáshoz.",
            },
            {
                "reference": "Zsolt 121",
                "rationale": "Az Úr őrizete közvetlenebb párhuzam.",
            },
        ],
        "overlap_note": "",
    }


def _nt_lection_for_ot_payload() -> dict:
    data = _strong_ot_for_nt_payload()
    data["one_sentence"] = (
        "János evangéliuma a szőlőtő képével az ószövetségi megmaradás-igéket "
        "Krisztusban hangolja tovább."
    )
    data["connection_types"] = [
        {
            "type": "typological_canonical",
            "rationale": "A szőlőtő kánoni íve az ószövetségi szőlő-motívumot folytatja.",
        }
    ]
    data["key_links"] = [
        {
            "verse_or_detail": "Ézs 5 — szőlőskert",
            "motif": "Isten népe mint szőlő",
            "sermon_significance": "A lekció a Krisztusban való megmaradást mutatja.",
        },
        {
            "verse_or_detail": "Jn 15,4 — maradjatok énbennem",
            "motif": "Megmaradás",
            "sermon_significance": "Homiletikai cél: Krisztusban maradás.",
        },
    ]
    return data


def test_normalize_link_types():
    assert normalize_lection_link_type("shared_motif") == "shared_motif"
    assert normalize_lection_link_type("Kontraszt") == "contrast"
    assert normalize_lection_link_type("unknown") == ""


def test_analyze_ai_suggested_lection_ot_for_nt():
    """Alkalmazás által javasolt OT lekció + NT textus."""
    result = analyze_lection_textus_link(
        passage="Júd 17–20",
        passage_text="Ti pedig, szeretteim, emlékezzetek…",
        lection_reference="Ézs 40,1–11",
        lection_text="Vigasztaljátok népemet…",
        exegesis="Júdás a hitben való megmaradásra buzdít.",
        theology="Isten megtartó kegyelme.",
        sermon_main_idea="Isten megtartja népét.",
        generate_fn=stub_json(_strong_ot_for_nt_payload()),
    )
    assert result.ok
    assert "megtart" in result.one_sentence.casefold() or "ígéret" in result.one_sentence.casefold()
    assert len(result.connection_types) >= 1
    assert len(result.key_links) >= 2
    assert result.connection_strength == "strong"
    assert result.weak_connection_note == ""
    assert result.source_fingerprint
    assert result.lection_reference == "Ézs 40,1–11"


def test_analyze_manual_lection_nt_for_ot():
    """Kézzel megadott NT lekció + OT textus."""
    result = analyze_lection_textus_link(
        passage="Ézs 5,1–7",
        passage_text="Dalolok szerelmesemről…",
        lection_reference="Jn 15,1–8",
        lection_text="Én vagyok a szőlőtő…",
        original_text="ἄμπελος — szőlőtő",
        history="A szőlőskert Izrael képe.",
        sermon_main_idea="Isten népének termő élete.",
        generate_fn=stub_json(_nt_lection_for_ot_payload()),
    )
    assert result.ok
    assert result.connection_types[0].type == "typological_canonical"
    assert any("szőlő" in k.motif.casefold() for k in result.key_links)


def test_analyze_directly_related_and_distant():
    strong = analyze_lection_textus_link(
        passage="Júd 17–20",
        passage_text="…",
        lection_reference="Jn 15,1–11",
        generate_fn=stub_json(_strong_ot_for_nt_payload()),
    )
    assert strong.ok and strong.connection_strength == "strong"

    weak = analyze_lection_textus_link(
        passage="Júd 17–20",
        passage_text="…",
        lection_reference="Préd 3,1–8",
        generate_fn=stub_json(_weak_payload()),
    )
    assert weak.ok
    assert weak.connection_strength == "weak"
    assert weak.weak_connection_note == WEAK_CONNECTION_MESSAGE
    assert len(weak.alternative_lections) == 2


def test_overlap_same_and_partial():
    note = detect_passage_lection_overlap("Júd 17–20", "Júd 17–20")
    assert "megegyezik" in note.casefold() or "azonos" in note.casefold()

    partial = detect_passage_lection_overlap("Júd 17–20", "Júd 17–23")
    assert partial  # részleges átfedés


def test_fingerprint_stale_on_textus_or_lection_change():
    fp1 = build_lection_link_fingerprint(
        passage_reference="Júd 17–20",
        passage_text="A",
        lection_reference="Jn 15,1–11",
        lection_text="B",
        sermon_main_idea="C",
        outline_signature="",
    )
    fp2 = build_lection_link_fingerprint(
        passage_reference="Júd 17–20",
        passage_text="A megváltozott",
        lection_reference="Jn 15,1–11",
        lection_text="B",
        sermon_main_idea="C",
        outline_signature="",
    )
    fp3 = build_lection_link_fingerprint(
        passage_reference="Júd 17–20",
        passage_text="A",
        lection_reference="Zsolt 121",
        lection_text="B",
        sermon_main_idea="C",
        outline_signature="",
    )
    assert fp1 != fp2
    assert fp1 != fp3
    analysis = {"ok": True, "one_sentence": "x", "source_fingerprint": fp1}
    assert lection_connection_analysis_is_stale(analysis, current_fingerprint=fp2)
    assert not lection_connection_analysis_is_stale(analysis, current_fingerprint=fp1)


def test_save_reload_preserves_analysis(session):
    result = analyze_lection_textus_link(
        passage="Júd 17–20",
        passage_text="…",
        lection_reference="Ézs 40,1–11",
        generate_fn=stub_json(_strong_ot_for_nt_payload()),
    )
    save_lection_connection_analysis(session, result.to_dict())
    project = build_project_data(session)
    cleaned = sanitize_project_data(project)
    restored = normalize_sermon_workshop(cleaned.get(SERMON_WORKSHOP_KEY))
    analysis = restored.get("lection_connection_analysis")
    assert isinstance(analysis, dict)
    assert analysis.get("one_sentence")
    assert analysis.get("source_fingerprint")
    assert analysis.get("lection_reference") == "Ézs 40,1–11"


def test_suggestion_payload_can_carry_analysis(session):
    """AI-javaslat részeként tárolható a kapcsolati elemzés."""
    analysis = analyze_lection_textus_link(
        passage="Júd 17–20",
        passage_text="…",
        lection_reference="Jn 15,1–11",
        generate_fn=stub_json(_strong_ot_for_nt_payload()),
    )
    save_lection_suggestions(
        session,
        {
            "recommended_lection": {"reference": "Jn 15,1–11"},
            "connection_analysis": analysis.to_dict(),
            "ok": True,
        },
    )
    sug = session[SERMON_WORKSHOP_KEY]["lection_suggestions"]
    assert sug["connection_analysis"]["lection_reference"] == "Jn 15,1–11"
    # Átvétel a tartós mezőbe
    save_lection_connection_analysis(session, sug["connection_analysis"])
    assert session[SERMON_WORKSHOP_KEY]["lection_connection_analysis"]["ok"] is True


def test_ai_or_network_error():
    def boom(*_a, **_k):
        raise RuntimeError("network down")

    result = analyze_lection_textus_link(
        passage="Júd 17–20",
        passage_text="…",
        lection_reference="Jn 15",
        generate_fn=boom,
    )
    assert result.ok is False
    assert "nem készíthető" in result.error_message.casefold()

    def bad_json(*_a, **_k):
        return "ez nem json"

    result2 = analyze_lection_textus_link(
        passage="Júd 17–20",
        passage_text="…",
        lection_reference="Jn 15",
        generate_fn=bad_json,
    )
    assert result2.ok is False


def test_missing_inputs_do_not_call_generate():
    called = {"n": 0}

    def gen(*_a, **_k):
        called["n"] += 1
        return "{}"

    r1 = analyze_lection_textus_link(
        passage="", lection_reference="Jn 15", generate_fn=gen
    )
    r2 = analyze_lection_textus_link(
        passage="Júd 17–20", lection_reference="", generate_fn=gen
    )
    assert r1.ok is False and r2.ok is False
    assert called["n"] == 0


def test_normalize_empty_and_partial():
    assert normalize_lection_connection_analysis(None) is None
    assert normalize_lection_connection_analysis({}) is None
    partial = normalize_lection_connection_analysis(
        {
            "one_sentence": "Illik hozzá.",
            "connection_types": [{"type": "contrast", "rationale": "Ellentét."}],
            "key_links": [],
            "connection_strength": "moderate",
        }
    )
    assert partial is not None
    assert partial["one_sentence"] == "Illik hozzá."
    assert partial["connection_types"][0]["type"] == "contrast"


def test_default_workshop_has_analysis_slot():
    base = get_default_sermon_workshop()
    assert "lection_connection_analysis" in base
    assert base["lection_connection_analysis"] is None
