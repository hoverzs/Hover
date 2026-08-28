from __future__ import annotations

import illustration_review_ui as m
from illustration_engine.illustration_unit_repository import IllustrationReviewItem


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


# ---------------------------------------------------------------------------
# Phase 3G-B2: reviewer-side risk triage / legacy-strategy mismatch
# ---------------------------------------------------------------------------


def _make_review_item(*, original_text_length: int, derivation_type: str, **overrides) -> IllustrationReviewItem:
    fields = dict(
        unit_id=1,
        story_id=1,
        unit_index=1,
        status="needs_review",
        derivation_type=derivation_type,
        title_hu="Cím",
        modern_hu_text="Rövid szöveg.",
        summary_hu="Összefoglaló.",
        moral_hu="Tanulság.",
        narrative_status="fable",
        narrative_status_confidence="high",
        human_reviewed_at=None,
        enrichment_model="claude-sonnet-5",
        enrichment_prompt_version="v1",
        enrichment_generated_at="2026-08-27T00:00:00+00:00",
        enrichment_warnings=(),
        qa_status=None,
        qa_model=None,
        qa_prompt_version=None,
        qa_checked_at=None,
        qa_confidence=None,
        qa_issues_json=None,
        title_original="Original Title",
        original_text="x" * original_text_length,
        source_reference="p. 1",
        source_code="SRC",
        source_title="Test Source",
        tradition=None,
        license_status="public_domain_confirmed",
        source_url=None,
        topics=("eszesseg",),
        tone="humoros",
        homiletic_functions=("szemlelteto_pelda",),
    )
    fields.update(overrides)
    return IllustrationReviewItem(**fields)


# --- _is_legacy_strategy_mismatch: direct_unit band (length <= 1500) -------


def test_short_source_full_story_translation_no_mismatch() -> None:
    item = _make_review_item(original_text_length=500, derivation_type="full_story_translation")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is False
    assert risk.current_expected_mode == "direct_unit"
    assert risk.current_expected_derivation_type == "full_story_translation"


def test_short_source_condensed_story_is_mismatch() -> None:
    item = _make_review_item(original_text_length=500, derivation_type="condensed_story")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is True


# --- _is_legacy_strategy_mismatch: direct_unit band (1501-3000) ------------


def test_medium_source_condensed_story_no_mismatch() -> None:
    item = _make_review_item(original_text_length=2000, derivation_type="condensed_story")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is False
    assert risk.current_expected_mode == "direct_unit"
    assert risk.current_expected_derivation_type == "condensed_story"


def test_medium_source_full_story_translation_is_mismatch() -> None:
    item = _make_review_item(original_text_length=2000, derivation_type="full_story_translation")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is True


# --- _is_legacy_strategy_mismatch: unit_proposal band (length > 3000) ------


def test_long_source_full_story_translation_is_mismatch() -> None:
    """The exact Alfred regression shape: >3000 chars, stored as
    full_story_translation -- today's pipeline would require unit_proposal."""
    item = _make_review_item(original_text_length=3200, derivation_type="full_story_translation")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is True
    assert risk.current_expected_mode == "unit_proposal"
    assert risk.current_expected_derivation_type is None
    assert any("unit_proposal" in r for r in risk.reasons)
    assert risk.level == "high"


def test_long_source_condensed_story_is_mismatch() -> None:
    item = _make_review_item(original_text_length=3200, derivation_type="condensed_story")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is True


def test_long_source_extracted_scene_is_not_mismatch() -> None:
    """extracted_scene is itself proposal-derived content -- the correct,
    modern shape for a long story -- so it must NOT be flagged as a
    legacy mismatch just because the story is long."""
    item = _make_review_item(original_text_length=3200, derivation_type="extracted_scene")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is False


# --- compute_review_risk: individual HIGH-priority criteria ----------------


def test_clean_short_unit_is_normal_risk() -> None:
    item = _make_review_item(original_text_length=500, derivation_type="full_story_translation")
    risk = m.compute_review_risk(item)
    assert risk.level == "normal"
    assert risk.reasons == ()


def test_enrichment_warnings_present_is_high_risk() -> None:
    item = _make_review_item(
        original_text_length=500, derivation_type="full_story_translation", enrichment_warnings=("finding",)
    )
    risk = m.compute_review_risk(item)
    assert risk.level == "high"
    assert any("warning" in r for r in risk.reasons)


def test_long_source_over_1500_is_high_risk_even_without_mismatch() -> None:
    """Source length > 1500 is its OWN high-priority criterion, independent
    of the legacy-mismatch check (a correctly-strategized condensed_story
    in the 1501-3000 band is still flagged for its length alone)."""
    item = _make_review_item(original_text_length=2000, derivation_type="condensed_story")
    risk = m.compute_review_risk(item)
    assert risk.is_legacy_mismatch is False
    assert risk.level == "high"
    assert any("1500" in r for r in risk.reasons)


def test_low_confidence_is_high_risk() -> None:
    item = _make_review_item(
        original_text_length=500, derivation_type="full_story_translation", narrative_status_confidence="low"
    )
    risk = m.compute_review_risk(item)
    assert risk.level == "high"
    assert any("confidence" in r for r in risk.reasons)


def test_long_modern_hu_text_is_high_risk() -> None:
    item = _make_review_item(
        original_text_length=500, derivation_type="full_story_translation", modern_hu_text="y" * 1600
    )
    risk = m.compute_review_risk(item)
    assert risk.level == "high"
    assert any("modern_hu_text" in r for r in risk.reasons)


def test_condensed_or_extracted_derivation_type_is_high_risk() -> None:
    item = _make_review_item(original_text_length=2000, derivation_type="condensed_story")
    risk = m.compute_review_risk(item)
    assert any("proposal/condensed" in r for r in risk.reasons)

    item2 = _make_review_item(original_text_length=3200, derivation_type="extracted_scene")
    risk2 = m.compute_review_risk(item2)
    assert risk2.is_legacy_mismatch is False
    assert risk2.level == "high"
    assert any("proposal/condensed" in r for r in risk2.reasons)
