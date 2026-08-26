# TEXTUS Knowledge Base — rendszeraudit (core fázis)

**Audit dátuma:** 2026-08-23 (Phase 0 bővítés: §7–15)  
**Repository gyökér:** `C:/Users/Hover/Textus`  
**Ág:** `feature/knowledge-base-core`  
**Bázis commit:** `707645d` — *Merge pull request #13 from hoverzs/feature/hymn-database*  
**Jelleg:** teljesen módosítás nélküli readiness audit — **csak ez a fájl módosul**.

Jelölések ebben a jelentésben:

- **[Tény]** — fájlúttal, függvénynévvel, teszttel vagy számlálással igazolt.
- **[Következtetés]** — tényekből levont, de nem közvetlenül mért állítás.
- **[Feltételezés / futás nélkül]** — kód alapján valószínű, de élő Streamlit/Supabase/Gemini futás nélkül nem bizonyított.

Kapcsolódó, részterületi auditok (nem helyettesítik ezt a dokumentumot):

- `docs/biblical_map_status_audit.md` — bibliai térkép / helyszín-adat
- `docs/hebrew_ot_architecture_audit.md` — TAHOT/TBESH forrás és séma
- `textus_teljes_rendszeraudit_2026-07-25.md` — AI-motor és műhelyfolyamat

---

## 1. Git-állapot

| Tétel | Érték | Bizonyíték |
|---|---|---|
| Gyökér | `C:/Users/Hover/Textus` | `git rev-parse --show-toplevel` |
| Aktuális ág | `feature/knowledge-base-core` | `git branch --show-current` |
| Bázis | `main` @ `707645d` | branch a friss `main`-ről lett létrehozva |
| `main` vs `origin/main` | **szinkronban** | mindkettő: `707645da322347a74daacff9b1e8da03ab259677` |
| Working tree az audit előtt | **tiszta** | `git status --porcelain` üres |
| Commit / push ebben a feladatban | **nem történt** | felhasználói utasítás |

**[Tény]** Ez az audit kizárólag `docs/textus_knowledge_base_audit.md` létrehozását célozza; production kód, séma, dependency és konfiguráció érintetlen.

---

## 2. Mi a „Knowledge Base” a TEXTUS-ban ma?

**[Következtetés]** A TEXTUS **nem rendelkezik** egyetlen, központi „Knowledge Base” modullal, sémával vagy szinkronréteggel. A tudás **szigetelt adattárakban** él, mindegyik saját import/build scripttel, repository-val és fogyasztói szerződéssel:

| Sziget | Típus | Runtime olvasás | AI / UI fogyasztó |
|---|---|---|---|
| Görög NT tokenek (TAGNT) | SQLite | `greek_token_repository.py` | exegézis token-blokk, görög panel, grounding check |
| Héber ÓSZ tokenek (TAHOT) | SQLite | `hebrew_token_repository.py` | exegézis token-blokk, eredeti nyelvi konkordancia, grounding check |
| Görög lexikon (TBESG) | SQLite (build) | `greek_lexicon_repository.py` | görög elemző UI |
| Héber lexikon (TBESH) | SQLite | `hebrew_lexicon_repository.py` | héber demo / lexikon lookup |
| Magyar lexikon overlay | JSON | `lexicon_hu.py`, `hebrew_lexicon_hu.py` | görög/héber UI magyar gloss |
| RÚF 2014 teljes szöveg | SQLite + FTS5 | `ruf_bible_local_db.py` | konkordancia (literal + concept lookup) |
| RÚF 2014 élő API | HTTP | `ruf_bible_service.py` | fő igehely-mező, passage fetch |
| Énekek (ERE/RE21/RE48) | SQLite + FTS5 | `hymn_repository.py` | `hymn_recommendation_ai.py` |
| Bibliai helyszínek | JSON katalógus | `biblical_map_data.py` | térkép UI, history prompt-injekció |
| Helyszín enrichment | JSON overlay | `biblical_place_enrichment.py` | térkép kártya + `build_biblical_place_history_context()` |
| Bibliai útvonalak | JSON | `biblical_routes.py` | térkép útvonal-nézet |
| Felhasználói projektek | Supabase | `project_storage.py` | munkamenet, passage history — **nem kanonikus KB** |

**[Következtetés]** A `feature/knowledge-base-core` célja valószínűleg egy **egységes olvasási réteg, verziózás és integrációs szerződés** bevezetése e fölött — jelenleg ez **0%-os implementáció**, de az adat és a minták már léteznek.

---

## 3. Adattárak — részletes leltár

### 3.1 SQLite adatbázisok

Útvonal-alap: `bible_engine/paths.py` → `data/generated/`.

| Fájl | Git | Séma / táblák (fő) | Forrás | Megjegyzés |
|---|---|---|---|---|
| `tagnt_nt.sqlite3` | **tracked** | `greek_tokens` | STEPBible TAGNT | ~142k token ([Tény] `nt_lexicon_coverage_report.json`) |
| `tahot_ot_runtime.sqlite3` | **tracked** | `metadata`, `books`, `tokens`, `token_strong_ids`, `ketiv_qere` | STEPBible TAHOT (pruned runtime) | teljes ÓSZ token réteg |
| `tbesh_lexicon_runtime.sqlite3` | **tracked** | `metadata`, `lexicon_entries` | STEPBible TBESH | angol fallback lexikon |
| `tbesg_lexicon.sqlite3` | **gitignored** | `greek_lexicon` | STEPBible TBESG | **lokálisan build szükséges** |
| `hymns.sqlite3` | **gitignored** | `hymnals`, `sections`, `hymns`, `stanzas`, `hymns_fts`, `import_meta` | DTX/DOCX + `scripts/build_hymn_database.py` | Supabase privát tükör is |
| `ruf_bible.sqlite3` | **soha ne commitold** | `verses`, `verses_fts`, `fetch_log`, `import_meta` | Szentírás.eu API bulk | szerződéses, belső használat |

**Env felülírások:** `TEXTUS_TAGNT_DB_PATH`, `TEXTUS_TBESG_DB_PATH`, `TEXTUS_HYMN_DB_*`, Supabase bucket/object/sha256 az ének- és RÚF-bootstraphez.

**`.gitignore` policy [Tény]:** blanket `*.sqlite3` tiltás, kivételek csak `tahot_ot_runtime.sqlite3` és `tbesh_lexicon_runtime.sqlite3`; RÚF explicit tiltás kommenttel.

### 3.2 JSON katalógusok és overlay-ek

**Lexikon / alias (`bible_engine/data/`):**

| Fájl | Szerep |
|---|---|
| `lexicon_hu.json` | Magyar NT Strong → gloss (overlay) |
| `hebrew_lexicon_hu.json` | Magyar héber lexikon overlay |
| `strong_aliases.json`, `hebrew_strong_aliases.json` | Strong alias mapok |

**Bibliai helyszínek (`data/biblical_places/`) — runtime:**

| Fájl | Méret (2026-08-23) | Szerep |
|---|---:|---|
| `biblical_places_catalog.json` | **1267** hely | kanonikus katalógus |
| `passage_place_links.json` | **8654** link | igehely ↔ hely |
| `place_enrichments.json` | **20** profil | UI overlay |
| `place_enrichment_sources.json` | forrásregiszter | enrichment attribution |
| `sources.json` | forrásregiszter | katalógus attribution |

**Nem runtime (build/review):** `enrichment_research/*`, `hungarian_review_*`, `duplicate_*`, `enrichment_batches/*`.

