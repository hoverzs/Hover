"""Tests for Knowledge Base health check."""

from __future__ import annotations

import json
from pathlib import Path

from textus_kb.health import run_canonical_self_tests, run_health_check


def test_canonical_self_tests_pass() -> None:
    results = run_canonical_self_tests()
    assert all(r.ok for r in results if not r.input.startswith("__cross_input_consistency__"))
    john_consistency = next(r for r in results if r.input == "__cross_input_consistency__:0")
    luke_consistency = next(r for r in results if r.input == "__cross_input_consistency__:1")
    assert john_consistency.ok is True
    assert john_consistency.canonical == "John.4.1-42"
    assert luke_consistency.ok is True
    assert luke_consistency.canonical == "Luke.10.25-37"


def test_health_check_structure() -> None:
    report = run_health_check()
    assert report.manifest_status == "ok"
    assert report.manifest_version == "1"
    assert report.overall_status in {"ok", "degraded", "error"}
    assert len(report.sources) >= 5
    for source in report.sources:
        assert source.id
        assert isinstance(source.available, bool)
        assert source.license


def test_health_includes_tagnt_source() -> None:
    report = run_health_check()
    tagnt = next(s for s in report.sources if s.id == "stepbible_tagnt")
    assert tagnt.required is True
    assert tagnt.enabled is True


def test_health_canonical_jn4_self_test() -> None:
    report = run_health_check()
    jn_tests = [
        t for t in report.canonical_self_tests if "Jn" in t.input or "JHN" in t.input
    ]
    assert jn_tests
    assert all(t.ok for t in jn_tests)


def test_health_json_serializable() -> None:
    report = run_health_check()
    payload = json.dumps(report.to_dict(), ensure_ascii=False)
    parsed = json.loads(payload)
    assert "overall_status" in parsed
    assert "sources" in parsed
    assert "pilot_registry" in parsed


def test_health_includes_multi_pilot_registry() -> None:
    report = run_health_check()
    assert report.pilot_registry is not None
    assert report.pilot_registry.valid is True
    assert report.pilot_registry.pilot_count == 2
    pilot_ids = {pilot.pilot_id for pilot in report.pilot_registry.pilots}
    assert pilot_ids == {"john_4_1_42", "luke_10_25_37"}
    for pilot in report.pilot_registry.pilots:
        assert pilot.study_notes_available is True
        assert pilot.dictionary_available is True
        assert pilot.acai_json_available is True


def test_health_with_missing_required_source(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kb_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "test",
                "sources": [
                    {
                        "id": "missing_required",
                        "name": "Missing",
                        "source_type": "sqlite",
                        "language": "en",
                        "version": "1",
                        "license": "MIT",
                        "license_url": None,
                        "local_path": "data/generated/absent_file.sqlite3",
                        "required": True,
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = run_health_check(manifest_path)
    assert report.overall_status == "error"
    missing = next(s for s in report.sources if s.id == "missing_required")
    assert missing.available is False
    assert missing.errors


def test_health_optional_missing_is_degraded_not_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kb_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "test",
                "sources": [
                    {
                        "id": "optional_missing",
                        "name": "Optional",
                        "source_type": "sqlite",
                        "language": "en",
                        "version": "1",
                        "license": "MIT",
                        "license_url": None,
                        "local_path": "data/generated/optional_absent.sqlite3",
                        "required": False,
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = run_health_check(manifest_path)
    assert report.overall_status == "degraded"
    assert not report.errors


def test_main_module_entry_point() -> None:
    from textus_kb.health import main

    code = main([])
    assert code in {0, 1}
