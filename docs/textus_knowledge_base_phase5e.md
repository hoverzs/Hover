# Textus Knowledge Base — Phase 5E

Controlled human A/B comparison workflow (dev/staging only).

**Not a production rollout.** Compare never runs inside normal `generate_section()`.
No Streamlit review UI. No LLM-as-judge. Theology remains excluded.

## A/B workflow

Explicit CLI / Python API only:

```bash
python -m textus_kb grounded-compare "Jn 4,1–42" --module exegesis
python -m textus_kb grounded-compare "Jn 4,1–42" --module historical_context --blind
```

For each run:

| Side | Prompt | Provider |
|------|--------|----------|
| A | current production prompt | same `generate_text_fn` |
| B | Phase 5C/5D grounded composition (only if prep succeeds) | same `generate_text_fn` |

Default generate function is **mock** (no API cost).  
`--live` imports `app.generate_text` when available (real provider cost — use sparingly).

## Flags

| Flag | Default | Role |
|------|---------|------|
| `TEXTUS_KB_COMPARE_STORE_ENABLED` | `false` | Persist compare artifacts to compare SQLite |
| `TEXTUS_KB_GROUNDED_ENABLED` | `false` | Production grounded injection (unchanged; compare forces grounded prep for B) |
| `TEXTUS_KB_SHADOW_*` | `false` | Unrelated shadow/audit flags |

Compare CLI does **not** enable production grounded rollout.

## Compare store

- Path: `data/generated/kb_grounded_compare.sqlite3` (gitignored)
- Also writes JSON under `data/generated/kb_grounded_compare/`
- **Separate** from Phase 5B privacy-limited `kb_shadow_audit.sqlite3`
- May store full model outputs (dev-only)
- Persistence only when flag true, or when `--database PATH` is passed explicitly

## Human review schema

Optional fields (not all required per module):

- `factual_accuracy_preference`: A | B | equal | unclear
- `exegetical_usefulness_preference`: A | B | equal | unclear
- `historical_grounding_preference`: A | B | equal | unclear
- `clarity_style_preference`: A | B | equal | unclear
- `hallucination_risk`: A | B | both | neither | unclear
- `overall_preference`: A | B | equal | unclear
- `reviewer_notes`: free text

### Review criteria (what to evaluate)

**Factual accuracy** — concrete linguistic, historical, cultural claims.  
**Exegetical usefulness** — helps understanding / interpretation.  
**Historical grounding** — usable historical background.  
**Clarity/style** — natural, usable Hungarian professional prose (Textus voice).  
**Hallucination risk** — unsourced or suspicious concrete claims.  
**Overall** — which would be a better base for Textus users.

## Blind review

`--blind` randomizes display mapping so the report shows only `RESPONSE A` / `RESPONSE B`.

- Mapping lives in artifact metadata (`blind_mapping`)
- Reviewer-facing text withholds mapping until `--reveal` on `review-show`
- Reduces label bias (“grounded must be better”)

## Source trace (reviewer only)

Report / artifact includes:

- source IDs
- selected evidence count
- Study Notes / Dictionary / ACAI / linguistic / places counts
- entity count

No user-facing citation UI in this phase.

## Cost / provider calls

- Normal production request: **1** provider call (invariant)
- Explicit compare: **2** when B succeeds; **1** if B prep fails before generation
- Report includes prompt/output token estimates and latencies
- No dollar cost estimate (no reliable runtime pricing)

## Failure behavior (compare-specific)

If A succeeds and grounded B fails:

- A output is kept
- B status = `error` (with reason)
- Artifact/report still created
- B is **not** replaced with the production prompt (that would hide grounded failure)

Production hard-fallback (Phase 5D) is unchanged and separate.

## Benchmark set (manual)

Passages:

- John.4.1-42
- Luke.10.25-37
- Acts.2.1-13
- Rom.8.28-30

Modules: `exegesis`, `historical_context` → **8** A/B pairs.

Do not auto-batch live runs. Smoke in CI/implementation: mock only; optional 1+1 live by hand.

## Commands for manual review

Mock (safe, no API cost):

```bash
set PYTHONPATH=.
python -m textus_kb grounded-compare "Jn 4,1-42" --module exegesis --blind --output compare_jn4_ex.md
python -m textus_kb grounded-compare "Jn 4,1-42" --module historical_context --blind
```

Persist to compare store:

```bash
set TEXTUS_KB_COMPARE_STORE_ENABLED=true
python -m textus_kb grounded-compare "Jn 4,1-42" --module exegesis --blind
python -m textus_kb review-list
python -m textus_kb review-show <run_id>
python -m textus_kb review-rate <run_id> --overall B --factual equal --hallucination neither --notes "..."
python -m textus_kb review-show <run_id> --reveal
```

Live smoke (costs real tokens — run deliberately):

```bash
python -m textus_kb grounded-compare "Jn 4,1-42" --module exegesis --live --prompt-file path\to\real_production_prompt.txt
python -m textus_kb grounded-compare "Jn 4,1-42" --module historical_context --live --prompt-file path\to\real_production_prompt.txt
```

Full 8-pair live benchmark (manual loop — not automated here):

```bash
for %p in (John.4.1-42 Luke.10.25-37 Acts.2.1-13 Rom.8.28-30) do (
  for %m in (exegesis historical_context) do (
    python -m textus_kb grounded-compare "%p" --module %m --live --blind
  )
)
```

## Privacy

- Compare store: may hold full outputs (dev-only, gitignored)
- Shadow audit DB: still must not hold full prompts/outputs
- Do not commit compare JSON/MD/SQLite

## How to review as a human

1. Run compare with `--blind`.
2. Read RESPONSE A / B without knowing which is grounded.
3. Fill preferences via `review-rate` (or edit JSON).
4. Only then `review-show --reveal` to see mapping.
5. Record notes on hallucination / style separately from “which felt nicer”.

## Suggested next phase (not started)

**Phase 5F:** after a completed human review set, decide staging enablement criteria for `TEXTUS_KB_GROUNDED_ENABLED`, citation policy, and latency mitigations — still no automatic judge.
