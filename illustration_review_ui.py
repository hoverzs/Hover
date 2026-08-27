"""Phase 3G-B1: illustration reviewer/admin panel.

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
"""

from __future__ import annotations

import os
import sqlite3

import streamlit as st

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
_FILTER_LIMIT_KEY = "ill_review_filter_limit"
_CONFIRM_PUBLISH_PREFIX = "ill_review_confirm_publish_"

_STATUS_OPTIONS = ("needs_review", "approved", "published")


def is_authenticated_owner(*, is_logged_in: bool, email: str | None) -> bool:
    """Production access path: a real Google login whose email matches
    the hardcoded reviewer/owner address."""
    return bool(is_logged_in) and (email or "").strip().lower() == REVIEWER_EMAIL


def _local_dev_flag_enabled() -> bool:
    raw = os.environ.get("TEXTUS_LOCAL_REVIEWER_ENABLED", "")
    return raw.strip().lower() in ("1", "true", "yes")


# Deliberately narrower than auth_config's own local-runtime concept.
# auth_config.is_local_runtime() also treats 192.168.*/10.* addresses as
# "local" -- a reasonable, already-reviewed call for ITS use case (is an
# OAuth redirect_uri safe to point at localhost), but too wide for an
# auth BYPASS: a cloud/container deployment's internal network address
# can easily be 10.* or 192.168.*, so that alone must never grant
# reviewer access. This module never changes or wraps
# auth_config.is_local_runtime() -- it reads the same request host via
# auth_config.request_host() and applies its own, strictly-narrower
# loopback-only allowlist instead.
_STRICT_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_strict_loopback_host(host: str | None) -> bool:
    return (host or "").strip().lower() in _STRICT_LOCAL_HOSTS


def _is_local_dev_runtime() -> bool:
    """Strict loopback-only runtime signal for the reviewer bypass --
    NOT the same concept as `auth_config.is_local_runtime()` (see
    `_STRICT_LOCAL_HOSTS` comment above for why). Fails CLOSED (`False`)
    on any error, including an empty/unavailable request host -- unlike
    `auth_config.is_local_runtime()`, an unknown host is treated as
    NON-local here, since this gates an auth bypass rather than an
    OAuth redirect safety check."""
    try:
        from auth_config import request_host

        return _is_strict_loopback_host(request_host())
    except Exception:
        return False


def is_explicit_local_dev_reviewer() -> bool:
    """Manual-QA-only escape hatch: local development has no Google
    OAuth configured, so `is_authenticated_owner()` can never pass
    there. Requires BOTH conditions -- the flag ALONE is never
    sufficient (an env var set in a misconfigured Cloud deployment must
    not grant access on its own):

    - `TEXTUS_LOCAL_REVIEWER_ENABLED` set to a truthy value, AND
    - `_is_local_dev_runtime()` independently confirming this process
      is not serving a non-local host.

    Never touches `st.session_state`, cookies, or the OAuth flow --
    this is a pure, stateless read of env + runtime-host signals."""
    if not _local_dev_flag_enabled():
        return False
    return _is_local_dev_runtime()


def is_authorized_reviewer(*, is_logged_in: bool, email: str | None) -> bool:
    """authorized_reviewer = authenticated_owner OR explicit_local_dev_reviewer.

    The local-dev branch never modifies auth/session state and never
    weakens the production path -- it only ever ADDS an additional way
    to pass this one boolean decision, gated by both an explicit env
    flag and an independent local-runtime check (see
    `is_explicit_local_dev_reviewer`)."""
    return is_authenticated_owner(is_logged_in=is_logged_in, email=email) or is_explicit_local_dev_reviewer()


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
    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        st.selectbox("Állapot", options=_STATUS_OPTIONS, key=_FILTER_STATUS_KEY)
    with cols[1]:
        st.text_input(
            "Forrás kód (opcionális)", key=_FILTER_SOURCE_KEY, placeholder="pl. PG_AESOPS_FABLES_TOWNSEND"
        )
    with cols[2]:
        st.checkbox("Csak figyelmeztetéssel", key=_FILTER_WARNINGS_KEY)
    with cols[3]:
        st.number_input(
            "Limit", min_value=1, max_value=200, value=20, step=1, key=_FILTER_LIMIT_KEY
        )


def _load_queue(connection: sqlite3.Connection) -> list[IllustrationReviewItem]:
    status = st.session_state.get(_FILTER_STATUS_KEY) or "needs_review"
    source_code = (st.session_state.get(_FILTER_SOURCE_KEY) or "").strip() or None
    warnings_only = bool(st.session_state.get(_FILTER_WARNINGS_KEY))
    limit = int(st.session_state.get(_FILTER_LIMIT_KEY) or 20)
    return list_review_items(
        connection, status=status, source_code=source_code, warnings_only=warnings_only, limit=limit
    )


def _render_queue_list(items: list[IllustrationReviewItem]) -> None:
    if not items:
        st.caption("Nincs a szűrőknek megfelelő tétel.")
        return
    selected_id = st.session_state.get(_SELECTED_UNIT_KEY)
    for item in items:
        warn_marker = " ⚠️" if item.enrichment_warnings else ""
        marker = "▶ " if item.unit_id == selected_id else ""
        label = f"{marker}#{item.unit_id} · {item.title_hu or '(cím nélkül)'}{warn_marker} · {item.source_code}"
        if st.button(label, key=f"ill_review_pick_{item.unit_id}", use_container_width=True):
            st.session_state[_SELECTED_UNIT_KEY] = item.unit_id
            st.rerun()


def _render_original_column(item: IllustrationReviewItem) -> None:
    st.markdown("##### Eredeti")
    st.caption(
        f"{item.source_title} ({item.source_code}) · {item.tradition or '—'} · {item.license_status}"
    )
    st.markdown(f"**{item.title_original}**")
    st.text_area(
        "original_text",
        value=item.original_text or "",
        height=280,
        disabled=True,
        key=f"ill_review_original_text_{item.unit_id}",
        label_visibility="collapsed",
    )
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


def _render_lifecycle_actions(connection: sqlite3.Connection, item: IllustrationReviewItem) -> None:
    st.markdown("##### Állapot-műveletek")
    cols = st.columns(3)

    with cols[0]:
        if item.status == "needs_review":
            if st.button(
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
    _render_taxonomy_section(connection, item)

    st.divider()
    _render_lifecycle_actions(connection, item)


def render_illustration_review_panel() -> None:
    """Entry point called by `app.py` after the reviewer gate passes."""
    connection = _get_connection()

    render_page_intro(
        eyebrow="Belső eszköz",
        title="Illusztráció-review",
        body="Enrichment-pipeline kimenetek humán ellenőrzése, jóváhagyása és publikálása.",
    )

    _render_queue_filters()
    items = _load_queue(connection)

    render_info_panel(
        title=f"{len(items)} tétel a jelenlegi szűrőkkel",
        body="A lista nem keresőmotor -- csak a Phase 3G-A review queue szűrőit (állapot, forrás, figyelmeztetés, limit) alkalmazza.",
        tone="info",
    )

    _render_queue_list(items)

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
    "is_authenticated_owner",
    "is_authorized_reviewer",
    "is_explicit_local_dev_reviewer",
    "render_illustration_review_panel",
]
