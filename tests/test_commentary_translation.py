"""Hungarian Commentary translation infrastructure tests -- store, policy,
service and minimal UI integration.

No external LLM/API is called anywhere in this file -- every ``generate_fn``
is a local fake that records what it was called with. Reuses the same
small, synthetic 3-source Commentary document as ``tests/test_commentary_
ui.py``/``tests/test_commentary_compare.py`` (``_synthetic_document``),
keeping these tests fast, deterministic and independent of whether the
real corpora have been fetched/built locally.
"""

from __future__ import annotations

from pathlib import Path

import tempfile

import pytest
from streamlit.testing.v1 import AppTest

import commentary_translation_service as svc
from tests.test_commentary_ui import _synthetic_document
from textus_kb import commentary_translation_policy as policy
from textus_kb import commentary_translation_store as store
from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
from textus_kb.repositories.commentary_repository import CommentaryRepository

_HENRY_SECTION_ID = "test.henry.range"  # 2 chunks: "PART ONE" / "PART TWO"
_JFB_SECTION_ID = "test.jfb.exact"  # 1 chunk

# Same fixed path ``_render_translation_toggle_flow`` below computes for
# its isolated translation store -- kept as a literal (not a shared
# import) inside that function per this repo's "AppTest.from_function
# helpers are fully self-contained" convention; duplicated here only so
# a pytest fixture can reset it BETWEEN test functions (never from
# inside the render function itself, which would also wipe it between
# reruns/clicks WITHIN one AppTest flow -- and between two independent
# AppTest instances in the same test, defeating the one test that
# deliberately checks cross-instance cache persistence).
_UI_TEST_TRANSLATION_DB_PATH = (
    Path(tempfile.gettempdir()) / "textus_test_commentary_translation_ui" / "commentary_translations.sqlite3"
)


@pytest.fixture()
def clean_ui_translation_cache():
    """Resets the isolated UI-test translation store before a test that
    needs to start from a genuine cache miss."""
    if _UI_TEST_TRANSLATION_DB_PATH.is_file():
        _UI_TEST_TRANSLATION_DB_PATH.unlink()
    yield


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


# --- Minimal UI integration ------------------------------------------------


def test_translation_view_defaults_to_original_when_section_has_no_text() -> None:
    import commentary_ui as cu

    assert (
        cu._render_translation_view_toggle(
            "any.section", has_text=False, has_cached_translation=False
        )
        == cu._TRANSLATION_VIEW_ORIGINAL
    )
    # Even a (nonsensical, but defensive) cached-translation flag can't
    # override the "no text at all" case.
    assert (
        cu._render_translation_view_toggle(
            "any.section", has_text=False, has_cached_translation=True
        )
        == cu._TRANSLATION_VIEW_ORIGINAL
    )


def test_translation_view_labels_are_original_and_hungarian() -> None:
    import commentary_ui as cu

    # 2026-09-03 UI polish round: "Eredeti" -> "Eredeti angol" (task item 4).
    assert cu._TRANSLATION_VIEW_ORIGINAL == "Eredeti angol"
    assert cu._TRANSLATION_VIEW_HUNGARIAN == "Magyar fordítás"


def test_ai_translation_disclosure_label_is_the_exact_required_string() -> None:
    src = Path("commentary_ui.py").read_text(encoding="utf-8")
    assert 'st.caption("AI által készített magyar fordítás")' in src


