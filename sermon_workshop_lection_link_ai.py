"""Lekció ↔ textus kapcsolati elemzés (egyszerű, textusközpontú).

Nem készít második prédikációt a lekcióból, és nem helyettesíti a Textusműhely
exegézisét. Cél: megmutatni, hogyan kapcsolódik a kiválasztott lekció az
aktuális igehirdetési textushoz, és hogyan segíti annak gyülekezeti meghallását.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping

from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import (
    MISSING,
    _as_str_list,
    _as_text,
    _display,
    _is_api_error_text,
    _is_present,
)
from sermon_workshop_m9_lection_ai import (
    references_equivalent,
    validate_lection_reference,
)

TAB_ANALYZE = "Lekció — kapcsolódás a textushoz"
DEFAULT_TEMPERATURE = 0.2
GenerateFn = Callable[..., str]

WEAK_CONNECTION_MESSAGE = "A kapcsolat inkább általános, mint szövegszerű."

LECTION_LINK_TYPES = (
    "immediate_context",
    "shared_motif",
    "promise_fulfillment",
    "theological_parallel",
    "typological_canonical",
    "contrast",
    "grace_response",
    "liturgical_preparation",
    "liturgical_arrival",
)

LECTION_LINK_TYPE_LABELS_HU: dict[str, str] = {
    "immediate_context": "Közvetlen szövegkörnyezeti kapcsolat",
    "shared_motif": "Közös bibliai motívum",
    "promise_fulfillment": "Ígéret és beteljesedés",
    "theological_parallel": "Teológiai párhuzam",
    "typological_canonical": "Tipológiai vagy kánoni kapcsolat",
    "contrast": "Kontraszt",
    "grace_response": "Kegyelmi válasz",
    "liturgical_preparation": "Liturgikus előkészítés",
    "liturgical_arrival": "Liturgikus megérkezés",
}

_PLACEMENT_LABELS_HU: dict[str, str] = {
    "introduction": "Bevezetés",
    "movement": "Prédikációs mozgás",
    "transition": "Átvezetés",
    "closing": "Lezárás",
    "prayer": "Imádsági válasz",
}

_BEFORE_AFTER_LABELS_HU: dict[str, str] = {
    "before": "Inkább a prédikáció előtt",
    "after": "Inkább a prédikáció után",
    "either": "Előtt vagy után is működhet",
}

_STRENGTH_VALUES = frozenset({"strong", "moderate", "weak"})
_PLACEMENT_VALUES = frozenset(_PLACEMENT_LABELS_HU)
_BEFORE_AFTER_VALUES = frozenset(_BEFORE_AFTER_LABELS_HU)

_SYSTEM = """\
Te református homiletikai segéd vagy. Feladatod: a KIVÁLASZTOTT LEKCIÓ és az \
IGEHIRDETÉSI TEXTUS kapcsolatának rövid, textusközpontú elemzése.

Alapelvek:
- A prédikáció textusa marad az elsődleges értelmezési középpont.
- A lekció előkészítheti, kiegészítheti, elmélyítheti, ellenpontozhatja, \
kánoni összefüggésbe helyezheti vagy liturgikus válasszal követheti a textust, \
de NE vegye át annak szerepét.
- NE készíts második prédikációt a lekcióból.
- NE elemezd a lekciót ugyanolyan részletességgel, mint a fő textust.
- NE találj ki görög/héber adatot, történeti tényt vagy tipológiát, ha a \
rendelkezésre álló anyag nem támasztja alá.
- Magyar szóazonosság alapján NE állíts lexikai kapcsolatot.
- Ha a kapcsolat gyenge vagy csak felszínes kulcsszóegyezés, mondd ki őszintén, \
és ajánlj legfeljebb két szorosabb alternatív lekciót.
- Ha a lekció és a textus azonos vagy jelentősen átfed, jelezd, és mondd meg, \
hogy külön lekcióként kevésbé indokolt, vagy csak liturgikus szerepe van.
- Csak érvényes JSON-t adj vissza, a megadott séma szerint.
"""

_USER_TEMPLATE = """\
Elemezd, hogyan kapcsolódik a lekció az igehirdetési textushoz.

## Textus (elsődleges)
Igehely: {{passage}}
Bibliai szöveg:
{{passage_text}}

## Lekció
Igehely: {{lection_reference}}
Teljes szöveg (ha van):
{{lection_text}}

