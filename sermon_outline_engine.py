"""Egyetlen közös igehirdetési-vázlat motor.

Mindkét belépési pont (Gyorseszközök → Vázlat, Igehirdetési műhely →
Igehirdetési vázlat) ezt a modult hívja. Egy séma, egy validátor, egy
tömörítő javítás. Nem importál app.py / sermon_workshop_ui.py fájlból.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    empty_outline_movement,
    empty_sermon_outline,
    ensure_sermon_workshop_state,
    normalize_sermon_outline,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _is_api_error_text

GenerateFn = Callable[..., str]

TAB_OUTLINE = "Igehirdetési vázlat"
DEFAULT_TEMPERATURE = 0.2

# ---------------------------------------------------------------------------
# Strict length limits (HARD)
# ---------------------------------------------------------------------------

LIMITS = {
    "title_words": 10,
    "focus_words": 40,
    "intro_words": 55,
    "intro_sentences_max": 2,
    "point_title_words": 12,
    "thesis_words": 35,
    "subpoint_min_words": 12,
    "subpoint_max_words": 30,
    "application_words": 30,
    "conclusion_words": 55,
    "conclusion_sentences_max": 2,
    "min_points": 3,
    "max_points": 5,
    "min_points_exception": 2,  # text structure may require 2
    "min_subpoints": 2,
    "max_subpoints": 3,
    "target_min_words": 350,
    "target_max_words": 550,
    "absolute_max_words": 650,
    "refinement_max": 2,
}

FORBIDDEN_HEADINGS: tuple[str, ...] = (
    "Mit rendez ez a pont",
    "Textuális horgony",
    "Teológiai horgony",
    "Textuális/teológiai horgony",
    "Átvezetési logika",
    "Diagnózis → evangéliumi fordulat → Isten válasza",
    "diagnózis → evangéliumi fordulat",
    "Exegetikai kibontás",
    "Kegyelmi kapcsolat",
    "Hallgatói kapcsolat",
    "Hallgatói felismerés",
    "Alkalmazási pontok",
    "Tételmondat (scopus)",
)

FORBIDDEN_FILLERS: tuple[str, ...] = (
    "de vajon",
    "ez azonban",
    "itt felmerül a kérdés",
    "nem marad titokban",
)

COMPRESS_INSTRUCTION = (
    "Tartsd meg a gondolati ívet és a textuális tartalmat, de alakítsd át "
    "szigorúan a megadott vázlatsémára. Töröld az ismétléseket, a magyarázó "
    "bekezdéseket és a metaszöveget. Ne adj hozzá új teológiai tartalmat."
)

OUTLINE_SYSTEM_PROMPT = """\
SZEREP
Tapasztalt, textushű, református szemléletű homiletikai szerkesztő vagy.
Feladatod: szószékre kész HOMILETIKAI VÁZLAT — nem teljes prédikáció,
nem részletes kommentár, nem diagnosztika, nem metaszöveg a vázlat szerkezetéről.

KÖTELEZŐ KIMENET
KIZÁRÓLAG érvényes JSON az alábbi sémával (semmi Markdown, semmi magyarázat):
{
  "title": "string",
  "text_reference": "string",
  "scope_note": "string or empty",
  "focus_sentence": "string",
  "introduction_direction": "string",
  "points": [
    {
      "title": "string",
      "verses": "string",
      "thesis": "string",
      "subpoints": ["string", "string"],
      "application": "string or empty"
    }
  ],
  "conclusion_direction": "string",
  "refinement_suggestions": ["string"]
}

HOSSZKORLÁTOK (KÖTELEZŐ)
- title: ≤10 szó
- focus_sentence: pontosan 1 mondat, ≤40 szó
- introduction_direction: 1–2 mondat, ≤55 szó
- points: 3–5 (kivételesen 2, ha a textus szerkezete indokolja)
- point.title: ≤12 szó
- point.thesis: ≤35 szó
- point.subpoints: 2–3; mindegyik pontosan 1 mondat, 12–30 szó
- point.application: legfeljebb 1 mondat, ≤30 szó (vagy üres)
- conclusion_direction: 1–2 mondat, ≤55 szó
- teljes vázlat cél: 350–550 szó; abszolút maximum 650 szó
- refinement_suggestions: legfeljebb 2 opcionális tipp („Tovább finomítható”);
  NEM a vázlat teste. Hiányzó műhelyszakaszokat NE említsd.

FORRÁSPRIORITÁS
1 bibliai szöveg/határok → 2 jóváhagyott textus fő gondolat → 3 eredeti/exegetikai
→ 4 történeti/műfaj/szerkezet → 5 jóváhagyott homiletikai döntések → 6 alkalom/bio
→ 7 felhasználói jegyzetek → 8 óvatos MI-összekötés, ha kell.

TILOS A KIMENETBEN
„Mit rendez ez a pont”, „Textuális/teológiai horgony”, „Átvezetési logika”,
„Diagnózis → evangéliumi fordulat → Isten válasza”, többbekezdéses egzegézis
pontonként, ismételt átfogalmazások, retorikai töltelék („de vajon…”,
„ez azonban…”, „itt felmerül a kérdés…”), hosszú dogmatikai kitérők,
kész bevezető/záróbeszéd, külön „Alkalmazási pontok” fejezet.
Versidézet: ne teljes szöveg — hivatkozás + rövid kulcskifejezés, ha kell.
Krisztus-/kegyelemhorizont: ahol indokolt, de ne mechanikus bekezdés minden pont végén.

