# TEXTUS Knowledge Base — Phase 4E

Phase 4E makes the **full ACAI SQLite store** the runtime primary source for entity retrieval. Passage-scoped lookup works for any canonical reference with org-ref data — no pilot JSON bundle required.

Build ID: `kb-phase4e-acai-full-runtime-v1`

## Full ACAI runtime

| Metric | Value |
|--------|------:|
| Entities | 5,700 |
| Passage links | 98,649 |
| Dictionary links | 7,075 |
| External IDs | 21,959 |
| SQLite size | ~35.2 MB |
| Import time | ~13 s |

Store path: `data/generated/acai_entities.sqlite3` (`import_mode: full`)

Importer: `python -m textus_kb.importers.acai_sqlite --mode full`

## Versification

Passage lookup uses shared org-ref bounds from `textus_kb.pilot_registry`:

```
ORG ref: BBCCCVVV (USFM book number + chapter + verse)
Canonical: {BookId}.{chapter}.{verse} via org_ref_to_canonical()
Query: entity_passage_links.org_ref BETWEEN passage_lo AND passage_hi
```

Supported for all 66 books where ACAI upstream stores org refs. Full retrieval (TAGNT linguistic layer) remains NT-only; OT ACAI lookup is validated at repository level (`Gen.1.1-5` → 2 deity entities).

**Limit:** No invented verse alignment — only explicit upstream org refs are indexed.

## Runtime flow

```
CanonicalReference
  → AcaiEntityRepository.entities_for_passage()
  → deterministic entity selection (limit 40)
  → Evidence Packet entities
  → entity → Dictionary expansion (Phase 4D SQLite)
  → Context Builder entity summaries (limit 8, budget 250/400 tokens)
```

Adapter: SQLite-first when `import_mode == "full"`. Pilot JSON bundles are regression/parity fallback only.

## Entity selection priority

1. Explicit passage occurrence (`passage_relations`)
2. Dictionary-linked entities (from retrieved dictionary articles)
3. person / place / group
4. supporting types (deity, realia, keyterm, fauna, flora)

Generic ACAI placeholders excluded from context summaries.

## Parity vs pilot JSON

### John 4

| Source | Count | Notes |
|--------|------:|-------|
| Pilot JSON bundle | 30 | Includes dictionary-seeded entities without John 4 org refs |
| Full SQLite passage lookup | 38 | Org-ref scoped only |
| Pilot org-ref entities in SQLite | 19/19 | All present with stable IDs |
| Selected for evidence packet | 38 | ≤ 40 limit |

Pilot-only entities (no org ref in John 4 range): e.g. `group:Galilee`, `keyterm:Worship`, `realia:Temple`.

### Luke 10

| Source | Count |
|--------|------:|
| Pilot JSON | 15 |
| Full SQLite passage | 24 |
| Org-ref pilot subset in SQLite | 100% |

## General passages (no pilot registry)

| Passage | Entities | Types (summary) |
|---------|--------:|-----------------|
| Acts.2.1-13 | 34 | 16 place, 9 group, … |
| Rom.8.28-30 | 7 | 5 keyterm, 1 person, 1 deity |
| Gen.1.1-5 (repo only) | 2 | deity |

## Entity expansion delta (sample)

| Passage | Direct dict | Unique entity-expanded |
|---------|------------:|-----------------------:|
| John 4 | 48 | 30 |
| Luke 10 | 48 | 40 |
| Acts 2 | 48 | 35 |
| Rom 8 | 48 | 24 |

## Context token impact

| Passage | Exegesis | Historical |
|---------|--------:|-----------:|
| John 4 | 3,151 | 2,524 |
| Luke 10 | 3,195 | 2,514 |
| Acts 2 | 3,194 | 2,537 |
| Rom 8 | 1,607 | 2,166 |

Entity budget: exegesis 250, historical 400 (within spec ranges).

## Performance (local smoke)

| Step | John 4 | Acts 2 | Rom 8 |
|------|-------:|-------:|------:|
| ACAI passage lookup | ~192 ms | ~117 ms | — |
| Full retrieval | ~2.4 s | ~1.0 s | ~0.8 s |
| Context build | ~91 ms | ~72 ms | ~35 ms |

## Crosswalk policy

Verified Phase 4A crosswalks preserved (OBI explicit ID only). Unresolved places **not** auto-linked:

- `galilee_1`
- `judea_1`
- `samaria_2`

## Health

`run_health_check().acai_store` reports: available, schema version, source version, upstream commit, entity/passage/dictionary/external counts, content hash, DB size.

Missing pilot JSON does **not** degrade health when `import_mode == full`.

## Remaining pilot dependencies

| Dependency | Purpose |
|------------|---------|
| Pilot registry | Lexical seeds, bundle paths for regression metadata |
| Pilot ACAI JSON | Parity/regression fixtures |
| Pilot Aquifer JSON | Offline fallback / golden tests |

Normal entity retrieval **does not** require pilot JSON or registry membership.

## Tests

219 KB tests green, including `tests/test_textus_kb/test_phase4e_acai_runtime.py`.

## Suggested next phase (not started)

**Phase 4F** — OT full retrieval path (TAHOT linguistic + passage-scoped context) or production KB integration behind feature flag.
