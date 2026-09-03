""""Kommentárok" fül -- közvetlen, retrieval-only, forrásközpontú nézet a
Commentary Knowledge Base fölött (jelenleg Calvin + JFB + Matthew Henry,
de a UI semmit nem tételez fel a forrásszámról vagy -nevekről -- ld.
lentebb).

A kártyalista maga NEM generatív: minden sor szó szerint a helyi
``commentary.sqlite3``-ból származik (``CommentaryRepository``). A meglévő
``render_section_tab()`` "Generálás gomb -> egy hosszú AI-szöveg" mintáját
szándékosan NEM használja ez a modul -- a Commentary UI/workflow audit
(2026-09-03) explicit döntése szerint ez retrieval-only forrásnézet, nem
generált tartalom, és a passage-retrieval mindig exact/range-overlap marad
(nincs FTS/semantic fallback -- ld. ``CommentaryRepository.
sections_for_passage`` saját dokumentációját).

Egy kibontott szakaszon belül -- opcionálisan, explicit felhasználói
kattintásra -- elérhető egy "Magyar fordítás" / "Eredeti angol" nézetváltó
is (ld. ``_render_translation_view_toggle``, ``commentary_translation_
service``). Ez az EGYETLEN generatív AI-hívási pont ezen a fülön; a
fordítás mindig származtatott, cache-elt réteg a ``commentary_
translations.sqlite3``-ban, sosem módosítja vagy helyettesíti az itt
megjelenő eredeti angol szöveget, és az eredeti mindig egy kattintással
visszaérhető marad.

Forrásközpontú UI (2026-09-03 polish kör): a találatok NEM egyetlen
hosszú, section-szintű listában jelennek meg, hanem forrás (work/edition
"család") szerint csoportosítva -- ld. ``_source_family_key``,
``_group_results_by_family``. A csoportosítás KULCSA mindig a metaadatból
(``work_id`` névtér-előtag) származik, sosem egy adott könyv aktuális
contributorjából -- így a forrás-szűrő és a kártyacsoportok egy jövőbeli
negyedik korpusz importálásakor is módosítás nélkül megjelennek, saját
csoportjukban. A megjelenítendő NÉV egy kis, kurált táblázatból jön a már
ismert forrásokhoz (``_SOURCE_FAMILY_DISPLAY_NAMES_HU``), egyébként a
ténylegesen jelenlévő contributor-nevekből származtatva (1 név -> az a
név; több név -> "–"-tel összefűzve) -- sosem összeomlik egy ismeretlen
forrásnál. A könyv-szintű, bibliográfiailag pontos contributor attribúció
(pl. "David Brown" a JFB "Jamieson–Fausset–Brown" család alatt) minden
kártyán/szűrőn külön, kisebb részletként megmarad.
"""

from __future__ import annotations

from typing import Any, Callable, MutableMapping, Sequence

import streamlit as st

import commentary_translation_service
from commentary_compare import render_commentary_compare_section
from textus_kb import commentary_runtime
from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.repositories.commentary_repository import (
    CommentaryRepository,
    CommentarySectionResult,
    primary_contributor_name,
)
from ui_components import (
    action_row,
    render_context_summary,
    render_info_panel,
    render_status_badge,
    render_work_section,
    work_surface,
)

_RELATION_TIER_LABELS_HU: dict[str, str] = {
    "exact_passage": "pontos találat",
    "containing_section": "tágabb szakasz tartalmazza",
    "partial_overlap": "részleges átfedés",
    "broader_context": "tágabb kontextus",
}

_PASSAGE_RELATION_LABELS_HU: dict[str, str] = {
    "primary": "Fő kommentált hely",
    "parallel": "Párhuzamos evangéliumi hely",
}

_PASSAGE_RELATION_LEGEND_HU = (
    "ℹ️ „Fő kommentált hely”: a szakasz elsődlegesen erről a helyről szól. "
    "„Párhuzamos evangéliumi hely”: a szerző (pl. Kálvin evangélium-"
    "harmóniája) egy másik evangéliumi párhuzam-vers kommentárjaként "
    "tárgyalja ezt a helyet is — ez a kapcsolat TÍPUSA, nem fontossági "
    "sorrend."
)

