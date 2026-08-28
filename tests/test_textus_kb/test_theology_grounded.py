"""Phase D3C: grounded Theology mapping, flags, runtime ensure, prompt/citation."""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.adapters.theology import THEOLOGY_SOURCE_ID
from textus_kb.context_builder import ContextItem, ContextSection, LLMContextPacket
from textus_kb.context_profiles import (
    PROFILE_EXEGESIS,
    PROFILE_HISTORICAL,
    PROFILE_THEOLOGY,
    THEOLOGY_NO_MATCH_WARNING,
)
from textus_kb.evidence import EvidencePacket
from textus_kb.importers.theology_sqlite import import_theology_sqlite
from textus_kb.retrieval import retrieve
from textus_kb.grounded_generation import (
    GROUNDED_FLAG,
    REASON_RETRIEVAL_ERROR,
    REASON_SOURCE_UNAVAILABLE,
    STATUS_DISABLED,
    STATUS_FALLBACK,
    STATUS_USED,
    is_grounded_enabled,
    is_grounded_injection_allowed,
    prepare_grounded_provider_prompt,
    resolve_grounded_module,
)
from textus_kb.prompt_composer import (
    DEFAULT_KB_CONTEXT_MAX_BY_MODULE,
    DEFAULT_KB_CONTEXT_TARGET_BY_MODULE,
    DRY_RUN_PRODUCTION_STUB,
    _SECTION_HEADERS,
    _SOURCE_DISPLAY_LABELS,
    _SUPPORTED_MODULES,
    _TRIM_SECTION_ORDER,
    compose_grounded_prompt,
    render_kb_context,
)
from textus_kb.shadow import MODULE_TO_PROFILE
from textus_kb.shadow_integration import run_production_with_optional_shadow
from textus_kb.theology_runtime import TheologyRuntimeStatus


PRODUCTION = "PRODUCTION-THEOLOGY-PROMPT"


def _noop_shadow(**kwargs):
    return {"status": "success", "success": True, "reused": False}


def _fake_generate_factory(calls: list[dict]):
    def fake_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(
            {
                "prompt": prompt,
                "enable_google_search": enable_google_search,
                "tab_label": tab_label,
            }
        )
        return "LLM-OUT"

    return fake_generate


def _status(*, available: bool, reason: str = "ok", path: str = "C:/tmp/theology.sqlite3"):
    return TheologyRuntimeStatus(
        available=available,
        reason=reason if not available else "ok",
        database_path=path,
        detail="" if available else reason,
    )


def _evidence(canonical: str = "John.4.1-42") -> EvidencePacket:
    return EvidencePacket(
        passage_canonical=canonical,
        passage_display="Jn 4,1–42",
        build_id="test-d3c",
        manifest_version="test",
    )


def _theology_item(**meta_overrides: object) -> ContextItem:
    metadata = {
        "author_name": "John Calvin",
        "work_title": "The Institutes of the Christian Religion",
        "human_readable_locator": (
            "John Calvin, The Institutes of the Christian Religion, "
            "Book II, Chapter 12, Section 4"
        ),
        "source_locator": "ccel:calvin/institutes#ii.xii-p4",
        "translator": "Henry Beveridge",
        "publication_year": 1845,
        "canonical_passages": ["John.3.16"],
        "canonical_scope": "John.3.16",
    }
    metadata.update({key: value for key, value in meta_overrides.items()})
    metadata = {key: value for key, value in metadata.items() if value is not None}
    return ContextItem(
        text="SYNTHETIC theology evidence body.",
        evidence_id="EV-THEO-chunk.ii.xii-p4",
        source_id=THEOLOGY_SOURCE_ID,
        relevance_score=90,
        item_type="theological_source",
        metadata=metadata,
    )


def _packet_with_items(
    *items: ContextItem,
    warnings: list[str] | None = None,
    profile: str = PROFILE_THEOLOGY,
    section_type: str | None = None,
) -> LLMContextPacket:
    if section_type is None:
        section_type = "theological" if any(
            item.item_type == "theological_source" for item in items
        ) else "dictionary"
    return LLMContextPacket(
        passage="John.3.16",
        passage_display="Jn 3,16",
        profile=profile,
        sections=[ContextSection(type=section_type, items=tuple(items))],
        source_ids=sorted({item.source_id for item in items}),
        evidence_ids=[item.evidence_id for item in items],
        warnings=list(warnings or []),
        schema_version="2",
        evidence_packet_build_id="test-d3c",
    )


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def test_resolve_grounded_module_theology() -> None:
    assert resolve_grounded_module("theology") == "theology"
    assert resolve_grounded_module("exegesis") == "exegesis"
    assert resolve_grounded_module("history") == "historical_context"
    assert resolve_grounded_module("illustrations") is None
    assert resolve_grounded_module("overview") is None
    assert resolve_grounded_module("actualization") is None


