from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bible_engine import lexicon_translation_workflow as workflow
from bible_engine.greek_lexicon_repository import TBESG_DATABASE_ENV_VAR
from bible_engine.greek_token_repository import TAGNT_DATABASE_ENV_VAR
from bible_engine.lexicon_hu import load_hungarian_lexicon
from bible_engine.lexicon_translation_workflow import (
    export_untranslated_lexicon_batch,
    import_hungarian_lexicon_batch,
)
from bible_engine.tagnt_sqlite import create_schema as create_tagnt_schema
from bible_engine.tbesg_sqlite import create_schema as create_tbesg_schema


def test_export_json_structure_utf8_and_frequency_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    tagnt_db = _build_tagnt_db(tmp_path)
    _patch_hungarian_sources(monkeypatch, tmp_path, translated=("G0002",))
    output = tmp_path / "batch.json"

    report = export_untranslated_lexicon_batch(
        output,
        limit=3,
        tbesg_database_path=tbesg_db,
        tagnt_database_path=tagnt_db,
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert report.records_exported == 3
    assert data["schema_version"] == "1.0"
    assert data["source"] == "STEPBible TBESG"
    assert data["batch"] == {"limit": 3, "offset": 0, "order_by": "nt_frequency"}
    assert [record["strong_id"] for record in data["records"]] == [
        "G0004",
        "G0001",
        "G0003",
    ]
    assert data["records"][0]["lemma"] == "δέλτα"
    assert data["records"][0]["primary_gloss_hu"] == ""
    assert data["records"][0]["senses_hu"] == []
    assert data["records"][0]["review_status"] == "draft"
    assert data["records"][0]["translation_method"] == "ai_assisted"
    assert data["records"][0]["meaning_plain_en"]
    assert len(data["records"][0]["meaning_plain_en"]) <= 2503


def test_export_falls_back_to_strong_order_when_tagnt_database_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    _patch_hungarian_sources(monkeypatch, tmp_path, translated=("G0002",))
    output = tmp_path / "batch.json"

    report = export_untranslated_lexicon_batch(
        output,
        limit=3,
        tbesg_database_path=tbesg_db,
        tagnt_database_path=tmp_path / "missing.sqlite3",
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert report.warnings
    assert [record["strong_id"] for record in data["records"]] == [
        "G0001",
        "G0003",
        "G0004",
    ]


def test_export_limit_offset_and_strong_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    tagnt_db = _build_tagnt_db(tmp_path)
    _patch_hungarian_sources(monkeypatch, tmp_path, translated=())
    output = tmp_path / "batch.json"

    export_untranslated_lexicon_batch(
        output,
        limit=2,
        offset=1,
        tbesg_database_path=tbesg_db,
        tagnt_database_path=tagnt_db,
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert [record["strong_id"] for record in data["records"]] == ["G0004", "G0001"]
    assert data["records"][1]["nt_frequency"] == 10


def test_import_success_is_compatible_with_existing_hungarian_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    monkeypatch.setenv(TBESG_DATABASE_ENV_VAR, str(tbesg_db))
    batch = _write_translated_batch(tmp_path, "G0001", "ἀλφα", "első", ["első", "kezdet"])
    output = tmp_path / "lexicon_hu.json"

    report = import_hungarian_lexicon_batch(batch, output_path=output)
    entries = load_hungarian_lexicon(output)

    assert report.records_imported == 1
    assert report.errors == ()
    assert entries["G0001"].primary_gloss == "első"
    assert entries["G0001"].senses == ("első", "kezdet")


def test_import_rejects_missing_gloss_empty_senses_bad_lemma_and_bad_strong(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    monkeypatch.setenv(TBESG_DATABASE_ENV_VAR, str(tbesg_db))
    batch = tmp_path / "bad_batch.json"
    data = _batch_data(
        [
            _translated_record("G0001", "ἀλφα", "", ["első"]),
            _translated_record("G0003", "γάμμα", "harmadik", []),
            _translated_record("G0004", "rossz", "negyedik", ["negyedik"]),
            _translated_record("H0001", "héber", "rossz", ["rossz"]),
        ]
    )
    batch.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    report = import_hungarian_lexicon_batch(batch, output_path=tmp_path / "out.json")

    assert report.records_imported == 0
    assert report.records_skipped == 4
    assert len(report.errors) == 4
    assert any("primary_gloss_hu" in error for error in report.errors)
    assert any("senses_hu" in error for error in report.errors)
    assert any("lemma mismatch" in error for error in report.errors)
    assert any("Hebrew id" in error for error in report.errors)


def test_import_reports_duplicate_records_and_unknown_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    monkeypatch.setenv(TBESG_DATABASE_ENV_VAR, str(tbesg_db))
    batch = tmp_path / "duplicate.json"
    batch.write_text(
        json.dumps(
            _batch_data(
                [
                    _translated_record("G0001", "ἀλφα", "első", ["első"]),
                    _translated_record("G0001", "ἀλφα", "első", ["első"]),
                ]
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = import_hungarian_lexicon_batch(batch, output_path=tmp_path / "out.json")
    assert report.records_imported == 1
    assert report.records_skipped == 1
    assert any("duplicate strong_id" in error for error in report.errors)

    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text(
        json.dumps({"schema_version": "9.9", "records": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        import_hungarian_lexicon_batch(bad_schema, output_path=tmp_path / "out.json")


def test_import_draft_does_not_overwrite_reviewed_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    monkeypatch.setenv(TBESG_DATABASE_ENV_VAR, str(tbesg_db))
    output = tmp_path / "lexicon_hu.json"
    output.write_text(
        json.dumps(
            [
                {
                    "strong_id": "G0001",
                    "lemma": "ἀλφα",
                    "primary_gloss": "ellenőrzött",
                    "senses": ["ellenőrzött"],
                    "note": None,
                    "source": "teszt",
                    "review_status": "reviewed",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    batch = _write_translated_batch(tmp_path, "G0001", "ἀλφα", "első", ["első"])

    first = import_hungarian_lexicon_batch(batch, output_path=output)
    second = import_hungarian_lexicon_batch(batch, output_path=output)
    entries = load_hungarian_lexicon(output)

    assert first.records_imported == 0
    assert first.warnings
    assert second.records_imported == 0
    assert entries["G0001"].primary_gloss == "ellenőrzött"


def test_import_rejects_placeholders_unknown_fields_and_bad_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    monkeypatch.setenv(TBESG_DATABASE_ENV_VAR, str(tbesg_db))
    record = _translated_record("G0001", "ἀλφα", "TODO", ["első"])
    record["unexpected"] = "nope"
    record["senses_hu"] = "első"
    batch = tmp_path / "bad.json"
    batch.write_text(json.dumps(_batch_data([record]), ensure_ascii=False), encoding="utf-8")

    report = import_hungarian_lexicon_batch(batch, output_path=tmp_path / "out.json")

    assert report.records_imported == 0
    assert report.errors

    placeholder_batch = tmp_path / "placeholder.json"
    placeholder_batch.write_text(
        json.dumps(
            _batch_data([_translated_record("G0001", "ἀλφα", "TODO", ["első"])]),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    placeholder_report = import_hungarian_lexicon_batch(
        placeholder_batch,
        output_path=tmp_path / "placeholder_out.json",
    )

    assert placeholder_report.records_imported == 0
    assert any("placeholder" in error for error in placeholder_report.errors)


def test_workflow_does_not_use_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tbesg_db = _build_tbesg_db(tmp_path)
    tagnt_db = _build_tagnt_db(tmp_path)
    _patch_hungarian_sources(monkeypatch, tmp_path, translated=())

    def fail_network(*_args, **_kwargs):
        raise AssertionError("network access must not be used")

    monkeypatch.setattr("socket.create_connection", fail_network)

    export_untranslated_lexicon_batch(
        tmp_path / "batch.json",
        limit=1,
        tbesg_database_path=tbesg_db,
        tagnt_database_path=tagnt_db,
    )


def _build_tbesg_db(tmp_path: Path) -> Path:
    database = tmp_path / "tbesg.sqlite3"
    with sqlite3.connect(database) as connection:
        create_tbesg_schema(connection)
        for strong_id, lemma, gloss, meaning, source_version in (
            ("G0001", "ἀλφα", "alpha", "Greek α meaning text.", "test"),
            ("G0002", "βῆτα", "beta", "Greek β meaning text.", "test"),
            ("G0003", "γάμμα", "gamma", "Greek γ meaning text.", "test"),
            ("G0004", "δέλτα", "delta", "Greek δ meaning text." * 200, "test"),
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
                    gloss,
                    meaning,
                    meaning,
                    json.dumps((meaning,), ensure_ascii=False),
                    json.dumps((), ensure_ascii=False),
                    "STEPBible TBESG",
                    source_version,
                    "2026-01-01T00:00:00+00:00",
                ),
            )
    return database


def _build_tagnt_db(tmp_path: Path) -> Path:
    database = tmp_path / "tagnt.sqlite3"
    with sqlite3.connect(database) as connection:
        create_tagnt_schema(connection)
        rows = [
            ("G0004", 12),
            ("G1", 10),
            ("G0003", 5),
            ("G0002", 20),
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


def _patch_hungarian_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    translated: tuple[str, ...],
) -> None:
    sample = tmp_path / "lexicon_hu_sample.json"
    entries = [
        {
            "strong_id": strong_id,
            "lemma": "βῆτα" if strong_id == "G0002" else "lemma",
            "primary_gloss": "magyar",
            "senses": ["magyar"],
            "note": None,
            "source": "teszt",
            "review_status": "draft",
        }
        for strong_id in translated
    ]
    sample.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(workflow, "LEXICON_HU_SAMPLE_PATH", sample)
    monkeypatch.setattr(workflow, "DEFAULT_LEXICON_HU_PATH", tmp_path / "missing_hu.json")


def _batch_data(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "source": "STEPBible TBESG",
        "batch": {"limit": len(records), "offset": 0, "order_by": "nt_frequency"},
        "records": records,
    }


def _translated_record(
    strong_id: str,
    lemma: str,
    primary_gloss_hu: str,
    senses_hu: list[str],
) -> dict[str, object]:
    return {
        "strong_id": strong_id,
        "lemma": lemma,
        "transliteration": lemma,
        "morph": "G:N",
        "gloss_en": "english",
        "meaning_plain_en": "English source text.",
        "nt_frequency": 1,
        "primary_gloss_hu": primary_gloss_hu,
        "senses_hu": senses_hu,
        "note_hu": "jegyzet" if primary_gloss_hu else "",
        "review_status": "draft",
        "translation_method": "ai_assisted",
        "source_name": "STEPBible TBESG",
        "source_version": "test",
    }


def _write_translated_batch(
    tmp_path: Path,
    strong_id: str,
    lemma: str,
    primary_gloss_hu: str,
    senses_hu: list[str],
) -> Path:
    batch = tmp_path / "translated.json"
    batch.write_text(
        json.dumps(
            _batch_data(
                [_translated_record(strong_id, lemma, primary_gloss_hu, senses_hu)]
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return batch
