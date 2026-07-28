from __future__ import annotations

import unicodedata
from pathlib import Path

from bible_engine.hebrew_parser import parse_tahot_row, parse_tahot_rows, strip_hebrew_accents


FIXTURE = Path(__file__).parent / "fixtures" / "tahot_ruth_psa_sample.tsv"


def _line(prefix: str) -> str:
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line
    raise AssertionError(f"missing fixture row: {prefix}")


def test_simple_hebrew_token_with_niqqud_and_cantillation() -> None:
    token = parse_tahot_row(_line("Rut.1.1#03="))

    assert token.stable_key == "Rut:1:1:3"
    assert token.surface == unicodedata.normalize("NFC", "שְׁפֹ֣ט")
    assert unicodedata.is_normalized("NFC", token.surface)
    assert token.surface_without_accents == "שפט"
    assert token.core_component
    assert token.core_component.strong_id == "H8199"
    assert token.language == "hebrew"


def test_prefix_word_keeps_prefix_and_core_components() -> None:
    token = parse_tahot_row(_line("Rut.1.1#01="))

    assert token.surface.startswith("וַ/")
    assert [item.strong_id for item in token.prefix_components] == ["H9001"]
    assert token.core_component and token.core_component.strong_id == "H1961"
    assert token.morphology_code == "Hc/Vqw3ms"


def test_suffix_word_keeps_suffix_component() -> None:
    token = parse_tahot_row(_line("Psa.23.1#04="))

    assert token.core_component and token.core_component.strong_id == "H7462B"
    assert [item.strong_id for item in token.suffix_components] == ["H9020"]
    assert token.suffix_components[0].morphology_code == "Sp1bs"


def test_maqaf_and_punctuation_are_preserved() -> None:
    token = parse_tahot_row(_line("Rut.4.13#03="))

    assert token.maqaf
    assert "־" in token.surface
    assert "H9014" in token.strong_ids


def test_ketiv_qere_variant_is_not_flattened() -> None:
    token = parse_tahot_row(_line("Rut.3.14#02=Q"))

    assert token.source_edition == "Q(K)"
    assert token.qere
    assert token.ketiv
    assert token.ketiv != token.qere
    assert "H4772" in token.strong_ids


def test_multiple_verses_are_sorted_by_source_order() -> None:
    tokens = parse_tahot_rows(FIXTURE.read_text(encoding="utf-8"), books={"Rut"})
    passage = [token for token in tokens if token.chapter == 1 and 1 <= token.verse <= 5]

    assert passage[0].stable_key == "Rut:1:1:1"
    assert passage == sorted(passage, key=lambda item: (item.chapter, item.verse, item.word_index))


def test_unicode_normalization_and_accent_stripping() -> None:
    assert strip_hebrew_accents("יְהוָ֥ה") == "יהוה"
    assert unicodedata.is_normalized("NFC", parse_tahot_row(_line("Psa.23.1#03=")).surface)
