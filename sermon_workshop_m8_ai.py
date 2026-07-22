"""Igehirdetési műhely M8 — homiletikai diagnosztika MI.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
Újrafelhasználja az M7 lezárási kontextusépítőt (M4–M7 aggregátum + lezárás).
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sermon_workshop_data import normalize_sermon_movements
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import (
    MISSING,
    _as_str_list,
    _as_text,
    _display,
    _is_api_error_text,
    _is_present,
)
from sermon_workshop_m7_ai import M7_SYSTEM_BUNDLE, has_sufficient_enrichment_material
from sermon_workshop_m7_closing_ai import build_closing_context

TAB_DIAG = "Homiletikai diagnosztika"
DEFAULT_TEMPERATURE = 0.15
MAX_REVISION_PRIORITIES = 3
MAX_MAJOR_STRENGTHS = 3

GenerateFn = Callable[..., str]

DIAGNOSTIC_AREA_KEYS = (
    "text_fidelity",
    "unity_and_focus",
    "listener_tension",
    "theological_accuracy",
    "christ_centeredness",
    "sermon_path",
    "hearability",
    "images_and_illustrations",
    "application",
    "closing",
    "pastoral_responsibility",
    "voice_and_originality",
)

DIAGNOSTIC_AREA_LABELS_HU: dict[str, str] = {
    "text_fidelity": "Textushűség",
    "unity_and_focus": "Egység és fókusz",
    "listener_tension": "Hallgatói feszültség",
    "theological_accuracy": "Teológiai pontosság",
    "christ_centeredness": "Krisztus-központúság",
    "sermon_path": "Prédikációs út",
    "hearability": "Hallhatóság",
    "images_and_illustrations": "Képek és illusztrációk",
    "application": "Alkalmazás",
    "closing": "Lezárás",
    "pastoral_responsibility": "Pásztori felelősség",
    "voice_and_originality": "Hang és eredetiség",
}

DIAGNOSTIC_STATUSES = (
    "strong",
    "stable",
    "needs_attention",
    "critical_gap",
    "not_enough_information",
)

DIAGNOSTIC_STATUS_LABELS_HU: dict[str, str] = {
    "strong": "Erős",
    "stable": "Stabil",
    "needs_attention": "Figyelmet igényel",
    "critical_gap": "Lényeges hiány",
    "not_enough_information": "Nincs elég adat",
}

_LIMITS_EXTRA = {"self_review_block": 2000}

_CLOSING_PLAN_KEYS = (
    "type",
    "final_discovery",
    "hope",
    "call_or_response",
    "image_or_line",
    "open_question",
    "tone",
)

_TENSION_KEYS = (
    "listener_question",
    "listener_resistance",
    "sermon_tension",
    "tension_source",
)


@dataclass
class DiagnosticAreaResult:
    key: str = ""
    label: str = ""
    status: str = "not_enough_information"
    summary: str = ""
    evidence: str = ""
    concerns: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "evidence": self.evidence,
            "concerns": self.concerns,
        }


@dataclass
class RevisionPriority:
    priority: int = 0
    title: str = ""
    problem: str = ""
    why_it_matters: str = ""
    recommended_action: str = ""
    affected_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority,
            "title": self.title,
            "problem": self.problem,
            "why_it_matters": self.why_it_matters,
            "recommended_action": self.recommended_action,
            "affected_sections": list(self.affected_sections),
        }


@dataclass
class HomileticalDiagnosticsResult:
    overall_summary: str = ""
    overall_coherence: str = ""
    diagnostic_areas: list[DiagnosticAreaResult] = field(default_factory=list)
    major_strengths: list[str] = field(default_factory=list)
    revision_priorities: list[RevisionPriority] = field(default_factory=list)
    consistency_warnings: list[str] = field(default_factory=list)
    pastoral_warnings: list[str] = field(default_factory=list)
    voice_and_originality_note: str = ""
    ready_for_next_stage: bool = False
    readiness_note: str = ""
    missing_information: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_summary": self.overall_summary,
            "overall_coherence": self.overall_coherence,
            "diagnostic_areas": [a.to_dict() for a in self.diagnostic_areas],
            "major_strengths": list(self.major_strengths),
            "revision_priorities": [p.to_dict() for p in self.revision_priorities],
            "consistency_warnings": list(self.consistency_warnings),
            "pastoral_warnings": list(self.pastoral_warnings),
            "voice_and_originality_note": self.voice_and_originality_note,
            "ready_for_next_stage": self.ready_for_next_stage,
            "readiness_note": self.readiness_note,
            "missing_information": list(self.missing_information),
            "warnings": list(self.warnings),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }


def normalize_diagnostic_status(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "eros": "strong",
        "erős": "strong",
        "stabil": "stable",
        "figyelmet_igenyel": "needs_attention",
        "figyelmet_igényel": "needs_attention",
        "lenyeges_hiany": "critical_gap",
        "lényeges_hiány": "critical_gap",
        "nincs_elég_adat": "not_enough_information",
        "nincs_eleg_adat": "not_enough_information",
    }
    if raw in DIAGNOSTIC_STATUSES:
        return raw
    return aliases.get(raw, "not_enough_information")


def diagnostic_status_label(value: Any) -> str:
    key = normalize_diagnostic_status(value)
    return DIAGNOSTIC_STATUS_LABELS_HU.get(key, "Nincs elég adat")


def diagnostic_area_label(key: str) -> str:
    return DIAGNOSTIC_AREA_LABELS_HU.get(key, key or "—")


def _format_self_review_block(
    *,
    self_review_strengths: str = "",
    self_review_uncertainties: str = "",
    self_review_priority: str = "",
    self_review_focus: str = "",
) -> str:
    labels = (
        ("self_review_strengths", "Erősségek (önellenőrzés)", self_review_strengths),
        ("self_review_uncertainties", "Bizonytalanságok", self_review_uncertainties),
        ("self_review_priority", "Elsődleges prioritás", self_review_priority),
        ("self_review_focus", "Fókuszpont", self_review_focus),
    )
    lines: list[str] = []
    for _key, label, val in labels:
        text = _as_text(val)
        if text:
            lines.append(f"{label}: {text}")
    if not lines:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS_EXTRA["self_review_block"])


def build_diagnostics_context(
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
    self_review_strengths: str = "",
    self_review_uncertainties: str = "",
    self_review_priority: str = "",
    self_review_focus: str = "",
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
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre,
    )
    ctx["self_review_block"] = _format_self_review_block(
        self_review_strengths=self_review_strengths,
        self_review_uncertainties=self_review_uncertainties,
        self_review_priority=self_review_priority,
        self_review_focus=self_review_focus,
    )
    return ctx


def _has_listener_tension(listener_tension: Any) -> bool:
    lt = listener_tension if isinstance(listener_tension, dict) else {}
    return any(_is_present(lt.get(k)) for k in _TENSION_KEYS)


def _has_closing_plan(closing: Any) -> bool:
    block = closing if isinstance(closing, dict) else {}
    return any(_is_present(block.get(k)) for k in _CLOSING_PLAN_KEYS)


def _has_m6_path_or_movements(sermon_path: Any, sermon_movements: Any) -> bool:
    path = sermon_path if isinstance(sermon_path, dict) else {}
    if any(
        _is_present(path.get(k))
        for k in ("type", "reason", "starting_point", "destination")
    ):
        return True
    movements = normalize_sermon_movements(sermon_movements)
    filled = [
        m
        for m in movements
        if _is_present(m.get("title")) or _is_present(m.get("core_content"))
    ]
    return len(filled) >= 3


def _missing_diagnostics_labels(
    ctx: Mapping[str, str],
    *,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    sermon_main_idea_status: str = "",
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
    closing: Any = None,
) -> list[str]:
    missing: list[str] = []
    if not _is_present(ctx.get("passage", MISSING)):
        missing.append("igehely-megjelölés (passage)")
    status = sermon_main_idea_status.strip().casefold()
    if status != "approved" or not _is_present(ctx.get("sermon_main_idea")):
        missing.append("jóváhagyott igehirdetési fő gondolat")
    if not _has_listener_tension(listener_tension):
        missing.append("hallgatói feszültség")
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
    if not _has_m6_path_or_movements(sermon_path, sermon_movements):
        missing.append("M6-os prédikációs út vagy legalább három mozgás")
    if not _has_closing_plan(closing):
        missing.append("lezárási terv")
    return missing


def has_sufficient_diagnostics_material(
    ctx: Mapping[str, str],
    *,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    sermon_main_idea_status: str = "",
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
    closing: Any = None,
) -> bool:
    return not _missing_diagnostics_labels(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
        closing=closing,
    )


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        if key.startswith("_"):
            continue
        out = out.replace("{{" + key + "}}", value)
    return out


_DIAGNOSTICS_TEMPLATE = """\
Feladatod: HOMILETIKAI DIAGNOSZTIKA — rövid, szöveges tükrözés az igehirdetési
műhely eddigi eredményéről.

