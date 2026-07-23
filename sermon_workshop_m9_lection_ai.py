"""Igehirdetési műhely M9 — liturgiai lekciójavaslat MI.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
Újrafelhasználja az M7 lezárási kontextusépítőt (M4–M7 aggregátum).
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
A RÚF-szöveget nem rekonstruálja — csak igehelyet és indoklást ajánl.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ruf_bible_service import parse_bible_reference
from sermon_workshop_data import (
    normalize_lection_connection_type,
    normalize_lection_length_preference,
    normalize_lection_testament_preference,
    normalize_sermon_movements,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import (
    MISSING,
    _as_str_list,
    _as_text,
    _display,
    _is_api_error_text,
    _is_present,
)
from sermon_workshop_m7_closing_ai import build_closing_context

TAB_LECTION = "Lekciójavaslat"
DEFAULT_TEMPERATURE = 0.2
MAX_ALTERNATIVES = 3
LECTION_GENERATE_USER_ERROR = (
    "A lekciójavaslat most nem készíthető el. "
    "Próbáld újra, vagy ellenőrizd a kapcsolatot."
)

GenerateFn = Callable[..., str]


def _public_generate_error_message(exc: BaseException) -> str:
    """Felhasználói üzenet; nyers TypeError / váratlan kwargs ne jelenjen meg."""
    raw = str(exc)
    lower = raw.casefold()
    if (
        "unexpected keyword argument" in lower
        or "system_instruction" in lower
        or "got an unexpected keyword" in lower
    ):
        return LECTION_GENERATE_USER_ERROR
    return (raw[:280] if raw else LECTION_GENERATE_USER_ERROR)

LECTION_CONNECTION_TYPES = (
    "thematic",
    "canonical",
    "redemptive_historical",
    "preparatory",
    "contrast",
    "gospel_complement",
    "liturgical_echo",
)

LECTION_CONNECTION_TYPE_LABELS_HU: dict[str, str] = {
    "thematic": "Tematikus kapcsolat",
    "canonical": "Kánoni kapcsolat",
    "redemptive_historical": "Üdvtörténeti kapcsolat",
    "preparatory": "Előkészítő kapcsolat",
    "contrast": "Kontraszt",
    "gospel_complement": "Evangéliumi kiegészítés",
    "liturgical_echo": "Liturgiai visszhang",
}

LECTION_TESTAMENT_PREFERENCES = (
    "any",
    "old_testament",
    "psalm",
    "gospel",
    "new_testament",
)

LECTION_TESTAMENT_PREFERENCE_LABELS_HU: dict[str, str] = {
    "any": "Bármely bibliai rész",
    "old_testament": "Ószövetség",
    "psalm": "Zsoltár",
    "gospel": "Evangélium",
    "new_testament": "Újszövetség",
}

LECTION_LENGTH_PREFERENCES = ("short", "standard", "extended")

LECTION_LENGTH_PREFERENCE_LABELS_HU: dict[str, str] = {
    "short": "Rövidebb",
    "standard": "Átlagos",
    "extended": "Hosszabb",
}

_LIMITS_EXTRA = {
    "lection_prefs": 400,
    "lection_block": 2500,
    "sermon_outline_block": 1600,
}


def lection_connection_type_label(value: str) -> str:
    key = normalize_lection_connection_type(value)
    if not key:
        return ""
    return LECTION_CONNECTION_TYPE_LABELS_HU.get(key, key)


def lection_testament_preference_label(value: str) -> str:
    key = normalize_lection_testament_preference(value)
    return LECTION_TESTAMENT_PREFERENCE_LABELS_HU.get(key, key)


def lection_length_preference_label(value: str) -> str:
    key = normalize_lection_length_preference(value)
    return LECTION_LENGTH_PREFERENCE_LABELS_HU.get(key, key)


@dataclass
class LectionCandidate:
    reference: str = ""
    connection_type: str = ""
    rationale: str = ""
    liturgical_function: str = ""
    estimated_length: str = ""
    warnings: list[str] = field(default_factory=list)
    reference_valid: bool = False
    reference_error: str = ""
    normalized_reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "connection_type": self.connection_type,
            "rationale": self.rationale,
            "liturgical_function": self.liturgical_function,
            "estimated_length": self.estimated_length,
            "warnings": list(self.warnings),
            "reference_valid": self.reference_valid,
            "reference_error": self.reference_error,
            "normalized_reference": self.normalized_reference,
        }


@dataclass
class LectionSuggestionResult:
    recommended_lection: LectionCandidate = field(default_factory=LectionCandidate)
    alternative_lections: list[LectionCandidate] = field(default_factory=list)
    overall_reasoning: str = ""
    no_separate_lection_needed: bool = False
    no_lection_reason: str = ""
    basis: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_lection": self.recommended_lection.to_dict(),
            "alternative_lections": [a.to_dict() for a in self.alternative_lections],
            "overall_reasoning": self.overall_reasoning,
            "no_separate_lection_needed": self.no_separate_lection_needed,
            "no_lection_reason": self.no_lection_reason,
            "basis": list(self.basis),
            "missing_information": list(self.missing_information),
            "warnings": list(self.warnings),
            "ok": self.ok,
            "error_message": self.error_message,
        }

    def to_ui_block(self) -> dict[str, str]:
        rec = self.recommended_lection
        return {
            "reference": rec.reference,
            "connection_type": rec.connection_type,
            "function": rec.liturgical_function,
            "rationale": rec.rationale,
        }


@dataclass
class LectionAssessmentResult:
    overall_assessment: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    connection_type_assessment: str = ""
    length_assessment: str = ""
    liturgical_fit_assessment: str = ""
    suggested_reference: str = ""
    suggested_connection_type: str = ""
    revised_rationale: str = ""
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_assessment": self.overall_assessment,
            "strengths": list(self.strengths),
            "improvements": list(self.improvements),
            "connection_type_assessment": self.connection_type_assessment,
            "length_assessment": self.length_assessment,
            "liturgical_fit_assessment": self.liturgical_fit_assessment,
            "suggested_reference": self.suggested_reference,
            "suggested_connection_type": self.suggested_connection_type,
            "revised_rationale": self.revised_rationale,
            "warnings": list(self.warnings),
            "ok": self.ok,
            "error_message": self.error_message,
        }


def validate_lection_reference(reference: str) -> dict[str, Any]:
    """Igehely ellenőrzése a meglévő RÚF-parserrel; montázs elutasítása.

    Nem módosítja a parser szakmai logikáját — csak előszűr és burkolja.
    """
    raw = (reference or "").strip()
    if not raw:
        return {
            "ok": False,
            "error": "Üres igehely.",
            "normalized_reference": "",
            "requested_reference": "",
        }

    # Több külön szakasz / montázs jelek
    if ";" in raw or "\n" in raw:
        return {
            "ok": False,
            "error": (
                "Több külön szakasz egy mezőben nem fogadható el lekcióként. "
                "Adj meg egyetlen összefüggő igehelyet."
            ),
            "normalized_reference": "",
            "requested_reference": raw,
        }
    # „Jn 3,16 és Mt 5,3” jellegű összefűzés
    if re.search(r"\bés\b", raw, flags=re.IGNORECASE) and re.search(
        r"\d", raw
    ):
        # Csak akkor utasítsuk el, ha két könyvszerű token is látszik
        bookish = re.findall(
            r"(?:[1-5]\s*)?[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű.]{2,}",
            raw,
        )
        if len(bookish) >= 2:
            return {
                "ok": False,
                "error": (
                    "Több szakasz összefűzése nem érvényes lekcióhivatkozás. "
                    "Adj meg egyetlen összefüggő szakaszt."
                ),
                "normalized_reference": "",
                "requested_reference": raw,
            }

    try:
        parsed = parse_bible_reference(raw)
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "normalized_reference": "",
            "requested_reference": raw,
        }

    return {
        "ok": True,
        "error": "",
        "normalized_reference": parsed.normalized_reference,
        "requested_reference": raw,
        "single_chapter": bool(parsed.book.single_chapter),
        "book_abbr": parsed.book.abbr,
    }


def references_equivalent(a: str, b: str) -> bool:
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    va = validate_lection_reference(a)
    vb = validate_lection_reference(b)
    if va.get("ok") and vb.get("ok"):
        return va.get("normalized_reference") == vb.get("normalized_reference")
    return a.casefold() == b.casefold()


def _format_lection_prefs(
    *,
    testament_preference: str = "any",
    length_preference: str = "standard",
    lection_user_focus: str = "",
) -> str:
    lines = [
        f"Kívánt bibliai rész: {lection_testament_preference_label(testament_preference)}",
        f"Kívánt hossz: {lection_length_preference_label(length_preference)}",
    ]
    focus = _as_text(lection_user_focus)
    if focus:
        lines.append(f"Külön szempont: {focus}")
    return _display("\n".join(lines), max_chars=_LIMITS_EXTRA["lection_prefs"])


def _format_lection_block(lection: Any) -> str:
    block = lection if isinstance(lection, dict) else {}
    labels = (
        ("reference", "Lekció igehelye"),
        ("connection_type", "Kapcsolat típusa"),
        ("function", "A lekció funkciója"),
        ("rationale", "Rövid indoklás"),
        ("notes", "Saját megjegyzés"),
        ("testament_preference", "Kívánt bibliai rész"),
        ("length_preference", "Kívánt hossz"),
        ("user_focus", "Külön szempont"),
    )
    lines: list[str] = []
    for key, label in labels:
        val = _as_text(block.get(key))
        if not val:
            continue
        if key == "connection_type":
            val = lection_connection_type_label(val) or val
        elif key == "testament_preference":
            val = lection_testament_preference_label(val)
        elif key == "length_preference":
            val = lection_length_preference_label(val)
        lines.append(f"{label}: {val}")
    if not lines:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS_EXTRA["lection_block"])


def _format_sermon_outline_block(outline: Any) -> str:
    """Kompakt vázlatösszefoglaló a lekció MI-nek — ha van elkészült vázlat."""
    block = outline if isinstance(outline, dict) else {}
    if not block:
        return MISSING
    lines: list[str] = []
    for key, label in (
        ("main_idea", "Fő gondolat"),
        ("opening_direction", "Bevezetési irány"),
        ("listener_question", "Hallgatói kérdés"),
        ("central_tension", "Központi feszültség"),
        ("gospel_resolution", "Evangéliumi feloldás"),
    ):
        val = _as_text(block.get(key))
        if val:
            lines.append(f"{label}: {val}")
    movements = block.get("movements") if isinstance(block.get("movements"), list) else []
    for idx, mv in enumerate(movements[:6], start=1):
        if not isinstance(mv, dict):
            continue
        title = _as_text(mv.get("title"))
        core = _as_text(mv.get("core_content"))
        bit = " — ".join(x for x in (title, core) if x)
        if bit:
            lines.append(f"Mozgás {idx}: {bit}")
    closing = block.get("closing") if isinstance(block.get("closing"), dict) else {}
    final = _as_text(closing.get("final_insight"))
    if final:
        lines.append(f"Lezárás: {final}")
    if not lines:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS_EXTRA["sermon_outline_block"])


def build_lection_context(
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
    lection: Any = None,
    sermon_outline: Any = None,
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    testament_preference: str = "any",
    length_preference: str = "standard",
    lection_user_focus: str = "",
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
    pref_test = normalize_lection_testament_preference(testament_preference)
    pref_len = normalize_lection_length_preference(length_preference)
    live = lection if isinstance(lection, dict) else {}
    if live.get("testament_preference"):
        pref_test = normalize_lection_testament_preference(
            live.get("testament_preference")
        )
    if live.get("length_preference"):
        pref_len = normalize_lection_length_preference(live.get("length_preference"))
    focus = _as_text(lection_user_focus) or _as_text(live.get("user_focus"))
    ctx["lection_prefs"] = _format_lection_prefs(
        testament_preference=pref_test,
        length_preference=pref_len,
        lection_user_focus=focus,
    )
    ctx["lection_block"] = _format_lection_block(live)
    ctx["sermon_outline_block"] = _format_sermon_outline_block(sermon_outline)
    return ctx


def _has_usable_main_idea(
    *,
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
) -> bool:
    """Draft vagy approved fő gondolat — a státusz nem kötelező a javaslathoz."""
    del text_main_idea_status, sermon_main_idea_status
    return _is_present(text_main_idea) or _is_present(sermon_main_idea)


def _has_approved_main_idea(
    *,
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
) -> bool:
    text_ok = (
        text_main_idea_status.strip().casefold() == "approved"
        and _is_present(text_main_idea)
    )
    sermon_ok = (
        sermon_main_idea_status.strip().casefold() == "approved"
        and _is_present(sermon_main_idea)
    )
    return text_ok or sermon_ok


def _has_extra_basis(
    ctx: Mapping[str, str],
    *,
    approved_insights: Any = None,
    christ_centered_arc: Any = None,
    theology: str = "",
    sermon_path: Any = None,
    lection_user_focus: str = "",
) -> bool:
    if _is_present(ctx.get("passage_text", MISSING)):
        return True
    if _is_present(lection_user_focus):
        return True
    if _is_present(ctx.get("sermon_outline_block", MISSING)):
        return True
    if isinstance(approved_insights, list) and any(
        _as_text(x) for x in approved_insights
    ):
        return True
    if _is_present(ctx.get("approved_insights", MISSING)):
        return True
    arc = christ_centered_arc if isinstance(christ_centered_arc, dict) else {}
    if any(
        _is_present(arc.get(k))
        for k in (
            "divine_gracious_action",
            "christ_connection",
            "grace_enabled_response",
        )
    ):
        return True
    if _is_present(ctx.get("christ_arc_block", MISSING)):
        return True
    if _is_present(theology) or _is_present(ctx.get("theology", MISSING)):
        return True
    path = sermon_path if isinstance(sermon_path, dict) else {}
    if _is_present(path.get("destination")):
        return True
    if _is_present(ctx.get("sermon_path_block", MISSING)):
        return True
    if _is_present(ctx.get("listener_tension_block", MISSING)):
        return True
    if _is_present(ctx.get("human_condition_block", MISSING)):
        return True
    return False


def has_sufficient_lection_material(
    ctx: Mapping[str, str],
    *,
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    approved_insights: Any = None,
    christ_centered_arc: Any = None,
    theology: str = "",
    sermon_path: Any = None,
    lection_user_focus: str = "",
) -> bool:
    if not _is_present(ctx.get("passage", MISSING)):
        return False
    has_idea = _has_usable_main_idea(
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
    )
    has_focus = _is_present(lection_user_focus)
    has_outline = _is_present(ctx.get("sermon_outline_block", MISSING))
    if not (has_idea or has_focus or has_outline):
        return False
    return _has_extra_basis(
        ctx,
        approved_insights=approved_insights,
        christ_centered_arc=christ_centered_arc,
        theology=theology,
        sermon_path=sermon_path,
        lection_user_focus=lection_user_focus,
    ) or has_outline or has_focus


def _missing_lection_labels(
    ctx: Mapping[str, str],
    *,
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    approved_insights: Any = None,
    christ_centered_arc: Any = None,
    theology: str = "",
    sermon_path: Any = None,
    lection_user_focus: str = "",
) -> list[str]:
    missing: list[str] = []
    if not _is_present(ctx.get("passage", MISSING)):
        missing.append("alapigehely")
    has_idea = _has_usable_main_idea(
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
    )
    has_focus = _is_present(lection_user_focus)
    has_outline = _is_present(ctx.get("sermon_outline_block", MISSING))
    if not (has_idea or has_focus or has_outline):
        missing.append(
            "textus- vagy igehirdetési fő gondolat, saját lekciószempont, "
            "vagy elkészült vázlat"
        )
    if not (
        _has_extra_basis(
            ctx,
            approved_insights=approved_insights,
            christ_centered_arc=christ_centered_arc,
            theology=theology,
            sermon_path=sermon_path,
            lection_user_focus=lection_user_focus,
        )
        or has_outline
        or has_focus
    ):
        missing.append(
            "legalább egy további érdemi alap "
            "(passage_text, felismerés, evangéliumi ív, teológia, "
            "saját szempont vagy vázlat)"
        )
    return missing


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        if key.startswith("_"):
            continue
        out = out.replace("{{" + key + "}}", value)
    return out


_SUGGEST_TEMPLATE = """\
Feladatod: LITURGIAI LEKCIÓ javaslata az igehirdetéshez.