def test_module_to_profile_theology() -> None:
    assert MODULE_TO_PROFILE["theology"] == PROFILE_THEOLOGY
    assert MODULE_TO_PROFILE["exegesis"] == PROFILE_EXEGESIS
    assert MODULE_TO_PROFILE["history"] == PROFILE_HISTORICAL
    assert MODULE_TO_PROFILE["historical_context"] == PROFILE_HISTORICAL


def test_prompt_composer_supports_theology() -> None:
    assert "theology" in _SUPPORTED_MODULES
    assert "exegesis" in _SUPPORTED_MODULES
    assert "historical_context" in _SUPPORTED_MODULES
    assert "illustrations" not in _SUPPORTED_MODULES
    assert _SECTION_HEADERS["theological"] == "THEOLOGICAL SOURCES"
    assert _SOURCE_DISPLAY_LABELS["theology_sqlite"] == "Theology store"
    assert "theological" in _TRIM_SECTION_ORDER
    assert DEFAULT_KB_CONTEXT_TARGET_BY_MODULE["theology"] == 3500
    assert DEFAULT_KB_CONTEXT_MAX_BY_MODULE["theology"] == 3500
    assert DEFAULT_KB_CONTEXT_TARGET_BY_MODULE["exegesis"] == 2500
    assert DEFAULT_KB_CONTEXT_MAX_BY_MODULE["exegesis"] == 4500
    assert DEFAULT_KB_CONTEXT_TARGET_BY_MODULE["historical_context"] == 2200
    assert DEFAULT_KB_CONTEXT_MAX_BY_MODULE["historical_context"] == 3500


def test_composer_compose_theology_succeeds() -> None:
    packet = _packet_with_items(_theology_item())
    preview = compose_grounded_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        canonical_passage="John.3.16",
        module="theology",
        context_packet=packet,
    )
    assert preview.success is True
    assert preview.module == "theology"
    assert preview.kb_context_target_tokens == 3500
    assert preview.kb_context_max_tokens == 3500
    assert "THEOLOGY GROUNDED USE RULES" in preview.composed_prompt
    assert "THEOLOGICAL SOURCES" in preview.composed_prompt
    assert "Only name a theologian, work, confession, catechism, translator," in (
        preview.composed_prompt
    )
    assert "Do not invent page numbers." in preview.composed_prompt
    assert "Never imply that the current corpus represents all Protestant," in (
        preview.composed_prompt
    )


def test_composer_still_rejects_unsupported_modules() -> None:
    packet = _packet_with_items(_theology_item())
    preview = compose_grounded_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        canonical_passage="John.3.16",
        module="illustrations",
        context_packet=packet,
    )
    assert preview.success is False
    assert "Unsupported module" in preview.error


# ---------------------------------------------------------------------------
# Flags / default-on kill switch
# ---------------------------------------------------------------------------

_STAGE_ENV = "TEXTUS_KB_GROUNDED_STAGE_ALLOWED"


def _clear_grounded_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GROUNDED_FLAG, raising=False)
    monkeypatch.delenv(_STAGE_ENV, raising=False)


def test_grounded_flag_default_on_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_grounded_env(monkeypatch)
    assert is_grounded_enabled() is True
    assert is_grounded_injection_allowed() is True

    gen_src = Path("textus_kb/grounded_generation.py").read_text(encoding="utf-8")
    assert "STAGE_ALLOWED_FLAG" not in gen_src
    assert "TEXTUS_KB_GROUNDED_STAGE_ALLOWED" not in gen_src
    assert "is_stage_allowed" not in gen_src
    assert "REASON_STAGE_NOT_ALLOWED" not in gen_src
    assert "enforce_stage_gate" not in gen_src
    app_src = Path("app.py").read_text(encoding="utf-8")
    assert "grounded_enabled=_is_kb_grounded_injection_allowed()" in app_src
    assert 'os.getenv(KB_SHADOW_FLAG, "false")' in app_src
    assert "TEXTUS_KB_GROUNDED_STAGE_ALLOWED" not in app_src


