"""Phase 5L-A — original-language AI fallback (DB-first)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from bible_engine.hebrew_token_repository import HebrewRepositoryResult
from bible_engine.original_language_analysis import (
    AI_FALLBACK_USER_NOTICE,
    STATUS_AI_FALLBACK,
    STATUS_GROUNDED,
    STATUS_UNAVAILABLE,
    UNAVAILABLE_USER_MESSAGE,
    inspect_original_language_tokens,
    plan_original_language_analysis,
    run_original_language_analysis,
)
from bible_engine.original_language_grounding_check import (
    GroundingCategory,
    GroundingWarning,
)


def _fake_generate_ok(prompt: str, **_kwargs: Any) -> str:
    is_fallback = "AI VISSZAESÉS" in prompt or "AI-alapú" in prompt
    if is_fallback:
        assert "TILOS ebben a módban" in prompt
        assert "helyi adatbázisból, kizárólagos forrás" not in prompt
        return "AI fallback elemzés: a λόγος szó a szöveg központi fogalma."
    return "DB grounded elemzés: a ἠγάπησεν alak a szakasz kulcsa."


def _fake_generate_fail(prompt: str, **_kwargs: Any) -> str:
    return "⚠️ **API hiba** — generálás sikertelen."


@dataclass
class _FakeHebrewRepo:
    status: str = "database_missing"

    def passage(self, *_args, **_kwargs) -> HebrewRepositoryResult:
        return HebrewRepositoryResult(status=self.status, tokens=())


def test_a_nt_token_data_available_is_grounded() -> None:
    plan = plan_original_language_analysis("Jn 3,16")
    assert plan.intended_status == STATUS_GROUNDED
    assert plan.should_generate is True
    assert plan.user_notice == ""
    assert "EREDETI NYELVI TOKENEK" in plan.prompt
    assert "AI VISSZAESÉS" not in plan.prompt

    result = run_original_language_analysis(
        "Jn 3,16",
        generate_text_fn=_fake_generate_ok,
        grounding_checker=lambda _text, _ref: [],
    )
    assert result.status == STATUS_GROUNDED
    assert result.user_notice == ""
    assert "DB grounded" in result.text


def test_b_ot_token_data_available_is_grounded() -> None:
    plan = plan_original_language_analysis("1Móz 1,1")
    assert plan.intended_status == STATUS_GROUNDED
    assert plan.should_generate is True
    assert plan.user_notice == ""
    assert "H7225" in plan.prompt or "lemma:" in plan.prompt


def test_c_nt_db_unavailable_uses_ai_fallback() -> None:
    def boom(_ref: str):
        raise FileNotFoundError("TAGNT missing")

    plan = plan_original_language_analysis("Jn 3,16", greek_loader=boom)
    assert plan.intended_status == STATUS_AI_FALLBACK
    assert plan.should_generate is True
    assert plan.user_notice == AI_FALLBACK_USER_NOTICE
    assert "AI VISSZAESÉS" in plan.prompt
    assert "TILOS ebben a módban" in plan.prompt
    assert "helyi adatbázisból, kizárólagos forrás" not in plan.prompt

    result = run_original_language_analysis(
        "Jn 3,16",
        generate_text_fn=_fake_generate_ok,
        greek_loader=boom,
    )
    assert result.status == STATUS_AI_FALLBACK
    assert result.user_notice == AI_FALLBACK_USER_NOTICE
    assert "AI fallback" in result.text
    assert result.grounding_warnings == []


def test_d_ot_db_unavailable_uses_ai_fallback() -> None:
    plan = plan_original_language_analysis(
        "1Móz 1,1",
        hebrew_repository_factory=lambda: _FakeHebrewRepo("database_missing"),
    )
    assert plan.intended_status == STATUS_AI_FALLBACK
    assert plan.user_notice == AI_FALLBACK_USER_NOTICE

    result = run_original_language_analysis(
        "1Móz 1,1",
        generate_text_fn=_fake_generate_ok,
        hebrew_repository_factory=lambda: _FakeHebrewRepo("database_missing"),
    )
    assert result.status == STATUS_AI_FALLBACK
    assert "AI fallback" in result.text


def test_e_malformed_unknown_book_does_not_pick_wrong_language() -> None:
    inspection = inspect_original_language_tokens("Ismeretlen 1,1")
    assert inspection.allow_ai_fallback is False
    assert inspection.has_authoritative_tokens is False
    assert inspection.language is None
    plan = plan_original_language_analysis("Ismeretlen 1,1")
    assert plan.intended_status == STATUS_UNAVAILABLE
    assert plan.should_generate is False


def test_f_chapter_only_nt_keeps_needs_verses() -> None:
    inspection = inspect_original_language_tokens("Lk 10")
    assert inspection.greek_status == "needs_verses"
    assert inspection.allow_ai_fallback is False
    assert inspection.language == "greek"
    plan = plan_original_language_analysis("Lk 10")
    assert plan.intended_status == STATUS_UNAVAILABLE
    assert plan.should_generate is False
    assert "vers" in plan.blocking_message.casefold()

    result = run_original_language_analysis(
        "Lk 10",
        generate_text_fn=_fake_generate_ok,
    )
    assert result.status == STATUS_UNAVAILABLE
    assert result.provider_called is False


def test_g_fallback_provider_failure_is_unavailable() -> None:
    def boom(_ref: str):
        raise FileNotFoundError("missing")

    result = run_original_language_analysis(
        "Jn 3,16",
        generate_text_fn=_fake_generate_fail,
        greek_loader=boom,
    )
    assert result.status == STATUS_UNAVAILABLE
    assert result.text == UNAVAILABLE_USER_MESSAGE
    assert result.user_notice == ""


def test_h_post_hoc_warning_does_not_switch_to_ai_fallback() -> None:
    warning = GroundingWarning(
        category=GroundingCategory.GLOBAL_OTHER_PASSAGE,
        kind="greek_word",
        value="λόγος",
        message="„λόγος” — figyelmeztetés",
    )

    result = run_original_language_analysis(
        "Jn 3,16",
        generate_text_fn=_fake_generate_ok,
        grounding_checker=lambda _text, _ref: [warning],
    )
    assert result.status == STATUS_GROUNDED
    assert result.grounding_warnings == [warning.message]
    assert result.user_notice == ""


def test_nt_invalid_does_not_ai_fallback() -> None:
    # Recognized NT book with unusable rest should stay blocked (5K-B).
    plan = plan_original_language_analysis("Lk")
    # "Lk" alone may be invalid or needs chapter — either way no AI fallback.
    assert plan.should_generate is False or plan.intended_status != STATUS_AI_FALLBACK
    inspection = inspect_original_language_tokens("Lk")
    assert inspection.allow_ai_fallback is False
