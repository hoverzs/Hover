"""Íróasztal dev-seed — csak teszt/dev, production no-op."""

from __future__ import annotations

from pathlib import Path

from workspace_data import sanitize_workspace_import_bytes
from writing_desk_data import WRITING_DESK_KEY
from writing_desk_dev_seed import (
    APPLIED_SESSION_KEY,
    DEV_SEED_FLAG,
    FIXTURE_PATH,
    apply_writing_desk_dev_seed,
    load_writing_desk_dev_workspace,
    maybe_apply_writing_desk_dev_seed,
)
from writing_desk_extracts import (
    STATUS_READY,
    WRITING_DESK_EXTRACT_KEYS,
    inspect_writing_desk_extract,
)


ROOT = Path(__file__).resolve().parents[1]


def test_dev_fixture_is_valid_workspace_import():
    raw = FIXTURE_PATH.read_bytes()
    report = sanitize_workspace_import_bytes(raw)
    assert report.rejected is False
    data = report.data
    assert data["_app"] == "Textus"
    assert data["last_igehely"] == "Lk 15,11–24"
    for key in ("original_text", "history", "theology"):
        assert len(str(data[key]).strip()) > 80
    extracts = data[WRITING_DESK_KEY]["extracts"]
    for key in WRITING_DESK_EXTRACT_KEYS:
        assert extracts[key]["content"] == ""
        assert extracts[key]["source_fingerprint"] == ""


def test_apply_seed_makes_all_three_extracts_ready_to_generate():
    session: dict = {}
    assert apply_writing_desk_dev_seed(session) is True
    payload = load_writing_desk_dev_workspace()
    assert session["original_text"] == payload["original_text"]
    assert session["history"] == payload["history"]
    assert session["theology"] == payload["theology"]
    for key in WRITING_DESK_EXTRACT_KEYS:
        view = inspect_writing_desk_extract(session, key)
        assert view.status == STATUS_READY
        assert view.content == ""


def test_second_apply_does_not_wipe_generated_extract():
    session: dict = {}
    apply_writing_desk_dev_seed(session)
    session[WRITING_DESK_KEY]["extracts"]["history"]["content"] = "Mentett kivonat."
    assert apply_writing_desk_dev_seed(session) is False
    assert session[WRITING_DESK_KEY]["extracts"]["history"]["content"] == "Mentett kivonat."


def test_maybe_apply_is_noop_without_env():
    session: dict = {"original_text": ""}
    assert maybe_apply_writing_desk_dev_seed(session, env={}, is_local=True) is False
    assert session.get("original_text") == ""
    assert APPLIED_SESSION_KEY not in session


def test_maybe_apply_is_noop_when_not_local():
    session: dict = {}
    assert maybe_apply_writing_desk_dev_seed(
        session,
        env={DEV_SEED_FLAG: "writing_desk"},
        is_local=False,
    ) is False
    assert "original_text" not in session


def test_maybe_apply_local_env_sets_writing_desk_mode():
    session: dict = {"ui_mode": "quick"}
    assert maybe_apply_writing_desk_dev_seed(
        session,
        env={DEV_SEED_FLAG: "writing_desk"},
        is_local=True,
    ) is True
    assert session["ui_mode"] == "writing_desk"
    assert inspect_writing_desk_extract(session, "theology").status == STATUS_READY


def test_dev_seed_is_not_in_production_ui():
    ui_src = (ROOT / "writing_desk_ui.py").read_text(encoding="utf-8")
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "TEXTUS_DEV_SEED" not in ui_src
    assert "dev-seed" not in ui_src
    assert "Kivonat készítése" in ui_src
    assert "maybe_apply_writing_desk_dev_seed(st.session_state)" in app_src
    seed_src = (ROOT / "writing_desk_dev_seed.py").read_text(encoding="utf-8")
    assert "from supabase" not in seed_src
    assert "import supabase" not in seed_src
