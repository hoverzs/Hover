# TEXTUS 2.0 — műszaki és UX-térkép

**Ág:** `textus-2.0-dev`  
**Státusz:** tervezési dokumentum (nincs implementáció)  
**Cél:** a meglévő Textus 1.x funkciók biztonságos átrendezése két műhelybe, gyorseszköz-használat megőrzésével.

---

## 1. A jelenlegi alkalmazás feltérképezése

### 1.1 Közös infrastruktúra

| Elem | Hol | Szerep |
|---|---|---|
| Tabok | `app.py` ~5565–5579 | 13 felső `st.tabs` |
| Projekt sáv | `_render_project_status_bar()` ~3852+ | Mentés, dirty, autosave, projektek |
| Szekció generálás | `generate_section(key)` ~3240 | `SECTION_PROMPTS` + `generate_text` |
| Egységes tab UI | `render_section_tab(...)` ~3276 | Generálás gomb, eredmény, chat, kosár |
| Gemini hívás | `generate_text(...)` ~4210+ | REST, cache, cooldown |
| Kontextus | `build_alap_from_state()` | `last_igehely/alkalom/stilus/sajat` |
| Mentés JSON | `workspace_data.PROJECT_DATA_KEYS` | Supabase `project_data` |
| CRUD | `project_storage.py` | `owner_sub` szűrés |

**`project_data`-ba kerülő tartalmi kulcsok** (`workspace_data.py`):  
`last_*`, `overview`, `exegesis`, `history`, `theology`, `illustrations`, `actualization`, `outline*`, `original_text`, `songs`, `series_*`, `basket`, `verse_history`, `*_chat` listák.

**Nem kerül mentésre:** API-kulcs, widget inputok (`igehely_input` stb.), running flag-ek, cache, auth cookie.

---

### 1.2 Modulok részletesen

#### Igehely — `tabs[0]` (~5586)

| | |
|---|---|
| **Render** | Inline a tabban (nincs külön `render_*`) |
| **Generálás** | `generate_section("overview")` — „Bibliai háttér összegzése” |
| **session_state olvas/ír** | Widget: `igehely_input`, `alkalom_input`, `stilus_input`, `sajat_input`; tartós: `last_*` (szinkron), `verse_history`, `overview`, `_overview_running` |
| **Eredmény** | Áttekintés / bibliai háttér markdown (`overview`) + bemeneti kontextus |
| **Felhasználók** | Minden szekció (`build_alap_from_state`); vázlat prompt; eredeti szöveg kijelzés |
| **Önállóan?** | Igen — igehely + áttekintés önmagában is használható |
| **project_data?** | Igen: `last_*`, `verse_history`, `overview` (widget kulcsok nem) |

#### Eredeti szöveg tanulmányozása — `tabs[1]` (~6298)

| | |
|---|---|
| **Render** | Inline |
| **Generálás** | Saját gomb → `build_original_text_prompt` + `generate_text(..., tab_label="Eredeti szöveg…")` |
| **session_state** | Olvas: `igehely_input` / `last_igehely`; ír: `original_text`, `original_text_chat`, `_original_running`, kosárjegyzet |
| **Eredmény** | Héber/görög kulcskifejezések, jelentésárnyalatok (`original_text`) |
| **Felhasználók** | Vázlatműhely (ha a kosárba kerül); nem kötelező a többi szekcióhoz |
| **Önállóan?** | Igen (igehely kell) |
| **project_data?** | Igen: `original_text`, `original_text_chat` |

#### Exegézis — `tabs[2]` (~5679)

| | |
|---|---|
| **Render** | `render_section_tab(key="exegesis", …)` |
| **Generálás** | `generate_section("exegesis")` |
| **session_state** | `exegesis`, `exegesis_chat`, `_exegesis_running`, kosár |
| **Eredmény** | Exegetikai háttér |
| **Felhasználók** | Vázlat prompt (`outline`); kosár → vázlat |
| **Önállóan?** | Igen |
| **project_data?** | Igen |

#### Kortörténet — `tabs[3]` (~5688)

