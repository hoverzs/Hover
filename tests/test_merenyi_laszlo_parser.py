from __future__ import annotations

from pathlib import Path

import pytest

from illustration_engine.merenyi_laszlo_parser import (
    MERENYI_1_RESZ,
    MERENYI_2_RESZ,
    MerenyiLaszloParseError,
    parse_merenyi_laszlo_file,
    parse_merenyi_laszlo_text,
)
from illustration_engine.paths import RAW_DATA_DIR


MERENYI_1_SOURCE = RAW_DATA_DIR / "pg39419_merenyi_laszlo_eredeti_nepmesek_1resz.txt"
MERENYI_2_SOURCE = RAW_DATA_DIR / "pg39386_merenyi_laszlo_eredeti_nepmesek_2resz.txt"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Raw Merényi László source not present locally: {path}")
    return path


def test_tale_count_per_volume_and_total() -> None:
    part1 = parse_merenyi_laszlo_file(_require(MERENYI_1_SOURCE), MERENYI_1_RESZ)
    part2 = parse_merenyi_laszlo_file(_require(MERENYI_2_SOURCE), MERENYI_2_RESZ)
    assert len(part1) == 10
    assert len(part2) == 13
    assert len(part1) + len(part2) == 23


def test_first_and_last_tale_part1() -> None:
    tales = parse_merenyi_laszlo_file(_require(MERENYI_1_SOURCE), MERENYI_1_RESZ)
    assert tales[0].title_original == "A kigyóbőr"
    assert tales[-1].title_original == "Bolond Jankó"


def test_first_and_last_tale_part2() -> None:
    tales = parse_merenyi_laszlo_file(_require(MERENYI_2_SOURCE), MERENYI_2_RESZ)
    assert tales[0].title_original == "A hamupipőke"
    assert tales[-1].title_original == "Bolond Jankó"


def test_both_volumes_end_with_a_distinct_bolond_janko_tale() -> None:
    """Both volumes' last tale happens to share the same title — they
    must remain two distinct stories (different source, different text),
    not accidentally collapse into one."""
    part1 = parse_merenyi_laszlo_file(_require(MERENYI_1_SOURCE), MERENYI_1_RESZ)
    part2 = parse_merenyi_laszlo_file(_require(MERENYI_2_SOURCE), MERENYI_2_RESZ)
    assert part1[-1].title_original == part2[-1].title_original == "Bolond Jankó"
    assert part1[-1].original_text != part2[-1].original_text


def test_footnote_suffixed_heading_is_matched_correctly() -> None:
    """This volume's 7th tale heading is fused to a footnote-reference
    bracket in the source ("...KOMÁJA.[101]") — a naive period-only
    header scan misses it; the heading pattern must tolerate the
    trailing "[NNN]" and still resolve the correct tale boundaries."""
    tales = parse_merenyi_laszlo_file(_require(MERENYI_1_SOURCE), MERENYI_1_RESZ)
    titles = [t.title_original for t in tales]
    assert "A szegény ember és a komája" in titles
    tale = next(t for t in tales if t.title_original == "A szegény ember és a komája")
    assert "Jelen népmondához hasonló" in tale.original_text


def test_tale_text_segmentation_does_not_bleed_across_boundary() -> None:
    tales = parse_merenyi_laszlo_file(_require(MERENYI_2_SOURCE), MERENYI_2_RESZ)
    first_text = tales[0].original_text
    assert "Volt egyszer egy király" in first_text
    assert "A NÁDSZÁL KISASSZONY" not in first_text.upper()

    second_text = tales[1].original_text
    assert "A HAMUPIPŐKE" not in second_text.upper()


def test_printer_colophon_excluded_from_last_tale_of_part2() -> None:
    tales = parse_merenyi_laszlo_file(_require(MERENYI_2_SOURCE), MERENYI_2_RESZ)
    joined = "\n".join(t.original_text for t in tales)
    assert "wigand" not in joined.lower()
    assert "könyvnyomdája" not in joined.lower()


def test_tale_text_excludes_gutenberg_boilerplate_and_front_matter() -> None:
    for spec, source in (
        (MERENYI_1_RESZ, MERENYI_1_SOURCE),
        (MERENYI_2_RESZ, MERENYI_2_SOURCE),
    ):
        tales = parse_merenyi_laszlo_file(_require(source), spec)
        joined = "\n".join(t.original_text for t in tales)
        for marker in ("PROJECT GUTENBERG", "This eBook is for the use of anyone", "KIADJA HECKENAST"):
            assert marker.upper() not in joined.upper(), f"{spec.source_code}: leaked {marker!r}"


def test_tale_text_excludes_back_matter() -> None:
    """Part 1 has a riddle section (Néptalányok/Felóldás) plus a back
    TARTALOM; part 2 has no riddle section, just a back TARTALOM plus a
    transcriber's note — both must be fully excluded, and part 1 must
    not gain 93 extra 'tales' from the riddles."""
    part1 = parse_merenyi_laszlo_file(_require(MERENYI_1_SOURCE), MERENYI_1_RESZ)
    part2 = parse_merenyi_laszlo_file(_require(MERENYI_2_SOURCE), MERENYI_2_RESZ)
    assert len(part1) == 10
    assert len(part2) == 13

    joined1 = "\n".join(t.original_text for t in part1)
    joined2 = "\n".join(t.original_text for t in part2)
    assert "NÉPTALÁNYOK" not in joined1.upper()
    assert "FELÓLDÁS" not in joined1.upper()
    assert "TARTALOM" not in joined1.upper()
    assert "TARTALOM" not in joined2.upper()
    assert "TRANSCRIBER" not in joined2.upper()


def test_canonical_keys_are_stable_zero_padded_and_sequential() -> None:
    tales = parse_merenyi_laszlo_file(_require(MERENYI_2_SOURCE), MERENYI_2_RESZ)
    keys = [t.canonical_key for t in tales]
    assert keys == [f"{i:02d}" for i in range(1, 14)]
    assert [t.external_ref for t in tales] == [str(i) for i in range(1, 14)]


def test_parsing_is_deterministic_across_repeated_calls() -> None:
    raw_text = _require(MERENYI_1_SOURCE).read_text(encoding="utf-8")
    first_pass = parse_merenyi_laszlo_text(raw_text, MERENYI_1_RESZ)
    second_pass = parse_merenyi_laszlo_text(raw_text, MERENYI_1_RESZ)
    assert first_pass == second_pass


def test_parse_raises_on_missing_pg_markers() -> None:
    with pytest.raises(MerenyiLaszloParseError):
        parse_merenyi_laszlo_text("no PG markers in this text at all", MERENYI_1_RESZ)


def test_parse_raises_on_missing_expected_tale_title() -> None:
    raw_text = _require(MERENYI_2_SOURCE).read_text(encoding="utf-8")
    mutilated = raw_text.replace("BOLOND JANKÓ.", "SOMETHING ELSE ENTIRELY.", 1)
    with pytest.raises(MerenyiLaszloParseError):
        parse_merenyi_laszlo_text(mutilated, MERENYI_2_RESZ)
