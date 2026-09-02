"""Commentary Knowledge Base production backend integration tests.

Covers the full evidence/context stack added on top of the Commentary
store: ``commentary_runtime`` status, ``CommentaryAdapter`` ->
``EvidenceItem``, ``retrieve_commentary_evidence``, the dedicated
``PROFILE_COMMENTARY`` context profile/budget, and citation formatting.

Uses the real, locally-fetched 45-volume Calvin corpus (gated on all raw
XML files being present, same as ``test_calvin_commentary_full_corpus.py``)
built once for the whole module — no network access at test time (the raw
XML is already on disk; only ``--calvin-fetch`` touches the network, which
is never invoked here). Store availability/corruption tests use small,
isolated tmp_path databases instead of the full corpus.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from textus_kb import commentary_runtime
from textus_kb.adapters.commentary import COMMENTARY_EXCERPT_CHAR_LIMIT
from textus_kb.citation import format_commentary_citation
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import (
    COMMENTARY_NO_MATCH_WARNING,
    COMMENTARY_SOURCE_WARNING,
    PROFILE_COMMENTARY,
)
from textus_kb.evidence import (
    RELATION_COMMENTARY_SOURCE,
    RELATION_DIRECT_PASSAGE,
    RELATION_LEXICAL_HIGHLIGHT,
    EvidenceItem,
    EvidencePacket,
)
from textus_kb.importers.calvin_commentary_thml import import_calvin_commentary_sqlite
from textus_kb.importers.calvin_source_fetch import load_source_manifest
from textus_kb.importers.calvin_commentary_thml import import_calvin_corpus_from_manifest
from textus_kb.importers.commentary_sqlite import create_empty_commentary_database
from textus_kb.repositories.commentary_repository import CommentaryRepository
from textus_kb.retrieval import retrieve_commentary_evidence

_ALL_MANIFEST_ENTRIES = load_source_manifest()
_ALL_RAW_PRESENT = all(entry.local_path.is_file() for entry in _ALL_MANIFEST_ENTRIES)

pytestmark = pytest.mark.skipif(
    not _ALL_RAW_PRESENT,
    reason=(
        "Not all 45 real Calvin ThML sources are present locally. Fetch with: "
        "python scripts/build_commentary_database.py --calvin-fetch"
    ),
)

ROMANS_FIXTURE = Path("tests/fixtures/kb/calvin_calcom38_romans_ch1_min.xml")


@pytest.fixture(scope="module")
def full_corpus_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("commentary_evidence") / "commentary.sqlite3"
    import_calvin_corpus_from_manifest(
        _ALL_MANIFEST_ENTRIES, database_path=database, imported_at="2026-01-01T00:00:00Z"
    )
    return database


@pytest.fixture(scope="module")
def full_corpus_repo(full_corpus_db: Path) -> CommentaryRepository:
    return CommentaryRepository(full_corpus_db)


# --- retrieve_commentary_evidence: real passage categories -----------------


def test_romans_exact_verse(full_corpus_repo: CommentaryRepository) -> None:
    items = retrieve_commentary_evidence("Romans.1.1", repository=full_corpus_repo)
    assert len(items) == 1
    item = items[0]
    assert item.relation_type == RELATION_COMMENTARY_SOURCE
    assert item.passage == "Rom.1.1"
    assert item.content.strip()
    assert item.metadata["query_relation_type"] == "exact_passage"
    assert "Rom.1.1" in item.metadata["primary_passages"]


def test_romans_range(full_corpus_repo: CommentaryRepository) -> None:
    items = retrieve_commentary_evidence("Romans.1.1-7", repository=full_corpus_repo)
    assert items, "expected commentary evidence covering Romans 1:1-7"
    assert all(item.content.strip() for item in items)
    assert all(item.metadata["work_title"] == "Commentary on Romans" for item in items)


def test_psalms(full_corpus_repo: CommentaryRepository) -> None:
    items = retrieve_commentary_evidence("Psalms.23.1", repository=full_corpus_repo)
    assert len(items) == 1
    assert items[0].passage == "Ps.23.1"
    assert items[0].content.strip()


def test_prophetic_book(full_corpus_repo: CommentaryRepository) -> None:
    items = retrieve_commentary_evidence("Isaiah.53.5", repository=full_corpus_repo)
    assert len(items) == 1
    assert items[0].passage == "Isa.53.5"
    assert items[0].content.strip()


def test_acts(full_corpus_repo: CommentaryRepository) -> None:
    items = retrieve_commentary_evidence("Acts.2.1", repository=full_corpus_repo)
    assert len(items) == 1
    assert items[0].passage == "Acts.2.1"
    assert items[0].content.strip()


def test_gospel_harmony_primary_and_parallel(
    full_corpus_repo: CommentaryRepository,
) -> None:
    """The same Harmony section is reachable via Matthew (its primary
    passage) and via Luke (its parallel passage); the adapter's metadata
    must label each correctly, never inferring it from row order."""
    via_matthew = retrieve_commentary_evidence("Matthew.1.1-17", repository=full_corpus_repo)
    via_luke = retrieve_commentary_evidence("Luke.3.23-38", repository=full_corpus_repo)
    matthew_ids = {item.evidence_id for item in via_matthew}
    luke_ids = {item.evidence_id for item in via_luke}
    shared = matthew_ids & luke_ids
    assert shared, "the shared Harmony section must be reachable via either gospel"

    matthew_hit = next(item for item in via_matthew if item.evidence_id in shared)
    luke_hit = next(item for item in via_luke if item.evidence_id in shared)
    assert matthew_hit.passage in matthew_hit.metadata["primary_passages"]
    assert luke_hit.passage in luke_hit.metadata["parallel_passages"]


def test_negative_no_commentary_for_book(full_corpus_repo: CommentaryRepository) -> None:
    """Calvin wrote no commentary on Judges; must yield zero evidence, not
    a fabricated hit."""
    assert retrieve_commentary_evidence("Judges.1.1", repository=full_corpus_repo) == []


def test_no_match_never_falls_back_to_fts(full_corpus_repo: CommentaryRepository) -> None:
    """Proof, not assumption: full-text search over this exact corpus DOES
    find 'Judges' (Calvin mentions the word in other books' commentary),
    yet passage-scoped retrieval for Judges.1.1 still returns nothing —
    demonstrating no silent FTS substitution when passage retrieval misses."""
    fts_hits = full_corpus_repo.search_text("Judges")
    assert fts_hits, "sanity check: FTS must actually find something for this term"
    assert retrieve_commentary_evidence("Judges.1.1", repository=full_corpus_repo) == []


def test_invalid_passage_mapping_returns_no_evidence(
    full_corpus_repo: CommentaryRepository,
) -> None:
    assert retrieve_commentary_evidence("Not A Real Reference", repository=full_corpus_repo) == []


# --- Excerpt / long-section chunk selection --------------------------------


def test_long_section_excerpt_is_bounded_but_citation_points_to_full_section(
    full_corpus_repo: CommentaryRepository,
) -> None:
    items = retrieve_commentary_evidence("Romans.1.1", repository=full_corpus_repo)
    item = items[0]
    assert len(item.content) <= COMMENTARY_EXCERPT_CHAR_LIMIT + 1
    # Citation/provenance still names the real, un-truncated section.
    assert item.metadata["section_id"] == "ccel.calvin.calcom38.v.ii.v1"
    assert item.metadata["chunk_ids"], "excerpt metadata must list the section's real chunk ids"


# --- Context builder: PROFILE_COMMENTARY -----------------------------------


def _packet(passage_canonical: str, passage_display: str, **kwargs) -> EvidencePacket:
    return EvidencePacket(
        passage_canonical=passage_canonical,
        passage_display=passage_display,
        build_id="test",
        manifest_version="test",
        **kwargs,
    )


def test_commentary_context_budget_is_respected(full_corpus_db: Path) -> None:
    ctx = build_context_from_evidence(
        _packet("Romans.1.1-7", "Romans 1:1-7"),
        PROFILE_COMMENTARY,
        commentary_database_path=full_corpus_db,
    )
    assert ctx.estimated_tokens <= ctx.max_tokens
    assert ctx.max_tokens == 3500
    assert ctx.target_tokens == 3000
    assert any(section.type == "commentary" for section in ctx.sections)


def test_commentary_context_deterministic_selection_across_calls(
    full_corpus_db: Path,
) -> None:
    packet = _packet("Romans.1.1-7", "Romans 1:1-7")
    runs = [
        [item.evidence_id for section in build_context_from_evidence(
            packet, PROFILE_COMMENTARY, commentary_database_path=full_corpus_db
        ).sections for item in section.items]
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


def test_commentary_context_preserves_repository_ranking_order(
    full_corpus_db: Path, full_corpus_repo: CommentaryRepository
) -> None:
    """The repository's own deterministic ranking (tier, span, then
    primary-before-parallel as the final tie-break) must survive the trip
    through evidence loading and generic token-budget selection — the
    selected context items' relative order must match the repository's
    order for the sections that made it into context, never a re-sort
    that discards the ranking already computed at the repository layer."""
    reference = "Romans.1.1-7"
    repo_order = [hit.section_id for hit in full_corpus_repo.sections_for_passage(reference)]

    ctx = build_context_from_evidence(
        _packet(reference, "Romans 1:1-7"),
        PROFILE_COMMENTARY,
        commentary_database_path=full_corpus_db,
    )
    context_section_ids = [
        item.metadata.get("section_id")
        for section in ctx.sections
        for item in section.items
        if item.item_type == "commentary_source"
    ]
    assert context_section_ids, "expected at least one commentary item selected"
    # The selected subset must appear in the same relative order as the
    # repository's own ranking (a filtered sub-sequence, not reordered).
    filtered_repo_order = [sid for sid in repo_order if sid in context_section_ids]
    assert filtered_repo_order == context_section_ids


def test_commentary_context_primary_labeling_survives_full_build(
    full_corpus_db: Path,
) -> None:
    """Within the shared Harmony section, when reached through its primary
    passage the evidence's own metadata must say so (and the reverse for
    the parallel passage) — proving the primary/parallel labeling survives
    the full context build, not just raw repository retrieval."""
    matthew_ctx = build_context_from_evidence(
        _packet("Matthew.1.1-17", "Matthew 1:1-17"),
        PROFILE_COMMENTARY,
        commentary_database_path=full_corpus_db,
    )
    luke_ctx = build_context_from_evidence(
        _packet("Luke.3.23-38", "Luke 3:23-38"),
        PROFILE_COMMENTARY,
        commentary_database_path=full_corpus_db,
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
    assert shared, "the shared Harmony section must survive selection on both sides"
    shared_id = next(iter(shared))
    assert "Matt.1.1-17" in matthew_items[shared_id].metadata.get("primary_passages", [])
    assert "Luke.3.23-38" in luke_items[shared_id].metadata.get("parallel_passages", [])


def test_commentary_source_unavailable_no_llm_substitution(tmp_path: Path) -> None:
    """Missing DB: explicit unavailable warning, no commentary section, no
    fabricated content — the other sections (passage scope) still build."""
    ctx = build_context_from_evidence(
        _packet("Romans.1.1", "Romans 1:1"),
        PROFILE_COMMENTARY,
        commentary_database_path=tmp_path / "does_not_exist.sqlite3",
    )
    assert COMMENTARY_SOURCE_WARNING in ctx.warnings
    assert all(section.type != "commentary" for section in ctx.sections)


def test_commentary_source_corrupt_db_no_llm_substitution(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    path.write_text("not a sqlite database", encoding="utf-8")
    ctx = build_context_from_evidence(
        _packet("Romans.1.1", "Romans 1:1"),
        PROFILE_COMMENTARY,
        commentary_database_path=path,
    )
    assert COMMENTARY_SOURCE_WARNING in ctx.warnings
    assert all(section.type != "commentary" for section in ctx.sections)


def test_commentary_source_wrong_schema_no_llm_substitution(tmp_path: Path) -> None:
    path = tmp_path / "wrong_schema.sqlite3"
    create_empty_commentary_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE store_metadata SET value = '999' WHERE key = 'schema_version'"
        )
        connection.commit()
    ctx = build_context_from_evidence(
        _packet("Romans.1.1", "Romans 1:1"),
        PROFILE_COMMENTARY,
        commentary_database_path=path,
    )
    assert COMMENTARY_SOURCE_WARNING in ctx.warnings
    assert all(section.type != "commentary" for section in ctx.sections)


def test_commentary_no_match_warning_no_fts_fallback(full_corpus_db: Path) -> None:
    """Available store, unsupported book: explicit no-match warning, not
    silence and not a full-text fallback section."""
    ctx = build_context_from_evidence(
        _packet("Judges.1.1", "Judges 1:1"),
        PROFILE_COMMENTARY,
        commentary_database_path=full_corpus_db,
    )
    assert COMMENTARY_NO_MATCH_WARNING in ctx.warnings
    assert all(section.type != "commentary" for section in ctx.sections)


def test_commentary_absence_does_not_break_other_profiles(full_corpus_db: Path) -> None:
    """A missing/irrelevant Commentary store must never affect the
    exegesis profile — Commentary is only ever loaded for PROFILE_COMMENTARY."""
    from textus_kb.context_profiles import PROFILE_EXEGESIS

    ctx = build_context_from_evidence(
        _packet("Romans.1.1", "Romans 1:1"),
        PROFILE_EXEGESIS,
        commentary_database_path=Path("/does/not/exist/commentary.sqlite3"),
    )
    assert ctx.profile == PROFILE_EXEGESIS
    assert all(section.type != "commentary" for section in ctx.sections)


def test_direct_linguistic_evidence_priority_not_degraded_by_commentary(
    full_corpus_db: Path,
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
        packet, PROFILE_COMMENTARY, commentary_database_path=full_corpus_db
    )
    scores_by_id = {
        item.evidence_id: item.relevance_score
        for section in ctx.sections
        for item in section.items
    }
    assert scores_by_id["EV-DIRECT-1"] > next(
        score for eid, score in scores_by_id.items() if eid.startswith("EV-COMM-")
    )
    assert scores_by_id["EV-DIRECT-1"] > scores_by_id["EV-LEX-G1401"]


# --- Citation / provenance ---------------------------------------------


def test_commentary_citation_has_required_provenance_fields(
    full_corpus_repo: CommentaryRepository,
) -> None:
    items = retrieve_commentary_evidence("Romans.1.1", repository=full_corpus_repo)
    item = items[0]
    meta = item.metadata
    assert meta.get("contributors")
    assert meta.get("work_id")
    assert meta.get("edition_id")
    assert item.passage
    assert item.passage in meta.get("primary_passages", []) or item.passage in meta.get(
        "parallel_passages", []
    )
    assert meta.get("source_locator")
    citation_text = format_commentary_citation(item)
    assert "John Calvin" in citation_text
    assert "primary" in citation_text or "parallel" in citation_text


# --- commentary_runtime -----------------------------------------------


def test_commentary_runtime_missing_database(tmp_path: Path) -> None:
    status = commentary_runtime.get_status(tmp_path / "missing.sqlite3")
    assert status.available is False
    assert status.reason == "database_missing"


def test_commentary_runtime_corrupt_database(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    path.write_text("not a sqlite database", encoding="utf-8")
    status = commentary_runtime.get_status(path)
    assert status.available is False
    assert status.reason in {"database_unopenable", "schema_incompatible"}


def test_commentary_runtime_wrong_schema(tmp_path: Path) -> None:
    path = tmp_path / "wrong_schema.sqlite3"
    create_empty_commentary_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE store_metadata SET value = '999' WHERE key = 'schema_version'"
        )
        connection.commit()
    status = commentary_runtime.get_status(path)
    assert status.available is False
    assert status.reason == "schema_incompatible"


def test_commentary_runtime_available(tmp_path: Path) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE], database_path=database)
    status = commentary_runtime.get_status(database)
    assert status.available is True
    assert status.reason == "ok"


def test_commentary_runtime_env_var_override(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "commentary.sqlite3"
    import_calvin_commentary_sqlite([ROMANS_FIXTURE], database_path=database)
    monkeypatch.setenv(
        commentary_runtime.COMMENTARY_DATABASE_PATH_ENV_VAR, str(database)
    )
    status = commentary_runtime.get_status()
    assert status.available is True
    assert status.database_path == str(database)
