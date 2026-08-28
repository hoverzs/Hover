"""Multi-author theology retrieval diversity and document-order tie-break tests."""

from __future__ import annotations

from pathlib import Path

from textus_kb.importers.theology_sqlite import import_theology_sqlite
from textus_kb.repositories.theology_repository import (
    AUTHOR_DIVERSITY_CAP,
    TheologyRepository,
)

QUERY = "John.3.16"
OVERLAP = "John.3.1-21"
CALVIN_TOP6 = {
    "Rom.8.3": [
        "ccel.calvin.institutes.iii.xvi-p16.chunk",
        "ccel.calvin.institutes.iv.viii-p25.chunk",
        "ccel.calvin.institutes.iv.xiii-p15.chunk",
        "ccel.calvin.institutes.iv.xiv-p8.chunk",
        "ccel.calvin.institutes.iv.xiv-p13.chunk",
        "ccel.calvin.institutes.iv.xvii-p29.chunk",
    ],
    "John.3.16": [
        "ccel.calvin.institutes.iv.xiii-p15.chunk",
        "ccel.calvin.institutes.iv.xvii-p27.chunk",
        "ccel.calvin.institutes.iv.xviii-p12.chunk",
        "ccel.calvin.institutes.v.xv-p47.chunk",
        "ccel.calvin.institutes.v.xxv-p27.chunk",
        "ccel.calvin.institutes.v.xxv-p30.chunk",
    ],
    "Ezek.18.20": [
        "ccel.calvin.institutes.iv.ix-p68.chunk",
        "ccel.calvin.institutes.iv.ix-p111.chunk",
        "ccel.calvin.institutes.iv.ix-p112.chunk",
        "ccel.calvin.institutes.iv.ix-p194.chunk",
        "ccel.calvin.institutes.v.v-p105.chunk",
    ],
}


def _section(section_id: str, *, parent: str | None, section_type: str, heading: str, sequence: int, edition_id: str) -> dict:
    return {
        "section_id": section_id,
        "edition_id": edition_id,
        "parent_section_id": parent,
        "section_type": section_type,
        "heading": heading,
        "sequence": sequence,
    }


def _chunk(chunk_id: str, section_id: str, links: list[str], *, sequence: int = 1) -> dict:
    return {
        "chunk_id": chunk_id,
        "section_id": section_id,
        "sequence": sequence,
        "text": f"SYNTHETIC {chunk_id}",
        "plain_text": f"SYNTHETIC {chunk_id}",
        "source_locator": f"test:{chunk_id}",
        "passage_links": [
            {"canonical_passage": passage, "raw_citation": passage} for passage in links
        ],
    }


def _author_block(
    *,
    author_id: str,
    name: str,
    layout: str,
    chunks: list[tuple[str, list[str]]],
) -> dict:
    work_id = f"{author_id}.work"
    edition_id = f"{author_id}.edition"
    token = author_id.replace(".", "_")
    sections: list[dict] = []
    chunk_rows: list[dict] = []
    if layout == "volume":
        root_id = f"{token}.vol"
        part_id = f"{token}.part"
        chapter_id = f"{token}.ch"
        sections.extend(
            [
                _section(root_id, parent=None, section_type="volume", heading="Vol. I", sequence=1, edition_id=edition_id),
                _section(part_id, parent=root_id, section_type="part", heading="Part I", sequence=1, edition_id=edition_id),
                _section(chapter_id, parent=part_id, section_type="chapter", heading="Chapter 1.", sequence=1, edition_id=edition_id),
            ]
        )
        parent = chapter_id
        leaf_type = "subsection"
        heading_for = lambda index: f"§{index}"
    else:
        root_id = f"{token}.book"
        chapter_id = f"{token}.ch"
        sections.extend(
            [
                _section(root_id, parent=None, section_type="book", heading="BOOK FIRST.", sequence=1, edition_id=edition_id),
                _section(chapter_id, parent=root_id, section_type="chapter", heading="CHAPTER 1.", sequence=1, edition_id=edition_id),
            ]
        )
        parent = chapter_id
        leaf_type = "section"
        heading_for = lambda index: f"{index}."
    for index, (chunk_id, links) in enumerate(chunks, start=1):
        section_id = f"{token}.s{index}"
        sections.append(
            _section(
                section_id,
                parent=parent,
                section_type=leaf_type,
                heading=heading_for(index),
                sequence=index,
                edition_id=edition_id,
            )
        )
        chunk_rows.append(_chunk(chunk_id, section_id, links, sequence=1))
    return {
        "author": {
            "author_id": author_id,
            "canonical_name": name,
            "tradition": "reformed",
            "birth_year": None,
            "death_year": None,
        },
        "work": {
            "work_id": work_id,
            "author_id": author_id,
            "title": f"{name} Work",
            "original_title": None,
            "tradition": "reformed",
            "original_language": "en",
        },
        "edition": {
            "edition_id": edition_id,
            "work_id": work_id,
            "edition_label": "Test",
            "translator": None,
            "publication_year": 1871,
            "publisher": "Test",
            "language": "en",
            "license": "unspecified",
            "rights_status": "needs-review",
            "rights_note": "Synthetic diversity fixture.",
            "source_url": "https://example.test/diversity",
            "corpus": "ccel",
            "external_id": author_id,
        },
        "sections": sections,
        "chunks": chunk_rows,
    }


