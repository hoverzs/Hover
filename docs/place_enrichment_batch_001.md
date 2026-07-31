# Place enrichment batch 001

Ez a batch az első 50 helyes, forráskutatásra előkészített enrichment munkalista.
Ebben a fázisban nem készült új történeti, régészeti vagy homiletikai tartalom,
és nem történt internetes forráskutatás.

## Cél

A batch célja, hogy a következő tartalmi munkakörhöz determinisztikus,
ellenőrizhető kutatási manifestet adjon. A lista nem kész adatlapokat tartalmaz,
hanem azt mondja meg, mely canonical helyekhez milyen szakaszokhoz kell forrást
keresni.

## Kiválasztási algoritmus

A builder a `place_enrichment_priority.json` soraiból indul ki, és kizárja:

- a már feldolgozott húsz pilothelyet;
- legacy vagy inaktív `place_id` értékeket;
- a `needs_record_resolution` státuszú rekordokat;
- a nem primary profile-group tagokat;
- hiányos koordinátájú rekordokat.

A rangsorolás tényezői:

- `total_score`;
- `research_priority`;
- `passage_count`;
- `biblical_book_count`;
- `route_stop_count`;
- `route_count`;
- `identification_status`;
- `source_gap_count`;
- `content_quality_score`;
- forráskészültség;
- manual priority;
- profile-group review állapot.

Az azonos fizikai profile-groupból alapértelmezésben csak a primary rekord
kerülhet aktív batchbe.

## Az 50 hely

A teljes manifest:

`data/biblical_places/enrichment_batches/place_enrichment_batch_001.json`

Az első húsz kiválasztott hely:

1. Egyiptom (`egypt`)
2. Jordán (`jordan`)
3. Moáb (`moab_1`)
4. Sion (`zion`)
5. Asszíria (`assyria`)
6. Edóm (`edom`)
7. Gileád (`gilead_1`)
8. Kánaán (`canaan`)
9. Ammón (`ammon`)
10. Tírusz (`tyre`)
11. Samária (`samaria_1`)
12. Negev (`negeb`)
13. Káldea (`chaldea`)
14. Libanon (`lebanon`)
15. Gilgál (`gilgal_1`)
16. Sodoma (`sodom`)
17. Nagy-tenger (`great_sea`)
18. Júdea (`judea_1`)
19. Nílus (`nile`)
20. Gáza (`gaza`)

## Fő forrástípusok

A research queue csak source-kategóriákat és kutatási kérdéseket rögzít, URL-eket
nem talál ki. Gyakori szükséges forrástípusok:

- biblical_text_dataset;
- academic_gazetteer;
- official_geographical_source;
- university_project;
- museum;
- peer_reviewed_publication;
- official_archaeological_site;
- excavation_project;
- heritage_authority.

OpenBible koordinátaadat önmagában nem elegendő régészeti vagy történeti
szakaszhoz.

## Blocked helyek

Blocked lista:

`data/biblical_places/enrichment_batches/place_enrichment_batch_001_blocked.json`

Biztosan dokumentált record-resolution helyek:

- `mount_sinai`;
- `antioch_syria`;
- `caesarea`.

Profile-group miatt blokkolt nem primary rekordok például Jerikó és Sínai
kapcsolódó tagjai.

## Profile-group szabályok

A batch-builder nem von össze rekordokat. Ha egy hely profile-group tagja, az
aktív batchbe csak a primary rekord kerülhet. A nem primary tagok blocked listába
kerülnek, hogy később külön rekordfeloldási döntés után lehessen velük dolgozni.

## Későbbi forráskutatás

A kutatási queue:

`data/biblical_places/enrichment_batches/place_enrichment_batch_001_research_queue.json`

Minden task külön sectionre vonatkozik, és `pending` státusszal indul. A későbbi
tartalmi munka csak ellenőrzött források után töltheti ki az enrichment
szakaszokat.

## Exportok

- JSON manifest: `data/biblical_places/enrichment_batches/place_enrichment_batch_001.json`
- Research queue: `data/biblical_places/enrichment_batches/place_enrichment_batch_001_research_queue.json`
- Blocked lista: `data/biblical_places/enrichment_batches/place_enrichment_batch_001_blocked.json`
- CSV áttekintő: `data/biblical_places/enrichment_batches/place_enrichment_batch_001.csv`
- Riport: `data/biblical_places/enrichment_batches/place_enrichment_batch_001_report.json`
