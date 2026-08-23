# TEXTUS Knowledge Base — Phase 3B (Source-aware context selection)

Phase 3B improves **LLM Context Packet** selection without adding sources or changing the audit-grade **Evidence Packet**.

## Problem (after Phase 3A)

Jn 4 exegesis context was ~**4480 / 4500** tokens with `truncated: true` because nearly all 24 Aquifer notes entered the context in score order.

## Solution overview

```
EvidencePacket (full, unchanged)
        │
        ▼
  candidate ContextItems
        │
        ▼
  context_selection.select_context_items()
        │  classify → dedup → coverage → type budgets → soft target → hard max
        ▼
  LLMContextPacket (schema_version: "2")
```

New module: `textus_kb/context_selection.py`  
Updated: `textus_kb/context_profiles.py`, `textus_kb/context_builder.py`

## Evidence classification (selection tiers)

Not a truth judgment — context priority only:

| Tier | Exegesis examples |
|------|-------------------|
| `core` | Passage identity, Greek coverage summary |
| `primary` | Lexical highlights, verse-specific Study Notes |
| `supporting` | Place links, catalog, mid-range notes |
| `optional` | Enrichment, whole-passage Aquifer overview |

## Reference specificity

Aquifer note score from canonical span width:

| Span | Specificity |
|------|-------------|
| Single verse | 100 |
| 1–2 verses | 90 |
| ≤5 verses | 75 |
| ≤10 verses | 55 |
| Full passage overview | 20 (optional tier) |

## Passage coverage

For a single-chapter range, verses are split into segments of **10** (e.g. 1–10, 11–20, 21–30, 31–40, 41–42).

Selection reserves **at least one non-overview note per segment** when candidates exist, so early-chapter notes cannot monopolize the budget.

Diagnostics: `selection_stats.coverage_segments[]` with `covered` / `note_count`.

## Redundancy

Deterministic, no NLP libraries:

1. Same `article_id` + `chunk_id`
2. Identical normalized plain text
3. Jaccard token overlap ≥ **0.85**

## Soft target vs hard max

| Profile | `target_tokens` | `max_tokens` |
|---------|-----------------|--------------|
| exegesis | 3200 | 4500 |
| historical_context | 2500 | 3500 |
| theology | 2500 | 3500 |

Builder prefers stopping near the **target**. Hard max is never exceeded. `truncated: true` only when hard-max drops occur.

## Per-type budgets (exegesis)

Configured on `ContextProfile.type_budgets`:

| Type | Soft cap |
|------|----------|
| passage | 150 |
| linguistic | 900 |
| exegetical | 1700 |
| background | 700 |

Sum ≈ target (3200).

## Minimum diversity

When candidates exist, exegesis reserves room for:

- linguistic
- exegetical
- background/places

## Jn 4 before / after

| Metric | Phase 3A | Phase 3B |
|--------|----------|----------|
| Evidence Packet Aquifer notes | 24 | 24 (unchanged) |
| Context Aquifer notes | ~24 | **9** |
| Exegesis context tokens | ~4480 | **~3197** |
| `truncated` | true | **false** |
| Coverage segments covered | uneven | **5/5** |

Example `selection_stats`:

```json
{
  "candidates": 52,
  "selected": 34,
  "dropped_budget": 0,
  "dropped_redundant": 0,
  "dropped_type_budget": 15,
  "aquifer_candidates": 24,
  "aquifer_selected": 9,
  "tokens_by_type": {
    "passage": 97,
    "linguistic": 639,
    "exegetical": 1897,
    "background": 564
  }
}
```

## Schema

`LLMContextPacket.schema_version = "2"` adds:

- `target_tokens`, `max_tokens`
- `selection_stats`

Phase 2B golden fixtures regenerated under Aquifer-disabled manifest.  
Phase 3B goldens: `john_4_1_42_*_context_phase3b.json`.

## Known gaps

- Coverage is verse-bucket based (not narrative unit detection)
- Jaccard dedup misses paraphrases
- Type budgets are static per profile (not passage-length adaptive)
- Historical profile does not yet consume Aquifer notes

## Production isolation

Unchanged: no LLM, no `app.py`, no prompts, no Supabase, no new upstream imports.

## Suggested next phase (not started)

1. Adaptive type budgets by passage length
2. Historical Aquifer inclusion rules from note metadata
3. Feature-flagged workshop injection of selected context
4. Bible Dictionary / UBS as additional `primary`/`supporting` sources under the same selector
