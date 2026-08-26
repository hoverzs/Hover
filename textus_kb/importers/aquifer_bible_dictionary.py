"""Reproducible pilot importer for Aquifer Open Bible Dictionary."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textus_kb.paths import PROJECT_ROOT
from textus_kb.pilot_registry import (
    JOHN_4_PILOT,
    PilotPassage,
    get_pilot,
    index_reference_overlaps_pilot,
)

AQUIFER_DICTIONARY_SOURCE_ID = "aquifer_open_bible_dictionary"
AQUIFER_LICENSE = "CC-BY-SA-4.0"
AQUIFER_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
AQUIFER_ATTRIBUTION = (
    "Aquifer Open Bible Dictionary © 2026 Mission Mutual, adapted from Tyndale Open Bible "
    "Dictionary © 2023 Tyndale House Publishers. Licensed under CC BY-SA 4.0."
)
AQUIFER_UPSTREAM_REPO = "https://github.com/BibleAquifer/AquiferOpenBibleDictionary"
DEFAULT_UPSTREAM_PATH = PROJECT_ROOT / "_upstream_audit" / "AquiferOpenBibleDictionary"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "kb" / "aquifer" / "john_4_1_42_bible_dictionary.json"
UPSTREAM_ENV_VAR = "TEXTUS_AQUIFER_DICTIONARY_UPSTREAM_PATH"

# Backward-compatible aliases for Phase 3C callers/tests.
JOHN_BOOK_NUM = JOHN_4_PILOT.usfm_book_num
JOHN_4_INDEX_LO = JOHN_4_PILOT.org_index_lo
JOHN_4_INDEX_HI = JOHN_4_PILOT.org_index_hi
PILOT_CANONICAL = JOHN_4_PILOT.canonical
PILOT_INDEX_REFERENCES = JOHN_4_PILOT.dictionary_index_refs
PILOT_PLACE_ENTITY_IDS = JOHN_4_PILOT.dictionary_place_ids
CHUNK_MAX_PLAIN_CHARS = 1200

_HEADING_SPLIT_RE = re.compile(r"(?=<h[1-3][^>]*>)", re.IGNORECASE)
_BLOCK_SPLIT_RE = re.compile(r"(?=</p>|</li>)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_TAG_RE = re.compile(r"<h([1-3])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)


@dataclass
class ImportIssue:
    level: str  # warning | error
    message: str
    article_id: str | None = None


@dataclass
class DictionaryChunk:
    chunk_id: str
    chunk_index: int
    heading: str | None
    content_html: str
    content_plain: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DictionaryRecord:
    article_id: str
    content_id: str
    reference_id: int | None
    title: str
    index_reference: str
    language: str
    content_html: str
    chunks: list[DictionaryChunk] = field(default_factory=list)
    passage_associations: list[dict[str, str]] = field(default_factory=list)
    entity_topics: list[dict[str, str]] = field(default_factory=list)
    selection_reason: str = ""
    source_id: str = AQUIFER_DICTIONARY_SOURCE_ID
    license: str = AQUIFER_LICENSE
    license_url: str = AQUIFER_LICENSE_URL
    attribution: str = AQUIFER_ATTRIBUTION

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "content_id": self.content_id,
            "reference_id": self.reference_id,
            "title": self.title,
            "index_reference": self.index_reference,
            "language": self.language,
            "content_html": self.content_html,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "passage_associations": list(self.passage_associations),
            "entity_topics": list(self.entity_topics),
            "selection_reason": self.selection_reason,
            "source_id": self.source_id,
            "license": self.license,
            "license_url": self.license_url,
            "attribution": self.attribution,
        }


@dataclass
class PilotImportResult:
    output_path: Path
    entry_count: int
    chunk_count: int
    issues: list[ImportIssue]
    upstream_commit: str
    upstream_resource_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "entry_count": self.entry_count,
            "chunk_count": self.chunk_count,
            "issues": [asdict(issue) for issue in self.issues],
            "upstream_commit": self.upstream_commit,
            "upstream_resource_version": self.upstream_resource_version,
        }


def resolve_upstream_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env = os.environ.get(UPSTREAM_ENV_VAR, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_UPSTREAM_PATH.resolve()


def read_upstream_commit(upstream_root: Path) -> str:
    git_head = upstream_root / ".git" / "refs" / "heads" / "main"
    if git_head.is_file():
        return git_head.read_text(encoding="utf-8").strip()
    return "unknown"


def import_john_4_pilot(
    *,
    upstream_root: str | Path | None = None,
    output_path: str | Path | None = None,
    language: str = "eng",
) -> PilotImportResult:
    """Import Jn 4-relevant Aquifer Bible Dictionary entries into a pilot JSON bundle."""
    return import_dictionary_pilot(
        pilot_id=JOHN_4_PILOT.id,
        upstream_root=upstream_root,
        output_path=output_path,
        language=language,
    )


def import_dictionary_pilot(
    *,
    pilot_id: str,
    upstream_root: str | Path | None = None,
    output_path: str | Path | None = None,
    language: str = "eng",
) -> PilotImportResult:
    """Import Aquifer Bible Dictionary entries for a registered pilot passage."""
    pilot = get_pilot(pilot_id)
    root = resolve_upstream_path(upstream_root)
    out = Path(output_path) if output_path is not None else pilot.dictionary_resolved
    out.parent.mkdir(parents=True, exist_ok=True)

    metadata_path = root / language / "metadata.json"
    json_dir = root / language / "json"
    issues: list[ImportIssue] = []

    if not metadata_path.is_file():
        raise FileNotFoundError(f"Aquifer dictionary metadata missing: {metadata_path}")
    if not json_dir.is_dir():
        raise FileNotFoundError(f"Aquifer dictionary JSON dir missing: {json_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    resource_version = str(metadata.get("resource_metadata", {}).get("version", "unknown"))
    upstream_commit = read_upstream_commit(root)

    articles_by_index = _load_articles_by_index(json_dir)
    selected = _select_pilot_articles(articles_by_index, pilot)

    entries: list[DictionaryRecord] = []
    chunk_total = 0
    for index_reference in sorted(selected.keys()):
        article = selected[index_reference]
        try:
            record, article_issues = _normalize_article(article, index_reference, pilot)
        except Exception as exc:  # noqa: BLE001 - importer collects issues
            issues.append(
                ImportIssue(
                    "error",
                    f"Normalization failed: {exc}",
                    article_id=str(article.get("content_id")),
                )
            )
            continue
        issues.extend(article_issues)
        if record is None:
            continue
        entries.append(record)
        chunk_total += len(record.chunks)

    bundle = {
        "bundle_version": "1",
        "pilot_id": pilot.id,
        "pilot_scope": pilot.canonical,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_id": AQUIFER_DICTIONARY_SOURCE_ID,
        "upstream_repository": AQUIFER_UPSTREAM_REPO,
        "upstream_commit": upstream_commit,
        "upstream_resource_version": resource_version,
        "language": language,
        "license": AQUIFER_LICENSE,
        "license_url": AQUIFER_LICENSE_URL,
        "attribution": AQUIFER_ATTRIBUTION,
        "content_hash": _hash_entries(entries),
        "import_issues": [asdict(issue) for issue in issues],
        "entries": [entry.to_dict() for entry in entries],
    }
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return PilotImportResult(
        output_path=out,
        entry_count=len(entries),
        chunk_count=chunk_total,
        issues=issues,
        upstream_commit=upstream_commit,
        upstream_resource_version=resource_version,
    )


def _load_articles_by_index(json_dir: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(json_dir.glob("*.content.json")):
        articles = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(articles, list):
            continue
        for article in articles:
            if not isinstance(article, dict):
                continue
            index_reference = str(article.get("index_reference") or "").strip()
            if not index_reference:
                continue
            grouped.setdefault(index_reference, []).append(article)
    return grouped


def _select_pilot_articles(
    articles_by_index: dict[str, list[dict[str, Any]]],
    pilot: PilotPassage,
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for index_reference in sorted(pilot.dictionary_index_refs):
        candidates = articles_by_index.get(index_reference, [])
        if not candidates:
            continue
        chosen = _pick_best_duplicate(candidates)
        selected[index_reference] = chosen
    return selected


def _pick_best_duplicate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer the fullest article body; tie-break on lowest content_id."""

    def sort_key(article: dict[str, Any]) -> tuple[int, str]:
        content = str(article.get("content") or "")
        return (-len(content), str(article.get("content_id") or ""))

    return sorted(candidates, key=sort_key)[0]


