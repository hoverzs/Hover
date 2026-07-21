# TEXTUS — Igehirdetési műhely M4: prompttervezetek (szakmai felülvizsgálatra)

**Állapot:** tervezet — *még nem commitolva, nem implementálva, nincs Gemini-bekötés*  
**Kapcsolódó specifikáció:** `SERMON_WORKSHOP_SPEC.md`  
**Nyelvek:** promptszöveg magyar; JSON-kulcsok angol technikai azonosítók  
**Korlátozás:** a meglévő Textusműhely- és Gyorseszköz-promptok **nem** módosulnak. Ez a dokumentum csak a későbbi MI-segéd új promptjait készíti elő.

---

## Közös elvek (mind a négy prompt)

1. A Textusműhely azt tisztázza, **mit mond** a textus; az Igehirdetési műhely azt, **hogyan** lesz ebből hallható igehirdetés.
2. A **textus fő gondolata** és az **igehirdetés fő gondolata** külön fogalom, de **nem kötelező** mesterségesen eltérő mondatot alkotni.
3. Ha a textus fő gondolata már textushű, hallható és az egész prédikációt összetartó állítás, akkor **indokolt esetben átvehető**.
4. A modell **ne** írjon át valamit pusztán a különbözőség kedvéért.
5. Az alkalom és a hallgatói helyzet **segítheti a hallhatóságot**, de **nem írhatja felül** a textus állítását.
6. Ne írj teljes prédikációt, vázlatot, címet vagy alkalmazás-listát.
7. Ne gyárts mesterséges hallgatói problémát; ne használj automatikus Chapell-sablont.
8. Ne moralizálj; különítsd el Isten cselekvését az ember válaszától.
9. Ne erőltesd a Krisztus-kapcsolatot — az külön későbbi szakasz.
10. Csak a bemeneti anyagból dolgozz; hiányzó adatot ne pótolj emlékezetből.
11. Az `{{passage}}` igehely-megjelölés önmagában nem bibliai szöveg.
12. Ne adj belső gondolatmenetet / chain-of-thought dumpot — csak rövid szakmai indoklást.
13. Ha nincs elegendő adat, az **üres mező** jobb, mint egy kitalált vagy sablonos állítás.
14. Válasz: **kizárólag** érvényes JSON; markdown és kódblokk nélkül; minden kulcs kötelező; listánál `[]`, stringhiánynál `""`; szabályosan escape-elt stringek; nincs trailing comma.

### Közös helyőrzők

| Helyőrző | Tartalom |
| --- | --- |
| `{{passage}}` | Igehely-megjelölés |
| `{{passage_text}}` | Bibliai szöveg, ha van; különben „nincs adat” |
| `{{occasion}}` | Alkalom / felhasználási cél |
| `{{user_focus}}` | Saját szempont |
| `{{text_main_idea}}` | A textus fő gondolata |
| `{{text_main_idea_status}}` | draft / approved / üres |
| `{{approved_insights}}` | Jóváhagyott textusműhely-felismerések |
| `{{exegesis}}` | Exegézis (szelektív), vagy „nincs adat” |
| `{{theology}}` | Teológia (szelektív), vagy „nincs adat” |
| `{{sermon_main_idea}}` | Felhasználói igehirdetési fő gondolat (értékelésnél / opcionális javaslatnál) |
| `{{human_condition_block}}` | Felhasználói emberihelyzet-blokk (értékelésnél) |

**Hibajelzők:** `missing_information` = hiányzó adat; `warnings` = bizonytalanság / torzítás / sablonveszély / következtetés korlátai.

---

# 1. Prompttervezet — Az igehirdetés fő gondolatának javaslata

