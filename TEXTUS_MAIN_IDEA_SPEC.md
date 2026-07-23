# TEXTUS — „A textus fő gondolata”: javaslat és értékelés

**Dokumentum típusa:** szakmai és műszaki specifikáció (M1 → első új MI-alapú funkció)  
**Állapot:** tervezés — *implementáció még nem kezdődött*  
**Dátum:** 2026-07-21  
**Kapcsolódó kód (csak olvasva):** `textus_workshop_ui.py`, `textus_workshop_data.py`, `workspace_data.py`, `app.py` (`generate_text`)

---

## Cél és hatókör

Új MI-segéd funkció a **Textusműhely → „A textus fő gondolata”** szakaszban:

1. **Javaslatok készítése** a már meglévő elemzési eredményekből;
2. **Saját megfogalmazás értékelése** emberi szövegre.

A funkció **nem** írja felül automatikusan a felhasználó mondatát, **nem** módosítja a befagyasztott elemzőmodulok promptjait, és **nem** keveri össze a textus állítását az igehirdetés fő gondolatával vagy a prédikáció címével.

A jelenlegi kézi mező (`text_main_idea` / `text_main_idea_status`) és az `approved_insights` megmarad; az MI csak javaslatot és értékelést ad.

---

## 1. Fogalmi meghatározás

### 1.1 Mi a „textus fő gondolata”?

**A textus fő gondolata** egyetlen, világos, teljes mondat, amely megfogalmazza:

- **miről** beszél az igeszakasz, és
- **mit állít** róla.

Követelmények:

| Szabály | Magyarázat |
| --- | --- |
| Egy mondat | Nem lista, nem vázlatpontok, nem bekezdés. |
| Állítás | Állító (vagy a textus saját műfajához illő) mondat — nem cím, nem szlogen. |
| Textushűség | A szakaszból következik; nem „általános keresztény igazság”. |
| Nem prédikáció | Még nem hallgatóra szabott üzenet, nem „alkalmazás”. |
| Nem felszólítás | Csak ha maga a textus felszólító jellegű (pl. imperatívusz). |
| Nem közhely | Kerüli a túl tág formulákat („Isten szeret minket” önmagában). |
| Nem cím | Nem „A megtérés öröme”, hanem állítás a szövegről. |

**Munkadefiníció (belső):**

> Egy mondatban: *mit állít ez az igeszakasz Istenről / emberről / a szöveg központi tárgyáról*, a szakasz szerkezetéből és tartalmából levezethetően.

### 1.2 Fogalmi elhatárolások

| Fogalom | Mi ez? | Példa-irány |
| --- | --- | --- |
| **Textus fő gondolata** | A szakasz központi *állítása* | „Isten a bűnös felé forduló szeretetét a kereszthalálban nyilvánítja ki.” |
| **Teológiai hangsúly** | Egy (vagy több) hangsúlyos teológiai szál az elemzésből | kegyelem, hit, ítélet — *nem* feltétlenül egy mondat |
| **Igehirdetés fő gondolata** | A prédikáció egységes *üzenete* a hallgatóknak | már alkalom- és gyülekezet-érzékeny |
| **Prédikáció címe** | Rövid, figyelemfelkeltő elnevezés | marketing / liturgiai cím |
| **Alkalmazás** | „Mit jelent ez ma nekünk?” | etika, életvezetés, felhívás |

Az új funkció **csak** a textus fő gondolatával foglalkozik. Az igehirdetés fő gondolata későbbi (Igehirdetési műhely) témája.

---

## 2. Jelenlegi adatforrások feltérképezése

### 2.1 Forrástábla

