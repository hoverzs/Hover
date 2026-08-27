"""Phase 3G-B1/B2: illustration reviewer/admin panel.

Internal-only Streamlit view for reviewing enrichment-pipeline output
(`illustration_units`) against the Phase 3G-A human-review backend
contract. Reads and writes ONLY through
`illustration_engine.illustration_unit_repository`'s public API -- this
module never issues its own SQL against unit content, tags, or
lifecycle state.

Access control is NOT decided by app.py's auth/session code -- `app.py`
calls `is_authorized_reviewer()` (defined in this module) BEFORE routing
into `render_illustration_review_panel()`, and this module assumes that
check already passed once inside. `is_authorized_reviewer` itself never
touches `st.session_state`, cookies, or the OAuth flow -- it only
combines two independent read-only signals (see its docstring) into one
access decision.

Phase 3G-B2 adds reviewer-SIDE ONLY risk triage (`compute_review_risk`)
and a legacy/current-strategy mismatch check
(`_is_legacy_strategy_mismatch`) -- both pure functions computed at
render time from an already-loaded `IllustrationReviewItem`. Neither
adds a DB column, a table, or a write path; they exist purely to help a
human reviewer prioritize which of many `needs_review` units need deep
manual attention versus a lighter pass.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import streamlit as st

from illustration_engine.enrichment_pipeline import EnrichmentStrategy, derive_enrichment_strategy
from illustration_engine.illustration_sqlite import (
    DEFAULT_DATABASE_PATH,
    PILOT_HOMILETIC_FUNCTIONS,
    PILOT_TONES,
    PILOT_TOPICS,
)
from illustration_engine.illustration_unit_repository import (
    IllustrationReviewItem,
    approve_unit,
    get_review_item,
    list_review_items,
    publish_unit,
    replace_review_tags,
    send_back_for_rework,
    update_draft_unit,
)
from ui_components import render_info_panel, render_page_intro

# Single-reviewer internal tool -- same hardcoded-owner-identity
# precedent as app.py's FEEDBACK_TO_EMAIL. No role/permission table.
REVIEWER_EMAIL = "hoverzsolt@gmail.com"

_SELECTED_UNIT_KEY = "ill_review_selected_unit_id"
_FILTER_STATUS_KEY = "ill_review_filter_status"
_FILTER_SOURCE_KEY = "ill_review_filter_source"
_FILTER_WARNINGS_KEY = "ill_review_filter_warnings_only"
_FILTER_RISK_KEY = "ill_review_filter_risk"
_FILTER_MISMATCH_ONLY_KEY = "ill_review_filter_mismatch_only"
_FILTER_LIMIT_KEY = "ill_review_filter_limit"
_CONFIRM_PUBLISH_PREFIX = "ill_review_confirm_publish_"

_STATUS_OPTIONS = ("needs_review", "approved", "published")
_RISK_FILTER_OPTIONS = ("Mind", "High priority", "Clean / normal")


# ---------------------------------------------------------------------------
# Phase 3G-B2: reviewer-side-only risk triage. Pure functions over an
# already-loaded IllustrationReviewItem -- no DB schema change, no new
# table/column, no write path. See module docstring.
# ---------------------------------------------------------------------------

# Mirrors derive_enrichment_strategy's own full_story_translation ceiling
# (enrichment_pipeline._MAX_FULL_TRANSLATION_CHARS) -- not re-imported
# directly (that constant is private to enrichment_pipeline) but the same
# value, used here purely as a reviewer-attention heuristic.
_LONG_SOURCE_THRESHOLD_CHARS = 1500
# Mirrors the pipeline's own established retrieval-ready band ceiling
# (enrichment_pipeline._MAX_CONDENSED_MODERN_TEXT_CHARS, formally enforced
# only for condensed_story) -- used here as a general reviewer-risk
# heuristic regardless of derivation_type.
_LONG_MODERN_TEXT_THRESHOLD_CHARS = 1500
_HIGHER_RISK_DERIVATION_TYPES = frozenset({"condensed_story", "extracted_scene"})


@dataclass(frozen=True)
class ReviewRisk:
    level: str  # "high" or "normal"
    reasons: tuple[str, ...]
    is_legacy_mismatch: bool
    current_expected_mode: str
    current_expected_derivation_type: str | None


def _is_legacy_strategy_mismatch(stored_derivation_type: str, current_strategy: EnrichmentStrategy) -> bool:
    """A unit is a legacy/current-strategy mismatch when the
    derivation_type actually stored on it would no longer be valid under
    TODAY's deterministic length strategy (`derive_enrichment_strategy`)
    for its story's CURRENT `original_text` length.

    - `current_strategy.expected_mode == "direct_unit"`: mismatch iff the
      stored `derivation_type` isn't exactly what length now dictates
      (a full_story_translation/condensed_story mix-up).
    - `current_strategy.expected_mode == "unit_proposal"`: a stored
      `full_story_translation` or `condensed_story` IS a mismatch -- both
      mean "the whole story was translated/condensed as ONE direct unit,"
      which today's rules no longer allow past the length threshold; the
      story would have to go through the human-in-the-loop unit_proposal
      path first. A stored `extracted_scene` is deliberately NOT flagged
      here -- it is itself proposal-derived content, i.e. already the
      correct shape for a long story under current rules."""
    if current_strategy.expected_mode == "direct_unit":
        return stored_derivation_type != current_strategy.expected_derivation_type
    return stored_derivation_type in ("full_story_translation", "condensed_story")


def compute_review_risk(item: IllustrationReviewItem) -> ReviewRisk:
    """Reviewer-side risk triage -- HIGH if any flagged criterion
    matches, otherwise NORMAL. Criteria: enrichment_warnings present;
    legacy/current-strategy mismatch; source length > 1500 chars;
    narrative_status_confidence == "low"; modern_hu_text length > 1500
    chars; derivation_type in (condensed_story, extracted_scene)."""
    original_length = len(item.original_text or "")
    current_strategy = derive_enrichment_strategy(original_length)
    mismatch = _is_legacy_strategy_mismatch(item.derivation_type, current_strategy)

    reasons: list[str] = []
    if item.enrichment_warnings:
        reasons.append(f"{len(item.enrichment_warnings)} enrichment warning")
    if mismatch:
        expected = current_strategy.expected_mode
        if current_strategy.expected_derivation_type:
            expected = f"{expected}/{current_strategy.expected_derivation_type}"
        reasons.append(
            f"legacy/current-strategy mismatch (tárolt: {item.derivation_type}, jelenlegi elvárás: {expected})"
        )
    if original_length > _LONG_SOURCE_THRESHOLD_CHARS:
        reasons.append(f"forrás hossza {original_length} > {_LONG_SOURCE_THRESHOLD_CHARS} karakter")
    if item.narrative_status_confidence == "low":
        reasons.append("narrative_status_confidence = low")
    modern_length = len(item.modern_hu_text or "")
    if modern_length > _LONG_MODERN_TEXT_THRESHOLD_CHARS:
        reasons.append(f"modern_hu_text hossza {modern_length} > {_LONG_MODERN_TEXT_THRESHOLD_CHARS} karakter")
    if item.derivation_type in _HIGHER_RISK_DERIVATION_TYPES:
        reasons.append(f"derivation_type={item.derivation_type} (proposal/condensed típus)")

    return ReviewRisk(
        level="high" if reasons else "normal",
        reasons=tuple(reasons),
        is_legacy_mismatch=mismatch,
        current_expected_mode=current_strategy.expected_mode,
        current_expected_derivation_type=current_strategy.expected_derivation_type,
    )


def is_authenticated_owner(*, is_logged_in: bool, email: str | None) -> bool:
    """Production access path: a real Google login whose email matches
    the hardcoded reviewer/owner address."""
    return bool(is_logged_in) and (email or "").strip().lower() == REVIEWER_EMAIL


# Deliberately narrower than auth_config's own local-runtime concept.
# auth_config.is_local_runtime() also treats 192.168.*/10.* addresses as
# "local" -- a reasonable, already-reviewed call for ITS use case (is an
# OAuth redirect_uri safe to point at localhost), but too wide for an
# auth bypass: a cloud/container deployment's internal network address
# can easily be 10.* or 192.168.*, so that alone must never grant
# reviewer access. This module never changes or wraps
# auth_config.is_local_runtime() -- it reads the same request host via
# auth_config.request_host() and applies its own, strictly-narrower
# loopback-only allowlist instead. Exactly these three values count --
# nothing else, ever.
_STRICT_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_strict_loopback_host(host: str | None) -> bool:
    return (host or "").strip().lower() in _STRICT_LOCAL_HOSTS


def is_local_loopback_request() -> bool:
    """True only when the CURRENT request's Host header is exactly
    `localhost`, `127.0.0.1`, or `::1` (see `_STRICT_LOCAL_HOSTS`).

    This is the entire local-dev reviewer access path -- no env flag,
    no OAuth. A developer running `streamlit run app.py` on their own
    machine gets the reviewer panel automatically; anyone reaching the
    app over a private LAN address (10.*, 192.168.*, 172.16-31.*) or a
    public/Cloud host does not, and falls through to the production
    `is_authenticated_owner` gate instead. Fails CLOSED (`False`) on
    any error, including an empty/unavailable request host."""
    try:
        from auth_config import request_host

        return _is_strict_loopback_host(request_host())
    except Exception:
        return False


def is_authorized_reviewer(*, is_logged_in: bool, email: str | None) -> bool:
    """authorized_reviewer = strict_loopback_host OR authenticated_owner.

    Loopback dev access never touches auth/session state, cookies, or
    the OAuth flow -- it only reads the request host. It can only ever
    ADD an access path on top of the unchanged production gate, never
    remove or weaken it."""
    return is_local_loopback_request() or is_authenticated_owner(is_logged_in=is_logged_in, email=email)


@st.cache_resource(show_spinner=False)
def _get_connection() -> sqlite3.Connection:
    """One process-wide connection to the REAL illustrations DB.

    Connection boundary note (Phase 3G-B1): this is the ONLY place in
    the module that opens a `sqlite3.Connection` or issues raw SQL
    (`PRAGMA foreign_keys = ON`, nothing else) -- every other function
    in this file only ever passes the resulting connection object into
    Phase 3G-A `illustration_unit_repository` calls. There is no query
    logic of this module's own. A connection-factory helper living in
    the repository/infra layer instead of here would be a reasonable
    later cleanup, but is not needed for Phase 3G-B1 and is deliberately
    out of scope for this round.

    Deliberately does NOT call `create_schema()` -- the Phase 3G-B audit
    confirmed the review workflow never touches the Phase 3F ledger
    tables (`enrichment_runs`/`enrichment_run_items`), so this module
    has no reason to ever mutate the real file's schema on its own
    initiative. `check_same_thread=False` because `st.cache_resource`
    shares this one connection across Streamlit session threads.
    """
    connection = sqlite3.connect(str(DEFAULT_DATABASE_PATH), check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _safe_index(options: tuple[str, ...], value: str | None) -> int:
    return options.index(value) if value in options else 0


def _render_queue_filters() -> None:
    cols = st.columns([1, 1, 1, 1, 1])
    with cols[0]:
        st.selectbox("Állapot", options=_STATUS_OPTIONS, key=_FILTER_STATUS_KEY)
    with cols[1]:
        st.text_input(
            "Forrás kód (opcionális)", key=_FILTER_SOURCE_KEY, placeholder="pl. PG_AESOPS_FABLES_TOWNSEND"
        )
    with cols[2]:
        st.checkbox("Csak figyelmeztetéssel", key=_FILTER_WARNINGS_KEY)
    with cols[3]:
        st.selectbox("Kockázat", options=_RISK_FILTER_OPTIONS, key=_FILTER_RISK_KEY)
    with cols[4]:
        st.number_input(
            "Limit", min_value=1, max_value=200, value=20, step=1, key=_FILTER_LIMIT_KEY
        )
    st.checkbox("Csak legacy/mismatch", key=_FILTER_MISMATCH_ONLY_KEY)


def _load_queue(connection: sqlite3.Connection) -> list[tuple[IllustrationReviewItem, ReviewRisk]]:
    """Fetches via the Phase 3G-A review queue API (status/source/
    warnings_only/limit -- all DB-level), then applies the risk/mismatch
    filters as a pure Python post-filter over the already-fetched page --
    risk is reviewer-side metadata, not a DB column, so it cannot be
    pushed into `list_review_items`'s SQL. NOTE: this means a risk/
    mismatch filter can show fewer than `limit` results even if more
    matching units exist beyond the fetched page -- surfaced explicitly
    in the panel's info caption rather than hidden."""
    status = st.session_state.get(_FILTER_STATUS_KEY) or "needs_review"
    source_code = (st.session_state.get(_FILTER_SOURCE_KEY) or "").strip() or None
    warnings_only = bool(st.session_state.get(_FILTER_WARNINGS_KEY))
    limit = int(st.session_state.get(_FILTER_LIMIT_KEY) or 20)
    items = list_review_items(
        connection, status=status, source_code=source_code, warnings_only=warnings_only, limit=limit
    )
    risk_filter = st.session_state.get(_FILTER_RISK_KEY) or "Mind"
    mismatch_only = bool(st.session_state.get(_FILTER_MISMATCH_ONLY_KEY))

    result: list[tuple[IllustrationReviewItem, ReviewRisk]] = []
    for item in items:
        risk = compute_review_risk(item)
        if mismatch_only and not risk.is_legacy_mismatch:
            continue
        if risk_filter == "High priority" and risk.level != "high":
            continue
        if risk_filter == "Clean / normal" and risk.level != "normal":
            continue
        result.append((item, risk))
    return result


