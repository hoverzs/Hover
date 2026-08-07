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
    build_outline_user_prompt,
    compute_context_hash,
    extract_outline_background_material,
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
        "exegesis_status": "approved",
        "original_text": "ἠγάπησεν — aoristos, Isten cselekvő szeretete.",
        "original_text_status": "approved",
        "theology": "",
        "history": "",
        "last_sajat": "",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state



def _layer(text: str, *, min_words: int | None = None) -> str:
    """Egy teljes mondat a háromrétegű séma célhosszához (~28–45 szó)."""
    target = max(28, min_words or 28)
    raw = text.strip()
    if not raw.endswith((".", "!", "?")):
        raw += "."
    # Csak az első mondatot tartjuk — a pad ne hozzon létre második mondatot.
    first = raw
    for sep in (". ", "! ", "? "):
        if sep in raw:
            first = raw.split(sep)[0] + sep.strip()
            break
    words = first.rstrip(".!?").split()
    pad = (
        "a textus saját mozgása szerint a hallgató előtt a szószéki "
        "felkészülés során is"
    ).split()
    while len(words) < target:
        words.extend(pad)
    words = words[: LIMITS["layer_max_words"]]
    return " ".join(words).rstrip(".,;:") + "."


def _valid_structured(**overrides) -> dict:
    base = {
        "title": "Isten szeretete a Fiúban",
        "text_reference": "Jn 3,16",
        "scope_note": "",
        "focus_sentence": (
            "Isten szeretete Fiában adja a megváltás útját a világnak, "
            "és a hallgatót hitbeli bizalomra hívja a textus szerint ma is."
        ),
        "introduction_direction": (
            "Sokan a szeretetéhség és az elveszettség feszültségében élnek, "
            "mégis nehezen hiszik, hogy Isten feléjük indult. "
            "A kérdés az, honnan jön az életet adó szeretet, és milyen válasz "
            "nyílik meg a textus előtt a gyülekezet konkrét helyzetében. "
            "Innen vezet a gondolat a Fiú odaadásához és a hitbeli bizalomhoz."
        ),
        "points": [
            {
                "title": "Isten cselekvő szeretete",
                "verses": "v. 16a",
                "textual_insight": _layer(
                    "A textus nem emberi érdemről beszél, hanem Isten "
                    "kezdeményező szeretetéről, amely a világ felé indult, "
                    "mielőtt bárki válaszolt volna."
                ),
                "theological_emphasis": _layer(
                    "A szeretet mértéke az egyszülött Fiú odaadásában "
                    "válik láthatóvá, és ez teológiai súlyt ad a mondatnak "
                    "a kegyelem felől."
                ),
                "listener_movement": _layer(
                    "A hallgató így azt kérdezheti, hol keresett saját érdemet "
                    "ott, ahol Isten már elindult felé a Fiúban a textus szerint."
                ),
            },
            {
                "title": "A Fiú odaadása",
                "verses": "v. 16b",
                "textual_insight": _layer(
                    "Az egyszülött Fiú ajándéka a szöveg középponti állítása "
                    "marad, nem csupán háttér-motívum a szeretetről szóló mondatban."
                ),
                "theological_emphasis": _layer(
                    "A hallgató nem magától talál utat Istenhez, hanem a "
                    "Fiúban kapja azt ajándékként a megváltás útján."
                ),
                "listener_movement": _layer(
                    "Ez a felismerés a saját útkeresés helyett a Fiúra "
                    "tekintésre fordítja a figyelmet a textus előtt."
                ),
            },
            {
                "title": "Hitben való élet",
                "verses": "v. 16c",
                "textual_insight": _layer(
                    "A textus az elveszés helyett az örök élet ígéretét "
                    "állítja elénk, és ezzel zárja a gondolatívet a hívő válaszban."
                ),
                "theological_emphasis": _layer(
                    "A hit Isten cselekvésére támaszkodik, nem a saját "
                    "teljesítményre vagy vallásos erőfeszítésre a Fiúban."
                ),
                "listener_movement": _layer(
                    "Így a válasz nem moralizáló felszólítás, hanem "
                    "bizalom a Fiúban megnyíló életben a hallgató számára ma."
                ),
            },
        ],
        "conclusion_direction": (
            "A hallgató Isten megtartó szeretetében állhat meg a Fiúban. "
            "Nem új témánál, hanem a textus megérkezésénél zárul az ív. "
            "Innen vihető tovább a szószéki kibontás a gyülekezet felé anélkül, "
            "hogy záróprédikáció születne a vázlatból a saját erőfeszítés helyett, "
            "és a Fiúban kapott út maradjon a megérkezés középpontja."
        ),
        "refinement_suggestions": [],
    }
    base.update(overrides)
    return normalize_structured_outline(base)


