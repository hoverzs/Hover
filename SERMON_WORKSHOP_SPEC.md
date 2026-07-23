# TEXTUS 2.0 — Igehirdetési műhely: szakmai, UX- és műszaki specifikáció

**Dokumentum típusa:** tervezési specifikáció (implementáció még nem kezdődött)  
**Fájl:** `SERMON_WORKSHOP_SPEC.md`  
**Dátum:** 2026-07-21  
**Állapot:** tervezés — *ne implementáld ebből automatikusan*  
**Kapcsolódó meglévő anyagok (csak olvasva):** `TEXTUS_2_ARCHITECTURE.md`, `TEXTUS_MAIN_IDEA_SPEC.md`, `textus_workshop_data.py`, `workspace_data.py`, `textus_workshop_ui.py`, `app.py`

---

## 0. Cél és hatókör

Az **Igehirdetési műhely** a Textusműhely **jóváhagyott** eredményeiből induló, egyszerű, áttekinthető, szakmailag komoly igehirdetés-előkészítő felület.

| Műhely | Kérdés |
| --- | --- |
| **Textusműhely** | Mit mond a bibliai szöveg? |
| **Igehirdetési műhely** | Hogyan válik ebből textushű, Krisztus-központú, hallható és a mai gyülekezetet megszólító igehirdetés? |

**Nem cél ebben a dokumentumban:** Python-kód, promptírás, adatbázis-séma, Gemini-hívás, commit.

**Befagyasztott / érinthetetlen:**
- a Textusműhely meglévő eredményei és promptjai;
- eredeti szöveg / exegézis / kortörténet / teológia / illusztráció / aktualizálás promptok és promptépítők;
- a Gyorseszközök 13 füles működése vendégként / projekt nélkül is.

---

## 1. Alapelvek

1. Az Igehirdetési műhely **nem írhatja vissza** a prédikáció kívánt üzenetét az exegézisbe vagy a textus fő gondolatába.
2. A Textusműhely meglévő eredményeit és promptjait **nem módosíthatja**.
3. A végső szakmai döntést **mindig a prédikátor** hozza meg (jóváhagyás, átvétel, elvetés).
4. Projekt nélkül és vendégként a **Gyorseszközök** továbbra is használhatók.
5. **Nincs kötelező lineáris varázsló** — bármelyik szakasz külön megnyitható.
6. Egy képernyőn **kevés elsődleges művelet**; részletes indoklások **összecsukhatók**.
7. **Nincsenek** külön Robinson- / Chapell- / Craddock- / Lowry- / Buttrick-fülek. A szakirodalmi elvek **természetes munkakérdések** mögött működnek.
8. Az MI **segít**, nem írja meg helyette az egész prédikációt egy lépésben.
9. Preferált bemenet: **jóváhagyott** Textusműhely-anyag (`approved` fő gondolat, `approved_insights`); a hosszú dumpok csak szükség esetén, szelektíven.
10. Mobilbarát: egyszerre **egy aktív szakasz** renderelődik (mint a Textusműhelyben).

---

## 2. Bemenet a Textusműhelyből

### 2.1 Forrástábla (jelenlegi kulcsok)