def _render_queue_list(rows: list[tuple[IllustrationReviewItem, ReviewRisk]]) -> None:
    if not rows:
        st.caption("Nincs a szűrőknek megfelelő tétel.")
        return
    selected_id = st.session_state.get(_SELECTED_UNIT_KEY)
    for item, risk in rows:
        warn_marker = " ⚠️" if item.enrichment_warnings else ""
        risk_marker = " 🔴HIGH" if risk.level == "high" else ""
        mismatch_marker = " 🧭LEGACY" if risk.is_legacy_mismatch else ""
        marker = "▶ " if item.unit_id == selected_id else ""
        label = (
            f"{marker}#{item.unit_id} · {item.title_hu or '(cím nélkül)'}"
            f"{warn_marker}{risk_marker}{mismatch_marker} · {item.source_code}"
        )
        if st.button(label, key=f"ill_review_pick_{item.unit_id}", use_container_width=True):
            st.session_state[_SELECTED_UNIT_KEY] = item.unit_id
            st.rerun()


def _render_original_column(item: IllustrationReviewItem) -> None:
    st.markdown("##### Eredeti")
    st.caption(
        f"{item.source_title} ({item.source_code}) · {item.tradition or '—'} · {item.license_status}"
    )
    st.markdown(f"**{item.title_original}**")
    # st.code() instead of a disabled st.text_area(): scrollable (fixed
    # height), fully selectable/copyable (native code block + built-in
    # copy button), and not an input-like widget at all -- a disabled
    # text_area blocks selection/copy in most browsers, which is exactly
    # the manual-QA pain point this replaces. language=None avoids Python
    # syntax highlighting being applied to plain prose.
    st.code(item.original_text or "", language=None, wrap_lines=True, height=280)
    if item.source_reference:
        st.caption(item.source_reference)


