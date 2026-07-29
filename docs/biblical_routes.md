# Bibliai útvonalak adatmodellje

Ez a réteg bibliai útvonalakat ír le a meglévő bibliai helykatalógusra építve. Nem hoz létre párhuzamos helymodellt: minden állomás `place_id` értéke a `data/biblical_places/biblical_places_catalog.json` aktív rekordjára mutat.

## Fájlok

- `data/biblical_routes/biblical_routes.json`: route-katalógus.
- `biblical_routes.py`: UI-tól független loader és validátor.
- `tests/test_biblical_routes.py`: célzott route-adatmodell tesztek.

## Route mezők

- `route_id`: stabil, egyedi útvonal-azonosító.
- `name_hu`, `name_en`: megjelenítési név.
- `short_description_hu`: rövid, felhasználói leírás.
- `route_category`: útvonaltípus.
- `primary_passage_refs`: elsődleges bibliai szakaszok.
- `chronology_label_hu`, `chronology_sort_key`: időrendi címke és rendezési kulcs.
- `certainty`: az útvonal egészének bizonyossági szintje.
- `geometry_status`: az útvonal geometriai státusza.
- `source_ids`: a meglévő `sources.json` rekordjaira mutató forráshivatkozások.
- `review_status`, `review_notes_hu`: szerkesztési és review metaadat.
- `evidence_model`: rövid metaadat arról, hogy a rekord bibliai állomássorrendet, történeti rekonstrukciót vagy sematikus térképi vonalat képvisel.
- `stops`: rendezett állomáslista.
- `segments`: opcionális kapcsolatok két stop között.

## Stop mezők

- `order`: 1-től induló, folytonos sorrend.
- `stop_id`: route-on belül egyedi stop-azonosító.
- `place_id`: aktív bibliai helyrekord azonosítója.
- `place_name_override_hu`: opcionális megjelenítési pontosítás, például két Antiókhia megkülönböztetésére.
- `passage_refs`: az állomáshoz tartozó bibliai hivatkozások.
- `event_summary_hu`: rövid eseményösszegzés.
- `certainty`: stop szintű bizonyosság.
- `stop_type`: például `explicit_place`, `embarkation`, `disembarkation`, `destination`, `return_stop`.
- `source_notes_hu`: rövid forrás- vagy értelmezési megjegyzés.

Ugyanaz a `place_id` több stopban is szerepelhet, ha a bibliai út oda- és visszaútja külön állomásként nevezi meg ugyanazt a helyet.

## Segment mezők

- `from_stop_id`, `to_stop_id`: létező stopokra mutató hivatkozások.
- `certainty`: segment szintű bizonyosság.
- `segment_type`: például `land`, `sea`, `river`, `mixed`, `schematic`, `unknown`.
- `geometry_status`: a vonal geometriai státusza.
- `source_notes_hu`: rövid megjegyzés arról, mit állít és mit nem állít a segment.
- `waypoints`, `geometry`: későbbi bővítéshez fenntartott mezők.

## Enumok

`certainty`:

- `certain`
- `probable`
- `possible`
- `disputed`
- `unknown`
- `mixed`

`geometry_status`:

- `schematic`
- `reconstructed`
- `approximate`
- `exact`
- `unavailable`

`route_category`:

- `missionary_journey`
- `patriarchal_journey`
- `exodus`
- `wilderness_journey`
- `royal_campaign`
- `prophetic_journey`
- `deportation`
- `return_from_exile`
- `ministry_journey`
- `other`

## Állomássorrend és rekonstrukció

A modell külön kezeli a bibliai szövegben megnevezett állomások sorrendjét, a történeti útvonalrekonstrukciót és a térképi vonal geometriai státuszát. A `schematic` segment nem állítja, hogy két hely között pontos ókori útvonal ismert; csak azt jelzi, hogy a két megnevezett állomás között a felhasználói térképen összekötés rajzolható.

## Pilot: Pál első missziói útja

Pilot route:

- `route_id`: `paul_first_missionary_journey`
- elsődleges szakasz: `ApCsel 13,1-14,28`
- állomásszám: 15
- segmentszám: 14

Stoplista:

1. `antioch_syria_departure` -> `antioch_syria`
2. `seleucia_departure` -> `seleucia`
3. `salamis_arrival` -> `salamis`
4. `paphos` -> `paphos`
5. `perga_outbound` -> `perga`
6. `antioch_pisidia_outbound` -> `antioch_2`
7. `iconium_outbound` -> `iconium`
8. `lystra_outbound` -> `lystra`
9. `derbe` -> `derbe`
10. `lystra_return` -> `lystra`
11. `iconium_return` -> `iconium`
12. `antioch_pisidia_return` -> `antioch_2`
13. `perga_return` -> `perga`
14. `attalia_return` -> `attalia`
15. `antioch_syria_return` -> `antioch_syria`

## Új route hozzáadása

1. Csak aktív `place_id`-ket használj a teljes katalógusból.
2. Ne használj legacy azonosítót új adatban.
3. Add meg a bibliai szakaszokat a `primary_passage_refs` és stop szintű `passage_refs` mezőkben.
4. A stop `order` legyen folytonos és növekvő.
5. Minden segment létező `stop_id`-ra mutasson.
6. Ha a pontos útvonal nincs forrásolva, a segment `geometry_status` értéke legyen `schematic`.
7. Futtasd a route-loader teszteket és a meglévő térképes teszteket.

## Ismert korlátok

- Nincs még térképi útvonalrajzolás.
- A pilot segmentek sematikusak, nem rekonstruált ókori utak.
- Nincs távolságszámítás vagy útvonal-optimalizálás.
- A legacy `place_id` feloldás csak kompatibilitási mód; új adatokban aktív `place_id` használata kötelező.
