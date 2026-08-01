"""Egyetlen közös igehirdetési-vázlat motor (pulpit_outline_v8).

Mindkét belépési pont (Gyorseszközök → Gyors vázlat, Igehirdetési műhely →
Igehirdetési vázlat) ezt a modult hívja. Strukturált OutlineContext,
BARE/PARTIAL/RICH módok, feltételes ExegeticalBrief, kanonikus `movements`
séma és determinisztikus minőségvédelem. Nem importál app.py /
sermon_workshop_ui.py fájlból.
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
from prompt_safety import wrap_untrusted_content
from ai_response_validation import sanitize_ai_json
from sermon_outline_context import (
    ContextMode,
    build_outline_context,
    outline_context_to_legacy_bundle,
)
from sermon_outline_exegesis import ExegeticalBrief, generate_exegetical_brief
from exegetical_core import (
    core_to_outline_brief,
    ensure_exegetical_core,
    invalidate_core_if_stale,
)
from sermon_outline_quality import (
    SEMANTIC_HARD_ISSUES,
    assess_semantic_quality,
    build_repair_prompt,
)

GenerateFn = Callable[..., str]

logger = logging.getLogger("textus.outline")

TAB_OUTLINE = "Igehirdetési vázlat"
DEFAULT_TEMPERATURE = 0.2
SCHEMA_VERSION = "pulpit_outline_v8"
ENGINE_VERSION = "outline_engine_v8"
LEGACY_SCHEMA_VERSIONS = frozenset(
    {
        "",
        "pulpit_outline_v3",
        "pulpit_outline_v4",
        "pulpit_outline_v5",
        "pulpit_outline_v6",
        "pulpit_outline_v7",
    }
)
OUTLINE_MAX_OUTPUT_TOKENS = 2400
RAPID_EVIDENCE_SESSION_KEY = "_outline_rapid_evidence_cache"

# ---------------------------------------------------------------------------
# Kanonikus movements-vázlat — nem prédikáció, nem kétsoros séma
# ---------------------------------------------------------------------------

LIMITS = {
    "title_words": 14,
    "focus_words": 45,
    "focus_min_words": 8,
    "intro_words": 90,
    "intro_min_words": 12,
    "intro_sentences_max": 4,
    "point_title_words": 14,
    "layer_min_words": 8,
    "layer_max_words": 70,
    "layer_sentences": 3,
    "point_layers_min_words": 28,
    "point_layers_max_words": 200,
    "conclusion_words": 90,
    "conclusion_min_words": 12,
    "conclusion_sentences_max": 4,
    "scope_note_words": 40,
    "transition_words": 40,
    "min_points": 2,
    "max_points": 5,
    "default_points": 3,
    # Soft céltartományok — iránymutatás, nem merev korlát.
    "target_min_words": 280,
    "target_max_words": 750,
    "target_min_2": 220,
    "target_max_2": 520,
    "target_min_3_4": 320,
    "target_max_3_4": 750,
    "target_min_5": 400,
    "target_max_5": 850,
    "soft_floor_words": 200,
    "absolute_max_words": 900,
    "max_prose_block_words": 160,
    "refinement_max": 2,
}

# Soft: under_target / too_thin → warning + opcionális enrich; soha nem önálló reject.
# Compress csak over_absolute_max / full_sermon_like.
SOFT_QUALITY_ISSUES = frozenset(
    {
        "under_target",
        "too_thin",
        "repeated_thematic_triad",
        "generic_filler",
        "paired_ab_verse_split",
        "repeated_phrase",
    }
)
ENRICHABLE_ISSUES = frozenset(
    {
        "too_thin",
        "focus_too_short",
        "intro_too_short",
        "conclusion_too_short",
        "stub_layer",
        "point_layers_too_short",
        "truncated_sentence",
        "layer_sentence_count",
        "missing_textual_insight",
        "missing_theological_emphasis",
        "missing_listener_movement",
        "generic_filler",
        "repeated_layer_text",
        "repeated_thematic_triad",
        "focus_not_one_sentence",
    }
)
COMPRESS_TRIGGER_ISSUES = frozenset({"over_absolute_max", "full_sermon_like"})
# Szemantikai hibák → egy célzott repair hívás
REPAIRABLE_ISSUES = frozenset(SEMANTIC_HARD_ISSUES) | frozenset(
    {
        "forbidden_heading",
        "forbidden_filler",
        "raw_markdown_chapters",
        "split_same_verse",
        "duplicate_points",
        "focus_too_long",
        "missing_focus",
        "missing_intro",
        "missing_conclusion",
        "truncated_sentence",
    }
)

# Prose-bait / legacy fields — soha ne kérjük és ne jelenjenek meg elsődlegesen.
# Megjegyzés: `subpoints` / `application` migrációval beolvasható, de nem kanonikus kimenet.
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

POINT_LAYER_KEYS = (
    "textual_insight",
    "theological_emphasis",
    "listener_movement",
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
    "FORMAI TÖMÖRÍTÉS — csak ha a látható vázlat az abszolút felső határ felett van. "
    "A kapott vázlat tartalmi és homiletikai ívét őrizd meg; "
    "ne tervezz új vázlatot és ne adj hozzá új exegetikai vagy teológiai állítást. "
    "Csak a fölösleges ismétlést, metaszöveget és prédikációs bőbeszédűséget csökkentsd. "
    "Soha ne vágj félbe mondatot szószám alapján. "
    "Őrizd a movements szerkezetet: textual_insight, theological_emphasis, "
    "listener_movement (és transition csak ha már volt). "
    f"Abszolút felső határ {LIMITS['absolute_max_words']} szó. "
    "Ne használj thesis/body/content/subpoints/application/points mezőt — "
    "a kanonikus tömb neve `movements`. "
    "Kizárólag a teljes, javított JSON objektumot add vissza."
)

ENRICH_INSTRUCTION = (
    "CÉLZOTT TARTALMI KIEGÉSZÍTÉS — ha a vázlat felszínes, ismétlődő, vagy "
    "egy kötelező réteg hiányzik/sovány. "
    "A kapott vázlat szerkezetét és igehely-beosztását őrizd; "
    "ne írj új prédikációt és ne találj ki verseket. "
    "Gazdagítsd a FORRÁS és a gyors háttércsomag anyagából. "
    "Minden mozgásban legyen konkrét textual_insight, theological_emphasis és "
    "listener_movement — teljes mondatok, nem közhely, nem bekezdés. "
    "Ne ismételd ugyanazt a mondatot más mezőben. "
    "Ne írj többbekezdéses prózát vagy záróprédikációt. "
    "refinement_suggestions: legfeljebb 2 hasznos szerkesztői javaslat, vagy []. "
    "Kizárólag a teljes, kiegészített JSON objektumot add vissza."
)

RAPID_EVIDENCE_SYSTEM_PROMPT = """\
Rövid, belső homiletikai háttércsomagot készítesz egy igehirdetési vázlathoz.
Nem teljes exegézis és nem prédikáció. Csak a releváns szempontok.

TILOS bizonytalan görög/héber adatot kitalálni. Ha nem biztos a nyelvi
részlet, hagyd el. Ne állítsd, hogy külső forráskutatást végeztél.

Kizárólag JSON:

{
  "central_claim": "a textus központi állítása",
  "internal_movement": "belső szerkezet és gondolati mozgás",
  "literary_context": "közvetlen irodalmi kontextus (röviden)",
  "historical_notes": "csak a megértéshez szükséges történeti háttér, vagy üres",
  "language_notes": "legfeljebb 1–2 biztos nyelvi megfigyelés, vagy üres",
  "theological_horizon": "teológiai / kánoni horizont",
  "homiletical_path": "természetes homiletikai út a hallgató felé"
}
"""

OUTLINE_SYSTEM_PROMPT = f"""\
SZEREP

Tapasztalt, biblikus, református szemléletű homiletikai szerkesztő vagy.
Feladatod szószékre vihető GONDOLATVÁZLAT készítése — nem kész prédikáció,
nem hosszú kommentár, nem mechanikus műhelyösszefoglaló.

SÉMAVERZIÓ: {SCHEMA_VERSION}
MOTOR: {ENGINE_VERSION}

CÉL

Találd meg a textus saját mozgását. A háttéranyagból válogass: az irreleváns,
ismétlődő vagy a textussal ellentétes elemeket hagyd el. A homiletikai módszerek
(Craddock, Lowry, Buttrick, Robinson, Chapell, Nicol) lencsék, nem kizárólagos
sablonok. Üres előkészítésnél is önálló, érdemi vázlatot készíts. Általános
helykitöltő mondat helyett mindig konkrét teológiai tartalom kell.
Belső gondolatmenetedet ne tedd láthatóvá — csak a strukturált JSON eredményt add.

FORRÁSPRIORITÁS (szigorú)

1. Betöltött bibliai szöveg (legmagasabb)
2. Ellenőrizhető eredeti nyelvi adatok (ne találj ki lemmát/Strongöt/igeidőt)
3. Felhasználó jóváhagyott döntései és saját megjegyzései
4. Releváns exegetikai háttéranyag
5. Homiletikai módszerválasztás / műhelyszempontok (lencsék)
6. Vázlatkosár tudatos elemei (opcionális; üres kosár nem hiány)
7. Modell által készített kiegészítő háttér (legalacsonyabb súly)

