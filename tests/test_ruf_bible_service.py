from __future__ import annotations

import json
import re
import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest
import requests

import ruf_bible_service as ruf


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any | None = None,
        *,
        headers: dict[str, str] | None = None,
        reason: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.reason = reason

    def json(self) -> Any:
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


def api_payload(reference: str = "Jn 3,16", verses: list[tuple[int, str]] | None = None) -> dict[str, Any]:
    items = verses or [(16, "Mert úgy szerette Isten a világot.")]
    book, chapter = ("JHN", 3)
    chapter_match = re.search(r"\s(\d+)", reference)
    if chapter_match:
        chapter = int(chapter_match.group(1))
    if reference.startswith("1Móz"):
        book = "GEN"
    elif reference.startswith("Róm"):
        book = "ROM"
    elif reference.startswith("Ef"):
        book = "EPH"
    elif reference.startswith("Júd"):
        book, chapter = ("JUD", 1)
    return {
        "keres": {"feladat": "idezet", "hivatkozas": reference, "forma": "json"},
        "valasz": {
            "forditas": {
                "nev": "Magyar Bibliatársulat újfordítású Bibliája (2014)",
                "rov": "RUF",
            },
            "versek": [
                {
                    "szoveg": text,
                    "jegyzetek": [],
                    "hely": {"gepi": f"{book}_{chapter}_{number}", "szep": f"{reference.split(',')[0]},{number}"},
                }
                for number, text in items
            ],
        },
    }


@pytest.fixture(autouse=True)
def clear_cache_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    ruf.clear_ruf_cache()
    monkeypatch.delenv(ruf.SZENTIRAS_EU_API_KEY_NAME, raising=False)
    monkeypatch.setattr(ruf, "_streamlit_secret", lambda _name: "")


def test_api_key_from_streamlit_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ruf, "_streamlit_secret", lambda name: "secret-key" if name == ruf.SZENTIRAS_EU_API_KEY_NAME else "")
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "env-key")

    assert ruf.get_szentiras_eu_api_key() == "secret-key"


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "env-key")

    assert ruf.get_szentiras_eu_api_key() == "env-key"


def test_missing_api_key_returns_manual_fallback_state() -> None:
    result = ruf.fetch_ruf_passage("Jn 3,16")

    assert not result["success"]
    assert result["error"] == ruf.API_NOT_CONFIGURED_MESSAGE
    assert result["verses"] == []


def test_single_verse_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    result = ruf.fetch_ruf_passage("Jn 3,16", http_get=lambda *_args, **_kwargs: api_payload())

    assert result["success"]
    assert result["verses"][0]["verse_number"] == 16
    assert "16. Mert úgy szerette" in result["text"]
    assert result["source_name"] == "Szentírás.eu"
    assert result["source_attribution"] == ruf.SOURCE_ATTRIBUTION


def test_szentiras_eu_fields_map_to_internal_verse_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    result = ruf.fetch_ruf_passage(
        "Ef 4,1",
        http_get=lambda *_args, **_kwargs: {
            "keres": {"feladat": "idezet", "hivatkozas": "Ef 4,1", "forma": "json"},
            "valasz": {
                "forditas": {"nev": "RUF", "rov": "RUF"},
                "versek": [
                    {
                        "szoveg": "Kérlek tehát titeket én, aki fogoly vagyok az Úrért.",
                        "jegyzetek": [],
                        "hely": {"gepi": "EPH_4_1", "szep": "Ef 4,1"},
                    }
                ],
            },
        },
    )

    assert result["success"]
    assert result["verses"] == [
        {
            "verse_number": 1,
            "number": 1,
            "text": "Kérlek tehát titeket én, aki fogoly vagyok az Úrért.",
            "reference": "Ef 4,1",
            "machine_reference": "EPH_4_1",
        }
    ]
    assert result["text"].startswith("1. Kérlek tehát")