def _normalize_article(
    article: dict[str, Any],
    index_reference: str,
    pilot: PilotPassage,
) -> tuple[DictionaryRecord | None, list[ImportIssue]]:
    issues: list[ImportIssue] = []
    article_id = str(article.get("content_id") or "").strip()
    title = str(article.get("title") or "").strip()
    content_html = str(article.get("content") or "")
    if not article_id or not title or not content_html:
        issues.append(
            ImportIssue(
                "warning",
                "Skipping article with missing id/title/content.",
                article_id=article_id or None,
            )
        )
        return None, issues

    passage_associations = _extract_passage_associations(article, pilot)
    entity_topics = _infer_entity_topics(index_reference, passage_associations, pilot)
    selection_reason = _selection_reason(index_reference, passage_associations, entity_topics)
    chunks = _chunk_html_content(article_id, content_html)

    record = DictionaryRecord(
        article_id=article_id,
        content_id=article_id,
        reference_id=_safe_int(article.get("reference_id")),
        title=title,
        index_reference=index_reference,
        language=str(article.get("language") or "eng"),
        content_html=content_html,
        chunks=chunks,
        passage_associations=passage_associations,
        entity_topics=entity_topics,
        selection_reason=selection_reason,
    )
    return record, issues


def _extract_passage_associations(
    article: dict[str, Any],
    pilot: PilotPassage,
) -> list[dict[str, str]]:
    associations: list[dict[str, str]] = []
    for passage in article.get("associations", {}).get("passage", []):
        start_ref = str(passage.get("start_ref") or "")
        end_ref = str(passage.get("end_ref") or start_ref)
        if not start_ref.isdigit() or not end_ref.isdigit():
            continue
        if not index_reference_overlaps_pilot(int(start_ref), int(end_ref), pilot):
            continue
        associations.append(
            {
                "start_ref": start_ref,
                "end_ref": end_ref,
                "start_ref_usfm": str(passage.get("start_ref_usfm") or ""),
                "end_ref_usfm": str(passage.get("end_ref_usfm") or ""),
            }
        )
    associations.sort(key=lambda item: (item["start_ref"], item["end_ref"]))
    return associations


