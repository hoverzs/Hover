"""Read-only ACAI entity SQLite repository."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.pilot_registry import org_ref_bounds
from textus_kb.entity_models import (
    EntityAlias,
    EntityDictionaryRelation,
    EntityPassageRelation,
    KBEntity,
    PlaceCrosswalk,
)
from textus_kb.importers.acai_entities import ACAI_SOURCE_ID
from textus_kb.importers.acai_sqlite import DEFAULT_DATABASE_PATH, validate_acai_database


@dataclass(frozen=True)
class AcaiStoreStatus:
    available: bool
    schema_version: str
    source_version: str
    upstream_commit: str
    entity_count: int
    passage_link_count: int
    dictionary_link_count: int
    external_id_count: int
    content_hash: str
    import_mode: str
    database_path: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "schema_version": self.schema_version,
            "source_version": self.source_version,
            "upstream_commit": self.upstream_commit,
            "entity_count": self.entity_count,
            "passage_link_count": self.passage_link_count,
            "dictionary_link_count": self.dictionary_link_count,
            "external_id_count": self.external_id_count,
            "content_hash": self.content_hash,
            "import_mode": self.import_mode,
            "database_path": self.database_path,
            "warnings": list(self.warnings),
        }


class AcaiEntityRepository:
    """Read-only repository over the ACAI entity SQLite store."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH

    @property
    def available(self) -> bool:
        return self.database_path.is_file()

    @property
    def is_pilot_store(self) -> bool:
        status = self.store_status()
        return status.import_mode == "pilot"

    def store_status(self) -> AcaiStoreStatus:
        if not self.available:
            return AcaiStoreStatus(
                available=False,
                schema_version="",
                source_version="",
                upstream_commit="",
                entity_count=0,
                passage_link_count=0,
                dictionary_link_count=0,
                external_id_count=0,
                content_hash="",
                import_mode="",
                database_path=str(self.database_path),
                warnings=("ACAI entity store file missing.",),
            )
        validation = validate_acai_database(self.database_path)
        meta = self._metadata()
        return AcaiStoreStatus(
            available=True,
            schema_version=validation.schema_version,
            source_version=validation.source_version,
            upstream_commit=validation.upstream_commit,
            entity_count=validation.entity_count,
            passage_link_count=validation.passage_link_count,
            dictionary_link_count=validation.dictionary_link_count,
            external_id_count=validation.external_id_count,
            content_hash=validation.content_hash,
            import_mode=str(meta.get("import_mode") or ""),
            database_path=str(self.database_path),
        )

    def entity_by_id(self, entity_id: str) -> KBEntity | None:
        row = self._fetchone(
            "SELECT * FROM entities WHERE entity_id = ?",
            (entity_id,),
        )
        return self._entity_from_row(row) if row is not None else None

    def entities_by_type(self, entity_type: str) -> list[KBEntity]:
        rows = self._fetchall(
            "SELECT * FROM entities WHERE entity_type = ? ORDER BY canonical_name, entity_id",
            (entity_type,),
        )
        return [self._entity_from_row(row) for row in rows]

    def entities_for_passage(self, reference: CanonicalReference | str) -> list[KBEntity]:
        canonical = (
            reference
            if isinstance(reference, CanonicalReference)
            else CanonicalReference.parse(reference)
        )
        org_lo, org_hi = _org_ref_bounds(canonical)
        rows = self._fetchall(
            """
            SELECT DISTINCT e.*
            FROM entities e
            JOIN entity_passage_links p ON p.entity_id = e.entity_id
            WHERE p.org_ref BETWEEN ? AND ?
            ORDER BY e.entity_type, e.canonical_name, e.entity_id
            """,
            (org_lo, org_hi),
        )
        return [self._entity_from_row(row) for row in rows]

    def all_entities(self) -> list[KBEntity]:
        rows = self._fetchall(
            "SELECT * FROM entities ORDER BY entity_id",
        )
        return [self._entity_from_row(row) for row in rows]

    def entities_for_evidence_packet(self, reference: CanonicalReference) -> list[KBEntity]:
        if self.is_pilot_store:
            return self.all_entities()
        return self.entities_for_passage(reference)

    def dictionary_articles_for_entity(self, entity_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT dictionary_article_id, dictionary_title, match_method,
                   match_confidence, mapping_method
            FROM entity_dictionary_links
            WHERE entity_id = ?
            ORDER BY dictionary_article_id
            """,
            (entity_id,),
        )
        return [dict(row) for row in rows]

    def external_ids_for_entity(self, entity_id: str) -> list[dict[str, str]]:
        rows = self._fetchall(
            """
            SELECT namespace, external_id
            FROM entity_external_ids
            WHERE entity_id = ?
            ORDER BY namespace, external_id
            """,
            (entity_id,),
        )
        return [{"namespace": row["namespace"], "external_id": row["external_id"]} for row in rows]

    def entities_for_dictionary_article(self, article_id: str) -> list[KBEntity]:
        rows = self._fetchall(
            """
            SELECT e.*
            FROM entities e
            JOIN entity_dictionary_links d ON d.entity_id = e.entity_id
            WHERE d.dictionary_article_id = ?
            ORDER BY e.entity_id
            """,
            (str(article_id),),
        )
        return [self._entity_from_row(row) for row in rows]

    def _metadata(self) -> dict[str, str]:
        rows = self._fetchall("SELECT key, value FROM store_metadata")
        return {row["key"]: row["value"] for row in rows}

    def _entity_from_row(self, row: sqlite3.Row) -> KBEntity:
        metadata = json.loads(row["metadata_json"])
        provenance = json.loads(row["provenance_json"])
        crosswalk_raw = row["place_crosswalk_json"]
        crosswalk = PlaceCrosswalk(**json.loads(crosswalk_raw)) if crosswalk_raw else None

        entity_id = row["entity_id"]
        aliases = self._aliases_for_entity(entity_id)
        passage_relations = self._passage_relations_for_entity(entity_id)
        dictionary_relations = self._dictionary_relations_for_entity(
            entity_id,
            external_id=row["external_id"],
        )

        return KBEntity(
            entity_id=entity_id,
            entity_type=row["entity_type"],
            canonical_name=row["canonical_name"],
            source_id=ACAI_SOURCE_ID,
            external_id=row["external_id"],
            aliases=aliases,
            metadata=metadata,
            provenance=provenance,
            passage_relations=passage_relations,
            dictionary_relations=dictionary_relations,
            place_crosswalk=crosswalk,
        )

    def _aliases_for_entity(self, entity_id: str) -> tuple[EntityAlias, ...]:
        rows = self._fetchall(
            """
            SELECT language, alias, alias_type
            FROM entity_aliases
            WHERE entity_id = ?
            ORDER BY language, alias
            """,
            (entity_id,),
        )
        return tuple(
            EntityAlias(label=row["alias"], language=row["language"], source=row["alias_type"])
            for row in rows
        )

    def _passage_relations_for_entity(self, entity_id: str) -> tuple[EntityPassageRelation, ...]:
        rows = self._fetchall(
            """
            SELECT canonical_passage, relation_type, org_ref, mapping_method, confidence
            FROM entity_passage_links
            WHERE entity_id = ?
            ORDER BY org_ref
            """,
            (entity_id,),
        )
        if not rows:
            return ()
        grouped: dict[tuple[str, str], list[str]] = {}
        methods: dict[tuple[str, str], tuple[str, str]] = {}
        for row in rows:
            key = (row["canonical_passage"] or "", row["relation_type"])
            grouped.setdefault(key, []).append(row["org_ref"])
            methods[key] = (row["mapping_method"], row["confidence"])
        relations: list[EntityPassageRelation] = []
        for (canonical_passage, relation_type), refs in sorted(grouped.items()):
            mapping_method, confidence = methods[(canonical_passage, relation_type)]
            relations.append(
                EntityPassageRelation(
                    canonical_passage=canonical_passage,
                    relation_type=relation_type,
                    source_id=ACAI_SOURCE_ID,
                    upstream_refs=tuple(sorted(set(refs))),
                    mapping_method=mapping_method,
                    confidence=confidence,
                )
            )
        return tuple(relations)

    def _dictionary_relations_for_entity(
        self,
        entity_id: str,
        *,
        external_id: str,
    ) -> tuple[EntityDictionaryRelation, ...]:
        rows = self._fetchall(
            """
            SELECT dictionary_article_id, dictionary_title, match_method,
                   match_confidence, mapping_method
            FROM entity_dictionary_links
            WHERE entity_id = ?
            ORDER BY dictionary_article_id
            """,
            (entity_id,),
        )
        return tuple(
            EntityDictionaryRelation(
                dictionary_article_id=row["dictionary_article_id"],
                dictionary_title=str(row["dictionary_title"] or ""),
                acai_id=external_id,
                match_method=row["match_method"],
                match_confidence=row["match_confidence"],
                source_id=ACAI_SOURCE_ID,
                mapping_method=row["mapping_method"],
            )
            for row in rows
        )

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _fetchone(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(query, params).fetchone()

    def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(connection.execute(query, params).fetchall())


def _org_ref_bounds(reference: CanonicalReference) -> tuple[str, str]:
    return org_ref_bounds(reference)