| | |
|---|---|
| **Render / generálás** | `render_section_tab` / `generate_section("history")` |
| **session_state** | `history`, `history_chat` |
| **Eredmény** | Kortörténeti háttér |
| **Felhasználók** | Vázlat; kosár |
| **Önállóan?** | Igen |
| **project_data?** | Igen |

#### Teológia — `tabs[4]` (~5697)

| | |
|---|---|
| **Render / generálás** | `render_section_tab` / `generate_section("theology")` |
| **session_state** | `theology`, `theology_chat` |
| **Eredmény** | Teológiai hangsúlyok |
| **Felhasználók** | Vázlat; kosár |
| **Önállóan?** | Igen |
| **project_data?** | Igen |

#### Illusztrációk — `tabs[5]` (~5706)

| | |
|---|---|
| **Render / generálás** | `render_section_tab` / `generate_section("illustrations")` |
| **session_state** | `illustrations`, `illustrations_chat` |
| **Eredmény** | Illusztrációs ötletek |
| **Felhasználók** | Vázlat; kosár; Igehirdetési műhelyben később „képek” |
| **Önállóan?** | Igen |
| **project_data?** | Igen |

#### Aktualizálás — `tabs[6]` (~5715)

| | |
|---|---|
| **Render / generálás** | `render_section_tab` / `generate_section("actualization")` + Google Search tool |
| **session_state** | `actualization`, `actualization_chat` |
| **Eredmény** | Mai kapcsolódások |
| **Felhasználók** | Vázlat; kosár; később „emberi helyzet / alkalmazás” |
| **Önállóan?** | Igen |
| **project_data?** | Igen |

#### Vázlat — `tabs[7]` (~5729)

| | |
|---|---|
| **Render** | Inline műhely: draft → kérdések → átdolgozás → végleges + címek |
| **Generálás** | Több `generate_text` hívás (nem `generate_section`); olvassa overview/exegesis/history/theology/illustrations/actualization + `basket` |
| **session_state** | `outline`, `outline_draft`, `outline_workshop_*`, `outline_reworked_draft`, `outline_title_suggestions`, `outline_chat`, `_outline_*_running`, editor widget kulcsok |
| **Eredmény** | Szerkeszthető → végleges prédikációvázlat |
| **Felhasználók** | Word/Markdown export; kosár |
| **Önállóan?** | Részben — jobb, ha van előző elemzés, de üresen is indítható |
| **project_data?** | Igen (tartós outline mezők); editor widgetek nem |

#### Vázlatkosár — `tabs[8]` (~6238)

| | |
|---|---|
| **Render** | Lista + törlés / átrendezés jellegű UI |
| **Generálás** | Nincs saját Gemini — gyűjtő |
| **session_state** | `basket` (lista: `(forrás, szöveg)` párok) |
| **Eredmény** | Felhasználó által kiválasztott megjegyzések |
| **Felhasználók** | Vázlat készítése beemeli a kosarat |
| **Önállóan?** | Igen, mint gyűjtő |
| **project_data?** | Igen: `basket` |

#### Énekajánló — `tabs[9]` (~6388)

| | |
|---|---|
| **Render** | Inline |
| **Generálás** | `build_songs_prompt` + `generate_text` |
| **session_state** | `songs`, `songs_chat`, alkalom/énekeskönyv selectboxok, `_songs_running` |
| **Eredmény** | Liturgiai énekajánlás |
| **Felhasználók** | Export (docx); nem kötelező a vázlathoz |
| **Önállóan?** | Igen |
| **project_data?** | Igen: `songs`, `songs_chat` |

#### Igehirdetési sorozat tervező — `tabs[10]` (~7008)

| | |
|---|---|
| **Render** | Inline |
| **Generálás** | Saját prompt + `generate_text(..., tab_label="Igehirdetési sorozat tervező")` |
| **session_state** | `series_idea`, `series_weeks`, `series_cadence`, `series_planner_output` |
| **Eredmény** | Többhetes sorozatterv |
| **Felhasználók** | Jelenleg külön pálya (nem táplálja a vázlatot) |
| **Önállóan?** | Igen |
| **project_data?** | Igen |

#### Útmutatás — `tabs[11]` (~6916)

