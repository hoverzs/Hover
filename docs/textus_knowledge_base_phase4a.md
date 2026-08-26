# TEXTUS Knowledge Base — Phase 4A (ACAI Entity Linking)

Phase 4A adds a structured **entity layer** for the John 4:1–42 pilot using upstream **ACAI** (Aquifer Concept Architecture for Information) data and Aquifer Bible Dictionary `associations.acai` metadata.

No LLM, embedding, graph database, or production integration in this phase.

## ACAI upstream schema

Repository: `https://github.com/BibleAquifer/ACAI`  
Release: `2025-07-23`  
Commit (pilot clone): `7e6a2d6674910aedb0888493ebbe6684d374ae5c`

Entity types (top-level folders):

| Folder | ACAI type prefix | Example ID |
|--------|------------------|------------|
| `people/json/` | `person` | `person:Jesus.2` |
| `places/json/` | `place` | `place:Sychar` |
| `groups/json/` | `group` | `group:Samaritan` |
| `deities/json/` | `deity` | `deity:God` |
| `realia/json/` | `realia` | `realia:Temple` |
| `fauna/json/` | `fauna` | … |
| `flora/json/` | `flora` | … |
| `keyterms/json/` | `keyterm` | `keyterm:Worship` |

Core record fields: `id`, `primary_id`, `type`, `localizations` (preferred_label, descriptions, alternate_labels), `referred_to_as`, `alternate_sources`, `references` / `key_references` (ORG versification `BBCCCVVV`), `explicit_instances` (edition → word-level refs).

Versification: Copenhagen Alliance **ORG** scheme (HB/NT native numbering). John 4 pilot span = `43004001`–`43004042`.

License: **CC BY-SA 4.0** (Mission Mutual © 2025).

## Dictionary → ACAI link format

Aquifer Open Bible Dictionary articles expose:

```json
{
  "id": "place:Sychar",
  "type": "place",
  "confidence": 1.0,
  "match_method": "content_id",
  "preferred_label": "Sychar"
}
```

Phase 4A uses these upstream associations directly (no string matching primary path).

## Textus entity ID strategy

| Field | Rule |
|-------|------|
| `external_id` | ACAI canonical ID unchanged, e.g. `place:Sychar` |
| `entity_id` | Deterministic Textus slug: `acai-{type}-{slug}` → `acai-place-Sychar` |
| Duplicate ACAI aliases | Merged to `primary_id` record |

## Entity model

See `textus_kb/entity_models.py`:

- `KBEntity` with `entity_id`, `entity_type`, `canonical_name`, `external_ids.acai`, `aliases`, `passage_relations`, `dictionary_relations`, `place_crosswalk`, `provenance`.

Confidence / mapping methods (no synthetic percentages):

- `explicit` — upstream passage or dictionary association
- `external_id` — OpenBible `obi` ID match
- `verified_exact_match` — reserved for exact canonical name + passage co-evidence
- `unresolved` — documented but not auto-linked

## Passage linking

Importer scans ACAI `people`, `places`, `groups` for ORG refs in John 4:1–42.

Query: `AcaiEntitiesAdapter.entities_for_passage(CanonicalReference.parse("John.4.1-42"))`

## Place crosswalk (Jn 4 pilot)

Priority:

1. ACAI `alternate_sources.obi` == Textus catalog `openbible_id`
2. Verified exact canonical match with passage co-evidence
3. Otherwise → `unresolved_crosswalks` (not auto-linked)

| Textus place ID | ACAI entity | Method |
|-----------------|-------------|--------|
| `sychar` | `place:Sychar` | external_id (`a27b472`) |
| `mount_gerizim` | `place:GerizimMount` | external_id (`a30e967`) |
| `jerusalem` | `place:Jerusalem` | external_id (`a15257a`) |
| `galilee_1` | — | unresolved |
| `judea_1` | — | unresolved |
| `samaria_2` | — | unresolved |

ACAI `place:Galilee` / `place:Judea` / `place:Samaria` exist with Jn 4 refs but catalog names (`Galilee 1`, etc.) prevent verified exact match without documented ID bridge.

## Jn 4 pilot statistics

| Metric | Value |
|--------|-------|
| Total entities | **30** |
| By type | place 9, person 10, group 8, keyterm 2, realia 1 |
| Passage-linked | **23** |
| Dictionary-linked | **16** |
| Confirmed place crosswalks | **3** |
| Unresolved place crosswalks | **3** |
| Generic ACAI placeholders (flagged) | 4 |

Named passage-linked examples: Jesus (`person:Jesus.2`), Samaritans (`group:Samaritan`), Jacob (`person:Jacob.2` via dictionary), Sychar, Samaria, Galilee, Judea, Mount Gerizim, Jacob's Well.

No dedicated ACAI record for “Samaritan woman” as a named person — only `person:GenericFemale` (flagged generic).

## Evidence Packet integration

`EvidencePacket.entities` populated from `data/kb/acai/john_4_1_42_entities.json`.  
Build ID: `kb-phase4a-john4-pilot-v1`.

Entities are **not** prose EvidenceItems; they are a structured audit layer.

## Context Packet impact

Compact `entity_summary` lines (max 8 named, non-generic):

`Sychar — place — directly linked to Jn 4, dictionary-linked`

| Profile | Tokens (Phase 3C → 4A) | Entity items selected |
|---------|------------------------|------------------------|
| Exegesis | 3161 → **3161** | 0 (at soft target) |
| Historical | 2174 → **2291** | 2 |

Entity budget cap: **120 tokens** per profile.

## Retrieval expansion boundary (future)

Prepared path (not implemented):

```
passage → ACAI entities → dictionary articles (associations.acai) → historical sources
```

Phase 4A stores bidirectional dictionary↔entity links and passage relations; no entity-driven retrieval engine yet.

## Storage scaling

ACAI release: **~13k JSON files** across 8 entity types (~full graph).

Jn 4 pilot bundle: **30 entities**, ~120 KB JSON.

**Conclusion:** JSON pilot remains appropriate for single-passage scope. Full ACAI production use warrants **SQLite entity index** (by `external_id`, passage ref index, dictionary back-link) when multi-passage or runtime entity queries are needed — recommend Phase 4B/5.

## Files

- `textus_kb/entity_models.py`
- `textus_kb/importers/acai_entities.py`
- `textus_kb/adapters/acai_entities.py`
- `data/kb/acai/john_4_1_42_entities.json`
- `tests/test_textus_kb/test_acai_entities.py`

## Out of scope

No full ACAI corpus import, Neo4j, LLM entity matching, embeddings, Supabase, `app.py`, production prompts, Hungarian entity descriptions, UBS/Sefaria integration.
