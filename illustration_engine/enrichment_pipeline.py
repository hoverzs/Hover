"""Controlled Hungarian enrichment pipeline for `illustration_units`
(Phase 3B pilot).

Architecture, mirroring this repo's established AI-module convention
(see `hymn_recommendation_ai.py`'s `llm_generate: Callable[[str], str]`
dependency-injection pattern, and the `extract_json_object` helper
duplicated across every `*_ai.py` module rather than shared — this
module owns its own copy for the same reason: illustration_engine stays
a fully self-contained package, never importing from or being imported
by app.py/bible_engine/the hymn system):

- `llm_generate: Callable[[str], str]` is injected by the CALLER (a
  future pilot-runner script or, eventually, an app.py-side caller —
  neither exists yet). This module never imports google.generativeai,
  never reads an API key, never makes a network call itself. Tests
  inject a trivial mock function.
- `enrich_story()` is the single entry point: loads one story (read-
  only), builds the prompt, calls `llm_generate`, parses/validates the
  JSON response, and — depending on the response's own declared `mode`
  — either writes ONE draft `illustration_unit` (mode="direct_unit",
  landing at `status="needs_review"`, never further) or returns a
  read-only list of proposed units for human review WITHOUT writing
  anything to `illustration_units` (mode="unit_proposal" — see the
  Phase 3B brief's explicit long-story safety requirement).
- Every DB write goes through the existing Phase 3A
  `illustration_unit_repository`/`illustration_sqlite` functions — this
  module contains no raw SQL of its own and no INSERT/UPDATE against
  `stories` or `sources` at all. That is what makes "original_text/
  title_original/source_reference can never be touched by enrichment"
  and "a human-reviewed unit can never be silently overwritten" true
  here: those guarantees live in the schema/repository layer (Phase 3A)
  and this module simply has no code path around them.

GUARDS (Phase 3B brief §9), all fail-closed (a failed guard produces
`EnrichmentResult(status="rejected", errors=(...))` — nothing is ever
written to the DB on a guard failure):
1. JSON parsing (`_extract_json_object`) — markdown-fence-tolerant,
   trailing-comma-tolerant, same tolerance level as this repo's other
   `extract_json_object` implementations.
2. Structural/schema validation — required keys present and non-empty.
3. Controlled vocabulary — topics/tone/homiletic_functions/
   narrative_status/narrative_status_confidence/derivation_type must
   all be members of the fixed pilot lists (§5) or the Phase 3A DB
   enums; the model can never invent a new tag or status value.
4. `summary_hu` word count (40-100 words).
5. `title_hu`/`modern_hu_text` non-empty.
6. `source_span_start`/`source_span_end` bounds validation (only
   meaningful/required for `extracted_scene`; mirrors the DB's own
   CHECK constraints).
7. A simple proper-noun hallucination guard — see `_hallucination_guard`.
8. `source_reference`/story provenance — NOT a guard, a structural
   impossibility: this module has no function that writes to `stories`
   at all, and the JSON contract has no field for it.
9. `original_text` immutability — same: no write path exists.
10. Human-reviewed overwrite protection — inherited unchanged from
    Phase 3A (`update_illustration_unit_fields`'s
    `IllustrationUnitReviewProtectionError`); this module catches it
    and turns it into `status="rejected"` rather than letting a batch
    run crash on one already-reviewed story.

FOLLOW-UP HARDENING (post-review, before any real LLM call):

- **`expected_mode` is caller-declared, not LLM-decided.** The model's
  own `"mode"` field is no longer trusted to decide whether a write
  happens — the CALLER states up front (`expected_mode="direct_unit"`
  or `"unit_proposal"`) which mode this particular story is allowed to
  use. If the model's response mode doesn't match, the result is
  `rejected` before either handler runs, so NO DB write is possible —
  this is what makes it safe to pass `expected_mode="unit_proposal"`
  for the long-story stress case and know a persistence write can never
  happen no matter what the model returns.
- **Tag sync, not tag accumulation.** `_sync_pilot_tags` replaces (not
  adds to) a unit's pilot-controlled (`topic`/`tone`/`function`) tags on
  every run — a re-run with a different `topics` list leaves exactly
  the new set attached, not the union of old and new. It only ever
  touches tags whose `(category, slug)` is a member of this module's
  own controlled lists (`PILOT_TOPICS`/`PILOT_TONES`/
  `PILOT_HOMILETIC_FUNCTIONS`) — a tag some other, non-pilot mechanism
  attached is left alone even if it happens to share a category name.
- **Atomic direct-unit persistence.** The create/get -> content update
  -> tag sync -> mark_needs_review sequence in `_handle_direct_unit`
  runs inside an explicit SQL SAVEPOINT. Any exception during that
  sequence rolls back ONLY this call's changes (via `ROLLBACK TO
  SAVEPOINT`, not a blanket `connection.rollback()`, which would also
  discard any unrelated uncommitted work a batch caller might have
  pending on the same connection) and returns `status="rejected"` — no
  half-written unit, no partial tag set, no stale content update can
  ever be observed by a caller that inspects the DB after a rejected
  result, whether or not the caller later calls `commit()`.
- **Hallucination guard narrowed** (see `_hallucination_guard`): now
  matches in ONE direction only (a Hungarian candidate must start with
  a real source word — matching Hungarian's own suffix-appends-after-
  the-stem morphology) against a source-word pool restricted to
  CAPITALIZED source tokens only (not every lowercase common word).
  This closes two false-negative holes found on audit: a short
  hallucinated name no longer slips through just because it happens to
  prefix a longer, unrelated capitalized source word (the OLD
  bidirectional check allowed this); and it can no longer accidentally
  "pass" by prefix-matching an ordinary lowercase common word. This
  stays a coarse, lightweight tripwire, NOT a real NER/hallucination-
  detection system — see the function's own docstring for what it still
  cannot catch (e.g. a translated place name/demonym, or a genuinely
  invented name that happens to start with a real short capitalized
  source word).

FINDINGS FROM THE PHASE 3C LIVE SMOKE PILOT (5 real Claude-generated
stories), fixed here before the full 25-story pilot:

- **Sentence-boundary false positive.** `_SENTENCE_SPLIT_RE` only
  recognized `.!?…` immediately followed by whitespace as a sentence
  boundary. Dialogue overwhelmingly ends "word.”" (terminal punctuation,
  THEN a closing curly quote, THEN the space) — that quote character
  defeated the boundary check, so the next sentence's genuinely
  sentence-initial word was treated as mid-sentence and wrongly checked
  by the hallucination guard. This is exactly how the real pilot
  rejected a valid story over the Hungarian article "Egy" (not a proper
  noun at all). Fixed with a minimal extension — a small, fixed set of
  closing punctuation characters allowed between the terminal mark and
  the whitespace — not a general NLP sentence segmenter.
- **Name completion is now an explicit prompt rule, not just a guard
  side-effect.** The real pilot's OTHER rejection (adding "Alexander"
  to a source that only ever wrote "Pope") was actually a CORRECT guard
  catch, but relying on the guard alone to catch this is fragile (the
  guard only catches a NEW capitalized token, not e.g. a title/rank
  silently expanded into a full name using a lowercase or already-
  present surname). `build_enrichment_prompt` now states outright,
  covering `title_hu`/`modern_hu_text`/`summary_hu`/`moral_hu`: never
  complete a name from outside knowledge, regardless of whether the
  completion happens to be factually correct.
- **`narrative_status` provenance discipline is now an explicit prompt
  rule.** Nothing in the schema or the pipeline could previously stop
  the model from using its own general historical knowledge (e.g.
  "Voltaire was really beaten in the Chevalier de Rohan affair") to
  decide how confidently a SPECIFIC anecdote should be classified —
  the classification must come only from `original_text` and the
  source metadata already in the prompt, never from the model's
  training-data knowledge about the named figures. The prompt now
  states this explicitly, using the Voltaire/Rohan case itself (found
  during the live pilot's own narrative_status output) as the
  illustrative example of what NOT to do. Deliberate architectural
  boundary, stated here rather than solved with more code: a genuine
  historical-fact-verification pipeline, if ever wanted, must be a
  separate, sourced research/enrichment pipeline — this one is not
  extended to attempt it.
- **A single typo ("önteltségééért") found in the live pilot's
  Hungarian output was audited for a lightweight, deterministic sanity
  check** (no spellchecker, no new dependency). A narrow, plausible
  candidate exists — flagging a doubled identical accented vowel
  letter within one word (e.g. "éé", "óó"), which is not valid in
  standard Hungarian orthography — but this was deliberately NOT
  implemented: one incidental typo from one run is not yet a
  demonstrated pattern, and adding a new rejecting guard on that basis
  would itself be the kind of speculative heuristic this project
  avoids. Left as a human-review task; documented here so the option
  is not lost if a real pattern emerges later. CORRECTION: this
  specific typo claim was itself wrong on review — "önteltségéért" is
  correct Hungarian (a possessed noun + the "-ért" postposition
  regularly doubles the accented vowel, as in the common word
  "kedvéért"), not a typo. No actual quality defect was found in the
  first pilot run's Hungarian text; the sanity-check idea above is kept
  only as a documented (and now known-questionable) option, not a
  finding that motivates anything.

FURTHER NARRATIVE_STATUS TIGHTENING (second follow-up, before the full
25-story pilot): the pilot's own `legend_about_historical_figure`
classification for the Voltaire "Justice" story turned out to still be
under-justified — "real historical person + old anecdote + punchline +
unverifiable" is NOT sufficient evidence for "legend" any more than it
is for "documented event"; both require the SAME kind of explicit
textual/provenance support. `legend_about_historical_figure`
now requires the source itself to identify the material as legendary
(e.g. an editor's preface using the words "legend"/"legendary"/
"traditional legend") — otherwise the conservative fallback is
`traditional_anecdote`. Source-aware defaults were also added (English
Jests -> traditional_anecdote, Aesop -> fable, Hungarian folktale
sources -> folktale, Hebrew Tales -> rabbinic_aggadic_tale, Gulistan ->
didactic_tale), with an explicit caution that Baldwin's preface
documenting a "half-legendary" character for the COLLECTION as a whole
must not be auto-applied to every individual Baldwin story.

PHASE 3C-c: the 25-story run itself must be described precisely — it was
a **diagnostic / curated pilot run**, not an untouched live-LLM pass:
several composed outputs were hand-edited during pre-flight specifically
to route around the (then single-tier) hallucination guard before the
real `enrich_story()` call, e.g. keeping "England"/"Scotland" untranslated
or lower-casing "ördög". That editing is exactly what motivated the two
changes below — it should not recur as a normal part of running this
pipeline.

TWO-TIER PROPER-NOUN GUARD (this section) — `_hallucination_guard` used
to have exactly one severity: any unmatched capitalized candidate was a
hard rejection, full stop. The 25-story pilot showed this conflates two
very different situations under one penalty:

- A genuinely invented identifying token glued onto a real, kept source
  name (source "Pope" -> output "Alexander Pope") — an actual,
  correctness-relevant hallucination.
- A correct Hungarian TRANSLATION of a source concept whose spelling
  simply doesn't resemble the English source word (God -> Isten,
  Devil -> Ördög, England -> Anglia, Scotland -> Skócia, France ->
  Franciaország, Ireland -> Írország) — not a hallucination at all.

Hand-maintaining a translation dictionary to whitelist the second case
was explicitly rejected (it only grows, never closes) — instead,
`_hallucination_guard` now uses a structural signal already present in
its own token stream: an unmatched candidate ADJACENT to a matched one
(the name-completion shape) is a hard reject; an unmatched candidate
with no such neighbor is a warning only. See `_hallucination_guard`'s
own docstring for the full reasoning and accepted limitations.
`EnrichmentResult` and `ProposedUnit` gained a `warnings` field so this
new, non-fatal tier is actually visible to a caller/reviewer rather than
silently dropped.

PROPOSAL CONTRACT (this section) — `unit_proposal` mode used to require
the SAME full `modern_hu_text`/`moral_hu` as `direct_unit`. On the
25-story pilot's own long-story stress case (412, King John and the
Abbot: ~6170-char source), this produced a ~5775-char "proposal" — in
substance a full translation already done, defeating the entire point of
proposing-before-generating (deciding WHICH unit(s) a long story should
become before spending tokens writing any of them). `unit_proposal` no
longer requires (or even accepts as meaningful — a returned
`ProposedUnit.modern_hu_text` is always `None`) `modern_hu_text`/
`moral_hu`. A `condensed_story` proposal instead states
`target_length_chars`, an estimate for a LATER, human-approved generation
pass to aim for. The pipeline: long source -> AI unit proposal (title,
summary, tags, narrative_status, rationale, target length) -> human
accept/reject -> only THEN, for an accepted proposal, a separate future
call generates the real `modern_hu_text`. That generation step does not
exist yet in this module — out of scope here, same as before.

PHASE 3D.1 (this section) — two changes, both prompted by findings from
the Phase 3D UNTOUCHED 25-story pilot (no pre-flight editing between LLM
output and validation):

**Proper-name guard is now warning-only.** The adjacency-based hard
reject (previous section) itself turned out to have a real false-reject
mode: "Ádámnak Lumley" and "North Írországgal" are both genuinely correct
translations that simply landed next to a real, matched source name by
ordinary sentence word order — not name-completion at all — and were
hard-rejected anyway (2 of 24 direct_unit attempts, ~8%, in the untouched
pilot). The guard cannot reliably tell "invented name glued onto a kept
one" apart from "unrelated correct word that happens to sit next to a
name" — so it no longer tries to. `_hallucination_guard` now ONLY
produces warnings (a higher-priority "SUSPICIOUS NAME EXPANSION" one for
the adjacency shape, a generic one otherwise) — see its own docstring.
Fail-closed correctness moves entirely to the human-review gate: a
warned unit still only ever reaches `needs_review`, never
`approved`/`published` automatically. Hard rejection is now reserved for
deterministically provable contract violations only: unparseable JSON,
missing/invalid required fields, a forbidden enum value, an invalid
source span, a length-window violation, or a mode/derivation_type
mismatch against the canonical strategy (below) — never a token-level
name heuristic.

Also added: `_fold_diacritics` (Unicode NFKD decomposition + combining-
mark stripping) closes the specific "Ádám"/"Alfréd"/"Orléans" class of
false positive — a genuine accent-only spelling difference from the
ASCII source word — WITHOUT any translation dictionary. A real semantic
translation (János/Anglia/Isten) shares no letters with its English
source word even after folding, so those still warn exactly as before;
this is normalization, not translation.

**Deterministic length strategy.** `derive_enrichment_strategy(length)`
is now the single canonical authority for which `expected_mode` AND (for
`direct_unit`) which `expected_derivation_type` a story is eligible for,
based purely on `len(story.original_text)`:
- <= 1500 chars -> `direct_unit` / `full_story_translation`.
- 1501-3000 chars -> `direct_unit` / `condensed_story`, with
  `modern_hu_text` itself required to land in
  `[_MIN_CONDENSED_MODERN_TEXT_CHARS, _MAX_CONDENSED_MODERN_TEXT_CHARS]`
  (currently 200-1500, the same retrieval-ready window as
  `target_length_chars` for proposals).
- > 3000 chars -> `unit_proposal` (unchanged from Phase 3C-c).

The caller still supplies `expected_mode` explicitly to `enrich_story` —
that safety contract (a batch runner asserting up front "this story may
only ever write directly, never propose," or vice versa) is unchanged
and still valuable — but it is now VALIDATED against
`derive_enrichment_strategy`'s output rather than trusted outright. A
mismatched caller `expected_mode` is a configuration error, rejected
BEFORE `llm_generate` is ever called — no LLM call, no tokens spent, no
`raw_response` to even parse. Within `direct_unit`, the LLM's own
`derivation_type` is validated the same way `mode` always was: it must
equal the ONE value the strategy computed, not merely be "one of the two
generally-valid direct_unit types" — the model is told exactly which one
to produce (`build_enrichment_prompt`'s `expected_derivation_type`
parameter), and a mismatch is rejected with zero DB writes, mirroring
`expected_mode` enforcement exactly.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from illustration_engine.illustration_sqlite import (
    ALLOWED_NARRATIVE_STATUS_CONFIDENCE,
    ALLOWED_NARRATIVE_STATUSES,
    PILOT_HOMILETIC_FUNCTIONS,
    PILOT_TONES,
    PILOT_TOPICS,
    IllustrationUnitReviewProtectionError,
)
from illustration_engine.illustration_unit_repository import (
    attach_tag_to_unit,
    create_draft_unit,
    detach_tag_from_unit,
    get_or_create_tag,
    mark_needs_review,
    update_draft_unit,
)


DEFAULT_PROMPT_VERSION = "hu_illustration_enrichment_pilot_v1"

# Phase 3G-A: PILOT_TOPICS/PILOT_TONES/PILOT_HOMILETIC_FUNCTIONS now live
# in illustration_sqlite.py (the shared, lower-level module both this
# file and illustration_unit_repository.py already import from) —
# re-exported here unchanged so every existing caller/test that does
# `from illustration_engine.enrichment_pipeline import PILOT_TOPICS`
# keeps working. See illustration_sqlite.py's own comment for why.

_PROPOSAL_DERIVATION_TYPES = frozenset({"extracted_scene", "condensed_story"})

# Which text fields _validate_common_fields requires to be non-empty --
# direct_unit still needs title_hu/modern_hu_text/summary_hu; unit_proposal
# (Phase 3C-c PROPOSAL CONTRACT) deliberately does NOT require
# modern_hu_text or moral_hu, since a proposal's job is only to decide WHAT
# unit could be made, not to write it. moral_hu is DELIBERATELY excluded
# here even for direct_unit (Phase 3G-B3 optional moral policy) -- not
# every source story carries a natural moral/lesson (many pilot anecdotes
# are purely humorous/ironic/punchline-driven), and forcing one invented a
# tacked-on "lesson" that wasn't in the source. moral_hu may still be
# filled in when the story genuinely warrants it; see moral_rules_section
# in build_enrichment_prompt() for the exact instruction given to the
# model, and _validate_common_fields' separate, permissive moral_hu type
# check (null/empty/any string all valid, only a non-string/non-null type
# is rejected).
_DIRECT_UNIT_REQUIRED_TEXT_FIELDS = ("title_hu", "modern_hu_text", "summary_hu")
_PROPOSAL_TEXT_FIELDS = ("title_hu", "summary_hu")

# A retrieval-ready illustration unit is meant to be a short, directly
# tellable pulpit illustration -- NOT a condensed-but-still-substantial
# translation of the whole source. Phase 3C-c follow-up: the original
# "just shorter than the source" rule alone let a 6000-char source pair
# with a 5800-char "condensed" proposal, i.e. almost no condensing at
# all -- exactly the problem the target_length_chars field exists to
# prevent. These bounds mirror the range real full_story_translation
# units landed in during the 25-story pilot (204-2395 chars, median 395).
_MIN_TARGET_LENGTH_CHARS = 200
_MAX_TARGET_LENGTH_CHARS = 1500

ALLOWED_MODES: frozenset[str] = frozenset({"direct_unit", "unit_proposal"})

# Phase 3D.1 DETERMINISTIC LENGTH STRATEGY (see module docstring): the ONLY
# authority for which expected_mode/expected_derivation_type a story is
# eligible for is len(story.original_text) -- neither the LLM nor the
# caller decides this. The caller still supplies expected_mode explicitly
# (an unchanged, valuable safety contract — see enrich_story()), but it is
# now VALIDATED against derive_enrichment_strategy()'s output rather than
# trusted outright; a mismatch is a caller/configuration error, rejected
# before the LLM is ever called.
_MAX_FULL_TRANSLATION_CHARS = 1500
_MAX_CONDENSED_DIRECT_CHARS = 3000
# The band-B (direct_unit/condensed_story) length window for the
# generated modern_hu_text itself -- deliberately the SAME range as
# target_length_chars for unit_proposal's condensed_story (Phase 3C-c):
# a retrieval-ready illustration unit is short and directly tellable,
# never "almost the whole source, just barely shorter."
_MIN_CONDENSED_MODERN_TEXT_CHARS = _MIN_TARGET_LENGTH_CHARS
_MAX_CONDENSED_MODERN_TEXT_CHARS = _MAX_TARGET_LENGTH_CHARS


@dataclass(frozen=True)
class EnrichmentStrategy:
    expected_mode: str
    # None only for unit_proposal -- a proposal's own derivation_type
    # (extracted_scene vs condensed_story) remains the model's structural
    # judgment call about the SOURCE story, not something length alone
    # can determine.
    expected_derivation_type: str | None


def derive_enrichment_strategy(original_text_length: int) -> EnrichmentStrategy:
    """The single, canonical source of truth for which mode and (for
    direct_unit) derivation_type a story is eligible for, based purely on
    the character length of its original_text. Callers, this module's own
    `enrich_story()`, and the LLM must all defer to this — it is never
    recomputed differently in more than one place.

    - length <= 1500  -> direct_unit / full_story_translation (full,
      faithful translation of a short story).
    - 1501 <= length <= 3000 -> direct_unit / condensed_story (the model
      still writes the unit directly, but modern_hu_text must itself land
      in the [200, 1500]-char retrieval-ready range — see
      _MIN_CONDENSED_MODERN_TEXT_CHARS/_MAX_CONDENSED_MODERN_TEXT_CHARS).
    - length > 3000 -> unit_proposal (too long to safely commit to one
      direct translation without a human first deciding WHAT unit(s) the
      story should become — see the PROPOSAL CONTRACT module-docstring
      section)."""
    if original_text_length <= _MAX_FULL_TRANSLATION_CHARS:
        return EnrichmentStrategy(expected_mode="direct_unit", expected_derivation_type="full_story_translation")
    if original_text_length <= _MAX_CONDENSED_DIRECT_CHARS:
        return EnrichmentStrategy(expected_mode="direct_unit", expected_derivation_type="condensed_story")
    return EnrichmentStrategy(expected_mode="unit_proposal", expected_derivation_type=None)


def is_legacy_strategy_mismatch(
    *, stored_derivation_type: str, expected_mode: str, expected_derivation_type: str | None
) -> bool:
    """Phase 3H.1: THE single, canonical authority for whether a unit's
    stored `derivation_type` conflicts with what `derive_enrichment_
    strategy()` currently dictates for its story's length -- moved here
    (next to `derive_enrichment_strategy` itself) from a private,
    duplicated copy in `illustration_review_ui.py`'s reviewer-risk
    triage, and now ALSO the sole source `qa_agent.run_content_qa` uses
    to decide the STRATEGY_MISMATCH issue (see that module's docstring
    for why this must never be an LLM judgment call). Both callers pass
    `expected_mode`/`expected_derivation_type` as already computed by
    `derive_enrichment_strategy(len(original_text))` — this function
    itself does no length math, only the mode/derivation_type
    comparison.

    - `expected_mode == "direct_unit"`: mismatch iff the stored
      `derivation_type` isn't exactly what length now dictates (a
      full_story_translation/condensed_story mix-up).
    - `expected_mode == "unit_proposal"`: a stored `full_story_
      translation` or `condensed_story` IS a mismatch -- both mean "the
      whole story was translated/condensed as ONE direct unit," which
      today's rules no longer allow past the length threshold. A stored
      `extracted_scene` is deliberately NOT flagged -- it is itself
      proposal-derived content, i.e. already the correct shape for a
      long story under current rules."""
    if expected_mode == "direct_unit":
        return stored_derivation_type != expected_derivation_type
    return stored_derivation_type in ("full_story_translation", "condensed_story")


# Which (category, controlled-slug-set) pairs this pipeline is allowed to
# synchronize on a unit — see `_sync_pilot_tags`. A tag whose category
# isn't a key here, or whose slug isn't in the matching set, is left
# alone even if some other mechanism attached it to the same unit.
_PILOT_CONTROLLED_TAG_CATEGORIES: dict[str, frozenset[str]] = {
    "topic": PILOT_TOPICS,
    "tone": PILOT_TONES,
    "function": PILOT_HOMILETIC_FUNCTIONS,
}

_SUMMARY_MIN_WORDS = 40
_SUMMARY_MAX_WORDS = 100

# Simple hallucination guard: a capitalized, non-sentence-initial "word"
# in the Hungarian output that does not appear (case-insensitively)
# anywhere in the source original_text is flagged as a possibly invented
# proper noun. KNOWN, ACCEPTED LIMITATION (documented, not silently
# swept under the rug): a translated place name/demonym (e.g. "Anglia"
# for "England") will also match this pattern and can produce a false
# positive — this is deliberately a coarse tripwire, not a translation-
# aware NER system; every enrichment output lands in needs_review for
# human review regardless, so a false rejection here just means a human
# re-runs or hand-corrects it, never that bad content silently ships.
_CANDIDATE_PROPER_NOUN_RE = re.compile(r"[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű'\-]{2,}")
# Allows a closing quote/apostrophe/bracket BETWEEN the terminal
# punctuation and the following whitespace — e.g. '...canals.” Egy
# ismerőse...' — before this fix, the lookbehind only matched
# whitespace immediately after .!?…, so a sentence ending in a closing
# curly quote (extremely common: dialogue almost always ends "word.”")
# was never recognized as a boundary. The whole rest of that quoted
# sentence was then treated as a continuation of the PRECEDING sentence,
# so the first word after the quote landed at a non-zero position and
# got checked by the hallucination guard even though it was genuinely
# sentence-initial — this is exactly the "Egy" (Hungarian indefinite
# article) false positive found on the first real pilot run (Phase 3C).
# Deliberately minimal: a small, fixed set of closing punctuation
# characters, not a general NLP sentence segmenter.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])[\"'’”)\]]*\s+|\n+")


@dataclass(frozen=True)
class ProposedUnit:
    """One AI-proposed illustration unit from a `mode="unit_proposal"`
    response. NEVER written to the DB by this module — purely a return
    value for a human (or a later, separately-approved phase) to act
    on."""

    derivation_type: str
    source_span_start: int | None
    source_span_end: int | None
    title_hu: str
    # modern_hu_text/moral_hu are deliberately None for every proposal (see
    # the Phase 3C-c "PROPOSAL CONTRACT" module-docstring section) -- full
    # Hungarian illustration text is generated only after a human accepts
    # a specific proposed unit, never speculatively for every candidate.
    modern_hu_text: str | None
    summary_hu: str
    moral_hu: str | None
    topics: tuple[str, ...]
    tone: str
    homiletic_functions: tuple[str, ...]
    narrative_status: str
    narrative_status_confidence: str
    rationale: str | None
    standalone_reason: str | None
    # Only set (and only meaningful) for derivation_type="condensed_story":
    # a rough character-count estimate for the modern_hu_text a LATER,
    # human-approved generation pass would aim for -- never used to
    # generate text now.
    target_length_chars: int | None = None


@dataclass(frozen=True)
class EnrichmentResult:
    status: str  # "unit_created" | "proposal_ready" | "rejected"
    story_id: int
    unit_id: int | None = None
    proposed_units: tuple[ProposedUnit, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    # Non-fatal hallucination-guard findings (see _hallucination_guard --
    # entirely warning-only as of Phase 3D.1) -- present alongside a
    # "unit_created" or "proposal_ready" result, never causes rejection by
    # itself. Meant to be surfaced to a human reviewer, not acted on
    # automatically.
    warnings: tuple[str, ...] = field(default_factory=tuple)
    raw_response: str | None = None


@dataclass(frozen=True)
class _LoadedStory:
    id: int
    source_id: int
    title_original: str
    original_text: str
    source_code: str
    tradition: str | None


def enrich_story(
    connection: sqlite3.Connection,
    *,
    story_id: int,
    llm_generate: Callable[[str], str],
    model_identifier: str,
    expected_mode: str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    unit_index: int = 1,
    allow_overwrite_reviewed: bool = False,
) -> EnrichmentResult:
    """Runs one story through the enrichment pipeline.

    `expected_mode` (required, must be `"direct_unit"` or
    `"unit_proposal"`) is decided by the CALLER ahead of time, NOT by
    the model's own response — a post-review hardening requirement: the
    pilot's normal 1:1 stories are always called with
    `expected_mode="direct_unit"`; the long-story stress case is always
    called with `expected_mode="unit_proposal"`. If the model's response
    declares a DIFFERENT `mode` than what the caller expected, the
    result is `rejected` before either the direct-unit or the proposal
    handler runs — so a model that (say) tries to slip a direct write in
    for a story the caller only authorized a proposal for gets no write
    at all, not even a partial one. This is what makes "the persistence
    decision is never left to the LLM" an enforced property rather than
    a prompt-level request.

    Read-only against `stories`/`sources`. Writes to `illustration_units`
    ONLY in the `mode="direct_unit"` case (and only when it also matches
    `expected_mode`), and only ever as far as `status="needs_review"` —
    this function has no way to set `approved` or `published` (see
    `illustration_unit_repository.mark_needs_review`, which is the only
    status-transition helper it calls).

    `unit_index` defaults to 1 (single-unit-per-story is the pilot's
    normal case); pass a different value to enrich a second/third unit
    for the same story without colliding on `UNIQUE(story_id,
    unit_index)`. Idempotent: re-running with the same `unit_index`
    against an existing draft/needs_review unit updates it in place
    (via `create_draft_unit`'s natural UNIQUE-violation-avoidance path,
    see `_create_or_get_unit_id`) rather than erroring or duplicating;
    against an already-reviewed unit it raises the same
    `IllustrationUnitReviewProtectionError`-derived rejection as any
    other `update_draft_unit` call would, unless
    `allow_overwrite_reviewed=True`.
    """
    if expected_mode not in ALLOWED_MODES:
        raise ValueError(f"expected_mode must be one of {sorted(ALLOWED_MODES)}, got {expected_mode!r}")

    story = _load_story(connection, story_id)
    if story is None:
        return EnrichmentResult(status="rejected", story_id=story_id, errors=("story not found",))

    # Phase 3D.1: derive_enrichment_strategy(), not the caller's
    # expected_mode, is the canonical authority for which mode/
    # derivation_type this story is eligible for. The caller's
    # expected_mode is still a required, valuable safety contract (it is
    # what lets a batch runner assert up front "this story may only ever
    # write directly, never propose" or vice versa), but it is now
    # VALIDATED against the length-derived strategy rather than trusted
    # outright — a caller that gets the length band wrong is a
    # configuration error, caught here, BEFORE the LLM is ever called (no
    # tokens spent, no raw_response to even parse).
    strategy = derive_enrichment_strategy(len(story.original_text))
    if expected_mode != strategy.expected_mode:
        return EnrichmentResult(
            status="rejected",
            story_id=story_id,
            errors=(
                f"expected_mode={expected_mode!r} does not match the length-derived strategy for "
                f"this story (original_text length={len(story.original_text)}): the canonical "
                f"strategy requires expected_mode={strategy.expected_mode!r} — refusing to call the "
                "LLM, no DB write attempted",
            ),
        )

    prompt = build_enrichment_prompt(
        story, expected_mode=expected_mode, expected_derivation_type=strategy.expected_derivation_type
    )
    raw_response = llm_generate(prompt)
    payload = _extract_json_object(raw_response)
    if payload is None:
        return EnrichmentResult(
            status="rejected",
            story_id=story_id,
            errors=("could not parse a JSON object from the model response",),
            raw_response=raw_response,
        )

    mode = payload.get("mode")
    if mode != expected_mode:
        return EnrichmentResult(
            status="rejected",
            story_id=story_id,
            errors=(
                f"model returned mode={mode!r} but caller expected "
                f"expected_mode={expected_mode!r} — no DB write attempted",
            ),
            raw_response=raw_response,
        )

    if mode == "direct_unit":
        return _handle_direct_unit(
            connection,
            story=story,
            payload=payload,
            model_identifier=model_identifier,
            prompt_version=prompt_version,
            unit_index=unit_index,
            allow_overwrite_reviewed=allow_overwrite_reviewed,
            expected_derivation_type=strategy.expected_derivation_type,
            raw_response=raw_response,
        )
    return _handle_unit_proposal(story=story, payload=payload, raw_response=raw_response)


def _load_story(connection: sqlite3.Connection, story_id: int) -> _LoadedStory | None:
    row = connection.execute(
        """
        SELECT st.id, st.source_id, st.title_original, st.original_text, s.code, s.tradition
        FROM stories st JOIN sources s ON s.id = st.source_id
        WHERE st.id = ?
        """,
        (story_id,),
    ).fetchone()
    return _LoadedStory(*row) if row else None


def _handle_direct_unit(
    connection: sqlite3.Connection,
    *,
    story: _LoadedStory,
    payload: dict,
    model_identifier: str,
    prompt_version: str,
    unit_index: int,
    allow_overwrite_reviewed: bool,
    expected_derivation_type: str,
    raw_response: str,
) -> EnrichmentResult:
    unit_payload = payload.get("unit")
    if not isinstance(unit_payload, dict):
        return EnrichmentResult(
            status="rejected",
            story_id=story.id,
            errors=("mode='direct_unit' requires a 'unit' object",),
            raw_response=raw_response,
        )

    errors: list[str] = []
    warnings: list[str] = []
    # Phase 3H.1: resolve safe accent/case slug variants BEFORE the
    # controlled-vocabulary check below, so a real production failure
    # mode ("eszesség" instead of "eszesseg") no longer rejects an
    # otherwise-valid enrichment. See _canonicalize_taxonomy_in_payload's
    # own docstring for the exact, deliberately narrow safety rule.
    warnings.extend(_canonicalize_taxonomy_in_payload(unit_payload))
    _validate_common_fields(
        unit_payload, errors, warnings,
        source_text=story.original_text, required_text_fields=_DIRECT_UNIT_REQUIRED_TEXT_FIELDS,
    )
    # Phase 3D.1: the LLM no longer freely picks between
    # full_story_translation/condensed_story -- expected_derivation_type
    # was already determined from story length by derive_enrichment_
    # strategy() in enrich_story(), before the LLM was even called. Any
    # OTHER value (including the other, otherwise-valid direct_unit
    # derivation_type) is a contract violation, same severity as an
    # expected_mode mismatch.
    derivation_type = unit_payload.get("derivation_type")
    if derivation_type != expected_derivation_type:
        errors.append(
            f"direct_unit derivation_type must be {expected_derivation_type!r} for this story's "
            f"length ({len(story.original_text)} chars), got {derivation_type!r}"
        )
    if "source_span_start" in unit_payload or "source_span_end" in unit_payload:
        if unit_payload.get("source_span_start") is not None or unit_payload.get("source_span_end") is not None:
            errors.append("direct_unit must not set source_span_start/source_span_end")

    # Band-B length window (condensed_story direct_unit, Phase 3D.1): the
    # generated text must itself already be a short, retrieval-ready
    # illustration -- not "the whole 1501-3000-char source, condensed
    # just enough to squeak under some limit."
    if expected_derivation_type == "condensed_story":
        modern_text = unit_payload.get("modern_hu_text")
        if isinstance(modern_text, str) and not (
            _MIN_CONDENSED_MODERN_TEXT_CHARS <= len(modern_text) <= _MAX_CONDENSED_MODERN_TEXT_CHARS
        ):
            errors.append(
                f"condensed_story modern_hu_text must be {_MIN_CONDENSED_MODERN_TEXT_CHARS}-"
                f"{_MAX_CONDENSED_MODERN_TEXT_CHARS} chars, got {len(modern_text)}"
            )

    if errors:
        return EnrichmentResult(
            status="rejected", story_id=story.id, errors=tuple(errors), raw_response=raw_response
        )

    now = datetime.now(UTC).isoformat()
    # Atomic persistence (post-review hardening): create/get -> content
    # update -> tag sync -> mark_needs_review must behave as ONE unit —
    # if any step fails, nothing from this call may survive. A SAVEPOINT
    # (not a blanket connection.rollback()) scopes the undo to just this
    # sequence, so it can't clobber unrelated uncommitted work a batch
    # caller might have pending on the same connection from a PREVIOUS
    # story in the same run.
    connection.execute("SAVEPOINT enrich_direct_unit")
    try:
        unit_id = _create_or_get_unit_id(
            connection, story_id=story.id, unit_index=unit_index, derivation_type=derivation_type
        )
        update_draft_unit(
            connection,
            unit_id=unit_id,
            title_hu=unit_payload["title_hu"],
            modern_hu_text=unit_payload["modern_hu_text"],
            summary_hu=unit_payload["summary_hu"],
            # moral_hu is optional (Phase 3G-B3) -- the key may be absent
            # entirely (not just null), so a plain [...] index would raise
            # KeyError for a model response that omits it outright.
            moral_hu=unit_payload.get("moral_hu"),
            narrative_status=unit_payload["narrative_status"],
            narrative_status_confidence=unit_payload["narrative_status_confidence"],
            enrichment_model=model_identifier,
            enrichment_prompt_version=prompt_version,
            enrichment_generated_at=now,
            # Always explicitly passed (never omitted) so a clean rerun's
            # empty tuple correctly REPLACES a stale warning from a
            # previous run with NULL, rather than leaving it untouched.
            enrichment_warnings=tuple(warnings),
            allow_overwrite_reviewed=allow_overwrite_reviewed,
        )
        _sync_pilot_tags(
            connection,
            unit_id=unit_id,
            topics=unit_payload["topics"],
            tone=unit_payload["tone"],
            homiletic_functions=unit_payload["homiletic_functions"],
        )
        mark_needs_review(connection, unit_id)
    except IllustrationUnitReviewProtectionError as exc:
        connection.execute("ROLLBACK TO SAVEPOINT enrich_direct_unit")
        connection.execute("RELEASE SAVEPOINT enrich_direct_unit")
        return EnrichmentResult(
            status="rejected", story_id=story.id, errors=(str(exc),), raw_response=raw_response
        )
    except Exception as exc:  # noqa: BLE001 - any mid-sequence failure must roll back, not just the known one
        connection.execute("ROLLBACK TO SAVEPOINT enrich_direct_unit")
        connection.execute("RELEASE SAVEPOINT enrich_direct_unit")
        return EnrichmentResult(
            status="rejected",
            story_id=story.id,
            errors=(f"enrichment persistence failed, rolled back: {exc}",),
            raw_response=raw_response,
        )
    else:
        connection.execute("RELEASE SAVEPOINT enrich_direct_unit")

    return EnrichmentResult(
        status="unit_created", story_id=story.id, unit_id=unit_id,
        warnings=tuple(warnings), raw_response=raw_response,
    )


def _handle_unit_proposal(
    *, story: _LoadedStory, payload: dict, raw_response: str
) -> EnrichmentResult:
    raw_units = payload.get("proposed_units")
    if not isinstance(raw_units, list) or not raw_units:
        return EnrichmentResult(
            status="rejected",
            story_id=story.id,
            errors=("mode='unit_proposal' requires a non-empty 'proposed_units' list",),
            raw_response=raw_response,
        )

    errors: list[str] = []
    warnings: list[str] = []
    proposed: list[ProposedUnit] = []
    for index, unit_payload in enumerate(raw_units):
        if not isinstance(unit_payload, dict):
            errors.append(f"proposed_units[{index}] is not an object")
            continue
        unit_errors: list[str] = []
        unit_warnings: list[str] = []
        unit_warnings.extend(_canonicalize_taxonomy_in_payload(unit_payload))
        _validate_common_fields(
            unit_payload, unit_errors, unit_warnings,
            source_text=story.original_text, required_text_fields=_PROPOSAL_TEXT_FIELDS,
        )

        derivation_type = unit_payload.get("derivation_type")
        if derivation_type not in _PROPOSAL_DERIVATION_TYPES:
            unit_errors.append(
                f"proposed_units[{index}].derivation_type must be one of "
                f"{sorted(_PROPOSAL_DERIVATION_TYPES)}, got {derivation_type!r}"
            )

        span_start = unit_payload.get("source_span_start")
        span_end = unit_payload.get("source_span_end")
        if derivation_type == "extracted_scene":
            unit_errors.extend(
                _validate_source_span(span_start, span_end, text_length=len(story.original_text))
            )
            if not (unit_payload.get("rationale") or "").strip():
                unit_errors.append(f"proposed_units[{index}]: extracted_scene requires a non-empty 'rationale'")
            if not (unit_payload.get("standalone_reason") or "").strip():
                unit_errors.append(
                    f"proposed_units[{index}]: extracted_scene requires a non-empty 'standalone_reason'"
                )
        elif span_start is not None or span_end is not None:
            unit_errors.append(f"proposed_units[{index}]: only extracted_scene may set source_span_start/end")

        # PROPOSAL CONTRACT (Phase 3C-c): a condensed_story proposal states
        # only an ESTIMATED target length for the eventual modern_hu_text —
        # the text itself is never generated at proposal time. Required
        # exactly where extracted_scene requires source_span_start/end.
        target_length_chars = unit_payload.get("target_length_chars")
        if derivation_type == "condensed_story":
            if (
                not isinstance(target_length_chars, int)
                or isinstance(target_length_chars, bool)
                or not (_MIN_TARGET_LENGTH_CHARS <= target_length_chars <= _MAX_TARGET_LENGTH_CHARS)
            ):
                unit_errors.append(
                    f"proposed_units[{index}]: condensed_story requires an integer 'target_length_chars' "
                    f"between {_MIN_TARGET_LENGTH_CHARS} and {_MAX_TARGET_LENGTH_CHARS}"
                )
            elif target_length_chars >= len(story.original_text):
                unit_errors.append(
                    f"proposed_units[{index}]: target_length_chars ({target_length_chars}) must be shorter "
                    f"than the source text ({len(story.original_text)} chars) — a condensed_story must "
                    "actually condense"
                )
        elif target_length_chars is not None:
            unit_errors.append(f"proposed_units[{index}]: only condensed_story may set target_length_chars")

        if unit_errors:
            errors.extend(f"proposed_units[{index}]: {e}" for e in unit_errors)
            continue
        warnings.extend(f"proposed_units[{index}]: {w}" for w in unit_warnings)

        proposed.append(
            ProposedUnit(
                derivation_type=derivation_type,
                source_span_start=span_start,
                source_span_end=span_end,
                title_hu=unit_payload["title_hu"],
                # Deliberately never carried forward from the payload, even
                # if the model supplied one anyway — see the PROPOSAL
                # CONTRACT note on ProposedUnit itself.
                modern_hu_text=None,
                summary_hu=unit_payload["summary_hu"],
                moral_hu=None,
                topics=tuple(unit_payload["topics"]),
                tone=unit_payload["tone"],
                homiletic_functions=tuple(unit_payload["homiletic_functions"]),
                narrative_status=unit_payload["narrative_status"],
                narrative_status_confidence=unit_payload["narrative_status_confidence"],
                rationale=unit_payload.get("rationale"),
                standalone_reason=unit_payload.get("standalone_reason"),
                target_length_chars=target_length_chars if derivation_type == "condensed_story" else None,
            )
        )

    if errors:
        return EnrichmentResult(
            status="rejected", story_id=story.id, errors=tuple(errors), raw_response=raw_response
        )

    # Deliberately NOT persisted — Phase 3B brief §3: a long-story 1:N
    # split may only become real illustration_units after separate,
    # explicit human approval of THIS proposal list.
    return EnrichmentResult(
        status="proposal_ready", story_id=story.id, proposed_units=tuple(proposed),
        warnings=tuple(warnings), raw_response=raw_response,
    )


def _create_or_get_unit_id(
    connection: sqlite3.Connection, *, story_id: int, unit_index: int, derivation_type: str
) -> int:
    row = connection.execute(
        "SELECT id FROM illustration_units WHERE story_id = ? AND unit_index = ?",
        (story_id, unit_index),
    ).fetchone()
    if row is not None:
        return int(row[0])
    return create_draft_unit(
        connection, story_id=story_id, unit_index=unit_index, derivation_type=derivation_type
    )


def _sync_pilot_tags(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    topics: list[str],
    tone: str,
    homiletic_functions: list[str],
) -> None:
    """REPLACES (does not accumulate onto) a unit's pilot-controlled
    tags: after this call, the unit's `topic`/`tone`/`function` tags are
    EXACTLY the given `topics`/`tone`/`homiletic_functions` — a stale
    tag from a previous enrichment run that isn't in the new set is
    detached, not left dangling alongside the new ones.

    Only ever touches a tag whose `(category, slug)` is a member of
    `_PILOT_CONTROLLED_TAG_CATEGORIES` (i.e. this module's own
    controlled vocabulary) — a tag attached by some other, non-pilot
    mechanism (even one sharing the same category name) is left alone,
    per the Phase 3B follow-up brief's explicit "don't blindly delete
    metadata this pipeline doesn't own" requirement.
    """
    desired: set[tuple[str, str]] = {("topic", slug) for slug in topics}
    desired.add(("tone", tone))
    desired.update(("function", slug) for slug in homiletic_functions)

    existing = connection.execute(
        "SELECT ut.tag_id, t.category, t.slug FROM illustration_unit_tags ut "
        "JOIN tags t ON t.id = ut.tag_id WHERE ut.unit_id = ?",
        (unit_id,),
    ).fetchall()

    for tag_id, category, slug in existing:
        controlled_slugs = _PILOT_CONTROLLED_TAG_CATEGORIES.get(category)
        if controlled_slugs is None or slug not in controlled_slugs:
            continue  # not a pilot-managed tag — never touched here
        pair = (category, slug)
        if pair in desired:
            desired.discard(pair)  # already correctly attached
        else:
            detach_tag_from_unit(connection, unit_id=unit_id, tag_id=tag_id)

    for category, slug in desired:
        tag_id = get_or_create_tag(connection, category=category, slug=slug, label_hu=slug)
        attach_tag_to_unit(connection, unit_id=unit_id, tag_id=tag_id)


def _validate_common_fields(
    unit_payload: dict,
    errors: list[str],
    warnings: list[str],
    *,
    source_text: str,
    required_text_fields: tuple[str, ...],
) -> None:
    for field_name in required_text_fields:
        value = unit_payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field_name} must be a non-empty string")

    # Phase 3G-B3: moral_hu is deliberately OPTIONAL, never in
    # required_text_fields (see _DIRECT_UNIT_REQUIRED_TEXT_FIELDS) -- a
    # missing key, null, or "" are all valid ("no natural moral for this
    # story"). Only a genuinely wrong TYPE (a number, list, etc.) is
    # rejected; an empty/whitespace-only string is accepted as-is, not
    # normalized here (persistence stores exactly what was given).
    if "moral_hu" in unit_payload:
        moral_hu = unit_payload.get("moral_hu")
        if moral_hu is not None and not isinstance(moral_hu, str):
            errors.append("moral_hu must be a string or null when present")

    summary_hu = unit_payload.get("summary_hu")
    if isinstance(summary_hu, str) and summary_hu.strip():
        word_count = len(summary_hu.split())
        if not (_SUMMARY_MIN_WORDS <= word_count <= _SUMMARY_MAX_WORDS):
            errors.append(
                f"summary_hu must be {_SUMMARY_MIN_WORDS}-{_SUMMARY_MAX_WORDS} words, got {word_count}"
            )

    topics = unit_payload.get("topics")
    if not isinstance(topics, list) or not (1 <= len(topics) <= 3):
        errors.append("topics must be a list of 1-3 items")
    elif not all(t in PILOT_TOPICS for t in topics):
        errors.append(f"topics must all be in the pilot topic taxonomy {sorted(PILOT_TOPICS)}: got {topics}")

    tone = unit_payload.get("tone")
    if tone not in PILOT_TONES:
        errors.append(f"tone must be exactly one of {sorted(PILOT_TONES)}, got {tone!r}")

    functions = unit_payload.get("homiletic_functions")
    if not isinstance(functions, list) or not (1 <= len(functions) <= 2):
        errors.append("homiletic_functions must be a list of 1-2 items")
    elif not all(f in PILOT_HOMILETIC_FUNCTIONS for f in functions):
        errors.append(
            f"homiletic_functions must all be in {sorted(PILOT_HOMILETIC_FUNCTIONS)}: got {functions}"
        )

    narrative_status = unit_payload.get("narrative_status")
    if narrative_status not in ALLOWED_NARRATIVE_STATUSES:
        errors.append(f"narrative_status must be one of {sorted(ALLOWED_NARRATIVE_STATUSES)}, got {narrative_status!r}")

    confidence = unit_payload.get("narrative_status_confidence")
    if confidence not in ALLOWED_NARRATIVE_STATUS_CONFIDENCE:
        errors.append(
            f"narrative_status_confidence must be one of {sorted(ALLOWED_NARRATIVE_STATUS_CONFIDENCE)}, "
            f"got {confidence!r}"
        )

    # Phase 3D.1: the proper-name guard is warning-only now (see
    # _hallucination_guard's docstring) -- it never contributes to
    # `errors`/rejection.
    warnings.extend(_hallucination_guard(unit_payload, source_text=source_text))


def _validate_source_span(span_start: object, span_end: object, *, text_length: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(span_start, int) or isinstance(span_start, bool):
        errors.append("source_span_start must be an integer")
    if not isinstance(span_end, int) or isinstance(span_end, bool):
        errors.append("source_span_end must be an integer")
    if errors:
        return errors
    if not (0 <= span_start < span_end <= text_length):
        errors.append(
            f"source_span_start/end out of bounds or non-increasing "
            f"(start={span_start}, end={span_end}, text_length={text_length})"
        )
    return errors


_MIN_SOURCE_WORD_LEN_FOR_PREFIX_MATCH = 3
# Source-side candidate pool is restricted to CAPITALIZED tokens only
# (see docstring below for why) — this pattern intentionally mirrors
# _CANDIDATE_PROPER_NOUN_RE's shape (ASCII-only, since original_text in
# this pilot is always English/Latin-script).
_SOURCE_PROPER_NOUN_RE = re.compile(r"[A-Z][a-zA-Z]{2,}")


def _fold_diacritics(s: str) -> str:
    """Unicode accent/diacritic folding (NFKD decompose, drop combining
    marks) — Phase 3D.1. Turns "Ádám"/"Alfréd"/"Orléans" into the same
    string as their unaccented ASCII spelling ("adam"/"alfred"/"orleans")
    so the guard's prefix match stops treating a bare accent difference
    as evidence of a different word. Pure Unicode normalization, NOT a
    translation table: it has no idea "János" means "John" or "Anglia"
    means "England" (different letters entirely, not an accent
    variant) — those remain genuinely unmatched and still warn, exactly
    as intended."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _canonicalize_slug(raw: object, vocabulary: frozenset[str]) -> tuple[object, bool]:
    """Phase 3H.1: a SAFE, deterministic taxonomy-slug fixer -- reuses
    the same `_fold_diacritics` folding as the hallucination guard, not a
    new heuristic. Fixes exactly the failure mode a real production
    batch hit: the model returning an accented spelling ("eszesség")
    instead of the canonical unaccented slug ("eszesseg").

    Returns `(raw, False)` unchanged unless ALL of:
    - `raw` is a string not already in `vocabulary`;
    - its diacritic-folded, lowercased form matches the folded form of
      EXACTLY ONE `vocabulary` member (never >1 -- that would be
      ambiguous, and this function never guesses between candidates);
    - there is no fuzzy/semantic matching of any kind -- an unrelated
      but similar-looking word (e.g. a genuine synonym) is NOT
      canonicalized, only an accent/case variant of an EXISTING slug is.

    Never invents a new taxonomy slug -- the returned value, when
    `True`, is always a real, pre-existing member of `vocabulary`."""
    if not isinstance(raw, str) or raw in vocabulary:
        return raw, False
    folded = _fold_diacritics(raw.strip().lower())
    matches = [slug for slug in vocabulary if _fold_diacritics(slug.lower()) == folded]
    if len(matches) == 1:
        return matches[0], True
    return raw, False


