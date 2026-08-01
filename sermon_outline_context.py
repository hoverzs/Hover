"""Strukturált vázlatkontextus — forrástípusok, prioritás, BARE/PARTIAL/RICH módok.

A modell nem egyetlen összeöntött FORRÁS blokkot kap, hanem típusozott,
prioritizált szakaszokat. Az AI által korábban előállított anyag soha nem
kap azonos súlyt a bibliai textussal vagy az ellenőrizhető eredeti nyelvi
adatokkal.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, MutableMapping, Protocol

from sermon_workshop_data import SERMON_WORKSHOP_KEY

ORIGINAL_LANGUAGE_DATA_VERSION = "original_language_provider_v2"


class SourcePriority(int, Enum):
    """Alacsonyabb szám = magasabb prioritás."""

    BIBLE_TEXT = 1
    ORIGINAL_LANGUAGE = 2
    EXEGETICAL_BACKGROUND = 3
    USER_DECISIONS = 4
    HOMILETICAL_METHOD = 5
    MODEL_SUPPLEMENT = 6


class ContextMode(str, Enum):
    BARE = "BARE"
    PARTIAL = "PARTIAL"
    RICH = "RICH"


class OriginalLanguageProvider(Protocol):
    """Bővíthető interfész eredeti nyelvi adatokhoz (TAGNT / TBESH / későbbi DB)."""

    def load_for_passage(self, reference: str) -> list[dict[str, Any]]:
        """Versenkénti tokenek / lemmák / morfológia — kitalálás nélkül."""
        ...


@dataclass
class SourceBlock:
    kind: str
    priority: SourcePriority
    available: bool
    origin: str
    payload: Any = None
    notes: str = ""

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "priority": int(self.priority),
            "priority_label": self.priority.name,
            "available": self.available,
            "origin": self.origin,
            "notes": self.notes,
            "payload": self.payload if self.available else None,
        }


@dataclass
class OutlineContext:
    """Teljes, típusozott vázlatkontextus a generáláshoz."""

    passage_reference: str = ""
    bible_text: str = ""
    bible_translation: str = "RÚF 2014"
    original_language_data: list[dict[str, Any]] = field(default_factory=list)
    exegetical_material: str = ""
    homiletical_preferences: dict[str, Any] = field(default_factory=dict)
    outline_basket: list[Any] = field(default_factory=list)
    user_notes: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)
    context_mode: ContextMode = ContextMode.BARE
    sources: list[SourceBlock] = field(default_factory=list)
    # Extra workshop fields (nem AI-súlyú, de hasznos)
    occasion: str = ""
    user_focus: str = ""
    theology: str = ""
    history: str = ""
    original_text_prose: str = ""
    exegetical_core: dict[str, Any] = field(default_factory=dict)
    approved_insights: list[str] = field(default_factory=list)
    approved_sermon_decisions: list[str] = field(default_factory=list)
    sermon_main_idea: str = ""
    text_main_idea: str = ""
    sermon_movements: list[dict[str, Any]] = field(default_factory=list)
    rapid_evidence: dict[str, Any] | None = None
    legacy_bundle: dict[str, Any] = field(default_factory=dict)

    def has_original_language(self) -> bool:
        return bool(self.original_language_data)

    def has_exegetical(self) -> bool:
        return bool(self.exegetical_core or self.exegetical_material.strip())

    def has_homiletical(self) -> bool:
        prefs = self.homiletical_preferences or {}
        return any(
            prefs.get(k) not in (None, "", [], {})
            for k in (
                "human_condition",
                "listener_tension",
                "christ_centered_arc",
                "sermon_path",
                "closing",
                "method_lens",
            )
        )

    def has_user_decisions(self) -> bool:
        return bool(
            self.user_notes.strip()
            or self.user_focus.strip()
            or self.sermon_main_idea.strip()
            or self.approved_sermon_decisions
            or self.outline_basket
        )

    def to_prompt_sections(self) -> dict[str, Any]:
        """Elkülönített promptszakaszok prioritás szerint."""
        sections: dict[str, Any] = {
            "context_mode": self.context_mode.value,
            "source_priority_order": [
                "bible_text",
                "original_language_data",
                "exegetical_core",
                "exegetical_material",
                "user_decisions_and_notes",
                "outline_basket",
                "homiletical_preferences",
                "model_supplement",
            ],
            "passage_reference": self.passage_reference,
            "bible_text": self.bible_text,
            "bible_translation": self.bible_translation,
            "original_language_data": self.original_language_data,
            "user_decisions_and_notes": {
                "user_focus": self.user_focus,
                "user_notes": self.user_notes,
                "sermon_main_idea": self.sermon_main_idea,
                "text_main_idea": self.text_main_idea,
                "approved_sermon_decisions": self.approved_sermon_decisions,
                "approved_insights": self.approved_insights,
                "occasion": self.occasion,
            },
            "exegetical_material": self.exegetical_material,
            "exegetical_core": self.exegetical_core,
            "homiletical_preferences": self.homiletical_preferences,
            "outline_basket": self.outline_basket,
            "supporting_background": {
                "theology": self.theology,
                "history": self.history,
                "original_text_prose": self.original_text_prose,
                "sermon_movements": self.sermon_movements,
            },
            "model_supplement": self.rapid_evidence or {},
            "source_metadata": self.source_metadata,
        }
        return sections

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["context_mode"] = self.context_mode.value
        d["sources"] = [s.to_prompt_dict() for s in self.sources]
        return d


def _s(value: Any) -> str:
    return str(value or "").strip()


def _strip_raw_markdown(text: str) -> str:
    """Nyers markdown zaj eltávolítása háttéranyagból (promptba menő tisztítás)."""
    raw = _s(text)
    if not raw:
        return ""
    raw = re.sub(r"(?m)^#{1,6}\s*", "", raw)
    raw = re.sub(r"```+\w*\n?", "", raw)
    raw = re.sub(r"\*\*([^*]+)\*\*", r"\1", raw)
    raw = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", raw)
    raw = re.sub(r"(?m)^\s*[-*•]\s+", "• ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _truncate(text: str, n: int) -> str:
    raw = _s(text)
    if len(raw) <= n:
        return raw
    return raw[: n - 1].rstrip() + "…"


class LocalOriginalLanguageProvider:
    """Helyi TAGNT / TBESH alapú provider — nem talál ki adatot."""

    def load_for_passage(self, reference: str) -> list[dict[str, Any]]:
        ref = _s(reference)
        if not ref:
            return []
        items: list[dict[str, Any]] = []
        # NT — görög
        try:
            from bible_engine.greek_token_repository import load_greek_passage_tokens
            from bible_engine.greek_lexicon_repository import get_tbesg_lexicon_entry
            from bible_engine.lexicon_hu import (
                load_default_hungarian_lexicon,
                load_strong_aliases,
                resolve_hungarian_lexicon_entry,
            )
            from bible_engine.morphology_hu import (
                format_morphology_hu,
                parse_morphology_hu,
            )

            verses = load_greek_passage_tokens(ref)
            hu_entries = load_default_hungarian_lexicon() or {}
            aliases = load_strong_aliases()
            for verse in verses:
                tokens = []
                for tok in verse.tokens[:40]:
                    strong_id = getattr(tok, "strong_id", "") or ""
                    morph_code = getattr(tok, "morph_code", "") or ""
                    morph_resolved = ""
                    if morph_code:
                        try:
                            morph_resolved = format_morphology_hu(
                                parse_morphology_hu(morph_code)
                            )
                        except Exception:
                            morph_resolved = ""
                    lexical_gloss = ""
                    lexical_source = ""
                    if strong_id:
                        try:
                            resolution = resolve_hungarian_lexicon_entry(
                                hu_entries, strong_id, aliases
                            )
                            if resolution and resolution.entry:
                                lexical_gloss = resolution.entry.primary_gloss
                                lexical_source = resolution.entry.source
                        except Exception:
                            lexical_gloss = ""
                        if not lexical_gloss:
                            try:
                                entry = get_tbesg_lexicon_entry(strong_id)
                                if entry:
                                    lexical_gloss = entry.gloss or ""
                                    lexical_source = entry.source_name or "STEPBible TBESG"
                            except Exception:
                                pass
                    tokens.append(
                        {
                            "book": verse.book,
                            "chapter": verse.chapter,
                            "verse": verse.verse,
                            "form": getattr(tok, "greek_form", "") or "",
                            "lemma": getattr(tok, "lemma", "") or "",
                            "morph": morph_code,
                            "morph_resolved": morph_resolved,
                            "strong": strong_id,
                            "lexical_gloss": lexical_gloss,
                            "lexical_source": lexical_source,
                            "source_id": "TAGNT",
                            "data_version": ORIGINAL_LANGUAGE_DATA_VERSION,
                            "index": getattr(tok, "word_index", 0),
                        }
                    )
                if tokens:
                    items.append(
                        {
                            "language": "greek",
                            "verse": verse.verse,
                            "chapter": verse.chapter,
                            "book": verse.book,
                            "tokens": tokens,
                        }
                    )
        except Exception:
            pass
        if items:
            return items
        # OT — héber (TAHOT SQLite)
        try:
            from bible_engine.hebrew_books import parse_hebrew_reference
            from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository
            from bible_engine.hebrew_token_repository import (
                default_hebrew_token_repository,
            )

            book, chapter, verse_start, verse_end = parse_hebrew_reference(ref)
            repo = default_hebrew_token_repository()
            result = repo.passage(
                book, chapter, verse_start, verse_end
            )
            if result.status != "ok" or not result.tokens:
                return items
            lexicon_repo = HebrewHungarianLexiconRepository()
            by_verse: dict[int, list[dict[str, Any]]] = {}
            for tok in result.tokens:
                vno = int(getattr(tok, "verse", 0) or 0)
                strongs = getattr(tok, "strong_ids", ()) or ()
                strong = ""
                if isinstance(strongs, (list, tuple)) and strongs:
                    strong = str(strongs[0] or "")
                morph_code = getattr(tok, "morphology_code", "") or ""
                morph_resolved = ""
                if morph_code:
                    try:
                        decoded = repo.morphology(tok)
                        morph_resolved = " ".join(
                            str(x or "").strip()
                            for x in (
                                decoded.language,
                                decoded.part_of_speech,
                                decoded.verb_stem,
                                decoded.verb_conjugation,
                                decoded.person,
                                decoded.gender,
                                decoded.number,
                                decoded.state,
                                decoded.english_expansion,
                            )
                            if str(x or "").strip()
                        )
                    except Exception:
                        morph_resolved = ""
                lexical_gloss = getattr(tok, "english_gloss", "") or ""
                lexical_source = "TAHOT"
                if strong:
                    try:
                        resolution = lexicon_repo.lookup(strong)
                        if resolution.entry:
                            lexical_gloss = resolution.entry.base_meaning_hu
                            lexical_source = resolution.entry.source
                        elif resolution.tbesh_fallback and resolution.tbesh_fallback.entry:
                            lexical_gloss = resolution.tbesh_fallback.entry.gloss
                            lexical_source = resolution.source or "STEPBible TBESH"
                    except Exception:
                        pass
                entry = {
                    "book": book,
                    "chapter": chapter,
                    "verse": vno,
                    "form": getattr(tok, "surface", "") or "",
                    "lemma": getattr(tok, "lemma", "") or "",
                    "morph": morph_code,
                    "morph_resolved": morph_resolved,
                    "strong": strong,
                    "lexical_gloss": lexical_gloss,
                    "lexical_source": lexical_source,
                    "source_id": "TAHOT/TBESH",
                    "data_version": ORIGINAL_LANGUAGE_DATA_VERSION,
                    "index": getattr(tok, "word_index", 0),
                }
                by_verse.setdefault(vno, []).append(entry)
            for vno in sorted(by_verse):
                toks = by_verse[vno][:40]
                if not toks:
                    continue
                items.append(
                    {
                        "language": "hebrew",
                        "verse": vno,
                        "chapter": chapter,
                        "book": book,
                        "tokens": toks,
                    }
                )
        except Exception:
            pass
        return items


_DEFAULT_PROVIDER: OriginalLanguageProvider | None = None


def get_original_language_provider() -> OriginalLanguageProvider:
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        _DEFAULT_PROVIDER = LocalOriginalLanguageProvider()
    return _DEFAULT_PROVIDER


def set_original_language_provider(provider: OriginalLanguageProvider | None) -> None:
    """Teszt / bővítmény: provider csere."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider


def detect_context_mode(
    *,
    has_bible: bool,
    has_original: bool,
    has_exegesis: bool,
    has_homiletical: bool,
    has_user: bool,
    has_basket: bool,
    has_movements: bool,
) -> ContextMode:
    """BARE / PARTIAL / RICH — belső mód, nem UI kapcsoló."""
    if not has_bible:
        return ContextMode.BARE
    rich_signals = sum(
        [
            has_original,
            has_exegesis and (has_homiletical or has_user or has_movements),
            has_homiletical and has_user,
            has_basket and (has_exegesis or has_homiletical),
            has_movements and has_exegesis,
        ]
    )
    if rich_signals >= 2 or (
        has_exegesis and has_original and (has_homiletical or has_user)
    ):
        return ContextMode.RICH
    partial_signals = sum(
        [has_exegesis, has_homiletical, has_user, has_basket, has_original, has_movements]
    )
    if partial_signals >= 1:
        return ContextMode.PARTIAL
    return ContextMode.BARE


def _method_lens_from_path(path: Mapping[str, Any] | None) -> str:
    """Homiletikai lencse — nem kötelező sablon."""
    if not isinstance(path, dict):
        return ""
    path_type = _s(path.get("type") or path.get("path_type")).casefold()
    mapping = {
        "inductive": "Craddock-szerű induktív ritmus (lencse, nem sablon)",
        "narrative": "Lowry-szerű narratív feszültség (lencse, nem sablon)",
        "tension_to_gospel": "Lowry / evangéliumi fordulat (lencse)",
        "deductive": "Robinson / Chapell-szerű expozitív mozgás (lencse)",
        "moves": "Buttrick-szerű mozgások (lencse)",
        "movements": "Buttrick-szerű mozgások (lencse)",
    }
    for key, label in mapping.items():
        if key in path_type:
            return label
    if path_type:
        return f"Homiletikai út: {path_type} (lencse, nem kötelező sablon)"
    return ""