Ez NEM kész prédikáció, NEM automatikus átírás, NEM pontozás vagy minősítő
rendszer. Ne adj százalékot, csillagot, osztályzatot vagy numerikus pontszámot.

## Szakmai elvek

- Csak a megadott műhelyanyagból dolgozz; ne találj ki tartalmat.
- Hiányzó adat esetén az adott szempont státusza legyen `not_enough_information`.
- A `revision_priorities` legfeljebb három elem — csak valódi, indokolt prioritás;
  ne találj ki hamis harmadik elemet, ha nincs rá alap.
- A prédikátor önellenőrző mezői (self_review_block) opcionális kontextus —
  ne írd felül őket, csak tükrözd, ha releváns.
- Figyelj a kereszt-konzisztenciára: fő gondolat ↔ feszültség ↔ evangélium ↔
  mozgások ↔ lezárás ↔ alkalmazás; jelezd az ellentmondásokat a
  `consistency_warnings` mezőben.
- A hang és eredetiség szempontjánál figyelj a steril, AI-szerű közhelyekre —
  de ne írj elő konkrét prédikátori stílust vagy személyiséget.
- Ne módosítsd javaslatként az M4–M7 jóváhagyott tartalmakat; csak értékelj.

## Diagnosztikai területek (pontos kulcsok)