def _canonicalize_taxonomy_in_payload(unit_payload: dict) -> list[str]:
    """Mutates `unit_payload["topics"]`/`["tone"]`/`["homiletic_functions"]`
    IN PLACE, replacing any slug `_canonicalize_slug` can safely resolve.
    Anything NOT uniquely resolvable is left exactly as the model wrote
    it -- `_validate_common_fields`'s existing controlled-vocabulary
    check is still the fail-closed authority for those; this function
    only ever narrows what reaches that check, never widens what it
    accepts. Returns human-readable audit notes for anything actually
    changed (folded into `warnings`, never applied silently)."""
    notes: list[str] = []

    topics = unit_payload.get("topics")
    if isinstance(topics, list):
        resolved_topics = []
        for slug in topics:
            resolved, changed = _canonicalize_slug(slug, PILOT_TOPICS)
            if changed:
                notes.append(f"topic slug {slug!r} auto-canonicalized to {resolved!r}")
            resolved_topics.append(resolved)
        unit_payload["topics"] = resolved_topics

    tone = unit_payload.get("tone")
    resolved_tone, tone_changed = _canonicalize_slug(tone, PILOT_TONES)
    if tone_changed:
        notes.append(f"tone slug {tone!r} auto-canonicalized to {resolved_tone!r}")
        unit_payload["tone"] = resolved_tone

    functions = unit_payload.get("homiletic_functions")
    if isinstance(functions, list):
        resolved_functions = []
        for slug in functions:
            resolved, changed = _canonicalize_slug(slug, PILOT_HOMILETIC_FUNCTIONS)
            if changed:
                notes.append(f"homiletic_function slug {slug!r} auto-canonicalized to {resolved!r}")
            resolved_functions.append(resolved)
        unit_payload["homiletic_functions"] = resolved_functions

    return notes


