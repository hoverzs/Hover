# TEXTUS Knowledge Base — Phase 4C

Phase 4C proves the retrieval architecture is not John-4-specific by adding **Luke.10.25-37** as a second end-to-end pilot and introducing measurable **direct vs entity-expanded** retrieval modes.

## What changed from Phase 4B

### Pilot registry (`textus_kb/pilot_registry.py`)

Minimal config for supported passages — no plugin framework:

| Field | Purpose |
|-------|---------|
| `canonical` | Stable passage span |
| `usfm_book_num` / org index bounds | Aquifer + ACAI org-ref overlap |
| `lexical_seed` | Deterministic TBESG highlight tie-break |
| `dictionary_index_refs` | Upstream dictionary topic seeds |
| `study_notes_path` / `dictionary_path` / `acai_json_path` | Per-passage bundles |

Registered pilots: `john_4_1_42`, `luke_10_25_37`.

### Generalized (formerly Jn 4-only)

| Area | Before | After |
|------|--------|-------|
| Dictionary adapter | `_overlaps_john_4` gate | `find_pilot()` + registry bundle path |
| Study Notes adapter | Already span-based; manifest-only | Registry bundle path |
| ACAI adapter / repository | Book 43 only org refs | `org_ref_bounds()` for Luke (42) and John (43) |
| Importers | `import_john_4_pilot()` only | `import_*_pilot(pilot_id=...)` wrappers retained |
| Lexical seed | `JOHN_4_LEXICAL_SEED` hardcoded | Per-pilot seed from registry |
| Retrieval | Always entity-expanded | `entity_mode`: `direct_only` / `direct_plus_entities` |

## Health check (multi-pilot)

`run_health_check()` reports `pilot_registry`:

| Field | Meaning |
|-------|---------|
| `valid` | Registry config consistency |
| `pilot_count` | Number of configured pilots |
| `pilots[]` | Per-pilot Study Notes / Dictionary / ACAI JSON availability |

Only registered pilots are probed — not a full-Bible crawler.

## Luke 10 upstream statistics

| Source | Count |
|--------|------:|
| Study Notes articles | 10 |
| Study Notes chunks | 11 |
| Dictionary entries | 10 |
| Dictionary chunks | 146 |
| ACAI entities | 15 |
| Passage-linked ACAI entities | 11 |
| Dictionary-linked ACAI entities | 8 |

Entity types (Luke): person, place, group, keyterm (see `pilot_report` in JSON bundle).

Unresolved place crosswalks: none seeded for Luke pilot (`jerusalem`, `jericho`, `samaria_2` tracked; only explicit external-ID matches link).

## Retrieval modes

```python
retrieve("Lk 10,25-37", entity_mode="direct_only")
retrieve("Lk 10,25-37", entity_mode="direct_plus_entities")  # default
```

### Expansion delta (Phase 4C metric)

`EvidencePacket.retrieval_debug.expansion_delta`:

```json
{
  "direct_candidates": 171,
  "entity_candidates": 0,
  "duplicate_with_direct": 0,
  "unique_entity_candidates": 0,
  "unique_entity_selected": 0
}
```

**Interpretation for Luke 10:** integrated retrieval adds **zero unique entity-expanded dictionary chunks** because the Phase 4C dictionary pilot (index-reference seeds + passage associations) already includes every article reachable via explicit ACAI dictionary links. Isolated expansion (empty direct set) yields **30** entity-linked candidates — confirming the entity layer works, but direct Aquifer metadata subsumes it at integration time.

Same pattern as John 4 Phase 4B.

## Context tokens (Luke 10)

| Profile | Tokens | Budget max |
|---------|-------:|----------:|
| Exegesis | 3,138 | 4,500 |
| Historical | 2,209 | 3,500 |

Direct vs expanded Context token delta: **0** (no unique expansion evidence selected).

CLI comparison: `python -m textus_kb.retrieval_comparison "Lk 10,25-37"`

## John 4 regression

Unchanged build ID (`kb-phase4b-john4-pilot-v1`), 30 entities, token budgets, Study Notes, Dictionary, context selection.

## Performance (Luke 10, diagnostic)

| Step | ~Time |
|------|------:|
| Direct retrieval | ~3 s |
| Entity-expanded retrieval | ~3 s |
| Context build (each profile) | <1 s |

Dominated by existing TAGNT/lexicon/place layers; entity lookup remains negligible.

## Conclusion: entity expansion value

For Aquifer pilot scope with explicit `associations.passage` and `associations.acai` metadata, **entity-driven dictionary expansion does not add unique integrated evidence** — direct retrieval already covers the same articles/chunks. The entity layer remains valuable for:

- Provenance and audit (`passage → entity → dictionary article`)
- Isolated expansion when direct seeds are narrower
- Future non-Aquifer sources without rich passage metadata
- Full-corpus SQLite entity queries beyond pilot dictionary bundles

## Suggested next phase (not started)

**Phase 4D — Full dictionary runtime + passage-scoped entity summaries:** switch dictionary from per-passage JSON bundles to SQLite runtime; measure expansion delta when direct passage association is sparse.
