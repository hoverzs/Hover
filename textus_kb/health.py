"""Read-only Knowledge Base health check."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.acai_entities import ACAI_SOURCE_ID
from textus_kb.manifest import (
    KnowledgeBaseManifest,
    ManifestValidationError,
    ManifestValidationIssue,
    load_manifest,
    validate_manifest_sources,
)
from textus_kb.paths import DEFAULT_MANIFEST_PATH, normalize_repo_relative_path
from textus_kb.pilot_registry import PILOTS, validate_pilot_registry

CANONICAL_SELF_TEST_GROUPS: tuple[tuple[str, ...], ...] = (
    (
        "Jn 4,1–42",
        "JHN 4:1-42",
        "John.4.1-42",
    ),
    (
        "Lk 10,25–37",
        "Luke.10.25-37",
    ),
)

# Backward-compatible flat tuple for callers that iterate all inputs.
CANONICAL_SELF_TEST_INPUTS = tuple(
    text for group in CANONICAL_SELF_TEST_GROUPS for text in group
)


@dataclass
class SourceHealthReport:
    id: str
    enabled: bool
    required: bool
    available: bool
    version: str
    license: str
    path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CanonicalSelfTestResult:
    input: str
    canonical: str | None
    ok: bool
    error: str | None = None


@dataclass
class AcaiStoreHealthReport:
    store_available: bool
    schema_version: str
    source_version: str
    entity_count: int
    passage_link_count: int
    dictionary_link_count: int
    content_hash: str
    import_mode: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PilotBundleHealthReport:
    pilot_id: str
    canonical: str
    study_notes_available: bool
    dictionary_available: bool
    acai_json_available: bool
    study_notes_path: str
    dictionary_path: str
    acai_json_path: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class PilotRegistryHealthReport:
    valid: bool
    pilot_count: int
    pilots: list[PilotBundleHealthReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeBaseHealthReport:
    overall_status: str  # ok | degraded | error
    manifest_status: str  # ok | error
    manifest_path: str
    manifest_version: str
    sources: list[SourceHealthReport]
    canonical_self_tests: list[CanonicalSelfTestResult]
    acai_store: AcaiStoreHealthReport | None = None
    pilot_registry: PilotRegistryHealthReport | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_canonical_self_tests(
    groups: tuple[tuple[str, ...], ...] = CANONICAL_SELF_TEST_GROUPS,
) -> list[CanonicalSelfTestResult]:
    results: list[CanonicalSelfTestResult] = []
    for group_index, group in enumerate(groups):
        canonical_strings: list[str] = []
        for text in group:
            try:
                ref = CanonicalReference.parse(text)
                canonical = ref.canonical_string()
                results.append(
                    CanonicalSelfTestResult(input=text, canonical=canonical, ok=True)
                )
                canonical_strings.append(canonical)
            except CanonicalReferenceError as exc:
                results.append(
                    CanonicalSelfTestResult(
                        input=text,
                        canonical=None,
                        ok=False,
                        error=str(exc),
                    )
                )
        consistency_key = f"__cross_input_consistency__:{group_index}"
        if len(set(canonical_strings)) > 1 and canonical_strings:
            results.append(
                CanonicalSelfTestResult(
                    input=consistency_key,
                    canonical=canonical_strings[0] if canonical_strings else None,
                    ok=False,
                    error="Self-test inputs did not normalize to the same canonical string.",
                )
            )
        elif len(canonical_strings) >= 2:
            results.append(
                CanonicalSelfTestResult(
                    input=consistency_key,
                    canonical=canonical_strings[0],
                    ok=True,
                )
            )
    return results


def run_health_check(
    manifest_path: str | Path | None = None,
    *,
    check_paths: bool = True,
) -> KnowledgeBaseHealthReport:
    path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST_PATH
    errors: list[str] = []
    warnings: list[str] = []
    manifest_status = "ok"
    sources_reports: list[SourceHealthReport] = []
    manifest_version = ""

    try:
        manifest = load_manifest(path)
        manifest_version = manifest.manifest_version
        validation_issues = validate_manifest_sources(manifest, check_paths=check_paths)
    except ManifestValidationError as exc:
        manifest = None
        manifest_status = "error"
        errors.append(str(exc))
        validation_issues = []

    for issue in validation_issues:
        target = errors if issue.level == "error" else warnings
        prefix = f"[{issue.source_id}] " if issue.source_id else ""
        target.append(f"{prefix}{issue.message}")

    if manifest is not None:
        for source in manifest.sources:
            if source.enabled:
                available = source.resolved_path.is_file()
            else:
                # Disabled sources are not probed on disk (contractual isolation).
                available = False
            report = SourceHealthReport(
                id=source.id,
                enabled=source.enabled,
                required=source.required,
                available=available,
                version=source.version,
                license=source.license,
                path=normalize_repo_relative_path(source.local_path),
            )
            if source.enabled and source.required and not available:
                report.errors.append("Required enabled source file is missing.")
            elif source.enabled and not source.required and not available:
                report.warnings.append("Optional enabled source file is missing.")
            if source.restricted and source.enabled:
                report.warnings.append(
                    "Restricted contractual source — internal use only."
                )
            sources_reports.append(report)

    acai_store_report = _acai_store_health(manifest, check_paths=check_paths)
    pilot_registry_report = _pilot_registry_health(check_paths=check_paths)
    if pilot_registry_report.errors:
        errors.extend(pilot_registry_report.errors)
    if pilot_registry_report.warnings:
        warnings.extend(pilot_registry_report.warnings)

    canonical_tests = run_canonical_self_tests()
    if any(not item.ok for item in canonical_tests):
        errors.append("Canonical reference self-test failed.")

    if manifest_status == "error" or errors:
        overall = "error"
    elif warnings or any(r.warnings for r in sources_reports):
        overall = "degraded"
    elif acai_store_report is not None and acai_store_report.warnings:
        overall = "degraded"
    elif pilot_registry_report.warnings:
        overall = "degraded"
    else:
        overall = "ok"

    return KnowledgeBaseHealthReport(
        overall_status=overall,
        manifest_status=manifest_status,
        manifest_path=str(path),
        manifest_version=manifest_version,
        sources=sources_reports,
        canonical_self_tests=canonical_tests,
        acai_store=acai_store_report,
        pilot_registry=pilot_registry_report,
        errors=errors,
        warnings=warnings,
    )


def _pilot_registry_health(*, check_paths: bool) -> PilotRegistryHealthReport:
    registry_errors = validate_pilot_registry()
    pilots: list[PilotBundleHealthReport] = []
    warnings: list[str] = []
    for pilot in PILOTS:
        study_ok = pilot.study_notes_resolved.is_file() if check_paths else True
        dict_ok = pilot.dictionary_resolved.is_file() if check_paths else True
        acai_ok = pilot.acai_json_resolved.is_file() if check_paths else True
        pilot_warnings: list[str] = []
        if check_paths and not study_ok:
            pilot_warnings.append(f"Study Notes bundle missing: {pilot.study_notes_path}")
        if check_paths and not dict_ok:
            pilot_warnings.append(f"Dictionary bundle missing: {pilot.dictionary_path}")
        if check_paths and not acai_ok:
            pilot_warnings.append(f"ACAI JSON bundle missing: {pilot.acai_json_path}")
        warnings.extend(f"[{pilot.id}] {msg}" for msg in pilot_warnings)
        pilots.append(
            PilotBundleHealthReport(
                pilot_id=pilot.id,
                canonical=pilot.canonical,
                study_notes_available=study_ok,
                dictionary_available=dict_ok,
                acai_json_available=acai_ok,
                study_notes_path=normalize_repo_relative_path(pilot.study_notes_path),
                dictionary_path=normalize_repo_relative_path(pilot.dictionary_path),
                acai_json_path=normalize_repo_relative_path(pilot.acai_json_path),
                warnings=pilot_warnings,
            )
        )
    return PilotRegistryHealthReport(
        valid=not registry_errors,
        pilot_count=len(PILOTS),
        pilots=pilots,
        errors=registry_errors,
        warnings=warnings,
    )


def _acai_store_health(
    manifest: KnowledgeBaseManifest | None,
    *,
    check_paths: bool,
) -> AcaiStoreHealthReport | None:
    if manifest is None:
        return None
    source = manifest.source_by_id(ACAI_SOURCE_ID)
    if source is None:
        return None
    if not source.enabled:
        return AcaiStoreHealthReport(
            store_available=False,
            schema_version="",
            source_version=source.version,
            entity_count=0,
            passage_link_count=0,
            dictionary_link_count=0,
            content_hash="",
            import_mode="",
            warnings=["ACAI source disabled in manifest."],
        )
    path = source.resolved_path
    if check_paths and not path.is_file():
        return AcaiStoreHealthReport(
            store_available=False,
            schema_version="",
            source_version=source.version,
            entity_count=0,
            passage_link_count=0,
            dictionary_link_count=0,
            content_hash="",
            import_mode="",
            warnings=["Optional ACAI entity store file is missing."],
        )
    if path.suffix.lower() not in {".sqlite3", ".db", ".sqlite"}:
        return None
    from textus_kb.repositories.acai_entity_repository import AcaiEntityRepository

    status = AcaiEntityRepository(path).store_status()
    warnings = list(status.warnings)
    if status.available and status.entity_count == 0:
        warnings.append("ACAI store is available but contains zero entities.")
    return AcaiStoreHealthReport(
        store_available=status.available,
        schema_version=status.schema_version,
        source_version=status.source_version,
        entity_count=status.entity_count,
        passage_link_count=status.passage_link_count,
        dictionary_link_count=status.dictionary_link_count,
        content_hash=status.content_hash,
        import_mode=status.import_mode,
        warnings=warnings,
    )


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    manifest_arg = DEFAULT_MANIFEST_PATH
    skip_paths = False
    i = 0
    while i < len(args):
        if args[i] in {"--manifest", "-m"} and i + 1 < len(args):
            manifest_arg = Path(args[i + 1])
            i += 2
            continue
        if args[i] == "--no-path-check":
            skip_paths = True
            i += 1
            continue
        i += 1

    report = run_health_check(manifest_arg, check_paths=not skip_paths)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.overall_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