**Útvonalak (`data/biblical_routes/`):**

| Fájl | Méret | Megjegyzés |
|---|---:|---|
| `biblical_routes.json` | **23** útvonal | a korábbi térképes audit 12-t említ — a katalógus bővült |

**Generált audit JSON (`data/generated/`):** `nt_lexicon_coverage_report.json`, `missing_tagnt_strong_id_audit.json`, `tagnt_strong_alias_candidates.json`.

### 3.3 Külső / távoli források

| Forrás | Hozzáférés | KB-szerep |
|---|---|---|
| STEPBible-Data (GitHub) | build scriptek | TAGNT, TAHOT, TBESG, TBESH |
| Szentírás.eu REST | API kulcs | élő RÚF szöveg |
| Supabase Storage (privát) | app bootstrap | `ruf_bible.sqlite3`, `hymns.sqlite3` tükör |
| OpenBible geocoding | import | helyszín koordináták |
| Pleiades | import | antik helynév / ID |
| Google Search (Gemini tool) | API | aktualizálás — **nem helyi KB** |

---

## 4. Repository-minták (`bible_engine/`)

**[Tény]** Közös építőkocka-minta minden szigetnél:

```text
forrásfájl (TSV/DTX/JSON/API)
  → parser modul
  → sqlite import / schema modul
  → read-only repository (runtime határ)
  → UI vagy AI fogyasztó
```

| Domain | Parser | SQLite | Repository | Kulcs viselkedés |
|---|---|---|---|---|
| Görög token | `tagnt_parser.py` | `tagnt_sqlite.py` | `greek_token_repository.py` | `load_greek_passage_tokens()` |
| Héber token | `hebrew_parser.py` | `hebrew_sqlite.py` | `hebrew_token_repository.py` | `HebrewTokenRepository.passage()` |
| Görög lexikon | `tbesg_parser.py` | `tbesg_sqlite.py` | `greek_lexicon_repository.py` | TBESG hiány → `TBESGDatabaseUnavailableError` |
| Héber lexikon | `tbesh_parser.py` | (TBESH import) | `hebrew_lexicon_repository.py` | TBESH + HU JSON alias |
| Ének | `hymn_dtx_parser.py`, `hymn_docx_parser.py` | `hymn_sqlite.py` | `hymn_repository.py` | checksum/count invariant; **soha nem talál ki számot/címet** |
| Grounding | — | — | `original_language_grounding_check.py` | post-hoc AI ellenőrzés, non-blocking |

**[Következtetés]** A jó minták (read-only repo, build/runtime szétválasztás, checksum, env override) **újrahasználhatók** egy központi KB-core réteghez; a hiányzó elem a **kereszt-modulis entitás-modell és verzió-registry**.

---

## 5. AI és UI: grounded vs modellmemória

Grounding erősségi skála (erős → gyenge):

| Szint | Példa | Mechanizmus |
|---|---|---|
| 1 — determinisztikus DB | eredeti nyelvi konkordancia, görög token panel | csak SQLite/JSON |
| 2 — LLM + DB validáció | énekajánló, concept konkordancia | modell javasol → repo validál / lookup |
| 3 — LLM + szintaxis | igehely-kereső | `parse_bible_reference()` — **nincs RÚF existence check** |
| 4 — részleges injekció | history helyszín-blokk | csak `source_backed` + high/medium szakaszok |
| 5 — modellmemória | exegézis, teológia, illusztráció | Gemini + prompt; részben grounding check utólag |

### Modulonkénti összefoglaló

| Modul | Fájl | Grounded | Modellmemória / rés |
|---|---|---|---|
| Énekajánló | `hymn_recommendation_ai.py` | jelöltpool FTS + `validate_hymn_ids()` | pastoral indoklás |
| Igehely-kereső | `passage_search_ai.py` | history + referencia-szintaxis | 5 javaslat szövege; **nem ellenőrzi a lokális RÚF DB-t** |
| Concept konkordancia | `concept_concordance.py` | post-LLM `lookup_local()` | kulcsszavak/refs kinyerése |
| Eredeti nyelvi konkordancia | `original_language_concordance.py` | TAGNT/TAHOT + RÚF kontextus | nincs LLM |
| History helyszín | `app.py` `build_biblical_place_history_context()` | max 2 hely, szűrt enrichment | a history szekció többi része modell |
| Exegézis / eredeti szöveg | `app.py` + `original_language_grounding_check.py` | token-blokk injekció + post-hoc Strong/lemma check | filológiai tartalom |
| Aktualizálás | `app.py` Google Search | web grounding | nem helyi KB |
| Térkép UI | `biblical_map_ui.py` | JSON render | nincs runtime LLM prose |

**[Tény]** `hymn_recommendation_ai.py` modul-docstring: *„hymn numbers, display numbers, first lines, and titles always come from hymn_repository”*.

**[Tény]** `passage_search_ai.py` modul-docstring: *„A modell csak referenciát és magyarázatot ad — bibliai idézetet nem.”*

**[Következtetés]** A TEXTUS már tartalmaz **mintát a „grounded recommendation” architektúrához** (ének); a KB-core ezt általánosíthatná más entitásokra (igehely, hely, lexikon-szó, hitvallás-idézet stb.).

---

## 6. Kapcsolódó modulok (nem kanonikus KB)

### `project_storage.py` / Supabase

- Tábla: `projects`, szűrés: `owner_sub`
- Payload: `workspace_data.build_project_data()` — AI kimenetek, műhelyállapot
- **[Következtetés]** Felhasználói **munkaterület**, nem tartalmi tudásbázis; passage history kizárásra használja az igehely-kereső.

### RÚF kettős útvonal

| Útvonal | Modul | Használat |
|---|---|---|
| Élő API | `ruf_bible_service.py` | fő igehely mező, cache |
| Lokális DB | `ruf_bible_local_db.py` | konkordancia, `lookup_local()` |

**[Tény]** A RÚF modul-docstring négy szerződéses kötelezettséget kód-szinten is rögzít: szó szerinti tárolás, belső használat, copyright megjelenítés, egyfájlos purge.

### Konkordancia stack

| Réteg | Modul |
|---|---|
| UI | `concordance_ui.py` |
| Magyar literal | `ruf_bible_local_db.search_literal()` |
| Eredeti nyelv | `original_language_concordance.py` |
| Concept | `concept_concordance.py` |

---

## 7. Canonical Scripture Reference audit

### 7.1 Van-e központi canonical reference?

**[Következtetés]** **Nincs** dedikált canonical reference modul vagy globális verse-ID séma. A de facto központ **`ruf_bible_service.parse_bible_reference()`** — de ez a **RÚF fetch-szerződés** része, nem platform-szintű KB-kulcs.