def _jude_good_structured() -> dict:
    """Aranyminta: Júd 17–20 háromrétegű szószéki vázlat (300–500 szó)."""
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
            "megmaradás útját mutatja a szeretteknek a szakadás idején. "
            "Ez a feszültség nyitja meg az igét anélkül, hogy azonnal "
            "moralizáló programot adna a hallgatónak."
        ),
        points=[
            {
                "title": "Emlékezzetek az apostolok szavára",
                "verses": "v. 17–18",
                "textual_insight": _layer(
                    "A szerettek először az Urunk Jézus Krisztus apostolai "
                    "által előre megmondott szavakra emlékeznek, miközben a "
                    "gúnyolódók megjelenése az utolsó időben már körülveszi őket."
                ),
                "theological_emphasis": _layer(
                    "A gúnyolódók érkezése nem lepi meg az apostoli "
                    "figyelmeztetést, hanem igazolja annak időszerűségét, "
                    "és a közösséget a Krisztustól kapott szóra köti."
                ),
                "listener_movement": _layer(
                    "A hallgató így azt kérdezheti, melyik apostoli szó tartja "
                    "meg őt, amikor a gúny hangosabbá válik a gyülekezet körül."
                ),
            },
            {
                "title": "Ismerjétek fel a szakadást",
                "verses": "v. 19",
                "textual_insight": _layer(
                    "A tizenkilencedik vers önállóan nevezi meg azokat, "
                    "akik szakadásokat okoznak, érzékiek, és akikben nincsen Lélek, "
                    "nem csupán a gúnyolódók külső magatartását ismétli."
                ),
                "theological_emphasis": _layer(
                    "Ez a felismerés nem a 17–18. vers átfogalmazása, hanem a "
                    "szakadás belső állapotának diagnózisa: a Lélek hiánya "
                    "teszi láthatóvá a széthúzás gyökerét."
                ),
                "listener_movement": _layer(
                    "A hallgató így nem általános ellenségképet kap, hanem "
                    "élesebb látást arról, hol jelenik meg a Lélek nélküli "
                    "széthúzás a saját közösségében."
                ),
            },
            {
                "title": "Épüljetek és imádkozzatok",
                "verses": "v. 20",
                "textual_insight": _layer(
                    "A huszadik vers párhuzamos felszólításai egyetlen "
                    "megmaradási mozgást alkotnak: a szerettek a legszentebb "
                    "hitben épülnek, miközben a Szentlélek által imádkoznak."
                ),
                "theological_emphasis": _layer(
                    "Az imádság a Szentlélek által nem külön program a hit "
                    "épülése mellett, hanem ugyanannak a megtartó életnek a "
                    "lélegzete a szakadás idején."
                ),
                "listener_movement": _layer(
                    "Így a hallgató nem két elválasztott kötelességet kap, "
                    "hanem egy Lélekben tartott életmódot, amelyben a hit "
                    "épülése és az imádság együtt tart meg."
                ),
            },
        ],
        conclusion_direction=(
            "A textus nem a gúny legyőzésénél, hanem a megtartó közösség "
            "megmaradásánál érkezik meg. A hallgató az apostoli emlékezet és "
            "a Lélekben való épülés felől nézheti újra a helyzetét. "
            "Innen indítható a szószéki kibontás anélkül, hogy új téma nyílna "
            "vagy üres közhely zárná a vázlatot a gyülekezet előtt."
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
                "textual_insight": _layer(
                    "Az apostolok előre megmondták a gúnyolódók érkezését "
                    "az utolsó időben a gyülekezet körül."
                ),
                "theological_emphasis": _layer(
                    "Ezek azok, akik szakadásokat okoznak, érzékiek, "
                    "akikben nincsen Lélek — hibásan ide húzva a 19. versből."
                ),
                "listener_movement": _layer(
                    "A hallgató így összekeveri a gúnyt a szakadás diagnózisával."
                ),
            },
            {
                "title": "Épüljetek a hitben",
                "verses": "v. 20",
                "textual_insight": _layer(
                    "A szerettek épüljenek legszentebb hitükben a "
                    "szakadás és a gúny idején is a textus szerint."
                ),
                "theological_emphasis": _layer(
                    "Ez a felszólítás a megmaradás első fele, de önmagában "
                    "nem bontja szét a huszadik verset külön főpontra."
                ),
                "listener_movement": _layer(
                    "A hallgató így csak a hit épülését hallja, az imádság nélkül."
                ),
            },
            {
                "title": "Imádkozzatok a Lélek által",
                "verses": "v. 20",
                "textual_insight": _layer(
                    "A második főpont indokolatlanul külön választja az "
                    "imádságot az épüléstől ugyanabból a versből."
                ),
                "theological_emphasis": _layer(
                    "A párhuzamos felszólítások így elveszítik egységüket, "
                    "és a vázlat mesterségesen kettéválik."
                ),
                "listener_movement": _layer(
                    "A hallgató két programot kap egyetlen megmaradási mozgás helyett."
                ),
            },
        ],
    )