| Forrás | Kulcs / elérési út | Fontosság a fő gondolathoz | Mindig kell? | Szerep | Zaj / hossz kockázat |
| --- | --- | --- | --- | --- | --- |
| Igehely | `igehely_input` (widget) → `last_igehely` (tartós) | **Kritikus** | Igen (üresen nem induljon a javaslat) | Azonosító, szöveghatár | Alacsony |
| Alkalom | `alkalom_input` / `last_alkalom` | Alacsony–közepes | Nem | Kontextus (ne keverje prédikációba) | Közepes, ha „prédikációs” irányba húz |
| Stílus | `stilus_input` / `last_stilus` | Alacsony | Nem | Inkább igehirdetésre tartozik | **Magas zaj** — fő gondolatnál csak háttérjelzés, vagy kihagyható |
| Saját szempont | `sajat_input` / `last_sajat` | Közepes | Nem | Felhasználói fókusz; nem írhatja felül a textust | Közepes |
| Áttekintés | `overview` | Közepes | Nem | Gyors kontextus | Közepes–magas (hosszú) |
| Eredeti szöveg | `original_text` | Magas | Nem | Kulcsszavak, jelentésárnyalat | **Magas** — teljes dump kerülendő |
| Exegézis | `exegesis` | **Nagyon magas** | Nem, de erősen ajánlott | Szerkezet, állítás | Magas — szelektív kivágás kell |
| Kortörténet | `history` | Alacsony–közepes | Nem | Csak ha a jelentéshez kell | Magas zaj, ha mindig megy |
| Teológia | `theology` | Magas | Nem | Hangsúlyok, kánoni összefüggés | Magas — tömörítés kell |
| Jóváhagyott felismerések | `text_workshop["approved_insights"][]` | **Nagyon magas** (ha van) | Nem | Emberi szűrés utáni jelzőfények | Alacsony (rövid tételek) |
| Kézi fő gondolat | `text_workshop["text_main_idea"]` + `text_main_idea_status` | Magas az *értékeléshez* | Értékelésnél igen | A vizsgálandó mondat | Alacsony |
| Illusztráció / aktualizálás | `illustrations`, `actualization` | **Nem javasolt** | — | Alkalmazás felé húz | Magas zaj — **ne kerüljön** a főgondolat-kontextusba |
| Vázlat / ének / sorozat | `outline*`, `songs`, … | Nem | — | Homiletika | Kizárandó |

### 2.2 Tartós vs. widget

- Tartós `project_data` / workspace: `last_*`, `overview`, `exegesis`, …, `text_workshop` (`workspace_data.py` / `normalize_text_workshop`).
- Widget-only (ne menjen mentésbe): `igehely_input`, `tw_main_idea_input`, `tw_main_idea_status_radio`, `ui_mode`, `tw_active_section`.
- Kontextusépítéskor: ha `last_igehely` üres, essen vissza `igehely_input`-ra (és fordítva).

### 2.3 Kortörténet külön szabály

A `history` **csak akkor** kerüljön a kontextusba, ha:

- a felhasználó explicit bekapcsolja („kortörténet is számít”), **vagy**
- más forrás hiányzik és az igehely ószövetségi / történeti narratíva, **vagy**
- a rendszer heurisztikája szerint a fő állítás kultúrtörténeti adat nélkül félreérthető (későbbi finomítás; M1 első körben: *opcionális, alapból ki*).

---

## 3. Kontextusépítési stratégia

### 3.1 Cél

Az új MI-hívás **ne** küldje el az összes hosszú elemzést teljes egészében. Új, **szelektív kontextusépítő** függvény kell (pl. `build_main_idea_context(...)`), amely:

- nem módosítja a forrásszövegeket a sessionben;
- csak olvas és levág / összefűz;
- külön szekciócímkékkel tartja elkülönítve a forrásokat.

### 3.2 Prioritási sorrend (javasolt)

1. **Igehely + felhasználói alap** (`last_igehely` / `igehely_input`; opcionálisan `last_sajat`; alkalom csak röviden; stílus alapból *kihagyva*).
2. **`approved_insights`** — teljes lista, ha ≤ N tétel (javaslat: max 12; felette a legfrissebb / „Fő gondolat” kategória előre).
3. **Exegézis** — első ~2500–3500 karakter **vagy** szerkezeti / összefoglaló szakaszok (ha markdown címek vannak: H2/H3 blokkok preferálása).
4. **Eredeti szöveg** — első ~2000 karakter + kulcsszó-listák, ha felismerhetők; különben eleje.
5. **Teológia** — első ~2000–2500 karakter.
6. **Áttekintés (`overview`)** — első ~1500 karakter (háttér, nem elsődleges).
7. **Kortörténet** — csak szükség esetén, max ~1200 karakter.

**Globális soft limit** a teljes user-kontextusra: kb. **10–14k karakter** (a system + JSON-utasítás mellett). Túllépéskor alulról (7→6→…) vágjunk.

