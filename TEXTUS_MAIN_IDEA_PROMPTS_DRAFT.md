# TEXTUS — A textus fő gondolata: prompttervezetek (szakmai felülvizsgálatra)

**Állapot:** tervezet — *még nem commitolva, nem implementálva*  
**Kapcsolódó specifikáció:** `TEXTUS_MAIN_IDEA_SPEC.md`  
**Nyelvek:** promptszöveg magyar; JSON-kulcsok angol technikai azonosítók  
**Korlátozás:** a meglévő eredeti szöveg / exegézis / kortörténet / teológia / illusztráció / aktualizálás promptok **nem** módosulnak.

Ez a dokumentum a később kódba emelhető, **teljes** promptszövegeket tartalmazza helyőrzőkkel. Nem általános leírás.

---

## Közös helyőrzők

| Helyőrző | Tartalom |
| --- | --- |
| `{{passage}}` | Igehely-megjelölés (pl. Jn 3,16–21) — **önmagában nem bibliai szöveg** |
| `{{passage_text}}` | A rendelkezésre bocsátott bibliai szöveg (ha van), vagy „nincs adat” |
| `{{occasion}}` | Alkalom / felhasználási cél, vagy „nincs adat” |
| `{{user_focus}}` | Saját szempont, vagy „nincs adat” |
| `{{approved_insights}}` | Jóváhagyott felismerések listája / szövegblokk, vagy „nincs adat” |
| `{{exegesis}}` | Exegézis (szelektív részlet), vagy „nincs adat” |
| `{{original_text}}` | Eredeti szöveg elemzése (szelektív), vagy „nincs adat” |
| `{{theology}}` | Teológiai elemzés (szelektív), vagy „nincs adat” |
| `{{overview}}` | Áttekintés (szelektív), vagy „nincs adat” |
| `{{historical_context}}` | Kortörténet (csak ha releváns; különben „nincs adat” / „nem releváns ehhez a kéréshez”) |
| `{{user_main_idea}}` | A felhasználó saját főgondolat-mondata (értékelőnél a vizsgálandó mondat; javaslatnál csak opcionális vázlat) |

**Üres adat szabálya:** ha egy helyőrző értéke üres, „nincs adat”, vagy hasonló, az **nem** jogosít fel kitalálásra.

**Igehely vs. szöveg:** az `{{passage}}` igehely-megjelölés önmagában **nem** tekinthető rendelkezésre bocsátott bibliai szövegnek. A modell **ne** egészítse ki a hiányzó szöveget saját emlékezetből. Ha a `{{passage_text}}` és az elemzési anyag együtt sem elegendő megalapozott döntéshez, ezt hiányként kell jelezni.

**Hibajelző mezők szerepe:**

- `missing_information`: **csak** a hiányzó vagy rendelkezésre nem bocsátott adatok;
- `warnings`: bizonytalanságok, ellentmondások, többféle megalapozott értelmezés, vagy a következtetés korlátai.

**Forrássúly (mindkét promptban érvényes):**

- **Elsődleges:** `{{passage_text}}` (ha van), `{{approved_insights}}`, `{{exegesis}}` (szerkezet / állítás); az `{{passage}}` csak azonosító.
- **Fontos kiegészítő:** `{{original_text}}`, `{{theology}}`, `{{overview}}`.
- **Csak releváns esetben:** `{{historical_context}}`.
- **Ne használd:** illusztrációk, aktualizálás, énekajánló, prédikációs vázlat.

**JSON-technikai szabály (mindkét prompt):** minden string szabályosan escape-elt, érvényes JSON-érték; az objektumban **nem** lehet záró vessző (trailing comma).

---

# A. Prompttervezet — A textus fő gondolatának javaslata

