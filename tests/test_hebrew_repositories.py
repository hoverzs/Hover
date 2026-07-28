from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_engine.hebrew_lexicon_repository import HebrewLexiconRepository
from bible_engine.hebrew_sqlite import import_hebrew_fixture_database
from bible_engine.hebrew_token_repository import HebrewTokenRepository


FIXTURES = Path(__file__).parent / "fixtures"
TAHOT = FIXTURES / "tahot_ruth_psa_sample.tsv"
TBESH = FIXTURES / "tbesh_ruth_psa_sample.tsv"


def test_token_repository_statuses_and_passage_query(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    repository = HebrewTokenRepository(database)

    result = repository.passage("Rut", 1, 1, 5)
    missing = HebrewTokenRepository(tmp_path / "missing.sqlite3").passage("Rut", 1, 1)

    assert result.status == "ok"
    assert result.tokens[0].stable_key == "Rut:1:1:1"
    assert missing.status == "database_missing"


def test_lexicon_repository_direct_alias_and_missing(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    alias_path = tmp_path / "hebrew_strong_aliases.json"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    alias_path.write_text(
        json.dumps(
            [
                {
                    "source_id": "H1961Z",
                    "target_id": "H1961",
                    "confidence": "high",
                    "evidence": "test alias",
                    "occurrence_count": 1,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    repository = HebrewLexiconRepository(database, alias_path)

    direct = repository.lookup("H1961")
    alias = repository.lookup("H1961Z")
    missing = repository.lookup("H9999Z")

    assert direct.status == "direct"
    assert direct.requested_strong_id == "H1961"
    assert direct.resolved_strong_id == "H1961"
    assert direct.resolution_type == "direct"
    assert alias.status == "alias"
    assert alias.via_alias
    assert alias.requested_strong_id == "H1961Z"
    assert alias.resolved_strong_id == "H1961"
    assert alias.resolution_type == "alias"
    assert alias.alias_confidence == "high"
    assert alias.entry == direct.entry
    assert missing.status == "lexicon_not_found"
    assert missing.resolution_type == "missing"


def test_token_lexicon_lookup_separates_core_prefix_suffix(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    token = HebrewTokenRepository(database).passage("Rut", 1, 1).tokens[0]
    lookup = HebrewLexiconRepository(database, tmp_path / "missing_aliases.json").lookup_token(token)

    assert lookup.prefixes
    assert lookup.core.entry is not None
    assert lookup.core.source_component == "core"
    assert lookup.all_strong_ids


def test_suffix_is_not_trimmed_without_documented_alias(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    repository = HebrewLexiconRepository(database, tmp_path / "missing_aliases.json")

    lookup = repository.lookup("H1961Z")

    assert lookup.status == "lexicon_not_found"
    assert lookup.resolution_type == "missing"


def test_missing_alias_target_is_controlled_partial_match(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    alias_path = tmp_path / "hebrew_strong_aliases.json"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    alias_path.write_text(
        json.dumps(
            [{"source_id": "H1961Z", "target_id": "H9999Z", "confidence": "high", "evidence": "test"}]
        ),
        encoding="utf-8",
    )

    lookup = HebrewLexiconRepository(database, alias_path).lookup("H1961Z")

    assert lookup.status == "partial_lexicon_match"
    assert lookup.resolution_type == "partial"
    assert lookup.resolved_strong_id == "H9999Z"


def test_chained_or_cyclic_aliases_are_rejected(tmp_path: Path) -> None:
    alias_path = tmp_path / "hebrew_strong_aliases.json"
    alias_path.write_text(
        json.dumps(
            [
                {"source_id": "H1961Z", "target_id": "H1961Y", "confidence": "high"},
                {"source_id": "H1961Y", "target_id": "H1961Z", "confidence": "high"},
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Chained or cyclic"):
        HebrewLexiconRepository(tmp_path / "missing.sqlite3", alias_path)