def test_grounded_flag_explicit_true(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("true", "1", "yes", "on"):
        monkeypatch.setenv(GROUNDED_FLAG, value)
        assert is_grounded_enabled() is True
        assert is_grounded_injection_allowed() is True


def test_grounded_flag_explicit_false(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("false", "0", "no", "off"):
        monkeypatch.setenv(GROUNDED_FLAG, value)
        assert is_grounded_enabled() is False
        assert is_grounded_injection_allowed() is False


def test_stage_env_has_no_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GROUNDED_FLAG, raising=False)
    monkeypatch.setenv(_STAGE_ENV, "false")
    assert is_grounded_enabled() is True
    assert is_grounded_injection_allowed() is True
    monkeypatch.setenv(_STAGE_ENV, "true")
    assert is_grounded_injection_allowed() is True
    monkeypatch.setenv(GROUNDED_FLAG, "false")
    monkeypatch.setenv(_STAGE_ENV, "true")
    assert is_grounded_injection_allowed() is False


def test_grounded_off_uses_production_prompt_and_skips_ensure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_calls: list[str] = []

    def _ensure(**kwargs):
        ensure_calls.append("called")
        return _status(available=True)

    monkeypatch.setattr("textus_kb.theology_runtime.ensure_theology_database", _ensure)
    retrieve_calls = {"n": 0}

    def counting_retrieve(ref):
        retrieve_calls["n"] += 1
        raise AssertionError("should not retrieve")

    monkeypatch.setattr("textus_kb.retrieval.retrieve", counting_retrieve)
    calls: list[dict] = []
    result = run_production_with_optional_shadow(
        key="theology",
        prompt=PRODUCTION,
        tab_label="Teológia",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=False,
        generate_text_fn=_fake_generate_factory(calls),
        shadow_runner_fn=_noop_shadow,
    )
    assert ensure_calls == []
    assert retrieve_calls["n"] == 0
    assert len(calls) == 1
    assert calls[0]["prompt"] == PRODUCTION
    assert result.provider_call_count == 1
    assert result.provider_prompt_kind == "production"
    assert result.grounded_event["grounded_status"] == STATUS_DISABLED

    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Jn 4,1-42",
        module="theology",
        grounded_enabled=False,
    )
    assert ensure_calls == []
    assert prep.provider_prompt == PRODUCTION
    assert prep.grounded_disabled is True
    assert "<<<BEGIN_KB_DATA>>>" not in prep.provider_prompt


def test_kill_switch_env_false_skips_ensure_and_uses_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GROUNDED_FLAG, "false")
    monkeypatch.delenv(_STAGE_ENV, raising=False)
    ensure_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called") or _status(available=True),
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Jn 4,1-42",
        module="theology",
    )
    assert ensure_calls == []
    assert prep.provider_prompt == PRODUCTION
    assert prep.grounded_disabled is True
    assert "<<<BEGIN_KB_DATA>>>" not in prep.provider_prompt


def test_shadow_flag_off_does_not_run_theology_shadow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shadow_calls: list[dict] = []

    def counting_shadow(**kwargs):
        shadow_calls.append(kwargs)
        return {"status": "success", "success": True}

    calls: list[dict] = []
    result = run_production_with_optional_shadow(
        key="theology",
        prompt=PRODUCTION,
        tab_label="Teológia",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=False,
        generate_text_fn=_fake_generate_factory(calls),
        shadow_runner_fn=counting_shadow,
    )
    assert shadow_calls == []
    assert result.shadow_event is None
    assert len(calls) == 1


def test_theology_auto_grounded_when_env_unset_and_db_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textus_kb.kb_cache import clear_kb_cache

    clear_kb_cache()
    _clear_grounded_env(monkeypatch)
    ensure_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called")
        or _status(available=True, path="C:/tmp/valid-theology.sqlite3"),
    )
    monkeypatch.setattr("textus_kb.retrieval.retrieve", lambda ref: _evidence())
    monkeypatch.setattr(
        "textus_kb.context_builder.build_context_from_evidence",
        lambda evidence, profile, theology_database_path=None: _packet_with_items(
            _theology_item()
        ),
    )
    calls: list[dict] = []
    result = run_production_with_optional_shadow(
        key="theology",
        prompt=PRODUCTION,
        tab_label="Teológia",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=is_grounded_injection_allowed(),
        generate_text_fn=_fake_generate_factory(calls),
        shadow_runner_fn=_noop_shadow,
    )
    assert is_grounded_injection_allowed() is True
    assert ensure_calls == ["called"]
    assert len(calls) == 1
    assert result.provider_call_count == 1
    assert result.provider_prompt_kind == "grounded"
    assert result.grounded_event["grounded_used"] is True
    assert result.grounded_event["grounded_status"] == STATUS_USED
    assert "<<<BEGIN_KB_DATA>>>" in calls[0]["prompt"]
    assert "[THEOLOGICAL SOURCES]" in calls[0]["prompt"]

    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Jn 4,1-42",
        module="theology",
        use_cache=False,
    )
    assert prep.grounded_used is True
    assert "[THEOLOGICAL SOURCES]" in prep.provider_prompt