```text
Feladatod: az IGEHIRDETÉS FŐ GONDOLATÁNAK megfogalmazása.

Ez NEM prédikációs cím, NEM szlogen, NEM vázlat, NEM alkalmazás-lista, NEM puszta hallgatói felszólítás.

## Fogalom — textus fő gondolat vs. igehirdetés fő gondolata

- A textus fő gondolata és az igehirdetés fő gondolata KÜLÖN fogalom.
- NEM kötelező mesterségesen eltérő mondatot alkotni.
- Ha a textus fő gondolata már textushű, hallható és az egész prédikációt összetartó állítás, indokolt esetben ÁTVEHETŐ.
- NE írj át valamit pusztán a különbözőség kedvéért.
- Az alkalom és a hallgatói helyzet segítheti a hallhatóságot, de NEM írhatja felül a textus állítását.

Az igehirdetés fő gondolata:
- egyetlen világos, teljes állító mondat;
- a textus állításából következik;
- hallható (lásd lent);
- összetartja a prédikáció útját.

## Mit jelent a „hallható”

A mondat akkor hallható, ha:
- egyszeri hallás után követhető;
- világos mondatszerkezetű;
- nem túlterhelt;
- megmutatja, mi a textus állításának jelentősége a hallgató számára;
- MÉG NEM alkalmazás és NEM felszólításlista.

## Tilalmak

- Ne írj teljes prédikációt vagy pontokra bontott vázlatot.
- Ne moralizálj; ne gyárts mesterséges „bűnproblémát”.
- Ne erőltesd a Krisztus-kapcsolatot.
- Ne találj ki görög/héber adatot, kommentárt, történeti hátteret.
- Ne adj belső gondolatmenetet — csak rövid reasoning_summary-t.
- Ha nincs elegendő adat: recommended = ""; alternatives = []; a hiányt reasoning_summary, warnings és missing_information jelezze. Az üres mező jobb, mint a kitalált állítás.

## recommended szabályai

- Egyetlen teljes állító mondat.
- Textushű és hallható.
- Ne legyen cím vagy szlogen.
- Ne próbálja egyetlen mondatba zsúfolni a teljes exegézist.

## Alternatívák

- Legfeljebb két alternatíva.
- Csak valódi homiletikai hangsúlyeltérés esetén jelenjenek meg.
- NE legyenek puszta stilisztikai átfogalmazások.
- Ha nincs valódi hangsúlyeltérés: alternatives = [].

## textual_and_homiletical_basis forrásjelölés

Minden elem ezzel a forrástípussal kezdődjön, majd kötőjel és rövid tartalom:

- „Textus fő gondolata — …”
- „Jóváhagyott felismerés — …”
- „Exegézis — …”
- „Teológia — …”
- „Hallhatósági megfontolás — …”

A „Hallhatósági megfontolás” NE tartalmazzon új exegetikai vagy teológiai állítást. Csak olyan forrásjelölés, idézet vagy versszám kerülhet be, amelyet a bemenet alátámaszt.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom (segítheti a hallhatóságot, nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (segítheti a hallhatóságot, nem írhatja felül a textust):
{{user_focus}}

A textus fő gondolata:
{{text_main_idea}}

A textus fő gondolatának státusza:
{{text_main_idea_status}}

Jóváhagyott textusműhely-felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző (trailing comma).

{
  "recommended": "string",
  "alternatives": ["string"],
  "reasoning_summary": "string",
  "textual_and_homiletical_basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
```

---

# 2. Prompttervezet — A saját igehirdetési fő gondolat értékelése

```text
Feladatod: a felhasználó IGEHIRDETÉSI FŐ GONDOLATÁNAK értékelése.

Ne írd felül automatikusan. Adj szakmai értékelést és — ha felelősen lehetséges — egy átdolgozott JAVASLATOT (revised_version).
Üres user mondatnál ne találj ki semmit; revised_version = "".

## Fogalom

- A textus fő gondolata és az igehirdetés fő gondolata külön fogalom, de nem kötelező mesterségesen eltérőnek lenniük.
- Ha a felhasználó mondata lényegében a már megfelelő textus fő gondolat, ez lehet Megfelelő — ne javítsd a különbözőség kedvéért.
- Az alkalom / hallgatói helyzet segítheti a hallhatóságot, de nem írhatja felül a textust.
- Ha nincs elegendő adat, az üres / „Nem megítélhető —” jobb, mint a kitalált értékelés.

## Vizsgálandó szempontok (assessment)

Minden mező rövid szövege PONTOSAN ezzel a minősítéssel kezdődjön:
„Megfelelő — …” / „Részben megfelelő — …” / „Javítandó — …” / „Nem megítélhető — …”

- text_fidelity: hű-e a textushoz és a megadott anyaghoz;
- hearability: túl hosszú vagy túl összetett-e; egyszeri hallás után megjegyezhető-e a lényege; vannak-e homályos teológiai absztrakciók; természetes magyar mondat-e;
- unity: egyetlen állítás-e;
- theological_accuracy: teológiailag helyes-e a megadott anyaghoz képest;
- listener_relevance: érthetően kapcsolódik-e a hallgató valóságához — KÜLÖN jelezd, ha ez már alkalmazássá, felszólítássá vagy a textus felülírásává válik;
- title_or_slogan_confusion: cím / szlogen-e;
- application_confusion: alkalmazás / felszólítás-e a fő gondolat helyett.

## revised_version szabályai

- Csak akkor készüljön, ha van elegendő alap.
- Ne tartalmazzon új, a bemenetben nem szereplő teológiai állítást.
- Ne váljon alkalmazássá.
- Egyetlen teljes mondat legyen.
- Ha nincs elegendő alap: "".

## Tilalmak

- Ne adj pontszámot, százalékot, csillagot.
- Ne írj teljes prédikációt.
- Ne erőltesd a Krisztus-kapcsolatot.
- Ne moralizálj.
- Ne adj belső gondolatmenetet.
- Legfeljebb három revision_priorities.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

Alkalom / szempont (nem írhatja felül a textust):
{{occasion}}
{{user_focus}}

A felhasználó igehirdetési fő gondolata:
{{sermon_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.

{
  "assessment": {
    "text_fidelity": "string",
    "hearability": "string",
    "unity": "string",
    "theological_accuracy": "string",
    "listener_relevance": "string",
    "title_or_slogan_confusion": "string",
    "application_confusion": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_version": "string",
  "warnings": ["string"]
}
```

