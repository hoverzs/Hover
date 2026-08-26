"""Read-only adapter for ACAI entity store (SQLite primary + JSON pilot fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.entity_models import KBEntity
from textus_kb.entity_selection import select_entities_for_evidence
from textus_kb.importers.acai_entities import (
    ACAI_ATTRIBUTION,
    ACAI_LICENSE,
    ACAI_LICENSE_URL,
    ACAI_SOURCE_ID,
    GENERIC_ACAI_IDS,
    load_pilot_bundle,
)
from textus_kb.manifest import ManifestSource
from textus_kb.pilot_registry import PILOTS, find_pilot, get_pilot
from textus_kb.repositories.acai_entity_repository import AcaiEntityRepository, AcaiStoreStatus
from textus_kb.retrieval_config import DEFAULT_ACAI_LIMITS, AcaiRetrievalLimits


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

    def __init__(
        self,
        source: ManifestSource | None,
        *,
        limits: AcaiRetrievalLimits | None = None,
    ) -> None:
        self._source = source
        self._limits = limits or DEFAULT_ACAI_LIMITS
        self._json_cache: dict[str, dict[str, Any]] = {}
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
    def import_mode(self) -> str:
        if self._repository is not None and self._repository.available:
            return self._repository.store_status().import_mode
        return ""

    @property
    def uses_full_sqlite_runtime(self) -> bool:
        return (
            self._repository is not None
            and self._repository.available
            and not self._repository.is_pilot_store
        )

    @property
    def available(self) -> bool:
        if self._source is None or not self._source.enabled:
            return False
        if self._repository is not None and self._repository.available:
            return True
        return any(pilot.acai_json_resolved.is_file() for pilot in PILOTS)

    def store_status(self) -> AcaiStoreStatus | dict[str, Any]:
        if self._repository is not None:
            return self._repository.store_status()
        return {"available": self.available, "backend": "json"}

    def entities_for_passage(self, reference: CanonicalReference) -> list[AcaiEntityView]:
        if not self.available:
            return []
        if self.uses_full_sqlite_runtime and self._repository is not None:
            views = [
                _entity_to_view(entity)
                for entity in self._repository.entities_for_passage(reference)
            ]
            views = [view for view in views if view.passage_relations]
            views.sort(key=lambda item: (item.entity_type, item.canonical_name, item.entity_id))
            return views
        pilot = find_pilot(reference)
        if pilot is None:
            return []
        views = self._entities_for_pilot_json(pilot, reference)
        linked = [view for view in views if view.passage_relations]
        linked.sort(key=lambda item: (item.entity_type, item.canonical_name, item.entity_id))
        return linked

    def entities_for_evidence_packet(
        self,
        reference: CanonicalReference,
        *,
        dictionary_article_ids: frozenset[str] | None = None,
    ) -> list[AcaiEntityView]:
        if not self.available:
            return []
        if self.uses_full_sqlite_runtime and self._repository is not None:
            passage_views = self.entities_for_passage(reference)
            selected = select_entities_for_evidence(
                passage_views,
                limit=self._limits.evidence_entity_limit,
                dictionary_article_ids=dictionary_article_ids,
            )
            selected.sort(key=lambda item: (item.entity_type, item.canonical_name, item.entity_id))
            return selected
        pilot = find_pilot(reference)
        if pilot is None:
            return []
        views = self._entities_for_pilot_json(pilot, reference)
        views.sort(key=lambda item: (item.entity_type, item.canonical_name, item.entity_id))
        return views

    def entity_by_id(self, entity_id: str) -> AcaiEntityView | None:
        if not self.available:
            return None
        if self._repository is not None and self._repository.available:
            entity = self._repository.entity_by_id(entity_id)
            if entity is not None:
                return _entity_to_view(entity)
        for pilot in PILOTS:
            for item in self._load_pilot_json(pilot.id).get("entities", []):
                if isinstance(item, dict) and str(item.get("entity_id")) == entity_id:
                    return _to_view(item)
        return None

    def entities_for_dictionary_article(self, article_id: str) -> list[AcaiEntityView]:
        if not self.available:
            return []
        article_id = str(article_id)
        matched: list[AcaiEntityView] = []
        if self._repository is not None and self._repository.available:
            matched.extend(
                _entity_to_view(entity)
                for entity in self._repository.entities_for_dictionary_article(article_id)
            )
        if not self.uses_full_sqlite_runtime:
            for pilot in PILOTS:
                for item in self._load_pilot_json(pilot.id).get("entities", []):
                    if not isinstance(item, dict):
                        continue
                    relations = item.get("dictionary_relations") or []
                    if any(str(rel.get("dictionary_article_id")) == article_id for rel in relations):
                        matched.append(_to_view(item))
        matched.sort(key=lambda view: view.entity_id)
        seen: set[str] = set()
        deduped: list[AcaiEntityView] = []
        for view in matched:
            if view.entity_id in seen:
                continue
            seen.add(view.entity_id)
            deduped.append(view)
        return deduped

    def all_entities(self) -> list[AcaiEntityView]:
        if not self.available:
            return []
        if self._repository is not None and self._repository.available:
            views = [_entity_to_view(entity) for entity in self._repository.all_entities()]
            views.sort(key=lambda item: item.entity_id)
            return views
        return []

    def context_summary_entities(
        self,
        reference: CanonicalReference,
        *,
        limit: int | None = None,
        dictionary_article_ids: frozenset[str] | None = None,
    ) -> list[AcaiEntityView]:
        cap = limit if limit is not None else self._limits.context_entity_limit
        candidates = self.entities_for_evidence_packet(
            reference,
            dictionary_article_ids=dictionary_article_ids,
        )
        candidates = [view for view in candidates if view.external_id not in GENERIC_ACAI_IDS]
        return candidates[:cap]

    def bundle_metadata(self, reference: CanonicalReference | None = None) -> dict[str, Any]:
        if not self.available:
            return {}
        if self._repository is not None and self._repository.available:
            status = self._repository.store_status()
            meta = {
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
            if not self.uses_full_sqlite_runtime:
                pilot = find_pilot(reference) if reference is not None else None
                if pilot is not None:
                    bundle = self._load_pilot_json(pilot.id)
                    if bundle:
                        meta.update(
                            {
                                "pilot_id": bundle.get("pilot_id"),
                                "pilot_scope": bundle.get("pilot_scope"),
                                "pilot_report": bundle.get("pilot_report"),
                            }
                        )
            return meta
        pilot = find_pilot(reference) if reference is not None else None
        if pilot is not None:
            bundle = self._load_pilot_json(pilot.id)
            if bundle:
                return _metadata_from_bundle(bundle)
        return {}

    def _entities_for_pilot_json(
        self,
        pilot: Any,
        reference: CanonicalReference,
    ) -> list[AcaiEntityView]:
        bundle = self._load_pilot_json(pilot.id)
        raw_entities = [item for item in bundle.get("entities", []) if isinstance(item, dict)]
        if raw_entities:
            return [_to_view(item) for item in raw_entities]
        if self._repository is not None and self._repository.available:
            entities = self._repository.entities_for_passage(reference)
            return [_entity_to_view(entity) for entity in entities]
        return []

    def _load_pilot_json(self, pilot_id: str) -> dict[str, Any]:
        if pilot_id in self._json_cache:
            return self._json_cache[pilot_id]
        path = get_pilot(pilot_id).acai_json_resolved
        if not path.is_file():
            self._json_cache[pilot_id] = {}
            return {}
        self._json_cache[pilot_id] = load_pilot_bundle(path)
        return self._json_cache[pilot_id]


def _is_sqlite_source(path: Path) -> bool:
    return path.suffix.lower() in {".sqlite3", ".db", ".sqlite"}


def _metadata_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": ACAI_SOURCE_ID,
        "backend": "json",
        "upstream_repository": bundle.get("upstream_repository"),
        "upstream_commit": bundle.get("upstream_commit"),
        "upstream_resource_version": bundle.get("upstream_resource_version"),
        "license": bundle.get("license"),
        "license_url": bundle.get("license_url"),
        "attribution": bundle.get("attribution"),
        "pilot_id": bundle.get("pilot_id"),
        "pilot_scope": bundle.get("pilot_scope"),
        "pilot_report": bundle.get("pilot_report"),
    }


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