def test_theology_auto_fallback_when_env_unset_and_db_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textus_kb.kb_cache import clear_kb_cache

    clear_kb_cache()
    _clear_grounded_env(monkeypatch)
    ensure_calls: list[str] = []
    retrieve_calls = {"n": 0}

    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called")
        or _status(available=False, reason="storage_not_configured"),
    )

    def counting_retrieve(ref):
        retrieve_calls["n"] += 1
        raise AssertionError("invalid store must not retrieve")

    monkeypatch.setattr("textus_kb.retrieval.retrieve", counting_retrieve)
    calls: list[dict] = []
    result = run_production_with_optional_shadow(
        key="theology",
        prompt=PRODUCTION,
        tab_label="Teológia",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=is_grounded_injection_allowed(),
        generate_text_fn=_fake_generate_factory(calls),
        shadow_runner_fn=_noop_shadow,
    )
    assert ensure_calls == ["called"]
    assert retrieve_calls["n"] == 0
    assert len(calls) == 1
    assert calls[0]["prompt"] == PRODUCTION
    assert "<<<BEGIN_KB_DATA>>>" not in calls[0]["prompt"]
    assert result.provider_call_count == 1
    assert result.provider_prompt_kind == "production"
    assert result.grounded_event["grounded_status"] == STATUS_FALLBACK
    assert result.grounded_event["fallback_reason"] == REASON_SOURCE_UNAVAILABLE


@pytest.mark.parametrize(
    ("key", "module", "tab_label", "prompt"),
    [
        ("theology", "theology", "Teológia", PRODUCTION),
        ("exegesis", "exegesis", "Exegézis", "PROD-EXEGESIS"),
        ("history", "historical_context", "Kortörténet", "PROD-HISTORY"),
    ],
)
def test_kill_switch_disables_all_mapped_modules(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    module: str,
    tab_label: str,
    prompt: str,
) -> None:
    monkeypatch.setenv(GROUNDED_FLAG, "false")
    ensure_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called") or _status(available=True),
    )
    retrieve_calls = {"n": 0}

    def counting_retrieve(ref):
        retrieve_calls["n"] += 1
        raise AssertionError("kill switch must not retrieve")

    monkeypatch.setattr("textus_kb.retrieval.retrieve", counting_retrieve)
    calls: list[dict] = []
    result = run_production_with_optional_shadow(
        key=key,
        prompt=prompt,
        tab_label=tab_label,
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=is_grounded_injection_allowed(),
        generate_text_fn=_fake_generate_factory(calls),
        shadow_runner_fn=_noop_shadow,
    )
    assert is_grounded_injection_allowed() is False
    assert ensure_calls == []
    assert retrieve_calls["n"] == 0
    assert len(calls) == 1
    assert calls[0]["prompt"] == prompt
    assert result.provider_prompt_kind == "production"
    assert result.grounded_event["grounded_status"] == STATUS_DISABLED

    prep = prepare_grounded_provider_prompt(
        production_prompt=prompt,
        passage="Jn 4,1-42",
        module=module,
    )
    assert prep.grounded_disabled is True
    assert prep.provider_prompt == prompt


@pytest.mark.parametrize("module", ["exegesis", "historical_context"])
def test_non_theology_modules_do_not_ensure_theology_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
    module: str,
) -> None:
    _clear_grounded_env(monkeypatch)
    ensure_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called") or _status(available=True),
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt="PROD-MAPPED",
        passage="Jn 4,1-42" if module == "exegesis" else "Lk 10,25-37",
        module=module,
        use_cache=False,
    )
    assert ensure_calls == []
    assert prep.grounded_disabled is False
    assert prep.grounded_used is True or prep.grounded_fallback is True
    if prep.grounded_used:
        assert "<<<BEGIN_KB_DATA>>>" in prep.provider_prompt


# ---------------------------------------------------------------------------
# Runtime ensure
# ---------------------------------------------------------------------------


