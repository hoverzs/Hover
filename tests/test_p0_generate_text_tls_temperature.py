# ruff: noqa: E402
"""P0: TLS-ellenőrzés + explicit temperature a generate_text signature-ben."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_build_payload_uses_explicit_temperature_over_session():
    import app as app_mod

    with patch.object(app_mod, "st") as st_mock:
        st_mock.session_state = {"temperature": 0.9}
        payload = app_mod._build_payload(
            "próba",
            False,
            "gemini-2.5-flash",
            temperature=0.15,
        )
    assert payload["generationConfig"]["temperature"] == 0.15


def test_build_payload_falls_back_to_session_temperature():
    import app as app_mod

    with patch.object(app_mod, "st") as st_mock:
        st_mock.session_state = {"temperature": 0.45}
        payload = app_mod._build_payload(
            "próba",
            False,
            "gemini-2.5-flash",
        )
    assert payload["generationConfig"]["temperature"] == 0.45


def test_generate_text_signature_accepts_temperature():
    import app as app_mod

    sig = inspect.signature(app_mod.generate_text)
    assert "temperature" in sig.parameters
    param = sig.parameters["temperature"]
    assert param.default is None
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_outline_diagnostics_compatible_with_real_generate_text_signature():
    """A diagnosztika temperature=… hívása ne okozzon TypeError-t a valódi signature-rel."""
    import app as app_mod
    from sermon_outline_diagnostics_ai import (
        DEFAULT_TEMPERATURE,
        run_outline_diagnostics,
    )

    sig = inspect.signature(app_mod.generate_text)
    captured: dict = {}

    def fake_generate(prompt, enable_google_search: bool = False, **kwargs):
        # Ugyanaz a keyword-only szerződés, mint app.generate_text
        bound = sig.bind_partial(prompt, enable_google_search, **kwargs)
        bound.apply_defaults()
        captured.update(dict(bound.arguments))
        return json.dumps(
            {
                "ok": True,
                "mode": "full",
                "overview": "A vázlat textusközpontú és követhető.",
                "overall_score": 8,
                "strengths": ["Világos fókusz"],
                "refinements": [],
                "scores": {},
            },
            ensure_ascii=False,
        )

    # bind_partial + apply_defaults ellenőrzi, hogy temperature elfogadott
    result = run_outline_diagnostics(
        sermon_outline={
            "main_idea": "Isten megtart a gúny közepette.",
            "passage_reference": "Júd 17–20",
            "opening_direction": "A gúny hangja körülöttünk erősödik.",
            "movements": [
                {
                    "title": "Emlékezet",
                    "development": ["Apostoli szavakra emlékezés."],
                },
                {
                    "title": "Megmaradás",
                    "development": ["Hitben épülés a Lélekben."],
                },
            ],
            "conclusion": {"development": "Isten szeretete megtart."},
        },
        generate_fn=fake_generate,
    )
    assert result.ok or result.mode in {"full", "partial", "parse_error", "api_error"}
    assert "temperature" in captured
    assert captured["temperature"] == DEFAULT_TEMPERATURE


def test_gemini_http_request_does_not_disable_tls_verification():
    import app as app_mod

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = '{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": "ok válasz"}]}}
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Resp()

    with patch.object(app_mod, "st") as st_mock, patch.object(
        app_mod.requests, "post", side_effect=fake_post
    ), patch.object(app_mod, "_resolve_api_key", return_value="test-key"), patch.object(
        app_mod, "resolve_gemini_model_for_tab", return_value="gemini-2.5-flash"
    ), patch.object(app_mod, "_cooldown_remaining", return_value=0.0), patch.object(
        app_mod, "_debug_log_append", MagicMock()
    ):
        st_mock.session_state = {
            "temperature": 0.3,
            "enable_cache": False,
            "_call_cache": {},
            "_last_api_call_ts": 0,
            "_debug_log": [],
        }
        text = app_mod.generate_text(
            "rövid próba",
            enable_google_search=False,
            tab_label="Teszt",
            use_cache=False,
            temperature=0.15,
        )

    assert "ok" in text.casefold() or "válasz" in text.casefold() or text
    assert "verify" not in captured["kwargs"] or captured["kwargs"].get("verify") is not False
    assert captured["kwargs"].get("verify") is not False
    # Explicit: soha ne legyen verify=False
    assert captured["kwargs"].get("verify", True) is not False


def test_no_urllib3_insecure_warning_suppression_in_app_source():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "disable_warnings" not in src
    assert "InsecureRequestWarning" not in src
    assert "verify=False" not in src


def test_effective_temperature_affects_cache_key_material():
    """Az explicit hőmérséklet része a cache-kulcsnak (különböző temp → külön hash)."""
    import app as app_mod

    extras: list[str] = []
    real_hash = app_mod._hash_prompt

    def capture_hash(prompt, extra=""):
        if extra and "gemini" in str(extra):
            extras.append(str(extra))
        return real_hash(prompt, extra=extra)

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": f"válasz-{len(extras)}"}]}}
                ]
            }

    with patch.object(app_mod, "st") as st_mock, patch.object(
        app_mod.requests, "post", return_value=_Resp()
    ), patch.object(app_mod, "_resolve_api_key", return_value="test-key"), patch.object(
        app_mod, "resolve_gemini_model_for_tab", return_value="gemini-2.5-flash"
    ), patch.object(app_mod, "_cooldown_remaining", return_value=0.0), patch.object(
        app_mod, "_debug_log_append", MagicMock()
    ), patch.object(app_mod, "_hash_prompt", side_effect=capture_hash):
        st_mock.session_state = {
            "temperature": 0.3,
            "enable_cache": True,
            "_call_cache": {},
            "_last_api_call_ts": 0,
            "_debug_log": [],
        }
        app_mod.generate_text("azonos prompt", use_cache=True, temperature=0.1)
        app_mod.generate_text("azonos prompt", use_cache=True, temperature=0.9)

    assert len(extras) >= 2
    assert extras[0] != extras[1]
    assert "0.1" in extras[0]
    assert "0.9" in extras[1]
