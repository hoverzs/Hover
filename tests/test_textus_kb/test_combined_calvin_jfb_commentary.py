"""Combined Calvin + JFB commentary store: the core multi-source proof.

Builds one commentary.sqlite3 containing the full Calvin corpus (45
files, 23 works) AND the full JFB corpus (1 file, 66 works) together,
and proves the Commentary Knowledge Base is genuinely source-independent
architecture: no ID collisions, correct per-source provenance, both
sources retrievable for a shared passage, work_id filtering isolates
each source, deterministic build, and — critically — that a single
commentary can no longer flood the PROFILE_COMMENTARY token budget now
that a second source exists for the same passage (the whole point of
this round).

Gated on both full corpora being present locally; no network access at
test time.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_COMMENTARY, PROFILE_EXEGESIS
from textus_kb.evidence import (
    RELATION_DIRECT_PASSAGE,
    RELATION_LEXICAL_HIGHLIGHT,
    EvidenceItem,
    EvidencePacket,
)
from textus_kb.importers.calvin_source_fetch import load_source_manifest as load_calvin_manifest
from textus_kb.importers.combined_commentary import import_combined_calvin_jfb_commentary
from textus_kb.importers.jfb_source_fetch import load_source_manifest as load_jfb_manifest
from textus_kb.qa.commentary_corpus_qa import generate_commentary_corpus_qa
from textus_kb.repositories.commentary_repository import CommentaryRepository
from textus_kb.retrieval import retrieve_commentary_evidence

_CALVIN_ENTRIES = load_calvin_manifest()
_JFB_MANIFEST = load_jfb_manifest()
_ALL_PRESENT = all(entry.local_path.is_file() for entry in _CALVIN_ENTRIES) and (
    _JFB_MANIFEST.source.local_path.is_file()
)

pytestmark = pytest.mark.skipif(
    not _ALL_PRESENT,
    reason=(
        "Full Calvin (45 files) and/or JFB (1 file) raw sources not present locally. "
        "See test_calvin_commentary_full_corpus.py / test_jfb_commentary_full_corpus.py "
        "for fetch instructions."
    ),
)


@pytest.fixture(scope="module")
def combined_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("combined_calvin_jfb") / "commentary.sqlite3"
    import_combined_calvin_jfb_commentary(
        calvin_entries=_CALVIN_ENTRIES,
        jfb_xml_path=_JFB_MANIFEST.source.local_path,
        jfb_book_entries=list(_JFB_MANIFEST.books),
        database_path=database,
        imported_at="2026-01-01T00:00:00Z",
    )
    return database


@pytest.fixture(scope="module")
def combined_repo(combined_db: Path) -> CommentaryRepository:
    return CommentaryRepository(combined_db)


# --- Architectural proof: no collisions, correct provenance -----------


def test_combined_scale_matches_sum_of_both_sources(
    combined_repo: CommentaryRepository,
) -> None:
    status = combined_repo.store_status()
    assert status.available is True
    assert status.work_count == 23 + 66
    assert status.edition_count == 45 + 66
    assert status.source_file_count == 45 + 66
    assert status.import_batch_count == 45 + 66
    assert status.contributor_count == 9 + 3
    # 2026-09-04: Calvin's own numbers grew twice in one day, from two
    # separate structural importer fixes:
    #   1. 14643/11785/14153 -> 18989/14673/18397 -- combined multi-book
    #      volumes (e.g. the Catholic Epistles: James/1-2Peter/1John/Jude)
    #      nest one extra div level between a chapter and its actual
    #      scripture-range content versus single-book volumes, and the
    #      importer only walked direct children, silently importing real
    #      chapters as bare "CHAPTER N" heading stubs.
    #   2. 18989/14673/18397 -> 19358/15372/18740 -- (a) a scripCom marker
    #      `<p>` with a harmless empty sibling element (e.g. CCEL's own
    #      `<a shape="rect" xml:link="simple" />` navigation placeholder)
    #      was rejected as "not a marker", silently dropping the real
    #      commentary body that followed it (171 cases corpus-wide); (b) a
    #      table-less wrapper div could itself be nested inside ANOTHER
    #      table-less wrapper (a real 3-level div2>div3>div4 pattern,
    #      confirmed unique to calcom05/"Harmony of the Law, Volume 3"),
    #      one level deeper than the first fix's single-level unwrap
    #      followed -- generalized into an unbounded recursive traversal
    #      that only ever follows genuine ThML "divN" structural tags
    #      (never a bare `<div class="Commentary">` content wrapper,
    #      which shares the "div" prefix but is not a nesting level).
    # See textus_kb.importers.calvin_commentary_thml
    # ._process_range_group_divs and ._as_scripcom_marker.
    assert status.section_count == 19358 + 32394
    assert status.chunk_count == 15372 + 21071
    assert status.passage_link_count == 18740 + 31097


def test_combined_qa_is_clean(combined_db: Path) -> None:
    report = generate_commentary_corpus_qa(combined_db)
    assert report.available is True
    assert report.orphan_sections == []
    assert report.invalid_references == []
    assert report.duplicate_section_ids == []
    assert report.duplicate_chunk_ids == []
    assert report.duplicate_passage_links == []
    assert report.cross_edition_hierarchy_issues == []
    assert report.hierarchy_cycle_sections == []
    assert report.invalid_relation_types == []
    assert report.warnings == []
    # Calvin's 6 documented known-unmapped exceptions must still surface
    # correctly through the combined store (2026-09-04: +1, calcom30's
    # "Malichi 3:15" — a plain-text, misspelled-book-name table caption
    # with no scripRef, newly surfaced once its wrapping chapter div was
    # correctly unwrapped instead of being silently skipped whole).
    assert len(report.known_unmapped) == 6
    # Calvin's 449 parallel Harmony links (2026-09-04: 354 -> 436 -> 449,
    # across both structural fixes above, as previously-invisible content
    # contributes some parallel links of its own); JFB contributes none.
    assert report.parallel_passage_link_count == 449
    assert len(report.works) == 89


def test_combined_build_is_deterministic(tmp_path: Path) -> None:
    second = tmp_path / "second.sqlite3"
    result_a = import_combined_calvin_jfb_commentary(
        calvin_entries=_CALVIN_ENTRIES,
        jfb_xml_path=_JFB_MANIFEST.source.local_path,
        jfb_book_entries=list(_JFB_MANIFEST.books),
        database_path=tmp_path / "first.sqlite3",
        imported_at="2026-01-01T00:00:00Z",
    )
    result_b = import_combined_calvin_jfb_commentary(
        calvin_entries=_CALVIN_ENTRIES,
        jfb_xml_path=_JFB_MANIFEST.source.local_path,
        jfb_book_entries=list(_JFB_MANIFEST.books),
        database_path=second,
        imported_at="2099-06-15T12:00:00Z",
    )
    assert result_a.content_hash == result_b.content_hash


def test_combined_refuses_production_database_path() -> None:
    from textus_kb.importers.combined_commentary import CombinedCommentaryImportError
    from textus_kb.importers.commentary_sqlite import DEFAULT_DATABASE_PATH

    with pytest.raises(CombinedCommentaryImportError, match="production"):
        import_combined_calvin_jfb_commentary(
            calvin_entries=_CALVIN_ENTRIES,
            jfb_xml_path=_JFB_MANIFEST.source.local_path,
            jfb_book_entries=list(_JFB_MANIFEST.books),
            database_path=DEFAULT_DATABASE_PATH,
        )


# --- Retrieval: both sources for a shared passage, one source where Calvin is silent --


@pytest.mark.parametrize(
    ("label", "reference"),
    [
        ("Genesis", "Genesis.1.1"),
        ("Psalms", "Psalms.23.1"),
        ("Isaiah", "Isaiah.53.5"),
        ("Gospel - Matthew", "Matthew.1.1"),
        ("Romans", "Romans.1.1"),
        ("General epistle - James", "James.1.1"),
    ],
)
def test_both_sources_retrievable_where_both_exist(
    combined_repo: CommentaryRepository, label: str, reference: str
) -> None:
    items = retrieve_commentary_evidence(reference, repository=combined_repo)
    work_ids = {item.metadata.get("work_id") for item in items}
    calvin_hit = any(str(w).startswith("ccel.calvin") for w in work_ids)
    jfb_hit = any(str(w).startswith("ccel.jfb") for w in work_ids)
    assert calvin_hit, f"{label}: expected a Calvin hit for {reference}"
    assert jfb_hit, f"{label}: expected a JFB hit for {reference}"
    for item in items:
        meta = item.metadata
        assert meta.get("contributors")
        assert meta.get("work_id")
        assert meta.get("edition_id")
        assert item.passage


def test_revelation_jfb_only_calvin_never_fabricated(
    combined_repo: CommentaryRepository,
) -> None:
    """Calvin never wrote a commentary on Revelation; JFB covers the whole
    Bible. The combined store must surface JFB alone here, never a
    fabricated Calvin hit."""
    items = retrieve_commentary_evidence("Revelation.1.1", repository=combined_repo)
    assert items
    work_ids = {item.metadata.get("work_id") for item in items}
    assert all(str(w).startswith("ccel.jfb") for w in work_ids)
    assert not any(str(w).startswith("ccel.calvin") for w in work_ids)


# --- work_id filtering isolates each source -----------------------------


def test_work_id_filter_isolates_calvin_from_jfb(
    combined_repo: CommentaryRepository,
) -> None:
    calvin_hits = combined_repo.sections_for_passage(
        "Genesis.1.1", work_id="ccel.calvin.work.genesis"
    )
    jfb_hits = combined_repo.sections_for_passage(
        "Genesis.1.1", work_id="ccel.jfb.work.genesis"
    )
    assert calvin_hits and jfb_hits
    assert all("Calvin" in h.work_title or "Genesis" in h.work_title for h in calvin_hits)
    assert all(h.work_title.startswith("Commentary Critical") for h in jfb_hits)
    assert all("Jamieson" in c or "Critical" in h.work_title for h in jfb_hits for c in h.contributors)


# --- PROFILE_COMMENTARY context selection: source diversity ------------


def _packet(passage_canonical: str, passage_display: str, **kwargs) -> EvidencePacket:
    return EvidencePacket(
        passage_canonical=passage_canonical,
        passage_display=passage_display,
        build_id="test",
        manifest_version="test",
        **kwargs,
    )


def test_commentary_context_balances_both_sources_for_range_query(
    combined_db: Path,
) -> None:
    """The core proof this round exists to make: a range query with many
    same-tier hits per source must not let one commentary (whichever
    happens to sort first in document order) consume the whole
    PROFILE_COMMENTARY budget before the other source is even considered."""
    ctx = build_context_from_evidence(
        _packet("Romans.1.1-7", "Romans 1:1-7"),
        PROFILE_COMMENTARY,
        commentary_database_path=combined_db,
    )
    work_titles = [
        item.metadata.get("work_title")
        for section in ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    ]
    counts = Counter(work_titles)
    assert len(counts) >= 2, f"expected both Calvin and JFB represented, got {counts}"
    calvin_count = sum(v for k, v in counts.items() if not k.startswith("Commentary Critical"))
    jfb_count = sum(v for k, v in counts.items() if k.startswith("Commentary Critical"))
    assert calvin_count > 0 and jfb_count > 0
    assert ctx.estimated_tokens <= ctx.max_tokens


def test_commentary_context_selection_deterministic_with_two_sources(
    combined_db: Path,
) -> None:
    packet = _packet("Romans.1.1-7", "Romans 1:1-7")
    runs = [
        [
            item.evidence_id
            for section in build_context_from_evidence(
                packet, PROFILE_COMMENTARY, commentary_database_path=combined_db
            ).sections
            for item in section.items
        ]
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


def test_commentary_primary_still_precedes_parallel_with_jfb_present(
    combined_db: Path,
) -> None:
    """The Harmony section's primary/parallel labeling (proven in the
    prior round) must survive unchanged now that JFB also has candidates
    for the same Matthew/Luke passages."""
    matthew_ctx = build_context_from_evidence(
        _packet("Matthew.1.1-17", "Matthew 1:1-17"),
        PROFILE_COMMENTARY,
        commentary_database_path=combined_db,
    )
    luke_ctx = build_context_from_evidence(
        _packet("Luke.3.23-38", "Luke 3:23-38"),
        PROFILE_COMMENTARY,
        commentary_database_path=combined_db,
    )
    matthew_items = {
        item.metadata.get("section_id"): item
        for section in matthew_ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    }
    luke_items = {
        item.metadata.get("section_id"): item
        for section in luke_ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    }
    shared = set(matthew_items) & set(luke_items)
    assert shared, "the shared Calvin Harmony section must survive selection on both sides"
    shared_id = next(iter(shared))
    assert "Matt.1.1-17" in matthew_items[shared_id].metadata.get("primary_passages", [])
    assert "Luke.3.23-38" in luke_items[shared_id].metadata.get("parallel_passages", [])


def test_direct_linguistic_evidence_priority_unaffected_by_two_sources(
    combined_db: Path,
) -> None:
    packet = _packet(
        "Romans.1.1",
        "Romans 1:1",
        linguistic_evidence={
            "lexical_highlights": [
                {"strong_id": "G1401", "lemma": "doulos", "gloss_en": "servant"}
            ],
        },
        evidence_items=[
            EvidenceItem(
                evidence_id="EV-DIRECT-1",
                source_id="stepbible_tagnt",
                source_type="sqlite",
                language="grc",
                relation_type=RELATION_DIRECT_PASSAGE,
                passage="Romans.1.1",
                content="direct passage evidence",
            ),
            EvidenceItem(
                evidence_id="EV-LEX-G1401",
                source_id="stepbible_tbesg",
                source_type="sqlite",
                language="grc",
                relation_type=RELATION_LEXICAL_HIGHLIGHT,
                passage="Romans.1.1",
                content="doulos lexicon entry",
                metadata={"strong_id": "G1401"},
            ),
        ],
    )
    ctx = build_context_from_evidence(
        packet, PROFILE_COMMENTARY, commentary_database_path=combined_db
    )
    scores_by_id = {
        item.evidence_id: item.relevance_score
        for section in ctx.sections
        for item in section.items
    }
    commentary_scores = [
        score for eid, score in scores_by_id.items() if eid.startswith("EV-COMM-")
    ]
    assert commentary_scores
    assert scores_by_id["EV-DIRECT-1"] > max(commentary_scores)
    assert scores_by_id["EV-DIRECT-1"] > scores_by_id["EV-LEX-G1401"]


def test_exegesis_profile_includes_bounded_commentary_from_combined_store(
    combined_db: Path,
) -> None:
    """2026-09-03 Commentary grounding round: PROFILE_EXEGESIS now
    intentionally includes Commentary as a bounded, supplementary
    interpretive-witness layer (ld. tests/test_textus_kb/test_commentary_
    grounded_study_modules.py, which uses real, full evidence packets and
    proves Commentary never displaces direct linguistic/exegetical
    evidence there) — this test's ``_packet()`` helper builds a minimal
    synthetic EvidencePacket with no linguistic evidence of its own, so it
    only proves Commentary appears without exceeding the profile's own
    token budget against a real, populated combined store."""
    ctx = build_context_from_evidence(
        _packet("Romans.1.1", "Romans 1:1"),
        PROFILE_EXEGESIS,
        commentary_database_path=combined_db,
    )
    assert ctx.profile == PROFILE_EXEGESIS
    assert ctx.estimated_tokens <= ctx.max_tokens
    section_types = {section.type for section in ctx.sections}
    assert "commentary" in section_types