text_fidelity | unity_and_focus | listener_tension | theological_accuracy |
christ_centeredness | sermon_path | hearability | images_and_illustrations |
application | closing | pastoral_responsibility | voice_and_originality

## Státuszok (pontos értékek)

strong | stable | needs_attention | critical_gap | not_enough_information

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

Lezárás és megérkezés:
{{closing_block}}

Prédikátor önellenőrzése (opcionális):
{{self_review_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma (csak ezt add vissza)

{
  "overall_summary": "",
  "overall_coherence": "",
  "diagnostic_areas": [
    {
      "key": "text_fidelity",
      "label": "Textushűség",
      "status": "stable",
      "summary": "",
      "evidence": "",
      "concerns": ""
    }
  ],
  "major_strengths": [],
  "revision_priorities": [
    {
      "priority": 1,
      "title": "",
      "problem": "",
      "why_it_matters": "",
      "recommended_action": "",
      "affected_sections": []
    }
  ],
  "consistency_warnings": [],
  "pastoral_warnings": [],
  "voice_and_originality_note": "",
  "ready_for_next_stage": false,
  "readiness_note": "",
  "missing_information": [],
  "warnings": []
}
"""


def build_diagnostics_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_DIAGNOSTICS_TEMPLATE, ctx)


def _call_diagnostics_generate(
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
            tab_label=TAB_DIAG,
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


def fallback_homiletical_diagnostics(
    *,
    overall_summary: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> HomileticalDiagnosticsResult:
    areas = [
        DiagnosticAreaResult(
            key=key,
            label=diagnostic_area_label(key),
            status="not_enough_information",
        )
        for key in DIAGNOSTIC_AREA_KEYS
    ]
    return HomileticalDiagnosticsResult(
        overall_summary=overall_summary
        or "Nem készült teljes diagnosztika — elégtelen adat vagy hiba.",
        diagnostic_areas=areas,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def _parse_revision_priorities(raw: Any, *, warnings: list[str]) -> list[RevisionPriority]:
    if not isinstance(raw, list):
        return []
    original = len([x for x in raw if isinstance(x, dict) or _as_text(x)])
    if original > MAX_REVISION_PRIORITIES:
        warnings.append(
            f"A javítási prioritások száma ({original}) túllépte a "
            f"{MAX_REVISION_PRIORITIES} elemet; a felesleg el lett hagyva."
        )
    out: list[RevisionPriority] = []
    for item in raw:
        if isinstance(item, dict):
            sections_raw = item.get("affected_sections")
            sections: list[str] = []
            if isinstance(sections_raw, list):
                sections = [_as_text(x) for x in sections_raw if _as_text(x)]
            out.append(
                RevisionPriority(
                    priority=int(item.get("priority") or len(out) + 1),
                    title=_as_text(item.get("title")),
                    problem=_as_text(item.get("problem")),
                    why_it_matters=_as_text(item.get("why_it_matters")),
                    recommended_action=_as_text(item.get("recommended_action")),
                    affected_sections=sections,
                )
            )
        elif _as_text(item):
            out.append(
                RevisionPriority(
                    priority=len(out) + 1,
                    title=_as_text(item),
                )
            )
        if len(out) >= MAX_REVISION_PRIORITIES:
            break
    return out


def _parse_diagnostic_areas(raw: Any, *, warnings: list[str]) -> list[DiagnosticAreaResult]:
    parsed: dict[str, DiagnosticAreaResult] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = _as_text(item.get("key"))
            if key not in DIAGNOSTIC_AREA_KEYS:
                continue
            parsed[key] = DiagnosticAreaResult(
                key=key,
                label=_as_text(item.get("label")) or diagnostic_area_label(key),
                status=normalize_diagnostic_status(item.get("status")),
                summary=_as_text(item.get("summary")),
                evidence=_as_text(item.get("evidence")),
                concerns=_as_text(item.get("concerns")),
            )
    missing_keys = [k for k in DIAGNOSTIC_AREA_KEYS if k not in parsed]
    if missing_keys:
        warnings.append(
            "Hiányzó diagnosztikai területek — alapértelmezett státusz: "
            "nincs elég adat."
        )
    out: list[DiagnosticAreaResult] = []
    for key in DIAGNOSTIC_AREA_KEYS:
        if key in parsed:
            out.append(parsed[key])
        else:
            out.append(
                DiagnosticAreaResult(
                    key=key,
                    label=diagnostic_area_label(key),
                    status="not_enough_information",
                )
            )
    return out


def _strip_false_passage_text_warnings(result: HomileticalDiagnosticsResult) -> None:
    result.warnings = [
        w
        for w in result.warnings
        if "passage_text" not in w.casefold()
        or ("hiány" not in w.casefold() and "nincs" not in w.casefold())
    ]
    result.missing_information = [
        m
        for m in result.missing_information
        if "passage_text" not in m.casefold()
    ]


def parse_homiletical_diagnostics(raw: str) -> HomileticalDiagnosticsResult:
    if _is_api_error_text(raw):
        return fallback_homiletical_diagnostics(
            overall_summary="Az API válasz hibás vagy üres.",
            warnings=["A diagnosztika nem adott érvényes választ."],
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return fallback_homiletical_diagnostics(
            overall_summary="A válasz nem volt érvényes JSON.",
            warnings=["Hibás vagy hiányos JSON; biztonságos alapértékeket használtunk."],
            error_message="Érvénytelen JSON.",
            raw_response=raw or "",
            ok=False,
        )
    warnings = _as_str_list(obj.get("warnings"))
    areas = _parse_diagnostic_areas(obj.get("diagnostic_areas"), warnings=warnings)
    priorities = _parse_revision_priorities(
        obj.get("revision_priorities"), warnings=warnings
    )
    ready_raw = obj.get("ready_for_next_stage")
    ready = bool(ready_raw) if isinstance(ready_raw, bool) else str(
        ready_raw
    ).strip().casefold() in ("true", "1", "igen", "yes")
    return HomileticalDiagnosticsResult(
        overall_summary=_as_text(obj.get("overall_summary")),
        overall_coherence=_as_text(obj.get("overall_coherence")),
        diagnostic_areas=areas,
        major_strengths=_as_str_list(obj.get("major_strengths"), max_items=MAX_MAJOR_STRENGTHS),
        revision_priorities=priorities,
        consistency_warnings=_as_str_list(obj.get("consistency_warnings")),
        pastoral_warnings=_as_str_list(obj.get("pastoral_warnings")),
        voice_and_originality_note=_as_text(obj.get("voice_and_originality_note")),
        ready_for_next_stage=ready,
        readiness_note=_as_text(obj.get("readiness_note")),
        missing_information=_as_str_list(obj.get("missing_information")),
        warnings=warnings,
        ok=True,
        raw_response=raw or "",
    )


def run_homiletical_diagnostics(
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
    self_review_strengths: str = "",
    self_review_uncertainties: str = "",
    self_review_priority: str = "",
    self_review_focus: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = False,
) -> HomileticalDiagnosticsResult:
    ctx = build_diagnostics_context(
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
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
        self_review_strengths=self_review_strengths,
        self_review_uncertainties=self_review_uncertainties,
        self_review_priority=self_review_priority,
        self_review_focus=self_review_focus,
    )
    missing = _missing_diagnostics_labels(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
        closing=closing,
    )
    if not _is_present(ctx["passage"]):
        return fallback_homiletical_diagnostics(
            overall_summary="Nincs megadva igehely-megjelölés; diagnosztika nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    has_full = has_sufficient_diagnostics_material(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
        closing=closing,
    )
    has_partial = has_sufficient_enrichment_material(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    ) or bool(_is_present(ctx.get("sermon_main_idea")))
    if skip_api_if_insufficient and not has_partial:
        return fallback_homiletical_diagnostics(
            overall_summary=(
                "Nincs elegendő műhelyanyag a felelős diagnosztikához."
            ),
            warnings=[
                "Elégtelen adat: csak hiányjelzés, nem teljes értékelés.",
                "Legalább igehely és némi műhelytartalom szükséges.",
            ],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_homiletical_diagnostics(
            overall_summary="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_diagnostics_prompt(ctx)
    try:
        raw = _call_diagnostics_generate(
            generate_fn,
            prompt,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_homiletical_diagnostics(
            overall_summary="A diagnosztika közben váratlan hiba történt.",
            warnings=["A diagnosztika nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    result = parse_homiletical_diagnostics(raw or "")
    if not has_full:
        note = (
            "A teljes diagnosztikához szükséges elemek egy része hiányzik; "
            "az értékelés csak a rendelkezésre álló területeken készült."
        )
        if note not in result.warnings:
            result.warnings = list(result.warnings) + [note]
        for item in missing:
            if item not in result.missing_information:
                result.missing_information = list(result.missing_information) + [item]
    if result.ok and _is_present(ctx.get("passage_text")):
        _strip_false_passage_text_warnings(result)
    elif result.ok and not _is_present(ctx.get("passage_text")):
        note = (
            "A teljes bibliai szöveg (passage_text) nem állt közvetlenül "
            "rendelkezésre; a diagnosztika a jóváhagyott műhelyeredményekből készült."
        )
        if note not in result.warnings and result.overall_summary:
            result.warnings = list(result.warnings) + [note]
        label = "bibliai szöveg (passage_text)"
        if label not in result.missing_information:
            result.missing_information = list(result.missing_information) + [label]
    return result


suggest_diagnostics = run_homiletical_diagnostics


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
        "listener_tension": {
            "sermon_tension": "Ki vezeti valójában az életemet?",
            "promised_resolution": "A jó pásztor megtartja juhait",
        },
        "christ_centered_arc": {"divine_gracious_action": "Jézus odaadja az életét"},
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
        "closing": {
            "final_discovery": "A pásztor neve szerint ismer.",
            "hope": "Jézus élete biztonság.",
        },
    }

    diag_a = (
        '{"overall_summary":"Egységes, textushű váz.",'
        '"overall_coherence":"A fő gondolat, feszültség és lezárás összhangban.",'
        '"diagnostic_areas":[{"key":"text_fidelity","label":"Textushűség",'
        '"status":"strong","summary":"A pásztor képe textusbeli.",'
        '"evidence":"Jn 10","concerns":""},'
        '{"key":"closing","label":"Lezárás","status":"stable","summary":"Megérkezik.",'
        '"evidence":"","concerns":""}],'
        '"major_strengths":["Erős textusbeli kép"],'
        '"revision_priorities":[{"priority":1,"title":"Mozgásátmenetek",'
        '"problem":"Gyenge átmenet","why_it_matters":"Hallhatóság",'
        '"recommended_action":"Erősítsd az átmenetet","affected_sections":["Mozgások"]}],'
        '"consistency_warnings":[],"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":true,"readiness_note":"Következő lépés lehetséges.",'
        '"missing_information":[],"warnings":[]}'
    )
    ra = run_homiletical_diagnostics(
        generate_fn=_gen_factory(diag_a), **base_kw
    )
    if not ra.overall_summary or ra.revision_priorities[0].title != "Mozgásátmenetek":
        errors.append("A: expected parsed summary and priority")
    if ra.diagnostic_areas[0].status != "strong":
        errors.append("A: expected strong text_fidelity")

    diag_b = (
        '{"overall_summary":"x","overall_coherence":"","diagnostic_areas":[],'
        '"major_strengths":[],"revision_priorities":['
        '{"priority":1,"title":"p1","problem":"","why_it_matters":"",'
        '"recommended_action":"","affected_sections":[]},'
        '{"priority":2,"title":"p2","problem":"","why_it_matters":"",'
        '"recommended_action":"","affected_sections":[]},'
        '{"priority":3,"title":"p3","problem":"","why_it_matters":"",'
        '"recommended_action":"","affected_sections":[]},'
        '{"priority":4,"title":"p4","problem":"","why_it_matters":"",'
        '"recommended_action":"","affected_sections":[]}],'
        '"consistency_warnings":[],"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],"warnings":[]}'
    )
    rb = parse_homiletical_diagnostics(diag_b)
    if len(rb.revision_priorities) != 3:
        errors.append("B: revision_priorities not capped at 3")

    diag_c = (
        '{"overall_summary":"Részleges.","overall_coherence":"","diagnostic_areas":['
        '{"key":"application","label":"Alkalmazás","status":"not_enough_information",'
        '"summary":"","evidence":"","concerns":""}],'
        '"major_strengths":[],"revision_priorities":[],"consistency_warnings":[],'
        '"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],'
        '"warnings":[]}'
    )
    rc = parse_homiletical_diagnostics(diag_c)
    app_area = next((a for a in rc.diagnostic_areas if a.key == "application"), None)
    if not app_area or app_area.status != "not_enough_information":
        errors.append("C: expected not_enough_information for application")
    if len(rc.diagnostic_areas) != len(DIAGNOSTIC_AREA_KEYS):
        errors.append("C: expected all diagnostic area keys filled")

    diag_d = (
        '{"overall_summary":"Ellentmondás.","overall_coherence":"Gyenge.",'
        '"diagnostic_areas":[],"major_strengths":[],"revision_priorities":[],'
        '"consistency_warnings":["A fő gondolat nem illeszkedik a lezáráshoz"],'
        '"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],"warnings":[]}'
    )
    rd = parse_homiletical_diagnostics(diag_d)
    if not rd.consistency_warnings:
        errors.append("D: expected consistency_warnings")

    diag_e = (
        '{"overall_summary":"","overall_coherence":"","diagnostic_areas":[],'
        '"major_strengths":[],"revision_priorities":[],"consistency_warnings":[],'
        '"pastoral_warnings":[],"voice_and_originality_note":'
        '"A szöveg túl sablonos, AI-szerű közhelyeket használ.",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],"warnings":[]}'
    )
    re_ = parse_homiletical_diagnostics(diag_e)
    if "sablon" not in re_.voice_and_originality_note.casefold():
        errors.append("E: expected voice/originality note")

    diag_f = (
        '{"overall_summary":"Pontszám: 87%","overall_coherence":"","diagnostic_areas":[],'
        '"major_strengths":[],"revision_priorities":[],"consistency_warnings":[],'
        '"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],"warnings":[]}'
    )
    rf = parse_homiletical_diagnostics(diag_f)
    if rf.overall_summary != "Pontszám: 87%":
        errors.append("F: parser should preserve text (prompt forbids scores)")
    if "%" in rf.overall_summary and "87" in rf.overall_summary:
        pass  # stored as-is from mock; prompt responsibility

    diag_g = (
        '{"overall_summary":"","overall_coherence":"","diagnostic_areas":[],'
        '"major_strengths":[],"revision_priorities":[],"consistency_warnings":[],'
        '"pastoral_warnings":["Ne manipuláld a bűntudatot a lezárásban"],'
        '"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],"warnings":[]}'
    )
    rg = parse_homiletical_diagnostics(diag_g)
    if not rg.pastoral_warnings:
        errors.append("G: expected pastoral_warnings")

    diag_h = (
        '{"overall_summary":"","overall_coherence":"","diagnostic_areas":[],'
        '"major_strengths":["Erős textusbeli kép","Egységes fő gondolat"],'
        '"revision_priorities":[],"consistency_warnings":[],"pastoral_warnings":[],'
        '"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],"warnings":[]}'
    )
    rh = parse_homiletical_diagnostics(diag_h)
    if len(rh.major_strengths) != 2:
        errors.append("H: expected major_strengths")

    diag_i = (
        '{"overall_summary":"","overall_coherence":"A mozgások logikus ívet követnek.",'
        '"diagnostic_areas":[],"major_strengths":[],"revision_priorities":[],'
        '"consistency_warnings":[],"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"","missing_information":[],"warnings":[]}'
    )
    ri = parse_homiletical_diagnostics(diag_i)
    if "mozgás" not in ri.overall_coherence.casefold():
        errors.append("I: expected overall_coherence")

    diag_j = (
        '{"overall_summary":"","overall_coherence":"","diagnostic_areas":[],'
        '"major_strengths":[],"revision_priorities":[],"consistency_warnings":[],'
        '"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":true,"readiness_note":"Készen áll a következő lépésre.",'
        '"missing_information":[],"warnings":[]}'
    )
    rj = parse_homiletical_diagnostics(diag_j)
    if not rj.ready_for_next_stage or not rj.readiness_note:
        errors.append("J: expected readiness fields")

    insuff = run_homiletical_diagnostics(
        passage="Jn 3,16",
        generate_fn=_gen_factory(diag_a),
        skip_api_if_insufficient=True,
    )
    if "elegendő" not in insuff.overall_summary.casefold() and "elégtelen" not in insuff.overall_summary.casefold():
        errors.append("K: expected insufficient material message")
    partial = run_homiletical_diagnostics(
        passage="Jn 3,16",
        sermon_main_idea="Isten szeretete",
        sermon_main_idea_status="draft",
        generate_fn=_gen_factory(diag_a),
    )
    if not partial.ok or not partial.overall_summary.startswith("Egységes"):
        errors.append("K: partial material may still run diagnostics")

    bad = parse_homiletical_diagnostics("nem json")
    if bad.ok:
        errors.append("L: bad json should fail")

    diag_m = (
        '{"overall_summary":"Ok.","overall_coherence":"","diagnostic_areas":[],'
        '"major_strengths":[],"revision_priorities":[],"consistency_warnings":[],'
        '"pastoral_warnings":[],"voice_and_originality_note":"",'
        '"ready_for_next_stage":false,"readiness_note":"",'
        '"missing_information":["bibliai szöveg (passage_text)"],'
        '"warnings":["A passage_text hiányzik"]}'
    )
    rm = run_homiletical_diagnostics(
        generate_fn=_gen_factory(diag_m), **base_kw
    )
    if any(
        "passage_text" in w.casefold() and ("hiány" in w.casefold() or "nincs" in w.casefold())
        for w in rm.warnings
    ):
        errors.append("M: false missing passage_text warning")
    if any("passage_text" in m.casefold() for m in rm.missing_information):
        errors.append("M: false missing passage_text in missing_information")

    from sermon_workshop_data import normalize_sermon_workshop

    old = normalize_sermon_workshop({"sermon_main_idea": "régi"})
    if "self_review_strengths" not in old:
        errors.append("N: old project missing self_review_strengths")
    if old.get("diagnostics", {}).get("result") != {}:
        errors.append("N: diagnostics.result default")
    if old.get("diagnostics", {}).get("priorities") != []:
        errors.append("N: diagnostics.priorities default")

    ctx = build_diagnostics_context(
        passage="Jn 10",
        passage_text="Szöveg",
        sermon_main_idea="Teszt",
        self_review_strengths="Erős kép",
    )
    if "Erős kép" not in ctx.get("self_review_block", ""):
        errors.append("self_review in context")

    if normalize_diagnostic_status("Erős") != "strong":
        errors.append("status alias Erős")
    if diagnostic_status_label("needs_attention") != "Figyelmet igényel":
        errors.append("status label HU")

    if suggest_diagnostics is not run_homiletical_diagnostics:
        errors.append("suggest_diagnostics alias")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("FAIL")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("homiletical diagnostics self-check OK")


__all__ = [
    "DIAGNOSTIC_AREA_KEYS",
    "DIAGNOSTIC_AREA_LABELS_HU",
    "DIAGNOSTIC_STATUSES",
    "DIAGNOSTIC_STATUS_LABELS_HU",
    "DiagnosticAreaResult",
    "RevisionPriority",
    "HomileticalDiagnosticsResult",
    "normalize_diagnostic_status",
    "diagnostic_status_label",
    "diagnostic_area_label",
    "build_diagnostics_context",
    "build_diagnostics_prompt",
    "has_sufficient_diagnostics_material",
    "parse_homiletical_diagnostics",
    "run_homiletical_diagnostics",
    "suggest_diagnostics",
]
