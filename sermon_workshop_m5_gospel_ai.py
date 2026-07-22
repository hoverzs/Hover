"""Igehirdetési műhely M5 — Krisztus-központú és evangéliumi ív MI.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
Újrafelhasználja az M5 hallgatói feszültség kontextusépítőjét.
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping

from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import (
    MISSING,
    _as_str_list,
    _as_text,
    _display,
    _is_api_error_text,
    _is_present,
    build_m5_context,
)

TAB_SUGGEST = "Evangéliumi ív — javaslat"
TAB_ASSESS = "Evangéliumi ív — értékelés"
DEFAULT_TEMPERATURE = 0.15

GenerateFn = Callable[..., str]

CHRIST_CONNECTION_TYPES = (
    "direct",
    "canonical",
    "redemptive_historical",
    "typological",
    "thematic",
    "implicit",
    "none_or_uncertain",
)

CHRIST_CONNECTION_TYPE_LABELS_HU: dict[str, str] = {
    "direct": "Közvetlen kapcsolat",
    "canonical": "Kánoni kapcsolat",
    "redemptive_historical": "Üdvtörténeti kapcsolat",
    "typological": "Tipológiai kapcsolat",
    "thematic": "Tematikus kapcsolat",
    "implicit": "Közvetett kapcsolat",
    "none_or_uncertain": "Nem állapítható meg felelősen",
}

CONFIDENCE_VALUES = ("high", "medium", "low")

M5_GOSPEL_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű, református asszisztense vagy.
Csak a megadott műhelyanyagból dolgozz. Ne találj ki bibliai szöveget,
keresztutalást, tipológiát vagy idézetet.
Válaszod KIZÁRÓLAG érvényes JSON legyen.\
"""

_LIMITS_EXTRA = {
    "christ_arc_block": 2400,
    "bible_translation": 80,
}


@dataclass
class GospelArcAlternativeConnection:
    christ_connection: str = ""
    connection_type: str = ""
    emphasis: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class GospelArcSuggestionResult:
    recommended_divine_gracious_action: str = ""
    recommended_christ_connection: str = ""
    recommended_christ_connection_type: str = "none_or_uncertain"
    recommended_promised_resolution: str = ""
    recommended_grace_enabled_response: str = ""
    expanded_summary: str = ""
    confidence: str = "low"
    alternative_connections: list[GospelArcAlternativeConnection] = field(
        default_factory=list
    )
    reasoning_summary: str = ""
    basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_ui_block(self) -> dict[str, str]:
        return {
            "divine_gracious_action": self.recommended_divine_gracious_action,
            "christ_connection": self.recommended_christ_connection,
            "christ_connection_type": self.recommended_christ_connection_type,
            "promised_resolution": self.recommended_promised_resolution,
            "grace_enabled_response": self.recommended_grace_enabled_response,
        }


@dataclass
class GospelArcAssessmentResult:
    overall_assessment: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    connection_type_assessment: str = ""
    revised_divine_gracious_action: str = ""
    revised_christ_connection: str = ""
    suggested_christ_connection_type: str = ""
    revised_promised_resolution: str = ""
    revised_grace_enabled_response: str = ""
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def revised_to_ui_block(self) -> dict[str, str]:
        return {
            "divine_gracious_action": self.revised_divine_gracious_action,
            "christ_connection": self.revised_christ_connection,
            "christ_connection_type": self.suggested_christ_connection_type,
            "promised_resolution": self.revised_promised_resolution,
            "grace_enabled_response": self.revised_grace_enabled_response,
        }


def normalize_christ_connection_type(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "kozvetlen": "direct",
        "közvetlen": "direct",
        "direct": "direct",
        "kanoni": "canonical",
        "kánoni": "canonical",
        "canonical": "canonical",
        "udvtorteneti": "redemptive_historical",
        "üdvtörténeti": "redemptive_historical",
        "redemptive_historical": "redemptive_historical",
        "tipologiai": "typological",
        "tipológiai": "typological",
        "typological": "typological",
        "tematikus": "thematic",
        "thematic": "thematic",
        "kozvetett": "implicit",
        "közvetett": "implicit",
        "implicit": "implicit",
        "none": "none_or_uncertain",
        "uncertain": "none_or_uncertain",
        "none_or_uncertain": "none_or_uncertain",
    }
    if raw in CHRIST_CONNECTION_TYPES:
        return raw
    return aliases.get(raw, "none_or_uncertain")