def build_outline_context(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
    legacy_bundle: Mapping[str, Any] | None = None,
    original_language_provider: OriginalLanguageProvider | None = None,
    include_original_language: bool = True,
) -> OutlineContext:
    """Session + műhelyanyag → típusozott OutlineContext."""
    from sermon_workshop_outline_ai import collect_available_sermon_material

    bundle = dict(
        legacy_bundle
        if isinstance(legacy_bundle, Mapping)
        else collect_available_sermon_material(
            session_state, sermon_workshop=sermon_workshop
        )
    )
    bundle.pop("sermon_outline", None)

    ref = _s(bundle.get("passage_reference"))
    bible = _strip_raw_markdown(_s(bundle.get("passage_text")))
    exegesis = _strip_raw_markdown(_truncate(_s(bundle.get("exegesis")), 2400))
    theology = _strip_raw_markdown(_truncate(_s(bundle.get("theology")), 1200))
    history = _strip_raw_markdown(_truncate(_s(bundle.get("history")), 800))
    original_prose = _strip_raw_markdown(
        _truncate(_s(bundle.get("original_text")), 1600)
    )
    exegetical_core_data: dict[str, Any] = {}
    try:
        from exegetical_core import get_cached_core

        cached_core = get_cached_core(session_state, reference=ref, bible_text=bible)
        if cached_core is not None:
            exegetical_core_data = cached_core.to_prompt_dict()
            exegesis = cached_core.to_prompt_summary()
            original_prose = ""
    except Exception:
        exegetical_core_data = {}

    sw = (
        dict(sermon_workshop)
        if isinstance(sermon_workshop, dict)
        else dict(session_state.get(SERMON_WORKSHOP_KEY) or {})
    )
    homiletical: dict[str, Any] = {}
    for key in (
        "human_condition",
        "listener_tension",
        "christ_centered_arc",
        "sermon_path",
        "closing",
    ):
        block = bundle.get(key)
        if isinstance(block, dict) and any(_s(v) for v in block.values()):
            homiletical[key] = block
    path = homiletical.get("sermon_path")
    lens = _method_lens_from_path(path if isinstance(path, dict) else None)
    if lens:
        homiletical["method_lens"] = lens

    basket = list(bundle.get("outline_basket") or [])
    notes = _s(bundle.get("outline_manual_notes"))
    user_focus = _s(bundle.get("user_focus"))
    decisions = [
        _s(x) for x in (bundle.get("approved_sermon_decisions") or []) if _s(x)
    ]
    insights = [_s(x) for x in (bundle.get("approved_insights") or []) if _s(x)]
    movements = [
        m for m in (bundle.get("sermon_movements") or []) if isinstance(m, dict)
    ]

    original_data: list[dict[str, Any]] = []
    if include_original_language and ref:
        provider = original_language_provider or get_original_language_provider()
        try:
            original_data = list(provider.load_for_passage(ref) or [])
        except Exception:
            original_data = []

    ctx = OutlineContext(
        passage_reference=ref,
        bible_text=bible,
        bible_translation=_s(bundle.get("bible_translation")) or "RÚF 2014",
        original_language_data=original_data,
        exegetical_material=exegesis,
        homiletical_preferences=homiletical,
        outline_basket=basket,
        user_notes=notes,
        occasion=_s(bundle.get("occasion")),
        user_focus=user_focus,
        theology=theology,
        history=history,
        original_text_prose=original_prose,
        exegetical_core=exegetical_core_data,
        approved_insights=insights,
        approved_sermon_decisions=decisions,
        sermon_main_idea=_s(bundle.get("sermon_main_idea")),
        text_main_idea=_s(bundle.get("text_main_idea")),
        sermon_movements=movements,
        rapid_evidence=(
            dict(bundle["rapid_evidence"])
            if isinstance(bundle.get("rapid_evidence"), dict)
            else None
        ),
        legacy_bundle=dict(bundle),
    )

    ctx.context_mode = detect_context_mode(
        has_bible=bool(bible),
        has_original=bool(original_data),
        has_exegesis=bool(exegesis),
        has_homiletical=ctx.has_homiletical(),
        has_user=ctx.has_user_decisions(),
        has_basket=bool(basket),
        has_movements=bool(movements),
    )

    sources = [
        SourceBlock(
            kind="passage_reference",
            priority=SourcePriority.BIBLE_TEXT,
            available=bool(ref),
            origin="session",
            payload=ref,
        ),
        SourceBlock(
            kind="bible_text",
            priority=SourcePriority.BIBLE_TEXT,
            available=bool(bible),
            origin="ruf_or_session",
            payload=_truncate(bible, 3200) if bible else None,
        ),
        SourceBlock(
            kind="original_language_data",
            priority=SourcePriority.ORIGINAL_LANGUAGE,
            available=bool(original_data),
            origin="local_tagnt_or_tbesh",
            payload=original_data[:8] if original_data else None,
            notes="Csak ellenőrizhető token/lemma/morfológia; kitalálás tilos.",
        ),
        SourceBlock(
            kind="user_notes",
            priority=SourcePriority.USER_DECISIONS,
            available=bool(notes or user_focus or decisions),
            origin="pastor",
            payload={
                "notes": notes,
                "focus": user_focus,
                "decisions": decisions,
                "main_idea": ctx.sermon_main_idea,
            },
        ),
        SourceBlock(
            kind="outline_basket",
            priority=SourcePriority.USER_DECISIONS,
            available=bool(basket),
            origin="user_selection",
            payload=basket[:12] if basket else None,
        ),
        SourceBlock(
            kind="exegetical_material",
            priority=SourcePriority.EXEGETICAL_BACKGROUND,
            available=bool(exegesis or exegetical_core_data),
            origin="exegetical_core" if exegetical_core_data else "workshop_or_tab",
            payload=_truncate(exegesis, 2000) if exegesis else None,
        ),
        SourceBlock(
            kind="homiletical_preferences",
            priority=SourcePriority.HOMILETICAL_METHOD,
            available=ctx.has_homiletical(),
            origin="sermon_workshop",
            payload=homiletical if homiletical else None,
            notes="Homiletikai lencsék, nem kötelező vázlatsablonok.",
        ),
        SourceBlock(
            kind="model_supplement",
            priority=SourcePriority.MODEL_SUPPLEMENT,
            available=bool(ctx.rapid_evidence),
            origin="rapid_evidence_or_prior_ai",
            payload=ctx.rapid_evidence,
            notes="Legalacsonyabb súly — ne másold mechanikusan.",
        ),
    ]
    ctx.sources = sources
    ctx.source_metadata = {
        "context_mode": ctx.context_mode.value,
        "available_kinds": [s.kind for s in sources if s.available],
        "original_language_token_verses": len(original_data),
        "has_raw_markdown_cleaned": True,
        "has_exegetical_core": bool(exegetical_core_data),
    }
    return ctx


