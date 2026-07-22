"""Igehirdetési műhely — igehirdetési vázlat összeállítása (M10).

Részleges munkafolyamatot is támogat: a rendelkezésre álló anyagból
állít össze munkavázlatot. Az opcionális egyetlen összegző MI-hívás
csak a hiányzó szerkezeti kapcsolatokat egészítheti ki a
`sermon_outline` belsejében — az M4–M9 forrásmezőket nem írja vissza.
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
from textus_workshop_data import TEXT_WORKSHOP_KEY, normalize_text_workshop

TAB_OUTLINE = "Igehirdetési vázlat"
MISSING_PART = "Ez a rész még nincs kidolgozva."
DEFAULT_TEMPERATURE = 0.2
MAX_PASSAGE_CHARS = 3200
MAX_EXEGESIS_CHARS = 1600
MAX_THEOLOGY_CHARS = 1200
MAX_HISTORY_CHARS = 800
MAX_INSIGHTS = 8
PROVISIONAL_NOTICE = (
    "A vázlat néhány összekötő eleme a rendelkezésre álló anyag alapján "
    "munkajavaslatként készült."
)
EMPTY_PROJECT_MESSAGE = (
    "A vázlathoz legalább a RÚF-szöveg betöltése vagy egy rövid saját "
    "gondolat / fő gondolat szükséges. Az igehely önmagában nem elég."
)

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


def _truncate(text: str, limit: int) -> str:
    raw = _s(text)
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip() + "…"


def _approved_insights_texts(tw: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for item in tw.get("approved_insights") or []:
        if not isinstance(item, dict):
            continue
        if item.get("approved") is False:
            continue
        content = _s(item.get("content"))
        if content:
            out.append(content)
        if len(out) >= MAX_INSIGHTS:
            break
    return out


@dataclass
class OutlineReadiness:
    ok: bool
    message: str = ""
    source_keys: list[str] = field(default_factory=list)


def assess_outline_readiness(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
) -> OutlineReadiness:
    """Minimális bemenet: igehely + legalább egy használható anyag."""
    sw = (
        dict(sermon_workshop)
        if isinstance(sermon_workshop, dict)
        else dict(session_state.get(SERMON_WORKSHOP_KEY) or {})
    )
    tw = normalize_text_workshop(session_state.get(TEXT_WORKSHOP_KEY))
    passage_ref = _session_str(
        session_state, "last_igehely", "igehely_input", "passage_reference"
    )
    sources: list[str] = []
    if passage_ref:
        sources.append("passage_reference")

    passage_text = _session_str(session_state, "passage_text")
    if passage_text:
        sources.append("passage_text")
    if _s(tw.get("text_main_idea")):
        sources.append("text_main_idea")
    if _approved_insights_texts(tw):
        sources.append("approved_insights")
    if _session_str(session_state, "exegesis"):
        sources.append("exegesis")
    if _session_str(session_state, "theology"):
        sources.append("theology")
    if _session_str(session_state, "history"):
        sources.append("history")
    if _s(sw.get("sermon_main_idea")):
        sources.append("sermon_main_idea")
    if _s(session_state.get("last_sajat")) or _s(session_state.get("sajat_input")):
        sources.append("user_notes")
    existing = normalize_sermon_outline(sw.get("sermon_outline"))
    if _s(existing.get("manual_notes")):
        sources.append("outline_manual_notes")
    movements = normalize_sermon_movements(sw.get("sermon_movements"))
    if movements:
        sources.append("sermon_movements")
    hc = sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    if _has_any_text(*hc.values()):
        sources.append("human_condition")
    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    if _has_any_text(*lt.values()):
        sources.append("listener_tension")
    arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    if _has_any_text(*arc.values()):
        sources.append("christ_centered_arc")
    path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    if _has_any_text(*path.values()):
        sources.append("sermon_path")
    closing = sw.get("closing") if isinstance(sw.get("closing"), dict) else {}
    if _has_any_text(*closing.values()):
        sources.append("closing")

    substantive = [k for k in sources if k != "passage_reference"]
    if not passage_ref:
        return OutlineReadiness(
            ok=False,
            message="Add meg az igehelyet, majd tölts be RÚF-szöveget vagy egy rövid gondolatot.",
            source_keys=sources,
        )
    if not substantive:
        return OutlineReadiness(
            ok=False,
            message=EMPTY_PROJECT_MESSAGE,
            source_keys=sources,
        )
    return OutlineReadiness(ok=True, source_keys=sources)


def collect_outline_context_bundle(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Tokenhatékony forráscsomag — csak nem üres mezők, aliasok nélkül."""
    sw = (
        dict(sermon_workshop)
        if isinstance(sermon_workshop, dict)
        else dict(session_state.get(SERMON_WORKSHOP_KEY) or {})
    )
    tw = normalize_text_workshop(session_state.get(TEXT_WORKSHOP_KEY))
    bundle: dict[str, Any] = {
        "passage_reference": _session_str(
            session_state, "last_igehely", "igehely_input", "passage_reference"
        ),
        "occasion": _session_str(session_state, "last_alkalom", "alkalom_input"),
        "user_focus": _session_str(session_state, "last_sajat", "sajat_input"),
        "bible_translation": _session_str(session_state, "bible_translation")
        or "RÚF 2014",
        "project_title": _session_str(
            session_state, "current_project_title", "project_title_input"
        ),
        "source_keys": [],
    }
    keys: list[str] = []
    if bundle["passage_reference"]:
        keys.append("passage_reference")

    passage_text = _truncate(
        _session_str(session_state, "passage_text"), MAX_PASSAGE_CHARS
    )
    if passage_text:
        bundle["passage_text"] = passage_text
        keys.append("passage_text")

    # Forráshierarchia: jóváhagyott / elmentett műhely → textus → saját
    sermon_idea = _s(sw.get("sermon_main_idea"))
    sermon_status = _s(sw.get("sermon_main_idea_status"))
    text_idea = _s(tw.get("text_main_idea"))
    text_status = _s(tw.get("text_main_idea_status"))
    if sermon_idea:
        bundle["sermon_main_idea"] = sermon_idea
        bundle["sermon_main_idea_status"] = sermon_status or "draft"
        keys.append("sermon_main_idea")
    if text_idea:
        bundle["text_main_idea"] = text_idea
        bundle["text_main_idea_status"] = text_status or "draft"
        keys.append("text_main_idea")

    insights = _approved_insights_texts(tw)
    if insights:
        bundle["approved_insights"] = insights
        keys.append("approved_insights")

    for field_name, limit, session_key in (
        ("exegesis", MAX_EXEGESIS_CHARS, "exegesis"),
        ("theology", MAX_THEOLOGY_CHARS, "theology"),
        ("history", MAX_HISTORY_CHARS, "history"),
    ):
        text = _truncate(_session_str(session_state, session_key), limit)
        if text:
            bundle[field_name] = text
            keys.append(field_name)

    # Ne küldjük a nyers MI-alternatívákat / elutasított javaslatokat
    for block_key in (
        "human_condition",
        "listener_tension",
        "christ_centered_arc",
        "sermon_path",
        "closing",
    ):
        block = sw.get(block_key) if isinstance(sw.get(block_key), dict) else {}
        cleaned = {k: _s(v) for k, v in block.items() if _s(v)}
        if cleaned:
            bundle[block_key] = cleaned
            keys.append(block_key)

    movements = normalize_sermon_movements(sw.get("sermon_movements"))
    if movements:
        compact_mvs = []
        for mv in movements:
            compact_mvs.append(
                {
                    "id": _s(mv.get("id")),
                    "title": _s(mv.get("title")),
                    "role": _s(mv.get("role")),
                    "textual_basis": _s(mv.get("textual_basis")),
                    "core_content": _s(mv.get("core_content")),
                    "listener_discovery": _s(mv.get("listener_discovery")),
                    "transition_to_next": _s(mv.get("transition_to_next")),
                }
            )
        bundle["sermon_movements"] = compact_mvs
        keys.append("sermon_movements")

    images = normalize_textual_images(sw.get("selected_images"))
    illustrations = normalize_illustrations(sw.get("illustrations"))
    applications = normalize_applications(sw.get("applications"))
    if images:
        bundle["selected_images"] = images
        keys.append("selected_images")
    if illustrations:
        bundle["illustrations"] = illustrations
        keys.append("illustrations")
    if applications:
        bundle["applications"] = applications
        keys.append("applications")

    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    if _s(lection.get("reference")):
        bundle["lection"] = {
            "reference": _s(lection.get("reference")),
            "function": _s(lection.get("function")),
            "rationale": _truncate(_s(lection.get("rationale")), 400),
        }
        keys.append("lection")

    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    before = prep.get("before") if isinstance(prep.get("before"), dict) else {}
    after = prep.get("after") if isinstance(prep.get("after"), dict) else {}
    pb = _prayer_side_retained(before)
    pa = _prayer_side_retained(after)
    if _has_any_text(*pb.values()):
        bundle["prayer_before"] = pb
        keys.append("prayer_before")
    if _has_any_text(*pa.values()):
        bundle["prayer_after"] = pa
        keys.append("prayer_after")

    existing = normalize_sermon_outline(sw.get("sermon_outline"))
    if _s(existing.get("manual_notes")):
        bundle["outline_manual_notes"] = _s(existing.get("manual_notes"))
        keys.append("outline_manual_notes")

    bundle["source_keys"] = list(dict.fromkeys(keys))
    bundle["_sw"] = sw
    bundle["_tw"] = tw
    return bundle


