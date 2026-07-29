from __future__ import annotations

from pathlib import Path

from bible_engine.hebrew_sqlite import get_hebrew_passage_tokens, import_hebrew_fixture_database
from components.hebrew_token_selector import component_tokens, normalize_hebrew_component_selection_key


FIXTURES = Path(__file__).parent / "fixtures"
TAHOT = FIXTURES / "tahot_ruth_psa_sample.tsv"
TBESH = FIXTURES / "tbesh_ruth_psa_sample.tsv"


def test_component_tokens_preserve_stable_key_and_rtl_surface(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    tokens = get_hebrew_passage_tokens(database, "Rut", 1, 1, 5)

    rendered = component_tokens(tokens, "Rut:1:1:1")

    assert rendered[0]["selection_key"] == "Rut:1:1:1"
    assert rendered[0]["selected"] is True
    assert rendered[0]["surface"] == tokens[0].surface
    assert rendered[0]["selected_word_index"] == tokens[0].word_index
    assert rendered[0]["strong_id"] == tokens[0].core_component.strong_id
    assert rendered[-1]["verse"] == 5


def test_selection_normalization_rejects_unknown_key(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    tokens = get_hebrew_passage_tokens(database, "Psa", 23, 1, 4)

    assert normalize_hebrew_component_selection_key(tokens[0].stable_key, tokens) == tokens[0].stable_key
    assert normalize_hebrew_component_selection_key("Psa:23:1:999", tokens) is None
    assert normalize_hebrew_component_selection_key("1", tokens) is None
