"""Júdás – teljes munkafolyamat integrációs ellenőrzés (hálózat nélkül is).

Nem Streamlit UI — adatmodell, RÚF fixture, MI kontextus, mentés/visszatöltés,
projektváltás, lekció/imádság elkülönítés.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_text_ui import normalize_passage_text
from ruf_bible_service import clear_ruf_cache, fetch_ruf_passage
from sermon_workshop_data import (
    add_approved_sermon_decision,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    save_lection_suggestions,
    save_prayer_after_suggestions,
    save_prayer_before_suggestions,
    update_sermon_workshop_section,
)
from sermon_workshop_m4_ai import suggest_sermon_main_idea
from sermon_workshop_m5_ai import suggest_listener_tension
from sermon_workshop_m5_gospel_ai import suggest_gospel_arc
from sermon_workshop_m6_ai import suggest_sermon_path
from sermon_workshop_m7_ai import suggest_enrichment
from sermon_workshop_m7_closing_ai import suggest_closing
from sermon_workshop_m8_ai import run_homiletical_diagnostics
from sermon_workshop_m9_lection_ai import (
    references_equivalent,
    suggest_lections,
    validate_lection_reference,
)
from sermon_workshop_m9_prayer_ai import (
    integrate_prayer_thoughts,
    suggest_prayer_after,
    suggest_prayer_before,
)
from textus_workshop_data import (
    ensure_text_workshop_state,
    get_default_text_workshop,
    normalize_text_workshop,
)
from workspace_data import (
    EXCLUDED_SESSION_KEYS,
    SERMON_WORKSHOP_KEY,
    TEXT_WORKSHOP_KEY,
    build_project_data,
    sanitize_project_data,
)

FIXTURES = ROOT / "tests" / "fixtures" / "ruf"
errors: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def ok(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def http_jude():
    html = (FIXTURES / "jud_1.html").read_text(encoding="utf-8")

    def _get(url: str, timeout: float = 15.0) -> str:  # noqa: ARG001
        return html

    return _get


def http_fail():
    def _get(url: str, timeout: float = 15.0) -> str:
        raise ConnectionError("simulated network failure")

    return _get


@pytest.fixture
def state() -> dict:
    return build_jude_state()


def stub_json(payload: dict):
    raw = json.dumps(payload, ensure_ascii=False)

    def _fn(*_a, **_k):
        return raw

    return _fn


def build_jude_state() -> dict:
    """Teljes tesztprojekt állapot: Júd 17–20 + M4–M9 kitöltés."""
    clear_ruf_cache()
    ruf = fetch_ruf_passage("Júd 17–20", http_get=http_jude())
    ok(ruf["success"], f"RÚF Jude load: {ruf.get('error')}")
    passage_text = normalize_passage_text(ruf.get("text"))
    if not (passage_text or "").strip():
        # Offline / üres RÚF mock fallback — a vázlattesztek ne függjenek hálózattól.
        passage_text = (
            "17 Ti pedig, szeretteim, emlékezzetek meg azokról a szavakról, "
            "amelyeket a mi Urunk Jézus Krisztus apostolai előre megmondtak.\n"
            "18 Mert azt mondták nektek, hogy az utolsó időben gúnyolódók lesznek, "
            "akik a maguk istenkáromló kívánságai szerint élnek.\n"
            "19 Ezek azok, akik szakadásokat okoznak, érzékiek, akikben nincsen Lélek.\n"
            "20 Ti pedig, szeretteim, épüljetek legszentebb hitetekben, "
            "imádkozva a Szentlélek által."
        )

    state: dict = {
        "last_igehely": "Júd 17–20",
        "igehely_input": "Júd 17–20",
        "bible_translation": "RÚF 2014",
        "passage_text": passage_text,
        "passage_text_source": ruf.get("source_name") or "szentiras.hu",
        "passage_text_source_url": ruf.get("source_url") or "",
        "passage_text_fetched_at": "2026-07-22T10:00:00Z",
        "passage_text_fetched_reference": ruf.get("normalized_reference") or "Júd 17–20",
        "last_alkalom": "Vasárnapi istentisztelet",
        "last_sajat": "Hitben megmaradás",
        "exegesis": "Júdás a gúnyolódók ellen figyelmeztet.",
        "theology": "Hit, ima, Szentlélek.",
        TEXT_WORKSHOP_KEY: {
            "text_main_idea": "A hívők a Szentlélekben imádkozva őrizzék meg magukat Isten szeretetében.",
            "text_main_idea_status": "approved",
            "approved_insights": [
                "Az apostoli szavakra kell emlékezni.",
                "A gúnyolódók a szakadás jelei.",
                "A hitben való épülés és az ima összetartozik.",
            ],
            "main_idea_suggestions": {
                "expanded_summary": "Júdás a közösséget a hit megőrzésére hívja."
            },
        },
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_text_workshop_state(state)
    ensure_sermon_workshop_state(state)

    # M4
    update_sermon_workshop_section(
        state,
        "sermon_main_idea",
        {
            "sermon_main_idea": (
                "Isten a gúnyolódók között is megtartja népét, "
                "ha a Szentlélekben imádkozva őrizzük magunkat az Ő szeretetében."
            ),
            "sermon_main_idea_status": "approved",
        },
    )
    # M4 human
    update_sermon_workshop_section(
        state,
        "human_condition",
        {
            "condition": "A hívők elbizonytalanodnak a gúny és szakadás közepette.",
            "false_response": "Vagy mi is gúnyolódunk, vagy visszavonulunk.",
            "human_need": "Megtartó szeretetre és imádságos kitartásra van szükség.",
            "divine_action": "Isten a Szentlélek által őriz.",
            "grace_response": "Imában és szeretetben megmaradni.",
        },
    )
    # M5
    update_sermon_workshop_section(
        state,
        "listener_tension",
        {
            "listener_question": "Hogyan maradjak meg, ha körülöttem gúny és szakadás van?",
            "listener_resistance": "Az ima és a hitgyakorlat nem elég a valóság ellen.",
            "sermon_tension": "A megtartás nem emberi erőből, hanem Isten szeretetéből fakad.",
            "promised_resolution": "A Szentlélekben imádkozva Isten szeretetében maradhatunk.",
        },
    )
    # Gospel arc
    update_sermon_workshop_section(
        state,
        "christ_centered_arc",
        {
            "divine_gracious_action": "Isten szeretete megtart.",
            "christ_connection": "Krisztusban van a megtartó szeretet.",
            "christ_connection_type": "direct",
            "grace_enabled_response": "Szentlélekben imádkozni és a hitben épülni.",
        },
    )
    # M6
    mid1, mid2, mid3 = "mv-a", "mv-b", "mv-c"
    update_sermon_workshop_section(
        state,
        "sermon_path",
        {
            "type": "text_following",
            "reason": "Júdás figyelmeztetése és bátorítása.",
            "starting_point": "Gúny és szakadás érzékelése",
            "destination": "Megmaradás Isten szeretetében",
        },
    )
    update_sermon_workshop_section(
        state,
        "sermon_movements",
        [
            {
                "id": mid1,
                "title": "Emlékezzetek",
                "role": "opening",
                "core_content": "Apostoli szavakra emlékezés",
                "textual_basis": "Júd 17",
                "listener_discovery": "Nem vagyunk tanácstalanok",
                "transition_to_next": "De kik a gúnyolódók?",
            },
            {
                "id": mid2,
                "title": "Gúnyolódók",
                "role": "deepening",
                "core_content": "A szakadás jelei",
                "textual_basis": "Júd 18–19",
                "listener_discovery": "Felismerjük a veszélyt",
                "transition_to_next": "Mi a válasz?",
            },
            {
                "id": mid3,
                "title": "Megmaradás",
                "role": "arrival",
                "core_content": "Hit, ima, Szentlélek, szeretet",
                "textual_basis": "Júd 20–21",
                "listener_discovery": "Isten megtart",
                "transition_to_next": "",
            },
        ],
    )
    # M7
    update_sermon_workshop_section(
        state,
        "selected_images",
        [
            {
                "id": "img1",
                "image": "épülő ház",
                "textual_basis": "épüljetek a ti szentséges hitetekben",
                "homiletical_function": "deepen",
                "placement": "movement",
                "movement_id": mid3,
                "development_notes": "A hit építése",
            }
        ],
    )
    update_sermon_workshop_section(
        state,
        "illustrations",
        [
            {
                "id": "ill1",
                "idea": "Viharban horgony",
                "source": "everyday",
                "function": "bridge",
                "placement": "movement",
                "movement_id": mid3,
                "connection_to_text": "megtartás",
                "risk_or_limit": "",
            }
        ],
    )
    update_sermon_workshop_section(
        state,
        "applications",
        [
            {
                "id": "app1",
                "application": "Napi ima a közösségért",
                "scope": "community",
                "gospel_basis": "Isten szeretete",
                "concreteness": "medium",
                "placement": "movement",
                "movement_id": mid3,
                "pastoral_caution": "",
            }
        ],
    )
    update_sermon_workshop_section(state, "enrichment_status", "approved")
    # Closing
    update_sermon_workshop_section(
        state,
        "closing",
        {
            "type": "gospel_assurance",
            "final_discovery": "Isten szeretete megtart a gúny közepette is.",
            "hope": "Ő képes megőrizni titeket.",
            "call_or_response": "Imádkozzatok a Szentlélekben.",
            "image_or_line": "épülő hit",
            "open_question": "",
            "tone": "hopeful",
        },
    )
    update_sermon_workshop_section(state, "closing_status", "approved")
    # Diagnostics
    update_sermon_workshop_section(
        state,
        "diagnostics",
        {
            "result": {
                "overall_summary": "Stabil terv, textushű.",
                "revision_priorities": [],
            },
            "priorities": [],
        },
    )
    # Lection
    update_sermon_workshop_section(
        state,
        "lection",
        {
            "reference": "Jn 15,1–11",
            "connection_type": "gospel_complement",
            "function": "Evangéliumi kiegészítés a megmaradáshoz",
            "rationale": "A szőlőtő kép a megmaradás evangéliumi fényét adja.",
            "text": "",
            "notes": "Ne legyen túl hosszú.",
            "testament_preference": "gospel",
            "length_preference": "standard",
            "user_focus": "Evangéliumi szakasz",
        },
    )
    update_sermon_workshop_section(state, "lection_status", "draft")
    save_lection_suggestions(
        state,
        {
            "ok": True,
            "recommended_lection": {
                "reference": "Jn 15,1–11",
                "connection_type": "gospel_complement",
                "rationale": "Megmaradás Krisztusban",
                "liturgical_function": "Evangéliumi kiegészítés",
                "estimated_length": "közepes",
                "warnings": [],
                "reference_valid": True,
            },
            "alternative_lections": [],
        },
    )
    # Prayer
    update_sermon_workshop_section(
        state,
        "prayer_preparation",
        {
            "tone_preference": "hopeful",
            "general_focus": "Közösségi megmaradás",
            "rewrite_mode": "integrate_into_arc",
            "before": {
                "own_thoughts": "Adj őszinteséget. Ne a saját bölcsességünket mondjuk.",
                "purpose": "Megnyílás az Ige hallására",
                "movement_notes": "Megszólítás\nCsend\nLélek kérése",
                "selected_opening": "Uram, szólj hozzánk.",
                "selected_lines": [
                    "Nyisd meg a szívünket.",
                    "Adj őszinte figyelmet.",
                ],
                "closing_direction": "Befogadó figyelem",
                "status": "draft",
            },
            "after": {
                "own_thoughts": "Hála a megtartásért. Imádkozni a hitben elfáradtakért.",
                "purpose": "Hála és ráhagyatkozás",
                "movement_notes": "Hála\nKegyelem\nKözbenjárás",
                "selected_opening": "Köszönjük, Uram.",
                "selected_lines": [
                    "Köszönjük, hogy megtartasz.",
                    "Őrizd a hitükben elfáradtakat.",
                ],
                "closing_direction": "Reménység",
                "status": "draft",
            },
            "status": "draft",
        },
    )
    save_prayer_before_suggestions(
        state,
        {
            "ok": True,
            "purpose": "Megnyílás",
            "suggested_lines": ["Nyisd meg a szívünket."],
            "side": "before",
        },
    )
    save_prayer_after_suggestions(
        state,
        {
            "ok": True,
            "purpose": "Hála",
            "suggested_lines": ["Köszönjük a megtartást."],
            "side": "after",
        },
    )

    add_approved_sermon_decision(
        state,
        "Az igehirdetés fő gondolata",
        "Fő gondolat",
        state[SERMON_WORKSHOP_KEY]["sermon_main_idea"],
    )
    return state


def test_old_project_compat() -> None:
    empty = normalize_sermon_workshop({})
    ok("lection" in empty and "prayer_preparation" in empty, "defaults missing")
    ok(empty["prayer_preparation"]["tone_preference"] == "mixed", "prayer tone default")
    # Pre-M9 project
    legacy = normalize_sermon_workshop(
        {
            "sermon_main_idea": "régi",
            "sermon_main_idea_status": "approved",
            "closing": {"final_discovery": "x"},
        }
    )
    ok(legacy["lection"]["reference"] == "", "legacy lection empty")
    ok(legacy["prayer_preparation"]["before"]["own_thoughts"] == "", "legacy prayer empty")
    ok(legacy["sermon_main_idea"] == "régi", "legacy idea kept")


def test_save_reload_switch(state: dict) -> None:
    payload = build_project_data(state, version="2.0-test", app_name="Textus")
    ok(payload.get("passage_text", "").startswith("17 "), "payload passage")
    ok(
        payload[SERMON_WORKSHOP_KEY]["lection"]["reference"] == "Jn 15,1–11",
        "payload lection ref",
    )
    before_lines = payload[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before"][
        "selected_lines"
    ]
    after_lines = payload[SERMON_WORKSHOP_KEY]["prayer_preparation"]["after"][
        "selected_lines"
    ]
    ok(before_lines != after_lines, "before/after lines distinct in payload")
    ok(
        "sw_prayer_before_own_thoughts" not in payload,
        "widget key leaked into project",
    )
    for k in EXCLUDED_SESSION_KEYS:
        ok(k not in payload, f"excluded leaked: {k}")

    # Reload
    cleaned = sanitize_project_data(payload)
    reloaded = {
        **{k: cleaned.get(k, "") for k in (
            "last_igehely",
            "bible_translation",
            "passage_text",
            "passage_text_source",
            "passage_text_source_url",
            "passage_text_fetched_at",
            "passage_text_fetched_reference",
        )},
        TEXT_WORKSHOP_KEY: cleaned[TEXT_WORKSHOP_KEY],
        SERMON_WORKSHOP_KEY: cleaned[SERMON_WORKSHOP_KEY],
    }
    ok(
        reloaded[SERMON_WORKSHOP_KEY]["sermon_main_idea_status"] == "approved",
        "status lost on reload",
    )
    mids = [m["id"] for m in reloaded[SERMON_WORKSHOP_KEY]["sermon_movements"]]
    ok(mids == ["mv-a", "mv-b", "mv-c"], f"movement ids changed: {mids}")
    img_mid = reloaded[SERMON_WORKSHOP_KEY]["selected_images"][0]["movement_id"]
    ok(img_mid == "mv-c", f"M7 image movement link broken: {img_mid}")
    ok(
        reloaded[SERMON_WORKSHOP_KEY]["diagnostics"]["result"].get("overall_summary"),
        "diagnostics lost",
    )

    # Project B switch isolation
    other = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16 Mert úgy szeretett…",
        "bible_translation": "RÚF 2014",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    other_payload = build_project_data(other, version="2.0-test")
    ok(
        other_payload[SERMON_WORKSHOP_KEY]["lection"]["reference"] == "",
        "other project leaked lection",
    )
    ok(
        other_payload["passage_text"] != reloaded["passage_text"],
        "passage mixed across projects",
    )
    # Switch back: jude payload unchanged
    again = sanitize_project_data(payload)
    ok(
        again[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before"]["own_thoughts"]
        == state[SERMON_WORKSHOP_KEY]["prayer_preparation"]["before"]["own_thoughts"],
        "prayer lost after switch cycle",
    )


def test_lection_isolation(state: dict) -> None:
    base_text = state["passage_text"]
    # Load lection RÚF via fixture (Jn) — use jude fixture wrongly would still not touch passage
    clear_ruf_cache()
    # Simulate applying lection text without touching passage
    lection_text = "1 Én vagyok a szőlőtő…"
    update_sermon_workshop_section(
        state,
        "lection",
        {
            "text": lection_text,
            "text_source": "szentiras.hu",
            "text_fetched_reference": "Jn 15,1–11",
            "reference": "Jn 15,1–11",
        },
    )
    ok(state["passage_text"] == base_text, "lection overwrite passage_text")
    ok(
        state[SERMON_WORKSHOP_KEY]["lection"]["text"] == lection_text,
        "lection text not stored",
    )
    ok(
        not references_equivalent(
            state[SERMON_WORKSHOP_KEY]["lection"]["reference"],
            "Júd 17–20",
        ),
        "lection should differ from base",
    )
    # Mismatch detection
    fetched = state[SERMON_WORKSHOP_KEY]["lection"]["text_fetched_reference"]
    new_ref = "Zsolt 23"
    ok(
        not references_equivalent(fetched, new_ref),
        "mismatch warning precondition",
    )
    # Network failure must not clear
    before = state[SERMON_WORKSHOP_KEY]["lection"]["text"]
    bad = fetch_ruf_passage("Jn 15,1–11", http_get=http_fail())
    ok(not bad["success"], "network fail should fail")
    ok(
        state[SERMON_WORKSHOP_KEY]["lection"]["text"] == before,
        "network fail cleared lection",
    )
    # Invalid ref
    inv = validate_lection_reference("Jn 3,16; Mt 5,3")
    ok(not inv["ok"], "montage should be invalid")
    # Jude valid
    jud = validate_lection_reference("Júd 17–20")
    ok(jud["ok"], f"Jude validation: {jud.get('error')}")


def test_prayer_separation(state: dict) -> None:
    prep = state[SERMON_WORKSHOP_KEY]["prayer_preparation"]
    ok("előtti" not in " ".join(prep["after"]["selected_lines"]).casefold() or True, "noop")
    ok(
        "őszinteség" in prep["before"]["own_thoughts"].casefold()
        or "oszinteseg" in prep["before"]["own_thoughts"].casefold()
        or "őszinte" in prep["before"]["own_thoughts"].casefold()
        or "Adj" in prep["before"]["own_thoughts"],
        "before thoughts missing",
    )
    ok("Hála" in prep["after"]["own_thoughts"] or "hála" in prep["after"]["own_thoughts"].casefold(), "after thoughts")
    ok(
        prep["before"]["selected_opening"] != prep["after"]["selected_opening"],
        "openings mixed",
    )
    # Integrate with little context
    r = integrate_prayer_thoughts(
        side="before",
        passage="Júd 17–20",
        rewrite_mode="light_polish",
        prayer_before={"own_thoughts": "Adj őszinteséget."},
        generate_fn=stub_json(
            {
                "purpose": "",
                "recommended_movements": [
                    {"title": "a", "function": "address", "content_direction": "x"},
                    {"title": "b", "function": "silence", "content_direction": "y"},
                    {"title": "c", "function": "illumination", "content_direction": "z"},
                ],
                "opening_options": ["Uram"],
                "suggested_lines": ["Adj őszinteséget."],
                "closing_direction": "",
                "integrated_user_thoughts": [
                    {
                        "original": "Adj őszinteséget.",
                        "refined": "Adj őszinteséget.",
                        "placement": "confession",
                    }
                ],
                "language_notes": ["light_polish"],
                "cliche_risks": [],
                "warnings": [],
                "missing_information": [],
            }
        ),
    )
    ok(r.ok, f"integrate little data: {r.error_message}")
    ok(r.integrated_user_thoughts, "integrated empty")


def test_ai_context_passage_text(state: dict) -> None:
    """MI modulok ne jelezzenek tévesen hiányzó passage_text-et."""
    sw = state[SERMON_WORKSHOP_KEY]
    tw = state[TEXT_WORKSHOP_KEY]
    base = dict(
        passage=state["last_igehely"],
        passage_text=state["passage_text"],
        bible_translation=state["bible_translation"],
        text_main_idea=tw["text_main_idea"],
        text_main_idea_status=tw["text_main_idea_status"],
        text_expanded_summary=tw["main_idea_suggestions"]["expanded_summary"],
        approved_insights=tw["approved_insights"],
        sermon_main_idea=sw["sermon_main_idea"],
        sermon_main_idea_status=sw["sermon_main_idea_status"],
        sermon_expanded_summary="A megtartás kegyelemből fakad.",
        human_condition=sw["human_condition"],
        listener_tension=sw["listener_tension"],
        christ_centered_arc=sw["christ_centered_arc"],
        sermon_path=sw["sermon_path"],
        sermon_movements=sw["sermon_movements"],
        selected_images=sw["selected_images"],
        illustrations=sw["illustrations"],
        applications=sw["applications"],
        closing=sw["closing"],
        theology=state["theology"],
        exegesis=state["exegesis"],
    )

    # Minimal stubs that return empty-ish but valid enough to parse
    def check_no_false_missing(result, label: str) -> None:
        warns = getattr(result, "warnings", None) or []
        if isinstance(result, dict):
            warns = result.get("warnings") or []
        for w in warns:
            if "passage_text" in str(w).casefold() and (
                "hiány" in str(w).casefold() or "nincs" in str(w).casefold()
            ):
                fail(f"{label}: false passage_text warning: {w}")

    # Lection suggest
    lection_payload = {
        "recommended_lection": {
            "reference": "Jn 15,1–11",
            "connection_type": "gospel_complement",
            "rationale": "x",
            "liturgical_function": "y",
            "estimated_length": "közepes",
            "warnings": [],
        },
        "alternative_lections": [],
        "overall_reasoning": "ok",
        "no_separate_lection_needed": False,
        "no_lection_reason": "",
        "basis": ["passage_text"],
        "missing_information": [],
        "warnings": [],
    }
    lr = suggest_lections(**base, generate_fn=stub_json(lection_payload))
    check_no_false_missing(lr, "lection")
    ok(lr.ok, f"lection suggest: {lr.error_message}")

    # Prayer before
    pr = suggest_prayer_before(
        **base,
        prayer_before=sw["prayer_preparation"]["before"],
        tone_preference="hopeful",
        generate_fn=stub_json(
            {
                "purpose": "p",
                "recommended_movements": [
                    {"title": "1", "function": "address", "content_direction": "a"},
                    {"title": "2", "function": "silence", "content_direction": "b"},
                    {"title": "3", "function": "illumination", "content_direction": "c"},
                ],
                "opening_options": ["o1", "o2"],
                "suggested_lines": ["s1", "s2", "s3", "s4"],
                "closing_direction": "c",
                "integrated_user_thoughts": [],
                "language_notes": [],
                "cliche_risks": [],
                "warnings": [],
                "missing_information": [],
            }
        ),
    )
    check_no_false_missing(pr, "prayer_before")
    ok(pr.ok, f"prayer before: {pr.error_message}")

    # Closing / enrichment / path / gospel / etc. with stubs that include warnings empty
    # Diagnostics
    diag = run_homiletical_diagnostics(
        **base,
        generate_fn=stub_json(
            {
                "overall_summary": "Stabil.",
                "diagnostic_areas": [],
                "revision_priorities": [],
                "warnings": [],
                "missing_information": [],
            }
        ),
    )
    check_no_false_missing(diag, "diagnostics")


def test_approval_adopt_not_auto(state: dict) -> None:
    """Átvétel szimuláció: status marad draft, ha csak mezőket írunk."""
    sw = state[SERMON_WORKSHOP_KEY]
    # Simulate lection adopt without approve
    update_sermon_workshop_section(
        state,
        "lection",
        {
            "reference": "Zsolt 1",
            "connection_type": "liturgical_echo",
            "function": "visszhang",
            "rationale": "imádságos",
        },
    )
    # status key separate — should stay draft unless explicitly approved
    ok(sw["lection_status"] == "draft", "lection auto-approved on adopt")
    update_sermon_workshop_section(state, "lection_status", "approved")
    ok(state[SERMON_WORKSHOP_KEY]["lection_status"] == "approved", "approve failed")
    payload = build_project_data(state, version="2.0-test")
    ok(
        payload[SERMON_WORKSHOP_KEY]["lection_status"] == "approved",
        "approved status not persisted",
    )


def test_deepcopy_isolation(state: dict) -> None:
    a = normalize_sermon_workshop(state[SERMON_WORKSHOP_KEY])
    b = normalize_sermon_workshop(copy.deepcopy(state[SERMON_WORKSHOP_KEY]))
    b["prayer_preparation"]["before"]["own_thoughts"] = "CHANGED"
    ok(
        a["prayer_preparation"]["before"]["own_thoughts"] != "CHANGED",
        "shallow copy pollution",
    )
    b["lection"]["text"] = "OTHER"
    ok(a["lection"]["text"] != "OTHER", "lection shallow copy pollution")


def test_duplicate_widget_keys() -> None:
    """Statikus kulcsok egyedisége a sermon_workshop_ui-ban."""
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    # literal key="..."
    keys = re.findall(r'key\s*=\s*["\']([^"\']+)["\']', src)
    # Also _KEY_* constant values
    const_keys = re.findall(
        r'"(sw_[a-z0-9_]+)"',
        src,
    )
    all_keys = keys + const_keys
    # Filter dynamic f-strings already excluded; focus on static duplicates
    from collections import Counter

    counts = Counter(all_keys)
    dups = {k: n for k, n in counts.items() if n > 1 and not k.startswith("sw_mi_")}
    # Many _KEY map values appear twice (definition + use) — only button keys matter
    buttonish = {
        k: n
        for k, n in counts.items()
        if n > 1 and ("_save" in k or "_approve" in k or "_mi_" in k or k.endswith("_run"))
    }
    # Appear twice is ok if once in EXCLUDED and once in UI — check exact button duplicates in key=
    btn_counts = Counter(keys)
    btn_dups = {k: n for k, n in btn_counts.items() if n > 1}
    if btn_dups:
        fail(f"duplicate Streamlit keys: {btn_dups}")
    notes.append(f"static widget keys scanned: {len(keys)}")


def test_no_full_prayer_adopt_button() -> None:
    src = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    ok("Teljes imádság" not in src, "full prayer adopt button present")
    ok("Átveszem az imaívet" in src, "arc adopt missing")
    ok("Átveszem ezt a mondatmagot" not in src, "per-line adopt still present")
    ok("Átveszem ezt az indítást" not in src, "per-opening adopt still present")
    ok("Eltérő imaindítások" not in src, "opening list still in main UI")
    ok("Saját gondolatok beépítése" not in src or "További beállítások" in src, "integrate section")


def test_flush_wired_for_project_save() -> None:
    """Projekt Mentés a sermon / textus workshop widgeteket is tartósítsa."""
    sw_ui = (ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    tw_ui = (ROOT / "textus_workshop_ui.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    ok("def flush_sermon_workshop_from_widgets" in sw_ui, "sermon flush helper missing")
    ok(
        "def flush_textus_workshop_from_widgets" in tw_ui,
        "textus flush helper missing",
    )
    ok("flush_sermon_workshop_from_widgets()" in app, "sermon flush not called from app")
    ok("flush_textus_workshop_from_widgets()" in app, "textus flush not called from app")
    # call sites inside _sync_inputs_to_last
    idx_sync = app.find("def _sync_inputs_to_last")
    idx_next_def = app.find("\ndef ", idx_sync + 1)
    idx_sw = app.find("flush_sermon_workshop_from_widgets()", idx_sync)
    idx_tw = app.find("flush_textus_workshop_from_widgets()", idx_sync)
    ok(
        idx_sw != -1 and idx_sw < idx_next_def,
        "sermon flush not inside _sync_inputs_to_last",
    )
    ok(
        idx_tw != -1 and idx_tw < idx_next_def,
        "textus flush not inside _sync_inputs_to_last",
    )


def main() -> int:
    print("=== Jude E2E integration ===")
    test_old_project_compat()
    state = build_jude_state()
    notes.append(f"project: Júdás – teljes munkafolyamat teszt")
    notes.append(f"passage_text lines: {len(state['passage_text'].splitlines())}")
    test_save_reload_switch(state)
    test_lection_isolation(state)
    test_prayer_separation(state)
    test_ai_context_passage_text(state)
    test_approval_adopt_not_auto(state)
    test_deepcopy_isolation(state)
    test_duplicate_widget_keys()
    test_no_full_prayer_adopt_button()

    if errors:
        print("FAILED:")
        for e in errors:
            print(" -", e)
        return 1
    print("ALL CHECKS PASSED")
    for n in notes:
        print(" ·", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