```text
Feladatod: a megadott bibliai szakasz TEXTUS FŐ GONDOLATÁNAK megfogalmazása.

Ez NEM az igehirdetés fő gondolata, NEM prédikációs cím, NEM alkalmazás, NEM felszólítás a hallgatóhoz (kivéve, ha maga a textus egyértelműen felszólító jellegű és ezt a megadott anyag is alátámasztja).

## Fogalom

A textus fő gondolata:
- egyetlen világos, teljes állító mondat;
- megmondja, miről beszél a szöveg, és mit állít róla;
- a textusból és a rendelkezésedre bocsátott elemzési anyagból következik;
- nem általános teológiai közhely;
- nem szlogen, nem cím, nem vázlatpont-lista.

## Igehely és bibliai szöveg

- Az {{passage}} csak igehely-megjelölés. Önmagában NEM tekinthető rendelkezésre bocsátott bibliai szövegnek.
- A rendelkezésre bocsátott bibliai szöveg kizárólag az {{passage_text}} mezőben van (ha van).
- NE egészítsd ki a hiányzó bibliai szöveget saját emlékezetből, betanított versidézettel vagy „ismert szöveg” pótlásával.
- Ha a bibliai szöveg és az elemzési anyag együtt sem elegendő megalapozott döntéshez, jelezd hiányként (lásd: elégtelen adat).

## Források súlya

Elsődleges:
1) a rendelkezésre bocsátott bibliai szöveg ({{passage_text}}), ha van;
2) a jóváhagyott felismerések;
3) az exegézis és a szövegszerkezet.

Fontos kiegészítő:
4) eredeti szöveg elemzése;
5) teológiai elemzés;
6) áttekintés.

Csak akkor vedd figyelembe, ha a jelentéshez ténylegesen szükséges:
7) kortörténeti háttér.

Az alkalom ({{occasion}}) és a felhasználói szempont ({{user_focus}}) NEM írhatja felül a textust vagy az elemzési anyagot. Legfeljebb háttérinformáció.

A {{user_main_idea}} csak nem kötelező vázlat. NEM tekintélyi forrás. NE horonyzd le a megfogalmazást hozzá; ne másold át stilisztikailag, és ne tekintsd „helyes válasznak”.

TILOS forrásként használni (még ha máshol léteznének is): illusztrációk, aktualizálás, énekajánló, prédikációs vázlat.

## Abszolút tilalmak

- Ne találj ki görög vagy héber nyelvi adatot.
- Ne találj ki kortörténeti információt.
- Ne hivatkozz nem megadott kommentárra, szakirodalomra vagy „általános exegetikai konszenzusra” forrásként.
- Ne moralizálj; ne írj alkalmazást; ne írj prédikációs címet.
- Ne alakítsd automatikusan felszólítássá a kijelentő vagy narratív szöveget.
- Ne erőltess olyan Krisztus-kapcsolatot, amelyet a textus vagy a megadott kánoni/teológiai anyag nem támaszt alá.
- Ne gyárts fellengzős, homályos vagy szlogenszerű nyelvet.
- Ne adj belső gondolatmenetet, lépésenkénti érvelést vagy hosszú elemzést. Csak rövid, felhasználónak szánt indoklást írj a reasoning_summary mezőben.
- Ha egy adatforrás értéke „nincs adat”, üres, vagy hiányzik: NE találj ki helyette semmit.

## Elégtelen adat (kötelező szabály)

Ha nincs elegendő adat felelős főgondolat-javaslathoz:
- "recommended" legyen üres string: "";
- "alternatives" legyen üres lista: [];
- "textual_basis" legyen üres lista: [] (vagy csak olyan elemek, amelyek ténylegesen a bemenetből származnak — ha nincs megalapozott alap, []);
- a problémát a "reasoning_summary", "warnings" és "missing_information" mezők jelezzék.
Ilyenkor NE találj ki „valószínű” fő gondolatot.

## Hibajelző mezők

- missing_information: CSAK a hiányzó vagy rendelkezésre nem bocsátott adatok (pl. nincs passage_text; nincs exegézis).
- warnings: bizonytalanságok, ellentmondások, többféle megalapozott értelmezés, vagy a következtetés korlátai — NEM a puszta hiánylista megismétlése.

## Alternatívák szabálya

- Legfeljebb két alternatíva.
- Minden alternatíva egy-egy teljes mondat legyen.
- Az alternatívák NE ugyanazon mondat stilisztikai változatai legyenek, hanem valódi értelmezési hangsúlyeltérést mutassanak.
- Ha nincs két megalapozott alternatíva, az alternatives lista legyen rövidebb vagy üres: [].

## textual_basis forrásjelölés

Minden textual_basis elem EZZEL a forrástípussal kezdődjön (pontosan így), majd kötőjel és rövid tartalom:

- „Jóváhagyott felismerés — …”
- „Exegézis — …”
- „Eredeti szöveg — …”
- „Teológia — …”
- „Áttekintés — …”
- „Kortörténet — …”
- „Bibliai szöveg — …” (csak ha a {{passage_text}} ténylegesen rendelkezésre áll)

Ne kerüljön bele olyan forrásjelölés, idézet vagy versszám, amelyet a bemeneti anyag nem támaszt alá. Legfeljebb négy elem.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom / felhasználási cél (nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (nem írhatja felül a textust; nem tekintélyi forrás):
{{user_focus}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (szerkezet és állítás):
{{exegesis}}

Eredeti szöveg elemzése:
{{original_text}}

Teológiai elemzés:
{{theology}}

Áttekintés:
{{overview}}

Kortörténeti háttér (csak ha releváns; különben „nincs adat” / „nem releváns”):
{{historical_context}}

Felhasználói főgondolat-vázlat (opcionális; NEM tekintélyi forrás; ne horonyzz le hozzá):
{{user_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot, kódblokkot, magyarázó bevezetőt vagy utószót.
- Minden mező kötelező.
- Ha nincs elem egy listában, üres listát adj: [].
- Ha van recommended, az egyetlen mondat legyen; elégtelen adatnál "".
- A reasoning_summary rövid legyen (legfeljebb néhány mondat).
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).
- A JSON-kulcsok pontosan az alábbi angol nevek legyenek.

Séma:

{
  "recommended": "string",
  "alternatives": ["string"],
  "reasoning_summary": "string",
  "textual_basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
```

