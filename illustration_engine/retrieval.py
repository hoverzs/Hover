"""Phase 3I: user-facing illustration retrieval.

A provider-independent, two-stage retrieval layer over the same
`illustration_units` corpus the reviewer/QA tooling already governs.
Same dependency-injection pattern as `enrichment_pipeline.py`/
`qa_agent.py`: the caller supplies `llm_generate: Callable[[str], str]`;
this module owns candidate selection, prompt construction, and
fail-closed response parsing -- no Streamlit dependency, no network
code of its own.

TWO RETRIEVAL MODES -- never conflated, never user-toggleable from this
module (the caller decides which one applies, see `RetrievalMode`):

- PRODUCTION: only `published_illustration_units` (status='published'
  AND source license publishable) -- the SAME fail-closed gate the rest
  of the app already trusts for public retrieval.
- DEVELOPMENT: `qa_status='passed'` units regardless of human-review
  status, for internal QA testing -- source rights must STILL be
  publishable, checksum STILL verified. Deliberately does NOT touch
  `human_reviewed_at`, `status`, `approved`, or `published` -- this
  module has no write path to `illustration_units` at all.

TWO-STAGE PIPELINE:
  Stage A (`find_candidates`) -- deterministic, local, no LLM call: FTS5
  full-text search (falling back to an unfiltered recent-first list when
  the query has no FTS matches, so a genuinely obscure passage doesn't
  return zero candidates before the ranker even gets a chance) plus a
  provenance/rights/checksum fail-closed filter, restricted to whichever
  mode's row set applies.
  Stage B (`rank_candidates`) -- Gemini sees ONLY the candidate list (not
  the whole corpus) and may ONLY select `unit_id`s FROM that list. A
  malformed response, or one naming an ID outside the candidate set, is
  parsed fail-closed: unknown IDs are silently dropped (never treated as
  "pick something else"), and a response that cannot be understood at
  all yields zero results -- see `parse_ranking_response`. THE MODEL
  NEVER GENERATES A STORY -- there is no field in the ranking response
  contract for one; the actual `modern_hu_text` shown to the end user
  always comes verbatim from the candidate's own DB row, never from the
  model's ranking response.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Callable

from illustration_engine.source_registry import PUBLISHABLE_LICENSE_STATUSES

RetrievalMode = str  # "production" | "development"
ALLOWED_RETRIEVAL_MODES = frozenset({"production", "development"})

DEFAULT_CANDIDATE_LIMIT = 30
DEFAULT_TOP_N = 5
MIN_TOP_N = 3
MAX_TOP_N = 5


@dataclass(frozen=True)
class RetrievalCandidate:
    unit_id: int
    title_hu: str
    modern_hu_text: str
    summary_hu: str
    moral_hu: str | None
    topics: tuple[str, ...]
    tone: str | None
    homiletic_functions: tuple[str, ...]
    source_title: str
    source_code: str
    tradition: str | None
    license_status: str
    provenance_status: str  # "published" | "development_qa_passed"


@dataclass(frozen=True)
class RankedIllustration:
    unit_id: int
    reason: str
    score: float


@dataclass(frozen=True)
class IllustrationRetrievalResult:
    unit_id: int
    title_hu: str
    modern_hu_text: str
    summary_hu: str
    moral_hu: str | None
    topics: tuple[str, ...]
    tone: str | None
    homiletic_functions: tuple[str, ...]
    source_title: str
    source_attribution: str
    provenance_status: str
    rank_reason: str
    rank_score: float


def _fold_diacritics(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _build_fts_query(query_text: str) -> str | None:
    """Turns free text into a safe FTS5 MATCH expression -- each word
    individually double-quoted (so punctuation/hyphens in the input can
    never be parsed as FTS5 query syntax) and OR-joined. Returns None
    for empty/whitespace-only input, signaling "no keyword filter"."""
    words = re.findall(r"\w+", query_text or "", flags=re.UNICODE)
    if not words:
        return None
    escaped = [w.replace('"', '""') for w in words]
    return " OR ".join(f'"{w}"' for w in escaped)


def _fetch_taxonomy(connection, unit_id: int) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    rows = connection.execute(
        "SELECT t.category, t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
        "WHERE ut.unit_id = ? ORDER BY t.category, t.slug",
        (unit_id,),
    ).fetchall()
    topics = tuple(slug for category, slug in rows if category == "topic")
    tones = [slug for category, slug in rows if category == "tone"]
    functions = tuple(slug for category, slug in rows if category == "function")
    return topics, (tones[0] if tones else None), functions


def _verify_checksum(connection, unit_id: int) -> bool:
    """Fail-closed provenance check: recompute the story's original_text
    checksum and compare against the stored one. A mismatch excludes the
    candidate entirely -- retrieval never surfaces a unit whose source
    integrity cannot be confirmed, in EITHER mode."""
    row = connection.execute(
        """
        SELECT st.original_text, st.original_text_checksum
        FROM illustration_units u JOIN stories st ON st.id = u.story_id
        WHERE u.id = ?
        """,
        (unit_id,),
    ).fetchone()
    if row is None:
        return False
    original_text, checksum = row
    if not checksum:
        return False
    return hashlib.sha256(original_text.encode("utf-8")).hexdigest() == checksum


def find_candidates(
    connection, *, query_text: str, mode: RetrievalMode, limit: int = DEFAULT_CANDIDATE_LIMIT
) -> list[RetrievalCandidate]:
    """Stage A: deterministic, local candidate retrieval. No LLM call.

    `mode="production"`: rows from `published_illustration_units` only
    (status='published' AND source license publishable -- the view
    itself already enforces this).
    `mode="development"`: rows with `qa_status='passed'` AND source
    license publishable, REGARDLESS of human-review `status` -- never
    touches or reads `human_reviewed_at`/`approved`/`published` as a
    gate, purely `qa_status`.

    Both modes additionally verify each candidate's raw-story checksum
    before inclusion (`_verify_checksum`) -- a provenance failure
    excludes the candidate silently, it is never surfaced as an error to
    the end user (this is expected to be rare/never in practice; the
    fail-closed behavior is the point)."""
    if mode not in ALLOWED_RETRIEVAL_MODES:
        raise ValueError(f"mode must be one of {sorted(ALLOWED_RETRIEVAL_MODES)}, got {mode!r}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit!r}")

    fts_query = _build_fts_query(query_text)
    publishable_list = ", ".join(f"'{s}'" for s in sorted(PUBLISHABLE_LICENSE_STATUSES))

    if mode == "production":
        base_select = """
            SELECT p.id, p.title_hu, p.modern_hu_text, p.summary_hu, p.moral_hu,
                   s.title, s.code, s.tradition, s.license_status
            FROM published_illustration_units p
            JOIN stories st ON st.id = p.story_id
            JOIN sources s ON s.id = st.source_id
        """
        provenance_status = "published"
    else:
        base_select = f"""
            SELECT u.id, u.title_hu, u.modern_hu_text, u.summary_hu, u.moral_hu,
                   s.title, s.code, s.tradition, s.license_status
            FROM illustration_units u
            JOIN stories st ON st.id = u.story_id
            JOIN sources s ON s.id = st.source_id
            WHERE u.qa_status = 'passed'
              AND s.license_status IN ({publishable_list})
        """
        provenance_status = "development_qa_passed"

    rows: list[tuple] = []
    if fts_query:
        fts_table = "illustration_units_fts"
        id_col = "p.id" if mode == "production" else "u.id"
        joined = base_select + (" AND" if mode == "development" else " WHERE") + (
            f" {id_col} IN (SELECT rowid FROM {fts_table} WHERE {fts_table} MATCH ?)"
        )
        order_col = "u.id" if mode == "development" else "p.id"
        rows = connection.execute(joined + f" ORDER BY {order_col} DESC LIMIT ?", (fts_query, limit)).fetchall()

    if not rows:
        # No FTS matches (or no keywords at all) -- fall back to an
        # unfiltered, deterministic candidate window so Stage B still
        # has something to rank rather than failing before it even
        # starts. Ordered by id DESC (most recently added first).
        order_col = "u.id" if mode == "development" else "p.id"
        rows = connection.execute(base_select + f" ORDER BY {order_col} DESC LIMIT ?", (limit,)).fetchall()

    candidates = []
    for row in rows:
        (
            unit_id, title_hu, modern_hu_text, summary_hu, moral_hu,
            source_title, source_code, tradition, license_status,
        ) = row
        if not _verify_checksum(connection, unit_id):
            continue
        topics, tone, functions = _fetch_taxonomy(connection, unit_id)
        candidates.append(
            RetrievalCandidate(
                unit_id=unit_id, title_hu=title_hu, modern_hu_text=modern_hu_text,
                summary_hu=summary_hu, moral_hu=moral_hu, topics=topics, tone=tone,
                homiletic_functions=functions, source_title=source_title, source_code=source_code,
                tradition=tradition, license_status=license_status, provenance_status=provenance_status,
            )
        )
    return candidates


def build_ranking_prompt(
    *,
    passage_reference: str,
    passage_text: str,
    theme: str,
    occasion: str,
    candidates: list[RetrievalCandidate],
) -> str:
    candidate_blocks = "\n".join(
        f"[{c.unit_id}] title_hu: {c.title_hu} | summary_hu: {c.summary_hu} | "
        f"topics: {', '.join(c.topics) or '—'} | tone: {c.tone or '—'} | "
        f"homiletic_functions: {', '.join(c.homiletic_functions) or '—'}"
        for c in candidates
    )
    context_lines = [f"Igehely: {passage_reference or 'nincs megadva'}"]
    if passage_text.strip():
        context_lines.append(f"Bibliai szöveg (részlet): {passage_text.strip()[:800]}")
    if theme.strip():
        context_lines.append(f"Téma/kulcsszavak: {theme.strip()}")
    if occasion.strip():
        context_lines.append(f"Alkalom: {occasion.strip()}")
    context_block = "\n".join(context_lines)

    return f"""\
