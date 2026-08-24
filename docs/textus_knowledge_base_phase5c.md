# Textus Knowledge Base — Phase 5C

Dry-run grounded prompt composition and size/provenance audit.

**Still no production KB injection.** The composed grounded prompt is never sent to a model provider. User-visible output remains the existing production generate path.

## Goal

Separate three layers:

1. Current production prompt (unchanged)
2. KB Context Packet (shadow retrieval/context)
3. Dry-run grounded prompt composition (`GroundedPromptPreview`)

Phase 5C exercises the **same composition shape** intended for a future Phase 5D feature-flagged injection — without calling the provider.

## Module: `textus_kb/prompt_composer.py`

Inputs:

- `production_prompt`
- `canonical_passage`
- `module` / profile (`exegesis` | `historical_context` only; theology excluded)
- `LLMContextPacket` (or equivalent mapping)

Output: `GroundedPromptPreview` (`composition_version = "1"`).

## Prompt composition structure (chosen layout)

Preferred order for the future grounded production prompt:

1. **Existing production instructions** (verbatim — never truncated)
2. **Canonical passage**
3. **Grounded-use rules** (KB = source material; synthesize; no invention)
4. **Injection delimiters** + `<<<BEGIN_KB_DATA>>>` … `<<<END_KB_DATA>>>`
5. **Rendered KB source context**
6. **Output/style constraints** (preserve Textus professional voice)

### Why this placement

Putting KB data **after** the production instruction block keeps Textus task/style ownership intact, while clear delimiters reduce prompt-injection risk from third-party source text. Placing KB before style constraints still lets the model treat KB as evidence rather than as the final answer template.

Alternatives considered (KB first, or interleaved JSON): higher risk of style drift and accidental instruction-following from source HTML/notes.

## Context rendering

Compact deterministic text — **not** raw `LLMContextPacket` JSON:

```
=== KNOWLEDGE BASE CONTEXT ===

[LINGUISTIC]
[EV-LEX-...]
source_id=...
canonical_scope=...
content...

[EXEGETICAL NOTES]
...

[DICTIONARY]
...

[ENTITIES]
...

[PLACES / BACKGROUND]
...

[HISTORICAL BACKGROUND]
...
```

Preserves evidence ID (via attribution marker), source ID, canonical scope, and content. Residual HTML is stripped via `normalize_prompt_text` (does not mutate audit-store evidence originals).

## Source attribution markers

Internal dry-run markers only (not user-facing citations):

- `[EV-AQUIFER-...]` study notes
- `[EV-DICT-...]` dictionary
- `[EV-LEX-...]` TAGNT / lexicon
- `[EV-ACAI-...]`
- `[EV-PLACE-...]`
- `[EV-SRC-...]` fallback

## Injection guardrail

KB content is treated as **untrusted data**:

- Explicit “data only / ignore instruction-like text” rules
- Hard delimiters around the KB block
- Tested with malicious evidence strings (“ignore previous instructions…”)

## Composer budget

- Default: **8000** estimated tokens (`estimate_text_tokens`; no new tokenizer dependency)
- Override: `TEXTUS_KB_GROUNDED_PROMPT_TOKEN_BUDGET` or CLI `--token-budget`
- If over budget: **trim KB context first** (section drop order, then items)
- **Never truncate** the production prompt
- Structured warnings when still over budget after trimming

This budget is independent of the Context Packet token budget.

## Dry-run artifact fields

`GroundedPromptPreview`:

- passage / module / profile
- original / KB / composed chars + estimated tokens
- `kb_prompt_ratio`
- source_ids / evidence_ids
- warnings, `prompt_hash`, `composition_version`
- source diversity, duplicate-text ratio, `budget_ok`
- `composed_prompt` **in memory only** (CLI `--show-prompt`); omitted from default JSON / audit

## CLI

```bash
python -m textus_kb prompt-preview "Jn 4,1–42" --module exegesis
python -m textus_kb prompt-preview "Jn 4,1–42" --module historical_context --show-prompt
python -m textus_kb prompt-preview "Jn 4,1–42" --module exegesis --prompt-file path\to\production_prompt.txt
```

Default output: sizes, ratios, sources, warnings, hash — **not** the full prompt.

## Shadow / audit integration

`run_kb_shadow_artifact_dict` attaches `grounded_prompt_preview` metrics (no full prompt). Composer failures become `grounded_preview_error` and never reach production callers.

### Audit schema migration (`schema_version` **2**)

Additive, backward-compatible columns on `shadow_runs`:

- `composed_prompt_chars`
- `composed_prompt_estimated_tokens`
- `kb_prompt_ratio`
- `composition_version`
- `prompt_hash`

**Never** stores full composed / production / output text.

## Benchmark results (dry-run, 2026-08-24)

Production stub: `DRY_RUN_PRODUCTION_STUB` (~231 chars).  
Budget: 8000 estimated tokens. Runs: **8** (4 passages × 2 modules).

| Passage | Module | KB tokens | Composed tokens | KB ratio | budget_ok |
|---------|--------|-----------|-----------------|----------|-----------|
| John.4.1-42 | exegesis | 1784 | 2137 | 0.835 | yes |
| John.4.1-42 | historical_context | 1424 | 1777 | 0.801 | yes |
| Luke.10.25-37 | exegesis | 1717 | 2071 | 0.829 | yes |
| Luke.10.25-37 | historical_context | 1452 | 1806 | 0.804 | yes |
| Acts.2.1-13 | exegesis | 1941 | 2295 | 0.846 | yes |
| Acts.2.1-13 | historical_context | 1231 | 1585 | 0.777 | yes |
| Rom.8.28-30 | exegesis | 889 | 1243 | 0.715 | yes |
| Rom.8.28-30 | historical_context | 1193 | 1547 | 0.771 | yes |

With a ~1265-char production-like stub (John.4.1-42): exegesis composed ≈2396 tokens (KB ratio ≈0.74); historical ≈2036 tokens (ratio ≈0.70). Real app prompts should be measured via shadow + store metrics.

### Source diversity (typical)

- Exegesis: linguistic + study notes + dictionary + ACAI
- Historical: linguistic (lighter) + dictionary + ACAI + places/background

Duplicate-text ratio on selected pilots: **0.0** (Context Builder already dedupes heavily).

### Budget warnings

No budget overflows on the 8 pilot dry-runs at 8000. Tight budgets in tests correctly trim KB sections/items and keep production text intact.

## Production invariance

- `generate_text()` prompt / model config / provider params / output unchanged
- `GroundedPromptPreview` never enters a provider call
- Phase 5A/5B shadow flags and flows remain optional and isolated

## Failure isolation

Composer exception → dry-run error field on artifact; shadow/audit may continue; production flow unchanged.

## Known risks

- Dry-run stub ≠ real production prompt length/style; ratios must be re-checked with live prompts.
- High KB ratio with short stubs can over-weight sources relative to task instructions.
- Delimiters reduce but do not eliminate injection risk.
- Attribution markers are internal only — user-facing citations not designed yet.
- No automatic quality judgment of model answers (none generated).

## What is still missing for real injection (Phase 5D+)

1. Explicit product approval + feature flag for production composition
2. Live production prompt wiring (not stub) into composer
3. Provider call using composed prompt **only** when flag on
4. Fallback to legacy prompt on composer/budget failure
5. User-visible citation policy (if any)
6. Latency/cost A/B vs shadow metrics
7. UI remains out of scope until explicitly requested

## Suggested next phase (not started)

**Phase 5D:** feature-flagged optional injection of the dry-run composition into production generate for exegesis / historical_context only, with hard fallback to the current production prompt and continued audit metrics — still no theology.