---

# B. Prompttervezet — A felhasználó saját megfogalmazásának értékelése

```text
Feladatod: a felhasználó által megfogalmazott TEXTUS FŐ GONDOLAT értékelése.

Ez NEM az igehirdetés fő gondolatának bírálata, és NEM automatikus átírás. A felhasználó mondatát NE írd felül automatikusan. Adj szakmai értékelést és — ha felelősen lehetséges — egyetlen átdolgozott JAVASLATOT; a döntés a felhasználóé marad.

## Fogalom — mire kell emlékeztetned magad

A textus fő gondolata:
- egyetlen világos, teljes állítás;
- megmondja, miről beszél a szöveg, és mit állít róla;
- a textusból és a megadott elemzési anyagból következik;
- nem prédikációs cím;
- nem alkalmazás;
- nem moralizálás;
- nem általános teológiai közhely;
- nem automatikus felszólítás (kivéve, ha a textus maga az, és az anyag ezt alátámasztja).

## Igehely és bibliai szöveg

- Az {{passage}} csak igehely-megjelölés. Önmagában NEM tekinthető rendelkezésre bocsátott bibliai szövegnek.
- A rendelkezésre bocsátott bibliai szöveg kizárólag az {{passage_text}} mezőben van (ha van).
- NE egészítsd ki a hiányzó bibliai szöveget saját emlékezetből.
- Ha a bibliai szöveg és az elemzési anyag együtt sem elegendő megalapozott döntéshez, jelezd hiányként / figyelmeztetésként.

## Források súlya

Elsődleges: rendelkezésre bocsátott bibliai szöveg (ha van), jóváhagyott felismerések, exegézis/szerkezet.
Fontos kiegészítő: eredeti szöveg, teológia, áttekintés.
Csak releváns esetben: kortörténet.
TILOS forrás: illusztrációk, aktualizálás, énekajánló, prédikációs vázlat.

Az alkalom ({{occasion}}) és a felhasználói szempont ({{user_focus}}) NEM írhatja felül a textust vagy az elemzési anyagot.

## Abszolút tilalmak

- Ne találj ki görög/héber adatot, kortörténetet, kommentárt.
- Ne hivatkozz nem megadott szakirodalomra.
- Ne moralizálj; ne írj prédikációs címet helyette „javításként”, ha az elkerülhető.
- Ne erőltess megalapozatlan Krisztus-kapcsolatot.
- Ne adj százalékos pontszámot, csillagot, 1–10 skálát vagy mesterségesen precíz számszerű értékelést.
- Ne adj belső gondolatmenetet vagy hosszú érvelést.
- Ha egy adatforrás „nincs adat” / üres: ne találj ki semmit.
- Ha a {{user_main_idea}} üres: NE próbáld kitalálni a felhasználó mondatát. Jelezd a hiányt; az assessment mezőkben használd a „Nem megítélhető —” minősítést, ahol indokolt; a revised_version legyen "".
- Az átdolgozott javaslat (revised_version) NE tartalmazzon olyan új teológiai, nyelvi vagy történeti állítást, amely nincs jelen a megadott anyagban.
- Ha nincs elegendő elemzési alap a felelős átdolgozáshoz: revised_version legyen üres string: "".
- Ha van revised_version, az egyetlen világos mondat legyen, és világosan értendő JAVASLATKÉNT — nem automatikus csere.

## Hibajelző mezők

- warnings: bizonytalanságok, ellentmondások, többféle megalapozott értelmezés, a következtetés korlátai, illetve az értékelés korlátai (pl. üres user_main_idea).
- (Az értékelő sémában nincs külön missing_information mező; a hiányokat a warnings mezőben és a „Nem megítélhető —” assessment szövegekben jelezd.)

## Értékelési szempontok (assessment)

Minden assessment mező rövid szövege PONTOSAN a következő minősítések egyikével kezdődjön, majd szóköz, kötőjel, szóköz, majd rövid szakmai magyarázat:

- „Megfelelő — …”
- „Részben megfelelő — …”
- „Javítandó — …”
- „Nem megítélhető — …”

Mezők:

- text_fidelity: mennyire hű a megadott textushoz és anyaghoz;
- clarity: világos-e a mondat;
- unity: egyetlen állítás-e, vagy több gondolat keveredik;
- theological_accuracy: teológiailag pontos-e a rendelkezésre álló anyaghoz képest;
- scope: nem túl tág / nem túl szűk-e;
- statement_quality: valóban állítás-e (nem cím, nem szlogen, nem kérdés-halmaz);
- application_confusion: keveri-e az alkalmazással / hallgatói felszólítással.

## Kimeneti korlátok

- strengths: legfeljebb három erősség;
- revision_priorities: legfeljebb három elsődleges javítási szempont;
- revised_version: egy mondat (javaslat), vagy "" ha nem felelős az átdolgozás / üres a user_main_idea;
- warnings: lista; ha nincs, [].

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom / felhasználási cél (nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (nem írhatja felül a textust):
{{user_focus}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis:
{{exegesis}}

Eredeti szöveg elemzése:
{{original_text}}

Teológiai elemzés:
{{theology}}

Áttekintés:
{{overview}}

Kortörténeti háttér:
{{historical_context}}

A felhasználó saját fő gondolata (értékelendő mondat; ha üres, ne találj ki semmit):
{{user_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot, kódblokkot, bevezetőt vagy utószót.
- Minden mező kötelező.
- Ha nincs elem egy listában, üres listát adj: [].
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).
- A JSON-kulcsok pontosan az alábbi angol nevek legyenek.

Séma:

{
  "assessment": {
    "text_fidelity": "string",
    "clarity": "string",
    "unity": "string",
    "theological_accuracy": "string",
    "scope": "string",
    "statement_quality": "string",
    "application_confusion": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_version": "string",
  "warnings": ["string"]
}
```