def test_ensure_available_starts_context_build(monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_calls: list[str] = []
    build_calls: list[dict] = []
    retrieve_calls = {"n": 0}

    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called")
        or _status(available=True, path="C:/tmp/valid-theology.sqlite3"),
    )

    def fake_retrieve(ref):
        retrieve_calls["n"] += 1
        return _evidence()

    def fake_build(evidence, profile, theology_database_path=None):
        build_calls.append(
            {"profile": profile, "path": theology_database_path}
        )
        return _packet_with_items(_theology_item())

    monkeypatch.setattr("textus_kb.retrieval.retrieve", fake_retrieve)
    monkeypatch.setattr(
        "textus_kb.context_builder.build_context_from_evidence", fake_build
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Jn 4,1-42",
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert ensure_calls == ["called"]
    assert retrieve_calls["n"] == 1
    assert build_calls
    assert build_calls[0]["profile"] == PROFILE_THEOLOGY
    assert build_calls[0]["path"] == "C:/tmp/valid-theology.sqlite3"
    assert prep.status == STATUS_USED
    assert prep.grounded_used is True
    assert prep.provider_prompt != PRODUCTION
    assert "<<<BEGIN_KB_DATA>>>" in prep.provider_prompt
    assert "John Calvin" in prep.provider_prompt
    assert "THEOLOGY GROUNDED USE RULES" in prep.provider_prompt


def test_ensure_unavailable_hard_fallback_no_partial_grounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_calls: list[str] = []
    retrieve_calls = {"n": 0}
    build_calls = {"n": 0}

    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called")
        or _status(available=False, reason="storage_not_configured"),
    )

    def counting_retrieve(ref):
        retrieve_calls["n"] += 1
        raise AssertionError("invalid store must not retrieve")

    def counting_build(*args, **kwargs):
        build_calls["n"] += 1
        raise AssertionError("invalid store must not build context")

    monkeypatch.setattr("textus_kb.retrieval.retrieve", counting_retrieve)
    monkeypatch.setattr(
        "textus_kb.context_builder.build_context_from_evidence", counting_build
    )
    calls: list[dict] = []
    result = run_production_with_optional_shadow(
        key="theology",
        prompt=PRODUCTION,
        tab_label="Teológia",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        grounded_enabled=True,
        generate_text_fn=_fake_generate_factory(calls),
        shadow_runner_fn=_noop_shadow,
    )
    assert ensure_calls == ["called"]
    assert retrieve_calls["n"] == 0
    assert build_calls["n"] == 0
    assert len(calls) == 1
    assert calls[0]["prompt"] == PRODUCTION
    assert "<<<BEGIN_KB_DATA>>>" not in calls[0]["prompt"]
    assert result.provider_call_count == 1
    assert result.provider_prompt_kind == "production"
    assert result.grounded_event["grounded_status"] == STATUS_FALLBACK
    assert result.grounded_event["fallback_reason"] == REASON_SOURCE_UNAVAILABLE