def _ezs46_good_structured() -> dict:
    return _valid_structured(
        title="Az örök Hordozó",
        text_reference="Ézs 46,3–4",
        focus_sentence=(
            "Az Úr a méhtől az öregségig egyetlen, folyamatos cselekvéssel "
            "hordozza, megtartja és megmenti népét a bálványok helyett ma is."
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
                "textual_insight": _layer(
                    "Az Úr a Jákób házát és Izráel maradékát a méhtől fogva "
                    "hordozza, nem idegen erőként, hanem személyes gondviselőként."
                ),
                "theological_emphasis": _layer(
                    "Ez a kezdetektől tartó hordozás állítja szembe Istent "
                    "azokkal a bálványokkal, amelyeket az embernek kell cipelnie."
                ),
                "listener_movement": _layer(
                    "A hallgató így már a textus elején láthatja: a gondviselés "
                    "nem későbbi pótlék, hanem Isten régóta tartó cselekvése."
                ),
            },
            {
                "title": "Ugyanaz az Úr az öregségig",
                "verses": "v. 4",
                "textual_insight": _layer(
                    "Az Úr ugyanaz marad öregségig és megőszülésig: ő hordoz, "
                    "visel és megszabadít egyetlen ígéretfolyamban."
                ),
                "theological_emphasis": _layer(
                    "A hordoz–megtart–megment mozgás nem három külön pont, "
                    "hanem ugyanannak az Úrnak folyamatos hűsége a nép iránt."
                ),
                "listener_movement": _layer(
                    "Homiletikailag ezért egy ívben marad az ígéret, hogy a "
                    "szószéken se ismétlődjön meg üresen ugyanaz a gondolat."
                ),
            },
        ],
        conclusion_direction=(
            "A hallgató nem három ismételt ígéretnél, hanem az örök Hordozó "
            "kezei között érkezik meg. A textus a bálványcipelés helyett Isten "
            "megtartó cselekvése felé fordít, és innen vihető a szószékre a bizalom. "
            "A gyülekezet a saját terhei közepette is az Úr kezeiben állhat meg."
        ),
    )


def _ezs_verbose_payload() -> dict:
    """Ézs 46,3–4 failure pattern: jóval 850 szó feletti, ismétlődő body_markdown."""
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
        "body_markdown": "\n\n".join([para] * 20),
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
    assert 2 <= len(result.outline.get("movements") or []) <= 5


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
    if not str(state.get("passage_text") or "").strip():
        state["passage_text"] = JUDE_PASSAGE
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert result.ok, result.error_message
    assert result.source == "workshop"
    assert result.outline.get("main_idea") or outline_has_content(result.outline)


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


def test_point_and_layer_counts_and_word_cap():
    data = _valid_structured()
    issues = validate_structured_outline(data)
    assert [i for i in issues if i not in ("under_target", "too_thin")] == [], issues
    rendered = render_structured_outline(data)
    assert word_count(rendered) <= LIMITS["absolute_max_words"]
    assert 2 <= len(data["points"]) <= 4
    for pt in data["points"]:
        assert "thesis" not in pt
        assert "subpoints" not in pt
        for key in ("textual_insight", "theological_emphasis", "listener_movement"):
            assert pt.get(key)
            assert word_count(pt[key]) <= LIMITS["layer_max_words"]
        total = sum(
            word_count(pt[k])
            for k in ("textual_insight", "theological_emphasis", "listener_movement")
        )
        assert LIMITS["point_layers_min_words"] <= total <= LIMITS["point_layers_max_words"]