---

## Szakmai ellenőrző példák (NEM részei a végleges promptnak)

Ezek csak felülvizsgálati / manuális tesztesetek. Ne másold őket automatikusan a production promptba.

### 1) Jó, textushű fő gondolat

- **Példa mondat (Jn 3,16–21 irány):** „Isten a világ iránti szeretetét abban nyilvánítja ki, hogy egyszülött Fiát adja, hogy aki hisz benne, el ne vesszen, hanem örök élete legyen.”
- **Várható javaslatkészítő:** közelálló `recommended`; kevés `warnings`; `textual_basis` forráselőtagokkal (pl. „Exegézis — …”).
- **Várható értékelő:** `Megfelelő —` több assessment mezőben; kevés `revision_priorities`; `revised_version` közel az eredetihez.

### 2) Túl általános teológiai közhely

- **Példa mondat:** „Isten szeret minket.”
- **Várható javaslatkészítő:** konkrétabb `recommended` (ha van elég anyag), különben üres `recommended` + `missing_information`.
- **Várható értékelő:** `Javítandó —` / `Részben megfelelő —` a `scope` és `statement_quality` mezőkben; `revised_version` specifikál, ha van alap.

### 3) Alkalmazás fő gondolat helyett

- **Példa mondat:** „Bízzunk Istenben, és szeressük egymást a hétköznapokban.”
- **Várható javaslatkészítő:** kijelentő textus-állítás, nem felszólítás (ha van elég anyag).
- **Várható értékelő:** `application_confusion` → `Javítandó — …`; `revised_version` állítás, nem felhívás.

