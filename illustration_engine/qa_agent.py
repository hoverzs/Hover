"""Phase 3H: automated content QA for illustration units.

A SECOND, independent LLM pass over an already-enriched unit -- judges
the enrichment against its own source, never trusts the enrichment
pipeline's own self-report. Same dependency-injection pattern as
`enrichment_pipeline.py`: the caller supplies `llm_generate: Callable[[str], str]`,
this module owns only prompt construction and response parsing, no
network code, no DB access.

Two layers of "provenance safety" that are NEVER delegated to the model:
- raw `original_text`/checksum immutability is enforced structurally
  (this module has no write path to `stories` at all);
- the model's own claim about faithfulness is ONE signal among the
  checklist criteria (`FAITHFULNESS_*` issue codes), not a substitute
  for the checksum-based structural check the caller performs itself.

Verdict states: PASS / NEEDS_ATTENTION / FAIL (see `QAVerdict`). Parsing
is fail-closed: a response that cannot be understood as a valid verdict
becomes a synthetic FAIL with a `QA_PARSE_ERROR` issue -- it is never
silently treated as PASS.

PHASE 3H.1 -- QA ISSUE AUTHORITY. Not every issue code is the LLM's to
decide. `STRATEGY_MISMATCH` (derivation_type vs. the length-derived
strategy) is a question code can answer exactly and cheaply
(`enrichment_pipeline.is_legacy_strategy_mismatch`) -- a real production
run showed the LLM QA judge gets this wrong often enough (a false
positive on a unit whose deterministic check was clean) that trusting
its own opinion here is actively harmful. So: `build_qa_prompt()`
deliberately does NOT ask the model to judge strategy correctness at
all (that checklist item and the JSON example's `STRATEGY_MISMATCH`
example are gone from the prompt); `run_content_qa()` computes the
deterministic answer itself and calls `reconcile_deterministic_strategy_issue()`
as its LAST step, which (a) drops any `STRATEGY_MISMATCH` issue the
model emits anyway despite the instruction, and (b) is the ONLY code
path that can ever add a `STRATEGY_MISMATCH` issue to a returned
`QAVerdict`. Every OTHER issue code (faithfulness, language quality,
title/summary/moral judgment, punchline/wordplay) stays a genuine LLM
semantic judgment -- code cannot evaluate those.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from illustration_engine.enrichment_pipeline import is_legacy_strategy_mismatch

ALLOWED_QA_VERDICT_STATUSES = frozenset({"PASS", "NEEDS_ATTENTION", "FAIL"})

# Known issue codes (Phase 3H brief) -- a model response is not REJECTED
# for using a code outside this set (an LLM's own phrasing may drift),
# but an unrecognized code is not silently trusted either; see
# `_normalize_issue_code`.
KNOWN_QA_ISSUE_CODES = frozenset(
    {
        "HALLUCINATED_DETAIL",
        "MEANING_SHIFT",
        "POOR_HUNGARIAN",
        "PUNCHLINE_LOST",
        "WORDPLAY_UNTRANSLATABLE",
        "FORCED_MORAL",
        "BAD_SUMMARY",
        "TITLE_PROBLEM",
        "STRATEGY_MISMATCH",
        "NAME_WARNING",
    }
)

# Phase 3H.1: STRATEGY_MISMATCH is excluded from the codes OFFERED to the
# LLM in build_qa_prompt -- it is deterministic-only (see module
# docstring). Still a member of KNOWN_QA_ISSUE_CODES because
# reconcile_deterministic_strategy_issue() itself constructs a QAIssue
# with this code -- it just never comes FROM the model.
_LLM_JUDGED_ISSUE_CODES = KNOWN_QA_ISSUE_CODES - {"STRATEGY_MISMATCH"}

# Content fields a repair pass is allowed to touch -- never original_text,
# never source/provenance, never derivation_type/status/human_reviewed_at.
REPAIRABLE_FIELDS = ("title_hu", "modern_hu_text", "summary_hu", "moral_hu")

QA_PROMPT_VERSION = "hu_illustration_qa_v1"


@dataclass(frozen=True)
class QAIssue:
    code: str
    detail: str


@dataclass(frozen=True)
class QAVerdict:
    status: str  # PASS | NEEDS_ATTENTION | FAIL
    confidence: float
    issues: tuple[QAIssue, ...]
    rationale: str


def _normalize_issue_code(raw: str) -> str:
    code = (raw or "").strip().upper().replace(" ", "_")
    return code if code in KNOWN_QA_ISSUE_CODES else (code or "UNSPECIFIED")


def _extract_json_object(raw: str) -> dict | None:
    """Same tolerance level as this repo's other `extract_json_object`
    implementations (markdown-fence stripping, trailing-comma repair) --
    reimplemented locally per this codebase's own convention (each
    `*_ai.py`/agent module owns its copy rather than sharing one)."""
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


def _parse_qa_verdict(raw_response: str) -> QAVerdict:
    payload = _extract_json_object(raw_response)
    if payload is None:
        return QAVerdict(
            status="FAIL",
            confidence=0.0,
            issues=(QAIssue(code="QA_PARSE_ERROR", detail="QA response was not valid/parseable JSON"),),
            rationale="fail-closed: could not parse the QA model's response",
        )

    status = str(payload.get("status", "")).strip().upper()
    if status not in ALLOWED_QA_VERDICT_STATUSES:
        return QAVerdict(
            status="FAIL",
            confidence=0.0,
            issues=(QAIssue(code="QA_PARSE_ERROR", detail=f"invalid/missing status: {status!r}"),),
            rationale="fail-closed: QA response had no valid status field",
        )

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    raw_issues = payload.get("issues", [])
    issues: list[QAIssue] = []
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if isinstance(item, dict):
                code = _normalize_issue_code(str(item.get("code", "")))
                detail = str(item.get("detail", "")).strip()
                issues.append(QAIssue(code=code, detail=detail))

    rationale = str(payload.get("rationale", "")).strip()
    return QAVerdict(status=status, confidence=confidence, issues=tuple(issues), rationale=rationale)


def build_qa_prompt(
    *,
    source_code: str,
    title_original: str,
    original_text: str,
    title_hu: str,
    modern_hu_text: str,
    summary_hu: str,
    moral_hu: str | None,
    tone: str | None,
    derivation_type: str,
    current_expected_mode: str,
    current_expected_derivation_type: str | None,
) -> str:
    """Builds the QA judge prompt. The model sees ONLY the original
    source and the already-generated Hungarian enrichment -- it never
    sees or is asked to touch original_text, checksum, or any DB field;
    provenance immutability is enforced structurally by the caller, not
    by this prompt."""
    strategy_line = (
        f"{current_expected_mode}/{current_expected_derivation_type}"
        if current_expected_derivation_type
        else current_expected_mode
    )
    moral_block = moral_hu if moral_hu else "(üres -- a moral_hu opcionális, ez önmagában NEM hiba)"
    issue_codes_list = ", ".join(sorted(_LLM_JUDGED_ISSUE_CODES))

    return f"""\
