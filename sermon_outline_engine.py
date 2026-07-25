"""Egyetlen közös igehirdetési-vázlat motor.

Mindkét belépési pont (Gyorseszközök → Vázlat, Igehirdetési műhely →
Igehirdetési vázlat) ezt a modult hívja. Egy séma, egy validátor, egy
tömörítő javítás. Nem importál app.py / sermon_workshop_ui.py fájlból.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    empty_outline_movement,
    empty_sermon_outline,
    ensure_sermon_workshop_state,
    normalize_sermon_outline,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _is_api_error_text

GenerateFn = Callable[..., str]

logger = logging.getLogger("textus.outline")

TAB_OUTLINE = "Igehirdetési vázlat"
DEFAULT_TEMPERATURE = 0.2
SCHEMA_VERSION = "pulpit_outline_v3"
# JSON vázlat: tömör, szószéki gondolatvázlat; ne legyen prédikáció-méretű budget.
OUTLINE_MAX_OUTPUT_TOKENS = 900

# ---------------------------------------------------------------------------
# Strict length limits (HARD) — szószéki gondolatvázlat, nem rövid prédikáció
# ---------------------------------------------------------------------------

LIMITS = {
    "title_words": 8,
    "focus_words": 22,
    "intro_words": 25,
    "intro_sentences_max": 1,
    "point_title_words": 8,
    "subpoint_min_words": 4,
    "subpoint_max_words": 18,
    "application_words": 16,
    "conclusion_words": 25,
    "conclusion_sentences_max": 1,
    "scope_note_words": 25,
    "min_points": 2,
    "max_points": 4,
    "default_points": 3,
    "min_subpoints": 2,
    "max_subpoints": 2,
    "target_min_words": 160,
    "target_max_words": 240,
    "absolute_max_words": 280,
    "max_prose_block_words": 35,
    "refinement_max": 0,
}

# Prose-bait / legacy fields — soha ne kérjük és ne jelenjenek meg elsődlegesen.
FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "body",
        "content",
        "exegesis",
        "theological_expansion",
        "grace_connection",
        "listener_connection",
        "transition_logic",
        "full_introduction",
        "full_conclusion",
        "thesis",
        "outline_text",
    }
)

FORBIDDEN_HEADINGS: tuple[str, ...] = (
    "Mit rendez ez a pont",
    "Textuális horgony",
    "Teológiai horgony",
    "Textuális/teológiai horgony",
    "Átvezetési logika",
    "Diagnózis → evangéliumi fordulat → Isten válasza",
    "diagnózis → evangéliumi fordulat",
    "Exegetikai kibontás",
    "Kegyelmi kapcsolat",
    "Hallgatói kapcsolat",
    "Hallgatói felismerés",
    "Hallgatói alkalmazás",
    "Alkalmazási pontok",
    "Problémafelvetés",
    "Magyarázat",
    "Teológiai kibontás",
    "Tételmondat (scopus)",
)

FORBIDDEN_FILLERS: tuple[str, ...] = (
    "de vajon",
    "ez azonban",
    "itt felmerül a kérdés",
    "nem marad titokban",
)

COMPRESS_INSTRUCTION = (
    "FORMAI JAVÍTÁS. A kapott vázlat tartalmi és homiletikai ívét őrizd meg; "
    "ne tervezz új vázlatot és ne adj hozzá új exegetikai vagy teológiai állítást. "
    "Csak a jelzett séma-, mondat- és hosszhibákat javítsd. "
    "Töröld az ismétlést, metaszöveget és fölösleges magyarázatot. "
    "Korlátok: teljes látható vázlat 160–240 szó, abszolút maximum 280; "
    "cím legfeljebb 8 szó; fókusz pontosan egy mondat és legfeljebb 22 szó; "
    "bevezető irány pontosan egy mondat és legfeljebb 25 szó; "
    "2–4 pont; pontcím legfeljebb 8 szó; pontonként pontosan két alpont; "
    "minden alpont egy teljes mondat és legfeljebb 18 szó; "
    "alkalmazás legfeljebb egy mondat és 16 szó, vagy üres; "
    "megérkezés pontosan egy mondat és legfeljebb 25 szó; "
    "refinement_suggestions mindig üres lista. "
    "Ne használj thesis/body/content vagy más új mezőt. "
    "Kizárólag a teljes, javított JSON objektumot add vissza."
)

OUTLINE_SYSTEM_PROMPT = f"""\
SZEREP ÉS CÉL

Tapasztalt, biblikus, református szemléletű homiletikai szerkesztő vagy.
Feladatod egy tömör, szószéken kibontásra alkalmas GONDOLATVÁZLAT elkészítése.
A vázlat segíti a prédikátor önálló munkáját: nem kész prédikáció, nem rövidített
igehirdetés, nem egzegézis és nem a korábbi műhelyanyag mechanikus összefoglalása.

SÉMAVERZIÓ: {SCHEMA_VERSION}

BELSŐ MUNKAMENET

A következő mérlegelést csendben végezd el; gondolatmenetet és magyarázatot ne
írj a válaszba.

1. Először közvetlenül a bibliai textust vizsgáld meg: központi állítás,
   textushatár, belső szerkezet, feszültség, fordulat és megérkezés.
2. Egyetlen mondatban fogalmazd meg, mit tesz, ígér, leplez le vagy kíván
   Isten ebben a textusban.
3. Keresd meg a textus természetes homiletikai mozgását. Ez lehet logikai
   kibontás, ellentét, kérdés–válasz, probléma–fordulat–feloldás, narratív
   mozgás vagy más, a textusból következő szerkezet.
4. Ezután mérlegeld a lelkész döntéseit, az alkalmat, a hallgatói helyzetet,
   a vázlatkosarat és a műhely háttéranyagát.
5. Csak azokat az elemeket építsd be, amelyek pontosítják vagy erősítik a
   textus saját állítását és homiletikai mozgását.

FORRÁSKEZELÉS

A források sorrendje:

1. Bibliai textus és indokolt textushatár.
2. A felhasználó kifejezett fókusza, alkalma, hallgatói helyzete és jóváhagyott
   homiletikai döntései.
3. A vázlatkosárba tudatosan kiválasztott anyagok.
4. Egyéb exegetikai, teológiai, történeti és homiletikai műhelyanyag.
5. Korábbi vagy gépileg előállított vázlat csak akkor, ha a feladat kifejezetten
   annak javítása; új vázlat készítésekor nem tekinthető mintának.

A textus mindig elsőbbséget élvez. A felhasználói és műhelyanyag iránymutatás,
nem kötelező tartalomjegyzék. Ne próbálj minden rendelkezésre álló elemet
beépíteni. Hagyd el a textustól idegen, gyenge, ismétlődő, bizonytalan vagy
egymásnak ellentmondó elemeket.

Az üres vázlatkosár nem hiányállapot. Ilyenkor is készíts teljes értékű,
konkrét és professzionális vázlatot a textus alapján. Ne jelezd a vázlatban,
hogy kevés adat állt rendelkezésre, és ne töltsd ki a hiányt általános vallásos
közhelyekkel.

Ne állíts olyasmit a textusról, amit a szöveg vagy annak biztos kontextusa nem
támaszt alá. Bizonytalan történeti, nyelvi vagy teológiai részletet ne találj ki.
A textushatárt ne bővítsd ki hallgatólagosan: ha a teljes gondolati ívhez valóban
szükséges módosítás, azt kizárólag a `scope_note` mezőben jelezd.