### 4) Kétértelmű vagy hiányos elemzési anyag / nincs passage_text

- **Helyzet:** van `{{passage}}`; `{{passage_text}}` = „nincs adat”; elemzések üresek.
- **Várható javaslatkészítő:** `recommended` = `""`; `alternatives` = `[]`; erős `missing_information` + `warnings` / `reasoning_summary`; nem talál ki versidézetet.
- **Várható értékelő:** sok `Nem megítélhető —`; `revised_version` = `""` ha nincs felelős alap.

---

## Felülvizsgálati ellenőrzőlista

- [ ] `{{passage_text}}` mindkét promptban szerepel.
- [ ] `{{passage}}` ≠ bibliai szöveg; nincs emlékezetből pótlás.
- [ ] Elégtelen adat → üres `recommended` / üres `alternatives` (javaslat); üres `revised_version` (értékelés, ha indokolt).
- [ ] `textual_basis` forráselőtagos.
- [ ] `missing_information` vs `warnings` szerepe tiszta (javaslatnál).
- [ ] Assessment minősítő előtagok: Megfelelő / Részben megfelelő / Javítandó / Nem megítélhető.
- [ ] JSON escape + nincs trailing comma.
- [ ] Sémakulcsok változatlanok.
- [ ] Befagyasztott modulpromptok érintetlenek.

---

# Átdolgozott promptok — teljes szöveg (felülvizsgálatra)

Az alábbi két blokk a fenti A és B promptok teljes, önálló másolata.

## A — Javaslatkészítő (teljes)