def test_valid_store_no_theology_match_stays_grounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: _status(available=True),
    )
    monkeypatch.setattr("textus_kb.retrieval.retrieve", lambda ref: _evidence())
    background = ContextItem(
        text="Dictionary background without theology.",
        evidence_id="ev-dict-1",
        source_id="aquifer_open_bible_dictionary",
        relevance_score=8,
        item_type="dictionary_background",
        metadata={"canonical_scope": "Obad.1.1"},
    )

    def fake_build(evidence, profile, theology_database_path=None):
        return _packet_with_items(
            background,
            warnings=[THEOLOGY_NO_MATCH_WARNING],
            section_type="dictionary",
        )

    monkeypatch.setattr(
        "textus_kb.context_builder.build_context_from_evidence", fake_build
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage="Obad.1.1",
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert prep.grounded_used is True
    assert prep.provider_prompt != PRODUCTION
    assert THEOLOGY_NO_MATCH_WARNING in prep.provider_prompt
    assert "author_name=" not in prep.provider_prompt
    assert "John Calvin" not in prep.provider_prompt


def test_ensure_only_on_theology_grounded_path(monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called") or _status(available=True),
    )
    monkeypatch.setattr("textus_kb.retrieval.retrieve", lambda ref: _evidence())
    monkeypatch.setattr(
        "textus_kb.context_builder.build_context_from_evidence",
        lambda evidence, profile, theology_database_path=None: _packet_with_items(
            ContextItem(
                text="exegetical note",
                evidence_id="ev-1",
                source_id="aquifer_open_study_notes",
                relevance_score=9,
                item_type="exegetical_note",
                metadata={"canonical_scope": "John.4.1-42"},
            ),
            section_type="exegetical",
        ),
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt="EXEGESIS",
        passage="Jn 4,1-42",
        module="exegesis",
        grounded_enabled=True,
        use_cache=False,
    )
    assert ensure_calls == []
    assert prep.module == "exegesis"


# ---------------------------------------------------------------------------
# Prompt / citation render
# ---------------------------------------------------------------------------


def test_theology_kb_render_includes_bibliographic_provenance() -> None:
    rendered, sources, evidence_ids, _warnings = render_kb_context(
        _packet_with_items(_theology_item())
    )
    assert "[THEOLOGICAL SOURCES]" in rendered
    assert "Source: Theology store" in rendered
    assert "source_type=theological_source" in rendered
    assert "author_name=John Calvin" in rendered
    assert "work_title=The Institutes of the Christian Religion" in rendered
    assert "human_readable_locator=John Calvin, The Institutes of the Christian Religion, Book II, Chapter 12, Section 4" in rendered
    assert "source_locator=ccel:calvin/institutes#ii.xii-p4" in rendered
    assert "translator=Henry Beveridge" in rendered
    assert "publication_year=1845" in rendered
    assert "canonical_passages=John.3.16" in rendered
    assert "SYNTHETIC theology evidence body." in rendered
    assert "trans. Henry Beveridge" in rendered
    assert "EV-THEO" not in rendered
    assert THEOLOGY_SOURCE_ID in sources
    assert evidence_ids == ["EV-THEO-chunk.ii.xii-p4"]


def test_missing_translator_and_year_are_omitted() -> None:
    item = _theology_item(translator=None, publication_year=None)
    rendered, _sources, _ids, _warnings = render_kb_context(_packet_with_items(item))
    assert "translator=" not in rendered
    assert "trans." not in rendered
    assert "publication_year=" not in rendered
    assert "1845" not in rendered
    assert "Henry Beveridge" not in rendered
    assert "author_name=John Calvin" in rendered
    assert "page=" not in rendered
    assert " p. " not in rendered


def test_no_page_metadata_does_not_invent_page_citation() -> None:
    item = _theology_item()
    assert "page" not in item.metadata
    rendered, _sources, _ids, _warnings = render_kb_context(_packet_with_items(item))
    assert "page=" not in rendered
    assert "pp." not in rendered.lower()


def test_no_match_packet_has_warning_and_no_named_source_metadata() -> None:
    background = ContextItem(
        text="Dictionary background without theology.",
        evidence_id="ev-dict-1",
        source_id="aquifer_open_bible_dictionary",
        relevance_score=8,
        item_type="dictionary_background",
        metadata={"canonical_scope": "John.3.16"},
    )
    packet = _packet_with_items(
        background,
        warnings=[THEOLOGY_NO_MATCH_WARNING],
        section_type="dictionary",
    )
    rendered, sources, _ids, _warnings = render_kb_context(packet)
    assert THEOLOGY_NO_MATCH_WARNING in rendered
    assert "[THEOLOGICAL SOURCES]" in rendered
    assert "author_name=" not in rendered
    assert "work_title=" not in rendered
    assert "John Calvin" not in rendered
    assert "Calvin" not in rendered
    preview = compose_grounded_prompt(
        production_prompt=DRY_RUN_PRODUCTION_STUB,
        canonical_passage="John.3.16",
        module="theology",
        context_packet=packet,
    )
    assert preview.success is True
    assert THEOLOGY_NO_MATCH_WARNING in preview.composed_prompt
    assert "do not attribute theological claims to a named source." in preview.composed_prompt
    assert "author_name=" not in preview.composed_prompt
    assert THEOLOGY_SOURCE_ID not in sources


def test_calvin_appears_only_from_evidence_metadata() -> None:
    unnamed = _theology_item(
        author_name=None,
        work_title="An unnamed treatise",
        human_readable_locator="Book I, Chapter 1",
        source_locator="store:work#i.i-p1",
        translator=None,
        publication_year=None,
    )
    rendered, _sources, _ids, _warnings = render_kb_context(_packet_with_items(unnamed))
    assert "Calvin" not in rendered
    assert "author_name=" not in rendered
    named = render_kb_context(_packet_with_items(_theology_item()))[0]
    assert "author_name=John Calvin" in named


# ---------------------------------------------------------------------------
# OT theology grounding (TAGNT NT-only must not block the store)
# ---------------------------------------------------------------------------

_OT_HIT = "Isa.53.5"
_OT_NO_MATCH = "Obad.1.1"
_NT_JOHN = "John.3.16"
_NT_ROM = "Rom.8.3"


def _linked_chunk(
    *,
    chunk_id: str,
    section_id: str,
    sequence: int,
    canonical: str,
    locator: str,
    body: str,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "section_id": section_id,
        "sequence": sequence,
        "text": body,
        "plain_text": body,
        "source_locator": locator,
        "passage_links": [{"canonical_passage": canonical, "raw_citation": canonical}],
    }


def _import_ot_nt_store(tmp_path: Path) -> Path:
    database = tmp_path / "theology-ot-nt.sqlite3"
    document = {
        "authors": [
            {
                "author_id": "test.author.d3c-ot",
                "canonical_name": "John Calvin",
                "tradition": "reformed",
                "birth_year": 1509,
                "death_year": 1564,
            }
        ],
        "works": [
            {
                "work_id": "test.work.d3c-ot",
                "author_id": "test.author.d3c-ot",
                "title": "The Institutes of the Christian Religion",
                "original_title": None,
                "tradition": "reformed",
                "original_language": "la",
            }
        ],
        "editions": [
            {
                "edition_id": "test.edition.d3c-ot",
                "work_id": "test.work.d3c-ot",
                "edition_label": "D3C OT fixture",
                "translator": "Henry Beveridge",
                "publication_year": 1845,
                "publisher": "Textus Test",
                "language": "en",
                "license": "Public Domain",
                "rights_status": "public-domain",
                "rights_note": "Synthetic OT/NT fixture.",
                "source_url": "https://example.test/theology-d3c-ot",
                "corpus": "ccel",
                "external_id": "test/calvin/institutes-d3c-ot",
            }
        ],
        "sections": [
            {
                "section_id": "book.ii",
                "edition_id": "test.edition.d3c-ot",
                "parent_section_id": None,
                "section_type": "book",
                "heading": "BOOK SECOND.",
                "sequence": 1,
            },
            {
                "section_id": "book.ii.ch12",
                "edition_id": "test.edition.d3c-ot",
                "parent_section_id": "book.ii",
                "section_type": "chapter",
                "heading": "CHAPTER 12.",
                "sequence": 1,
            },
            {
                "section_id": "book.ii.ch12.s1",
                "edition_id": "test.edition.d3c-ot",
                "parent_section_id": "book.ii.ch12",
                "section_type": "section",
                "heading": "1.",
                "sequence": 1,
            },
            {
                "section_id": "book.ii.ch12.s2",
                "edition_id": "test.edition.d3c-ot",
                "parent_section_id": "book.ii.ch12",
                "section_type": "section",
                "heading": "2.",
                "sequence": 2,
            },
            {
                "section_id": "book.ii.ch12.s3",
                "edition_id": "test.edition.d3c-ot",
                "parent_section_id": "book.ii.ch12",
                "section_type": "section",
                "heading": "3.",
                "sequence": 3,
            },
        ],
        "chunks": [
            _linked_chunk(
                chunk_id="chunk.isa535",
                section_id="book.ii.ch12.s1",
                sequence=1,
                canonical=_OT_HIT,
                locator="ccel:calvin/institutes#isa53",
                body="SYNTHETIC OT Isaiah 53 theology body.",
            ),
            _linked_chunk(
                chunk_id="chunk.john316",
                section_id="book.ii.ch12.s2",
                sequence=1,
                canonical=_NT_JOHN,
                locator="ccel:calvin/institutes#john316",
                body="SYNTHETIC NT John 3.16 theology body.",
            ),
            _linked_chunk(
                chunk_id="chunk.rom83",
                section_id="book.ii.ch12.s3",
                sequence=1,
                canonical=_NT_ROM,
                locator="ccel:calvin/institutes#rom83",
                body="SYNTHETIC NT Romans 8.3 theology body.",
            ),
        ],
    }
    import_theology_sqlite(document=document, database_path=database)
    return database


def _theology_item_count(prep) -> int:
    packet = prep.context_packet or {}
    count = 0
    for section in packet.get("sections") or []:
        for item in section.get("items") or []:
            if item.get("item_type") == "theological_source":
                count += 1
    return count


def test_ot_retrieve_skips_tagnt_and_does_not_invent_lexical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tagnt_calls: list[str] = []

    def boom_if_called(self, reference):
        tagnt_calls.append(str(reference))
        raise RuntimeError("TAGNT should not load for OT")

    monkeypatch.setattr(
        "textus_kb.adapters.tagnt.TagntAdapter.load_passage_tokens",
        boom_if_called,
    )
    packet = retrieve(_OT_NO_MATCH)
    assert tagnt_calls == []
    assert packet.passage_canonical == _OT_NO_MATCH
    assert all(item.source_id != "stepbible_tagnt" for item in packet.evidence_items)
    assert all(
        item.relation_type not in {"passage_token", "lexical_highlight"}
        for item in packet.evidence_items
    )
    assert any("not applicable to this Old Testament" in warning for warning in packet.warnings)

    with pytest.raises(RuntimeError, match="TAGNT should not load for OT"):
        retrieve("Jn 4,1-42")
    assert tagnt_calls


def test_ot_passage_valid_store_theology_hit_is_grounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_ot_nt_store(tmp_path)
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: _status(available=True, path=str(database)),
    )
    theo_calls: list[str] = []
    orig = __import__(
        "textus_kb.retrieval", fromlist=["retrieve_theology_evidence"]
    ).retrieve_theology_evidence

    def counting_theo(reference, **kwargs):
        theo_calls.append(str(reference))
        return orig(reference, **kwargs)

    monkeypatch.setattr("textus_kb.retrieval.retrieve_theology_evidence", counting_theo)
    monkeypatch.setattr(
        "textus_kb.context_builder.retrieve_theology_evidence", counting_theo
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage=_OT_HIT,
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert theo_calls
    assert prep.grounded_used is True
    assert prep.status == STATUS_USED
    assert prep.provider_prompt != PRODUCTION
    assert _theology_item_count(prep) >= 1
    assert "author_name=John Calvin" in prep.provider_prompt
    assert "work_title=The Institutes of the Christian Religion" in prep.provider_prompt
    assert "human_readable_locator=" in prep.provider_prompt
    assert "SYNTHETIC OT Isaiah 53 theology body." in prep.provider_prompt
    assert THEOLOGY_NO_MATCH_WARNING not in prep.provider_prompt


def test_ot_passage_valid_store_no_theology_hit_is_grounded_nomatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_ot_nt_store(tmp_path)
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: _status(available=True, path=str(database)),
    )
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage=_OT_NO_MATCH,
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert prep.grounded_used is True
    assert prep.provider_prompt != PRODUCTION
    assert _theology_item_count(prep) == 0
    assert THEOLOGY_NO_MATCH_WARNING in prep.provider_prompt
    assert "author_name=" not in prep.provider_prompt
    assert "John Calvin" not in prep.provider_prompt


