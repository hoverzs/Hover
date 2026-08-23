"""Read-only TAGNT Greek token adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.manifest import ManifestSource


@dataclass(frozen=True)
class TagntVerseTokens:
    verse: int
    tokens: tuple[dict[str, Any], ...]


class TagntAdapter:
    source_id = "stepbible_tagnt"

    def __init__(self, source: ManifestSource) -> None:
        self._source = source
        self._database_path = source.resolved_path

    @property
    def available(self) -> bool:
        return self._source.enabled and self._database_path.is_file()

    def load_passage_tokens(self, reference: CanonicalReference) -> list[TagntVerseTokens]:
        if not self.available:
            raise FileNotFoundError(
                f"Required TAGNT source unavailable: {self._database_path}"
            )

        from bible_engine.greek_token_repository import load_greek_passage_tokens

        display_ref = _reference_display_for_tagnt(reference)
        verses = load_greek_passage_tokens(
            display_ref,
            database_path=self._database_path,
        )
        result: list[TagntVerseTokens] = []
        for verse_row in verses:
            tokens = tuple(
                {
                    "word_index": token.word_index,
                    "greek_form": token.greek_form,
                    "lemma": token.lemma,
                    "morph_code": token.morph_code,
                    "strong_id": token.strong_id or None,
                }
                for token in verse_row.tokens
            )
            result.append(TagntVerseTokens(verse=verse_row.verse, tokens=tokens))
        return result


def _reference_display_for_tagnt(reference: CanonicalReference) -> str:
    """Map canonical reference to RUF-style input expected by TAGNT repository."""
    book_code = reference.ruf_book_code
    if reference.is_single_verse:
        return f"{book_code} {reference.start_chapter},{reference.start_verse}"
    if reference.start_chapter == reference.end_chapter:
        return (
            f"{book_code} {reference.start_chapter},"
            f"{reference.start_verse}-{reference.end_verse}"
        )
    return (
        f"{book_code} {reference.start_chapter},{reference.start_verse}-"
        f"{reference.end_chapter},{reference.end_verse}"
    )
