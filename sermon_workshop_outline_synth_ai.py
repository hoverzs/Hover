"""Igehirdetési vázlat — szintézis / lektor (delegál a közös motorra).

A kanonikus generálás: `sermon_outline_engine.generate_sermon_outline`.
Ez a modul megtartja a részleges újragenerálást és a legacy quality API-t,
de a hossz-/sémaellenőrzés a közös hard limiteken alapul.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from sermon_outline_engine import (
    COMPRESS_INSTRUCTION,
    FORBIDDEN_HEADINGS,
    LIMITS,
    OUTLINE_SYSTEM_PROMPT,
    normalize_structured_outline,
    render_structured_outline,
    structured_to_sermon_outline,
    validate_structured_outline,
    word_count,
)
from sermon_workshop_data import normalize_sermon_outline
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _is_api_error_text
from sermon_workshop_outline_ai import (
    DEFAULT_TEMPERATURE,
    OUTLINE_PLACEHOLDER_BANLIST,
    TAB_OUTLINE,
    _normalize_cmp,
    _s,
    _usable_text,
    outline_to_readable_content,
)

GenerateFn = Callable[..., str]

# Soft = tip only after compress. Length / structure stay HARD in engine.
SOFT_QUALITY_ISSUES = frozenset(
    {
        "stock_phrases",
        "transition_fillers",
        "word_count_out_of_range",  # soft only below absolute max
    }
)

HOMILETIC_SYSTEM_PROMPT = OUTLINE_SYSTEM_PROMPT

_STOCK_PHRASE_MARKERS = (
    "a kegyelem abban van",
    "nem a mi erőnkből",
    "isten tervének része",
    "isten tervének része volt",
)

_TRANSITION_FILLER_MARKERS = (
    "de vajon mi következik",
    "ez azonban",
    "nem marad titokban",
)

_SYNTH_JSON_SHAPE = """\
{
  "title": "Rövid cím",
  "text_reference": "Igehely",
  "scope_note": "",
  "focus_sentence": "Egy teljes fókuszmondat (20–40 szó).",
  "introduction_direction": "Bevezetési irány (45–80 szó).",
  "points": [
    {
      "title": "Pontcím",
      "verses": "v. x–y",
      "textual_insight": "Egy teljes mondat: mit állít / milyen mozgást végez a textus.",
      "theological_emphasis": "Egy teljes mondat: textusból levezethető teológiai jelentés.",
      "listener_movement": "Egy teljes mondat: felismerés / kérdés / válasz a hallgató felé."
    }
  ],
  "conclusion_direction": "Megérkezés irány (45–80 szó).",
  "refinement_suggestions": []
}
"""


def resolve_outline_occasion(
    bundle: Mapping[str, Any] | None = None,
    *,
    occasion: Any = "",
    extra_text: Any = "",
) -> str:
    raw = _s(occasion)
    if not raw and isinstance(bundle, Mapping):
        raw = _s(bundle.get("passage_search_occasion")) or _s(bundle.get("occasion"))
        if not raw:
            occ_ctx = bundle.get("occasion_context")
            if isinstance(occ_ctx, Mapping):
                raw = _s(occ_ctx.get("occasion_type"))
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
    if "keresztel" in blob:
        return "Keresztelés"
    if "esket" in blob or "esküvő" in blob or "eskuvo" in blob:
        return "Esketés"
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
    return 0 < len(keys) < 5


def outline_length_profile(
    occasion: Any = "",
    *,
    partial: bool = False,
) -> dict[str, Any]:
    """Alkalomfüggő útmutató — hard abszolút max a közös LIMITS-ből."""
    from sermon_outline_engine import SCHEMA_VERSION

    occ = resolve_outline_occasion(occasion=occasion)
    occ_cf = occ.casefold()
    target = f"{LIMITS['target_min_3_4']}–{LIMITS['target_max_3_4']}"
    if "virraszt" in occ_cf:
        min_movements = 2
        max_movements = 3
    elif "temet" in occ_cf:
        min_movements = 2
        max_movements = 3
    else:
        min_movements = 2
        max_movements = 5
    soft_min = LIMITS["soft_floor_words"] - (20 if partial else 0)
    soft_max = LIMITS["absolute_max_words"]
    guidance = (
        f"KANONIKUS MOVEMENTS VÁZLAT (~{target} szó irányadó 3–4 mozgásnál; "
        f"abszolút max 850; séma {SCHEMA_VERSION}). "
        f"Mozgások: {min_movements}–{max_movements}; minden mozgásban "
        "textual_insight + theological_emphasis + listener_movement. "
        "Ne írj prédikációt; a kanonikus tömb neve `movements` (ne `points`)."
    )
    if partial:
        guidance += " Részleges anyag: teljes szerkezet, kissé rövidebb OK."
    return {
        "occasion": occ or "Vasárnapi istentisztelet",
        "soft_min": max(300, soft_min),
        "soft_max": soft_max,
        "target_range": target,
        "min_movements": min_movements,
        "max_movements": max_movements,
        "guidance": guidance,
        "intro_hint": f"{LIMITS['intro_min_words']}–{LIMITS['intro_words']} szó",
        "movement_hint": (
            f"{min_movements}–{max_movements} pont, három réteg "
            f"({LIMITS['point_layers_min_words']}–{LIMITS['point_layers_max_words']} szó)"
        ),
        "conclusion_hint": (
            f"{LIMITS['conclusion_min_words']}–{LIMITS['conclusion_words']} szó"
        ),
        "partial": partial,
        "schema_version": SCHEMA_VERSION,
    }


def _hard_quality_issues(issues: list[str] | tuple[str, ...] | None) -> list[str]:
    return [i for i in (issues or []) if i not in SOFT_QUALITY_ISSUES]


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


def suggest_text_boundary_hint(
    passage_reference: Any,
    passage_text: Any = "",
) -> dict[str, str]:
    import re

    ref = _normalize_cmp(passage_reference)
    text = _s(passage_text)
    note = ""
    suggested = ""
    if re.search(r"j[uú]d(?:[aá]s)?\s*17\s*[–\-—]\s*20\b", ref) or re.search(
        r"\bjud(?:e)?\s*17\s*[–\-—]\s*20\b", ref
    ):
        suggested = "Júd 17–21"
        note = (
            "A gondolati ív a következő versben zárul le. "
            f"Javasolt textushatár: {suggested}"
        )
        return {"text_boundary_note": note, "suggested_text_boundary": suggested}
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


def apply_synth_payload_to_outline(
    seed: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any],
    replace_movements: bool = True,
) -> dict[str, Any]:
    """JSON payload → normalizált vázlat a közös struktúrán keresztül."""
    structured = normalize_structured_outline(payload)
    if not replace_movements and seed.get("movements"):
        if not structured.get("points"):
            structured = normalize_structured_outline(seed)
    locked = _locked_main_idea(bundle, seed)
    if locked:
        structured["focus_sentence"] = locked
    if not structured.get("text_reference"):
        structured["text_reference"] = _s(
            seed.get("passage_reference") or bundle.get("passage_reference")
        )
    if not structured.get("scope_note"):
        hint = suggest_text_boundary_hint(
            structured.get("text_reference") or bundle.get("passage_reference"),
            bundle.get("passage_text") or "",
        )
        structured["scope_note"] = hint.get("text_boundary_note") or ""
    merged = structured_to_sermon_outline(
        structured,
        seed=seed,
        source=_s(seed.get("source")) or "workshop",
        context_hash=_s(seed.get("context_hash")),
    )
    if _usable_text(seed.get("manual_notes")):
        merged["manual_notes"] = _usable_text(seed.get("manual_notes"))
    for meta in (
        "bible_translation",
        "lection_reference",
        "lection",
        "prayer_before",
        "prayer_after",
        "source_sections",
        "project_title",
    ):
        if seed.get(meta) not in (None, "", [], {}):
            merged[meta] = seed.get(meta)
    sug = _s(payload.get("suggested_text_boundary"))
    if sug:
        merged["suggested_text_boundary"] = sug
    merged["content"] = outline_to_readable_content(merged)
    return normalize_sermon_outline(merged)


def assess_outline_quality_issues(
    outline: Any,
    *,
    for_ai_output: bool = False,
    occasion: Any = "",
    bundle: Mapping[str, Any] | None = None,
) -> list[str]:
    """Hard + soft quality. Verbosity / absolute max → hard via engine validator."""
    import re

    safe = normalize_sermon_outline(outline)
    structured = normalize_structured_outline(
        safe.get("structured") if safe.get("structured") else safe
    )
    issues = list(validate_structured_outline(structured))
    content = _s(safe.get("content")) or render_structured_outline(structured)

    for banned in OUTLINE_PLACEHOLDER_BANLIST:
        if banned in content:
            issues.append("placeholder")
            break
    if "##" in content or "```" in content:
        issues.append("raw_markdown")
    if re.search(r"(?m)^\*{0,2}\d+[.)]\s+\d+[.)]", content):
        issues.append("double_numbering")

    for heading in FORBIDDEN_HEADINGS:
        if heading.casefold() in content.casefold():
            issues.append("forbidden_heading")
            break
    for label in (
        "Exegetikai kibontás",
        "Hallgatói kapcsolat",
        "Kegyelmi kapcsolat",
        "gospel_resolution",
        "core_content",
    ):
        if label in content:
            issues.append("technical_labels")
            break

    focus = _usable_text(safe.get("main_idea")) or structured.get("focus_sentence")
    if focus and str(focus).casefold().startswith("a textus arra szólít"):
        issues.append("focus_formulaic")

    if for_ai_output:
        profile = outline_length_profile(
            resolve_outline_occasion(bundle, occasion=occasion),
            partial=_is_partial_workshop_bundle(bundle),
        )
        words = word_count(content)
        if words and (
            words < int(profile["soft_min"]) or words > LIMITS["target_max_words"]
        ):
            if "over_absolute_max" not in issues:
                issues.append("word_count_out_of_range")
        content_cf = content.casefold()
        if any(m in content_cf for m in _STOCK_PHRASE_MARKERS):
            issues.append("stock_phrases")
        filler_blob = " ".join(
            [
                content_cf,
                *[
                    _usable_text(m.get("transition")).casefold()
                    for m in (safe.get("movements") or [])
                    if isinstance(m, dict)
                ],
            ]
        )
        if any(m in filler_blob for m in _TRANSITION_FILLER_MARKERS):
            issues.append("transition_fillers")
        if "subpoint_length" in issues or "multi_paragraph_point" in issues:
            issues.append("verbose_point_bullets")
        if "full_sermon_like" in issues or "over_absolute_max" in issues:
            issues.append("sermon_like_verbosity")
        if "conclusion_too_long" in issues:
            issues.append("closing_too_long")

    # Repeated paragraphs in rendered content
    paras = [
        _normalize_cmp(p)
        for p in content.split("\n\n")
        if _usable_text(p) and len(_usable_text(p)) > 40
    ]
    seen: set[str] = set()
    for p in paras:
        if p in seen:
            issues.append("repeated_paragraphs")
            break
        seen.add(p)

    return list(dict.fromkeys(issues))


def synthesize_homiletic_outline(
    seed_outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    seed = normalize_sermon_outline(seed_outline)
    warnings: list[str] = []
    if generate_fn is None:
        return seed, warnings
    ctx = _ctx_for_prompt(bundle)
    locked = _locked_main_idea(bundle, seed)
    profile = outline_length_profile(
        resolve_outline_occasion(bundle),
        partial=_is_partial_workshop_bundle(bundle),
    )
    prompt = (
        "Készíts szószékre kész HOMILETIKAI VÁZLATOT (nem prédikációt).\n"
        f"ALKALOM: {profile['occasion']}. CÉL: ~{profile['target_range']} szó; "
        f"abszolút max {LIMITS['absolute_max_words']}.\n"
        f"ZÁROLT FÓKUSZ: {locked or '(nincs)'}\n\n"
        f"FORRÁS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_SYNTH_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.3)
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
    return apply_synth_payload_to_outline(
        seed, obj, bundle=bundle, replace_movements=True
    ), warnings


def repair_outline_as_lektor(
    outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    current = normalize_sermon_outline(outline)
    warnings: list[str] = []
    if generate_fn is None or not issues:
        return current, warnings
    ctx = _ctx_for_prompt(bundle)
    prompt = (
        f"{COMPRESS_INSTRUCTION}\n"
        f"ALKALOM: {outline_length_profile(resolve_outline_occasion(bundle))['occasion']}.\n"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n"
        f"ZÁROLT FŐGONDOLAT: {_locked_main_idea(bundle, current)}\n\n"
        f"FORRÁS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"JAVÍTANDÓ:\n{json.dumps(current.get('structured') or current, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_SYNTH_JSON_SHAPE}"
    )
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.2)
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
    return apply_synth_payload_to_outline(
        current, obj, bundle=bundle, replace_movements=True
    ), warnings


def regenerate_outline_part(
    outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    part: str,
    movement_id: str = "",
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    current = normalize_sermon_outline(outline)
    warnings: list[str] = []
    if generate_fn is None:
        warnings.append("Nincs generáló függvény a részleges újraíráshoz.")
        return current, warnings
    part_key = _s(part).casefold()
    target = {
        "opening": "introduction_direction",
        "opening_direction": "introduction_direction",
        "bevezetes": "introduction_direction",
        "introduction": "introduction_direction",
        "closing": "conclusion_direction",
        "lezaras": "conclusion_direction",
        "conclusion": "conclusion_direction",
        "megerkezes": "conclusion_direction",
        "movement": "point",
        "mozgás": "point",
        "mozgas": "point",
        "applications": "applications",
        "alkalmazas": "applications",
        "christ": "christ_arc",
        "christ_arc": "christ_arc",
    }.get(part_key, part_key)
    structured = normalize_structured_outline(
        current.get("structured") if current.get("structured") else current
    )
    ctx = _ctx_for_prompt(bundle)
    prompt = (
        f"Írd újra CSAK ezt: {target}. A többi mezőt másold át.\n"
        f"FÓKUSZ (zárolt): {_locked_main_idea(bundle, current)}\n"
        f"FORRÁS:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"JELENLEGI:\n{json.dumps(structured, ensure_ascii=False)}\n\n"
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
    new_struct = normalize_structured_outline(obj)
    if target == "introduction_direction" and new_struct.get("introduction_direction"):
        structured["introduction_direction"] = new_struct["introduction_direction"]
    elif target == "conclusion_direction" and new_struct.get("conclusion_direction"):
        structured["conclusion_direction"] = new_struct["conclusion_direction"]
    elif target == "point" and new_struct.get("points"):
        if movement_id and movement_id.startswith("pt_"):
            try:
                idx = int(movement_id.split("_")[1]) - 1
            except ValueError:
                idx = None
            if idx is not None and 0 <= idx < len(structured.get("points") or []):
                structured["points"][idx] = new_struct["points"][0]
            elif structured.get("points") and new_struct["points"]:
                structured["points"][0] = new_struct["points"][0]
        else:
            structured["points"] = new_struct["points"]
    elif target == "applications" and new_struct.get("points"):
        for i, pt in enumerate(structured.get("points") or []):
            if i < len(new_struct["points"]):
                src = new_struct["points"][i]
                pt["listener_movement"] = _s(
                    src.get("listener_movement") or src.get("application")
                )
    return apply_synth_payload_to_outline(
        current, structured, bundle=bundle, replace_movements=True
    ), warnings


def run_two_phase_outline_synthesis(
    seed_outline: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn | None,
) -> tuple[dict[str, Any], list[str]]:
    """Legacy belépő → közös séma + hard validáció + egy compress."""
    outline, warnings = synthesize_homiletic_outline(
        seed_outline, bundle, generate_fn=generate_fn
    )
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
            st = normalize_structured_outline(
                outline.get("structured") if outline.get("structured") else outline
            )
            st["scope_note"] = hint["text_boundary_note"]
            outline["structured"] = st
            outline["content"] = outline_to_readable_content(outline)

    issues = assess_outline_quality_issues(
        outline, for_ai_output=bool(generate_fn is not None), bundle=bundle
    )
    hard = _hard_quality_issues(issues)
    if hard and generate_fn is not None:
        outline, repair_warnings = repair_outline_as_lektor(
            outline, bundle, issues=issues, generate_fn=generate_fn
        )
        warnings.extend(repair_warnings)
        remaining = assess_outline_quality_issues(
            outline, for_ai_output=True, bundle=bundle
        )
        hard_remaining = _hard_quality_issues(remaining)
        if hard_remaining:
            warnings.append("QUALITY_GATE_FAILED:" + ",".join(hard_remaining))
        else:
            outline["provisional_sections"] = []
    elif generate_fn is not None and not hard:
        outline["provisional_sections"] = []
    outline = normalize_sermon_outline(outline)
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
