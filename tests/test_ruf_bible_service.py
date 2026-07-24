"""RÚF betöltő — fixture és logikai tesztek (élő hálózat nélkül is)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ruf_bible_service import (
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
    ok(text.startswith("17 "), "Jude starts with 17")
    lines = text.splitlines()
    ok(len(lines) == 4, f"Jude line count {len(lines)}")
    for n in (17, 18, 19, 20):
        ok(any(line.startswith(f"{n} ") for line in lines), f"missing verse {n}")
    # Keresztutalás / navigáció ne legyen a szövegben
    lowered = text.casefold()
    for bad in ("2pt", "előző", "következő", "lábjegyzet", "szentiras", "copyright"):
        ok(bad not in lowered, f"Jude leaked {bad!r}")
    ok("csúfolódók" in text or "csufolodok" in text.casefold(), "Jude 18 body")
    ok(r["source_url"].endswith("/JUD/1"), f"url {r['source_url']}")
    ok(r["translation"] == "RÚF 2014", "translation")


def test_ranges_and_full_chapter() -> None:
    clear_ruf_cache()
    # B Jn 3,16
    r = fetch_ruf_passage("Jn 3,16", http_get=http_from_fixture("jhn_3.html"))
    ok(r["success"], f"Jn 3,16: {r.get('error')}")
    ok(r["text"].startswith("16 "), "Jn 16 prefix")
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

    r = fetch_ruf_passage("Jn 3,16", http_get=boom_timeout)
    ok(not r["success"], "timeout fail")
    ok("Időtúllépés" in r["error"] or "timeout" in r["error"].casefold(), r["error"])

    clear_ruf_cache()

    def boom_conn(url: str, timeout: float = 15.0) -> str:  # noqa: ARG001
        raise ConnectionError("Nincs elérhető kapcsolat a szentiras.hu-hoz")

    r = fetch_ruf_passage("Jn 3,16", http_get=boom_conn)
    ok(not r["success"], "conn fail")
    ok("kapcsolat" in r["error"].casefold() or "Nincs" in r["error"], r["error"])


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
    test_error_paths()
    test_network_errors()
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