| Logikai adat | Jelenlegi kulcs / út | Tartós `project_data`? | Homiletikai fontosság | Átadás módja | Zaj / torzítás | Ha hiányzik |
| --- | --- | --- | --- | --- | --- | --- |
| Igehely | `last_igehely` (tartós); widget: `igehely_input` | Igen (`last_igehely`) | **Kritikus** | Rövid azonosító string | Alacsony | Figyelmeztetés; MI-műveletek disabled / gyenge kontextus |
| Alkalom | `last_alkalom` / `alkalom_input` | Igen | Magas (műfaj, hangnem) | Rövid string | Közepes, ha „prédikációs” irányba húz | „nincs adat”; ne találjon ki liturgiai keretet |
| Homiletikai stílus | `last_stilus` / `stilus_input` | Igen | Közepes–magas (forma) | Rövid string | Magas, ha felülírja a textust | Opcionális; útjavaslatnál háttér |
| Saját szempont | `last_sajat` / `sajat_input` | Igen | Közepes | Rövid–közepes szöveg | Közepes (prédikátor-hang) | Opcionális |
| Textus fő gondolata | `text_workshop["text_main_idea"]` | Igen (nested) | **Nagyon magas** | Egy mondat | Alacsony | Erős figyelmeztetés; javaslat: térjen vissza a Textusműhelybe |
| Fő gondolat státusz | `text_workshop["text_main_idea_status"]` (`draft` \| `approved` \| `""`) | Igen | Magas (szűrés) | Enum-szerű string | — | `draft` / üres → „még nem jóváhagyott” jelzés |
| Jóváhagyott felismerések | `text_workshop["approved_insights"][]` (`id`, `source`, `category`, `content`, `approved`, `created_at`) | Igen | **Nagyon magas** | Teljes lista (rövid tételek) | Alacsony | Gyenge bázis; MI jelezze a hiányt |
| Exegézis | `exegesis` | Igen | Magas (szükség esetén) | **Szelektív kivonat** (~2–3k kar.) | Magas hossz | Csak ha insights kevés; ne kötelező |
| Teológia | `theology` | Igen | Magas (Krisztus-ív, hangsúly) | Szelektív kivonat | Magas hossz | Opcionális |
| Eredeti szöveg | `original_text` | Igen | Közepes–magas (kép, kulcsszó) | Szelektív kivonat | Magas (nyelvi dump) | Opcionális |
| Áttekintés | `overview` | Igen | Alacsony–közepes | Rövid kivonat | Közepes | Opcionális háttér |
| Kortörténet | `history` | Igen | Alacsony–közepes | Csak ha releváns, max ~1–1,2k | Magas zaj | Alapból ki |
| Illusztrációk (Gyorseszköz) | `illustrations` | Igen | Közepes (átvételhez) | **Nem** automatikus kontextus; felhasználói válogatás | Magas (alkalmazás felé húz) | Üres lista |
| Aktualizálás | `actualization` | Igen | Közepes (átvételhez) | Ugyanígy: emberi válogatás | Magas | Üres |
| Vázlat / kosár | `outline*`, `basket` | Igen | Alacsony a műhelyben | Ne legyen elsődleges MI-bemenet | Magas duplikáció | Kihagyandó a kontextusépítőből |
| Textus MI-javaslat cache | `text_workshop["main_idea_suggestions"]` / `main_idea_assessment` | Igen | Alacsony | **Ne** legyen tekintélyi forrás | Lehorgonyzás | Figyelmen kívül |

**Widget vs. tartós:** a `*_input` kulcsok UI-only (`EXCLUDED_SESSION_KEYS`); kontextusépítéskor: `last_*` elsőbbség, fallback widgetre (mint a Textusműhelyben).

### 2.2 Prioritás a kontextusépítéshez

1. `last_igehely` + `text_workshop.text_main_idea` (ha `approved`, jelölve; ha csak `draft`, figyelmeztetve)  
2. `approved_insights` (teljes, ha ≤ ~12 tétel)  
3. `last_alkalom`, `last_stilus`, `last_sajat` (röviden)  
4. Szelektív `exegesis` / `theology` / `original_text` — csak ha insights kevés, vagy a szakasz explicit kéri  
5. `overview` — háttér  
6. `history` — kapcsoló / heurisztika  
7. **Soha automatikusan:** `illustrations`, `actualization`, `outline*`, `songs`, sorozattervező

### 2.3 „Jóváhagyott anyag” kapu (soft)

Nem kötelező soft-lock, de ajánlott UI-jelzés:

- Ha `text_main_idea_status != "approved"` vagy üres a fő gondolat / insights:  
  „A Textusműhely még nem hagyott jóvá stabil alapot. Dolgozhatsz tovább, de az MI óvatosabb lesz.”
- Nincs automatikus átírás a Textusműhely mezőibe.

---

## 3. Az Igehirdetési műhely szakaszai (áttekintés)

Kilenc szakasz — **nem** kötelező sorrend; egyszerre egy aktív.