## Elérhető műhelyanyag (opcionális, ha van)
Exegézis: {{exegesis}}
Eredeti nyelvi felismerések: {{original_text}}
Kortörténeti háttér: {{history}}
Teológiai hangsúlyok: {{theology}}
Homiletikai mag / fő gondolat: {{sermon_main_idea}}
Textus fő gondolata: {{text_main_idea}}
Igehirdetési vázlat (ha van):
{{sermon_outline_block}}

## Elvárt JSON
{
  "one_sentence": "Egy mondat: miért illik a lekció a textushoz.",
  "connection_types": [
    {
      "type": "immediate_context|shared_motif|promise_fulfillment|theological_parallel|typological_canonical|contrast|grace_response|liturgical_preparation|liturgical_arrival",
      "rationale": "Rövid indoklás (nem elég a típusnév)."
    }
  ],
  "key_links": [
    {
      "verse_or_detail": "Kapcsolódó igevers vagy részlet",
      "motif": "Közös vagy eltérő motívum",
      "sermon_significance": "Jelentőség a prédikáció szempontjából"
    }
  ],
  "linguistic_insights": [
    {
      "observation": "Csak ha valóban segíti a kapcsolat megértését",
      "why_it_matters": "Miért számít"
    }
  ],
  "historical_background": [
    {
      "observation": "Csak ha nélkülözhetetlen a kapcsolat megértéséhez"
    }
  ],
  "theological_gospel_link": {
    "divine_action": "Hogyan segíti Isten cselekvése megértését",
    "grace_arc": "Kegyelmi ív",
    "christ_centered": "Krisztus-központú kapcsolat — csak ha indokolt",
    "listener_response": "Hallgatói válasz előkészítése"
  },
  "liturgical_role": {
    "why_read": "Miért érdemes felolvasni",
    "congregation_focus": "Mire figyeljen a gyülekezet",
    "before_or_after": "before|after|either",
    "needs_brief_intro": false,
    "strongest_verses": "Legerősebb kapcsolathordozó versek"
  },
  "homiletical_uses": [
    {
      "placement": "introduction|movement|transition|closing|prayer",
      "suggestion": "Rövid javaslat — nem írja át a vázlatot"
    }
  ],
  "connection_strength": "strong|moderate|weak",
  "weak_connection_note": "",
  "alternative_lections": [
    {
      "reference": "Szorosabb alternatíva igehelye",
      "rationale": "Rövid indoklás"
    }
  ],
  "overlap_note": "Ha a textus és a lekció azonos/átfedő: rövid megjegyzés, különben üres."
}

Korlátok:
- connection_types: 1–2 elem
- key_links: 2–4 elem
- linguistic_insights: 0–2 (üres lista, ha nincs valódi nyelvi kapcsolat)
- historical_background: 0–3
- homiletical_uses: 0–3
- alternative_lections: csak gyenge kapcsolatnál, legfeljebb 2
- Ha connection_strength=weak, a weak_connection_note legyen pontosan:
  „A kapcsolat inkább általános, mint szövegszerű.”
