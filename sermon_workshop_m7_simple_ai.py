"""Igehirdetési műhely — egyszerűsített illusztrációk és aktualizálás (M7 UI).

Egy MI-hívás az illusztrációkra; aktualizálás: webes keresés + egy összegző
MI-hívás. Nem írja át az M4–M6 promptokat. A régi részletes M7 mezők
kompatibilitása megmarad a data rétegben.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from current_events_search_service import (
    NO_SEARCH_MESSAGE,
    search_current_events,
)
from sermon_workshop_data import (
    empty_illustration,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _as_text, _is_api_error_text
from textus_workshop_data import TEXT_WORKSHOP_KEY, normalize_text_workshop

TAB_ILL = "Illusztrációk"
TAB_ACT = "Aktualizálás"
DEFAULT_TEMPERATURE = 0.25
MAX_ILLUSTRATION_SUGGESTIONS = 4
MAX_ACTUALIZATION_SUGGESTIONS = 5
MAX_PASSAGE = 2800
MAX_BLOCK = 1200

GenerateFn = Callable[..., str]

ILLUSTRATION_TYPES = (
    "textual_image",
    "everyday",
    "analogy",
    "historical",
    "literary",
    "spiritual_story",
    "other",
)

EMPTY_PASSAGE_MESSAGE = (
    "A javaslatokhoz töltsd be a bibliai szöveget (RÚF), vagy adj meg "
    "legalább egy érdemi műhelyeredményt."
)

NO_RELEVANT_EVENTS = (
    "A jelenlegi találatok között nincs olyan friss esemény, amelyet "
    "érdemes lenne erőltetés nélkül ehhez a textushoz kapcsolni."
)


def _s(value: Any) -> str:
    return str(value or "").strip()


def _truncate(text: str, limit: int) -> str:
    raw = _s(text)
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip() + "…"


def empty_illustration_card() -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "title": "",
        "type": "other",
        "idea": "",
        "connection_to_text": "",
        "usage_note": "",
        "source_name": "",
        "source_reference": "",
        "source_verification_required": False,
        "selected": False,
        "from_text_workshop": False,
        "listener_link": "",
    }


def empty_actualization_card() -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "title": "",
        "event_summary": "",
        "connection_to_text": "",
        "possible_use": "",
        "source_name": "",
        "source_url": "",
        "published_at": "",
        "caution": "",
        "selected": False,
        "from_text_workshop": False,
    }


def normalize_illustration_card(raw: Any) -> dict[str, Any]:
    base = empty_illustration_card()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "id",
        "title",
        "type",
        "idea",
        "connection_to_text",
        "usage_note",
        "source_name",
        "source_reference",
        "listener_link",
    ):
        if key in raw:
            out[key] = _s(raw.get(key))
    if out["type"] not in ILLUSTRATION_TYPES:
        out["type"] = "other"
    if not out["id"]:
        out["id"] = str(uuid.uuid4())
    out["source_verification_required"] = bool(
        raw.get("source_verification_required")
    )
    out["selected"] = bool(raw.get("selected"))
    out["from_text_workshop"] = bool(raw.get("from_text_workshop"))
    return out


def normalize_actualization_card(raw: Any) -> dict[str, Any]:
    base = empty_actualization_card()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "id",
        "title",
        "event_summary",
        "connection_to_text",
        "possible_use",
        "source_name",
        "source_url",
        "published_at",
        "caution",
    ):
        if key in raw:
            out[key] = _s(raw.get(key))
    if not out["id"]:
        out["id"] = str(uuid.uuid4())
    out["selected"] = bool(raw.get("selected"))
    out["from_text_workshop"] = bool(raw.get("from_text_workshop"))
    return out


def normalize_illustration_cards(raw: Any, *, max_items: int = 8) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        card = normalize_illustration_card(item)
        if _s(card.get("idea")) or _s(card.get("title")):
            out.append(card)
        if len(out) >= max_items:
            break
    return out


def normalize_actualization_cards(
    raw: Any, *, max_items: int = 8
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        card = normalize_actualization_card(item)
        if _s(card.get("title")) or _s(card.get("event_summary")):
            out.append(card)
        if len(out) >= max_items:
            break
    return out


def illustration_card_to_legacy(card: Mapping[str, Any]) -> dict[str, str]:
    """Kompatibilis M7 illusztráció a vázlat / régi mentésekhez."""
    item = empty_illustration()
    c = normalize_illustration_card(card)
    item["id"] = _s(c.get("id")) or item["id"]
    title = _s(c.get("title"))
    idea = _s(c.get("idea"))
    item["idea"] = f"{title} — {idea}" if title and idea and title not in idea else (idea or title)
    item["connection_to_text"] = _s(c.get("connection_to_text"))
    item["risk_or_limit"] = _s(c.get("usage_note"))
    if c.get("source_verification_required"):
        item["source"] = "needs_verification"
    elif _s(c.get("source_name")):
        item["source"] = "known_story"
    else:
        item["source"] = "everyday_observation"
    ref = _s(c.get("source_reference")) or _s(c.get("source_name"))
    if c.get("from_text_workshop"):
        item["source"] = "text_workshop_import"
        item["source_ref"] = ref or "text_workshop"
    else:
        item["source_ref"] = ref
    return item


def legacy_illustration_to_card(raw: Mapping[str, Any]) -> dict[str, Any]:
    card = empty_illustration_card()
    card["id"] = _s(raw.get("id")) or card["id"]
    card["idea"] = _s(raw.get("idea"))
    card["title"] = _truncate(card["idea"], 60) if card["idea"] else "Illusztráció"
    card["connection_to_text"] = _s(raw.get("connection_to_text"))
    card["usage_note"] = _s(raw.get("risk_or_limit"))
    card["source_reference"] = _s(raw.get("source_ref"))
    card["source_verification_required"] = _s(raw.get("source")) == "needs_verification"
    card["selected"] = True
    card["from_text_workshop"] = _s(raw.get("source")) == "text_workshop_import"
    return card


@dataclass
class EnrichmentReadiness:
    ok: bool
    message: str = ""


def assess_enrichment_readiness(session_state: Mapping[str, Any]) -> EnrichmentReadiness:
    passage = _s(session_state.get("last_igehely") or session_state.get("igehely_input"))
    passage_text = _s(session_state.get("passage_text"))
    if not passage:
        return EnrichmentReadiness(
            ok=False,
            message="Add meg az igehelyet, majd töltsd be a bibliai szöveget.",
        )
    tw = normalize_text_workshop(session_state.get(TEXT_WORKSHOP_KEY))
    sw = session_state.get("sermon_workshop")
    sw = sw if isinstance(sw, dict) else {}
    has_substance = bool(
        passage_text
        or _s(tw.get("text_main_idea"))
        or (tw.get("approved_insights") or [])
        or _s(sw.get("sermon_main_idea"))
        or _s(session_state.get("exegesis"))
        or _s(session_state.get("theology"))
        or _s(session_state.get("last_sajat"))
        or _s(session_state.get("actualization"))
        or _s(session_state.get("illustrations"))
    )
    if not has_substance:
        return EnrichmentReadiness(ok=False, message=EMPTY_PASSAGE_MESSAGE)
    return EnrichmentReadiness(ok=True)


def build_simple_enrichment_context(
    session_state: Mapping[str, Any],
    *,
    user_direction: str = "",
) -> dict[str, str]:
    """Tokenhatékony kontextus — csak nem üres mezők."""
    tw = normalize_text_workshop(session_state.get(TEXT_WORKSHOP_KEY))
    sw = session_state.get("sermon_workshop")
    sw = sw if isinstance(sw, dict) else {}
    ctx: dict[str, str] = {}
    passage = _s(session_state.get("last_igehely") or session_state.get("igehely_input"))
    if passage:
        ctx["passage"] = passage
    pt = _truncate(_s(session_state.get("passage_text")), MAX_PASSAGE)
    if pt:
        ctx["passage_text"] = pt
    if _s(tw.get("text_main_idea")):
        ctx["text_main_idea"] = _s(tw.get("text_main_idea"))
    insights = []
    for item in tw.get("approved_insights") or []:
        if isinstance(item, dict) and _s(item.get("content")):
            insights.append(_s(item.get("content")))
        if len(insights) >= 6:
            break
    if insights:
        ctx["approved_insights"] = "\n".join(f"- {x}" for x in insights)
    if _s(sw.get("sermon_main_idea")):
        ctx["sermon_main_idea"] = _s(sw.get("sermon_main_idea"))
    hc = sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    if any(_s(v) for v in hc.values()):
        ctx["human_condition"] = _truncate(json.dumps(hc, ensure_ascii=False), 800)
    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    if any(_s(v) for v in lt.values()):
        ctx["listener_tension"] = _truncate(json.dumps(lt, ensure_ascii=False), 800)
    arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    if any(_s(v) for v in arc.values()):
        ctx["christ_centered_arc"] = _truncate(json.dumps(arc, ensure_ascii=False), 800)
    movements = sw.get("sermon_movements") if isinstance(sw.get("sermon_movements"), list) else []
    if movements:
        lines = []
        for mv in movements[:5]:
            if not isinstance(mv, dict):
                continue
            title = _s(mv.get("title"))
            core = _s(mv.get("core_content"))
            if title or core:
                lines.append(f"- {title}: {_truncate(core, 180)}")
        if lines:
            ctx["sermon_movements"] = "\n".join(lines)
    for key, limit in (("exegesis", MAX_BLOCK), ("theology", MAX_BLOCK)):
        text = _truncate(_s(session_state.get(key)), limit)
        if text:
            ctx[key] = text
    basket_ill = _s(session_state.get("illustrations"))
    if basket_ill:
        ctx["textus_workshop_illustrations"] = _truncate(basket_ill, 1000)
    basket_act = _s(session_state.get("actualization"))
    if basket_act:
        ctx["textus_workshop_actualization"] = _truncate(basket_act, 1000)
    if _s(user_direction):
        ctx["user_direction"] = _s(user_direction)
    return ctx


_ILL_SYSTEM = """\
Te a TEXTUS homiletikai illusztráció-segédje vagy.
Adj legfeljebb 3–4 valóban eltérő illusztrációs javaslatot a megadott anyag alapján.
TILOS: kitalált haszid / Anthony de Mello / irodalmi történet biztos forrásként;
hosszú szerzői jogi idézet; új bibliai adat; kötelező külső illusztráció.
Ha a textus saját képe erősebb, mondd ki.
Bizonytalan forrásnál: source_verification_required=true és usage_note-ban
„A pontos forrás ellenőrzendő.”
Válaszod KIZÁRÓLAG érvényes JSON.\
"""

_ILL_PROMPT = """\
Feladat: illusztrációs javaslatok az igehirdetéshez.