def test_ot_passage_missing_store_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieve_calls = {"n": 0}
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: _status(available=False, reason="missing_database"),
    )

    def counting_retrieve(ref):
        retrieve_calls["n"] += 1
        raise AssertionError("missing store must not retrieve")

    monkeypatch.setattr("textus_kb.retrieval.retrieve", counting_retrieve)
    prep = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage=_OT_HIT,
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert retrieve_calls["n"] == 0
    assert prep.grounded_fallback is True
    assert prep.fallback_reason == REASON_SOURCE_UNAVAILABLE
    assert prep.provider_prompt == PRODUCTION


def test_nt_john_and_rom_still_grounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_ot_nt_store(tmp_path)
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: _status(available=True, path=str(database)),
    )
    for passage, body in (
        (_NT_JOHN, "SYNTHETIC NT John 3.16 theology body."),
        (_NT_ROM, "SYNTHETIC NT Romans 8.3 theology body."),
    ):
        prep = prepare_grounded_provider_prompt(
            production_prompt=PRODUCTION,
            passage=passage,
            module="theology",
            grounded_enabled=True,
            use_cache=False,
        )
        assert prep.grounded_used is True, passage
        assert _theology_item_count(prep) >= 1, passage
        assert body in prep.provider_prompt


def test_nt_tagnt_failure_is_not_globally_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _import_ot_nt_store(tmp_path)
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: _status(available=True, path=str(database)),
    )

    def boom(self, reference):
        raise RuntimeError("tagnt exploded")

    monkeypatch.setattr(
        "textus_kb.adapters.tagnt.TagntAdapter.load_passage_tokens", boom
    )
    nt = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage=_NT_JOHN,
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert nt.grounded_fallback is True
    assert nt.fallback_reason == REASON_RETRIEVAL_ERROR
    assert nt.provider_prompt == PRODUCTION
    assert "tagnt exploded" in nt.error or nt.error == "RuntimeError"

    ot = prepare_grounded_provider_prompt(
        production_prompt=PRODUCTION,
        passage=_OT_HIT,
        module="theology",
        grounded_enabled=True,
        use_cache=False,
    )
    assert ot.grounded_used is True
    assert _theology_item_count(ot) >= 1


