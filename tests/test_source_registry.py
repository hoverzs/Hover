from __future__ import annotations

import json
from pathlib import Path

import pytest

from illustration_engine.paths import SOURCE_REGISTRY_PATH
from illustration_engine.source_registry import (
    PUBLISHABLE_LICENSE_STATUSES,
    SourceRecord,
    SourceRegistryError,
    is_publishable_license,
    load_source_registry,
    validate_source_record,
)


def _valid_record(**overrides: object) -> SourceRecord:
    defaults: dict[str, object] = dict(
        code="TEST_SOURCE_1",
        title="Teszt forrás",
        author="Teszt Szerző",
        orig_language="hu",
        publication_year=1900,
        edition_reference=None,
        license_status="public_domain_confirmed",
        license_basis_hu="Teszt indoklás.",
        rights_holder=None,
        source_url=None,
        retrieved_at=None,
        reliability_tier="high",
        notes_hu=None,
    )
    defaults.update(overrides)
    return SourceRecord(**defaults)  # type: ignore[arg-type]


def test_is_publishable_license_true_for_confirmed_and_permission_granted() -> None:
    assert is_publishable_license("public_domain_confirmed") is True
    assert is_publishable_license("permission_granted") is True


def test_is_publishable_license_false_for_assumed_by_age_unknown_restricted() -> None:
    assert is_publishable_license("public_domain_assumed_by_age") is False
    assert is_publishable_license("unknown") is False
    assert is_publishable_license("restricted") is False


def test_publishable_license_statuses_is_exactly_two_values() -> None:
    assert PUBLISHABLE_LICENSE_STATUSES == {"public_domain_confirmed", "permission_granted"}


def test_validate_source_record_accepts_valid_record() -> None:
    assert validate_source_record(_valid_record()) == []


def test_validate_source_record_rejects_invalid_code() -> None:
    errors = validate_source_record(_valid_record(code="not-a-valid-code"))
    assert any("code invalid" in e for e in errors)


def test_validate_source_record_rejects_missing_title() -> None:
    errors = validate_source_record(_valid_record(title="  "))
    assert any("title is required" in e for e in errors)


def test_validate_source_record_rejects_invalid_license_status() -> None:
    errors = validate_source_record(_valid_record(license_status="totally_made_up"))
    assert any("license_status invalid" in e for e in errors)


def test_validate_source_record_rejects_missing_license_basis() -> None:
    errors = validate_source_record(_valid_record(license_basis_hu=""))
    assert any("license_basis_hu is required" in e for e in errors)


def test_validate_source_record_rejects_invalid_reliability_tier() -> None:
    errors = validate_source_record(_valid_record(reliability_tier="ultra"))
    assert any("reliability_tier invalid" in e for e in errors)


def test_load_source_registry_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SourceRegistryError, match="not found"):
        load_source_registry(tmp_path / "missing.json")


def test_load_source_registry_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(SourceRegistryError, match="Invalid JSON"):
        load_source_registry(path)


def test_load_source_registry_rejects_duplicate_codes(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    entry = json.loads(json.dumps(_valid_record().__dict__))
    path.write_text(json.dumps({"sources": [entry, entry]}), encoding="utf-8")
    with pytest.raises(SourceRegistryError, match="duplicate code"):
        load_source_registry(path)


def test_load_source_registry_rejects_invalid_entry_and_aggregates_errors(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    bad_entry = json.loads(json.dumps(_valid_record(license_basis_hu="", reliability_tier="x").__dict__))
    path.write_text(json.dumps({"sources": [bad_entry]}), encoding="utf-8")
    with pytest.raises(SourceRegistryError) as exc_info:
        load_source_registry(path)
    message = str(exc_info.value)
    assert "license_basis_hu is required" in message
    assert "reliability_tier invalid" in message


def test_load_source_registry_requires_sources_array(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"not_sources": []}), encoding="utf-8")
    with pytest.raises(SourceRegistryError, match="'sources' array"):
        load_source_registry(path)


def test_load_source_registry_valid_records_are_returned(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    entry = json.loads(json.dumps(_valid_record().__dict__))
    path.write_text(json.dumps({"sources": [entry]}), encoding="utf-8")
    records = load_source_registry(path)
    assert len(records) == 1
    assert records[0].code == "TEST_SOURCE_1"


def test_seed_registry_file_exists_and_is_valid() -> None:
    assert SOURCE_REGISTRY_PATH.is_file()
    records = load_source_registry()
    assert len(records) >= 1


def test_seed_pesti_esopus_entry_is_not_yet_publishable() -> None:
    records = load_source_registry()
    pesti = next((r for r in records if r.code == "PESTI_ESOPUS_1536"), None)
    assert pesti is not None, "Expected PESTI_ESOPUS_1536 seed entry in sources.json"
    assert pesti.license_status == "public_domain_assumed_by_age"
    assert is_publishable_license(pesti.license_status) is False
    assert pesti.license_basis_hu.strip() != ""
