"""Determinisztikus minőségvédelem a prédikációvázlat-motorhoz.

Fókuszmondat–versszöveg egyezés, helykitöltők, Ámen-főpont, a/b felosztás,
ismétlés, nyers markdown, sémaellenőrzés. Max egy célzott javító hívás.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

# Tiltott sablon / helykitöltő minták (részleges egyezés casefold-dal)
QUALITY_BANLIST: tuple[str, ...] = (
    "a textus saját szavai szerint",
    "a hallgató konkrét felismerésre jut",
    "innen vihető tovább a szószéki kibontás",
    "a teológiai hangsúly abban áll",
    "a teológiai jelentés abban áll",
    "a textus saját mozgása bontja ki ezt a pontot",
    "a textus saját mozgása tovább pontosítja",
    "üres felszólítást kapna",
    "hitbeli felismerésre és válaszra hívja",
    "a textus isten megtartó szavát hirdeti",
    "ez a rész még nincs kidolgozva",
    "nem állapítható meg felelősen",
    "a textus magja elmélyül",
    "a hallgató a textus világába lép",
)

# Önálló Ámen-főpont cím minták
_AMEN_TITLE_RE = re.compile(
    r"^\s*(az\s+)?ámen\.?\s*$",
    re.I,
)
_AMEN_ONLY_CONTENT_RE = re.compile(
    r"^\s*(az\s+)?ámen\.?\s*$",
    re.I,
)

# Önkénes félvers: v. 24a / v. —a / v. 3-a
_HALF_VERSE_RE = re.compile(
    r"\bv\.?\s*(?:—|--)?\s*\d{0,3}\s*[–\-]?\s*[ab]\b",
    re.I,
)
_SYNTHETIC_HALF_RE = re.compile(
    r"\bv\.?\s*(?:—|--)\s*[ab]\b",
    re.I,
)


def _s(value: Any) -> str:
    return str(value or "").strip()


def _norm(text: Any) -> str:
    return " ".join(_s(text).casefold().split())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-záéíóöőúüű0-9]+", _norm(text), flags=re.I)


def focus_passage_overlap_ratio(focus: str, passage: str) -> float:
    """Szóhalmaz-átfedés a fókuszmondat és a bibliai szöveg között (0–1)."""
    f_toks = set(_tokens(focus))
    p_toks = set(_tokens(passage))
    # Szűrjük a nagyon rövid / funkciószavakat
    stop = {
        "a",
        "az",
        "és",
        "hogy",
        "is",
        "nem",
        "meg",
        "el",
        "ki",
        "be",
        "le",
        "fel",
        "vagy",
        "de",
        "ha",
        "mert",
        "mint",
        "egy",
        "ő",
        "ők",
        "mi",
        "ti",
        "én",
        "te",
    }
    f_toks = {t for t in f_toks if len(t) > 2 and t not in stop}
    p_toks = {t for t in p_toks if len(t) > 2 and t not in stop}
    if not f_toks or not p_toks:
        return 0.0
    inter = f_toks & p_toks
    return len(inter) / max(1, len(f_toks))


def focus_is_passage_quote(focus: str, passage: str, *, threshold: float = 0.82) -> bool:
    """Igaz, ha a fókusz lényegében a versszöveg / annak nagy részlete."""
    f = _norm(focus)
    p = _norm(passage)
    if not f or not p:
        return False
    # Teljes vagy majdnem teljes tartalmazás (idézet)
    if len(f) >= 28 and f in p:
        return True
    if len(p) >= 28 and p in f and len(f) <= len(p) + 20:
        return True
    # Hosszú közös substring (≥ 50 karakter)
    if len(f) >= 50:
        window = f[: max(50, int(len(f) * 0.6))]
        if window in p:
            return True
    ratio = focus_passage_overlap_ratio(focus, passage)
    # Magas átfedés önmagában nem elég (teológiai kulcsszavak), csak ha
    # a fókusz rövid a passage-hez képest és majdnem teljes szóhalmaz-egyezés.
    if ratio >= threshold and len(_tokens(focus)) >= 12:
        f_toks = set(_tokens(focus))
        p_toks = set(_tokens(passage))
        if f_toks and len(f_toks - p_toks) <= max(2, len(f_toks) // 10):
            return True
    return False


def find_banned_phrases(text: str) -> list[str]:
    blob = _norm(text)
    hits = []
    for banned in QUALITY_BANLIST:
        if _norm(banned) in blob:
            hits.append(banned)
    return hits


def find_repeated_phrases(
    texts: Sequence[str], *, min_words: int = 8
) -> list[str]:
    """Ismétlődő hosszabb szókapcsolatok a mezők között."""
    seen: dict[str, int] = {}
    repeats: list[str] = []
    for text in texts:
        words = _tokens(text)
        if len(words) < min_words:
            continue
        n = min_words
        if len(words) < n:
            continue
        for i in range(0, len(words) - n + 1):
            gram = " ".join(words[i : i + n])
            seen[gram] = seen.get(gram, 0) + 1
    for gram, count in seen.items():
        if count >= 3:
            repeats.append(gram)
    return repeats[:12]


def has_raw_markdown_noise(text: str) -> bool:
    raw = _s(text)
    if not raw:
        return False
    if re.search(r"(?m)^#{1,6}\s+\S", raw):
        return True
    if "```" in raw:
        return True
    # Félbehagyott csillagozás
    if raw.count("**") % 2 == 1:
        return True
    if re.search(r"(?m)^\s*\*\s+\*\*\s*$", raw):
        return True
    return False


def amen_as_standalone_movement(title: str, body: str = "") -> bool:
    """Ámen önálló főpont — tiltott, ha nincs érdemi teológiai tartalom."""
    if _AMEN_TITLE_RE.match(_s(title) or ""):
        body_n = _norm(body)
        # Ha a body csak ámen / üres / liturgikus szó
        if not body_n or _AMEN_ONLY_CONTENT_RE.match(_s(body) or ""):
            return True
        if body_n in {"ámen", "amen", "az ámen"}:
            return True
        # Cím Ámen, body rövid és nem teológiai
        if len(body_n.split()) <= 8 and "ámen" in body_n:
            return True
        return True  # cím maga is elég a flagezéshez
    return False


def has_arbitrary_half_verse_split(verses_label: str) -> bool:
    """Önkénes „v. —a” / „v. —b” — nem minden hagyományos 24a jelölés."""
    label = _s(verses_label)
    if not label:
        return False
    if _SYNTHETIC_HALF_RE.search(label):
        return True
    # „v. a” / „v. b” szám nélkül
    if re.search(r"\bv\.?\s*[ab]\b", label, flags=re.I) and not re.search(
        r"\d", label
    ):
        return True
    return False


def movements_have_paired_ab_split(movements: Sequence[Mapping[str, Any]]) -> bool:
    """Ugyanazon vers a/b páros felosztása — tipikus sablonhiba."""
    labels = [_s(m.get("verses") or m.get("textual_basis")) for m in movements]
    bases: dict[str, set[str]] = {}
    for lab in labels:
        m = re.search(r"\bv\.?\s*(\d{1,3})\s*([ab])\b", lab, flags=re.I)
        if not m:
            continue
        num, half = m.group(1), m.group(2).lower()
        bases.setdefault(num, set()).add(half)
    return any(len(v) >= 2 for v in bases.values())


def collect_outline_text_fields(payload: Mapping[str, Any]) -> list[str]:
    fields = [
        _s(payload.get("title")),
        _s(payload.get("focus_sentence")),
        _s(payload.get("introduction_direction")),
        _s(payload.get("conclusion_direction")),
        _s(payload.get("christ_grace_connection")),
        _s(payload.get("closing_line")),
    ]
    for h in payload.get("exegetical_handles") or []:
        fields.append(_s(h))
    movements = payload.get("movements") or payload.get("points") or []
    if isinstance(movements, list):
        for mv in movements:
            if not isinstance(mv, dict):
                continue
            fields.extend(
                [
                    _s(mv.get("title")),
                    _s(mv.get("textual_insight")),
                    _s(mv.get("theological_emphasis")),
                    _s(mv.get("listener_movement")),
                    _s(mv.get("transition")),
                    _s(mv.get("original_language_note")),
                    _s(mv.get("poetic_turn")),
                ]
            )
            thoughts = mv.get("thoughts")
            if isinstance(thoughts, list):
                fields.extend(_s(t) for t in thoughts)
    return [f for f in fields if f]


def assess_semantic_quality(
    payload: Mapping[str, Any],
    *,
    passage_text: str = "",
) -> list[str]:
    """Szemantikai / minőségi issue-kódok (determinisztikus)."""
    issues: list[str] = []
    focus = _s(payload.get("focus_sentence"))
    intro = _s(payload.get("introduction_direction"))
    conclusion = _s(payload.get("conclusion_direction"))
    passage = _s(passage_text)

    if focus and passage and focus_is_passage_quote(focus, passage):
        issues.append("focus_is_passage_quote")
    elif focus and passage and focus_passage_overlap_ratio(focus, passage) >= 0.92:
        issues.append("focus_passage_overlap")

    # Bevezetés ne ismételje a teljes textust
    if intro and passage and focus_is_passage_quote(intro, passage):
        issues.append("intro_repeats_passage")
    if conclusion and passage and focus_is_passage_quote(conclusion, passage):
        issues.append("conclusion_repeats_passage")

    blob_fields = collect_outline_text_fields(payload)
    blob = "\n".join(blob_fields)
    banned = find_banned_phrases(blob)
    if banned:
        issues.append("placeholder_banlist")
    if has_raw_markdown_noise(blob):
        issues.append("raw_markdown_noise")

    movements = payload.get("movements") or payload.get("points") or []
    if isinstance(movements, list):
        titles: list[str] = []
        for mv in movements:
            if not isinstance(mv, dict):
                continue
            title = _s(mv.get("title"))
            body = " ".join(
                [
                    _s(mv.get("textual_insight")),
                    _s(mv.get("theological_emphasis")),
                    _s(mv.get("listener_movement")),
                ]
            )
            verses = _s(mv.get("verses") or mv.get("textual_basis"))
            if amen_as_standalone_movement(title, body):
                issues.append("amen_as_main_point")
            if has_arbitrary_half_verse_split(verses):
                issues.append("arbitrary_half_verse")
            # Teljes versismétlés a rétegekben
            if passage and body and focus_is_passage_quote(body, passage):
                issues.append("movement_repeats_passage")
            tnorm = _norm(title)
            if tnorm:
                titles.append(tnorm)
        if movements_have_paired_ab_split(
            [m for m in movements if isinstance(m, dict)]
        ):
            # Páros a/b: soft jelzés a validátorban hardként, de csak ha
            # szintetikus „—” félvers is van, vagy a cím Ámen-szerű.
            # Önálló hard: arbitrary_half_verse már lefedi a „v. —a” esetet.
            # Itt csak akkor hard, ha mindkét félvers cím/vers mezőben van
            # ÉS nincs érdemi különbség a tartalomban — egyszerűsítve: warning kód.
            issues.append("paired_ab_verse_split")
        # Főpontok érdemi különbsége
        if len(titles) >= 2:
            for i in range(len(titles)):
                for j in range(i + 1, len(titles)):
                    a, b = titles[i], titles[j]
                    if a == b or (len(a) > 8 and (a in b or b in a)):
                        issues.append("duplicate_movement_titles")

    # Eredeti nyelvi adat egyezés — ha a payload állít strong/lemmát
    # a brief / handles ellenőrzése a hívó oldalán történik grounded flaggel.

    return list(dict.fromkeys(issues))


SEMANTIC_HARD_ISSUES = frozenset(
    {
        "focus_is_passage_quote",
        "focus_passage_overlap",
        "placeholder_banlist",
        "amen_as_main_point",
        "arbitrary_half_verse",
        "raw_markdown_noise",
        "intro_repeats_passage",
        "conclusion_repeats_passage",
        "movement_repeats_passage",
        "duplicate_movement_titles",
    }
)

REPAIR_INSTRUCTION = """\
CÉLZOTT JAVÍTÁS — csak a jelzett hibákat korrigáld.
Őrizd a textus természetes mozgását és a meglévő érdemi tartalmat.
Ne írj új prédikációt. Ne találj ki verseket vagy nyelvi adatot.

