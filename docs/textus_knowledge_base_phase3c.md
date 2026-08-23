# TEXTUS Knowledge Base — Phase 3C (Aquifer Open Bible Dictionary)

Phase 3C adds the first real **historical/cultural reference source** for the John 4:1–42 pilot using upstream **Aquifer Open Bible Dictionary** data.

## Upstream schema

Repository: `https://github.com/BibleAquifer/AquiferOpenBibleDictionary`

Layout (English):

```
eng/
  metadata.json          # resource_metadata + article_metadata + scripture_burrito
  json/
    001.content.json     # array of article objects
    ...
  md/                    # parallel Markdown exports
  pdf/, docx/
```

Each article in `*.content.json`:

| Field | Description |
|-------|-------------|
| `content_id` | Stable article ID (string) |
| `reference_id` | Numeric upstream reference |
| `title` | English article title |
| `index_reference` | Canonical slug (e.g. `samaritans`, `mount gerizim`) |
| `language` | `eng` |
| `content` | Original English HTML (`<h1>`, `<p>`, ref.ly links) |
| `associations.passage[]` | `{start_ref, end_ref, start_ref_usfm, end_ref_usfm}` — BBCCCVVV numeric refs |
| `associations.resource[]` | Cross-resource links |
| `associations.acai[]` | ACAI metadata (not integrated in this phase) |

`article_metadata` in `metadata.json` maps `content_id` → localizations; English titles live in content files.

## Version / license / provenance

| Field | Value |
|-------|-------|
| Upstream version | `1.1.2` |
| Upstream commit | `3c4773e8746c9b051ce754c5a01ceddaabea84ce` |
| License | CC BY-SA 4.0 |
| License URL | `https://creativecommons.org/licenses/by-sa/4.0/` |
| Attribution | Aquifer Open Bible Dictionary © 2026 Mission Mutual, adapted from Tyndale Open Bible Dictionary © 2023 Tyndale House Publishers |

Manifest source ID: `aquifer_open_bible_dictionary` (`source_type = bible_dictionary`, `language = en`, optional, enabled when pilot bundle exists).

Provenance chain:

`Context item → Evidence item (EV-DICT-*) → Dictionary chunk → Dictionary article → Aquifer source → version + upstream commit + license`

## Pilot entry list (Jn 4)

Deterministic selection from `PILOT_INDEX_REFERENCES` (upstream titles verified to exist). Duplicate `index_reference` rows prefer the fullest article body (tie-break: lowest `content_id`).

| Title | content_id | Selection reason |
|-------|------------|------------------|
| Samaria | 8120 | pilot place/entity |
| Samaritans | 8121 | direct John 4 passage association |
| Mount Gerizim | 5428 | pilot place/entity |
| Sychar | 8676 | direct John 4 passage association |
| Jacob | 6163 | pilot index match |
| Jacob's Well | 6162 | direct John 4 passage association |
| Galilee | 5354 | pilot place/entity |
| Judea, Judeans | 6487 | pilot place/entity |
| Temple | 8782 | cultural/worship background |
| Worship | 9094 | direct John 4 passage association |
| Well | 9052 | direct John 4 passage association |
| Water | 9040 | direct John 4 passage association |

**12 entries**, **120 chunks** in `data/kb/aquifer/john_4_1_42_bible_dictionary.json`.

Entity/topic links inferred from Jn 4 place IDs are marked `source: inferred_from_pilot_place_links`. Passage links use `source: upstream_passage_association`.

## Chunking

Deterministic structural split (`textus_kb/importers/aquifer_bible_dictionary.py`):

1. Upstream heading boundaries (`<h1>`–`<h3>`)
2. Paragraph/list blocks (`</p>`, `</li>`)
3. Length split (1200 plain chars) as last resort

Each chunk stores: `chunk_id`, `chunk_index`, `heading`, `content_html`, `content_plain`, parent entry provenance.

## Retrieval

Adapter: `textus_kb/adapters/aquifer_bible_dictionary.py`

Evidence type: `dictionary_background` (distinct from `exegetical_note`).

Evidence IDs: `EV-DICT-0001` …

Relevance tiers (deterministic):

1. Direct John 4 passage association → 88
2. Pilot place/entity match → 80
3. Pilot index/topic match → 72
4. General background → 65

Build ID when dictionary present: `kb-phase3c-john4-pilot-v1`.

Dictionary evidence is **audit-retained** in the Evidence Packet (not dropped by supplemental token trimming).

## Historical context selection

Profile: `historical_context`

Priority order:

1. Dictionary chunks (dominant budget: 1600 tokens)
2. Passage–place links + enrichment + catalog/geography (background budget: 450)
3. Minimal linguistic (200 cap; typically unused)

Jn 4 pilot result: **~2174 tokens** (was ~1134 in Phase 3B), **3 dictionary chunks** selected from 120 candidates.

## Exegesis context selection

Dictionary receives a **lower budget** (450 tokens) than Study Notes (1700). Diversity reservation ensures linguistic + exegetical + dictionary types when available.

Per-article cap: max **2 dictionary chunks** per article to prevent one entry consuming the full budget.

Jn 4 pilot result: **~3161 tokens** (was ~3197), **9 Study Notes + 1 dictionary chunk**, full passage coverage retained.

## Tokens by source/type (Jn 4 pilot)

### Exegesis

| Budget type | Tokens (approx.) |
|-------------|------------------|
| passage | 97 |
| exegetical (Study Notes) | 1897 |
| linguistic | 639 |
| dictionary | 528 |

### Historical

| Budget type | Tokens (approx.) |
|-------------|------------------|
| dictionary | 1494 |
| background (places) | 640 |
| passage | 40 |

## Study Notes + Dictionary cooperation

- Separate manifest sources and evidence relation types
- Study Notes remain primary for exegesis (`exegetical_note`)
- Dictionary supplies cultural/geographical depth for `historical_context`
- Both full sets remain in the Evidence Packet; Context Packet applies source-aware selection

## Storage scaling

| Asset | Phase 3C size |
|-------|---------------|
| Study Notes pilot bundle | 24 articles |
| Dictionary pilot bundle | 12 entries, 120 chunks |
| Combined dictionary evidence items | 120 |

Full dictionary corpus: **6120 articles** across 26 JSON shard files (~30 MB English JSON alone).

**Conclusion:** JSON pilot bundles remain appropriate for the Jn 4 pilot (combined ~144 supplemental evidence items). A move to **SQLite** is justified when:

- expanding beyond pilot scope to hundreds/thousands of articles,
- cross-passage dictionary retrieval is needed without loading full bundles, or
- combined Study Notes + Dictionary evidence for multiple passages exceeds ~500 KB–1 MB per retrieval build.

Recommend SQLite evaluation in Phase 4 if multi-passage or whole-book pilots begin.

## Files added/changed

- `textus_kb/importers/aquifer_bible_dictionary.py`
- `textus_kb/adapters/aquifer_bible_dictionary.py`
- `data/kb/aquifer/john_4_1_42_bible_dictionary.json`
- `textus_kb/evidence.py`, `retrieval.py`, `context_profiles.py`, `context_selection.py`, `context_builder.py`
- `tests/test_textus_kb/test_aquifer_bible_dictionary.py`
- Fixtures: `john_4_1_42_packet_with_dictionary.json`, `*_phase3c.json`

## Out of scope (Phase 3C)

No UBS, ACAI runtime, Sefaria, LLM, embeddings, Supabase schema, production prompt, or `app.py` changes.
