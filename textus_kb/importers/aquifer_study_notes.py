"""Reproducible pilot importer for Aquifer Open Study Notes."""

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

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.paths import PROJECT_ROOT
from textus_kb.pilot_registry import (
    JOHN_4_PILOT,
    PilotPassage,
    book_id_from_usfm,
    get_pilot,
    index_reference_overlaps_pilot,
    references_overlap,
)

AQUIFER_SOURCE_ID = "aquifer_open_study_notes"
AQUIFER_LICENSE = "CC-BY-SA-4.0"
AQUIFER_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
AQUIFER_ATTRIBUTION = (
    "Aquifer Open Study Notes © 2026 Mission Mutual, adapted from Tyndale Open Study Notes "
    "© 2023 Tyndale House Publishers. Licensed under CC BY-SA 4.0."
)
AQUIFER_UPSTREAM_REPO = "https://github.com/BibleAquifer/AquiferOpenStudyNotes"
DEFAULT_UPSTREAM_PATH = PROJECT_ROOT / "_upstream_audit" / "AquiferOpenStudyNotes"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "kb" / "aquifer" / "john_4_1_42_study_notes.json"
UPSTREAM_ENV_VAR = "TEXTUS_AQUIFER_UPSTREAM_PATH"

# Backward-compatible aliases for Phase 3A callers/tests.
JOHN_BOOK_NUM = JOHN_4_PILOT.usfm_book_num
JOHN_4_INDEX_LO = JOHN_4_PILOT.org_index_lo
JOHN_4_INDEX_HI = JOHN_4_PILOT.org_index_hi
PILOT_CANONICAL = JOHN_4_PILOT.canonical
CHUNK_MAX_PLAIN_CHARS = 900

_BLOCK_SPLIT_RE = re.compile(r"(?=</p>|</li>)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ImportIssue:
    level: str  # warning | error
    message: str
    article_id: str | None = None


@dataclass
class StudyNoteChunk:
    chunk_id: str
    chunk_index: int
    content_html: str
    content_plain: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StudyNoteRecord:
    article_id: str
    content_id: str
    reference_id: int | None
    title: str
    index_reference: str
    canonical_reference: str
    upstream_reference_usfm: str | None
    language: str
    content_html: str
    chunks: list[StudyNoteChunk] = field(default_factory=list)
    source_id: str = AQUIFER_SOURCE_ID
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
            "canonical_reference": self.canonical_reference,
            "upstream_reference_usfm": self.upstream_reference_usfm,
            "language": self.language,
            "content_html": self.content_html,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "source_id": self.source_id,
            "license": self.license,
            "license_url": self.license_url,
            "attribution": self.attribution,
        }


@dataclass
class PilotImportResult:
    output_path: Path
    note_count: int
    chunk_count: int
    issues: list[ImportIssue]
    upstream_commit: str
    upstream_resource_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "note_count": self.note_count,
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
    """Import John 4:1-42 Aquifer study notes into a normalized pilot JSON bundle."""
    return import_study_notes_pilot(
        pilot_id=JOHN_4_PILOT.id,
        upstream_root=upstream_root,
        output_path=output_path,
        language=language,
    )