### 3.3 Ismétlés elkerülése

- Ugyanaz a mondat ne szerepeljen két blokkban: insights elsőbbsége az elemző dumpokkal szemben.
- Ha `approved_insights` már összefoglalja az exegézist, az exegézis-blokk rövidebb legyen.
- A kézi `text_main_idea` **javaslat** módban opcionális („jelenlegi vázlat”), **értékelés** módban kötelező fő input.

### 3.4 Hiányzó modulok

| Állapot | Viselkedés |
| --- | --- |
| Nincs igehely | Gomb disabled / figyelmeztetés; nincs API-hívás |
| Van igehely, semmi elemzés | Gyenge javaslat megengedett, de `missing_information` és `warnings` kötelezően jelezze |
| Csak egy modul kész | Annak prioritása szerint; hiányzó modulok listázva |
| Ellentmondás (későbbi heurisztika / modell) | `warnings` + esetleg két eltérő alternatíva |

### 3.5 Elkülönített bemeneti mezők (promptban)

Mindig külön címkézett blokkok, pl.:

```text
## IGEHELY
## FELHASZNÁLÓI SZEMPONT (opcionális)
## JÓVÁHAGYOTT FELISMERÉSEK
## EXEGÉZIS (részlet)
## EREDETI SZÖVEG (részlet)
## TEOLÓGIA (részlet)
## ÁTTEKINTÉS (részlet)
## KORTÖRTÉNET (opcionális részlet)
## JELENLEGI FŐ GONDOLAT VÁZLAT (opcionális / értékelésnél kötelező)
```

### 3.6 Új kontextusépítő

**Igen, szükséges** külön függvény (új fájlban vagy `textus_workshop_*` mellett), pl.:

- `build_main_idea_context(state) -> dict` (strukturált részek + összesített prompt-string)
- Nem nyúl a meglévő `build_original_text_prompt` / section promptokhoz.

---

## 4. Két külön MI-művelet

### 4.A Javaslatok készítése (`suggest`)

**Cél:** segíteni a textus központi állításának megfogalmazását.

**Kimenet elvárása:**

- 1× **ajánlott** fő gondolat (`recommended`);
- legfeljebb **2** valóban eltérő alternatíva (`alternatives`);
- rövid indoklás (`reasoning_summary`) — felhasználónak szánt, nem belső CoT;
- szövegbeli alapok (`textual_basis[]`);
- figyelmeztetések (`warnings[]`);
- hiányzó információ (`missing_information[]`).

**Nem cél:** automatikus mentés a `text_main_idea`-ba; automatikus `approved` státusz.

### 4.B Saját megfogalmazás értékelése (`assess`)

**Bemenet:** a felhasználó aktuális mondata (`text_main_idea` vagy a szerkesztőmező tartalma) + ugyanaz a szelektív kontextus.

**Értékelési szempontok:**

- szöveghűség;
- világosság;
- egység (egy állítás-e);
- teológiai pontosság (a rendelkezésre álló anyaghoz képest);
- terjedelem (egy mondat / nem túl hosszú);
- állítás-e (nem cím, nem kérdés-halmaz);
- nem keveri-e az alkalmazással;
- nem túl általános-e;
- nem tesz-e hozzá olyat, amit a textus / anyag nem állít.

**Kimenet:**

- rövid szöveges értékelés mezőnként (nem százalék);
- erősségek;
- legfeljebb **3** javítási prioritás;
- **egy** átdolgozott változat (`revised_version`) — opcionális átvételre.

**Nem cél:** a mező automatikus felülírása.

---

## 5. Szakmai promptszabályok (majdani új promptok)

A **két új** promptépítő (pl. `build_main_idea_suggest_prompt`, `build_main_idea_assess_prompt`) közös szakmai kerete:

A modell:

1. Csak a bemenetben kapott textus- és műhelyanyagból dolgozzon.
2. Ne találjon ki görög / héber adatot, történeti hátteret, kommentárt.
3. Ne változtassa prédikációs témává vagy címmé a textus állítását.
4. Ne alkalmazza a hallgatókra; ne moralizáljon.
5. Ne erőltesse Krisztust olyan módon, amelyet a textus / kánoni anyag nem támaszt alá.
6. Kerülje a fellengzős, homályos, szlogenszerű nyelvet.
7. Jelezze a bizonytalanságot (`warnings` / `missing_information`).
8. Különböztesse a szövegbeli adatot és a következtetést.
9. Ne kérjen és ne adjon belső „gondolatmenetet” / chain-of-thought dumpot — csak rövid `reasoning_summary`.
10. Magyarul válaszoljon, JSON-séma szerint.

**Befagyasztott modulok — tilos módosítani:**

- Eredeti szöveg, Exegézis, Kortörténet, Teológia, Illusztrációk, Aktualizálás  
  (és ezek meglévő promptépítő / system bundle szövegei).

---

## 6. Javasolt strukturált kimenet

### 6.1 Javaslat — JSON-séma

```json
{
  "recommended": "string",
  "alternatives": ["string", "string"],
  "reasoning_summary": "string",
  "textual_basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
```

| Mező | Kötelező | Megjegyzés |
| --- | --- | --- |
| `recommended` | Igen | Egy mondat; üres string csak hiba esetén |
| `alternatives` | Igen (lista) | 0–2 elem; üres lista OK |
| `reasoning_summary` | Igen | Rövid, 2–5 mondat max |
| `textual_basis` | Igen (lista) | Üres lista OK, ha hiányos az anyag |
| `warnings` | Igen (lista) | Üres lista = nincs figyelmeztetés |
| `missing_information` | Igen (lista) | Üres lista OK |

### 6.2 Értékelés — JSON-séma

```json
{
  "assessment": {
    "text_fidelity": "string",
    "clarity": "string",
    "unity": "string",
    "theological_accuracy": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_version": "string"
}
```

| Mező | Kötelező | Megjegyzés |
| --- | --- | --- |
| `assessment.*` | Igen | Rövid szöveg; **nem** 1–10 pont / % |
| `strengths` | Igen (lista) | Üres ritka, de megengedett |
| `revision_priorities` | Igen (lista) | Max 3 a promptban előírva |
| `revised_version` | Igen | Egy mondat; ha a saját jó, lehet közel azonos |

### 6.3 Parser és fallback

- Új parser pl. `parse_main_idea_json(raw: str) -> dict | None`.
- Lépések: nyers szöveg → markdown fence levágás → `json.loads` → sémaellenőrzés (kötelező kulcsok, típusok, `alternatives` ≤ 2, `revision_priorities` ≤ 3).
- Hibás JSON / hiányzó mező: felhasználói hibaüzenet + opcionális „nyers válasz” expander; **ne** írjon a `text_main_idea`-ba.
- API-hiba: a meglévő `generate_text` figyelmeztető stringjei jelenjenek meg; ne parsáljuk JSON-ként.

### 6.4 Hol tárolódjon?

| Adat | Session | Tartós `project_data` (`text_workshop` bővítés)? |
| --- | --- | --- |
| `text_main_idea` / `status` / `approved_insights` | Igen | **Igen** (már megvan) |
| Utolsó javaslat payload (`main_idea_suggestions`) | Igen | **Igen (ajánlott)** — visszatöltéskor látható |
| Utolsó értékelés (`main_idea_assessment`) | Igen | **Igen (ajánlott)** |
| `main_idea_last_generated_at` | Igen | Igen (ISO string) |
| Futó flag (`_main_idea_suggest_running`) | Igen | **Nem** |
| Widget kulcsok | Igen | **Nem** |

A `normalize_text_workshop` bővíthető visszafelé kompatibilisen: hiányzó új mezők → üres default; régi projektek ne törjenek el.

---

## 7. Egyszerű felületi terv

A meglévő `render_text_main_idea_section()` továbbfejlesztése — **kézi használat megmarad**.

### 7.1 Javasolt elrendezés (egyszerű)

1. Cím + jelenlegi útmutató szöveg (megmarad).
2. Szerkeszthető `text_area` (jelenlegi).
3. Állapot: Vázlat / Jóváhagyva + „Fő gondolat mentése” (jelenlegi).
4. **Új gombok** (egymás mellett / egymás alatt, nem zsúfoltan):
   - „Javaslatok készítése”
   - „Saját megfogalmazás értékelése” (disabled, ha a mező üres)
