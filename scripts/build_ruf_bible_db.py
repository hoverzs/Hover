"""Teljes RÚF 2014 Biblia-szöveg bulk-importálása helyi SQLite adatbázisba.

JOGI MEGJEGYZÉS: lásd `ruf_bible_local_db.py` és `ruf_bible_service.py`
modul-docstringjeit — a teljes szöveg helyi tárolása a Magyar
Bibliatársulattal fennálló érvényes szerződés/engedély alapján történik.

Folytatható: minden fejezet állapota a célDB `fetch_log` táblájában
rögzül ('ok' / 'error'). Újrafuttatáskor a már 'ok' fejezetek azonnal
kimaradnak, ezért a szkript bármikor biztonságosan megszakítható és
újraindítható.

Használat:
    python scripts/build_ruf_bible_db.py
    python scripts/build_ruf_bible_db.py --retry-failed
    python scripts/build_ruf_bible_db.py --book GEN --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ruf_bible_local_db as local_db
from ruf_bible_service import (
    CANONICAL_BOOKS,
    COPYRIGHT_NOTICE,
    SOURCE_ATTRIBUTION,
    TRANSLATION_CODE,
    fetch_ruf_passage,
)


# Kanonikus fejezetszámok a standard 66 könyves protestáns kánon szerint —
# egyetemesen ismert, állandó adat (nem függ semmilyen más adatbázistól,
# és a helyi héber ÓSZ token-DB `chapters_count` mezőjénél megbízhatóbb,
# mert az utóbbiban Genezisnél pl. hiányos adatot találtunk).
CANONICAL_CHAPTER_COUNTS: dict[str, int] = {
    "GEN": 50, "EXO": 40, "LEV": 27, "NUM": 36, "DEU": 34,
    "JOS": 24, "JDG": 21, "RUT": 4, "1SA": 31, "2SA": 24,
    "1KI": 22, "2KI": 25, "1CH": 29, "2CH": 36, "EZR": 10,
    "NEH": 13, "EST": 10, "JOB": 42, "PSA": 150, "PRO": 31,
    "ECC": 12, "SNG": 8, "ISA": 66, "JER": 52, "LAM": 5,
    "EZK": 48, "DAN": 12, "HOS": 14, "JOL": 3, "AMO": 9,
    "OBA": 1, "JON": 4, "MIC": 7, "NAM": 3, "HAB": 3,
    "ZEP": 3, "HAG": 2, "ZEC": 14,
    # MAL: a RÚF (héber versifikáció szerint) 3 fejezetes — amit néhány
    # angol kiadás külön 4. fejezetként számoz (Mal 3,19-24 versei), az a
    # RÚF-ban a 3. fejezet végéhez tartozik. Élesben ellenőrizve: a
    # Szentírás.eu API "Mal 4"-re üres találatot ad, "Mal 3" viszont
    # helyesen 24 verset (a "4. fejezetnyi" tartalmat is beleértve).
    "MAL": 3,
    "MAT": 28, "MRK": 16, "LUK": 24, "JHN": 21, "ACT": 28,
    "ROM": 16, "1CO": 16, "2CO": 13, "GAL": 6, "EPH": 6,
    "PHP": 4, "COL": 4, "1TH": 5, "2TH": 3, "1TI": 6,
    "2TI": 4, "TIT": 3, "PHM": 1, "HEB": 13, "JAS": 5,
    "1PE": 5, "2PE": 3, "1JN": 5, "2JN": 1, "3JN": 1,
    "JUD": 1, "REV": 22,
}


def build_work_queue(only_book: str | None = None) -> list[tuple[int, str, str, int]]:
    """(ordinal, book_code, book_abbr, chapter) négyesek listája kanonikus sorrendben."""
    queue: list[tuple[int, str, str, int]] = []
    for ordinal, info in enumerate(CANONICAL_BOOKS, start=1):
        if only_book and info.code.upper() != only_book.upper():
            continue
        chapters = CANONICAL_CHAPTER_COUNTS.get(info.code)
        if chapters is None:
            raise KeyError(f"Nincs kanonikus fejezetszám ehhez a könyvhöz: {info.code}")
        for chapter in range(1, chapters + 1):
            queue.append((ordinal, info.code, info.abbr, chapter))
    return queue


def run(
    *,
    output: Path,
    delay_s: float,
    retry_failed: bool,
    only_book: str | None,
    dry_run: bool,
) -> None:
    queue = build_work_queue(only_book)
    print(f"Munkasor: {len(queue)} fejezet" + (f" ({only_book})" if only_book else " (teljes Biblia)"))
    if dry_run:
        for ordinal, book_code, book_abbr, chapter in queue[:10]:
            print(f"  {ordinal:>2} {book_code} {book_abbr} {chapter}")
        if len(queue) > 10:
            print(f"  ... és még {len(queue) - 10} tétel")
        return

    conn = local_db.get_connection(output)
    local_db.set_meta(conn, "translation_code", TRANSLATION_CODE)
    local_db.set_meta(conn, "copyright_notice", COPYRIGHT_NOTICE)
    local_db.set_meta(conn, "source_attribution", SOURCE_ATTRIBUTION)
    conn.commit()

    fetched = 0
    skipped = 0
    failed: list[tuple[str, int, str]] = []
    total_verses = 0
    started_at = time.time()

    try:
        for i, (ordinal, book_code, book_abbr, chapter) in enumerate(queue, start=1):
            status = local_db.get_chapter_status(conn, book_code, chapter)
            if retry_failed:
                # Csak a korábban hibázott fejezeteket próbálja újra — a
                # sosem érintett és a már kész fejezeteket kihagyja.
                if status != "error":
                    skipped += 1
                    continue
            else:
                if status == "ok":
                    skipped += 1
                    continue

            reference = f"{book_abbr} {chapter}"
            result = fetch_ruf_passage(reference, use_cache=False)
            if not result.get("success"):
                error_message = result.get("error") or "Ismeretlen hiba."
                local_db.record_fetch_error(conn, book_code, chapter, error_message)
                failed.append((book_code, chapter, error_message))
                print(f"[{i}/{len(queue)}] HIBA {reference}: {error_message}")
            else:
                n = local_db.upsert_chapter_verses(
                    conn,
                    book_code=book_code,
                    book_abbr=book_abbr,
                    ordinal=ordinal,
                    chapter=chapter,
                    verses=result.get("verses") or [],
                )
                total_verses += n
                fetched += 1
                if fetched % 20 == 0:
                    print(f"[{i}/{len(queue)}] {reference} — OK ({n} vers) — commit")

            if i % 20 == 0:
                conn.commit()
            time.sleep(delay_s)
    finally:
        conn.commit()
        conn.close()

    elapsed = time.time() - started_at
    print()
    print("Összegzés:")
    print(f"  Lekért fejezet: {fetched}")
    print(f"  Kihagyott (már kész): {skipped}")
    print(f"  Beírt vers összesen: {total_verses}")
    print(f"  Hibás fejezet: {len(failed)}")
    for book_code, chapter, msg in failed[:20]:
        print(f"    - {book_code} {chapter}: {msg}")
    if len(failed) > 20:
        print(f"    ... és még {len(failed) - 20} hiba")
    print(f"  Eltelt idő: {elapsed:.1f} mp")
    if failed:
        print("\nÚjrafuttatás a hibás fejezetekre: python scripts/build_ruf_bible_db.py --retry-failed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Teljes RÚF 2014 szöveg bulk-importja helyi SQLite DB-be (folytatható)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=local_db.DEFAULT_DATABASE_PATH,
        help="Cél SQLite fájl elérési útja",
    )
    parser.add_argument(
        "--delay-s",
        type=float,
        default=0.4,
        help="Késleltetés (mp) két fejezet-lekérés között (udvarias rate-limit)",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Csak a korábban 'error' státuszú fejezetek újralekérése",
    )
    parser.add_argument(
        "--book",
        type=str,
        default=None,
        help="Egy könyvre szűkítés (pl. GEN) — teszteléshez",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak a munkasor kiírása, API-hívás nélkül",
    )
    args = parser.parse_args()
    run(
        output=args.output,
        delay_s=args.delay_s,
        retry_failed=args.retry_failed,
        only_book=args.book,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
