"""Igehirdetési műhely — igehirdetési vázlat összeállítása (M10).

Determinisztikus összeszerelés a jóváhagyott / megtartott műhelyanyagból.
Az opcionális MI csak tömörítést és átmeneteket finomíthat — új teológiát,
illusztrációt, alkalmazást vagy fő gondolatot nem talál ki.
Nem importál app.py / sermon_workshop_ui.py fájlból.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    empty_outline_movement,
    empty_sermon_outline,
    ensure_sermon_workshop_state,
    normalize_applications,
    normalize_illustrations,
    normalize_sermon_movements,
    normalize_sermon_outline,
    normalize_textual_images,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _as_text, _is_api_error_text
from sermon_workshop_m5_gospel_ai import christ_connection_type_label
from sermon_workshop_m6_ai import movement_role_label
from sermon_workshop_m7_closing_ai import closing_tone_label

TAB_OUTLINE = "Igehirdetési vázlat"
MISSING_PART = "Ez a rész még nincs kidolgozva."
DEFAULT_TEMPERATURE = 0.1

GenerateFn = Callable[..., str]


def _s(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _session_str(session: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        val = _s(session.get(key))
        if val:
            return val
    return ""


def _prayer_side_retained(side: Mapping[str, Any] | None) -> dict[str, Any]:
    """Csak megtartott / átvett imádsági elemek — nem az összes MI-javaslat."""
    block = side if isinstance(side, dict) else {}
    lines_raw = block.get("selected_lines")
    lines: list[str] = []
    if isinstance(lines_raw, list):
        for item in lines_raw:
            text = _s(item)
            if text:
                lines.append(text)
    notes = _s(block.get("movement_notes"))
    movements = [notes] if notes else []
    return {
        "movements": movements,
        "own_thoughts": _s(block.get("own_thoughts")),
        "selected_opening": _s(block.get("selected_opening")),
        "selected_lines": lines,
        "closing_direction": _s(block.get("closing_direction")),
    }


def _enrichment_text(item: Mapping[str, Any], *, kind: str) -> str:
    if kind == "image":
        return _s(item.get("image"))
    if kind == "illustration":
        return _s(item.get("idea"))
    return _s(item.get("application"))


def _attach_enrichment(
    movements: list[dict[str, Any]],
    *,
    images: list[dict[str, str]],
    illustrations: list[dict[str, str]],
    applications: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    by_id = {str(m.get("id") or ""): m for m in movements if m.get("id")}
    used_ids: set[str] = set()
    extra: dict[str, list[str]] = {
        "images": [],
        "illustrations": [],
        "applications": [],
    }

    def place(items: list[dict[str, str]], kind: str, target_key: str) -> None:
        for item in items:
            text = _enrichment_text(item, kind=kind)
            if not text:
                continue
            mid = _s(item.get("movement_id"))
            if mid and mid in by_id:
                by_id[mid][target_key].append(text)
                used_ids.add(mid)
            else:
                extra[target_key].append(text)

    place(images, "image", "images")
    place(illustrations, "illustration", "illustrations")
    place(applications, "application", "applications")
    return movements, extra


def _has_any_text(*values: Any) -> bool:
    for value in values:
        if isinstance(value, list):
            if any(_s(x) for x in value):
                return True
        elif isinstance(value, dict):
            if _has_any_text(*value.values()):
                return True
        elif _s(value):
            return True
    return False


def build_outline_from_workshop(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Műhelyanyag → vázlat struktúra. Nem módosít sessiont / forrásmezőket."""
    sw = (
        dict(sermon_workshop)
        if isinstance(sermon_workshop, dict)
        else dict(session_state.get(SERMON_WORKSHOP_KEY) or {})
    )
    outline = empty_sermon_outline()

    outline["project_title"] = _session_str(
        session_state, "current_project_title", "project_title_input"
    )
    outline["passage_reference"] = _session_str(
        session_state, "last_igehely", "igehely_input", "passage_reference"
    )
    outline["bible_translation"] = _session_str(
        session_state, "bible_translation"
    ) or "RÚF 2014"
    outline["sermon_title"] = _session_str(
        session_state, "sermon_title", "current_sermon_title"
    )

    idea = _s(sw.get("sermon_main_idea"))
    outline["main_idea"] = idea
    # Rövid kifejtés csak ha van approved insights / summary a textus műhelyből —
    # de új teológiát nem találunk ki; max tömörítés a meglévő fő gondolatból.
    if idea and len(idea) > 180:
        outline["main_idea_summary"] = idea[:177].rstrip() + "…"
    else:
        outline["main_idea_summary"] = ""

    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    outline["listener_question"] = _s(lt.get("listener_question"))
    outline["central_tension"] = _s(lt.get("sermon_tension"))
    outline["listener_resistance"] = _s(lt.get("listener_resistance"))

    arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    outline["divine_gracious_action"] = _s(arc.get("divine_gracious_action"))
    outline["christ_connection"] = _s(arc.get("christ_connection"))
    ctype = _s(arc.get("christ_connection_type"))
    outline["christ_connection_type_label"] = (
        christ_connection_type_label(ctype) if ctype else ""
    )
    outline["gospel_resolution"] = _s(lt.get("promised_resolution"))
    outline["grace_enabled_response"] = _s(arc.get("grace_enabled_response"))

    path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    start = _s(path.get("starting_point"))
    question = outline["listener_question"]
    if start and question:
        outline["opening_direction"] = (
            f"Kiindulópont: {start}. A hallgatói kérdés, amely megnyitja: {question}"
        )
    elif start:
        outline["opening_direction"] = f"Kiindulópont: {start}."
    elif question:
        outline["opening_direction"] = f"Hallgatói nyitás: {question}"
    else:
        outline["opening_direction"] = ""

    movements_out: list[dict[str, Any]] = []
    for mv in normalize_sermon_movements(sw.get("sermon_movements")):
        role = _s(mv.get("role"))
        item = empty_outline_movement()
        item.update(
            {
                "id": _s(mv.get("id")),
                "title": _s(mv.get("title")),
                "role": role,
                "role_label": movement_role_label(role) if role else "",
                "textual_basis": _s(mv.get("textual_basis")),
                "core_content": _s(mv.get("core_content")),
                "listener_discovery": _s(mv.get("listener_discovery")),
                "transition": _s(mv.get("transition_to_next")),
                "images": [],
                "illustrations": [],
                "applications": [],
            }
        )
        movements_out.append(item)

    images = normalize_textual_images(sw.get("selected_images"))
    illustrations = normalize_illustrations(sw.get("illustrations"))
    applications = normalize_applications(sw.get("applications"))
    movements_out, extra = _attach_enrichment(
        movements_out,
        images=images,
        illustrations=illustrations,
        applications=applications,
    )
    outline["movements"] = movements_out
    outline["extra_enrichment"] = extra

    closing = sw.get("closing") if isinstance(sw.get("closing"), dict) else {}
    tone = _s(closing.get("tone"))
    outline["closing"] = {
        "final_insight": _s(closing.get("final_discovery")),
        "gospel_assurance": _s(closing.get("hope")),
        "invitation": _s(closing.get("call_or_response")),
        "image_or_line": _s(closing.get("image_or_line")),
        "open_question": _s(closing.get("open_question")),
        "tone": tone,
        "tone_label": closing_tone_label(tone) if tone else "",
    }

    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    lec_ref = _s(lection.get("reference"))
    outline["lection_reference"] = lec_ref
    outline["lection_translation"] = (
        outline["bible_translation"] if lec_ref else ""
    )
    outline["lection"] = {
        "reference": lec_ref,
        "function": _s(lection.get("function")),
        "rationale": _s(lection.get("rationale")),
    }

    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    before = prep.get("before") if isinstance(prep.get("before"), dict) else {}
    after = prep.get("after") if isinstance(prep.get("after"), dict) else {}
    outline["prayer_before"] = _prayer_side_retained(before)
    outline["prayer_after"] = _prayer_side_retained(after)

    stamp = _now()
    outline["generated_at"] = stamp
    outline["updated_at"] = stamp
    outline["status"] = "draft"
    outline["manually_edited"] = False
    outline["manual_notes"] = ""
    return normalize_sermon_outline(outline)


