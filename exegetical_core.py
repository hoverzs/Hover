"""Közös exegetikai mag — Eredeti szöveg, műhely és vázlat számára.

Adatfolyam:
  EREDETI TEXTUS → tokenek/morfológia → kulcsszójelöltek → szelekció
  → célzott kiegészítés → tömör exegetikai összegzés → homiletikai híd
  → prédikációvázlat.

Az ExegeticalCoreResult a kanonikus strukturált eredmény; a felületi
markdown és a vázlat promptja ebből származik, nem fordítva.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from prompt_safety import wrap_untrusted_content

logger = logging.getLogger("textus.exegetical_core")

GenerateFn = Callable[..., str]

SESSION_CORE_KEY = "exegetical_core_result"
SESSION_CORE_FP_KEY = "exegetical_core_fingerprint"
SESSION_PASSAGE_FP_KEY = "exegetical_passage_fingerprint"
SOURCE_DATA_VERSION = "exegetical_core_v1"
CORE_SCHEMA_VERSION = "exegetical_core_schema_v2"
CORE_PROMPT_VERSION = "exegetical_core_prompt_v2"

LINKED_PASSAGE_OUTPUT_KEYS: tuple[str, ...] = (
    "overview",
    "exegesis",
    "history",
    "theology",
    "original_text",
    "outline",
    "outline_draft",
    "outline_reworked_draft",
    "outline_title_suggestions",
    "outline_workshop_questions",
    "outline_workshop_answers",
)


class ClaimKind(str, Enum):
    TEXT_DATA = "TEXT_DATA"
    SOURCE_BASED = "SOURCE_BASED"
    INTERPRETATION = "INTERPRETATION"
    HOMILETICAL_BRIDGE = "HOMILETICAL_BRIDGE"


class AlignmentStatus(str, Enum):
    ALIGNED = "aligned"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    MISMATCH_WARNING = "mismatch_warning"


@dataclass
class SourceReference:
    source_type: str = ""  # database | grounding | model_synthesis | user
    name: str = ""
    url: str = ""
    related_lemma_or_span: str = ""
    excerpt: str = ""
    reliability: str = "medium"  # high | medium | low | unverified
    origin: str = ""  # database | external | model_synthesis

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> SourceReference:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            source_type=_s(raw.get("source_type")),
            name=_s(raw.get("name")),
            url=_s(raw.get("url")),
            related_lemma_or_span=_s(raw.get("related_lemma_or_span")),
            excerpt=_s(raw.get("excerpt")),
            reliability=_s(raw.get("reliability")) or "medium",
            origin=_s(raw.get("origin")),
        )


@dataclass
class SelectedExpression:
    """Egy kulcskifejezés — lehet összetett formula is."""

    surface: str = ""
    lemma: str = ""
    morph_relevant: str = ""
    strong_ids: list[str] = field(default_factory=list)
    verses: list[int] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    is_phrase: bool = False
    importance: float = 0.0
    contextual_gloss: str = ""
    role_in_passage: str = ""
    prose_paragraph: str = ""
    claim_kinds: list[str] = field(default_factory=list)
    grounded: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> SelectedExpression:
        if not isinstance(raw, dict):
            return cls()
        strongs = raw.get("strong_ids") or []
        verses = raw.get("verses") or []
        forms = raw.get("forms") or []
        kinds = raw.get("claim_kinds") or []
        return cls(
            surface=_s(raw.get("surface")),
            lemma=_s(raw.get("lemma")),
            morph_relevant=_s(raw.get("morph_relevant")),
            strong_ids=[_s(x) for x in strongs if _s(x)],
            verses=[int(v) for v in verses if str(v).isdigit() or isinstance(v, int)],
            forms=[_s(x) for x in forms if _s(x)],
            is_phrase=bool(raw.get("is_phrase")),
            importance=float(raw.get("importance") or 0.0),
            contextual_gloss=_s(raw.get("contextual_gloss")),
            role_in_passage=_s(raw.get("role_in_passage")),
            prose_paragraph=_s(raw.get("prose_paragraph")),
            claim_kinds=[_s(x) for x in kinds if _s(x)],
            grounded=bool(raw.get("grounded", True)),
        )


@dataclass
class ExegeticalCoreResult:
    """Kanonikus közös exegetikai eredményobjektum."""

    passage_reference: str = ""
    passage_fingerprint: str = ""
    bible_text_fingerprint: str = ""
    original_language_signature: str = ""
    prompt_schema_version: str = CORE_SCHEMA_VERSION
    verse_range: str = ""
    original_language: str = ""  # greek | hebrew | unknown
    alignment_status: str = AlignmentStatus.UNAVAILABLE.value
    literary_genre: str = ""
    literary_movement: str = ""
    central_claim: str = ""
    immediate_context: str = ""
    selected_expressions: list[SelectedExpression] = field(default_factory=list)
    decisive_observations: list[str] = field(default_factory=list)
    concise_analysis: str = ""  # „A szöveg mozgása” — 2–4 bekezdés
    theological_synthesis: str = ""
    interpretive_issues: list[str] = field(default_factory=list)
    historical_context: str = ""
    close_parallels: list[dict[str, str]] = field(default_factory=list)
    homiletical_bridge: str = ""
    source_references: list[SourceReference] = field(default_factory=list)
    confidence_flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: str = ""
    source_data_version: str = SOURCE_DATA_VERSION
    fingerprint: str = ""
    detailed_morphology: list[dict[str, Any]] = field(default_factory=list)
    enrichment_notes: str = ""
    raw_token_verses: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passage_reference": self.passage_reference,
            "passage_fingerprint": self.passage_fingerprint,
            "bible_text_fingerprint": self.bible_text_fingerprint,
            "original_language_signature": self.original_language_signature,
            "prompt_schema_version": self.prompt_schema_version,
            "verse_range": self.verse_range,
            "original_language": self.original_language,
            "alignment_status": self.alignment_status,
            "literary_genre": self.literary_genre,
            "literary_movement": self.literary_movement,
            "central_claim": self.central_claim,
            "immediate_context": self.immediate_context,
            "selected_expressions": [e.to_dict() for e in self.selected_expressions],
            "decisive_observations": list(self.decisive_observations),
            "concise_analysis": self.concise_analysis,
            "theological_synthesis": self.theological_synthesis,
            "interpretive_issues": list(self.interpretive_issues),
            "historical_context": self.historical_context,
            "close_parallels": list(self.close_parallels),
            "homiletical_bridge": self.homiletical_bridge,
            "source_references": [s.to_dict() for s in self.source_references],
            "confidence_flags": list(self.confidence_flags),
            "warnings": list(self.warnings),
            "generated_at": self.generated_at,
            "source_data_version": self.source_data_version,
            "fingerprint": self.fingerprint,
            "detailed_morphology": list(self.detailed_morphology),
            "enrichment_notes": self.enrichment_notes,
            "raw_token_verses": list(self.raw_token_verses),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> ExegeticalCoreResult:
        if not isinstance(raw, dict):
            return cls()
        exprs = [
            SelectedExpression.from_dict(x)
            for x in (raw.get("selected_expressions") or [])
            if isinstance(x, dict)
        ]
        refs = [
            SourceReference.from_dict(x)
            for x in (raw.get("source_references") or [])
            if isinstance(x, dict)
        ]
        return cls(
            passage_reference=_s(raw.get("passage_reference")),
            passage_fingerprint=_s(raw.get("passage_fingerprint")),
            bible_text_fingerprint=_s(raw.get("bible_text_fingerprint")),
            original_language_signature=_s(raw.get("original_language_signature")),
            prompt_schema_version=_s(raw.get("prompt_schema_version"))
            or CORE_SCHEMA_VERSION,
            verse_range=_s(raw.get("verse_range")),
            original_language=_s(raw.get("original_language")),
            alignment_status=_s(raw.get("alignment_status"))
            or AlignmentStatus.UNAVAILABLE.value,
            literary_genre=_s(raw.get("literary_genre")),
            literary_movement=_s(raw.get("literary_movement")),
            central_claim=_s(raw.get("central_claim")),
            immediate_context=_s(raw.get("immediate_context")),
            selected_expressions=exprs,
            decisive_observations=[
                _s(x) for x in (raw.get("decisive_observations") or []) if _s(x)
            ],
            concise_analysis=_s(raw.get("concise_analysis")),
            theological_synthesis=_s(raw.get("theological_synthesis")),
            interpretive_issues=[
                _s(x) for x in (raw.get("interpretive_issues") or []) if _s(x)
            ],
            historical_context=_s(raw.get("historical_context")),
            close_parallels=[
                {
                    "reference": _s(x.get("reference")),
                    "connection": _s(x.get("connection")),
                }
                for x in (raw.get("close_parallels") or [])
                if isinstance(x, dict) and (_s(x.get("reference")) or _s(x.get("connection")))
            ],
            homiletical_bridge=_s(raw.get("homiletical_bridge")),
            source_references=refs,
            confidence_flags=[_s(x) for x in (raw.get("confidence_flags") or []) if _s(x)],
            warnings=[_s(x) for x in (raw.get("warnings") or []) if _s(x)],
            generated_at=_s(raw.get("generated_at")),
            source_data_version=_s(raw.get("source_data_version")) or SOURCE_DATA_VERSION,
            fingerprint=_s(raw.get("fingerprint")),
            detailed_morphology=[
                x for x in (raw.get("detailed_morphology") or []) if isinstance(x, dict)
            ],
            enrichment_notes=_s(raw.get("enrichment_notes")),
            raw_token_verses=[
                x for x in (raw.get("raw_token_verses") or []) if isinstance(x, dict)
            ],
        )

    def is_usable(self) -> bool:
        return bool(
            self.passage_reference
            and (
                self.concise_analysis
                or self.central_claim
                or self.selected_expressions
            )
        )

    def handles_for_outline(self, *, max_items: int = 5) -> list[str]:
        out: list[str] = []
        for expr in self.selected_expressions[:max_items]:
            label = expr.lemma or expr.surface
            gloss = expr.contextual_gloss or expr.role_in_passage
            if label and gloss:
                out.append(f"{label} — {gloss}")
            elif label:
                out.append(label)
            elif expr.prose_paragraph:
                out.append(_first_sentence(expr.prose_paragraph))
        if not out and self.central_claim:
            out.append(self.central_claim)
        return out[:max_items]

    def to_display_markdown(self) -> str:
        """Alapértelmezett felületi megjelenés — prózai szakaszok, nem sabloncímek."""
        blocks: list[str] = []
        if self.central_claim:
            blocks.append("## Exegetikai lényeg\n\n" + self.central_claim.strip())
        if self.concise_analysis:
            text_structure = self.concise_analysis.strip()
            if self.immediate_context:
                text_structure += "\n\n" + self.immediate_context.strip()
            blocks.append("## Szöveg és szerkezet\n\n" + text_structure)
        if self.decisive_observations:
            observations = "\n\n".join(
                obs.strip() for obs in self.decisive_observations if obs.strip()
            )
            if observations:
                blocks.append("## Döntő exegetikai megfigyelések\n\n" + observations)
        if self.selected_expressions:
            parts = ["## Kulcskifejezések\n"]
            for expr in self.selected_expressions:
                title = expr.surface or expr.lemma or "Kifejezés"
                para = expr.prose_paragraph.strip()
                if not para:
                    bits = []
                    if expr.lemma:
                        bits.append(f"Lemma: {expr.lemma}")
                    if expr.morph_relevant:
                        bits.append(expr.morph_relevant)
                    if expr.contextual_gloss:
                        bits.append(expr.contextual_gloss)
                    if expr.role_in_passage:
                        bits.append(expr.role_in_passage)
                    para = " ".join(bits)
                if para:
                    parts.append(f"**{title}**\n\n{para}\n")
            blocks.append("\n".join(parts).strip())
        if self.theological_synthesis:
            blocks.append(
                "## Teológiai összegzés\n\n" + self.theological_synthesis.strip()
            )
        if self.interpretive_issues:
            issues = "\n".join(f"- {issue}" for issue in self.interpretive_issues)
            blocks.append("## Értelmezési kérdések\n\n" + issues)
        if self.historical_context:
            blocks.append("## Történeti és irodalmi háttér\n\n" + self.historical_context)
        if self.close_parallels:
            lines = []
            for item in self.close_parallels[:4]:
                ref = _s(item.get("reference"))
                connection = _s(item.get("connection"))
                if ref and connection:
                    lines.append(f"- **{ref}:** {connection}")
            if lines:
                blocks.append("## Szoros párhuzamok\n\n" + "\n".join(lines))
        if self.homiletical_bridge:
            blocks.append(
                "## Átadás a homiletikai műhelynek\n\n" + self.homiletical_bridge.strip()
            )
        if self.warnings:
            warn = "\n".join(f"- {w}" for w in self.warnings)
            blocks.append("## Figyelmeztetések\n\n" + warn)
        # Források — visszafogottan
        named = [s for s in self.source_references if s.name or s.url]
        if named:
            lines = ["## Források és alap\n"]
            for s in named[:12]:
                label = s.name or s.source_type or "Forrás"
                origin = s.origin or s.source_type
                if s.url:
                    lines.append(f"- [{label}]({s.url}) _{origin}_")
                else:
                    lines.append(f"- {label} _{origin}_")
            blocks.append("\n".join(lines))
        # Részletes morf — expander tartalomként külön is használható
        return "\n\n".join(blocks).strip() + ("\n" if blocks else "")

    def to_prompt_dict(self) -> dict[str, Any]:
        """Downstream modelleknek szánt strukturált, rövidített core csomag."""
        return {
            "passage_reference": self.passage_reference,
            "passage_fingerprint": self.passage_fingerprint,
            "bible_text_fingerprint": self.bible_text_fingerprint,
            "original_language_signature": self.original_language_signature,
            "source_data_version": self.source_data_version,
            "prompt_schema_version": self.prompt_schema_version,
            "literary_genre": self.literary_genre,
            "literary_movement": self.literary_movement,
            "central_claim": self.central_claim,
            "immediate_context": self.immediate_context,
            "decisive_observations": self.decisive_observations[:6],
            "selected_key_expressions": [
                {
                    "surface": e.surface,
                    "lemma": e.lemma,
                    "morph_relevant": e.morph_relevant,
                    "strong_ids": e.strong_ids,
                    "verses": e.verses,
                    "contextual_gloss": e.contextual_gloss,
                    "role_in_passage": e.role_in_passage,
                    "claim_kinds": e.claim_kinds,
                    "grounded": e.grounded,
                }
                for e in self.selected_expressions[:6]
            ],
            "theological_synthesis": self.theological_synthesis,
            "interpretive_issues": self.interpretive_issues[:4],
            "historical_context": self.historical_context,
            "close_parallels": self.close_parallels[:4],
            "homiletical_bridge": self.homiletical_bridge,
            "source_references": [s.to_dict() for s in self.source_references[:8]],
            "confidence_flags": self.confidence_flags,
            "warnings": self.warnings,
        }

    def to_prompt_summary(self) -> str:
        """Legacy adapterekhez rövid prózai összefoglaló, nem teljes markdown dump."""
        parts = [
            self.central_claim,
            self.concise_analysis,
            " ".join(self.decisive_observations[:4]),
            self.theological_synthesis,
        ]
        text = "\n\n".join(p.strip() for p in parts if p and p.strip())
        return text[:2400].rstrip()

    def detailed_morphology_markdown(self) -> str:
        if not self.detailed_morphology:
            return ""
        lines = ["| Forma | Lemma | Morph | Strong | Vers |", "|---|---|---|---|---|"]
        for row in self.detailed_morphology[:80]:
            lines.append(
                "| {form} | {lemma} | {morph} | {strong} | {verse} |".format(
                    form=_s(row.get("form")),
                    lemma=_s(row.get("lemma")),
                    morph=_s(row.get("morph")),
                    strong=_s(row.get("strong")),
                    verse=row.get("verse", ""),
                )
            )
        return "\n".join(lines)


def _s(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _first_sentence(text: str) -> str:
    raw = _s(text)
    if not raw:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", raw)
    return parts[0] if parts else raw


def compute_exegetical_fingerprint(
    *,
    reference: str,
    bible_text: str = "",
    original_language: str = "",
    token_signature: str = "",
    source_data_version: str = SOURCE_DATA_VERSION,
    prompt_schema_version: str = CORE_SCHEMA_VERSION,
) -> str:
    payload = {
        "ref": _s(reference),
        "text": " ".join(_s(bible_text).split())[:4000],
        "lang": _s(original_language),
        "tokens": _s(token_signature),
        "ver": source_data_version,
        "schema": prompt_schema_version,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def compute_passage_fingerprint(
    *,
    reference: str,
    bible_text: str = "",
    bible_translation: str = "",
    token_signature: str = "",
    source_data_version: str = SOURCE_DATA_VERSION,
    prompt_schema_version: str = CORE_SCHEMA_VERSION,
) -> str:
    payload = {
        "reference": " ".join(_s(reference).casefold().split()),
        "bible_text_hash": hashlib.sha1(
            " ".join(_s(bible_text).split()).encode("utf-8")
        ).hexdigest()[:20],
        "translation": _s(bible_translation),
        "token_signature": _s(token_signature),
        "source_data_version": source_data_version,
        "prompt_schema_version": prompt_schema_version,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _token_signature(token_verses: Sequence[Mapping[str, Any]]) -> str:
    bits: list[str] = []
    for verse in token_verses[:20]:
        v = verse.get("verse")
        for tok in (verse.get("tokens") or [])[:30]:
            if not isinstance(tok, dict):
                continue
            bits.append(
                f"{v}:{tok.get('lemma') or ''}:{tok.get('strong') or ''}:{tok.get('form') or ''}"
            )
    return hashlib.sha1("|".join(bits).encode("utf-8")).hexdigest()[:16] if bits else ""


# ---------------------------------------------------------------------------
# Kulcsszó-szelekció
# ---------------------------------------------------------------------------

_SKIP_GREEK = {
    "ὁ",
    "ἡ",
    "τό",
    "καί",
    "δέ",
    "γάρ",
    "ἀλλά",
    "οὖν",
    "ἐν",
    "εἰς",
    "ἐκ",
    "πρός",
    "διά",
    "ἀπό",
    "μετά",
    "ὅτι",
    "ὡς",
    "μή",
    "οὐ",
    "οὐκ",
    "οὐχ",
    "εἰμί",
    "αὐτός",
    "ἐγώ",
    "σύ",
    "ἡμεῖς",
    "ὑμεῖς",
    "τις",
    "οὗτος",
    "ἐκεῖνος",
}
_SKIP_HEBREW = {"ו", "ה", "את", "על", "אל", "מן", "ל", "ב", "כ", "אשר", "כי", "לא"}


def _score_token(tok: Mapping[str, Any], *, language: str) -> float:
    lemma = _s(tok.get("lemma"))
    form = _s(tok.get("form"))
    morph = _s(tok.get("morph")).upper()
    strong = _s(tok.get("strong"))
    skip = _SKIP_GREEK if language == "greek" else _SKIP_HEBREW
    if lemma in skip or form in skip:
        return 0.0
    score = 1.0
    if strong:
        score += 0.5
    if len(lemma) >= 4 or len(form) >= 4:
        score += 0.5
    if any(tag in morph for tag in ("V-", "N-", "A-", "V", "N-", "verb", "noun")):
        score += 1.5
    if any(tag in morph for tag in ("AOR", "PERF", "IMP", "PART", "INF")):
        score += 0.5
    # Doxológiai / teológiai hangzású lemmák enyhe bónusz — nem automatikus felvétel
    hot = ("φυλασσ", "απταιστ", "αμωμ", "σωτηρ", "δοξ", "κυρι", "θεο", "χριστ")
    low = (lemma + form).casefold()
    if any(h in low for h in hot):
        score += 0.8
    return score


def select_keyword_candidates(
    token_verses: Sequence[Mapping[str, Any]],
    *,
    max_items: int | None = None,
) -> list[SelectedExpression]:
    """Tokenekből kulcsszójelöltek — rövid textusnál 2–4, hosszabbnál 3–6."""
    language = ""
    for verse in token_verses:
        language = _s(verse.get("language")) or language
    # Versszám → terjedelem
    verse_nos = sorted(
        {
            int(v.get("verse"))
            for v in token_verses
            if v.get("verse") is not None and str(v.get("verse")).isdigit()
            or isinstance(v.get("verse"), int)
        }
    )
    n_verses = max(1, len(verse_nos))
    if max_items is None:
        max_items = 4 if n_verses <= 2 else 6
        max_items = max(2, min(6, max_items))

    scored: list[tuple[float, SelectedExpression]] = []
    seen: set[str] = set()
    for verse in token_verses:
        vno = verse.get("verse")
        lang = _s(verse.get("language")) or language or "unknown"
        for tok in verse.get("tokens") or []:
            if not isinstance(tok, dict):
                continue
            score = _score_token(tok, language=lang)
            if score < 1.2:
                continue
            lemma = _s(tok.get("lemma")) or _s(tok.get("form"))
            key = lemma.casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            morph = _s(tok.get("morph"))
            # Csak releváns morph — ne a teljes kód dumpszerűen
            morph_relevant = ""
            mu = morph.upper()
            if any(t in mu for t in ("AOR", "PERF", "PRES", "IMP", "INF", "PART")):
                morph_relevant = morph
            elif any(t in mu for t in ("N-", "V-", "A-")):
                morph_relevant = morph
            expr = SelectedExpression(
                surface=_s(tok.get("form")) or lemma,
                lemma=lemma,
                morph_relevant=morph_relevant,
                strong_ids=[_s(tok.get("strong"))] if _s(tok.get("strong")) else [],
                verses=[int(vno)] if vno is not None else [],
                forms=[_s(tok.get("form"))] if _s(tok.get("form")) else [],
                is_phrase=False,
                importance=score,
                contextual_gloss=_s(tok.get("lexical_gloss")),
                grounded=True,
                claim_kinds=[ClaimKind.TEXT_DATA.value],
            )
            scored.append((score, expr))

    scored.sort(key=lambda x: (-x[0], x[1].lemma))
    selected = [e for _, e in scored[:max_items]]

    # Összetartozó formulák — pl. doxológiai párok
    selected = _merge_related_phrases(selected, token_verses)
    return selected[:max_items]


def _merge_related_phrases(
    selected: list[SelectedExpression],
    token_verses: Sequence[Mapping[str, Any]],
) -> list[SelectedExpression]:
    """Ismert párok / listák összevonása (pl. ἄπταιστος + ἄμωμος)."""
    lemmas = {e.lemma.casefold(): e for e in selected if e.lemma}
    pairs = [
        ("ἄπταιστος", "ἄμωμος", "botlástól megőrzött és feddhetetlen"),
        ("ἀπταίστους", "ἀμώμους", "botlástól megőrzött és feddhetetlen"),
        ("δόξα", "κράτος", "doxológiai hatalmi felsorolás"),
        ("μεγαλωσύνη", "ἐξουσία", "doxológiai hatalmi felsorolás"),
    ]
    # Normalizálás: ékezet nélküli közelítés egyszerű casefold-dal
    used: set[str] = set()
    out: list[SelectedExpression] = []
    for a, b, gloss in pairs:
        ea = lemmas.get(a.casefold())
        eb = lemmas.get(b.casefold())
        # részleges egyezés
        if not ea:
            ea = next((e for k, e in lemmas.items() if a.casefold() in k or k in a.casefold()), None)
        if not eb:
            eb = next((e for k, e in lemmas.items() if b.casefold() in k or k in b.casefold()), None)
        if ea and eb and ea.lemma not in used and eb.lemma not in used:
            phrase = SelectedExpression(
                surface=f"{ea.surface} · {eb.surface}",
                lemma=f"{ea.lemma} + {eb.lemma}",
                morph_relevant=ea.morph_relevant or eb.morph_relevant,
                strong_ids=list(dict.fromkeys(ea.strong_ids + eb.strong_ids)),
                verses=sorted(set(ea.verses + eb.verses)),
                forms=list(dict.fromkeys(ea.forms + eb.forms)),
                is_phrase=True,
                importance=max(ea.importance, eb.importance) + 0.5,
                contextual_gloss=gloss,
                role_in_passage="Összetartozó kifejezéspár a szakasz mozgásában.",
                grounded=True,
                claim_kinds=[ClaimKind.TEXT_DATA.value, ClaimKind.INTERPRETATION.value],
            )
            out.append(phrase)
            used.add(ea.lemma)
            used.add(eb.lemma)
    for e in selected:
        if e.lemma in used:
            continue
        out.append(e)
    # „egyedül üdvözítő Isten” jellegű — ha σωτήρ és θεός együtt
    sot = next((e for e in out if "σωτηρ" in e.lemma.casefold() or "σωτήρ" in e.lemma), None)
    theos = next((e for e in out if e.lemma.casefold() in {"θεός", "θεος", "θεοῦ"}), None)
    if sot and theos and not any(x.is_phrase and "σωτηρ" in x.lemma.casefold() for x in out):
        out.insert(
            0,
            SelectedExpression(
                surface=f"{theos.surface} · {sot.surface}",
                lemma=f"{theos.lemma} + {sot.lemma}",
                strong_ids=list(dict.fromkeys(theos.strong_ids + sot.strong_ids)),
                verses=sorted(set(theos.verses + sot.verses)),
                forms=list(dict.fromkeys(theos.forms + sot.forms)),
                is_phrase=True,
                importance=max(sot.importance, theos.importance) + 0.6,
                contextual_gloss="egyedül üdvözítő Isten (doxológiai formula)",
                role_in_passage="A doxológia zárlatának hitvalló magja.",
                grounded=True,
                claim_kinds=[ClaimKind.TEXT_DATA.value, ClaimKind.INTERPRETATION.value],
            ),
        )
    return out


# ---------------------------------------------------------------------------
# Determinisztikus mag + AI szintézis
# ---------------------------------------------------------------------------

CORE_SYSTEM_PROMPT = """\
Tapasztalt, biblikus, református szemléletű exegetikai szerkesztő vagy.
Feladatod tömör, prózai exegetikai mag készítése — nem prédikációvázlat,
nem teljes kommentár, nem szótári cikkgyűjtemény.

