"""Igehirdetési vázlat homiletikai diagnosztika — egyszerűsített kimenet.

A meglévő M8 mintákat újrafelhasználja, de a fő vizsgálati tárgy a
összeállított `sermon_outline`. Nem módosítja a vázlatot és a műhelymezőket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sermon_workshop_data import normalize_sermon_outline
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _as_str_list, _as_text, _is_api_error_text
from sermon_workshop_m8_ai import (
    MAX_MAJOR_STRENGTHS,
    MAX_REVISION_PRIORITIES,
    HomileticalDiagnosticsResult,
    build_diagnostics_context,
    parse_homiletical_diagnostics,
)
from sermon_workshop_outline_ai import MISSING_PART, outline_has_content

TAB_OUTLINE_DIAG = "Homiletikai diagnosztika"
DEFAULT_TEMPERATURE = 0.15
MAX_STRENGTHS = MAX_MAJOR_STRENGTHS  # 3
MAX_REFINEMENTS = MAX_REVISION_PRIORITIES  # 3

GenerateFn = Callable[..., str]


def _s(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class OutlineRefinement:
    title: str = ""
    explanation: str = ""
    suggested_action: str = ""
    affected_outline_parts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "explanation": self.explanation,
            "suggested_action": self.suggested_action,
            "affected_outline_parts": list(self.affected_outline_parts),
        }


@dataclass
class OutlineDiagnosticsResult:
    overview: str = ""
    strengths: list[str] = field(default_factory=list)
    refinements: list[OutlineRefinement] = field(default_factory=list)
    ready_to_use: bool = False
    next_step: str = ""
    detailed_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostic_areas: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "ai"  # ai | local_heuristic | api_error | parse_error
    ok: bool = True
    error_message: str = ""
    missing_outline: bool = False
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overview": self.overview,
            "strengths": list(self.strengths)[:MAX_STRENGTHS],
            "refinements": [r.to_dict() for r in self.refinements[:MAX_REFINEMENTS]],
            "ready_to_use": bool(self.ready_to_use),
            "next_step": self.next_step,
            "detailed_notes": list(self.detailed_notes),
            "warnings": list(self.warnings),
            "diagnostic_areas": list(self.diagnostic_areas),
            "mode": self.mode or "ai",
            "ok": self.ok,
            "error_message": self.error_message,
            "missing_outline": self.missing_outline,
        }


def empty_outline_diagnostics() -> dict[str, Any]:
    return OutlineDiagnosticsResult().to_dict()


def normalize_outline_diagnostics(raw: Any) -> dict[str, Any]:
    base = empty_outline_diagnostics()
    if not isinstance(raw, dict):
        return base
    strengths = [
        _s(x) for x in (raw.get("strengths") or []) if _s(x)
    ][:MAX_STRENGTHS]
    refinements: list[dict[str, Any]] = []
    for item in raw.get("refinements") or []:
        if not isinstance(item, dict):
            continue
        title = _s(item.get("title"))
        if not title:
            continue
        refinements.append(
            {
                "title": title,
                "explanation": _s(
                    item.get("explanation") or item.get("why_it_matters") or item.get("problem")
                ),
                "suggested_action": _s(
                    item.get("suggested_action") or item.get("recommended_action")
                ),
                "affected_outline_parts": [
                    _s(x)
                    for x in (
                        item.get("affected_outline_parts")
                        or item.get("affected_sections")
                        or []
                    )
                    if _s(x)
                ],
            }
        )
        if len(refinements) >= MAX_REFINEMENTS:
            break
    return {
        "overview": _s(raw.get("overview") or raw.get("overall_summary")),
        "strengths": strengths,
        "refinements": refinements,
        "ready_to_use": bool(
            raw.get("ready_to_use")
            if "ready_to_use" in raw
            else raw.get("ready_for_next_stage")
        ),
        "next_step": _s(raw.get("next_step") or raw.get("readiness_note")),
        "detailed_notes": [
            _s(x) for x in (raw.get("detailed_notes") or []) if _s(x)
        ],
        "warnings": [_s(x) for x in (raw.get("warnings") or []) if _s(x)],
        "diagnostic_areas": [
            dict(a) for a in (raw.get("diagnostic_areas") or []) if isinstance(a, dict)
        ],
        "mode": _s(raw.get("mode")) or "ai",
        "ok": bool(raw.get("ok", True)),
        "error_message": _s(raw.get("error_message")),
        "missing_outline": bool(raw.get("missing_outline")),
    }


def adapt_m8_to_outline_diagnostics(
    result: HomileticalDiagnosticsResult | Mapping[str, Any],
) -> OutlineDiagnosticsResult:
    """Régi M8 séma → egyszerűsített UI-kimenet."""
    if isinstance(result, HomileticalDiagnosticsResult):
        data = result.to_dict()
        ok = result.ok
        err = result.error_message
    else:
        data = dict(result) if isinstance(result, Mapping) else {}
        ok = bool(data.get("ok", True))
        err = _s(data.get("error_message"))

    strengths = [
        _s(x) for x in (data.get("major_strengths") or []) if _s(x)
    ][:MAX_STRENGTHS]

    refinements: list[OutlineRefinement] = []
    for item in data.get("revision_priorities") or []:
        if not isinstance(item, dict):
            continue
        title = _s(item.get("title"))
        if not title:
            continue
        refinements.append(
            OutlineRefinement(
                title=title,
                explanation=_s(
                    item.get("why_it_matters") or item.get("problem")
                ),
                suggested_action=_s(item.get("recommended_action")),
                affected_outline_parts=[
                    _s(x) for x in (item.get("affected_sections") or []) if _s(x)
                ],
            )
        )
        if len(refinements) >= MAX_REFINEMENTS:
            break

    notes: list[str] = []
    for key in ("overall_coherence", "voice_and_originality_note"):
        text = _s(data.get(key))
        if text:
            notes.append(text)
    for warn_key in ("consistency_warnings", "pastoral_warnings"):
        for item in data.get(warn_key) or []:
            line = _s(item)
            if line:
                notes.append(line)
    for area in data.get("diagnostic_areas") or []:
        if not isinstance(area, dict):
            continue
        summary = _s(area.get("summary"))
        label = _s(area.get("label") or area.get("key"))
        if summary:
            notes.append(f"{label}: {summary}" if label else summary)

    ready = bool(data.get("ready_for_next_stage"))
    next_step = _s(data.get("readiness_note"))
    if not next_step:
        next_step = (
            "A vázlat alapján tovább lehet lépni a kézi kidolgozásra."
            if ready
            else "Érdemes a fenti finomítások közül az elsőt elvégezni."
        )

    warnings = [_s(x) for x in (data.get("warnings") or []) if _s(x)]
    return OutlineDiagnosticsResult(
        overview=_s(data.get("overall_summary")),
        strengths=strengths,
        refinements=refinements,
        ready_to_use=ready,
        next_step=next_step,
        detailed_notes=notes,
        warnings=warnings,
        ok=ok,
        error_message=err,
    )


def _outline_context_block(outline: Mapping[str, Any]) -> str:
    import json

    # Ne küldjük a teljes bibliai szöveget — a vázlatban amúgy sincs.
    safe = normalize_sermon_outline(outline)
    return json.dumps(safe, ensure_ascii=False, indent=2)


_OUTLINE_DIAG_TEMPLATE = """\
Feladatod: a végső IGEHIRDETÉSI VÁZLAT homiletikai ellenőrzése.