def _hallucination_guard(unit_payload: dict, *, source_text: str) -> list[str]:
    """Flags capitalized, non-sentence-initial Hungarian words in the
    enrichment output that don't look like they're built from any
    CAPITALIZED word appearing in the source text — a coarse tripwire
    for an AI-invented proper noun. Deliberately lightweight: this is
    NOT a real NER/hallucination-detection system, and must not be
    relied on as one.

    Phase 3D.1: this used to hard-reject when an unmatched candidate sat
    adjacent to a matched one (the "Alexander Pope" name-completion
    shape). The 25-story untouched pilot found that shape ALSO fires on
    two genuinely correct translations that simply happened to land next
    to a real kept name by ordinary sentence word order — "Ádámnak
    Lumley" (a correct, if diacritic-different, biblical name right
    before a real surname) and "North Írországgal" (a correct place-name
    translation right after a real surname) — a real ~10% false-reject
    rate on live translated output. Since the guard cannot reliably tell
    "invented name glued onto a kept one" apart from "unrelated correct
    word that happens to sit next to a name," adjacency is now ONLY ever
    a WARNING signal (a higher-priority one, still worth a human's
    attention first) — never a rejection. ALL findings from this
    function are warnings; nothing it returns can block persistence by
    itself. Fail-closed correctness now lives entirely in the human-
    review gate: a warned unit still lands at needs_review, never
    approved/published automatically.

    Returns a flat list of warning messages — a "SUSPICIOUS NAME
    EXPANSION" one (adjacent to a matched source name — prioritize this
    in review) and/or a generic "translation/exonym" one (standalone),
    depending on what was found.

    Diacritic folding (`_fold_diacritics`) is applied to BOTH sides of
    the comparison before matching, closing the Ádám/Alfréd/Orléans class
    of false positive without any translation dictionary — a semantic
    translation (János/Anglia/Isten) shares no letters with its English
    source word even after folding, so those keep warning exactly as
    before; only genuine accent-only spelling differences are absorbed.

    REMAINING, ACCEPTED LIMITATIONS (a lightweight heuristic cannot close
    these without becoming a real NER system):
    - A wholly invented name is indistinguishable, by this heuristic,
      from a correct translation/exonym — both surface as the same class
      of warning. This is intentional: distinguishing them would require
      exactly the translation dictionary or NER system this project has
      repeatedly declined to build. A human reviewer makes the actual
      call.
    - Very short candidates (right at the 3-letters-after-the-initial-
      capital minimum) are inherently easier to accidentally prefix-
      match than long ones; this guard does not attempt frequency-
      based or dictionary-based discrimination.
    """
    combined = "\n".join(
        str(unit_payload.get(f, "") or "")
        for f in ("title_hu", "modern_hu_text", "summary_hu", "moral_hu")
    )
    source_words = {
        _fold_diacritics(m.group(0).lower())
        for m in _SOURCE_PROPER_NOUN_RE.finditer(source_text)
        if len(m.group(0)) >= _MIN_SOURCE_WORD_LEN_FOR_PREFIX_MATCH
    }
    suspicious_flagged: list[str] = []
    generic_flagged: list[str] = []
    seen_suspicious: set[str] = set()
    seen_generic: set[str] = set()
    for sentence in _SENTENCE_SPLIT_RE.split(combined):
        words = sentence.strip().split()
        # candidates[i] / matched[i] are None for a non-candidate word.
        # Position 0 (sentence-initial) IS still recorded here -- it must
        # never itself be REPORTED (see the loop below), but if it is a
        # genuinely matched real name ("Sheridan Ede ...", "Sheridan" at
        # position 0), its match status must still be visible to its
        # neighbor's adjacency check.
        candidates: list[str | None] = [None] * len(words)
        matched: list[bool | None] = [None] * len(words)
        for position, word in enumerate(words):
            match = _CANDIDATE_PROPER_NOUN_RE.match(word.strip(",.;:!?\"'()"))
            if not match:
                continue
            candidate = match.group(0)
            candidates[position] = candidate
            candidate_folded = _fold_diacritics(candidate.lower())
            matched[position] = any(candidate_folded.startswith(sw) for sw in source_words)

        for position, candidate in enumerate(candidates):
            if position == 0:
                continue  # sentence-initial capital is normal, never itself a name signal
            if candidate is None or matched[position]:
                continue
            key = candidate.lower()
            adjacent_matched = (
                (position > 0 and candidates[position - 1] is not None and matched[position - 1])
                or (
                    position + 1 < len(candidates)
                    and candidates[position + 1] is not None
                    and matched[position + 1]
                )
            )
            if adjacent_matched:
                if key not in seen_suspicious:
                    seen_suspicious.add(key)
                    suspicious_flagged.append(candidate)
            else:
                if key not in seen_generic:
                    seen_generic.add(key)
                    generic_flagged.append(candidate)

    messages: list[str] = []
    if suspicious_flagged:
        messages.append(
            "SUSPICIOUS NAME EXPANSION (adjacent to a matched source name — could be an "
            "invented name completion like 'Pope'->'Alexander Pope', or could be an "
            "unrelated correct word that just happens to sit next to a real name; "
            "prioritize this in review): " + ", ".join(sorted(set(suspicious_flagged)))
        )
    if generic_flagged:
        messages.append(
            "capitalized word(s) with no matching source token — likely a "
            "translation/exonym, not necessarily a hallucination; needs human "
            "review: " + ", ".join(sorted(set(generic_flagged)))
        )
    return messages


