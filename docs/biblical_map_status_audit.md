# Bibliai térképes modul — készültségi audit

**Audit dátuma:** 2026-07-30  
**Repository gyökér:** `C:/Users/Hover/Textus-smart-map`  
**Ág:** `feature/biblical-smart-map`  
**Jelleg:** teljesen módosítás nélküli readiness audit (csak ez a fájl jött létre/íródott).  
**Megjegyzés:** A `docs/textus_knowledge_base_audit.md` a vizsgált munkaterületen **nem található**; a térképes állítások közvetlenül kódból és adatból lettek ellenőrizve.

Jelölések ebben a jelentésben:

- **[Tény]** — fájlúttal, függvénynévvel, teszttel vagy számlálással igazolt.
- **[Következtetés]** — tényekből levont, de nem közvetlenül mért állítás.
- **[Feltételezés / UI-ellenőrzés]** — kód alapján valószínű, de emberi Streamlit-futás nélkül nem bizonyított.

---

## 1. Git-állapot

| Tétel | Érték | Bizonyíték |
|---|---|---|
| Gyökér | `C:/Users/Hover/Textus-smart-map` | `git rev-parse --show-toplevel` |
| Aktuális ág | `feature/biblical-smart-map` | `git branch --show-current` |
| Remote | `origin` → `https://github.com/hoverzs/Textus.git` | `git remote -v` |
| Tracking | `origin/feature/biblical-smart-map` | `git status -sb` |
| Ahead / behind | **ahead 38**, behind 0 | `git rev-list --left-right --count origin/feature/biblical-smart-map...HEAD` → `0 38` |
| HEAD | `8655650` — `data: audit first biblical place research evidence` | `git log -1` |

### Pusholatlan térképes commitok (38, a remote ághoz képest)

A teljes 38 commit a feature ágon van; a térképes munka gerince ezek között van, többek között:

- katalógus / HU review / duplicate review (`5e9cb8c` … `c90cfb5`, `50d418a`);
- útvonalmodell és Pál / pátriárka / exodus / Józsué útvonalak (`b3d9436` … `d80d015`);
- layout / route UI (`2f64408`, `77da8b6`, `a2616d7`, `1763aeb`);
- enrichment framework + 20 helyes pilot (`e07a1df` … `7edcf66`);
- kutatási workflow + szigorú evidence audit (`ae3d019`, `4dc1e9d`, `0c844c3`, `8655650`).

**[Tény]** A feature ág **nincs szinkronban** a remote-tal; push nélkül main/merge nem aktuális.

### Commitolatlan / nem követett fájlok

| Fájl | Állapot | Valószínű előzmény |
|---|---|---|
| `bible_text_ui.py` | módosított (−1 sor: `persist_state="session"` eltávolítva) | Streamlit inkompatibilis arg miatti hibajavítás a térképes integráció idején |
| `data/biblical_places/duplicate_review_batch_001.json` … `_004.json` | untracked | Nyers duplicate-review batch fájlok; a repo már tartalmazza a `*_reviewed.json` változatokat és az alkalmazott merge-eket |

**[Tény]** Ezeket az audit **nem** módosította és **nem** stage-elte.  
**[Következtetés]** A `bible_text_ui.py` diff nem térképlogika, de a workshop igehely-szerkesztőjét érinti; külön review kell commit előtt. A négy untracked duplicate batch valószínűleg elavult / párhuzamos a reviewed fájlokkal.

---

## 2. Térképes komponensek leltára

### Futó alkalmazásba kötött (aktív)