Te egy magyar református prédikációs illusztráció-adatbázis FÜGGETLEN \
minőségellenőre vagy. A feladatod egy MÁR ELKÉSZÜLT magyar enrichment \
kiértékelése az eredeti forrás alapján -- te magad NEM generálsz \
tartalmat, kizárólag ítéletet mondasz.

EREDETI FORRÁS (source_code: {source_code}):
---
title_original: {title_original}
{original_text}
---

ELKÉSZÜLT MAGYAR ENRICHMENT (ezt kell kiértékelned):
- title_hu: {title_hu}
- modern_hu_text: {modern_hu_text}
- summary_hu: {summary_hu}
- moral_hu: {moral_block}
- tone: {tone or "nincs megadva"}
- derivation_type (tárolt): {derivation_type} (kontextusnak: a rendszer szerinti jelenlegi elvárt stratégia {strategy_line} -- EZT a szempontot a rendszer külön, kód szinten ellenőrzi, TE ne foglalkozz vele, ld. lent)

ELLENŐRZÉSI SZEMPONTOK (mindegyiket vizsgáld):
1. FAITHFULNESS -- nincs kitalált személy, esemény, vagy megváltoztatott \
   jelentés; nincs kihagyott lényegi csattanó.
2. MAGYAR NYELVI MINŐSÉG -- természetes, nem gépies vagy félrefordított \
   mondat; a nevek/tulajdonnevek kezelése elfogadható.
3. TITLE_HU -- hű és használható cím.
4. SUMMARY_HU -- az eredeti történetet foglalja össze, nem talál ki új \
   értelmezést.
5. MORAL_HU -- opcionális; ha üres, ez NEM hiba; ha van megadva, valóban \
   következzen a történetből, és NE legyen ráerőltetett prédikációs \
   tanulság egy alapvetően humoros/ironikus/anekdotikus történetre.
6. CSATTANÓ / SZÓJÁTÉK -- ha a történet humoros vagy szójátékra épül, \
   ellenőrizd, hogy a csattanó/poén magyarul is megmaradt-e, \
   érthető-e.

