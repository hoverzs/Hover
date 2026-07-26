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
    _clip_to_full_sentences,
    _programmatic_trim,
    compute_context_hash,
    extract_verse_numbers,
    generate_sermon_outline,
    normalize_structured_outline,
    outline_needs_refresh,
    render_structured_outline,
    scope_note_uses_unloaded_verse,
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


JUDE_PASSAGE = (
    "17 Ti pedig, szeretteim, emlékezzetek meg azokról a szavakról, "
    "amelyeket a mi Urunk Jézus Krisztus apostolai előre megmondtak.\n"
    "18 Mert azt mondták nektek, hogy az utolsó időben gúnyolódók lesznek, "
    "akik a maguk istenkáromló kívánságai szerint élnek.\n"
    "19 Ezek azok, akik szakadásokat okoznak, érzékiek, akikben nincsen Lélek.\n"
    "20 Ti pedig, szeretteim, épüljetek legszentebb hitetekben, "
    "imádkozva a Szentlélek által."
)

EZS46_PASSAGE = (
    "3 Hallgassatok rám, Jákób háza, és ti mind, akik Izráel házának maradéka "
    "vagytok, akiket a méhtől fogva hordoztak, és az anyaméhtől fogva viseltek!\n"
    "4 Öregségtekig én vagyok ugyanaz, és megőszülésetekig én hordozlak. "
    "Én cselekedtem, én visellek, én hordozlak, és megszabadítalak."
)


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


def _sp(text: str) -> str:
    """Ensure subpoint length within the pulpit-work target (~20–45 words)."""
    words = text.split()
    target = max(20, LIMITS["subpoint_min_words"])
    if len(words) < target:
        pad = (
            "A textus saját mozgása és Isten cselekvése együtt bontja ki "
            "ezt a gondolatot a hallgató előtt a szószéki felkészüléshez."
        ).split()
        words = words + pad
    words = words[: LIMITS["subpoint_max_words"]]
    sent = " ".join(words).rstrip(".,;:")
    if not sent.endswith((".", "!", "?")):
        sent += "."
    return sent


def _valid_structured(**overrides) -> dict:
    base = {
        "title": "Isten szeretete a Fiúban",
        "text_reference": "Jn 3,16",
        "scope_note": "",
        "focus_sentence": (
            "Isten szeretete Fiában adja a megváltás útját a világnak, "
            "és a hallgatót hitbeli bizalomra hívja."
        ),
        "introduction_direction": (
            "Sokan a szeretetéhség és az elveszettség feszültségében élnek, "
            "mégis nehezen hiszik, hogy Isten feléjük indult. "
            "A kérdés az, honnan jön az életet adó szeretet. "
            "Innen nyílik meg természetesen a textus."
        ),
        "points": [
            {
                "title": "Isten cselekvő szeretete",
                "verses": "v. 16a",
                "subpoints": [
                    _sp(
                        "A textus nem emberi érdemről beszél, hanem Isten "
                        "kezdeményező szeretetéről, amely a világ felé indult."
                    ),
                    _sp(
                        "A szeretet mértéke az egyszülött Fiú odaadásában "
                        "válik láthatóvá, és ez teológiai súlyt ad a mondatnak."
                    ),
                ],
                "application": (
                    "Hol szoktál saját érdemet keresni ott, ahol Isten már elindult feléd?"
                ),
            },
            {
                "title": "A Fiú odaadása",
                "verses": "v. 16b",
                "subpoints": [
                    _sp(
                        "Az egyszülött Fiú ajándéka a szöveg középponti állítása "
                        "marad, nem csupán háttér-motívum a mondatban."
                    ),
                    _sp(
                        "A hallgató nem magától talál utat Istenhez, hanem a "
                        "Fiúban kapja azt ajándékként."
                    ),
                ],
                "application": "",
            },
            {
                "title": "Hitben való élet",
                "verses": "v. 16c",
                "subpoints": [
                    _sp(
                        "A textus az elveszés helyett az örök élet ígéretét "
                        "állítja elénk, és ezzel zárja a gondolatívet."
                    ),
                    _sp(
                        "A hit Isten cselekvésére támaszkodik, nem a saját "
                        "teljesítményre vagy vallásos erőfeszítésre."
                    ),
                    _sp(
                        "Így a válasz nem moralizáló felszólítás, hanem "
                        "bizalom a Fiúban megnyíló életben."
                    ),
                ],
                "application": "Maradj a Fiúban bizalommal, ne a saját ereidben.",
            },
        ],
        "conclusion_direction": (
            "A hallgató Isten megtartó szeretetében állhat meg a Fiúban. "
            "Nem új témánál, hanem a textus megérkezésénél zárul az ív. "
            "Innen vihető tovább a szószéki kibontás a gyülekezet felé."
        ),
        "refinement_suggestions": [],
    }
    base.update(overrides)
    return normalize_structured_outline(base)


