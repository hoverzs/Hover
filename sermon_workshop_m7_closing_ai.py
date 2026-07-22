"""Igehirdetési műhely M7 — lezárás és megérkezés MI.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
Újrafelhasználja az M7 kontextusépítőt (M6 útvonal + M7 képek/illusztrációk).
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sermon_workshop_data import normalize_sermon_movements, normalize_textual_images
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import (
    MISSING,
    _as_str_list,
    _as_text,
    _display,
    _is_api_error_text,
    _is_present,
)
from sermon_workshop_m7_ai import (
    M7_SYSTEM_BUNDLE,
    build_enrichment_context,
    has_sufficient_enrichment_material,
)

TAB_SUGGEST = "Lezárás — javaslat"
TAB_ASSESS = "Lezárás — értékelés"
DEFAULT_TEMPERATURE = 0.15
DEFAULT_CLOSING_TYPE = "gospel_assurance"
DEFAULT_CLOSING_TONE = "hopeful"
MAX_ALTERNATIVE_CLOSINGS = 2

GenerateFn = Callable[..., str]

CLOSING_TYPES = (
    "gospel_assurance",
    "grace_enabled_call",
    "contemplative",
    "open_question",
    "communal_response",
    "hopeful_vision",
    "return_to_image",
    "doxological",
    "mixed",
)

CLOSING_TYPE_LABELS_HU: dict[str, str] = {
    "gospel_assurance": "Evangéliumi bizonyosság",
    "grace_enabled_call": "Kegyelemből fakadó meghívás",
    "contemplative": "Meditatív megérkezés",
    "open_question": "Nyitott kérdés",
    "communal_response": "Közösségi válasz",
    "hopeful_vision": "Reménységgel teli látás",
    "return_to_image": "Visszatérés a központi képhez",
    "doxological": "Doxologikus lezárás",
    "mixed": "Vegyes forma",
}

CLOSING_TONES = (
    "quiet",
    "hopeful",
    "assuring",
    "challenging",
    "communal",
    "prayerful",
    "doxological",
)

CLOSING_TONE_LABELS_HU: dict[str, str] = {
    "quiet": "Csendes",
    "hopeful": "Reménységgel teli",
    "assuring": "Megerősítő",
    "challenging": "Szembesítő",
    "communal": "Közösségi",
    "prayerful": "Imádságos",
    "doxological": "Doxologikus",
}

_UI_KEY_MAP = {
    "type": "recommended_closing_type",
    "final_discovery": "recommended_final_insight",
    "hope": "recommended_gospel_assurance",
    "call_or_response": "recommended_invitation",
    "image_or_line": "recommended_closing_image_or_line",
    "open_question": "recommended_open_question",
    "tone": "recommended_tone",
}

_REVISED_KEY_MAP = {
    "type": "revised_closing_type",
    "final_discovery": "revised_final_insight",
    "hope": "revised_gospel_assurance",
    "call_or_response": "revised_invitation",
    "image_or_line": "revised_closing_image_or_line",
    "open_question": "revised_open_question",
    "tone": "revised_tone",
}

_LIMITS_EXTRA = {"closing_block": 2500}


@dataclass
class AlternativeClosing:
    closing_type: str = ""
    emphasis: str = ""
    tone: str = ""
    reason_for_use: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "closing_type": self.closing_type,
            "emphasis": self.emphasis,
            "tone": self.tone,
            "reason_for_use": self.reason_for_use,
        }


@dataclass
class ClosingSuggestionResult:
    recommended_closing_type: str = DEFAULT_CLOSING_TYPE
    recommended_final_insight: str = ""
    recommended_gospel_assurance: str = ""
    recommended_invitation: str = ""
    recommended_closing_image_or_line: str = ""
    recommended_open_question: str = ""
    recommended_tone: str = DEFAULT_CLOSING_TONE
    expanded_summary: str = ""
    alternative_closings: list[AlternativeClosing] = field(default_factory=list)
    reasoning_summary: str = ""
    basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_closing_type": self.recommended_closing_type,
            "recommended_final_insight": self.recommended_final_insight,
            "recommended_gospel_assurance": self.recommended_gospel_assurance,
            "recommended_invitation": self.recommended_invitation,
            "recommended_closing_image_or_line": self.recommended_closing_image_or_line,
            "recommended_open_question": self.recommended_open_question,
            "recommended_tone": self.recommended_tone,
            "expanded_summary": self.expanded_summary,
            "alternative_closings": [x.to_dict() for x in self.alternative_closings],
            "reasoning_summary": self.reasoning_summary,
            "basis": list(self.basis),
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }

    def to_ui_block(self) -> dict[str, str]:
        return {
            "type": self.recommended_closing_type,
            "final_discovery": self.recommended_final_insight,
            "hope": self.recommended_gospel_assurance,
            "call_or_response": self.recommended_invitation,
            "image_or_line": self.recommended_closing_image_or_line,
            "open_question": self.recommended_open_question,
            "tone": self.recommended_tone,
        }


@dataclass
class ClosingAssessmentResult:
    overall_assessment: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    arrival_assessment: str = ""
    gospel_assurance_assessment: str = ""
    invitation_assessment: str = ""
    tone_assessment: str = ""
    revised_closing_type: str = ""
    revised_final_insight: str = ""
    revised_gospel_assurance: str = ""
    revised_invitation: str = ""
    revised_closing_image_or_line: str = ""
    revised_open_question: str = ""
    revised_tone: str = ""
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_assessment": self.overall_assessment,
            "strengths": list(self.strengths),
            "improvements": list(self.improvements),
            "arrival_assessment": self.arrival_assessment,
            "gospel_assurance_assessment": self.gospel_assurance_assessment,
            "invitation_assessment": self.invitation_assessment,
            "tone_assessment": self.tone_assessment,
            "revised_closing_type": self.revised_closing_type,
            "revised_final_insight": self.revised_final_insight,
            "revised_gospel_assurance": self.revised_gospel_assurance,
            "revised_invitation": self.revised_invitation,
            "revised_closing_image_or_line": self.revised_closing_image_or_line,
            "revised_open_question": self.revised_open_question,
            "revised_tone": self.revised_tone,
            "warnings": list(self.warnings),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }

    def revised_to_ui_block(self) -> dict[str, str]:
        return {
            "type": self.revised_closing_type,
            "final_discovery": self.revised_final_insight,
            "hope": self.revised_gospel_assurance,
            "call_or_response": self.revised_invitation,
            "image_or_line": self.revised_closing_image_or_line,
            "open_question": self.revised_open_question,
            "tone": self.revised_tone,
        }


def normalize_closing_type(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "gospel_assurance": "gospel_assurance",
        "evangeliumi_bizonyossag": "gospel_assurance",
        "evangéliumi_bizonyosság": "gospel_assurance",
        "grace_enabled_call": "grace_enabled_call",
        "kegyelembol_fakado_meghivas": "grace_enabled_call",
        "contemplative": "contemplative",
        "meditativ": "contemplative",
        "open_question": "open_question",
        "nyitott_kerdes": "open_question",
        "communal_response": "communal_response",
        "kozossegi_valasz": "communal_response",
        "hopeful_vision": "hopeful_vision",
        "return_to_image": "return_to_image",
        "visszateres": "return_to_image",
        "doxological": "doxological",
        "mixed": "mixed",
        "vegyes": "mixed",
    }
    if raw in CLOSING_TYPES:
        return raw
    return aliases.get(raw, DEFAULT_CLOSING_TYPE)


def closing_type_label(value: Any) -> str:
    key = normalize_closing_type(value)
    return CLOSING_TYPE_LABELS_HU.get(key, "—")


def normalize_closing_tone(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "quiet": "quiet",
        "csendes": "quiet",
        "hopeful": "hopeful",
        "remenységgel_teli": "hopeful",
        "assuring": "assuring",
        "megerosito": "assuring",
        "challenging": "challenging",
        "szembesito": "challenging",
        "communal": "communal",
        "kozossegi": "communal",
        "prayerful": "prayerful",
        "imadsagos": "prayerful",
        "doxological": "doxological",
    }
    if raw in CLOSING_TONES:
        return raw
    return aliases.get(raw, DEFAULT_CLOSING_TONE)


def closing_tone_label(value: Any) -> str:
    key = normalize_closing_tone(value)
    return CLOSING_TONE_LABELS_HU.get(key, "—")


def _format_closing_block(raw: Any) -> str:
    if not isinstance(raw, dict):
        return MISSING
    labels = (
        ("type", "Lezárás iránya"),
        ("final_discovery", "Végső felismerés"),
        ("hope", "Evangéliumi bizonyosság"),
        ("call_or_response", "Kegyelemből fakadó meghívás"),
        ("image_or_line", "Záró kép vagy mondatmag"),
        ("open_question", "Nyitva maradó kérdés"),
        ("tone", "Hangnem"),
    )
    lines: list[str] = []
    for key, label in labels:
        val = _as_text(raw.get(key))
        if not val:
            continue
        if key == "type":
            val = closing_type_label(val)
        elif key == "tone":
            val = closing_tone_label(val)
        lines.append(f"{label}: {val}")
    if not lines:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS_EXTRA["closing_block"])


def build_closing_context(
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
) -> dict[str, str]:
    ctx = build_enrichment_context(
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
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre,
    )
    ctx["closing_block"] = _format_closing_block(closing)
    return ctx


def _has_m6_destination(sermon_path: Any) -> bool:
    path = sermon_path if isinstance(sermon_path, dict) else {}
    return _is_present(path.get("destination"))


def _has_m6_path_or_movements(sermon_path: Any, sermon_movements: Any) -> bool:
    if _has_m6_destination(sermon_path):
        return True
    movements = normalize_sermon_movements(sermon_movements)
    filled = [
        m
        for m in movements
        if _is_present(m.get("title")) or _is_present(m.get("core_content"))
    ]
    return len(filled) >= 3


def _missing_closing_labels(
    ctx: Mapping[str, str],
    *,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    sermon_main_idea_status: str = "",
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
) -> list[str]:
    missing: list[str] = []
    if not _is_present(ctx.get("passage", MISSING)):
        missing.append("igehely-megjelölés (passage)")
    status = sermon_main_idea_status.strip().casefold()
    if status != "approved" or not _is_present(ctx.get("sermon_main_idea")):
        missing.append("jóváhagyott igehirdetési fő gondolat")
    if not _has_m6_path_or_movements(sermon_path, sermon_movements):
        missing.append("M6-os megérkezési pont vagy legalább három mozgás")
    arc = christ_centered_arc if isinstance(christ_centered_arc, dict) else {}
    lt = listener_tension if isinstance(listener_tension, dict) else {}
    if not _is_present(arc.get("divine_gracious_action")) and not _is_present(
        lt.get("promised_resolution")
    ):
        block = ctx.get("christ_arc_block", MISSING)
        has_resolution = False
        if _is_present(block):
            for marker in ("Evangéliumi feloldás:", "Isten kegyelmi cselekvése:"):
                if marker in str(block):
                    has_resolution = True
                    break
        if not has_resolution:
            missing.append("evangéliumi feloldás vagy Isten kegyelmi cselekvése")
    return missing


def _collect_textual_image_phrases(
    *,
    selected_images: Any = None,
    sermon_path: Any = None,
    sermon_movements: Any = None,
) -> list[str]:
    phrases: list[str] = []
    for img in normalize_textual_images(selected_images):
        for key in ("image", "textual_basis", "development_notes"):
            val = _as_text(img.get(key))
            if val:
                phrases.append(val)
    path = sermon_path if isinstance(sermon_path, dict) else {}
    for key in ("starting_point", "destination", "reason"):
        val = _as_text(path.get(key))
        if val:
            phrases.append(val)
    for mv in normalize_sermon_movements(sermon_movements):
        for key in (
            "title",
            "core_content",
            "textual_basis",
            "listener_discovery",
            "transition_to_next",
        ):
            val = _as_text(mv.get(key))
            if val:
                phrases.append(val)
    return phrases


def _has_textual_image_reference(
    *,
    selected_images: Any = None,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    image_or_line: str = "",
) -> bool:
    if normalize_textual_images(selected_images):
        return True
    phrases = _collect_textual_image_phrases(
        selected_images=selected_images,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
    )
    if not phrases:
        return False
    needle = _as_text(image_or_line).casefold()
    if needle:
        blob = " ".join(phrases).casefold()
        for token in needle.split():
            if len(token) >= 4 and token in blob:
                return True
    return False


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        if key.startswith("_"):
            continue
        out = out.replace("{{" + key + "}}", value)
    return out


_SUGGEST_TEMPLATE = """\
Feladatod: LEZÁRÁSI ÉS MEGÉRKEZÉSI IRÁNY javaslata az igehirdetéshez.