| # | Szakasz | Rövid cél |
| --- | --- | --- |
| 1 | Az igehirdetés fő gondolata | Hallható, textushű `sermon_main_idea` |
| 2 | Emberi helyzet és kegyelmi válasz | Törés + Isten cselekvése, sablon nélkül |
| 3 | Hallgatói kérdés és feszültség | Valódi kérdés / feszültség a textusból |
| 4 | Krisztus-központú és evangéliumi ív | Kapcsolat típusa + kegyelem az igény előtt |
| 5 | A prédikáció útja | Forma (deduktív / induktív / …) természetes nyelven |
| 6 | Prédikációs mozgások | 3–5 felismerési mozgás |
| 7 | Képek, illusztrációk és alkalmazás | Válogatott képek + konkrét alkalmazás |
| 8 | Lezárás | Érkezés, remény, nem manipulatív zárás |
| 9 | Homiletikai diagnosztika | Szöveges tükrözés, max 3 prioritás |

Minden szakasz közös UX-váz (lásd §8): rövid cél → egy elsődleges döntés → max két művelet → MI-javaslat → összecsukott indoklás → következő ajánlott lépés.

---

## 4. Modern homiletikai eszközök — természetes beépítés

Nincs szerző-fül. A kérdések mögött futnak az elvek.

### A. Robinson — fő gondolat
- `text_main_idea` ≠ `sermon_main_idea`.
- Az igehirdetés fő gondolata: **egy állítás**, amely összetartja az utat; nem cím, nem szlogen.
- UI-kérdés: „Egy mondatban: mit szeretnél, hogy a hallgató hazavigyen — a textus állításából?”

### B. Chapell — emberi helyzet
- Kérdés: „Mi a közös emberi törés / szükség / téves bizalom ebben a textusban és a hallgatóban?”
- **Ne** kényszerítsen bűnprobléma-sablont minden textusra (hálaadó zsoltár, bölcsesség, narratíva).
- Külön mezők: helyzet vs. kegyelmi válasz.

### C. Craddock — induktív út
- Kérdés: „Mit mikor ismerjen fel a hallgató?”
- Induktív forma **csak ha** a textus és a cél indokolja — nem default.

### D. Lowry — narratív feszültség
- Kérdés: „Mi a nyitott zavar / ellentmondás, amit a textus mozgat?”
- Nincs mesterséges dráma; a feloldás a textusból jöjjön.

### E. Buttrick — mozgások
- Nem „1. pont / 2. pont”, hanem: honnan → mit látunk meg → hogyan kapcsolódik → merre tovább.
- UI: mozgáskártyák egyszerű címkékkel („Indulás”, „Felismerés”, „Tovább”).

### F. Krisztus-központúság
- Típusválasztó (közvetlen / üdvtörténeti / tipológiai / kánoni / teológiai / nincs közvetlen / további vizsgálat).
- Bizonytalanság külön mezőben; tilos allegória és utólagos evangéliumi toldalék.

### G. Hallgatóközpontúság
- Kérdések, ellenállás, félelem, félreértés, remény — **anélkül**, hogy a textust felülírná.
- Aktualizálás ≠ közhelyes példa.

---

## 5. Szakaszok részletes tartalma

### 5.1 Az igehirdetés fő gondolata

**Cél:** a textus állításából hallható, de textushű `sermon_main_idea`.

**Fogalmi elhatárolás**

| Fogalom | Mi ez? | Hol él? |
| --- | --- | --- |
| `text_main_idea` | A szakasz központi *állítása* | `text_workshop` |
| `sermon_main_idea` | A prédikáció egységes *üzenetmondata* a hallgatóknak | `sermon_workshop` |
| Prédikációs cím | Rövid elnevezés | Későbbi / opcionális; **nem** ez a szakasz fő terméke |
| Célmondat | „Mit akarok elérni?” (homiletikai szándék) | Opcionális mező vagy a `sermon_path` része |
| Alkalmazás | „Mit tegyünk / milyen válasz?” | Külön szakasz (7–8) |

**Prédikátori kérdés:** „Ha egyetlen mondatot vihetnének haza, mi lenne az — úgy, hogy a textus is ezt állítja?”

**Bemenet:** `text_main_idea` (+ státusz), `approved_insights`, igehely, alkalom, stílus, saját szempont; szükség esetén rövid exegézis-kivonat.

**Kézi:** egy szövegmező + `draft` / `approved` (ugyanaz a kétgombos minta, mint a Textusműhelynél: „Mentés vázlatként” / „Jóváhagyom”).

