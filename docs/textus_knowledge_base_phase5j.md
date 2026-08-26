# Textus Knowledge Base — Phase 5J-B

Separate comparative hallucination risk from reliability severity for staging readiness.

## Problem

`hallucination_risk=both` mixed non-blocking interpretive overclaim with genuine
factual/historical reliability issues. The legacy
`hallucination_grounded_elevated_ratio` counted all `both` as grounded-elevated,
which overstated grounded regression on Phase 5I.

## Taxonomy

Unchanged comparative field:

- `hallucination_risk`: A | B | both | neither | unclear

New severity fields on `HumanReview` / `review_json`:

- `reliability_issue`: none | non_blocking_overclaim | blocking_reliability | unclear
- `reliability_category` (optional): factual_error | unsupported_concrete_claim |
  anachronism | source_scope_mismatch | invented_entity_date_status |
  internal_output_leak | linguistic_overclaim |
  theological_exegetical_overinterpretation | other

## Readiness semantics

Reported (compatibility):

- `hallucination_grounded_elevated_ratio` = share of
  `grounded_only` + `both` (unchanged formula; **not** a veto after 5J-B)

Readiness veto:

- `grounded_blocking_reliability_ratio` = share of live reviewed runs where
  mapping-aware hallucination is `grounded_only` or `both` **and**
  `reliability_issue=blocking_reliability`
- Denominator: all live reviewed successful pairs (when fully classifiable)
- Threshold: ≤ 0.20 (`max_grounded_blocking_reliability_ratio`)

Fail closed:

- If grounded participates in risk (`grounded_only` / `both`) and
  `reliability_issue` is missing or `unclear` →
  veto `missing_or_unclear_reliability_issue:N`
- Never treat legacy missing severity as safe

## CLI

```powershell
python -m textus_kb review-rate <run_id> `
  --hallucination both `
  --reliability non_blocking_overclaim `
  --reliability-category linguistic_overclaim `
  --database data/generated/kb_grounded_compare_phase5i.sqlite3
```

## Migration

Existing Phase 5G/5I reviews remain valid without severity fields.
Phase 5I must be **manually** annotated before readiness can be recomputed under
the new veto. See:

`data/generated/kb_grounded_compare/phase5i/phase5j_b_annotation_required.json`

Do not auto-infer severity from free-text notes.