def _render_edit_column(connection: sqlite3.Connection, item: IllustrationReviewItem) -> None:
    st.markdown("##### Magyar enrichment")
    with st.form(key=f"ill_review_edit_form_{item.unit_id}"):
        title_hu = st.text_input(
            "title_hu", value=item.title_hu or "", key=f"ill_review_title_hu_{item.unit_id}"
        )
        modern_hu_text = st.text_area(
            "modern_hu_text",
            value=item.modern_hu_text or "",
            height=160,
            key=f"ill_review_modern_hu_text_{item.unit_id}",
        )
        summary_hu = st.text_area(
            "summary_hu", value=item.summary_hu or "", height=100, key=f"ill_review_summary_hu_{item.unit_id}"
        )
        moral_hu = st.text_area(
            "moral_hu", value=item.moral_hu or "", height=80, key=f"ill_review_moral_hu_{item.unit_id}"
        )
        st.caption(
            "A moral opcionális; humoros/ironikus történetnél üresen maradhat. "
            "Nem kell mesterséges tanulságot kitalálni, ha a történetnek nincs természetes morálja."
        )
        save_clicked = st.form_submit_button("Mentés (szerkesztés)")
    if save_clicked:
        try:
            update_draft_unit(
                connection,
                unit_id=item.unit_id,
                title_hu=title_hu,
                modern_hu_text=modern_hu_text,
                summary_hu=summary_hu,
                moral_hu=moral_hu,
            )
            connection.commit()
            st.success("Mentve. Állapot változatlan (nem approve).")
            st.rerun()
        except Exception as exc:  # noqa: BLE001 -- surfaced verbatim to the reviewer
            st.error(f"Mentés sikertelen: {exc}")