Ez NEM pontozás, NEM átírás, NEM teljes kézirat. Ne találj ki új teológiát.

## Fontos elv
A műhelymodulok (M4–M9) kihagyása önmagában NEM hiba.
Ne minősítsd `critical_gap`-nek és ne sorold fel hiányzó modulként, ha:
- nincs külön hallgatói kérdés modul, de a vázlat megszólítja a hallgatót;
- nincs M6 modul, de a vázlat mozgásai világosak;
- nincs M7 / illusztráció, de van alkalmazási irány vagy a vázlat enélkül is működik
  (külső illusztráció hiánya SOHA ne legyen hiba);
- nincs külön lezárási modul, de a vázlat jól megérkezik;
- nincs lekció vagy imádság — ezek opcionálisak.

Csak a vázlatban ténylegesen érzékelhető homiletikai problémákat jelezd.
Ha valami nem ítélhető meg a rövidség miatt, írd egyszerűen:
„Az alkalmazás részletezettsége még nem ítélhető meg teljesen, mert a
vázlat ezen a ponton rövid.” — de a teljes diagnosztikát ne tedd használhatatlanná.

## Vizsgáld elsősorban
- egyetlen fő gondolat körül épül-e;
- a bevezetés megnyitja-e a központi kérdést;
- a mozgások különböző funkciót töltenek-e be / ismétlés nélkül;
- világos-e az evangéliumi fordulat (ha a vázlatban van ilyen tartalom);
- az alkalmazások kegyelemből fakadnak-e (ha vannak);
- a lezárás oda érkezik-e, ahová az út vezetett (ha van);
- hallás útján követhető-e;
- maradt-e hely a prédikátor saját hangjának.

