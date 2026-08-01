"""Feltételes mini-exegézis (ExegeticalBrief) a vázlatgenerálás előtt.

BARE, illetve szükség esetén PARTIAL módban készül. Elsődlegesen a Textus
helyi görög/héber adatait használja; nem talál ki lemmát, Strong-számot vagy
igeidőt. A brief belső réteg — a vázlatban csak a hasznos kapaszkodók jelennek meg.

Külső fizetős API / internetes keresés nélkül. A BackgroundResearchProvider
interfész későbbi, forrásolt háttéradatbázishoz bővíthető.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Protocol

from sermon_outline_context import ContextMode, OutlineContext
from prompt_safety import wrap_untrusted_content

logger = logging.getLogger("textus.outline.exegesis")

GenerateFn = Callable[..., str]


class BackgroundResearchProvider(Protocol):
    """Későbbi bővíthető interfész — forrásolt háttéradatbázis számára."""

    def lookup(self, reference: str, *, query: str = "") -> list[dict[str, Any]]:
        """Ellenőrizhető, forrásolt háttértételek. Üres lista = nincs adat."""
        ...


class NullBackgroundResearchProvider:
    """Alapértelmezés: nincs külső kutatás."""

    def lookup(self, reference: str, *, query: str = "") -> list[dict[str, Any]]:
        return []


@dataclass
class LexicalHandle:
    form: str = ""
    lemma: str = ""
    morph: str = ""
    strong: str = ""
    verse: int | None = None
    homiletical_relevance: str = ""
    grounded: bool = True  # False = óvatos / nem állítható biztosan


@dataclass
class ExegeticalBrief:
    """Strukturált belső mini-exegézis."""

    genre_and_movement: str = ""
    central_claim: str = ""
    internal_tension: str = ""
    key_expressions: list[LexicalHandle] = field(default_factory=list)
    theological_emphasis: str = ""
    historical_canonical_note: str = ""
    listener_connection: str = ""
    caution_flags: list[str] = field(default_factory=list)
    source: str = "deterministic"  # deterministic | ai_assisted | hybrid
    grounded_in_original_data: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key_expressions"] = [asdict(x) for x in self.key_expressions]
        return d

    def handles_for_outline(self, *, max_items: int = 5) -> list[str]:
        """Rövid exegetikai kapaszkodók a vázlat megjelenítéséhez."""
        out: list[str] = []
        for expr in self.key_expressions[:max_items]:
            bits = []
            if expr.lemma or expr.form:
                bits.append(expr.lemma or expr.form)
            if expr.homiletical_relevance:
                bits.append(expr.homiletical_relevance)
            elif expr.morph and expr.grounded:
                bits.append(f"morfológia: {expr.morph}")
            line = " — ".join(bits) if bits else ""
            if line:
                out.append(line)
        if not out and self.central_claim:
            out.append(self.central_claim)
        if self.theological_emphasis and len(out) < max_items:
            out.append(self.theological_emphasis)
        return out[:max_items]


def _s(value: Any) -> str:
    return str(value or "").strip()


def _normalize(text: str) -> str:
    return " ".join(_s(text).casefold().split())


def infer_literary_hints(reference: str, bible_text: str) -> dict[str, str]:
    """Könnyű, determinisztikus műfaj-/mozgásjelzések a textusból."""
    ref = _normalize(reference)
    text = _normalize(bible_text)
    hints: dict[str, str] = {}

    doxology_markers = (
        "dicsőség",
        "hatalom",
        "fenség",
        "ámen",
        "egyedül",
        "örökkön",
        "örökké",
    )
    narrative_markers = (
        "mondta",
        "felelte",
        "odament",
        "megkérdezte",
        "példázat",
        "út",
        "samaritánus",
    )
    psalm_markers = ("zsolt", "selah", "áldjad", "az úr a")

    if any(m in text for m in doxology_markers) and (
        "júd" in ref or text.count("dicsőség") >= 1
    ):
        hints["genre"] = "doxológia"
        hints["movement"] = (
            "Isten megtartó cselekvése → feddhetetlenül elé állítás → dicsőítés"
        )
    elif "zsolt" in ref or any(m in text for m in psalm_markers):
        hints["genre"] = "zsoltár / költői szöveg"
        hints["movement"] = "képek és gondolati mozgások, nem merev pontlista"
    elif any(m in text for m in narrative_markers) or "lk" in ref or "luk" in ref:
        hints["genre"] = "elbeszélés / példázat"
        hints["movement"] = "jelenetek, feszültség és fordulat"
    elif any(w in text for w in ("azért", "tehát", "mert", "hogy")):
        hints["genre"] = "érvelő / tanító szakasz"
        hints["movement"] = "expozitív gondolatmenet a textus állítása mentén"
    else:
        hints["genre"] = "bibliai szakasz"
        hints["movement"] = "a textus saját belső egységei szerint"

    # Amen: liturgikus zárójel, nem főpont
    if re.search(r"\bámen\b", text) or re.search(r"\bamen\b", text):
        hints["amen_note"] = (
            "Az „Ámen” litugikus/hitvalló lezárás — ne legyen önálló főpont, "
            "hacsak nincs külön teológiai indoka."
        )
    return hints


def _select_salient_tokens(
    original_data: list[dict[str, Any]], *, limit: int = 5
) -> list[LexicalHandle]:
    """Fontosnak tűnő tokenek — content words, nem kötőszók."""
    skip_lemmas = {
        "ὁ",
        "ἡ",
        "τό",
        "καί",
        "δέ",
        "γάρ",
        "ἀλλά",
        "οὖν",
        "ἐν",
        "εἰς",
        "ἐκ",
        "πρός",
        "διά",
        "ἀπό",
        "μετά",
        "ὅτι",
        "ὡς",
        "μή",
        "οὐ",
        "οὐκ",
        "οὐχ",
        "εἰμί",
        "αὐτός",
        "ἐγώ",
        "σύ",
        "ἡμεῖς",
        "ὑμεῖς",
        "ו",
        "ה",
        "את",
        "על",
        "אל",
        "מן",
        "ל",
        "ב",
        "כ",
    }
    scored: list[tuple[int, LexicalHandle]] = []
    seen: set[str] = set()
    for verse_block in original_data:
        verse_no = verse_block.get("verse")
        for tok in verse_block.get("tokens") or []:
            if not isinstance(tok, dict):
                continue
            lemma = _s(tok.get("lemma"))
            form = _s(tok.get("form"))
            key = _normalize(lemma or form)
            if not key or key in seen:
                continue
            if lemma in skip_lemmas or form in skip_lemmas:
                continue
            # Prefer verbs/nouns-ish morph codes when present
            morph = _s(tok.get("morph"))
            score = 1
            if morph:
                m = morph.upper()
                if any(tag in m for tag in ("V-", "N-", "A-", "V", "N")):
                    score += 2
                if "IMP" in m or "AOR" in m or "PERF" in m:
                    score += 1
            if len(lemma) >= 4 or len(form) >= 4:
                score += 1
            seen.add(key)
            scored.append(
                (
                    score,
                    LexicalHandle(
                        form=form,
                        lemma=lemma or form,
                        morph=morph,
                        strong=_s(tok.get("strong")),
                        verse=int(verse_no) if verse_no is not None else None,
                        grounded=True,
                    ),
                )
            )
    scored.sort(key=lambda x: (-x[0], x[1].lemma))
    return [h for _, h in scored[:limit]]


def build_deterministic_brief(ctx: OutlineContext) -> ExegeticalBrief:
    """Adatokból épített brief — kitalálás nélkül."""
    hints = infer_literary_hints(ctx.passage_reference, ctx.bible_text)
    handles = _select_salient_tokens(ctx.original_language_data, limit=5)

    # Homiletikai relevancia csak óvatosan, adat alapján
    for h in handles:
        parts = []
        if h.lemma:
            parts.append(f"lemma: {h.lemma}")
        if h.strong:
            parts.append(h.strong)
        if h.morph:
            parts.append(f"morph: {h.morph}")
        if h.verse is not None:
            parts.append(f"v. {h.verse}")
        h.homiletical_relevance = (
            "Eredeti nyelvi adat a kiválasztott textusból ("
            + ", ".join(parts)
            + "). A jelentést csak a rendelkezésre álló morph/lemma alapján mérlegeld."
        )

    central = ""
    if ctx.sermon_main_idea:
        central = ctx.sermon_main_idea
    elif ctx.text_main_idea:
        central = ctx.text_main_idea
    elif ctx.bible_text:
        # Ne idézzük a teljes verset — rövid irány
        first_line = ctx.bible_text.split("\n")[0]
        words = first_line.split()
        if len(words) > 14:
            central = (
                "A szakasz központi állítása a textus saját mozgásából olvasható ki; "
                "ne a teljes versidézet legyen a fókusz."
            )
        else:
            central = (
                "A szakasz központi állítását a textus belső egysége határozza meg."
            )

    tension = ""
    lt = ctx.homiletical_preferences.get("listener_tension")
    if isinstance(lt, dict):
        tension = _s(lt.get("listener_question") or lt.get("tension"))
    if not tension and hints.get("genre") == "doxológia":
        tension = (
            "Hogyan lehet botlás közepette is Isten megtartó hatalmában bízni, "
            "és a dicsőítés felé megérkezni?"
        )
    elif not tension:
        tension = (
            "Milyen belső feszültség vagy kérdés mozgatja a szakaszt a hallgató felé?"
        )

    theo = ""
    hc = ctx.homiletical_preferences.get("human_condition")
    if isinstance(hc, dict):
        theo = _s(hc.get("divine_action") or hc.get("condition"))
    if not theo and hints.get("genre") == "doxológia":
        theo = (
            "Isten megtartó cselekvése, a feddhetetlenül elé állítás és a dicsőítés "
            "összetartozó doxológiai mozgása."
        )

    cautions = []
    if hints.get("amen_note"):
        cautions.append(hints["amen_note"])
    if not ctx.original_language_data:
        cautions.append(
            "Nincs betöltött eredeti nyelvi adat: ne állíts konkrét lemmát, "
            "Strong-számot vagy igeidőt."
        )
    if ctx.exegetical_material:
        cautions.append(
            "Az exegetikai háttéranyag válogatandó; ne másold mechanikusan."
        )

    listener = ""
    if isinstance(lt, dict):
        listener = _s(lt.get("human_situation") or lt.get("listener_need"))
    if not listener:
        listener = (
            "A hallgató saját botlásfélelme, hűségküzdelme vagy dicsőítésre "
            "szomjazó helyzete lehet a kapcsolódási pont — a textus mozgása szerint."
        )

    return ExegeticalBrief(
        genre_and_movement=(
            f"{hints.get('genre', '')}: {hints.get('movement', '')}".strip(": ")
        ),
        central_claim=central,
        internal_tension=tension,
        key_expressions=handles,
        theological_emphasis=theo,
        historical_canonical_note=_s(ctx.history)[:400],
        listener_connection=listener,
        caution_flags=cautions,
        source="deterministic",
        grounded_in_original_data=bool(handles),
    )


BRIEF_SYSTEM_PROMPT = """\
Belső, rövid ExegeticalBrief-et készítesz igehirdetési vázlathoz.
Nem prédikáció és nem teljes kommentár.

