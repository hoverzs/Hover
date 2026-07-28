from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass


_REF_RE = re.compile(
    r"^(?P<book>[1-3]?[A-Za-z]{2,3})\.(?P<chapter>\d+)\.(?P<verse>\d+)#"
    r"(?P<word_index>\d+)=(?P<source_edition>.+)$"
)
_HEBREW_MARKS_RE = re.compile(r"[\u0591-\u05BD\u05BF-\u05C7]")
_STRONG_RE = re.compile(r"H\d{4}[A-Z]?", re.IGNORECASE)
_CORE_STRONG_RE = re.compile(r"\{(?P<strong>H\d{4}[A-Z]?)\}", re.IGNORECASE)


@dataclass(frozen=True)
class HebrewComponent:
    surface: str
    strong_id: str
    morphology_code: str
    role: str
    gloss: str = ""


@dataclass(frozen=True)
class HebrewToken:
    book: str
    chapter: int
    verse: int
    word_index: int
    token_index: int
    surface: str
    surface_without_accents: str
    transliteration: str
    english_gloss: str
    lemma: str
    strong_ids: tuple[str, ...]
    morphology_code: str
    language: str
    prefix_components: tuple[HebrewComponent, ...]
    core_component: HebrewComponent | None
    suffix_components: tuple[HebrewComponent, ...]
    ketiv: str
    qere: str
    punctuation: str
    maqaf: bool
    source_token_id: str
    source_edition: str
    meaning_variant: str
    spelling_variant: str
    expanded_strong_tags: str
    raw_fields: tuple[str, ...]

    @property
    def stable_key(self) -> str:
        return f"{self.book}:{self.chapter}:{self.verse}:{self.word_index}"


def parse_tahot_row(row: str, *, token_index: int | None = None) -> HebrewToken:
    fields = next(csv.reader([row.rstrip("\n")], delimiter="\t"))
    if len(fields) < 12:
        raise ValueError(f"Invalid TAHOT row: expected at least 12 columns, got {len(fields)}")

    source_token_id = fields[0].strip()
    match = _REF_RE.match(source_token_id)
    if not match:
        raise ValueError(f"Invalid TAHOT reference field: {source_token_id!r}")

    surface = _nfc(fields[1].strip())
    dstrongs = fields[4].strip()
    morphology = fields[5].strip()
    meaning_variant = fields[6].strip() if len(fields) > 6 else ""
    spelling_variant = fields[7].strip() if len(fields) > 7 else ""
    expanded = fields[11].strip() if len(fields) > 11 else ""
    components = _build_components(surface, dstrongs, morphology, expanded)
    core_component = next((item for item in components if item.role == "core"), None)

    return HebrewToken(
        book=match.group("book"),
        chapter=int(match.group("chapter")),
        verse=int(match.group("verse")),
        word_index=int(match.group("word_index")),
        token_index=token_index if token_index is not None else int(match.group("word_index")),
        surface=surface,
        surface_without_accents=strip_hebrew_accents(surface),
        transliteration=fields[2].strip(),
        english_gloss=fields[3].strip(),
        lemma=_lemma_from_expanded(expanded),
        strong_ids=tuple(dict.fromkeys(match.upper() for match in _STRONG_RE.findall(dstrongs))),
        morphology_code=morphology,
        language="aramaic" if morphology.startswith("A") else "hebrew",
        prefix_components=tuple(item for item in components if item.role == "prefix"),
        core_component=core_component,
        suffix_components=tuple(item for item in components if item.role == "suffix"),
        ketiv=_variant_text(meaning_variant, "K"),
        qere=surface if "Q" in match.group("source_edition") else "",
        punctuation=_punctuation_from_surface(surface),
        maqaf="\\H9014" in dstrongs or "\u05be" in surface,
        source_token_id=source_token_id,
        source_edition=match.group("source_edition"),
        meaning_variant=meaning_variant,
        spelling_variant=spelling_variant,
        expanded_strong_tags=expanded,
        raw_fields=tuple(fields),
    )


def parse_tahot_rows(text: str, *, books: set[str] | None = None) -> list[HebrewToken]:
    tokens: list[HebrewToken] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not _REF_RE.match(line.split("\t", 1)[0]):
            continue
        if books:
            book = line.split(".", 1)[0]
            if book not in books:
                continue
        tokens.append(parse_tahot_row(line, token_index=len(tokens) + 1))
    return tokens


def strip_hebrew_accents(value: str) -> str:
    return _HEBREW_MARKS_RE.sub("", unicodedata.normalize("NFD", value)).replace("/", "").replace("\\", "")


def _build_components(
    surface: str,
    dstrongs: str,
    morphology: str,
    expanded: str,
) -> tuple[HebrewComponent, ...]:
    surfaces = [part for part in re.split(r"[/\\]", surface) if part]
    strong_parts = [part for part in re.split(r"[/\\]", dstrongs) if part]
    morph_parts = [part for part in morphology.split("/") if part]
    components: list[HebrewComponent] = []
    core_index = _core_index(strong_parts)
    for index, strong_part in enumerate(strong_parts):
        strong = _strong_from_part(strong_part)
        if not strong:
            continue
        role = "core" if index == core_index else ("prefix" if index < core_index else "suffix")
        surface_part = surfaces[min(index, len(surfaces) - 1)] if surfaces else surface
        morph_part = morph_parts[min(index, len(morph_parts) - 1)] if morph_parts else morphology
        components.append(
            HebrewComponent(
                surface=_nfc(surface_part),
                strong_id=strong,
                morphology_code=morph_part,
                role=role,
                gloss=_gloss_for_strong(expanded, strong),
            )
        )
    return tuple(components)


def _core_index(strong_parts: list[str]) -> int:
    for index, part in enumerate(strong_parts):
        if "{" in part and "}" in part:
            return index
    return 0


def _strong_from_part(part: str) -> str:
    core = _CORE_STRONG_RE.search(part)
    if core:
        return core.group("strong").upper()
    found = _STRONG_RE.search(part)
    return found.group(0).upper() if found else ""


def _lemma_from_expanded(expanded: str) -> str:
    match = re.search(r"\{H\d{4}[A-Z]?=([^=}/\\]+)=", expanded)
    return _nfc(match.group(1)) if match else ""


def _gloss_for_strong(expanded: str, strong_id: str) -> str:
    pattern = re.escape(strong_id) + r"=[^=}/\\]+=?([^}/\\]*)"
    match = re.search(pattern, expanded)
    return (match.group(1) or "").strip() if match else ""


def _variant_text(value: str, marker: str) -> str:
    match = re.search(rf"{re.escape(marker)}=\s*[^()]*\(([^)]*)\)", value)
    return _nfc(match.group(1)) if match else ""


def _punctuation_from_surface(surface: str) -> str:
    parts = surface.split("\\", 1)
    return parts[1] if len(parts) > 1 else ""


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value or "")
