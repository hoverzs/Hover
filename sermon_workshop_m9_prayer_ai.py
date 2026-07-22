"""Igehirdetési műhely M9 — imádsági előkészítés MI.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
Nem generál teljes, felolvasható imádságot — imaívet, mondatmagokat
és a prédikátor saját gondolatainak beépítését segíti.
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sermon_workshop_data import (
    normalize_prayer_rewrite_mode,
    normalize_prayer_tone_preference,
)
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
from sermon_workshop_m7_closing_ai import build_closing_context

TAB_PRAYER = "Imádsági előkészítés"
DEFAULT_TEMPERATURE = 0.25

GenerateFn = Callable[..., str]

PRAYER_TONE_PREFERENCES = (
    "quiet_meditative",
    "honest_confessional",
    "hopeful",
    "assuring",
    "intercessory",
    "communal",
    "festive",
    "simple_direct",
    "biblical_imagery",
    "mixed",
)

PRAYER_TONE_PREFERENCE_LABELS_HU: dict[str, str] = {
    "quiet_meditative": "Csendes és meditatív",
    "honest_confessional": "Őszinte és bűnvalló",
    "hopeful": "Reménységgel teli",
    "assuring": "Megerősítő",
    "intercessory": "Közbenjáró",
    "communal": "Közösségi",
    "festive": "Ünnepélyes",
    "simple_direct": "Egyszerű és közvetlen",
    "biblical_imagery": "Bibliai képekre építő",
    "mixed": "Vegyes",
}

PRAYER_REWRITE_MODES = (
    "light_polish",
    "integrate_into_arc",
    "free_rephrase",
)

PRAYER_REWRITE_MODE_LABELS_HU: dict[str, str] = {
    "light_polish": "Csak nyelvileg finomítsa",
    "integrate_into_arc": "Rendezze és építse be az imaívbe",
    "free_rephrase": "Fogalmazza újra szabadabban",
}

BEFORE_MOVEMENT_FUNCTIONS = (
    "address",
    "silence",
    "confession",
    "illumination",
    "preacher",
    "hearers",
    "surrender",
)

AFTER_MOVEMENT_FUNCTIONS = (
    "gratitude",
    "confession",
    "gospel_trust",
    "request",
    "intercession",
    "response",
    "hope",
)

_LIMITS = {
    "prefs": 500,
    "side_block": 2000,
    "own_thoughts": 1800,
}


def prayer_tone_preference_label(value: str) -> str:
    key = normalize_prayer_tone_preference(value)
    return PRAYER_TONE_PREFERENCE_LABELS_HU.get(key, key)


def prayer_rewrite_mode_label(value: str) -> str:
    key = normalize_prayer_rewrite_mode(value)
    return PRAYER_REWRITE_MODE_LABELS_HU.get(key, key)


def normalize_before_movement_function(raw: Any) -> str:
    value = _as_text(raw).casefold()
    return value if value in BEFORE_MOVEMENT_FUNCTIONS else ""


def normalize_after_movement_function(raw: Any) -> str:
    value = _as_text(raw).casefold()
    return value if value in AFTER_MOVEMENT_FUNCTIONS else ""


@dataclass
class PrayerMovement:
    title: str = ""
    function: str = ""
    content_direction: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "function": self.function,
            "content_direction": self.content_direction,
        }


@dataclass
class IntegratedThought:
    original: str = ""
    refined: str = ""
    placement: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "original": self.original,
            "refined": self.refined,
            "placement": self.placement,
        }


@dataclass
class PrayerArcSuggestionResult:
    purpose: str = ""
    recommended_movements: list[PrayerMovement] = field(default_factory=list)
    opening_options: list[str] = field(default_factory=list)
    suggested_lines: list[str] = field(default_factory=list)
    closing_direction: str = ""
    integrated_user_thoughts: list[IntegratedThought] = field(default_factory=list)
    language_notes: list[str] = field(default_factory=list)
    cliche_risks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    side: str = "before"  # before | after
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose,
            "recommended_movements": [m.to_dict() for m in self.recommended_movements],
            "opening_options": list(self.opening_options),
            "suggested_lines": list(self.suggested_lines),
            "closing_direction": self.closing_direction,
            "integrated_user_thoughts": [
                t.to_dict() for t in self.integrated_user_thoughts
            ],
            "language_notes": list(self.language_notes),
            "cliche_risks": list(self.cliche_risks),
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "side": self.side,
            "ok": self.ok,
            "error_message": self.error_message,
        }

    def movements_as_notes(self) -> str:
        lines: list[str] = []
        for m in self.recommended_movements:
            title = m.title.strip()
            direction = m.content_direction.strip()
            if title and direction:
                lines.append(f"{title}: {direction}")
            elif title:
                lines.append(title)
            elif direction:
                lines.append(direction)
        return "\n".join(lines)


@dataclass
class PrayerAssessmentResult:
    overall_assessment: str = ""
    before_assessment: str = ""
    after_assessment: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    cliche_findings: list[str] = field(default_factory=list)
    text_connection_assessment: str = ""
    voice_assessment: str = ""
    revised_before_movements: list[dict[str, str]] = field(default_factory=list)
    revised_before_lines: list[str] = field(default_factory=list)
    revised_after_movements: list[dict[str, str]] = field(default_factory=list)
    revised_after_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_assessment": self.overall_assessment,
            "before_assessment": self.before_assessment,
            "after_assessment": self.after_assessment,
            "strengths": list(self.strengths),
            "improvements": list(self.improvements),
            "cliche_findings": list(self.cliche_findings),
            "text_connection_assessment": self.text_connection_assessment,
            "voice_assessment": self.voice_assessment,
            "revised_before_movements": list(self.revised_before_movements),
            "revised_before_lines": list(self.revised_before_lines),
            "revised_after_movements": list(self.revised_after_movements),
            "revised_after_lines": list(self.revised_after_lines),
            "warnings": list(self.warnings),
            "ok": self.ok,
            "error_message": self.error_message,
        }


def _format_prayer_prefs(
    *,
    tone_preference: str = "mixed",
    general_focus: str = "",
    rewrite_mode: str = "integrate_into_arc",
) -> str:
    lines = [
        f"Hangoltság: {prayer_tone_preference_label(tone_preference)}",
        f"Átalakítási mód: {prayer_rewrite_mode_label(rewrite_mode)}",
    ]
    focus = _as_text(general_focus)
    if focus:
        lines.append(f"Külön fókusz: {focus}")
    return _display("\n".join(lines), max_chars=_LIMITS["prefs"])


def _format_prayer_side(side: Any, *, label: str) -> str:
    block = side if isinstance(side, dict) else {}
    lines: list[str] = [f"=== {label} ==="]
    for key, title in (
        ("own_thoughts", "Saját gondolatok"),
        ("purpose", "Cél"),
        ("movement_notes", "Imaív"),
        ("selected_opening", "Kiválasztott indítás"),
        ("closing_direction", "Záró irány"),
    ):
        val = _as_text(block.get(key))
        if val:
            lines.append(f"{title}: {val}")
    selected = block.get("selected_lines")
    if isinstance(selected, list) and selected:
        lines.append("Kiválasztott mondatmagok:")
        for item in selected:
            s = _as_text(item)
            if s:
                lines.append(f"- {s}")
    elif _as_text(selected):
        lines.append(f"Kiválasztott mondatmagok: {_as_text(selected)}")
    if len(lines) == 1:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS["side_block"])


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        if key.startswith("_"):
            continue
        out = out.replace("{{" + key + "}}", value)
    return out


def _has_gospel_resolution(
    *,
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
) -> bool:
    arc = christ_centered_arc if isinstance(christ_centered_arc, dict) else {}
    lt = listener_tension if isinstance(listener_tension, dict) else {}
    return bool(
        _is_present(arc.get("divine_gracious_action"))
        or _is_present(lt.get("promised_resolution"))
    )


def has_sufficient_before_material(
    *,
    passage: str = "",
    passage_text: str = "",
    text_main_idea: str = "",
) -> bool:
    if not _is_present(passage):
        return False
    return _is_present(text_main_idea) or _is_present(passage_text)


def has_sufficient_after_material(
    *,
    passage: str = "",
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
) -> bool:
    if not _is_present(passage):
        return False
    if sermon_main_idea_status.strip().casefold() != "approved":
        return False
    if not _is_present(sermon_main_idea):
        return False
    return _has_gospel_resolution(
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    )


_COMMON_GUARDRAILS = """\
## Általános tilalmak

