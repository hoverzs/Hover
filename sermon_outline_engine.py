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
SCHEMA_VERSION = "pulpit_outline_v4"
# JSON vázlat: szószéki munkavázlat ≤550 szó; ~1600–1800 token biztonságos keret.
OUTLINE_MAX_OUTPUT_TOKENS = 1700

# ---------------------------------------------------------------------------
# Strict length limits — szószéki munkavázlat (nem jegyzet, nem prédikáció)
# ---------------------------------------------------------------------------

LIMITS = {
    "title_words": 10,
    "focus_words": 35,
    "focus_min_words": 18,
    "intro_words": 60,
    "intro_min_words": 28,
    "intro_sentences_max": 3,
    "point_title_words": 10,
    "subpoint_min_words": 12,
    "subpoint_max_words": 45,
    "subpoint_sentences_max": 2,
    "application_words": 28,
    "conclusion_words": 60,
    "conclusion_min_words": 28,
    "conclusion_sentences_max": 3,
    "scope_note_words": 40,
    "min_points": 2,
    "max_points": 4,
    "default_points": 3,
    "min_subpoints": 2,
    "max_subpoints": 3,
    "target_min_words": 320,
    "target_max_words": 480,
    "soft_floor_words": 280,
    "absolute_max_words": 550,
    "max_prose_block_words": 70,
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
    "Exegetikai és teológiai kibontás",
    "Hallgatói és kegyelmi kapcsolat",
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
    "Először töröld az ismétlést, metaszöveget és fölösleges magyarázatot; "
    "azután rövidíts teljes mondatok megőrzésével; "
    "csak ezután távolítsd el az opcionális alkalmazásokat. "
    "Soha ne vágj félbe mondatot szószám alapján. "
    "Korlátok: teljes látható vázlat 320–480 szó, abszolút maximum 550; "
    "280 szó alatt a vázlat túl sovány; "
    "cím legfeljebb 10 szó; fókusz egy mondat, kb. 20–35 szó; "
    "bevezetési irány 2–3 teljes mondat, kb. 30–60 szó; "
    "2–4 pont; pontcím legfeljebb 10 szó (igehely NÉLKÜL a címmezőben); "
    "pontonként 2–3 alpont; minden alpont 1–2 teljes mondat, kb. 20–45 szó; "
    "alkalmazás rövid, konkrét, vagy üres; "
    "megérkezés 2–3 teljes mondat, kb. 30–60 szó; "
    "refinement_suggestions mindig üres lista. "
    "Ne használj thesis/body/content vagy más új mezőt. "
    "Kizárólag a teljes, javított JSON objektumot add vissza."
)