| Komponens | Szerep | Aktív? |
|---|---|---|
| `app.py` → `render_current_biblical_map_prototype()` (~6897) + hívás `render_igehely_panel()` végén (~7010) | Bekötés a Textusműhely igehely paneljébe | **Igen** |
| `biblical_map_ui.py` | Helyszínek / útvonalak UI, kereső, kártya, enrichment megjelenítés | **Igen** |
| `biblical_map_data.py` | Katalógus + `sources.json` betöltés; `BIBLICAL_MAP_PLACES` (1267) | **Igen** |
| `biblical_map_passages.py` | Passage→place auto-választás | **Igen** |
| `biblical_routes.py` | Útvonal JSON betöltés / validáció | **Igen** |
| `biblical_place_enrichment.py` | 20 pilot enrichment overlay a helykártyán | **Igen** (UI hívja: `get_place_enrichment`) |
| `data/biblical_places/biblical_places_catalog.json` | Canonical helyszínkatalógus | **Igen** |
| `data/biblical_places/sources.json` | Térképi forrásregiszter (16) | **Igen** |
| `data/biblical_places/passage_place_links.json` | Igehely–helyszín kapcsolatok (8654) | **Igen** |
| `data/biblical_routes/biblical_routes.json` | 12 útvonal | **Igen** |
| `data/biblical_places/place_enrichments.json` | 20 enrichment profil | **Igen** (overlay) |
| `data/biblical_places/place_enrichment_sources.json` | Enrichment forrásregiszter (19) | **Igen** (overlay) |

### Import / pipeline / review (előállító, nem UI-runtime)

| Komponens | Szerep | Aktív runtime? |
|---|---|---|
| `biblical_map_import/` (`pipeline.py`, `openbible_loader.py`, `pleiades_loader.py`, `merge.py`, `pilot_catalog.py`) | OpenBible/Pleiades import, merge, lock | Nem közvetlenül; scriptből |
| `scripts/import_biblical_places.py`, `scripts/build_biblical_places_catalog.py`, `scripts/audit_biblical_places.py` | Katalógusépítés / audit | Script |
| `scripts/build_place_enrichment_*.py`, `scripts/build_place_enrichment_research.py` | Enrichment batch + kutatási evidence builder | Script |
| `scripts/apply_biblical_places_duplicate_review.py` | Duplicate merge alkalmazás | Script |
| HU review batch JSON-ok (`hungarian_review_batch_00*.json`) | Magyar név/review queue | Előállító / auditált |
| Duplicate review `*_reviewed.json` + `duplicate_place_merges.json` | Merge döntések | Előállító |
| `data/biblical_places/enrichment_research/*` | Evidence packet, readiness, acquisition queue | Kutatási réteg; **nem** Streamlit runtime forrás |
| `data/biblical_places/manual_locks.json` | Corinth/Ephesus védelem | Importkor aktív |
| `data/biblical_places/place_profile_groups.json` | Profilcsoport / needs_review csoportok | Enrichment/research |
| Route validation report JSON-ok | Pauline / exodus / joshua jelentések | Dokumentáló |

### Tesztek és docs

| Terület | Fájlok |
|---|---|
| UI / passage / layout / routes UI | `tests/test_biblical_map_ui.py` (106 teszt) |
| Route modell | `tests/test_biblical_routes.py` (33) |
| Import / audit / HU / duplicate | `test_biblical_place_import.py`, `test_biblical_places_audit.py`, `test_biblical_places_hu_review_queue.py`, `test_biblical_places_duplicate_review_*.py` |
| Enrichment | `test_biblical_place_enrichment.py`, `test_place_enrichment_batch.py`, `test_enrichment_simplify.py`, `test_place_enrichment_research.py` |
| Docs | `docs/biblical_map_data_model.md`, `docs/biblical_place_import.md`, `docs/biblical_places_*.md`, `docs/place_enrichment_*.md`, `docs/biblical_routes.md` (ha jelen), ez az audit |

---

## 3. Adatfeldolgozási folyamat

```text
OpenBible / Pleiades / kézi lock
  → raw (import cache / GitHub adat; részben gitignored)
  → biblical_map_import pipeline + build_biblical_places_catalog
  → dedupe (duplicate review apply)
  → biblical_places_catalog.json
  → HU review batch-ek (név, card_summary)
  → passage_place_links.json (+ passage catalog)
  → place_enrichments.json (20 pilot) + enrichment_sources
  → enrichment_research evidence packets / readiness (50-ös batch)
  → biblical_map_ui / biblical_routes Streamlit megjelenítés
```

