"""Internal citation policy and CitationRef model (Phase 5F).

No user-facing UI. Builds citation-ready metadata from Evidence / Context items
and the KB manifest. Does not bind model sentences to evidence via LLM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from textus_kb.context_builder import LLMContextPacket
from textus_kb.evidence import EvidencePacket
from textus_kb.manifest import KnowledgeBaseManifest, load_manifest
from textus_kb.prompt_composer import packet_from_mapping

# Human-readable registry (fallback when manifest name missing).
CITATION_DISPLAY_NAMES: dict[str, str] = {
    "stepbible_tagnt": "STEPBible TAGNT (Greek NT morphology)",
    "stepbible_tbesg": "STEPBible TBESG (Greek lexicon)",
    "stepbible_tahot": "STEPBible TAHOT (Hebrew OT morphology)",
    "stepbible_tbesh": "STEPBible TBESH (Hebrew lexicon)",
    "lexicon_hu_overlay": "Hungarian lexicon overlay",
    "aquifer_open_study_notes": "Aquifer Open Study Notes",
    "aquifer_open_bible_dictionary": "Aquifer Open Bible Dictionary",
    "acai": "ACAI Biblical Entities",
    "biblical_places_passage_links": "Biblical places (passage links)",
    "place_enrichments_overlay": "Biblical places enrichments",
}

CITABLE_RELATION_TYPES = frozenset(
    {
        "lexical_highlight",
        "passage_token",
        "exegetical_note",
        "dictionary_background",
        "passage_place_link",
        "place_catalog",
        "place_enrichment",
    }
)

NON_CITABLE_HINTS = (
    "model editorial / synthesizing sentence",
    "general transition sentence",
    "plain biblical paraphrase without external background claim",
)


@dataclass(frozen=True)
class CitationRef:
    citation_id: str
    source_id: str
    evidence_id: str
    source_type: str
    title: str
    article_or_chunk_id: str = ""
    canonical_scope: str = ""
    license: str = ""
    license_url: str = ""
    attribution: str = ""
    upstream_url: str = ""
    upstream_version: str = ""
    restricted: bool = False
    citation_ready: bool = False
    missing_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CitationCoverageReport:
    selected_evidence_count: int = 0
    citation_ready_count: int = 0
    incomplete_count: int = 0
    by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    citations: list[CitationRef] = field(default_factory=list)
    policy_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_evidence_count": self.selected_evidence_count,
            "citation_ready_count": self.citation_ready_count,
            "incomplete_count": self.incomplete_count,
            "by_source": dict(self.by_source),
            "citations": [c.to_dict() for c in self.citations],
            "policy_notes": list(self.policy_notes),
        }


def display_name_for_source(source_id: str, manifest: KnowledgeBaseManifest | None = None) -> str:
    if manifest is not None:
        src = manifest.source_by_id(source_id)
        if src is not None and src.name:
            return src.name
    return CITATION_DISPLAY_NAMES.get(source_id, source_id)


def citation_policy_document() -> dict[str, Any]:
    """Static policy answers for later user-facing citation design."""
    return {
        "version": "1",
        "cite_when": [
            "concrete linguistic / lexical claims from TAGNT/TBESG/lexicon",
            "historical or cultural background from Study Notes / dictionary / places",
            "dictionary background used as a factual claim",
            "Study Notes–based concrete assertions",
            "ACAI entity facts used as grounding",
        ],
        "do_not_require_separate_citation_for": list(NON_CITABLE_HINTS),
        "user_facing_rule": (
            "Do not dump internal EV-* IDs to end users. Resolve via CitationRef "
            "display title + license/attribution."
        ),
        "ruf_policy": (
            "RÚF Bible text remains contractual-restricted and separate from KB "
            "source licenses. Never mix RÚF license with Aquifer/STEPBible/ACAI."
        ),
        "cc_by_sa": (
            "CC BY-SA sources must retain license, license_url, and attribution "
            "on every CitationRef."
        ),
    }


def _meta_get(meta: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = meta.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def build_citation_ref(
    *,
    evidence_id: str,
    source_id: str,
    source_type: str = "",
    metadata: dict[str, Any] | None = None,
    manifest: KnowledgeBaseManifest | None = None,
    relation_type: str = "",
) -> CitationRef:
    meta = dict(metadata or {})
    mf = manifest or load_manifest()
    src = mf.source_by_id(source_id)
    title = display_name_for_source(source_id, mf)
    heading = _meta_get(meta, "heading", "title", "lemma")
    if heading:
        title = f"{title}: {heading}"

    license_value = _meta_get(meta, "license") or (src.license if src else "")
    license_url = _meta_get(meta, "license_url") or (src.license_url or "" if src else "")
    attribution = _meta_get(meta, "attribution") or (src.usage_note or "" if src else "")
    article = _meta_get(meta, "article_id", "chunk_id", "strong_id", "entity_id", "place_id")
    scope = _meta_get(meta, "canonical_scope", "passage", "index_reference")
    upstream_url = _meta_get(meta, "upstream_url", "source_url")
    upstream_version = _meta_get(
        meta, "upstream_resource_version", "upstream_commit", "version"
    ) or (src.version if src else "")
    restricted = bool(src.restricted) if src else license_value == "contractual-restricted"

    missing: list[str] = []
    if not source_id:
        missing.append("source_id")
    if not evidence_id:
        missing.append("evidence_id")
    if not license_value:
        missing.append("license")
    if license_value.upper().startswith("CC-BY") and not attribution and not license_url:
        missing.append("attribution_or_license_url")
    if relation_type and relation_type not in CITABLE_RELATION_TYPES and relation_type != "passage":
        # Still build ref, but mark incomplete for non-citable relation unless passage.
        pass

    citation_ready = not missing and bool(source_id and evidence_id and license_value)
    return CitationRef(
        citation_id=f"cite:{source_id}:{evidence_id}",
        source_id=source_id,
        evidence_id=evidence_id,
        source_type=source_type or (src.source_type if src else ""),
        title=title,
        article_or_chunk_id=article,
        canonical_scope=scope,
        license=license_value,
        license_url=license_url or "",
        attribution=attribution,
        upstream_url=upstream_url,
        upstream_version=upstream_version,
        restricted=restricted,
        citation_ready=citation_ready,
        missing_fields=tuple(missing),
    )


def citations_from_evidence_packet(
    packet: EvidencePacket,
    *,
    manifest: KnowledgeBaseManifest | None = None,
) -> CitationCoverageReport:
    mf = manifest or load_manifest()
    report = CitationCoverageReport(
        policy_notes=[
            "Coverage is source-metadata readiness, not sentence-level grounding.",
            citation_policy_document()["ruf_policy"],
        ]
    )
    for item in packet.evidence_items:
        if item.relation_type == "direct_passage_match":
            continue
        ref = build_citation_ref(
            evidence_id=item.evidence_id,
            source_id=item.source_id,
            source_type=item.source_type,
            metadata=item.metadata,
            manifest=mf,
            relation_type=item.relation_type,
        )
        report.citations.append(ref)
        report.selected_evidence_count += 1
        bucket = report.by_source.setdefault(
            item.source_id, {"total": 0, "ready": 0, "incomplete": 0}
        )
        bucket["total"] += 1
        if ref.citation_ready:
            report.citation_ready_count += 1
            bucket["ready"] += 1
        else:
            report.incomplete_count += 1
            bucket["incomplete"] += 1
    return report


def citations_from_context_packet(
    packet: LLMContextPacket | dict[str, Any],
    *,
    manifest: KnowledgeBaseManifest | None = None,
) -> CitationCoverageReport:
    """Diagnostic coverage for selected context items (post Context Builder)."""
    mf = manifest or load_manifest()
    ctx = packet_from_mapping(packet) if isinstance(packet, dict) else packet
    report = CitationCoverageReport(
        policy_notes=[
            "Selected context citation readiness (no LLM sentence linking).",
            citation_policy_document()["user_facing_rule"],
        ]
    )
    for section in ctx.sections:
        for item in section.items:
            if item.item_type in {"passage", "passage_summary", "passage_scope"}:
                continue
            ref = build_citation_ref(
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                source_type=item.item_type,
                metadata=item.metadata,
                manifest=mf,
                relation_type=item.item_type,
            )
            report.citations.append(ref)
            report.selected_evidence_count += 1
            bucket = report.by_source.setdefault(
                item.source_id, {"total": 0, "ready": 0, "incomplete": 0}
            )
            bucket["total"] += 1
            if ref.citation_ready:
                report.citation_ready_count += 1
                bucket["ready"] += 1
            else:
                report.incomplete_count += 1
                bucket["incomplete"] += 1
    return report


__all__ = [
    "CITABLE_RELATION_TYPES",
    "CITATION_DISPLAY_NAMES",
    "CitationCoverageReport",
    "CitationRef",
    "build_citation_ref",
    "citation_policy_document",
    "citations_from_context_packet",
    "citations_from_evidence_packet",
    "display_name_for_source",
]