SZABÁLYOK:
- Csak a kapott bibliai szövegre és az ellenőrizhető eredeti nyelvi adatokra támaszkodj.
- Ne találj ki lemmát, Strong-számot, igeidőt vagy szójelentést.
- Ha nincs nyelvi adat, fogalmazz óvatosan, vagy hagyd üresen a nyelvi mezőket.
- Az „Ámen” ne legyen önálló exegetikai főegység.
- Kizárólag JSON:

{
  "genre_and_movement": "műfaj és irodalmi mozgás",
  "central_claim": "központi állítás (nem versidézet)",
  "internal_tension": "belső feszültség / kérdés",
  "key_expressions": [
    {"lemma_or_form": "", "relevance": "", "grounded": true}
  ],
  "theological_emphasis": "teológiai hangsúly",
  "historical_canonical_note": "rövid kánoni/történeti megjegyzés vagy üres",
  "listener_connection": "lehetséges hallgatói kapcsolódás",
  "caution_flags": ["óvatossági megjegyzés"]
}
"""


def _merge_ai_brief(
    base: ExegeticalBrief, obj: Mapping[str, Any], *, has_original: bool
) -> ExegeticalBrief:
    out = ExegeticalBrief(
        genre_and_movement=base.genre_and_movement,
        central_claim=base.central_claim,
        internal_tension=base.internal_tension,
        key_expressions=list(base.key_expressions),
        theological_emphasis=base.theological_emphasis,
        historical_canonical_note=base.historical_canonical_note,
        listener_connection=base.listener_connection,
        caution_flags=list(base.caution_flags),
        source=base.source,
        grounded_in_original_data=base.grounded_in_original_data,
    )
    for field_name in (
        "genre_and_movement",
        "central_claim",
        "internal_tension",
        "theological_emphasis",
        "historical_canonical_note",
        "listener_connection",
    ):
        val = _s(obj.get(field_name))
        if val:
            setattr(out, field_name, val)
    flags = obj.get("caution_flags")
    if isinstance(flags, list):
        for f in flags:
            t = _s(f)
            if t and t not in out.caution_flags:
                out.caution_flags.append(t)
    # AI nyelvi kifejezések: csak ha grounded és van adat; különben elvetjük
    exprs = obj.get("key_expressions")
    if isinstance(exprs, list) and has_original and not out.key_expressions:
        for item in exprs[:5]:
            if not isinstance(item, dict):
                continue
            if item.get("grounded") is False:
                continue
            form = _s(item.get("lemma_or_form") or item.get("lemma") or item.get("form"))
            if not form:
                continue
            out.key_expressions.append(
                LexicalHandle(
                    lemma=form,
                    form=form,
                    homiletical_relevance=_s(item.get("relevance")),
                    grounded=True,
                )
            )
    out.source = "hybrid" if base.grounded_in_original_data else "ai_assisted"
    return out


def generate_exegetical_brief(
    ctx: OutlineContext,
    *,
    generate_fn: GenerateFn | None = None,
    force: bool = False,
    background_provider: BackgroundResearchProvider | None = None,
) -> ExegeticalBrief | None:
    """BARE / hiányos PARTIAL esetén brief; RICH-nél általában None.

    force=True: mindig készít (teszt / diagnosztika).
    """
    needs = force or ctx.context_mode in {ContextMode.BARE, ContextMode.PARTIAL}
    if ctx.context_mode == ContextMode.PARTIAL and ctx.has_exegetical() and not force:
        # Van exegetikai anyag: brief csak kiegészítésnek, ha nincs nyelvi adat
        if ctx.has_original_language():
            needs = False
    if ctx.context_mode == ContextMode.RICH and not force:
        needs = False
    if not needs:
        return None

    brief = build_deterministic_brief(ctx)

    # Opcionális későbbi háttérkutatás — jelenleg null
    provider = background_provider or NullBackgroundResearchProvider()
    try:
        extra = provider.lookup(ctx.passage_reference)
        if extra:
            brief.caution_flags.append(
                "Külső háttéradat érkezett; csak forrásolt állításokat használd."
            )
    except Exception:
        pass

    if generate_fn is None or ctx.context_mode == ContextMode.RICH:
        return brief

    # AI asszisztált kiegészítés BARE/PARTIAL-nál — nyelvi adat nélkül nem inventál
    user_prompt = (
        f"Igehely: {ctx.passage_reference}\n"
        f"Mód: {ctx.context_mode.value}\n\n"
        f"{wrap_untrusted_content('BIBLE_TEXT', ctx.bible_text[:5000])}\n\n"
        f"EREDETI NYELVI ADAT (csak ezt használd nyelvi állításokhoz):\n"
        f"{json.dumps(ctx.original_language_data[:6], ensure_ascii=False)}\n\n"
        f"DETERMINISZTIKUS MAG:\n{json.dumps(brief.to_dict(), ensure_ascii=False)}\n\n"
        "Egészítsd ki / pontosítsd a briefet. Ne találj ki nyelvi adatot."
    )
    try:
        try:
            raw = generate_fn(
                user_prompt,
                enable_google_search=False,
                tab_label="Igehirdetési vázlat",
                use_cache=False,
                system_bundle=BRIEF_SYSTEM_PROMPT,
                include_brevity_directive=False,
                max_output_tokens=900,
            )
        except TypeError:
            raw = generate_fn(user_prompt)
    except Exception as exc:  # pragma: no cover
        logger.info("exegetical_brief_ai_failed err=%s", type(exc).__name__)
        return brief

    try:
        from sermon_workshop_m4_ai import extract_json_object
        from ai_response_validation import sanitize_ai_json

        obj = extract_json_object(raw or "") or {}
        if isinstance(obj, dict):
            obj = sanitize_ai_json(obj) or obj
            return _merge_ai_brief(
                brief, obj, has_original=bool(ctx.original_language_data)
            )
    except Exception:
        pass
    return brief


__all__ = [
    "BRIEF_SYSTEM_PROMPT",
    "BackgroundResearchProvider",
    "ExegeticalBrief",
    "LexicalHandle",
    "NullBackgroundResearchProvider",
    "build_deterministic_brief",
    "generate_exegetical_brief",
    "infer_literary_hints",
]
