from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from illustration_engine.illustration_sqlite import (
    IllustrationLicenseGateError,
    create_schema,
    insert_illustration_unit,
    insert_source,
    insert_story,
    update_illustration_unit_fields,
    update_unit_machine_qa,
)
from illustration_engine.retrieval import (
    RankedIllustration,
    build_ranking_prompt,
    find_candidates,
    parse_ranking_response,
    retrieve_illustrations,
)

_VALID_SUMMARY = " ".join(["szo"] * 45)


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _make_source(conn: sqlite3.Connection, *, code: str = "SRC", license_status: str = "public_domain_confirmed") -> int:
    return insert_source(
        conn, code=code, title="Test Source", orig_language="en",
        license_status=license_status, license_basis_hu="x", reliability_tier="high", tradition="tradition",
    )


def _make_story(conn: sqlite3.Connection, source_id: int, *, external_ref: str = "1", original_text: str = "Az irgalmas atya története a fiaknak.") -> int:
    return insert_story(
        conn, source_id=source_id, external_ref=external_ref, canonical_key=f"key-{external_ref}",
        title_original="Original Title", adaptation_status="verbatim_transcription", original_text=original_text,
        original_text_checksum=hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
    )


def _make_unit(
    conn: sqlite3.Connection, story_id: int, *, unit_index: int = 1, status: str = "needs_review",
    qa_status: str | None = None, title_hu: str = "Cím", modern_hu_text: str = "Az irgalmas atya elfogadta vissza a fiát.",
    summary_hu: str = _VALID_SUMMARY,
) -> int:
    unit_id = insert_illustration_unit(
        conn, story_id=story_id, unit_index=unit_index, derivation_type="full_story_translation",
        status=status, title_hu=title_hu, modern_hu_text=modern_hu_text, summary_hu=summary_hu,
        human_reviewed_at="2026-08-28T00:00:00+00:00" if status in ("approved", "published") else None,
    )
    if qa_status:
        update_unit_machine_qa(conn, unit_id=unit_id, qa_status=qa_status, qa_model="m", qa_prompt_version="v1")
    return unit_id


def _make_published_unit(conn: sqlite3.Connection, story_id: int, **kwargs) -> int:
    unit_id = _make_unit(conn, story_id, status="published", qa_status="passed", **kwargs)
    return unit_id


def _llm(response) -> callable:
    if isinstance(response, dict):
        return lambda prompt: json.dumps(response)
    return lambda prompt: response


# ---------------------------------------------------------------------------
# Mode gating
# ---------------------------------------------------------------------------


def test_production_mode_returns_only_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_1 = _make_story(conn, source_id, external_ref="1")
    story_2 = _make_story(conn, source_id, external_ref="2")
    published_id = _make_published_unit(conn, story_1, title_hu="Publikált")
    _make_unit(conn, story_2, status="needs_review", qa_status="passed", title_hu="Nem publikált")
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="production", limit=10)
    conn.close()

    assert [c.unit_id for c in candidates] == [published_id]
    assert candidates[0].provenance_status == "published"


def test_development_mode_returns_qa_passed_regardless_of_review_status() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="development", limit=10)
    conn.close()

    assert [c.unit_id for c in candidates] == [unit_id]
    assert candidates[0].provenance_status == "development_qa_passed"


def test_development_mode_excludes_needs_attention() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, qa_status="needs_attention")
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="development", limit=10)
    conn.close()
    assert candidates == []


def test_development_mode_excludes_failed() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, qa_status="failed")
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="development", limit=10)
    conn.close()
    assert candidates == []


def test_development_mode_excludes_pending_qa() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, qa_status=None)  # never QA'd
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="development", limit=10)
    conn.close()
    assert candidates == []


def test_production_mode_excludes_approved_but_not_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, status="approved", qa_status="passed")
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="production", limit=10)
    conn.close()
    assert candidates == []


def test_invalid_mode_rejected() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        find_candidates(conn, query_text="", mode="staging", limit=10)
    conn.close()


# ---------------------------------------------------------------------------
# Rights fail-closed
# ---------------------------------------------------------------------------