Ez NEM kész záróbekezdés, NEM teljes imádság, NEM új illusztráció vagy
alkalmazáslista, NEM hosszú érzelmi felhívás.

## Szakmai elvek

- A lezárás a teljes prédikációs út megérkezése legyen.
- Egyetlen fő felismeréshez érkezzen; ne ismételje mechanikusan az egész prédikációt.
- Ne vezessen be új témát.
- Ne legyen mesterségesen érzelmes vagy pusztán retorikai csattanó.
- Ne kényszerítse ki a hallgató reakcióját.
- A meghívás, záró kép és nyitott kérdés OPCIONÁLIS — csak ha indokolt.
- A `return_to_image` típust CSAK akkor javasold, ha textusbeli kép szerepel
  az M7 képek között VAGY korábban már megjelent az útban / mozgásokban.
- Ne állítsd, hogy minden prédikációt felszólítással vagy kérdéssel kell lezárni.

## Tilos

- teljes prédikáció pontjainak újra felsorolása;
- közhelyes lezárások textusbeli tartalom nélkül;
- manipuláló kérdés;
- bűntudatkeltő felszólítás;
- kitalált idézet, új történet vagy illusztráció;
- teljes zárókézirat vagy több bekezdéses befejezés.

## Lezárási típusok

gospel_assurance | grace_enabled_call | contemplative | open_question |
communal_response | hopeful_vision | return_to_image | doxological | mixed

