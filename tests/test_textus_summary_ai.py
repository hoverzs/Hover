"""RESET 3B-2 — az "Eredeti szöveg" (original_text) bekötése a
Textusösszegzés (text_summary) szintézisébe.

`textus_summary_ai.py` korábban NEM rendelkezett dedikált tesztfájllal
(csak a modul saját `_self_check()` smoke-tesztjével) — ez a fájl az
ELSŐ dedikált tesztfájl, elsősorban a RESET 3B-2-ben bevezetett
`original_text`/`original_text_is_fresh` szerződést fedi le.

A modul (`textus_summary_ai.py`) SZÁNDÉKOSAN nem fér hozzá
`st.session_state`-hez — minden teszt itt sima Python stringekkel/
booleanokkel dolgozik, hálózat/API-hívás nélkül (`generate_fn` mindig
mock vagy egyáltalán nincs átadva).
"""

from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import textus_summary_ai as summary_ai  # noqa: E402

PASSAGE = "Jn 3,16"
PASSAGE_TEXT = "Mert úgy szerette Isten a világot."


# =============================================================================
# 1-3. `original_text` a context builderben — friss / hiányzó / stale
# =============================================================================


def test_1_fresh_original_text_enters_context():
    ctx = summary_ai.build_summary_context(
        passage=PASSAGE,
        passage_text=PASSAGE_TEXT,
        exegesis="RAW_EXEGESIS_SENTINEL",
        original_text="ORIGINAL_TEXT_SENTINEL",
        original_text_is_fresh=True,
    )
    assert ctx["original_text"] == "ORIGINAL_TEXT_SENTINEL"


def test_2_missing_original_text_leaves_existing_behavior_unchanged():
    """`original_text` paraméter nélkül (alapérték "" + `is_fresh=True`)
    a context pontosan úgy néz ki, mint RESET 3B-2 előtt — a mező
    "nincs adat"-ot kap, minden más mező változatlan."""
    ctx_without = summary_ai.build_summary_context(
        passage=PASSAGE,
        passage_text=PASSAGE_TEXT,
        exegesis="RAW_EXEGESIS_SENTINEL",
        theology="RAW_THEOLOGY_SENTINEL",
    )
    assert ctx_without["original_text"] == summary_ai.MISSING
    assert ctx_without["exegesis"] == "RAW_EXEGESIS_SENTINEL"
    assert ctx_without["theology"] == "RAW_THEOLOGY_SENTINEL"
    assert ctx_without["passage"] == PASSAGE
    assert ctx_without["passage_text"] == PASSAGE_TEXT


def test_3_stale_original_text_is_excluded_from_context():
    ctx = summary_ai.build_summary_context(
        passage=PASSAGE,
        passage_text=PASSAGE_TEXT,
        original_text="ORIGINAL_TEXT_SENTINEL",
        original_text_is_fresh=False,
    )
    assert ctx["original_text"] == summary_ai.MISSING
    prompt = summary_ai.build_summary_suggest_prompt(ctx)
    assert "ORIGINAL_TEXT_SENTINEL" not in prompt


# =============================================================================
# 4. A prompt explicit tartalmazza a grounding-tilalmat
# =============================================================================


def test_4_prompt_forbids_inventing_new_original_language_data():
    assert (
        "SOHA ne találj ki, ne egészíts ki és ne pontosíts saját "
        "emlékezetből új lemmát, morfológiai vagy lexikai adatot"
        in summary_ai._SUGGEST_PROMPT_TEMPLATE
    )
    assert "Nem a te feladatod új nyelvi elemzést végezni" in summary_ai._SUGGEST_PROMPT_TEMPLATE
    assert "{{original_text}}" in summary_ai._SUGGEST_PROMPT_TEMPLATE


# =============================================================================
# 5. Releváns original-text insight a promptban ténylegesen elérhető a
#    key_exegetical_findings mező számára (a MECHANIZMUS helyessége —
#    az AI tényleges viselkedése nem unit-tesztelhető)
# =============================================================================


def test_5_prompt_instructs_key_exegetical_findings_to_absorb_relevant_insight():
    assert (
        "Ha az alább mellékelt eredeti nyelvi megfigyelések között van "
        "olyan, ami TÉNYLEGESEN segíti a szakasz értelmezését"
        in summary_ai._SUGGEST_PROMPT_TEMPLATE
    )
    ctx = summary_ai.build_summary_context(
        passage=PASSAGE,
        passage_text=PASSAGE_TEXT,
        original_text="ORIGINAL_TEXT_SENTINEL",
        original_text_is_fresh=True,
    )
    prompt = summary_ai.build_summary_suggest_prompt(ctx)
    assert "ORIGINAL_TEXT_SENTINEL" in prompt
    # A promptban a key_exegetical_findings leírása és az eredeti nyelvi
    # blokk is szerepel -- a modellnek van honnan összekötnie a kettőt.
    assert "key_exegetical_findings" in prompt


def test_5_prompt_allows_skipping_when_not_relevant():
    assert (
        "Ha nincs ilyen releváns eredeti nyelvi megfigyelés, egyszerűen "
        "hagyd ki" in summary_ai._SUGGEST_PROMPT_TEMPLATE
    )


# =============================================================================
# 6. Nincs kötelező original-language output
# =============================================================================


def test_6_original_text_is_not_a_required_source_for_sufficient_material():
    """`original_text` egyedül NEM elég ahhoz, hogy a szintézis
    "elégséges anyagnak" minősüljön -- csak kiegészítő forrás, ahogy a
    kortörténet is (`historical_context`) a meglévő szerződés szerint."""
    ctx = summary_ai.build_summary_context(
        passage=PASSAGE,
        original_text="ORIGINAL_TEXT_SENTINEL",
        original_text_is_fresh=True,
    )
    assert not summary_ai.has_sufficient_summary_material(ctx)
    assert "original_text" not in dict(summary_ai._SUGGEST_SOURCE_KEYS)


