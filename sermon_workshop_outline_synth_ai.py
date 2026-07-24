"""Igehirdetési vázlat — kétfázisú homiletikai szintézis (szerkesztő + lektor).

Nem importál app.py / sermon_workshop_ui.py fájlból.
A forrás műhelymezőket (M4–M9) soha nem írja vissza.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from sermon_workshop_data import (
    empty_outline_movement,
    normalize_sermon_outline,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _is_api_error_text
from sermon_workshop_m6_ai import movement_role_label
from sermon_workshop_outline_ai import (
    DEFAULT_TEMPERATURE,
    OUTLINE_PLACEHOLDER_BANLIST,
    TAB_OUTLINE,
    _GENERIC_MOVEMENT_TITLES,
    _normalize_cmp,
    _s,
    _usable_text,
    is_banned_outline_placeholder,
    outline_to_readable_content,
)

GenerateFn = Callable[..., str]

# Soft issues may hint a repair pass, but never discard an otherwise usable outline.
SOFT_QUALITY_ISSUES = frozenset(
    {
        "word_count_out_of_range",
        "stock_phrases",
        "sermon_like_verbosity",
    }
)

# Üres sablonfordulatok — csak ha a textus+kontextus nem indokolja őket.
_STOCK_PHRASE_MARKERS = (
    "a kegyelem abban van",
    "nem a mi erőnkből",
    "isten tervének része",
    "isten tervének része volt",
)

HOMILETIC_SYSTEM_PROMPT = """\
SZEREP

Tapasztalt, textushű, református (reformátori) szemléletű homiletikai szerkesztő vagy. \
Feladatod: a rendelkezésre álló műhelyanyagból koherens, teológiailag pontos, \
hallható, röviden kibontott igehirdetési MUNKAVÁZLATOT készíteni.

Ez NEM bullet-jegyzet, és NEM kész prédikáció / kézirat. A szószéken tovább \
fejleszthető, áttekinthető munkavázlat legyen: világos ív, rövid kidolgozás, \
kevés ismétlés.

A vázlat legyen biblikusan felelős, gyülekezetszerű és hallható nyelven \
megfogalmazott. A krisztusközpontúság a textusból és a kánoni összefüggésből \
emelkedjen ki — ne legyen automatikus zárójelszó minden pont végén.

KÖTELEZŐ FORRÁSOK (ebben a sorrendben)

1. Textus + bibliai szöveg (és közvetlen irodalmi kontextusa).
2. Jóváhagyott Textusműhely-felismerések.
3. Meglévő homiletikai döntések (főgondolat, feszültség, Krisztus-ív, mozgások stb.).
4. Alkalom típusa + alkalmi kontextus, ha a projektben jelen van.
5. Saját megjegyzések / felhasználói fókusz.
6. A még hiányzó elemekhez felelős, visszafogott MI-következtetés.

A hiányzó műhelyadatok nem akadályozhatják meg egy teljes szerkezetű vázlat \
elkészítését. A meglévő műhelyanyag elsőbbséget élvez; a hiányzó részeket a \
textusból óvatosan egészítsd ki. Részleges anyag esetén is add vissza a teljes \
szerkezetet — rövidebben.

CSENDES ELŐKÉSZÍTÉS

1. Határozd meg a textus műfaját, gondolati mozgását és természetes határait.
2. Ha a gondolati ív a következő versben zárul, jelezd a text_boundary_note \
mezőben (nem blokkoló).
3. Fogalmazz meg egyetlen, hallható fókuszmondatot (legfeljebb 25 szó).
4. Textusspecifikus egységek: tipikusan 2–3 (Virrasztó/Temetés: 2, max. 3; \
vasárnapi: 2–3, csak ha a textus természetesen kívánja a harmadikat).
5. Hallgatói ív: helyzet → textusállítások → megérkezés (Krisztusra mutató, \
nem moralizáló).
6. Távolítsd el az ismétléseket, közhelyeket és a generikus MI-fordulatokat.

CÉLFORMA (a JSON mezők ezt a szerkezetet hordozzák)

- Cím + Textus + egyetlen Fókuszmondat.
- Bevezetés: rövid bekezdés konkrét hallgatói helyzetből; ne közhely, ne \
kérdéslista.
- 1–3 mozgás, mindegyik: rövid emlékezetes cím; development[0] = „A textus \
állítása” (2–4 mondat); development[1] = „Hallgatói irány” (1–2 mondat, a \
textusból). Ne használj „Exegetikai kibontás / Kegyelmi kapcsolat / Hallgatói \
kapcsolat” technikai címkéket.
- Megérkezés: rövid, Krisztusra mutató zárás; ne ismételd a bevezetést; ne \
moralizálj.
- Még finomítható: legfeljebb két rövid, hasznos tipp.

KIMENET (JSON)

- title, text_reference, focus_sentence (max. 25 szó; ne: „A textus arra szólít fel…”).
- introduction.development + rövid transition.
- movements[]: title, textual_anchor, development (2 bekezdés a fenti forma szerint), transition.
- conclusion.development + final_sentence.
- refinement_suggestions: max. 2 rövid tipp.
- text_boundary_note / suggested_text_boundary: csak ha indokolt.

TEOLÓGIAI ÉS STILÁRIS SZABÁLYOK

- Ne állíts többet annál, mint amit a textus és a források alátámasztanak.
- Ne ismételd pontonként a fókuszmondatot a bevezetésben, a pontokban és a lezárásban.
- Kerüld az üres sablonfordulatokat, hacsak a textus+kontextus indokolja: \
„a kegyelem abban van”, „nem a mi erőnkből”, „Isten tervének része”.
- Ne sugalld, hogy bibliai szereplők szabadon választanak életet/halált, ha a \
textus feszültség, várakozás vagy gondviselés (pl. Fil 1,21–24).
- Gyász / Virrasztó: ne bagatellizáld a veszteséget; ne ígérj üdvösséget az \
elhunytról adat nélkül; ne találj ki életrajzi részleteket a családnak.
- Krisztusközpontúság a textusból jöjjön — ne automatikus zárójelszó.
- Felszólításokat hordozza Isten cselekvése; kerüld a moralizálást.
- Legfeljebb egy retorikai kérdés a bevezetésben; ne három egymást követő kérdés.