def import_study_notes_pilot(
    *,
    pilot_id: str,
    upstream_root: str | Path | None = None,
    output_path: str | Path | None = None,
    language: str = "eng",
) -> PilotImportResult:
    """Import Aquifer study notes for a registered pilot passage."""
    pilot = get_pilot(pilot_id)
    root = resolve_upstream_path(upstream_root)
    out = Path(output_path) if output_path is not None else pilot.study_notes_resolved
    out.parent.mkdir(parents=True, exist_ok=True)

    metadata_path = root / language / "metadata.json"
    content_path = root / language / "json" / pilot.aquifer_study_notes_content_file
    issues: list[ImportIssue] = []

    if not metadata_path.is_file():
        raise FileNotFoundError(f"Aquifer metadata missing: {metadata_path}")
    if not content_path.is_file():
        raise FileNotFoundError(f"Aquifer content missing: {content_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    resource_version = str(
        metadata.get("resource_metadata", {}).get("version", "unknown")
    )
    upstream_commit = read_upstream_commit(root)
    articles = json.loads(content_path.read_text(encoding="utf-8"))

    notes: list[StudyNoteRecord] = []
    chunk_total = 0
    for article in articles:
        if not _article_overlaps_pilot(article, pilot):
            continue
        try:
            record, article_issues = _normalize_article(article, pilot)
        except CanonicalReferenceError as exc:
            issues.append(
                ImportIssue(
                    "error",
                    f"Canonical mapping failed: {exc}",
                    article_id=str(article.get("content_id")),
                )
            )
            continue
        issues.extend(article_issues)
        if record is None:
            continue
        notes.append(record)
        chunk_total += len(record.chunks)

    notes.sort(key=lambda item: (item.index_reference, item.article_id))

    bundle = {
        "bundle_version": "1",
        "pilot_id": pilot.id,
        "pilot_scope": pilot.canonical,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_id": AQUIFER_SOURCE_ID,
        "upstream_repository": AQUIFER_UPSTREAM_REPO,
        "upstream_commit": upstream_commit,
        "upstream_resource_version": resource_version,
        "language": language,
        "license": AQUIFER_LICENSE,
        "license_url": AQUIFER_LICENSE_URL,
        "attribution": AQUIFER_ATTRIBUTION,
        "content_hash": _hash_notes(notes),
        "import_issues": [asdict(issue) for issue in issues],
        "notes": [note.to_dict() for note in notes],
    }
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return PilotImportResult(
        output_path=out,
        note_count=len(notes),
        chunk_count=chunk_total,
        issues=issues,
        upstream_commit=upstream_commit,
        upstream_resource_version=resource_version,
    )


def _article_overlaps_pilot(article: dict[str, Any], pilot: PilotPassage) -> bool:
    for passage in article.get("associations", {}).get("passage", []):
        start_ref = str(passage.get("start_ref") or "")
        end_ref = str(passage.get("end_ref") or start_ref)
        if not start_ref.isdigit() or not end_ref.isdigit():
            continue
        if index_reference_overlaps_pilot(int(start_ref), int(end_ref), pilot):
            return True
    return False


def _article_overlaps_john_4_pilot(article: dict[str, Any]) -> bool:
    return _article_overlaps_pilot(article, JOHN_4_PILOT)


def _normalize_article(
    article: dict[str, Any],
    pilot: PilotPassage,
) -> tuple[StudyNoteRecord | None, list[ImportIssue]]:
    issues: list[ImportIssue] = []
    article_id = str(article.get("content_id") or "").strip()
    title = str(article.get("title") or "").strip()
    index_reference = str(article.get("index_reference") or "").strip()
    content_html = str(article.get("content") or "")
    if not article_id or not index_reference or not content_html:
        issues.append(
            ImportIssue(
                "warning",
                "Skipping article with missing id/reference/content.",
                article_id=article_id or None,
            )
        )
        return None, issues

    canonical = index_reference_to_canonical(index_reference)
    parsed = CanonicalReference.parse(canonical)
    pilot_ref = pilot.reference()
    if parsed.book_id != pilot_ref.book_id:
        issues.append(
            ImportIssue(
                "error",
                f"Article {article_id} mapped outside {pilot.canonical}: {canonical}",
                article_id=article_id,
            )
        )
        return None, issues

    if not references_overlap(parsed, pilot_ref):
        issues.append(
            ImportIssue(
                "warning",
                f"Article {article_id} canonical {canonical} outside pilot span.",
                article_id=article_id,
            )
        )
        return None, issues

    upstream_usfm = _first_passage_usfm(article)
    chunks = _chunk_html_content(article_id, content_html)
    record = StudyNoteRecord(
        article_id=article_id,
        content_id=article_id,
        reference_id=_safe_int(article.get("reference_id")),
        title=title,
        index_reference=index_reference,
        canonical_reference=canonical,
        upstream_reference_usfm=upstream_usfm,
        language=str(article.get("language") or "eng"),
        content_html=content_html,
        chunks=chunks,
    )
    return record, issues