def _repo_from_blocks(tmp_path: Path, blocks: list[dict]) -> TheologyRepository:
    document = {
        "authors": [block["author"] for block in blocks],
        "works": [block["work"] for block in blocks],
        "editions": [block["edition"] for block in blocks],
        "sections": [section for block in blocks for section in block["sections"]],
        "chunks": [chunk for block in blocks for chunk in block["chunks"]],
    }
    database = tmp_path / "diversity.sqlite3"
    import_theology_sqlite(document=document, database_path=database)
    return TheologyRepository(database)


def _exact_ids(author: str, count: int) -> list[tuple[str, list[str]]]:
    return [(f"{author}.{index}", [QUERY]) for index in range(1, count + 1)]


def _overlap_ids(author: str, count: int) -> list[tuple[str, list[str]]]:
    return [(f"{author}.ov{index}", [OVERLAP]) for index in range(1, count + 1)]


def test_author_diversity_cap_is_three() -> None:
    assert AUTHOR_DIVERSITY_CAP == 3


def test_a_single_author_exact_keeps_top_six(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="ccel.calvin",
                name="John Calvin",
                layout="book",
                chunks=_exact_ids("calvin", 6),
            )
        ],
    )
    hits = repo.chunks_for_passage(QUERY, limit=6)
    assert [hit.author_id for hit in hits] == ["ccel.calvin"] * 6
    assert [hit.chunk_id for hit in hits] == [f"calvin.{index}" for index in range(1, 7)]


def test_b_equal_exact_authors_split_three_and_three(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="ccel.calvin",
                name="John Calvin",
                layout="book",
                chunks=_exact_ids("calvin", 6),
            ),
            _author_block(
                author_id="ccel.hodge",
                name="Charles Hodge",
                layout="volume",
                chunks=_exact_ids("hodge", 6),
            ),
        ],
    )
    hits = repo.chunks_for_passage(QUERY, limit=6)
    authors = [hit.author_id for hit in hits]
    assert authors.count("ccel.calvin") == 3
    assert authors.count("ccel.hodge") == 3
    assert authors[:3] == ["ccel.calvin"] * 3
    assert authors[3:] == ["ccel.hodge"] * 3


def test_c_overlap_does_not_displace_exact(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="ccel.hodge",
                name="Charles Hodge",
                layout="volume",
                chunks=_exact_ids("hodge", 6),
            ),
            _author_block(
                author_id="ccel.calvin",
                name="John Calvin",
                layout="book",
                chunks=_overlap_ids("calvin", 3),
            ),
        ],
    )
    hits = repo.chunks_for_passage(QUERY, limit=6)
    assert [hit.author_id for hit in hits] == ["ccel.hodge"] * 6
    assert all(QUERY in hit.canonical_passages for hit in hits)


def test_d_mixed_exact_same_tier_is_three_and_three(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="ccel.calvin",
                name="John Calvin",
                layout="book",
                chunks=_exact_ids("calvin", 3),
            ),
            _author_block(
                author_id="ccel.hodge",
                name="Charles Hodge",
                layout="volume",
                chunks=_exact_ids("hodge", 6),
            ),
        ],
    )
    hits = repo.chunks_for_passage(QUERY, limit=6)
    authors = [hit.author_id for hit in hits]
    assert authors.count("ccel.calvin") == 3
    assert authors.count("ccel.hodge") == 3


def test_e_soft_cap_fills_when_second_author_is_short(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="ccel.calvin",
                name="John Calvin",
                layout="book",
                chunks=_exact_ids("calvin", 2),
            ),
            _author_block(
                author_id="ccel.hodge",
                name="Charles Hodge",
                layout="volume",
                chunks=_exact_ids("hodge", 10),
            ),
        ],
    )
    hits = repo.chunks_for_passage(QUERY, limit=6)
    authors = [hit.author_id for hit in hits]
    assert authors.count("ccel.calvin") == 2
    assert authors.count("ccel.hodge") == 4


