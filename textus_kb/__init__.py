"""TEXTUS Knowledge Base — isolated core foundation (Phase 1)."""

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.health import KnowledgeBaseHealthReport, run_health_check
from textus_kb.manifest import KnowledgeBaseManifest, load_manifest

__all__ = [
    "CanonicalReference",
    "CanonicalReferenceError",
    "KnowledgeBaseHealthReport",
    "KnowledgeBaseManifest",
    "load_manifest",
    "run_health_check",
]

__version__ = "0.1.0"
