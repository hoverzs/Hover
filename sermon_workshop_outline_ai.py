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
from sermon_workshop_m7_simple_ai import illustration_card_to_legacy
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

# Előnézetben és generált szövegben tiltott sablon / technikai helykitöltők.
OUTLINE_PLACEHOLDER_BANLIST: tuple[str, ...] = (
    "Ez a rész még nincs kidolgozva.",
    "Nem állapítható meg felelősen",
    "Nincs elegendő adat",
    "Nincs elég adat",
    "A textus magja elmélyül.",
    "A hallgató a textus világába lép.",
    "A fő gondolat megérkezik a hallgatóhoz.",
    "A textus a fő gondolatot a saját hangján bontja ki.",
    "A hallgató a kegyelem felől válaszolhat.",
    "Nyitás – Megnyitás",
    "Nyitás — Megnyitás",
    "Kibontás – Elmélyítés",
    "Kibontás — Elmélyítés",
    "Megérkezés – Megérkezés",
    "Megérkezés — Megérkezés",
)
_GENERIC_MOVEMENT_TITLES = {
    "nyitás",
    "kibontás",
    "megérkezés",
    "megnyitás",
    "elmélyítés",
    "1. mozgás",
    "2. mozgás",
    "3. mozgás",
    "4. mozgás",
    "5. mozgás",
}
_UNCERTAIN_CHRIST_LABELS = {
    "nem állapítható meg felelősen",
    "none_or_uncertain",
    "—",
    "-",
}

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


def _normalize_cmp(text: str) -> str:
    return " ".join(_s(text).casefold().split())


def is_banned_outline_placeholder(text: Any) -> bool:
    """Igaz, ha a szöveg tiltott sablon / technikai helykitöltő."""
    raw = _s(text)
    if not raw:
        return False
    norm = _normalize_cmp(raw)
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        b = _normalize_cmp(banned)
        if not b:
            continue
        if norm == b or b in norm:
            return True
    return False


def _clean_source_text(text: Any) -> str:
    """Forrásmező tisztítás: markdown fejléc, mezőnév, csonka vég, ismétlés."""
    import re

    raw = _s(text)
    if not raw:
        return ""
    # Markdown / technikai jelek
    raw = re.sub(r"(?m)^#{1,6}\s*", "", raw)
    raw = raw.replace("```", "")
    # Nyers mezőnevek / JSON-szerű kulcsok a szöveg elején
    raw = re.sub(
        r"(?i)^\s*(main_idea|core_content|listener_discovery|textual_basis|"
        r"gospel_resolution|christ_connection|opening_direction)\s*[:=]\s*",
        "",
        raw,
    )
    # Többszörös whitespace
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    # Félbehagyott / csonka vég („az útmu…”, „…”)
    if raw.endswith("…") or raw.endswith("..."):
        stripped = raw.rstrip("….").rstrip()
        # Nincs lezárt mondat → csonka AI-válasz, ne mentsük „kész” szövegként
        if not re.search(r"[.!?]", stripped):
            return ""
        parts = re.split(r"(?<=[.!?])\s+", raw)
        if len(parts) >= 2 and len(parts[-1]) < 18:
            raw = " ".join(parts[:-1]).rstrip()
        else:
            raw = stripped
    # Azonos mondat kétszer egymás után
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]
    deduped: list[str] = []
    for sent in sentences:
        if deduped and _normalize_cmp(sent) == _normalize_cmp(deduped[-1]):
            continue
        deduped.append(sent)
    raw = " ".join(deduped) if deduped else raw
    if is_banned_outline_placeholder(raw):
        return ""
    return raw.strip()


def _usable_text(value: Any) -> str:
    """Üres / tiltott / technikai szöveg kiszűrése."""
    return _clean_source_text(value)


