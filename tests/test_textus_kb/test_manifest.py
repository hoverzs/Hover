"""Tests for Knowledge Base manifest loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textus_kb.manifest import ManifestValidationError, load_manifest, validate_manifest_sources


def _write_manifest(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "kb_manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _minimal_source(**overrides: object) -> dict:
    base = {
        "id": "sample",
        "name": "Sample",
        "source_type": "json",
        "language": "en",
        "version": "1",
        "license": "MIT",
        "license_url": "https://opensource.org/licenses/MIT",
        "local_path": "README.md",
        "required": False,
        "enabled": True,
    }
    base.update(overrides)
    return base


def test_load_default_manifest() -> None:
    manifest = load_manifest()
    assert manifest.manifest_version == "1"
    assert len(manifest.sources) >= 5
    tagnt = manifest.source_by_id("stepbible_tagnt")
    assert tagnt is not None
    assert tagnt.license == "CC-BY-4.0"


def test_duplicate_source_id_rejected(tmp_path: Path) -> None:
    payload = {
        "manifest_version": "1",
        "sources": [
            _minimal_source(id="dup"),
            _minimal_source(id="dup"),
        ],
    }
    path = _write_manifest(tmp_path, payload)
    with pytest.raises(ManifestValidationError, match="Duplicate"):
        load_manifest(path)


def test_missing_required_field_rejected(tmp_path: Path) -> None:
    bad = _minimal_source()
    del bad["license"]
    path = _write_manifest(
        tmp_path,
        {"manifest_version": "1", "sources": [bad]},
    )
    with pytest.raises(ManifestValidationError, match="missing required"):
        load_manifest(path)


def test_unsupported_license_rejected(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "manifest_version": "1",
            "sources": [_minimal_source(license="GPL-3.0")],
        },
    )
    with pytest.raises(ManifestValidationError, match="Unsupported license"):
        load_manifest(path)


def test_ruf_source_marked_restricted_in_default_manifest() -> None:
    manifest = load_manifest()
    ruf = manifest.source_by_id("ruf_2014_local")
    assert ruf is not None
    assert ruf.license == "contractual-restricted"
    assert ruf.restricted is True
    assert ruf.enabled is False


def test_validate_required_missing_path(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "manifest_version": "1",
            "sources": [
                _minimal_source(
                    id="missing",
                    local_path="data/generated/does_not_exist.sqlite3",
                    required=True,
                )
            ],
        },
    )
    manifest = load_manifest(path)
    issues = validate_manifest_sources(manifest, check_paths=True)
    assert any(i.level == "error" and "missing" in i.message.lower() for i in issues)


def test_validate_optional_missing_path_warning(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "manifest_version": "1",
            "sources": [
                _minimal_source(
                    id="optional",
                    local_path="data/generated/optional_missing.sqlite3",
                    required=False,
                )
            ],
        },
    )
    manifest = load_manifest(path)
    issues = validate_manifest_sources(manifest, check_paths=True)
    assert any(i.level == "warning" for i in issues)


def test_restricted_required_enabled_invalid(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "manifest_version": "1",
            "sources": [
                _minimal_source(
                    id="bad_ruf",
                    license="contractual-restricted",
                    restricted=True,
                    required=True,
                    enabled=True,
                    local_path="README.md",
                )
            ],
        },
    )
    manifest = load_manifest(path)
    issues = validate_manifest_sources(manifest, check_paths=False)
    assert any("Restricted source cannot" in i.message for i in issues)