def _extract_john4_passage_associations(article: dict[str, Any]) -> list[dict[str, str]]:
    return _extract_passage_associations(article, JOHN_4_PILOT)


def _infer_entity_topics(
    index_reference: str,
    passage_associations: list[dict[str, str]],
    pilot: PilotPassage,
) -> list[dict[str, str]]:
    topics: list[dict[str, str]] = []
    place_map = {
        "sychar": "sychar",
        "samaria": "samaria_2",
        "samaritans": "samaria_2",
        "mount gerizim": "mount_gerizim",
        "galilee": "galilee_1",
        "judea judeans": "judea_1",
        "jacobs well": "sychar",
        "jerusalem": "jerusalem",
        "jericho": "jericho",
    }
    place_id = place_map.get(index_reference)
    if place_id and place_id in pilot.dictionary_place_ids:
        topics.append(
            {
                "entity_id": place_id,
                "entity_type": "place",
                "source": "inferred_from_pilot_place_links",
            }
        )
    if passage_associations:
        topics.append(
            {
                "entity_id": pilot.canonical,
                "entity_type": "passage",
                "source": "upstream_passage_association",
            }
        )
    return topics


def _selection_reason(
    index_reference: str,
    passage_associations: list[dict[str, str]],
    entity_topics: list[dict[str, str]],
) -> str:
    if passage_associations:
        return "direct_passage_association"
    if any(topic.get("entity_type") == "place" for topic in entity_topics):
        return "pilot_place_entity_match"
    return "pilot_index_reference_match"