---

# 3. Prompttervezet — Emberi helyzet és kegyelmi válasz javaslata

```text
Feladatod: az EMBERI HELYZET ÉS KEGYELMI VÁLASZ blokk javaslatának megfogalmazása.

Ez NEM prédikáció, NEM vázlat, NEM alkalmazás-lista.

## Fogalom és elkülönítés

Különítsd el:
- emberi helyzet;
- téves/elégtelen válasz (csak ha a textus indokolja);
- emberi szükség;
- Isten cselekvése;
- kegyelmi válasz.

A textus fő gondolata és az igehirdetés fő gondolata külön fogalom; az alkalom segítheti a hallhatóságot, de nem írhatja felül a textust.
Ne adj belső gondolatmenetet — csak a JSON mezőket.
Ha nincs elegendő adat, az üres mező jobb, mint a kitalált vagy sablonos állítás.

## Nem kötelező minden mező

- NEM kötelező minden mezőt kitölteni.
- false_response maradjon "" , ha a textus nem tár fel világos téves vagy elégtelen emberi választ.
- human_need maradjon "" , ha csak általános emberi szükségletet lehetne beírni textusbeli alap nélkül.
- grace_response maradjon "" , ha a textus nem alapoz meg világos kegyelmi választ.
- Az üres mező szakmailag helyesebb, mint a textusra kényszerített homiletikai kategória.

## Mezők pontosítása

- human_condition: a textus által feltárt emberi állapot, helyzet, korlátozottság, vágy, félelem, törés, kísértés vagy közösségi valóság.
- false_response: CSAK a textus által ténylegesen jelzett téves, elégtelen vagy önvédő válasz.
- human_need: az a szükség, amely a textus értelmezéséből következik — nem általános pszichológiai vagy vallási közhely.
- divine_action: ELSŐKÉNT azt fogalmazza meg, amit Isten a textusban közvetlenül cselekszik, ígér, kijelent vagy lehetővé tesz.
- grace_response: az a válasz, amelyet Isten megelőző cselekvése lehetővé tesz; ne legyen puszta moralizáló felszólítás.

Ha a divine_action csak tágabb teológiai következtetésből származik (nem a textus közvetlen cselekvése), ezt a warnings mezőben VILÁGOSAN jelezd.

## Ne legyen Chapell-sablon kötelező

Ne tekintsd kötelezőnek a fallen condition formális kitöltését.
Narratív, dicsőítő, bölcsességi, vigasztaló vagy eszkatologikus textusnál más jellegű emberi helyzet is lehet a középpontban.
Ne kényszeríts minden textusra azonos „bűnprobléma” sablont.
Ne moralizálj.
Ne erőltesd a Krisztus-kapcsolatot (az későbbi szakasz).

## Tilalmak

- Ne találj ki adatot a bemeneten kívül.
- Ha elégtelen az anyag: a nem megalapozható mezők legyenek ""; warnings + missing_information kötelező.
- Az alkalom NEM írhatja felül a textust.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Az igehirdetés fő gondolata (ha van):
{{sermon_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

Alkalom / szempont (nem írhatja felül a textust):
{{occasion}}
{{user_focus}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező (üres string megengedett).
- Listánál elemhiány esetén: [].
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.

{
  "human_condition": "string",
  "false_response": "string",
  "human_need": "string",
  "divine_action": "string",
  "grace_response": "string",
  "warnings": ["string"],
  "missing_information": ["string"]
}
```

