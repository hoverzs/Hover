"""Read-only adapter for Aquifer Open Bible Dictionary pilot bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.importers.aquifer_bible_dictionary import (
    AQUIFER_ATTRIBUTION,
    AQUIFER_DICTIONARY_SOURCE_ID,
    AQUIFER_LICENSE,
    AQUIFER_LICENSE_URL,
    html_to_plain,
    load_pilot_bundle,
)
from textus_kb.manifest import ManifestSource


@dataclass(frozen=True)
class AquiferDictionaryChunk:
    article_id: str
    chunk_id: str
    chunk_index: int
    title: str
    index_reference: str
    heading: str | None
    content_html: str
    content_plain: str
    selection_reason: str
    passage_associations: tuple[dict[str, str], ...]
    entity_topics: tuple[dict[str, str], ...]
    license: str
    license_url: str
    attribution: str


class AquiferBibleDictionaryAdapter:
    SOURCE_ID = AQUIFER_DICTIONARY_SOURCE_ID

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

    def load_chunks_for_passage(self, reference: CanonicalReference) -> list[AquiferDictionaryChunk]:
        if not self.available:
            return []
        if reference.book_id != "John" or not _overlaps_john_4(reference):
            return []

        bundle = self._load_bundle()
        chunks: list[AquiferDictionaryChunk] = []
        for entry in bundle.get("entries", []):
            if not isinstance(entry, dict):
                continue
            for chunk in entry.get("chunks", []):
                if not isinstance(chunk, dict):
                    continue
                chunks.append(
                    AquiferDictionaryChunk(
                        article_id=str(entry.get("article_id") or ""),
                        chunk_id=str(chunk.get("chunk_id") or ""),
                        chunk_index=int(chunk.get("chunk_index") or 0),
                        title=str(entry.get("title") or ""),
                        index_reference=str(entry.get("index_reference") or ""),
                        heading=chunk.get("heading"),
                        content_html=str(chunk.get("content_html") or ""),
                        content_plain=str(chunk.get("content_plain") or html_to_plain(
                            str(chunk.get("content_html") or "")
                        )),
                        selection_reason=str(entry.get("selection_reason") or ""),
                        passage_associations=tuple(entry.get("passage_associations") or ()),
                        entity_topics=tuple(entry.get("entity_topics") or ()),
                        license=str(entry.get("license") or AQUIFER_LICENSE),
                        license_url=str(entry.get("license_url") or AQUIFER_LICENSE_URL),
                        attribution=str(entry.get("attribution") or AQUIFER_ATTRIBUTION),
                    )
                )
        chunks.sort(
            key=lambda item: (
                -_chunk_relevance(item),
                item.index_reference,
                item.article_id,
                item.chunk_index,
            )
        )
        return chunks

    def bundle_metadata(self) -> dict[str, Any]:
        if not self.available:
            return {}
        bundle = self._load_bundle()
        return {
            "source_id": AQUIFER_DICTIONARY_SOURCE_ID,
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


def _overlaps_john_4(reference: CanonicalReference) -> bool:
    if reference.start_chapter > 4 or reference.end_chapter < 4:
        return False
    if reference.start_chapter == 4 and reference.end_chapter == 4:
        return not (reference.end_verse < 1 or reference.start_verse > 42)
    return reference.start_chapter <= 4 <= reference.end_chapter


def _chunk_relevance(chunk: AquiferDictionaryChunk) -> int:
    if chunk.passage_associations:
        return 100
    if chunk.selection_reason == "pilot_place_entity_match":
        return 85
    if chunk.selection_reason == "pilot_index_reference_match":
        return 70
    return 60
