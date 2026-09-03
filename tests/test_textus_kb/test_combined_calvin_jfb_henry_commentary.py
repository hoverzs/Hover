"""Combined Calvin + JFB + Henry commentary store: the 3-source proof.

Builds one commentary.sqlite3 containing all three full corpora together
and proves the Commentary Knowledge Base architecture generalizes cleanly
from 2 sources (the prior round's proof, in
``test_combined_calvin_jfb_commentary.py``) to 3: no ID collisions,
correct per-source provenance, all three sources retrievable for a shared
passage, work_id filtering isolates each source, deterministic build, and
that the tier-aware work-diversity interleave (fixed this round in
``context_builder.py``) keeps exact/primary hits from any source ahead of
lower-tier hits from another source while still surfacing multiple works.

Gated on all three full corpora being present locally; no network access
at test time.
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
from textus_kb.importers.combined_commentary import import_combined_commentary_corpus
from textus_kb.importers.henry_source_fetch import load_source_manifest as load_henry_manifest
from textus_kb.importers.jfb_source_fetch import load_source_manifest as load_jfb_manifest
from textus_kb.qa.commentary_corpus_qa import generate_commentary_corpus_qa
from textus_kb.repositories.commentary_repository import CommentaryRepository
from textus_kb.retrieval import retrieve_commentary_evidence

_CALVIN_ENTRIES = load_calvin_manifest()
_JFB_MANIFEST = load_jfb_manifest()
_HENRY_MANIFEST = load_henry_manifest()
_ALL_PRESENT = (
    all(entry.local_path.is_file() for entry in _CALVIN_ENTRIES)
    and _JFB_MANIFEST.source.local_path.is_file()
    and all(v.local_path.is_file() for v in _HENRY_MANIFEST.volumes)
)

pytestmark = pytest.mark.skipif(
    not _ALL_PRESENT,
    reason=(
        "Full Calvin (45 files), JFB (1 file), and/or Henry (6 files) raw sources not "
        "present locally. See test_calvin_commentary_full_corpus.py / "
        "test_jfb_commentary_full_corpus.py / test_henry_commentary_full_corpus.py "
        "for fetch instructions."
    ),
)


@pytest.fixture(scope="module")
def combined_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("combined_calvin_jfb_henry") / "commentary.sqlite3"
    import_combined_commentary_corpus(
        calvin_entries=_CALVIN_ENTRIES,
        jfb_xml_path=_JFB_MANIFEST.source.local_path,
        jfb_book_entries=list(_JFB_MANIFEST.books),
        henry_manifest=_HENRY_MANIFEST,
        database_path=database,
        imported_at="2026-01-01T00:00:00Z",
    )
    return database


@pytest.fixture(scope="module")
def combined_repo(combined_db: Path) -> CommentaryRepository:
    return CommentaryRepository(combined_db)


# --- Architectural proof: no collisions, correct provenance -----------


def test_combined_scale_matches_sum_of_all_three_sources(
    combined_repo: CommentaryRepository,
) -> None:
    status = combined_repo.store_status()
    assert status.available is True
    assert status.work_count == 23 + 66 + 66
    assert status.edition_count == 45 + 66 + 66
    assert status.source_file_count == 45 + 66 + 66
    assert status.import_batch_count == 45 + 66 + 66
    assert status.contributor_count == 9 + 3 + 15
    assert status.section_count == 14643 + 32394 + 5579
    assert status.chunk_count == 11785 + 21071 + 5512
    assert status.passage_link_count == 14153 + 31097 + 4258


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
    # Only Henry's 5 one-chapter-book source files trip the generic
    # "< 5 passage links" heuristic (same as in isolation) — Calvin and
    # JFB contribute no warnings of their own.
    assert len(report.warnings) == 1
    assert "< 5 passage link" in report.warnings[0]
    # Calvin's 5 + Henry's 5 documented known-unmapped exceptions must
    # both survive correctly through the combined store; JFB has none.
    assert len(report.known_unmapped) == 5 + 5
    # Only Calvin's 354 parallel Harmony links; JFB and Henry contribute none.
    assert report.parallel_passage_link_count == 354
    assert len(report.works) == 23 + 66 + 66
    assert len(report.contributors) == 9 + 3 + 15


def test_combined_build_is_deterministic(tmp_path: Path) -> None:
    result_a = import_combined_commentary_corpus(
        calvin_entries=_CALVIN_ENTRIES,
        jfb_xml_path=_JFB_MANIFEST.source.local_path,
        jfb_book_entries=list(_JFB_MANIFEST.books),
        henry_manifest=_HENRY_MANIFEST,
        database_path=tmp_path / "first.sqlite3",
        imported_at="2026-01-01T00:00:00Z",
    )
    result_b = import_combined_commentary_corpus(
        calvin_entries=_CALVIN_ENTRIES,
        jfb_xml_path=_JFB_MANIFEST.source.local_path,
        jfb_book_entries=list(_JFB_MANIFEST.books),
        henry_manifest=_HENRY_MANIFEST,
        database_path=tmp_path / "second.sqlite3",
        imported_at="2099-06-15T12:00:00Z",
    )
    assert result_a.content_hash == result_b.content_hash


def test_combined_refuses_production_database_path() -> None:
    from textus_kb.importers.combined_commentary import CombinedCommentaryImportError
    from textus_kb.importers.commentary_sqlite import DEFAULT_DATABASE_PATH

    with pytest.raises(CombinedCommentaryImportError, match="production"):
        import_combined_commentary_corpus(
            calvin_entries=_CALVIN_ENTRIES,
            jfb_xml_path=_JFB_MANIFEST.source.local_path,
            jfb_book_entries=list(_JFB_MANIFEST.books),
            henry_manifest=_HENRY_MANIFEST,
            database_path=DEFAULT_DATABASE_PATH,
        )


# --- Retrieval: all three sources for a shared passage, two where Calvin is silent --


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
def test_all_three_sources_retrievable_where_all_exist(
    combined_repo: CommentaryRepository, label: str, reference: str
) -> None:
    items = retrieve_commentary_evidence(reference, repository=combined_repo)
    work_ids = {item.metadata.get("work_id") for item in items}
    calvin_hit = any(str(w).startswith("ccel.calvin") for w in work_ids)
    jfb_hit = any(str(w).startswith("ccel.jfb") for w in work_ids)
    henry_hit = any(str(w).startswith("ccel.henry") for w in work_ids)
    assert calvin_hit, f"{label}: expected a Calvin hit for {reference}"
    assert jfb_hit, f"{label}: expected a JFB hit for {reference}"
    assert henry_hit, f"{label}: expected a Henry hit for {reference}"
    for item in items:
        meta = item.metadata
        assert meta.get("contributors")
        assert meta.get("work_id")
        assert meta.get("edition_id")
        assert item.passage


def test_revelation_calvin_absent_jfb_and_henry_still_work(
    combined_repo: CommentaryRepository,
) -> None:
    """Calvin never wrote a commentary on Revelation; JFB and Henry both
    cover the whole Bible. The combined store must surface JFB+Henry
    here, never a fabricated Calvin hit."""
    items = retrieve_commentary_evidence("Revelation.1.1", repository=combined_repo)
    assert items
    work_ids = {item.metadata.get("work_id") for item in items}
    assert not any(str(w).startswith("ccel.calvin") for w in work_ids)
    assert any(str(w).startswith("ccel.jfb") for w in work_ids)
    assert any(str(w).startswith("ccel.henry") for w in work_ids)


# --- work_id filtering isolates each of the 3 sources -------------------


def test_work_id_filter_isolates_all_three_sources(
    combined_repo: CommentaryRepository,
) -> None:
    calvin_hits = combined_repo.sections_for_passage(
        "Genesis.1.1", work_id="ccel.calvin.work.genesis"
    )
    jfb_hits = combined_repo.sections_for_passage(
        "Genesis.1.1", work_id="ccel.jfb.work.genesis"
    )
    henry_hits = combined_repo.sections_for_passage(
        "Genesis.1.1", work_id="ccel.henry.work.genesis"
    )
    assert calvin_hits and jfb_hits and henry_hits
    assert all("Calvin" in h.work_title or "Genesis" in h.work_title for h in calvin_hits)
    assert all(h.work_title.startswith("Commentary Critical") for h in jfb_hits)
    assert all(h.work_title.startswith("Matthew Henry's Commentary") for h in henry_hits)


# --- PROFILE_COMMENTARY context selection: 3-source diversity ----------


def _packet(passage_canonical: str, passage_display: str, **kwargs) -> EvidencePacket:
    return EvidencePacket(
        passage_canonical=passage_canonical,
        passage_display=passage_display,
        build_id="test",
        manifest_version="test",
        **kwargs,
    )


def test_commentary_context_balances_three_sources_for_range_query(
    combined_db: Path,
) -> None:
    """The core proof this round exists to make: a range query with many
    same-tier hits across three works (including Henry's long,
    multi-verse-range prose) must not let any single commentary consume
    the whole PROFILE_COMMENTARY budget before the others are considered."""
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
    calvin_count = sum(v for k, v in counts.items() if k == "Commentary on Romans")
    jfb_count = sum(v for k, v in counts.items() if k.startswith("Commentary Critical"))
    henry_count = sum(v for k, v in counts.items() if k.startswith("Matthew Henry's Commentary"))
    assert calvin_count > 0, f"expected a Calvin section, got {counts}"
    assert jfb_count > 0, f"expected a JFB section, got {counts}"
    assert henry_count > 0, f"expected a Henry section, got {counts}"
    assert ctx.estimated_tokens <= ctx.max_tokens


def test_commentary_context_selection_deterministic_with_three_sources(
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


def test_exact_tier_from_any_source_precedes_lower_tier_across_sources(
    combined_db: Path,
) -> None:
    """The context_builder.py tier-aware interleave fix, proven directly
    against the real 3-source store: within PROFILE_COMMENTARY's selected
    items, no partial_overlap/containing_section hit may precede an
    exact_passage hit, regardless of which source (Calvin/JFB/Henry)
    either one belongs to. Work diversity must never outrank relevance."""
    ctx = build_context_from_evidence(
        _packet("Romans.1.1-7", "Romans 1:1-7"),
        PROFILE_COMMENTARY,
        commentary_database_path=combined_db,
    )
    tiers = [
        item.metadata.get("query_relation_type")
        for section in ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    ]
    rank = {"exact_passage": 0, "containing_section": 1, "partial_overlap": 2}
    ranked = [rank.get(str(t), 99) for t in tiers]
    assert ranked == sorted(ranked), f"tier ordering violated: {tiers}"


def test_direct_linguistic_evidence_priority_unaffected_by_three_sources(
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


def test_exegesis_profile_unaffected_by_three_source_combined_store(
    combined_db: Path,
) -> None:
    """PROFILE_EXEGESIS never touches Commentary at all — proven by simply
    building it against a real, populated 3-source combined store and
    confirming no commentary section appears."""
    ctx = build_context_from_evidence(
        _packet("Romans.1.1", "Romans 1:1"),
        PROFILE_EXEGESIS,
        commentary_database_path=combined_db,
    )
    assert ctx.profile == PROFILE_EXEGESIS
    assert all(section.type != "commentary" for section in ctx.sections)


# --- Grounded-generation smoke: deterministic evidence/context payload only --


@pytest.mark.parametrize(
    ("label", "reference"),
    [
        ("Genesis", "Genesis.1.1"),
        ("Psalms", "Psalms.23.1"),
        ("Isaiah", "Isaiah.53.5"),
        ("Gospel", "Matthew.1.1"),
        ("Romans", "Romans.1.1"),
        ("General/catholic epistle", "James.1.1"),
        ("Revelation", "Revelation.1.1"),
    ],
)
def test_grounded_commentary_context_smoke_across_canonical_categories(
    combined_db: Path, label: str, reference: str
) -> None:
    """Requirement #6: without calling any external LLM/API, prove the
    deterministic PROFILE_COMMENTARY evidence/context payload is well
    formed across Genesis/Psalms/Isaiah/a Gospel/Romans/a general
    epistle/Revelation, and that wherever multiple sources are available
    each is separately citable (distinct work_title/edition_id per item,
    never merged or attributed to the wrong work)."""
    ctx = build_context_from_evidence(
        _packet(reference, reference),
        PROFILE_COMMENTARY,
        commentary_database_path=combined_db,
    )
    items = [
        item
        for section in ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    ]
    assert items, f"{label}: expected at least one commentary item for {reference}"
    for item in items:
        assert item.metadata.get("work_id"), f"{label}: missing work_id provenance"
        assert item.metadata.get("edition_id"), f"{label}: missing edition_id provenance"
        assert item.metadata.get("contributors"), f"{label}: missing contributor provenance"
        assert item.text
    # Every citable item's (work_id, edition_id) pair must be internally
    # consistent — no cross-source attribution bleed.
    prefixes = {"ccel.calvin", "ccel.jfb", "ccel.henry"}
    for item in items:
        work_id = str(item.metadata.get("work_id"))
        edition_id = str(item.metadata.get("edition_id"))
        work_prefix = next((p for p in prefixes if work_id.startswith(p)), None)
        assert work_prefix, f"{label}: unrecognized work_id source prefix {work_id!r}"
        assert edition_id.startswith(work_prefix), (
            f"{label}: edition_id {edition_id!r} does not match work_id source {work_prefix!r}"
        )
    assert ctx.estimated_tokens <= ctx.max_tokens