def _extract_json_object(raw: str) -> dict | None:
    """Same tolerance level as this repo's other `extract_json_object`
    implementations (markdown-fence stripping, trailing-comma repair) —
    reimplemented locally rather than imported, matching how every other
    `*_ai.py` module in this codebase owns its own copy."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        candidate_fixed = re.sub(r",\s*}", "}", candidate)
        candidate_fixed = re.sub(r",\s*]", "]", candidate_fixed)
        for attempt in (candidate, candidate_fixed):
            try:
                obj = json.loads(attempt)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def build_enrichment_prompt(
    story: _LoadedStory, *, expected_mode: str, expected_derivation_type: str | None = None
) -> str:
    topics_list = ", ".join(sorted(PILOT_TOPICS))
    tones_list = ", ".join(sorted(PILOT_TONES))
    functions_list = ", ".join(sorted(PILOT_HOMILETIC_FUNCTIONS))
    narrative_statuses = ", ".join(sorted(ALLOWED_NARRATIVE_STATUSES))
    if expected_mode == "direct_unit":
        # Phase 3D.1: expected_derivation_type is now DICTATED by
        # derive_enrichment_strategy() from the story's length, before
        # this prompt is even built — the model is told exactly which
        # one to produce, not offered a free choice between the two.
        if expected_derivation_type == "condensed_story":
            mode_instructions = f"""\
