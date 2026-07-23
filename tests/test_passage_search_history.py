"""Korábban használt textusok — igehely-keresés history / overlap tesztek."""

from __future__ import annotations

import json
from typing import Any

from passage_search_ai import (
    REQUIRED_COUNT,
    merge_exclude_list,
    normalize_passage_reference,
    suggest_passages_for_occasion,
    validate_and_normalize_suggestions,
)
from passage_search_history import (
    CACHE_KEY,
    collect_used_passage_references,
    find_previous_usage,
    format_used_month_hu,
    get_cached_used_passage_history,
    invalidate_used_passage_cache,
    reference_overlaps_any,
    references_overlap,
)


def _sug(
    reference: str,
    *,
    title: str = "Rovid predikalhato cim",
    reason: str = "Illik az alkalomhoz.",
    direction: str = "Homiletikai irany.",
    familiarity: str = "less_common",
) -> dict[str, Any]:
    return {
        "reference": reference,
        "title": title,
        "reason": reason,
        "homiletical_direction": direction,
        "familiarity": familiarity,
    }


def _payload(occasion: str, suggestions: list[dict[str, Any]]) -> str:
    return json.dumps(
        {
            "occasion": occasion,
            "context_summary": occasion,
            "suggestions": suggestions,
        },
        ensure_ascii=False,
    )


_BATCH_A = [
    _sug("Job 19,23-27"),
    _sug("Zsolt 90,1-12"),
    _sug("Ezs 25,6-9"),
    _sug("2Kor 4,16-18"),
    _sug("1Pt 1,3-9"),
]

_BATCH_B = [
    _sug("Ezs 40,1-11"),
    _sug("Jn 14,27-31"),
    _sug("2Kor 1,3-7"),
    _sug("Zsolt 46,1-11"),
    _sug("1Thess 5,1-11"),
]


def test_guest_does_not_fetch_projects():
    calls: list[str] = []

    def fetch(owner: str) -> list[dict]:
        calls.append(owner)
        return [{"passage": "Jn 3,16"}]

    history = get_cached_used_passage_history(
        owner_sub=None,
        fetch_projects_fn=fetch,
        session_state={},
    )
    assert history.count == 0
    assert calls == []

    history2 = get_cached_used_passage_history(
        owner_sub="",
        fetch_projects_fn=fetch,
        session_state={},
    )
    assert history2.count == 0
    assert calls == []


def test_collect_used_passage_references_from_projects():
    projects = [
        {
            "id": "1",
            "passage": "Jn 3,16–18",
            "title": "Titkos cim — ne menjen AI-nak",
            "updated_at": "2026-03-15T10:00:00Z",
        },
        {
            "id": "2",
            "passage": "",
            "project_data": {"last_igehely": "János 3:16-18"},
            "updated_at": "2026-04-01T10:00:00Z",
        },
        {"id": "3", "passage": "   ", "updated_at": "2026-01-01T00:00:00Z"},
        {"id": "4", "passage": "NemLetezo 99,1", "updated_at": "2026-01-02T00:00:00Z"},
        {
            "id": "5",
            "passage": "Mt 5,1–12",
            "updated_at": "2026-05-20T12:00:00Z",
        },
    ]
    hist = collect_used_passage_references(projects)
    assert hist.count == 2
    norms = {normalize_passage_reference(r) for r in hist.normalized_references}
    assert normalize_passage_reference("Jn 3,16-18") in norms
    assert normalize_passage_reference("Mt 5,1-12") in norms
    # Dedup: Jn egyszer, frissebb dátum (project_data path április)
    jn = normalize_passage_reference("Jn 3,16-18")
    assert "2026-04" in hist.last_used_at_by_ref[jn]


def test_normalize_formats_equivalent_for_overlap():
    a = "Jn 3,16–18"
    b = "János 3:16-18"
    c = "Jn 3:16–18"
    assert normalize_passage_reference(a) == normalize_passage_reference(b)
    assert normalize_passage_reference(b) == normalize_passage_reference(c)
    assert references_overlap(a, b)
    assert references_overlap(b, c)


def test_exact_exclude_via_history_filter():
    used = ["Jn 3,16–18"]
    raw = [
        _sug("Jn 3,16-18"),
        *_BATCH_A[:4],
    ]
    out, warnings = validate_and_normalize_suggestions(
        raw, occasion="Temetés", history_exclude=used
    )
    assert all("Jn 3,16" not in s.reference for s in out)
    assert any("elvetve" in w.casefold() for w in warnings)


def test_overlap_exclude_ranges():
    used = "Jn 3,16–18"
    assert references_overlap(used, "Jn 3,16–21")
    assert references_overlap(used, "Jn 3,18–21")
    assert references_overlap(used, "Jn 3,14–21")
    assert reference_overlaps_any("Jn 3,16-21", [used])


