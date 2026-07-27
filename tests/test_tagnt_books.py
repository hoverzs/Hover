from __future__ import annotations

import pytest

from bible_engine.tagnt_books import (
    RUF_TO_TAGNT_BOOK_CODES,
    tagnt_book_code_from_reference,
    tagnt_book_code_from_ruf_code,
)


@pytest.mark.parametrize(
    ("ruf_code", "tagnt_code"),
    [
        ("MAT", "Mat"),
        ("MRK", "Mrk"),
        ("LUK", "Luk"),
        ("JHN", "Jhn"),
        ("ACT", "Act"),
        ("ROM", "Rom"),
        ("1CO", "1Co"),
        ("2CO", "2Co"),
        ("GAL", "Gal"),
        ("EPH", "Eph"),
        ("PHP", "Php"),
        ("COL", "Col"),
        ("1TH", "1Th"),
        ("2TH", "2Th"),
        ("1TI", "1Ti"),
        ("2TI", "2Ti"),
        ("TIT", "Tit"),
        ("PHM", "Phm"),
        ("HEB", "Heb"),
        ("JAS", "Jas"),
        ("1PE", "1Pe"),
        ("2PE", "2Pe"),
        ("1JN", "1Jn"),
        ("2JN", "2Jn"),
        ("3JN", "3Jn"),
        ("JUD", "Jud"),
        ("REV", "Rev"),
    ],
)
def test_ruf_code_to_tagnt_code_mapping(ruf_code: str, tagnt_code: str) -> None:
    assert tagnt_book_code_from_ruf_code(ruf_code) == tagnt_code
    assert RUF_TO_TAGNT_BOOK_CODES[ruf_code] == tagnt_code


@pytest.mark.parametrize(
    ("reference", "tagnt_code"),
    [
        ("Mt 5,1", "Mat"),
        ("Máté 5,1", "Mat"),
        ("Mk 1,1", "Mrk"),
        ("Márk 1,1", "Mrk"),
        ("Lk 15,11", "Luk"),
        ("Lukács 15,11", "Luk"),
        ("Jn 3,16", "Jhn"),
        ("János 3,16", "Jhn"),
        ("ApCsel 2,1", "Act"),
        ("Apostolok 2,1", "Act"),
        ("Róm 8,1", "Rom"),
        ("Róma 8,1", "Rom"),
        ("1Kor 13,1", "1Co"),
        ("2Kor 1,1", "2Co"),
        ("Gal 5,22", "Gal"),
        ("Ef 2,8", "Eph"),
        ("Fil 2,5", "Php"),
        ("Kol 1,1", "Col"),
        ("1Thess 1,1", "1Th"),
        ("2Thessz 1,1", "2Th"),
        ("1Tim 1,1", "1Ti"),
        ("2Timóteus 1,1", "2Ti"),
        ("Tit 1,1", "Tit"),
        ("Filem 1", "Phm"),
        ("Zsid 11,1", "Heb"),
        ("Jak 1,2", "Jas"),
        ("1Pt 1,3", "1Pe"),
        ("2Péter 1,1", "2Pe"),
        ("1Jn 4,7", "1Jn"),
        ("2Jn 1", "2Jn"),
        ("3Jn 1", "3Jn"),
        ("Júd 20", "Jud"),
        ("Júd 1,20", "Jud"),
        ("Jelenések 22,20", "Rev"),
        ("Jel 22,20", "Rev"),
    ],
)
def test_reference_aliases_map_to_tagnt_codes(reference: str, tagnt_code: str) -> None:
    assert tagnt_book_code_from_reference(reference) == tagnt_code