def test_ephesians_4_1_6_multi_verse_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    result = ruf.fetch_ruf_passage(
        "Ef 4,1-6",
        http_get=lambda *_args, **_kwargs: api_payload(
            "Ef 4,1-6",
            [
                (1, "Kérlek tehát titeket."),
                (2, "Teljes alázatossággal."),
                (3, "Igyekezzetek megtartani."),
                (4, "Egy a test."),
                (5, "Egy az Úr."),
                (6, "Egy az Istene és Atyja mindeneknek."),
            ],
        ),
    )

    assert result["success"]
    assert [item["verse_number"] for item in result["verses"]] == [1, 2, 3, 4, 5, 6]
    assert "1. Kérlek tehát titeket." in result["text"]
    assert "6. Egy az Istene és Atyja mindeneknek." in result["text"]


def test_multi_verse_new_testament_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    result = ruf.fetch_ruf_passage(
        "Róm 8,1-4",
        http_get=lambda *_args, **_kwargs: api_payload(
            "Róm 8,1-4",
            [(1, "Nincs tehát most már semmiféle kárhoztató ítélet."), (2, "Mert a Lélek törvénye."), (3, "Amire képtelen volt a törvény."), (4, "Hogy a törvény követelése teljesüljön.")],
        ),
    )

    assert result["success"]
    assert [item["verse_number"] for item in result["verses"]] == [1, 2, 3, 4]


def test_old_testament_and_numbered_books(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    result = ruf.fetch_ruf_passage(
        "1Móz 1,1-5",
        http_get=lambda *_args, **_kwargs: api_payload("1Móz 1,1-5", [(1, "Kezdetben."), (2, "A föld."), (3, "Legyen."), (4, "Látta."), (5, "Este és reggel.")]),
    )

    assert result["success"]
    assert result["verses"][0]["machine_reference"].startswith("GEN_1_")


def test_single_chapter_book(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")
    requested_urls: list[str] = []

    def fake_get(url: str, **_kwargs):
        requested_urls.append(url)
        return api_payload("Jud 1,24-25", [(24, "Annak pedig."), (25, "Az egyedul udvozito Istennek.")])

    result = ruf.fetch_ruf_passage("Jud 24-25", http_get=fake_get)

    assert result["success"]
    assert result["normalized_reference"] == "Júd 24–25"
    parsed = ruf.parse_bible_reference("Jud 24-25")
    assert parsed.canonical_reference == "Júd 1,24–25"
    assert parsed.api_reference == "Júd 1,24-25"
    assert requested_urls
    assert "1%2C24-25" in requested_urls[0]


def test_single_chapter_short_and_explicit_forms_share_cache_key() -> None:
    short = ruf.parse_bible_reference("Jud 24-25")
    explicit = ruf.parse_bible_reference("Jud 1,24-25")
    assert short.canonical_reference == explicit.canonical_reference
    assert short.api_reference == explicit.api_reference
    assert ruf._passage_key(short) == ruf._passage_key(explicit)


def test_non_single_chapter_range_without_comma_is_rejected() -> None:
    with pytest.raises(ValueError):
        ruf.parse_bible_reference("Jn 24-25")

def test_empty_or_invalid_json_is_not_successful(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    empty = ruf.fetch_ruf_passage("Jn 3,16", http_get=lambda *_args, **_kwargs: {"valasz": {"forditas": {"rov": "RUF"}, "versek": []}})
    invalid = ruf.fetch_ruf_passage("Jn 3,16", http_get=lambda *_args, **_kwargs: "{not json")

    assert not empty["success"]
    assert not invalid["success"]


def test_api_items_without_renderable_text_are_not_successful(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    result = ruf.fetch_ruf_passage(
        "Jn 3,16",
        http_get=lambda *_args, **_kwargs: {
            "valasz": {
                "forditas": {"rov": "RUF"},
                "versek": [
                    {"szoveg": "   ", "hely": {"gepi": "JHN_3_16", "szep": "Jn 3,16"}}
                ],
            }
        },
    )

    assert not result["success"]
    assert result["verses"] == []


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "A Szentírás.eu API-kulcs hiányzik vagy érvénytelen."),
        (403, "A Szentírás.eu API-kulcs jelenleg nem használható."),
        (404, "A megadott igehely nem található."),
    ],
)
def test_final_http_errors_do_not_use_stale_cache(monkeypatch: pytest.MonkeyPatch, status: int, message: str) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")
    ruf.fetch_ruf_passage("Jn 3,16", http_get=lambda *_args, **_kwargs: api_payload())

    result = ruf.fetch_ruf_passage(
        "Jn 3,16",
        cache_ttl_s=0,
        http_get=lambda *_args, **_kwargs: FakeResponse(status, {}),
    )

    assert not result["success"]
    assert result["error"] == message
    assert not result["is_stale"]


def test_429_retries_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")
    sleeps: list[float] = []
    calls = [FakeResponse(429, {}, headers={"Retry-After": "1"}), FakeResponse(200, api_payload())]

    result = ruf.fetch_ruf_passage(
        "Jn 3,16",
        http_get=lambda *_args, **_kwargs: calls.pop(0),
        sleep=sleeps.append,
    )

    assert result["success"]
    assert sleeps == [1.0]


def test_500_and_timeout_use_stale_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")
    first = ruf.fetch_ruf_passage("Jn 3,16", http_get=lambda *_args, **_kwargs: api_payload())

    stale_500 = ruf.fetch_ruf_passage(
        "Jn 3,16",
        cache_ttl_s=0,
        http_get=lambda *_args, **_kwargs: FakeResponse(500, {}),
        retry_delays_s=(),
    )
    stale_timeout = ruf.fetch_ruf_passage(
        "Jn 3,16",
        cache_ttl_s=0,
        http_get=lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout("timeout")),
        retry_delays_s=(),
    )

    assert first["success"]
    assert stale_500["success"] and stale_500["is_stale"]
    assert stale_timeout["success"] and stale_timeout["is_stale"]