def christ_connection_type_label(value: Any) -> str:
    key = normalize_christ_connection_type(value)
    return CHRIST_CONNECTION_TYPE_LABELS_HU.get(
        key, CHRIST_CONNECTION_TYPE_LABELS_HU["none_or_uncertain"]
    )


def _format_christ_arc_block(raw: Any) -> str:
    if not isinstance(raw, dict):
        return MISSING
    labels = (
        ("divine_gracious_action", "Isten kegyelmi cselekvése"),
        ("christ_connection", "Krisztus-kapcsolat"),
        ("christ_connection_type", "Kapcsolat típusa"),
        ("promised_resolution", "Evangéliumi feloldás"),
        ("grace_enabled_response", "Kegyelemből fakadó válasz"),
    )
    lines: list[str] = []
    for key, label in labels:
        val = _as_text(raw.get(key))
        if not val:
            continue
        if key == "christ_connection_type":
            val = christ_connection_type_label(val)
        lines.append(f"{label}: {val}")
    if not lines:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS_EXTRA["christ_arc_block"])


def build_gospel_arc_context(
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
    exegesis: str = "",
    theology: str = "",
) -> dict[str, str]:
    """Evangéliumi ív kontextus — jóváhagyott főgondolatok elsőbbségével."""
    ctx = build_m5_context(
        passage=passage,
        passage_text=passage_text,
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
        exegesis=exegesis,
        theology=theology,
    )
    lt = listener_tension if isinstance(listener_tension, dict) else {}
    arc = christ_centered_arc if isinstance(christ_centered_arc, dict) else {}
    merged_arc = {
        "divine_gracious_action": arc.get("divine_gracious_action", ""),
        "christ_connection": arc.get("christ_connection", ""),
        "christ_connection_type": arc.get("christ_connection_type", ""),
        "promised_resolution": lt.get("promised_resolution", "")
        or arc.get("promised_resolution", ""),
        "grace_enabled_response": arc.get("grace_enabled_response", ""),
    }
    ctx["bible_translation"] = (
        _display(bible_translation, max_chars=_LIMITS_EXTRA["bible_translation"])
        if _is_present(bible_translation)
        else MISSING
    )
    ctx["christ_arc_block"] = _format_christ_arc_block(merged_arc)
    return ctx


def _has_approved_idea(ctx: Mapping[str, str]) -> bool:
    return _is_present(ctx.get("text_main_idea")) or _is_present(
        ctx.get("sermon_main_idea")
    )


def _has_tension_or_condition(ctx: Mapping[str, str]) -> bool:
    return _is_present(ctx.get("listener_tension_block", MISSING)) or _is_present(
        ctx.get("human_condition_block", MISSING)
    )


def _theological_bases(ctx: Mapping[str, str]) -> list[str]:
    keys = (
        ("passage_text", "bibliai szöveg (passage_text)"),
        ("approved_insights", "jóváhagyott felismerések"),
        ("theology", "teológiai elemzés"),
        ("exegesis", "exegézis"),
        ("human_condition_block", "emberi helyzet / kegyelmi válasz"),
    )
    present: list[str] = []
    for key, label in keys:
        if _is_present(ctx.get(key, MISSING)):
            present.append(label)
    return present


def _missing_gospel_labels(ctx: Mapping[str, str]) -> list[str]:
    missing: list[str] = []
    if not _is_present(ctx.get("passage", MISSING)):
        missing.append("igehely-megjelölés (passage)")
    if not _has_approved_idea(ctx):
        missing.append("jóváhagyott textus- vagy igehirdetési fő gondolat")
    if not _has_tension_or_condition(ctx):
        missing.append("központi feszültség vagy emberi helyzet")
    if not _theological_bases(ctx):
        missing.append(
            "további teológiai alap (passage_text, felismerés, teológia, "
            "exegézis vagy kegyelmi válasz)"
        )
    return missing