| Lépés | Hol | Automatizáltság | Állapot | Idempotens? | Kockázat |
|---|---|---|---|---|---|
| Külső forrás betöltés | `openbible_loader`, `pleiades_loader` | Félautomata (script) | Működő a teljes katalógushoz | Igen (dry-run/tesztelt) | Hiányzó koordináta → skip (33) |
| Normalizálás | `merge.py`, catalog builder | Automata | Működő | Igen | Mezőütközés lock nélkül |
| Deduplikálás | duplicate review queue/apply | Kézi döntés + automata apply | Részleges (161 uncertain audit szerint) | Apply száraz futás biztonságos | Téves merge |
| Katalógus | `biblical_places_catalog.json` | Automata kimenet | Működő (1267) | Audit hash idempotens | Shell rekordok többsége |
| Magyar név | HU review batch-ek | Kézi/szerkesztői + apply | Nagy lefedettség (1267 `name_hu`) | Batch apply | 203 HU review finding maradt az auditban |
| Igehelykapcsolat | `passage_place_links.json` | Automata OpenBible alapú | Működő (8654) | Igen | Nagy listák egy igerészhez (118 finding) |
| Enrichment próza | `place_enrichments.json` | Kézi/szerkesztett pilot | **20 hely** | Loader validál | Többségnél nincs profil |
| Evidence / readiness | `enrichment_research/` | Automata builder | Működő, szigorú | Igen (`cache_version` 2) | Nem írja a publikált enrichments-t |
| Streamlit UI | `biblical_map_ui.py` | Runtime | Bekötött | n/a | Vizuális regresszió |

**[Tény]** A kutatási evidence réteg és a publikált `place_enrichments.json` **diszjunkt**: 0 közös `place_id` a 50-ös research batch és a 20 enrichment pilot között.

---

## 4. Pontos adatstatisztika

Forrás, ha nincs külön jelezve: `data/biblical_places/biblical_places_catalog.json` + kapcsolódó JSON-ok, 2026-07-30 helyi számlálás.

| Mutató | Érték | Forrás / logika |
|---|---:|---|
| Egyedi helyszín | **1267** | `len(catalog)`; `place_id` egyedi |
| Importált (OpenBible sikeres) | **1309** | `full_catalog_import_report.json` → `imported_place_count` |
| Skipelt import | **33** | hiányzó/rossz koordináta |
| Merge utáni katalógus | **1267** | `merged_catalog_count`; 39 merge (`duplicate_place_merges.json`) |
| Kézi / lockolt pilot | **2** lock (`corinth`, `ephesus`) + **10** manual override a full import reportban | `manual_locks.json`, import report |
| `is_primary_demo_place` | **1** | katalógus mező |
| `needs_review` | **1** | `review_status == needs_review` |
| `reviewed` | **39** | `review_status` |
| `draft` | **1227** | `review_status` |
| Koordinátával | **1267 / 1267** | `latitude`+`longitude` |
| Magyar `name_hu` | **1267 / 1267** | nem üres string |
| `ancient_names` lista nem üres | **1267** | lista mező |
| `original_names` nem üres | **6** | szigorúbb „eredeti név” mező |
| `modern_name` | **1267** | |
| `pleiades_id` | **124** | |
| Igehelykapcsolattal bíró hely | **1212** | distinct `place_id` a links fájlban |
| Egyedi igehely–helyszín pár | **8654** | `passage_place_links.json` sorok |
| Katalógus `history_hu` / `archaeology_hu` / `biblical_significance_hu` kitöltve | **2 / 2 / 2** | főleg Corinth/Ephesus shell mezők |
| Publikált enrichment profil | **20** | `place_enrichments.json` |
| Enrichment: historical_context szöveg | **2** | Corinth, Ephesus |
| Enrichment: archaeology szöveg | **2** | Corinth, Ephesus |
| Enrichment: modern_context / biblical_significance / identification_notes | **20 / 20 / 20** | |
| Enrichment profil HTTP forrással | **20 / 20** | `place_enrichment_sources.json` `identifier` |
| Katalógus hely HTTP forrással (`sources.json` `source_url`) | **1267 / 1267** | legalább OpenBible URL |
| `biblical_draft_ready` | **50** | `batch_001_biblical_draft_ready.json` |
| `partial_profile_ready` | **6** | egypt, tyre, zion, mount_zion, judea_1, edom |
| `source_backed_profile_ready` (szigorú research) | **0** | `batch_001_source_backed_ready.json` |
| `featured_candidate` (szigorú research) | **0** | |
| Publikált enrichment `overall_review_status=source_backed` | **20** | **lazább** publikált státusz, nem a research DoD |
| Publikált `profile_tier=featured` | **2** | corinth, ephesus |
| Evidence item (research) | **514** | A312 + B185 + C4 + E13 |
| Nyitott acquisition task | **92** | mind `status=open` |
| Útvonal | **12** | `biblical_routes.json` |
| Útvonalállomás | **193** | stops összege |
| Szegmens | ~175 | route-onként stops−1 jellegű, plusz branch |
| Teljes / hiányos útvonal | Mind **12 draft + schematic**; 1 textual-only stop az exodus úton; certainty többnyire `mixed` (Pál első: `certain`) | route mezők |
| Bizonytalan duplicate (audit) | **161** | `audit_report.json` `uncertain_duplicate_count` |
| Audit `review_required_count` | **1042** | findings |

