from __future__ import annotations

import illustration_review_ui as m


def _set_request_host(monkeypatch, host: str) -> None:
    import auth_config

    monkeypatch.setattr(auth_config, "request_host", lambda: host)


# ---------------------------------------------------------------------------
# authorized_reviewer = strict_loopback_host OR authenticated_owner
# ---------------------------------------------------------------------------


def test_localhost_guest_is_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "localhost")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is True


def test_127_0_0_1_guest_is_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "127.0.0.1")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is True


def test_ipv6_loopback_guest_is_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "::1")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is True


def test_10_x_guest_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "10.0.0.5")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_192_168_x_guest_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "192.168.1.20")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_172_16_31_range_guest_is_not_authorized(monkeypatch) -> None:
    for host in ("172.16.0.5", "172.20.5.5", "172.31.255.255"):
        _set_request_host(monkeypatch, host)
        assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False, host


def test_cloud_guest_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_cloud_non_owner_login_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=True, email="someone@else.com") is False


def test_cloud_owner_login_is_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=True, email="hoverzsolt@gmail.com") is True


def test_empty_or_unavailable_host_is_not_authorized_for_guest(monkeypatch) -> None:
    """Unlike auth_config.is_local_runtime() (which defaults an unknown
    host to "local" for its own OAuth-redirect use case), the reviewer
    loopback check must fail CLOSED on an unknown host."""
    _set_request_host(monkeypatch, "")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


# ---------------------------------------------------------------------------
# Production owner path (unchanged by the loopback simplification)
# ---------------------------------------------------------------------------


def test_production_guest_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False


def test_production_non_owner_is_not_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=True, email="someone@else.com") is False


def test_production_owner_is_authorized(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=True, email="hoverzsolt@gmail.com") is True


def test_owner_email_case_and_whitespace_insensitive(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=True, email="  HoverZsolt@Gmail.COM  ") is True


def test_owner_email_without_login_flag_is_not_authorized(monkeypatch) -> None:
    """A matching email string alone (not logged in) must not authorize --
    is_logged_in is a required, independent condition."""
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_authorized_reviewer(is_logged_in=False, email="hoverzsolt@gmail.com") is False


def test_is_authenticated_owner_standalone() -> None:
    assert m.is_authenticated_owner(is_logged_in=True, email="hoverzsolt@gmail.com") is True
    assert m.is_authenticated_owner(is_logged_in=False, email="hoverzsolt@gmail.com") is False
    assert m.is_authenticated_owner(is_logged_in=True, email="other@x.com") is False


# ---------------------------------------------------------------------------
# Strict loopback host classifier
# ---------------------------------------------------------------------------


def test_strict_loopback_host_classifier() -> None:
    assert m._is_strict_loopback_host("localhost") is True
    assert m._is_strict_loopback_host("127.0.0.1") is True
    assert m._is_strict_loopback_host("::1") is True
    assert m._is_strict_loopback_host("LOCALHOST") is True
    assert m._is_strict_loopback_host("  localhost  ") is True
    assert m._is_strict_loopback_host("10.0.0.5") is False
    assert m._is_strict_loopback_host("192.168.1.20") is False
    assert m._is_strict_loopback_host("172.16.0.5") is False
    assert m._is_strict_loopback_host("emmaus.streamlit.app") is False
    assert m._is_strict_loopback_host(None) is False
    assert m._is_strict_loopback_host("") is False


def test_is_local_loopback_request_matches_classifier(monkeypatch) -> None:
    _set_request_host(monkeypatch, "localhost")
    assert m.is_local_loopback_request() is True
    _set_request_host(monkeypatch, "10.0.0.5")
    assert m.is_local_loopback_request() is False


# ---------------------------------------------------------------------------
# Production safety: loopback bypass cannot activate on a non-loopback host
# ---------------------------------------------------------------------------


def test_loopback_bypass_never_activates_on_cloud_host_regardless_of_login(monkeypatch) -> None:
    _set_request_host(monkeypatch, "emmaus.streamlit.app")
    assert m.is_local_loopback_request() is False
    # Even with a login present but wrong email, and even with no login at
    # all, the ONLY way to pass on this host is is_authenticated_owner.
    assert m.is_authorized_reviewer(is_logged_in=False, email=None) is False
    assert m.is_authorized_reviewer(is_logged_in=True, email="someone@else.com") is False
    assert m.is_authorized_reviewer(is_logged_in=True, email="hoverzsolt@gmail.com") is True


def test_auth_config_is_local_runtime_itself_untouched() -> None:
    """This module must never modify or wrap auth_config.is_local_runtime --
    it only reads auth_config.request_host() and applies its own,
    stricter allowlist. Sanity check that the real function still exists
    and is not monkeypatched/shadowed by importing this module."""
    import inspect

    import auth_config

    assert callable(auth_config.is_local_runtime)
    assert "192.168." in inspect.getsource(auth_config.is_local_runtime)
