"""Igehirdetési műhely M7 — képek, illusztrációk és alkalmazás MI.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
Újrafelhasználja az M6 kontextusépítőt.
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sermon_workshop_data import (
    empty_application,
    empty_illustration,
    empty_textual_image,
    normalize_application,
    normalize_applications,
    normalize_illustration,
    normalize_illustrations,
    normalize_sermon_movements,
    normalize_textual_image,
    normalize_textual_images,
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
from sermon_workshop_m6_ai import build_sermon_path_context

TAB_SUGGEST = "Képek és alkalmazások — javaslat"
TAB_ASSESS = "Képek és alkalmazások — értékelés"
DEFAULT_TEMPERATURE = 0.15

GenerateFn = Callable[..., str]

IMAGE_FUNCTIONS = (
    "open",
    "clarify",
    "deepen",
    "create_tension",
    "carry_transition",
    "support_gospel_turn",
    "support_memory",
)

IMAGE_FUNCTION_LABELS_HU: dict[str, str] = {
    "open": "Megnyitás",
    "clarify": "Tisztázás",
    "deepen": "Elmélyítés",
    "create_tension": "Feszültség érzékeltetése",
    "carry_transition": "Átmenet hordozása",
    "support_gospel_turn": "Evangéliumi fordulat támogatása",
    "support_memory": "Megjegyezhetőség segítése",
}

ILLUSTRATION_FUNCTIONS = (
    "bridge",
    "clarify",
    "embody",
    "contrast",
    "intensify",
    "release_tension",
    "support_memory",
)

ILLUSTRATION_FUNCTION_LABELS_HU: dict[str, str] = {
    "bridge": "Kapcsolódás teremtése",
    "clarify": "Tisztázás",
    "embody": "Megtestesítés",
    "contrast": "Kontraszt",
    "intensify": "Elmélyítés",
    "release_tension": "Feszültség oldása",
    "support_memory": "Megjegyezhetőség segítése",
}

ILLUSTRATION_SOURCES = (
    "own_experience",
    "known_story",
    "literature_art",
    "everyday_observation",
    "text_workshop_import",
    "needs_verification",
)

ILLUSTRATION_SOURCE_LABELS_HU: dict[str, str] = {
    "own_experience": "Saját tapasztalat",
    "known_story": "Ismert történet vagy esemény",
    "literature_art": "Irodalom / művészet",
    "everyday_observation": "Hétköznapi megfigyelés",
    "text_workshop_import": "Textusműhelyből átvett javaslat",
    "needs_verification": "Még ellenőrizendő",
}

APPLICATION_SCOPES = (
    "personal",
    "relational",
    "congregational",
    "communal",
    "public",
    "pastoral",
)

APPLICATION_SCOPE_LABELS_HU: dict[str, str] = {
    "personal": "Személyes",
    "relational": "Kapcsolati",
    "congregational": "Gyülekezeti",
    "communal": "Közösségi",
    "public": "Társadalmi",
    "pastoral": "Lelkigondozói",
}

PLACEMENT_KINDS = (
    "general",
    "introduction",
    "movement",
    "gospel_turn",
    "toward_arrival",
)

PLACEMENT_KIND_LABELS_HU: dict[str, str] = {
    "general": "Általános",
    "introduction": "Bevezetés",
    "movement": "Kiválasztott mozgás",
    "gospel_turn": "Evangéliumi fordulat",
    "toward_arrival": "Megérkezés felé",
}

MAX_TEXTUAL_IMAGES = 3
MAX_AI_TEXTUAL_IMAGES = 2
MAX_ILLUSTRATIONS = 3
MAX_AI_ILLUSTRATIONS = 2
MAX_APPLICATIONS = 4
MIN_AI_APPLICATIONS = 2

M7_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű, református asszisztense vagy.
Csak a megadott műhelyanyagból dolgozz. Ne találj ki személyes történetet,
történelmi eseményt, idézetet vagy hallgatói demográfiát.
Válaszod KIZÁRÓLAG érvényes JSON legyen.\
"""

_LIMITS_EXTRA = {
    "images_block": 3000,
    "illustrations_block": 3000,
    "applications_block": 3500,
    "workshop_illustrations": 2800,
    "workshop_actualization": 2800,
}


@dataclass
class EnrichmentSuggestionResult:
    recommended_textual_images: list[dict[str, str]] = field(default_factory=list)
    recommended_illustrations: list[dict[str, str]] = field(default_factory=list)
    recommended_applications: list[dict[str, str]] = field(default_factory=list)
    expanded_summary: str = ""
    load_assessment: str = ""
    reasoning_summary: str = ""
    basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_textual_images": [
                dict(x) for x in self.recommended_textual_images
            ],
            "recommended_illustrations": [
                dict(x) for x in self.recommended_illustrations
            ],
            "recommended_applications": [
                dict(x) for x in self.recommended_applications
            ],
            "expanded_summary": self.expanded_summary,
            "load_assessment": self.load_assessment,
            "reasoning_summary": self.reasoning_summary,
            "basis": list(self.basis),
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }


@dataclass
class EnrichmentAssessmentResult:
    overall_assessment: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    image_assessment: str = ""
    illustration_assessment: str = ""
    application_assessment: str = ""
    load_assessment: str = ""
    revised_textual_images: list[dict[str, str]] = field(default_factory=list)
    revised_illustrations: list[dict[str, str]] = field(default_factory=list)
    revised_applications: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_assessment": self.overall_assessment,
            "strengths": list(self.strengths),
            "improvements": list(self.improvements),
            "image_assessment": self.image_assessment,
            "illustration_assessment": self.illustration_assessment,
            "application_assessment": self.application_assessment,
            "load_assessment": self.load_assessment,
            "revised_textual_images": [dict(x) for x in self.revised_textual_images],
            "revised_illustrations": [dict(x) for x in self.revised_illustrations],
            "revised_applications": [dict(x) for x in self.revised_applications],
            "warnings": list(self.warnings),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }


def normalize_image_function(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "open": "open",
        "megnyitas": "open",
        "megnyitás": "open",
        "clarify": "clarify",
        "tisztazas": "clarify",
        "tisztázás": "clarify",
        "deepen": "deepen",
        "elmelyites": "deepen",
        "elmélyítés": "deepen",
        "create_tension": "create_tension",
        "carry_transition": "carry_transition",
        "support_gospel_turn": "support_gospel_turn",
        "support_memory": "support_memory",
    }
    if raw in IMAGE_FUNCTIONS:
        return raw
    return aliases.get(raw, "")


def image_function_label(value: Any) -> str:
    key = normalize_image_function(value)
    return IMAGE_FUNCTION_LABELS_HU.get(key, "—") if key else "—"


def normalize_illustration_function(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    if raw in ILLUSTRATION_FUNCTIONS:
        return raw
    aliases = {
        "bridge": "bridge",
        "embody": "embody",
        "contrast": "contrast",
        "intensify": "intensify",
        "release_tension": "release_tension",
        "clarify": "clarify",
        "support_memory": "support_memory",
    }
    return aliases.get(raw, "")


def illustration_function_label(value: Any) -> str:
    key = normalize_illustration_function(value)
    return ILLUSTRATION_FUNCTION_LABELS_HU.get(key, "—") if key else "—"


def normalize_illustration_source(value: Any) -> str:
    raw = (
        _as_text(value)
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )
    aliases = {
        "own_experience": "own_experience",
        "sajat_tapasztalat": "own_experience",
        "known_story": "known_story",
        "literature_art": "literature_art",
        "everyday_observation": "everyday_observation",
        "text_workshop_import": "text_workshop_import",
        "textusmuhely": "text_workshop_import",
        "needs_verification": "needs_verification",
        "ellenorizendo": "needs_verification",
    }
    if raw in ILLUSTRATION_SOURCES:
        return raw
    return aliases.get(raw, "needs_verification")


def illustration_source_label(value: Any) -> str:
    key = normalize_illustration_source(value)
    return ILLUSTRATION_SOURCE_LABELS_HU.get(key, key)


def normalize_application_scope(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    if raw in APPLICATION_SCOPES:
        return raw
    aliases = {
        "personal": "personal",
        "szemelyes": "personal",
        "relational": "relational",
        "congregational": "congregational",
        "gyulekezeti": "congregational",
        "communal": "communal",
        "public": "public",
        "pastoral": "pastoral",
    }
    return aliases.get(raw, "personal")


def application_scope_label(value: Any) -> str:
    key = normalize_application_scope(value)
    return APPLICATION_SCOPE_LABELS_HU.get(key, key)


def normalize_placement_kind(value: Any) -> str:
    raw = _as_text(value).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "general": "general",
        "altalanos": "general",
        "általános": "general",
        "introduction": "introduction",
        "bevezetes": "introduction",
        "bevezetés": "introduction",
        "movement": "movement",
        "mozgás": "movement",
        "mozgas": "movement",
        "gospel_turn": "gospel_turn",
        "toward_arrival": "toward_arrival",
        "megerkezes": "toward_arrival",
    }
    if raw in PLACEMENT_KINDS:
        return raw
    return aliases.get(raw, "general")


def placement_kind_label(value: Any) -> str:
    key = normalize_placement_kind(value)
    return PLACEMENT_KIND_LABELS_HU.get(key, key)


def resolve_movement_id(
    movement_id: Any,
    *,
    known_ids: set[str] | None = None,
) -> str:
    """Ismeretlen / hiányzó movement_id → üres string (ne omoljon össze)."""
    mid = _as_text(movement_id)
    if not mid:
        return ""
    if known_ids is None:
        return mid
    return mid if mid in known_ids else ""


def _format_textual_images_block(raw: Any) -> str:
    images = normalize_textual_images(raw)
    if not images:
        return MISSING
    chunks: list[str] = []
    for idx, img in enumerate(images, start=1):
        title = _as_text(img.get("image")) or f"Kép {idx}"
        func = image_function_label(img.get("homiletical_function"))
        place = placement_kind_label(img.get("placement"))
        parts = [f"{idx}. {title} ({func}; {place})"]
        for key, label in (
            ("textual_basis", "Textusbeli alap"),
            ("development_notes", "Kibontás"),
        ):
            val = _as_text(img.get(key))
            if val:
                parts.append(f"  {label}: {val}")
        mid = _as_text(img.get("movement_id"))
        if mid:
            parts.append(f"  Mozgás ID: {mid}")
        chunks.append("\n".join(parts))
    return _display("\n\n".join(chunks), max_chars=_LIMITS_EXTRA["images_block"])


def _format_illustrations_block(raw: Any) -> str:
    items = normalize_illustrations(raw)
    if not items:
        return MISSING
    chunks: list[str] = []
    for idx, ill in enumerate(items, start=1):
        title = _as_text(ill.get("idea")) or f"Illusztráció {idx}"
        func = illustration_function_label(ill.get("function"))
        src = illustration_source_label(ill.get("source"))
        place = placement_kind_label(ill.get("placement"))
        parts = [f"{idx}. {title} ({func}; {src}; {place})"]
        for key, label in (
            ("connection_to_text", "Kapcsolódás a textushoz"),
            ("risk_or_limit", "Kockázat / korlát"),
        ):
            val = _as_text(ill.get(key))
            if val:
                parts.append(f"  {label}: {val}")
        mid = _as_text(ill.get("movement_id"))
        if mid:
            parts.append(f"  Mozgás ID: {mid}")
        chunks.append("\n".join(parts))
    return _display("\n\n".join(chunks), max_chars=_LIMITS_EXTRA["illustrations_block"])


def _format_applications_block(raw: Any) -> str:
    apps = normalize_applications(raw)
    if not apps:
        return MISSING
    chunks: list[str] = []
    for idx, app in enumerate(apps, start=1):
        title = _as_text(app.get("application")) or f"Alkalmazás {idx}"
        scope = application_scope_label(app.get("scope"))
        place = placement_kind_label(app.get("placement"))
        parts = [f"{idx}. {title} ({scope}; {place})"]
        for key, label in (
            ("gospel_basis", "Evangéliumi alap"),
            ("concreteness", "Konkrétság"),
            ("pastoral_caution", "Pásztori óvatosság"),
        ):
            val = _as_text(app.get(key))
            if val:
                parts.append(f"  {label}: {val}")
        mid = _as_text(app.get("movement_id"))
        if mid:
            parts.append(f"  Mozgás ID: {mid}")
        chunks.append("\n".join(parts))
    return _display("\n\n".join(chunks), max_chars=_LIMITS_EXTRA["applications_block"])


def build_enrichment_context(
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
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
) -> dict[str, str]:
    """M7 kontextus — M6 útvonal + képek/illusztrációk/alkalmazások + Textusműhely."""
    ctx = build_sermon_path_context(
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
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre,
    )
    ctx["images_block"] = _format_textual_images_block(selected_images)
    ctx["illustrations_block"] = _format_illustrations_block(illustrations)
    ctx["applications_block"] = _format_applications_block(applications)
    ctx["workshop_illustrations"] = (
        _display(workshop_illustrations, max_chars=_LIMITS_EXTRA["workshop_illustrations"])
        if _is_present(workshop_illustrations)
        else MISSING
    )
    ctx["workshop_actualization"] = (
        _display(workshop_actualization, max_chars=_LIMITS_EXTRA["workshop_actualization"])
        if _is_present(workshop_actualization)
        else MISSING
    )
    return ctx


def _has_approved_sermon_idea(ctx: Mapping[str, str], *, status: str = "") -> bool:
    if status and status.strip().casefold() != "approved":
        return False
    return _is_present(ctx.get("sermon_main_idea"))


def _has_gospel_resolution_or_divine_action(
    ctx: Mapping[str, str],
    *,
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
) -> bool:
    arc = christ_centered_arc if isinstance(christ_centered_arc, dict) else {}
    lt = listener_tension if isinstance(listener_tension, dict) else {}
    if _is_present(arc.get("divine_gracious_action")):
        return True
    if _is_present(lt.get("promised_resolution")):
        return True
    block = ctx.get("christ_arc_block", MISSING)
    if not _is_present(block):
        return False
    text = str(block)
    for marker in (
        "Evangéliumi feloldás:",
        "Isten kegyelmi cselekvése:",
    ):
        if marker in text:
            for line in text.splitlines():
                if line.startswith(marker):
                    val = line.split(":", 1)[-1].strip()
                    if val and val != MISSING:
                        return True
    return False


def _has_m6_path_or_movements(
    sermon_path: Any,
    sermon_movements: Any,
) -> bool:
    path = sermon_path if isinstance(sermon_path, dict) else {}
    if any(
        _is_present(path.get(k))
        for k in ("type", "reason", "starting_point", "destination")
    ):
        return True
    movements = normalize_sermon_movements(sermon_movements)
    filled = [
        m
        for m in movements
        if _is_present(m.get("title")) or _is_present(m.get("core_content"))
    ]
    return len(filled) >= 3


def _missing_enrichment_labels(
    ctx: Mapping[str, str],
    *,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    sermon_main_idea_status: str = "",
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
) -> list[str]:
    missing: list[str] = []
    if not _is_present(ctx.get("passage", MISSING)):
        missing.append("igehely-megjelölés (passage)")
    if not _has_approved_sermon_idea(ctx, status=sermon_main_idea_status):
        missing.append("jóváhagyott igehirdetési fő gondolat")
    if not _has_m6_path_or_movements(sermon_path, sermon_movements):
        missing.append("M6-os prédikációs út vagy legalább három mozgás")
    if not _has_gospel_resolution_or_divine_action(
        ctx,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    ):
        missing.append("evangéliumi feloldás vagy Isten kegyelmi cselekvése")
    return missing


def has_sufficient_enrichment_material(
    ctx: Mapping[str, str],
    *,
    sermon_path: Any = None,
    sermon_movements: Any = None,
    sermon_main_idea_status: str = "",
    christ_centered_arc: Any = None,
    listener_tension: Any = None,
) -> bool:
    return not _missing_enrichment_labels(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    )


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        if key.startswith("_"):
            continue
        out = out.replace("{{" + key + "}}", value)
    return out


_SUGGEST_TEMPLATE = """\
Feladatod: TEXTUSBÓL FAKADÓ KÉPEK, ILLUSZTRÁCIÓK ÉS ALKALMAZÁSI IRÁNYOK javaslata.

Ez NEM kész prédikációrész, NEM teljes illusztráció megírása, NEM feladatlista,
NEM moralizáló tanácsok gyűjteménye.

## Szakmai elvek

- A textus saját képe elsőbbséget élvezhet a külső példával szemben.
- Ne legyen minden prédikációhoz kötelező külső illusztráció.
- Egy erős textusbeli kép többet érhet három gyenge példánál.
- Az illusztráció ne legyen érdekesebb, mint az üzenet.
- Az alkalmazás Isten kegyelmi cselekvéséből fakadjon.
- Az alkalmazás ne legyen moralizáló feladatlista.
- Ne találj ki személyes történetet, történelmi eseményt vagy idézetet.
- Ne feltételezz életkort, családi helyzetet vagy lelkiállapotot.
- Ha külső illusztráció nem szükséges, az `recommended_illustrations` lehet üres lista.

## Korlátok

- `recommended_textual_images`: legfeljebb 2 elem;
- `recommended_illustrations`: 0–2 elem (üres lista elfogadható);
- `recommended_applications`: 2–4 elem;
- minden elemhez javasolt `placement` és `movement_id`, ha az M6 mozgások
  rendelkezésre állnak; ismeretlen movement_id ne legyen kitalálva.

## Textusbeli kép mezői

- `image`, `textual_basis`, `homiletical_function`
  (open | clarify | deepen | create_tension | carry_transition |
   support_gospel_turn | support_memory)
- `placement` (general | introduction | movement | gospel_turn | toward_arrival)
- `movement_id`, `development_notes`

## Illusztráció mezői

- `idea`, `source`
  (own_experience | known_story | literature_art | everyday_observation |
   text_workshop_import | needs_verification)
- `function`
  (bridge | clarify | embody | contrast | intensify | release_tension |
   support_memory)
- `placement`, `movement_id`, `connection_to_text`, `risk_or_limit`

## Alkalmazás mezői

- `application`, `scope`
  (personal | relational | congregational | communal | public | pastoral)
- `gospel_basis`, `concreteness`, `placement`, `movement_id`, `pastoral_caution`

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

Textusműhely — illusztrációk (forrás, ne másold automatikusan):
{{workshop_illustrations}}

Textusműhely — aktualizálás (forrás):
{{workshop_actualization}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma (csak ezt add vissza)

{
  "recommended_textual_images": [
    {
      "image": "",
      "textual_basis": "",
      "homiletical_function": "open|clarify|deepen|create_tension|carry_transition|support_gospel_turn|support_memory",
      "placement": "general|introduction|movement|gospel_turn|toward_arrival",
      "movement_id": "",
      "development_notes": ""
    }
  ],
  "recommended_illustrations": [],
  "recommended_applications": [
    {
      "application": "",
      "scope": "personal|relational|congregational|communal|public|pastoral",
      "gospel_basis": "",
      "concreteness": "",
      "placement": "",
      "movement_id": "",
      "pastoral_caution": ""
    }
  ],
  "expanded_summary": "",
  "load_assessment": "",
  "reasoning_summary": "",
  "basis": [],
  "warnings": [],
  "missing_information": []
}

A `load_assessment` röviden értékelje a túlterhelés, sablonosság vagy
moralizálás kockázatát. Mondd ki, ha külső illusztráció nem szükséges.
"""


_ASSESS_TEMPLATE = """\
Feladatod: a prédikátor SAJÁT képei, illusztrációi és alkalmazásai értékelése.

Vizsgáld:
- a képek valóban a textusból fakadnak-e, van-e funkciójuk, nem válnak-e allegorikussá;
- az illusztráció világosabbá teszi-e az üzenetet, nem érdekesebb-e a textusnál;
- túl sok elem került-e a prédikációba;
- megfelelő helyen szerepelnek-e az M6 mozgásokhoz képest;
- van-e ismétlés;
- az alkalmazások a kegyelemből fakadnak-e, elég konkrétak-e;
- nem moralizálóak-e, nem túl általánosak-e;
- nem feltételeznek-e túl sokat a hallgatóról;
- pásztorilag érzékenyek-e.

Ne írd felül automatikusan a felhasználó munkáját — a `revised_*` mezők
csak javaslatok.

## Műhelyanyag

Igehely: {{passage}}
Fordítás: {{bible_translation}}
Műfaj / irodalmi adat: {{literary_genre}}

Bibliai szöveg:
{{passage_text}}

Jóváhagyott igehirdetési fő gondolat: {{sermon_main_idea}}
Kifejtés: {{sermon_expanded_summary}}

Evangéliumi ív:
{{christ_arc_block}}

Az igehirdetés útja:
{{sermon_path_block}}

Prédikációs mozgások:
{{movements_block}}

A prédikátor textusbeli képei:
{{images_block}}

A prédikátor illusztrációi:
{{illustrations_block}}

A prédikátor alkalmazásai:
{{applications_block}}

Exegézis: {{exegesis}}
Teológia: {{theology}}

## JSON-séma

{
  "overall_assessment": "",
  "strengths": [],
  "improvements": [],
  "image_assessment": "",
  "illustration_assessment": "",
  "application_assessment": "",
  "load_assessment": "",
  "revised_textual_images": [],
  "revised_illustrations": [],
  "revised_applications": [],
  "warnings": []
}
"""


def build_enrichment_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_SUGGEST_TEMPLATE, ctx)


