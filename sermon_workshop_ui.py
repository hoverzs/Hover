"""Textus 2.0 Igehirdetési műhely — UI (M4: kézi + MI-segéd).

Nem importál az app.py-ból. A Gemini-hívást a hívó által átadott
`generate_fn` végzi (tipikusan `generate_text`).
"""

from __future__ import annotations

import html
from typing import Any, Callable

import streamlit as st

from bible_text_ui import (
    normalize_passage_text,
    render_bible_text_preview,
    render_formatted_bible_text,
)
from bible_text_ui import _ensure_bible_text_styles
from ruf_bible_service import SOURCE_NAME, fetch_ruf_passage
from sermon_workshop_data import (
    add_approved_sermon_decision,
    empty_application,
    empty_illustration,
    empty_sermon_movement,
    empty_textual_image,
    ensure_sermon_workshop_state,
    normalize_applications,
    normalize_illustrations,
    normalize_lection_connection_type,
    normalize_lection_length_preference,
    normalize_lection_testament_preference,
    normalize_sermon_movements,
    normalize_textual_images,
    remove_approved_sermon_decision,
    save_gospel_arc_assessment,
    save_gospel_arc_suggestions,
    save_human_condition_assessment,
    save_human_condition_suggestion,
    save_listener_tension_assessment,
    save_listener_tension_suggestions,
    save_closing_assessment,
    save_closing_suggestions,
    save_homiletical_diagnostics,
    save_lection_assessment,
    save_lection_suggestions,
    save_prayer_after_suggestions,
    save_prayer_assessment,
    save_prayer_before_suggestions,
    save_sermon_enrichment_assessment,
    save_sermon_enrichment_suggestions,
    save_sermon_main_idea_assessment,
    save_sermon_main_idea_suggestions,
    save_sermon_outline,
    save_sermon_outline_diagnostics,
    save_sermon_path_assessment,
    save_sermon_path_suggestions,
    update_sermon_workshop_section,
    normalize_prayer_rewrite_mode,
    normalize_prayer_tone_preference,
    normalize_sermon_outline,
)
from sermon_workshop_m4_ai import (
    HumanConditionAssessmentResult,
    HumanConditionSuggestionResult,
    SermonMainIdeaAssessmentResult,
    SermonMainIdeaSuggestionResult,
    assess_human_condition,
    assess_sermon_main_idea,
    suggest_human_condition,
    suggest_sermon_main_idea,
)
from sermon_workshop_m5_ai import (
    ListenerTensionAssessmentResult,
    ListenerTensionSuggestionResult,
    assess_listener_tension,
    suggest_listener_tension,
)
from sermon_workshop_m5_gospel_ai import (
    CHRIST_CONNECTION_TYPES,
    CHRIST_CONNECTION_TYPE_LABELS_HU,
    GospelArcAssessmentResult,
    GospelArcSuggestionResult,
    assess_gospel_arc,
    christ_connection_type_label,
    normalize_christ_connection_type,
    suggest_gospel_arc,
)
from sermon_workshop_m6_ai import (
    DEFAULT_MOVEMENT_COUNT,
    MAX_MOVEMENTS,
    MIN_MOVEMENTS,
    MOVEMENT_ROLES,
    MOVEMENT_ROLE_LABELS_HU,
    SERMON_PATH_TYPES,
    SERMON_PATH_TYPE_LABELS_HU,
    SermonPathAssessmentResult,
    SermonPathSuggestionResult,
    assess_sermon_path,
    movement_role_label,
    normalize_movement_role,
    normalize_sermon_path_type,
    sermon_path_type_label,
    suggest_sermon_path,
)
from sermon_workshop_m7_ai import (
    APPLICATION_SCOPES,
    APPLICATION_SCOPE_LABELS_HU,
    IMAGE_FUNCTIONS,
    IMAGE_FUNCTION_LABELS_HU,
    ILLUSTRATION_FUNCTIONS,
    ILLUSTRATION_FUNCTION_LABELS_HU,
    ILLUSTRATION_SOURCES,
    ILLUSTRATION_SOURCE_LABELS_HU,
    MAX_APPLICATIONS,
    MAX_ILLUSTRATIONS,
    MAX_TEXTUAL_IMAGES,
    PLACEMENT_KINDS,
    PLACEMENT_KIND_LABELS_HU,
    EnrichmentAssessmentResult,
    EnrichmentSuggestionResult,
    application_scope_label,
    assess_enrichment,
    illustration_function_label,
    illustration_source_label,
    image_function_label,
    normalize_application_scope,
    normalize_illustration_function,
    normalize_illustration_source,
    normalize_image_function,
    normalize_placement_kind,
    placement_kind_label,
    suggest_enrichment,
)
from sermon_workshop_m7_closing_ai import (
    CLOSING_TONES,
    CLOSING_TONE_LABELS_HU,
    CLOSING_TYPES,
    CLOSING_TYPE_LABELS_HU,
    ClosingAssessmentResult,
    ClosingSuggestionResult,
    assess_closing,
    closing_tone_label,
    closing_type_label,
    normalize_closing_tone,
    normalize_closing_type,
    suggest_closing,
)
from sermon_workshop_m8_ai import (
    DIAGNOSTIC_AREA_KEYS,
    HomileticalDiagnosticsResult,
    diagnostic_area_label,
    diagnostic_status_label,
    normalize_diagnostic_status,
    run_homiletical_diagnostics,
)
from sermon_workshop_m9_lection_ai import (
    LECTION_CONNECTION_TYPES,
    LECTION_LENGTH_PREFERENCES,
    LECTION_TESTAMENT_PREFERENCES,
    LECTION_CONNECTION_TYPE_LABELS_HU,
    LECTION_LENGTH_PREFERENCE_LABELS_HU,
    LECTION_TESTAMENT_PREFERENCE_LABELS_HU,
    LectionAssessmentResult,
    LectionCandidate,
    LectionSuggestionResult,
    assess_lection,
    lection_connection_type_label,
    references_equivalent,
    suggest_lections,
    validate_lection_reference,
)
from sermon_workshop_m9_prayer_ai import (
    PRAYER_REWRITE_MODES,
    PRAYER_REWRITE_MODE_LABELS_HU,
    PRAYER_TONE_PREFERENCES,
    PRAYER_TONE_PREFERENCE_LABELS_HU,
    PRAYER_TONE_UI_OPTIONS,
    adapt_prayer_suggestion_for_ui,
    assess_prayer_preparation,
    prayer_tone_preference_label,
    suggest_prayer_after,
    suggest_prayer_before,
)
from sermon_workshop_outline_ai import (
    assemble_sermon_outline,
    editable_outline_snapshot,
    outline_has_content,
    render_compact_sermon_outline,
)
from sermon_outline_diagnostics_ai import (
    MAX_REFINEMENTS,
    MAX_STRENGTHS,
    OutlineDiagnosticsResult,
    adapt_m8_to_outline_diagnostics,
    run_outline_diagnostics,
)
from textus_workshop_data import ensure_text_workshop_state
from workshop_nav_ui import render_section_stepper, sermon_completed_sections

GenerateFn = Callable[..., str]

_SW_SECTION_OPTIONS = [
    "Az igehirdetés fő gondolata",
    "Emberi helyzet és kegyelmi válasz",
    "Hallgatói kérdés és feszültség",
    "Krisztus-központú és evangéliumi ív",
    "Az igehirdetés útja és mozgásai",
    "Képek, illusztrációk és alkalmazás",
    "Lezárás és megérkezés",
    "Lekciójavaslat",
    "Imádsági előkészítés",
    "Igehirdetési vázlat",
    "Homiletikai diagnosztika",
]

_SW_SECTION_PLACEHOLDERS: dict[str, dict[str, str]] = {}

_SW_NEXT_HINTS: dict[str, str] = {
    "Az igehirdetés fő gondolata": (
        "Következő ajánlott lépés: Emberi helyzet és kegyelmi válasz"
    ),
    "Emberi helyzet és kegyelmi válasz": (
        "Következő ajánlott lépés: Hallgatói kérdés és feszültség"
    ),
    "Hallgatói kérdés és feszültség": (
        "Következő ajánlott lépés: Krisztus-központú és evangéliumi ív"
    ),
    "Krisztus-központú és evangéliumi ív": (
        "Következő ajánlott lépés: Az igehirdetés útja és mozgásai"
    ),
    "Az igehirdetés útja és mozgásai": (
        "Következő ajánlott lépés: Képek, illusztrációk és alkalmazás"
    ),
    "Képek, illusztrációk és alkalmazás": (
        "Következő ajánlott lépés: Lezárás és megérkezés"
    ),
    "Lezárás és megérkezés": (
        "Következő ajánlott lépés: Lekciójavaslat"
    ),
    "Lekciójavaslat": (
        "Következő ajánlott lépés: Imádsági előkészítés"
    ),
    "Imádsági előkészítés": (
        "Következő ajánlott lépés: Igehirdetési vázlat"
    ),
    "Igehirdetési vázlat": (
        "Következő ajánlott lépés: Homiletikai diagnosztika"
    ),
}

_STATUS_LABELS = {
    "draft": "Vázlat",
    "approved": "Jóváhagyva",
}

_SOURCE_SERMON_MAIN = "Az igehirdetés fő gondolata"
_SOURCE_HUMAN = "Emberi helyzet és kegyelmi válasz"
_SOURCE_LISTENER = "Hallgatói kérdés és feszültség"
_SOURCE_GOSPEL = "Krisztus-központú és evangéliumi ív"
_SOURCE_PATH = "Az igehirdetés útja és mozgásai"
_SOURCE_ENRICHMENT = "Képek, illusztrációk és alkalmazás"
_SOURCE_CLOSING = "Lezárás és megérkezés"
_SOURCE_LECTION = "Lekciójavaslat"
_SOURCE_PRAYER = "Imádsági előkészítés"
_SOURCE_OUTLINE = "Igehirdetési vázlat"
_CAT_MAIN_IDEA = "Fő gondolat"

_HC_FIELDS = [
    ("condition", "Milyen emberi helyzetet tár fel a textus?", "Emberi helyzet", False),
    (
        "false_response",
        "Milyen téves vagy elégtelen emberi válasz jelenik meg? (opcionális)",
        "Téves emberi válasz",
        True,
    ),
    ("human_need", "Mire van valójában szüksége az embernek?", "Emberi szükség", False),
    ("divine_action", "Mit cselekszik Isten ebben a helyzetben?", "Isten cselekvése", False),
    (
        "grace_response",
        "Milyen választ tesz lehetővé Isten kegyelme?",
        "Kegyelmi válasz",
        False,
    ),
]

_LT_FIELDS = [
    (
        "listener_question",
        "Hallgatói kérdés",
        (
            "Fogalmazd meg azt az őszinte kérdést, amely a textus hallgatása közben "
            "megszülethet a hallgatóban. Ne vizsgakérdés legyen, hanem valós, "
            "egzisztenciális vagy hitbeli kérdés."
        ),
        "Hogyan maradhatok meg a hitben, amikor körülöttem minden annak "
        "ellenkezőjét erősíti?",
        "Hallgatói kérdés",
    ),
    (
        "listener_resistance",
        "Hallgatói ellenállás",
        (
            "Nevezd meg röviden, miért nehéz a hallgatónak elfogadnia vagy "
            "megélnie azt, amit a textus állít. Kerüld az általánosítást és a "
            "hallgató elítélését."
        ),
        "Könnyebb a romboló környezetet hibáztatni, mint felelősséget vállalni "
        "a saját lelki épülésünkért.",
        "Hallgatói ellenállás",
    ),
    (
        "sermon_tension",
        "Központi feszültség",
        (
            "Fogalmazd meg egy világos mondatban a textus igazsága és a hallgató "
            "megélt valósága közötti feszültséget. Ez még ne legyen a feloldás."
        ),
        "Miközben Isten a hitben való megmaradásra hív, a hallgató gyakran úgy "
        "érzi, hogy a körülötte lévő romboló hatások erősebbek a benne lévő "
        "hitnél.",
        "Központi feszültség",
    ),
]

_GA_TEXT_FIELDS = [
    (
        "divine_gracious_action",
        "Isten kegyelmi cselekvése",
        (
            "Fogalmazd meg, mit tesz Isten a textusban, a textus ígéretében vagy a "
            "teljes bibliai összefüggésben. Ne csak azt írd le, mit kell tennie az "
            "embernek."
        ),
        "Isten nem hagyja magára a hitben megmaradásért küzdő gyülekezetet, "
        "hanem szeretetével körülveszi és irgalmában megtartja.",
        "Isten kegyelmi cselekvése",
    ),
    (
        "christ_connection",
        "Krisztus-kapcsolat",
        (
            "Fogalmazd meg, hogyan kapcsolódik a textus Krisztus személyéhez, "
            "munkájához vagy evangéliumához. Ne erőltesd a közvetlen kapcsolatot, "
            "ha a textus csak kánoni, üdvtörténeti vagy tematikus kapcsolatot "
            "alapoz meg."
        ),
        "A megtartó szeretet Krisztusban válik személyessé a gyülekezet számára.",
        "Krisztus-kapcsolat",
    ),
    (
        "promised_resolution",
        "Evangéliumi feloldás",
        (
            "Fogalmazd meg, hogyan válaszol Isten kegyelme a központi "
            "feszültségre. Ez ne legyen olcsó megoldás vagy gyors vallásos válasz, "
            "hanem a textusból és az evangéliumból fakadó valódi feloldás."
        ),
        "A romboló erők közepette Isten megtartó kegyelme ad valós reményt "
        "a megmaradásra.",
        "Evangéliumi feloldás",
    ),
    (
        "grace_enabled_response",
        "Kegyelemből fakadó válasz",
        (
            "Fogalmazd meg, milyen emberi válasz válik lehetővé Isten kegyelmi "
            "cselekvése által. Ne puszta kötelességet vagy moralizáló felszólítást adj."
        ),
        "A gyülekezet hittel ragaszkodhat Krisztushoz, és egymást is építheti.",
        "Kegyelemből fakadó válasz",
    ),
]

_GA_TYPE_HELP = (
    "Válaszd ki, milyen módon kapcsolódik a textus Krisztushoz. "
    "A közvetett vagy kánoni kapcsolat nem alacsonyabb rendű a közvetlennél."
)

_CONFIDENCE_LABELS_HU = {
    "high": "Magas bizonyosság",
    "medium": "Közepes bizonyosság",
    "low": "Alacsony bizonyosság / óvatosság",
}

_SERMON_ASSESSMENT_LABELS = [
    ("text_fidelity", "Textushűség"),
    ("hearability", "Hallhatóság"),
    ("unity", "Egység"),
    ("theological_accuracy", "Teológiai pontosság"),
    ("listener_relevance", "Hallgatói relevancia"),
    ("title_or_slogan_confusion", "Cím / szlogen kockázat"),
    ("application_confusion", "Alkalmazás-összekeverés"),
]

_HC_ASSESSMENT_LABELS = [
    ("text_fidelity", "Textushűség"),
    ("template_risk", "Sablon-kockázat"),
    ("divine_human_separation", "Isteni–emberi elkülönítés"),
    ("moralizing_risk", "Moralizálás kockázata"),
    ("false_response_appropriateness", "Téves válasz indokoltsága"),
    ("grace_grounding", "Kegyelmi megalapozottság"),
]

_HC_SUGGEST_DISPLAY = [
    ("human_condition", "Emberi helyzet"),
    ("false_response", "Téves vagy elégtelen válasz"),
    ("human_need", "Emberi szükség"),
    ("divine_action", "Isten cselekvése"),
    ("grace_response", "Kegyelmi válasz"),
]

# Widget / technikai kulcsok — nem project_data
_KEY_ACTIVE_SECTION = "sw_active_section"
_KEY_SERMON_IDEA = "sw_sermon_main_idea_input"
_KEY_HC = {
    "condition": "sw_hc_condition",
    "false_response": "sw_hc_false_response",
    "human_need": "sw_hc_human_need",
    "divine_action": "sw_hc_divine_action",
    "grace_response": "sw_hc_grace_response",
}
_KEY_LT = {
    "listener_question": "sw_lt_listener_question",
    "listener_resistance": "sw_lt_listener_resistance",
    "sermon_tension": "sw_lt_sermon_tension",
}
_KEY_GA = {
    "divine_gracious_action": "sw_ga_divine_gracious_action",
    "christ_connection": "sw_ga_christ_connection",
    "christ_connection_type": "sw_ga_christ_connection_type",
    "promised_resolution": "sw_ga_promised_resolution",
    "grace_enabled_response": "sw_ga_grace_enabled_response",
}
_KEY_PATH = {
    "type": "sw_path_type",
    "reason": "sw_path_reason",
    "starting_point": "sw_path_starting_point",
    "destination": "sw_path_destination",
}
_RESYNC_FLAG = "_sw_ui_resync"
_ADOPT_SERMON_PENDING = "_sw_sermon_idea_adopt_pending"
_ADOPT_HC_PENDING = "_sw_hc_adopt_pending"
_ADOPT_LT_PENDING = "_sw_lt_adopt_pending"
_ADOPT_GA_PENDING = "_sw_ga_adopt_pending"
_ADOPT_PATH_PENDING = "_sw_path_adopt_pending"
_ADOPT_MOVEMENTS_PENDING = "_sw_movements_adopt_pending"
_MV_DELETE_PENDING = "_sw_mv_delete_pending"
_MV_WIDGET_PREFIX = "sw_mv_"
_IMG_WIDGET_PREFIX = "sw_en_img_"
_ILL_WIDGET_PREFIX = "sw_en_ill_"
_APP_WIDGET_PREFIX = "sw_en_app_"
_ADOPT_EN_ALL_PENDING = "_sw_en_adopt_all_pending"
_ADOPT_EN_IMAGES_PENDING = "_sw_en_adopt_images_pending"
_ADOPT_EN_ILL_PENDING = "_sw_en_adopt_ill_pending"
_ADOPT_EN_APPS_PENDING = "_sw_en_adopt_apps_pending"
_ADOPT_CL_PENDING = "_sw_cl_adopt_pending"
_ADOPT_LECTION_PENDING = "_sw_lection_adopt_pending"
_LECTION_RUF_PENDING = "_sw_lection_ruf_pending"
_ADOPT_PRAYER_PENDING = "_sw_prayer_adopt_pending"
_KEY_DIAG = {
    "self_review_strengths": "sw_diag_self_strengths",
    "self_review_uncertainties": "sw_diag_self_uncertainties",
    "self_review_priority": "sw_diag_self_priority",
    "self_review_focus": "sw_diag_self_focus",
}
_KEY_CL = {
    "type": "sw_cl_type",
    "final_discovery": "sw_cl_final_discovery",
    "hope": "sw_cl_hope",
    "call_or_response": "sw_cl_call_or_response",
    "image_or_line": "sw_cl_image_or_line",
    "open_question": "sw_cl_open_question",
    "tone": "sw_cl_tone",
}
_KEY_LECTION = {
    "reference": "sw_lection_reference",
    "connection_type": "sw_lection_connection_type",
    "function": "sw_lection_function",
    "rationale": "sw_lection_rationale",
    "text": "sw_lection_text",
    "notes": "sw_lection_notes",
    "testament_preference": "sw_lection_testament_preference",
    "length_preference": "sw_lection_length_preference",
    "user_focus": "sw_lection_user_focus",
}
DEFAULT_LECTION_CONNECTION_UI = "thematic"
DEFAULT_LECTION_TESTAMENT_UI = "any"
DEFAULT_LECTION_LENGTH_UI = "standard"
_KEY_PRAYER_COMMON = {
    "tone_preference": "sw_prayer_tone",
    "general_focus": "sw_prayer_general_focus",
    "rewrite_mode": "sw_prayer_rewrite_mode",
}
_KEY_PRAYER_BEFORE = {
    "own_thoughts": "sw_prayer_before_own_thoughts",
    "purpose": "sw_prayer_before_purpose",
    "movement_notes": "sw_prayer_before_movement_notes",
    "selected_opening": "sw_prayer_before_selected_opening",
    "selected_lines": "sw_prayer_before_selected_lines",
    "closing_direction": "sw_prayer_before_closing_direction",
}
_KEY_PRAYER_AFTER = {
    "own_thoughts": "sw_prayer_after_own_thoughts",
    "purpose": "sw_prayer_after_purpose",
    "movement_notes": "sw_prayer_after_movement_notes",
    "selected_opening": "sw_prayer_after_selected_opening",
    "selected_lines": "sw_prayer_after_selected_lines",
    "closing_direction": "sw_prayer_after_closing_direction",
}
_KEY_OUTLINE = {
    "main_idea": "sw_outline_main_idea",
    "main_idea_summary": "sw_outline_main_idea_summary",
    "listener_question": "sw_outline_listener_question",
    "central_tension": "sw_outline_central_tension",
    "listener_resistance": "sw_outline_listener_resistance",
    "divine_gracious_action": "sw_outline_divine_action",
    "christ_connection": "sw_outline_christ_connection",
    "christ_connection_type_label": "sw_outline_christ_type",
    "gospel_resolution": "sw_outline_gospel_resolution",
    "grace_enabled_response": "sw_outline_grace_response",
    "opening_direction": "sw_outline_opening",
    "manual_notes": "sw_outline_manual_notes",
}
_KEY_OUTLINE_CLOSING = {
    "final_insight": "sw_outline_closing_final",
    "gospel_assurance": "sw_outline_closing_hope",
    "invitation": "sw_outline_closing_invitation",
    "image_or_line": "sw_outline_closing_image",
    "open_question": "sw_outline_closing_question",
    "tone_label": "sw_outline_closing_tone",
}
_KEY_OUTLINE_LECTION = {
    "reference": "sw_outline_lection_ref",
    "function": "sw_outline_lection_function",
    "rationale": "sw_outline_lection_rationale",
}
_KEY_OUTLINE_PRAYER_BEFORE = {
    "own_thoughts": "sw_outline_prayer_before_own",
    "selected_opening": "sw_outline_prayer_before_opening",
    "selected_lines": "sw_outline_prayer_before_lines",
    "closing_direction": "sw_outline_prayer_before_closing",
}
_KEY_OUTLINE_PRAYER_AFTER = {
    "own_thoughts": "sw_outline_prayer_after_own",
    "selected_opening": "sw_outline_prayer_after_opening",
    "selected_lines": "sw_outline_prayer_after_lines",
    "closing_direction": "sw_outline_prayer_after_closing",
}
_OUTLINE_MV_PREFIX = "sw_outline_mv_"
_CONFIRM_OUTLINE_OVERWRITE = "_sw_outline_confirm_overwrite"
DEFAULT_PRAYER_TONE_UI = "mixed"
DEFAULT_PRAYER_REWRITE_UI = "integrate_into_arc"
_CL_FIELDS = (
    ("type", "Lezárás iránya", "", False),
    (
        "final_discovery",
        "Végső felismerés",
        "Fogalmazd meg egyetlen világos mondatban, mit lásson másként a "
        "hallgató az igehirdetés végére.",
        False,
    ),
    (
        "hope",
        "Evangéliumi bizonyosság",
        "Mi az az isteni ígéret, kegyelmi valóság vagy Krisztusban adott "
        "bizonyosság, amelyre a hallgató támaszkodhat?",
        False,
    ),
    (
        "call_or_response",
        "Kegyelemből fakadó meghívás",
        "Milyen válaszra hívhatja az Ige a hallgatót Isten kegyelmi "
        "cselekvésének fényében? Ne parancslistát írj, hanem egy világos, "
        "megélhető irányt.",
        True,
    ),
    (
        "image_or_line",
        "Záró kép vagy mondatmag",
        "Adj egy rövid kép- vagy mondatmagot a lezárás megfogalmazásához. "
        "Ez még ne legyen teljes kész záróbekezdés.",
        True,
    ),
    (
        "open_question",
        "Nyitva maradó kérdés",
        "Ha indokolt, fogalmazz meg egy őszinte kérdést, amely tovább "
        "dolgozhat a hallgatóban. Ne tartalmazza előre a választ.",
        True,
    ),
    ("tone", "Hangnem", "", False),
)
DEFAULT_CLOSING_TYPE_UI = "gospel_assurance"
DEFAULT_CLOSING_TONE_UI = "hopeful"
_EN_IMG_DELETE_PENDING = "_sw_en_img_delete_pending"
_EN_ILL_DELETE_PENDING = "_sw_en_ill_delete_pending"
_EN_APP_DELETE_PENDING = "_sw_en_app_delete_pending"
_IMG_FIELDS = (
    "image",
    "textual_basis",
    "homiletical_function",
    "placement",
    "movement_id",
    "development_notes",
)
_ILL_FIELDS = (
    "idea",
    "source",
    "function",
    "placement",
    "movement_id",
    "connection_to_text",
    "risk_or_limit",
)
_APP_FIELDS = (
    "application",
    "scope",
    "gospel_basis",
    "concreteness",
    "placement",
    "movement_id",
    "pastoral_caution",
)
_MV_FIELDS = (
    "title",
    "role",
    "core_content",
    "textual_basis",
    "listener_discovery",
    "transition_to_next",
)

_HC_PROMPT_TO_UI = {
    "human_condition": "condition",
    "false_response": "false_response",
    "human_need": "human_need",
    "divine_action": "divine_action",
    "grace_response": "grace_response",
}


def _session_str(*keys: str) -> str:
    for key in keys:
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _session_passage_text() -> str:
    """Központi passage_text; mentés előtt a szerkesztő widget is elfogadható."""
    for key in ("passage_text", "passage_text_input"):
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.replace("\r\n", "\n").replace("\r", "\n")
    return ""


def _apply_pending_adopts_if_needed() -> None:
    """Átvétel: widget ELŐTT (pending + rerun). Nem hagy jóvá automatikusan."""
    pending_idea = st.session_state.pop(_ADOPT_SERMON_PENDING, None)
    if pending_idea is not None:
        text = str(pending_idea).strip()
        st.session_state[_KEY_SERMON_IDEA] = text
        update_sermon_workshop_section(
            st.session_state,
            "sermon_main_idea",
            {
                "sermon_main_idea": text,
                "sermon_main_idea_status": "draft",
            },
        )

    pending_hc = st.session_state.pop(_ADOPT_HC_PENDING, None)
    if isinstance(pending_hc, dict):
        # Csak nem üres javasolt mezőket írjuk; üres javaslat ne töröljön.
        for ui_key, wkey in _KEY_HC.items():
            suggested = str(pending_hc.get(ui_key) or "").strip()
            if suggested:
                st.session_state[wkey] = suggested
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_HC.items()
        }
        update_sermon_workshop_section(st.session_state, "human_condition", block)

    pending_lt = st.session_state.pop(_ADOPT_LT_PENDING, None)
    if isinstance(pending_lt, dict):
        for ui_key, wkey in _KEY_LT.items():
            suggested = str(pending_lt.get(ui_key) or "").strip()
            if suggested:
                st.session_state[wkey] = suggested
        # Preserve promised_resolution from durable data
        sw = ensure_sermon_workshop_state(st.session_state)
        current = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_LT.items()
        }
        block["promised_resolution"] = str(current.get("promised_resolution") or "")
        update_sermon_workshop_section(st.session_state, "listener_tension", block)

    pending_ga = st.session_state.pop(_ADOPT_GA_PENDING, None)
    if isinstance(pending_ga, dict):
        for ui_key, wkey in _KEY_GA.items():
            suggested = str(pending_ga.get(ui_key) or "").strip()
            if not suggested:
                continue
            if ui_key == "christ_connection_type":
                st.session_state[wkey] = normalize_christ_connection_type(suggested)
            else:
                st.session_state[wkey] = suggested
        _persist_gospel_arc_from_widgets()

    pending_path = st.session_state.pop(_ADOPT_PATH_PENDING, None)
    if isinstance(pending_path, dict):
        for ui_key, wkey in _KEY_PATH.items():
            if ui_key not in pending_path:
                continue
            suggested = str(pending_path.get(ui_key) or "").strip()
            if ui_key == "type":
                st.session_state[wkey] = normalize_sermon_path_type(suggested)
            elif suggested:
                st.session_state[wkey] = suggested
        _persist_sermon_path_from_widgets()

    pending_mvs = st.session_state.pop(_ADOPT_MOVEMENTS_PENDING, None)
    if isinstance(pending_mvs, list):
        normalized = normalize_sermon_movements(pending_mvs)
        update_sermon_workshop_section(
            st.session_state, "sermon_movements", normalized
        )
        _clear_movement_widgets()
        st.session_state[_RESYNC_FLAG] = True

    pending_en_all = st.session_state.pop(_ADOPT_EN_ALL_PENDING, None)
    if isinstance(pending_en_all, dict):
        if pending_en_all.get("images") is not None:
            update_sermon_workshop_section(
                st.session_state,
                "selected_images",
                normalize_textual_images(pending_en_all.get("images")),
            )
            _clear_enrichment_widgets("images")
        if pending_en_all.get("illustrations") is not None:
            update_sermon_workshop_section(
                st.session_state,
                "illustrations",
                normalize_illustrations(pending_en_all.get("illustrations")),
            )
            _clear_enrichment_widgets("illustrations")
        if pending_en_all.get("applications") is not None:
            update_sermon_workshop_section(
                st.session_state,
                "applications",
                normalize_applications(pending_en_all.get("applications")),
            )
            _clear_enrichment_widgets("applications")
        st.session_state[_RESYNC_FLAG] = True

    pending_en_imgs = st.session_state.pop(_ADOPT_EN_IMAGES_PENDING, None)
    if isinstance(pending_en_imgs, list):
        update_sermon_workshop_section(
            st.session_state, "selected_images", normalize_textual_images(pending_en_imgs)
        )
        _clear_enrichment_widgets("images")
        st.session_state[_RESYNC_FLAG] = True

    pending_en_ills = st.session_state.pop(_ADOPT_EN_ILL_PENDING, None)
    if isinstance(pending_en_ills, list):
        update_sermon_workshop_section(
            st.session_state, "illustrations", normalize_illustrations(pending_en_ills)
        )
        _clear_enrichment_widgets("illustrations")
        st.session_state[_RESYNC_FLAG] = True

    pending_en_apps = st.session_state.pop(_ADOPT_EN_APPS_PENDING, None)
    if isinstance(pending_en_apps, list):
        update_sermon_workshop_section(
            st.session_state, "applications", normalize_applications(pending_en_apps)
        )
        _clear_enrichment_widgets("applications")
        st.session_state[_RESYNC_FLAG] = True

    pending_cl = st.session_state.pop(_ADOPT_CL_PENDING, None)
    if isinstance(pending_cl, dict):
        for ui_key, wkey in _KEY_CL.items():
            suggested = str(pending_cl.get(ui_key) or "").strip()
            if not suggested:
                continue
            if ui_key == "type":
                st.session_state[wkey] = normalize_closing_type(suggested)
            elif ui_key == "tone":
                st.session_state[wkey] = normalize_closing_tone(suggested)
            else:
                st.session_state[wkey] = suggested
        _persist_closing_from_widgets()

    pending_lection = st.session_state.pop(_ADOPT_LECTION_PENDING, None)
    if isinstance(pending_lection, dict):
        for ui_key, wkey in _KEY_LECTION.items():
            if ui_key not in pending_lection:
                continue
            suggested = str(pending_lection.get(ui_key) or "").strip()
            if ui_key == "connection_type":
                st.session_state[wkey] = (
                    normalize_lection_connection_type(suggested)
                    if suggested
                    else DEFAULT_LECTION_CONNECTION_UI
                )
            elif ui_key == "testament_preference":
                st.session_state[wkey] = normalize_lection_testament_preference(
                    suggested
                )
            elif ui_key == "length_preference":
                st.session_state[wkey] = normalize_lection_length_preference(
                    suggested
                )
            elif suggested or ui_key in (
                "reference",
                "function",
                "rationale",
                "notes",
            ):
                # Átvétel: csak a választott mezőket írja; textet nem törli itt
                if ui_key == "text":
                    continue
                st.session_state[wkey] = suggested
        _persist_lection_from_widgets(include_text=False)

    pending_prayer = st.session_state.pop(_ADOPT_PRAYER_PENDING, None)
    if isinstance(pending_prayer, dict):
        side = str(pending_prayer.get("side") or "before").strip()
        keys = _KEY_PRAYER_BEFORE if side != "after" else _KEY_PRAYER_AFTER
        # own_thoughts soha nem törlődik átvételkor
        if "purpose" in pending_prayer:
            val = str(pending_prayer.get("purpose") or "").strip()
            if val:
                st.session_state[keys["purpose"]] = val
        if "movement_notes" in pending_prayer:
            val = str(pending_prayer.get("movement_notes") or "").strip()
            if val:
                st.session_state[keys["movement_notes"]] = val
        if "selected_opening" in pending_prayer:
            val = str(pending_prayer.get("selected_opening") or "").strip()
            if val:
                st.session_state[keys["selected_opening"]] = val
        if "closing_direction" in pending_prayer:
            val = str(pending_prayer.get("closing_direction") or "").strip()
            if val:
                st.session_state[keys["closing_direction"]] = val
        if "selected_lines" in pending_prayer:
            raw_lines = pending_prayer.get("selected_lines")
            if isinstance(raw_lines, list):
                lines = [str(x).strip() for x in raw_lines if str(x).strip()]
            else:
                lines = _lines_from_widget(raw_lines)
            # Teljes terv átvétele: cserél, ne duplikál
            st.session_state[keys["selected_lines"]] = "\n".join(lines)
        else:
            append_line = str(pending_prayer.get("append_line") or "").strip()
            if append_line:
                current = str(st.session_state.get(keys["selected_lines"]) or "")
                lines = [
                    ln.strip()
                    for ln in current.replace("\r\n", "\n").split("\n")
                    if ln.strip()
                ]
                if append_line not in lines:
                    lines.append(append_line)
                st.session_state[keys["selected_lines"]] = "\n".join(lines)
        _persist_prayer_from_widgets()


