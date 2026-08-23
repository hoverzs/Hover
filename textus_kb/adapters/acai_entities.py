"""Read-only adapter for ACAI entity store (SQLite primary, JSON pilot fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.entity_models import KBEntity
from textus_kb.importers.acai_entities import (
    ACAI_ATTRIBUTION,
    ACAI_LICENSE,
    ACAI_LICENSE_URL,
    ACAI_SOURCE_ID,
    GENERIC_ACAI_IDS,
    load_pilot_bundle,
)
from textus_kb.manifest import ManifestSource
from textus_kb.repositories.acai_entity_repository import AcaiEntityRepository, AcaiStoreStatus


@dataclass(frozen=True)
class AcaiEntityView:
    entity_id: str
    entity_type: str
    canonical_name: str
    external_id: str
    aliases: tuple[dict[str, str], ...]
    metadata: dict[str, Any]
    provenance: dict[str, Any]
    passage_relations: tuple[dict[str, Any], ...]
    dictionary_relations: tuple[dict[str, Any], ...]
    place_crosswalk: dict[str, Any] | None


class AcaiEntitiesAdapter:
    SOURCE_ID = ACAI_SOURCE_ID

    def __init__(self, source: ManifestSource | None) -> None:
        self._source = source
        self._bundle: dict[str, Any] | None = None
        self._repository: AcaiEntityRepository | None = None
        if source is not None and _is_sqlite_source(source.resolved_path):
            self._repository = AcaiEntityRepository(source.resolved_path)

    @property
    def repository(self) -> AcaiEntityRepository | None:
        return self._repository

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
        if self._repository is not None:
            return self._repository.available
        return self._source.resolved_path.is_file()

    def store_status(self) -> AcaiStoreStatus | dict[str, Any]:
        if self._repository is not None:
            return self._repository.store_status()
        if not self.available:
            return {"available": False, "backend": "json"}
        bundle = self._load_bundle()
        return {
            "available": True,
            "backend": "json",
            "entity_count": len(bundle.get("entities") or []),
            "upstream_commit": bundle.get("upstream_commit"),
            "source_version": bundle.get("upstream_resource_version"),
        }

    def entities_for_passage(self, reference: CanonicalReference) -> list[AcaiEntityView]:
        if not self.available:
            return []
        if self._repository is not None:
            if not _overlaps_john_4_pilot(reference):
                return []
            entities = self._repository.entities_for_passage(reference)
            views = [_entity_to_view(entity) for entity in entities if entity.passage_relations]
            views.sort(key=lambda item: (item.entity_type, item.canonical_name, item.entity_id))
            return views
        if not _overlaps_john_4_pilot(reference):
            return []
        bundle = self._load_bundle()
        views = [_to_view(item) for item in bundle.get("entities", []) if isinstance(item, dict)]
        linked = [view for view in views if view.passage_relations]
        linked.sort(key=lambda item: (item.entity_type, item.canonical_name, item.entity_id))
        return linked

    def entities_for_evidence_packet(self, reference: CanonicalReference) -> list[AcaiEntityView]:
        if not self.available:
            return []
        if self._repository is not None:
            entities = self._repository.entities_for_evidence_packet(reference)
            return [_entity_to_view(entity) for entity in entities]
        return self.all_entities()

    def entity_by_id(self, entity_id: str) -> AcaiEntityView | None:
        if not self.available:
            return None
        if self._repository is not None:
            entity = self._repository.entity_by_id(entity_id)
            return _entity_to_view(entity) if entity is not None else None
        for item in self._load_bundle().get("entities", []):
            if isinstance(item, dict) and str(item.get("entity_id")) == entity_id:
                return _to_view(item)
        return None

    def entities_for_dictionary_article(self, article_id: str) -> list[AcaiEntityView]:
        if not self.available:
            return []
        article_id = str(article_id)
        if self._repository is not None:
            return [_entity_to_view(entity) for entity in self._repository.entities_for_dictionary_article(article_id)]
        matched: list[AcaiEntityView] = []
        for item in self._load_bundle().get("entities", []):
            if not isinstance(item, dict):
                continue
            relations = item.get("dictionary_relations") or []
            if any(str(rel.get("dictionary_article_id")) == article_id for rel in relations):
                matched.append(_to_view(item))
        matched.sort(key=lambda view: view.entity_id)
        return matched

    def all_entities(self) -> list[AcaiEntityView]:
        if not self.available:
            return []
        if self._repository is not None:
            views = [_entity_to_view(entity) for entity in self._repository.all_entities()]
            views.sort(key=lambda item: item.entity_id)
            return views
        views = [_to_view(item) for item in self._load_bundle().get("entities", []) if isinstance(item, dict)]
        views.sort(key=lambda item: item.entity_id)
        return views

    def context_summary_entities(self, *, limit: int = 8) -> list[AcaiEntityView]:
        """Named, non-generic entities prioritized for compact context summaries."""
        candidates = [
            view
            for view in self.all_entities()
            if view.external_id not in GENERIC_ACAI_IDS
        ]
        candidates.sort(
            key=lambda view: (
                0 if view.passage_relations else 1,
                0 if view.dictionary_relations else 1,
                0 if view.place_crosswalk else 1,
                view.entity_type,
                view.canonical_name,
                view.entity_id,
            )
        )
        return candidates[:limit]

    def bundle_metadata(self) -> dict[str, Any]:
        if not self.available:
            return {}
        if self._repository is not None:
            status = self._repository.store_status()
            return {
                "source_id": ACAI_SOURCE_ID,
                "backend": "sqlite",
                "upstream_repository": "https://github.com/BibleAquifer/ACAI",
                "upstream_commit": status.upstream_commit,
                "upstream_resource_version": status.source_version,
                "license": ACAI_LICENSE,
                "license_url": ACAI_LICENSE_URL,
                "attribution": ACAI_ATTRIBUTION,
                "import_mode": status.import_mode,
                "content_hash": status.content_hash,
            }
        bundle = self._load_bundle()
        return {
            "source_id": ACAI_SOURCE_ID,
            "backend": "json",
            "upstream_repository": bundle.get("upstream_repository"),
            "upstream_commit": bundle.get("upstream_commit"),
            "upstream_resource_version": bundle.get("upstream_resource_version"),
            "license": bundle.get("license"),
            "license_url": bundle.get("license_url"),
            "attribution": bundle.get("attribution"),
            "pilot_report": bundle.get("pilot_report"),
        }

    def _load_bundle(self) -> dict[str, Any]:
        if self._bundle is not None:
            return self._bundle
        path = self._source.resolved_path if self._source is not None else Path()
        self._bundle = load_pilot_bundle(path)
        return self._bundle


def _is_sqlite_source(path: Path) -> bool:
    return path.suffix.lower() in {".sqlite3", ".db", ".sqlite"}


def _overlaps_john_4_pilot(reference: CanonicalReference) -> bool:
    if reference.book_id != "John":
        return False
    if reference.start_chapter > 4 or reference.end_chapter < 4:
        return False
    if reference.start_chapter == 4 and reference.end_chapter == 4:
        return not (reference.end_verse < 1 or reference.start_verse > 42)
    return reference.start_chapter <= 4 <= reference.end_chapter


def _entity_to_view(entity: KBEntity) -> AcaiEntityView:
    payload = entity.to_dict()
    return AcaiEntityView(
        entity_id=entity.entity_id,
        entity_type=entity.entity_type,
        canonical_name=entity.canonical_name,
        external_id=entity.external_id,
        aliases=tuple(dict(item) for item in payload.get("aliases") or []),
        metadata=dict(entity.metadata),
        provenance=dict(entity.provenance),
        passage_relations=tuple(dict(item) for item in payload.get("passage_relations") or []),
        dictionary_relations=tuple(dict(item) for item in payload.get("dictionary_relations") or []),
        place_crosswalk=dict(payload["place_crosswalk"]) if payload.get("place_crosswalk") else None,
    )


def _to_view(raw: dict[str, Any]) -> AcaiEntityView:
    return AcaiEntityView(
        entity_id=str(raw.get("entity_id") or ""),
        entity_type=str(raw.get("entity_type") or ""),
        canonical_name=str(raw.get("canonical_name") or ""),
        external_id=str((raw.get("external_ids") or {}).get("acai") or raw.get("external_id") or ""),
        aliases=tuple(dict(item) for item in raw.get("aliases") or [] if isinstance(item, dict)),
        metadata=dict(raw.get("metadata") or {}),
        provenance=dict(raw.get("provenance") or {}),
        passage_relations=tuple(dict(item) for item in raw.get("passage_relations") or [] if isinstance(item, dict)),
        dictionary_relations=tuple(
            dict(item) for item in raw.get("dictionary_relations") or [] if isinstance(item, dict)
        ),
        place_crosswalk=dict(raw["place_crosswalk"]) if isinstance(raw.get("place_crosswalk"), dict) else None,
    )


def entity_to_packet_dict(view: AcaiEntityView) -> dict[str, Any]:
    return {
        "entity_id": view.entity_id,
        "entity_type": view.entity_type,
        "canonical_name": view.canonical_name,
        "external_ids": {"acai": view.external_id},
        "aliases": list(view.aliases),
        "metadata": dict(view.metadata),
        "provenance": dict(view.provenance),
        "passage_relations": list(view.passage_relations),
        "dictionary_relations": list(view.dictionary_relations),
        **({"place_crosswalk": view.place_crosswalk} if view.place_crosswalk else {}),
    }