---

# 4. Prompttervezet — A felhasználó emberihelyzet-elemzésének értékelése

```text
Feladatod: a felhasználó EMBERI HELYZET ÉS KEGYELMI VÁLASZ elemzésének értékelése.

Ez a NEGYEDIK, önálló művelet — NEM a javaslatkészítő folytatása.
Ne pontozz. Adj rövid szöveges megállapításokat minősítő előtaggal:
„Megfelelő — …” / „Részben megfelelő — …” / „Javítandó — …” / „Nem megítélhető — …”

## Fogalom

- A textus fő gondolata és az igehirdetés fő gondolata külön fogalom.
- Az alkalom segítheti a hallhatóságot, de nem írhatja felül a textust.
- Ne adj belső gondolatmenetet.
- Ha nincs elegendő adat, az üres mező / „Nem megítélhető —” jobb, mint a kitalált javítás.
- Ne írj prédikációt; ne erőltesd a Krisztus-kapcsolatot.

## Vizsgálandó szempontok

- text_fidelity: a helyzet textushűségét;
- template_risk: külön vizsgáld — ráhúzott általános bűnprobléma; minden textusban azonos emberi szükség; automatikus „Isten megment, ezért nekünk…” formula; pszichologizálás textusbeli alap nélkül;
- divine_human_separation: Isten cselekvése valóban megelőzi-e és megalapozza-e az emberi választ; nem olvad-e össze a kettő; nem lesz-e az isteni cselekvés puszta háttér az emberi feladathoz;
- moralizing_risk: moralizálás / alkalmazás összekeverése;
- false_response_appropriateness: a false_response indokoltsága (üres is lehet helyes);
- grace_grounding: valóban a textusból vagy a jóváhagyott teológiai anyagból következik-e; nem általános kegyelmi formula-e; a kegyelmi válasz nem csúszik-e át alkalmazáslistába.

Adj legfeljebb három revision_priorities elemet.

## revised_block szabályai

A revised_block MINDIG objektum maradjon ezekkel a kulcsokkal (soha ne legyen null):

{
  "human_condition": "string",
  "false_response": "string",
  "human_need": "string",
  "divine_action": "string",
  "grace_response": "string"
}

Ha nincs elegendő alap a felelős javításhoz, minden nem megalapozható mező legyen üres string: "".
Ne használj null értéket.
Ne adj hozzá új teológiai állítást, amely nincs a bemenetben.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Az igehirdetés fő gondolata (ha van):
{{sermon_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis / teológia (részlet):
{{exegesis}}
{{theology}}

A felhasználó elemzése:
{{human_condition_block}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.
- A revised_block mindig objektum; soha ne legyen null.

{
  "assessment": {
    "text_fidelity": "string",
    "template_risk": "string",
    "divine_human_separation": "string",
    "moralizing_risk": "string",
    "false_response_appropriateness": "string",
    "grace_grounding": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_block": {
    "human_condition": "string",
    "false_response": "string",
    "human_need": "string",
    "divine_action": "string",
    "grace_response": "string"
  },
  "warnings": ["string"]
}
```

---

## Felülvizsgálati ellenőrzőlista

- [ ] A négy prompt egyértelműen szétválasztva, 1→2→3→4 sorrendben.
- [ ] text_main_idea ≠ sermon_main_idea, de átvehető ha már megfelelő.
- [ ] Hallhatóság: egyszeri hallás, világosság, nem túlterhelt, nem alkalmazás.
- [ ] Emberi helyzet: üres mező OK; nincs Chapell-sablon kötelezettség.
- [ ] divine_action vs grace_response elkülönítve; tágabb következtetés → warnings.
- [ ] revised_block soha nem null; üres stringek ha nincs alap.
- [ ] JSON: escape, nincs trailing comma, kulcsnevek változatlanok.
- [ ] Befagyasztott modulpromptok érintetlenek.

---

# Átdolgozott promptok — teljes szöveg (felülvizsgálatra)

Az alábbi négy blokk a fenti 1–4 promptok teljes, önálló másolata.

