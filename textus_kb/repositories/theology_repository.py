"""Read-only Theology DB v1 SQLite repository."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.importers.theology_sqlite import (
    DEFAULT_DATABASE_PATH,
    SCHEMA_VERSION,
    TheologyImportError,
    validate_theology_database,
)
from textus_kb.pilot_registry import org_ref_bounds, references_overlap

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50
AUTHOR_DIVERSITY_CAP = 3
_FTS_FETCH_CAP = 200


@dataclass(frozen=True)
class TheologyStoreStatus:
    available: bool
    schema_version: str
    author_count: int
    work_count: int
    edition_count: int
    section_count: int
    chunk_count: int
    passage_link_count: int
    content_hash: str = ""
    import_mode: str = ""
    generated_at: str = ""
    database_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "schema_version": self.schema_version,
            "author_count": self.author_count,
            "work_count": self.work_count,
            "edition_count": self.edition_count,
            "section_count": self.section_count,
            "chunk_count": self.chunk_count,
            "passage_link_count": self.passage_link_count,
            "content_hash": self.content_hash,
            "import_mode": self.import_mode,
            "generated_at": self.generated_at,
            "database_path": self.database_path,
        }


@dataclass(frozen=True)
class TheologySearchHit:
    chunk_id: str
    heading: str
    plain_text: str
    snippet: str


@dataclass(frozen=True)
class TheologyChunkResult:
    """Provenance-ready theology chunk hit."""

    chunk_id: str
    plain_text: str
    heading: str
    section_type: str
    source_locator: str
    human_readable_locator: str
    author_name: str
    work_title: str
    tradition: str
    translator: str
    publication_year: int | None
    language: str
    rights_status: str
    license: str
    rights_note: str
    source_url: str
    corpus: str
    external_id: str
    canonical_passages: tuple[str, ...]
    snippet: str = ""
    author_id: str = ""
    work_id: str = ""


class TheologyRepository:
    """Read-only repository over the isolated theology SQLite store."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = (
            Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
        )

    @property
    def available(self) -> bool:
        return self.database_path.is_file()

    def store_status(self) -> TheologyStoreStatus:
        if not self.available:
            return self._unavailable()
        try:
            validation = validate_theology_database(self.database_path)
        except (OSError, sqlite3.Error, TheologyImportError, FileNotFoundError):
            return self._unavailable()
        if validation.schema_version != SCHEMA_VERSION:
            return self._unavailable(schema_version=validation.schema_version)
        return TheologyStoreStatus(
            available=True,
            schema_version=validation.schema_version,
            author_count=validation.author_count,
            work_count=validation.work_count,
            edition_count=validation.edition_count,
            section_count=validation.section_count,
            chunk_count=validation.chunk_count,
            passage_link_count=validation.passage_link_count,
            content_hash=validation.content_hash,
            import_mode=validation.import_mode,
            generated_at=validation.generated_at,
            database_path=str(self.database_path),
        )

    def chunks_for_passage(
        self,
        reference: CanonicalReference | str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[TheologyChunkResult]:
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
            rows = connection.execute(
                """
                SELECT
                    c.chunk_id AS chunk_id,
                    c.plain_text AS plain_text,
                    c.source_locator AS source_locator,
                    c.sequence AS chunk_sequence,
                    s.section_id AS section_id,
                    s.section_type AS section_type,
                    s.heading AS heading,
                    s.sequence AS section_sequence,
                    s.parent_section_id AS parent_section_id,
                    e.translator AS translator,
                    e.publication_year AS publication_year,
                    e.language AS language,
                    e.license AS license,
                    e.rights_status AS rights_status,
                    e.rights_note AS rights_note,
                    e.source_url AS source_url,
                    e.edition_id AS edition_id,
                    e.corpus AS corpus,
                    e.external_id AS external_id,
                    w.work_id AS work_id,
                    w.title AS work_title,
                    w.tradition AS tradition,
                    a.author_id AS author_id,
                    a.canonical_name AS author_name,
                    p.canonical_passage AS canonical_passage,
                    p.book_id AS book_id,
                    p.start_chapter AS start_chapter,
                    p.start_verse AS start_verse,
                    p.end_chapter AS end_chapter,
                    p.end_verse AS end_verse
                FROM passage_links p
                JOIN chunks c ON c.chunk_id = p.chunk_id
                JOIN sections s ON s.section_id = c.section_id
                JOIN editions e ON e.edition_id = s.edition_id
                JOIN works w ON w.work_id = e.work_id
                JOIN authors a ON a.author_id = w.author_id
                WHERE p.book_id = ?
                  AND (
                      p.end_chapter > ?
                      OR (p.end_chapter = ? AND p.end_verse >= ?)
                  )
                  AND (
                      p.start_chapter < ?
                      OR (p.start_chapter = ? AND p.start_verse <= ?)
                  )
                """,
                (
                    query_ref.book_id,
                    query_ref.start_chapter,
                    query_ref.start_chapter,
                    query_ref.start_verse,
                    query_ref.end_chapter,
                    query_ref.end_chapter,
                    query_ref.end_verse,
                ),
            ).fetchall()
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
            chunk_id = str(row["chunk_id"])
            bucket = grouped.get(chunk_id)
            if bucket is None:
                bucket = {
                    "row": row,
                    "passages": [],
                    "exact": False,
                    "min_span": None,
                }
                grouped[chunk_id] = bucket
            canonical = str(row["canonical_passage"] or stored.canonical_string())
            if canonical not in bucket["passages"]:
                bucket["passages"].append(canonical)
            span = _span_size(stored)
            if bucket["min_span"] is None or span < bucket["min_span"]:
                bucket["min_span"] = span
            if canonical == query_canonical:
                bucket["exact"] = True

        ranked: list[tuple[tuple[Any, ...], TheologyChunkResult]] = []
        for bucket in grouped.values():
            row = bucket["row"]
            result = _result_from_row(
                row,
                section_map,
                chunk_counts,
                passages=_ordered_passages(
                    bucket["passages"],
                    exact=query_canonical,
                ),
            )
            order = (
                0 if bucket["exact"] else 1,
                int(bucket["min_span"] if bucket["min_span"] is not None else 10**9),
                *_document_order_key(section_map, row),
            )
            ranked.append((order, result))
        ranked.sort(key=lambda item: item[0])
        return _apply_author_diversity(ranked, limit=capped)

    def search_text(
        self,
        query: str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[TheologyChunkResult]:
        q = (query or "").strip()
        capped = _clamp_limit(limit)
        if not q or capped == 0:
            return []
        connection = self._connect_ready()
        if connection is None:
            return []
        match_query = _fts_phrase_query(q)
        try:
            section_map = _load_section_map(connection)
            chunk_counts = _load_section_chunk_counts(connection)
            rows = _fts_match_rows(connection, match_query)
            if not rows:
                return []
            chunk_ids = [str(row["chunk_id"]) for row in rows]
            links_by_chunk = _passage_links_for_chunks(connection, chunk_ids)
        except sqlite3.Error:
            return []
        finally:
            connection.close()

        ranked: list[tuple[tuple[Any, ...], TheologyChunkResult]] = []
        for row in rows:
            chunk_id = str(row["chunk_id"])
            result = _result_from_row(
                row,
                section_map,
                chunk_counts,
                passages=tuple(links_by_chunk.get(chunk_id, ())),
                snippet=str(row["snippet"] or ""),
            )
            rank = float(row["fts_rank"] if row["fts_rank"] is not None else 0.0)
            order = (rank, *_document_order_key(section_map, row))
            ranked.append((order, result))
        ranked.sort(key=lambda item: item[0])
        return [item[1] for item in ranked[:capped]]

    def search_plain_text(
        self,
        query: str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[TheologySearchHit]:
        """Minimal FTS helper for isolated store tests. Not a retrieval API."""
        hits = self.search_text(query, limit=limit)
        return [
            TheologySearchHit(
                chunk_id=hit.chunk_id,
                heading=hit.heading,
                plain_text=hit.plain_text,
                snippet=hit.snippet or hit.plain_text,
            )
            for hit in hits
        ]

    def _unavailable(self, *, schema_version: str = "") -> TheologyStoreStatus:
        return TheologyStoreStatus(
            available=False,
            schema_version=schema_version,
            author_count=0,
            work_count=0,
            edition_count=0,
            section_count=0,
            chunk_count=0,
            passage_link_count=0,
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


def _fts_phrase_query(query: str) -> str:
    escaped = query.replace('"', '""')
    return f'"{escaped}"'


def _fts_match_rows(connection: sqlite3.Connection, match_query: str) -> list[sqlite3.Row]:
    sql = """
        SELECT
            c.chunk_id AS chunk_id,
            c.plain_text AS plain_text,
            c.source_locator AS source_locator,
            c.sequence AS chunk_sequence,
            s.section_id AS section_id,
            s.section_type AS section_type,
            s.heading AS heading,
            s.sequence AS section_sequence,
            s.parent_section_id AS parent_section_id,
            e.translator AS translator,
            e.publication_year AS publication_year,
            e.language AS language,
            e.license AS license,
            e.rights_status AS rights_status,
            e.rights_note AS rights_note,
            e.source_url AS source_url,
            e.edition_id AS edition_id,
            e.corpus AS corpus,
            e.external_id AS external_id,
            w.work_id AS work_id,
            w.title AS work_title,
            w.tradition AS tradition,
            a.author_id AS author_id,
            a.canonical_name AS author_name,
            snippet(chunks_fts, 2, '**', '**', '…', 32) AS snippet,
            bm25(chunks_fts) AS fts_rank
        FROM chunks_fts
        JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
        JOIN sections s ON s.section_id = c.section_id
        JOIN editions e ON e.edition_id = s.edition_id
        JOIN works w ON w.work_id = e.work_id
        JOIN authors a ON a.author_id = w.author_id
        WHERE chunks_fts MATCH ?
        LIMIT ?
        """
    try:
        return list(connection.execute(sql, (match_query, _FTS_FETCH_CAP)).fetchall())
    except sqlite3.Error:
        fallback = sql.replace("bm25(chunks_fts) AS fts_rank", "0 AS fts_rank")
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


def _passage_links_for_chunks(
    connection: sqlite3.Connection,
    chunk_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = connection.execute(
        f"""
        SELECT chunk_id, canonical_passage
        FROM passage_links
        WHERE chunk_id IN ({placeholders})
        ORDER BY canonical_passage
        """,
        tuple(chunk_ids),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        chunk_id = str(row["chunk_id"])
        passage = str(row["canonical_passage"] or "")
        if not passage:
            continue
        bucket = grouped.setdefault(chunk_id, [])
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


def _ordered_passages(passages: list[str], *, exact: str) -> tuple[str, ...]:
    unique = list(dict.fromkeys(passages))
    unique.sort(key=lambda item: (0 if item == exact else 1, item))
    return tuple(unique)


def _section_chain(
    section_map: dict[str, sqlite3.Row],
    section_id: str,
) -> list[sqlite3.Row]:
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
    book_seq = 0
    chapter_seq = 0
    section_seq = int(row["section_sequence"] or 0)
    for node in chain:
        kind = str(node["section_type"] or "")
        sequence = int(node["sequence"] or 0)
        if kind == "book":
            book_seq = sequence
        elif kind == "chapter":
            chapter_seq = sequence
        elif kind == "section":
            section_seq = sequence
    return (
        str(row["author_id"] or ""),
        str(row["work_id"] or ""),
        str(row["edition_id"] or ""),
        book_seq,
        chapter_seq,
        section_seq,
        int(row["chunk_sequence"] or 0),
        str(row["chunk_id"]),
    )


def _apply_author_diversity(
    ranked: list[tuple[tuple[Any, ...], TheologyChunkResult]],
    *,
    limit: int,
    cap: int = AUTHOR_DIVERSITY_CAP,
) -> list[TheologyChunkResult]:
    """Prefer at most `cap` hits per author_id, without promoting a worse relevance tier.

    Walk each (exact, min_span) tier in already-ranked order. Within a tier, take
    hits while the author is under the cap; leftover slots in that tier are then
    filled from the same tier in original relevance order so a single-author
    corpus is unchanged and a missing second author does not drop information.
    """
    if limit <= 0 or not ranked:
        return []
    tiers: list[list[tuple[tuple[Any, ...], TheologyChunkResult]]] = []
    for item in ranked:
        tier_key = item[0][:2]
        if not tiers or tiers[-1][0][0][:2] != tier_key:
            tiers.append([item])
        else:
            tiers[-1].append(item)

    selected: list[TheologyChunkResult] = []
    counts: dict[str, int] = {}
    remaining = limit
    for tier in tiers:
        if remaining <= 0:
            break
        deferred: list[TheologyChunkResult] = []
        for _order, result in tier:
            if remaining <= 0:
                deferred.append(result)
                continue
            author_id = str(result.author_id or "")
            if counts.get(author_id, 0) >= cap:
                deferred.append(result)
                continue
            selected.append(result)
            counts[author_id] = counts.get(author_id, 0) + 1
            remaining -= 1
        for result in deferred:
            if remaining <= 0:
                break
            selected.append(result)
            author_id = str(result.author_id or "")
            counts[author_id] = counts.get(author_id, 0) + 1
            remaining -= 1
    return selected


def _to_roman(number: int) -> str:
    if number <= 0:
        return str(number)
    numerals = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    remaining = number
    parts: list[str] = []
    for value, glyph in numerals:
        while remaining >= value:
            parts.append(glyph)
            remaining -= value
    return "".join(parts)


def _hierarchy_label(node: sqlite3.Row) -> str:
    kind = str(node["section_type"] or "").strip().casefold()
    sequence = int(node["sequence"] or 0)
    heading = str(node["heading"] or "").strip()
    if kind == "book":
        named = re.search(
            r"\bBOOK\s+(FIRST|SECOND|THIRD|FOURTH|FIFTH|[IVXLCDM]+|\d+)",
            heading,
            flags=re.IGNORECASE,
        )
        if named:
            token = named.group(1)
            words = {
                "FIRST": "I",
                "SECOND": "II",
                "THIRD": "III",
                "FOURTH": "IV",
                "FIFTH": "V",
            }
            numeral = words.get(token.upper())
            if numeral is None:
                numeral = _to_roman(int(token)) if token.isdigit() else token.upper()
            return f"Book {numeral}"
        return f"Book {_to_roman(sequence)}"
    if kind == "chapter":
        if re.match(r"ARGUMENT\b", heading, flags=re.IGNORECASE):
            return "Argument"
        numbered = re.search(r"\bCHAPTER\s+(\d+)", heading, flags=re.IGNORECASE)
        if numbered:
            return f"Chapter {int(numbered.group(1))}"
        return f"Chapter {sequence}"
    if kind == "section":
        numbered = re.match(r"^(\d+)\.", heading)
        if numbered:
            return f"Section {int(numbered.group(1))}"
        return f"Section {sequence}"
    return heading or str(node["section_type"] or "").strip()


def _human_readable_locator(
    author_name: str,
    work_title: str,
    chain: list[sqlite3.Row],
    *,
    chunk_sequence: int = 1,
    section_chunk_count: int = 1,
) -> str:
    parts = [author_name.strip(), work_title.strip()]
    parts.extend(_hierarchy_label(node) for node in chain)
    locator = ", ".join(part for part in parts if part)
    if section_chunk_count > 1:
        locator = f"{locator}, fragment {int(chunk_sequence)}"
    return locator


def _result_from_row(
    row: sqlite3.Row,
    section_map: dict[str, sqlite3.Row],
    chunk_counts: dict[str, int],
    *,
    passages: tuple[str, ...],
    snippet: str = "",
) -> TheologyChunkResult:
    chain = _section_chain(section_map, str(row["section_id"]))
    author = str(row["author_name"] or "")
    title = str(row["work_title"] or "")
    year = row["publication_year"]
    try:
        publication_year = int(year) if year is not None and year != "" else None
    except (TypeError, ValueError):
        publication_year = None
    section_id = str(row["section_id"])
    return TheologyChunkResult(
        chunk_id=str(row["chunk_id"]),
        plain_text=str(row["plain_text"] or ""),
        heading=str(row["heading"] or ""),
        section_type=str(row["section_type"] or ""),
        source_locator=str(row["source_locator"] or ""),
        human_readable_locator=_human_readable_locator(
            author,
            title,
            chain,
            chunk_sequence=int(row["chunk_sequence"] or 1),
            section_chunk_count=int(chunk_counts.get(section_id) or 1),
        ),
        author_name=author,
        work_title=title,
        tradition=str(row["tradition"] or ""),
        translator=str(row["translator"] or ""),
        publication_year=publication_year,
        language=str(row["language"] or ""),
        rights_status=str(row["rights_status"] or ""),
        license=str(row["license"] or ""),
        rights_note=str(row["rights_note"] or ""),
        source_url=str(row["source_url"] or ""),
        corpus=str(row["corpus"] or ""),
        external_id=str(row["external_id"] or ""),
        canonical_passages=passages,
        snippet=snippet,
        author_id=str(row["author_id"] or ""),
        work_id=str(row["work_id"] or ""),
    )