def outline_has_content(outline: Any) -> bool:
    if not isinstance(outline, dict) or not outline:
        return False
    skip = {
        "status",
        "generated_at",
        "updated_at",
        "manually_edited",
        "bible_translation",
        "lection_translation",
    }
    return _has_any_text(*(v for k, v in outline.items() if k not in skip))


def outline_part_display(value: Any, *, missing: str = MISSING_PART) -> str:
    """Üres részhez hiányjelzés; listákhoz vesszős összegzés."""
    if isinstance(value, list):
        items = [_s(x) for x in value if _s(x)]
        return "; ".join(items) if items else missing
    if isinstance(value, dict):
        return missing if not _has_any_text(*value.values()) else ""
    text = _s(value)
    return text if text else missing


@dataclass
class OutlineAssemblyResult:
    outline: dict[str, Any] = field(default_factory=empty_sermon_outline)
    ok: bool = True
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)
    overwritten_manual_edit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "outline": dict(self.outline),
            "ok": self.ok,
            "error_message": self.error_message,
            "warnings": list(self.warnings),
            "overwritten_manual_edit": self.overwritten_manual_edit,
        }


_POLISH_SYSTEM = """\
Te a TEXTUS homiletikai segéd asszisztense vagy.
A megadott igehirdetési vázlatot csak áttekinthetőbbé és tömörebbé teheted.
TILOS: új teológiai tartalom, új illusztráció, új alkalmazás, új fő gondolat,
új igehely, teljes kézirat, teljes imádság.
Csak a meglévő mondatok tömörítése / rövid összekötő átmenetek.
Válaszod KIZÁRÓLAG érvényes JSON legyen, ugyanezzel a szerkezettel.\
"""


