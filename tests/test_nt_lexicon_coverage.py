from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bible_engine.nt_lexicon_coverage import (
    audit_nt_lexicon_coverage,
    collect_tagnt_strong_frequencies,
    export_nt_missing_lexicon_batch,
    normalize_tagnt_strong_ids,
)
from bible_engine.tagnt_sqlite import create_schema as create_tagnt_schema
from bible_engine.tbesg_sqlite import create_schema as create_tbesg_schema


def test_tagnt_strong_id_normalization_handles_padding_suffixes_and_alternates() -> None:
    assert normalize_tagnt_strong_ids("G123") == ("G0123",)
    assert normalize_tagnt_strong_ids("g0123") == ("G0123",)
    assert normalize_tagnt_strong_ids("G3004G") == ("G3004G",)
    assert normalize_tagnt_strong_ids("G123/G456, G0123 + G3004G") == (
        "G0123",
        "G0456",
        "G3004G",
    )
    assert normalize_tagnt_strong_ids("") == ()
    assert normalize_tagnt_strong_ids(None) == ()
    assert normalize_tagnt_strong_ids("H0001") == ()


def test_collect_tagnt_strong_frequencies_deduplicates_and_counts_missing_tokens(
    tmp_path: Path,
) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)

    report = collect_tagnt_strong_frequencies(tagnt_db)

    assert report.token_count == 22
    assert report.missing_strong_token_count == 1
    assert report.frequencies["G0001"] == 4
    assert report.frequencies["G0004"] == 5
    assert report.frequencies["G0002"] == 10