## Kontextus
{context_json}

## Szabályok
- max 4 javaslat; ne legyen minden típusból kötelező példa;
- típusok: textual_image | everyday | analogy | historical | literary | spiritual_story | other;
- Anthony de Mello / haszid / irodalmi: ne találj ki történetet; rövid összefoglaló; forrás ellenőrzendő ha bizonytalan;
- ha nincs megbízható forrás, inkább hétköznapi példa;
- mondhatod: a textus saját képe erősebb, mint egy külső illusztráció.

## JSON
{{
  "note": "opcionális rövid megjegyzés",
  "suggestions": [
    {{
      "title": "rövid cím",
      "type": "everyday",
      "idea": "2-4 mondat",
      "connection_to_text": "1-2 mondat",
      "usage_note": "opcionális",
      "source_name": "opcionális",
      "source_reference": "opcionális",
      "source_verification_required": false,
      "listener_link": "opcionális rövid életkapcsolat"
    }}
  ]
}}
"""


_ACT_RANK_SYSTEM = """\
Te a TEXTUS aktualizálási segédje vagy.
A webes keresés eredményéből válogass legfeljebb 3–5 óvatos kapcsolódási pontot.
TILOS: hír ráerőltetése a textusra; politikai állásfoglalás; tragédia hatásvadász
használata; ellenőrizetlen szám; clickbait; összeesküvés; „bizonyítja a textust”.
Ha nincs érdemi találat, üres suggestions listát adj, és a note-ban írd:
„A jelenlegi találatok között nincs olyan friss esemény, amelyet érdemes lenne
erőltetés nélkül ehhez a textushoz kapcsolni.”
Válaszod KIZÁRÓLAG érvényes JSON.\
"""


@dataclass
class IllustrationSuggestResult:
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestions": [dict(x) for x in self.suggestions],
            "note": self.note,
            "ok": self.ok,
            "error_message": self.error_message,
        }


@dataclass
class ActualizationSuggestResult:
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    ok: bool = True
    error_message: str = ""
    used_web_search: bool = False
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestions": [dict(x) for x in self.suggestions],
            "note": self.note,
            "ok": self.ok,
            "error_message": self.error_message,
            "used_web_search": self.used_web_search,
        }


def suggest_illustrations(
    session_state: Mapping[str, Any],
    *,
    user_direction: str = "",
    generate_fn: GenerateFn | None = None,
) -> IllustrationSuggestResult:
    ready = assess_enrichment_readiness(session_state)
    if not ready.ok:
        return IllustrationSuggestResult(ok=False, error_message=ready.message)
    if generate_fn is None:
        return IllustrationSuggestResult(
            ok=False,
            error_message="Az illusztrációs javaslatkészítés jelenleg nem elérhető.",
        )
    ctx = build_simple_enrichment_context(
        session_state, user_direction=user_direction
    )
    prompt = _ILL_PROMPT.format(context_json=json.dumps(ctx, ensure_ascii=False, indent=2))
    try:
        raw = generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_ILL,
            use_cache=False,
            system_bundle=_ILL_SYSTEM,
            temperature=DEFAULT_TEMPERATURE,
            include_brevity_directive=False,
        )
    except TypeError:
        raw = generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_ILL,
            use_cache=False,
        )
    except Exception as exc:  # noqa: BLE001
        return IllustrationSuggestResult(ok=False, error_message=str(exc))

    if _is_api_error_text(raw or ""):
        return IllustrationSuggestResult(
            ok=False,
            error_message="Az illusztrációs javaslat nem sikerült.",
            raw_response=raw or "",
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return IllustrationSuggestResult(
            ok=False,
            error_message="Érvénytelen illusztrációs válasz.",
            raw_response=raw or "",
        )
    suggestions: list[dict[str, Any]] = []
    for item in obj.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        card = normalize_illustration_card(item)
        if _s(card.get("idea")) or _s(card.get("title")):
            card["selected"] = False
            suggestions.append(card)
        if len(suggestions) >= MAX_ILLUSTRATION_SUGGESTIONS:
            break
    return IllustrationSuggestResult(
        suggestions=suggestions,
        note=_as_text(obj.get("note")),
        ok=True,
        raw_response=raw or "",
    )


def suggest_actualizations(
    session_state: Mapping[str, Any],
    *,
    user_direction: str = "",
    generate_fn: GenerateFn | None = None,
) -> ActualizationSuggestResult:
    ready = assess_enrichment_readiness(session_state)
    if not ready.ok:
        return ActualizationSuggestResult(ok=False, error_message=ready.message)

    ctx = build_simple_enrichment_context(
        session_state, user_direction=user_direction
    )
    search_prompt = (
        "Keress friss, ellenőrizhető híreket / társadalmi jelenségeket, amelyek "
        "óvatosan kapcsolódhatnak ehhez a textushoz. Kerüld a pártpolitikát és a "
        "hatásvadászatot. Adj rövid címet, 2-3 mondatos összefoglalót, forrást, "
        "dátumot és URL-t, ahol lehetséges.\n\n"
        f"KONTEXTUS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        "Felhasználói irány: "
        f"{_s(user_direction) or '(nincs megadva — a textus hangsúlyai alapján)'}"
    )
    search = search_current_events(
        query_prompt=search_prompt,
        generate_fn=generate_fn,
        tab_label=TAB_ACT,
        system_bundle=(
            "Használd a Google Search eszközt. Csak valós, friss, ellenőrizhető "
            "források. Ne találj ki hírt. Kerüld a politikai állásfoglalást."
        ),
    )
    if not search.ok:
        return ActualizationSuggestResult(
            ok=False,
            error_message=search.error_message or NO_SEARCH_MESSAGE,
            used_web_search=search.used_web_search,
            raw_response=search.raw_text,
        )

    if generate_fn is None:
        return ActualizationSuggestResult(
            ok=False,
            error_message=NO_SEARCH_MESSAGE,
            used_web_search=False,
        )

    rank_prompt = (
        "Rangsorold a webes találatokat óvatos textus-kapcsolódási pontokká.\n\n"
        f"MŰHELYKONTEXTUS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"WEBES TALÁLATOK (rövid):\n{_truncate(search.raw_text, 6000)}\n\n"
        "JSON kimenet:\n"
        "{\n"
        '  "note": "opcionális",\n'
        '  "suggestions": [\n'
        "    {\n"
        '      "title": "",\n'
        '      "event_summary": "",\n'
        '      "connection_to_text": "",\n'
        '      "possible_use": "",\n'
        '      "source_name": "",\n'
        '      "source_url": "",\n'
        '      "published_at": "",\n'
        '      "caution": ""\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Max 5 tétel. Ha nincs érdemi kapcsolódás, suggestions=[] és a note-ban "
        f"írd: {NO_RELEVANT_EVENTS}"
    )
    try:
        raw = generate_fn(
            rank_prompt,
            enable_google_search=False,
            tab_label=TAB_ACT,
            use_cache=False,
            system_bundle=_ACT_RANK_SYSTEM,
            temperature=0.2,
            include_brevity_directive=False,
        )
    except TypeError:
        raw = generate_fn(
            rank_prompt,
            enable_google_search=False,
            tab_label=TAB_ACT,
            use_cache=False,
        )
    except Exception as exc:  # noqa: BLE001
        return ActualizationSuggestResult(
            ok=False,
            error_message=str(exc),
            used_web_search=True,
            raw_response=search.raw_text,
        )

    if _is_api_error_text(raw or ""):
        return ActualizationSuggestResult(
            ok=False,
            error_message="Az aktualizálási rangsorolás nem sikerült.",
            used_web_search=True,
            raw_response=raw or "",
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return ActualizationSuggestResult(
            ok=False,
            error_message="Érvénytelen aktualizálási válasz.",
            used_web_search=True,
            raw_response=raw or "",
        )
    suggestions: list[dict[str, Any]] = []
    for item in obj.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        card = normalize_actualization_card(item)
        if _s(card.get("title")) or _s(card.get("event_summary")):
            card["selected"] = False
            suggestions.append(card)
        if len(suggestions) >= MAX_ACTUALIZATION_SUGGESTIONS:
            break
    note = _as_text(obj.get("note"))
    if not suggestions and not note:
        note = NO_RELEVANT_EVENTS
    return ActualizationSuggestResult(
        suggestions=suggestions,
        note=note,
        ok=True,
        used_web_search=True,
        raw_response=raw or "",
    )


def collect_textus_retained_illustrations(
    session_state: Mapping[str, Any],
    *,
    existing_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Textusműhely kosár / illusztráció mező → egyszerű kártyák."""
    existing = existing_ids or set()
    out: list[dict[str, Any]] = []
    text = _s(session_state.get("illustrations"))
    if text and "tw_ill" not in existing:
        card = empty_illustration_card()
        card["id"] = "tw_ill_field"
        card["title"] = "Textusműhelyi illusztráció"
        card["idea"] = _truncate(text, 800)
        card["from_text_workshop"] = True
        card["selected"] = True
        out.append(card)
    basket = session_state.get("basket") or []
    if isinstance(basket, list):
        for idx, entry in enumerate(basket):
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            source, content = _s(entry[0]), _s(entry[1])
            if source != "Illusztráció" or not content:
                continue
            cid = f"basket_ill_{idx}"
            if cid in existing:
                continue
            card = empty_illustration_card()
            card["id"] = cid
            card["title"] = f"Textusműhely ({idx + 1})"
            card["idea"] = content
            card["from_text_workshop"] = True
            card["selected"] = True
            out.append(card)
    return out