def _render_meta_section(item: IllustrationReviewItem) -> None:
    with st.expander("Meta / provenance", expanded=bool(item.enrichment_warnings)):
        st.write(f"derivation_type: {item.derivation_type}")
        st.write(
            f"narrative_status: {item.narrative_status or '—'} "
            f"(confidence: {item.narrative_status_confidence or '—'})"
        )
        st.write(
            f"model: {item.enrichment_model or '—'} · prompt_version: {item.enrichment_prompt_version or '—'}"
        )
        st.write(f"generated_at: {item.enrichment_generated_at or '—'}")
        st.write(f"human_reviewed_at: {item.human_reviewed_at or '—'}")
        if item.enrichment_warnings:
            for warning in item.enrichment_warnings:
                st.warning(warning)


def _render_risk_section(item: IllustrationReviewItem) -> ReviewRisk:
    risk = compute_review_risk(item)
    if risk.is_legacy_mismatch:
        expected = risk.current_expected_mode
        if risk.current_expected_derivation_type:
            expected = f"{expected}/{risk.current_expected_derivation_type}"
        st.error(
            "**LEGACY PILOT / CURRENT STRATEGY MISMATCH**\n\n"
            f"A forrás jelenlegi hossza ({len(item.original_text or '')} karakter) alapján a mai "
            f"pipeline **{expected}** stratégiát várna, a tárolt unit viszont "
            f"**{item.derivation_type}** típusú. Ez a rekord a régi pipeline-szabályokkal készült.\n\n"
            "Az Approve emiatt le van tiltva ezen a rekordon -- a helyes út jelenleg csak "
            "**Visszaküldés javításra** (a re-enrichment/derivation_type-javítás nem része ennek a körnek)."
        )
    badge = "🔴 HIGH REVIEW PRIORITY" if risk.level == "high" else "🟢 NORMAL REVIEW"
    with st.expander(f"Review risk: {badge}", expanded=(risk.level == "high")):
        if risk.reasons:
            for reason in risk.reasons:
                st.write(f"- {reason}")
        else:
            st.caption("Nincs kockázati jelző -- normál review elegendő.")
    return risk


