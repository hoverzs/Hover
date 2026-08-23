"""TEXTUS Knowledge Base — isolated core (Phase 1 foundation + Phase 2A pilot)."""

from textus_kb.context_builder import (
    LLMContextPacket,
    build_context,
    build_context_from_evidence,
    build_context_to_json,
)
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
    "LLMContextPacket",
    "RetrievalError",
    "build_context",
    "build_context_from_evidence",
    "build_context_to_json",
    "load_manifest",
    "retrieve",
    "retrieve_to_json",
    "run_health_check",
]

__version__ = "0.3.0"
