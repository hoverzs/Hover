"""Read-only adapter for Aquifer Open Bible Dictionary (SQLite runtime + JSON pilot fallback)."""

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
from textus_kb.pilot_registry import PILOTS, find_pilot
from textus_kb.repositories.aquifer_dictionary_repository import AquiferDictionaryRepository
from textus_kb.retrieval_config import DEFAULT_AQUIFER_LIMITS, AquiferRetrievalLimits


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

    def __init__(
        self,
        source: ManifestSource | None,
        *,
        limits: AquiferRetrievalLimits | None = None,
    ) -> None:
        self._source = source
        self._limits = limits or DEFAULT_AQUIFER_LIMITS
        self._bundles: dict[str, dict[str, Any]] = {}
        self._repository: AquiferDictionaryRepository | None = None
        if source is not None and _is_sqlite_source(source.resolved_path):
            self._repository = AquiferDictionaryRepository(source.resolved_path)

    @property
    def backend(self) -> str:
        if self._repository is not None and self._repository.available:
            return "sqlite"
        if self.available:
            return "json"
        return "none"

    @property
    def available(self) -> bool:
        if self._source is None or not self._source.enabled:
            return False
        if self._repository is not None and self._repository.available:
            return True
        if any(pilot.dictionary_resolved.is_file() for pilot in PILOTS):
            return True
        return self._source.resolved_path.is_file()

    def store_available(self) -> bool:
        return self.available

    def passage_has_data(self, reference: CanonicalReference) -> bool:
        if not self.available:
            return False
        if self.backend == "sqlite" and self._repository is not None:
            return bool(self._repository.articles_for_passage(reference))
        pilot = find_pilot(reference)
        if pilot is None:
            return False
        return pilot.dictionary_resolved.is_file()

    def load_chunks_for_passage(self, reference: CanonicalReference) -> list[AquiferDictionaryChunk]:
        if not self.available:
            return []
        if self.backend == "sqlite" and self._repository is not None:
            raw_chunks = self._repository.chunks_for_passage(reference)
            chunks = [_chunk_from_sqlite_row(row) for row in raw_chunks]
        else:
            pilot = find_pilot(reference)
            if pilot is None:
                return []
            bundle = self._load_bundle_for_pilot(pilot.id)
            if not bundle:
                return []
            chunks = []
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
        return chunks[: self._limits.dictionary_candidate_limit]

    def load_chunks_for_article(self, article_id: str) -> list[AquiferDictionaryChunk]:
        if not self.available:
            return []
        article_id = str(article_id)
        if self.backend == "sqlite" and self._repository is not None:
            rows = self._repository.chunks_for_article(article_id)
            chunks = [_chunk_from_sqlite_row(row) for row in rows]
            chunks.sort(key=lambda item: (item.chunk_index, item.chunk_id))
            return chunks
        chunks: list[AquiferDictionaryChunk] = []
        for pilot in PILOTS:
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
        if self.backend == "sqlite" and self._repository is not None:
            status = self._repository.store_status()
            return {
                "source_id": AQUIFER_DICTIONARY_SOURCE_ID,
                "backend": "sqlite",
                "upstream_repository": status.upstream_repository,
                "upstream_commit": status.upstream_commit,
                "upstream_resource_version": status.source_version,
                "license": status.license,
                "license_url": status.license_url,
                "attribution": status.attribution,
            }
        pilot = find_pilot(reference) if reference is not None else None
        if pilot is not None:
            bundle = self._load_bundle_for_pilot(pilot.id)
        else:
            bundle = self._load_fallback_bundle()
        if not bundle:
            return {}
        return {
            "source_id": AQUIFER_DICTIONARY_SOURCE_ID,
            "backend": "json",
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
        if not path.is_file() or _is_sqlite_source(path):
            return {}
        key = str(path)
        if key not in self._bundles:
            self._bundles[key] = load_pilot_bundle(path)
        return self._bundles[key]


def _is_sqlite_source(path: Path) -> bool:
    return path.suffix.lower() in {".sqlite3", ".db", ".sqlite"}


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


def _chunk_from_sqlite_row(row: dict[str, Any]) -> AquiferDictionaryChunk:
    return AquiferDictionaryChunk(
        article_id=str(row.get("article_id") or ""),
        chunk_id=str(row.get("chunk_id") or ""),
        chunk_index=int(row.get("chunk_index") or 0),
        title=str(row.get("title") or ""),
        index_reference=str(row.get("index_reference") or ""),
        heading=row.get("heading"),
        content_html=str(row.get("content_html") or ""),
        content_plain=str(row.get("content_plain") or ""),
        selection_reason=str(row.get("selection_reason") or ""),
        passage_associations=tuple(row.get("passage_associations") or ()),
        entity_topics=tuple(row.get("entity_topics") or ()),
        license=str(row.get("license") or AQUIFER_LICENSE),
        license_url=str(row.get("license_url") or AQUIFER_LICENSE_URL),
        attribution=str(row.get("attribution") or AQUIFER_ATTRIBUTION),
    )


def _chunk_relevance(chunk: AquiferDictionaryChunk) -> int:
    if chunk.passage_associations:
        return 100
    if chunk.selection_reason == "pilot_place_entity_match":
        return 85
    if chunk.selection_reason == "pilot_index_reference_match":
        return 70
    if chunk.selection_reason == "direct_acai_association":
        return 65
    return 60
