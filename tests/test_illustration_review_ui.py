from __future__ import annotations

import illustration_review_ui as m


def _prod(monkeypatch) -> None:
    """Simulate production: no local-dev signal true."""
    monkeypatch.delenv("TEXTUS_LOCAL_REVIEWER_ENABLED", raising=False)
    monkeypatch.setattr(m, "_is_local_dev_runtime", lambda: False)


def _localhost(monkeypatch) -> None:
    monkeypatch.setattr(m, "_is_local_dev_runtime", lambda: True)


def test_production_guest_is_not_authorized(monkeypatch) -> None:
    _prod(monkeypatch)
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_production_non_owner_is_not_authorized(monkeypatch) -> None:
    _prod(monkeypatch)
    assert m.is_authorized_reviewer(is_logged_in=True, email="someone@else.com") is False


def test_production_owner_is_authorized(monkeypatch) -> None:
    _prod(monkeypatch)
    assert m.is_authorized_reviewer(is_logged_in=True, email="hoverzsolt@gmail.com") is True


def test_localhost_with_flag_true_is_authorized(monkeypatch) -> None:
    _localhost(monkeypatch)
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is True


def test_localhost_with_flag_false_is_not_authorized(monkeypatch) -> None:
    _localhost(monkeypatch)
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "false")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_non_localhost_with_flag_true_is_not_authorized(monkeypatch) -> None:
    """The flag alone must never be sufficient -- requirement 2."""
    monkeypatch.setattr(m, "_is_local_dev_runtime", lambda: False)
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_local_dev_flag_alone_is_insufficient_without_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(m, "_is_local_dev_runtime", lambda: False)
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_explicit_local_dev_reviewer() is False


def test_local_runtime_alone_is_insufficient_without_flag(monkeypatch) -> None:
    _localhost(monkeypatch)
    monkeypatch.delenv("TEXTUS_LOCAL_REVIEWER_ENABLED", raising=False)
    assert m.is_explicit_local_dev_reviewer() is False
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_env_flag_truthy_values_whitespace_and_case_insensitive(monkeypatch) -> None:
    _localhost(monkeypatch)
    for raw in ("true", "  true  ", "True", "TRUE", "1", "yes", "YES", " Yes "):
        monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", raw)
        assert m.is_explicit_local_dev_reviewer() is True, repr(raw)


def test_env_flag_falsy_or_garbage_values_rejected(monkeypatch) -> None:
    _localhost(monkeypatch)
    for raw in ("false", "0", "no", "", "   ", "maybe", "yesplease", "TRUEX"):
        monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", raw)
        assert m.is_explicit_local_dev_reviewer() is False, repr(raw)


def test_env_flag_unset_is_falsy(monkeypatch) -> None:
    _localhost(monkeypatch)
    monkeypatch.delenv("TEXTUS_LOCAL_REVIEWER_ENABLED", raising=False)
    assert m.is_explicit_local_dev_reviewer() is False


def test_owner_email_case_and_whitespace_insensitive(monkeypatch) -> None:
    _prod(monkeypatch)
    assert m.is_authorized_reviewer(is_logged_in=True, email="  HoverZsolt@Gmail.COM  ") is True


def test_owner_email_without_login_flag_is_not_authorized(monkeypatch) -> None:
    """A matching email string alone (not logged in) must not authorize --
    is_logged_in is a required, independent condition."""
    _prod(monkeypatch)
    assert m.is_authorized_reviewer(is_logged_in=False, email="hoverzsolt@gmail.com") is False


def test_is_authenticated_owner_matches_is_authorized_reviewer_production_path(monkeypatch) -> None:
    _prod(monkeypatch)
    assert m.is_authenticated_owner(is_logged_in=True, email="hoverzsolt@gmail.com") is True
    assert m.is_authenticated_owner(is_logged_in=False, email="hoverzsolt@gmail.com") is False
    assert m.is_authenticated_owner(is_logged_in=True, email="other@x.com") is False


# ---------------------------------------------------------------------------
# Strict loopback-only host check (security hardening): the reviewer
# bypass must NOT inherit auth_config.is_local_runtime()'s wider
# "192.168.*/10.* counts as local" concept -- a cloud/container internal
# address can easily fall in those ranges. These tests exercise the
# REAL host-classification logic (not a blanket _is_local_dev_runtime
# mock) by faking auth_config.request_host(), the same function
# _is_local_dev_runtime() itself calls.
# ---------------------------------------------------------------------------


def _set_request_host(monkeypatch, host: str) -> None:
    import auth_config

    monkeypatch.setattr(auth_config, "request_host", lambda: host)


def test_strict_loopback_host_classifier() -> None:
    assert m._is_strict_loopback_host("localhost") is True
    assert m._is_strict_loopback_host("127.0.0.1") is True
    assert m._is_strict_loopback_host("::1") is True
    assert m._is_strict_loopback_host("LOCALHOST") is True
    assert m._is_strict_loopback_host("  localhost  ") is True
    assert m._is_strict_loopback_host("10.0.0.5") is False
    assert m._is_strict_loopback_host("192.168.1.20") is False
    assert m._is_strict_loopback_host("emmaus.streamlit.app") is False
    assert m._is_strict_loopback_host(None) is False
    assert m._is_strict_loopback_host("") is False


def test_localhost_host_with_flag_true_is_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "localhost")
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is True


def test_127_0_0_1_host_with_flag_true_is_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "127.0.0.1")
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is True


def test_localhost_host_with_flag_false_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "localhost")
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "false")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_10_x_network_host_with_flag_true_is_not_authorized(monkeypatch) -> None:
    """10.* must NOT count as local for the reviewer bypass, even though
    auth_config.is_local_runtime() treats it as local for OAuth purposes."""
    _set_request_host(monkeypatch, "10.0.0.5")
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_192_168_network_host_with_flag_true_is_not_authorized(monkeypatch) -> None:
    """192.168.* must NOT count as local for the reviewer bypass, even
    though auth_config.is_local_runtime() treats it as local for OAuth
    purposes."""
    _set_request_host(monkeypatch, "192.168.1.20")
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_cloud_host_with_flag_true_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_empty_or_unavailable_host_with_flag_true_is_not_authorized(monkeypatch) -> None:
    """Unlike auth_config.is_local_runtime() (which defaults an unknown
    host to "local" for its OAuth-redirect use case), the reviewer
    bypass must fail CLOSED on an unknown host."""
    _set_request_host(monkeypatch, "")
    monkeypatch.setenv("TEXTUS_LOCAL_REVIEWER_ENABLED", "true")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_auth_config_is_local_runtime_itself_untouched() -> None:
    """This module must never modify or wrap auth_config.is_local_runtime --
    it only reads auth_config.request_host() and applies its own,
    stricter allowlist. Sanity check that the real function still exists
    and is not monkeypatched/shadowed by importing this module."""
    import auth_config
    import inspect

    assert callable(auth_config.is_local_runtime)
    assert "192.168." in inspect.getsource(auth_config.is_local_runtime)
