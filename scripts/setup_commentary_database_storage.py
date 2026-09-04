"""Egyszeri beallitas: privat Supabase Storage bucket + nagy artifact
feltoltes a Commentary DB-hez.

Ugyanaz a minta, mint `scripts/setup_ruf_bible_storage.py` es a hymn/
theology modulok sajat (nem repoban levo) feltoltesei: egy PRIVAT bucket
(`public: False`), es a helyi, mar felepitett `commentary.sqlite3`
feltoltese oda. Innen toltodik le futasidoben a
`textus_kb.commentary_runtime.ensure_commentary_database` /
`ensure_status` fuggvenyekkel -- production sose epiti ujra a teljes
Calvin/JFB/Henry corpust.

FONTOS -- upload-transport, NEM runtime-valtozas: a ~534 MB-os DB
meghaladja a Supabase Storage sima (nem resumable) egy-request-es
upload-vegpontjanak gyakorlati meretkorlatjat (413 Payload Too Large --
ezt a projekt Pro-csomagra emelese es a globalis Storage file-size limit
1 GB-ra allitasa sem oldotta meg, ld. a 2026-09-04-i audit ebben a
korben). Ez a szkript ezert kizarolag a FELTOLTEST valtja at Supabase
S3-compatible Multipart Upload-ra (boto3), a Supabase sajat dokumentacioja
altal ajanlott modon nagy fajlokhoz. A PRODUCTION LETOLTES ettol teljesen
fuggetlen es VALTOZATLAN marad: `commentary_runtime.py` tovabbra is a
sima Supabase Storage API-t hasznalja (`client.storage.from_(bucket).
download(...)`), nem kap semmilyen S3/boto3 fuggoseget -- a multipart
upload vegen egyetlen, kozonseges `commentary.sqlite3` Storage object
jon letre, amit a runtime a megszokott modon tud letolteni. A bucket es
az object neve valtozatlan:
    bucket: commentary-db-private
    object: commentary.sqlite3

A szkript a feltoltes elott validalja a helyi DB-t (sema + tartalmi
szamlalok + content_hash) a `textus_kb.commentary_runtime` modulban
rogzitett `EXPECTED_*` ertekek ellen, es figyelmeztet (de nem all le), ha
eltetes -- igy ha idokozben ujra epul/frissul a corpus, ez a szkript
akkor is jelzi, ha a pinnelt konstansokat is frissiteni kell a
feltoltes elott.

Feltoltes utan a szkript VISSZATOLTI az objectet a rendes (nem S3)
Supabase Storage download API-n keresztul -- ugyanazon az uton, amit a
production runtime is hasznalna --, es a letoltott bajtok SHA256-jat
osszeveti a helyi fajl SHA256-javal. Ez ket kulon integritasi ertek:
    - raw file SHA256 (a nyers .sqlite3 fajl bajtjai -- ezt hasonlitja
      ossze ez a szkript letoltes utan)
    - Commentary content_hash (a `validate_commentary_database()` altal
      szamitott, a DB TARTALMAra vonatkozo hash -- ezt a lokalis build
      mar validalta, feltoltes/letoltes nem befolyasolja)

Hasznalat (egyszeri, manualis futtatas -- NEM fut le automatikusan):
    python scripts/setup_commentary_database_storage.py

Ket, EGYMASTOL FUGGETLEN hitelesito adatkeszlet szukseges, mindket
kizarolag LOKALIS kornyezeti valtozokbol/secrets-bol olvasva -- egyik
sem kerul a repoba, Streamlit Secrets-be, vagy a production runtime
configba:

1) A rendes Supabase kliens (bucket letrehozas/ellenorzes + a feltoltes
   utani visszaellenorzo letoltes) -- ld. `supabase_client.
   get_supabase_client()`: SUPABASE_URL / SUPABASE_KEY env valtozok
   (vagy `.streamlit/secrets.toml` `[supabase]`), MAR MEGLEVO,
   valtozatlan konfiguracio.

2) Az S3-compatible Multipart Upload-hoz (CSAK ehhez az egyszeri
   szkripthez -- a production runtime SOSE hasznalja):
    TEXTUS_COMMENTARY_S3_ENDPOINT_URL   -- pl. https://<project-ref>.supabase.co/storage/v1/s3
    TEXTUS_COMMENTARY_S3_REGION         -- a projekt Storage regioja
    TEXTUS_COMMENTARY_S3_ACCESS_KEY_ID
    TEXTUS_COMMENTARY_S3_SECRET_ACCESS_KEY
   Ezeket a Supabase Dashboard -> Project Settings -> Storage -> "S3
   Connection" (S3 access keys) oldalon lehet letrehozni. A szkript
   SOSE logolja/irja ki egyik hitelesito adat erteket sem.

Sikeres feltoltes utan a futtato kornyezetben (Streamlit Secrets) be kell
allitani -- SECTION-alapu forma, ahogy `textus_kb.commentary_runtime.
_commentary_secret_value` ténylegesen olvassa (`st.secrets["commentary_
database"][key]`); NEM egy flat, top-level `TEXTUS_COMMENTARY_DB_*` kulcs
(az korabban pontosan ezt a hibat okozta -- a runtime meg env-valtozokent
is nezi ugyan ezeket a neveket, de a Streamlit Secrets-be flat kulcskent
irt ertekek egyiket sem talalja meg):
    [commentary_database]
    storage_bucket = "commentary-db-private"
    storage_object = "commentary.sqlite3"
    database_sha256 = "<a szkript altal kiirt, visszatoltessel VERIFIKALT
        raw file SHA256>"

Fuggoseg: `pip install boto3` -- kizarolag ennek az egyszeri
deployment-szkriptnek a futtatasahoz, NINCS hozzaadva a `requirements.txt`
(production) fajlhoz, mert a production runtime nem hasznalja.
"""

