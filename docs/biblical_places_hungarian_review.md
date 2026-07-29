# Bibliai helyek magyarítási munkalistája

- Teljes munkalista: `data\biblical_places\hungarian_review_queue.json` (1302 rekord)
- Első feldolgozási köteg: `data\biblical_places\hungarian_review_batch_001.json` (100 rekord)

## Prioritási szabály

A rendezés determinisztikus. Elöl állnak a legtöbb bibliai hivatkozással rendelkező helyek, ezen belül a pilotban szereplő rekordok, majd a biztosabb azonosítású és mai helyhez kapcsolható rekordok. A bizonytalan, vitatott vagy audit által valószínű duplikátumnak jelölt rekordok nem vesznek el, de `review_notes_hu` figyelmeztetést kapnak.

## Későbbi magyar kártyaleírás szabálya

- Legfeljebb 1-2 rövid mondat legyen.
- Elsősorban az ókori hely szerepét és a mai azonosítást tartalmazza.
- Ne legyen esszészerű.
- Ne ismételje fölöslegesen a nevet, országot és koordinátát.
- Bizonytalan azonosítást ne állítson biztos tényként.
- Csak ellenőrzött strukturált adatra és forrásokra támaszkodjon.

A script nem ír vissza a teljes katalógusba, és nem tölti ki automatikusan a javasolt magyar mezőket.
