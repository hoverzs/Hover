# TEXTUS Knowledge Base — Phase 4D

Phase 4D replaces Aquifer **pilot JSON bundles** as the runtime primary source with **full English-corpus SQLite stores** for Study Notes and Bible Dictionary. Pilot bundles remain for regression, parity, and offline fallback.

Build ID: `kb-phase4d-aquifer-sqlite-v1`

## Upstream audit (English `eng`)

Measured via `scripts/audit_aquifer_upstream.py` against upstream JSON clones:

| Source | Raw articles | Content size | Passage links | Other |
|--------|-------------:|-------------:|--------------:|-------|
| Study Notes | 16,923 | ~25.7 MB | 16,932 | 66 books |
| Bible Dictionary | 6,120 index refs (6,071 unique) | ~19.7 MB | 43,405 | 7,075 ACAI links |

## SQLite stores (imported)

| Store | Path | Articles | Chunks | Passage links | ACAI links | File size |
|-------|------|----------|--------|---------------|------------|-----------|
| Study Notes | `data/generated/aquifer_study_notes.sqlite3` | 16,601 | 16,805 | 16,601 | — | ~28.1 MB |
| Bible Dictionary | `data/generated/aquifer_bible_dictionary.sqlite3` | 6,071 | 14,043 | 43,389 | 7,034 | ~47.8 MB |

Import is idempotent, checksum-aware, and records upstream commit + `source_version` 1.1.2 in `store_metadata`.

Typical full import time (local): Study Notes ~2.8 s, Dictionary ~2.0 s.

### Study Notes schema (`schema_version` 1)

- `store_metadata` — provenance, counts, content hash
- `study_articles` — article ID, title, original HTML, language, source version
- `study_passage_links` — article ID, canonical passage, org start/end refs, relation type
- `study_chunks` — chunk ID, article ID, ordinal, content, heading, token metadata

Indexes: article ID, passage org refs, book/chapter slice, chunk/article relation.

### Dictionary schema (`schema_version` 1)

- `store_metadata`
- `dictionary_articles` — content ID, title, original content, provenance
- `dictionary_chunks` — chunk ID, article ID, heading, content, ordinal
- `dictionary_passage_links` — article ID, canonical reference, org bounds
- `dictionary_acai_links` — article ID, ACAI entity ID, match method, confidence

Indexes: article ID, normalized title, passage org refs, ACAI entity ID.

ACAI SQLite (`data/generated/acai_entities.sqlite3`) remains separate.

## Import pipeline

```bash
PYTHONPATH=. python -m textus_kb.importers.aquifer_study_notes_sqlite
PYTHONPATH=. python -m textus_kb.importers.aquifer_bible_dictionary_sqlite
```

Importers: `textus_kb/importers/aquifer_study_notes_sqlite.py`, `textus_kb/importers/aquifer_bible_dictionary_sqlite.py`

Repositories (read-only): `textus_kb/repositories/aquifer_study_notes_repository.py`, `textus_kb/repositories/aquifer_dictionary_repository.py`

Manifest entries point to `.sqlite3` paths with `source_type: sqlite`.

## Runtime retrieval flow

```
CanonicalReference
  → SQLite passage lookup (org-ref overlap + same-book filter)
  → Study Notes candidates (limit 24)
  → Dictionary candidates (limit 48 direct)
  → ACAI entities (pilot JSON / ACAI SQLite)
  → Entity-expanded Dictionary (limit 24)
  → Evidence Packet
  → Context Selection
```

Pilot registry is **not required** for passage retrieval. It remains for lexical seeds, ACAI JSON paths, and bundle parity.

Adapters use SQLite when the store exists; JSON pilot bundles are fallback only.

Stable evidence IDs when SQLite is active: `EV-DICT-{chunk_id}`, `EV-SN-{chunk_id}`.

## Parity: SQLite vs pilot bundles

### John 4 (`John.4.1-42`)

| Metric | Pilot | SQLite |
|--------|------:|-------:|
| Study Notes article IDs | 24 | 24 (exact match) |
| Dictionary article IDs | 12 | 34 passage-linked |