def _en_widget_key(prefix: str, item_id: str, field: str) -> str:
    return f"{prefix}{item_id}_{field}"


def _clear_enrichment_widgets(kind: str | None = None) -> None:
    prefixes: tuple[str, ...]
    if kind == "images":
        prefixes = (_IMG_WIDGET_PREFIX,)
    elif kind == "illustrations":
        prefixes = (_ILL_WIDGET_PREFIX,)
    elif kind == "applications":
        prefixes = (_APP_WIDGET_PREFIX,)
    else:
        prefixes = (_IMG_WIDGET_PREFIX, _ILL_WIDGET_PREFIX, _APP_WIDGET_PREFIX)
    stale = [
        key
        for key in list(st.session_state.keys())
        if isinstance(key, str) and key.startswith(prefixes)
    ]
    for key in stale:
        st.session_state.pop(key, None)


def _movement_options() -> list[tuple[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    mvs = normalize_sermon_movements(sw.get("sermon_movements"))
    options: list[tuple[str, str]] = [("", "— nincs mozgáskapcsolat —")]
    for idx, mv in enumerate(mvs, start=1):
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        title = str(mv.get("title") or f"Mozgás {idx}").strip()
        role = movement_role_label(mv.get("role"))
        options.append((mid, f"{idx}. {title} ({role})"))
    return options


def _read_textual_images_from_widgets() -> list[dict[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_textual_images(sw.get("selected_images"))
    out: list[dict[str, str]] = []
    for item in current:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        row = dict(item)
        for field in _IMG_FIELDS:
            wkey = _en_widget_key(_IMG_WIDGET_PREFIX, iid, field)
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey)
            if field == "homiletical_function":
                row[field] = normalize_image_function(raw)
            elif field == "placement":
                row[field] = normalize_placement_kind(raw)
            else:
                row[field] = str(raw or "").strip()
        out.append(row)
    return out


def _read_illustrations_from_widgets() -> list[dict[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_illustrations(sw.get("illustrations"))
    out: list[dict[str, str]] = []
    for item in current:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        row = dict(item)
        for field in _ILL_FIELDS:
            wkey = _en_widget_key(_ILL_WIDGET_PREFIX, iid, field)
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey)
            if field == "source":
                row[field] = normalize_illustration_source(raw)
            elif field == "function":
                row[field] = normalize_illustration_function(raw)
            elif field == "placement":
                row[field] = normalize_placement_kind(raw)
            else:
                row[field] = str(raw or "").strip()
        out.append(row)
    return out


def _read_applications_from_widgets() -> list[dict[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_applications(sw.get("applications"))
    out: list[dict[str, str]] = []
    for item in current:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        row = dict(item)
        for field in _APP_FIELDS:
            wkey = _en_widget_key(_APP_WIDGET_PREFIX, iid, field)
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey)
            if field == "scope":
                row[field] = normalize_application_scope(raw)
            elif field == "placement":
                row[field] = normalize_placement_kind(raw)
            else:
                row[field] = str(raw or "").strip()
        out.append(row)
    return out


def _persist_enrichment_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "selected_images", _read_textual_images_from_widgets()
    )
    update_sermon_workshop_section(
        st.session_state, "illustrations", _read_illustrations_from_widgets()
    )
    update_sermon_workshop_section(
        st.session_state, "applications", _read_applications_from_widgets()
    )


def _existing_source_refs() -> set[str]:
    sw = ensure_sermon_workshop_state(st.session_state)
    refs: set[str] = set()
    for key in ("selected_images", "illustrations", "applications"):
        for item in sw.get(key) or []:
            if isinstance(item, dict):
                ref = str(item.get("source_ref") or "").strip()
                if ref:
                    refs.add(ref)
    return refs


def _collect_text_workshop_import_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    basket = st.session_state.get("basket") or []
    if isinstance(basket, list):
        for idx, entry in enumerate(basket):
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            source, text = str(entry[0] or ""), str(entry[1] or "").strip()
            if not text:
                continue
            if source == "Illusztráció":
                items.append(
                    {
                        "kind": "illustration",
                        "label": f"Illusztráció ({idx + 1})",
                        "content": text,
                        "source_ref": f"basket:Illusztráció:{idx}",
                    }
                )
            elif source == "Aktualizálás":
                items.append(
                    {
                        "kind": "application",
                        "label": f"Aktualizálás ({idx + 1})",
                        "content": text,
                        "source_ref": f"basket:Aktualizálás:{idx}",
                    }
                )
    tw = ensure_text_workshop_state(st.session_state)
    for insight in tw.get("approved_insights") or []:
        if not isinstance(insight, dict):
            continue
        content = str(insight.get("content") or "").strip()
        iid = str(insight.get("id") or "").strip()
        if not content:
            continue
        items.append(
            {
                "kind": "application",
                "label": f"Jóváhagyott felismerés ({insight.get('category') or '—'})",
                "content": content,
                "source_ref": f"insight:{iid or content[:40]}",
            }
        )
    return items


def _request_adopt_enrichment_plan(
    *,
    images: list[dict[str, str]] | None = None,
    illustrations: list[dict[str, str]] | None = None,
    applications: list[dict[str, str]] | None = None,
) -> None:
    st.session_state[_ADOPT_EN_ALL_PENDING] = {
        "images": images,
        "illustrations": illustrations,
        "applications": applications,
    }
    st.rerun()


def _request_adopt_enrichment_images(images: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_EN_IMAGES_PENDING] = list(images or [])
    st.rerun()


def _request_adopt_enrichment_illustrations(items: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_EN_ILL_PENDING] = list(items or [])
    st.rerun()


def _request_adopt_enrichment_applications(items: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_EN_APPS_PENDING] = list(items or [])
    st.rerun()


def _append_enrichment_item(kind: str) -> None:
    _persist_enrichment_from_widgets()
    sw = ensure_sermon_workshop_state(st.session_state)
    if kind == "images":
        current = normalize_textual_images(sw.get("selected_images"))
        if len(current) >= MAX_TEXTUAL_IMAGES:
            return
        current.append(empty_textual_image())
        update_sermon_workshop_section(st.session_state, "selected_images", current)
    elif kind == "illustrations":
        current = normalize_illustrations(sw.get("illustrations"))
        if len(current) >= MAX_ILLUSTRATIONS:
            return
        current.append(empty_illustration())
        update_sermon_workshop_section(st.session_state, "illustrations", current)
    else:
        current = normalize_applications(sw.get("applications"))
        if len(current) >= MAX_APPLICATIONS:
            return
        current.append(empty_application())
        update_sermon_workshop_section(st.session_state, "applications", current)
    st.session_state[_RESYNC_FLAG] = True


def _sync_enrichment_widgets(
    *,
    force: bool,
    images: list[dict[str, str]],
    illustrations: list[dict[str, str]],
    applications: list[dict[str, str]],
) -> None:
    if force:
        _clear_enrichment_widgets()
    live_img = {str(i.get("id") or "") for i in images if i.get("id")}
    live_ill = {str(i.get("id") or "") for i in illustrations if i.get("id")}
    live_app = {str(i.get("id") or "") for i in applications if i.get("id")}
    if not force:
        for prefix, live_ids in (
            (_IMG_WIDGET_PREFIX, live_img),
            (_ILL_WIDGET_PREFIX, live_ill),
            (_APP_WIDGET_PREFIX, live_app),
        ):
            stale = [
                key
                for key in list(st.session_state.keys())
                if isinstance(key, str)
                and key.startswith(prefix)
                and not any(
                    key.startswith(f"{prefix}{iid}_") for iid in live_ids
                )
            ]
            for key in stale:
                st.session_state.pop(key, None)
    mv_options = _movement_options()
    mv_ids = [mid for mid, _label in mv_options if mid]
    for item in images:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        for field in _IMG_FIELDS:
            wkey = _en_widget_key(_IMG_WIDGET_PREFIX, iid, field)
            if force or wkey not in st.session_state:
                if field == "homiletical_function":
                    raw = str(item.get(field) or "").strip()
                    st.session_state[wkey] = (
                        normalize_image_function(raw) if raw else "open"
                    )
                elif field == "placement":
                    st.session_state[wkey] = normalize_placement_kind(
                        item.get(field)
                    )
                elif field == "movement_id":
                    mid = str(item.get("movement_id") or "")
                    st.session_state[wkey] = mid if mid in mv_ids else ""
                else:
                    st.session_state[wkey] = str(item.get(field) or "")
    for item in illustrations:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        for field in _ILL_FIELDS:
            wkey = _en_widget_key(_ILL_WIDGET_PREFIX, iid, field)
            if force or wkey not in st.session_state:
                if field == "source":
                    st.session_state[wkey] = normalize_illustration_source(
                        item.get(field)
                    )
                elif field == "function":
                    raw = str(item.get(field) or "").strip()
                    st.session_state[wkey] = (
                        normalize_illustration_function(raw) if raw else "bridge"
                    )
                elif field == "placement":
                    st.session_state[wkey] = normalize_placement_kind(
                        item.get(field)
                    )
                elif field == "movement_id":
                    mid = str(item.get("movement_id") or "")
                    st.session_state[wkey] = mid if mid in mv_ids else ""
                else:
                    st.session_state[wkey] = str(item.get(field) or "")
    for item in applications:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        for field in _APP_FIELDS:
            wkey = _en_widget_key(_APP_WIDGET_PREFIX, iid, field)
            if force or wkey not in st.session_state:
                if field == "scope":
                    st.session_state[wkey] = normalize_application_scope(
                        item.get(field)
                    )
                elif field == "placement":
                    st.session_state[wkey] = normalize_placement_kind(
                        item.get(field)
                    )
                elif field == "movement_id":
                    mid = str(item.get("movement_id") or "")
                    st.session_state[wkey] = mid if mid in mv_ids else ""
                else:
                    st.session_state[wkey] = str(item.get(field) or "")


def _mv_widget_key(movement_id: str, field: str) -> str:
    return f"{_MV_WIDGET_PREFIX}{movement_id}_{field}"


def _clear_movement_widgets() -> None:
    stale = [
        key
        for key in list(st.session_state.keys())
        if isinstance(key, str) and key.startswith(_MV_WIDGET_PREFIX)
    ]
    for key in stale:
        st.session_state.pop(key, None)


def _persist_gospel_arc_from_widgets() -> None:
    """Widgetek → christ_centered_arc + listener_tension.promised_resolution."""
    sw = ensure_sermon_workshop_state(st.session_state)
    arc = {
        "divine_gracious_action": (
            st.session_state.get(_KEY_GA["divine_gracious_action"]) or ""
        ).strip(),
        "christ_connection": (
            st.session_state.get(_KEY_GA["christ_connection"]) or ""
        ).strip(),
        "christ_connection_type": normalize_christ_connection_type(
            st.session_state.get(_KEY_GA["christ_connection_type"])
        ),
        "grace_enabled_response": (
            st.session_state.get(_KEY_GA["grace_enabled_response"]) or ""
        ).strip(),
    }
    update_sermon_workshop_section(st.session_state, "christ_centered_arc", arc)
    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    lt_block = {
        "listener_question": str(lt.get("listener_question") or ""),
        "listener_resistance": str(lt.get("listener_resistance") or ""),
        "sermon_tension": str(lt.get("sermon_tension") or ""),
        "promised_resolution": (
            st.session_state.get(_KEY_GA["promised_resolution"]) or ""
        ).strip(),
    }
    update_sermon_workshop_section(st.session_state, "listener_tension", lt_block)


def _persist_sermon_path_from_widgets() -> None:
    """Widgetek → sermon_path (type/reason/starting_point/destination)."""
    path = {
        "type": normalize_sermon_path_type(
            st.session_state.get(_KEY_PATH["type"])
        ),
        "reason": (st.session_state.get(_KEY_PATH["reason"]) or "").strip(),
        "starting_point": (
            st.session_state.get(_KEY_PATH["starting_point"]) or ""
        ).strip(),
        "destination": (
            st.session_state.get(_KEY_PATH["destination"]) or ""
        ).strip(),
    }
    update_sermon_workshop_section(st.session_state, "sermon_path", path)


def _read_movements_from_widgets() -> list[dict[str, str]]:
    """Tartós sorrend + widgetértékek → mozgáslista."""
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_sermon_movements(sw.get("sermon_movements"))
    out: list[dict[str, str]] = []
    for mv in current:
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        item = dict(mv)
        for field in _MV_FIELDS:
            wkey = _mv_widget_key(mid, field)
            if wkey in st.session_state:
                raw = st.session_state.get(wkey)
                if field == "role":
                    item[field] = normalize_movement_role(raw)
                else:
                    item[field] = str(raw or "").strip()
        out.append(item)
    return out


def _persist_sermon_movements_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "sermon_movements", _read_movements_from_widgets()
    )


def _apply_sw_ui_resync_if_needed() -> None:
    """Widgetkulcsok szinkronja a tartós sermon_workshop adatokkal (widget előtt)."""
    sw = ensure_sermon_workshop_state(st.session_state)
    force = bool(st.session_state.pop(_RESYNC_FLAG, False))

    idea = sw.get("sermon_main_idea") or ""
    if force or _KEY_SERMON_IDEA not in st.session_state:
        st.session_state[_KEY_SERMON_IDEA] = idea

    hc = sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    for field, wkey in _KEY_HC.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(hc.get(field) or "")

    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    for field, wkey in _KEY_LT.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(lt.get(field) or "")

    arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    for field, wkey in _KEY_GA.items():
        if force or wkey not in st.session_state:
            if field == "promised_resolution":
                st.session_state[wkey] = str(lt.get("promised_resolution") or "")
            elif field == "christ_connection_type":
                raw = str(arc.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_christ_connection_type(raw)
                    if raw
                    else "none_or_uncertain"
                )
            else:
                st.session_state[wkey] = str(arc.get(field) or "")

    path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    for field, wkey in _KEY_PATH.items():
        if force or wkey not in st.session_state:
            if field == "type":
                raw = str(path.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_sermon_path_type(raw) if raw else "text_following"
                )
            else:
                st.session_state[wkey] = str(path.get(field) or "")

    movements = normalize_sermon_movements(sw.get("sermon_movements"))
    live_ids = {str(m.get("id") or "") for m in movements if m.get("id")}
    if force:
        _clear_movement_widgets()
    else:
        stale = [
            key
            for key in list(st.session_state.keys())
            if isinstance(key, str)
            and key.startswith(_MV_WIDGET_PREFIX)
            and not any(
                key.startswith(f"{_MV_WIDGET_PREFIX}{mid}_") for mid in live_ids
            )
        ]
        for key in stale:
            st.session_state.pop(key, None)
    for mv in movements:
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        for field in _MV_FIELDS:
            wkey = _mv_widget_key(mid, field)
            if force or wkey not in st.session_state:
                if field == "role":
                    raw = str(mv.get(field) or "").strip()
                    st.session_state[wkey] = (
                        normalize_movement_role(raw) if raw else "deepening"
                    )
                else:
                    st.session_state[wkey] = str(mv.get(field) or "")

    images = normalize_textual_images(sw.get("selected_images"))
    illustrations = normalize_illustrations(sw.get("illustrations"))
    applications = normalize_applications(sw.get("applications"))
    _sync_enrichment_widgets(
        force=force,
        images=images,
        illustrations=illustrations,
        applications=applications,
    )

    closing = sw.get("closing") if isinstance(sw.get("closing"), dict) else {}
    for field, wkey in _KEY_CL.items():
        if force or wkey not in st.session_state:
            if field == "type":
                raw = str(closing.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_closing_type(raw) if raw else DEFAULT_CLOSING_TYPE_UI
                )
            elif field == "tone":
                raw = str(closing.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_closing_tone(raw) if raw else DEFAULT_CLOSING_TONE_UI
                )
            else:
                st.session_state[wkey] = str(closing.get(field) or "")

    for field, wkey in _KEY_DIAG.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(sw.get(field) or "")

    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    for field, wkey in _KEY_LECTION.items():
        if force or wkey not in st.session_state:
            if field == "connection_type":
                raw = str(lection.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_lection_connection_type(raw) if raw else ""
                )
            elif field == "testament_preference":
                st.session_state[wkey] = normalize_lection_testament_preference(
                    lection.get(field)
                )
            elif field == "length_preference":
                st.session_state[wkey] = normalize_lection_length_preference(
                    lection.get(field)
                )
            elif field == "text":
                st.session_state[wkey] = normalize_passage_text(lection.get(field))
            else:
                st.session_state[wkey] = str(lection.get(field) or "")

    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    for field, wkey in _KEY_PRAYER_COMMON.items():
        if force or wkey not in st.session_state:
            if field == "tone_preference":
                st.session_state[wkey] = normalize_prayer_tone_preference(
                    prep.get(field)
                )
            elif field == "rewrite_mode":
                st.session_state[wkey] = normalize_prayer_rewrite_mode(
                    prep.get(field)
                )
            else:
                st.session_state[wkey] = str(prep.get(field) or "")
    before = prep.get("before") if isinstance(prep.get("before"), dict) else {}
    after = prep.get("after") if isinstance(prep.get("after"), dict) else {}
    for side_data, key_map in (
        (before, _KEY_PRAYER_BEFORE),
        (after, _KEY_PRAYER_AFTER),
    ):
        for field, wkey in key_map.items():
            if force or wkey not in st.session_state:
                if field == "selected_lines":
                    lines = side_data.get("selected_lines")
                    if isinstance(lines, list):
                        st.session_state[wkey] = "\n".join(
                            str(x).strip() for x in lines if str(x).strip()
                        )
                    else:
                        st.session_state[wkey] = str(lines or "")
                else:
                    st.session_state[wkey] = str(side_data.get(field) or "")

    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    for field, wkey in _KEY_OUTLINE.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(outline.get(field) or "")
    closing_o = outline.get("closing") if isinstance(outline.get("closing"), dict) else {}
    for field, wkey in _KEY_OUTLINE_CLOSING.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(closing_o.get(field) or "")
    lection_o = outline.get("lection") if isinstance(outline.get("lection"), dict) else {}
    for field, wkey in _KEY_OUTLINE_LECTION.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(lection_o.get(field) or "")
    for side_key, key_map in (
        ("prayer_before", _KEY_OUTLINE_PRAYER_BEFORE),
        ("prayer_after", _KEY_OUTLINE_PRAYER_AFTER),
    ):
        side = outline.get(side_key) if isinstance(outline.get(side_key), dict) else {}
        for field, wkey in key_map.items():
            if force or wkey not in st.session_state:
                if field == "selected_lines":
                    lines = side.get("selected_lines")
                    if isinstance(lines, list):
                        st.session_state[wkey] = "\n".join(
                            str(x).strip() for x in lines if str(x).strip()
                        )
                    else:
                        st.session_state[wkey] = str(lines or "")
                else:
                    st.session_state[wkey] = str(side.get(field) or "")
    movements_o = outline.get("movements") if isinstance(outline.get("movements"), list) else []
    if force:
        for key in list(st.session_state.keys()):
            if isinstance(key, str) and key.startswith(_OUTLINE_MV_PREFIX):
                st.session_state.pop(key, None)
    for mv in movements_o:
        if not isinstance(mv, dict):
            continue
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        for field in (
            "title",
            "role_label",
            "textual_basis",
            "core_content",
            "listener_discovery",
            "transition",
            "images",
            "illustrations",
            "applications",
        ):
            wkey = f"{_OUTLINE_MV_PREFIX}{mid}_{field}"
            if force or wkey not in st.session_state:
                val = mv.get(field)
                if isinstance(val, list):
                    st.session_state[wkey] = "\n".join(
                        str(x).strip() for x in val if str(x).strip()
                    )
                else:
                    st.session_state[wkey] = str(val or "")


def _request_adopt_sermon_sentence(sentence: str) -> None:
    st.session_state[_ADOPT_SERMON_PENDING] = str(sentence or "").strip()
    st.rerun()


def _request_adopt_hc_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_HC_PENDING] = dict(block or {})
    st.rerun()


def _request_adopt_lt_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_LT_PENDING] = dict(block or {})
    st.rerun()


def _request_adopt_ga_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_GA_PENDING] = dict(block or {})
    st.rerun()


def _request_adopt_path_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_PATH_PENDING] = dict(block or {})
    st.rerun()


def _request_adopt_movements(movements: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_MOVEMENTS_PENDING] = list(movements or [])
    st.rerun()


def _request_adopt_path_plan(
    *,
    path_block: dict[str, str] | None = None,
    movements: list[dict[str, str]] | None = None,
) -> None:
    if path_block:
        st.session_state[_ADOPT_PATH_PENDING] = dict(path_block)
    if movements is not None:
        st.session_state[_ADOPT_MOVEMENTS_PENDING] = list(movements)
    st.rerun()


def _user_facing_error(result_ok: bool, error_message: str, *, fallback: str) -> str:
    if result_ok:
        return ""
    msg = (error_message or "").strip()
    if not msg:
        return fallback
    if len(msg) > 280:
        return fallback
    lower = msg.casefold()
    if "api key" in lower or "apikey" in lower or "x-goog-api-key" in lower:
        return fallback
    if (
        "unexpected keyword argument" in lower
        or "got an unexpected keyword" in lower
        or "system_instruction" in lower
    ):
        return fallback
    return msg


def _log_lection_developer_error(exact: str, *, tab: str = "Lekciójavaslat") -> None:
    """Pontos kivétel a fejlesztői debug logba; a UI-n ne jelenjen meg."""
    entry = {
        "ts": __import__("datetime").datetime.now().strftime("%H:%M:%S"),
        "tab": tab,
        "attempt": 0,
        "status": "LECTION_UI_ERROR",
        "error": (exact or "")[:2000],
    }
    try:
        log = st.session_state.setdefault("_debug_log", [])
        if isinstance(log, list):
            log.append(entry)
            if len(log) > 200:
                del log[:-200]
    except Exception:
        pass
    try:
        print(f"[lection] {tab}: {exact}", flush=True)
    except Exception:
        pass


def _collect_m4_kwargs(*, sermon_main_idea: str = "") -> dict[str, Any]:
    """Sessionből M4 MI-bemenet; illusztráció / aktualizálás / ének / vázlat nélkül."""
    tw = ensure_text_workshop_state(st.session_state)
    sw = ensure_sermon_workshop_state(st.session_state)
    idea = (sermon_main_idea or "").strip()
    if not idea:
        idea = (sw.get("sermon_main_idea") or "").strip()
    return {
        "passage": _session_str("last_igehely", "igehely_input"),
        "passage_text": _session_passage_text(),
        "occasion": _session_str("last_alkalom", "alkalom_input"),
        "user_focus": _session_str("last_sajat", "sajat_input"),
        "text_main_idea": (tw.get("text_main_idea") or "").strip(),
        "text_main_idea_status": (tw.get("text_main_idea_status") or "").strip(),
        "approved_insights": tw.get("approved_insights") or [],
        "exegesis": _session_str("exegesis"),
        "theology": _session_str("theology"),
        "sermon_main_idea": idea,
    }


def _collect_m5_kwargs() -> dict[str, Any]:
    """Sessionből M5 MI-bemenet (hallgatói kérdés és feszültség)."""
    tw = ensure_text_workshop_state(st.session_state)
    sw = ensure_sermon_workshop_state(st.session_state)
    text_sugs = tw.get("main_idea_suggestions")
    text_expanded = ""
    if isinstance(text_sugs, dict):
        text_expanded = str(text_sugs.get("expanded_summary") or "").strip()
    sermon_sugs = sw.get("sermon_main_idea_suggestions")
    sermon_expanded = ""
    if isinstance(sermon_sugs, dict):
        sermon_expanded = str(sermon_sugs.get("expanded_summary") or "").strip()
    hc = sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    return {
        "passage": _session_str("last_igehely", "igehely_input"),
        "passage_text": _session_passage_text(),
        "occasion": _session_str("last_alkalom", "alkalom_input"),
        "user_focus": _session_str("last_sajat", "sajat_input"),
        "text_main_idea": (tw.get("text_main_idea") or "").strip(),
        "text_main_idea_status": (tw.get("text_main_idea_status") or "").strip(),
        "text_expanded_summary": text_expanded,
        "approved_insights": tw.get("approved_insights") or [],
        "sermon_main_idea": (sw.get("sermon_main_idea") or "").strip(),
        "sermon_main_idea_status": (sw.get("sermon_main_idea_status") or "").strip(),
        "sermon_expanded_summary": sermon_expanded,
        "human_condition": dict(hc) if isinstance(hc, dict) else {},
        "exegesis": _session_str("exegesis"),
        "theology": _session_str("theology"),
    }


def _collect_gospel_arc_kwargs() -> dict[str, Any]:
    """Sessionből M5 evangéliumi ív MI-bemenet."""
    base = _collect_m5_kwargs()
    sw = ensure_sermon_workshop_state(st.session_state)
    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    # Élő widgetekkel frissített LT (feszültség + feloldás)
    live_lt = {
        "listener_question": (
            st.session_state.get(_KEY_LT["listener_question"])
            or lt.get("listener_question")
            or ""
        ),
        "listener_resistance": (
            st.session_state.get(_KEY_LT["listener_resistance"])
            or lt.get("listener_resistance")
            or ""
        ),
        "sermon_tension": (
            st.session_state.get(_KEY_LT["sermon_tension"])
            or lt.get("sermon_tension")
            or ""
        ),
        "promised_resolution": (
            st.session_state.get(_KEY_GA["promised_resolution"])
            or lt.get("promised_resolution")
            or ""
        ),
    }
    arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    live_arc = {
        "divine_gracious_action": (
            st.session_state.get(_KEY_GA["divine_gracious_action"])
            or arc.get("divine_gracious_action")
            or ""
        ),
        "christ_connection": (
            st.session_state.get(_KEY_GA["christ_connection"])
            or arc.get("christ_connection")
            or ""
        ),
        "christ_connection_type": normalize_christ_connection_type(
            st.session_state.get(_KEY_GA["christ_connection_type"])
            or arc.get("christ_connection_type")
            or ""
        ),
        "grace_enabled_response": (
            st.session_state.get(_KEY_GA["grace_enabled_response"])
            or arc.get("grace_enabled_response")
            or ""
        ),
    }
    base["listener_tension"] = live_lt
    base["christ_centered_arc"] = live_arc
    base["bible_translation"] = _session_str("bible_translation") or "RÚF 2014"
    return base


def _collect_sermon_path_kwargs() -> dict[str, Any]:
    """Sessionből M6 igehirdetési út MI-bemenet."""
    base = _collect_gospel_arc_kwargs()
    sw = ensure_sermon_workshop_state(st.session_state)
    path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    live_path = {
        "type": normalize_sermon_path_type(
            st.session_state.get(_KEY_PATH["type"]) or path.get("type") or ""
        ),
        "reason": (
            st.session_state.get(_KEY_PATH["reason"]) or path.get("reason") or ""
        ),
        "starting_point": (
            st.session_state.get(_KEY_PATH["starting_point"])
            or path.get("starting_point")
            or ""
        ),
        "destination": (
            st.session_state.get(_KEY_PATH["destination"])
            or path.get("destination")
            or ""
        ),
    }
    # Ígért feloldás a LT-ben (gospel kwargs már beletette)
    lt = base.get("listener_tension") if isinstance(base.get("listener_tension"), dict) else {}
    if not str(lt.get("promised_resolution") or "").strip():
        # promised_resolution lehet a GA widgetben
        live_lt = dict(lt)
        live_lt["promised_resolution"] = (
            st.session_state.get(_KEY_GA["promised_resolution"]) or ""
        )
        base["listener_tension"] = live_lt
    base["sermon_path"] = live_path
    base["sermon_movements"] = _read_movements_from_widgets() or normalize_sermon_movements(
        sw.get("sermon_movements")
    )
    base["literary_genre"] = _session_str("exegesis")
    return base


def _collect_enrichment_kwargs() -> dict[str, Any]:
    """Sessionből M7 kép/illusztráció/alkalmazás MI-bemenet."""
    base = _collect_sermon_path_kwargs()
    base["selected_images"] = _read_textual_images_from_widgets()
    base["illustrations"] = _read_illustrations_from_widgets()
    base["applications"] = _read_applications_from_widgets()
    base["workshop_illustrations"] = _session_str("illustrations")
    base["workshop_actualization"] = _session_str("actualization")
    return base


def _read_closing_from_widgets() -> dict[str, str]:
    return {
        "type": normalize_closing_type(st.session_state.get(_KEY_CL["type"])),
        "final_discovery": (
            st.session_state.get(_KEY_CL["final_discovery"]) or ""
        ).strip(),
        "hope": (st.session_state.get(_KEY_CL["hope"]) or "").strip(),
        "call_or_response": (
            st.session_state.get(_KEY_CL["call_or_response"]) or ""
        ).strip(),
        "image_or_line": (
            st.session_state.get(_KEY_CL["image_or_line"]) or ""
        ).strip(),
        "open_question": (
            st.session_state.get(_KEY_CL["open_question"]) or ""
        ).strip(),
        "tone": normalize_closing_tone(st.session_state.get(_KEY_CL["tone"])),
    }


def _persist_closing_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "closing", _read_closing_from_widgets()
    )


def _read_lection_from_widgets() -> dict[str, str]:
    """Widgetek → lekcióblokk; hiányzó widgetkulcsnál a tartós érték marad.

    Így a kapcsolat / funkció / indoklás akkor sem vész el, ha a
    részletes mezők nincsenek a fő felületen (csak összefoglalóban /
    zárt expanderben).
    """
    sw = ensure_sermon_workshop_state(st.session_state)
    durable = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}

    def _pick_str(field: str) -> str:
        wkey = _KEY_LECTION[field]
        if wkey in st.session_state:
            return (st.session_state.get(wkey) or "").strip()
        return str(durable.get(field) or "").strip()

    conn_raw = (
        st.session_state.get(_KEY_LECTION["connection_type"])
        if _KEY_LECTION["connection_type"] in st.session_state
        else durable.get("connection_type")
    )
    text_raw = (
        st.session_state.get(_KEY_LECTION["text"])
        if _KEY_LECTION["text"] in st.session_state
        else durable.get("text")
    )
    test_raw = (
        st.session_state.get(_KEY_LECTION["testament_preference"])
        if _KEY_LECTION["testament_preference"] in st.session_state
        else durable.get("testament_preference")
    )
    len_raw = (
        st.session_state.get(_KEY_LECTION["length_preference"])
        if _KEY_LECTION["length_preference"] in st.session_state
        else durable.get("length_preference")
    )
    return {
        "reference": _pick_str("reference"),
        "connection_type": (
            normalize_lection_connection_type(conn_raw)
            if str(conn_raw or "").strip()
            else ""
        ),
        "function": _pick_str("function"),
        "rationale": _pick_str("rationale"),
        "text": normalize_passage_text(text_raw),
        "notes": _pick_str("notes"),
        "testament_preference": normalize_lection_testament_preference(test_raw),
        "length_preference": normalize_lection_length_preference(len_raw),
        "user_focus": _pick_str("user_focus"),
    }


