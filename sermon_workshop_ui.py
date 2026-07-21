"""Textus 2.0 Igehirdetési műhely — UI (M4: kézi + MI-segéd).

Nem importál az app.py-ból. A Gemini-hívást a hívó által átadott
`generate_fn` végzi (tipikusan `generate_text`).
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from bible_text_ui import render_bible_text_preview
from sermon_workshop_data import (
    add_approved_sermon_decision,
    ensure_sermon_workshop_state,
    remove_approved_sermon_decision,
    save_human_condition_assessment,
    save_human_condition_suggestion,
    save_listener_tension_assessment,
    save_listener_tension_suggestions,
    save_sermon_main_idea_assessment,
    save_sermon_main_idea_suggestions,
    update_sermon_workshop_section,
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
from textus_workshop_data import ensure_text_workshop_state

GenerateFn = Callable[..., str]

_SW_SECTION_OPTIONS = [
    "Az igehirdetés fő gondolata",
    "Emberi helyzet és kegyelmi válasz",
    "Hallgatói kérdés és feszültség",
    "Krisztus-központú és evangéliumi ív",
    "A prédikáció útja",
    "Prédikációs mozgások",
    "Képek, illusztrációk és alkalmazás",
    "Lezárás",
    "Homiletikai diagnosztika",
]

_SW_SECTION_PLACEHOLDERS: dict[str, dict[str, str]] = {
    "Krisztus-központú és evangéliumi ív": {
        "goal": (
            "Meghatározni, hogyan kapcsolódik a textus Krisztushoz "
            "és az evangéliumhoz — erőltetés nélkül."
        ),
        "later": (
            "Itt jelölöd a kapcsolattípust, a kegyelem elsőbbségét, "
            "és a bizonytalanságot, ha a kapcsolat közvetett."
        ),
    },
    "A prédikáció útja": {
        "goal": (
            "Kiválasztani, hogyan haladjon a prédikáció "
            "(például elöl kimondott állítás, közös felfedezés, történet)."
        ),
        "later": (
            "Itt a forma természetes nyelven jelenik meg — nem "
            "szakzsargon-fülekben."
        ),
    },
    "Prédikációs mozgások": {
        "goal": (
            "3–5 felismerési mozgásban megtervezni, mit lát meg a "
            "hallgató szakaszról szakaszra."
        ),
        "later": (
            "Itt nem pontlistát, hanem indulást, felismerést és "
            "továbbhaladást szerkesztesz."
        ),
    },
    "Képek, illusztrációk és alkalmazás": {
        "goal": (
            "Válogatni textusból eredő képeket, illusztrációkat és "
            "konkrét alkalmazásokat."
        ),
        "later": (
            "Itt a meglévő illusztráció / aktualizálás anyagából is "
            "átvehetsz elemeket — a régi promptok változatlanok maradnak."
        ),
    },
    "Lezárás": {
        "goal": (
            "Meghatározni, hová érkezik a hallgató, milyen reménységet "
            "visz, és mi maradjon nyitott."
        ),
        "later": (
            "Itt a lezárás nem puszta összefoglaló, és nem érzelmi "
            "manipuláció."
        ),
    },
    "Homiletikai diagnosztika": {
        "goal": (
            "Rövid, szöveges tükrözést kapni textushűségről, egységről, "
            "kegyelemről és hallhatóságról."
        ),
        "later": (
            "Itt legfeljebb három javítási prioritás jelenik meg — "
            "pontszám és automatikus átírás nélkül."
        ),
    },
}

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
        "Következő ajánlott lépés: A prédikáció útja"
    ),
    "A prédikáció útja": "Következő ajánlott lépés: Prédikációs mozgások",
    "Prédikációs mozgások": (
        "Következő ajánlott lépés: Képek, illusztrációk és alkalmazás"
    ),
    "Képek, illusztrációk és alkalmazás": "Következő ajánlott lépés: Lezárás",
    "Lezárás": "Következő ajánlott lépés: Homiletikai diagnosztika",
}

_STATUS_LABELS = {
    "draft": "Vázlat",
    "approved": "Jóváhagyva",
}

_SOURCE_SERMON_MAIN = "Az igehirdetés fő gondolata"
_SOURCE_HUMAN = "Emberi helyzet és kegyelmi válasz"
_SOURCE_LISTENER = "Hallgatói kérdés és feszültség"
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
_RESYNC_FLAG = "_sw_ui_resync"
_ADOPT_SERMON_PENDING = "_sw_sermon_idea_adopt_pending"
_ADOPT_HC_PENDING = "_sw_hc_adopt_pending"
_ADOPT_LT_PENDING = "_sw_lt_adopt_pending"

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


def _request_adopt_sermon_sentence(sentence: str) -> None:
    st.session_state[_ADOPT_SERMON_PENDING] = str(sentence or "").strip()
    st.rerun()


def _request_adopt_hc_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_HC_PENDING] = dict(block or {})
    st.rerun()


def _request_adopt_lt_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_LT_PENDING] = dict(block or {})
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
    return msg


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


def _render_section_placeholder(section: str) -> None:
    meta = _SW_SECTION_PLACEHOLDERS.get(section) or {
        "goal": "Ez a szakasz a későbbi mérföldkövekben válik működővé.",
        "later": "Itt később homiletikai döntést hozol.",
    }
    st.subheader(section)
    st.markdown(f"**Cél:** {meta['goal']}")
    st.markdown(meta["later"])
    st.caption("Következő fejlesztési mérföldkőben válik működővé.")


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
        st.session_state[_KEY_ACTIVE_SECTION] = _SW_SECTION_OPTIONS[0]

    st.radio(
        "Aktív szakasz",
        options=_SW_SECTION_OPTIONS,
        key=_KEY_ACTIVE_SECTION,
    )

    active = st.session_state.get(_KEY_ACTIVE_SECTION) or _SW_SECTION_OPTIONS[0]
    if active == "Az igehirdetés fő gondolata":
        render_sermon_main_idea_section(generate_fn=generate_fn)
    elif active == "Emberi helyzet és kegyelmi válasz":
        render_human_condition_section(generate_fn=generate_fn)
    elif active == "Hallgatói kérdés és feszültség":
        render_listener_tension_section(generate_fn=generate_fn)
    else:
        _render_section_placeholder(active)

    if active not in (
        "Az igehirdetés fő gondolata",
        "Emberi helyzet és kegyelmi válasz",
        "Hallgatói kérdés és feszültség",
    ):
        next_hint = _SW_NEXT_HINTS.get(active)
        if next_hint:
            st.caption(next_hint)
    elif active == "Az igehirdetés fő gondolata":
        st.caption(_SW_NEXT_HINTS[active])


__all__ = [
    "render_sermon_workshop_shell",
    "render_sermon_main_idea_section",
    "render_human_condition_section",
    "render_listener_tension_section",
]