| Réteg | Belépési pont | Belső reprezentáció | Kanonikus? |
|---|---|---|---|
| **RÚF élő API** | `fetch_ruf_passage()` → `ParsedReference.api_reference` | `BookInfo.code` (pl. `JHN`) + fejezet/vers; API string: `Jn 3,16` (kötőjel: `-`) | **De facto parser-forrás** |
| **RÚF lokális SQLite** | `lookup_local(book_code, chapter, verse_start, verse_end)` | `verses.book_code`, `chapter`, `verse`; megjelenítés: `reference` mező API-formátumban; **`ordinal`** = könyv kanonikus sorszám (1–66) | Ugyanaz a `book_code`, mint parser |
| **TAGNT (görög NT)** | `load_greek_passage_tokens()` → `parse_tagnt_bible_reference()` | DB: `book` = TAGNT kód (`Jhn`, `Mat`…); RÚF→TAGNT: `RUF_TO_TAGNT_BOOK_CODES` | Külön könyvkód-tér |
| **TAHOT (héber ÓSZ)** | `HebrewTokenRepository.passage()` → `parse_hebrew_reference()` | DB: `book` = TAHOT kód (`Gen`, `Rut`…); RÚF→TAHOT: `tahot_book_code_from_ruf_code()` | Külön parser + alias-tér |
| **Konkordancia** | `concept_concordance`: `parse_bible_reference` + `lookup_local`; `original_language_concordance`: héber/görög saját parser | Concept: normalizált ref string; eredeti nyelv: token lookup | Vegyes |
| **Görög/héber panelek** | `build_original_language_token_block()` → `greek_reference_status()` / `parse_hebrew_reference()` | Ugyanaz, mint TAGNT/TAHOT | Ugyanaz |
| **Helyszín / útvonal** | `find_place_links_for_passage()` → `passage_refs_overlap()`; route: `find_route_stop_matches_for_passage()` | JSON: `"JHN 4,5"` (RÚF kód + vessző); OpenBible: `"osis": "John.4.5"` | **Két párhuzamos forma** |
| **Exegézis / Kortörténet / Teológia** | `generate_section()` → `build_alap_from_state()` | Promptban: nyers `last_igehely` string + opcionális token/hely blokk; **nincs normalizált KB-kulcs** | Nem kanonikus |

**Megosztott segéd:** `biblical_passage_refs.py` — `PassageSpan`, `passage_span()`, `passage_refs_overlap()`; mind **`parse_bible_reference()`-re épít**.

### 7.2 Könyvkódok és referenciaformátumok

**RÚF `BookInfo.code` (66 könyv)** — `[Tény]` `ruf_bible_service._BOOK_DEFS`: pl. `JHN`, `GEN`, `1CO`, `PSA`. Megjelenítő rövidítés: `Jn`, `1Móz`, `ApCsel` (`BookInfo.abbr`).

**TAGNT könyvkódok** — `[Tény]` `tagnt_books.RUF_TO_TAGNT_BOOK_CODES`: pl. `JHN`→`Jhn`, `1CO`→`1Co` (27 NT könyv).

**TAHOT könyvkódok** — `[Tény]` `hebrew_books.OT_BOOKS`: pl. `GEN`→`Gen`, `PSA`→`Psa` (39 ÓSZ könyv).

**OpenBible OSIS** — `[Tény]` `passage_place_links.json`: `"osis": "John.4.5"` (ponttal elválasztott angol könyvnév).

**Felhasználói / UI formátumok** — `[Tény]` `parse_bible_reference()` elfogad: `Jn 4,1–42`, `Ján 4,1-42`, `1Jn 4,7`, ékezetes magyar aliasok; normalizált kimenet: magyar rövidítés + `,` + en-dash `–` (pl. `Jn 4,1–42`).

**Import JSON eltérés** — `[Tény]` OpenBible-generált linkek: `"reference": "JHN 4,5"` (3 betűs RÚF **code**, ASCII kötőjel `-` a tartományban). A UI tipikusan `Jn 4,5`-öt használ. Mindkettő ugyanarra a `BOOK_LOOKUP`-ra fut, de a **tárolt string nem egységes**.

### 7.3 Könyvnév-normalizálás

| Mechanizmus | Fájl | Logika |
|---|---|---|
| RÚF alias-fold | `ruf_bible_service._fold()` | NFKD + ékezet strip + whitespace/pont eltávolítás + casefold → `BOOK_LOOKUP` |
| TAGNT alias | `tagnt_books._normalize_reference_alias()` | Minimális (pl. `1thessz`→`1Thess`) → majd `parse_bible_reference()` |
| Héber OT alias | `hebrew_books._fold_book_alias()` + `OT_BOOKS.aliases` | Külön alias lista, **nem** a teljes RÚF lookup |
| OpenBible import | `biblical_map_import` pipeline | OSIS → belső referencia; runtime JSON-ben mindkét forma megmarad |

**[Következtetés]** Három párhuzamos normalizátor van (RÚF / héber OT / OSIS-import), **nincs** visszafelé kompatibilis „canonical ID” export minden fogyasztónak.

### 7.4 Szakasz-reprezentáció

**[Tény]** Közös modell: `PassageSpan(book_code, start_chapter, start_verse, end_chapter, end_verse)` — `biblical_passage_refs.passage_span()`.

Támogatott input-minták:

- egy vers / vers-tartomány egy fejezeten belül: `Jn 4,1–42`;
- fejezet-tartomány: `Jn 4-5` → `end_verse=999` sentinel;
- keresztfejezetes (egy könyv): `Jn 4,1-5,10` — `is_valid_cross_chapter_reference()`.

**Korlátok [Tény]:**

- `build_original_language_token_block()`: `greek_reference_status()` → **keresztfejezetes görög token blokk tiltva** (`CROSS_CHAPTER_GREEK_MESSAGE`);
- TAGNT repo: vers-szintű lekérés, fejezet-only ref elutasítva;
- TAHOT: `parse_hebrew_reference()` **kötelező versszám** — fejezet-only OT token blokk nem megy.

### 7.5 Globális verse ordinal

**[Tény]** A RÚF lokális DB `verses.ordinal` mezője = **könyv szintű** kanonikus sorszám (1–66), **nem** globális vers-index a teljes Bibliában — `scripts/build_ruf_bible_db.py` + `CANONICAL_BOOKS`.

**[Következtetés]** **Nincs** globális verse ordinal (pl. 1…31 102). Külső források (OSIS, UBS, STEP record ID) **nem** map-elhetők egyetlen meglévő mezőre.

### 7.6 Versifikációs és referencia-kockázatok (új külső forrásoknál)

| Probléma | Példa / bizonyíték | KB-hatás |
|---|---|---|
| **Psalm / Jeremias vers-számozás** | RÚF egyetlen versifikáció; kommentár-források gyakran KJV/MT/LXX eltérés | chunk ↔ verse mapping hibás lehet |
| **Single-chapter könyvek** | `OBA`, `2JN`, `3JN`, `JUD`, `PHM` — `BookInfo.single_chapter` | fejezet=1 kényszer |
| **NT-only vs OT-only token DB** | TAGNT / TAHOT szétválasztás | cross-testament „eredeti nyelv” rés |
| **OSIS vs RÚF abbr** | `John.4.5` vs `Jn 4,5` vs `JHN 4,5` | import duplikátum / missed join |
| **Apocrypha / deuterokanonikus** | nincs a 66 könyvben | külső forrás nem parse-olható |
| **Perikópa vs vers** | AI promptok szabad szövegű `last_igehely`-et használnak | retrieval span eltérés |
| **Magyar vs angol könyvnév** | `_BOOK_DEFS` magyar-centrikus aliasok | angol forrás-import extra mapping |

### 7.7 Újrahasználható elemek

| Elem | Újrahasználat |
|---|---|
| `parse_bible_reference()` | **Parser motor** — ne duplikálni |
| `ParsedReference` + `PassageSpan` | Belső span modell |
| `passage_refs_overlap()` | Retrieval / link matching |
| `RUF_TO_TAGNT_BOOK_CODES` / `tahot_book_code_from_ruf_code()` | Consumer-specifikus export |
| `CANONICAL_BOOKS` | Könyv sorrend + ordinal |
| OpenBible `osis` mező | Külső ID forrás — map table input |

