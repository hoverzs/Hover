"""Read-only adapter for Aquifer Open Study Notes pilot bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.importers.aquifer_study_notes import (
    AQUIFER_ATTRIBUTION,
    AQUIFER_LICENSE,
    AQUIFER_LICENSE_URL,
    AQUIFER_SOURCE_ID,
    html_to_plain,
    load_pilot_bundle,
)
from textus_kb.manifest import ManifestSource
from textus_kb.pilot_registry import PILOTS, find_pilot, references_overlap


@dataclass(frozen=True)
class AquiferNoteChunk:
    article_id: str
    chunk_id: str
    chunk_index: int
    title: str
    canonical_reference: str
    upstream_reference_usfm: str | None
    content_html: str
    content_plain: str
    license: str
    license_url: str
    attribution: str


class AquiferStudyNotesAdapter:
    SOURCE_ID = AQUIFER_SOURCE_ID

    def __init__(self, source: ManifestSource | None) -> None:
        self._source = source
        self._bundles: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        if self._source is None or not self._source.enabled:
            return False
        if any(pilot.study_notes_resolved.is_file() for pilot in PILOTS):
            return True
        return self._source.resolved_path.is_file()

    def pilot_bundle_available(self, reference: CanonicalReference) -> bool:
        if not self.available:
            return False
        pilot = find_pilot(reference)
        if pilot is None:
            return False
        return pilot.study_notes_resolved.is_file()

    def load_chunks_for_passage(self, reference: CanonicalReference) -> list[AquiferNoteChunk]:
        if not self.available:
            return []
        pilot = find_pilot(reference)
        if pilot is None:
            return []
        bundle = self._load_bundle_for_pilot(pilot.id)
        if not bundle:
            return []
        chunks: list[AquiferNoteChunk] = []
        for note in bundle.get("notes", []):
            if not isinstance(note, dict):
                continue
            canonical = str(note.get("canonical_reference") or "")
            if not canonical:
                continue
            try:
                note_ref = CanonicalReference.parse(canonical)
            except Exception:
                continue
            if not references_overlap(reference, note_ref):
                continue
            for chunk in note.get("chunks", []):
                if not isinstance(chunk, dict):
                    continue
                chunks.append(
                    AquiferNoteChunk(
                        article_id=str(note.get("article_id") or ""),
                        chunk_id=str(chunk.get("chunk_id") or ""),
                        chunk_index=int(chunk.get("chunk_index") or 0),
                        title=str(note.get("title") or ""),
                        canonical_reference=canonical,
                        upstream_reference_usfm=note.get("upstream_reference_usfm"),
                        content_html=str(chunk.get("content_html") or ""),
                        content_plain=str(
                            chunk.get("content_plain")
                            or html_to_plain(str(chunk.get("content_html") or ""))
                        ),
                        license=str(note.get("license") or AQUIFER_LICENSE),
                        license_url=str(note.get("license_url") or AQUIFER_LICENSE_URL),
                        attribution=str(note.get("attribution") or AQUIFER_ATTRIBUTION),
                    )
                )
        chunks.sort(key=lambda item: (item.canonical_reference, item.article_id, item.chunk_index))
        return chunks

    def bundle_metadata(self, reference: CanonicalReference | None = None) -> dict[str, Any]:
        if not self.available:
            return {}
        pilot = find_pilot(reference) if reference is not None else None
        if pilot is not None:
            bundle = self._load_bundle_for_pilot(pilot.id)
        else:
            path = self._source.resolved_path if self._source else Path()
            if not path.is_file():
                return {}
            bundle = load_pilot_bundle(path)
        if not bundle:
            return {}
        return {
            "source_id": AQUIFER_SOURCE_ID,
            "upstream_repository": bundle.get("upstream_repository"),
            "upstream_commit": bundle.get("upstream_commit"),
            "upstream_resource_version": bundle.get("upstream_resource_version"),
            "license": bundle.get("license"),
            "license_url": bundle.get("license_url"),
            "attribution": bundle.get("attribution"),
            "pilot_id": bundle.get("pilot_id"),
            "pilot_scope": bundle.get("pilot_scope"),
        }

    def _load_bundle_for_pilot(self, pilot_id: str) -> dict[str, Any]:
        if pilot_id in self._bundles:
            return self._bundles[pilot_id]
        from textus_kb.pilot_registry import get_pilot

        path = get_pilot(pilot_id).study_notes_resolved
        if not path.is_file():
            self._bundles[pilot_id] = {}
            return {}
        self._bundles[pilot_id] = load_pilot_bundle(path)
        return self._bundles[pilot_id]
