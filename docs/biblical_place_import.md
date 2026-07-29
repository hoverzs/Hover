# Biblical place import

## Goal

Build a reproducible ten-place pilot from open geocoding sources while preserving
hand-curated Corinth and Ephesus records.

## Run

```bash
# Dry-run (no writes)
python scripts/import_biblical_places.py --dry-run

# Download raw sources (if needed) and write pilot JSON
python scripts/import_biblical_places.py

# Use already downloaded raw files
python scripts/import_biblical_places.py --no-download

# Second-pass idempotency check
python scripts/import_biblical_places.py --no-download --check-idempotent
```

Raw files land in `data/biblical_places/raw/`.

## Sources

Primary:

- OpenBible Bible Geocoding Data (`ancient.jsonl`, `modern.jsonl`)
  - License: CC-BY-4.0
  - https://github.com/openbibleinfo/Bible-Geocoding-Data

Supplementary:

- Pleiades place JSON (where a trusted `pleiades_id` is known)
  - License: CC-BY-3.0
  - https://pleiades.stoa.org/

Not used in this pilot pass:

- STEPBible Data for original-script names. OpenBible STEP links are often
  uncertain or incomplete for these places, so the importer does not invent
  STEP linkages.

## Manual record protection

Locked place ids:

- `corinth`
- `ephesus`

Policy (`data/biblical_places/manual_locks.json`):

- non-empty protected content fields are never overwritten
- null/missing fields may be filled
- `source_ids` are unioned without duplicates
- `review_status` is never auto-promoted to `reviewed` / `approved`

## Antioch handling

- Pilot place: `antioch_syria` (Orontes / Syrian Antioch)
- Known separate place: `antioch_pisidia` (catalogued, not in the 10-place pilot file)
- Bare Hungarian lookup for `Antiókhia` returns both candidates and must not
  silently collapse them (`resolve_places_by_hungarian_name`)

## Adding another pilot place

1. Add a `PilotPlaceSpec` in `biblical_map_import/pilot_catalog.py`.
2. Prefer an explicit OpenBible `ancient` id.
3. Add a Pleiades id only when confidently identified.
4. Re-run the importer.
5. Add passage links in `data/biblical_places/passage_place_links.json`.

## Scaling to hundreds of places

1. Keep the same download + parse + merge pipeline.
2. Expand the catalog from a reviewable CSV/JSON of place specs.
3. Leave detailed background/exegetical fields null until human review.
4. Keep `review_status=needs_review` for imported shells.

## What still needs scholarly review

- Short card summaries
- Identification confidence language
- Any later historical/exegetical prose
- Passage coverage beyond the pilot index