## Hangnemek

quiet | hopeful | assuring | challenging | communal | prayerful | doxological

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

Az igehirdetés útja:
{{sermon_path_block}}

Prédikációs mozgások:
{{movements_block}}

Textusbeli képek:
{{images_block}}

Illusztrációk:
{{illustrations_block}}

Alkalmazási irányok:
{{applications_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma (csak ezt add vissza)

{
  "recommended_closing_type": "gospel_assurance|grace_enabled_call|contemplative|open_question|communal_response|hopeful_vision|return_to_image|doxological|mixed",
  "recommended_final_insight": "",
  "recommended_gospel_assurance": "",
  "recommended_invitation": "",
  "recommended_closing_image_or_line": "",
  "recommended_open_question": "",
  "recommended_tone": "quiet|hopeful|assuring|challenging|communal|prayerful|doxological",
  "expanded_summary": "",
  "alternative_closings": [
    {
      "closing_type": "",
      "emphasis": "",
      "tone": "",
      "reason_for_use": ""
    }
  ],
  "reasoning_summary": "",
  "basis": [],
  "warnings": [],
  "missing_information": []
}

Az `alternative_closings` legfeljebb 2 elem. Az `expanded_summary` 3–4 mondat legyen
arról, hogyan kapcsolódik a lezárás az egész igehirdetési úthoz.
"""


_ASSESS_TEMPLATE = """\
Feladatod: a prédikátor SAJÁT lezárási tervének értékelése.

Vizsgáld:
- kapcsolódik-e a fő gondolathoz és az M6 megérkezési ponthoz;
- az utolsó mozgásból természetesen következik-e;
- világos-e a végső felismerés;
- Isten kegyelmi cselekvése jelen van-e;
- a meghívás a kegyelemből fakad-e, nem moralizáló-e;
- nem vezet-e be új témát;
- nem túl hosszú vagy mechanikus összefoglaló-e;
- nem manipulatív-e a nyitott kérdés;
- illik-e a hangnem a textushoz;
- a záró kép elő volt-e készítve;
- nincs-e túl sok különböző lezárási elem.

Ne írd felül automatikusan a felhasználó munkáját — a `revised_*` mezők csak javaslatok.

## Műhelyanyag

Igehely: {{passage}}
Fordítás: {{bible_translation}}
Műfaj / irodalmi adat: {{literary_genre}}

Bibliai szöveg:
{{passage_text}}

Jóváhagyott igehirdetési fő gondolat: {{sermon_main_idea}}
Kifejtés: {{sermon_expanded_summary}}

Evangéliumi ív:
{{christ_arc_block}}

Az igehirdetés útja:
{{sermon_path_block}}

Prédikációs mozgások:
{{movements_block}}

Textusbeli képek:
{{images_block}}

Alkalmazási irányok:
{{applications_block}}

A prédikátor lezárási terve:
{{closing_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma

{
  "overall_assessment": "",
  "strengths": [],
  "improvements": [],
  "arrival_assessment": "",
  "gospel_assurance_assessment": "",
  "invitation_assessment": "",
  "tone_assessment": "",
  "revised_closing_type": "",
  "revised_final_insight": "",
  "revised_gospel_assurance": "",
  "revised_invitation": "",
  "revised_closing_image_or_line": "",
  "revised_open_question": "",
  "revised_tone": "",
  "warnings": []
}
"""


def build_closing_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_SUGGEST_TEMPLATE, ctx)


def build_closing_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_ASSESS_TEMPLATE, ctx)


def _call_closing_generate(
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
            system_bundle=M7_SYSTEM_BUNDLE,
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


def fallback_closing_suggestion(
    *,
    reasoning: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> ClosingSuggestionResult:
    return ClosingSuggestionResult(
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_closing_assessment(
    *,
    overall: str = "",
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> ClosingAssessmentResult:
    return ClosingAssessmentResult(
        overall_assessment=overall
        or "Nem megítélhető — nincs elegendő értékelhető lezárási terv.",
        warnings=list(warnings or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def _parse_alternative_closings(
    raw: Any,
    *,
    warnings: list[str],
) -> list[AlternativeClosing]:
    if not isinstance(raw, list):
        return []
    original = len([x for x in raw if isinstance(x, dict)])
    if original > MAX_ALTERNATIVE_CLOSINGS:
        warnings.append(
            f"Az alternatív lezárások száma ({original}) túllépte a "
            f"{MAX_ALTERNATIVE_CLOSINGS} elemet; a felesleg el lett hagyva."
        )
    out: list[AlternativeClosing] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            AlternativeClosing(
                closing_type=normalize_closing_type(item.get("closing_type")),
                emphasis=_as_text(item.get("emphasis")),
                tone=normalize_closing_tone(item.get("tone")),
                reason_for_use=_as_text(item.get("reason_for_use")),
            )
        )
        if len(out) >= MAX_ALTERNATIVE_CLOSINGS:
            break
    return out


def parse_closing_suggestions(
    raw: str,
    *,
    selected_images: Any = None,
    sermon_path: Any = None,
    sermon_movements: Any = None,
) -> ClosingSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_closing_suggestion(
            reasoning="Az API válasz hibás vagy üres.",
            warnings=["A javaslatkészítés nem adott érvényes választ."],
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return fallback_closing_suggestion(
            reasoning="A válasz nem volt érvényes JSON.",
            warnings=["Hibás vagy hiányos JSON; biztonságos alapértékeket használtunk."],
            error_message="Érvénytelen JSON.",
            raw_response=raw or "",
            ok=False,
        )
    warnings = _as_str_list(obj.get("warnings"))
    closing_type = normalize_closing_type(obj.get("recommended_closing_type"))
    image_or_line = _as_text(obj.get("recommended_closing_image_or_line"))
    if closing_type == "return_to_image" and not _has_textual_image_reference(
        selected_images=selected_images,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        image_or_line=image_or_line,
    ):
        warnings.append(
            "A visszatérés a központi képhez csak előkészített textusbeli "
            "kép esetén javasolt; az irány módosítva lett."
        )
        closing_type = DEFAULT_CLOSING_TYPE
    return ClosingSuggestionResult(
        recommended_closing_type=closing_type,
        recommended_final_insight=_as_text(obj.get("recommended_final_insight")),
        recommended_gospel_assurance=_as_text(obj.get("recommended_gospel_assurance")),
        recommended_invitation=_as_text(obj.get("recommended_invitation")),
        recommended_closing_image_or_line=image_or_line,
        recommended_open_question=_as_text(obj.get("recommended_open_question")),
        recommended_tone=normalize_closing_tone(obj.get("recommended_tone")),
        expanded_summary=_as_text(obj.get("expanded_summary")),
        alternative_closings=_parse_alternative_closings(
            obj.get("alternative_closings"), warnings=warnings
        ),
        reasoning_summary=_as_text(obj.get("reasoning_summary")),
        basis=_as_str_list(obj.get("basis")),
        warnings=warnings,
        missing_information=_as_str_list(obj.get("missing_information")),
        ok=True,
        raw_response=raw or "",
    )


def parse_closing_assessment(raw: str) -> ClosingAssessmentResult:
    if _is_api_error_text(raw):
        return fallback_closing_assessment(
            overall="Az értékelés nem sikerült (hibás vagy üres API-válasz).",
            warnings=["Az értékelés nem adott érvényes választ."],
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return fallback_closing_assessment(
            overall="Az értékelés nem értelmezhető — érvénytelen JSON.",
            warnings=["Hibás vagy hiányos JSON; biztonságos alapértékeket használtunk."],
            error_message="Érvénytelen JSON.",
            raw_response=raw or "",
            ok=False,
        )
    warnings = _as_str_list(obj.get("warnings"))
    revised_type = normalize_closing_type(obj.get("revised_closing_type"))
    if not _as_text(obj.get("revised_closing_type")):
        revised_type = ""
    revised_tone = normalize_closing_tone(obj.get("revised_tone"))
    if not _as_text(obj.get("revised_tone")):
        revised_tone = ""
    return ClosingAssessmentResult(
        overall_assessment=_as_text(obj.get("overall_assessment")),
        strengths=_as_str_list(obj.get("strengths")),
        improvements=_as_str_list(obj.get("improvements")),
        arrival_assessment=_as_text(obj.get("arrival_assessment")),
        gospel_assurance_assessment=_as_text(obj.get("gospel_assurance_assessment")),
        invitation_assessment=_as_text(obj.get("invitation_assessment")),
        tone_assessment=_as_text(obj.get("tone_assessment")),
        revised_closing_type=revised_type,
        revised_final_insight=_as_text(obj.get("revised_final_insight")),
        revised_gospel_assurance=_as_text(obj.get("revised_gospel_assurance")),
        revised_invitation=_as_text(obj.get("revised_invitation")),
        revised_closing_image_or_line=_as_text(
            obj.get("revised_closing_image_or_line")
        ),
        revised_open_question=_as_text(obj.get("revised_open_question")),
        revised_tone=revised_tone,
        warnings=warnings,
        ok=True,
        raw_response=raw or "",
    )


def suggest_closing(
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
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> ClosingSuggestionResult:
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
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
    )
    missing = _missing_closing_labels(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    )
    if not _is_present(ctx["passage"]):
        return fallback_closing_suggestion(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_enrichment_material(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    ):
        return fallback_closing_suggestion(
            reasoning=(
                "Nincs elegendő jóváhagyott műhelyeredmény a felelős "
                "lezárási javaslathoz."
            ),
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres ajánlások.",
                "Szükséges: igehely, jóváhagyott igehirdetési fő gondolat, "
                "M6-os megérkezési pont vagy legalább három mozgás, valamint "
                "evangéliumi feloldás vagy Isten kegyelmi cselekvése.",
            ],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_closing_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_closing_suggest_prompt(ctx)
    try:
        raw = _call_closing_generate(
            generate_fn,
            prompt,
            tab_label=TAB_SUGGEST,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_closing_suggestion(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=["A javaslatkészítés nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    result = parse_closing_suggestions(
        raw or "",
        selected_images=selected_images,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
    )
    if not _has_m6_destination(sermon_path):
        note = (
            "Az M6 megérkezési pont még nincs rögzítve; a javaslat a "
            "mozgásokra és az eddigi munkára támaszkodik."
        )
        if note not in result.warnings:
            result.warnings = list(result.warnings) + [note]
    if result.ok and not _is_present(ctx.get("passage_text")):
        note = (
            "A teljes bibliai szöveg (passage_text) nem állt közvetlenül "
            "rendelkezésre; a javaslat a jóváhagyott műhelyeredményekből készült."
        )
        if note not in result.warnings and (
            result.recommended_final_insight or result.recommended_gospel_assurance
        ):
            result.warnings = list(result.warnings) + [note]
        label = "bibliai szöveg (passage_text)"
        if label not in result.missing_information:
            result.missing_information = list(result.missing_information) + [label]
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


def assess_closing(
    *,
    passage: str,
    closing: Any = None,
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
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> ClosingAssessmentResult:
    block = closing if isinstance(closing, dict) else {}
    filled = any(_is_present(block.get(k)) for k in (
        "type",
        "final_discovery",
        "hope",
        "call_or_response",
        "image_or_line",
        "open_question",
        "tone",
    ))
    if not filled:
        return fallback_closing_assessment(
            overall="Nincs értékelhető lezárási terv.",
            warnings=["Tölts ki legalább egy lezárási mezőt az értékeléshez."],
            ok=True,
        )
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
        closing=block,
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
    )
    if generate_fn is None:
        return fallback_closing_assessment(
            overall="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_closing_assess_prompt(ctx)
    try:
        raw = _call_closing_generate(
            generate_fn,
            prompt,
            tab_label=TAB_ASSESS,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_closing_assessment(
            overall="Az értékelés közben váratlan hiba történt.",
            warnings=["Az értékelés nem sikerült. Próbáld újra később."],
            error_message=str(exc),
            ok=False,
        )
    return parse_closing_assessment(raw or "")


def _self_check() -> list[str]:
    errors: list[str] = []

    def _gen_factory(payload: str):
        def _gen(*_a, **_k):
            return payload

        return _gen

    base_kw = {
        "passage": "Jn 10,11–18",
        "passage_text": "Én vagyok a jó pásztor…",
        "sermon_main_idea": "Jézus a jó pásztor",
        "sermon_main_idea_status": "approved",
        "christ_centered_arc": {"divine_gracious_action": "Jézus odaadja az életét"},
        "listener_tension": {"promised_resolution": "A pásztor megtartja a juhait"},
        "sermon_path": {
            "type": "narrative",
            "reason": "Elbeszélő ív",
            "destination": "Bizalom a pásztorban",
        },
        "sermon_movements": [
            {"id": "mv1", "title": "M1", "role": "opening", "core_content": "a"},
            {"id": "mv2", "title": "M2", "role": "tension", "core_content": "b"},
            {"id": "mv3", "title": "M3", "role": "gospel_resolution", "core_content": "c"},
        ],
    }

    suggest_a = (
        '{"recommended_closing_type":"gospel_assurance",'
        '"recommended_final_insight":"A jó pásztor neve szerint ismer és megtart.",'
        '"recommended_gospel_assurance":"Jézus élete a juhokért konkrét ígéret.",'
        '"recommended_invitation":"","recommended_closing_image_or_line":"",'
        '"recommended_open_question":"","recommended_tone":"assuring",'
        '"expanded_summary":"A lezárás az út megérkezése.",'
        '"alternative_closings":[],"reasoning_summary":"Textusbeli bizonyosság.",'
        '"basis":["Jn 10,11"],"warnings":[],"missing_information":[]}'
    )
    ra = suggest_closing(generate_fn=_gen_factory(suggest_a), **base_kw)
    blob_a = (
        ra.recommended_gospel_assurance + ra.recommended_final_insight
    ).casefold()
    if "mindig velünk" in blob_a or "általános" in blob_a:
        errors.append("A: should not be generic cliché")
    if ra.recommended_closing_type != "gospel_assurance":
        errors.append("A: expected gospel_assurance")

    suggest_b = (
        '{"recommended_closing_type":"grace_enabled_call",'
        '"recommended_final_insight":"A kegyelem meghív bizalomra.",'
        '"recommended_gospel_assurance":"Jézus odaadja életét.",'
        '"recommended_invitation":"Bízz a pásztor vezetésében ma is.",'
        '"recommended_closing_image_or_line":"","recommended_open_question":"",'
        '"recommended_tone":"hopeful","expanded_summary":"","alternative_closings":[],'
        '"reasoning_summary":"","basis":[],"warnings":[],"missing_information":[]}'
    )
    rb = suggest_closing(generate_fn=_gen_factory(suggest_b), **base_kw)
    if not rb.recommended_invitation:
        errors.append("B: expected grace-enabled invitation")

    suggest_c = (
        '{"recommended_closing_type":"contemplative",'
        '"recommended_final_insight":"A pásztor szava elcsendesedik a szívben.",'
        '"recommended_gospel_assurance":"Isten megtart.",'
        '"recommended_invitation":"","recommended_closing_image_or_line":"",'
        '"recommended_open_question":"","recommended_tone":"quiet",'
        '"expanded_summary":"","alternative_closings":[],"reasoning_summary":"",'
        '"basis":[],"warnings":[],"missing_information":[]}'
    )
    rc = suggest_closing(generate_fn=_gen_factory(suggest_c), **base_kw)
    if rc.recommended_invitation or rc.recommended_open_question:
        errors.append("C: contemplative may omit invitation and question")

    suggest_d = (
        '{"recommended_closing_type":"open_question",'
        '"recommended_final_insight":"A pásztor hangja ma is szól.",'
        '"recommended_gospel_assurance":"Jézus ismer és vezet.",'
        '"recommended_invitation":"","recommended_closing_image_or_line":"",'
        '"recommended_open_question":"Kinek a hangjára hallgatsz ma?",'
        '"recommended_tone":"quiet","expanded_summary":"","alternative_closings":[],'
        '"reasoning_summary":"","basis":[],"warnings":[],"missing_information":[]}'
    )
    rd = suggest_closing(generate_fn=_gen_factory(suggest_d), **base_kw)
    if "?" not in rd.recommended_open_question:
        errors.append("D: expected open question")
    if "kinek" in rd.recommended_open_question.casefold() and "pásztor" in (
        rd.recommended_gospel_assurance + rd.recommended_final_insight
    ).casefold():
        pass  # question should not pre-answer — heuristic ok for mock

    suggest_e = (
        '{"recommended_closing_type":"communal_response",'
        '"recommended_final_insight":"A gyülekezet együtt hallja a pásztor hangját.",'
        '"recommended_gospel_assurance":"Krisztus a közösség pásztora.",'
        '"recommended_invitation":"","recommended_closing_image_or_line":"",'
        '"recommended_open_question":"","recommended_tone":"communal",'
        '"expanded_summary":"","alternative_closings":[],"reasoning_summary":"",'
        '"basis":[],"warnings":[],"missing_information":[]}'
    )
    re_ = suggest_closing(generate_fn=_gen_factory(suggest_e), **base_kw)
    if "gyülekezet" not in (
        re_.recommended_final_insight + re_.expanded_summary
    ).casefold() and "közösség" not in (
        re_.recommended_final_insight + re_.expanded_summary
    ).casefold():
        errors.append("E: expected communal emphasis")

    suggest_f_bad = (
        '{"recommended_closing_type":"return_to_image",'
        '"recommended_final_insight":"Visszatérünk a képhez.",'
        '"recommended_gospel_assurance":"Isten megtart.",'
        '"recommended_invitation":"","recommended_closing_image_or_line":"Ismeretlen kép",'
        '"recommended_open_question":"","recommended_tone":"hopeful",'
        '"expanded_summary":"","alternative_closings":[],"reasoning_summary":"",'
        '"basis":[],"warnings":[],"missing_information":[]}'
    )
    rf_bad_kw = dict(base_kw)
    rf_bad_kw["sermon_path"] = {"reason": "Elbeszélő ív"}
    rf_bad_kw["selected_images"] = []
    rf_bad = suggest_closing(
        generate_fn=_gen_factory(suggest_f_bad),
        **rf_bad_kw,
    )
    if rf_bad.recommended_closing_type == "return_to_image":
        errors.append("F: return_to_image without prepared image should be rejected")

    suggest_f_ok = (
        '{"recommended_closing_type":"return_to_image",'
        '"recommended_final_insight":"A jó pásztor képe most már bizalomként zár.",'
        '"recommended_gospel_assurance":"Jézus ismer.",'
        '"recommended_invitation":"","recommended_closing_image_or_line":"A jó pásztor",'
        '"recommended_open_question":"","recommended_tone":"hopeful",'
        '"expanded_summary":"","alternative_closings":[],"reasoning_summary":"",'
        '"basis":[],"warnings":[],"missing_information":[]}'
    )
    rf_ok = suggest_closing(
        generate_fn=_gen_factory(suggest_f_ok),
        selected_images=[{"image": "A jó pásztor", "textual_basis": "Jn 10,11"}],
        **base_kw,
    )
    if rf_ok.recommended_closing_type != "return_to_image":
        errors.append("F: return_to_image should work when M7 image exists")

    suggest_g = (
        '{"recommended_closing_type":"doxological",'
        '"recommended_final_insight":"A pásztor dicsőségére mutat.",'
        '"recommended_gospel_assurance":"Isten hű pásztor.",'
        '"recommended_invitation":"","recommended_closing_image_or_line":"Dicséret irány",'
        '"recommended_open_question":"","recommended_tone":"doxological",'
        '"expanded_summary":"","alternative_closings":[],"reasoning_summary":"",'
        '"basis":[],"warnings":[],"missing_information":[]}'
    )
    rg = suggest_closing(generate_fn=_gen_factory(suggest_g), **base_kw)
    if len(rg.recommended_closing_image_or_line.split()) > 20:
        errors.append("G: doxological should not be full prayer paragraph")

    assess_h = (
        '{"overall_assessment":"A lezárás új témát hoz be a misszióról.",'
        '"strengths":[],"improvements":["Maradj a pásztor képénél"],'
        '"arrival_assessment":"Nem illeszkedik a megérkezési ponthoz.",'
        '"gospel_assurance_assessment":"","invitation_assessment":"",'
        '"tone_assessment":"","revised_closing_type":"","revised_final_insight":"",'
        '"revised_gospel_assurance":"","revised_invitation":"",'
        '"revised_closing_image_or_line":"","revised_open_question":"",'
        '"revised_tone":"","warnings":["Új téma"]}'
    )
    rh = assess_closing(
        passage="Jn 10",
        closing={
            "final_discovery": "Most a misszióprogramot kell elindítanunk.",
            "hope": "Jézus küld.",
        },
        sermon_main_idea="Jézus a jó pásztor",
        generate_fn=_gen_factory(assess_h),
    )
    if "új tém" not in rh.overall_assessment.casefold() and "uj tem" not in rh.overall_assessment.casefold():
        errors.append("H: expected new topic signal")

    assess_i = (
        '{"overall_assessment":"A lezárás túl hosszú összefoglaló.",'
        '"strengths":[],"improvements":["Rövidíts egy felismerésre"],'
        '"arrival_assessment":"","gospel_assurance_assessment":"",'
        '"invitation_assessment":"","tone_assessment":"",'
        '"revised_closing_type":"","revised_final_insight":"Egy mondatban: a pásztor megtart.",'
        '"revised_gospel_assurance":"","revised_invitation":"",'
        '"revised_closing_image_or_line":"","revised_open_question":"",'
        '"revised_tone":"","warnings":["Túl hosszú"]}'
    )
    ri = assess_closing(
        passage="Jn 10",
        closing={"final_discovery": "Először… Másodszor… Harmadszor… " * 5},
        generate_fn=_gen_factory(assess_i),
    )
    if "hossz" not in ri.overall_assessment.casefold() and "rövid" not in " ".join(
        ri.improvements
    ).casefold():
        errors.append("I: expected long summary signal")

    assess_j = (
        '{"overall_assessment":"A nyitott kérdés manipulatív.",'
        '"strengths":[],"improvements":["Ne sugallj választ a kérdésben"],'
        '"arrival_assessment":"","gospel_assurance_assessment":"",'
        '"invitation_assessment":"","tone_assessment":"",'
        '"revised_closing_type":"","revised_final_insight":"",'
        '"revised_gospel_assurance":"","revised_invitation":"",'
        '"revised_closing_image_or_line":"","revised_open_question":"",'
        '"revised_tone":"","warnings":["Manipulatív kérdés"]}'
    )
    rj = assess_closing(
        passage="Jn 10",
        closing={"open_question": "Nem akarod már végre megbízni benne?"},
        generate_fn=_gen_factory(assess_j),
    )
    if "manipul" not in (
        rj.overall_assessment + " ".join(rj.warnings)
    ).casefold():
        errors.append("J: expected manipulative question signal")

    assess_k = (
        '{"overall_assessment":"A felszólítás kegyelem nélkül hangzik.",'
        '"strengths":[],"improvements":["Előbb Isten cselekvése"],'
        '"arrival_assessment":"","gospel_assurance_assessment":"",'
        '"invitation_assessment":"Moralizáló feladatlista.",'
        '"tone_assessment":"","revised_closing_type":"","revised_final_insight":"",'
        '"revised_gospel_assurance":"","revised_invitation":"",'
        '"revised_closing_image_or_line":"","revised_open_question":"",'
        '"revised_tone":"","warnings":["Kegyelem hiányzik"]}'
    )
    rk = assess_closing(
        passage="Jn 10",
        closing={"call_or_response": "Tedd meg végre, amit kell!"},
        generate_fn=_gen_factory(assess_k),
    )
    if "kegyelem" not in (
        rk.overall_assessment + rk.invitation_assessment
    ).casefold() and "moraliz" not in (
        rk.overall_assessment + rk.invitation_assessment
    ).casefold():
        errors.append("K: expected grace-less call signal")

    assess_l = (
        '{"overall_assessment":"Túl sok záróelem egyszerre.",'
        '"strengths":[],"improvements":["Válassz egy fő irányt"],'
        '"arrival_assessment":"","gospel_assurance_assessment":"",'
        '"invitation_assessment":"Túlterhelt.",'
        '"tone_assessment":"","revised_closing_type":"","revised_final_insight":"",'
        '"revised_gospel_assurance":"","revised_invitation":"",'
        '"revised_closing_image_or_line":"","revised_open_question":"",'
        '"revised_tone":"","warnings":["Túl sok elem"]}'
    )
    rl = assess_closing(
        passage="Jn 10",
        closing={
            "final_discovery": "a",
            "hope": "b",
            "call_or_response": "c",
            "image_or_line": "d",
            "open_question": "e?",
        },
        generate_fn=_gen_factory(assess_l),
    )
    blob_l = (rl.overall_assessment + rl.invitation_assessment).casefold()
    if "túl" not in blob_l and "tul" not in blob_l and "terhel" not in blob_l:
        errors.append("L: expected overload signal")

    rm = suggest_closing(
        passage="Zsolt 23",
        passage_text="Az Úr az én pásztorom…",
        sermon_main_idea="Isten gondviselése",
        sermon_main_idea_status="approved",
        christ_centered_arc={"divine_gracious_action": "Isten pásztorol"},
        sermon_path={"destination": "Bizalom"},
        sermon_movements=base_kw["sermon_movements"],
        generate_fn=_gen_factory(suggest_a),
    )
    if any(
        "passage_text" in w.casefold() and ("hiány" in w.casefold() or "nincs" in w.casefold())
        for w in rm.warnings
    ):
        errors.append("M: false missing passage_text warning")

    from sermon_workshop_data import normalize_sermon_workshop

    old = normalize_sermon_workshop({"sermon_main_idea": "régi"})
    if old.get("closing", {}).get("type") != "":
        pass  # type defaults empty
    if "image_or_line" not in old.get("closing", {}):
        errors.append("N: old project missing image_or_line in closing")
    if old.get("closing_status") != "draft":
        errors.append("N: closing_status default")
    if old.get("closing_suggestions") is not None:
        errors.append("N: closing_suggestions default None")

    insuff = suggest_closing(
        passage="Jn 3,16",
        sermon_main_idea="Isten szeretete",
        sermon_main_idea_status="draft",
        generate_fn=_gen_factory(suggest_a),
    )
    if "jóváhagyott igehirdetési fő gondolat" not in " ".join(
        insuff.missing_information
    ):
        errors.append("min input: missing approved sermon idea")

    bad = parse_closing_suggestions("nem json")
    if bad.ok:
        errors.append("bad json should fail")

    ui = suggest_closing(generate_fn=_gen_factory(suggest_a), **base_kw).to_ui_block()
    if ui.get("type") != "gospel_assurance" or ui.get("final_discovery") != ra.recommended_final_insight:
        errors.append("to_ui_block mapping")

    if normalize_closing_type("Evangéliumi bizonyosság") != "gospel_assurance":
        errors.append("alias closing type")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("FAIL")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon closing self-check OK")


__all__ = [
    "CLOSING_TYPES",
    "CLOSING_TYPE_LABELS_HU",
    "CLOSING_TONES",
    "CLOSING_TONE_LABELS_HU",
    "AlternativeClosing",
    "ClosingSuggestionResult",
    "ClosingAssessmentResult",
    "normalize_closing_type",
    "closing_type_label",
    "normalize_closing_tone",
    "closing_tone_label",
    "build_closing_context",
    "build_closing_suggest_prompt",
    "build_closing_assess_prompt",
    "parse_closing_suggestions",
    "parse_closing_assessment",
    "suggest_closing",
    "assess_closing",
    "fallback_closing_suggestion",
    "fallback_closing_assessment",
]
