"""Production combined-build CLI tests for ``scripts/build_commentary_database.py``.

Two groups:
  - Real, gated end-to-end tests (skipped unless all three raw corpora are
    present locally) that exercise the actual ``--combined``/``--qa`` CLI
    path against the real Calvin + JFB + Henry sources.
  - Fully offline, monkeypatched tests of the fail-closed/atomic behavior
    (missing raw files, import failure, post-build sanity-check failure,
    fetch failure) that run in every environment regardless of whether the
    raw corpora have been fetched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.build_commentary_database as build_mod
from textus_kb import commentary_runtime
from textus_kb.importers.calvin_source_fetch import (
    CalvinSourceEntry,
    CalvinSourceFetchError,
    load_source_manifest as load_calvin_manifest,
)
from textus_kb.importers.henry_source_fetch import (
    HenrySourceManifest,
    HenryVolumeFile,
    load_source_manifest as load_henry_manifest,
)
from textus_kb.importers.jfb_source_fetch import (
    JfbSourceFile,
    JfbSourceManifest,
    load_source_manifest as load_jfb_manifest,
)
from textus_kb.repositories.commentary_repository import CommentaryRepository

# Locked in from the Henry-corpus round's real combined build (also
# reproduced by test_combined_calvin_jfb_henry_commentary.py): the exact
# content_hash of the full Calvin + JFB + Henry document. content_hash is
# purely content-derived (imported_at never affects it), so this stays a
# valid fixed expectation across CLI invocations at different times.
_KNOWN_COMBINED_CONTENT_HASH = (
    "d02276993c03bf0f91b103f2ec097c0ba1f5b556d13bb7a50f115fb35ae96f5a"
)

_CALVIN_ENTRIES = load_calvin_manifest()
_JFB_MANIFEST = load_jfb_manifest()
_HENRY_MANIFEST = load_henry_manifest()
_ALL_RAW_PRESENT = (
    all(entry.local_path.is_file() for entry in _CALVIN_ENTRIES)
    and _JFB_MANIFEST.source.local_path.is_file()
    and all(v.local_path.is_file() for v in _HENRY_MANIFEST.volumes)
)

_requires_raw_sources = pytest.mark.skipif(
    not _ALL_RAW_PRESENT,
    reason=(
        "Full Calvin/JFB/Henry raw sources not present locally. See "
        "test_combined_calvin_jfb_henry_commentary.py for fetch instructions."
    ),
)


def _fake_manifests(tmp_path: Path) -> tuple[list, JfbSourceManifest, HenrySourceManifest]:
    """Minimal, valid manifest objects whose local_path files DO exist on
    disk (empty placeholders) -- used to pass the pre-import missing-file
    check without touching the real, large raw corpora."""
    calvin_path = tmp_path / "calvin_stub.xml"
    calvin_path.write_text("<x/>", encoding="utf-8")
    jfb_path = tmp_path / "jfb_stub.xml"
    jfb_path.write_text("<x/>", encoding="utf-8")
    henry_path = tmp_path / "henry_stub.xml"
    henry_path.write_text("<x/>", encoding="utf-8")

    calvin_entries = [
        CalvinSourceEntry(
            id="stub",
            title="Stub",
            url="https://example.test/stub.xml",
            local_path=calvin_path,
            raw_sha256="0" * 64,
            byte_size=4,
            work_group="stub",
            work_title="Stub",
            volume=None,
            coverage="",
            translator="",
            known_unmapped_sections=(),
        )
    ]
    jfb_manifest = JfbSourceManifest(
        manifest_version="1",
        description="",
        source=JfbSourceFile(
            id="stub",
            title="Stub",
            url="https://example.test/stub.xml",
            local_path=jfb_path,
            raw_sha256="0" * 64,
            byte_size=4,
        ),
        books=(),
    )
    henry_manifest = HenrySourceManifest(
        manifest_version="1",
        description="",
        volumes=(
            HenryVolumeFile(
                volume=1,
                title="Stub",
                url="https://example.test/stub.xml",
                local_path=henry_path,
                raw_sha256="0" * 64,
                byte_size=4,
            ),
        ),
        books=(),
    )
    return calvin_entries, jfb_manifest, henry_manifest


def _patch_manifests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calvin_entries, jfb_manifest, henry_manifest = _fake_manifests(tmp_path)
    monkeypatch.setattr(build_mod, "load_calvin_manifest", lambda: calvin_entries)
    monkeypatch.setattr(build_mod, "load_jfb_manifest", lambda: jfb_manifest)
    monkeypatch.setattr(build_mod, "load_henry_manifest", lambda: henry_manifest)


# --- Real, gated end-to-end CLI tests (one shared build for the group) --


@pytest.fixture(scope="module")
def _combined_cli_build(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict]:
    if not _ALL_RAW_PRESENT:
        pytest.skip(
            "Full Calvin/JFB/Henry raw sources not present locally. See "
            "test_combined_calvin_jfb_henry_commentary.py for fetch instructions."
        )
    import subprocess
    import sys

    output = tmp_path_factory.mktemp("combined_cli_build") / "commentary.sqlite3"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_commentary_database.py",
            "--combined",
            "--output",
            str(output),
            "--qa",
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    return output, payload


@_requires_raw_sources
def test_combined_cli_builds_production_store_with_qa(
    _combined_cli_build: tuple[Path, dict],
) -> None:
    output, payload = _combined_cli_build

    assert payload["content_hash"] == _KNOWN_COMBINED_CONTENT_HASH
    assert payload["work_count"] == 23 + 66 + 66
    assert payload["edition_count"] == 45 + 66 + 66
    assert payload["contributor_count"] == 9 + 3 + 15
    assert payload["section_count"] == 14643 + 32394 + 5579
    assert payload["chunk_count"] == 11785 + 21071 + 5512
    assert payload["passage_link_count"] == 14153 + 31097 + 4258
    assert payload["runtime_status"]["available"] is True

    assert payload["qa"]["available"] is True
    assert len(payload["qa"]["known_unmapped"]) == 10
    assert payload["qa"]["parallel_passage_link_count"] == 354

    # No leftover staging file next to the real output.
    leftovers = list(output.parent.glob(f".{output.stem}.combined-build.*"))
    assert leftovers == []


@_requires_raw_sources
def test_commentary_runtime_available_after_combined_build(
    _combined_cli_build: tuple[Path, dict],
) -> None:
    output, _payload = _combined_cli_build
    status = commentary_runtime.get_status(output)
    assert status.available is True
    assert status.reason == "ok"


@_requires_raw_sources
def test_combined_cli_three_source_passage_retrieval(
    _combined_cli_build: tuple[Path, dict],
) -> None:
    output, _payload = _combined_cli_build
    repo = CommentaryRepository(output)
    hits = repo.sections_for_passage("Romans.1.1")
    work_ids = {h.work_id for h in hits}
    assert any(w.startswith("ccel.calvin") for w in work_ids)
    assert any(w.startswith("ccel.jfb") for w in work_ids)
    assert any(w.startswith("ccel.henry") for w in work_ids)


# --- Offline, monkeypatched fail-closed / atomicity tests ----------------


def test_combined_missing_raw_files_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --combined-fetch, missing raw files must be listed clearly
    and the build must refuse (never build a silently partial store)."""
    calvin_entries, jfb_manifest, henry_manifest = _fake_manifests(tmp_path)
    # Point every path at a file that does NOT exist.
    calvin_entries[0] = CalvinSourceEntry(
        **{**calvin_entries[0].__dict__, "local_path": tmp_path / "does_not_exist_calvin.xml"}
    )
    jfb_manifest = JfbSourceManifest(
        manifest_version=jfb_manifest.manifest_version,
        description=jfb_manifest.description,
        source=JfbSourceFile(
            **{**jfb_manifest.source.__dict__, "local_path": tmp_path / "does_not_exist_jfb.xml"}
        ),
        books=jfb_manifest.books,
    )
    henry_manifest = HenrySourceManifest(
        manifest_version=henry_manifest.manifest_version,
        description=henry_manifest.description,
        volumes=(
            HenryVolumeFile(
                **{
                    **henry_manifest.volumes[0].__dict__,
                    "local_path": tmp_path / "does_not_exist_henry.xml",
                }
            ),
        ),
        books=henry_manifest.books,
    )
    monkeypatch.setattr(build_mod, "load_calvin_manifest", lambda: calvin_entries)
    monkeypatch.setattr(build_mod, "load_jfb_manifest", lambda: jfb_manifest)
    monkeypatch.setattr(build_mod, "load_henry_manifest", lambda: henry_manifest)

    output = tmp_path / "commentary.sqlite3"
    exit_code = build_mod.main(["--combined", "--output", str(output)])
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "Missing raw source file(s)" in err
    assert "does_not_exist_calvin.xml" in err
    assert "does_not_exist_jfb.xml" in err
    assert "does_not_exist_henry.xml" in err
    assert not output.exists()