FELADAT — a rendszer ehhez a történethez EGYETLEN illustration unitot \
vár ("mode": "direct_unit", "derivation_type": "condensed_story" — ezt \
a történet hossza határozza meg, NE válassz másik derivation_type-ot). \
A story hosszabb, ezért a modern_hu_text NEM lehet majdnem-teljes \
fordítás: {_MIN_CONDENSED_MODERN_TEXT_CHARS}–{_MAX_CONDENSED_MODERN_TEXT_CHARS} \
karakter hosszú, közvetlenül elmondható, RÖVID prédikációs illusztráció \
legyen, amely a történet lényegét (a legfontosabb szereplőt, helyzetet \
és csattanót) őrzi meg, a részletek tömörítésével. NE válaszolj \
"unit_proposal" móddal — ezt a történetet a rendszer nem fogadja el \
bontásra javasoltként."""
        else:
            mode_instructions = """\
FELADAT — a rendszer ehhez a történethez EGYETLEN, teljes illustration \
unitot vár ("mode": "direct_unit", "derivation_type": \
"full_story_translation" — ezt a történet hossza határozza meg, NE \
válassz másik derivation_type-ot). A teljes történetet dolgozd fel \
egyetlen unitba. NE válaszolj "unit_proposal" móddal — ezt a történetet \
a rendszer nem fogadja el bontásra javasoltként."""
    else:
        mode_instructions = f"""\