def has_sufficient_gospel_arc_material(ctx: Mapping[str, str]) -> bool:
    if not _is_present(ctx.get("passage", MISSING)):
        return False
    if not _has_approved_idea(ctx):
        return False
    if not _has_tension_or_condition(ctx):
        return False
    return bool(_theological_bases(ctx))


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


_SUGGEST_TEMPLATE = """\
Feladatod: a KRISZTUS-KÖZPONTÚ ÉS EVANGÉLIUMI ÍV megfogalmazása.

Ez NEM prédikációvázlat, NEM alkalmazáslista, NEM hallgatói kérdés újrírása.
Mutasd meg a prédikáció teológiai / evangéliumi feloldási ívét.

## Négy + egy megkülönböztetendő elem

1) Isten kegyelmi cselekvése (`recommended_divine_gracious_action`):
- mit tesz Isten a textusban, ígéretében vagy a teljes bibliai összefüggésben;
- NE csak azt írd, mit kell tennie az embernek;
- 1–3 mondat.

2) Krisztus-kapcsolat (`recommended_christ_connection`):
- hogyan kapcsolódik a textus Krisztus személyéhez, munkájához vagy evangéliumához;
- NE erőltesd a közvetlen kapcsolatot;
- ha nem megalapozható: röviden jelezd, és a típus legyen `none_or_uncertain`.

3) Kapcsolat típusa (`recommended_christ_connection_type`) — EGYÉRTÉLMŰEN az alábbiak egyike:
- `direct` — a textus közvetlenül Krisztusról / evangéliumáról beszél;
- `canonical` — a kapcsolat a kánon más, világosabb szakaszai révén jelenik meg;
- `redemptive_historical` — üdvtörténeti mozzanat, amely Krisztusban teljesedik ki;
- `typological` — megalapozott előremutatás; CSAK ha teológiailag védhető;
- `thematic` — a textus témája kapcsolódik az evangéliumhoz;
- `implicit` — közvetett, óvatos, kis bizonyosságú kapcsolat;
- `none_or_uncertain` — a rendelkezésre álló anyagból nem fogalmazható meg felelősen.

A közvetett / kánoni / üdvtörténeti kapcsolat NEM alacsonyabb rendű a közvetlennél.
NE állítsd, hogy minden textus közvetlenül Krisztusról beszél.

4) Evangéliumi feloldás (`recommended_promised_resolution`):
- hogyan válaszol Isten kegyelme a központi feszültségre;
- NE olcsó, gyors, fájdalommentes „Jézus a megoldás” lezárás;
- ha nincs megnevezhető feszültség: jelezd warningban, és hagyd óvatosan / üresen.

5) Kegyelemből fakadó válasz (`recommended_grace_enabled_response`):
- milyen emberi válasz válik lehetővé Isten cselekvése által;
- NE puszta kötelesség vagy moralizáló felszólítás;
- az ígéret / kegyelem előzze meg a felszólítást.

A három (kegyelmi cselekvés / feloldás / emberi válasz) NE legyen ugyanannak a mondatnak három változata.

## expanded_summary

3–5 rövid, összefüggő mondat: az ív hogyan kapcsolja össze a feszültséget,
Isten cselekedetét, a Krisztus-kapcsolatot és az emberi választ.
TILOS: prédikációvázlat, alkalmazáslista, az ajánlott mondatok szó szerinti ismétlése.

## Alternatívák

`alternative_connections`: legfeljebb 2 elem.
Mezők: christ_connection, connection_type, emphasis.
Csak valóban eltérő, teológiailag védhető irányok. Ha nincs: [].

## confidence

`high` | `medium` | `low` — a Krisztus-kapcsolat megalapozottságára.

## Tilalmak

- Krisztus nevének mechanikus hozzáadása;
- minden ÓSZ-rész közvetlen messiási próféciává alakítása;
- önkényes allegória / megalapozatlan tipológia;
- bibliai személyek/tárgyak automatikus Krisztus-jelképpé tétele;
- a textus történeti-irodalmi jelentésének megkerülése;
- kitalált keresztutalás vagy hamis idézet;
- erőltetett „Jézus a megoldás” lezárás;
- a kegyelem motivációs üzenetté egyszerűsítése;
- az emberi válasz kegyelemtől független moralizálása;
- azonnali, fájdalommentes feszültségfeloldás.

## Református hangsúlyok (tartalmi, nem szakkifejezésekkel)

Isten kezdeményező kegyelme; emberi válasz kegyelemből; Krisztus személye és műve;
Íge és Lélek; ígéret → felszólítás sorrend; üdvtörténeti / kánoni összefüggés;
megszentelődés mint kegyelemből fakadó valóság; közösségi dimenzió, ha indokolt.
A felhasználói kimenetben KERÜLD a szükségtelen dogmatikai zsargont.

## Elégtelen adat

Ha nincs elegendő alap: ajánlások üresek lehetnek; `missing_information` és
`warnings` legyen kitöltve; a típus lehet `none_or_uncertain`.
A passage_text hiánya önmagában NEM blokkol, ha van más teológiai alap.

## Bemenet

Igehely: {{passage}}
Bibliafordítás: {{bible_translation}}
Bibliai szöveg: {{passage_text}}
Alkalom: {{occasion}}
Felhasználói fókusz: {{user_focus}}
Textus fő gondolat (csak ha jóváhagyott): {{text_main_idea}}
Textus fő gondolat státusz: {{text_main_idea_status}}
Textus fő gondolat rövid kifejtése: {{text_expanded_summary}}
Jóváhagyott felismerések: {{approved_insights}}
Igehirdetési fő gondolat (csak ha jóváhagyott): {{sermon_main_idea}}
Igehirdetési fő gondolat státusz: {{sermon_main_idea_status}}
Igehirdetési fő gondolat rövid kifejtése: {{sermon_expanded_summary}}
Emberi helyzet és kegyelmi válasz: {{human_condition_block}}
Hallgatói kérdés / ellenállás / feszültség: {{listener_tension_block}}
Exegézis: {{exegesis}}
Teológia: {{theology}}

## Kimenet — KIZÁRÓLAG JSON

{
  "recommended_divine_gracious_action": "",
  "recommended_christ_connection": "",
  "recommended_christ_connection_type": "direct|canonical|redemptive_historical|typological|thematic|implicit|none_or_uncertain",
  "recommended_promised_resolution": "",
  "recommended_grace_enabled_response": "",
  "expanded_summary": "",
  "confidence": "high|medium|low",
  "alternative_connections": [],
  "reasoning_summary": "",
  "basis": [],
  "warnings": [],
  "missing_information": []
}
"""

