"""RESET 3B-4c — a meglévő, forrásolt `biblical_places` adatbázis szűk
connectora a kortörténet ("history") szekció "Földrajzi és régészeti
háttér" alcíméhez.

A connector (`app.py::build_biblical_place_history_context`) KIZÁRÓLAG
`ancient_geography` / `historical_context` / `archaeology` szakaszt ad
tovább, csak `review_status == "source_backed"` ÉS `confidence in
{"high", "medium"}` esetén, legfeljebb 2 helyszínről, a
`find_place_links_for_passage()` meglévő determinisztikus sorrendjében.
Ha nincs kvalifikáló tartalom, a connector üres stringet ad vissza, és a
blokk teljesen kimarad a promptból (nincs "nincs adat" placeholder) — ld.
RESET 3B-4b audit: ez a valós adaton ma a tipikus eset.

FONTOS TESZTINFRASTRUKTÚRA-MEGJEGYZÉS — ugyanaz a korlátozás, mint a
`tests/test_original_language_token_block.py`-ban és `tests/test_
exegesis_original_language_grounding.py`-ban dokumentálva: `app.py`
importálása a FŐ pytest-folyamatban korrumpálja a Streamlit globális
DeltaGenerator-állapotát. Ezért két különálló alfolyamat-mintát
használunk:

  1. `_CONNECTOR_RESULTS` — bare `python -c` alfolyamat (nincs szükség
     `st.session_state`-re, a connector sima string paramétert kap) —
     ez futtatja a valós-adatos ÉS a monkeypatch-elt mock-adatos
     eseteket is (`app.find_place_links_for_passage` / `app.
     get_place_enrichment` felülírásával, mert azok modulszintű nevek
     az `app` modulban).
  2. `_run_prompt_worker(igehely)` — AppTest-alapú alfolyamat, VALÓDI
     ideiglenes .py fájlon keresztül (mert `AppTest.from_function`
     nem tud forrást olvasni `python -c` inline szkriptből) — ez a
     `build_alap_from_state` / `SECTION_PROMPTS` integrációt teszteli,
     ahol `st.session_state["last_igehely"]`-re van szükség.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# =============================================================================
# 1. Worker — bare alfolyamat: valós adat + monkeypatch-elt mock adat
# =============================================================================

_CONNECTOR_WORKER_SCRIPT = '''
import json
import sys

sys.path.insert(0, __ROOT__)

import app
from biblical_place_enrichment import (
    EnrichmentKeyEvent,
    EnrichmentKeyEventsSection,
    EnrichmentTextSection,
    PlaceEnrichment,
)


def _text_section(text, *, review_status="source_backed", confidence="high"):
    return EnrichmentTextSection(
        text_hu=text, source_ids=(), confidence=confidence, review_status=review_status
    )


def _enrichment(place_id, sections):
    return PlaceEnrichment(
        place_id=place_id,
        profile_tier="basic",
        content_version=1,
        sections=sections,
        related_route_ids=(),
        editorial_notes_hu=None,
        overall_review_status="source_backed",
    )


class _FakeLink:
    def __init__(self, place_id):
        self.place_id = place_id


result = {}

# --- 1-3. Valós adat: Korinthus (ApCsel 18,1-18) -----------------------
result["corinth_block"] = app.build_biblical_place_history_context("ApCsel 18,1-18")

# --- 7. Nincs place-link -------------------------------------------------
result["no_link_block"] = app.build_biblical_place_history_context("Jn 3,16")

# --- 8. Van place-link, de nincs kvalifikáló szakasz (1Móz 12,1-9: csak
#        shechem/bethel_1, egyiknek sincs ancient_geography/historical_
#        context/archaeology szakasza -- ld. RESET 3B-4b audit) ---------
result["no_qualifying_block"] = app.build_biblical_place_history_context("1Moz 12,1-9")

# --- Mock-adatos esetek: monkeypatch app modulszintu neveit -------------
_real_find_links = app.find_place_links_for_passage
_real_get_enrichment = app.get_place_enrichment

# 4. needs_review kizarva
app.find_place_links_for_passage = lambda ref: (_FakeLink("mock_needs_review"),)
app.get_place_enrichment = lambda pid: _enrichment(
    "mock_needs_review",
    {"historical_context": _text_section("MOCK_NEEDS_REVIEW_TEXT", review_status="needs_review")},
)
result["needs_review_block"] = app.build_biblical_place_history_context("X 1,1")

# 5. confidence=low kizarva
app.find_place_links_for_passage = lambda ref: (_FakeLink("mock_low_conf"),)
app.get_place_enrichment = lambda pid: _enrichment(
    "mock_low_conf",
    {"archaeology": _text_section("MOCK_LOW_CONFIDENCE_TEXT", confidence="low")},
)
result["low_confidence_block"] = app.build_biblical_place_history_context("X 1,1")

# 6a. confidence=high bekerul
app.find_place_links_for_passage = lambda ref: (_FakeLink("mock_high_conf"),)
app.get_place_enrichment = lambda pid: _enrichment(
    "mock_high_conf",
    {"ancient_geography": _text_section("MOCK_HIGH_CONFIDENCE_TEXT", confidence="high")},
)
result["high_confidence_block"] = app.build_biblical_place_history_context("X 1,1")

# 6b. confidence=medium bekerul
app.find_place_links_for_passage = lambda ref: (_FakeLink("mock_medium_conf"),)
app.get_place_enrichment = lambda pid: _enrichment(
    "mock_medium_conf",
    {"historical_context": _text_section("MOCK_MEDIUM_CONFIDENCE_TEXT", confidence="medium")},
)
result["medium_confidence_block"] = app.build_biblical_place_history_context("X 1,1")

# 9-10. 3+ kvalifikalo hely eseten csak az elso 2 kerul be, determinisztikusan
_mock_enrichments = {
    "mock_a": _enrichment(
        "mock_a", {"historical_context": _text_section("MOCK_TEXT_PLACE_A")}
    ),
    "mock_b": _enrichment(
        "mock_b", {"archaeology": _text_section("MOCK_TEXT_PLACE_B", confidence="medium")}
    ),
    "mock_c": _enrichment(
        "mock_c", {"ancient_geography": _text_section("MOCK_TEXT_PLACE_C")}
    ),
}
app.find_place_links_for_passage = lambda ref: (
    _FakeLink("mock_a"),
    _FakeLink("mock_b"),
    _FakeLink("mock_c"),
)
app.get_place_enrichment = lambda pid: _mock_enrichments.get(pid)
result["cap_block_run1"] = app.build_biblical_place_history_context("X 1,1")
result["cap_block_run2"] = app.build_biblical_place_history_context("X 1,1")

# 11. key_events nem kerul be (meg akkor sem, ha az az EGYETLEN szakasz)
app.find_place_links_for_passage = lambda ref: (_FakeLink("mock_key_events_only"),)
app.get_place_enrichment = lambda pid: _enrichment(
    "mock_key_events_only",
    {
        "key_events": EnrichmentKeyEventsSection(
            items=(
                EnrichmentKeyEvent(
                    summary_hu="MOCK_KEY_EVENT_SHOULD_NOT_APPEAR",
                    passage_refs=("X 1,1",),
                    source_ids=(),
                ),
            ),
            confidence="high",
            review_status="source_backed",
        )
    },
)
result["key_events_only_block"] = app.build_biblical_place_history_context("X 1,1")

# 12. homiletical_context nem kerul be, meg akkor sem, ha VAN masik
#     kvalifikalo (tovabbitando) szakasz ugyanannal a helynel
app.find_place_links_for_passage = lambda ref: (_FakeLink("mock_with_homiletical"),)
app.get_place_enrichment = lambda pid: _enrichment(
    "mock_with_homiletical",
    {
        "historical_context": _text_section("MOCK_HIST_WITH_HOMILETICAL_SIBLING"),
        "homiletical_context": _text_section("MOCK_HOMILETICAL_SHOULD_NOT_APPEAR"),
    },
)
result["homiletical_context_block"] = app.build_biblical_place_history_context("X 1,1")

app.find_place_links_for_passage = _real_find_links
app.get_place_enrichment = _real_get_enrichment

with open(__OUT_PATH__, "w", encoding="utf-8") as f:
    json.dump(result, f)
'''


def _load_connector_results() -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        script = _CONNECTOR_WORKER_SCRIPT.replace("__ROOT__", repr(str(ROOT))).replace(
            "__OUT_PATH__", repr(str(out_path))
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"worker alfolyamat-hiba:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
        return json.loads(out_path.read_text(encoding="utf-8"))


_R = _load_connector_results()


# =============================================================================
# 1-3. Valós adat: Korinthus
# =============================================================================


def test_1_corinth_found_for_acts_18():
    assert "Korinthus" in _R["corinth_block"]
    assert "FORRÁSOLT FÖLDRAJZI/RÉGÉSZETI HÁTTÉR" in _R["corinth_block"]


def test_2_corinth_qualifying_sections_included():
    block = _R["corinth_block"]
    assert "Peloponnészosz" in block  # ancient_geography
    assert "neolitikus" in block  # historical_context
    assert "fórum" in block  # archaeology


def test_3_source_institution_attribution_preserved():
    block = _R["corinth_block"]
    assert "American School of Classical Studies at Athens" in block
    assert "Hellenic Ministry of Culture" in block
    # Nyers URL NEM kerulhet a promptba.
    assert "http" not in block


# =============================================================================
# 4-6. Filtering
# =============================================================================


def test_4_needs_review_section_excluded():
    assert _R["needs_review_block"] == ""


def test_5_low_confidence_section_excluded():
    assert _R["low_confidence_block"] == ""


def test_6_high_and_medium_confidence_included():
    assert "MOCK_HIGH_CONFIDENCE_TEXT" in _R["high_confidence_block"]
    assert "MOCK_MEDIUM_CONFIDENCE_TEXT" in _R["medium_confidence_block"]


# =============================================================================
# 7-8. Fallback -- ures connector
# =============================================================================


def test_7_no_place_link_yields_empty_connector():
    assert _R["no_link_block"] == ""


def test_8_place_link_without_qualifying_section_yields_empty_connector():
    assert _R["no_qualifying_block"] == ""


# =============================================================================
# 9-10. Max. 2 helyszin, determinisztikus sorrend
# =============================================================================


def test_9_only_first_two_qualifying_places_included():
    block = _R["cap_block_run1"]
    assert "MOCK_TEXT_PLACE_A" in block
    assert "MOCK_TEXT_PLACE_B" in block
    assert "MOCK_TEXT_PLACE_C" not in block


def test_10_order_is_deterministic_across_calls():
    assert _R["cap_block_run1"] == _R["cap_block_run2"]
    pos_a = _R["cap_block_run1"].index("MOCK_TEXT_PLACE_A")
    pos_b = _R["cap_block_run1"].index("MOCK_TEXT_PLACE_B")
    assert pos_a < pos_b


# =============================================================================
# 11-12. Felelossegi hatar -- key_events / homiletical_context kizarva
# =============================================================================


def test_11_key_events_never_included():
    assert _R["key_events_only_block"] == ""


def test_12_homiletical_context_never_included():
    block = _R["homiletical_context_block"]
    assert "MOCK_HIST_WITH_HOMILETICAL_SIBLING" in block
    assert "MOCK_HOMILETICAL_SHOULD_NOT_APPEAR" not in block


# =============================================================================
# 13-16. Prompt-integracio -- AppTest-alapu worker
# =============================================================================

_PROMPT_WORKER_TEMPLATE = '''
import json
import sys

sys.path.insert(0, __ROOT__)

from streamlit.testing.v1 import AppTest


def _render():
    import streamlit as st
    from app import SECTION_PROMPTS, build_alap_from_state

    st.session_state["last_igehely"] = __IGEHELY__
    st.session_state["bible_translation"] = ""
    st.session_state["passage_text"] = __PASSAGE_TEXT__

    alap_history_with_places = build_alap_from_state(include_biblical_place_context=True)
    alap_history_without_places = build_alap_from_state(include_biblical_place_context=False)
    alap_exegesis = build_alap_from_state(include_original_language_tokens=True)
    alap_theology = build_alap_from_state()
    alap_overview = build_alap_from_state(include_pastoral_context=True)
    alap_actualization = build_alap_from_state(include_pastoral_context=True)

    result = {
        "history_prompt_with_places": SECTION_PROMPTS["history"].format(alap=alap_history_with_places),
        "history_prompt_without_places": SECTION_PROMPTS["history"].format(alap=alap_history_without_places),
        "exegesis_prompt": SECTION_PROMPTS["exegesis"].format(alap=alap_exegesis),
        "theology_prompt": SECTION_PROMPTS["theology"].format(alap=alap_theology),
        "overview_prompt": SECTION_PROMPTS["overview"].format(alap=alap_overview),
        "actualization_prompt": SECTION_PROMPTS["actualization"].format(alap=alap_actualization),
    }
    st.session_state["_worker_result"] = result


app_test = AppTest.from_function(_render).run(timeout=60)
worker_result = app_test.session_state["_worker_result"]

with open(__OUT_PATH__, "w", encoding="utf-8") as f:
    json.dump(worker_result, f)
'''


def _run_prompt_worker(*, igehely: str, passage_text: str = "") -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        worker_path = Path(tmp_dir) / "worker.py"
        script = (
            _PROMPT_WORKER_TEMPLATE.replace("__ROOT__", repr(str(ROOT)))
            .replace("__IGEHELY__", repr(igehely))
            .replace("__PASSAGE_TEXT__", repr(passage_text))
            .replace("__OUT_PATH__", repr(str(out_path)))
        )
        worker_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(worker_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"worker alfolyamat-hiba ({igehely!r}):\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
        return json.loads(out_path.read_text(encoding="utf-8"))


_WITH_DATA = _run_prompt_worker(
    igehely="ApCsel 18,1-18", passage_text="Pál Korinthusba érkezett."
)
_WITHOUT_DATA = _run_prompt_worker(igehely="Jn 3,16", passage_text="Mert úgy szerette Isten a világot.")


def test_13_history_prompt_gets_block_only_when_connector_non_empty():
    assert "FORRÁSOLT FÖLDRAJZI/RÉGÉSZETI HÁTTÉR" in _WITH_DATA["history_prompt_with_places"]
    # Ugyanahhoz az igehelyhez, de a flag kikapcsolva -- nincs blokk.
    assert "FORRÁSOLT FÖLDRAJZI/RÉGÉSZETI HÁTTÉR" not in _WITH_DATA["history_prompt_without_places"]
    # Olyan igehelyhez, aminek nincs kvalifikáló connector-tartalma, a
    # flag bekapcsolva sem hoz létre blokkot.
    assert "FORRÁSOLT FÖLDRAJZI/RÉGÉSZETI HÁTTÉR" not in _WITHOUT_DATA["history_prompt_with_places"]


def test_14_partial_grounding_disclaimer_always_present_when_block_exists():
    prompt = _WITH_DATA["history_prompt_with_places"]
    assert "KIZÁRÓLAG az" in prompt
    assert "TÖBBI RÉSZE továbbra is" in prompt
    assert "Ne sugalld, hogy a teljes válasz forrásolt." in prompt


def test_15_connector_block_does_not_leak_into_other_sections():
    for key in ("exegesis_prompt", "theology_prompt", "overview_prompt", "actualization_prompt"):
        assert "FORRÁSOLT FÖLDRAJZI/RÉGÉSZETI HÁTTÉR" not in _WITH_DATA[key], key


def test_16_reset_3b4a_uncertainty_hardening_still_present():
    for prompt in (
        _WITH_DATA["history_prompt_with_places"],
        _WITH_DATA["history_prompt_without_places"],
        _WITHOUT_DATA["history_prompt_with_places"],
    ):
        assert (
            "A BIZONYTALANSÁG JELZÉSE NEM GYENGESÉG, HANEM KÖTELEZŐ SZAKMAI "
            "FEGYELEM" in prompt
        )
        assert "A hiányzó részlet MINDIG jobb" in prompt
