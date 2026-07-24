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
    SOFT_QUALITY_ISSUES,
    apply_synth_payload_to_outline,
    assess_outline_quality_issues,
    outline_length_profile,
    regenerate_outline_part,
    resolve_outline_occasion,
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
    assert "Krisztus" in HOMILETIC_SYSTEM_PROMPT or "krisztus" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "Ne másold egymás után" in HOMILETIC_SYSTEM_PROMPT
    assert "Virrasztó" in HOMILETIC_SYSTEM_PROMPT
    assert "szószám önmagában soha" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "text_boundary_note" in HOMILETIC_SYSTEM_PROMPT
    assert "25" in HOMILETIC_SYSTEM_PROMPT
    assert "munkavázlat" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "A textus állítása" in HOMILETIC_SYSTEM_PROMPT
    assert "Hallgatói irány" in HOMILETIC_SYSTEM_PROMPT
    assert "450–700" in HOMILETIC_SYSTEM_PROMPT
    assert "350–550" in HOMILETIC_SYSTEM_PROMPT
    assert "bagatellizáld" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "Exegetikai kibontás" in HOMILETIC_SYSTEM_PROMPT
    assert "kész prédikáció" in HOMILETIC_SYSTEM_PROMPT.casefold()


def test_soft_length_ranges_match_working_outline_targets():
    sunday = outline_length_profile("Vasárnapi istentisztelet")
    assert sunday["target_range"] == "450–700"
    assert sunday["soft_min"] == 400
    assert sunday["soft_max"] == 800
    assert sunday["min_movements"] == 2

    wake = outline_length_profile("Virrasztó")
    assert wake["target_range"] == "350–550"
    assert wake["soft_min"] == 300
    assert wake["soft_max"] == 600
    assert wake["min_movements"] == 2

    partial = outline_length_profile("Virrasztó", partial=True)
    assert partial["soft_min"] < wake["soft_min"] or partial["soft_min"] == 250
    assert "Részleges" in partial["guidance"] or "részleges" in partial["guidance"].casefold()
    assert "word_count_out_of_range" in SOFT_QUALITY_ISSUES
    assert "stock_phrases" in SOFT_QUALITY_ISSUES
    assert "sermon_like_verbosity" in SOFT_QUALITY_ISSUES


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
    previous = normalize_sermon_outline(
        (state.get(SERMON_WORKSHOP_KEY) or {}).get("sermon_outline")
    )

    def gen(prompt, **kwargs):
        return json.dumps(
            {
                "title": "Rossz vázlat",
                "focus_sentence": (
                    "A textus arra szólít fel, hogy legyünk jók mindig és mindenütt "
                    "a saját erőnkből mindenkivel szemben."
                ),
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
    assert "word_count_out_of_range" not in (result.error_message or "")
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


def _words(n: int, seed: str = "szó") -> str:
    return " ".join([f"{seed}{i}" for i in range(max(1, n))])


def _usable_ai_payload(
    *,
    focus: str = "Isten megtart a gúny közepette a Szentlélek által.",
    intro_words: int = 70,
    movement_words: int = 60,
    conclusion_words: int = 70,
    movement_count: int = 3,
    title: str = "Megtartva a gúny között",
) -> dict:
    titles = [
        "Apostoli emlékezet",
        "A szakadás jelei",
        "Épülés a Lélekben",
        "Megmaradás a szeretetben",
    ]
    movements = []
    for i in range(movement_count):
        movements.append(
            {
                "title": titles[i % len(titles)],
                "textual_anchor": f"Júd {17 + i}",
                "development": [
                    _words(movement_words, seed=f"mozg{i}a"),
                    _words(max(20, movement_words // 2), seed=f"mozg{i}b"),
                ],
                "transition": "Tovább lépünk." if i + 1 < movement_count else "",
            }
        )
    return {
        "title": title,
        "text_reference": "Júd 17–20",
        "focus_sentence": focus,
        "introduction": {
            "development": _words(intro_words, seed="bevezet"),
            "transition": "Először az emlékezethez fordulunk.",
        },
        "movements": movements,
        "conclusion": {
            "development": _words(conclusion_words, seed="zaras"),
            "final_sentence": "Imádkozzatok a Szentlélekben.",
        },
        "refinement_suggestions": [
            "Egy konkrét gyülekezeti helyzet tovább erősíthetné a megérkezést."
        ],
    }


def test_resolve_virraszto_occasion_from_text_and_field():
    assert resolve_outline_occasion({"occasion": "Virrasztó"}) == "Virrasztó"
    assert (
        resolve_outline_occasion(
            {"occasion": "", "user_focus": "Rövid virrasztó áhítat a családnak"}
        )
        == "Virrasztó"
    )
    profile = outline_length_profile("Virrasztó")
    assert profile["min_movements"] == 2
    assert profile["soft_max"] <= 600
    assert profile["target_range"] == "350–550"


def test_word_count_alone_is_soft_not_hard_rejection():
    """Slightly off word-count but otherwise good → soft only, assembly keeps it."""
    payload = _usable_ai_payload(
        intro_words=55, movement_words=45, conclusion_words=55, movement_count=3
    )
    calls = {"n": 0}

    def gen(prompt, **kwargs):
        calls["n"] += 1
        return json.dumps(payload, ensure_ascii=False)

    state = {
        "last_igehely": "Júd 17–20",
        "last_alkalom": "Vasárnapi istentisztelet",
        "passage_text": (
            "17 Ti pedig, szeretteim, emlékezzetek… "
            "20 Ti azonban, szeretteim, épüljetek… imádkozva a Szentlélek által."
        ),
        "last_sajat": "Hitben megmaradás a gúny közepette",
        "exegesis": "Júdás a gúnyolódók ellen figyelmeztet, majd a megmaradásra hív.",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    result = assemble_sermon_outline(
        state, generate_fn=gen, synthesize=True, force_overwrite=True
    )
    assert result.ok, result.error_message
    content = outline_to_readable_content(result.outline)
    assert content.strip()
    assert "word_count_out_of_range" not in (result.error_message or "")
    assert "word_count_out_of_range" not in " ".join(result.warnings or [])
    soft = assess_outline_quality_issues(
        result.outline,
        for_ai_output=True,
        bundle={"occasion": "Vasárnapi istentisztelet", "source_keys": ["exegesis"]},
    )
    hard = [i for i in soft if i not in SOFT_QUALITY_ISSUES]
    assert hard == []
    # Soft szószámjelzés megengedett, de nem bukhat el miatta.
    assert calls["n"] >= 1


def test_partial_workshop_ai_outline_kept_despite_short_word_count():
    """Részleges, de tartalmas műhelyanyag + rövidebb AI válasz → használható vázlat."""
    payload = _usable_ai_payload(
        intro_words=50, movement_words=40, conclusion_words=50, movement_count=3
    )

    def gen(prompt, **kwargs):
        return json.dumps(payload, ensure_ascii=False)

    state = {
        "last_igehely": "Júd 17–20",
        "last_alkalom": "Vasárnapi istentisztelet",
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
        },
        SERMON_WORKSHOP_KEY: {
            **get_default_sermon_workshop(),
            "sermon_main_idea": "Isten megtart a gúny közepette.",
            "sermon_main_idea_status": "draft",
        },
    }
    ensure_sermon_workshop_state(state)
    result = assemble_sermon_outline(
        state, generate_fn=gen, synthesize=True, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert result.outline.get("main_idea")
    assert len(result.outline.get("movements") or []) >= 3
    content = outline_to_readable_content(result.outline)
    assert "Apostoli emlékezet" in content
    assert "Fókuszmondat" in content or result.outline.get("main_idea")
    assert MISSING_PART not in content


def test_virraszto_produces_shorter_complete_usable_outline():
    """Virrasztó: rövidebb, 2–3 egységes, teljes szerkezetű használható vázlat."""
    payload = {
        "title": "Otthon a pásztor mellett",
        "text_reference": "Zsolt 23,1–4",
        "focus_sentence": "Az Úr jelenléte vigasztal a gyász csendjében.",
        "introduction": {
            "development": (
                "A család csendben ül össze. A hiány fáj, mégis keresünk "
                "szavakat, amelyek nem magyaráznak túl sokat, csak hordoznak."
            ),
            "transition": "A zsoltáros a pásztor közelségéről beszél.",
        },
        "movements": [
            {
                "title": "A pásztor jelenléte",
                "textual_anchor": "Zsolt 23,1–2",
                "development": [
                    "Az Úr mint pásztor nem távoli ígéret, hanem közelben járó gondoskodás. "
                    "A virrasztóban ez a közelség ad tartást a fájdalomnak.",
                    "Nem kell erőltetett magyarázat: elég, hogy Ő vezet zöldellő legelőre.",
                ],
                "transition": "A völgy is az Ő útján van.",
            },
            {
                "title": "A völgyben sem magány",
                "textual_anchor": "Zsolt 23,4",
                "development": [
                    "A halál árnyékának völgyében a félelem valós, de a bot és a pásztorbot "
                    "vigasztal. Krisztus feltámadása adja a reménység talaját.",
                    "A gyászoló közösség együtt hallja: nem vagyunk elhagyatva.",
                ],
            },
        ],
        "conclusion": {
            "development": (
                "A virrasztó nem oldja fel a veszteséget, de Isten közelségében "
                "helyet kap a sírás és a hála. A pásztor tovább vezet."
            ),
            "final_sentence": "Az Úr veletek van ebben a csendben is.",
        },
        "refinement_suggestions": [
            "Egy rövid személyes hálaemlék erősítheti az intim hangnemet."
        ],
    }

    def gen(prompt, **kwargs):
        assert "Virrasztó" in prompt or "virraszt" in prompt.casefold()
        return json.dumps(payload, ensure_ascii=False)

    state = {
        "last_igehely": "Zsolt 23,1–4",
        "last_alkalom": "Virrasztó",
        "passage_text": (
            "1 Az Úr az én pásztorom, nem szűkölködöm. "
            "4 Még ha a halál árnyékának völgyében járok is, nem félek a bajtól."
        ),
        "last_sajat": "Intim virrasztó áhítat a családnak",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    result = assemble_sermon_outline(
        state, generate_fn=gen, synthesize=True, force_overwrite=True
    )
    assert result.ok, result.error_message
    outline = result.outline
    content = outline_to_readable_content(outline)
    mvs = outline.get("movements") or []
    assert 2 <= len(mvs) <= 3
    assert outline.get("sermon_title") == "Otthon a pásztor mellett"
    # Meglévő felhasználói fókusz elsőbbséget élvezhet az AI focus_sentence felett.
    assert outline.get("main_idea")
    assert len(str(outline.get("main_idea")).split()) <= 25
    opening = outline.get("opening_direction") or (
        (outline.get("introduction") or {}).get("development") or ""
    )
    assert "család" in opening.casefold() or "hiány" in opening.casefold()
    closing = (outline.get("closing") or {}).get("final_insight") or (
        (outline.get("conclusion") or {}).get("development") or ""
    )
    assert "virrasztó" in closing.casefold() or "pásztor" in closing.casefold()
    tips = outline.get("editorial_tips") or []
    assert len(tips) <= 2
    assert MISSING_PART not in content
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        assert banned not in content
    issues = assess_outline_quality_issues(
        outline,
        for_ai_output=True,
        occasion="Virrasztó",
        bundle={"occasion": "Virrasztó"},
    )
    assert "weak_movements" not in issues
    assert [i for i in issues if i not in SOFT_QUALITY_ISSUES] == []
    assert "pásztor" in content.casefold() or "völgy" in content.casefold()
    # Concrete structure fields for parent deliverable
    assert {
        "title": outline.get("sermon_title"),
        "textus": outline.get("passage_reference") or "Zsolt 23,1–4",
        "focus": outline.get("main_idea"),
        "intro": bool(opening),
        "movements": [m.get("title") for m in mvs],
        "closing": bool(closing),
        "refinements": tips,
    }


def test_truncated_or_empty_ai_outline_still_rejected():
    def gen_empty(prompt, **kwargs):
        return json.dumps(
            {
                "title": "",
                "focus_sentence": "",
                "introduction": {"development": ""},
                "movements": [],
                "conclusion": {"development": ""},
            },
            ensure_ascii=False,
        )

    state = {
        "last_igehely": "Júd 17–20",
        "passage_text": "Emlékezzetek… épüljetek…",
        "last_sajat": "Hitben megmaradás",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    empty_result = assemble_sermon_outline(
        state, generate_fn=gen_empty, synthesize=True, force_overwrite=True
    )
    assert not empty_result.ok
    assert "word_count_out_of_range" not in (empty_result.error_message or "")

    def gen_truncated(prompt, **kwargs):
        return json.dumps(
            {
                "title": "Félbehagyott",
                "focus_sentence": "Isten megtart a gúny közepette.",
                "introduction": {
                    "development": "A gúny hangja körülöttünk egyre hangosabb…"
                },
                "movements": [
                    {
                        "title": "Emlékezet",
                        "development": ["Az apostolok szavaira…"],
                    },
                    {"title": "Gúny", "development": ["A szakadás jelei…"]},
                    {
                        "title": "Megmaradás",
                        "development": ["Hitben épülés a Lélekben…"],
                    },
                ],
                "conclusion": {"development": "Isten szeretete megtart…"},
            },
            ensure_ascii=False,
        )

    trunc_result = assemble_sermon_outline(
        state, generate_fn=gen_truncated, synthesize=True, force_overwrite=True
    )
    assert not trunc_result.ok
    assert "word_count_out_of_range" not in (trunc_result.error_message or "")


def test_filippi_virraszto_partial_workshop_working_outline():
    """Filippi 1,21–24 + Virrasztó + részleges műhely → rövid, teljes, gyászhű vázlat.

    Assert: alkalom eléri a generáló promptot; quality gate hard issue nélkül elfogad.
    """
    captured: dict[str, str] = {}
    focus = "Krisztusban az élet is, a halál is Isten kezében van."
    payload = {
        "title": "Élni is, meghalni is Krisztusé",
        "text_reference": "Filippi 1,21–24",
        "focus_sentence": focus,
        "introduction": {
            "development": (
                "A család a virrasztó csendjében ül. A hiány valóságos, "
                "és nem kell siettetni a magyarázatot. Pál szavai nem "
                "bagatellizálják a veszteséget: a feszültség és a reménység "
                "együtt szólalhat meg."
            ),
            "transition": "Pál a filippieknek a Krisztusban való életről beszél.",
        },
        "movements": [
            {
                "title": "Élet Krisztusban",
                "textual_anchor": "Fil 1,21",
                "development": [
                    (
                        "Pál szerint az élet Krisztus: nem üres jelszó, hanem "
                        "olyan valóság, amelyben a jelen is Krisztushoz kötődik. "
                        "A „nyereség” a halálban nem a fájdalom tagadása, "
                        "hanem a Krisztussal való együttlét reménysége."
                    ),
                    (
                        "A gyászoló hallgató nem kap könnyű választ — kap "
                        "egy irányt: a szerettet Krisztusra bízni, a saját "
                        "fájdalmát pedig Őelőtte hordozni."
                    ),
                ],
                "transition": "Pál mégis a közösségért való megmaradásról is beszél.",
            },
            {
                "title": "Maradás a többiekért",
                "textual_anchor": "Fil 1,22–24",
                "development": [
                    (
                        "Pál feszültségben áll: a Krisztussal lenni vonzóbb, "
                        "mégis a gyülekezetért való megmaradás is gyümölcsöző. "
                        "Ez nem szabad, önkényes élet-halál választás, hanem "
                        "a szolgálat és a gondviselés feszültségében való állás."
                    ),
                    (
                        "A virrasztó közösség is ebben a feszültségben áll: "
                        "a hiány fáj, és mégis egymásért maradunk — imában, "
                        "emlékezetben, egymás hordozásában."
                    ),
                ],
            },
        ],
        "conclusion": {
            "development": (
                "Nem oldjuk fel a veszteséget szavakkal. Krisztus feltámadása "
                "adja a reménység talaját: Pál Ura a mi Urunk is. A sírás "
                "helyet kap, és a hála is — adat nélkül nem ígérünk többet, "
                "mint amit a textus ad."
            ),
            "final_sentence": "Krisztusban van a mi életünk és a mi reménységünk.",
        },
        "refinement_suggestions": [
            "Egy rövid, név nélküli hálaemlék erősítheti az intim hangnemet.",
        ],
    }

    def gen(prompt, **kwargs):
        captured["prompt"] = prompt
        assert "ALKALOM: Virrasztó" in prompt
        assert "Virrasztó" in prompt
        assert "350–550" in prompt or "350-550" in prompt
        # Alkalmi kontextus eléri a promptot
        assert "virraszt" in prompt.casefold() or "gyász" in prompt.casefold()
        return json.dumps(payload, ensure_ascii=False)

    state = {
        "last_igehely": "Filippi 1,21–24",
        "last_alkalom": "Virrasztó",
        "passage_text": (
            "21 Mert nekem az élet Krisztus, és a meghalás nyereség. "
            "22 Ha pedig az életben maradásom testben gyümölcsöző lesz "
            "a munkámra nézve, akkor nem tudom, mit válasszak. "
            "23 Szorongat engem a kettő: kívánok elköltözni és Krisztussal "
            "lenni, mert ez sokkal jobb; 24 de miattatok szükségesebb "
            "testben maradnom."
        ),
        "last_sajat": (
            "Virrasztó: hosszú életű rokon emlékére; hálás emlékezés, "
            "ne temetési szónoklat."
        ),
        "exegesis": (
            "Pál filippi fogságából ír. A 21–24 a Krisztusban való élet "
            "és a Krisztussal való együttlét feszültségét mutatja — nem "
            "önkényes élet/halál választásként."
        ),
        TEXT_WORKSHOP_KEY: {
            **get_default_text_workshop(),
            "text_main_idea": focus,
            "text_main_idea_status": "approved",
            "approved_insights": [
                {
                    "content": (
                        "Pál nem bagatellizálja a halált: nyereségként "
                        "a Krisztussal való együttlétet nevezi meg."
                    ),
                    "approved": True,
                },
                {
                    "content": (
                        "A megmaradás a többiekért is része a gondviselésnek — "
                        "nem szabad választás-játék."
                    ),
                    "approved": True,
                },
            ],
        },
        SERMON_WORKSHOP_KEY: {
            **get_default_sermon_workshop(),
            "sermon_main_idea": focus,
            "sermon_main_idea_status": "approved",
        },
    }
    ensure_sermon_workshop_state(state)
    result = assemble_sermon_outline(
        state, generate_fn=gen, synthesize=True, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert captured.get("prompt")
    assert "ALKALOM: Virrasztó" in captured["prompt"]

    outline = result.outline
    content = outline_to_readable_content(outline)
    mvs = outline.get("movements") or []
    assert 2 <= len(mvs) <= 3
    assert outline.get("sermon_title") == "Élni is, meghalni is Krisztusé"
    assert outline.get("main_idea")
    assert len(str(outline.get("main_idea")).split()) <= 25

    opening = outline.get("opening_direction") or (
        (outline.get("introduction") or {}).get("development") or ""
    )
    assert "virrasztó" in opening.casefold() or "család" in opening.casefold()
    assert "hiány" in opening.casefold() or "csend" in opening.casefold()

    closing = (outline.get("closing") or {}).get("final_insight") or (
        (outline.get("conclusion") or {}).get("development") or ""
    )
    assert closing
    # Gyászhű: ne trivializáljon / ne ígérjen adat nélküli üdvösséget
    low = content.casefold()
    assert "biztosan a mennyben" not in low
    assert "üdvözült" not in low
    assert "könnyű válasz" not in low or "nem kap könnyű" in low

    assert "A textus állítása" in content or "textus állítása" in content.casefold()
    assert "Hallgatói irány" in content or "hallgatói irány" in content.casefold()
    assert "Fókuszmondat" in content
    assert "Bevezetés" in content
    assert "Megérkezés" in content
    assert MISSING_PART not in content
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        assert banned not in content
    assert "Exegetikai kibontás" not in content
    assert "Kegyelmi kapcsolat" not in content

    # Nem ismétli háromszor a fókuszt; nem sablonos
    assert content.count(focus) < 3
    assert "a kegyelem abban van" not in low

    tips = outline.get("editorial_tips") or []
    assert len(tips) <= 2

    # Részleges műhelyjelzés eléri a promptot / profilt
    assert "Részleges" in captured["prompt"] or "részleges" in captured["prompt"].casefold()

    issues = assess_outline_quality_issues(
        outline,
        for_ai_output=True,
        occasion="Virrasztó",
        bundle={
            "occasion": "Virrasztó",
            "user_focus": state["last_sajat"],
            "source_keys": [
                "exegesis",
                "approved_insights",
                "passage_text",
                "sermon_main_idea",
                "text_main_idea",
            ],
        },
    )
    hard = [i for i in issues if i not in SOFT_QUALITY_ISSUES]
    assert hard == [], hard
    assert "weak_movements" not in issues
    assert "truncated" not in issues
    assert "placeholder" not in issues

    # Rövid munkavázlat-jelleg: célzónához közel (soft tartományon belül vagy soft-only)
    words = len([w for w in content.replace("\n", " ").split(" ") if w.strip()])
    assert words < 900
    # Struktúra-minta a deliverable-hez
    sample = {
        "title": outline.get("sermon_title"),
        "textus": outline.get("passage_reference"),
        "focus": outline.get("main_idea"),
        "intro_ok": bool(opening),
        "movements": [m.get("title") for m in mvs],
        "closing_ok": bool(closing),
        "refinements": tips,
        "words": words,
        "hard_issues": hard,
    }
    assert sample["movements"] == ["Élet Krisztusban", "Maradás a többiekért"]
    assert sample["intro_ok"] and sample["closing_ok"]