- NE írj teljes, felolvasható imádságot vagy több bekezdéses liturgiai szöveget.
- NE írj hosszú könyörgést; a kimenet imaív + mondatmagok legyen.
- A mondatmagok legyenek teljes, használható mondatok, de NE álljanak össze
  automatikusan kész imádsággá.
- Kerüld a sablonos, bármely istentiszteleten felcserélhető fordulatokat
  (pl. „ebben a rohanó világban”, „légy velünk”, „áldd meg mindazokat”,
  „add, hogy mindig”, „vigyük magunkkal ezt az üzenetet”), ha nincs
  világos textusbeli okuk — jelezd a `cliche_risks` mezőben.
- Kerüld a hallgatók megszégyenítését, az imába rejtett prédikációt/kioktatást,
  személyekre célzó utalást, manipuláló bűntudatkeltést, túlzó ígéretet,
  pszichológiai diagnózist, érzéketlen traumaemlítést.
- Ne gyárts kitalált bibliai idézetet; a textus szavait ne idézd szó szerint
  hosszasan.
- Az imamondatok Istenhez szóljanak, ne a gyülekezethez intézett rejtett
  beszédként.
- Őrizd a prédikátor saját hangját; ne tedd felismerhetetlenné a saját
  gondolatokat.
"""


_BEFORE_TEMPLATE = """\
Feladatod: IGEHIRDETÉS ELŐTTI imádsági ív és mondatmagok javaslata.

Az előtti ima feladata: Isten megszólítása, elcsendesedés, az Ige hallására
való megnyílás, a Szentlélek munkájának kérése, az igehirdető és a gyülekezet
Isten Igéje alá helyezése. Alázat, őszinteség, befogadás.

TILOS:
- előre elmondani a teljes prédikációt;
- előre feloldani a központi feszültséget;
- teljes kész imádságot írni.

Mozzanat-funkciók (function):
address | silence | confession | illumination | preacher | hearers | surrender

Korlátok: 3–6 movement; 2–4 opening_options; 4–7 suggested_lines.

""" + _COMMON_GUARDRAILS + """

## Beállítások
{{prayer_prefs}}

## Műhelyanyag (korlátozott — ne használd a teljes lezárást / alkalmazást)

Igehely: {{passage}}
Fordítás: {{bible_translation}}
Bibliai szöveg:
{{passage_text}}

Textusfőgondolat: {{text_main_idea}}
Kifejtés: {{text_expanded_summary}}
Felismerések: {{approved_insights}}

Igehirdetési fő gondolat: {{sermon_main_idea}}

Emberi helyzet:
{{human_condition_block}}

Hallgatói kérdés / feszültség:
{{listener_tension_block}}

Saját imádsági gondolatok (előtti):
{{own_thoughts}}

Kézi imaív / cél (ha van):
{{side_block}}

## JSON-séma (csak ezt add vissza)