FELADAT — a rendszer ehhez a történethez egy vagy több JAVASOLT \
illustration unitot vár ("mode": "unit_proposal"). Ez a történet hosszú \
és/vagy több epizódból állhat. Egy epizódot csak akkor javasolj önálló \
extracted_scene-ként, ha:
   - önmagában, a kihagyott rész nélkül is érthető;
   - valódi narratív egységet alkot (szereplő, helyzet, esemény);
   - a csattanója/jelentése NEM igényli a kihagyott rész ismeretét.
   Ha ez nem teljesül egyértelműen, NE bontsd szét — adj helyette EGY \
   "condensed_story" javaslatot, ami az egész történetet tömöríti. \
NE válaszolj "direct_unit" móddal — a rendszer ennél a történetnél \
semmilyen közvetlen írást nem fogad el, csak javaslatot.

FONTOS — ebben a módban NE generálj "modern_hu_text"-et és "moral_hu"-t: \
a javaslat egyetlen célja annak eldöntése, MILYEN illustration unit \
készülhetne ebből a történetből, nem pedig annak megírása. A teljes \
magyar illusztrációs szöveg csak egy KÉSŐBBI, ember által jóváhagyott \
lépésben készül el, kizárólag az elfogadott javaslathoz. "condensed_story" \
esetén add meg helyette a "target_length_chars" mezőt: egy becsült \
célhosszt (karakterben) a leendő modern_hu_text-hez — {_MIN_TARGET_LENGTH_CHARS} \
és {_MAX_TARGET_LENGTH_CHARS} közötti egész szám, és mindig rövidebb, mint \
az original_text hossza. A cél egy közvetlenül elmondható, RÖVID \
prédikációs illusztráció — NEM a teljes történet magyar fordítása \
tömörítve. Ha a story olyan rövid, hogy egy {_MIN_TARGET_LENGTH_CHARS} \
karakteres célhossz sem értelmezhető rá, az nem "unit_proposal", hanem \
"direct_unit" móddal kezelendő történet."""
    if expected_mode == "direct_unit":
        length_rule_line = (
            f"- pontosan {_MIN_CONDENSED_MODERN_TEXT_CHARS}–{_MAX_CONDENSED_MODERN_TEXT_CHARS} "
            "karakter hosszú legyen — ne a teljes történet fordítása, hanem annak "
            "tömörített, retrieval-ready lényege;"
            if expected_derivation_type == "condensed_story"
            else "- rövid történetnél őrizd meg a teljes narratív tartalmat."
        )
        modern_text_rules_section = f"""\