def test_cache_hit_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")
    calls = 0

    def success(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return api_payload()

    first = ruf.fetch_ruf_passage("Jn 3,16", http_get=success)
    second = ruf.fetch_ruf_passage("Jn 3,16", http_get=success)

    assert first["success"] and second["success"]
    assert calls == 1
    assert second["from_cache"]


def test_old_cache_schema_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")
    parsed = ruf.parse_bible_reference("Jn 3,16")
    key = ruf._passage_key(parsed)
    ruf._PASSAGE_CACHE[key] = {
        "fetched_at": time.time(),
        "result": {
            "success": True,
            "text": "",
            "verses": [],
            "source_name": ruf.SOURCE_NAME,
            "source_url": "https://szentiras.eu/api/idezet/Jn%203%2C16/RUF",
            "warnings": [],
        },
    }
    calls = 0

    def success(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return api_payload()

    result = ruf.fetch_ruf_passage("Jn 3,16", http_get=success)

    assert result["success"]
    assert calls == 1
    assert result["text"].strip()


def test_old_cache_schema_is_not_used_as_stale_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")
    parsed = ruf.parse_bible_reference("Jn 3,16")
    key = ruf._passage_key(parsed)
    ruf._PASSAGE_CACHE[key] = {
        "fetched_at": 0,
        "result": {
            "success": True,
            "text": "16. Bad old cached text.",
            "verses": [{"number": 16, "text": "Bad old cached text."}],
            "source_name": ruf.SOURCE_NAME,
            "source_url": "https://szentiras.eu/api/idezet/Jn%203%2C16/RUF",
            "warnings": [],
        },
    }

    result = ruf.fetch_ruf_passage(
        "Jn 3,16",
        cache_ttl_s=0,
        http_get=lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout("timeout")),
        retry_delays_s=(),
    )

    assert not result["success"]
    assert not result["is_stale"]


def test_returned_passage_must_cover_requested_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ruf.SZENTIRAS_EU_API_KEY_NAME, "key")

    result = ruf.fetch_ruf_passage(
        "Ef 1,1-4",
        http_get=lambda *_args, **_kwargs: api_payload("Ef 1,1-4", [(1, "Pál."), (2, "Kegyelem.")]),
    )

    assert not result["success"]
    assert "nem a teljes kért igehelyet" in result["error"]


def test_old_html_providers_are_removed() -> None:
    assert not hasattr(ruf, "SzentirasHuProvider")
    assert not hasattr(ruf, "ABibliaMindenkieProvider")
    assert not hasattr(ruf, "build_chapter_url")
    assert not hasattr(ruf, "extract_verse_data_json")