_SOURCE_BADGE_TONES: tuple[str, ...] = ("info", "success", "warning", "neutral")

_STATUS_REASON_LABELS_HU: dict[str, str] = {
    "database_missing": "A Commentary adatbázis (commentary.sqlite3) még nincs legenerálva.",
    "database_unopenable": "A Commentary adatbázis nem nyitható meg.",
    "schema_incompatible": "A Commentary adatbázis sémája nem kompatibilis a jelenlegi verzióval.",
}

_BUILD_HINT = (
    "Build parancs: `python scripts/build_commentary_database.py "
    "--combined-fetch --qa` (vagy `--combined`, ha a nyers forrásfájlok "
    "már helyben vannak a `data/raw/` alatt)."
)

_CACHE_PASSAGE_KEY = "_commentary_ui_cached_passage"
_CACHE_RESULTS_KEY = "_commentary_ui_cached_results"
_FILTER_STATE_KEY = "_commentary_ui_source_filter"
_PREVIEW_MAX_CHARS = 220
_MAX_SECTIONS_PER_FAMILY = 6

# Curated display names for the currently-known source families (keyed by
# the metadata-derived family key, ld. _source_family_key) -- a plain
# presentation-layer lookup, same idiom as _RELATION_TIER_LABELS_HU above.
# NOT the grouping mechanism itself (that's pure work_id metadata, scales
# to any future family automatically) -- only the cosmetic label for the
# three sources this corpus happens to have today. Any family key NOT
# listed here still groups and displays correctly via
# _source_family_display_name's generic, data-derived fallback.
_SOURCE_FAMILY_DISPLAY_NAMES_HU: dict[str, str] = {
    "ccel.calvin": "John Calvin",
    "ccel.jfb": "Jamieson–Fausset–Brown",
    "ccel.henry": "Matthew Henry",
}

# OSIS-style canonical book id (ld. textus_kb.books.BOOKS) -> standard
# Hungarian (RÚF-style) abbreviation. Display-only: never touches the
# canonical reference system itself (CanonicalReference / textus_kb.books
# stay completely unmodified) -- ld. _format_passage_hu.
_OSIS_TO_RUF_ABBR_HU: dict[str, str] = {
    "Gen": "1Móz", "Exod": "2Móz", "Lev": "3Móz", "Num": "4Móz", "Deut": "5Móz",
    "Josh": "Józs", "Judg": "Bír", "Ruth": "Ruth", "1Sam": "1Sám", "2Sam": "2Sám",
    "1Kgs": "1Kir", "2Kgs": "2Kir", "1Chr": "1Krón", "2Chr": "2Krón", "Ezra": "Ezsd",
    "Neh": "Neh", "Esth": "Eszt", "Job": "Jób", "Ps": "Zsolt", "Prov": "Péld",
    "Eccl": "Préd", "Song": "Én", "Isa": "Ézs", "Jer": "Jer", "Lam": "JSir",
    "Ezek": "Ez", "Dan": "Dán", "Hos": "Hós", "Joel": "Jóel", "Amos": "Ámós",
    "Obad": "Abd", "Jonah": "Jón", "Mic": "Mik", "Nah": "Náh", "Hab": "Hab",
    "Zeph": "Zof", "Hag": "Hag", "Zech": "Zak", "Mal": "Mal",
    "Matt": "Mt", "Mark": "Mk", "Luke": "Lk", "John": "Jn", "Acts": "ApCsel",
    "Rom": "Róm", "1Cor": "1Kor", "2Cor": "2Kor", "Gal": "Gal", "Eph": "Ef",
    "Phil": "Fil", "Col": "Kol", "1Thess": "1Thessz", "2Thess": "2Thessz",
    "1Tim": "1Tim", "2Tim": "2Tim", "Titus": "Tit", "Phlm": "Filem", "Heb": "Zsid",
    "Jas": "Jak", "1Pet": "1Pt", "2Pet": "2Pt", "1John": "1Jn", "2John": "2Jn",
    "3John": "3Jn", "Jude": "Júd", "Rev": "Jel",
}


