"""RÚF betöltő — fixture és logikai tesztek (élő hálózat nélkül is)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ruf_bible_service import (
    RufHttpError,
    STALE_CACHE_WARNING,
    clear_ruf_cache,
    extract_verse_data_json,
    fetch_ruf_passage,
    parse_bible_reference,
    select_verse_range,
    verses_dict_from_verse_data,
)
from workspace_data import build_project_data, sanitize_project_data

FIXTURES = ROOT / "tests" / "fixtures" / "ruf"
errors: list[str] = []


def ok(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def http_from_fixture(name: str):
    html = load_fixture(name)

    def _get(url: str, timeout: float = 15.0) -> str:  # noqa: ARG001
        return html

    return _get


def html_from_verses(chapter: int, verses: list[tuple[int, str]]) -> str:
    payload = {
        "chapter": str(chapter),
        "verses": [
            {"verse_number": str(number), "verse": text}
            for number, text in verses
        ],
    }
    import json

    return (
        '<script id="verse-data" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )


def test_parse_forms() -> None:
    cases = {
        "Jn 3,16": ("JHN", 3, 16, 16),
        "Jn 3:16": ("JHN", 3, 16, 16),
        "Jn 3,16–18": ("JHN", 3, 16, 18),
        "Jn 3:16-18": ("JHN", 3, 16, 18),
        "Júd 17–20": ("JUD", 1, 17, 20),
        "Júd 17-20": ("JUD", 1, 17, 20),
        "1Kor 13,4–8": ("1CO", 13, 4, 8),
        "1Kor 13:4-8": ("1CO", 13, 4, 8),
        "1Móz 1,1–5": ("GEN", 1, 1, 5),
        "Zsolt 23": ("PSA", 23, None, None),
        "Fil 2,1–11": ("PHP", 2, 1, 11),
        "Mt 5,1–12": ("MAT", 5, 1, 12),
        # Gemini gyakran teljes magyar könyvnevet ad
        "Róma 8,31–37": ("ROM", 8, 31, 37),
        "2 Timóteus 4,6–8": ("2TI", 4, 6, 8),
        "Jelenések 21,1–5": ("REV", 21, 1, 5),
        "1 Péter 1,3–9": ("1PE", 1, 3, 9),
    }
    for ref, expected in cases.items():
        p = parse_bible_reference(ref)
        got = (p.book.code, p.chapter, p.verse_start, p.verse_end)
        ok(got == expected, f"parse {ref}: {got} != {expected}")


def test_bad_references() -> None:
    for ref, needle in [
        ("Xyyzz 1,1", "Ismeretlen"),
        ("Jn 3,20-18", "Fordított"),
        ("", "Add meg"),
    ]:
        try:
            parse_bible_reference(ref)
            errors.append(f"expected error for {ref!r}")
        except ValueError as exc:
            ok(needle.lower() in str(exc).lower() or needle in str(exc), f"{ref}: {exc}")


def test_jude_fixture() -> None:
    clear_ruf_cache()
    r = fetch_ruf_passage("Júd 17–20", http_get=http_from_fixture("jud_1.html"))
    ok(r["success"], f"Jude success: {r.get('error')}")
    text = r["text"]
    ok(text.startswith("17. "), "Jude starts with 17")
    lines = text.splitlines()
    ok(len(lines) == 4, f"Jude line count {len(lines)}")
    for n in (17, 18, 19, 20):
        ok(any(line.startswith(f"{n}. ") for line in lines), f"missing verse {n}")
    # Keresztutalás / navigáció ne legyen a szövegben
    lowered = text.casefold()
    for bad in ("2pt", "előző", "következő", "lábjegyzet", "szentiras", "copyright"):
        ok(bad not in lowered, f"Jude leaked {bad!r}")
    ok("csúfolódók" in text or "csufolodok" in text.casefold(), "Jude 18 body")
    ok(r["source_url"].endswith("/JUD/1"), f"url {r['source_url']}")
    ok(r["translation"] == "RÚF 2014", "translation")
    ok(r["verses"][0] == {"number": 17, "text": lines[0].removeprefix("17. ")}, "structured Jude verse")


def test_ranges_and_full_chapter() -> None:
    clear_ruf_cache()
    # B Jn 3,16
    r = fetch_ruf_passage("Jn 3,16", http_get=http_from_fixture("jhn_3.html"))
    ok(r["success"], f"Jn 3,16: {r.get('error')}")
    ok(r["text"].startswith("16. "), "Jn 16 prefix")
    ok(r["verses"] == [{"number": 16, "text": r["text"].removeprefix("16. ")}], "Jn structured verse")
    ok("\n" not in r["text"].strip(), "single verse one line")

    # C Jn 3,16-18
    clear_ruf_cache()
    r = fetch_ruf_passage("Jn 3,16–18", http_get=http_from_fixture("jhn_3.html"))
    ok(r["success"], f"Jn range: {r.get('error')}")
    ok(len(r["text"].splitlines()) == 3, "three verses")

    # D 1Kor 13,4-8
    clear_ruf_cache()
    r = fetch_ruf_passage("1Kor 13,4–8", http_get=http_from_fixture("1co_13.html"))
    ok(r["success"], f"1Kor: {r.get('error')}")
    ok(len(r["text"].splitlines()) == 5, "1Kor five verses")

    # E 1Móz 1,1-5
    clear_ruf_cache()
    r = fetch_ruf_passage("1Móz 1,1–5", http_get=http_from_fixture("gen_1.html"))
    ok(r["success"], f"Gen: {r.get('error')}")
    ok("Kezdetben teremtette" in r["text"], "Gen 1,1 text")
    ok(len(r["text"].splitlines()) == 5, "Gen five")

    # F Zsolt 23 full
    clear_ruf_cache()
    r = fetch_ruf_passage("Zsolt 23", http_get=http_from_fixture("psa_23.html"))
    ok(r["success"], f"Ps: {r.get('error')}")
    ok(len(r["text"].splitlines()) == 6, f"Ps lines {len(r['text'].splitlines())}")

    # G Fil 2,1-11
    clear_ruf_cache()
    r = fetch_ruf_passage("Fil 2,1–11", http_get=http_from_fixture("php_2.html"))
    ok(r["success"], f"Phil: {r.get('error')}")
    ok(len(r["text"].splitlines()) == 11, "Phil 11 verses")

    # H full chapter Jn 3
    clear_ruf_cache()
    r = fetch_ruf_passage("Jn 3", http_get=http_from_fixture("jhn_3.html"))
    ok(r["success"], f"Jn full: {r.get('error')}")
    ok(len(r["text"].splitlines()) == 36, f"Jn full {len(r['text'].splitlines())}")


def test_romans_multi_verse_structured_text() -> None:
    clear_ruf_cache()
    html = html_from_verses(
        8,
        [
            (1, "Nincsen azért most már semmiféle kárhoztató ítélet."),
            (2, "Mert az élet Lelkének törvénye megszabadított."),
            (3, "Amire ugyanis képtelen volt a törvény."),
            (4, "Hogy a törvény követelése teljesüljön bennünk."),
        ],
    )

    r = fetch_ruf_passage("Róm 8,1-4", http_get=lambda _url, timeout=None: html)

    assert r["success"]
    assert r["text"].splitlines() == [
        "1. Nincsen azért most már semmiféle kárhoztató ítélet.",
        "2. Mert az élet Lelkének törvénye megszabadított.",
        "3. Amire ugyanis képtelen volt a törvény.",
        "4. Hogy a törvény követelése teljesüljön bennünk.",
    ]
    assert r["verses"][0] == {
        "number": 1,
        "text": "Nincsen azért most már semmiféle kárhoztató ítélet.",
    }


def test_raw_html_extracts_three_digit_verse_number_and_text() -> None:
    data = extract_verse_data_json(
        html_from_verses(119, [(100, "Parancsolataidból értelmesebb lettem.")])
    )
    verses = verses_dict_from_verse_data(data)
    text, warnings, structured = select_verse_range(verses, 100, 100)

    assert warnings == []
    assert structured == [{"number": 100, "text": "Parancsolataidból értelmesebb lettem."}]
    assert text == "100. Parancsolataidból értelmesebb lettem."


def test_error_paths() -> None:
    clear_ruf_cache()
    r = fetch_ruf_passage("Xyyzz 1,1", http_get=http_from_fixture("jud_1.html"))
    ok(not r["success"], "unknown book should fail")
    ok("Ismeretlen" in r["error"], r["error"])

    clear_ruf_cache()
    r = fetch_ruf_passage("Jn 999", http_get=http_from_fixture("no_verse_data.html"))
    ok(not r["success"], "missing chapter / no verse-data")

    clear_ruf_cache()
    r = fetch_ruf_passage("Jn 3,90–91", http_get=http_from_fixture("jhn_3.html"))
    ok(not r["success"], "missing verses")
    ok("nem találhatók" in r["error"].casefold() or "hiányzik" in r["error"].casefold(), r["error"])

    clear_ruf_cache()
    r = fetch_ruf_passage("Jn 3,16–18", http_get=http_from_fixture("broken_json.html"))
    ok(not r["success"], "broken json")

    # Részleges: törölt vers a dictből
    data = extract_verse_data_json(load_fixture("jhn_3.html"))
    verses = verses_dict_from_verse_data(data)
    del verses[17]
    try:
        select_verse_range(verses, 16, 18)
        errors.append("partial should raise")
    except ValueError as exc:
        ok("Részleges" in str(exc) or "hiányzik" in str(exc).casefold(), str(exc))


def test_network_errors() -> None:
    clear_ruf_cache()

    def boom_timeout(url: str, timeout: float = 15.0) -> str:  # noqa: ARG001
        raise TimeoutError("Időtúllépés a szentiras.hu elérésekor. Próbáld újra később.")

    r = fetch_ruf_passage(
        "Jn 3,16",
        http_get=boom_timeout,
        retry_delays_s=(),
        sleep=lambda _delay: None,
    )
    ok(not r["success"], "timeout fail")
    ok("Időtúllépés" in r["error"] or "timeout" in r["error"].casefold(), r["error"])

    clear_ruf_cache()

    def boom_conn(url: str, timeout: float = 15.0) -> str:  # noqa: ARG001
        raise ConnectionError("Nincs elérhető kapcsolat a szentiras.hu-hoz")

    r = fetch_ruf_passage(
        "Jn 3,16",
        http_get=boom_conn,
        retry_delays_s=(),
        sleep=lambda _delay: None,
    )
    ok(not r["success"], "conn fail")
    ok("kapcsolat" in r["error"].casefold() or "Nincs" in r["error"], r["error"])


def test_retry_success_after_initial_timeout() -> None:
    clear_ruf_cache()
    calls: list[str] = []

    def flaky(url: str, timeout: object = None) -> str:  # noqa: ARG001
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("mock timeout")
        return load_fixture("jhn_3.html")

    sleeps: list[float] = []
    r = fetch_ruf_passage(
        "Jn 3,16",
        http_get=flaky,
        retry_delays_s=(0.5, 1.5),
        sleep=sleeps.append,
    )

    assert r["success"]
    assert len(calls) == 2
    assert sleeps == [0.5]
    assert "Mert úgy szerette" in r["text"]


def test_three_timeouts_return_controlled_error() -> None:
    clear_ruf_cache()
    calls = 0

    def timeout(url: str, timeout: object = None) -> str:  # noqa: ARG001
        nonlocal calls
        calls += 1
        raise TimeoutError("mock timeout")

    sleeps: list[float] = []
    r = fetch_ruf_passage(
        "Jn 3,16",
        http_get=timeout,
        retry_delays_s=(0.5, 1.5),
        sleep=sleeps.append,
    )

    assert not r["success"]
    assert calls == 3
    assert sleeps == [0.5, 1.5]
    assert "Külső szolgáltatási kapcsolat hibája" in r["error"]
    assert "Traceback" not in r["error"]


def test_http_503_retries_then_succeeds() -> None:
    clear_ruf_cache()
    calls = 0

    def flaky_503(url: str, timeout: object = None) -> str:  # noqa: ARG001
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RufHttpError(503, "Service Unavailable", transient=True)
        return load_fixture("jhn_3.html")

    r = fetch_ruf_passage(
        "Jn 3,16",
        http_get=flaky_503,
        retry_delays_s=(),
        sleep=lambda _delay: None,
    )

    assert r["success"]
    assert calls == 2


def test_http_404_does_not_retry() -> None:
    clear_ruf_cache()
    calls = 0

    def not_found(url: str, timeout: object = None) -> str:  # noqa: ARG001
        nonlocal calls
        calls += 1
        raise RufHttpError(404, "Not Found", transient=False)

    r = fetch_ruf_passage(
        "Jn 3,16",
        http_get=not_found,
        retry_delays_s=(),
        sleep=lambda _delay: None,
    )

    assert not r["success"]
    assert calls == 1
    assert "HTTP 404" in r["error"]


def test_cache_hit_skips_network_request() -> None:
    clear_ruf_cache()
    calls = 0

    def success(url: str, timeout: object = None) -> str:  # noqa: ARG001
        nonlocal calls
        calls += 1
        return load_fixture("jhn_3.html")

    first = fetch_ruf_passage("Jn 3,16", http_get=success)
    second = fetch_ruf_passage("Jn 3,16", http_get=success)

    assert first["success"]
    assert second["success"]
    assert calls == 1
    assert second["cache_status"] == "fresh"


def test_live_failure_uses_previous_cached_passage() -> None:
    clear_ruf_cache()
    first = fetch_ruf_passage("Jn 3,16", http_get=http_from_fixture("jhn_3.html"))
    assert first["success"]

    def timeout(url: str, timeout: object = None) -> str:  # noqa: ARG001
        raise TimeoutError("mock timeout")

    second = fetch_ruf_passage(
        "Jn 3,16",
        http_get=timeout,
        cache_ttl_s=0,
        retry_delays_s=(),
        sleep=lambda _delay: None,
    )

    assert second["success"]
    assert second["text"] == first["text"]
    assert STALE_CACHE_WARNING in second["warnings"]
    assert second["cache_status"] == "stale_fallback"


def test_cache_key_keeps_distinct_verse_ranges() -> None:
    clear_ruf_cache()
    calls = 0

    def success(url: str, timeout: object = None) -> str:  # noqa: ARG001
        nonlocal calls
        calls += 1
        return load_fixture("jhn_3.html")

    single = fetch_ruf_passage("Jn 3,16", http_get=success)
    ranged = fetch_ruf_passage("Jn 3,16-18", http_get=success)

    assert single["success"]
    assert ranged["success"]
    assert len(single["text"].splitlines()) == 1
    assert len(ranged["text"].splitlines()) == 3
    assert calls == 1


def test_cache_without_live_or_stale_returns_manual_fallback_state() -> None:
    clear_ruf_cache()

    def timeout(url: str, timeout: object = None) -> str:  # noqa: ARG001
        raise TimeoutError("mock timeout")

    r = fetch_ruf_passage(
        "Jn 3,16",
        http_get=timeout,
        retry_delays_s=(),
        sleep=lambda _delay: None,
    )

    assert not r["success"]
    assert r["text"] == ""
    assert r["source_name"] == "szentiras.hu"
    assert "Külső szolgáltatási kapcsolat hibája" in r["error"]


def test_unicode_hungarian_text_survives_retry_and_cache() -> None:
    clear_ruf_cache()
    r = fetch_ruf_passage("Jn 3,16", http_get=http_from_fixture("jhn_3.html"))
    cached = fetch_ruf_passage("Jn 3,16", http_get=lambda _url, timeout=None: "")

    assert r["success"]
    assert cached["success"]
    assert "Mert úgy szerette Isten a világot" in cached["text"]


def test_project_persist() -> None:
    state = {
        "last_igehely": "Júd 17–20",
        "bible_translation": "RÚF 2014",
        "passage_text": "17 foo\n18 bar",
        "passage_text_source": "szentiras.hu",
        "passage_text_source_url": "https://szentiras.hu/biblia/ruf/JUD/1",
        "passage_text_fetched_at": "2026-07-21T20:00:00Z",
        "passage_text_fetched_reference": "Júd 17–20",
    }
    pdata = build_project_data(state, version="1.0")
    ok(pdata["passage_text"].startswith("17 "), "persist text")
    ok(pdata["passage_text_source"] == "szentiras.hu", "persist source")
    ok("passage_text_input" not in pdata, "no widget leak")

    old = sanitize_project_data({"last_igehely": "Jn 3,16"})
    ok(old.get("passage_text_source") == "", "old project default")
    ok(old.get("passage_text") == "", "old project text default")


def test_error_keeps_existing_text_contract() -> None:
    """Hiba esetén a szolgáltatás üres text-et ad vissza; a UI nem írja felül."""
    clear_ruf_cache()
    r = fetch_ruf_passage("Jn 999", http_get=http_from_fixture("no_verse_data.html"))
    ok(r["text"] == "", "error text empty so UI can keep previous")


def main() -> None:
    test_parse_forms()
    test_bad_references()
    test_jude_fixture()
    test_ranges_and_full_chapter()
    test_romans_multi_verse_structured_text()
    test_raw_html_extracts_three_digit_verse_number_and_text()
    test_error_paths()
    test_network_errors()
    test_retry_success_after_initial_timeout()
    test_three_timeouts_return_controlled_error()
    test_http_503_retries_then_succeeds()
    test_http_404_does_not_retry()
    test_cache_hit_skips_network_request()
    test_live_failure_uses_previous_cached_passage()
    test_cache_key_keeps_distinct_verse_ranges()
    test_cache_without_live_or_stale_returns_manual_fallback_state()
    test_unicode_hungarian_text_survives_retry_and_cache()
    test_project_persist()
    test_error_keeps_existing_text_contract()
    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    print("OK ruf bible fixture/unit tests passed")


if __name__ == "__main__":
    main()