5. **Javaslatok zóna** (csak ha van eredmény): kártyák
   - Ajánlott
   - Alternatíva 1–2
   - Indoklás, alapok, figyelmeztetések (összecsukható)
   - Minden javaslatnál: **„Átveszem”** → bemásolja a szerkesztőmezőbe (státusz maradjon `draft`, amíg a user nem ment / nem hagyja jóvá)
6. **Értékelés zóna** (csak ha van eredmény): szempontok + prioritások + átdolgozott változat + „Átveszem az átdolgozottat”
7. „Korábbi műhelyanyagok áttekintése” expander — **megmarad**

### 7.2 Kerülendő

- Automatikus mentés / automatikus jóváhagyás
- Százalékok, csillagok, túl sok metrika
- Új felső fül / kötelező wizard
- Illusztráció–aktualizálás behúzása ebbe a szakaszba

### 7.3 Emberi döntés

A végső `text_main_idea_status = approved` és az `approved_insights`-ba továbbadás **csak** emberi gombnyomásra történik (jelenlegi M1 logika).

---

## 8. Adatmodell és állapotkezelés

### 8.1 Meglévő mezők — változatlanok

- `text_workshop.text_main_idea`
- `text_workshop.text_main_idea_status` (`draft` \| `approved` \| `""`)
- `text_workshop.approved_insights[]`

### 8.2 Javasolt bővítés (ugyanabban az objektumban)

```text
text_workshop = {
  text_main_idea,
  text_main_idea_status,
  approved_insights,
  main_idea_suggestions,      # utolsó sikeres suggest JSON (dict)
  main_idea_assessment,       # utolsó sikeres assess JSON (dict)
  main_idea_last_generated_at # ISO string vagy ""
}
```

### 8.3 Technikai / átmeneti kulcsok (nem project_data)

- `_main_idea_suggest_running`, `_main_idea_assess_running`
- `_tw_ui_resync` (már létezik a kézi UI-hoz)
- widget: `tw_main_idea_input`, `tw_main_idea_status_radio`

### 8.4 Widget sorrend

- „Átveszem”: **ne** írjon közvetlenül a widget key-re a widget létrehozása után ugyanabban a futásban konfliktust okozva — használjon `_tw_ui_resync` + érték a `text_main_idea`-ba mentve **vagy** pending flag + `st.rerun()` mintát (ahogy a projekt betöltésnél).
- Mentés továbbra is `update_text_main_idea(...)`.

### 8.5 Projektbetöltés

- `normalize_text_workshop` fogadja el a hiányzó suggest/assess mezőket.
- Betöltés után `_tw_ui_resync = True` (már megvan) — a kézi mező visszatöltődik; a javaslat/értékelés kártyák a tartós mezőkből jelennek meg, ha vannak.

### 8.6 Visszafelé kompatibilitás

- Régi projekt `text_workshop` nélkül → default.
- Régi `text_big_idea` → már migrálva `text_main_idea`-ra.
- Új mezők hiánya → `{}` / `[]` / `""`.

---

## 9. Modell- és hívási stratégia

### 9.1 Újrafelhasználás

- **Egyetlen** kliens: meglévő `generate_text(...)` az `app.py`-ban.
- Nincs párhuzamos API-kliens / külön SDK-ág.
- `tab_label` javaslat: pl. `"Textus fő gondolat — javaslat"` és `"Textus fő gondolat — értékelés"` (új címkék a `GEMINI_MODEL_BY_TAB_LABEL` mapben → alapból `LOCKED_MODEL` / Flash, ha nincs külön bejegyzés).

### 9.2 Új függvények (terv)

| Függvény | Szerep |
| --- | --- |
| `build_main_idea_context(state)` | Szelektív kontextus |
| `build_main_idea_suggest_prompt(ctx)` | **Új** prompt — nem nyúl a régiekhez |
| `build_main_idea_assess_prompt(ctx, user_sentence)` | **Új** prompt |
| `parse_main_idea_suggestions(raw)` | JSON + validáció |
| `parse_main_idea_assessment(raw)` | JSON + validáció |
| `run_main_idea_suggestions()` / `run_main_idea_assessment()` | Orchestráció: kontextus → prompt → `generate_text` → parse → session |

### 9.3 Két művelet elkülönítése

