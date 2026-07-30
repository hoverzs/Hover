# Bibliai helyszínek bővített adatlapjai

Ez a dokumentum a bibliai térkép bővített helyszínadatlapjainak adatmodelljét,
forrásolási szabályait és későbbi bővítési folyamatát rögzíti.

## Adatmodell

Az alap katalógus továbbra is a `data/biblical_places/biblical_places_catalog.json`.
A hosszabb, tanulmányozási célú tartalom külön overlay-fájlban él:

`data/biblical_places/place_enrichments.json`

Az overlay canonical `place_id` alapján kapcsolódik az alap helyrekordhoz. A
loader elutasítja az ismeretlen vagy legacy `place_id` értéket, ezért a bővített
rekord nem hozhat létre rejtett új helyet és nem írja felül az alapkatalógust.

## Szakaszonkénti forrásolás

Minden nem üres tartalmi szakasznak saját `source_ids` listája van. Nem elég egy
közös rekordvégi forráslista. Az archaeology szakasz kihagyható vagy `null`, ha
nincs ellenőrizhető intézményi vagy szakmai forrás.

Támogatott szakaszok:

- `biblical_significance`
- `key_events`
- `ancient_geography`
- `historical_context`
- `archaeology`
- `modern_context`
- `identification_notes`
- `homiletical_context`

A `key_events` elemei külön `summary_hu`, `passage_refs` és `source_ids`
mezőkkel rendelkeznek.

## Source registry

A bővített adatlapok csak a `data/biblical_places/place_enrichment_sources.json`
fájlban szereplő forrásokra hivatkozhatnak. A registry minimális mezői:

- `source_id`
- `title`
- `institution`
- `source_type`
- `identifier`
- `license`
- `attribution`
- `allowed_use`
- `reliability_scope`
- `notes_hu`

Nem kerülhet a registrybe ellenőrizetlen blog, általános weboldal vagy licencileg
bizonytalan, hosszú szövegátvételre csábító forrás. All-rights-reserved forrásnál
csak saját, rövid magyar összefoglalás használható.

## Review és státuszmezők

A szakaszok `confidence` értéke: `high`, `medium`, `low`.

A szakaszok `review_status` értéke: `source_backed`, `needs_review`.

A teljes profil `profile_tier` értéke: `featured`, `high`, `medium`, `basic`.

## Prioritási pontszám

A `data/biblical_places/place_enrichment_priority.json` újragenerálható lista.
Pontozási tényezők:

- passage-place előfordulásszám;
- külön bibliai könyvek száma;
- route-stop előfordulás;
- kapcsolódó route-ok száma;
- azonosítási státusz;
- forrásgazdagság;
- kézi pilot-prioritás;
- meglévő gazdag kézi tartalom.

Ez a lista adja a későbbi 100-200 helyes enrichment batch kiindulópontját.

## Pilot helyek

Az első pilot húsz helye:

Jeruzsálem, Betlehem, Názáret, Kapernaum, Jerikó, Sikem, Bétel, Hebrón,
Beérseba, Sínai-hegy, Kádés-Barnea, Babilon, Ninive, szíriai Antiókhia,
Efezus, Korinthus, Filippi, Athén, tengeri Cézárea és Róma.

A feloldási döntéseket a
`data/biblical_places/place_enrichment_pilot_resolution.json` rögzíti.

## Tartalmi korlátok

A bővített kártyák tömörek maradnak. Irányadó maximumok:

- biblical_significance: 700 karakter;
- ancient_geography: 600 karakter;
- historical_context: 700 karakter;
- archaeology: 600 karakter;
- modern_context: 350 karakter;
- identification_notes: 500 karakter;
- homiletical_context: 650 karakter;
- key_events: legfeljebb 6 esemény a pilotban.

## Homiletikai kontextus

A `homiletical_context` nem kész prédikáció és nem modern alkalmazás. Csak rövid,
tényszerű megfigyelés lehet arról, hogy a hely történeti, társadalmi vagy
földrajzi háttere hogyan segíti a bibliai szöveg értelmezését.

Nem tartalmazhat forrás nélküli lelki tanulságot, erkölcsi következtetést vagy
kitalált szimbolikát.

## Új hely hozzáadása

1. Ellenőrizd, hogy a hely canonical `place_id` értéke aktív-e.
2. Ellenőrizd a source registryben a szükséges forrásokat.
3. Minden szakaszhoz adj saját `source_ids` listát.
4. Futtasd a loader-validációt és a célzott teszteket.
5. Frissítsd a pilot vagy batch riportot.

## Source registry bővítése

Új forrás csak akkor vehető fel, ha ismert a licenc, az attribution, a
megbízhatósági kör és az engedélyezett felhasználás. Régészeti állításhoz
intézményi, múzeumi, ásatási, egyetemi vagy tudományos forrás kell.

## Későbbi batch-folyamat

A következő 100-200 hely kiválasztása a prioritási lista alapján történjen.
A batch először csak review-queue legyen, majd szakmai ellenőrzés után kerüljön
az overlaybe. Az alapkatalógust nem kell hosszú szövegekkel terhelni.