def _render_taxonomy_section(connection: sqlite3.Connection, item: IllustrationReviewItem) -> None:
    with st.expander("Taxonómia", expanded=False):
        topics_options = tuple(sorted(PILOT_TOPICS))
        tones_options = tuple(sorted(PILOT_TONES))
        functions_options = tuple(sorted(PILOT_HOMILETIC_FUNCTIONS))
        with st.form(key=f"ill_review_tags_form_{item.unit_id}"):
            topics = st.multiselect(
                "topics (1-3)",
                options=topics_options,
                default=[t for t in item.topics if t in topics_options],
                key=f"ill_review_topics_{item.unit_id}",
            )
            tone = st.selectbox(
                "tone",
                options=tones_options,
                index=_safe_index(tones_options, item.tone),
                key=f"ill_review_tone_{item.unit_id}",
            )
            functions = st.multiselect(
                "homiletic_functions (1-2)",
                options=functions_options,
                default=[f for f in item.homiletic_functions if f in functions_options],
                key=f"ill_review_functions_{item.unit_id}",
            )
            tags_clicked = st.form_submit_button("Tag-ek mentése (teljes csere)")
        if tags_clicked:
            try:
                replace_review_tags(
                    connection, item.unit_id, topics=topics, tone=tone, homiletic_functions=functions
                )
                connection.commit()
                st.success("Tag-ek frissítve (a régi tag-ek lecserélve).")
                st.rerun()
            except ValueError as exc:
                st.error(f"Érvénytelen tag-kombináció -- semmi nem módosult: {exc}")


