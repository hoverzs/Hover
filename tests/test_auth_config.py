"""OAuth publikus URL / redirect biztonság."""

from __future__ import annotations

from auth_config import (
    DEFAULT_CLOUD_APP_URL,
    DEFAULT_LOCAL_APP_URL,
    is_localhost_url,
    is_local_runtime,
    oauth_redirect_uri_for,
    resolve_public_app_url,
    validate_oauth_redirect_safe,
)


def test_localhost_detection():
    assert is_localhost_url("http://localhost:8501/oauth2callback")
    assert is_localhost_url("http://127.0.0.1:8501/oauth2callback")
    assert not is_localhost_url("https://emmaus.streamlit.app/oauth2callback")


def test_resolve_local_vs_cloud_host():
    assert (
        resolve_public_app_url(secrets={}, host="localhost")
        == DEFAULT_LOCAL_APP_URL
    )
    assert (
        resolve_public_app_url(secrets={}, host="emmaus.streamlit.app")
        == "https://emmaus.streamlit.app"
    )


def test_configured_app_public_url_wins_on_local():
    secrets = {"TEXTUS_PUBLIC_URL": "http://localhost:8501"}
    assert (
        resolve_public_app_url(secrets=secrets, host="localhost")
        == "http://localhost:8501"
    )


def test_textus_public_url_preferred_over_app_public_url():
    secrets = {
        "TEXTUS_PUBLIC_URL": "https://emmaus.streamlit.app",
        "APP_PUBLIC_URL": "http://localhost:8501",
    }
    assert (
        resolve_public_app_url(secrets=secrets, host="emmaus.streamlit.app")
        == "https://emmaus.streamlit.app"
    )


def test_app_public_url_alias_still_works():
    secrets = {"APP_PUBLIC_URL": "https://emmaus.streamlit.app"}
    assert (
        resolve_public_app_url(secrets=secrets, host="localhost")
        == "https://emmaus.streamlit.app"
    )


def test_cloud_rejects_localhost_configured_url():
    secrets = {"TEXTUS_PUBLIC_URL": "http://localhost:8501"}
    url = resolve_public_app_url(secrets=secrets, host="emmaus.streamlit.app")
    assert url == "https://emmaus.streamlit.app"
    assert not is_localhost_url(url)


def test_oauth_callback_path():
    assert (
        oauth_redirect_uri_for(DEFAULT_CLOUD_APP_URL)
        == "https://emmaus.streamlit.app/oauth2callback"
    )
    assert (
        oauth_redirect_uri_for(DEFAULT_LOCAL_APP_URL)
        == "http://localhost:8501/oauth2callback"
    )


def test_validate_blocks_localhost_on_cloud_host():
    ok, msg = validate_oauth_redirect_safe(
        redirect_uri="http://localhost:8501/oauth2callback",
        host="emmaus.streamlit.app",
    )
    assert not ok
    assert "localhost" in msg.casefold() or "localhostra" in msg.casefold()


def test_validate_allows_localhost_on_local_host():
    ok, _msg = validate_oauth_redirect_safe(
        redirect_uri="http://localhost:8501/oauth2callback",
        host="localhost",
    )
    assert ok


def test_is_local_runtime_streamlit_app_host():
    assert not is_local_runtime(host="emmaus.streamlit.app")
    assert is_local_runtime(host="localhost")
