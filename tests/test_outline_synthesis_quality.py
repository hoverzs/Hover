# ruff: noqa: E402
"""Ketfazisu vazlatszintezis — keves / kozepes / teljes forras regresszio."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_outline,
)
from sermon_workshop_outline_ai import (
    MISSING_PART,
    OUTLINE_PLACEHOLDER_BANLIST,
    assemble_sermon_outline,
    build_outline_from_workshop,
    outline_to_readable_content,
)
from sermon_workshop_outline_synth_ai import (
    HOMILETIC_SYSTEM_PROMPT,
    apply_synth_payload_to_outline,
    assess_outline_quality_issues,
    regenerate_outline_part,
    run_two_phase_outline_synthesis,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop
from tests.test_jude_e2e_workflow import build_jude_state


def _assert_usable_outline(outline: dict) -> str:
    content = outline_to_readable_content(outline)
    assert outline.get("main_idea")
    assert content.strip()
    assert MISSING_PART not in content
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        assert banned not in content, banned
    mvs = outline.get("movements") or []
    assert len(mvs) >= 3
    titles = [str(m.get("title") or "") for m in mvs]
    for t in ("Nyitás", "Kibontás", "Megérkezés"):
        assert t not in titles
    idea = (outline.get("main_idea") or "").strip()
    opening = (outline.get("opening_direction") or "").strip()
    if opening:
        assert opening != idea
    closing = ((outline.get("closing") or {}).get("final_insight") or "").strip()
    if closing:
        assert closing != idea
    return content


def test_system_prompt_contains_homiletic_core():
    assert "református" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "Krisztus" in HOMILETIC_SYSTEM_PROMPT
    assert "Ne másold egymás után" in HOMILETIC_SYSTEM_PROMPT
    assert "850" in HOMILETIC_SYSTEM_PROMPT and "1150" in HOMILETIC_SYSTEM_PROMPT
    assert "text_boundary_note" in HOMILETIC_SYSTEM_PROMPT
    assert "25" in HOMILETIC_SYSTEM_PROMPT


def test_jude_text_boundary_hint_continues_in_v21():
    from sermon_workshop_outline_synth_ai import suggest_text_boundary_hint

    hint = suggest_text_boundary_hint("Júd 17–20", "17 Ti pedig… 20 épüljetek…")
    assert hint["suggested_text_boundary"] == "Júd 17–21"
    assert "következő versben" in hint["text_boundary_note"]
    assert "21" in hint["text_boundary_note"]

    seed = build_outline_from_workshop(build_jude_state())
    out, _ = run_two_phase_outline_synthesis(
        seed,
        {
            "passage_reference": "Júd 17–20",
            "passage_text": seed.get("passage_reference") or "",
            "source_keys": [],
        },
        generate_fn=None,
    )
    assert out.get("suggested_text_boundary") == "Júd 17–21"
    content = outline_to_readable_content(out)
    assert "Júd 17–21" in content
    assert "Megjegyzés a textushatárról" in content
    assert "Hallgatói felismerés" not in content
    assert "Exegetikai kibontás" not in content


def test_quality_gate_flags_double_numbering_and_focus_length():
    long_focus = " ".join(["szó"] * 30)
    bad = {
        "main_idea": long_focus,
        "passage_reference": "Júd 17–20",
        "sermon_title": "Cím",
        "introduction": {
            "development": "Valós hallgatói feszültség a gúny közepette."
        },
        "movements": [
            {
                "title": "1. Apostoli emlékezet",
                "development": ["Első kibontás a textusból."],
            },
            {
                "title": "2. A szakadás jelei",
                "development": ["Második kibontás."],
            },
            {
                "title": "3. Épülés a Lélekben",
                "development": ["Harmadik kibontás."],
            },
        ],
        "conclusion": {"development": "Megtartó szeretet zárja az ívet."},
        "content": (
            "**1. 1. Apostoli emlékezet**\n\nElső kibontás a textusból.\n\n"
            "**2. 2. A szakadás jelei**\n\nMásodik kibontás.\n\n"
            "**3. 3. Épülés a Lélekben**\n\nHarmadik kibontás."
        ),
    }
    issues = assess_outline_quality_issues(bad)
    assert "double_numbering" in issues
    assert "focus_too_long" in issues


def test_quality_gate_flags_technical_labels_and_repeated_paragraphs():
    para = (
        "Az apostolok szavaira emlékezés tartást ad a zavar közepette, "
        "és nem hagy tanácstalanságban."
    )
    bad = {
        "main_idea": "Isten megtart a gúny közepette.",
        "introduction": {"development": "A gúny hangja körülöttünk egyre hangosabb."},
        "movements": [
            {
                "title": "Emlékezet",
                "development": [para, "Exegetikai kibontás: a szöveg figyelmeztet."],
            },
            {"title": "Gúny", "development": [para]},
            {"title": "Megmaradás", "development": ["Hitben épülés a Lélekben."]},
        ],
        "conclusion": {"development": "Isten szeretete megtart."},
    }
    content = outline_to_readable_content(normalize_sermon_outline(bad))
    bad["content"] = content + "\n\n" + para + "\n\n" + para
    issues = assess_outline_quality_issues(bad)
    assert "technical_labels" in issues or "Exegetikai" in content
    assert "repeated_paragraphs" in issues


def test_ai_failure_does_not_replace_with_mechanical_success():
    """Egy javító kör utáni minőségbukás → őszinte hiba, nem mechanikus „kész”."""
    state = copy.deepcopy(build_jude_state())
    ensure_sermon_workshop_state(state)
    previous = normalize_sermon_outline(
        (state.get(SERMON_WORKSHOP_KEY) or {}).get("sermon_outline")
    )

    def gen(prompt, **kwargs):
        return json.dumps(
            {
                "title": "Rossz vázlat",
                "focus_sentence": "A textus arra szólít fel, hogy legyünk jók mindig és mindenütt a saját erőnkből mindenkivel szemben.",
                "introduction": {
                    "development": "A hallgató a textus világába lép.",
                    "transition": "",
                },
                "movements": [
                    {"title": "Nyitás", "development": ["A textus magja elmélyül."]},
                    {"title": "Kibontás", "development": ["A fő gondolat megérkezik."]},
                    {
                        "title": "Megérkezés",
                        "development": ["Ez a rész még nincs kidolgozva."],
                    },
                ],
                "conclusion": {"development": "A textus magja elmélyül."},
            },
            ensure_ascii=False,
        )

    result = assemble_sermon_outline(
        state, generate_fn=gen, synthesize=True, force_overwrite=True
    )
    assert not result.ok
    assert "szószéken használható" in (result.error_message or "").casefold() or (
        "nem adott" in (result.error_message or "").casefold()
    )
    # Ne mentse felül a meglévő állapotot „kész” mechanikus vázlattal
    kept = normalize_sermon_outline(
        (state.get(SERMON_WORKSHOP_KEY) or {}).get("sermon_outline")
    )
    assert kept.get("main_idea") == previous.get("main_idea")


def test_sparse_workshop_still_coherent_outline():
    """Üres műhelyek mellett is: igehely + rövid saját gondolat → koherens vázlat."""
    state = {
        "last_igehely": "Júd 17–20",
        "passage_text": (
            "17 Ti pedig, szeretteim, emlékezzetek… "
            "20 Ti azonban, szeretteim, épüljetek… imádkozva a Szentlélek által."
        ),
        "last_sajat": "Hitben megmaradás a gúny közepette",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    result = assemble_sermon_outline(state, generate_fn=None, synthesize=True)
    assert result.ok
    content = _assert_usable_outline(result.outline)
    assert "##" not in content
    assert "Hallgatói felismerés" not in content
    assert "Exegetikai kibontás" not in content
    assert result.outline.get("suggested_text_boundary") == "Júd 17–21"


def test_minimal_sources_usable_outline():
    state = {
        "last_igehely": "Júd 17–20",
        "passage_text": (
            "17 Ti pedig, szeretteim, emlékezzetek az apostolok szavaira… "
            "20 Ti azonban, szeretteim, épüljetek legszentebb hitetekben, "
            "imádkozva a Szentlélek által."
        ),
        "last_sajat": "Hitben megmaradás a gúny közepette",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    result = assemble_sermon_outline(state, generate_fn=None, synthesize=True)
    assert result.ok
    _assert_usable_outline(result.outline)


def test_partial_sources_usable_outline():
    state = {
        "last_igehely": "Júd 17–20",
        "passage_text": "Emlékezzetek… épüljetek… imádkozva a Szentlélek által.",
        "exegesis": "Júdás a gúnyolódók ellen figyelmeztet, majd a megmaradásra hív.",
        "theology": "A megtartás Isten szeretetéből fakad.",
        TEXT_WORKSHOP_KEY: {
            **get_default_text_workshop(),
            "text_main_idea": (
                "A hívők a Szentlélekben imádkozva őrizzék meg magukat "
                "Isten szeretetében."
            ),
            "text_main_idea_status": "approved",
            "approved_insights": [
                "Az apostoli szavakra kell emlékezni.",
                "A gúnyolódók a szakadás jelei.",
            ],
        },
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    content = _assert_usable_outline(result.outline)
    assert "Szentlélek" in content or "szeretet" in content.casefold()


def test_full_jude_sources_usable_outline():
    state = copy.deepcopy(build_jude_state())
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok
    content = _assert_usable_outline(result.outline)
    assert result.outline.get("christ_connection") or result.outline.get(
        "divine_gracious_action"
    )
    assert "Fókuszmondat" in content
    assert "##" not in content
    assert "Hallgatói felismerés" not in content
    assert "Kapcsolat típusa" not in content


def test_apply_synth_payload_locks_approved_idea():
    seed = build_outline_from_workshop(build_jude_state())
    locked = seed["main_idea"]
    payload = {
        "title": "Megtartva a gúny között",
        "focus_sentence": "Gyengített, moralizáló változat az emberi erőfeszítésről.",
        "introduction": {
            "development": "A gúny hangja körülöttünk egyre hangosabb.",
            "transition": "A textus először emlékeztet.",
        },
        "refinement_suggestions": [
            "A hallgatói kapcsolat tovább erősíthető egy konkrét gyülekezeti élethelyzettel."
        ],
        "movements": [
            {
                "id": "a",
                "title": "Apostoli emlékezet",
                "textual_anchor": "Júd 17",
                "development": [
                    "Az apostolok szavaira emlékezés tartást ad a zavar közepette.",
                    "A hallgató nem tanácstalan — van irány a zűrzavarban.",
                ],
                "transition": "De kik a gúnyolódók?",
            },
            {
                "id": "b",
                "title": "A szakadás jelei",
                "textual_anchor": "Júd 18–19",
                "development": [
                    "A gúnyolódók a szakadás jelei, lélek nélkül élnek.",
                    "Felismerjük a veszélyt, hogy ne sodródjunk vele.",
                ],
                "transition": "Mi a válasz?",
            },
            {
                "id": "c",
                "title": "Épülés a Lélekben",
                "textual_anchor": "Júd 20–21",
                "development": [
                    "Hitben épülés, Szentlélekben ima, Isten szeretetében megmaradás.",
                    "A megmaradás kegyelemből fakad, nem emberi erőből.",
                ],
            },
        ],
        "conclusion": {
            "development": "Isten szeretete megtart a gúny közepette is.",
            "final_sentence": "Imádkozzatok a Szentlélekben.",
        },
    }
    bundle = {
        "sermon_main_idea": locked,
        "sermon_main_idea_status": "approved",
        "source_keys": ["sermon_main_idea", "passage_text"],
    }
    merged = apply_synth_payload_to_outline(seed, payload, bundle=bundle)
    assert merged["main_idea"] == locked
    assert merged["sermon_title"]
    assert merged["editorial_tips"]
    content = outline_to_readable_content(merged)
    assert "Apostoli emlékezet" in content
    assert "Fókuszmondat" in content
    assert "Bevezetés" in content
    assert "Megérkezés" in content
    assert "##" not in content
    assert MISSING_PART not in content
    issues = assess_outline_quality_issues(merged)
    assert "placeholder" not in issues
    assert "generic_titles" not in issues
    assert "weak_movements" not in issues


def test_quality_gate_detects_generic_and_placeholder():
    bad = {
        "main_idea": "Isten megtart.",
        "opening_direction": "A hallgató a textus világába lép.",
        "movements": [
            {"title": "Nyitás", "core_content": "Isten megtart."},
            {"title": "Kibontás", "core_content": "A textus magja elmélyül."},
            {"title": "Megérkezés", "core_content": "Isten megtart."},
        ],
        "closing": {"final_insight": "Isten megtart."},
    }
    issues = assess_outline_quality_issues(bad)
    assert (
        "placeholder" in issues
        or "weak_movements" in issues
        or "closing_repeats_focus" in issues
    )


def test_partial_regen_preserves_other_parts():
    seed = build_outline_from_workshop(build_jude_state())
    before_idea = seed["main_idea"]
    before_closing = dict(seed.get("closing") or {})
    before_notes = "Kézi megjegyzés — ne töröld."
    seed["manual_notes"] = before_notes

    def gen(prompt, **kwargs):
        return json.dumps(
            {
                "introduction": {
                    "development": "Új bevezetés: a gúny hangja körülöttünk.",
                    "transition": "Először emlékezzünk.",
                },
                "focus_sentence": "Ezt ne fogadja el a zárolás helyett.",
                "conclusion": {"development": "Ezt se cserélje."},
                "movements": seed.get("movements"),
            },
            ensure_ascii=False,
        )

    bundle = {
        "sermon_main_idea": before_idea,
        "sermon_main_idea_status": "approved",
        "passage_reference": "Júd 17–20",
        "passage_text": "…",
        "source_keys": ["sermon_main_idea", "passage_text"],
    }
    updated, _ = regenerate_outline_part(
        seed, bundle, part="introduction", generate_fn=gen
    )
    assert updated["main_idea"] == before_idea
    assert updated["manual_notes"] == before_notes
    assert updated["opening_direction"].startswith("Új bevezetés")
    assert updated["closing"]["final_insight"] == before_closing.get("final_insight")


def test_two_phase_without_ai_keeps_seed():
    seed = build_outline_from_workshop(build_jude_state())
    out, warnings = run_two_phase_outline_synthesis(
        seed, {"source_keys": []}, generate_fn=None
    )
    assert out["main_idea"] == seed["main_idea"]
    assert warnings == []


def test_deficiency_tips_not_required_workshop_message():
    tip = "Kötelező kitölteni minden műhelymezőt a folytatáshoz."
    seed = normalize_sermon_outline(
        {"main_idea": "Isten megtart.", "passage_reference": "Júd 17–20"}
    )
    merged = apply_synth_payload_to_outline(
        seed,
        {
            "editorial_tips": [
                tip,
                "A hallgatói kapcsolat tovább erősíthető egy konkrét élethelyzettel.",
            ],
            "movements": [
                {"title": "Emlékezet", "core_content": "Apostoli szó", "id": "1"},
                {"title": "Gúny", "core_content": "Szakadás", "id": "2"},
                {"title": "Megmaradás", "core_content": "Lélek", "id": "3"},
            ],
            "opening_direction": "Kérdés a gúny közepette.",
            "closing": {"final_insight": "Megtartó szeretet."},
            "christ_connection": "Krisztusban",
            "applications": ["Imádkozni", "Épülni a hitben"],
        },
        bundle={"source_keys": []},
    )
    assert tip not in (merged.get("editorial_tips") or [])
    assert merged.get("editorial_tips")