MAGYAR SZÖVEG SZABÁLYOK (modern_hu_text):
- természetes, mai magyar nyelv;
- hű az original_text tartalmához — ne adj hozzá új szereplőt, \
  eseményt, motivációt vagy tanulságot;
- ne prédikáld túl a történetet (ne fűzz hozzá saját magyarázatot);
- ne legyen fölöslegesen archaikus;
{length_rule_line}

"""
        name_completion_fields = "title_hu, modern_hu_text, summary_hu és moral_hu"
        moral_rules_section = """\
MORAL_HU SZABÁLYOK (OPCIONÁLIS mező):
- a moral_hu OPCIONÁLIS — ha a történet a saját természeténél fogva \
  világos erkölcsi/emberi tanulságot hordoz, adj meg egy rövid, \
  SEMLEGES tanulság/téma-mondatot;
- Ne gyárts erkölcsi tanulságot, ha a történet természetéből nem \
  következik. Humoros, ironikus vagy pusztán anekdotikus történetnél a \
  moral_hu lehet üres — ilyenkor a moral_hu értéke legyen null, NE \
  találj ki hozzá mesterséges tanulságot csak azért, hogy a mező ki \
  legyen töltve, és NE erőltess rá a forrásra prédikációs alkalmazást;
- ha mégis megadod, NE legyen automatikusan keresztény teológiai \
  értelmezés, és NE helyezz bibliai jelentést olyan történetre, ahol \
  az nincs a forrásban.

"""
        json_shape_section = """\
"direct_unit" mód esetén pontosan ez az alak:
{
  "mode": "direct_unit",
  "unit": {
    "derivation_type": "EXPECTED_DERIVATION_TYPE",
    "title_hu": "...",
    "modern_hu_text": "...",
    "summary_hu": "...",
    "moral_hu": "... vagy null, ha a történetnek nincs természetes tanulsága",
    "topics": ["irgalom"],
    "tone": "komoly",
    "homiletic_functions": ["szemlelteto_pelda"],
    "narrative_status": "...",
    "narrative_status_confidence": "low | medium | high"
  }
}
(A "topics"/"tone"/"homiletic_functions" fenti értékei CSAK a helyes \
formátumot illusztrálják — a te válaszodban a KONTROLLÁLT CÍMKÉK \
listákból a TÉNYLEGESEN a történethez illő elemeket add meg, szó \
szerint úgy írva, ahogy azok a listákban szerepelnek.)
"""
        json_shape_section = json_shape_section.replace(
            "EXPECTED_DERIVATION_TYPE", expected_derivation_type or ""
        )
    else:
        modern_text_rules_section = ""
        name_completion_fields = "title_hu és summary_hu"
        moral_rules_section = ""
        json_shape_section = """\
"unit_proposal" mód esetén pontosan ez az alak:
{
  "mode": "unit_proposal",
  "proposed_units": [
    {
      "derivation_type": "extracted_scene | condensed_story",
      "source_span_start": <int, csak extracted_scene esetén>,
      "source_span_end": <int, csak extracted_scene esetén>,
      "title_hu": "...",
      "summary_hu": "...",
      "topics": ["irgalom"],
      "tone": "komoly",
      "homiletic_functions": ["szemlelteto_pelda"],
      "narrative_status": "...",
      "narrative_status_confidence": "...",
      "rationale": "miért ez a szövegrész, csak extracted_scene esetén kötelező",
      "standalone_reason": "miért érthető és mondható el önálló illusztrációként, csak extracted_scene esetén kötelező",
      "target_length_chars": <int, csak condensed_story esetén — TARGET_LENGTH_RANGE közötti egész, a leendő modern_hu_text becsült célhossza karakterben, mindig kisebb mint az original_text hossza>
    }
  ]
}
(A "topics"/"tone"/"homiletic_functions" fenti értékei CSAK a helyes \
formátumot illusztrálják — a te válaszodban a KONTROLLÁLT CÍMKÉK \
listákból a TÉNYLEGESEN a történethez illő elemeket add meg, szó \
szerint úgy írva, ahogy azok a listákban szerepelnek.)

NE add meg "modern_hu_text"-et vagy "moral_hu"-t ebben a módban — ezek \
a mezők ehhez a módhoz nem tartoznak (ld. FELADAT fent).
"""
        json_shape_section = json_shape_section.replace(
            "TARGET_LENGTH_RANGE", f"{_MIN_TARGET_LENGTH_CHARS}–{_MAX_TARGET_LENGTH_CHARS}"
        )

    return f"""\
