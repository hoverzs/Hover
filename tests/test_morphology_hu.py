from pathlib import Path

from bible_engine.morphology_hu import (
    HungarianMorphology,
    format_morphology_hu,
    parse_morphology_hu,
)
from bible_engine.tagnt_parser import get_verse_tokens


JHN_FIXTURE = Path(__file__).parent / "fixtures" / "tagnt_jhn_3_16_sample.tsv"


def test_verb_aorist_active_indicative_third_singular() -> None:
    morphology = parse_morphology_hu("V-AAI-3S")

    assert morphology == HungarianMorphology(
        raw_code="V-AAI-3S",
        part_of_speech="ige",
        tense="aorisztosz",
        voice="aktív",
        mood="kijelentő",
        verb_form=None,
        person="harmadik",
        number="egyes",
        case=None,
        gender=None,
        degree=None,
        extra=(),
    )


def test_pronoun_from_john_fixture() -> None:
    morphology = parse_morphology_hu("P-GSM")

    assert morphology.part_of_speech == "személyes névmás"
    assert morphology.case == "birtokos eset"
    assert morphology.number == "egyes"
    assert morphology.gender == "hímnem"


def test_participle_from_john_fixture() -> None:
    morphology = parse_morphology_hu("V-PAP-NSM")

    assert morphology.part_of_speech == "ige"
    assert morphology.tense == "jelen idő"
    assert morphology.voice == "aktív igenem"
    assert morphology.verb_form == "participium"
    assert morphology.case == "alanyeset"
    assert morphology.number == "egyes"
    assert morphology.gender == "hímnem"
    assert morphology.extra == ()


def test_infinitive_uses_verb_form_when_documented() -> None:
    morphology = parse_morphology_hu("V-AAN")

    assert morphology.part_of_speech == "ige"
    assert morphology.tense == "aorisztosz"
    assert morphology.voice == "aktív"
    assert morphology.verb_form == "infinitivus"
    assert morphology.mood is None
    assert morphology.extra == ()


def test_incomplete_code_keeps_unknown_remainder() -> None:
    morphology = parse_morphology_hu("V-AAI")

    assert morphology.raw_code == "V-AAI"
    assert morphology.part_of_speech == "ige"
    assert morphology.extra == ("AAI",)


def test_unknown_code_keeps_all_unknown_parts() -> None:
    morphology = parse_morphology_hu("ZZ-QQ-9")

    assert morphology.raw_code == "ZZ-QQ-9"
    assert morphology.part_of_speech is None
    assert morphology.extra == ("ZZ", "QQ", "9")


def test_empty_code_is_safe() -> None:
    morphology = parse_morphology_hu("")

    assert morphology.raw_code == ""
    assert morphology.part_of_speech is None
    assert morphology.extra == ()
    assert format_morphology_hu(morphology) == ""


def test_formatter_uses_natural_hungarian_terms() -> None:
    morphology = parse_morphology_hu("V-AAI-3S")

    assert (
        format_morphology_hu(morphology)
        == "ige, aorisztosz, aktív, kijelentő, harmadik személy, egyes szám"
    )


def test_formatter_places_participle_as_verb_form_not_extra() -> None:
    morphology = parse_morphology_hu("V-PAP-NSM")

    assert (
        format_morphology_hu(morphology)
        == "ige, jelen idő, aktív igenem, participium, egyes szám, alanyeset, hímnem"
    )
    assert "egyéb" not in format_morphology_hu(morphology)


def test_unknown_subcode_is_not_lost() -> None:
    morphology = parse_morphology_hu("N-NSM-X")

    assert morphology.part_of_speech == "főnév"
    assert morphology.extra == ("NSM", "X")
    assert "X" in format_morphology_hu(morphology)


def test_john_3_16_morph_codes_parse_without_crashing() -> None:
    tokens = get_verse_tokens(JHN_FIXTURE, book="Jhn", chapter=3, verse=16)
    morphologies = [
        parse_morphology_hu(token.morph_code)
        for token in tokens
        if token.morph_code
    ]

    assert len(morphologies) == 26
    assert [morphology.raw_code for morphology in morphologies] == [
        token.morph_code for token in tokens
    ]
    assert all(
        morphology.part_of_speech or morphology.extra
        for morphology in morphologies
    )