FONTOS -- amit NE értékelj: a derivation_type/stratégia helyességét a \
rendszer determinisztikusan, kód szinten ellenőrzi, NEM a te feladatod. \
NE adj vissza "STRATEGY_MISMATCH" issue-t semmilyen körülmények között \
-- ha mégis megtennéd, a rendszer eldobja és a saját, kód szintű \
eredményével helyettesíti.

KIMENET -- KIZÁRÓLAG ezt a JSON alakot add vissza, más szöveg nélkül:
{{
  "status": "PASS | NEEDS_ATTENTION | FAIL",
  "confidence": <0.0-1.0 közötti szám, a saját ítéleted bizonyossága>,
  "issues": [
    {{"code": "ISMERT_KÓD_VAGY_LEÍRÓ_KÓD", "detail": "rövid, konkrét magyarázat"}}
  ],
  "rationale": "1-2 mondatos összegzés, miért ez a verdikt"
}}

Ismert issue code-ok, amiket TE adhatsz vissza (ne használd a \
STRATEGY_MISMATCH-et, az nem a tiéd): {issue_codes_list}.
Ha nincs probléma, "issues" legyen üres lista és "status" legyen "PASS". \
Ha csak apró, nem-blokkoló észrevétel van, "status" legyen \
"NEEDS_ATTENTION". Súlyos hűségi/jelentésbeli hiba esetén "FAIL"."""


def reconcile_deterministic_strategy_issue(
    verdict: QAVerdict,
    *,
    stored_derivation_type: str,
    current_expected_mode: str,
    current_expected_derivation_type: str | None,
) -> QAVerdict:
    """Phase 3H.1: THE only place a `QAVerdict` may carry a
    `STRATEGY_MISMATCH` issue. Runs `enrichment_pipeline.
    is_legacy_strategy_mismatch()` -- the same deterministic authority
    `illustration_review_ui.compute_review_risk` uses -- and reconciles
    it against whatever the model returned:

    - deterministic mismatch=True: ensures exactly one authoritative
      STRATEGY_MISMATCH issue is present (any the model added itself are
      discarded and replaced with this one, carrying a deterministic
      detail string), and the status is raised to at least
      NEEDS_ATTENTION if the model said PASS -- a real strategy mismatch
      can never be silently PASS. An existing NEEDS_ATTENTION/FAIL status
      is left alone (never downgraded).
    - deterministic mismatch=False: strips any STRATEGY_MISMATCH issue
      the model returned anyway (a false positive -- observed in a real
      production run). If that was the ONLY issue present, the status is
      recomputed to PASS; if other, genuine issues remain, the model's
      original status is kept unchanged."""
    is_mismatch = is_legacy_strategy_mismatch(
        stored_derivation_type=stored_derivation_type,
        expected_mode=current_expected_mode,
        expected_derivation_type=current_expected_derivation_type,
    )
    llm_issues = tuple(i for i in verdict.issues if i.code != "STRATEGY_MISMATCH")
    model_claimed_mismatch = len(llm_issues) != len(verdict.issues)

    if is_mismatch:
        expected = current_expected_mode
        if current_expected_derivation_type:
            expected = f"{current_expected_mode}/{current_expected_derivation_type}"
        detail = f"tárolt: {stored_derivation_type}, jelenlegi elvárás: {expected} (determinisztikus ellenőrzés)"
        issues = llm_issues + (QAIssue(code="STRATEGY_MISMATCH", detail=detail),)
        status = "NEEDS_ATTENTION" if verdict.status == "PASS" else verdict.status
        return QAVerdict(status=status, confidence=verdict.confidence, issues=issues, rationale=verdict.rationale)

    if not model_claimed_mismatch:
        return verdict  # nothing to reconcile
    status = "PASS" if not llm_issues else verdict.status
    return QAVerdict(status=status, confidence=verdict.confidence, issues=llm_issues, rationale=verdict.rationale)


def run_content_qa(
    *,
    source_code: str,
    title_original: str,
    original_text: str,
    title_hu: str,
    modern_hu_text: str,
    summary_hu: str,
    moral_hu: str | None,
    tone: str | None,
    derivation_type: str,
    current_expected_mode: str,
    current_expected_derivation_type: str | None,
    llm_generate,
) -> QAVerdict:
    prompt = build_qa_prompt(
        source_code=source_code,
        title_original=title_original,
        original_text=original_text,
        title_hu=title_hu,
        modern_hu_text=modern_hu_text,
        summary_hu=summary_hu,
        moral_hu=moral_hu,
        tone=tone,
        derivation_type=derivation_type,
        current_expected_mode=current_expected_mode,
        current_expected_derivation_type=current_expected_derivation_type,
    )
    raw_response = llm_generate(prompt)
    verdict = _parse_qa_verdict(raw_response)
    return reconcile_deterministic_strategy_issue(
        verdict,
        stored_derivation_type=derivation_type,
        current_expected_mode=current_expected_mode,
        current_expected_derivation_type=current_expected_derivation_type,
    )


def build_repair_prompt(
    *,
    source_code: str,
    title_original: str,
    original_text: str,
    title_hu: str,
    modern_hu_text: str,
    summary_hu: str,
    moral_hu: str | None,
    issues: tuple[QAIssue, ...],
) -> str:
    """Repair is CONTENT-ONLY: the model may rewrite title_hu/
    modern_hu_text/summary_hu/moral_hu, and MUST echo original_text back
    unchanged in spirit (it is not given a way to change it -- there is
    no field for it in the output contract). derivation_type/strategy
    issues (STRATEGY_MISMATCH) are explicitly called out as NOT
    repairable this way."""
    issues_block = "\n".join(f"- [{i.code}] {i.detail}" for i in issues) or "(nincs konkrét issue megadva)"
    return f"""\