HOMILETIKAI MINŐSÉG

- A fókuszmondat egyetlen világos, textusból következő állítás legyen.
- Ne ragaszkodj három ponthoz. A textus természetes szerkezete szerint válassz
  2–4 pontot.
- A pontok egymás után valódi gondolati előrehaladást mutassanak. Egyik pont
  se legyen a fókuszmondat vagy egy korábbi pont puszta átfogalmazása.
- A pontcímek egymás után olvasva is tegyék láthatóvá a prédikáció útját.
- Pontonként az első alpont rögzítse a textuális állítást vagy képet, a második
  mutassa meg annak teológiai vagy homiletikai jelentőségét.
- Az alkalmazás legyen konkrétan összekötve az adott ponttal és a hallgatói
  helyzettel. Kerüld az önmagában álló közhelyeket, például: „Fontos
  felismernünk”, „Bízzunk jobban Istenben”, „Ez kulcsfontosságú”.
- A bevezető iránya nevezzen meg konkrét emberi helyzetet, tapasztalatot,
  kérdést vagy feszültséget. Ne legyen metautasítás, például: „A bevezetés
  teremtsen feszültséget”.
- A megérkezés ne a vázlat pontjainak ismételt összefoglalása és ne
  metautasítás legyen. Fogalmazza meg, hová érkezik a textus a hallgatóval:
  Isten cselekvéséhez, ígéretéhez, kegyelméhez, vigasztalásához vagy a hit
  konkrét válaszához.
- A Krisztus- és kegyelemhorizont ott jelenjen meg, ahol azt a textus és a
  kánoni összefüggés természetesen indokolja. Ne illessz minden ponthoz
  mechanikus krisztológiai mondatot, de ne zárd le a vázlatot puszta
  moralizálással sem.
- Különleges alkalomnál a textus határozza meg az üzenetet. Életrajzi adatból,
  gyászesetből vagy hallgatói helyzetből ne vezess le a textuson túlmenő
  bizonyosságot.

MEZŐK TARTALMA

- `title`: rövid, megjegyezhető cím; ne puszta témamegjelölés legyen.
- `text_reference`: a megadott igehely.
- `scope_note`: csak valódi textushatár-probléma esetén; különben üres.
- `focus_sentence`: a teljes vázlatot összetartó egyetlen állítás.
- `introduction_direction`: konkrét, tartalmi nyitómondat; nem kész bevezető
  beszéd és nem szerkesztői utasítás.
- `points`: a textus természetes mozgásának 2–4 állomása.
- `verses`: csak az adott ponthoz ténylegesen tartozó vers vagy versszakasz.
- `subpoints`: két tömör, teljes mondat; ne bekezdés és ne prédikációs próza.
- `application`: egy konkrét hallgatói következmény vagy üres érték.
- `conclusion_direction`: konkrét tartalmi megérkezés; nem kész záróbeszéd és
  nem szerkesztői utasítás.
- `refinement_suggestions`: mindig üres lista.

HOSSZKORLÁTOK – KÖTELEZŐ

- `title`: legfeljebb 8 szó.
- `focus_sentence`: pontosan 1 mondat, legfeljebb 22 szó.
- `introduction_direction`: pontosan 1 mondat, legfeljebb 25 szó.
- `points`: 2–4, kizárólag a textus természetes szerkezete szerint.
- `point.title`: legfeljebb 8 szó.
- `point.subpoints`: pontosan 2; mindkettő pontosan 1 teljes mondat,
  egyenként legfeljebb 18 szó.
- `point.application`: legfeljebb 1 mondat és 16 szó, vagy üres.
- `conclusion_direction`: pontosan 1 mondat, legfeljebb 25 szó.
- `scope_note`: legfeljebb 25 szó, vagy üres.
- A teljes látható vázlat céltartománya 160–240 szó, abszolút maximuma 280 szó.
- `refinement_suggestions`: mindig `[]`.

TILOS

Tilos teljes prédikációt, kidolgozott bevezetést vagy záróbeszédet írni.
Tilos többbekezdéses prózát írni a pontok alatt.
Tilos a megadott sémán kívüli mezőt létrehozni, különösen:
`body`, `content`, `exegesis`, `theological_expansion`, `grace_connection`,
`listener_connection`, `transition_logic`, `full_introduction`,
`full_conclusion`, `thesis`, `outline_text`.
Tilos szerkesztői fejezetcímeket létrehozni, például:
„Problémafelvetés”, „Magyarázat”, „Teológiai kibontás”,
„Kegyelmi kapcsolat”, „Hallgatói alkalmazás”, „Átvezetési logika”.
Tilos metaszöveget, önértékelést, hiányjelzést vagy a választ magyarázó
megjegyzést írni.

KÖTELEZŐ KIMENET

Kizárólag egy érvényes JSON objektumot adj vissza, Markdown és minden további
magyarázat nélkül:

{{
  "title": "string",
  "text_reference": "string",
  "scope_note": "string or empty",
  "focus_sentence": "string",
  "introduction_direction": "string",
  "points": [
    {{
      "title": "string",
      "verses": "string",
      "subpoints": ["one full sentence", "one full sentence"],
      "application": "one sentence or empty"
    }}
  ],
  "conclusion_direction": "string",
  "refinement_suggestions": []
}}

VÉGSŐ ELLENŐRZÉS