def _render_lifecycle_actions(
    connection: sqlite3.Connection, item: IllustrationReviewItem, risk: ReviewRisk
) -> None:
    st.markdown("##### Állapot-műveletek")
    cols = st.columns(3)

    with cols[0]:
        if item.status == "needs_review":
            if risk.is_legacy_mismatch:
                st.button(
                    "✅ Jóváhagyás (Approve)",
                    key=f"ill_review_approve_{item.unit_id}",
                    use_container_width=True,
                    disabled=True,
                )
                st.caption(
                    "Letiltva: legacy/current-strategy mismatch (lásd fent). "
                    "Használd a Visszaküldés javításra lehetőséget."
                )
            elif st.button(
                "✅ Jóváhagyás (Approve)", key=f"ill_review_approve_{item.unit_id}", use_container_width=True
            ):
                try:
                    approve_unit(connection, item.unit_id)
                    connection.commit()
                    st.success("Jóváhagyva (approved). Publish még nem történt.")
                    st.session_state[_SELECTED_UNIT_KEY] = None
                    st.rerun()
                except ValueError as exc:
                    st.error(f"Jóváhagyás sikertelen: {exc}")
        else:
            st.caption("Approve csak needs_review állapotban érhető el.")

    with cols[1]:
        confirm_key = f"{_CONFIRM_PUBLISH_PREFIX}{item.unit_id}"
        if item.status == "approved":
            if not st.session_state.get(confirm_key):
                if st.button(
                    "📢 Publikálás (Publish)", key=f"ill_review_publish_{item.unit_id}", use_container_width=True
                ):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                st.warning(
                    "Ez a lépés bekerül a felhasználói illusztráció-keresésbe "
                    "(published_illustration_units + search_units). Biztos?"
                )
                confirm_cols = st.columns(2)
                with confirm_cols[0]:
                    if st.button(
                        "Igen, publikálom", key=f"ill_review_publish_confirm_{item.unit_id}",
                        use_container_width=True,
                    ):
                        try:
                            publish_unit(connection, item.unit_id)
                            connection.commit()
                            st.success("Publikálva.")
                            st.session_state[confirm_key] = False
                            st.session_state[_SELECTED_UNIT_KEY] = None
                            st.rerun()
                        except sqlite3.IntegrityError as exc:
                            st.error(f"Publikálás sikertelen: {exc}")
                with confirm_cols[1]:
                    if st.button(
                        "Mégse", key=f"ill_review_publish_cancel_{item.unit_id}", use_container_width=True
                    ):
                        st.session_state[confirm_key] = False
                        st.rerun()
        else:
            st.caption("Publish csak approved állapotban érhető el.")

    with cols[2]:
        if item.status in ("approved", "published"):
            if item.status == "published":
                st.caption("⚠️ Publikált tétel -- a visszaküldés AZONNAL eltávolítja a nyilvános keresésből.")
            if st.button(
                "↩️ Visszaküldés javításra", key=f"ill_review_rework_{item.unit_id}", use_container_width=True
            ):
                send_back_for_rework(connection, item.unit_id)
                connection.commit()
                st.success("Visszaküldve javításra (needs_review, human_reviewed_at törölve).")
                st.session_state[_SELECTED_UNIT_KEY] = None
                st.rerun()
        else:
            st.caption("Rework csak approved/published állapotból érhető el.")


def _render_item_detail(connection: sqlite3.Connection, item: IllustrationReviewItem) -> None:
    st.divider()
    st.subheader(f"#{item.unit_id} — {item.status}")

    left, right = st.columns(2)
    with left:
        _render_original_column(item)
    with right:
        _render_edit_column(connection, item)

    _render_meta_section(item)
    risk = _render_risk_section(item)
    _render_taxonomy_section(connection, item)

    st.divider()
    _render_lifecycle_actions(connection, item, risk)


def render_illustration_review_panel() -> None:
    """Entry point called by `app.py` after the reviewer gate passes."""
    connection = _get_connection()

    render_page_intro(
        eyebrow="Belső eszköz",
        title="Illusztráció-review",
        body="Enrichment-pipeline kimenetek humán ellenőrzése, jóváhagyása és publikálása.",
    )

    _render_queue_filters()
    rows = _load_queue(connection)
    high_count = sum(1 for _, risk in rows if risk.level == "high")
    normal_count = len(rows) - high_count

    render_info_panel(
        title=f"{len(rows)} tétel a jelenlegi szűrőkkel ({high_count} high priority, {normal_count} normal)",
        body=(
            "A lista nem keresőmotor -- csak a Phase 3G-A review queue szűrőit (állapot, forrás, "
            "figyelmeztetés, limit) alkalmazza, a Kockázat/legacy szűrő pedig a MÁR betöltött (limit-en "
            "belüli) listán utószűr -- risk/mismatch szűrésnél a teljes darabszám a limit felett ennél "
            "több is lehet."
        ),
        tone="info",
    )

    _render_queue_list(rows)

    selected_id = st.session_state.get(_SELECTED_UNIT_KEY)
    if selected_id is None:
        st.info("Válassz egy tételt a fenti listából a részletek megtekintéséhez.")
        return

    item = get_review_item(connection, int(selected_id))
    if item is None:
        st.warning("A kiválasztott tétel már nem található.")
        st.session_state[_SELECTED_UNIT_KEY] = None
        return

    _render_item_detail(connection, item)


__all__ = [
    "ReviewRisk",
    "compute_review_risk",
    "is_authenticated_owner",
    "is_authorized_reviewer",
    "is_local_loopback_request",
    "render_illustration_review_panel",
]
