# TEXTUS · Homiletikai műhely

**Verzió:** 1.0 (lásd `APP_VERSION` az `app.py` elején)

**A szövegtől a szószékig** — református lelkipásztori környezetre szabott, AI-asszisztált homiletikai műhely: bibliai szakasz alapján exegetikai, teológiai és homiletikai segédleteket készít a **Google Gemini** API-val. A projekt **ingyenes és nyílt forráskódú** ([MIT licenc](LICENSE)).

**Web:** [textus.ro](https://textus.ro) · [textus.streamlit.app](https://textus.streamlit.app)

## Funkciók (röviden)

- **Igehely** — teljes elemzés: áttekintés, exegézis, kortörténet, teológia, illusztrációk, aktualizálás (Google Search grounding), eredeti nyelvi fókusz, énekajánló
- **Finomító chat** szekciónként, **vázlatkosár**, **Markdown export**, **munkamenet mentése / betöltése** (JSON)
- TEXTUS-arculat: háttér, glassmorphism, tipográfia (részletek az `app.py` CSS-blokkjában)

## Előfeltételek

- **Python 3.10** vagy újabb
- **Google Gemini API kulcs** ([Google AI Studio](https://aistudio.google.com/))

## Telepítés

```bash
git clone <a-repo-URL-je>.git
cd <a-klónozott-mappa-neve>
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

## Futtatás

```bash
streamlit run app.py
```

Az alkalmazás megnyílik a böngészőben. A **Gemini API kulcsot** az oldalsáv **Beállítások** fülén add meg (a kulcs a munkamenetben marad; éles környezetben érdemes titkot / környezeti változót használni).

## Opcionális eszközök

- **Ikonok / logó:** az `app.py` a `icons/` mappa és egyéb útvonalak alapján keres képeket (pl. `igehely.png`, `textus_logo.png`). Ha nincs fájl, van elegáns fallback.
- **Háttérkép:** a kódban definiált útvonalak szerint (lásd `find_file` az `app.py`-ban).

## Licenc

**MIT** — lásd a [LICENSE](LICENSE) fájlt. Szabadon használhatod, módosíthatod, terjesztheted; nincs garancia. Nem kell érte fizetni.

A LICENSE szerzői sora: **Copyright (c) 2026 Hover**.

## Közreműködés

Pull request és issue üdvözölt — különösen: fordítások, hozzáférhetőség, hibajavítások, dokumentáció.

---

*„A teljes Írás Istentől ihletett és hasznos a tanításra, a feddésre, a megjobbításra és az igazságban való nevelésre.” — 2Timóteus 3,16*
