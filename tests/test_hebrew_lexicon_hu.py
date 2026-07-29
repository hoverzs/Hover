from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository, load_hebrew_hungarian_lexicon
from bible_engine.hebrew_sqlite import DEFAULT_TBESH_DATABASE_PATH
from bible_engine.hebrew_sqlite import import_hebrew_fixture_database


FIXTURES = Path(__file__).parent / "fixtures"
TAHOT = FIXTURES / "tahot_ruth_psa_sample.tsv"
TBESH = FIXTURES / "tbesh_ruth_psa_sample.tsv"


def test_loads_direct_hungarian_record(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    lexicon = _write_hu(tmp_path, "H1961", "lenni")

    repo = HebrewHungarianLexiconRepository(lexicon, tbesh_database_path=database, alias_path=tmp_path / "missing.json")
    result = repo.lookup("H1961")

    assert result.resolution_type == "direct"
    assert result.entry is not None
    assert result.entry.base_meaning_hu == "lenni"
    assert result.review_status == "draft"
    assert result.translation_method == "ai_assisted"


def test_resolves_hungarian_alias_and_preserves_status(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    lexicon = _write_hu(tmp_path, "H1961", "lenni", review_status="reviewed")
    aliases = tmp_path / "aliases.json"
    aliases.write_text(
        json.dumps({"H1961Z": "H1961"}),
        encoding="utf-8",
    )

    result = HebrewHungarianLexiconRepository(lexicon, tbesh_database_path=database, alias_path=aliases).lookup("H1961Z")

    assert result.resolution_type == "alias"
    assert result.resolved_strong_id == "H1961"
    assert result.review_status == "reviewed"
    assert result.warnings


def test_direct_hungarian_record_has_priority_over_alias(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    lexicon = tmp_path / "hebrew_lexicon_hu.json"
    lexicon.write_text(
        json.dumps([_record("H1961", "lenni"), _record("H1961Z", "közvetlen")], ensure_ascii=False),
        encoding="utf-8",
    )
    aliases = tmp_path / "aliases.json"
    aliases.write_text(json.dumps({"H1961Z": "H1961"}), encoding="utf-8")

    result = HebrewHungarianLexiconRepository(lexicon, tbesh_database_path=database, alias_path=aliases).lookup("H1961Z")

    assert result.resolution_type == "direct"
    assert result.resolved_strong_id == "H1961Z"
    assert result.entry is not None
    assert result.entry.base_meaning_hu == "közvetlen"
    assert not result.warnings


def test_uses_tbesh_fallback_and_missing_state(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    repo = HebrewHungarianLexiconRepository(empty, tbesh_database_path=database, alias_path=tmp_path / "missing.json")

    fallback = repo.lookup("H1961")
    missing = repo.lookup("H9999")

    assert fallback.resolution_type == "tbesh_fallback"
    assert fallback.tbesh_fallback is not None
    assert fallback.tbesh_fallback.entry is not None
    assert fallback.warnings
    assert missing.resolution_type == "missing"


def test_rejects_duplicate_or_invalid_production_entries(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    records = [_record("H1961", "lenni"), _record("H1961", "létezni")]
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    try:
        load_hebrew_hungarian_lexicon(path)
    except ValueError as exc:
        assert "Duplicate" in str(exc)
    else:
        raise AssertionError("duplicate Strong ID must be rejected")


def test_accepts_documented_mixed_language_record(tmp_path: Path) -> None:
    path = tmp_path / "mixed.json"
    record = _record("H1961", "lenni")
    record["language"] = "mixed"
    path.write_text(json.dumps([record], ensure_ascii=False), encoding="utf-8")

    entries = load_hebrew_hungarian_lexicon(path)

    assert entries["H1961"].language == "mixed"


def test_runtime_loads_imported_pilot_records_without_fallback() -> None:
    batch = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0001_hu.json").read_text(encoding="utf-8"))["records"]
    aramaic_id = next(record["strong_id"] for record in batch if record["language"] == "aramaic")
    mixed_id = next(record["strong_id"] for record in batch if record["language"] == "mixed")
    repo = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)

    required = ["H1961", "H0776G", "H1696G", "H1697G", "H5650", "H6944G", aramaic_id, mixed_id]
    results = {strong_id: repo.lookup(strong_id) for strong_id in required}

    assert all(result.resolution_type == "direct" for result in results.values())
    assert all(result.entry is not None for result in results.values())
    assert results[aramaic_id].entry.language == "aramaic"
    assert results[mixed_id].entry.language == "mixed"


def test_all_imported_pilot_records_are_runtime_direct_hits() -> None:
    batch = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0001_hu.json").read_text(encoding="utf-8"))["records"]
    repo = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)
    results = [repo.lookup(record["strong_id"]) for record in batch]

    assert len(results) == 100
    assert sum(result.resolution_type == "direct" for result in results) == 100
    assert not any(result.resolution_type == "tbesh_fallback" for result in results)
    assert not any(result.resolution_type == "missing" for result in results)


def test_post_0008_missing_id_audit_promotes_only_safe_alias() -> None:
    audit = json.loads(Path("data/generated/hebrew_missing_ids_after_aliases_0008.json").read_text(encoding="utf-8"))
    batch = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_missing_ids_0001.json").read_text(encoding="utf-8"))
    translation_audit = json.loads(
        Path("data/generated/hebrew_lexicon_missing_ids_0001_translation_audit.json").read_text(encoding="utf-8")
    )
    aliases = json.loads(Path("bible_engine/data/hebrew_strong_aliases.json").read_text(encoding="utf-8"))

    records = {record["strong_step_id"]: record for record in audit["records"]}
    batch_ids = {record["strong_id"] for record in batch["records"]}

    assert audit["previous_missing_id_count"] == 13
    assert audit["category_counts"] == {"missing_translation_record": 12, "safe_alias": 1}
    assert records["H0430J"]["category"] == "safe_alias"
    assert aliases["H0430J"] == "H0430G"
    assert batch["batch"]["record_count"] == 12
    assert "H0430J" not in batch_ids
    assert set(records) - {"H0430J"} == batch_ids
    assert translation_audit["validation"]["all_require_separate_hungarian_record"]
    assert translation_audit["validation"]["production_overlap_count"] == 0
    assert translation_audit["validation"]["alias_source_overlap_count"] == 0
    assert translation_audit["validation"]["technical_or_parser_residue_count"] == 0


def test_missing_id_translation_import_resolves_all_remaining_missing_ids() -> None:
    coverage = json.loads(
        Path("data/generated/hebrew_runtime_coverage_after_missing_translation_0001.json").read_text(encoding="utf-8")
    )
    repo = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)
    expected = {
        "H1247G": "leszármazott",
        "H1247H": "fiatal állat",
        "H1247I": "valaminek a fia",
        "H1247J": "fiú",
        "H1940G": "Hódijjá",
        "H3243G": "szopik",
        "H3243H": "szoptat",
        "H3243I": "dajka",
        "H3243J": "csecsemő",
        "H3431G": "Jisbáh",
        "H5892I": "város",
        "H7417I": "Rimmón",
    }

    results = {strong_id: repo.lookup(strong_id) for strong_id in expected}

    assert coverage["production_lexicon_record_count"] == 6493
    assert coverage["lexeme_coverage"]["direct"] == 6493
    assert coverage["lexeme_coverage"]["alias"] == 127
    assert coverage["lexeme_coverage"].get("missing", 0) == 0
    assert coverage["token_coverage"].get("missing", 0) == 0
    assert coverage["resolved_previous_missing_id_count"] == 12
    assert coverage["resolved_previous_missing_token_count"] == 53
    assert not coverage["unresolved_strong_ids"]
    assert all(result.resolution_type == "direct" for result in results.values())
    assert {strong_id: result.entry.base_meaning_hu for strong_id, result in results.items() if result.entry} == expected


def test_demo_lexical_panel_uses_hungarian_record_without_english_fallback(monkeypatch) -> None:
    import hebrew_text_demo

    calls: list[tuple[str, str]] = []

    class FakeStreamlit:
        def markdown(self, text: str) -> None:
            calls.append(("markdown", text))

        def caption(self, text: str) -> None:
            calls.append(("caption", text))

        def info(self, text: str) -> None:
            calls.append(("info", text))

        def warning(self, text: str) -> None:
            calls.append(("warning", text))

    hu_entry = SimpleNamespace(
        base_meaning_hu="lenni",
        possible_meanings_hu=("lenni", "válni"),
        lexical_note_hu="Magyar lexikai megjegyzés.",
        review_status="draft",
        translation_method="ai_assisted",
        source="STEPBible TBESH alapján készített magyar munkaváltozat",
    )
    hu_lookup = SimpleNamespace(entry=hu_entry, warnings=())
    tbesh_lookup = SimpleNamespace(core=SimpleNamespace(entry=SimpleNamespace(gloss="to be", meaning="English fallback")))
    monkeypatch.setattr(hebrew_text_demo, "st", FakeStreamlit())

    hebrew_text_demo.render_lexical_panel(hu_lookup, tbesh_lookup)
    rendered = "\n".join(text for _, text in calls)

    assert "Alapjelentés" in rendered
    assert "Lehetséges jelentések" in rendered
    assert "Lexikai megjegyzés" in rendered
    assert "Ellenőrzési állapot" in rendered
    assert "Forrás" in rendered
    assert "angol TBESH fallback" not in rendered
    assert "English fallback" not in rendered


def test_demo_lexical_panel_shows_hungarian_alias_warning(monkeypatch) -> None:
    import hebrew_text_demo

    calls: list[tuple[str, str]] = []

    class FakeStreamlit:
        def markdown(self, text: str) -> None:
            calls.append(("markdown", text))

        def caption(self, text: str) -> None:
            calls.append(("caption", text))

        def info(self, text: str) -> None:
            calls.append(("info", text))

        def warning(self, text: str) -> None:
            calls.append(("warning", text))

    hu_entry = SimpleNamespace(
        base_meaning_hu="lenni",
        possible_meanings_hu=("lenni",),
        lexical_note_hu="",
        review_status="draft",
        translation_method="ai_assisted",
        source="STEPBible TBESH alapján készített magyar munkaváltozat",
    )
    hu_lookup = SimpleNamespace(
        entry=hu_entry,
        warnings=("Magyar lexikai rekord alias alapján: H1961Z → H1961",),
    )
    tbesh_lookup = SimpleNamespace(core=SimpleNamespace(entry=None))
    monkeypatch.setattr(hebrew_text_demo, "st", FakeStreamlit())

    hebrew_text_demo.render_lexical_panel(hu_lookup, tbesh_lookup)
    rendered = "\n".join(text for _, text in calls)

    assert "Magyar lexikai rekord alias alapján: H1961Z → H1961" in rendered


def _write_hu(tmp_path: Path, strong_id: str, base: str, *, review_status: str = "draft") -> Path:
    path = tmp_path / "hebrew_lexicon_hu.json"
    path.write_text(
        json.dumps([_record(strong_id, base, review_status=review_status)], ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _record(strong_id: str, base: str, *, review_status: str = "draft") -> dict[str, object]:
    return {
        "strong_id": strong_id,
        "lemma": "הָיָה",
        "transliteration": "ha.yah",
        "language": "hebrew",
        "base_meaning_hu": base,
        "possible_meanings_hu": [base],
        "lexical_note_hu": "",
        "source_gloss_en": "to be",
        "source_note_en": "to be",
        "translation_method": "ai_assisted",
        "review_status": review_status,
        "source": "STEPBible TBESH alapján készített magyar munkaváltozat",
        "source_record_id": strong_id,
        "aliases": [],
        "warnings": [],
    }