def _persist_lection_from_widgets(*, include_text: bool = True) -> None:
    """Lekció mezők mentése; opcionálisan a szövegmező kihagyásával."""
    sw = ensure_sermon_workshop_state(st.session_state)
    current = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    block = _read_lection_from_widgets()
    if not include_text:
        block["text"] = str(current.get("text") or "")
        for meta in (
            "text_source",
            "text_source_url",
            "text_fetched_at",
            "text_fetched_reference",
        ):
            block[meta] = str(current.get(meta) or "")
    else:
        for meta in (
            "text_source",
            "text_source_url",
            "text_fetched_at",
            "text_fetched_reference",
        ):
            block[meta] = str(current.get(meta) or "")
    update_sermon_workshop_section(st.session_state, "lection", block)


def _apply_lection_assessment_to_fields(result: LectionAssessmentResult) -> None:
    """Értékelés → háttér mezők (kapcsolat, funkció, indoklás), ha van javaslat."""
    sw = ensure_sermon_workshop_state(st.session_state)
    current = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    block = dict(current)

    conn = normalize_lection_connection_type(result.suggested_connection_type)
    if conn:
        block["connection_type"] = conn
        st.session_state[_KEY_LECTION["connection_type"]] = conn

    rationale = str(result.revised_rationale or "").strip()
    if rationale:
        block["rationale"] = rationale
        st.session_state[_KEY_LECTION["rationale"]] = rationale

    function = str(result.liturgical_fit_assessment or "").strip()
    if function:
        block["function"] = function
        st.session_state[_KEY_LECTION["function"]] = function

    update_sermon_workshop_section(st.session_state, "lection", block)


def _lines_from_widget(raw: Any) -> list[str]:
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def _read_prayer_side_from_widgets(key_map: dict[str, str]) -> dict[str, Any]:
    return {
        "own_thoughts": (st.session_state.get(key_map["own_thoughts"]) or "").strip(),
        "purpose": (st.session_state.get(key_map["purpose"]) or "").strip(),
        "movement_notes": (
            st.session_state.get(key_map["movement_notes"]) or ""
        ).strip(),
        "selected_opening": (
            st.session_state.get(key_map["selected_opening"]) or ""
        ).strip(),
        "selected_lines": _lines_from_widget(
            st.session_state.get(key_map["selected_lines"])
        ),
        "closing_direction": (
            st.session_state.get(key_map["closing_direction"]) or ""
        ).strip(),
    }


def _read_prayer_from_widgets() -> dict[str, Any]:
    sw = ensure_sermon_workshop_state(st.session_state)
    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    before = _read_prayer_side_from_widgets(_KEY_PRAYER_BEFORE)
    after = _read_prayer_side_from_widgets(_KEY_PRAYER_AFTER)
    before["status"] = str(
        (prep.get("before") or {}).get("status")
        if isinstance(prep.get("before"), dict)
        else "draft"
    ) or "draft"
    after["status"] = str(
        (prep.get("after") or {}).get("status")
        if isinstance(prep.get("after"), dict)
        else "draft"
    ) or "draft"
    return {
        "tone_preference": normalize_prayer_tone_preference(
            st.session_state.get(_KEY_PRAYER_COMMON["tone_preference"])
        ),
        "general_focus": (
            st.session_state.get(_KEY_PRAYER_COMMON["general_focus"]) or ""
        ).strip(),
        "rewrite_mode": normalize_prayer_rewrite_mode(
            st.session_state.get(_KEY_PRAYER_COMMON["rewrite_mode"])
        ),
        "before": before,
        "after": after,
        "before_suggestions": prep.get("before_suggestions"),
        "after_suggestions": prep.get("after_suggestions"),
        "assessment": prep.get("assessment"),
        "status": str(prep.get("status") or "draft"),
        "last_generated_at": str(prep.get("last_generated_at") or ""),
    }


def _persist_prayer_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "prayer_preparation", _read_prayer_from_widgets()
    )


def _collect_closing_kwargs() -> dict[str, Any]:
    """Sessionből M7 lezárás MI-bemenet (M6 + M7 + élő lezárás widgetek)."""
    base = _collect_enrichment_kwargs()
    base["closing"] = _read_closing_from_widgets()
    return base


def _read_self_review_from_widgets() -> dict[str, str]:
    return {
        field: (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_DIAG.items()
    }


def _persist_self_review_from_widgets() -> None:
    block = _read_self_review_from_widgets()
    for field, value in block.items():
        update_sermon_workshop_section(st.session_state, field, value)


def _outline_mv_widget_key(mid: str, field: str) -> str:
    return f"{_OUTLINE_MV_PREFIX}{mid}_{field}"


def _read_outline_from_widgets() -> dict[str, Any]:
    sw = ensure_sermon_workshop_state(st.session_state)
    base = normalize_sermon_outline(sw.get("sermon_outline"))
    out = dict(base)
    for field, wkey in _KEY_OUTLINE.items():
        if wkey in st.session_state:
            out[field] = (st.session_state.get(wkey) or "").strip()
    closing = dict(out.get("closing") or {})
    for field, wkey in _KEY_OUTLINE_CLOSING.items():
        if wkey in st.session_state:
            closing[field] = (st.session_state.get(wkey) or "").strip()
    out["closing"] = closing
    lection = dict(out.get("lection") or {})
    for field, wkey in _KEY_OUTLINE_LECTION.items():
        if wkey in st.session_state:
            lection[field] = (st.session_state.get(wkey) or "").strip()
    out["lection"] = lection
    out["lection_reference"] = str(lection.get("reference") or "")
    for side_key, key_map in (
        ("prayer_before", _KEY_OUTLINE_PRAYER_BEFORE),
        ("prayer_after", _KEY_OUTLINE_PRAYER_AFTER),
    ):
        side = dict(out.get(side_key) or {})
        for field, wkey in key_map.items():
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey) or ""
            if field == "selected_lines":
                side[field] = [
                    line.strip()
                    for line in str(raw).splitlines()
                    if line.strip()
                ]
            else:
                side[field] = str(raw).strip()
        out[side_key] = side
    movements: list[dict[str, Any]] = []
    for mv in out.get("movements") or []:
        if not isinstance(mv, dict):
            continue
        mid = str(mv.get("id") or "")
        item = dict(mv)
        if mid:
            for field in (
                "title",
                "role_label",
                "textual_basis",
                "core_content",
                "listener_discovery",
                "transition",
            ):
                wkey = _outline_mv_widget_key(mid, field)
                if wkey in st.session_state:
                    item[field] = (st.session_state.get(wkey) or "").strip()
            for field in ("images", "illustrations", "applications"):
                wkey = _outline_mv_widget_key(mid, field)
                if wkey in st.session_state:
                    item[field] = [
                        line.strip()
                        for line in str(st.session_state.get(wkey) or "").splitlines()
                        if line.strip()
                    ]
        movements.append(item)
    out["movements"] = movements
    return normalize_sermon_outline(out)


def _persist_outline_from_widgets(*, mark_manual_edit: bool | None = True) -> None:
    """Widget → vázlat. mark_manual_edit=None: csak ha a szerkeszthető tartalom változott."""
    sw = ensure_sermon_workshop_state(st.session_state)
    outline = _read_outline_from_widgets()
    if mark_manual_edit is None:
        before = editable_outline_snapshot(sw.get("sermon_outline"))
        after = editable_outline_snapshot(outline)
        mark_manual_edit = before != after
    save_sermon_outline(
        st.session_state,
        outline,
        stamp_generated_at=False,
        mark_manual_edit=bool(mark_manual_edit),
    )


def _collect_outline_diagnostics_kwargs() -> dict[str, Any]:
    base = _collect_closing_kwargs()
    sw = ensure_sermon_workshop_state(st.session_state)
    base["sermon_outline"] = normalize_sermon_outline(sw.get("sermon_outline"))
    return base


def _outline_diagnostics_payload(result: OutlineDiagnosticsResult) -> dict[str, Any]:
    return result.to_dict()


def _run_outline_homiletical_diagnostics(*, generate_fn: GenerateFn | None) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    if not outline_has_content(outline):
        st.warning("Előbb állítsd össze az igehirdetési vázlatot.")
        return
    with st.spinner("A vázlat homiletikai ellenőrzése…"):
        kwargs = _collect_outline_diagnostics_kwargs()
        # Snapshot before run — diagnosztika nem módosíthatja a vázlatot.
        outline_before = dict(outline)
        main_idea_before = str(sw.get("sermon_main_idea") or "")
        result = run_outline_diagnostics(**kwargs, generate_fn=generate_fn)
        if result.missing_outline:
            st.warning(result.error_message or "Előbb állítsd össze az igehirdetési vázlatot.")
            return
        if result.ok and (result.overview or result.strengths or result.refinements):
            save_sermon_outline_diagnostics(
                st.session_state, _outline_diagnostics_payload(result)
            )
        # Védelem: ne írjunk vissza forrásmezőket / vázlatot
        sw_after = ensure_sermon_workshop_state(st.session_state)
        sw_after["sermon_outline"] = normalize_sermon_outline(outline_before)
        sw_after["sermon_main_idea"] = main_idea_before
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A vázlatdiagnosztika nem sikerült.",
                )
            )
        else:
            st.success("Vázlatellenőrzés elkészült.")


def _run_homiletical_diagnostics(*, generate_fn: GenerateFn | None) -> None:
    """Kompatibilitási alias — a fő folyamat a vázlatdiagnosztika."""
    _run_outline_homiletical_diagnostics(generate_fn=generate_fn)


def _diagnostics_payload(result: HomileticalDiagnosticsResult) -> dict[str, Any]:
    return result.to_dict()


def _collect_diagnostics_kwargs() -> dict[str, Any]:
    """Sessionből M8 diagnosztika MI-bemenet (M4–M7 + lezárás + önellenőrzés)."""
    base = _collect_closing_kwargs()
    review = _read_self_review_from_widgets()
    base.update(review)
    return base


def _assemble_and_save_outline(
    *,
    generate_fn: GenerateFn | None,
    force_overwrite: bool,
) -> None:
    with st.spinner("Igehirdetési vázlat összeállítása…"):
        result = assemble_sermon_outline(
            st.session_state,
            generate_fn=generate_fn,
            force_overwrite=force_overwrite,
            polish=False,
        )
        if not result.ok:
            st.warning(result.error_message or "A vázlat összeállítása nem sikerült.")
            st.session_state[_CONFIRM_OUTLINE_OVERWRITE] = True
            return
        save_sermon_outline(st.session_state, result.outline, mark_manual_edit=False)
        st.session_state[_CONFIRM_OUTLINE_OVERWRITE] = False
        st.session_state[_RESYNC_FLAG] = True
        for w in result.warnings:
            st.caption(w)
        st.success("A vázlat elkészült.")
        st.rerun()


def _diag_view_model_simplified(diag: dict[str, Any]) -> dict[str, Any]:
    """Egyszerűsített diagnosztikai nézet — vázlatdiagnosztika vagy M8 adapter."""
    if not isinstance(diag, dict) or not diag:
        return {
            "overview": "",
            "strengths": [],
            "refinements": [],
            "ready_to_use": False,
            "next_step": "",
            "detailed_notes": [],
            "warnings": [],
        }
    # Új séma
    if "overview" in diag or "refinements" in diag or "strengths" in diag:
        return {
            "overview": str(diag.get("overview") or "").strip(),
            "strengths": [
                str(x).strip() for x in (diag.get("strengths") or []) if str(x).strip()
            ][:MAX_STRENGTHS],
            "refinements": list(diag.get("refinements") or [])[:MAX_REFINEMENTS],
            "ready_to_use": bool(diag.get("ready_to_use")),
            "next_step": str(diag.get("next_step") or "").strip(),
            "detailed_notes": [
                str(x).strip()
                for x in (diag.get("detailed_notes") or [])
                if str(x).strip()
            ],
            "warnings": [
                str(x).strip() for x in (diag.get("warnings") or []) if str(x).strip()
            ],
        }
    # Régi M8 séma a diagnostics.result alatt
    adapted = adapt_m8_to_outline_diagnostics(diag)
    return adapted.to_dict()


_DIAG_STATUS_COLORS: dict[str, str] = {
    "strong": "#4a7c74",
    "stable": "#5a6f8a",
    "needs_attention": "#c4923a",
    "critical_gap": "#a65d48",
    "not_enough_information": "#8a8580",
}

# Pastor-friendly UI labels (schema keys unchanged).
_DIAG_STATUS_SOFT_LABELS: dict[str, str] = {
    "strong": "Erős",
    "stable": "Stabil",
    "needs_attention": "Figyelmet igényel",
    "critical_gap": "Javítandó",
    "not_enough_information": "Nincs elég adat",
}

_DIAG_DETAIL_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "title": "Bibliai és teológiai alap",
        "keys": (
            "text_fidelity",
            "theological_accuracy",
            "christ_centeredness",
        ),
    },
    {
        "title": "Az igehirdetés íve",
        "keys": (
            "unity_and_focus",
            "listener_tension",
            "sermon_path",
            "closing",
        ),
    },
    {
        "title": "Hallhatóság és megvalósítás",
        "keys": (
            "hearability",
            "images_and_illustrations",
            "application",
        ),
    },
    {
        "title": "Pásztori hang és felelősség",
        "keys": (
            "pastoral_responsibility",
            "voice_and_originality",
        ),
    },
)

# Keep alias for older imports/tests.
_DIAG_MAP_GROUPS = _DIAG_DETAIL_GROUPS

_DIAG_SOFT_PHRASES: tuple[tuple[str, str], ...] = (
    ("kritikus hiányosságot mutat", "finomítást igényel"),
    ("kritikus hiányosság", "javítandó pont"),
    ("koherenciája jelenleg alacsony", "összhangja még gyenge"),
    ("koherencia jelenleg alacsony", "összhang még gyenge"),
    ("integritási probléma", "összefüggésbeli hiány"),
    ("lényeges hiányosságot", "javítandó pontot"),
    ("lényeges hiányosság", "javítandó pont"),
    ("lényeges hiány", "javítandó pont"),
)

_DIAG_STYLES_FLAG = "_sw_diag_ui_styles"


