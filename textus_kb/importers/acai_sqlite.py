"""ACAI entity SQLite schema, import, and validation."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.entity_models import (
    MAPPING_EXPLICIT,
    KBEntity,
    textus_entity_id_from_acai,
)
from textus_kb.importers.acai_entities import (
    ACAI_ATTRIBUTION,
    ACAI_LICENSE,
    ACAI_LICENSE_URL,
    ACAI_RELEASE_VERSION,
    ACAI_SOURCE_ID,
    ACAI_TYPE_FOLDERS,
    ACAI_UPSTREAM_REPO,
    DEFAULT_UPSTREAM_PATH,
    UPSTREAM_ENV_VAR,
    _build_crosswalk_index,
    _collect_org_refs,
    _collect_unresolved_crosswalks,
    _load_acai_record,
    _load_catalog_places,
    _normalize_entity,
    import_john_4_pilot,
    load_pilot_bundle,
    read_upstream_commit,
    resolve_upstream_path,
)
from textus_kb.paths import PROJECT_ROOT

SCHEMA_VERSION = "1"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "generated" / "acai_entities.sqlite3"
PILOT_JSON_PATH = PROJECT_ROOT / "data" / "kb" / "acai" / "john_4_1_42_entities.json"


@dataclass
class AcaiSqliteImportReport:
    database_path: Path
    entity_count: int
    alias_count: int
    passage_link_count: int
    external_id_count: int
    dictionary_link_count: int
    upstream_commit: str
    source_version: str
    content_hash: str
    elapsed_ms: int
    import_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": str(self.database_path),
            "entity_count": self.entity_count,
            "alias_count": self.alias_count,
            "passage_link_count": self.passage_link_count,
            "external_id_count": self.external_id_count,
            "dictionary_link_count": self.dictionary_link_count,
            "upstream_commit": self.upstream_commit,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
            "elapsed_ms": self.elapsed_ms,
            "import_mode": self.import_mode,
        }


@dataclass
class AcaiStoreValidation:
    schema_version: str
    entity_count: int
    passage_link_count: int
    dictionary_link_count: int
    external_id_count: int
    source_version: str
    upstream_commit: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            external_id TEXT NOT NULL UNIQUE,
            entity_type TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            primary_external_id TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            place_crosswalk_json TEXT
        );

        CREATE TABLE IF NOT EXISTS entity_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            language TEXT NOT NULL,
            alias TEXT NOT NULL,
            alias_type TEXT NOT NULL,
            UNIQUE(entity_id, language, alias, alias_type)
        );

        CREATE TABLE IF NOT EXISTS entity_passage_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            org_ref TEXT NOT NULL,
            canonical_passage TEXT,
            relation_type TEXT NOT NULL,
            mapping_method TEXT NOT NULL,
            confidence TEXT NOT NULL,
            UNIQUE(entity_id, org_ref, relation_type)
        );

        CREATE TABLE IF NOT EXISTS entity_external_ids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            external_id TEXT NOT NULL,
            UNIQUE(entity_id, namespace, external_id)
        );

        CREATE TABLE IF NOT EXISTS entity_dictionary_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            dictionary_article_id TEXT NOT NULL,
            dictionary_title TEXT,
            match_method TEXT NOT NULL,
            match_confidence REAL,
            mapping_method TEXT NOT NULL,
            UNIQUE(entity_id, dictionary_article_id, match_method)
        );

        CREATE INDEX IF NOT EXISTS idx_entities_external_id ON entities(external_id);
        CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
        CREATE INDEX IF NOT EXISTS idx_entities_canonical_name ON entities(canonical_name);
        CREATE INDEX IF NOT EXISTS idx_entity_passage_org_ref ON entity_passage_links(org_ref);
        CREATE INDEX IF NOT EXISTS idx_entity_passage_canonical ON entity_passage_links(canonical_passage);
        CREATE INDEX IF NOT EXISTS idx_entity_external_namespace ON entity_external_ids(namespace, external_id);
        CREATE INDEX IF NOT EXISTS idx_entity_dictionary_article ON entity_dictionary_links(dictionary_article_id);
        """
    )