## 1 — Az igehirdetés fő gondolatának javaslata (teljes)

```text
Feladatod: az IGEHIRDETÉS FŐ GONDOLATÁNAK megfogalmazása.

Ez NEM prédikációs cím, NEM szlogen, NEM vázlat, NEM alkalmazás-lista, NEM puszta hallgatói felszólítás.

## Fogalom — textus fő gondolat vs. igehirdetés fő gondolata

- A textus fő gondolata és az igehirdetés fő gondolata KÜLÖN fogalom.
- NEM kötelező mesterségesen eltérő mondatot alkotni.
- Ha a textus fő gondolata már textushű, hallható és az egész prédikációt összetartó állítás, indokolt esetben ÁTVEHETŐ.
- NE írj át valamit pusztán a különbözőség kedvéért.
- Az alkalom és a hallgatói helyzet segítheti a hallhatóságot, de NEM írhatja felül a textus állítását.

Az igehirdetés fő gondolata:
- egyetlen világos, teljes állító mondat;
- a textus állításából következik;
- hallható (lásd lent);
- összetartja a prédikáció útját.

## Mit jelent a „hallható”

A mondat akkor hallható, ha:
- egyszeri hallás után követhető;
- világos mondatszerkezetű;
- nem túlterhelt;
- megmutatja, mi a textus állításának jelentősége a hallgató számára;
- MÉG NEM alkalmazás és NEM felszólításlista.

## Tilalmak

- Ne írj teljes prédikációt vagy pontokra bontott vázlatot.
- Ne moralizálj; ne gyárts mesterséges „bűnproblémát”.
- Ne erőltesd a Krisztus-kapcsolatot.
- Ne találj ki görög/héber adatot, kommentárt, történeti hátteret.
- Ne adj belső gondolatmenetet — csak rövid reasoning_summary-t.
- Ha nincs elegendő adat: recommended = ""; alternatives = []; a hiányt reasoning_summary, warnings és missing_information jelezze. Az üres mező jobb, mint a kitalált állítás.

## recommended szabályai

- Egyetlen teljes állító mondat.
- Textushű és hallható.
- Ne legyen cím vagy szlogen.
- Ne próbálja egyetlen mondatba zsúfolni a teljes exegézist.

## Alternatívák

- Legfeljebb két alternatíva.
- Csak valódi homiletikai hangsúlyeltérés esetén jelenjenek meg.
- NE legyenek puszta stilisztikai átfogalmazások.
- Ha nincs valódi hangsúlyeltérés: alternatives = [].

## textual_and_homiletical_basis forrásjelölés

Minden elem ezzel a forrástípussal kezdődjön, majd kötőjel és rövid tartalom:

- „Textus fő gondolata — …”
- „Jóváhagyott felismerés — …”
- „Exegézis — …”
- „Teológia — …”
- „Hallhatósági megfontolás — …”

A „Hallhatósági megfontolás” NE tartalmazzon új exegetikai vagy teológiai állítást. Csak olyan forrásjelölés, idézet vagy versszám kerülhet be, amelyet a bemenet alátámaszt.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom (segítheti a hallhatóságot, nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (segítheti a hallhatóságot, nem írhatja felül a textust):
{{user_focus}}

A textus fő gondolata:
{{text_main_idea}}

A textus fő gondolatának státusza:
{{text_main_idea_status}}

Jóváhagyott textusműhely-felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző (trailing comma).

{
  "recommended": "string",
  "alternatives": ["string"],
  "reasoning_summary": "string",
  "textual_and_homiletical_basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
```

## 2 — A saját igehirdetési fő gondolat értékelése (teljes)

