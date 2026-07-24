"""Igehely-keresés — AI szolgáltatás (alkalomi textusajánlás).

Önálló, Streamlit-független modul. A Gemini-hívást a hívó `generate_fn`-je
végzi. A modell csak referenciát és magyarázatot ad — bibliai idézetet nem.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from passage_search_config import (
    MAX_COMMON_IN_BATCH,
    OCCASION_OPTIONS,
    common_references_for,
)
from passage_search_history import reference_overlaps_any
from ruf_bible_service import parse_bible_reference
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _is_api_error_text

TAB_LABEL = "Igehely keresése"
DEFAULT_TEMPERATURE = 0.25
REQUIRED_COUNT = 5
# A modell 5-öt kérünk; history/alias szűrés után 4 is használható siker.
MIN_ACCEPTABLE_COUNT = 4

_LOG = logging.getLogger("textus.passage_search")

GenerateFn = Callable[..., str]

_HISTORY_EXCLUDE_INSTRUCTION = (
    "Az alábbi igeszakaszokat vagy azokkal érdemben átfedő perikópákat "
    "ne ajánld, mert a felhasználó mentett projektjeiben már szerepeltek. "
    "A tematikusan hasonló, de más bibliai szakaszok ajánlhatók."
)

PASSAGE_SEARCH_SYSTEM = """\
Tapasztalt református lelkipásztor, biblikus teológus és homiletikai tanácsadó vagy.

Feladatod egy istentiszteleti vagy lelkipásztori alkalomhoz öt, valóban prédikálható bibliai igeszakasz ajánlása. Nem prédikációt és nem teljes exegézist készítesz, hanem felelős textusválasztásban segítesz.

A javaslatokat az alábbi sorrendben értékeld:

1. textuális és teológiai alkalmasság;
2. az alkalom és a megadott pásztori helyzet iránti érzékenység;
3. önálló, koherens prédikációs egység;
4. homiletikai termékenység;
5. változatosság és frissesség.

A kevésbé ismert textus nem önmagában érték. Ne ajánlj erőltetett vagy nehezen alkalmazható szakaszt csak azért, hogy eredetinek tűnj. Ugyanakkor ne töltsd meg a listát kizárólag a leggyakrabban használt alkalmi igékkel.

Az öt javaslat között:

- legfeljebb egy közismert, klasszikus alkalmi textus szerepelhet;
- legalább három kevésbé elcsépelt, de jól prédikálható szakasz legyen;
- lehetőség szerint legyen ószövetségi és újszövetségi szakasz is;
- lehetőség szerint több bibliai műfaj jelenjen meg;
- ne ajánlj öt, lényegében azonos témájú szakaszt.

Elsősorban összefüggő perikópákat ajánlj, ne kiragadott mottóverseket. Egyetlen verset csak akkor javasolj, ha a közvetlen kontextussal együtt is felelősen használható.

A felhasználó leírását pásztori tájékozódási pontként kezeld, ne diagnózisként. Ne egészítsd ki ismeretlen életrajzi vagy lelki adatokkal.

Virrasztó esetén:

- rövid, intim családi vagy gyülekezeti búcsúalkalmat (virrasztót) szolgáló textusokat ajánlj, nem teljes temetési prédikációt;
- ne kisebbítsd a gyászt; a hangnem legyen személyesebb és csendesebb, mint temetésnél;
- vigasztalás, Isten közelsége, feltámadási reménység és — ha a helyzet engedi — hálaadás az elhunyt életéért jelenjen meg;
- ha a kontextus kort, hirtelen halált, hosszú betegséget vagy hasonló körülményt említ, különösen érzékenyen reagálj;
- ne csak a legelcsépeltebb gyásztextusokra szorítkozz; Temetéssel közös textusok előfordulhatnak, de a tonus legyen intim és pásztori;
- minden javaslatnál adj rövid indoklást és lehetséges áhítat-/homiletikai irányt.

Temetés esetén:

- ne állítsd automatikusan, hogy az elhunyt üdvözült;
- ne magyarázd meg könnyelműen a halál okát vagy Isten szándékát;
- ne kisebbítsd a gyászt;
- a gyászoló közösséget szólítsd meg;
- a vigasztalást Isten ígéretére, Krisztus feltámadására, az irgalomra és a reménységre alapozd;
- fiatal vagy hirtelen halál esetén különösen kerüld a közhelyes magyarázatokat.

Esketés esetén:

- ne idealizáld a házasságot;
- jelenjen meg a szövetség, hűség, kegyelem, kölcsönös szolgálat és közös növekedés;
- ne korlátozódj automatikusan az 1Korinthus 13-ra.

Keresztelés esetén:

- vedd figyelembe a szövetség, ígéret, kegyelem, gyülekezeti felelősség és tanítványság összefüggéseit;
- kerüld a keresztség mágikus vagy automatikus értelmezését.

Bűnbánati alkalom esetén:

- az ítélet mellett jelenjen meg a kegyelem és a helyreállítás lehetősége;
- ne építs szégyenre vagy lelki nyomásgyakorlásra;
- tartsd együtt a törvényt és az evangéliumot.

Vasárnapi istentisztelet esetén:

- törekedj Isten teljes tanácsának változatos megszólaltatására;
- ne csak tematikus mottóverseket ajánlj;
- részesítsd előnyben a világos belső mozgással rendelkező perikópákat.

Minden javaslatnál adj:

- pontos referenciát;
- rövid címet;
- rövid indoklást;
- egyetlen homiletikai irányt.

Ne idézd emlékezetből a bibliai szöveget. Ne találj ki verset, könyvet, fejezetet vagy történeti adatot.

Válaszod KIZÁRÓLAG érvényes JSON legyen — semmi más szöveg, markdown vagy magyarázat.
"""

_USER_TEMPLATE = """\
Alkalom: {occasion}
Pásztori helyzet / rövid leírás: {context}
Kizárandó referenciák (ne ismételd őket, még közeli változatban sem): {exclude_list}
KIZÁRT TEXTUSOK: {history_block}
Gyakori / elcsépelt textusok ehhez az alkalomhoz (legfeljebb EGY jelenhet meg a listában, ha valóban a legjobb): {common_list}

Adj pontosan 5 javaslatot. Ne idézz bibliai szöveget.

