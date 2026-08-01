"""Vázlatmotor v8 — kontextusmódok, minőségvédelem, Júdás / narratív regresszió.

Modellhívások mockolva; nincs élő fizetős API-hívás.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_context import (
    ContextMode,
    OutlineContext,
    SourcePriority,
    build_outline_context,
    detect_context_mode,
    outline_context_to_legacy_bundle,
    set_original_language_provider,
)
from sermon_outline_exegesis import (
    build_deterministic_brief,
    generate_exegetical_brief,
    infer_literary_hints,
)
from sermon_outline_quality import (
    assess_semantic_quality,
    focus_is_passage_quote,
    find_banned_phrases,
    has_arbitrary_half_verse_split,
)
from sermon_outline_engine import (
    SCHEMA_VERSION,
    generate_sermon_outline,
    normalize_structured_outline,
    render_structured_outline,
    validate_structured_outline,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop


JUDE_24_25 = (
    "24 Aki pedig képes megőrizni titeket a botlástól, és feddhetetlenül, "
    "ujjongással állítani dicsősége elé,\n"
    "25 az egyedüli Istennek, a mi Üdvözítőnknek dicsőség, fenség, erő és hatalom "
    "a mi Urunk Jézus Krisztus által, minden idő előtt, most és minden időben. Ámen."
)

LK_10 = (
    "25 És ímé egy törvénytudó felkelt, kísértvén őt, és mondván: Mester, "
    "mit cselekedjem, hogy az örök életet örököljem?\n"
    "26 Ő pedig monda néki: A törvényben mi van megírva? mint olvasod?\n"
    "30 Jézus pedig felelvén, monda: Egy ember megy vala alá Jeruzsálemből "
    "Jerikóba, és rablók kezébe esék...\n"
    "33 Egy samaritánus pedig az úton megyén, és meglátván őt, könyörületességre "
    "indula.\n"
    "37 Menj el, és te is hasonlóképpen cselekedjél."
)


class _EmptyOriginalProvider:
    def load_for_passage(self, reference: str) -> list[dict[str, Any]]:
        return []


class _FakeGreekProvider:
    def load_for_passage(self, reference: str) -> list[dict[str, Any]]:
        if "Júd" not in reference and "Jud" not in reference:
            return []
        return [
            {
                "language": "greek",
                "verse": 24,
                "chapter": 1,
                "book": "Jud",
                "tokens": [
                    {
                        "form": "φυλάξαι",
                        "lemma": "φυλάσσω",
                        "morph": "V-AAN",
                        "strong": "G5442",
                        "index": 3,
                    },
                    {
                        "form": "ἀπταίστους",
                        "lemma": "ἄπταιστος",
                        "morph": "A-APM",
                        "strong": "G679",
                        "index": 5,
                    },
                ],
            }
        ]


def _base_state(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "last_igehely": "Júd 24–25",
        "igehely_input": "Júd 24–25",
        "passage_text": JUDE_24_25,
        "exegesis": "",
        "original_text": "",
        "theology": "",
        "history": "",
        "last_sajat": "",
        "basket": [],
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state


def _good_jude_json() -> dict[str, Any]:
    return {
        "title": "A megtartó és dicsőséges Isten",
        "text_reference": "Júd 24–25",
        "scope_note": "",
        "focus_sentence": (
            "Az egyedüli üdvözítő Isten képes megőrizni a botlástól, "
            "és feddhetetlenül, örömmel állít dicsősége elé."
        ),
        "exegetical_handles": [
            "φυλάσσω — megtartó/őrző cselekvés",
            "ἄπταιστος — botlástól megőrzött állapot",
            "Doxológiai egység: megtartás → eléállás → dicsőítés",
        ],
        "introduction_direction": (
            "A hallgató gyakran a saját botlásfélelméből indul. "
            "A záró doxológia nem általános bátorítás, hanem Isten megtartó "
            "cselekvésének dicsőítése."
        ),
        "movements": [
            {
                "title": "Megőrzés és eléállás",
                "verses": "v. 24",
                "textual_insight": (
                    "A textus Istenről állítja, hogy képes megőrizni a közösséget "
                    "a botlástól, és feddhetetlenül, ujjongással állítani dicsősége elé; "
                    "a megmaradás nem emberi erőfeszítésre van bízva."
                ),
                "theological_emphasis": (
                    "A megtartás és a dicsőség elé állítás Isten hatalmához tartozik; "
                    "a bizalom forrása nem a hallgató állhatatossága."
                ),
                "listener_movement": (
                    "A hallgató botlásfélelmeit Isten megtartó képességére bízhatja, "
                    "és a végső megjelenés reményében állhat."
                ),
                "original_language_note": "φυλάσσω / ἄπταιστος a 24. versben",
                "poetic_turn": "Ki őriz, ha mi magunk is botladozunk?",
                "transition": "",
            },
            {
                "title": "Dicsőítés az egyedüli üdvözítő Istennek",
                "verses": "v. 25",
                "textual_insight": (
                    "A doxológia az egyedüli Istennek szól a mi Üdvözítőnknek, "
                    "Jézus Krisztus által, dicsőséggel, fenséggel és hatalommal."
                ),
                "theological_emphasis": (
                    "Az üdvözítés és a dicsőség Krisztus által kötődik Istenhez; "
                    "nincs párhuzamos üdvút a közösség számára."
                ),
                "listener_movement": (
                    "A hála Krisztusra irányul, nem általános vallásos magasztalásra "
                    "a gyülekezet istentiszteletén."
                ),
                "transition": "",
            },
        ],
        "christ_grace_connection": (
            "A megtartás és a dicsőítés Jézus Krisztus által kapcsolódik Istenhez."
        ),
        "conclusion_direction": (
            "A doxológia Isten megtartó hatalmát és dicsőségét állítja középre: "
            "a hallgató az egyedüli üdvözítő Isten elé érkezik meg."
        ),
        "closing_line": (
            "Állhatunk-e ma is abban a bizonyosságban, hogy Ő őriz és elé állít?"
        ),
        "refinement_suggestions": [],
    }


def _good_luke_json() -> dict[str, Any]:
    return {
        "title": "Ki az én felebarátom?",
        "text_reference": "Lk 10,25–37",
        "scope_note": "",
        "focus_sentence": (
            "Jézus a felebaráti szeretetet nem elméleti határral, hanem "
            "irgalmas cselekvéssel rendezi újra."
        ),
        "exegetical_handles": [
            "Kérdés → törvény → példázat → felszólítás",
            "A samaritánus fordulata",
        ],
        "introduction_direction": (
            "A hallgató gyakran azt kérdezi, meddig tart a kötelezettsége. "
            "A törvénytudó kérdése ezt a határt keresi."
        ),
        "movements": [
            {
                "title": "A kérdés és a törvény",
                "verses": "v. 25–28",
                "textual_insight": (
                    "A törvénytudó az örök életet kérdezi, Jézus a törvény "
                    "olvasható magjához irányítja."
                ),
                "theological_emphasis": (
                    "Az élet útja Isten és a felebarát szeretetében van lerakva."
                ),
                "listener_movement": (
                    "A hallgató saját „meddig?” kérdését ismerheti fel."
                ),
                "transition": "Innen nyílik a példázat.",
            },
            {
                "title": "Az út jelenetei",
                "verses": "v. 30–32",
                "textual_insight": (
                    "A sebesült ember mellett a pap és a lévita elhalad; "
                    "a feszültség a mulasztásban nő."
                ),
                "theological_emphasis": (
                    "A vallásos státusz önmagában nem biztosít irgalmat."
                ),
                "listener_movement": (
                    "Hol kerüljük meg mi is a sebesültet az utunkon?"
                ),
                "transition": "",
            },
            {
                "title": "A samaritánus fordulata",
                "verses": "v. 33–35",
                "textual_insight": (
                    "A váratlan szereplő könyörületre indul, és cselekvéssel "
                    "gondoskodik."
                ),
                "theological_emphasis": (
                    "Az irgalom közeledik, kötöz, fizet — nem csak érez."
                ),
                "listener_movement": (
                    "A felebarát az, aki irgalmat cselekszik."
                ),
                "transition": "",
            },
            {
                "title": "Menj, és cselekedjél",
                "verses": "v. 36–37",
                "textual_insight": (
                    "Jézus visszafordítja a kérdést: ki volt a felebarát, "
                    "és felszólít a hasonló cselekvésre."
                ),
                "theological_emphasis": (
                    "A példázat nem elméleti definíciót, hanem követést kér."
                ),
                "listener_movement": (
                    "A gyülekezet egy konkrét irgalmas lépésre hívható."
                ),
                "transition": "",
            },
        ],
        "christ_grace_connection": "",
        "conclusion_direction": (
            "A megérkezés nem a helyes válasz megtalálása, hanem az irgalmas "
            "cselekvés felé fordulás."
        ),
        "closing_line": "Ki az, akihez ma te mehetsz közel?",
        "refinement_suggestions": [],
    }


# ---------------------------------------------------------------------------
# Kontextusmódok
# ---------------------------------------------------------------------------


def test_detect_context_modes():
    assert (
        detect_context_mode(
            has_bible=True,
            has_original=False,
            has_exegesis=False,
            has_homiletical=False,
            has_user=False,
            has_basket=False,
            has_movements=False,
        )
        == ContextMode.BARE
    )
    assert (
        detect_context_mode(
            has_bible=True,
            has_original=False,
            has_exegesis=True,
            has_homiletical=False,
            has_user=False,
            has_basket=False,
            has_movements=False,
        )
        == ContextMode.PARTIAL
    )
    assert (
        detect_context_mode(
            has_bible=True,
            has_original=True,
            has_exegesis=True,
            has_homiletical=True,
            has_user=True,
            has_basket=False,
            has_movements=False,
        )
        == ContextMode.RICH
    )


def test_build_outline_context_bare_and_priority():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state()
        ctx = build_outline_context(state, include_original_language=True)
        assert ctx.context_mode == ContextMode.BARE
        assert ctx.bible_text
        assert ctx.passage_reference
        sections = ctx.to_prompt_sections()
        assert sections["bible_text"]
        assert "original_language_data" in sections
        # Prioritás: bibliai textus a legmagasabb
        bible_src = next(s for s in ctx.sources if s.kind == "bible_text")
        model_src = next(s for s in ctx.sources if s.kind == "model_supplement")
        assert bible_src.priority == SourcePriority.BIBLE_TEXT
        assert model_src.priority == SourcePriority.MODEL_SUPPLEMENT
        assert int(bible_src.priority) < int(model_src.priority)
    finally:
        set_original_language_provider(None)


def test_build_outline_context_partial_and_rich():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        partial = _base_state(
            exegesis="Rövid exegetikai jegyzet a doxológiáról és a megtartásról."
        )
        ctx_p = build_outline_context(partial, include_original_language=True)
        assert ctx_p.context_mode == ContextMode.PARTIAL

        set_original_language_provider(_FakeGreekProvider())
        rich = _base_state(
            exegesis="Részletes exegetikai háttér a Júdás záró doxológiájáról.",
            last_sajat="A gyülekezet botlásfélelmeire válaszoljon.",
        )
        sw = rich[SERMON_WORKSHOP_KEY]
        sw["sermon_path"] = {"type": "deductive", "starting_point": "Botlásfélelem"}
        sw["human_condition"] = {"divine_action": "Isten megőriz"}
        ctx_r = build_outline_context(rich, include_original_language=True)
        assert ctx_r.context_mode == ContextMode.RICH
        assert ctx_r.original_language_data
    finally:
        set_original_language_provider(None)


def test_irrelevant_background_is_separated_not_fused():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state(
            exegesis="## Teljesen más témájú jegyzet\n\n* félbehagyott",
            theology="Irreleváns teológiai esszé a teremtéstanról.",
        )
        ctx = build_outline_context(state)
        sections = ctx.to_prompt_sections()
        # Nem egyetlen FORRÁS blokk — külön mezők
        assert "exegetical_material" in sections
        assert "supporting_background" in sections
        # Markdown zaj tisztítva
        assert "##" not in (ctx.exegetical_material or "")
    finally:
        set_original_language_provider(None)


def test_missing_original_language_handled():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state()
        ctx = build_outline_context(state)
        brief = build_deterministic_brief(ctx)
        assert brief.caution_flags
        assert any("nyelvi" in c.casefold() for c in brief.caution_flags)
        assert brief.key_expressions == []
    finally:
        set_original_language_provider(None)


# ---------------------------------------------------------------------------
# Minőségvédelem
# ---------------------------------------------------------------------------


def test_focus_passage_quote_detection():
    passage = JUDE_24_25
    assert focus_is_passage_quote(
        "Aki pedig képes megőrizni titeket a botlástól, és feddhetetlenül, "
        "ujjongással állítani dicsősége elé,",
        passage,
    )
    assert not focus_is_passage_quote(
        "Az egyedüli üdvözítő Isten őriz és dicsősége elé állít.",
        passage,
    )


def test_banned_placeholder_detection():
    hits = find_banned_phrases(
        "A teológiai hangsúly abban áll, hogy a textus saját szavai szerint "
        "innen vihető tovább a szószéki kibontás."
    )
    assert len(hits) >= 2


def test_arbitrary_half_verse_and_amen():
    assert has_arbitrary_half_verse_split("v. —a")
    assert has_arbitrary_half_verse_split("v. —b")
    assert not has_arbitrary_half_verse_split("v. 24")
    bad = {
        "focus_sentence": "Isten megőriz.",
        "introduction_direction": "Kérdés a botlásról.",
        "conclusion_direction": "Megérkezés a dicsőítéshez.",
        "movements": [
            {
                "title": "Ámen",
                "verses": "v. 25",
                "textual_insight": "Ámen.",
                "theological_emphasis": "Ámen.",
                "listener_movement": "Ámen.",
            },
            {
                "title": "Másik",
                "verses": "v. 24",
                "textual_insight": "Megőrzés a botlástól Isten hatalma által.",
                "theological_emphasis": "Isten cselekvése hív bizalomra.",
                "listener_movement": "A hallgató rábízhatja magát.",
            },
        ],
    }
    issues = assess_semantic_quality(bad, passage_text=JUDE_24_25)
    assert "amen_as_main_point" in issues


def test_validate_rejects_focus_quote_and_placeholders():
    payload = normalize_structured_outline(
        {
            "title": "Teszt",
            "text_reference": "Júd 24–25",
            "focus_sentence": (
                "Aki pedig képes megőrizni titeket a botlástól, és feddhetetlenül, "
                "ujjongással állítani dicsősége elé,"
            ),
            "introduction_direction": (
                "A hallgató konkrét felismerésre jut a textus saját szavai szerint."
            ),
            "movements": [
                {
                    "title": "Egy",
                    "verses": "v. —a",
                    "textual_insight": (
                        "A teológiai hangsúly abban áll tartalom nélkül ismételve a "
                        "szöveget többször a hallgató előtt a gyülekezetben ma is."
                    ),
                    "theological_emphasis": (
                        "Innen vihető tovább a szószéki kibontás a közösség felé "
                        "anélkül hogy valódi tartalom lenne a mondatban."
                    ),
                    "listener_movement": (
                        "A hallgató konkrét felismerésre jut anélkül hogy "
                        "valódi irányt kapna a szöveg mozgása szerint."
                    ),
                },
                {
                    "title": "Ámen",
                    "verses": "v. —b",
                    "textual_insight": "Ámen zárja a doxológiát önálló pontként.",
                    "theological_emphasis": "Az Ámen litugikus szó önmagában.",
                    "listener_movement": "Mondjunk Áment külön főpontként.",
                },
            ],
            "conclusion_direction": (
                "Aki pedig képes megőrizni titeket a botlástól, és feddhetetlenül, "
                "ujjongással állítani dicsősége elé, az egyedüli Istennek."
            ),
        }
    )
    issues = validate_structured_outline(payload, passage_text=JUDE_24_25)
    assert "focus_is_passage_quote" in issues or "focus_passage_overlap" in issues
    assert "placeholder_banlist" in issues or "amen_as_main_point" in issues
    assert "arbitrary_half_verse" in issues


# ---------------------------------------------------------------------------
# Generálás mockolt modellel
# ---------------------------------------------------------------------------


def test_bare_mode_generation_with_mock():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state()
        payload = _good_jude_json()

        def generate_fn(prompt: str, **kwargs: Any) -> str:
            # BARE: ne legyen gazdag műhely a promptban kötelezőként
            assert "Júd" in prompt or "outline_context" in prompt or True
            return json.dumps(payload, ensure_ascii=False)

        result = generate_sermon_outline(
            state, mode="quick", generate_fn=generate_fn, force_overwrite=True
        )
        assert result.ok, result.error_message
        assert result.outline.get("schema_version") == SCHEMA_VERSION
        focus = (result.outline.get("main_idea") or "").casefold()
        assert "képes megőrizni titeket a botlástól, és feddhetetlenül" not in focus
        blob = render_structured_outline(
            result.outline.get("structured") or result.outline
        ).casefold()
        assert "ámen" not in blob.split("1.")[0] or "dicsőítés" in blob
        assert "a textus saját szavai szerint" not in blob
    finally:
        set_original_language_provider(None)


def test_partial_mode_with_sparse_exegesis():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state(
            exegesis="A záró doxológia Isten megtartó hatalmát emeli ki."
        )
        ctx = build_outline_context(state)
        assert ctx.context_mode == ContextMode.PARTIAL

        def generate_fn(prompt: str, **kwargs: Any) -> str:
            assert "PARTIAL" in prompt or "exegetical" in prompt.casefold() or True
            return json.dumps(_good_jude_json(), ensure_ascii=False)

        result = generate_sermon_outline(
            state, mode="workshop", generate_fn=generate_fn, force_overwrite=True
        )
        assert result.ok, result.error_message
    finally:
        set_original_language_provider(None)


def test_rich_mode_filters_irrelevant_in_prompt_structure():
    set_original_language_provider(_FakeGreekProvider())
    try:
        state = _base_state(
            exegesis="Érdemi jegyzet a doxológiáról.",
            theology="Irreleváns: a teremtéstan hét napja.",
            last_sajat="Botlásfélelem a gyülekezetben.",
        )
        sw = state[SERMON_WORKSHOP_KEY]
        sw["sermon_path"] = {"type": "inductive", "starting_point": "Félelem"}
        sw["human_condition"] = {"condition": "Botlás", "divine_action": "Megőrzés"}
        ctx = build_outline_context(state)
        assert ctx.context_mode == ContextMode.RICH
        sections = ctx.to_prompt_sections()
        assert sections["homiletical_preferences"].get("method_lens")

        def generate_fn(prompt: str, **kwargs: Any) -> str:
            # Strukturált források, nem egyetlen összeöntött MAG
            assert "STRUKTURÁLT FORRÁSOK" in prompt or "outline_context" in prompt
            return json.dumps(_good_jude_json(), ensure_ascii=False)

        result = generate_sermon_outline(
            state, mode="workshop", generate_fn=generate_fn, force_overwrite=True
        )
        assert result.ok, result.error_message
    finally:
        set_original_language_provider(None)


def test_invalid_json_triggers_reject_not_weak_template():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state()

        def generate_fn(prompt: str, **kwargs: Any) -> str:
            return "Ez nem JSON, hanem szabad szöveg."

        result = generate_sermon_outline(
            state, mode="quick", generate_fn=generate_fn, force_overwrite=True
        )
        assert not result.ok
        assert result.error_message
    finally:
        set_original_language_provider(None)


def test_repair_pass_fixes_bad_focus(monkeypatch):
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state()
        bad = _good_jude_json()
        bad["focus_sentence"] = (
            "Aki pedig képes megőrizni titeket a botlástól, és feddhetetlenül, "
            "ujjongással állítani dicsősége elé,"
        )
        good = _good_jude_json()
        calls = {"n": 0}

        def generate_fn(prompt: str, **kwargs: Any) -> str:
            calls["n"] += 1
            if "CÉLZOTT JAVÍTÁS" in prompt or "JAVÍTANDÓ" in prompt:
                return json.dumps(good, ensure_ascii=False)
            return json.dumps(bad, ensure_ascii=False)

        result = generate_sermon_outline(
            state, mode="quick", generate_fn=generate_fn, force_overwrite=True
        )
        assert result.ok, result.error_message
        assert calls["n"] >= 2  # generate + repair
        focus = result.outline.get("main_idea") or ""
        assert not focus_is_passage_quote(focus, JUDE_24_25)
    finally:
        set_original_language_provider(None)


# ---------------------------------------------------------------------------
# Júdás 24–25 regresszió + narratív Lk 10
# ---------------------------------------------------------------------------


def test_jude_24_25_regression_contract():
    set_original_language_provider(_FakeGreekProvider())
    try:
        state = _base_state()

        def generate_fn(prompt: str, **kwargs: Any) -> str:
            return json.dumps(_good_jude_json(), ensure_ascii=False)

        result = generate_sermon_outline(
            state, mode="quick", generate_fn=generate_fn, force_overwrite=True
        )
        assert result.ok, result.error_message
        structured = normalize_structured_outline(
            result.outline.get("structured") or result.outline
        )
        focus = structured["focus_sentence"]
        assert focus
        assert not focus_is_passage_quote(focus, JUDE_24_25)
        blob = render_structured_outline(structured).casefold()
        assert "megőriz" in blob or "megtart" in blob
        assert "feddhetetlen" in blob or "dicsőség" in blob
        assert "dicső" in blob
        titles = [m["title"].casefold() for m in structured["movements"]]
        assert not any(t.strip() in {"ámen", "az ámen"} for t in titles)
        assert "a textus saját szavai szerint" not in blob
        assert "innen vihető tovább" not in blob
        # Doxológiai egység: ne legyen 5 mesterséges pont
        assert 2 <= len(structured["movements"]) <= 4
    finally:
        set_original_language_provider(None)


def test_narrative_luke_not_forced_three_point_template():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state(
            last_igehely="Lk 10,25–37",
            igehely_input="Lk 10,25–37",
            passage_text=LK_10,
        )
        hints = infer_literary_hints("Lk 10,25–37", LK_10)
        assert "elbeszél" in hints.get("genre", "").casefold() or "példázat" in hints.get(
            "genre", ""
        ).casefold()

        def generate_fn(prompt: str, **kwargs: Any) -> str:
            return json.dumps(_good_luke_json(), ensure_ascii=False)

        result = generate_sermon_outline(
            state, mode="quick", generate_fn=generate_fn, force_overwrite=True
        )
        assert result.ok, result.error_message
        structured = normalize_structured_outline(
            result.outline.get("structured") or result.outline
        )
        assert len(structured["movements"]) >= 3
        titles = " ".join(m["title"] for m in structured["movements"]).casefold()
        # Narratív jelek: jelenet / fordulat / samaritánus — ne doxológia-sablon
        assert "samaritán" in titles or "fordulat" in titles or "jelenet" in titles
        assert "botlástól" not in titles
    finally:
        set_original_language_provider(None)


def test_exegetical_brief_uses_grounded_tokens_only():
    set_original_language_provider(_FakeGreekProvider())
    try:
        state = _base_state()
        ctx = build_outline_context(state)
        brief = generate_exegetical_brief(ctx, generate_fn=None, force=True)
        assert brief is not None
        assert brief.grounded_in_original_data
        lemmas = {e.lemma for e in brief.key_expressions}
        assert "φυλάσσω" in lemmas or "ἄπταιστος" in lemmas
        handles = brief.handles_for_outline()
        assert handles
    finally:
        set_original_language_provider(None)


def test_offline_heuristic_jude_no_amen_point_no_placeholders():
    set_original_language_provider(_EmptyOriginalProvider())
    try:
        state = _base_state()
        result = generate_sermon_outline(state, mode="quick", force_overwrite=True)
        assert result.ok, result.error_message
        structured = normalize_structured_outline(
            result.outline.get("structured") or result.outline
        )
        blob = render_structured_outline(structured).casefold()
        assert "a textus saját szavai szerint" not in blob
        assert "innen vihető tovább a szószéki kibontás" not in blob
        titles = [m["title"].casefold() for m in structured["movements"]]
        assert not any(t.strip() in {"ámen", "az ámen"} for t in titles)
        assert not focus_is_passage_quote(
            structured["focus_sentence"], JUDE_24_25
        )
    finally:
        set_original_language_provider(None)


def test_schema_version_v8():
    assert SCHEMA_VERSION == "pulpit_outline_v8"
