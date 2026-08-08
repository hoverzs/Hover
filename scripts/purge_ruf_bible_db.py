"""A helyi RÚF 2014 szövegtár azonnali, teljes törlése.

Szerződéses feltétel: ha a Magyar Bibliatársulattal fennálló engedély
megszűnik, ez az egylépéses parancs azonnal és teljesen eltávolítja a
helyi adatbázist (és minden SQLite melléktermék-fájlt) — lásd
`ruf_bible_local_db.py` modul-docstringjét.

Használat:
    python scripts/purge_ruf_bible_db.py            # megerősítést kér
    python scripts/purge_ruf_bible_db.py --yes       # azonnali törlés
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ruf_bible_local_db as local_db


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A helyi RÚF 2014 szövegtár (és melléktermék-fájljainak) teljes törlése."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=local_db.DEFAULT_DATABASE_PATH,
        help="A törlendő SQLite fájl elérési útja",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Megerősítő kérdés nélkül, azonnal töröl",
    )
    args = parser.parse_args()

    path = local_db.resolve_database_path(args.output)
    if not args.yes:
        answer = input(
            f"Biztosan törlöd a teljes helyi RÚF-szövegtárat ({path})? [y/N] "
        ).strip().lower()
        if answer not in {"y", "yes", "igen", "i"}:
            print("Megszakítva — nem történt törlés.")
            return

    removed = local_db.purge_database(path)
    # Az élő API-útvonal munkamenet-cache-ét is kiürítjük, hogy a
    # folyamatban lévő Python-processzben se maradjon RÚF-szöveg.
    try:
        import ruf_bible_service

        ruf_bible_service.clear_ruf_cache()
    except ImportError:
        pass

    if removed:
        print("Törölve:")
        for item in removed:
            print(f"  - {item}")
    else:
        print("Nem volt mit törölni (a DB nem létezett).")


if __name__ == "__main__":
    main()
