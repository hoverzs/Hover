from __future__ import annotations

from bible_engine.paths import GENERATED_DATA_DIR, PROJECT_ROOT


DATA_DIR = PROJECT_ROOT / "data" / "illustrations"
SOURCE_REGISTRY_PATH = DATA_DIR / "sources.json"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "illustrations"

__all__ = [
    "PROJECT_ROOT",
    "GENERATED_DATA_DIR",
    "DATA_DIR",
    "SOURCE_REGISTRY_PATH",
    "RAW_DATA_DIR",
]
