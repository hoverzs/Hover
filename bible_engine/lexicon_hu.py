from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from bible_engine.tbesg_parser import normalize_greek_strong_id


VALID_REVIEW_STATUSES = frozenset({"draft", "reviewed"})


@dataclass(frozen=True)
class HungarianLexiconEntry:
    strong_id: str
    lemma: str
    primary_gloss: str
    senses: tuple[str, ...]
    note: str | None
    source: str
    review_status: str


def validate_hungarian_lexicon_entry(entry: HungarianLexiconEntry) -> None:
    if normalize_greek_strong_id(entry.strong_id) != entry.strong_id:
        raise ValueError(
            f"Hungarian lexicon entry strong_id is not normalized: {entry.strong_id!r}."
        )
    if not entry.lemma.strip():
        raise ValueError("Hungarian lexicon entry lemma must not be empty.")
    if not entry.primary_gloss.strip():
        raise ValueError("Hungarian lexicon entry primary_gloss must not be empty.")
    if not entry.senses:
        raise ValueError("Hungarian lexicon entry must contain at least one sense.")

    normalized_senses = []
    for sense in entry.senses:
        if not isinstance(sense, str) or not sense.strip():
            raise ValueError("Hungarian lexicon entry senses must not contain empty values.")
        normalized_senses.append(sense.strip())

    if len(set(normalized_senses)) != len(normalized_senses):
        raise ValueError("Hungarian lexicon entry senses must not contain duplicates.")
    if entry.review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(
            "Hungarian lexicon entry review_status must be 'draft' or 'reviewed'."
        )
    if not entry.source.strip():
        raise ValueError("Hungarian lexicon entry source must not be empty.")


def load_hungarian_lexicon(path: str | Path) -> dict[str, HungarianLexiconEntry]:
    source_path = Path(path)
    try:
        raw_data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Hungarian lexicon JSON: {exc.msg}.") from exc

    if not isinstance(raw_data, list):
        raise ValueError("Invalid Hungarian lexicon JSON: root value must be a list.")

    entries: dict[str, HungarianLexiconEntry] = {}
    for index, raw_entry in enumerate(raw_data, start=1):
        entry = _entry_from_json(raw_entry, index)
        validate_hungarian_lexicon_entry(entry)
        if entry.strong_id in entries:
            raise ValueError(
                f"Duplicate Hungarian lexicon strong_id: {entry.strong_id!r}."
            )
        entries[entry.strong_id] = entry
    return entries


def get_hungarian_lexicon_entry(
    entries: dict[str, HungarianLexiconEntry],
    strong_id: str,
) -> HungarianLexiconEntry | None:
    normalized = normalize_greek_strong_id(strong_id)
    return entries.get(normalized)


def _entry_from_json(raw_entry: Any, index: int) -> HungarianLexiconEntry:
    if not isinstance(raw_entry, dict):
        raise ValueError(f"Invalid Hungarian lexicon record #{index}: expected object.")

    try:
        senses = raw_entry["senses"]
        note = raw_entry.get("note")
        entry = HungarianLexiconEntry(
            strong_id=str(raw_entry["strong_id"]).strip(),
            lemma=str(raw_entry["lemma"]).strip(),
            primary_gloss=str(raw_entry["primary_gloss"]).strip(),
            senses=tuple(senses),
            note=str(note).strip() if note is not None and str(note).strip() else None,
            source=str(raw_entry["source"]).strip(),
            review_status=str(raw_entry["review_status"]).strip(),
        )
    except KeyError as exc:
        raise ValueError(
            f"Invalid Hungarian lexicon record #{index}: missing field {exc.args[0]!r}."
        ) from exc
    except TypeError as exc:
        raise ValueError(
            f"Invalid Hungarian lexicon record #{index}: senses must be a list."
        ) from exc

    return entry
