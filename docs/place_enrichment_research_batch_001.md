# Place enrichment research batch 001

Ez a dokumentum az első, 50 helyes enrichment batch **szigorú**
forráskutatási és evidence-integritási szabályait rögzíti. A munka nem
végleges adatlapimport: nem módosítja a `place_enrichments.json` fájlt, nem
ír kész történeti vagy homiletikai szöveget, és nem hoz létre útvonaladatot.

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

- `batch_001_source_candidates.json`
- `batch_001_evidence_packets.json`
- `batch_001_evidence_integrity_audit.json`
- `batch_001_source_validation_report.json`
- `batch_001_source_acquisition_queue.json`
- `batch_001_coverage_report.json`
- `batch_001_strict_coverage_report.json`
- `batch_001_biblical_draft_ready.json`
- `batch_001_partial_profile_ready.json`
- `batch_001_source_backed_ready.json`
- `batch_001_featured_candidates.json`
- `batch_001_ready_for_drafting.json` (legacy, max. 20, szigorú readiness szerint)
- `batch_001_research_blocked.json`
- `cache/batch_001_research_cache.json`

## Source strength osztályok

Minden evidence item kap `source_strength_class` mezőt:

| Osztály | Jelentés | Tipikus használat |
|---|---|---|
| `A_biblical_primary` | bibliai szöveg / passage-place | `biblical_significance`, `key_events` |
| `B_structured_gazetteer` | OpenBible / Pleiades / koordináta / névváltozat | azonosítás, basic geography |
| `C_external_institutional` | UNESCO, múzeum, hatóság, ásatás | history / archaeology / modern |
| `D_external_scholarly` | lektorált / tudományos publikáció | history / archaeology |
| `E_contextual_secondary` | ellenőrizhető, de kontextuális másodlagos | részleges támogatás |
| `F_inference` | világosan jelölt következtetés | ritka |
| `G_unsupported` | nincs levezethető forrás | **nem** `usable_for_drafting` |

A `G_unsupported` item:

- nem számít section coverage-nek;
- nem draftolható;
- az integrity auditban megjelenik.

## Sectionönkénti forrásküszöb

- **biblical_significance**: legalább egy `A` pontos `passage_refs`-szel; puszta előfordulásszám nem elég.
- **key_events**: minden eseményhez `A` + konkrét refs.
- **ancient_geography**: `B` szükséges; részletes állításhoz `C`/`D`/`E` is. Csak koordináta/`place_type` → basic/partial, nem source-backed.
- **historical_context**: csak `C` / `D` / erős `E`. Bibliai hivatkozás vagy OpenBible önmagában nem elég.
- **archaeology**: kizárólag `C` vagy `D`.
- **modern_context**: hivatalos / örökségi / intézményi / ellenőrizhető modern gazetteer.
- **identification_notes**: `B`/`C`/`D` vagy ezek összevetése.
- **homiletical_context**: helyspecifikus megfigyelés + `C`/`D`/erős `E`; nem route-lista és nem általános mondat.

## Readiness osztályok

A `ready_for_drafting` **nem** jelent automatikus source-backed státuszt.

- `biblical_draft_ready`: bibliai significance vagy key events megbízható; ≥2 `A`; nincs record-resolution blokk.
- `partial_profile_ready`: ≥2 érdemi section; ≥1 section `C`/`D`/`E` támogatással; nincs unsupported claim.
- `source_backed_profile_ready`: ≥3 érdemi section; ≥2 független külső `C/D/E`; közülük ≥1 `C` vagy `D`; biblical ellenőrzött; nincs `G`.
- `featured_candidate`: ≥4 érdemi section; ≥2 helyspecifikus `C`/`D`; history vagy archaeology helyspecifikus; nincs needs_review / record-resolution blokk.

Csak `A+B` evidence:

- lehet `biblical_draft_ready`;
- **nem** lehet `source_backed_profile_ready` vagy `featured_candidate`.

## Candidate validáció és registry-promóció

A `batch_001_source_validation_report.json` minden jelöltnél rögzíti:

- URL státusz;
- identity / institution / relevance / claim support;
- license;
- `validation_status`: `approved` | `citation_only` | `metadata_only` | `unclear` | `rejected`.

Promóció a `place_enrichment_sources.json` fájlba **csak** `approved` vagy `citation_only` státusz után történik.
Nem promótálunk forrást a forrásszám növelése érdekében.

Ebben a körben citation-only promócióra került:

- UNESCO Ancient Thebes (`unesco_ancient_thebes_87`)
- UNESCO Tyre (`unesco_tyre_299`)
- UNESCO Old City of Jerusalem (`unesco_jerusalem_148`)
- UNESCO Petra (`unesco_petra_326`)

Nem promótált:

- Pleiades index oldal (`metadata_only`);
- COGAT archaeology unit (`unclear`, live fetch blokkolva);
- katalógus Pleiades ID-k live tartalmi ellenőrzés nélkül (`unclear`).

## Acquisition queue

A `batch_001_source_acquisition_queue.json` a tényleges hiányokra épül.
A batch research queue feladatait `(place_id, section, missing_strength)` szerint
deduplikálja. Régió-jellegű rekordoknál az archaeology nem erőltetett
településspecifikus állításként, de a hiány taskként megmaradhat.

## Korlátozott internetelérés

Ha egy intézményi URL nem érhető el (botvédelem, Cloudflare), a builder:

- nem jelent sikeres külső kutatást arra a forrásra;
- `unclear` / `rejected` validációt ír;
- acquisition taskot hagy nyitva;
- a readiness státuszt a ténylegesen ellenőrzött evidence alapján csökkenti.

## Drafting fázis belépési feltétele

- Biblical draft: a hely szerepel a `batch_001_biblical_draft_ready.json` listán.
- Részleges profil: `batch_001_partial_profile_ready.json`.
- Source-backed / featured: a megfelelő lista nem üres, és minden használt
  forrás registryben van érvényes licenc-/citation mezővel.
- Végleges enrichment próza és `place_enrichments.json` módosítás csak a
  következő, külön drafting fázisban történhet.

## Batch 001 szigorú állapot (audit után)

- evidence packet: 50;
- biblical_draft_ready: 50;
- partial_profile_ready: kis számú, intézményi C/E támogatással rendelkező hely;
- source_backed_profile_ready: 0;
- featured candidate: 0;
- kutatási / record-resolution blocked: 8;
- a korábbi „50/50 source-backed” állítás visszavonva.

## Újragenerálás

```powershell
python scripts\build_place_enrichment_research.py --batch-number 1
```

A builder determinisztikus és idempotens: ugyanazon bemenetek mellett ugyanazokat
a JSON kimeneteket írja vissza, és a már promótált registry-forrásokat nem
duplikálja.
