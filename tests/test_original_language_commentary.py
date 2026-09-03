"""Commentary (Calvin/JFB/Henry) integration for "Eredeti szöveg
tanulmányozása" — strictly secondary, smallest budget of the three
grounded study modules (2026-09-03 round).

``bible_engine.original_language_analysis`` has no Streamlit dependency of
its own (no ``st.form``/widget instantiation at import time), so unlike
``tests/test_original_language_token_block.py`` (which imports THROUGH
``app.py``) these tests import it directly — no subprocess isolation
needed.

Real end-to-end checks use the real, locally-built 3-source production
Commentary store (gated, skipped when unavailable) together with the
real local Greek/Hebrew token databases already used by this module.
Fail-closed checks use monkeypatched ``commentary_runtime.get_status``.
No external LLM/API is called anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bible_engine.original_language_analysis import (
    ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER,
    ORIGINAL_TEXT_COMMENTARY_ITEM_LIMIT,
    ORIGINAL_TEXT_COMMENTARY_MAX_CHARS,
    ORIGINAL_TEXT_COMMENTARY_RULE,
    TOKEN_BLOCK_HEADER,
    build_ai_fallback_original_text_prompt,
    build_grounded_original_text_prompt,
    build_original_text_commentary_block,
    plan_original_language_analysis,
)
from textus_kb import commentary_runtime
from textus_kb.repositories.commentary_repository import CommentaryRepository

_PRODUCTION_DB = Path("data/generated/commentary.sqlite3")
_requires_production_commentary = pytest.mark.skipif(
    not (_PRODUCTION_DB.is_file() and CommentaryRepository(_PRODUCTION_DB).store_status().available),
    reason=(
        "Production 3-source commentary.sqlite3 not present/valid locally. Build with: "
        "python scripts/build_commentary_database.py --combined-fetch --qa"
    ),
)

# References with confirmed real local Greek/Hebrew token coverage
# (ld. tests/test_original_language_token_block.py's own known-good set).
_GROUNDED_REF = "Jn 3,16"


# --- Fail-closed: no passage, DB missing/invalid, no match ---------------


def test_empty_passage_returns_empty_block() -> None:
    assert build_original_text_commentary_block("") == ""
    assert build_original_text_commentary_block("   ") == ""


def test_missing_db_returns_empty_block(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Unavailable:
        available = False
        database_path = ""

    monkeypatch.setattr(commentary_runtime, "get_status", lambda *a, **k: _Unavailable())
    assert build_original_text_commentary_block(_GROUNDED_REF) == ""


def test_invalid_db_returns_empty_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlite3

    bad_db = tmp_path / "invalid.sqlite3"
    conn = sqlite3.connect(bad_db)
    conn.execute("CREATE TABLE store_metadata (key TEXT, value TEXT)")
    conn.execute("INSERT INTO store_metadata VALUES ('schema_version', '999')")
    conn.commit()
    conn.close()
    real_status = commentary_runtime.get_status(bad_db)
    assert real_status.available is False  # sanity: this really is invalid
    monkeypatch.setattr(commentary_runtime, "get_status", lambda *a, **k: real_status)
    assert build_original_text_commentary_block(_GROUNDED_REF) == ""


def test_unresolvable_reference_returns_empty_block() -> None:
    assert build_original_text_commentary_block("Xyz 99,99") == ""


def test_no_commentary_block_leaves_grounded_prompt_unchanged_shape() -> None:
    """Fail-closed contract: when the block is "" (e.g. empty igehely, so
    build_original_text_commentary_block itself returns "") the grounded
    prompt carries no stray rule text or empty section header."""
    prompt = build_grounded_original_text_prompt("", "", "TOKEN BLOCK PLACEHOLDER")
    assert ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER not in prompt
    assert ORIGINAL_TEXT_COMMENTARY_RULE.strip() not in prompt


def test_ai_fallback_prompt_never_gets_commentary_block() -> None:
    """The AI-fallback path (no authoritative local token data) must never
    be blurred with a second, unrelated secondary source."""
    prompt = build_ai_fallback_original_text_prompt("Jn 3,16", "")
    assert ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER not in prompt
    assert "KLASSZIKUS KOMMENTÁTORI" not in prompt


# --- Real production-store checks -----------------------------------------


@_requires_production_commentary
def test_grounded_block_has_real_attributable_content() -> None:
    block = build_original_text_commentary_block(_GROUNDED_REF)
    assert block, "expected real commentary content for John 3:16"
    assert block.startswith(ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER)
    # Never invents a citation: each excerpt line names a real contributor.
    lines = [line for line in block.splitlines() if line.startswith("- ")]
    assert lines
    assert len(lines) <= ORIGINAL_TEXT_COMMENTARY_ITEM_LIMIT
    for line in lines:
        assert "(author)" in line or "edition:" in line


@_requires_production_commentary
def test_grounded_block_excerpt_respects_char_cap() -> None:
    block = build_original_text_commentary_block(_GROUNDED_REF)
    assert block
    for line in block.splitlines():
        if not line.startswith("- "):
            continue
        # The excerpt portion (after the citation) must be capped -- the
        # whole line includes the citation prefix too, so just assert the
        # line isn't unboundedly long (a real, uncapped Calvin/Henry
        # section can run to several thousand characters).
        assert len(line) < ORIGINAL_TEXT_COMMENTARY_MAX_CHARS + 400


@_requires_production_commentary
def test_grounded_prompt_contains_both_token_block_and_commentary_rule() -> None:
    """Nyelvi adat vs. klasszikus kommentátori értelmezés must both be
    explicitly present and distinguished when commentary is available."""
    prompt = build_grounded_original_text_prompt(
        _GROUNDED_REF, "", TOKEN_BLOCK_HEADER + "[1] λόγος | lemma: λόγος | morf: N (noun) | Strong: G3056"
    )
    assert TOKEN_BLOCK_HEADER in prompt
    assert ORIGINAL_TEXT_COMMENTARY_RULE.strip() in prompt
    assert ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER in prompt
    # Token block appears before the commentary rule/block (nyelvi adat elsőbbsége).
    assert prompt.index(TOKEN_BLOCK_HEADER) < prompt.index(ORIGINAL_TEXT_COMMENTARY_RULE.strip())


@_requires_production_commentary
def test_revelation_unsupported_by_calvin_jfb_henry_still_work() -> None:
    """Calvin never wrote Revelation; JFB/Henry must still surface here."""
    block = build_original_text_commentary_block("Jel 1,1")
    assert block
    assert "Calvin" not in block


@_requires_production_commentary
def test_plan_grounded_status_includes_commentary_when_available() -> None:
    plan = plan_original_language_analysis(_GROUNDED_REF, "")
    assert plan.intended_status == "grounded_language_data"
    assert "KLASSZIKUS KOMMENTÁTORI" in plan.prompt


def test_rule_text_forbids_reliability_scores() -> None:
    assert "reliability" in ORIGINAL_TEXT_COMMENTARY_RULE.lower() or (
        "rangsorolást" in ORIGINAL_TEXT_COMMENTARY_RULE
    )