# =============================================================================
# 7. A summary response schema nem változott
# =============================================================================


def test_7_response_schema_unchanged_no_new_field_introduced():
    field_names = {f.name for f in fields(summary_ai.TextSummarySuggestionResult)}
    assert field_names == {
        "base_tension",
        "key_exegetical_findings",
        "theological_emphases",
        "genre_structure_notes",
        "reasoning_summary",
        "warnings",
        "missing_information",
        "ok",
        "error_message",
        "raw_response",
    }
    # Nincs semmilyen "original_language"-szerű új mező.
    assert not any("original" in name for name in field_names)


def test_7_parse_summary_suggestion_still_only_reads_the_four_fields():
    import json

    raw = json.dumps(
        {
            "base_tension": "BT",
            "key_exegetical_findings": "KF, eredeti nyelvi megfigyeléssel összefonva.",
            "theological_emphases": "TE",
            "genre_structure_notes": "GS",
            "reasoning_summary": "Ok.",
            "warnings": [],
            "missing_information": [],
        },
        ensure_ascii=False,
    )
    result = summary_ai.parse_summary_suggestion(raw)
    assert result.ok is True
    assert result.key_exegetical_findings == "KF, eredeti nyelvi megfigyeléssel összefonva."


# =============================================================================
# 8. Suggest_text_summary végponton át is működik az original_text
#    átadás/szűrés
# =============================================================================


def test_8_suggest_text_summary_passes_fresh_original_text_through_to_prompt():
    captured: dict = {}

    def fake_gen(prompt: str, **kwargs):
        captured["prompt"] = prompt
        return (
            '{"base_tension":"BT","key_exegetical_findings":"KF",'
            '"theological_emphases":"TE","genre_structure_notes":"GS",'
            '"reasoning_summary":"ok.","warnings":[],"missing_information":[]}'
        )

    result = summary_ai.suggest_text_summary(
        passage=PASSAGE,
        passage_text=PASSAGE_TEXT,
        exegesis="RAW_EXEGESIS_SENTINEL",
        original_text="ORIGINAL_TEXT_SENTINEL",
        original_text_is_fresh=True,
        generate_fn=fake_gen,
    )
    assert result.ok is True
    assert "ORIGINAL_TEXT_SENTINEL" in captured["prompt"]


def test_8_suggest_text_summary_excludes_stale_original_text_from_prompt():
    captured: dict = {}

    def fake_gen(prompt: str, **kwargs):
        captured["prompt"] = prompt
        return (
            '{"base_tension":"BT","key_exegetical_findings":"KF",'
            '"theological_emphases":"TE","genre_structure_notes":"GS",'
            '"reasoning_summary":"ok.","warnings":[],"missing_information":[]}'
        )

    summary_ai.suggest_text_summary(
        passage=PASSAGE,
        passage_text=PASSAGE_TEXT,
        exegesis="RAW_EXEGESIS_SENTINEL",
        original_text="ORIGINAL_TEXT_SENTINEL",
        original_text_is_fresh=False,
        generate_fn=fake_gen,
    )
    assert "ORIGINAL_TEXT_SENTINEL" not in captured["prompt"]


# =============================================================================
# Caller-szintű teszt: `textus_workshop_ui._original_text_is_fresh_for_
# summary()` — a MEGLÉVŐ `original_text_approved_context_hash`/
# `compute_current_passage_context_hash` kontraktus helyes felhasználása.
# Ez a helper `st.session_state`-et olvas, ezért AppTest-en keresztül.
# =============================================================================


def _render_fresh_original_text_probe() -> None:
    import streamlit as st

    import textus_workshop_ui as tw_ui
    from sermon_outline_engine import compute_current_passage_context_hash

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["original_text"] = "ORIGINAL_TEXT_SENTINEL"
    st.session_state["original_text_approved_context_hash"] = (
        compute_current_passage_context_hash(st.session_state)
    )
    st.session_state["_probe_result"] = tw_ui._original_text_is_fresh_for_summary()


def _render_stale_original_text_probe() -> None:
    import streamlit as st

    import textus_workshop_ui as tw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["original_text"] = "ORIGINAL_TEXT_SENTINEL"
    st.session_state["original_text_approved_context_hash"] = "STALE_HASH_MISMATCH"
    st.session_state["_probe_result"] = tw_ui._original_text_is_fresh_for_summary()


def _render_missing_hash_original_text_probe() -> None:
    import streamlit as st

    import textus_workshop_ui as tw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["original_text"] = "ORIGINAL_TEXT_SENTINEL"
    # Nincs mentett approved_context_hash -- régi projekt / soha nem
    # generált még a mechanizmus bevezetése előtt.
    st.session_state["_probe_result"] = tw_ui._original_text_is_fresh_for_summary()


def test_9_caller_freshness_helper_true_when_hash_matches_current_context():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_render_fresh_original_text_probe).run(timeout=60)
    assert not app.exception
    assert app.session_state["_probe_result"] is True


def test_9_caller_freshness_helper_false_when_hash_is_stale():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_render_stale_original_text_probe).run(timeout=60)
    assert not app.exception
    assert app.session_state["_probe_result"] is False


def test_9_caller_freshness_helper_true_when_no_stored_hash():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_render_missing_hash_original_text_probe).run(timeout=60)
    assert not app.exception
    assert app.session_state["_probe_result"] is True