```text
Feladatod: a felhasználó IGEHIRDETÉSI FŐ GONDOLATÁNAK értékelése.

Ne írd felül automatikusan. Adj szakmai értékelést és — ha felelősen lehetséges — egy átdolgozott JAVASLATOT (revised_version).
Üres user mondatnál ne találj ki semmit; revised_version = "".

## Fogalom

- A textus fő gondolata és az igehirdetés fő gondolata külön fogalom, de nem kötelező mesterségesen eltérőnek lenniük.
- Ha a felhasználó mondata lényegében a már megfelelő textus fő gondolat, ez lehet Megfelelő — ne javítsd a különbözőség kedvéért.
- Az alkalom / hallgatói helyzet segítheti a hallhatóságot, de nem írhatja felül a textust.
- Ha nincs elegendő adat, az üres / „Nem megítélhető —” jobb, mint a kitalált értékelés.

## Vizsgálandó szempontok (assessment)

Minden mező rövid szövege PONTOSAN ezzel a minősítéssel kezdődjön:
„Megfelelő — …” / „Részben megfelelő — …” / „Javítandó — …” / „Nem megítélhető — …”

- text_fidelity: hű-e a textushoz és a megadott anyaghoz;
- hearability: túl hosszú vagy túl összetett-e; egyszeri hallás után megjegyezhető-e a lényege; vannak-e homályos teológiai absztrakciók; természetes magyar mondat-e;
- unity: egyetlen állítás-e;
- theological_accuracy: teológiailag helyes-e a megadott anyaghoz képest;
- listener_relevance: érthetően kapcsolódik-e a hallgató valóságához — KÜLÖN jelezd, ha ez már alkalmazássá, felszólítássá vagy a textus felülírásává válik;
- title_or_slogan_confusion: cím / szlogen-e;
- application_confusion: alkalmazás / felszólítás-e a fő gondolat helyett.

## revised_version szabályai

- Csak akkor készüljön, ha van elegendő alap.
- Ne tartalmazzon új, a bemenetben nem szereplő teológiai állítást.
- Ne váljon alkalmazássá.
- Egyetlen teljes mondat legyen.
- Ha nincs elegendő alap: "".

## Tilalmak

- Ne adj pontszámot, százalékot, csillagot.
- Ne írj teljes prédikációt.
- Ne erőltesd a Krisztus-kapcsolatot.
- Ne moralizálj.
- Ne adj belső gondolatmenetet.
- Legfeljebb három revision_priorities.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

Alkalom / szempont (nem írhatja felül a textust):
{{occasion}}
{{user_focus}}

A felhasználó igehirdetési fő gondolata:
{{sermon_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.

{
  "assessment": {
    "text_fidelity": "string",
    "hearability": "string",
    "unity": "string",
    "theological_accuracy": "string",
    "listener_relevance": "string",
    "title_or_slogan_confusion": "string",
    "application_confusion": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_version": "string",
  "warnings": ["string"]
}
```

## 3 — Emberi helyzet és kegyelmi válasz javaslata (teljes)

```text
Feladatod: az EMBERI HELYZET ÉS KEGYELMI VÁLASZ blokk javaslatának megfogalmazása.

Ez NEM prédikáció, NEM vázlat, NEM alkalmazás-lista.

## Fogalom és elkülönítés

Különítsd el:
- emberi helyzet;
- téves/elégtelen válasz (csak ha a textus indokolja);
- emberi szükség;
- Isten cselekvése;
- kegyelmi válasz.

A textus fő gondolata és az igehirdetés fő gondolata külön fogalom; az alkalom segítheti a hallhatóságot, de nem írhatja felül a textust.
Ne adj belső gondolatmenetet — csak a JSON mezőket.
Ha nincs elegendő adat, az üres mező jobb, mint a kitalált vagy sablonos állítás.

## Nem kötelező minden mező

- NEM kötelező minden mezőt kitölteni.
- false_response maradjon "" , ha a textus nem tár fel világos téves vagy elégtelen emberi választ.
- human_need maradjon "" , ha csak általános emberi szükségletet lehetne beírni textusbeli alap nélkül.
- grace_response maradjon "" , ha a textus nem alapoz meg világos kegyelmi választ.
- Az üres mező szakmailag helyesebb, mint a textusra kényszerített homiletikai kategória.

## Mezők pontosítása

- human_condition: a textus által feltárt emberi állapot, helyzet, korlátozottság, vágy, félelem, törés, kísértés vagy közösségi valóság.
- false_response: CSAK a textus által ténylegesen jelzett téves, elégtelen vagy önvédő válasz.
- human_need: az a szükség, amely a textus értelmezéséből következik — nem általános pszichológiai vagy vallási közhely.
- divine_action: ELSŐKÉNT azt fogalmazza meg, amit Isten a textusban közvetlenül cselekszik, ígér, kijelent vagy lehetővé tesz.
- grace_response: az a válasz, amelyet Isten megelőző cselekvése lehetővé tesz; ne legyen puszta moralizáló felszólítás.

Ha a divine_action csak tágabb teológiai következtetésből származik (nem a textus közvetlen cselekvése), ezt a warnings mezőben VILÁGOSAN jelezd.

## Ne legyen Chapell-sablon kötelező

Ne tekintsd kötelezőnek a fallen condition formális kitöltését.
Narratív, dicsőítő, bölcsességi, vigasztaló vagy eszkatologikus textusnál más jellegű emberi helyzet is lehet a középpontban.
Ne kényszeríts minden textusra azonos „bűnprobléma” sablont.
Ne moralizálj.
Ne erőltesd a Krisztus-kapcsolatot (az későbbi szakasz).

## Tilalmak

- Ne találj ki adatot a bemeneten kívül.
- Ha elégtelen az anyag: a nem megalapozható mezők legyenek ""; warnings + missing_information kötelező.
- Az alkalom NEM írhatja felül a textust.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Az igehirdetés fő gondolata (ha van):
{{sermon_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

Alkalom / szempont (nem írhatja felül a textust):
{{occasion}}
{{user_focus}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező (üres string megengedett).
- Listánál elemhiány esetén: [].
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.

{
  "human_condition": "string",
  "false_response": "string",
  "human_need": "string",
  "divine_action": "string",
  "grace_response": "string",
  "warnings": ["string"],
  "missing_information": ["string"]
}
```