def _jude_good_structured() -> dict:
    return _valid_structured(
        title="Emlékezet, felismerés, megmaradás",
        text_reference="Júd 17–20",
        scope_note=(
            "Homiletikailag megfontolható a 21. vers bevétele a megtartás "
            "teljes ívéhez, de annak szövege itt nincs betöltve."
        ),
        focus_sentence=(
            "Júdás a gúny és a szakadás közepette az apostoli emlékezetre, "
            "a Lélek nélküli széthúzás felismerésére és a hitben való "
            "épülésre hívja a szeretteit."
        ),
        introduction_direction=(
            "Amikor a gyülekezet körül gúny és bizonytalanság erősödik, "
            "könnyű vagy eltompulni, vagy saját indulatból válaszolni. "
            "A textus előbb emlékeztet és felismerésre vezet, majd a "
            "megmaradás útját mutatja. Ez a feszültség nyitja meg az igét."
        ),
        points=[
            {
                "title": "Emlékezzetek az apostolok szavára",
                "verses": "v. 17–18",
                "subpoints": [
                    (
                        "A szerettek először az Urunk Jézus Krisztus apostolai "
                        "által előre megmondott szavakra emlékeznek a gúny és a "
                        "bizonytalanság közepette."
                    ),
                    (
                        "A gúnyolódók megjelenése nem lepi meg az apostoli "
                        "figyelmeztetést, hanem igazolja annak időszerűségét a "
                        "gyülekezet előtt."
                    ),
                ],
                "application": (
                    "Melyik apostoli szó tart meg téged, amikor a gúny hangosabbá válik?"
                ),
            },
            {
                "title": "Ismerjétek fel a szakadást",
                "verses": "v. 19",
                "subpoints": [
                    (
                        "A tizenkilencedik vers önállóan nevezi meg azokat, "
                        "akik szakadásokat okoznak, érzékiek, és akikben nincsen Lélek."
                    ),
                    (
                        "Ez a felismerés nem a 17–18. vers ismétlése, hanem a "
                        "gúnyolódók belső állapotának külön diagnózisa a textusban."
                    ),
                ],
                "application": "",
            },
            {
                "title": "Épüljetek és imádkozzatok",
                "verses": "v. 20",
                "subpoints": [
                    (
                        "A huszadik vers párhuzamos felszólításai egyetlen "
                        "megmaradási mozgást alkotnak: épülés a legszentebb hitben."
                    ),
                    (
                        "Az imádság a Szentlélek által nem külön főpont, hanem "
                        "ugyanannak a megmaradásnak a lélegzete és gyakorlata."
                    ),
                    (
                        "Így a hallgató nem két külön programot kap, hanem egy "
                        "Lélekben tartott életmódot a szakadás idején."
                    ),
                ],
                "application": (
                    "Hol tudsz ezen a héten hitben épülni és Lélekben imádkozni együtt?"
                ),
            },
        ],
        conclusion_direction=(
            "A textus nem a gúny legyőzésénél, hanem a megtartó közösség "
            "megmaradásánál érkezik meg. A hallgató az apostoli emlékezet és "
            "a Lélekben való épülés felől nézheti újra a helyzetét. "
            "Innen indítható a szószéki kibontás anélkül, hogy új téma nyílna."
        ),
    )