CÉLHOSSZ (irányadó, NEM merev elutasítás)

- Vasárnapi / általános munkavázlat: ~450–700 szó.
- Virrasztó / rövid áhítat: ~350–550 szó.
- Temetés: tömör, vigasztaló (~350–600 szó).
- Részleges műhelyanyag: teljes szerkezet, rövidebb OK.
A szószám önmagában soha nem indokolja a válasz elvetését — a használhatóság a döntő.

TILOS A KIMENETBEN: kettős számozás („1. 1.”); üres cím/mező; tartalom nélküli \
címkék; nyers Markdown ##; félbehagyott / …-dal levágott mondatok; belső \
sémanév; fallback-összefűzés; „Ez a rész még nincs kidolgozva”; „Nem \
állapítható meg felelősen”; „A hallgató a textus világába lép”; „A textus \
magja elmélyül”; „A fő gondolat megérkezik”; „Exegetikai kibontás”; \
„Kegyelmi kapcsolat”; „Hallgatói kapcsolat”.

Ne másold egymás után a forrásanyagokat — szintetizálj.

Válaszod KIZÁRÓLAG érvényes JSON legyen.\
"""

_SYNTH_JSON_SHAPE = """\
{
  "title": "Textusspecifikus, rövid cím",
  "text_reference": "Igehely",
  "focus_sentence": "Egyetlen hallható központi állítás (max. 25 szó)",
  "text_boundary_note": "",
  "suggested_text_boundary": "",
  "introduction": {
    "development": "Rövid bekezdés konkrét hallgatói helyzetből — ne ismételje a fókuszt",
    "transition": "Átvezetés az első mozgásba"
  },
  "movements": [
    {
      "title": "Rövid, emlékezetes cím (számozás nélkül)",
      "textual_anchor": "Kapcsolódó versszakasz",
      "development": [
        "A textus állítása: 2–4 mondat a textus saját hangján",
        "Hallgatói irány: 1–2 mondat a textusból — konkrét felismerés vagy válasz"
      ],
      "transition": "Rövid átvezetés"
    }
  ],
  "conclusion": {
    "development": "Rövid Megérkezés: Krisztusra mutató, nem moralizáló, ne ismételje a bevezetést",
    "final_sentence": "Megjegyezhető zárómondat"
  },
  "refinement_suggestions": [
    "Legfeljebb két rövid, hasznos tipp"
  ]
}
"""


def resolve_outline_occasion(
    bundle: Mapping[str, Any] | None = None,
    *,
    occasion: Any = "",
    extra_text: Any = "",
) -> str:
    """Alkalom a bundle / session mezőkből vagy a szövegből (Virrasztó stb.)."""
    raw = _s(occasion)
    if not raw and isinstance(bundle, Mapping):
        raw = _s(bundle.get("occasion"))
    blob = " ".join(
        [
            raw,
            _s(extra_text),
            _s((bundle or {}).get("user_focus")) if isinstance(bundle, Mapping) else "",
            _s((bundle or {}).get("project_title"))
            if isinstance(bundle, Mapping)
            else "",
        ]
    ).casefold()
    if "virraszt" in blob:
        return "Virrasztó"
    if "temet" in blob:
        return "Temetés"
    if "vasárnap" in blob or "vasarnap" in blob:
        return "Vasárnapi istentisztelet"
    return raw


def _is_partial_workshop_bundle(bundle: Mapping[str, Any] | None) -> bool:
    if not isinstance(bundle, Mapping):
        return False
    keys = {
        _s(k)
        for k in (bundle.get("source_keys") or [])
        if _s(k)
        and _s(k)
        not in {
            "passage_reference",
            "passage_text",
            "bible_translation",
            "project_title",
            "occasion",
            "user_focus",
        }
    }
    # Részleges: van valami tartalom, de nincs tele a műhely.
    return 0 < len(keys) < 5


def outline_length_profile(
    occasion: Any = "",
    *,
    partial: bool = False,
) -> dict[str, Any]:
    """Alkalomfüggő hossz-/szerkezet-útmutató (prompt + soft szószámjelzés).

    Cél-tartományok (prompt): vasárnapi ~450–700; Virrasztó ~350–550.
    Soft min/max enyhén tágabb — szószám önmagában soha nem hard reject.
    """
    occ = resolve_outline_occasion(occasion=occasion)
    occ_cf = occ.casefold()
    if "virraszt" in occ_cf:
        soft_min, soft_max = 300, 600
        target = "350–550"
        min_movements = 2
        guidance = (
            f"Virrasztó: rövidebb, intim áhítat-munkavázlat (~{target} szó irányadó). "
            "Hangnem: csendes, gyászoló közösséghez illő — ne bagatellizáld a veszteséget; "
            "ne ígérj üdvösséget az elhunytról adat nélkül; ne találj ki életrajzi részleteket. "
            "Szerkezet: cím, textus, fókuszmondat, rövid bevezetés, 2 (max. 3) egység "
            "(A textus állítása + Hallgatói irány), megérkezés; legfeljebb 1–2 rövid tipp. "
            "Ne írj teljes temetési prédikációt vagy hosszú szószéki kéziratot."
        )
        intro_hint = "40–70 szó"
        movement_hint = "2 egység (max. 3), egyenként: 2–4 mondat textusállítás + 1–2 mondat hallgatói irány"
        conclusion_hint = "40–80 szó"
    elif "temet" in occ_cf:
        soft_min, soft_max = 300, 650
        target = "350–600"
        min_movements = 2
        guidance = (
            f"Temetés: tömör, világos, vigasztaló munkavázlat (~{target} szó irányadó). "
            "2–3 egység; kerüld a túlírt szószéki kibontást és a moralizálást."
        )
        intro_hint = "40–80 szó"
        movement_hint = "2–3 egység (A textus állítása + Hallgatói irány)"
        conclusion_hint = "50–90 szó"
    else:
        soft_min, soft_max = 400, 800
        target = "450–700"
        min_movements = 2
        guidance = (
            f"Vasárnapi / általános igehirdetés: szószéki munkavázlat (~{target} szó irányadó). "
            "2–3 textusspecifikus mozgás (a harmadik csak ha a textus természetesen kívánja). "
            "Röviden kibontott — ne kész prédikáció."
        )
        intro_hint = "50–90 szó"
        movement_hint = "2–3 egység, egyenként: 2–4 mondat textusállítás + 1–2 mondat hallgatói irány"
        conclusion_hint = "50–100 szó"
    if partial:
        soft_min = max(250, soft_min - 100)
        guidance += (
            " Részleges műhelyanyag: a meglévő adatok elsőbbséget élveznek; "
            "a hiányzó részeket a textusból óvatosan egészítsd ki. "
            "Teljes szerkezet, rövidebb terjedelem elfogadható."
        )
    return {
        "occasion": occ or "Vasárnapi istentisztelet",
        "soft_min": soft_min,
        "soft_max": soft_max,
        "target_range": target,
        "min_movements": min_movements,
        "guidance": guidance,
        "intro_hint": intro_hint,
        "movement_hint": movement_hint,
        "conclusion_hint": conclusion_hint,
        "partial": partial,
    }


def _hard_quality_issues(issues: list[str] | tuple[str, ...] | None) -> list[str]:
    return [i for i in (issues or []) if i not in SOFT_QUALITY_ISSUES]


def _occasional_context_for_prompt(bundle: Mapping[str, Any] | None) -> str:
    """Alkalmi kontextus a projektből (saját fókusz / megjegyzés), ha van."""
    if not isinstance(bundle, Mapping):
        return ""
    parts: list[str] = []
    for key in ("user_focus", "outline_manual_notes"):
        val = _usable_text(bundle.get(key))
        if val:
            parts.append(val)
    # Dedup similar snippets
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        n = _normalize_cmp(p)
        if n and n not in seen:
            seen.add(n)
            out.append(p)
    return " | ".join(out[:2])


def _occasion_block_for_prompt(
    bundle: Mapping[str, Any] | None,
) -> str:
    """Alkalom típusa + hosszútávú útmutatás — kötelezően a generáló promptba."""
    profile = outline_length_profile(
        resolve_outline_occasion(bundle),
        partial=_is_partial_workshop_bundle(bundle),
    )
    occ_ctx = _occasional_context_for_prompt(bundle)
    lines = [
        f"ALKALOM: {profile['occasion']}",
        f"CÉLHOSSZ: ~{profile['target_range']} szó (irányadó).",
        f"HOSSZÚTÁVÚ ÚTMUTATÁS: {profile['guidance']}",
        (
            f"Bevezetés irányadó hossza: {profile['intro_hint']}. "
            f"Mozgások: {profile['movement_hint']}. "
            f"Lezárás / Megérkezés: {profile['conclusion_hint']}."
        ),
        "A szószám NEM merev elutasítási küszöb — használható munkavázlatot adj vissza.",
    ]
    if occ_ctx:
        lines.insert(
            1,
            f"ALKALMI KONTEXTUS (projektből — hangnemet/struktúrát igazítsd ehhez): {occ_ctx}",
        )
    return "\n".join(lines) + "\n"


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    system_bundle: str = HOMILETIC_SYSTEM_PROMPT,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    prev_temp = None
    touched = False
    try:
        import streamlit as st

        prev_temp = st.session_state.get("temperature")
        st.session_state["temperature"] = float(temperature)
        touched = True
    except Exception:  # noqa: BLE001
        touched = False
    try:
        return generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TAB_OUTLINE,
            use_cache=False,
            system_bundle=system_bundle,
            include_brevity_directive=False,
        )
    finally:
        if touched:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:  # noqa: BLE001
                pass


def _ctx_for_prompt(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in bundle.items() if not str(k).startswith("_")}


def _locked_main_idea(bundle: Mapping[str, Any], seed: Mapping[str, Any]) -> str:
    """Jóváhagyott / prioritásos főgondolat — AI ne gyengítse."""
    sermon = _usable_text(bundle.get("sermon_main_idea"))
    sermon_status = _s(bundle.get("sermon_main_idea_status"))
    text = _usable_text(bundle.get("text_main_idea"))
    text_status = _s(bundle.get("text_main_idea_status"))
    if sermon and sermon_status == "approved":
        return sermon
    if text and text_status == "approved":
        return text
    if sermon:
        return sermon
    seed_idea = _usable_text(seed.get("main_idea"))
    if seed_idea:
        return seed_idea
    insights = bundle.get("approved_insights") or []
    if isinstance(insights, list) and insights:
        return _usable_text(insights[0])
    return text


def _protect_approved_fields(
    merged: dict[str, Any],
    *,
    bundle: Mapping[str, Any],
    seed: Mapping[str, Any],
) -> dict[str, Any]:
    locked = _locked_main_idea(bundle, seed)
    if locked:
        merged["main_idea"] = locked
    if _usable_text(seed.get("manual_notes")):
        merged["manual_notes"] = _usable_text(seed.get("manual_notes"))
    for meta in (
        "passage_reference",
        "bible_translation",
        "lection_reference",
        "lection",
        "prayer_before",
        "prayer_after",
        "source_sections",
        "source_fingerprint",
        "source_completeness",
        "project_title",
    ):
        if seed.get(meta) not in (None, "", [], {}):
            merged[meta] = seed.get(meta)
    return merged


def _movement_from_obj(raw: Mapping[str, Any], *, index: int) -> dict[str, Any] | None:
    item = empty_outline_movement()
    role = _s(raw.get("role"))
    title = _strip_leading_number(_usable_text(raw.get("title")))
    if not title or is_banned_outline_placeholder(title):
        return None
    if _normalize_cmp(title) in _GENERIC_MOVEMENT_TITLES:
        return None

    development: list[str] = []
    seen: set[str] = set()
    for para in raw.get("development") or []:
        t = _usable_text(para)
        n = _normalize_cmp(t)
        if t and n not in seen:
            development.append(t)
            seen.add(n)
    # Legacy mezők → development, ha a modell régi sémát adott
    if not development:
        for key in (
            "exegetical_core",
            "textual_basis",
            "theological_claim",
            "core_content",
            "listener_discovery",
            "grace_application",
        ):
            t = _usable_text(raw.get(key))
            n = _normalize_cmp(t)
            if t and n not in seen:
                development.append(t)
                seen.add(n)
        for a in raw.get("applications") or []:
            t = _usable_text(a)
            n = _normalize_cmp(t)
            if t and n not in seen:
                development.append(t)
                seen.add(n)
    if len(development) < 1:
        return None

    anchor = _usable_text(raw.get("textual_anchor")) or _usable_text(
        raw.get("textual_basis")
    )
    # Ne ismételjük a vershorgonyt első bekezdésként
    development = [
        p for p in development if _normalize_cmp(p) != _normalize_cmp(anchor)
    ]
    if not development:
        return None
    core = development[0]
    item.update(
        {
            "id": _s(raw.get("id")) or f"synth_mv_{index}",
            "title": title,
            "role": role,
            "role_label": movement_role_label(role) if role else "",
            "textual_basis": anchor,
            "textual_anchor": anchor,
            "exegetical_core": _usable_text(raw.get("exegetical_core")),
            "theological_claim": _usable_text(raw.get("theological_claim")),
            "core_content": _usable_text(raw.get("core_content")) or core,
            "listener_discovery": _usable_text(raw.get("listener_discovery")),
            "grace_application": _usable_text(raw.get("grace_application")),
            "transition": _usable_text(raw.get("transition")),
            "development": development[:6],
            "applications": [
                _usable_text(a)
                for a in (raw.get("applications") or [])
                if _usable_text(a)
            ][:4],
        }
    )
    return item


def apply_synth_payload_to_outline(
    seed: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any],
    replace_movements: bool = True,
) -> dict[str, Any]:
    """JSON payload → normalizált munkavázlat (jóváhagyott mezők védelmével)."""
    merged = dict(normalize_sermon_outline(seed))

    # Új séma mezők
    title = _usable_text(payload.get("title")) or _usable_text(
        (payload.get("title_suggestions") or [None])[0]
        if isinstance(payload.get("title_suggestions"), list)
        and payload.get("title_suggestions")
        else ""
    )
    if title:
        merged["sermon_title"] = title
        tips_titles = [
            _usable_text(t)
            for t in (payload.get("title_suggestions") or [])
            if _usable_text(t)
        ]
        if title not in tips_titles:
            tips_titles = [title] + tips_titles
        merged["title_suggestions"] = tips_titles[:3]

    focus = _usable_text(payload.get("focus_sentence")) or _usable_text(
        payload.get("main_idea")
    )
    if focus:
        merged["main_idea"] = focus

    text_ref = _usable_text(payload.get("text_reference"))
    if text_ref:
        merged["passage_reference"] = text_ref

    # Textushatár megjegyzés (AI vagy determinisztikus hint)
    boundary_note = _usable_text(payload.get("text_boundary_note"))
    boundary_sug = _usable_text(payload.get("suggested_text_boundary"))
    if not boundary_note:
        hint = suggest_text_boundary_hint(
            merged.get("passage_reference") or bundle.get("passage_reference"),
            bundle.get("passage_text") or "",
        )
        boundary_note = hint.get("text_boundary_note") or ""
        boundary_sug = boundary_sug or hint.get("suggested_text_boundary") or ""
    if boundary_note:
        merged["text_boundary_note"] = boundary_note
    if boundary_sug:
        merged["suggested_text_boundary"] = boundary_sug

    intro_raw = (
        payload.get("introduction")
        if isinstance(payload.get("introduction"), dict)
        else {}
    )
    intro_dev = _usable_text(intro_raw.get("development")) or _usable_text(
        payload.get("opening_direction")
    )
    intro_tr = _usable_text(intro_raw.get("transition"))
    if intro_dev:
        idea_n = _normalize_cmp(merged.get("main_idea"))
        if idea_n and _normalize_cmp(intro_dev) == idea_n:
            intro_dev = ""
        if intro_dev:
            merged["introduction"] = {
                "development": intro_dev,
                "transition": intro_tr,
            }
            merged["opening_direction"] = intro_dev

    # Háttér mezők (nem jelennek meg a főnézetben, de a diagnosztika használhatja)
    for key in (
        "homiletical_aim",
        "human_situation",
        "listener_question",
        "central_tension",
        "listener_resistance",
        "divine_gracious_action",
        "christ_connection",
        "gospel_resolution",
        "grace_enabled_response",
        "main_idea_summary",
    ):
        val = _usable_text(payload.get(key))
        if val:
            merged[key] = val

    tips_src = payload.get("refinement_suggestions")
    if not tips_src:
        tips_src = payload.get("editorial_tips")
    tips = [
        _usable_text(t)
        for t in (tips_src or [])
        if _usable_text(t) and not is_banned_outline_placeholder(t)
    ]
    cleaned_tips: list[str] = []
    for tip in tips[:2]:
        low = tip.casefold()
        if any(w in low for w in ("hiányzik", "kötelező", "nem töltött", "üres mező")):
            continue
        cleaned_tips.append(tip)
    if cleaned_tips:
        merged["editorial_tips"] = cleaned_tips[:2]

    if replace_movements:
        raw_mvs = payload.get("movements")
        if isinstance(raw_mvs, list) and raw_mvs:
            new_mvs: list[dict[str, Any]] = []
            for i, mv in enumerate(raw_mvs[:4], start=1):
                if not isinstance(mv, dict):
                    continue
                built = _movement_from_obj(mv, index=i)
                if built:
                    new_mvs.append(built)
            min_mvs = int(
                outline_length_profile(
                    resolve_outline_occasion(bundle),
                    partial=_is_partial_workshop_bundle(bundle),
                )["min_movements"]
            )
            if len(new_mvs) >= min_mvs:
                merged["movements"] = new_mvs
                merged["provisional_sections"] = [
                    p
                    for p in (merged.get("provisional_sections") or [])
                    if p != "sermon_movements"
                ]
    conc_raw = (
        payload.get("conclusion")
        if isinstance(payload.get("conclusion"), dict)
        else {}
    )
    obj_closing = (
        payload.get("closing") if isinstance(payload.get("closing"), dict) else {}
    )
    conc_dev = _usable_text(conc_raw.get("development")) or _usable_text(
        obj_closing.get("final_insight")
    )
    conc_final = _usable_text(conc_raw.get("final_sentence")) or _usable_text(
        obj_closing.get("image_or_line")
    ) or _usable_text(obj_closing.get("invitation"))
    idea_n = _normalize_cmp(merged.get("main_idea"))
    if conc_dev and idea_n and _normalize_cmp(conc_dev) == idea_n:
        conc_dev = ""
    if conc_dev or conc_final:
        merged["conclusion"] = {
            "development": conc_dev,
            "final_sentence": conc_final,
        }
        cur = dict(merged.get("closing") or {})
        if conc_dev:
            cur["final_insight"] = conc_dev
        if conc_final:
            cur["image_or_line"] = conc_final
        for key in ("gospel_assurance", "invitation", "open_question"):
            cand = _usable_text(obj_closing.get(key))
            if cand:
                cur[key] = cand
        merged["closing"] = cur

    # Alkalmazások a mozgások development-jéből / legacy applications
    apps: list[str] = []
    seen: set[str] = set()
    for item in payload.get("applications") or []:
        a = _usable_text(item)
        n = _normalize_cmp(a)
        if a and n not in seen:
            apps.append(a)
            seen.add(n)
    for mv in merged.get("movements") or []:
        for item in mv.get("applications") or []:
            a = _usable_text(item)
            n = _normalize_cmp(a)
            if a and n not in seen:
                apps.append(a)
                seen.add(n)
        ga = _usable_text(mv.get("grace_application"))
        n = _normalize_cmp(ga)
        if ga and n not in seen:
            apps.append(ga)
            seen.add(n)
    if apps:
        extra = dict(merged.get("extra_enrichment") or {})
        extra["applications"] = apps[:8]
        merged["extra_enrichment"] = extra

    merged = _protect_approved_fields(merged, bundle=bundle, seed=seed)
    opening = _usable_text((merged.get("introduction") or {}).get("development")) or _usable_text(
        merged.get("opening_direction")
    )
    idea_n = _normalize_cmp(merged.get("main_idea"))
    if opening and idea_n and _normalize_cmp(opening) == idea_n:
        merged["opening_direction"] = ""
        merged["introduction"] = {"development": "", "transition": ""}
    merged = normalize_sermon_outline(merged)
    merged["content"] = outline_to_readable_content(merged)
    return merged


def _word_count(text: Any) -> int:
    raw = _s(text)
    if not raw:
        return 0
    return len([w for w in raw.replace("\n", " ").split(" ") if w.strip()])


def _strip_leading_number(title: str) -> str:
    import re

    return re.sub(r"^\s*\d+[.)]\s*", "", _s(title)).strip()


def suggest_text_boundary_hint(
    passage_reference: Any,
    passage_text: Any = "",
) -> dict[str, str]:
    """Nem blokkoló textushatár-javaslat, ha a gondolati ív a kijelölésen túl zárul.

    Júd 17–20 regresszió: a megmaradás felszólítása a 21. versben zárul le.
    """
    import re

    ref = _normalize_cmp(passage_reference)
    text = _s(passage_text)
    note = ""
    suggested = ""

    # Júdás 17–20 (különböző írásmódok)
    if re.search(r"j[uú]d(?:[aá]s)?\s*17\s*[–\-—]\s*20\b", ref) or re.search(
        r"\bjud(?:e)?\s*17\s*[–\-—]\s*20\b", ref
    ):
        suggested = "Júd 17–21"
        note = (
            "A gondolati ív a következő versben zárul le. "
            f"Javasolt textushatár: {suggested}"
        )
        return {"text_boundary_note": note, "suggested_text_boundary": suggested}

    # Általános: a szöveg félbehagyott mondattal végződik, és van következő vers jelzése
    if text and (
        text.rstrip().endswith("…")
        or text.rstrip().endswith("...")
        or (
            not text.rstrip().endswith((".", "!", "?", "”", '"'))
            and len(text) > 40
        )
    ):
        m = re.search(
            r"(.+?)(\d+)\s*[–\-—]\s*(\d+)\s*$",
            _s(passage_reference).replace(" ", " "),
        )
        if m:
            start_n = int(m.group(2))
            end_n = int(m.group(3))
            if end_n >= start_n:
                prefix = m.group(1).strip()
                suggested = f"{prefix} {start_n}–{end_n + 1}".strip()
                note = (
                    "A gondolati ív a következő versben zárul le. "
                    f"Javasolt textushatár: {suggested}"
                )
    return {
        "text_boundary_note": note,
        "suggested_text_boundary": suggested,
    }


def _looks_truncated(text: Any) -> bool:
    raw = _s(text)
    if not raw:
        return False
    if raw.endswith("...") or raw.endswith("…"):
        return True
    import re

    if re.search(r"[a-záéíóöőúüű]{1,3}\.\.\.$", raw.casefold()):
        return True
    return False


def _has_repeated_paragraphs(content: str) -> bool:
    paras = [
        _normalize_cmp(p)
        for p in content.split("\n\n")
        if _usable_text(p) and len(_usable_text(p)) > 40
    ]
    seen: set[str] = set()
    for p in paras:
        if p in seen:
            return True
        seen.add(p)
    return False


def assess_outline_quality_issues(
    outline: Any,
    *,
    for_ai_output: bool = False,
    occasion: Any = "",
    bundle: Mapping[str, Any] | None = None,
) -> list[str]:
    """Determinisztikus minőségellenőrzés — csak ha van javítandó.

    for_ai_output=True: alkalomfüggő soft jelzések (word_count_out_of_range,
    stock_phrases, sermon_like_verbosity) kerülhetnek a listába, de
    SOFT_QUALITY_ISSUES — önmagában nem utasítható el.
    """
    import re

    safe = normalize_sermon_outline(outline)
    content = _s(safe.get("content")) or outline_to_readable_content(safe)
    issues: list[str] = []
    profile = outline_length_profile(
        resolve_outline_occasion(bundle, occasion=occasion),
        partial=_is_partial_workshop_bundle(bundle),
    )
    min_movements = int(profile["min_movements"])

    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        if banned in content or is_banned_outline_placeholder(
            safe.get("opening_direction")
        ):
            issues.append("placeholder")
            break

    if "##" in content or "```" in content:
        issues.append("raw_markdown")

    # Kettős számozás: „1. 1.” vagy „**1. 1. Cím**”
    if re.search(r"(?m)^\*{0,2}\d+[.)]\s+\d+[.)]", content):
        issues.append("double_numbering")

    forbidden_labels = (
        "Hallgatói felismerés",
        "Kapcsolat típusa",
        "Homiletikai funkció",
        "Grace direction",
        "Listener connection",
        "Központi tartalom",
        "Exegetikai kibontás",
        "Hallgatói kapcsolat",
        "Kegyelmi kapcsolat",
        "gospel_resolution",
        "core_content",
        "listener_discovery",
    )
    for label in forbidden_labels:
        if label in content:
            issues.append("technical_labels")
            break

    focus = _usable_text(safe.get("main_idea"))
    if not focus:
        issues.append("missing_focus")
    elif _word_count(focus) > 25:
        issues.append("focus_too_long")
    if focus.casefold().startswith("a textus arra szólít"):
        issues.append("focus_formulaic")

    intro = safe.get("introduction") if isinstance(safe.get("introduction"), dict) else {}
    opening = _usable_text(intro.get("development")) or _usable_text(
        safe.get("opening_direction")
    )
    if not opening:
        issues.append("missing_opening")
    elif focus and _normalize_cmp(opening) == _normalize_cmp(focus):
        issues.append("intro_repeats_focus")
    elif opening and not _usable_text(opening):
        issues.append("empty_section")

    mvs = [m for m in (safe.get("movements") or []) if isinstance(m, dict)]
    usable_mvs = []
    for mv in mvs:
        title = _strip_leading_number(_usable_text(mv.get("title")))
        if not title or _normalize_cmp(title) in _GENERIC_MOVEMENT_TITLES:
            continue
        if is_banned_outline_placeholder(title):
            continue
        paras = [
            _usable_text(p) for p in (mv.get("development") or []) if _usable_text(p)
        ]
        if not paras:
            core = _usable_text(mv.get("core_content")) or _usable_text(
                mv.get("theological_claim")
            )
            if core:
                paras = [core]
        if not paras:
            issues.append("empty_section")
            continue
        usable_mvs.append(mv)
        for p in paras:
            if _looks_truncated(p):
                issues.append("truncated")
        # Üres „Hallgatói felismerés” jellegű címke a developmentben
        for p in paras:
            if re.match(
                r"(?i)^(hallgatói felismerés|exegetikai kibontás|"
                r"kegyelmi kapcsolat)\s*:?\s*$",
                p,
            ):
                issues.append("empty_section")
    if len(usable_mvs) < min_movements:
        issues.append("weak_movements")

    conclusion = (
        safe.get("conclusion") if isinstance(safe.get("conclusion"), dict) else {}
    )
    closing = safe.get("closing") if isinstance(safe.get("closing"), dict) else {}
    arrival = _usable_text(conclusion.get("development")) or _usable_text(
        closing.get("final_insight")
    )
    if not arrival:
        issues.append("missing_closing")
    elif focus and _normalize_cmp(arrival) == _normalize_cmp(focus):
        issues.append("closing_repeats_focus")

    if _looks_truncated(opening) or _looks_truncated(arrival) or _looks_truncated(content):
        issues.append("truncated")

    if focus and content.count(focus) >= 3:
        issues.append("main_idea_repeat")

    if _has_repeated_paragraphs(content):
        issues.append("repeated_paragraphs")

    # Soft only: guide a repair pass; never a hard rejection by itself.
    if for_ai_output:
        words = _word_count(content)
        soft_min = int(profile["soft_min"])
        soft_max = int(profile["soft_max"])
        if words and (words < soft_min or words > soft_max):
            issues.append("word_count_out_of_range")

        content_cf = content.casefold()
        if any(marker in content_cf for marker in _STOCK_PHRASE_MARKERS):
            issues.append("stock_phrases")

        # Készprédikáció-szerű túlírás: hosszú bevezetés + hosszú lezárás egyszerre
        if (
            _word_count(opening) > 140
            and _word_count(arrival) > 140
            and words > int(profile["soft_max"])
        ):
            issues.append("sermon_like_verbosity")

    return list(dict.fromkeys(issues))


def synthesize_homiletic_outline(
    seed_outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    """1. fázis: teljes homiletikai szintézis. generate_fn nélkül: seed megmarad."""
    seed = normalize_sermon_outline(seed_outline)
    warnings: list[str] = []
    if generate_fn is None:
        return seed, warnings

    ctx = _ctx_for_prompt(bundle)
    locked = _locked_main_idea(bundle, seed)
    seed_slim = {
        k: seed.get(k)
        for k in (
            "main_idea",
            "sermon_title",
            "opening_direction",
            "introduction",
            "movements",
            "closing",
            "conclusion",
            "listener_question",
            "christ_connection",
        )
    }
    occasion_block = _occasion_block_for_prompt(bundle)
    profile = outline_length_profile(
        resolve_outline_occasion(bundle),
        partial=_is_partial_workshop_bundle(bundle),
    )
    prompt = (
        "Készíts KOHERENS, szószéken használható igehirdetési MUNKAVÁZLATOT "
        "(nem bullet-jegyzetet, nem kész prédikációt) a forrásanyagok "
        "SZINTÉZISÉVEL.\n"
        f"{occasion_block}"
        "Kötelező források a FORRÁS JSON-ból: textus+szöveg, jóváhagyott "
        "Textusműhely-felismerések, meglévő homiletikai döntések, alkalom + "
        "alkalmi kontextus, saját megjegyzések.\n"
        "Mozgások formája: rövid emlékezetes cím; development[0]=A textus "
        f"állítása (2–4 mondat); development[1]=Hallgatói irány (1–2 mondat). "
        f"Egységek: {profile['movement_hint']}.\n"
        "A bevezetés ne ismételje a fókuszmondatot. A megérkezés ne legyen "
        "puszta összefoglalás és ne moralizáljon. Legfeljebb 2 "
        "refinement_suggestions.\n"
        f"ZÁROLT FÓKUSZMONDAT (ne gyengítsd): {locked or '(nincs — te állapítsd meg)'}\n\n"
        f"FORRÁS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"MAGVÁZLAT (seed, szintetizáld tovább):\n"
        f"{json.dumps(seed_slim, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_SYNTH_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.35)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Homiletikai szintézis kihagyva: {exc}")
        return seed, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A szintézis API-hiba miatt elmaradt; a helyi vázlat megmaradt.")
        return seed, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen szintézis-válasz; a helyi vázlat megmaradt.")
        return seed, warnings

    had_m6 = "sermon_movements" in (bundle.get("source_keys") or [])
    seed_mvs = seed.get("movements") or []
    replace_mvs = not (
        had_m6
        and len(seed_mvs) >= 3
        and all(_usable_text(m.get("title")) for m in seed_mvs if isinstance(m, dict))
    )
    merged = apply_synth_payload_to_outline(
        seed, obj, bundle=bundle, replace_movements=replace_mvs
    )
    if had_m6 and not replace_mvs and isinstance(obj.get("movements"), list):
        enriched = []
        by_i = [m for m in obj["movements"] if isinstance(m, dict)]
        for i, mv in enumerate(merged.get("movements") or []):
            copy_mv = dict(mv)
            if i < len(by_i):
                other = by_i[i]
                for fk in (
                    "exegetical_core",
                    "theological_claim",
                    "grace_application",
                    "listener_discovery",
                    "transition",
                ):
                    if not _usable_text(copy_mv.get(fk)) and _usable_text(
                        other.get(fk)
                    ):
                        copy_mv[fk] = _usable_text(other.get(fk))
            enriched.append(copy_mv)
        merged["movements"] = enriched
        merged["content"] = outline_to_readable_content(merged)
    return normalize_sermon_outline(merged), warnings


def repair_outline_as_lektor(
    outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    """2. fázis: homiletikai lektor — csak ha a quality gate hibát jelez."""
    current = normalize_sermon_outline(outline)
    warnings: list[str] = []
    if generate_fn is None or not issues:
        return current, warnings

    ctx = _ctx_for_prompt(bundle)
    occasion_block = _occasion_block_for_prompt(bundle)
    # Soft szószámjelzés csak tipp a lektornak — ne dominálja a javítást.
    issue_line = ", ".join(issues)
    prompt = (
        "Te homiletikai LEKTOR vagy. Írd újra a gyenge részeket; a kész vázlatot add vissza.\n"
        "Ne adj hibalista kimenetet a felhasználónak — csak a javított JSON vázlatot.\n"
        f"{occasion_block}"
        f"JELZETT PROBLÉMÁK: {issue_line}\n"
        "Ha csak soft jelzés szerepel (word_count_out_of_range, stock_phrases, "
        "sermon_like_verbosity), ne dobd el a vázlatot: tömöríts / tisztíts, "
        "de tartsd meg a használható tartalmat.\n"
        "Távolítsd el az ismétléseket, sablon címeket, placeholder-eket, moralizálást "
        "és az üres sablonfordulatokat.\n"
        "Mozgások: A textus állítása (2–4 mondat) + Hallgatói irány (1–2 mondat). "
        "Erősítsd a textushűséget és a megérkezést — ne írj kész prédikációt.\n"
        f"ZÁROLT FŐGONDOLAT: {_locked_main_idea(bundle, current)}\n\n"
        f"FORRÁS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"JAVÍTANDÓ VÁZLAT:\n{json.dumps(current, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_SYNTH_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.25)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Lektori javítás kihagyva: {exc}")
        return current, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A lektori kör API-hiba miatt elmaradt.")
        return current, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen lektori válasz.")
        return current, warnings
    repaired = apply_synth_payload_to_outline(
        current, obj, bundle=bundle, replace_movements=True
    )
    return repaired, warnings


def regenerate_outline_part(
    outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    part: str,
    movement_id: str = "",
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    """Részleges újragenerálás — a többi rész és kézi megjegyzések érintetlenek."""
    current = normalize_sermon_outline(outline)
    warnings: list[str] = []
    if generate_fn is None:
        warnings.append("Nincs generáló függvény a részleges újraíráshoz.")
        return current, warnings

    part_key = _s(part)
    allowed = {
        "opening": "introduction",
        "opening_direction": "introduction",
        "bevezetes": "introduction",
        "introduction": "introduction",
        "christ": "christ_arc",
        "christ_arc": "christ_arc",
        "applications": "applications",
        "alkalmazas": "applications",
        "closing": "conclusion",
        "lezaras": "conclusion",
        "conclusion": "conclusion",
        "megerkezes": "conclusion",
        "movement": "movement",
        "mozgás": "movement",
        "mozgas": "movement",
    }
    target = allowed.get(part_key.casefold(), part_key)
    ctx = _ctx_for_prompt(bundle)
    occasion_block = _occasion_block_for_prompt(bundle)
    focus_map = {
        "introduction": current.get("introduction")
        or {"development": current.get("opening_direction"), "transition": ""},
        "christ_arc": {
            "divine_gracious_action": current.get("divine_gracious_action"),
            "christ_connection": current.get("christ_connection"),
            "gospel_resolution": current.get("gospel_resolution"),
            "grace_enabled_response": current.get("grace_enabled_response"),
        },
        "conclusion": current.get("conclusion")
        or {
            "development": (current.get("closing") or {}).get("final_insight"),
            "final_sentence": (current.get("closing") or {}).get("image_or_line"),
        },
        "applications": (current.get("extra_enrichment") or {}).get("applications"),
        "movement": next(
            (
                m
                for m in (current.get("movements") or [])
                if _s(m.get("id")) == _s(movement_id)
            ),
            None,
        ),
    }
    prompt = (
        f"Írd újra CSAK a vázlat ezen részét: {target}.\n"
        "A többi mezőt NE módosítsd — csak a kért részt add vissza "
        "a teljes séma szerint, a változatlan mezőket másold át.\n"
        f"{occasion_block}"
        f"FÓKUSZMONDAT (zárolt): {_locked_main_idea(bundle, current)}\n"
        f"CÉLZOTT RÉSZ MOST: {json.dumps(focus_map.get(target), ensure_ascii=False)}\n\n"
        f"FORRÁS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"TELJES VÁZLAT:\n{json.dumps(current, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_SYNTH_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.3)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Részleges újraírás kihagyva: {exc}")
        return current, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A részleges újraírás API-hiba miatt elmaradt.")
        return current, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen részleges válasz.")
        return current, warnings

    updated = dict(current)
    if target == "introduction":
        intro = obj.get("introduction") if isinstance(obj.get("introduction"), dict) else {}
        cand = _usable_text(intro.get("development")) or _usable_text(
            obj.get("opening_direction")
        )
        if cand and _normalize_cmp(cand) != _normalize_cmp(current.get("main_idea")):
            updated["introduction"] = {
                "development": cand,
                "transition": _usable_text(intro.get("transition")),
            }
            updated["opening_direction"] = cand
    elif target == "christ_arc":
        for key in (
            "divine_gracious_action",
            "christ_connection",
            "gospel_resolution",
            "grace_enabled_response",
        ):
            if _usable_text(obj.get(key)):
                updated[key] = _usable_text(obj.get(key))
    elif target == "conclusion":
        conc = obj.get("conclusion") if isinstance(obj.get("conclusion"), dict) else {}
        closing_obj = obj.get("closing") if isinstance(obj.get("closing"), dict) else {}
        dev = _usable_text(conc.get("development")) or _usable_text(
            closing_obj.get("final_insight")
        )
        final = _usable_text(conc.get("final_sentence")) or _usable_text(
            closing_obj.get("image_or_line")
        )
        if dev or final:
            if _normalize_cmp(dev) == _normalize_cmp(current.get("main_idea")):
                dev = ""
            updated["conclusion"] = {"development": dev, "final_sentence": final}
            cur_c = dict(updated.get("closing") or {})
            if dev:
                cur_c["final_insight"] = dev
            if final:
                cur_c["image_or_line"] = final
            updated["closing"] = cur_c
    elif target == "applications":
        apps = [
            _usable_text(a)
            for a in (obj.get("applications") or [])
            if _usable_text(a)
        ]
        if apps:
            extra = dict(updated.get("extra_enrichment") or {})
            extra["applications"] = apps[:8]
            updated["extra_enrichment"] = extra
    elif target == "movement" and isinstance(obj.get("movements"), list):
        replacement = None
        for mv in obj["movements"]:
            if isinstance(mv, dict) and (
                not movement_id or _s(mv.get("id")) == _s(movement_id)
            ):
                replacement = _movement_from_obj(mv, index=1)
                if replacement:
                    if movement_id:
                        replacement["id"] = movement_id
                    break
        new_list = []
        for mv in updated.get("movements") or []:
            if movement_id and _s(mv.get("id")) == _s(movement_id) and replacement:
                new_list.append(replacement)
            else:
                new_list.append(mv)
        if new_list:
            updated["movements"] = new_list

    updated = _protect_approved_fields(updated, bundle=bundle, seed=current)
    updated = normalize_sermon_outline(updated)
    updated["content"] = outline_to_readable_content(updated)
    return updated, warnings


def run_two_phase_outline_synthesis(
    seed_outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    """Teljes pipeline: szintézis → quality gate → egy javító kör.

    AI hiba / minőségi bukás esetén warnings-ben jelzi; mechanikus
    fallback-összefűzés helyett őszinte QUALITY_GATE_FAILED.
    """
    outline, warnings = synthesize_homiletic_outline(
        seed_outline, bundle, generate_fn=generate_fn
    )
    # Determinisztikus textushatár, ha az AI nem adta
    if not _usable_text(outline.get("text_boundary_note")):
        hint = suggest_text_boundary_hint(
            outline.get("passage_reference") or bundle.get("passage_reference"),
            bundle.get("passage_text") or "",
        )
        if hint.get("text_boundary_note"):
            outline["text_boundary_note"] = hint["text_boundary_note"]
            outline["suggested_text_boundary"] = hint.get(
                "suggested_text_boundary", ""
            )
            outline["content"] = outline_to_readable_content(outline)

    issues = assess_outline_quality_issues(
        outline,
        for_ai_output=bool(generate_fn is not None),
        bundle=bundle,
    )
    if issues and generate_fn is not None:
        outline, repair_warnings = repair_outline_as_lektor(
            outline, bundle, issues=issues, generate_fn=generate_fn
        )
        warnings.extend(repair_warnings)
        remaining = assess_outline_quality_issues(
            outline, for_ai_output=True, bundle=bundle
        )
        hard_remaining = _hard_quality_issues(remaining)
        if hard_remaining:
            warnings.append(
                "A vázlat minőségellenőrzése nem ment át: "
                + ", ".join(hard_remaining)
            )
            content = outline_to_readable_content(outline)
            for banned in OUTLINE_PLACEHOLDER_BANLIST:
                content = content.replace(banned, "")
            outline["content"] = content
        else:
            # Soft-only (pl. szószám) → megtartjuk a használható vázlatot.
            outline["provisional_sections"] = []
    elif generate_fn is not None and not issues:
        outline["provisional_sections"] = []
    outline = normalize_sermon_outline(outline)
    if generate_fn is not None:
        remaining = assess_outline_quality_issues(
            outline, for_ai_output=True, bundle=bundle
        )
        hard_remaining = _hard_quality_issues(remaining)
        if hard_remaining:
            warnings.append("QUALITY_GATE_FAILED:" + ",".join(hard_remaining))
    outline["content"] = outline_to_readable_content(outline)
    return outline, warnings


__all__ = [
    "HOMILETIC_SYSTEM_PROMPT",
    "SOFT_QUALITY_ISSUES",
    "assess_outline_quality_issues",
    "apply_synth_payload_to_outline",
    "outline_length_profile",
    "regenerate_outline_part",
    "repair_outline_as_lektor",
    "resolve_outline_occasion",
    "run_two_phase_outline_synthesis",
    "suggest_text_boundary_hint",
    "synthesize_homiletic_outline",
]