"""


def lection_link_type_label(value: str) -> str:
    key = normalize_lection_link_type(value)
    if not key:
        return ""
    return LECTION_LINK_TYPE_LABELS_HU.get(key, key)


def normalize_lection_link_type(raw: Any) -> str:
    value = _as_text(raw).strip().casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "kozos_bibliai_motivum": "shared_motif",
        "shared_biblical_motif": "shared_motif",
        "kozvetlen_szovegkornyezeti": "immediate_context",
        "immediate_literary_context": "immediate_context",
        "igeret_es_beteljesedes": "promise_fulfillment",
        "teologiai_parhuzam": "theological_parallel",
        "tipologiai_vagy_kanoni": "typological_canonical",
        "canonical": "typological_canonical",
        "kegyelmi_valasz": "grace_response",
        "liturgikus_elokeszites": "liturgical_preparation",
        "liturgikus_megerkezes": "liturgical_arrival",
        "preparatory": "liturgical_preparation",
        "contrast": "contrast",
        "kontraszt": "contrast",
    }
    value = aliases.get(value, value)
    return value if value in LECTION_LINK_TYPES else ""


def placement_label(value: str) -> str:
    key = _as_text(value).strip().casefold()
    return _PLACEMENT_LABELS_HU.get(key, key)


def before_after_label(value: str) -> str:
    key = _as_text(value).strip().casefold()
    return _BEFORE_AFTER_LABELS_HU.get(key, key)


@dataclass
class LectionLinkTypeItem:
    type: str = ""
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "label": lection_link_type_label(self.type),
            "rationale": self.rationale,
        }


@dataclass
class LectionKeyLink:
    verse_or_detail: str = ""
    motif: str = ""
    sermon_significance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verse_or_detail": self.verse_or_detail,
            "motif": self.motif,
            "sermon_significance": self.sermon_significance,
        }


@dataclass
class LectionLinkAlternative:
    reference: str = ""
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"reference": self.reference, "rationale": self.rationale}


@dataclass
class LectionConnectionAnalysis:
    one_sentence: str = ""
    connection_types: list[LectionLinkTypeItem] = field(default_factory=list)
    key_links: list[LectionKeyLink] = field(default_factory=list)
    linguistic_insights: list[dict[str, str]] = field(default_factory=list)
    historical_background: list[dict[str, str]] = field(default_factory=list)
    theological_gospel_link: dict[str, str] = field(default_factory=dict)
    liturgical_role: dict[str, Any] = field(default_factory=dict)
    homiletical_uses: list[dict[str, str]] = field(default_factory=list)
    connection_strength: str = "moderate"
    weak_connection_note: str = ""
    alternative_lections: list[LectionLinkAlternative] = field(default_factory=list)
    overlap_note: str = ""
    source_fingerprint: str = ""
    passage_reference: str = ""
    lection_reference: str = ""
    generated_at: str = ""
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "one_sentence": self.one_sentence,
            "connection_types": [c.to_dict() for c in self.connection_types],
            "key_links": [k.to_dict() for k in self.key_links],
            "linguistic_insights": list(self.linguistic_insights),
            "historical_background": list(self.historical_background),
            "theological_gospel_link": dict(self.theological_gospel_link),
            "liturgical_role": dict(self.liturgical_role),
            "homiletical_uses": list(self.homiletical_uses),
            "connection_strength": self.connection_strength,
            "weak_connection_note": self.weak_connection_note,
            "alternative_lections": [a.to_dict() for a in self.alternative_lections],
            "overlap_note": self.overlap_note,
            "source_fingerprint": self.source_fingerprint,
            "passage_reference": self.passage_reference,
            "lection_reference": self.lection_reference,
            "generated_at": self.generated_at,
            "ok": self.ok,
            "error_message": self.error_message,
        }


def empty_lection_connection_analysis() -> dict[str, Any]:
    return LectionConnectionAnalysis(ok=False).to_dict()


def _clip(text: str, *, max_chars: int) -> str:
    raw = _as_text(text)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1].rstrip() + "…"


def _hash_text(value: Any) -> str:
    raw = _as_text(value).strip()
    if not raw:
        return ""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_lection_link_fingerprint(
    *,
    passage_reference: str = "",
    passage_text: str = "",
    lection_reference: str = "",
    lection_text: str = "",
    sermon_main_idea: str = "",
    outline_signature: str = "",
) -> str:
    """Forrásverzió-ujjlenyomat: textus + lekció + homiletikai mag / vázlat."""
    payload = "|".join(
        [
            _as_text(passage_reference).strip().casefold(),
            _hash_text(passage_text),
            _as_text(lection_reference).strip().casefold(),
            _hash_text(lection_text),
            _hash_text(sermon_main_idea),
            _hash_text(outline_signature),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:24]


def outline_signature_for_link(outline: Any) -> str:
    block = outline if isinstance(outline, dict) else {}
    if not block:
        return ""
    parts = [
        _as_text(block.get("central_claim")),
        _as_text(block.get("homiletical_aim")),
        _as_text(block.get("generated_at")),
        _as_text(block.get("updated_at")),
        _as_text(block.get("source_fingerprint")),
    ]
    movements = block.get("movements") if isinstance(block.get("movements"), list) else []
    for mv in movements[:8]:
        if isinstance(mv, dict):
            parts.append(_as_text(mv.get("title")))
            parts.append(_as_text(mv.get("core_content")))
    return "\n".join(p for p in parts if p)


def detect_passage_lection_overlap(
    passage_reference: str,
    lection_reference: str,
) -> str:
    """Azonos / jelentős átfedés rövid megjegyzése (heurisztika)."""
    p = _as_text(passage_reference).strip()
    l = _as_text(lection_reference).strip()
    if not p or not l:
        return ""
    if references_equivalent(p, l):
        return (
            "A lekció megegyezik vagy gyakorlatilag azonos az igehirdetési "
            "textussal — külön lekcióként kevésbé indokolt."
        )
    vp = validate_lection_reference(p)
    vl = validate_lection_reference(l)
    if not (vp.get("ok") and vl.get("ok")):
        if p.casefold() in l.casefold() or l.casefold() in p.casefold():
            return (
                "A lekció és a textus részben átfed — ellenőrizd, hogy a "
                "felolvasás valóban kiegészíti-e a prédikációt."
            )
        return ""
    np = str(vp.get("normalized_reference") or "")
    nl = str(vl.get("normalized_reference") or "")
    if np and nl and (np in nl or nl in np):
        return (
            "A lekció és a textus részben átfed — a kapcsolat liturgikus "
            "szerepe fontosabb lehet, mint a tartalmi kiegészítés."
        )
    # Azonos könyv + fejezet, átfedő versszakasz (pl. Júd 17–20 / Júd 17–23)
    book_p = str(vp.get("book_abbr") or "").strip().casefold()
    book_l = str(vl.get("book_abbr") or "").strip().casefold()
    if book_p and book_p == book_l:
        def _verse_span(normalized: str) -> tuple[int, int] | None:
            # „Júd 17–20” vagy „Jn 15,1–8”
            m = re.search(
                r"(\d+)\s*[,:]\s*(\d+)\s*[–\-]\s*(\d+)\s*$",
                normalized,
            )
            if m:
                return int(m.group(2)), int(m.group(3))
            m2 = re.search(r"(\d+)\s*[–\-]\s*(\d+)\s*$", normalized)
            if m2:
                return int(m2.group(1)), int(m2.group(2))
            m3 = re.search(r"(\d+)\s*$", normalized)
            if m3:
                v = int(m3.group(1))
                return v, v
            return None

        sp = _verse_span(np)
        sl = _verse_span(nl)
        if sp and sl:
            a0, a1 = sp
            b0, b1 = sl
            if max(a0, b0) <= min(a1, b1):
                return (
                    "A lekció és a textus részben átfed — a kapcsolat liturgikus "
                    "szerepe fontosabb lehet, mint a tartalmi kiegészítés."
                )
    return ""


def normalize_lection_connection_analysis(raw: Any) -> dict[str, Any] | None:
    """Tartós elemzés normalizálása; üres/None → None."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    if not raw:
        return None
    parsed = _parse_analysis_dict(raw, raw_response="")
    has_substance = bool(
        parsed.one_sentence
        or parsed.connection_types
        or parsed.key_links
        or parsed.linguistic_insights
        or parsed.historical_background
        or parsed.homiletical_uses
        or parsed.error_message
        or (parsed.ok is False)
    )
    if not has_substance:
        return None
    out = parsed.to_dict()
    out.pop("raw_response", None)
    return out