**Ne keverendő rétegek:**

1. **Katalógus rekord** (1267) ≠ **kész történeti profil**.  
2. **Research evidence** (50 hely, 514 item) ≠ **publikált enrichment** (20 hely).  
3. **Publikált `source_backed` címke** (20) ≠ **szigorú `source_backed_profile_ready`** (0).

---

## 5. Funkcionális állapot

### Bekötés

**[Tény]** `app.py` importálja és az igehely panelben, az áttekintés gomb után rendereli a térképet (`render_current_biblical_map_prototype`).  
**[Tény]** Teszt: `test_map_call_is_in_igehely_panel_after_overview_button`, `test_exactly_one_active_ui_map_render_call`.

### Helyszínek nézet — logika

| Funkció | Állapot | Bizonyíték |
|---|---|---|
| Aktuális igerész helyszínei | **Igazolt logika** | `passage_linked_places`; ApCsel 18,1–18 → 9 hely (corinth első); tesztek |
| Egy hely auto-select | **Igazolt** | `apply_passage_place_selection` + UI tesztek |
| Több hely választó | **Igazolt** | ApCsel 16 / 18 selectbox tesztek |
| Ismeretlen igehely | **Igazolt** | Jn 3,16 → 0 hely; no arbitrary pick tesztek |
| Katalóguskereső + ékezet | **Igazolt** | `search_biblical_places('efézus')` → ephesus; accent tesztek |
| Forrás dedupe | **Igazolt** | `dedupe_sources` + UI tesztek |
| Teljes szélességű térkép | **Kód + fake-st teszt** | nincs `st.columns` a map layoutban; `use_container_width=True`, `height=520`; **emberi UI-ellenőrzést igényel** a tényleges böngészőben |
| Helyszínkártya + expander | **Igazolt render** fake Streamlit-tel | Corinth/Ephesus detail tesztek |
| Enrichment overlay | **Kódigazolt** | `_render_place_enrichment`; csak a 20 pilotnál látszik tartalom |

### Útvonalak nézet

| Funkció | Állapot | Bizonyíték |
|---|---|---|
| 12 útvonal betöltés | **Igazolt** | `load_biblical_routes`, selector teszt |
| Pál első út | **Igazolt** | 15 stop; render teszt |
| ApCsel 13 → route match | **Igazolt** | `route_matches_for_passage` → `paul_first_missionary_journey` |
| Állomáslista / fázis / family nav | **Igazolt** | számos UI + routes teszt |
| Pydeck / st.map fallback | **Kód + hibatűrés teszt** | vizuális minőség: **UI-ellenőrzés** |

### Forgatókönyv-ellenőrzés (logika, 2026-07-30)

| Eset | Eredmény |
|---|---|
| ApCsel 18,1–18 | 9 linked place; corinth az élen |
| ApCsel 13 | 15 place + route match Pál első útra |
| Pál első missziói út | 15 stop, betöltődik |
| Korinthus / Efézus | kereső talál; enrichment featured profil |
| Jn 3,16 | 0 place link |
| Több helyszínes szakasz | ApCsel 18 / 13 igazolt |

