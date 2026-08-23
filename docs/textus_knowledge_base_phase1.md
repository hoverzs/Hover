# TEXTUS Knowledge Base — Phase 1 implementációs jegyzet

**Dátum:** 2026-08-23  
**Ág:** `feature/knowledge-base-core`  
**Státusz:** KB Core Foundation (Phase 1) — kész, production integráció nélkül

---

## Mit implementáltunk

Izolált `textus_kb` Python csomag:

| Modul | Feladat |
|---|---|
| `textus_kb/canonical_reference.py` | `CanonicalReference` parse + determinisztikus serializáció |
| `textus_kb/books.py` | 66 könyv OSIS-szerű belső registry + RÚF mapping |
| `textus_kb/manifest.py` | Read-only `kb_manifest.json` loader/validator |
| `textus_kb/health.py` | Strukturált health report + self-test |
| `textus_kb/paths.py` | Package/project path feloldás |
| `textus_kb/data/kb_manifest.json` | Forrás registry (6 reprezentatív forrás) |
| `textus_kb/__main__.py` | CLI: `python -m textus_kb` |

**Nem implementált (szándékos):** retrieval, embeddings, UI, `app.py` bekötés, feature flag production flow-ban, external importer.

---

## Canonical form

**Belső kanonikus könyvkód:** OSIS-szerű rövid azonosító (pl. `John`, `Gen`, `1Cor`, `Ps`).

**Canonical serialization:**

| Eset | Formátum | Példa |
|---|---|---|
| Egy vers | `{book}.{chapter}.{verse}` | `John.4.16` |
| Tartomány, egy fejezet | `{book}.{chapter}.{start}-{end}` | `John.4.1-42` |
| Keresztfejezetes | `{book}.{sc}.{sv}-{ec}.{ev}` | `John.4.1-5.10` |

**Determinizmus:** `parse(input).canonical_string()` — azonos szakasz különböző bemeneti alakjai ugyanazt adja (pl. `Jn 4,1–42`, `JHN 4:1-42`, `John.4.1-42` → `John.4.1-42`).

**Magyar / belső nevek:** delegálás a meglévő `ruf_bible_service.parse_bible_reference()` + `BOOK_LOOKUP` aliasokra (production kód **nem** módosult).

**Versifikáció:** `CanonicalReference.versification_scheme` opcionális mező — későbbi ENG/ORG/RUF mapping réteghez; Phase 1-ben nem töltődik.

---

## Manifest schema

Fájl: `textus_kb/data/kb_manifest.json`

Gyökér mezők:

- `manifest_version` (string)
- `description`, `generated_at` (opcionális meta)
- `sources` (tömb)

Forrás objektum kötelező mezői:

- `id`, `name`, `source_type`, `language`, `version`, `license`, `local_path`, `required`, `enabled`
- opcionális: `license_url`, `restricted`, `usage_note`

Támogatott `license` értékek: `CC-BY-4.0`, `CC-BY-3.0`, `MIT`, `contractual-restricted`, `reference-only`, `unknown`.

**Phase 1 források:**

| id | Megjegyzés |
|---|---|
| `stepbible_tagnt` | required, enabled |
| `stepbible_tahot` | required, enabled |
| `stepbible_tbesg` | optional, enabled |
| `stepbible_tbesh` | required, enabled |
| `biblical_places_catalog` | optional, enabled |
| `ruf_2014_local` | **restricted**, `enabled: false`, contractual license |

---

## Health működés

Parancsok:

```bash
python -m textus_kb
python -m textus_kb.health
```

Kimenet: JSON

- `overall_status`: `ok` | `degraded` | `error`
- `manifest_status`
- `sources[]`: id, enabled, required, available, version, license, path, errors, warnings
- `canonical_self_tests[]`: Jn 4 normalizálás + cross-input consistency

Read-only — **nem** javít, **nem** tölt le, **nem** módosít fájlokat.

---

## Tesztek

- `tests/test_textus_kb/test_canonical_reference.py`
- `tests/test_textus_kb/test_manifest.py`
- `tests/test_textus_kb/test_health.py`

**39 új teszt** (≥25 követelmény teljesül).

Baseline KB-kapcsolódó 198 teszt + újak: **237 passed**.

---

## Ismert korlátok

1. **Nincs fejezet/vers felső határ ellenőrzés** — csak ≥1 és range sorrend (nincs per-könyv max vers szám).
2. **Nincs teljes OSIS / SBL / UBS univerzális parser** — csak Textusban használt magyar/belső/angol formák.
3. **Cross-book tartomány** nem támogatott.
4. **RÚF manifestben szerepel**, de `enabled: false` — tartalom nem került mozgatásra; disabled forrás **nincs disk probe** a health checkben.
5. **Preferált CLI:** `python -m textus_kb` (`python -m textus_kb.health` runpy warning lehetséges).
6. **TBESG / RÚF** hiánya clone-on → optional esetén `degraded`, required esetén `error` — app viselkedés változatlan.

---

## Phase 1 quality gate (2026-08-23)

- **CanonicalReference edge cases:** `Jn` vs `1Jn/2Jn/3Jn`, magyar/angol/belső kódok, Zsoltárok, range/unicode dash — zöld.
- **Path portability:** manifest `local_path` repo-relative; health report **POSIX relative** (`data/...`), nincs hardcoded `C:\Users\...`.
- **RÚF izoláció:** `enabled: false`, disabled hiány nem ront health státuszt, nincs fájl probe.
- **Tesztek:** 56 `test_textus_kb` + 198 baseline = **254 passed**; teljes suite `_qa_shell` permission miatt kihagyva (`pytest --ignore=_qa_shell` futtatható külön).

---

## Következő fázisra nyitott pontok (Phase 2 — nem kezdve)

- `textus_kb/retrieval.py` + adapterek (`places`, `tokens_greek`, …)
- Jn 4,1–42 Evidence Packet golden fixture + CLI `retrieve`
- Shadow mode / prompt injekció — **külön fázis**, feature flaggel
- Versification mapping réteg
- Manifest generátor script (checksum automatikus)

---

## Production izoláció ellenőrzés

Phase 1 diff **nem** érinti: `app.py`, AI promptok, Supabase, `bible_engine/*` runtime, `requirements.txt`.
