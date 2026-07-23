"""Igehirdetési műhely M6 — igehirdetés útja és mozgásai MI.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
Újrafelhasználja az M5 evangéliumi ív kontextusépítőjét.
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping

from sermon_workshop_data import (
    empty_sermon_movement,
    normalize_sermon_movement,
    normalize_sermon_movements,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import (
    MISSING,
    _as_str_list,
    _as_text,
    _display,
    _is_api_error_text,
    _is_present,
)
from sermon_workshop_m5_gospel_ai import build_gospel_arc_context

TAB_SUGGEST = "Igehirdetési út — javaslat"
TAB_ASSESS = "Igehirdetési út — értékelés"
DEFAULT_TEMPERATURE = 0.15

GenerateFn = Callable[..., str]

SERMON_PATH_TYPES = (
    "text_following",
    "deductive",
    "inductive",
    "narrative",
    "tension_to_gospel",
    "meditative",
    "dialogical",
    "mixed",
)

SERMON_PATH_TYPE_LABELS_HU: dict[str, str] = {
    "text_following": "Textuskövető",
    "deductive": "Deduktív",
    "inductive": "Induktív",
    "narrative": "Narratív",
    "tension_to_gospel": "Feszültségtől az evangéliumig",
    "meditative": "Meditatív",
    "dialogical": "Párbeszédes",
    "mixed": "Vegyes forma",
}

MOVEMENT_ROLES = (
    "opening",
    "tension",
    "deepening",
    "turn",
    "gospel_resolution",
    "response",
    "arrival",
)

MOVEMENT_ROLE_LABELS_HU: dict[str, str] = {
    "opening": "Megnyitás",
    "tension": "Feszültség",
    "deepening": "Elmélyítés",
    "turn": "Fordulat",
    "gospel_resolution": "Evangéliumi feloldás",
    "response": "Válasz",
    "arrival": "Megérkezés",
}

MIN_MOVEMENTS = 3
MAX_MOVEMENTS = 5
DEFAULT_MOVEMENT_COUNT = 4

M6_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű, református asszisztense vagy.
Csak a megadott műhelyanyagból dolgozz. Ne találj ki bibliai szöveget,
idézetet, személyes történetet vagy történeti adatot.
Válaszod KIZÁRÓLAG érvényes JSON legyen.\
"""

_LIMITS_EXTRA = {
    "sermon_path_block": 2400,
    "movements_block": 5000,
    "literary_genre": 800,
}


@dataclass
class SermonPathAlternative:
    path_type: str = "text_following"
    emphasis: str = ""
    reason_for_use: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class SermonPathSuggestionResult:
    recommended_path_type: str = "text_following"
    path_rationale: str = ""
    starting_point: str = ""
    destination: str = ""
    movements: list[dict[str, str]] = field(default_factory=list)
    expanded_summary: str = ""
    alternative_paths: list[SermonPathAlternative] = field(default_factory=list)
    reasoning_summary: str = ""
    basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_path_type": self.recommended_path_type,
            "path_rationale": self.path_rationale,
            "starting_point": self.starting_point,
            "destination": self.destination,
            "movements": [dict(m) for m in self.movements],
            "expanded_summary": self.expanded_summary,
            "alternative_paths": [a.to_dict() for a in self.alternative_paths],
            "reasoning_summary": self.reasoning_summary,
            "basis": list(self.basis),
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }

    def to_ui_path_block(self) -> dict[str, str]:
        return {
            "type": self.recommended_path_type,
            "reason": self.path_rationale,
            "starting_point": self.starting_point,
            "destination": self.destination,
        }


@dataclass
class SermonPathAssessmentResult:
    overall_assessment: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    path_type_assessment: str = ""
    structure_assessment: str = ""
    gospel_turn_assessment: str = ""
    transition_assessment: str = ""
    revised_path_rationale: str = ""
    revised_starting_point: str = ""
    revised_destination: str = ""
    revised_movements: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_assessment": self.overall_assessment,
            "strengths": list(self.strengths),
            "improvements": list(self.improvements),
            "path_type_assessment": self.path_type_assessment,
            "structure_assessment": self.structure_assessment,
            "gospel_turn_assessment": self.gospel_turn_assessment,
            "transition_assessment": self.transition_assessment,
            "revised_path_rationale": self.revised_path_rationale,
            "revised_starting_point": self.revised_starting_point,
            "revised_destination": self.revised_destination,
            "revised_movements": [dict(m) for m in self.revised_movements],
            "warnings": list(self.warnings),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }


def normalize_sermon_path_type(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "text_following": "text_following",
        "textuskoveto": "text_following",
        "textuskövető": "text_following",
        "deductive": "deductive",
        "deduktiv": "deductive",
        "deduktív": "deductive",
        "inductive": "inductive",
        "induktiv": "inductive",
        "induktív": "inductive",
        "narrative": "narrative",
        "narrativ": "narrative",
        "narratív": "narrative",
        "tension_to_gospel": "tension_to_gospel",
        "feszultsegtol_az_evangeliumig": "tension_to_gospel",
        "meditative": "meditative",
        "meditativ": "meditative",
        "meditatív": "meditative",
        "dialogical": "dialogical",
        "parbeszedes": "dialogical",
        "párbeszédes": "dialogical",
        "mixed": "mixed",
        "vegyes": "mixed",
        "vegyes_forma": "mixed",
    }
    if raw in SERMON_PATH_TYPES:
        return raw
    return aliases.get(raw, "text_following")


def sermon_path_type_label(value: Any) -> str:
    key = normalize_sermon_path_type(value)
    return SERMON_PATH_TYPE_LABELS_HU.get(key, SERMON_PATH_TYPE_LABELS_HU["text_following"])


def normalize_movement_role(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "opening": "opening",
        "megnyitas": "opening",
        "megnyitás": "opening",
        "tension": "tension",
        "feszultseg": "tension",
        "feszültség": "tension",
        "deepening": "deepening",
        "elmelyites": "deepening",
        "elmélyítés": "deepening",
        "turn": "turn",
        "fordulat": "turn",
        "gospel_resolution": "gospel_resolution",
        "evangeliumi_feloldas": "gospel_resolution",
        "evangéliumi_feloldás": "gospel_resolution",
        "response": "response",
        "valasz": "response",
        "válasz": "response",
        "arrival": "arrival",
        "megerkezes": "arrival",
        "megérkezés": "arrival",
    }
    if raw in MOVEMENT_ROLES:
        return raw
    return aliases.get(raw, "")


def movement_role_label(value: Any) -> str:
    key = normalize_movement_role(value)
    if not key:
        return "—"
    return MOVEMENT_ROLE_LABELS_HU.get(key, key)


def _format_sermon_path_block(raw: Any) -> str:
    if not isinstance(raw, dict):
        return MISSING
    labels = (
        ("type", "Úttípus"),
        ("reason", "Indoklás"),
        ("starting_point", "Kiindulópont"),
        ("destination", "Megérkezési pont"),
    )
    lines: list[str] = []
    for key, label in labels:
        val = _as_text(raw.get(key))
        if not val:
            continue
        if key == "type":
            val = sermon_path_type_label(val)
        lines.append(f"{label}: {val}")
    if not lines:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS_EXTRA["sermon_path_block"])


def _format_movements_block(raw: Any) -> str:
    movements = normalize_sermon_movements(raw)
    if not movements:
        return MISSING
    chunks: list[str] = []
    for idx, mv in enumerate(movements, start=1):
        role = movement_role_label(mv.get("role"))
        title = _as_text(mv.get("title")) or f"Mozgás {idx}"
        parts = [f"{idx}. {title} ({role})"]
        for key, label in (
            ("core_content", "Tartalom"),
            ("textual_basis", "Textusbeli alap"),
            ("listener_discovery", "Hallgatói felismerés"),
            ("transition_to_next", "Átmenet"),
        ):
            val = _as_text(mv.get(key))
            if val:
                parts.append(f"  {label}: {val}")
        chunks.append("\n".join(parts))
    return _display("\n\n".join(chunks), max_chars=_LIMITS_EXTRA["movements_block"])


def build_sermon_path_context(
    *,
    passage: str = "",
    passage_text: str = "",
    bible_translation: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    text_expanded_summary: str = "",
    approved_insights: Any = None,
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    sermon_expanded_summary: str = "",
    human_condition: Any = None,
    listener_tension: Any = None,
    christ_centered_arc: Any = None,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
) -> dict[str, str]:
    """M6 kontextus — jóváhagyott főgondolat és evangéliumi ív elsőbbségével."""
    ctx = build_gospel_arc_context(
        passage=passage,
        passage_text=passage_text,
        bible_translation=bible_translation,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        text_expanded_summary=text_expanded_summary,
        approved_insights=approved_insights,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        sermon_expanded_summary=sermon_expanded_summary,
        human_condition=human_condition,
        listener_tension=listener_tension,
        christ_centered_arc=christ_centered_arc,
        exegesis=exegesis,
        theology=theology,
    )
    path = sermon_path if isinstance(sermon_path, dict) else {}
    ctx["sermon_path_block"] = _format_sermon_path_block(path)
    ctx["movements_block"] = _format_movements_block(sermon_movements)
    ctx["literary_genre"] = (
        _display(literary_genre, max_chars=_LIMITS_EXTRA["literary_genre"])
        if _is_present(literary_genre)
        else MISSING
    )
    return ctx


def _has_approved_sermon_idea(ctx: Mapping[str, str]) -> bool:
    return _is_present(ctx.get("sermon_main_idea"))


