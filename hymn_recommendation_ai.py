"""Database-grounded hymn recommendation flow.

The LLM may rank known hymn IDs and write pastoral reasons, but hymn numbers,
display numbers, first lines, and titles always come from `hymn_repository`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from bible_engine.hymn_repository import (
    HymnRecord,
    HymnRepositoryStatus,
    ensure_hymn_database,
    get_hymn_candidates,
    get_status,
    validate_hymn_ids,
)


ERE_BOOK_LABEL = "Erdélyi Református Énekeskönyv"
ERE_HYMNAL_CODE = "ERE"
SUPPORTED_HYMNAL_LABELS = {ERE_BOOK_LABEL}
DEFAULT_CANDIDATE_LIMIT = 36

LITURGICAL_SLOTS = (
    ("opening", "Kezdőének"),
    ("before_sermon", "Prédikáció előtti ének"),
    ("main", "Főének"),
    ("closing", "Záróének"),
)

_OCCASION_KEYWORDS = {
    "Úrvacsorás istentisztelet": ("úrvacsora", "Krisztus vére", "bűnbocsánat", "asztal"),
    "Adventi istentisztelet": ("advent", "eljövetel", "várakozás", "reménység"),
    "Karácsonyi istentisztelet": ("karácsony", "született", "Betlehem", "testté lett"),
    "Nagyhét": ("szenvedés", "kereszt", "Krisztus", "megváltás"),
    "Nagypénteki istentisztelet": ("kereszt", "szenvedés", "halál", "vére"),
    "Húsvéti istentisztelet": ("feltámadás", "él", "győzelem", "húsvét"),
    "Pünkösdi istentisztelet": ("Szentlélek", "Lélek", "pünkösd", "tűz"),
    "Reformáció ünnepe": ("erős vár", "ige", "hit", "kegyelem"),
    "Temetés": ("vigasztalás", "feltámadás", "örök élet", "reménység"),
    "Esküvő": ("szeretet", "áldás", "hűség", "szövetség"),
    "Keresztelő": ("szövetség", "gyermek", "áldás", "kegyelem"),
    "Konfirmáció": ("hit", "követés", "fogadás", "Szentlélek"),
    "Bűnbánati istentisztelet": ("bűnbánat", "irgalom", "kegyelem", "megtérés"),
    "Hétközi alkalom / Bibliaóra": ("ige", "tanítás", "követés", "hit"),
    "Ifjúsági istentisztelet": ("követés", "hit", "öröm", "ifjúság"),
}


class HymnRepositoryPort(Protocol):
    def ensure_hymn_database(self) -> HymnRepositoryStatus: ...
    def get_status(self) -> HymnRepositoryStatus: ...
    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> list[HymnRecord]: ...
    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]: ...


@dataclass(frozen=True)
class RecommendedHymn:
    slot_key: str
    slot_label: str
    hymn: HymnRecord
    reason: str
    connection: str


@dataclass(frozen=True)
class HymnRecommendationResult:
    status: str
    markdown: str
    recommendations: tuple[RecommendedHymn, ...] = ()
    repository_status: HymnRepositoryStatus | None = None
    candidate_count: int = 0

    @property
    def available(self) -> bool:
        return self.status == "ok"


class DefaultHymnRepositoryAdapter:
    def ensure_hymn_database(self) -> HymnRepositoryStatus:
        return ensure_hymn_database()

    def get_status(self) -> HymnRepositoryStatus:
        return get_status()

    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> list[HymnRecord]:
        return get_hymn_candidates(query, hymnal_codes, limit=limit)

    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]:
        return validate_hymn_ids(hymn_ids)


def recommend_hymns(
    *,
    igehely: str,
    alkalom: str,
    enekeskonyv: str,
    hangsuly: str = "",
    llm_generate: Callable[[str], str],
    repository: HymnRepositoryPort | None = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> HymnRecommendationResult:
    book = (enekeskonyv or "").strip()
    if book not in SUPPORTED_HYMNAL_LABELS:
        return HymnRecommendationResult(
            status="unsupported_hymnal",
            markdown=_unsupported_hymnal_markdown(book),
        )

    repo = repository or DefaultHymnRepositoryAdapter()
    status = repo.ensure_hymn_database()
    if not status.available:
        return HymnRecommendationResult(
            status="database_unavailable",
            markdown=_unavailable_markdown(status),
            repository_status=status,
        )

    candidates = _collect_candidates(
        repo,
        igehely=igehely,
        alkalom=alkalom,
        hangsuly=hangsuly,
        limit=candidate_limit,
    )
    if not candidates:
        return HymnRecommendationResult(
            status="no_candidates",
            markdown=(
                "⚠️ **Nem találtam ellenőrzött ERE énekjelöltet a helyi énekadatbázisban.**\n\n"
                "Nem készítek szabad LLM-alapú éneklistát, mert az énekszám és a kezdősor "
                "csak validált adatbázisrekordból származhat."
            ),
            repository_status=status,
        )

    prompt = build_hymn_ranking_prompt(
        igehely=igehely,
        alkalom=alkalom,
        hangsuly=hangsuly,
        candidates=candidates,
    )
    raw = llm_generate(prompt)
    ranked = _parse_ranked_response(raw)
    valid_by_id = repo.validate_hymn_ids(item.hymn_id for item in ranked)
    recommendations = _compose_recommendations(ranked, valid_by_id, candidates)
    if not recommendations:
        return HymnRecommendationResult(
            status="no_valid_ranked_hymns",
            markdown=(
                "⚠️ **Az AI-rangsorolás nem adott vissza ellenőrzött hymn_id-t.**\n\n"
                "A hibás vagy nem létező azonosítókat eldobtam, és nem készítek "
                "szabad, adatbázison kívüli énekajánlást."
            ),
            repository_status=status,
            candidate_count=len(candidates),
        )

    return HymnRecommendationResult(
        status="ok",
        markdown=_format_recommendations_markdown(recommendations, _liturgical_note(raw)),
        recommendations=tuple(recommendations),
        repository_status=status,
        candidate_count=len(candidates),
    )


def build_hymn_ranking_prompt(
    *,
    igehely: str,
    alkalom: str,
    hangsuly: str,
    candidates: list[HymnRecord],
) -> str:
    candidate_lines = "\n".join(
        f"- {h.hymn_id}: {h.display_number} — {h.first_line}"
        + (f" | cím: {h.title}" if h.title and h.title != h.first_line else "")
        + (f" | szakasz: {h.section}" if h.section else "")
        for h in candidates
    )
    return f"""\
