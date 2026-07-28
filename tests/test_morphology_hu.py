from pathlib import Path

from bible_engine.morphology_hu import (
    HungarianMorphology,
    format_morphology_hu,
    parse_morphology_hu,
)
from bible_engine.tagnt_parser import get_verse_tokens


JHN_FIXTURE = Path(__file__).parent / "fixtures" / "tagnt_jhn_3_16_sample.tsv"


def rendered(code: str) -> str:
    return format_morphology_hu(parse_morphology_hu(code))


def test_present_indicative_active_third_singular() -> None:
    assert rendered("V-PAI-3S") == (
        "ige, jelen idő, kijelentő mód, aktív igenem, egyes szám harmadik személy"
    )


def test_aorist_indicative_active_and_second_aorist() -> None:
    assert rendered("V-AAI-3S") == (
        "ige, aorisztoszi, kijelentő mód, aktív igenem, egyes szám harmadik személy"
    )
    assert rendered("V-2AAI-3S") == (
        "ige, második aorisztoszi, kijelentő mód, aktív igenem, egyes szám harmadik személy"
    )


def test_perfect_middle_passive_and_passive_verb_forms() -> None:
    assert rendered("V-RAI-3S") == (
        "ige, perfectum, kijelentő mód, aktív igenem, egyes szám harmadik személy"
    )
    assert "mediális vagy passzív igenem" in rendered("V-PEI-3S")
    assert "passzív igenem" in rendered("V-API-3S")


def test_middle_imperative_and_subjunctive_forms() -> None:
    assert rendered("V-AMI-3S") == (
        "ige, aorisztoszi, kijelentő mód, mediális igenem, egyes szám harmadik személy"
    )
    assert "felszólító mód" in rendered("V-PAM-2S")
    assert "kötőmód" in rendered("V-PAS-3S")


def test_infinitive_and_participle_are_named_as_verb_forms() -> None:
    assert rendered("V-AAN") == "főnévi igenév, aorisztoszi, aktív igenem"
    assert rendered("V-PAP-NSM") == (
        "igei melléknévi igenév, jelen idejű, aktív igenem, hímnem, "
        "egyes szám, alanyeset"
    )


def test_nominal_categories() -> None:
    assert rendered("N-NSM") == "főnév, hímnem, egyes szám, alanyeset"
    assert rendered("N-ASF") == "főnév, nőnem, egyes szám, tárgyeset"
    assert rendered("N-NSN") == "főnév, semlegesnem, egyes szám, alanyeset"
    assert rendered("N-NSM-P") == "tulajdonnév, hímnem, egyes szám, alanyeset"
    assert rendered("A-NSM-C") == "melléknév, hímnem, egyes szám, alanyeset, középfok"
    assert rendered("T-NSF") == "határozott névelő, nőnem, egyes szám, alanyeset"


def test_pronouns_prepositions_conjunctions_adverbs_and_indeclinable() -> None:
    assert rendered("P-2GS") == "személyes névmás, egyes szám második személy, birtokos eset"
    assert rendered("R-NSM") == "vonatkozó névmás, hímnem, egyes szám, alanyeset"
    assert rendered("PREP") == "elöljárószó"
    assert rendered("CONJ") == "kötőszó"
    assert rendered("ADV") == "határozószó"
    assert rendered("A-NUI") == "melléknév, ragozhatatlan számnév"


def test_special_pronouns_and_particles() -> None:
    assert rendered("D-NSM").startswith("mutató névmás")
    assert rendered("I-NSM").startswith("kérdő névmás")
    assert rendered("X-ASN").startswith("határozatlan névmás")
    assert rendered("F-3ASM").startswith("visszaható névmás")
    assert rendered("S-1SGSN").startswith("birtokos névmás")
    assert rendered("PRT-N") == "partikula, tagadó jelölés"
    assert rendered("INJ-HEB") == "indulatszó, héberből átírt alak"


def test_documented_rare_production_codes_are_fully_resolved() -> None:
    assert rendered("N-NSN-LI") == (
        "főnév, semlegesnem, egyes szám, alanyeset, ragozhatatlan betűnév"
    )
    assert rendered("V-2PAN") == "főnévi igenév, jelen idő, aktív igenem"
    assert "arámi eredetű alak" in rendered("V-AAI-2S-ARAM")
    assert "attikai görög alak" in rendered("V-AOI-2P-ATT")


def test_compound_morphology_decodes_each_documented_component() -> None:
    text = rendered("CONJ + G1565=D-NSM")

    assert text == "kötőszó + mutató névmás, hímnem, egyes szám, alanyeset"
    assert "G1565" not in text
    assert "egyéb" not in text


def test_unknown_and_empty_codes_are_controlled() -> None:
    unknown = parse_morphology_hu("ZZ-QQ-9")

    assert unknown == HungarianMorphology(
        raw_code="ZZ-QQ-9",
        part_of_speech=None,
        tense=None,
        voice=None,
        mood=None,
        verb_form=None,
        person=None,
        number=None,
        case=None,
        gender=None,
        degree=None,
        extra=(),
        unresolved=("ZZ", "QQ", "9"),
    )
    assert rendered("ZZ-QQ-9") == (
        "nem feloldott morfológiai jelölés: ZZ, "
        "nem feloldott morfológiai jelölés: QQ, "
        "nem feloldott morfológiai jelölés: 9"
    )
    assert rendered("") == ""


def test_no_technical_remainder_for_documented_examples() -> None:
    for code in ("V-PNI-3S", "N-NSM-P", "V-AMI-3S"):
        text = rendered(code)
        assert "egyéb" not in text
        assert "nem feloldott" not in text
        assert "PNI" not in text
        assert "NSM" not in text
        assert "3S" not in text


def test_production_regression_examples_use_actual_codes() -> None:
    assert rendered("V-PNI-3S") == (
        "ige, jelen idő, kijelentő mód, mediális vagy passzív deponens, "
        "egyes szám harmadik személy"
    )
    assert rendered("N-NSM-P") == "tulajdonnév, hímnem, egyes szám, alanyeset"
    assert rendered("V-AMI-3S") == (
        "ige, aorisztoszi, kijelentő mód, mediális igenem, egyes szám harmadik személy"
    )


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
        morphology.part_of_speech or morphology.components or morphology.unresolved
        for morphology in morphologies
    )