from __future__ import annotations

import hashlib
import os
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

S3_ENDPOINT_ENV_VAR = "TEXTUS_COMMENTARY_S3_ENDPOINT_URL"
S3_REGION_ENV_VAR = "TEXTUS_COMMENTARY_S3_REGION"
S3_ACCESS_KEY_ID_ENV_VAR = "TEXTUS_COMMENTARY_S3_ACCESS_KEY_ID"
S3_SECRET_ACCESS_KEY_ENV_VAR = "TEXTUS_COMMENTARY_S3_SECRET_ACCESS_KEY"

# Reasonable, not-too-small part size for a ~534 MB single-object upload --
# large enough to keep the part count (and per-part HTTP overhead) small,
# small enough that a single part failure only costs a modest re-send.
# boto3's TransferManager streams each part from disk; the whole file is
# never held in memory at once.
_MULTIPART_CHUNK_SIZE_BYTES = 64 * 1024 * 1024  # 64 MiB
_MULTIPART_THRESHOLD_BYTES = 64 * 1024 * 1024  # anything smaller: single PUT


def _read_required_s3_env() -> dict[str, str]:
    """Reads all four S3 env vars, returning only the ones that ARE set.
    Never raises here -- the caller decides what to do with a partial/empty
    result, so main() can print one clear, complete list of what's missing
    instead of failing on the first absent variable."""
    names = (
        S3_ENDPOINT_ENV_VAR,
        S3_REGION_ENV_VAR,
        S3_ACCESS_KEY_ID_ENV_VAR,
        S3_SECRET_ACCESS_KEY_ENV_VAR,
    )
    return {name: value for name in names if (value := os.environ.get(name, "").strip())}


def _s3_client(env: dict[str, str]):  # noqa: ANN201 - boto3 client, avoid hard import at module scope
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=env[S3_ENDPOINT_ENV_VAR],
        region_name=env[S3_REGION_ENV_VAR],
        aws_access_key_id=env[S3_ACCESS_KEY_ID_ENV_VAR],
        aws_secret_access_key=env[S3_SECRET_ACCESS_KEY_ENV_VAR],
    )


def _multipart_upload(s3_client, db_path: Path, *, bucket_id: str, object_path: str) -> None:
    """Streams ``db_path`` to Supabase's S3-compatible endpoint via boto3's
    managed multipart transfer -- reads the file in ``_MULTIPART_CHUNK_
    SIZE_BYTES``-sized parts (never buffers the whole file in memory), and
    on ANY failure boto3's own ``TransferManager`` aborts the in-progress
    multipart upload and leaves no partial/incomplete object behind (this
    is built into ``upload_file``'s managed-transfer machinery, not
    hand-rolled here). Result: exactly one ``commentary.sqlite3`` object,
    never a permanently sharded set of parts."""
    from boto3.s3.transfer import TransferConfig

    config = TransferConfig(
        multipart_threshold=_MULTIPART_THRESHOLD_BYTES,
        multipart_chunksize=_MULTIPART_CHUNK_SIZE_BYTES,
        max_concurrency=4,
        use_threads=True,
    )
    s3_client.upload_file(
        str(db_path),
        bucket_id,
        object_path,
        Config=config,
        ExtraArgs={"ContentType": "application/octet-stream"},
    )


