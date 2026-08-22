from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pytest

from bible_engine.hymn_repository import HymnRecord, HymnRepositoryStatus
from bible_engine.hymn_repository import get_hymn_candidates as repo_get_hymn_candidates
from bible_engine.hymn_repository import get_status, validate_hymn_ids
from bible_engine.hymn_sqlite import import_dtx_hymnal_database
from hymn_recommendation_ai import (
    ERE_BOOK_LABEL,
    build_hymn_ranking_prompt,
    build_topic_search_profile,
    _collect_candidates,
    recommend_hymns,
)


ROOT = Path(__file__).resolve().parents[1]
ERE_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"


H1 = HymnRecord(
    hymn_id="ERE:1",
    hymnal_code="ERE",
    number=1,
    variant="",
    display_number="1",
    first_line="DB first line 1",
    title="DB title 1",
    section="",
    parent_section="",
)
H254A = HymnRecord(
    hymn_id="ERE:254a",
    hymnal_code="ERE",
    number=254,
    variant="a",
    display_number="254a",
    first_line="DB first line 254a",
    title="DB title 254a",
    section="Reformáció",
    parent_section="",
)
H254B = HymnRecord(
    hymn_id="ERE:254b",
    hymnal_code="ERE",
    number=254,
    variant="b",
    display_number="254b",
    first_line="DB first line 254b",
    title="DB title 254b",
    section="Reformáció",
    parent_section="",
)
H504 = HymnRecord(
    hymn_id="ERE:504",
    hymnal_code="ERE",
    number=504,
    variant="",
    display_number="504",
    first_line="DB first line 504",
    title="DB title 504",
    section="Kánonok",
    parent_section="Bibliaórák",
)


class FakeRepository:
    def __init__(
        self,
        *,
        available: bool = True,
        candidates: list[HymnRecord] | None = None,
    ) -> None:
        self.status = HymnRepositoryStatus(
            available=available,
            reason="ok" if available else "database_missing",
            database_path="fake.sqlite3",
        )
        self.candidates = candidates if candidates is not None else [H1, H254A, H254B, H504]
        self.candidate_queries: list[str] = []
        self.validated_ids: list[str] = []

    def ensure_hymn_database(self) -> HymnRepositoryStatus:
        return self.status

    def get_status(self) -> HymnRepositoryStatus:
        return self.status

    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = 36,
    ) -> list[HymnRecord]:
        self.candidate_queries.append(query)
        return self.candidates[:limit]

    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]:
        self.validated_ids.extend(hymn_ids)
        by_id = {h.hymn_id: h for h in self.candidates}
        return {hymn_id: by_id[hymn_id] for hymn_id in self.validated_ids if hymn_id in by_id}


class LocalDatabaseRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def ensure_hymn_database(self) -> HymnRepositoryStatus:
        return get_status(self.database_path)

    def get_status(self) -> HymnRepositoryStatus:
        return get_status(self.database_path)

    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = 36,
    ) -> list[HymnRecord]:
        return repo_get_hymn_candidates(
            query,
            hymnal_codes,
            limit=limit,
            database_path=self.database_path,
        )

    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]:
        return validate_hymn_ids(hymn_ids, database_path=self.database_path)


@pytest.fixture(scope="module")
def ere_repository(tmp_path_factory: pytest.TempPathFactory) -> LocalDatabaseRepository:
    if not ERE_SOURCE.exists():
        pytest.skip("Full ERE.dtx is local raw data")
    database = tmp_path_factory.mktemp("hymn_recommendation_quality") / "hymns.sqlite3"
    import_dtx_hymnal_database(ERE_SOURCE, database, hymnal_code="ERE")
    return LocalDatabaseRepository(database)


def test_valid_candidate_ranking_uses_database_fields() -> None:
    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        hangsuly="Isten oltalma",
        repository=FakeRepository(),
        llm_generate=lambda prompt: _ranking(["ERE:254a", "ERE:1"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["ERE:254a", "ERE:1"]
    assert "ERE 254a" in result.markdown
    assert "DB first line 254a" in result.markdown
    assert "LLM invented first line" not in result.markdown


def test_false_hymn_id_is_filtered_out() -> None:
    repo = FakeRepository()

    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["ERE:999", "ERE:254a"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["ERE:254a"]
    assert "ERE 999" not in result.markdown
    assert "ERE:999" in repo.validated_ids


def test_display_number_and_first_line_come_from_database_not_llm() -> None:
    db_hymn = replace(H254A, display_number="254a", first_line="Canonical DB line")
    repo = FakeRepository(candidates=[db_hymn])

    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: json.dumps(
            {
                "ranked": [
                    {
                        "slot": "opening",
                        "hymn_id": "ERE:254a",
                        "number": "999",
                        "first_line": "LLM invented first line",
                        "reason": "ok",
                        "connection": "ok",
                    }
                ]
            }
        ),
    )

    assert result.status == "ok"
    assert "ERE 254a" in result.markdown
    assert "Canonical DB line" in result.markdown
    assert "999" not in result.markdown
    assert "LLM invented first line" not in result.markdown


def test_unavailable_database_returns_unavailable_without_llm_call() -> None:
    called = False

    def llm(_prompt: str) -> str:
        nonlocal called
        called = True
        return _ranking(["ERE:1"])

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(available=False),
        llm_generate=llm,
    )

    assert result.status == "database_unavailable"
    assert called is False
    assert "Nem készítek szabad LLM-alapú éneklistát" in result.markdown


def test_unsupported_hymnal_has_no_hallucinated_fallback() -> None:
    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv="Református Énekeskönyv (2021)",
        repository=FakeRepository(),
        llm_generate=lambda prompt: _ranking(["ERE:1"]),
    )

    assert result.status == "unsupported_hymnal"
    assert result.recommendations == ()
    assert "még nincs validált helyi hymn adatbázis" in result.markdown


