"""Reproducible pilot importer for ACAI entity graph (John 4:1-42)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.entity_models import (
    MAPPING_EXTERNAL_ID,
    MAPPING_EXPLICIT,
    MAPPING_UNRESOLVED,
    MAPPING_VERIFIED_EXACT_MATCH,
    RELATION_DICTIONARY_ASSOCIATION,
    RELATION_PASSAGE_MENTION,
    EntityAlias,
    EntityDictionaryRelation,
    EntityPassageRelation,
    KBEntity,
    PlaceCrosswalk,
    textus_entity_id_from_acai,
)
from textus_kb.importers.aquifer_bible_dictionary import (
    DEFAULT_OUTPUT_PATH as DICTIONARY_BUNDLE_PATH,
    load_pilot_bundle as load_dictionary_bundle,
)
from textus_kb.paths import PROJECT_ROOT

ACAI_SOURCE_ID = "acai"
ACAI_LICENSE = "CC-BY-SA-4.0"
ACAI_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
ACAI_ATTRIBUTION = "ACAI (Aquifer Concept Architecture for Information) © 2025 Mission Mutual. Licensed under CC BY-SA 4.0."
ACAI_UPSTREAM_REPO = "https://github.com/BibleAquifer/ACAI"
ACAI_RELEASE_VERSION = "2025-07-23"
DEFAULT_UPSTREAM_PATH = PROJECT_ROOT / "_upstream_audit" / "ACAI"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "kb" / "acai" / "john_4_1_42_entities.json"
UPSTREAM_ENV_VAR = "TEXTUS_ACAI_UPSTREAM_PATH"

PILOT_CANONICAL = "John.4.1-42"
JOHN_4_INDEX_LO = 43004001
JOHN_4_INDEX_HI = 43004042

# Jn 4 pilot place IDs from Textus passage-place links within the pilot span.
PILOT_TEXTUS_PLACE_IDS = frozenset(
    {
        "sychar",
        "samaria_2",
        "galilee_1",
        "judea_1",
        "mount_gerizim",
        "jerusalem",
    }
)

# Generic ACAI placeholders excluded from context summaries (still in bundle for audit).
GENERIC_ACAI_IDS = frozenset(
    {
        "person:GenericFemale",
        "person:GenericPerson",
        "person:GenericMale",
        "group:GenericGroup",
        "group:GenericDisciples",
    }
)

ACAI_TYPE_FOLDERS = {
    "person": "people",
    "place": "places",
    "group": "groups",
    "deity": "deities",
    "realia": "realia",
    "fauna": "fauna",
    "flora": "flora",
    "keyterm": "keyterms",
}

PASSAGE_ENTITY_TYPES = frozenset({"person", "place", "group"})


@dataclass
class ImportIssue:
    level: str
    message: str
    entity_id: str | None = None


@dataclass
class PilotImportResult:
    output_path: Path
    entity_count: int
    issues: list[ImportIssue]
    upstream_commit: str
    upstream_resource_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "entity_count": self.entity_count,
            "issues": [asdict(issue) for issue in self.issues],
            "upstream_commit": self.upstream_commit,
            "upstream_resource_version": self.upstream_resource_version,
        }


def resolve_upstream_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env = os.environ.get(UPSTREAM_ENV_VAR, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_UPSTREAM_PATH.resolve()


def read_upstream_commit(upstream_root: Path) -> str:
    git_head = upstream_root / ".git" / "refs" / "heads" / "main"
    if git_head.is_file():
        return git_head.read_text(encoding="utf-8").strip()
    return "unknown"


def import_john_4_pilot(
    *,
    upstream_root: str | Path | None = None,
    output_path: str | Path | None = None,
    dictionary_bundle_path: str | Path | None = None,
    places_catalog_path: str | Path | None = None,
) -> PilotImportResult:
    root = resolve_upstream_path(upstream_root)
    out = Path(output_path) if output_path is not None else DEFAULT_OUTPUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)

    dict_bundle_path = Path(dictionary_bundle_path) if dictionary_bundle_path else DICTIONARY_BUNDLE_PATH
    catalog_path = (
        Path(places_catalog_path)
        if places_catalog_path is not None
        else PROJECT_ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
    )

    issues: list[ImportIssue] = []
    upstream_commit = read_upstream_commit(root)

    passage_ids = _scan_passage_entity_ids(root)
    dictionary_links = _collect_dictionary_acai_links(root, dict_bundle_path, issues)
    dictionary_ids = {link["acai_id"] for link in dictionary_links}

    selected_ids = sorted(passage_ids | dictionary_ids)
    catalog_places = _load_catalog_places(catalog_path)
    crosswalk_index = _build_crosswalk_index(catalog_places)

    entities_by_external: dict[str, KBEntity] = {}
    primary_groups: dict[str, set[str]] = {}
    for acai_id in selected_ids:
        record = _load_acai_record(root, acai_id)
        if record is None:
            issues.append(ImportIssue("warning", f"ACAI record missing for {acai_id}", acai_id))
            continue
        primary_id = str(record.get("primary_id") or record.get("id") or acai_id)
        primary_groups.setdefault(primary_id, set()).add(acai_id)

    for primary_id, alias_ids in sorted(primary_groups.items()):
        primary_record = _load_acai_record(root, primary_id)
        if primary_record is None:
            alias_record = _load_acai_record(root, sorted(alias_ids)[0])
            if alias_record is None:
                continue
            primary_record = alias_record
            primary_id = str(primary_record.get("primary_id") or primary_record.get("id"))

        alias_links = [
            link for link in dictionary_links if link["acai_id"] in alias_ids or link["acai_id"] == primary_id
        ]
        entity = _normalize_entity(
            primary_record,
            upstream_commit=upstream_commit,
            dictionary_links=alias_links,
            crosswalk_index=crosswalk_index,
            catalog_places=catalog_places,
        )
        entities_by_external[primary_id] = entity

    entities = sorted(entities_by_external.values(), key=lambda item: item.entity_id)
    unresolved_crosswalks = _collect_unresolved_crosswalks(catalog_places, entities, crosswalk_index)

    bundle = {
        "bundle_version": "1",
        "pilot_scope": PILOT_CANONICAL,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_id": ACAI_SOURCE_ID,
        "upstream_repository": ACAI_UPSTREAM_REPO,
        "upstream_commit": upstream_commit,
        "upstream_resource_version": ACAI_RELEASE_VERSION,
        "license": ACAI_LICENSE,
        "license_url": ACAI_LICENSE_URL,
        "attribution": ACAI_ATTRIBUTION,
        "content_hash": _hash_entities(entities),
        "import_issues": [asdict(issue) for issue in issues],
        "pilot_report": _build_pilot_report(entities, unresolved_crosswalks),
        "entities": [entity.to_dict() for entity in entities],
        "unresolved_crosswalks": unresolved_crosswalks,
    }
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return PilotImportResult(
        output_path=out,
        entity_count=len(entities),
        issues=issues,
        upstream_commit=upstream_commit,
        upstream_resource_version=ACAI_RELEASE_VERSION,
    )


def load_pilot_bundle(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_OUTPUT_PATH
    if not target.is_file():
        raise FileNotFoundError(f"ACAI pilot bundle missing: {target}")
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("ACAI pilot bundle root must be an object.")
    return raw


def _scan_passage_entity_ids(root: Path) -> set[str]:
    selected: set[str] = set()
    for folder in ("people", "places", "groups"):
        json_dir = root / folder / "json"
        if not json_dir.is_dir():
            continue
        for path in json_dir.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            entity_type = str(record.get("type") or "").strip()
            if entity_type not in PASSAGE_ENTITY_TYPES:
                continue
            if _record_has_john4_reference(record):
                selected.add(str(record.get("id") or ""))
    return {item for item in selected if item}


def _collect_dictionary_acai_links(
    root: Path,
    dictionary_bundle_path: Path,
    issues: list[ImportIssue],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    if not dictionary_bundle_path.is_file():
        issues.append(ImportIssue("warning", f"Dictionary pilot bundle missing: {dictionary_bundle_path}"))
        return links

    dict_bundle = load_dictionary_bundle(dictionary_bundle_path)
    dict_dir = PROJECT_ROOT / "_upstream_audit" / "AquiferOpenBibleDictionary" / "eng" / "json"
    article_index: dict[str, dict[str, Any]] = {}
    if dict_dir.is_dir():
        for path in dict_dir.glob("*.content.json"):
            for article in json.loads(path.read_text(encoding="utf-8")):
                article_index[str(article.get("content_id") or "")] = article

    for entry in dict_bundle.get("entries", []):
        if not isinstance(entry, dict):
            continue
        article_id = str(entry.get("article_id") or "")
        title = str(entry.get("title") or "")
        article = article_index.get(article_id, {})
        for assoc in article.get("associations", {}).get("acai", []):
            if not isinstance(assoc, dict):
                continue
            acai_id = str(assoc.get("id") or "").strip()
            if not acai_id:
                continue
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


def _load_acai_record(root: Path, acai_id: str) -> dict[str, Any] | None:
    if ":" not in acai_id:
        return None
    entity_type, slug = acai_id.split(":", 1)
    folder = ACAI_TYPE_FOLDERS.get(entity_type)
    if folder is None:
        return None
    path = root / folder / "json" / f"{slug}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_entity(
    record: dict[str, Any],
    *,
    upstream_commit: str,
    dictionary_links: list[dict[str, Any]],
    crosswalk_index: dict[str, dict[str, Any]],
    catalog_places: dict[str, dict[str, Any]],
) -> KBEntity:
    external_id = str(record.get("id") or "")
    entity_type = str(record.get("type") or external_id.split(":", 1)[0])
    canonical_name = _preferred_label(record)
    aliases = _collect_aliases(record)
    upstream_refs = tuple(sorted(_collect_john4_refs(record)))

    passage_relations: list[EntityPassageRelation] = []
    if upstream_refs:
        passage_relations.append(
            EntityPassageRelation(
                canonical_passage=PILOT_CANONICAL,
                relation_type=RELATION_PASSAGE_MENTION,
                source_id=ACAI_SOURCE_ID,
                upstream_refs=upstream_refs,
                mapping_method=MAPPING_EXPLICIT,
                confidence=MAPPING_EXPLICIT,
            )
        )

    dictionary_relations = tuple(
        EntityDictionaryRelation(
            dictionary_article_id=str(link["dictionary_article_id"]),
            dictionary_title=str(link["dictionary_title"]),
            acai_id=external_id,
            match_method=str(link["match_method"]),
            match_confidence=_safe_float(link.get("match_confidence")),
            source_id=ACAI_SOURCE_ID,
            mapping_method=MAPPING_EXPLICIT,
        )
        for link in dictionary_links
    )

    place_crosswalk = None
    if entity_type == "place":
        place_crosswalk = _resolve_place_crosswalk(
            record,
            external_id,
            canonical_name,
            crosswalk_index,
            catalog_places,
            has_passage_link=bool(upstream_refs),
        )

    metadata = {
        "primary_id": str(record.get("primary_id") or external_id),
        "referred_to_as": list(record.get("referred_to_as") or []),
        "alternate_sources": dict(record.get("alternate_sources") or {}),
        "is_generic": external_id in GENERIC_ACAI_IDS,
    }
    if record.get("lemmas"):
        metadata["lemmas"] = dict(record.get("lemmas") or {})

    provenance = {
        "source_id": ACAI_SOURCE_ID,
        "external_id": external_id,
        "upstream_commit": upstream_commit,
        "upstream_resource_version": ACAI_RELEASE_VERSION,
        "license": ACAI_LICENSE,
        "license_url": ACAI_LICENSE_URL,
        "attribution": ACAI_ATTRIBUTION,
    }

    return KBEntity(
        entity_id=textus_entity_id_from_acai(external_id),
        entity_type=entity_type,
        canonical_name=canonical_name,
        source_id=ACAI_SOURCE_ID,
        external_id=external_id,
        aliases=aliases,
        metadata=metadata,
        provenance=provenance,
        passage_relations=tuple(passage_relations),
        dictionary_relations=dictionary_relations,
        place_crosswalk=place_crosswalk,
    )


def _preferred_label(record: dict[str, Any]) -> str:
    localizations = record.get("localizations") or {}
    eng = localizations.get("eng") or {}
    label = eng.get("preferred_label")
    if label:
        return str(label)
    return str(record.get("id") or "Unknown")


def _collect_aliases(record: dict[str, Any]) -> tuple[EntityAlias, ...]:
    aliases: list[EntityAlias] = []
    localizations = record.get("localizations") or {}
    for language, payload in localizations.items():
        if not isinstance(payload, dict):
            continue
        label = payload.get("preferred_label")
        if label:
            aliases.append(
                EntityAlias(label=str(label), language=str(language), source="acai_localization")
            )
    for referred_id in record.get("referred_to_as") or []:
        aliases.append(
            EntityAlias(label=str(referred_id), language="en", source="acai_referred_to_as")
        )
    lemmas = record.get("lemmas") or {}
    for language, values in lemmas.items():
        if not isinstance(values, list):
            continue
        for lemma in values:
            aliases.append(
                EntityAlias(label=str(lemma), language=str(language), source="acai_lemma")
            )
    # Stable dedupe
    seen: set[tuple[str, str, str]] = set()
    unique: list[EntityAlias] = []
    for alias in aliases:
        key = (alias.label, alias.language, alias.source)
        if key in seen:
            continue
        seen.add(key)
        unique.append(alias)
    unique.sort(key=lambda item: (item.language, item.label, item.source))
    return tuple(unique)


def _collect_john4_refs(record: dict[str, Any]) -> set[str]:
    return {ref for ref in _collect_org_refs(record) if _is_john4_org_ref(ref)}


def _collect_org_refs(record: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("references", "key_references"):
        block = record.get(key)
        if isinstance(block, list):
            for item in block:
                ref = _normalize_org_ref(str(item))
                if ref is not None:
                    refs.add(ref)
    for key in ("explicit_instances", "pronominal_referents", "subject_referents"):
        block = record.get(key)
        if isinstance(block, dict):
            for items in block.values():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, list):
                            for sub in item:
                                ref = _normalize_org_ref(str(sub))
                                if ref is not None:
                                    refs.add(ref)
                        else:
                            ref = _normalize_org_ref(str(item))
                            if ref is not None:
                                refs.add(ref)
    return refs


def _is_john4_org_ref(ref: str) -> bool:
    if len(ref) != 8 or not ref.isdigit():
        return False
    value = int(ref)
    return JOHN_4_INDEX_LO <= value <= JOHN_4_INDEX_HI


def _normalize_org_ref(raw: str) -> str | None:
    digits = "".join(ch for ch in raw if ch.isdigit())
    for idx in range(max(0, len(digits) - 7)):
        chunk = digits[idx : idx + 8]
        if chunk.isdigit():
            return chunk
    return None


def _record_has_john4_reference(record: dict[str, Any]) -> bool:
    return bool(_collect_john4_refs(record))


def _load_catalog_places(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    places = raw if isinstance(raw, list) else raw.get("places") or []
    return {
        str(place.get("place_id")): place
        for place in places
        if isinstance(place, dict) and place.get("place_id")
    }


def _build_crosswalk_index(catalog_places: dict[str, dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for place_id, place in catalog_places.items():
        obi = place.get("openbible_id")
        if obi:
            index[str(obi)] = place_id
    return index


def _resolve_place_crosswalk(
    record: dict[str, Any],
    external_id: str,
    canonical_name: str,
    crosswalk_index: dict[str, str],
    catalog_places: dict[str, dict[str, Any]],
    *,
    has_passage_link: bool,
) -> PlaceCrosswalk | None:
    obi_ids = (record.get("alternate_sources") or {}).get("obi") or []
    for obi in obi_ids:
        textus_place_id = crosswalk_index.get(str(obi))
        if textus_place_id and textus_place_id in PILOT_TEXTUS_PLACE_IDS:
            place = catalog_places[textus_place_id]
            return PlaceCrosswalk(
                textus_place_id=textus_place_id,
                acai_entity_id=external_id,
                openbible_id=str(obi),
                pleiades_id=place.get("pleiades_id"),
                canonical_name=str(place.get("name_en") or canonical_name),
                mapping_method=MAPPING_EXTERNAL_ID,
                confidence=MAPPING_EXTERNAL_ID,
            )

    normalized_acai = _normalize_name(canonical_name)
    candidates = [
        place_id
        for place_id in PILOT_TEXTUS_PLACE_IDS
        if _normalize_name(str(catalog_places.get(place_id, {}).get("name_en") or "")) == normalized_acai
        or _normalize_name(str(catalog_places.get(place_id, {}).get("name_hu") or "")) == normalized_acai
    ]
    if len(candidates) == 1 and has_passage_link:
        place_id = candidates[0]
        place = catalog_places[place_id]
        return PlaceCrosswalk(
            textus_place_id=place_id,
            acai_entity_id=external_id,
            openbible_id=place.get("openbible_id"),
            pleiades_id=place.get("pleiades_id"),
            canonical_name=str(place.get("name_en") or canonical_name),
            mapping_method=MAPPING_VERIFIED_EXACT_MATCH,
            confidence=MAPPING_VERIFIED_EXACT_MATCH,
        )
    return None


def _collect_unresolved_crosswalks(
    catalog_places: dict[str, dict[str, Any]],
    entities: list[KBEntity],
    crosswalk_index: dict[str, str],
) -> list[dict[str, Any]]:
    linked = {
        crosswalk.textus_place_id
        for entity in entities
        if entity.place_crosswalk is not None
        for crosswalk in [entity.place_crosswalk]
    }
    unresolved: list[dict[str, Any]] = []
    for place_id in sorted(PILOT_TEXTUS_PLACE_IDS):
        if place_id in linked:
            continue
        place = catalog_places.get(place_id, {})
        unresolved.append(
            {
                "textus_place_id": place_id,
                "name_en": place.get("name_en"),
                "openbible_id": place.get("openbible_id"),
                "confidence": MAPPING_UNRESOLVED,
                "reason": "no_explicit_acai_external_id_or_verified_exact_match",
            }
        )
    return unresolved


def _build_pilot_report(
    entities: list[KBEntity],
    unresolved_crosswalks: list[dict[str, Any]],
) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    passage_linked = 0
    dictionary_linked = 0
    crosswalks = 0
    for entity in entities:
        by_type[entity.entity_type] = by_type.get(entity.entity_type, 0) + 1
        if entity.passage_relations:
            passage_linked += 1
        if entity.dictionary_relations:
            dictionary_linked += 1
        if entity.place_crosswalk is not None:
            crosswalks += 1
    return {
        "entity_count": len(entities),
        "entities_by_type": by_type,
        "passage_linked_entities": passage_linked,
        "dictionary_linked_entities": dictionary_linked,
        "confirmed_place_crosswalks": crosswalks,
        "unresolved_place_crosswalks": len(unresolved_crosswalks),
        "generic_entity_ids": sorted(
            entity.external_id for entity in entities if entity.metadata.get("is_generic")
        ),
    }


def _normalize_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return " ".join(cleaned.split())


def _hash_entities(entities: list[KBEntity]) -> str:
    payload = json.dumps([entity.to_dict() for entity in entities], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    upstream = None
    output = None
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
        i += 1

    result = import_john_4_pilot(upstream_root=upstream, output_path=output)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
