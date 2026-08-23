"""Read-only adapter for Aquifer Open Study Notes pilot bundle."""

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
        self._bundle: dict[str, Any] | None = None

    @property
    def available(self) -> bool:
        return (
            self._source is not None
            and self._source.enabled
            and self._source.resolved_path.is_file()
        )

    def load_chunks_for_passage(self, reference: CanonicalReference) -> list[AquiferNoteChunk]:
        if not self.available:
            return []
        bundle = self._load_bundle()
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
            if not _references_overlap(reference, note_ref):
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
                        content_plain=str(chunk.get("content_plain") or html_to_plain(
                            str(chunk.get("content_html") or "")
                        )),
                        license=str(note.get("license") or AQUIFER_LICENSE),
                        license_url=str(note.get("license_url") or AQUIFER_LICENSE_URL),
                        attribution=str(note.get("attribution") or AQUIFER_ATTRIBUTION),
                    )
                )
        chunks.sort(key=lambda item: (item.canonical_reference, item.article_id, item.chunk_index))
        return chunks

    def bundle_metadata(self) -> dict[str, Any]:
        if not self.available:
            return {}
        bundle = self._load_bundle()
        return {
            "source_id": AQUIFER_SOURCE_ID,
            "upstream_repository": bundle.get("upstream_repository"),
            "upstream_commit": bundle.get("upstream_commit"),
            "upstream_resource_version": bundle.get("upstream_resource_version"),
            "license": bundle.get("license"),
            "license_url": bundle.get("license_url"),
            "attribution": bundle.get("attribution"),
        }

    def _load_bundle(self) -> dict[str, Any]:
        if self._bundle is not None:
            return self._bundle
        path = self._source.resolved_path if self._source is not None else Path()
        self._bundle = load_pilot_bundle(path)
        return self._bundle


def _references_overlap(left: CanonicalReference, right: CanonicalReference) -> bool:
    if left.book_id != right.book_id:
        return False
    if left.end_chapter < right.start_chapter or right.end_chapter < left.start_chapter:
        return False
    if left.start_chapter == right.start_chapter and left.end_chapter == right.end_chapter:
        return not (left.end_verse < right.start_verse or right.end_verse < left.start_verse)
    return left.start_chapter <= right.end_chapter and right.start_chapter <= left.end_chapter
