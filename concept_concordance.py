"""Konkordancia — 3. mód: kérdés/fogalom alapú keresés.

A felhasználó egy összetett, teológiai/fogalmi kérdést tesz fel (nem egy
szót vagy kifejezést) — pl. "hol beszél a Biblia arról, hogy a
megbocsátás nem mindig automatikus, hanem feltételekhez kötött?". Ez a
modul EGY Gemini-hívással (`app.generate_text`, strukturált JSON-válasz)
konkrét igehelyeket, magyar kulcsszavakat és eredeti nyelvi terminusokat
von ki a kérdésből, majd:

  1. minden Gemini-javasolt igehelyet VALIDÁL a helyi RÚF-tár ellen
     (`ruf_bible_service.parse_bible_reference` + `ruf_bible_local_db.
     lookup_local`) — csak valóban létező, szöveggel rendelkező versek
     kerülnek ki, a modell esetleges hallucinációit csendben eldobjuk;
  2. a javasolt kulcsszavakat/eredeti nyelvi terminusokat lefuttatja a
     már meglévő 1-2. módú keresőmotorokon (`ruf_bible_local_db.
     search_literal`, `original_language_concordance.search_original`)
     másodlagos, kiegészítő találatokként.

A Gemini-hívásnak KIZÁRÓLAG a felhasználó kérdése kerül a promptjába —
a helyi RÚF-szövegtár tartalma sosem kerül ki a modellnek (lásd
`ruf_bible_local_db.py` modul-docstringje: a DB kizárólag az alkalmazás
belső működését szolgálhatja).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

import original_language_concordance as olc
import ruf_bible_local_db as local_db
from ruf_bible_service import parse_bible_reference

TAB_LABEL = "Konkordancia"

MAX_KEYWORDS = 6
MAX_ORIGINAL_TERMS = 4
KEYWORD_HIT_LIMIT = 5
ORIGINAL_TERM_HIT_LIMIT = 5

_RELATION_LABELS: dict[str, str] = {
    "megerosit": "megerősíti a fogalmat",
    "kontrasztban_all": "kontrasztban áll / árnyalja más irányból",
    "arnyalja": "árnyalja a fogalmat",
}

_SYSTEM_PROMPT = """\
Te egy bibliai konkordancia-kutató vagy. A feladatod: egy összetett,
teológiai/fogalmi kérdés alapján konkrét, VALÓBAN LÉTEZŐ bibliai
igehelyeket találni — nem csak szó szerinti egyezéseket, hanem valódi
fogalmi/teológiai kapcsolódásokat és NARRATÍV példákat is (olyan
történeteket, amik illusztrálják a fogalmat anélkül, hogy a kulcsszó
szó szerint szerepelne bennük).

KRITIKUS SZABÁLYOK:
- SOSE találj ki igehelyet. Csak olyan hivatkozást adj, amiről biztosan
  tudod, hogy létezik és a tartalma valóban kapcsolódik a kérdéshez.
- KÖTELEZŐ ELLENPONT-KERESÉS: ha a kérdés egy fogalmat árnyaltan vagy
  feltételesen állít be (pl. "nem mindig X", "nem automatikus", "van
  kivétel"), ne elégedj meg azzal, hogy csak a kérdésben feltett
  állítást megerősítő helyeket sorolod fel. AKTÍVAN keress legalább
  1-2 olyan helyet is, amelyik az ELLENKEZŐ vagy tágabb nézőpontot
  képviseli (pl. feltétel NÉLKÜLI változat), és jelöld meg
  "kontrasztban_all" relation-nel. Ha a kérdés a megbocsátás
  feltételességéről szól, és tudsz olyan helyről, ami feltétel nélküli
  megbocsátásra buzdít, azt MINDENKÉPP add hozzá kontrasztként — ne
  hagyd ki csak azért, mert "ellentmond" a kérdés premisszájának; épp
  ez a kontraszt adja a válasz teológiai hitelességét.
- Részesítsd előnyben a narratív (elbeszélő) példákat is a tanító
  igék mellett, ha van ilyen — ez adja a konkordancia valódi hozzáadott
  értékét a puszta kulcsszókereséshez képest.
- A "keywords" mezőbe csak olyan magyar szót/kifejezést adj, ami
  valószínűleg szó szerint szerepel a RÚF 2014 fordítás szövegében.
- Az "original_language_terms" mezőbe CSAK akkor adj valamit, ha egy
  konkrét héber/görög szó fogalmilag valóban központi — sose adj
  általános/gyakori igéket vagy funkciószavakat.
- Legfeljebb 8 igehelyet adj vissza, a legrelevánsabbakat — de a fenti
  ellenpont-keresési kötelezettség ETTŐL FÜGGETLENÜL érvényes.

A válasz KIZÁRÓLAG a megadott JSON-sémának megfelelő, nyers JSON legyen
— semmilyen bevezető, magyarázó vagy záró szöveg nélkül.
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": "Magyar rövidítéses igehely, pl. 'Lk 17,3-4'",
                    },
                    "relation": {
                        "type": "string",
                        "enum": ["megerosit", "kontrasztban_all", "arnyalja"],
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "1 mondat, miért releváns ez a hely",
                    },
                },
                "required": ["reference", "relation", "reasoning"],
            },
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
        "original_language_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["term"],
            },
        },
    },
    "required": ["references", "keywords"],
}