def index_reference_to_canonical(index_reference: str) -> str:
    """Map Aquifer index_reference (BBCCCVVV) to Textus canonical form."""
    parts = index_reference.split("-")
    start = parts[0]
    if len(start) != 8 or not start.isdigit():
        raise CanonicalReferenceError(f"Invalid index_reference: {index_reference!r}")
    book_num = int(start[:2])
    book_id = book_id_from_usfm(book_num)
    if book_id is None:
        raise CanonicalReferenceError(f"Unsupported book number: {book_num}")
    chapter = int(start[2:5])
    verse_start = int(start[5:8])
    if len(parts) == 1:
        return f"{book_id}.{chapter}.{verse_start}"
    end = parts[1]
    if len(end) != 8 or not end.isdigit():
        raise CanonicalReferenceError(f"Invalid index_reference end: {index_reference!r}")
    verse_end = int(end[5:8])
    end_chapter = int(end[2:5])
    if end_chapter != chapter:
        raise CanonicalReferenceError(f"Cross-chapter index_reference unsupported: {index_reference!r}")
    if verse_start == verse_end:
        return f"{book_id}.{chapter}.{verse_start}"
    return f"{book_id}.{chapter}.{verse_start}-{verse_end}"


def _canonical_overlaps_pilot(reference: CanonicalReference) -> bool:
    return references_overlap(reference, JOHN_4_PILOT.reference())


def _first_passage_usfm(article: dict[str, Any]) -> str | None:
    passages = article.get("associations", {}).get("passage", [])
    if not passages:
        return None
    value = passages[0].get("start_ref_usfm")
    return str(value) if value else None


def _chunk_html_content(article_id: str, content_html: str) -> list[StudyNoteChunk]:
    plain = html_to_plain(content_html)
    if len(plain) <= CHUNK_MAX_PLAIN_CHARS:
        return [
            StudyNoteChunk(
                chunk_id=f"{article_id}-c001",
                chunk_index=1,
                content_html=content_html.strip(),
                content_plain=plain,
            )
        ]

    blocks = [block.strip() for block in _BLOCK_SPLIT_RE.split(content_html) if block.strip()]
    if not blocks:
        blocks = [content_html]

    chunks: list[StudyNoteChunk] = []
    current_html: list[str] = []
    current_plain_len = 0
    chunk_index = 0

    for block in blocks:
        block_plain_len = len(html_to_plain(block))
        if current_html and current_plain_len + block_plain_len > CHUNK_MAX_PLAIN_CHARS:
            chunk_index += 1
            joined = "".join(current_html)
            chunks.append(
                StudyNoteChunk(
                    chunk_id=f"{article_id}-c{chunk_index:03d}",
                    chunk_index=chunk_index,
                    content_html=joined,
                    content_plain=html_to_plain(joined),
                )
            )
            current_html = []
            current_plain_len = 0
        current_html.append(block)
        current_plain_len += block_plain_len

    if current_html:
        chunk_index += 1
        joined = "".join(current_html)
        chunks.append(
            StudyNoteChunk(
                chunk_id=f"{article_id}-c{chunk_index:03d}",
                chunk_index=chunk_index,
                content_html=joined,
                content_plain=html_to_plain(joined),
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
        raise FileNotFoundError(f"Aquifer pilot bundle missing: {target}")
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Aquifer pilot bundle root must be an object.")
    return raw


def _hash_notes(notes: list[StudyNoteRecord]) -> str:
    payload = json.dumps([note.to_dict() for note in notes], ensure_ascii=False, sort_keys=True)
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

    result = import_study_notes_pilot(
        pilot_id=pilot_id,
        upstream_root=upstream,
        output_path=output,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
