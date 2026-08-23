# TEXTUS Knowledge Base — Phase 2A (John 4 retrieval pilot)

Phase 2A adds a **read-only, deterministic retrieval pilot** for `Jn 4,1–42` on top of the Phase 1 KB core. No LLM, no embeddings, no production integration.

## Scope

| In scope | Out of scope |
|----------|--------------|
| `retrieve("Jn 4,1–42")` → Evidence Packet | General passage retrieval API |
| TAGNT tokens, TBESG + HU lexicon highlights | Full lexicon dump per token |
| Passage-place links + catalog + enrichment excerpts | Entity/person indexes |
| Manifest-provenance for every evidence item | RUF Bible text in packet |
| CLI: `python -m textus_kb retrieve "Jn 4,1–42"` | `app.py`, prompts, Supabase, UI |

## Architecture

```
CanonicalReference.parse("Jn 4,1–42")
        │
        ▼
   retrieval.retrieve()
        │
        ├── TagntAdapter ──────────► stepbible_tagnt (SQLite)
        ├── LexiconAdapter ────────► stepbible_tbesg + lexicon_hu_overlay
        └── PlacesAdapter ─────────► biblical_places_catalog
                                     biblical_places_passage_links
                                     place_enrichments_overlay
        │
        ▼
   EvidencePacket (JSON-serializable)
```

Modules:

- `textus_kb/evidence.py` — `EvidenceItem`, `EvidencePacket`, token estimates
- `textus_kb/retrieval.py` — orchestration, scoring, budget
- `textus_kb/adapters/tagnt.py` — Greek passage tokens
- `textus_kb/adapters/lexicon.py` — TBESG + Hungarian overlay lookup
- `textus_kb/adapters/places.py` — passage-place links, catalog, enrichment

Adapters are **thin read-only wrappers** over existing `bible_engine` and `biblical_map_*` loaders. They do not mutate repository behaviour.

## Sources used (manifest)

| Source ID | Role in pilot |
|-----------|---------------|
| `stepbible_tagnt` | Required — 42-verse Greek token set |
| `stepbible_tbesg` | Optional — English gloss for lexical highlights |
| `lexicon_hu_overlay` | Optional — Hungarian gloss (`bible_engine/data/lexicon_hu.json`) |
| `biblical_places_catalog` | Optional — place names, coords, card summaries |
| `biblical_places_passage_links` | Optional — passage → place index |
| `place_enrichments_overlay` | Optional — source-backed enrichment excerpts |
| `ruf_2014_local` | **Disabled** — never included |

Phase 2A extends `kb_manifest.json` with the three biblical-places / lexicon overlay entries above so provenance stays explicit.

## Evidence Packet schema

Top-level JSON shape:

```json
{
  "passage": { "canonical": "John.4.1-42", "display": "Jn 4,1–42" },
  "build": { "build_id": "kb-phase2a-john4-pilot-v1", "manifest_version": "1" },
  "entities": [],
  "places": [ "... PlaceRecord ..." ],
  "linguistic_evidence": {
    "passage_token_set": { "verse_count": 42, "token_count": 723, "verses": [] },
    "lexical_highlights": []
  },
  "historical_evidence": [],
  "sources": [],
  "evidence_items": [],
  "warnings": [],
  "estimated_tokens": 0,
  "supplemental_tokens": 0,
  "token_budget": 4500,
  "token_budget_applied": false
}
```

### Evidence item fields

- `evidence_id` — deterministic prefix, e.g. `EV-TAGNT-0001`, `EV-PLACE-0003`, `EV-LEX-0005`
- `source_id` — manifest source
- `source_type`, `language`, `relation_type`, `passage`, `content`, `metadata`, `relevance_score`

### Linguistic split

1. **`passage_token_set`** — complete TAGNT tokens for verses 1–42 (form, lemma, morph, Strong).
2. **`lexical_highlights`** — up to 12 Strong IDs selected deterministically (frequency, then John 4 seed list, then ID order). Full TBESG/HU entries are **not** inlined for every token.

**Known limitation:** automatic “theologically important word” detection is not implemented; highlights use frequency + a fixed seed list (`G5204`, `G5207`, `G3962`, …).

## Relevance scoring (deterministic)

Higher score = retained first under budget pressure.

| Priority | Score | Relation |
|----------|-------|----------|
| 1 | 100 | Direct passage / passage token set |
| 2 | 85 | Passage-place link |
| 3 | 75 | Place catalog summary |
| 4 | 70 | Lexical highlight |
| 5 | 45 | Place enrichment excerpt |

No vector similarity.

## Token estimation and budget

- **Estimate:** `max(word_count, char_count // 4)` per text blob (no new tokenizer dependency).
- **`estimated_tokens`:** full packet including Greek token set JSON.
- **`supplemental_tokens`:** everything except the passage Greek token set.
- **`max_evidence_tokens` (default 4500):** applies to **supplemental** content only.

Passage Greek tokens and passage-place provenance are **never dropped** for budget. When supplemental content exceeds the cap, enrichment excerpts are removed first, then lexical highlights are reduced in fixed steps (12 → 6 → 4 → 0).

## CLI

```bash
python -m textus_kb retrieve "Jn 4,1–42"
python -m textus_kb health
python -m textus_kb          # default: health
```

Read-only. UTF-8 JSON on stdout.

## Golden fixture

`tests/fixtures/kb/john_4_1_42_packet.json` — regression anchor for:

- source presence
- place link set
- canonical mapping
- evidence ordering / counts

No RUF prose.

## Known gaps (Phase 2A)

- Pilot hard-coded to NT Greek + existing John 4 data paths; not generalized.
- No person/entity extraction.
- No route/travel layer in packet (routes exist elsewhere but omitted from MVP).
- Most Jn 4-linked places have catalog shells only; enrichment prose mainly for `jerusalem`.
- Hungarian lexicon overlay is draft (`review_status: draft` in source file).
- `supplemental_tokens` under default budget (~2.3k) — budget trimming rarely triggers unless forced low in tests.

## Phase 2B (planned, not started)

1. Generalize `retrieve()` beyond John 4 fixed assumptions.
2. Passage-agnostic adapter registry (still no plugin framework bloat).
3. Entity index (persons, groups) from structured sources.
4. Optional RUF concordance snippets under contractual guardrails.
5. Evidence Packet schema versioning + migration tests.
6. Integration hook for workshop / map UI (feature-flagged).

## Production isolation

Unchanged: `app.py`, AI prompts, Supabase, `bible_engine` repository behaviour, RUF service.
