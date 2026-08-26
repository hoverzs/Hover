"""Runtime bootstrap for the gitignored Theology SQLite artifact.

Lazy, fail-closed provisioning modeled on ``bible_engine.hymn_repository``.
Does not import on module load, does not call a model provider, and does not
download CCEL/XML sources.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    TheologyImportError,
    TheologyStoreValidation,
    validate_theology_database,
)

# Pinned Calvin Institutes v1 production artifact (store metadata / counts).
# The SQLite *file* SHA-256 is configuration-only and is never invented here.
EXPECTED_SCHEMA_VERSION = "1"
EXPECTED_IMPORT_MODE = "ccel_thml"
EXPECTED_CONTENT_HASH = (
    "edc70f3389d622f105eda709a6592ced961c178c0e205cbcf3aeaef601a63b71"
)
EXPECTED_AUTHOR_COUNT = 1
EXPECTED_WORK_COUNT = 1
EXPECTED_EDITION_COUNT = 1
EXPECTED_SECTION_COUNT = 1370
EXPECTED_CHUNK_COUNT = 1282
EXPECTED_PASSAGE_LINK_COUNT = 3553

THEOLOGY_STORAGE_BUCKET_ENV_VAR = "TEXTUS_THEOLOGY_DB_STORAGE_BUCKET"
THEOLOGY_STORAGE_OBJECT_ENV_VAR = "TEXTUS_THEOLOGY_DB_STORAGE_OBJECT"
THEOLOGY_DATABASE_SHA256_ENV_VAR = "TEXTUS_THEOLOGY_DB_SHA256"


@dataclass(frozen=True)
class TheologyRuntimeStatus:
    available: bool
    reason: str
    database_path: str
    detail: str = ""


def get_status(
    database_path: str | Path | None = None,
    *,
    expected_database_sha256: str | None = None,
) -> TheologyRuntimeStatus:
    """Validate a local Theology DB without downloading."""
    path = _resolve_database_path(database_path)
    expected = _resolve_expected_sha256(expected_database_sha256)
    return _validate_database(path, expected_database_sha256=expected)


def ensure_theology_database(
    database_path: str | Path | None = None,
    *,
    storage_bucket_id: str | None = None,
    storage_object_path: str | None = None,
    expected_database_sha256: str | None = None,
) -> TheologyRuntimeStatus:
    """Ensure a valid local Theology SQLite file, downloading if allowed.

    Explicit ``database_path`` without storage kwargs never touches the network
    (test/tmp paths). The default path may lazily download from private storage.
    Passing storage kwargs opts into download even for an explicit target path.
    """
    explicit_path = database_path is not None
    path = _resolve_database_path(database_path)
    expected = _resolve_expected_sha256(expected_database_sha256)
    status = _validate_database(path, expected_database_sha256=expected)
    if status.available:
        return status

    allow_download = (not explicit_path) or (
        storage_bucket_id is not None or storage_object_path is not None
    )
    if not allow_download:
        return status

    bucket_id = storage_bucket_id or _configured_storage_bucket_id()
    object_path = storage_object_path or _configured_storage_object_path()
    if not bucket_id or not object_path:
        return TheologyRuntimeStatus(
            available=False,
            reason="storage_not_configured",
            database_path=str(path),
            detail=status.reason,
        )

    try:
        from supabase_client import get_supabase_client

        client = get_supabase_client()
        data = client.storage.from_(bucket_id).download(object_path)
    except Exception as exc:  # noqa: BLE001 - runtime bootstrap must fail closed
        return TheologyRuntimeStatus(
            available=False,
            reason="download_failed",
            database_path=str(path),
            detail=str(exc),
        )
    if not data:
        return TheologyRuntimeStatus(
            available=False,
            reason="download_empty",
            database_path=str(path),
        )

    if expected and _sha256_bytes(data) != expected:
        return TheologyRuntimeStatus(
            available=False,
            reason="database_checksum_mismatch",
            database_path=str(path),
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    try:
        tmp_path.write_bytes(data)
        downloaded_status = _validate_database(
            tmp_path, expected_database_sha256=expected
        )
        if not downloaded_status.available:
            return TheologyRuntimeStatus(
                available=False,
                reason=downloaded_status.reason,
                database_path=str(path),
                detail=downloaded_status.detail,
            )
        tmp_path.replace(path)
    except OSError as exc:
        return TheologyRuntimeStatus(
            available=False,
            reason="write_failed",
            database_path=str(path),
            detail=str(exc),
        )
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return _validate_database(path, expected_database_sha256=expected)


def _resolve_database_path(database_path: str | Path | None) -> Path:
    return Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH


def _resolve_expected_sha256(expected_database_sha256: str | None) -> str:
    if expected_database_sha256 is not None:
        return expected_database_sha256.strip().lower()
    return _configured_database_sha256()


def _validate_database(
    path: Path, *, expected_database_sha256: str = ""
) -> TheologyRuntimeStatus:
    if not path.is_file():
        return TheologyRuntimeStatus(False, "database_missing", str(path))
    if expected_database_sha256:
        try:
            digest = _sha256_file(path)
        except OSError as exc:
            return TheologyRuntimeStatus(False, "database_unopenable", str(path), str(exc))
        if digest != expected_database_sha256:
            return TheologyRuntimeStatus(False, "database_checksum_mismatch", str(path))
    try:
        validation = validate_theology_database(path)
    except FileNotFoundError:
        return TheologyRuntimeStatus(False, "database_missing", str(path))
    except (OSError, sqlite3.Error) as exc:
        return TheologyRuntimeStatus(False, "database_unopenable", str(path), str(exc))
    except TheologyImportError as exc:
        return TheologyRuntimeStatus(False, "schema_incompatible", str(path), str(exc))
    if validation.schema_version != EXPECTED_SCHEMA_VERSION:
        return TheologyRuntimeStatus(
            False,
            "schema_incompatible",
            str(path),
            f"schema_version={validation.schema_version or '<missing>'}",
        )
    mismatches = _invariant_mismatches(validation)
    if mismatches:
        return TheologyRuntimeStatus(
            False,
            "metadata_validation_failed",
            str(path),
            "; ".join(mismatches),
        )
    return TheologyRuntimeStatus(True, "ok", str(path))


def _invariant_mismatches(validation: TheologyStoreValidation) -> list[str]:
    expected = {
        "import_mode": (validation.import_mode, EXPECTED_IMPORT_MODE),
        "content_hash": (validation.content_hash, EXPECTED_CONTENT_HASH),
        "author_count": (validation.author_count, EXPECTED_AUTHOR_COUNT),
        "work_count": (validation.work_count, EXPECTED_WORK_COUNT),
        "edition_count": (validation.edition_count, EXPECTED_EDITION_COUNT),
        "section_count": (validation.section_count, EXPECTED_SECTION_COUNT),
        "chunk_count": (validation.chunk_count, EXPECTED_CHUNK_COUNT),
        "passage_link_count": (validation.passage_link_count, EXPECTED_PASSAGE_LINK_COUNT),
    }
    return [
        f"{name}={actual} expected={want}"
        for name, (actual, want) in expected.items()
        if actual != want
    ]


def _configured_storage_bucket_id() -> str:
    env_value = os.environ.get(THEOLOGY_STORAGE_BUCKET_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return _theology_secret_value("storage_bucket")


def _configured_storage_object_path() -> str:
    env_value = os.environ.get(THEOLOGY_STORAGE_OBJECT_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return _theology_secret_value("storage_object")


def _configured_database_sha256() -> str:
    env_value = os.environ.get(THEOLOGY_DATABASE_SHA256_ENV_VAR, "").strip()
    if env_value:
        return env_value.strip().lower()
    return _theology_secret_value("database_sha256").strip().lower()


def _theology_secret_value(key: str) -> str:
    try:
        import streamlit as st

        cfg = st.secrets.get("theology_database", {})
        if isinstance(cfg, dict):
            value = cfg.get(key)
        else:
            value = getattr(cfg, key, "")
        return str(value or "").strip()
    except Exception:
        return ""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "EXPECTED_AUTHOR_COUNT",
    "EXPECTED_CHUNK_COUNT",
    "EXPECTED_CONTENT_HASH",
    "EXPECTED_EDITION_COUNT",
    "EXPECTED_IMPORT_MODE",
    "EXPECTED_PASSAGE_LINK_COUNT",
    "EXPECTED_SCHEMA_VERSION",
    "EXPECTED_SECTION_COUNT",
    "EXPECTED_WORK_COUNT",
    "THEOLOGY_DATABASE_SHA256_ENV_VAR",
    "THEOLOGY_STORAGE_BUCKET_ENV_VAR",
    "THEOLOGY_STORAGE_OBJECT_ENV_VAR",
    "TheologyRuntimeStatus",
    "ensure_theology_database",
    "get_status",
]