def _chunk_html_content(article_id: str, content_html: str) -> list[DictionaryChunk]:
    sections = [section.strip() for section in _HEADING_SPLIT_RE.split(content_html) if section.strip()]
    if not sections:
        sections = [content_html]

    chunks: list[DictionaryChunk] = []
    chunk_index = 0
    current_heading: str | None = None

    for section in sections:
        heading_match = _HEADING_TAG_RE.search(section)
        if heading_match:
            current_heading = html_to_plain(heading_match.group(2))

        section_plain = html_to_plain(section)
        if len(section_plain) <= CHUNK_MAX_PLAIN_CHARS:
            chunk_index += 1
            chunks.append(
                DictionaryChunk(
                    chunk_id=f"{article_id}-c{chunk_index:03d}",
                    chunk_index=chunk_index,
                    heading=current_heading,
                    content_html=section.strip(),
                    content_plain=section_plain,
                )
            )
            continue

        blocks = [block.strip() for block in _BLOCK_SPLIT_RE.split(section) if block.strip()]
        if not blocks:
            blocks = [section]

        current_html: list[str] = []
        current_plain_len = 0
        for block in blocks:
            block_plain_len = len(html_to_plain(block))
            if current_html and current_plain_len + block_plain_len > CHUNK_MAX_PLAIN_CHARS:
                chunk_index += 1
                joined = "".join(current_html)
                chunks.append(
                    DictionaryChunk(
                        chunk_id=f"{article_id}-c{chunk_index:03d}",
                        chunk_index=chunk_index,
                        heading=current_heading,
                        content_html=joined,
                        content_plain=html_to_plain(joined),
                    )
                )
                current_html = []
                current_plain_len = 0
            current_html.append(block)
            current_plain_len += block_plain_len

        if current_html:
            joined = "".join(current_html)
            joined_plain = html_to_plain(joined)
            if len(joined_plain) > CHUNK_MAX_PLAIN_CHARS:
                split_chunks = _length_split_chunks(
                    article_id,
                    joined,
                    current_heading,
                    start_index=chunk_index,
                )
                chunks.extend(split_chunks)
                chunk_index += len(split_chunks)
            else:
                chunk_index += 1
                chunks.append(
                    DictionaryChunk(
                        chunk_id=f"{article_id}-c{chunk_index:03d}",
                        chunk_index=chunk_index,
                        heading=current_heading,
                        content_html=joined,
                        content_plain=joined_plain,
                    )
                )

    if not chunks:
        chunk_index = 1
        chunks.append(
            DictionaryChunk(
                chunk_id=f"{article_id}-c001",
                chunk_index=1,
                heading=None,
                content_html=content_html.strip(),
                content_plain=html_to_plain(content_html),
            )
        )
    return chunks


def _length_split_chunks(
    article_id: str,
    content_html: str,
    heading: str | None,
    *,
    start_index: int,
) -> list[DictionaryChunk]:
    plain = html_to_plain(content_html)
    chunks: list[DictionaryChunk] = []
    cursor = 0
    chunk_index = start_index
    while cursor < len(plain):
        chunk_index += 1
        piece = plain[cursor : cursor + CHUNK_MAX_PLAIN_CHARS]
        cursor += CHUNK_MAX_PLAIN_CHARS
        chunks.append(
            DictionaryChunk(
                chunk_id=f"{article_id}-c{chunk_index:03d}",
                chunk_index=chunk_index,
                heading=heading,
                content_html=f"<p>{html.escape(piece)}</p>",
                content_plain=piece,
            )
        )
    return chunks


def html_to_plain(content_html: str) -> str:
    text = _TAG_RE.sub(" ", content_html)
    text = html.unescape(text)
    return " ".join(text.split())


def load_pilot_bundle(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_OUTPUT_PATH
    if not target.is_file():
        raise FileNotFoundError(f"Aquifer dictionary pilot bundle missing: {target}")
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Aquifer dictionary pilot bundle root must be an object.")
    return raw


def _hash_entries(entries: list[DictionaryRecord]) -> str:
    payload = json.dumps([entry.to_dict() for entry in entries], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    upstream = None
    output = None
    pilot_id = JOHN_4_PILOT.id
    i = 0
    while i < len(args):
        if args[i] == "--upstream" and i + 1 < len(args):
            upstream = args[i + 1]
            i += 2
            continue
        if args[i] == "--output" and i + 1 < len(args):
            output = args[i + 1]
            i += 2
            continue
        if args[i] == "--pilot" and i + 1 < len(args):
            pilot_id = args[i + 1]
            i += 2
            continue
        i += 1

    result = import_dictionary_pilot(
        pilot_id=pilot_id,
        upstream_root=upstream,
        output_path=output,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
