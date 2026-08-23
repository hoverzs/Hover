"""Read-only adapter for Aquifer Open Bible Dictionary pilot bundles."""

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
from textus_kb.pilot_registry import find_pilot


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
        self._bundles: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        if self._source is None or not self._source.enabled:
            return False
        # Enabled if at least one registered pilot dictionary bundle exists,
        # or the legacy single-file manifest path is present.
        if any(pilot.dictionary_resolved.is_file() for pilot in __import__(
            "textus_kb.pilot_registry", fromlist=["PILOTS"]
        ).PILOTS):
            return True
        return self._source.resolved_path.is_file()

    def pilot_bundle_available(self, reference: CanonicalReference) -> bool:
        if not self.available:
            return False
        pilot = find_pilot(reference)
        if pilot is None:
            return False
        return pilot.dictionary_resolved.is_file()

    def load_chunks_for_passage(self, reference: CanonicalReference) -> list[AquiferDictionaryChunk]:
        if not self.available:
            return []
        pilot = find_pilot(reference)
        if pilot is None:
            return []
        bundle = self._load_bundle_for_pilot(pilot.id)
        if not bundle:
            return []
        chunks: list[AquiferDictionaryChunk] = []
        for entry in bundle.get("entries", []):
            if not isinstance(entry, dict):
                continue
            for chunk in entry.get("chunks", []):
                if not isinstance(chunk, dict):
                    continue
                chunks.append(_chunk_from_entry(entry, chunk))
        chunks.sort(
            key=lambda item: (
                -_chunk_relevance(item),
                item.index_reference,
                item.article_id,
                item.chunk_index,
            )
        )
        return chunks

    def load_chunks_for_article(self, article_id: str) -> list[AquiferDictionaryChunk]:
        if not self.available:
            return []
        article_id = str(article_id)
        chunks: list[AquiferDictionaryChunk] = []
        for pilot in __import__("textus_kb.pilot_registry", fromlist=["PILOTS"]).PILOTS:
            bundle = self._load_bundle_for_pilot(pilot.id)
            if not bundle:
                continue
            for entry in bundle.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("article_id") or "") != article_id:
                    continue
                for chunk in entry.get("chunks", []):
                    if not isinstance(chunk, dict):
                        continue
                    chunks.append(_chunk_from_entry(entry, chunk))
        chunks.sort(key=lambda item: (item.chunk_index, item.chunk_id))
        return chunks

    def bundle_metadata(self, reference: CanonicalReference | None = None) -> dict[str, Any]:
        if not self.available:
            return {}
        pilot = find_pilot(reference) if reference is not None else None
        if pilot is not None:
            bundle = self._load_bundle_for_pilot(pilot.id)
        else:
            bundle = self._load_fallback_bundle()
        if not bundle:
            return {}
        return {
            "source_id": AQUIFER_DICTIONARY_SOURCE_ID,
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

        path = get_pilot(pilot_id).dictionary_resolved
        if not path.is_file():
            self._bundles[pilot_id] = {}
            return {}
        self._bundles[pilot_id] = load_pilot_bundle(path)
        return self._bundles[pilot_id]

    def _load_fallback_bundle(self) -> dict[str, Any]:
        if self._source is None:
            return {}
        path = self._source.resolved_path
        if not path.is_file():
            return {}
        key = str(path)
        if key not in self._bundles:
            self._bundles[key] = load_pilot_bundle(path)
        return self._bundles[key]


def _chunk_from_entry(entry: dict[str, Any], chunk: dict[str, Any]) -> AquiferDictionaryChunk:
    return AquiferDictionaryChunk(
        article_id=str(entry.get("article_id") or ""),
        chunk_id=str(chunk.get("chunk_id") or ""),
        chunk_index=int(chunk.get("chunk_index") or 0),
        title=str(entry.get("title") or ""),
        index_reference=str(entry.get("index_reference") or ""),
        heading=chunk.get("heading"),
        content_html=str(chunk.get("content_html") or ""),
        content_plain=str(
            chunk.get("content_plain")
            or html_to_plain(str(chunk.get("content_html") or ""))
        ),
        selection_reason=str(entry.get("selection_reason") or ""),
        passage_associations=tuple(entry.get("passage_associations") or ()),
        entity_topics=tuple(entry.get("entity_topics") or ()),
        license=str(entry.get("license") or AQUIFER_LICENSE),
        license_url=str(entry.get("license_url") or AQUIFER_LICENSE_URL),
        attribution=str(entry.get("attribution") or AQUIFER_ATTRIBUTION),
    )


def _chunk_relevance(chunk: AquiferDictionaryChunk) -> int:
    if chunk.passage_associations:
        return 100
    if chunk.selection_reason == "pilot_place_entity_match":
        return 85
    if chunk.selection_reason == "pilot_index_reference_match":
        return 70
    return 60