### 7.8 Minimális új canonical reference / mapping réteg (terv — nem implementáció)

Javasolt **read-only** modul (pl. `textus_kb/canonical_reference.py`), amely **delegál**, nem helyettesít:

```text
CanonicalReference:
  ruf_book_code: str          # JHN — belső primary key
  span: PassageSpan
  display_hu: str             # parsed.normalized_reference
  osis: str | None             # John.4.1-John.4.42 (generált)
  tagnt_book: str | None
  tahot_book: str | None
  testament: "OT" | "NT"
  single_chapter: bool

CanonicalReference.parse(text) -> CanonicalReference
  └─ parse_bible_reference + passage_span (meglévő)

CanonicalReference.for_consumer(consumer: "ruf"|"tagnt"|"tahot"|"osis"|"openbible_json")
  └─ kód-transzformáció, nem újra-parse
```

**MVP scope:** parse + normalize + consumer export + overlap; **nem** globális verse ordinal; **nem** versifikáció-korrekció.

**Elfogadás:** `CanonicalReference.parse("Jn 4,1–42").ruf_book_code == "JHN"` és `.for_consumer("osis")` stabil string; unit tesztek a §13 szerint.

---

## 8. Knowledge Base Core – repo-specifikus adatmodell

A modell **nem** másolja mechanikusan egy általános RAG-sémát: a TEXTUS már read-only SQLite + JSON overlay + import audit mintákat használ. A KB Core **index + registry + olvasási facade** — a tartalom nagy része továbbra is meglévő artifactokban marad.

### 8.1 Tárolási stratégia: SQLite / Supabase / hibrid

| Opció | Értékelés |
|---|---|
| **Csak Supabase/PostgreSQL** | User projects már ott van; de RÚF **tilos** publikus DB-be; nagy TAGNT/TAHOT clone felesleges; pgvector infra nincs |
| **Csak helyi SQLite** | Illeszkedik a `bible_engine/*` mintához; jól verziózható artifact; Streamlit Cloud deploy: kis registry fájl gitben |
| **Hibrid (javasolt MVP)** | **Tartalom:** meglévő SQLite/JSON artifactok változatlan helyen; **KB Core meta:** `data/kb/kb_core.sqlite3` (gitignored vagy kis tracked manifest JSON) + opcionális Supabase **csak** nem-RÚF publikálható meta/chunk index később |

**[Következtetés]** MVP = **hibrid**: meta/index SQLite (vagy kezdetben csak `kb_manifest.json`) + delegálás meglévő repo-kra. PostgreSQL/pgvector **későbbi fázis**, amikor chunk+embedding skálázás kell.

### 8.2 Komponens-táblázat

Minden sor: **feladat | tárolás | fő mezők | kapcsolatok | új/meglévő | MVP?**

#### Source registry

| | |
|---|---|
| **Feladat** | Külső/belső adatforrás azonosító, attribution, base URL |
| **Tárolás** | Kezdet: **`data/biblical_places/sources.json` + `place_enrichment_sources.json` mintája** → egységesített `kb_sources` tábla vagy manifest szekció |
| **Mezők** | `source_id`, `name`, `kind` (stepbible/openbible/ruf_contract/institutional), `license_code`, `attribution_hu`, `reference_only` bool |
| **Kapcsolatok** | → source_version, document, chunk |
| **Új/meglévő** | **Részben meglévő** JSON — MVP: manifest-be emelt unifikált lista |
| **MVP** | **Kötelező** (manifest szinten) |

#### Source version registry

| | |
|---|---|
| **Feladat** | Buildelt artifact verzió, checksum, import idő |
| **Tárolás** | `import_meta` táblák (hymns, ruf) + **`kb_manifest.json`** per artifact |
| **Mezők** | `source_id`, `artifact_path`, `sha256`, `record_counts`, `built_at`, `schema_version` |
| **Kapcsolatok** | source → artifact file |
| **Új/meglévő** | **Új** manifest; minta: `hymn_repository` expected checksums |
| **MVP** | **Kötelező** |

#### License registry

| | |
|---|---|
| **Feladat** | Licenc kód → kötelező attribution, export tiltás, chunk-olhatóság |
| **Tárolás** | Kezdet: **`docs` + JSON `license` mezők**; MVP: `kb_licenses.yaml` vagy manifest beágyazás |
| **Mezők** | `license_id`, `spdx_or_custom`, `allow_chunk_in_prompt`, `allow_embedding`, `requires_attribution`, `purge_on_contract_end` |
| **Kapcsolatok** | → source |
| **Új/meglévő** | **Új** egységes registry; szöveg RÚF modul-docstringből |
| **MVP** | **Kötelező** (RÚF + STEPBible minimum) |

#### Canonical verse / reference mapping

| | |
|---|---|
| **Feladat** | §7 szerinti cross-layer kulcs |
| **Tárolás** | **Kód modul** + opcionális `kb_book_codes` lookup tábla (66 sor + osis + tagnt + tahot) |
| **Mezők** | `ruf_code`, `osis_book`, `tagnt_code`, `tahot_code`, `ordinal`, `testament` |
| **Kapcsolatok** | → passage_links, retrieval |
| **Új/meglévő** | **Új** modul; adat: `CANONICAL_BOOKS` + mapok |
| **MVP** | **Kötelező** |

#### Documents

| | |
|---|---|
| **Feladat** | Címzett, forrásolt szöveges egység (pl. enrichment szakasz, később kommentár bekezdés) |
| **Tárolás** | MVP: **nem új DB** — hivatkozás meglévő JSON/SQLite sorra (`place_enrichment` section, lexicon entry) |
| **Mezők** | `document_id`, `source_id`, `source_version`, `content_type`, `language`, `external_ref`, `payload_ref` (fájl+path) |
| **Kapcsolatok** | → chunks, passage_links |
| **Új/meglévő** | **Új** logikai ID; fizikai tárolás meglévő |
| **MVP** | **Kötelező** (logikai réteg) |

#### Chunks

| | |
|---|---|
| **Feladat** | Prompt-injekciós egység (Evidence Packet atom) |
| **Tárolás** | MVP: **generált runtime objektum**, opcionális cache JSON; később SQLite |
| **Mezők** | `chunk_id`, `document_id`, `text_hu`, `token_estimate`, `section_kind`, `confidence`, `review_status` |
| **Kapcsolatok** | document → passage |
| **Új/meglévő** | **Új** |
| **MVP** | **Kötelező** (in-memory spec) |

#### Passage links

| | |
|---|---|
| **Feladat** | Canonical ref ↔ entitás (hely, útvonal stop, később topic/person) |
| **Tárolás** | **Meglévő:** `passage_place_links.json`, route `passage_refs` |
| **Mezők** | `canonical_ref`, `entity_type`, `entity_id`, `link_type`, `source_id` |
| **Kapcsolatok** | place catalog, routes |
| **Új/meglévő** | **Meglévő adat** + **új** normalizáló adapter |
| **MVP** | **Kötelező** (adapter) |

#### Entities

| | |
|---|---|
| **Feladat** | Hely, személy, esemény — retrieval cél |
| **Tárolás** | Hely: **`biblical_places_catalog.json`**; személy: **nincs** |
| **Mezők** | `entity_id`, `entity_type`, `label_hu`, `external_ids[]` |
| **Kapcsolatok** | passage_links, enrichment |
| **Új/meglévő** | Hely **meglévő**; személy **új** (később) |
| **MVP** | Hely **kötelező**; személy **halasztott** |

