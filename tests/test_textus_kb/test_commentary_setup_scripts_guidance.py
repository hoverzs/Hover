"""Narrow regression tests for the two Commentary one-time deployment
scripts' DDL/guidance content (2026-09-04 "final cleanup" round).

Neither script's ``main()`` is called here -- these tests only import
module-level constants (safe: no network/side effects at import time) and
read each script's own source text, so nothing here ever touches a real
Supabase project. Purpose: catch a regression back to either of the two
concrete production bugs found and fixed this round --

1. ``scripts/setup_commentary_translation_table.py`` used to emit
   ``create policy if not exists ...`` (not valid PostgreSQL -- ``CREATE
   POLICY`` has no ``IF NOT EXISTS`` clause) and blanket ``using(true)/
   with check(true)`` policies that provide no real access control once
   you know ``SUPABASE_KEY`` is a service_role-class key (which always
   bypasses RLS). Corrected model: RLS enabled with NO policy, `anon`/
   `authenticated` explicitly revoked, `service_role` explicitly granted
   only SELECT/INSERT/UPDATE (never DELETE, since the store never
   deletes rows).
2. Both scripts' printed Streamlit Secrets guidance used to show FLAT
   top-level keys (``TEXTUS_COMMENTARY_DB_STORAGE_BUCKET = "..."`` /
   ``TEXTUS_COMMENTARY_TRANSLATION_BACKEND = "..."``), which
   ``textus_kb.commentary_runtime._commentary_secret_value`` and
   ``textus_kb.commentary_translation_store._translation_secret_value``
   never actually read (they look for a nested ``[commentary_database]``/
   ``[commentary_translation]`` section) -- this was the confirmed root
   cause of the shared translation cache silently falling back to local,
   per-instance SQLite in production.
"""

from __future__ import annotations

from pathlib import Path

from scripts.setup_commentary_translation_table import DDL, TABLE_NAME

TRANSLATION_SCRIPT_PATH = Path("scripts/setup_commentary_translation_table.py")
DATABASE_SCRIPT_PATH = Path("scripts/setup_commentary_database_storage.py")


# --- translation table DDL content -----------------------------------


def test_translation_ddl_table_name_matches_store_default() -> None:
    assert TABLE_NAME == "commentary_translations"
    assert f"create table if not exists {TABLE_NAME}" in DDL


def test_translation_ddl_composite_primary_key_matches_cache_key() -> None:
    """Same composite cache key the store's Python code actually uses as
    the upsert conflict target: section_id, source_fingerprint,
    language, policy_version -- in this exact order."""
    pk_start = DDL.index("primary key")
    pk_clause = DDL[pk_start : DDL.index(")", pk_start) + 1]
    for name in ("section_id", "source_fingerprint", "language", "policy_version"):
        assert name in pk_clause
    assert pk_clause.index("section_id") < pk_clause.index("source_fingerprint")
    assert pk_clause.index("source_fingerprint") < pk_clause.index("language")
    assert pk_clause.index("language") < pk_clause.index("policy_version")


def test_translation_ddl_enables_rls() -> None:
    assert f"alter table {TABLE_NAME}" in DDL
    assert "enable row level security" in DDL


def test_translation_ddl_revokes_anon_and_authenticated() -> None:
    assert f"revoke all on {TABLE_NAME} from anon, authenticated" in DDL


def test_translation_ddl_grants_only_select_insert_update_to_service_role() -> None:
    assert "grant select, insert, update" in DDL
    assert f"on {TABLE_NAME}" in DDL
    assert "to service_role" in DDL
    assert "delete" not in DDL.lower()


def test_translation_ddl_has_no_policy_statements() -> None:
    """The corrected model is grant-based, not policy-based (ld. module
    docstring: SUPABASE_KEY is a service_role-class key that bypasses
    RLS regardless of policy content) -- no CREATE POLICY at all, so the
    previously-invalid ``CREATE POLICY IF NOT EXISTS`` syntax can't
    regress back in, and no blanket ``using(true)`` grant either."""
    lowered = DDL.lower()
    assert "create policy" not in lowered
    assert "using (true)" not in lowered
    assert "with check (true)" not in lowered


# --- Streamlit Secrets guidance: section-based, not flat ---------------


def test_translation_script_guidance_uses_section_not_flat_key() -> None:
    source = TRANSLATION_SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"  [commentary_translation]"' in source
    assert 'backend = \\"supabase\\"' in source or "backend = \"supabase\"" in source
    # The OLD, confirmed-broken flat-key guidance line must not come back.
    assert 'print(\'  TEXTUS_COMMENTARY_TRANSLATION_BACKEND = "supabase"\')' not in source


def test_database_script_guidance_uses_section_not_flat_key() -> None:
    source = DATABASE_SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"  [commentary_database]"' in source
    assert 'storage_bucket = "{BUCKET_ID}"' in source
    # The OLD, confirmed-broken flat-key guidance lines must not come back.
    assert (
        "print(f'  TEXTUS_COMMENTARY_DB_STORAGE_BUCKET = \"{BUCKET_ID}\"')" not in source
    )


def test_database_script_still_uses_s3_multipart_not_simple_upload() -> None:
    """Guards against silently reverting to the simple ``bucket.upload()``
    call that hits Supabase Storage's ~413 Payload Too Large limit well
    under this DB's real size (~534 MB) -- confirmed broken even after a
    Pro-plan upgrade and a 1 GB global Storage limit change, ld. module
    docstring."""
    source = DATABASE_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "_multipart_upload" in source
    assert "TransferConfig" in source
    assert "bucket.upload(" not in source


def test_database_script_s3_credentials_are_local_env_only() -> None:
    """The four S3 credential env vars must be read ONLY from
    ``os.environ`` -- never from Streamlit secrets, never hardcoded --
    matching the explicit "one-time local deployment only" credential
    handling requirement (never in the repo, Streamlit Secrets, or the
    production runtime config)."""
    source = DATABASE_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "os.environ.get(name" in source
    # Skip the module docstring (it explains the unrelated commentary_database
    # Streamlit-secrets bug using the literal text "st.secrets") -- check only
    # the actual code below it for any S3-credential secrets fallback.
    code_only = source.split('"""', 2)[-1]
    assert "st.secrets" not in code_only
    assert "boto3" not in Path("requirements.txt").read_text(encoding="utf-8")