**[Feltételezés / UI-ellenőrzés]** A helyi Streamlit (`localhost`) vizuális megjelenése, pydeck stílusa és a teljes szélesség böngészőben nem lett ebben az auditban képernyőn ellenőrizve.

---

## 6. Tesztek

### Futtatott parancsok (lokális, hálózat nélküli)

```text
python -m pytest tests/test_biblical_map_ui.py tests/test_biblical_routes.py
  tests/test_biblical_place_import.py tests/test_biblical_places_audit.py
  tests/test_biblical_place_enrichment.py tests/test_place_enrichment_research.py
  tests/test_place_enrichment_batch.py tests/test_enrichment_simplify.py
  tests/test_biblical_places_hu_review_queue.py
  tests/test_biblical_places_duplicate_review_queue.py
  tests/test_biblical_places_duplicate_review_apply.py -q --tb=no
→ 223 passed, 3 failed (42.83s)

python -m pytest tests/test_biblical_places_audit.py -q --tb=line
→ 3 failed, 2 passed

python -m pytest tests/test_biblical_map_ui.py tests/test_biblical_routes.py
  tests/test_place_enrichment_research.py -q --tb=no
→ 151 passed (21.30s)
```

### Hibás tesztek (3) — stale elvárások

Mind `tests/test_biblical_places_audit.py`:

1. `imported_place_count` (1309) vs jelenlegi `len(catalog)` (1267) egyenlőség — a merge utáni katalógus kisebb; a teszt elavult.
2. `uncertain_duplicate_count` 201 vs jelenlegi 161.
3. Elvárja a `missing_hungarian_name` finding típust, ami a HU review után eltűnt.

**[Következtetés]** Nem funkcionális regresszió a térkép UI-ban, hanem audit-jelentés / teszt szinkronhiány.

### Korábbi „42 / 45 / 65 / 12” sikerszámok

| Korábbi jelzés | Valószínű kör | Most |
|---|---|---|
| ~42–45 | Korai `test_biblical_map_ui` (hely + passage) | Beépült a 106 UI tesztbe |
| 65 | Bővített map UI (routes előtt/után) | UI fájl most 106 teszt; UI+routes+research = **151 passed** |
| 12 | `test_place_enrichment_research.py` | **12** teszt, a 151-es futás része |

### Lefedettség vs hiány

**Jól fedett:** passage linking, auto/manual select, kereső, forrás UI, route modell, family nav, layout columns hiánya, research readiness szabályok, enrichment loader.  
**Gyengén / nincs automata:** valódi böngésző megjelenés; pydeck vizuális minőség; éles Streamlit verzió `st.map(height=…)` kompatibilitás éles gépen; központi tudásbázis integráció; research → enrichment próza pipeline.

---

## 7. Forrás- és tartalmi készültség

### Evidence osztályok (research batch, megtalálható)

`batch_001_evidence_packets.json` + `batch_001_strict_coverage_report.json`:

| Osztály | Darab | Jelentés |
|---|---:|---|
| A_biblical_primary | 312 | passage / bibliai |
| B_structured_gazetteer | 185 | OpenBible / Pleiades meta |
| C_external_institutional | 4 | UNESCO jellegű |
| D_external_scholarly | 0 | — |
| E_contextual_secondary | 13 | kontextuális |
| F_inference | 0 | — |
| G_unsupported | 0 | — |
| **Összesen** | **514** | |

**[Tény]** A 92 acquisition task létezik (`batch_001_source_acquisition_queue.json`, mind open).  
**[Tény]** Ezek a research helyek **nem** kapcsolódnak a 20 publikált enrichment profilhoz (0 overlap).

### Hat `partial_profile_ready` hely — mi hiányzik a `source_backed_profile_ready`-hez

Közös szigorú küszöb (builder DoD): ≥3 érvényes section, ≥2 független külső C/D/E, legalább egy C vagy D, nincs G, biblical rendben.

| place_id | Most | Fő hiány |
|---|---|---|
| egypt | partial; ext=1 (UNESCO Théba) | 2. független C/D; homiletics tiltva; Théba csak kontextuális Egyiptomra |
| tyre | partial; ext=1 (UNESCO Tyre) | 2. független C/D (pl. ásatás/múzeum); scholarly D |
| zion / mount_zion / judea_1 | partial; ext=1 (UNESCO Jeruzsálem) | 2. forrás; archaeology helyspecifikus C/D; Sion ≠ teljes Óváros |
| edom | partial; ext=1 (UNESCO Petra) | Petra ≠ egész Edóm; archaeology szándékosan blocked; 2. forrás |