| | |
|---|---|
| **Render** | Statikus / súgó tartalom + visszajelzés szekció hívás |
| **Generálás** | Nincs |
| **session_state** | Feedback helper kulcsok |
| **Eredmény** | Útmutató szöveg |
| **Önállóan?** | Igen |
| **project_data?** | Nem (súgó) |

#### Beállítások — `tabs[12]` (~6500)

| | |
|---|---|
| **Render** | Fiók, Saját munkáim lista, API-kulcs, modell, cache, workspace JSON, feedback |
| **Generálás** | Csak API teszt |
| **session_state** | `api_key`, `using_builtin_key`, `user_model_choice`, `temperature`, `enable_cache`, projekt meta (`current_project_*`), debug |
| **Önállóan?** | Igen |
| **project_data?** | Nem (kulcsok / infra); projektcím a sávon → DB `title` mező |

---

### 1.3 Összefüggés-térkép (mai állapot)

```
Igehely (last_*) ──┬──► Eredeti szöveg
                   ├──► Exegézis / Kortörténet / Teológia / Illusztrációk / Aktualizálás
                   │         │
                   │         └──► Vázlatkosár (basket)
                   │                    │
                   └────────────────────┴──► Vázlat műhely ──► outline
Énekajánló ───────────────────────────────► (export)
Sorozattervező ───────────────────────────► (külön pálya)
```

---

## 2. Textus 2.0 szerkezeti térkép

### 2.1 Két fő munkatér

#### TEXTUSMŰHELY (szövegfeltárás)

| Új szakasz | Mai forrás | Átvitel jellege |
|---|---|---|
| Igehely, alkalom és szövegkörnyezet | Igehely tab | **Kisebb átalakítás** (UI keret; ugyanazok a mezők) |
| Eredeti szöveg és kulcsszavak | Eredeti szöveg tab | **Változtatás nélkül** modulként |
| Exegézis, műfaj és szerkezet | Exegézis | **Kisebb átalakítás** (prompt/címke finomítás később) |
| Kortörténeti háttér | Kortörténet | **Változtatás nélkül** |
| Teológiai hangsúlyok | Teológia | **Változtatás nélkül** |
| A textus nagy gondolata | Áttekintés (`overview`) + új, rövid kiemelés UI | **Összeolvadás / kiegészítés** (nem új Gemini-rendszer) |
| Mit viszünk tovább? | Vázlatkosár + új „jóváhagyás” lépés | **Átalakítás** → `approved_insights` felé |

#### IGEHÍRDETÉSI MŰHELY (prédikációformálás)

| Új szakasz | Mai forrás | Átvitel jellege |
|---|---|---|
| A prédikáció nagy gondolata | Új (táplálék: approved textus insights) | **Új szakasz**, meglévő `generate_text` réteggel |
| Emberi helyzet és kegyelmi válasz | Aktualizálás + teológia | **Összeolvadás** (ugyanazok a modulok / eredmények) |
| Hallgatói kérdés és feszültség | Új + aktualizálás | **Új szakasz** |
| Homiletikai út | Vázlat „homiletikai modell” select | **Kisebb átalakítás** |
| Prédikációs mozgások | Vázlat draft / pontok | **Átalakítás** strukturált `sermon_movements`-re |
| Képek, illusztrációk és alkalmazás | Illusztrációk + aktualizálás | **Összeolvadás megjelenítésben** |
| Lezárás | Vázlat vége / címek | **Kisebb átalakítás** |
| Homiletikai diagnosztika | Új | **Új szakasz** (2. mérföldkő után) |

### 2.2 Kiegészítők (műhelyen kívül vagy „Továbbiak”)

| Funkció | Döntés |
|---|---|
| Énekajánló | **Külön kiegészítő** marad |
| Sorozattervező | **Külön kiegészítő** marad |
| Útmutatás | **Továbbiak / súgó** |
| Beállítások + Fiók | **Továbbiak** vagy sticky fiók |
| Saját munkáim / Projekt sáv | **Saját munkáim** főnav + meglévő sáv egyszerűsítése |
| Teljes 13 fül párhuzamosan | Fokozatosan **fölöslegessé** válik a felső tab-sor, a modulok megmaradnak |