**MI:** javaslat + értékelés (két művelet), JSON-séma; nem írja felül automatikusan.

**Továbbadás:** jóváhagyott `sermon_main_idea` → minden későbbi szakasz elsődleges horgonya.

**UI (alapból látható):** mező, két mentő gomb, „Javaslat” / „Értékelés”, elmentett állapot.  
**Összecsukva:** indoklás, figyelmeztetések, textus↔prédikáció különbség magyarázata.

**Önállóan:** igen — ha van legalább igehely + (fő gondolat vagy insights).

---

### 5.2 Emberi helyzet és kegyelmi válasz

**Cél:** a textus és a hallgató közös emberi valósága + Isten válasza, sablon nélkül.

**Javasolt mezők (kritikai szűréssel)**

| Mező | Szükséges? | Megjegyzés |
| --- | --- | --- |
| `human_condition` | **Igen** | Rövid: törés / helyzet / korlát |
| `human_need` | **Igen** | Mit keres / mire van szüksége |
| `divine_action` | **Igen** | Mit tesz Isten a textusban |
| `grace_response` | **Igen** | Kegyelem / evangéliumi válasz (indicative) |
| `false_belief_or_response` | Opcionális | Csak ha a textus tényleg téves bizalmat mutat |
| `desired_transformation` | Opcionális / később | Könnyen moralizálássá válik — **ne legyen kötelező** az M4-ben |

**Összevonás:** az első implementációban elég egy nested objektum 4 kötelező + 1–2 opcionális mezővel; ne legyen 6 kötelező szövegdoboz egyszerre.

**Prédikátori kérdés:** „Mi a közös emberi helyzet, és mit válaszol erre Isten *ebben* a textusban?”

**MI:** javaslat a négy fő mezőre; figyelmeztetés, ha bűn-sablont erőltetne.

**UI:** egy elsődleges szöveg (`human_condition`); a többi expanderben vagy „További mezők” alatt.  
**Összecsukva:** MI-indoklás, sablon-figyelmeztetés.

---

### 5.3 Hallgatói kérdés és feszültség

**Mezők**

| Mező | Szerep |
| --- | --- |
| `listener_question` | A hallgató valódi kérdése |
| `listener_resistance` | Ellenállás / félelem / félreértés |
| `sermon_tension` | A prédikációt mozgató feszültség |
| `tension_source` | Honnan jön: textus / helyzet / kettő feszültsége |
| `promised_resolution` | Mit ígérhet a prédikáció — **nem többet**, mint a textus |

**Prédikátori kérdés:** „Mi tartja fenn a figyelmet — és mit *nem* ígérünk túl?”

**UI:** egy látható kérdésmező; a többi összecsukva.  
**Önállóan:** igen, de figyelmeztetés, ha nincs `sermon_main_idea`.

---

### 5.4 Krisztus-központú és evangéliumi ív

**Mezők**

| Mező | Szerep |
| --- | --- |
| `christ_connection_type` | Enum-szerű típus (lásd lent) |
| `christ_connection` | Rövid szöveges kapcsolat |
| `gospel_indicative` | Evangéliumi kijelentés (mit tett / ad Isten) |
| `grace_before_demand` | Bool vagy rövid szöveg: kegyelem az igény előtt |
| `uncertainty_note` | Ha közvetett / bizonytalan |

**Kapcsolattípusok (UI-címkék természetes nyelven):**
- közvetlen;
- üdvtörténeti;
- tipológiai;
- kánoni;
- teológiai;
- nincs közvetlen kapcsolat;
- további vizsgálat szükséges.

**Prédikátori kérdés:** „Hogyan kapcsolódik Krisztus / az evangélium *ehhez* a textushoz — erőltetés nélkül?”

**MI:** típusjavaslat + szöveg; kötelező `uncertainty_note`, ha nem közvetlen.

---

### 5.5 A prédikáció útja

**Lehetőségek (belső kód → felhasználói magyarázat):**

