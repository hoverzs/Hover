# Textus Knowledge Base — Phase 5G

Live human A/B review campaign workflow (technical support).

**No LLM-as-judge. No automatic quality scoring.** Humans read and rate responses.
**No production rollout.** Grounded flags stay default-off.
**Do not auto-run the full 8×2 live provider batch** — each pair is manual and costs provider calls.

## Required benchmark (first campaign)

| Passage | Modules |
|---------|---------|
| `John.4.1-42` | `exegesis`, `historical_context` |
| `Luke.10.25-37` | `exegesis`, `historical_context` |
| `Acts.2.1-13` | `exegesis`, `historical_context` |
| `Rom.8.28-30` | `exegesis`, `historical_context` |

**8 live A/B pairs.** A = production prompt output. B = same production prompt + Phase 5C/5D grounded composition.

## Ideal run workflow

1. Export the real production prompt for the module (from `SECTION_PROMPTS` / session builder) into a text file.
2. Generate one live A/B pair (`--live --blind --prompt-file …`).
3. Compare artifact is saved (JSON + optional compare SQLite).
4. `review-show <run_id>` — read Response A / Response B (blind).
5. Optionally `review-sources <run_id>` for citation/source trace (not mixed into Response B).
6. Human rates with `review-rate`.
7. Only then `review-show <run_id> --reveal`.
8. `review-campaign-status` / `review-summary --live-only` when ready.

## Live guard

- Live provider calls require **`--live`**.
- Default CLI remains mock / dry-run.
- `--live` also requires **`--blind`** and either:
  - **`--from-production`** (builds the real `SECTION_PROMPTS` prompt via
    `textus_kb.production_prompt_export`), or
  - **`--prompt-file`** (hand-exported production prompt).
- The dry-run stub prompt is rejected for `--live`.

There is no code path that auto-starts live provider calls for the full campaign
from the CLI default. Dev runner:
`python -m textus_kb.review_campaign_runner --run` (explicit only).

## Budget note (real production prompts)

The old Phase 5C **8000** value is no longer the total grounded prompt max.

Bounded adaptive model:

| Limit | Env | Default |
|-------|-----|---------|
| KB context max | `TEXTUS_KB_GROUNDED_CONTEXT_MAX_TOKENS` | **4500** (matches Context Builder exegesis) |
| Total hard safety cap | `TEXTUS_KB_GROUNDED_TOTAL_MAX_TOKENS` | **28000** |

`required ≈ production_tokens + kb_tokens + composition_overhead`

- Production prompt is **immutable** (never truncated).
- Oversized KB is trimmed via Context Selection priorities.
- If production + minimum usable KB still exceeds the total hard cap → structured `budget_exceeded` (B error in compare; A unchanged).

The total cap is an explicit safety config — the app only sets `maxOutputTokens`; there is no reliable in-repo model input-window claim.

Dry-run check (no provider calls):

```powershell
python scripts/phase5g_budget_dry_run.py
```

## Print manual commands (does not execute)

```powershell
$env:TEXTUS_KB_COMPARE_STORE_ENABLED="true"
python -m textus_kb review-campaign-commands --prompt-file "path\to\production_prompt.txt"
```

## Exact live commands (run one at a time)

Replace `PROD_PROMPT.txt` with your exported production prompt path. Enable the compare store first:

```powershell
$env:TEXTUS_KB_COMPARE_STORE_ENABLED="true"
```

```powershell
python -m textus_kb grounded-compare "John.4.1-42" --module exegesis --live --blind --prompt-file "PROD_PROMPT.txt"
python -m textus_kb grounded-compare "John.4.1-42" --module historical_context --live --blind --prompt-file "PROD_PROMPT.txt"
python -m textus_kb grounded-compare "Luke.10.25-37" --module exegesis --live --blind --prompt-file "PROD_PROMPT.txt"
python -m textus_kb grounded-compare "Luke.10.25-37" --module historical_context --live --blind --prompt-file "PROD_PROMPT.txt"
python -m textus_kb grounded-compare "Acts.2.1-13" --module exegesis --live --blind --prompt-file "PROD_PROMPT.txt"
python -m textus_kb grounded-compare "Acts.2.1-13" --module historical_context --live --blind --prompt-file "PROD_PROMPT.txt"
python -m textus_kb grounded-compare "Rom.8.28-30" --module exegesis --live --blind --prompt-file "PROD_PROMPT.txt"
python -m textus_kb grounded-compare "Rom.8.28-30" --module historical_context --live --blind --prompt-file "PROD_PROMPT.txt"
```

Each successful pair ≈ **2 provider calls** (A production + B grounded). KB prep cache may apply to grounded preparation; provider outputs are not cached.

