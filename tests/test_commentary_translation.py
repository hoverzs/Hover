"""Hungarian Commentary translation infrastructure tests -- store, policy
and service layer only.

2026-09-03 reader redesign: the UI-integration tests that used to live at
the bottom of this file (a per-section "Eredeti" / "Magyar fordítás"
toggle) were removed along with that UI -- translation is now a
READER-level concern (one HU/EN toggle + one "translate the missing
parts" action per selected source family). The reader-level translation
UI tests now live in tests/test_commentary_ui.py, next to the rest of
the reader's own tests, and exercise the exact same, completely
unchanged store/policy/service layer tested here.

No external LLM/API is called anywhere in this file -- every ``generate_fn``
is a local fake that records what it was called with. Reuses the same
small, synthetic 3-source Commentary document as ``tests/test_commentary_
ui.py``/``tests/test_commentary_compare.py`` (``_synthetic_document``),
keeping these tests fast, deterministic and independent of whether the
real corpora have been fetched/built locally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import commentary_translation_service as svc
from tests.test_commentary_ui import _synthetic_document
from textus_kb import commentary_translation_policy as policy
from textus_kb import commentary_translation_store as store
from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
from textus_kb.repositories.commentary_repository import CommentaryRepository

_HENRY_SECTION_ID = "test.henry.range"  # 2 chunks: "PART ONE" / "PART TWO"
_JFB_SECTION_ID = "test.jfb.exact"  # 1 chunk


@pytest.fixture(scope="module")
def synthetic_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("commentary_translation_synth") / "commentary.sqlite3"
    import_commentary_sqlite(document=_synthetic_document(), database_path=database)
    return database


@pytest.fixture()
def synthetic_repo(synthetic_db: Path) -> CommentaryRepository:
    return CommentaryRepository(synthetic_db)


@pytest.fixture()
def translation_db(tmp_path: Path) -> Path:
    return tmp_path / "commentary_translations.sqlite3"


class _FakeGenerate:
    """Records every call; never a real provider."""

    def __init__(self, response: str = "SZINTETIKUS MAGYAR FORDÍTÁS") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.response = response

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append((prompt, kwargs))
        return self.response


# --- Store: fail-closed cache primitives --------------------------------


def test_store_get_returns_none_when_db_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.sqlite3"
    assert store.get_translation(
        "sec", "fp", language="hu", policy_version="v1", database_path=missing
    ) is None


def test_store_get_returns_none_on_corrupt_db(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a real sqlite database")
    assert store.get_translation(
        "sec", "fp", language="hu", policy_version="v1", database_path=corrupt
    ) is None


def test_store_save_then_get_round_trips(translation_db: Path) -> None:
    saved = store.save_translation(
        section_id="sec.1",
        source_fingerprint="fp-abc",
        language="hu",
        policy_version="v1",
        translated_text="Lefordított szöveg.",
        provider_model="gemini-2.5-flash",
        database_path=translation_db,
    )
    assert saved is not None
    assert saved.translated_text == "Lefordított szöveg."

    fetched = store.get_translation(
        "sec.1", "fp-abc", language="hu", policy_version="v1", database_path=translation_db
    )
    assert fetched is not None
    assert fetched.translated_text == "Lefordított szöveg."
    assert fetched.provider_model == "gemini-2.5-flash"
    assert fetched.section_id == "sec.1"
    assert fetched.source_fingerprint == "fp-abc"
    assert fetched.policy_version == "v1"


def test_store_never_caches_blank_text(translation_db: Path) -> None:
    assert store.save_translation(
        section_id="sec.1",
        source_fingerprint="fp",
        language="hu",
        policy_version="v1",
        translated_text="   ",
        database_path=translation_db,
    ) is None
    assert not translation_db.is_file()


def test_store_different_fingerprint_is_a_miss(translation_db: Path) -> None:
    store.save_translation(
        section_id="sec.1",
        source_fingerprint="fp-old",
        language="hu",
        policy_version="v1",
        translated_text="Régi fordítás.",
        database_path=translation_db,
    )
    assert store.get_translation(
        "sec.1", "fp-new", language="hu", policy_version="v1", database_path=translation_db
    ) is None
    # the old row itself is untouched, still fetchable under its own key
    old = store.get_translation(
        "sec.1", "fp-old", language="hu", policy_version="v1", database_path=translation_db
    )
    assert old is not None and old.translated_text == "Régi fordítás."


def test_store_different_policy_version_is_a_miss(translation_db: Path) -> None:
    store.save_translation(
        section_id="sec.1",
        source_fingerprint="fp",
        language="hu",
        policy_version="v1",
        translated_text="v1 fordítás.",
        database_path=translation_db,
    )
    assert store.get_translation(
        "sec.1", "fp", language="hu", policy_version="v2", database_path=translation_db
    ) is None


def test_store_fingerprint_is_deterministic_and_order_sensitive() -> None:
    fp1 = store.compute_source_fingerprint(["PART ONE", "PART TWO"])
    fp2 = store.compute_source_fingerprint(["PART ONE", "PART TWO"])
    fp3 = store.compute_source_fingerprint(["PART TWO", "PART ONE"])
    assert fp1 == fp2
    assert fp1 != fp3


# --- Policy: prompt/glossary ---------------------------------------------


def test_glossary_has_common_reformed_terms() -> None:
    for term in ("justification", "sanctification", "covenant", "atonement", "grace"):
        assert term in policy.HU_THEOLOGICAL_GLOSSARY
        assert policy.HU_THEOLOGICAL_GLOSSARY[term]


def test_prompt_contains_full_source_text_and_no_summarization_rule() -> None:
    prompt = policy.build_translation_prompt(
        section_text="PART ONE\n\nPART TWO",
        work_title="Test Work",
        contributors="Test Author (author)",
        passage_display="John.3.16-21",
    )
    assert "PART ONE" in prompt
    assert "PART TWO" in prompt
    assert "Ne foglald össze" in prompt
    assert "ne \"korrigáld\" teológiailag" in prompt or "korrigáld" in prompt
    assert "Test Work" in prompt
    assert "Test Author (author)" in prompt


def test_prompt_includes_glossary_terms() -> None:
    prompt = policy.build_translation_prompt(
        section_text="x", work_title="W", contributors="C", passage_display="P"
    )
    assert "justification → megigazulás" in prompt
    assert "covenant → szövetség" in prompt


# --- Service: cache miss -> generate -> save; cache hit -> no provider ---


def test_get_or_create_cache_miss_generates_and_saves(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    fake = _FakeGenerate()
    outcome = svc.get_or_create_translation(
        _HENRY_SECTION_ID,
        generate_fn=fake,
        provider_model="gemini-2.5-flash",
        repository=synthetic_repo,
        database_path=translation_db,
    )
    assert outcome.status == "generated"
    assert outcome.text == fake.response
    assert len(fake.calls) == 1

    cached = svc.get_translation(
        _HENRY_SECTION_ID, repository=synthetic_repo, database_path=translation_db
    )
    assert cached.status == "cached"
    assert cached.text == fake.response
    assert cached.provider_model == "gemini-2.5-flash"


def test_second_request_is_cache_hit_provider_never_called_again(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    fake = _FakeGenerate()
    first = svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake, repository=synthetic_repo, database_path=translation_db
    )
    assert first.status == "generated"
    assert len(fake.calls) == 1

    second = svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake, repository=synthetic_repo, database_path=translation_db
    )
    assert second.status == "cached"
    assert second.text == fake.response
    assert len(fake.calls) == 1  # NOT called again


def test_source_fingerprint_change_invalidates_cached_translation(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    fake = _FakeGenerate()
    svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake, repository=synthetic_repo, database_path=translation_db
    )
    assert len(fake.calls) == 1

    # Simulate the original section's content changing underneath the
    # cache: same section_id, different fingerprint (as if the corpus
    # were rebuilt/re-imported with edited text) -- MUST be a cache miss.
    stale = store.get_translation(
        _HENRY_SECTION_ID,
        "a-fingerprint-that-no-longer-matches",
        language="hu",
        policy_version=policy.TRANSLATION_POLICY_VERSION,
        database_path=translation_db,
    )
    assert stale is None

    fake2 = _FakeGenerate(response="ÚJ FORDÍTÁS")
    # get_or_create still hits the (still-valid) real fingerprint cache --
    # this proves the ORIGINAL entry stays a hit until its OWN fingerprint
    # actually changes; the invalidation semantics are exercised directly
    # above via the store, mirroring how a real corpus rebuild changes it.
    again = svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake2, repository=synthetic_repo, database_path=translation_db
    )
    assert again.status == "cached"
    assert len(fake2.calls) == 0


def test_policy_version_bump_requires_new_translation(
    synthetic_repo: CommentaryRepository, translation_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_v1 = _FakeGenerate(response="V1 FORDÍTÁS")
    svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake_v1, repository=synthetic_repo, database_path=translation_db
    )
    assert len(fake_v1.calls) == 1

    monkeypatch.setattr(svc, "TRANSLATION_POLICY_VERSION", "v2-test")
    fake_v2 = _FakeGenerate(response="V2 FORDÍTÁS")
    outcome = svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake_v2, repository=synthetic_repo, database_path=translation_db
    )
    assert outcome.status == "generated"
    assert outcome.text == "V2 FORDÍTÁS"
    assert len(fake_v2.calls) == 1  # new policy version forced a real regeneration


def test_provider_failure_string_is_never_cached(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    failing = _FakeGenerate(response="⚠️ **Hiányzó API kulcs.** Nincs beállítva Gemini API kulcs.")
    outcome = svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=failing, repository=synthetic_repo, database_path=translation_db
    )
    assert outcome.status == "provider_error"

    # Nothing was persisted -- a fresh lookup is still a plain cache miss,
    # never returning the warning string as if it were a real translation.
    still_missing = svc.get_translation(
        _HENRY_SECTION_ID, repository=synthetic_repo, database_path=translation_db
    )
    assert still_missing.status == "missing"
    assert not translation_db.is_file() or store.get_translation(
        _HENRY_SECTION_ID,
        store.compute_source_fingerprint(["x"]),
        language="hu",
        policy_version=policy.TRANSLATION_POLICY_VERSION,
        database_path=translation_db,
    ) is None


def test_empty_provider_response_is_treated_as_failure(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    outcome = svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=_FakeGenerate(response=""), repository=synthetic_repo,
        database_path=translation_db,
    )
    assert outcome.status == "provider_error"


def test_no_generate_fn_is_explicit_status_not_a_crash(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    outcome = svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=None, repository=synthetic_repo, database_path=translation_db
    )
    assert outcome.status == "no_generate_fn"


def test_translation_db_missing_or_corrupt_does_not_break_original_commentary(
    synthetic_repo: CommentaryRepository, tmp_path: Path
) -> None:
    corrupt_translation_db = tmp_path / "corrupt_translations.sqlite3"
    corrupt_translation_db.write_bytes(b"garbage, not sqlite")

    # Cache-only lookup against a corrupt store -> safe "missing", no raise.
    outcome = svc.get_translation(
        _HENRY_SECTION_ID, repository=synthetic_repo, database_path=corrupt_translation_db
    )
    assert outcome.status == "missing"

    # The ORIGINAL, retrieval-only Commentary repository is completely
    # unaffected -- it never even imports the translation store module.
    detail = synthetic_repo.section_detail(_HENRY_SECTION_ID)
    assert detail is not None
    assert [c.plain_text for c in detail.chunks] == [
        "SYNTH HENRY RANGE MARKER PART ONE",
        "SYNTH HENRY RANGE MARKER PART TWO",
    ]


def test_full_section_translates_not_just_first_chunk_preview(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    fake = _FakeGenerate()
    svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake, repository=synthetic_repo, database_path=translation_db
    )
    assert len(fake.calls) == 1
    prompt_sent = fake.calls[0][0]
    assert "SYNTH HENRY RANGE MARKER PART ONE" in prompt_sent
    assert "SYNTH HENRY RANGE MARKER PART TWO" in prompt_sent


def test_single_chunk_section_also_translates_fully(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    fake = _FakeGenerate()
    outcome = svc.get_or_create_translation(
        _JFB_SECTION_ID, generate_fn=fake, repository=synthetic_repo, database_path=translation_db
    )
    assert outcome.status == "generated"
    assert "SYNTH JFB EXACT MARKER" in fake.calls[0][0]


def test_unavailable_section_id_is_fail_closed(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    outcome = svc.get_or_create_translation(
        "no.such.section", generate_fn=_FakeGenerate(), repository=synthetic_repo,
        database_path=translation_db,
    )
    assert outcome.status == "unavailable"


def test_generate_fn_called_with_dedicated_tab_label(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    fake = _FakeGenerate()
    svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake, repository=synthetic_repo, database_path=translation_db
    )
    _, kwargs = fake.calls[0]
    assert kwargs["tab_label"] == svc.TRANSLATION_TAB_LABEL
    assert kwargs["use_cache"] is False  # generate_text's own cache never fronts this cache


def test_bypass_cooldown_defaults_to_false_and_forwards_to_generate_fn(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    """Real bug found via manual smoke test (2026-09-03, Róm 8,1-4): a
    caller that translates SEVERAL sections from one button click (ld.
    commentary_ui._translate_missing_sections) must be able to bypass
    app.py's own inter-call cooldown for every call after the first, or
    every call but the first fails as a false "provider unavailable"."""
    fake = _FakeGenerate()
    svc.get_or_create_translation(
        _HENRY_SECTION_ID, generate_fn=fake, repository=synthetic_repo, database_path=translation_db
    )
    _, kwargs = fake.calls[0]
    assert kwargs["bypass_cooldown"] is False  # unset -> real cooldown protection intact

    fake2 = _FakeGenerate()
    svc.get_or_create_translation(
        _JFB_SECTION_ID,
        generate_fn=fake2,
        repository=synthetic_repo,
        database_path=translation_db,
        bypass_cooldown=True,
    )
    _, kwargs2 = fake2.calls[0]
    assert kwargs2["bypass_cooldown"] is True


# --- Provenance ------------------------------------------------------------


def test_translation_outcome_carries_traceable_metadata(
    synthetic_repo: CommentaryRepository, translation_db: Path
) -> None:
    outcome = svc.get_or_create_translation(
        _HENRY_SECTION_ID,
        generate_fn=_FakeGenerate(),
        provider_model="gemini-2.5-flash",
        repository=synthetic_repo,
        database_path=translation_db,
    )
    assert outcome.provider_model == "gemini-2.5-flash"
    assert outcome.created_at  # non-empty timestamp
    # section_id itself is the traceability key back to the original
    # section -> work -> edition -> upstream source, already exposed by
    # CommentaryRepository.section_detail (work_title/edition_id/
    # contributors/source_url/external_id) -- unchanged by this module.
    detail = synthetic_repo.section_detail(_HENRY_SECTION_ID)
    assert detail is not None
    assert detail.work_title == "Test Henry Commentary on John"


# --- Regression: dedicated output-token budget (mirrors the compare-tab
# regression added for the same class of bug in 660195f) -----------------


def test_translation_tab_has_a_dedicated_output_token_budget() -> None:
    import app

    label = svc.TRANSLATION_TAB_LABEL
    assert label in app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB
    budget = app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB[label]
    generic_fallback = 4096
    assert budget > generic_fallback * 2
    assert app._default_max_output_tokens(label) == budget
    service_src = Path("commentary_translation_service.py").read_text(encoding="utf-8")
    assert f'tab_label=TRANSLATION_TAB_LABEL' in service_src