Te egy magyar református prédikációs illusztráció-ajánló asszisztens \
vagy. Az alábbi, MÁR ELKÉSZÜLT és ellenőrzött illusztráció-jelöltek \
közül kell kiválasztanod és rangsorolnod a legrelevánsabbakat -- TE MAGAD \
NEM ÍRSZ, NEM TALÁLSZ KI TÖRTÉNETET, kizárólag a megadott jelöltek közül \
választhatsz.

KONTEXTUS:
{context_block}

JELÖLTEK (kizárólag ezek közül választhatsz, az azonosítójuk szögletes \
zárójelben áll):
{candidate_blocks}

FELADAT:
- válaszd ki a {MIN_TOP_N}-{MAX_TOP_N} legrelevánsabb jelöltet a fenti kontextushoz \
  (textus, téma, alkalom) -- homiletikai használhatóság alapján;
- ha KEVESEBB, mint {MIN_TOP_N} jelölt valóban releváns, csak azokat add vissza, \
  amik ténylegesen kapcsolódnak -- ne told be a listát irreleváns \
  jelölttel csak a szám kitöltéséért;
- ha EGYETLEN jelölt sem releváns, adj vissza üres listát;
- KIZÁRÓLAG a fenti [ID] azonosítók egyikét használhatod -- SOHA ne adj \
  vissza olyan ID-t, ami nem szerepel a listában, és SOHA ne írj le új \
  történetet vagy tartalmat.

