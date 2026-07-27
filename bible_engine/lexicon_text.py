from __future__ import annotations

from dataclasses import dataclass
import html
import re

from bible_engine.tbesg_parser import GreekLexiconEntry


_BREAK_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_TAG_NAME_RE = re.compile(r"</?\s*([A-Za-z][A-Za-z0-9_-]*)")
_REF_RE = re.compile(r"<\s*ref\s*=\s*(['\"])(.*?)\1\s*>", re.IGNORECASE)
_KNOWN_TAGS = frozenset({"b", "br", "i", "re", "ref"})


@dataclass(frozen=True)
class LexiconMeaning:
    raw: str
    plain_text: str
    paragraphs: tuple[str, ...]
    references: tuple[str, ...]
    warnings: tuple[str, ...]


def parse_lexicon_meaning(raw: str | None) -> LexiconMeaning:
    if raw is None:
        return _empty_meaning("")

    if raw == "":
        return _empty_meaning(raw)

    warnings = _unknown_tag_warnings(raw)
    references = tuple(html.unescape(ref.strip()) for _, ref in _REF_RE.findall(raw))

    text = _BREAK_RE.sub("\n", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    paragraphs = _normalize_paragraphs(text)

    return LexiconMeaning(
        raw=raw,
        plain_text="\n".join(paragraphs),
        paragraphs=paragraphs,
        references=references,
        warnings=warnings,
    )


def get_plain_lexicon_meaning(entry: GreekLexiconEntry) -> str:
    return parse_lexicon_meaning(entry.meaning_raw).plain_text


def _empty_meaning(raw: str) -> LexiconMeaning:
    return LexiconMeaning(
        raw=raw,
        plain_text="",
        paragraphs=(),
        references=(),
        warnings=(),
    )


def _normalize_paragraphs(text: str) -> tuple[str, ...]:
    paragraphs: list[str] = []
    for line in text.splitlines():
        normalized = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        if normalized:
            paragraphs.append(normalized)
    return tuple(paragraphs)


def _unknown_tag_warnings(raw: str) -> tuple[str, ...]:
    unknown_tags = sorted(
        {
            match.group(1).lower()
            for match in _TAG_NAME_RE.finditer(raw)
            if match.group(1).lower() not in _KNOWN_TAGS
        }
    )
    return tuple(f"Unknown TBESG tag preserved as text content: {tag}" for tag in unknown_tags)