def _primary_contributor(contributors: tuple[str, ...]) -> str:
    """UI-facing wrapper around ``commentary_repository.
    primary_contributor_name`` (shared with ``commentary_compare.py``, so
    the compare source-selection groups results the exact same way these
    cards do) — adds this module's own "unknown author" fallback label."""
    return primary_contributor_name(contributors) or "Ismeretlen szerző"


def _source_badge_tone(source_name: str) -> str:
    """Deterministic, generic tone assignment -- stable across reruns,
    scales to any number of distinct sources (cycles the palette)."""
    idx = sum(ord(ch) for ch in source_name) % len(_SOURCE_BADGE_TONES)
    return _SOURCE_BADGE_TONES[idx]


def _query_canonical(passage: str) -> str | None:
    try:
        return CanonicalReference.parse(passage).canonical_string()
    except CanonicalReferenceError:
        return None


def _format_passage_hu(canonical: str) -> str:
    """Human-friendly Hungarian passage display (e.g. ``Mt 5,1–12``) for a
    single canonical/OSIS-style reference string -- display-only, never
    changes what's stored/matched internally (still plain ``canonical``
    everywhere else: provenance, retrieval, compare). Falls back to the
    raw canonical string for any book id not in the abbreviation table,
    so nothing is ever hidden -- just less prettily formatted."""
    try:
        ref = CanonicalReference.parse(canonical)
    except CanonicalReferenceError:
        return canonical
    abbr = _OSIS_TO_RUF_ABBR_HU.get(ref.book_id)
    if not abbr:
        return canonical
    if ref.start_chapter == ref.end_chapter:
        if ref.start_verse == ref.end_verse:
            return f"{abbr} {ref.start_chapter},{ref.start_verse}"
        return f"{abbr} {ref.start_chapter},{ref.start_verse}–{ref.end_verse}"
    return (
        f"{abbr} {ref.start_chapter},{ref.start_verse}"
        f"–{ref.end_chapter},{ref.end_verse}"
    )


def _format_passage_list_hu(passages: Sequence[str]) -> str:
    formatted = [_format_passage_hu(p) for p in passages if p]
    return ", ".join(formatted) if formatted else "—"


