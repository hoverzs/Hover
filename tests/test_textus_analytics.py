"""GA4 analytics module — sanitization, dedupe, config."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textus_analytics import (  # noqa: E402
    DEFAULT_GA_MEASUREMENT_ID,
    SECRET_KEY,
    begin_analytics_run,
    feature_name_from_label,
    get_measurement_id,
    sanitize_event_params,
    track_event,
    track_page_view,
)


def test_default_measurement_id(monkeypatch):
    monkeypatch.delenv(SECRET_KEY, raising=False)

    class _Secrets(dict):
        def get(self, key, default=None):  # noqa: A003
            return default

    mock_st = MagicMock()
    mock_st.secrets = _Secrets()
    with patch.dict("sys.modules", {"streamlit": mock_st}):
        assert get_measurement_id() == DEFAULT_GA_MEASUREMENT_ID


def test_env_overrides_measurement_id(monkeypatch):
    monkeypatch.setenv(SECRET_KEY, "G-TESTID123")
    assert get_measurement_id() == "G-TESTID123"


def test_sanitize_drops_email_and_unknown_keys():
    cleaned = sanitize_event_params(
        {
            "module_name": "workshop",
            "feature_name": "exegesis",
            "email": "a@b.com",
            "user_id": "u1",
            "prompt": "titkos",
            "method": "gemini",
            "status": "ok",
            "file_format": "docx",
            "error_code": "http_429",
            "passage": "Jn 3,16",
        }
    )
    assert cleaned == {
        "module_name": "workshop",
        "feature_name": "exegesis",
        "method": "gemini",
        "status": "ok",
        "file_format": "docx",
        "error_code": "http_429",
    }
    assert "email" not in cleaned
    assert "prompt" not in cleaned
    assert "passage" not in cleaned


def test_feature_name_slug():
    assert feature_name_from_label("Eredeti szöveg tanulmányozása").startswith("eredeti")


def test_page_view_dedupes_within_session():
    ss: dict = {}
    mock_st = MagicMock()
    mock_st.session_state = ss
    with (
        patch("textus_analytics._inject_js") as inject,
        patch.dict("sys.modules", {"streamlit": mock_st}),
        patch("textus_analytics._session", return_value=ss),
    ):
        begin_analytics_run()
        track_page_view("Gyorseszközök", "/quick")
        track_page_view("Gyorseszközök", "/quick")
        track_page_view("Textusműhely", "/workshop")
        assert inject.call_count >= 2  # boot + at least one pv, second pv same skipped
        # Exact: first pv + second different pv (+ maybe boot)
        paths = [
            c.kwargs.get("element_id") or (c.args[1] if len(c.args) > 1 else "")
            for c in inject.call_args_list
        ]
        assert any("textus-ga-pv" in str(p) for p in paths)


def test_event_dedupes_same_run_only():
    ss: dict = {"_textus_ga_run_counter": 0}
    with (
        patch("textus_analytics._inject_js") as inject,
        patch("textus_analytics._session", return_value=ss),
        patch("textus_analytics.init_analytics"),
    ):
        begin_analytics_run()
        track_event("login", {"method": "google"})
        track_event("login", {"method": "google"})  # same run → once
        assert inject.call_count == 1
        begin_analytics_run()
        track_event("login", {"method": "google"})  # new run → again
        assert inject.call_count == 2


def test_track_helpers_never_raise():
    with patch("textus_analytics._inject_js", side_effect=RuntimeError("boom")):
        track_page_view("X", "/x")
        track_event("login", {"method": "google"})
