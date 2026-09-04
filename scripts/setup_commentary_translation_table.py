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

Hasznalat:
    python scripts/setup_commentary_translation_table.py
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
    primary key (section_id, source_fingerprint, language, policy_version)
);

-- Row Level Security: enable, and allow the anon/service key this app
-- already uses to read/write (mirrors how the app already trusts its
-- single Supabase key for Storage access -- no separate end-user auth
-- layer exists yet in this repo's Supabase usage). Tighten this policy
-- if/when per-user auth is introduced.
alter table {TABLE_NAME} enable row level security;

create policy if not exists "{TABLE_NAME}_read_all"
    on {TABLE_NAME} for select
    using (true);

create policy if not exists "{TABLE_NAME}_write_all"
    on {TABLE_NAME} for insert
    with check (true);

create policy if not exists "{TABLE_NAME}_upsert_update"
    on {TABLE_NAME} for update
    using (true)
    with check (true);
""".strip()


def main() -> None:
    print("Ezt a DDL-t futtasd le MANUALISAN a Supabase projekt SQL Editor-jaban:\n")
    print(DDL)
    print(
        "\nUtana allitsd be productionben (pl. Streamlit secrets), hogy a "
        "forditasi cache erre a megosztott tablara aljon at a helyi SQLite "
        "helyett:"
    )
    print('  TEXTUS_COMMENTARY_TRANSLATION_BACKEND = "supabase"')
    print(f'  TEXTUS_COMMENTARY_TRANSLATION_TABLE = "{TABLE_NAME}"  # (opcionalis, ez az alapertelmezett)')

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