def _ensure_diag_styles() -> None:
    if st.session_state.get(_DIAG_STYLES_FLAG):
        return
    st.session_state[_DIAG_STYLES_FLAG] = True
    st.markdown(
        """
<style>
.sw-diag-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.82rem;
  font-weight: 600;
  border: 1px solid transparent;
  line-height: 1.3;
}
.sw-diag-chip .dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex: 0 0 auto;
}
.sw-diag-chip-strong { background: rgba(74,124,116,0.14); color: #2f5a54; border-color: rgba(74,124,116,0.28); }
.sw-diag-chip-stable { background: rgba(90,111,138,0.14); color: #3a4b63; border-color: rgba(90,111,138,0.28); }
.sw-diag-chip-needs_attention { background: rgba(196,146,58,0.16); color: #7a5620; border-color: rgba(196,146,58,0.34); }
.sw-diag-chip-critical_gap { background: rgba(166,93,72,0.14); color: #7a3d2f; border-color: rgba(166,93,72,0.30); }
.sw-diag-chip-not_enough_information { background: rgba(138,133,128,0.16); color: #5a5652; border-color: rgba(138,133,128,0.30); }
.sw-diag-count-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.35rem 0 0.85rem 0;
}
@media (max-width: 900px) {
  .sw-diag-count-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .sw-diag-count-grid { grid-template-columns: 1fr; }
}
.sw-diag-count-card {
  border-radius: 12px;
  padding: 0.6rem 0.65rem;
  background: rgba(248, 245, 238, 0.92);
  border: 1px solid rgba(93, 72, 48, 0.12);
  min-width: 0;
}
.sw-diag-count-card .n {
  font-size: 1.3rem;
  font-weight: 700;
  color: #2b2116;
  line-height: 1.1;
}
.sw-diag-count-card .lbl {
  font-size: 0.78rem;
  color: #6b5a48;
  margin-top: 0.12rem;
  line-height: 1.25;
}
.sw-diag-prio-card {
  border-radius: 12px;
  padding: 0.75rem 0.85rem;
  margin-bottom: 0.5rem;
  background: rgba(255, 248, 238, 0.92);
  border: 1px solid rgba(196,146,58,0.28);
  border-left: 4px solid #c4923a;
}
.sw-diag-prio-card h5 {
  margin: 0 0 0.3rem 0;
  color: #2b2116;
  font-size: 0.96rem;
}
.sw-diag-prio-card p {
  margin: 0 0 0.3rem 0;
  color: #4a3e32;
  font-size: 0.88rem;
  line-height: 1.4;
}
.sw-diag-prio-card .meta {
  font-size: 0.8rem;
  color: #6b5a48;
}
.sw-diag-area-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.3rem 0.5rem;
  padding: 0.22rem 0;
  border-top: 1px solid rgba(93, 72, 48, 0.08);
}
.sw-diag-area-row:first-of-type { border-top: none; }
.sw-diag-area-name {
  color: #3d3228;
  font-size: 0.86rem;
  min-width: 0;
  flex: 1 1 auto;
}
.sw-diag-group-block {
  margin: 0.35rem 0 0.75rem 0;
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  background: rgba(255, 252, 247, 0.75);
  border: 1px solid rgba(93, 72, 48, 0.10);
}
.sw-diag-group-block h5 {
  margin: 0 0 0.25rem 0;
  color: #2b2116;
  font-size: 0.9rem;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _diag_areas_index(areas: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(areas, list):
        return out
    for area in areas:
        if not isinstance(area, dict):
            continue
        key = str(area.get("key") or "").strip()
        if key:
            out[key] = area
    return out


def _diag_shorten(text: str, *, limit: int = 320) -> str:
    raw = " ".join(str(text or "").split())
    if len(raw) <= limit:
        return raw
    cut = raw[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:")
    return (cut or raw[: limit - 1]) + "…"


def _diag_soften_text(text: str) -> str:
    """UI-only wording softener; does not alter stored JSON."""
    out = str(text or "")
    lower = out.casefold()
    for harsh, soft in _DIAG_SOFT_PHRASES:
        idx = lower.find(harsh.casefold())
        if idx < 0:
            continue
        out = out[:idx] + soft + out[idx + len(harsh) :]
        lower = out.casefold()
    return out


def _diag_status_soft_label(status: str) -> str:
    key = normalize_diagnostic_status(status)
    return _DIAG_STATUS_SOFT_LABELS.get(key, diagnostic_status_label(key))


def _diag_status_caption(status: str) -> str:
    return _diag_status_soft_label(status)


def _diag_status_chip_html(status: str, *, label: str | None = None) -> str:
    key = normalize_diagnostic_status(status)
    text = html.escape(label or _diag_status_soft_label(key))
    color = _DIAG_STATUS_COLORS.get(key, _DIAG_STATUS_COLORS["not_enough_information"])
    return (
        f'<span class="sw-diag-chip sw-diag-chip-{html.escape(key)}">'
        f'<span class="dot" style="background:{color};"></span>'
        f"{text}</span>"
    )


def _diag_count_statuses(areas_by_key: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {
        "strong_stable": 0,
        "needs_attention": 0,
        "critical_gap": 0,
        "not_enough_information": 0,
    }
    for key in DIAGNOSTIC_AREA_KEYS:
        area = areas_by_key.get(key) or {}
        status = normalize_diagnostic_status(area.get("status"))
        if key not in areas_by_key:
            status = "not_enough_information"
        if status in ("strong", "stable"):
            counts["strong_stable"] += 1
        elif status in counts:
            counts[status] += 1
        else:
            counts["not_enough_information"] += 1
    return counts


def _diag_collect_priorities(diag: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer durable/UI priorities, else revision_priorities (already max 3)."""
    priorities = diag.get("priorities") if isinstance(diag.get("priorities"), list) else []
    if not priorities:
        rev_raw = result.get("revision_priorities")
        if isinstance(rev_raw, list):
            priorities = [p for p in rev_raw if isinstance(p, dict)]
    out: list[dict[str, Any]] = []
    for item in priorities[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        out.append(item)
    return out


def _diag_view_model(diag: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Shape diagnostics JSON for the simplified pastor-facing UI."""
    areas_by_key = _diag_areas_index(result.get("diagnostic_areas"))
    summary = _diag_soften_text(str(result.get("overall_summary") or "").strip())
    return {
        "summary": _diag_shorten(summary, limit=420) if summary else "",
        "counts": _diag_count_statuses(areas_by_key),
        "priorities": _diag_collect_priorities(diag, result),
        "areas_by_key": areas_by_key,
        "coherence": _diag_soften_text(
            str(result.get("overall_coherence") or "").strip()
        ),
        "ready": result.get("ready_for_next_stage"),
        "readiness_note": _diag_soften_text(
            str(result.get("readiness_note") or "").strip()
        ),
        "strengths": result.get("major_strengths"),
        "consistency_warnings": result.get("consistency_warnings"),
        "pastoral_warnings": result.get("pastoral_warnings"),
        "voice_note": _diag_soften_text(
            str(result.get("voice_and_originality_note") or "").strip()
        ),
        "warnings": result.get("warnings"),
        "missing_information": result.get("missing_information"),
        "areas": result.get("diagnostic_areas"),
    }


def _render_diag_summary(summary: str) -> None:
    st.markdown("**Rövid összkép**")
    if summary:
        st.markdown(summary)
    else:
        st.caption("Még nincs rövid összkép ehhez a diagnosztikához.")


def _render_diag_status_cards(counts: dict[str, int]) -> None:
    st.markdown("**Gyors státusz**")
    cards = [
        (counts.get("strong_stable", 0), "Erősségek", "#4a7c74"),
        (counts.get("needs_attention", 0), "Figyelmet igényel", "#c4923a"),
        (counts.get("critical_gap", 0), "Javítandó pontok", "#a65d48"),
        (counts.get("not_enough_information", 0), "Nincs elég adat", "#8a8580"),
    ]
    cards_html = "".join(
        (
            '<div class="sw-diag-count-card" '
            f'style="border-top: 3px solid {color};">'
            f'<div class="n">{n}</div>'
            f'<div class="lbl">{html.escape(lbl)}</div>'
            "</div>"
        )
        for n, lbl, color in cards
    )
    st.markdown(
        f'<div class="sw-diag-count-grid">{cards_html}</div>',
        unsafe_allow_html=True,
    )


def _render_diag_focus(priorities: list[dict[str, Any]]) -> None:
    st.markdown("**Most erre figyelj**")
    if not priorities:
        st.caption("Most nincs kiemelt javítási javaslat.")
        return
    for item in priorities[:3]:
        title = _diag_soften_text(str(item.get("title") or "").strip())
        why = _diag_soften_text(
            str(item.get("why_it_matters") or item.get("problem") or "").strip()
        )
        action = _diag_soften_text(str(item.get("recommended_action") or "").strip())
        parts = [f"<h5>{html.escape(title)}</h5>"]
        if why:
            parts.append(f"<p>{html.escape(_diag_shorten(why, limit=240))}</p>")
        if action:
            parts.append(
                f'<div class="meta"><strong>Következő lépés:</strong> '
                f"{html.escape(_diag_shorten(action, limit=180))}</div>"
            )
        st.markdown(
            f'<div class="sw-diag-prio-card">{"".join(parts)}</div>',
            unsafe_allow_html=True,
        )


def _render_diag_area_detail(area: dict[str, Any], *, expanded: bool) -> None:
    key = str(area.get("key") or "").strip()
    label = str(area.get("label") or "").strip() or diagnostic_area_label(key)
    # Never show raw internal keys as the visible title.
    if label == key or "_" in label:
        label = diagnostic_area_label(key) or label
    status = str(area.get("status") or "").strip()
    status_label = _diag_status_soft_label(status)
    with st.expander(f"{label} — {status_label}", expanded=expanded):
        st.markdown(
            _diag_status_chip_html(status),
            unsafe_allow_html=True,
        )
        for field_label, field_key in (
            ("Megállapítás", "summary"),
            ("Bizonyíték", "evidence"),
            ("Javasolt irány", "concerns"),
        ):
            text = _diag_soften_text(str(area.get(field_key) or "").strip())
            if text:
                st.markdown(f"**{field_label}:** {_diag_shorten(text, limit=420)}")


def _render_diag_details(view: dict[str, Any]) -> None:
    areas_by_key: dict[str, dict[str, Any]] = view.get("areas_by_key") or {}
    areas = view.get("areas")

    with st.expander("Részletes diagnosztika", expanded=False):
        # Short category list (human labels only).
        if areas_by_key or (
            isinstance(areas, list) and any(isinstance(a, dict) for a in areas)
        ):
            st.markdown("**Területek áttekintése**")
            shown_keys: set[str] = set()
            for group in _DIAG_DETAIL_GROUPS:
                rows: list[str] = []
                for key in group["keys"]:
                    area = areas_by_key.get(key) or {}
                    if key in areas_by_key:
                        status = normalize_diagnostic_status(area.get("status"))
                    else:
                        status = "not_enough_information"
                    shown_keys.add(key)
                    rows.append(
                        '<div class="sw-diag-area-row">'
                        f'<span class="sw-diag-area-name">'
                        f"{html.escape(diagnostic_area_label(key))}</span>"
                        f"{_diag_status_chip_html(status)}"
                        "</div>"
                    )
                st.markdown(
                    '<div class="sw-diag-group-block">'
                    f"<h5>{html.escape(str(group['title']))}</h5>"
                    + "".join(rows)
                    + "</div>",
                    unsafe_allow_html=True,
                )
            # Any unexpected extras: show by human label only.
            if isinstance(areas, list):
                for area in areas:
                    if not isinstance(area, dict):
                        continue
                    key = str(area.get("key") or "").strip()
                    if not key or key in shown_keys:
                        continue
                    label = diagnostic_area_label(key) or str(
                        area.get("label") or "Egyéb terület"
                    ).strip()
                    status = normalize_diagnostic_status(area.get("status"))
                    st.markdown(
                        f"{label} — {_diag_status_soft_label(status)}"
                    )

        strengths = view.get("strengths")
        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Ami jól áll**")
            for item in strengths[:4]:
                line = _diag_soften_text(str(item or "").strip())
                if line:
                    st.markdown(f"- {line}")

        coherence = str(view.get("coherence") or "").strip()
        if coherence:
            st.markdown("**Összhang**")
            st.markdown(_diag_shorten(coherence, limit=280))

        ready = view.get("ready")
        readiness_note = str(view.get("readiness_note") or "").strip()
        if ready is not None or readiness_note:
            st.markdown("**Továbbhaladás**")
            if isinstance(ready, bool):
                st.markdown(
                    "A terv alapján tovább lehet lépni."
                    if ready
                    else "Érdemes még finomítani a fenti pontokon."
                )
            if readiness_note:
                st.markdown(_diag_shorten(readiness_note, limit=240))

        voice_note = str(view.get("voice_note") or "").strip()
        if voice_note:
            st.markdown("**Saját hang**")
            st.markdown(_diag_shorten(voice_note, limit=280))

        for title, key in (
            ("Összefüggésbeli megjegyzések", "consistency_warnings"),
            ("Pásztori megjegyzések", "pastoral_warnings"),
        ):
            items = view.get(key)
            if isinstance(items, list) and any(str(x).strip() for x in items):
                st.markdown(f"**{title}**")
                for item in items:
                    line = _diag_soften_text(str(item or "").strip())
                    if line:
                        st.caption(line)

        if isinstance(areas, list) and areas:
            attention = [
                a
                for a in areas
                if isinstance(a, dict)
                and normalize_diagnostic_status(a.get("status"))
                in ("critical_gap", "needs_attention")
            ]
            if attention:
                st.markdown("**Részletek a finomítandó területekről**")
                for area in attention:
                    _render_diag_area_detail(area, expanded=False)

        warnings = view.get("warnings")
        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            for item in warnings:
                line = _diag_soften_text(str(item or "").strip())
                if line:
                    st.caption(line)

        missing = view.get("missing_information")
        if isinstance(missing, list) and any(str(x).strip() for x in missing):
            st.caption(
                "Hiányzó információ: "
                + "; ".join(
                    _diag_soften_text(str(x).strip())
                    for x in missing
                    if str(x).strip()
                )
            )


def _outline_field_filled(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(x or "").strip() for x in value)
    if isinstance(value, dict):
        return any(_outline_field_filled(v) for v in value.values())
    return bool(str(value or "").strip())


def _render_outline_edit_expander(outline: dict[str, Any]) -> None:
    """Zárt szerkesztő — csak tartalommal bíró szakaszok; nem ír vissza M4–M9-be."""
    has_main = _outline_field_filled(outline.get("main_idea")) or _outline_field_filled(
        outline.get("main_idea_summary")
    )
    has_opening = _outline_field_filled(outline.get("opening_direction"))
    movements = (
        outline.get("movements") if isinstance(outline.get("movements"), list) else []
    )
    has_movements = bool(movements)
    closing = outline.get("closing") if isinstance(outline.get("closing"), dict) else {}
    has_closing = any(
        _outline_field_filled(closing.get(k))
        for k in (
            "final_insight",
            "gospel_assurance",
            "invitation",
            "image_or_line",
            "open_question",
        )
    )

    with st.expander("Vázlat szerkesztése", expanded=False):
        st.caption(
            "A módosítások csak a vázlatot érintik; az eredeti műhelydöntéseket "
            "nem írják felül."
        )
        if has_main:
            st.markdown("**Fő gondolat**")
            st.text_area("Fő gondolat", key=_KEY_OUTLINE["main_idea"], height=90)
            st.text_area(
                "Rövid kifejtés (opcionális)",
                key=_KEY_OUTLINE["main_idea_summary"],
                height=70,
            )
        if has_opening:
            st.markdown("**Bevezetési irány**")
            st.text_area(
                "Bevezetési irány",
                key=_KEY_OUTLINE["opening_direction"],
                height=80,
                label_visibility="collapsed",
            )
        if has_movements:
            st.markdown("**Prédikációs mozgások**")
            for idx, mv in enumerate(movements, start=1):
                if not isinstance(mv, dict):
                    continue
                mid = str(mv.get("id") or f"mv{idx}")
                title = str(mv.get("title") or f"{idx}. mozgás").strip()
                role = str(mv.get("role_label") or "").strip()
                label = f"{idx}. {title}" + (f" — {role}" if role else "")
                with st.expander(label, expanded=False):
                    st.text_input("Cím", key=_outline_mv_widget_key(mid, "title"))
                    st.text_area(
                        "Textusbeli alap",
                        key=_outline_mv_widget_key(mid, "textual_basis"),
                        height=60,
                    )
                    st.text_area(
                        "Központi tartalom",
                        key=_outline_mv_widget_key(mid, "core_content"),
                        height=80,
                    )
                    st.text_area(
                        "Hallgatói felismerés",
                        key=_outline_mv_widget_key(mid, "listener_discovery"),
                        height=60,
                    )
                    st.text_area(
                        "Átmenet",
                        key=_outline_mv_widget_key(mid, "transition"),
                        height=60,
                    )
                    st.text_area(
                        "Képek (soronként)",
                        key=_outline_mv_widget_key(mid, "images"),
                        height=50,
                    )
                    st.text_area(
                        "Illusztrációk (soronként)",
                        key=_outline_mv_widget_key(mid, "illustrations"),
                        height=50,
                    )
                    st.text_area(
                        "Alkalmazások (soronként)",
                        key=_outline_mv_widget_key(mid, "applications"),
                        height=50,
                    )
        if has_closing:
            st.markdown("**Lezárás**")
            if _outline_field_filled(closing.get("final_insight")):
                st.text_area(
                    "Végső felismerés",
                    key=_KEY_OUTLINE_CLOSING["final_insight"],
                    height=70,
                )
            if _outline_field_filled(closing.get("gospel_assurance")):
                st.text_area(
                    "Evangéliumi bizonyosság",
                    key=_KEY_OUTLINE_CLOSING["gospel_assurance"],
                    height=70,
                )
            if _outline_field_filled(closing.get("invitation")):
                st.text_area(
                    "Meghívás",
                    key=_KEY_OUTLINE_CLOSING["invitation"],
                    height=60,
                )
            if _outline_field_filled(closing.get("image_or_line")):
                st.text_area(
                    "Záró kép vagy mondatmag",
                    key=_KEY_OUTLINE_CLOSING["image_or_line"],
                    height=50,
                )
            if _outline_field_filled(closing.get("open_question")):
                st.text_area(
                    "Nyitott kérdés",
                    key=_KEY_OUTLINE_CLOSING["open_question"],
                    height=50,
                )

        st.markdown("**Saját megjegyzéseim**")
        st.text_area(
            "Saját megjegyzéseim",
            key=_KEY_OUTLINE["manual_notes"],
            height=80,
            label_visibility="collapsed",
            placeholder="Szószéki emlékeztetők, hangsúlyok, időzítés…",
        )
        if st.button("Vázlat mentése", key="sw_outline_save_edit"):
            _persist_outline_from_widgets(mark_manual_edit=True)
            st.session_state[_RESYNC_FLAG] = True
            st.success("Vázlat elmentve.")
            st.rerun()


def render_outline_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Igehirdetési vázlat — egységes olvasónézet a rendelkezésre álló anyagból."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Igehirdetési vázlat")
    st.markdown(
        "Nem szükséges minden műhelyszakaszt kitölteni. Az alkalmazás az "
        "aktuálisan rendelkezésre álló anyagból állít össze használható "
        "munkavázlatot."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    has_outline = outline_has_content(outline)
    manually_edited = bool(outline.get("manually_edited"))
    need_confirm = bool(st.session_state.get(_CONFIRM_OUTLINE_OVERWRITE))

    primary_label = (
        "Vázlat frissítése a meglévő anyagból"
        if has_outline
        else "Vázlat összeállítása a meglévő anyagból"
    )
    if st.button(primary_label, type="primary", key="sw_outline_assemble"):
        if has_outline and manually_edited and not need_confirm:
            st.session_state[_CONFIRM_OUTLINE_OVERWRITE] = True
            st.warning(
                "A vázlat kézzel szerkesztve van. "
                "A frissítés felülírja a kézi módosításokat — "
                "kattints újra a megerősítéshez."
            )
        else:
            _assemble_and_save_outline(
                generate_fn=generate_fn,
                force_overwrite=bool(has_outline),
            )

    if has_outline:
        status = str(sw.get("sermon_outline_status") or outline.get("status") or "draft")
        b_ap, b_dr = st.columns(2)
        with b_ap:
            if status != "approved" and st.button(
                "Vázlat jóváhagyása", key="sw_outline_approve"
            ):
                _persist_outline_from_widgets(mark_manual_edit=None)
                update_sermon_workshop_section(
                    st.session_state, "sermon_outline_status", "approved"
                )
                st.success("Vázlat jóváhagyva.")
                st.rerun()
        with b_dr:
            if status == "approved" and st.button(
                "Jóváhagyás visszavonása", key="sw_outline_unapprove"
            ):
                update_sermon_workshop_section(
                    st.session_state, "sermon_outline_status", "draft"
                )
                st.rerun()
        generated = str(
            sw.get("sermon_outline_updated_at") or outline.get("updated_at") or ""
        )
        if generated:
            st.caption(f"Utolsó frissítés: {generated}")

        st.markdown("---")
        render_compact_sermon_outline(outline)
        _render_outline_edit_expander(outline)


def _render_diagnostics_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    outline_diag = sw.get("sermon_outline_diagnostics")
    legacy = sw.get("diagnostics") if isinstance(sw.get("diagnostics"), dict) else {}
    legacy_result = legacy.get("result") if isinstance(legacy.get("result"), dict) else {}

    source: dict[str, Any] = {}
    generated = ""
    if isinstance(outline_diag, dict) and (
        outline_diag.get("overview")
        or outline_diag.get("strengths")
        or outline_diag.get("refinements")
    ):
        source = outline_diag
        generated = str(sw.get("sermon_outline_diagnostics_generated_at") or "").strip()
    elif legacy_result:
        source = legacy_result
        generated = str(sw.get("m8_last_generated_at") or "").strip()
    else:
        return

    _ensure_diag_styles()
    view = _diag_view_model_simplified(source)

    st.markdown("**Rövid összkép**")
    overview = str(view.get("overview") or "").strip()
    if overview:
        st.markdown(_diag_soften_text(overview))
    else:
        st.caption("Még nincs rövid összkép.")

    st.markdown("**Ami már jól működik**")
    strengths = view.get("strengths") or []
    if strengths:
        for item in strengths[:MAX_STRENGTHS]:
            line = _diag_soften_text(str(item or "").strip())
            if line:
                st.markdown(f"- {line}")
    else:
        st.caption("Még nincs kiemelt erősség.")

    st.markdown("**Ezen érdemes még finomítani**")
    refinements = view.get("refinements") or []
    if not refinements:
        st.caption("Most nincs kiemelt finomítási javaslat.")
    else:
        for item in refinements[:MAX_REFINEMENTS]:
            if not isinstance(item, dict):
                continue
            title = _diag_soften_text(str(item.get("title") or "").strip())
            explanation = _diag_soften_text(
                str(item.get("explanation") or "").strip()
            )
            action = _diag_soften_text(
                str(item.get("suggested_action") or "").strip()
            )
            parts = [f"<h5>{html.escape(title)}</h5>"]
            if explanation:
                parts.append(
                    f"<p>{html.escape(_diag_shorten(explanation, limit=280))}</p>"
                )
            if action:
                parts.append(
                    f'<div class="meta"><strong>Javaslat:</strong> '
                    f"{html.escape(_diag_shorten(action, limit=200))}</div>"
                )
            st.markdown(
                f'<div class="sw-diag-prio-card">{"".join(parts)}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("**Továbbhaladás**")
    ready = view.get("ready_to_use")
    next_step = _diag_soften_text(str(view.get("next_step") or "").strip())
    if isinstance(ready, bool):
        st.markdown(
            "A vázlat alapján tovább lehet lépni a kézi kidolgozásra."
            if ready
            else "Érdemes még finomítani a fenti pontokon."
        )
    if next_step:
        st.markdown(next_step)

    with st.expander("Részletesebb homiletikai megjegyzések", expanded=False):
        notes = view.get("detailed_notes") or []
        warnings = view.get("warnings") or []
        if notes:
            for note in notes:
                line = _diag_soften_text(str(note or "").strip())
                if line:
                    st.markdown(f"- {line}")
        if warnings:
            for warn in warnings:
                line = _diag_soften_text(str(warn or "").strip())
                if line:
                    st.caption(line)
        if not notes and not warnings:
            st.caption("Nincs további részletes megjegyzés.")

    if generated:
        st.caption(f"Utolsó diagnosztika: {generated}")


def render_diagnostics_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Homiletikai diagnosztika — elsősorban a végső vázlat ellenőrzése."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Homiletikai diagnosztika")
    st.markdown(
        "Rövid, szöveges tükrözés az összeállított igehirdetési vázlatról — "
        "pontszám és automatikus átírás nélkül. A diagnosztika a tényleges "
        "vázlatot értékeli, nem a kitöltött műhelymodulok számát."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    has_outline = outline_has_content(outline)
    if not has_outline:
        st.info(
            "Ha van összeállított vázlat, itt ellenőrizheted. "
            "Előbb állítsd össze az igehirdetési vázlatot a rendelkezésre "
            "álló anyagból — nem kell minden műhelyszakaszt kitölteni."
        )
        return

    st.caption("Az ellenőrzés a jelenlegi vázlat alapján készült.")

    if st.button(
        "A vázlat homiletikai ellenőrzése",
        type="primary",
        key="sw_diag_run",
    ):
        _run_outline_homiletical_diagnostics(generate_fn=generate_fn)

    _render_diagnostics_results()


def _request_adopt_lection_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_LECTION_PENDING] = dict(block or {})
    st.rerun()


def _lection_suggestion_payload(result: LectionSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _lection_assessment_payload(result: LectionAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _collect_lection_kwargs() -> dict[str, Any]:
    """Sessionből M9 lekció MI-bemenet."""
    base = _collect_closing_kwargs()
    live = _read_lection_from_widgets()
    sw = ensure_sermon_workshop_state(st.session_state)
    durable = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    # Meta mezők megőrzése a durable blokkból
    for meta in (
        "text_source",
        "text_source_url",
        "text_fetched_at",
        "text_fetched_reference",
    ):
        live[meta] = str(durable.get(meta) or "")
    base["lection"] = live
    base["testament_preference"] = live.get("testament_preference") or "any"
    base["length_preference"] = live.get("length_preference") or "standard"
    base["lection_user_focus"] = live.get("user_focus") or ""
    return base


def _run_lection_suggest(*, generate_fn: GenerateFn | None) -> None:
    _persist_lection_from_widgets()
    with st.spinner("Lekciójavaslat készül…"):
        kwargs = _collect_lection_kwargs()
        result = suggest_lections(**kwargs, generate_fn=generate_fn)
        if not result.ok:
            exact = (result.error_message or "").strip()
            for w in result.warnings or []:
                if "Generálási hiba:" in str(w):
                    exact = str(w)
                    break
            _log_lection_developer_error(exact or "lection suggest failed")
            # Ne töröljük a korábbi javaslatokat / manuális lekcióadatot.
            st.error(
                "A lekciójavaslat most nem készíthető el. "
                "Próbáld újra, vagy ellenőrizd a kapcsolatot."
            )
            return
        save_lection_suggestions(
            st.session_state, _lection_suggestion_payload(result)
        )
        if result.missing_information and not (
            result.recommended_lection.reference
            or result.no_separate_lection_needed
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_lection_assess(*, generate_fn: GenerateFn | None) -> None:
    _persist_lection_from_widgets()
    live = _read_lection_from_widgets()
    if not live.get("reference"):
        st.warning("Add meg a lekció igehelyét az értékeléshez.")
        return
    with st.spinner("Saját lekció értékelése…"):
        kwargs = _collect_lection_kwargs()
        result = assess_lection(**kwargs, generate_fn=generate_fn)
        if not result.ok:
            exact = (result.error_message or "").strip()
            for w in result.warnings or []:
                if "Generálási hiba:" in str(w):
                    exact = str(w)
                    break
            _log_lection_developer_error(
                exact or "lection assess failed", tab="Lekcióértékelés"
            )
            # Korábbi értékelés és manuális lekciómezők megmaradnak.
            st.error(
                _user_facing_error(
                    False,
                    result.error_message,
                    fallback=(
                        "A lekciójavaslat most nem készíthető el. "
                        "Próbáld újra, vagy ellenőrizd a kapcsolatot."
                    ),
                )
            )
            return
        save_lection_assessment(
            st.session_state, _lection_assessment_payload(result)
        )
        _apply_lection_assessment_to_fields(result)
        st.success("Értékelés elkészült.")


def _apply_lection_ruf_result(result: dict[str, Any]) -> None:
    """RÚF eredmény → lection_text + meta; nem érinti a passage_text-et."""
    text = normalize_passage_text(result.get("text"))
    from datetime import datetime, timezone

    sw = ensure_sermon_workshop_state(st.session_state)
    current = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    block = dict(current)
    block["text"] = text
    block["text_source"] = SOURCE_NAME
    block["text_source_url"] = str(result.get("source_url") or "")
    block["text_fetched_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    block["text_fetched_reference"] = str(
        result.get("normalized_reference") or result.get("requested_reference") or ""
    )
    # Widget + tartós
    st.session_state[_KEY_LECTION["text"]] = text
    update_sermon_workshop_section(st.session_state, "lection", block)
    st.session_state[_RESYNC_FLAG] = True


def _lection_text_mismatch_warning() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    fetched = str(lection.get("text_fetched_reference") or "").strip()
    current = str(
        st.session_state.get(_KEY_LECTION["reference"])
        or lection.get("reference")
        or ""
    ).strip()
    text = normalize_passage_text(
        st.session_state.get(_KEY_LECTION["text"]) or lection.get("text")
    )
    if not fetched or not current or not text.strip():
        return
    if references_equivalent(fetched, current):
        return
    st.warning(
        "A betöltött lekciószöveg egy másik igehelyhez tartozik. "
        "Töltsd be az új szakaszt, vagy ellenőrizd a jelenlegi szöveget."
    )


def _request_lection_ruf_load(reference: str) -> None:
    ref = (reference or "").strip()
    validation = validate_lection_reference(ref)
    if not validation.get("ok"):
        st.warning(
            str(validation.get("error") or "Az igehely nem érvényes a RÚF-betöltéshez.")
        )
        return
    with st.spinner("RÚF szöveg betöltése a szentiras.hu-ról…"):
        result = fetch_ruf_passage(ref)
    if not result.get("success"):
        err = str(result.get("error") or "A RÚF-szöveg betöltése nem sikerült.")
        st.error(err)
        st.info("A meglévő lekciószöveg nem törlődött.")
        return

    sw = ensure_sermon_workshop_state(st.session_state)
    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    existing = normalize_passage_text(lection.get("text")).strip()
    fetched_ref = str(lection.get("text_fetched_reference") or "").strip()
    new_ref = str(
        result.get("normalized_reference") or result.get("requested_reference") or ""
    )
    if existing and fetched_ref and not references_equivalent(fetched_ref, new_ref):
        st.session_state[_LECTION_RUF_PENDING] = result
        st.warning(
            "Már van betöltött lekciószöveg egy másik igehelyhez. "
            "Megerősítés nélkül nem írjuk felül."
        )
        return
    _apply_lection_ruf_result(result)
    st.success("A lekció RÚF-szövege betöltődött.")
    st.rerun()


def _render_lection_ruf_confirm() -> None:
    pending = st.session_state.get(_LECTION_RUF_PENDING)
    if not isinstance(pending, dict):
        return
    st.warning(
        "Megerősíted a meglévő lekciószöveg cseréjét az új RÚF-szakaszra?"
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Igen, cserélem", key="sw_lection_ruf_confirm_yes"):
            result = st.session_state.pop(_LECTION_RUF_PENDING, None)
            if isinstance(result, dict):
                _apply_lection_ruf_result(result)
                st.success("A lekció RÚF-szövege frissült.")
            st.rerun()
    with c2:
        if st.button("Mégse", key="sw_lection_ruf_confirm_no"):
            st.session_state.pop(_LECTION_RUF_PENDING, None)
            st.info("A meglévő lekciószöveg megmaradt.")


def _render_lection_candidate(
    candidate: LectionCandidate | dict[str, Any],
    *,
    key_prefix: str,
    heading: str,
) -> None:
    if isinstance(candidate, LectionCandidate):
        data = candidate.to_dict()
    elif isinstance(candidate, dict):
        data = candidate
    else:
        return
    ref = str(data.get("reference") or "").strip()
    if not ref and not str(data.get("rationale") or "").strip():
        return
    valid = bool(data.get("reference_valid"))
    if "reference_valid" not in data and ref:
        validation = validate_lection_reference(ref)
        valid = bool(validation.get("ok"))
        data["reference_error"] = str(validation.get("error") or "")
        data["reference_valid"] = valid

    st.markdown(f"**{heading}**")
    st.markdown(f"**Igehely:** {ref or '—'}")
    conn = normalize_lection_connection_type(data.get("connection_type"))
    if conn:
        st.markdown(
            f"**Kapcsolat típusa:** {lection_connection_type_label(conn)}"
        )
    rationale = str(data.get("rationale") or "").strip()
    if rationale:
        st.markdown("**Miért illik hozzá?**")
        st.write(rationale)
    func = str(
        data.get("liturgical_function") or data.get("function") or ""
    ).strip()
    if func:
        st.markdown(f"**Liturgiai funkció:** {func}")
    length = str(data.get("estimated_length") or "").strip()
    if length:
        st.markdown(f"**Becsült hossz:** {length}")

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if str(w).strip():
            st.caption(f"Figyelem: {w}")
    if ref and not valid:
        err = str(data.get("reference_error") or "").strip()
        st.warning(
            err
            or "Az igehely nem érvényesíthető — RÚF-betöltés nem érhető el."
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Ezt választom lekciónak", key=f"{key_prefix}_adopt"):
            _request_adopt_lection_block(
                {
                    "reference": ref,
                    "connection_type": conn,
                    "function": func,
                    "rationale": rationale,
                }
            )
    with b2:
        if ref and valid:
            if st.button("RÚF-szöveg betöltése", key=f"{key_prefix}_ruf"):
                _request_lection_ruf_load(ref)


def _render_lection_suggestions() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("lection_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        isinstance(data.get("recommended_lection"), dict)
        and data.get("recommended_lection", {}).get("reference")
    ):
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback=(
                "A lekciójavaslat most nem készíthető el. "
                "Próbáld újra, vagy ellenőrizd a kapcsolatot."
            ),
        )
        if err:
            st.error(err)
        return

    if data.get("no_separate_lection_needed"):
        st.info(
            str(data.get("no_lection_reason") or "").strip()
            or "Az MI szerint külön lekció nem feltétlenül szükséges."
        )

    rec = data.get("recommended_lection")
    if isinstance(rec, dict) and (
        rec.get("reference") or rec.get("rationale")
    ):
        st.markdown("**MI-javaslat**")
        _render_lection_candidate(
            rec, key_prefix="sw_mi_lection_rec", heading="Ajánlott lekció"
        )

    alts = (
        data.get("alternative_lections")
        if isinstance(data.get("alternative_lections"), list)
        else []
    )
    visible_alts = [a for a in alts[:3] if isinstance(a, dict)]
    if visible_alts:
        with st.expander(
            f"További javaslatok ({len(visible_alts)})",
            expanded=True,
        ):
            for idx, alt in enumerate(visible_alts, start=1):
                _render_lection_candidate(
                    alt,
                    key_prefix=f"sw_mi_lection_alt_{idx}",
                    heading=f"Alternatíva {idx}",
                )

    reasoning = str(data.get("overall_reasoning") or "").strip()
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for b in basis:
                if str(b).strip():
                    st.caption(f"• {b}")
        if not reasoning and not basis:
            st.caption("Nincs részletes indoklás.")

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    for w in warnings:
        if str(w).strip():
            st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_lection_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("lection_assessment")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not str(data.get("overall_assessment") or "").strip():
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback=(
                "A lekciójavaslat most nem készíthető el. "
                "Próbáld újra, vagy ellenőrizd a kapcsolatot."
            ),
        )
        if err:
            st.error(err)
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and not data.get("strengths") and not data.get("improvements"):
        return
    st.markdown("**Saját lekció értékelése**")
    if overall:
        st.write(overall)
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if str(s).strip():
                st.caption(f"• {s}")
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if improvements:
        st.markdown("**Javítási lehetőségek**")
        for s in improvements:
            if str(s).strip():
                st.caption(f"• {s}")
    for label, key in (
        ("Kapcsolattípus", "connection_type_assessment"),
        ("Hossz", "length_assessment"),
        ("Liturgiai illeszkedés", "liturgical_fit_assessment"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")
    sug_ref = str(data.get("suggested_reference") or "").strip()
    sug_conn = normalize_lection_connection_type(
        data.get("suggested_connection_type")
    )
    revised = str(data.get("revised_rationale") or "").strip()
    if sug_ref or revised:
        st.caption("Javaslatok (nem írják felül automatikusan a választásodat):")
        if sug_ref:
            st.write(f"Javasolt igehely: {sug_ref}")
        if sug_conn:
            st.write(
                f"Javasolt kapcsolattípus: {lection_connection_type_label(sug_conn)}"
            )
        if revised:
            st.write(revised)
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if str(w).strip():
            st.warning(str(w))


def _render_lection_reader() -> None:
    """Betöltött lekció olvasónézete — külön az alaptextustól."""
    text = normalize_passage_text(st.session_state.get(_KEY_LECTION["text"]))
    _ensure_bible_text_styles()
    st.markdown("**Lekció szövege**")
    if text.strip():
        _lection_text_mismatch_warning()
        render_formatted_bible_text(text)
        sw = ensure_sermon_workshop_state(st.session_state)
        lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
        source = str(lection.get("text_source") or "").strip()
        url = str(lection.get("text_source_url") or "").strip()
        fetched_ref = str(lection.get("text_fetched_reference") or "").strip()
        if source or url or fetched_ref:
            caption = f"Forrás: {source or SOURCE_NAME}"
            if fetched_ref:
                caption += f" — {fetched_ref}"
            if url:
                st.markdown(f"{caption}  \n[Megnyitás a forrásoldalon]({url})")
            else:
                st.caption(caption)
    with st.expander(
        "Lekció szövegének szerkesztése",
        expanded=not bool(text.strip()),
    ):
        st.text_area(
            "Lekció szövege",
            key=_KEY_LECTION["text"],
            height=180,
            label_visibility="collapsed",
            placeholder="Töltsd be a RÚF szöveget, vagy illeszd be ide kézzel…",
        )
        if st.button("Lekciószöveg mentése", key="sw_lection_text_save"):
            _persist_lection_from_widgets(include_text=True)
            st.success("Lekciószöveg elmentve.")


def _render_lection_selected_summary() -> None:
    """Kiválasztott / jóváhagyott lekció kompakt összefoglalója."""
    block = _read_lection_from_widgets()
    sw = ensure_sermon_workshop_state(st.session_state)
    durable = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    ref = block.get("reference") or ""
    text = normalize_passage_text(block.get("text") or durable.get("text"))
    conn = normalize_lection_connection_type(block.get("connection_type"))
    function = (block.get("function") or "").strip()
    rationale = (block.get("rationale") or "").strip()
    if not (ref or text.strip() or conn or function or rationale):
        return

    status = (sw.get("lection_status") or "draft").strip()
    st.markdown("**Kiválasztott lekció**")
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")
    if ref:
        st.markdown(f"**Igehely:** {ref}")
    if conn:
        st.markdown(
            f"**Kapcsolat típusa:** {lection_connection_type_label(conn)}"
        )
    if rationale:
        st.markdown("**Rövid indoklás**")
        st.write(rationale)
    if function:
        st.markdown(f"**Liturgiai funkció:** {function}")
    if text.strip():
        st.caption("RÚF-szöveg betöltve — lásd alább.")


def _render_lection_connection_details_editor() -> None:
    """Mentett kapcsolat / funkció / indoklás — zárt, haladó szerkesztő."""
    block = _read_lection_from_widgets()
    has_details = bool(
        normalize_lection_connection_type(block.get("connection_type"))
        or (block.get("function") or "").strip()
        or (block.get("rationale") or "").strip()
    )
    if not has_details:
        return

    with st.expander("A lekció kapcsolódásának részletei", expanded=False):
        conn_options = [""] + list(LECTION_CONNECTION_TYPES)
        st.selectbox(
            "Kapcsolat típusa",
            options=conn_options,
            format_func=lambda v: (
                "—"
                if not v
                else LECTION_CONNECTION_TYPE_LABELS_HU.get(v, str(v))
            ),
            key=_KEY_LECTION["connection_type"],
        )
        st.text_area(
            "A lekció funkciója",
            key=_KEY_LECTION["function"],
            height=70,
            placeholder="Mit készít elő vagy mit mélyít el ez a lekció?",
        )
        st.text_area(
            "Rövid indoklás",
            key=_KEY_LECTION["rationale"],
            height=90,
            placeholder="Hogyan kapcsolódik a lekció az alaptextushoz?",
        )


def _render_lection_save_approve() -> None:
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_lection_save_draft"):
            block = _read_lection_from_widgets()
            if not any(
                block.get(k)
                for k in (
                    "reference",
                    "function",
                    "rationale",
                    "notes",
                    "text",
                    "user_focus",
                )
            ):
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                _persist_lection_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "lection_status", "draft"
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_lection_approve",
        ):
            block = _read_lection_from_widgets()
            if not block.get("reference"):
                st.warning("Jóváhagyáshoz add meg a lekció igehelyét.")
            else:
                _persist_lection_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "lection_status", "approved"
                )
                decisions = [
                    ("reference", "Lekció igehelye", block["reference"]),
                    (
                        "connection_type",
                        "Kapcsolat típusa",
                        lection_connection_type_label(block["connection_type"]),
                    ),
                    ("function", "A lekció funkciója", block["function"]),
                    ("rationale", "Rövid indoklás", block["rationale"]),
                ]
                added = 0
                skipped = 0
                for _field, category, content in decisions:
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_LECTION,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_LECTION,
                        category,
                        content,
                    )
                    added += 1
                if added:
                    st.success(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    st.info("Ezek a döntések már szerepelnek.")
                else:
                    st.warning("Nem volt menthető tartalom.")

    _render_decisions_for_section(_SOURCE_LECTION)


def render_lection_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Lekciójavaslat — egyszerűsített lelkipásztori munkafolyamat."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Lekciójavaslat")
    st.markdown(
        "A lekció hosszabb, összefüggő bibliai szakasz, amely előkészíti, "
        "elmélyíti vagy tágabb bibliai összefüggésbe helyezi az igehirdetés "
        "üzenetét. Elég néhány mondatban leírnod, mit keresel — vagy "
        "megadnod egy saját igehelyet."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    status = (sw.get("lection_status") or "draft").strip()
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")

    st.text_area(
        "Milyen lekciót keresel?",
        key=_KEY_LECTION["user_focus"],
        height=100,
        help=(
            "Néhány mondatban megadhatod, milyen bibliai szakaszt szeretnél: "
            "milyen hangsúlyt hordozzon, melyik bibliai részből származzon, "
            "vagy körülbelül milyen hosszú legyen."
        ),
        placeholder=(
            "Evangéliumi szakaszt szeretnék, amely Isten megtartó kegyelmét "
            "és a hitben való megmaradást hangsúlyozza. Ne legyen túl hosszú."
        ),
    )
    st.caption(
        "Opcionális. Ha üresen hagyod, az MI a teljes eddigi munkafolyamat "
        "alapján javasol lekciót."
    )

    with st.expander("További beállítások", expanded=False):
        st.selectbox(
            "Melyik bibliai részből szeretnél lekciót?",
            options=list(LECTION_TESTAMENT_PREFERENCES),
            format_func=lambda v: LECTION_TESTAMENT_PREFERENCE_LABELS_HU.get(
                v, str(v)
            ),
            key=_KEY_LECTION["testament_preference"],
        )
        st.selectbox(
            "Körülbelül milyen hosszú legyen?",
            options=list(LECTION_LENGTH_PREFERENCES),
            format_func=lambda v: LECTION_LENGTH_PREFERENCE_LABELS_HU.get(
                v, str(v)
            ),
            key=_KEY_LECTION["length_preference"],
        )
        st.caption(
            "Irányadó: rövidebb ≈ 5–9 vers; átlagos ≈ 8–18; hosszabb ≈ 15–30. "
            "A szakasz természetes egysége fontosabb, mint a pontos versszám."
        )

    if st.button("Lekciók javaslata", type="primary", key="sw_lection_mi_suggest"):
        _run_lection_suggest(generate_fn=generate_fn)

    _render_lection_suggestions()

    with st.expander("Már van saját lekcióötletem", expanded=False):
        st.text_input(
            "Lekció igehelye",
            key=_KEY_LECTION["reference"],
            placeholder="Pl. Fil 2,1–16",
        )
        st.text_area(
            "Saját megjegyzés",
            key=_KEY_LECTION["notes"],
            height=70,
            help="Röviden leírhatod, mit szeretnél ezzel a szakasszal hangsúlyozni.",
            placeholder="Opcionális — mit szeretnél hangsúlyozni ezzel a szakasszal?",
        )
        manual_ref = (st.session_state.get(_KEY_LECTION["reference"]) or "").strip()
        if manual_ref:
            validation = validate_lection_reference(manual_ref)
            if validation.get("ok"):
                if st.button(
                    "RÚF-szöveg betöltése a megadott igehelyhez",
                    key="sw_lection_manual_ruf",
                ):
                    _request_lection_ruf_load(manual_ref)
            else:
                st.caption(
                    str(validation.get("error") or "Az igehely nem érvényesíthető.")
                )
        if st.button("Saját lekció értékelése", key="sw_lection_mi_assess"):
            _run_lection_assess(generate_fn=generate_fn)
        _render_lection_assessment()

    _render_lection_ruf_confirm()
    _render_lection_selected_summary()
    _render_lection_connection_details_editor()

    st.markdown("---")
    _render_lection_reader()
    _render_lection_save_approve()


def _request_adopt_prayer(payload: dict[str, Any]) -> None:
    st.session_state[_ADOPT_PRAYER_PENDING] = dict(payload or {})
    st.rerun()


def _collect_prayer_kwargs() -> dict[str, Any]:
    base = _collect_closing_kwargs()
    live = _read_prayer_from_widgets()
    base["tone_preference"] = live.get("tone_preference") or "mixed"
    base["general_focus"] = live.get("general_focus") or ""
    base["rewrite_mode"] = live.get("rewrite_mode") or "integrate_into_arc"
    base["prayer_before"] = live.get("before") or {}
    base["prayer_after"] = live.get("after") or {}
    return base


def _run_prayer_before_suggest(*, generate_fn: GenerateFn | None) -> None:
    _persist_prayer_from_widgets()
    with st.spinner("Igehirdetés előtti imaív készül…"):
        kwargs = _collect_prayer_kwargs()
        result = suggest_prayer_before(**kwargs, generate_fn=generate_fn)
        save_prayer_before_suggestions(st.session_state, result.to_dict())
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.recommended_movements or result.suggested_lines
        ):
            st.warning(
                "Nincs elegendő adat. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Előtti imaív javaslat elkészült.")


def _run_prayer_after_suggest(*, generate_fn: GenerateFn | None) -> None:
    _persist_prayer_from_widgets()
    with st.spinner("Igehirdetés utáni imaív készül…"):
        kwargs = _collect_prayer_kwargs()
        result = suggest_prayer_after(**kwargs, generate_fn=generate_fn)
        save_prayer_after_suggestions(st.session_state, result.to_dict())
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.recommended_movements or result.suggested_lines
        ):
            st.warning(
                "Nincs elegendő adat. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Utáni imaív javaslat elkészült.")


def _run_prayer_assess(*, generate_fn: GenerateFn | None) -> None:
    _persist_prayer_from_widgets()
    with st.spinner("Imádsági terv értékelése…"):
        kwargs = _collect_prayer_kwargs()
        result = assess_prayer_preparation(**kwargs, generate_fn=generate_fn)
        save_prayer_assessment(st.session_state, result.to_dict())
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


_PRAYER_BEFORE_OWN_HELP = (
    "Röviden leírhatod, mit szeretnél kérni vagy hangsúlyozni. Töredékesen "
    "is írható. Ha üresen hagyod, az MI a textus alapján javasol imaívet."
)
_PRAYER_BEFORE_OWN_PLACEHOLDER = (
    "Csendesedjünk el Isten előtt; kérjük a Szentlélek világosságát; ne "
    "csak másokra gondoljunk az Ige hallgatása közben."
)
_PRAYER_AFTER_OWN_HELP = (
    "Röviden leírhatod, mire szeretnél válaszolni hálaadással, "
    "bűnvallással, kéréssel vagy közbenjárással. Ha üresen hagyod, az MI az "
    "igehirdetési ív alapján javasol."
)
_PRAYER_AFTER_OWN_PLACEHOLDER = (
    "Hála Isten megtartó kegyelméért; imádság a hitükben elfáradtakért; "
    "kérés, hogy a gyülekezet egymást is erősítse."
)


def _prayer_side_has_retained_plan(side: dict[str, Any]) -> bool:
    return bool(
        side.get("selected_opening")
        or side.get("selected_lines")
        or side.get("closing_direction")
        or side.get("purpose")
        or side.get("movement_notes")
    )


def _prayer_side_has_any_content(side: dict[str, Any]) -> bool:
    return _prayer_side_has_retained_plan(side) or bool(side.get("own_thoughts"))


def _build_prayer_adopt_payload(
    data: dict[str, Any],
    *,
    side: str,
) -> dict[str, Any]:
    """Egyetlen átvétel: nyitó + 4–6 ívpont + záró → tartós mezők."""
    simple = adapt_prayer_suggestion_for_ui(data)
    opening = str(simple.get("opening_line") or "").strip()
    closing = str(simple.get("closing_line") or "").strip()
    arc = (
        simple.get("prayer_arc")
        if isinstance(simple.get("prayer_arc"), list)
        else []
    )
    lines: list[str] = []
    notes: list[str] = []
    for item in arc:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        thought = str(item.get("thought") or "").strip()
        if thought:
            lines.append(thought)
        if title and thought:
            notes.append(f"{title}: {thought}")
        elif thought:
            notes.append(thought)
        elif title:
            notes.append(title)
    purpose = str(data.get("purpose") or "").strip()
    payload: dict[str, Any] = {"side": side}
    if opening:
        payload["selected_opening"] = opening
    if lines:
        payload["selected_lines"] = lines
    if closing:
        payload["closing_direction"] = closing
    if notes:
        payload["movement_notes"] = "\n".join(notes)
    if purpose:
        payload["purpose"] = purpose
    return payload


def _render_prayer_own_thoughts_field(
    *,
    title: str,
    key_map: dict[str, str],
    help_text: str,
    placeholder: str,
) -> None:
    st.markdown(f"**{title}**")
    st.caption(help_text)
    st.text_area(
        title,
        key=key_map["own_thoughts"],
        height=110,
        placeholder=placeholder,
        label_visibility="collapsed",
    )


def _render_prayer_plan_details(
    *,
    side: str,
    key_map: dict[str, str],
    side_data: dict[str, Any],
) -> None:
    """Átvétel után szerkeszthető részletek — alapból zárt expander."""
    if not _prayer_side_has_retained_plan(side_data):
        return
    with st.expander("Az imádsági terv részletei", expanded=False):
        st.text_area(
            "Nyitó mondat",
            key=key_map["selected_opening"],
            height=60,
        )
        st.text_area(
            "Fontos imádsági gondolatok (soronként)",
            key=key_map["selected_lines"],
            height=120,
        )
        st.text_area(
            "Záró mondat",
            key=key_map["closing_direction"],
            height=60,
        )
        st.caption(
            "A cél és az imaív a háttérben megmarad a kompatibilitás miatt."
        )
        st.text_area(
            "Imaív (rövid)",
            key=key_map["movement_notes"],
            height=80,
        )
        st.text_area(
            "Cél (opcionális)",
            key=key_map["purpose"],
            height=60,
        )


def _render_prayer_simple_result(
    data: dict[str, Any] | None,
    *,
    side: str,
    heading: str,
) -> None:
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        data.get("recommended_movements") or data.get("suggested_lines")
    ):
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return

    simple = adapt_prayer_suggestion_for_ui(data)
    opening = str(simple.get("opening_line") or "").strip()
    closing = str(simple.get("closing_line") or "").strip()
    arc = (
        simple.get("prayer_arc")
        if isinstance(simple.get("prayer_arc"), list)
        else []
    )
    brief_warning = str(simple.get("brief_warning") or "").strip()
    if not (opening or arc or closing):
        missing = (
            data.get("missing_information")
            if isinstance(data.get("missing_information"), list)
            else []
        )
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    st.markdown(f"**{heading}**")
    # Egy tompított kártya — nyitó / ív / záró
    card_parts: list[str] = []
    if opening:
        card_parts.append(f"**Nyitó mondat**\n\n{opening}")
    if arc:
        arc_lines = ["**Javasolt imaív**"]
        for item in arc:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            thought = str(item.get("thought") or "").strip()
            if not (title or thought):
                continue
            if title:
                arc_lines.append(f"**{title}**")
            if thought:
                arc_lines.append(thought)
            arc_lines.append("")
        card_parts.append("\n".join(arc_lines).rstrip())
    if closing:
        card_parts.append(f"**Záró mondat**\n\n{closing}")
    st.markdown("\n\n---\n\n".join(card_parts))

    integrated = (
        data.get("integrated_user_thoughts")
        if isinstance(data.get("integrated_user_thoughts"), list)
        else []
    )
    if integrated:
        st.caption("A javaslat beépíti a saját gondolataidat is.")

    if brief_warning:
        st.warning(brief_warning)

    if opening or arc or closing:
        if st.button(
            "Átveszem az imaívet",
            key=f"sw_prayer_{side}_adopt_arc",
            type="primary",
        ):
            _request_adopt_prayer(_build_prayer_adopt_payload(data, side=side))

    with st.expander("Mi alapján készült?", expanded=False):
        st.caption(
            "Az imaív a textushoz és a műhelyanyaghoz kötődik; "
            "nem teljes imádság. Angol funkciókódok csak a háttérben vannak."
        )
        purpose = str(data.get("purpose") or "").strip()
        if purpose:
            st.caption(f"Irány: {purpose}")
        missing = (
            data.get("missing_information")
            if isinstance(data.get("missing_information"), list)
            else []
        )
        if missing:
            st.caption("Hiányzó: " + "; ".join(str(x) for x in missing if x))

    with st.expander("Részletes megjegyzések", expanded=False):
        notes = (
            data.get("language_notes")
            if isinstance(data.get("language_notes"), list)
            else []
        )
        cliches = (
            data.get("cliche_risks")
            if isinstance(data.get("cliche_risks"), list)
            else []
        )
        if notes:
            st.markdown("**Nyelvi megjegyzések**")
            for n in notes:
                if str(n).strip():
                    st.caption(f"• {n}")
        if cliches:
            st.markdown("**Sablonossági jelzések**")
            for c in cliches:
                if str(c).strip():
                    st.caption(f"• {c}")
        if integrated:
            st.markdown("**Saját gondolatok beépítése**")
            for item in integrated:
                if not isinstance(item, dict):
                    continue
                original = str(item.get("original") or "").strip()
                refined = str(item.get("refined") or "").strip()
                placement = str(item.get("placement") or "").strip()
                if refined:
                    st.caption(f"• {refined}")
                if original and original != refined:
                    st.caption(f"  Eredeti: {original}")
                if placement and placement not in (
                    "address",
                    "silence",
                    "confession",
                    "illumination",
                    "preacher",
                    "hearers",
                    "surrender",
                    "gratitude",
                    "gospel_trust",
                    "request",
                    "intercession",
                    "response",
                    "hope",
                ):
                    st.caption(f"  Hely: {placement}")
        if not (notes or cliches or integrated):
            st.caption("Nincs további részletes megjegyzés.")


def _render_prayer_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    data = prep.get("assessment")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not str(data.get("overall_assessment") or "").strip():
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and not data.get("strengths"):
        return
    with st.expander("Imádsági terv értékelése", expanded=False):
        if overall:
            st.write(overall)
        before_a = str(data.get("before_assessment") or "").strip()
        after_a = str(data.get("after_assessment") or "").strip()
        if before_a:
            st.markdown(f"**Előtti:** {before_a}")
        if after_a:
            st.markdown(f"**Utáni:** {after_a}")
        for label, key in (
            ("Erősségek", "strengths"),
            ("Javítási lehetőségek", "improvements"),
        ):
            items = data.get(key) if isinstance(data.get(key), list) else []
            if items:
                st.markdown(f"**{label}**")
                for item in items:
                    if str(item).strip():
                        st.caption(f"• {item}")
        cliches = (
            data.get("cliche_findings")
            if isinstance(data.get("cliche_findings"), list)
            else []
        )
        if cliches:
            with st.expander("Sablonossági részletek", expanded=False):
                for item in cliches:
                    if str(item).strip():
                        st.caption(f"• {item}")


def _render_prayer_side_block(
    *,
    side: str,
    key_map: dict[str, str],
    own_title: str,
    help_text: str,
    placeholder: str,
    suggest_label: str,
    result_heading: str,
    generate_fn: GenerateFn | None,
) -> None:
    side_key = "before" if side != "after" else "after"
    suggestions_key = (
        "before_suggestions" if side != "after" else "after_suggestions"
    )

    _render_prayer_own_thoughts_field(
        title=own_title,
        key_map=key_map,
        help_text=help_text,
        placeholder=placeholder,
    )
    btn_key = f"sw_prayer_mi_{side}"
    if st.button(suggest_label, key=btn_key):
        if side != "after":
            _run_prayer_before_suggest(generate_fn=generate_fn)
        else:
            _run_prayer_after_suggest(generate_fn=generate_fn)
    # Újraolvasás: a javaslat mentése után ne stale dict-et mutassunk
    prep = ensure_sermon_workshop_state(st.session_state).get("prayer_preparation")
    prep = prep if isinstance(prep, dict) else {}
    sug = prep.get(suggestions_key)
    _render_prayer_simple_result(
        sug if isinstance(sug, dict) else None,
        side=side,
        heading=result_heading,
    )
    # Friss side_data a widgetekből az átvétel utáni megjelenítéshez
    live = _read_prayer_side_from_widgets(key_map)
    side_data = (
        prep.get(side_key) if isinstance(prep.get(side_key), dict) else {}
    )
    _render_prayer_plan_details(
        side=side,
        key_map=key_map,
        side_data=live if _prayer_side_has_retained_plan(live) else side_data,
    )


def render_prayer_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Imádsági előkészítés — egyszerű saját gondolat + MI imaív."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Imádsági előkészítés")
    st.markdown(
        "Röviden leírhatod saját imádsági gondolataidat. Az MI egy nyitó "
        "mondatot, 4–6 pontból álló imaívet és egy záró mondatot javasol. "
        "Teljes imádság nem készül — az előtti és utáni ima külön marad."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    status = str(prep.get("status") or "draft").strip()
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")

    before_tab, after_tab = st.tabs(
        ["Igehirdetés előtti imádság", "Igehirdetés utáni imádság"]
    )
    with before_tab:
        _render_prayer_side_block(
            side="before",
            key_map=_KEY_PRAYER_BEFORE,
            own_title="Saját gondolataim az igehirdetés előtti imádsághoz",
            help_text=_PRAYER_BEFORE_OWN_HELP,
            placeholder=_PRAYER_BEFORE_OWN_PLACEHOLDER,
            suggest_label="Imaív javaslata",
            result_heading="MI-javaslat — igehirdetés előtti imádság",
            generate_fn=generate_fn,
        )
    with after_tab:
        _render_prayer_side_block(
            side="after",
            key_map=_KEY_PRAYER_AFTER,
            own_title="Saját gondolataim az igehirdetés utáni imádsághoz",
            help_text=_PRAYER_AFTER_OWN_HELP,
            placeholder=_PRAYER_AFTER_OWN_PLACEHOLDER,
            suggest_label="Imaív javaslata",
            result_heading="MI-javaslat — igehirdetés utáni imádság",
            generate_fn=generate_fn,
        )

    with st.expander("További beállítások", expanded=False):
        tone_options = list(PRAYER_TONE_UI_OPTIONS)
        current_tone = normalize_prayer_tone_preference(
            st.session_state.get(_KEY_PRAYER_COMMON["tone_preference"])
        )
        if current_tone not in tone_options and current_tone in PRAYER_TONE_PREFERENCES:
            tone_options = tone_options + [current_tone]
        st.selectbox(
            "Imádsági hangoltság",
            options=tone_options,
            format_func=lambda v: PRAYER_TONE_PREFERENCE_LABELS_HU.get(v, str(v)),
            key=_KEY_PRAYER_COMMON["tone_preference"],
            help="Alapból az MI választ a textushoz illő hangot.",
        )
        st.selectbox(
            "Saját gondolatok átalakítási módja",
            options=list(PRAYER_REWRITE_MODES),
            format_func=lambda v: PRAYER_REWRITE_MODE_LABELS_HU.get(v, str(v)),
            key=_KEY_PRAYER_COMMON["rewrite_mode"],
        )
        st.caption(
            "Az imaív javaslata automatikusan beépíti a saját gondolatokat "
            "a választott mód szerint."
        )
        st.markdown("**Külön hangsúly**")
        st.caption(
            "Van-e külön gyülekezeti, liturgiai vagy lelkipásztori hangsúly?"
        )
        st.text_area(
            "Külön hangsúly",
            key=_KEY_PRAYER_COMMON["general_focus"],
            height=70,
            label_visibility="collapsed",
        )
        if st.button("Imádsági terv értékelése", key="sw_prayer_mi_assess"):
            _run_prayer_assess(generate_fn=generate_fn)

    _render_prayer_assessment()

    st.markdown("---")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_prayer_save_draft"):
            block = _read_prayer_from_widgets()
            before = block.get("before") if isinstance(block.get("before"), dict) else {}
            after = block.get("after") if isinstance(block.get("after"), dict) else {}
            filled = (
                _prayer_side_has_any_content(before)
                or _prayer_side_has_any_content(after)
                or bool(block.get("general_focus"))
            )
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                block["status"] = "draft"
                update_sermon_workshop_section(
                    st.session_state, "prayer_preparation", block
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_prayer_approve",
        ):
            block = _read_prayer_from_widgets()
            before = block.get("before") if isinstance(block.get("before"), dict) else {}
            after = block.get("after") if isinstance(block.get("after"), dict) else {}
            if not (
                _prayer_side_has_retained_plan(before)
                or _prayer_side_has_retained_plan(after)
                or before.get("own_thoughts")
                or after.get("own_thoughts")
            ):
                st.warning(
                    "Jóváhagyáshoz legyen legalább saját gondolat vagy "
                    "átvett imaív (előtti vagy utáni)."
                )
            else:
                before["status"] = "approved"
                after["status"] = "approved"
                block["before"] = before
                block["after"] = after
                block["status"] = "approved"
                update_sermon_workshop_section(
                    st.session_state, "prayer_preparation", block
                )
                decisions = [
                    (
                        "tone",
                        "Imádsági hangoltság",
                        prayer_tone_preference_label(block.get("tone_preference")),
                    ),
                    (
                        "before_opening",
                        "Előtti ima nyitó",
                        str(before.get("selected_opening") or ""),
                    ),
                    (
                        "after_opening",
                        "Utáni ima nyitó",
                        str(after.get("selected_opening") or ""),
                    ),
                    (
                        "before_purpose",
                        "Előtti ima célja",
                        str(before.get("purpose") or ""),
                    ),
                    (
                        "after_purpose",
                        "Utáni ima célja",
                        str(after.get("purpose") or ""),
                    ),
                ]
                added = 0
                skipped = 0
                for _field, category, content in decisions:
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_PRAYER,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_PRAYER,
                        category,
                        content,
                    )
                    added += 1
                if added:
                    st.success(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    st.info("Ezek a döntések már szerepelnek.")
                else:
                    st.warning("Nem volt menthető tartalom.")

    _render_decisions_for_section(_SOURCE_PRAYER)


def _request_adopt_closing_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_CL_PENDING] = dict(block or {})
    st.rerun()


def _closing_suggestion_payload(result: ClosingSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _closing_assessment_payload(result: ClosingAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _run_closing_suggest(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Lezárási irány javaslata készül…"):
        kwargs = _collect_closing_kwargs()
        kwargs.pop("closing", None)
        result = suggest_closing(**kwargs, generate_fn=generate_fn)
        save_closing_suggestions(
            st.session_state, _closing_suggestion_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.recommended_final_insight or result.recommended_gospel_assurance
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_closing_assess(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Saját lezárási terv értékelése…"):
        kwargs = _collect_closing_kwargs()
        result = assess_closing(**kwargs, generate_fn=generate_fn)
        save_closing_assessment(
            st.session_state, _closing_assessment_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


def _enrichment_suggestion_payload(result: EnrichmentSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _enrichment_assessment_payload(result: EnrichmentAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _run_enrichment_suggest(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Képek és alkalmazások javaslata készül…"):
        kwargs = _collect_enrichment_kwargs()
        result = suggest_enrichment(**kwargs, generate_fn=generate_fn)
        save_sermon_enrichment_suggestions(
            st.session_state, _enrichment_suggestion_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.recommended_textual_images
            or result.recommended_illustrations
            or result.recommended_applications
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_enrichment_assess(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Saját terv értékelése…"):
        kwargs = _collect_enrichment_kwargs()
        result = assess_enrichment(**kwargs, generate_fn=generate_fn)
        save_sermon_enrichment_assessment(
            st.session_state, _enrichment_assessment_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


def _render_placement_and_movement(
    *,
    prefix: str,
    item_id: str,
    placement_key: str,
    movement_key: str,
) -> None:
    st.selectbox(
        "Elhelyezés",
        options=list(PLACEMENT_KINDS),
        format_func=lambda v: PLACEMENT_KIND_LABELS_HU.get(v, str(v)),
        key=placement_key,
    )
    placement = normalize_placement_kind(st.session_state.get(placement_key))
    mv_options = _movement_options()
    mv_ids = [mid for mid, _label in mv_options if mid]
    if placement == "movement" and mv_ids:
        current_mid = str(st.session_state.get(movement_key) or "")
        if current_mid not in mv_ids:
            st.session_state[movement_key] = mv_ids[0]
        st.selectbox(
            "Kapcsolódó mozgás",
            options=mv_ids,
            format_func=lambda mid: next(
                (label for oid, label in mv_options if oid == mid), mid
            ),
            key=movement_key,
        )
    elif movement_key in st.session_state:
        st.session_state[movement_key] = ""


def _render_reorder_delete_bar(
    *,
    kind: str,
    item_id: str,
    index: int,
    total: int,
    list_key: str,
    delete_pending_key: str,
    delete_prefix: str,
) -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Feljebb", key=f"{delete_prefix}_up_{item_id}", disabled=index <= 0):
            _persist_enrichment_from_widgets()
            sw = ensure_sermon_workshop_state(st.session_state)
            if kind == "images":
                items = normalize_textual_images(sw.get("selected_images"))
            elif kind == "illustrations":
                items = normalize_illustrations(sw.get("illustrations"))
            else:
                items = normalize_applications(sw.get("applications"))
            if index > 0 and index < len(items):
                items[index - 1], items[index] = items[index], items[index - 1]
                update_sermon_workshop_section(st.session_state, list_key, items)
                st.session_state[_RESYNC_FLAG] = True
                st.rerun()
    with c2:
        if st.button(
            "Lejjebb",
            key=f"{delete_prefix}_down_{item_id}",
            disabled=index >= total - 1,
        ):
            _persist_enrichment_from_widgets()
            sw = ensure_sermon_workshop_state(st.session_state)
            if kind == "images":
                items = normalize_textual_images(sw.get("selected_images"))
            elif kind == "illustrations":
                items = normalize_illustrations(sw.get("illustrations"))
            else:
                items = normalize_applications(sw.get("applications"))
            if index < len(items) - 1:
                items[index + 1], items[index] = items[index], items[index + 1]
                update_sermon_workshop_section(st.session_state, list_key, items)
                st.session_state[_RESYNC_FLAG] = True
                st.rerun()
    with c3:
        pending = st.session_state.get(delete_pending_key)
        if pending == item_id:
            if st.button(
                "Igen, törlés",
                key=f"{delete_prefix}_del_yes_{item_id}",
                type="primary",
            ):
                _persist_enrichment_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                if kind == "images":
                    items = [
                        x
                        for x in normalize_textual_images(sw.get("selected_images"))
                        if str(x.get("id") or "") != item_id
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "selected_images", items
                    )
                    _clear_enrichment_widgets("images")
                elif kind == "illustrations":
                    items = [
                        x
                        for x in normalize_illustrations(sw.get("illustrations"))
                        if str(x.get("id") or "") != item_id
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "illustrations", items
                    )
                    _clear_enrichment_widgets("illustrations")
                else:
                    items = [
                        x
                        for x in normalize_applications(sw.get("applications"))
                        if str(x.get("id") or "") != item_id
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "applications", items
                    )
                    _clear_enrichment_widgets("applications")
                st.session_state.pop(delete_pending_key, None)
                st.session_state[_RESYNC_FLAG] = True
                st.rerun()
            if st.button("Mégse", key=f"{delete_prefix}_del_no_{item_id}"):
                st.session_state.pop(delete_pending_key, None)
                st.rerun()
        elif st.button("Törlés", key=f"{delete_prefix}_del_{item_id}"):
            st.session_state[delete_pending_key] = item_id
            st.rerun()


def _render_textual_image_editor(item: dict[str, str], *, index: int, total: int) -> None:
    iid = str(item.get("id") or "")
    preview = (
        st.session_state.get(_en_widget_key(_IMG_WIDGET_PREFIX, iid, "image"))
        or item.get("image")
        or ""
    ).strip() or f"Kép {index + 1}"
    func = image_function_label(
        st.session_state.get(
            _en_widget_key(_IMG_WIDGET_PREFIX, iid, "homiletical_function")
        )
        or item.get("homiletical_function")
    )
    with st.expander(f"{index + 1}. {preview} — {func}", expanded=False):
        st.text_input(
            "Kép vagy motívum",
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "image"),
            placeholder="Textusbeli kép, jelenet, motívum…",
        )
        st.text_area(
            "Textusbeli alap",
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "textual_basis"),
            height=70,
        )
        st.selectbox(
            "Homiletikai funkció",
            options=list(IMAGE_FUNCTIONS),
            format_func=lambda v: IMAGE_FUNCTION_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "homiletical_function"),
        )
        _render_placement_and_movement(
            prefix=_IMG_WIDGET_PREFIX,
            item_id=iid,
            placement_key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "placement"),
            movement_key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "movement_id"),
        )
        st.text_area(
            "Kibontási jegyzet",
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "development_notes"),
            height=70,
        )
        _render_reorder_delete_bar(
            kind="images",
            item_id=iid,
            index=index,
            total=total,
            list_key="selected_images",
            delete_pending_key=_EN_IMG_DELETE_PENDING,
            delete_prefix="sw_en_img",
        )


def _render_illustration_editor(item: dict[str, str], *, index: int, total: int) -> None:
    iid = str(item.get("id") or "")
    preview = (
        st.session_state.get(_en_widget_key(_ILL_WIDGET_PREFIX, iid, "idea"))
        or item.get("idea")
        or ""
    ).strip() or f"Illusztráció {index + 1}"
    func = illustration_function_label(
        st.session_state.get(_en_widget_key(_ILL_WIDGET_PREFIX, iid, "function"))
        or item.get("function")
    )
    with st.expander(f"{index + 1}. {preview} — {func}", expanded=False):
        st.text_area(
            "Illusztrációs ötlet",
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "idea"),
            height=80,
        )
        st.selectbox(
            "Forrás",
            options=list(ILLUSTRATION_SOURCES),
            format_func=lambda v: ILLUSTRATION_SOURCE_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "source"),
        )
        st.selectbox(
            "Funkció",
            options=list(ILLUSTRATION_FUNCTIONS),
            format_func=lambda v: ILLUSTRATION_FUNCTION_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "function"),
        )
        _render_placement_and_movement(
            prefix=_ILL_WIDGET_PREFIX,
            item_id=iid,
            placement_key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "placement"),
            movement_key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "movement_id"),
        )
        st.text_area(
            "Kapcsolódás a textushoz",
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "connection_to_text"),
            height=70,
        )
        st.text_area(
            "Kockázat vagy korlát",
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "risk_or_limit"),
            height=60,
        )
        _render_reorder_delete_bar(
            kind="illustrations",
            item_id=iid,
            index=index,
            total=total,
            list_key="illustrations",
            delete_pending_key=_EN_ILL_DELETE_PENDING,
            delete_prefix="sw_en_ill",
        )


def _render_application_editor(item: dict[str, str], *, index: int, total: int) -> None:
    iid = str(item.get("id") or "")
    preview = (
        st.session_state.get(_en_widget_key(_APP_WIDGET_PREFIX, iid, "application"))
        or item.get("application")
        or ""
    ).strip() or f"Alkalmazás {index + 1}"
    scope = application_scope_label(
        st.session_state.get(_en_widget_key(_APP_WIDGET_PREFIX, iid, "scope"))
        or item.get("scope")
    )
    with st.expander(f"{index + 1}. {preview} — {scope}", expanded=False):
        st.text_area(
            "Alkalmazás",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "application"),
            height=80,
        )
        st.selectbox(
            "Hatókör",
            options=list(APPLICATION_SCOPES),
            format_func=lambda v: APPLICATION_SCOPE_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "scope"),
        )
        st.text_area(
            "Evangéliumi alap",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "gospel_basis"),
            height=70,
        )
        st.text_area(
            "Konkrétság",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "concreteness"),
            height=70,
        )
        _render_placement_and_movement(
            prefix=_APP_WIDGET_PREFIX,
            item_id=iid,
            placement_key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "placement"),
            movement_key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "movement_id"),
        )
        st.text_area(
            "Pásztori óvatosság",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "pastoral_caution"),
            height=60,
        )
        _render_reorder_delete_bar(
            kind="applications",
            item_id=iid,
            index=index,
            total=total,
            list_key="applications",
            delete_pending_key=_EN_APP_DELETE_PENDING,
            delete_prefix="sw_en_app",
        )


def _render_text_workshop_import_panel() -> None:
    import_items = _collect_text_workshop_import_items()
    existing_refs = _existing_source_refs()
    with st.expander("Elem átvétele a Textusműhely / meglévő anyagból", expanded=False):
        if not import_items:
            st.caption(
                "Nincs átvehető illusztráció, aktualizálás vagy jóváhagyott felismerés."
            )
            return
        for idx, entry in enumerate(import_items):
            ref = entry.get("source_ref") or ""
            if ref in existing_refs:
                st.caption(f"✓ Már átvéve: {entry.get('label')}")
                continue
            st.markdown(f"**{entry.get('label')}**")
            st.write(str(entry.get("content") or "")[:500])
            if st.button("Átveszem", key=f"sw_en_import_{idx}"):
                _persist_enrichment_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                content = str(entry.get("content") or "").strip()
                if entry.get("kind") == "illustration":
                    current = normalize_illustrations(sw.get("illustrations"))
                    if len(current) >= MAX_ILLUSTRATIONS:
                        st.warning(f"Legfeljebb {MAX_ILLUSTRATIONS} illusztráció lehet.")
                    else:
                        item = empty_illustration()
                        item["idea"] = content
                        item["source"] = "text_workshop_import"
                        item["source_ref"] = ref
                        current.append(item)
                        update_sermon_workshop_section(
                            st.session_state, "illustrations", current
                        )
                        st.session_state[_RESYNC_FLAG] = True
                        st.rerun()
                else:
                    current = normalize_applications(sw.get("applications"))
                    if len(current) >= MAX_APPLICATIONS:
                        st.warning(f"Legfeljebb {MAX_APPLICATIONS} alkalmazás lehet.")
                    else:
                        item = empty_application()
                        item["application"] = content
                        item["source_ref"] = ref
                        current.append(item)
                        update_sermon_workshop_section(
                            st.session_state, "applications", current
                        )
                        st.session_state[_RESYNC_FLAG] = True
                        st.rerun()


def _render_enrichment_suggestions() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_enrichment_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        data.get("recommended_textual_images")
        or data.get("recommended_illustrations")
        or data.get("recommended_applications")
    ):
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return

    images = normalize_textual_images(data.get("recommended_textual_images"))
    ills = normalize_illustrations(data.get("recommended_illustrations"))
    apps = normalize_applications(data.get("recommended_applications"))
    expanded = str(data.get("expanded_summary") or "").strip()
    load = str(data.get("load_assessment") or "").strip()
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    reasoning = str(data.get("reasoning_summary") or "").strip()

    if not (images or ills or apps or expanded or load):
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    st.markdown("**MI-javaslat**")
    if images:
        st.markdown("**Textusból fakadó képek**")
        for idx, img in enumerate(images, start=1):
            with st.expander(
                f"{idx}. {img.get('image') or '—'} — "
                f"{image_function_label(img.get('homiletical_function'))}",
                expanded=False,
            ):
                st.write(img.get("textual_basis") or "")
                if st.button(f"Átveszem ezt a képet ({idx})", key=f"sw_mi_en_img_{idx}"):
                    current = _read_textual_images_from_widgets()
                    if len(current) >= MAX_TEXTUAL_IMAGES:
                        st.warning(f"Legfeljebb {MAX_TEXTUAL_IMAGES} kép lehet.")
                    else:
                        new_item = empty_textual_image()
                        for field in _IMG_FIELDS:
                            if field != "id":
                                new_item[field] = str(img.get(field) or "")
                        new_item["homiletical_function"] = normalize_image_function(
                            img.get("homiletical_function")
                        )
                        new_item["placement"] = normalize_placement_kind(
                            img.get("placement")
                        )
                        current.append(new_item)
                        _request_adopt_enrichment_images(current)

    if ills:
        st.markdown("**Illusztrációk**")
        for idx, ill in enumerate(ills, start=1):
            with st.expander(
                f"{idx}. {ill.get('idea') or '—'} — "
                f"{illustration_function_label(ill.get('function'))}",
                expanded=False,
            ):
                st.write(ill.get("connection_to_text") or "")
                if st.button(
                    f"Átveszem ezt az illusztrációt ({idx})",
                    key=f"sw_mi_en_ill_{idx}",
                ):
                    current = _read_illustrations_from_widgets()
                    if len(current) >= MAX_ILLUSTRATIONS:
                        st.warning(f"Legfeljebb {MAX_ILLUSTRATIONS} illusztráció lehet.")
                    else:
                        new_item = empty_illustration()
                        for field in _ILL_FIELDS:
                            if field != "id":
                                new_item[field] = str(ill.get(field) or "")
                        new_item["source"] = normalize_illustration_source(
                            ill.get("source")
                        ) or "needs_verification"
                        new_item["function"] = normalize_illustration_function(
                            ill.get("function")
                        )
                        current.append(new_item)
                        _request_adopt_enrichment_illustrations(current)
    elif load and "nem szükséges" in load.casefold():
        st.info(load)

    if apps:
        st.markdown("**Alkalmazási irányok**")
        for idx, app in enumerate(apps, start=1):
            with st.expander(
                f"{idx}. {app.get('application') or '—'} — "
                f"{application_scope_label(app.get('scope'))}",
                expanded=False,
            ):
                st.write(app.get("gospel_basis") or "")
                if st.button(
                    f"Átveszem ezt az alkalmazást ({idx})",
                    key=f"sw_mi_en_app_{idx}",
                ):
                    current = _read_applications_from_widgets()
                    if len(current) >= MAX_APPLICATIONS:
                        st.warning(f"Legfeljebb {MAX_APPLICATIONS} alkalmazás lehet.")
                    else:
                        new_item = empty_application()
                        for field in _APP_FIELDS:
                            if field != "id":
                                new_item[field] = str(app.get(field) or "")
                        new_item["scope"] = normalize_application_scope(app.get("scope"))
                        current.append(new_item)
                        _request_adopt_enrichment_applications(current)

    if expanded:
        st.markdown("**Az egész ív rövid összefoglalása**")
        st.write(expanded)
    if load:
        st.markdown(f"**Terheltségi értékelés:** {load}")

    if st.button("Átveszem a teljes tervet", key="sw_mi_en_adopt_all"):
        merged_imgs = _read_textual_images_from_widgets()
        merged_ills = _read_illustrations_from_widgets()
        merged_apps = _read_applications_from_widgets()
        for img in images:
            if len(merged_imgs) >= MAX_TEXTUAL_IMAGES:
                break
            new_item = empty_textual_image()
            for field in _IMG_FIELDS:
                if field != "id":
                    new_item[field] = str(img.get(field) or "")
            merged_imgs.append(new_item)
        for ill in ills:
            if len(merged_ills) >= MAX_ILLUSTRATIONS:
                break
            new_item = empty_illustration()
            for field in _ILL_FIELDS:
                if field != "id":
                    new_item[field] = str(ill.get(field) or "")
            new_item["source"] = normalize_illustration_source(ill.get("source"))
            merged_ills.append(new_item)
        for app in apps:
            if len(merged_apps) >= MAX_APPLICATIONS:
                break
            new_item = empty_application()
            for field in _APP_FIELDS:
                if field != "id":
                    new_item[field] = str(app.get(field) or "")
            merged_apps.append(new_item)
        _request_adopt_enrichment_plan(
            images=merged_imgs,
            illustrations=merged_ills,
            applications=merged_apps,
        )

    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for item in basis:
                if item:
                    st.markdown(f"- {item}")

    for w in warnings:
        if w:
            st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_enrichment_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_enrichment_assessment")
    if not isinstance(data, dict):
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and data.get("ok") is False:
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    if not overall and not data.get("revised_textual_images"):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)
    for key, label in (
        ("image_assessment", "Textusbeli képek"),
        ("illustration_assessment", "Illusztrációk"),
        ("application_assessment", "Alkalmazások"),
        ("load_assessment", "Terheltség"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")

    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if s:
                st.markdown(f"- {s}")
    if improvements:
        st.markdown("**Javítási javaslatok**")
        for s in improvements:
            if s:
                st.markdown(f"- {s}")

    rev_imgs = normalize_textual_images(data.get("revised_textual_images"))
    rev_ills = normalize_illustrations(data.get("revised_illustrations"))
    rev_apps = normalize_applications(data.get("revised_applications"))
    if rev_imgs or rev_ills or rev_apps:
        st.markdown("**Javított javaslatok**")
        if st.button("Átveszem a javított teljes tervet", key="sw_mi_en_adopt_rev_all"):
            _request_adopt_enrichment_plan(
                images=rev_imgs or None,
                illustrations=rev_ills or None,
                applications=rev_apps or None,
            )

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if w:
            st.warning(str(w))


def _render_closing_suggestions() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("closing_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        data.get("recommended_final_insight") or data.get("recommended_gospel_assurance")
    ):
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return

    closing_type = normalize_closing_type(data.get("recommended_closing_type"))
    final_insight = str(data.get("recommended_final_insight") or "").strip()
    assurance = str(data.get("recommended_gospel_assurance") or "").strip()
    invitation = str(data.get("recommended_invitation") or "").strip()
    image_line = str(data.get("recommended_closing_image_or_line") or "").strip()
    open_q = str(data.get("recommended_open_question") or "").strip()
    tone = normalize_closing_tone(data.get("recommended_tone"))
    expanded = str(data.get("expanded_summary") or "").strip()
    alternatives = (
        data.get("alternative_closings")
        if isinstance(data.get("alternative_closings"), list)
        else []
    )
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    reasoning = str(data.get("reasoning_summary") or "").strip()

    if not (final_insight or assurance or invitation or image_line or open_q):
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    st.markdown("**MI-javaslat**")
    st.markdown(f"**Ajánlott lezárási irány:** {closing_type_label(closing_type)}")
    if st.button("Átveszem a lezárási irányt", key="sw_mi_cl_adopt_type"):
        _request_adopt_closing_block({"type": closing_type})

    if final_insight:
        st.markdown(f"**Végső felismerés:** {final_insight}")
        if st.button("Átveszem a végső felismerést", key="sw_mi_cl_adopt_insight"):
            _request_adopt_closing_block({"final_discovery": final_insight})

    if assurance:
        st.markdown(f"**Evangéliumi bizonyosság:** {assurance}")
        if st.button("Átveszem az evangéliumi bizonyosságot", key="sw_mi_cl_adopt_hope"):
            _request_adopt_closing_block({"hope": assurance})

    if invitation:
        st.markdown(f"**Kegyelemből fakadó meghívás:** {invitation}")
        if st.button("Átveszem a meghívást", key="sw_mi_cl_adopt_inv"):
            _request_adopt_closing_block({"call_or_response": invitation})

    if image_line:
        st.markdown(f"**Záró kép vagy mondatmag:** {image_line}")
        if st.button("Átveszem a záró képet", key="sw_mi_cl_adopt_img"):
            _request_adopt_closing_block({"image_or_line": image_line})

    if open_q:
        st.markdown(f"**Nyitva maradó kérdés:** {open_q}")
        if st.button("Átveszem a nyitott kérdést", key="sw_mi_cl_adopt_q"):
            _request_adopt_closing_block({"open_question": open_q})

    st.markdown(f"**Hangnem:** {closing_tone_label(tone)}")
    if st.button("Átveszem a hangnemet", key="sw_mi_cl_adopt_tone"):
        _request_adopt_closing_block({"tone": tone})

    if expanded:
        st.markdown("**Rövid kifejtés**")
        st.write(expanded)

    ui_block = {
        "type": closing_type,
        "final_discovery": final_insight,
        "hope": assurance,
        "call_or_response": invitation,
        "image_or_line": image_line,
        "open_question": open_q,
        "tone": tone,
    }
    if st.button("Átveszem a teljes lezárási tervet", key="sw_mi_cl_adopt_all"):
        _request_adopt_closing_block(ui_block)

    if alternatives:
        with st.expander("Alternatív lezárási irányok", expanded=False):
            for idx, alt in enumerate(alternatives, start=1):
                if not isinstance(alt, dict):
                    continue
                st.markdown(
                    f"**{idx}. {closing_type_label(alt.get('closing_type'))}** "
                    f"({closing_tone_label(alt.get('tone'))})"
                )
                if alt.get("emphasis"):
                    st.write(str(alt.get("emphasis")))
                if alt.get("reason_for_use"):
                    st.caption(str(alt.get("reason_for_use")))

    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for item in basis:
                if item:
                    st.markdown(f"- {item}")

    for w in warnings:
        if w:
            st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_closing_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("closing_assessment")
    if not isinstance(data, dict):
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and data.get("ok") is False:
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    if not overall and not data.get("revised_final_insight"):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if s:
                st.markdown(f"- {s}")
    if improvements:
        st.markdown("**Javítási javaslatok**")
        for s in improvements:
            if s:
                st.markdown(f"- {s}")
    for key, label in (
        ("arrival_assessment", "Megérkezés"),
        ("gospel_assurance_assessment", "Evangéliumi bizonyosság"),
        ("invitation_assessment", "Meghívás"),
        ("tone_assessment", "Hangnem"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")

    revised = {
        "type": normalize_closing_type(data.get("revised_closing_type")),
        "final_discovery": str(data.get("revised_final_insight") or "").strip(),
        "hope": str(data.get("revised_gospel_assurance") or "").strip(),
        "call_or_response": str(data.get("revised_invitation") or "").strip(),
        "image_or_line": str(data.get("revised_closing_image_or_line") or "").strip(),
        "open_question": str(data.get("revised_open_question") or "").strip(),
        "tone": normalize_closing_tone(data.get("revised_tone")),
    }
    if any(revised.values()):
        st.markdown("**Javított javaslatok**")
        if st.button("Átveszem a javított teljes tervet", key="sw_mi_cl_adopt_rev_all"):
            _request_adopt_closing_block(
                {k: v for k, v in revised.items() if v}
            )
        for field, label, key in (
            ("type", "lezárási irányt", "sw_mi_cl_adopt_rev_type"),
            ("final_discovery", "végső felismerést", "sw_mi_cl_adopt_rev_insight"),
            ("hope", "evangéliumi bizonyosságot", "sw_mi_cl_adopt_rev_hope"),
            ("call_or_response", "meghívást", "sw_mi_cl_adopt_rev_inv"),
            ("image_or_line", "záró képet", "sw_mi_cl_adopt_rev_img"),
            ("open_question", "nyitott kérdést", "sw_mi_cl_adopt_rev_q"),
            ("tone", "hangnemet", "sw_mi_cl_adopt_rev_tone"),
        ):
            val = revised.get(field) or ""
            if not val:
                continue
            display = (
                closing_type_label(val)
                if field == "type"
                else closing_tone_label(val)
                if field == "tone"
                else val
            )
            st.markdown(f"*{label.capitalize()}:* {display}")
            if st.button(f"Átveszem a {label}", key=key):
                _request_adopt_closing_block({field: val})

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if w:
            st.warning(str(w))


def render_closing_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Lezárás és megérkezés — kézi szerkesztő + MI-segéd."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Lezárás és megérkezés")
    st.markdown(
        "Itt nem a teljes záróbekezdést írjuk meg, hanem megtervezzük, milyen "
        "felismeréshez és milyen kegyelemből fakadó válaszhoz érkezzen meg az "
        "igehirdetés."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    status = (sw.get("closing_status") or "draft").strip()
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")

    if (sw.get("sermon_main_idea_status") or "").strip() != "approved":
        st.info(
            "A szakasz használható, de a javaslatkészítéshez előbb jóvá kell "
            "hagyni az igehirdetés fő gondolatát, szükség van M6-os megérkezési "
            "pontra vagy legalább három mozgásra, valamint evangéliumi feloldásra "
            "vagy Isten kegyelmi cselekvésére."
        )

    for field, title, help_text, optional in _CL_FIELDS:
        st.markdown(f"**{title}**")
        if help_text:
            st.caption(help_text)
        if optional:
            st.caption("Opcionális mező — üresen hagyható.")
        if field == "type":
            st.selectbox(
                title,
                options=list(CLOSING_TYPES),
                format_func=lambda v: CLOSING_TYPE_LABELS_HU.get(v, str(v)),
                key=_KEY_CL["type"],
                label_visibility="collapsed",
            )
        elif field == "tone":
            st.selectbox(
                title,
                options=list(CLOSING_TONES),
                format_func=lambda v: CLOSING_TONE_LABELS_HU.get(v, str(v)),
                key=_KEY_CL["tone"],
                label_visibility="collapsed",
            )
        else:
            st.text_area(
                title,
                key=_KEY_CL[field],
                height=80,
                label_visibility="collapsed",
            )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_cl_save_draft"):
            block = _read_closing_from_widgets()
            filled = any(
                block.get(k)
                for k in (
                    "final_discovery",
                    "hope",
                    "call_or_response",
                    "image_or_line",
                    "open_question",
                )
            )
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                _persist_closing_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "closing_status", "draft"
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_cl_approve",
        ):
            block = _read_closing_from_widgets()
            if not any(
                block.get(k)
                for k in (
                    "final_discovery",
                    "hope",
                    "call_or_response",
                    "image_or_line",
                    "open_question",
                )
            ):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                _persist_closing_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "closing_status", "approved"
                )
                decisions = [
                    ("type", "Lezárás iránya", closing_type_label(block["type"])),
                    ("final_discovery", "Végső felismerés", block["final_discovery"]),
                    ("hope", "Evangéliumi bizonyosság", block["hope"]),
                    (
                        "call_or_response",
                        "Kegyelemből fakadó meghívás",
                        block["call_or_response"],
                    ),
                    (
                        "image_or_line",
                        "Záró kép vagy mondatmag",
                        block["image_or_line"],
                    ),
                    ("open_question", "Nyitva maradó kérdés", block["open_question"]),
                    ("tone", "Hangnem", closing_tone_label(block["tone"])),
                ]
                added = 0
                skipped = 0
                for _field, category, content in decisions:
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_CLOSING,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_CLOSING,
                        category,
                        content,
                    )
                    added += 1
                if added:
                    st.success(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    st.info("Ezek a döntések már szerepelnek.")
                else:
                    st.warning("Nem volt menthető tartalom.")

    _render_decisions_for_section(_SOURCE_CLOSING)

    st.markdown("---")
    st.markdown("**MI-segéd**")
    mi1, mi2 = st.columns(2)
    with mi1:
        if st.button("Lezárási irány javaslata", key="sw_cl_mi_suggest"):
            _run_closing_suggest(generate_fn=generate_fn)
    with mi2:
        if st.button("Saját lezárási terv értékelése", key="sw_cl_mi_assess"):
            _run_closing_assess(generate_fn=generate_fn)

    _render_closing_suggestions()
    _render_closing_assessment()

    st.caption("Következő ajánlott lépés: Lekciójavaslat")


def render_enrichment_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Képek, illusztrációk és alkalmazás — kézi szerkesztő + MI-segéd."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Képek, illusztrációk és alkalmazás")
    st.markdown(
        "Itt azt tervezzük meg, milyen kép segítheti a textus hallását, "
        "milyen illusztráció szolgálhatja a felismerést, és hogyan érkezhet "
        "meg az üzenet a hallgató valós életébe."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    if (sw.get("sermon_main_idea_status") or "").strip() != "approved":
        st.info(
            "A szakasz használható, de a javaslatkészítéshez előbb jóvá kell "
            "hagyni az igehirdetés fő gondolatát, szükség van M6-os útra vagy "
            "legalább három mozgásra, valamint evangéliumi feloldásra vagy "
            "Isten kegyelmi cselekvésére."
        )

    _render_text_workshop_import_panel()

    st.markdown("**Textusból fakadó képek**")
    st.caption(f"0–{MAX_TEXTUAL_IMAGES} kép vagy motívum (MI javaslat: legfeljebb 2).")
    images = normalize_textual_images(sw.get("selected_images"))
    if not images:
        st.info("Még nincs textusbeli kép.")
    for idx, img in enumerate(images):
        _render_textual_image_editor(img, index=idx, total=len(images))
    if st.button(
        "Kép hozzáadása",
        key="sw_en_add_image",
        disabled=len(images) >= MAX_TEXTUAL_IMAGES,
    ):
        _append_enrichment_item("images")
        st.rerun()

    st.markdown("**Illusztrációk**")
    st.caption(
        f"0–{MAX_ILLUSTRATIONS} illusztráció — nem kötelező minden prédikációhoz."
    )
    illustrations = normalize_illustrations(sw.get("illustrations"))
    if not illustrations:
        st.info("Még nincs illusztráció.")
    for idx, ill in enumerate(illustrations):
        _render_illustration_editor(ill, index=idx, total=len(illustrations))
    if st.button(
        "Illusztráció hozzáadása",
        key="sw_en_add_ill",
        disabled=len(illustrations) >= MAX_ILLUSTRATIONS,
    ):
        _append_enrichment_item("illustrations")
        st.rerun()

    st.markdown("**Alkalmazási irányok**")
    st.caption(f"1–{MAX_APPLICATIONS} alkalmazás (ajánlott: 2–4).")
    applications = normalize_applications(sw.get("applications"))
    if not applications:
        st.info("Még nincs alkalmazási irány.")
    for idx, app in enumerate(applications):
        _render_application_editor(app, index=idx, total=len(applications))
    if st.button(
        "Alkalmazás hozzáadása",
        key="sw_en_add_app",
        disabled=len(applications) >= MAX_APPLICATIONS,
    ):
        _append_enrichment_item("applications")
        st.rerun()

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_en_save_draft"):
            _persist_enrichment_from_widgets()
            imgs = _read_textual_images_from_widgets()
            ills = _read_illustrations_from_widgets()
            apps = _read_applications_from_widgets()
            filled = any(
                (x.get("image") or x.get("textual_basis") or "").strip() for x in imgs
            ) or any((x.get("idea") or "").strip() for x in ills) or any(
                (x.get("application") or "").strip() for x in apps
            )
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                update_sermon_workshop_section(st.session_state, "enrichment_status", "draft")
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_en_approve",
        ):
            _persist_enrichment_from_widgets()
            imgs = _read_textual_images_from_widgets()
            ills = _read_illustrations_from_widgets()
            apps = _read_applications_from_widgets()
            filled = any(
                (x.get("image") or x.get("textual_basis") or "").strip() for x in imgs
            ) or any((x.get("idea") or "").strip() for x in ills) or any(
                (x.get("application") or "").strip() for x in apps
            )
            if not filled:
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. "
                    "Tölts ki legalább egy elemet."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "enrichment_status", "approved"
                )
                added = 0
                skipped = 0
                for idx, img in enumerate(imgs, start=1):
                    summary = (
                        f"{idx}. {img.get('image') or 'Kép'} "
                        f"({image_function_label(img.get('homiletical_function'))}): "
                        f"{(img.get('textual_basis') or '')[:120]}"
                    ).strip()
                    if not (img.get("image") or img.get("textual_basis")):
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_ENRICHMENT,
                        category="Textusbeli kép",
                        content=summary,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_ENRICHMENT,
                        "Textusbeli kép",
                        summary,
                    )
                    added += 1
                for idx, ill in enumerate(ills, start=1):
                    summary = (
                        f"{idx}. {ill.get('idea') or 'Illusztráció'} "
                        f"({illustration_function_label(ill.get('function'))})"
                    ).strip()
                    if not ill.get("idea"):
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_ENRICHMENT,
                        category="Illusztráció",
                        content=summary,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_ENRICHMENT,
                        "Illusztráció",
                        summary,
                    )
                    added += 1
                for idx, app in enumerate(apps, start=1):
                    summary = (
                        f"{idx}. {app.get('application') or 'Alkalmazás'} "
                        f"({application_scope_label(app.get('scope'))})"
                    ).strip()
                    if not app.get("application"):
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_ENRICHMENT,
                        category="Alkalmazás",
                        content=summary,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_ENRICHMENT,
                        "Alkalmazás",
                        summary,
                    )
                    added += 1
                if added:
                    st.success(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    st.info("Ezek a döntések már szerepelnek.")
                else:
                    st.warning("Nem volt menthető tartalom.")

    _render_decisions_for_section(_SOURCE_ENRICHMENT)

    st.markdown("---")
    st.markdown("**MI-segéd**")
    mi1, mi2 = st.columns(2)
    with mi1:
        if st.button("Képek és alkalmazások javaslata", key="sw_en_mi_suggest"):
            _run_enrichment_suggest(generate_fn=generate_fn)
    with mi2:
        if st.button("Saját terv értékelése", key="sw_en_mi_assess"):
            _run_enrichment_assess(generate_fn=generate_fn)

    _render_enrichment_suggestions()
    _render_enrichment_assessment()

    st.caption("Következő ajánlott lépés: Lezárás és megérkezés")


def _suggestion_payload_from_result(
    result: SermonMainIdeaSuggestionResult,
) -> dict[str, Any]:
    return {
        "recommended": result.recommended,
        "expanded_summary": result.expanded_summary or "",
        "alternatives": list(result.alternatives),
        "reasoning_summary": result.reasoning_summary,
        "textual_and_homiletical_basis": list(result.textual_and_homiletical_basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _sermon_assessment_payload(
    result: SermonMainIdeaAssessmentResult,
) -> dict[str, Any]:
    return {
        "assessment": result.assessment.to_dict(),
        "strengths": list(result.strengths),
        "revision_priorities": list(result.revision_priorities),
        "revised_version": result.revised_version,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _hc_suggestion_payload(result: HumanConditionSuggestionResult) -> dict[str, Any]:
    return {
        "human_condition": result.human_condition,
        "false_response": result.false_response,
        "human_need": result.human_need,
        "divine_action": result.divine_action,
        "grace_response": result.grace_response,
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _hc_assessment_payload(result: HumanConditionAssessmentResult) -> dict[str, Any]:
    return {
        "assessment": result.assessment.to_dict(),
        "strengths": list(result.strengths),
        "revision_priorities": list(result.revision_priorities),
        "revised_block": result.revised_block.to_dict(),
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _lt_suggestion_payload(result: ListenerTensionSuggestionResult) -> dict[str, Any]:
    return {
        "recommended_listener_question": result.recommended_listener_question,
        "recommended_listener_resistance": result.recommended_listener_resistance,
        "recommended_tension": result.recommended_tension,
        "expanded_summary": result.expanded_summary or "",
        "alternative_sets": [alt.to_dict() for alt in result.alternative_sets],
        "reasoning_summary": result.reasoning_summary,
        "basis": list(result.basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _lt_assessment_payload(result: ListenerTensionAssessmentResult) -> dict[str, Any]:
    return {
        "overall_assessment": result.overall_assessment,
        "strengths": list(result.strengths),
        "improvements": list(result.improvements),
        "revised_listener_question": result.revised_listener_question,
        "revised_listener_resistance": result.revised_listener_resistance,
        "revised_tension": result.revised_tension,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _ga_suggestion_payload(result: GospelArcSuggestionResult) -> dict[str, Any]:
    return {
        "recommended_divine_gracious_action": result.recommended_divine_gracious_action,
        "recommended_christ_connection": result.recommended_christ_connection,
        "recommended_christ_connection_type": result.recommended_christ_connection_type,
        "recommended_promised_resolution": result.recommended_promised_resolution,
        "recommended_grace_enabled_response": result.recommended_grace_enabled_response,
        "expanded_summary": result.expanded_summary or "",
        "confidence": result.confidence or "low",
        "alternative_connections": [
            alt.to_dict() for alt in result.alternative_connections
        ],
        "reasoning_summary": result.reasoning_summary,
        "basis": list(result.basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _ga_assessment_payload(result: GospelArcAssessmentResult) -> dict[str, Any]:
    return {
        "overall_assessment": result.overall_assessment,
        "strengths": list(result.strengths),
        "improvements": list(result.improvements),
        "connection_type_assessment": result.connection_type_assessment,
        "revised_divine_gracious_action": result.revised_divine_gracious_action,
        "revised_christ_connection": result.revised_christ_connection,
        "suggested_christ_connection_type": result.suggested_christ_connection_type,
        "revised_promised_resolution": result.revised_promised_resolution,
        "revised_grace_enabled_response": result.revised_grace_enabled_response,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _prompt_block_to_ui(block: dict[str, Any] | None) -> dict[str, str]:
    out = {k: "" for k in _KEY_HC}
    if not isinstance(block, dict):
        return out
    for prompt_key, ui_key in _HC_PROMPT_TO_UI.items():
        if prompt_key in block:
            out[ui_key] = str(block.get(prompt_key) or "").strip()
        elif ui_key in block:
            out[ui_key] = str(block.get(ui_key) or "").strip()
    return out


def _render_shell_input_summary() -> None:
    """Rövid bemeneti összegzés a shell tetején."""
    tw = ensure_text_workshop_state(st.session_state)
    passage = _session_str("last_igehely", "igehely_input") or "—"
    idea = (tw.get("text_main_idea") or "").strip()
    status = (tw.get("text_main_idea_status") or "").strip()
    insights = tw.get("approved_insights") or []
    insight_count = len(insights) if isinstance(insights, list) else 0
    project_title = (
        _session_str("current_project_title")
        or _session_str("project_title_input")
        or ""
    )

    if status == "approved" and idea:
        idea_line = idea
    elif idea:
        idea_line = f"{idea} *(még nem jóváhagyva)*"
    else:
        idea_line = "—"

    st.markdown(
        f"**Igehely:** {passage}  \n"
        f"**A textus fő gondolata:** {idea_line}  \n"
        f"**Jóváhagyott felismerések:** {insight_count}"
        + (f"  \n**Projekt:** {project_title}" if project_title else "")
    )

    render_bible_text_preview(expanded=False)

    if status != "approved" or not idea:
        st.info(
            "A műhely használható, de a homiletikai munka biztosabb alapokon "
            "áll, ha előbb jóváhagyod a textus fő gondolatát."
        )


def _render_textus_basis_expander() -> None:
    """Csak olvasható Textusműhely-alapok — alapból összecsukva."""
    tw = ensure_text_workshop_state(st.session_state)
    with st.expander("Textusműhelyi alapok", expanded=False):
        idea = (tw.get("text_main_idea") or "").strip()
        status = (tw.get("text_main_idea_status") or "").strip()
        st.markdown("**A textus fő gondolata**")
        if idea:
            label = _STATUS_LABELS.get(status, status or "—")
            st.markdown(idea)
            st.caption(f"Státusz: {label}")
        else:
            st.caption("Még nincs megfogalmazva.")

        insights = tw.get("approved_insights") or []
        st.markdown("**Jóváhagyott felismerések**")
        if isinstance(insights, list) and insights:
            for item in insights:
                if not isinstance(item, dict):
                    continue
                content = (item.get("content") or "").strip()
                if not content:
                    continue
                cat = (item.get("category") or "").strip()
                src = (item.get("source") or "").strip()
                prefix = f"**{cat}** — " if cat else ""
                suffix = f" *(forrás: {src})*" if src else ""
                st.markdown(f"- {prefix}{content}{suffix}")
        else:
            st.caption("Még nincs jóváhagyott felismerés.")

        for key, label in (("exegesis", "Exegézis"), ("theology", "Teológia")):
            text = (st.session_state.get(key) or "").strip()
            if not text:
                continue
            with st.expander(label, expanded=False):
                st.markdown(text)


def _decision_is_duplicate(
    *,
    source_section: str,
    category: str,
    content: str,
) -> bool:
    sw = ensure_sermon_workshop_state(st.session_state)
    needle = (content or "").strip()
    for item in sw.get("approved_sermon_decisions") or []:
        if not isinstance(item, dict):
            continue
        if (
            (item.get("source_section") or "") == source_section
            and (item.get("category") or "") == category
            and (item.get("content") or "").strip() == needle
        ):
            return True
    return False


def _render_decisions_for_section(source_section: str) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    items = [
        item
        for item in (sw.get("approved_sermon_decisions") or [])
        if isinstance(item, dict)
        and (item.get("source_section") or "") == source_section
    ]
    with st.expander("Jóváhagyott homiletikai döntések", expanded=False):
        if not items:
            st.caption("Ebben a szakaszban még nincs jóváhagyott döntés.")
            return
        for item in items:
            did = str(item.get("id") or "")
            if not did:
                continue
            category = item.get("category") or "—"
            content = item.get("content") or ""
            created = item.get("created_at") or ""
            with st.container(border=True):
                st.markdown(f"**{category}**")
                if created:
                    st.caption(f"Létrehozva: {created}")
                st.markdown(content)
                confirm_key = f"sw_decision_del_confirm_{did}"
                if st.session_state.get(confirm_key):
                    st.warning("Biztosan eltávolítod ezt a döntést?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "Igen, törlés",
                            key=f"sw_decision_del_yes_{did}",
                            type="primary",
                        ):
                            remove_approved_sermon_decision(st.session_state, did)
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                    with c2:
                        if st.button("Mégse", key=f"sw_decision_del_no_{did}"):
                            st.session_state[confirm_key] = False
                            st.rerun()
                else:
                    if st.button(
                        "Döntés eltávolítása",
                        key=f"sw_decision_del_{did}",
                    ):
                        st.session_state[confirm_key] = True
                        st.rerun()


def _run_sermon_suggest(generate_fn: GenerateFn) -> None:
    kwargs = _collect_m4_kwargs(
        sermon_main_idea=(st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    )
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return
    with st.spinner(
        "Az igehirdetés fő gondolatának lehetséges megfogalmazásait vizsgálom…"
    ):
        result = suggest_sermon_main_idea(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_sermon_main_idea_suggestions(
        st.session_state,
        _suggestion_payload_from_result(result),
    )
    if not (result.recommended or "").strip():
        st.info(
            "A rendelkezésre álló anyag alapján nem készült felelős ajánlott "
            "fő gondolat. Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslatok elkészültek.")


def _run_sermon_assess(generate_fn: GenerateFn) -> None:
    idea = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    if not idea:
        st.warning("Nincs megfogalmazás az értékeléshez.")
        return
    kwargs = _collect_m4_kwargs(sermon_main_idea=idea)
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return
    with st.spinner(
        "A megfogalmazást textushűségi és hallhatósági szempontból vizsgálom…"
    ):
        result = assess_sermon_main_idea(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_sermon_main_idea_assessment(
        st.session_state,
        _sermon_assessment_payload(result),
    )
    st.success("Az értékelés elkészült.")


def _render_sermon_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("sermon_main_idea_suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (sw.get("m4_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    recommended = (sugs.get("recommended") or "").strip()
    expanded = (sugs.get("expanded_summary") or "").strip()
    alternatives = sugs.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []

    if recommended:
        with st.container(border=True):
            st.markdown("**Ajánlott fő gondolat**")
            st.markdown(recommended)
            if expanded:
                st.caption("Rövid kifejtés")
                st.markdown(expanded)
            if st.button("Átveszem", key="sw_mi_adopt_recommended"):
                _request_adopt_sermon_sentence(recommended)
    else:
        st.info(
            "Nincs ajánlott fő gondolat (elégtelen adat vagy a modell üresen hagyta). "
            "A részletek a „Mi alapján készült?” részben vannak."
        )

    alt_items: list[str] = []
    for alt in alternatives[:2]:
        text = (alt or "").strip() if isinstance(alt, str) else str(alt or "").strip()
        if text:
            alt_items.append(text)
    if alt_items:
        with st.expander("További javaslatok", expanded=False):
            for idx, text in enumerate(alt_items):
                with st.container(border=True):
                    st.markdown(f"**Alternatíva {idx + 1}**")
                    st.markdown(text)
                    if st.button("Átveszem", key=f"sw_mi_adopt_alt_{idx}"):
                        _request_adopt_sermon_sentence(text)

    reasoning = (sugs.get("reasoning_summary") or "").strip()
    basis = sugs.get("textual_and_homiletical_basis") or []
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_basis = isinstance(basis, list) and any(str(x).strip() for x in basis)
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)

    if reasoning or has_basis or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_basis:
                st.markdown("**Szövegbeli és homiletikai alapok**")
                for item in basis:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def _render_sermon_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    assessment_payload = sw.get("sermon_main_idea_assessment")
    if not isinstance(assessment_payload, dict):
        return

    fields = assessment_payload.get("assessment") or {}
    if not isinstance(fields, dict):
        fields = {}
    strengths = assessment_payload.get("strengths") or []
    priorities = assessment_payload.get("revision_priorities") or []
    revised = (assessment_payload.get("revised_version") or "").strip()
    warnings = assessment_payload.get("warnings") or []

    with st.expander("Szakmai értékelés részletei", expanded=False):
        if any(str(fields.get(k) or "").strip() for k, _ in _SERMON_ASSESSMENT_LABELS):
            st.markdown("**Szempontok**")
            for key, label in _SERMON_ASSESSMENT_LABELS:
                text = str(fields.get(key) or "").strip()
                if text:
                    st.markdown(f"**{label}:** {text}")

        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Erősségek**")
            for item in strengths[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if isinstance(priorities, list) and any(str(x).strip() for x in priorities):
            st.markdown("**Javítási szempontok**")
            for item in priorities[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if revised:
            st.markdown("**Átdolgozott javaslat**")
            st.markdown(revised)
            if st.button(
                "Átdolgozott változat átvétele",
                key="sw_mi_adopt_revised_sermon",
            ):
                _request_adopt_sermon_sentence(revised)
        else:
            st.caption(
                "Nincs átdolgozott javaslat (üres mező vagy elégtelen elemzési alap)."
            )

        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            st.markdown("**Figyelmeztetések**")
            for item in warnings:
                line = str(item or "").strip()
                if line:
                    st.warning(line)


def _run_hc_suggest(generate_fn: GenerateFn) -> None:
    kwargs = _collect_m4_kwargs(
        sermon_main_idea=(st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    )
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return
    with st.spinner(
        "A textus által feltárt emberi helyzetet és Isten kegyelmi "
        "cselekvését vizsgálom…"
    ):
        result = suggest_human_condition(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_human_condition_suggestion(
        st.session_state,
        _hc_suggestion_payload(result),
    )
    if not (
        result.human_condition.strip()
        or result.divine_action.strip()
        or result.false_response.strip()
        or result.human_need.strip()
        or result.grace_response.strip()
    ):
        st.info(
            "A rendelkezésre álló anyag alapján nem készült felelős javaslat. "
            "Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslat elkészült.")


def _run_hc_assess(generate_fn: GenerateFn) -> None:
    block = {
        field: (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_HC.items()
    }
    if not any(block.values()):
        st.warning("Nincs kitöltött elemzés az értékeléshez.")
        return
    kwargs = _collect_m4_kwargs(
        sermon_main_idea=(st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    )
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return
    with st.spinner(
        "Az emberihelyzet-elemzést textushűségi és szakmai szempontból vizsgálom…"
    ):
        result = assess_human_condition(
            **kwargs,
            human_condition=block,
            generate_fn=generate_fn,
        )
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_human_condition_assessment(
        st.session_state,
        _hc_assessment_payload(result),
    )
    st.success("Az értékelés elkészült.")


def _render_hc_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("human_condition_suggestion")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslat")
    generated_at = (sw.get("m4_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    any_field = False
    for key, label in _HC_SUGGEST_DISPLAY:
        value = str(sugs.get(key) or "").strip()
        with st.container(border=True):
            st.markdown(f"**{label}**")
            if value:
                any_field = True
                st.markdown(value)
            else:
                st.caption(
                    "Üresen hagyva — a textus alapján nem megalapozható, "
                    "vagy szándékosan nem kötelező mező."
                )

    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
        st.markdown("**Figyelmeztetések**")
        for item in warnings:
            line = str(item or "").strip()
            if line:
                st.warning(line)
    if isinstance(missing, list) and any(str(x).strip() for x in missing):
        st.markdown("**Hiányzó információk**")
        for item in missing:
            line = str(item or "").strip()
            if line:
                st.markdown(f"- {line}")

    ui_block = _prompt_block_to_ui(sugs)
    if any(ui_block.values()):
        if st.button("Javaslat átvétele", key="sw_mi_hc_adopt_suggestion"):
            _request_adopt_hc_block(ui_block)
    elif not any_field:
        st.info("Nincs átvehető javasolt mező.")


def _render_hc_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    assessment_payload = sw.get("human_condition_assessment")
    if not isinstance(assessment_payload, dict):
        return

    fields = assessment_payload.get("assessment") or {}
    if not isinstance(fields, dict):
        fields = {}
    strengths = assessment_payload.get("strengths") or []
    priorities = assessment_payload.get("revision_priorities") or []
    revised_raw = assessment_payload.get("revised_block") or {}
    if not isinstance(revised_raw, dict):
        revised_raw = {}
    warnings = assessment_payload.get("warnings") or []

    with st.expander("Szakmai értékelés részletei", expanded=False):
        if any(str(fields.get(k) or "").strip() for k, _ in _HC_ASSESSMENT_LABELS):
            st.markdown("**Szempontok**")
            for key, label in _HC_ASSESSMENT_LABELS:
                text = str(fields.get(key) or "").strip()
                if text:
                    st.markdown(f"**{label}:** {text}")

        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Erősségek**")
            for item in strengths[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if isinstance(priorities, list) and any(str(x).strip() for x in priorities):
            st.markdown("**Javítási szempontok**")
            for item in priorities[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        st.markdown("**Átdolgozott blokk**")
        revised_ui = _prompt_block_to_ui(revised_raw)
        any_revised = False
        for key, label in _HC_SUGGEST_DISPLAY:
            ui_key = _HC_PROMPT_TO_UI[key]
            value = (revised_ui.get(ui_key) or "").strip()
            st.markdown(f"*{label}*")
            if value:
                any_revised = True
                st.markdown(value)
            else:
                st.caption("Üres")

        if any_revised:
            if st.button(
                "Átdolgozott blokk átvétele",
                key="sw_mi_hc_adopt_revised",
            ):
                _request_adopt_hc_block(revised_ui)
        else:
            st.caption(
                "Nincs átdolgozott javaslat (üres mezők vagy elégtelen elemzési alap)."
            )

        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            st.markdown("**Figyelmeztetések**")
            for item in warnings:
                line = str(item or "").strip()
                if line:
                    st.warning(line)


def render_sermon_main_idea_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Az igehirdetés fő gondolata — kézi szerkesztő + opcionális MI-segéd."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    tw = ensure_text_workshop_state(st.session_state)

    st.subheader("Az igehirdetés fő gondolata")
    st.markdown(
        "Fogalmazd meg egyetlen világos mondatban, mit szeretnél, hogy a "
        "hallgató a textus alapján felismerjen. Ez még nem cím és nem "
        "vázlat, hanem az egész igehirdetést összetartó állítás."
    )

    passage = _session_str("last_igehely", "igehely_input") or "—"
    text_idea = (tw.get("text_main_idea") or "").strip()
    text_status = (tw.get("text_main_idea_status") or "").strip()
    insights = tw.get("approved_insights") or []
    insight_count = len(insights) if isinstance(insights, list) else 0

    st.markdown(
        f"**Igehely:** {passage}  \n"
        f"**A textus fő gondolata:** {text_idea or '—'}  \n"
        f"**Jóváhagyott felismerések:** {insight_count}"
    )
    if text_status != "approved" or not text_idea:
        st.info(
            "A textus fő gondolata még nincs jóváhagyva. A szakasz használható, "
            "de a homiletikai munka biztosabb alapokon áll, ha előbb a "
            "Textusműhelyben jóváhagyod."
        )

    st.text_area(
        "Az igehirdetés fő gondolata",
        key=_KEY_SERMON_IDEA,
        height=120,
        label_visibility="collapsed",
        placeholder="Egyetlen, hallható állítás…",
    )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_sermon_idea_save_draft"):
            content = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
            if not content:
                st.warning("Üres fő gondolatot nem lehet menteni. Írj egy mondatot.")
            else:
                update_sermon_workshop_section(
                    st.session_state,
                    "sermon_main_idea",
                    {
                        "sermon_main_idea": content,
                        "sermon_main_idea_status": "draft",
                    },
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_sermon_idea_approve",
        ):
            content = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
            if not content:
                st.warning(
                    "Üres fő gondolatot nem lehet jóváhagyni. Írj egy mondatot."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state,
                    "sermon_main_idea",
                    {
                        "sermon_main_idea": content,
                        "sermon_main_idea_status": "approved",
                    },
                )
                if _decision_is_duplicate(
                    source_section=_SOURCE_SERMON_MAIN,
                    category=_CAT_MAIN_IDEA,
                    content=content,
                ):
                    st.success(
                        "Jóváhagyva. Ez a fő gondolat már szerepel a "
                        "homiletikai döntések között."
                    )
                else:
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_SERMON_MAIN,
                        _CAT_MAIN_IDEA,
                        content,
                    )
                    st.success("Jóváhagyva és továbbvíve a homiletikai döntésekhez.")

    sw = ensure_sermon_workshop_state(st.session_state)
    saved = (sw.get("sermon_main_idea") or "").strip()
    saved_status = sw.get("sermon_main_idea_status") or ""
    if saved or saved_status:
        label = _STATUS_LABELS.get(saved_status, saved_status or "—")
        st.caption(f"Elmentett állapot: **{label}**")

    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Az MI a jóváhagyott textusműhelyi eredményekből segít "
        "megfogalmazni és megvizsgálni az igehirdetés fő gondolatát. "
        "A végső döntés továbbra is a prédikátoré."
    )
    ai_ready = generate_fn is not None
    idea_draft = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Javaslatok készítése",
            key="sw_mi_sermon_suggest",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_sermon_suggest(generate_fn)
    with a2:
        if st.button(
            "Saját megfogalmazás értékelése",
            key="sw_mi_sermon_assess",
            disabled=not ai_ready or not idea_draft,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_sermon_assess(generate_fn)

    _render_sermon_suggestion_results()
    _render_sermon_assessment_results()
    _render_textus_basis_expander()
    _render_decisions_for_section(_SOURCE_SERMON_MAIN)


def render_human_condition_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Emberi helyzet és kegyelmi válasz — kézi szerkesztő + opcionális MI-segéd."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Emberi helyzet és kegyelmi válasz")
    st.markdown(
        "Vizsgáld meg, milyen emberi helyzetet tár fel a textus, és mit "
        "cselekszik ebben a helyzetben Isten. Ne csak problémát keress: "
        "figyelj a korlátozottságra, téves bizalomra, félelemre, vágyra, "
        "törésre és reménységre is."
    )

    for field, label, _category, _optional in _HC_FIELDS:
        st.text_area(
            label,
            key=_KEY_HC[field],
            height=80,
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_hc_save_draft"):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_HC.items()
            }
            if not (block["condition"] or block["divine_action"]):
                st.warning(
                    "A mentéshez legalább az emberi helyzet vagy Isten "
                    "cselekvése mezőt töltsd ki."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "human_condition", block
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_hc_approve",
        ):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_HC.items()
            }
            if not (block["condition"] or block["divine_action"]):
                st.warning(
                    "A jóváhagyáshoz legalább az emberi helyzet vagy Isten "
                    "cselekvése mezőt töltsd ki."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "human_condition", block
                )
                added = 0
                skipped = 0
                for field, _label, category, _optional in _HC_FIELDS:
                    content = block.get(field) or ""
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_HUMAN,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_HUMAN,
                        category,
                        content,
                    )
                    added += 1
                if added and skipped:
                    st.success(
                        f"Jóváhagyva. {added} új döntés került továbbvitelre; "
                        f"{skipped} már szerepelt."
                    )
                elif added:
                    st.success(
                        f"Jóváhagyva és továbbvíve ({added} homiletikai döntés)."
                    )
                else:
                    st.success(
                        "Jóváhagyva. A kitöltött elemek már szerepeltek a "
                        "homiletikai döntések között."
                    )

    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Az MI a jóváhagyott textusműhelyi eredményekből segít "
        "megfogalmazni és megvizsgálni az emberi helyzetet és a kegyelmi választ. "
        "A végső döntés továbbra is a prédikátoré."
    )
    ai_ready = generate_fn is not None
    hc_filled = any(
        (st.session_state.get(wkey) or "").strip() for wkey in _KEY_HC.values()
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Javaslat készítése",
            key="sw_mi_hc_suggest",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_hc_suggest(generate_fn)
    with a2:
        if st.button(
            "Saját elemzés értékelése",
            key="sw_mi_hc_assess",
            disabled=not ai_ready or not hc_filled,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_hc_assess(generate_fn)

    _render_hc_suggestion_results()
    _render_hc_assessment_results()

    st.caption("Következő ajánlott lépés: Hallgatói kérdés és feszültség")
    _render_decisions_for_section(_SOURCE_HUMAN)


def _run_lt_suggest(generate_fn: GenerateFn) -> None:
    kwargs = _collect_m5_kwargs()
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return
    with st.spinner(
        "A hallgatói kérdést, ellenállást és a prédikációt mozgató "
        "feszültséget vizsgálom…"
    ):
        result = suggest_listener_tension(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_listener_tension_suggestions(
        st.session_state,
        _lt_suggestion_payload(result),
    )
    if not (
        result.recommended_listener_question.strip()
        or result.recommended_listener_resistance.strip()
        or result.recommended_tension.strip()
    ):
        st.info(
            "A rendelkezésre álló anyag alapján nem készült felelős javaslat. "
            "Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslatok elkészültek.")


def _run_lt_assess(generate_fn: GenerateFn) -> None:
    block = {
        field: (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_LT.items()
    }
    if not any(block.values()):
        st.warning("Nincs kitöltött megfogalmazás az értékeléshez.")
        return
    kwargs = _collect_m5_kwargs()
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return
    with st.spinner(
        "A hallgatói kérdés, ellenállás és feszültség megfogalmazását vizsgálom…"
    ):
        result = assess_listener_tension(
            **kwargs,
            listener_tension=block,
            generate_fn=generate_fn,
        )
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_listener_tension_assessment(
        st.session_state,
        _lt_assessment_payload(result),
    )
    st.success("Az értékelés elkészült.")


def _render_lt_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("listener_tension_suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (sw.get("m5_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    q = str(sugs.get("recommended_listener_question") or "").strip()
    r = str(sugs.get("recommended_listener_resistance") or "").strip()
    t = str(sugs.get("recommended_tension") or "").strip()
    expanded = str(sugs.get("expanded_summary") or "").strip()

    with st.container(border=True):
        st.markdown("**Ajánlott hallgatói kérdés**")
        st.markdown(q or "—")
        st.markdown("**Ajánlott hallgatói ellenállás**")
        st.markdown(r or "—")
        st.markdown("**Ajánlott központi feszültség**")
        st.markdown(t or "—")
        if expanded:
            st.caption("Rövid kifejtés")
            st.markdown(expanded)

        ui_all = {
            "listener_question": q,
            "listener_resistance": r,
            "sermon_tension": t,
        }
        if any(ui_all.values()):
            if st.button("Átveszem mindhármat", key="sw_mi_lt_adopt_all"):
                _request_adopt_lt_block(ui_all)
            c1, c2, c3 = st.columns(3)
            with c1:
                if q and st.button("Kérdés átvétele", key="sw_mi_lt_adopt_q"):
                    _request_adopt_lt_block({"listener_question": q})
            with c2:
                if r and st.button("Ellenállás átvétele", key="sw_mi_lt_adopt_r"):
                    _request_adopt_lt_block({"listener_resistance": r})
            with c3:
                if t and st.button("Feszültség átvétele", key="sw_mi_lt_adopt_t"):
                    _request_adopt_lt_block({"sermon_tension": t})
        else:
            st.info(
                "Nincs átvehető ajánlás (elégtelen adat vagy üres modellválasz)."
            )

    alt_sets = sugs.get("alternative_sets") or []
    if isinstance(alt_sets, list) and alt_sets:
        with st.expander("További javaslatok", expanded=False):
            for idx, alt in enumerate(alt_sets[:2]):
                if not isinstance(alt, dict):
                    continue
                aq = str(alt.get("listener_question") or "").strip()
                ar = str(alt.get("listener_resistance") or "").strip()
                at = str(alt.get("tension") or "").strip()
                if not (aq or ar or at):
                    continue
                with st.container(border=True):
                    st.markdown(f"**Alternatíva {idx + 1}**")
                    if aq:
                        st.markdown(f"*Kérdés:* {aq}")
                    if ar:
                        st.markdown(f"*Ellenállás:* {ar}")
                    if at:
                        st.markdown(f"*Feszültség:* {at}")
                    if st.button(
                        "Átveszem ezt a hármast",
                        key=f"sw_mi_lt_adopt_alt_{idx}",
                    ):
                        _request_adopt_lt_block(
                            {
                                "listener_question": aq,
                                "listener_resistance": ar,
                                "sermon_tension": at,
                            }
                        )

    reasoning = str(sugs.get("reasoning_summary") or "").strip()
    basis = sugs.get("basis") or []
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_basis = isinstance(basis, list) and any(str(x).strip() for x in basis)
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)
    if reasoning or has_basis or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_basis:
                st.markdown("**Alapok**")
                for item in basis:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def _render_lt_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    payload = sw.get("listener_tension_assessment")
    if not isinstance(payload, dict):
        return

    overall = str(payload.get("overall_assessment") or "").strip()
    strengths = payload.get("strengths") or []
    improvements = payload.get("improvements") or []
    rq = str(payload.get("revised_listener_question") or "").strip()
    rr = str(payload.get("revised_listener_resistance") or "").strip()
    rt = str(payload.get("revised_tension") or "").strip()
    warnings = payload.get("warnings") or []

    with st.expander("Szakmai értékelés részletei", expanded=False):
        if overall:
            st.markdown("**Összegzés**")
            st.markdown(overall)
        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Erősségek**")
            for item in strengths:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")
        if isinstance(improvements, list) and any(str(x).strip() for x in improvements):
            st.markdown("**Javítási szempontok**")
            for item in improvements:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        st.markdown("**Átdolgozott javaslatok**")
        if rq:
            st.markdown(f"*Hallgatói kérdés:* {rq}")
            if st.button("Átdolgozott kérdés átvétele", key="sw_mi_lt_adopt_rev_q"):
                _request_adopt_lt_block({"listener_question": rq})
        if rr:
            st.markdown(f"*Hallgatói ellenállás:* {rr}")
            if st.button(
                "Átdolgozott ellenállás átvétele", key="sw_mi_lt_adopt_rev_r"
            ):
                _request_adopt_lt_block({"listener_resistance": rr})
        if rt:
            st.markdown(f"*Központi feszültség:* {rt}")
            if st.button(
                "Átdolgozott feszültség átvétele", key="sw_mi_lt_adopt_rev_t"
            ):
                _request_adopt_lt_block({"sermon_tension": rt})
        if rq or rr or rt:
            if st.button(
                "Átdolgozott hármas átvétele", key="sw_mi_lt_adopt_rev_all"
            ):
                _request_adopt_lt_block(
                    {
                        "listener_question": rq,
                        "listener_resistance": rr,
                        "sermon_tension": rt,
                    }
                )
        else:
            st.caption("Nincs átdolgozott javaslat.")

        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            st.markdown("**Figyelmeztetések**")
            for item in warnings:
                line = str(item or "").strip()
                if line:
                    st.warning(line)


def render_listener_tension_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Hallgatói kérdés és feszültség — kézi szerkesztő + opcionális MI-segéd."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    tw = ensure_text_workshop_state(st.session_state)

    st.subheader("Hallgatói kérdés és feszültség")
    st.markdown(
        "Tisztázd, milyen valódi kérdést, nehézséget vagy ellenállást érinthet "
        "a textus a hallgatóban. A cél nem mesterséges dráma, hanem a "
        "felismeréshez vezető feszültség megnevezése."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    text_idea = (tw.get("text_main_idea") or "").strip()
    text_status = (tw.get("text_main_idea_status") or "").strip()
    sermon_idea = (sw.get("sermon_main_idea") or "").strip()
    sermon_status = (sw.get("sermon_main_idea_status") or "").strip()
    if text_status != "approved" and sermon_status != "approved":
        st.info(
            "A szakasz használható, de a munka biztosabb, ha előbb jóváhagyod "
            "a textus vagy az igehirdetés fő gondolatát."
        )
    elif sermon_status != "approved" and not sermon_idea:
        st.caption(
            f"Textus fő gondolat: {(text_idea[:120] + '…') if len(text_idea) > 120 else text_idea or '—'}"
        )

    for field, title, help_text, placeholder, _category in _LT_FIELDS:
        st.markdown(f"**{title}**")
        st.caption(help_text)
        st.text_area(
            title,
            key=_KEY_LT[field],
            height=90,
            label_visibility="collapsed",
            placeholder=placeholder,
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_lt_save_draft"):
            current = (
                sw.get("listener_tension")
                if isinstance(sw.get("listener_tension"), dict)
                else {}
            )
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_LT.items()
            }
            block["promised_resolution"] = str(
                current.get("promised_resolution") or ""
            )
            if not any(block[f] for f in _KEY_LT):
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                update_sermon_workshop_section(
                    st.session_state, "listener_tension", block
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_lt_approve",
        ):
            current = (
                sw.get("listener_tension")
                if isinstance(sw.get("listener_tension"), dict)
                else {}
            )
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_LT.items()
            }
            block["promised_resolution"] = str(
                current.get("promised_resolution") or ""
            )
            if not any(block[f] for f in _KEY_LT):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "listener_tension", block
                )
                added = 0
                skipped = 0
                for field, _title, _help, _ph, category in _LT_FIELDS:
                    content = block.get(field) or ""
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_LISTENER,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_LISTENER,
                        category,
                        content,
                    )
                    added += 1
                if added and skipped:
                    st.success(
                        f"Jóváhagyva. {added} új döntés került továbbvitelre; "
                        f"{skipped} már szerepelt."
                    )
                elif added:
                    st.success(
                        f"Jóváhagyva és továbbvíve ({added} homiletikai döntés)."
                    )
                else:
                    st.success(
                        "Jóváhagyva. A kitöltött elemek már szerepeltek a "
                        "homiletikai döntések között."
                    )

    saved = ensure_sermon_workshop_state(st.session_state).get("listener_tension") or {}
    if isinstance(saved, dict) and any(str(saved.get(k) or "").strip() for k in _KEY_LT):
        st.caption("Elmentett állapot: **vázlat / jóváhagyott döntésekkel** (lásd lent)")

    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Az MI a jóváhagyott textus- és igehirdetési műhelyeredményekből segít "
        "megfogalmazni a hallgatói kérdést, az ellenállást és a központi "
        "feszültséget. A végső döntés továbbra is a prédikátoré."
    )
    ai_ready = generate_fn is not None
    lt_filled = any(
        (st.session_state.get(wkey) or "").strip() for wkey in _KEY_LT.values()
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Javaslatok készítése",
            key="sw_mi_lt_suggest",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_lt_suggest(generate_fn)
    with a2:
        if st.button(
            "Saját megfogalmazás értékelése",
            key="sw_mi_lt_assess",
            disabled=not ai_ready or not lt_filled,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_lt_assess(generate_fn)

    _render_lt_suggestion_results()
    _render_lt_assessment_results()

    st.caption("Következő ajánlott lépés: Krisztus-központú és evangéliumi ív")
    _render_decisions_for_section(_SOURCE_LISTENER)


def _run_ga_suggest(generate_fn: GenerateFn) -> None:
    if st.session_state.get("_sw_m5_ga_suggest_running"):
        return
    st.session_state["_sw_m5_ga_suggest_running"] = True
    try:
        kwargs = _collect_gospel_arc_kwargs()
        with st.spinner("Evangéliumi ív javaslat készül…"):
            result = suggest_gospel_arc(**kwargs, generate_fn=generate_fn)
        save_gospel_arc_suggestions(
            st.session_state, _ga_suggestion_payload(result)
        )
        if result.ok and (
            result.recommended_divine_gracious_action
            or result.recommended_christ_connection
            or result.recommended_promised_resolution
            or result.recommended_grace_enabled_response
        ):
            st.success("A javaslatok elkészültek.")
        elif result.ok:
            st.info(
                result.reasoning_summary
                or "Nincs elegendő anyag felelős javaslathoz."
            )
        else:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
                )
            )
    finally:
        st.session_state["_sw_m5_ga_suggest_running"] = False


def _run_ga_assess(generate_fn: GenerateFn) -> None:
    if st.session_state.get("_sw_m5_ga_assess_running"):
        return
    st.session_state["_sw_m5_ga_assess_running"] = True
    try:
        kwargs = _collect_gospel_arc_kwargs()
        with st.spinner("Az evangéliumi ív értékelése készül…"):
            result = assess_gospel_arc(
                **kwargs,
                generate_fn=generate_fn,
            )
        save_gospel_arc_assessment(
            st.session_state, _ga_assessment_payload(result)
        )
        if result.ok:
            st.success("Az értékelés elkészült.")
        else:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült. Próbáld újra később.",
                )
            )
    finally:
        st.session_state["_sw_m5_ga_assess_running"] = False


def _render_ga_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("gospel_arc_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not any(
        str(data.get(k) or "").strip()
        for k in (
            "recommended_divine_gracious_action",
            "recommended_christ_connection",
            "recommended_promised_resolution",
            "recommended_grace_enabled_response",
        )
    ):
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback="A legutóbbi javaslatkészítés nem sikerült.",
        )
        if err:
            st.warning(err)
        return

    divine = str(data.get("recommended_divine_gracious_action") or "").strip()
    christ = str(data.get("recommended_christ_connection") or "").strip()
    ctype = normalize_christ_connection_type(
        data.get("recommended_christ_connection_type")
    )
    resolution = str(data.get("recommended_promised_resolution") or "").strip()
    grace = str(data.get("recommended_grace_enabled_response") or "").strip()
    expanded = str(data.get("expanded_summary") or "").strip()
    confidence = str(data.get("confidence") or "low").strip().casefold()
    if not (divine or christ or resolution or grace or expanded):
        missing = data.get("missing_information") or []
        warnings = data.get("warnings") or []
        if missing or warnings:
            st.markdown("**MI-javaslat**")
            for item in warnings if isinstance(warnings, list) else []:
                line = str(item or "").strip()
                if line:
                    st.warning(line)
            if isinstance(missing, list) and any(str(x).strip() for x in missing):
                st.caption("Hiányzó információk: " + "; ".join(
                    str(x).strip() for x in missing if str(x).strip()
                ))
        return

    st.markdown("**MI-javaslat**")
    if divine:
        st.markdown(f"**Isten kegyelmi cselekvése**  \n{divine}")
    if christ:
        st.markdown(f"**Krisztus-kapcsolat**  \n{christ}")
    st.markdown(
        f"**Kapcsolat típusa:** {christ_connection_type_label(ctype)}  \n"
        f"**Bizonyosság:** {_CONFIDENCE_LABELS_HU.get(confidence, confidence)}"
    )
    if ctype == "none_or_uncertain":
        st.info(
            "A rendelkezésre álló anyag alapján a konkrét Krisztus-kapcsolat még "
            "további vizsgálatot igényel."
        )
    if resolution:
        st.markdown(f"**Evangéliumi feloldás**  \n{resolution}")
    if grace:
        st.markdown(f"**Kegyelemből fakadó válasz**  \n{grace}")
    if expanded:
        st.markdown("**Rövid kifejtés**")
        st.write(expanded)

    if st.button("Átveszem mindet", key="sw_mi_ga_adopt_all"):
        _request_adopt_ga_block(
            {
                "divine_gracious_action": divine,
                "christ_connection": christ,
                "christ_connection_type": ctype,
                "promised_resolution": resolution,
                "grace_enabled_response": grace,
            }
        )

    c1, c2 = st.columns(2)
    with c1:
        if divine and st.button(
            "Kegyelmi cselekvés átvétele", key="sw_mi_ga_adopt_divine"
        ):
            _request_adopt_ga_block({"divine_gracious_action": divine})
        if christ and st.button(
            "Krisztus-kapcsolat átvétele", key="sw_mi_ga_adopt_christ"
        ):
            _request_adopt_ga_block(
                {"christ_connection": christ, "christ_connection_type": ctype}
            )
    with c2:
        if resolution and st.button(
            "Feloldás átvétele", key="sw_mi_ga_adopt_resolution"
        ):
            _request_adopt_ga_block({"promised_resolution": resolution})
        if grace and st.button(
            "Emberi válasz átvétele", key="sw_mi_ga_adopt_grace"
        ):
            _request_adopt_ga_block({"grace_enabled_response": grace})
    if ctype and st.button(
        "Kapcsolattípus átvétele", key="sw_mi_ga_adopt_type"
    ):
        _request_adopt_ga_block({"christ_connection_type": ctype})

    alts = data.get("alternative_connections") or []
    if isinstance(alts, list) and any(isinstance(a, dict) for a in alts):
        with st.expander("Alternatív kapcsolódási irányok", expanded=False):
            for idx, alt in enumerate(alts[:2]):
                if not isinstance(alt, dict):
                    continue
                a_conn = str(alt.get("christ_connection") or "").strip()
                a_type = normalize_christ_connection_type(alt.get("connection_type"))
                a_emp = str(alt.get("emphasis") or "").strip()
                if not (a_conn or a_emp):
                    continue
                st.markdown(
                    f"**Alternatíva {idx + 1}** — "
                    f"{christ_connection_type_label(a_type)}"
                )
                if a_conn:
                    st.write(a_conn)
                if a_emp:
                    st.caption(f"Hangsúly: {a_emp}")
                if st.button(
                    "Ezt a kapcsolatot átveszem",
                    key=f"sw_mi_ga_adopt_alt_{idx}",
                ):
                    _request_adopt_ga_block(
                        {
                            "christ_connection": a_conn,
                            "christ_connection_type": a_type,
                        }
                    )

    basis = data.get("basis") or []
    reasoning = str(data.get("reasoning_summary") or "").strip()
    if reasoning or (isinstance(basis, list) and any(str(x).strip() for x in basis)):
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.write(reasoning)
            if isinstance(basis, list):
                for item in basis:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")

    warnings = data.get("warnings") or []
    missing = data.get("missing_information") or []
    if isinstance(warnings, list):
        for item in warnings:
            line = str(item or "").strip()
            if line:
                st.warning(line)
    if isinstance(missing, list) and any(str(x).strip() for x in missing):
        st.caption(
            "Hiányzó információk: "
            + "; ".join(str(x).strip() for x in missing if str(x).strip())
        )


def _render_ga_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("gospel_arc_assessment")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not str(data.get("overall_assessment") or "").strip():
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback="A legutóbbi értékelés nem sikerült.",
        )
        if err:
            st.warning(err)
        return

    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and not any(
        str(data.get(k) or "").strip()
        for k in (
            "revised_divine_gracious_action",
            "revised_christ_connection",
            "revised_promised_resolution",
            "revised_grace_enabled_response",
        )
    ):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)

    strengths = data.get("strengths") or []
    if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
        st.markdown("**Erősségek**")
        for item in strengths:
            line = str(item or "").strip()
            if line:
                st.markdown(f"- {line}")

    improvements = data.get("improvements") or []
    if isinstance(improvements, list) and any(str(x).strip() for x in improvements):
        st.markdown("**Javítási irányok**")
        for item in improvements:
            line = str(item or "").strip()
            if line:
                st.markdown(f"- {line}")

    type_assess = str(data.get("connection_type_assessment") or "").strip()
    if type_assess:
        st.markdown(f"**Kapcsolattípus értékelése**  \n{type_assess}")

    rd = str(data.get("revised_divine_gracious_action") or "").strip()
    rc = str(data.get("revised_christ_connection") or "").strip()
    rt = normalize_christ_connection_type(
        data.get("suggested_christ_connection_type") or ""
    )
    rr = str(data.get("revised_promised_resolution") or "").strip()
    rg = str(data.get("revised_grace_enabled_response") or "").strip()
    has_rev = bool(rd or rc or rr or rg or data.get("suggested_christ_connection_type"))
    if has_rev:
        st.markdown("**Átdolgozott javaslatok**")
        if rd:
            st.markdown(f"*Isten kegyelmi cselekvése:* {rd}")
            if st.button(
                "Átdolgozott kegyelmi cselekvés átvétele",
                key="sw_mi_ga_adopt_rev_divine",
            ):
                _request_adopt_ga_block({"divine_gracious_action": rd})
        if rc:
            st.markdown(f"*Krisztus-kapcsolat:* {rc}")
            if st.button(
                "Átdolgozott Krisztus-kapcsolat átvétele",
                key="sw_mi_ga_adopt_rev_christ",
            ):
                block = {"christ_connection": rc}
                if data.get("suggested_christ_connection_type"):
                    block["christ_connection_type"] = rt
                _request_adopt_ga_block(block)
        if data.get("suggested_christ_connection_type"):
            st.markdown(
                f"*Javasolt kapcsolattípus:* {christ_connection_type_label(rt)}"
            )
            if st.button(
                "Javasolt típus átvétele", key="sw_mi_ga_adopt_rev_type"
            ):
                _request_adopt_ga_block({"christ_connection_type": rt})
        if rr:
            st.markdown(f"*Evangéliumi feloldás:* {rr}")
            if st.button(
                "Átdolgozott feloldás átvétele", key="sw_mi_ga_adopt_rev_resolution"
            ):
                _request_adopt_ga_block({"promised_resolution": rr})
        if rg:
            st.markdown(f"*Kegyelemből fakadó válasz:* {rg}")
            if st.button(
                "Átdolgozott emberi válasz átvétele", key="sw_mi_ga_adopt_rev_grace"
            ):
                _request_adopt_ga_block({"grace_enabled_response": rg})
        if rd or rc or rr or rg:
            if st.button(
                "Átdolgozott ív átvétele", key="sw_mi_ga_adopt_rev_all"
            ):
                _request_adopt_ga_block(
                    {
                        "divine_gracious_action": rd,
                        "christ_connection": rc,
                        "christ_connection_type": rt
                        if data.get("suggested_christ_connection_type")
                        else "",
                        "promised_resolution": rr,
                        "grace_enabled_response": rg,
                    }
                )

    warnings = data.get("warnings") or []
    if isinstance(warnings, list):
        for item in warnings:
            line = str(item or "").strip()
            if line:
                st.warning(line)


def render_gospel_arc_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Krisztus-központú és evangéliumi ív — kézi szerkesztő + MI-segéd."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    tw = ensure_text_workshop_state(st.session_state)

    st.subheader("Krisztus-központú és evangéliumi ív")
    st.markdown(
        "Mutasd meg, mit tesz Isten, hogyan kapcsolódik a textus Krisztushoz, "
        "és milyen kegyelemből fakadó válasz következhet. A cél nem az erőltetett "
        "krisztologizálás, hanem a textushű evangéliumi feloldási ív."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    text_status = (tw.get("text_main_idea_status") or "").strip()
    sermon_status = (sw.get("sermon_main_idea_status") or "").strip()
    if text_status != "approved" and sermon_status != "approved":
        st.info(
            "A szakasz használható, de a munka biztosabb, ha előbb jóváhagyod "
            "a textus vagy az igehirdetés fő gondolatát."
        )

    for field, title, help_text, placeholder, _category in _GA_TEXT_FIELDS:
        if field == "promised_resolution":
            # Kapcsolattípus a Krisztus-kapcsolat után, feloldás előtt
            st.markdown("**Kapcsolat típusa**")
            st.caption(_GA_TYPE_HELP)
            st.selectbox(
                "Kapcsolat típusa",
                options=list(CHRIST_CONNECTION_TYPES),
                format_func=lambda v: CHRIST_CONNECTION_TYPE_LABELS_HU.get(
                    v, str(v)
                ),
                key=_KEY_GA["christ_connection_type"],
                label_visibility="collapsed",
            )
            if (
                st.session_state.get(_KEY_GA["christ_connection_type"])
                == "none_or_uncertain"
            ):
                st.caption(
                    "A rendelkezésre álló anyag alapján a konkrét Krisztus-kapcsolat "
                    "még további vizsgálatot igényelhet."
                )
        st.markdown(f"**{title}**")
        st.caption(help_text)
        st.text_area(
            title,
            key=_KEY_GA[field],
            height=90,
            label_visibility="collapsed",
            placeholder=placeholder,
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_ga_save_draft"):
            filled = any(
                (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_GA.items()
                if field != "christ_connection_type"
            ) or bool(st.session_state.get(_KEY_GA["christ_connection_type"]))
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                _persist_gospel_arc_from_widgets()
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_ga_approve",
        ):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_GA.items()
            }
            block["christ_connection_type"] = normalize_christ_connection_type(
                block.get("christ_connection_type")
            )
            if not any(
                block.get(f)
                for f in (
                    "divine_gracious_action",
                    "christ_connection",
                    "promised_resolution",
                    "grace_enabled_response",
                )
            ):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                _persist_gospel_arc_from_widgets()
                text_items = [
                    (field, title, category)
                    for field, title, _help, _ph, category in _GA_TEXT_FIELDS
                ]
                # Add type as decision if meaningful
                added = 0
                skipped = 0
                for field, _title, category in text_items:
                    content = block.get(field) or ""
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_GOSPEL,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_GOSPEL,
                        category,
                        content,
                    )
                    added += 1
                type_label = christ_connection_type_label(
                    block.get("christ_connection_type")
                )
                type_content = f"Kapcsolat típusa: {type_label}"
                if block.get("christ_connection_type") and block.get(
                    "christ_connection_type"
                ) != "none_or_uncertain":
                    if not _decision_is_duplicate(
                        source_section=_SOURCE_GOSPEL,
                        category="Kapcsolat típusa",
                        content=type_content,
                    ):
                        add_approved_sermon_decision(
                            st.session_state,
                            _SOURCE_GOSPEL,
                            "Kapcsolat típusa",
                            type_content,
                        )
                        added += 1
                    else:
                        skipped += 1
                if added and skipped:
                    st.success(
                        f"Jóváhagyva. {added} új döntés került továbbvitelre; "
                        f"{skipped} már szerepelt."
                    )
                elif added:
                    st.success(
                        f"Jóváhagyva és továbbvíve ({added} homiletikai döntés)."
                    )
                else:
                    st.success(
                        "Jóváhagyva. A kitöltött elemek már szerepeltek a "
                        "homiletikai döntések között."
                    )

    saved_arc = (
        ensure_sermon_workshop_state(st.session_state).get("christ_centered_arc") or {}
    )
    saved_lt = (
        ensure_sermon_workshop_state(st.session_state).get("listener_tension") or {}
    )
    if isinstance(saved_arc, dict) and (
        any(
            str(saved_arc.get(k) or "").strip()
            for k in (
                "divine_gracious_action",
                "christ_connection",
                "grace_enabled_response",
            )
        )
        or (
            isinstance(saved_lt, dict)
            and str(saved_lt.get("promised_resolution") or "").strip()
        )
    ):
        st.caption("Elmentett állapot: **vázlat / jóváhagyott döntésekkel** (lásd lent)")

    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Az MI a jóváhagyott műhelyeredményekből segít megfogalmazni az "
        "evangéliumi ívet. Nem erőltet kapcsolatot, ahol az nem megalapozható. "
        "A végső döntés a prédikátoré."
    )
    ai_ready = generate_fn is not None
    ga_filled = any(
        (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_GA.items()
        if field != "christ_connection_type"
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Javaslatok készítése",
            key="sw_mi_ga_suggest",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_ga_suggest(generate_fn)
    with a2:
        if st.button(
            "Saját megfogalmazás értékelése",
            key="sw_mi_ga_assess",
            disabled=not ai_ready or not ga_filled,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_ga_assess(generate_fn)

    _render_ga_suggestion_results()
    _render_ga_assessment_results()

    st.caption("Következő ajánlott lépés: Az igehirdetés útja és mozgásai")
    _render_decisions_for_section(_SOURCE_GOSPEL)


def _default_role_for_index(index: int) -> str:
    defaults = (
        "opening",
        "tension",
        "deepening",
        "gospel_resolution",
        "arrival",
    )
    if 0 <= index < len(defaults):
        return defaults[index]
    return "deepening"


def _render_movement_editor(mv: dict[str, str], *, index: int, total: int) -> None:
    mid = str(mv.get("id") or "")
    title_preview = (
        st.session_state.get(_mv_widget_key(mid, "title")) or mv.get("title") or ""
    ).strip() or f"Mozgás {index + 1}"
    role_preview = normalize_movement_role(
        st.session_state.get(_mv_widget_key(mid, "role")) or mv.get("role") or ""
    )
    header = f"{index + 1}. {title_preview} — {movement_role_label(role_preview)}"
    with st.expander(header, expanded=False):
        st.text_input(
            "Cím (munkacím)",
            key=_mv_widget_key(mid, "title"),
            placeholder="Rövid munkacím…",
        )
        st.selectbox(
            "Funkció",
            options=list(MOVEMENT_ROLES),
            format_func=lambda v: MOVEMENT_ROLE_LABELS_HU.get(v, str(v)),
            key=_mv_widget_key(mid, "role"),
        )
        st.text_area(
            "Központi tartalom",
            key=_mv_widget_key(mid, "core_content"),
            height=90,
            placeholder="Egyetlen világos bekezdés…",
            help=(
                "Mit bont ki ez a mozgás? Egyetlen világos bekezdésben fogalmazd meg, "
                "ne írd meg a teljes prédikációrészt."
            ),
        )
        st.text_area(
            "Textusbeli alap",
            key=_mv_widget_key(mid, "textual_basis"),
            height=70,
            placeholder="Vers, kifejezés, kép vagy összefüggés…",
            help=(
                "Melyik versre, kifejezésre, képre vagy szövegbeli összefüggésre épül "
                "ez a mozgás?"
            ),
        )
        st.text_area(
            "Hallgatói felismerés",
            key=_mv_widget_key(mid, "listener_discovery"),
            height=70,
            placeholder="Mit láthat meg másként a hallgató…",
            help="Mit láthat meg másként a hallgató ennek a mozgásnak a végére?",
        )
        st.text_area(
            "Átmenet a következőhöz",
            key=_mv_widget_key(mid, "transition_to_next"),
            height=70,
            placeholder="Mi teszi szükségessé a következő mozgást…",
            help=(
                "Mi teszi szükségessé a következő mozgást? Ne csak azt írd: "
                "„Térjünk át a következő pontra.”"
            ),
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button(
                "Feljebb",
                key=f"sw_mv_up_{mid}",
                disabled=index <= 0,
            ):
                _persist_sermon_movements_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                mvs = normalize_sermon_movements(sw.get("sermon_movements"))
                if index > 0 and index < len(mvs):
                    mvs[index - 1], mvs[index] = mvs[index], mvs[index - 1]
                    update_sermon_workshop_section(
                        st.session_state, "sermon_movements", mvs
                    )
                    st.session_state[_RESYNC_FLAG] = True
                    st.rerun()
        with c2:
            if st.button(
                "Lejjebb",
                key=f"sw_mv_down_{mid}",
                disabled=index >= total - 1,
            ):
                _persist_sermon_movements_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                mvs = normalize_sermon_movements(sw.get("sermon_movements"))
                if index < len(mvs) - 1:
                    mvs[index + 1], mvs[index] = mvs[index], mvs[index + 1]
                    update_sermon_workshop_section(
                        st.session_state, "sermon_movements", mvs
                    )
                    st.session_state[_RESYNC_FLAG] = True
                    st.rerun()
        with c3:
            pending = st.session_state.get(_MV_DELETE_PENDING)
            if pending == mid:
                if st.button("Igen, törlés", key=f"sw_mv_del_yes_{mid}", type="primary"):
                    _persist_sermon_movements_from_widgets()
                    sw = ensure_sermon_workshop_state(st.session_state)
                    mvs = [
                        m
                        for m in normalize_sermon_movements(sw.get("sermon_movements"))
                        if str(m.get("id") or "") != mid
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "sermon_movements", mvs
                    )
                    st.session_state.pop(_MV_DELETE_PENDING, None)
                    _clear_movement_widgets()
                    st.session_state[_RESYNC_FLAG] = True
                    st.rerun()
                if st.button("Mégse", key=f"sw_mv_del_no_{mid}"):
                    st.session_state.pop(_MV_DELETE_PENDING, None)
                    st.rerun()
            else:
                if st.button("Törlés", key=f"sw_mv_del_{mid}"):
                    st.session_state[_MV_DELETE_PENDING] = mid
                    st.rerun()


def _path_suggestion_payload(result: SermonPathSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _path_assessment_payload(result: SermonPathAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _run_sermon_path_suggest(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Igehirdetési út javaslata készül…"):
        kwargs = _collect_sermon_path_kwargs()
        result = suggest_sermon_path(**kwargs, generate_fn=generate_fn)
        save_sermon_path_suggestions(
            st.session_state, _path_suggestion_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.path_rationale or result.movements
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_sermon_path_assess(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Saját út és mozgások értékelése…"):
        kwargs = _collect_sermon_path_kwargs()
        result = assess_sermon_path(**kwargs, generate_fn=generate_fn)
        save_sermon_path_assessment(
            st.session_state, _path_assessment_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


def _render_sermon_path_suggestions() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_path_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        data.get("path_rationale") or data.get("movements")
    ):
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return

    path_type = normalize_sermon_path_type(data.get("recommended_path_type"))
    rationale = str(data.get("path_rationale") or "").strip()
    starting = str(data.get("starting_point") or "").strip()
    destination = str(data.get("destination") or "").strip()
    movements = normalize_sermon_movements(data.get("movements"))
    expanded = str(data.get("expanded_summary") or "").strip()
    alts = data.get("alternative_paths") if isinstance(data.get("alternative_paths"), list) else []
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    reasoning = str(data.get("reasoning_summary") or "").strip()

    if not (rationale or starting or destination or movements):
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    st.markdown("**MI-javaslat**")
    st.markdown(
        f"**Ajánlott úttípus:** {sermon_path_type_label(path_type)}"
    )
    if rationale:
        st.markdown(f"**Miért illik ehhez a textushoz?**  \n{rationale}")
    if starting:
        st.markdown(f"**Kiindulópont**  \n{starting}")
    if movements:
        st.markdown("**Mozgások**")
        for idx, mv in enumerate(movements, start=1):
            role = movement_role_label(mv.get("role"))
            title = str(mv.get("title") or f"Mozgás {idx}")
            with st.expander(f"{idx}. {title} — {role}", expanded=False):
                if mv.get("core_content"):
                    st.write(mv["core_content"])
                if mv.get("textual_basis"):
                    st.caption(f"Textusbeli alap: {mv['textual_basis']}")
                if mv.get("listener_discovery"):
                    st.caption(f"Hallgatói felismerés: {mv['listener_discovery']}")
                if mv.get("transition_to_next"):
                    st.caption(f"Átmenet: {mv['transition_to_next']}")
                if st.button(
                    f"Átveszem ezt a mozgást ({idx})",
                    key=f"sw_mi_path_adopt_mv_{idx}",
                ):
                    current = _read_movements_from_widgets()
                    if len(current) >= MAX_MOVEMENTS:
                        st.warning(f"Legfeljebb {MAX_MOVEMENTS} mozgás lehet.")
                    else:
                        new_mv = empty_sermon_movement(
                            role=normalize_movement_role(mv.get("role"))
                        )
                        for field in _MV_FIELDS:
                            if field == "role":
                                continue
                            new_mv[field] = str(mv.get(field) or "")
                        new_mv["role"] = normalize_movement_role(mv.get("role")) or "deepening"
                        current.append(new_mv)
                        _request_adopt_movements(current)
    if destination:
        st.markdown(f"**Megérkezési pont**  \n{destination}")
    if expanded:
        st.markdown("**Az egész út rövid összefoglalása**")
        st.write(expanded)

    if st.button("Átveszem az egész tervet", key="sw_mi_path_adopt_all"):
        _request_adopt_path_plan(
            path_block={
                "type": path_type,
                "reason": rationale,
                "starting_point": starting,
                "destination": destination,
            },
            movements=movements,
        )
    c1, c2, c3 = st.columns(3)
    with c1:
        if rationale and st.button("Átveszem az indoklást", key="sw_mi_path_adopt_reason"):
            _request_adopt_path_block({"reason": rationale, "type": path_type})
    with c2:
        if starting and st.button(
            "Átveszem a kiindulópontot", key="sw_mi_path_adopt_start"
        ):
            _request_adopt_path_block({"starting_point": starting})
    with c3:
        if destination and st.button(
            "Átveszem a megérkezést", key="sw_mi_path_adopt_dest"
        ):
            _request_adopt_path_block({"destination": destination})

    if alts:
        with st.expander("Alternatív igehirdetési utak", expanded=False):
            for i, alt in enumerate(alts[:2], start=1):
                if not isinstance(alt, dict):
                    continue
                a_type = normalize_sermon_path_type(alt.get("path_type"))
                st.markdown(
                    f"**{i}. {sermon_path_type_label(a_type)}**  \n"
                    f"{alt.get('emphasis') or ''}  \n"
                    f"*{alt.get('reason_for_use') or ''}*"
                )
                if st.button(
                    f"Átveszem ezt az úttípust ({i})",
                    key=f"sw_mi_path_adopt_alt_{i}",
                ):
                    _request_adopt_path_block({"type": a_type})

    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for item in basis:
                if item:
                    st.markdown(f"- {item}")

    if warnings:
        for w in warnings:
            if w:
                st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_sermon_path_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_path_assessment")
    if not isinstance(data, dict):
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and data.get("ok") is False:
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    if not overall and not data.get("revised_movements"):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)
    for key, label in (
        ("path_type_assessment", "Úttípus"),
        ("structure_assessment", "Szerkezet"),
        ("gospel_turn_assessment", "Evangéliumi fordulat"),
        ("transition_assessment", "Átmenetek"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if s:
                st.markdown(f"- {s}")
    if improvements:
        st.markdown("**Javítási javaslatok**")
        for s in improvements:
            if s:
                st.markdown(f"- {s}")

    revised_reason = str(data.get("revised_path_rationale") or "").strip()
    revised_start = str(data.get("revised_starting_point") or "").strip()
    revised_dest = str(data.get("revised_destination") or "").strip()
    revised_mvs = normalize_sermon_movements(data.get("revised_movements"))
    if revised_reason or revised_start or revised_dest or revised_mvs:
        st.markdown("**Javított javaslatok**")
        if revised_reason:
            st.markdown(f"*Indoklás:* {revised_reason}")
        if revised_start:
            st.markdown(f"*Kiindulópont:* {revised_start}")
        if revised_dest:
            st.markdown(f"*Megérkezés:* {revised_dest}")
        if revised_mvs:
            for idx, mv in enumerate(revised_mvs, start=1):
                with st.expander(
                    f"Javított mozgás {idx}: {mv.get('title') or '—'}",
                    expanded=False,
                ):
                    st.write(mv.get("core_content") or "")
                    if st.button(
                        f"Átveszem a javított mozgást ({idx})",
                        key=f"sw_mi_path_adopt_rev_mv_{idx}",
                    ):
                        current = _read_movements_from_widgets()
                        if len(current) >= MAX_MOVEMENTS:
                            st.warning(f"Legfeljebb {MAX_MOVEMENTS} mozgás lehet.")
                        else:
                            new_mv = empty_sermon_movement(
                                role=normalize_movement_role(mv.get("role"))
                            )
                            for field in _MV_FIELDS:
                                if field != "role":
                                    new_mv[field] = str(mv.get(field) or "")
                            new_mv["role"] = (
                                normalize_movement_role(mv.get("role")) or "deepening"
                            )
                            current.append(new_mv)
                            _request_adopt_movements(current)
        if st.button("Átveszem a javított egész tervet", key="sw_mi_path_adopt_rev_all"):
            path_block: dict[str, str] = {}
            if revised_reason:
                path_block["reason"] = revised_reason
            if revised_start:
                path_block["starting_point"] = revised_start
            if revised_dest:
                path_block["destination"] = revised_dest
            _request_adopt_path_plan(
                path_block=path_block or None,
                movements=revised_mvs or None,
            )

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if w:
            st.warning(str(w))


def render_sermon_path_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Az igehirdetés útja és mozgásai — kézi szerkesztő + MI-segéd."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Az igehirdetés útja és mozgásai")
    st.markdown(
        "Itt nem kész prédikációvázlatot írunk, hanem megtervezzük, milyen "
        "felismerési úton haladjon végig a hallgató."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    if (sw.get("sermon_main_idea_status") or "").strip() != "approved":
        st.info(
            "A szakasz használható, de a javaslatkészítéshez előbb jóvá kell "
            "hagyni az igehirdetés fő gondolatát, és szükség van központi "
            "feszültségre, valamint evangéliumi feloldásra vagy Isten kegyelmi "
            "cselekvésére."
        )

    st.markdown("**Az igehirdetés útja**")
    st.selectbox(
        "Úttípus",
        options=list(SERMON_PATH_TYPES),
        format_func=lambda v: SERMON_PATH_TYPE_LABELS_HU.get(v, str(v)),
        key=_KEY_PATH["type"],
    )
    st.text_area(
        "Az út rövid indoklása",
        key=_KEY_PATH["reason"],
        height=80,
        placeholder="Miért illik ez az út a textushoz…",
        help=(
            "Röviden fogalmazd meg, miért illik ez az út a textushoz, a központi "
            "feszültséghez és az igehirdetés fő gondolatához."
        ),
    )
    st.text_area(
        "Kiindulópont",
        key=_KEY_PATH["starting_point"],
        height=80,
        placeholder="Kérdés, tapasztalat, kép, jelenet vagy feszültség…",
        help=(
            "Hol találkozzon először a hallgató a textussal? Ez lehet kérdés, "
            "tapasztalat, kép, jelenet, állítás vagy a textus egyik feszültsége."
        ),
    )
    st.text_area(
        "Megérkezési pont",
        key=_KEY_PATH["destination"],
        height=80,
        placeholder="Felismerés, hitbeli látás vagy kegyelemből fakadó válasz…",
        help=(
            "Milyen felismeréshez, hitbeli látáshoz vagy kegyelemből fakadó "
            "válaszhoz érkezzen meg a hallgató az igehirdetés végére?"
        ),
    )

    st.markdown("**Prédikációs mozgások**")
    st.caption(
        f"3–5 mozgás (ajánlott: {DEFAULT_MOVEMENT_COUNT}). "
        "A mozgás felismerési lépés, nem hagyományos prédikációs pont."
    )
    movements = normalize_sermon_movements(
        ensure_sermon_workshop_state(st.session_state).get("sermon_movements")
    )
    if not movements:
        st.info("Még nincs mozgás. Adj hozzá egyet, vagy kérj MI-javaslatot.")
    for idx, mv in enumerate(movements):
        _render_movement_editor(mv, index=idx, total=len(movements))

    add_cols = st.columns(2)
    with add_cols[0]:
        if st.button(
            "Mozgás hozzáadása",
            key="sw_path_add_movement",
            disabled=len(movements) >= MAX_MOVEMENTS,
        ):
            _persist_sermon_path_from_widgets()
            _persist_sermon_movements_from_widgets()
            sw = ensure_sermon_workshop_state(st.session_state)
            mvs = normalize_sermon_movements(sw.get("sermon_movements"))
            if len(mvs) < MAX_MOVEMENTS:
                mvs.append(
                    empty_sermon_movement(role=_default_role_for_index(len(mvs)))
                )
                update_sermon_workshop_section(
                    st.session_state, "sermon_movements", mvs
                )
                st.session_state[_RESYNC_FLAG] = True
                st.rerun()
    with add_cols[1]:
        if st.button(
            f"{DEFAULT_MOVEMENT_COUNT} üres mozgás",
            key="sw_path_seed_movements",
            disabled=len(movements) > 0,
        ):
            seeded = [
                empty_sermon_movement(role=_default_role_for_index(i))
                for i in range(DEFAULT_MOVEMENT_COUNT)
            ]
            update_sermon_workshop_section(
                st.session_state, "sermon_movements", seeded
            )
            _clear_movement_widgets()
            st.session_state[_RESYNC_FLAG] = True
            st.rerun()

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_path_save_draft"):
            _persist_sermon_path_from_widgets()
            _persist_sermon_movements_from_widgets()
            path = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_PATH.items()
            }
            mvs = _read_movements_from_widgets()
            filled = any(path.values()) or any(
                (m.get("title") or m.get("core_content") or "").strip() for m in mvs
            )
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="sw_path_approve",
        ):
            _persist_sermon_path_from_widgets()
            _persist_sermon_movements_from_widgets()
            path = {
                "type": normalize_sermon_path_type(
                    st.session_state.get(_KEY_PATH["type"])
                ),
                "reason": (st.session_state.get(_KEY_PATH["reason"]) or "").strip(),
                "starting_point": (
                    st.session_state.get(_KEY_PATH["starting_point"]) or ""
                ).strip(),
                "destination": (
                    st.session_state.get(_KEY_PATH["destination"]) or ""
                ).strip(),
            }
            mvs = _read_movements_from_widgets()
            if not any(
                path.get(k) for k in ("reason", "starting_point", "destination")
            ) and not any(
                (m.get("title") or m.get("core_content") or "").strip() for m in mvs
            ):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                if len(mvs) < MIN_MOVEMENTS:
                    st.warning(
                        f"Javasolt legalább {MIN_MOVEMENTS} mozgás; "
                        f"jelenleg {len(mvs)} van. A jóváhagyás így is megtörténhet."
                    )
                decisions = [
                    ("type", "Úttípus", sermon_path_type_label(path["type"])),
                    ("reason", "Út indoklása", path["reason"]),
                    ("starting_point", "Kiindulópont", path["starting_point"]),
                    ("destination", "Megérkezési pont", path["destination"]),
                ]
                added = 0
                skipped = 0
                for _field, category, content in decisions:
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_PATH,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_PATH,
                        category,
                        content,
                    )
                    added += 1
                for idx, mv in enumerate(mvs, start=1):
                    summary = (
                        f"{idx}. {mv.get('title') or 'Mozgás'} "
                        f"({movement_role_label(mv.get('role'))}): "
                        f"{(mv.get('core_content') or '')[:180]}"
                    ).strip()
                    if not (mv.get("title") or mv.get("core_content")):
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_PATH,
                        category="Mozgás",
                        content=summary,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_PATH,
                        "Mozgás",
                        summary,
                    )
                    added += 1
                if added:
                    st.success(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    st.info("Ezek a döntések már szerepelnek.")
                else:
                    st.warning("Nem volt menthető tartalom.")

    _render_decisions_for_section(_SOURCE_PATH)

    st.markdown("---")
    st.markdown("**MI-segéd**")
    mi1, mi2 = st.columns(2)
    with mi1:
        if st.button("Igehirdetési út javaslata", key="sw_path_mi_suggest"):
            _run_sermon_path_suggest(generate_fn=generate_fn)
    with mi2:
        if st.button("Saját út és mozgások értékelése", key="sw_path_mi_assess"):
            _run_sermon_path_assess(generate_fn=generate_fn)

    _render_sermon_path_suggestions()
    _render_sermon_path_assessment()

    st.caption("Következő ajánlott lépés: Képek, illusztrációk és alkalmazás")


def _render_section_placeholder(section: str) -> None:
    meta = _SW_SECTION_PLACEHOLDERS.get(section) or {
        "goal": "Ez a szakasz a későbbi mérföldkövekben válik működővé.",
        "later": "Itt később homiletikai döntést hozol.",
    }
    st.subheader(section)
    st.markdown(f"**Cél:** {meta['goal']}")
    st.markdown(meta["later"])
    st.caption("Következő fejlesztési mérföldkőben válik működővé.")


def flush_sermon_workshop_from_widgets() -> None:
    """Élő Streamlit widgetek → tartós `sermon_workshop` (ha a widget létezik).

    A fejléc Mentés / autosave előtt hívandó, hogy a még nem „Mentés
    vázlatként” gombbal elmentett mezők se vesszenek el — ugyanaz a minta,
    mint a Bibliai szöveg `save_bible_text_from_widgets` hívása.
    Nem változtatja a jóváhagyási státuszokat (draft/approved).
    """
    ensure_sermon_workshop_state(st.session_state)

    if _KEY_SERMON_IDEA in st.session_state:
        update_sermon_workshop_section(
            st.session_state,
            "sermon_main_idea",
            (st.session_state.get(_KEY_SERMON_IDEA) or "").strip(),
        )

    if all(wkey in st.session_state for wkey in _KEY_HC.values()):
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_HC.items()
        }
        update_sermon_workshop_section(st.session_state, "human_condition", block)

    if all(wkey in st.session_state for wkey in _KEY_LT.values()):
        sw = ensure_sermon_workshop_state(st.session_state)
        current = (
            sw.get("listener_tension")
            if isinstance(sw.get("listener_tension"), dict)
            else {}
        )
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_LT.items()
        }
        # promised_resolution a GA widgetből jöhet, ha létezik
        if _KEY_GA["promised_resolution"] in st.session_state:
            block["promised_resolution"] = (
                st.session_state.get(_KEY_GA["promised_resolution"]) or ""
            ).strip()
        else:
            block["promised_resolution"] = str(
                current.get("promised_resolution") or ""
            )
        update_sermon_workshop_section(st.session_state, "listener_tension", block)

    if all(
        wkey in st.session_state
        for field, wkey in _KEY_GA.items()
        if field != "promised_resolution"
    ):
        _persist_gospel_arc_from_widgets()

    if all(wkey in st.session_state for wkey in _KEY_PATH.values()):
        _persist_sermon_path_from_widgets()

    if any(
        isinstance(k, str) and k.startswith(_MV_WIDGET_PREFIX)
        for k in st.session_state.keys()
    ):
        _persist_sermon_movements_from_widgets()

    if any(
        isinstance(k, str)
        and (
            k.startswith(_IMG_WIDGET_PREFIX)
            or k.startswith(_ILL_WIDGET_PREFIX)
            or k.startswith(_APP_WIDGET_PREFIX)
        )
        for k in st.session_state.keys()
    ):
        _persist_enrichment_from_widgets()

    if all(wkey in st.session_state for wkey in _KEY_CL.values()):
        _persist_closing_from_widgets()

    if all(wkey in st.session_state for wkey in _KEY_DIAG.values()):
        _persist_self_review_from_widgets()

    if (
        _KEY_LECTION["reference"] in st.session_state
        or _KEY_LECTION["user_focus"] in st.session_state
    ):
        _persist_lection_from_widgets(include_text=True)

    if _KEY_PRAYER_COMMON["tone_preference"] in st.session_state:
        _persist_prayer_from_widgets()

    if (
        _KEY_OUTLINE["main_idea"] in st.session_state
        or _KEY_OUTLINE["opening_direction"] in st.session_state
        or _KEY_OUTLINE["manual_notes"] in st.session_state
        or any(
            isinstance(k, str) and k.startswith(_OUTLINE_MV_PREFIX)
            for k in st.session_state.keys()
        )
    ):
        # Csak valódi tartalomváltozáskor jelöljük kézi szerkesztésnek.
        _persist_outline_from_widgets(mark_manual_edit=None)


def render_sermon_workshop_shell(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Igehirdetési műhely keret — működő szakaszok + helyőrzők."""
    _apply_pending_adopts_if_needed()
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    ensure_text_workshop_state(st.session_state)

    st.header("Igehirdetési műhely")
    st.caption(
        "A textus megértésétől a hallható, textushű és kegyelemközpontú "
        "igehirdetés felépítéséig."
    )

    _render_shell_input_summary()

    if st.session_state.get(_KEY_ACTIVE_SECTION) not in _SW_SECTION_OPTIONS:
        legacy = str(st.session_state.get(_KEY_ACTIVE_SECTION) or "")
        if legacy in ("A prédikáció útja", "Prédikációs mozgások"):
            st.session_state[_KEY_ACTIVE_SECTION] = "Az igehirdetés útja és mozgásai"
        elif legacy == "Lezárás":
            st.session_state[_KEY_ACTIVE_SECTION] = "Lezárás és megérkezés"
        else:
            st.session_state[_KEY_ACTIVE_SECTION] = _SW_SECTION_OPTIONS[0]

    render_section_stepper(
        _SW_SECTION_OPTIONS,
        key=_KEY_ACTIVE_SECTION,
        completed=sermon_completed_sections(st.session_state),
        label="Aktív szakasz",
    )

    active = st.session_state.get(_KEY_ACTIVE_SECTION) or _SW_SECTION_OPTIONS[0]
    if active == "Az igehirdetés fő gondolata":
        render_sermon_main_idea_section(generate_fn=generate_fn)
    elif active == "Emberi helyzet és kegyelmi válasz":
        render_human_condition_section(generate_fn=generate_fn)
    elif active == "Hallgatói kérdés és feszültség":
        render_listener_tension_section(generate_fn=generate_fn)
    elif active == "Krisztus-központú és evangéliumi ív":
        render_gospel_arc_section(generate_fn=generate_fn)
    elif active == "Az igehirdetés útja és mozgásai":
        render_sermon_path_section(generate_fn=generate_fn)
    elif active == "Képek, illusztrációk és alkalmazás":
        render_enrichment_section(generate_fn=generate_fn)
    elif active == "Lezárás és megérkezés":
        render_closing_section(generate_fn=generate_fn)
    elif active == "Lekciójavaslat":
        render_lection_section(generate_fn=generate_fn)
    elif active == "Imádsági előkészítés":
        render_prayer_section(generate_fn=generate_fn)
    elif active == "Igehirdetési vázlat":
        render_outline_section(generate_fn=generate_fn)
    elif active == "Homiletikai diagnosztika":
        render_diagnostics_section(generate_fn=generate_fn)
    else:
        _render_section_placeholder(active)

    if active not in (
        "Az igehirdetés fő gondolata",
        "Emberi helyzet és kegyelmi válasz",
        "Hallgatói kérdés és feszültség",
        "Krisztus-központú és evangéliumi ív",
        "Az igehirdetés útja és mozgásai",
        "Képek, illusztrációk és alkalmazás",
        "Lezárás és megérkezés",
        "Lekciójavaslat",
        "Imádsági előkészítés",
        "Igehirdetési vázlat",
        "Homiletikai diagnosztika",
    ):
        next_hint = _SW_NEXT_HINTS.get(active)
        if next_hint:
            st.caption(next_hint)
    elif active == "Az igehirdetés fő gondolata":
        st.caption(_SW_NEXT_HINTS[active])
    elif active == "Lekciójavaslat":
        st.caption(_SW_NEXT_HINTS[active])
    elif active == "Imádsági előkészítés":
        st.caption(_SW_NEXT_HINTS[active])
    elif active == "Igehirdetési vázlat":
        st.caption(_SW_NEXT_HINTS[active])


__all__ = [
    "render_sermon_workshop_shell",
    "flush_sermon_workshop_from_widgets",
    "render_sermon_main_idea_section",
    "render_human_condition_section",
    "render_listener_tension_section",
    "render_gospel_arc_section",
    "render_sermon_path_section",
    "render_enrichment_section",
    "render_closing_section",
    "render_lection_section",
    "render_prayer_section",
    "render_outline_section",
    "render_diagnostics_section",
]