_ASSESS_TEMPLATE = """\
Feladatod: a felhasználó KRISZTUS-KÖZPONTÚ ÉS EVANGÉLIUMI ÍV megfogalmazásának
értékelése. Ne írd felül automatikusan a felhasználó szövegét — javasolj.

## Vizsgáld

- világos-e Isten cselekvése (nem csak emberi feladat);
- textushű-e a Krisztus-kapcsolat;
- megfelelő-e a választott kapcsolattípus;
- erőltetett / allegorikus-e az összekapcsolás;
- válaszol-e a feloldás a központi feszültségre;
- a kegyelemből fakadó válasz tényleg a kegyelemből következik-e;
- nincs-e túl gyors / közhelyes lezárás;
- különbözik-e egymástól a kegyelmi cselekvés, a feloldás és az emberi válasz.

## Tilalmak (értékeléskor is)

Mechanikus krisztologizálás, megalapozatlan tipológia, moralizálás,
kitalált keresztutalás, olcsó evangéliumi lezárás.

## Bemenet

Igehely: {{passage}}
Bibliai szöveg: {{passage_text}}
Textus fő gondolat: {{text_main_idea}}
Igehirdetési fő gondolat: {{sermon_main_idea}}
Emberi helyzet / kegyelem: {{human_condition_block}}
Hallgatói feszültség: {{listener_tension_block}}
Felhasználó megfogalmazása: {{christ_arc_block}}
Exegézis: {{exegesis}}
Teológia: {{theology}}

## Kimenet — KIZÁRÓLAG JSON

{
  "overall_assessment": "",
  "strengths": [],
  "improvements": [],
  "connection_type_assessment": "",
  "revised_divine_gracious_action": "",
  "revised_christ_connection": "",
  "suggested_christ_connection_type": "direct|canonical|redemptive_historical|typological|thematic|implicit|none_or_uncertain",
  "revised_promised_resolution": "",
  "revised_grace_enabled_response": "",
  "warnings": []
}

A revised_* mezők csak akkor legyenek nem üresek, ha valódi javítást javasolsz.
"""


