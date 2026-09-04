"""Egyszeri beallitas: megosztott Supabase Postgres tabla a magyar
Commentary-forditasi cache-hez (`textus_kb.commentary_translation_store`
"supabase" backendje).

A Supabase Python kliens NEM tud DDL-t (CREATE TABLE) futtatni -- ehhez
nincs praducens minta ebben a repoban (a `supabase_client.py` csak
mar-letezo tablakat/storage-ot er el). A tabla letrehozasa ezert egy
MANUALIS lepes: nyisd meg a Supabase projekt SQL Editor-jat, es futtasd
le ott a lenti DDL-t.

Ez a szkript NEM hoz letre semmit -- csak (1) kiirja a pontos DDL-t, es
(2) ha mar lefuttattad a DDL-t, ellenorzi, hogy a tabla elerheto-e es a
vart oszlopokkal rendelkezik-e (egy read-only SELECT ... LIMIT 0 -- nem
ir semmit).

A hozzaferesi modell (2026-09-04-i audit alapjan javitva -- ld. a "final
cleanup" kor jegyzeteit): a production `SUPABASE_KEY` egy Supabase
"secret" (service_role-osztalyu) kulcs, ami MINDIG megkeruli a Row Level
Security-t, fuggetlenul attol, milyen policy van (vagy nincs) a tablan.
Emiatt egy `using(true)/with check(true)` blanket policy semmilyen
valodi hozzaferes-vezerlest nem ad -- csak felesleges kockazatot, ha a
kulcstipus valaha valtozna. A helyes modell ezert NEM policy-alapu,
hanem grant-alapu:
    - RLS bekapcsolva marad (vedelmi retegkent, policy nelkul -- alapertelmezett
      tiltas minden nem-service_role szerepre);
    - `anon`/`authenticated` EXPLICIT revoke-olva (meg egy jovobeli,
      veletlenul hozza adott policy sem adna nekik hozzaferest, mert a
      tabla-szintu jogosultsaguk is hianyzik);
    - `service_role` EXPLICIT grant: SELECT, INSERT, UPDATE -- pontosan
      azok a muveletek, amiket `commentary_translation_store.py` tenylegesen
      vegez (`_supabase_get_translation` / `_supabase_save_translation`,
      utobbi upsert = insert+update). Nincs DELETE grant, mert a store
      sosem torol sort.
    - Nincs `CREATE POLICY` egyaltalan -- ez elkeruli a korabbi (hibas)
      valtozat `CREATE POLICY IF NOT EXISTS` szintaxisat is, ami NEM
      ervenyes PostgreSQL (a `CREATE POLICY` nem tamogatja az
      `IF NOT EXISTS` zaradekot, csak a `CREATE TABLE`/`CREATE INDEX`).

Hasznalat:
    python scripts/setup_commentary_translation_table.py

A backend-valasztas Streamlit Secrets-ben SECTION-alapu (ahogy
`textus_kb.commentary_translation_store._translation_secret_value`
ténylegesen olvassa: `st.secrets["commentary_translation"][key]`) -- NEM
egy flat, top-level `TEXTUS_COMMENTARY_TRANSLATION_BACKEND` kulcs (ez
korabban pontosan azt a production hibat okozta, hogy minden forditas a
lokalis, a container-ujrainditas utan elveszo SQLite cache-be irodott,
sosem a megosztott Postgres tablaba -- ld. a "final cleanup" kor
gyokerok-elemzeset):
    [commentary_translation]
    backend = "supabase"
    table = "commentary_translations"  # (opcionalis, ez az alapertelmezett)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textus_kb.commentary_translation_store import DEFAULT_TRANSLATION_SUPABASE_TABLE

TABLE_NAME = DEFAULT_TRANSLATION_SUPABASE_TABLE

DDL = f"""
create table if not exists {TABLE_NAME} (
    section_id text not null,
    source_fingerprint text not null,
    language text not null,
    policy_version text not null,
    translated_text text not null,
    provider_model text not null default '',
    created_at timestamptz not null default now(),
    primary key (
        section_id,
        source_fingerprint,
        language,
        policy_version
    )
);

alter table {TABLE_NAME}
enable row level security;

revoke all on {TABLE_NAME} from anon, authenticated;

grant select, insert, update
on {TABLE_NAME}
to service_role;
""".strip()


def main() -> None:
    print("Ezt a DDL-t futtasd le MANUALISAN a Supabase projekt SQL Editor-jaban:\n")
    print(DDL)
    print(
        "\nUtana allitsd be productionben Streamlit Secrets-ben (section-alapu "
        "forma -- NEM flat TEXTUS_COMMENTARY_TRANSLATION_BACKEND kulcskent, "
        "ld. a modul docstringjet), hogy a forditasi cache erre a megosztott "
        "tablara aljon at a helyi SQLite helyett:"
    )
    print("  [commentary_translation]")
    print('  backend = "supabase"')
    print(f'  table = "{TABLE_NAME}"  # (opcionalis, ez az alapertelmezett)')

    print("\nEllenorzes: a tabla mar elerheto-e (csak olvasas, LIMIT 0)...")
    try:
        from supabase_client import get_supabase_client

        client = get_supabase_client()
        client.table(TABLE_NAME).select("section_id").limit(0).execute()
    except Exception as exc:  # noqa: BLE001
        print(
            f"  Meg nem erheto el (ez varhato, ha a DDL-t meg nem futtattad le): {exc}"
        )
        return
    print(f"  OK -- a(z) '{TABLE_NAME}' tabla mar letezik es elerheto.")


if __name__ == "__main__":
    main()