def import_acai_sqlite(
    *,
    upstream_root: str | Path | None = None,
    database_path: str | Path | None = None,
    mode: str = "full",
    dictionary_upstream: str | Path | None = None,
    places_catalog_path: str | Path | None = None,
) -> AcaiSqliteImportReport:
    """Import ACAI upstream into SQLite. mode='full' imports entire corpus; 'pilot' mirrors Phase 4A selection."""
    import time

    started = time.perf_counter()
    root = resolve_upstream_path(upstream_root)
    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    dict_upstream = (
        Path(dictionary_upstream)
        if dictionary_upstream is not None
        else PROJECT_ROOT / "_upstream_audit" / "AquiferOpenBibleDictionary"
    )
    catalog_path = (
        Path(places_catalog_path)
        if places_catalog_path is not None
        else PROJECT_ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
    )

    upstream_commit = read_upstream_commit(root)
    catalog_places = _load_catalog_places(catalog_path)
    crosswalk_index = _build_crosswalk_index(catalog_places)

    if mode == "pilot":
        if PILOT_JSON_PATH.is_file():
            bundle = load_pilot_bundle(PILOT_JSON_PATH)
        else:
            pilot_result = import_john_4_pilot(upstream_root=root, places_catalog_path=catalog_path)
            bundle = load_pilot_bundle(pilot_result.output_path)
        entities = [_entity_from_dict(item) for item in bundle.get("entities", [])]
        dictionary_links = _flatten_dictionary_links(entities)
        unresolved = bundle.get("unresolved_crosswalks") or []
    else:
        entities, dictionary_links, unresolved = _import_full_entities(
            root,
            upstream_commit=upstream_commit,
            crosswalk_index=crosswalk_index,
            catalog_places=catalog_places,
            dict_upstream=dict_upstream,
        )

    content_hash = _hash_entity_payload(entities)
    alias_count = 0
    passage_count = 0
    external_count = 0
    dict_count = 0

    with sqlite3.connect(db_path) as connection:
        create_schema(connection)
        with connection:
            connection.execute("DELETE FROM store_metadata")
            connection.execute("DELETE FROM entities")
            connection.execute("DELETE FROM entity_aliases")
            connection.execute("DELETE FROM entity_passage_links")
            connection.execute("DELETE FROM entity_external_ids")
            connection.execute("DELETE FROM entity_dictionary_links")

            _write_metadata(
                connection,
                upstream_commit=upstream_commit,
                content_hash=content_hash,
                entity_count=len(entities),
                import_mode=mode,
                unresolved_count=len(unresolved),
            )

            for entity in entities:
                connection.execute(
                    """
                    INSERT INTO entities (
                        entity_id, external_id, entity_type, canonical_name,
                        primary_external_id, metadata_json, provenance_json, place_crosswalk_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity.entity_id,
                        entity.external_id,
                        entity.entity_type,
                        entity.canonical_name,
                        str(entity.metadata.get("primary_id") or entity.external_id),
                        json.dumps(entity.metadata, ensure_ascii=False),
                        json.dumps(entity.provenance, ensure_ascii=False),
                        json.dumps(entity.place_crosswalk.to_dict(), ensure_ascii=False)
                        if entity.place_crosswalk
                        else None,
                    ),
                )

                for alias in entity.aliases:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO entity_aliases (entity_id, language, alias, alias_type)
                        VALUES (?, ?, ?, ?)
                        """,
                        (entity.entity_id, alias.language, alias.label, alias.source),
                    )
                    alias_count += 1

                for rel in entity.passage_relations:
                    for org_ref in rel.upstream_refs:
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO entity_passage_links (
                                entity_id, org_ref, canonical_passage, relation_type,
                                mapping_method, confidence
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                entity.entity_id,
                                org_ref,
                                rel.canonical_passage,
                                rel.relation_type,
                                rel.mapping_method,
                                rel.confidence,
                            ),
                        )
                        passage_count += 1

                for org_ref in entity.metadata.get("all_org_refs") or []:
                    if any(org_ref in (rel.upstream_refs or ()) for rel in entity.passage_relations):
                        continue
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO entity_passage_links (
                            entity_id, org_ref, canonical_passage, relation_type,
                            mapping_method, confidence
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entity.entity_id,
                            org_ref,
                            _org_ref_to_canonical(org_ref),
                            "passage_mention",
                            MAPPING_EXPLICIT,
                            MAPPING_EXPLICIT,
                        ),
                    )
                    passage_count += 1

                alternate_sources = entity.metadata.get("alternate_sources") or {}
                if isinstance(alternate_sources, dict):
                    for namespace, values in alternate_sources.items():
                        if not isinstance(values, list):
                            continue
                        for value in values:
                            connection.execute(
                                """
                                INSERT OR IGNORE INTO entity_external_ids (entity_id, namespace, external_id)
                                VALUES (?, ?, ?)
                                """,
                                (entity.entity_id, str(namespace), str(value)),
                            )
                            external_count += 1

                if entity.place_crosswalk and entity.place_crosswalk.openbible_id:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO entity_external_ids (entity_id, namespace, external_id)
                        VALUES (?, 'obi', ?)
                        """,
                        (entity.entity_id, entity.place_crosswalk.openbible_id),
                    )
                    external_count += 1

            external_to_entity_id = {entity.external_id: entity.entity_id for entity in entities}
            primary_to_entity_id = {
                str(entity.metadata.get("primary_id") or entity.external_id): entity.entity_id
                for entity in entities
            }
            for link in dictionary_links:
                acai_id = link["acai_id"]
                record = _load_acai_record(root, acai_id)
                if record is not None:
                    primary_id = str(record.get("primary_id") or record.get("id") or acai_id)
                else:
                    primary_id = acai_id
                entity_id = primary_to_entity_id.get(primary_id) or external_to_entity_id.get(acai_id)
                if not entity_id:
                    continue
                connection.execute(
                    """
                    INSERT OR IGNORE INTO entity_dictionary_links (
                        entity_id, dictionary_article_id, dictionary_title,
                        match_method, match_confidence, mapping_method
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        link["dictionary_article_id"],
                        link.get("dictionary_title"),
                        link.get("match_method", "unknown"),
                        link.get("match_confidence"),
                        link.get("mapping_method", MAPPING_EXPLICIT),
                    ),
                )
                dict_count += 1

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return AcaiSqliteImportReport(
        database_path=db_path,
        entity_count=len(entities),
        alias_count=alias_count,
        passage_link_count=passage_count,
        external_id_count=external_count,
        dictionary_link_count=dict_count,
        upstream_commit=upstream_commit,
        source_version=ACAI_RELEASE_VERSION,
        content_hash=content_hash,
        elapsed_ms=elapsed_ms,
        import_mode=mode,
    )