A lekció NEM keresztutalás és NEM „kapcsolódó igeversek” lista.

### Keresztutalás
Egy vers vagy rövid rész, amely egy állítást alátámaszt vagy kiegészít.

### Lekció
Összefüggő, önmagában is felolvasható bibliai szakasz, amelynek saját
gondolatmenete, jelenete vagy teológiai íve van. Liturgikusan felolvasható
hosszúságú; teológiailag kapcsolódik az alapigéhez; előkészíti, elmélyíti
vagy tágabb bibliai összefüggésbe helyezi az igehirdetés üzenetét.

## Tilos lekcióként ajánlani
- elszigetelt félmondatot vagy egyetlen bizonyító verset;
- egymástól távoli versekből összeállított montázst;
- több külön könyvből összefűzött idézetlistát;
- összefüggéstelen versválogatást;
- nem létező bibliai szakaszt vagy hibás vershivatkozást;
- kizárólag kulcsszó-egyezésre épülő ajánlást;
- erőltetett krisztologizálást vagy megalapozatlan tipológiát;
- a kapcsolat túlzását („ugyanazt mondja”, ha csak távoli a kapcsolat);
- indoklás nélkül túl hosszú, liturgikusan nehezen felolvasható szakaszt;
- a teljes Bibliát vagy nagy könyvrészt;
- az alaptextus automatikus megismétlését lekcióként;
- kitalált bibliai idézetet;
- a RÚF-szöveg rekonstruálását (csak hivatkozást és indoklást adj).

