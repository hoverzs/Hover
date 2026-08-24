"""Contract tests for production invariance around shadow hook."""

from __future__ import annotations

from textus_kb.shadow_integration import run_production_with_optional_shadow


def test_prompt_and_params_invariant_with_shadow_flag_toggle() -> None:
    calls: list[dict] = []

    def fake_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append(
            {
                "prompt": prompt,
                "enable_google_search": enable_google_search,
                "tab_label": tab_label,
            }
        )
        return "PROD"

    shadow_calls: list[dict] = []

    def fake_shadow_runner(**kwargs):
        shadow_calls.append(kwargs)
        return {"status": "success", "success": True}

    kwargs = {
        "key": "exegesis",
        "prompt": "PROMPT-X",
        "tab_label": "Exegézis",
        "use_search": False,
        "passage": "Jn 4,1-42",
        "generate_text_fn": fake_generate,
        "shadow_runner_fn": fake_shadow_runner,
    }
    off = run_production_with_optional_shadow(shadow_enabled=False, **kwargs)
    on = run_production_with_optional_shadow(shadow_enabled=True, **kwargs)

    assert off.production_output == "PROD"
    assert on.production_output == "PROD"
    assert calls == [
        {"prompt": "PROMPT-X", "enable_google_search": False, "tab_label": "Exegézis"},
        {"prompt": "PROMPT-X", "enable_google_search": False, "tab_label": "Exegézis"},
    ]
    assert off.shadow_event is None
    assert len(shadow_calls) == 1


def test_shadow_exception_isolated_and_production_survives() -> None:
    prod_calls = 0

    def fake_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        nonlocal prod_calls
        prod_calls += 1
        return "PROD-OK"

    def failing_shadow_runner(**kwargs):
        raise RuntimeError("shadow explode")

    result = run_production_with_optional_shadow(
        key="history",
        prompt="P",
        tab_label="Kortörténet",
        use_search=True,
        passage="Lk 10,25-37",
        shadow_enabled=True,
        generate_text_fn=fake_generate,
        shadow_runner_fn=failing_shadow_runner,
    )
    assert prod_calls == 1
    assert result.production_output == "PROD-OK"
    assert result.shadow_event is not None
    assert result.shadow_event["status"] == "error"
    assert "RuntimeError" in result.shadow_event["error"]


def test_shadow_disabled_zero_shadow_work() -> None:
    shadow_called = False

    def fake_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        return "PROD"

    def fake_shadow_runner(**kwargs):
        nonlocal shadow_called
        shadow_called = True
        return {"status": "success", "success": True}

    result = run_production_with_optional_shadow(
        key="exegesis",
        prompt="P",
        tab_label="Exegézis",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=False,
        generate_text_fn=fake_generate,
        shadow_runner_fn=fake_shadow_runner,
    )
    assert result.production_output == "PROD"
    assert result.shadow_event is None
    assert shadow_called is False