def test_adjacent_non_overlapping_kept():
    used = "Jn 3,16–18"
    assert not references_overlap(used, "Jn 3,19–21")
    out, _ = validate_and_normalize_suggestions(
        [_sug("Jn 3,19-21"), *_BATCH_A[:4]],
        occasion="Temetés",
        history_exclude=[used],
    )
    assert any("19" in s.reference for s in out)


def test_other_book_same_chapter_verse_kept():
    used = "Jn 3,16–18"
    assert not references_overlap(used, "Mt 3,16–18")
    out, _ = validate_and_normalize_suggestions(
        [_sug("Mt 3,16-18"), *_BATCH_A[:4]],
        occasion="Temetés",
        history_exclude=[used],
    )
    assert any(s.reference.startswith("Mt") for s in out)


def test_server_filter_drops_history_overlap_from_model():
    prompts: list[str] = []
    calls = {"n": 0}

    def gen(prompt, **kwargs):
        prompts.append(prompt)
        calls["n"] += 1
        if calls["n"] == 1:
            # Modell engedetlen: visszaadja a kizárt Jn szakaszt
            polluted = [_sug("Jn 3,16-21"), *_BATCH_A[1:]]
            return _payload("Temetés", polluted)
        return _payload("Temetés", _BATCH_B)

    result = suggest_passages_for_occasion(
        occasion="Temetés",
        history_exclude_references=["Jn 3,16–18"],
        generate_fn=gen,
    )
    assert "KIZÁRT TEXTUSOK" in prompts[0]
    assert "ne ajánld" in prompts[0]
    assert "Titkos" not in prompts[0]
    assert result.ok, result.warnings
    for s in result.suggestions:
        assert not reference_overlaps_any(s.reference, ["Jn 3,16–18"])


