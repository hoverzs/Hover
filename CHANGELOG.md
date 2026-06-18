# Changelog

## [1.0] — 2026-06-17 — TEXTUS arculat

### Branding

- Az alkalmazás neve **Emmaus** → **TEXTUS** (minden felhasználói felületen, metaadatban és exportban).
- Alcím: **Homiletikai műhely** (a korábbi „digitális homiletikai műhely” helyett).
- Új mottó: **A szövegtől a szószékig**.
- Igeidézet: Lukács 24,32 (Emmaus-út) → **2Timóteus 3,16** (az Írás ihletettségéről és hasznáról).

### Fejléc és vizuális identitás

- Új fejléc-struktúra: TEXTUS és V1.0 külön sorban, alatta Homiletikai műhely, mottó (A szövegtől a szószékig), majd 2Timóteus 3,16.
- A logó fallback a kereszt helyett a **T** betűt jeleníti meg; a logókeresés előnyben részesíti a `textus_logo.png` fájlt.
- Tipográfia finomítás: nagybetűs TEXTUS cím, szövegértelmezésre utaló idézet-stílus (bal oldali szegély).
- Oldalikon: 📖 (bibliai szöveg hangsúly).

### Domain és hivatkozások

- Hivatalos domain: **textus.ro**
- Streamlit Cloud: **textus.streamlit.app**
- Lábléc domain-linkekkel.

### Fájlok és azonosítók

- Export fájlnevek: `textus-vazlat-…`, `textus-munka-…`.
- Munkamenet JSON `_app` mező: **Textus** (a korábbi Emmaus fájlok továbbra is betölthetők).
- AI rendszerprompt és tiltott bevezető-minták frissítve TEXTUS megnevezésre.

### Dokumentáció

- `README.md`, `requirements.txt`, `secrets.toml` kommentek egységesítve.

### Nem változott

- Üzleti logika, funkciók, Gemini-modellválasztás, munkamenet-struktúra és API-viselkedés érintetlen.
