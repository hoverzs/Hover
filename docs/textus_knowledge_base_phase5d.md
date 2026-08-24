# Textus Knowledge Base — Phase 5D

Guarded, feature-flagged KB-grounded production prompt injection.

**Default remains off.** When enabled, only `exegesis` and `historical_context` may send the Phase 5C composed prompt to the model provider — with hard fallback to the original production prompt on any KB failure.

## Rollout flag

| Flag | Default | Effect |
|------|---------|--------|
| `TEXTUS_KB_GROUNDED_ENABLED` | `false` | When true: prepare grounded prompt before the single provider call for supported modules. |
| `TEXTUS_KB_SHADOW_ENABLED` | `false` | Phase 5A shadow diagnostics (unchanged). |
| `TEXTUS_KB_SHADOW_STORE_ENABLED` | `false` | Phase 5B/5C/5D audit SQLite writes. |
| `TEXTUS_KB_GROUNDED_PROMPT_TOKEN_BUDGET` | `8000` | Estimated-token budget for composed grounded prompt. |

Do **not** enable grounded in production environments without explicit ops approval. This phase only adds code support.

## Flag combinations

| SHADOW | GROUNDED | STORE | Behavior |
|--------|----------|-------|----------|
| false | false | * | Pre-5D production flow; provider gets original prompt. |
| true | false | * | Phase 5A/5B/5C shadow after production generate. |
| false | true | * | Grounded prep → single provider call (composed or fallback). |
| true | true | * | Grounded prep → single provider call; shadow reuses prep artifact when possible (no double retrieve). |

## Integration boundary

`app.py::generate_section()` still builds the production prompt via `SECTION_PROMPTS` + `build_alap_from_state(...)`.

Then:

```
run_production_with_optional_shadow(
  ...,
  grounded_enabled=_is_kb_grounded_enabled(),
  shadow_enabled=_is_kb_shadow_enabled(),
)
```

Core logic: `textus_kb/grounded_generation.py` + `textus_kb/shadow_integration.py`.

Composer: unchanged Phase 5C `prompt_composer.py` (`composition_version = "1"`).

## Success path

1. Production prompt built (unchanged builder).
2. `retrieve` → Evidence Packet.
3. `build_context_from_evidence` → LLMContextPacket.
4. `compose_grounded_prompt` → `GroundedPromptPreview`.
5. If `success` and `budget_ok`: provider receives **composed** prompt.
6. Exactly **one** `generate_text` / provider call.
7. Optional shadow reuses prep context when both flags are on.

## Fallback path (hard)

Any of: retrieval / context / composition / budget / empty passage / source unavailable / unexpected exception

→ provider receives **original production prompt** in the **same** request.

- No grounded-then-retry double provider call.
- No user-visible KB error.
- Exception does not propagate to `generate_section` caller.

## Internal status values

- `grounded_used`
- `grounded_fallback`
- `grounded_disabled`
- `grounded_unsupported_module`

Not shown in user-facing UI.

## Fallback reason taxonomy

- `retrieval_error`
- `context_error`
- `budget_exceeded`
- `composition_error`
- `unsupported_passage`
- `source_unavailable`
- `unsupported_module`

Logged as short type names / codes — not sensitive payloads.

## Prompt budget

- Default 8000 estimated tokens (`estimate_text_tokens`).
- Production prompt **never** truncated.
- KB context trimmed first; if still over budget → `budget_exceeded` fallback.
- Oversized grounded prompts are **not** sent.

## Provider call invariance (flag OFF)

With `TEXTUS_KB_GROUNDED_ENABLED=false`:

- Same provider function
- Same model/config parameters (`enable_google_search`, `tab_label`)
- Exact original production prompt
- Exactly one provider call
- No grounded composition on the provider path

## Provider call (flag ON)

- Success: one call with composed grounded prompt.
- Failure: one call with original production prompt.
- Never two calls for grounded prep failure.

## Audit schema (`schema_version` = **3**)

Additive columns on `shadow_runs`:

- `grounded_flag_enabled`
- `grounded_used`
- `grounded_fallback`
- `fallback_reason`
- `provider_call_count`
- `grounded_status`

Still never stores full production / grounded prompts or model outputs.

## Dev A/B compare

```bash
python -m textus_kb grounded-compare "Jn 4,1–42" --module exegesis
python -m textus_kb grounded-compare "Rom.8.28-30" --module historical_context
```

- Default: **mock** generate (two calls, no API cost).
- Writes summary + artifact under `data/generated/kb_grounded_compare/` (local/dev).
- `--live` is intentionally not wired to production `generate_text` in CLI (use `run_grounded_compare(..., generate_text_fn=...)` from a local script if needed).
- No automatic “grounded is better” scoring.

## Performance (local smoke, 2026-08-24)

Grounded **preparation** overhead (before provider), stub prompt:

| Passage | Module | retrieval_ms | context_ms | composition_ms | wall_ms |
|---------|--------|--------------|------------|----------------|---------|
| John.4.1-42 | exegesis | ~2441 | ~84 | ~13 | ~2544 |
| Luke.10.25-37 | historical_context | ~1009 | ~55 | ~2 | ~1067 |

Compare CLI prep: John exegesis ~2.6s; Rom historical ~1.2s (mock provider).

No async in this phase — overhead is synchronous when grounded is ON.

## Production UI

No user-facing changes: no badge, source panel, fallback warning, or citation UI.

## Rollback

1. Ensure `TEXTUS_KB_GROUNDED_ENABLED` is unset/`false` (default).
2. Behavior returns to pre-5D production prompt path immediately.
3. Optional: keep shadow flags independent.
4. No migration rollback required (additive schema only).

## Known risks

- Live production prompts are longer than the dry-run stub; re-check budget with real prompts before enabling.
- Synchronous KB prep adds ~1–3s before the provider call when ON.
- Delimiters reduce but do not eliminate prompt-injection risk from source text.
- Mock A/B compare does not evaluate answer quality.
- Dual shadow+grounded reuse assumes prep context is sufficient for shadow metrics.

## What Phase 5E could do (not started)

- Controlled staging enablement + human A/B review of live outputs
- User-visible citation policy (without dumping `EV-*` IDs)
- Optional async prep / caching to cut perceived latency
- Theology remains out of scope until separately approved