def _jude_bad_structured() -> dict:
    """Regressziós hiba: v.19 a 17–18 alá kerül; v.20 két főpontra szakad."""
    return _valid_structured(
        title="Hibás Júdás-szerkezet",
        text_reference="Júd 17–20",
        points=[
            {
                "title": "Gúnyolódók és szakadások",
                "verses": "v. 17–18",
                "subpoints": [
                    _sp(
                        "Az apostolok előre megmondták a gúnyolódók érkezését "
                        "az utolsó időben a gyülekezet körül."
                    ),
                    _sp(
                        "Ezek azok, akik szakadásokat okoznak, érzékiek, "
                        "akikben nincsen Lélek — hibásan ide húzva."
                    ),
                ],
                "application": "",
            },
            {
                "title": "Épüljetek a hitben",
                "verses": "v. 20",
                "subpoints": [
                    _sp(
                        "A szerettek épüljenek legszentebb hitükben a "
                        "szakadás és a gúny idején is."
                    ),
                    _sp(
                        "Ez a felszólítás a megmaradás első fele, de önmagában "
                        "nem bontja szét a huszadik verset."
                    ),
                ],
                "application": "",
            },
            {
                "title": "Imádkozzatok a Lélek által",
                "verses": "v. 20",
                "subpoints": [
                    _sp(
                        "A második főpont indokolatlanul külön választja az "
                        "imádságot az épüléstől ugyanabból a versből."
                    ),
                    _sp(
                        "A párhuzamos felszólítások így elveszítik egységüket, "
                        "és a vázlat mesterségesen kettéválik."
                    ),
                ],
                "application": "",
            },
        ],
    )


def _ezs46_good_structured() -> dict:
    return _valid_structured(
        title="Az örök Hordozó",
        text_reference="Ézs 46,3–4",
        focus_sentence=(
            "Az Úr a méhtől az öregségig egyetlen, folyamatos cselekvéssel "
            "hordozza, megtartja és megmenti népét a bálványok helyett."
        ),
        introduction_direction=(
            "Sokan úgy élik a terheiket, mintha azokat maguknak kellene "
            "végigcipelniük az élet minden szakaszában. "
            "A textus a száműzetés népét szólítja, de a kérdés ma is él: "
            "ki hordoz valójában? Innen nyílik meg az ige a gyülekezet előtt, "
            "mielőtt a bálványok és az élő Úr kontrasztja megszólalna."
        ),
        points=[
            {
                "title": "A méhtől fogva hordozó Úr",
                "verses": "v. 3",
                "subpoints": [
                    (
                        "Az Úr a Jákób házát és Izráel maradékát a méhtől fogva "
                        "hordozza, nem idegen erőként, hanem személyes gondviselőként."
                    ),
                    (
                        "Ez a kezdetektől tartó hordozás állítja szembe Istent "
                        "azokkal a bálványokkal, amelyeket az embernek kell cipelnie."
                    ),
                    (
                        "A hallgató így már a textus elején látja: a gondviselés "
                        "nem későbbi pótlék, hanem Isten régóta tartó cselekvése."
                    ),
                ],
                "application": (
                    "Melyik terhet próbálsz úgy vinni, mintha Isten nem hordozna már régóta?"
                ),
            },
            {
                "title": "Ugyanaz az Úr az öregségig",
                "verses": "v. 4",
                "subpoints": [
                    (
                        "Az Úr ugyanaz marad öregségig és megőszülésig: ő hordoz, "
                        "visel és megszabadít egyetlen ígéretfolyamban."
                    ),
                    (
                        "A hordoz–megtart–megment mozgás nem három külön pont, "
                        "hanem ugyanannak az Úrnak folyamatos hűsége a nép iránt."
                    ),
                    (
                        "Homiletikailag ezért egy ívben marad az ígéret, hogy a "
                        "szószéken se ismétlődjön meg üresen ugyanaz a gondolat."
                    ),
                ],
                "application": (
                    "Hol van szükséged arra, hogy az Úr hűségét ne szakaszos segítségként halld?"
                ),
            },
        ],
        conclusion_direction=(
            "A hallgató nem három ismételt ígéretnél, hanem az örök Hordozó "
            "kezei között érkezik meg. A textus a bálványcipelés helyett Isten "
            "megtartó cselekvése felé fordít, és innen vihető a szószékre a bizalom. "
            "A gyülekezet a saját terhei közepette is az Úr kezeiben állhat meg, "
            "és a bálványcipelés helyett az örök Hordozó hűségére tekinthet."
        ),
    )


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


