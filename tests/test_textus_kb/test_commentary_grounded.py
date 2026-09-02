"""Commentary production dispatch: grounded_generation.py wiring.

Closes the loop on the Commentary backend built in prior rounds (store,
repository, runtime, evidence, citation, PROFILE_COMMENTARY): proves the
actual grounded-generation entry point (``prepare_grounded_provider_prompt``)
can use it, fail-closed, isolated from theology/exegesis/historical, and
never auto-included unless explicitly requested via module="commentary".

Real end-to-end smoke tests use the real, locally-fetched 45-volume Calvin
corpus (same gating as ``test_calvin_commentary_full_corpus.py``) built
once for the module — no network access at test time. Fail-closed and
regression tests use monkeypatched ``commentary_runtime.get_status`` /
small isolated tmp_path stores, matching ``test_theology_grounded.py``'s
established pattern for the theology module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from textus_kb.adapters.commentary import COMMENTARY_SOURCE_ID
from textus_kb.commentary_runtime import CommentaryRuntimeStatus
from textus_kb.context_profiles import (
    COMMENTARY_NO_MATCH_WARNING,
    PROFILE_COMMENTARY,
    PROFILE_EXEGESIS,
    PROFILE_HISTORICAL,
    PROFILE_THEOLOGY,
)
from textus_kb.grounded_generation import (
    GROUNDED_FLAG,
    REASON_SOURCE_UNAVAILABLE,
    STATUS_DISABLED,
    STATUS_FALLBACK,
    STATUS_USED,
    prepare_grounded_provider_prompt,
    resolve_grounded_module,
)
from textus_kb.importers.calvin_commentary_thml import import_calvin_corpus_from_manifest
from textus_kb.importers.calvin_source_fetch import load_source_manifest
from textus_kb.importers.commentary_sqlite import create_empty_commentary_database
from textus_kb.prompt_composer import (
    DEFAULT_KB_CONTEXT_MAX_BY_MODULE,
    DEFAULT_KB_CONTEXT_TARGET_BY_MODULE,
    DRY_RUN_PRODUCTION_STUB,
    _SECTION_HEADERS,
    _SOURCE_DISPLAY_LABELS,
    _SUPPORTED_MODULES,
    _TRIM_SECTION_ORDER,
    compose_grounded_prompt,
)
from textus_kb.shadow import MODULE_TO_PROFILE

PRODUCTION = "PRODUCTION-COMMENTARY-PROMPT"


def _status(*, available: bool, reason: str = "ok", path: str = "C:/tmp/commentary.sqlite3"):
    return CommentaryRuntimeStatus(
        available=available,
        reason=reason if not available else "ok",
        database_path=path,
        detail="" if available else reason,
    )


# --- Mapping / composer support --------------------------------------------


def test_resolve_grounded_module_commentary() -> None:
    assert resolve_grounded_module("commentary") == "commentary"
    # Existing mappings unaffected.
    assert resolve_grounded_module("theology") == "theology"
    assert resolve_grounded_module("exegesis") == "exegesis"
    assert resolve_grounded_module("history") == "historical_context"


def test_module_to_profile_commentary() -> None:
    assert MODULE_TO_PROFILE["commentary"] == PROFILE_COMMENTARY
    assert MODULE_TO_PROFILE["theology"] == PROFILE_THEOLOGY
    assert MODULE_TO_PROFILE["exegesis"] == PROFILE_EXEGESIS
    assert MODULE_TO_PROFILE["historical_context"] == PROFILE_HISTORICAL


def test_prompt_composer_supports_commentary() -> None:
    assert "commentary" in _SUPPORTED_MODULES
    assert _SECTION_HEADERS["commentary"] == "COMMENTARY SOURCES"
    assert _SOURCE_DISPLAY_LABELS[COMMENTARY_SOURCE_ID] == "Commentary store"
    assert "commentary" in _TRIM_SECTION_ORDER
    assert DEFAULT_KB_CONTEXT_TARGET_BY_MODULE["commentary"] == 3000
    assert DEFAULT_KB_CONTEXT_MAX_BY_MODULE["commentary"] == 3500
    # Never reuses theology's budget numbers by accident.
    assert (
        DEFAULT_KB_CONTEXT_TARGET_BY_MODULE["commentary"]
        != DEFAULT_KB_CONTEXT_TARGET_BY_MODULE["theology"]
    )


def test_composer_compose_commentary_succeeds() -> None:
    from textus_kb.context_builder import ContextItem, ContextSection, LLMContextPacket

    item = ContextItem(
        text="SYNTHETIC Calvin commentary body.",
        evidence_id="EV-COMM-test.section",
        source_id=COMMENTARY_SOURCE_ID,
        relevance_score=90,
        item_type="commentary_source",
        metadata={
            "human_readable_locator": "John Calvin (author), Commentary on Romans, Chapter 1",
            "work_title": "Commentary on Romans",
            "section_id": "ccel.calvin.calcom38.v.ii.v1",
            "edition_id": "ccel.calvin.calcom38.edition",
            "source_locator": "ccel:calvin/calcom38#v.ii-p1.1",
            "canonical_scope": "Rom.1.1",
            "primary_passages": ["Rom.1.1"],
            "parallel_passages": [],
        },
    )
    packet = LLMContextPacket(
        passage="Rom.1.1",
        passage_display="Romans 1:1",
        profile=PROFILE_COMMENTARY,
        sections=[ContextSection(type="commentary", items=(item,))],
        source_ids=[COMMENTARY_SOURCE_ID],
        evidence_ids=[item.evidence_id],
        schema_version="2",
        evidence_packet_build_id="test",
    )
    preview = compose_grounded_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        canonical_passage="Rom.1.1",
        module="commentary",
        context_packet=packet,
    )
    assert preview.success is True
    assert preview.module == "commentary"
    assert preview.kb_context_target_tokens == 3000
    assert preview.kb_context_max_tokens == 3500
    assert "COMMENTARY GROUNDED USE RULES" in preview.composed_prompt
    assert "[COMMENTARY SOURCES]" in preview.composed_prompt
    assert "Do not assign or imply a reliability score for the commentator." in (
        preview.composed_prompt
    )
    assert "John Calvin (author), Commentary on Romans, Chapter 1" in preview.composed_prompt
    assert "primary_passages=Rom.1.1" in preview.composed_prompt
    assert "SYNTHETIC Calvin commentary body." in preview.composed_prompt


# --- Fail-closed (mocked runtime) ------------------------------------------


def test_commentary_missing_db_hard_fallback_no_partial_grounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_calls: list[str] = []
    retrieve_calls = {"n": 0}

    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: status_calls.append("called")
        or _status(available=False, reason="database_missing"),
    )

    def counting_retrieve(ref):
        retrieve_calls["n"] += 1
        raise AssertionError("missing store must not retrieve")

    monkeypatch.setattr("textus_kb.retrieval.retrieve", counting_retrieve)
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Romans.1.1",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert status_calls == ["called"]
    assert retrieve_calls["n"] == 0
    assert prep.status == STATUS_FALLBACK
    assert prep.fallback_reason == REASON_SOURCE_UNAVAILABLE
    assert prep.provider_prompt == PRODUCTION
    assert "<<<BEGIN_KB_DATA>>>" not in prep.provider_prompt


def test_commentary_corrupt_db_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    path.write_text("not a sqlite database", encoding="utf-8")
    from textus_kb.commentary_runtime import get_status

    status = get_status(path)
    assert status.available is False
    assert status.reason in {"database_unopenable", "schema_incompatible"}


def test_commentary_wrong_schema_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "wrong_schema.sqlite3"
    create_empty_commentary_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE store_metadata SET value = '999' WHERE key = 'schema_version'"
        )
        connection.commit()
    from textus_kb.commentary_runtime import get_status

    status = get_status(path)
    assert status.available is False
    assert status.reason == "schema_incompatible"

    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status", lambda **kwargs: status
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Romans.1.1",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert prep.status == STATUS_FALLBACK
    assert prep.fallback_reason == REASON_SOURCE_UNAVAILABLE
    assert prep.provider_prompt == PRODUCTION


def test_commentary_explicit_db_path_override_reaches_context_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves the runtime-resolved (potentially overridden) path is the one
    actually threaded into context building, not silently ignored."""
    build_calls: list[dict] = []
    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: _status(available=True, path="C:/tmp/explicit-override.sqlite3"),
    )

    def fake_retrieve(ref):
        from textus_kb.evidence import EvidencePacket

        return EvidencePacket(
            passage_canonical="Romans.1.1",
            passage_display="Romans 1:1",
            build_id="test",
            manifest_version="test",
        )

    def fake_build(evidence, profile, commentary_database_path=None, **kwargs):
        build_calls.append({"profile": profile, "path": commentary_database_path})
        from textus_kb.context_builder import LLMContextPacket

        return LLMContextPacket(
            passage="Rom.1.1",
            passage_display="Romans 1:1",
            profile=profile,
            warnings=[COMMENTARY_NO_MATCH_WARNING],
            schema_version="2",
            evidence_packet_build_id="test",
        )

    monkeypatch.setattr("textus_kb.retrieval.retrieve", fake_retrieve)
    monkeypatch.setattr(
        "textus_kb.context_builder.build_context_from_evidence", fake_build
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Romans.1.1",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert build_calls
    assert build_calls[0]["profile"] == PROFILE_COMMENTARY
    assert build_calls[0]["path"] == "C:/tmp/explicit-override.sqlite3"


# --- Regression: kill switch / other modules unaffected --------------------


@pytest.mark.parametrize(
    ("key", "module"),
    [
        ("theology", "theology"),
        ("exegesis", "exegesis"),
        ("history", "historical_context"),
        ("commentary", "commentary"),
    ],
)
def test_kill_switch_disables_commentary_too(
    monkeypatch: pytest.MonkeyPatch, key: str, module: str
) -> None:
    monkeypatch.setenv(GROUNDED_FLAG, "false")
    status_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: status_calls.append("called") or _status(available=True),
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Jn 4,1-42" if module != "commentary" else "Romans.1.1",
        module=module,
    )
    assert status_calls == []
    assert prep.status == STATUS_DISABLED
    assert prep.provider_prompt == PRODUCTION