Te református liturgiai szerkesztő vagy. Nem adhatsz meg énekszámot,
kezdősort vagy címet saját tudásból.

Feladat: az alábbi, adatbázisból kapott ERE hymn_id-k közül válassz ki
legfeljebb négyet a liturgiai ívre. Csak a felsorolt hymn_id-kat használhatod.
Ha egy hymn_id nincs a listában, tilos szerepeltetni.

Igeszakasz: {igehely}
Alkalom: {alkalom}
Prédikációs / teológiai hangsúly: {hangsuly.strip() or "nincs külön megadva"}

Jelöltek:
{candidate_lines}

Válaszolj kizárólag JSON objektummal, ebben az alakban:
{{
  "ranked": [
    {{
      "slot": "opening|before_sermon|main|closing",
      "hymn_id": "ERE:254a",
      "reason": "1-2 magyar mondat",
      "connection": "1 magyar mondat"
    }}
  ],
  "liturgical_note": "opcionális, rövid magyar megjegyzés"
}}

Ne írj markdown-t. Ne írj énekszámot. Ne írj kezdősort. Csak hymn_id-t
rangsorolj és indoklást adj.
"""


@dataclass(frozen=True)
class _RankedItem:
    slot: str
    hymn_id: str
    reason: str
    connection: str


def _collect_candidates(
    repo: HymnRepositoryPort,
    *,
    igehely: str,
    alkalom: str,
    hangsuly: str,
    limit: int,
) -> list[HymnRecord]:
    seen: dict[str, HymnRecord] = {}
    terms = _search_terms(igehely=igehely, alkalom=alkalom, hangsuly=hangsuly)
    per_query_limit = max(8, min(limit, 18))
    for term in terms:
        for hymn in repo.get_hymn_candidates(term, [ERE_HYMNAL_CODE], limit=per_query_limit):
            seen.setdefault(hymn.hymn_id, hymn)
            if len(seen) >= limit:
                return list(seen.values())
    return list(seen.values())


def _search_terms(*, igehely: str, alkalom: str, hangsuly: str) -> list[str]:
    terms: list[str] = []
    terms.extend(_OCCASION_KEYWORDS.get(alkalom, ()))
    terms.extend(_meaningful_phrases(hangsuly))
    terms.extend(_meaningful_phrases(igehely))
    terms.extend(("kegyelem", "hit", "Krisztus", "irgalom", "dicsőség", "reménység"))
    unique: list[str] = []
    for term in terms:
        clean = re.sub(r"\s+", " ", term or "").strip()
        if len(clean) >= 3 and clean.casefold() not in {t.casefold() for t in unique}:
            unique.append(clean)
    return unique


def _meaningful_phrases(text: str) -> list[str]:
    clean = re.sub(r"[^\w\sáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]", " ", text or "", flags=re.UNICODE)
    words = [w for w in clean.split() if len(w) >= 4 and not any(ch.isdigit() for ch in w)]
    phrases: list[str] = []
    if text.strip():
        phrases.append(text.strip())
    phrases.extend(words[:8])
    return phrases


def _parse_ranked_response(raw: str) -> list[_RankedItem]:
    data = _load_json_object(raw)
    ranked = data.get("ranked", []) if isinstance(data, dict) else []
    items: list[_RankedItem] = []
    if not isinstance(ranked, list):
        return items
    for entry in ranked:
        if not isinstance(entry, dict):
            continue
        slot = str(entry.get("slot") or "").strip()
        hymn_id = str(entry.get("hymn_id") or "").strip()
        if slot not in {key for key, _label in LITURGICAL_SLOTS} or not hymn_id:
            continue
        items.append(
            _RankedItem(
                slot=slot,
                hymn_id=hymn_id,
                reason=_clean_reason(entry.get("reason")),
                connection=_clean_reason(entry.get("connection")),
            )
        )
    return items


def _load_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _compose_recommendations(
    ranked: list[_RankedItem],
    valid_by_id: dict[str, HymnRecord],
    candidates: list[HymnRecord],
) -> list[RecommendedHymn]:
    used_ids: set[str] = set()
    used_slots: set[str] = set()
    recommendations: list[RecommendedHymn] = []
    slot_labels = dict(LITURGICAL_SLOTS)
    for item in ranked:
        hymn = valid_by_id.get(item.hymn_id)
        if hymn is None or hymn.hymn_id in used_ids or item.slot in used_slots:
            continue
        recommendations.append(
            RecommendedHymn(
                slot_key=item.slot,
                slot_label=slot_labels[item.slot],
                hymn=hymn,
                reason=item.reason or "Az ének a megadott textus és alkalom fényében illeszkedő jelölt.",
                connection=item.connection or "A kapcsolatot a prédikáció hangsúlyához kell tovább pontosítani.",
            )
        )
        used_ids.add(hymn.hymn_id)
        used_slots.add(item.slot)
        if len(recommendations) >= len(LITURGICAL_SLOTS):
            break
    return recommendations


def _format_recommendations_markdown(
    recommendations: list[RecommendedHymn],
    liturgical_note: str,
) -> str:
    blocks: list[str] = []
    for index, item in enumerate(recommendations, start=1):
        hymn = item.hymn
        blocks.append(
            f"### {index}. {item.slot_label} — *{hymn.hymnal_code} {hymn.display_number}*\n"
            f"**Cím / kezdősor:** {hymn.first_line}\n"
            f"**Indoklás:** {item.reason}\n"
            f"**Kapcsolat az igével:** {item.connection}"
        )
    if liturgical_note:
        blocks.append(f"---\n\n## Liturgiai megjegyzés\n{liturgical_note}")
    return "\n\n".join(blocks)


def _liturgical_note(raw: str) -> str:
    data = _load_json_object(raw)
    note = data.get("liturgical_note", "") if isinstance(data, dict) else ""
    return _clean_reason(note)


def _clean_reason(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:700]


def _unsupported_hymnal_markdown(book: str) -> str:
    label = book or "a választott énekeskönyv"
    return (
        f"⚠️ **A(z) {label} énekeskönyvhöz még nincs validált helyi hymn adatbázis.**\n\n"
        "Ebben az átmeneti állapotban nem készítek szabad LLM-alapú énekajánlást, "
        "mert az énekszám és a kezdősor csak ellenőrzött adatbázisrekordból "
        "származhat. Jelenleg adatbázis-alapon az Erdélyi Református Énekeskönyv támogatott."
    )


def _unavailable_markdown(status: HymnRepositoryStatus) -> str:
    detail = f" (`{status.reason}`)" if status.reason else ""
    return (
        f"⚠️ **Az ellenőrzött ERE énekadatbázis jelenleg nem elérhető{detail}.**\n\n"
        "Nem készítek szabad LLM-alapú éneklistát, mert az énekszám és a kezdősor "
        "csak validált SQLite rekordból származhat."
    )


__all__ = [
    "ERE_BOOK_LABEL",
    "HymnRecommendationResult",
    "RecommendedHymn",
    "build_hymn_ranking_prompt",
    "recommend_hymns",
]