---

## 3. Gyors használat és teljes műhelymunka

**Egy modul = egy generáló út.** Nincs külön „gyors exegézis” és „műhely-exegézis” prompt-rendszer.

| Mód | Viselkedés |
|---|---|
| **Gyorseszköz** | A Textusműhely / Továbbiak egy szakasza önmagában megnyitható; igehely kell; eredmény a meglévő `session_state[key]`-be kerül; projekt nem kötelező; mentés opcionális |
| **Projekt-mód** | Megnyitott felhőprojekt + `approved_insights` lánc; a szakasz eredménye „továbbvisz” jelöléssel bekerülhet a következő fázisba |

Technikai elv:

- UI: két belépési pont (Kezdőlap kártya / műhely-expander), **ugyanaz** a `generate_section` / `render_section_tab` / meglévő custom generator.
- Állapot: továbbra is a mai kulcsok (`exegesis`, `theology`, …) az első mérföldkőben.
- Projekt: csak a jóváhagyott felismerések (`approved_insights`) képeznek új, strukturált hidat — implementáció később.

---

## 4. Adatáramlás (célállapot — még nem implementált)

```
[Modul teljes eredménye]     pl. exegesis markdown
        │
        ▼
[Felhasználói válogatás]     kosár / „viszem tovább” jelölés
        │
        ▼
approved_insights            strukturált, rövidített felismerések
        │
        ▼
Igehirdetési műhely          nagy gondolat, feszültség, út…
        │
        ▼
sermon_movements             prédikációs mozgások (lista)
        │
        ▼
outline / outline_basket     vázlat + kosár
        │
        ▼
diagnostics                  homiletikai diagnosztika
```

### Javasolt új projekt-adatcsomagok (terv)

| Kulcs | Tartalom (vázlat) |
|---|---|
| `text_workshop` | Meta: mely textus-szakaszok készültek el; opcionális összefoglalók |
| `approved_insights` | `{source, text, tags?}[]` — jóváhagyott továbbvitel |
| `sermon_workshop` | Nagy gondolat, helyzet, kérdés, út, lezárás mezők |
| `sermon_movements` | Rendezett mozgások / pontok |
| `outline_basket` | Mai `basket` utódja vagy alias |
| `diagnostics` | Diagnosztikai futások eredménye |

**Első mérföldkőben ezeket NEM vezetjük be** — a mai `PROJECT_DATA_KEYS` marad.

---

## 5. Új navigációs javaslat (mobilbarát)

### Fő szint (max. 5)

1. **Kezdőlap** — projekt státusz, gyorsindítás (egy szakasz), „folytatás”
2. **Textusműhely** — összecsukható szakaszok (expander / accordion)
3. **Igehirdetési műhely** — ugyancsak expander-szakaszok
4. **Saját munkáim** — lista, megnyitás, törlés (mai Projekt sáv + Beállítások lista)
5. **Továbbiak** — Ének, Sorozat, Útmutatás, Beállítások / API

### Elvek

- Ne legyen 13 felső tab.
- Műhelyeken belül **egy nyitott szakasz** legyen a fókusz (accordion).
- Sticky / felső sáv: projektcím + Mentve/dirty + Mentés (mai sáv egyszerűsítve).
- Mobilon: alsó nav (5 ikon) vagy selectbox főnav — Streamlit korlátok miatt első körben `st.navigation` / radio / select a legpraktikusabb.

### Átmeneti kompatibilitás

Amíg a 13 tab él: a Kezdőlapról mélylink / scroll a meglévő tabokra **vagy** párhuzamosan megjelenő expander-nézet, amely ugyanazokat a renderelőket hívja.

---

## 6. Kockázatok