{
  "purpose": "",
  "recommended_movements": [
    {"title": "", "function": "", "content_direction": ""}
  ],
  "opening_options": [],
  "suggested_lines": [],
  "closing_direction": "",
  "integrated_user_thoughts": [
    {"original": "", "refined": "", "placement": ""}
  ],
  "language_notes": [],
  "cliche_risks": [],
  "warnings": [],
  "missing_information": []
}
"""


_AFTER_TEMPLATE = """\
Feladatod: IGEHIRDETÉS UTÁNI imádsági ív és mondatmagok javaslata.

Az utáni ima feladata: válasz a hallott Igére, hála, indokolt bűnvallás,
ráhagyatkozás Isten kegyelmi cselekvésére, kérés a kegyelemből fakadó
válaszhoz, közbenjárás, reménység és bizalom.

TILOS:
- mini-prédikációként megismételni az igehirdetést;
- teljes kész imádságot írni;
- kegyelem nélküli moralizáló felszólítást adni.

Mozzanat-funkciók (function):
gratitude | confession | gospel_trust | request | intercession | response | hope

Korlátok: 3–7 movement; 2–4 opening_options; 4–8 suggested_lines.

""" + _COMMON_GUARDRAILS + """

## Beállítások
{{prayer_prefs}}

## Műhelyanyag

Igehely: {{passage}}
Fordítás: {{bible_translation}}
Bibliai szöveg:
{{passage_text}}

Textusfőgondolat: {{text_main_idea}}
Igehirdetési fő gondolat: {{sermon_main_idea}}
Kifejtés: {{sermon_expanded_summary}}

Emberi helyzet:
{{human_condition_block}}

Hallgatói kérdés és feszültség:
{{listener_tension_block}}

Evangéliumi ív:
{{christ_arc_block}}

Megérkezési pont / út:
{{sermon_path_block}}

Alkalmazási irányok:
{{applications_block}}

Lezárás (végső felismerés / bizonyosság / hangnem):
{{closing_block}}

Saját imádsági gondolatok (utáni):
{{own_thoughts}}

Kézi imaív / cél (ha van):
{{side_block}}

## JSON-séma (csak ezt add vissza)

{
  "purpose": "",
  "recommended_movements": [
    {"title": "", "function": "", "content_direction": ""}
  ],
  "opening_options": [],
  "suggested_lines": [],
  "closing_direction": "",
  "integrated_user_thoughts": [
    {"original": "", "refined": "", "placement": ""}
  ],
  "language_notes": [],
  "cliche_risks": [],
  "warnings": [],
  "missing_information": []
}
"""


_INTEGRATE_TEMPLATE = """\
Feladatod: a prédikátor SAJÁT imádsági gondolatainak beépítése
az {{side_label}} imádságba.

Átalakítási mód: {{rewrite_mode_label}} ({{rewrite_mode}})

- light_polish: csak nyelvi finomítás; tartsd meg a szókincset és hangsúlyt.
- integrate_into_arc: rendezd és helyezd el az imaívben; maradjon felismerhető.
- free_rephrase: frissebb megfogalmazás, de tartalmi hűség; jelezd a jelentős
  átalakításokat.

Ne keverd össze az előtti és utáni gondolatokat.
Ne írj teljes imádságot.
Ha egy gondolat prédikációs állítás, közlemény, túl érzékeny, vagy nem illik
az imába: ne töröld csendben — jelezd a warnings / language_notes mezőben.

""" + _COMMON_GUARDRAILS + """

## Beállítások
{{prayer_prefs}}

Igehely: {{passage}}
Textusfőgondolat: {{text_main_idea}}
Igehirdetési fő gondolat: {{sermon_main_idea}}

Saját gondolatok (csak ez az oldal):
{{own_thoughts}}

Jelenlegi kézi terv:
{{side_block}}

## JSON-séma

{
  "purpose": "",
  "recommended_movements": [
    {"title": "", "function": "", "content_direction": ""}
  ],
  "opening_options": [],
  "suggested_lines": [],
  "closing_direction": "",
  "integrated_user_thoughts": [
    {"original": "", "refined": "", "placement": ""}
  ],
  "language_notes": [],
  "cliche_risks": [],
  "warnings": [],
  "missing_information": []
}
"""


_ASSESS_TEMPLATE = """\
Feladatod: az imádsági terv értékelése (előtti ÉS utáni külön).

Vizsgáld:
- világos-e az imaív; nem lett-e kész prédikáció;
- Istenhez szól-e; kapcsolódik-e a textushoz;
- sablonos-e; ismétlődnek-e a fordulatok / mondatkezdések;
- az előtti ima nem mondja-e el előre a feloldást;
- az utáni ima nem ismétli-e mini-prédikációként az üzenetet;
- jelen van-e a kegyelem; pásztorilag érzékeny-e;
- megmarad-e a prédikátor saját hangja;
- túl költői-e a nyelv.

A revised_* mezők CSAK javaslatok — ne írd felül automatikusan a kézi munkát.
Ne írj teljes imádságot.

""" + _COMMON_GUARDRAILS + """

## Beállítások
{{prayer_prefs}}

Igehely: {{passage}}
Bibliai szöveg:
{{passage_text}}

Textusfőgondolat: {{text_main_idea}}
Igehirdetési fő gondolat: {{sermon_main_idea}}

Evangéliumi ív:
{{christ_arc_block}}

Előtti terv:
{{before_block}}

Utáni terv:
{{after_block}}

## JSON-séma

