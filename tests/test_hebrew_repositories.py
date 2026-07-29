from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository
from bible_engine.hebrew_lexicon_repository import HebrewLexiconRepository
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH, DEFAULT_TBESH_DATABASE_PATH, import_hebrew_fixture_database
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from hebrew_text_demo import _component_value, _display_lexical_note, build_hebrew_token_view_model


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


def test_repository_exposes_full_slash_morphology_fields(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    repository = HebrewTokenRepository(database)
    token = repository.passage("Rut", 1, 1).tokens[0]

    morphology = repository.morphology(
        token,
        {
            "Hc": "Function=Conjunction; Form=Consecutive",
            "HVqw3ms": "Function=Verb ; Stem=Qal ; Form=Consecutive Imperfect",
        },
    )

    assert token.morphology_code == "Hc/Vqw3ms"
    assert morphology.part_of_speech == "Conjunction + Verb"
    assert morphology.verb_stem == "Qal"
    assert morphology.verb_conjugation == "Consecutive Imperfect"
    assert morphology.person == "Third"
    assert morphology.gender == "Masculine"
    assert morphology.number == "Singular"
    assert morphology.components[1]["verb_stem"] == "Qal"


def test_demo_view_model_receives_full_decoded_morphology(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    token_repository = HebrewTokenRepository(database)
    token = token_repository.passage("Rut", 1, 1).tokens[0]
    morphology = token_repository.morphology(token)
    lookup = HebrewLexiconRepository(database, tmp_path / "missing_aliases.json").lookup_token(token)

    view_model = build_hebrew_token_view_model(token, morphology, lookup)

    assert view_model["morphology_code"] == "Hc/Vqw3ms"
    assert (
        view_model["morphology_summary"]
        == "héber; kötőszó + ige; qal törzs, wayyiqtol, harmadik személy, hímnem, egyes szám"
    )
    rows = dict(view_model["morphology_rows"])
    assert rows["Igetörzs"] == "qal"
    assert rows["Igealak"] == "wayyiqtol"
    assert rows["Személy"] == "harmadik személy"
    assert rows["Nem"] == "hímnem"
    assert rows["Szám"] == "egyes szám"
    components = view_model["components"]
    assert components[0]["role"] == "prefix"
    assert components[0]["role_label"] == "prefixum"
    assert components[0]["analysis_summary"] == "kötőszó"
    assert components[1]["role"] == "core"
    assert components[1]["role_label"] == "lexikai mag"
    assert components[1]["analysis_summary"] == "ige, qal törzs, wayyiqtol, harmadik személy, hímnem, egyes szám"


def test_demo_view_model_does_not_repeat_suffix_analysis_for_punctuation_components(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    token_repository = HebrewTokenRepository(database)
    token = next(
        token
        for token in token_repository.passage("Rut", 1, 5).tokens
        if token.morphology_code == "HC/R/Ncmsc/Sp3fs"
    )
    morphology = token_repository.morphology(token)

    view_model = build_hebrew_token_view_model(token, morphology, None)

    assert view_model["components"][3]["analysis_summary"] == "suffixum; egyes szám harmadik személy nőnem birtokos suffixummal"
    assert view_model["components"][4]["analysis_summary"] == ""


def test_genesis_1_1_heavens_token_uses_reader_facing_hebrew_display() -> None:
    token_repository = HebrewTokenRepository(DEFAULT_TAHOT_DATABASE_PATH)
    token = next(
        token
        for token in token_repository.passage("Gen", 1, 1).tokens
        if "H8064" in token.strong_ids
    )
    lexicon = HebrewLexiconRepository(DEFAULT_TBESH_DATABASE_PATH, Path("bible_engine/data/hebrew_strong_aliases.json"))
    hungarian_lexicon = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)

    view_model = build_hebrew_token_view_model(token, token_repository.morphology(token), lexicon.lookup_token(token))
    components = view_model["components"]
    prefix = components[0]
    core = components[1]
    lexical_note = _display_lexical_note(hungarian_lexicon.lookup("H8064").entry, view_model)

    assert view_model["display_surface"] == "הַשָּׁמַיִם"
    assert "/" not in view_model["display_surface"]
    assert prefix["display_surface"] == "הַ"
    assert _component_value(prefix).startswith("הַ־ — névelő")
    assert core["display_surface"] == "שָּׁמַיִם"
    assert view_model["language_label"] == "héber"
    assert "Arámi" not in lexical_note
    assert lexical_note == "Héber főnév. Az eget vagy mennyet jelöli; a pontos magyar alakot a szövegkörnyezet határozza meg."
    assert view_model["readable_transliteration"] == "haššāmayim"
    assert prefix["strong_id"] == "H9009"
    assert core["strong_id"] == "H8064"


def test_ruth_4_17_women_neighbors_token_uses_feminine_plural_noun_meaning() -> None:
    token_repository = HebrewTokenRepository(DEFAULT_TAHOT_DATABASE_PATH)
    token = next(
        token
        for token in token_repository.passage("Rut", 4, 17).tokens
        if "H7934" in token.strong_ids
    )
    lexicon = HebrewLexiconRepository(DEFAULT_TBESH_DATABASE_PATH, Path("bible_engine/data/hebrew_strong_aliases.json"))
    hungarian_lexicon = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)

    view_model = build_hebrew_token_view_model(token, token_repository.morphology(token), lexicon.lookup_token(token))
    rows = dict(view_model["morphology_rows"])
    entry = hungarian_lexicon.lookup("H7934").entry
    lexical_note = _display_lexical_note(entry, view_model)

    assert view_model["display_surface"] == "הַשְּׁכֵנוֹת"
    assert view_model["language_label"] == "héber"
    assert rows["Nem"] == "nőnem"
    assert rows["Szám"] == "többes szám"
    assert entry.base_meaning_hu == "szomszédasszony"
    assert entry.possible_meanings_hu == ("szomszédasszony", "szomszéd nő", "szomszéd")
    assert entry.base_meaning_hu in entry.possible_meanings_hu
    assert lexical_note == (
        "Héber főnév. Női szomszédot vagy szomszédasszonyt jelöl; "
        "többes számban: szomszédasszonyok."
    )


def test_affix_display_surfaces_are_derived_for_prefix_and_suffix_tokens() -> None:
    token_repository = HebrewTokenRepository(DEFAULT_TAHOT_DATABASE_PATH)
    lexicon = HebrewLexiconRepository(DEFAULT_TBESH_DATABASE_PATH, Path("bible_engine/data/hebrew_strong_aliases.json"))

    prefix_token = token_repository.passage("Gen", 1, 1).tokens[0]
    prefix_model = build_hebrew_token_view_model(
        prefix_token,
        token_repository.morphology(prefix_token),
        lexicon.lookup_token(prefix_token),
    )
    assert prefix_model["display_surface"] == "בְּרֵאשִׁית"
    assert prefix_model["components"][0]["display_surface"] == "בְּ"
    assert prefix_model["components"][1]["display_surface"] == "רֵאשִׁית"

    suffix_token = next(
        token
        for token in token_repository.passage("Gen", 1, 11).tokens
        if token.stable_key == "Gen:1:11:13"
    )
    suffix_model = build_hebrew_token_view_model(
        suffix_token,
        token_repository.morphology(suffix_token),
        lexicon.lookup_token(suffix_token),
    )
    assert suffix_model["display_surface"] == "לְמִינוֹ"
    assert suffix_model["components"][0]["display_surface"] == "לְ"
    assert suffix_model["components"][1]["display_surface"] == "מִינ"
    assert suffix_model["components"][2]["display_surface"] == "וֹ"


def test_lexicon_repository_direct_alias_and_missing(tmp_path: Path) -> None:
    database = tmp_path / "tahot_ot.sqlite3"
    alias_path = tmp_path / "hebrew_strong_aliases.json"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    alias_path.write_text(
        json.dumps({"H1961Z": "H1961"}, ensure_ascii=False),
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
        json.dumps({"H1961Z": "H9999Z"}),
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


def test_self_referential_map_alias_is_rejected(tmp_path: Path) -> None:
    alias_path = tmp_path / "hebrew_strong_aliases.json"
    alias_path.write_text(json.dumps({"H1961": "H1961"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Self-referential"):
        HebrewLexiconRepository(tmp_path / "missing.sqlite3", alias_path)
