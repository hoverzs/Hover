"""Reproducible download + verification for CCEL Calvin commentary sources.

Reads ``textus_kb/data/calvin_commentary_source_manifest.json`` (id, url,
local_path, raw_sha256) and fetches each entry to its declared local path,
verifying the downloaded bytes against the manifest's pinned SHA-256
before accepting the file. Raw XML is never committed to git
(``data/raw/`` is gitignored); this manifest is the reproducible
alternative — anyone can re-derive the exact same bytes from the pinned
URL + hash. Fail-closed: a checksum mismatch or an already-present local
file with the wrong hash is rejected, never silently overwritten with
unverified content.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.paths import PROJECT_ROOT

DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT / "textus_kb" / "data" / "calvin_commentary_source_manifest.json"
)
REQUEST_TIMEOUT_SECONDS = 60


class CalvinSourceFetchError(RuntimeError):
    """Raised when a manifest entry cannot be fetched or fails verification."""


@dataclass(frozen=True)
class CalvinSourceEntry:
    id: str
    title: str
    url: str
    local_path: Path
    raw_sha256: str
    byte_size: int | None = None
    work_group: str = ""
    work_title: str = ""
    volume: int | None = None
    coverage: str = ""
    translator: str = ""
    known_unmapped_div2_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CalvinSourceFetchResult:
    id: str
    local_path: Path
    raw_sha256: str
    byte_size: int
    already_present: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "local_path": str(self.local_path),
            "raw_sha256": self.raw_sha256,
            "byte_size": self.byte_size,
            "already_present": self.already_present,
        }


def load_source_manifest(
    path: str | Path | None = None,
) -> list[CalvinSourceEntry]:
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CalvinSourceFetchError(f"Cannot read manifest: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise CalvinSourceFetchError(f"Invalid manifest JSON: {exc}") from exc
    entries = []
    seen_ids: set[str] = set()
    for item in raw.get("sources") or []:
        source_id = str(item["id"])
        if source_id in seen_ids:
            raise CalvinSourceFetchError(f"Duplicate source id in manifest: {source_id!r}")
        seen_ids.add(source_id)
        entries.append(
            CalvinSourceEntry(
                id=source_id,
                title=str(item.get("title") or item["id"]),
                url=str(item["url"]),
                local_path=PROJECT_ROOT / str(item["local_path"]),
                raw_sha256=str(item["raw_sha256"]).strip().lower(),
                byte_size=item.get("byte_size"),
                work_group=str(item.get("work_group") or ""),
                work_title=str(item.get("work_title") or ""),
                volume=item.get("volume"),
                coverage=str(item.get("coverage") or ""),
                translator=str(item.get("translator") or ""),
                known_unmapped_div2_ids=frozenset(item.get("known_unmapped_div2_ids") or ()),
            )
        )
    return entries


def group_entries_by_work(
    entries: list[CalvinSourceEntry],
) -> dict[str, list[CalvinSourceEntry]]:
    """Group manifest entries by their declarative ``work_group`` key,
    ordered by ``volume`` within each group (entries without a volume
    number keep manifest order). An entry with no ``work_group`` is its
    own single-entry group keyed by its own ``id`` (one file, one work —
    the existing single-volume behavior)."""
    groups: dict[str, list[CalvinSourceEntry]] = {}
    for entry in entries:
        key = entry.work_group or entry.id
        groups.setdefault(key, []).append(entry)
    for key, members in groups.items():
        members.sort(key=lambda e: (e.volume if e.volume is not None else 0, e.id))
    return groups


def fetch_source(
    entry: CalvinSourceEntry, *, force: bool = False
) -> CalvinSourceFetchResult:
    """Ensure ``entry.local_path`` holds bytes matching ``entry.raw_sha256``.

    If the file already exists and matches, no network call is made. If it
    exists but does NOT match, this is a fail-closed error (never silently
    overwritten) unless ``force=True``.
    """
    if entry.local_path.is_file() and not force:
        existing_hash = _sha256_file(entry.local_path)
        if existing_hash == entry.raw_sha256:
            return CalvinSourceFetchResult(
                id=entry.id,
                local_path=entry.local_path,
                raw_sha256=existing_hash,
                byte_size=entry.local_path.stat().st_size,
                already_present=True,
            )
        raise CalvinSourceFetchError(
            f"{entry.id}: local file {entry.local_path} exists but its SHA-256 "
            f"({existing_hash}) does not match the manifest "
            f"({entry.raw_sha256}). Pass force=True to re-download."
        )

    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed https CCEL URL from the pinned manifest
            entry.url, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            data = response.read()
    except OSError as exc:
        raise CalvinSourceFetchError(f"{entry.id}: download failed: {exc}") from exc

    digest = hashlib.sha256(data).hexdigest()
    if digest != entry.raw_sha256:
        raise CalvinSourceFetchError(
            f"{entry.id}: downloaded SHA-256 ({digest}) does not match the "
            f"manifest ({entry.raw_sha256}); refusing to write {entry.local_path}."
        )

    entry.local_path.parent.mkdir(parents=True, exist_ok=True)
    entry.local_path.write_bytes(data)
    return CalvinSourceFetchResult(
        id=entry.id,
        local_path=entry.local_path,
        raw_sha256=digest,
        byte_size=len(data),
        already_present=False,
    )


def fetch_all_sources(
    *, manifest_path: str | Path | None = None, force: bool = False
) -> list[CalvinSourceFetchResult]:
    entries = load_source_manifest(manifest_path)
    return [fetch_source(entry, force=force) for entry in entries]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "CalvinSourceEntry",
    "CalvinSourceFetchError",
    "CalvinSourceFetchResult",
    "fetch_all_sources",
    "fetch_source",
    "group_entries_by_work",
    "load_source_manifest",
]