### Publikált 20 enrichment „source_backed” vs research 0

**[Tény]** A `place_enrichments.json` 20 profilja `overall_review_status: source_backed`, de a szigorú research DoD szerint a batch **0** `source_backed_profile_ready`.  
**[Következtetés]** A publikált címke lazább (section_count / source_ids alapú `enrichment_profile_status`). Nyilvános állításoknál a szigorúbb research küszöb a mérvadóbb a történeti/régészeti mélységre.

---

## 8. Készültségi szintek (Definition of Done)

### A. Belső MVP

**DoD (mérhető):**

1. Modul bekötve a Textusműhelybe.  
2. Katalógus betölt ≥100 hellyel, koordinátával.  
3. Passage linking + kereső működik tesztekkel.  
4. ≥1 útvonal (Pál első) állomásokkal.  
5. ≥2 ellenőrzött, forrásolt helyprofil (Corinth, Ephesus).  
6. Lokális pytest zöld a UI+routes magra.

| Feltétel | Állapot |
|---|---|
| 1–5 | **Teljesült** |
| 6 | **Részleges** (mag 151 zöld; 3 audit teszt piros) |
| Vizuális smoke | **Hiányzik / UI-ellenőrzés** |

### B. Nyilvános béta

**DoD:**

1. Támogatott tartomány UI-ban jelezve (shell vs source-backed).  
2. Minden látható történeti/régészeti állítás C/D forrással.  
3. ≥50 partial vagy jobb profil **vagy** világos „csak bibliai+földrajzi váz” címke.  
4. Útvonalak `draft` helyett legalább `reviewed` family-nként 1.  
5. Audit tesztek szinkronban; feature ág pusholva.  
6. Nincs félrevezető 50/50 source-backed állítás.

| Feltétel | Állapot |
|---|---|
| 2, 3, 4 | **Hiányzik** |
| 6 | **Részleges** (research kijavítva; publikált 20-as címke még laza) |
| 1, 5 | **Hiányzik / részleges** |

### C. Éles, bővíthető

**DoD:** központi tudásbázis-összekötés, verziózott tartalom, szerkesztői workflow, skálázható import, monitoring, mainre mergeable CI.  
**Állapot:** **Hiányzik** (tudásbázis audit fájl sincs a repóban).

### Százalékos becslések (nem rekordarány)

| Tengely | MVP | Béta | Éles | Indoklás |
|---|---:|---:|---:|---|
| Technikai implementáció | **85%** | 55% | 35% | UI+adatmodell+route kész; hiány: státuszjelölés, KB bridge |
| Automata tesztlefedettség | **80%** | 60% | 40% | Erős unit/fake-st; 3 stale audit; nincs e2e böngésző |
| Helyszínadatok mennyisége | **90%** | 70% | 50% | 1267 hely + 8654 link bőséges MVP/béta mennyiségre |
| Helyszínadatok forrásminősége | **35%** | 20% | 10% | 2 featured mélyprofil; 20 laza enrichment; 0 szigorú research source-backed |
| Útvonalak készültsége | **70%** | 40% | 25% | 12 schematic draft route; jó navigáció, nem „kész történelem” |
| Dokumentáció / karbantarthatóság | **75%** | 50% | 30% | Sok docs; KB audit hiányzik; audit tesztek elcsúsztak |
| Éles bevezethetőség | **25%** | 15% | 5% | 38 unpushed commit; uncommitted fájlok; nincs production gate |

**Összesített [Következtetés]:**

- **Belső MVP: ~75–80%** (használható belsőre).  
- **Nyilvános béta: ~35–40%**.  
- **Éles: ~15–20%**.

---

## 9. Hátralévő munka (prioritás)