def _optional_polish(
    outline: dict[str, Any],
    *,
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    """Opcionális MI-tömörítés; hiba esetén az eredeti vázlat marad."""
    if generate_fn is None:
        return outline, []
    warnings: list[str] = []
    try:
        import json

        payload = json.dumps(outline, ensure_ascii=False)
        prompt = (
            "Tömörítsd a vázlatot a meglévő tartalom megőrzésével. "
            "Ne találj ki új elemet.\n\n"
            f"VÁZLAT JSON:\n{payload}"
        )
        raw = generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_OUTLINE,
            use_cache=False,
            system_bundle=_POLISH_SYSTEM,
            temperature=DEFAULT_TEMPERATURE,
        )
        if _is_api_error_text(raw or ""):
            warnings.append("A vázlat-tömörítés nem sikerült; az alapösszeállítás megmaradt.")
            return outline, warnings
        obj = extract_json_object(raw or "")
        if not isinstance(obj, dict):
            warnings.append("Érvénytelen tömörítési válasz; az alapösszeállítás megmaradt.")
            return outline, warnings
        # Csak meglévő kulcsokon engedünk finomítást — struktúra + forrástartalom védelme
        merged = dict(outline)
        for key in (
            "main_idea_summary",
            "opening_direction",
            "manual_notes",
        ):
            if _s(obj.get(key)):
                # Ne cserélje a jóváhagyott fő gondolatot
                if key == "main_idea_summary" and not _s(outline.get("main_idea")):
                    continue
                merged[key] = _as_text(obj.get(key))
        # Mozgás-átmenetek tömörítése, ha ugyanazok az id-k
        polished_mvs = obj.get("movements")
        if isinstance(polished_mvs, list) and merged.get("movements"):
            by_id = {
                _s(m.get("id")): m
                for m in polished_mvs
                if isinstance(m, dict) and _s(m.get("id"))
            }
            new_mvs = []
            for mv in merged["movements"]:
                if not isinstance(mv, dict):
                    continue
                copy_mv = dict(mv)
                other = by_id.get(_s(mv.get("id")))
                if other and _s(other.get("transition")):
                    copy_mv["transition"] = _as_text(other.get("transition"))
                new_mvs.append(copy_mv)
            merged["movements"] = new_mvs
        # Fő gondolat, képek, imák, lekció — soha ne jöjjön MI-ből új tartalom
        for locked in (
            "main_idea",
            "passage_reference",
            "lection_reference",
            "lection",
            "prayer_before",
            "prayer_after",
            "extra_enrichment",
        ):
            merged[locked] = outline.get(locked)
        for i, mv in enumerate(merged.get("movements") or []):
            if not isinstance(mv, dict):
                continue
            src = (outline.get("movements") or [None])[i] if i < len(
                outline.get("movements") or []
            ) else None
            if not isinstance(src, dict):
                continue
            for field_name in (
                "title",
                "role",
                "role_label",
                "textual_basis",
                "core_content",
                "listener_discovery",
                "images",
                "illustrations",
                "applications",
                "id",
            ):
                mv[field_name] = src.get(field_name)
        return normalize_sermon_outline(merged), warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Tömörítés kihagyva: {exc}")
        return outline, warnings


def assemble_sermon_outline(
    session_state: MutableMapping[str, Any],
    *,
    generate_fn: GenerateFn | None = None,
    force_overwrite: bool = False,
    polish: bool = False,
) -> OutlineAssemblyResult:
    """Összeállítja a vázlatot a műhelyanyagból.

    Nem módosítja a forrás műhelymezőket. Ha már van kézzel szerkesztett
    vázlat és `force_overwrite` False, nem írja felül — jelez.
    """
    ensure_sermon_workshop_state(session_state)
    sw = session_state[SERMON_WORKSHOP_KEY]
    existing = normalize_sermon_outline(sw.get("sermon_outline"))
    manually_edited = bool(
        existing.get("manually_edited")
        or _s(sw.get("sermon_outline_status")) == "approved"
    )
    if (
        outline_has_content(existing)
        and manually_edited
        and not force_overwrite
    ):
        return OutlineAssemblyResult(
            outline=existing,
            ok=False,
            error_message=(
                "A vázlat kézzel szerkesztve van. "
                "Frissítéshez használd: „Vázlat frissítése a műhelyanyagokból”."
            ),
            overwritten_manual_edit=False,
        )

    outline = build_outline_from_workshop(session_state, sermon_workshop=sw)
    warnings: list[str] = []
    if polish:
        outline, polish_warnings = _optional_polish(outline, generate_fn=generate_fn)
        warnings.extend(polish_warnings)

    return OutlineAssemblyResult(
        outline=outline,
        ok=True,
        warnings=warnings,
        overwritten_manual_edit=bool(manually_edited and force_overwrite),
    )


__all__ = [
    "TAB_OUTLINE",
    "MISSING_PART",
    "GenerateFn",
    "OutlineAssemblyResult",
    "assemble_sermon_outline",
    "build_outline_from_workshop",
    "empty_sermon_outline",
    "outline_has_content",
    "outline_part_display",
]