| Kockázat | Részletek | Védelem |
|---|---|---|
| Egyszerre UI + prompt + séma | Könnyen eltörik a mentés / dirty hash | Fázisonként: először csak UI keret |
| session_state ütközés | Widget kulcsok (`igehely_input`) vs `last_*`; outline editor pending minta | Meglévő pending minták megőrzése; új kulcs csak új namespace alatt |
| Generálás duplikáció | Második exegézis-prompt „műhelyhez” | Tilos; egy `generate_section` / meglévő custom út |
| Vázlat függőségei | Üres overview mellett gyenge minőség | Figyelmeztetés, nem hard gate a gyorsmódban |
| Autosave / dirty | Új struktúra megváltoztatja a fingerprintet | `PROJECT_DATA_KEYS` bővítésével együtt dirty újraszámolás |
| Auth Cloud | `[auth]` nélkül `st.user` attribútumok | Meglévő `_is_logged_in()` guard |
| Fölösleges párhuzamos fájlok | Korábbi `project_store.py` | Már törölve; ne hozzunk létre másodikat |

**Változatlanul megőrzendő (stabil mag):**

- `generate_text`, `generate_section`, `render_section_tab`
- `workspace_data` / `project_storage` / `supabase_client`
- Gemini modell-mapping, cooldown, cache
- Opcionális Google login + vendég mód
- API-kulcs kezelés

**Fokozatos átállás:**

1. Dokumentum + baseline ág (kész)  
2. Navigációs keret + Textusműhely expander-ek, tabok még élnek  
3. Tabok elrejtése / átirányítás  
4. `approved_insights` + Igehirdetési műhely  
5. Diagnosztika, modernebb homiletikai promptok  

Minden lépés után: helyi smoke + Cloud reboot + mentés/megnyitás teszt.

---

## 7. Első megvalósítási mérföldkő (ajánlás)

### Cél

**M0 — „Textusműhely keret”:** a meglévő szövegfeltáró funkciók egy Textusműhely oldalon, összecsukható szakaszokban jelennek meg, **ugyanazokkal** a generáló függvényekkel. Nincs új homiletikai generálás, nincs új DB-séma, nincs `approved_insights` implementáció.

### Scope (igen)

- Új főnézet: „Textusműhely” (pl. `st.navigation` vagy egy „nézet” select a tabok mellett/helyett)
- Expander szakaszok: Igehely+áttekintés, Eredeti szöveg, Exegézis, Kortörténet, Teológia, Illusztrációk, Aktualizálás, (opcionális) Mit viszünk tovább? = meglévő kosár UI
- Meglévő `render_section_tab` / Igehely / eredeti szöveg kód **újrahasználata** (függvények kiemelése UI-törés nélkül, ha szükséges)
- Gyorselérés: Kezdőlapról vagy Továbbiakból egy-egy szakasz továbbra is indítható
- Régi 13 tab **még elérhető** (feature flag vagy „Klasszikus nézet”)

### Scope (nem)

- Igehirdetési műhely új promptjai
- Diagnosztika
- Új `project_data` struktúrák
- Autosave / auth átalakítás
- Adatbázis-migráció

### Készültségi kritériumok

- Exegézis generálás ugyanúgy működik Textusműhelyből és klasszikus fülről
- Projekt mentés/betöltés változatlan
- Vendég mód változatlan
- Nincs regresszió az API-kulcs Beállításokban

### Becsült érintett fájlok (későbbi implementáció)

- `app.py` (navigáció + UI keret)  
- Esetleg `textus_workshop_ui.py` (csak render, ha szétválasztjuk)  
- **Nem:** `project_storage.py` séma, Supabase

---

## Függelék A — Tab index gyorsreferencia

| Index | Címke |
|---:|---|
| 0 | Igehely |
| 1 | Eredeti szöveg tanulmányozása |
| 2 | Exegézis |
| 3 | Kortörténet |
| 4 | Teológia |
| 5 | Illusztrációk |
| 6 | Aktualizálás |
| 7 | Vázlat |
| 8 | Vázlatkosár |
| 9 | Énekajánló |
| 10 | Igehirdetési sorozat tervező |
| 11 | Útmutatás |
| 12 | Beállítások |

## Függelék B — Kapcsolódó modulok

| Fájl | Szerep |
|---|---|
| `app.py` | UI + generálás + auth UI |
| `workspace_data.py` | Mentendő kulcsok / fingerprint |
| `project_storage.py` | Supabase CRUD |
| `supabase_client.py` | Kliens |
| `.streamlit/secrets.toml` | Titkok (gitignore) |