def outline_context_to_legacy_bundle(ctx: OutlineContext) -> dict[str, Any]:
    """Visszafelé kompatibilis csomag a meglévő hash / seed / UI felé."""
    bundle = dict(ctx.legacy_bundle) if ctx.legacy_bundle else {}
    bundle["passage_reference"] = ctx.passage_reference
    bundle["passage_text"] = ctx.bible_text
    bundle["bible_translation"] = ctx.bible_translation
    if ctx.exegetical_material:
        bundle["exegesis"] = ctx.exegetical_material
    if ctx.theology:
        bundle["theology"] = ctx.theology
    if ctx.history:
        bundle["history"] = ctx.history
    if ctx.original_text_prose:
        bundle["original_text"] = ctx.original_text_prose
    if ctx.exegetical_core:
        bundle["exegetical_core"] = ctx.exegetical_core
    if ctx.outline_basket:
        bundle["outline_basket"] = ctx.outline_basket
    if ctx.homiletical_preferences:
        for k, v in ctx.homiletical_preferences.items():
            if k != "method_lens":
                bundle[k] = v
    if ctx.user_focus:
        bundle["user_focus"] = ctx.user_focus
    if ctx.user_notes:
        bundle["outline_manual_notes"] = ctx.user_notes
    if ctx.sermon_main_idea:
        bundle["sermon_main_idea"] = ctx.sermon_main_idea
    if ctx.text_main_idea:
        bundle["text_main_idea"] = ctx.text_main_idea
    if ctx.approved_insights:
        bundle["approved_insights"] = ctx.approved_insights
    if ctx.approved_sermon_decisions:
        bundle["approved_sermon_decisions"] = ctx.approved_sermon_decisions
    if ctx.sermon_movements:
        bundle["sermon_movements"] = ctx.sermon_movements
    if ctx.rapid_evidence:
        bundle["rapid_evidence"] = ctx.rapid_evidence
    if ctx.original_language_data:
        bundle["original_language_data"] = ctx.original_language_data
    bundle["context_mode"] = ctx.context_mode.value
    bundle["outline_context_sections"] = ctx.to_prompt_sections()
    keys = list(bundle.get("source_keys") or [])
    for k in (
        "passage_reference",
        "passage_text",
        "original_language_data",
        "exegetical_core",
        "exegesis",
        "context_mode",
    ):
        if bundle.get(k) not in (None, "", [], {}) and k not in keys:
            keys.append(k)
    bundle["source_keys"] = keys
    return bundle


__all__ = [
    "ContextMode",
    "LocalOriginalLanguageProvider",
    "OriginalLanguageProvider",
    "OutlineContext",
    "SourceBlock",
    "SourcePriority",
    "build_outline_context",
    "detect_context_mode",
    "get_original_language_provider",
    "outline_context_to_legacy_bundle",
    "set_original_language_provider",
]
