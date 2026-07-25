# ruff: noqa: E402
"""Közös igehirdetési-vázlat motor — séma, validáció, belépési pontok."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import (
    FORBIDDEN_HEADINGS,
    LIMITS,
    OUTLINE_MAX_OUTPUT_TOKENS,
    OUTLINE_RESPONSE_SCHEMA,
    OUTLINE_SYSTEM_PROMPT,
    REFRESH_NOTICE,
    SCHEMA_VERSION,
    compute_context_hash,
    generate_sermon_outline,
    normalize_structured_outline,
    outline_needs_refresh,
    render_structured_outline,
    structured_to_sermon_outline,
    validate_structured_outline,
    word_count,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_outline,
    save_sermon_outline,
)
from sermon_workshop_outline_ai import (
    assemble_sermon_outline,
    assess_outline_readiness,
    outline_canonical_text,
    outline_has_content,
    outline_to_readable_content,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop
from tests.test_jude_e2e_workflow import build_jude_state


def _base_state(**extra) -> dict:
    state = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta…",
        "exegesis": "A szeret ige a szöveg központi mozgása a megváltás felé.",
        "original_text": "ἠγάπησεν — aoristos, Isten cselekvő szeretete.",
        "theology": "",
        "history": "",
        "last_sajat": "",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state


def _valid_structured(**overrides) -> dict:
    base = {
        "title": "Isten szeretete",
        "text_reference": "Jn 3,16",
        "scope_note": "",
        "focus_sentence": "Isten szeretete Fiában adja a megváltás útját a világnak.",
        "introduction_direction": (
            "A hallgató a szeretetéhség és az elveszettség feszültségéből indul."
        ),
        "points": [
            {
                "title": "Isten cselekvő szeretete",
                "verses": "v. 16a",
                "subpoints": [
                    "A textus nem emberi érdemről, hanem Isten kezdeményezéséről beszél.",
                    "A szeretet mértéke az egyszülött Fiú odaadásában válik láthatóvá.",
                ],
                "application": "Fogadd el, hogy Isten feléd indult el előbb.",
            },
            {
                "title": "A Fiú odaadása",
                "verses": "v. 16b",
                "subpoints": [
                    "Az egyszülött Fiú ajándéka a szöveg középponti állítása marad.",
                    "A hallgató nem magától talál utat, hanem a Fiúban kapja azt.",
                ],
                "application": "",
            },
            {
                "title": "Hitben való élet",
                "verses": "v. 16c",
                "subpoints": [
                    "A textus az elveszés helyett az örök élet ígéretét állítja elénk.",
                    "A hit Isten cselekvésére támaszkodik, nem a saját teljesítményre.",
                ],
                "application": "Maradj a Fiúban bizalommal, ne magadban.",
            },
        ],
        "conclusion_direction": (
            "A hallgató Isten megtartó szeretetében állhat meg a Fiúban."
        ),
        "refinement_suggestions": [],
    }
    base.update(overrides)
    return normalize_structured_outline(base)


def _ezs_verbose_payload() -> dict:
    """Ézs 46,3–4 failure pattern: long intro, multi-para points, long close."""
    para = (
        "Az Úr nem idegen erőként áll a nép fölött, hanem anyai gondoskodással "
        "hordozza őket a méhtől fogva, és az öregség napjaiban sem engedi el "
        "a kezüket, hanem továbbra is magán viseli terhüket. "
        "Ez a gondolat többször ismétlődik magyarázatként és alkalmazásként is, "
        "hogy a hallgató megértse: Isten hordozása nem pillanatnyi segítség."
    )
    return {
        "title": "Az örök Hordozó",
        "text_reference": "Ézs 46,3–4",
        "scope_note": "",
        "focus_sentence": (
            "Az örökkévaló Isten a méhtől az öregségig hordozza népét, "
            "és nem engedi el a kezét a fáradtság napjaiban sem."
        ),
        "introduction_direction": " ".join(["bevezetés"] * 50)
        + " A hallgató a saját terheivel áll a textus elé, mielőtt Isten "
        "hordozó szeretetét hallaná, és hosszú magyarázatot kap arról, "
        "miért fontos ez a kép a száműzetés népének és nekünk is.",
        "points": [
            {
                "title": "A méhtől fogva hordozó Isten",
                "verses": "v. 3",
                "thesis": para,
                "body": para + "\n\n" + para,
                "subpoints": [para, para + "\n\n" + para, para],
                "application": para,
            },
            {
                "title": "Az öregségig tartó megtartás",
                "verses": "v. 4",
                "thesis": para,
                "subpoints": [para, para, para],
                "application": para,
            },
            {
                "title": "A bálványokkal szemben álló Úr",
                "verses": "v. 3–4",
                "thesis": para,
                "subpoints": [para, para],
                "application": para,
            },
            {
                "title": "A hallgató válasza a hordozásra",
                "verses": "v. 4",
                "thesis": para,
                "subpoints": [para, para, para],
                "application": para,
            },
        ],
        "conclusion_direction": " ".join(["zaras"] * 55)
        + " Hosszú záró beszéd ismétli a magyarázatot és az alkalmazást.",
        "refinement_suggestions": [],
    }


def test_schema_version_shared_by_quick_and_workshop():
    state = _base_state()
    quick = generate_sermon_outline(state, mode="quick", generate_fn=None)
    workshop = generate_sermon_outline(dict(state), mode="workshop", generate_fn=None)
    assert quick.ok and workshop.ok
    assert quick.outline.get("schema_version") == SCHEMA_VERSION
    assert workshop.outline.get("schema_version") == SCHEMA_VERSION
    qs = normalize_structured_outline(quick.outline.get("structured"))
    ws = normalize_structured_outline(workshop.outline.get("structured"))
    assert qs.get("schema_version") == SCHEMA_VERSION
    assert ws.get("schema_version") == SCHEMA_VERSION
    assert "thesis" not in qs["points"][0]
    assert "thesis" not in ws["points"][0]


def test_quick_outline_without_homiletical_workshop():
    state = _base_state()
    ready = assess_outline_readiness(state)
    assert ready.ok
    assert "human_condition" not in ready.source_keys
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok, result.error_message
    assert result.source == "quick"
    assert outline_has_content(result.outline)
    assert 2 <= len(result.outline.get("movements") or []) <= 4


def test_outline_from_biblical_text_plus_exegesis_original():
    state = _base_state(theology="", history="")
    state[SERMON_WORKSHOP_KEY] = get_default_sermon_workshop()
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok
    content = outline_to_readable_content(result.outline)
    assert word_count(content) <= LIMITS["absolute_max_words"]
    assert "Mit rendez ez a pont" not in content


def test_workshop_outline_with_approved_decisions():
    state = build_jude_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert result.ok
    assert result.source == "workshop"
    assert result.outline.get("main_idea")
    assert len(result.outline.get("movements") or []) >= 2


def test_both_entry_points_same_output_schema():
    state = _base_state()
    quick = generate_sermon_outline(state, mode="quick", generate_fn=None)
    workshop = generate_sermon_outline(dict(state), mode="workshop", generate_fn=None)
    assert quick.ok and workshop.ok
    qs = normalize_structured_outline(quick.outline.get("structured"))
    ws = normalize_structured_outline(workshop.outline.get("structured"))
    for key in (
        "title",
        "text_reference",
        "focus_sentence",
        "introduction_direction",
        "points",
        "conclusion_direction",
        "schema_version",
    ):
        assert key in qs and key in ws
    assert isinstance(qs["points"], list) and isinstance(ws["points"], list)


def test_outline_saved_on_one_surface_appears_on_other():
    state = _base_state()
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok
    save_sermon_outline(state, result.outline, mark_manual_edit=False)
    sw = state[SERMON_WORKSHOP_KEY]
    loaded = normalize_sermon_outline(sw.get("sermon_outline"))
    assert outline_has_content(loaded)
    assert loaded.get("source") == "quick"
    assemble_sermon_outline(
        state, generate_fn=None, force_overwrite=False, synthesize=True
    )
    assert outline_has_content(normalize_sermon_outline(sw.get("sermon_outline")))


def test_point_and_subpoint_counts_and_word_cap():
    data = _valid_structured()
    issues = validate_structured_outline(data)
    assert issues == [], issues
    rendered = render_structured_outline(data)
    assert word_count(rendered) <= LIMITS["absolute_max_words"]
    assert 2 <= len(data["points"]) <= 4
    for pt in data["points"]:
        assert len(pt["subpoints"]) == 2
        assert "thesis" not in pt
        for sp in pt["subpoints"]:
            assert word_count(sp) <= 18


def test_rejects_over_280_words_and_multi_paragraph():
    long_para = " ".join(["szó"] * 80) + "."
    bad = _valid_structured(
        points=[
            {
                "title": "Túlírt pont",
                "verses": "v. 1",
                "subpoints": [
                    long_para + "\n\n" + long_para,
                    long_para + "\n\n" + long_para,
                    long_para,
                ],
                "application": "",
            },
            {
                "title": "Második",
                "verses": "v. 2",
                "subpoints": [long_para, long_para],
                "application": "",
            },
            {
                "title": "Harmadik",
                "verses": "v. 3",
                "subpoints": [long_para, long_para],
                "application": "",
            },
        ]
    )
    issues = validate_structured_outline(bad)
    assert (
        "over_absolute_max" in issues
        or "multi_paragraph_point" in issues
        or "subpoint_length" in issues
        or "full_sermon_like" in issues
        or "prose_block_too_long" in issues
    )


def test_ezs46_failure_pattern_rejected_and_compress_triggered():
    """Prior Ézs 46,3–4 near-sermon must not save; compress once then reject."""
    state = _base_state(
        last_igehely="Ézs 46,3–4",
        igehely_input="Ézs 46,3–4",
        passage_text=(
            "3 Hallgassatok rám, Jákób háza… 4 Öregségtekig én vagyok ugyanaz, "
            "és megőszülésetekig én hordozlak."
        ),
        exegesis=(
            "Az Úr a méhtől fogva hordozza népét; a nasa ige a folyamatos "
            "gondviselő cselekvést emeli ki a bálványokkal szemben."
        ),
        last_sajat="Az örök Hordozó",
    )
    # Seed a previous valid outline — must not be overwritten on fail
    prev = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert prev.ok
    save_sermon_outline(state, prev.outline, mark_manual_edit=False)
    prev_content = outline_canonical_text(prev.outline)

    calls = {"n": 0}

    def gen(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(_ezs_verbose_payload(), ensure_ascii=False)
        # Second (compress) still bad
        return json.dumps(_ezs_verbose_payload(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert not result.ok
    assert calls["n"] == 2  # first + compress
    assert result.compressed
    assert "over_absolute_max" in result.validation_issues or result.validation_issues
    # Previous valid outline preserved
    kept = normalize_sermon_outline(
        state[SERMON_WORKSHOP_KEY].get("sermon_outline")
    )
    assert outline_canonical_text(kept) == prev_content


def test_ezs46_valid_limits_on_rendered_outline():
    data = _valid_structured(
        title="Az örök Hordozó",
        text_reference="Ézs 46,3–4",
        focus_sentence="Az Úr a méhtől az öregségig hordozza népét.",
        introduction_direction="A hallgató saját terhével áll a textus elé.",
        points=[
            {
                "title": "Méhtől fogva hordoz",
                "verses": "v. 3",
                "subpoints": [
                    "Isten a kezdetektől fogva viseli népének terhét.",
                    "A hordozás nem idegen erő, hanem személyes gondviselés.",
                ],
                "application": "Engedd, hogy Isten hordozzon, ne te magad.",
            },
            {
                "title": "Öregségig megtart",
                "verses": "v. 4",
                "subpoints": [
                    "Az Úr ugyanaz marad a fáradtság napjaiban is.",
                    "A megtartás ígérete túléli az emberi erő fogyatkozását.",
                ],
                "application": "",
            },
            {
                "title": "Bálványok helyett Úr",
                "verses": "v. 3–4",
                "subpoints": [
                    "A bálványokat hordozni kell, az Úr viszont hordoz minket.",
                    "A textus a valódi és a hamis teherviselőt állítja szembe.",
                ],
                "application": "Ne hordozz bálványt; bízd magad az Úrra.",
            },
        ],
        conclusion_direction="Állj meg az örök Hordozó kezei között.",
    )
    issues = validate_structured_outline(data)
    assert issues == [], issues
    rendered = render_structured_outline(data)
    assert word_count(rendered) <= 280
    assert word_count(data["introduction_direction"]) <= 25
    assert word_count(data["conclusion_direction"]) <= 25
    assert 2 <= len(data["points"]) <= 4
    for pt in data["points"]:
        assert len(pt["subpoints"]) == 2
        assert "body" not in pt and "content" not in pt and "thesis" not in pt
        for sp in pt["subpoints"]:
            assert word_count(sp) <= 18
            assert "\n\n" not in sp


def test_legacy_markdown_not_shown_after_new_generation():
    state = _base_state()
    long_legacy = (
        "## Bevezetés\n\n"
        + ("Hosszú prédikációs bekezdés. " * 40)
        + "\n\n## Pontok\n\n"
        + ("Magyarázat és alkalmazás ismételve. " * 50)
    )
    sw = state[SERMON_WORKSHOP_KEY]
    sw["sermon_outline"] = normalize_sermon_outline(
        {
            "content": long_legacy,
            "legacy_outline_text": "",
            "main_idea": "Régi fő gondolat",
            "passage_reference": "Jn 3,16",
        }
    )
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok
    save_sermon_outline(state, result.outline, mark_manual_edit=False)
    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    primary = outline_canonical_text(outline)
    assert word_count(primary) <= 420
    assert "## Bevezetés" not in primary
    assert "Hosszú prédikációs bekezdés" not in primary
    # Legacy may be preserved separately
    legacy = outline.get("legacy_outline_text") or ""
    if legacy:
        assert "Hosszú prédikációs" in legacy or "##" in legacy


def test_forbidden_meta_headings_absent_in_renderer():
    data = _valid_structured()
    text = render_structured_outline(data)
    for heading in FORBIDDEN_HEADINGS:
        assert heading not in text
    assert "Diagnózis" not in text
    assert "Átvezetési logika" not in text
    assert text.count("\n\n\n") == 0


def test_old_project_outline_migrates_safely():
    legacy = {
        "main_idea": "Isten megtart a gúny közepette.",
        "passage_reference": "Júd 17–20",
        "opening_direction": "A gúny hangja körülöttünk egyre hangosabb.",
        "movements": [
            {
                "title": "Emlékezzetek",
                "core_content": "Az apostolok szavaira emlékezés tartást ad.",
                "development": [
                    "Az apostolok szavaira emlékezés tartást ad a zavar közepette.",
                    "A textus saját emlékezete tartja a közösséget.",
                ],
                "textual_basis": "v. 17",
            },
            {
                "title": "Gúnyolódók",
                "core_content": "A szakadás jelei felismerhetők a textusban.",
                "development": [
                    "A gúnyolódók jelenléte nem lepi meg az apostoli figyelmeztetést.",
                    "A textus néven nevezi a szakadást, mielőtt választ adna.",
                ],
            },
            {
                "title": "Megmaradás",
                "core_content": "A Lélekben épülés a megtartás útja.",
                "development": [
                    "A megmaradás imádságban és szeretetben formálódik ki.",
                    "Isten megtartó szeretete zárja az ívet a hallgató előtt.",
                ],
            },
        ],
        "closing": {"final_insight": "Isten szeretete megtart."},
        "content": "régi szabad szöveg",
    }
    normalized = normalize_sermon_outline(legacy)
    assert normalized.get("main_idea")
    assert normalized.get("movements")
    structured = normalize_structured_outline(normalized)
    assert structured.get("focus_sentence")
    assert structured.get("points")
    assert "thesis" not in structured["points"][0]
    outline = structured_to_sermon_outline(structured, seed=normalized, source="workshop")
    assert outline_has_content(outline)


def test_incomplete_homiletics_with_exegesis_succeeds():
    state = _base_state()
    assert not state[SERMON_WORKSHOP_KEY].get("sermon_main_idea")
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok, result.error_message
    tips = result.outline.get("editorial_tips") or []
    assert len(tips) <= 2
    content = outline_to_readable_content(result.outline)
    assert "műhelyszakasz" not in content.casefold()


def test_context_hash_refresh_notice_without_second_outline():
    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert result.ok
    save_sermon_outline(state, result.outline)
    from sermon_workshop_outline_ai import collect_available_sermon_material

    bundle = collect_available_sermon_material(state)
    assert not outline_needs_refresh(result.outline, bundle)
    state["exegesis"] = "Új exegetikai megfigyelés a szeret igéről és a Fiúról."
    bundle2 = collect_available_sermon_material(state)
    assert outline_needs_refresh(result.outline, bundle2)
    assert REFRESH_NOTICE
    assert compute_context_hash(bundle) != compute_context_hash(bundle2)


def test_assemble_uses_shared_engine():
    state = _base_state()
    a = assemble_sermon_outline(state, generate_fn=None, mode="quick")
    assert a.ok
    assert a.outline.get("structured") or a.outline.get("movements")
    content = outline_to_readable_content(a.outline)
    assert word_count(content) <= LIMITS["absolute_max_words"]
    assert a.outline.get("schema_version") == SCHEMA_VERSION


def test_absolute_max_and_schema_are_compact():
    assert OUTLINE_MAX_OUTPUT_TOKENS == 900
    assert LIMITS["absolute_max_words"] == 280
    assert LIMITS["target_min_words"] == 160
    assert LIMITS["target_max_words"] == 240
    assert LIMITS["intro_words"] == 25
    assert LIMITS["max_points"] == 4
    assert LIMITS["max_subpoints"] == 2
    assert OUTLINE_RESPONSE_SCHEMA["properties"]["points"]["minItems"] == 2
    assert OUTLINE_RESPONSE_SCHEMA["properties"]["points"]["maxItems"] == 4
    assert (
        OUTLINE_RESPONSE_SCHEMA["properties"]["points"]["items"]["properties"][
            "subpoints"
        ]["minItems"]
        == 2
    )
    assert (
        OUTLINE_RESPONSE_SCHEMA["properties"]["points"]["items"]["properties"][
            "subpoints"
        ]["maxItems"]
        == 2
    )
    assert "thesis" not in LIMITS


def test_outline_calls_request_structured_json_and_default_payload_does_not():
    import app as app_mod
    from unittest.mock import patch

    state = _base_state()
    captured: dict = {}

    def gen(_prompt, **kwargs):
        captured.update(kwargs)
        return json.dumps(_valid_structured(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert captured["max_output_tokens"] == 900
    assert captured["response_mime_type"] == "application/json"
    assert captured["response_schema"] == OUTLINE_RESPONSE_SCHEMA

    with patch.object(app_mod, "st") as st_mock:
        st_mock.session_state = {"temperature": 0.3}
        outline_payload = app_mod._build_payload(
            "vázlat",
            False,
            "gemini-2.5-flash-lite",
            response_mime_type="application/json",
            response_schema=OUTLINE_RESPONSE_SCHEMA,
        )
        ordinary_payload = app_mod._build_payload(
            "más funkció",
            False,
            "gemini-2.5-flash",
        )
    assert outline_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert outline_payload["generationConfig"]["responseSchema"] == OUTLINE_RESPONSE_SCHEMA
    assert "responseMimeType" not in ordinary_payload["generationConfig"]
    assert "responseSchema" not in ordinary_payload["generationConfig"]


def test_validator_rejects_extra_subpoints_and_legacy_headings():
    data = _valid_structured()
    data["points"][0] = {
        "title": "Problémafelvetés",
        "verses": "v. 1",
        "subpoints": [
            "A textus Isten kezdeményező szeretetét állítja elénk.",
            "A Fiú ajándéka nyitja meg a hit útját.",
            "Ez nem maradhat harmadik alpont.",
        ],
        "application": "",
    }
    issues = validate_structured_outline(data)
    assert "invalid_subpoint_count" in issues
    assert "forbidden_heading" in issues


def test_empty_outline_basket_generates_without_seed_anchor():
    state = _base_state(basket=[])
    captured: list[str] = []

    def gen(prompt, **_kwargs):
        captured.append(prompt)
        return json.dumps(_valid_structured(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert len(captured) == 1
    assert "VÁZLATKOSÁR – OPCIONÁLIS, SZELEKTÁLVA HASZNÁLHATÓ:\n[]" in captured[0]
    assert "MAG (opcionális)" not in captured[0]
    assert "Üres vázlatkosár esetén is készíts teljes értékű, konkrét vázlatot." in captured[0]


def test_outline_basket_is_separate_optional_source_material():
    state = _base_state(
        basket=[
            ("Exegézis", "A Fiú odaadása a textus középponti állítása."),
            ("Alkalmazás", "A bizalom Isten kezdeményező szeretetére válaszol."),
        ]
    )
    captured: list[str] = []

    def gen(prompt, **_kwargs):
        captured.append(prompt)
        return json.dumps(_valid_structured(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="workshop", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    prompt = captured[0]
    assert '"outline_basket"' not in prompt.split("VÁZLATKOSÁR")[0]
    assert '"source": "Exegézis"' in prompt
    assert '"source": "Alkalmazás"' in prompt
    assert "nem kell mindegyiket felhasználni." in prompt


def test_conflicting_or_repetitive_basket_material_is_instructed_to_be_omitted():
    state = _base_state(
        basket=[
            ("Jegyzet", "A textus szerint az üdvösség kizárólag emberi érdem."),
            ("Jegyzet", "A Fiú ajándéka központi, központi, központi."),
        ]
    )
    captured: list[str] = []

    def gen(prompt, **_kwargs):
        captured.append(prompt)
        return json.dumps(_valid_structured(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    rendered = outline_canonical_text(result.outline)
    assert "kizárólag emberi érdem" not in rendered
    assert "A textus mindig elsőbbséget élvez." in OUTLINE_SYSTEM_PROMPT
    assert "Hagyd el a textustól idegen, gyenge, ismétlődő, bizonytalan vagy" in OUTLINE_SYSTEM_PROMPT
    assert "kizárólag emberi érdem" in captured[0]