def test_theology_module_does_not_touch_commentary_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commentary_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: commentary_calls.append("called") or _status(available=True),
    )
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: __import__(
            "textus_kb.theology_runtime", fromlist=["TheologyRuntimeStatus"]
        ).TheologyRuntimeStatus(
            available=False, reason="database_missing", database_path="x"
        ),
    )
    prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Jn 4,1-42",
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert commentary_calls == []


@pytest.mark.parametrize("module", ["exegesis", "historical_context"])
def test_exegesis_and_historical_do_not_touch_commentary_runtime(
    monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    commentary_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: commentary_calls.append("called") or _status(available=True),
    )
    prepare_grounded_provider_prompt(
        production_prompt="PROD",
        passage="Jn 4,1-42" if module == "exegesis" else "Lk 10,25-37",
        module=module,
        grounded_enabled=True,
        use_cache=False,
    )
    assert commentary_calls == []


def test_commentary_module_does_not_touch_theology_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    theology_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: theology_calls.append("called"),
    )
    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: _status(available=False, reason="database_missing"),
    )
    prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Romans.1.1",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert theology_calls == []


def test_commentary_not_auto_included_in_other_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Commentary must only ever be built when module='commentary' is
    explicitly requested — proven by never calling commentary_runtime for
    any other mapped module, across a full prepare call for each."""
    commentary_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: commentary_calls.append("called") or _status(available=True),
    )
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: __import__(
            "textus_kb.theology_runtime", fromlist=["TheologyRuntimeStatus"]
        ).TheologyRuntimeStatus(available=True, reason="ok", database_path="x"),
    )
    for module, passage in (
        ("theology", "Jn 4,1-42"),
        ("exegesis", "Jn 4,1-42"),
        ("historical_context", "Lk 10,25-37"),
    ):
        prepare_grounded_provider_prompt(
            production_prompt="PROD",
            passage=passage,
            module=module,
            grounded_enabled=True,
            use_cache=False,
        )
    assert commentary_calls == []


# --- Real end-to-end smoke (full 45-volume corpus, no network) -------------

_ALL_MANIFEST_ENTRIES = load_source_manifest()
_ALL_RAW_PRESENT = all(entry.local_path.is_file() for entry in _ALL_MANIFEST_ENTRIES)

_smoke_skip = pytest.mark.skipif(
    not _ALL_RAW_PRESENT,
    reason=(
        "Not all 45 real Calvin ThML sources are present locally. Fetch with: "
        "python scripts/build_commentary_database.py --calvin-fetch"
    ),
)


@pytest.fixture(scope="module")
def full_corpus_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("commentary_grounded") / "commentary.sqlite3"
    import_calvin_corpus_from_manifest(
        _ALL_MANIFEST_ENTRIES, database_path=database, imported_at="2026-01-01T00:00:00Z"
    )
    return database


@pytest.fixture()
def _use_full_corpus(full_corpus_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "textus_kb.commentary_runtime.get_status",
        lambda **kwargs: _status(available=True, path=str(full_corpus_db)),
    )
    yield full_corpus_db


def _commentary_items(prep) -> list[dict]:
    packet = prep.context_packet or {}
    items = []
    for section in packet.get("sections") or []:
        for item in section.get("items") or []:
            if item.get("item_type") == "commentary_source":
                items.append(item)
    return items


@_smoke_skip
@pytest.mark.parametrize(
    ("label", "passage", "expect_work_title"),
    [
        ("Romans", "Romans.1.1", "Commentary on Romans"),
        ("Psalms", "Psalms.23.1", "Commentary on the Book of Psalms"),
        ("Prophetic book", "Isaiah.53.5", "Commentary on Isaiah"),
    ],
)
def test_smoke_evidence_payload_correct(
    _use_full_corpus, label: str, passage: str, expect_work_title: str
) -> None:
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage=passage,
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert prep.status == STATUS_USED, label
    items = _commentary_items(prep)
    assert items, f"{label}: expected at least one commentary evidence item"
    for item in items:
        meta = item.get("metadata") or {}
        assert "John Calvin" in (meta.get("contributors") or [""])[0]
        assert meta.get("work_title") == expect_work_title
        assert meta.get("primary_passages") or meta.get("parallel_passages")
        assert meta.get("edition_id")
        assert meta.get("section_id")
        assert meta.get("source_locator")
    assert prep.kb_context_estimated_tokens <= 3500
    assert "COMMENTARY GROUNDED USE RULES" in prep.provider_prompt


@_smoke_skip
def test_smoke_gospel_harmony_primary_and_parallel(_use_full_corpus) -> None:
    matthew_prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Matthew.1.1-17",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    luke_prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Luke.3.23-38",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert matthew_prep.status == STATUS_USED
    assert luke_prep.status == STATUS_USED
    matthew_ids = {item["metadata"].get("section_id") for item in _commentary_items(matthew_prep)}
    luke_ids = {item["metadata"].get("section_id") for item in _commentary_items(luke_prep)}
    shared = matthew_ids & luke_ids
    assert shared, "the shared Harmony section must surface on both sides"
    shared_id = next(iter(shared))
    matthew_item = next(
        item for item in _commentary_items(matthew_prep)
        if item["metadata"].get("section_id") == shared_id
    )
    luke_item = next(
        item for item in _commentary_items(luke_prep)
        if item["metadata"].get("section_id") == shared_id
    )
    assert "Matt.1.1-17" in matthew_item["metadata"].get("primary_passages", [])
    assert "Luke.3.23-38" in luke_item["metadata"].get("parallel_passages", [])
    # No unrelated Calvin section leaking in: every item returned for the
    # Matthew query must itself cover a Matthew passage (and likewise for
    # Luke) — a Harmony section legitimately also lists its parallel
    # gospel passage (that's real primary/parallel data, not a leak), but
    # nothing from an unrelated book/query should ever appear.
    for item in _commentary_items(matthew_prep):
        passages = item["metadata"].get("canonical_passages", [])
        assert any(p.startswith("Matt.") for p in passages), passages
    for item in _commentary_items(luke_prep):
        passages = item["metadata"].get("canonical_passages", [])
        assert any(p.startswith("Luke.") for p in passages), passages


@_smoke_skip
def test_smoke_negative_no_commentary_for_book(_use_full_corpus) -> None:
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Judges.1.1",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    assert prep.status == STATUS_USED
    assert _commentary_items(prep) == []
    assert COMMENTARY_NO_MATCH_WARNING in prep.provider_prompt
    assert "John Calvin" not in prep.provider_prompt.split("=== KNOWLEDGE BASE CONTEXT ===")[-1].split(
        "<<<END_KB_DATA>>>"
    )[0]


@_smoke_skip
def test_smoke_no_unrelated_section_for_narrow_query(_use_full_corpus) -> None:
    """A narrow exact-verse query must not pull in unrelated Calvin sections
    from other chapters/books."""
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Romans.1.1",
        module="commentary",
        grounded_enabled=True,
        use_cache=False,
    )
    items = _commentary_items(prep)
    assert items
    for item in items:
        meta = item.get("metadata") or {}
        assert all(p.startswith("Rom.") for p in meta.get("canonical_passages", []))
