"""Read-only Commentary DB v1 SQLite repository.

Section-first, fail-closed. Passage retrieval is exact/range-overlap only;
it never falls back to full-text or semantic search. ``search_text`` is a
separate, explicitly-invoked secondary channel.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    SCHEMA_VERSION,
    CommentaryImportError,
    validate_commentary_database,
)
from textus_kb.pilot_registry import org_ref_bounds, references_overlap

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50

RELATION_EXACT_PASSAGE = "exact_passage"
RELATION_CONTAINING_SECTION = "containing_section"
RELATION_PARTIAL_OVERLAP = "partial_overlap"
RELATION_BROADER_CONTEXT = "broader_context"
RELATION_FTS_MATCH = "fts_match"

_TIER_RANK = {
    RELATION_EXACT_PASSAGE: 0,
    RELATION_CONTAINING_SECTION: 1,
    RELATION_PARTIAL_OVERLAP: 2,
}

# Passage-link-level relation (stored explicitly on section_passage_links,
# schema v2+) — distinct from the query-relative RELATION_* constants above.
# Used only as a ranking tie-break: when two sections tie on tier and span,
# the one whose deciding link is "primary" ranks first.
PASSAGE_RELATION_PRIMARY = "primary"
PASSAGE_RELATION_PARALLEL = "parallel"

_PASSAGE_RELATION_RANK = {
    PASSAGE_RELATION_PRIMARY: 0,
    PASSAGE_RELATION_PARALLEL: 1,
}

_CONTRIBUTOR_ROLE_ORDER = {
    "author": 0,
    "translator": 1,
    "editor": 2,
    "annotator": 3,
    "compiler": 4,
}

_FTS_FETCH_CAP = 200


@dataclass(frozen=True)
class CommentaryStoreStatus:
    available: bool
    schema_version: str
    contributor_count: int
    work_count: int
    work_contributor_count: int
    edition_count: int
    source_file_count: int
    import_batch_count: int
    section_count: int
    passage_link_count: int
    chunk_count: int
    content_hash: str = ""
    import_mode: str = ""
    generated_at: str = ""
    database_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "schema_version": self.schema_version,
            "contributor_count": self.contributor_count,
            "work_count": self.work_count,
            "work_contributor_count": self.work_contributor_count,
            "edition_count": self.edition_count,
            "source_file_count": self.source_file_count,
            "import_batch_count": self.import_batch_count,
            "section_count": self.section_count,
            "passage_link_count": self.passage_link_count,
            "chunk_count": self.chunk_count,
            "content_hash": self.content_hash,
            "import_mode": self.import_mode,
            "generated_at": self.generated_at,
            "database_path": self.database_path,
        }


@dataclass(frozen=True)
class CommentaryChunkResult:
    chunk_id: str
    section_id: str
    sequence: int
    plain_text: str
    char_count: int
    source_locator: str


@dataclass(frozen=True)
class CommentarySectionResult:
    """A section hit, always carrying an explicit relation_type (never just a score)."""

    section_id: str
    edition_id: str
    work_id: str
    work_title: str
    section_type: str
    heading: str
    sequence: int
    parent_section_id: str | None
    relation_type: str
    canonical_passages: tuple[str, ...]
    chunk_count: int
    primary_passages: tuple[str, ...] = ()
    parallel_passages: tuple[str, ...] = ()
    contributors: tuple[str, ...] = ()
    language: str = ""
    rights_status: str = ""
    license: str = ""
    rights_note: str = ""
    source_url: str = ""
    corpus: str = ""
    external_id: str = ""


@dataclass(frozen=True)
class CommentarySectionDetail:
    section_id: str
    edition_id: str
    work_id: str
    work_title: str
    section_type: str
    heading: str
    sequence: int
    parent_section_id: str | None
    canonical_passages: tuple[str, ...]
    contributors: tuple[str, ...]
    parent_chain: tuple[tuple[str, str], ...]  # (section_id, heading) root-first
    primary_passages: tuple[str, ...] = ()
    parallel_passages: tuple[str, ...] = ()
    chunks: tuple[CommentaryChunkResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommentarySearchHit:
    section_id: str
    heading: str
    snippet: str
    canonical_passages: tuple[str, ...]
    relation_type: str = RELATION_FTS_MATCH


class CommentaryRepository:
    """Read-only repository over the isolated commentary SQLite store."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = (
            Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
        )

    @property
    def available(self) -> bool:
        return self.database_path.is_file()

    def store_status(self) -> CommentaryStoreStatus:
        if not self.available:
            return self._unavailable()
        try:
            validation = validate_commentary_database(self.database_path)
        except (OSError, sqlite3.Error, CommentaryImportError, FileNotFoundError):
            return self._unavailable()
        if validation.schema_version != SCHEMA_VERSION:
            return self._unavailable(schema_version=validation.schema_version)
        return CommentaryStoreStatus(
            available=True,
            schema_version=validation.schema_version,
            contributor_count=validation.contributor_count,
            work_count=validation.work_count,
            work_contributor_count=validation.work_contributor_count,
            edition_count=validation.edition_count,
            source_file_count=validation.source_file_count,
            import_batch_count=validation.import_batch_count,
            section_count=validation.section_count,
            passage_link_count=validation.passage_link_count,
            chunk_count=validation.chunk_count,
            content_hash=validation.content_hash,
            import_mode=validation.import_mode,
            generated_at=validation.generated_at,
            database_path=str(self.database_path),
        )

    def sections_for_passage(
        self,
        reference: CanonicalReference | str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
        work_id: str | None = None,
    ) -> list[CommentarySectionResult]:
        """Exact + range-overlap section hits. Never falls back to FTS/semantic search."""
        query_ref = _parse_reference(reference)
        capped = _clamp_limit(limit)
        if query_ref is None or capped == 0:
            return []
        connection = self._connect_ready()
        if connection is None:
            return []
        try:
            section_map = _load_section_map(connection)
            chunk_counts = _load_section_chunk_counts(connection)
            contributors_by_work = _load_contributors_by_work(connection)
            sql = _SECTIONS_BY_BOOK_SQL
            params: list[Any] = [
                query_ref.book_id,
                query_ref.start_chapter,
                query_ref.start_chapter,
                query_ref.start_verse,
                query_ref.end_chapter,
                query_ref.end_chapter,
                query_ref.end_verse,
            ]
            if work_id:
                sql += " AND w.work_id = ?"
                params.append(work_id)
            rows = connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error:
            return []
        finally:
            connection.close()

        grouped: dict[str, dict[str, Any]] = {}
        query_canonical = query_ref.canonical_string()
        for row in rows:
            stored = _reference_from_link_row(row)
            if stored is None or not references_overlap(query_ref, stored):
                continue
            section_id = str(row["section_id"])
            bucket = grouped.setdefault(
                section_id,
                {
                    "row": row,
                    "primary_passages": [],
                    "parallel_passages": [],
                    "tier": None,
                    "span": None,
                    "relation_rank": None,
                },
            )
            canonical = str(row["canonical_passage"] or stored.canonical_string())
            link_relation = str(row["relation_type"] or PASSAGE_RELATION_PRIMARY)
            target_list = (
                bucket["primary_passages"]
                if link_relation == PASSAGE_RELATION_PRIMARY
                else bucket["parallel_passages"]
            )
            if canonical not in target_list:
                target_list.append(canonical)
            tier = _classify_tier(query_ref, stored, canonical, query_canonical)
            span = _span_size(stored)
            relation_rank = _PASSAGE_RELATION_RANK.get(link_relation, 1)
            # Same-tier, same-span ties are broken in favor of a "primary"
            # deciding link over a "parallel" one — never insertion order.
            if bucket["tier"] is None or (
                _TIER_RANK[tier],
                span,
                relation_rank,
            ) < (
                _TIER_RANK[bucket["tier"]],
                bucket["span"],
                bucket["relation_rank"],
            ):
                bucket["tier"] = tier
                bucket["span"] = span
                bucket["relation_rank"] = relation_rank

        ranked: list[tuple[tuple[Any, ...], CommentarySectionResult]] = []
        for section_id, bucket in grouped.items():
            row = bucket["row"]
            result = _result_from_row(
                row,
                relation_type=bucket["tier"],
                primary_passages=_ordered_passages(
                    bucket["primary_passages"], exact=query_canonical
                ),
                parallel_passages=_ordered_passages(
                    bucket["parallel_passages"], exact=query_canonical
                ),
                chunk_counts=chunk_counts,
                contributors_by_work=contributors_by_work,
            )
            order = (
                _TIER_RANK[bucket["tier"]],
                int(bucket["span"]),
                int(bucket["relation_rank"]),
                *_document_order_key(section_map, row),
            )
            ranked.append((order, result))
        ranked.sort(key=lambda item: item[0])
        return [item[1] for item in ranked[:capped]]

    def section_detail(self, section_id: str) -> CommentarySectionDetail | None:
        connection = self._connect_ready()
        if connection is None:
            return None
        try:
            row = connection.execute(_SECTION_DETAIL_SQL, (section_id,)).fetchone()
            if row is None:
                return None
            section_map = _load_section_map(connection)
            contributors_by_work = _load_contributors_by_work(connection)
            passage_rows = connection.execute(
                """
                SELECT canonical_passage, relation_type FROM section_passage_links
                WHERE section_id = ?
                ORDER BY start_chapter, start_verse, canonical_passage
                """,
                (section_id,),
            ).fetchall()
            chunk_rows = connection.execute(
                """
                SELECT chunk_id, section_id, sequence, plain_text, char_count, source_locator
                FROM chunks
                WHERE section_id = ?
                ORDER BY sequence
                """,
                (section_id,),
            ).fetchall()
        except sqlite3.Error:
            return None
        finally:
            connection.close()

        chain = _section_chain(section_map, section_id)
        parent_chain = tuple(
            (str(node["section_id"]), str(node["heading"] or ""))
            for node in chain[:-1]
        )
        contributors = contributors_by_work.get(str(row["work_id"]), ())
        primary_passages = tuple(
            str(r["canonical_passage"]) for r in passage_rows
            if str(r["relation_type"] or PASSAGE_RELATION_PRIMARY) == PASSAGE_RELATION_PRIMARY
        )
        parallel_passages = tuple(
            str(r["canonical_passage"]) for r in passage_rows
            if str(r["relation_type"] or PASSAGE_RELATION_PRIMARY) == PASSAGE_RELATION_PARALLEL
        )
        return CommentarySectionDetail(
            section_id=str(row["section_id"]),
            edition_id=str(row["edition_id"]),
            work_id=str(row["work_id"]),
            work_title=str(row["work_title"] or ""),
            section_type=str(row["section_type"] or ""),
            heading=str(row["heading"] or ""),
            sequence=int(row["sequence"] or 0),
            parent_section_id=(
                str(row["parent_section_id"]) if row["parent_section_id"] else None
            ),
            canonical_passages=tuple(str(r["canonical_passage"]) for r in passage_rows),
            primary_passages=primary_passages,
            parallel_passages=parallel_passages,
            contributors=contributors,
            parent_chain=parent_chain,
            chunks=tuple(
                CommentaryChunkResult(
                    chunk_id=str(r["chunk_id"]),
                    section_id=str(r["section_id"]),
                    sequence=int(r["sequence"] or 0),
                    plain_text=str(r["plain_text"] or ""),
                    char_count=int(r["char_count"] or 0),
                    source_locator=str(r["source_locator"] or ""),
                )
                for r in chunk_rows
            ),
        )

    def chunk_previews(
        self,
        section_ids: list[str],
        *,
        max_chars: int = 240,
    ) -> dict[str, str]:
        """Cheap first-chunk preview text per section, truncated to
        ``max_chars`` (word-boundary safe, with an ellipsis).

        For compact card display without loading a section's full chunk
        sequence — callers that need the complete, ordered text should
        use ``section_detail()`` instead (explicit opt-in, e.g. on
        expand). One batched query for the whole ``section_ids`` list,
        mirroring the existing ``_load_section_chunk_counts``/
        ``_load_contributors_by_work`` batched-lookup pattern.
        """
        ids = [str(s) for s in section_ids if str(s).strip()]
        if not ids:
            return {}
        connection = self._connect_ready()
        if connection is None:
            return {}
        try:
            placeholders = ",".join("?" for _ in ids)
            rows = connection.execute(
                f"""
                SELECT chunks.section_id AS section_id, chunks.plain_text AS plain_text
                FROM chunks
                WHERE chunks.section_id IN ({placeholders})
                  AND chunks.sequence = (
                      SELECT MIN(c2.sequence) FROM chunks AS c2
                      WHERE c2.section_id = chunks.section_id
                  )
                """,
                tuple(ids),
            ).fetchall()
        except sqlite3.Error:
            return {}
        finally:
            connection.close()
        return {
            str(row["section_id"]): _truncate_preview(str(row["plain_text"] or ""), max_chars)
            for row in rows
        }

    def broader_context(
        self,
        section_id: str,
        *,
        levels: int = 1,
    ) -> list[CommentarySectionResult]:
        """Ancestor sections above ``section_id``. Explicit opt-in only; never automatic."""
        if levels <= 0:
            return []
        connection = self._connect_ready()
        if connection is None:
            return []
        try:
            section_map = _load_section_map(connection)
            chunk_counts = _load_section_chunk_counts(connection)
            contributors_by_work = _load_contributors_by_work(connection)
            if section_id not in {str(k) for k in section_map}:
                return []
            chain = _section_chain(section_map, section_id)
            ancestors = chain[:-1][-levels:]
            if not ancestors:
                return []
            ancestor_ids = [str(node["section_id"]) for node in ancestors]
            placeholders = ",".join("?" for _ in ancestor_ids)
            rows = connection.execute(
                f"{_SECTION_BASE_SQL} WHERE s.section_id IN ({placeholders})",
                tuple(ancestor_ids),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            connection.close()

        rows_by_id = {str(row["section_id"]): row for row in rows}
        results: list[CommentarySectionResult] = []
        for ancestor_id in ancestor_ids:
            row = rows_by_id.get(ancestor_id)
            if row is None:
                continue
            results.append(
                _result_from_row(
                    row,
                    relation_type=RELATION_BROADER_CONTEXT,
                    chunk_counts=chunk_counts,
                    contributors_by_work=contributors_by_work,
                )
            )
        return results

    def search_text(
        self,
        query: str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[CommentarySearchHit]:
        """Secondary FTS channel. Not used by sections_for_passage."""
        q = (query or "").strip()
        capped = _clamp_limit(limit)
        if not q or capped == 0:
            return []
        connection = self._connect_ready()
        if connection is None:
            return []
        match_query = _fts_phrase_query(q)
        try:
            section_ids = [row[0] for row in connection.execute(
                "SELECT DISTINCT section_id FROM section_passage_links"
            ).fetchall()]
            passages_by_section = _passage_links_for_sections(connection, section_ids)
            rows = _fts_match_rows(connection, match_query)
        except sqlite3.Error:
            return []
        finally:
            connection.close()

        hits: list[tuple[float, CommentarySearchHit]] = []
        for row in rows:
            section_id = str(row["section_id"])
            hits.append(
                (
                    float(row["fts_rank"] if row["fts_rank"] is not None else 0.0),
                    CommentarySearchHit(
                        section_id=section_id,
                        heading=str(row["heading"] or ""),
                        snippet=str(row["snippet"] or ""),
                        canonical_passages=passages_by_section.get(section_id, ()),
                    ),
                )
            )
        hits.sort(key=lambda item: item[0])
        return [item[1] for item in hits[:capped]]

    def _unavailable(self, *, schema_version: str = "") -> CommentaryStoreStatus:
        return CommentaryStoreStatus(
            available=False,
            schema_version=schema_version,
            contributor_count=0,
            work_count=0,
            work_contributor_count=0,
            edition_count=0,
            source_file_count=0,
            import_batch_count=0,
            section_count=0,
            passage_link_count=0,
            chunk_count=0,
            database_path=str(self.database_path),
        )

    def _connect_ready(self) -> sqlite3.Connection | None:
        connection = self._connect()
        if connection is None:
            return None
        try:
            row = connection.execute(
                "SELECT value FROM store_metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None or str(row["value"]) != SCHEMA_VERSION:
                connection.close()
                return None
            return connection
        except sqlite3.Error:
            connection.close()
            return None

    def _connect(self) -> sqlite3.Connection | None:
        if not self.database_path.is_file():
            return None
        try:
            connection = sqlite3.connect(
                f"file:{self.database_path.as_posix()}?mode=ro",
                uri=True,
            )
            connection.row_factory = sqlite3.Row
            return connection
        except sqlite3.Error:
            return None


_SECTION_BASE_SQL = """
    SELECT
        s.section_id AS section_id,
        s.edition_id AS edition_id,
        s.parent_section_id AS parent_section_id,
        s.section_type AS section_type,
        s.heading AS heading,
        s.sequence AS sequence,
        e.language AS language,
        e.rights_status AS rights_status,
        e.license AS license,
        e.rights_note AS rights_note,
        e.source_url AS source_url,
        e.corpus AS corpus,
        e.external_id AS external_id,
        w.work_id AS work_id,
        w.title AS work_title
    FROM sections s
    JOIN editions e ON e.edition_id = s.edition_id
    JOIN works w ON w.work_id = e.work_id
"""

_SECTION_DETAIL_SQL = _SECTION_BASE_SQL + " WHERE s.section_id = ?"

_SECTIONS_BY_BOOK_SQL = (
    """
    SELECT
        s.section_id AS section_id,
        s.edition_id AS edition_id,
        s.parent_section_id AS parent_section_id,
        s.section_type AS section_type,
        s.heading AS heading,
        s.sequence AS sequence,
        e.language AS language,
        e.rights_status AS rights_status,
        e.license AS license,
        e.rights_note AS rights_note,
        e.source_url AS source_url,
        e.corpus AS corpus,
        e.external_id AS external_id,
        w.work_id AS work_id,
        w.title AS work_title,
        p.canonical_passage AS canonical_passage,
        p.book_id AS book_id,
        p.start_chapter AS start_chapter,
        p.start_verse AS start_verse,
        p.end_chapter AS end_chapter,
        p.end_verse AS end_verse,
        p.relation_type AS relation_type
    FROM section_passage_links p
    JOIN sections s ON s.section_id = p.section_id
    JOIN editions e ON e.edition_id = s.edition_id
    JOIN works w ON w.work_id = e.work_id
    WHERE p.book_id = ?
      AND (
          p.end_chapter > ?
          OR (p.end_chapter = ? AND p.end_verse >= ?)
      )
      AND (
          p.start_chapter < ?
          OR (p.start_chapter = ? AND p.start_verse <= ?)
      )
    """
)


def _parse_reference(reference: CanonicalReference | str) -> CanonicalReference | None:
    if isinstance(reference, CanonicalReference):
        return reference
    try:
        return CanonicalReference.parse(str(reference or ""))
    except CanonicalReferenceError:
        return None


def _clamp_limit(limit: int) -> int:
    try:
        number = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_SEARCH_LIMIT
    if number <= 0:
        return 0
    return min(number, MAX_SEARCH_LIMIT)


def _truncate_preview(text: str, max_chars: int) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= max_chars:
        return stripped
    cut = stripped[:max_chars]
    last_space = cut.rfind(" ")
    if last_space > max_chars * 0.6:
        cut = cut[:last_space]
    return cut.rstrip(" ,.;:") + "…"


def _fts_phrase_query(query: str) -> str:
    escaped = query.replace('"', '""')
    return f'"{escaped}"'


def _fts_match_rows(connection: sqlite3.Connection, match_query: str) -> list[sqlite3.Row]:
    sql = """
        SELECT
            section_id,
            heading,
            snippet(sections_fts, 2, '**', '**', '…', 32) AS snippet,
            bm25(sections_fts) AS fts_rank
        FROM sections_fts
        WHERE sections_fts MATCH ?
        LIMIT ?
        """
    try:
        return list(connection.execute(sql, (match_query, _FTS_FETCH_CAP)).fetchall())
    except sqlite3.Error:
        fallback = sql.replace("bm25(sections_fts) AS fts_rank", "0 AS fts_rank")
        return list(connection.execute(fallback, (match_query, _FTS_FETCH_CAP)).fetchall())


def _load_section_map(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT section_id, parent_section_id, section_type, heading, sequence
        FROM sections
        """
    ).fetchall()
    return {str(row["section_id"]): row for row in rows}


def _load_section_chunk_counts(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT section_id, COUNT(*) AS chunk_count
        FROM chunks
        GROUP BY section_id
        """
    ).fetchall()
    return {str(row["section_id"]): int(row["chunk_count"]) for row in rows}


def _load_contributors_by_work(connection: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    rows = connection.execute(
        """
        SELECT wc.work_id AS work_id, c.canonical_name AS canonical_name, wc.role AS role
        FROM work_contributors wc
        JOIN contributors c ON c.contributor_id = wc.contributor_id
        """
    ).fetchall()
    grouped: dict[str, list[tuple[int, str, str]]] = {}
    for row in rows:
        work_id = str(row["work_id"])
        role = str(row["role"] or "")
        name = str(row["canonical_name"] or "")
        rank = _CONTRIBUTOR_ROLE_ORDER.get(role, 99)
        grouped.setdefault(work_id, []).append((rank, name, role))
    result: dict[str, tuple[str, ...]] = {}
    for work_id, entries in grouped.items():
        entries.sort(key=lambda item: (item[0], item[1]))
        result[work_id] = tuple(f"{name} ({role})" for _rank, name, role in entries)
    return result


def _passage_links_for_sections(
    connection: sqlite3.Connection,
    section_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not section_ids:
        return {}
    placeholders = ",".join("?" for _ in section_ids)
    rows = connection.execute(
        f"""
        SELECT section_id, canonical_passage
        FROM section_passage_links
        WHERE section_id IN ({placeholders})
        ORDER BY start_chapter, start_verse, canonical_passage
        """,
        tuple(section_ids),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        section_id = str(row["section_id"])
        passage = str(row["canonical_passage"] or "")
        if not passage:
            continue
        bucket = grouped.setdefault(section_id, [])
        if passage not in bucket:
            bucket.append(passage)
    return {key: tuple(value) for key, value in grouped.items()}


def _reference_from_link_row(row: sqlite3.Row) -> CanonicalReference | None:
    try:
        return CanonicalReference(
            book_id=str(row["book_id"]),
            start_chapter=int(row["start_chapter"]),
            start_verse=int(row["start_verse"]),
            end_chapter=int(row["end_chapter"]),
            end_verse=int(row["end_verse"]),
        )
    except (TypeError, ValueError, CanonicalReferenceError):
        return None


def _span_size(reference: CanonicalReference) -> int:
    try:
        low, high = org_ref_bounds(reference)
        return int(high) - int(low)
    except (TypeError, ValueError):
        return (
            (reference.end_chapter - reference.start_chapter) * 1000
            + (reference.end_verse - reference.start_verse)
        )


def _contains(outer: CanonicalReference, inner: CanonicalReference) -> bool:
    """True when ``outer`` fully contains ``inner`` (same book, ordered by (chapter, verse))."""
    if outer.book_id != inner.book_id:
        return False
    outer_start = (outer.start_chapter, outer.start_verse)
    outer_end = (outer.end_chapter, outer.end_verse)
    inner_start = (inner.start_chapter, inner.start_verse)
    inner_end = (inner.end_chapter, inner.end_verse)
    return outer_start <= inner_start and outer_end >= inner_end


def _classify_tier(
    query_ref: CanonicalReference,
    stored: CanonicalReference,
    canonical: str,
    query_canonical: str,
) -> str:
    if canonical == query_canonical:
        return RELATION_EXACT_PASSAGE
    if _contains(stored, query_ref):
        return RELATION_CONTAINING_SECTION
    return RELATION_PARTIAL_OVERLAP


def _ordered_passages(passages: list[str], *, exact: str) -> tuple[str, ...]:
    unique = list(dict.fromkeys(passages))
    unique.sort(key=lambda item: (0 if item == exact else 1, item))
    return tuple(unique)


def _section_chain(
    section_map: dict[str, sqlite3.Row],
    section_id: str,
) -> list[sqlite3.Row]:
    """Root-first ancestor chain, ending with ``section_id`` itself."""
    chain: list[sqlite3.Row] = []
    seen: set[str] = set()
    current_id: str | None = section_id
    while current_id and current_id not in seen:
        seen.add(current_id)
        row = section_map.get(current_id)
        if row is None:
            break
        chain.append(row)
        parent = row["parent_section_id"]
        current_id = str(parent) if parent else None
    chain.reverse()
    return chain


def _document_order_key(section_map: dict[str, sqlite3.Row], row: sqlite3.Row) -> tuple[Any, ...]:
    chain = _section_chain(section_map, str(row["section_id"]))
    sequence_chain = tuple(int(node["sequence"] or 0) for node in chain)
    return (
        str(row["work_id"] or ""),
        str(row["edition_id"] or ""),
        sequence_chain,
        str(row["section_id"]),
    )


def _result_from_row(
    row: sqlite3.Row,
    *,
    relation_type: str,
    primary_passages: tuple[str, ...] = (),
    parallel_passages: tuple[str, ...] = (),
    chunk_counts: dict[str, int],
    contributors_by_work: dict[str, tuple[str, ...]],
) -> CommentarySectionResult:
    section_id = str(row["section_id"])
    work_id = str(row["work_id"] or "")
    # Combined view: primary passages first, then parallel — matches each
    # tuple's own (exact-match-first) ordering, not re-sorted further.
    combined = tuple(dict.fromkeys([*primary_passages, *parallel_passages]))
    return CommentarySectionResult(
        section_id=section_id,
        edition_id=str(row["edition_id"] or ""),
        work_id=work_id,
        work_title=str(row["work_title"] or ""),
        section_type=str(row["section_type"] or ""),
        heading=str(row["heading"] or ""),
        sequence=int(row["sequence"] or 0),
        parent_section_id=(
            str(row["parent_section_id"]) if row["parent_section_id"] else None
        ),
        relation_type=relation_type,
        canonical_passages=combined,
        primary_passages=primary_passages,
        parallel_passages=parallel_passages,
        chunk_count=int(chunk_counts.get(section_id) or 0),
        contributors=contributors_by_work.get(work_id, ()),
        language=str(row["language"] or ""),
        rights_status=str(row["rights_status"] or ""),
        license=str(row["license"] or ""),
        rights_note=str(row["rights_note"] or ""),
        source_url=str(row["source_url"] or ""),
        corpus=str(row["corpus"] or ""),
        external_id=str(row["external_id"] or ""),
    )