#### External entity IDs

| | |
|---|---|
| **Feladat** | Pleiades, OpenBible, OSIS, Strong |
| **Tárolás** | Katalógus mezőkben (`pleiades_id`, `openbible_id`, `osis`) |
| **MVP** | **Kötelező** read path-on |

#### Topics

| | |
|---|---|
| **Feladat** | Tematikus retrieval (pl. „viz”, „imádat helye”) |
| **Tárolás** | Nincs — csak AI vagy hymn `_OCCASION_KEYWORDS` szint |
| **MVP** | **Halasztott** |

#### Import audit

| | |
|---|---|
| **Feladat** | Build/import nyomkövetés, integrity |
| **Tárolás** | **Meglévő:** `data/generated/*_audit.json`, `import_meta`, hymn checksum |
| **MVP** | **Kötelező** (manifest-be összefoglalva) |

#### Embeddings

| | |
|---|---|
| **Feladat** | Szemantikus retrieval |
| **Tárolás** | Nincs; pgvector nincs a repóban |
| **MVP** | **Halasztott** — MVP retrieval: **referencia + FTS + keyword** |

---

## 9. Integrációs boundary

### 9.1 Cél folyamat (későbbi fázis — most nem bekötve)

```text
passage (UI: last_igehely)
  → CanonicalReference.parse()
  → KB retrieval (chunks + entities + sources)
  → Evidence Packet (strukturált, token-budgetált)
  → generate_text() / meglévő Gemini provider
  → magyar markdown output
```

### 9.2 Legkisebb regressziós beillesztési pont

**[Tény]** Mindhárom szekció ugyanazon a útvonalon megy: `generate_section(key)` → `SECTION_PROMPTS[key].format(alap=build_alap_from_state(...))` → `generate_text()` (`app.py` ~4916–4940).

| Szekció | Session kulcs | Jelenlegi grounding | Javasolt bekötési pont | Mi marad változatlan |
|---|---|---|---|---|
| **Exegézis** | `exegesis` | `include_original_language_tokens=True` → `build_original_language_token_block()` | **`build_alap_from_state()` után**, `SECTION_PROMPTS.format()` **előtt**: opcionális `kb_evidence_block = kb_retrieval.build_packet(ref, section="exegesis")` append az `alap` stringhez | `generate_text`, `SECTION_PROMPTS` szöveg, grounding check |
| **Kortörténet** | `history` | `include_biblical_place_context=True` → `build_biblical_place_history_context()` | Ugyanaz a hook; KB packet **kiterjeszti** (nem helyettesíti) a helyszín blokkot | history prompt szerkezet |
| **Teológia** | `theology` | nincs KB blokk | Ugyanaz a hook; **`section="theology"`** szűrő: csak forrásolt, bizonyossági metadatával | teológia prompt |

**Konkrét függvény-szint (terv):**

```text
app.py :: generate_section(key)
  └─ [ÚJ, feature-flag mögött] kb_retrieval.maybe_build_evidence_packet(
         passage=st.session_state["last_igehely"],
         section_key=key,
     )
  └─ build_alap_from_state(...)  # változatlan
  └─ prompt = SECTION_PROMPTS[key].format(alap=alap + optional_packet)
  └─ generate_text(prompt, ...)  # változatlan
```

**Alternatíva (még kisebb diff):** `build_alap_from_state(include_kb_evidence: bool)` — de a §10 szerint a logika **`textus_kb/`** csomagban maradjon, `app.py` csak 1 sor flag-gate.

**Tilos ebben a fázisban:** `generate_text`, `SECTION_PROMPTS`, `ruf_bible_service`, meglévő repo-k módosítása.

---

## 10. Izoláció és feature flag

### 10.1 Package struktúra (terv)

```text
textus_kb/
  __init__.py
  canonical_reference.py    # §7 — parse/normalize/export
  manifest.py               # kb_manifest load/validate
  health.py                 # artifact + license health report
  retrieval.py              # passage → EvidencePacket (determinisztikus)
  evidence.py               # EvidencePacket, Chunk dataclasses
  adapters/
    places.py               # biblical_map_passages + enrichment
    tokens_greek.py           # delegál greek_token_repository
    tokens_hebrew.py          # delegál hebrew_token_repository
    ruf_local.py              # lookup_local (read-only)
  cli.py                    # python -m textus_kb.health (UI nélkül)
```

**Nem** a `bible_engine/` alá — hogy a KB ne keveredjen token parser belső részével; **`bible_engine` marad adatsziget**, `textus_kb` az integrátor.

### 10.2 Feature flag

| Flag | Hol | Alapértelmezés | Viselkedés |
|---|---|---|---|
| `TEXTUS_KB_ENABLED` | env | `0` | Ha off: `textus_kb` egyáltalán nem importálódik `app.py`-ból |
| `TEXTUS_KB_SHADOW_MODE` | env | `0` | Ha on: packet épül + naplózás/`st.session_state["_kb_shadow"]`, **de nem kerül a promptba** |
| `TEXTUS_KB_INJECT_SECTIONS` | env | `""` | Pl. `exegesis,history` — részletes rollout |

Streamlit secrets tükör: `st.secrets["textus_kb"]["enabled"]` — mint hymn/RÚF bootstrap.

### 10.3 Tesztelhetőség UI nélkül

```bash
python -m textus_kb.cli health --passage "Jn 4,1-42"
python -m textus_kb.cli retrieve --passage "Jn 4,1-42" --json
```

**Shadow mode összehasonlítás:** ugyanazon `last_igehely` mellett log: chunk count, token estimate, source IDs vs. jelenlegi `build_original_language_token_block` + `build_biblical_place_history_context` hossza — emberi diff, automata metrika.

---

## 11. Kockázati audit

| Kockázat | Szint | Indok | Mitigáció |
|---|---|---|---|
| **Canonical reference** | **HIGH** | 3+ párhuzamos könyvkód; JSON `JHN` vs UI `Jn`; nincs OSIS export | §7.8 `CanonicalReference` modul + könyv map tábla + mapping tesztek |
| **Versifikáció** | **HIGH** | Külső források eltérő vers számozása; RÚF egyetlen igazság | Chunkok **RÚF span-hoz** kötése; külső forrás `alignment_status`; emberi review flag |
| **Adatduplikáció** | **MEDIUM** | RÚF API + local DB; enrichment research vs published | Manifest `payload_ref`; research ≠ runtime; single purge path RÚF-hoz |
| **RÚF szerződés/licenc** | **HIGH** | Verbatim DB; export tiltás | KB chunk `allow_chunk_in_prompt` licenc check; RÚF csak lookup, **soha** chunk export fájlba; attribution kötelező |
| **Külső adatforrás licencek** | **MEDIUM** | CC BY STEPBible vs reference-only archaeology | `license_registry`; chunk szintű `reference_only` → paraphrase only |
| **SQLite / Supabase szétválás** | **MEDIUM** | Projects Supabase-en; KB artifact lokális | Hibrid modell (§8.1); ne mozgassuk RÚF-ot Supabase publikus DB-be |
| **Deploy méret** | **MEDIUM** | TAGNT/TAHOT tracked; hymn/ruf privát | Manifest + Supabase privát tükör; health degraded mode |
| **pgvector** | **LOW** (MVP) | Nincs infra | Halasztás; FTS/keyword/előszűrés referencia alapú |
| **Cache** | **MEDIUM** | Gemini session cache; KB packet ismétlődhet | Packet cache kulcs: `canonical_ref + section + manifest_version`; TTL |
| **Provider coupling** | **MEDIUM** | Evidence → `generate_text` prompt string | Evidence Packet **provider-független** dataclass; csak adapter alakít prompttá |
| **Import frissítés** | **MEDIUM** | 8654 place link OpenBible-ből | `source_version` + diff audit; canonical ref normalizálás importkor (későbbi) |
| **Tesztlefedettség** | **MEDIUM** | Nincs KB modul | §13; meglévő 198 teszt nem sérülhet |
| **Regressziós kockázat** | **HIGH** | `app.py` monolith; `build_alap_from_state` érzékeny | Feature flag default off; shadow mode; injekció **csak** új blokk append |

