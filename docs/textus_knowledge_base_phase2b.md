# TEXTUS Knowledge Base — Phase 2B (Evidence Context Builder)

Phase 2B separates **audit-grade retrieval** from **LLM-ready context**. No new data sources, no LLM, no production integration.

## Three concepts

| Concept | Role |
|---------|------|
| `EvidencePacket` | Full deterministic retrieval output (~20k+ tokens for Jn 4); audit archive |
| `ContextSelection` | Profile-specific prioritisation and trimming rules |
| `LLMContextPacket` | Compact, token-budgeted, provenance-linked context for future model use |

Phase 2A `EvidencePacket` schema is unchanged.

## Architecture

```
retrieve("Jn 4,1–42")  →  EvidencePacket
                              │
                              ▼
              build_context(..., profile=exegesis|historical_context|theology)
                              │
                              ▼
                        LLMContextPacket
```

Modules:

- `textus_kb/context_profiles.py` — profile budgets and priority tables
- `textus_kb/context_builder.py` — selection, compact formatting, budget, CLI

## Profiles

| Profile | Default budget | Focus |
|---------|----------------|-------|
| `exegesis` | 4500 | Compact Greek lines, lexical highlights, brief places/background |
| `historical_context` | 3500 | Places, passage links, enrichment, geography |
| `theology` | 3500 | Passage + lexical + places; warns no dedicated theology layer |

### Exegesis compact linguistic line (example)

```text
Jn 4,10 — δωρεάν (G1432), adverb, "freely" / "ingyen"
```

Built from lexical highlights + first TAGNT token occurrence (lemma, morph prefix, gloss EN/HU). **Does not** embed the full 723-token JSON verse array.

### Historical profile

- No full Greek token set
- Passage-place links with coordinates
- Source-backed enrichment excerpts where available
- Catalog summaries + geography lines

### Theology profile

Minimal by design. Emits:

```text
warnings: ["No dedicated theological source layer available"]
```

No inferred theological claims.

## Relevance / selection priority

**Exegesis:** passage → passage summary → lexical lines → place links → catalog → enrichment

**Historical:** passage-place links → enrichment → catalog → geography → (minimal lexical)

**Theology:** passage → lexical → place links → catalog

Provenance fields on every context item: `evidence_id`, `source_id`, `relevance_score`.

## Token budget

Uses Phase 2A `estimate_text_tokens()` (`max(words, chars//4)`).

- Budget applies to **LLMContextPacket** only
- Evidence Packet remains complete when retrieved separately
- Truncation drops lowest-priority items first; may shorten a single oversized item
- `truncated: true` + warning when items dropped

## Jn 4,1–42 pilot results

| Artifact | Estimated tokens |
|----------|------------------|
| Full Evidence Packet | ~21 820 |
| Exegesis LLM Context | ~894 (≤ 4500) |
| Historical LLM Context | ~885 (≤ 3500) |
| Theology LLM Context | ~560 (≤ 3500) |

Size reduction vs full packet: **~96%** for both exegesis and historical profiles.

Evidence items included:

- Exegesis: 28 (all provenance-linked context lines; compact linguistic view)
- Historical: 21 (no lexical highlight lines; no raw token JSON)

## CLI

```bash
python -m textus_kb context "Jn 4,1–42" --profile exegesis
python -m textus_kb context "Jn 4,1–42" --profile historical_context
python -m textus_kb context "Jn 4,1–42" --profile theology --token-budget 2000
```

## Golden fixtures

- `tests/fixtures/kb/john_4_1_42_exegesis_context.json`
- `tests/fixtures/kb/john_4_1_42_historical_context.json`

## Known gaps

- Profiles are pilot-tuned for Jn 4 data shape; not yet generalised
- Morphology description is prefix-based (N/V/A/…), not full TAGNT morph decode
- Theology profile is schema placeholder only
- Context builder does not deduplicate overlapping place catalog + link prose
- No streaming / incremental context updates

## Production isolation

Unchanged: `app.py`, prompts, UI, Supabase, `bible_engine` repos, RUF service.

## Suggested Phase 2C (not started)

1. Wire `LLMContextPacket` behind feature flag in workshop (still explicit opt-in)
2. Generalise profiles for arbitrary passages
3. Full morph decode for exegesis lines
4. Dedicated theology source slot when data exists
5. Context schema version migration tests
