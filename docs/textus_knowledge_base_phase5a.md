# TEXTUS Knowledge Base — Phase 5A

Phase 5A integrates KB into Textus in **shadow mode only**: production generation stays unchanged, while a parallel KB pipeline produces diagnostics artifacts for `exegesis` and `historical_context`.

## Integration boundary

- Production entry point: `app.py::generate_section()`
- Canonical/passage input source: existing `st.session_state["last_igehely"]` flow (no duplicated parsing path added in app)
- Exegesis start: `generate_section("exegesis")`
- Historical start: `generate_section("history")`
- Shadow hook location: immediately **after** production `generate_text(...)` result is stored, so prompt/output rendering behavior is unchanged

## Feature flag

- Name: `TEXTUS_KB_SHADOW_ENABLED`
- Default: `false`
- Behavior:
  - `false` -> no shadow KB call
  - `true` -> shadow retrieval + context build run for `exegesis` and `history`

## Shadow flow

```
same passage
  -> retrieve()
  -> Evidence Packet
  -> build_context_from_evidence(profile)
  -> KBShadowArtifact
  -> session artifact store + structured kb_shadow debug entry
```

Profiles:
- `exegesis`
- `historical_context`

Theology is intentionally excluded in 5A.

## Shadow artifact schema

Implemented in `textus_kb/shadow.py` (`KBShadowArtifact`):

- `success`
- `module`, `profile`
- `passage_input`, `passage_canonical`
- `evidence_packet_build_id`
- `context_packet`
- `source_ids`, `evidence_ids`
- `token_estimate`
- `retrieval_warnings`
- `retrieval_duration_ms`
- `context_build_duration_ms`
- `evidence_item_count`, `entity_count`, `study_notes_count`, `dictionary_count`
- `selected_context_count`, `source_count`
- `comparison`:
  - `production_prompt_chars`
  - `production_output_chars`
  - `kb_context_tokens`
  - `shadow_evidence_coverage`
  - `source_count`
  - `warnings`
- `error`
- `status` (`success | degraded | error`)

Raw Evidence Packet is not persisted into production logs.

## Logging and failure isolation

- Shadow events are logged via existing `_debug_log_append(...)` with `tab="kb_shadow"` and statuses:
  - `KB_SHADOW_OK`
  - `KB_SHADOW_FAIL`
  - `KB_SHADOW_EXCEPTION`
- Shadow exceptions are swallowed in hook layer and only logged as structured debug error.
- Production section generation always continues unchanged.

## Dev CLI / report

New command in `python -m textus_kb`:

- Single artifact:
  - `python -m textus_kb shadow "Jn 4,1-42" --module exegesis`
- Benchmark report:
  - `python -m textus_kb shadow "John.4.1-42" --benchmark`

The benchmark mode returns artifacts for:
- `John.4.1-42`
- `Luke.10.25-37`
- `Acts.2.1-13`
- `Rom.8.28-30`

with both `exegesis` and `historical_context`.

## Benchmark results

| Passage | Module | Evidence | Entities | SN | Dict | Selected | Tokens | Retrieval | Context |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| John.4.1-42 | exegesis | 130 | 38 | 24 | 78 | 27 | 3165 | 2929 ms | 99 ms |
| John.4.1-42 | historical_context | 130 | 38 | 24 | 78 | 19 | 2528 | 1484 ms | 66 ms |
| Luke.10.25-37 | exegesis | 112 | 24 | 11 | 81 | 27 | 3160 | 1117 ms | 75 ms |
| Luke.10.25-37 | historical_context | 112 | 24 | 11 | 81 | 16 | 2517 | 1116 ms | 58 ms |
| Acts.2.1-13 | exegesis | 130 | 34 | 6 | 80 | 30 | 3194 | 1091 ms | 85 ms |
| Acts.2.1-13 | historical_context | 130 | 34 | 6 | 80 | 18 | 2537 | 1146 ms | 66 ms |
| Rom.8.28-30 | exegesis | 87 | 7 | 1 | 72 | 20 | 1607 | 817 ms | 37 ms |
| Rom.8.28-30 | historical_context | 87 | 7 | 1 | 72 | 12 | 2166 | 792 ms | 34 ms |

## Production invariance (5A)

- Hook is post-generation and does not alter prompt assembly or output rendering.
- `tests/test_textus_kb/test_phase5a_shadow_integration.py` verifies:
  - flag default false wiring
  - shadow hook is gated and attached after production assignment
  - shadow artifact generation for both profiles
  - failure-isolated shadow behavior
- `tests/test_textus_kb/test_shadow_integration_contract.py` verifies runtime contract:
  - same production prompt + params with flag false/true
  - production call survives forced shadow exception
  - flag false performs zero shadow work (shadow runner not invoked)

## Known limitations

- In-app shadow storage is session-local (`_kb_shadow_runs`), no persistence.
- No async offloading in 5A; timings are measured and logged first.
- OT full production generation is still constrained by existing local linguistic stack; shadow CLI/report remains available.

