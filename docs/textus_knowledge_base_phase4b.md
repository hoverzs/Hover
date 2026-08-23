# TEXTUS Knowledge Base — Phase 4B

Phase 4B replaces the Phase 4A JSON runtime with a read-only SQLite ACAI entity store and adds deterministic entity-driven dictionary retrieval expansion.

## SQLite schema

Runtime schema version: `1` (`textus_kb/importers/acai_sqlite.py`).

| Table | Purpose |
|-------|---------|
| `entities` | Internal ID, ACAI external ID, type, canonical name, metadata/provenance JSON, optional place crosswalk JSON |
| `entity_aliases` | Entity ID, language, alias label, alias type |
| `entity_passage_links` | Entity ID, 8-digit org ref, canonical passage, relation type, mapping method, confidence |
| `entity_external_ids` | Entity ID, namespace, external ID (incl. verified OpenBible `obi` IDs) |
| `entity_dictionary_links` | Entity ID, dictionary article ID, match method/confidence, mapping method |
| `store_metadata` | Schema/source version, upstream commit, content hash, import mode |

Indexes: ACAI external ID, entity type, canonical name, org ref, canonical passage, external ID namespace, dictionary article ID.

## Import size and time

| Mode | Path | Entities | Passage links | Dictionary links | Import time | File size |
|------|------|----------|---------------|------------------|-------------|-----------|
| **Pilot (runtime)** | `data/generated/acai_entities.sqlite3` | 30 | 92 | 17 | ~40 ms | ~196 KB |
| **Full corpus (measured)** | `data/generated/acai_entities_full.sqlite3` | 5,700 | 98,649 | 7,075 | ~7.0 s | ~28 MB |

**Decision:** Runtime manifest uses **pilot import** from the committed Phase 4A JSON bundle (`data/kb/acai/john_4_1_42_entities.json`) for Jn 4 parity. Full import is supported, measured, and reasonable for offline build pipelines; switching manifest `local_path` to the full DB is a one-line change when broader passage coverage is required.

Importer: `python -m textus_kb.importers.acai_sqlite --mode pilot|full [--output PATH]`

Properties: deterministic, idempotent (DELETE + rebuild), checksum-aware, upstream read-only.

## Repository API

`textus_kb/repositories/acai_entity_repository.py` — read-only URI mode.

| Method | Description |
|--------|-------------|
| `entity_by_id(entity_id)` | Single entity with aliases, passage/dictionary relations |
| `entities_for_passage(canonical_ref)` | Entities with org-ref overlap |
| `entities_by_type(entity_type)` | Filter by ACAI type |
| `dictionary_articles_for_entity(entity_id)` | Linked dictionary article IDs |
| `external_ids_for_entity(entity_id)` | Namespaced external IDs |
| `entities_for_dictionary_article(article_id)` | Reverse lookup |
| `entities_for_evidence_packet(reference)` | Pilot store → all entities; full store → passage-scoped |
| `store_status()` | Health/diagnostic metadata |

Adapter: `AcaiEntitiesAdapter` uses SQLite when manifest path is `.sqlite3`; JSON pilot bundle remains for parity testing.

## Parity (JSON ↔ SQLite)

Jn 4 pilot: **30/30 entity IDs match** between `data/kb/acai/john_4_1_42_entities.json` and `data/generated/acai_entities.sqlite3`.

Verified place crosswalks unchanged: Sychar, Mount Gerizim, Jerusalem (OpenBible external ID).

Unresolved (not auto-linked): `galilee_1`, `judea_1`, `samaria_2`.

## Entity-driven expansion

Flow (`textus_kb/entity_expansion.py`):

```
canonical passage → ACAI entities → dictionary article IDs → dictionary chunks → evidence items
```

Primary links only (no string/fuzzy matching):

1. Explicit ACAI passage entity links
2. Explicit dictionary `associations.acai`
3. Verified place crosswalk (external ID)

**Priority order:** passage entity → passage+dictionary → verified crosswalk → indirect.

**Limits:**

| Limit | Value |
|-------|-------|
| Max entities used | 12 |
| Max dictionary candidates / entity | 3 |
| Max total expansion candidates | 40 |

Provenance on each expanded evidence item: `metadata.entity_expansion` chain from passage → entity → dictionary article/chunk → license/upstream.

Retrieval debug: `EvidencePacket.retrieval_debug.entity_expansion`.

### Jn 4 retrieval change

At Evidence Packet level, direct dictionary pilot selection (Phase 3C) already covers all 12 pilot dictionary articles linked to Jn 4 entities. Entity expansion adds **0 duplicate chunks** at integration time (correct dedupe). Isolated expansion (without direct candidates) yields **36 dictionary chunks** from entity links — used for diagnostics and full-corpus scaling.

Historical context profile benefits via higher selection specificity (`88`) for entity-expanded dictionary items vs exegesis (`55`), keeping study notes and lexical evidence primary in exegesis.

## Token impact (Jn 4)

| Profile | Tokens | Limit |
|---------|--------|-------|
| Exegesis | 3,168 | target 3200 / max 4500 |
| Historical | 2,311 | target 2500 / max 3500 |

Context selector source-aware budgets unchanged; entity summaries remain ~120 token budget type.

## Performance (Jn 4)

| Operation | Time |
|-----------|------|
| Entity lookup (passage) | ~1–3 ms |
| Entity expansion (isolated) | ~5–15 ms |
| Full retrieval | ~3–7 s (dominated by existing KB sources) |

SQLite runtime lookup is negligible vs total retrieval.

## Health check

`python -m textus_kb health` includes `acai_store`:

- store available, schema version, source version
- entity / passage-link / dictionary-link counts
- content hash, import mode
- graceful warning when optional store missing

## CLI

```bash
python -m textus_kb entity "Jn 4,1–42"
```

Reports entity counts/types/IDs, expansion diagnostics, timing, store status.

## Build ID

`kb-phase4b-john4-pilot-v1` when ACAI SQLite backend is active.

## Scaling conclusion

Full ACAI import (~5.7k entities, ~7 s, ~28 MB) is practical for batch build. Runtime passage queries use indexed org-ref lookups; full store defers evidence-packet entity lists to passage scope. Next phase can wire full store + broader dictionary corpus without architectural changes.

## Suggested next phase (not started)

**Phase 4C — Full-corpus runtime switch:** point manifest to full SQLite, expand Aquifer dictionary beyond Jn 4 pilot, add passage-scoped entity summaries, and measure context selection under multi-passage workloads.