def lection_connection_analysis_is_stale(
    analysis: Mapping[str, Any] | None,
    *,
    current_fingerprint: str,
) -> bool:
    if not isinstance(analysis, dict):
        return False
    if analysis.get("ok") is False and not _as_text(analysis.get("one_sentence")):
        return False
    stored = _as_text(analysis.get("source_fingerprint")).strip()
    current = _as_text(current_fingerprint).strip()
    if not stored or not current:
        return False
    return stored != current


def _fill(template: str, values: Mapping[str, str]) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _format_outline_block(outline: Any) -> str:
    block = outline if isinstance(outline, dict) else {}
    if not block:
        return MISSING
    lines: list[str] = []
    for key, label in (
        ("central_claim", "Központi állítás"),
        ("homiletical_aim", "Homiletikai cél"),
        ("human_situation", "Emberi helyzet"),
        ("title", "Cím"),
    ):
        val = _as_text(block.get(key))
        if val:
            lines.append(f"{label}: {val}")
    movements = block.get("movements") if isinstance(block.get("movements"), list) else []
    for i, mv in enumerate(movements[:6], start=1):
        if not isinstance(mv, dict):
            continue
        title = _as_text(mv.get("title"))
        core = _as_text(mv.get("core_content"))
        if title or core:
            lines.append(f"Mozgás {i}: {title} — {_clip(core, max_chars=180)}")
    if not lines:
        return MISSING
    return _display("\n".join(lines), max_chars=1600)