| Kód | Felhasználói címke (példa) |
| --- | --- |
| `deductive` | „Elöl kimondom az állítást, aztán kifejtem” |
| `inductive` | „Együtt fedezzük fel, és a végén kristályosodik” |
| `narrative` | „Történetként / feszültséggel haladunk” |
| `problem_gospel` | „Emberi helyzet → evangéliumi válasz” |
| `text_following` | „A szöveg saját menetét követjük” |
| `thematic_faithful` | „Témák szerint, de a textushoz kötve” |
| `meditative` | „Lassú, elmélyülő, kevés pont” |
| `apologetic` | „Kérdésekre válaszoló, érvelő” |

**Tárolás:** `sermon_path = { "type": "...", "rationale": "...", "status": "draft|approved" }`

**UI:** radio / select természetes címkékkel + egy rövid „miért ez?” mező. Nincs szakzsargon a felületen.

---

### 5.6 Prédikációs mozgások

**Egy mozgás mezői**

| Mező | Kell az M6-ban? |
| --- | --- |
| `id` | Igen |
| `position` | Igen (1…n) |
| `title` | Igen (rövid) |
| `starting_point` | Igen |
| `listener_discovery` | Igen |
| `textual_basis` | Igen (rövid; insights / textus) |
| `theological_claim` | Igen |
| `transition` | Igen |
| `destination` | Igen |
| `image_or_example` | Opcionális |
| `application` | Opcionális (részletek a 7. szakaszban) |

**Egyszerűség 3–5 mozgásnál:**
- lista kártyákként;
- egyszerre **egy** mozgás szerkesztője nyitva;
- „+ Mozgás” / törlés / fel-le;
- MI: „Javaslat a teljes ívre” *vagy* „Javaslat ehhez a mozgáshoz” — ne mindkettő egyszerre elsődleges.

**Továbbadás:** a mozgások listája táplálja a képeket, alkalmazást, lezárást, diagnosztikát.

---

### 5.7 Képek, illusztrációk és alkalmazás

**Típusok (válogatás, nem mind kötelező mező):**
- textusból eredő kép;
- szemléltető illusztráció;
- történet;
- analógia;
- konkrét / közösségi / egyéni alkalmazás;
- liturgiai vagy lelki gyakorlat.

**Tárolás (egyszerűsített):**
- `selected_images[]`: `{ id, kind, content, source, approved }`
- `applications[]`: `{ id, audience, content, approved }`  
  (`audience`: individual | community | liturgical)

**Átvétel a meglévő modulokból (promptok változatlanok):**
1. Olvasás: `illustrations`, `actualization` session/project mezőkből.
2. UI: „Elem átvétele a Gyorseszközök / meglévő anyagból” expander — checkbox lista.
3. Átvétel → bemásolás a `selected_images` / `applications` draftjába; **nem** módosítja az eredeti `illustrations` / `actualization` szöveget.
4. Új MI-generálás ebben a szakaszban: *opcionális, későbbi mérföldkő*; első körben az átvétel + kézi szerkesztés elég.

---

### 5.8 Lezárás

**Nem** puszta összefoglaló. Vizsgálandó:
- hová érkezett a hallgató;
- végső felismerés;
- reménység a textusból;
- kell-e felszólítás (és milyen);
- mi maradjon nyitott;
- hogyan kerülhető el az érzelmi manipuláció.

**Tárolás:** `closing = { arrival, final_insight, hope, exhortation, open_ends, anti_manipulation_note, status }`  
Első UI: 2–3 mező látható (`final_insight`, `hope`); a többi expander.

---

### 5.9 Homiletikai diagnosztika

**Forma:** rövid **szöveges** minősítések (mint a textus fő gondolat értékelőjénél: `Megfelelő —` / `Részben megfelelő —` / `Javítandó —` / `Nem megítélhető —`), **pontszám nélkül**.

**Szempontok (legalább):**
textushűség; egység; teológiai pontosság; Krisztus-központúság; kegyelem/felszólítás aránya; hallgatói relevancia; valódi feszültség; szerkezeti mozgás; alkalmazás konkrétsága; illusztrációk funkciója; túlterheltség; lezárás ereje; a prédikátor saját hangja.

**Kimenet:**
- `diagnostics.assessment` (mezőnként szöveg);
- `diagnostics.strengths[]` (max 3);
- `diagnostics.revision_priorities[]` (**max 3**);
- `diagnostics.summary` (rövid);
- **nem** írja felül automatikusan a prédikációt.