---

## 12. Jn 4,1–42 pilot (terv — nem implementált)

### 12.1 Cél

**MI nélkül** strukturált `EvidencePacket` JSON (CLI output), amely összekapcsolja a meglévő szigeteket egy NT narratíva perikópára.

### 12.2 Bemenet

| Mező | Érték |
|---|---|
| Canonical input | `Jn 4,1–42` → `CanonicalReference` |
| RÚF span | `JHN`, fejezet 4, verse 1–42 |

### 12.3 Pilot végállapot — kötelező mezők

```json
{
  "canonical_passage": {
    "display_hu": "Jn 4,1–42",
    "ruf_book_code": "JHN",
    "span": {"start": [4,1], "end": [4,42]},
    "osis": "John.4.1-John.4.42"
  },
  "original_language": {
    "language": "greek",
    "source_id": "stepbible_tagnt",
    "verses_covered": [1, 2, "..."]
  },
  "persons": [],
  "places": [],
  "topics": [],
  "source_excerpts": [],
  "provenance": [],
  "retrieval_score": 0.0,
  "token_estimate": 0
}
```

### 12.4 Meglévő adatforrások (pilot kitöltés)

| Kitöltés | Forrás | Fájl / függvény | Pilotnál várható |
|---|---|---|---|
| Görög tokenek | TAGNT | `load_greek_passage_tokens("Jn 4,1-42")` | **Igen** — 42 vers token |
| Magyar szöveg | RÚF local / API | `lookup_local("JHN", 4, 1, 42)` | **Feltételes** — DB presence |
| Helyek | OpenBible links | `passage_place_links.json` — `JHN 4,3`…`4,54`, `sychar`, `samaria_*` | **Igen** — több link; **`passage_refs_overlap("Jn 4,1-42", link)`** |
| Enrichment prose | Pilot overlay | `place_enrichments.json` | **Nem** — Sychar nincs a 20 pilotban |
| Katalógus shell | Places | `biblical_places_catalog.json` → `sychar` | **Igen** — `card_summary_hu`, koordináta |
| Személyek | — | nincs entity DB | **Üres** — pilot jelzi hiányt |
| Témák | — | nincs topic index | **Üres** vagy keyword `["viz", "samaria"]` stub |
| Forrásrészletek | Enrichment / lexikon | szűrt section szövegek | **Minimális** — csak katalógus + token sorok |
| License | Registry | STEPBible CC BY; OpenBible CC BY; RÚF contractual | **Igen** — provenance blokk |
| Retrieval score | Heurisztika | overlap count + token coverage + enrichment presence | **Számított** — determinisztikus formula |
| Token estimate | Szöveghossz | ~chars/4 összes chunk | **Számított** |

### 12.5 Később importálandó (pilothoz nem szükséges, de jelzi a rést)

- Személy-entitás lista (Wikidata / saját curation);
- Sychar `source_backed` enrichment (research pipeline);
- Kommentár chunkok (licenc audit után);
- Topic taxonomy.

### 12.6 Pilot acceptance (audit szint)

- CLI: `python -m textus_kb.cli retrieve --passage "Jn 4,1-42"` → valid JSON, `canonical_passage.osis` kitöltve, `original_language.verses_covered` nem üres, `places` ≥ 1, `token_estimate` > 0.
- **Nincs** `app.py` import, **nincs** Gemini hívás.

---

## 13. Tesztstratégia

**Alapelv:** a meglévő **198 zöld** KB-kapcsolódó teszt ([Tény] §Függelék A) **minden fázisban zöld marad**; új tesztek külön `tests/test_textus_kb/` alatt.

| Kategória | Mit fed | Példa fájl / eset |
|---|---|---|
| **Unit** | `CanonicalReference.parse/export` | `Jn 4,1–42` → `JHN`; OSIS export |
| **Reference mapping** | RÚF↔TAGNT↔OSIS | `1Jn 4,7` vs `1Jn`; `JHN 4,5` JSON link |
| **Schema / integrity** | `kb_manifest.json` | kötelező artifact mezők; checksum formátum |
| **Importer validation** | Manifest generátor | hiányzó `tbesg` → degraded, nem fail |
| **Retrieval fixture** | Jn 4 pilot | golden JSON: `tests/fixtures/kb/jn_4_1_42_packet.json` |
| **Source provenance** | Minden chunk licenc | RÚF chunk `allow_chunk_in_prompt=false` → kizárva |
| **Token budget** | Packet max méret | pl. 4000 token plafon — csonkítás szabály |
| **Regression** | `build_alap_from_state` | flag off → byte-identical prompt alap (mock session) |
| **Shadow mode** | Packet épül, prompt nem változik | flag shadow → alap string unchanged assert |
| **Health CLI** | `textus_kb.cli health` | exit 0/1; JSON report schema |

**CI javaslat:** `pytest tests/test_textus_kb/ tests/test_hymn_* ...` (meglévő subset) — KB tesztek **nem** igényelnek hálózatot / Gemini-t / Supabase-t (fixture DB-k).

---

## 14. Fázisokra bontott repo-specifikus roadmap

### Fázis 0 — Audit (kész)

| | |
|---|---|
| **Cél** | Inventár + §7–15 dokumentáció |
| **Komponensek** | csak `docs/` |
| **Tilos** | production kód |
| **Tesztek** | meglévő 198 pass (baseline) |
| **Acceptance** | ez a dokumentum |
| **Rollback** | doc törlése |

### Fázis 1 — KB Core Foundation (`textus_kb` + manifest + canonical ref)

| | |
|---|---|
| **Cél** | Izolált csomag; artifact health; canonical reference |
| **Érintett** | **Új:** `textus_kb/*`, `data/kb/kb_manifest.json`, `tests/test_textus_kb/` |
| **Tilos módosítani** | `app.py`, `bible_engine/*` repo-k, Supabase séma, `requirements.txt` (kezdetben) |
| **Tesztek** | canonical mapping; manifest parse; health CLI |
| **Acceptance** | CLI health + Jn 4 retrieve JSON (determinisztikus); flag nélkül app viselkedés változatlan |
| **Rollback** | `textus_kb/` törlése; manifest törlése |

### Fázis 2 — Retrieval + Evidence Packet (Jn 4 pilot teljes)

| | |
|---|---|
| **Cél** | `retrieval.py` összerakja a packetet meglévő adapterekből |
| **Érintett** | `textus_kb/retrieval.py`, `adapters/*`, fixtures |
| **Tilos** | `app.py` bekötés |
| **Tesztek** | golden fixture; token budget; provenance |
| **Acceptance** | §12.6 CLI acceptance |
| **Rollback** | Fázis 1 állapot |

