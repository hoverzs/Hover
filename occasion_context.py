"""Opcionális alkalmi háttér (occasion_context) — ceremoniális alkalmakhoz.

Strukturált, opcionális mezők virrasztó / temetés / keresztelés / esketés
esetén. Soha nem kötelező; nem szivárog globális history-ba vagy más
felhasználó projektjeibe. Vendégnél session-only; bejelentkezve a saját
projekt `project_data`-jában él.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

from passage_search_config import OCCASION_OPTIONS

OCCASION_CONTEXT_KEY = "occasion_context"

CEREMONIAL_OCCASIONS: frozenset[str] = frozenset(
    {
        "Virrasztó",
        "Temetés",
        "Keresztelés",
        "Esketés",
    }
)

# Mezőkulcsok csoportok szerint (UI + normalizálás).
FUNERAL_FIELD_KEYS: tuple[str, ...] = (
    "deceased_name",
    "age",
    "life_path",
    "specific_situation",
    "pastoral_note",
)
BAPTISM_FIELD_KEYS: tuple[str, ...] = (
    "child_name",
    "family_siblings",
    "parents_request",
    "pastoral_note",
)
WEDDING_FIELD_KEYS: tuple[str, ...] = (
    "couple_names",
    "shared_story",
    "marriage_emphasis",
    "pastoral_note",
)

ALL_FIELD_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (*FUNERAL_FIELD_KEYS, *BAPTISM_FIELD_KEYS, *WEDDING_FIELD_KEYS)
    )
)

# UI címkék (magyar).
FIELD_LABELS: dict[str, str] = {
    "deceased_name": "Az elhunyt neve / megszólítása",
    "age": "Életkor",
    "life_path": "Életút, foglalkozás, család — röviden",
    "specific_situation": "Különleges helyzet / mire van különösen szükség",
    "pastoral_note": "Pásztori háttérmegjegyzés",
    "child_name": "A gyermek neve",
    "family_siblings": "Család / testvérek",
    "parents_request": "A szülők kérése / hangsúlya",
    "couple_names": "A házasulandók nevei",
    "shared_story": "Közös történet / élethelyzet",
    "marriage_emphasis": "Házassági hangsúly / kérés",
}

FIELD_PLACEHOLDERS: dict[str, str] = {
    "deceased_name": "Pl. Kovács János bácsi",
    "age": "Pl. 78",
    "life_path": "Pl. tanár, három gyermek, hosszú házasság…",
    "specific_situation": "Pl. hirtelen veszteség; hosszú betegség után…",
    "pastoral_note": "Csak amit a megszólaláshoz valóban felhasználnál.",
    "child_name": "Pl. Anna",
    "family_siblings": "Pl. két idősebb testvér",
    "parents_request": "Pl. a szövetség ígéretének hangsúlya",
    "couple_names": "Pl. Eszter és Márton",
    "shared_story": "Pl. hosszú barátság után; gyülekezeti közösség…",
    "marriage_emphasis": "Pl. hűség és kölcsönös szolgálat",
}

_PROMPT_FIELD_LABELS: dict[str, str] = {
    "deceased_name": "elhunyt megszólítása",
    "age": "életkor",
    "life_path": "életút / család",
    "specific_situation": "helyzet / pásztori szükség",
    "pastoral_note": "pásztori megjegyzés",
    "child_name": "gyermek neve",
    "family_siblings": "család / testvérek",
    "parents_request": "szülői kérés / hangsúly",
    "couple_names": "házasulandók",
    "shared_story": "közös történet",
    "marriage_emphasis": "házassági hangsúly",
}

_MAX_FIELD_CHARS = 800
_MAX_PROMPT_CHARS = 1400

_GUARDRAIL_NOTE = (
    "SZABÁLYOK: Ne találj ki személyes tényt. Ne diagnosztizálj. "
    "Ne legyél tolakodó vagy érzelgős. Ne állíts bizonyosságot az "
    "elhunyt üdvösségéről. Személyes adatot NE másolj automatikusan a "
    "generált szövegbe — csak hangnem / irány / érzékenység."
)


def _s(value: Any, *, max_chars: int = _MAX_FIELD_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def is_ceremonial_occasion(occasion: Any) -> bool:
    return _s(occasion, max_chars=120) in CEREMONIAL_OCCASIONS


def field_keys_for_occasion(occasion: Any) -> tuple[str, ...]:
    occ = _s(occasion, max_chars=120)
    if occ in ("Virrasztó", "Temetés"):
        return FUNERAL_FIELD_KEYS
    if occ == "Keresztelés":
        return BAPTISM_FIELD_KEYS
    if occ == "Esketés":
        return WEDDING_FIELD_KEYS
    return ()


def empty_occasion_context(*, occasion_type: str = "") -> dict[str, Any]:
    occ = _s(occasion_type, max_chars=120)
    if occ and occ not in OCCASION_OPTIONS:
        occ = ""
    return {
        "occasion_type": occ,
        "fields": {key: "" for key in ALL_FIELD_KEYS},
        "note": "",
    }


def normalize_occasion_context(raw: Any) -> dict[str, Any]:
    """Régi / hiányos projektekhez is biztonságos üres alap."""
    base = empty_occasion_context()
    if not isinstance(raw, Mapping):
        return base
    occ = _s(raw.get("occasion_type") or raw.get("occasion"), max_chars=120)
    if occ and occ not in OCCASION_OPTIONS:
        occ = ""
    fields_raw = raw.get("fields")
    fields: dict[str, str] = {key: "" for key in ALL_FIELD_KEYS}
    if isinstance(fields_raw, Mapping):
        for key in ALL_FIELD_KEYS:
            fields[key] = _s(fields_raw.get(key))
    else:
        # Lapos legacy: mezők a gyökérben
        for key in ALL_FIELD_KEYS:
            if key in raw:
                fields[key] = _s(raw.get(key))
    note = _s(raw.get("note") or raw.get("pastoral_note_free"))
    # Ha a note üres, de van pastoral_note a fields-ben, ne másoljuk fel —
    # a pastoral_note a strukturált mező.
    return {
        "occasion_type": occ,
        "fields": fields,
        "note": note,
    }


def occasion_context_has_content(raw: Any) -> bool:
    ctx = normalize_occasion_context(raw)
    if _s(ctx.get("note")):
        return True
    fields = ctx.get("fields") or {}
    if isinstance(fields, Mapping):
        return any(_s(fields.get(k)) for k in ALL_FIELD_KEYS)
    return False


def relevant_fields(raw: Any, occasion: Any = "") -> dict[str, str]:
    """Az aktuális alkalomhoz tartozó, nem üres mezők."""
    ctx = normalize_occasion_context(raw)
    occ = _s(occasion, max_chars=120) or _s(ctx.get("occasion_type"), max_chars=120)
    keys = field_keys_for_occasion(occ)
    fields = ctx.get("fields") if isinstance(ctx.get("fields"), dict) else {}
    out: dict[str, str] = {}
    for key in keys:
        val = _s(fields.get(key))
        if val:
            out[key] = val
    note = _s(ctx.get("note"))
    if note and "pastoral_note" not in out:
        out["note"] = note
    elif note and note != out.get("pastoral_note"):
        out["note"] = note
    return out


def format_occasion_context_for_prompt(
    raw: Any,
    *,
    occasion: Any = "",
    label: str = "pásztori alkalmazási kontextus",
    max_chars: int = _MAX_PROMPT_CHARS,
    include_guardrails: bool = True,
) -> str:
    """Promptba illeszthető blokk; üres, ha nincs tartalom."""
    ctx = normalize_occasion_context(raw)
    occ = _s(occasion, max_chars=120) or _s(ctx.get("occasion_type"), max_chars=120)
    parts = relevant_fields(ctx, occ)
    if not parts and not is_ceremonial_occasion(occ):
        return ""
    if not parts:
        return ""
    lines = [f"{label}:"]
    if occ:
        lines.append(f"- alkalom típusa: {occ}")
    for key, val in parts.items():
        if key == "note":
            lab = "szabad pásztori megjegyzés"
        else:
            lab = _PROMPT_FIELD_LABELS.get(key, key)
        lines.append(f"- {lab}: {val}")
    if include_guardrails:
        lines.append(_GUARDRAIL_NOTE)
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def merge_context_for_passage_search(
    free_context: Any,
    occasion_context: Any,
    *,
    occasion: Any = "",
) -> str:
    """Szabad leírás + strukturált háttér a textusajánló promptjához."""
    free = _s(free_context, max_chars=1200)
    structured = format_occasion_context_for_prompt(
        occasion_context,
        occasion=occasion,
        label="Strukturált alkalmi háttér",
        include_guardrails=True,
    )
    chunks = [c for c in (free, structured) if c]
    return "\n\n".join(chunks)


def ensure_occasion_context_state(
    session_state: MutableMapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_occasion_context(session_state.get(OCCASION_CONTEXT_KEY))
    session_state[OCCASION_CONTEXT_KEY] = normalized
    return normalized


def update_occasion_context_fields(
    session_state: MutableMapping[str, Any],
    *,
    occasion_type: str = "",
    fields: Mapping[str, Any] | None = None,
    note: Any | None = None,
) -> dict[str, Any]:
    ctx = ensure_occasion_context_state(session_state)
    occ = _s(occasion_type, max_chars=120)
    if occ in OCCASION_OPTIONS:
        ctx["occasion_type"] = occ
    if fields:
        for key in ALL_FIELD_KEYS:
            if key in fields:
                ctx["fields"][key] = _s(fields.get(key))
    if note is not None:
        ctx["note"] = _s(note)
    session_state[OCCASION_CONTEXT_KEY] = normalize_occasion_context(ctx)
    return session_state[OCCASION_CONTEXT_KEY]


def widget_key_for_field(field_key: str) -> str:
    return f"passage_search_oc_{field_key}"


def sync_occasion_context_widgets_from_state(
    session_state: MutableMapping[str, Any],
) -> dict[str, str]:
    """Projektbetöltéshez: widget-kulcs → érték mapping."""
    ctx = ensure_occasion_context_state(session_state)
    fields = ctx.get("fields") if isinstance(ctx.get("fields"), dict) else {}
    pending: dict[str, str] = {}
    for key in ALL_FIELD_KEYS:
        pending[widget_key_for_field(key)] = _s(fields.get(key))
    return pending


def field_defs_for_occasion(occasion: Any) -> list[tuple[str, str, str]]:
    """(key, label, placeholder) lista az UI-hoz."""
    return [
        (
            key,
            FIELD_LABELS.get(key, key),
            FIELD_PLACEHOLDERS.get(key, ""),
        )
        for key in field_keys_for_occasion(occasion)
    ]


__all__ = [
    "OCCASION_CONTEXT_KEY",
    "CEREMONIAL_OCCASIONS",
    "FUNERAL_FIELD_KEYS",
    "BAPTISM_FIELD_KEYS",
    "WEDDING_FIELD_KEYS",
    "ALL_FIELD_KEYS",
    "FIELD_LABELS",
    "is_ceremonial_occasion",
    "field_keys_for_occasion",
    "field_defs_for_occasion",
    "empty_occasion_context",
    "normalize_occasion_context",
    "occasion_context_has_content",
    "relevant_fields",
    "format_occasion_context_for_prompt",
    "merge_context_for_passage_search",
    "ensure_occasion_context_state",
    "update_occasion_context_fields",
    "widget_key_for_field",
    "sync_occasion_context_widgets_from_state",
]