Válaszadás előtt csendben ellenőrizd, hogy a vázlat a textusból indul-e,
önállóan is teljes-e, a pontok előrehaladnak-e, nincs-e ismétlés vagy
metaszöveg, és minden mező megfelel-e a sémának és a hosszkorlátoknak.
A válasz kizárólag a JSON objektum.\
"""

_JSON_SHAPE = """\
{
  "title": "Rövid cím",
  "text_reference": "Igehely",
  "scope_note": "",
  "focus_sentence": "Egyetlen fókuszmondat.",
  "introduction_direction": "Rövid bevezető irány.",
  "points": [
    {
      "title": "Pontcím",
      "verses": "v. x–y",
      "subpoints": [
        "Egy teljes mondat (≤18 szó).",
        "Második teljes mondat (≤18 szó)."
      ],
      "application": ""
    }
  ],
  "conclusion_direction": "Rövid megérkezés.",
  "refinement_suggestions": []
}
"""

# Gemini `responseSchema` — ugyanaz a szerkezet, amelyet a prompt és a
# helyi validátor is elvár. A szöveghosszokat a prompt + validátor kezeli.
OUTLINE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "text_reference": {"type": "STRING"},
        "scope_note": {"type": "STRING"},
        "focus_sentence": {"type": "STRING"},
        "introduction_direction": {"type": "STRING"},
        "points": {
            "type": "ARRAY",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "verses": {"type": "STRING"},
                    "subpoints": {
                        "type": "ARRAY",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {"type": "STRING"},
                    },
                    "application": {"type": "STRING"},
                },
                "required": ["title", "verses", "subpoints", "application"],
            },
        },
        "conclusion_direction": {"type": "STRING"},
        "refinement_suggestions": {
            "type": "ARRAY",
            "maxItems": 0,
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "title",
        "text_reference",
        "scope_note",
        "focus_sentence",
        "introduction_direction",
        "points",
        "conclusion_direction",
        "refinement_suggestions",
    ],
}


def _s(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_cmp(text: str) -> str:
    return " ".join(_s(text).casefold().split())


def word_count(text: Any) -> int:
    raw = _s(text)
    if not raw:
        return 0
    return len([w for w in re.split(r"\s+", raw) if w])


def sentence_count(text: Any) -> int:
    raw = _s(text)
    if not raw:
        return 0
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw) if p.strip()]
    return max(1, len(parts)) if raw else 0


def _looks_multi_paragraph(text: Any) -> bool:
    raw = _s(text)
    if not raw:
        return False
    if "\n\n" in raw:
        return True
    return sentence_count(raw) >= 3 and word_count(raw) > 40


def _has_forbidden_keys(raw: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    for key in FORBIDDEN_PAYLOAD_KEYS:
        if key not in raw:
            continue
        # points[].application ok; top-level content/body/thesis not
        if key == "application":
            continue
        val = raw.get(key)
        if val in (None, "", [], {}):
            continue
        if key == "content" and isinstance(val, str) and word_count(val) <= 5:
            continue
        found.append(key)
    for pt in raw.get("points") or []:
        if not isinstance(pt, dict):
            continue
        for key in FORBIDDEN_PAYLOAD_KEYS:
            if key in ("application",):
                continue
            if key in pt and _s(pt.get(key)):
                # thesis/body inside point is prose-bait
                if key in {
                    "body",
                    "content",
                    "exegesis",
                    "theological_expansion",
                    "grace_connection",
                    "listener_connection",
                    "transition_logic",
                    "thesis",
                }:
                    found.append(f"point.{key}")
    return list(dict.fromkeys(found))


def empty_structured_outline() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "",
        "text_reference": "",
        "scope_note": "",
        "focus_sentence": "",
        "introduction_direction": "",
        "points": [],
        "conclusion_direction": "",
        "refinement_suggestions": [],
    }


def normalize_structured_outline(raw: Any) -> dict[str, Any]:
    """AI / legacy payload → kanonikus struktúra (thesis nélkül)."""
    base = empty_structured_outline()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    out["title"] = _s(raw.get("title") or raw.get("sermon_title"))
    out["text_reference"] = _s(
        raw.get("text_reference") or raw.get("passage_reference")
    )
    out["scope_note"] = _s(raw.get("scope_note") or raw.get("text_boundary_note"))
    out["focus_sentence"] = _s(raw.get("focus_sentence") or raw.get("main_idea"))
    intro = raw.get("introduction") if isinstance(raw.get("introduction"), dict) else {}
    out["introduction_direction"] = _s(
        raw.get("introduction_direction")
        or intro.get("development")
        or raw.get("opening_direction")
    )
    conc = raw.get("conclusion") if isinstance(raw.get("conclusion"), dict) else {}
    closing = raw.get("closing") if isinstance(raw.get("closing"), dict) else {}
    out["conclusion_direction"] = _s(
        raw.get("conclusion_direction")
        or conc.get("development")
        or closing.get("final_insight")
    )
    tips = raw.get("refinement_suggestions") or raw.get("editorial_tips") or []
    cleaned_tips: list[str] = []
    for t in tips if isinstance(tips, list) else []:
        tip = _s(t)
        if not tip:
            continue
        low = tip.casefold()
        if any(
            w in low
            for w in ("hiányzik", "kötelező", "nem töltött", "üres mező", "műhelymez")
        ):
            continue
        cleaned_tips.append(tip)
    out["refinement_suggestions"] = cleaned_tips[: LIMITS["refinement_max"]]

    points: list[dict[str, Any]] = []
    raw_points = raw.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        raw_points = raw.get("movements") if isinstance(raw.get("movements"), list) else []
    for i, item in enumerate(raw_points[: LIMITS["max_points"]], start=1):
        if not isinstance(item, dict):
            continue
        title = re.sub(r"^\s*\d+[.)]\s*", "", _s(item.get("title"))).strip()
        verses = _s(
            item.get("verses")
            or item.get("textual_anchor")
            or item.get("textual_basis")
        )
        # Legacy thesis/core_content → fold into subpoints (never keep as thesis)
        legacy_thesis = _s(
            item.get("thesis") or item.get("core_content") or item.get("body")
        )
        subs_raw = item.get("subpoints")
        if not isinstance(subs_raw, list) or not subs_raw:
            subs_raw = (
                item.get("development")
                if isinstance(item.get("development"), list)
                else []
            )
        subpoints = [_s(x) for x in subs_raw if _s(x)]
        if legacy_thesis and all(
            _normalize_cmp(legacy_thesis) != _normalize_cmp(sp) for sp in subpoints
        ):
            subpoints = [legacy_thesis] + subpoints
        subpoints = subpoints[: LIMITS["max_subpoints"]]
        application = _s(item.get("application"))
        if not application:
            application = _s(item.get("listener_insight")) or _s(
                item.get("listener_discovery")
            )
        if not application:
            apps = item.get("applications") if isinstance(item.get("applications"), list) else []
            application = _s(apps[0]) if apps else ""
        if not title and not subpoints:
            continue
        points.append(
            {
                "title": title or f"{i}. pont",
                "verses": verses,
                "subpoints": subpoints,
                "application": application,
            }
        )
    out["points"] = points
    out["schema_version"] = SCHEMA_VERSION
    return out


def validate_structured_outline(payload: Any) -> list[str]:
    """Hard validation — bármely találat → érvénytelen (compress / reject)."""
    data = normalize_structured_outline(payload)
    issues: list[str] = []

    if isinstance(payload, dict):
        forbidden = _has_forbidden_keys(payload)
        if forbidden:
            issues.append("forbidden_prose_fields")
        for key in (
            "title",
            "text_reference",
            "scope_note",
            "focus_sentence",
            "introduction_direction",
            "conclusion_direction",
        ):
            if _looks_multi_paragraph(payload.get(key)):
                issues.append("multi_paragraph_field")
                break
        raw_tips = payload.get("refinement_suggestions")
        if raw_tips not in (None, [], ()):
            issues.append("refinement_suggestions_not_empty")
        raw_points = payload.get("points")
        if isinstance(raw_points, list):
            if not LIMITS["min_points"] <= len(raw_points) <= LIMITS["max_points"]:
                issues.append("invalid_point_count")
            for raw_point in raw_points:
                if not isinstance(raw_point, dict):
                    continue
                if _looks_multi_paragraph(raw_point.get("title")) or _looks_multi_paragraph(
                    raw_point.get("verses")
                ):
                    issues.append("multi_paragraph_field")
                    break
                raw_subpoints = raw_point.get("subpoints")
                if isinstance(raw_subpoints, list) and len(raw_subpoints) != 2:
                    issues.append("invalid_subpoint_count")
                if _looks_multi_paragraph(raw_point.get("application")):
                    issues.append("multi_paragraph_field")
                    break

    if not data["focus_sentence"]:
        issues.append("missing_focus")
    elif word_count(data["focus_sentence"]) > LIMITS["focus_words"]:
        issues.append("focus_too_long")
    elif sentence_count(data["focus_sentence"]) != 1:
        issues.append("focus_not_one_sentence")

    if data["title"] and word_count(data["title"]) > LIMITS["title_words"]:
        issues.append("title_too_long")

    if data["scope_note"] and word_count(data["scope_note"]) > LIMITS["scope_note_words"]:
        issues.append("scope_note_too_long")

    intro = data["introduction_direction"]
    if not intro:
        issues.append("missing_intro")
    else:
        if word_count(intro) > LIMITS["intro_words"]:
            issues.append("intro_too_long")
        if sentence_count(intro) > LIMITS["intro_sentences_max"]:
            issues.append("intro_too_many_sentences")
        if _looks_multi_paragraph(intro):
            issues.append("intro_multi_paragraph")

    points = data["points"]
    n = len(points)
    if n < LIMITS["min_points"]:
        issues.append("too_few_points")
    if n > LIMITS["max_points"]:
        issues.append("too_many_points")

    titles_seen: set[str] = set()
    for pt in points:
        title = _s(pt.get("title"))
        subs = [_s(x) for x in (pt.get("subpoints") or []) if _s(x)]
        app = _s(pt.get("application"))
        tnorm = _normalize_cmp(title)
        if not title:
            issues.append("empty_point_title")
        elif word_count(title) > LIMITS["point_title_words"]:
            issues.append("point_title_too_long")
        if tnorm in titles_seen:
            issues.append("duplicate_points")
        titles_seen.add(tnorm)
        # Near-duplicate titles
        for prev in titles_seen - {tnorm}:
            if prev and tnorm and (prev in tnorm or tnorm in prev):
                if abs(len(prev) - len(tnorm)) <= 8:
                    issues.append("duplicate_points")
        if len(subs) < LIMITS["min_subpoints"]:
            issues.append("too_few_subpoints")
        if len(subs) > LIMITS["max_subpoints"]:
            issues.append("too_many_subpoints")
        if len(subs) != 2:
            issues.append("invalid_subpoint_count")
        for sp in subs:
            wc = word_count(sp)
            if wc < LIMITS["subpoint_min_words"]:
                issues.append("stub_subpoint")
            if wc > LIMITS["subpoint_max_words"]:
                issues.append("subpoint_length")
            if sentence_count(sp) != 1:
                issues.append("subpoint_not_one_sentence")
            if _looks_multi_paragraph(sp):
                issues.append("multi_paragraph_point")
            if wc > LIMITS["max_prose_block_words"]:
                issues.append("prose_block_too_long")
        if app:
            if word_count(app) > LIMITS["application_words"]:
                issues.append("application_too_long")
            if sentence_count(app) > 1:
                issues.append("application_too_many_sentences")
            if _looks_multi_paragraph(app):
                issues.append("multi_paragraph_point")

    conc = data["conclusion_direction"]
    if not conc:
        issues.append("missing_conclusion")
    else:
        if word_count(conc) > LIMITS["conclusion_words"]:
            issues.append("conclusion_too_long")
        if sentence_count(conc) > LIMITS["conclusion_sentences_max"]:
            issues.append("conclusion_too_many_sentences")
        if _looks_multi_paragraph(conc):
            issues.append("conclusion_multi_paragraph")

    rendered = render_structured_outline(data)
    total = word_count(rendered)
    if total > LIMITS["absolute_max_words"]:
        issues.append("over_absolute_max")
    if total and total < 60:
        issues.append("too_thin")

    # Contiguous prose block >50 words (paragraph without bullets)
    for block in rendered.split("\n\n"):
        plain = re.sub(r"^[-•*]\s+", "", block.strip(), flags=re.M)
        plain = re.sub(r"\*\*?|[*_]", "", plain)
        if word_count(plain) > LIMITS["max_prose_block_words"] and not plain.startswith(
            ("1.", "2.", "3.", "4.")
        ):
            # Allow titled sections only if short; long blocks fail
            if not plain.startswith("**") and "\n- " not in block and not block.strip().startswith("-"):
                if not any(
                    block.strip().startswith(f"**{lab}")
                    for lab in (
                        "Cím",
                        "Textus",
                        "Fókuszmondat",
                        "Bevezetés",
                        "Megérkezés",
                        "Megjegyzés",
                    )
                ):
                    issues.append("prose_block_too_long")

    blob = rendered.casefold()
    for heading in FORBIDDEN_HEADINGS:
        if heading.casefold() in blob:
            issues.append("forbidden_heading")
            break
    for filler in FORBIDDEN_FILLERS:
        if filler in blob:
            issues.append("forbidden_filler")
            break

    # Raw Markdown chapter heuristics
    if re.search(r"(?m)^#{1,3}\s+\S", rendered) or rendered.count("##") >= 2:
        issues.append("raw_markdown_chapters")

    para_count = len([p for p in rendered.split("\n\n") if len(p) > 80])
    if para_count >= 8 and total > LIMITS["target_max_words"]:
        issues.append("full_sermon_like")

    return list(dict.fromkeys(issues))


def render_structured_outline(payload: Any) -> str:
    """Felhasználói megjelenés — CSAK strukturált mezők, legacy próza nélkül."""
    data = normalize_structured_outline(payload)
    blocks: list[str] = []

    def _sec(label: str, body: str) -> None:
        text = _s(body)
        if text:
            blocks.append(f"**{label}**\n\n{text}")

    _sec("Cím", data["title"])
    _sec("Textus", data["text_reference"])
    if data["scope_note"]:
        _sec("Megjegyzés a textushatárról", data["scope_note"])
    _sec("Fókuszmondat", data["focus_sentence"])
    _sec("Bevezetés", data["introduction_direction"])

    for idx, pt in enumerate(data["points"], start=1):
        title = re.sub(r"^\s*\d+[.)]\s*", "", _s(pt.get("title"))).strip()
        if not title:
            continue
        parts: list[str] = []
        verses = _s(pt.get("verses"))
        if verses:
            parts.append(f"*{verses}*")
        for sp in pt.get("subpoints") or []:
            cleaned = re.sub(r"^[-•*]\s+", "", _s(sp)).strip()
            # Never render multi-paragraph under a point
            if "\n\n" in cleaned:
                cleaned = cleaned.split("\n\n")[0].strip()
            if cleaned:
                parts.append(f"- {cleaned}")
        app = _s(pt.get("application"))
        if app:
            parts.append(f"*{app}*")
        if not parts:
            continue
        blocks.append(f"**{idx}. {title}**\n\n" + "\n".join(parts))

    _sec("Megérkezés", data["conclusion_direction"])
    text = "\n\n".join(blocks).strip()
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    return text + ("\n" if text else "")


def structured_to_sermon_outline(
    payload: Any,
    *,
    seed: Mapping[str, Any] | None = None,
    source: str = "",
    context_hash: str = "",
) -> dict[str, Any]:
    """Struktúra → tartós sermon_outline."""
    data = normalize_structured_outline(payload)
    outline = normalize_sermon_outline(seed) if seed else empty_sermon_outline()
    stamp = _now()

    # Preserve prior long freeform as migration data — never as primary content
    prior_content = _s(outline.get("content"))
    prior_legacy = _s(outline.get("legacy_outline_text"))
    structured_preview = render_structured_outline(data)
    if prior_content and word_count(prior_content) > LIMITS["absolute_max_words"]:
        if _normalize_cmp(prior_content) != _normalize_cmp(structured_preview):
            prior_legacy = prior_legacy or prior_content
    if prior_legacy:
        outline["legacy_outline_text"] = prior_legacy

    outline["sermon_title"] = data["title"]
    outline["passage_reference"] = data["text_reference"] or _s(
        outline.get("passage_reference")
    )
    outline["text_boundary_note"] = data["scope_note"]
    outline["main_idea"] = data["focus_sentence"]
    outline["opening_direction"] = data["introduction_direction"]
    outline["introduction"] = {
        "development": data["introduction_direction"],
        "transition": "",
    }
    outline["conclusion"] = {
        "development": data["conclusion_direction"],
        "final_sentence": "",
    }
    closing = dict(outline.get("closing") or {})
    closing["final_insight"] = data["conclusion_direction"]
    outline["closing"] = closing
    outline["editorial_tips"] = list(data["refinement_suggestions"][:2])
    try:
        from sermon_workshop_outline_synth_ai import suggest_text_boundary_hint

        if not data["scope_note"]:
            hint = suggest_text_boundary_hint(
                data["text_reference"] or outline.get("passage_reference"),
                "",
            )
            if hint.get("text_boundary_note"):
                data["scope_note"] = hint["text_boundary_note"]
                outline["text_boundary_note"] = hint["text_boundary_note"]
                outline["suggested_text_boundary"] = hint.get(
                    "suggested_text_boundary", ""
                )
        elif "Júd 17–21" in data["scope_note"] or "Júd 17-21" in data["scope_note"]:
            outline["suggested_text_boundary"] = "Júd 17–21"
    except Exception:  # noqa: BLE001
        pass
    outline["text_boundary_note"] = data["scope_note"] or outline.get(
        "text_boundary_note", ""
    )

    movements: list[dict[str, Any]] = []
    for i, pt in enumerate(data["points"], start=1):
        item = empty_outline_movement()
        subs = [_s(x) for x in (pt.get("subpoints") or []) if _s(x)]
        app = _s(pt.get("application"))
        verses = _s(pt.get("verses"))
        item.update(
            {
                "id": f"pt_{i}",
                "title": _s(pt.get("title")),
                "textual_basis": verses,
                "textual_anchor": verses,
                "core_content": "",
                "development": subs[: LIMITS["max_subpoints"]],
                "listener_discovery": app,
                "applications": [app] if app else [],
                "transition": "",
            }
        )
        movements.append(item)
    outline["movements"] = movements
    outline["structured"] = data
    outline["content"] = structured_preview
    outline["schema_version"] = SCHEMA_VERSION
    outline["source"] = source if source in ("quick", "workshop") else _s(
        outline.get("source")
    )
    outline["context_hash"] = context_hash or _s(outline.get("context_hash"))
    if not outline.get("generated_at"):
        outline["generated_at"] = stamp
    outline["updated_at"] = stamp
    if _s(outline.get("status")) not in ("draft", "approved", "needs_refresh", "empty"):
        outline["status"] = "draft"
    outline["needs_rebuild"] = False
    outline["provisional_sections"] = []
    return normalize_sermon_outline(outline)


def sermon_outline_to_structured(outline: Any) -> dict[str, Any]:
    safe = normalize_sermon_outline(outline)
    stored = safe.get("structured")
    if isinstance(stored, dict) and (
        stored.get("points") or stored.get("focus_sentence")
    ):
        return normalize_structured_outline(stored)
    return normalize_structured_outline(safe)


def compute_context_hash(bundle: Mapping[str, Any]) -> str:
    """Forrásanyag ujjlenyomat — változás → needs_refresh, nem auto-duplikátum."""
    keys = (
        "passage_reference",
        "passage_text",
        "text_main_idea",
        "sermon_main_idea",
        "exegesis",
        "original_text",
        "theology",
        "history",
        "approved_insights",
        "approved_sermon_decisions",
        "human_condition",
        "listener_tension",
        "christ_centered_arc",
        "sermon_path",
        "sermon_movements",
        "closing",
        "occasion",
        "user_focus",
    )
    payload = {k: bundle.get(k) for k in keys if bundle.get(k) not in (None, "", [], {})}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def outline_needs_refresh(
    outline: Any,
    bundle: Mapping[str, Any],
) -> bool:
    safe = normalize_sermon_outline(outline)
    stored = _s(safe.get("context_hash") or safe.get("source_fingerprint"))
    if not stored:
        return False
    current = compute_context_hash(bundle)
    return bool(current and stored != current)


REFRESH_NOTICE = (
    "A műhelyanyag a vázlat elkészítése óta megváltozott. A vázlat frissíthető."
)

INVALID_OUTLINE_MESSAGE = (
    "A vázlatgenerálás nem adott szószéken használható, tömör gondolatvázlatot "
    f"(max. {LIMITS['absolute_max_words']} szó). "
    "Próbáld újra — a hosszú prédikációs szöveg nem kerül mentésre."
)


@dataclass
class OutlineGenerationResult:
    outline: dict[str, Any] = field(default_factory=empty_sermon_outline)
    ok: bool = True
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
    source: str = ""
    overwritten_manual_edit: bool = False
    compressed: bool = False
    schema_version: str = SCHEMA_VERSION
    raw_word_count: int = 0
    rendered_word_count: int = 0

    def to_assembly_dict(self) -> dict[str, Any]:
        return {
            "outline": dict(self.outline),
            "ok": self.ok,
            "error_message": self.error_message,
            "warnings": list(self.warnings),
            "overwritten_manual_edit": self.overwritten_manual_edit,
        }


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    system_bundle: str = OUTLINE_SYSTEM_PROMPT,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    prev_temp = None
    touched = False
    try:
        import streamlit as st

        prev_temp = st.session_state.get("temperature")
        st.session_state["temperature"] = float(temperature)
        touched = True
    except Exception:  # noqa: BLE001
        touched = False
    try:
        try:
            return generate_fn(
                prompt,
                enable_google_search=False,
                tab_label=TAB_OUTLINE,
                use_cache=False,
                system_bundle=system_bundle,
                include_brevity_directive=False,
                max_output_tokens=OUTLINE_MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
                response_schema=OUTLINE_RESPONSE_SCHEMA,
            )
        except TypeError:
            # Teszt / legacy generate_fn signature
            return generate_fn(
                prompt,
                enable_google_search=False,
                tab_label=TAB_OUTLINE,
                use_cache=False,
                system_bundle=system_bundle,
                include_brevity_directive=False,
                max_output_tokens=OUTLINE_MAX_OUTPUT_TOKENS,
            )
    finally:
        if touched:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:  # noqa: BLE001
                pass


def _heuristic_structured_from_bundle(
    bundle: Mapping[str, Any],
    *,
    seed_outline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Offline / teszt: tömör struktúra a rendelkezésre álló anyagból."""
    from sermon_workshop_outline_ai import (
        _prefer_main_idea,
        _truncate,
        _usable_text,
    )

    data = empty_structured_outline()
    data["text_reference"] = _s(bundle.get("passage_reference"))
    data["title"] = _s(bundle.get("project_title")) or data["text_reference"] or "Vázlat"
    if word_count(data["title"]) > LIMITS["title_words"]:
        data["title"] = " ".join(data["title"].split()[: LIMITS["title_words"]])

    focus = _prefer_main_idea(bundle)
    if not focus and seed_outline:
        focus = _s(seed_outline.get("main_idea"))
    data["focus_sentence"] = _usable_text(focus) or "A textus Isten megtartó szavát hirdeti."
    if word_count(data["focus_sentence"]) > LIMITS["focus_words"]:
        data["focus_sentence"] = " ".join(
            data["focus_sentence"].split()[: LIMITS["focus_words"]]
        )

    lt = bundle.get("listener_tension") if isinstance(bundle.get("listener_tension"), dict) else {}
    path = bundle.get("sermon_path") if isinstance(bundle.get("sermon_path"), dict) else {}
    intro = (
        _usable_text(path.get("starting_point"))
        or _usable_text(lt.get("listener_question"))
        or "A hallgató a textus feszültségéből indul a fő állítás felé."
    )
    data["introduction_direction"] = _truncate(intro, 200)
    if word_count(data["introduction_direction"]) > LIMITS["intro_words"]:
        data["introduction_direction"] = " ".join(
            data["introduction_direction"].split()[: LIMITS["intro_words"]]
        )

    points: list[dict[str, Any]] = []
    movements = bundle.get("sermon_movements") if isinstance(bundle.get("sermon_movements"), list) else []
    insights = [
        _usable_text(x)
        for x in (bundle.get("approved_insights") or [])
        if _usable_text(x)
    ]
    decisions = [
        _usable_text(x)
        for x in (bundle.get("approved_sermon_decisions") or [])
        if _usable_text(x)
    ]
    exe = _usable_text(bundle.get("exegesis"))
    original = _usable_text(bundle.get("original_text"))

    def _one_sentence(text: str, *, fallback: str, max_w: int | None = None) -> str:
        max_w = max_w or LIMITS["subpoint_max_words"]
        target_min = 12
        cleaned = _usable_text(text) or fallback
        words = cleaned.split()
        if len(words) < target_min:
            pad = (fallback + " " + data["focus_sentence"]).split()
            for w in pad:
                if len(words) >= target_min:
                    break
                words.append(w)
            while len(words) < target_min:
                words.append("szava")
        words = words[:max_w]
        sent = " ".join(words).rstrip(".,;:")
        if not sent.endswith((".", "!", "?")):
            sent += "."
        return sent

    if movements:
        for i, mv in enumerate(movements[: LIMITS["max_points"]], start=1):
            if not isinstance(mv, dict):
                continue
            core = _usable_text(mv.get("core_content")) or _usable_text(
                mv.get("listener_discovery")
            )
            title = _usable_text(mv.get("title")) or f"Pont {i}"
            if word_count(title) > LIMITS["point_title_words"]:
                title = " ".join(title.split()[: LIMITS["point_title_words"]])
            basis = _usable_text(mv.get("textual_basis"))
            sp1 = _one_sentence(
                core
                or exe
                or (insights[0] if insights else data["focus_sentence"]),
                fallback="A textus saját szavai rendezik ezt a gondolatot.",
            )
            sp2 = _one_sentence(
                _usable_text(mv.get("listener_discovery"))
                or (insights[1] if len(insights) > 1 else "")
                or original
                or "Isten cselekvése hív választ, nem emberi erőfeszítés.",
                fallback="Isten cselekvése hív választ, nem emberi erőfeszítés.",
            )
            points.append(
                {
                    "title": title,
                    "verses": basis or data["text_reference"],
                    "subpoints": [sp1, sp2],
                    "application": "",
                }
            )
    else:
        seeds = insights or decisions or [
            exe[:120] if exe else "",
            original[:120] if original else "",
            data["focus_sentence"],
        ]
        seeds = [s for s in seeds if s] or [data["focus_sentence"]]
        while len(seeds) < 3:
            seeds.append(data["focus_sentence"])
        titles = ("A textus megnyitása", "A központi állítás", "A kegyelmi megérkezés")
        for i in range(3):
            body = seeds[i % len(seeds)]
            points.append(
                {
                    "title": titles[i],
                    "verses": data["text_reference"],
                    "subpoints": [
                        _one_sentence(
                            body,
                            fallback="A textus saját mozgása bontja ki ezt a pontot.",
                        ),
                        _one_sentence(
                            exe or original or data["focus_sentence"],
                            fallback="A hallgató Isten cselekvése felől látja a választ.",
                        ),
                    ],
                    "application": "",
                }
            )

    data["points"] = points[: LIMITS["max_points"]]
    closing = bundle.get("closing") if isinstance(bundle.get("closing"), dict) else {}
    arc = (
        bundle.get("christ_centered_arc")
        if isinstance(bundle.get("christ_centered_arc"), dict)
        else {}
    )
    conc = (
        _usable_text(closing.get("final_discovery"))
        or _usable_text(arc.get("grace_enabled_response"))
        or "A hallgató Isten megtartó szeretetében állhat meg."
    )
    data["conclusion_direction"] = _truncate(conc, 220)
    if word_count(data["conclusion_direction"]) > LIMITS["conclusion_words"]:
        data["conclusion_direction"] = " ".join(
            data["conclusion_direction"].split()[: LIMITS["conclusion_words"]]
        )
    data["refinement_suggestions"] = []
    return normalize_structured_outline(data)