def build_enrichment_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_ASSESS_TEMPLATE, ctx)


def _call_m7_generate(
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
            system_bundle=M7_SYSTEM_BUNDLE,
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


def fallback_enrichment_suggestion(
    *,
    reasoning: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> EnrichmentSuggestionResult:
    return EnrichmentSuggestionResult(
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_enrichment_assessment(
    *,
    overall: str = "",
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> EnrichmentAssessmentResult:
    return EnrichmentAssessmentResult(
        overall_assessment=overall
        or "Nem megítélhető — nincs elegendő értékelhető megfogalmazás.",
        warnings=list(warnings or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def _known_movement_ids(sermon_movements: Any) -> set[str]:
    return {
        _as_text(m.get("id"))
        for m in normalize_sermon_movements(sermon_movements)
        if _as_text(m.get("id"))
    }


def _normalize_textual_image_item(
    raw: Any,
    *,
    known_ids: set[str],
    warnings: list[str],
) -> dict[str, str]:
    item = normalize_textual_image(raw if isinstance(raw, dict) else {})
    item["homiletical_function"] = normalize_image_function(item.get("homiletical_function"))
    item["placement"] = normalize_placement_kind(item.get("placement"))
    resolved = resolve_movement_id(item.get("movement_id"), known_ids=known_ids)
    raw_dict = raw if isinstance(raw, dict) else {}
    if _as_text(raw_dict.get("movement_id")) and not resolved:
        warnings.append("Ismeretlen movement_id — üresen hagyva.")
    item["movement_id"] = resolved
    if not isinstance(raw, dict) or not _as_text(raw.get("id")):
        item["id"] = empty_textual_image()["id"]
    return item


def _normalize_illustration_item(
    raw: Any,
    *,
    known_ids: set[str],
    warnings: list[str],
) -> dict[str, str]:
    item = normalize_illustration(raw if isinstance(raw, dict) else {})
    item["source"] = normalize_illustration_source(item.get("source"))
    item["function"] = normalize_illustration_function(item.get("function"))
    item["placement"] = normalize_placement_kind(item.get("placement"))
    resolved = resolve_movement_id(item.get("movement_id"), known_ids=known_ids)
    raw_dict = raw if isinstance(raw, dict) else {}
    if _as_text(raw_dict.get("movement_id")) and not resolved:
        warnings.append("Ismeretlen movement_id — üresen hagyva.")
    item["movement_id"] = resolved
    if not isinstance(raw, dict) or not _as_text(raw.get("id")):
        item["id"] = empty_illustration()["id"]
    return item


def _normalize_application_item(
    raw: Any,
    *,
    known_ids: set[str],
    warnings: list[str],
) -> dict[str, str]:
    item = normalize_application(raw if isinstance(raw, dict) else {})
    item["scope"] = normalize_application_scope(item.get("scope"))
    item["placement"] = normalize_placement_kind(item.get("placement"))
    resolved = resolve_movement_id(item.get("movement_id"), known_ids=known_ids)
    raw_dict = raw if isinstance(raw, dict) else {}
    if _as_text(raw_dict.get("movement_id")) and not resolved:
        warnings.append("Ismeretlen movement_id — üresen hagyva.")
    item["movement_id"] = resolved
    if not isinstance(raw, dict) or not _as_text(raw.get("id")):
        item["id"] = empty_application()["id"]
    return item


def _parse_textual_images_list(
    raw: Any,
    *,
    known_ids: set[str],
    warnings: list[str],
    max_items: int = MAX_AI_TEXTUAL_IMAGES,
) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        if raw not in (None, []):
            warnings.append("A textusbeli képek listája érvénytelen.")
        return []
    original = len([x for x in raw if isinstance(x, dict)])
    if original > max_items:
        warnings.append(
            f"A javaslat {original} textusbeli képet tartalmazott; "
            f"legfeljebb {max_items} marad meg."
        )
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            _normalize_textual_image_item(item, known_ids=known_ids, warnings=warnings)
        )
        if len(out) >= max_items:
            break
    return out


def _parse_illustrations_list(
    raw: Any,
    *,
    known_ids: set[str],
    warnings: list[str],
    max_items: int = MAX_AI_ILLUSTRATIONS,
) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        if raw not in (None, []):
            warnings.append("Az illusztrációk listája érvénytelen.")
        return []
    original = len([x for x in raw if isinstance(x, dict)])
    if original > max_items:
        warnings.append(
            f"A javaslat {original} illusztrációt tartalmazott; "
            f"legfeljebb {max_items} marad meg."
        )
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            _normalize_illustration_item(item, known_ids=known_ids, warnings=warnings)
        )
        if len(out) >= max_items:
            break
    return out


def _parse_applications_list(
    raw: Any,
    *,
    known_ids: set[str],
    warnings: list[str],
    max_items: int = MAX_APPLICATIONS,
) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        warnings.append("Az alkalmazások listája hiányzik vagy érvénytelen.")
        return []
    original = len([x for x in raw if isinstance(x, dict)])
    if original > max_items:
        warnings.append(
            f"A javaslat {original} alkalmazást tartalmazott; "
            f"legfeljebb {max_items} marad meg."
        )
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            _normalize_application_item(item, known_ids=known_ids, warnings=warnings)
        )
        if len(out) >= max_items:
            break
    if out and len(out) < MIN_AI_APPLICATIONS:
        warnings.append(
            f"A javaslat kevesebb mint {MIN_AI_APPLICATIONS} alkalmazást tartalmaz "
            f"({len(out)}). Érdemes kiegészíteni."
        )
    return out


def parse_enrichment_suggestions(
    raw: str,
    *,
    known_ids: set[str] | None = None,
) -> EnrichmentSuggestionResult:
    ids = known_ids or set()
    if _is_api_error_text(raw):
        return fallback_enrichment_suggestion(
            reasoning="Az API válasz hibás vagy üres.",
            warnings=["A javaslatkészítés nem adott érvényes választ."],
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return fallback_enrichment_suggestion(
            reasoning="A válasz nem volt érvényes JSON.",
            warnings=["Hibás vagy hiányos JSON; biztonságos alapértékeket használtunk."],
            error_message="Érvénytelen JSON.",
            raw_response=raw or "",
            ok=False,
        )
    warnings = _as_str_list(obj.get("warnings"))
    images = _parse_textual_images_list(
        obj.get("recommended_textual_images"), known_ids=ids, warnings=warnings
    )
    illustrations = _parse_illustrations_list(
        obj.get("recommended_illustrations"), known_ids=ids, warnings=warnings
    )
    applications = _parse_applications_list(
        obj.get("recommended_applications"), known_ids=ids, warnings=warnings
    )
    return EnrichmentSuggestionResult(
        recommended_textual_images=images,
        recommended_illustrations=illustrations,
        recommended_applications=applications,
        expanded_summary=_as_text(obj.get("expanded_summary")),
        load_assessment=_as_text(obj.get("load_assessment")),
        reasoning_summary=_as_text(obj.get("reasoning_summary")),
        basis=_as_str_list(obj.get("basis")),
        warnings=warnings,
        missing_information=_as_str_list(obj.get("missing_information")),
        ok=True,
        raw_response=raw or "",
    )


def parse_enrichment_assessment(
    raw: str,
    *,
    known_ids: set[str] | None = None,
) -> EnrichmentAssessmentResult:
    ids = known_ids or set()
    if _is_api_error_text(raw):
        return fallback_enrichment_assessment(
            overall="Az értékelés nem sikerült (hibás vagy üres API-válasz).",
            warnings=["Az értékelés nem adott érvényes választ."],
            error_message=_as_text(raw)[:280],
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        return fallback_enrichment_assessment(
            overall="Az értékelés nem értelmezhető — érvénytelen JSON.",
            warnings=["Hibás vagy hiányos JSON; biztonságos alapértékeket használtunk."],
            error_message="Érvénytelen JSON.",
            raw_response=raw or "",
            ok=False,
        )
    warnings = _as_str_list(obj.get("warnings"))
    return EnrichmentAssessmentResult(
        overall_assessment=_as_text(obj.get("overall_assessment")),
        strengths=_as_str_list(obj.get("strengths")),
        improvements=_as_str_list(obj.get("improvements")),
        image_assessment=_as_text(obj.get("image_assessment")),
        illustration_assessment=_as_text(obj.get("illustration_assessment")),
        application_assessment=_as_text(obj.get("application_assessment")),
        load_assessment=_as_text(obj.get("load_assessment")),
        revised_textual_images=_parse_textual_images_list(
            obj.get("revised_textual_images"),
            known_ids=ids,
            warnings=warnings,
            max_items=MAX_TEXTUAL_IMAGES,
        ),
        revised_illustrations=_parse_illustrations_list(
            obj.get("revised_illustrations"),
            known_ids=ids,
            warnings=warnings,
            max_items=MAX_ILLUSTRATIONS,
        ),
        revised_applications=_parse_applications_list(
            obj.get("revised_applications"),
            known_ids=ids,
            warnings=warnings,
            max_items=MAX_APPLICATIONS,
        ),
        warnings=warnings,
        ok=True,
        raw_response=raw or "",
    )


def suggest_enrichment(
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
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> EnrichmentSuggestionResult:
    ctx = build_enrichment_context(
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
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
    )
    missing = _missing_enrichment_labels(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    )
    if not _is_present(ctx["passage"]):
        return fallback_enrichment_suggestion(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_enrichment_material(
        ctx,
        sermon_path=sermon_path,
        sermon_movements=sermon_movements,
        sermon_main_idea_status=sermon_main_idea_status,
        christ_centered_arc=christ_centered_arc,
        listener_tension=listener_tension,
    ):
        return fallback_enrichment_suggestion(
            reasoning=(
                "Nincs elegendő jóváhagyott műhelyeredmény a felelős "
                "kép/illusztráció/alkalmazás javaslathoz."
            ),
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres ajánlások.",
                "Szükséges: igehely, jóváhagyott igehirdetési fő gondolat, "
                "M6-os út vagy legalább három mozgás, valamint evangéliumi "
                "feloldás vagy Isten kegyelmi cselekvése.",
            ],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_enrichment_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_enrichment_suggest_prompt(ctx)
    try:
        raw = _call_m7_generate(
            generate_fn,
            prompt,
            tab_label=TAB_SUGGEST,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_enrichment_suggestion(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=["A javaslatkészítés nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    known_ids = _known_movement_ids(sermon_movements)
    result = parse_enrichment_suggestions(raw or "", known_ids=known_ids)
    if result.ok and not _is_present(ctx.get("passage_text")):
        note = (
            "A teljes bibliai szöveg (passage_text) nem állt közvetlenül "
            "rendelkezésre; a javaslat a jóváhagyott műhelyeredményekből készült."
        )
        if note not in result.warnings and (
            result.recommended_textual_images or result.recommended_applications
        ):
            result.warnings = list(result.warnings) + [note]
        label = "bibliai szöveg (passage_text)"
        if label not in result.missing_information:
            result.missing_information = list(result.missing_information) + [label]
    if result.ok and _is_present(ctx.get("passage_text")):
        result.warnings = [
            w
            for w in result.warnings
            if "passage_text" not in w.casefold()
            or "nem állt" not in w.casefold()
        ]
        result.missing_information = [
            m
            for m in result.missing_information
            if "passage_text" not in m.casefold()
        ]
    return result


def assess_enrichment(
    *,
    passage: str,
    selected_images: Any = None,
    illustrations: Any = None,
    applications: Any = None,
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
    workshop_illustrations: str = "",
    workshop_actualization: str = "",
    exegesis: str = "",
    theology: str = "",
    literary_genre: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> EnrichmentAssessmentResult:
    images = normalize_textual_images(selected_images)
    ills = normalize_illustrations(illustrations)
    apps = normalize_applications(applications)
    filled = bool(images or ills or apps)
    if not filled:
        return fallback_enrichment_assessment(
            overall="Nincs értékelhető kép, illusztráció vagy alkalmazás.",
            warnings=["Adj hozzá legalább egy elemet az értékeléshez."],
            ok=True,
        )

    ctx = build_enrichment_context(
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
        selected_images=images,
        illustrations=ills,
        applications=apps,
        workshop_illustrations=workshop_illustrations,
        workshop_actualization=workshop_actualization,
        exegesis=exegesis,
        theology=theology,
        literary_genre=literary_genre or exegesis,
    )
    if generate_fn is None:
        return fallback_enrichment_assessment(
            overall="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_enrichment_assess_prompt(ctx)
    try:
        raw = _call_m7_generate(
            generate_fn,
            prompt,
            tab_label=TAB_ASSESS,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_enrichment_assessment(
            overall="Az értékelés közben váratlan hiba történt.",
            warnings=["Az értékelés nem sikerült. Próbáld újra később."],
            error_message=str(exc),
            ok=False,
        )
    known_ids = _known_movement_ids(sermon_movements)
    return parse_enrichment_assessment(raw or "", known_ids=known_ids)


def _self_check() -> list[str]:
    errors: list[str] = []

    def _gen_factory(payload: str):
        def _gen(*_a, **_k):
            return payload

        return _gen

    base_kw = {
        "passage": "Jn 10,11–18",
        "passage_text": "Én vagyok a jó pásztor…",
        "sermon_main_idea": "Jézus a jó pásztor",
        "sermon_main_idea_status": "approved",
        "christ_centered_arc": {"divine_gracious_action": "Jézus odaadja az életét"},
        "listener_tension": {"promised_resolution": "A pásztor megtartja a juhait"},
        "sermon_path": {"type": "narrative", "reason": "Elbeszélő ív"},
        "sermon_movements": [
            {"id": "mv1", "title": "M1", "role": "opening", "core_content": "a"},
            {"id": "mv2", "title": "M2", "role": "tension", "core_content": "b"},
            {"id": "mv3", "title": "M3", "role": "gospel_resolution", "core_content": "c"},
        ],
    }

    suggest_a = (
        '{"recommended_textual_images":[{"image":"A jó pásztor","textual_basis":"Jn 10,11",'
        '"homiletical_function":"deepen","placement":"movement","movement_id":"mv2",'
        '"development_notes":"Rövid kibontás."}],'
        '"recommended_illustrations":[],'
        '"recommended_applications":[{"application":"Bizalom a pásztorban","scope":"personal",'
        '"gospel_basis":"Jézus odaadja életét","concreteness":"Hitbeli bizalom",'
        '"placement":"toward_arrival","movement_id":"","pastoral_caution":""},'
        '{"application":"Gyülekezeti gondviselés","scope":"congregational",'
        '"gospel_basis":"Krisztus példája","concreteness":"Közösségi figyelem",'
        '"placement":"movement","movement_id":"mv3","pastoral_caution":""}],'
        '"expanded_summary":"A textus képe viszi az ívet.","load_assessment":"Egy kép elegendő.",'
        '"reasoning_summary":"Textusbeli kép elég.","basis":["Jn 10"],"warnings":[],'
        '"missing_information":[]}'
    )
    ra = suggest_enrichment(generate_fn=_gen_factory(suggest_a), **base_kw)
    if not ra.ok or ra.recommended_illustrations:
        errors.append("A/D: expected textual image without external illustration")
    if len(ra.recommended_textual_images) != 1:
        errors.append("A: expected one textual image")
    if len(ra.recommended_applications) < 2:
        errors.append("A: expected at least 2 applications")

    suggest_b = (
        '{"recommended_textual_images":[{"image":"A jelenet","textual_basis":"v.5",'
        '"homiletical_function":"open","placement":"movement","movement_id":"mv1",'
        '"development_notes":""}],'
        '"recommended_illustrations":[],"recommended_applications":['
        '{"application":"a","scope":"personal","gospel_basis":"g","concreteness":"c",'
        '"placement":"general","movement_id":"","pastoral_caution":""},'
        '{"application":"b","scope":"relational","gospel_basis":"g","concreteness":"c",'
        '"placement":"general","movement_id":"","pastoral_caution":""}],'
        '"expanded_summary":"","load_assessment":"","reasoning_summary":"","basis":[],'
        '"warnings":[],"missing_information":[]}'
    )
    rb = suggest_enrichment(generate_fn=_gen_factory(suggest_b), **base_kw)
    if not rb.recommended_textual_images[0].get("movement_id") == "mv1":
        errors.append("B: expected movement link")

    suggest_c = (
        '{"recommended_textual_images":[],"recommended_illustrations":[],'
        '"recommended_applications":[{"application":"a","scope":"personal","gospel_basis":"g",'
        '"concreteness":"c","placement":"general","movement_id":"","pastoral_caution":""},'
        '{"application":"b","scope":"personal","gospel_basis":"g","concreteness":"c",'
        '"placement":"general","movement_id":"","pastoral_caution":""}],'
        '"expanded_summary":"","load_assessment":"Nincs erőltetett vizuális kép.",'
        '"reasoning_summary":"","basis":[],"warnings":[],"missing_information":[]}'
    )
    rc = suggest_enrichment(
        passage="Róm 5,1–11",
        passage_text="Megigazulván tehát hit által…",
        sermon_main_idea="Békesség Istennel",
        sermon_main_idea_status="approved",
        christ_centered_arc={"divine_gracious_action": "Isten kegyelme"},
        sermon_path={"type": "deductive", "reason": "Érvelés"},
        sermon_movements=[
            {"id": "a", "title": "1", "core_content": "x"},
            {"id": "b", "title": "2", "core_content": "y"},
            {"id": "c", "title": "3", "core_content": "z"},
        ],
        generate_fn=_gen_factory(suggest_c),
    )
    if rc.recommended_textual_images:
        errors.append("C: expected no forced visual image")

    rk = parse_enrichment_suggestions(
        '{"recommended_textual_images":[{"image":"k","textual_basis":"v",'
        '"homiletical_function":"open","placement":"movement","movement_id":"UNKNOWN",'
        '"development_notes":""}],"recommended_illustrations":[],"recommended_applications":[],'
        '"expanded_summary":"","load_assessment":"","reasoning_summary":"","basis":[],'
        '"warnings":[],"missing_information":[]}',
        known_ids={"mv1"},
    )
    if rk.recommended_textual_images[0].get("movement_id") != "":
        errors.append("K: unknown movement_id should become empty")
    if not any("movement_id" in w.casefold() for w in rk.warnings):
        errors.append("K: expected movement_id warning")

    rm = suggest_enrichment(
        passage="Zsolt 23",
        passage_text="Az Úr az én pásztorom…",
        sermon_main_idea="Isten gondviselése",
        sermon_main_idea_status="approved",
        christ_centered_arc={"divine_gracious_action": "Isten pásztorol"},
        sermon_path={"reason": "Zsoltár"},
        sermon_movements=[
            {"id": "m1", "title": "1", "core_content": "a"},
            {"id": "m2", "title": "2", "core_content": "b"},
            {"id": "m3", "title": "3", "core_content": "c"},
        ],
        generate_fn=_gen_factory(suggest_a),
    )
    if any(
        "passage_text" in w.casefold() and ("hiány" in w.casefold() or "nincs" in w.casefold())
        for w in rm.warnings
    ):
        errors.append("M: false missing passage_text warning")

    assess_g = (
        '{"overall_assessment":"Túl sok illusztráció terheli a prédikációt.",'
        '"strengths":["Van textusbeli kép"],"improvements":["Csökkentsd az illusztrációkat"],'
        '"image_assessment":"Erős.","illustration_assessment":"Túlterhelt.",'
        '"application_assessment":"Rendben.","load_assessment":"Túlterhelés.",'
        '"revised_textual_images":[],"revised_illustrations":[],"revised_applications":[],'
        '"warnings":["Túl sok illusztráció"]}'
    )
    rg = assess_enrichment(
        passage="Mk 4,35–41",
        selected_images=[{"image": "Vihar", "textual_basis": "v.37"}],
        illustrations=[
            {"idea": "I1", "source": "everyday_observation"},
            {"idea": "I2", "source": "everyday_observation"},
            {"idea": "I3", "source": "everyday_observation"},
        ],
        applications=[{"application": "Bizalom", "scope": "personal"}],
        sermon_main_idea="Jézus uralma",
        sermon_main_idea_status="approved",
        generate_fn=_gen_factory(assess_g),
    )
    blob = (rg.overall_assessment + " " + rg.load_assessment).casefold()
    if "túl" not in blob and "tul" not in blob:
        errors.append("G: expected overload signal")

    assess_h = (
        '{"overall_assessment":"Moralizáló alkalmazások dominálnak.",'
        '"strengths":[],"improvements":["Kegyelmi alap hiányzik"],'
        '"image_assessment":"","illustration_assessment":"","application_assessment":'
        '"Moralizáló feladatlista jelleg.",'
        '"load_assessment":"","revised_textual_images":[],"revised_illustrations":[],'
        '"revised_applications":[],"warnings":["Moralizálás"]}'
    )
    rh = assess_enrichment(
        passage="Fil 2,1–11",
        applications=[{"application": "Legyünk jobb emberek", "scope": "personal"}],
        sermon_main_idea="Krisztus alázata",
        generate_fn=_gen_factory(assess_h),
    )
    if "moraliz" not in (
        rh.overall_assessment + rh.application_assessment
    ).casefold():
        errors.append("H: expected moralizing signal")

    assess_i = (
        '{"overall_assessment":"Az alkalmazások túl általánosak.",'
        '"strengths":[],"improvements":["Adj konkrétabb irányt"],'
        '"image_assessment":"","illustration_assessment":"","application_assessment":'
        '"Túl általános.",'
        '"load_assessment":"","revised_textual_images":[],"revised_illustrations":[],'
        '"revised_applications":[{"application":"Konkrétabb válasz","scope":"relational",'
        '"gospel_basis":"Kegyelem","concreteness":"Kapcsolati lépés","placement":"general",'
        '"movement_id":"","pastoral_caution":""}],'
        '"warnings":[]}'
    )
    ri = assess_enrichment(
        passage="1Jn 4,7–12",
        applications=[{"application": "Szeressük egymást", "scope": "general"}],
        sermon_main_idea="Isten szeretete",
        generate_fn=_gen_factory(assess_i),
    )
    if "általános" not in (
        ri.overall_assessment + ri.application_assessment
    ).casefold() and "altalanos" not in (
        ri.overall_assessment + ri.application_assessment
    ).casefold():
        errors.append("I: expected too-general signal")
    if not ri.revised_applications:
        errors.append("I: expected revised application")

    assess_j = (
        '{"overall_assessment":"Érzéketlen pásztori alkalmazás.",'
        '"strengths":[],"improvements":["Óvatosabb megfogalmazás"],'
        '"image_assessment":"","illustration_assessment":"","application_assessment":'
        '"Trauma érzéketlenül kezelve.",'
        '"load_assessment":"","revised_textual_images":[],"revised_illustrations":[],'
        '"revised_applications":[],"warnings":["Pásztori érzékenység hiányzik"]}'
    )
    rj = assess_enrichment(
        passage="Jn 11",
        applications=[{"application": "Mindenki gyógyuljon azonnal", "scope": "pastoral"}],
        sermon_main_idea="Jézus sirat",
        generate_fn=_gen_factory(assess_j),
    )
    if "érzéketlen" not in rj.overall_assessment.casefold() and "erzeketlen" not in rj.overall_assessment.casefold():
        errors.append("J: expected pastoral sensitivity signal")

    mvs = normalize_sermon_movements(
        [
            {"id": "x1", "title": "A", "core_content": "1"},
            {"id": "x2", "title": "B", "core_content": "2"},
            {"id": "x3", "title": "C", "core_content": "3"},
        ]
    )
    mvs[0], mvs[1] = mvs[1], mvs[0]
    known = _known_movement_ids(mvs)
    if "x1" not in known or "x2" not in known:
        errors.append("L: movement ids should survive reorder")
    parsed_l = parse_enrichment_suggestions(
        '{"recommended_textual_images":[{"image":"k","textual_basis":"v",'
        '"homiletical_function":"open","placement":"movement","movement_id":"x2",'
        '"development_notes":""}],"recommended_illustrations":[],"recommended_applications":[],'
        '"expanded_summary":"","load_assessment":"","reasoning_summary":"","basis":[],'
        '"warnings":[],"missing_information":[]}',
        known_ids=known,
    )
    if parsed_l.recommended_textual_images[0].get("movement_id") != "x2":
        errors.append("L: movement_id link should resolve after reorder")

    from sermon_workshop_data import normalize_sermon_workshop

    old = normalize_sermon_workshop({"sermon_main_idea": "régi"})
    if old.get("selected_images") != []:
        errors.append("N: old project missing selected_images default")
    if old.get("enrichment_status") != "draft":
        errors.append("N: enrichment_status default")
    if old.get("sermon_enrichment_suggestions") is not None:
        errors.append("N: suggestions default None")

    insuff = suggest_enrichment(
        passage="Jn 3,16",
        sermon_main_idea="Isten szeretete",
        sermon_main_idea_status="draft",
        generate_fn=_gen_factory(suggest_a),
    )
    if "jóváhagyott igehirdetési fő gondolat" not in " ".join(
        insuff.missing_information
    ):
        errors.append("min input: missing approved sermon idea")

    bad = parse_enrichment_suggestions("nem json")
    if bad.ok:
        errors.append("bad json should fail")

    if normalize_placement_kind("Mozgás") != "movement":
        errors.append("alias movement placement")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("FAIL")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon enrichment self-check OK")


__all__ = [
    "IMAGE_FUNCTIONS",
    "IMAGE_FUNCTION_LABELS_HU",
    "ILLUSTRATION_FUNCTIONS",
    "ILLUSTRATION_FUNCTION_LABELS_HU",
    "ILLUSTRATION_SOURCES",
    "ILLUSTRATION_SOURCE_LABELS_HU",
    "APPLICATION_SCOPES",
    "APPLICATION_SCOPE_LABELS_HU",
    "PLACEMENT_KINDS",
    "PLACEMENT_KIND_LABELS_HU",
    "MAX_TEXTUAL_IMAGES",
    "MAX_AI_TEXTUAL_IMAGES",
    "MAX_ILLUSTRATIONS",
    "MAX_AI_ILLUSTRATIONS",
    "MAX_APPLICATIONS",
    "MIN_AI_APPLICATIONS",
    "EnrichmentSuggestionResult",
    "EnrichmentAssessmentResult",
    "normalize_image_function",
    "image_function_label",
    "normalize_illustration_function",
    "illustration_function_label",
    "normalize_illustration_source",
    "illustration_source_label",
    "normalize_application_scope",
    "application_scope_label",
    "normalize_placement_kind",
    "placement_kind_label",
    "resolve_movement_id",
    "build_enrichment_context",
    "has_sufficient_enrichment_material",
    "build_enrichment_suggest_prompt",
    "build_enrichment_assess_prompt",
    "parse_enrichment_suggestions",
    "parse_enrichment_assessment",
    "suggest_enrichment",
    "assess_enrichment",
    "fallback_enrichment_suggestion",
    "fallback_enrichment_assessment",
]