def build_gospel_arc_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_SUGGEST_TEMPLATE, ctx)


def build_gospel_arc_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_ASSESS_TEMPLATE, ctx)


def _call_gospel_generate(
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
            system_bundle=M5_GOSPEL_SYSTEM_BUNDLE,
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


def fallback_gospel_arc_suggestion(
    *,
    reasoning: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> GospelArcSuggestionResult:
    return GospelArcSuggestionResult(
        recommended_christ_connection_type="none_or_uncertain",
        confidence="low",
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_gospel_arc_assessment(
    *,
    overall: str = "",
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> GospelArcAssessmentResult:
    return GospelArcAssessmentResult(
        overall_assessment=overall
        or "Nem megítélhető — nincs elegendő értékelhető megfogalmazás.",
        warnings=list(warnings or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def _parse_alt_connections(raw: Any) -> list[GospelArcAlternativeConnection]:
    if not isinstance(raw, list):
        return []
    out: list[GospelArcAlternativeConnection] = []
    for item in raw[:2]:
        if not isinstance(item, dict):
            continue
        conn = _as_text(item.get("christ_connection"))
        ctype = normalize_christ_connection_type(item.get("connection_type"))
        emphasis = _as_text(item.get("emphasis"))
        if not (conn or emphasis):
            continue
        out.append(
            GospelArcAlternativeConnection(
                christ_connection=conn,
                connection_type=ctype,
                emphasis=emphasis,
            )
        )
    return out


def _normalize_confidence(value: Any) -> str:
    raw = _as_text(value).casefold()
    if raw in CONFIDENCE_VALUES:
        return raw
    return "low"


def parse_gospel_arc_suggestions(raw: str) -> GospelArcSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_gospel_arc_suggestion(
            reasoning="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_gospel_arc_suggestion(
            reasoning="A válasz nem dolgozható fel érvényes JSON-ként.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )
    divine = _as_text(obj.get("recommended_divine_gracious_action"))
    christ = _as_text(obj.get("recommended_christ_connection"))
    ctype = normalize_christ_connection_type(
        obj.get("recommended_christ_connection_type")
    )
    resolution = _as_text(obj.get("recommended_promised_resolution"))
    grace = _as_text(obj.get("recommended_grace_enabled_response"))
    expanded = _as_text(obj.get("expanded_summary"))
    if not (divine or christ or resolution or grace):
        expanded = ""
    return GospelArcSuggestionResult(
        recommended_divine_gracious_action=divine,
        recommended_christ_connection=christ,
        recommended_christ_connection_type=ctype,
        recommended_promised_resolution=resolution,
        recommended_grace_enabled_response=grace,
        expanded_summary=expanded,
        confidence=_normalize_confidence(obj.get("confidence")),
        alternative_connections=_parse_alt_connections(
            obj.get("alternative_connections")
        ),
        reasoning_summary=_as_text(obj.get("reasoning_summary")),
        basis=_as_str_list(obj.get("basis"), max_items=6),
        warnings=_as_str_list(obj.get("warnings")),
        missing_information=_as_str_list(obj.get("missing_information")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def parse_gospel_arc_assessment(raw: str) -> GospelArcAssessmentResult:
    if _is_api_error_text(raw):
        return fallback_gospel_arc_assessment(
            overall="Nem megítélhető — a modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_gospel_arc_assessment(
            overall="Nem megítélhető — érvénytelen JSON.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )
    suggested_type = _as_text(obj.get("suggested_christ_connection_type"))
    if suggested_type:
        suggested_type = normalize_christ_connection_type(suggested_type)
    return GospelArcAssessmentResult(
        overall_assessment=_as_text(obj.get("overall_assessment"))
        or "A modell nem adott összegző értékelést.",
        strengths=_as_str_list(obj.get("strengths"), max_items=4),
        improvements=_as_str_list(obj.get("improvements"), max_items=4),
        connection_type_assessment=_as_text(obj.get("connection_type_assessment")),
        revised_divine_gracious_action=_as_text(
            obj.get("revised_divine_gracious_action")
        ),
        revised_christ_connection=_as_text(obj.get("revised_christ_connection")),
        suggested_christ_connection_type=suggested_type,
        revised_promised_resolution=_as_text(obj.get("revised_promised_resolution")),
        revised_grace_enabled_response=_as_text(
            obj.get("revised_grace_enabled_response")
        ),
        warnings=_as_str_list(obj.get("warnings")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def suggest_gospel_arc(
    *,
    passage: str,
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
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> GospelArcSuggestionResult:
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
    missing = _missing_gospel_labels(ctx)
    if not _is_present(ctx["passage"]):
        return fallback_gospel_arc_suggestion(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_gospel_arc_material(ctx):
        return fallback_gospel_arc_suggestion(
            reasoning=(
                "Nincs elegendő jóváhagyott műhelyeredmény a felelős "
                "evangéliumi ív megfogalmazásához."
            ),
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres ajánlások."
            ],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_gospel_arc_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_gospel_arc_suggest_prompt(ctx)
    try:
        raw = _call_gospel_generate(
            generate_fn,
            prompt,
            tab_label=TAB_SUGGEST,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_gospel_arc_suggestion(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=["A javaslatkészítés nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    result = parse_gospel_arc_suggestions(raw or "")
    if result.ok and not _has_tension_or_condition(ctx):
        note = (
            "A központi feszültség / emberi helyzet hiányos; "
            "az evangéliumi feloldás nem fogalmazható meg megfelelően."
        )
        if note not in result.warnings:
            result.warnings = list(result.warnings) + [note]
    if result.ok and not _is_present(ctx.get("passage_text")):
        note = (
            "A teljes bibliai szöveg (passage_text) nem állt közvetlenül "
            "rendelkezésre; a javaslat a jóváhagyott műhelyeredményekből készült."
        )
        if note not in result.warnings and (
            result.recommended_divine_gracious_action
            or result.recommended_christ_connection
        ):
            result.warnings = list(result.warnings) + [note]
        label = "bibliai szöveg (passage_text)"
        if label not in result.missing_information:
            result.missing_information = list(result.missing_information) + [label]
    return result


def assess_gospel_arc(
    *,
    passage: str,
    christ_centered_arc: Any,
    listener_tension: Any = None,
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
    exegesis: str = "",
    theology: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> GospelArcAssessmentResult:
    arc = christ_centered_arc if isinstance(christ_centered_arc, dict) else {}
    lt = listener_tension if isinstance(listener_tension, dict) else {}
    filled = any(
        _as_text(arc.get(k))
        for k in (
            "divine_gracious_action",
            "christ_connection",
            "grace_enabled_response",
        )
    ) or _as_text(lt.get("promised_resolution")) or _as_text(
        arc.get("promised_resolution")
    )
    if not filled:
        return fallback_gospel_arc_assessment(
            overall="Nincs értékelhető megfogalmazás az evangéliumi ív mezőiben.",
            warnings=["Tölts ki legalább egy mezőt az értékeléshez."],
            ok=True,
        )

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
    if generate_fn is None:
        return fallback_gospel_arc_assessment(
            overall="Nem megítélhető — hiányzó generate_fn.",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_gospel_arc_assess_prompt(ctx)
    try:
        raw = _call_gospel_generate(
            generate_fn,
            prompt,
            tab_label=TAB_ASSESS,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_gospel_arc_assessment(
            overall="Az értékelés közben váratlan hiba történt.",
            warnings=["Az értékelés nem sikerült. Próbáld újra később."],
            error_message=str(exc),
            ok=False,
        )
    return parse_gospel_arc_assessment(raw or "")


def _self_check() -> list[str]:
    errors: list[str] = []

    def fake_generate(prompt: str, **kwargs: Any) -> str:  # noqa: ARG001
        if "értékelése" in prompt or "Felhasználó megfogalmazása" in prompt:
            return (
                '{"overall_assessment":"Moralizáló hangsúly.",'
                '"strengths":["Van feszültségérzékenység"],'
                '"improvements":["Isten cselekvése legyen első"],'
                '"connection_type_assessment":"Túl erőltetett tipológia",'
                '"revised_divine_gracious_action":"Isten megtartja az övéit.",'
                '"revised_christ_connection":"A megtartás Krisztusban teljesedik ki.",'
                '"suggested_christ_connection_type":"canonical",'
                '"revised_promised_resolution":"A feszültségre Isten hűsége válaszol.",'
                '"revised_grace_enabled_response":"A gyülekezet hittel épülhet.",'
                '"warnings":["Kerüld a moralizálást"]}'
            )
        return (
            '{"recommended_divine_gracious_action":"Isten szeretettel körülveszi az övéit.",'
            '"recommended_christ_connection":"Krisztus a gyülekezet feje és megtartója.",'
            '"recommended_christ_connection_type":"direct",'
            '"recommended_promised_resolution":"A feszültségre Isten megtartó kegyelme válaszol.",'
            '"recommended_grace_enabled_response":"A hallgató hittel ragaszkodhat Krisztushoz.",'
            '"expanded_summary":"A textus Isten megtartó szeretetét mutatja. '
            "A feszültség a romboló erők és a hit között áll. "
            'Krisztus közvetlenül jelenik meg mint megtartó.",'
            '"confidence":"high",'
            '"alternative_connections":[{"christ_connection":'
            '"A megtartás közösségi dimenziója.",'
            '"connection_type":"thematic","emphasis":"közösség"}],'
            '"reasoning_summary":"ÚSZ, közvetlen Krisztus-szöveg.",'
            '"basis":["jóváhagyott főgondolat","feszültség"],'
            '"warnings":[],"missing_information":[]}'
        )

    ra = suggest_gospel_arc(
        passage="Jn 15,1–8",
        passage_text="Én vagyok a szőlőtő...",
        text_main_idea="Krisztusban maradás",
        text_main_idea_status="approved",
        listener_tension={"sermon_tension": "Nehéz a megmaradás"},
        human_condition={"grace_response": "Isten megtart"},
        generate_fn=fake_generate,
    )
    if not ra.ok or ra.recommended_christ_connection_type != "direct":
        errors.append("A: expected direct connection")

    def ot_generate(prompt: str, **kwargs: Any) -> str:  # noqa: ARG001
        return (
            '{"recommended_divine_gracious_action":"Isten szabadítóan cselekszik.",'
            '"recommended_christ_connection":"A szabadítás Krisztusban teljesedik ki.",'
            '"recommended_christ_connection_type":"redemptive_historical",'
            '"recommended_promised_resolution":"Isten szabadítása ad reményt.",'
            '"recommended_grace_enabled_response":"A nép hálával járhat.",'
            '"expanded_summary":"Egy. Kettő. Három.",'
            '"confidence":"medium","alternative_connections":[],'
            '"reasoning_summary":"ÓSZ üdvtörténet","basis":["exegézis"],'
            '"warnings":[],"missing_information":[]}'
        )

    rb = suggest_gospel_arc(
        passage="2Móz 14",
        text_main_idea="Isten átvezeti népét",
        text_main_idea_status="approved",
        listener_tension={"sermon_tension": "Félelem a veszedelemben"},
        exegesis="A tengerátkelés szabadítás",
        generate_fn=ot_generate,
    )
    if rb.recommended_christ_connection_type == "direct":
        errors.append("B: OT should not be forced direct")
    if rb.recommended_christ_connection_type != "redemptive_historical":
        errors.append("B: expected redemptive_historical")

    def unc_generate(prompt: str, **kwargs: Any) -> str:  # noqa: ARG001
        return (
            '{"recommended_divine_gracious_action":"Isten bölcsességet ad.",'
            '"recommended_christ_connection":"",'
            '"recommended_christ_connection_type":"none_or_uncertain",'
            '"recommended_promised_resolution":"Isten bölcsessége vezet.",'
            '"recommended_grace_enabled_response":"Az ember kérhet bölcsességet.",'
            '"expanded_summary":"A kapcsolat további vizsgálatot igényel.",'
            '"confidence":"low","alternative_connections":[],'
            '"reasoning_summary":"Bizonytalan","basis":["teológia"],'
            '"warnings":["További teológiai vizsgálat szükséges"],'
            '"missing_information":[]}'
        )

    rf = suggest_gospel_arc(
        passage="Péld 3,5–6",
        sermon_main_idea="Bízz az Úrban",
        sermon_main_idea_status="approved",
        human_condition={"condition": "Önrendelkezés"},
        theology="Bölcsességi irodalom",
        generate_fn=unc_generate,
    )
    if rf.recommended_christ_connection_type != "none_or_uncertain":
        errors.append("F: expected none_or_uncertain")

    rg = suggest_gospel_arc(
        passage="Jn 3,16",
        text_main_idea="Isten szeretete",
        text_main_idea_status="approved",
        theology="kegyelem",
        generate_fn=fake_generate,
        skip_api_if_insufficient=True,
    )
    if rg.recommended_divine_gracious_action:
        errors.append("G: should not suggest without tension/condition")
    if not rg.missing_information:
        errors.append("G: expected missing info")

    rh = assess_gospel_arc(
        passage="Júd 17–20",
        christ_centered_arc={
            "divine_gracious_action": "",
            "christ_connection": "Júdás = Krisztus előképe",
            "christ_connection_type": "typological",
            "grace_enabled_response": "Legyél jobb ember",
        },
        listener_tension={
            "sermon_tension": "Feszültség",
            "promised_resolution": "Jézus a megoldás",
        },
        text_main_idea="Megmaradás",
        text_main_idea_status="approved",
        generate_fn=fake_generate,
    )
    if not rh.ok:
        errors.append("H: assess should ok")
    if "moral" not in rh.overall_assessment.casefold() and not rh.improvements:
        errors.append("H: expected moralizing signal")

    if normalize_christ_connection_type("Kánoni") != "canonical":
        errors.append("J: alias canonical")
    if not christ_connection_type_label("none_or_uncertain").startswith("Nem"):
        errors.append("J: uncertain label")

    bad = parse_gospel_arc_suggestions("nem json")
    if bad.ok:
        errors.append("bad json should fail")

    ctx = build_gospel_arc_context(
        passage="Fil 2,1–11",
        passage_text="Krisztus alázata",
        text_main_idea="Krisztus útja",
        text_main_idea_status="approved",
        listener_tension={"sermon_tension": "Önzés vs alázat"},
        theology="kenózis",
    )
    prompt = build_gospel_arc_suggest_prompt(ctx)
    if "{{passage}}" in prompt or "Fil 2" not in prompt:
        errors.append("placeholders not filled")

    # Régi projekt normalizálás (adatréteg)
    from sermon_workshop_data import normalize_sermon_workshop

    old = normalize_sermon_workshop({"sermon_main_idea": "x"})
    arc = old.get("christ_centered_arc") or {}
    for k in (
        "divine_gracious_action",
        "christ_connection",
        "christ_connection_type",
        "grace_enabled_response",
    ):
        if k not in arc:
            errors.append(f"old project missing {k}")
    if "gospel_arc_suggestions" not in old:
        errors.append("old project missing gospel_arc_suggestions")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("FAIL")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("OK sermon_workshop_m5_gospel_ai self-check passed")


__all__ = [
    "CHRIST_CONNECTION_TYPES",
    "CHRIST_CONNECTION_TYPE_LABELS_HU",
    "GospelArcAlternativeConnection",
    "GospelArcSuggestionResult",
    "GospelArcAssessmentResult",
    "normalize_christ_connection_type",
    "christ_connection_type_label",
    "build_gospel_arc_context",
    "has_sufficient_gospel_arc_material",
    "build_gospel_arc_suggest_prompt",
    "build_gospel_arc_assess_prompt",
    "parse_gospel_arc_suggestions",
    "parse_gospel_arc_assessment",
    "suggest_gospel_arc",
    "assess_gospel_arc",
]
