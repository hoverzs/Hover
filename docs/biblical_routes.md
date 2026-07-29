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

## UI-integráció

A bibliai térkép expanderén belül két külön nézet van:

- `Helyszínek`: az aktuális igerészhez kapcsolódó konkrét helyeket mutatja a meglévő passage-place index alapján.
- `Bibliai útvonalak`: teljes bibliai route rekordokat jelenít meg a route-loaderből.

A két nézet ugyanabban a térképes expanderben él, de nem keveri a működési módokat. A Helyszínek nézet nem rajzolja ki automatikusan a teljes útvonalat; csak kompakt jelzést ad, ha az aktuális passage egy nagyobb route része.

## Passage -> Route kapcsolat

A passage-route kapcsolat nem külön kézi mapping. A UI a route stopok `passage_refs` mezőiből építi fel memóriában:

1. betölti a route rekordokat;
2. végigmegy a stopok `passage_refs` értékein;
3. a meglévő bibliai hivatkozásparserrel ellenőrzi az átfedést;
4. visszaadja a kapcsolódó route és stop párokat.

Ez kezeli az azonos verset, a versszakasz-átfedést és a fejezet-szintű lekérdezést is. Példa: `ApCsel 13` több induló állomást ad vissza, `ApCsel 14` pedig a visszaúti állomásokkal is összekapcsolódik.

## Stopkiemelés

Ha a Helyszínek nézetben az aktuális passage route-stophoz kapcsolódik, megjelenik egy kompakt blokk:

- kapcsolódó útvonal neve;
- érintett állomások;
- `A teljes útvonal megtekintése` gomb.

A gomb a `Bibliai útvonalak` nézetre vált, kiválasztja az érintett route-ot, és a passage-hez tartozó stopokat kiemelésre adja át. A váltás Streamlit session state-ben történik:

- `_biblical_map_active_view`
- `_biblical_map_selected_route_id`
- `_biblical_map_highlighted_route_stop_ids`
- `_biblical_map_selected_route_stop_id`

## Sematikus route-vonalak

A route-nézetben a segmentek közvetlenül az egymás utáni stopok koordinátáit kötik össze. Ez nem modern útvonaltervezés, nem Google Maps route, és nem pontos ókori nyomvonalrekonstrukció. A tengeri és szárazföldi szakaszok visszafogottan eltérő színnel jelennek meg:

- `land`: szárazföldi, barna árnyalatú sematikus vonal;
- `sea`: tengeri, kék árnyalatú sematikus vonal.

A viewport az útvonal összes stopja alapján számolódik.

## Új útvonal UI-ba kerülésének feltételei

Egy új route akkor jelenhet meg a UI-ban, ha:

1. átmegy a `biblical_routes.py` loader-validáción;
2. minden stop aktív `place_id`-ra mutat;
3. minden stopnak van koordinátával rendelkező helyrekordja;
4. a stop `passage_refs` értékei formailag parse-olhatók;
5. a segmentek létező `stop_id`-kra mutatnak;
6. a `geometry_status` világosan jelzi, hogy sematikus vagy rekonstruált geometriáról van-e szó;
7. van legalább egy `source_ids` hivatkozás a meglévő forrásjegyzékben.