def _source_family_key(work_id: str) -> str:
    """Metadata-derived source-family grouping key: the shared namespace
    prefix of ``work_id`` (e.g. ``ccel.calvin``, ``ccel.jfb``,
    ``ccel.henry`` for the real corpus -- ld. ``commentary_sqlite``
    import's ``<namespace>.<family>.work.<book>`` convention, verified
    identical across every book from one source and distinct across
    sources). Never a per-book contributor name -- a future 4th corpus
    following the same import convention groups itself automatically,
    with zero code changes here."""
    parts = (work_id or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else (work_id or "")


def _source_family_display_name(
    family_key: str, contributor_names: Sequence[str]
) -> str:
    """Primary, human-facing source name for a family (task requirement:
    "fő forrásnév", e.g. "Jamieson–Fausset–Brown" instead of whichever
    single book's contributor happens to be showing). Curated for the
    currently-known families; for anything else, derives a reasonable
    name straight from the real contributor(s) actually present -- never
    crashes or falls back to a raw internal key."""
    curated = _SOURCE_FAMILY_DISPLAY_NAMES_HU.get(family_key)
    if curated:
        return curated
    names = [n for n in contributor_names if n]
    if not names:
        return "Ismeretlen forrás"
    if len(names) == 1:
        return names[0]
    return " – ".join(names)


def _passage_relation_key(
    result: CommentarySectionResult, query_canonical: str | None
) -> str | None:
    """Which relation label applies to THIS query passage specifically --
    a section can carry both primary and parallel links, so this is
    resolved per query, never as a blanket "this section is primary"."""
    if query_canonical and query_canonical in result.primary_passages:
        return "primary"
    if query_canonical and query_canonical in result.parallel_passages:
        return "parallel"
    if result.primary_passages and not result.parallel_passages:
        return "primary"
    if result.parallel_passages and not result.primary_passages:
        return "parallel"
    return None


def interleave_by_source(
    results: list[CommentarySectionResult],
) -> list[CommentarySectionResult]:
    """Diversity pass on top of the repository's already tier/primary-
    sorted list.

    ``CommentaryRepository.sections_for_passage`` already returns results
    ordered by (relevance tier, span, primary-before-parallel, document
    order) -- that ordering is fully preserved here. Within each tier this
    additionally round-robins across distinct sources so one commentator
    with many overlapping same-tier hits (e.g. JFB's per-verse partial-
    overlap sections across a wide range query) never crowds the others
    out of view. Structurally mirrors ``context_builder.
    _interleave_commentary_by_work`` / ``_round_robin_by_work``'s two-level
    (tier, then per-tier round-robin) approach, applied here to display
    cards instead of AI evidence items -- a UI-local helper, not a reuse
    of that private, differently-shaped function.

    Runs at the book-level contributor granularity (unchanged) -- the
    family-level grouping used for display (ld. _group_results_by_family)
    is a separate, later pass over this already-diversified order.
    """
    tier_order: list[str] = []
    tiers: dict[str, list[CommentarySectionResult]] = {}
    for item in results:
        tier = item.relation_type
        if tier not in tiers:
            tiers[tier] = []
            tier_order.append(tier)
        tiers[tier].append(item)

    interleaved: list[CommentarySectionResult] = []
    for tier in tier_order:
        source_order: list[str] = []
        by_source: dict[str, list[CommentarySectionResult]] = {}
        for item in tiers[tier]:
            source = _primary_contributor(item.contributors)
            if source not in by_source:
                by_source[source] = []
                source_order.append(source)
            by_source[source].append(item)
        while any(by_source[s] for s in source_order):
            for source in source_order:
                bucket = by_source[source]
                if bucket:
                    interleaved.append(bucket.pop(0))
    return interleaved


def _group_book_sources_by_family(
    results: list[CommentarySectionResult],
) -> list[tuple[str, str, list[str]]]:
    """Ordered ``(family_key, family_display_name, book_contributor_
    names)`` groups for the source filter -- purely derived from
    ``results`` metadata (work_id namespace + contributors), never a
    hardcoded source list. Each family may list more than one book-level
    contributor name when the current passage spans multiple books from
    the same source family."""
    family_order: list[str] = []
    family_names: dict[str, list[str]] = {}
    for r in results:
        key = _source_family_key(r.work_id)
        name = _primary_contributor(r.contributors)
        bucket = family_names.setdefault(key, [])
        if key not in family_order:
            family_order.append(key)
        if name not in bucket:
            bucket.append(name)
    return [
        (key, _source_family_display_name(key, family_names[key]), family_names[key])
        for key in family_order
    ]


def _group_results_by_family(
    results: list[CommentarySectionResult],
) -> list[tuple[str, str, list[CommentarySectionResult]]]:
    """Ordered ``(family_key, family_display_name, sections)`` groups for
    the card list -- first-appearance order preserved from the already
    relevance-sorted/interleaved input, never re-sorted by family name."""
    family_order: list[str] = []
    buckets: dict[str, list[CommentarySectionResult]] = {}
    for r in results:
        key = _source_family_key(r.work_id)
        if key not in buckets:
            buckets[key] = []
            family_order.append(key)
        buckets[key].append(r)
    groups: list[tuple[str, str, list[CommentarySectionResult]]] = []
    for key in family_order:
        items = buckets[key]
        names: list[str] = []
        for item in items:
            name = _primary_contributor(item.contributors)
            if name not in names:
                names.append(name)
        groups.append((key, _source_family_display_name(key, names), items))
    return groups


def _get_repository() -> CommentaryRepository:
    """Single, monkeypatchable seam for DB access -- production always uses
    the default (production) path; tests point this at an isolated store."""
    return CommentaryRepository()


def _translation_database_path() -> str | None:
    """Single, monkeypatchable seam mirroring ``_get_repository`` for the
    (separate, derived) translation cache -- ``None`` means "use
    ``commentary_translation_service``'s own default production path";
    tests point this at an isolated store so they never touch the real
    ``data/generated/commentary_translations.sqlite3``."""
    return None


def _get_status() -> commentary_runtime.CommentaryRuntimeStatus:
    """Single, monkeypatchable seam mirroring ``_get_repository`` for the
    runtime availability check."""
    return commentary_runtime.get_status()


def _fetch_results(passage: str) -> list[CommentarySectionResult]:
    repo = _get_repository()
    return interleave_by_source(repo.sections_for_passage(passage))


def _sources_present(results: list[CommentarySectionResult]) -> list[str]:
    """Distinct BOOK-LEVEL source (contributor) names in first-seen order
    -- purely data-derived, never a hardcoded corpus list. Unchanged
    granularity (still book-level, not family-level): this is exactly
    the identity ``commentary_compare.py`` groups evidence by, so the
    compare integration's ``enabled_sources`` contract stays untouched
    by the family-grouped UI presentation above it."""
    seen: set[str] = set()
    ordered: list[str] = []
    for r in results:
        name = _primary_contributor(r.contributors)
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _apply_source_filter(
    results: list[CommentarySectionResult], enabled_sources: set[str]
) -> list[CommentarySectionResult]:
    return [r for r in results if _primary_contributor(r.contributors) in enabled_sources]


def _ensure_results(
    passage: str,
    *,
    session: MutableMapping[str, Any] | None = None,
    force: bool = False,
) -> list[CommentarySectionResult]:
    """Per-passage cached retrieval. ``session`` defaults to the real
    ``st.session_state`` in production; tests may inject a plain dict to
    exercise the caching logic without a live Streamlit context."""
    store: MutableMapping[str, Any] = st.session_state if session is None else session
    if (
        force
        or store.get(_CACHE_PASSAGE_KEY) != passage
        or _CACHE_RESULTS_KEY not in store
    ):
        store[_CACHE_RESULTS_KEY] = _fetch_results(passage)
        store[_CACHE_PASSAGE_KEY] = passage
    return store[_CACHE_RESULTS_KEY]


def _render_missing_db(status: commentary_runtime.CommentaryRuntimeStatus) -> None:
    reason = _STATUS_REASON_LABELS_HU.get(status.reason, status.reason)
    render_info_panel(
        title="Commentary adatbázis nem elérhető",
        body=f"{reason} {_BUILD_HINT}",
        tone="warning",
    )


def _render_no_passage() -> None:
    render_info_panel(
        title="Nincs kiválasztva igeszakasz",
        body="Add meg az igeszakaszt az „Igehely” fülön, mielőtt a kommentárokat böngészed.",
        tone="neutral",
    )


def _render_no_match(passage: str) -> None:
    render_info_panel(
        title="Nincs kommentár-találat",
        body=(
            f"A jelenleg elérhető kommentárforrások egyike sem tartalmaz közvetlen "
            f"kommentárt erre a helyre: {passage}. A rendszer nem tér át szövegkeresésre "
            "vagy AI-pótlásra — csak a valódi, hozzárendelt kommentárszakaszokat mutatja."
        ),
        tone="neutral",
    )


def _render_all_sources_disabled() -> None:
    render_info_panel(
        title="Minden forrás ki van kapcsolva",
        body="Kapcsolj vissza legalább egy forrást a szűrőben a találatok megtekintéséhez.",
        tone="neutral",
    )


def _render_source_filter(results: list[CommentarySectionResult]) -> set[str]:
    """Renders ONE checkbox per source FAMILY (task item 2 -- not per
    book-level contributor), labeled with the family's primary display
    name; the concrete book-level contributor(s) actually present for the
    current passage show as a small caption underneath, so bibliographic
    attribution is never lost. Returns the set of enabled BOOK-LEVEL
    contributor names (unchanged contract from before this round --
    ``commentary_compare.py`` groups evidence by exactly this identity,
    so the compare integration keeps working without any change there)."""
    groups = _group_book_sources_by_family(results)
    filter_state: dict[str, bool] = st.session_state.setdefault(_FILTER_STATE_KEY, {})
    if groups:
        cols = st.columns(len(groups))
        for col, (family_key, family_display, book_names) in zip(cols, groups):
            with col:
                filter_state[family_key] = st.checkbox(
                    family_display,
                    value=filter_state.get(family_key, True),
                    key=f"commentary_source_filter_{family_key}",
                )
                st.caption(", ".join(book_names))
    enabled_families = {key for key, enabled in filter_state.items() if enabled}
    enabled_book_names: set[str] = set()
    for family_key, _display, book_names in groups:
        if family_key in enabled_families:
            enabled_book_names.update(book_names)
    return enabled_book_names


def _render_compact_section(
    result: CommentarySectionResult,
    *,
    query_canonical: str | None,
    generate_fn: Callable[..., str] | None,
    resolve_model_fn: Callable[[str], str] | None,
) -> None:
    """One compact row within a source-family group: passage + short
    preview + relation + expand -- never repeats a full-size author/work
    heading per section (that's now the family header above); the exact
    book-level work/contributor still shows, just as a small caption."""
    tier_label = _RELATION_TIER_LABELS_HU.get(result.relation_type, result.relation_type)
    relation_key = _passage_relation_key(result, query_canonical)
    relation_label = _PASSAGE_RELATION_LABELS_HU.get(relation_key or "", "")
    contributor = _primary_contributor(result.contributors)

    passages = result.primary_passages or result.canonical_passages
    passage_display = _format_passage_list_hu(passages)

    with st.container(border=True):
        st.markdown(f"**{passage_display}**")
        caption_bits = [f"{result.work_title} — {contributor}", tier_label]
        if relation_label:
            caption_bits.append(relation_label)
        st.caption(" · ".join(caption_bits))

        repo = _get_repository()
        preview = repo.chunk_previews([result.section_id], max_chars=_PREVIEW_MAX_CHARS).get(
            result.section_id, ""
        )
        if preview:
            st.caption(preview)

        with st.expander("Teljes szöveg és forrásadatok"):
            _render_detail(result, generate_fn=generate_fn, resolve_model_fn=resolve_model_fn)


_TRANSLATION_VIEW_HUNGARIAN = "Magyar fordítás"
_TRANSLATION_VIEW_ORIGINAL = "Eredeti angol"
_TRANSLATION_VIEW_KEY_PREFIX = "commentary_translation_view_"


def _render_translation_view_toggle(
    section_id: str, *, has_text: bool, has_cached_translation: bool
) -> str:
    """"Magyar fordítás" / "Eredeti angol" nézetváltó -- csak akkor
    jelenik meg, ha a szakaszhoz egyáltalán tartozik önálló szöveg
    (szerkezeti, üres szakaszoknál nincs mit fordítani/mutatni két
    nézetben). Ha már van cache-elt magyar fordítás, a magyar nézet a
    kényelmes alapértelmezett; egyébként "Eredeti angol" indul -- de
    mindkét irányba egy kattintás, az eredeti soha nem tűnik el."""
    if not has_text:
        return _TRANSLATION_VIEW_ORIGINAL
    options = (_TRANSLATION_VIEW_HUNGARIAN, _TRANSLATION_VIEW_ORIGINAL)
    key = f"{_TRANSLATION_VIEW_KEY_PREFIX}{section_id}"
    if key not in st.session_state:
        st.session_state[key] = (
            _TRANSLATION_VIEW_HUNGARIAN if has_cached_translation else _TRANSLATION_VIEW_ORIGINAL
        )
    return st.radio(
        "Nézet",
        options=options,
        key=key,
        horizontal=True,
        label_visibility="collapsed",
    )


def _render_translation_panel(
    card: CommentarySectionResult,
    *,
    generate_fn: Callable[..., str] | None,
    resolve_model_fn: Callable[[str], str] | None,
) -> None:
    """Cache-hit -> azonnal megjelenik, új modellhívás nélkül. Cache-miss
    -> explicit "Magyar fordítás készítése" gomb (SOHA nem generál
    automatikusan); a teljes kanonikus szakasz fordul (nem preview). Hiba/
    elérhetetlen provider esetén csak ez a panel jelez -- az "Eredeti
    angol" nézet és a fenti kártyalista ettől függetlenül változatlanul
    működik."""
    repo = _get_repository()
    db_path = _translation_database_path()
    outcome = commentary_translation_service.get_translation(
        card.section_id, repository=repo, database_path=db_path
    )
    if outcome.status == "cached":
        _render_translated_text(outcome, card)
        return
    if outcome.status != "missing":
        st.caption("A fordítás jelenleg nem érhető el ehhez a szakaszhoz.")
        return

    if st.button(
        "Magyar fordítás készítése",
        key=f"commentary_translate_btn_{card.section_id}",
        disabled=generate_fn is None,
    ):
        provider_model = (
            resolve_model_fn(commentary_translation_service.TRANSLATION_TAB_LABEL)
            if resolve_model_fn is not None
            else ""
        )
        with st.spinner("Magyar fordítás készítése…"):
            result = commentary_translation_service.get_or_create_translation(
                card.section_id,
                generate_fn=generate_fn,
                provider_model=provider_model,
                repository=repo,
                database_path=db_path,
            )
        if result.status in ("cached", "generated"):
            _render_translated_text(result, card)
        else:
            st.warning(result.message or "A fordítás jelenleg nem készíthető el.")


def _render_translated_text(
    outcome: "commentary_translation_service.TranslationOutcome",
    card: CommentarySectionResult,
) -> None:
    st.caption("AI által készített magyar fordítás")
    st.write(outcome.text)
    st.caption(
        "Az eredeti angol szöveg gépi fordítása. Az eredeti szöveg az "
        "„Eredeti angol” nézetben egy kattintással elérhető."
    )


def _has_cached_translation(section_id: str) -> bool:
    """Cache-only check (no provider call) used purely to decide the
    toggle's default view -- a real cache-hit lookup happens again inside
    _render_translation_panel regardless of this default."""
    outcome = commentary_translation_service.get_translation(
        section_id, repository=_get_repository(), database_path=_translation_database_path()
    )
    return outcome.status == "cached"


def _render_detail(
    card: CommentarySectionResult,
    *,
    generate_fn: Callable[..., str] | None = None,
    resolve_model_fn: Callable[[str], str] | None = None,
) -> None:
    repo = _get_repository()
    detail = repo.section_detail(card.section_id)
    if detail is None:
        st.warning("A szakasz részletei jelenleg nem érhetők el.")
        return

    if detail.parent_chain:
        breadcrumb = " › ".join((heading or sid) for sid, heading in detail.parent_chain)
        current = detail.heading or detail.section_type
        st.caption(f"Szerkezet: {breadcrumb} › {current}")

    passages = detail.primary_passages or detail.canonical_passages
    passage_display = _format_passage_list_hu(passages)
    render_context_summary(
        [
            ("Szerző", ", ".join(detail.contributors) or "—"),
            ("Mű", card.work_title),
            ("Igehely", passage_display),
        ]
    )
    if detail.parallel_passages:
        st.caption(
            f"Párhuzamos evangéliumi hely: {_format_passage_list_hu(detail.parallel_passages)}"
        )

    has_translation = bool(detail.chunks) and _has_cached_translation(card.section_id)
    view = _render_translation_view_toggle(
        card.section_id, has_text=bool(detail.chunks), has_cached_translation=has_translation
    )
    if view == _TRANSLATION_VIEW_HUNGARIAN and detail.chunks:
        _render_translation_panel(card, generate_fn=generate_fn, resolve_model_fn=resolve_model_fn)
    else:
        for chunk in detail.chunks:
            st.write(chunk.plain_text)
        if not detail.chunks:
            st.caption("Ehhez a szakaszhoz nem tartozik önálló szöveg (csak szerkezeti elem).")

    # Detailed, technical provenance -- kept fully available but demoted
    # below the reading surface (task item 7): never lost, just not
    # competing with the actual commentary text for attention.
    source_locator = detail.chunks[0].source_locator if detail.chunks else ""
    st.markdown("**Forrásadatok**")
    render_context_summary(
        [
            ("Kiadás (edition)", detail.edition_id),
            ("Forrás locator", source_locator or "—"),
            ("Upstream forrás", card.source_url or "—"),
            ("Azonosító", card.external_id or "—"),
            (
                "Jogi státusz",
                (card.rights_status or "—") + (f" ({card.license})" if card.license else ""),
            ),
        ]
    )
    if card.rights_note:
        st.caption(card.rights_note)


def render_commentary_panel(
    *,
    generate_fn: Callable[..., str] | None = None,
    resolve_model_fn: Callable[[str], str] | None = None,
) -> None:
    """Renders the "Kommentárok" tab's entire content.

    ``generate_fn`` powers two independent, explicit-click-only generative
    actions: the "Kommentárok összehasonlítása" section below the cards,
    and the per-section "Magyar fordítás készítése" button inside an
    expanded section's "Magyar fordítás" / "Eredeti angol" toggle (ld.
    ``_render_translation_panel``). The retrieval-only card list itself
    still makes zero LLM calls on its own -- and, like ``generate_fn``,
    never names a concrete provider in this module's own source.
    ``resolve_model_fn`` (app.py's own tab-based model-routing lookup) is
    optional, translation-only provenance metadata -- when omitted,
    translations are still generated and cached normally, just without a
    recorded provider/model name.
    """
    render_work_section(
        title="Kommentárok",
        body=(
            "Klasszikus kommentárok az aktuális igeszakaszhoz -- forrásonként "
            "csoportosítva, közvetlenül a forrásból, AI-összefoglalás nélkül. "
            "Minden szakasz szó szerinti idézet a kiválasztott műből."
        ),
        context="Textusműhely",
    )

    status = _get_status()
    if not status.available:
        with work_surface("commentary_unavailable"):
            _render_missing_db(status)
        return

    passage = (st.session_state.get("last_igehely") or "").strip()
    if not passage:
        with work_surface("commentary_no_passage"):
            _render_no_passage()
        return

    with work_surface("commentary_results"):
        with action_row("commentary_refresh"):
            if st.button("Frissítés", key="commentary_refresh_btn"):
                _ensure_results(passage, force=True)
                st.rerun()

        results = _ensure_results(passage)
        if not results:
            _render_no_match(passage)
            return

        query_canonical = _query_canonical(passage)
        enabled_sources = _render_source_filter(results)
        visible = _apply_source_filter(results, enabled_sources)
        if not visible:
            _render_all_sources_disabled()
            return

        if any(r.parallel_passages for r in visible):
            st.caption(_PASSAGE_RELATION_LEGEND_HU)

        for _family_key, family_display, items in _group_results_by_family(visible):
            shown, hidden = items[:_MAX_SECTIONS_PER_FAMILY], items[_MAX_SECTIONS_PER_FAMILY:]
            st.markdown(f"#### {family_display}")
            for result in shown:
                _render_compact_section(
                    result,
                    query_canonical=query_canonical,
                    generate_fn=generate_fn,
                    resolve_model_fn=resolve_model_fn,
                )
            if hidden:
                st.caption(
                    f"+ {len(hidden)} további, alacsonyabb relevanciájú "
                    f"{family_display} találat nem jelenik meg."
                )

        # Only enabled-AND-currently-shown sources count -- filter_state can
        # carry stale entries from a previous passage's checkboxes that no
        # longer render this render (ld. _render_source_filter), so this
        # must be intersected with the sources actually present now, not
        # used as the raw filter_state dict.
        ordered_enabled_sources = [s for s in _sources_present(results) if s in enabled_sources]

    with work_surface("commentary_compare_section"):
        render_commentary_compare_section(
            passage=passage,
            passage_display=passage,
            enabled_sources=ordered_enabled_sources,
            generate_fn=generate_fn,
        )


__all__ = ["render_commentary_panel", "interleave_by_source"]

# NOTE: the underscored helpers below (`_get_repository`, `_get_status`,
# `_fetch_results`, `_ensure_results`, `_sources_present`,
# `_apply_source_filter`, `_primary_contributor`, `_passage_relation_key`,
# `_query_canonical`, `_source_family_key`, `_source_family_display_name`,
# `_group_results_by_family`, `_group_book_sources_by_family`,
# `_format_passage_hu`, `_format_passage_list_hu`) are intentionally still
# module-private (no public API contract) but are imported directly by
# tests/test_commentary_ui.py -- consistent with this repo's existing
# pattern of testing Streamlit UI modules via their pure helper functions
# rather than full rendering.