def test_repair_fill_when_below_five_after_history_filter():
    calls = {"n": 0}

    def gen(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # 3 érvényes + 2 history-átfedő
            return _payload(
                "Temetés",
                [
                    _sug("Jn 3,16-21"),
                    _sug("Jn 3,14-20"),
                    *_BATCH_A[:3],
                ],
            )
        return _payload("Temetés", _BATCH_B)

    result = suggest_passages_for_occasion(
        occasion="Temetés",
        history_exclude_references=["Jn 3,16-18"],
        generate_fn=gen,
    )
    assert calls["n"] == 2
    assert result.ok, result.warnings
    assert len(result.suggestions) == REQUIRED_COUNT
    for s in result.suggestions:
        assert not reference_overlaps_any(s.reference, ["Jn 3,16-18"])


def test_toggle_off_badge_previous_usage():
    hist = collect_used_passage_references(
        [
            {
                "passage": "Jn 3,16-18",
                "updated_at": "2026-03-15T10:00:00Z",
            }
        ]
    )
    used, month = find_previous_usage("Jn 3,16-21", hist)
    assert used is True
    assert month == "2026. március"
    assert "projekt" not in month.casefold()
    assert format_used_month_hu("2026-07-01") == "2026. július"


def test_session_more_request_exclude_still_works():
    def gen_a(prompt, **kwargs):
        return _payload("Temetés", _BATCH_A)

    calls = {"n": 0}

    def gen_b(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _payload(
                "Temetés",
                [_sug(_BATCH_A[0]["reference"]), *_BATCH_B[1:]],
            )
        return _payload("Temetés", _BATCH_B)

    r1 = suggest_passages_for_occasion(occasion="Temetés", generate_fn=gen_a)
    exclude = merge_exclude_list(r1.suggestions, [])
    r2 = suggest_passages_for_occasion(
        occasion="Temetés",
        exclude_references=exclude,
        generate_fn=gen_b,
    )
    assert r2.ok
    assert {s.reference for s in r1.suggestions}.isdisjoint(
        {s.reference for s in r2.suggestions}
    )


def test_unsaved_work_not_in_durable_history():
    # collect csak a mentett projektek listájából dolgozik
    hist = collect_used_passage_references([])
    assert hist.count == 0
    # Session last_igehely NEM kerül bele, ha nincs a projects listában
    session_like = {"last_igehely": "Jn 3,16", "igehely_input": "Jn 3,16"}
    hist2 = collect_used_passage_references([session_like])  # type: ignore[list-item]
    # session_like-nak nincs passage / project_data.last_igehely kulcsa a tetején mint projekt
    # last_igehely top-level NEM számít (csak passage vagy project_data.last_igehely)
    assert hist2.count == 0


def test_save_invalidates_cache_then_excludes():
    ss: dict[str, Any] = {}
    projects_v1 = [{"passage": "Mt 5,1-12", "updated_at": "2026-01-01T00:00:00Z"}]
    projects_v2 = [
        {"passage": "Mt 5,1-12", "updated_at": "2026-01-01T00:00:00Z"},
        {"passage": "Jn 3,16-18", "updated_at": "2026-06-01T00:00:00Z"},
    ]
    store = {"rows": projects_v1}

    def fetch(_owner: str) -> list[dict]:
        return list(store["rows"])

    h1 = get_cached_used_passage_history(
        owner_sub="user-a",
        fetch_projects_fn=fetch,
        session_state=ss,
    )
    assert h1.count == 1
    assert CACHE_KEY in ss

    store["rows"] = projects_v2
    # Cache még a régit adja
    h_stale = get_cached_used_passage_history(
        owner_sub="user-a",
        fetch_projects_fn=fetch,
        session_state=ss,
    )
    assert h_stale.count == 1

    invalidate_used_passage_cache(ss)
    h2 = get_cached_used_passage_history(
        owner_sub="user-a",
        fetch_projects_fn=fetch,
        session_state=ss,
    )
    assert h2.count == 2
    assert any("Jn" in r for r in h2.normalized_references)


def test_delete_invalidates_unexclude():
    ss: dict[str, Any] = {}
    store = {
        "rows": [
            {"passage": "Jn 3,16-18", "updated_at": "2026-06-01T00:00:00Z"},
            {"passage": "Mt 5,1-12", "updated_at": "2026-01-01T00:00:00Z"},
        ]
    }

    def fetch(_owner: str) -> list[dict]:
        return list(store["rows"])

    h1 = get_cached_used_passage_history(
        owner_sub="user-a",
        fetch_projects_fn=fetch,
        session_state=ss,
    )
    assert h1.count == 2
    store["rows"] = [store["rows"][1]]  # Jn törölve
    invalidate_used_passage_cache(ss)
    h2 = get_cached_used_passage_history(
        owner_sub="user-a",
        fetch_projects_fn=fetch,
        session_state=ss,
    )
    assert h2.count == 1
    assert not any("Jn" in r for r in h2.normalized_references)


def test_other_user_projects_never_mixed():
    # collect csak a átadott listát nézi — más user projektjeit a hívó nem adja
    mine = collect_used_passage_references(
        [{"passage": "Jn 3,16", "owner_sub": "me"}]
    )
    other = collect_used_passage_references(
        [{"passage": "Mt 5,1-12", "owner_sub": "other"}]
    )
    assert mine.normalized_references != other.normalized_references
    ss: dict[str, Any] = {}
    fetch_calls: list[str] = []

    def fetch(owner: str) -> list[dict]:
        fetch_calls.append(owner)
        if owner == "me":
            return [{"passage": "Jn 3,16"}]
        return [{"passage": "Mt 5,1-12"}]

    h_me = get_cached_used_passage_history(
        owner_sub="me", fetch_projects_fn=fetch, session_state=ss
    )
    assert all("Jn" in r or "3,16" in r for r in h_me.normalized_references)
    invalidate_used_passage_cache(ss)
    h_other = get_cached_used_passage_history(
        owner_sub="other", fetch_projects_fn=fetch, session_state=ss
    )
    assert all("Mt" in r for r in h_other.normalized_references)
    assert fetch_calls == ["me", "other"]


def test_fetch_error_graceful_search_continues():
    ss: dict[str, Any] = {
        "passage_search": {
            "suggestions": _BATCH_A,
            "status": "ready",
            "context": "maradjon",
        }
    }

    def boom(_owner: str) -> list[dict]:
        raise RuntimeError("supabase down")

    history = get_cached_used_passage_history(
        owner_sub="user-a",
        fetch_projects_fn=boom,
        session_state=ss,
    )
    assert history.fetch_failed
    assert "nem sikerült ellenőrizni" in history.error_message
    # Korábbi keresési találatok érintetlenek
    assert ss["passage_search"]["suggestions"]
    assert ss["passage_search"]["context"] == "maradjon"

    # Keresés history nélkül továbbmegy
    result = suggest_passages_for_occasion(
        occasion="Temetés",
        history_exclude_references=[],
        generate_fn=lambda *a, **k: _payload("Temetés", _BATCH_A),
    )
    assert result.ok
    assert len(result.suggestions) == 5


def test_prompt_never_contains_project_pii():
    seen: list[str] = []

    def gen(prompt, **kwargs):
        seen.append(prompt)
        return _payload("Temetés", _BATCH_A)

    projects = [
        {
            "title": "Titkos gyaszbeszed Maria",
            "passage": "Jn 11,1-44",
            "notes": "csaladi tragédia részletek",
        }
    ]
    hist = collect_used_passage_references(projects)
    suggest_passages_for_occasion(
        occasion="Temetés",
        history_exclude_references=hist.normalized_references,
        generate_fn=gen,
    )
    blob = seen[0]
    assert "Titkos" not in blob
    assert "Maria" not in blob
    assert "csaladi" not in blob
    assert "Jn 11" in blob or "11,1" in blob