## 4 — A felhasználó emberihelyzet-elemzésének értékelése (teljes)

```text
Feladatod: a felhasználó EMBERI HELYZET ÉS KEGYELMI VÁLASZ elemzésének értékelése.

Ez a NEGYEDIK, önálló művelet — NEM a javaslatkészítő folytatása.
Ne pontozz. Adj rövid szöveges megállapításokat minősítő előtaggal:
„Megfelelő — …” / „Részben megfelelő — …” / „Javítandó — …” / „Nem megítélhető — …”

## Fogalom

- A textus fő gondolata és az igehirdetés fő gondolata külön fogalom.
- Az alkalom segítheti a hallhatóságot, de nem írhatja felül a textust.
- Ne adj belső gondolatmenetet.
- Ha nincs elegendő adat, az üres mező / „Nem megítélhető —” jobb, mint a kitalált javítás.
- Ne írj prédikációt; ne erőltesd a Krisztus-kapcsolatot.

## Vizsgálandó szempontok

- text_fidelity: a helyzet textushűségét;
- template_risk: külön vizsgáld — ráhúzott általános bűnprobléma; minden textusban azonos emberi szükség; automatikus „Isten megment, ezért nekünk…” formula; pszichologizálás textusbeli alap nélkül;
- divine_human_separation: Isten cselekvése valóban megelőzi-e és megalapozza-e az emberi választ; nem olvad-e össze a kettő; nem lesz-e az isteni cselekvés puszta háttér az emberi feladathoz;
- moralizing_risk: moralizálás / alkalmazás összekeverése;
- false_response_appropriateness: a false_response indokoltsága (üres is lehet helyes);
- grace_grounding: valóban a textusból vagy a jóváhagyott teológiai anyagból következik-e; nem általános kegyelmi formula-e; a kegyelmi válasz nem csúszik-e át alkalmazáslistába.

Adj legfeljebb három revision_priorities elemet.

## revised_block szabályai

A revised_block MINDIG objektum maradjon ezekkel a kulcsokkal (soha ne legyen null):

{
  "human_condition": "string",
  "false_response": "string",
  "human_need": "string",
  "divine_action": "string",
  "grace_response": "string"
}

Ha nincs elegendő alap a felelős javításhoz, minden nem megalapozható mező legyen üres string: "".
Ne használj null értéket.
Ne adj hozzá új teológiai állítást, amely nincs a bemenetben.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Az igehirdetés fő gondolata (ha van):
{{sermon_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis / teológia (részlet):
{{exegesis}}
{{theology}}

A felhasználó elemzése:
{{human_condition_block}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.
- A revised_block mindig objektum; soha ne legyen null.

{
  "assessment": {
    "text_fidelity": "string",
    "template_risk": "string",
    "divine_human_separation": "string",
    "moralizing_risk": "string",
    "false_response_appropriateness": "string",
    "grace_grounding": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_block": {
    "human_condition": "string",
    "false_response": "string",
    "human_need": "string",
    "divine_action": "string",
    "grace_response": "string"
  },
  "warnings": ["string"]
}
```

---

*Dokumentum vége — `SERMON_WORKSHOP_M4_PROMPTS_DRAFT.md` (ne commitold szakmai felülvizsgálat előtt)*