def _has_central_tension(ctx: Mapping[str, str]) -> bool:
    block = ctx.get("listener_tension_block", MISSING)
    if not _is_present(block):
        return False
    # A formázott blokkban a központi feszültség sorának tartalma kell
    for line in str(block).splitlines():
        if "Központi feszültség:" in line:
            val = line.split(":", 1)[-1].strip()
            return bool(val) and val != MISSING
    # Ha a blokk jelen van, de a címke eltér, fogadjuk el
    return True


def _has_gospel_resolution_or_divine_action(ctx: Mapping[str, str]) -> bool:
    block = ctx.get("christ_arc_block", MISSING)
    if not _is_present(block):
        return False
    text = str(block)
    for marker in (
        "Evangéliumi feloldás:",
        "Isten kegyelmi cselekvése:",
    ):
        if marker in text:
            for line in text.splitlines():
                if line.startswith(marker):
                    val = line.split(":", 1)[-1].strip()
                    if val and val != MISSING:
                        return True
    return False


def _missing_path_labels(ctx: Mapping[str, str]) -> list[str]:
    missing: list[str] = []
    if not _is_present(ctx.get("passage", MISSING)):
        missing.append("igehely-megjelölés (passage)")
    if not _has_approved_sermon_idea(ctx):
        missing.append("jóváhagyott igehirdetési fő gondolat")
    if not _has_central_tension(ctx):
        missing.append("központi feszültség")
    if not _has_gospel_resolution_or_divine_action(ctx):
        missing.append("evangéliumi feloldás vagy Isten kegyelmi cselekvése")
    return missing


def has_sufficient_sermon_path_material(ctx: Mapping[str, str]) -> bool:
    return not _missing_path_labels(ctx)


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


_SUGGEST_TEMPLATE = """\
Feladatod: AZ IGEHIRDETÉS ÚTJA ÉS MOZGÁSAI megtervezése.

Ez NEM hagyományos hárompontos vázlat, NEM kész kézirat, NEM teljes bevezető,
NEM hosszú illusztráció, NEM alkalmazáslista, NEM teljes lezárás.

A „mozgás” azt jelenti, hogy változik a hallgató látása, mélyül a textus
megértése, átalakul a feszültség, születik felismerés, az evangélium más
fénybe helyezi a helyzetet, és megszületik a kegyelemből fakadó válasz.

## Úttípusok (EGYÉRTÉLMŰEN az alábbiak egyike)

- `text_following` — textuskövető
- `deductive` — deduktív
- `inductive` — induktív
- `narrative` — narratív
- `tension_to_gospel` — feszültségtől az evangéliumig
- `meditative` — meditatív
- `dialogical` — párbeszédes
- `mixed` — vegyes forma

Egyik forma sem „jobb” a másiknál. A javaslat a textus műfajából, belső
mozgásából és a megadott homiletikai eredményekből induljon.

## Mozgások

Adj 3–5 összefüggő mozgást (alapértelmezett cél: 4).
Minden mozgás mezői:
- `title` — rövid munkacím
- `role` — opening | tension | deepening | turn | gospel_resolution | response | arrival
- `core_content` — egy világos bekezdés, nem teljes prédikációrész
- `textual_basis` — vers, kifejezés, kép vagy összefüggés; NE találj ki idézetet
- `listener_discovery` — mit lát másként a hallgató a mozgás végére
- `transition_to_next` — tartalmi szükségszerűség a következő felé (utolsónál lehet üres)

## Homiletikai tilalmak

- mechanikus hárompontos vázlat erőltetése
- a fő gondolat három szinonim mondatra bontása
- azonos tartalmú mozgások ismétlése
- textustól független általános vallási pontok
- puszta újramesélés felismerési út nélkül
- feszültség azonnali feloldása
- Krisztus-kapcsolat mechanikus ismétlése minden mozgásban
- alkalmazás túl korai beillesztése minden pont végére
- hallgató megszégyenítése; hatásvadász dramaturgia; cliffhanger
- kitalált történetek, bibliai vagy történeti adatok
- kész prédikációs kézirat

## Modern homiletikai elvek (szerzőnevek nélkül)

- a hallgató felismerési úton haladjon
- ne mondd ki az elején az összes következtetést
- a feszültségnek legyen funkciója
- az átmenetek tartalmi szükségszerűségből szülessenek
- egy központi fő gondolat köré szerveződjön
- az evangéliumi fordulat változtassa meg a helyzet értelmezését
- az evangélium ne legyen utólagos függelék
- a lezárás felé ne jelenjenek meg új témák

## Műhelyanyag

Igehely: {{passage}}
Fordítás: {{bible_translation}}
Alkalom: {{occasion}}
Fókusz: {{user_focus}}
Műfaj / irodalmi adat: {{literary_genre}}

Bibliai szöveg (passage_text):
{{passage_text}}

Jóváhagyott textusfőgondolat: {{text_main_idea}}
Textusfőgondolat kifejtése: {{text_expanded_summary}}
Jóváhagyott felismerések: {{approved_insights}}

Jóváhagyott igehirdetési fő gondolat: {{sermon_main_idea}}
Igehirdetési fő gondolat kifejtése: {{sermon_expanded_summary}}

Emberi helyzet / kegyelmi válasz:
{{human_condition_block}}

Hallgatói kérdés és feszültség:
{{listener_tension_block}}

Krisztus-központú és evangéliumi ív:
{{christ_arc_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma (csak ezt add vissza)

{
  "recommended_path_type": "text_following|deductive|inductive|narrative|tension_to_gospel|meditative|dialogical|mixed",
  "path_rationale": "",
  "starting_point": "",
  "destination": "",
  "movements": [
    {
      "title": "",
      "role": "opening|tension|deepening|turn|gospel_resolution|response|arrival",
      "core_content": "",
      "textual_basis": "",
      "listener_discovery": "",
      "transition_to_next": ""
    }
  ],
  "expanded_summary": "",
  "alternative_paths": [
    {
      "path_type": "",
      "emphasis": "",
      "reason_for_use": ""
    }
  ],
  "reasoning_summary": "",
  "basis": [],
  "warnings": [],
  "missing_information": []
}

Az `alternative_paths` legfeljebb 2 elem. Az alternatívák ne átfogalmazások
legyenek, hanem eltérő, de védhető útirányok.
"""