def build_lection_link_context(
    *,
    passage: str = "",
    passage_text: str = "",
    lection_reference: str = "",
    lection_text: str = "",
    exegesis: str = "",
    original_text: str = "",
    history: str = "",
    theology: str = "",
    sermon_main_idea: str = "",
    text_main_idea: str = "",
    sermon_outline: Any = None,
) -> dict[str, str]:
    return {
        "passage": _display(passage, max_chars=200) if _is_present(passage) else MISSING,
        "passage_text": (
            _display(passage_text, max_chars=4500)
            if _is_present(passage_text)
            else MISSING
        ),
        "lection_reference": (
            _display(lection_reference, max_chars=200)
            if _is_present(lection_reference)
            else MISSING
        ),
        "lection_text": (
            _display(lection_text, max_chars=4500)
            if _is_present(lection_text)
            else MISSING
        ),
        "exegesis": _display(exegesis, max_chars=2200) if _is_present(exegesis) else MISSING,
        "original_text": (
            _display(original_text, max_chars=1800)
            if _is_present(original_text)
            else MISSING
        ),
        "history": _display(history, max_chars=1800) if _is_present(history) else MISSING,
        "theology": _display(theology, max_chars=1800) if _is_present(theology) else MISSING,
        "sermon_main_idea": (
            _display(sermon_main_idea, max_chars=800)
            if _is_present(sermon_main_idea)
            else MISSING
        ),
        "text_main_idea": (
            _display(text_main_idea, max_chars=800)
            if _is_present(text_main_idea)
            else MISSING
        ),
        "sermon_outline_block": _format_outline_block(sermon_outline),
    }


def build_lection_link_prompt(**kwargs: Any) -> str:
    ctx = build_lection_link_context(**kwargs)
    return _fill(_USER_TEMPLATE, ctx)


def _call_generate(
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
            tab_label=TAB_ANALYZE,
            use_cache=False,
            include_brevity_directive=False,
            system_bundle=_SYSTEM,
        )
    except TypeError:
        return generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_ANALYZE,
            use_cache=False,
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


def _parse_type_items(raw: Any) -> list[LectionLinkTypeItem]:
    items: list[LectionLinkTypeItem] = []
    if not isinstance(raw, list):
        return items
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        typ = normalize_lection_link_type(entry.get("type") or entry.get("label"))
        rationale = _as_text(entry.get("rationale") or entry.get("explanation"))
        if not typ and not rationale:
            continue
        items.append(LectionLinkTypeItem(type=typ, rationale=rationale))
        if len(items) >= 2:
            break
    return items


def _parse_key_links(raw: Any) -> list[LectionKeyLink]:
    items: list[LectionKeyLink] = []
    if not isinstance(raw, list):
        return items
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        link = LectionKeyLink(
            verse_or_detail=_as_text(
                entry.get("verse_or_detail") or entry.get("verse") or entry.get("detail")
            ),
            motif=_as_text(entry.get("motif")),
            sermon_significance=_as_text(
                entry.get("sermon_significance") or entry.get("significance")
            ),
        )
        if not (link.verse_or_detail or link.motif or link.sermon_significance):
            continue
        items.append(link)
        if len(items) >= 4:
            break
    return items