OUTLINE_SYSTEM_PROMPT = f"""\
SZEREP ÉS CÉL

Tapasztalt, biblikus, református szemléletű homiletikai szerkesztő vagy.
Feladatod egy tartalmas SZÓSZÉKI MUNKAVÁZLAT elkészítése: elég részletes a
felkészüléshez és a szószéki használathoz, de nem kész prédikáció, nem teljes
bevezető vagy záróbeszéd, és nem hosszú retorikai próza.

SÉMAVERZIÓ: {SCHEMA_VERSION}

BELSŐ MUNKAMENET

A következő mérlegelést csendben végezd el; gondolatmenetet és magyarázatot ne
írj a válaszba.

1. Először a betöltött bibliai szöveg belső szerkezetét vizsgáld: központi
   állítás, természetes egységek, feszültség, fordulat és megérkezés.
2. Fogalmazd meg, mit mond vagy tesz a textus, és milyen hitbeli válasz felé
   vezeti a hallgatót.
3. A textus természetes mozgása szerint válassz 2–4 főpontot. Ne ragaszkodj
   automatikusan három ponthoz.
4. Ezután mérlegeld az exegézist, az eredeti nyelvi megfigyeléseket, a releváns
   kortörténetet, a lelkész fókuszát, az alkalmat, a vázlatkosarat és a többi
   műhelyanyagot — csak szelektíven.
5. Hagyd el az ismétlődő, gyenge, bizonytalan vagy a textusnak ellentmondó
   elemeket. Ne próbálj minden mezőt beépíteni.

FORRÁSHIERARCHIA (kötelező sorrend)

1. A ténylegesen betöltött bibliai szöveg és annak belső szerkezete.
2. Az exegézis.
3. Az eredeti héber vagy görög szöveggel kapcsolatos mentett munka.
4. A kortörténeti háttér, de csak ahol valóban megvilágítja a textust.
5. A lelkész saját, kifejezett fókusza és jóváhagyott döntései.
6. Az alkalom és a hallgatói helyzet.
7. A vázlatkosár tudatosan kiválasztott elemei.
8. A többi rendelkezésre álló teológiai és homiletikai műhelyanyag.

A bibliai szöveg, az exegézis, az eredeti nyelvi megfigyelések és a releváns
kortörténet az értelmezési alap. A többi anyag csak szelektíven gazdagítson.
Korábbi vagy gépileg előállított vázlat csak akkor minta, ha a feladat
kifejezetten annak javítása.

Az üres vázlatkosár nem hiányállapot. Teljes, konkrét és professzionális
vázlatot készíts akkor is, ha a kosár üres, feltéve hogy van bibliai szöveg és
legalább érdemi exegézis, eredeti nyelvi megfigyelés, jóváhagyott textusgondolat
vagy saját exegetikai felismerés. A vázlathoz nem kötelező minden homiletikai
műhelylépés. Ne jelezd a hiányt a vázlatban, és ne töltsd ki közhelyekkel.

Ne állíts olyasmit a textusról, amit a betöltött szöveg vagy biztos kontextusa
nem támaszt alá. Versszámot ne találj ki. Egy vers tartalmát ne rendelj más
vershivatkozás alá. Ugyanazt a verset ne bontsd automatikusan több főpontra;
egyetlen versből csak akkor legyen több pont, ha valóban elkülönülő,
homiletikailag indokolt mozgásai vannak. Párhuzamos vagy egymást kiegészítő
felszólításokat alapértelmezetten egy pontban tarts (pl. Júd 20 épülés és
imádság együtt).

A textushatárt ne bővítsd hallgatólagosan. Ha valódi és homiletikailag fontos
határkérdés van, jelezd a `scope_note` mezőben. Ha a következő vers szövege
nincs betöltve, ne használd fel annak tartalmát tényként — csak a lehetséges
bővítést jelezd.

HOMILETIKAI MINŐSÉG

- A fókuszmondat fogja össze a textus állítását és a hallgatói válasz irányát;
  ne legyen puszta témamegjelölés vagy moralizáló felszólítás.
- A pontok valódi gondolati előrehaladást mutassanak; egyik se ismételje a
  fókuszt vagy egy korábbi pontot.
- Pontonként: első alpont a textusbeli állítás/kép/fordulat; következő alpont
  a teológiai és homiletikai jelentőség; opcionálisan rövid, konkrét hallgatói
  irány vagy kérdés.
- Kerüld az általános felszólításokat: „bízzunk jobban”, „fontos felismernünk”,
  „törekedjünk mindennap”.
- Eredeti nyelvi és kortörténeti megfigyelés csak akkor kerüljön a pontba, ha
  tényleg segíti a megértést — ne legyen nyelvészeti vagy történeti előadás.
- Ne ismételd külön pontokban ugyanazt a gondolatot (pl. Ézs 46 „hordoz /
  megtart / megment” egyetlen ívként, ne háromszor).
- A bevezetési irány konkrét emberi helyzet, kérdés vagy feszültség legyen
  (2–3 mondat), nem kész bevezető beszéd és nem metautasítás.
- A megérkezés mutassa, hová érkezik a textus a hallgatóval; ne ismételje a
  pontokat, ne legyen záróprédikáció, és ne vezessen be új témát.
- A Krisztus- és kegyelemhorizont ott jelenjen meg, ahol a textus és a kánoni
  összefüggés indokolja — ne mechanikusan minden pontnál.

MEZŐK TARTALMA

- `title`: rövid, megjegyezhető, a teljes textust összefogó cím.
- `text_reference`: a megadott igehely (és fordítás, ha ismert).
- `scope_note`: csak valódi textushatár-probléma esetén; különben üres.
- `focus_sentence`: egy világos, teljes mondat (kb. 20–35 szó).
- `introduction_direction`: bevezetési irány, 2–3 teljes mondat (kb. 30–60 szó).
- `points`: 2–4 főpont a textus természetes szerkezete szerint.
- `point.title`: pontcím IGEHELY NÉLKÜL (a renderer a `verses` mezőből illeszti).
- `verses`: csak az adott ponthoz tartozó, a betöltött szövegből származó egység.
- `subpoints`: 2–3 alpont; mindegyik 1–2 teljes mondat, kb. 20–45 szó.
- `application`: opcionális, rövid, konkrét hallgatói irány vagy üres.
- `conclusion_direction`: megérkezés, 2–3 teljes mondat (kb. 30–60 szó).
- `refinement_suggestions`: mindig üres lista (nem jelenik meg a szószéki nézetben).

HOSSZKORLÁTOK – KÖTELEZŐ

- `title`: legfeljebb 10 szó.
- `focus_sentence`: 1 mondat, kb. 20–35 szó.
- `introduction_direction`: 2–3 mondat, kb. 30–60 szó.
- `points`: 2–4.
- `point.title`: legfeljebb 10 szó, verses nélkül.
- `point.subpoints`: 2–3; egyenként 1–2 teljes mondat, kb. 20–45 szó.
- `point.application`: legfeljebb 1–2 mondat / 28 szó, vagy üres.
- `conclusion_direction`: 2–3 mondat, kb. 30–60 szó.
- `scope_note`: legfeljebb 40 szó, vagy üres.
- Teljes látható vázlat céltartomány: 320–480 szó; puha alsó határ ~280;
  abszolút maximum 550 szó. A JSON mezőnevek nem számítanak a látható
  szószámba.
- `refinement_suggestions`: mindig `[]`.

TILOS

Tilos teljes prédikációt, kidolgozott bevezetést vagy záróbeszédet írni.
Tilos többbekezdéses prózát írni a pontok alatt.
Tilos félbemaradt mondatot visszaadni.
Tilos a megadott sémán kívüli mezőt létrehozni, különösen:
`body`, `content`, `exegesis`, `theological_expansion`, `grace_connection`,
`listener_connection`, `transition_logic`, `full_introduction`,
`full_conclusion`, `thesis`, `outline_text`.
Tilos szerkesztői fejezetcímeket létrehozni, például:
„Problémafelvetés”, „Magyarázat”, „Teológiai kibontás”,
„Exegetikai és teológiai kibontás”, „Hallgatói és kegyelmi kapcsolat”,
„Kegyelmi kapcsolat”, „Hallgatói alkalmazás”, „Átvezetési logika”.
Tilos metaszöveget, önértékelést, hiányjelzést vagy a választ magyarázó
megjegyzést írni.
Tilos töltelékes fordulatokat használni, például: „de vajon”, „ez azonban”,
„itt felmerül a kérdés”, „nem marad titokban”.

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
      "title": "string without verse ref",
      "verses": "v. x–y",
      "subpoints": ["1–2 full sentences", "1–2 full sentences"],
      "application": "short concrete direction or empty"
    }}
  ],
  "conclusion_direction": "string",
  "refinement_suggestions": []
}}

VÉGSŐ ELLENŐRZÉS

Válaszadás előtt csendben ellenőrizd: textusközpontú-e, szószéki munkavázlat-e
(nem prédikáció), a pontok a természetes egységeket követik-e, az igehelyek
helyesek-e, nincs-e ismétlés vagy félmondat, és a hossz 320–480 szó körül van-e
(max 550). A válasz kizárólag a JSON objektum.\
"""