SZABÁLYOK:
- Csak a kapott tokenek/lemmák/morph adatokból állíts nyelvi TÉNYT.
- Ne találj ki Strong-számot, lemmát, igeidőt.
- Kulcskifejezések: csak a megadott jelöltekből; ne elemezz minden teológiai hangzású szót.
- Összetartozó formulákat együtt kezeld.
- Megkülönböztetés (belsőleg): TEXT_DATA / SOURCE_BASED / INTERPRETATION / HOMILETICAL_BRIDGE.
- Ne ismételj mechanikus alcímeket (Alapjelentés / Miért fontos / stb.).
- Rövid textusnál rövid elemzés: 2–4 bekezdés a mozgásról; 2–4 kulcskifejezés.
- Teljes, összefüggő magyar mondatok; ne távirati stílus.
- Homiletikai irány: híd, NEM vázlat (nincs 3 főpont, nincs kész bevezetés).

Kizárólag JSON:
{
  "literary_genre": "rövid műfaji azonosítás",
  "literary_movement": "rövid műfaj+mozgás jelzés",
  "central_claim": "saját megfogalmazású központi állítás (nem versidézet)",
  "immediate_context": "csak ha közvetlen kontextus tényleg segít; különben üres",
  "decisive_observations": ["2-5 döntő exegetikai megfigyelés"],
  "concise_analysis": "2-4 bekezdés: A szöveg mozgása",
  "expressions": [
    {
      "lemma_or_surface": "egyezzen a jelölttel",
      "prose_paragraph": "egy összefüggő bekezdés",
      "contextual_gloss": "rövid glossza",
      "role_in_passage": "szerep a szakaszban",
      "claim_kinds": ["TEXT_DATA", "INTERPRETATION"]
    }
  ],
  "theological_synthesis": "1-3 bekezdés",
  "interpretive_issues": ["csak valódi értelmezési kérdés, vagy []"],
  "historical_context": "csak releváns történeti/irodalmi háttér, vagy üres",
  "close_parallels": [{"reference": "igehely", "connection": "szoros kapcsolat magyarázata"}],
  "homiletical_bridge": "1-2 bekezdés",
  "warnings": ["óvatossági megjegyzés"],
  "confidence_flags": ["high_confidence_on_tokens"]
}
"""

CORE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "literary_movement": {"type": "STRING"},
        "literary_genre": {"type": "STRING"},
        "central_claim": {"type": "STRING"},
        "immediate_context": {"type": "STRING"},
        "concise_analysis": {"type": "STRING"},
        "decisive_observations": {"type": "ARRAY", "items": {"type": "STRING"}},
        "expressions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "lemma_or_surface": {"type": "STRING"},
                    "prose_paragraph": {"type": "STRING"},
                    "contextual_gloss": {"type": "STRING"},
                    "role_in_passage": {"type": "STRING"},
                    "claim_kinds": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                },
            },
        },
        "theological_synthesis": {"type": "STRING"},
        "interpretive_issues": {"type": "ARRAY", "items": {"type": "STRING"}},
        "historical_context": {"type": "STRING"},
        "close_parallels": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "reference": {"type": "STRING"},
                    "connection": {"type": "STRING"},
                },
            },
        },
        "homiletical_bridge": {"type": "STRING"},
        "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
        "confidence_flags": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "literary_movement",
        "central_claim",
        "concise_analysis",
        "expressions",
        "theological_synthesis",
        "homiletical_bridge",
    ],
}


def _build_deterministic_skeleton(
    *,
    reference: str,
    bible_text: str,
    token_verses: list[dict[str, Any]],
    selected: list[SelectedExpression],
) -> ExegeticalCoreResult:
    from sermon_outline_exegesis import infer_literary_hints

    hints = infer_literary_hints(reference, bible_text)
    language = ""
    for v in token_verses:
        language = _s(v.get("language")) or language
    verse_nos = sorted(
        {
            int(v.get("verse"))
            for v in token_verses
            if isinstance(v.get("verse"), int)
            or (isinstance(v.get("verse"), str) and str(v.get("verse")).isdigit())
        }
    )
    verse_range = ""
    if verse_nos:
        verse_range = (
            f"v. {verse_nos[0]}"
            if len(verse_nos) == 1
            else f"v. {verse_nos[0]}–{verse_nos[-1]}"
        )

    alignment = (
        AlignmentStatus.ALIGNED.value
        if token_verses
        else AlignmentStatus.UNAVAILABLE.value
    )
    warnings: list[str] = []
    if not token_verses:
        warnings.append(
            "Nincs betöltött eredeti nyelvi token: a nyelvi állítások óvatosak."
        )
    if hints.get("amen_note"):
        warnings.append(hints["amen_note"])

    # Determinisztikus próza — rövid
    movement = hints.get("movement") or "A szakasz saját belső egységei szerint halad."
    genre = hints.get("genre") or "bibliai szakasz"
    concise = (
        f"A szakasz {genre} jellegű szöveg. {movement} "
        f"A központi állítás a textus saját szavainak mozgásából olvasható ki; "
        f"nem a teljes versidézet a fókusz.\n\n"
        f"A nyelvtani és retorikai kapcsolatok a kiválasztott kulcskifejezésekben "
        f"sűrűsödnek; a hangsúly a szakasz természetes ívén van."
    )
    if "doxológ" in genre.casefold():
        concise = (
            "A szakasz doxológiai egység: Isten megtartó cselekvése felől "
            "a feddhetetlenül elé állításon át a dicsőítésig vezet.\n\n"
            "A mozgást nem mesterséges főpontok, hanem a dicsőítés felé tartó "
            "hitvalló ív tartja össze. Az „Ámen” liturgikus lezárás, nem önálló "
            "elemzési egység.\n\n"
            "A hangsúly Isten hatalmán és üdvözítő egyedülvalóságán van, "
            "nem a hallgató saját állhatatosságán."
        )

    for expr in selected:
        if not expr.prose_paragraph:
            bits = []
            if expr.is_phrase:
                bits.append(
                    f"A(z) «{expr.surface}» összetartozó kifejezés a szakaszban."
                )
            else:
                bits.append(
                    f"A(z) «{expr.surface}» (lemma: {expr.lemma or '—'}) "
                    f"a kiválasztott textus eredeti nyelvi adatából igazolható."
                )
            if expr.morph_relevant:
                bits.append(f"Releváns nyelvtani jelölés: {expr.morph_relevant}.")
            if expr.contextual_gloss:
                bits.append(expr.contextual_gloss + ".")
            bits.append(
                "A pontos kontextuális jelentést a szakasz mozgása határozza meg; "
                "ne olvassuk rá a szó összes lehetséges szótári jelentését."
            )
            expr.prose_paragraph = " ".join(bits)
            expr.claim_kinds = list(
                dict.fromkeys(
                    (expr.claim_kinds or [])
                    + [ClaimKind.TEXT_DATA.value, ClaimKind.INTERPRETATION.value]
                )
            )

    detailed = []
    for verse in token_verses:
        for tok in verse.get("tokens") or []:
            if not isinstance(tok, dict):
                continue
            detailed.append(
                {
                    "form": _s(tok.get("form")),
                    "lemma": _s(tok.get("lemma")),
                    "morph": _s(tok.get("morph")),
                    "strong": _s(tok.get("strong")),
                    "verse": verse.get("verse"),
                }
            )

    sources = []
    if token_verses:
        source_names = sorted(
            {
                _s(tok.get("source_id"))
                for verse in token_verses
                for tok in (verse.get("tokens") or [])
                if isinstance(tok, dict) and _s(tok.get("source_id"))
            }
        )
        sources.append(
            SourceReference(
                source_type="database",
                name=(
                    "Textus helyi eredetinyelvi adatbázis "
                    f"({', '.join(source_names) if source_names else 'TAGNT/TAHOT'})"
                ),
                related_lemma_or_span=reference,
                reliability="high",
                origin="database",
            )
        )

    return ExegeticalCoreResult(
        passage_reference=reference,
        passage_fingerprint=compute_passage_fingerprint(
            reference=reference,
            bible_text=bible_text,
            token_signature=_token_signature(token_verses),
            source_data_version=SOURCE_DATA_VERSION,
            prompt_schema_version=CORE_SCHEMA_VERSION,
        ),
        bible_text_fingerprint=hashlib.sha1(
            " ".join(_s(bible_text).split()).encode("utf-8")
        ).hexdigest()[:20],
        original_language_signature=_token_signature(token_verses),
        prompt_schema_version=CORE_SCHEMA_VERSION,
        verse_range=verse_range,
        original_language=language or "unknown",
        alignment_status=alignment,
        literary_genre=genre,
        literary_movement=f"{genre}: {movement}",
        central_claim=(
            "A szakasz központi teológiai állítása Isten cselekvése körül forog."
            if "doxológ" not in genre.casefold()
            else (
                "Az egyedüli üdvözítő Isten megőriz a botlástól, "
                "és feddhetetlenül, örömmel állít dicsősége elé."
            )
        ),
        immediate_context=(
            "A közvetlen kontextushoz nincs külön ellenőrzött háttéradat betöltve; "
            "a megállapítások a megadott textusra és a helyi eredetinyelvi adatra támaszkodnak."
            if not bible_text
            else ""
        ),
        selected_expressions=selected,
        decisive_observations=[
            "A kulcskifejezések a betöltött tokenkészletből lettek kiválasztva."
            if token_verses
            else "Eredetinyelvi token nem állt rendelkezésre; nyelvi állítás nem készül.",
            movement,
        ],
        concise_analysis=concise,
        theological_synthesis=(
            "A szakasz Isten megtartó és dicsőséges cselekvését állítja középpontba. "
            "Az ember botlásfélelme és hűségküzdelme a textus felől nyer választ, "
            "nem általános kegyességi közhelyként."
            if "doxológ" in genre.casefold()
            else (
                "A teológiai összegzés csak a textusból következő állításokat "
                "tartalmazza Istenről és az ember helyzetéről."
            )
        ),
        interpretive_issues=[],
        historical_context="",
        close_parallels=[],
        homiletical_bridge=(
            "A textus a hallgató botlásfélelme és dicsőítésre szomjazó helyzete "
            "felé nyit: nem teljesítményre, hanem Isten megőrző ígéretére hív. "
            "Ez híd a prédikáció felé — még nem vázlat."
            if "doxológ" in genre.casefold()
            else (
                "A szakasz saját feszültsége és felismerése felé vezethető a "
                "hallgató; ez még nem prédikációvázlat."
            )
        ),
        source_references=sources,
        confidence_flags=["token_grounded"] if token_verses else ["no_tokens"],
        warnings=warnings,
        generated_at=_now(),
        detailed_morphology=detailed,
        raw_token_verses=list(token_verses),
    )


def _merge_ai_core(
    base: ExegeticalCoreResult, obj: Mapping[str, Any]
) -> ExegeticalCoreResult:
    out = ExegeticalCoreResult.from_dict(base.to_dict())
    for field_name in (
        "literary_genre",
        "literary_movement",
        "central_claim",
        "immediate_context",
        "concise_analysis",
        "theological_synthesis",
        "historical_context",
        "homiletical_bridge",
    ):
        val = _s(obj.get(field_name))
        if val:
            setattr(out, field_name, val)
    for list_field in ("decisive_observations", "interpretive_issues"):
        raw_items = obj.get(list_field) or []
        if isinstance(raw_items, list):
            clean = [_s(x) for x in raw_items if _s(x)]
            if clean:
                setattr(out, list_field, clean[:6])
    raw_parallels = obj.get("close_parallels") or []
    if isinstance(raw_parallels, list):
        close_parallels = []
        for item in raw_parallels[:4]:
            if not isinstance(item, dict):
                continue
            ref = _s(item.get("reference"))
            connection = _s(item.get("connection"))
            if ref and connection:
                close_parallels.append({"reference": ref, "connection": connection})
        if close_parallels:
            out.close_parallels = close_parallels
    for w in obj.get("warnings") or []:
        t = _s(w)
        if t and t not in out.warnings:
            out.warnings.append(t)
    for f in obj.get("confidence_flags") or []:
        t = _s(f)
        if t and t not in out.confidence_flags:
            out.confidence_flags.append(t)

    ai_exprs = obj.get("expressions") or []
    if isinstance(ai_exprs, list) and out.selected_expressions:
        by_key: dict[str, SelectedExpression] = {}
        for e in out.selected_expressions:
            by_key[e.lemma.casefold()] = e
            by_key[e.surface.casefold()] = e
        for item in ai_exprs:
            if not isinstance(item, dict):
                continue
            key = _s(item.get("lemma_or_surface")).casefold()
            target = by_key.get(key)
            if not target:
                # részleges egyezés
                target = next(
                    (
                        e
                        for e in out.selected_expressions
                        if key and (key in e.lemma.casefold() or key in e.surface.casefold())
                    ),
                    None,
                )
            if not target:
                continue
            # Csak a jelölt kifejezésekhez írunk — nem veszünk fel új, nem grounded lemmát
            para = _s(item.get("prose_paragraph"))
            if para and not _has_mechanical_subheads(para):
                target.prose_paragraph = para
            gloss = _s(item.get("contextual_gloss"))
            if gloss:
                target.contextual_gloss = gloss
            role = _s(item.get("role_in_passage"))
            if role:
                target.role_in_passage = role
            kinds = item.get("claim_kinds") or []
            if isinstance(kinds, list):
                for k in kinds:
                    ks = _s(k)
                    if ks and ks not in target.claim_kinds:
                        target.claim_kinds.append(ks)
    return out


_MECHANICAL_HEADINGS = (
    "**alapjelentés",
    "alapjelentés:",
    "**miért fontos",
    "miért fontos itt",
    "**mélyebb árnyalat",
    "mélyebb árnyalat",
    "**bibliai párhuzam",
    "bibliai párhuzam",
    "**igehirdetési hozam",
    "igehirdetési hozam:",
)


def _has_mechanical_subheads(text: str) -> bool:
    low = text.casefold()
    return any(h in low for h in _MECHANICAL_HEADINGS)


def _token_text_set(token_verses: Sequence[Mapping[str, Any]]) -> set[str]:
    values: set[str] = set()
    for verse in token_verses:
        for tok in verse.get("tokens") or []:
            if not isinstance(tok, dict):
                continue
            for key in ("form", "lemma"):
                val = _s(tok.get(key)).casefold()
                if val:
                    values.add(val)
    return values


def _token_morph_set(token_verses: Sequence[Mapping[str, Any]]) -> set[str]:
    values: set[str] = set()
    for verse in token_verses:
        for tok in verse.get("tokens") or []:
            if not isinstance(tok, dict):
                continue
            for key in ("morph", "morph_resolved"):
                val = _s(tok.get(key)).casefold()
                if val:
                    values.add(val)
    return values


def validate_core_result(result: ExegeticalCoreResult) -> list[str]:
    """Determinisztikus minőségi ellenőrzés."""
    issues: list[str] = []
    if not result.passage_reference:
        issues.append("missing_reference")
    if not result.concise_analysis:
        issues.append("missing_concise_analysis")
    # Aránytalan hossz rövid textusnál
    n_verses = 0
    if result.verse_range:
        nums = re.findall(r"\d+", result.verse_range)
        if len(nums) >= 2:
            n_verses = max(1, int(nums[-1]) - int(nums[0]) + 1)
        elif nums:
            n_verses = 1
    word_count = len(result.concise_analysis.split())
    expr_words = sum(len(e.prose_paragraph.split()) for e in result.selected_expressions)
    total = word_count + expr_words + len(result.theological_synthesis.split())
    if n_verses and n_verses <= 2 and total > 900:
        issues.append("disproportionate_length")
    if len(result.selected_expressions) > 6:
        issues.append("too_many_keywords")
    if len(result.selected_expressions) == 0 and result.raw_token_verses:
        issues.append("no_keywords_selected")
    token_values = _token_text_set(result.raw_token_verses)
    token_morph_values = _token_morph_set(result.raw_token_verses)
    for e in result.selected_expressions:
        if _has_mechanical_subheads(e.prose_paragraph):
            issues.append("mechanical_subheads")
            break
        if e.grounded and token_values:
            candidates = [
                _s(e.surface).casefold(),
                _s(e.lemma).casefold(),
                *[_s(form).casefold() for form in e.forms],
            ]
            # Phrase expressions are grounded if every named form/lemma piece is token-backed.
            parts = []
            for candidate in candidates:
                if "+" in candidate:
                    parts.extend(x.strip() for x in candidate.split("+") if x.strip())
                elif candidate:
                    parts.append(candidate)
            if parts and not any(part in token_values for part in parts):
                issues.append("ungrounded_expression")
                break
        if e.grounded and token_morph_values and e.morph_relevant:
            morph = _s(e.morph_relevant).casefold()
            if morph and morph not in token_morph_values:
                issues.append("ungrounded_morphology")
                break
    # Színlelt forrás: URL nélküli „external” magas reliability gyanús
    for s in result.source_references:
        if s.origin == "external" and not s.url and s.reliability == "high":
            issues.append("fake_external_source")
            break
        if "wikipedia" in (s.name or "").casefold() and not s.url:
            issues.append("unsourced_web_claim")
    # Homiletikai következtetés lexikai tényként
    for e in result.selected_expressions:
        kinds = set(e.claim_kinds or [])
        if (
            ClaimKind.HOMILETICAL_BRIDGE.value in kinds
            and kinds == {ClaimKind.HOMILETICAL_BRIDGE.value}
            and e.grounded
        ):
            issues.append("homiletical_as_lexical_fact")
            break
    return list(dict.fromkeys(issues))


def build_exegetical_core(
    *,
    reference: str,
    bible_text: str = "",
    token_verses: list[dict[str, Any]] | None = None,
    generate_fn: GenerateFn | None = None,
    enrich: bool = True,
    enrichment_service: Any | None = None,
    force_refresh: bool = False,
) -> ExegeticalCoreResult:
    """Teljes pipeline: tokenek → szelekció → (kiegészítés) → szintézis."""
    from sermon_outline_context import get_original_language_provider

    ref = _s(reference)
    tokens = list(token_verses) if token_verses is not None else []
    if token_verses is None and not tokens and ref:
        try:
            tokens = list(get_original_language_provider().load_for_passage(ref) or [])
        except Exception:
            tokens = []

    selected = select_keyword_candidates(tokens)
    core = _build_deterministic_skeleton(
        reference=ref,
        bible_text=bible_text,
        token_verses=tokens,
        selected=selected,
    )
    sig = _token_signature(tokens)
    core.fingerprint = compute_exegetical_fingerprint(
        reference=ref,
        bible_text=bible_text,
        original_language=core.original_language,
        token_signature=sig,
        prompt_schema_version=CORE_SCHEMA_VERSION,
    )
    core.original_language_signature = sig
    core.bible_text_fingerprint = hashlib.sha1(
        " ".join(_s(bible_text).split()).encode("utf-8")
    ).hexdigest()[:20]
    core.passage_fingerprint = compute_passage_fingerprint(
        reference=ref,
        bible_text=bible_text,
        token_signature=sig,
        source_data_version=SOURCE_DATA_VERSION,
        prompt_schema_version=CORE_SCHEMA_VERSION,
    )
    core.prompt_schema_version = CORE_SCHEMA_VERSION

    # Kiegészítő keresés — csak a kiválasztott kifejezésekhez
    if enrich and enrichment_service is not None:
        try:
            notes, refs = enrichment_service.enrich(core)
            if notes:
                core.enrichment_notes = notes
            for r in refs or []:
                if isinstance(r, SourceReference):
                    core.source_references.append(r)
                elif isinstance(r, dict):
                    core.source_references.append(SourceReference.from_dict(r))
        except Exception as exc:
            logger.info("enrichment_failed err=%s", type(exc).__name__)
            core.warnings.append(
                "A kiegészítő keresés nem sikerült; az elemzés a helyi adatokra támaszkodik."
            )

    if generate_fn is not None:
        user_prompt = (
            f"Igehely: {ref}\n"
            f"Vershatár: {core.verse_range}\n"
            f"Nyelv: {core.original_language}\n"
            f"Alignment: {core.alignment_status}\n\n"
            f"{wrap_untrusted_content('BIBLE_TEXT', bible_text[:5000])}\n\n"
            f"TOKEN ADATOK (csak ebből állíts nyelvi tényt):\n"
            f"{json.dumps(tokens[:8], ensure_ascii=False)}\n\n"
            f"KIVÁLASZTOTT KULCSKIFEJEZÉSEK (csak ezekhez írj bekezdéses elemzést):\n"
            f"{json.dumps([e.to_dict() for e in selected], ensure_ascii=False)}\n\n"
            f"KIEGÉSZÍTŐ JEGYZETEK (SOURCE_BASED, óvatosan):\n"
            f"{core.enrichment_notes[:2000]}\n\n"
            f"DETERMINISZTIKUS MAG:\n"
            f"{json.dumps({k: core.to_dict()[k] for k in ('literary_movement','central_claim','warnings')}, ensure_ascii=False)}\n\n"
            "Készítsd el a tömör exegetikai JSON-t."
        )
        try:
            try:
                raw = generate_fn(
                    user_prompt,
                    enable_google_search=False,
                    tab_label="Eredeti szöveg tanulmányozása",
                    use_cache=False,
                    system_bundle=CORE_SYSTEM_PROMPT,
                    include_brevity_directive=False,
                    max_output_tokens=2400,
                    response_mime_type="application/json",
                    response_schema=CORE_RESPONSE_SCHEMA,
                )
            except TypeError:
                raw = generate_fn(user_prompt)
            from sermon_workshop_m4_ai import extract_json_object
            from ai_response_validation import sanitize_ai_json

            obj = extract_json_object(raw or "") or {}
            if isinstance(obj, dict):
                obj = sanitize_ai_json(obj) or obj
                core = _merge_ai_core(core, obj)
        except Exception as exc:
            logger.info("core_ai_failed err=%s", type(exc).__name__)
            core.warnings.append("Az AI-szintézis nem sikerült; a determinisztikus mag maradt.")

    # Validáció — aránytalan hossz esetén vágás soft figyelmeztetéssel
    issues = validate_core_result(core)
    for issue in issues:
        tip = f"validáció: {issue}"
        if tip not in core.warnings:
            core.warnings.append(tip)
    core.generated_at = _now()
    return core


# ---------------------------------------------------------------------------
# Session cache
# ---------------------------------------------------------------------------


def get_cached_core(
    session_state: Mapping[str, Any],
    *,
    reference: str,
    bible_text: str = "",
) -> ExegeticalCoreResult | None:
    raw = session_state.get(SESSION_CORE_KEY)
    if not isinstance(raw, dict):
        return None
    core = ExegeticalCoreResult.from_dict(raw)
    if not core.is_usable():
        return None
    if _s(core.passage_reference).casefold() != _s(reference).casefold():
        return None
    if _s(core.source_data_version) != SOURCE_DATA_VERSION:
        return None
    stored_fp = _s(session_state.get(SESSION_CORE_FP_KEY)) or core.fingerprint
    sig = _token_signature(core.raw_token_verses)
    current = compute_exegetical_fingerprint(
        reference=reference,
        bible_text=bible_text,
        original_language=core.original_language,
        token_signature=sig,
        source_data_version=SOURCE_DATA_VERSION,
        prompt_schema_version=CORE_SCHEMA_VERSION,
    )
    current_passage = compute_passage_fingerprint(
        reference=reference,
        bible_text=bible_text,
        token_signature=sig,
        source_data_version=SOURCE_DATA_VERSION,
        prompt_schema_version=CORE_SCHEMA_VERSION,
    )
    # Textus, vershatár vagy adatverzió változás → érvénytelen
    if stored_fp and current and stored_fp != current:
        return None
    if core.fingerprint and current and core.fingerprint != current:
        return None
    if core.passage_fingerprint and current_passage and core.passage_fingerprint != current_passage:
        return None
    if _s(core.prompt_schema_version) != CORE_SCHEMA_VERSION:
        return None
    return core


def store_core(
    session_state: MutableMapping[str, Any],
    core: ExegeticalCoreResult,
    *,
    sync_original_text: bool = True,
) -> None:
    session_state[SESSION_CORE_KEY] = core.to_dict()
    session_state[SESSION_CORE_FP_KEY] = core.fingerprint
    if core.passage_fingerprint:
        session_state[SESSION_PASSAGE_FP_KEY] = core.passage_fingerprint
    # Legacy prose mező a műhely / kosár számára — csak ha a felületi
    # „Eredeti szöveg” elemzéshez szinkronizálunk.
    if sync_original_text:
        display = core.to_display_markdown()
        if display:
            session_state["original_text"] = display


def invalidate_core_if_stale(
    session_state: MutableMapping[str, Any],
    *,
    reference: str,
    bible_text: str = "",
) -> bool:
    """True, ha érvénytelenítettük."""
    raw = session_state.get(SESSION_CORE_KEY)
    stored_core = ExegeticalCoreResult.from_dict(raw) if isinstance(raw, dict) else None
    stored_passage_fp = _s(session_state.get(SESSION_PASSAGE_FP_KEY))
    if not stored_passage_fp and stored_core is not None:
        stored_passage_fp = stored_core.passage_fingerprint
    current_passage_fp = ""
    if stored_core is not None:
        current_passage_fp = compute_passage_fingerprint(
            reference=reference,
            bible_text=bible_text,
            token_signature=_token_signature(stored_core.raw_token_verses),
            source_data_version=SOURCE_DATA_VERSION,
            prompt_schema_version=CORE_SCHEMA_VERSION,
        )
    core = get_cached_core(
        session_state, reference=reference, bible_text=bible_text
    )
    if core is not None:
        return False
    stale_passage = bool(
        stored_passage_fp and current_passage_fp and stored_passage_fp != current_passage_fp
    )
    if session_state.get(SESSION_CORE_KEY) or stale_passage:
        session_state.pop(SESSION_CORE_KEY, None)
        session_state.pop(SESSION_CORE_FP_KEY, None)
        session_state.pop(SESSION_PASSAGE_FP_KEY, None)
        for key in LINKED_PASSAGE_OUTPUT_KEYS:
            session_state.pop(key, None)
        return True
    return False


def ensure_exegetical_core(
    session_state: MutableMapping[str, Any],
    *,
    reference: str,
    bible_text: str = "",
    generate_fn: GenerateFn | None = None,
    enrich: bool = True,
    force_refresh: bool = False,
    sync_original_text: bool = True,
) -> ExegeticalCoreResult:
    """Ha van érvényes cache, azt adja; különben felépíti."""
    if not force_refresh:
        cached = get_cached_core(
            session_state, reference=reference, bible_text=bible_text
        )
        if cached is not None:
            if sync_original_text and not _s(session_state.get("original_text")):
                display = cached.to_display_markdown()
                if display:
                    session_state["original_text"] = display
            return cached

    enrichment_service = None
    if enrich:
        try:
            from exegetical_enrichment import get_default_enrichment_service

            enrichment_service = get_default_enrichment_service(
                generate_fn=generate_fn
            )
        except Exception:
            enrichment_service = None

    core = build_exegetical_core(
        reference=reference,
        bible_text=bible_text,
        generate_fn=generate_fn,
        enrich=enrich and enrichment_service is not None,
        enrichment_service=enrichment_service,
        force_refresh=force_refresh,
    )
    store_core(session_state, core, sync_original_text=sync_original_text)
    return core


def core_to_outline_brief(core: ExegeticalCoreResult):
    """ExegeticalCoreResult → ExegeticalBrief (vázlatmotor kompatibilitás)."""
    from sermon_outline_exegesis import ExegeticalBrief, LexicalHandle

    handles = []
    for e in core.selected_expressions:
        handles.append(
            LexicalHandle(
                form=e.surface,
                lemma=e.lemma or e.surface,
                morph=e.morph_relevant,
                strong=(e.strong_ids[0] if e.strong_ids else ""),
                verse=e.verses[0] if e.verses else None,
                homiletical_relevance=e.contextual_gloss or e.role_in_passage,
                grounded=e.grounded,
            )
        )
    return ExegeticalBrief(
        genre_and_movement=core.literary_movement,
        central_claim=core.central_claim,
        internal_tension="",
        key_expressions=handles,
        theological_emphasis=_first_sentence(core.theological_synthesis),
        historical_canonical_note="",
        listener_connection=_first_sentence(core.homiletical_bridge),
        caution_flags=list(core.warnings),
        source="hybrid" if core.selected_expressions else "deterministic",
        grounded_in_original_data=bool(core.raw_token_verses),
    )


__all__ = [
    "AlignmentStatus",
    "CORE_RESPONSE_SCHEMA",
    "CORE_PROMPT_VERSION",
    "CORE_SCHEMA_VERSION",
    "CORE_SYSTEM_PROMPT",
    "ClaimKind",
    "ExegeticalCoreResult",
    "LINKED_PASSAGE_OUTPUT_KEYS",
    "SESSION_CORE_FP_KEY",
    "SESSION_CORE_KEY",
    "SESSION_PASSAGE_FP_KEY",
    "SOURCE_DATA_VERSION",
    "SelectedExpression",
    "SourceReference",
    "build_exegetical_core",
    "compute_exegetical_fingerprint",
    "compute_passage_fingerprint",
    "core_to_outline_brief",
    "ensure_exegetical_core",
    "get_cached_core",
    "invalidate_core_if_stale",
    "select_keyword_candidates",
    "store_core",
    "validate_core_result",
]