A válasz CSAK a JSON objektum.\
"""

_JSON_SHAPE = """\
{
  "title": "Rövid cím",
  "text_reference": "Igehely",
  "scope_note": "",
  "focus_sentence": "Egyetlen fókuszmondat.",
  "introduction_direction": "Rövid bevezető irány.",
  "points": [
    {
      "title": "Pontcím",
      "verses": "v. x–y",
      "thesis": "Egy mondatos tétel.",
      "subpoints": [
        "Egy teljes, tartalmas mondat (12–30 szó).",
        "Második tartalmas mondat (12–30 szó)."
      ],
      "application": "Rövid alkalmazás vagy üres."
    }
  ],
  "conclusion_direction": "Rövid megérkezés.",
  "refinement_suggestions": []
}
"""


def _s(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_cmp(text: str) -> str:
    return " ".join(_s(text).casefold().split())


def word_count(text: Any) -> int:
    raw = _s(text)
    if not raw:
        return 0
    return len([w for w in re.split(r"\s+", raw) if w])


def sentence_count(text: Any) -> int:
    raw = _s(text)
    if not raw:
        return 0
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw) if p.strip()]
    return max(1, len(parts)) if raw else 0


def _looks_multi_paragraph(text: Any) -> bool:
    raw = _s(text)
    if not raw:
        return False
    if "\n\n" in raw:
        return True
    # 3+ mondat egy mezőben → prédikációs bekezdés
    return sentence_count(raw) >= 3 and word_count(raw) > 40


def empty_structured_outline() -> dict[str, Any]:
    return {
        "title": "",
        "text_reference": "",
        "scope_note": "",
        "focus_sentence": "",
        "introduction_direction": "",
        "points": [],
        "conclusion_direction": "",
        "refinement_suggestions": [],
    }


def normalize_structured_outline(raw: Any) -> dict[str, Any]:
    """AI / legacy payload → kanonikus struktúra."""
    base = empty_structured_outline()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    out["title"] = _s(raw.get("title") or raw.get("sermon_title"))
    out["text_reference"] = _s(
        raw.get("text_reference") or raw.get("passage_reference")
    )
    out["scope_note"] = _s(raw.get("scope_note") or raw.get("text_boundary_note"))
    out["focus_sentence"] = _s(raw.get("focus_sentence") or raw.get("main_idea"))
    intro = raw.get("introduction") if isinstance(raw.get("introduction"), dict) else {}
    out["introduction_direction"] = _s(
        raw.get("introduction_direction")
        or intro.get("development")
        or raw.get("opening_direction")
    )
    conc = raw.get("conclusion") if isinstance(raw.get("conclusion"), dict) else {}
    closing = raw.get("closing") if isinstance(raw.get("closing"), dict) else {}
    out["conclusion_direction"] = _s(
        raw.get("conclusion_direction")
        or conc.get("development")
        or closing.get("final_insight")
    )
    tips = raw.get("refinement_suggestions") or raw.get("editorial_tips") or []
    cleaned_tips: list[str] = []
    for t in tips if isinstance(tips, list) else []:
        tip = _s(t)
        if not tip:
            continue
        low = tip.casefold()
        if any(
            w in low
            for w in ("hiányzik", "kötelező", "nem töltött", "üres mező", "műhelymez")
        ):
            continue
        cleaned_tips.append(tip)
    out["refinement_suggestions"] = cleaned_tips[: LIMITS["refinement_max"]]

    points: list[dict[str, Any]] = []
    raw_points = raw.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        raw_points = raw.get("movements") if isinstance(raw.get("movements"), list) else []
    for i, item in enumerate(raw_points[: LIMITS["max_points"]], start=1):
        if not isinstance(item, dict):
            continue
        title = re.sub(r"^\s*\d+[.)]\s*", "", _s(item.get("title"))).strip()
        verses = _s(
            item.get("verses")
            or item.get("textual_anchor")
            or item.get("textual_basis")
        )
        thesis = _s(item.get("thesis") or item.get("core_content"))
        subs_raw = item.get("subpoints")
        if not isinstance(subs_raw, list) or not subs_raw:
            subs_raw = item.get("development") if isinstance(item.get("development"), list) else []
        subpoints = [_s(x) for x in subs_raw if _s(x)][: LIMITS["max_subpoints"]]
        if not thesis and subpoints:
            thesis = subpoints[0]
            subpoints = subpoints[1:] if len(subpoints) > 1 else subpoints
        application = _s(item.get("application"))
        if not application:
            application = _s(item.get("listener_insight")) or _s(
                item.get("listener_discovery")
            )
        if not application:
            apps = item.get("applications") if isinstance(item.get("applications"), list) else []
            application = _s(apps[0]) if apps else ""
        if not title and not thesis and not subpoints:
            continue
        points.append(
            {
                "title": title or f"{i}. pont",
                "verses": verses,
                "thesis": thesis,
                "subpoints": subpoints,
                "application": application,
            }
        )
    out["points"] = points
    return out


def validate_structured_outline(payload: Any) -> list[str]:
    """Hard validation — bármely találat → érvénytelen (compress / reject)."""
    data = normalize_structured_outline(payload)
    issues: list[str] = []

    if not data["focus_sentence"]:
        issues.append("missing_focus")
    elif word_count(data["focus_sentence"]) > LIMITS["focus_words"]:
        issues.append("focus_too_long")
    elif sentence_count(data["focus_sentence"]) != 1:
        issues.append("focus_not_one_sentence")

    if data["title"] and word_count(data["title"]) > LIMITS["title_words"]:
        issues.append("title_too_long")

    intro = data["introduction_direction"]
    if not intro:
        issues.append("missing_intro")
    else:
        if word_count(intro) > LIMITS["intro_words"]:
            issues.append("intro_too_long")
        if sentence_count(intro) > LIMITS["intro_sentences_max"]:
            issues.append("intro_too_many_sentences")
        if _looks_multi_paragraph(intro):
            issues.append("intro_multi_paragraph")

    points = data["points"]
    n = len(points)
    if n < LIMITS["min_points_exception"]:
        issues.append("too_few_points")
    elif n < LIMITS["min_points"] and n != LIMITS["min_points_exception"]:
        # 2 pont csak kivétel — soft jelzés helyett hard, ha 0–1
        if n < 2:
            issues.append("too_few_points")
        elif n == 2:
            pass  # allowed exception
        else:
            issues.append("too_few_points")
    if n > LIMITS["max_points"]:
        issues.append("too_many_points")

    titles_seen: set[str] = set()
    for pt in points:
        title = _s(pt.get("title"))
        thesis = _s(pt.get("thesis"))
        subs = [_s(x) for x in (pt.get("subpoints") or []) if _s(x)]
        app = _s(pt.get("application"))
        tnorm = _normalize_cmp(title)
        if not title:
            issues.append("empty_point_title")
        elif word_count(title) > LIMITS["point_title_words"]:
            issues.append("point_title_too_long")
        if tnorm in titles_seen:
            issues.append("duplicate_points")
        titles_seen.add(tnorm)
        if not thesis:
            issues.append("missing_thesis")
        elif word_count(thesis) > LIMITS["thesis_words"]:
            issues.append("thesis_too_long")
        if len(subs) < LIMITS["min_subpoints"]:
            issues.append("too_few_subpoints")
        if len(subs) > LIMITS["max_subpoints"]:
            issues.append("too_many_subpoints")
        for sp in subs:
            wc = word_count(sp)
            if wc < LIMITS["subpoint_min_words"] or wc > LIMITS["subpoint_max_words"]:
                issues.append("subpoint_length")
            if sentence_count(sp) != 1:
                issues.append("subpoint_not_one_sentence")
            if _looks_multi_paragraph(sp):
                issues.append("multi_paragraph_point")
            # one-word stubs
            if wc <= 2:
                issues.append("stub_subpoint")
        if app:
            if word_count(app) > LIMITS["application_words"]:
                issues.append("application_too_long")
            if sentence_count(app) > 1:
                issues.append("application_too_many_sentences")

    conc = data["conclusion_direction"]
    if not conc:
        issues.append("missing_conclusion")
    else:
        if word_count(conc) > LIMITS["conclusion_words"]:
            issues.append("conclusion_too_long")
        if sentence_count(conc) > LIMITS["conclusion_sentences_max"]:
            issues.append("conclusion_too_many_sentences")
        if _looks_multi_paragraph(conc):
            issues.append("conclusion_multi_paragraph")

    rendered = render_structured_outline(data)
    total = word_count(rendered)
    if total > LIMITS["absolute_max_words"]:
        issues.append("over_absolute_max")
    if total and total < 120:
        issues.append("too_thin")

    blob = rendered.casefold()
    for heading in FORBIDDEN_HEADINGS:
        if heading.casefold() in blob:
            issues.append("forbidden_heading")
            break
    for filler in FORBIDDEN_FILLERS:
        if filler in blob:
            issues.append("forbidden_filler")
            break

    # Full-sermon heuristics: many long paragraphs
    para_count = len([p for p in rendered.split("\n\n") if len(p) > 80])
    if para_count >= 10 and total > LIMITS["target_max_words"]:
        issues.append("full_sermon_like")

    return list(dict.fromkeys(issues))


def render_structured_outline(payload: Any) -> str:
    """Felhasználói megjelenés — mezőnevek nélkül, tiszta vázlat."""
    data = normalize_structured_outline(payload)
    blocks: list[str] = []

    def _sec(label: str, body: str) -> None:
        text = _s(body)
        if text:
            blocks.append(f"**{label}**\n\n{text}")

    _sec("Cím", data["title"])
    _sec("Textus", data["text_reference"])
    if data["scope_note"]:
        _sec("Megjegyzés a textushatárról", data["scope_note"])
    _sec("Fókuszmondat", data["focus_sentence"])
    _sec("Bevezetés", data["introduction_direction"])

    for idx, pt in enumerate(data["points"], start=1):
        title = re.sub(r"^\s*\d+[.)]\s*", "", _s(pt.get("title"))).strip()
        if not title:
            continue
        parts: list[str] = []
        verses = _s(pt.get("verses"))
        thesis = _s(pt.get("thesis"))
        if verses:
            parts.append(f"*{verses}*")
        if thesis:
            parts.append(thesis)
        for sp in pt.get("subpoints") or []:
            cleaned = re.sub(r"^[-•*]\s+", "", _s(sp)).strip()
            if cleaned:
                parts.append(f"- {cleaned}")
        app = _s(pt.get("application"))
        if app:
            parts.append(f"*{app}*")
        if not parts:
            continue
        blocks.append(f"**{idx}. {title}**\n\n" + "\n".join(parts))

    _sec("Megérkezés", data["conclusion_direction"])
    text = "\n\n".join(blocks).strip()
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    return text + ("\n" if text else "")


def structured_to_sermon_outline(
    payload: Any,
    *,
    seed: Mapping[str, Any] | None = None,
    source: str = "",
    context_hash: str = "",
) -> dict[str, Any]:
    """Struktúra → tartós sermon_outline (legacy mezőkkel szinkronban)."""
    data = normalize_structured_outline(payload)
    outline = normalize_sermon_outline(seed) if seed else empty_sermon_outline()
    stamp = _now()
    outline["sermon_title"] = data["title"]
    outline["passage_reference"] = data["text_reference"] or _s(
        outline.get("passage_reference")
    )
    outline["text_boundary_note"] = data["scope_note"]
    outline["main_idea"] = data["focus_sentence"]
    outline["opening_direction"] = data["introduction_direction"]
    outline["introduction"] = {
        "development": data["introduction_direction"],
        "transition": "",
    }
    outline["conclusion"] = {
        "development": data["conclusion_direction"],
        "final_sentence": "",
    }
    closing = dict(outline.get("closing") or {})
    closing["final_insight"] = data["conclusion_direction"]
    outline["closing"] = closing
    outline["editorial_tips"] = list(data["refinement_suggestions"][:2])
    # Textushatár hint
    try:
        from sermon_workshop_outline_synth_ai import suggest_text_boundary_hint

        if not data["scope_note"]:
            hint = suggest_text_boundary_hint(
                data["text_reference"] or outline.get("passage_reference"),
                "",
            )
            if hint.get("text_boundary_note"):
                data["scope_note"] = hint["text_boundary_note"]
                outline["text_boundary_note"] = hint["text_boundary_note"]
                outline["suggested_text_boundary"] = hint.get(
                    "suggested_text_boundary", ""
                )
        elif "Júd 17–21" in data["scope_note"] or "Júd 17-21" in data["scope_note"]:
            outline["suggested_text_boundary"] = "Júd 17–21"
    except Exception:  # noqa: BLE001
        pass
    outline["text_boundary_note"] = data["scope_note"] or outline.get(
        "text_boundary_note", ""
    )

    movements: list[dict[str, Any]] = []
    for i, pt in enumerate(data["points"], start=1):
        item = empty_outline_movement()
        subs = [_s(x) for x in (pt.get("subpoints") or []) if _s(x)]
        thesis = _s(pt.get("thesis"))
        app = _s(pt.get("application"))
        verses = _s(pt.get("verses"))
        item.update(
            {
                "id": f"pt_{i}",
                "title": _s(pt.get("title")),
                "textual_basis": verses,
                "textual_anchor": verses,
                "core_content": thesis,
                "development": ([thesis] + subs) if thesis else subs,
                "listener_discovery": app,
                "applications": [app] if app else [],
                "transition": "",
            }
        )
        # Keep development as subpoints only for cleaner render when thesis separate
        item["development"] = subs[: LIMITS["max_subpoints"]]
        if thesis and thesis not in item["development"]:
            # Renderer uses core_content + development; store thesis in core
            pass
        movements.append(item)
    outline["movements"] = movements
    outline["structured"] = data
    outline["content"] = render_structured_outline(data)
    outline["structured"] = data
    outline["source"] = source if source in ("quick", "workshop") else _s(
        outline.get("source")
    )
    outline["context_hash"] = context_hash or _s(outline.get("context_hash"))
    if not outline.get("generated_at"):
        outline["generated_at"] = stamp
    outline["updated_at"] = stamp
    if _s(outline.get("status")) not in ("draft", "approved", "needs_refresh", "empty"):
        outline["status"] = "draft"
    outline["needs_rebuild"] = False
    outline["provisional_sections"] = []
    return normalize_sermon_outline(outline)


def sermon_outline_to_structured(outline: Any) -> dict[str, Any]:
    safe = normalize_sermon_outline(outline)
    stored = safe.get("structured")
    if isinstance(stored, dict) and (
        stored.get("points") or stored.get("focus_sentence")
    ):
        return normalize_structured_outline(stored)
    return normalize_structured_outline(safe)


def compute_context_hash(bundle: Mapping[str, Any]) -> str:
    """Forrásanyag ujjlenyomat — változás → needs_refresh, nem auto-duplikátum."""
    keys = (
        "passage_reference",
        "passage_text",
        "text_main_idea",
        "sermon_main_idea",
        "exegesis",
        "original_text",
        "theology",
        "history",
        "approved_insights",
        "approved_sermon_decisions",
        "human_condition",
        "listener_tension",
        "christ_centered_arc",
        "sermon_path",
        "sermon_movements",
        "closing",
        "occasion",
        "user_focus",
    )
    payload = {k: bundle.get(k) for k in keys if bundle.get(k) not in (None, "", [], {})}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def outline_needs_refresh(
    outline: Any,
    bundle: Mapping[str, Any],
) -> bool:
    safe = normalize_sermon_outline(outline)
    stored = _s(safe.get("context_hash") or safe.get("source_fingerprint"))
    if not stored:
        return False
    current = compute_context_hash(bundle)
    return bool(current and stored != current)


REFRESH_NOTICE = (
    "A műhelyanyag a vázlat elkészítése óta megváltozott. A vázlat frissíthető."
)

INVALID_OUTLINE_MESSAGE = (
    "A vázlatgenerálás nem adott szószéken használható, tömör vázlatot. "
    "Próbáld újra — a hosszú prédikációs szöveg nem kerül mentésre."
)


@dataclass
class OutlineGenerationResult:
    outline: dict[str, Any] = field(default_factory=empty_sermon_outline)
    ok: bool = True
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
    source: str = ""
    overwritten_manual_edit: bool = False

    def to_assembly_dict(self) -> dict[str, Any]:
        return {
            "outline": dict(self.outline),
            "ok": self.ok,
            "error_message": self.error_message,
            "warnings": list(self.warnings),
            "overwritten_manual_edit": self.overwritten_manual_edit,
        }


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    system_bundle: str = OUTLINE_SYSTEM_PROMPT,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    prev_temp = None
    touched = False
    try:
        import streamlit as st

        prev_temp = st.session_state.get("temperature")
        st.session_state["temperature"] = float(temperature)
        touched = True
    except Exception:  # noqa: BLE001
        touched = False
    try:
        return generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_OUTLINE,
            use_cache=False,
            system_bundle=system_bundle,
            include_brevity_directive=False,
        )
    finally:
        if touched:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:  # noqa: BLE001
                pass


def _heuristic_structured_from_bundle(
    bundle: Mapping[str, Any],
    *,
    seed_outline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Offline / teszt: tömör struktúra a rendelkezésre álló anyagból."""
    from sermon_workshop_outline_ai import (
        _prefer_main_idea,
        _truncate,
        _usable_text,
    )

    data = empty_structured_outline()
    data["text_reference"] = _s(bundle.get("passage_reference"))
    data["title"] = _s(bundle.get("project_title")) or data["text_reference"] or "Vázlat"
    if word_count(data["title"]) > LIMITS["title_words"]:
        data["title"] = " ".join(data["title"].split()[: LIMITS["title_words"]])

    focus = _prefer_main_idea(bundle)
    if not focus and seed_outline:
        focus = _s(seed_outline.get("main_idea"))
    data["focus_sentence"] = _usable_text(focus) or "A textus Isten megtartó szavát hirdeti."
    if word_count(data["focus_sentence"]) > LIMITS["focus_words"]:
        data["focus_sentence"] = " ".join(
            data["focus_sentence"].split()[: LIMITS["focus_words"]]
        )

    lt = bundle.get("listener_tension") if isinstance(bundle.get("listener_tension"), dict) else {}
    path = bundle.get("sermon_path") if isinstance(bundle.get("sermon_path"), dict) else {}
    intro = (
        _usable_text(path.get("starting_point"))
        or _usable_text(lt.get("listener_question"))
        or "A hallgató a textus feszültségéből indul, mielőtt a fő állítást hallaná."
    )
    data["introduction_direction"] = _truncate(intro, 280)
    if word_count(data["introduction_direction"]) > LIMITS["intro_words"]:
        data["introduction_direction"] = " ".join(
            data["introduction_direction"].split()[: LIMITS["intro_words"]]
        )

    points: list[dict[str, Any]] = []
    movements = bundle.get("sermon_movements") if isinstance(bundle.get("sermon_movements"), list) else []
    insights = [
        _usable_text(x)
        for x in (bundle.get("approved_insights") or [])
        if _usable_text(x)
    ]
    decisions = [
        _usable_text(x)
        for x in (bundle.get("approved_sermon_decisions") or [])
        if _usable_text(x)
    ]
    exe = _usable_text(bundle.get("exegesis"))
    original = _usable_text(bundle.get("original_text"))

    def _one_sentence(text: str, *, fallback: str, min_w: int = 12, max_w: int = 30) -> str:
        cleaned = _usable_text(text) or fallback
        words = cleaned.split()
        if len(words) < min_w:
            pad = fallback.split()
            words = (words + pad)[: max(min_w, len(words))]
            while len(words) < min_w:
                words.append("szava")
        words = words[:max_w]
        sent = " ".join(words).rstrip(".,;:")
        if not sent.endswith((".", "!", "?")):
            sent += "."
        return sent

    if movements:
        for i, mv in enumerate(movements[:5], start=1):
            if not isinstance(mv, dict):
                continue
            core = _usable_text(mv.get("core_content")) or _usable_text(
                mv.get("listener_discovery")
            )
            title = _usable_text(mv.get("title")) or f"Pont {i}"
            if word_count(title) > LIMITS["point_title_words"]:
                title = " ".join(title.split()[: LIMITS["point_title_words"]])
            thesis = _one_sentence(
                core or data["focus_sentence"],
                fallback=data["focus_sentence"],
                min_w=8,
                max_w=LIMITS["thesis_words"],
            )
            basis = _usable_text(mv.get("textual_basis"))
            sp1 = _one_sentence(
                core
                or exe
                or (insights[0] if insights else data["focus_sentence"]),
                fallback="A textus saját szavai rendezik ezt a gondolatot a hallgató előtt.",
            )
            sp2 = _one_sentence(
                _usable_text(mv.get("listener_discovery"))
                or (insights[1] if len(insights) > 1 else "")
                or original
                or "Isten cselekvése hív választ, nem csupán emberi erőfeszítés.",
                fallback="Isten cselekvése hív választ, nem csupán emberi erőfeszítés.",
            )
            points.append(
                {
                    "title": title,
                    "verses": basis or data["text_reference"],
                    "thesis": thesis,
                    "subpoints": [sp1, sp2],
                    "application": "",
                }
            )
    else:
        seeds = insights or decisions or [
            exe[:180] if exe else "",
            original[:180] if original else "",
            data["focus_sentence"],
        ]
        seeds = [s for s in seeds if s] or [data["focus_sentence"]]
        while len(seeds) < 3:
            seeds.append(data["focus_sentence"])
        titles = ("A textus megnyitása", "A központi állítás", "A kegyelmi megérkezés")
        for i in range(3):
            body = seeds[i % len(seeds)]
            points.append(
                {
                    "title": titles[i],
                    "verses": data["text_reference"],
                    "thesis": _one_sentence(
                        body,
                        fallback=data["focus_sentence"],
                        min_w=8,
                        max_w=LIMITS["thesis_words"],
                    ),
                    "subpoints": [
                        _one_sentence(
                            body,
                            fallback="A textus saját mozgása bontja ki ezt a pontot a hallgató előtt.",
                        ),
                        _one_sentence(
                            exe or original or data["focus_sentence"],
                            fallback="A hallgató Isten cselekvése felől látja meg a válasz útját.",
                        ),
                    ],
                    "application": "",
                }
            )

    data["points"] = points[:5]
    closing = bundle.get("closing") if isinstance(bundle.get("closing"), dict) else {}
    arc = (
        bundle.get("christ_centered_arc")
        if isinstance(bundle.get("christ_centered_arc"), dict)
        else {}
    )
    conc = (
        _usable_text(closing.get("final_discovery"))
        or _usable_text(arc.get("grace_enabled_response"))
        or "A hallgató Isten megtartó szeretetében állhat meg a megnyitott kérdésre."
    )
    data["conclusion_direction"] = _truncate(conc, 280)
    if word_count(data["conclusion_direction"]) > LIMITS["conclusion_words"]:
        data["conclusion_direction"] = " ".join(
            data["conclusion_direction"].split()[: LIMITS["conclusion_words"]]
        )
    data["refinement_suggestions"] = []
    return normalize_structured_outline(data)