def test_non_publishable_license_structurally_cannot_reach_production() -> None:
    """A 'published' unit on a non-publishable-license source cannot
    exist at all -- Python-level (IllustrationLicenseGateError) AND
    DB-level (trigger) both block it. Production-mode retrieval's rights
    guarantee is therefore structural (enforced by published_
    illustration_units' own WHERE clause + this two-layer gate), not
    merely a Python-side filter that could be bypassed."""
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="restricted")
    story_id = _make_story(conn, source_id)
    with pytest.raises(IllustrationLicenseGateError):
        insert_illustration_unit(
            conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation",
            status="published", title_hu="T", modern_hu_text="M", summary_hu=_VALID_SUMMARY,
            human_reviewed_at="2026-08-28T00:00:00+00:00",
        )
    conn.close()


def test_non_publishable_license_excluded_in_development() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="restricted")
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="development", limit=10)
    conn.close()
    assert candidates == []  # qa_status=passed alone is NOT enough -- rights still required


# ---------------------------------------------------------------------------
# Provenance / checksum fail-closed
# ---------------------------------------------------------------------------


def test_checksum_mismatch_excludes_candidate() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()
    # Corrupt the checksum directly -- simulates an integrity breach.
    conn.execute("UPDATE stories SET original_text_checksum = 'corrupted' WHERE id = ?", (story_id,))
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="development", limit=10)
    conn.close()
    assert candidates == []


def test_missing_checksum_excludes_candidate() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()
    conn.execute("UPDATE stories SET original_text_checksum = NULL WHERE id = ?", (story_id,))
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="development", limit=10)
    conn.close()
    assert candidates == []


# ---------------------------------------------------------------------------
# FTS candidate retrieval
# ---------------------------------------------------------------------------


def test_fts_keyword_match_finds_relevant_candidate() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_1 = _make_story(conn, source_id, external_ref="1")
    story_2 = _make_story(conn, source_id, external_ref="2")
    prodigal_id = _make_published_unit(
        conn, story_1, title_hu="A tékozló fiú", modern_hu_text="Az irgalmas atya elfogadta vissza a fiát.",
    )
    _make_published_unit(conn, story_2, title_hu="Másik történet", modern_hu_text="Egy teljesen más témájú anekdota.")
    conn.commit()

    candidates = find_candidates(conn, query_text="irgalmas atya", mode="production", limit=10)
    conn.close()
    assert prodigal_id in [c.unit_id for c in candidates]


def test_fts_no_match_falls_back_to_unfiltered_candidates() -> None:
    """A genuinely obscure query must not return zero candidates before
    the ranker even runs -- Stage A falls back to a recent-first window."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id)
    conn.commit()

    candidates = find_candidates(conn, query_text="teljesen_ismeretlen_szokombinacio_xyz", mode="production", limit=10)
    conn.close()
    assert unit_id in [c.unit_id for c in candidates]


def test_empty_query_text_returns_candidates_unfiltered() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id)
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="production", limit=10)
    conn.close()
    assert unit_id in [c.unit_id for c in candidates]


def test_fts_query_sanitizes_special_characters() -> None:
    """Punctuation/hyphens in free-text input must never break FTS5
    query syntax."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id)
    conn.commit()

    # Should not raise sqlite3.OperationalError.
    find_candidates(conn, query_text="Lk 15,11-24 -- \"idézet\" (zárójel)!", mode="production", limit=10)
    conn.close()


def test_candidate_limit_respected() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    for i in range(5):
        story_id = _make_story(conn, source_id, external_ref=str(i))
        _make_published_unit(conn, story_id, unit_index=1)
    conn.commit()

    candidates = find_candidates(conn, query_text="", mode="production", limit=3)
    conn.close()
    assert len(candidates) == 3


def test_invalid_limit_rejected() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        find_candidates(conn, query_text="", mode="production", limit=0)
    conn.close()


def test_candidate_includes_taxonomy_and_attribution_fields() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id)
    conn.commit()
    candidates = find_candidates(conn, query_text="", mode="production", limit=10)
    conn.close()
    c = next(c for c in candidates if c.unit_id == unit_id)
    assert c.source_title == "Test Source"
    assert c.license_status == "public_domain_confirmed"