### Fázis 3 — Shadow mode integráció

| | |
|---|---|
| **Cél** | `app.py` minimal gate: log shadow packet exegesis/history/theology |
| **Érintett** | `app.py` (~5–15 sor), `textus_kb` |
| **Tilos** | prompt módosítás default alatt |
| **Tesztek** | regression: flag off; shadow: prompt unchanged |
| **Acceptance** | streamlit fut; shadow log látható dev módban |
| **Rollback** | flag off + app diff revert |

### Fázis 4 — Prompt injekció (szekciónkénti rollout)

| | |
|---|---|
| **Cél** | Evidence Packet append exegesis → history → theology |
| **Érintett** | `app.py` `generate_section`, `textus_kb` |
| **Tilos** | `generate_text` belső szerződés |
| **Tesztek** | prompt snapshot tesztek; grounding warnings nem nőnek rossz irányba |
| **Acceptance** | emberi review 3 szekcióra; token plafon betartva |
| **Rollback** | `TEXTUS_KB_INJECT_SECTIONS=""` |

### Fázis 5 — Passage search existence + manifest CI

| | |
|---|---|
| **Cél** | `passage_search_ai` → `lookup_local` filter; CI manifest checksum |
| **Érintett** | `passage_search_ai.py`, CI script |
| **Acceptance** | nem létező vers kiszűrve; CI zöld |
| **Rollback** | filter feature flag |

### Fázis 6 — Meta SQLite + topic/entity bővítés (opcionális)

| | |
|---|---|
| **Cél** | `kb_core.sqlite3` chunk index; személy entitás |
| **Halasztott** | pgvector, Supabase chunk sync |

---

## 15. RECOMMENDED NEXT IMPLEMENTATION PHASE

### Javasolt egyetlen következő munkacsomag: **Fázis 1 — KB Core Foundation**

**Csomag tartalma (egy PR-ben):**

1. `textus_kb/canonical_reference.py` — §7.8 delegáló modell  
2. `textus_kb/manifest.py` + `data/kb/kb_manifest.json` — artifact + license + version registry  
3. `textus_kb/health.py` + `textus_kb/cli.py` — UI nélküli health/retrieve előkészítés  
4. `tests/test_textus_kb/` — mapping + manifest + health tesztek  

**Miért ez legyen az első?**

1. **Canonical reference HIGH kockázat** (§11) — KB retrieval, passage links és külső OSIS **join nélkül** minden további réteg hibás kapcsolódást épít.  
2. **`kb_manifest` önmagában nem elég** — látja a hiányzó `tbesg` fájlt, de **nem oldja meg** a `JHN` vs `Jn` vs `John.4.5` szétszórást, ami a pilot és az Evidence Packet előfeltétele.  
3. **Együtt mégis egy koherens „foundation” PR:** a manifest **`canonical_book_codes`** szekciót hordoz (66 sor map); a health report **`CanonicalReference`-t használ** a teszt-passage ellenőrzéshez (`Jn 4,1-42`: TAGNT elérhető-e, hány place link overlap).  
4. **Minimális regresszió:** új csomag + JSON manifest; **`app.py` érintetlen**; feature flag még nincs bekötve.  
5. **Megelőzi** a Fázis 2 Jn 4 pilotot és Fázis 3 shadow integrációt — tiszta dependency sorrend.

**Milyen problémát old meg?**

- Egységes belső referencia-kulcs a szigetek között.  
- Látható artifact/ licenc állapot (degraded clone, hiányzó hymn/ruf/tbesg).  
- Tesztelhető alap UI és Gemini nélkül.

**Érintett fájlok (újak):**

| Fájl | Szerep |
|---|---|
| `textus_kb/__init__.py` | package export |
| `textus_kb/canonical_reference.py` | §7.8 |
| `textus_kb/manifest.py` | manifest load/validate/generate helper |
| `textus_kb/health.py` | artifact + mapping health |
| `textus_kb/evidence.py` | dataclass stub (Packet váz) |
| `textus_kb/cli.py` | `health`, később `retrieve` |
| `data/kb/kb_manifest.json` | generált/ kézi manifest |
| `tests/test_textus_kb/test_canonical_reference.py` | mapping |
| `tests/test_textus_kb/test_manifest.py` | schema |
| `tests/test_textus_kb/test_health.py` | CLI |

**Nem érinti:** `app.py`, `bible_engine/*`, `requirements.txt` (stdlib + meglévő pytest elég az 1. fázishoz).

**Tesztek:**

- ≥ 25 új unit teszt mappingre (66 könyv spot check + Jn 4 + 1Jn + OT negatív TAGNT);  
- manifest schema validation;  
- health CLI exit code ha TAGNT tracked artifact hiányzik (tmp path);  
- **regression:** teljes meglévő 198-as KB subset zöld.

**Definition of Done:**

1. `python -m textus_kb.cli health` fut és JSON-t ad (artifact státuszok + licenc figyelmeztetések).  
2. `CanonicalReference.parse("Jn 4,1–42")` stabil `ruf_book_code`, `osis`, `tagnt_book`.  
3. `kb_manifest.json` verziózott; minden ismert artifact listázva checksum-mal vagy `missing_reason`-nel.  
4. Nincs `app.py` diff.  
5. Meglévő 198 KB-kapcsolódó teszt zöld + új `test_textus_kb` zöld.

**Előfeltételek:**

- `feature/knowledge-base-core` ág;  
- tracked `tagnt_nt.sqlite3` / `tahot_ot_runtime.sqlite3` (health ellenőrzéshez);  
- audit §7–15 jóváhagyva (ez a dokumentum).

**Miért nem csak `kb_manifest` külön?** A manifest alone **nem ad canonical join kulcsot**; a canonical ref alone **nem ad deploy health-et**. A Fázis 1 **szándékosan egyesíti** a kettőt egy izolált csomagban — de a **implementációs sorrend** a csomagon belül: (a) book map + `CanonicalReference`, (b) manifest schema, (c) health CLI, mert a health **`parse()`-t használja** a pilot passage ellenőrzésére.

---

## Függelék A — Korábbi audit szekciók (statisztika, build, licenc összefoglaló)

### A.1 Build / import scriptek (KB-előállítás)

**Adatbázis-builderek:**

| Script | Kimenet |
|---|---|
| `scripts/build_tagnt_nt_db.py` | `tagnt_nt.sqlite3` |
| `scripts/build_tbesg_lexicon_db.py` | `tbesg_lexicon.sqlite3` |
| `scripts/build_hebrew_prototype_db.py` | TAHOT + TBESH runtime |
| `scripts/build_ruf_bible_db.py` | `ruf_bible.sqlite3` |
| `scripts/build_hymn_database.py` | `hymns.sqlite3` |

**Lexikon workflow:** `export_*_lexicon_batch.py`, `import_hungarian_lexicon_batch.py`, `import_hebrew_lexicon_batch.py`, `audit_nt_lexicon_coverage.py`, `audit_hebrew_lexicon_hu.py`.

**Helyszín / útvonal:** `scripts/import_biblical_places.py`, `build_biblical_places_catalog.py`, `build_place_enrichment_*.py`, `build_*_routes.py`, csomag: `biblical_map_import/`.

**[Következtetés]** Erős **offline-first** toolchain van; a központi build orchestration a **Fázis 1 manifest** feladata (§15).

### A.2 Pontos adatstatisztika (2026-08-23, helyi)


