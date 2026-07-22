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

## Vizsgáld elsősorban
- egyetlen fő gondolat körül épül-e;
- a bevezetés megnyitja-e a központi kérdést;
- a mozgások különböző funkciót töltenek-e be / ismétlés nélkül;
- világos-e az evangéliumi fordulat;
- az alkalmazások kegyelemből fakadnak-e;
- a lezárás oda érkezik-e, ahová az út vezetett;
- hallás útján követhető-e;
- maradt-e hely a prédikátor saját hangjának;
- lekció / imádság: összhang, nem versengő téma, előtti/utáni nem keveredik,
  nem váltak teljes sablonos MI-imádsággá.

## Korlátok
- strengths: legfeljebb 3, csak valódi erősség;
- refinements: legfeljebb 3; ne gyárts mesterséges harmadik problémát;
- detailed_notes: opcionális, mélyebb megjegyzések.

## Vázlat JSON
{{outline_json}}

## Összevetés (rövid műhelykivonat)
Fő gondolat: {{sermon_main_idea}}
Hallgatói feszültség: {{listener_tension_block}}
Evangéliumi ív: {{christ_arc_block}}
Mozgások: {{movements_block}}
Lezárás: {{closing_block}}

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
  "ready_to_use": true,
  "next_step": "egy rövid mondat",
  "detailed_notes": ["opcionális"],
  "warnings": ["opcionális"]
}
"""


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def parse_outline_diagnostics(raw: str) -> OutlineDiagnosticsResult:
    if not _s(raw) or _is_api_error_text(raw):
        return OutlineDiagnosticsResult(
            ok=False,
            error_message="A vázlatdiagnosztika nem adott érvényes választ.",
            raw_response=raw or "",
        )
    obj = extract_json_object(raw)
    if not isinstance(obj, dict):
        return OutlineDiagnosticsResult(
            ok=False,
            error_message="Érvénytelen diagnosztikai JSON.",
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
    return OutlineDiagnosticsResult(
        overview=_as_text(obj.get("overview")),
        strengths=strengths,
        refinements=refinements,
        ready_to_use=bool(obj.get("ready_to_use")),
        next_step=_as_text(obj.get("next_step")),
        detailed_notes=[
            _s(x) for x in _as_str_list(obj.get("detailed_notes")) if _s(x)
        ],
        warnings=[_s(x) for x in _as_str_list(obj.get("warnings")) if _s(x)],
        ok=True,
        raw_response=raw,
    )


def fallback_outline_diagnostics(
    *,
    outline: Mapping[str, Any],
    message: str = "",
) -> OutlineDiagnosticsResult:
    """Hálózat nélküli / hiányos válasz esetén egyszerű heurisztika."""
    strengths: list[str] = []
    refinements: list[OutlineRefinement] = []
    if _s(outline.get("main_idea")):
        strengths.append("Van világos igehirdetési fő gondolat.")
    if outline.get("movements"):
        strengths.append("A prédikációs mozgások struktúrája kirajzolódik.")
    closing = outline.get("closing") if isinstance(outline.get("closing"), dict) else {}
    if _s(closing.get("final_insight")):
        strengths.append("A lezárás irányát rögzítetted.")
    strengths = strengths[:MAX_STRENGTHS]

    if not _s(outline.get("opening_direction")):
        refinements.append(
            OutlineRefinement(
                title="Bevezetési irány hiányzik",
                explanation="A vázlat még nem rögzítette, hogyan nyílik meg a prédikáció.",
                suggested_action="Fogalmazz meg rövid kiindulópontot a hallgatói kérdéshez kapcsolva.",
                affected_outline_parts=["opening_direction"],
            )
        )
    mvs = outline.get("movements") or []
    if isinstance(mvs, list) and len(mvs) < 3:
        refinements.append(
            OutlineRefinement(
                title="Kevesebb mint három mozgás",
                explanation="A hallható ívhez általában legalább három mozgás segít.",
                suggested_action="Egészítsd ki a mozgásokat az M6 szakaszban, majd frissítsd a vázlatot.",
                affected_outline_parts=["movements"],
            )
        )
    if not _s(closing.get("final_insight")):
        refinements.append(
            OutlineRefinement(
                title="Lezárás még nyitott",
                explanation="A megérkezés nélkül a vázlat nehezebben zárul.",
                suggested_action="Rögzíts egy végső felismerést a Lezárás szakaszban.",
                affected_outline_parts=["closing"],
            )
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
        ready_to_use=ready,
        next_step=(
            "A vázlat használható kézi kidolgozásra."
            if ready
            else "Kezdd a legelső finomítási javaslattal."
        ),
        ok=True,
        warnings=[],
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
    **_extra: Any,
) -> OutlineDiagnosticsResult:
    """Vázlatközpontú diagnosztika. Nincs vázlat → nem futtat teljes nyers M8-at."""
    outline = normalize_sermon_outline(sermon_outline)
    if not outline_has_content(outline):
        return OutlineDiagnosticsResult(
            ok=False,
            missing_outline=True,
            error_message="Előbb állítsd össze az igehirdetési vázlatot.",
            overview="",
            next_step="Előbb állítsd össze az igehirdetési vázlatot.",
        )

    # Összevető kontextus a műhelyből (UI-ban nem jelenik meg nyersen)
    ctx = build_diagnostics_context(
        passage=passage,
        bible_translation=bible_translation,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        sermon_main_idea=sermon_main_idea or _s(outline.get("main_idea")),
        sermon_main_idea_status="approved",
        listener_tension=listener_tension,
        christ_centered_arc=christ_centered_arc,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements or outline.get("movements"),
        selected_images=selected_images,
        illustrations=illustrations,
        applications=applications,
        closing=closing or outline.get("closing"),
    )
    ctx["outline_json"] = _outline_context_block(outline)

    if generate_fn is None:
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
                "Csak a megadott vázlatból és összevető kivonatból dolgozz. "
                "Válaszod KIZÁRÓLAG érvényes JSON."
            ),
            temperature=DEFAULT_TEMPERATURE,
        )
    except Exception as exc:  # noqa: BLE001
        result = fallback_outline_diagnostics(
            outline=outline,
            message="A diagnosztika hálózati hiba miatt heurisztikus módra váltott.",
        )
        result.warnings.append(str(exc))
        return result

    if _is_api_error_text(raw or ""):
        return fallback_outline_diagnostics(
            outline=outline,
            message="A diagnosztika nem volt elérhető; heurisztikus összkép készült.",
        )

    parsed = parse_outline_diagnostics(raw or "")
    if not parsed.ok or not (parsed.overview or parsed.strengths or parsed.refinements):
        fb = fallback_outline_diagnostics(outline=outline)
        fb.raw_response = raw or ""
        return fb
    # Kemény korlátok
    parsed.strengths = parsed.strengths[:MAX_STRENGTHS]
    parsed.refinements = parsed.refinements[:MAX_REFINEMENTS]
    return parsed


__all__ = [
    "TAB_OUTLINE_DIAG",
    "MAX_STRENGTHS",
    "MAX_REFINEMENTS",
    "MISSING_PART",
    "OutlineDiagnosticsResult",
    "OutlineRefinement",
    "adapt_m8_to_outline_diagnostics",
    "empty_outline_diagnostics",
    "normalize_outline_diagnostics",
    "parse_outline_diagnostics",
    "run_outline_diagnostics",
    "fallback_outline_diagnostics",
]