**Important:** Use the real module production prompt for each module (exegesis vs historical_context may differ). If you export one shared file, ensure it matches the module under test.

## Review commands

After each generation, note `run_id` from the CLI JSON summary:

```powershell
python -m textus_kb review-show <run_id>
python -m textus_kb review-sources <run_id>
python -m textus_kb review-rate <run_id> `
  --overall B `
  --factual equal `
  --exegetical B `
  --historical equal `
  --clarity equal `
  --hallucination neither `
  --notes "..."
python -m textus_kb review-show <run_id> --reveal
```

### Review criteria (Phase 5E schema)

- `factual_accuracy_preference`: A | B | equal | unclear  
- `exegetical_usefulness_preference`: A | B | equal | unclear  
- `historical_grounding_preference`: A | B | equal | unclear  
- `clarity_style_preference`: A | B | equal | unclear  
- `hallucination_risk`: A | B | both | neither | unclear  
- `overall_preference`: A | B | equal | unclear  
- `reviewer_notes`: free text  

Updating the same `run_id` overwrites the review (one record per run; optional `review_updated_at`).

### Module emphasis (human checklist)

**Exegesis:** Greek claims, lexical notes, context, real exegetical value, no data-dump, natural Hungarian.

**Historical context:** concrete historical/cultural claims, places/people/groups, Samaritan/Jewish background, fewer unsourced specifics, usable for pastoral prep, not a lexicon entry dump.

### Reviewer notes template (optional aid)

- Mi volt egyértelműen jobb?
- Volt-e konkrét hibás vagy gyanús állítás?
- Volt-e hasznos új adat?
- Volt-e felesleges vagy túl technikai rész?
- Természetes maradt-e a magyar szöveg?
- Melyiket használnám inkább felkészüléshez?

## Blind review integrity

- Reviewer-facing report shows **Response A** / **Response B** only.
- Mapping (`production` / `grounded`) is withheld until `--reveal`.
- Use `--reveal` only after rating.

## Source / citation trace

```powershell
python -m textus_kb review-sources <run_id>
```

Shows human-readable source name, evidence type, article/title, canonical scope, license, attribution, and citation-ready flags. Uses Phase 5F `CitationRef`. Not mixed into Response B text.

## Campaign status

```powershell
python -m textus_kb review-campaign-status
python -m textus_kb review-campaign-status --json
```

Shows required/generated/reviewed/missing/failed/mock pairs, live provider call count, matrix, and readiness status.

Run completeness classes:

| Class | Counts for readiness? |
|-------|------------------------|
| mock | No |
| failed_generation | No (error-rate veto may still see failed live) |
| live_generated_unreviewed | No |
| live_reviewed | **Yes** (live + success + overall review) |

## Review summary / readiness

```powershell
python -m textus_kb review-summary --live-only
```

Phase 5F thresholds are unchanged (examples):

- ≥ 8 live reviewed pairs  
- ≥ 4 passages, both modules  
- ≥ 2 passages with both modules  
- ≥ 75% overall B or equal  
- factual B not repeatedly worse; hallucination B not repeatedly elevated  
- citation readiness veto when selected evidence exists but citation_ready_count is 0  

Statuses such as `needs_more_review` / `not_ready` / `insufficient_human_review_data` are acceptable until criteria are met. Readiness never auto-flips:

- `TEXTUS_KB_GROUNDED_ENABLED` (default false)
- `TEXTUS_KB_GROUNDED_STAGE_ALLOWED` (default false)

## Privacy / store

- Compare DB: `data/generated/kb_grounded_compare.sqlite3` (gitignored).
- May store A/B model outputs for explicit dev review.
- Must not store API keys, user identity, email, session credentials, production account metadata.
- Must not write into Phase 5B audit DB, production user history, or Supabase.

## Provider / model parity

Live path reuses `app.generate_text` for both A and B with the same call pattern. Tab labels are `grounded-compare:A` / `grounded-compare:B` for tracing. If production model selection is tab-dependent and differs by those labels, document that as a known parity limit and prefer wiring a fixed generate function when needed.

## What you must do manually

1. Export real production prompts per module.  
2. Run the 8 live commands one-by-one (cost control).  
3. Read each pair blind; rate; then reveal.  
4. Run campaign status + live-only review summary / readiness.  
5. Decide staging enablement later (not in Phase 5G).  

Do **not** retune grounded prompt, context selection, or budgets based on early weak reviews — finish the full round of 8 first.

## Phase 5G technical DoD

- Safe manual live campaign path  
- Campaign status + source trace CLIs  
- Readiness based only on human live reviews  
- Mock excluded; no automatic judge; no production enable  
- Tests green  

Professional Phase 5G closure happens only after you complete the manual live reviews and final readiness report.