def _verify_remote_object(
    s3_client, supabase_client, *, bucket_id: str, object_path: str, expected_sha256: str
) -> tuple[int, str]:
    """Post-upload verification: HEAD for the remote object's size (via
    the S3-compatible endpoint), then a full round-trip download via the
    ORDINARY (non-S3) Supabase Storage download API -- the exact same
    call ``commentary_runtime._download_and_install`` uses in production
    -- hashed and compared against the local file's SHA256. Proves both
    that the object landed correctly AND that production's own download
    path can actually fetch it."""
    head = s3_client.head_object(Bucket=bucket_id, Key=object_path)
    remote_size = int(head["ContentLength"])

    data = supabase_client.storage.from_(bucket_id).download(object_path)
    downloaded_sha256 = hashlib.sha256(data).hexdigest()
    if downloaded_sha256 != expected_sha256:
        raise SystemExit(
            "INTEGRITAS HIBA: a visszatoltott object SHA256-ja NEM egyezik a "
            f"helyi fajleval (vart: {expected_sha256}, kapott: {downloaded_sha256}). "
            "A feltoltott object nem megbizhato -- ELLENORIZD kezzel a Supabase "
            "dashboardon, mielott productionben hasznalod."
        )
    return remote_size, downloaded_sha256


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

    s3_env = _read_required_s3_env()
    missing = [
        name
        for name in (
            S3_ENDPOINT_ENV_VAR,
            S3_REGION_ENV_VAR,
            S3_ACCESS_KEY_ID_ENV_VAR,
            S3_SECRET_ACCESS_KEY_ENV_VAR,
        )
        if name not in s3_env
    ]
    if missing:
        raise SystemExit(
            "Hianyzo S3 hitelesito kornyezeti valtozo(k), a feltoltes NEM "
            "indul el:\n"
            + "\n".join(f"  - {name}" for name in missing)
            + "\n\nEzeket a Supabase Dashboard -> Project Settings -> Storage "
            "-> \"S3 Connection\" oldalon talalod/hozod letre (access key + "
            "secret key), es kizarolag LOKALIS kornyezeti valtozokent allitsd "
            "be -- SOSE a repoba vagy Streamlit Secrets-be."
        )

    try:
        import boto3  # noqa: F401
    except ImportError:
        raise SystemExit(
            "A boto3 csomag nincs telepitve. Telepitsd: pip install boto3 "
            "(ez kizarolag ennek az egyszeri deployment-szkriptnek a "
            "fuggosege, a production runtime nem hasznalja, es nincs a "
            "requirements.txt-ben)."
        )

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

    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(
        f"Feltoltes (S3 multipart): {db_path} ({size_mb:.1f} MB) -> "
        f"{BUCKET_ID}/{OBJECT_PATH}"
    )
    s3_client = _s3_client(s3_env)
    try:
        _multipart_upload(s3_client, db_path, bucket_id=BUCKET_ID, object_path=OBJECT_PATH)
    except Exception as exc:  # noqa: BLE001 - report, never leak credentials via traceback text
        raise SystemExit(f"Feltoltes sikertelen (S3 multipart): {exc}")
    print("Feltoltes kesz -- ellenorzes...")

    remote_size, verified_sha256 = _verify_remote_object(
        s3_client,
        client,
        bucket_id=BUCKET_ID,
        object_path=OBJECT_PATH,
        expected_sha256=raw_sha256,
    )
    remote_size_mb = remote_size / (1024 * 1024)
    print(f"  remote object meret = {remote_size} bajt ({remote_size_mb:.1f} MB)")
    print(f"  visszatoltott SHA256 = {verified_sha256}")
    print("  EGYEZIK a helyi fajl SHA256-javal -- integritas OK.")

    print("\nAllitsd be productionben Streamlit Secrets-ben (section-alapu forma --")
    print("NEM flat TEXTUS_COMMENTARY_DB_* kulcskent, ld. a modul docstringjet):")
    print("  [commentary_database]")
    print(f'  storage_bucket = "{BUCKET_ID}"')
    print(f'  storage_object = "{OBJECT_PATH}"')
    print(f'  database_sha256 = "{raw_sha256}"')


if __name__ == "__main__":
    main()