def test_exegesis_and_history_nt_paths_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_calls: list[str] = []
    monkeypatch.setattr(
        "textus_kb.theology_runtime.ensure_theology_database",
        lambda **kwargs: ensure_calls.append("called") or _status(available=True),
    )
    exegesis = prepare_grounded_provider_prompt(
        production_prompt="EXEGESIS",
        passage="Jn 4,1-42",
        module="exegesis",
        grounded_enabled=True,
        use_cache=False,
    )
    history = prepare_grounded_provider_prompt(
        production_prompt="HISTORY",
        passage="Lk 10,25-37",
        module="historical_context",
        grounded_enabled=True,
        use_cache=False,
    )
    assert ensure_calls == []
    assert exegesis.module == "exegesis"
    assert history.module == "historical_context"
    assert exegesis.grounded_used is True or exegesis.grounded_fallback is True
    assert history.grounded_used is True or history.grounded_fallback is True
    if exegesis.grounded_used:
        assert "STEPBible TAGNT" in exegesis.provider_prompt
    unsupported = prepare_grounded_provider_prompt(
        production_prompt="ILLUSTRATIONS",
        passage="Jn 4,1-42",
        module="illustrations",
        grounded_enabled=True,
        use_cache=False,
    )
    assert unsupported.grounded_unsupported_module is True
    assert unsupported.provider_prompt == "ILLUSTRATIONS"