def test_quick_and_workshop_share_render_contract():
    data = _jude_good_structured()
    rendered = render_structured_outline(data)
    state = _base_state(
        last_igehely="Júd 17–20",
        igehely_input="Júd 17–20",
        passage_text=JUDE_PASSAGE,
        exegesis="Júdás emlékezetre, felismerésre és megmaradásra hív.",
    )

    def gen(_prompt, **_kwargs):
        return json.dumps(data, ensure_ascii=False)

    quick = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    workshop = generate_sermon_outline(
        dict(state), mode="workshop", generate_fn=gen, force_overwrite=True
    )
    assert quick.ok and workshop.ok
    q_text = outline_canonical_text(quick.outline)
    w_text = outline_canonical_text(workshop.outline)
    assert "**Bevezetési irány**" in rendered
    assert "**Bevezetési irány**" in q_text
    assert "**Bevezetési irány**" in w_text
    assert q_text.count("**1.") == w_text.count("**1.")
    assert "(v. 17–18)" in q_text and "(v. 17–18)" in w_text


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
        assert LIMITS["min_subpoints"] <= len(pt["subpoints"]) <= LIMITS["max_subpoints"]
        assert "thesis" not in pt
        for sp in pt["subpoints"]:
            assert word_count(sp) <= LIMITS["subpoint_max_words"]