def _ai_generate_structured(
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn,
    seed_outline: Mapping[str, Any] | None = None,
    mode: str = "standard",
) -> tuple[dict[str, Any] | None, list[str], int]:
    """Returns (structured|None, warnings, raw_rendered_word_count)."""
    warnings: list[str] = []
    ctx_without_basket_and_seed = {
        k: v
        for k, v in bundle.items()
        if not str(k).startswith("_")
        and k not in {"outline_basket", "sermon_outline", "outline_manual_notes"}
    }
    source_keys = ctx_without_basket_and_seed.get("source_keys")
    if isinstance(source_keys, list):
        ctx_without_basket_and_seed["source_keys"] = [
            key
            for key in source_keys
            if key not in {"outline_basket", "outline_manual_notes"}
        ]
    outline_basket = bundle.get("outline_basket") or []
    task_mode_note = (
        "ÚJ GYORSVÁZLAT: készíts önálló vázlatot a textusból; "
        "a rendelkezésre álló műhelyanyagot csak szelektív háttérként használd."
        if mode == "quick"
        else
        "ÚJ MŰHELYVÁZLAT: készíts önálló vázlatot a textusból; "
        "a lelkész jóváhagyott döntéseit mérlegeld, de ne másold mechanikusan."
    )
    try:
        from sermon_workshop_outline_synth_ai import (
            _is_partial_workshop_bundle,
            outline_length_profile,
            resolve_outline_occasion,
        )

        profile = outline_length_profile(
            resolve_outline_occasion(bundle),
            partial=_is_partial_workshop_bundle(bundle),
        )
        occasion_block = (
            f"ALKALOM: {profile['occasion']}\n"
            f"SÉMAVERZIÓ: {SCHEMA_VERSION}\n"
            f"CÉLHOSSZ: ~{profile['target_range']} szó "
            f"(abszolút max {LIMITS['absolute_max_words']}).\n"
            f"{profile['guidance']}\n"
        )
    except Exception:  # noqa: BLE001
        occasion_block = (
            f"SÉMAVERZIÓ: {SCHEMA_VERSION}\n"
            f"CÉLHOSSZ: 160–240 szó (abszolút max {LIMITS['absolute_max_words']}).\n"
        )
    prompt = (
        f"{task_mode_note}\n"
        f"{occasion_block}"
        "A feladat új vázlat készítése, nem egy korábbi vázlat javítása vagy "
        "átszövegezése.\n"
        "Először a textus központi állítását és természetes homiletikai mozgását "
        "állapítsd meg. Csak ezután mérlegeld a többi anyagot.\n"
        "Üres vázlatkosár esetén is készíts teljes értékű, konkrét vázlatot.\n"
        "Ne ragaszkodj három ponthoz; a textus szerint válassz 2–4 pontot.\n"
        "Pontonként pontosan két, egyenként legfeljebb 18 szavas alpontot adj.\n"
        "A bevezető és a megérkezés tartalmi mondat legyen, ne szerkesztői "
        "utasítás.\n\n"
        f"FORRÁSCSOMAG:\n{json.dumps(ctx_without_basket_and_seed, ensure_ascii=False)}\n\n"
        "A forráscsomag exegetikai, teológiai és homiletikai elemei háttéranyagok; "
        "nem kell mindegyiket felhasználni.\n\n"
        f"VÁZLATKOSÁR – OPCIONÁLIS, SZELEKTÁLVA HASZNÁLHATÓ:\n"
        f"{json.dumps(outline_basket or [], ensure_ascii=False)}\n\n"
        f"KIMENETI SÉMA:\n{_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.3)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Vázlat AI-hívás sikertelen: {exc}")
        return None, warnings, 0
    if _is_api_error_text(raw or ""):
        warnings.append("A vázlat AI-válasz hibát jelzett.")
        return None, warnings, 0
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        # Raw markdown / prose instead of JSON
        warnings.append("Érvénytelen JSON vázlatválasz.")
        logger.info(
            "outline_invalid_json schema=%s raw_words=%s",
            SCHEMA_VERSION,
            word_count(raw or ""),
        )
        return None, warnings, word_count(raw or "")
    structured = normalize_structured_outline(obj)
    raw_wc = word_count(render_structured_outline(structured))
    logger.info(
        "outline_ai_raw schema=%s rendered_words=%s forbidden=%s",
        SCHEMA_VERSION,
        raw_wc,
        _has_forbidden_keys(obj),
    )
    return structured, warnings, raw_wc