KIMENET -- KIZÁRÓLAG ezt a JSON alakot add vissza, más szöveg nélkül:
{{
  "results": [
    {{"unit_id": <a jelöltek közül választott egész szám>, "score": <0.0-1.0>, \
"reason": "1 mondatos magyarázat, miért releváns ehhez a textushoz/témához"}}
  ]
}}"""


def _extract_json_object(raw: str) -> dict | None:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    candidate = text[start : end + 1]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_ranking_response(raw: str, *, valid_ids: set[int]) -> list[RankedIllustration]:
    """Fail-closed: unparseable JSON, a missing/non-list `results` field,
    or a malformed entry all yield an EMPTY list (never a guess, never a
    replacement story). An entry naming an `unit_id` outside `valid_ids`
    is silently DROPPED -- the rest of a partially-valid response is
    still honored, but that one entry is never trusted."""
    payload = _extract_json_object(raw)
    if payload is None:
        return []
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []
    ranked: list[RankedIllustration] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        unit_id = item.get("unit_id")
        if not isinstance(unit_id, int) or unit_id not in valid_ids:
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        reason = str(item.get("reason", "")).strip()
        ranked.append(RankedIllustration(unit_id=unit_id, reason=reason, score=score))
    return ranked


def _source_attribution(candidate: RetrievalCandidate) -> str:
    parts = [candidate.source_title]
    if candidate.tradition:
        parts.append(candidate.tradition)
    return " · ".join(parts)


def retrieve_illustrations(
    connection,
    *,
    mode: RetrievalMode,
    passage_reference: str,
    llm_generate: Callable[[str], str],
    passage_text: str = "",
    theme: str = "",
    occasion: str = "",
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    top_n: int = DEFAULT_TOP_N,
) -> list[IllustrationRetrievalResult]:
    """The full two-stage pipeline. Returns an EMPTY list (never an
    exception, never a fabricated result) when: no candidates exist, the
    ranking response fails to parse, or the model finds nothing
    relevant. The caller is responsible for showing the user-facing
    "nem találtam megfelelő illusztrációt" message in that case."""
    query_text = " ".join(filter(None, [theme, passage_reference, occasion]))
    candidates = find_candidates(connection, query_text=query_text, mode=mode, limit=candidate_limit)
    if not candidates:
        return []

    prompt = build_ranking_prompt(
        passage_reference=passage_reference, passage_text=passage_text,
        theme=theme, occasion=occasion, candidates=candidates,
    )
    raw_response = llm_generate(prompt)
    ranked = parse_ranking_response(raw_response, valid_ids={c.unit_id for c in candidates})
    if not ranked:
        return []

    candidates_by_id = {c.unit_id: c for c in candidates}
    results: list[IllustrationRetrievalResult] = []
    for r in sorted(ranked, key=lambda x: -x.score)[:top_n]:
        c = candidates_by_id.get(r.unit_id)
        if c is None:
            continue
        results.append(
            IllustrationRetrievalResult(
                unit_id=c.unit_id, title_hu=c.title_hu, modern_hu_text=c.modern_hu_text,
                summary_hu=c.summary_hu, moral_hu=c.moral_hu, topics=c.topics, tone=c.tone,
                homiletic_functions=c.homiletic_functions, source_title=c.source_title,
                source_attribution=_source_attribution(c), provenance_status=c.provenance_status,
                rank_reason=r.reason, rank_score=r.score,
            )
        )
    return results


__all__ = [
    "ALLOWED_RETRIEVAL_MODES",
    "DEFAULT_CANDIDATE_LIMIT",
    "DEFAULT_TOP_N",
    "IllustrationRetrievalResult",
    "RankedIllustration",
    "RetrievalCandidate",
    "build_ranking_prompt",
    "find_candidates",
    "parse_ranking_response",
    "retrieve_illustrations",
]
