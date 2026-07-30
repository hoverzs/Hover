# Place enrichment research batch 001

Ez a dokumentum az első, 50 helyes enrichment batch forráskutatási kimeneteit
rögzíti. A munka nem végleges adatlapimport: nem módosítja a
`place_enrichments.json` fájlt, nem ír kész történeti vagy homiletikai
szöveget, és nem hoz létre útvonaladatot.

## Bemenetek

A kutatási builder a következő helyi adatrétegekből dolgozik:

- `data/biblical_places/enrichment_batches/place_enrichment_batch_001.json`
- `data/biblical_places/enrichment_batches/place_enrichment_batch_001_research_queue.json`
- `data/biblical_places/enrichment_batches/place_enrichment_batch_001_blocked.json`
- `data/biblical_places/place_enrichment_sources.json`
- `data/biblical_places/place_profile_groups.json`
- `data/biblical_places/place_enrichment_priority.json`
- `data/biblical_places/biblical_places_catalog.json`
- `data/biblical_places/passage_place_links.json`
- `data/biblical_routes/biblical_routes.json`

## Kimenetek

A kutatási kimenetek:

- `data/biblical_places/enrichment_research/batch_001_source_candidates.json`
- `data/biblical_places/enrichment_research/batch_001_evidence_packets.json`
- `data/biblical_places/enrichment_research/batch_001_coverage_report.json`
- `data/biblical_places/enrichment_research/batch_001_ready_for_drafting.json`
- `data/biblical_places/enrichment_research/batch_001_research_blocked.json`
- `data/biblical_places/enrichment_research/cache/batch_001_research_cache.json`

## Source candidate szabály

A `batch_001_source_candidates.json` nem végleges forrásregiszter. A jelöltek
két forrásból származnak:

- a már meglévő, helyi `place_enrichment_sources.json` regiszterből;
- korlátozott webes forrásfelderítésből, ahol csak intézményi vagy szakmai
  jellegű forrásjelölt került be.

Új központi source rekord ebben a körben nem lett automatikusan promózva. A
coverage report ezért `approved_registry_source_promotions: 0` értéket rögzít.

## Evidence packet szabály

Az `batch_001_evidence_packets.json` helyenként tartalmaz bizonyítékblokkokat a
következő enrichment szakaszokhoz:

- `biblical_significance`
- `key_events`
- `ancient_geography`
- `historical_context`
- `archaeology`
- `modern_context`
- `identification_notes`
- `homiletical_context`

Az evidence itemek csak kontrollált állításokat tartalmaznak: passage-place
kapcsolatot, strukturált katalógusadatot, route-stop kapcsolatot vagy
forrásjelöltre mutató metaadatot. Ezekből később lehet szövegtervezetet írni,
de ez még nem publikálható enrichment tartalom.

## Batch 001 állapota

A generált coverage report szerint:

- aktív evidence packet: 50;
- source candidate: 5;
- evidence item: 621;
- draftingre előkészített rekord: 50;
- source-backed előkészített rekord: 50;
- featured candidate: 0;
- kutatási vagy record-resolution blocked tétel: 8.

A legnagyobb fennmaradó forráshiány a történeti háttér és a régészet. Ez azért
marad nyitva, mert a meglévő strukturált katalógusadat és az OpenBible
geokódolás nem helyettesít szakmai történeti vagy régészeti forrást.

## Webes forrásfelderítés

A körben korlátozott webes forrásfelderítés történt. A felvett jelöltek:

- UNESCO World Heritage Centre: Ancient Thebes with its Necropolis
- Pleiades: Ancient Places gazetteer
- Israel Civil Administration Archaeology Unit

Ezek jelöltként vagy citation-only kontextusként szerepelnek. A szövegírási
fázisban minden rekordnál külön ellenőrizni kell, hogy az adott forrás közvetlen
vagy csak kontextuális bizonyítéknak használható-e.

## Blokkolt tételek

A `batch_001_research_blocked.json` a batchből kizárt record-resolution és
profile-group problémákat is tartalmazza. Ezeket nem oldja fel a kutatási
builder, és nem von össze rekordokat.

## Újragenerálás

Parancs:

```powershell
python scripts\build_place_enrichment_research.py --batch-number 1
```

A builder determinisztikus: ugyanazon bemenetek mellett ugyanazokat a JSON
kimeneteket írja vissza.
