"""Egyszeri beállítás: privát Supabase Storage bucket a helyi RÚF-DB-hez.

JOGI MEGJEGYZÉS: lásd `ruf_bible_local_db.py` modul-docstringjét — a
teljes RÚF szöveg tárolása (itt: a Supabase-projekt PRIVÁT storage
bucketjében) a Magyar Bibliatársulattal fennálló szerződés alapján
történik. A bucket SOSE legyen publikus — ez a szkript explicit
`public: False` beállítással hozza létre, és feltöltés előtt
ellenőrzi is, hogy nem publikus.

Használat (egyszeri, manuális futtatás):
    python scripts/setup_ruf_bible_storage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supabase_client import get_supabase_client
import ruf_bible_local_db as local_db

BUCKET_ID = "ruf-bible-private"
OBJECT_PATH = "ruf_bible.sqlite3"


def main() -> None:
    db_path = local_db.DEFAULT_DATABASE_PATH
    if not db_path.is_file():
        raise SystemExit(
            f"Nincs helyi DB ezen az útvonalon: {db_path}. "
            "Előbb futtasd: python scripts/build_ruf_bible_db.py"
        )

    client = get_supabase_client()
    storage = client.storage

    existing_buckets = {b.id for b in storage.list_buckets()}
    if BUCKET_ID not in existing_buckets:
        storage.create_bucket(BUCKET_ID, options={"public": False})
        print(f"Bucket létrehozva: {BUCKET_ID} (privát)")
    else:
        bucket_info = storage.get_bucket(BUCKET_ID)
        if getattr(bucket_info, "public", False):
            raise SystemExit(
                f"BIZTONSÁGI LEÁLLÁS: a(z) '{BUCKET_ID}' bucket PUBLIKUS — "
                "ez sérti a szerződéses feltételt. Állítsd privátra a "
                "Supabase dashboardon, mielőtt újra futtatod ezt a szkriptet."
            )
        print(f"Bucket már létezik és privát: {BUCKET_ID}")

    bucket = storage.from_(BUCKET_ID)
    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"Feltöltés: {db_path} ({size_mb:.1f} MB) -> {BUCKET_ID}/{OBJECT_PATH}")
    with db_path.open("rb") as f:
        bucket.upload(
            OBJECT_PATH,
            f,
            file_options={"content-type": "application/octet-stream", "upsert": "true"},
        )
    print("Feltöltés kész.")


if __name__ == "__main__":
    main()
