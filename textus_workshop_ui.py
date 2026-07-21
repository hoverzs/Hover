"""Textus 2.0 Textusműhely — kézi UI + főgondolat MI-segéd bekötés.

A textus fő gondolata és a továbbvihető felismerések felülete.
A Gemini-hívást a hívó által átadott `generate_fn` végzi
(általában az app.py `generate_text` függvénye).
Nem importál az app.py-ból (nincs körkörös import).
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from textus_main_idea_ai import (
    MainIdeaAssessmentResult,
    MainIdeaSuggestionResult,
    assess_user_main_idea,
    suggest_text_main_idea,
)
from textus_workshop_data import (
    add_approved_insight,
    ensure_text_workshop_state,
    remove_approved_insight,
    save_main_idea_assessment,
    save_main_idea_suggestions,
    update_text_main_idea,
)

GenerateFn = Callable[..., str]

_STATUS_LABELS = {
    "draft": "Vázlat",
    "approved": "Jóváhagyva",
}

_INSIGHT_SOURCES = [
    "Saját megfigyelés",
    "Áttekintés",
    "Eredeti szöveg",
    "Exegézis",
    "Kortörténet",
    "Teológia",
]

_INSIGHT_CATEGORIES = [
    "Fő gondolat",
    "Szerkezet",
    "Kulcsszó vagy kifejezés",
    "Teológiai hangsúly",
    "Emberi helyzet",
    "Isten cselekvése és kegyelme",
    "Krisztus-kapcsolat",
    "Kép vagy kontraszt",
    "Nyitott kérdés",
    "Egyéb",
]

_SOURCE_REVIEW = [
    ("overview", "Áttekintés"),
    ("original_text", "Eredeti szöveg"),
    ("exegesis", "Exegézis"),
    ("history", "Kortörténet"),
    ("theology", "Teológia"),
]

_ASSESSMENT_FIELD_LABELS = [
    ("text_fidelity", "Szöveghűség"),
    ("clarity", "Világosság"),
    ("unity", "Egység"),
    ("theological_accuracy", "Teológiai pontosság"),
    ("scope", "Terjedelem"),
    ("statement_quality", "Állítás minősége"),
    ("application_confusion", "Alkalmazással való keveredés"),
]

_MAIN_IDEA_SOURCE = "A textus fő gondolata"
_MAIN_IDEA_CATEGORY = "Fő gondolat"

# Widget / technikai kulcsok — csak session UI, nem project_data
_KEY_IDEA_INPUT = "tw_main_idea_input"
_RESYNC_FLAG = "_tw_ui_resync"
_ADOPT_PENDING = "_tw_main_idea_adopt_pending"


def _session_str(*keys: str) -> str:
    for key in keys:
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if val is not None and not isinstance(val, str):
            text = str(val).strip()
            if text:
                return text
    return ""


def _apply_pending_adopt_if_needed() -> None:
    """Átvétel: widget ELŐTT alkalmazza a pending mondatot (pending + rerun).

    Csak a szerkeszthető mezőbe másol; nem hagyja jóvá automatikusan.
    """
    pending = st.session_state.pop(_ADOPT_PENDING, None)
    if pending is None:
        return
    text = str(pending).strip()
    st.session_state[_KEY_IDEA_INPUT] = text
    update_text_main_idea(st.session_state, text, "draft")


def _apply_tw_ui_resync_if_needed() -> None:
    """Widgetkulcsok szinkronja a tartós text_workshop adatokkal (widget előtt)."""
    tw = ensure_text_workshop_state(st.session_state)
    force = bool(st.session_state.pop(_RESYNC_FLAG, False))
    idea = tw.get("text_main_idea") or ""

    if force or _KEY_IDEA_INPUT not in st.session_state:
        st.session_state[_KEY_IDEA_INPUT] = idea


def _request_adopt_sentence(sentence: str) -> None:
    """Mondat átvétele a kézi mezőbe — következő futásban, widget előtt."""
    st.session_state[_ADOPT_PENDING] = str(sentence or "").strip()
    st.rerun()


def _suggestion_payload_from_result(result: MainIdeaSuggestionResult) -> dict[str, Any]:
    return {
        "recommended": result.recommended,
        "expanded_summary": result.expanded_summary or "",
        "alternatives": list(result.alternatives),
        "reasoning_summary": result.reasoning_summary,
        "textual_basis": list(result.textual_basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _assessment_payload_from_result(result: MainIdeaAssessmentResult) -> dict[str, Any]:
    return {
        "assessment": result.assessment.to_dict(),
        "strengths": list(result.strengths),
        "revision_priorities": list(result.revision_priorities),
        "revised_version": result.revised_version,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _collect_ai_kwargs(*, user_main_idea: str) -> dict[str, Any]:
    """Sessionből MI-bemenet; illusztráció / aktualizálás / ének / vázlat nélkül."""
    history = _session_str("history")
    return {
        "passage": _session_str("last_igehely", "igehely_input"),
        "passage_text": _session_str("passage_text"),
        "occasion": _session_str("last_alkalom", "alkalom_input"),
        "user_focus": _session_str("last_sajat", "sajat_input"),
        "approved_insights": (
            ensure_text_workshop_state(st.session_state).get("approved_insights") or []
        ),
        "exegesis": _session_str("exegesis"),
        "original_text": _session_str("original_text"),
        "theology": _session_str("theology"),
        "overview": _session_str("overview"),
        "historical_context": history,
        "user_main_idea": (user_main_idea or "").strip(),
        "include_historical_context": bool(history),
    }


def _user_facing_error(result_ok: bool, error_message: str, *, fallback: str) -> str:
    if result_ok:
        return ""
    msg = (error_message or "").strip()
    if not msg:
        return fallback
    # Ne szivárogtassunk hosszú technikai dumpot / kulcsot
    if len(msg) > 280:
        return fallback
    lower = msg.casefold()
    if "api key" in lower or "apikey" in lower or "x-goog-api-key" in lower:
        return fallback
    return msg


def _render_source_materials_expander() -> None:
    """Csak olvasható áttekintés a már elkészült műhelyanyagokról."""
    with st.expander("Korábbi műhelyanyagok áttekintése", expanded=False):
        any_content = False
        for key, label in _SOURCE_REVIEW:
            text = (st.session_state.get(key) or "").strip()
            if not text:
                continue
            any_content = True
            with st.expander(label, expanded=False):
                st.markdown(text)

        if not any_content:
            st.info(
                "Még nincs áttekinthető műhelyanyag. "
                "Ha az előző szakaszokban generálsz tartalmat, itt fog megjelenni."
            )


def _render_suggestion_results() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    sugs = tw.get("main_idea_suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (tw.get("main_idea_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    recommended = (sugs.get("recommended") or "").strip()
    expanded = (sugs.get("expanded_summary") or "").strip()
    alternatives = sugs.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []

    # Elsődleges: ajánlott mondat + rövid kifejtés + átvétel (csak főmondat)
    if recommended:
        with st.container(border=True):
            st.markdown("**Ajánlott fő gondolat**")
            st.markdown(recommended)
            if expanded:
                st.caption("Rövid kifejtés")
                st.markdown(expanded)
            if st.button("Átveszem", key="tw_mi_adopt_recommended"):
                _request_adopt_sentence(recommended)
    else:
        st.info(
            "Nincs ajánlott fő gondolat (elégtelen adat vagy a modell üresen hagyta). "
            "A részletek a „Mi alapján készült?” részben vannak."
        )

    # Alternatívák — alapból összecsukva
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
                    if st.button("Átveszem", key=f"tw_mi_adopt_alt_{idx}"):
                        _request_adopt_sentence(text)

    reasoning = (sugs.get("reasoning_summary") or "").strip()
    basis = sugs.get("textual_basis") or []
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
                st.markdown("**Szövegbeli alapok**")
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


def _render_assessment_results() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    assessment_payload = tw.get("main_idea_assessment")
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
        if any(str(fields.get(k) or "").strip() for k, _ in _ASSESSMENT_FIELD_LABELS):
            st.markdown("**Szempontok**")
            for key, label in _ASSESSMENT_FIELD_LABELS:
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
                key="tw_mi_adopt_revised",
            ):
                _request_adopt_sentence(revised)
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


def _run_suggest(generate_fn: GenerateFn) -> None:
    idea_draft = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()
    kwargs = _collect_ai_kwargs(user_main_idea=idea_draft)
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return

    with st.spinner(
        "A textus fő gondolatának lehetséges megfogalmazásait vizsgálom…"
    ):
        result = suggest_text_main_idea(**kwargs, generate_fn=generate_fn)

    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return

    save_main_idea_suggestions(
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


def _run_assess(generate_fn: GenerateFn) -> None:
    idea = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()
    if not idea:
        st.warning("Nincs megfogalmazás az értékeléshez.")
        return

    kwargs = _collect_ai_kwargs(user_main_idea=idea)
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return

    with st.spinner(
        "A megfogalmazást textushűségi és szakmai szempontból vizsgálom…"
    ):
        result = assess_user_main_idea(**kwargs, generate_fn=generate_fn)

    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return

    save_main_idea_assessment(
        st.session_state,
        _assessment_payload_from_result(result),
    )
    st.success("Az értékelés elkészült.")


def render_text_main_idea_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """A textus fő gondolata: kézi szerkesztő + opcionális MI-segéd."""
    _apply_pending_adopt_if_needed()
    _apply_tw_ui_resync_if_needed()
    ensure_text_workshop_state(st.session_state)

    st.header("A textus fő gondolata")
    st.markdown(
        "Fogalmazd meg egyetlen világos mondatban, mit állít ez az "
        "igeszakasz. Ne még a prédikáció témáját, hanem magának a "
        "textusnak a központi állítását keresd."
    )

    st.text_area(
        "A textus fő gondolata",
        key=_KEY_IDEA_INPUT,
        height=120,
        label_visibility="collapsed",
        placeholder="Egyetlen, világos mondat…",
    )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="tw_main_idea_save_draft_btn"):
            _save_main_idea_as_draft()
    with b2:
        if st.button(
            "Jóváhagyom és továbbviszem",
            type="primary",
            key="tw_main_idea_approve_forward_btn",
        ):
            _approve_main_idea_and_forward()

    tw = ensure_text_workshop_state(st.session_state)
    saved = (tw.get("text_main_idea") or "").strip()
    saved_status = tw.get("text_main_idea_status") or ""
    if saved or saved_status:
        label = _STATUS_LABELS.get(saved_status, saved_status or "—")
        st.caption(f"Elmentett állapot: **{label}**")

    st.markdown("---")
    st.caption(
        "Az MI a már elkészült és jóváhagyott műhelyanyagok alapján "
        "segít. A végső megfogalmazás és jóváhagyás továbbra is a "
        "prédikátor döntése."
    )

    idea_now = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()
    ai_ready = generate_fn is not None
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Javaslatok készítése",
            key="tw_mi_suggest_btn",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("A javaslatkészítés jelenleg nem érhető el.")
            else:
                _run_suggest(generate_fn)
    with c2:
        if st.button(
            "Saját megfogalmazás értékelése",
            key="tw_mi_assess_btn",
            disabled=(not ai_ready) or (not idea_now),
        ):
            if generate_fn is None:
                st.warning("Az értékelés jelenleg nem érhető el.")
            else:
                _run_assess(generate_fn)

    if not ai_ready:
        st.caption("Az MI-segéd nincs bekötve ehhez a nézethez.")

    _render_suggestion_results()
    _render_assessment_results()
    _render_source_materials_expander()


def _current_main_idea_text() -> str:
    return (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()


def _insight_is_duplicate_main_idea(content: str) -> bool:
    tw = ensure_text_workshop_state(st.session_state)
    needle = (content or "").strip()
    for item in tw.get("approved_insights") or []:
        if not isinstance(item, dict):
            continue
        if (
            (item.get("source") or "") == _MAIN_IDEA_SOURCE
            and (item.get("category") or "") == _MAIN_IDEA_CATEGORY
            and (item.get("content") or "").strip() == needle
        ):
            return True
    return False


def _save_main_idea_as_draft() -> None:
    """Mező mentése vázlatként — nem kerül az approved_insights listába."""
    content = _current_main_idea_text()
    if not content:
        st.warning("Üres fő gondolatot nem lehet menteni. Írj egy mondatot.")
        return
    update_text_main_idea(st.session_state, content, "draft")
    st.success("Vázlatként elmentve.")


def _approve_main_idea_and_forward() -> None:
    """Jóváhagyás + továbbvitel a felismerésekhez (duplikáció nélkül)."""
    content = _current_main_idea_text()
    if not content:
        st.warning(
            "Üres fő gondolatot nem lehet jóváhagyni. Írj egy mondatot."
        )
        return

    update_text_main_idea(st.session_state, content, "approved")

    if _insight_is_duplicate_main_idea(content):
        st.success(
            "Jóváhagyva. Ez a fő gondolat már szerepel a továbbvihető "
            "felismerések között."
        )
        return

    add_approved_insight(
        st.session_state,
        _MAIN_IDEA_SOURCE,
        _MAIN_IDEA_CATEGORY,
        content,
    )
    st.success("Jóváhagyva és továbbvíve a felismerésekhez.")


def _render_insight_cards() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    insights = list(tw.get("approved_insights") or [])
    if not insights:
        st.info(
            "Még nincs jóváhagyott felismerés. "
            "Add hozzá az elsőt az „Új felismerés hozzáadása” résznél, "
            "vagy használd a „Jóváhagyom és továbbviszem” gombot "
            "a fő gondolat szakaszban."
        )
        return

    for item in insights:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id") or "")
        if not iid:
            continue
        source = item.get("source") or "—"
        category = item.get("category") or "—"
        content = item.get("content") or ""
        created = item.get("created_at") or ""

        with st.container(border=True):
            st.markdown(f"**Forrás:** {source}  \n**Kategória:** {category}")
            if created:
                st.caption(f"Létrehozva: {created}")
            st.markdown(content)

            confirm_key = f"tw_insight_del_confirm_{iid}"
            if st.session_state.get(confirm_key):
                st.warning("Biztosan törölni szeretnéd ezt a felismerést?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        "Igen, törlés",
                        key=f"tw_insight_del_yes_{iid}",
                        type="primary",
                    ):
                        remove_approved_insight(st.session_state, iid)
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                with c2:
                    if st.button("Mégse", key=f"tw_insight_del_no_{iid}"):
                        st.session_state[confirm_key] = False
                        st.rerun()
            else:
                if st.button(
                    "Felismerés eltávolítása",
                    key=f"tw_insight_del_{iid}",
                ):
                    st.session_state[confirm_key] = True
                    st.rerun()


def render_approved_insights_section() -> None:
    """Jóváhagyott, továbbvihető felismerések gyűjtése (Gemini nélkül)."""
    ensure_text_workshop_state(st.session_state)

    st.header("Mit viszünk tovább?")
    st.markdown(
        "Itt gyűjtheted össze azokat a felismeréseket, amelyekre az "
        "igehirdetés felépítésekor valóban támaszkodni szeretnél."
    )

    st.subheader("Jóváhagyott felismerések")
    _render_insight_cards()

    with st.expander("Új felismerés hozzáadása", expanded=False):
        with st.form("tw_add_insight_form", clear_on_submit=True):
            source = st.selectbox("Forrás", options=_INSIGHT_SOURCES)
            category = st.selectbox("Kategória", options=_INSIGHT_CATEGORIES)
            content = st.text_area(
                "Tartalom",
                placeholder="Fogalmazd meg röviden a továbbvihető felismerést…",
                height=100,
            )
            submitted = st.form_submit_button(
                "Jóváhagyott felismerés hozzáadása",
                type="primary",
            )

        if submitted:
            text = (content or "").strip()
            if not text:
                st.warning("Üres felismerést nem lehet hozzáadni.")
            else:
                add_approved_insight(st.session_state, source, category, text)
                st.success("Felismerés hozzáadva.")
                st.rerun()

    st.caption(
        "A jóváhagyott felismerésekkel folytathatod a munkát az "
        "Igehirdetési műhelyben."
    )
    if st.button(
        "Tovább az Igehirdetési műhelybe",
        key="tw_goto_sermon_workshop_btn",
    ):
        st.session_state["ui_mode"] = "sermon_workshop"
        st.rerun()


__all__ = [
    "render_text_main_idea_section",
    "render_approved_insights_section",
]