def _ai_generate_structured(
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn,
    seed_outline: Mapping[str, Any] | None = None,
    mode: str = "standard",
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    ctx = {k: v for k, v in bundle.items() if not str(k).startswith("_")}
    mode_note = (
        "Gyors vázlat: a projektben jelenleg rendelkezésre álló anyagból dolgozz."
        if mode == "quick"
        else "Műhelyvázlat: használd a jóváhagyott homiletikai döntéseket is, ha vannak."
    )
    try:
        from sermon_workshop_outline_synth_ai import (
            _is_partial_workshop_bundle,
            outline_length_profile,
            resolve_outline_occasion,
        )

        profile = outline_length_profile(
            resolve_outline_occasion(bundle),
            partial=_is_partial_workshop_bundle(bundle),
        )
        occasion_block = (
            f"ALKALOM: {profile['occasion']}\n"
            f"CÉLHOSSZ: ~{profile['target_range']} szó "
            f"(abszolút max {LIMITS['absolute_max_words']}).\n"
            f"{profile['guidance']}\n"
        )
    except Exception:  # noqa: BLE001
        occasion_block = (
            f"CÉLHOSSZ: 350–550 szó (abszolút max {LIMITS['absolute_max_words']}).\n"
        )
    seed_slim = {}
    if seed_outline:
        seed_slim = {
            "main_idea": _s(seed_outline.get("main_idea")),
            "opening_direction": _s(seed_outline.get("opening_direction")),
            "movements": seed_outline.get("movements") or [],
        }
    prompt = (
        f"{mode_note}\n"
        f"{occasion_block}"
        "Készíts szószékre kész HOMILETIKAI VÁZLATOT a forrásból. "
        "Ne írj teljes prédikációt. Tartsd a szigorú hosszkorlátokat.\n"
        "Pontok: title, verses, thesis, subpoints (2–3; 12–30 szó; "
        "egyenként egy mondat), application (opcionális; alias: listener_insight).\n\n"
        f"FORRÁS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"MAG (opcionális):\n{json.dumps(seed_slim, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.3)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Vázlat AI-hívás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A vázlat AI-válasz hibát jelzett.")
        return None, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen JSON vázlatválasz.")
        return None, warnings
    return normalize_structured_outline(obj), warnings


def _compress_structured(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    ctx = {k: v for k, v in bundle.items() if not str(k).startswith("_")}
    try:
        from sermon_workshop_outline_synth_ai import (
            _is_partial_workshop_bundle,
            outline_length_profile,
            resolve_outline_occasion,
        )

        profile = outline_length_profile(
            resolve_outline_occasion(bundle),
            partial=_is_partial_workshop_bundle(bundle),
        )
        occasion_line = (
            f"ALKALOM: {profile['occasion']}. "
            f"CÉL: ~{profile['target_range']} szó.\n"
        )
        if profile.get("partial"):
            occasion_line += "Részleges műhelyanyag: tartsd a teljes szerkezetet, rövidebben.\n"
    except Exception:  # noqa: BLE001
        occasion_line = ""
    prompt = (
        f"{COMPRESS_INSTRUCTION}\n"
        f"{occasion_line}"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n"
        "Add vissza a teljes vázlatot a szigorú JSON sémában.\n\n"
        f"FORRÁS (csak támasz):\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"JAVÍTANDÓ VÁZLAT:\n{json.dumps(dict(payload), ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Tömörítő javítás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A tömörítő javítás API-hibát jelzett.")
        return None, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen tömörítő válasz.")
        return None, warnings
    return normalize_structured_outline(obj), warnings


def _programmatic_trim(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic length enforcement before/after AI."""
    data = normalize_structured_outline(payload)

    def _clip_words(text: str, max_w: int) -> str:
        words = _s(text).split()
        if len(words) <= max_w:
            return _s(text)
        clipped = " ".join(words[:max_w]).rstrip(".,;:")
        if clipped and not clipped.endswith((".", "!", "?")):
            clipped += "."
        return clipped

    data["title"] = _clip_words(data["title"], LIMITS["title_words"])
    data["focus_sentence"] = _clip_words(data["focus_sentence"], LIMITS["focus_words"])
    data["introduction_direction"] = _clip_words(
        data["introduction_direction"], LIMITS["intro_words"]
    )
    data["conclusion_direction"] = _clip_words(
        data["conclusion_direction"], LIMITS["conclusion_words"]
    )
    trimmed_points: list[dict[str, Any]] = []
    for pt in data["points"][: LIMITS["max_points"]]:
        subs = []
        for sp in (pt.get("subpoints") or [])[: LIMITS["max_subpoints"]]:
            words = _s(sp).split()
            if len(words) > LIMITS["subpoint_max_words"]:
                sp = " ".join(words[: LIMITS["subpoint_max_words"]]).rstrip(".,;:") + "."
            elif len(words) < LIMITS["subpoint_min_words"] and words:
                # leave short ones for validator; don't invent theology
                sp = _s(sp)
            if sp:
                # Keep only first sentence
                first = re.split(r"(?<=[.!?])\s+", sp)[0].strip()
                subs.append(first if first else sp)
        trimmed_points.append(
            {
                "title": _clip_words(_s(pt.get("title")), LIMITS["point_title_words"]),
                "verses": _s(pt.get("verses")),
                "thesis": _clip_words(_s(pt.get("thesis")), LIMITS["thesis_words"]),
                "subpoints": subs,
                "application": _clip_words(
                    _s(pt.get("application")), LIMITS["application_words"]
                ),
            }
        )
    data["points"] = trimmed_points
    data["refinement_suggestions"] = list(data["refinement_suggestions"][:2])
    # Absolute total: drop trailing subpoints if still over
    rendered = render_structured_outline(data)
    if word_count(rendered) > LIMITS["absolute_max_words"]:
        for pt in data["points"]:
            if len(pt["subpoints"]) > 2:
                pt["subpoints"] = pt["subpoints"][:2]
        rendered = render_structured_outline(data)
    if word_count(rendered) > LIMITS["absolute_max_words"]:
        data["introduction_direction"] = _clip_words(
            data["introduction_direction"], 40
        )
        data["conclusion_direction"] = _clip_words(data["conclusion_direction"], 40)
    return normalize_structured_outline(data)


def generate_sermon_outline(
    session_state: MutableMapping[str, Any] | Mapping[str, Any],
    *,
    mode: str = "standard",
    generate_fn: GenerateFn | None = None,
    force_overwrite: bool = False,
) -> OutlineGenerationResult:
    """Egyetlen vázlatgeneráló belépő.

    mode: \"quick\" | \"workshop\" | \"standard\" — csak kontextusdúsítás / forrásjelölés,
    NEM külön séma.
    """
    from sermon_workshop_outline_ai import (
        EMPTY_PROJECT_MESSAGE,
        assess_outline_readiness,
        build_outline_from_workshop,
        collect_available_sermon_material,
        outline_has_content,
    )

    source_tag = "quick" if mode == "quick" else "workshop" if mode == "workshop" else ""
    if mode == "standard":
        source_tag = "workshop"

    # Mutable session for ensure_*
    if not isinstance(session_state, MutableMapping):
        # read-only path for tests — copy into local mutable
        session: MutableMapping[str, Any] = dict(session_state)
    else:
        session = session_state

    ensure_sermon_workshop_state(session)
    sw = session[SERMON_WORKSHOP_KEY]
    readiness = assess_outline_readiness(session, sermon_workshop=sw)
    if not readiness.ok:
        return OutlineGenerationResult(
            outline=normalize_sermon_outline(sw.get("sermon_outline")),
            ok=False,
            error_message=readiness.message or EMPTY_PROJECT_MESSAGE,
            source=source_tag,
        )

    existing = normalize_sermon_outline(sw.get("sermon_outline"))
    manually_edited = bool(
        existing.get("manually_edited")
        or _s(sw.get("sermon_outline_status")) == "approved"
    )
    if outline_has_content(existing) and manually_edited and not force_overwrite:
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=(
                "A vázlat kézzel szerkesztve van. "
                "Frissítéshez erősítsd meg a felülírást."
            ),
            source=_s(existing.get("source")) or source_tag,
            overwritten_manual_edit=False,
        )

    bundle = collect_available_sermon_material(session, sermon_workshop=sw)
    ctx_hash = compute_context_hash(bundle)
    warnings: list[str] = []

    # Seed from workshop fields (deterministic) — never shown until validated
    seed = build_outline_from_workshop(session, sermon_workshop=sw)
    structured: dict[str, Any] | None = None

    if generate_fn is not None:
        structured, ai_warnings = _ai_generate_structured(
            bundle, generate_fn=generate_fn, seed_outline=seed, mode=mode
        )
        warnings.extend(ai_warnings)
    if structured is None:
        structured = _heuristic_structured_from_bundle(bundle, seed_outline=seed)

    structured = _programmatic_trim(structured)
    issues = validate_structured_outline(structured)

    if issues and generate_fn is not None:
        compressed, c_warn = _compress_structured(
            structured, bundle, issues=issues, generate_fn=generate_fn
        )
        warnings.extend(c_warn)
        if compressed is not None:
            structured = _programmatic_trim(compressed)
            issues = validate_structured_outline(structured)

    # Hard reject: never save long bad sermon as canonical
    hard_blockers = [
        i
        for i in issues
        if i
        in {
            "over_absolute_max",
            "full_sermon_like",
            "multi_paragraph_point",
            "forbidden_heading",
            "too_few_points",
            "missing_focus",
            "missing_intro",
            "missing_conclusion",
            "too_thin",
        }
    ]
    # After compress, remaining length/structure issues still block save when AI was used
    if generate_fn is not None and hard_blockers:
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=INVALID_OUTLINE_MESSAGE,
            warnings=warnings,
            validation_issues=issues,
            source=source_tag,
        )

    if generate_fn is not None and issues:
        # Soft-ish remaining (subpoint length etc.) — one more programmatic trim;
        # if still critically broken, reject.
        structured = _programmatic_trim(structured)
        issues = validate_structured_outline(structured)
        still_hard = [
            i
            for i in issues
            if i
            in {
                "over_absolute_max",
                "full_sermon_like",
                "forbidden_heading",
                "too_few_points",
                "missing_focus",
            }
        ]
        if still_hard:
            return OutlineGenerationResult(
                outline=existing,
                ok=False,
                error_message=INVALID_OUTLINE_MESSAGE,
                warnings=warnings,
                validation_issues=issues,
                source=source_tag,
            )

    # Offline heuristic: ensure we don't exceed absolute max after trim
    if word_count(render_structured_outline(structured)) > LIMITS["absolute_max_words"]:
        structured = _programmatic_trim(structured)

    outline = structured_to_sermon_outline(
        structured,
        seed=seed,
        source=source_tag or "workshop",
        context_hash=ctx_hash,
    )
    outline["source_fingerprint"] = ctx_hash
    outline["source_sections"] = list(bundle.get("source_keys") or [])
    # Heuristic / partial workshop → tip, not blocker
    if generate_fn is None and "sermon_movements" not in (bundle.get("source_keys") or []):
        outline["provisional_sections"] = ["sermon_movements"]
        from sermon_workshop_outline_ai import PROVISIONAL_NOTICE

        if PROVISIONAL_NOTICE not in warnings:
            warnings.append(PROVISIONAL_NOTICE)
    if not outline_has_content(outline):
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=EMPTY_PROJECT_MESSAGE,
            warnings=warnings,
            validation_issues=issues,
            source=source_tag,
        )

    return OutlineGenerationResult(
        outline=outline,
        ok=True,
        warnings=warnings,
        validation_issues=[i for i in issues if i not in hard_blockers],
        source=source_tag or "workshop",
        overwritten_manual_edit=bool(manually_edited and force_overwrite),
    )


__all__ = [
    "COMPRESS_INSTRUCTION",
    "FORBIDDEN_HEADINGS",
    "INVALID_OUTLINE_MESSAGE",
    "LIMITS",
    "OUTLINE_SYSTEM_PROMPT",
    "REFRESH_NOTICE",
    "OutlineGenerationResult",
    "compute_context_hash",
    "generate_sermon_outline",
    "normalize_structured_outline",
    "outline_needs_refresh",
    "render_structured_outline",
    "sermon_outline_to_structured",
    "structured_to_sermon_outline",
    "validate_structured_outline",
    "word_count",
]