def _parse_insight_list(raw: Any, *, text_key: str, max_items: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if isinstance(entry, str) and entry.strip():
            out.append({text_key: entry.strip(), "why_it_matters": ""})
        elif isinstance(entry, dict):
            obs = _as_text(
                entry.get(text_key) or entry.get("observation") or entry.get("text")
            )
            why = _as_text(entry.get("why_it_matters") or entry.get("significance"))
            if obs:
                out.append({text_key: obs, "why_it_matters": why})
        if len(out) >= max_items:
            break
    return out


def _parse_analysis_dict(
    obj: Mapping[str, Any],
    *,
    raw_response: str,
) -> LectionConnectionAnalysis:
    strength = _as_text(obj.get("connection_strength")).strip().casefold()
    if strength not in _STRENGTH_VALUES:
        strength = "moderate"

    weak_note = _as_text(obj.get("weak_connection_note"))
    alts_raw = obj.get("alternative_lections")
    alts: list[LectionLinkAlternative] = []
    if isinstance(alts_raw, list):
        for entry in alts_raw:
            if not isinstance(entry, dict):
                continue
            ref = _as_text(entry.get("reference"))
            rat = _as_text(entry.get("rationale"))
            if ref or rat:
                alts.append(LectionLinkAlternative(reference=ref, rationale=rat))
            if len(alts) >= 2:
                break

    if strength == "weak":
        weak_note = WEAK_CONNECTION_MESSAGE
    else:
        weak_note = ""
        alts = []

    theo_raw = obj.get("theological_gospel_link")
    theo = theo_raw if isinstance(theo_raw, dict) else {}
    theological = {
        "divine_action": _as_text(theo.get("divine_action")),
        "grace_arc": _as_text(theo.get("grace_arc")),
        "christ_centered": _as_text(theo.get("christ_centered")),
        "listener_response": _as_text(theo.get("listener_response")),
    }

    lit_raw = obj.get("liturgical_role")
    lit = lit_raw if isinstance(lit_raw, dict) else {}
    before_after = _as_text(lit.get("before_or_after")).strip().casefold()
    if before_after not in _BEFORE_AFTER_VALUES:
        before_after = "either"
    liturgical = {
        "why_read": _as_text(lit.get("why_read")),
        "congregation_focus": _as_text(lit.get("congregation_focus")),
        "before_or_after": before_after,
        "needs_brief_intro": bool(lit.get("needs_brief_intro")),
        "strongest_verses": _as_text(lit.get("strongest_verses")),
    }

    uses: list[dict[str, str]] = []
    uses_raw = obj.get("homiletical_uses")
    if isinstance(uses_raw, list):
        for entry in uses_raw:
            if not isinstance(entry, dict):
                continue
            placement = _as_text(entry.get("placement")).strip().casefold()
            if placement not in _PLACEMENT_VALUES:
                placement = "movement"
            suggestion = _as_text(entry.get("suggestion"))
            if suggestion:
                uses.append({"placement": placement, "suggestion": suggestion})
            if len(uses) >= 3:
                break

    linguistic = _parse_insight_list(
        obj.get("linguistic_insights"), text_key="observation", max_items=2
    )
    # Ensure shape
    linguistic_norm: list[dict[str, str]] = []
    for row in linguistic:
        linguistic_norm.append(
            {
                "observation": _as_text(row.get("observation")),
                "why_it_matters": _as_text(row.get("why_it_matters")),
            }
        )

    historical = _parse_insight_list(
        obj.get("historical_background"), text_key="observation", max_items=3
    )
    historical_norm = [
        {"observation": _as_text(row.get("observation"))}
        for row in historical
        if _as_text(row.get("observation"))
    ]

    return LectionConnectionAnalysis(
        one_sentence=_as_text(obj.get("one_sentence")),
        connection_types=_parse_type_items(obj.get("connection_types")),
        key_links=_parse_key_links(obj.get("key_links")),
        linguistic_insights=linguistic_norm,
        historical_background=historical_norm,
        theological_gospel_link=theological,
        liturgical_role=liturgical,
        homiletical_uses=uses,
        connection_strength=strength,
        weak_connection_note=weak_note,
        alternative_lections=alts,
        overlap_note=_as_text(obj.get("overlap_note")),
        source_fingerprint=_as_text(obj.get("source_fingerprint")),
        passage_reference=_as_text(obj.get("passage_reference")),
        lection_reference=_as_text(obj.get("lection_reference")),
        generated_at=_as_text(obj.get("generated_at")),
        ok=bool(obj.get("ok", True)),
        error_message=_as_text(obj.get("error_message")),
        raw_response=raw_response,
    )


def analyze_lection_textus_link(
    *,
    passage: str = "",
    passage_text: str = "",
    lection_reference: str = "",
    lection_text: str = "",
    exegesis: str = "",
    original_text: str = "",
    history: str = "",
    theology: str = "",
    sermon_main_idea: str = "",
    text_main_idea: str = "",
    sermon_outline: Any = None,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> LectionConnectionAnalysis:
    """Lekció–textus kapcsolati elemzés futtatása."""
    fingerprint = build_lection_link_fingerprint(
        passage_reference=passage,
        passage_text=passage_text,
        lection_reference=lection_reference,
        lection_text=lection_text,
        sermon_main_idea=sermon_main_idea or text_main_idea,
        outline_signature=outline_signature_for_link(sermon_outline),
    )
    overlap = detect_passage_lection_overlap(passage, lection_reference)

    if not _is_present(passage):
        return LectionConnectionAnalysis(
            ok=False,
            error_message="Add meg az igehirdetési textus igehelyét.",
            source_fingerprint=fingerprint,
            passage_reference=_as_text(passage),
            lection_reference=_as_text(lection_reference),
            overlap_note=overlap,
        )
    if not _is_present(lection_reference):
        return LectionConnectionAnalysis(
            ok=False,
            error_message="Add meg a lekció igehelyét az elemzéshez.",
            source_fingerprint=fingerprint,
            passage_reference=_as_text(passage),
            lection_reference=_as_text(lection_reference),
            overlap_note=overlap,
        )
    if generate_fn is None:
        return LectionConnectionAnalysis(
            ok=False,
            error_message="Az elemzés most nem futtatható (nincs generáló).",
            source_fingerprint=fingerprint,
            passage_reference=_as_text(passage),
            lection_reference=_as_text(lection_reference),
            overlap_note=overlap,
        )

    prompt = build_lection_link_prompt(
        passage=passage,
        passage_text=passage_text,
        lection_reference=lection_reference,
        lection_text=lection_text,
        exegesis=exegesis,
        original_text=original_text,
        history=history,
        theology=theology,
        sermon_main_idea=sermon_main_idea,
        text_main_idea=text_main_idea,
        sermon_outline=sermon_outline,
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=temperature)
    except Exception as exc:  # noqa: BLE001 — UI-barát hiba
        return LectionConnectionAnalysis(
            ok=False,
            error_message=(
                "A kapcsolati elemzés most nem készíthető el. "
                "Próbáld újra, vagy ellenőrizd a kapcsolatot."
            ),
            source_fingerprint=fingerprint,
            passage_reference=_as_text(passage),
            lection_reference=_as_text(lection_reference),
            overlap_note=overlap,
            raw_response=str(exc),
        )

    if _is_api_error_text(raw):
        return LectionConnectionAnalysis(
            ok=False,
            error_message=(
                "A kapcsolati elemzés most nem készíthető el. "
                "Próbáld újra, vagy ellenőrizd a kapcsolatot."
            ),
            source_fingerprint=fingerprint,
            passage_reference=_as_text(passage),
            lection_reference=_as_text(lection_reference),
            overlap_note=overlap,
            raw_response=_as_text(raw),
        )

    try:
        obj = extract_json_object(raw)
    except Exception:
        obj = None
    if not isinstance(obj, dict):
        return LectionConnectionAnalysis(
            ok=False,
            error_message=(
                "A kapcsolati elemzés nem adott értelmezhető választ. Próbáld újra."
            ),
            source_fingerprint=fingerprint,
            passage_reference=_as_text(passage),
            lection_reference=_as_text(lection_reference),
            overlap_note=overlap,
            raw_response=_as_text(raw),
        )

    result = _parse_analysis_dict(obj, raw_response=_as_text(raw))
    result.source_fingerprint = fingerprint
    result.passage_reference = _as_text(passage)
    result.lection_reference = _as_text(lection_reference)
    result.generated_at = datetime.now().isoformat(timespec="seconds")
    result.ok = True
    result.error_message = ""
    if overlap and not result.overlap_note:
        result.overlap_note = overlap
    if not result.one_sentence and result.connection_types:
        first = result.connection_types[0]
        result.one_sentence = first.rationale or lection_link_type_label(first.type)
    if not result.one_sentence and not result.key_links:
        result.ok = False
        result.error_message = (
            "A kapcsolati elemzés nem adott értelmezhető választ. Próbáld újra."
        )
    return result


__all__ = [
    "WEAK_CONNECTION_MESSAGE",
    "LECTION_LINK_TYPES",
    "LECTION_LINK_TYPE_LABELS_HU",
    "LectionConnectionAnalysis",
    "LectionLinkTypeItem",
    "LectionKeyLink",
    "LectionLinkAlternative",
    "analyze_lection_textus_link",
    "before_after_label",
    "build_lection_link_fingerprint",
    "build_lection_link_prompt",
    "detect_passage_lection_overlap",
    "empty_lection_connection_analysis",
    "lection_connection_analysis_is_stale",
    "lection_link_type_label",
    "normalize_lection_connection_analysis",
    "normalize_lection_link_type",
    "outline_signature_for_link",
    "placement_label",
]