---

## 6. Munkamódok (fokozatos)

| Mód | Jelleg | Első megjelenés |
| --- | --- | --- |
| **Gyors segítség** | Rövid MI-javaslat, kevés kérdés, gyors átvétel | M4–M5 egyes szakaszain |
| **Műhely** | Kézi bevitel + MI + jóváhagyás / továbbvitel | **Alapértelmezett** az első implementációban |
| **Mentor** | Először kérdez; értékeli a döntést; nem ad azonnal kész választ | M8 vagy később |

**Bevezetési sorrend:** Műhely → Gyors segítség gombok szakaszonként → Mentor (opcionális kapcsoló, csak diagnosztika + fő gondolat szakaszon kísérleti jelleggel).

Az első éles verzióban **nem** kell mindhárom teljes értékű.

---

## 7. Adatmodell: `sermon_workshop`

### 7.1 Javasolt tartós szerkezet (kritikai egyszerűsítéssel)

```text
sermon_workshop = {
  "sermon_main_idea": "",
  "sermon_main_idea_status": "",          # "" | "draft" | "approved"

  "human_condition_block": {              # §5.2 — összevont
    "human_condition": "",
    "human_need": "",
    "divine_action": "",
    "grace_response": "",
    "false_belief_or_response": "",       # opcionális
    "status": ""
  },

  "listener_tension": {
    "listener_question": "",
    "listener_resistance": "",
    "sermon_tension": "",
    "tension_source": "",
    "promised_resolution": "",
    "status": ""
  },

  "christ_centered_arc": {
    "christ_connection_type": "",
    "christ_connection": "",
    "gospel_indicative": "",
    "grace_before_demand": "",
    "uncertainty_note": "",
    "status": ""
  },

  "sermon_path": {
    "type": "",
    "rationale": "",
    "status": ""
  },

  "sermon_movements": [],                 # mozgás objektumok listája

  "selected_images": [],
  "applications": [],

  "closing": {
    "final_insight": "",
    "hope": "",
    "exhortation": "",
    "open_ends": "",
    "arrival": "",
    "anti_manipulation_note": "",
    "status": ""
  },

  "diagnostics": null,                    # utolsó sikeres diagnosztika dict vagy null
  "approved_sermon_decisions": [],        # általános jóváhagyott döntések

  # opcionális cache (mint text_workshop MI-cache)
  "last_ai_payloads": {},                 # szakasz-kulcs → utolsó javaslat (nem tekintélyi)
  "last_generated_at": ""
}
```

**Miért nem a nyers „minden külön top-level” séma?**  
A `human_condition: {}` stb. önmagában jó irány; az összevont `human_condition_block` csökkenti a szétszórt kulcsok számát. A `desired_transformation` **kimarad** az első sémából (túl könnyen moralizál).

### 7.2 `approved_sermon_decisions[]` általános forma

```text
{
  "id": "uuid",
  "source_section": "sermon_main_idea" | "human_condition" | ... ,
  "category": "rövid címke",
  "content": "szöveg",
  "approved": true,
  "created_at": "ISO-8601"
}
```

Szerepe: a Textusműhely `approved_insights` párja — homiletikai döntések továbbvitele (pl. későbbi vázlat / export).

### 7.3 Tartós vs. átmeneti vs. kizárt

| Kategória | Példák |
| --- | --- |
| **Tartós** (`project_data` nested) | fenti `sermon_workshop` mezők |
| **Átmeneti MI** | futó flagek, nyers válasz, pending átvétel |
| **Kizárt UI** | `sw_active_section`, `sw_*_input`, `_sw_*_pending`, `ui_mode` |

### 7.4 Beillesztés a meglévő JSON-ba (séma nélkül)

- Új nested kulcs: `sermon_workshop` (mint `text_workshop`).
- `PROJECT_NESTED_KEYS` bővítése + `normalize_sermon_workshop()` (hiányzó mezők → default).
- Régi projektek: hiányzó kulcs → üres default; **nincs** Supabase DDL.
- Fingerprint / dirty jelzés: a nested objektum része a `project_content_fingerprint`-nek.

