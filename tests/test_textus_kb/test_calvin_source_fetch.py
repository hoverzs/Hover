"""Calvin source manifest + fetch verification tests (no real network I/O).

Uses local ``file://`` URLs so the SHA-256 verify/reject logic is tested
deterministically without depending on ccel.org being reachable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from textus_kb.importers.calvin_source_fetch import (
    CalvinSourceEntry,
    CalvinSourceFetchError,
    fetch_source,
    load_source_manifest,
)


def test_default_manifest_loads_with_two_pilot_sources() -> None:
    entries = load_source_manifest()
    ids = {entry.id for entry in entries}
    assert {"calcom38", "calcom31"} <= ids
    for entry in entries:
        assert len(entry.raw_sha256) == 64
        assert entry.url.startswith("https://www.ccel.org/")


def test_fetch_source_downloads_and_verifies(tmp_path: Path) -> None:
    payload = b"synthetic calvin source fetch test payload"
    source_path = tmp_path / "source.xml"
    source_path.write_bytes(payload)
    target_path = tmp_path / "downloaded" / "source.xml"
    entry = CalvinSourceEntry(
        id="test",
        title="Test",
        url=source_path.as_uri(),
        local_path=target_path,
        raw_sha256=hashlib.sha256(payload).hexdigest(),
    )
    result = fetch_source(entry)
    assert result.already_present is False
    assert target_path.read_bytes() == payload
    assert result.raw_sha256 == entry.raw_sha256


def test_fetch_source_rejects_checksum_mismatch(tmp_path: Path) -> None:
    payload = b"unexpected bytes"
    source_path = tmp_path / "source.xml"
    source_path.write_bytes(payload)
    target_path = tmp_path / "downloaded" / "source.xml"
    entry = CalvinSourceEntry(
        id="test",
        title="Test",
        url=source_path.as_uri(),
        local_path=target_path,
        raw_sha256="0" * 64,
    )
    with pytest.raises(CalvinSourceFetchError, match="does not match"):
        fetch_source(entry)
    assert not target_path.exists()


def test_fetch_source_reuses_existing_matching_file_without_network(tmp_path: Path) -> None:
    payload = b"already downloaded"
    target_path = tmp_path / "source.xml"
    target_path.write_bytes(payload)
    entry = CalvinSourceEntry(
        id="test",
        title="Test",
        url="https://example.invalid/should-not-be-fetched.xml",
        local_path=target_path,
        raw_sha256=hashlib.sha256(payload).hexdigest(),
    )
    result = fetch_source(entry)
    assert result.already_present is True


def test_fetch_source_rejects_stale_local_file_without_force(tmp_path: Path) -> None:
    target_path = tmp_path / "source.xml"
    target_path.write_bytes(b"stale content")
    entry = CalvinSourceEntry(
        id="test",
        title="Test",
        url="https://example.invalid/should-not-be-fetched.xml",
        local_path=target_path,
        raw_sha256=hashlib.sha256(b"expected content").hexdigest(),
    )
    with pytest.raises(CalvinSourceFetchError, match="does not match"):
        fetch_source(entry)
