"""TEXTUS Knowledge Base — isolated core (Phase 1 foundation + Phase 2A pilot)."""

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.evidence import EvidenceItem, EvidencePacket
from textus_kb.health import KnowledgeBaseHealthReport, run_health_check
from textus_kb.manifest import KnowledgeBaseManifest, load_manifest
from textus_kb.retrieval import RetrievalError, retrieve, retrieve_to_json

__all__ = [
    "CanonicalReference",
    "CanonicalReferenceError",
    "EvidenceItem",
    "EvidencePacket",
    "KnowledgeBaseHealthReport",
    "KnowledgeBaseManifest",
    "RetrievalError",
    "load_manifest",
    "retrieve",
    "retrieve_to_json",
    "run_health_check",
]

__version__ = "0.2.0"