Te egy magyar református prédikációs illusztráció-adatbázis JAVÍTÓ \
asszisztense vagy. Egy független minőségellenőr az alábbi problémákat \
találta egy már elkészült magyar enrichmentben. A feladatod: JAVÍTSD ki \
ezeket, az eredeti forrás alapján -- SOHA nem térhetsz el az eredeti \
forrás tartalmától, nem adhatsz hozzá új szereplőt/eseményt/tanulságot.

EREDETI FORRÁS (source_code: {source_code}, VÁLTOZATLAN, nem szerkesztheted):
---
title_original: {title_original}
{original_text}
---

JELENLEGI (javítandó) ENRICHMENT:
- title_hu: {title_hu}
- modern_hu_text: {modern_hu_text}
- summary_hu: {summary_hu}
- moral_hu: {moral_hu or "(üres)"}

TALÁLT PROBLÉMÁK:
{issues_block}

FONTOS KORLÁTOK:
- csak title_hu, modern_hu_text, summary_hu, moral_hu javítható;
- a derivation_type/stratégia (STRATEGY_MISMATCH típusú probléma) NEM \
  javítható ezzel a lépéssel -- ha ilyen problémát látsz, azt hagyd \
  figyelmen kívül, csak a tartalmi problémákat javítsd;
- moral_hu opcionális marad -- ha a történetnek természeténél fogva \
  nincs tanulsága, hagyd üresen (null), NE találj ki egyet csak azért, \
  hogy a mező ki legyen töltve;
- ha egy mezőn nincs mit javítani, add vissza változatlanul.

KIMENET -- KIZÁRÓLAG ezt a JSON alakot add vissza, más szöveg nélkül:
{{
  "title_hu": "...",
  "modern_hu_text": "...",
  "summary_hu": "...",
  "moral_hu": "... vagy null"
}}"""


def run_repair(
    *,
    source_code: str,
    title_original: str,
    original_text: str,
    title_hu: str,
    modern_hu_text: str,
    summary_hu: str,
    moral_hu: str | None,
    issues: tuple[QAIssue, ...],
    llm_generate,
) -> dict | None:
    """Returns the repaired {"title_hu","modern_hu_text","summary_hu",
    "moral_hu"} dict, or None if the repair response could not be parsed
    (fail-closed: no repair applied rather than guessing)."""
    prompt = build_repair_prompt(
        source_code=source_code,
        title_original=title_original,
        original_text=original_text,
        title_hu=title_hu,
        modern_hu_text=modern_hu_text,
        summary_hu=summary_hu,
        moral_hu=moral_hu,
        issues=issues,
    )
    raw_response = llm_generate(prompt)
    payload = _extract_json_object(raw_response)
    if payload is None:
        return None
    required = ("title_hu", "modern_hu_text", "summary_hu")
    if not all(isinstance(payload.get(f), str) and payload.get(f).strip() for f in required):
        return None
    moral = payload.get("moral_hu")
    if moral is not None and not isinstance(moral, str):
        return None
    return {
        "title_hu": payload["title_hu"],
        "modern_hu_text": payload["modern_hu_text"],
        "summary_hu": payload["summary_hu"],
        "moral_hu": moral,
    }


__all__ = [
    "ALLOWED_QA_VERDICT_STATUSES",
    "KNOWN_QA_ISSUE_CODES",
    "QA_PROMPT_VERSION",
    "REPAIRABLE_FIELDS",
    "QAIssue",
    "QAVerdict",
    "build_qa_prompt",
    "build_repair_prompt",
    "reconcile_deterministic_strategy_issue",
    "run_content_qa",
    "run_repair",
]