Te egy magyar református prédikációs illusztráció-adatbázist épító \
szerkesztő asszisztens vagy. A feladatod egyetlen, alább megadott \
forrástörténet feldolgozása — SOHA nem találhatsz ki új szereplőt, \
eseményt, motivációt, tanulságot vagy bibliográfiai adatot, amely nincs \
a forrásszövegben.

FORRÁS ADATOK (csak olvasásra — a mezőket változatlanul kell hagynod):
- source_code: {story.source_code}
- tradition: {story.tradition or "nincs megadva"}
- title_original: {story.title_original}
- original_text hossza: {len(story.original_text)} karakter

ORIGINAL_TEXT:
---
{story.original_text}
---

{mode_instructions}

{modern_text_rules_section}NÉV-KIEGÉSZÍTÉS TILALMA — ez {name_completion_fields} \
MINDEGYIKÉRE vonatkozik:
- SOHA ne egészíts ki egy, az original_text-ben szereplő személynevet \
  a saját (külső) tudásodból;
- ha a forrás csak vezetéknevet ír ("Pope"), a kimenetben is csak az \
  a vezetéknév szerepelhet — TILOS keresztnevet hozzáadni (pl. \
  "Alexander Pope"), még akkor is, ha külső tudásod szerint helyes \
  lenne;
- cím/rang mellé (pl. "a herceg", "a doktor") ne told bele a teljes \
  nevet, ha az original_text nem adja meg;
- helynevet se pontosíts vagy egészíts ki külső tudásodból (pl. ha a \
  forrás csak "London"-t ír, ne told bele, hogy melyik városrész vagy \
  ország fővárosa — csak azt írd, ami a forrásban áll);
- ez a szabály ATTÓL FÜGGETLENÜL érvényes, hogy a kiegészítés \
  ténylegesen igaz-e a valóságban — a kérdés nem az, hogy helyes-e a \
  kiegészítés, hanem hogy szerepel-e az original_text-ben.

{moral_rules_section}SUMMARY_HU SZABÁLYOK:
- pontosan 40-100 szó;
- a történet lényegét foglalja össze, retrieval/böngészés céljára;
- ne tartalmazzon új információt.

NARRATIVE_STATUS — szigorúan kezelendő, csak ezek egyike: \
{narrative_statuses}
- SOHA ne állítsd bizonyíték nélkül, hogy egy történet dokumentált \
  történelmi esemény (documented_historical_event) — ez KIZÁRÓLAG \
  akkor használható, ha a rendelkezésre álló forrásadat (original_text \
  vagy a fenti FORRÁS ADATOK) EXPLICIT módon dokumentált eseményként \
  azonosítja a történetet. A saját (a promptban nem szereplő) \
  tudásod erre sosem elegendő;
- a legend_about_historical_figure ÉRTÉK HASZNÁLATÁNAK FELTÉTELE: ez \
  KIZÁRÓLAG akkor választható, ha a rendelkezésre álló forrásadat vagy \
  explicit provenance TÉNYLEGESEN legendaként/legendary/traditional \
  legend jellegűként azonosítja az adott történetet vagy a forrás \
  ilyen státuszát (pl. a forrás bevezetője kifejezetten "legend"-nek \
  vagy "half-legendary"-nek nevezi). ÖNMAGÁBAN EGYIK SEM ELÉG OK a \
  legend_about_historical_figure választásához: (a) a szereplő valós \
  történelmi személy; (b) a történet régi/klasszikus anekdota; (c) van \
  csattanója; (d) nem tudod dokumentálni, hogy megtörtént-e. Ezek a \
  jellemzők önmagukban egy sima, forma szerinti anekdotát írnak le, \
  NEM legendát;
- ha egy valós történelmi személyről szóló anekdota forráskritikai \
  státusza NEM ismert (a fenti kritérium nem teljesül sem \
  documented_historical_event-hez, sem legend_about_historical_figure-höz), \
  a KONZERVATÍV alapértelmezés: traditional_anecdote, megfelelő "low" \
  vagy "medium" narrative_status_confidence értékkel;
- ha bizonytalan vagy, narrative_status_confidence legyen "low" vagy \
  "medium" — SOHA ne találj ki bizonyosságot.

NARRATIVE_STATUS FORRÁS-TUDATOS ALAPÉRTELMEZÉSEK — a besorolás \
elsősorban a forrás (source_code/tradition, fent) dokumentált \
műfajából induljon ki, ettől csak akkor térj el egy adott \
történetnél, ha az adott story saját tartalma vagy metaadata konkrétan \
indokolja:
- PG_ENGLISH_JESTS_AND_ANECDOTES → alapértelmezett fallback: \
  traditional_anecdote;
- Aesop-jellegű fabulaforrás → fable;
- magyar népmese-forrás → folktale;
- Hebrew Tales (talmudi/midrási) → rabbinic_aggadic_tale;
- Gulistan (perzsa didaktikus mű) → didactic_tale;
- James Baldwin "Fifty Famous Stories Retold" KÜLÖNÖSEN óvatosan \
  kezelendő: a kötet saját előszava dokumentáltan félig-legendás/\
  romantikus jelleget tulajdonít az anyagnak ÁLTALÁBAN, de ez NEM \
  jelenti azt, hogy MINDEN Baldwin-történet automatikusan \
  legend_about_historical_figure — story-szintű bizonytalanság esetén \
  a narrative_status_confidence legyen "low" vagy "medium", és a \
  konkrét besorolást mindig az adott történet saját tartalma döntse \
  el, ne a kötet egészére vonatkozó általános jellemzés automatikus \
  átvitele.

NARRATIVE_STATUS FORRÁS-FEGYELEM (provenance discipline) — KRITIKUS \
szabály:
- a narrative_status és narrative_status_confidence besorolás \
  KIZÁRÓLAG a fenti ORIGINAL_TEXT tartalmából és a fenti FORRÁS \
  ADATOK-ból (source_code, tradition) származhat;
- TILOS a saját (külső, a forrás szövegén kívüli) történelmi \
  ismereteidet felhasználni annak eldöntésére, hogy egy konkrét \
  anekdota documented_historical_event vagy legend_about_historical_figure \
  — még akkor is, ha a szereplő valós, azonosítható történelmi személy, \
  és még akkor is, ha külső tudásod szerint ismersz a témához \
  kapcsolódó, dokumentált eseményeket;
- PÉLDA a helytelen eljárásra: ha a forrás csak egy rövid, Voltaire-ről \
  szóló anekdotát ad, TILOS a saját tudásodból ismert, dokumentált \
  Rohan-affért felhasználni annak eldöntésére, hogy EZ a konkrét \
  anekdota dokumentált esemény-e vagy legenda — a forrás önmagában, \
  külső kontextus nélkül, tipikusan nem ad elég alapot ehhez a \
  megkülönböztetéshez, ezért ilyenkor traditional_anecdote a helyes \
  konzervatív választás, NEM legend_about_historical_figure;
- ha a rendelkezésre álló forrásadat (original_text + forrás \
  metaadatok) önmagában NEM elegendő a pontos besoroláshoz, a \
  KONZERVATÍV alapértelmezés traditional_anecdote (NEM \
  documented_historical_event, és NEM legend_about_historical_figure, \
  hacsak a fenti explicit provenance-feltétel nem teljesül), és \
  narrative_status_confidence legyen "low" vagy "medium".

KONTROLLÁLT CÍMKÉK — KIZÁRÓLAG EZEKET HASZNÁLHATOD, új címkét nem \
találhatsz ki:
- topics (1-3 db): {topics_list}
- tone (pontosan 1): {tones_list}
- homiletic_functions (1-2 db): {functions_list}

SZIGORÚ SZABÁLYOK a fenti három listára (Phase 3J.1 — a leggyakoribb \
elutasítási ok éppen e szabályok megsértése volt):
- minden topics/tone/homiletic_functions érték KARAKTERRŐL KARAKTERRE \
  egyezzen meg a fenti listák egyikével — pontosan úgy írva, ahogy ott \
  áll (kisbetű, ékezet NÉLKÜL, aláhúzásokkal, pl. "eszesseg", NEM \
  "eszesség", NEM "eszessegg", NEM semmilyen más alak);
- NE fordítsd vissza magyar ékezetes alakra, és NE változtass a \
  szóalakon (elgépelés, toldalék, kötőjel stb.) — a validátor szó \
  szerinti egyezést ellenőriz;
- ha egy fogalom rokon értelmű valamelyik listaelemmel, de nem AZONOS \
  vele, TILOS új, hasonló hangzású vagy szinonim címkét kitalálni — \
  pl. "szorgalom", "nagylelkűség", "kitartás", "hűség", "csalás" NEM \
  szerepelnek egyik listán sem, ezért MÉG AKKOR SEM használhatók, ha \
  a történethez jól illenének;
- ha a topics-lista egyik eleme sem illik VALÓBAN jelentésben a \
  történethez, VÁLASSZ KEVESEBBET (akár csak 1 topicot, a leginkább \
  releváns egyet) — az 1-3-as tartomány FELSŐ határ, nem kötelező \
  mindig 2-3-at megadni; egy hiányzó, de pontos topic jobb, mint egy \
  kitalált, közel álló címke.

VÁLASZOLJ KIZÁRÓLAG JSON OBJEKTUMMAL, más szöveg nélkül.

{json_shape_section}"""


__all__ = [
    "DEFAULT_PROMPT_VERSION",
    "PILOT_HOMILETIC_FUNCTIONS",
    "PILOT_TONES",
    "PILOT_TOPICS",
    "EnrichmentResult",
    "ProposedUnit",
    "build_enrichment_prompt",
    "enrich_story",
    "is_legacy_strategy_mismatch",
]