_ASSESS_TEMPLATE = """\
Feladatod: a prédikátor SAJÁT igehirdetési útjának és mozgásainak értékelése.

Vizsgáld:
- illik-e az úttípus a textus műfajához;
- világos-e a kiindulópont és a megérkezési pont;
- minden mozgás továbbviszi-e az igehirdetést;
- van-e ismétlés vagy hiányzó lépés;
- textushűek-e a mozgások;
- megfelelő helyen történik-e az evangéliumi fordulat;
- nem válik-e az evangélium utólagos függelékké;
- működnek-e az átmenetek;
- túl gyorsan vagy túl későn oldódik-e fel a feszültség;
- jelen van-e a hallgató felismerési útja;
- nem lett-e belőle kész kézirat vagy túl részletes vázlat.

Ne írd felül automatikusan a felhasználó munkáját — a `revised_*` mezők
csak javaslatok. A `revised_movements` 3–5 elemet tartalmazzon, ha adsz
javítást.

## Műhelyanyag

Igehely: {{passage}}
Fordítás: {{bible_translation}}
Műfaj / irodalmi adat: {{literary_genre}}

Bibliai szöveg:
{{passage_text}}

Jóváhagyott igehirdetési fő gondolat: {{sermon_main_idea}}
Kifejtés: {{sermon_expanded_summary}}

Hallgatói kérdés és feszültség:
{{listener_tension_block}}

Evangéliumi ív:
{{christ_arc_block}}

A prédikátor útja:
{{sermon_path_block}}

A prédikátor mozgásai:
{{movements_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma

{
  "overall_assessment": "",
  "strengths": [],
  "improvements": [],
  "path_type_assessment": "",
  "structure_assessment": "",
  "gospel_turn_assessment": "",
  "transition_assessment": "",
  "revised_path_rationale": "",
  "revised_starting_point": "",
  "revised_destination": "",
  "revised_movements": [
    {
      "title": "",
      "role": "",
      "core_content": "",
      "textual_basis": "",
      "listener_discovery": "",
      "transition_to_next": ""
    }
  ],
  "warnings": []
}
"""


def build_sermon_path_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_SUGGEST_TEMPLATE, ctx)


def build_sermon_path_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_ASSESS_TEMPLATE, ctx)


def _call_m6_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    tab_label: str,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> str:
    prev_temp = None
    touched_temp = False
    if temperature is not None:
        try:
            import streamlit as st

            prev_temp = st.session_state.get("temperature")
            st.session_state["temperature"] = float(temperature)
            touched_temp = True
        except Exception:
            touched_temp = False
    try:
        return generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=tab_label,
            use_cache=False,
            system_bundle=M6_SYSTEM_BUNDLE,
            include_brevity_directive=False,
        )
    finally:
        if touched_temp:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:
                pass


