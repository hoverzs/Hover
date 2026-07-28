from __future__ import annotations

from bible_engine.hebrew_morphology import decode_hebrew_morphology


def test_decodes_qal_perfect_and_wayyiqtol() -> None:
    perfect = decode_hebrew_morphology("HVqp3ms", {"HVqp3ms": "Function=Verb ; Stem=Qal"})
    wayyiqtol = decode_hebrew_morphology("HVqw3ms", {"HVqw3ms": "Function=Verb ; Stem=Qal"})

    assert perfect.language == "Hebrew"
    assert perfect.part_of_speech == "Verb"
    assert perfect.verb_stem == "Qal"
    assert perfect.verb_conjugation == "Perfect"
    assert perfect.person == "Third"
    assert perfect.gender == "Masculine"
    assert perfect.number == "Singular"
    assert perfect.status == "fully_decoded"
    assert wayyiqtol.verb_conjugation == "Consecutive Imperfect"


def test_decodes_common_stems_and_nonverbs() -> None:
    assert decode_hebrew_morphology("HVNp3ms").verb_stem == "Niphal"
    assert decode_hebrew_morphology("HVpp3ms").verb_stem == "Piel"
    assert decode_hebrew_morphology("HVPp3ms").verb_stem == "Pual"
    assert decode_hebrew_morphology("HVhp3ms").verb_stem == "Hiphil"
    assert decode_hebrew_morphology("HVHp3ms").verb_stem == "Hophal"
    assert decode_hebrew_morphology("HVtp3ms").verb_stem == "Hithpael"
    noun = decode_hebrew_morphology("HNcmsc")
    assert noun.part_of_speech == "Noun"
    assert noun.noun_type == "Common"
    assert noun.state == "Construct"
    assert noun.status == "fully_decoded"


def test_decodes_suffix_and_aramaic_without_inventing_unknowns() -> None:
    suffix = decode_hebrew_morphology("Sp3ms")
    aramaic = decode_hebrew_morphology("AVqp3ms")
    unknown = decode_hebrew_morphology("HZzzz")

    assert suffix.part_of_speech == "Suffix"
    assert suffix.suffix_person == "Third"
    assert suffix.suffix_gender == "Masculine"
    assert suffix.suffix_number == "Singular"
    assert aramaic.language == "Aramaic"
    assert aramaic.status == "fully_decoded"
    assert unknown.unresolved_parts
    assert unknown.status in {"partially_decoded", "unresolved"}


def test_decodes_slash_components_with_inherited_language() -> None:
    decoded = decode_hebrew_morphology(
        "Hc/Vqw3ms",
        {
            "Hc": "Function=Conjunction; Form=Consecutive",
            "HVqw3ms": "Function=Verb ; Stem=Qal ; Form=Consecutive Imperfect",
        },
    )

    assert decoded.language == "Hebrew"
    assert decoded.part_of_speech == "Conjunction + Verb"
    assert decoded.status == "fully_decoded"
    assert not decoded.unresolved_parts


def test_common_previously_unresolved_patterns_are_consumed() -> None:
    expansions = {
        "HR": "Function=Preposition",
        "HTd": "Function=Particle ; Form=Definite article (Hebrew)",
        "HNcmsa": "Function=Noun ; Form=Common ; Gender=Masculine; Number=Singular; State=Absolute",
        "HNcmsc": "Function=Noun ; Form=Common ; Gender=Masculine; Number=Singular; State=Construct",
        "HVqcc": "Function=Verb ; Stem=Qal ; Form=Infinitive ; State=Construct",
        "HTo": "Function=Particle ; Form=Object marker",
        "HSp3ms": "Function=Suffix ; Person=Third; Gender=Masculine; Number=Singular",
    }

    for code in ["HR/Ncmsc", "HTd/Ncmsa", "HR/Vqcc", "HC/To", "HR/Sp3ms"]:
        decoded = decode_hebrew_morphology(code, expansions)
        assert decoded.status == "fully_decoded"
        assert not decoded.unresolved_parts


def test_empty_morphology_is_malformed() -> None:
    decoded = decode_hebrew_morphology("")

    assert decoded.status == "malformed"
