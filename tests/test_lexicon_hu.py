from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_engine.lexicon_hu import (
    HungarianLexiconEntry,
    get_hungarian_lexicon_entry,
    load_hungarian_lexicon,
    validate_hungarian_lexicon_entry,
)
from bible_engine.tagnt_parser import get_verse_tokens


ROOT = Path(__file__).parents[1]
LEXICON_FIXTURE = ROOT / "bible_engine" / "data" / "lexicon_hu_sample.json"
JHN_FIXTURE = ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"


def test_loads_three_sample_hungarian_lexicon_entries() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    assert set(entries) == {"G0025", "G2889", "G3779"}
    assert all(entry.review_status == "draft" for entry in entries.values())


def test_get_g0025_entry_by_normalized_and_short_strong_id() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    direct = get_hungarian_lexicon_entry(entries, "G0025")
    normalized = get_hungarian_lexicon_entry(entries, "G25")

    assert direct is not None
    assert normalized == direct
    assert direct.lemma == "ἀγαπάω"
    assert direct.primary_gloss == "szeret"
    assert direct.senses == (
        "szeret",
        "megbecsül",
        "jóindulattal viszonyul valakihez",
    )


def test_get_g2889_and_g3779_entries() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    kosmos = get_hungarian_lexicon_entry(entries, "G2889")
    houtos = get_hungarian_lexicon_entry(entries, "G3779")

    assert kosmos is not None
    assert kosmos.lemma == "κόσμος"
    assert kosmos.primary_gloss == "világ"
    assert "világegyetem" in kosmos.senses
    assert "dísz vagy ékesség" in kosmos.senses

    assert houtos is not None
    assert houtos.lemma == "οὕτως"
    assert houtos.primary_gloss == "így"
    assert "ennyire vagy ilyen mértékben" in houtos.senses


def test_utf8_characters_are_preserved() -> None:
    text = LEXICON_FIXTURE.read_text(encoding="utf-8")
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    assert "ἀγαπάω" in text
    assert "κόσμος" in text
    assert "οὕτως" in text
    assert entries["G2889"].note
    assert "teremtett világra" in entries["G2889"].note
    assert "szövegkörnyezettől" in entries["G0025"].note


def test_unknown_strong_id_returns_none() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    assert get_hungarian_lexicon_entry(entries, "G9999") is None


def test_duplicate_strong_id_is_rejected(tmp_path: Path) -> None:
    data = _sample_json_records()
    data.append(dict(data[0]))
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate Hungarian lexicon strong_id"):
        load_hungarian_lexicon(path)


def test_empty_primary_gloss_is_rejected() -> None:
    entry = _valid_entry(primary_gloss=" ")

    with pytest.raises(ValueError, match="primary_gloss"):
        validate_hungarian_lexicon_entry(entry)


def test_empty_or_duplicate_senses_are_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_hungarian_lexicon_entry(_valid_entry(senses=("szeret", " ")))

    with pytest.raises(ValueError, match="duplicates"):
        validate_hungarian_lexicon_entry(_valid_entry(senses=("szeret", "szeret")))


def test_invalid_review_status_is_rejected() -> None:
    entry = _valid_entry(review_status="needs-review")

    with pytest.raises(ValueError, match="review_status"):
        validate_hungarian_lexicon_entry(entry)


def test_invalid_strong_id_and_empty_source_are_rejected() -> None:
    with pytest.raises(ValueError, match="not normalized"):
        validate_hungarian_lexicon_entry(_valid_entry(strong_id="G25"))

    with pytest.raises(ValueError, match="source"):
        validate_hungarian_lexicon_entry(_valid_entry(source=" "))


def test_missing_file_raises_file_not_found_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        load_hungarian_lexicon(missing)


def test_invalid_json_has_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid Hungarian lexicon JSON"):
        load_hungarian_lexicon(path)


def test_missing_required_json_field_has_clear_error(tmp_path: Path) -> None:
    data = _sample_json_records()
    del data[0]["primary_gloss"]
    path = tmp_path / "missing-field.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing field 'primary_gloss'"):
        load_hungarian_lexicon(path)


def test_john_3_16_tokens_can_find_sample_hungarian_entries() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)
    tokens = get_verse_tokens(JHN_FIXTURE, book="Jhn", chapter=3, verse=16)
    tokens_by_strong = {token.strong_id: token for token in tokens}

    for strong_id in ("G0025", "G2889", "G3779"):
        token = tokens_by_strong[strong_id]
        entry = get_hungarian_lexicon_entry(entries, token.strong_id)

        assert entry is not None
        assert entry.strong_id == strong_id
        assert entry.lemma
        assert entry.senses


def _valid_entry(**overrides: object) -> HungarianLexiconEntry:
    values = {
        "strong_id": "G0025",
        "lemma": "ἀγαπάω",
        "primary_gloss": "szeret",
        "senses": ("szeret", "megbecsül"),
        "note": None,
        "source": "STEPBible TBESG alapján készített magyar munkaváltozat",
        "review_status": "draft",
    }
    values.update(overrides)
    return HungarianLexiconEntry(**values)


def _sample_json_records() -> list[dict[str, object]]:
    return json.loads(LEXICON_FIXTURE.read_text(encoding="utf-8"))