| Mutató | Érték | Forrás |
|---|---:|---|
| TAGNT tokenek | 142 096 | `nt_lexicon_coverage_report.json` |
| TAGNT egyedi Strong | 5 580 | u.o. |
| Magyar lexikon token lefedettség (effektív) | **99,98%** | u.o. |
| Bibliai helyszín | **1 267** | `biblical_places_catalog.json` |
| Igehely–hely link | **8 654** | `passage_place_links.json` |
| Publikált helyszín-enrichment | **20** | `place_enrichments.json` |
| Bibliai útvonal | **23** | `biblical_routes.json` |
| ERE ének (várható) | 513 | `hymn_repository.py` invariant |
| RE21 ének (várható) | 667 | u.o. |
| RE48 ének (várható) | 512 | u.o. |

**Ne keverendő rétegek** (a térképes auditból is ismert, KB-szinten is érvényes):

1. **Katalógus rekord** ≠ **mély, forrásolt profil**
2. **Research evidence** (`enrichment_research/*`) ≠ **publikált enrichment** (20)
3. **Publikált `source_backed` címke** ≠ **szigorú research DoD** (0 source_backed_profile_ready a 50-es batchre — lásd `docs/biblical_map_status_audit.md`)

### A.3 Licenc- és jogi rétegek (összefoglaló)


| Eszköz | Licenc / feltétel | Hol dokumentált |
|---|---|---|
| TEXTUS alkalmazáskód | MIT | `LICENSE`, `README.md` |
| STEPBible (TAGNT/TAHOT/TBESG/TBESH) | **CC BY 4.0** — STEPBible.org attribution | `docs/hebrew_ot_architecture_audit.md`, UI forrásjegyzetek |
| RÚF 2014 | **Szerződéses** — belső, verbatim, purge-olható | `ruf_bible_local_db.py`, `ruf_bible_service.py` |
| OpenBible | CC BY 4.0 | `data/biblical_places/sources.json` |
| Pleiades | CC BY 3.0 | `sources.json` |
| Régészeti intézményi források | reference-only / paraphrase | `place_enrichment_sources.json` |
| Énekkönyv források (DTX/DOCX) | **nincs kódolt licenc a repóban** | `data/raw/hymnals/` gitignored |
| Gemini / Google Search | külső ToS | `app.py` actualization |

**[Következtetés]** Részletezve §8 License registry és §11 kockázati táblában.

### A.4 Korábbi integrációs hiányok listája (2026-08-23)


| # | Hiány | Hatás | KB-core irány |
|---|---|---|---|
| 1 | Nincs központi KB modul / API | szigetelt adat, duplikált bootstrap | `KnowledgeBaseRegistry` vagy hasonló olvasási facade |
| 2 | Nincs verziózott manifest | checksum drift, nehéz deploy | `kb_manifest.json` + build hash |
| 3 | `tbesg_lexicon.sqlite3` nincs gitben | görög lexikon UI build nélkül hal el | manifest + CI artifact / Supabase tükör mint hymns |
| 4 | `hymns.sqlite3` / `ruf_bible.sqlite3` privát | friss clone degraded mode | dokumentált bootstrap UX + health check |
| 5 | Passage search nincs RÚF existence check | nem létező vers javasolható | `lookup_local()` integráció |
| 6 | TAGNT=NT, TAHOT=OT — rés coverage | grounding check UNKNOWN kategória | cross-testament policy dokumentálva |
| 7 | Magyar lexikon overlay részleges | angol fallback UI-ban | translation workflow folytatása |
| 8 | Place research ≠ runtime enrichment | 50 research hely nem él az AI-ban | publish pipeline research → enrichment |
| 9 | Supabase RLS nincs a repóban | app-layer `owner_sub` only | infra audit külön |
| 10 | Héber OT UI nincs teljesen bekötve | görög-first élmény | UI integráció külön feature |

*(A fenti lista a Phase 0 állapotot rögzíti; frissített integrációs terv: §9, §14.)*

### A.5 Baseline tesztlefedettség (2026-08-23)


**Futtatott parancs (2026-08-23, lokális):**

```text
python -m pytest tests/test_hymn_recommendation_ai.py tests/test_hymn_repository.py
  tests/test_hymn_sqlite.py tests/test_concordance_ui.py tests/test_concept_concordance.py
  tests/test_original_language_concordance.py tests/test_passage_search.py
  tests/test_greek_token_repository.py tests/test_hebrew_repositories.py
  tests/test_biblical_place_enrichment.py -q --tb=no
→ 198 passed in ~49s
```

**Jól fedett:** hymn grounded flow, konkordancia módok, passage search szerződés, görög/héber repo, enrichment loader.

**Gyengén fedett / hiányzik KB-szinten:** központi registry, cross-modul bootstrap, unified health endpoint, RÚF existence a passage searchben, KB manifest validáció. *(Friss tesztstratégia: §13.)*

### A.6 Korábbi készültségi becslés (Phase 0 zárás)


### A. Inventár + audit (Phase 0)

| Feltétel | Állapot |
|---|---|
| Központi KB audit dokumentum §1–15 | **Teljesült** (2026-08-23 bővítés) |
| Sziget-leltár + grounding térkép | **Teljesült** |
| Canonical reference audit | **Teljesült** (§7) |
| KB Core adatmodell terv | **Teljesült** (§8) |
| Production kód módosítás | **Nincs** (szándékos) |


### B. KB-core MVP (következő implementációs fázis — nem ebben a commitban)

**Javasolt DoD:**

1. `kb_manifest` — verzió, checksum, elérhetőség státusz minden adatszigethez.
2. Egységes `ensure_kb_artifacts()` bootstrap (hymn/RÚF/TBESG mintájára).
3. Read-only facade: `get_passage_tokens()`, `lookup_lexicon()`, `search_hymns()`, `get_place_context()` — a meglévő repo-k delegálása.
4. Health/diagnostic panel vagy CLI: mely artifact hiányzik, mely licenc érintett.
5. Tesztek: manifest parse, degraded mode, nincs cross-sziget írás runtime-ban.

| Feltétel | Állapot |
|---|---|
| 1–5 | **Hiányzik** |

### C. Integrált éles KB

**DoD:** AI modulok task_id-n keresztül KB-facade-t használnak; research→publish pipeline; CI build + privát artifact; RLS/infra; monitoring.

**Állapot:** **Hiányzik**

### Százalékos becslés

| Tengely | Inventár (A) | KB-core MVP (B) | Integrált (C) |
|---|---:|---:|---:|
| Adat mennyisége | **85%** | 85% | 70% |
| Adat minőség / forrás | **40%** | 45% | 60% |
| Repository minták | **75%** | 80% | 90% |
| Központi integráció | **5%** | 35% | 75% |
| AI grounding lefedettség | **35%** | 50% | 70% |
| Dokumentáció | **70%** (ez az audit után) | 80% | 90% |

**[Következtetés]**

- **Phase 0 audit: teljes** (§1–15 + függelék).
- **KB-core MVP implementáció: ~0%** — következő lépés §15.
- **Integrált éles KB: ~10%**.

---

## Audit záradék

**Phase 0 (2026-08-23):** ez a jelentés kizárólag `docs/textus_knowledge_base_audit.md` létrehozását / bővítését célozza. A záró `git status` csak ezt a dokumentumot mutassa módosításként; production kód, adatbázis-séma, dependency, konfiguráció és tesztkód érintetlen marad.