Dictionary delta: 5 pilot-only articles (`5354`, `6163`, `6487`, `8120`, `8782`) were included in the Phase 4B pilot via index-reference / entity-topic seeds, not passage links alone. SQLite adds 27 additional passage-linked articles beyond the pilot subset. All pilot Study Notes IDs are present in SQLite.

### Luke 10 (`Luke.10.25-37`)

| Metric | Pilot | SQLite |
|--------|------:|-------:|
| Study Notes article IDs | 10 | 10 (exact match) |
| Dictionary article IDs | 10 | 24 passage-linked |

Dictionary delta: 5 pilot-only articles (`6333`, `6731`, `6786`, `8120`, `8915`) from pilot seeds; 19 extra passage-linked articles in SQLite.

Chunk IDs unchanged: `{article_id}-c{index:03d}`.

## Third passage (no pilot registry)

`Acts.2.1-13` — not in pilot registry; retrieval works without special logic:

- 6 Study Notes, 48 Dictionary (direct), 0 ACAI entities
- Exegesis ~3,037 tokens, Historical ~2,386 tokens

## No-data passage (graceful)

`3John.1.15` — Study Notes present (2), Dictionary empty:

- Warning: dictionary no data for passage
- No exception; linguistic layers still build
- Exegesis ~926 tokens

## Entity expansion (full corpus)

With full Dictionary SQLite, entity-expanded unique dictionary candidates increase vs Phase 4B pilot scope:

| Passage | Direct dict | Entity-expanded unique |
|---------|------------:|-----------------------:|
| John 4 | 48 | 36 |
| Luke 10 | 48 | 30 |
| Acts 2 | 48 | 0 |

Direct Aquifer retrieval is not artificially boosted; diagnostics report direct / entity-expanded / duplicate counts separately.

## Performance (local smoke)

| Passage | SN query | Dict query | Full retrieve | Context (exegesis) |
|---------|--------:|-----------:|--------------:|-------------------:|
| John 4 | ~5 ms | ~29 ms | ~1.6 s | ~82 ms |
| Luke 10 | ~2 ms | ~16 ms | ~0.3 s | ~56 ms |
| Acts 2 | ~2 ms | ~24 ms | ~0.3 s | ~42 ms |

Full retrieval dominated by existing TAGNT / lexicon / places layers.

## Context token budgets

| Passage | Exegesis | Historical | Max |
|---------|--------:|-----------:|----:|
| John 4 | 3,163 | 2,475 | 4,500 / 3,500 |
| Luke 10 | 3,176 | 2,235 | ✓ |
| Acts 2 | 3,037 | 2,386 | ✓ |

Context builder uses compact dictionary metadata (`passage_linked` flag) so token estimation is not inflated by full passage-association audit lists.

## Health check

`run_health_check()` adds:

- `aquifer_study_notes_store` — available, schema version, source version, article/passage counts
- `aquifer_dictionary_store` — available, schema version, article/chunk/passage/ACAI counts

Missing optional sources degrade with warnings, not exceptions.

## Licensing / provenance

All evidence and store metadata retain:

- `source_id`, `source_version`, `upstream_commit`, `upstream_repository`
- CC BY-SA 4.0 license + attribution strings
- Original English HTML/content preserved in SQLite

## Remaining pilot dependencies

| Dependency | Purpose |
|------------|---------|
| Pilot registry | Lexical seeds, ACAI JSON paths, bundle parity |
| Pilot JSON bundles | Regression fixtures, offline fallback |
| ACAI pilot JSON / SQLite | Entity summaries (not full ACAI corpus SQLite yet) |

Normal Aquifer retrieval **does not** require passage-specific bundles.

## Tests

205 KB tests green, including Phase 4D suite (`tests/test_textus_kb/test_phase4d_aquifer_sqlite.py`):

- Full importers, idempotency, schema/indexes
- Jn 4 / Lk 10 parity, Acts 2 without registry
- No-data graceful, stable evidence IDs, candidate limits
- Context budgets, health, prior phase regressions

## Suggested next phase (not started)

**Phase 4E** — Full ACAI SQLite runtime beyond John pilot store; passage-scoped entity summaries without JSON bundles.
