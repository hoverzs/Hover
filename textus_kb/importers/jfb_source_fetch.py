"""Reproducible download + verification for the CCEL JFB commentary source.

Reads ``textus_kb/data/jfb_commentary_source_manifest.json`` (one physical
file: url, local_path, raw_sha256, plus a declarative ``books`` list
describing which div2 in that file is which canonical Bible book) and
fetches the single upstream file, verifying the downloaded bytes against
the manifest's pinned SHA-256 before accepting it. Unlike Calvin (45
per-volume CCEL files), JFB is one ThML/XML file covering the whole Bible;
the corpus build later slices per-book documents out of that one parsed
tree — see ``jfb_commentary_thml.py``. Raw XML is never committed to git
(``data/raw/`` is gitignored). Fail-closed: a checksum mismatch or an
already-present local file with the wrong hash is rejected, never
silently overwritten with unverified content.
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
    PROJECT_ROOT / "textus_kb" / "data" / "jfb_commentary_source_manifest.json"
)
REQUEST_TIMEOUT_SECONDS = 120


class JfbSourceFetchError(RuntimeError):
    """Raised when the JFB source cannot be fetched or fails verification."""


@dataclass(frozen=True)
class JfbSourceFile:
    id: str
    title: str
    url: str
    local_path: Path
    raw_sha256: str
    byte_size: int | None = None


@dataclass(frozen=True)
class JfbBookEntry:
    """One canonical Bible book, as a div2 within the single JFB source file."""

    order: int
    div2_id: str
    title: str
    testament: str
    contributor_raw_name: str
    coverage: str = ""


@dataclass(frozen=True)
class JfbSourceManifest:
    manifest_version: str
    description: str
    source: JfbSourceFile
    books: tuple[JfbBookEntry, ...]


@dataclass(frozen=True)
class JfbSourceFetchResult:
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


def load_source_manifest(path: str | Path | None = None) -> JfbSourceManifest:
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise JfbSourceFetchError(f"Cannot read manifest: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise JfbSourceFetchError(f"Invalid manifest JSON: {exc}") from exc

    src = raw.get("source") or {}
    source = JfbSourceFile(
        id=str(src["id"]),
        title=str(src.get("title") or src["id"]),
        url=str(src["url"]),
        local_path=PROJECT_ROOT / str(src["local_path"]),
        raw_sha256=str(src["raw_sha256"]).strip().lower(),
        byte_size=src.get("byte_size"),
    )

    books: list[JfbBookEntry] = []
    seen_div2_ids: set[str] = set()
    seen_orders: set[int] = set()
    for item in raw.get("books") or []:
        div2_id = str(item["div2_id"])
        if div2_id in seen_div2_ids:
            raise JfbSourceFetchError(f"Duplicate div2_id in JFB manifest: {div2_id!r}")
        seen_div2_ids.add(div2_id)
        order = int(item["order"])
        if order in seen_orders:
            raise JfbSourceFetchError(f"Duplicate order in JFB manifest: {order!r}")
        seen_orders.add(order)
        books.append(
            JfbBookEntry(
                order=order,
                div2_id=div2_id,
                title=str(item["title"]),
                testament=str(item["testament"]),
                contributor_raw_name=str(item["contributor_raw_name"]),
                coverage=str(item.get("coverage") or item["title"]),
            )
        )
    books.sort(key=lambda b: b.order)

    return JfbSourceManifest(
        manifest_version=str(raw.get("manifest_version") or ""),
        description=str(raw.get("description") or ""),
        source=source,
        books=tuple(books),
    )


def fetch_source(source: JfbSourceFile, *, force: bool = False) -> JfbSourceFetchResult:
    """Ensure ``source.local_path`` holds bytes matching ``source.raw_sha256``.

    If the file already exists and matches, no network call is made. If it
    exists but does NOT match, this is a fail-closed error (never silently
    overwritten) unless ``force=True``.
    """
    if source.local_path.is_file() and not force:
        existing_hash = _sha256_file(source.local_path)
        if existing_hash == source.raw_sha256:
            return JfbSourceFetchResult(
                id=source.id,
                local_path=source.local_path,
                raw_sha256=existing_hash,
                byte_size=source.local_path.stat().st_size,
                already_present=True,
            )
        raise JfbSourceFetchError(
            f"{source.id}: local file {source.local_path} exists but its SHA-256 "
            f"({existing_hash}) does not match the manifest "
            f"({source.raw_sha256}). Pass force=True to re-download."
        )

    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed https CCEL URL from the pinned manifest
            source.url, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            data = response.read()
    except OSError as exc:
        raise JfbSourceFetchError(f"{source.id}: download failed: {exc}") from exc

    digest = hashlib.sha256(data).hexdigest()
    if digest != source.raw_sha256:
        raise JfbSourceFetchError(
            f"{source.id}: downloaded SHA-256 ({digest}) does not match the "
            f"manifest ({source.raw_sha256}); refusing to write {source.local_path}."
        )

    source.local_path.parent.mkdir(parents=True, exist_ok=True)
    source.local_path.write_bytes(data)
    return JfbSourceFetchResult(
        id=source.id,
        local_path=source.local_path,
        raw_sha256=digest,
        byte_size=len(data),
        already_present=False,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "JfbBookEntry",
    "JfbSourceFetchError",
    "JfbSourceFetchResult",
    "JfbSourceFile",
    "JfbSourceManifest",
    "fetch_source",
    "load_source_manifest",
]