Elfogadható eredmény az is, hogy nincs szükség külön lekcióra
(`no_separate_lection_needed`: true), ha az alaptextus önmagában megfelelő
bibliaolvasási szakasz, vagy további liturgiai / gyülekezeti szempont kell.

## Kapcsolattípusok (egyik sem „jobb” általánosságban)
thematic | canonical | redemptive_historical | preparatory | contrast |
gospel_complement | liturgical_echo

Adj egy elsődlegesen ajánlott lekciót és 2–3 eltérő irányú alternatívát
(nem ugyanannak a témának közeli verseit). Nem kötelező minden kategóriából.

A `reference` legyen EGYETLEN összefüggő szakasz, magyar igehely-formában
(pl. Fil 2,1–16 vagy Zsolt 23 vagy Júd 17–20), magyarázó szöveg és
pontosvessző nélküli több szakasz nélkül.

## Felhasználói lekcióbeállítások
{{lection_prefs}}

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

Alkalmazási irányok:
{{applications_block}}

Lezárási terv:
{{closing_block}}

Elkészült igehirdetési vázlat (ha van):
{{sermon_outline_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma (csak ezt add vissza)

{
  "recommended_lection": {
    "reference": "",
    "connection_type": "thematic|canonical|redemptive_historical|preparatory|contrast|gospel_complement|liturgical_echo",
    "rationale": "",
    "liturgical_function": "",
    "estimated_length": "",
    "warnings": []
  },
  "alternative_lections": [
    {
      "reference": "",
      "connection_type": "",
      "rationale": "",
      "liturgical_function": "",
      "estimated_length": "",
      "warnings": []
    }
  ],
  "overall_reasoning": "",
  "no_separate_lection_needed": false,
  "no_lection_reason": "",
  "basis": [],
  "missing_information": []
}

Az `alternative_lections` listában adj 2–3 valódi alternatívát
(legfeljebb 3 elem). Ha nincs különálló lekció indokolt, hagyd üresen,
és állítsd `no_separate_lection_needed`-et true-ra.
"""


_ASSESS_TEMPLATE = """\
Feladatod: a prédikátor SAJÁT lekcióválasztásának értékelése.

Vizsgáld:
- valóban összefüggő szakasz-e (nem bizonyító vers / montázs);
- megfelelő hosszúságú-e a liturgiai célhoz;
- kapcsolódik-e az alaptextushoz és az igehirdetés fő gondolatához;
- milyen típusú a kapcsolat;
- előkészíti vagy elmélyíti-e az igehirdetést;
- nem vezet-e más, versengő fő témát az istentiszteletbe;
- felolvasható-e önmagában;
- szükséges-e rövidebb vagy hosszabb szakaszhatár;
- nem ismétli-e szükségtelenül ugyanazt, mint az alaptextus.

A `suggested_*` és `revised_rationale` mezők CSAK javaslatok —
ne írd felül automatikusan a felhasználó választását.
Ne rekonstruáld a RÚF-szöveget.

## Felhasználói lekcióbeállítások
{{lection_prefs}}

## Műhelyanyag

Igehely: {{passage}}
Fordítás: {{bible_translation}}

Bibliai szöveg:
{{passage_text}}

Jóváhagyott textusfőgondolat: {{text_main_idea}}
Jóváhagyott igehirdetési fő gondolat: {{sermon_main_idea}}
Kifejtés: {{sermon_expanded_summary}}

Evangéliumi ív:
{{christ_arc_block}}

Az igehirdetés útja:
{{sermon_path_block}}

Prédikációs mozgások:
{{movements_block}}

Alkalmazási irányok:
{{applications_block}}

A prédikátor lekciója:
{{lection_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma

{
  "overall_assessment": "",
  "strengths": [],
  "improvements": [],
  "connection_type_assessment": "",
  "length_assessment": "",
  "liturgical_fit_assessment": "",
  "suggested_reference": "",
  "suggested_connection_type": "",
  "revised_rationale": "",
  "warnings": []
}
"""


def build_lection_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_SUGGEST_TEMPLATE, ctx)


def build_lection_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_ASSESS_TEMPLATE, ctx)


def _call_lection_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    tab_label: str,
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
            tab_label=tab_label,
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


def _enrich_candidate(raw: Any) -> LectionCandidate:
    item = raw if isinstance(raw, dict) else {}
    reference = _as_text(item.get("reference"))
    connection = normalize_lection_connection_type(item.get("connection_type"))
    warnings = _as_str_list(item.get("warnings"))
    candidate = LectionCandidate(
        reference=reference,
        connection_type=connection,
        rationale=_as_text(item.get("rationale")),
        liturgical_function=_as_text(
            item.get("liturgical_function") or item.get("function")
        ),
        estimated_length=_as_text(item.get("estimated_length")),
        warnings=warnings,
    )
    if reference:
        validation = validate_lection_reference(reference)
        candidate.reference_valid = bool(validation.get("ok"))
        candidate.reference_error = str(validation.get("error") or "")
        candidate.normalized_reference = str(
            validation.get("normalized_reference") or ""
        )
        if not candidate.reference_valid and candidate.reference_error:
            if candidate.reference_error not in candidate.warnings:
                candidate.warnings.append(candidate.reference_error)
    return candidate


def fallback_lection_suggestion(
    *,
    reasoning: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    ok: bool = True,
    no_separate: bool = False,
    no_reason: str = "",
    raw_response: str = "",
) -> LectionSuggestionResult:
    return LectionSuggestionResult(
        overall_reasoning=reasoning,
        no_separate_lection_needed=no_separate,
        no_lection_reason=no_reason,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response or "",
    )


def parse_lection_suggestion_response(raw: str) -> LectionSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_lection_suggestion(
            reasoning="Az API hibát jelzett.",
            warnings=["API hiba a lekciójavaslat során."],
            error_message=_as_text(raw)[:280],
            ok=False,
        )
    try:
        obj = extract_json_object(raw)
    except Exception:
        return fallback_lection_suggestion(
            reasoning="A válasz nem volt érvényes JSON.",
            warnings=["Hibás JSON — üres javaslatok biztonsági alapértékekkel."],
            error_message="Hibás JSON a lekciójavaslatban.",
            ok=False,
            raw_response=raw or "",
        )
    if not isinstance(obj, dict):
        return fallback_lection_suggestion(
            reasoning="A JSON nem objektum.",
            warnings=["Érvénytelen JSON-struktúra."],
            error_message="Érvénytelen JSON-struktúra.",
            ok=False,
            raw_response=raw or "",
        )

    recommended = _enrich_candidate(obj.get("recommended_lection"))
    alts_raw = obj.get("alternative_lections")
    alternatives: list[LectionCandidate] = []
    if isinstance(alts_raw, list):
        for item in alts_raw:
            if len(alternatives) >= MAX_ALTERNATIVES:
                break
            cand = _enrich_candidate(item)
            if cand.reference or cand.rationale:
                alternatives.append(cand)

    no_sep = bool(obj.get("no_separate_lection_needed"))
    return LectionSuggestionResult(
        recommended_lection=recommended,
        alternative_lections=alternatives,
        overall_reasoning=_as_text(obj.get("overall_reasoning")),
        no_separate_lection_needed=no_sep,
        no_lection_reason=_as_text(obj.get("no_lection_reason")),
        basis=_as_str_list(obj.get("basis")),
        missing_information=_as_str_list(obj.get("missing_information")),
        warnings=_as_str_list(obj.get("warnings")),
        ok=True,
        raw_response=raw or "",
    )


def parse_lection_assessment_response(raw: str) -> LectionAssessmentResult:
    if _is_api_error_text(raw):
        return LectionAssessmentResult(
            overall_assessment="Az API hibát jelzett.",
            warnings=["API hiba a lekcióértékelés során."],
            ok=False,
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
        )
    try:
        obj = extract_json_object(raw)
    except Exception:
        return LectionAssessmentResult(
            overall_assessment="A válasz nem volt érvényes JSON.",
            warnings=["Hibás JSON — üres értékelés biztonsági alapértékekkel."],
            ok=False,
            error_message="Hibás JSON a lekcióértékelésben.",
            raw_response=raw or "",
        )
    if not isinstance(obj, dict):
        return LectionAssessmentResult(
            overall_assessment="A JSON nem objektum.",
            warnings=["Érvénytelen JSON-struktúra."],
            ok=False,
            error_message="Érvénytelen JSON-struktúra.",
            raw_response=raw or "",
        )

    suggested_ref = _as_text(obj.get("suggested_reference"))
    suggested_conn = normalize_lection_connection_type(
        obj.get("suggested_connection_type")
    )
    warnings = _as_str_list(obj.get("warnings"))
    if suggested_ref:
        validation = validate_lection_reference(suggested_ref)
        if not validation.get("ok"):
            err = str(validation.get("error") or "Hibás javasolt igehely.")
            if err not in warnings:
                warnings.append(err)

    return LectionAssessmentResult(
        overall_assessment=_as_text(obj.get("overall_assessment")),
        strengths=_as_str_list(obj.get("strengths")),
        improvements=_as_str_list(obj.get("improvements")),
        connection_type_assessment=_as_text(obj.get("connection_type_assessment")),
        length_assessment=_as_text(obj.get("length_assessment")),
        liturgical_fit_assessment=_as_text(obj.get("liturgical_fit_assessment")),
        suggested_reference=suggested_ref,
        suggested_connection_type=suggested_conn,
        revised_rationale=_as_text(obj.get("revised_rationale")),
        warnings=warnings,
        ok=True,
        raw_response=raw or "",
    )


def suggest_lections(
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
    lection: Any = None,
    sermon_outline: Any = None,
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    testament_preference: str = "any",
    length_preference: str = "standard",
    lection_user_focus: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> LectionSuggestionResult:
    ctx = build_lection_context(
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
        lection=lection,
        sermon_outline=sermon_outline,
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
        testament_preference=testament_preference,
        length_preference=length_preference,
        lection_user_focus=lection_user_focus,
    )
    missing = _missing_lection_labels(
        ctx,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        approved_insights=approved_insights,
        christ_centered_arc=christ_centered_arc,
        theology=theology,
        sermon_path=sermon_path,
        lection_user_focus=lection_user_focus,
    )
    if not _is_present(ctx["passage"]):
        return fallback_lection_suggestion(
            reasoning="Nincs megadva alapigehely; javaslat nem indítható.",
            warnings=["Az alapigehely (passage) hiányzik."],
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_lection_material(
        ctx,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        approved_insights=approved_insights,
        christ_centered_arc=christ_centered_arc,
        theology=theology,
        sermon_path=sermon_path,
        lection_user_focus=lection_user_focus,
    ):
        only_passage = not (
            _has_usable_main_idea(
                text_main_idea=text_main_idea,
                text_main_idea_status=text_main_idea_status,
                sermon_main_idea=sermon_main_idea,
                sermon_main_idea_status=sermon_main_idea_status,
            )
            or _is_present(lection_user_focus)
            or _is_present(ctx.get("sermon_outline_block", MISSING))
        )
        reason = (
            "Csak az igehely áll rendelkezésre — adj meg fő gondolatot, "
            "saját szempontot, vagy állíts össze vázlatot a felelős javaslathoz."
            if only_passage
            else (
                "Nincs elegendő műhelyanyag a felelős lekciójavaslathoz. "
                "Tölts ki még egy-két szakaszt, vagy írj rövid saját szempontot."
            )
        )
        return fallback_lection_suggestion(
            reasoning=reason,
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres ajánlások.",
                reason,
            ],
            missing=missing,
            error_message=reason,
            ok=False,
        )
    if generate_fn is None:
        return fallback_lection_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_lection_suggest_prompt(ctx)
    try:
        raw = _call_lection_generate(
            generate_fn,
            prompt,
            tab_label=TAB_LECTION,
            temperature=temperature,
        )
    except Exception as exc:
        return fallback_lection_suggestion(
            reasoning="A Gemini-hívás sikertelen volt.",
            warnings=[f"Generálási hiba: {exc}"],
            missing=missing,
            error_message=_public_generate_error_message(exc),
            ok=False,
        )
    result = parse_lection_suggestion_response(raw)
    if result.missing_information is None:
        result.missing_information = []
    for item in missing:
        if item not in result.missing_information:
            result.missing_information.append(item)
    if result.ok and _is_present(ctx.get("passage_text")):
        result.warnings = [
            w
            for w in result.warnings
            if "passage_text" not in w.casefold()
        ]
        result.missing_information = [
            m
            for m in result.missing_information
            if "passage_text" not in m.casefold()
        ]
    return result


def assess_lection(
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
    lection: Any = None,
    sermon_outline: Any = None,
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    testament_preference: str = "any",
    length_preference: str = "standard",
    lection_user_focus: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> LectionAssessmentResult:
    live = lection if isinstance(lection, dict) else {}
    if not _as_text(live.get("reference")):
        return LectionAssessmentResult(
            overall_assessment=(
                "Nincs megadva saját lekcióigehely az értékeléshez."
            ),
            warnings=["Add meg a lekció igehelyét az értékelés előtt."],
            ok=False,
            error_message="Hiányzó lekcióigehely.",
        )
    ctx = build_lection_context(
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
        lection=lection,
        sermon_outline=sermon_outline,
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
        testament_preference=testament_preference,
        length_preference=length_preference,
        lection_user_focus=lection_user_focus,
    )
    if generate_fn is None:
        return LectionAssessmentResult(
            overall_assessment="Nincs bekötött Gemini-hívó függvény.",
            warnings=["generate_fn nélkül nem indítható értékelés."],
            ok=False,
            error_message="Hiányzó generate_fn.",
        )
    prompt = build_lection_assess_prompt(ctx)
    try:
        raw = _call_lection_generate(
            generate_fn,
            prompt,
            tab_label=TAB_LECTION,
            temperature=temperature,
        )
    except Exception as exc:
        return LectionAssessmentResult(
            overall_assessment="A Gemini-hívás sikertelen volt.",
            warnings=[f"Generálási hiba: {exc}"],
            ok=False,
            error_message=_public_generate_error_message(exc),
        )
    return parse_lection_assessment_response(raw)


def _gen_factory(payload: str) -> GenerateFn:
    def _fn(*_a: Any, **_k: Any) -> str:
        return payload

    return _fn


def _self_check() -> list[str]:
    errors: list[str] = []

    # I: hibás / montázs hivatkozás
    bad = validate_lection_reference("Jn 3,16; Mt 5,3")
    if bad.get("ok"):
        errors.append("I: multiline montage should fail")
    good = validate_lection_reference("Fil 2,1–16")
    if not good.get("ok"):
        errors.append(f"I: Fil 2,1–16 should parse: {good.get('error')}")
    # J: egyfejezetes
    jude = validate_lection_reference("Júd 17–20")
    if not jude.get("ok"):
        errors.append(f"J: Júd 17–20 should parse: {jude.get('error')}")

    base_kw = {
        "passage": "Fil 2,5–11",
        "passage_text": "Az az indulat legyen bennetek…",
        "bible_translation": "RÚF 2014",
        "text_main_idea": "Krisztus alázata a közösség mintája.",
        "text_main_idea_status": "approved",
        "sermon_main_idea": "A kegyelem alázatra hív.",
        "sermon_main_idea_status": "approved",
        "sermon_expanded_summary": "A közösség Krisztus útját követi.",
        "approved_insights": ["Az alázat nem gyengeség."],
        "christ_centered_arc": {
            "divine_gracious_action": "Krisztus megalázta magát",
            "christ_connection": "Fil 2 himnusz",
            "christ_connection_type": "direct",
            "grace_enabled_response": "egymás szolgálata",
        },
        "sermon_path": {
            "type": "text_following",
            "destination": "Közösségi alázat Krisztusban",
            "starting_point": "Verseny a dicsőségért",
            "reason": "A himnusz íve",
        },
        "sermon_movements": normalize_sermon_movements(
            [
                {"title": "Nyitás", "core_content": "A"},
                {"title": "Mélyítés", "core_content": "B"},
                {"title": "Megérkezés", "core_content": "C"},
            ]
        ),
        "applications": [
            {
                "application": "Szolgálat a közösségben",
                "scope": "community",
                "gospel_basis": "Krisztus alázata",
                "concreteness": "medium",
                "placement": "closing",
                "movement_id": "",
                "pastoral_caution": "",
            }
        ],
        "closing": {
            "type": "gospel_assurance",
            "final_discovery": "Krisztus útja a mi utunk",
            "hope": "Ő felemel",
            "tone": "hopeful",
        },
        "theology": "Krisztológia és közösség.",
    }

    suggest_json = """\
{
  "recommended_lection": {
    "reference": "Ézs 53,1–12",
    "connection_type": "redemptive_historical",
    "rationale": "Az Ószövetség szenvedő szolgája tágabb összefüggésbe helyezi a himnuszt.",
    "liturgical_function": "Előkészíti a Krisztus-út hallását.",
    "estimated_length": "közepes (12 vers)",
    "warnings": []
  },
  "alternative_lections": [
    {
      "reference": "Jn 13,1–17",
      "connection_type": "gospel_complement",
      "rationale": "Jézus lábmosása evangéliumi kiegészítés az alázathoz.",
      "liturgical_function": "Evangéliumi fényt ad.",
      "estimated_length": "közepes",
      "warnings": []
    },
    {
      "reference": "Zsolt 22,2–32",
      "connection_type": "liturgical_echo",
      "rationale": "Imádságos visszhang a szenvedés és bizalom között.",
      "liturgical_function": "Liturgiai visszhang.",
      "estimated_length": "hosszabb",
      "warnings": ["Ünnepi liturgián rövidíthető."]
    },
    {
      "reference": "Róm 12,1–8",
      "connection_type": "thematic",
      "rationale": "A test közösségi szolgálata tematikus párhuzam.",
      "liturgical_function": "Közösségi alkalmazás előkészítése.",
      "estimated_length": "közepes",
      "warnings": []
    }
  ],
  "overall_reasoning": "Az ajánlott Ószövetségi szakasz üdvtörténeti hátteret ad.",
  "no_separate_lection_needed": false,
  "no_lection_reason": "",
  "basis": ["jóváhagyott fő gondolat", "evangéliumi ív"],
  "missing_information": []
}
"""
    ra = suggest_lections(generate_fn=_gen_factory(suggest_json), **base_kw)
    if not ra.ok or not ra.recommended_lection.reference_valid:
        errors.append("A: suggest OT lection failed validation")
    if ra.recommended_lection.connection_type != "redemptive_historical":
        errors.append("A: expected redemptive_historical")
    if len(ra.alternative_lections) != 3:
        errors.append("A: expected 3 alternatives")

    # B: OT text → gospel (not forced — just parse)
    suggest_b = suggest_json.replace("Ézs 53,1–12", "Mk 10,32–45").replace(
        "redemptive_historical", "gospel_complement"
    )
    rb = suggest_lections(
        generate_fn=_gen_factory(suggest_b),
        **{
            **base_kw,
            "passage": "Ézs 52,13–53,12",
            "passage_text": "Íme, sikerrel jár az én szolgám…",
        },
    )
    if rb.recommended_lection.connection_type != "gospel_complement":
        errors.append("B: gospel complement type")

    # C: psalm liturgical echo — covered in alternatives
    if not any(
        a.connection_type == "liturgical_echo" for a in ra.alternative_lections
    ):
        errors.append("C: liturgical_echo alternative missing")

    # D: thematic — covered
    if not any(a.connection_type == "thematic" for a in ra.alternative_lections):
        errors.append("D: thematic alternative missing")

    # E: contrast
    suggest_e = """\
{
  "recommended_lection": {
    "reference": "Lk 18,9–14",
    "connection_type": "contrast",
    "rationale": "A farizeus és a vámszedő kontrasztja kiemeli az alázatot.",
    "liturgical_function": "Kontraszttal tisztítja a hallást.",
    "estimated_length": "rövid",
    "warnings": []
  },
  "alternative_lections": [],
  "overall_reasoning": "A különbség segít hallani a himnuszt.",
  "no_separate_lection_needed": false,
  "no_lection_reason": "",
  "basis": ["fő gondolat"],
  "missing_information": []
}
"""
    re_ = suggest_lections(generate_fn=_gen_factory(suggest_e), **base_kw)
    if re_.recommended_lection.connection_type != "contrast":
        errors.append("E: contrast type")
    if "kontraszt" not in re_.recommended_lection.rationale.casefold() and (
        "különbség" not in re_.recommended_lection.rationale.casefold()
    ):
        # still ok if wording differs
        pass

    # F: single proof verse assessment
    assess_f = """\
{
  "overall_assessment": "Ez inkább bizonyító vers, nem felolvasható lekció.",
  "strengths": [],
  "improvements": ["Válassz összefüggő szakaszt."],
  "connection_type_assessment": "Túl szűk.",
  "length_assessment": "Egyetlen vers nem megfelelő lekcióhossz.",
  "liturgical_fit_assessment": "Nem önálló felolvasás.",
  "suggested_reference": "Jn 3,1–21",
  "suggested_connection_type": "gospel_complement",
  "revised_rationale": "A Nikodémus-jelenet összefüggő szakasz.",
  "warnings": ["Nem megfelelő lekció: izolált bizonyító vers."]
}
"""
    rf = assess_lection(
        generate_fn=_gen_factory(assess_f),
        **base_kw,
        lection={"reference": "Jn 3,16", "rationale": "Isten szeretete"},
    )
    if not rf.ok:
        errors.append("F: assess should ok")
    if "bizonyító" not in rf.overall_assessment.casefold() and not any(
        "bizonyító" in w.casefold() for w in rf.warnings
    ):
        errors.append("F: should flag proof verse")

    # G: too long
    assess_g = """\
{
  "overall_assessment": "A szakasz liturgikusan túl hosszú.",
  "strengths": ["Erős kánoni kapcsolat."],
  "improvements": ["Rövidebb természetes egységet válassz."],
  "connection_type_assessment": "canonical",
  "length_assessment": "Túl hosszú ünnepi liturgiához.",
  "liturgical_fit_assessment": "Nehéz felolvasni egyben.",
  "suggested_reference": "Róm 8,31–39",
  "suggested_connection_type": "canonical",
  "revised_rationale": "A rövidebb egység megőrzi a gondolatívet.",
  "warnings": ["Túl hosszú szakasz."]
}
"""
    rg = assess_lection(
        generate_fn=_gen_factory(assess_g),
        **base_kw,
        lection={"reference": "Róm 1–8", "rationale": "teljes levélrész"},
    )
    if "hossz" not in rg.length_assessment.casefold() and not any(
        "hossz" in w.casefold() for w in rg.warnings
    ):
        errors.append("G: should warn long section")

    # H: natural unit — assessment suggests not mechanical cut
    assess_h = """\
{
  "overall_assessment": "Természetes egység, ne rövidítsd mechanikusan.",
  "strengths": ["Összefüggő jelenet."],
  "improvements": [],
  "connection_type_assessment": "thematic",
  "length_assessment": "Megfelelő, a szakasz természetes határai fontosabbak.",
  "liturgical_fit_assessment": "Felolvasható.",
  "suggested_reference": "",
  "suggested_connection_type": "",
  "revised_rationale": "",
  "warnings": []
}
"""
    rh = assess_lection(
        generate_fn=_gen_factory(assess_h),
        **base_kw,
        lection={"reference": "Lk 15,11–32", "rationale": "tékozló fiú"},
    )
    if "természetes" not in rh.length_assessment.casefold() and (
        "mechanik" not in rh.overall_assessment.casefold()
    ):
        errors.append("H: natural unit wording")

    # I: invalid AI reference
    suggest_i = """\
{
  "recommended_lection": {
    "reference": "XYZ 99,1–5",
    "connection_type": "thematic",
    "rationale": "teszt",
    "liturgical_function": "teszt",
    "estimated_length": "rövid",
    "warnings": []
  },
  "alternative_lections": [],
  "overall_reasoning": "",
  "no_separate_lection_needed": false,
  "no_lection_reason": "",
  "basis": [],
  "missing_information": []
}
"""
    ri = suggest_lections(generate_fn=_gen_factory(suggest_i), **base_kw)
    if ri.recommended_lection.reference_valid:
        errors.append("I: invalid book should be invalid")

    # K: adopt ≠ approve — covered in UI; here to_ui_block only fills draft fields
    ui = ra.to_ui_block()
    if "status" in ui or ui.get("reference") != "Ézs 53,1–12":
        if ui.get("reference") != "Ézs 53,1–12":
            errors.append("K: to_ui_block reference")

    # O: assessment does not overwrite — suggested fields separate
    if rf.suggested_reference and rf.suggested_reference == "Jn 3,16":
        errors.append("O: should suggest different ref")

    # insufficient: only passage
    insuff = suggest_lections(
        generate_fn=_gen_factory(suggest_json),
        passage="Fil 2,5–11",
        skip_api_if_insufficient=True,
    )
    if insuff.recommended_lection.reference:
        errors.append("9: insufficient should not invent refs")
    if insuff.ok:
        errors.append("9: insufficient must be ok=False (no false success)")
    if not insuff.missing_information:
        errors.append("9: should list missing info")

    # P: old project empty lection normalize via candidate empty
    empty = _enrich_candidate({})
    if empty.reference_valid:
        errors.append("P: empty candidate should not be valid")

    # bad JSON
    bad_json = suggest_lections(
        generate_fn=_gen_factory("not json {{{"),
        **base_kw,
    )
    if bad_json.ok:
        errors.append("JSON: bad json should not be ok")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon_workshop_m9_lection_ai self-check OK")


__all__ = [
    "TAB_LECTION",
    "LECTION_CONNECTION_TYPES",
    "LECTION_CONNECTION_TYPE_LABELS_HU",
    "LECTION_TESTAMENT_PREFERENCES",
    "LECTION_TESTAMENT_PREFERENCE_LABELS_HU",
    "LECTION_LENGTH_PREFERENCES",
    "LECTION_LENGTH_PREFERENCE_LABELS_HU",
    "LectionCandidate",
    "LectionSuggestionResult",
    "LectionAssessmentResult",
    "validate_lection_reference",
    "references_equivalent",
    "lection_connection_type_label",
    "lection_testament_preference_label",
    "lection_length_preference_label",
    "normalize_lection_connection_type",
    "normalize_lection_testament_preference",
    "normalize_lection_length_preference",
    "build_lection_context",
    "has_sufficient_lection_material",
    "build_lection_suggest_prompt",
    "build_lection_assess_prompt",
    "suggest_lections",
    "assess_lection",
    "parse_lection_suggestion_response",
    "parse_lection_assessment_response",
]