# ---------------------------------------------------------------------------
# Stage B: ranker fail-closed parsing
# ---------------------------------------------------------------------------


def test_ranker_only_returns_known_ids() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x"}, {"unit_id": 999, "score": 0.8, "reason": "y"}]}),
        valid_ids={1, 2, 3},
    )
    assert [r.unit_id for r in ranked] == [1]  # 999 silently dropped, not replaced


def test_ranker_malformed_json_fails_closed() -> None:
    ranked = parse_ranking_response("this is not json", valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_missing_results_field_fails_closed() -> None:
    ranked = parse_ranking_response(json.dumps({"other": "stuff"}), valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_results_not_a_list_fails_closed() -> None:
    ranked = parse_ranking_response(json.dumps({"results": "not a list"}), valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_empty_results_is_valid_empty_answer() -> None:
    ranked = parse_ranking_response(json.dumps({"results": []}), valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_score_clamped_to_0_1() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 5.0, "reason": "x"}]}), valid_ids={1},
    )
    assert ranked[0].score == 1.0


def test_ranker_non_int_unit_id_dropped() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": "1", "score": 0.9, "reason": "x"}]}), valid_ids={1},
    )
    assert ranked == []  # string "1" is not accepted as int 1 -- fail closed, no type coercion guessing


def test_ranking_prompt_forbids_new_story_generation() -> None:
    from illustration_engine.retrieval import RetrievalCandidate

    candidate = RetrievalCandidate(
        unit_id=1, title_hu="T", modern_hu_text="M", summary_hu="S", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    prompt = build_ranking_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="", candidates=[candidate])
    assert "NEM ÍRSZ" in prompt or "NEM TALÁLSZ KI" in prompt
    assert "[1]" in prompt


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_returns_result_with_verbatim_db_text() -> None:
    """The critical no-hallucination guarantee: modern_hu_text in the
    result is EXACTLY the candidate's DB row, never anything from the
    LLM's own response text."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, modern_hu_text="Az eredeti, adatbázisban tárolt szöveg.")
    conn.commit()

    llm = _llm({"results": [{"unit_id": unit_id, "score": 0.95, "reason": "Nagyon releváns."}]})
    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert len(results) == 1
    assert results[0].modern_hu_text == "Az eredeti, adatbázisban tárolt szöveg."
    assert results[0].unit_id == unit_id
    assert results[0].rank_reason == "Nagyon releváns."


def test_empty_candidates_returns_empty_without_calling_llm() -> None:
    conn = _fresh_connection()
    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps({"results": []})

    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()
    assert results == []
    assert calls == []  # no candidates -> never even calls the LLM


def test_malformed_ranker_response_yields_empty_result_not_exception() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id)
    conn.commit()

    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=_llm("garbage, not json"),
    )
    conn.close()
    assert results == []


def test_top_n_limits_result_count() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    unit_ids = []
    for i in range(6):
        story_id = _make_story(conn, source_id, external_ref=str(i))
        unit_ids.append(_make_published_unit(conn, story_id))
    conn.commit()

    llm = _llm({"results": [{"unit_id": uid, "score": 0.9, "reason": "x"} for uid in unit_ids]})
    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm, top_n=3,
    )
    conn.close()
    assert len(results) == 3


def test_development_mode_result_marks_provenance_status() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()

    llm = _llm({"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x"}]})
    results = retrieve_illustrations(conn, mode="development", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()

    assert results[0].provenance_status == "development_qa_passed"


def test_retrieval_never_writes_to_db() -> None:
    """Retrieval is READ-ONLY -- human_reviewed_at, status, qa_status must
    all be unchanged after a full retrieval call."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()
    before = conn.execute("SELECT status, human_reviewed_at, qa_status FROM illustration_units WHERE id=?", (unit_id,)).fetchone()

    llm = _llm({"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x"}]})
    retrieve_illustrations(conn, mode="development", passage_reference="Lk 15,11-24", llm_generate=llm)

    after = conn.execute("SELECT status, human_reviewed_at, qa_status FROM illustration_units WHERE id=?", (unit_id,)).fetchone()
    conn.close()
    assert before == after