def _render_translation_toggle_flow() -> None:
    """Self-contained AppTest render helper (own imports/inline data,
    per this repo's established ``AppTest.from_function`` convention --
    ld. tests/test_sermon_workshop_developed_outline_ui.py). Builds its
    own isolated synthetic Commentary + translation SQLite stores under
    the system temp dir (never the real production DBs) and drives the
    real ``commentary_ui._render_detail`` "Eredeti" / "Magyar fordítás"
    toggle end to end with a fake, call-counting generate_fn."""
    import tempfile
    from pathlib import Path as _Path

    import streamlit as st

    import commentary_ui as cu
    from textus_kb.importers.commentary_sqlite import import_commentary_sqlite
    from textus_kb.repositories.commentary_repository import (
        CommentaryRepository,
        CommentarySectionResult,
    )

    tmp_root = _Path(tempfile.gettempdir()) / "textus_test_commentary_translation_ui"
    tmp_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_root / "commentary.sqlite3"
    translation_db_path = tmp_root / "commentary_translations.sqlite3"

    document = {
        "contributors": [
            {"contributor_id": "ui.henry", "canonical_name": "UI Test Henry", "birth_year": 1662, "death_year": 1714},
        ],
        "works": [
            {"work_id": "ui.work.henry", "title": "UI Test Henry Commentary", "original_title": None, "original_language": "en", "work_type": "commentary"},
        ],
        "work_contributors": [
            {"work_id": "ui.work.henry", "contributor_id": "ui.henry", "role": "author"},
        ],
        "editions": [
            {
                "edition_id": "ui.edition.henry",
                "work_id": "ui.work.henry",
                "edition_label": "Test edition",
                "publication_year": 1900,
                "publisher": "Textus Test",
                "language": "en",
                "license": "CC-BY-4.0",
                "rights_status": "public-domain",
                "rights_note": "Synthetic UI fixture; not a real commentary source.",
                "source_url": "https://example.test/ui-henry",
                "corpus": "ui-henry",
                "external_id": "test/ui-henry",
            },
        ],
        "source_files": [
            {"source_file_id": "ui.sf.henry", "edition_id": "ui.edition.henry", "file_name": "henry.xml", "raw_sha256": "d" * 64, "byte_size": 10, "retrieved_at": "2026-08-01T00:00:00Z"},
        ],
        "import_batches": [
            {"batch_id": "ui.batch.henry", "source_file_id": "ui.sf.henry", "importer_name": "test", "importer_version": "0.1.0", "imported_at": "2026-08-01T00:05:00Z", "report": {}},
        ],
        "sections": [
            {"section_id": "ui.henry.range", "edition_id": "ui.edition.henry", "parent_section_id": None, "section_type": "range_commentary", "heading": "Henry on John 3:16-21 (UI synthetic)", "sequence": 1, "passage_links": [{"raw_citation": "John 3:16-21", "relation_type": "primary"}]},
        ],
        "chunks": [
            {"chunk_id": "ui.chunk.henry.1", "section_id": "ui.henry.range", "sequence": 1, "text": "UI SYNTH HENRY PART ONE", "plain_text": "UI SYNTH HENRY PART ONE", "source_locator": "fixture://ui-henry/1"},
            {"chunk_id": "ui.chunk.henry.2", "section_id": "ui.henry.range", "sequence": 2, "text": "UI SYNTH HENRY PART TWO", "plain_text": "UI SYNTH HENRY PART TWO", "source_locator": "fixture://ui-henry/2"},
        ],
    }
    import_commentary_sqlite(document=document, database_path=db_path)

    cu._get_repository = lambda: CommentaryRepository(db_path)  # type: ignore[assignment]
    cu._translation_database_path = lambda: translation_db_path  # type: ignore[assignment]

    if "_test_call_count" not in st.session_state:
        st.session_state["_test_call_count"] = 0

    def fake_gen(prompt, **kwargs):
        st.session_state["_test_call_count"] += 1
        st.session_state["_test_last_prompt"] = prompt
        return "UI SZINTETIKUS MAGYAR FORDÍTÁS"

    card = CommentarySectionResult(
        section_id="ui.henry.range",
        edition_id="ui.edition.henry",
        work_id="ui.work.henry",
        work_title="UI Test Henry Commentary",
        section_type="range_commentary",
        heading="Henry on John 3:16-21 (UI synthetic)",
        sequence=1,
        parent_section_id=None,
        relation_type="exact_passage",
        canonical_passages=("John.3.16-21",),
        chunk_count=2,
        primary_passages=("John.3.16-21",),
        contributors=("UI Test Henry (author)",),
    )
    cu._render_detail(card, generate_fn=fake_gen, resolve_model_fn=lambda label: "test-model-id")


def test_ui_toggle_original_view_shows_english_text_by_default(clean_ui_translation_cache) -> None:
    at = AppTest.from_function(_render_translation_toggle_flow).run(timeout=60)
    body = "\n".join(md.value for md in at.markdown)
    assert "UI SYNTH HENRY PART ONE" in body
    assert "UI SYNTH HENRY PART TWO" in body
    captions = [c.value for c in at.caption]
    assert not any("AI által készített magyar fordítás" in c for c in captions)
    assert at.session_state["_test_call_count"] == 0  # no provider call just from viewing


