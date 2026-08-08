from __future__ import annotations

import pytest

import original_language_concordance as olc


def test_detect_query_kind_hebrew_strong() -> None:
    assert olc.detect_query_kind("H3467") == "strong_hebrew"
    assert olc.detect_query_kind("h3467") == "strong_hebrew"
    assert olc.detect_query_kind("H1234A") == "strong_hebrew"


def test_detect_query_kind_greek_strong() -> None:
    assert olc.detect_query_kind("G2316") == "strong_greek"
    assert olc.detect_query_kind("g2316") == "strong_greek"


def test_detect_query_kind_hebrew_script() -> None:
    assert olc.detect_query_kind("יָשַׁע") == "hebrew_lemma"


def test_detect_query_kind_greek_script() -> None:
    assert olc.detect_query_kind("θεός") == "greek_lemma"


def test_detect_query_kind_hungarian_text_is_unknown() -> None:
    assert olc.detect_query_kind("szeretet") == "unknown"
    assert olc.detect_query_kind("örök élet") == "unknown"
    assert olc.detect_query_kind("") == "unknown"


def test_is_original_language_query() -> None:
    assert olc.is_original_language_query("H3467") is True
    assert olc.is_original_language_query("G2316") is True
    assert olc.is_original_language_query("szeretet") is False


def test_search_original_unknown_query_returns_empty() -> None:
    assert olc.search_original("szeretet") == []


def test_search_original_hebrew_strong_is_deduplicated_and_ordered() -> None:
    from bible_engine.hebrew_token_repository import HebrewTokenRepository

    hits = olc.search_original("H3467", with_hungarian_context=False)
    raw_tokens = HebrewTokenRepository().by_strong_id("H3467")
    unique_stable_keys = {t.stable_key for t in raw_tokens}

    assert len(hits) > 0
    # A nyers lekérdezés (komponens- + flat 'token'-szerep sor miatt)
    # kétszerezi a találatokat — a modulnak pontosan az egyedi token-ök
    # számára kell csökkentenie, NEM (book,chapter,verse,strong_id)
    # szerint (egy versben jogosan előfordulhat ugyanaz a szó kétszer).
    assert len(hits) == len(unique_stable_keys)
    assert len(hits) < len(raw_tokens)
    ordinals = [h.ordinal for h in hits]
    assert ordinals == sorted(ordinals), "a találatoknak kanonikus sorrendben kell lenniük"
    assert all(h.language == "héber" for h in hits)


def test_search_original_greek_strong_returns_hits() -> None:
    hits = olc.search_original("G2316", with_hungarian_context=False)

    assert len(hits) > 0
    assert all(h.language == "görög" for h in hits)
    assert all(h.strong_id == "G2316" for h in hits)


def test_search_original_attaches_hungarian_context_by_default() -> None:
    hits = olc.search_original("G2316")

    assert len(hits) > 0
    assert any(h.hungarian_context for h in hits), (
        "legalább néhány találatnak legyen magyar kontextusa (a helyi RÚF-DB-ből)"
    )


def test_search_original_hebrew_lemma_matches_strong_lookup_book() -> None:
    strong_hits = olc.search_original("H3467", with_hungarian_context=False)
    lemma = None
    from bible_engine.hebrew_token_repository import HebrewTokenRepository

    repo = HebrewTokenRepository()
    tokens = repo.by_strong_id("H3467")
    if tokens:
        lemma = tokens[0].lemma
    if not lemma:
        pytest.skip("nincs elérhető lemma a tesztkörnyezetben")

    lemma_hits = olc.search_original(lemma, with_hungarian_context=False)
    assert len(lemma_hits) > 0
    assert all(h.language == "héber" for h in lemma_hits)
