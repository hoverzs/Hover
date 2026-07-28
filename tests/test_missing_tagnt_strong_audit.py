from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bible_engine.lexicon_translation_workflow import import_hungarian_lexicon_batch
from bible_engine.missing_tagnt_strong_audit import (
    CLASS_ALIAS,
    CLASS_MISSING,
    CLASS_REVIEW,
    CLASS_SAME_LEMMA,
    audit_missing_tagnt_strong_ids,
    split_tagnt_suffix,
)
from bible_engine.tagnt_sqlite import create_schema as create_tagnt_schema
from bible_engine.tbesg_sqlite import create_schema as create_tbesg_schema


def test_g_h_suffix_and_base_extraction() -> None:
    assert split_tagnt_suffix("G0007G") == ("G0007", "G")
    assert split_tagnt_suffix("G0007H") == ("G0007", "H")
    assert split_tagnt_suffix("G7H") == ("G0007", "H")
    assert split_tagnt_suffix("G0007") == ("G0007", None)
    assert split_tagnt_suffix("bad") == (None, None)


def test_missing_tagnt_audit_classifies_aliases_missing_and_review(tmp_path: Path) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)
    tbesg_db = _build_tbesg_db(tmp_path)
    hungarian = _write_hungarian(tmp_path)
    coverage = _write_coverage(tmp_path, ["G0001G", "G0002G", "G0004G", "G0006G", "G99999G"])

    result = audit_missing_tagnt_strong_ids(
        coverage_report_path=coverage,
        tagnt_database_path=tagnt_db,
        tbesg_database_path=tbesg_db,
        hungarian_lexicon_path=hungarian,
        audit_output_path=tmp_path / "audit.json",
        alias_output_path=tmp_path / "aliases.json",
        unresolved_export_path=tmp_path / "unresolved.json",
    )
    audit = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    aliases = json.loads((tmp_path / "aliases.json").read_text(encoding="utf-8"))["records"]
    unresolved = json.loads((tmp_path / "unresolved.json").read_text(encoding="utf-8"))
    by_id = {record["strong_id"]: record for record in audit["records"]}

    assert by_id["G0001G"]["classification"] == CLASS_ALIAS
    assert by_id["G0001G"]["alias_candidate"]["target_strong_id"] == "G0001"
    assert by_id["G0002G"]["classification"] == CLASS_SAME_LEMMA
    assert by_id["G0002G"]["alias_candidate"]["target_strong_id"] == "G0003"
    assert by_id["G0004G"]["classification"] == CLASS_MISSING
    assert by_id["G0006G"]["classification"] == CLASS_REVIEW
    assert by_id["G99999G"]["classification"] == "malformed_or_unknown"
    assert len({alias["source_strong_id"] for alias in aliases}) == len(aliases)
    assert result.alias_candidate_count == 2
    assert result.alias_token_frequency == 5
    assert unresolved["records"][0]["strong_id"] == "G0004G"
    assert unresolved["records"][0]["sample_references"] == ["Mat 1:1#6"]
    assert unresolved["records"][0]["source_name"] == "TAGNT unresolved lexeme audit"


def test_alias_is_blocked_when_base_lemma_differs_and_no_same_lemma_record(tmp_path: Path) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)
    tbesg_db = _build_tbesg_db(tmp_path, include_same_lemma_target=False)
    hungarian = _write_hungarian(tmp_path, include_same_lemma_target=False)
    coverage = _write_coverage(tmp_path, ["G0002G"])

    audit_missing_tagnt_strong_ids(
        coverage_report_path=coverage,
        tagnt_database_path=tagnt_db,
        tbesg_database_path=tbesg_db,
        hungarian_lexicon_path=hungarian,
        audit_output_path=tmp_path / "audit.json",
        alias_output_path=tmp_path / "aliases.json",
        unresolved_export_path=tmp_path / "unresolved.json",
    )
    aliases = json.loads((tmp_path / "aliases.json").read_text(encoding="utf-8"))["records"]
    record = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))["records"][0]

    assert aliases == []
    assert record["classification"] != CLASS_ALIAS