def validate_acai_database(database_path: str | Path) -> AcaiStoreValidation:
    path = Path(database_path)
    with sqlite3.connect(path) as connection:
        meta = {row[0]: row[1] for row in connection.execute("SELECT key, value FROM store_metadata")}
        entity_count = connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        passage_link_count = connection.execute("SELECT COUNT(*) FROM entity_passage_links").fetchone()[0]
        dictionary_link_count = connection.execute("SELECT COUNT(*) FROM entity_dictionary_links").fetchone()[0]
        external_id_count = connection.execute("SELECT COUNT(*) FROM entity_external_ids").fetchone()[0]
    return AcaiStoreValidation(
        schema_version=meta.get("schema_version", ""),
        entity_count=int(entity_count),
        passage_link_count=int(passage_link_count),
        dictionary_link_count=int(dictionary_link_count),
        external_id_count=int(external_id_count),
        source_version=meta.get("source_version", ""),
        upstream_commit=meta.get("upstream_commit", ""),
        content_hash=meta.get("content_hash", ""),
    )


def _import_full_entities(
    root: Path,
    *,
    upstream_commit: str,
    crosswalk_index: dict[str, str],
    catalog_places: dict[str, dict[str, Any]],
    dict_upstream: Path,
) -> tuple[list[KBEntity], list[dict[str, Any]], list[dict[str, Any]]]:
    entities: list[KBEntity] = []
    seen_primary: set[str] = set()
    for folder in ACAI_TYPE_FOLDERS.values():
        json_dir = root / folder / "json"
        if not json_dir.is_dir():
            continue
        for path in sorted(json_dir.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            external_id = str(record.get("id") or "")
            primary_id = str(record.get("primary_id") or external_id)
            if primary_id != external_id:
                continue
            if primary_id in seen_primary:
                continue
            seen_primary.add(primary_id)
            entity = _normalize_entity(
                record,
                upstream_commit=upstream_commit,
                dictionary_links=[],
                crosswalk_index=crosswalk_index,
                catalog_places=catalog_places,
            )
            metadata = dict(entity.metadata)
            metadata["all_org_refs"] = sorted(_collect_org_refs(record))
            entity = KBEntity(
                entity_id=entity.entity_id,
                entity_type=entity.entity_type,
                canonical_name=entity.canonical_name,
                source_id=entity.source_id,
                external_id=entity.external_id,
                aliases=entity.aliases,
                metadata=metadata,
                provenance=entity.provenance,
                passage_relations=entity.passage_relations,
                dictionary_relations=entity.dictionary_relations,
                place_crosswalk=entity.place_crosswalk,
            )
            entities.append(entity)

    dictionary_links: list[dict[str, Any]] = []
    if dict_upstream.is_dir():
        dictionary_links = _collect_dictionary_acai_links_from_upstream(dict_upstream)

    entities.sort(key=lambda item: item.entity_id)
    unresolved = _collect_unresolved_crosswalks(catalog_places, entities, crosswalk_index)
    return entities, dictionary_links, unresolved


def _org_ref_to_canonical(org_ref: str) -> str | None:
    if len(org_ref) != 8 or not org_ref.isdigit():
        return None
    book = int(org_ref[:2])
    if book != 43:
        return None
    chapter = int(org_ref[2:5])
    verse = int(org_ref[5:8])
    return f"John.{chapter}.{verse}"


def _collect_dictionary_acai_links_from_upstream(dict_upstream: Path) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    json_dir = dict_upstream / "eng" / "json"
    if not json_dir.is_dir():
        return links
    seen: set[tuple[str, str]] = set()
    for path in json_dir.glob("*.content.json"):
        articles = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(articles, list):
            continue
        for article in articles:
            article_id = str(article.get("content_id") or "")
            title = str(article.get("title") or "")
            for assoc in article.get("associations", {}).get("acai", []):
                acai_id = str(assoc.get("id") or "").strip()
                if not acai_id:
                    continue
                key = (acai_id, article_id)
                if key in seen:
                    continue
                seen.add(key)
                links.append(
                    {
                        "acai_id": acai_id,
                        "dictionary_article_id": article_id,
                        "dictionary_title": title,
                        "match_method": str(assoc.get("match_method") or "unknown"),
                        "match_confidence": assoc.get("confidence"),
                    }
                )
    return links


def _entity_from_dict(raw: dict[str, Any]) -> KBEntity:
    from textus_kb.entity_models import EntityAlias, EntityDictionaryRelation, EntityPassageRelation, PlaceCrosswalk

    crosswalk = raw.get("place_crosswalk")
    return KBEntity(
        entity_id=str(raw.get("entity_id") or ""),
        entity_type=str(raw.get("entity_type") or ""),
        canonical_name=str(raw.get("canonical_name") or ""),
        source_id=ACAI_SOURCE_ID,
        external_id=str((raw.get("external_ids") or {}).get("acai") or ""),
        aliases=tuple(EntityAlias(**item) for item in raw.get("aliases") or []),
        metadata=dict(raw.get("metadata") or {}),
        provenance=dict(raw.get("provenance") or {}),
        passage_relations=tuple(
            EntityPassageRelation(
                canonical_passage=item["canonical_passage"],
                relation_type=item["relation_type"],
                source_id=item["source_id"],
                upstream_refs=tuple(item.get("upstream_refs") or ()),
                mapping_method=item.get("mapping_method", MAPPING_EXPLICIT),
                confidence=item.get("confidence", MAPPING_EXPLICIT),
            )
            for item in raw.get("passage_relations") or []
        ),
        dictionary_relations=tuple(
            EntityDictionaryRelation(
                dictionary_article_id=item["dictionary_article_id"],
                dictionary_title=item["dictionary_title"],
                acai_id=str((raw.get("external_ids") or {}).get("acai") or ""),
                match_method=item.get("match_method", "unknown"),
                match_confidence=item.get("match_confidence"),
                source_id=item.get("source_id", ACAI_SOURCE_ID),
                mapping_method=item.get("mapping_method", MAPPING_EXPLICIT),
            )
            for item in raw.get("dictionary_relations") or []
        ),
        place_crosswalk=PlaceCrosswalk(**crosswalk) if isinstance(crosswalk, dict) else None,
    )


def _flatten_dictionary_links(entities: list[KBEntity]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for entity in entities:
        for rel in entity.dictionary_relations:
            links.append(
                {
                    "acai_id": entity.external_id,
                    "dictionary_article_id": rel.dictionary_article_id,
                    "dictionary_title": rel.dictionary_title,
                    "match_method": rel.match_method,
                    "match_confidence": rel.match_confidence,
                    "mapping_method": rel.mapping_method,
                }
            )
    return links


def _group_dictionary_links(
    dictionary_links: list[dict[str, Any]],
    entities: list[KBEntity],
) -> dict[str, list[dict[str, Any]]]:
    external_to_entity_id = {entity.external_id: entity.entity_id for entity in entities}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for link in dictionary_links:
        acai_id = link["acai_id"]
        entity_id = external_to_entity_id.get(acai_id)
        if not entity_id:
            continue
        grouped.setdefault(entity_id, []).append(link)
    for entity in entities:
        for rel in entity.dictionary_relations:
            grouped.setdefault(entity.entity_id, []).append(
                {
                    "dictionary_article_id": rel.dictionary_article_id,
                    "dictionary_title": rel.dictionary_title,
                    "match_method": rel.match_method,
                    "match_confidence": rel.match_confidence,
                    "mapping_method": rel.mapping_method,
                }
            )
    return grouped


def _write_metadata(
    connection: sqlite3.Connection,
    *,
    upstream_commit: str,
    content_hash: str,
    entity_count: int,
    import_mode: str,
    unresolved_count: int,
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source_id": ACAI_SOURCE_ID,
        "source_version": ACAI_RELEASE_VERSION,
        "upstream_commit": upstream_commit,
        "upstream_repository": ACAI_UPSTREAM_REPO,
        "license": ACAI_LICENSE,
        "license_url": ACAI_LICENSE_URL,
        "attribution": ACAI_ATTRIBUTION,
        "content_hash": content_hash,
        "entity_count": str(entity_count),
        "import_mode": import_mode,
        "unresolved_crosswalk_count": str(unresolved_count),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    for key, value in payload.items():
        connection.execute(
            "INSERT INTO store_metadata (key, value) VALUES (?, ?)",
            (key, value),
        )


def _hash_entity_payload(entities: list[KBEntity]) -> str:
    payload = json.dumps([entity.to_dict() for entity in entities], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    upstream = None
    output = None
    mode = "full"
    i = 0
    while i < len(args):
        if args[i] == "--upstream" and i + 1 < len(args):
            upstream = args[i + 1]
            i += 2
            continue
        if args[i] == "--output" and i + 1 < len(args):
            output = args[i + 1]
            i += 2
            continue
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]
            i += 2
            continue
        i += 1

    result = import_acai_sqlite(upstream_root=upstream, database_path=output, mode=mode)
    validation = validate_acai_database(result.database_path)
    print(json.dumps({**result.to_dict(), "validation": validation.to_dict()}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