@dataclass(frozen=True)
class ConceptReference:
    reference: str
    relation: str
    reasoning: str
    book_abbr: str
    chapter: int
    verse_start: int | None
    verse_end: int | None
    context_text: str

    @property
    def relation_label(self) -> str:
        return _RELATION_LABELS.get(self.relation, self.relation)

    @property
    def sort_key(self) -> tuple[str, int, int]:
        return (self.book_abbr, self.chapter, self.verse_start or 0)


@dataclass(frozen=True)
class ConceptSearchResult:
    question: str
    references: list[ConceptReference] = field(default_factory=list)
    keyword_hits: list[local_db.LiteralSearchHit] = field(default_factory=list)
    original_language_hits: list[olc.OriginalLanguageHit] = field(default_factory=list)
    raw_keywords: list[str] = field(default_factory=list)
    raw_terms: list[str] = field(default_factory=list)
    error: str | None = None


def _extract_json(text: str) -> dict | None:
    """A Gemini-válaszból megpróbálja kinyerni a JSON objektumot.

    A `generate_text` szöveges udvariassági/levágás-heurisztikái (lásd
    `app._strip_chatty_intro`) nem JSON-tudatosak — ha ezek mégis
    hozzányúlnának a nyers JSON-hoz, itt egy védőháló próbálja
    kigyomlálni a { … } közötti tartalmat."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _validate_reference(raw_reference: str) -> tuple[str, int, int | None, int | None, str] | None:
    """Ha a hivatkozás valóban feloldható ÉS van hozzá szöveg a helyi
    RÚF-tárban, visszaadja `(book_abbr, chapter, verse_start, verse_end,
    context_text)`-et — egyébként `None` (a találatot el kell dobni)."""
    try:
        parsed = parse_bible_reference(raw_reference)
    except ValueError:
        return None
    verses = local_db.lookup_local(
        parsed.book.code, parsed.chapter, parsed.verse_start, parsed.verse_end
    )
    if not verses:
        return None
    context_text = " ".join(str(v.get("text", "")).strip() for v in verses).strip()
    if not context_text:
        return None
    return (
        parsed.book.abbr,
        parsed.chapter,
        parsed.verse_start,
        parsed.verse_end,
        context_text,
    )


def _build_references(raw_items: list[dict]) -> list[ConceptReference]:
    results: list[ConceptReference] = []
    seen: set[tuple[str, int, int | None]] = set()
    for item in raw_items:
        raw_reference = str(item.get("reference") or "").strip()
        if not raw_reference:
            continue
        validated = _validate_reference(raw_reference)
        if validated is None:
            continue
        book_abbr, chapter, verse_start, verse_end, context_text = validated
        dedupe_key = (book_abbr, chapter, verse_start)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        relation = str(item.get("relation") or "megerosit").strip()
        if relation not in _RELATION_LABELS:
            relation = "megerosit"
        reasoning = str(item.get("reasoning") or "").strip()
        results.append(
            ConceptReference(
                reference=raw_reference,
                relation=relation,
                reasoning=reasoning,
                book_abbr=book_abbr,
                chapter=chapter,
                verse_start=verse_start,
                verse_end=verse_end,
                context_text=context_text,
            )
        )
    results.sort(key=lambda r: r.sort_key)
    return results


def _keyword_hits(keywords: list[str], exclude: set[tuple[str, int, int | None]]) -> list[local_db.LiteralSearchHit]:
    hits: list[local_db.LiteralSearchHit] = []
    for keyword in keywords[:MAX_KEYWORDS]:
        keyword = keyword.strip()
        if not keyword:
            continue
        for hit in local_db.search_literal(keyword, limit=KEYWORD_HIT_LIMIT):
            key = (hit.book_abbr, hit.chapter, hit.verse)
            if key in exclude:
                continue
            exclude.add(key)
            hits.append(hit)
    return hits


def _original_language_hits(
    terms: list[str], exclude: set[tuple[str, int, int | None]]
) -> list[olc.OriginalLanguageHit]:
    hits: list[olc.OriginalLanguageHit] = []
    for term in terms[:MAX_ORIGINAL_TERMS]:
        term = term.strip()
        if not term or not olc.is_original_language_query(term):
            continue
        term_hits = olc.search_original(term, with_hungarian_context=False)[:ORIGINAL_TERM_HIT_LIMIT]
        for hit in term_hits:
            key = (hit.book_abbr, hit.chapter, hit.verse)
            if key in exclude:
                continue
            exclude.add(key)
            hits.append(olc.attach_hungarian_context(hit))
    return hits


def _app_module():
    """Az `app.generate_text`-et hordozó modult adja vissza.

    FONTOS: Streamlit a futó `app.py`-t `sys.modules["__main__"]` alatt
    regisztrálja, NEM `sys.modules["app"]` alatt (lásd
    `streamlit.runtime.scriptrunner.script_runner._new_module`). Egy
    egyszerű `import app` élő Streamlit-munkamenetben ezért NEM a már
    futó, inicializált modult adná vissza, hanem a `app.py`-t egy
    teljesen ÚJ, második modulként futtatná le a nulláról — ami a teljes
    oldal-renderelést újra elindítja önmagán belül, és
    `StreamlitDuplicateElementKey` hibát okoz. Ezért előbb a
    `__main__`-t próbáljuk (élő Streamlit-eset), csak utána esünk
    vissza a normál `import app`-ra (teszt-/parancssori kontextus, ahol
    `app.py` sosem futott Streamlit-szkriptként)."""
    main_module = sys.modules.get("__main__")
    if main_module is not None and hasattr(main_module, "generate_text"):
        return main_module
    import app

    return app


def search_concept(question: str) -> ConceptSearchResult:
    """Egy fogalmi/összetett kérdés alapján igehelyeket, kulcsszavas és
    eredeti nyelvi kapcsolódó találatokat ad vissza. A Gemini-hívás a
    meglévő `app.generate_text` infrastruktúrát használja (cache,
    cooldown, retry) — nincs önálló hívási útvonal."""
    question = (question or "").strip()
    if not question:
        return ConceptSearchResult(question=question, error="Üres kérdés.")

    app = _app_module()

    task_prompt = (
        "Kérdés/fogalom, amihez konkrét bibliai igehelyeket, kulcsszavakat "
        "és (ha releváns) eredeti nyelvi terminusokat kell találni:\n\n"
        f"{question}"
    )
    raw_response = app.generate_text(
        task_prompt,
        tab_label=TAB_LABEL,
        system_bundle=_SYSTEM_PROMPT,
        include_brevity_directive=False,
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
        temperature=0.2,
        max_output_tokens=4096,
        truncation_notice_mode="never",
    )

    if raw_response.startswith("⚠️") or raw_response.startswith("⏳"):
        return ConceptSearchResult(question=question, error=raw_response)

    payload = _extract_json(raw_response)
    if payload is None:
        return ConceptSearchResult(
            question=question,
            error="⚠️ A Gemini válasza nem volt értelmezhető JSON formátumban.",
        )

    raw_references = payload.get("references") or []
    raw_keywords = [str(k).strip() for k in (payload.get("keywords") or []) if str(k).strip()]
    raw_terms_items = payload.get("original_language_terms") or []
    raw_terms = [
        str(item.get("term") or "").strip()
        for item in raw_terms_items
        if isinstance(item, dict) and str(item.get("term") or "").strip()
    ]

    references = _build_references(raw_references if isinstance(raw_references, list) else [])
    exclude: set[tuple[str, int, int | None]] = set()
    for r in references:
        start = r.verse_start or 0
        end = r.verse_end or start
        if start == 0:
            exclude.add((r.book_abbr, r.chapter, None))
        else:
            for verse in range(start, end + 1):
                exclude.add((r.book_abbr, r.chapter, verse))
    keyword_hits = _keyword_hits(raw_keywords, exclude)
    original_language_hits = _original_language_hits(raw_terms, exclude)

    return ConceptSearchResult(
        question=question,
        references=references,
        keyword_hits=keyword_hits,
        original_language_hits=original_language_hits,
        raw_keywords=raw_keywords,
        raw_terms=raw_terms,
    )


__all__ = [
    "ConceptReference",
    "ConceptSearchResult",
    "TAB_LABEL",
    "search_concept",
]
