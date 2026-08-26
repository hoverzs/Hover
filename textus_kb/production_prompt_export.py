"""Read-only export of the real production section prompt (dev benchmark).

Builds the same prompt string ``generate_section()`` would send for a given
passage + module, without mutating production flags or running the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError

# KB module → app SECTION_PROMPTS key / SECTION_LABELS
MODULE_TO_SECTION: dict[str, str] = {
    "exegesis": "exegesis",
    "historical_context": "history",
    "history": "history",
}


@dataclass(frozen=True)
class ProductionPromptExport:
    passage_canonical: str
    passage_display: str
    module: str
    section_key: str
    tab_label: str
    production_prompt: str
    passage_text_chars: int
    passage_text_source: str
    include_original_language_tokens: bool
    include_biblical_place_context: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "passage_canonical": self.passage_canonical,
            "passage_display": self.passage_display,
            "module": self.module,
            "section_key": self.section_key,
            "tab_label": self.tab_label,
            "production_prompt_chars": len(self.production_prompt),
            "passage_text_chars": self.passage_text_chars,
            "passage_text_source": self.passage_text_source,
            "include_original_language_tokens": self.include_original_language_tokens,
            "include_biblical_place_context": self.include_biblical_place_context,
        }


def _hu_abbr_for_osis(osis_id: str) -> str:
    try:
        from textus_kb.books import OSIS_BY_ID
        from ruf_bible_service import CANONICAL_BOOKS
    except Exception:
        return osis_id
    record = OSIS_BY_ID.get(osis_id)
    ruf_code = (record.ruf_code if record is not None else osis_id).upper()
    for book_info in CANONICAL_BOOKS:
        if str(book_info.code).upper() == ruf_code:
            return book_info.abbr
    # Fallback: match OSIS name in BOOK_LOOKUP-style aliases via lowercase.
    try:
        from ruf_bible_service import BOOK_LOOKUP

        hit = BOOK_LOOKUP.get(osis_id.lower())
        if hit is not None:
            return hit.abbr
    except Exception:
        pass
    return osis_id


def display_reference_hu(passage: str) -> str:
    """Convert canonical/OSIS-like refs to Hungarian display (e.g. Jn 4,1-42)."""
    try:
        ref = CanonicalReference.parse(passage)
    except CanonicalReferenceError:
        return str(passage or "").strip()
    abbr = _hu_abbr_for_osis(ref.book_id)
    if ref.start_chapter == ref.end_chapter:
        if ref.start_verse == ref.end_verse:
            return f"{abbr} {ref.start_chapter},{ref.start_verse}"
        return f"{abbr} {ref.start_chapter},{ref.start_verse}-{ref.end_verse}"
    return (
        f"{abbr} {ref.start_chapter},{ref.start_verse}-"
        f"{ref.end_chapter},{ref.end_verse}"
    )


def fetch_passage_text_for_benchmark(passage: str) -> tuple[str, str]:
    """Best-effort RÚF text for benchmark prompts. Returns (text, source_note)."""
    try:
        from ruf_bible_service import fetch_ruf_passage
    except Exception as exc:  # pragma: no cover
        return "", f"ruf_import_failed:{type(exc).__name__}"

    display = display_reference_hu(passage)
    result = fetch_ruf_passage(display)
    if not isinstance(result, dict):
        return "", "ruf_invalid_response"
    text = str(result.get("text") or "").strip()
    if text and result.get("success") is not False and not result.get("error"):
        return text, str(result.get("source_name") or "ruf")
    return "", f"ruf_unavailable:{result.get('error') or 'empty'}"


def build_production_section_prompt(
    passage: str,
    *,
    module: str,
    passage_text: str | None = None,
    bible_translation: str = "RÚF",
) -> ProductionPromptExport:
    """Build the exact SECTION_PROMPTS prompt for passage + module.

    Uses the same ``build_alap_from_state`` + ``SECTION_PROMPTS`` path as
    ``generate_section()``, with ephemeral session fields only.
    """
    module_key = "historical_context" if module == "history" else module
    if module_key not in MODULE_TO_SECTION:
        raise ValueError(f"Unsupported module for production prompt export: {module!r}")

    section_key = MODULE_TO_SECTION[module_key]
    ref = CanonicalReference.parse(passage)
    canonical = ref.canonical_string()
    display = display_reference_hu(canonical)

    text_source = "caller"
    if passage_text is None:
        passage_text, text_source = fetch_passage_text_for_benchmark(canonical)
    passage_text = str(passage_text or "")

    # Import app late — Streamlit session side effects.
    import app as app_module

    section_prompts = app_module.SECTION_PROMPTS
    section_labels = app_module.SECTION_LABELS
    build_alap = app_module.build_alap_from_state
    st = app_module.st

    if section_key not in section_prompts:
        raise KeyError(f"SECTION_PROMPTS missing key: {section_key!r}")

    tab_label = str(section_labels.get(section_key, section_key))
    include_tokens = section_key == "exegesis"
    include_places = section_key == "history"

    # Ephemeral session fields mirroring generate_section → build_alap_from_state.
    st.session_state["last_igehely"] = display
    st.session_state["passage_text"] = passage_text
    st.session_state["passage_text_input"] = passage_text
    st.session_state["bible_translation"] = bible_translation
    st.session_state.setdefault("last_alkalom", "")
    st.session_state.setdefault("last_stilus", "")
    st.session_state.setdefault("last_sajat", "")

    alap = build_alap(
        include_pastoral_context=False,
        include_original_language_tokens=include_tokens,
        include_biblical_place_context=include_places,
    )
    prompt = section_prompts[section_key].format(alap=alap)

    return ProductionPromptExport(
        passage_canonical=canonical,
        passage_display=display,
        module=module_key,
        section_key=section_key,
        tab_label=tab_label,
        production_prompt=prompt,
        passage_text_chars=len(passage_text),
        passage_text_source=text_source,
        include_original_language_tokens=include_tokens,
        include_biblical_place_context=include_places,
    )


__all__ = [
    "MODULE_TO_SECTION",
    "ProductionPromptExport",
    "build_production_section_prompt",
    "display_reference_hu",
    "fetch_passage_text_for_benchmark",
]