def fallback_sermon_path_suggestion(
    *,
    reasoning: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> SermonPathSuggestionResult:
    return SermonPathSuggestionResult(
        recommended_path_type="text_following",
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_sermon_path_assessment(
    *,
    overall: str = "",
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> SermonPathAssessmentResult:
    return SermonPathAssessmentResult(
        overall_assessment=overall
        or "Nem megítélhető — nincs elegendő értékelhető megfogalmazás.",
        warnings=list(warnings or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def _normalize_movement_item(raw: Any) -> dict[str, str]:
    mv = normalize_sermon_movement(raw if isinstance(raw, dict) else {})
    role = normalize_movement_role(mv.get("role"))
    mv["role"] = role
    # AI-eredménynél új id-t adunk, hogy ne ütközzön a kézi listával
    if not isinstance(raw, dict) or not _as_text(raw.get("id")):
        mv["id"] = empty_sermon_movement()["id"]
    return mv


def _parse_movements_list(
    raw: Any,
    *,
    warnings: list[str],
) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        warnings.append("A mozgások listája hiányzik vagy érvénytelen.")
        return []
    original_count = len([x for x in raw if isinstance(x, dict)])
    if original_count > MAX_MOVEMENTS:
        warnings.append(
            f"A javaslat {original_count} mozgást tartalmazott; "
            f"legfeljebb {MAX_MOVEMENTS} mozgást tartunk meg."
        )
    parsed: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        parsed.append(_normalize_movement_item(item))
        if len(parsed) >= MAX_MOVEMENTS:
            break
    if len(parsed) < MIN_MOVEMENTS:
        warnings.append(
            f"A javaslat kevesebb mint {MIN_MOVEMENTS} mozgást tartalmaz "
            f"({len(parsed)}). Érdemes kiegészíteni."
        )
    return parsed


def _parse_alternative_paths(raw: Any) -> list[SermonPathAlternative]:
    if not isinstance(raw, list):
        return []
    out: list[SermonPathAlternative] = []
    for item in raw[:2]:
        if not isinstance(item, dict):
            continue
        out.append(
            SermonPathAlternative(
                path_type=normalize_sermon_path_type(item.get("path_type")),
                emphasis=_as_text(item.get("emphasis")),
                reason_for_use=_as_text(item.get("reason_for_use")),
            )
        )
    return out


def parse_sermon_path_suggestions(raw: str) -> SermonPathSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_sermon_path_suggestion(
            reasoning="Az API válasz hibás vagy üres.",
            warnings=["A javaslatkészítés nem adott érvényes választ."],
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return fallback_sermon_path_suggestion(
            reasoning="A válasz nem volt érvényes JSON.",
            warnings=["Hibás vagy hiányos JSON; biztonságos alapértékeket használtunk."],
            error_message="Érvénytelen JSON.",
            raw_response=raw or "",
            ok=False,
        )
    warnings = _as_str_list(obj.get("warnings"))
    movements = _parse_movements_list(obj.get("movements"), warnings=warnings)
    return SermonPathSuggestionResult(
        recommended_path_type=normalize_sermon_path_type(
            obj.get("recommended_path_type")
        ),
        path_rationale=_as_text(obj.get("path_rationale")),
        starting_point=_as_text(obj.get("starting_point")),
        destination=_as_text(obj.get("destination")),
        movements=movements,
        expanded_summary=_as_text(obj.get("expanded_summary")),
        alternative_paths=_parse_alternative_paths(obj.get("alternative_paths")),
        reasoning_summary=_as_text(obj.get("reasoning_summary")),
        basis=_as_str_list(obj.get("basis")),
        warnings=warnings,
        missing_information=_as_str_list(obj.get("missing_information")),
        ok=True,
        raw_response=raw or "",
    )


def parse_sermon_path_assessment(raw: str) -> SermonPathAssessmentResult:
    if _is_api_error_text(raw):
        return fallback_sermon_path_assessment(
            overall="Az értékelés nem sikerült (hibás vagy üres API-válasz).",
            warnings=["Az értékelés nem adott érvényes választ."],
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return fallback_sermon_path_assessment(
            overall="Az értékelés nem értelmezhető — érvénytelen JSON.",
            warnings=["Hibás vagy hiányos JSON; biztonságos alapértékeket használtunk."],
            error_message="Érvénytelen JSON.",
            raw_response=raw or "",
            ok=False,
        )
    warnings = _as_str_list(obj.get("warnings"))
    revised_movements = _parse_movements_list(
        obj.get("revised_movements"), warnings=warnings
    )
    return SermonPathAssessmentResult(
        overall_assessment=_as_text(obj.get("overall_assessment")),
        strengths=_as_str_list(obj.get("strengths")),
        improvements=_as_str_list(obj.get("improvements")),
        path_type_assessment=_as_text(obj.get("path_type_assessment")),
        structure_assessment=_as_text(obj.get("structure_assessment")),
        gospel_turn_assessment=_as_text(obj.get("gospel_turn_assessment")),
        transition_assessment=_as_text(obj.get("transition_assessment")),
        revised_path_rationale=_as_text(obj.get("revised_path_rationale")),
        revised_starting_point=_as_text(obj.get("revised_starting_point")),
        revised_destination=_as_text(obj.get("revised_destination")),
        revised_movements=revised_movements,
        warnings=warnings,
        ok=True,
        raw_response=raw or "",
    )


def suggest_sermon_path(
    *,
    passage: str = "",
    passage_text: str = "",
    bible_translation: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    text_expanded_summary: str = "",
    approved_insights: Any = None,
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    sermon_expanded_summary: str = "",
    human_condition: Any = None,
    listener_tension: Any = None,
    christ_centered_arc: Any = None,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> SermonPathSuggestionResult:
    ctx = build_sermon_path_context(
        passage=passage,
        passage_text=passage_text,
        bible_translation=bible_translation,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        text_expanded_summary=text_expanded_summary,
        approved_insights=approved_insights,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        sermon_expanded_summary=sermon_expanded_summary,
        human_condition=human_condition,
        listener_tension=listener_tension,
        christ_centered_arc=christ_centered_arc,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
    )
    missing = _missing_path_labels(ctx)
    if not _is_present(ctx["passage"]):
        return fallback_sermon_path_suggestion(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_sermon_path_material(ctx):
        return fallback_sermon_path_suggestion(
            reasoning=(
                "Nincs elegendő jóváhagyott műhelyeredmény a felelős "
                "igehirdetési út megtervezéséhez. Ne készítsünk általános vázlatot."
            ),
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres ajánlások.",
                "Szükséges: igehely, jóváhagyott igehirdetési fő gondolat, "
                "központi feszültség, valamint evangéliumi feloldás vagy "
                "Isten kegyelmi cselekvése.",
            ],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_sermon_path_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_sermon_path_suggest_prompt(ctx)
    try:
        raw = _call_m6_generate(
            generate_fn,
            prompt,
            tab_label=TAB_SUGGEST,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_sermon_path_suggestion(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=["A javaslatkészítés nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    result = parse_sermon_path_suggestions(raw or "")
    if result.ok and not _is_present(ctx.get("passage_text")):
        note = (
            "A teljes bibliai szöveg (passage_text) nem állt közvetlenül "
            "rendelkezésre; a javaslat a jóváhagyott műhelyeredményekből készült."
        )
        if note not in result.warnings and (
            result.path_rationale or result.movements
        ):
            result.warnings = list(result.warnings) + [note]
        label = "bibliai szöveg (passage_text)"
        if label not in result.missing_information:
            result.missing_information = list(result.missing_information) + [label]
    # Ha van passage_text, ne jelenjen meg téves hiány figyelmeztetés
    if result.ok and _is_present(ctx.get("passage_text")):
        result.warnings = [
            w
            for w in result.warnings
            if "passage_text" not in w.casefold()
            or "nem állt" not in w.casefold()
        ]
        result.missing_information = [
            m
            for m in result.missing_information
            if "passage_text" not in m.casefold()
        ]
    return result


def assess_sermon_path(
    *,
    passage: str,
    sermon_path: Any,
    sermon_movements: Any = None,
    passage_text: str = "",
    bible_translation: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    text_expanded_summary: str = "",
    approved_insights: Any = None,
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    sermon_expanded_summary: str = "",
    human_condition: Any = None,
    listener_tension: Any = None,
    christ_centered_arc: Any = None,
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> SermonPathAssessmentResult:
    path = sermon_path if isinstance(sermon_path, dict) else {}
    movements = normalize_sermon_movements(sermon_movements)
    filled = any(
        _as_text(path.get(k))
        for k in ("type", "reason", "starting_point", "destination")
    ) or any(
        _as_text(m.get("title")) or _as_text(m.get("core_content")) for m in movements
    )
    if not filled:
        return fallback_sermon_path_assessment(
            overall="Nincs értékelhető megfogalmazás az igehirdetési út mezőiben.",
            warnings=["Tölts ki legalább az út vagy egy mozgás mezőit az értékeléshez."],
            ok=True,
        )

    ctx = build_sermon_path_context(
        passage=passage,
        passage_text=passage_text,
        bible_translation=bible_translation,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        text_expanded_summary=text_expanded_summary,
        approved_insights=approved_insights,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        sermon_expanded_summary=sermon_expanded_summary,
        human_condition=human_condition,
        listener_tension=listener_tension,
        christ_centered_arc=christ_centered_arc,
        sermon_path=path,
        sermon_movements=movements,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
    )
    if generate_fn is None:
        return fallback_sermon_path_assessment(
            overall="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_sermon_path_assess_prompt(ctx)
    try:
        raw = _call_m6_generate(
            generate_fn,
            prompt,
            tab_label=TAB_ASSESS,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_sermon_path_assessment(
            overall="Az értékelés közben váratlan hiba történt.",
            warnings=["Az értékelés nem sikerült. Próbáld újra később."],
            error_message=str(exc),
            ok=False,
        )
    return parse_sermon_path_assessment(raw or "")


def _self_check() -> list[str]:
    errors: list[str] = []

    def _gen_factory(payload: str):
        def _gen(*_a, **_k):
            return payload

        return _gen

    def _mv_json(n: int, path_type: str, rationale: str = "r") -> str:
        items = ",".join(
            '{"title":"M%d","role":"deepening","core_content":"c","textual_basis":"t",'
            '"listener_discovery":"d","transition_to_next":"x"}' % i
            for i in range(1, n + 1)
        )
        return (
            f'{{"recommended_path_type":"{path_type}","path_rationale":"{rationale}",'
            f'"starting_point":"s","destination":"d","movements":[{items}],'
            '"expanded_summary":"s","alternative_paths":[],"reasoning_summary":"",'
            '"basis":[],"warnings":[],"missing_information":[]}'
        )

    base_kw = {
        "sermon_main_idea_status": "approved",
        "listener_tension": {"sermon_tension": "Központi feszültség"},
        "christ_centered_arc": {"divine_gracious_action": "Isten cselekszik"},
    }

    narrative_json = (
        '{"recommended_path_type":"narrative","path_rationale":"Elbeszélő ív.",'
        '"starting_point":"A jelenet feszültsége.","destination":"Hitbeli látás.",'
        '"movements":['
        '{"title":"M1","role":"opening","core_content":"a","textual_basis":"v1",'
        '"listener_discovery":"d1","transition_to_next":"t1"},'
        '{"title":"M2","role":"tension","core_content":"b","textual_basis":"v2",'
        '"listener_discovery":"d2","transition_to_next":"t2"},'
        '{"title":"M3","role":"gospel_resolution","core_content":"c","textual_basis":"v3",'
        '"listener_discovery":"d3","transition_to_next":""}'
        '],"expanded_summary":"Összefoglaló.","alternative_paths":[],'
        '"reasoning_summary":"ok","basis":["textus"],"warnings":[],'
        '"missing_information":[]}'
    )
    ra = suggest_sermon_path(
        passage="Lk 15,11–32",
        passage_text="Egy embernek volt két fia…",
        sermon_main_idea="Az Atya kereső szeretete",
        generate_fn=_gen_factory(narrative_json),
        **base_kw,
    )
    if not ra.ok or ra.recommended_path_type != "narrative":
        errors.append("A: expected narrative path")
    if len(ra.movements) != 3:
        errors.append("E: expected 3 movements")
    if any(
        "passage_text" in w.casefold() and ("hiány" in w.casefold() or "nincs" in w.casefold())
        for w in ra.warnings
    ):
        errors.append("M: false missing passage_text warning")

    rb = suggest_sermon_path(
        passage="Róm 5,1–11",
        passage_text="Megigazulván tehát hit által…",
        sermon_main_idea="Békesség Istennel",
        generate_fn=_gen_factory(_mv_json(4, "deductive", "Érvelés.")),
        **base_kw,
    )
    if rb.recommended_path_type != "deductive" or len(rb.movements) != 4:
        errors.append("B/F: expected deductive with 4 movements")

    rc = suggest_sermon_path(
        passage="Zsolt 23",
        passage_text="Az Úr az én pásztorom…",
        sermon_main_idea="Isten gondviselő jelenléte",
        generate_fn=_gen_factory(_mv_json(5, "meditative", "Zsoltár.")),
        **base_kw,
    )
    if rc.recommended_path_type != "meditative" or len(rc.movements) != 5:
        errors.append("C/G: expected meditative with 5 movements")

    rd = suggest_sermon_path(
        passage="Mk 4,35–41",
        passage_text="Miért féltek ennyire?",
        sermon_main_idea="Jézus uralma a viharban",
        listener_tension={
            "sermon_tension": "Hit vs félelem a viharban",
            "promised_resolution": "Jézus jelenléte lecsendesíti a félelmet",
        },
        christ_centered_arc={"divine_gracious_action": "Jézus megszólal a viharban"},
        sermon_main_idea_status="approved",
        generate_fn=_gen_factory(_mv_json(3, "tension_to_gospel", "Feszültség.")),
    )
    if rd.recommended_path_type != "tension_to_gospel":
        errors.append("D: expected tension_to_gospel")

    rh = parse_sermon_path_suggestions(_mv_json(2, "mixed"))
    if len(rh.movements) != 2:
        errors.append("H: keep 2 movements")
    if not any("kevesebb" in w.casefold() or "3" in w for w in rh.warnings):
        errors.append("H: expected under-min warning")

    ri = parse_sermon_path_suggestions(_mv_json(6, "text_following"))
    if len(ri.movements) != 5:
        errors.append("I: expected max 5 movements")
    if not any("5" in w or "legfeljebb" in w.casefold() for w in ri.warnings):
        errors.append("I: expected trim warning")

    assess_json = (
        '{"overall_assessment":"Ismétlődő mozgások és gyenge átmenetek; '
        'az evangélium függelékként jelenik meg.",'
        '"strengths":["Van kiindulópont"],'
        '"improvements":["Kerüld az ismétlést","Erősítsd az átmeneteket",'
        '"Az evangélium ne legyen függelék"],'
        '"path_type_assessment":"Illik.",'
        '"structure_assessment":"Ismétlés van.",'
        '"gospel_turn_assessment":"Az evangélium csak az utolsó mondatban, függelékként.",'
        '"transition_assessment":"Hiányzó átmenetek.",'
        '"revised_path_rationale":"Jobb indoklás.",'
        '"revised_starting_point":"Pontosabb indulás.",'
        '"revised_destination":"Pontosabb megérkezés.",'
        '"revised_movements":['
        + ",".join(
            '{"title":"J%d","role":"deepening","core_content":"c","textual_basis":"t",'
            '"listener_discovery":"d","transition_to_next":"x"}' % i
            for i in range(1, 4)
        )
        + '],"warnings":["Ismétlés","Hiányzó átmenet","Evangélium függelékként"]}'
    )
    rj = assess_sermon_path(
        passage="Fil 2,1–11",
        sermon_path={"type": "deductive", "reason": "r", "starting_point": "s"},
        sermon_movements=[
            {"title": "Ugyanaz", "core_content": "A", "transition_to_next": ""},
            {"title": "Ugyanaz újra", "core_content": "A", "transition_to_next": ""},
            {"title": "Végén Jézus", "core_content": "B", "transition_to_next": ""},
        ],
        sermon_main_idea="Krisztus alázata",
        sermon_main_idea_status="approved",
        generate_fn=_gen_factory(assess_json),
    )
    if not rj.ok:
        errors.append("J/K/L: assess should ok")
    blob = (
        rj.overall_assessment
        + " "
        + " ".join(rj.improvements)
        + " "
        + rj.gospel_turn_assessment
        + " "
        + rj.transition_assessment
    ).casefold()
    if "ismétl" not in blob and "ismetl" not in blob:
        errors.append("J: expected repetition signal")
    if "átmenet" not in blob and "atmenet" not in blob:
        errors.append("K: expected transition signal")
    if "függelék" not in blob and "fuggalek" not in blob:
        errors.append("L: expected gospel-appendix signal")

    insuff = suggest_sermon_path(
        passage="Jn 3,16",
        sermon_main_idea="Isten szeretete",
        sermon_main_idea_status="draft",
        generate_fn=_gen_factory(narrative_json),
    )
    if "jóváhagyott igehirdetési fő gondolat" not in " ".join(
        insuff.missing_information
    ):
        errors.append("min input: missing approved sermon idea")

    bad = parse_sermon_path_suggestions("nem json")
    if bad.ok:
        errors.append("bad json should fail")

    if normalize_sermon_path_type("Narratív") != "narrative":
        errors.append("alias narrative")
    if movement_role_label("gospel_resolution") != "Evangéliumi feloldás":
        errors.append("role label")

    from sermon_workshop_data import normalize_sermon_workshop

    old = normalize_sermon_workshop({"sermon_main_idea": "régi"})
    if "starting_point" not in old["sermon_path"]:
        errors.append("N: old project missing starting_point default")
    if old["sermon_movements"] != []:
        errors.append("N: old movements should be empty list")
    if old.get("sermon_path_suggestions") is not None:
        errors.append("N: suggestions default None")

    mvs = normalize_sermon_movements(
        [
            {"title": "A", "core_content": "1"},
            {"title": "B", "core_content": "2"},
            {"title": "C", "core_content": "3"},
        ]
    )
    mvs[0], mvs[1] = mvs[1], mvs[0]
    if [m["title"] for m in mvs] != ["B", "A", "C"]:
        errors.append("Q: reorder failed")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("FAIL")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon path self-check OK")


__all__ = [
    "SERMON_PATH_TYPES",
    "SERMON_PATH_TYPE_LABELS_HU",
    "MOVEMENT_ROLES",
    "MOVEMENT_ROLE_LABELS_HU",
    "MIN_MOVEMENTS",
    "MAX_MOVEMENTS",
    "DEFAULT_MOVEMENT_COUNT",
    "SermonPathSuggestionResult",
    "SermonPathAssessmentResult",
    "SermonPathAlternative",
    "normalize_sermon_path_type",
    "sermon_path_type_label",
    "normalize_movement_role",
    "movement_role_label",
    "build_sermon_path_context",
    "has_sufficient_sermon_path_material",
    "build_sermon_path_suggest_prompt",
    "build_sermon_path_assess_prompt",
    "parse_sermon_path_suggestions",
    "parse_sermon_path_assessment",
    "suggest_sermon_path",
    "assess_sermon_path",
    "fallback_sermon_path_suggestion",
    "fallback_sermon_path_assessment",
]
