"""Read-only Knowledge Base manifest loader and validator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from textus_kb.paths import DEFAULT_MANIFEST_PATH, resolve_project_path

SUPPORTED_LICENSES = frozenset(
    {
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "CC-BY-3.0",
        "MIT",
        "contractual-restricted",
        "reference-only",
        "unknown",
    }
)

REQUIRED_SOURCE_FIELDS = frozenset(
    {
        "id",
        "name",
        "source_type",
        "language",
        "version",
        "license",
        "local_path",
        "required",
        "enabled",
    }
)


class ManifestValidationError(ValueError):
    """Raised when manifest JSON fails structural validation."""


@dataclass(frozen=True)
class ManifestSource:
    id: str
    name: str
    source_type: str
    language: str
    version: str
    license: str
    license_url: str | None
    local_path: str
    required: bool
    enabled: bool
    restricted: bool = False
    usage_note: str | None = None

    @property
    def resolved_path(self) -> Path:
        return resolve_project_path(self.local_path)


@dataclass
class ManifestValidationIssue:
    level: str  # error | warning
    message: str
    source_id: str | None = None


@dataclass
class KnowledgeBaseManifest:
    manifest_version: str
    sources: tuple[ManifestSource, ...]
    description: str = ""
    generated_at: str = ""
    path: Path = field(default_factory=lambda: DEFAULT_MANIFEST_PATH)

    def source_by_id(self, source_id: str) -> ManifestSource | None:
        for source in self.sources:
            if source.id == source_id:
                return source
        return None


def load_manifest(path: str | Path | None = None) -> KnowledgeBaseManifest:
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestValidationError(f"Cannot read manifest: {manifest_path}") from exc

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"Invalid manifest JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestValidationError("Manifest root must be a JSON object.")

    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise ManifestValidationError("Manifest must contain a non-empty 'sources' array.")

    sources: list[ManifestSource] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(sources_raw):
        if not isinstance(item, dict):
            raise ManifestValidationError(f"Source entry #{index} must be an object.")
        missing = REQUIRED_SOURCE_FIELDS - item.keys()
        if missing:
            raise ManifestValidationError(
                f"Source entry #{index} missing required fields: {sorted(missing)}"
            )
        source_id = str(item["id"]).strip()
        if not source_id:
            raise ManifestValidationError(f"Source entry #{index} has empty id.")
        if source_id in seen_ids:
            raise ManifestValidationError(f"Duplicate source id: {source_id!r}")
        seen_ids.add(source_id)

        license_value = str(item["license"]).strip()
        if license_value not in SUPPORTED_LICENSES:
            raise ManifestValidationError(
                f"Unsupported license for {source_id!r}: {license_value!r}"
            )

        license_url = item.get("license_url")
        if license_url is not None and not isinstance(license_url, str):
            raise ManifestValidationError(f"license_url must be string or null for {source_id!r}")

        sources.append(
            ManifestSource(
                id=source_id,
                name=str(item["name"]),
                source_type=str(item["source_type"]),
                language=str(item["language"]),
                version=str(item["version"]),
                license=license_value,
                license_url=license_url,
                local_path=str(item["local_path"]),
                required=bool(item["required"]),
                enabled=bool(item["enabled"]),
                restricted=bool(item.get("restricted", False)),
                usage_note=(
                    str(item["usage_note"]) if item.get("usage_note") is not None else None
                ),
            )
        )

    return KnowledgeBaseManifest(
        manifest_version=str(raw.get("manifest_version", "")),
        description=str(raw.get("description", "")),
        generated_at=str(raw.get("generated_at", "")),
        sources=tuple(sources),
        path=manifest_path,
    )


def validate_manifest_sources(
    manifest: KnowledgeBaseManifest,
    *,
    check_paths: bool = True,
) -> list[ManifestValidationIssue]:
    """Validate manifest semantics without mutating data."""
    issues: list[ManifestValidationIssue] = []

    if not manifest.manifest_version:
        issues.append(
            ManifestValidationIssue("warning", "manifest_version is empty.")
        )

    for source in manifest.sources:
        if source.restricted and source.enabled and source.required:
            issues.append(
                ManifestValidationIssue(
                    "error",
                    "Restricted source cannot be both enabled and required.",
                    source_id=source.id,
                )
            )
        if source.license == "contractual-restricted" and not source.restricted:
            issues.append(
                ManifestValidationIssue(
                    "warning",
                    "Contractual license should set restricted=true.",
                    source_id=source.id,
                )
            )
        if check_paths and source.enabled and source.local_path:
            path = source.resolved_path
            if source.required and not path.is_file():
                issues.append(
                    ManifestValidationIssue(
                        "error",
                        f"Required source file missing: {path}",
                        source_id=source.id,
                    )
                )
            elif not source.required and not path.is_file():
                issues.append(
                    ManifestValidationIssue(
                        "warning",
                        f"Optional source file missing: {path}",
                        source_id=source.id,
                    )
                )

    return issues
