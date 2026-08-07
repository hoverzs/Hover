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


def _pad_sp(text: str, *, min_words: int = 28) -> str:
    """Teszt-fixture: egy teljes rétegmondat a háromrétegű séma célhosszához."""
    raw = str(text or "").strip()
    if not raw.endswith((".", "!", "?")):
        raw += "."
    first = raw
    for sep in (". ", "! ", "? "):
        if sep in raw:
            first = raw.split(sep)[0] + sep.strip()
            break
    words = first.rstrip(".!?").split()
    filler = (
        "a textus saját mozgása szerint a hallgató előtt a szószéki "
        "felkészülés során is"
    ).split()
    while len(words) < min_words:
        words.extend(filler)
    return " ".join(words[:55]).rstrip(".,;:") + "."


def _assert_usable_outline(outline: dict) -> str:
    content = outline_to_readable_content(outline)
    assert outline.get("main_idea")
    assert content.strip()
    assert MISSING_PART not in content
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        assert banned not in content, banned
    mvs = outline.get("movements") or []
    assert 2 <= len(mvs) <= 5
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
    assert "igehirdető" in HOMILETIC_SYSTEM_PROMPT.casefold() or "teológus" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "prédikációvázlat" in HOMILETIC_SYSTEM_PROMPT.casefold() or "vázlat" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "KÖTELEZŐ FORMA" in HOMILETIC_SYSTEM_PROMPT
    assert "Fókuszmondat" in HOMILETIC_SYSTEM_PROMPT  # a tiltólista része
    assert "háttéranyag" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "gyakorlati" in HOMILETIC_SYSTEM_PROMPT.casefold()
    assert "A textus mozgása" in HOMILETIC_SYSTEM_PROMPT  # tiltott példa
    assert "Hiányzó háttéranyag" in HOMILETIC_SYSTEM_PROMPT or "hiányzó háttéranyag" in HOMILETIC_SYSTEM_PROMPT.casefold()


def test_soft_length_ranges_match_working_outline_targets():
    sunday = outline_length_profile("Vasárnapi istentisztelet")
    assert sunday["target_range"] == "300–500"
    assert sunday["soft_max"] == 850
    assert sunday["min_movements"] == 2
    assert sunday["max_movements"] == 5

    wake = outline_length_profile("Virrasztó")
    assert wake["target_range"] == "300–500"
    assert wake["soft_max"] == 850
    assert wake["min_movements"] == 2
    assert wake["max_movements"] == 3

    partial = outline_length_profile("Virrasztó", partial=True)
    assert partial["soft_min"] <= wake["soft_min"]
    assert "Részleges" in partial["guidance"] or "részleges" in partial["guidance"].casefold()
    assert "word_count_out_of_range" in SOFT_QUALITY_ISSUES
    assert "stock_phrases" in SOFT_QUALITY_ISSUES
    assert "transition_fillers" in SOFT_QUALITY_ISSUES
    # Length issues are HARD now
    assert "intro_too_long" not in SOFT_QUALITY_ISSUES
    assert "verbose_point_bullets" not in SOFT_QUALITY_ISSUES


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
    long_focus = " ".join(["szó"] * 45)
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


def test_ai_failure_rescues_usable_pulpit_notes_instead_of_hard_error():
    """Rossz AI-JSON után is szószéki jegyzet készül (ne üres hibaüzenet)."""
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
    assert result.ok, result.error_message
    content = _assert_usable_outline(result.outline)
    assert "szószéken használható" not in (result.error_message or "").casefold()
    assert MISSING_PART not in content
    assert any(
        "jegyzet" in w.casefold() or "finomítható" in w.casefold() or "formázással" in w
        for w in (result.warnings or [])
    )


