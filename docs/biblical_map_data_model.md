# Biblical Map Pilot Data Model

The pilot map data lives in JSON so it can be reviewed, versioned, and later
imported into a database without changing the Streamlit UI code.

## Files

- `data/biblical_places/pilot_places.json`: place records for the current pilot.
- `data/biblical_places/sources.json`: source registry used by place records.
- `data/biblical_places/passage_place_links.json`: data-driven passage-to-place index.
- `data/biblical_places/manual_locks.json`: hand-curated place ids protected from bulk overwrite.
- `biblical_map_passages.py`: loads the passage index and keeps overlap-based selection.
- `biblical_map_import/`: reusable download/parse/merge importer.
- `docs/biblical_place_import.md`: how to run and extend the importer.

## Required Place Fields

- `place_id`: stable internal identifier, unique.
- `name_hu`: Hungarian display name.
- `modern_country`: current country label for the card.
- `place_type`: short place type label.
- `identification_status`: one of `certain`, `probable`, `possible`, `disputed`, `unknown`.
- `latitude`, `longitude`: point coordinates.
- `geometry_type`: currently only `point`.
- `coordinate_source_id`: must exist in `sources.json`.
- `is_primary_demo_place`: exactly one place must be `true`.
- `source_ids`: every id must exist in `sources.json`.
- `translation_status`: one of `not_translated`, `machine_draft`, `human_translated`, `not_required`.
- `review_status`: one of `prototype`, `draft`, `needs_review`, `reviewed`, `approved`.

## Optional Place Fields

Identification: `name_en`, `ancient_names`, `original_names`, `transliterations`,
`modern_name`, `confidence_note_hu`.

Geography: `region_hu`, `ancient_region`.

Display: `card_summary_hu`, `card_summary_en`.

Background: `geography_hu`, `history_hu`, `political_context_hu`,
`economic_context_hu`, `social_context_hu`, `religious_context_hu`,
`archaeology_hu`, `biblical_significance_hu`, `modern_context_hu`.

External identifiers: `openbible_id`, `pleiades_id`, `step_id`, `wikidata_id`.

Missing optional values should be `null` or `[]`. The UI skips missing sections.

## Exegetical Notes

`exegetical_notes` is a list. Each item contains:

- `passage_reference`
- `title_hu`
- `note_hu`
- `limitations_hu`
- `source_ids`

Do not add exegetical content without reviewed source references.

## Sources

Each source record contains:

- `source_id`
- `provider`
- `title`
- `original_language`
- `source_url`
- `license`
- `attribution`
- `retrieved_at`
- `source_type`
- `reliability_tier`
- `notes_hu`

The current pilot source is `manual_demo_v1`. It is only a prototype source and
must not be presented as a scholarly authority. The UI displays it as
`Forrás: demonstrációs adat`.

## Adding A Place

1. Add a source to `sources.json`, unless an existing source really covers the record.
2. Add one object to `pilot_places.json` with a unique `place_id`.
3. Keep unknown background fields as `null` or `[]`.
4. Run the biblical map tests and JSON validation.

The structure supports a ten-place pilot. Use `scripts/import_biblical_places.py`
to refresh sparse records. Do not overwrite locked Corinth/Ephesus prose via bulk
import. Keep bare `Antiókhia` lookups ambiguous between Syrian and Pisidian places.

## Adding A Passage Link

Add the link in `biblical_map_passages.py` using the stable `place_id`. The link
must include a normalized reference, link type `primary_event_location`, a short
Hungarian reason, and source note `kézzel definiált demonstrációs kapcsolat`.

## Content Rule

Do not add historical, archaeological, geographical, or exegetical claims without
an explicit reviewed source. Leave the field empty instead.