_JSON_SHAPE = """\
{
  "title": "Rövid, megjegyezhető cím",
  "text_reference": "Igehely",
  "scope_note": "",
  "focus_sentence": "Egy teljes fókuszmondat (kb. 20–35 szó).",
  "introduction_direction": "2–3 teljes mondat bevezetési irány (kb. 30–60 szó).",
  "points": [
    {
      "title": "Pontcím igehely nélkül",
      "verses": "v. x–y",
      "subpoints": [
        "Textuális kibontás: 1–2 teljes mondat (kb. 20–45 szó).",
        "Teológiai/homiletikai jelentőség: 1–2 teljes mondat (kb. 20–45 szó)."
      ],
      "application": ""
    }
  ],
  "conclusion_direction": "2–3 teljes mondat megérkezés (kb. 30–60 szó).",
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
                        "maxItems": 3,
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
    # Ne tördeljen versszám/ordinal pontnál: „17–18. vers”, „3. pont”
    protected = re.sub(r"(?<=\d)\.(?=\s)", "⟪DOT⟫", raw)
    parts = [
        p.replace("⟪DOT⟫", ".").strip()
        for p in re.split(r"(?<=[.!?])\s+", protected)
        if p.strip()
    ]
    return max(1, len(parts)) if raw else 0


def _looks_truncated_sentence(text: Any) -> bool:
    """Félbemaradt mondat: nincs záró írásjel, vagy nyilvánvalóan csonka."""
    raw = _s(text)
    if not raw:
        return False
    if raw.endswith((".", "!", "?", "…", '"', "”", "'")):
        # Still flag obvious mid-clause stubs ending with period after tiny tail
        low = raw.casefold()
        if re.search(r"\b(és|vagy|hogy|mert|ha|de|majd)\s*\.$", low):
            return True
        return False
    # Ends mid-thought without terminal punctuation
    if re.search(r"\b(és|vagy|hogy|mert|ha|de|majd|két|egy)\s*$", raw.casefold()):
        return True
    if word_count(raw) >= 4 and not re.search(r"[.!?…]$", raw):
        return True
    return False


def _split_sentences(text: str) -> list[str]:
    raw = _s(text)
    if not raw:
        return []
    protected = re.sub(r"(?<=\d)\.(?=\s)", "⟪DOT⟫", raw)
    return [
        p.replace("⟪DOT⟫", ".").strip()
        for p in re.split(r"(?<=[.!?])\s+", protected)
        if p.strip()
    ]


def _clip_to_full_sentences(text: str, max_w: int) -> str:
    """Rövidít teljes mondatok mentén — soha nem vág félbe mondatot."""
    raw = _s(text)
    if not raw or word_count(raw) <= max_w:
        return raw
    sents = _split_sentences(raw)
    # Ha nincs mondatzáró, ne vágjunk szóhatáron — hagyjuk a validátorra.
    if len(sents) <= 1 and not re.search(r"[.!?…]$", raw):
        return raw
    kept: list[str] = []
    for sent in sents:
        trial = " ".join(kept + [sent]).strip()
        if kept and word_count(trial) > max_w:
            break
        kept.append(sent)
    if kept:
        return " ".join(kept).strip()
    # Első mondat önmagában túl hosszú: ne csonkítsuk szóhatáron.
    return sents[0] if sents else raw


def extract_verse_numbers(text: Any) -> set[int]:
    """Versszámok kinyerése igehely-mezőből vagy bibliai szövegből."""
    raw = _s(text)
    if not raw:
        return set()
    found: set[int] = set()
    # Ranges: 17–20 / 17-20 / 17–18
    for a, b in re.findall(r"\b(\d{1,3})\s*[–\-]\s*(\d{1,3})\b", raw):
        lo, hi = int(a), int(b)
        if 1 <= lo <= hi <= 200:
            found.update(range(lo, hi + 1))
    # Standalone verse markers near v. / vers
    for m in re.finditer(
        r"(?:(?:^|[\s(,;:])v\.?\s*|vers(?:e[ks])?\s+)(\d{1,3})\b",
        raw,
        flags=re.I | re.M,
    ):
        n = int(m.group(1))
        if 1 <= n <= 200:
            found.add(n)
    # Hungarian ordinal style: "21. vers"
    for m in re.finditer(r"\b(\d{1,3})\.\s*vers", raw, flags=re.I):
        n = int(m.group(1))
        if 1 <= n <= 200:
            found.add(n)
    # Leading verse numbers in loaded biblical text: "17 Ti pedig"
    for m in re.finditer(r"(?m)^\s*(\d{1,3})\s+\S", raw):
        n = int(m.group(1))
        if 1 <= n <= 200:
            found.add(n)
    return found


def scope_note_uses_unloaded_verse(scope_note: Any, passage_text: Any) -> bool:
    """True, ha a scope_note olyan verset említ tényként, ami nincs betöltve."""
    note = _s(scope_note)
    passage = _s(passage_text)
    if not note or not passage:
        return False
    loaded = extract_verse_numbers(passage)
    if not loaded:
        return False
    mentioned = extract_verse_numbers(note)
    if not mentioned:
        return False
    # Pure boundary suggestion (e.g. "fontolható a 21. vers bevétele") is OK
    # only if it does not assert content of the missing verse as fact.
    missing = mentioned - loaded
    if not missing:
        return False
    factual = re.search(
        r"(állít|mondja|tanítja|ígéri|parancsol|hirdeti|tartalmazza|arról beszél)",
        note.casefold(),
    )
    return bool(factual)


def _looks_multi_paragraph(text: Any) -> bool:
    raw = _s(text)
    if not raw:
        return False
    if "\n\n" in raw:
        return True
    return sentence_count(raw) >= 4 and word_count(raw) > 80


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


def validate_structured_outline(
    payload: Any,
    *,
    passage_text: Any = "",
) -> list[str]:
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
                if isinstance(raw_subpoints, list):
                    n_sp = len(raw_subpoints)
                    if n_sp < LIMITS["min_subpoints"] or n_sp > LIMITS["max_subpoints"]:
                        issues.append("invalid_subpoint_count")
                if _looks_multi_paragraph(raw_point.get("application")):
                    issues.append("multi_paragraph_field")
                    break

    if not data["focus_sentence"]:
        issues.append("missing_focus")
    else:
        if word_count(data["focus_sentence"]) > LIMITS["focus_words"]:
            issues.append("focus_too_long")
        if sentence_count(data["focus_sentence"]) != 1:
            issues.append("focus_not_one_sentence")
        if _looks_truncated_sentence(data["focus_sentence"]):
            issues.append("truncated_sentence")

    if data["title"] and word_count(data["title"]) > LIMITS["title_words"]:
        issues.append("title_too_long")

    if data["scope_note"] and word_count(data["scope_note"]) > LIMITS["scope_note_words"]:
        issues.append("scope_note_too_long")
    if passage_text and scope_note_uses_unloaded_verse(
        data["scope_note"], passage_text
    ):
        issues.append("scope_note_unloaded_verse")

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
        if _looks_truncated_sentence(intro):
            issues.append("truncated_sentence")

    points = data["points"]
    n = len(points)
    if n < LIMITS["min_points"]:
        issues.append("too_few_points")
    if n > LIMITS["max_points"]:
        issues.append("too_many_points")

    titles_seen: set[str] = set()
    verse_sets: list[frozenset[int]] = []
    verse_labels: list[str] = []
    for pt in points:
        title = _s(pt.get("title"))
        verses = _s(pt.get("verses"))
        subs = [_s(x) for x in (pt.get("subpoints") or []) if _s(x)]
        app = _s(pt.get("application"))
        tnorm = _normalize_cmp(title)
        if not title:
            issues.append("empty_point_title")
        elif word_count(title) > LIMITS["point_title_words"]:
            issues.append("point_title_too_long")
        if any(_normalize_cmp(title) == _normalize_cmp(h) for h in FORBIDDEN_HEADINGS):
            issues.append("forbidden_heading")
        # Title must not embed a hand-written verse ref (renderer owns that)
        if re.search(r"\(\s*v\.?\s*\d", title.casefold()) or re.search(
            r"\bv\.?\s*\d{1,3}\s*[–\-]\s*\d", title.casefold()
        ):
            issues.append("verse_in_point_title")
        if tnorm in titles_seen:
            issues.append("duplicate_points")
        titles_seen.add(tnorm)
        for prev in titles_seen - {tnorm}:
            if prev and tnorm and (prev in tnorm or tnorm in prev):
                if abs(len(prev) - len(tnorm)) <= 8:
                    issues.append("duplicate_points")
        vset = frozenset(extract_verse_numbers(verses))
        verse_sets.append(vset)
        verse_labels.append(_normalize_cmp(verses))
        if len(subs) < LIMITS["min_subpoints"]:
            issues.append("too_few_subpoints")
        if len(subs) > LIMITS["max_subpoints"]:
            issues.append("too_many_subpoints")
        if not (
            LIMITS["min_subpoints"] <= len(subs) <= LIMITS["max_subpoints"]
        ):
            issues.append("invalid_subpoint_count")
        for sp in subs:
            wc = word_count(sp)
            if wc < LIMITS["subpoint_min_words"]:
                issues.append("stub_subpoint")
            if wc > LIMITS["subpoint_max_words"]:
                issues.append("subpoint_length")
            sc = sentence_count(sp)
            if sc < 1 or sc > LIMITS["subpoint_sentences_max"]:
                issues.append("subpoint_sentence_count")
            if _looks_multi_paragraph(sp):
                issues.append("multi_paragraph_point")
            if _looks_truncated_sentence(sp):
                issues.append("truncated_sentence")
            if wc > LIMITS["max_prose_block_words"]:
                issues.append("prose_block_too_long")
        if app:
            if word_count(app) > LIMITS["application_words"]:
                issues.append("application_too_long")
            if sentence_count(app) > 2:
                issues.append("application_too_many_sentences")
            if _looks_multi_paragraph(app):
                issues.append("multi_paragraph_point")
            if _looks_truncated_sentence(app):
                issues.append("truncated_sentence")

    # Same verse label split into consecutive main points (e.g. two "v. 20")
    for i in range(1, len(verse_labels)):
        a, b = verse_labels[i - 1], verse_labels[i]
        if a and b and a == b:
            issues.append("split_same_verse")

    # Loaded middle verse skipped while neighbors covered (e.g. Jude 19)
    loaded_verses = extract_verse_numbers(passage_text) if passage_text else set()
    covered: set[int] = set()
    for vs in verse_sets:
        covered |= set(vs)
    if loaded_verses and covered:
        for v in sorted(loaded_verses):
            if v in covered:
                continue
            if (v - 1) in covered and (v + 1) in covered:
                issues.append("missing_verse_unit")
                break

    # Ézs 46-style triad repeated as separate point cores
    point_blobs = [
        " ".join(
            [
                _s(pt.get("title")),
                " ".join(_s(x) for x in (pt.get("subpoints") or [])),
            ]
        ).casefold()
        for pt in points
    ]
    triad = ("hordoz", "megtart", "megment")
    triad_hits = sum(1 for blob in point_blobs if sum(1 for t in triad if t in blob) >= 2)
    if triad_hits >= 3:
        issues.append("repeated_thematic_triad")

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
        if _looks_truncated_sentence(conc):
            issues.append("truncated_sentence")

    rendered = render_structured_outline(data)
    total = word_count(rendered)
    if total > LIMITS["absolute_max_words"]:
        issues.append("over_absolute_max")
    if total and total < LIMITS["soft_floor_words"]:
        issues.append("too_thin")

    # Standalone verse-only lines under point titles must not appear
    for block in rendered.split("\n\n"):
        plain = block.strip()
        if re.fullmatch(r"\*?v\.?\s*\d{1,3}(?:\s*[–\-]\s*\d{1,3})?\*?", plain.casefold()):
            issues.append("standalone_verse_line")
            break

    for block in rendered.split("\n\n"):
        plain = re.sub(r"^[-•*]\s+", "", block.strip(), flags=re.M)
        plain = re.sub(r"\*\*?|[*_]", "", plain)
        if word_count(plain) > LIMITS["max_prose_block_words"] and not plain.startswith(
            ("1.", "2.", "3.", "4.")
        ):
            if not plain.startswith("**") and "\n- " not in block and not block.strip().startswith("-"):
                if not any(
                    block.strip().startswith(f"**{lab}")
                    for lab in (
                        "Cím",
                        "Textus",
                        "Fókuszmondat",
                        "Bevezetési irány",
                        "Bevezetés",
                        "Megérkezés",
                        "Megjegyzés",
                    )
                ):
                    issues.append("prose_block_too_long")

    blob = rendered.casefold()
    for heading in FORBIDDEN_HEADINGS:
        # Csak cím-/fejezetszerű előfordulás (ne a futó szöveg „magyarázat” szava)
        h = re.escape(heading.casefold())
        if re.search(
            rf"(?m)^(?:\*\*|#{1,3}\s*)?{h}\**\s*$",
            blob,
        ) or re.search(rf"\*\*{h}\*\*", blob):
            issues.append("forbidden_heading")
            break
    for filler in FORBIDDEN_FILLERS:
        if filler in blob:
            issues.append("forbidden_filler")
            break

    if re.search(r"(?m)^#{1,3}\s+\S", rendered) or rendered.count("##") >= 2:
        issues.append("raw_markdown_chapters")

    para_count = len([p for p in rendered.split("\n\n") if len(p) > 120])
    if para_count >= 8 and total > LIMITS["absolute_max_words"]:
        issues.append("full_sermon_like")

    return list(dict.fromkeys(issues))


def _strip_trailing_verse_from_title(title: str) -> str:
    cleaned = re.sub(r"^\s*\d+[.)]\s*", "", _s(title)).strip()
    cleaned = re.sub(
        r"\s*\(\s*v\.?\s*\d{1,3}(?:\s*[–\-]\s*\d{1,3})?\s*\)\s*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    cleaned = re.sub(
        r"\s+v\.?\s*\d{1,3}(?:\s*[–\-]\s*\d{1,3})?\s*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    return cleaned


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
    _sec("Bevezetési irány", data["introduction_direction"])

    for idx, pt in enumerate(data["points"], start=1):
        title = _strip_trailing_verse_from_title(_s(pt.get("title")))
        if not title:
            continue
        verses = _s(pt.get("verses"))
        heading = f"{idx}. {title}"
        if verses:
            heading = f"{heading} ({verses})"
        parts: list[str] = []
        for sp in pt.get("subpoints") or []:
            cleaned = re.sub(r"^[-•*]\s+", "", _s(sp)).strip()
            if "\n\n" in cleaned:
                cleaned = cleaned.split("\n\n")[0].strip()
            if cleaned:
                parts.append(f"- {cleaned}")
        app = _s(pt.get("application"))
        if app:
            parts.append(f"*{app}*")
        if not parts:
            continue
        blocks.append(f"**{heading}**\n\n" + "\n".join(parts))

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
    "A vázlatgenerálás nem adott szószéken használható munkavázlatot "
    f"(céltartomány {LIMITS['target_min_words']}–{LIMITS['target_max_words']} szó, "
    f"abszolút max. {LIMITS['absolute_max_words']} szó). "
    "Próbáld újra — a hosszú prédikációs szöveg vagy a csonka vázlat nem kerül mentésre."
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
    """Offline / teszt: szószéki munkavázlat a rendelkezésre álló anyagból."""
    from sermon_workshop_outline_ai import (
        _prefer_main_idea,
        _truncate,
        _usable_text,
    )

    data = empty_structured_outline()
    data["text_reference"] = _s(bundle.get("passage_reference"))
    data["title"] = _s(bundle.get("project_title")) or data["text_reference"] or "Vázlat"
    if word_count(data["title"]) > LIMITS["title_words"]:
        data["title"] = _clip_to_full_sentences(data["title"], LIMITS["title_words"])
        if word_count(data["title"]) > LIMITS["title_words"]:
            data["title"] = " ".join(data["title"].split()[: LIMITS["title_words"]])

    focus = _prefer_main_idea(bundle)
    if not focus and seed_outline:
        focus = _s(seed_outline.get("main_idea"))
    data["focus_sentence"] = (
        _usable_text(focus)
        or "A textus Isten megtartó szavát hirdeti, és a hallgatót hitbeli válaszra hívja."
    )
    if data["focus_sentence"] and not data["focus_sentence"].endswith((".", "!", "?")):
        data["focus_sentence"] += "."
    data["focus_sentence"] = _clip_to_full_sentences(
        data["focus_sentence"], LIMITS["focus_words"]
    )
    if data["focus_sentence"] and not data["focus_sentence"].endswith((".", "!", "?")):
        data["focus_sentence"] += "."

    lt = bundle.get("listener_tension") if isinstance(bundle.get("listener_tension"), dict) else {}
    path = bundle.get("sermon_path") if isinstance(bundle.get("sermon_path"), dict) else {}
    intro = (
        _usable_text(path.get("starting_point"))
        or _usable_text(lt.get("listener_question"))
        or (
            "A hallgató gyakran a saját bizonytalanságából indul, amikor a textus "
            "szava elé áll. A kérdés az, milyen feszültség nyitja meg természetesen "
            "ezt az igeszakaszt. Innen vezet az út a textus saját állítása felé."
        )
    )
    data["introduction_direction"] = _clip_to_full_sentences(
        _truncate(intro, 420), LIMITS["intro_words"]
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
    history = _usable_text(bundle.get("history"))

    def _rich_bullet(text: str, *, fallback: str) -> str:
        target_min = LIMITS["subpoint_min_words"]
        max_w = LIMITS["subpoint_max_words"]
        cleaned = _usable_text(text) or fallback
        if cleaned and not cleaned.endswith((".", "!", "?")):
            cleaned += "."
        pad = (
            f" {fallback} {data['focus_sentence']}"
            if word_count(cleaned) < target_min
            else ""
        )
        sent = (cleaned + pad).strip()
        if not sent.endswith((".", "!", "?")):
            sent += "."
        # Ha még mindig sovány, egész mondatot toldunk, nem szótöredéket.
        while word_count(sent) < target_min:
            sent = (
                sent.rstrip(".!?")
                + ", és a textus saját mozgása tovább pontosítja ezt a pontot."
            )
        return _clip_to_full_sentences(sent, max_w)

    if movements:
        for i, mv in enumerate(movements[: LIMITS["max_points"]], start=1):
            if not isinstance(mv, dict):
                continue
            core = _usable_text(mv.get("core_content")) or _usable_text(
                mv.get("listener_discovery")
            )
            title = _strip_trailing_verse_from_title(
                _usable_text(mv.get("title")) or f"Pont {i}"
            )
            if word_count(title) > LIMITS["point_title_words"]:
                title = " ".join(title.split()[: LIMITS["point_title_words"]])
            basis = _usable_text(mv.get("textual_basis")) or _usable_text(
                mv.get("textual_anchor")
            )
            # Prefer short verse refs over full passage labels
            if basis and extract_verse_numbers(basis) and len(basis) > 24:
                nums = sorted(extract_verse_numbers(basis))
                if len(nums) == 1:
                    basis = f"v. {nums[0]}"
                elif nums:
                    basis = f"v. {nums[0]}–{nums[-1]}"
            sp1 = _rich_bullet(
                core
                or exe
                or (insights[0] if insights else data["focus_sentence"]),
                fallback=(
                    "A textus saját szavai és szerkezete rendezik ezt a gondolatot "
                    "a hallgató előtt."
                ),
            )
            sp2 = _rich_bullet(
                _usable_text(mv.get("listener_discovery"))
                or (insights[1] if len(insights) > 1 else "")
                or original
                or exe
                or "Isten cselekvése hív választ, nem emberi erőfeszítés.",
                fallback=(
                    "A teológiai és homiletikai jelentőség abban áll, hogy Isten "
                    "cselekvése hív választ, nem az emberi erőfeszítés."
                ),
            )
            points.append(
                {
                    "title": title,
                    "verses": basis or "",
                    "subpoints": [sp1, sp2],
                    "application": "",
                }
            )
    else:
        seeds = insights or decisions or [
            exe[:180] if exe else "",
            original[:180] if original else "",
            data["focus_sentence"],
        ]
        seeds = [s for s in seeds if s] or [data["focus_sentence"]]
        while len(seeds) < 3:
            seeds.append(data["focus_sentence"])
        titles = ("A textus megnyitása", "A központi állítás", "A kegyelmi megérkezés")
        loaded = sorted(extract_verse_numbers(bundle.get("passage_text") or ""))
        if len(loaded) >= 3:
            verse_labels = [
                f"v. {loaded[0]}–{loaded[1]}" if len(loaded) > 1 else f"v. {loaded[0]}",
                f"v. {loaded[len(loaded)//2]}",
                f"v. {loaded[-1]}",
            ]
        elif len(loaded) == 2:
            verse_labels = [f"v. {loaded[0]}", f"v. {loaded[1]}", f"v. {loaded[1]}"]
            # Avoid consecutive identical labels
            verse_labels[2] = f"v. {loaded[0]}–{loaded[1]}"
        elif len(loaded) == 1:
            verse_labels = [f"v. {loaded[0]}a", f"v. {loaded[0]}b", f"v. {loaded[0]}c"]
        else:
            verse_labels = ["", "", ""]
        for i in range(3):
            body = seeds[i % len(seeds)]
            points.append(
                {
                    "title": titles[i],
                    "verses": verse_labels[i],
                    "subpoints": [
                        _rich_bullet(
                            body,
                            fallback=(
                                "A textus saját mozgása bontja ki ezt a pontot a "
                                "betöltött igeszakasz alapján a hallgató előtt."
                            ),
                        ),
                        _rich_bullet(
                            exe or original or data["focus_sentence"],
                            fallback=(
                                "A hallgató Isten cselekvése felől látja a választ, "
                                "és így a textus homiletikai súlya is kirajzolódik."
                            ),
                        ),
                        _rich_bullet(
                            history or data["focus_sentence"],
                            fallback=(
                                "Ez a pont előreviszi a prédikáció ívét anélkül, "
                                "hogy ismételné a fókuszmondatot vagy a korábbi állítást."
                            ),
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
        or (
            "A hallgató nem új témánál, hanem a textus megérkezésénél áll meg. "
            "Isten megtartó szeretete hív válaszra. Innen vihető tovább a szószéki "
            "kibontás a gyülekezet konkrét helyzetére."
        )
    )
    data["conclusion_direction"] = _clip_to_full_sentences(
        _truncate(conc, 420), LIMITS["conclusion_words"]
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
            f"CÉLHOSSZ: {LIMITS['target_min_words']}–{LIMITS['target_max_words']} szó "
            f"(abszolút max {LIMITS['absolute_max_words']}; "
            f"puha alsó határ ~{LIMITS['soft_floor_words']}).\n"
        )
    prompt = (
        f"{task_mode_note}\n"
        f"{occasion_block}"
        "A feladat új szószéki munkavázlat készítése, nem egy korábbi vázlat "
        "javítása vagy átszövegezése.\n"
        "Forráshierarchia: betöltött bibliai szöveg → exegézis → eredeti nyelvi "
        "munka → releváns kortörténet → lelkészi fókusz/döntések → alkalom/"
        "hallgató → vázlatkosár → egyéb műhelyanyag.\n"
        "Először a textus központi állítását és természetes egységeit állapítsd "
        "meg. Csak ezután mérlegeld a többi anyagot szelektíven.\n"
        "Üres vázlatkosár esetén is készíts teljes értékű, konkrét vázlatot.\n"
        "Ne ragaszkodj három ponthoz; a textus szerint válassz 2–4 pontot.\n"
        "Pontonként 2–3 alpontot adj (1–2 teljes mondat, kb. 20–45 szó).\n"
        "Az igehelyet csak a `verses` mezőbe írd; a pont `title` mezője legyen "
        "igehely nélküli.\n"
        "Ugyanazt a verset ne bontsd több főpontra; párhuzamos felszólításokat "
        "egy pontban tarts.\n"
        "A bevezetési irány és a megérkezés 2–3 tartalmi mondat legyen, ne "
        "szerkesztői utasítás és ne kész beszéd.\n\n"
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
    """Deterministic cleanup — teljes mondatok mentén, félmondat nélkül."""
    data = normalize_structured_outline(payload)

    data["title"] = _strip_trailing_verse_from_title(data["title"])
    if word_count(data["title"]) > LIMITS["title_words"]:
        # Címnél a szóhatár elfogadható (nem mondat); ne hagyjunk üres címet.
        data["title"] = " ".join(data["title"].split()[: LIMITS["title_words"]])
    data["focus_sentence"] = _clip_to_full_sentences(
        data["focus_sentence"], LIMITS["focus_words"]
    )
    data["introduction_direction"] = _clip_to_full_sentences(
        data["introduction_direction"], LIMITS["intro_words"]
    )
    data["conclusion_direction"] = _clip_to_full_sentences(
        data["conclusion_direction"], LIMITS["conclusion_words"]
    )
    data["scope_note"] = _clip_to_full_sentences(
        data["scope_note"], LIMITS["scope_note_words"]
    )
    trimmed_points: list[dict[str, Any]] = []
    for pt in data["points"][: LIMITS["max_points"]]:
        title = _strip_trailing_verse_from_title(_s(pt.get("title")))
        if word_count(title) > LIMITS["point_title_words"]:
            title = " ".join(title.split()[: LIMITS["point_title_words"]])
        subs: list[str] = []
        for sp in (pt.get("subpoints") or [])[: LIMITS["max_subpoints"]]:
            cleaned = _s(sp)
            if "\n\n" in cleaned:
                cleaned = cleaned.split("\n\n")[0].strip()
            cleaned = _clip_to_full_sentences(cleaned, LIMITS["subpoint_max_words"])
            # Max 2 sentences per subpoint
            sents = _split_sentences(cleaned)[: LIMITS["subpoint_sentences_max"]]
            cleaned = " ".join(sents).strip()
            if cleaned and not _looks_truncated_sentence(cleaned):
                subs.append(cleaned)
            elif cleaned and not _looks_truncated_sentence(
                _split_sentences(cleaned)[0] if _split_sentences(cleaned) else ""
            ):
                first = _split_sentences(cleaned)[0]
                if first:
                    subs.append(first)
        app = _clip_to_full_sentences(
            _s(pt.get("application")), LIMITS["application_words"]
        )
        trimmed_points.append(
            {
                "title": title,
                "verses": _s(pt.get("verses")),
                "subpoints": subs,
                "application": app,
            }
        )
    data["points"] = trimmed_points
    data["refinement_suggestions"] = []

    def _over() -> bool:
        return word_count(render_structured_outline(data)) > LIMITS["absolute_max_words"]

    # 1) Drop optional applications
    if _over():
        for pt in data["points"]:
            pt["application"] = ""
    # 2) Drop third subpoints
    if _over():
        for pt in data["points"]:
            if len(pt["subpoints"]) > 2:
                pt["subpoints"] = pt["subpoints"][:2]
    # 3) Shorten framing fields by whole sentences
    if _over():
        data["introduction_direction"] = _clip_to_full_sentences(
            data["introduction_direction"], 40
        )
        data["conclusion_direction"] = _clip_to_full_sentences(
            data["conclusion_direction"], 40
        )
        data["focus_sentence"] = _clip_to_full_sentences(data["focus_sentence"], 30)
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

    passage_for_validation = bundle.get("passage_text") or ""

    soft_quality_issues = frozenset({"too_thin"})

    def _hard_issues(items: list[str]) -> list[str]:
        return [i for i in items if i not in soft_quality_issues]

    # Validate BEFORE aggressive trim — trim must not hide a near-sermon.
    issues = validate_structured_outline(
        structured, passage_text=passage_for_validation
    )
    if raw_wc > LIMITS["absolute_max_words"] and "over_absolute_max" not in issues:
        issues = list(issues) + ["over_absolute_max"]

    if _hard_issues(issues) and generate_fn is not None:
        repaired, c_warn = _compress_structured(
            structured, bundle, issues=issues, generate_fn=generate_fn
        )
        warnings.extend(c_warn)
        compressed = True
        if repaired is not None:
            structured = repaired
            issues = validate_structured_outline(
                structured, passage_text=passage_for_validation
            )
        logger.info(
            "outline_after_compress schema=%s issues=%s words=%s",
            SCHEMA_VERSION,
            issues,
            word_count(render_structured_outline(structured)),
        )
        # After compress, remaining HARD issues are final — trim must not salvage.
        if _hard_issues(issues):
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
    issues = validate_structured_outline(
        structured, passage_text=passage_for_validation
    )

    rendered_wc = word_count(render_structured_outline(structured))

    # Soft quality flags (e.g. too_thin) → warning, not silent overwrite of primary view
    for soft in issues:
        if soft in soft_quality_issues:
            tip = f"Vázlat minőség: {soft}"
            if tip not in warnings:
                warnings.append(tip)

    # Hard reject: remaining HARD issues after AI path → do not overwrite
    if generate_fn is not None and _hard_issues(issues):
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
        issues = validate_structured_outline(
            structured, passage_text=passage_for_validation
        )
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
        # Non-fatal offline leftovers (incl. too_thin) → warnings only
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
    "OUTLINE_RESPONSE_SCHEMA",
    "OUTLINE_SYSTEM_PROMPT",
    "REFRESH_NOTICE",
    "SCHEMA_VERSION",
    "OutlineGenerationResult",
    "compute_context_hash",
    "extract_verse_numbers",
    "generate_sermon_outline",
    "normalize_structured_outline",
    "outline_needs_refresh",
    "render_structured_outline",
    "scope_note_uses_unloaded_verse",
    "sermon_outline_to_structured",
    "structured_to_sermon_outline",
    "validate_structured_outline",
    "word_count",
]
