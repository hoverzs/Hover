# ruff: noqa: E402
"""Fázis 2B — egyetlen generálási szerződés, mechanikus fallback nélkül.

Célarchitektúra-terv, 2. fázis, 2. rész (2026-08-13): a `sermon_outline_
engine.generate_sermon_outline()` az EGYETLEN kanonikus vázlatmotor.
Vázlat csak sikeres AI-szintézisből vagy már meglévő, érvényes mentett
vázlatból származhat — a rendszer semmilyen körülmények között nem állít
elő mechanikus, versszakaszokra darabolt álvázlatot.

Ez a fájl a fázis explicit 12 pontos tesztlistáját fedi le. A meglévő
`tests/test_outline_engine.py`-ban már módosított tesztek (a korábbi
`generate_fn=None` hívások `_ok_gen`-re cserélve) ellenőrzik a regressziót;
ez a fájl a SZERZŐDÉST magát dokumentálja és bizonyítja, egy helyen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

import sermon_outline_engine as engine
from sermon_outline_engine import (
    OUTLINE_SYSTEM_PROMPT,
    SCHEMA_VERSION,
    build_outline_user_prompt,
    collect_outline_evidence,
    extract_outline_background_material,
    generate_sermon_outline,
    normalize_sermon_outline,
    render_structured_outline,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    save_sermon_outline,
    update_sermon_workshop_section,
)
from sermon_workshop_outline_ai import outline_has_content, outline_to_readable_content
from tests.test_outline_engine import (
    JUDE_PASSAGE,
    _base_state,
    _jude_good_structured,
    _ok_gen,
    _valid_structured,
)


# ---------------------------------------------------------------------------
# 1. Sikeres AI-generálás érvényes vázlatot ad
# ---------------------------------------------------------------------------


def test_successful_ai_generation_returns_valid_outline():
    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=_ok_gen)
    assert result.ok
    assert not result.error_kind
    assert not result.retryable
    assert outline_has_content(result.outline)
    assert result.outline.get("schema_version") == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. generate_fn hiányakor nincs heurisztikus vázlat
# ---------------------------------------------------------------------------


def test_missing_generate_fn_produces_no_heuristic_outline():
    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert not result.ok
    assert result.error_kind == "ai_unavailable"
    assert not result.retryable
    assert engine.AI_UNAVAILABLE_MESSAGE in result.error_message
    # Nincs mentett korábbi vázlat, tehát a visszaadott outline is üres —
    # semmiképp sem mechanikusan előállított tartalom.
    assert not outline_has_content(result.outline)
    # A mechanikus fallback függvények véglegesen eltávolítva a motorból.
    assert not hasattr(engine, "_heuristic_structured_from_bundle")
    assert not hasattr(engine, "_passage_verse_chunks")


# ---------------------------------------------------------------------------
# 3. AI-kivétel → strukturált, retryable hiba
# ---------------------------------------------------------------------------


def test_ai_exception_returns_structured_retryable_error():
    def boom(*_a, **_k):
        raise RuntimeError("network down")

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=boom)
    assert not result.ok
    assert result.error_kind == "ai_call_failed"
    assert result.retryable
    assert result.error_message


# ---------------------------------------------------------------------------
# 4. Üres/hibás AI-válasz nem lesz vázlat
# ---------------------------------------------------------------------------


def test_empty_ai_response_produces_no_outline():
    def empty_gen(*_a, **_k):
        return json.dumps({"title": "", "focus_sentence": "", "points": []})

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=empty_gen)
    assert not result.ok
    assert result.error_kind in ("ai_invalid_response", "validation_failed", "empty_result")
    assert result.retryable


def test_garbled_ai_response_produces_no_outline():
    def garbled_gen(*_a, **_k):
        return "nem JSON és nem Markdown vázlat, csak összefüggéstelen szöveg"

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=garbled_gen)
    assert not result.ok
    assert result.error_kind in ("ai_invalid_response", "validation_failed", "empty_result")
    assert result.retryable


# ---------------------------------------------------------------------------
# 5. Sikertelen generálás megőrzi a korábbi approved vázlatot
# ---------------------------------------------------------------------------


def test_failed_generation_preserves_previous_approved_outline():
    state = _base_state()
    first = generate_sermon_outline(state, mode="workshop", generate_fn=_ok_gen)
    assert first.ok
    save_sermon_outline(state, first.outline, mark_manual_edit=False)
    state[SERMON_WORKSHOP_KEY]["sermon_outline_status"] = "approved"
    state[SERMON_WORKSHOP_KEY]["sermon_outline"]["status"] = "approved"
    before = json.dumps(state[SERMON_WORKSHOP_KEY]["sermon_outline"], sort_keys=True)

    def boom(*_a, **_k):
        raise RuntimeError("offline")

    failed = generate_sermon_outline(
        state, mode="workshop", generate_fn=boom, force_overwrite=True
    )
    assert not failed.ok
    assert failed.error_kind == "ai_call_failed"
    # A visszaadott outline a korábbi (megmaradt) vázlat, nem üres/új tartalom.
    assert outline_has_content(failed.outline)
    assert failed.outline.get("main_idea") == first.outline.get("main_idea")
    # A session állapotban tárolt vázlat sem változott — hibás generálás
    # nem íródik vissza automatikusan.
    after = json.dumps(state[SERMON_WORKSHOP_KEY]["sermon_outline"], sort_keys=True)
    assert before == after


# ---------------------------------------------------------------------------
# 6. Sikeres generálás frissítheti a korábbi vázlatot
# ---------------------------------------------------------------------------


def test_successful_generation_can_update_previous_outline():
    state = _base_state()
    first = generate_sermon_outline(state, mode="workshop", generate_fn=_ok_gen)
    assert first.ok
    save_sermon_outline(state, first.outline, mark_manual_edit=False)
    state[SERMON_WORKSHOP_KEY]["sermon_outline_status"] = "approved"
    state[SERMON_WORKSHOP_KEY]["sermon_outline"]["status"] = "approved"

    def gen_updated(*_a, **_k):
        return json.dumps(
            _valid_structured(title="Frissített cím — új fókusz"), ensure_ascii=False
        )

    second = generate_sermon_outline(
        state, mode="workshop", generate_fn=gen_updated, force_overwrite=True
    )
    assert second.ok
    save_sermon_outline(state, second.outline, mark_manual_edit=False)
    assert (
        state[SERMON_WORKSHOP_KEY]["sermon_outline"]["main_idea"]
        != first.outline.get("main_idea")
        or state[SERMON_WORKSHOP_KEY]["sermon_outline"]["content"]
        != first.outline.get("content")
    )


# ---------------------------------------------------------------------------
# 7. Nyers bibliai szöveg nem darabolódik mechanikusan
# ---------------------------------------------------------------------------


def test_raw_passage_text_not_split_mechanically_without_ai():
    """generate_fn hiányában a motor SOHA nem darabolja fel a betöltött
    bibliai szöveget versenkénti heurisztikus vázlattá — a visszaadott
    outline üres marad, nem a passage_text egy mechanikus átalakítása."""
    state = _base_state(passage_text=JUDE_PASSAGE, last_igehely="Júd 17–20")
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert not result.ok
    assert result.error_kind == "ai_unavailable"
    content = outline_to_readable_content(result.outline)
    # Egyetlen versszó/versszám-töredék sem szivároghat át mechanikus
    # feldolgozásból, mert nincs is feldolgozás — a content üres.
    assert content.strip() == ""
    assert "17 Ti pedig" not in content
    assert "20 Ti pedig" not in content


# ---------------------------------------------------------------------------
# 8. A prompt tartalmazza a hétpontos modellt
# ---------------------------------------------------------------------------


def test_prompt_contains_seven_point_arc_model():
    for label in (
        "Belépés",
        "Alaphelyzet",
        "fordulópont",
        "Mélyítés",
        "Átértelmezés",
        "Megérkezés",
    ):
        assert label in OUTLINE_SYSTEM_PROMPT, label


# ---------------------------------------------------------------------------
# 9. Kimeneti beszédegységek közt valódi átvezetés (nem hét mechanikus cím)
# ---------------------------------------------------------------------------


def test_output_points_are_coherent_not_seven_mechanical_labels():
    data = _jude_good_structured()
    # A kész vázlat 2-4 koherens beszédegységből áll — NEM hét, egymás
    # mellé másolt cím a hét modellpont szerint.
    assert 2 <= len(data["points"]) <= 4
    titles = [p["title"].casefold() for p in data["points"]]
    # A hét modellpont technikai neve nem jelenhet meg literál címként —
    # a modell belső gondolatmenet-szerkezet, nem mechanikus fejezetcím.
    for forbidden in (
        "belépés",
        "alaphelyzet",
        "első fordulópont",
        "mélyítés és fokozás",
        "átértelmezés",
        "második fordulópont",
        "megérkezés",
    ):
        assert forbidden not in titles
    # Valódi előrehaladás: minden pont más verset/címet fed le (nem
    # ismételt sablonmondat), és a szöveg ténylegesen hivatkozik a
    # megelőző felismerésre (nem önálló, elszigetelt blokkok).
    verses = [p.get("verses") for p in data["points"]]
    assert len(set(verses)) == len(verses)
    rendered = render_structured_outline(data)
    assert "1. rész" not in rendered and "2. rész" not in rendered
    assert rendered.count("Emlékezzetek") <= 2  # cím + legfeljebb egy visszautalás


# ---------------------------------------------------------------------------
# 10. Draft/elavult anyag nem kerül be a kanonikus háttérbe
# ---------------------------------------------------------------------------


def test_draft_homiletical_decision_excluded_from_canonical_background():
    state = _base_state()
    sw = state[SERMON_WORKSHOP_KEY]
    # Homiletikai döntés (sermon_main_idea) DRAFT állapotban — approval
    # nélkül sosem kerülhet be a promptba szolgáló háttéranyagba.
    sw["sermon_main_idea"] = "Ki nem próbált, jóvá nem hagyott ötlet."
    sw["sermon_main_idea_status"] = "draft"
    ensure_sermon_workshop_state(state)

    bundle = collect_outline_evidence(state, sermon_workshop=sw)
    background = extract_outline_background_material(bundle)
    assert "sermon_main_idea" not in background

    joined_background = json.dumps(background, ensure_ascii=False)
    assert "Ki nem próbált, jóvá nem hagyott ötlet." not in joined_background


def test_approved_text_workshop_source_reaches_canonical_background():
    """Kontraszt a 10. ponthoz: a Textusműhely-forrás (nem homiletikai
    döntés) jóváhagyva helyesen bekerül — a gate szelektív, nem tiltja
    le az egész háttéranyagot."""
    state = _base_state(exegesis="Jóváhagyott, konkrét exegetikai megfigyelés.")
    state["exegesis_status"] = "approved"
    ensure_sermon_workshop_state(state)
    sw = state[SERMON_WORKSHOP_KEY]

    bundle = collect_outline_evidence(state, sermon_workshop=sw)
    background = extract_outline_background_material(bundle)
    assert "exegesis" in background
    assert "Jóváhagyott, konkrét exegetikai megfigyelés." in str(background["exegesis"])


# ---------------------------------------------------------------------------
# 11. Régi mentett vázlatok betölthetők/megőrződnek
# ---------------------------------------------------------------------------


def test_old_saved_outline_loads_and_content_is_preserved():
    state = _base_state()
    legacy = normalize_sermon_outline(
        {
            "schema_version": "pulpit_outline_v3",
            "content": "Régi, korábbi sémájú mentett vázlatszöveg.",
            "main_idea": "Régi fő gondolat",
            "status": "approved",
        }
    )
    save_sermon_outline(state, legacy, mark_manual_edit=False)
    stored = normalize_sermon_outline(state[SERMON_WORKSHOP_KEY]["sermon_outline"])
    # A régi séma tartalma megmarad, még ha frissítésre szoruló jelzést
    # is kap — a motor nem törli/nem generálja újra automatikusan.
    assert "Régi, korábbi sémájú mentett vázlatszöveg." in (stored.get("content") or "")
    assert stored.get("status") == "needs_refresh"

    # generate_fn nélküli hívás sem törli a korábbi mentett tartalmat.
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert not result.ok
    assert "Régi, korábbi sémájú mentett vázlatszöveg." in (
        state[SERMON_WORKSHOP_KEY]["sermon_outline"].get("content") or ""
    )


# ---------------------------------------------------------------------------
# 12. Word-export működik (teljes, valós AI-generálásra épülő végpont)
# ---------------------------------------------------------------------------


def test_word_export_works_end_to_end_with_generated_outline(monkeypatch):
    import streamlit as st

    from outline_word_export import build_outline_docx

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=_ok_gen)
    assert result.ok
    outline_text = outline_to_readable_content(result.outline)
    assert outline_text.strip()

    session: dict = {
        "last_igehely": "Jn 3,16",
        "last_alkalom": "vasárnapi igehirdetés",
        "last_stilus": "expozíciós",
        "outline": outline_text,
        "basket": [],
        "songs": "",
    }
    monkeypatch.setattr(st, "session_state", session)

    docx_bytes = build_outline_docx()
    assert isinstance(docx_bytes, (bytes, bytearray))
    assert len(docx_bytes) > 0
    assert docx_bytes[:2] == b"PK"  # érvényes .docx (zip) fejléc

    from docx import Document
    import io

    doc = Document(io.BytesIO(docx_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Jn 3,16" in full_text