KÖTELEZŐ:
- A fókuszmondat saját megfogalmazású teológiai állítás legyen, NEM versidézet.
- Ne használj helykitöltő / sablonmondatokat.
- Ne bontsd a verseket önkényes v. —a / v. —b részekre.
- Az „Ámen” ne legyen önálló főpont.
- Ne ismételd a teljes versszöveget a bevezetésben, mozgásokban vagy lezárásban.
- Ne hagyj nyers Markdown jeleket.
- Add vissza a teljes, javított JSON vázlatot.
"""


def build_repair_prompt(
    *,
    issues: Sequence[str],
    outline_json: str,
    passage_reference: str,
    bible_text: str,
    json_shape: str,
) -> str:
    return (
        f"{REPAIR_INSTRUCTION}\n"
        f"JELZETT HIBÁK: {', '.join(issues)}\n"
        f"Igehely: {passage_reference}\n\n"
        f"BIBLIAI SZÖVEG (ellenőrzéshez, ne idézd fókuszként):\n{bible_text[:3000]}\n\n"
        f"JAVÍTANDÓ VÁZLAT JSON:\n{outline_json}\n\n"
        f"Kimeneti séma:\n{json_shape}"
    )


__all__ = [
    "QUALITY_BANLIST",
    "REPAIR_INSTRUCTION",
    "SEMANTIC_HARD_ISSUES",
    "amen_as_standalone_movement",
    "assess_semantic_quality",
    "build_repair_prompt",
    "focus_is_passage_quote",
    "focus_passage_overlap_ratio",
    "find_banned_phrases",
    "find_repeated_phrases",
    "has_arbitrary_half_verse_split",
    "has_raw_markdown_noise",
    "movements_have_paired_ab_split",
]