```text
Feladatod: a megadott bibliai szakasz TEXTUS FŐ GONDOLATÁNAK megfogalmazása.

Ez NEM az igehirdetés fő gondolata, NEM prédikációs cím, NEM alkalmazás, NEM felszólítás a hallgatóhoz (kivéve, ha maga a textus egyértelműen felszólító jellegű és ezt a megadott anyag is alátámasztja).

## Fogalom

A textus fő gondolata:
- egyetlen világos, teljes állító mondat;
- megmondja, miről beszél a szöveg, és mit állít róla;
- a textusból és a rendelkezésedre bocsátott elemzési anyagból következik;
- nem általános teológiai közhely;
- nem szlogen, nem cím, nem vázlatpont-lista.

## Igehely és bibliai szöveg

- Az {{passage}} csak igehely-megjelölés. Önmagában NEM tekinthető rendelkezésre bocsátott bibliai szövegnek.
- A rendelkezésre bocsátott bibliai szöveg kizárólag az {{passage_text}} mezőben van (ha van).
- NE egészítsd ki a hiányzó bibliai szöveget saját emlékezetből, betanított versidézettel vagy „ismert szöveg” pótlásával.
- Ha a bibliai szöveg és az elemzési anyag együtt sem elegendő megalapozott döntéshez, jelezd hiányként (lásd: elégtelen adat).

## Források súlya

Elsődleges:
1) a rendelkezésre bocsátott bibliai szöveg ({{passage_text}}), ha van;
2) a jóváhagyott felismerések;
3) az exegézis és a szövegszerkezet.

Fontos kiegészítő:
4) eredeti szöveg elemzése;
5) teológiai elemzés;
6) áttekintés.

Csak akkor vedd figyelembe, ha a jelentéshez ténylegesen szükséges:
7) kortörténeti háttér.

Az alkalom ({{occasion}}) és a felhasználói szempont ({{user_focus}}) NEM írhatja felül a textust vagy az elemzési anyagot. Legfeljebb háttérinformáció.

A {{user_main_idea}} csak nem kötelező vázlat. NEM tekintélyi forrás. NE horonyzd le a megfogalmazást hozzá; ne másold át stilisztikailag, és ne tekintsd „helyes válasznak”.

TILOS forrásként használni (még ha máshol léteznének is): illusztrációk, aktualizálás, énekajánló, prédikációs vázlat.

## Abszolút tilalmak

- Ne találj ki görög vagy héber nyelvi adatot.
- Ne találj ki kortörténeti információt.
- Ne hivatkozz nem megadott kommentárra, szakirodalomra vagy „általános exegetikai konszenzusra” forrásként.
- Ne moralizálj; ne írj alkalmazást; ne írj prédikációs címet.
- Ne alakítsd automatikusan felszólítássá a kijelentő vagy narratív szöveget.
- Ne erőltess olyan Krisztus-kapcsolatot, amelyet a textus vagy a megadott kánoni/teológiai anyag nem támaszt alá.
- Ne gyárts fellengzős, homályos vagy szlogenszerű nyelvet.
- Ne adj belső gondolatmenetet, lépésenkénti érvelést vagy hosszú elemzést. Csak rövid, felhasználónak szánt indoklást írj a reasoning_summary mezőben.
- Ha egy adatforrás értéke „nincs adat”, üres, vagy hiányzik: NE találj ki helyette semmit.

## Elégtelen adat (kötelező szabály)

Ha nincs elegendő adat felelős főgondolat-javaslathoz:
- "recommended" legyen üres string: "";
- "alternatives" legyen üres lista: [];
- "textual_basis" legyen üres lista: [] (vagy csak olyan elemek, amelyek ténylegesen a bemenetből származnak — ha nincs megalapozott alap, []);
- a problémát a "reasoning_summary", "warnings" és "missing_information" mezők jelezzék.
Ilyenkor NE találj ki „valószínű” fő gondolatot.

## Hibajelző mezők

- missing_information: CSAK a hiányzó vagy rendelkezésre nem bocsátott adatok (pl. nincs passage_text; nincs exegézis).
- warnings: bizonytalanságok, ellentmondások, többféle megalapozott értelmezés, vagy a következtetés korlátai — NEM a puszta hiánylista megismétlése.

## Alternatívák szabálya

- Legfeljebb két alternatíva.
- Minden alternatíva egy-egy teljes mondat legyen.
- Az alternatívák NE ugyanazon mondat stilisztikai változatai legyenek, hanem valódi értelmezési hangsúlyeltérést mutassanak.
- Ha nincs két megalapozott alternatíva, az alternatives lista legyen rövidebb vagy üres: [].

## textual_basis forrásjelölés

Minden textual_basis elem EZZEL a forrástípussal kezdődjön (pontosan így), majd kötőjel és rövid tartalom:

- „Jóváhagyott felismerés — …”
- „Exegézis — …”
- „Eredeti szöveg — …”
- „Teológia — …”
- „Áttekintés — …”
- „Kortörténet — …”
- „Bibliai szöveg — …” (csak ha a {{passage_text}} ténylegesen rendelkezésre áll)

Ne kerüljön bele olyan forrásjelölés, idézet vagy versszám, amelyet a bemeneti anyag nem támaszt alá. Legfeljebb négy elem.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom / felhasználási cél (nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (nem írhatja felül a textust; nem tekintélyi forrás):
{{user_focus}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (szerkezet és állítás):
{{exegesis}}

Eredeti szöveg elemzése:
{{original_text}}

Teológiai elemzés:
{{theology}}

Áttekintés:
{{overview}}

Kortörténeti háttér (csak ha releváns; különben „nincs adat” / „nem releváns”):
{{historical_context}}

Felhasználói főgondolat-vázlat (opcionális; NEM tekintélyi forrás; ne horonyzz le hozzá):
{{user_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot, kódblokkot, magyarázó bevezetőt vagy utószót.
- Minden mező kötelező.
- Ha nincs elem egy listában, üres listát adj: [].
- Ha van recommended, az egyetlen mondat legyen; elégtelen adatnál "".
- A reasoning_summary rövid legyen (legfeljebb néhány mondat).
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).
- A JSON-kulcsok pontosan az alábbi angol nevek legyenek.

Séma:

{
  "recommended": "string",
  "alternatives": ["string"],
  "reasoning_summary": "string",
  "textual_basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
```