- Külön gomb, külön running flag, külön eredménymező.
- Cache: `use_cache=False` ajánlott (kontextus gyakran változik), vagy cache kulcs tartalmazza a fingerprintet.

### 9.4 Kreativitás

- Exegetikai feladat: **alacsonyabb temperature**, pl. **0.1–0.2** a hívás idejére (ha a `generate_text` engedi paraméterként; ha nem, dokumentálni kell a meglévő session `temperature` ideiglenes override + visszaállítás mintáját — implementációkor a legkisebb invazív megoldás).
- Alap session `temperature` (0.3) megmaradhat más moduloknál.

### 9.5 Hibakezelés

| Eset | UI |
| --- | --- |
| Nincs API kulcs | Meglévő figyelmeztetés |
| 429 / hálózat | `generate_text` üzenet |
| Nem JSON | „A válasz nem dolgozható fel” + ne mentsen |
| Üres `recommended` | Figyelmeztetés, ne ajánljon „Átveszem”-et |

---

## 10. Tesztelési terv

| # | Eset | Elvárt |
| --- | --- | --- |
| 1 | Minden elemzőmodul kész | Javaslat + textual_basis; kevés missing |
| 2 | Csak exegézis | Javaslat exegézisre támaszkodva; missing jelzi a többit |
| 3 | Csak eredeti szöveg | Óvatos javaslat; warnings |
| 4 | Semmilyen elemzés (van igehely) | Erős missing/warnings; gyenge vagy elutasított minőségjelzés |
| 5 | Nincs igehely | Nincs hívás |
| 6 | Ellentmondó anyagok | warnings; eltérő alternatives |
| 7 | Jó saját mondat | Erősségek; kevés prioritás; revised ≈ eredeti |
| 8 | Túl általános mondat | revision_priorities a konkrétságra |
| 9 | Alkalmazás fő gondolat helyett | Egyértelmű jelzés + revised állítássá alakítva |
| 10 | Hibás JSON | Fallback üzenet; mező érintetlen |
| 11 | API-hiba | Nincs részleges felülírás |
| 12 | Mentés / betöltés | suggestions + assessment visszajön (ha tartós) |
| 13 | quick ↔ workshop | `text_main_idea` és eredmények megmaradnak; nincs DuplicateElementKey |
| 14 | Diff regresszió | Befagyasztott promptfájlok / promptépítők byte-szinten érintetlenek |

Manuális smoke: generálás nélkül UI gombok állapota; unit: parser + kontextus hosszlimit.

---

## 11. Implementációs javaslat (3–4 lépés)

### Lépés 1 — Promptépítő + parser (UI nélkül)

- `build_main_idea_context`, suggest/assess promptok, JSON parserek.
- Egységtesztek (fixture szövegekkel, API nélkül).
- App továbbra is működik; gombok még nincsenek.

### Lépés 2 — Javaslatkészítés a felületen

- Gomb + running flag + kártyák + „Átveszem”.
- `generate_text` bekötés.
- Kézi mentés / jóváhagyás változatlan.

### Lépés 3 — Saját megfogalmazás értékelése

- Második gomb + assessment UI + „Átveszem az átdolgozottat”.
- Üres mező → disabled.

### Lépés 4 — Projektmentés, regresszió, UX

- `normalize_text_workshop` bővítés; fingerprint.
- quick/workshop; DuplicateElementKey ellenőrzés.
- Prompt-diff ellenőrzés (befagyasztott modulok).
- Finomítás: üres állapotok, hibaüzenetek.

Minden lépés után az alkalmazás **futóképes** marad.

---

## Összefoglaló döntések

| Kérdés | Döntés |
| --- | --- |
| Meglévő promptok | **Tilos módosítani** |
| API | Csak meglévő `generate_text` |
| Automatikus jóváhagyás | **Nincs** |
| Illusztráció / aktualizálás a kontextusban | **Nem** |
| Kortörténet | Opcionális, alapból ki |
| Tartós MI-eredmények | `main_idea_suggestions` / `main_idea_assessment` a `text_workshop`-ban |
| Első kódolási lépés | Kontextus + új promptépítők + parser, UI nélkül |

---

*Dokumentum vége — `TEXTUS_MAIN_IDEA_SPEC.md`*
