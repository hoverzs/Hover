# TEXTUS Knowledge Base — Phase 3A (Aquifer Open Study Notes pilot)

Phase 3A integrates the first external exegetical source: **Aquifer Open Study Notes** (English) for **John 4:1–42** only.

## Upstream source audit

**Repository:** [BibleAquifer/AquiferOpenStudyNotes](https://github.com/BibleAquifer/AquiferOpenStudyNotes)

**Pinned pilot import:**
- Resource version: `1.1.2` (`resource_metadata.version`)
- Git commit: `8f4d7c3614e9a41495f16d7c778e9c8ed0dde808` (clone date 2026-08-23)
- Language folder: `eng/`

### Layout (English)

```
eng/
  metadata.json          # resource + scripture_burrito + article_metadata index
  json/
    43.content.json      # Gospel of John articles (list of content objects)
    01.content.json …    # other biblical books
  md/ pdf/ docx/         # alternate exports (not used in pilot)
```

### Article object schema (from `43.content.json`)

| Field | Role |
|-------|------|
| `content_id` | Stable Aquifer article ID (string) |
| `reference_id` | Internal numeric reference id |
| `title` | Human title, e.g. `John 4:10` |
| `index_reference` | `BBCCCVVV` or range `43004001-43004042` (book 43 = John) |
| `language` | `eng` |
| `content` | Original English HTML body (unchanged in import) |
| `associations.passage[]` | `{ start_ref, end_ref, start_ref_usfm, end_ref_usfm }` |

### John 4 pilot selection

Articles in `43.content.json` whose `associations.passage` overlap index range **43004001–43004042**.

**Result:** 24 articles, 24 chunks (all under 900 plain-text chars — no split needed).

## License

- **License:** CC BY-SA 4.0
- **URL:** https://creativecommons.org/licenses/by-sa/4.0/
- **Attribution (stored in bundle + evidence metadata):** Aquifer Open Study Notes © 2026 Mission Mutual, adapted from Tyndale Open Study Notes © 2023 Tyndale House Publishers.

Manifest source id: `aquifer_open_study_notes` (`source_type: exegetical_notes`, optional, enabled).

## Import strategy

Module: `textus_kb/importers/aquifer_study_notes.py`

```bash
# Requires upstream clone (default: _upstream_audit/AquiferOpenStudyNotes)
python -m textus_kb.importers.aquifer_study_notes

# Or explicit paths
python -m textus_kb.importers.aquifer_study_notes --upstream /path/to/AquiferOpenStudyNotes
```

Env override: `TEXTUS_AQUIFER_UPSTREAM_PATH`

**Output:** `data/kb/aquifer/john_4_1_42_study_notes.json` (committed pilot bundle)

### Why JSON bundle (not SQLite)

- Pilot scope = 24 notes (~50 KB normalized JSON)
- Reproducible diff/review in git
- Matches existing KB read-only JSON pattern (places, manifest)
- SQLite deferred until multi-book scale is required

## Normalization

Each note record contains:

- `article_id`, `content_id`, `title`
- `index_reference`, `canonical_reference` (via `CanonicalReference` mapping)
- `upstream_reference_usfm` (e.g. `JHN 4:10`)
- `content_html` (original, unmodified)
- `chunks[]` with deterministic `chunk_id`, `content_plain` (derived, not stored as source of truth)
- `license`, `license_url`, `attribution`, `source_id`

Invalid / out-of-scope mappings → import issue log entry; note skipped.

## Chunking

Deterministic paragraph/list split when plain text exceeds **900 characters**.

John 4 pilot: all articles fit in a single chunk.

## Retrieval integration

Adapter: `textus_kb/adapters/aquifer_study_notes.py`

New evidence relation: `exegetical_note` (`source_type: exegetical_note`, language `en`)

Evidence IDs: `EV-AQUIFER-0001` … (sorted by canonical reference)

**Build id when Aquifer present:** `kb-phase3a-john4-pilot-v1`

Evidence packet supplemental budget: Aquifer notes are **audit-retained** (not dropped when supplemental estimate exceeds cap). Trimmable supplemental budget still applies to enrichment/highlights/catalog.

## Context Builder

**Exegesis profile only** — Aquifer notes appear in `exegetical` section, ranked by relevance (verse-specific > range > chapter overview).

Historical/theology profiles exclude Aquifer in Phase 3A (no deterministic historical-only classifier yet).

## Jn 4 pilot metrics

| Metric | Value |
|--------|-------|
| Articles imported | 24 |
| Evidence items added | 24 |
| Full evidence packet items | 52 |
| Evidence packet supplemental estimate | ~10 345 (Aquifer retained) |
| Exegesis LLM context estimate | ~4 480 (budget 4500) |

## Golden fixtures

| Fixture | Purpose |
|---------|---------|
| `tests/fixtures/kb/john_4_1_42_packet.json` | Phase 2A baseline (unchanged) |
| `tests/fixtures/kb/john_4_1_42_packet_with_aquifer.json` | Phase 3A packet + `aquifer_evidence_count` |
| `tests/fixtures/kb/john_4_1_42_exegesis_context_phase3a.json` | Phase 3A exegesis context |

Phase 2B exegesis/historical fixtures remain valid when Aquifer is disabled in manifest (see `conftest.py`).

## Known gaps

- John 4 / Gospel of John book file only (`43.content.json`)
- No Open Bible Dictionary, ACAI, UBS, or other Aquifer resources
- No Hungarian translation of notes
- Historical profile integration deferred
- Upstream clone not vendored — import requires separate clone or env path
- Context may truncate lower-priority place/enrichment lines when Aquifer notes fill budget

## Production isolation

Unchanged: `app.py`, prompts, UI, Supabase, `bible_engine` repositories, RUF service, LLM.

## Suggested Phase 3B (not started)

1. Expand Aquifer import beyond John 4 with book-aware importer CLI
2. Historical-profile inclusion rules from note metadata/tags
3. SQLite runtime if corpus size warrants
4. Feature-flagged workshop injection of exegesis LLM context
5. UI attribution component using stored license metadata
