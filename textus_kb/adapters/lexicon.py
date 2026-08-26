"""Read-only Greek lexicon adapters (TBESG + Hungarian overlay)."""

from __future__ import annotations

from dataclasses import dataclass

from textus_kb.manifest import ManifestSource


@dataclass(frozen=True)
class LexiconLookup:
    strong_id: str
    lemma: str
    gloss_en: str | None
    gloss_hu: str | None
    source_ids: tuple[str, ...]


class LexiconAdapter:
    TBESG_SOURCE_ID = "stepbible_tbesg"
    HU_SOURCE_ID = "lexicon_hu_overlay"

    def __init__(
        self,
        tbesg_source: ManifestSource | None,
        hu_source: ManifestSource | None,
    ) -> None:
        self._tbesg_source = tbesg_source
        self._hu_source = hu_source
        self._hu_entries: dict | None = None
        self._hu_aliases: dict | None = None
        self._tbesg_path = (
            tbesg_source.resolved_path
            if tbesg_source is not None and tbesg_source.enabled
            else None
        )
        self._hu_path = (
            hu_source.resolved_path
            if hu_source is not None and hu_source.enabled
            else None
        )

    @property
    def tbesg_available(self) -> bool:
        return (
            self._tbesg_source is not None
            and self._tbesg_source.enabled
            and self._tbesg_path is not None
            and self._tbesg_path.is_file()
        )

    @property
    def hu_available(self) -> bool:
        return (
            self._hu_source is not None
            and self._hu_source.enabled
            and self._hu_path is not None
            and self._hu_path.is_file()
        )

    def lookup(self, strong_id: str) -> LexiconLookup | None:
        if not strong_id or not str(strong_id).strip():
            return None

        normalized = str(strong_id).strip().upper()
        if not normalized.startswith("G"):
            return None

        lemma = ""
        gloss_en: str | None = None
        source_ids: list[str] = []

        if self.tbesg_available:
            from bible_engine.greek_lexicon_repository import get_tbesg_lexicon_entry

            entry = get_tbesg_lexicon_entry(normalized, database_path=self._tbesg_path)
            if entry is not None:
                lemma = entry.lemma or ""
                gloss_en = entry.gloss or None
                source_ids.append(self.TBESG_SOURCE_ID)

        gloss_hu: str | None = None
        if self.hu_available:
            hu_entries = self._load_hu_entries()
            hu_aliases = self._load_hu_aliases()
            if hu_entries is not None:
                from bible_engine.lexicon_hu import resolve_hungarian_lexicon_entry

                resolution = resolve_hungarian_lexicon_entry(
                    hu_entries,
                    normalized,
                    hu_aliases or {},
                )
                if resolution is not None:
                    gloss_hu = resolution.entry.primary_gloss
                    if not lemma:
                        lemma = resolution.entry.lemma
                    source_ids.append(self.HU_SOURCE_ID)

        if not source_ids:
            return None

        return LexiconLookup(
            strong_id=normalized,
            lemma=lemma,
            gloss_en=gloss_en,
            gloss_hu=gloss_hu,
            source_ids=tuple(dict.fromkeys(source_ids)),
        )

    def _load_hu_entries(self) -> dict | None:
        if self._hu_entries is not None:
            return self._hu_entries
        if not self.hu_available or self._hu_path is None:
            self._hu_entries = {}
            return self._hu_entries
        from bible_engine.lexicon_hu import load_hungarian_lexicon

        self._hu_entries = load_hungarian_lexicon(self._hu_path)
        return self._hu_entries

    def _load_hu_aliases(self) -> dict | None:
        if self._hu_aliases is not None:
            return self._hu_aliases
        if not self.hu_available:
            self._hu_aliases = {}
            return self._hu_aliases
        from bible_engine.lexicon_hu import load_strong_aliases

        self._hu_aliases = load_strong_aliases()
        return self._hu_aliases
