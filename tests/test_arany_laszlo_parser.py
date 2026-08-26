from __future__ import annotations

from pathlib import Path

import pytest

from illustration_engine.arany_laszlo_parser import (
    TALE_TITLES,
    AranyLaszloParseError,
    parse_arany_laszlo_file,
    parse_arany_laszlo_text,
)
from illustration_engine.paths import RAW_DATA_DIR


ARANY_SOURCE = RAW_DATA_DIR / "pg38852_arany_laszlo_eredeti_nepmesek.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Arany László source not present locally: {path}")
    return path


def test_tale_count_matches_table_of_contents() -> None:
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    assert len(tales) == 31
    assert len(TALE_TITLES) == 31


def test_first_and_last_tale() -> None:
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    assert tales[0].external_ref == "1"
    assert tales[0].title_original == "A vak király"
    assert tales[-1].external_ref == "31"
    assert tales[-1].title_original == (
        "Mért haragszik a disznó a kutyára, a kutya a macskára, a macska az egérre"
    )


def test_tale_text_segmentation_does_not_bleed_across_boundary() -> None:
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    first_text = tales[0].original_text
    assert "Hol volt, hol nem volt" in first_text
    assert "A BOLTOS HÁROM LYÁNYA" not in first_text.upper()

    second_text = tales[1].original_text
    assert "A VAK KIRÁLY" not in second_text.upper()


def test_long_tale_boundaries_are_correct_across_a_much_larger_source() -> None:
    """Ráadó és Anyicska is one of the longest tales in this collection —
    make sure a much bigger single-story span (thousands of characters)
    still resolves to exactly the right start/end, not just short tales."""
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    raado = next(t for t in tales if t.title_original == "Ráadó és Anyicska")
    assert len(raado.original_text) > 5000
    assert "AZ ARANYHAJÚ HERCZEGKISASSZONY" not in raado.original_text.upper()


def test_irregular_case_and_missing_accent_headings_are_matched_correctly() -> None:
    """This edition has two confirmed typographic irregularities in its
    ALL-CAPS body headings: one keeps sentence case, one drops the accent
    on a capital É. Both must still resolve to the right tale."""
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    titles = {t.title_original for t in tales}
    assert "Az aranyhajú herczegkisasszony" in titles
    assert "A tündérkisasszony és a czigánylyány" in titles

    aranyhaju = next(t for t in tales if t.title_original == "Az aranyhajú herczegkisasszony")
    assert "Egyszer volt, hol nem volt" in aranyhaju.original_text


def test_wrapped_last_title_is_matched_across_two_physical_lines() -> None:
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    last = tales[-1]
    assert "A disznó egyszer kapott" in last.original_text
    assert last.original_text.strip().endswith("a macska az egérre.")


def test_tale_text_excludes_gutenberg_boilerplate() -> None:
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    joined = "\n".join(tale.original_text for tale in tales)
    forbidden = (
        "PROJECT GUTENBERG",
        "This eBook is for the use of anyone",
        "Google Books Library Project",
    )
    for marker in forbidden:
        assert marker.upper() not in joined.upper(), f"leaked boilerplate marker: {marker!r}"


def test_tale_text_excludes_front_matter() -> None:
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    joined = "\n".join(tale.original_text for tale in tales)
    assert "TARTALOM" not in joined.upper()
    assert "KIADJA HECKENAST" not in joined.upper()


def test_tale_text_excludes_riddles_trick_tales_and_answer_key() -> None:
    """Structural exclusion, not taste-based: Találós mesék (riddles) and
    Csali-mesék (trick tales) have no title + narrative-paragraph shape
    (just numbered 2-5 line verses), and Megfejtések is a pure answer
    key — none of them match this engine's story model."""
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    joined = "\n".join(tale.original_text for tale in tales)
    assert "TALÁLOS MESÉK" not in joined.upper()
    assert "CSALI-MESÉK" not in joined.upper()
    assert "MEGFEJTÉSEK" not in joined.upper()
    assert len(tales) == 31  # not 31 + 54 riddles + 5 trick tales


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    tales = parse_arany_laszlo_file(_require(ARANY_SOURCE))
    keys = [tale.canonical_key for tale in tales]
    assert keys == [f"{i:02d}" for i in range(1, 32)]
    assert [tale.external_ref for tale in tales] == [str(i) for i in range(1, 32)]


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(ARANY_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_arany_laszlo_text(raw_text)
    second_pass = parse_arany_laszlo_text(raw_text)
    assert first_pass == second_pass


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(AranyLaszloParseError):
        parse_arany_laszlo_text("no PG markers in this text at all")


def test_parse_raises_on_missing_expected_tale_title() -> None:
    raw_text = _require(ARANY_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("ICZINKE-PICZINKE.", "SOMETHING ELSE ENTIRELY.", 1)
    with pytest.raises(AranyLaszloParseError):
        parse_arany_laszlo_text(mutilated)