def test_unresolved_export_schema_can_be_imported_after_translation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tagnt_db = _build_tagnt_db(tmp_path)
    tbesg_db = _build_tbesg_db(tmp_path)
    hungarian = _write_hungarian(tmp_path)
    coverage = _write_coverage(tmp_path, ["G0004G"])

    audit_missing_tagnt_strong_ids(
        coverage_report_path=coverage,
        tagnt_database_path=tagnt_db,
        tbesg_database_path=tbesg_db,
        hungarian_lexicon_path=hungarian,
        audit_output_path=tmp_path / "audit.json",
        alias_output_path=tmp_path / "aliases.json",
        unresolved_export_path=tmp_path / "unresolved.json",
    )
    data = json.loads((tmp_path / "unresolved.json").read_text(encoding="utf-8"))
    data["records"][0]["primary_gloss_hu"] = "negyedik"
    data["records"][0]["senses_hu"] = ["negyedik"]
    translated = tmp_path / "translated.json"
    translated.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    report = import_hungarian_lexicon_batch(translated, output_path=tmp_path / "hu_out.json")

    assert report.records_imported == 1
    assert report.errors == ()


def _build_tbesg_db(tmp_path: Path, *, include_same_lemma_target: bool = True) -> Path:
    database = tmp_path / "tbesg.sqlite3"
    rows = [
        ("G0001", "ἄλφα", "G:N", "alpha"),
        ("G0002", "βῆτα", "G:N", "beta"),
    ]
    if include_same_lemma_target:
        rows.append(("G0003", "γάμμα", "G:N", "gamma"))
    with sqlite3.connect(database) as connection:
        create_tbesg_schema(connection)
        for strong_id, lemma, morph, gloss in rows:
            connection.execute(
                """
                INSERT INTO greek_lexicon (
                    strong_id, dstrong_id, ustrong_id, lemma, lemma_normalized,
                    transliteration, morph, gloss, meaning_raw, meaning_plain,
                    meaning_paragraphs_json, references_json, source_name,
                    source_version, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strong_id,
                    f"{strong_id} =",
                    strong_id,
                    lemma,
                    lemma.casefold(),
                    "",
                    morph,
                    gloss,
                    gloss,
                    gloss,
                    json.dumps((gloss,), ensure_ascii=False),
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
            ("G0001G", "ἄλφα", "ἄλφα", "N-NSN", "NKO"),
            ("G0001G", "ἄλφα", "ἄλφα", "N-ASN", "K"),
            ("G0002G", "γάμμα", "γάμμα", "N-NSN", "NKO"),
            ("G0002G", "γάμμα", "γάμμα", "N-GSN", "NKO"),
            ("G0002G", "γάμμα", "γάμμα", "N-DSN", "NKO"),
            ("G0004G", "δέλτα", "δέλτα", "N-NSN", "NKO"),
            ("G0006G", "ἕν", "εἷς", "A-NSN", "NKO"),
            ("G0006G", "μία", "εἷς2", "A-NSF", "NKO"),
        ]
        for index, (strong_id, form, lemma, morph, editions) in enumerate(rows, start=1):
            connection.execute(
                """
                INSERT INTO greek_tokens (
                    book, chapter, verse, word_index, greek_form, lemma,
                    morph_code, strong_id, edition_flags, source_name,
                    source_version, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Mat",
                    1,
                    1,
                    index,
                    form,
                    lemma,
                    morph,
                    strong_id,
                    editions,
                    "test",
                    "test",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
    return database


def _write_hungarian(
    tmp_path: Path,
    *,
    include_same_lemma_target: bool = True,
) -> Path:
    rows = [
        {
            "strong_id": "G0001",
            "lemma": "ἄλφα",
            "primary_gloss": "alfa",
            "senses": ["alfa"],
            "note": None,
            "source": "teszt",
            "review_status": "draft",
        }
    ]
    if include_same_lemma_target:
        rows.append(
            {
                "strong_id": "G0003",
                "lemma": "γάμμα",
                "primary_gloss": "gamma",
                "senses": ["gamma"],
                "note": None,
                "source": "teszt",
                "review_status": "draft",
            }
        )
    output = tmp_path / "lexicon_hu.json"
    output.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return output


def _write_coverage(tmp_path: Path, missing: list[str]) -> Path:
    output = tmp_path / "coverage.json"
    output.write_text(
        json.dumps(
            {
                "summary": {
                    "tagnt_total_tokens": 100,
                    "tagnt_tokens_with_hungarian_lexicon": 80,
                    "tagnt_unique_strong_ids": 20,
                    "tagnt_strong_ids_found_in_hungarian": 15,
                },
                "missing_tbesg_strong_ids": missing,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return output
