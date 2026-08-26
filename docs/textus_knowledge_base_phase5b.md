# Textus Knowledge Base — Phase 5B

Shadow audit store and read-only comparison reporting.

**Production invariance (unchanged from Phase 5A):** KB Context Packet is **not** injected into the production prompt. User-visible output continues to come only from the existing production generate path.

## Audit store choice

**SQLite** at `data/generated/kb_shadow_audit.sqlite3` (gitignored via `*.sqlite3`).

Rationale:

- Structured, indexable rows for passage / module / timestamp / status filters
- Simple aggregation for min/avg/max latency and token stats
- Suitable for later comparison reports without a dashboard
- No Supabase in this phase

JSONL would also have worked for append-only logs, but SQLite matched the reporting queries with less custom aggregation code.

Optional override: pass `--database PATH` to `shadow-report` / `shadow-compare`. Persistence always uses the default path unless callers pass `database_path=` to `persist_shadow_audit`.

## Schema (`schema_version = "1"`)

Table `shadow_runs`:

| Column | Notes |
|--------|--------|
| `run_id` | UUID primary key |
| `schema_version` | `"1"` |
| `timestamp` | UTC ISO-8601 |
| `canonical_passage` | CanonicalReference string |
| `module` | `exegesis` or `historical_context` |
| `profile` | KB profile id |
| `evidence_build_id` | Evidence Packet build id |
| `context_schema_version` | From Context Packet metadata only |
| `source_ids_json` | JSON array of source IDs |
| `evidence_count` | Count only |
| `entity_count` | Count only |
| `selected_item_count` | Selected context items |
| `context_tokens` | Token estimate |
| `retrieval_ms` | Retrieval duration |
| `context_build_ms` | Context build duration |
| `warning_count` | Warning count |
| `status` | `success` / `degraded` / `error` |
| `production_prompt_chars` | Length only |
| `production_output_chars` | Length only |
| `generation_ms` | Optional production generate duration |

Indexes: `canonical_passage`, `(module, profile)`, `timestamp`, `status`.

## Feature flag

| Flag | Default | Effect |
|------|---------|--------|
| `TEXTUS_KB_SHADOW_STORE_ENABLED` | `false` | When false: no SQLite open, no disk write, no persistence overhead. When true: write one audit row per shadow artifact. |

Orthogonal to `TEXTUS_KB_SHADOW_ENABLED` (Phase 5A shadow execution).

## Persistence flow

1. Production generate runs (unchanged).
2. If shadow enabled, `run_kb_shadow_artifact_dict()` builds the shadow artifact.
3. If store enabled, `persist_shadow_audit(artifact)` maps to a privacy-safe row and inserts into SQLite.
4. Any persistence exception is caught inside `run_kb_shadow_artifact_dict`, recorded as `audit_persist_error` on the in-memory artifact, and **never** raised to `generate_section()` / production callers.

## Privacy guardrails

**Never stored:**

- API keys / provider credentials
- User name, account ID, email, session token
- Full user / production prompt text
- Full production output text
- Full raw Evidence Packet / Context Packet body / evidence ID lists

**Allowed:** canonical passage, module/profile, source IDs, counts, timings, status, char-length metrics.

Helper: `assert_record_privacy_safe()`.

## Failure isolation

- Store disabled → no DB connection.
- Store enabled + write failure → shadow artifact still returned; production output unchanged.
- Persistence exceptions do not propagate past `run_kb_shadow_artifact_dict`.

## CLI report

```bash
python -m textus_kb shadow-report
python -m textus_kb shadow-report --passage "Jn 4,1–42"
python -m textus_kb shadow-report --module exegesis
python -m textus_kb shadow-report --module historical_context
```

Passage filter uses `CanonicalReference.parse` (no CLI-specific parser).

Emits JSON with: run count; by passage / module / status; retrieval and context-build min/avg/max; context token min/avg/max; evidence/entity stats; source mix buckets; warning/error ratios.

## Comparison report

```bash
python -m textus_kb shadow-compare "Jn 4,1–42"
```

Per module (`exegesis`, `historical_context`): production prompt/output **sizes**, KB context tokens, source breakdown, evidence/entity/selected counts, latency overhead, warnings, status.

**Does not** score production output as better/worse/more or less accurate.

## Benchmark results (dev machine, 2026-08-24)

Store: `data/generated/kb_shadow_audit.sqlite3`  
Flag: `TEXTUS_KB_SHADOW_STORE_ENABLED=true`  
Runs: **16** (4 passages × 2 modules × 2 repeats)  
Synthetic production lengths: prompt 1200 chars, output 3400 chars (length metrics only).

### Passage / module split

| Passage | Runs |
|---------|------|
| John.4.1-42 | 4 |
| Luke.10.25-37 | 4 |
| Acts.2.1-13 | 4 |
| Rom.8.28-30 | 4 |

| Module | Runs |
|--------|------|
| exegesis | 8 |
| historical_context | 8 |

All 16 runs status: `degraded` (existing retrieval warnings; 0 errors).

### Source / coverage mix (sum of source-ID bucket hits across runs)

| Bucket | Hits |
|--------|------|
| linguistic (TAGNT / TBESG / lexicon overlay) | 32 |
| ACAI | 16 |
| Dictionary | 16 |
| places/background | 12 |
| Study Notes | 8 |
| other | 0 |

### Latency (ms)

| Metric | min | avg | max |
|--------|-----|-----|-----|
| retrieval | 1164 | 1998.44 | 2483 |
| context_build | 33 | 61.94 | 89 |

### Context tokens

| min | avg | max |
|-----|-----|-----|
| 1607 | 2609.25 | 3194 |

### Evidence / entities

| Metric | min | avg | max |
|--------|-----|-----|-----|
| evidence_count | 87 | 114.75 | 130 |
| entity_count | 7 | 25.75 | 38 |

Warning-run ratio: 1.0 · Error-run ratio: 0.0

## Known limits

- Audit DB is local/dev-only; not synced or multi-user.
- Shadow remains **synchronous** when enabled (Phase 5A).
- Source mix is derived from source IDs only (no new retrieval).
- `degraded` status reflects retrieval warnings, not production failure.
- No UI / Streamlit / Supabase reporting in this phase.
- Store path is fixed unless callers pass an explicit database path.

## Suggested Phase 5C (not started)

Optional, opt-in **shadow comparison of context quality signals** (still without production injection), or a carefully gated dry-run of prompt composition that never calls the provider — only after explicit product approval.