def test_empty_candidate_list_does_not_call_llm() -> None:
    called = False

    def llm(_prompt: str) -> str:
        nonlocal called
        called = True
        return _ranking(["ERE:1"])

    result = recommend_hymns(
        igehely="semmi",
        alkalom="Egyéb",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(candidates=[]),
        llm_generate=llm,
    )

    assert result.status == "no_candidates"
    assert called is False
    assert "Nem készítek szabad LLM-alapú éneklistát" in result.markdown


def test_no_valid_ranked_hymns_does_not_fallback_to_generated_song() -> None:
    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(),
        llm_generate=lambda prompt: json.dumps(
            {
                "ranked": [
                    {
                        "slot": "opening",
                        "hymn_id": "ERE:999",
                        "reason": "Invented",
                        "connection": "Invented",
                    }
                ]
            }
        ),
    )

    assert result.status == "no_valid_ranked_hymns"
    assert result.recommendations == ()
    assert "szabad, adatbázison kívüli énekajánlást" in result.markdown
    assert "jelenleg nem elérhető" not in result.markdown


def test_llm_network_error_message_returns_ranking_unavailable() -> None:
    repo = FakeRepository()

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: "⚠️ **Nincs internetkapcsolat.** Nem sikerült elérni a Gemini API-t.",
    )

    assert result.status == "ranking_unavailable"
    assert result.recommendations == ()
    assert repo.validated_ids == []
    assert "AI-rangsorolás jelenleg nem elérhető" in result.markdown
    assert "nem adott vissza ellenőrzött hymn_id-t" not in result.markdown


def test_malformed_json_returns_ranking_unavailable_without_crash() -> None:
    repo = FakeRepository()

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: "{not valid json",
    )

    assert result.status == "ranking_unavailable"
    assert result.recommendations == ()
    assert repo.validated_ids == []
    assert "malformed_json" in result.markdown


def test_variant_handling_keeps_ranked_variant() -> None:
    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(),
        llm_generate=lambda prompt: _ranking(["ERE:254b"]),
    )

    assert result.status == "ok"
    assert result.recommendations[0].hymn.hymn_id == "ERE:254b"
    assert result.recommendations[0].hymn.display_number == "254b"
    assert "DB first line 254b" in result.markdown


def test_mocked_llm_response_can_be_json_fenced() -> None:
    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(),
        llm_generate=lambda prompt: "```json\n" + _ranking(["ERE:254a"]) + "\n```",
    )

    assert result.status == "ok"
    assert result.recommendations[0].hymn.hymn_id == "ERE:254a"


def test_candidate_prompt_uses_unambiguous_hymn_id_fields() -> None:
    prompt = build_hymn_ranking_prompt(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        candidates=[H254A],
    )

    assert 'hymn_id="ERE:254a"' in prompt
    assert 'display_number="254a"' in prompt
    assert 'first_line="DB first line 254a"' in prompt
    assert "- ERE:254a:" not in prompt


def test_topic_profile_extracts_psalm_51_repentance() -> None:
    profile = build_topic_search_profile(
        igehely="Zsolt 51,3-14",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
    )

    assert "bűnbánat" in profile.themes
    assert "Bűnbánati énekek" in profile.section_hints
    assert "Megtérés" in profile.section_hints


def test_psalm_51_candidates_are_repentance_weighted(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="Zsolt 51,3-14",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert _count_sections(sections, {"Bűnbánati énekek", "Megtérés"}) >= 9
    assert "Karácsony" not in sections[:8]
    assert any(h.section == "Bűnbánati énekek" for h in candidates[:6])


def test_isaiah_53_candidates_prioritize_passion_sections(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="Ézs 53,3-7",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert sections[:8] == ["Nagypéntek"] * 8
    assert _count_sections(sections[:10], {"Nagypéntek", "Nagyszombat"}) >= 9
    assert "Isten dicsérete" not in sections[:10]


def test_first_corinthians_11_candidates_prioritize_communion_section(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert sections[:8] == ["Úrvacsorai énekek"] * 8
    assert _count_sections(sections[:10], {"Úrvacsorai énekek"}) >= 8


def test_psalm_23_candidates_prioritize_providence_and_trust(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert _count_sections(sections, {"Gondviselés", "Bizodalom Istenben"}) >= 10
    assert any(h.section == "Gondviselés" for h in candidates[:5])
    assert "Keresztyén élet" not in sections[:8]


def _ranking(ids: list[str]) -> str:
    slots = ["opening", "before_sermon", "main", "closing"]
    return json.dumps(
        {
            "ranked": [
                {
                    "slot": slot,
                    "hymn_id": hymn_id,
                    "reason": f"Reason for {hymn_id}",
                    "connection": f"Connection for {hymn_id}",
                }
                for slot, hymn_id in zip(slots, ids)
            ],
            "liturgical_note": "Rövid liturgiai megjegyzés.",
        }
    )


def _count_sections(sections: list[str], expected: set[str]) -> int:
    return sum(1 for section in sections if section in expected)
