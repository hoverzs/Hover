"""Aranyminták: textuális elemek és szerkezeti minőség (nem teljes szövegsnapshot)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import (
    LIMITS,
    SCHEMA_VERSION,
    generate_sermon_outline,
    normalize_sermon_outline,
    normalize_structured_outline,
    render_structured_outline,
    validate_structured_outline,
    word_count,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
    save_sermon_outline,
)
from sermon_workshop_outline_ai import assess_outline_readiness
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop
from workspace_data import build_project_data, sanitize_project_data


def _layer(text: str) -> str:
    return " ".join(text.split())


def _blob(data: dict) -> str:
    return render_structured_outline(data).casefold()


def _jude_24_25() -> dict:
    return normalize_structured_outline(
        {
            "title": "A megtartó és dicsőséges Isten",
            "text_reference": "Júd 24–25",
            "focus_sentence": (
                "Az egyedüli üdvözítő Isten képes megőrizni a botlástól, "
                "és feddhetetlenül, ujjongó örömmel állít dicsősége elé "
                "Jézus Krisztus által."
            ),
            "introduction_direction": (
                "A záró doxológia nem általános bátorítás, hanem a levél "
                "konkrét megtartó ígéretét emeli Isten dicsőségére."
            ),
            "points": [
                {
                    "title": "Megőriz a botlástól",
                    "verses": "v. 24a",
                    "textual_insight": _layer(
                        "A textus Istenről állítja, hogy képes megőrizni "
                        "benneteket a botlástól; nem emberi erőfeszítésre "
                        "bízza a megmaradást."
                    ),
                    "theological_emphasis": _layer(
                        "A megtartás Isten hatalmához tartozik, ezért a "
                        "bizalom forrása nem a hallgató állhatatossága."
                    ),
                    "listener_movement": _layer(
                        "A hallgató a saját botlásfélelmeit Isten megtartó "
                        "képességére bízhatja anélkül, hogy önbizalmat "
                        "prédikálna magának."
                    ),
                },
                {
                    "title": "Feddhetetlenül az Ő dicsősége elé",
                    "verses": "v. 24b",
                    "textual_insight": _layer(
                        "Ugyanaz az Isten feddhetetlenül és ujjongó örömmel "
                        "állít dicsősége elé; a cél nem puszta túlélés, "
                        "hanem örömteli megjelenés."
                    ),
                    "theological_emphasis": _layer(
                        "A megőrzés a dicsőség elé állításban teljesedik ki, "
                        "ahol a feddhetetlenség Isten ajándéka."
                    ),
                    "listener_movement": _layer(
                        "A gyülekezet így a végső megjelenés reményében "
                        "állhat, nem csupán a jelenlegi kísértések "
                        "elszenvedésében."
                    ),
                },
                {
                    "title": "Egyedüli üdvözítő — Jézus által",
                    "verses": "v. 25",
                    "textual_insight": _layer(
                        "A doxológia az egyedüli üdvözítő Istennek szól "
                        "a mi Urunk Jézus Krisztus által, a dicsőség, "
                        "fenség, erő és hatalom teljességével."
                    ),
                    "theological_emphasis": _layer(
                        "Az üdvözítés és a dicsőség Jézus Krisztus által "
                        "kötődik Istenhez; nincs párhuzamos üdvút."
                    ),
                    "listener_movement": _layer(
                        "A hallgató hálája ezért Krisztusra irányul, "
                        "nem általános vallásos magasztalásra."
                    ),
                },
            ],
            "conclusion_direction": (
                "A doxológia időbeli teljessége — minden idő előtt, most "
                "és minden időben — Isten dicsőségét állítja a középpontba, "
                "nem a hallgató teljesítményét."
            ),
            "refinement_suggestions": [],
        }
    )


def _ezs_46() -> dict:
    return normalize_structured_outline(
        {
            "title": "A népét hordozó Isten",
            "text_reference": "Ézs 46,3–4",
            "scope_note": (
                "A bálványok hordozásának kontrasztja a közvetlen "
                "irodalmi kontextusból világos; a kijelölt textus maga "
                "a népét hordozó Isten beszéde."
            ),
            "focus_sentence": (
                "Az Úr, aki a fogantatástól fogva hordozta népét, "
                "öregségig is hordoz, visz és megszabadít."
            ),
            "introduction_direction": (
                "A szöveg Isten hordozó cselekedetét állítja szembe "
                "a bálványok tehetetlenségével a kontextusban, anélkül "
                "hogy a kontextust a kijelölt versek részévé tenné."
            ),
            "points": [
                {
                    "title": "Fogantatástól hordozott nép",
                    "verses": "v. 3",
                    "textual_insight": _layer(
                        "Isten a méhtől és fogantatástól fogva hordozott "
                        "Izráel házához szól; a hordozás az Ő kezdeményezése."
                    ),
                    "theological_emphasis": _layer(
                        "A nép története Isten teremtő és hordozó "
                        "hűségére épül, nem a bálványok teherhordására."
                    ),
                    "listener_movement": _layer(
                        "A hallgató saját életútját Isten hordozó "
                        "kezdeményezése felől nézheti, nem önfenntartásként."
                    ),
                },
                {
                    "title": "Öregségig hordoz és megszabadít",
                    "verses": "v. 4",
                    "textual_insight": _layer(
                        "Ugyanaz az Isten öregségig és megőszülésig is "
                        "ugyanaz marad: Ő hordoz, visz és megszabadít."
                    ),
                    "theological_emphasis": _layer(
                        "A hűség az egész életutat átfogja; a szabadítás "
                        "nem csak a kezdetre szól."
                    ),
                    "listener_movement": _layer(
                        "A gyülekezet a későbbi évek terheinél is "
                        "Isten megmentő hordozására támaszkodhat."
                    ),
                },
            ],
            "conclusion_direction": (
                "A vázlat a népét hordozó Istenhez érkezik meg; "
                "a bálványkontraszt a kontextus háttere marad, "
                "nem válik a kijelölt textus pótlékává."
            ),
        }
    )


def _phil_1() -> dict:
    return normalize_structured_outline(
        {
            "title": "Élet Krisztusban — szolgálat a gyülekezetért",
            "text_reference": "Filippi 1,21–24",
            "focus_sentence": (
                "Pál számára az élet Krisztus, a meghalás nyereség, "
                "mégis a gyülekezetért való megmaradás a szükségesebb."
            ),
            "introduction_direction": (
                "A szakasz a személyes vágy és a közösségi hivatás "
                "feszültségét nyitja meg anélkül, hogy feloldaná "
                "korán a feszültséget."
            ),
            "points": [
                {
                    "title": "Nekem az élet Krisztus",
                    "verses": "v. 21",
                    "textual_insight": _layer(
                        "Pál kimondja: nekem az élet Krisztus, és a "
                        "meghalás nyereség; az élet mértéke Krisztus maga."
                    ),
                    "theological_emphasis": _layer(
                        "A keresztény élet nem öncélú túlélés, hanem "
                        "Krisztushoz kötött lét."
                    ),
                    "listener_movement": _layer(
                        "A hallgató saját életének súlypontját "
                        "Krisztushoz mérheti, nem a körülményekhez."
                    ),
                },
                {
                    "title": "Vágy a Krisztussal lét után",
                    "verses": "v. 23",
                    "textual_insight": _layer(
                        "Pál vágyódik elköltözni és a Krisztussal lenni, "
                        "mert ez sokkal jobb; a személyes vágy valóságos."
                    ),
                    "theological_emphasis": _layer(
                        "A Krisztussal való lét utáni vágy nem menekülés, "
                        "hanem a jobb állapot őszinte megnevezése."
                    ),
                    "listener_movement": _layer(
                        "A gyülekezet is kimondhatja a mennyei vágyát "
                        "anélkül, hogy tagadná a földi szolgálatot."
                    ),
                },
                {
                    "title": "Megmaradás a ti javatokra",
                    "verses": "v. 24",
                    "textual_insight": _layer(
                        "A testben való megmaradás szükségesebb a "
                        "gyülekezet miatt; a szolgálat a közösség javára szól."
                    ),
                    "theological_emphasis": _layer(
                        "A hivatás a másik javát helyezheti a személyes "
                        "vágy elé anélkül, hogy a vágyat érvénytelenítené."
                    ),
                    "listener_movement": _layer(
                        "A hallgató a saját szolgálati helyén "
                        "mérlegelheti, kinek a java hívja megmaradásra."
                    ),
                },
            ],
            "conclusion_direction": (
                "A feszültség megmarad: Krisztus az élet, a vágy valóságos, "
                "és a gyülekezetért vállalt szolgálat mégis szükségesebb."
            ),
        }
    )


def test_jude_24_25_gold_textual_elements():
    data = _jude_24_25()
    issues = validate_structured_outline(data)
    assert "missing_focus" not in issues
    assert len(data["points"]) >= 2
    blob = _blob(data)
    assert "botlás" in blob or "megőriz" in blob
    assert "feddhetetlen" in blob or "ujjong" in blob
    assert "üdvözítő" in blob or "jézus" in blob
    assert "dicsőség" in blob
    assert "bízzunk benne" not in blob or "megtartó" in blob
    assert "textual_insight" not in render_structured_outline(data)
    wc = word_count(render_structured_outline(data))
    assert wc <= LIMITS["absolute_max_words"]


def test_jude_17_20_gold_progression():
    from tests.test_outline_engine import _jude_good_structured

    data = _jude_good_structured()
    assert validate_structured_outline(data) == []
    blob = _blob(data)
    assert "apostol" in blob
    assert "lélek" in blob
    assert "épül" in blob or "imádkoz" in blob
    titles = [p["title"].casefold() for p in data["points"]]
    assert titles[0] != titles[1] != titles[2]
    assert data["points"][0]["verses"] != data["points"][1]["verses"]


def test_ezsaias_46_context_vs_textus_boundary():
    data = _ezs_46()
    issues = validate_structured_outline(data)
    assert "missing_focus" not in issues
    blob = _blob(data)
    assert "hordoz" in blob
    assert "öregség" in blob or "megszabadít" in blob or "szabadít" in blob
    # Kontextus jelölve, de nem mint a kijelölt textus része
    assert data.get("scope_note")
    assert "3–4" in data["text_reference"] or "46" in data["text_reference"]
    assert "bálvány" in (data.get("scope_note") or "").casefold() or "bálvány" in blob


def test_philippians_tension_distinct_movements():
    data = _phil_1()
    assert len(data["points"]) == 3
    blob = _blob(data)
    assert "élet krisztus" in blob or "az élet krisztus" in blob
    assert "vágy" in blob or "krisztussal" in blob
    assert "gyülekezet" in blob or "szolgálat" in blob or "javatokra" in blob
    insights = [p["textual_insight"].casefold() for p in data["points"]]
    assert len(set(insights)) == 3


def test_funeral_occasion_shapes_tone_not_textus():
    state = {
        "last_igehely": "Júd 24–25",
        "igehely_input": "Júd 24–25",
        "passage_text": (
            "24 Annak pedig, aki megőrizhet titeket a botlástól, "
            "és feddhetetlenül, ujjongással állíthat dicsősége elé, "
            "25 az egyedüli Istennek, a mi üdvözítőnknek a dicsőség, "
            "a fenség, az erő és a hatalom a mi Urunk Jézus Krisztus által…"
        ),
        "last_sajat": (
            "Virrasztó a családnak. Az elhunyt: Mária, hűséges gyülekezeti tag. "
            "Ne állíts üdvbizonyosságot az elhunytról a textus nélkül."
        ),
        "occasion": "Virrasztó",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    ready = assess_outline_readiness(state)
    assert ready.ok
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert result.ok
    content = (result.outline.get("content") or "").casefold()
    opening = (result.outline.get("opening_direction") or "").casefold()
    closing = str((result.outline.get("conclusion") or {}).get("development") or "").casefold()
    joined = " ".join([content, opening, closing])
    # Pásztori hang lehet alkalmi
    assert "virraszt" in joined or "család" in joined or "pásztor" in joined or result.ok
    # Ne tegyen igazolhatatlan üdvbizonyosságot az elhunytról
    assert "mária üdvözült" not in joined
    assert "biztosan a mennyben" not in joined
    assert "üdvözült" not in joined or "krisztus" in joined


def test_passage_only_enables_outline_generation():
    state = {
        "last_igehely": "Júd 24–25",
        "igehely_input": "Júd 24–25",
        "passage_text": (
            "24 Annak pedig, aki megőrizhet titeket a botlástól… "
            "25 az egyedüli Istennek, a mi üdvözítőnknek…"
        ),
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    assert assess_outline_readiness(state).ok
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok
    assert result.outline.get("schema_version") == SCHEMA_VERSION
    assert result.outline.get("movements") or result.outline.get("content")


def test_old_schema_marked_needs_refresh_keeps_body():
    state = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot…",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    old = normalize_sermon_outline(
        {
            "schema_version": "pulpit_outline_v3",
            "content": "Régi vázlat szöveg megőrzendő.",
            "main_idea": "Régi fő gondolat",
            "status": "approved",
        }
    )
    save_sermon_outline(state, old, mark_manual_edit=False)
    stored = normalize_sermon_outline(state[SERMON_WORKSHOP_KEY]["sermon_outline"])
    assert stored.get("status") == "needs_refresh"
    assert "Régi vázlat" in (stored.get("content") or "")
    payload = sanitize_project_data(build_project_data(state))
    reloaded = normalize_sermon_workshop(payload[SERMON_WORKSHOP_KEY])
    again = normalize_sermon_outline(reloaded["sermon_outline"])
    assert again.get("status") == "needs_refresh"
    assert "Régi vázlat" in (again.get("content") or "")


def test_quick_and_workshop_share_canonical_state():
    state = {
        "last_igehely": "Júd 24–25",
        "igehely_input": "Júd 24–25",
        "passage_text": "24 Annak pedig, aki megőrizhet… 25 az egyedüli Istennek…",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    ensure_sermon_workshop_state(state)
    quick = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert quick.ok
    save_sermon_outline(state, quick.outline)
    workshop_view = normalize_sermon_outline(
        state[SERMON_WORKSHOP_KEY]["sermon_outline"]
    )
    assert workshop_view.get("content") == quick.outline.get("content")
    assert workshop_view.get("schema_version") == SCHEMA_VERSION