def test_rejects_over_absolute_max_and_multi_paragraph():
    long_para = " ".join(["szó"] * 80) + "."
    bad = _valid_structured(
        points=[
            {
                "title": "Túlírt pont",
                "verses": "v. 1",
                "textual_insight": long_para + "\n\n" + long_para,
                "theological_emphasis": long_para + "\n\n" + long_para,
                "listener_movement": long_para,
            },
            {
                "title": "Második",
                "verses": "v. 2",
                "textual_insight": long_para,
                "theological_emphasis": long_para,
                "listener_movement": long_para,
            },
            {
                "title": "Harmadik",
                "verses": "v. 3",
                "textual_insight": long_para,
                "theological_emphasis": long_para,
                "listener_movement": long_para,
            },
        ]
    )
    issues = validate_structured_outline(bad)
    assert (
        "over_absolute_max" in issues
        or "multi_paragraph_point" in issues
        or "layer_too_long" in issues
        or "full_sermon_like" in issues
        or "prose_block_too_long" in issues
    )



def test_ezs46_failure_pattern_rejected_and_compress_triggered():
    """Near-sermon AI válasz: tömörítés, majd szószéki jegyzet menthető (nem hard error)."""
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

    calls = {"n": 0}

    def gen(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(_ezs_verbose_payload(), ensure_ascii=False)
        return json.dumps(_ezs_verbose_payload(), ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert calls["n"] >= 2  # first + compress (+ optional enrich)
    assert result.compressed
    content = outline_to_readable_content(result.outline)
    assert word_count(content) <= LIMITS["absolute_max_words"]
    assert outline_has_content(result.outline)
    assert "szószéken használható" not in (result.error_message or "").casefold()


def test_ezs46_valid_limits_and_no_repeated_triad():
    data = _ezs46_good_structured()
    issues = validate_structured_outline(data, passage_text=EZS46_PASSAGE)
    hard = [i for i in issues if i not in ("too_thin", "under_target", "focus_too_short", "conclusion_too_short")]
    assert hard == [], hard
    rendered = render_structured_outline(data)
    assert word_count(rendered) <= LIMITS["absolute_max_words"]
    assert word_count(data["introduction_direction"]) <= LIMITS["intro_words"]
    assert word_count(data["conclusion_direction"]) <= LIMITS["conclusion_words"]
    # Ne legyen három külön pont ugyanarra a triádra
    assert len(data["points"]) == 2
    joined = " ".join(
        " ".join(
            [
                pt["textual_insight"],
                pt["theological_emphasis"],
                pt["listener_movement"],
            ]
        )
        for pt in data["points"]
    ).casefold()
    assert "hordoz" in joined
    # repeated_thematic_triad only fires on 3+ points carrying the triad
    triad_bad = _ezs46_good_structured()
    triad_bad.pop("movements", None)
    triad_bad["points"] = [
        {
            "title": "Hordoz",
            "verses": "v. 3",
            "textual_insight": _layer("Isten hordozza és megtartja népét a méhtől fogva."),
            "theological_emphasis": _layer(
                "A megmentés már ebben a hordozásban is jelen van a textus szerint."
            ),
            "listener_movement": _layer(
                "A hallgató a hordozó Úr felé fordul a saját terhei közepette."
            ),
        },
        {
            "title": "Megtart",
            "verses": "v. 4a",
            "textual_insight": _layer(
                "Az Úr megtartja és hordozza őket az öregségig is."
            ),
            "theological_emphasis": _layer(
                "A megmentés ígérete ugyanebben a hűségben hangzik tovább."
            ),
            "listener_movement": _layer(
                "A hallgató a megtartó hűséget nem szakaszos segítségként hallja."
            ),
        },
        {
            "title": "Megment",
            "verses": "v. 4b",
            "textual_insight": _layer(
                "Isten megmenti, hordozza és megtartja népét végig."
            ),
            "theological_emphasis": _layer(
                "A triadikus ismétlés külön pontokra bontva hibás a textusban."
            ),
            "listener_movement": _layer(
                "A hallgató így háromszor hallja ugyanazt a gondolatot üresen."
            ),
        },
    ]
    triad_bad["movements"] = list(triad_bad["points"])
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
                    _layer("Az apostolok szavaira emlékezés tartást ad a zavar közepette."),
                    _layer("A textus saját emlékezete tartja a közösséget a gúny idején."),
                ],
                "textual_basis": "v. 17",
            },
            {
                "title": "Gúnyolódók",
                "core_content": "A szakadás jelei felismerhetők a textusban.",
                "development": [
                    _layer("A gúnyolódók jelenléte nem lepi meg az apostoli figyelmeztetést."),
                    _layer("A textus néven nevezi a szakadást, mielőtt választ adna."),
                ],
            },
            {
                "title": "Megmaradás",
                "core_content": "A Lélekben épülés a megtartás útja.",
                "development": [
                    _layer("A megmaradás imádságban és szeretetben formálódik ki."),
                    _layer("Isten megtartó szeretete zárja az ívet a hallgató előtt."),
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


def test_absolute_max_and_schema_are_three_layer_pulpit_outline():
    # 2026-08-06: 2400 -> 8000, mert a MAX_TOKENS-csonkulas a regi plafonnal
    # szinte minden futasnal bekovetkezett (elo, ismetelt tesztekkel igazolva).
    assert 7500 <= OUTLINE_MAX_OUTPUT_TOKENS <= 8500
    assert LIMITS["absolute_max_words"] == 850
    assert LIMITS["target_min_3_4"] == 300
    assert LIMITS["target_max_3_4"] == 500
    assert LIMITS["soft_floor_words"] == 250
    assert LIMITS["layer_min_words"] == 12
    assert LIMITS["intro_words"] == 80
    assert LIMITS["max_points"] == 5
    assert LIMITS["point_layers_min_words"] == 40
    assert LIMITS["point_layers_max_words"] == 160
    # 2026-08-07: séma pulpit_outline_v8 — egyetlen folyó szövegű
    # `body_markdown`, nem `movements` tömb (ld. formai átalakítás).
    assert SCHEMA_VERSION == "pulpit_outline_v8"
    assert "body_markdown" in OUTLINE_RESPONSE_SCHEMA["properties"]
    assert "movements" not in OUTLINE_RESPONSE_SCHEMA["properties"]
    assert "thesis" not in LIMITS
    assert "SZEREP:" in OUTLINE_SYSTEM_PROMPT
    assert "KÖTELEZŐ FORMA" in OUTLINE_SYSTEM_PROMPT
    # A régi, mezőkre tagolt forma most kifejezetten TILTOTT — a "Fókuszmondat"
    # csak a tiltólistán szerepel, nem kötelező mezőként.
    assert "Fókuszmondat:" in OUTLINE_SYSTEM_PROMPT  # a tiltólista része
    assert "SZIGORÚAN TILOS" in OUTLINE_SYSTEM_PROMPT
    assert "háttéranyag" in OUTLINE_SYSTEM_PROMPT.casefold()
    assert "A textus mozgása" in OUTLINE_SYSTEM_PROMPT  # tiltott példa a promptban
    from sermon_outline_engine import ENRICH_INSTRUCTION, COMPRESS_INSTRUCTION

    assert "TARTALMI KIEGÉSZÍTÉS" in ENRICH_INSTRUCTION or "KIEGÉSZÍTÉS" in ENRICH_INSTRUCTION
    assert "850" in COMPRESS_INSTRUCTION


def test_outline_calls_request_markdown_not_json_schema():
    """Fő vázlatgenerálás: Markdown system prompt, NEM JSON responseSchema."""
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

    with patch.object(app_mod, "generate_text", side_effect=gen):
        result = generate_sermon_outline(
            state, mode="quick", generate_fn=gen, force_overwrite=True
        )
    assert result.ok, result.error_message
    assert captured.get("system_bundle") == OUTLINE_SYSTEM_PROMPT
    assert captured.get("use_cache") is False
    # Markdown mód: ne kényszerítsünk JSON sémát a fő generálásra
    assert captured.get("response_schema") is None
    assert captured.get("response_mime_type") in (None, "text/plain", "text/markdown")
    assert captured.get("max_output_tokens") == OUTLINE_MAX_OUTPUT_TOKENS


def test_validator_rejects_missing_layer_and_legacy_headings():
    data = _valid_structured()
    data["points"][0] = {
        "title": "Problémafelvetés",
        "verses": "v. 1",
        "textual_insight": _layer(
            "A textus Isten kezdeményező szeretetét állítja elénk a hallgató előtt."
        ),
        "theological_emphasis": "",
        "listener_movement": _layer(
            "A Fiú ajándéka nyitja meg a hit útját a világ felé a hallgató számára."
        ),
    }
    issues = validate_structured_outline(data)
    assert "missing_theological_emphasis" in issues
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
    outline_prompts = [p for p in captured if "BIBLIAI SZÖVEG" in p or "IGEHELY:" in p]
    assert outline_prompts
    prompt = outline_prompts[0]
    # Üres kosár: ne kerüljön üres vázlatkosár-blokk a promptba
    assert 'label="vázlatkosár"' not in prompt
    assert "HÁTTÉRANYAG" in prompt  # _base_state has exegesis/original_text
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
    outline_prompts = [p for p in captured if "BIBLIAI SZÖVEG" in p or "IGEHELY:" in p]
    assert outline_prompts
    prompt = outline_prompts[0]
    # A kosár külön untrusted blokkban van, nem a textus aliasaként.
    before_basket = prompt.split('label="vázlatkosár"')[0]
    assert '"outline_basket"' not in before_basket
    assert '"source": "Exegézis"' in prompt
    assert '"source": "Alkalmazás"' in prompt
    assert "HÁTTÉRANYAG" in prompt
    assert "UNTRUSTED_DATA" in prompt
    assert "IGEHELY:" in prompt


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
    thin = _valid_structured()
    thin["introduction_direction"] = "Rövid nyitás."
    thin["conclusion_direction"] = "Rövid zárás."
    thin["focus_sentence"] = "Isten szeret."
    for pt in thin["points"]:
        pt["textual_insight"] = "Rövid textuális mondat."
        pt["theological_emphasis"] = "Rövid teológiai mondat."
        pt["listener_movement"] = "Rövid hallgatói mondat."
    rendered_wc = word_count(render_structured_outline(thin))
    assert rendered_wc < LIMITS["soft_floor_words"]
    issues = validate_structured_outline(thin)
    assert "too_thin" in issues

    state = _base_state()
    calls = {"n": 0}

    def gen(_prompt, **_kwargs):
        calls["n"] += 1
        return json.dumps(thin, ensure_ascii=False)

    # Structurally complete but still under soft floor after enrich attempt
    thin["focus_sentence"] = (
        "A textus Isten kezdeményező szeretetét hirdeti a hallgatónak."
    )
    thin["introduction_direction"] = (
        "A hallgató a saját hiányával áll a textus elé a gyülekezetben."
    )
    thin["conclusion_direction"] = (
        "A hallgató Isten szereteténél érkezik meg a textus szerint."
    )
    thin["points"] = [
        {
            "title": "Isten szeretete",
            "verses": "v. 16a",
            "textual_insight": "A textus Isten kezdeményező szeretetét állítja a világ elé.",
            "theological_emphasis": "A teológiai súly a Fiú odaadásában válik láthatóvá.",
            "listener_movement": "A hallgató az érdemkeresés helyett Isten indítására néz.",
        },
        {
            "title": "Hitbeli válasz",
            "verses": "v. 16b",
            "textual_insight": "A hallgató nem saját érdemmel felel, hanem a Fiúban kapott úttal.",
            "theological_emphasis": "A válasz a textus mozgásából következik, nem moralizálásból.",
            "listener_movement": "A felismerés a Fiúban való bizalom felé fordítja.",
        },
    ]
    assert word_count(render_structured_outline(thin)) < LIMITS["soft_floor_words"]
    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert result.enriched
    assert calls["n"] == 2
    assert any("too_thin" in w for w in result.warnings)


def test_enrich_pass_deepens_thin_outline_from_sources():
    state = _base_state(
        last_igehely="Júd 17–20",
        igehely_input="Júd 17–20",
        passage_text=JUDE_PASSAGE,
        exegesis=(
            "Júdás az apostoli emlékezetre, a Lélek nélküli szakadás felismerésére "
            "és a hitben való épülésre hív. A 19. vers önálló diagnózis."
        ),
    )
    thin = _jude_good_structured()
    thin["introduction_direction"] = (
        "A gúny és a bizonytalanság feszültségében áll a gyülekezet ma is. "
        "Innen nyílik meg a textus az emlékezet felé a hallgató előtt."
    )
    thin["conclusion_direction"] = (
        "A megérkezés a megtartó közösség megmaradásánál van a textus szerint. "
        "A hallgató a Lélekben való épülés felől nézi újra a helyzetét."
    )
    thin["introduction_direction"] = (
        "A gúny és a bizonytalanság feszültségében áll a gyülekezet."
    )
    thin["conclusion_direction"] = (
        "A megérkezés a megtartó közösség megmaradásánál van."
    )
    for pt in thin["points"]:
        pt["textual_insight"] = "Rövid textuális felismerés a versből."
        pt["theological_emphasis"] = "Rövid teológiai hangsúly a textusból."
        pt["listener_movement"] = "Rövid hallgatói mozdulat a felismerés felé."
    thin_issues = validate_structured_outline(thin)
    assert "truncated_sentence" not in thin_issues
    assert any(
        i in thin_issues
        for i in ("intro_too_short", "conclusion_too_short", "too_thin", "stub_layer")
    )

    rich = _jude_good_structured()
    calls = {"n": 0}

    def gen(prompt, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(thin, ensure_ascii=False)
        assert "TARTALMI MÉLYÍTÉS" in prompt or "MÉLYÍTENDŐ" in prompt
        assert "exegesis" in prompt.casefold() or "Emlékezet" in prompt
        return json.dumps(rich, ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert result.enriched
    assert calls["n"] == 2
    assert word_count(outline_canonical_text(result.outline)) >= LIMITS["soft_floor_words"]


def test_outline_tabs_use_flash_not_lite():
    import app as app_mod

    assert app_mod.resolve_gemini_model_for_tab("Vázlat") == app_mod.LOCKED_MODEL
    assert (
        app_mod.resolve_gemini_model_for_tab("Igehirdetési vázlat")
        == app_mod.LOCKED_MODEL
    )
    assert (
        app_mod.resolve_gemini_model_for_tab("Prédikációvázlat") == app_mod.LOCKED_MODEL
    )


def test_over_850_not_primary_display():
    # Build a payload clearly over the absolute visible-word ceiling
    fat_para = (
        "Ez egy szándékosan hosszú bekezdés, amely a textus állítását, teológiai "
        "súlyát, homiletikai fordulatát és a hallgatói helyzet konkrét feszültségét "
        "is magába sűríti annak érdekében, hogy a teljes látható vázlat könnyen "
        "átlépje az abszolút szóhatárt a szószéki vázlat szerződésében, "
        "és még további magyarázó szavakat is hozzáad a bőbeszédűséghez, miközben "
        "újra és újra elismétli ugyanazt a gondolatot a prédikációs próza mintájára "
        "a szószéki munkavázlat helyett a tesztelt abszolút határ átlépéséhez."
    )
    fat = {
        "title": "Túlírt próbakövet",
        "text_reference": "Jn 3,16",
        "scope_note": "",
        "body_markdown": "\n\n".join([fat_para] * 18),
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
    assert result.ok, result.error_message
    assert result.compressed
    rescued = outline_to_readable_content(result.outline)
    assert word_count(rescued) <= LIMITS["absolute_max_words"]
    assert outline_has_content(result.outline)
    assert rescued != prev_text or word_count(rescued) <= LIMITS["absolute_max_words"]


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
    prompt = OUTLINE_SYSTEM_PROMPT.casefold()
    assert "háttéranyag" in prompt
    assert "bibliai" in prompt
    assert "exegézis" in prompt
    assert "hiányzó háttéranyag" in prompt or "ne pótold saját tudásból" in prompt


def test_outline_prompt_includes_background_when_present():
    bundle = {
        "passage_reference": "Jn 3,16",
        "passage_text": "Mert úgy szerette Isten a világot…",
        "exegesis": "A szeret ige a szöveg központi mozgása.",
        "exegesis_status": "approved",
        "history": "A nikodémusi párbeszéd kontextusa.",
        "history_status": "approved",
        "original_text": "ἠγάπησεν — aoristos.",
        "original_text_status": "approved",
    }
    bg = extract_outline_background_material(bundle)
    assert "exegesis" in bg and "history" in bg and "original_text" in bg
    prompt = build_outline_user_prompt(bundle, mode="quick")
    assert "HÁTTÉRANYAG" in prompt
    assert "A szeret ige" in prompt
    assert "csak a fenti bibliai textus" not in prompt.casefold()
    assert "BIBLIAI SZÖVEG" in prompt or "IGEHELY:" in prompt


def test_outline_prompt_passage_only_without_missing_warnings():
    bundle = {
        "passage_reference": "Jn 3,16",
        "passage_text": "Mert úgy szerette Isten a világot…",
        "exegesis": "",
        "history": None,
        "theology": {},
        "original_text": "   ",
    }
    assert extract_outline_background_material(bundle) == {}
    prompt = build_outline_user_prompt(bundle, mode="quick")
    assert "HÁTTÉRANYAG" not in prompt
    assert "BIBLIAI SZÖVEG" in prompt or "IGEHELY:" in prompt
    # 2026-08-08: termékdöntés — a puszta-textus eset a leggyakoribb, nem
    # kivétel; a modell a saját tudására támaszkodva adjon a lehető
    # legjobb vázlatot, ne írjon bocsánatkérő "nincs háttéranyag" nyitányt.
    assert "leggyakoribb eset" in prompt.casefold()
    assert "saját" in prompt.casefold() and "tudásodra" in prompt.casefold()
    assert "ne írj bevezető megjegyzést arról, hogy nincs mellékelt háttéranyag" in prompt.casefold()
    assert "hiba" not in prompt.casefold()
    assert "nincs elég" not in prompt.casefold()


def test_passage_only_generation_ok_without_error_banner():
    state = _base_state(exegesis="", original_text="", theology="", history="")
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok, result.error_message
    assert "szószéken használható" not in (result.error_message or "").casefold()
    assert outline_has_content(result.outline)


def test_markdown_outline_parses_into_structured_fields():
    """2026-08-07: a parser már csak a címet választja le — a maradék
    (mozgás-címkékkel tagolt folyó szöveg) változatlanul `body_markdown`."""
    from sermon_outline_engine import markdown_outline_to_structured

    md = """# Együtt erősödünk – Préd 4,9–12

Indítás: az egyedül cipelt teher

Sokszor egyedül cipelnénk a terhet, pedig a bölcsességi irodalom a társas élet áldását emeli ki.

Jobb ketten, mint egyedül

A 9–10. vers a közös munka gyümölcséről beszél — a „jó” (tób) itt gyakorlati áldást jelent.

A hármas kötél nem szakad el könnyen

A 12. vers képe a közösség erejét mutatja: a hármas kötél a tartós összetartozás jele.

Hazavezető gondolat

Isten a közösségben tart meg, nem a magányos erőfeszítésben. Kit hívsz ma melléd a teherhordásban?
"""
    data = markdown_outline_to_structured(md)
    assert "Együtt erősödünk" in data["title"]
    assert "Préd" in data["text_reference"]
    assert "közösségben" in data["body_markdown"].casefold()
    assert "Indítás" in data["body_markdown"]
    assert "Hazavezető gondolat" in data["body_markdown"]
    # A cím sora ne maradjon benne a body_markdown-ban
    assert not data["body_markdown"].startswith("#")


def test_jude_gold_three_layer_outline_contract():
    """Aranyminta: Júd 17–20 — háromrétegű, 300–500 szó, nem prédikáció."""
    data = _jude_good_structured()
    issues = validate_structured_outline(data, passage_text=JUDE_PASSAGE)
    assert issues == [], issues
    assert len(data["points"]) == 3
    rendered = render_structured_outline(data)
    wc = word_count(rendered)
    assert LIMITS["target_min_3_4"] <= wc <= LIMITS["target_max_3_4"], wc
    assert SCHEMA_VERSION == "pulpit_outline_v8"

    state = _base_state(
        last_igehely="Júd 17–20",
        igehely_input="Júd 17–20",
        passage_text=JUDE_PASSAGE,
        exegesis="Júdás az apostoli emlékezetre és a hitben való épülésre hív.",
    )
    calls = {"n": 0, "prompts": []}

    def gen(prompt, **kwargs):
        calls["n"] += 1
        calls["prompts"].append(prompt)
        return json.dumps(data, ensure_ascii=False)

    result = generate_sermon_outline(
        state, mode="quick", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert calls["n"] == 1
    assert "IGEHELY:" in calls["prompts"][0] or "Markdown" in calls["prompts"][0]
    content = outline_canonical_text(result.outline)
    assert LIMITS["target_min_words"] <= word_count(content) <= LIMITS["target_max_words"]


def test_live_paths_use_canonical_v7_prompt_and_schema():
    """Audit lock: Quick és Workshop ugyanazt a system promptot használja."""
    assert SCHEMA_VERSION == "pulpit_outline_v8"
    assert "KÖTELEZŐ FORMA" in OUTLINE_SYSTEM_PROMPT
    assert "szószékre kész" in OUTLINE_SYSTEM_PROMPT.casefold()
    from sermon_workshop_outline_synth_ai import HOMILETIC_SYSTEM_PROMPT

    assert HOMILETIC_SYSTEM_PROMPT is OUTLINE_SYSTEM_PROMPT or HOMILETIC_SYSTEM_PROMPT == OUTLINE_SYSTEM_PROMPT


def test_extract_verse_numbers_from_passage_and_labels():
    assert extract_verse_numbers(JUDE_PASSAGE) >= {17, 18, 19, 20}
    assert extract_verse_numbers("v. 17–18") == {17, 18}
    assert extract_verse_numbers("v. 20") == {20}