def _title_from_text(text: str, *, fallback: str, max_len: int = 48) -> str:
    cleaned = _usable_text(text)
    if not cleaned:
        return fallback
    words = cleaned.split()
    title = " ".join(words[:6]).rstrip(".,;:")
    if len(title) > max_len:
        title = title[: max_len - 1].rstrip() + "…"
    low = _normalize_cmp(title)
    if low in _GENERIC_MOVEMENT_TITLES or is_banned_outline_placeholder(title):
        return fallback
    return title or fallback


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
        return _usable_text(item.get("image"))
    if kind == "illustration":
        return _usable_text(item.get("idea"))
    return _usable_text(item.get("application"))


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
    """Rövidítés gondolati egység határán — ne vágjon szó/mondat közepén."""
    import re

    raw = _clean_source_text(text)
    if not raw or len(raw) <= limit:
        return raw
    window = raw[:limit].rstrip()
    # Preferált: utolsó teljes mondat a ablakban
    sentences = re.split(r"(?<=[.!?])\s+", window)
    if len(sentences) >= 2:
        candidate = " ".join(sentences[:-1]).strip()
        if len(candidate) >= max(40, limit // 3):
            return candidate
    # Másodlagos: utolsó szóhatár
    cut = window.rsplit(" ", 1)[0].rstrip(".,;:")
    if len(cut) >= max(24, limit // 4):
        return cut
    return window.rstrip(".,;:")

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


def collect_available_sermon_material(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Központi anyaggyűjtés: minden nem üres, elmentett tartalom státusztól függetlenül.

    Alias a meglévő `collect_outline_context_bundle` fölött — a vázlatgenerálás
    és a diagnosztika ugyanezt a forrást használja.
    """
    return collect_outline_context_bundle(
        session_state, sermon_workshop=sermon_workshop
    )


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
    # Minimális forrás: saját szempont / fókusz is elég a szintézis magjához
    focus = _s(bundle.get("user_focus"))
    if focus:
        return focus
    return ""


def _heuristic_provisional_movements(
    *,
    main_idea: str,
    insights: list[str],
    exegesis: str,
    christ: Mapping[str, Any] | None,
    listener_question: str = "",
    passage_reference: str = "",
) -> list[dict[str, Any]]:
    """3 textusspecifikus mozgás — csak ha nincs M6; sablon címek nélkül."""
    idea = _usable_text(main_idea) or (
        _usable_text(insights[0]) if insights else ""
    )
    if not idea:
        return []
    christ = christ if isinstance(christ, dict) else {}
    grace = _usable_text(christ.get("divine_gracious_action")) or _usable_text(
        christ.get("grace_enabled_response")
    ) or _usable_text(christ.get("christ_connection"))
    clean_insights = [_usable_text(x) for x in insights if _usable_text(x)]
    exe = _truncate(exegesis, 220)

    # Bevezetés: helyzet / kérdés — ne ismételje a fő gondolatot.
    q = _usable_text(listener_question)
    first_core = q or (
        clean_insights[0]
        if clean_insights and _normalize_cmp(clean_insights[0]) != _normalize_cmp(idea)
        else ""
    )
    if not first_core:
        first_core = (
            "A hallgató abból a feszültségből indul, amelyet a textus "
            "saját világában megszólít."
        )
    first_discovery = (
        "A textus megnevezi a helyzetet, mielőtt választ adna."
        if q
        else "A hallgató felismeri: a textus az ő helyzetéről beszél."
    )

    second_core = ""
    if len(clean_insights) > 1:
        second_core = clean_insights[1]
    elif exe:
        second_core = exe
    elif len(clean_insights) == 1 and _normalize_cmp(clean_insights[0]) != _normalize_cmp(
        first_core
    ):
        second_core = clean_insights[0]
    if not second_core or _normalize_cmp(second_core) == _normalize_cmp(first_core):
        second_core = idea
    second_discovery = "A textus teológiai magja kibontakozik a hallgató előtt."

    third_core = grace
    if not third_core and len(clean_insights) > 2:
        third_core = clean_insights[2]
    if not third_core:
        third_core = (
            "Isten megtartó kegyelme hív válaszra — nem csupán emberi erőfeszítés."
        )
    third_discovery = "A hallgató kegyelmi válaszra talál, nem csupán kötelességre."

    ref = _usable_text(passage_reference)
    specs = [
        (
            _title_from_text(first_core, fallback="A helyzet megnevezése"),
            "opening",
            first_discovery,
            first_core,
            ref,
        ),
        (
            _title_from_text(second_core, fallback="A textus magja"),
            "deepening",
            second_discovery,
            second_core,
            ref,
        ),
        (
            _title_from_text(third_core, fallback="Kegyelmi megérkezés"),
            "arrival",
            third_discovery,
            third_core,
            ref,
        ),
    ]
    out: list[dict[str, Any]] = []
    for i, (title, role, discovery, core, basis) in enumerate(specs, start=1):
        core_u = _usable_text(core)
        if not core_u:
            continue
        item = empty_outline_movement()
        item.update(
            {
                "id": f"prov_mv_{i}",
                "title": title,
                "role": role,
                "role_label": movement_role_label(role) if role else title,
                "textual_basis": basis,
                "core_content": core_u,
                "listener_discovery": _usable_text(discovery),
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
    outline["listener_question"] = _usable_text(lt.get("listener_question"))
    outline["central_tension"] = _usable_text(lt.get("sermon_tension"))
    outline["listener_resistance"] = _usable_text(lt.get("listener_resistance"))

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
    outline["divine_gracious_action"] = _usable_text(
        arc.get("divine_gracious_action")
    ) or _usable_text(hc.get("divine_action"))
    outline["christ_connection"] = _usable_text(arc.get("christ_connection"))
    ctype = _s(arc.get("christ_connection_type"))
    type_label = christ_connection_type_label(ctype) if ctype else ""
    if _normalize_cmp(type_label) in _UNCERTAIN_CHRIST_LABELS or not ctype:
        outline["christ_connection_type_label"] = ""
    elif _normalize_cmp(type_label) in {"direct", "indirect", "typological"}:
        outline["christ_connection_type_label"] = ""
    else:
        outline["christ_connection_type_label"] = type_label
    outline["gospel_resolution"] = _usable_text(lt.get("promised_resolution"))
    outline["grace_enabled_response"] = _usable_text(
        arc.get("grace_enabled_response")
    ) or _usable_text(hc.get("grace_response"))

    path = bundle.get("sermon_path") if isinstance(bundle.get("sermon_path"), dict) else {}
    start = _usable_text(path.get("starting_point"))
    question = outline["listener_question"]
    if start and question:
        outline["opening_direction"] = (
            f"{start.rstrip('.')} — és felmerül a kérdés: {question}"
        )
    elif start:
        outline["opening_direction"] = start
    elif question:
        outline["opening_direction"] = question
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
                "textual_anchor": _s(mv.get("textual_basis")),
                "core_content": _s(mv.get("core_content")),
                "listener_discovery": _s(mv.get("listener_discovery")),
                "transition": _s(mv.get("transition_to_next")),
                "development": [],
                "images": [],
                "illustrations": [],
                "applications": [],
            }
        )
        # Fejlesztési bekezdések a meglévő mezőkből — technikai címke nélkül
        item["development"] = _movement_development_paragraphs(item)
        movements_out.append(item)

    images = list(bundle.get("selected_images") or [])
    # Csak megtartott illusztrációk — ne az összes generált alternatíva
    retained_cards = sw.get("retained_illustration_cards")
    if isinstance(retained_cards, list) and retained_cards:
        illustrations = [
            illustration_card_to_legacy(c)
            for c in retained_cards
            if isinstance(c, dict)
        ]
    else:
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
            listener_question=question,
            passage_reference=_s(outline.get("passage_reference")),
        )
        if movements_out:
            provisional.append("sermon_movements")
            if not used_m6:
                # Ne jelöljük M6 forrásként
                pass

    outline["movements"] = movements_out
    outline["extra_enrichment"] = extra

    act_conn = sw.get("actualization_connections")
    outline["actualization_connections"] = []
    if isinstance(act_conn, list):
        for item in act_conn[:5]:
            if not isinstance(item, dict):
                continue
            title = _s(item.get("title"))
            summary = _s(item.get("event_summary"))
            if not (title or summary):
                continue
            outline["actualization_connections"].append(
                {
                    "title": title,
                    "event_summary": _truncate(summary, 280),
                    "source_name": _s(item.get("source_name")),
                    "published_at": _s(item.get("published_at")),
                    "source_url": _s(item.get("source_url")),
                }
            )
        if outline["actualization_connections"]:
            sources.append("actualization_connections")

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

    # Lezárás: ne ismételje változtatás nélkül a fő gondolatot.
    if not _usable_text(outline["closing"]["final_insight"]) and idea:
        closing_seed = (
            _usable_text(outline.get("grace_enabled_response"))
            or _usable_text(outline.get("gospel_resolution"))
            or _usable_text(outline.get("divine_gracious_action"))
        )
        if closing_seed and _normalize_cmp(closing_seed) != _normalize_cmp(idea):
            outline["closing"]["final_insight"] = closing_seed
        else:
            outline["closing"]["final_insight"] = (
                "A hallgató Isten megtartó szeretetében állhat meg — "
                "a megnyitott kérdésre kegyelmi válasz érkezik."
            )
        if not _usable_text(outline["closing"].get("invitation")) and _usable_text(
            outline.get("grace_enabled_response")
        ):
            outline["closing"]["invitation"] = _usable_text(
                outline.get("grace_enabled_response")
            )
        provisional.append("closing")

    if not _usable_text(outline["opening_direction"]) and (idea or question):
        if question and start:
            outline["opening_direction"] = (
                f"{start.rstrip('.')} — és felmerül a kérdés: {question}"
            )
        elif question:
            outline["opening_direction"] = question
        elif start:
            outline["opening_direction"] = start
        else:
            outline["opening_direction"] = (
                "A bevezetés hallgatói helyzetet és feszültséget teremt, "
                "mielőtt a textus központi állítását kibontanánk."
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
    outline["needs_rebuild"] = False
    outline["source_sections"] = list(dict.fromkeys(sources))
    outline["provisional_sections"] = list(dict.fromkeys(provisional))
    # Forrás-ujjlenyomat + teljesség — diagnosztikai frissességhez.
    import hashlib
    import json as _json

    fp_payload = {
        "keys": list(dict.fromkeys(sources)),
        "main_idea": _s(outline.get("main_idea")),
        "movements": len(outline.get("movements") or []),
        "closing": _s((outline.get("closing") or {}).get("final_insight")),
    }
    outline["source_fingerprint"] = hashlib.sha1(
        _json.dumps(fp_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    n_src = len(sources)
    if n_src >= 8 and not provisional:
        outline["source_completeness"] = "full"
    elif n_src >= 3:
        outline["source_completeness"] = "partial"
    else:
        outline["source_completeness"] = "minimal"
    # Bevezetés / megérkezés szinkron a főnézet sémájához
    outline["introduction"] = {
        "development": _usable_text(outline.get("opening_direction")),
        "transition": "",
    }
    cl = outline.get("closing") if isinstance(outline.get("closing"), dict) else {}
    outline["conclusion"] = {
        "development": _usable_text(cl.get("final_insight")),
        "final_sentence": _usable_text(cl.get("image_or_line"))
        or _usable_text(cl.get("invitation")),
    }
    for mv in outline.get("movements") or []:
        if isinstance(mv, dict) and not (mv.get("development") or []):
            mv["development"] = _movement_development_paragraphs(mv)
        if isinstance(mv, dict) and not _usable_text(mv.get("textual_anchor")):
            mv["textual_anchor"] = _usable_text(mv.get("textual_basis"))
    outline = normalize_sermon_outline(outline)
    outline["content"] = outline_to_readable_content(outline)
    return normalize_sermon_outline(outline)


def _movement_development_paragraphs(mv: Mapping[str, Any]) -> list[str]:
    """Mozgás kibontása: development lista, vagy legacy mezőkből összerakva."""
    paras: list[str] = []
    seen: set[str] = set()
    anchor_n = _normalize_cmp(
        _usable_text(mv.get("textual_anchor")) or _usable_text(mv.get("textual_basis"))
    )

    def _push(text: Any) -> None:
        cleaned = _usable_text(text)
        if not cleaned:
            return
        n = _normalize_cmp(cleaned)
        if n in seen:
            return
        # Ne ismételjük a vershorgonyt bekezdésként
        if anchor_n and n == anchor_n:
            return
        seen.add(n)
        paras.append(cleaned)

    for item in mv.get("development") or []:
        _push(item)
    if paras:
        for key in ("images", "illustrations"):
            for item in mv.get(key) or []:
                _push(item)
        return paras[:8]

    # Legacy → természetes bekezdések (technikai címkék nélkül)
    # textual_basis kihagyva — a vershorgony külön jelenik meg
    for key in (
        "exegetical_core",
        "theological_claim",
        "core_content",
        "listener_discovery",
        "grace_application",
    ):
        _push(mv.get(key))
    for item in mv.get("applications") or []:
        _push(item)
    for key in ("images", "illustrations"):
        for item in mv.get(key) or []:
            _push(item)
    return paras[:8]


def outline_to_readable_content(outline: Any) -> str:
    """Kanonikus szószéki munkavázlat — tiszta, emberi nyelvű szöveg.

    Főnézet mezői: cím, textus, fókuszmondat, bevezetés, 3–4 mozgás, megérkezés.
    Nincs `##` fejléc, nincs technikai mezőnév, nincs üres adatlap-címke.
    """
    import re

    safe = outline if isinstance(outline, dict) else {}
    blocks: list[str] = []

    def _section(label: str, body: str) -> None:
        text = _usable_text(body)
        if not text:
            return
        blocks.append(f"**{label}**\n\n{text}")

    title = _usable_text(safe.get("sermon_title"))
    if not title:
        suggestions = [
            _usable_text(t)
            for t in (safe.get("title_suggestions") or [])
            if _usable_text(t)
        ]
        title = suggestions[0] if suggestions else ""
    _section("Cím", title)

    passage = _usable_text(safe.get("passage_reference"))
    bt = _usable_text(safe.get("bible_translation"))
    textus = passage
    if passage and bt:
        textus = f"{passage} ({bt})"
    _section("Textus", textus)

    boundary = _usable_text(safe.get("text_boundary_note"))
    if boundary:
        _section("Megjegyzés a textushatárról", boundary)

    focus = _usable_text(safe.get("main_idea"))
    _section("Fókuszmondat", focus)

    intro = safe.get("introduction") if isinstance(safe.get("introduction"), dict) else {}
    opening = (
        _usable_text(intro.get("development"))
        or _usable_text(safe.get("opening_direction"))
    )
    if opening and focus and _normalize_cmp(opening) == _normalize_cmp(focus):
        opening = ""
    intro_parts: list[str] = []
    if opening:
        intro_parts.append(opening)
    transition = _usable_text(intro.get("transition"))
    if transition and _normalize_cmp(transition) != _normalize_cmp(opening):
        intro_parts.append(transition)
    _section("Bevezetés", "\n\n".join(intro_parts))

    movements = safe.get("movements") if isinstance(safe.get("movements"), list) else []
    for idx, mv in enumerate(
        [m for m in movements if isinstance(m, dict)], start=1
    ):
        mv_title = re.sub(
            r"^\s*\d+[.)]\s*", "", _usable_text(mv.get("title"))
        ).strip()
        if not mv_title or _normalize_cmp(mv_title) in _GENERIC_MOVEMENT_TITLES:
            continue
        if is_banned_outline_placeholder(mv_title):
            continue
        paras = _movement_development_paragraphs(mv)
        if not paras:
            continue
        anchor = _usable_text(mv.get("textual_anchor")) or _usable_text(
            mv.get("textual_basis")
        )
        body_parts: list[str] = []
        if anchor:
            body_parts.append(f"*{anchor}*")
        # Preferált forma: A textus állítása + Hallgatói irány (ha 2+ bekezdés)
        claim_labels = ("a textus állítása", "hallgatói irány")
        if len(paras) >= 2 and not any(
            _normalize_cmp(p).startswith(lab) for p in paras for lab in claim_labels
        ):
            body_parts.append(f"**A textus állítása:** {paras[0]}")
            body_parts.append(f"*Hallgatói irány:* {paras[1]}")
            for p in paras[2:]:
                if anchor and _normalize_cmp(p) == _normalize_cmp(anchor):
                    continue
                body_parts.append(p)
        else:
            for p in paras:
                if anchor and _normalize_cmp(p) == _normalize_cmp(anchor):
                    continue
                body_parts.append(p)
        mv_transition = _usable_text(mv.get("transition"))
        if mv_transition and _normalize_cmp(mv_transition) not in {
            _normalize_cmp(p) for p in paras
        }:
            body_parts.append(mv_transition)
        blocks.append(f"**{idx}. {mv_title}**\n\n" + "\n\n".join(body_parts))

    conclusion = (
        safe.get("conclusion") if isinstance(safe.get("conclusion"), dict) else {}
    )
    closing = safe.get("closing") if isinstance(safe.get("closing"), dict) else {}
    arrival = (
        _usable_text(conclusion.get("development"))
        or _usable_text(closing.get("final_insight"))
        or _usable_text(closing.get("gospel_assurance"))
    )
    if arrival and focus and _normalize_cmp(arrival) == _normalize_cmp(focus):
        arrival = (
            _usable_text(closing.get("invitation"))
            or _usable_text(closing.get("gospel_assurance"))
            or ""
        )
    final_line = (
        _usable_text(conclusion.get("final_sentence"))
        or _usable_text(closing.get("image_or_line"))
        or _usable_text(closing.get("invitation"))
    )
    arrival_parts: list[str] = []
    if arrival:
        arrival_parts.append(arrival)
    if final_line and _normalize_cmp(final_line) != _normalize_cmp(arrival):
        arrival_parts.append(final_line)
    _section("Megérkezés", "\n\n".join(arrival_parts))

    text = "\n\n".join(blocks).strip()
    # Védőháló: sem ##, sem tiltott sablon
    if "##" in text:
        text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        text = text.replace(banned, "")
    return text.strip() + ("\n" if text.strip() else "")


def _structure_has_substantive_text(safe: Mapping[str, Any]) -> bool:
    """Valódi vázlattartalom — nem jegyzet, nem lekció, nem imádság önmagában."""
    text_keys = (
        "main_idea",
        "main_idea_summary",
        "listener_question",
        "central_tension",
        "listener_resistance",
        "divine_gracious_action",
        "christ_connection",
        "gospel_resolution",
        "grace_enabled_response",
        "opening_direction",
    )
    if any(_s(safe.get(k)) for k in text_keys):
        return True
    intro = safe.get("introduction") if isinstance(safe.get("introduction"), dict) else {}
    if _s(intro.get("development")):
        return True
    movements = safe.get("movements") if isinstance(safe.get("movements"), list) else []
    for mv in movements:
        if not isinstance(mv, dict):
            continue
        if _has_any_text(
            mv.get("title"),
            mv.get("textual_basis"),
            mv.get("textual_anchor"),
            mv.get("core_content"),
            mv.get("listener_discovery"),
            mv.get("transition"),
            mv.get("development"),
            mv.get("images"),
            mv.get("illustrations"),
            mv.get("applications"),
        ):
            return True
    conclusion = (
        safe.get("conclusion") if isinstance(safe.get("conclusion"), dict) else {}
    )
    if _has_any_text(conclusion.get("development"), conclusion.get("final_sentence")):
        return True
    closing = safe.get("closing") if isinstance(safe.get("closing"), dict) else {}
    if _has_any_text(
        closing.get("final_insight"),
        closing.get("gospel_assurance"),
        closing.get("invitation"),
        closing.get("image_or_line"),
        closing.get("open_question"),
    ):
        return True
    return False


def outline_has_content(outline: Any) -> bool:
    """Van-e olvasható, valódi vázlattartalom.

    A saját megjegyzés, igehely, lekcióhivatkozás, imádság, textushatár-megjegyzés
    vagy státusz / időbélyeg önmagában NEM számít elkészült vázlatnak.
    """
    if not isinstance(outline, dict) or not outline:
        return False
    safe = normalize_sermon_outline(outline)
    if _structure_has_substantive_text(safe):
        return True
    body = _s(safe.get("content"))
    if not body:
        return False
    stripped = (
        body.replace(MISSING_PART, "")
        .replace("_", "")
        .replace("#", "")
        .replace("*", "")
        .replace("-", "")
        .strip()
    )
    if len(stripped) < 40:
        return False
    # Ne fogadjuk el a csak Textus + textushatár-héjat „kész vázlatként”
    outline_markers = (
        "Fókuszmondat",
        "Bevezetés",
        "Megérkezés",
        "Központi állítás",
        "**1.",
        "1. ",
    )
    if any(m in body for m in outline_markers):
        return True
    # Legacy szabad szöveg (nem csak meta-fejléc)
    meta_only_labels = (
        "**Textus**",
        "**Cím**",
        "**Megjegyzés a textushatárról**",
    )
    residual = body
    for label in meta_only_labels:
        residual = residual.replace(label, "")
    residual_stripped = (
        residual.replace("*", "").replace("#", "").replace("-", "").strip()
    )
    # Ha a maradék lényegében az igehely + határjegyzet, az nem vázlat
    if "textushatár" in residual.casefold() or "következő versben" in residual.casefold():
        without_note = residual
        for frag in (
            "A gondolati ív a következő versben zárul le.",
            "Javasolt textushatár:",
            "Júd 17–21",
            "Júd 17–20",
        ):
            without_note = without_note.replace(frag, "")
        without_note = without_note.strip()
        if len(without_note) < 40:
            return False
    return len(residual_stripped) >= 40


def sync_outline_content(outline: Any, *, force: bool = False) -> dict[str, Any]:
    """Biztosítja, hogy a kanonikus `content` mező a struktúrából frissüljön."""
    safe = normalize_sermon_outline(outline)
    if _structure_has_substantive_text(safe):
        if force or not _s(safe.get("content")):
            safe["content"] = outline_to_readable_content(safe)
    elif not _s(safe.get("content")):
        safe["content"] = ""
    return normalize_sermon_outline(safe)


def repair_outline_integrity(outline: Any) -> tuple[dict[str, Any], bool]:
    """approved/üres → draft+needs_rebuild. Más adatot nem töröl."""
    safe = normalize_sermon_outline(outline)
    has = outline_has_content(safe)
    repaired = False
    if has:
        if safe.get("needs_rebuild"):
            safe["needs_rebuild"] = False
            repaired = True
        if not _s(safe.get("content")):
            safe = sync_outline_content(safe, force=True)
            repaired = True
        return normalize_sermon_outline(safe), repaired

    status = _s(safe.get("status"))
    if status in {"approved", "empty"}:
        safe["status"] = "empty" if status == "empty" else "draft"
        safe["needs_rebuild"] = True
        repaired = True
    elif _s(safe.get("updated_at")) or _s(safe.get("generated_at")) or safe.get(
        "manually_edited"
    ):
        safe["status"] = "draft"
        safe["needs_rebuild"] = True
        repaired = True
    if not _s(safe.get("content")):
        safe["content"] = ""
    return normalize_sermon_outline(safe), repaired


def outline_canonical_text(outline: Any) -> str:
    """A megjelenítéshez / diagnosztikához használt kanonikus szöveg."""
    safe = normalize_sermon_outline(outline)
    if _s(safe.get("content")):
        return _s(safe.get("content"))
    if _structure_has_substantive_text(safe):
        return outline_to_readable_content(safe)
    return ""


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
        "content": _s(safe.get("content")),
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
.sw-outline-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 0.55rem;
  margin: 0.15rem 0 0.85rem 0;
  align-items: center;
}
.sw-outline-badge {
  display: inline-block;
  padding: 0.22rem 0.65rem;
  border-radius: 999px;
  border: 1px solid rgba(90, 122, 168, 0.28);
  background: rgba(90, 122, 168, 0.08);
  color: #1f334d;
  font-size: 0.86rem;
  font-weight: 600;
  line-height: 1.35;
  font-family: "Inter", "Segoe UI", sans-serif;
}
.sw-outline-body {
  font-size: 1.02rem;
  line-height: 1.55;
  color: #2b2116;
}
.sw-outline-body strong {
  display: block;
  margin-top: 1.05rem;
  margin-bottom: 0.35rem;
  font-size: 1.08rem;
  color: #1f334d;
}
.sw-outline-body p {
  margin-bottom: 0.55rem !important;
}
.sw-pulpit-view {
  background: #fbf8f1;
  color: #1a1712;
  padding: 1.6rem 1.8rem 2rem;
  border-radius: 12px;
  border: 1px solid rgba(117, 99, 72, 0.22);
  font-size: 1.22rem;
  line-height: 1.65;
  font-family: "Georgia", "Times New Roman", serif;
}
.sw-pulpit-view strong {
  display: block;
  margin-top: 1.35rem;
  margin-bottom: 0.45rem;
  font-size: 1.28rem;
  font-family: "Georgia", "Times New Roman", serif;
  color: #2b2116;
  letter-spacing: 0.01em;
}
.sw-pulpit-view em {
  color: #5a4a38;
}
/* Egyetlen chevron az outline-szerkesztő expanderben — ne legyen dupla ikon. */
div[data-testid="stExpander"]:has(textarea) summary [data-testid="stIconMaterial"]:not(:last-of-type),
div[data-testid="stExpander"] summary svg + svg {
  display: none !important;
}
div[data-testid="stExpander"] summary {
  list-style: none !important;
}
div[data-testid="stExpander"] summary::-webkit-details-marker {
  display: none !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_outline_meta_badges(outline: Mapping[str, Any]) -> None:
    import html

    import streamlit as st

    safe = outline if isinstance(outline, dict) else {}
    passage = _usable_text(safe.get("passage_reference"))
    bt = _usable_text(safe.get("bible_translation"))
    lec_block = safe.get("lection") if isinstance(safe.get("lection"), dict) else {}
    lec = _usable_text(lec_block.get("reference")) or _usable_text(
        safe.get("lection_reference")
    )
    title = _usable_text(safe.get("sermon_title"))
    badges: list[str] = []
    if passage:
        badges.append(
            f'<span class="sw-outline-badge">Textus: {html.escape(passage)}</span>'
        )
    if bt:
        badges.append(
            f'<span class="sw-outline-badge">Fordítás: {html.escape(bt)}</span>'
        )
    if lec:
        badges.append(
            f'<span class="sw-outline-badge">Lekció: {html.escape(lec)}</span>'
        )
    if title:
        badges.append(
            f'<span class="sw-outline-badge">Cím: {html.escape(title)}</span>'
        )
    if badges:
        st.markdown(
            f'<div class="sw-outline-meta">{"".join(badges)}</div>',
            unsafe_allow_html=True,
        )


def _strip_meta_section_from_content(text: str) -> str:
    """A meta badge-ek mellett a tartalomból kihagyjuk a duplikált Cím/Textus fejet."""
    import re

    raw = _s(text)
    if not raw:
        return ""
    # Régi ## formátum
    raw = re.sub(
        r"(?ms)^##\s*Textus és alapadatok\s*\n.*?(?=^##\s|\Z)",
        "",
        raw,
    ).strip()
    # Új formátum: Cím / Textus a badge-ek mellett felesleges lehet az előnézetben,
    # de a fókuszmondattól kezdve kell — megtartjuk a teljes tartalmat.
    return raw


def render_compact_sermon_outline(outline: Any) -> None:
    """Olvasó / dokumentumnézet — nem űrlap. Streamlit UI.

    A kanonikus `content` mezőt jeleníti meg (ugyanaz, mint az előnézet /
    diagnosztika). Ha a content üres, a struktúrából épít szöveget.
    """
    import streamlit as st

    safe = normalize_sermon_outline(outline)
    if not outline_has_content(safe):
        st.info("Még nincs összeállított vázlat.")
        return

    _ensure_outline_reader_styles()
    tips = [
        _usable_text(t)
        for t in (safe.get("editorial_tips") or [])
        if _usable_text(t)
    ]
    if outline_has_provisional_bridges(safe) and not tips:
        st.caption(PROVISIONAL_NOTICE)

    _render_outline_meta_badges(safe)

    text = _strip_meta_section_from_content(outline_canonical_text(safe))
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        if banned in text:
            text = text.replace(f"_{banned}_", "").replace(banned, "")
    import re

    text = re.sub(r"(?m)^#{1,6}\s*", "", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if text:
        with st.container(border=True):
            st.markdown(text)
    notes = _s(safe.get("manual_notes"))
    if notes:
        st.markdown("#### Saját megjegyzéseim")
        st.markdown(notes)
    if tips:
        with st.expander("További szerkesztési lehetőségek", expanded=False):
            st.caption(
                "Opcionális szerkesztői javaslatok — nem hibák, és nem "
                "akadályozzák a mentést vagy a jóváhagyást."
            )
            for tip in tips[:2]:
                st.markdown(f"- {tip}")
    return


def render_pulpit_outline_view(outline: Any) -> None:
    """Szószéki nézet — nagyobb betű, tiszta háttér, zavaró UI nélkül."""
    import streamlit as st

    safe = normalize_sermon_outline(outline)
    if not outline_has_content(safe):
        st.info("Még nincs összeállított vázlat a szószéki nézethez.")
        return
    _ensure_outline_reader_styles()
    text = outline_canonical_text(safe)
    import re

    text = re.sub(r"(?m)^#{1,6}\s*", "", text).strip()
    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        text = text.replace(banned, "")
    st.markdown(
        f'<div class="sw-pulpit-view">{_markdownish_to_html(text)}</div>',
        unsafe_allow_html=True,
    )


def _markdownish_to_html(text: str) -> str:
    """Egyszerű **félkövér** / *dőlt* → HTML a szószéki nézethez."""
    import html
    import re

    escaped = html.escape(_s(text))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    paras = [p.strip() for p in escaped.split("\n\n") if p.strip()]
    return "".join(f"<p>{p.replace(chr(10), '<br/>')}</p>" for p in paras)


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
Ha nincs mozgás, adj 3–4 textusspecifikus prédikációs mozgást.
TILOS sablon: „Nyitás/Kibontás/Megérkezés", „A textus magja elmélyül",
„A hallgató a textus világába lép", „Nem állapítható meg felelősen",
„Ez a rész még nincs kidolgozva", Markdown ## jelek, mezőnevek, JSON.
A bevezetés NE ismételje szó szerint a fő gondolatot.
A lezárás oldja fel a bevezetés kérdését, ne másolja a fő gondolatot.
Adj felelős Krisztus-/kegyelemívet a textus és a kánoni összefüggés alapján —
ne erőltess mesterséges utalást, de ne is térj ki a feladat elől.
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
    needs_gospel = not (
        _usable_text(outline.get("christ_connection"))
        or _usable_text(outline.get("divine_gracious_action"))
    )
    # Ha már van heurisztikus provisional, az MI finomíthatja — de csak gap-ekre
    if not (
        needs_movements
        or needs_opening
        or needs_closing
        or needs_idea
        or needs_gospel
    ):
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
        "tartalmat ne cseréld le.\n"
        "Mozgáscímek legyenek textusspecifikusak. Tilos a sablonos helykitöltő.\n"
        "Töltsd ki a christ_connection / divine_gracious_action / applications "
        "mezőket is, ha a forrásból felelősen következnek.\n\n"
        f"FORRÁS (csak nem üres mezők):\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"JELENLEGI VÁZLAT:\n{json.dumps(outline, ensure_ascii=False)}\n\n"
        "Kimenet JSON kulcsok (opcionálisak, csak ha indokolt):\n"
        '{"main_idea":"","opening_direction":"","christ_connection":"",'
        '"divine_gracious_action":"","grace_enabled_response":"",'
        '"gospel_resolution":"",'
        '"movements":[{"id":"","title":"",'
        '"role":"","textual_basis":"","core_content":"","listener_discovery":"",'
        '"transition":""}],"closing":{"final_insight":"","gospel_assurance":"",'
        '"invitation":""},"applications":["",""],'
        '"provisional_sections":["opening_direction","sermon_movements","closing"]}'
    )
    try:
        # generate_text a session temperature-t használja, nem kwarg-ot.
        prev_temp = None
        try:
            import streamlit as st

            prev_temp = st.session_state.get("temperature")
            st.session_state["temperature"] = DEFAULT_TEMPERATURE
        except Exception:  # noqa: BLE001
            prev_temp = None
        try:
            raw = generate_fn(
                prompt,
                enable_google_search=False,
                tab_label=TAB_OUTLINE,
                use_cache=False,
                system_bundle=_SYNTH_SYSTEM,
                include_brevity_directive=False,
            )
        finally:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:  # noqa: BLE001
                pass
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
    if not _s(merged.get("main_idea")) and _usable_text(obj.get("main_idea")):
        merged["main_idea"] = _usable_text(obj.get("main_idea"))
        provisional.append("main_idea")

    if (
        not _s(merged.get("opening_direction")) or "opening_direction" in provisional
    ) and _usable_text(obj.get("opening_direction")):
        opening = _usable_text(obj.get("opening_direction"))
        idea_n = _normalize_cmp(merged.get("main_idea"))
        if opening and _normalize_cmp(opening) != idea_n:
            merged["opening_direction"] = opening
            if "opening_direction" not in provisional:
                provisional.append("opening_direction")

    # Krisztus-/kegyelemív — csak üres mezőkre
    for gkey in (
        "christ_connection",
        "divine_gracious_action",
        "grace_enabled_response",
        "gospel_resolution",
    ):
        if not _usable_text(merged.get(gkey)) and _usable_text(obj.get(gkey)):
            merged[gkey] = _usable_text(obj.get(gkey))

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
            title = _usable_text(mv.get("title")) or _title_from_text(
                _usable_text(mv.get("core_content")),
                fallback=f"{i}. mozgás",
            )
            if is_banned_outline_placeholder(title) or _normalize_cmp(
                title
            ) in _GENERIC_MOVEMENT_TITLES:
                title = _title_from_text(
                    _usable_text(mv.get("core_content"))
                    or _usable_text(mv.get("textual_basis")),
                    fallback=f"{i}. mozgás",
                )
            item = empty_outline_movement()
            item.update(
                {
                    "id": _s(mv.get("id")) or f"prov_mv_{i}",
                    "title": title,
                    "role": role,
                    "role_label": movement_role_label(role) if role else "",
                    "textual_basis": _usable_text(mv.get("textual_basis")),
                    "core_content": _usable_text(mv.get("core_content")),
                    "listener_discovery": _usable_text(mv.get("listener_discovery")),
                    "transition": _usable_text(mv.get("transition")),
                    "images": [],
                    "illustrations": [],
                    "applications": [],
                }
            )
            if _usable_text(item["core_content"]) or _usable_text(item["title"]):
                new_mvs.append(item)
        if new_mvs:
            merged["movements"] = new_mvs
            if "sermon_movements" not in provisional:
                provisional.append("sermon_movements")

    obj_closing = obj.get("closing") if isinstance(obj.get("closing"), dict) else {}
    if obj_closing:
        cur_closing = dict(merged.get("closing") or {})
        idea_n = _normalize_cmp(merged.get("main_idea"))
        for key in ("final_insight", "gospel_assurance", "invitation"):
            candidate = _usable_text(obj_closing.get(key))
            if not candidate:
                continue
            if key == "final_insight" and idea_n and _normalize_cmp(candidate) == idea_n:
                continue
            if not _usable_text(cur_closing.get(key)) or "closing" in provisional:
                cur_closing[key] = candidate
                if "closing" not in provisional:
                    provisional.append("closing")
        merged["closing"] = cur_closing

    # Alkalmazások → extra_enrichment
    raw_apps = obj.get("applications")
    if isinstance(raw_apps, list):
        extra = dict(merged.get("extra_enrichment") or {})
        existing = [
            _usable_text(x)
            for x in (extra.get("applications") or [])
            if _usable_text(x)
        ]
        seen = {_normalize_cmp(x) for x in existing}
        for item in raw_apps:
            a = _usable_text(item)
            n = _normalize_cmp(a)
            if a and n not in seen:
                existing.append(a)
                seen.add(n)
        if existing:
            extra["applications"] = existing[:8]
            merged["extra_enrichment"] = extra

    for extra in obj.get("provisional_sections") or []:
        label = _s(extra)
        if label and label not in provisional:
            provisional.append(label)

    merged["provisional_sections"] = list(dict.fromkeys(provisional))
    merged = normalize_sermon_outline(merged)
    merged["content"] = outline_to_readable_content(merged)
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

    bundle = collect_available_sermon_material(session_state, sermon_workshop=sw)
    outline = build_outline_from_workshop(session_state, sermon_workshop=sw)
    warnings: list[str] = []

    if synthesize:
        # Kétfázisú homiletikai szintézis (szerkesztő + opcionális lektor).
        # generate_fn nélkül a helyi seed marad (offline / teszt).
        # AI minőségi bukás esetén ne mentünk használhatatlan vázlatot „kész”-ként.
        try:
            from sermon_workshop_outline_synth_ai import (
                SOFT_QUALITY_ISSUES,
                assess_outline_quality_issues,
                run_two_phase_outline_synthesis,
            )

            outline, synth_warnings = run_two_phase_outline_synthesis(
                outline, bundle, generate_fn=generate_fn
            )
            warnings.extend(
                w for w in synth_warnings if not str(w).startswith("QUALITY_GATE_FAILED:")
            )
            quality_failed = any(
                str(w).startswith("QUALITY_GATE_FAILED:") for w in synth_warnings
            )
            remaining_ai = [
                i
                for i in assess_outline_quality_issues(
                    outline, for_ai_output=True, bundle=bundle
                )
                if i not in SOFT_QUALITY_ISSUES
            ]
            if generate_fn is not None and (quality_failed or remaining_ai):
                return OutlineAssemblyResult(
                    outline=normalize_sermon_outline(sw.get("sermon_outline")),
                    ok=False,
                    error_message=(
                        "A vázlatgenerálás nem adott szószéken használható eredményt. "
                        "Próbáld újra, vagy egészítsd ki a műhelyanyagot."
                    ),
                    warnings=warnings,
                )
        except Exception as exc:  # noqa: BLE001
            if generate_fn is not None:
                return OutlineAssemblyResult(
                    outline=normalize_sermon_outline(sw.get("sermon_outline")),
                    ok=False,
                    error_message=(
                        "A vázlat AI-szintézise sikertelen. "
                        f"Próbáld újra. ({exc})"
                    ),
                    warnings=warnings,
                )
            warnings.append(f"Szintézis tartalék módra váltott: {exc}")
            outline, synth_warnings = _synthesize_outline_gaps(
                outline, bundle, generate_fn=generate_fn
            )
            warnings.extend(synth_warnings)

    if polish:
        outline, polish_warnings = _optional_polish(outline, generate_fn=generate_fn)
        warnings.extend(polish_warnings)

    # Ne jelenjen meg „hiányos műhely” jellegű figyelmeztetés, ha van tipp.
    if outline_has_provisional_bridges(outline) and not (
        outline.get("editorial_tips") or []
    ):
        notice = PROVISIONAL_NOTICE
        if notice not in warnings:
            warnings.append(notice)

    outline = sync_outline_content(outline, force=True)
    outline["needs_rebuild"] = False
    if not outline_has_content(outline):
        return OutlineAssemblyResult(
            outline=normalize_sermon_outline(sw.get("sermon_outline")),
            ok=False,
            error_message=(
                "Nem jött létre olvasható vázlattartalom a rendelkezésre álló "
                "anyagból. Tölts ki legalább egy műhelyszakaszt, majd próbáld újra."
            ),
            warnings=warnings,
        )

    return OutlineAssemblyResult(
        outline=outline,
        ok=True,
        warnings=warnings,
        overwritten_manual_edit=bool(manually_edited and force_overwrite),
    )


__all__ = [
    "TAB_OUTLINE",
    "MISSING_PART",
    "OUTLINE_PLACEHOLDER_BANLIST",
    "PROVISIONAL_NOTICE",
    "EMPTY_PROJECT_MESSAGE",
    "GenerateFn",
    "OutlineAssemblyResult",
    "OutlineReadiness",
    "assess_outline_readiness",
    "assemble_sermon_outline",
    "build_outline_from_workshop",
    "collect_outline_context_bundle",
    "collect_available_sermon_material",
    "editable_outline_snapshot",
    "empty_sermon_outline",
    "is_banned_outline_placeholder",
    "outline_canonical_text",
    "outline_has_content",
    "outline_has_provisional_bridges",
    "outline_missing_parts",
    "outline_part_display",
    "outline_refinable_parts",
    "outline_refinable_summary",
    "outline_to_readable_content",
    "repair_outline_integrity",
    "render_compact_sermon_outline",
    "render_pulpit_outline_view",
    "sync_outline_content",
]