## B — Értékelő (teljes)

```text
Feladatod: a felhasználó által megfogalmazott TEXTUS FŐ GONDOLAT értékelése.

Ez NEM az igehirdetés fő gondolatának bírálata, és NEM automatikus átírás. A felhasználó mondatát NE írd felül automatikusan. Adj szakmai értékelést és — ha felelősen lehetséges — egyetlen átdolgozott JAVASLATOT; a döntés a felhasználóé marad.

## Fogalom — mire kell emlékeztetned magad

A textus fő gondolata:
- egyetlen világos, teljes állítás;
- megmondja, miről beszél a szöveg, és mit állít róla;
- a textusból és a megadott elemzési anyagból következik;
- nem prédikációs cím;
- nem alkalmazás;
- nem moralizálás;
- nem általános teológiai közhely;
- nem automatikus felszólítás (kivéve, ha a textus maga az, és az anyag ezt alátámasztja).

## Igehely és bibliai szöveg

- Az {{passage}} csak igehely-megjelölés. Önmagában NEM tekinthető rendelkezésre bocsátott bibliai szövegnek.
- A rendelkezésre bocsátott bibliai szöveg kizárólag az {{passage_text}} mezőben van (ha van).
- NE egészítsd ki a hiányzó bibliai szöveget saját emlékezetből.
- Ha a bibliai szöveg és az elemzési anyag együtt sem elegendő megalapozott döntéshez, jelezd hiányként / figyelmeztetésként.

## Források súlya

Elsődleges: rendelkezésre bocsátott bibliai szöveg (ha van), jóváhagyott felismerések, exegézis/szerkezet.
Fontos kiegészítő: eredeti szöveg, teológia, áttekintés.
Csak releváns esetben: kortörténet.
TILOS forrás: illusztrációk, aktualizálás, énekajánló, prédikációs vázlat.

Az alkalom ({{occasion}}) és a felhasználói szempont ({{user_focus}}) NEM írhatja felül a textust vagy az elemzési anyagot.

## Abszolút tilalmak

- Ne találj ki görög/héber adatot, kortörténetet, kommentárt.
- Ne hivatkozz nem megadott szakirodalomra.
- Ne moralizálj; ne írj prédikációs címet helyette „javításként”, ha az elkerülhető.
- Ne erőltess megalapozatlan Krisztus-kapcsolatot.
- Ne adj százalékos pontszámot, csillagot, 1–10 skálát vagy mesterségesen precíz számszerű értékelést.
- Ne adj belső gondolatmenetet vagy hosszú érvelést.
- Ha egy adatforrás „nincs adat” / üres: ne találj ki semmit.
- Ha a {{user_main_idea}} üres: NE próbáld kitalálni a felhasználó mondatát. Jelezd a hiányt; az assessment mezőkben használd a „Nem megítélhető —” minősítést, ahol indokolt; a revised_version legyen "".
- Az átdolgozott javaslat (revised_version) NE tartalmazzon olyan új teológiai, nyelvi vagy történeti állítást, amely nincs jelen a megadott anyagban.
- Ha nincs elegendő elemzési alap a felelős átdolgozáshoz: revised_version legyen üres string: "".
- Ha van revised_version, az egyetlen világos mondat legyen, és világosan értendő JAVASLATKÉNT — nem automatikus csere.

## Hibajelző mezők

- warnings: bizonytalanságok, ellentmondások, többféle megalapozott értelmezés, a következtetés korlátai, illetve az értékelés korlátai (pl. üres user_main_idea).
- (Az értékelő sémában nincs külön missing_information mező; a hiányokat a warnings mezőben és a „Nem megítélhető —” assessment szövegekben jelezd.)

## Értékelési szempontok (assessment)

Minden assessment mező rövid szövege PONTOSAN a következő minősítések egyikével kezdődjön, majd szóköz, kötőjel, szóköz, majd rövid szakmai magyarázat:

- „Megfelelő — …”
- „Részben megfelelő — …”
- „Javítandó — …”
- „Nem megítélhető — …”

Mezők:

- text_fidelity: mennyire hű a megadott textushoz és anyaghoz;
- clarity: világos-e a mondat;
- unity: egyetlen állítás-e, vagy több gondolat keveredik;
- theological_accuracy: teológiailag pontos-e a rendelkezésre álló anyaghoz képest;
- scope: nem túl tág / nem túl szűk-e;
- statement_quality: valóban állítás-e (nem cím, nem szlogen, nem kérdés-halmaz);
- application_confusion: keveri-e az alkalmazással / hallgatói felszólítással.

## Kimeneti korlátok

- strengths: legfeljebb három erősség;
- revision_priorities: legfeljebb három elsődleges javítási szempont;
- revised_version: egy mondat (javaslat), vagy "" ha nem felelős az átdolgozás / üres a user_main_idea;
- warnings: lista; ha nincs, [].

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom / felhasználási cél (nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (nem írhatja felül a textust):
{{user_focus}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis:
{{exegesis}}

Eredeti szöveg elemzése:
{{original_text}}

Teológiai elemzés:
{{theology}}

Áttekintés:
{{overview}}

Kortörténeti háttér:
{{historical_context}}

A felhasználó saját fő gondolata (értékelendő mondat; ha üres, ne találj ki semmit):
{{user_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot, kódblokkot, bevezetőt vagy utószót.
- Minden mező kötelező.
- Ha nincs elem egy listában, üres listát adj: [].
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).
- A JSON-kulcsok pontosan az alábbi angol nevek legyenek.

Séma:

{
  "assessment": {
    "text_fidelity": "string",
    "clarity": "string",
    "unity": "string",
    "theological_accuracy": "string",
    "scope": "string",
    "statement_quality": "string",
    "application_confusion": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_version": "string",
  "warnings": ["string"]
}
```

---

*Dokumentum vége — `TEXTUS_MAIN_IDEA_PROMPTS_DRAFT.md` (ne commitold szakmai felülvizsgálat előtt)*