def _prefer_main_idea(bundle: Mapping[str, Any]) -> str:
    sermon = _s(bundle.get("sermon_main_idea"))
    text = _s(bundle.get("text_main_idea"))
    sermon_status = _s(bundle.get("sermon_main_idea_status"))
    text_status = _s(bundle.get("text_main_idea_status"))
    if sermon and sermon_status == "approved":
        return sermon
    if text and text_status == "approved" and not sermon:
        return text
    if sermon:
        return sermon
    if text:
        return text
    insights = bundle.get("approved_insights") or []
    if isinstance(insights, list) and insights:
        return _s(insights[0])
    return ""


def _heuristic_provisional_movements(
    *,
    main_idea: str,
    insights: list[str],
    exegesis: str,
    christ: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """3 egyszerű mozgás — csak ha nincs M6, AI nélkül."""
    idea = _s(main_idea) or (insights[0] if insights else "")
    if not idea:
        return []
    christ = christ if isinstance(christ, dict) else {}
    grace = _s(christ.get("divine_gracious_action")) or _s(
        christ.get("grace_enabled_response")
    )
    second = _s(insights[1]) if len(insights) > 1 else ""
    if not second and exegesis:
        second = _truncate(exegesis, 220)
    if not second:
        second = "A textus a fő gondolatot a saját hangján bontja ki."
    third = grace or (
        _s(insights[2]) if len(insights) > 2 else "A hallgató a kegyelem felől válaszolhat."
    )
    specs = [
        ("Nyitás", "opening", "A hallgató a textus világába lép.", idea),
        ("Kibontás", "deepening", "A textus magja elmélyül.", second),
        ("Megérkezés", "arrival", "A fő gondolat megérkezik a hallgatóhoz.", third),
    ]
    out: list[dict[str, Any]] = []
    for i, (title, role, discovery, core) in enumerate(specs, start=1):
        item = empty_outline_movement()
        item.update(
            {
                "id": f"prov_mv_{i}",
                "title": title,
                "role": role,
                "role_label": movement_role_label(role) if role else title,
                "textual_basis": "",
                "core_content": _s(core),
                "listener_discovery": discovery,
                "transition": "",
                "images": [],
                "illustrations": [],
                "applications": [],
            }
        )
        out.append(item)
    return out


def build_outline_from_workshop(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Műhelyanyag → vázlat. Nem módosít sessiont / forrásmezőket."""
    bundle = collect_outline_context_bundle(
        session_state, sermon_workshop=sermon_workshop
    )
    sw = bundle.get("_sw") if isinstance(bundle.get("_sw"), dict) else {}
    outline = empty_sermon_outline()
    sources: list[str] = list(bundle.get("source_keys") or [])
    provisional: list[str] = []

    outline["project_title"] = _s(bundle.get("project_title"))
    outline["passage_reference"] = _s(bundle.get("passage_reference"))
    outline["bible_translation"] = _s(bundle.get("bible_translation")) or "RÚF 2014"
    outline["sermon_title"] = _session_str(
        session_state, "sermon_title", "current_sermon_title"
    )

    idea = _prefer_main_idea(bundle)
    outline["main_idea"] = idea
    if idea and len(idea) > 180:
        outline["main_idea_summary"] = idea[:177].rstrip() + "…"
    else:
        outline["main_idea_summary"] = ""

    lt = bundle.get("listener_tension") if isinstance(bundle.get("listener_tension"), dict) else {}
    outline["listener_question"] = _s(lt.get("listener_question"))
    outline["central_tension"] = _s(lt.get("sermon_tension"))
    outline["listener_resistance"] = _s(lt.get("listener_resistance"))

    arc = (
        bundle.get("christ_centered_arc")
        if isinstance(bundle.get("christ_centered_arc"), dict)
        else {}
    )
    hc = (
        bundle.get("human_condition")
        if isinstance(bundle.get("human_condition"), dict)
        else {}
    )
    outline["divine_gracious_action"] = _s(arc.get("divine_gracious_action")) or _s(
        hc.get("divine_action")
    )
    outline["christ_connection"] = _s(arc.get("christ_connection"))
    ctype = _s(arc.get("christ_connection_type"))
    outline["christ_connection_type_label"] = (
        christ_connection_type_label(ctype) if ctype else ""
    )
    outline["gospel_resolution"] = _s(lt.get("promised_resolution"))
    outline["grace_enabled_response"] = _s(arc.get("grace_enabled_response")) or _s(
        hc.get("grace_response")
    )

    path = bundle.get("sermon_path") if isinstance(bundle.get("sermon_path"), dict) else {}
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
    workshop_movements = bundle.get("sermon_movements") or []
    used_m6 = bool(workshop_movements)
    for mv in workshop_movements if isinstance(workshop_movements, list) else []:
        if not isinstance(mv, dict):
            continue
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

    images = list(bundle.get("selected_images") or [])
    illustrations = list(bundle.get("illustrations") or [])
    applications = list(bundle.get("applications") or [])
    if movements_out:
        movements_out, extra = _attach_enrichment(
            movements_out,
            images=images,
            illustrations=illustrations,
            applications=applications,
        )
    else:
        extra = {"images": [], "illustrations": [], "applications": []}
        for item in images:
            t = _enrichment_text(item, kind="image")
            if t:
                extra["images"].append(t)
        for item in illustrations:
            t = _enrichment_text(item, kind="illustration")
            if t:
                extra["illustrations"].append(t)
        for item in applications:
            t = _enrichment_text(item, kind="application")
            if t:
                extra["applications"].append(t)

    if not movements_out and idea:
        movements_out = _heuristic_provisional_movements(
            main_idea=idea,
            insights=list(bundle.get("approved_insights") or []),
            exegesis=_s(bundle.get("exegesis")),
            christ=arc or hc,
        )
        if movements_out:
            provisional.append("sermon_movements")
            if not used_m6:
                # Ne jelöljük M6 forrásként
                pass

    outline["movements"] = movements_out
    outline["extra_enrichment"] = extra

    closing = bundle.get("closing") if isinstance(bundle.get("closing"), dict) else {}
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

    # Rövid munkajavaslat lezárásra — csak ha teljesen üres, van fő gondolat
    if not _s(outline["closing"]["final_insight"]) and idea:
        outline["closing"]["final_insight"] = (
            f"A hallgató a fő gondolat fényében állhat meg: {idea}"
        )
        if _s(outline["grace_enabled_response"]):
            outline["closing"]["invitation"] = _s(outline["grace_enabled_response"])
        provisional.append("closing")

    if not _s(outline["opening_direction"]) and (idea or question):
        if question:
            outline["opening_direction"] = f"Hallgatói nyitás: {question}"
        else:
            outline["opening_direction"] = (
                f"A prédikáció a fő gondolat felől nyílik: {idea}"
            )
        provisional.append("opening_direction")

    lection = bundle.get("lection") if isinstance(bundle.get("lection"), dict) else {}
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

    outline["prayer_before"] = (
        dict(bundle["prayer_before"])
        if isinstance(bundle.get("prayer_before"), dict)
        else _prayer_side_retained({})
    )
    outline["prayer_after"] = (
        dict(bundle["prayer_after"])
        if isinstance(bundle.get("prayer_after"), dict)
        else _prayer_side_retained({})
    )

    if _s(bundle.get("outline_manual_notes")):
        outline["manual_notes"] = _s(bundle.get("outline_manual_notes"))

    stamp = _now()
    outline["generated_at"] = stamp
    outline["updated_at"] = stamp
    outline["status"] = "draft"
    outline["manually_edited"] = False
    outline["source_sections"] = list(dict.fromkeys(sources))
    outline["provisional_sections"] = list(dict.fromkeys(provisional))
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
        "source_sections",
        "provisional_sections",
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


def outline_missing_parts(outline: Any) -> list[str]:
    """Finomítható részek — nem blokkoló hibák, opcionális üresek kimaradnak."""
    return outline_refinable_parts(outline)


def outline_refinable_parts(outline: Any) -> list[str]:
    """Rövid, pasztorális finomítási tippek — modulhiány nélkül."""
    safe = normalize_sermon_outline(outline)
    tips: list[str] = []
    provisional = set(safe.get("provisional_sections") or [])
    if not _s(safe.get("main_idea")):
        tips.append("a fő gondolat")
    if "sermon_movements" in provisional or not (
        safe.get("movements") if isinstance(safe.get("movements"), list) else []
    ):
        if "sermon_movements" in provisional:
            tips.append("a prédikációs mozgások (jelenleg munkajavaslat)")
        elif not (safe.get("movements") or []):
            tips.append("a prédikációs mozgások")
    closing = safe.get("closing") if isinstance(safe.get("closing"), dict) else {}
    if "closing" in provisional or not _s(closing.get("final_insight")):
        if "closing" in provisional:
            tips.append("a lezárás (jelenleg munkajavaslat)")
        elif not _s(closing.get("final_insight")):
            tips.append("a lezárás")
    if "opening_direction" in provisional and _s(safe.get("opening_direction")):
        tips.append("a bevezetési irány (jelenleg munkajavaslat)")
    return tips


def outline_has_provisional_bridges(outline: Any) -> bool:
    safe = normalize_sermon_outline(outline)
    return bool(safe.get("provisional_sections"))


def outline_refinable_summary(outline: Any) -> str:
    tips = outline_refinable_parts(outline)
    if not tips:
        return ""
    return (
        "A vázlat elkészült a rendelkezésre álló anyagból. "
        f"Még finomítható: {', '.join(tips)}."
    )


def editable_outline_snapshot(outline: Any) -> dict[str, Any]:
    """Összehasonlítható kivágat — időbélyeg / státusz nélkül."""
    safe = normalize_sermon_outline(outline)
    return {
        "main_idea": _s(safe.get("main_idea")),
        "main_idea_summary": _s(safe.get("main_idea_summary")),
        "opening_direction": _s(safe.get("opening_direction")),
        "manual_notes": _s(safe.get("manual_notes")),
        "closing": {
            k: _s((safe.get("closing") or {}).get(k))
            for k in (
                "final_insight",
                "gospel_assurance",
                "invitation",
                "image_or_line",
                "open_question",
                "tone_label",
            )
        },
        "movements": [
            {
                "id": _s(m.get("id")),
                "title": _s(m.get("title")),
                "role_label": _s(m.get("role_label")),
                "textual_basis": _s(m.get("textual_basis")),
                "core_content": _s(m.get("core_content")),
                "listener_discovery": _s(m.get("listener_discovery")),
                "transition": _s(m.get("transition")),
                "images": [_s(x) for x in (m.get("images") or []) if _s(x)],
                "illustrations": [
                    _s(x) for x in (m.get("illustrations") or []) if _s(x)
                ],
                "applications": [
                    _s(x) for x in (m.get("applications") or []) if _s(x)
                ],
            }
            for m in (safe.get("movements") or [])
            if isinstance(m, dict)
        ],
    }


def _md_line(label: str, value: Any) -> str | None:
    text = _s(value)
    if not text:
        return None
    return f"**{label}:** {text}"


def _prayer_has_compact_content(side: Mapping[str, Any] | None) -> bool:
    block = side if isinstance(side, dict) else {}
    if _s(block.get("selected_opening")) or _s(block.get("closing_direction")):
        return True
    lines = block.get("selected_lines")
    return isinstance(lines, list) and any(_s(x) for x in lines)


def _ensure_outline_reader_styles() -> None:
    import streamlit as st

    st.markdown(
        """
<style>
.sw-outline-card {
  border: 1px solid rgba(49, 51, 63, 0.16);
  border-radius: 0.5rem;
  padding: 0.85rem 1rem 0.35rem 1rem;
  margin: 0.35rem 0 0.75rem 0;
  background: rgba(250, 250, 252, 0.65);
}
.sw-outline-card h4 {
  margin: 0.15rem 0 0.55rem 0;
  font-size: 1.02rem;
}
.sw-outline-sep {
  border: 0;
  border-top: 1px solid rgba(49, 51, 63, 0.12);
  margin: 0.65rem 0;
}
.sw-outline-mv {
  border: 1px solid rgba(49, 51, 63, 0.12);
  border-radius: 0.4rem;
  padding: 0.55rem 0.75rem;
  margin: 0.4rem 0;
  background: #fff;
}
.sw-outline-mv h5 {
  margin: 0 0 0.35rem 0;
  font-size: 0.98rem;
}
.sw-outline-missing {
  border-left: 3px solid rgba(49, 51, 63, 0.35);
  padding: 0.35rem 0.65rem;
  margin: 0.5rem 0 0.75rem 0;
  background: rgba(49, 51, 63, 0.04);
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_compact_sermon_outline(outline: Any) -> None:
    """Olvasó / dokumentumnézet — nem űrlap. Streamlit UI."""
    import html as html_lib

    import streamlit as st

    safe = normalize_sermon_outline(outline)
    if not outline_has_content(safe):
        st.info("Még nincs összeállított vázlat.")
        return

    _ensure_outline_reader_styles()
    if outline_has_provisional_bridges(safe):
        st.caption(PROVISIONAL_NOTICE)
    refinable = outline_refinable_summary(safe)
    if refinable:
        st.markdown(
            f'<div class="sw-outline-missing"><strong>Még finomítható részek</strong>'
            f"<p>{html_lib.escape(refinable)}</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown('<div class="sw-outline-card">', unsafe_allow_html=True)

    basics: list[str] = []
    for label, key in (
        ("Textus", "passage_reference"),
        ("Lekció", "lection_reference"),
        ("Fordítás", "bible_translation"),
    ):
        line = _md_line(label, safe.get(key))
        if line:
            basics.append(line)
    if basics:
        st.markdown("#### Alapadatok")
        st.markdown("\n\n".join(basics))
        st.markdown('<hr class="sw-outline-sep"/>', unsafe_allow_html=True)

    core_bits: list[str] = []
    if _s(safe.get("main_idea")):
        core_bits.append(f"**Fő gondolat**\n\n{_s(safe.get('main_idea'))}")
        if _s(safe.get("main_idea_summary")):
            core_bits.append(_s(safe.get("main_idea_summary")))
    if _s(safe.get("listener_question")):
        core_bits.append(
            f"**Hallgatói kérdés**\n\n{_s(safe.get('listener_question'))}"
        )
    if _s(safe.get("central_tension")):
        core_bits.append(
            f"**Központi feszültség**\n\n{_s(safe.get('central_tension'))}"
        )
    if _s(safe.get("listener_resistance")):
        core_bits.append(
            f"**Hallgatói ellenállás**\n\n{_s(safe.get('listener_resistance'))}"
        )
    if core_bits:
        st.markdown("#### Az igehirdetés magja")
        for bit in core_bits:
            st.markdown(bit)
        st.markdown('<hr class="sw-outline-sep"/>', unsafe_allow_html=True)

    gospel_lines: list[str] = []
    for label, key in (
        ("Isten kegyelmi cselekvése", "divine_gracious_action"),
        ("Krisztus-kapcsolat", "christ_connection"),
        ("Evangéliumi feloldás", "gospel_resolution"),
        ("Kegyelemből fakadó válasz", "grace_enabled_response"),
    ):
        line = _md_line(label, safe.get(key))
        if line:
            gospel_lines.append(line)
    ctype = _s(safe.get("christ_connection_type_label"))
    if ctype and ctype not in {"—", "-", "direct", "indirect", "typological"}:
        insert_at = 1 if gospel_lines else 0
        gospel_lines.insert(insert_at, f"**Kapcsolat:** {ctype}")
    if gospel_lines:
        st.markdown("#### Evangéliumi fordulat")
        st.markdown("\n\n".join(gospel_lines))
        st.markdown('<hr class="sw-outline-sep"/>', unsafe_allow_html=True)

    if _s(safe.get("opening_direction")):
        st.markdown("#### Bevezetési irány")
        st.markdown(_s(safe.get("opening_direction")))
        st.markdown('<hr class="sw-outline-sep"/>', unsafe_allow_html=True)

    movements = safe.get("movements") if isinstance(safe.get("movements"), list) else []
    if movements:
        st.markdown("#### A prédikáció mozgásai")
        for idx, mv in enumerate(movements, start=1):
            if not isinstance(mv, dict):
                continue
            title = _s(mv.get("title")) or f"{idx}. mozgás"
            role = _s(mv.get("role_label"))
            role_raw = _s(mv.get("role"))
            if role and role == role_raw and "_" in role:
                role = ""
            header = f"{idx}. {title}"
            if role:
                header = f"{header} — {role}"
            body: list[str] = [
                f'<div class="sw-outline-mv"><h5>{html_lib.escape(header)}</h5>'
            ]
            for label, key in (
                ("Textusbeli alap", "textual_basis"),
                ("Mit bont ki?", "core_content"),
                ("Mit ismer fel a hallgató?", "listener_discovery"),
                ("Átmenet", "transition"),
            ):
                val = _s(mv.get(key))
                if val:
                    body.append(
                        f"<div><strong>{html_lib.escape(label)}:</strong> "
                        f"{html_lib.escape(val)}</div>"
                    )
            images = [_s(x) for x in (mv.get("images") or []) if _s(x)]
            illustrations = [
                _s(x) for x in (mv.get("illustrations") or []) if _s(x)
            ]
            applications = [
                _s(x) for x in (mv.get("applications") or []) if _s(x)
            ]
            media = images + illustrations
            if media:
                body.append(
                    "<div><strong>Kép vagy illusztráció:</strong> "
                    f"{html_lib.escape('; '.join(media))}</div>"
                )
            if applications:
                body.append(
                    "<div><strong>Alkalmazási irány:</strong> "
                    f"{html_lib.escape('; '.join(applications))}</div>"
                )
            body.append("</div>")
            st.markdown("\n".join(body), unsafe_allow_html=True)
        st.markdown('<hr class="sw-outline-sep"/>', unsafe_allow_html=True)

    closing = safe.get("closing") if isinstance(safe.get("closing"), dict) else {}
    closing_lines: list[str] = []
    for label, key in (
        ("Végső felismerés", "final_insight"),
        ("Evangéliumi bizonyosság", "gospel_assurance"),
        ("Meghívás", "invitation"),
        ("Záró kép vagy mondatmag", "image_or_line"),
        ("Nyitott kérdés", "open_question"),
    ):
        line = _md_line(label, closing.get(key))
        if line:
            closing_lines.append(line)
    if closing_lines:
        st.markdown("#### Lezárás")
        st.markdown("\n\n".join(closing_lines))
        st.markdown('<hr class="sw-outline-sep"/>', unsafe_allow_html=True)

    lection = safe.get("lection") if isinstance(safe.get("lection"), dict) else {}
    lec_ref = _s(lection.get("reference")) or _s(safe.get("lection_reference"))
    lec_role = _s(lection.get("function")) or _s(lection.get("rationale"))
    if lec_ref or lec_role:
        st.markdown("#### Lekció")
        lec_bits: list[str] = []
        if lec_ref:
            lec_bits.append(f"**Lekció:** {lec_ref}")
        if lec_role:
            lec_bits.append(f"**Szerepe:** {lec_role}")
        st.markdown("\n\n".join(lec_bits))
        st.markdown('<hr class="sw-outline-sep"/>', unsafe_allow_html=True)

    before = (
        safe.get("prayer_before")
        if isinstance(safe.get("prayer_before"), dict)
        else {}
    )
    after = (
        safe.get("prayer_after") if isinstance(safe.get("prayer_after"), dict) else {}
    )
    if _prayer_has_compact_content(before) or _prayer_has_compact_content(after):
        st.markdown("#### Imádsági előkészítés")

        def _render_prayer_side(label: str, side: Mapping[str, Any]) -> None:
            if not _prayer_has_compact_content(side):
                return
            with st.expander(label, expanded=False):
                opening = _s(side.get("selected_opening"))
                if opening:
                    st.markdown(f"**Nyitó mondat**\n\n{opening}")
                lines = [
                    _s(x)
                    for x in (side.get("selected_lines") or [])
                    if _s(x)
                ][:5]
                if lines:
                    st.markdown("**Fő gondolatok**")
                    for item in lines:
                        st.markdown(f"- {item}")
                closing_dir = _s(side.get("closing_direction"))
                if closing_dir:
                    st.markdown(f"**Záró mondat**\n\n{closing_dir}")

        _render_prayer_side("Igehirdetés előtti imádság", before)
        _render_prayer_side("Igehirdetés utáni imádság", after)

    notes = _s(safe.get("manual_notes"))
    if notes:
        st.markdown("#### Saját megjegyzéseim")
        st.markdown(notes)

    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("Következő lépés: a vázlat homiletikai ellenőrzése")


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


_SYNTH_SYSTEM = """\
Te a TEXTUS homiletikai vázlat-összegző asszisztense vagy.
Egyetlen feladattal: a megadott meglévő anyagból egészítsd ki a hiányzó
szerkezeti kapcsolatokat a végső igehirdetési vázlatban.
TILOS: új bibliai / történeti / teológiai adat kitalálása; teljes kézirat;
az üres modulok külön háttérben való „pótlása"; nyers MI-alternatívák
felhasználása. Csak a megadott anyagból dolgozz.
Ha van sermon_movements a forrásban, TARTSD meg őket — ne cseréld le.
Ha nincs mozgás, adj 3–5 egyszerű prédikációs mozgást.
Válaszod KIZÁRÓLAG érvényes JSON legyen.\
"""


def _synthesize_outline_gaps(
    outline: dict[str, Any],
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    """Egyetlen összegző MI-hívás a hiányzó vázlatelemekhez — forrásmezők érintetlenek."""
    if generate_fn is None:
        return outline, []
    needs_movements = not (outline.get("movements") or [])
    needs_opening = not _s(outline.get("opening_direction"))
    closing = outline.get("closing") if isinstance(outline.get("closing"), dict) else {}
    needs_closing = not _s(closing.get("final_insight"))
    needs_idea = not _s(outline.get("main_idea"))
    # Ha már van heurisztikus provisional, az MI finomíthatja — de csak gap-ekre
    if not (needs_movements or needs_opening or needs_closing or needs_idea):
        # Van provisional heurisztika → engedjük az MI-nek finomítani a provisional részeket
        provisional = set(outline.get("provisional_sections") or [])
        if not provisional:
            return outline, []

    import json

    warnings: list[str] = []
    ctx = {k: v for k, v in bundle.items() if not str(k).startswith("_")}
    # Ne küldjük újra a teljes diagnosztikát / nyers javaslatlistákat
    prompt = (
        "Egészítsd ki a vázlat hiányzó szerkezeti elemeit a forrásanyag alapján.\n"
        "Csak a hiányzó / munkajavaslat mezőket töltsd; a meglévő kanonikus "
        "tartalmat ne cseréld le.\n\n"
        f"FORRÁS (csak nem üres mezők):\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"JELENLEGI VÁZLAT:\n{json.dumps(outline, ensure_ascii=False)}\n\n"
        "Kimenet JSON kulcsok (opcionálisak, csak ha indokolt):\n"
        '{"main_idea":"","opening_direction":"","movements":[{"id":"","title":"",'
        '"role":"","textual_basis":"","core_content":"","listener_discovery":"",'
        '"transition":""}],"closing":{"final_insight":"","gospel_assurance":"",'
        '"invitation":""},"provisional_sections":["opening_direction","sermon_movements","closing"]}'
    )
    try:
        raw = generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_OUTLINE,
            use_cache=False,
            system_bundle=_SYNTH_SYSTEM,
            temperature=DEFAULT_TEMPERATURE,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Összegző kiegészítés kihagyva: {exc}")
        return outline, warnings

    if _is_api_error_text(raw or ""):
        warnings.append("Az összegző kiegészítés nem sikerült; a helyi összeállítás megmaradt.")
        return outline, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen összegző válasz; a helyi összeállítás megmaradt.")
        return outline, warnings

    merged = dict(outline)
    provisional = list(merged.get("provisional_sections") or [])

    # Fő gondolat: csak ha üres volt
    if not _s(merged.get("main_idea")) and _s(obj.get("main_idea")):
        merged["main_idea"] = _as_text(obj.get("main_idea"))
        provisional.append("main_idea")

    if (not _s(merged.get("opening_direction")) or "opening_direction" in provisional) and _s(
        obj.get("opening_direction")
    ):
        merged["opening_direction"] = _as_text(obj.get("opening_direction"))
        if "opening_direction" not in provisional:
            provisional.append("opening_direction")

    # Mozgások: csak ha nem volt M6 forrás, vagy üres / provisional
    had_m6 = "sermon_movements" in (bundle.get("source_keys") or [])
    raw_mvs = obj.get("movements")
    if (
        isinstance(raw_mvs, list)
        and raw_mvs
        and (not had_m6)
        and (
            not merged.get("movements")
            or "sermon_movements" in provisional
        )
    ):
        new_mvs: list[dict[str, Any]] = []
        for i, mv in enumerate(raw_mvs[:5], start=1):
            if not isinstance(mv, dict):
                continue
            role = _s(mv.get("role"))
            item = empty_outline_movement()
            item.update(
                {
                    "id": _s(mv.get("id")) or f"prov_mv_{i}",
                    "title": _s(mv.get("title")) or f"{i}. mozgás",
                    "role": role,
                    "role_label": movement_role_label(role) if role else "",
                    "textual_basis": _s(mv.get("textual_basis")),
                    "core_content": _s(mv.get("core_content")),
                    "listener_discovery": _s(mv.get("listener_discovery")),
                    "transition": _s(mv.get("transition")),
                    "images": [],
                    "illustrations": [],
                    "applications": [],
                }
            )
            if _s(item["core_content"]) or _s(item["title"]):
                new_mvs.append(item)
        if new_mvs:
            merged["movements"] = new_mvs
            if "sermon_movements" not in provisional:
                provisional.append("sermon_movements")

    obj_closing = obj.get("closing") if isinstance(obj.get("closing"), dict) else {}
    if obj_closing:
        cur_closing = dict(merged.get("closing") or {})
        for key in ("final_insight", "gospel_assurance", "invitation"):
            if (not _s(cur_closing.get(key)) or "closing" in provisional) and _s(
                obj_closing.get(key)
            ):
                cur_closing[key] = _as_text(obj_closing.get(key))
                if "closing" not in provisional:
                    provisional.append("closing")
        merged["closing"] = cur_closing

    for extra in obj.get("provisional_sections") or []:
        label = _s(extra)
        if label and label not in provisional:
            provisional.append(label)

    merged["provisional_sections"] = list(dict.fromkeys(provisional))
    return normalize_sermon_outline(merged), warnings


def assemble_sermon_outline(
    session_state: MutableMapping[str, Any],
    *,
    generate_fn: GenerateFn | None = None,
    force_overwrite: bool = False,
    polish: bool = False,
    synthesize: bool = True,
) -> OutlineAssemblyResult:
    """Összeállítja a vázlatot a rendelkezésre álló anyagból.

    Nem módosítja a forrás műhelymezőket. Részleges munkafolyamat esetén
    is működik — egyetlen összegző MI-hívással kiegészítheti a hiányzó
    szerkezeti kapcsolatokat a vázlatban.
    """
    ensure_sermon_workshop_state(session_state)
    sw = session_state[SERMON_WORKSHOP_KEY]
    readiness = assess_outline_readiness(session_state, sermon_workshop=sw)
    if not readiness.ok:
        return OutlineAssemblyResult(
            outline=normalize_sermon_outline(sw.get("sermon_outline")),
            ok=False,
            error_message=readiness.message or EMPTY_PROJECT_MESSAGE,
        )

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
                "Frissítéshez használd: „Vázlat frissítése a meglévő anyagból”."
            ),
            overwritten_manual_edit=False,
        )

    bundle = collect_outline_context_bundle(session_state, sermon_workshop=sw)
    outline = build_outline_from_workshop(session_state, sermon_workshop=sw)
    warnings: list[str] = []

    if synthesize:
        outline, synth_warnings = _synthesize_outline_gaps(
            outline, bundle, generate_fn=generate_fn
        )
        warnings.extend(synth_warnings)

    if polish:
        outline, polish_warnings = _optional_polish(outline, generate_fn=generate_fn)
        warnings.extend(polish_warnings)

    if outline_has_provisional_bridges(outline):
        notice = PROVISIONAL_NOTICE
        if notice not in warnings:
            warnings.append(notice)

    return OutlineAssemblyResult(
        outline=outline,
        ok=True,
        warnings=warnings,
        overwritten_manual_edit=bool(manually_edited and force_overwrite),
    )


__all__ = [
    "TAB_OUTLINE",
    "MISSING_PART",
    "PROVISIONAL_NOTICE",
    "EMPTY_PROJECT_MESSAGE",
    "GenerateFn",
    "OutlineAssemblyResult",
    "OutlineReadiness",
    "assess_outline_readiness",
    "assemble_sermon_outline",
    "build_outline_from_workshop",
    "collect_outline_context_bundle",
    "editable_outline_snapshot",
    "empty_sermon_outline",
    "outline_has_content",
    "outline_has_provisional_bridges",
    "outline_missing_parts",
    "outline_part_display",
    "outline_refinable_parts",
    "outline_refinable_summary",
    "render_compact_sermon_outline",
]