| Prio | Feladat | Érintett | Függőség | Típus | Codex? | Emberi teológia/forrás? | Méret | Kockázat | Elfogadás |
|---|---|---|---|---|---|---|---|---|---|
| MVP | Audit tesztek szinkronja a 1267/161 állapothoz | `tests/test_biblical_places_audit.py`, audit JSON | — | tech | Igen | Nem | S | Alacsony | 0 fail a mapish suite-ban |
| MVP | `bible_text_ui.py` persist_state diff külön commit/review | `bible_text_ui.py` | — | tech | Igen | Nem | XS | Közepes (idegen a map PR-tól) | Clean working tree vagy tudatos commit |
| MVP | Untracked duplicate batch 001–004 sorsa (törlés vagy docs) | untracked JSON | reviewed fájlok | tartalmi/ops | Részben | Igen (ha új merge) | XS–S | Zavar a PR-ban | Nincs véletlen stage |
| MVP | Emberi UI smoke: ApCsel 18, ApCsel 13, Pál út, kereső | futó Streamlit | local server | QA | Nem | Nem | S | Vizuális bug | Checklist pipa |
| Béta | UI státuszjelölés: shell / biblical_draft / partial / source_backed | `biblical_map_ui.py` | readiness listák | tech+UX | Igen | Részben | M | Félrevezető tartalom | Felirat egyezik DoD-dal |
| Béta | 6 partial → 2. C/D forrás + szigorú source_backed | research + registry | internet/forrás | tartalmi | Részben | **Igen** | L | Gyenge forrás | `source_backed_ready` > 0 |
| Béta | Research evidence → draftolt enrichment a 50-ös biblical listára | enrichment builder/data | emberi szerkesztés | tartalmi | Részben | **Igen** | L–XL | AI-próza | biblical sections reviewed |
| Béta | Publikált 20-as `source_backed` címke szigorítása | `biblical_place_enrichment.py` | research szabályok | tech | Igen | Igen | M | Státuszcsökkenés | Egy DoD |
| Béta | Útvonal review: Pál család `reviewed` + warning megmarad | routes JSON | szerkesztő | tartalmi | Részben | Igen | M | Túlzott pontosság érzet | review_status mező |
| Későbbi | 161 uncertain duplicate döntés | duplicate workflow | emberi | tartalmi | Nem | Igen | L | Rossz merge | queue csökken |
| Későbbi | Archaeology/history C/D tömeges research | acquisition queue (92) | források | tartalmi | Részben | **Igen** | XL | Licenc/URL | gap csökken |
| Éles | Központi tudásbázis összekötés | új modul + docs | KB audit | arch | Részben | Igen | XL | Architektúra | verziózott sync |
| Éles | CI + main merge policy a feature ágra | GitHub | zöld tesztek | tech | Igen | Nem | M | Regresszió | required checks |
| Éles | Push 38 commit tudatos PR-rel | remote | review | ops | Nem | Igen (PR) | M | Nagy diff | PR URL |

### Szétválasztás

- **MVP előtt kötelező:** audit tesztfix, uncommitted fájlok tisztázása, rövid UI smoke.  
- **Béta előtt kötelező:** státuszjelölés, forrásminőség / címke igazság, legalább néhány szigorú source-backed profil, útvonal review jelölés.  
- **Későbbi bővítés:** tömeges archaeology, duplicate maradék, új útvonalcsaládok.  
- **Tudásbázis-átállás:** külön XL projekt; jelen audit fájl hiányzik.

---

## 10. Kötelező végkövetkeztetés

### Hol tart most ténylegesen a térképes modul?

**[Következtetés]** Stabil **belső prototípus / közel MVP**: teljes katalógus, erős passage+route UI, 12 schematic útvonal, 2 mély featured helyprofil (Corinth, Ephesus), 20 lazábban „source_backed” enrichment, és egy szigorú research réteg, ami őszintén 0 source_backed_profile_ready-t ad a 50-ös batchre.

### Használható-e már belső tesztelésre?

**Igen** — a Textusműhelybe be van kötve; a mag tesztek (151) zöldek; a fő forgatókönyvek logikailag igazolhatók.

### Mi akadályozza a nyilvános használatot?