def test_f_three_authors_are_capped_and_deterministic(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="ccel.calvin",
                name="John Calvin",
                layout="book",
                chunks=_exact_ids("calvin", 6),
            ),
            _author_block(
                author_id="ccel.hodge",
                name="Charles Hodge",
                layout="volume",
                chunks=_exact_ids("hodge", 6),
            ),
            _author_block(
                author_id="ccel.ursinus",
                name="Zacharias Ursinus",
                layout="book",
                chunks=_exact_ids("ursinus", 6),
            ),
        ],
    )
    first = [hit.author_id for hit in repo.chunks_for_passage(QUERY, limit=6)]
    second = [hit.author_id for hit in repo.chunks_for_passage(QUERY, limit=6)]
    assert first == second
    assert max(first.count(author) for author in set(first)) <= 3
    assert first.count("ccel.calvin") == 3
    assert first.count("ccel.hodge") == 3
    assert "ccel.ursinus" not in first


def test_hodge_volumes_share_one_author_cap(tmp_path: Path) -> None:
    volumes = []
    for volume in (1, 2, 3):
        block = _author_block(
            author_id="ccel.hodge",
            name="Charles Hodge",
            layout="volume",
            chunks=[(f"hodge.v{volume}.{index}", [QUERY]) for index in range(1, 4)],
        )
        work_id = "ccel.hodge.work"
        edition_id = f"ccel.hodge.vol{volume}"
        token = f"vol{volume}"
        block["work"]["work_id"] = work_id
        block["edition"]["work_id"] = work_id
        block["edition"]["edition_id"] = edition_id
        for section in block["sections"]:
            section["edition_id"] = edition_id
            suffix = section["section_id"].split(".", 1)[-1]
            section["section_id"] = f"{token}.{suffix}"
            if section["parent_section_id"]:
                parent_suffix = section["parent_section_id"].split(".", 1)[-1]
                section["parent_section_id"] = f"{token}.{parent_suffix}"
        for chunk in block["chunks"]:
            suffix = chunk["section_id"].split(".", 1)[-1]
            chunk["section_id"] = f"{token}.{suffix}"
        volumes.append(block)
    database = tmp_path / "hodge-volumes.sqlite3"
    import_theology_sqlite(
        document={
            "authors": [volumes[0]["author"]],
            "works": [volumes[0]["work"]],
            "editions": [block["edition"] for block in volumes],
            "sections": [section for block in volumes for section in block["sections"]],
            "chunks": [chunk for block in volumes for chunk in block["chunks"]],
        },
        database_path=database,
    )
    hits = TheologyRepository(database).chunks_for_passage(QUERY, limit=6)
    assert {hit.author_id for hit in hits} == {"ccel.hodge"}
    assert len(hits) == 6


def test_document_order_uses_author_id_not_missing_book_seq(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="ccel.hodge",
                name="Charles Hodge",
                layout="volume",
                chunks=[("hodge.1", [QUERY])],
            ),
            _author_block(
                author_id="ccel.calvin",
                name="John Calvin",
                layout="book",
                chunks=[("calvin.1", [QUERY])],
            ),
        ],
    )
    hits = repo.chunks_for_passage(QUERY, limit=6)
    assert [hit.author_id for hit in hits] == ["ccel.calvin", "ccel.hodge"]
    assert [hit.chunk_id for hit in hits] == ["calvin.1", "hodge.1"]


def test_document_order_author_id_beats_hodge_structure_even_if_ids_reverse(tmp_path: Path) -> None:
    repo = _repo_from_blocks(
        tmp_path,
        [
            _author_block(
                author_id="zz.hodge",
                name="Charles Hodge",
                layout="volume",
                chunks=[("hodge.1", [QUERY])],
            ),
            _author_block(
                author_id="aa.calvin",
                name="John Calvin",
                layout="book",
                chunks=[("calvin.1", [QUERY])],
            ),
        ],
    )
    hits = repo.chunks_for_passage(QUERY, limit=2)
    assert [hit.author_id for hit in hits] == ["aa.calvin", "zz.hodge"]


def test_production_calvin_top_results_unchanged() -> None:
    database = Path("data/generated/theology.sqlite3")
    if not database.is_file():
        return
    repo = TheologyRepository(database)
    if not repo.store_status().available:
        return
    if repo.store_status().import_mode != "ccel_thml":
        return
    for passage, expected in CALVIN_TOP6.items():
        hits = repo.chunks_for_passage(passage, limit=6)
        assert [hit.chunk_id for hit in hits] == expected
        assert all(hit.author_id == "ccel.calvin" for hit in hits)