MŰFAJ ÉS FORMA

A vázlat formáját elsősorban a textus műfaja és mozgása határozza meg:
- érvelő/tanító: természetes expozitív mozgás
- elbeszélés: jelenetek, feszültség, fordulat
- zsoltár/prófétai: képek és gondolati mozgások
- doxológia: teológiai kijelentés → dicsőítő és egzisztenciális megérkezés
- rövid textus: ne gyárts mesterségesen három főpontot
- hosszabb textus: ne zsúfold egyetlen gondolatba
Ha a felhasználó módszert választott, az befolyásolja a ritmust, de eltérhetsz,
ha a textus természetes szerkezete ezt indokolja. A lelkész saját megjegyzéseit
erősebben vedd figyelembe, mint a módszerlencsét.

Az evangéliumi vagy krisztológiai kapcsolat, Krisztus és a kegyelemhorizont
csak akkor jelenjen meg (`christ_grace_connection`), ha textuálisan és
kánonilag indokolható — ne legyen erőltetett.

TILTOTT / TILOS

- fókuszmondat = versidézet vagy annak nagy átfedésű parafrázisa
- textus ismétlése a bevezetésben / minden szakaszban
- önkényes „v. —a” / „v. —b” felosztás
- „Ámen” önálló főpontként (hacsak nincs valódi teológiai indoka)
- helykitöltők: „a textus saját szavai szerint”, „a hallgató konkrét
  felismerésre jut”, „innen vihető tovább a szószéki kibontás”,
  „a teológiai hangsúly abban áll” tartalom nélkül