def _compress_structured(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    repair_context = {
        "passage_reference": bundle.get("passage_reference", ""),
        "passage_text": bundle.get("passage_text", ""),
        "bible_translation": bundle.get("bible_translation", ""),
    }
    try:
        from sermon_workshop_outline_synth_ai import (
            _is_partial_workshop_bundle,
            outline_length_profile,
            resolve_outline_occasion,
        )

        profile = outline_length_profile(
            resolve_outline_occasion(bundle),
            partial=_is_partial_workshop_bundle(bundle),
        )
        occasion_line = (
            f"ALKALOM: {profile['occasion']}. "
            f"CÉL: ~{profile['target_range']} szó "
            f"(max {LIMITS['absolute_max_words']}).\n"
        )
        if profile.get("partial"):
            occasion_line += "Részleges műhelyanyag: tartsd a teljes szerkezetet, rövidebben.\n"
    except Exception:  # noqa: BLE001
        occasion_line = ""
    # Strip prose-bait keys before sending to compress
    slim = normalize_structured_outline(payload)
    prompt = (
        f"{COMPRESS_INSTRUCTION}\n"
        f"{occasion_line}"
        f"SÉMAVERZIÓ: {SCHEMA_VERSION}\n"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n"
        "Add vissza a teljes vázlatot a szigorú JSON sémában "
        "(thesis/body/content nélkül).\n\n"
        f"FORRÁS (csak támasz):\n{json.dumps(repair_context, ensure_ascii=False)}\n\n"
        f"JAVÍTANDÓ VÁZLAT:\n{json.dumps(slim, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Tömörítő javítás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A tömörítő javítás API-hibát jelzett.")
        return None, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen tömörítő válasz.")
        return None, warnings
    logger.info(
        "outline_compress schema=%s rendered_words=%s",
        SCHEMA_VERSION,
        word_count(render_structured_outline(normalize_structured_outline(obj))),
    )
    return normalize_structured_outline(obj), warnings


def _programmatic_trim(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic length enforcement before/after AI."""
    data = normalize_structured_outline(payload)

    def _clip_words(text: str, max_w: int) -> str:
        words = _s(text).split()
        if len(words) <= max_w:
            return _s(text)
        clipped = " ".join(words[:max_w]).rstrip(".,;:")
        if clipped and not clipped.endswith((".", "!", "?")):
            clipped += "."
        return clipped

    data["title"] = _clip_words(data["title"], LIMITS["title_words"])
    data["focus_sentence"] = _clip_words(data["focus_sentence"], LIMITS["focus_words"])
    data["introduction_direction"] = _clip_words(
        data["introduction_direction"], LIMITS["intro_words"]
    )
    data["conclusion_direction"] = _clip_words(
        data["conclusion_direction"], LIMITS["conclusion_words"]
    )
    data["scope_note"] = _clip_words(data["scope_note"], LIMITS["scope_note_words"])
    trimmed_points: list[dict[str, Any]] = []
    for pt in data["points"][: LIMITS["max_points"]]:
        subs = []
        for sp in (pt.get("subpoints") or [])[: LIMITS["max_subpoints"]]:
            words = _s(sp).split()
            if len(words) > LIMITS["subpoint_max_words"]:
                sp = " ".join(words[: LIMITS["subpoint_max_words"]]).rstrip(".,;:") + "."
            else:
                sp = _s(sp)
            if sp:
                first = re.split(r"(?<=[.!?])\s+", sp)[0].strip()
                # Drop multi-paragraph residue
                if "\n\n" in first:
                    first = first.split("\n\n")[0].strip()
                subs.append(first if first else sp)
        trimmed_points.append(
            {
                "title": _clip_words(_s(pt.get("title")), LIMITS["point_title_words"]),
                "verses": _s(pt.get("verses")),
                "subpoints": subs,
                "application": _clip_words(
                    _s(pt.get("application")), LIMITS["application_words"]
                ),
            }
        )
    data["points"] = trimmed_points
    data["refinement_suggestions"] = list(data["refinement_suggestions"][:2])

    # Absolute total: drop applications, then 3rd subpoints, then clip harder
    def _over() -> bool:
        return word_count(render_structured_outline(data)) > LIMITS["absolute_max_words"]

    if _over():
        for pt in data["points"]:
            pt["application"] = ""
    if _over():
        for pt in data["points"]:
            if len(pt["subpoints"]) > 2:
                pt["subpoints"] = pt["subpoints"][:2]
    if _over():
        data["introduction_direction"] = _clip_words(
            data["introduction_direction"], 25
        )
        data["conclusion_direction"] = _clip_words(data["conclusion_direction"], 30)
        data["focus_sentence"] = _clip_words(data["focus_sentence"], 24)
    if _over() and len(data["points"]) > 3:
        data["points"] = data["points"][:3]
    return normalize_structured_outline(data)


def generate_sermon_outline(
    session_state: MutableMapping[str, Any] | Mapping[str, Any],
    *,
    mode: str = "standard",
    generate_fn: GenerateFn | None = None,
    force_overwrite: bool = False,
) -> OutlineGenerationResult:
    """Egyetlen vázlatgeneráló belépő.

    mode: \"quick\" | \"workshop\" | \"standard\" — csak kontextusdúsítás / forrásjelölés,
    NEM külön séma.
    """
    from sermon_workshop_outline_ai import (
        EMPTY_PROJECT_MESSAGE,
        assess_outline_readiness,
        build_outline_from_workshop,
        collect_available_sermon_material,
        outline_has_content,
    )

    source_tag = "quick" if mode == "quick" else "workshop" if mode == "workshop" else ""
    if mode == "standard":
        source_tag = "workshop"

    if not isinstance(session_state, MutableMapping):
        session: MutableMapping[str, Any] = dict(session_state)
    else:
        session = session_state

    ensure_sermon_workshop_state(session)
    sw = session[SERMON_WORKSHOP_KEY]
    readiness = assess_outline_readiness(session, sermon_workshop=sw)
    if not readiness.ok:
        return OutlineGenerationResult(
            outline=normalize_sermon_outline(sw.get("sermon_outline")),
            ok=False,
            error_message=readiness.message or EMPTY_PROJECT_MESSAGE,
            source=source_tag,
        )

    existing = normalize_sermon_outline(sw.get("sermon_outline"))
    retained_outline_notice = (
        " A korábbi mentett vázlat változatlanul maradt, és továbbra is az látható."
        if outline_has_content(existing)
        else ""
    )
    manually_edited = bool(
        existing.get("manually_edited")
        or _s(sw.get("sermon_outline_status")) == "approved"
    )
    if outline_has_content(existing) and manually_edited and not force_overwrite:
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=(
                "A vázlat kézzel szerkesztve van. "
                "Frissítéshez erősítsd meg a felülírást."
            ),
            source=_s(existing.get("source")) or source_tag,
            overwritten_manual_edit=False,
        )

    bundle = collect_available_sermon_material(session, sermon_workshop=sw)
    ctx_hash = compute_context_hash(bundle)
    warnings: list[str] = []
    compressed = False
    raw_wc = 0

    seed = build_outline_from_workshop(session, sermon_workshop=sw)
    structured: dict[str, Any] | None = None

    if generate_fn is not None:
        structured, ai_warnings, raw_wc = _ai_generate_structured(
            bundle, generate_fn=generate_fn, seed_outline=seed, mode=mode
        )
        warnings.extend(ai_warnings)
    if structured is None:
        structured = _heuristic_structured_from_bundle(bundle, seed_outline=seed)

    # Validate BEFORE aggressive trim — trim must not hide a near-sermon.
    issues = validate_structured_outline(structured)
    if raw_wc > LIMITS["absolute_max_words"] and "over_absolute_max" not in issues:
        issues = list(issues) + ["over_absolute_max"]

    if issues and generate_fn is not None:
        repaired, c_warn = _compress_structured(
            structured, bundle, issues=issues, generate_fn=generate_fn
        )
        warnings.extend(c_warn)
        compressed = True
        if repaired is not None:
            structured = repaired
            issues = validate_structured_outline(structured)
        logger.info(
            "outline_after_compress schema=%s issues=%s words=%s",
            SCHEMA_VERSION,
            issues,
            word_count(render_structured_outline(structured)),
        )
        # After compress, remaining issues are final — trim must not salvage.
        if issues:
            rendered_wc = word_count(render_structured_outline(structured))
            logger.info(
                "outline_reject_after_compress schema=%s issues=%s words=%s",
                SCHEMA_VERSION,
                issues,
                rendered_wc,
            )
            return OutlineGenerationResult(
                outline=existing,
                ok=False,
                error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
                warnings=warnings,
                validation_issues=issues,
                source=source_tag,
                compressed=True,
                raw_word_count=raw_wc,
                rendered_word_count=rendered_wc,
            )

    structured = _programmatic_trim(structured)
    issues = validate_structured_outline(structured)

    rendered_wc = word_count(render_structured_outline(structured))

    # Hard reject: ANY remaining issue after AI path → do not overwrite
    if generate_fn is not None and issues:
        logger.info(
            "outline_reject schema=%s issues=%s rendered_words=%s raw_words=%s",
            SCHEMA_VERSION,
            issues,
            rendered_wc,
            raw_wc,
        )
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
            warnings=warnings,
            validation_issues=issues,
            source=source_tag,
            compressed=compressed,
            raw_word_count=raw_wc,
            rendered_word_count=rendered_wc,
        )

    # Offline heuristic: only hard-block catastrophic failures
    if generate_fn is None and issues:
        structured = _programmatic_trim(structured)
        issues = validate_structured_outline(structured)
        fatal = [
            i
            for i in issues
            if i
            in {
                "over_absolute_max",
                "too_few_points",
                "missing_focus",
                "missing_intro",
                "missing_conclusion",
                "full_sermon_like",
            }
        ]
        if fatal or word_count(render_structured_outline(structured)) > LIMITS[
            "absolute_max_words"
        ]:
            return OutlineGenerationResult(
                outline=existing,
                ok=False,
                error_message=INVALID_OUTLINE_MESSAGE,
                warnings=warnings,
                validation_issues=issues,
                source=source_tag,
            )
        # Non-fatal offline leftovers → warnings only (deterministic seed)
        for issue in issues:
            tip = f"Vázlat finomítható: {issue}"
            if tip not in warnings:
                warnings.append(tip)

    outline = structured_to_sermon_outline(
        structured,
        seed=seed,
        source=source_tag or "workshop",
        context_hash=ctx_hash,
    )
    outline["source_fingerprint"] = ctx_hash
    outline["source_sections"] = list(bundle.get("source_keys") or [])
    if generate_fn is None and "sermon_movements" not in (bundle.get("source_keys") or []):
        outline["provisional_sections"] = ["sermon_movements"]
        from sermon_workshop_outline_ai import PROVISIONAL_NOTICE

        if PROVISIONAL_NOTICE not in warnings:
            warnings.append(PROVISIONAL_NOTICE)
    if not outline_has_content(outline):
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=EMPTY_PROJECT_MESSAGE,
            warnings=warnings,
            validation_issues=issues,
            source=source_tag,
            compressed=compressed,
            raw_word_count=raw_wc,
        )

    final_wc = word_count(outline.get("content") or render_structured_outline(structured))
    logger.info(
        "outline_ok schema=%s source=%s rendered_words=%s compressed=%s",
        SCHEMA_VERSION,
        source_tag,
        final_wc,
        compressed,
    )
    return OutlineGenerationResult(
        outline=outline,
        ok=True,
        warnings=warnings,
        validation_issues=[],
        source=source_tag or "workshop",
        overwritten_manual_edit=bool(manually_edited and force_overwrite),
        compressed=compressed,
        raw_word_count=raw_wc,
        rendered_word_count=final_wc,
    )


__all__ = [
    "COMPRESS_INSTRUCTION",
    "FORBIDDEN_HEADINGS",
    "FORBIDDEN_PAYLOAD_KEYS",
    "INVALID_OUTLINE_MESSAGE",
    "LIMITS",
    "OUTLINE_MAX_OUTPUT_TOKENS",
    "OUTLINE_SYSTEM_PROMPT",
    "REFRESH_NOTICE",
    "SCHEMA_VERSION",
    "OutlineGenerationResult",
    "compute_context_hash",
    "generate_sermon_outline",
    "normalize_structured_outline",
    "outline_needs_refresh",
    "render_structured_outline",
    "sermon_outline_to_structured",
    "structured_to_sermon_outline",
    "validate_structured_outline",
    "word_count",
]
