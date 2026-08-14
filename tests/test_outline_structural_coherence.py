# ruff: noqa: E402
"""Fázis 2C.1 (célarchitektúra-terv, 2. fázis, 3. rész, 2026-08-13):
a generált vázlat SZERKEZETI koherenciaellenőrzése.

FONTOS FOGALMI HATÁR: ez NEM a hét homiletikai modellelem (Belépés,
Alaphelyzet, ...) teológiai megvalósulásának szemantikai felismerése —
a motor nem állítja, hogy determinisztikusan megítéli, egy beszédegység
ténylegesen "Alaphelyzet"-e. Kizárólag szerkezeti proxykat mér: hány
beszédegység van, és ezek egymástól ténylegesen megkülönböztethetőek-e.

Ez a fájl:
1) unit-tesztekkel bizonyítja a parser (`_extract_markdown_movements`) és
   a szerkezeti ellenőrző (`_assess_outline_structure`) defenzív
   viselkedését, öt eltérő műfajú regressziós mintával;
2) integrációs tesztekkel bizonyítja, hogy az új issue-k a MEGLÉVŐ
   enrich/repair hurokba illeszkednek, sosem mechanikus fallbackhez
   vezetnek, és a 2B AI-only / no-overwrite garanciái érintetlenek
   maradnak.

FONTOS KÜLÖNBSÉGTÉTEL (2026-08-13, commit előtti javítás): a beszéd-
egységek SZÁMA (too_few_speech_units / too_many_speech_units) valódi
kimeneti szerződés — ENRICHABLE (a repair kap esélyt), de HA A REPAIR
UTÁN IS FENNMARAD, blokkoló, retryable validációs hiba lesz, nem puszta
figyelmeztetés. A `units_not_distinct` ezzel szemben SOFT is marad: a
0.60-as hasonlósági küszöb empirikus, ezért repair után is fennmaradva
csak figyelmeztetést kap, nem blokkol.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import (
    COMPRESS_TRIGGER_ISSUES,
    ENRICHABLE_ISSUES,
    LIMITS,
    OUTLINE_SYSTEM_PROMPT,
    SOFT_QUALITY_ISSUES,
    SPEECH_UNIT_DISTINCTNESS_MIN_WORDS,
    SPEECH_UNIT_DISTINCTNESS_SIMILARITY_THRESHOLD,
    _assess_outline_structure,
    _extract_markdown_movements,
    generate_sermon_outline,
    normalize_structured_outline,
    render_structured_outline,
    validate_structured_outline,
)
from sermon_workshop_data import SERMON_WORKSHOP_KEY, save_sermon_outline
from sermon_workshop_outline_ai import outline_has_content, outline_to_readable_content
from tests.test_outline_engine import _base_state, _valid_structured

_NEW_ISSUE_CODES = ("too_few_speech_units", "too_many_speech_units", "units_not_distinct")


# ---------------------------------------------------------------------------
# Segédfüggvények — kanonikus formátumú Markdown vázlattest építése
# ---------------------------------------------------------------------------


def _unit_md(number: int, title: str, *paragraphs: str) -> str:
    body = "\n\n".join(paragraphs)
    return f"**{number}. {title}**\n\n{body}"


def _markdown_outline(title: str, reference: str, units: list[tuple[str, list[str]]]) -> str:
    parts = [f"# {title} – {reference}"]
    for i, (unit_title, paragraphs) in enumerate(units, start=1):
        parts.append(_unit_md(i, unit_title, *paragraphs))
    return "\n\n".join(parts) + "\n"


_DISTINCT_SAMPLE_SENTENCES = (
    "Az apostoli emlékeztetés a gúny közepette tartja meg a közösséget, mert "
    "a korábban kapott tanítás nem veszíti erejét az idő múlásával sem.",
    "A szakadás gyökere nem a külső nyomásban, hanem a Lélek hiányában "
    "rejlik, ami láthatóvá teszi a valódi lelki állapotot a gyülekezetben.",
    "A pásztor gondviselése a zöld legelőtől a halál árnyékáig kíséri a "
    "nyájat, és a bizalom nem a körülményektől, hanem a jelenléttől függ.",
    "A hazatérő fiú elé fut az apa, mielőtt bármit mondhatna, és az ünnepi "
    "lakoma a megbocsátás nyilvános, ellenállhatatlan kifejezése lesz.",
)


def _distinct_unit_body(index: int) -> str:
    """Valódi, egymástól tartalmilag eltérő mondat — NEM sablonból,
    csak a sorszámban eltérő szöveg, mert az álnév-szintű ismétlődés
    (azonos töltelékszavak) hamis `units_not_distinct` jelzést adna."""
    return _DISTINCT_SAMPLE_SENTENCES[(index - 1) % len(_DISTINCT_SAMPLE_SENTENCES)]


def _long_paragraph(seed: str, n_words: int = 24) -> str:
    """Legalább `n_words` szavas, egyedi bekezdés a `seed` köré."""
    filler = (
        "a textus saját mozgása szerint a hallgató előtt a szószéki "
        "felkészülés során is tartósan megmarad"
    ).split()
    words = seed.split()
    while len(words) < n_words:
        words.extend(filler)
    return " ".join(words[:n_words]).rstrip(".,;:") + "."


# ---------------------------------------------------------------------------
# 1. _extract_markdown_movements — defenzív parser
# ---------------------------------------------------------------------------


def test_extract_movements_empty_and_none_inputs_return_empty_list():
    assert _extract_markdown_movements("") == []
    assert _extract_markdown_movements(None) == []
    assert _extract_markdown_movements("   \n\n  ") == []


def test_extract_movements_pure_prose_without_headings_returns_empty_list():
    text = (
        "# Cím – Jn 3,16\n\n"
        "Ez egy olyan válasz, amely nem tartalmaz számozott, félkövér "
        "mozgás-címeket, csak folyó prózát a régi, tiltott formátumból "
        "visszaesve, vagy egyszerűen hibásan formázva."
    )
    assert _extract_markdown_movements(text) == []


def test_extract_movements_recognizes_canonical_bold_numbered_headings():
    text = _markdown_outline(
        "Megtartva",
        "Júd 17–20",
        [
            ("Emlékezzetek az apostoli szóra", [_long_paragraph("Az apostolok szava megtart.")]),
            ("Ismerjétek fel a szakadást", [_long_paragraph("A szakadás jelei láthatók.")]),
            ("Épüljetek a Lélekben", [_long_paragraph("A Lélek épít és megtart.")]),
        ],
    )
    units = _extract_markdown_movements(text)
    assert [u["title"] for u in units] == [
        "Emlékezzetek az apostoli szóra",
        "Ismerjétek fel a szakadást",
        "Épüljetek a Lélekben",
    ]
    assert [u["index"] for u in units] == [1, 2, 3]
    assert all(u["body"] for u in units)


def test_extract_movements_handles_crlf_line_endings_and_stray_whitespace():
    text = (
        "# Cím – Jn 3,16\r\n\r\n"
        "**1.   Első mozgás  **   \r\n\r\n"
        f"{_long_paragraph('Első bekezdés tartalma.')}\r\n\r\n"
        "**2. Második mozgás**\r\n\r\n"
        f"{_long_paragraph('Második bekezdés tartalma.')}\r\n"
    )
    units = _extract_markdown_movements(text)
    assert [u["title"] for u in units] == ["Első mozgás", "Második mozgás"]


def test_extract_movements_does_not_search_for_the_seven_model_element_names():
    """A parser NEM a hét modellelem nevét keresi — bármilyen tartalmi
    cím felismerhető, és fordítva: a hét elem NEVE sem elég önmagában
    (a felismerés a "**N. Cím**" FORMÁTUMON alapul, nem a szótáron)."""
    text = "# Cím – Jn 3,16\n\nBelépés. Alaphelyzet. Fordulópont. Megérkezés. Ebben nincs egyetlen felismerhető, kötelező formájú cím sem."
    assert _extract_markdown_movements(text) == []


# ---------------------------------------------------------------------------
# 2. _assess_outline_structure — mennyiségi korlátok
# ---------------------------------------------------------------------------


def test_assess_structure_accepts_two_three_and_four_units():
    for n in (2, 3, 4):
        units = [
            {"index": i, "title": f"Egység {i}", "body": _distinct_unit_body(i)}
            for i in range(1, n + 1)
        ]
        issues = _assess_outline_structure(units)
        assert not any(code in issues for code in _NEW_ISSUE_CODES), (n, issues)


def test_assess_structure_flags_single_unit_as_too_few():
    units = [{"index": 1, "title": "Egy", "body": _long_paragraph("Egyetlen egység tartalma.")}]
    issues = _assess_outline_structure(units)
    assert "too_few_speech_units" in issues
    assert "too_many_speech_units" not in issues


def test_assess_structure_flags_five_and_seven_units_as_too_many():
    for n in (5, 7):
        units = [
            {"index": i, "title": f"Egység {i}", "body": _long_paragraph(f"Egyedi tartalom {i} a szövegben.")}
            for i in range(1, n + 1)
        ]
        issues = _assess_outline_structure(units)
        assert "too_many_speech_units" in issues, (n, issues)
        assert "too_few_speech_units" not in issues


def test_seven_model_point_labeled_units_are_still_flagged_too_many():
    """Ha valaki (AI-hiba vagy régi minta) szó szerint a hét modellelem
    nevét másolja egyenkénti címként, ez FORMAILAG 7 beszédegység — a
    szerkezeti ellenőrzés a SZÁM alapján jelez, nem a cím szövege
    alapján dönt, tehát ez sosem válik "elfogadott hétpontos" kimenetté."""
    labels = [
        "Belépés",
        "Alaphelyzet",
        "Első fordulópont",
        "Mélyítés és fokozás",
        "Átértelmezés",
        "Második fordulópont",
        "Megérkezés",
    ]
    units = [
        {"index": i, "title": label, "body": _long_paragraph(f"{label} tartalma egyedi módon kifejtve.")}
        for i, label in enumerate(labels, start=1)
    ]
    issues = _assess_outline_structure(units)
    assert "too_many_speech_units" in issues


def test_empty_units_list_produces_no_issue_regardless_of_parser_failure():
    """Ha a parser NEM talál felismerhető címet (pl. hibás/felismerhetetlen
    Markdown), az `_assess_outline_structure([])` NEM jelez
    `too_few_speech_units`-ot — a formai érvényesség más ellenőrzés
    felelőssége."""
    assert _assess_outline_structure([]) == []


# ---------------------------------------------------------------------------
# 3. units_not_distinct — konzervatív hasonlósági ellenőrzés
# ---------------------------------------------------------------------------


def test_near_identical_units_flagged_not_distinct():
    shared = _long_paragraph(
        "Isten megtartja népét a gúny és a szakadás közepette is Krisztusban.",
        n_words=30,
    )
    units = [
        {"index": 1, "title": "Első", "body": shared},
        {"index": 2, "title": "Második", "body": shared},
    ]
    issues = _assess_outline_structure(units)
    assert "units_not_distinct" in issues


def test_thematically_related_but_distinct_units_are_not_flagged():
    """Két egység, amely UGYANARRÓL a témáról (Isten szeretete) szól, de
    ténylegesen eltérő tartalmat fejt ki, NEM kaphat hamis ismétlődési
    jelzést pusztán a közös teológiai szavak miatt."""
    unit_a = _long_paragraph(
        "Isten szeretete a Fiú odaadásában konkrét, történelmi tettben mutatkozik meg.",
        n_words=30,
    )
    unit_b = _long_paragraph(
        "A hallgató mindennapi bizalmatlansága éles ellentétben áll azzal, amit a "
        "kereszt ígér a jövő felől nézve.",
        n_words=30,
    )
    units = [
        {"index": 1, "title": "Első", "body": unit_a},
        {"index": 2, "title": "Második", "body": unit_b},
    ]
    issues = _assess_outline_structure(units)
    assert "units_not_distinct" not in issues


def test_short_units_below_word_threshold_are_not_compared():
    """Rövid egységeknél (a dokumentált `SPEECH_UNIT_DISTINCTNESS_MIN_WORDS`
    szószám alatt) a hasonlósági ellenőrzés NEM fut le — még szó szerint
    azonos, de rövid tartalomra sem jelez, mert nincs elég megbízható jel."""
    short_text = "Rövid, azonos tartalom."
    assert len(short_text.split()) < SPEECH_UNIT_DISTINCTNESS_MIN_WORDS
    units = [
        {"index": 1, "title": "Első", "body": short_text},
        {"index": 2, "title": "Második", "body": short_text},
    ]
    issues = _assess_outline_structure(units)
    assert "units_not_distinct" not in issues


def test_distinctness_threshold_and_min_words_are_named_documented_constants():
    assert isinstance(SPEECH_UNIT_DISTINCTNESS_MIN_WORDS, int)
    assert 0 < SPEECH_UNIT_DISTINCTNESS_SIMILARITY_THRESHOLD < 1


def test_missing_reinterpretation_alone_is_never_an_issue():
    """Az Átértelmezés (opcionális modellelem) hiánya önmagában sosem
    okoz issue-t — az ellenőrzés nem is tud a hét elem nevéről, csak a
    beszédegységek számáról/megkülönböztethetőségéről."""
    units = [
        {"index": 1, "title": "Alaphelyzet és belépés", "body": _distinct_unit_body(1)},
        {"index": 2, "title": "Fordulópont és megérkezés", "body": _distinct_unit_body(2)},
    ]
    issues = _assess_outline_structure(units)
    assert not any(code in issues for code in _NEW_ISSUE_CODES)


# ---------------------------------------------------------------------------
# 4. Öt műfaj — regressziós bizonyíték (NEM teológiai igazságteszt)
# ---------------------------------------------------------------------------


def test_narrative_genre_sample_passes_structural_check():
    text = _markdown_outline(
        "Két testvér, két út",
        "Lk 15,11–24",
        [
            (
                "Az elveszett fiú távozása",
                [_long_paragraph("A fiatalabb fiú elkéri örökségét, és távoli országba megy.", 26)],
            ),
            (
                "A mélypont és a hazafelé forduló szív",
                [_long_paragraph("Az éhínség és a magány hozza el az első valódi felismerést.", 26)],
            ),
            (
                "Az apa fogadása — a megérkezés",
                [_long_paragraph("Az apa elébe fut, és ünnepet rendel a hazatérőnek.", 26)],
            ),
        ],
    )
    structured = normalize_structured_outline({"body_markdown": text})
    issues = validate_structured_outline(structured)
    assert not any(code in issues for code in _NEW_ISSUE_CODES), issues


def test_pauline_argument_genre_sample_passes_structural_check():
    text = _markdown_outline(
        "Nincs kárhoztatás",
        "Róm 8,1–4",
        [
            (
                "Az elítéltetés alóli szabadulás ténye",
                [_long_paragraph("A Krisztusban levőkre nincs többé kárhoztató ítélet.", 26)],
            ),
            (
                "A törvény betöltése a Lélek szerint járóknak",
                [_long_paragraph("A Lélek törvénye szabaddá tesz a bűn és a halál törvényétől.", 26)],
            ),
        ],
    )
    structured = normalize_structured_outline({"body_markdown": text})
    issues = validate_structured_outline(structured)
    assert not any(code in issues for code in _NEW_ISSUE_CODES), issues


def test_wisdom_psalm_genre_sample_passes_structural_check():
    text = _markdown_outline(
        "A pásztor gondviselése",
        "Zsolt 23",
        [
            (
                "A pásztor gondviselése a zöld legelőn és a halál árnyékában",
                [_long_paragraph("Az Úr vezet, táplál és megőriz a legsötétebb völgyben is.", 26)],
            ),
            (
                "A megtartott vendég asztala és otthona",
                [_long_paragraph("A terített asztal és az örökös otthon a bizalom záró képe.", 26)],
            ),
        ],
    )
    structured = normalize_structured_outline({"body_markdown": text})
    issues = validate_structured_outline(structured)
    assert not any(code in issues for code in _NEW_ISSUE_CODES), issues


def test_prophetic_genre_sample_passes_structural_check():
    text = _markdown_outline(
        "Folyjon az igazság",
        "Ám 5,18–24",
        [
            (
                "Az ítélet napjának félreértése",
                [_long_paragraph("Az Úr napja nem a várt biztonságot hozza a hamis vallásosságnak.", 26)],
            ),
            (
                "A látszat-vallásosság leleplezése",
                [_long_paragraph("Az ünnepek és áldozatok önmagukban nem kedvesek Isten előtt.", 26)],
            ),
            (
                "Az igazi elvárás — folyjon az ítélet, mint a víz",
                [_long_paragraph("Az igazságosság állandó, élő folyamként várt el a néptől.", 26)],
            ),
        ],
    )
    structured = normalize_structured_outline({"body_markdown": text})
    issues = validate_structured_outline(structured)
    assert not any(code in issues for code in _NEW_ISSUE_CODES), issues


def test_single_verse_short_textus_genre_sample_passes_structural_check():
    text = _markdown_outline(
        "Isten Fia sír",
        "Jn 11,35",
        [
            (
                "Isten Fia könnyekre fakad",
                [_long_paragraph("A rövid mondat mögött valódi, emberi fájdalom áll a barát sírjánál.", 26)],
            ),
            (
                "A könny és a feltámadás ereje ugyanabban a jelenetben",
                [_long_paragraph("Ugyanaz a Jézus sír és hív életre — a könny nem a tehetetlenség jele.", 26)],
            ),
        ],
    )
    structured = normalize_structured_outline({"body_markdown": text})
    issues = validate_structured_outline(structured)
    assert not any(code in issues for code in _NEW_ISSUE_CODES), issues


# ---------------------------------------------------------------------------
# 5. Rendszerprompt — 2–4 beszédegység, hétpontos modell megmarad
# ---------------------------------------------------------------------------


def test_system_prompt_requests_two_to_four_speech_units():
    assert "2–4" in OUTLINE_SYSTEM_PROMPT
    assert "2–3, EGYMÁSBÓL KÖVETKEZŐ beszédegység" not in OUTLINE_SYSTEM_PROMPT


def test_system_prompt_still_contains_seven_point_recognition_arc():
    for label in (
        "BELÉPÉS",
        "ALAPHELYZET",
        "ELSŐ FORDULÓPONT",
        "MÉLYÍTÉS ÉS FOKOZÁS",
        "ÁTÉRTELMEZÉS",
        "MÁSODIK FORDULÓPONT",
        "MEGÉRKEZÉS",
    ):
        assert label in OUTLINE_SYSTEM_PROMPT, label


def test_limits_speech_units_are_independent_from_legacy_points_limits():
    assert LIMITS["min_speech_units"] == 2
    assert LIMITS["max_speech_units"] == 4
    # A legacy korlátok VÁLTOZATLANOK — 2C.1 nem nyúl hozzájuk.
    assert LIMITS["min_points"] == 2
    assert LIMITS["max_points"] == 5


def test_parser_recognizes_the_exact_format_the_system_prompt_prescribes():
    """A rendszerprompt (OUTLINE_SYSTEM_PROMPT "MOZGÁS-CÍMEK" szakasza)
    konkrét példákat ad a kötelező mozgás-cím formátumra — ez a teszt
    ugyanazt a mintát futtatja át a VALÓDI parseren, hogy a leírás és a
    `_MOVEMENT_HEADING_RE` regex ne csússzon szét egymástól."""
    prompt_flat = " ".join(OUTLINE_SYSTEM_PROMPT.split())
    assert "**1. A kezdetek: két testvér, két út**" in prompt_flat
    assert "**2. Az áldozat és az elutasítás**" in prompt_flat
    sample = (
        "# Cím – Igehely\n\n"
        "**1. A kezdetek: két testvér, két út**\n\n"
        f"{_distinct_unit_body(1)}\n\n"
        "**2. Az áldozat és az elutasítás**\n\n"
        f"{_distinct_unit_body(2)}\n"
    )
    units = _extract_markdown_movements(sample)
    assert [u["title"] for u in units] == [
        "A kezdetek: két testvér, két út",
        "Az áldozat és az elutasítás",
    ]
    issues = _assess_outline_structure(units)
    assert not any(code in issues for code in _NEW_ISSUE_CODES)


def test_speech_unit_count_issues_are_enrichable_but_not_soft():
    """A beszédegység-SZÁM (too_few/too_many) ENRICHABLE — a meglévő
    repair-hurok kap esélyt —, de NEM soft-only: ha a javítás után is
    fennmarad, blokkoló hibává válik (ld. az integrációs teszteket
    lentebb). `units_not_distinct` viszont SOFT is marad — a 0.60-as
    hasonlósági küszöb empirikus, nem elég megbízható kemény
    elutasításhoz."""
    for code in ("too_few_speech_units", "too_many_speech_units"):
        assert code in ENRICHABLE_ISSUES, code
        assert code not in SOFT_QUALITY_ISSUES, code
        assert code not in COMPRESS_TRIGGER_ISSUES, code
    assert "units_not_distinct" in ENRICHABLE_ISSUES
    assert "units_not_distinct" in SOFT_QUALITY_ISSUES
    assert "units_not_distinct" not in COMPRESS_TRIGGER_ISSUES


# ---------------------------------------------------------------------------
# 6. Integráció — repair/enrich hurok, AI-only és no-overwrite garanciák
# ---------------------------------------------------------------------------


def _too_few_units_markdown() -> str:
    return _markdown_outline(
        "Egyetlen egység",
        "Jn 3,16",
        [
            (
                "Isten szeretete a Fiúban",
                [
                    _long_paragraph("Isten szeretete Fiában adja a megváltás útját.", 40),
                    _long_paragraph("A hallgató hitbeli bizalomra kap meghívást a textus szerint.", 40),
                ],
            ),
        ],
    )


def _compliant_two_unit_markdown() -> str:
    return _markdown_outline(
        "Isten szeretete a Fiúban",
        "Jn 3,16",
        [
            (
                "Isten cselekvő szeretete",
                [_long_paragraph("A textus Isten kezdeményező szeretetéről beszél, nem emberi érdemről.", 40)],
            ),
            (
                "A hitben való élet",
                [_long_paragraph("A hallgató a Fiúban kapott életre bízhatja magát, nem saját erejére.", 40)],
            ),
        ],
    )


def _many_units_markdown(n: int) -> str:
    return _markdown_outline(
        "Túl sok egység",
        "Jn 3,16",
        [(f"Egység {i}", [_distinct_unit_body(i)]) for i in range(1, n + 1)],
    )


def _near_duplicate_two_unit_markdown() -> str:
    shared = _long_paragraph(
        "Isten megtartja népét a gúny és a szakadás közepette is Krisztusban.",
        n_words=40,
    )
    return _markdown_outline(
        "Ismétlődő egységek", "Jn 3,16", [("Első", [shared]), ("Második", [shared])]
    )


def test_too_few_speech_units_triggers_repair_attempt():
    """1 egységes AI-válasz esetén a MEGLÉVŐ enrich-hurok (nem új motor)
    automatikusan egy második hívást indít — nem áll meg az első,
    formailag hiányos válasznál."""
    calls = {"n": 0}

    def gen(_prompt=None, **_kwargs):
        calls["n"] += 1
        return _too_few_units_markdown()

    state = _base_state()
    generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert calls["n"] >= 2


def test_successful_enrich_repairs_too_few_speech_units():
    """Első AI-válasz 1 egységes (too_few) — a repair második hívással
    kap esélyt, és ha az megfelelő (2–4 egységes) választ ad, a
    végleges vázlat issue nélkül, sikeresen elkészül."""
    calls = {"n": 0}

    def gen(_prompt=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _too_few_units_markdown()
        return _compliant_two_unit_markdown()

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert result.ok, result.error_message
    assert calls["n"] >= 2
    assert result.enriched


def test_persistent_too_few_speech_units_is_rejected_as_validation_failed():
    """Ha a repair-kísérlet(ek) UTÁN is 1 egység marad (a modell
    mindig ugyanazt az 1 egységes választ adja), a generálás NEM
    fogadja el a formailag hiányos AI-választ — strukturált, retryable
    hibával tér vissza, mechanikus tartalom nélkül."""

    def gen(_prompt=None, **_kwargs):
        return _too_few_units_markdown()

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert not result.ok
    assert result.error_kind == "validation_failed"
    assert result.retryable is True
    assert not outline_has_content(result.outline)


def test_many_speech_units_triggers_repair_attempt():
    calls = {"n": 0}

    def gen(_prompt=None, **_kwargs):
        calls["n"] += 1
        return _many_units_markdown(7)

    state = _base_state()
    generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert calls["n"] >= 2


def test_successful_enrich_repairs_too_many_speech_units():
    calls = {"n": 0}

    def gen(_prompt=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _many_units_markdown(5)
        return _compliant_two_unit_markdown()

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert result.ok, result.error_message
    assert calls["n"] >= 2


def test_persistent_too_many_speech_units_is_rejected_as_validation_failed():
    """5+ egység a repair után is — ugyanaz a blokkoló, retryable
    validációs hiba, mint a too_few esetben."""

    def gen(_prompt=None, **_kwargs):
        return _many_units_markdown(7)

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert not result.ok
    assert result.error_kind == "validation_failed"
    assert result.retryable is True


def test_units_not_distinct_disappears_after_successful_repair():
    calls = {"n": 0}

    def gen(_prompt=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _near_duplicate_two_unit_markdown()
        return _compliant_two_unit_markdown()

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert result.ok, result.error_message
    assert not any("units_not_distinct" in w for w in result.warnings)


def test_units_not_distinct_persists_but_still_accepted_with_warning():
    """A `units_not_distinct` — a too_few/too_many-tól ELTÉRŐEN — akkor
    is elfogadható marad (ok=True), ha a repair sem oldja meg: a 0.60-as
    hasonlósági küszöb empirikus, nem elég megbízható kemény
    elutasításhoz. A figyelmeztetés viszont kötelező."""

    def gen(_prompt=None, **_kwargs):
        return _near_duplicate_two_unit_markdown()

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=gen)
    assert result.ok, result.error_message
    assert any("units_not_distinct" in w for w in result.warnings)


def test_previous_approved_outline_preserved_after_persistent_speech_unit_failure():
    """A 2B no-overwrite garanciája a 2C.1 blokkoló egységszám-hibára is
    érvényes: egy korábban mentett vázlat egy sikertelen (perzisztensen
    too_few) regenerálási kísérlet után bájtra pontosan megmarad."""

    def gen_ok(_prompt=None, **_kwargs):
        return _compliant_two_unit_markdown()

    state = _base_state()
    first = generate_sermon_outline(state, mode="workshop", generate_fn=gen_ok)
    assert first.ok
    save_sermon_outline(state, first.outline, mark_manual_edit=False)
    before = json.dumps(state[SERMON_WORKSHOP_KEY]["sermon_outline"], sort_keys=True)

    def gen_bad(_prompt=None, **_kwargs):
        return _too_few_units_markdown()

    failed = generate_sermon_outline(
        state, mode="workshop", generate_fn=gen_bad, force_overwrite=True
    )
    assert not failed.ok
    assert failed.error_kind == "validation_failed"
    after = json.dumps(state[SERMON_WORKSHOP_KEY]["sermon_outline"], sort_keys=True)
    assert before == after


def test_new_project_has_no_savable_outline_after_persistent_speech_unit_failure():
    """Új projektben (nincs korábbi mentett vázlat) egy perzisztensen
    too_few válasz után nincs menthető, jóváhagyható vagy Wordbe
    exportálható kész vázlat — a visszaadott outline üres marad."""

    def gen_bad(_prompt=None, **_kwargs):
        return _too_few_units_markdown()

    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=gen_bad)
    assert not result.ok
    assert not outline_has_content(result.outline)
    assert outline_to_readable_content(result.outline).strip() == ""


def test_previous_approved_outline_preserved_on_hard_ai_failure():
    """A 2B AI-only/no-overwrite garanciája érintetlen: kemény AI-hiba
    (nem a szerkezeti soft-issue) esetén a korábbi, mentett vázlat
    változatlanul megmarad."""

    def gen_ok(_prompt=None, **_kwargs):
        return _compliant_two_unit_markdown()

    state = _base_state()
    first = generate_sermon_outline(state, mode="workshop", generate_fn=gen_ok)
    assert first.ok
    save_sermon_outline(state, first.outline, mark_manual_edit=False)
    before = json.dumps(state[SERMON_WORKSHOP_KEY]["sermon_outline"], sort_keys=True)

    def boom(*_a, **_k):
        raise RuntimeError("offline")

    failed = generate_sermon_outline(
        state, mode="workshop", generate_fn=boom, force_overwrite=True
    )
    assert not failed.ok
    assert failed.error_kind == "ai_call_failed"
    after = json.dumps(state[SERMON_WORKSHOP_KEY]["sermon_outline"], sort_keys=True)
    assert before == after


def test_legacy_five_point_outline_loads_and_exports_unaffected(monkeypatch):
    """Régi, points[]-alapú (body_markdown ÜRES), akár ötpontos mentett
    vázlat: az új szerkezeti ellenőrzés NEM fut le rá (a `body` ág csak
    `body_markdown` jelenlétekor aktív), betölthető, megjeleníthető és
    Word-exportálható marad."""
    legacy = _valid_structured(
        points=[
            {
                "title": f"Pont {i}",
                "verses": f"v. {i}",
                "textual_insight": _long_paragraph(f"Régi pont {i} textuális felismerése.", 20),
                "theological_emphasis": _long_paragraph(f"Régi pont {i} teológiai súlya.", 20),
                "listener_movement": _long_paragraph(f"Régi pont {i} hallgatói mozdulata.", 20),
            }
            for i in range(1, 6)
        ]
    )
    assert legacy["body_markdown"] == ""
    issues = validate_structured_outline(legacy)
    assert not any(code in issues for code in _NEW_ISSUE_CODES)

    rendered = render_structured_outline(legacy)
    assert rendered.strip()

    import io

    from docx import Document

    import streamlit as st

    from outline_word_export import build_outline_docx

    session = {
        "last_igehely": "Jn 3,16",
        "last_alkalom": "vasárnapi igehirdetés",
        "last_stilus": "expozíciós",
        "outline": rendered,
        "basket": [],
        "songs": "",
    }
    monkeypatch.setattr(st, "session_state", session)
    docx_bytes = build_outline_docx()
    assert docx_bytes[:2] == b"PK"
    doc = Document(io.BytesIO(docx_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Pont 1" in full_text or "Régi pont 1" in full_text
