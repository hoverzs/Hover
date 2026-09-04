"""Reproducible download + verification for the CCEL Matthew Henry commentary source.

Reads ``textus_kb/data/henry_commentary_source_manifest.json`` (6
physical volume files: url, local_path, raw_sha256 each, plus a
declarative ``books`` list describing which div1 in which volume file is
which canonical Bible book) and fetches each volume, verifying the
downloaded bytes against the manifest's pinned SHA-256 before accepting
it. Unlike JFB (one file, whole Bible) and unlike Calvin (45 files, one
per book), Henry is 6 files, each covering several consecutive books —
see ``henry_commentary_thml.py`` for how one file yields several
per-book documents. Raw XML is never committed to git (``data/raw/`` is
gitignored). Fail-closed: a checksum mismatch or an already-present
local file with the wrong hash is rejected, never silently overwritten
with unverified content.
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
    PROJECT_ROOT / "textus_kb" / "data" / "henry_commentary_source_manifest.json"
)
REQUEST_TIMEOUT_SECONDS = 120


class HenrySourceFetchError(RuntimeError):
    """Raised when a Henry volume cannot be fetched or fails verification."""


@dataclass(frozen=True)
class HenryVolumeFile:
    volume: int
    title: str
    url: str
    local_path: Path
    raw_sha256: str
    byte_size: int | None = None


@dataclass(frozen=True)
class KnownEmptyCommentaryDiv:
    """One individually-audited, explicitly declared exception: a real
    ``<scripCom>``-marked commentary ``<div>`` that is completely empty
    in the source (confirmed upstream CCEL markup artifact — see
    ``henry_commentary_thml.py``'s module docstring). Declared in the
    source manifest, never invented by the parser; ``reason`` and
    ``classification`` are threaded into the built commentary.sqlite3
    (via import_batches.report) so QA can report a dedicated category
    instead of an unexplained gap.
    """

    div2_id: str
    commentary_div_id: str
    reason: str
    classification: str


@dataclass(frozen=True)
class HenryBookEntry:
    """One canonical Bible book, as a div1 within one Henry volume file.

    ``div1_id`` is only unique *within* its own volume (e.g. "Ez" means
    Ezra in volume 2 but Ezekiel in volume 4) — always resolve it
    together with ``volume``, never on its own.
    """

    order: int
    volume: int
    div1_id: str
    title: str
    contributor_raw_name: str
    coverage: str = ""
    authorship_note: str = ""
    known_empty_commentary_divs: tuple[KnownEmptyCommentaryDiv, ...] = ()


@dataclass(frozen=True)
class HenrySourceManifest:
    manifest_version: str
    description: str
    volumes: tuple[HenryVolumeFile, ...]
    books: tuple[HenryBookEntry, ...]

    def volume_by_number(self, volume: int) -> HenryVolumeFile:
        for v in self.volumes:
            if v.volume == volume:
                return v
        raise HenrySourceFetchError(f"Unknown Henry volume: {volume!r}")


@dataclass(frozen=True)
class HenrySourceFetchResult:
    volume: int
    local_path: Path
    raw_sha256: str
    byte_size: int
    already_present: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume": self.volume,
            "local_path": str(self.local_path),
            "raw_sha256": self.raw_sha256,
            "byte_size": self.byte_size,
            "already_present": self.already_present,
        }


def load_source_manifest(path: str | Path | None = None) -> HenrySourceManifest:
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HenrySourceFetchError(f"Cannot read manifest: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise HenrySourceFetchError(f"Invalid manifest JSON: {exc}") from exc

    volumes: list[HenryVolumeFile] = []
    seen_volumes: set[int] = set()
    for item in raw.get("volumes") or []:
        volume = int(item["volume"])
        if volume in seen_volumes:
            raise HenrySourceFetchError(f"Duplicate volume in Henry manifest: {volume!r}")
        seen_volumes.add(volume)
        volumes.append(
            HenryVolumeFile(
                volume=volume,
                title=str(item.get("title") or f"Volume {volume}"),
                url=str(item["url"]),
                local_path=PROJECT_ROOT / str(item["local_path"]),
                raw_sha256=str(item["raw_sha256"]).strip().lower(),
                byte_size=item.get("byte_size"),
            )
        )
    volumes.sort(key=lambda v: v.volume)

    books: list[HenryBookEntry] = []
    seen_keys: set[tuple[int, str]] = set()
    seen_orders: set[int] = set()
    for item in raw.get("books") or []:
        volume = int(item["volume"])
        div1_id = str(item["div1_id"])
        key = (volume, div1_id)
        if key in seen_keys:
            raise HenrySourceFetchError(f"Duplicate (volume, div1_id) in Henry manifest: {key!r}")
        seen_keys.add(key)
        order = int(item["order"])
        if order in seen_orders:
            raise HenrySourceFetchError(f"Duplicate order in Henry manifest: {order!r}")
        seen_orders.add(order)
        books.append(
            HenryBookEntry(
                order=order,
                volume=volume,
                div1_id=div1_id,
                title=str(item["title"]),
                contributor_raw_name=str(item["contributor_raw_name"]),
                coverage=str(item.get("coverage") or item["title"]),
                authorship_note=str(item.get("authorship_note") or ""),
                known_empty_commentary_divs=tuple(
                    KnownEmptyCommentaryDiv(
                        div2_id=str(section["div2_id"]),
                        commentary_div_id=str(section["commentary_div_id"]),
                        reason=str(section["reason"]),
                        classification=str(section["classification"]),
                    )
                    for section in (item.get("known_empty_commentary_divs") or ())
                ),
            )
        )
    books.sort(key=lambda b: b.order)

    return HenrySourceManifest(
        manifest_version=str(raw.get("manifest_version") or ""),
        description=str(raw.get("description") or ""),
        volumes=tuple(volumes),
        books=tuple(books),
    )


def fetch_volume(volume: HenryVolumeFile, *, force: bool = False) -> HenrySourceFetchResult:
    """Ensure ``volume.local_path`` holds bytes matching ``volume.raw_sha256``.

    If the file already exists and matches, no network call is made. If it
    exists but does NOT match, this is a fail-closed error (never silently
    overwritten) unless ``force=True``.
    """
    if volume.local_path.is_file() and not force:
        existing_hash = _sha256_file(volume.local_path)
        if existing_hash == volume.raw_sha256:
            return HenrySourceFetchResult(
                volume=volume.volume,
                local_path=volume.local_path,
                raw_sha256=existing_hash,
                byte_size=volume.local_path.stat().st_size,
                already_present=True,
            )
        raise HenrySourceFetchError(
            f"volume {volume.volume}: local file {volume.local_path} exists but its SHA-256 "
            f"({existing_hash}) does not match the manifest "
            f"({volume.raw_sha256}). Pass force=True to re-download."
        )

    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed https CCEL URL from the pinned manifest
            volume.url, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            data = response.read()
    except OSError as exc:
        raise HenrySourceFetchError(f"volume {volume.volume}: download failed: {exc}") from exc

    digest = hashlib.sha256(data).hexdigest()
    if digest != volume.raw_sha256:
        raise HenrySourceFetchError(
            f"volume {volume.volume}: downloaded SHA-256 ({digest}) does not match the "
            f"manifest ({volume.raw_sha256}); refusing to write {volume.local_path}."
        )

    volume.local_path.parent.mkdir(parents=True, exist_ok=True)
    volume.local_path.write_bytes(data)
    return HenrySourceFetchResult(
        volume=volume.volume,
        local_path=volume.local_path,
        raw_sha256=digest,
        byte_size=len(data),
        already_present=False,
    )


def fetch_all_volumes(
    *, manifest_path: str | Path | None = None, force: bool = False
) -> list[HenrySourceFetchResult]:
    manifest = load_source_manifest(manifest_path)
    return [fetch_volume(v, force=force) for v in manifest.volumes]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "HenryBookEntry",
    "HenrySourceFetchError",
    "HenrySourceFetchResult",
    "HenrySourceManifest",
    "HenryVolumeFile",
    "KnownEmptyCommentaryDiv",
    "fetch_all_volumes",
    "fetch_volume",
    "load_source_manifest",
]