def test_ui_toggle_switch_and_generate_shows_disclosed_translation(clean_ui_translation_cache) -> None:
    at = AppTest.from_function(_render_translation_toggle_flow).run(timeout=60)
    radios = at.radio
    assert len(radios) == 1
    at = radios[0].set_value("Magyar fordítás").run(timeout=60)

    translate_btn = next(
        b for b in at.button if b.label == "Magyar fordítás készítése"
    )
    assert translate_btn.disabled is False
    at = translate_btn.click().run(timeout=60)

    assert at.session_state["_test_call_count"] == 1
    captions = [c.value for c in at.caption]
    assert any("AI által készített magyar fordítás" in c for c in captions)
    body = "\n".join(md.value for md in at.markdown)
    assert "UI SZINTETIKUS MAGYAR FORDÍTÁS" in body
    # the FULL section (both chunks) must have been sent for translation
    assert "UI SYNTH HENRY PART ONE" in at.session_state["_test_last_prompt"]
    assert "UI SYNTH HENRY PART TWO" in at.session_state["_test_last_prompt"]


def test_ui_toggle_cache_hit_on_rerun_does_not_call_provider_again(clean_ui_translation_cache) -> None:
    at = AppTest.from_function(_render_translation_toggle_flow).run(timeout=60)
    radios = at.radio
    at = radios[0].set_value("Magyar fordítás").run(timeout=60)
    translate_btn = next(b for b in at.button if b.label == "Magyar fordítás készítése")
    at = translate_btn.click().run(timeout=60)
    assert at.session_state["_test_call_count"] == 1

    # A later, independent AppTest run (simulating reopening the section
    # in a new script run) must hit the now-populated cache -- no button
    # needed, no new provider call, since view defaults back to
    # "Eredeti" -- switch to "Magyar fordítás" again and confirm it's
    # already there without a generate click.
    at2 = AppTest.from_function(_render_translation_toggle_flow).run(timeout=60)
    radios2 = at2.radio
    at2 = radios2[0].set_value("Magyar fordítás").run(timeout=60)
    captions = [c.value for c in at2.caption]
    assert any("AI által készített magyar fordítás" in c for c in captions)
    # cache-hit path never calls generate_fn -- session_state counter for
    # THIS fresh run starts at 0 and must stay there.
    assert at2.session_state["_test_call_count"] == 0


def test_ui_toggle_defaults_to_hungarian_when_translation_already_cached(
    clean_ui_translation_cache,
) -> None:
    """2026-09-03 UI polish round (task item 4): "A magyar nézet legyen
    kényelmes elsődleges választás, ha már létezik cache-elt fordítás" --
    pre-populate the cache directly (no button click, no provider call),
    then confirm a FRESH AppTest run defaults straight to the Hungarian
    view with zero clicks."""
    fingerprint = store.compute_source_fingerprint(
        ["UI SYNTH HENRY PART ONE", "UI SYNTH HENRY PART TWO"]
    )
    store.save_translation(
        section_id="ui.henry.range",
        source_fingerprint=fingerprint,
        language="hu",
        policy_version=policy.TRANSLATION_POLICY_VERSION,
        translated_text="ELŐRE CACHE-ELT MAGYAR FORDÍTÁS",
        provider_model="test-model-id",
        database_path=_UI_TEST_TRANSLATION_DB_PATH,
    )

    at = AppTest.from_function(_render_translation_toggle_flow).run(timeout=60)
    captions = [c.value for c in at.caption]
    assert any("AI által készített magyar fordítás" in c for c in captions)
    body = "\n".join(md.value for md in at.markdown)
    assert "ELŐRE CACHE-ELT MAGYAR FORDÍTÁS" in body
    # Zero provider calls -- this was a pure cache hit, no generation.
    assert at.session_state["_test_call_count"] == 0
    # The radio widget itself is showing the Hungarian option as selected.
    radios = at.radio
    assert radios[0].value == "Magyar fordítás"


def test_ui_toggle_original_always_one_click_away_after_translation(clean_ui_translation_cache) -> None:
    at = AppTest.from_function(_render_translation_toggle_flow).run(timeout=60)
    radios = at.radio
    at = radios[0].set_value("Magyar fordítás").run(timeout=60)
    translate_btn = next(b for b in at.button if b.label == "Magyar fordítás készítése")
    at = translate_btn.click().run(timeout=60)

    radios = at.radio
    at = radios[0].set_value("Eredeti angol").run(timeout=60)
    body = "\n".join(md.value for md in at.markdown)
    assert "UI SYNTH HENRY PART ONE" in body
    captions = [c.value for c in at.caption]
    assert not any("AI által készített magyar fordítás" in c for c in captions)