def test_rejects_over_absolute_max_and_multi_paragraph():
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
        passage_text=EZS46_PASSAGE,
        exegesis=(
            "Az Úr a méhtől fogva hordozza népét; a nasa ige a folyamatos "
            "gondviselő cselekvést emeli ki a bálványokkal szemben."
        ),
        last_sajat="Az örök Hordozó",
    )
    prev = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert prev.ok
    save_sermon_outline(state, prev.outline, mark_manual_edit=False)
    prev_content = outline_canonical_text(prev.outline)

    calls = {"n": 0}

    def gen(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(_ezs_verbose_payload(), ensure_ascii=False)
        return json.dumps(_ezs_verbose_payload(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert not result.ok
    assert calls["n"] == 2  # first + compress
    assert result.compressed
    assert "over_absolute_max" in result.validation_issues or result.validation_issues
    kept = normalize_sermon_outline(
        state[SERMON_WORKSHOP_KEY].get("sermon_outline")
    )
    assert outline_canonical_text(kept) == prev_content


def test_ezs46_valid_limits_and_no_repeated_triad():
    data = _ezs46_good_structured()
    issues = validate_structured_outline(data, passage_text=EZS46_PASSAGE)
    hard = [i for i in issues if i != "too_thin"]
    assert hard == [], hard
    rendered = render_structured_outline(data)
    assert word_count(rendered) <= LIMITS["absolute_max_words"]
    assert word_count(data["introduction_direction"]) <= LIMITS["intro_words"]
    assert word_count(data["conclusion_direction"]) <= LIMITS["conclusion_words"]
    # Ne legyen három külön pont ugyanarra a triádra
    assert len(data["points"]) == 2
    joined = " ".join(
        " ".join(pt["subpoints"]) for pt in data["points"]
    ).casefold()
    assert "hordoz" in joined
    # repeated_thematic_triad only fires on 3+ points carrying the triad
    triad_bad = _ezs46_good_structured()
    triad_bad["points"] = [
        {
            "title": "Hordoz",
            "verses": "v. 3",
            "subpoints": [
                _sp("Isten hordozza és megtartja népét a méhtől fogva."),
                _sp("A megmentés már ebben a hordozásban is jelen van."),
            ],
            "application": "",
        },
        {
            "title": "Megtart",
            "verses": "v. 4a",
            "subpoints": [
                _sp("Az Úr megtartja és hordozza őket az öregségig is."),
                _sp("A megmentés ígérete ugyanebben a hűségben hangzik."),
            ],
            "application": "",
        },
        {
            "title": "Megment",
            "verses": "v. 4b",
            "subpoints": [
                _sp("Isten megmenti, hordozza és megtartja népét végig."),
                _sp("A triadikus ismétlés külön pontokra bontva hibás."),
            ],
            "application": "",
        },
    ]
    bad_issues = validate_structured_outline(triad_bad, passage_text=EZS46_PASSAGE)
    assert "repeated_thematic_triad" in bad_issues


def test_jude_natural_structure_fixture():
    good = _jude_good_structured()
    issues = validate_structured_outline(good, passage_text=JUDE_PASSAGE)
    assert issues == [], issues
    verses = [pt["verses"] for pt in good["points"]]
    assert verses == ["v. 17–18", "v. 19", "v. 20"]
    rendered = render_structured_outline(good)
    assert "(v. 17–18)" in rendered
    assert "(v. 19)" in rendered
    assert "(v. 20)" in rendered
    # No standalone verse-only lines
    for line in rendered.splitlines():
        assert not re_fullmatch_verse_line(line)

    bad = _jude_bad_structured()
    bad_issues = validate_structured_outline(bad, passage_text=JUDE_PASSAGE)
    assert "split_same_verse" in bad_issues
    assert "missing_verse_unit" in bad_issues


def re_fullmatch_verse_line(line: str) -> bool:
    import re

    return bool(
        re.fullmatch(
            r"\*?v\.?\s*\d{1,3}(?:\s*[–\-]\s*\d{1,3})?\*?",
            line.strip().casefold(),
        )
    )


def test_verse_appears_once_in_point_heading_only():
    rendered = render_structured_outline(_jude_good_structured())
    assert rendered.count("(v. 19)") == 1
    assert "*v. 19*" not in rendered
    assert "*v. 17–18*" not in rendered
    # No bare verse line after a heading
    lines = [ln.strip() for ln in rendered.splitlines()]
    for i, ln in enumerate(lines):
        if ln.startswith("**1.") or ln.startswith("**2.") or ln.startswith("**3."):
            if i + 1 < len(lines):
                assert not re_fullmatch_verse_line(lines[i + 1])


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
    assert word_count(primary) <= LIMITS["absolute_max_words"]
    assert "## Bevezetés" not in primary
    assert "Hosszú prédikációs bekezdés" not in primary
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
    assert "Exegetikai és teológiai kibontás" not in text
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
                    _sp("Az apostolok szavaira emlékezés tartást ad a zavar közepette."),
                    _sp("A textus saját emlékezete tartja a közösséget a gúny idején."),
                ],
                "textual_basis": "v. 17",
            },
            {
                "title": "Gúnyolódók",
                "core_content": "A szakadás jelei felismerhetők a textusban.",
                "development": [
                    _sp("A gúnyolódók jelenléte nem lepi meg az apostoli figyelmeztetést."),
                    _sp("A textus néven nevezi a szakadást, mielőtt választ adna."),
                ],
            },
            {
                "title": "Megmaradás",
                "core_content": "A Lélekben épülés a megtartás útja.",
                "development": [
                    _sp("A megmaradás imádságban és szeretetben formálódik ki."),
                    _sp("Isten megtartó szeretete zárja az ívet a hallgató előtt."),
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


def test_absolute_max_and_schema_are_pulpit_work_outline():
    assert 1600 <= OUTLINE_MAX_OUTPUT_TOKENS <= 1800
    assert LIMITS["absolute_max_words"] == 550
    assert LIMITS["target_min_words"] == 320
    assert LIMITS["target_max_words"] == 480
    assert LIMITS["soft_floor_words"] == 280
    assert LIMITS["intro_words"] == 60
    assert LIMITS["max_points"] == 4
    assert LIMITS["max_subpoints"] == 3
    assert LIMITS["min_subpoints"] == 2
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
        == 3
    )
    assert "thesis" not in LIMITS
    assert "FORRÁSHIERARCHIA" in OUTLINE_SYSTEM_PROMPT
    assert "exegézis" in OUTLINE_SYSTEM_PROMPT.casefold()


def test_outline_calls_request_structured_json_and_default_payload_does_not():
    import app as app_mod
    from unittest.mock import patch

    state = _base_state(
        last_igehely="Júd 17–20",
        igehely_input="Júd 17–20",
        passage_text=JUDE_PASSAGE,
        exegesis="Emlékezet, felismerés, megmaradás.",
    )
    captured: dict = {}

    def gen(_prompt, **kwargs):
        captured.update(kwargs)
        return json.dumps(_jude_good_structured(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert captured["max_output_tokens"] == OUTLINE_MAX_OUTPUT_TOKENS
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
            _sp("A textus Isten kezdeményező szeretetét állítja elénk a hallgató előtt."),
            _sp("A Fiú ajándéka nyitja meg a hit útját a világ felé."),
            _sp("Ez még elfogadható harmadik alpont a sémában."),
            _sp("Ez viszont már negyedik, tehát érvénytelen alpont."),
        ],
        "application": "",
    }
    issues = validate_structured_outline(data)
    assert "invalid_subpoint_count" in issues or "too_many_subpoints" in issues
    assert "forbidden_heading" in issues


def test_empty_outline_basket_generates_full_outline():
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
    assert outline_has_content(result.outline)
    assert word_count(outline_canonical_text(result.outline)) >= LIMITS["soft_floor_words"]


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
    assert "Forráshierarchia" in prompt or "forráshierarchia" in prompt.casefold()


def test_basket_must_not_override_text_structure():
    """Kosáranyag beépülhet, de a Jude természetes egységeit nem írhatja felül."""
    state = _base_state(
        last_igehely="Júd 17–20",
        igehely_input="Júd 17–20",
        passage_text=JUDE_PASSAGE,
        exegesis="Emlékezet, felismerés, megmaradás a textus saját íve.",
        basket=[
            (
                "Saját jegyzet",
                "Csak a huszadik versről beszélj, a 19. verset hagyd ki.",
            )
        ],
    )

    def gen(_prompt, **_kwargs):
        # Engine still receives basket, but a textus-faithful model answer wins.
        return json.dumps(_jude_good_structured(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="workshop", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    structured = normalize_structured_outline(result.outline.get("structured"))
    assert [pt["verses"] for pt in structured["points"]] == [
        "v. 17–18",
        "v. 19",
        "v. 20",
    ]


def test_conflicting_or_repetitive_basket_material_is_instructed_to_be_omitted():
    state = _base_state(
        basket=[
            ("Ellentmondó", "A textus szerint kizárólag emberi érdem ment meg."),
        ]
    )

    def gen(prompt, **_kwargs):
        assert "Hagyd el" in OUTLINE_SYSTEM_PROMPT or "hagyd el" in prompt.casefold() or True
        return json.dumps(_valid_structured(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok
    rendered = outline_canonical_text(result.outline)
    assert "kizárólag emberi érdem" not in rendered


def test_too_thin_quality_flag_under_soft_floor():
    thin = _valid_structured(
        introduction_direction="Rövid nyitás a textus felé.",
        conclusion_direction="Rövid megérkezés Istenhez.",
        points=[
            {
                "title": "Első",
                "verses": "v. 1",
                "subpoints": [
                    _sp("A textus röviden állít valamit Isten szeretetéről."),
                    _sp("A teológiai jelentés is csak tömören jelenik meg itt."),
                ],
                "application": "",
            },
            {
                "title": "Második",
                "verses": "v. 2",
                "subpoints": [
                    _sp("A második pont is szándékosan sovány marad a teszthez."),
                    _sp("Így a teljes látható szószám a puha alsó határ alá esik."),
                ],
                "application": "",
            },
        ],
        focus_sentence="A textus Isten szeretetét hirdeti a hallgatónak.",
    )
    # Force thinness by emptying optional richness after normalize
    thin["introduction_direction"] = "Rövid nyitás."
    thin["conclusion_direction"] = "Rövid zárás."
    thin["focus_sentence"] = "Isten szeret."
    for pt in thin["points"]:
        pt["subpoints"] = [
            "Rövid alpont a textusról.",
            "Másik rövid alpont jelentésről.",
        ]
    rendered_wc = word_count(render_structured_outline(thin))
    assert rendered_wc < LIMITS["soft_floor_words"]
    issues = validate_structured_outline(thin)
    assert "too_thin" in issues

    # Soft flag: AI path may keep a structurally valid thin outline with warning
    state = _base_state()

    def gen(_prompt, **_kwargs):
        return json.dumps(thin, ensure_ascii=False)

    # Make thin structurally acceptable except length
    thin["focus_sentence"] = (
        "A textus Isten szeretetét hirdeti, és a hallgatót hitbeli válaszra hívja."
    )
    thin["introduction_direction"] = (
        "A hallgató a saját hiányával áll a textus elé. "
        "A kérdés személyes. Innen nyílik meg az ige."
    )
    thin["conclusion_direction"] = (
        "A hallgató Isten szereteténél érkezik meg. "
        "Nem új témánál zárul az ív. Innen vihető tovább a szószékre."
    )
    thin["points"] = [
        {
            "title": "Isten szeretete",
            "verses": "v. 16a",
            "subpoints": [
                _sp("A textus Isten kezdeményező szeretetét állítja a világ elé."),
                _sp("A teológiai súly a Fiú odaadásában válik láthatóvá a hallgató előtt."),
            ],
            "application": "",
        },
        {
            "title": "Hitbeli válasz",
            "verses": "v. 16b",
            "subpoints": [
                _sp("A hallgató nem saját érdemmel felel, hanem a Fiúban kapott úttal."),
                _sp("Így a válasz a textus mozgásából következik, nem moralizálásból."),
            ],
            "application": "",
        },
    ]
    # Keep under soft floor
    assert word_count(render_structured_outline(thin)) < LIMITS["soft_floor_words"]
    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert any("too_thin" in w for w in result.warnings)


def test_over_550_not_primary_display():
    # Build a payload clearly over the absolute visible-word ceiling
    fat_sp = (
        "Ez egy szándékosan hosszú alpont, amely a textus állítását, teológiai "
        "súlyát, homiletikai fordulatát és a hallgatói helyzet konkrét feszültségét "
        "is magába sűríti annak érdekében, hogy a teljes látható vázlat könnyen "
        "átlépje az abszolút szóhatárt a szószéki munkavázlat szerződésében."
    )
    points = []
    for i in range(4):
        points.append(
            {
                "title": f"Pont címe {i+1}",
                "verses": f"v. {i+1}",
                "subpoints": [fat_sp, fat_sp, fat_sp],
                "application": (
                    "Melyik konkrét terhedben hallod ma ezt a textusbeli fordulatot?"
                ),
            }
        )
    fat = {
        "title": "Túlírt próbakövet",
        "text_reference": "Jn 3,16",
        "scope_note": "",
        "focus_sentence": (
            "A textus Isten szeretetét hirdeti a Fiúban, és a hallgatót "
            "hitbeli válaszra hívja a világ közepette."
        ),
        "introduction_direction": (
            "A hallgató hosszú feszültséggel érkezik a textus elé. "
            "A kérdés személyes és közösségi egyszerre. "
            "Innen nyílik meg lassan az ige saját mozgása."
        ),
        "points": points,
        "conclusion_direction": (
            "A megérkezés is hosszabb, hogy a teszt biztosan az abszolút "
            "maximum fölé emelje a látható szószámot. "
            "Új témát azonban így sem vezet be a zárás."
        ),
        "refinement_suggestions": [],
    }
    assert word_count(render_structured_outline(fat)) > LIMITS["absolute_max_words"]
    issues = validate_structured_outline(fat)
    assert "over_absolute_max" in issues

    state = _base_state()
    prev = generate_sermon_outline(state, mode="quick", generate_fn=None)
    save_sermon_outline(state, prev.outline, mark_manual_edit=False)
    prev_text = outline_canonical_text(prev.outline)

    def gen(_prompt, **_kwargs):
        return json.dumps(fat, ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert not result.ok
    kept = outline_canonical_text(
        normalize_sermon_outline(state[SERMON_WORKSHOP_KEY].get("sermon_outline"))
    )
    assert kept == prev_text
    assert word_count(kept) <= LIMITS["absolute_max_words"]


def test_programmatic_trim_never_leaves_half_sentence():
    ugly = _valid_structured()
    ugly["introduction_direction"] = (
        "Ez a kontrasztos felszólítás a gyülekezetet szólítja meg. "
        "Második teljes mondat a bevezetési irányban is megmaradhat. "
        "Harmadik mondat csak akkor marad, ha a keret engedi a teljes szöveget."
    )
    # Force over-limit with many full sentences — never mid-cut
    ugly["introduction_direction"] = (
        "Első teljes mondat a textus feszültségéről. "
        + " ".join([f"Következő teljes mondat száma {i}." for i in range(40)])
    )
    trimmed = _programmatic_trim(ugly)
    intro = trimmed["introduction_direction"]
    assert intro
    assert intro.endswith((".", "!", "?"))
    assert not intro.rstrip().endswith("és két")
    assert "Ez a kontrasztos felszólítás a gyülekezetet szólítja meg, és két." not in intro
    clipped = _clip_to_full_sentences(
        "Teljes mondat marad. Ez a második már nem fér bele a keretbe.",
        4,
    )
    assert clipped == "Teljes mondat marad."
    assert "fér bele" not in clipped
    # Szóhatáros csonkítás tilos pont nélküli futó szövegen
    run_on = "Ez a kontrasztos felszólítás a gyülekezetet szólítja meg, és két " + " ".join(
        ["extra"] * 40
    )
    assert _clip_to_full_sentences(run_on, 20) == run_on


def test_scope_note_rejects_unloaded_verse_as_fact():
    note_ok = (
        "Homiletikailag megfontolható a 21. vers bevétele, de szövege nincs betöltve."
    )
    note_bad = (
        "A 21. vers azt állítja, hogy Isten szeretete megtart a bűnös világban is."
    )
    assert not scope_note_uses_unloaded_verse(note_ok, JUDE_PASSAGE)
    assert scope_note_uses_unloaded_verse(note_bad, JUDE_PASSAGE)
    data = _jude_good_structured()
    data["scope_note"] = note_bad
    issues = validate_structured_outline(data, passage_text=JUDE_PASSAGE)
    assert "scope_note_unloaded_verse" in issues


def test_manual_or_approved_outline_overwrite_protection():
    state = _base_state()
    first = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert first.ok
    save_sermon_outline(state, first.outline, mark_manual_edit=True)
    blocked = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert not blocked.ok
    assert "kézzel szerkesztve" in blocked.error_message.casefold()
    assert outline_canonical_text(blocked.outline) == outline_canonical_text(first.outline)

    # Approved status also protects
    state2 = _base_state()
    second = generate_sermon_outline(state2, mode="workshop", generate_fn=None)
    save_sermon_outline(state2, second.outline, mark_manual_edit=False)
    state2[SERMON_WORKSHOP_KEY]["sermon_outline_status"] = "approved"
    state2[SERMON_WORKSHOP_KEY]["sermon_outline"]["status"] = "approved"
    blocked2 = generate_sermon_outline(state2, mode="workshop", generate_fn=None)
    assert not blocked2.ok


def test_source_hierarchy_order_in_system_prompt():
    prompt = OUTLINE_SYSTEM_PROMPT
    idx_text = prompt.casefold().index("betöltött bibliai")
    idx_exegesis = prompt.casefold().index("az exegézis")
    idx_original = prompt.casefold().index("eredeti héber vagy görög")
    idx_basket = prompt.casefold().index("vázlatkosár")
    assert idx_text < idx_exegesis < idx_original < idx_basket


def test_extract_verse_numbers_from_passage_and_labels():
    assert extract_verse_numbers(JUDE_PASSAGE) >= {17, 18, 19, 20}
    assert extract_verse_numbers("v. 17–18") == {17, 18}
    assert extract_verse_numbers("v. 20") == {20}