- nyers Markdown (#, ```, félbehagyott *)
- teljes prédikáció vagy hosszú kommentár
- bizonytalan nyelvi adat kitalálása
- `points` / `subpoints` / `application` / `body` / `thesis` mezők a kimenetben

MOZGÁSOK (2–5, textus szerint)

Általában 3–4 gazdagon kibontott mozgás jobb, mint sok egysoros pont.
Minden mozgás:
- rövid tartalmi title (igehely nélkül)
- verses: pontos textusbeli alap
- textual_insight, theological_emphasis, listener_movement: érdemi, különböző
- original_language_note / poetic_turn: csak ha valóban segít
- transition: csak ha szükséges

MEZŐK

- title / text_reference / scope_note
- focus_sentence: egyetlen saját megfogalmazású, teológiailag pontos mondat
- exegetical_handles: 2–5 rövid kapaszkodó (nem teljes mini-exegézis)
- introduction_direction: hallgatói kérdés/feszültség/kép — nem anekdota,
  nem textusismétlés
- movements
- christ_grace_connection: csak ha textuálisan/kánonilag természetes
- conclusion_direction: teológiai és egzisztenciális megérkezés
- closing_line: tömör zárómondat vagy zárókérdés
- refinement_suggestions: 0–2

Kizárólag JSON-t adj vissza a megadott sémában.
"""

_JSON_SHAPE = """\
{
  "title": "Rövid cím vagy vezérmotívum",
  "text_reference": "Igehely",
  "scope_note": "",
  "focus_sentence": "Saját megfogalmazású fókuszmondat (nem versidézet).",
  "exegetical_handles": ["rövid kapaszkodó 1", "rövid kapaszkodó 2"],
  "introduction_direction": "Hallgatói kérdés / feszültség / kép.",
  "movements": [
    {
      "title": "Mozgás cím igehely nélkül",
      "verses": "v. x–y",
      "textual_insight": "Mit állít / milyen mozgást végez a textus.",
      "theological_emphasis": "Konkrét teológiai súlypont.",
      "listener_movement": "Konkrét hallgatói / pásztori irány.",
      "original_language_note": "",
      "poetic_turn": "",
      "transition": ""
    }
  ],
  "christ_grace_connection": "",
  "conclusion_direction": "Teológiai és egzisztenciális megérkezés.",
  "closing_line": "Tömör zárómondat vagy zárókérdés.",
  "refinement_suggestions": []
}
"""

# Gemini responseSchema — kanonikus movements + v8 mezők.
OUTLINE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "text_reference": {"type": "STRING"},
        "scope_note": {"type": "STRING"},
        "focus_sentence": {"type": "STRING"},
        "exegetical_handles": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "introduction_direction": {"type": "STRING"},
        "movements": {
            "type": "ARRAY",
            "minItems": 2,
            "maxItems": 5,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "verses": {"type": "STRING"},
                    "textual_insight": {"type": "STRING"},
                    "theological_emphasis": {"type": "STRING"},
                    "listener_movement": {"type": "STRING"},
                    "original_language_note": {"type": "STRING"},
                    "poetic_turn": {"type": "STRING"},
                    "transition": {"type": "STRING"},
                },
                "required": [
                    "title",
                    "verses",
                    "textual_insight",
                    "theological_emphasis",
                    "listener_movement",
                ],
            },
        },
        "christ_grace_connection": {"type": "STRING"},
        "conclusion_direction": {"type": "STRING"},
        "closing_line": {"type": "STRING"},
        "refinement_suggestions": {
            "type": "ARRAY",
            "maxItems": 2,
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "title",
        "text_reference",
        "scope_note",
        "focus_sentence",
        "introduction_direction",
        "movements",
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
    if raw.endswith(("…", "...")):
        return True
    if raw.endswith((".", "!", "?", '"', "”", "'")):
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
        val = raw.get(key)
        if val in (None, "", [], {}):
            continue
        if key == "content" and isinstance(val, str) and word_count(val) <= 5:
            continue
        found.append(key)
    for pt in raw.get("points") or raw.get("movements") or []:
        if not isinstance(pt, dict):
            continue
        for key in FORBIDDEN_PAYLOAD_KEYS:
            if key in pt and _s(pt.get(key)):
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
        "engine_version": ENGINE_VERSION,
        "title": "",
        "text_reference": "",
        "scope_note": "",
        "focus_sentence": "",
        "exegetical_handles": [],
        "introduction_direction": "",
        "movements": [],
        "points": [],
        "christ_grace_connection": "",
        "conclusion_direction": "",
        "closing_line": "",
        "refinement_suggestions": [],
    }


def _point_layer_words(pt: Mapping[str, Any]) -> int:
    return sum(word_count(pt.get(k)) for k in POINT_LAYER_KEYS)


def _migrate_point_layers(item: Mapping[str, Any]) -> dict[str, str]:
    """v5 subpoints/application vagy legacy development → három réteg."""
    textual = _s(item.get("textual_insight"))
    theological = _s(item.get("theological_emphasis"))
    listener = _s(item.get("listener_movement"))

    legacy_parts: list[str] = []
    legacy_thesis = _s(
        item.get("thesis") or item.get("core_content") or item.get("body")
    )
    if legacy_thesis:
        legacy_parts.append(legacy_thesis)
    subs_raw = item.get("subpoints")
    if not isinstance(subs_raw, list) or not subs_raw:
        development = item.get("development")
        subs_raw = development if isinstance(development, list) else []
    for x in subs_raw:
        part = _s(x)
        if part and all(_normalize_cmp(part) != _normalize_cmp(p) for p in legacy_parts):
            legacy_parts.append(part)

    application = _s(item.get("application"))
    if not application:
        application = _s(item.get("listener_insight")) or _s(
            item.get("listener_discovery")
        )
    if not application:
        apps = item.get("applications") if isinstance(item.get("applications"), list) else []
        application = _s(apps[0]) if apps else ""

    if not textual and legacy_parts:
        textual = legacy_parts[0]
    if not theological and len(legacy_parts) > 1:
        theological = legacy_parts[1]
    if not listener:
        # Prefer a full third development sentence over a short legacy application.
        if len(legacy_parts) > 2:
            listener = legacy_parts[2]
        elif application:
            listener = application
    elif (
        application
        and word_count(listener) < LIMITS["layer_min_words"]
        and len(legacy_parts) > 2
        and word_count(legacy_parts[2]) >= LIMITS["layer_min_words"]
    ):
        listener = legacy_parts[2]

    if textual and (not theological or not listener):
        sents = _split_sentences(textual)
        if len(sents) >= 3 and not theological and not listener:
            textual, theological, listener = sents[0], sents[1], sents[2]
        elif len(sents) == 2 and not theological:
            textual, theological = sents[0], sents[1]

    return {
        "textual_insight": textual,
        "theological_emphasis": theological,
        "listener_movement": listener,
    }


def normalize_structured_outline(raw: Any) -> dict[str, Any]:
    """AI / legacy payload → kanonikus háromrétegű struktúra."""
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
    handles_raw = raw.get("exegetical_handles") or raw.get("exegetical_notes") or []
    handles: list[str] = []
    if isinstance(handles_raw, list):
        for h in handles_raw:
            hs = _s(h)
            if hs and hs not in handles:
                handles.append(hs)
    out["exegetical_handles"] = handles[:5]
    intro_raw = raw.get("introduction")
    intro = intro_raw if isinstance(intro_raw, dict) else {}
    out["introduction_direction"] = _s(
        raw.get("introduction_direction")
        or intro.get("development")
        or raw.get("opening_direction")
    )
    conc_raw = raw.get("conclusion")
    closing_raw = raw.get("closing")
    conc = conc_raw if isinstance(conc_raw, dict) else {}
    closing = closing_raw if isinstance(closing_raw, dict) else {}
    out["conclusion_direction"] = _s(
        raw.get("conclusion_direction")
        or conc.get("development")
        or closing.get("final_insight")
    )
    out["christ_grace_connection"] = _s(raw.get("christ_grace_connection"))
    out["closing_line"] = _s(
        raw.get("closing_line")
        or conc.get("final_sentence")
        or closing.get("final_sentence")
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

    movements: list[dict[str, Any]] = []
    raw_movements = raw.get("movements")
    if not isinstance(raw_movements, list) or not raw_movements:
        points_raw = raw.get("points")
        raw_movements = points_raw if isinstance(points_raw, list) else []
    assert isinstance(raw_movements, list)
    for i, item in enumerate(raw_movements[: LIMITS["max_points"]], start=1):
        if not isinstance(item, dict):
            continue
        title = re.sub(r"^\s*\d+[.)]\s*", "", _s(item.get("title"))).strip()
        verses = _s(
            item.get("verses")
            or item.get("textual_anchor")
            or item.get("textual_basis")
        )
        layers = _migrate_point_layers(item)
        if not title and not any(layers.values()):
            continue
        transition = _s(item.get("transition"))
        if word_count(transition) > LIMITS["transition_words"]:
            transition = _clip_to_full_sentences(transition, LIMITS["transition_words"])
        movements.append(
            {
                "title": title or f"{i}. mozgás",
                "verses": verses,
                "transition": transition,
                "original_language_note": _s(item.get("original_language_note")),
                "poetic_turn": _s(item.get("poetic_turn")),
                **layers,
            }
        )
    # Kanonikus: movements. points alias a meglévő belső hívásokhoz / tesztekhez.
    out["movements"] = movements
    out["points"] = movements
    out["schema_version"] = SCHEMA_VERSION
    out["engine_version"] = ENGINE_VERSION
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
        if isinstance(raw_tips, list) and len(raw_tips) > LIMITS["refinement_max"]:
            issues.append("too_many_refinements")
        raw_points = payload.get("movements")
        if not isinstance(raw_points, list):
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
                for lk in POINT_LAYER_KEYS:
                    if _looks_multi_paragraph(raw_point.get(lk)):
                        issues.append("multi_paragraph_field")
                        break

    if not data["focus_sentence"]:
        issues.append("missing_focus")
    else:
        fw = word_count(data["focus_sentence"])
        if fw > LIMITS["focus_words"]:
            issues.append("focus_too_long")
        if fw and fw < LIMITS["focus_min_words"]:
            issues.append("focus_too_short")
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
        iw = word_count(intro)
        if iw > LIMITS["intro_words"]:
            issues.append("intro_too_long")
        if iw and iw < LIMITS["intro_min_words"]:
            issues.append("intro_too_short")
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
        textual = _s(pt.get("textual_insight"))
        theological = _s(pt.get("theological_emphasis"))
        listener = _s(pt.get("listener_movement"))
        tnorm = _normalize_cmp(title)
        if not title:
            issues.append("empty_point_title")
        elif word_count(title) > LIMITS["point_title_words"]:
            issues.append("point_title_too_long")
        if any(_normalize_cmp(title) == _normalize_cmp(h) for h in FORBIDDEN_HEADINGS):
            issues.append("forbidden_heading")
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

        if not textual:
            issues.append("missing_textual_insight")
        if not theological:
            issues.append("missing_theological_emphasis")
        if not listener:
            issues.append("missing_listener_movement")

        for key, val in (
            ("textual_insight", textual),
            ("theological_emphasis", theological),
            ("listener_movement", listener),
        ):
            if not val:
                continue
            wc = word_count(val)
            if wc < LIMITS["layer_min_words"]:
                issues.append("stub_layer")
            if wc > LIMITS["layer_max_words"]:
                issues.append("layer_too_long")
            sc = sentence_count(val)
            if sc < 1 or sc > LIMITS["layer_sentences"]:
                issues.append("layer_sentence_count")
            # Ismételt réteg / közhely
            if key != "textual_insight" and textual and _normalize_cmp(val) == _normalize_cmp(
                textual
            ):
                issues.append("repeated_layer_text")
            generic_bits = (
                "a textus isten megtartó szavát",
                "a textus saját mozgása tovább pontosítja",
                "hitbeli felismerésre és válaszra hívja",
            )
            if any(g in val.casefold() for g in generic_bits):
                issues.append("generic_filler")
            template_titles = (
                "a textus megnyitása",
                "a központi állítás",
                "a kegyelmi megérkezés",
            )
            if tnorm in template_titles:
                issues.append("generic_filler")
            if _looks_multi_paragraph(val):
                issues.append("multi_paragraph_point")
            if _looks_truncated_sentence(val):
                issues.append("truncated_sentence")
            if wc > LIMITS["max_prose_block_words"]:
                issues.append("prose_block_too_long")

        layer_total = _point_layer_words(pt)
        if layer_total and layer_total < LIMITS["point_layers_min_words"]:
            issues.append("point_layers_too_short")
        if layer_total > LIMITS["point_layers_max_words"]:
            issues.append("point_layers_too_long")

    for i in range(1, len(verse_labels)):
        a, b = verse_labels[i - 1], verse_labels[i]
        if a and b and a == b:
            issues.append("split_same_verse")

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

    point_blobs = [
        " ".join(
            [
                _s(pt.get("title")),
                _s(pt.get("textual_insight")),
                _s(pt.get("theological_emphasis")),
                _s(pt.get("listener_movement")),
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
        cw = word_count(conc)
        if cw > LIMITS["conclusion_words"]:
            issues.append("conclusion_too_long")
        if cw and cw < LIMITS["conclusion_min_words"]:
            issues.append("conclusion_too_short")
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
    if n <= 2:
        tmin = LIMITS["target_min_2"]
    elif n >= 5:
        tmin = LIMITS["target_min_5"]
    else:
        tmin = LIMITS["target_min_3_4"]
    if total and total < LIMITS["soft_floor_words"]:
        issues.append("too_thin")
    elif total and total < tmin:
        issues.append("under_target")

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
                    # Point bodies are three lines; skip heading+body blocks
                    if not re.match(r"\*\*\d+\.", block.strip()):
                        issues.append("prose_block_too_long")

    blob = rendered.casefold()
    for heading in FORBIDDEN_HEADINGS:
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

    # v8 szemantikai minőségvédelem
    semantic = assess_semantic_quality(data, passage_text=passage_text)
    for code in semantic:
        issues.append(code)

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
    """Felhasználói megjelenés — szószéki jegyzet, mezőcímkékkel."""
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
    handles = data.get("exegetical_handles") or []
    if isinstance(handles, list) and handles:
        handle_lines = "\n".join(f"- {_s(h)}" for h in handles if _s(h))
        if handle_lines:
            _sec("Exegetikai kapaszkodók", handle_lines)
    _sec("Bevezetési irány", data["introduction_direction"])

    for idx, pt in enumerate(data["points"], start=1):
        title = _strip_trailing_verse_from_title(_s(pt.get("title")))
        if not title:
            continue
        verses = _s(pt.get("verses"))
        heading = f"{idx}. {title}"
        if verses:
            heading = f"{heading} ({verses})"
        textual = _s(pt.get("textual_insight"))
        theological = _s(pt.get("theological_emphasis"))
        listener = _s(pt.get("listener_movement"))
        parts: list[str] = []
        if textual:
            parts.append(f"**{textual}**")
        if theological:
            parts.append(theological)
        lang_note = _s(pt.get("original_language_note"))
        if lang_note:
            parts.append(lang_note)
        if listener:
            parts.append(f"*{listener}*")
        poetic = _s(pt.get("poetic_turn"))
        if poetic:
            parts.append(poetic)
        transition = _s(pt.get("transition"))
        if transition:
            parts.append(transition)
        if not parts:
            continue
        blocks.append(f"**{heading}**\n\n" + "\n\n".join(parts))

    christ = _s(data.get("christ_grace_connection"))
    if christ:
        _sec("Krisztus- és kegyelemközpontú összefüggés", christ)
    _sec("Megérkezés", data["conclusion_direction"])
    closing = _s(data.get("closing_line"))
    if closing:
        _sec("Zárómondat", closing)
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
        "final_sentence": _s(data.get("closing_line")),
    }
    closing = dict(outline.get("closing") or {})
    closing["final_insight"] = data["conclusion_direction"]
    if _s(data.get("closing_line")):
        closing["final_sentence"] = _s(data.get("closing_line"))
    outline["closing"] = closing
    if data.get("christ_grace_connection"):
        outline["christ_grace_connection"] = _s(data.get("christ_grace_connection"))
    if data.get("exegetical_handles"):
        outline["exegetical_handles"] = list(data.get("exegetical_handles") or [])
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
        textual = _s(pt.get("textual_insight"))
        theological = _s(pt.get("theological_emphasis"))
        listener = _s(pt.get("listener_movement"))
        verses = _s(pt.get("verses"))
        development = [x for x in (textual, theological, listener) if x]
        item.update(
            {
                "id": f"pt_{i}",
                "title": _s(pt.get("title")),
                "textual_basis": verses,
                "textual_anchor": verses,
                "core_content": textual,
                "development": development,
                "listener_discovery": listener,
                "applications": [listener] if listener else [],
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
    # Új generálás mindig draft (régi needs_refresh seed ne ragadjon rá).
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


def collect_outline_evidence(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Központi evidence csomag — wrapper a meglévő material collectorre."""
    from sermon_workshop_outline_ai import collect_available_sermon_material

    bundle = collect_available_sermon_material(
        session_state, sermon_workshop=sermon_workshop
    )
    # Ne küldjük vissza a régi generált vázlatot mint követendő mintát.
    bundle.pop("sermon_outline", None)
    bundle.pop("outline_manual_notes", None)
    return bundle


def ensure_passage_text_for_outline(
    session_state: MutableMapping[str, Any],
) -> tuple[bool, str]:
    """Igehely + szöveg biztosítása; hiányzó szövegnél RÚF-betöltési kísérlet.

    Returns: (ok, message).
    """
    ref = _s(
        session_state.get("last_igehely")
        or session_state.get("igehely_input")
        or session_state.get("passage_reference")
    )
    if not ref:
        # Widget élő értéke
        ref = _s(session_state.get("igehely_input"))
    if ref and not _s(session_state.get("last_igehely")):
        session_state["last_igehely"] = ref

    text = _s(session_state.get("passage_text"))
    if not text:
        text = _s(session_state.get("passage_text_input"))
        if text:
            session_state["passage_text"] = text

    if ref and text:
        return True, ""
    if not ref:
        return False, (
            "Add meg az igehelyet, majd tölts be RÚF-szöveget "
            "(vagy engedd, hogy a rendszer betöltse)."
        )
    # Van igehely, nincs szöveg → RÚF
    try:
        from ruf_bible_service import fetch_ruf_passage
    except Exception as exc:  # pragma: no cover
        logger.info("ruf_import_failed err=%s", type(exc).__name__)
        return False, (
            "Az igehely megvan, de a bibliai szöveg hiányzik, "
            "és a RÚF-betöltő nem érhető el."
        )
    try:
        result = fetch_ruf_passage(ref)
    except Exception as exc:  # pragma: no cover
        logger.info("ruf_fetch_failed err=%s", type(exc).__name__)
        return False, (
            "Az igehely megvan, de a bibliai szöveg automatikus betöltése nem sikerült. "
            "Illeszd be kézzel a RÚF szöveget."
        )
    if not result.get("success"):
        return False, (
            "Az igehely megvan, de a RÚF-szöveg nem volt betölthető. "
            "Illeszd be kézzel a bibliai szöveget."
        )
    loaded = _s(result.get("text") or result.get("passage_text"))
    if not loaded:
        return False, (
            "Az igehely megvan, de a RÚF-válasz üres volt. "
            "Illeszd be kézzel a bibliai szöveget."
        )
    session_state["passage_text"] = loaded
    session_state["passage_text_input"] = loaded
    if result.get("reference"):
        session_state["last_igehely"] = _s(result.get("reference")) or ref
    session_state["bible_translation"] = _s(
        result.get("translation") or "RÚF 2014"
    ) or "RÚF 2014"
    return True, ""


def _bundle_has_rich_workshop_material(bundle: Mapping[str, Any]) -> bool:
    keys = (
        "exegesis",
        "original_text",
        "theology",
        "history",
        "approved_sermon_decisions",
        "approved_insights",
        "sermon_main_idea",
        "text_main_idea",
        "human_condition",
        "listener_tension",
        "christ_centered_arc",
        "sermon_path",
        "sermon_movements",
    )
    return any(bundle.get(k) not in (None, "", [], {}) for k in keys)


def _generate_rapid_evidence(
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn,
    session: MutableMapping[str, Any],
    context_hash: str,
) -> dict[str, Any] | None:
    """Gyors háttércsomag — cache-elve context_hash alapján."""
    cache = session.get(RAPID_EVIDENCE_SESSION_KEY)
    if not isinstance(cache, dict):
        cache = {}
        session[RAPID_EVIDENCE_SESSION_KEY] = cache
    cached = cache.get(context_hash)
    if isinstance(cached, dict) and cached:
        return cached

    passage = _s(bundle.get("passage_text"))
    ref = _s(bundle.get("passage_reference"))
    if not passage:
        return None
    user_prompt = (
        f"Igehely: {ref}\n\n"
        f"{wrap_untrusted_content('PASSAGE', passage[:6000])}\n\n"
        "Készíts rövid belső háttércsomagot a fenti JSON sémában."
    )
    try:
        try:
            raw = generate_fn(
                user_prompt,
                enable_google_search=False,
                tab_label=TAB_OUTLINE,
                use_cache=False,
                system_bundle=RAPID_EVIDENCE_SYSTEM_PROMPT,
                include_brevity_directive=False,
                max_output_tokens=900,
            )
        except TypeError:
            raw = generate_fn(user_prompt)
    except Exception as exc:  # pragma: no cover
        logger.info("rapid_evidence_failed err=%s", type(exc).__name__)
        return None
    if _is_api_error_text(raw):
        return None
    obj = extract_json_object(raw) or {}
    if not isinstance(obj, dict):
        return None
    try:
        obj = sanitize_ai_json(obj)
    except Exception:
        pass
    pack = {
        "central_claim": _s(obj.get("central_claim")),
        "internal_movement": _s(obj.get("internal_movement")),
        "literary_context": _s(obj.get("literary_context")),
        "historical_notes": _s(obj.get("historical_notes")),
        "language_notes": _s(obj.get("language_notes")),
        "theological_horizon": _s(obj.get("theological_horizon")),
        "homiletical_path": _s(obj.get("homiletical_path")),
    }
    if not any(pack.values()):
        return None
    cache[context_hash] = pack
    session[RAPID_EVIDENCE_SESSION_KEY] = cache
    return pack


def mirror_outline_to_session_strings(
    session_state: MutableMapping[str, Any],
    outline: Mapping[str, Any],
) -> None:
    """Kanonikus vázlat → session outline / outline_draft tükrök (Word-export)."""
    from sermon_workshop_outline_ai import outline_canonical_text

    body = outline_canonical_text(outline)
    if body:
        session_state["outline"] = body
        session_state["outline_draft"] = body


def outline_needs_refresh(
    outline: Any,
    bundle: Mapping[str, Any],
) -> bool:
    safe = normalize_sermon_outline(outline)
    schema = _s(safe.get("schema_version"))
    if schema and schema != SCHEMA_VERSION:
        return True
    if not schema and (
        _s(safe.get("content"))
        or (isinstance(safe.get("movements"), list) and safe.get("movements"))
        or (isinstance(safe.get("structured"), dict) and safe.get("structured"))
    ):
        return True
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
    f"(abszolút felső határ {LIMITS['absolute_max_words']} szó; "
    "a céltartomány minőségi iránymutatás). "
    "Próbáld újra — a gyenge sablon, a textusismétlés vagy a szerkezetileg "
    "hibás vázlat nem kerül mentésre."
)