JSON séma:
{{
  "occasion": "{occasion}",
  "context_summary": "rövid összefoglaló",
  "suggestions": [
    {{
      "reference": "könyv fejezet,vers–vers",
      "title": "3–7 szavas cím",
      "reason": "1–2 mondat, miért illik",
      "homiletical_direction": "egy mondatos homiletikai irány",
      "familiarity": "common" | "less_common"
    }}
  ]
}}
"""

_REPAIR_HINT = (
    "Az előző válaszod nem felelt meg a követelményeknek "
    "(5 érvényes, különböző, normalizálható bibliai referencia; "
    "legfeljebb egy common/elcsépelt). "
    "Add vissza UGYANAZT a feladatot KIZÁRÓLAG érvényes JSON-ként, "
    "javított referenciákkal. Ne idézz bibliai szöveget."
)

_FILL_HINT = (
    "Az alábbi elfogadott javaslatokat tartsd meg, és egészítsd ki a listát "
    "pontosan 5 érvényes, különböző referenciára. "
    "Csak a hiányzó helyeket töltsd fel új szakaszokkal. "
    "Ne ismételd az elfogadottakat, a kizárandókat, és a KIZÁRT TEXTUSOKAT "
    "(átfedő perikópákat sem). Ne idézz bibliai szöveget."
)

_USER_API_FAIL = (
    "Most nem sikerült igehelyeket keresni. A megadott adatok megmaradtak, próbáld újra."
)


def _s(value: Any) -> str:
    return str(value or "").strip()


def _sanitize_log_fragment(text: str, *, max_len: int = 180) -> str:
    """API-kulcs / hosszú szabad szöveg nélkül logolható töredék."""
    raw = _s(text)
    if not raw:
        return ""
    # Ne vigyünk session/kulcs-szerű tokeneket a logba.
    cleaned = re.sub(
        r"(?i)(api[_-]?key|bearer|AIza)[^\s,;]{0,80}",
        "[redacted]",
        raw,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def _log_stage(
    stage: str,
    *,
    exc: BaseException | None = None,
    mode: str = "",
    suggestion_count: int | None = None,
    warning_count: int | None = None,
    detail: str = "",
) -> None:
    """Szerveroldali diagnosztika — stage + kivétel típus, PII nélkül."""
    parts = [f"stage={stage}"]
    if mode:
        parts.append(f"mode={mode}")
    if suggestion_count is not None:
        parts.append(f"suggestions={suggestion_count}")
    if warning_count is not None:
        parts.append(f"warnings={warning_count}")
    if exc is not None:
        parts.append(f"exc_type={type(exc).__name__}")
        parts.append(f"exc={_sanitize_log_fragment(str(exc))}")
    if detail:
        parts.append(f"detail={_sanitize_log_fragment(detail)}")
    _LOG.warning("passage_search %s", " ".join(parts))


def normalize_passage_reference(reference: str) -> str:
    """Kanonikus igehely-referencia; ValueError érvénytelen esetén."""
    return parse_bible_reference(reference).normalized_reference


def references_equivalent(a: str, b: str) -> bool:
    aa, bb = _s(a), _s(b)
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    try:
        return normalize_passage_reference(aa) == normalize_passage_reference(bb)
    except ValueError:
        return aa.casefold() == bb.casefold()


@dataclass
class PassageSuggestion:
    reference: str = ""
    title: str = ""
    reason: str = ""
    homiletical_direction: str = ""
    familiarity: str = "less_common"  # common | less_common

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PassageSearchResult:
    occasion: str = ""
    context_summary: str = ""
    suggestions: list[PassageSuggestion] = field(default_factory=list)
    excluded_references: list[str] = field(default_factory=list)
    generated_at: str = ""
    ok: bool = True
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)
    raw_response: str = ""
    mode: str = "ai"

    def to_dict(self) -> dict[str, Any]:
        return {
            "occasion": self.occasion,
            "context_summary": self.context_summary,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "excluded_references": list(self.excluded_references),
            "generated_at": self.generated_at,
            "ok": self.ok,
            "error_message": self.error_message,
            "warnings": list(self.warnings),
            "mode": self.mode,
        }


def empty_passage_search_state() -> dict[str, Any]:
    return {
        "occasion": OCCASION_OPTIONS[0],
        "context": "",
        "suggestions": [],
        "excluded_references": [],
        "generated_at": "",
        "last_error": "",
        "status": "idle",  # idle | ready | error | running
    }


def normalize_passage_search_state(raw: Any) -> dict[str, Any]:
    base = empty_passage_search_state()
    if not isinstance(raw, dict):
        return base
    occasion = _s(raw.get("occasion")) or base["occasion"]
    if occasion not in OCCASION_OPTIONS:
        occasion = base["occasion"]
    suggestions: list[dict[str, Any]] = []
    for item in raw.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        ref = _s(item.get("reference"))
        if not ref:
            continue
        fam = _s(item.get("familiarity")) or "less_common"
        if fam not in ("common", "less_common"):
            fam = "less_common"
        suggestions.append(
            {
                "reference": ref,
                "title": _s(item.get("title")),
                "reason": _s(item.get("reason")),
                "homiletical_direction": _s(
                    item.get("homiletical_direction") or item.get("direction")
                ),
                "familiarity": fam,
            }
        )
    excluded = [
        _s(x) for x in (raw.get("excluded_references") or []) if _s(x)
    ][:40]
    status = _s(raw.get("status")) or ("ready" if suggestions else "idle")
    if status not in ("idle", "ready", "error", "running"):
        status = "idle"
    return {
        "occasion": occasion,
        "context": _s(raw.get("context") or raw.get("context_summary")),
        "suggestions": suggestions[:REQUIRED_COUNT],
        "excluded_references": excluded,
        "generated_at": _s(raw.get("generated_at")),
        "last_error": _s(raw.get("last_error") or raw.get("error_message")),
        "status": status,
    }


def _fold_ref_key(reference: str) -> str:
    try:
        return normalize_passage_reference(reference).casefold()
    except ValueError:
        return re.sub(r"\s+", "", _s(reference).casefold())


def _is_common_for_occasion(reference: str, occasion: str) -> bool:
    commons = common_references_for(occasion)
    if not commons:
        return False
    try:
        norm = normalize_passage_reference(reference)
    except ValueError:
        return False
    for c in commons:
        if references_equivalent(norm, c):
            return True
        try:
            pc = parse_bible_reference(c)
            pn = parse_bible_reference(norm)
            if pc.book.code == pn.book.code and pc.chapter == pn.chapter:
                if pc.book.single_chapter or (
                    pc.verse_start is None and pc.verse_end is None
                ):
                    return True
                if (
                    pn.verse_start == pc.verse_start
                    and pn.verse_end == pc.verse_end
                ):
                    return True
        except (ValueError, AttributeError):
            continue
    return False


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", _s(text)) if w])


def validate_and_normalize_suggestions(
    raw_suggestions: Sequence[Any],
    *,
    occasion: str,
    exclude: Sequence[str] | None = None,
    history_exclude: Sequence[str] | None = None,
) -> tuple[list[PassageSuggestion], list[str]]:
    """Validál + normalizál. Vissza: (elfogadott lista, figyelmeztetések)."""
    warnings: list[str] = []
    exclude_keys = {_fold_ref_key(x) for x in (exclude or []) if _s(x)}
    history_refs = [_s(x) for x in (history_exclude or []) if _s(x)]
    seen: set[str] = set()
    out: list[PassageSuggestion] = []
    common_count = 0

    for item in raw_suggestions or []:
        if len(out) >= REQUIRED_COUNT:
            break
        if not isinstance(item, dict):
            continue
        raw_ref = _s(item.get("reference"))
        if not raw_ref:
            continue
        try:
            norm = normalize_passage_reference(raw_ref)
        except ValueError:
            warnings.append(f"Érvénytelen referencia elvetve: {raw_ref}")
            continue
        key = _fold_ref_key(norm)
        if key in seen:
            warnings.append(f"Duplikátum elvetve: {norm}")
            continue
        if key in exclude_keys:
            warnings.append(f"Kizárt (előző kör) elvetve: {norm}")
            continue
        if history_refs and reference_overlaps_any(norm, history_refs):
            warnings.append(f"Korábban használt / átfedő textus elvetve: {norm}")
            continue
        is_common = _is_common_for_occasion(norm, occasion) or (
            _s(item.get("familiarity")) == "common"
        )
        if is_common and common_count >= MAX_COMMON_IN_BATCH:
            warnings.append(f"Többlet klasszikus textus elvetve: {norm}")
            continue
        title = _s(item.get("title"))
        if title and _word_count(title) > 12:
            title = " ".join(title.split()[:7])
        fam = "common" if is_common else "less_common"
        out.append(
            PassageSuggestion(
                reference=norm,
                title=title,
                reason=_s(item.get("reason")),
                homiletical_direction=_s(
                    item.get("homiletical_direction") or item.get("direction")
                ),
                familiarity=fam,
            )
        )
        seen.add(key)
        if is_common:
            common_count += 1

    return out, warnings


def parse_passage_search_response(
    raw: str,
    *,
    occasion: str,
    exclude: Sequence[str] | None = None,
    history_exclude: Sequence[str] | None = None,
    require_full_count: bool = True,
) -> PassageSearchResult:
    if not _s(raw) or _is_api_error_text(raw):
        return PassageSearchResult(
            ok=False,
            mode="api_error",
            error_message=_USER_API_FAIL,
            occasion=occasion,
            raw_response=raw or "",
        )
    obj = extract_json_object(raw)
    if not isinstance(obj, dict):
        return PassageSearchResult(
            ok=False,
            mode="parse_error",
            error_message=_USER_API_FAIL,
            occasion=occasion,
            raw_response=raw,
        )
    suggestions, warnings = validate_and_normalize_suggestions(
        obj.get("suggestions") or [],
        occasion=occasion,
        exclude=exclude,
        history_exclude=history_exclude,
    )
    if require_full_count and len(suggestions) < REQUIRED_COUNT:
        return PassageSearchResult(
            ok=False,
            mode="parse_error",
            error_message=_USER_API_FAIL,
            occasion=_s(obj.get("occasion")) or occasion,
            context_summary=_s(obj.get("context_summary")),
            suggestions=suggestions,
            warnings=warnings
            + [f"Csak {len(suggestions)}/{REQUIRED_COUNT} érvényes javaslat."],
            raw_response=raw,
        )
    return PassageSearchResult(
        ok=len(suggestions) >= REQUIRED_COUNT,
        mode="ai",
        occasion=_s(obj.get("occasion")) or occasion,
        context_summary=_s(obj.get("context_summary")),
        suggestions=suggestions[:REQUIRED_COUNT],
        warnings=warnings,
        raw_response=raw,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
) -> str:
    prev_temp = None
    touched_temp = False
    try:
        import streamlit as st

        prev_temp = st.session_state.get("temperature")
        st.session_state["temperature"] = float(DEFAULT_TEMPERATURE)
        touched_temp = True
    except Exception:
        touched_temp = False
    # Egy gombnyomás alatt fill/repair több HTTP-t indíthat; a globális
    # cooldown ne blokkolja az ugyanazon ajánláson belüli pótló hívást.
    kwargs: dict[str, Any] = {
        "enable_google_search": False,
        "tab_label": TAB_LABEL,
        "use_cache": False,
        "system_bundle": PASSAGE_SEARCH_SYSTEM,
        "include_brevity_directive": False,
        "bypass_cooldown": True,
    }
    try:
        return generate_fn(prompt, **kwargs)
    except TypeError:
        kwargs.pop("include_brevity_directive", None)
        try:
            return generate_fn(prompt, **kwargs)
        except TypeError:
            kwargs.pop("bypass_cooldown", None)
            return generate_fn(prompt, **kwargs)
    finally:
        if touched_temp:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:
                pass


def _history_block(history_exclude: Sequence[str]) -> str:
    refs = [_s(x) for x in history_exclude if _s(x)]
    if not refs:
        return "(nincs)"
    listed = ", ".join(refs)
    return f"{_HISTORY_EXCLUDE_INSTRUCTION}\n{listed}"


def _build_user_prompt(
    *,
    occasion: str,
    context: str,
    exclude: Sequence[str],
    history_exclude: Sequence[str],
    commons: Sequence[str],
) -> str:
    return _USER_TEMPLATE.format(
        occasion=occasion,
        context=context or "(nincs megadva — csak az alkalom típusa alapján)",
        exclude_list=", ".join(exclude) if exclude else "(nincs)",
        history_block=_history_block(history_exclude),
        common_list=", ".join(commons) if commons else "(nincs megadva)",
    )


def _merge_suggestion_batches(
    accepted: Sequence[PassageSuggestion],
    extras: Sequence[PassageSuggestion],
    *,
    exclude: Sequence[str],
    history_exclude: Sequence[str],
    occasion: str,
) -> list[PassageSuggestion]:
    """Elfogadott + pótlás; session/history kizárás és common-cap érvényes."""
    combined = [s.to_dict() for s in accepted] + [s.to_dict() for s in extras]
    # Ideiglenesen magasabb common-cap a merge során: a validate újra számol.
    # A meglévő accepted common-okat megtartjuk; extras-nál a cap érvényes.
    out, _warnings = validate_and_normalize_suggestions(
        combined,
        occasion=occasion,
        exclude=exclude,
        history_exclude=history_exclude,
    )
    return out[:REQUIRED_COUNT]


def suggest_passages_for_occasion(
    *,
    occasion: str,
    context: str = "",
    exclude_references: Sequence[str] | None = None,
    history_exclude_references: Sequence[str] | None = None,
    generate_fn: GenerateFn | None = None,
) -> PassageSearchResult:
    """Öt prédikálható igeszakasz ajánlása. generate_fn nélkül → hiba."""
    occ = _s(occasion) or OCCASION_OPTIONS[0]
    if occ not in OCCASION_OPTIONS:
        occ = OCCASION_OPTIONS[0]
    ctx = _s(context)
    exclude = [_s(x) for x in (exclude_references or []) if _s(x)]
    history_exclude = [
        _s(x) for x in (history_exclude_references or []) if _s(x)
    ]
    # AI prompt: csak normalizált ref stringek (PII / projektcím nélkül)
    history_for_prompt: list[str] = []
    for ref in history_exclude:
        try:
            history_for_prompt.append(normalize_passage_reference(ref))
        except ValueError:
            continue
    commons = list(common_references_for(occ))

    if generate_fn is None:
        _log_stage("missing_generate_fn", mode="api_error", suggestion_count=0)
        return PassageSearchResult(
            ok=False,
            mode="api_error",
            error_message=_USER_API_FAIL,
            occasion=occ,
            context_summary=ctx,
            excluded_references=exclude,
        )

    prompt = _build_user_prompt(
        occasion=occ,
        context=ctx,
        exclude=exclude,
        history_exclude=history_for_prompt,
        commons=commons,
    )

    try:
        raw = _call_generate(generate_fn, prompt)
    except Exception as exc:  # noqa: BLE001
        _log_stage("generate_primary", exc=exc, mode="api_error")
        return PassageSearchResult(
            ok=False,
            mode="api_error",
            error_message=_USER_API_FAIL,
            occasion=occ,
            context_summary=ctx,
            excluded_references=exclude,
            warnings=[f"Generálási hiba: {exc}"],
        )

    if _is_api_error_text(raw or ""):
        _log_stage(
            "generate_primary_api_error",
            mode="api_error",
            detail=_s(raw)[:120],
        )
        return PassageSearchResult(
            ok=False,
            mode="api_error",
            error_message=_USER_API_FAIL,
            occasion=occ,
            context_summary=ctx,
            excluded_references=exclude,
            raw_response=raw or "",
            warnings=[f"Generálási hiba: {_s(raw)[:400]}"],
        )

    parsed = parse_passage_search_response(
        raw or "",
        occasion=occ,
        exclude=exclude,
        history_exclude=history_for_prompt,
        require_full_count=False,
    )
    if ctx and not parsed.context_summary:
        parsed.context_summary = ctx
    parsed.excluded_references = exclude

    def _finalize(result: PassageSearchResult, *, stage: str) -> PassageSearchResult:
        result.excluded_references = exclude
        if ctx and not result.context_summary:
            result.context_summary = ctx
        n = len(result.suggestions)
        if n >= MIN_ACCEPTABLE_COUNT:
            result.ok = True
            result.error_message = ""
            result.suggestions = result.suggestions[:REQUIRED_COUNT]
            if n < REQUIRED_COUNT:
                result.warnings = list(result.warnings) + [
                    f"Csak {n}/{REQUIRED_COUNT} érvényes javaslat — elfogadva."
                ]
        else:
            result.ok = False
            if not result.error_message:
                result.error_message = _USER_API_FAIL
            _log_stage(
                stage,
                mode=result.mode or "incomplete",
                suggestion_count=n,
                warning_count=len(result.warnings or []),
                detail="; ".join(result.warnings[:3]) if result.warnings else "",
            )
        return result

    # Teljes parse-hiba (0 érvényes) → egyszeri általános javítás
    if not parsed.suggestions and not parsed.ok:
        _log_stage(
            "primary_empty_repair",
            mode=parsed.mode,
            suggestion_count=0,
            warning_count=len(parsed.warnings or []),
        )
        repair_prompt = (
            f"{prompt}\n\n{_REPAIR_HINT}\n\nElőző válasz:\n{_s(raw)[:2500]}"
        )
        try:
            raw2 = _call_generate(generate_fn, repair_prompt)
        except Exception as exc:  # noqa: BLE001
            _log_stage("generate_repair", exc=exc, mode="api_error")
            parsed.warnings = list(parsed.warnings) + [f"Generálási hiba: {exc}"]
            return _finalize(parsed, stage="finalize_after_repair_exc")

        if _is_api_error_text(raw2 or ""):
            _log_stage(
                "generate_repair_api_error",
                mode="api_error",
                detail=_s(raw2)[:120],
            )
            parsed.warnings = list(parsed.warnings) + [
                f"Generálási hiba: {_s(raw2)[:400]}"
            ]
            return _finalize(parsed, stage="finalize_after_repair_api_error")

        repaired = parse_passage_search_response(
            raw2 or "",
            occasion=occ,
            exclude=exclude,
            history_exclude=history_for_prompt,
            require_full_count=False,
        )
        return _finalize(repaired, stage="finalize_after_repair")

    if len(parsed.suggestions) >= REQUIRED_COUNT:
        return _finalize(parsed, stage="finalize_primary_full")

    # History / exclude / alias-szűrés miatt hiányzik → egyetlen pótló hívás
    accepted = list(parsed.suggestions)
    _log_stage(
        "primary_partial_fill",
        mode=parsed.mode,
        suggestion_count=len(accepted),
        warning_count=len(parsed.warnings or []),
    )
    accepted_blob = "\n".join(
        f"- {s.reference}: {s.title}" for s in accepted
    ) or "(nincs)"
    fill_prompt = (
        f"{prompt}\n\n{_FILL_HINT}\n\n"
        f"Elfogadott javaslatok ({len(accepted)}/{REQUIRED_COUNT}):\n"
        f"{accepted_blob}\n\n"
        f"Előző válasz:\n{_s(raw)[:2000]}"
    )
    try:
        raw_fill = _call_generate(generate_fn, fill_prompt)
    except Exception as exc:  # noqa: BLE001
        _log_stage("generate_fill", exc=exc, mode="api_error")
        parsed.warnings = list(parsed.warnings) + [f"Generálási hiba: {exc}"]
        return _finalize(parsed, stage="finalize_after_fill_exc")

    if _is_api_error_text(raw_fill or ""):
        _log_stage(
            "generate_fill_api_error",
            mode="api_error",
            detail=_s(raw_fill)[:120],
        )
        parsed.warnings = list(parsed.warnings) + [
            f"Generálási hiba: {_s(raw_fill)[:400]}"
        ]
        return _finalize(parsed, stage="finalize_after_fill_api_error")

    filled = parse_passage_search_response(
        raw_fill or "",
        occasion=occ,
        exclude=exclude + [s.reference for s in accepted],
        history_exclude=history_for_prompt,
        require_full_count=False,
    )
    merged = _merge_suggestion_batches(
        accepted,
        filled.suggestions,
        exclude=exclude,
        history_exclude=history_for_prompt,
        occasion=occ,
    )
    parsed.suggestions = merged
    parsed.warnings = list(parsed.warnings) + list(filled.warnings)
    parsed.raw_response = filled.raw_response or parsed.raw_response
    if filled.generated_at:
        parsed.generated_at = filled.generated_at
    return _finalize(parsed, stage="finalize_after_fill")


def merge_exclude_list(
    previous_suggestions: Sequence[Mapping[str, Any] | PassageSuggestion],
    existing_exclude: Sequence[str] | None = None,
) -> list[str]:
    """Előző kör referenciái + meglévő kizárások (max 40)."""
    out: list[str] = []
    seen: set[str] = set()
    for src in (existing_exclude or [], previous_suggestions):
        for item in src:
            if isinstance(item, PassageSuggestion):
                ref = item.reference
            elif isinstance(item, Mapping):
                ref = _s(item.get("reference"))
            else:
                ref = _s(item)
            if not ref:
                continue
            key = _fold_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            try:
                out.append(normalize_passage_reference(ref))
            except ValueError:
                out.append(ref)
            if len(out) >= 40:
                return out
    return out


__all__ = [
    "TAB_LABEL",
    "REQUIRED_COUNT",
    "MIN_ACCEPTABLE_COUNT",
    "OCCASION_OPTIONS",
    "PASSAGE_SEARCH_SYSTEM",
    "PassageSuggestion",
    "PassageSearchResult",
    "empty_passage_search_state",
    "normalize_passage_search_state",
    "normalize_passage_reference",
    "references_equivalent",
    "validate_and_normalize_suggestions",
    "parse_passage_search_response",
    "suggest_passages_for_occasion",
    "merge_exclude_list",
]