{
  "overall_assessment": "",
  "before_assessment": "",
  "after_assessment": "",
  "strengths": [],
  "improvements": [],
  "cliche_findings": [],
  "text_connection_assessment": "",
  "voice_assessment": "",
  "revised_before_movements": [],
  "revised_before_lines": [],
  "revised_after_movements": [],
  "revised_after_lines": [],
  "warnings": []
}
"""


def build_prayer_before_context(
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
    exegesis: str = "",
    theology: str = "",
    tone_preference: str = "mixed",
    general_focus: str = "",
    rewrite_mode: str = "integrate_into_arc",
    prayer_before: Any = None,
) -> dict[str, str]:
    # Előtti: korlátozott kontextus — zárás/alkalmazás nélkül.
    # A textusfőgondolatot akkor is átadjuk, ha még nem approved (imaívet szolgál).
    ctx = build_m5_context(
        passage=passage,
        passage_text=passage_text,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        text_main_idea_status="approved" if _is_present(text_main_idea) else "",
        text_expanded_summary=text_expanded_summary,
        approved_insights=approved_insights,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=(
            "approved" if _is_present(sermon_main_idea) else sermon_main_idea_status
        ),
        sermon_expanded_summary=sermon_expanded_summary,
        human_condition=human_condition,
        listener_tension=listener_tension,
        exegesis=exegesis,
        theology=theology,
    )
    # Hallgatói ellenállást / feloldást ne hangsúlyozzuk az előtti imában:
    # a feszültség blokk megmaradhat, de a prompt tiltja a feloldást.
    ctx["bible_translation"] = (
        _display(bible_translation, max_chars=80)
        if _is_present(bible_translation)
        else MISSING
    )
    before = prayer_before if isinstance(prayer_before, dict) else {}
    ctx["own_thoughts"] = (
        _display(before.get("own_thoughts"), max_chars=_LIMITS["own_thoughts"])
        if _is_present(before.get("own_thoughts"))
        else MISSING
    )
    ctx["side_block"] = _format_prayer_side(before, label="Igehirdetés előtti imádság")
    ctx["prayer_prefs"] = _format_prayer_prefs(
        tone_preference=tone_preference,
        general_focus=general_focus,
        rewrite_mode=rewrite_mode,
    )
    ctx["side_label"] = "igehirdetés előtti"
    ctx["rewrite_mode"] = normalize_prayer_rewrite_mode(rewrite_mode)
    ctx["rewrite_mode_label"] = prayer_rewrite_mode_label(rewrite_mode)
    return ctx


def build_prayer_after_context(
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
    selected_images: Any = None,
    illustrations: Any = None,
    applications: Any = None,
    closing: Any = None,
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    tone_preference: str = "mixed",
    general_focus: str = "",
    rewrite_mode: str = "integrate_into_arc",
    prayer_after: Any = None,
) -> dict[str, str]:
    ctx = build_closing_context(
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
        selected_images=selected_images,
        illustrations=illustrations,
        applications=applications,
        closing=closing,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre,
    )
    after = prayer_after if isinstance(prayer_after, dict) else {}
    ctx["own_thoughts"] = (
        _display(after.get("own_thoughts"), max_chars=_LIMITS["own_thoughts"])
        if _is_present(after.get("own_thoughts"))
        else MISSING
    )
    ctx["side_block"] = _format_prayer_side(after, label="Igehirdetés utáni imádság")
    ctx["prayer_prefs"] = _format_prayer_prefs(
        tone_preference=tone_preference,
        general_focus=general_focus,
        rewrite_mode=rewrite_mode,
    )
    ctx["side_label"] = "igehirdetés utáni"
    ctx["rewrite_mode"] = normalize_prayer_rewrite_mode(rewrite_mode)
    ctx["rewrite_mode_label"] = prayer_rewrite_mode_label(rewrite_mode)
    return ctx


def build_prayer_assess_context(**kwargs: Any) -> dict[str, str]:
    before = kwargs.pop("prayer_before", None)
    after = kwargs.pop("prayer_after", None)
    tone = kwargs.pop("tone_preference", "mixed")
    focus = kwargs.pop("general_focus", "")
    mode = kwargs.pop("rewrite_mode", "integrate_into_arc")
    ctx = build_closing_context(**kwargs)
    ctx["before_block"] = _format_prayer_side(
        before, label="Igehirdetés előtti imádság"
    )
    ctx["after_block"] = _format_prayer_side(
        after, label="Igehirdetés utáni imádság"
    )
    ctx["prayer_prefs"] = _format_prayer_prefs(
        tone_preference=tone,
        general_focus=focus,
        rewrite_mode=mode,
    )
    return ctx


def _call_prayer_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
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
            tab_label=TAB_PRAYER,
            use_cache=False,
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


def _parse_movements(
    raw: Any,
    *,
    side: str,
    min_n: int,
    max_n: int,
) -> list[PrayerMovement]:
    if not isinstance(raw, list):
        return []
    out: list[PrayerMovement] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fn_raw = item.get("function")
        function = (
            normalize_before_movement_function(fn_raw)
            if side == "before"
            else normalize_after_movement_function(fn_raw)
        )
        mov = PrayerMovement(
            title=_as_text(item.get("title")),
            function=function,
            content_direction=_as_text(item.get("content_direction")),
        )
        if mov.title or mov.content_direction:
            out.append(mov)
        if len(out) >= max_n:
            break
    return out


def _parse_integrated(raw: Any) -> list[IntegratedThought]:
    if not isinstance(raw, list):
        return []
    out: list[IntegratedThought] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        thought = IntegratedThought(
            original=_as_text(item.get("original")),
            refined=_as_text(item.get("refined")),
            placement=_as_text(item.get("placement")),
        )
        if thought.original or thought.refined:
            out.append(thought)
        if len(out) >= 12:
            break
    return out


def fallback_prayer_arc(
    *,
    side: str = "before",
    reasoning: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    ok: bool = True,
    raw_response: str = "",
) -> PrayerArcSuggestionResult:
    notes = list(warnings or [])
    if reasoning and reasoning not in notes:
        notes.append(reasoning)
    return PrayerArcSuggestionResult(
        side=side,
        warnings=notes,
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def parse_prayer_arc_response(
    raw: str,
    *,
    side: str = "before",
) -> PrayerArcSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_prayer_arc(
            side=side,
            reasoning="Az API hibát jelzett.",
            warnings=["API hiba az imádsági javaslat során."],
            error_message=_as_text(raw)[:280],
            ok=False,
            raw_response=raw or "",
        )
    try:
        obj = extract_json_object(raw)
    except Exception:
        return fallback_prayer_arc(
            side=side,
            reasoning="A válasz nem volt érvényes JSON.",
            warnings=["Hibás JSON — üres javaslatok biztonsági alapértékekkel."],
            error_message="Hibás JSON az imádsági javaslatban.",
            ok=False,
            raw_response=raw or "",
        )
    if not isinstance(obj, dict):
        return fallback_prayer_arc(
            side=side,
            reasoning="A JSON nem objektum.",
            warnings=["Érvénytelen JSON-struktúra."],
            error_message="Érvénytelen JSON-struktúra.",
            ok=False,
            raw_response=raw or "",
        )

    max_mov = 6 if side == "before" else 7
    min_mov = 3
    max_open = 4
    max_lines = 7 if side == "before" else 8

    movements = _parse_movements(
        obj.get("recommended_movements"),
        side=side,
        min_n=min_mov,
        max_n=max_mov,
    )
    openings = _as_str_list(obj.get("opening_options"), max_items=max_open)
    lines = _as_str_list(obj.get("suggested_lines"), max_items=max_lines)

    return PrayerArcSuggestionResult(
        purpose=_as_text(obj.get("purpose")),
        recommended_movements=movements,
        opening_options=openings,
        suggested_lines=lines,
        closing_direction=_as_text(obj.get("closing_direction")),
        integrated_user_thoughts=_parse_integrated(
            obj.get("integrated_user_thoughts")
        ),
        language_notes=_as_str_list(obj.get("language_notes")),
        cliche_risks=_as_str_list(obj.get("cliche_risks")),
        warnings=_as_str_list(obj.get("warnings")),
        missing_information=_as_str_list(obj.get("missing_information")),
        side=side,
        ok=True,
        raw_response=raw or "",
    )


def parse_prayer_assessment_response(raw: str) -> PrayerAssessmentResult:
    if _is_api_error_text(raw):
        return PrayerAssessmentResult(
            overall_assessment="Az API hibát jelzett.",
            warnings=["API hiba az imádsági értékelés során."],
            ok=False,
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
        )
    try:
        obj = extract_json_object(raw)
    except Exception:
        return PrayerAssessmentResult(
            overall_assessment="A válasz nem volt érvényes JSON.",
            warnings=["Hibás JSON — üres értékelés biztonsági alapértékekkel."],
            ok=False,
            error_message="Hibás JSON az imádsági értékelésben.",
            raw_response=raw or "",
        )
    if not isinstance(obj, dict):
        return PrayerAssessmentResult(
            overall_assessment="A JSON nem objektum.",
            warnings=["Érvénytelen JSON-struktúra."],
            ok=False,
            error_message="Érvénytelen JSON-struktúra.",
            raw_response=raw or "",
        )

    def _mov_list(key: str) -> list[dict[str, str]]:
        raw_list = obj.get(key)
        if not isinstance(raw_list, list):
            return []
        out: list[dict[str, str]] = []
        for item in raw_list[:8]:
            if isinstance(item, dict):
                out.append(
                    {
                        "title": _as_text(item.get("title")),
                        "function": _as_text(item.get("function")),
                        "content_direction": _as_text(item.get("content_direction")),
                    }
                )
            elif _as_text(item):
                out.append(
                    {"title": _as_text(item), "function": "", "content_direction": ""}
                )
        return out

    return PrayerAssessmentResult(
        overall_assessment=_as_text(obj.get("overall_assessment")),
        before_assessment=_as_text(obj.get("before_assessment")),
        after_assessment=_as_text(obj.get("after_assessment")),
        strengths=_as_str_list(obj.get("strengths")),
        improvements=_as_str_list(obj.get("improvements")),
        cliche_findings=_as_str_list(obj.get("cliche_findings")),
        text_connection_assessment=_as_text(obj.get("text_connection_assessment")),
        voice_assessment=_as_text(obj.get("voice_assessment")),
        revised_before_movements=_mov_list("revised_before_movements"),
        revised_before_lines=_as_str_list(obj.get("revised_before_lines"), max_items=8),
        revised_after_movements=_mov_list("revised_after_movements"),
        revised_after_lines=_as_str_list(obj.get("revised_after_lines"), max_items=8),
        warnings=_as_str_list(obj.get("warnings")),
        ok=True,
        raw_response=raw or "",
    )


def _strip_false_passage_warnings(
    result: PrayerArcSuggestionResult,
    *,
    passage_text: str,
) -> PrayerArcSuggestionResult:
    if not result.ok or not _is_present(passage_text):
        return result
    result.warnings = [
        w for w in result.warnings if "passage_text" not in w.casefold()
    ]
    result.missing_information = [
        m for m in result.missing_information if "passage_text" not in m.casefold()
    ]
    return result


def suggest_prayer_before(
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
    exegesis: str = "",
    theology: str = "",
    tone_preference: str = "mixed",
    general_focus: str = "",
    rewrite_mode: str = "integrate_into_arc",
    prayer_before: Any = None,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
    **_ignored: Any,
) -> PrayerArcSuggestionResult:
    ctx = build_prayer_before_context(
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
        exegesis=exegesis,
        theology=theology,
        tone_preference=tone_preference,
        general_focus=general_focus,
        rewrite_mode=rewrite_mode,
        prayer_before=prayer_before,
    )
    missing: list[str] = []
    if not _is_present(passage):
        missing.append("alapigehely")
    if not (_is_present(text_main_idea) or _is_present(passage_text)):
        missing.append("textusfőgondolat vagy passage_text")

    if not _is_present(passage):
        return fallback_prayer_arc(
            side="before",
            reasoning="Nincs megadva igehely; előtti imaív nem indítható.",
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_before_material(
        passage=passage,
        passage_text=passage_text,
        text_main_idea=text_main_idea,
    ):
        return fallback_prayer_arc(
            side="before",
            reasoning=(
                "Nincs elegendő adat a felelős előtti imaívhez. "
                "Ne készüljön általános sablon."
            ),
            warnings=["Elégtelen adat: üres ajánlások."],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_prayer_arc(
            side="before",
            reasoning="Nincs bekötött generate_fn.",
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = _fill(_BEFORE_TEMPLATE, ctx)
    try:
        raw = _call_prayer_generate(generate_fn, prompt, temperature=temperature)
    except Exception as exc:
        return fallback_prayer_arc(
            side="before",
            reasoning="A Gemini-hívás sikertelen volt.",
            warnings=[f"Generálási hiba: {exc}"],
            missing=missing,
            error_message=str(exc)[:280],
            ok=False,
        )
    result = parse_prayer_arc_response(raw, side="before")
    for item in missing:
        if item not in result.missing_information:
            result.missing_information.append(item)
    return _strip_false_passage_warnings(result, passage_text=passage_text)


def suggest_prayer_after(
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
    selected_images: Any = None,
    illustrations: Any = None,
    applications: Any = None,
    closing: Any = None,
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    tone_preference: str = "mixed",
    general_focus: str = "",
    rewrite_mode: str = "integrate_into_arc",
    prayer_after: Any = None,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
    **_ignored: Any,
) -> PrayerArcSuggestionResult:
    ctx = build_prayer_after_context(
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
        selected_images=selected_images,
        illustrations=illustrations,
        applications=applications,
        closing=closing,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
        tone_preference=tone_preference,
        general_focus=general_focus,
        rewrite_mode=rewrite_mode,
        prayer_after=prayer_after,
    )
    missing: list[str] = []
    if not _is_present(passage):
        missing.append("alapigehely")
    if sermon_main_idea_status.strip().casefold() != "approved" or not _is_present(
        sermon_main_idea
    ):
        missing.append("jóváhagyott igehirdetési fő gondolat")
    if not _has_gospel_resolution(
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    ):
        missing.append("evangéliumi feloldás vagy Isten kegyelmi cselekvése")

    if not _is_present(passage):
        return fallback_prayer_arc(
            side="after",
            reasoning="Nincs megadva igehely; utáni imaív nem indítható.",
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_after_material(
        passage=passage,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    ):
        return fallback_prayer_arc(
            side="after",
            reasoning=(
                "Nincs elegendő adat a felelős utáni imaívhez. "
                "Ne készüljön általános sablon."
            ),
            warnings=["Elégtelen adat: üres ajánlások."],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_prayer_arc(
            side="after",
            reasoning="Nincs bekötött generate_fn.",
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = _fill(_AFTER_TEMPLATE, ctx)
    try:
        raw = _call_prayer_generate(generate_fn, prompt, temperature=temperature)
    except Exception as exc:
        return fallback_prayer_arc(
            side="after",
            reasoning="A Gemini-hívás sikertelen volt.",
            warnings=[f"Generálási hiba: {exc}"],
            missing=missing,
            error_message=str(exc)[:280],
            ok=False,
        )
    result = parse_prayer_arc_response(raw, side="after")
    for item in missing:
        if item not in result.missing_information:
            result.missing_information.append(item)
    return _strip_false_passage_warnings(result, passage_text=passage_text)


def integrate_prayer_thoughts(
    *,
    side: str = "before",
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
    selected_images: Any = None,
    illustrations: Any = None,
    applications: Any = None,
    closing: Any = None,
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    tone_preference: str = "mixed",
    general_focus: str = "",
    rewrite_mode: str = "integrate_into_arc",
    prayer_before: Any = None,
    prayer_after: Any = None,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    **_ignored: Any,
) -> PrayerArcSuggestionResult:
    side_key = "before" if side != "after" else "after"
    side_block = prayer_before if side_key == "before" else prayer_after
    own = ""
    if isinstance(side_block, dict):
        own = _as_text(side_block.get("own_thoughts"))
    if not own:
        return fallback_prayer_arc(
            side=side_key,
            reasoning="Nincs saját imádsági gondolat a beépítéshez.",
            warnings=["Add meg a saját gondolatokat az adott imához."],
            error_message="Hiányzó saját gondolatok.",
            ok=False,
        )
    if side_key == "before":
        ctx = build_prayer_before_context(
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
            exegesis=exegesis,
            theology=theology,
            tone_preference=tone_preference,
            general_focus=general_focus,
            rewrite_mode=rewrite_mode,
            prayer_before=prayer_before,
        )
    else:
        ctx = build_prayer_after_context(
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
            selected_images=selected_images,
            illustrations=illustrations,
            applications=applications,
            closing=closing,
            exegesis=exegesis,
            theology=theology,
            literary_genre=literary_genre or exegesis,
            tone_preference=tone_preference,
            general_focus=general_focus,
            rewrite_mode=rewrite_mode,
            prayer_after=prayer_after,
        )
    if generate_fn is None:
        return fallback_prayer_arc(
            side=side_key,
            reasoning="Nincs bekötött generate_fn.",
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = _fill(_INTEGRATE_TEMPLATE, ctx)
    try:
        raw = _call_prayer_generate(generate_fn, prompt, temperature=temperature)
    except Exception as exc:
        return fallback_prayer_arc(
            side=side_key,
            reasoning="A Gemini-hívás sikertelen volt.",
            warnings=[f"Generálási hiba: {exc}"],
            error_message=str(exc)[:280],
            ok=False,
        )
    result = parse_prayer_arc_response(raw, side=side_key)
    return _strip_false_passage_warnings(result, passage_text=passage_text)


def assess_prayer_preparation(
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
    selected_images: Any = None,
    illustrations: Any = None,
    applications: Any = None,
    closing: Any = None,
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    tone_preference: str = "mixed",
    general_focus: str = "",
    rewrite_mode: str = "integrate_into_arc",
    prayer_before: Any = None,
    prayer_after: Any = None,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    **_ignored: Any,
) -> PrayerAssessmentResult:
    before = prayer_before if isinstance(prayer_before, dict) else {}
    after = prayer_after if isinstance(prayer_after, dict) else {}
    has_content = any(
        _is_present(before.get(k)) or _is_present(after.get(k))
        for k in (
            "own_thoughts",
            "purpose",
            "movement_notes",
            "selected_opening",
            "closing_direction",
        )
    ) or bool(before.get("selected_lines")) or bool(after.get("selected_lines"))
    if not has_content:
        return PrayerAssessmentResult(
            overall_assessment="Nincs értékelhető imádsági terv.",
            warnings=["Tölts ki legalább egy előtti vagy utáni mezőt."],
            ok=False,
            error_message="Üres imádsági terv.",
        )
    ctx = build_prayer_assess_context(
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
        selected_images=selected_images,
        illustrations=illustrations,
        applications=applications,
        closing=closing,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
        tone_preference=tone_preference,
        general_focus=general_focus,
        rewrite_mode=rewrite_mode,
        prayer_before=prayer_before,
        prayer_after=prayer_after,
    )
    if generate_fn is None:
        return PrayerAssessmentResult(
            overall_assessment="Nincs bekötött generate_fn.",
            warnings=["generate_fn nélkül nem indítható értékelés."],
            ok=False,
            error_message="Hiányzó generate_fn.",
        )
    prompt = _fill(_ASSESS_TEMPLATE, ctx)
    try:
        raw = _call_prayer_generate(generate_fn, prompt, temperature=temperature)
    except Exception as exc:
        return PrayerAssessmentResult(
            overall_assessment="A Gemini-hívás sikertelen volt.",
            warnings=[f"Generálási hiba: {exc}"],
            ok=False,
            error_message=str(exc)[:280],
        )
    result = parse_prayer_assessment_response(raw)
    if result.ok and _is_present(passage_text):
        result.warnings = [
            w for w in result.warnings if "passage_text" not in w.casefold()
        ]
    return result


def _gen_factory(payload: str) -> GenerateFn:
    def _fn(*_a: Any, **_k: Any) -> str:
        return payload

    return _fn


def _self_check() -> list[str]:
    errors: list[str] = []

    before_json = """\
{
  "purpose": "Megnyílás az Ige hallására.",
  "recommended_movements": [
    {"title": "Megszólítás", "function": "address", "content_direction": "Istenhez fordulás"},
    {"title": "Csend", "function": "silence", "content_direction": "Elcsendesedés"},
    {"title": "Lélek", "function": "illumination", "content_direction": "Szentlélek segítsége"},
    {"title": "Átadás", "function": "preacher", "content_direction": "Igehirdető átadása"}
  ],
  "opening_options": ["Uram, most hozzád fordulunk.", "Szólj, Uram, hallunk."],
  "suggested_lines": [
    "Nyisd meg a szívünket a te Igéd előtt.",
    "Ne a saját bölcsességünket keressük.",
    "Adj őszinte figyelmet.",
    "Áldd meg az igehirdetőt a szolgálatában."
  ],
  "closing_direction": "Befogadó figyelem.",
  "integrated_user_thoughts": [],
  "language_notes": [],
  "cliche_risks": [],
  "warnings": [],
  "missing_information": []
}
"""
    # A: before does not include resolution language in purpose/lines heavily
    ra = suggest_prayer_before(
        generate_fn=_gen_factory(before_json),
        passage="Fil 2,5–11",
        passage_text="Az az indulat legyen bennetek…",
        text_main_idea="Krisztus alázata.",
    )
    if not ra.ok or len(ra.recommended_movements) < 3:
        errors.append("A: before suggest failed")
    blob = " ".join(ra.suggested_lines + [ra.purpose]).casefold()
    if "ezért most már tudjuk hogy" in blob:
        errors.append("A: premature resolution")

    after_json = before_json.replace('"purpose": "Megnyílás az Ige hallására."', '"purpose": "Hála és ráhagyatkozás."')
    after_json = after_json.replace("address", "gratitude").replace("silence", "gospel_trust").replace("illumination", "request").replace("preacher", "hope")
    rb = suggest_prayer_after(
        generate_fn=_gen_factory(after_json),
        passage="Fil 2,5–11",
        passage_text="Az az indulat…",
        sermon_main_idea="A kegyelem alázatra hív.",
        sermon_main_idea_status="approved",
        christ_centered_arc={"divine_gracious_action": "Krisztus megalázta magát"},
        listener_tension={"promised_resolution": "Ő felemel"},
    )
    if not rb.ok:
        errors.append("B: after suggest failed")

    # C/D/E/F integrate modes
    integrate_json = """\
{
  "purpose": "Saját gondolat beépítve.",
  "recommended_movements": [
    {"title": "Őszinteség", "function": "confession", "content_direction": "Őszinteség kérése"},
    {"title": "Lélek", "function": "illumination", "content_direction": "Szentlélek"},
    {"title": "Figyelem", "function": "hearers", "content_direction": "Befogadás"}
  ],
  "opening_options": ["Uram, légy irgalmas."],
  "suggested_lines": [
    "Adj őszinteséget a szívünkben.",
    "Ne csak másokra gondoljunk az Ige hallgatása közben."
  ],
  "closing_direction": "",
  "integrated_user_thoughts": [
    {
      "original": "Ne csak másokra gondoljunk az Ige hallgatása közben.",
      "refined": "Ne csak másokra gondoljunk az Ige hallgatása közben.",
      "placement": "hearers"
    }
  ],
  "language_notes": ["light_polish: szókincs megőrizve"],
  "cliche_risks": [],
  "warnings": [],
  "missing_information": []
}
"""
    for mode in ("light_polish", "integrate_into_arc", "free_rephrase"):
        ri = integrate_prayer_thoughts(
            side="before",
            generate_fn=_gen_factory(integrate_json),
            passage="Fil 2,5–11",
            passage_text="szöveg",
            text_main_idea="x",
            rewrite_mode=mode,
            prayer_before={
                "own_thoughts": "Ne csak másokra gondoljunk az Ige hallgatása közben."
            },
        )
        if not ri.ok or not ri.integrated_user_thoughts:
            errors.append(f"{mode}: integrate failed")
        else:
            orig = ri.integrated_user_thoughts[0].original
            if "másokra" not in orig.casefold():
                errors.append(f"{mode}: original thought lost")

    # G/H/I/J/K assessment
    assess_json = """\
{
  "overall_assessment": "Vegyes: vannak erősségek, de sablonosság és kockázatok is.",
  "before_assessment": "Az előtti ima túl korán hozza az evangéliumi feloldást.",
  "after_assessment": "Az utáni ima kegyelem nélküli felszólítást tartalmaz, és mini-prédikációra emlékeztet.",
  "strengths": ["Van saját hang."],
  "improvements": ["Természetesebb nyelvet használj.", "Kevesebb kioktatás."],
  "cliche_findings": ["„ebben a rohanó világban” felcserélhető sablon."],
  "text_connection_assessment": "Részben kapcsolódik.",
  "voice_assessment": "A saját hang részben megmarad; a túl költői fordulatok idegenek.",
  "revised_before_movements": [],
  "revised_before_lines": ["Nyisd meg a szívünket a te Igéd előtt."],
  "revised_after_movements": [],
  "revised_after_lines": ["Köszönjük, hogy megtartasz minket."],
  "warnings": [
    "Rejtett prédikáció / kioktatás az imában.",
    "Túl korai evangéliumi feloldás az előtti imában.",
    "Kegyelem nélküli felszólítás az utáni imában.",
    "Túl költői megfogalmazás."
  ]
}
"""
    rc = assess_prayer_preparation(
        generate_fn=_gen_factory(assess_json),
        passage="Fil 2,5–11",
        passage_text="Az az indulat…",
        prayer_before={"purpose": "x", "movement_notes": "y"},
        prayer_after={"purpose": "z"},
    )
    if not rc.ok:
        errors.append("assess failed")
    warn_blob = " ".join(rc.warnings + [rc.before_assessment, rc.after_assessment]).casefold()
    if "felold" not in warn_blob:
        errors.append("J: early resolution warning")
    if "kegyelem" not in warn_blob and "felszólít" not in warn_blob:
        errors.append("K: grace-less warning")
    if "sablon" not in " ".join(rc.cliche_findings).casefold() and "rohanó" not in " ".join(rc.cliche_findings).casefold():
        errors.append("G: cliche finding")
    if "költői" not in warn_blob and "természetesebb" not in " ".join(rc.improvements).casefold():
        errors.append("H: poetic language")
    if "kioktat" not in warn_blob and "prédikáció" not in warn_blob:
        errors.append("I: hidden sermon")

    # L: no own thoughts — suggest still works
    rl = suggest_prayer_before(
        generate_fn=_gen_factory(before_json),
        passage="Fil 2,5–11",
        passage_text="szöveg",
        text_main_idea="gondolat",
        prayer_before={},
    )
    if not rl.ok:
        errors.append("L: without own thoughts")

    # M: only own thoughts — integrate works with little data
    rm = integrate_prayer_thoughts(
        side="before",
        generate_fn=_gen_factory(integrate_json),
        passage="Fil 2,5–11",
        rewrite_mode="light_polish",
        prayer_before={"own_thoughts": "Adj őszinteséget."},
    )
    if not rm.ok:
        errors.append("M: integrate with little data")

    # N: passage_text present — no false missing
    rn = suggest_prayer_before(
        generate_fn=_gen_factory(before_json),
        passage="Fil 2,5–11",
        passage_text="Teljes szöveg itt van.",
        text_main_idea="x",
    )
    if any("passage_text" in w.casefold() for w in rn.warnings):
        errors.append("N: false passage_text warning")

    # insufficient before
    insuff = suggest_prayer_before(
        generate_fn=_gen_factory(before_json),
        passage="Fil 2,5–11",
        skip_api_if_insufficient=True,
    )
    if insuff.suggested_lines:
        errors.append("insufficient should not invent lines")

    # bad JSON
    bad = suggest_prayer_before(
        generate_fn=_gen_factory("not json"),
        passage="Fil 2,5–11",
        passage_text="x",
        text_main_idea="y",
    )
    if bad.ok:
        errors.append("bad json should fail")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon_workshop_m9_prayer_ai self-check OK")


__all__ = [
    "TAB_PRAYER",
    "PRAYER_TONE_PREFERENCES",
    "PRAYER_TONE_PREFERENCE_LABELS_HU",
    "PRAYER_REWRITE_MODES",
    "PRAYER_REWRITE_MODE_LABELS_HU",
    "PrayerMovement",
    "IntegratedThought",
    "PrayerArcSuggestionResult",
    "PrayerAssessmentResult",
    "prayer_tone_preference_label",
    "prayer_rewrite_mode_label",
    "normalize_prayer_tone_preference",
    "normalize_prayer_rewrite_mode",
    "has_sufficient_before_material",
    "has_sufficient_after_material",
    "suggest_prayer_before",
    "suggest_prayer_after",
    "integrate_prayer_thoughts",
    "assess_prayer_preparation",
    "parse_prayer_arc_response",
    "parse_prayer_assessment_response",
]