def test_combined_import_failure_leaves_output_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_manifests(monkeypatch, tmp_path)

    def _boom(**kwargs):
        raise build_mod.CombinedCommentaryImportError("synthetic failure")

    monkeypatch.setattr(build_mod, "import_combined_commentary_corpus", _boom)

    output = tmp_path / "commentary.sqlite3"
    exit_code = build_mod.main(["--combined", "--output", str(output)])
    assert exit_code == 1
    assert "synthetic failure" in capsys.readouterr().err
    assert not output.exists()
    assert list(tmp_path.glob(f".{output.stem}.combined-build.*")) == []


def test_combined_post_build_sanity_check_failure_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Even if the import itself "succeeds", a post-move
    commentary_runtime.get_status() that reports unavailable must still
    fail the build -- an extra fail-closed safety net, not just trust in
    the importer's own return value."""
    _patch_manifests(monkeypatch, tmp_path)

    def _fake_import(*, database_path, **kwargs):
        return build_mod.create_empty_commentary_database(database_path)

    monkeypatch.setattr(build_mod, "import_combined_commentary_corpus", _fake_import)

    class _FakeStatus:
        available = False
        reason = "schema_incompatible"
        detail = "synthetic mismatch"

    monkeypatch.setattr(build_mod.commentary_runtime, "get_status", lambda path: _FakeStatus())

    output = tmp_path / "commentary.sqlite3"
    exit_code = build_mod.main(["--combined", "--output", str(output)])
    assert exit_code == 1
    assert "Post-build sanity check failed" in capsys.readouterr().err
    # The file WAS moved into place (the import itself succeeded) -- the
    # sanity check is a belt-and-suspenders layer on top, not a guarantee
    # that --output never gets written; it fails the *build*, loudly.
    assert output.exists()


def test_combined_fetch_calvin_failure_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom():
        raise CalvinSourceFetchError("network down")

    monkeypatch.setattr(build_mod, "fetch_all_calvin_sources", _boom)

    output = tmp_path / "commentary.sqlite3"
    exit_code = build_mod.main(["--combined-fetch", "--output", str(output)])
    assert exit_code == 1
    assert "Calvin source fetch failed" in capsys.readouterr().err
    assert not output.exists()
