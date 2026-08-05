from __future__ import annotations

import pytest

import supabase_client


@pytest.fixture(autouse=True)
def _clear_supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setattr(supabase_client, "_SECRETS_PATH", supabase_client._SECRETS_PATH.parent / "does-not-exist.toml")


def test_env_fallback_wins_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://env.example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "env-key")

    url, key = supabase_client._load_supabase_secrets()

    assert url == "https://env.example.supabase.co"
    assert key == "env-key"


def test_project_secrets_file_fallback_used_when_no_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    secrets_file = tmp_path / "secrets.toml"
    secrets_file.write_text(
        '[supabase]\nurl = "https://file.example.supabase.co"\nkey = "file-key"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(supabase_client, "_SECRETS_PATH", secrets_file)

    url, key = supabase_client._load_supabase_secrets()

    assert url == "https://file.example.supabase.co"
    assert key == "file-key"


def test_streamlit_secrets_fallback_used_when_no_env_and_no_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSecrets(dict):
        def get(self, key, default=None):  # type: ignore[override]
            return dict.get(self, key, default)

    fake_secrets = _FakeSecrets(
        {"supabase": {"url": "https://st.example.supabase.co", "key": "st-key"}}
    )

    import streamlit as st

    monkeypatch.setattr(st, "secrets", fake_secrets)

    url, key = supabase_client._load_supabase_secrets()

    assert url == "https://st.example.supabase.co"
    assert key == "st-key"


def test_missing_everywhere_raises_with_all_three_sources_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit as st

    monkeypatch.setattr(st, "secrets", {})

    with pytest.raises(RuntimeError) as excinfo:
        supabase_client._load_supabase_secrets()

    message = str(excinfo.value)
    assert "SUPABASE_URL" in message
    assert "SUPABASE_KEY" in message
    assert "secrets.toml" in message
    assert "st.secrets" in message
