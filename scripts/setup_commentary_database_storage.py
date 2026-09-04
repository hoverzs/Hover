"""Egyszeri beallitas: privat Supabase Storage bucket a Commentary DB-hez.

Ugyanaz a minta, mint `scripts/setup_ruf_bible_storage.py` es a hymn/
theology modulok sajat (nem repoban levo) feltoltesei: egy PRIVAT bucket
(`public: False`), es a helyi, mar felepitett `commentary.sqlite3`
feltoltese oda. Innen toltodik le futasidoben a
`textus_kb.commentary_runtime.ensure_commentary_database` fuggvennyel --
production sose epiti ujra a teljes Calvin/JFB/Henry corpust.

A szkript a feltoltes elott validalja a helyi DB-t (sema + tartalmi
szamlalok + content_hash) a `textus_kb.commentary_runtime` modulban
rogzitett `EXPECTED_*` ertekek ellen, es figyelmeztet (de nem all le), ha
eltetes -- igy ha idokozben ujra epul/frissul a corpus, ez a szkript
akkor is jelzi, ha a pinnelt konstansokat is frissiteni kell a
feltoltes elott.

Hasznalat (egyszeri, manualis futtatas -- NEM fut le automatikusan):
    python scripts/setup_commentary_database_storage.py

Ehhez a beallitott Supabase secrets/env valtozok szuksegesek (ld.
`supabase_client.get_supabase_client`), es utana a futtato kornyezetben
(pl. Streamlit secrets) be kell allitani:
    TEXTUS_COMMENTARY_DB_STORAGE_BUCKET = "commentary-db-private"
    TEXTUS_COMMENTARY_DB_STORAGE_OBJECT = "commentary.sqlite3"
    TEXTUS_COMMENTARY_DB_SHA256 = "<a szkript altal kiirt SHA256>"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supabase_client import get_supabase_client
from textus_kb import commentary_runtime as runtime
from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    validate_commentary_database,
)

BUCKET_ID = "commentary-db-private"
OBJECT_PATH = "commentary.sqlite3"


def main() -> None:
    db_path = DEFAULT_DATABASE_PATH
    if not db_path.is_file():
        raise SystemExit(
            f"Nincs helyi DB ezen az utvonalon: {db_path}. "
            "Eloszor futtasd: python scripts/build_commentary_database.py "
            "--combined-fetch --qa"
        )

    validation = validate_commentary_database(db_path)
    mismatches = runtime._invariant_mismatches(validation)  # noqa: SLF001
    raw_sha256 = runtime._sha256_file(db_path)  # noqa: SLF001

    print(f"Helyi DB: {db_path}")
    print(f"  schema_version   = {validation.schema_version}")
    print(f"  import_mode      = {validation.import_mode}")
    print(f"  content_hash     = {validation.content_hash}")
    print(f"  section_count    = {validation.section_count}")
    print(f"  chunk_count      = {validation.chunk_count}")
    print(f"  passage_link_count = {validation.passage_link_count}")
    print(f"  raw file SHA256  = {raw_sha256}")
    if mismatches:
        print(
            "\nFIGYELEM: a helyi DB nem egyezik a textus_kb.commentary_runtime "
            "modulban pinnelt EXPECTED_* ertekekkel:"
        )
        for line in mismatches:
            print(f"  - {line}")
        print(
            "Ha ez a build a szandekolt uj eles allapot, frissitsd az "
            "EXPECTED_* konstansokat es a TEXTUS_COMMENTARY_DB_SHA256 "
            "secretet is a fenti ertekekre, mielott productionben elesitedd.\n"
        )
    else:
        print("\nA helyi DB egyezik a pinnelt EXPECTED_* ertekekkel.\n")

    client = get_supabase_client()
    storage = client.storage

    existing_buckets = {b.id for b in storage.list_buckets()}
    if BUCKET_ID not in existing_buckets:
        storage.create_bucket(BUCKET_ID, options={"public": False})
        print(f"Bucket letrehozva: {BUCKET_ID} (privat)")
    else:
        bucket_info = storage.get_bucket(BUCKET_ID)
        if getattr(bucket_info, "public", False):
            raise SystemExit(
                f"BIZTONSAGI LEALLAS: a(z) '{BUCKET_ID}' bucket PUBLIKUS -- "
                "allitsd privatra a Supabase dashboardon, mielott ujra "
                "futtatod ezt a szkriptet."
            )
        print(f"Bucket mar letezik es privat: {BUCKET_ID}")

    bucket = storage.from_(BUCKET_ID)
    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"Feltoltes: {db_path} ({size_mb:.1f} MB) -> {BUCKET_ID}/{OBJECT_PATH}")
    with db_path.open("rb") as f:
        bucket.upload(
            OBJECT_PATH,
            f,
            file_options={"content-type": "application/octet-stream", "upsert": "true"},
        )
    print("Feltoltes kesz.")
    print(f"\nAllitsd be productionben (pl. Streamlit secrets):")
    print(f'  TEXTUS_COMMENTARY_DB_STORAGE_BUCKET = "{BUCKET_ID}"')
    print(f'  TEXTUS_COMMENTARY_DB_STORAGE_OBJECT = "{OBJECT_PATH}"')
    print(f'  TEXTUS_COMMENTARY_DB_SHA256 = "{raw_sha256}"')


if __name__ == "__main__":
    main()
