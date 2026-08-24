# Textus Knowledge Base — Phase 5F

Staging readiness framework, citation policy prep, and grounded prep latency mitigation.

**Default production remains unchanged.** Readiness reports never flip runtime flags.
No LLM-as-judge. No general production enablement.

## Review readiness audit (current store)

As of Phase 5F implementation on this machine:

| Metric | Value |
|--------|-------|
| Compare runs | 4 (all mock) |
| Live runs | 0 |
| Human reviews | 0 |
| Passage/module pairs | John.4.1-42 × exegesis + historical_context (mock only) |

**Staging readiness status: `insufficient_human_review_data`**

No quality conclusion is drawn from mock runs.

## Staging readiness model

CLI:

```bash
python -m textus_kb review-summary
python -m textus_kb review-summary --live-only
python -m textus_kb review-summary --module exegesis
```

Statuses:

| Status | Meaning |
|--------|---------|
| `insufficient_human_review_data` | Too few live reviewed pairs |
| `needs_more_review` | Some live reviews, criteria still unmet |
| `not_ready` | Safety veto fired |
| `ready_for_limited_staging` | All criteria met — **still does not enable grounded** |

### Minimum criteria (config: `StagingReadinessCriteria`)

Initial staging thresholds (not a scientific benchmark):

- ≥ 8 **live** A/B pairs with overall human review
- ≥ 4 distinct passages
- both `exegesis` and `historical_context`
- ≥ 2 passages reviewed in **both** modules
- ≥ 75% overall preference is B (grounded) or equal
- factual: B-worse rate ≤ 25%
- hallucination elevated (B/both) ≤ 20%
- grounded error rate ≤ 25%

Mock provider runs are excluded from readiness evidence.

### Safety vetoes

Automatic `not_ready` when:

- factual accuracy repeatedly prefers A (B worse) above threshold
- hallucination risk elevated for B/both above threshold
- success runs missing `source_ids`
- grounded error rate too high

## Citation policy (no UI yet)

Module: `textus_kb/citation.py`

### Cite / mark when

- concrete linguistic claims (TAGNT / TBESG / lexicon)
- historical/cultural background from Study Notes, dictionary, places
- dictionary background used as factual claim
- Study Notes–based concrete assertions
- ACAI entity facts used as grounding

### Do not require separate citation for

- model editorial / synthesizing sentences
- general transition sentences
- plain biblical paraphrase without external background claims

### `CitationRef`

- citation_id, source_id, evidence_id, source_type, title
- article/chunk ID, canonical_scope
- license, license_url, attribution
- upstream URL/version, restricted, citation_ready, missing_fields

Display names resolve via manifest + registry (STEPBible, Aquifer, ACAI, places).

### License guardrail

- CC BY / CC BY-SA: keep license + attribution/URL on every ref
- RÚF remains contractual-restricted and **separate** from KB source licenses

Coverage diagnostic: `citations_from_context_packet` / `citations_from_evidence_packet`  
(source-metadata readiness only — no LLM sentence linking).

## Latency breakdown

Bottleneck is **`retrieve()`** (~1–3 s cold). Context build ~50–90 ms; composition ~5–15 ms.

Adapter-level Study Notes / Dictionary / ACAI timings sit inside `retrieval_ms` (single call). Deeper per-adapter timers are optional future work.

CLI:

```bash
python -m textus_kb latency-audit
python -m textus_kb latency-audit --passage "John.4.1-42" --module exegesis
```

### Sample (John.4.1-42 / exegesis)

| Path | wall_ms | retrieval_ms | context_ms | composition_ms |
|------|---------|--------------|------------|----------------|
| cold | ~2575 | ~2476 | ~85 | ~13 |
| warm (cache) | ~7 | ~0 | ~0 | ~7 |

## Cache strategy

In-process cache (`textus_kb/kb_cache.py`):

- Evidence Packet by `canonical|kb_build_id|retrieval_version`
- Context Packet by `canonical|profile|kb_build_id|context_schema|selection_version`
- **Never** caches provider output or composed prompts (would need production prompt hash)

On cache I/O error → normal retrieve/build. Retrieve errors still propagate to hard fallback.

Async/background prep: **deferred** — revisit only if warm path still misses SLA.

## Staging guard

| Flag | Default | Role |
|------|---------|------|
| `TEXTUS_KB_GROUNDED_ENABLED` | false | Intent to use grounded |
| `TEXTUS_KB_GROUNDED_STAGE_ALLOWED` | false | Staging/dev gate |
| `TEXTUS_KB_GROUNDED_PASSAGE_ALLOWLIST` | empty | Optional comma-separated passages; empty = unrestricted when gates on |

App injection requires **both** grounded + stage-allowed (`is_grounded_injection_allowed()`).

Readiness = ready does **not** set either flag.

## Rollback

1. Leave both grounded flags false (default).
2. Clear allowlist env if set.
3. `clear_kb_cache()` for process-local cache (optional).

## What is still missing for limited staging enablement

1. ≥ 8 **live** A/B pairs with human overall reviews across 4 passages × both modules
2. Meet preference / veto thresholds in `review-summary`
3. Explicit ops decision to set `TEXTUS_KB_GROUNDED_STAGE_ALLOWED=true` **and** `TEXTUS_KB_GROUNDED_ENABLED=true` in staging only
4. Optional allowlist of approved passages
5. Human-approved citation UI design (Phase later)
6. Optional per-adapter retrieval timers / async if warm cache insufficient under load

## Suggested next phase (not started)

**Phase 5G:** execute live human review campaign → if ready, limited staging enablement with allowlist + monitoring; design user-facing citation presentation without dumping `EV-*` IDs.