### 7.5 Visszafelé kompatibilitás

- Régi `project_data` `sermon_workshop` nélkül → `get_default_sermon_workshop()`.
- Ismeretlen extra kulcsok: normalize megtarthatja *vagy* eldobhatja — ajánlás: **ismert kulcsok + biztonságos ignore**.

---

## 8. Navigáció és UX

### 8.1 Hol legyen az Igehirdetési műhely?

**Javaslat: A + B hibrid (háromelemű fő nézet + Textusműhely-kapu)**

| Elem | Megvalósítás |
| --- | --- |
| **A. Fő nézetválasztó** | `ui_mode`: `quick` \| `workshop` \| `sermon` (feliratok: Gyorseszközök / Textusműhely / Igehirdetési műhely) |
| **B. Kapu** | A Textusműhely „Mit viszünk tovább?” végén caption + nem kötelező szöveg: „Amikor kész vagy, válaszd az Igehirdetési műhelyt.” (nem automatikus navigáció az első körben; később egyetlen „Megnyitás” gomb `ui_mode=sermon`-ra állíthat) |

**Indoklás**

| Szempont | Értékelés |
| --- | --- |
| Mobil | Három radio/segment átlátható; szakaszonként egy panel |
| Egyszerűség | Ugyanaz a minta, mint a mostani quick/workshop |
| Widget-key | `sw_*` előtag; nem ütközik `tw_*` / quick tab kulcsokkal |
| Egyértelműség | Három világos munkatér |
| Visszaállíthatóság | `ui_mode` nem tartós; projekt nested adat igen |
| Szabad modulhasználat | Gyorseszközök megmaradnak; szakaszok nem lineárisak |

**Elvetett tiszta C (pl. csak Textusműhelyen belüli almenü):** összekeveri a „mit mond a szöveg” és a „hogyan prédikálok” munkát egy radio-listában, és megnehezíti a vendég/Gyorseszköz elkülönítést.

### 8.2 Belső navigáció

- `sw_active_section` — session-only.
- Egyszerre egy szakasz render.
- Szakaszvég: egy `st.caption("Következő ajánlott lépés: …")` — nincs kényszerített ugrás.

### 8.3 Szakaszon belüli sorrend (kötelező UX-minta)

1. Rövid cél (1–2 mondat)  
2. Egy elsődleges döntés / mező  
3. Legfeljebb két látható művelet  
4. MI-javaslatok (ha van)  
5. Részletes indoklás összecsukva  
6. Következő ajánlott lépés  

---

## 9. Promptstratégia (térkép — teljes promptok nélkül)

**Elv:** nincs egyetlen óriásprompt az egész prédikációra. A meglévő modulpromptok **érinthetetlenek**.

| # | MI-művelet | Összevonható? | Bemenet (rövid) | Kimenet | Temperature | Emberi jóváhagyás |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `suggest_sermon_main_idea` | — | textus fő gondolat, insights, alkalom | recommended + alts + warnings | 0.15–0.25 | Átveszem / mentés |
| 2 | `assess_sermon_main_idea` | — | user mondat + kontextus | assessment + revised | alacsony | Átvétel opcionális |
| 3 | `suggest_human_grace_block` | — | textus idea, insights, theology kivonat | 4 fő mező | alacsony | Mezőnkénti átvétel |
| 4 | `suggest_listener_tension` | 3-mal *nem* (külön szakma) | idea + human block | tension mezők | alacsony | Igen |
| 5 | `suggest_christ_arc` | — | idea, theology, insights | type + texts + uncertainty | **nagyon** alacsony | Igen + uncertainty |
| 6 | `suggest_sermon_path` | — | idea, stilus, tension | type + rationale | közepes-alacsony | Igen |
| 7 | `suggest_movements` | path-tal *nem* elsőre | idea + path + tension | 3–5 mozgás | közepes-alacsony | Szerkesztés + approve |
| 8 | `refine_one_movement` | 7 részlete | egy mozgás + kontextus | egy mozgás | alacsony | Igen |
| 9 | `suggest_closing` | — | idea + movements summary | closing mezők | alacsony | Igen |
| 10 | `run_homiletical_diagnostics` | — | teljes sermon_workshop kivonat | diagnostics | alacsony | Csak tükrözés |