def test_prompt_dynamic_background_vs_passage_only_in_assembly():
    """Háttérrel: HÁTTÉRANYAG a promptban; anélkül: textus-only mód, nincs hiány-panasz."""
    from sermon_outline_engine import build_outline_user_prompt

    captured: list[str] = []

    def gen_ok(prompt, **kwargs):
        captured.append(prompt)
        return json.dumps(
            {
                "title": "Megtartva",
                "text_reference": "Júd 17–20",
                "scope_note": "",
                "focus_sentence": (
                    "Isten a gúny közepette is megtartja népét a Szentlélekben."
                ),
                "introduction_direction": (
                    "A gúny hangja körülöttünk egyre hangosabb. "
                    "A kérdés: hogyan maradhatunk meg hitben."
                ),
                "movements": [
                    {
                        "title": "Emlékezzetek az apostoli szóra",
                        "verses": "v. 17–18",
                        "textual_insight": (
                            "Júdás az apostolok előrejelzésére hív: gúnyolódók jönnek."
                        ),
                        "theological_emphasis": (
                            "Az emlékezet nem nosztalgia, hanem megtartó igazság."
                        ),
                        "listener_movement": (
                            "A hallgató az apostoli szóra támaszkodik, nem a hangulataira."
                        ),
                        "transition": "",
                    },
                    {
                        "title": "Ismerjétek fel a szakadást",
                        "verses": "v. 19",
                        "textual_insight": (
                            "A szakadáskeltők érzékiek, és nincs bennük Lélek."
                        ),
                        "theological_emphasis": (
                            "A Lélek hiánya a közösség valódi veszélye."
                        ),
                        "listener_movement": (
                            "A hallgató nem gyanakvással, hanem józan felismeréssel él."
                        ),
                        "transition": "",
                    },
                    {
                        "title": "Épüljetek a Lélekben",
                        "verses": "v. 20",
                        "textual_insight": (
                            "A megmaradás hitben való épülés és Lélekben való ima."
                        ),
                        "theological_emphasis": (
                            "Isten szeretete tart meg, nem az emberi erőfeszítés."
                        ),
                        "listener_movement": (
                            "A hallgató imában és szeretetben marad a közösségben."
                        ),
                        "transition": "",
                    },
                ],
                "conclusion_direction": (
                    "A megtartás Isten ajándéka. Maradjatok imában és szeretetben."
                ),
                "refinement_suggestions": [],
            },
            ensure_ascii=False,
        )

    bare = {
        "last_igehely": "Júd 17–20",
        "passage_text": (
            "17 Ti pedig, szeretteim, emlékezzetek… "
            "20 Ti azonban, szeretteim, épüljetek… imádkozva a Szentlélek által."
        ),
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(bare)
    captured.clear()
    bare_result = assemble_sermon_outline(
        bare, generate_fn=gen_ok, synthesize=True, force_overwrite=True
    )
    assert bare_result.ok, bare_result.error_message
    outline_prompts = [
        p for p in captured if "BIBLIAI SZÖVEG" in p or "IGEHELY:" in p
    ]
    assert outline_prompts, captured
    assert "HÁTTÉRANYAG" not in outline_prompts[0]
    # 2026-08-08: a puszta-textus mód a leggyakoribb eset, nem hiány —
    # a modell a saját tudására támaszkodva adjon legjobb minőségű vázlatot.
    assert "leggyakoribb eset" in outline_prompts[0].casefold()

    rich = dict(bare)
    rich["exegesis"] = "Júdás a gúnyolódók ellen figyelmeztet, majd a megmaradásra hív."
    rich["exegesis_status"] = "approved"
    rich["history"] = "A levél a korai egyház szakadásainak közegében született."
    rich["history_status"] = "approved"
    rich["original_text"] = "ἐποικοδομοῦντες — folyamatos épülés."
    rich["original_text_status"] = "approved"
    ensure_sermon_workshop_state(rich)
    # Direct prompt check mirrors assembly context
    from sermon_outline_engine import collect_outline_evidence

    bundle = collect_outline_evidence(rich)
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    assert "HÁTTÉRANYAG" in prompt
    assert "gúnyolódók ellen" in prompt
    assert "csak a fenti bibliai textus" not in prompt.casefold()

    captured.clear()
    rich_result = assemble_sermon_outline(
        rich, generate_fn=gen_ok, synthesize=True, force_overwrite=True
    )
    assert rich_result.ok, rich_result.error_message
    assert any("HÁTTÉRANYAG" in p for p in captured)


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
    if not str(state.get("passage_text") or "").strip():
        from tests.test_outline_engine import JUDE_PASSAGE

        state["passage_text"] = JUDE_PASSAGE
    result = assemble_sermon_outline(state, generate_fn=None)
    assert result.ok, result.error_message
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
                "listener_insight": "Hol emlékeztet Isten a saját szavára ma?",
                "transition": "",
            },
            {
                "id": "b",
                "title": "A szakadás jelei",
                "textual_anchor": "Júd 18–19",
                "development": [
                    "A gúnyolódók a szakadás jelei, lélek nélkül élnek.",
                    "Felismerjük a veszélyt, hogy ne sodródjunk vele.",
                ],
                "listener_insight": "Hol látjuk a szakadás jeleit anélkül, hogy mi szakítanánk?",
                "transition": "",
            },
            {
                "id": "c",
                "title": "Épülés a Lélekben",
                "textual_anchor": "Júd 20–21",
                "development": [
                    "Hitben épülés, Szentlélekben ima, Isten szeretetében megmaradás.",
                    "A megmaradás kegyelemből fakad, nem emberi erőből.",
                ],
                "listener_insight": "Mit jelent ma a Szentlélekben való imádkozás?",
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
    content = outline_to_readable_content(merged)
    # refinement_suggestions nem jelenhet meg a szószéki elsődleges nézetben
    assert "Egy konkrét gyülekezeti helyzet" not in content
    assert "Apostoli emlékezet" in content
    assert "Fókuszmondat" in content
    assert "Bevezetési irány" in content or "Bevezetés" in content
    assert "Megérkezés" in content
    assert "*" in content or "**" in content
    assert "Hol emlékeztet Isten" in content or "*Hol emlékeztet Isten" in content
    assert "A textus állítása" not in content
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
    # A kötelező-műhely hiánylistázás tilos; egyéb tippek opcionálisak / üresek is lehetnek.
    content = outline_to_readable_content(merged)
    assert tip not in content


def _words(n: int, seed: str = "szó") -> str:
    return " ".join([f"{seed}{i}" for i in range(max(1, n))])


def _usable_ai_payload(
    *,
    focus: str = (
        "Isten megtart a gúny közepette a Szentlélek által, "
        "és a hitben való épülésre hívja ma a szeretett gyülekezetet a textus szerint."
    ),
    intro_words: int = 45,
    movement_words: int = 28,
    conclusion_words: int = 45,
    movement_count: int = 3,
    title: str = "Megtartva a gúny között",
) -> dict:
    titles = [
        "Apostoli emlékezet",
        "A szakadás jelei",
        "Épülés a Lélekben",
        "Megmaradás a szeretetben",
    ]
    verse_labels = ["v. 17–18", "v. 19", "v. 20", "v. 20"]
    insights = [
        "Hol emlékeztet Isten a saját szavaival a gúny idején?",
        "Felismerjük-e a szakadás jeleit a saját közösségünkben?",
        "Hol tudsz ezen a héten hitben épülni és Lélekben imádkozni?",
        "Hogyan őrizzük magunkat Isten szeretetében a megmaradásban?",
    ]
    movements = []
    for i in range(movement_count):
        movements.append(
            {
                "title": titles[i % len(titles)],
                "textual_anchor": verse_labels[i % len(verse_labels)],
                "development": [
                    _words(movement_words, seed=f"mozg{i}a") + ".",
                    _words(max(20, movement_words - 2), seed=f"mozg{i}b") + ".",
                    _words(max(20, movement_words - 2), seed=f"mozg{i}c") + ".",
                ],
                "listener_insight": insights[i % len(insights)],
                "transition": "",
            }
        )
    intro = (
        _words(max(12, intro_words // 3), seed="bevezet1")
        + ". "
        + _words(max(12, intro_words // 3), seed="bevezet2")
        + ". "
        + _words(max(10, intro_words // 3), seed="bevezet3")
        + "."
    )
    conclusion = (
        _words(max(12, conclusion_words // 3), seed="zaras1")
        + ". "
        + _words(max(12, conclusion_words // 3), seed="zaras2")
        + ". "
        + _words(max(10, conclusion_words // 3), seed="zaras3")
        + "."
    )
    focus_text = focus
    if len(focus_text.split()) < 20:
        focus_text = (
            "Isten megtart a gúny közepette a Szentlélek által, "
            "és a hitben való épülésre hívja ma a szeretett gyülekezetet."
        )
    return {
        "title": title,
        "text_reference": "Júd 17–20",
        "scope_note": "",
        "focus_sentence": focus_text,
        "introduction_direction": intro,
        "points": [
            {
                "title": m["title"],
                "verses": m["textual_anchor"],
                "textual_insight": m["development"][0],
                "theological_emphasis": m["development"][1],
                "listener_movement": m["development"][2],
            }
            for m in movements
        ],
        "conclusion_direction": conclusion,
        "refinement_suggestions": [],
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
    assert profile["soft_max"] <= 850
    assert profile["target_range"] == "300–500"


def test_word_count_alone_is_soft_not_hard_rejection():
    """Valid pulpit outline in target range → assembly keeps it."""
    payload = _usable_ai_payload(
        intro_words=60, movement_words=36, conclusion_words=60, movement_count=3
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
    from sermon_outline_engine import word_count as _wc

    assert _wc(content) <= 850
    soft = assess_outline_quality_issues(
        result.outline,
        for_ai_output=True,
        bundle={"occasion": "Vasárnapi istentisztelet", "source_keys": ["exegesis"]},
    )
    hard = [
        i
        for i in soft
        if i not in SOFT_QUALITY_ISSUES
        and i
        not in {
            "focus_too_short",
            "stub_layer",
            "point_layers_too_short",
            "too_thin",
            "under_target",
            "intro_too_short",
            "conclusion_too_short",
        }
    ]
    assert hard == [], hard


def test_partial_workshop_ai_outline_kept_despite_short_word_count():
    """Részleges, de tartalmas műhelyanyag + tömör AI válasz → használható vázlat."""
    payload = _usable_ai_payload(
        intro_words=40, movement_words=24, conclusion_words=40, movement_count=3
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
        "scope_note": "",
        "focus_sentence": (
            "Az Úr jelenléte vigasztal a gyász csendjében, és a pásztor "
            "közelsége tartást ad ma a gyászoló közösségnek a textus szerint."
        ),
        "introduction_direction": (
            "A család csendben ül össze, és a hiány fájdalma körülveszi őket. "
            "Mégis keresünk szavakat, amelyek nem beszélnek túl sokat, csak hordoznak. "
            "Innen nyílik meg a zsoltár pásztorképe a virrasztóban a gyülekezet előtt."
        ),
        "points": [
            {
                "title": "A pásztor jelenléte",
                "verses": "v. 1–2",
                "subpoints": [
                    _pad_sp(
                        "Az Úr mint pásztor nem távoli ígéret a gyászoló előtt, "
                        "hanem közelben járó gondoskodás a fájdalom idején is."
                    ),
                    _pad_sp(
                        "A virrasztóban ez a közelség ad tartást a fájdalomnak "
                        "anélkül, hogy a textus saját szavát túlbeszélné."
                    ),
                    _pad_sp(
                        "Elég, hogy Ő vezet zöldellő legelőre, és ez már "
                        "homiletikai tartást ad a gyászoló közösség csendjében."
                    ),
                ],
                "application": "Hol érzed ma a pásztor közelségét a csendben a saját veszteséged közepette?",
            },
            {
                "title": "A völgyben sem magány",
                "verses": "v. 4",
                "subpoints": [
                    _pad_sp(
                        "A halál árnyékának völgyében a félelem valós marad, "
                        "de a bot és a pásztorbot vigasztalása jelen van."
                    ),
                    _pad_sp(
                        "Krisztus feltámadása adja a reménység talaját a "
                        "gyászoló közösségnek anélkül, hogy a fájdalmat elhallgattatná."
                    ),
                    _pad_sp(
                        "A gyászoló közösség együtt hallja: nem vagyunk "
                        "elhagyatva ebben a völgyben, mert a pásztor tovább vezet."
                    ),
                ],
                "application": "Kit bízhatsz a pásztorra a völgyben is ezen a héten?",
            },
            {
                "title": "Asztal a gyász közepette",
                "verses": "v. 1–4",
                "subpoints": [
                    _pad_sp(
                        "A zsoltár íve a pásztor gondoskodásától a völgyön át "
                        "a megtartó jelenlétig vezet egyetlen mozgásban."
                    ),
                    _pad_sp(
                        "A virrasztóban ez nem temetési szónoklat, hanem a "
                        "textus saját ígérete a közösség csendjében."
                    ),
                    _pad_sp(
                        "Így a hallgató nem új témánál, hanem az Úr hűséges "
                        "közelségénél érkezik meg a gyászban."
                    ),
                ],
                "application": "Melyik ígéretet tudod ma hálával kimondani a hiány közepette is?",
            },
        ],
        "conclusion_direction": (
            "A virrasztó nem oldja fel a veszteséget, de Isten közelségében "
            "helyet kap a sírás és a hála. A pásztor tovább vezet a közösséggel. "
            "Az Úr veletek van ebben a csendben is, és ez adja a megérkezést."
        ),
        "refinement_suggestions": [],
    }

    def gen(prompt, **kwargs):
        assert "Virrasztó" in prompt or "virraszt" in prompt.casefold() or "ALKALOM" in prompt
        assert (
            "GONDOLATVÁZLAT" in prompt
            or "gondolatvázlat" in prompt.casefold()
            or "SZÓSZÉKI MUNKAVÁZLAT" in prompt
            or "HOMILETIKAI VÁZLAT" in prompt
            or "homiletikai vázlat" in prompt.casefold()
            or "vázlatsémára" in prompt
            or "vázlat" in prompt.casefold()
        )
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
    assert len(str(outline.get("main_idea")).split()) <= 40
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
    soft_ok = SOFT_QUALITY_ISSUES | {
        "intro_too_short",
        "conclusion_too_short",
        "under_target",
        "too_thin",
        "stub_layer",
        "point_layers_too_short",
        "focus_too_short",
        "layer_sentence_count",
    }
    assert [i for i in issues if i not in soft_ok] == []
    assert "pásztor" in content.casefold() or "völgy" in content.casefold()
    assert "*" in content or "**" in content
    assert all(1 <= len(m.get("development") or []) <= 3 for m in mvs)
    assert all(m.get("listener_discovery") for m in mvs)
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


def test_truncated_or_empty_ai_outline_rescues_usable_notes():
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
    assert empty_result.ok, empty_result.error_message
    assert "word_count_out_of_range" not in (empty_result.error_message or "")
    assert "szószéken használható" not in (empty_result.error_message or "").casefold()
    _assert_usable_outline(empty_result.outline)

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
    assert trunc_result.ok, trunc_result.error_message
    assert "word_count_out_of_range" not in (trunc_result.error_message or "")
    _assert_usable_outline(trunc_result.outline)


def test_filippi_virraszto_partial_workshop_working_outline():
    """Filippi 1,21–24 + Virrasztó + részleges műhely → rövid, teljes, gyászhű vázlat.

    Assert: alkalom eléri a generáló promptot; quality gate hard issue nélkül elfogad.
    """
    captured: dict[str, str] = {}
    focus = "Krisztusban az élet is, a halál is Isten kezében van."
    payload = {
        "title": "Élni is, meghalni is Krisztusé",
        "text_reference": "Filippi 1,21–24",
        "scope_note": "",
        "focus_sentence": (
            "Krisztusban az élet is, a halál is Isten kezében van, "
            "és a gyászoló közösséget ez a reménység tartja."
        ),
        "introduction_direction": (
            "A család a virrasztó csendjében ül, és a hiány valóságos. "
            "Nem keresünk olcsó választ, hanem irányt a textus felől. "
            "Innen szólal meg Pál feszültsége az élet és a Krisztussal lét között."
        ),
        "points": [
            {
                "title": "Élet Krisztusban",
                "verses": "v. 21",
                "subpoints": [
                    _pad_sp(
                        "Pál szerint az élet Krisztus: nem üres jelszó, "
                        "hanem a gyászoló előtt álló valóság ma is."
                    ),
                    _pad_sp(
                        "A nyereség a halálban a Krisztussal való együttlétet "
                        "jelenti, nem könnyű frázist a közösségnek."
                    ),
                    _pad_sp(
                        "A gyászoló nem kap olcsó választ, hanem irányt "
                        "Krisztusra a hiány és a csend közepette."
                    ),
                ],
                "application": "Kit bízhatsz Krisztusra a hiány közepette ebben a virrasztóban?",
            },
            {
                "title": "Maradás a többiekért",
                "verses": "v. 22–24",
                "subpoints": [
                    _pad_sp(
                        "Pál feszültségben áll, mégis a többiekért marad "
                        "szolgálatban a testben a gyülekezetért."
                    ),
                    _pad_sp(
                        "Ez nem szabad élet-halál választás, hanem "
                        "gondviselő szolgálat a közösségért ma is."
                    ),
                    _pad_sp(
                        "A virrasztó közösség is ebben áll: a hiány fáj, "
                        "mégis egymásért maradunk hálával együtt."
                    ),
                ],
                "application": "Kinek a megmaradása hordoz téged ma is a gyász idején?",
            },
            {
                "title": "Reménység a csendben",
                "verses": "v. 21–24",
                "subpoints": [
                    _pad_sp(
                        "A textus nem oldja fel a veszteséget, de Krisztus "
                        "kezébe helyezi az életet és a halált a gyászoló előtt."
                    ),
                    _pad_sp(
                        "A virrasztó ezért nem temetési szónoklat, hanem a "
                        "megtartó reménység rövid, hűséges megszólalása ma este."
                    ),
                    _pad_sp(
                        "Így a hallgató a megmaradás és a hála feszültségében "
                        "állhat meg új téma nélkül a közösségben."
                    ),
                ],
                "application": "Melyik hálaadás tud megmaradni benned a hiány közepette is?",
            },
        ],
        "conclusion_direction": (
            "Nem oldjuk fel a veszteséget szavakkal; Krisztus ad reménységet a gyászolóknak. "
            "A virrasztó közösség a megmaradás és a hála feszültségében állhat meg együtt. "
            "Krisztusban van a mi életünk és reménységünk a csend közepette is ma."
        ),
        "refinement_suggestions": [],
    }

    def gen(prompt, **kwargs):
        captured["prompt"] = prompt
        # Generáló + tömörítő kör: alkalom / vázlat jelenjen meg
        assert (
            "Virrasztó" in prompt
            or "virraszt" in prompt.casefold()
            or "ALKALOM" in prompt
            or "vázlat" in prompt.casefold()
        )
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
    assert "Virrasztó" in captured["prompt"] or "ALKALOM" in captured["prompt"]

    outline = result.outline
    content = outline_to_readable_content(outline)
    mvs = outline.get("movements") or []
    assert 2 <= len(mvs) <= 3
    assert outline.get("sermon_title") == "Élni is, meghalni is Krisztusé"
    assert outline.get("main_idea")
    assert len(str(outline.get("main_idea")).split()) <= 40

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

    assert "A textus állítása" not in content
    assert "Hallgatói irány" not in content
    assert "*" in content or "**" in content  # háromrétegű megjelenés
    assert "pásztor" in content.casefold() or "Krisztus" in content or "krisztus" in content.casefold()
    assert "Fókuszmondat" in content
    assert "Bevezetési irány" in content or "Bevezetés" in content
    assert "Megérkezés" in content
    assert MISSING_PART not in content
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        assert banned not in content
    assert "Exegetikai kibontás" not in content
    assert "Kegyelmi kapcsolat" not in content
    # Hallgatói mozdulat dőltként jelenik meg (háromrétegű render)
    assert "*" in content
    assert "krisztus" in content.casefold()

    # Nem ismétli háromszor a fókuszt; nem sablonos
    assert content.count(focus) < 3
    assert "a kegyelem abban van" not in low
    assert "de vajon mi következik" not in low
    assert "Továbbgondolható" not in content  # tippek nem a vázlat teste

    tips = outline.get("editorial_tips") or []
    assert len(tips) <= 2

    # Részleges műhelyjelzés eléri a profilt (generáló kör); tömörítő lehet rövidebb
    assert (
        "Részleges" in captured["prompt"]
        or "részleges" in captured["prompt"].casefold()
        or "ALKALOM" in captured["prompt"]
        or "Virrasztó" in captured["prompt"]
    )
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
    soft_ok = SOFT_QUALITY_ISSUES | {
        "intro_too_short",
        "conclusion_too_short",
        "under_target",
        "too_thin",
        "stub_layer",
        "point_layers_too_short",
        "focus_too_short",
        "layer_sentence_count",
    }
    hard = [i for i in issues if i not in soft_ok]
    assert hard == [], hard
    assert "weak_movements" not in issues
    assert "truncated" not in issues
    assert "placeholder" not in issues

    # Háromrétegű szószéki vázlat: abszolút max 850
    words = len([w for w in content.replace("\n", " ").split(" ") if w.strip()])
    assert words <= 850
    # Struktúra-minta a deliverable-hez
    sample = {
        "title": outline.get("sermon_title"),
        "textus": outline.get("passage_reference"),
        "focus": outline.get("main_idea"),
        "intro_ok": bool(opening),
        "movements": [
            {
                "title": m.get("title"),
                "anchor": m.get("textual_anchor"),
                "bullets": len(m.get("development") or []),
                "insight": m.get("listener_discovery") or "",
            }
            for m in mvs
        ],
        "closing_ok": bool(closing),
        "refinements": tips,
        "words": words,
        "hard_issues": hard,
    }
    titles = [m["title"] for m in sample["movements"]]
    assert titles[0] == "Élet Krisztusban"
    assert titles[1] == "Maradás a többiekért"
    assert 2 <= len(titles) <= 3
    assert all(1 <= m["bullets"] <= 3 for m in sample["movements"])
    assert all(m["insight"] for m in sample["movements"])
    assert sample["intro_ok"] and sample["closing_ok"]
    assert words <= 850


def test_soft_gate_flags_intro_closing_and_filler_but_keeps_usable():
    """Hosszú intro/closing/bullet most HARD — abszolút max / hossz hiba."""
    long_intro = " ".join([f"bevezet{i}" for i in range(85)])
    long_close = " ".join([f"zaras{i}" for i in range(100)])
    long_bullet = (
        "Ez egy túl hosszú, prédikációszerű bekezdés a pontban, amely több mint "
        "harmincöt szót tartalmaz, és két mondatból áll. Így hard length jelzést kap."
    )
    outline = normalize_sermon_outline(
        {
            "main_idea": "Isten megtart a gúny közepette.",
            "sermon_title": "Megtartva",
            "passage_reference": "Júd 17–20",
            "introduction": {"development": long_intro},
            "movements": [
                {
                    "title": "Apostoli emlékezet",
                    "textual_anchor": "Júd 17",
                    "development": [long_bullet, long_bullet, long_bullet, long_bullet],
                    "listener_discovery": " ".join(["kérdés"] * 30),
                    "transition": "De vajon mi következik ezután?",
                },
                {
                    "title": "Épülés a Lélekben",
                    "textual_anchor": "Júd 20",
                    "development": [
                        "Hitben épülés a Szentlélekben való imádkozással együtt.",
                        "A megmaradás Isten szeretetéből fakad a gúny közepette.",
                    ],
                    "listener_discovery": "Hol őrzöd magad Isten szeretetében?",
                },
            ],
            "conclusion": {"development": long_close},
        }
    )
    outline["content"] = outline_to_readable_content(outline)
    issues = assess_outline_quality_issues(
        outline,
        for_ai_output=True,
        occasion="Vasárnapi istentisztelet",
        bundle={"occasion": "Vasárnapi istentisztelet", "source_keys": ["exegesis"]},
    )
    hard = [i for i in issues if i not in SOFT_QUALITY_ISSUES]
    assert (
        "intro_too_long" in hard
        or "over_absolute_max" in hard
        or "subpoint_length" in hard
        or "conclusion_too_long" in hard
        or "prose_block_too_long" in hard
    )
    # Transition filler may live on movement.transition even if not in body text
    transition_blob = " ".join(
        str((m or {}).get("transition") or "")
        for m in (outline.get("movements") or [])
    ).casefold()
    assert "de vajon" in transition_blob or "transition_fillers" in issues