## Korlátok
- strengths: legfeljebb 3, csak valódi erősség;
- refinements: legfeljebb 3; ne gyárts mesterséges problémát modulhiányból;
- detailed_notes: opcionális;
- ne listázd az összes ki nem töltött műhelymodult;
- diagnostic_areas: pontosan a lenti 8 kulcs; ha nincs elég vázlattartalom
  egy tengelyhez, status legyen "not_enough_information", score pedig null
  (SOHA ne írj 0 pontot hiányzó adat helyett).

## Vázlat JSON
{{outline_json}}

## Összevetés (rövid, csak ha van)
Fő gondolat: {{sermon_main_idea}}
Igehely: {{passage}}

## Kimenet — KIZÁRÓLAG érvényes JSON
{
  "overview": "2-4 mondat",
  "strengths": ["max 3"],
  "refinements": [
    {
      "title": "rövid cím",
      "explanation": "1-2 mondat",
      "suggested_action": "konkrét javaslat",
      "affected_outline_parts": ["opcionális"]
    }
  ],
  "diagnostic_areas": [
    {
      "key": "text_fidelity",
      "label": "Textushűség",
      "status": "strong|stable|needs_attention|critical_gap|not_enough_information",
      "score": 1,
      "summary": "rövid indoklás a vázlatból",
      "suggested_action": "konkrét javaslat vagy üres"
    },
    {"key": "unity_and_focus", "label": "Fő gondolat és fókusz", "status": "…", "score": null, "summary": "", "suggested_action": ""},
    {"key": "listener_tension", "label": "Hallgatói megszólítás", "status": "…", "score": null, "summary": "", "suggested_action": ""},
    {"key": "christ_centeredness", "label": "Krisztus-központúság", "status": "…", "score": null, "summary": "", "suggested_action": ""},
    {"key": "sermon_path", "label": "Szerkezet és mozgások", "status": "…", "score": null, "summary": "", "suggested_action": ""},
    {"key": "application", "label": "Alkalmazás", "status": "…", "score": null, "summary": "", "suggested_action": ""},
    {"key": "closing", "label": "Lezárás", "status": "…", "score": null, "summary": "", "suggested_action": ""},
    {"key": "pastoral_responsibility", "label": "Pásztori hang", "status": "…", "score": null, "summary": "", "suggested_action": ""}
  ],
  "ready_to_use": true,
  "next_step": "egy rövid mondat",
  "detailed_notes": ["opcionális"],
  "warnings": ["opcionális"]
}
"""

# Homiletikai profil 8 tengelye (dashboard és AI-séma).
OUTLINE_PROFILE_AREA_KEYS: tuple[str, ...] = (
    "text_fidelity",
    "unity_and_focus",
    "listener_tension",
    "christ_centeredness",
    "sermon_path",
    "application",
    "closing",
    "pastoral_responsibility",
)

OUTLINE_PROFILE_AREA_LABELS: dict[str, str] = {
    "text_fidelity": "Textushűség",
    "unity_and_focus": "Fő gondolat és fókusz",
    "listener_tension": "Hallgatói megszólítás",
    "christ_centeredness": "Krisztus-központúság",
    "sermon_path": "Szerkezet és mozgások",
    "application": "Alkalmazás",
    "closing": "Lezárás",
    "pastoral_responsibility": "Pásztori hang",
}

_USER_API_FAIL = "A részletes MI-diagnosztika most nem sikerült."
_USER_PARSE_FAIL = "A diagnosztikai válasz nem volt érvényes."


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def _normalize_area_score(raw: Any, *, status: str) -> int | None:
    """Hiányzó adat → None (soha ne 0). Érvényes score: 1–4."""
    if status == "not_enough_information":
        return None
    if raw is None or raw == "":
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return max(1, min(4, n))


def _parse_diagnostic_areas(raw: Any) -> list[dict[str, Any]]:
    """8 profil-tengely; hiányzó tengely → not_enough_information, score=null."""
    by_key: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = _s(item.get("key"))
            if key not in OUTLINE_PROFILE_AREA_KEYS:
                continue
            status = _s(item.get("status")) or "not_enough_information"
            if status not in (
                "strong",
                "stable",
                "needs_attention",
                "critical_gap",
                "not_enough_information",
            ):
                status = "not_enough_information"
            score = _normalize_area_score(item.get("score"), status=status)
            by_key[key] = {
                "key": key,
                "label": OUTLINE_PROFILE_AREA_LABELS.get(
                    key, _s(item.get("label")) or key
                ),
                "status": status,
                "score": score,
                "summary": _as_text(item.get("summary")),
                "suggested_action": _as_text(item.get("suggested_action")),
            }
    out: list[dict[str, Any]] = []
    for key in OUTLINE_PROFILE_AREA_KEYS:
        if key in by_key:
            out.append(by_key[key])
        else:
            out.append(
                {
                    "key": key,
                    "label": OUTLINE_PROFILE_AREA_LABELS[key],
                    "status": "not_enough_information",
                    "score": None,
                    "summary": "",
                    "suggested_action": "",
                }
            )
    return out


def parse_outline_diagnostics(raw: str) -> OutlineDiagnosticsResult:
    if not _s(raw) or _is_api_error_text(raw):
        return OutlineDiagnosticsResult(
            ok=False,
            mode="api_error",
            error_message=_USER_API_FAIL,
            raw_response=raw or "",
        )
    obj = extract_json_object(raw)
    if not isinstance(obj, dict):
        return OutlineDiagnosticsResult(
            ok=False,
            mode="parse_error",
            error_message=_USER_PARSE_FAIL,
            raw_response=raw,
        )
    strengths = [_s(x) for x in _as_str_list(obj.get("strengths")) if _s(x)][
        :MAX_STRENGTHS
    ]
    refinements: list[OutlineRefinement] = []
    for item in obj.get("refinements") or []:
        if not isinstance(item, dict):
            continue
        title = _s(item.get("title"))
        if not title:
            continue
        refinements.append(
            OutlineRefinement(
                title=title,
                explanation=_as_text(item.get("explanation")),
                suggested_action=_as_text(item.get("suggested_action")),
                affected_outline_parts=[
                    _s(x)
                    for x in (item.get("affected_outline_parts") or [])
                    if _s(x)
                ],
            )
        )
        if len(refinements) >= MAX_REFINEMENTS:
            break
    areas = _parse_diagnostic_areas(obj.get("diagnostic_areas"))
    evaluated = sum(
        1
        for a in areas
        if a.get("status") != "not_enough_information"
        or _s(a.get("summary"))
    )
    overview = _as_text(obj.get("overview"))
    if not overview and not strengths and not refinements and evaluated == 0:
        return OutlineDiagnosticsResult(
            ok=False,
            mode="parse_error",
            error_message=_USER_PARSE_FAIL,
            raw_response=raw,
        )
    return OutlineDiagnosticsResult(
        overview=overview,
        strengths=strengths,
        refinements=refinements,
        diagnostic_areas=areas,
        ready_to_use=bool(obj.get("ready_to_use")),
        next_step=_as_text(obj.get("next_step")),
        detailed_notes=[
            _s(x) for x in _as_str_list(obj.get("detailed_notes")) if _s(x)
        ],
        warnings=[_s(x) for x in _as_str_list(obj.get("warnings")) if _s(x)],
        mode="ai",
        ok=True,
        raw_response=raw,
    )


def fallback_outline_diagnostics(
    *,
    outline: Mapping[str, Any],
    message: str = "",
) -> OutlineDiagnosticsResult:
    """Hálózat nélküli / hiányos válasz esetén egyszerű heurisztika.

    Nem bünteti a kihagyott műhelymodulokat — csak a vázlat tartalmát nézi.
    """
    strengths: list[str] = []
    refinements: list[OutlineRefinement] = []
    if _s(outline.get("main_idea")):
        strengths.append("Van világos igehirdetési fő gondolat.")
    mvs = outline.get("movements") if isinstance(outline.get("movements"), list) else []
    if mvs:
        strengths.append("A prédikációs mozgások struktúrája kirajzolódik.")
    closing = outline.get("closing") if isinstance(outline.get("closing"), dict) else {}
    if _s(closing.get("final_insight")):
        strengths.append("A lezárás irányát rögzítetted.")
    if _s(outline.get("opening_direction")) and len(strengths) < MAX_STRENGTHS:
        strengths.append("A bevezetési irány kirajzolódik.")
    strengths = strengths[:MAX_STRENGTHS]

    # Csak tényleges vázlathiány — ne küldjük az M6/M7 modulba
    if not _s(outline.get("main_idea")):
        refinements.append(
            OutlineRefinement(
                title="Fő gondolat még gyenge",
                explanation="A vázlat magja még nem kristályosodott ki egy mondatban.",
                suggested_action="Fogalmazz meg egyetlen, hallható fő gondolatot a vázlatban.",
                affected_outline_parts=["main_idea"],
            )
        )
    elif not mvs:
        refinements.append(
            OutlineRefinement(
                title="Mozgások még hiányoznak",
                explanation="A hallható ívhez legalább néhány világos mozgás segít.",
                suggested_action="Egészítsd ki a vázlat mozgásait, majd futtasd újra az ellenőrzést.",
                affected_outline_parts=["movements"],
            )
        )
    elif len(mvs) == 1:
        refinements.append(
            OutlineRefinement(
                title="Az ív még rövid",
                explanation="Egyetlen mozgás mellett a hallgatói út kevésbé bontakozik ki.",
                suggested_action="Ha indokolt, adj még egy-két világos mozgást a vázlathoz.",
                affected_outline_parts=["movements"],
            )
        )
    if not _s(closing.get("final_insight")) and len(refinements) < MAX_REFINEMENTS:
        refinements.append(
            OutlineRefinement(
                title="Lezárás még nyitott",
                explanation="A megérkezés nélkül a vázlat nehezebben zárul.",
                suggested_action="Rögzíts egy rövid végső felismerést a vázlat lezárásában.",
                affected_outline_parts=["closing"],
            )
        )
    # Rövid vázlat — nem hiba, csak jelzés
    notes: list[str] = []
    blob_len = len(_s(outline.get("main_idea"))) + sum(
        len(_s(m.get("core_content")) if isinstance(m, dict) else "") for m in mvs
    )
    if blob_len < 120:
        notes.append(
            "Az alkalmazás részletezettsége még nem ítélhető meg teljesen, "
            "mert a vázlat ezen a ponton rövid."
        )

    refinements = refinements[:MAX_REFINEMENTS]
    ready = bool(strengths) and len(refinements) == 0
    overview = (
        "A vázlat alapjai kirajzolódnak; a finomítandó pontok a lenti listában vannak."
        if refinements
        else "A vázlat koherensnek tűnik a rendelkezésre álló anyag alapján."
    )
    if message:
        overview = message
    return OutlineDiagnosticsResult(
        overview=overview,
        strengths=strengths,
        refinements=refinements,
        # Gyors helyi ellenőrzés: NEM töltünk ki kitalált 0/8-as dashboardot.
        diagnostic_areas=[],
        ready_to_use=ready,
        next_step=(
            "A vázlat használható kézi kidolgozásra."
            if ready
            else "Kezdd a legelső finomítási javaslattal."
        ),
        detailed_notes=notes,
        mode="local_heuristic",
        ok=True,
        warnings=[
            "Gyors helyi ellenőrzés — nem teljes MI-diagnosztika.",
            "Az ellenőrzés a jelenlegi vázlat alapján készült.",
        ],
    )


def _api_failure_result(
    *,
    technical: str = "",
    raw: str = "",
    mode: str = "api_error",
) -> OutlineDiagnosticsResult:
    """API / hálózat / parse hiba — soha ne jelenjen meg sikeres diagnózisként."""
    warnings: list[str] = []
    if technical:
        warnings.append(f"Generálási hiba: {technical}")
    return OutlineDiagnosticsResult(
        ok=False,
        mode=mode,
        error_message=_USER_API_FAIL if mode == "api_error" else _USER_PARSE_FAIL,
        warnings=warnings,
        raw_response=raw,
        diagnostic_areas=[],
    )


def run_outline_diagnostics(
    *,
    sermon_outline: Any,
    sermon_main_idea: str = "",
    listener_tension: Any = None,
    christ_centered_arc: Any = None,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    closing: Any = None,
    selected_images: Any = None,
    illustrations: Any = None,
    applications: Any = None,
    passage: str = "",
    bible_translation: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    generate_fn: GenerateFn | None = None,
    prefer_local_heuristic: bool = False,
    **_extra: Any,
) -> OutlineDiagnosticsResult:
    """Vázlatközpontú diagnosztika. Nincs vázlat → nem futtat teljes nyers M8-at.

    API-hiba esetén ok=False (nincs hamis siker / heurisztikus ál-diagnózis).
    A gyors helyi ellenőrzés csak generate_fn=None vagy prefer_local_heuristic=True
    esetén fut, és mode=local_heuristic jelzéssel tér vissza.
    """
    outline = normalize_sermon_outline(sermon_outline)
    if not outline_has_content(outline):
        return OutlineDiagnosticsResult(
            ok=False,
            missing_outline=True,
            error_message="Előbb állítsd össze az igehirdetési vázlatot.",
            overview="",
            next_step="Előbb állítsd össze az igehirdetési vázlatot.",
        )

    # Összevető kontextus: elsősorban a vázlat; a műhelyblokkok csak röviden,
    # ha a vázlatban még nincs megfelelő tartalom.
    ctx = build_diagnostics_context(
        passage=passage,
        bible_translation=bible_translation,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        sermon_main_idea=sermon_main_idea or _s(outline.get("main_idea")),
        sermon_main_idea_status="approved",
        listener_tension=listener_tension
        if not _s(outline.get("listener_question"))
        else None,
        christ_centered_arc=christ_centered_arc
        if not _s(outline.get("divine_gracious_action"))
        else None,
        sermon_path=sermon_path,
        sermon_movements=outline.get("movements") or sermon_movements,
        selected_images=selected_images,
        illustrations=illustrations,
        applications=applications,
        closing=outline.get("closing") or closing,
    )
    ctx["outline_json"] = _outline_context_block(outline)
    # Tokenhatékonyság: a sablon csak a fő gondolatot és a vázlat JSON-t használja
    ctx.setdefault("sermon_main_idea", sermon_main_idea or _s(outline.get("main_idea")))
    ctx.setdefault("passage", passage or "")

    if generate_fn is None or prefer_local_heuristic:
        return fallback_outline_diagnostics(outline=outline)

    prompt = _fill(_OUTLINE_DIAG_TEMPLATE, ctx)
    try:
        raw = generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_OUTLINE_DIAG,
            use_cache=False,
            system_bundle=(
                "Te a TEXTUS homiletikai diagnoszta asszisztense vagy. "
                "A vizsgált tárgy a végső vázlat, nem a kitöltött modulok száma. "
                "Ne minősítsd hibának a kihagyott műhelyszakaszokat. "
                "Hiányzó adatnál score=null és status=not_enough_information. "
                "Válaszod KIZÁRÓLAG érvényes JSON."
            ),
            temperature=DEFAULT_TEMPERATURE,
        )
    except Exception as exc:  # noqa: BLE001
        return _api_failure_result(technical=str(exc), mode="api_error")

    if _is_api_error_text(raw or ""):
        return _api_failure_result(
            technical=_s(raw)[:400],
            raw=raw or "",
            mode="api_error",
        )

    parsed = parse_outline_diagnostics(raw or "")
    if not parsed.ok:
        return parsed
    # Kemény korlátok
    parsed.strengths = parsed.strengths[:MAX_STRENGTHS]
    parsed.refinements = parsed.refinements[:MAX_REFINEMENTS]
    notice = "Az ellenőrzés a jelenlegi vázlat alapján készült."
    if notice not in parsed.warnings:
        parsed.warnings = list(parsed.warnings) + [notice]
    parsed.mode = "ai"
    return parsed


__all__ = [
    "TAB_OUTLINE_DIAG",
    "MAX_STRENGTHS",
    "MAX_REFINEMENTS",
    "MISSING_PART",
    "OUTLINE_PROFILE_AREA_KEYS",
    "OUTLINE_PROFILE_AREA_LABELS",
    "OutlineDiagnosticsResult",
    "OutlineRefinement",
    "adapt_m8_to_outline_diagnostics",
    "empty_outline_diagnostics",
    "normalize_outline_diagnostics",
    "parse_outline_diagnostics",
    "run_outline_diagnostics",
    "fallback_outline_diagnostics",
]