**Összevonások később:** 3+4 „helyzet és feszültség” gyors módban; 7+8 mentor módban.

**Külön tartandó:** fő gondolat ≠ diagnosztika ≠ Krisztus-ív (különböző tévedési módok).

**Kreativitás:** exegetikai/teológiai szakaszokon 0.1–0.2; út/mozgás 0.2–0.35; soha magas „kreatív író” mód az első verzióban.

---

## 10. Fokozatos implementáció (mérföldkövek)

Minden lépés után: futóképes app, külön commit, visszaállítható.

### M3 — Keret, MI nélkül
- `sermon_workshop` adatmodell + `normalize_*`
- `ui_mode` harmadik érték + üres shell + szakaszradio
- kapu-szöveg a Textusműhelyben
- nincs Gemini

### M4 — Fő gondolat + emberi helyzet
- `sermon_main_idea` kézi + MI suggest/assess (új promptmodul)
- `human_condition_block` kézi + MI
- mentés / betöltés

### M5 — Feszültség + Krisztus-ív
- `listener_tension`, `christ_centered_arc`
- típusválasztó + uncertainty

### M6 — Út + mozgások
- `sermon_path`, `sermon_movements` szerkesztő
- MI ívjavaslat

### M7 — Képek, alkalmazás, lezárás
- átvétel `illustrations` / `actualization` → selected_*
- `closing`
- *nem* módosítja a régi promptokat

### M8 — Diagnosztika + polish
- `run_homiletical_diagnostics`
- `approved_sermon_decisions` továbbvitel
- regresszió (Gyorseszközök, Textusműhely, befagyasztott promptok)
- UX-finomítás; opcionális Gyors segítség / Mentor kísérlet

---

## 11. Kockázatok és elhárítás

| Kockázat | Hol | Elhárítás |
| --- | --- | --- |
| Túl bonyolult UI | Mozgások, 6+ kötelező mező | Egy nyitott szerkesztő; opcionális mezők expanderben |
| MI túl korán „kész prédikációt” ír | suggest_movements, óriásprompt | Tiltott all-in-one; rövid JSON mezők |
| Hallgatói relevancia felülírja a textust | tension, application | Prompt: textus elsőbbség; diagnostics textushűség |
| Chapell-sablon | human_condition | Opcionális false_belief; figyelmeztetés sablonra |
| Erőltetett Krisztus-központúság | christ arc | Típus: „nincs közvetlen”; uncertainty kötelező |
| Duplikáció Vázlat / Illusztráció / Aktualizálás | M7 | Átvétel, nem újraprompt; outline nem elsődleges forrás |
| Adatmodell-burjánzás | nested mezők | Összevont blockok; `desired_transformation` nélkül indul |
| Prédikátor hangjának elvesztése | minden MI | Átveszem = draft; Mentor később; diagnostics „saját hang” szempont |

---

## 12. Tesztelési irányelvek (későbbi implementációhoz)

- Régi projekt `sermon_workshop` nélkül betöltődik.  
- quick ↔ workshop ↔ sermon: adatok megmaradnak; nincs DuplicateElementKey (`sw_*` vs `tw_*`).  
- Befagyasztott promptok byte-szintű diffje változatlan.  
- Üres textus fő gondolat: figyelmeztetés, nincs összeomlás.  
- Diagnosztika nem írja felül a mezőket.  
- Mobil szélesség: egy szakasz, kevés elsődleges gomb.

---

## 13. Összefoglaló döntések

| Kérdés | Döntés |
| --- | --- |
| Navigáció | Háromelemű `ui_mode` + Textusműhely kapu-szöveg |
| Szakaszok száma | **9** |
| Homiletika | Természetes kérdések mögött; nincs szerző-fül |
| Adat | Nested `sermon_workshop` a `project_data` JSON-ban |
| Promptok | Új, külön műveletek; régiek érintetlenek |
| Első kód | **M3** — adatmodell + üres keret, MI nélkül |
| Mérföldkövek | **M3–M8** (6 lépés) |

---

*Dokumentum vége — `SERMON_WORKSHOP_SPEC.md` (tervezés; ne commitold / ne implementáld automatikusan ennél a lépésnél)*