def collect_textus_retained_actualizations(
    session_state: Mapping[str, Any],
    *,
    existing_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    existing = existing_ids or set()
    out: list[dict[str, Any]] = []
    text = _s(session_state.get("actualization"))
    if text and "tw_act" not in existing:
        card = empty_actualization_card()
        card["id"] = "tw_act_field"
        card["title"] = "Textusműhelyi aktualizálás"
        card["event_summary"] = _truncate(text, 800)
        card["from_text_workshop"] = True
        card["selected"] = True
        out.append(card)
    basket = session_state.get("basket") or []
    if isinstance(basket, list):
        for idx, entry in enumerate(basket):
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            source, content = _s(entry[0]), _s(entry[1])
            if source != "Aktualizálás" or not content:
                continue
            cid = f"basket_act_{idx}"
            if cid in existing:
                continue
            card = empty_actualization_card()
            card["id"] = cid
            card["title"] = f"Textusműhely aktualizálás ({idx + 1})"
            card["event_summary"] = content
            card["from_text_workshop"] = True
            card["selected"] = True
            out.append(card)
    return out


def sync_retained_illustrations_to_legacy(
    cards: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [illustration_card_to_legacy(c) for c in cards if c.get("selected") or True]


__all__ = [
    "TAB_ILL",
    "TAB_ACT",
    "EMPTY_PASSAGE_MESSAGE",
    "NO_RELEVANT_EVENTS",
    "NO_SEARCH_MESSAGE",
    "EnrichmentReadiness",
    "IllustrationSuggestResult",
    "ActualizationSuggestResult",
    "assess_enrichment_readiness",
    "build_simple_enrichment_context",
    "suggest_illustrations",
    "suggest_actualizations",
    "empty_illustration_card",
    "empty_actualization_card",
    "normalize_illustration_card",
    "normalize_actualization_card",
    "normalize_illustration_cards",
    "normalize_actualization_cards",
    "illustration_card_to_legacy",
    "legacy_illustration_to_card",
    "collect_textus_retained_illustrations",
    "collect_textus_retained_actualizations",
    "sync_retained_illustrations_to_legacy",
]