1. A legtöbb hely **shell** (nincs mély history/archaeology).  
2. Státuszjelölés nem védi a felhasználót a túlzó tartalomérzettől.  
3. Útvonalak `draft` / `schematic`.  
4. 38 pusholatlan commit + commitolatlan fájlok.  
5. 3 elavult audit teszt.  
6. Nincs központi tudásbázis-összekötés / éles DoD.

### Hány, valóban forrásolt helyszínprofil kész?

- **Szigorú research DoD szerint:** **0** `source_backed_profile_ready`; **6** partial; **50** biblical_draft_ready (csak evidence, nem próza).  
- **Publikált enrichment szerint:** **2** featured (Corinth, Ephesus) érdemi history+archaeology szekcióval; **20** profil létezik lazább `source_backed` címkével.

### Hány útvonal tekinthető késznek?

**0 éles „kész”.** **12** funkcionálisan használható **draft/schematic** útvonal; Pál első a legérettebb (`certainty: certain`), de review_status továbbra is `draft`.

### Mi legyen a következő egyetlen implementációs feladat?

**Az elavult `tests/test_biblical_places_audit.py` három failing tesztjének igazítása a jelenlegi 1267-es katalógus / 161 uncertain duplicate / HU-complete állapothoz** — ez gyors, Codex-képes, és helyreállítja a „mapish suite zöld” MVP-kaput anélkül, hogy tartalmi döntést kérne.

### A feature ág készen áll-e commitra / pushra / main merge-re?

| Lépés | Állapot |
|---|---|
| További map-commit (tiszta tree nélkül) | **Nem** — van `M bible_text_ui.py` + 4 untracked duplicate batch |
| Push | **Technikailag lehetséges** (38 ahead), de **nem ajánlott** review nélkül |
| Main merge | **Nem** — nincs remote szinkron + béta DoD hiányzik |

### Mely commitolatlan fájlokat kell külön ellenőrizni?

1. `bible_text_ui.py` (`persist_state` eltávolítás)  
2. `duplicate_review_batch_001.json` … `_004.json` (untracked; vs `*_reviewed.json`)

### Mekkora a hátralévő munka?

| Szint | Becslés | Jelleg |
|---|---|---|
| MVP zárás | **S–M** (tesztfix + tree tisztítás + UI smoke) | főleg tech/QA |
| Béta | **L–XL** (forrásminőség, státusz UX, útvonal review, néhány szigorú profil) | tech + emberi forrás |
| Éles | **XL+** (KB integráció, CI/main, skálázott szerkesztés) | architektúra + tartalom |

---

## Audit záradék

Ez a jelentés kizárólag `docs/biblical_map_status_audit.md` létrehozását/módosítását célozza. A többi working-tree fájl érintetlenül hagyandó; a záró `git status` ezt visszaigazolja.

---

## 11. Automatizált MVP-lezárás után (2026-07-30, későbbi kör)

A következő technikai lépések **elkészültek** a kézi béta-smoke előtt:

1. Feature ág push + working tree tisztítás.
2. Elavult `test_biblical_places_audit` asszertek igazítva a 1267 / 161 állapothoz.
3. Őszinte profilstátusz: OpenBible/gazetteer-only profilok legfeljebb `partial`; `featured` csak Corinth/Ephesus mélységnél.
4. Térkép expander scope-figyelmeztetés + kutatási readiness caption a helykártyán.

### Kézi UI-smoke checklist (béta előtt — nálad)

Futtasd a Streamlit appot, nyisd ki a **Bibliai térkép** expandert, és ellenőrizd:

1. Látszik-e a prototípus / vázlatos útvonal figyelmeztetés.
2. **ApCsel 18,1–18** → Korinthus / több hely, teljes szélességű térkép.
3. **ApCsel 13** → route prompt / Pál első út átváltás.
4. **Bibliai útvonalak** → Pál első missziói út, állomások a térkép alatt.
5. Kereső: `Korinthus`, `Efézus` → featured státusz szöveg.
6. Egy shell hely (pl. katalógusból) → alap / részleges státusz, nem „forrásolt” túlzás.
7. Ismeretlen igehely (pl. Jn 3,16) → nincs véletlen helyválasztás.

Ha ez a checklist zöld, a modul **belső MVP kész**; a nyilvános béta továbbra is tartalmi forrásmunkát igényel (lásd §9).