def test_audit_reports_nt_hungarian_and_tbesg_coverage(tmp_path: Path) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)
    tbesg_db = _build_tbesg_db(tmp_path)
    hungarian = _write_hungarian_lexicon(tmp_path, ("G0002", "G0003", "G7777"))
    output = tmp_path / "coverage.json"

    report = audit_nt_lexicon_coverage(
        output_path=output,
        tagnt_database_path=tagnt_db,
        tbesg_database_path=tbesg_db,
        hungarian_lexicon_path=hungarian,
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert report.summary["tagnt_total_tokens"] == 22
    assert report.summary["tagnt_unique_strong_ids"] == 5
    assert report.summary["tagnt_tokens_without_strong_id"] == 1
    assert report.summary["tagnt_strong_ids_found_in_tbesg"] == 4
    assert report.summary["tagnt_strong_ids_missing_from_tbesg"] == 1
    assert report.summary["tagnt_strong_ids_found_in_hungarian"] == 2
    assert report.summary["tagnt_strong_ids_missing_from_hungarian"] == 3
    assert report.summary["tagnt_tokens_with_hungarian_lexicon"] == 12
    assert report.summary["tagnt_tokens_without_hungarian_lexicon"] == 9
    assert data["missing_tbesg_strong_ids"] == ["G9999"]
    assert data["hungarian_strong_ids_not_used_in_nt"] == ["G7777"]


def test_audit_can_count_runtime_aliases_as_effective_hungarian_coverage(
    tmp_path: Path,
) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)
    tbesg_db = _build_tbesg_db(tmp_path)
    hungarian = _write_hungarian_lexicon(tmp_path, ("G0002", "G0003"))
    aliases = _write_aliases(tmp_path, source="G9999", target="G0003")
    output = tmp_path / "coverage.json"

    audit_nt_lexicon_coverage(
        output_path=output,
        tagnt_database_path=tagnt_db,
        tbesg_database_path=tbesg_db,
        hungarian_lexicon_path=hungarian,
        strong_aliases_path=aliases,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    summary = data["summary"]

    assert summary["direct_hungarian_token_count"] == 12
    assert summary["direct_hungarian_lexeme_count"] == 2
    assert summary["alias_hungarian_token_count"] == 1
    assert summary["alias_hungarian_lexeme_count"] == 1
    assert summary["effective_tokens_with_hungarian_lexicon"] == 13
    assert "G9999" in data["alias_hungarian_coverage"]["strong_ids"]
    assert "G9999" not in data["unresolved_strong_ids"]


def test_nt_missing_export_filters_translated_lxx_only_and_missing_tbesg(
    tmp_path: Path,
) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)
    tbesg_db = _build_tbesg_db(tmp_path)
    hungarian = _write_hungarian_lexicon(tmp_path, ("G0002", "G0003"))
    output = tmp_path / "nt_missing.json"

    report = export_nt_missing_lexicon_batch(
        output_path=output,
        limit=10,
        offset=0,
        tagnt_database_path=tagnt_db,
        tbesg_database_path=tbesg_db,
        hungarian_lexicon_path=hungarian,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    records = data["records"]

    assert report.total_missing_nt_records == 3
    assert report.records_exported == 2
    assert report.warnings == ("TBESG source record not found: G9999",)
    assert [record["strong_id"] for record in records] == ["G0004", "G0001"]
    assert [record["nt_frequency"] for record in records] == [5, 4]
    assert "G0002" not in {record["strong_id"] for record in records}
    assert "G0003" not in {record["strong_id"] for record in records}
    assert "G21464" not in {record["strong_id"] for record in records}
    assert data["source"] == "STEPBible TBESG + TAGNT coverage"
    assert data["batch"] == {
        "source": "STEPBible TBESG + TAGNT coverage",
        "limit": 10,
        "offset": 0,
        "order_by": "tagnt_token_frequency",
        "total_missing_nt_records": 3,
    }
    assert set(records[0]) == {
        "strong_id",
        "lemma",
        "transliteration",
        "morph",
        "gloss_en",
        "meaning_plain_en",
        "nt_frequency",
        "primary_gloss_hu",
        "senses_hu",
        "note_hu",
        "review_status",
        "translation_method",
        "source_name",
        "source_version",
    }
    assert records[0]["primary_gloss_hu"] == ""
    assert records[0]["senses_hu"] == []
    assert records[0]["source_name"] == "STEPBible TBESG"


def test_nt_missing_export_limit_offset_and_validation_guards(tmp_path: Path) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)
    tbesg_db = _build_tbesg_db(tmp_path)
    hungarian = _write_hungarian_lexicon(tmp_path, ())
    output = tmp_path / "nt_missing.json"

    report = export_nt_missing_lexicon_batch(
        output_path=output,
        limit=1,
        offset=1,
        tagnt_database_path=tagnt_db,
        tbesg_database_path=tbesg_db,
        hungarian_lexicon_path=hungarian,
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert report.records_exported == 1
    assert data["records"][0]["strong_id"] == "G0004"

    with pytest.raises(ValueError, match="limit"):
        export_nt_missing_lexicon_batch(output_path=output, limit=0)
    with pytest.raises(ValueError, match="offset"):
        export_nt_missing_lexicon_batch(output_path=output, offset=-1)


def _build_tbesg_db(tmp_path: Path) -> Path:
    database = tmp_path / "tbesg.sqlite3"
    with sqlite3.connect(database) as connection:
        create_tbesg_schema(connection)
        for strong_id, lemma, frequency_rank in (
            ("G0001", "alpha", 1),
            ("G0002", "beta", 2),
            ("G0003", "gamma", 3),
            ("G0004", "delta", 4),
            ("G21464", "lxx only", 5),
        ):
            connection.execute(
                """
                INSERT INTO greek_lexicon (
                    strong_id,
                    dstrong_id,
                    ustrong_id,
                    lemma,
                    lemma_normalized,
                    transliteration,
                    morph,
                    gloss,
                    meaning_raw,
                    meaning_plain,
                    meaning_paragraphs_json,
                    references_json,
                    source_name,
                    source_version,
                    imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strong_id,
                    f"{strong_id} =",
                    strong_id,
                    lemma,
                    lemma.casefold(),
                    lemma,
                    "G:N",
                    f"gloss {frequency_rank}",
                    f"meaning {frequency_rank}",
                    f"meaning {frequency_rank}",
                    json.dumps((f"meaning {frequency_rank}",), ensure_ascii=False),
                    json.dumps((), ensure_ascii=False),
                    "STEPBible TBESG",
                    "test",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
    return database


def _build_tagnt_db(tmp_path: Path) -> Path:
    database = tmp_path / "tagnt.sqlite3"
    with sqlite3.connect(database) as connection:
        create_tagnt_schema(connection)
        rows = [
            ("G0002", 10),
            ("G0004", 4),
            ("G1", 3),
            ("G0003", 2),
            ("G0004/G0001", 1),
            ("G9999", 1),
            ("", 1),
        ]
        word_index = 1
        for strong_id, frequency in rows:
            for _ in range(frequency):
                connection.execute(
                    """
                    INSERT INTO greek_tokens (
                        book,
                        chapter,
                        verse,
                        word_index,
                        greek_form,
                        lemma,
                        morph_code,
                        strong_id,
                        edition_flags,
                        source_name,
                        source_version,
                        imported_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Mat",
                        1,
                        1,
                        word_index,
                        "λέξη",
                        "λέξη",
                        "N-NSF",
                        strong_id,
                        "NKO",
                        "test",
                        "test",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )
                word_index += 1
    return database


def _write_hungarian_lexicon(tmp_path: Path, strong_ids: tuple[str, ...]) -> Path:
    output = tmp_path / "lexicon_hu.json"
    output.write_text(
        json.dumps(
            [
                {
                    "strong_id": strong_id,
                    "lemma": f"lemma {strong_id}",
                    "primary_gloss": "magyar",
                    "senses": ["magyar"],
                    "note": None,
                    "source": "teszt",
                    "review_status": "draft",
                }
                for strong_id in strong_ids
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def _write_aliases(tmp_path: Path, *, source: str, target: str) -> Path:
    output = tmp_path / "aliases.json"
    output.write_text(
        json.dumps(
            [
                {
                    "source_strong_id": source,
                    "target_strong_id": target,
                    "confidence": 0.99,
                    "evidence": "test alias",
                    "token_frequency": 1,
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output