SCHEMA_REFRESH_NOTICE = (
    "Ez a vázlat korábbi sémával készült. Frissíthető az új motorral; "
    "a meglévő szöveg megmarad, amíg újat nem generálsz."
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
    enriched: bool = False
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


def _passage_verse_chunks(passage: Any) -> list[tuple[str, str]]:
    """Számozott RÚF-sorok → (versjelölés, szöveg) párok."""
    text = _s(passage)
    if not text:
        return []
    chunks: list[tuple[str, str]] = []
    pattern = re.compile(
        r"(?:^|\n)\s*(\d+)\s+([^\n]+(?:\n(?!\s*\d+\s)[^\n]+)*)",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        num = match.group(1)
        body = " ".join(match.group(2).split()).strip()
        if body:
            chunks.append((f"v. {num}", body))
    if chunks:
        return chunks
    # Nincs számozás: teljes szöveg egy egységként
    compact = " ".join(text.split()).strip()
    return [("v. —", compact)] if compact else []


def _distinct_layer(preferred: str, *, banned: set[str], fallback: str) -> str:
    """Réteg szöveg, amely nem ismétli a már használt mondatot és nem sablon."""
    from sermon_workshop_outline_ai import _usable_text

    candidate = _usable_text(preferred) or fallback
    if candidate and not candidate.endswith((".", "!", "?")):
        candidate += "."
    if _normalize_cmp(candidate) in banned:
        candidate = fallback
        if candidate and not candidate.endswith((".", "!", "?")):
            candidate += "."
    banned.add(_normalize_cmp(candidate))
    candidate = _clip_to_full_sentences(candidate, LIMITS["layer_max_words"])
    if candidate and not candidate.endswith((".", "!", "?")):
        candidate += "."
    return candidate


def _heuristic_focus_from_bundle(
    bundle: Mapping[str, Any],
    *,
    seed_outline: Mapping[str, Any] | None = None,
    brief: ExegeticalBrief | None = None,
) -> str:
    """Saját megfogalmazású fókusz — soha ne legyen nyers versidézet."""
    from sermon_workshop_outline_ai import _prefer_main_idea, _usable_text

    focus = _prefer_main_idea(bundle)
    if not focus and seed_outline:
        focus = _s(seed_outline.get("main_idea"))
    if not focus and brief and _s(brief.central_claim):
        claim = _s(brief.central_claim)
        # Ne fogadjuk el, ha a claim maga a passage
        passage = _s(bundle.get("passage_text"))
        from sermon_outline_quality import focus_is_passage_quote

        if not focus_is_passage_quote(claim, passage):
            focus = claim
    if not focus and brief and _s(brief.theological_emphasis):
        focus = _s(brief.theological_emphasis)
    if not focus:
        ref = _s(bundle.get("passage_reference"))
        genre = ""
        if brief:
            genre = _s(brief.genre_and_movement).casefold()
        if "doxológ" in genre or "júd" in ref.casefold():
            focus = (
                "Az egyedüli üdvözítő Isten képes megőrizni a botlástól, "
                "és feddhetetlenül, örömmel állít dicsősége elé."
            )
        else:
            focus = (
                "A textus Isten cselekvését állítja a középpontba, "
                "és a hallgatót hitbeli felismerésre hívja a szakasz saját mozgása szerint."
            )
    focus = _usable_text(focus) or focus
    # Ha mégis passage-idézet lenne, cseréljük
    from sermon_outline_quality import focus_is_passage_quote

    passage = _s(bundle.get("passage_text"))
    if focus and passage and focus_is_passage_quote(focus, passage):
        focus = (
            "A szakasz központi teológiai állítása Isten cselekvése körül forog, "
            "és a hallgatót a textus saját mozgása szerint hívja válaszra."
        )
    # Csak szintetikus fókusznál erőltessünk zárójelet; a jóváhagyott főgondolatot ne írjuk át.
    synthetic = focus.startswith("A szakasz központi") or focus.startswith(
        "Az egyedüli üdvözítő"
    ) or focus.startswith("A textus Isten")
    if focus and synthetic and not focus.endswith((".", "!", "?")):
        focus += "."
    return _clip_to_full_sentences(focus, LIMITS["focus_words"])


def _heuristic_structured_from_bundle(
    bundle: Mapping[str, Any],
    *,
    seed_outline: Mapping[str, Any] | None = None,
    brief: ExegeticalBrief | None = None,
) -> dict[str, Any]:
    """Offline / teszt: szószéki vázlat — sablon és versidézet nélkül."""
    from sermon_workshop_outline_ai import (
        _truncate,
        _usable_text,
    )

    data = empty_structured_outline()
    data["text_reference"] = _s(bundle.get("passage_reference"))
    data["title"] = _s(bundle.get("project_title")) or data["text_reference"] or "Vázlat"
    if word_count(data["title"]) > LIMITS["title_words"]:
        data["title"] = " ".join(data["title"].split()[: LIMITS["title_words"]])

    passage = _s(bundle.get("passage_text"))
    verse_chunks = _passage_verse_chunks(passage)
    data["focus_sentence"] = _heuristic_focus_from_bundle(
        bundle, seed_outline=seed_outline, brief=brief
    )

    if brief:
        data["exegetical_handles"] = brief.handles_for_outline(max_items=5)

    lt_raw = bundle.get("listener_tension")
    path_raw = bundle.get("sermon_path")
    lt = lt_raw if isinstance(lt_raw, dict) else {}
    path = path_raw if isinstance(path_raw, dict) else {}
    intro = (
        _usable_text(path.get("starting_point"))
        or _usable_text(lt.get("listener_question"))
        or (brief.internal_tension if brief else "")
        or (
            "A hallgató gyakran a saját bizonytalanságából indul, amikor Isten "
            "megtartó ígérete elé áll. A kérdés az, milyen emberi feszültség "
            "nyitja meg természetesen ezt az igeszakaszt a gyülekezet előtt."
        )
    )
    data["introduction_direction"] = _clip_to_full_sentences(
        _truncate(intro, 700), LIMITS["intro_words"]
    )

    points: list[dict[str, Any]] = []
    movements = (
        bundle.get("sermon_movements")
        if isinstance(bundle.get("sermon_movements"), list)
        else []
    )
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
    used_layers: set[str] = set()

    def _one_layer(text: str, *, fallback: str) -> str:
        return _distinct_layer(text, banned=used_layers, fallback=fallback)

    genre = _s(brief.genre_and_movement).casefold() if brief else ""
    is_doxology = "doxológ" in genre or "júd" in data["text_reference"].casefold()

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
            # Ámen ne legyen főpont
            if re.match(r"^\s*(az\s+)?ámen\.?\s*$", title, flags=re.I):
                continue
            basis = _usable_text(mv.get("textual_basis")) or _usable_text(
                mv.get("textual_anchor")
            )
            if basis and extract_verse_numbers(basis) and len(basis) > 24:
                nums = sorted(extract_verse_numbers(basis))
                if len(nums) == 1:
                    basis = f"v. {nums[0]}"
                elif nums:
                    basis = f"v. {nums[0]}–{nums[-1]}"
            points.append(
                {
                    "title": title,
                    "verses": basis or "",
                    "textual_insight": _one_layer(
                        core or exe or (insights[0] if insights else ""),
                        fallback=(
                            "A textus ebben a szakaszban Isten cselekvését állítja "
                            "előtérbe, és a gondolat a kiválasztott versekhez kötődik."
                        ),
                    ),
                    "theological_emphasis": _one_layer(
                        _usable_text(mv.get("listener_discovery"))
                        or (insights[1] if len(insights) > 1 else "")
                        or original
                        or exe
                        or "",
                        fallback=(
                            "Isten cselekvése hív választ, nem az emberi erőfeszítés; "
                            "ez adja a szakasz teológiai súlyát."
                        ),
                    ),
                    "listener_movement": _one_layer(
                        (insights[2] if len(insights) > 2 else "")
                        or (decisions[0] if decisions else "")
                        or "",
                        fallback=(
                            "A hallgató kérdezheti, hol kell ezt a mozgást "
                            "személyesen komolyan vennie a gyülekezet életében."
                        ),
                    ),
                }
            )
    elif is_doxology and verse_chunks:
        # Doxológia: 2 természetes mozgás (v. 24 megtartás+eléállás, v. 25 dicsőítés)
        points.append(
            {
                "title": "Megőrzés és eléállás",
                "verses": verse_chunks[0][0] if verse_chunks else "v. 24",
                "textual_insight": _one_layer(
                    (
                        "Isten megtartó cselekvése áll a középpontban: képes "
                        "megőrizni a botlástól, és feddhetetlenül, örömmel állít "
                        "dicsősége elé."
                    ),
                    fallback="A doxológia Isten megtartó és dicsőséges cselekvését bontja ki.",
                ),
                "theological_emphasis": _one_layer(
                    (
                        brief.theological_emphasis
                        if brief and brief.theological_emphasis
                        else ""
                    )
                    or exe
                    or "",
                    fallback=(
                        "A bizalom forrása Isten hatalma és üdvözítő egyedülvalósága, "
                        "nem a hallgató állhatatossága."
                    ),
                ),
                "listener_movement": _one_layer(
                    (brief.listener_connection if brief else "") or "",
                    fallback=(
                        "A gyülekezet botlásfélelmeit Isten megtartó ígéretére "
                        "bízhatja, és a dicsőítés felé mozdulhat."
                    ),
                ),
            }
        )
        points.append(
            {
                "title": "Dicsőítés az egyedüli üdvözítő Istennek",
                "verses": verse_chunks[-1][0] if verse_chunks else "v. 25",
                "textual_insight": _one_layer(
                    (
                        "A doxológia az egyedüli üdvözítő Isten dicsőségét, "
                        "fenségét és hatalmát hirdeti Jézus Krisztus által."
                    ),
                    fallback="A szakasz a dicsőítésben érkezik meg.",
                ),
                "theological_emphasis": _one_layer(
                    "",
                    fallback=(
                        "Az üdvözítés és a dicsőség Krisztus által kötődik Istenhez."
                    ),
                ),
                "listener_movement": _one_layer(
                    "",
                    fallback=(
                        "A hála Krisztusra irányul, nem általános vallásos magasztalásra."
                    ),
                ),
            }
        )
    elif verse_chunks:
        # Természetes versblokkok — NINCS a/b hasítás
        def _body_usable(raw_body: str) -> str:
            text = " ".join(_s(raw_body).split()).strip()
            if text.endswith(("…", "...")):
                text = text.rstrip("….").rstrip()
            if text and not text.endswith((".", "!", "?")):
                text += "."
            return text

        units: list[tuple[str, str]] = [
            (label, _body_usable(body))
            for label, body in verse_chunks
            if _body_usable(body)
            and not re.search(r"^\s*ámen\.?\s*$", body, flags=re.I)
        ]
        if not units and verse_chunks:
            label, body = verse_chunks[0]
            units = [
                (
                    label,
                    _body_usable(body)
                    or "A textus Isten szavát szólítja a hallgatóhoz.",
                )
            ]
        # Ha csak 1 egység van, 2 teológiai mozgás — nem félvers-split
        if len(units) == 1:
            units = [
                (units[0][0], units[0][1]),
                (
                    units[0][0],
                    "Ugyanez a szakasz a hallgató válaszát is rendezi Isten "
                    "cselekvése felől.",
                ),
            ]
        n = min(max(len(units), 2), LIMITS["max_points"])
        if len(units) > n:
            if n == 2:
                units = [units[0], units[-1]]
            else:
                step = max(1, len(units) // n)
                picked = [units[i * step] for i in range(n - 1)]
                picked.append(units[-1])
                units = picked[:n]
        for i, (verses, body) in enumerate(units):
            # Ne ismételd a teljes body-t a rétegekben
            title_words = body.split()[:6]
            title = " ".join(title_words).rstrip(".,;:")
            if word_count(title) > LIMITS["point_title_words"]:
                title = " ".join(title.split()[: LIMITS["point_title_words"]])
            if any(_normalize_cmp(title) == _normalize_cmp(p["title"]) for p in points):
                title = f"{i + 1}. mozgás"
            summary = _clip_to_full_sentences(body, 28)
            points.append(
                {
                    "title": title or f"{i + 1}. mozgás",
                    "verses": verses,
                    "textual_insight": _one_layer(
                        (
                            f"Ebben a szakaszban a textus ezt a mozgást végzi: {summary}"
                        ),
                        fallback=(
                            "A textus ebben a szakaszban Isten cselekvését bontja ki "
                            "a betöltött igeszakasz alapján."
                        ),
                    ),
                    "theological_emphasis": _one_layer(
                        exe or original or "",
                        fallback=(
                            "A teológiai súly Isten cselekvéében van, amely "
                            "rendezi a közösség helyzetét a szöveg szerint."
                        ),
                    ),
                    "listener_movement": _one_layer(
                        history or (decisions[0] if decisions else "") or "",
                        fallback=(
                            "A hallgató e szakasz előtt kérdezheti, hol érint "
                            "őt személyesen Istennek ez a cselekvése."
                        ),
                    ),
                }
            )
    else:
        seeds = insights or decisions or [
            exe[:220] if exe else "",
            original[:220] if original else "",
            data["focus_sentence"],
        ]
        seeds = [s for s in seeds if s] or [data["focus_sentence"]]
        while len(seeds) < 2:
            seeds.append(
                "A textus további mozgása pontosítja a hallgató felismerését Isten cselekvése felől."
            )
        titles = (
            "A szakasz megnyílása",
            "A központi állítás kibontása",
            "A hallgatói megérkezés",
        )
        loaded = sorted(extract_verse_numbers(bundle.get("passage_text") or ""))
        count = min(max(len(seeds), 2), 3)
        if len(loaded) >= count:
            verse_labels = [
                f"v. {loaded[min(i, len(loaded) - 1)]}" for i in range(count)
            ]
        else:
            verse_labels = [""] * count
        for i in range(count):
            body = seeds[i % len(seeds)]
            points.append(
                {
                    "title": titles[i] if i < len(titles) else f"{i + 1}. mozgás",
                    "verses": verse_labels[i],
                    "textual_insight": _one_layer(
                        body,
                        fallback=(
                            "A textus ebben a szakaszban Isten cselekvését bontja ki "
                            "a betöltött igeszakasz alapján."
                        ),
                    ),
                    "theological_emphasis": _one_layer(
                        exe or original or "",
                        fallback=(
                            "A teológiai súly Isten cselekvéében van, amely "
                            "rendezi a hallgató helyzetét."
                        ),
                    ),
                    "listener_movement": _one_layer(
                        history or "",
                        fallback=(
                            "A hallgató így konkrét felismerésre juthat anélkül, "
                            "hogy moralizáló felszólítást kapna."
                        ),
                    ),
                }
            )

    data["points"] = points[: LIMITS["max_points"]]
    closing_raw = bundle.get("closing")
    arc_raw = bundle.get("christ_centered_arc")
    closing = closing_raw if isinstance(closing_raw, dict) else {}
    arc = arc_raw if isinstance(arc_raw, dict) else {}
    if is_doxology:
        default_conc = (
            "A doxológia Isten megtartó hatalmát és dicsőségét állítja a középpontba: "
            "a hallgató nem saját teljesítményénél, hanem az egyedüli üdvözítő Isten "
            "elé állva érkezik meg."
        )
        data["christ_grace_connection"] = (
            _usable_text(arc.get("grace_enabled_response"))
            or "A megtartás és a dicsőítés Jézus Krisztus által kötődik Istenhez."
        )
        data["closing_line"] = (
            "Állhatunk-e ma is abban a bizonyosságban, hogy Ő őriz és elé állít?"
        )
    else:
        default_conc = (
            "A hallgató nem új témánál, hanem a textus megérkezésénél áll meg. "
            "Isten cselekvése hív válaszra a gyülekezet konkrét helyzetében."
        )
    conc = (
        _usable_text(closing.get("final_discovery"))
        or _usable_text(arc.get("grace_enabled_response"))
        or default_conc
    )
    data["conclusion_direction"] = _clip_to_full_sentences(
        _truncate(conc, 700), LIMITS["conclusion_words"]
    )
    if not data.get("closing_line"):
        data["closing_line"] = _clip_to_full_sentences(
            data["conclusion_direction"], 28
        )
    data["refinement_suggestions"] = []
    return normalize_structured_outline(data)


def _ai_generate_structured(
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn,
    seed_outline: Mapping[str, Any] | None = None,
    mode: str = "standard",
    context_mode: str = "",
    brief: ExegeticalBrief | None = None,
) -> tuple[dict[str, Any] | None, list[str], int]:
    """Returns (structured|None, warnings, raw_rendered_word_count)."""
    warnings: list[str] = []
    sections = bundle.get("outline_context_sections")
    if not isinstance(sections, dict):
        sections = {
            k: v
            for k, v in bundle.items()
            if not str(k).startswith("_")
            and k
            not in {
                "outline_basket",
                "sermon_outline",
                "outline_manual_notes",
                "outline_context_sections",
            }
        }
    outline_basket = bundle.get("outline_basket") or []
    ctx_mode = context_mode or _s(bundle.get("context_mode")) or "PARTIAL"
    task_mode_note = (
        "ÚJ GYORSVÁZLAT: készíts önálló vázlatot a textusból; "
        "a rendelkezésre álló műhelyanyagot csak szelektív háttérként használd."
        if mode == "quick"
        else "ÚJ MŰHELYVÁZLAT: készíts önálló vázlatot a textusból; "
        "a lelkész jóváhagyott döntéseit mérlegeld, de ne másold mechanikusan."
    )
    mode_guidance = {
        "BARE": (
            "MÓD: BARE — csak igehely és bibliai szöveg (+ belső mini-exegézis). "
            "Készíts önálló, érdemi vázlatot; ne jelezd a hiányt."
        ),
        "PARTIAL": (
            "MÓD: PARTIAL — van némi exegetikai/homiletikai anyag. "
            "Használd, és egészítsd ki a hiányzó részeket."
        ),
        "RICH": (
            "MÓD: RICH — válogass és szerkessz a meglévő anyagból; "
            "ne másold vagy foglald össze mechanikusan. "
            "Az irreleváns vagy ellentmondó elemeket hagyd el."
        ),
    }.get(ctx_mode, "")
    brief_block = ""
    if brief is not None:
        brief_block = (
            "BELSŐ EXEGETICAL BRIEF (ne másold teljes terjedelmében; "
            "csak a hasznos kapaszkodókat emeld a vázlatba):\n"
            f"{json.dumps(brief.to_dict(), ensure_ascii=False)}\n\n"
        )
    method_note = ""
    prefs = sections.get("homiletical_preferences") if isinstance(sections, dict) else {}
    if isinstance(prefs, dict) and prefs.get("method_lens"):
        method_note = (
            f"HOMILETIKAI LENCSE (nem kötelező sablon): {prefs.get('method_lens')}\n"
        )
    prompt = (
        f"{task_mode_note}\n"
        f"{mode_guidance}\n"
        f"SÉMAVERZIÓ: {SCHEMA_VERSION}\n"
        f"{method_note}"
        "A feladat új szószéki munkavázlat készítése.\n"
        "Forrásprioritás: bibliai textus → eredeti nyelvi adat → felhasználói "
        "döntések → exegetikai háttér → homiletikai lencsék → modell-kiegészítő.\n"
        "A textus műfaja és mozgása határozza meg a formát (2–5 mozgás).\n"
        "A fókuszmondat saját megfogalmazású legyen — ne versidézet.\n"
        "Ne használj helykitöltő mondatokat; ne bontsd önkényesen a/b félversekre; "
        "az Ámen ne legyen önálló főpont.\n\n"
        f"{brief_block}"
        "STRUKTURÁLT FORRÁSOK (típusozott szakaszok):\n"
        f"{wrap_untrusted_content('outline_context', json.dumps(sections, ensure_ascii=False), limit_name='prompt_context_total')}\n\n"
        f"{wrap_untrusted_content('vázlatkosár', json.dumps(outline_basket or [], ensure_ascii=False), limit_name='basket_total')}\n\n"
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
        warnings.append("Érvénytelen JSON vázlatválasz.")
        logger.info(
            "outline_invalid_json schema=%s raw_words=%s",
            SCHEMA_VERSION,
            word_count(raw or ""),
        )
        return None, warnings, word_count(raw or "")
    cleaned = sanitize_ai_json(
        obj,
        allowed_keys={
            "title",
            "text_reference",
            "scope_note",
            "focus_sentence",
            "exegetical_handles",
            "introduction_direction",
            "points",
            "movements",
            "christ_grace_connection",
            "conclusion_direction",
            "closing_line",
            "refinement_suggestions",
            "schema_version",
            "subpoints",
            "application",
            "textual_insight",
            "theological_emphasis",
            "listener_movement",
            "original_language_note",
            "poetic_turn",
            "transition",
            "verses",
        },
    )
    if cleaned is None:
        warnings.append("A vázlat JSON biztonsági szűrése sikertelen.")
        return None, warnings, word_count(raw or "")
    structured = normalize_structured_outline(cleaned)
    # Brief kapaszkodók, ha az AI üresen hagyta
    if brief and not structured.get("exegetical_handles"):
        structured["exegetical_handles"] = brief.handles_for_outline(max_items=5)
    raw_wc = word_count(render_structured_outline(structured))
    logger.info(
        "outline_ai_raw schema=%s mode=%s rendered_words=%s forbidden=%s",
        SCHEMA_VERSION,
        ctx_mode,
        raw_wc,
        _has_forbidden_keys(obj),
    )
    return structured, warnings, raw_wc


def _repair_structured(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Egyetlen célzott javító hívás a feltárt hibákra."""
    warnings: list[str] = []
    slim = normalize_structured_outline(payload)
    prompt = build_repair_prompt(
        issues=issues,
        outline_json=json.dumps(slim, ensure_ascii=False),
        passage_reference=_s(bundle.get("passage_reference")),
        bible_text=_s(bundle.get("passage_text")),
        json_shape=_JSON_SHAPE,
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Célzott javítás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A célzott javítás API-hibát jelzett.")
        return None, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen javító válasz.")
        return None, warnings
    return normalize_structured_outline(obj), warnings


def _repair_source_context(bundle: Mapping[str, Any], *, rich: bool = False) -> dict[str, Any]:
    """Passage-only for compress; richer support material for enrich."""
    ctx: dict[str, Any] = {
        "passage_reference": bundle.get("passage_reference", ""),
        "passage_text": bundle.get("passage_text", ""),
        "bible_translation": bundle.get("bible_translation", ""),
    }
    if not rich:
        return ctx

    def _clip(value: Any, n: int) -> str:
        text = _s(value)
        return text if len(text) <= n else text[: n - 1].rstrip() + "…"

    for key, cap in (
        ("exegesis", 1200),
        ("original_text", 800),
        ("history", 600),
        ("theology", 800),
        ("user_focus", 400),
        ("text_main_idea", 400),
        ("sermon_main_idea", 400),
    ):
        val = _clip(bundle.get(key), cap)
        if val:
            ctx[key] = val
    basket = bundle.get("outline_basket") or bundle.get("basket") or []
    if isinstance(basket, list) and basket:
        clipped: list[Any] = []
        for item in basket[:8]:
            if isinstance(item, Mapping):
                clipped.append(
                    {
                        k: _clip(item.get(k), 240)
                        for k in ("title", "text", "note", "content", "label")
                        if _s(item.get(k))
                    }
                )
            else:
                clipped.append(_clip(item, 240))
        ctx["outline_basket"] = clipped
    return ctx


def _compress_structured(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    repair_context = _repair_source_context(bundle, rich=False)
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


def _enrich_structured(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    repair_context = _repair_source_context(bundle, rich=True)
    slim = normalize_structured_outline(payload)
    prompt = (
        f"{ENRICH_INSTRUCTION}\n"
        f"SÉMAVERZIÓ: {SCHEMA_VERSION}\n"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n"
        "Őrizd a pontok számát és az igehely-beosztást; egészítsd ki a három "
        "réteget és a keretmondatokat a forrásból. Cél: 450–750 szó; "
        "ne lépd át a 850 szót.\n\n"
        f"FORRÁS (mélyítéshez):\n{json.dumps(repair_context, ensure_ascii=False)}\n\n"
        f"MÉLYÍTENDŐ VÁZLAT:\n{json.dumps(slim, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.35)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Mélyítő javítás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A mélyítő javítás API-hibát jelzett.")
        return None, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen mélyítő válasz.")
        return None, warnings
    logger.info(
        "outline_enrich schema=%s rendered_words=%s",
        SCHEMA_VERSION,
        word_count(render_structured_outline(normalize_structured_outline(obj))),
    )
    return normalize_structured_outline(obj), warnings


def _programmatic_trim(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Könnyű tisztítás — csak abszolút felső határ felett agresszívebb; félmondat nélkül."""
    data = normalize_structured_outline(payload)

    data["title"] = _strip_trailing_verse_from_title(data["title"])
    if word_count(data["title"]) > LIMITS["title_words"]:
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
        layers: dict[str, str] = {}
        for key in POINT_LAYER_KEYS:
            cleaned = _s(pt.get(key))
            if "\n\n" in cleaned:
                cleaned = cleaned.split("\n\n")[0].strip()
            cleaned = _clip_to_full_sentences(cleaned, LIMITS["layer_max_words"])
            sents = _split_sentences(cleaned)[: LIMITS["layer_sentences"]]
            cleaned = " ".join(sents).strip()
            if cleaned and _looks_truncated_sentence(cleaned):
                first = _split_sentences(cleaned)
                cleaned = first[0] if first else cleaned
            layers[key] = cleaned
        trimmed_points.append(
            {
                "title": title,
                "verses": _s(pt.get("verses")),
                **layers,
            }
        )
    data["points"] = trimmed_points
    data["refinement_suggestions"] = []

    def _over() -> bool:
        return word_count(render_structured_outline(data)) > LIMITS["absolute_max_words"]

    # Csak 850+ szó esetén rövidíts programatikusan (AI compress utáni biztonsági háló).
    if _over():
        data["introduction_direction"] = _clip_to_full_sentences(
            data["introduction_direction"], 60
        )
        data["conclusion_direction"] = _clip_to_full_sentences(
            data["conclusion_direction"], 60
        )
        data["focus_sentence"] = _clip_to_full_sentences(data["focus_sentence"], 35)
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

    passage_ok, passage_msg = ensure_passage_text_for_outline(session)
    if not passage_ok:
        return OutlineGenerationResult(
            outline=normalize_sermon_outline(sw.get("sermon_outline")),
            ok=False,
            error_message=passage_msg or EMPTY_PROJECT_MESSAGE,
            source=source_tag,
        )

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

    # Strukturált kontextus (típusozott források + BARE/PARTIAL/RICH)
    outline_ctx = build_outline_context(
        session,
        sermon_workshop=sw,
        include_original_language=True,
    )
    bundle = outline_context_to_legacy_bundle(outline_ctx)
    # Hash a collect_available-kompatibilis csomagon (passage fill ELŐTT),
    # különben a nyers session-szöveg és a tisztított collect eltérne.
    ctx_hash = compute_context_hash(bundle)
    warnings: list[str] = []
    compressed = False
    enriched = False
    raw_wc = 0
    used_ai = False

    raw_passage = _s(session.get("passage_text")) or _s(
        session.get("passage_text_input")
    )
    if raw_passage and not _s(bundle.get("passage_text")):
        bundle["passage_text"] = raw_passage
        outline_ctx.bible_text = raw_passage
        keys = list(bundle.get("source_keys") or [])
        if "passage_text" not in keys:
            keys.append("passage_text")
        bundle["source_keys"] = keys

    # Közös exegetikai mag — ha van érvényes cache (pl. Eredeti szöveg fül),
    # azt használjuk; különben determinisztikus magot építünk.
    # Szándékosan NEM a vázlat generate_fn-jét adjuk át: az outline JSON
    # séma és a core séma külön hívás; a mag AI-szintézise az eredeti
    # szöveg panelen történik.
    invalidate_core_if_stale(
        session,
        reference=outline_ctx.passage_reference,
        bible_text=outline_ctx.bible_text or raw_passage,
    )
    brief: ExegeticalBrief | None = None
    try:
        core = ensure_exegetical_core(
            session,
            reference=outline_ctx.passage_reference,
            bible_text=outline_ctx.bible_text or raw_passage,
            generate_fn=None,
            enrich=False,
            force_refresh=False,
            # Ne írjuk felül a felületi original_text-et a vázlat futásakor —
            # különben hamis needs_refresh lenne a context_hash miatt.
            sync_original_text=False,
        )
        brief = core_to_outline_brief(core)
    except Exception as exc:
        logger.info("shared_exegetical_core_failed err=%s", type(exc).__name__)
        brief = generate_exegetical_brief(outline_ctx, generate_fn=None)

    if (
        generate_fn is not None
        and brief is None
        and outline_ctx.context_mode in {ContextMode.BARE, ContextMode.PARTIAL}
        and not _bundle_has_rich_workshop_material(bundle)
    ):
        rapid = _generate_rapid_evidence(
            bundle,
            generate_fn=generate_fn,
            session=session,
            context_hash=ctx_hash,
        )
        if rapid:
            bundle["rapid_evidence"] = rapid
            outline_ctx.rapid_evidence = rapid
            bundle = outline_context_to_legacy_bundle(outline_ctx)
            keys = list(bundle.get("source_keys") or [])
            if "rapid_evidence" not in keys:
                keys.append("rapid_evidence")
            bundle["source_keys"] = keys

    seed = build_outline_from_workshop(session, sermon_workshop=sw)
    structured: dict[str, Any] | None = None

    if generate_fn is not None:
        structured, ai_warnings, raw_wc = _ai_generate_structured(
            bundle,
            generate_fn=generate_fn,
            seed_outline=seed,
            mode=mode,
            context_mode=outline_ctx.context_mode.value,
            brief=brief,
        )
        warnings.extend(ai_warnings)
        used_ai = structured is not None
    if structured is None:
        # AI hiány / hiba: heurisztika csak offline (nincs generate_fn) esetén
        # érvényes eredményként; AI-s sikertelenségnél később reject.
        structured = _heuristic_structured_from_bundle(
            bundle, seed_outline=seed, brief=brief
        )

    passage_for_validation = bundle.get("passage_text") or ""

    def _hard_issues(items: list[str]) -> list[str]:
        return [
            i
            for i in items
            if i not in ENRICHABLE_ISSUES and i not in SOFT_QUALITY_ISSUES
        ]

    def _soft_final_issues(items: list[str]) -> list[str]:
        return [i for i in items if i in SOFT_QUALITY_ISSUES]

    def _needs_compress(items: list[str]) -> bool:
        return any(i in COMPRESS_TRIGGER_ISSUES for i in items)

    def _needs_enrich(items: list[str]) -> bool:
        return any(i in ENRICHABLE_ISSUES for i in items)

    def _needs_repair(items: list[str]) -> bool:
        return any(i in REPAIRABLE_ISSUES or i in SEMANTIC_HARD_ISSUES for i in items)

    issues = validate_structured_outline(
        structured, passage_text=passage_for_validation
    )
    if raw_wc > LIMITS["absolute_max_words"] and "over_absolute_max" not in issues:
        issues = list(issues) + ["over_absolute_max"]

    # Egy célzott javító hívás szemantikai / formai hibákra (nem végtelen loop)
    repaired_once = False
    if (
        generate_fn is not None
        and used_ai
        and _needs_repair(issues)
        and not _needs_compress(issues)
    ):
        repaired, r_warn = _repair_structured(
            structured, bundle, issues=issues, generate_fn=generate_fn
        )
        warnings.extend(r_warn)
        repaired_once = True
        if repaired is not None:
            structured = repaired
            issues = validate_structured_outline(
                structured, passage_text=passage_for_validation
            )
        logger.info(
            "outline_after_repair schema=%s issues=%s words=%s",
            SCHEMA_VERSION,
            issues,
            word_count(render_structured_outline(structured)),
        )

    # Tömörítés CSAK abszolút felső határ / prédikációjelleg esetén
    if _needs_compress(issues) and generate_fn is not None:
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
        if _needs_compress(issues) or _hard_issues(issues):
            rendered_wc = word_count(render_structured_outline(structured))
            return OutlineGenerationResult(
                outline=existing,
                ok=False,
                error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
                warnings=warnings,
                validation_issues=issues,
                source=source_tag,
                compressed=True,
                enriched=enriched,
                raw_word_count=raw_wc,
                rendered_word_count=rendered_wc,
            )

    # Tartalmi kiegészítés sovány rétegeknél (ha még nem volt repair)
    if (
        generate_fn is not None
        and used_ai
        and not repaired_once
        and not _needs_compress(issues)
        and _needs_enrich(issues)
    ):
        deepened, e_warn = _enrich_structured(
            structured, bundle, issues=issues, generate_fn=generate_fn
        )
        warnings.extend(e_warn)
        enriched = True
        if deepened is not None:
            structured = deepened
            issues = validate_structured_outline(
                structured, passage_text=passage_for_validation
            )
        leftover_hard = [
            i
            for i in issues
            if i
            in {
                "missing_textual_insight",
                "missing_theological_emphasis",
                "missing_listener_movement",
                "truncated_sentence",
            }
        ]
        if _hard_issues(issues) or leftover_hard:
            rendered_wc = word_count(render_structured_outline(structured))
            return OutlineGenerationResult(
                outline=existing,
                ok=False,
                error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
                warnings=warnings,
                validation_issues=issues,
                source=source_tag,
                compressed=compressed,
                enriched=True,
                raw_word_count=raw_wc,
                rendered_word_count=rendered_wc,
            )

    # AI volt, de a válasz érvénytelen maradt → ne mentsünk gyenge sablont
    if generate_fn is not None and not used_ai:
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
            warnings=warnings + ["Az AI nem adott érvényes JSON vázlatot."],
            validation_issues=issues,
            source=source_tag,
            raw_word_count=raw_wc,
        )

    structured = _programmatic_trim(structured)
    issues = validate_structured_outline(
        structured, passage_text=passage_for_validation
    )

    rendered_wc = word_count(render_structured_outline(structured))

    # Soft quality flags (too_thin / under_target) → warning, keep if otherwise valid
    for soft in _soft_final_issues(issues):
        tip = f"Vázlat minőség: {soft}"
        if tip not in warnings:
            warnings.append(tip)

    # Hard reject: struktúra-/forma-hibák. Enrichable hossz/réteg soft warning a végén.
    post_hard = [
        i
        for i in issues
        if i not in SOFT_QUALITY_ISSUES and i not in ENRICHABLE_ISSUES
    ]
    # AI után: félbemaradt mondat mindig hard reject
    if used_ai and "truncated_sentence" in issues:
        post_hard.append("truncated_sentence")
    for softish in issues:
        if softish in ENRICHABLE_ISSUES and softish not in SOFT_QUALITY_ISSUES:
            tip = f"Vázlat minőség: {softish}"
            if tip not in warnings:
                warnings.append(tip)
    if generate_fn is not None and post_hard:
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
            enriched=enriched,
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
            enriched=enriched,
            raw_word_count=raw_wc,
        )

    final_wc = word_count(outline.get("content") or render_structured_outline(structured))
    logger.info(
        "outline_ok schema=%s source=%s rendered_words=%s compressed=%s enriched=%s",
        SCHEMA_VERSION,
        source_tag,
        final_wc,
        compressed,
        enriched,
    )
    return OutlineGenerationResult(
        outline=outline,
        ok=True,
        warnings=warnings,
        validation_issues=[],
        source=source_tag or "workshop",
        overwritten_manual_edit=bool(manually_edited and force_overwrite),
        compressed=compressed,
        enriched=enriched,
        raw_word_count=raw_wc,
        rendered_word_count=final_wc,
    )


__all__ = [
    "COMPRESS_INSTRUCTION",
    "COMPRESS_TRIGGER_ISSUES",
    "ENRICH_INSTRUCTION",
    "ENRICHABLE_ISSUES",
    "ENGINE_VERSION",
    "FORBIDDEN_HEADINGS",
    "FORBIDDEN_PAYLOAD_KEYS",
    "INVALID_OUTLINE_MESSAGE",
    "LEGACY_SCHEMA_VERSIONS",
    "LIMITS",
    "OUTLINE_MAX_OUTPUT_TOKENS",
    "OUTLINE_RESPONSE_SCHEMA",
    "OUTLINE_SYSTEM_PROMPT",
    "RAPID_EVIDENCE_SYSTEM_PROMPT",
    "REFRESH_NOTICE",
    "REPAIRABLE_ISSUES",
    "SCHEMA_REFRESH_NOTICE",
    "SCHEMA_VERSION",
    "SOFT_QUALITY_ISSUES",
    "OutlineGenerationResult",
    "collect_outline_evidence",
    "compute_context_hash",
    "ensure_passage_text_for_outline",
    "extract_verse_numbers",
    "generate_sermon_outline",
    "mirror_outline_to_session_strings",
    "normalize_structured_outline",
    "outline_needs_refresh",
    "render_structured_outline",
    "scope_note_uses_unloaded_verse",
    "sermon_outline_to_structured",
    "structured_to_sermon_outline",
    "validate_structured_outline",
    "word_count",
]
