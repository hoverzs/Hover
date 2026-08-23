"""Path helpers for the isolated Knowledge Base package."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_MANIFEST_PATH = PACKAGE_ROOT / "data" / "kb_manifest.json"
GENERATED_DATA_DIR = PROJECT_ROOT / "data" / "generated"
BIBLICAL_PLACES_DIR = PROJECT_ROOT / "data" / "biblical_places"


def resolve_project_path(relative: str) -> Path:
    normalized = relative.replace("\\", "/")
    return PROJECT_ROOT.joinpath(*[part for part in normalized.split("/") if part])


def normalize_repo_relative_path(relative: str) -> str:
    """Repository-relative POSIX path for portable health/manifest reporting."""
    return relative.replace("\\", "/").lstrip("/")
